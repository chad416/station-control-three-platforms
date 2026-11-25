"""Checks of the Logix port that run without Rockwell software (CI).

None of them shows that Logix Designer imports or verifies the file; see tools/l5x_check.py and
tools/logix_st.py for what each one does and does not prove.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import l5x_check  # noqa: E402
import logix_st  # noqa: E402
import make_logix  # noqa: E402

L5X = ROOT / "logix" / "StationPort.L5X"
EXPECTED_NOK = [0, 0, 2, 2, 2, 3, 5, 2, 9, 2, 0, 0, 0, 0, 0, 20, 20, 5, 5, 0]


def test_l5x_is_generated_from_the_sources(tmp_path, monkeypatch):
    out = tmp_path / "StationPort.L5X"
    monkeypatch.setattr(make_logix, "OUT", out)
    make_logix.main()
    assert out.read_text(encoding="utf-8") == L5X.read_text(encoding="utf-8")


def test_structural_check_finds_nothing():
    assert l5x_check.check(L5X) == []


def _mutated(tmp_path, old, new, count=1):
    text = L5X.read_text(encoding="utf-8")
    assert text.count(old) >= count, old
    p = tmp_path / "m.L5X"
    p.write_text(text.replace(old, new, count), encoding="utf-8")
    return p


def test_structural_check_catches_an_array_input(tmp_path):
    p = _mutated(tmp_path, '<Parameter Name="X" TagType="Base" DataType="REAL" Usage="Input"',
                 '<Parameter Name="X" TagType="Base" DataType="REAL" Dimensions="4" Usage="Input"')
    assert any(e.startswith("A1") for e in l5x_check.check(p))


def test_structural_check_catches_a_global_tag_inside_an_aoi(tmp_path):
    p = _mutated(tmp_path, "tNodeX := Rcp.EnvX0", "tNodeX := TD_EnvX0")
    assert any(e.startswith("S2") and "td_envx0" in e for e in l5x_check.check(p))


def test_structural_check_catches_a_missing_inout_argument(tmp_path):
    p = _mutated(tmp_path, "AOI_HandleStation(Station, StationRcp, StationCnt);", "AOI_HandleStation(Station, StationRcp);")
    assert any(e.startswith("A7") for e in l5x_check.check(p))


def test_interpreter_runs_the_bench_20_of_20():
    r = logix_st.run_bench(L5X)
    assert r["Done"] and r["AllPassed"]
    assert (r["CasesTotal"], r["CasesRun"], r["CasesPassed"], r["CasesFailed"]) == (20, 20, 20, 0)
    assert r["CaseNok"] == EXPECTED_NOK and r["CaseCheck"] == [0] * 20
    assert r["BenchCalls"] == 102
    assert r["MaxFeatError"] < 1e-4
    assert r["Station"] == {"State": 0, "CntTotal": 5, "CntOk": 2, "CntNok": 3, "CntRejectConfirmed": 3}


def test_interpreter_bench_fails_on_a_wrong_limit(tmp_path):
    # the release-step check turned round: the bench must notice
    p = _mutated(tmp_path, "ELSIF sFStep &lt; Rcp.StepLo THEN", "ELSIF sFStep &gt; Rcp.StepLo THEN") \
        if "sFStep &lt;" in L5X.read_text(encoding="utf-8") else \
        _mutated(tmp_path, "ELSIF sFStep < Rcp.StepLo THEN", "ELSIF sFStep > Rcp.StepLo THEN")
    r = logix_st.run_bench(p)
    assert r["Done"] and not r["AllPassed"] and r["CasesFailed"] > 0
