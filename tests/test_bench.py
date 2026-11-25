"""Checks that run without any vendor tool (CI).

1. The Siemens SCL sources of the bench (siemens/scl) run through the SCL translator of the
   door-handle project (tools/scl37.py, float32 arithmetic): 20 of 20 cases must pass.
2. The CODESYS test data list is exactly what tools/testdata.py makes from the Siemens data block.
3. The CODESYS run record (results/codesys_bench.json, written by the CODESYS script engine on the
   development PC) says 0 build errors and 20 of 20 cases. This only checks the record; the run
   itself needs CODESYS and cannot happen in CI.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import scl37  # noqa: E402
import testdata  # noqa: E402

SCL = ROOT / "siemens" / "scl"
SOURCES = [SCL / n for n in ("FB_CurveEval.scl", "FB_HandleStation.scl", "test/DB_TestData.scl",
                             "test/DB_TestResult.scl", "test/FB_TestPlant.scl", "test/FB_TestBench.scl",
                             "test/OB_Main.scl")]
EXPECTED_NOK = [0, 0, 2, 2, 2, 3, 5, 2, 9, 2, 0, 0, 0, 0, 0, 20, 20, 5, 5, 0]


def test_siemens_sources_in_translator():
    prog = scl37.load_program(SOURCES)
    for n in range(1, 2001):
        prog.ob["Main"]()
        if prog.db["DB_TestResult"].Done:
            break
    r = prog.db["DB_TestResult"]
    assert r.Done and r.AllPassed
    assert (r.CasesTotal, r.CasesRun, r.CasesPassed, r.CasesFailed) == (20, 20, 20, 0)
    assert r.CaseNok[:20] == EXPECTED_NOK
    assert int(r.BenchCalls) == 102
    assert float(r.MaxFeatError) < 1e-4


def test_codesys_test_data_is_generated_from_siemens_block():
    lines = testdata.codesys_lines(testdata.read_db())
    assert "\n".join(lines) + "\n" == (ROOT / "codesys" / "src" / "GVL_TestData.st").read_text(encoding="utf-8")


def test_codesys_run_record():
    rec = json.loads((ROOT / "results" / "codesys_bench.json").read_text(encoding="utf-8"))
    assert rec["build"] == {"errors": 0, "warnings": 0}
    b = rec["bench"]
    assert b["Done"] == "TRUE" and b["AllPassed"] == "TRUE"
    assert b["CasesPassed"] == "INT#20" and b["CasesFailed"] == "INT#0"
    noks = [int(c["nok"].split("#")[1]) for c in rec["cases"]]
    assert noks == EXPECTED_NOK
    assert all(c["pass"] == "TRUE" for c in rec["cases"])
