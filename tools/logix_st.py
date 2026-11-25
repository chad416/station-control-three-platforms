"""A small interpreter for the subset of Logix Structured Text used in logix/StationPort.L5X.

It reads the L5X file itself (data types, Add-On Instruction definitions, tags with their decorated
start values, routines) and runs a routine, so the check runs the text that would be imported.

What it proves: the Structured Text in the L5X, read with the semantics below, gives the same
20 bench results as the Siemens and CODESYS versions. What it does NOT prove: that Logix Designer
accepts the file, that the controller's arithmetic, conversion and scan behave as assumed here, or
anything about timing. It is not Rockwell software and was not checked against a controller.

Semantics assumed (not verified on a controller)
  REAL   numpy.float32, rounded after every operation; INT and DINT mixed with REAL become REAL
  INT    16-bit, DINT 32-bit, wrapped when stored; integer arithmetic in Python ints
  BOOL   stored as 0 or 1; any non-zero value stored into a BOOL is 1
  arrays zero-based, size from Dimensions; an index outside raises (a major fault on a controller)
  AOI    called as  Name(instance, inout1, inout2 ...): instance tag first, then the required
         parameters (here: only the InOut parameters) in the order of the definition
         (1756-PM010I p. 76, 84); Input and Output parameters are members of the instance tag;
         local tags keep their value between calls; InOut parameters are references (p. 43)
  COP    COP(source, destination, length): element-wise copy; length counts destination elements
Supported: :=, IF/ELSIF/ELSE, CASE (integer labels and lists, ELSE), FOR ... TO ... [BY] ... DO,
AND OR XOR NOT MOD, comparisons, + - * /, ABS, COP, AOI calls. Anything else raises LogixError.
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np


class LogixError(Exception):
    pass


# ---------------------------------------------------------------- values

class Arr(list):
    def __init__(self, typ, n, values=None):
        super().__init__([conv(typ, 0)] * n if values is None else values)
        self.t = typ


class Struct:
    """Instance of a UDT or an AOI, and also a tag scope. Field names are case-insensitive."""

    def __init__(self, typ):
        self.typ = typ
        self.f = {}
        self.t = {}

    def __deepcopy__(self, memo):
        s = Struct(self.typ)
        s.t = dict(self.t)
        s.f = {k: copy.deepcopy(v, memo) for k, v in self.f.items()}
        return s


def wrap(v, bits):
    v = int(v) & ((1 << bits) - 1)
    return v - (1 << bits) if v >= 1 << (bits - 1) else v


def to_int(v):
    if isinstance(v, (float, np.floating)):
        return int(np.rint(v))   # round half to even
    return int(v)


def conv(typ, v):
    if typ == "REAL":
        return np.float32(v)
    if typ == "BOOL":
        return 1 if v else 0
    if typ == "INT":
        return wrap(to_int(v), 16)
    if typ == "DINT":
        return wrap(to_int(v), 32)
    if typ == "SINT":
        return wrap(to_int(v), 8)
    return v


def is_real(v):
    return isinstance(v, (float, np.floating))


# ---------------------------------------------------------------- L5X model

class Model:
    def __init__(self, path: Path):
        root = ET.parse(path).getroot()
        ctl = root.find("Controller")
        self.udt = {}
        for dt in ctl.iter("DataType"):
            self.udt[dt.get("Name").lower()] = [(m.get("Name"), m.get("DataType"), int(m.get("Dimension") or 0))
                                                for m in dt.iter("Member")]
        self.aoi = {}
        for a in ctl.iter("AddOnInstructionDefinition"):
            params = [(p.get("Name"), p.get("DataType"), int(p.get("Dimensions") or 0), p.get("Usage"),
                       p.get("Required") == "true", p.find("DefaultData/DataValue")) for p in a.iter("Parameter")]
            locs = [(t.get("Name"), t.get("DataType"), int(t.get("Dimensions") or 0), t.find("DefaultData"))
                    for t in a.iter("LocalTag")]
            logic = None
            for r in a.iter("Routine"):
                if r.get("Name") == "Logic":
                    logic = "\n".join((ln.text or "") for ln in r.iter("Line"))
            self.aoi[a.get("Name").lower()] = {"name": a.get("Name"), "params": params, "locals": locs,
                                               "src": logic, "code": None}
        self.ctl_tags = Struct("controller")
        for t in ctl.find("Tags"):
            self._add_tag(self.ctl_tags, t)
        self.programs = {}
        for p in ctl.iter("Program"):
            scope = Struct(p.get("Name"))
            for t in p.find("Tags"):
                self._add_tag(scope, t)
            routines = {r.get("Name"): "\n".join((ln.text or "") for ln in r.iter("Line")) for r in p.iter("Routine")}
            self.programs[p.get("Name")] = {"tags": scope, "routines": routines, "code": {}}
        self.tasks = [(t.get("Name"), t.get("Type"), t.get("Rate"), t.get("InhibitTask"),
                       [s.get("Name") for s in t.iter("ScheduledProgram")]) for t in ctl.iter("Task")]

    # values ----------------------------------------------------------
    def new(self, typ, dim=0, data=None):
        if dim:
            arr = Arr(typ, dim)
            if not atomic(typ):
                arr[:] = [self.new(typ) for _ in range(dim)]
            if data is not None and data.tag == "Array":
                for e in data.iter("Element"):
                    i = int(e.get("Index").strip("[]"))
                    arr[i] = conv(typ, float(e.get("Value")) if typ == "REAL" else int(float(e.get("Value"))))
            return arr
        if atomic(typ):
            if data is not None and data.get("Value") is not None:
                return conv(typ, float(data.get("Value")) if typ == "REAL" else int(float(data.get("Value"))))
            return conv(typ, 0)
        s = Struct(typ)
        key = typ.lower()
        if key in self.udt:
            for n, t, d in self.udt[key]:
                self._field(s, n, t, d)
        elif key in self.aoi:
            a = self.aoi[key]
            for n, t, d, usage, _req, dv in a["params"]:
                if usage == "InOut":
                    continue
                self._field(s, n, t, d, dv)
            for n, t, d, dd in a["locals"]:
                inner = None
                if dd is not None and len(dd):
                    inner = dd[0]
                self._field(s, n, t, d, inner)
            s.f["enablein"] = 1
        else:
            raise LogixError("unknown data type " + typ)
        if data is not None and data.tag == "Structure":
            self._fill(s, data)
        return s

    def _field(self, s, n, t, d, data=None):
        s.f[n.lower()] = self.new(t, d, data)
        s.t[n.lower()] = t

    def _fill(self, s, data):
        for m in data:
            k = m.get("Name").lower()
            if m.tag == "DataValueMember":
                t = m.get("DataType")
                s.f[k] = conv(t, float(m.get("Value")) if t == "REAL" else int(float(m.get("Value"))))
            elif m.tag == "ArrayMember":
                s.f[k] = self.new(m.get("DataType"), int(m.get("Dimensions")), _as_array(m))

    def _add_tag(self, scope, t):
        typ = t.get("DataType")
        if typ == "ALARM_DIGITAL":
            scope.f[t.get("Name").lower()] = Struct("ALARM_DIGITAL")
            scope.t[t.get("Name").lower()] = typ
            return
        d = int(t.get("Dimensions") or 0)
        data = t.find("Data")
        inner = data[0] if data is not None and len(data) else None
        scope.f[t.get("Name").lower()] = self.new(typ, d, inner)
        scope.t[t.get("Name").lower()] = typ

    # running ---------------------------------------------------------
    def run_routine(self, program, routine):
        p = self.programs[program]
        code = p["code"].get(routine)
        if code is None:
            code = p["code"][routine] = Compiler(self).block(parse(p["routines"][routine]))
        code(Env(self, [p["tags"], self.ctl_tags]))

    def call_aoi(self, name, inst, inouts):
        a = self.aoi[name.lower()]
        if a["code"] is None:
            a["code"] = Compiler(self).block(parse(a["src"]))
        io = [p for p in a["params"] if p[3] == "InOut"]
        if len(inouts) != len(io):
            raise LogixError(f"{a['name']}: {len(io)} InOut arguments expected, {len(inouts)} given")
        b = Struct("inout")
        for (n, t, d, *_), v in zip(io, inouts):
            b.f[n.lower()] = v
            b.t[n.lower()] = t
        inst.f["enablein"] = 1
        a["code"](Env(self, [b, inst]))
        inst.f["enableout"] = 1


def _as_array(m):
    a = ET.Element("Array")
    a.extend(list(m))
    return a


def atomic(t):
    return t in ("REAL", "BOOL", "INT", "DINT", "SINT")


class Env:
    def __init__(self, model, scopes):
        self.m = model
        self.scopes = scopes

    def base(self, name):
        k = name.lower()
        for s in self.scopes:
            if k in s.f:
                return s, k
        raise LogixError("unknown tag " + name)


# ---------------------------------------------------------------- parser

_TOK = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/|\(\*.*?\*\))
  | (?P<real>\d+\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)
  | (?P<int>\d+)
  | (?P<id>[A-Za-z_]\w*)
  | (?P<op>:=|<=|>=|<>|\*\*|[-+*/=<>()\[\],;:.])
""", re.X | re.S)

