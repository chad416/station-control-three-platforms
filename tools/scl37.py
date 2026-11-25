"""Run the SCL source files of this repo in Python (for tests and CI).

This is a small translator for the subset of Siemens SCL used in plc/*.scl.
It is NOT a general SCL compiler.  It parses each FUNCTION_BLOCK, turns it
into a Python class and runs it with S7 data types:

* Real  -> numpy.float32 (IEEE single, rounded after every operation)
* Int   -> 16-bit, DInt -> 32-bit (wrap-around on assignment)
* Bool, Array[lo..hi] of <elementary>, multi-instances of other FBs

Besides FUNCTION_BLOCKs it reads global DATA_BLOCKs (elementary variables and arrays, start values
in the BEGIN section), instance DATA_BLOCKs and ORGANIZATION_BLOCKs, so that a small test program
with its data runs as a whole (load_program).  Variables are addressed as #local, "DB".member,
#instance.member (inputs, outputs, nested instances) and [index].

Supported statements: assignment, IF/ELSIF/ELSE, CASE ... OF (integer labels and lists),
FOR ... TO ... [BY] ... DO, REGION, RETURN, FB multi-instance calls, whole-array copy
(#a := #b; same element type and bounds).  VAR CONSTANT is read-only.  Expressions: arithmetic, comparison,
AND/OR/XOR/NOT, MOD, array index, member access, and the functions LIMIT, MIN,
MAX, ABS, SQRT, EXP, LN, INT_TO_REAL, DINT_TO_REAL, REAL_TO_DINT, INT_TO_DINT.

Operation counting (for the PLC cycle-time budget, dossier section 7):
- every Real +,-,*,/ is counted as "real";
- every Real comparison as "cmp";
- every EXP/LN/SQRT as "math";
- every assignment as "mov";
- every integer +,-,* and every loop pass as "int".
`OPS` holds the counts; reset it with `reset_ops()`.

Origin: copied from the door-handle-force-travel-test project (handletest/scl.py, same author, MIT),
which took it from the extruder-pressure-fill-estimator project,
then extended with CASE, VAR CONSTANT and the whole-array copy.

Anything else raises SclError, so an unsupported construct can never be
silently ignored.  The authority for the real PLC is the TIA Portal compiler;
this file only lets CI execute the same source text that goes into TIA.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class SclError(Exception):
    pass


# --------------------------------------------------------------------------
# lexer
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|\(\*.*?\*\)|/\*.*?\*/)
  | (?P<attr>\{[^}]*\})
  | (?P<real>\d+\.\d+(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)
  | (?P<int>\d+)
  | (?P<local>\#[A-Za-z_][A-Za-z0-9_]*)
  | (?P<qname>"[^"]+")
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>:=|=>|<>|<=|>=|\.\.|[-+*/=<>();:,\[\].])
""", re.VERBOSE | re.DOTALL)

_HEADER_RE = re.compile(r"^\s*(TITLE\s*=|AUTHOR\s*:|VERSION\s*:|FAMILY\s*:)[^\n]*$",
                        re.IGNORECASE | re.MULTILINE)


@dataclass
class Tok:
    kind: str
    text: str
    line: int

    @property
    def up(self) -> str:
        return self.text.upper()


def tokenize(src: str) -> list[Tok]:
    src = _HEADER_RE.sub("", src)
    toks: list[Tok] = []
    pos, line = 0, 1
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            raise SclError(f"line {line}: cannot read {src[pos:pos + 20]!r}")
        kind = m.lastgroup
        text = m.group()
        if kind not in ("ws", "comment", "attr"):
            if kind == "local":
                text = text[1:]
            elif kind == "qname":
                text = text[1:-1]
            toks.append(Tok(kind, text, line))
        line += text.count("\n") if kind in ("ws", "comment", "attr") else 0
        pos = m.end()
    toks.append(Tok("eof", "", line))
    return toks


# --------------------------------------------------------------------------
# parser -> Python source
# --------------------------------------------------------------------------

ELEMENTARY = {"REAL", "INT", "DINT", "BOOL"}

