"""Derive the station visualization from the visualization of the CODESYS sample project.

The CODESYS script API showed no call that creates a visualization, and drawing one needs the
CODESYS window. So the visualization "Visualization" and the "Visualization Manager" of the sample
project that ships with CODESYS (Projects/RefrigeratorControl.projectarchive) were exported in the
native format by the CODESYS script engine (ScriptObject.export_native), and this script replaces
their variables, texts and start visualization by the station's. The result is imported by
codesys/scripts/visu_try.py. The exported files and the result stay in codesys/build/ (not in the
repo): they are the vendor's sample with a few strings changed.

What the result shows: the five variables below and the texts. The element types and the layout are
the sample's (lamps, a meter, a potentiometer, a rocker switch, text fields). It is a proof that a
visualization bound to the station builds without a window, not the station screen of the
specification (docs/img/screen_spec.svg).

    python codesys/scripts/derive_visu.py <Visualization.export> <VisualizationManager.export>
"""

import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1] / "build"

VISU = [
    ("Glob_Var.TempActual", "PLC_PRG.Bench.Station.TCycle"),
    ("Glob_Var.TempSet", "PLC_PRG.Bench.Eval.FPeak"),
    ("Glob_Var.DoorOpen", "PLC_PRG.Bench.Station.Locked"),
    ("Glob_Var.Compressor", "PLC_PRG.Bench.Station.RigCheckRequired"),
    ("Glob_Var.Signal", "GVL_TestResult.AllPassed"),
    ("Actual temperature: %2.1f °C", "Cycle time of the last part: %2.3f s"),
    ("Temperature presetting: %.1f °C", "Peak force of the last replayed curve: %.1f N"),
    ("Door open", "Reject lock"),
    ("Cooling compressor", "Rig check required"),
    ("Signal (Beep)", "Bench: all cases passed"),
    ('<Single Name="Name" Type="string">Visualization</Single>', '<Single Name="Name" Type="string">StationVisu</Single>'),
]
MANAGER = [
    ('<Single Name="StartVisu" Type="string">Live_Visu</Single>', '<Single Name="StartVisu" Type="string">StationVisu</Single>'),
    ('<Single Name="StartVisu" Type="string">Diagnosis</Single>', '<Single Name="StartVisu" Type="string">StationVisu</Single>'),
]


def apply(src: Path, dst: Path, pairs) -> None:
    t = src.read_text(encoding="utf-8")
    for a, b in pairs:
        if a not in t:
            raise SystemExit(f"not found in {src.name}: {a}")
        t = t.replace(a, b)
    dst.write_text(t, encoding="utf-8")


if __name__ == "__main__":
    apply(Path(sys.argv[1]), BUILD / "StationVisu.export", VISU)
    apply(Path(sys.argv[2]), BUILD / "VisuManager.export", MANAGER)
    print("written", BUILD / "StationVisu.export", BUILD / "VisuManager.export")