KEYWORDS = {"IF", "THEN", "ELSIF", "ELSE", "END_IF", "CASE", "OF", "END_CASE", "FOR", "TO", "BY", "DO",
            "END_FOR", "AND", "OR", "XOR", "NOT", "MOD", "WHILE", "REPEAT", "RETURN", "EXIT"}


def tokenize(src):
    out, pos = [], 0
    while pos < len(src):
        m = _TOK.match(src, pos)
        if not m:
            raise LogixError(f"cannot read {src[pos:pos + 20]!r}")
        pos = m.end()
        k = m.lastgroup
        if k in ("ws", "comment"):
            continue
        v = m.group()
        if k == "id" and v.upper() in KEYWORDS:
            out.append(("kw", v.upper()))
        else:
            out.append((k, v))
    out.append(("eof", ""))
    return out


class Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self, k=0):
        return self.t[self.i + k]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, v):
        tok = self.next()
        if tok[1].upper() != v:
            raise LogixError(f"expected {v}, found {tok[1]!r}")

    def at(self, *vals):
        return self.peek()[1].upper() in vals and self.peek()[0] in ("kw", "op")

    def stmts(self, *end):
        out = []
        while not (self.peek()[0] == "eof" or (self.peek()[0] == "kw" and self.peek()[1] in end)):
            if self.at(";"):
                self.next()
                continue
            out.append(self.stmt())
        return out

    def stmt(self):
        tok = self.peek()
        if tok == ("kw", "IF"):
            self.next()
            arms = []
            cond = self.expr()
            self.expect("THEN")
            arms.append((cond, self.stmts("ELSIF", "ELSE", "END_IF")))
            other = []
            while True:
                k = self.next()[1]
                if k == "ELSIF":
                    c = self.expr()
                    self.expect("THEN")
                    arms.append((c, self.stmts("ELSIF", "ELSE", "END_IF")))
                elif k == "ELSE":
                    other = self.stmts("END_IF")
                else:
                    break
            self.expect(";")
            return ("if", arms, other)
        if tok == ("kw", "CASE"):
            self.next()
            sel = self.expr()
            self.expect("OF")
            arms, other = [], []
            while True:
                if self.at("ELSE"):
                    self.next()
                    other = self.stmts("END_CASE")
                    self.expect("END_CASE")
                    break
                if self.at("END_CASE"):
                    self.next()
                    break
                labels = [self.label()]
                while self.at(","):
                    self.next()
                    labels.append(self.label())
                self.expect(":")
                arms.append((labels, self.case_body()))
            self.expect(";")
            return ("case", sel, arms, other)
        if tok == ("kw", "FOR"):
            self.next()
            var = self.lvalue()
            self.expect(":=")
            a = self.expr()
            self.expect("TO")
            b = self.expr()
            step = ("num", 1)
            if self.at("BY"):
                self.next()
                step = self.expr()
            self.expect("DO")
            body = self.stmts("END_FOR")
            self.expect("END_FOR")
            self.expect(";")
            return ("for", var, a, b, step, body)
        if tok[0] == "id" and self.peek(1)[1] == "(":
            name = self.next()[1]
            self.next()
            args = []
            if not self.at(")"):
                args.append(self.arg())
                while self.at(","):
                    self.next()
                    args.append(self.arg())
            self.expect(")")
            self.expect(";")
            return ("call", name, args)
        if tok[0] == "kw":
            raise LogixError(f"statement {tok[1]} not supported")
        lv = self.lvalue()
        self.expect(":=")
        e = self.expr()
        self.expect(";")
        return ("set", lv, e)

    def arg(self):
        if self.at(","):
            return ("none",)
        return self.expr()

    def case_body(self):
        out = []
        while True:
            if self.at("ELSE", "END_CASE"):
                return out
            # a new label: integer (or list) followed by ':' / ','
            if self.peek()[0] in ("int",) or (self.at("-") and self.peek(1)[0] == "int"):
                j = 1 if self.peek()[0] == "int" else 2
                if self.peek(j)[1] in (":", ","):
                    return out
            if self.at(";"):
                self.next()
                continue
            out.append(self.stmt())

    def label(self):
        neg = False
        if self.at("-"):
            self.next()
            neg = True
        tok = self.next()
        if tok[0] != "int":
            raise LogixError("CASE label must be an integer")
        return -int(tok[1]) if neg else int(tok[1])

    def lvalue(self):
        tok = self.next()
        if tok[0] != "id":
            raise LogixError(f"name expected, found {tok[1]!r}")
        path = [("name", tok[1])]
        while self.at(".", "["):
            if self.next()[1] == ".":
                path.append(("member", self.next()[1]))
            else:
                path.append(("index", self.expr()))
                self.expect("]")
        return ("ref", path)

    PREC = [("OR",), ("XOR",), ("AND",), ("=", "<>"), ("<", ">", "<=", ">="), ("+", "-"), ("*", "/", "MOD")]

    def expr(self, level=0):
        if level == len(self.PREC):
            return self.unary()
        left = self.expr(level + 1)
        while self.at(*self.PREC[level]):
            op = self.next()[1].upper()
            left = ("bin", op, left, self.expr(level + 1))
        return left

    def unary(self):
        if self.at("NOT"):
            self.next()
            return ("not", self.unary())
        if self.at("-"):
            self.next()
            return ("neg", self.unary())
        if self.at("("):
            self.next()
            e = self.expr()
            self.expect(")")
            return e
        tok = self.peek()
        if tok[0] == "real":
            self.next()
            return ("num", np.float32(float(tok[1])))
        if tok[0] == "int":
            self.next()
            return ("num", int(tok[1]))
        if tok[0] == "id" and self.peek(1)[1] == "(":
            name = self.next()[1].upper()
            self.next()
            args = [self.expr()]
            while self.at(","):
                self.next()
                args.append(self.expr())
            self.expect(")")
            return ("fn", name, args)
        if tok[0] == "id":
            return self.lvalue()
        raise LogixError(f"unexpected {tok[1]!r}")


