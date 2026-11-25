"""Structural check of logix/StationPort.L5X, written in this repo. It is NOT Logix Designer.

What it checks (rule source in brackets; PM010 = Rockwell 1756-PM010I-EN-P, Feb 2018, read through
a public copy, page numbers of the manual):
  X1  the file is well-formed XML, root RSLogix5000Content, one Controller
  X2  every data type used is atomic, ALARM_DIGITAL, a UDT or an AOI defined in the file
  X3  user-defined types come before the AOIs, a nested AOI before the AOI that uses it
      (PM010 p. 99: import data types before the AOIs that use them)
  A1  AOI Input and Output parameters are BOOL, SINT, INT, DINT or REAL and not arrays (PM010 p. 43)
  A2  InOut parameters are Required and Visible (PM010 pp. 34-35)
  A3  names of AOIs, parameters, local tags and tags have at most 40 characters (PM010 p. 41 gives
      40 for the AOI name; the same limit is applied to every name here)
  A4  descriptions have at most 512 characters (PM010 p. 42)
  A5  local tag arrays have one dimension (PM010 p. 46)
  A6  AOI nesting depth at most 8 (PM010 pp. 28-29 recommends at most eight levels)
  A7  every AOI call in ST passes the instance tag of that AOI type and exactly its required
      parameters (PM010 p. 76, 84); here all required parameters are InOut
  S1  every ST routine parses with the subset parser of tools/logix_st.py
  S2  every tag name used in a routine resolves in its scope (AOI: parameters and local tags only,
      PM010 p. 19 local tags are not reachable from outside; program: program then controller tags)
  T1  every scheduled program exists, every program's main routine exists
  D1  decorated array data stays inside the declared dimension

What it does not check: anything else Logix Designer verifies (instruction operand types, the
ALMD operand rules, tag data layout, the controller and its firmware). Passing it does not mean
the file imports.

    python tools/l5x_check.py logix/StationPort.L5X
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import logix_st as lx  # noqa: E402

ATOMIC = {"BOOL", "SINT", "INT", "DINT", "REAL"}
BUILTIN_INSTR = {"COP", "ALMD"}


def names_used(stmts):
    """Base names of every tag reference, and the AOI calls, in parsed ST."""
    refs, calls = set(), []

    def ex(e):
        if e[0] == "ref":
            refs.add(e[1][0][1].lower())
            for kind, v in e[1][1:]:
                if kind == "index":
                    ex(v)
        elif e[0] in ("bin",):
            ex(e[2]); ex(e[3])
        elif e[0] in ("not", "neg"):
            ex(e[1])
        elif e[0] == "fn":
            for a in e[2]:
                ex(a)

    def st(s):
        k = s[0]
        if k == "set":
            ex(s[1]); ex(s[2])
        elif k == "if":
            for c, b in s[1]:
                ex(c)
                for x in b:
                    st(x)
            for x in s[2]:
                st(x)
        elif k == "case":
            ex(s[1])
            for _l, b in s[2]:
                for x in b:
                    st(x)
            for x in s[3]:
                st(x)
        elif k == "for":
            ex(s[1]); ex(s[2]); ex(s[3]); ex(s[4])
            for x in s[5]:
                st(x)
        elif k == "call":
            calls.append((s[1], s[2]))
            for a in s[2]:
                if a[0] != "none":
                    ex(a)
    for s in stmts:
        st(s)
    return refs, calls


def check(path: Path) -> list[str]:
    errs: list[str] = []
    ok: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        return [f"X1 not well-formed: {e}"]
    if root.tag != "RSLogix5000Content" or len(root.findall("Controller")) != 1:
        errs.append("X1 root must be RSLogix5000Content with one Controller")
    ctl = root.find("Controller")
    udts = [d.get("Name") for d in ctl.iter("DataType")]
    aois = [a.get("Name") for a in ctl.iter("AddOnInstructionDefinition")]
    known = ATOMIC | {"ALARM_DIGITAL"} | {u.upper() for u in udts} | {a.upper() for a in aois}

    def typ_ok(t, where):
        if t is None or t.upper() not in known:
            errs.append(f"X2 unknown data type {t} in {where}")

    def name_ok(n, where):
        if len(n) > 40:
            errs.append(f"A3 name longer than 40 characters: {n} ({where})")

    for d in ctl.iter("DataType"):
        name_ok(d.get("Name"), "data type")
        for m in d.iter("Member"):
            typ_ok(m.get("DataType"), "UDT " + d.get("Name"))
            name_ok(m.get("Name"), "member")
    for e in root.iter("Description"):
        if e.text and len(e.text) > 512:
            errs.append("A4 description longer than 512 characters")

    # order: UDTs before AOIs; nested AOI before its user
    children = [c.tag for c in ctl]
    if "DataTypes" in children and "AddOnInstructionDefinitions" in children:
        if children.index("DataTypes") > children.index("AddOnInstructionDefinitions"):
            errs.append("X3 DataTypes must come before AddOnInstructionDefinitions")
    seen = set()
    nest = {}
    for a in ctl.iter("AddOnInstructionDefinition"):
        an = a.get("Name")
        name_ok(an, "AOI")
        nest[an.upper()] = []
        for p in a.iter("Parameter"):
            u, t, dims = p.get("Usage"), p.get("DataType"), p.get("Dimensions")
            name_ok(p.get("Name"), an)
            typ_ok(t, an + "." + p.get("Name"))
            if u in ("Input", "Output") and (t not in ATOMIC or dims):
                errs.append(f"A1 {an}.{p.get('Name')}: {u} parameter must be atomic, is {t}{'[' + dims + ']' if dims else ''}")
            if u == "InOut" and not (p.get("Required") == "true" and p.get("Visible") == "true"):
                errs.append(f"A2 {an}.{p.get('Name')}: InOut parameter must be Required and Visible")
        for t in a.iter("LocalTag"):
            name_ok(t.get("Name"), an)
            typ_ok(t.get("DataType"), an + "." + t.get("Name"))
            if t.get("Dimensions") and "," in t.get("Dimensions"):
                errs.append(f"A5 {an}.{t.get('Name')}: local tag array with more than one dimension")
            if t.get("DataType").upper() in {x.upper() for x in aois}:
                nest[an.upper()].append(t.get("DataType").upper())
                if t.get("DataType").upper() not in seen:
                    errs.append(f"X3 {an} uses {t.get('DataType')} before its definition")
        seen.add(an.upper())

    def depth(n, stack=()):
        if n in stack:
            errs.append("A6 recursive AOI nesting " + n)
            return 99
        return 1 + max((depth(c, stack + (n,)) for c in nest.get(n, [])), default=0)
    for n in nest:
        if depth(n) > 8:
            errs.append(f"A6 nesting deeper than 8 levels in {n}")

    for arr in root.iter("Array"):
        dim = int(arr.get("Dimensions"))
        for el in arr.iter("Element"):
            if not 0 <= int(el.get("Index").strip("[]")) < dim:
                errs.append("D1 element outside its array")

    # ST: parse, names, calls
    m = lx.Model(path)
    aoi_params = {k: v for k, v in m.aoi.items()}

    def check_routine(src, where, scope_names, scope_types):
        try:
            stmts = lx.parse(src)
        except lx.LogixError as e:
            errs.append(f"S1 {where}: {e}")
            return
        refs, calls = names_used(stmts)
        for r in sorted(refs - scope_names):
            errs.append(f"S2 {where}: tag {r} is not visible here")
        for name, args in calls:
            if name.upper() in BUILTIN_INSTR:
                continue
            a = aoi_params.get(name.lower())
            if a is None:
                errs.append(f"A7 {where}: unknown instruction {name}")
                continue
            req = [p for p in a["params"] if p[4]]
            if len(args) != 1 + len(req):
                errs.append(f"A7 {where}: {name} needs the instance and {len(req)} required arguments, has {len(args) - 1}")
            if args and args[0][0] == "ref" and len(args[0][1]) == 1:
                t = scope_types.get(args[0][1][0][1].lower())
                if t is None or t.lower() != name.lower():
                    errs.append(f"A7 {where}: instance {args[0][1][0][1]} of {name} has type {t}")

    for k, a in m.aoi.items():
        names = {p[0].lower() for p in a["params"]} | {t[0].lower() for t in a["locals"]}
        types = {p[0].lower(): p[1] for p in a["params"]} | {t[0].lower(): t[1] for t in a["locals"]}
        check_routine(a["src"], a["name"], names, types)
    ctl_types = {t.get("Name").lower(): t.get("DataType") for t in ctl.find("Tags")}
    for t in ctl.find("Tags"):
        name_ok(t.get("Name"), "controller tag")
        typ_ok(t.get("DataType"), "tag " + t.get("Name"))
    for p in ctl.iter("Program"):
        ptypes = {t.get("Name").lower(): t.get("DataType") for t in p.find("Tags")}
        for t in p.find("Tags"):
            name_ok(t.get("Name"), "program tag")
            typ_ok(t.get("DataType"), "tag " + t.get("Name"))
        routines = {r.get("Name") for r in p.iter("Routine")}
        if p.get("MainRoutineName") not in routines:
            errs.append(f"T1 {p.get('Name')}: main routine {p.get('MainRoutineName')} missing")
        for rn, src in m.programs[p.get("Name")]["routines"].items():
            check_routine(src, p.get("Name") + "/" + rn, set(ptypes) | set(ctl_types), {**ctl_types, **ptypes})
    programs = {p.get("Name") for p in ctl.iter("Program")}
    for t in ctl.iter("ScheduledProgram"):
        if t.get("Name") not in programs:
            errs.append(f"T1 scheduled program {t.get('Name')} missing")
    del ok
    return errs


if __name__ == "__main__":
    p = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "logix" / "StationPort.L5X")
    e = check(p)
    for x in e:
        print(x)
    print(f"{p.name}: {len(e)} findings")
    sys.exit(1 if e else 0)