#: Names TIA Portal rejects as variable names (data types and keywords).  Found the
#: hard way: an output called "Time" passed this translator but not the TIA compiler.
RESERVED = {
    "TIME", "LTIME", "S5TIME", "DATE", "TOD", "LTOD", "TIME_OF_DAY", "DT", "LDT", "DTL",
    "DATE_AND_TIME", "STRING", "WSTRING", "CHAR", "WCHAR", "BYTE", "WORD", "DWORD", "LWORD",
    "BOOL", "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT", "REAL", "LREAL",
    "ARRAY", "STRUCT", "VOID", "ANY", "POINTER", "VARIANT", "IF", "THEN", "ELSIF", "ELSE",
    "END_IF", "CASE", "OF", "END_CASE", "FOR", "TO", "BY", "DO", "END_FOR", "WHILE",
    "END_WHILE", "REPEAT", "UNTIL", "END_REPEAT", "EXIT", "CONTINUE", "RETURN", "GOTO",
    "AND", "OR", "XOR", "NOT", "MOD", "TRUE", "FALSE", "VAR", "BEGIN", "REGION", "END_REGION",
}


@dataclass
class VarDecl:
    name: str
    section: str  # VAR_INPUT / VAR_OUTPUT / VAR / VAR_TEMP / VAR_IN_OUT
    type: str  # REAL / INT / DINT / BOOL / ARRAY / FB:<name>
    elem: str = ""
    lo: int = 0
    hi: int = 0
    init: object = None


