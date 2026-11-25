# -*- coding: utf-8 -*-
"""Build the station blocks and the test bench in CODESYS V3.5 and run the bench in simulation.

Runs inside the CODESYS script engine (IronPython 2.7), without a window:

    CODESYS.exe --profile="CODESYS V3.5 SP22 Patch 1" --noUI --runscript=codesys\scripts\build_and_run.py

(codesys/scripts/run_codesys.ps1 does exactly that.)

Steps
  1. copy the "Standard" project template of the installation to codesys/build/ and switch its
     device to "CODESYS Control Win V3 x64" 3.5.22.10
  2. replace PLC_PRG and add the POUs and global variable lists from codesys/src/*.st
     (a file holds the declaration, the line (* @IMPLEMENTATION *), then the body)
  3. build; every message of the build is written to results/codesys_build.txt
  4. export the POUs as PLCopen XML to codesys/plcopen/
  5. if the build has no errors: simulation mode on, log in, start, poll GVL_TestResult.Done,
     read every result variable, log out; results/codesys_bench.json
"""
from __future__ import print_function
import io
import json
import os
import shutil
import sys
import time

from scriptengine import *  # noqa: F401,F403  (projects, online, system, PouType ... in the engine)

HERE = os.path.dirname(os.path.abspath(__file__))
CDS = os.path.dirname(HERE)
ROOT = os.path.dirname(CDS)
SRC = os.path.join(CDS, "src")
BUILD = os.path.join(CDS, "build")
RESULTS = os.path.join(ROOT, "results")
TEMPLATE = r"C:\Program Files\CODESYS 3.5.22.10\CODESYS\Templates\Standard.project"
DEVICE = (4096, "0000 0004", "3.5.22.10")   # CODESYS Control Win V3 x64

ORDER = [  # called blocks before their callers
    ("ST_EvalRecipe", "dut"), ("GVL_TestData", "gvl"), ("GVL_TestResult", "gvl"),
    ("FB_CurveEval", "fb"), ("FB_HandleStation", "fb"),
    ("FB_TestPlant", "fb"), ("FB_TestBench", "fb"),
    ("PLC_PRG", "prg"),
]
MARK = "(* @IMPLEMENTATION *)"

if not os.path.isdir(BUILD):
    os.makedirs(BUILD)
LOG = io.open(os.path.join(RESULTS, "codesys_build.txt"), "w", encoding="utf-8")


def log(*a):
    s = u" ".join(u"%s" % x for x in a)
    LOG.write(s + u"\n")
    LOG.flush()


def read_src(name):
    with io.open(os.path.join(SRC, name + ".st"), encoding="utf-8") as f:
        text = f.read()
    if MARK in text:
        decl, impl = text.split(MARK, 1)
        impl = impl.replace("END_FUNCTION_BLOCK", "").replace("END_PROGRAM", "")
        return decl.rstrip() + u"\n", impl.strip("\n") + u"\n"
    return text, None


def find(parent, name):
    for c in parent.get_children(False):
        if c.get_name() == name:
            return c
    return None


def all_messages():
    out = []
    for cat in system.get_message_categories():
        try:
            desc = system.get_message_category_description(cat)
        except Exception:
            desc = str(cat)
        for m in system.get_message_objects(cat):
            out.append((desc, m))
    return out


def sev(m):
    return str(m.severity)


log(u"CODESYS %s, script engine, no user interface: ui_present=%s" % ("V3.5 SP22 Patch 1", system.ui_present))
log(u"date %s" % time.strftime("%Y-%m-%d %H:%M"))

path = os.path.join(BUILD, "station_cds.project")
if os.path.exists(path):
    os.remove(path)
shutil.copyfile(os.path.normpath(TEMPLATE), path)
proj = projects.open(path)

dev = None
for o in proj.get_children(False):
    try:
        if o.is_device:
            dev = o
    except Exception:
        pass
dev.update(DEVICE[0], DEVICE[1], DEVICE[2])
dev.rename("Station_PLC")
log(u"device %s" % (dev.get_device_identification(),))

app = proj.active_application
# libraries of the template that the device update did not resolve are removed and the current
# Standard library is added (the station code uses no library function)
libman = None
for c in app.get_children(False):
    if c.get_name() == "Library Manager":
        libman = c
for lib in list(libman.get_libraries()):
    log(u"library in template: %s" % lib)
