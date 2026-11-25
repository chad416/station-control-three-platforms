"""The generated screen files are well-formed and match their generators (no vendor tool involved)."""

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wincc_import_files_are_generated_and_well_formed():
    m = _load(ROOT / "siemens" / "hmi" / "make_hmi_xml.py")
    files = sorted((ROOT / "siemens" / "hmi" / "xml").glob("*.xml"))
    assert len(files) == 11
    for f in files:
        ET.parse(f)
    assert (ROOT / "siemens" / "hmi" / "xml" / "tags_Station.xml").read_text(encoding="utf-8") == m.tag_table()
    assert len(m.TAGS) == 36


def test_screen_drawing_is_labelled_generated():
    svg = (ROOT / "docs" / "img" / "screen_spec.svg").read_text(encoding="utf-8")
    ET.fromstring(svg)
    assert "GENERATED DRAWING" in svg
