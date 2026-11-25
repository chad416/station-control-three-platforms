"""Write the Studio 5000 Logix Designer import file logix/StationPort.L5X.

NOT COMPILED: no Rockwell software was available. This file is written from the rules in the
manuals listed in logix/README.md and from the form of public L5X exports; whether Logix Designer
imports and verifies it is not known.

Sources
  logix/src/*.body.st         the Logix Structured Text of the two AOIs, the plant stand-in AOI,
                              the bench routine and the station routine
  codesys/src/*.st            declarations, taken over and changed by the rules below
  results/testdata.json       recorded curves and expected values (tools/testdata.py)

Port rules applied here (each one is a row of the findings table)
  - AOI Input and Output parameters only BOOL, SINT, INT, DINT, REAL (1756-PM010I p. 43):
    the recipe is an InOut of the UDT ST_EvalRecipe, the counter array an InOut DINT[32].
  - Arrays have a size, not bounds: ARRAY[lo..hi] becomes [hi + 1] and index lo..hi is kept
    (element 0 unused where lo = 1). BOOL arrays get 64 elements.
  - No temporary variables in an AOI: VAR_TEMP become local tags (they keep their value).
  - The bench is a routine, not an AOI: an AOI sees only its parameters and local tags.
    Its static variables are program tags.

    python tools/make_logix.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
CDS = ROOT / "codesys" / "src"
LGX = ROOT / "logix"
OUT = LGX / "StationPort.L5X"

TYPES = {"real": "REAL", "int": "INT", "dint": "DINT", "bool": "BOOL"}
REC = ["Mode", "GateX", "Gate2X", "PeakXLo", "PeakXHi", "StepSpan", "StopF", "G1Lo", "G1Hi", "MeanLo",
       "MeanHi", "HystLo", "HystHi", "RetFMin", "G2Lo", "G2Hi", "PeakFLo", "PeakFHi", "PeakXMin",
       "PeakXMax", "StepLo", "StopXLo", "StopXHi", "EnvX0", "EnvDx", "EnvN", "EnvLo", "EnvHi"]

_DECL = re.compile(r"^\s*(\w+)\s*:\s*(ARRAY\[(\d+)\.\.(\d+)\]\s+OF\s+(\w+)|\w+)\s*(?::=\s*([^;]+))?;", re.I)


def parse_decl(path: Path) -> dict[str, list[dict]]:
    """VAR sections of a CODESYS source: section -> [{name, type, dim, init}]."""
    text = path.read_text(encoding="utf-8").split("(* @IMPLEMENTATION *)")[0]
    sec, out = None, {}
    for line in text.splitlines():
        s = line.split("//")[0].strip()
        if s.upper() in ("VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR", "VAR_TEMP", "STRUCT"):
            sec = s.upper()
            out.setdefault(sec, [])
            continue
        if s.upper() in ("END_VAR", "END_STRUCT"):
            sec = None
            continue
        m = _DECL.match(s)
        if sec and m:
            if m.group(3) is not None:
                typ, dim = m.group(5), int(m.group(4)) + 1
            else:
                typ, dim = m.group(2), 0
            typ = TYPES.get(typ.lower(), typ.replace("FB_", "AOI_"))
            if typ == "BOOL" and dim:
                dim = 64 if dim <= 64 else ((dim + 31) // 32) * 32
            out[sec].append({"name": m.group(1), "type": typ, "dim": dim, "init": (m.group(6) or "").strip()})
    return out


def radix(t: str) -> str:
    return {"REAL": "Float", "BOOL": "Decimal", "INT": "Decimal", "DINT": "Decimal", "SINT": "Decimal"}.get(t, "NullType")


def fmt(t: str, v) -> str:
    if t == "REAL":
        return repr(float(v)) if v not in ("", None) else "0.0"
    if t == "BOOL":
        return "1" if str(v).upper() in ("1", "TRUE") else "0"
    return str(int(v)) if v not in ("", None) else "0"


def atomic(t: str) -> bool:
    return t in ("REAL", "BOOL", "INT", "DINT", "SINT")


def data_value(t: str, v="") -> str:
    return f'<DataValue DataType="{t}" Radix="{radix(t)}" Value="{fmt(t, v)}"/>'


def array_xml(tag: str, t: str, dim: int, values=None, name: str | None = None) -> str:
    values = values if values is not None else [""] * dim
    els = "".join(f'<Element Index="[{i}]" Value="{fmt(t, values[i] if i < len(values) else "")}"/>' for i in range(dim))
    nm = f' Name="{name}"' if name else ""
    rad = "" if t == "BOOL" else f' Radix="{radix(t)}"'
    return f'<{tag}{nm} DataType="{t}" Dimensions="{dim}"{rad}>{els}</{tag}>'


def cdata_lines(text: str) -> str:
    lines = text.rstrip("\n").split("\n")
    return "".join(f'<Line Number="{i}"><![CDATA[{ln}]]></Line>\n' for i, ln in enumerate(lines))


def description(text: str) -> str:
    return f"<Description><![CDATA[{text}]]></Description>" if text else ""


# ---------------------------------------------------------------- declarations

def recipe_udt() -> list[dict]:
    return parse_decl(CDS / "ST_EvalRecipe.st")["STRUCT"]


def aoi_defs() -> dict[str, dict]:
    ce = parse_decl(CDS / "FB_CurveEval.st")
    st = parse_decl(CDS / "FB_HandleStation.st")
    pl = parse_decl(CDS / "FB_TestPlant.st")
    defs = {}
    defs["AOI_CurveEval"] = {
        "desc": "Force-travel curve evaluation, one sample per call. Port of FB_CurveEval.",
        "body": "CurveEval.body.st",
        "inputs": [v for v in ce["VAR_INPUT"] if v["name"] not in REC],
        "inouts": [{"name": "Rcp", "type": "ST_EvalRecipe", "dim": 0, "init": ""}],
        "outputs": ce["VAR_OUTPUT"],
        "locals": ce["VAR"] + ce.get("VAR_TEMP", []),
    }
    outs = [v for v in st["VAR_OUTPUT"] if v["dim"] == 0]
    outs += [{"name": "E_" + n, "type": "REAL", "dim": 0, "init": ""}
             for n in ("FpG1", "FrG1", "FMean", "FHyst", "FpG2", "FPeak", "XPeak", "FStep", "XStop")]
    defs["AOI_HandleStation"] = {
        "desc": "Force-travel test station: sequence, poka-yoke, counters. Port of FB_HandleStation.",
        "body": "HandleStation.body.st",
        "inputs": st["VAR_INPUT"],
        "inouts": [{"name": "Rcp", "type": "ST_EvalRecipe", "dim": 0, "init": ""},
                   {"name": "CntByCode", "type": "DINT", "dim": 32, "init": ""}],
        "outputs": outs,
        "locals": st["VAR"] + st.get("VAR_TEMP", []) + [{"name": "sRcp", "type": "ST_EvalRecipe", "dim": 0, "init": ""}],
    }
    defs["AOI_TestPlant"] = {
        "desc": "Test bench only: stand-in for axis, clamp and handle. Port of FB_TestPlant.",
        "body": "TestPlant.body.st",
        "inputs": pl["VAR_INPUT"],
        "inouts": [{"name": "X", "type": "REAL", "dim": 5932, "init": ""},
                   {"name": "F", "type": "REAL", "dim": 5932, "init": ""},
                   {"name": "CurveStart", "type": "INT", "dim": 16, "init": ""},
                   {"name": "CurveNPull", "type": "INT", "dim": 16, "init": ""}],
        "outputs": pl["VAR_OUTPUT"],
        "locals": pl["VAR"] + pl.get("VAR_TEMP", []),
    }
    return defs


def bench_tags() -> list[dict]:
    b = parse_decl(CDS / "FB_TestBench.st")
    tags = b["VAR_INPUT"] + [v for v in b["VAR"] if v["name"] != "StationRcp"] + b.get("VAR_TEMP", [])
    tags += [{"name": "BenchRcp", "type": "ST_EvalRecipe", "dim": 0, "init": ""},
             {"name": "StationRcp", "type": "ST_EvalRecipe", "dim": 0, "init": ""},
             {"name": "StationCnt", "type": "DINT", "dim": 32, "init": ""}]
    return tags


# ---------------------------------------------------------------- XML

def param_xml(p: dict, usage: str, required: bool) -> str:
    t = p["type"]
    dims = f' Dimensions="{p["dim"]}"' if p["dim"] else ""
    rad = f' Radix="{radix(t)}"' if atomic(t) else ""
    req = "true" if required else "false"
    acc = "Read/Write" if usage == "Input" else "Read Only" if usage == "Output" else ""
    acc_attr = f' ExternalAccess="{acc}"' if acc else ""
    dflt = ""
    if usage in ("Input", "Output"):
        dflt = f'<DefaultData Format="Decorated">{data_value(t, p["init"])}</DefaultData>'
    return (f'<Parameter Name="{p["name"]}" TagType="Base" DataType="{t}"{dims} Usage="{usage}"{rad} '
            f'Required="{req}" Visible="{req if usage != "Output" else "true"}"{acc_attr}>{dflt}</Parameter>\n')


def struct_data(t: str, defs: dict, udt: list[dict]) -> str:
    """Decorated start values of a tag of an AOI or UDT type (atomic members and arrays only)."""
    if t == "ST_EvalRecipe":
        mem = udt
    else:
        d = defs[t]
        mem = [{"name": "EnableIn", "type": "BOOL", "dim": 0, "init": "1"},
               {"name": "EnableOut", "type": "BOOL", "dim": 0, "init": "0"}] + d["inputs"] + d["outputs"]
    parts = []
    for m in mem:
        if m["dim"]:
            parts.append(array_xml("ArrayMember", m["type"], m["dim"], name=m["name"]))
        elif atomic(m["type"]):
            parts.append(f'<DataValueMember Name="{m["name"]}" DataType="{m["type"]}"'
                         + ("" if m["type"] == "BOOL" else f' Radix="{radix(m["type"])}"')
                         + f' Value="{fmt(m["type"], m["init"])}"/>')
    return f'<Structure DataType="{t}">' + "".join(parts) + "</Structure>"


def local_xml(v: dict, defs: dict, udt: list[dict]) -> str:
    t = v["type"]
    if v["dim"]:
        return (f'<LocalTag Name="{v["name"]}" DataType="{t}" Dimensions="{v["dim"]}"'
                + (f' Radix="{radix(t)}"' if atomic(t) else "") + ' ExternalAccess="None">'
                + f'<DefaultData Format="Decorated">{array_xml("Array", t, v["dim"])}</DefaultData></LocalTag>\n')
    if atomic(t):
        return (f'<LocalTag Name="{v["name"]}" DataType="{t}" Radix="{radix(t)}" ExternalAccess="None">'
                f'<DefaultData Format="Decorated">{data_value(t, v["init"])}</DefaultData></LocalTag>\n')
    return (f'<LocalTag Name="{v["name"]}" DataType="{t}" ExternalAccess="None">'
            f'<DefaultData Format="Decorated">{struct_data(t, defs, udt)}</DefaultData></LocalTag>\n')


def tag_xml(v: dict, defs: dict, udt: list[dict], values=None, desc: str = "") -> str:
    t = v["type"]
    head = f'<Tag Name="{v["name"]}" TagType="Base" DataType="{t}"'
    if v["dim"]:
        head += f' Dimensions="{v["dim"]}"'
    if atomic(t):
        head += f' Radix="{radix(t)}"'
    head += ' Constant="false" ExternalAccess="Read/Write">'
    if v["dim"]:
        data = array_xml("Array", t, v["dim"], values)
    elif atomic(t):
        data = data_value(t, values if values is not None else v["init"])
    else:
        data = struct_data(t, defs, udt)
    return head + description(desc) + f'<Data Format="Decorated">{data}</Data></Tag>\n'


def alarm_tag(name: str, severity: int, desc: str) -> str:
    return (f'<Tag Name="{name}" TagType="Base" DataType="ALARM_DIGITAL" ExternalAccess="Read/Write">'
            + description(desc)
            + f'<Data Format="Alarm"><AlarmDigitalParameters Severity="{severity}" MinDurationPRE="0" ShelveDuration="0" '
            'MaxShelveDuration="0" ProgTime="DT#1970-01-01-00:00:00.000_000Z" EnableIn="false" In="false" '
            'InFault="false" Condition="true" AckRequired="true" Latched="false" ProgAck="false" OperAck="false" '
            'ProgReset="false" OperReset="false" ProgSuppress="false" OperSuppress="false" ProgUnsuppress="false" '
            'OperUnsuppress="false" OperShelve="false" ProgUnshelve="false" OperUnshelve="false" ProgDisable="false" '
            'OperDisable="false" ProgEnable="false" OperEnable="false" AlarmCountReset="false" UseProgTime="false"/>'
            '<AlarmConfig/></Data></Tag>\n')


ALARMS = [  # tag, severity, condition text (station program), description
    ("ALM_SafetyOpen", 900, "Station.FaultCode = 1", "Fault 1: safety circuit open"),
    ("ALM_DriveNotReady", 800, "Station.FaultCode = 2", "Fault 2: drive not ready"),
    ("ALM_ClampTimeout", 700, "Station.FaultCode = 3", "Fault 3: clamp did not close in time"),
    ("ALM_TareFailed", 700, "Station.FaultCode = 4", "Fault 4: load cell does not tare"),
    ("ALM_RejectWaiting", 500, "Station.Locked AND Station.QCallOperator", "Reject lock: part waits for the reject chute"),
    ("ALM_RigCheck", 600, "Station.RigCheckRequired", "Three rejects in a row: run the master part"),
]


def main() -> None:
    td = json.loads((ROOT / "results" / "testdata.json").read_text(encoding="utf-8"))
    udt = recipe_udt()
    defs = aoi_defs()
    x = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n',
         "<!--Written by tools/make_logix.py. NOT compiled or imported in Logix Designer: no Rockwell software was available.-->\n",
         '<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="34.01" TargetName="StationPort" TargetType="Controller" '
         'ContainsContext="false" ExportDate="Wed Nov 25 00:00:00 2026" ExportOptions="NoRawData DecoratedData ForceProtectedEncoding AllProjDocTrans">\n',
         '<Controller Use="Target" Name="StationPort" ProcessorType="1756-L85E" MajorRev="34" MinorRev="11">\n',
         description("Port of the door-handle force-travel station (Siemens SCL / CODESYS ST) to Logix. Not compiled."),
         "<DataTypes>\n",
         '<DataType Name="ST_EvalRecipe" Family="NoFamily" Class="User">',
         description("Evaluation recipe of AOI_CurveEval. Arrays must be InOut (AOI Input/Output: atomic types only)."),
         "<Members>\n"]
    for m in udt:
        dims = m["dim"]
        x.append(f'<Member Name="{m["name"]}" DataType="{m["type"]}" Dimension="{dims}" Radix="{radix(m["type"])}" '
                 'Hidden="false" ExternalAccess="Read/Write"/>\n')
    x += ["</Members></DataType>\n</DataTypes>\n<AddOnInstructionDefinitions>\n"]
    # nested AOI first: a definition must exist before it is used
    for name in ["AOI_CurveEval", "AOI_TestPlant", "AOI_HandleStation"]:
        d = defs[name]
        body = (LGX / "src" / d["body"]).read_text(encoding="utf-8")
        x.append(f'<AddOnInstructionDefinition Name="{name}" Revision="1.0" ExecutePrescan="false" '
                 'ExecutePostscan="false" ExecuteEnableInFalse="false">\n' + description(d["desc"]) + "<Parameters>\n")
        x.append('<Parameter Name="EnableIn" TagType="Base" DataType="BOOL" Usage="Input" Radix="Decimal" Required="false" Visible="false" ExternalAccess="Read Only"/>\n')
        x.append('<Parameter Name="EnableOut" TagType="Base" DataType="BOOL" Usage="Output" Radix="Decimal" Required="false" Visible="false" ExternalAccess="Read Only"/>\n')
        for p in d["inputs"]:
            x.append(param_xml(p, "Input", False))
        for p in d["inouts"]:
            x.append(param_xml(p, "InOut", True))
        for p in d["outputs"]:
            x.append(param_xml(p, "Output", False))
        x.append("</Parameters>\n<LocalTags>\n")
        for v in d["locals"]:
            x.append(local_xml(v, defs, udt))
        x.append('</LocalTags>\n<Routines>\n<Routine Name="Logic" Type="ST">\n<STContent>\n' + cdata_lines(body)
                 + "</STContent>\n</Routine>\n</Routines>\n</AddOnInstructionDefinition>\n")
    x.append("</AddOnInstructionDefinitions>\n<Tags>\n")
    # controller tags: test data (TD_), bench result (TR_)
    vals, bounds = td["values"], td["bounds"]
    for n, v in vals.items():
        if n in bounds:
            lo, hi = bounds[n]
            t = {"X": "REAL", "F": "REAL"}.get(n)
            t = t or ("REAL" if isinstance(v[0], float) else "BOOL" if isinstance(v[0], bool) else "INT")
            dim = hi + 1
            if t == "BOOL":
                dim = 64 if dim <= 64 else ((dim + 31) // 32) * 32
            arr = [None] * lo + list(v)
            arr = [a if a is not None else ("" if t != "BOOL" else 0) for a in arr]
            x.append(tag_xml({"name": "TD_" + n, "type": t, "dim": dim, "init": ""}, defs, udt, arr))
        else:
            t = "REAL" if isinstance(v, float) else "BOOL" if isinstance(v, bool) else "INT"
            x.append(tag_xml({"name": "TD_" + n, "type": t, "dim": 0, "init": ""}, defs, udt, v))
    res = parse_decl(CDS / "GVL_TestResult.st")
    x.append("</Tags>\n")
    # the result list: parse the CODESYS GVL (VAR_GLOBAL)
    text = (CDS / "GVL_TestResult.st").read_text(encoding="utf-8")
    rtags = []
    for line in text.splitlines():
        m = _DECL.match(line.split("//")[0])
        if m:
            if m.group(3) is not None:
                t, dim = TYPES[m.group(5).lower()], int(m.group(4)) + 1
                if t == "BOOL":
                    dim = 64
            else:
                t, dim = TYPES[m.group(2).lower()], 0
            rtags.append({"name": "TR_" + m.group(1), "type": t, "dim": dim, "init": ""})
    del res
    x[-1] = "".join(tag_xml(v, defs, udt) for v in rtags) + "</Tags>\n"
    x.append("<Programs>\n")
    # bench program
    x.append('<Program Name="BenchProgram" TestEdits="false" MainRoutineName="Bench" Disabled="false" UseAsFolder="false">\n'
             + description("Test bench: replays recorded curves and runs the station against a stand-in. Port of FB_TestBench.")
             + "<Tags>\n")
    for v in bench_tags():
        x.append(tag_xml(v, defs, udt))
    body = (LGX / "src" / "TestBench.body.st").read_text(encoding="utf-8")
    x.append('</Tags>\n<Routines>\n<Routine Name="Bench" Type="ST">\n<STContent>\n' + cdata_lines(body)
             + "</STContent>\n</Routine>\n</Routines>\n</Program>\n")
    # station program: the station on real I/O, with its alarms
    st = defs["AOI_HandleStation"]
    x.append('<Program Name="StationProgram" TestEdits="false" MainRoutineName="Station" Disabled="false" UseAsFolder="false">\n'
             + description("The station on the machine. Runs in the periodic task StationTask; its Rate must equal Station.CycleTime.")
             + "<Tags>\n")
    x.append(tag_xml({"name": "Station", "type": "AOI_HandleStation", "dim": 0, "init": ""}, defs, udt))
    x.append(tag_xml({"name": "Rcp", "type": "ST_EvalRecipe", "dim": 0, "init": ""}, defs, udt,
                     desc="Evaluation recipe, written by the operator screen or a recipe manager"))
    x.append(tag_xml({"name": "CntByCode", "type": "DINT", "dim": 32, "init": ""}, defs, udt, desc="Parts per NOK code"))
    x.append(tag_xml({"name": "AlmAck", "type": "BOOL", "dim": 0, "init": ""}, defs, udt, desc="Programmatic acknowledge of all station alarms"))
    x.append(tag_xml({"name": "AlmZero", "type": "BOOL", "dim": 0, "init": ""}, defs, udt, desc="Always 0: unused ALMD operands"))
    for name, sev, cond, desc in ALARMS:
        x.append(tag_xml({"name": name + "_In", "type": "BOOL", "dim": 0, "init": ""}, defs, udt, desc="Condition of " + name))
        x.append(alarm_tag(name, sev, desc))
    x.append("</Tags>\n<Routines>\n")
    body = (LGX / "src" / "Station.routine.st").read_text(encoding="utf-8")
    al = ["", "// --- Alarms: one ALMD per condition (Logix alarm instruction; the panel or FactoryTalk shows them) ---"]
    for name, _sev, cond, _d in ALARMS:
        al.append(f"{name}_In := {cond};")
        al.append(f"ALMD({name}, {name}_In, AlmAck, AlmZero, AlmZero, AlmZero);")
    x.append('<Routine Name="Station" Type="ST">\n<STContent>\n' + cdata_lines(body + "\n".join(al) + "\n")
             + "</STContent>\n</Routine>\n</Routines>\n</Program>\n</Programs>\n")
    x.append('<Tasks>\n<Task Name="BenchTask" Type="CONTINUOUS" Priority="10" Watchdog="500" DisableUpdateOutputs="false" InhibitTask="false">'
             '<ScheduledPrograms><ScheduledProgram Name="BenchProgram"/></ScheduledPrograms></Task>\n'
             '<Task Name="StationTask" Type="PERIODIC" Rate="2" Priority="5" Watchdog="10" DisableUpdateOutputs="false" InhibitTask="true">'
             '<ScheduledPrograms><ScheduledProgram Name="StationProgram"/></ScheduledPrograms></Task>\n</Tasks>\n')
    x.append("</Controller>\n</RSLogix5000Content>\n")
    OUT.write_text("".join(x), encoding="utf-8")
    print(OUT, OUT.stat().st_size, "bytes")
    del st


if __name__ == "__main__":
    main()