try:
    libman.add_library("Standard, * (System)")
except Exception as e:
    log(u"add Standard: %s" % e)

old = find(app, "PLC_PRG")
if old is not None:
    old.remove()
for name, kind in ORDER:
    decl, impl = read_src(name)
    if kind == "gvl":
        obj = app.create_gvl(name)
        obj.textual_declaration.replace(decl)
    elif kind == "dut":
        obj = app.create_dut(name)
        obj.textual_declaration.replace(decl)
    else:
        if kind == "fb":
            obj = app.create_pou(name, PouType.FunctionBlock)
        else:
            obj = app.create_pou(name, PouType.Program)
        obj.textual_declaration.replace(decl)
        obj.textual_implementation.replace(impl)
    log(u"added %s (%s)" % (name, kind))

# the template's task calls PLC_PRG; keep it and set the interval
tc = find(app, "Taskkonfiguration") or find(app, "Task Configuration")
task = None
for c in tc.get_children(False):
    task = c
try:
    task.interval = "t#10ms"
    log(u"task %s interval %s" % (task.get_name(), task.interval))
except Exception as e:
    log(u"task interval not set: %s" % e)

for cat in system.get_message_categories():
    system.clear_messages(cat)
app.rebuild()
errors = warnings = 0
log(u"--- build messages ---")
for desc, m in all_messages():
    s = sev(m)
    if "Error" in s or "Fatal" in s:
        errors += 1
    elif "Warning" in s:
        warnings += 1
    try:
        obj = m.object.get_name() if m.object is not None else ""
    except Exception:
        obj = ""
    log(u"%s | %s | %s%s | %s | %s" % (desc, s, m.prefix, m.number, obj, m.text))
log(u"BUILD errors=%d warnings=%d" % (errors, warnings))
proj.save()

# PLCopen XML of the station blocks and of the bench

for n, _ in ORDER:
    o = find(app, n)
    proj.export_xml([o], path=os.path.join(CDS, "plcopen", n + ".xml"), recursive=True)

log(u"PLCopen XML exported to codesys/plcopen/")

result = {"build": {"errors": errors, "warnings": warnings}}
if errors == 0:
    dev.set_simulation_mode(True)
    log(u"simulation mode %s" % dev.get_simulation_mode())
    onl = online.create_online_application(app)
    onl.login(OnlineChangeOption.Never, True)
    onl.start()
    log(u"logged in, state %s" % onl.application_state)
    t0 = time.time()
    done = False
    while time.time() - t0 < 120:
        system.delay(500)
        v = onl.read_value("GVL_TestResult.Done")
        if str(v).upper() == "TRUE":
            done = True
            break
    log(u"Done=%s after %.1f s" % (done, time.time() - t0))
    names = ["Done", "AllPassed", "CasesTotal", "CasesRun", "CasesPassed", "CasesFailed",
             "FirstFailedCase", "FirstFailedCheck", "MaxFeatError", "BenchCalls"]
    bench = {}
    for n in names:
        bench[n] = str(onl.read_value("GVL_TestResult." + n))
        log(u"GVL_TestResult.%s = %s" % (n, bench[n]))
    cases = []
    for i in range(1, 21):
        c = {
            "case": i,
            "pass": str(onl.read_value("GVL_TestResult.CasePass[%d]" % i)),
            "check": str(onl.read_value("GVL_TestResult.CaseCheck[%d]" % i)),
            "nok": str(onl.read_value("GVL_TestResult.CaseNok[%d]" % i)),
        }
        cases.append(c)
        log(u"case %(case)2d pass=%(pass)s check=%(check)s nok=%(nok)s" % c)
    # the station block itself, as an operator screen would read it
    for n in ["State", "Verdict", "NokCode", "CntTotal", "CntOk", "CntNok", "CntRejectConfirmed",
              "RigCheckRequired", "Locked"]:
        log(u"PLC_PRG.Bench.Station.%s = %s" % (n, onl.read_value("PLC_PRG.Bench.Station." + n)))
    result["bench"] = bench
    result["cases"] = cases
    onl.stop()
    onl.logout()
    log(u"logged out")

with io.open(os.path.join(RESULTS, "codesys_bench.json"), "w", encoding="utf-8") as f:
    f.write(unicode(json.dumps(result, indent=1)))
proj.save()
proj.close()
LOG.close()