class Parser:
    def __init__(self, toks: list[Tok], fb_types: dict[str, dict[str, VarDecl]]):
        self.t = toks
        self.i = 0
        self.fb_types = fb_types  # name -> its variable table (for member types)
        self.db_types: dict[str, dict[str, VarDecl]] = {}  # global data blocks
        self.inst_dbs: dict[str, str] = {}  # instance data block -> FB name
        self.vars: dict[str, VarDecl] = {}
        self.lines: list[str] = []
        self.loop_id = 0

    # -- token helpers ------------------------------------------------------
    def peek(self, k: int = 0) -> Tok:
        return self.t[self.i + k]

    def next(self) -> Tok:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def accept(self, text: str) -> bool:
        if self.peek().up == text.upper() and self.peek().kind in ("ident", "op"):
            self.i += 1
            return True
        return False

    def expect(self, text: str) -> Tok:
        tok = self.next()
        if tok.up != text.upper():
            raise SclError(f"line {tok.line}: expected {text!r}, got {tok.text!r}")
        return tok

    # -- declarations -------------------------------------------------------
    def parse_type(self) -> tuple[str, str, int, int]:
        tok = self.next()
        if tok.kind == "qname":
            if tok.text not in self.fb_types:
                raise SclError(f"line {tok.line}: unknown FB type {tok.text!r}")
            return "FB:" + tok.text, "", 0, 0
        if tok.up == "ARRAY":
            self.expect("[")
            lo = self.parse_int_const()
            self.expect("..")
            hi = self.parse_int_const()
            self.expect("]")
            self.expect("OF")
            elem = self.next().up
            if elem not in ELEMENTARY:
                raise SclError(f"line {tok.line}: unsupported array element {elem}")
            return "ARRAY", elem, lo, hi
        if tok.up not in ELEMENTARY:
            raise SclError(f"line {tok.line}: unsupported type {tok.text!r}")
        return tok.up, "", 0, 0

    def parse_int_const(self) -> int:
        sign = -1 if self.accept("-") else 1
        tok = self.next()
        if tok.kind != "int":
            raise SclError(f"line {tok.line}: expected integer, got {tok.text!r}")
        return sign * int(tok.text)

    def parse_literal(self) -> object:
        sign = -1 if self.accept("-") else 1
        tok = self.next()
        if tok.kind == "real":
            return sign * float(tok.text)
        if tok.kind == "int":
            return sign * int(tok.text)
        if tok.up in ("TRUE", "FALSE"):
            return tok.up == "TRUE"
        raise SclError(f"line {tok.line}: unsupported initial value {tok.text!r}")

    def parse_var_sections(self) -> None:
        while self.peek().up.startswith("VAR"):
            section = self.next().up
            if self.accept("CONSTANT"):
                section = "VAR CONSTANT"
            while not self.accept("END_VAR"):
                name_tok = self.next()
                if name_tok.kind != "ident":
                    raise SclError(f"line {name_tok.line}: bad variable name {name_tok.text!r}")
                if name_tok.up in RESERVED:
                    raise SclError(f"line {name_tok.line}: {name_tok.text!r} is a reserved word in SCL")
                self.expect(":")
                typ, elem, lo, hi = self.parse_type()
                init = None
                if self.accept(":="):
                    init = self.parse_literal()
                self.expect(";")
                self.vars[name_tok.text] = VarDecl(name_tok.text, section, typ, elem, lo, hi, init)

    # -- types of expressions -------------------------------------------------
    @staticmethod
    def num_type(*types: str) -> str:
        if "REAL" in types:
            return "REAL"
        if "DINT" in types:
            return "DINT"
        return "INT"

    # -- expressions: return (python_source, scl_type) -----------------------
    def expr(self) -> tuple[str, str]:
        return self.or_expr()

    def _binary(self, sub, ops: dict[str, str]) -> tuple[str, str]:
        left, lt = sub()
        while self.peek().up in ops and self.peek().kind in ("op", "ident"):
            op = self.next().up
            right, rt = sub()
            left, lt = self.combine(op, ops[op], left, lt, right, rt)
        return left, lt

    def combine(self, op: str, pyop: str, a: str, at: str, b: str, bt: str) -> tuple[str, str]:
        if op in ("AND", "OR", "XOR", "&"):
            if at != "BOOL" or bt != "BOOL":
                raise SclError(f"{op} on non-Bool operands is not supported")
            return f"({a} {pyop} {b})", "BOOL"
        if op in ("=", "<>", "<", ">", "<=", ">="):
            if "REAL" in (at, bt):
                return f"_cmp({a} {pyop} {b})", "BOOL"
            return f"({a} {pyop} {b})", "BOOL"
        t = self.num_type(at, bt)
        if op == "/" and t != "REAL":
            return f"_idiv({a}, {b})", t
        if op == "MOD":
            if t == "REAL":
                raise SclError("MOD on Real is not supported")
            return f"_imod({a}, {b})", t
        if t == "REAL":
            return f"_fop(_f32({a}) {pyop} _f32({b}))", "REAL"
        return f"_iop({a} {pyop} {b})", t

    def or_expr(self):
        return self._binary(self.xor_expr, {"OR": "or"})

    def xor_expr(self):
        return self._binary(self.and_expr, {"XOR": "!="})

    def and_expr(self):
        return self._binary(self.eq_expr, {"AND": "and", "&": "and"})

    def eq_expr(self):
        return self._binary(self.rel_expr, {"=": "==", "<>": "!="})

    def rel_expr(self):
        return self._binary(self.add_expr, {"<": "<", ">": ">", "<=": "<=", ">=": ">="})

    def add_expr(self):
        return self._binary(self.mul_expr, {"+": "+", "-": "-"})

    def mul_expr(self):
        return self._binary(self.unary, {"*": "*", "/": "/", "MOD": "%"})

    def unary(self) -> tuple[str, str]:
        if self.accept("-"):
            s, t = self.unary()
            return f"(-{s})", t
        if self.accept("+"):
            return self.unary()
        if self.accept("NOT"):
            s, t = self.unary()
            if t != "BOOL":
                raise SclError("NOT on non-Bool is not supported")
            return f"(not {s})", "BOOL"
        return self.primary()

    def primary(self) -> tuple[str, str]:
        tok = self.next()
        if tok.kind == "real":
            return f"_f32({float(tok.text)!r})", "REAL"
        if tok.kind == "int":
            return tok.text, "INT"
        if tok.up in ("TRUE", "FALSE"):
            return ("True" if tok.up == "TRUE" else "False"), "BOOL"
        if tok.text == "(":
            s, t = self.expr()
            self.expect(")")
            return f"({s})", t
        if tok.kind in ("local", "qname"):
            return self.access(tok)
        if tok.kind == "ident" and self.peek().text == "(":
            return self.function_call(tok)
        raise SclError(f"line {tok.line}: unexpected {tok.text!r} in expression")

    def designator(self, tok: Tok) -> tuple[str, VarDecl, bool, bool]:
        """#local, "GlobalDB".member or "InstanceDB".member, then .member (FB instances) and [index].

        Returns (python source, declaration of the variable, indexed, writable). With `indexed` the
        source addresses one element of the array declaration. From outside an instance only its
        inputs and outputs (and the instances inside it) can be addressed; only inputs can be written.
        """
        if tok.kind == "local":
            d = self.vars.get(tok.text)
            if d is None:
                raise SclError(f"line {tok.line}: undeclared #{tok.text}")
            src = f"self.{d.name}"
            writable = d.section not in ("VAR_INPUT", "VAR CONSTANT")
        else:
            self.expect(".")
            member = self.next().text
            if tok.text in self.db_types:
                d = self.db_types[tok.text].get(member)
                writable = True
            elif tok.text in self.inst_dbs:
                d = self.fb_types[self.inst_dbs[tok.text]].get(member)
                if d is not None and not (d.section in ("VAR_INPUT", "VAR_OUTPUT") or d.type.startswith("FB:")):
                    d = None
                writable = d is not None and d.section == "VAR_INPUT"
            else:
                raise SclError(f"line {tok.line}: unknown data block {tok.text!r}")
            if d is None:
                raise SclError(f"line {tok.line}: {tok.text!r} has no accessible member {member!r}")
            src = f"_DB[{tok.text!r}].{d.name}"
        while self.peek().text == "." and d.type.startswith("FB:"):
            self.next()
            member = self.next().text
            m = self.fb_types[d.type[3:]].get(member)
            if m is None or not (m.section in ("VAR_INPUT", "VAR_OUTPUT") or m.type.startswith("FB:")):
                raise SclError(f"line {tok.line}: {d.name}.{member} is not an input, an output or an instance")
            src, d, writable = f"{src}.{m.name}", m, m.section == "VAR_INPUT"
        indexed = False
        if self.peek().text == "[":
            if d.type != "ARRAY":
                raise SclError(f"line {tok.line}: {d.name} is not an array")
            self.next()
            idx, it = self.expr()
            self.expect("]")
            if it not in ("INT", "DINT"):
                raise SclError(f"line {tok.line}: array index must be integer")
            src, indexed = f"{src}[_ix({idx}, {d.lo}, {d.hi})]", True
        elif self.peek().text == ".":
            raise SclError(f"line {tok.line}: {d.name} has no members")
        return src, d, indexed, writable

    def access(self, tok: Tok) -> tuple[str, str]:
        src, d, indexed, _ = self.designator(tok)
        return src, (d.elem if indexed else d.type)

    def function_call(self, tok: Tok) -> tuple[str, str]:
        name = tok.up
        self.expect("(")
        args: dict[str, tuple[str, str]] = {}
        pos: list[tuple[str, str]] = []
        while not self.accept(")"):
            if self.peek().kind == "ident" and self.peek(1).text == ":=":
                key = self.next().up
                self.next()
                args[key] = self.expr()
            else:
                pos.append(self.expr())
            self.accept(",")
        if name == "LIMIT":
            mn, inp, mx = (args["MN"], args["IN"], args["MX"]) if args else pos
            t = self.num_type(mn[1], inp[1], mx[1])
            cast = "_f32" if t == "REAL" else ""
            return f"_limit({cast}({mn[0]}), {cast}({inp[0]}), {cast}({mx[0]}))", t
        if name in ("MIN", "MAX"):
            vals = [args[k] for k in sorted(args)] if args else pos
            t = self.num_type(*(v[1] for v in vals))
            cast = "_f32" if t == "REAL" else ""
            inner = ", ".join(f"{cast}({v[0]})" for v in vals)
            return f"{name.lower()}({inner})", t
        one = (args.get("IN") or pos[0]) if (args or pos) else None
        if one is None:
            raise SclError(f"line {tok.line}: {name} needs an argument")
        if name == "ABS":
            return f"abs({one[0]})", one[1]
        if name == "SQRT":
            return f"_fn(np.sqrt(_f32({one[0]})))", "REAL"
        if name == "EXP":
            return f"_fn(np.exp(_f32({one[0]})))", "REAL"
        if name == "LN":
            return f"_fn(np.log(_f32({one[0]})))", "REAL"
        if name in ("INT_TO_REAL", "DINT_TO_REAL"):
            return f"_f32({one[0]})", "REAL"
        if name == "INT_TO_DINT":
            return f"int({one[0]})", "DINT"
        if name == "REAL_TO_DINT":
            return f"_round_even({one[0]})", "DINT"
        raise SclError(f"line {tok.line}: function {name} is not supported")

    # -- statements -----------------------------------------------------------
    def emit(self, depth: int, text: str) -> None:
        self.lines.append("    " * depth + text)

    def statements(self, depth: int, stop: tuple[str, ...]) -> None:
        start = len(self.lines)
        while self.peek().up not in stop:
            self.statement(depth)
        if len(self.lines) == start:
            self.emit(depth, "pass")

    def case_body(self, depth: int) -> None:
        """Statements of one CASE branch: up to the next label, ELSE or END_CASE."""
        start = len(self.lines)
        while True:
            t = self.peek()
            if t.up in ("ELSE", "END_CASE"):
                break
            if t.kind == "int" and self.peek(1).text in (":", ","):
                break
            if t.text == "-" and self.peek(1).kind == "int" and self.peek(2).text in (":", ","):
                break
            self.statement(depth)
        if len(self.lines) == start:
            self.emit(depth, "pass")

    def cast_for(self, typ: str, src: str) -> str:
        if typ == "REAL":
            return f"_f32({src})"
        if typ == "INT":
            return f"_wrap({src}, 16)"
        if typ == "DINT":
            return f"_wrap({src}, 32)"
        if typ == "BOOL":
            return f"bool({src})"
        raise SclError(f"cannot assign to type {typ}")

    def statement(self, depth: int) -> None:
        tok = self.peek()
        up = tok.up
        if tok.text == ";":
            self.next()
            return
        if up == "REGION":
            self.next()
            self.next()  # region name (single identifier)
            self.statements(depth, ("END_REGION",))
            self.expect("END_REGION")
            return
        if up == "IF":
            self.next()
            cond, ct = self.expr()
            if ct != "BOOL":
                raise SclError(f"line {tok.line}: IF condition is not Bool")
            self.expect("THEN")
            self.emit(depth, f"if {cond}:")
            self.statements(depth + 1, ("ELSIF", "ELSE", "END_IF"))
            while self.accept("ELSIF"):
                cond, _ = self.expr()
                self.expect("THEN")
                self.emit(depth, f"elif {cond}:")
                self.statements(depth + 1, ("ELSIF", "ELSE", "END_IF"))
            if self.accept("ELSE"):
                self.emit(depth, "else:")
                self.statements(depth + 1, ("END_IF",))
            self.expect("END_IF")
            self.expect(";")
            return
        if up == "CASE":
            self.next()
            sel, st = self.expr()
            if st not in ("INT", "DINT"):
                raise SclError(f"line {tok.line}: CASE selector must be integer")
            self.expect("OF")
            self.loop_id += 1
            selv = f"_sel{self.loop_id}"
            self.emit(depth, f"{selv} = {sel}")
            first = True
            while not self.accept("END_CASE"):
                if self.accept("ELSE"):
                    self.accept(":")
                    self.emit(depth, "else:" if not first else "if True:")
                    self.case_body(depth + 1)
                    continue
                labels = [str(self.parse_int_const())]
                while self.accept(","):
                    labels.append(str(self.parse_int_const()))
                self.expect(":")
                self.emit(depth, f"{'if' if first else 'elif'} {selv} in ({', '.join(labels)},):")
                first = False
                self.case_body(depth + 1)
            self.expect(";")
            return
        if up == "FOR":
            self.next()
            var = self.next()
            if var.kind != "local" or self.vars.get(var.text, VarDecl("", "", "")).type not in ("INT", "DINT"):
                raise SclError(f"line {var.line}: FOR needs an Int/DInt #variable")
            self.expect(":=")
            a, _ = self.expr()
            self.expect("TO")
            b, _ = self.expr()
            step = "1"
            if self.accept("BY"):
                step, _ = self.expr()
            self.expect("DO")
            self.loop_id += 1
            end, stp = f"_end{self.loop_id}", f"_stp{self.loop_id}"
            v = f"self.{var.text}"
            self.emit(depth, f"{v} = {a}; {end} = {b}; {stp} = {step}")
            self.emit(depth, f"while ({v} <= {end}) if {stp} > 0 else ({v} >= {end}):")
            self.statements(depth + 1, ("END_FOR",))
            self.emit(depth + 1, f"{v} = _iop({v} + {stp})")
            self.expect("END_FOR")
            self.expect(";")
            return
        if up == "RETURN":
            self.next()
            self.expect(";")
            self.emit(depth, "return")
            return
        if tok.kind in ("local", "qname"):
            self.next()
            if self.peek().text == "(":
                self.fb_call(tok, depth)
                return
            target, d, indexed, writable = self.designator(tok)
            if not writable:
                raise SclError(f"line {tok.line}: writing {d.name} ({d.section}) is not allowed here")
            self.expect(":=")
            if d.type == "ARRAY" and not indexed:
                # whole-array copy between two arrays of the same element type and bounds
                self.emit(depth, f"{target} = _mov({self.array_value(d)})")
                self.expect(";")
                return
            if d.type.startswith("FB:"):
                raise SclError(f"line {tok.line}: instance assignment not supported")
            val, _ = self.expr()
            self.expect(";")
            self.emit(depth, f"{target} = _mov({self.cast_for(d.elem if indexed else d.type, val)})")
            return
        raise SclError(f"line {tok.line}: unsupported statement starting with {tok.text!r}")

    def array_value(self, target: VarDecl) -> str:
        """Right-hand side of a whole-array copy: a designator of an array with the same shape."""
        tok = self.next()
        if tok.kind not in ("local", "qname"):
            raise SclError(f"line {tok.line}: array copy needs an array on the right-hand side")
        src, d, indexed, _ = self.designator(tok)
        if indexed or (d.type, d.elem, d.lo, d.hi) != ("ARRAY", target.elem, target.lo, target.hi):
            raise SclError(f"line {tok.line}: array copy needs two arrays of the same type and bounds")
        return f"list({src})"

    def fb_call(self, tok: Tok, depth: int) -> None:
        """#Instance(...) of a multi-instance, or "InstanceDB"(...)."""
        if tok.kind == "local":
            d = self.vars.get(tok.text)
            if d is None or not d.type.startswith("FB:"):
                raise SclError(f"line {tok.line}: #{tok.text} is not an FB instance")
            inst, fb = f"self.{d.name}", d.type[3:]
        elif tok.text in self.inst_dbs:
            inst, fb = f"_DB[{tok.text!r}]", self.inst_dbs[tok.text]
        else:
            raise SclError(f"line {tok.line}: {tok.text!r} is not an instance data block")
        fb_vars = self.fb_types[fb]
        self.expect("(")
        while not self.accept(")"):
            pname = self.next().text
            if pname not in fb_vars or fb_vars[pname].section != "VAR_INPUT":
                raise SclError(f"line {tok.line}: {pname} is not an input of {fb}")
            self.expect(":=")
            if fb_vars[pname].type == "ARRAY":
                self.emit(depth, f"{inst}.{pname} = {self.array_value(fb_vars[pname])}")
            else:
                val, _ = self.expr()
                self.emit(depth, f"{inst}.{pname} = {self.cast_for(fb_vars[pname].type, val)}")
            self.accept(",")
        self.expect(";")
        self.emit(depth, f"{inst}()")