def parse(src):
    p = Parser(tokenize(src))
    out = p.stmts()
    if p.peek()[0] != "eof":
        raise LogixError(f"unexpected {p.peek()[1]!r}")
    return out


# ---------------------------------------------------------------- compiler to closures

def _arith(op, a, b):
    if is_real(a) or is_real(b):
        a, b = np.float32(a), np.float32(b)
        if op == "+":
            return np.float32(a + b)
        if op == "-":
            return np.float32(a - b)
        if op == "*":
            return np.float32(a * b)
        if op == "/":
            return np.float32(a / b)
        raise LogixError("MOD on REAL not supported")
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        q = abs(a) // abs(b)
        return q if (a >= 0) == (b >= 0) else -q
    if op == "MOD":
        return a - b * _arith("/", a, b)


_CMP = {"=": lambda a, b: a == b, "<>": lambda a, b: a != b, "<": lambda a, b: a < b,
        ">": lambda a, b: a > b, "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}


class Compiler:
    def __init__(self, model):
        self.m = model

    def block(self, stmts):
        fs = [self.stmt(s) for s in stmts]

        def run(env):
            for f in fs:
                f(env)
        return run

    def stmt(self, s):
        k = s[0]
        if k == "set":
            loc = self.loc(s[1])
            e = self.expr(s[2])

            def f(env):
                c, key, typ = loc(env)
                v = e(env)
                if typ is None:
                    raise LogixError("cannot assign a whole structure; use COP")
                c[key] = conv(typ, v)
            return f
        if k == "if":
            arms = [(self.expr(c), self.block(b)) for c, b in s[1]]
            other = self.block(s[2])

            def f(env):
                for c, b in arms:
                    if c(env):
                        b(env)
                        return
                other(env)
            return f
        if k == "case":
            sel = self.expr(s[1])
            table = {}
            for labels, body in s[2]:
                b = self.block(body)
                for lab in labels:
                    table[lab] = b
            other = self.block(s[3])

            def f(env):
                table.get(int(sel(env)), other)(env)
            return f
        if k == "for":
            loc = self.loc(s[1])
            a, b, st = self.expr(s[2]), self.expr(s[3]), self.expr(s[4])
            body = self.block(s[5])

            def f(env):
                c, key, typ = loc(env)
                i, hi, step = int(a(env)), int(b(env)), int(st(env))
                c[key] = conv(typ, i)
                while (step > 0 and c[key] <= hi) or (step < 0 and c[key] >= hi):
                    body(env)
                    c[key] = conv(typ, c[key] + step)
            return f
        if k == "call":
            name, args = s[1], s[2]
            up = name.upper()
            if up == "COP":
                src, dst, n = self.loc(args[0]), self.loc(args[1]), self.expr(args[2])

                def f(env):
                    sc, sk, _ = src(env)
                    dc, dk, _ = dst(env)
                    cnt = int(n(env))
                    if isinstance(sc[sk], Struct):
                        if cnt != 1:
                            raise LogixError("COP of a structure with length other than 1")
                        tgt = dc[dk]
                        tgt.f = copy.deepcopy(sc[sk]).f
                        return
                    if not isinstance(sc, list) or not isinstance(dc, list):
                        raise LogixError("COP needs array elements or structures")
                    if sk + cnt > len(sc) or dk + cnt > len(dc):
                        raise LogixError("COP beyond the end of an array")
                    for j in range(cnt):
                        dc[dk + j] = conv(dc.t, sc[sk + j])
                return f
            if up == "ALMD":
                raise LogixError("ALMD is not interpreted (the bench does not use it)")
            if name.lower() not in self.m.aoi:
                raise LogixError("unknown instruction " + name)
            inst = self.loc(args[0])
            ios = [self.loc(a) for a in args[1:]]

            def f(env):
                c, key, _ = inst(env)
                vals = []
                for io in ios:
                    cc, kk, _t = io(env)
                    v = cc[kk]
                    if not isinstance(v, (Arr, Struct)):
                        raise LogixError("InOut argument must be an array or a structure here")
                    vals.append(v)
                env.m.call_aoi(name, c[key], vals)
            return f
        raise LogixError("statement not supported: " + k)

    def loc(self, ref):
        """Compile a reference into env -> (container, key, element type or None)."""
        if ref[0] != "ref":
            raise LogixError("not a tag reference")
        path = ref[1]
        steps = []
        for kind, v in path[1:]:
            steps.append((kind, self.expr(v) if kind == "index" else v.lower()))
        base = path[0][1]

        def f(env):
            scope, key = env.base(base)
            c, k, typ = scope.f, key, scope.t.get(key)
            for kind, v in steps:
                cur = c[k]
                if kind == "member":
                    if not isinstance(cur, Struct) or v not in cur.f:
                        raise LogixError(f"no member {v} in {base}")
                    c, k, typ = cur.f, v, cur.t.get(v)
                else:
                    i = int(v(env))
                    if not isinstance(cur, list) or not 0 <= i < len(cur):
                        raise LogixError(f"index {i} out of range in {base}")
                    c, k, typ = cur, i, cur.t
            if typ is not None and not atomic(typ):
                typ = None
            return c, k, typ
        return f

    def expr(self, e):
        k = e[0]
        if k == "num":
            v = e[1]
            return lambda env: v
        if k == "ref":
            loc = self.loc(e)

            def f(env):
                c, key, _ = loc(env)
                return c[key]
            return f
        if k == "not":
            a = self.expr(e[1])
            return lambda env: 0 if a(env) else 1
        if k == "neg":
            a = self.expr(e[1])
            return lambda env: _arith("-", 0 if not is_real(a(env)) else np.float32(0), a(env))
        if k == "bin":
            op, a, b = e[1], self.expr(e[2]), self.expr(e[3])
            if op in _CMP:
                cmp = _CMP[op]

                def f(env):
                    x, y = a(env), b(env)
                    if is_real(x) or is_real(y):
                        x, y = np.float32(x), np.float32(y)
                    return 1 if cmp(x, y) else 0
                return f
            if op == "AND":
                return lambda env: int(a(env)) & int(b(env))
            if op == "OR":
                return lambda env: int(a(env)) | int(b(env))
            if op == "XOR":
                return lambda env: int(a(env)) ^ int(b(env))
            return lambda env: _arith(op, a(env), b(env))
        if k == "fn":
            name, args = e[1], [self.expr(x) for x in e[2]]
            if name == "ABS" and len(args) == 1:
                return lambda env: np.float32(abs(args[0](env))) if is_real(args[0](env)) else abs(args[0](env))
            raise LogixError("function not supported: " + name)
        raise LogixError("expression not supported: " + k)


# ---------------------------------------------------------------- the bench

def run_bench(path: Path, max_calls: int = 2000) -> dict:
    m = Model(path)
    calls = 0
    tr = m.ctl_tags.f
    while not tr["tr_done"] and calls < max_calls:
        m.run_routine("BenchProgram", "Bench")
        calls += 1
    st = m.programs["BenchProgram"]["tags"].f["station"].f
    return {
        "Done": bool(tr["tr_done"]), "AllPassed": bool(tr["tr_allpassed"]),
        "CasesTotal": tr["tr_casestotal"], "CasesRun": tr["tr_casesrun"],
        "CasesPassed": tr["tr_casespassed"], "CasesFailed": tr["tr_casesfailed"],
        "FirstFailedCase": tr["tr_firstfailedcase"], "FirstFailedCheck": tr["tr_firstfailedcheck"],
        "MaxFeatError": float(tr["tr_maxfeaterror"]), "BenchCalls": int(tr["tr_benchcalls"]),
        "CasePass": [int(x) for x in tr["tr_casepass"][1:21]],
        "CaseCheck": [int(x) for x in tr["tr_casecheck"][1:21]],
        "CaseNok": [int(x) for x in tr["tr_casenok"][1:21]],
        "Station": {k: int(st[k.lower()]) for k in ("State", "CntTotal", "CntOk", "CntNok", "CntRejectConfirmed")},
        "calls_run": calls,
    }


if __name__ == "__main__":
    import json
    import sys
    root = Path(__file__).resolve().parents[1]
    r = run_bench(root / "logix" / "StationPort.L5X")
    print(json.dumps(r, indent=1))
    sys.exit(0 if r["AllPassed"] else 1)