# --------------------------------------------------------------------------
# runtime helpers used by the generated code
# --------------------------------------------------------------------------

def _f32(x) -> np.float32:
    return np.float32(x)


OPS = {"real": 0, "cmp": 0, "math": 0, "mov": 0, "int": 0}


def reset_ops() -> None:
    for k in OPS:
        OPS[k] = 0


def _fop(x):
    OPS["real"] += 1
    return np.float32(x)


def _fn(x):
    OPS["math"] += 1
    return np.float32(x)


def _cmp(x):
    OPS["cmp"] += 1
    return x


def _mov(x):
    OPS["mov"] += 1
    return x


def _iop(x):
    OPS["int"] += 1
    return x


def _wrap(x, bits: int) -> int:
    x = int(x)
    m = 1 << bits
    x &= m - 1
    return x - m if x >= m >> 1 else x


def _idiv(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("integer division by zero")
    q = abs(int(a)) // abs(int(b))
    return q if (a >= 0) == (b >= 0) else -q


def _imod(a: int, b: int) -> int:
    return int(a) - _idiv(a, b) * int(b)


def _limit(mn, x, mx):
    return mn if x < mn else (mx if x > mx else x)


def _ix(i: int, lo: int, hi: int) -> int:
    if not lo <= i <= hi:
        raise IndexError(f"array index {i} outside [{lo}..{hi}]")
    return i - lo


def _round_even(x) -> int:
    return int(np.rint(np.float32(x)))


_DEFAULT = {"REAL": "np.float32(0.0)", "INT": "0", "DINT": "0", "BOOL": "False"}


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

_BLOCKS = {"FUNCTION_BLOCK": "END_FUNCTION_BLOCK", "DATA_BLOCK": "END_DATA_BLOCK",
           "ORGANIZATION_BLOCK": "END_ORGANIZATION_BLOCK"}


def _block_spans(toks: list[Tok]) -> list[tuple[str, str, int, int]]:
    spans, i = [], 0
    while toks[i].kind != "eof":
        kind = toks[i].up
        if kind in _BLOCKS:
            name = toks[i + 1].text
            j = i
            while toks[j].up != _BLOCKS[kind]:
                if toks[j].kind == "eof":
                    raise SclError(f"{name}: missing {_BLOCKS[kind]}")
                j += 1
            spans.append((kind, name, i, j))
            i = j + 1
        elif kind in ("FUNCTION", "TYPE"):
            raise SclError(f"line {toks[i].line}: {toks[i].text} is not translated")
        else:
            raise SclError(f"line {toks[i].line}: unexpected {toks[i].text!r}")
    return spans


def _parse_data_block(toks: list[Tok], name: str):
    """Global DB: ("global", variables with their start values). Instance DB: ("instance", FB name)."""
    p = Parser(toks, {})
    p.expect("DATA_BLOCK")
    p.next()
    p.accept("NON_RETAIN")
    if p.peek().kind == "qname":
        fb = p.next().text
        p.expect("BEGIN")
        p.expect("END_DATA_BLOCK")
        return "instance", fb
    p.parse_var_sections()
    p.expect("BEGIN")
    while not p.accept("END_DATA_BLOCK"):          # start values: Name := literal;  Name[i] := literal;
        t = p.next()
        d = p.vars.get(t.text)
        if d is None:
            raise SclError(f"line {t.line}: {name} has no variable {t.text!r}")
        if p.accept("["):
            i = p.parse_int_const()
            p.expect("]")
            if d.type != "ARRAY" or not d.lo <= i <= d.hi:
                raise SclError(f"line {t.line}: {name}.{d.name}[{i}] does not exist")
            p.expect(":=")
            if not isinstance(d.init, dict):
                d.init = {}
            d.init[i] = p.parse_literal()
        else:
            if d.type == "ARRAY":
                raise SclError(f"line {t.line}: start value of the whole array {d.name} is not supported")
            p.expect(":=")
            d.init = p.parse_literal()
        p.expect(";")
    return "global", p.vars


def _py_value(typ: str, v: object) -> str:
    if typ == "REAL":
        return f"np.float32({float(v)!r})"
    if typ == "BOOL":
        return repr(bool(v))
    return repr(int(v))


def _data_block_source(name: str, variables: dict[str, VarDecl]) -> list[str]:
    cname = "DB_" + re.sub(r"\W", "_", name)
    out = [f"class {cname}:", f"    SCL_NAME = {name!r}", "    def __init__(self):"]
    for d in variables.values():
        if d.type == "ARRAY":
            start = d.init if isinstance(d.init, dict) else {}
            zero = {"REAL": 0.0, "BOOL": False}.get(d.elem, 0)
            vals = ", ".join(_py_value(d.elem, start.get(i, zero)) for i in range(d.lo, d.hi + 1))
            out.append(f"        self.{d.name} = [{vals}]")
        else:
            out.append(f"        self.{d.name} = {_py_value(d.type, d.init) if d.init is not None else _DEFAULT[d.type]}")
    if not variables:
        out.append("        pass")
    out += [f"_DB[{name!r}] = {cname}()", ""]
    return out


def translate(sources: list[str]) -> tuple[str, dict[str, dict[str, VarDecl]]]:
    """Translate SCL sources (any order) into one Python module source.

    The module fills three dictionaries: _FB (name -> class), _DB (name -> object: a global data block
    or the instance of an FB) and _OB (name -> callable organization block).
    """
    blocks: dict[str, list[tuple[str, list[Tok]]]] = {k: [] for k in _BLOCKS}
    for src in sources:
        toks = tokenize(src)
        for kind, name, a, b in _block_spans(toks):
            blocks[kind].append((name, toks[a:b + 1] + [Tok("eof", "", toks[b].line)]))
    fb_types: dict[str, dict[str, VarDecl]] = {}
    db_types: dict[str, dict[str, VarDecl]] = {}
    inst_dbs: dict[str, str] = {}
    code = ["import numpy as np",
            "from scl37 import _f32, _wrap, _idiv, _imod, _limit, _ix, _round_even, _fop, _fn, _cmp, _mov, _iop",
            ""]
    for name, toks in blocks["DATA_BLOCK"]:
        kind, content = _parse_data_block(toks, name)
        if kind == "instance":
            inst_dbs[name] = content
        else:
            db_types[name] = content
            code.extend(_data_block_source(name, content))
    pending = dict(blocks["FUNCTION_BLOCK"])
    while pending:  # a block can only be translated after the FBs it instantiates
        progressed = False
        for name, toks in list(pending.items()):
            p = Parser(toks, fb_types)
            p.db_types, p.inst_dbs = db_types, inst_dbs
            p.expect("FUNCTION_BLOCK")
            p.next()
            try:
                p.parse_var_sections()
            except SclError as e:
                if "unknown FB type" in str(e):
                    continue
                raise
            p.expect("BEGIN")
            p.statements(2, ("END_FUNCTION_BLOCK",))
            p.expect("END_FUNCTION_BLOCK")
            fb_types[name] = p.vars
            code.extend(_class_source(name, p))
            del pending[name]
            progressed = True
        if not progressed:
            raise SclError(f"cannot resolve FB types for: {', '.join(pending)}")
    for name, fb in inst_dbs.items():
        if fb not in fb_types:
            raise SclError(f"instance data block {name!r}: unknown FB {fb!r}")
        code += [f"_DB[{name!r}] = _FB[{fb!r}]()", ""]
    for name, toks in blocks["ORGANIZATION_BLOCK"]:
        p = Parser(toks, fb_types)
        p.db_types, p.inst_dbs = db_types, inst_dbs
        p.expect("ORGANIZATION_BLOCK")
        p.next()
        p.parse_var_sections()
        p.expect("BEGIN")
        p.statements(2, ("END_ORGANIZATION_BLOCK",))
        p.expect("END_ORGANIZATION_BLOCK")
        code.extend(_class_source(name, p, registry="_OB", prefix="OB_", instantiate=True))
    return "\n".join(code) + "\n", fb_types


def _class_source(name: str, p: Parser, registry: str = "_FB", prefix: str = "", instantiate: bool = False) -> list[str]:
    cname = prefix + re.sub(r"\W", "_", name)
    out = [f"class {cname}:", f"    SCL_NAME = {name!r}", "    def __init__(self):"]
    temps = []
    for d in p.vars.values():
        if d.type.startswith("FB:"):
            init = f"_FB[{d.type[3:]!r}]()"
        elif d.type == "ARRAY":
            init = f"[{_DEFAULT[d.elem]} for _ in range({d.hi - d.lo + 1})]"
        elif d.init is not None:
            init = _py_value(d.type, d.init)
        else:
            init = _DEFAULT[d.type]
        out.append(f"        self.{d.name} = {init}")
        if d.section == "VAR_TEMP":
            temps.append((d, init))
    if not p.vars:
        out.append("        pass")
    out.append("    def __call__(self):")
    for d, init in temps:  # temp data is re-initialised on every call
        out.append(f"        self.{d.name} = {init}")
    out.extend(p.lines)
    out.append(f"{registry}[{name!r}] = {cname}{'()' if instantiate else ''}")
    out.append("")
    return out


@dataclass
class Program:
    """A translated set of sources: FB classes, data block objects, callable organization blocks."""
    fb: dict
    db: dict
    ob: dict


def load_program(paths: list[str | Path]) -> Program:
    """Translate and load SCL files with data blocks and organization blocks. Every call gives a
    fresh set of data blocks (start values as in the sources)."""
    sources = [Path(x).read_text(encoding="utf-8-sig") for x in paths]
    code, _ = translate(sources)
    namespace: dict[str, object] = {"_FB": {}, "_DB": {}, "_OB": {}}
    exec(compile(code, "<scl>", "exec"), namespace)
    return Program(dict(namespace["_FB"]), dict(namespace["_DB"]), dict(namespace["_OB"]))  # type: ignore[arg-type]


def load(paths: list[str | Path]) -> dict[str, type]:
    """Translate and load SCL files; returns {FB name: Python class}."""
    return load_program(paths).fb


def generated_source(paths: list[str | Path]) -> str:
    return translate([Path(x).read_text(encoding="utf-8") for x in paths])[0]


__all__ = ["SclError", "load", "load_program", "Program", "translate", "generated_source", "math", "OPS", "reset_ops"]
