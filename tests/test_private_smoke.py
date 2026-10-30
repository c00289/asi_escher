"""Local-only smoke test on the owner's private control structure.

The datasets live in the private asi_standards repository beside this one;
when that folder is absent (CI, any other machine) the test skips.  Nothing
from the datasets is asserted or printed: only counts, the tier shape, that
the outputs are well-formed and the OCR verdict.
"""
import io
import json
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from asi_escher import Diagram, LayoutWarning, layout, ocr_check, render, to_drawio
from asi_escher.ocr import expected_labels

DATASETS = Path(__file__).resolve().parents[2] / "asi_standards" / "control-structures" / "wheel-loader" / "datasets"

pytestmark = pytest.mark.skipif(not DATASETS.is_dir(), reason="private datasets not present")


def _rows(name: str) -> list[dict]:
    with open(DATASETS / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)["rows"]


def _private_structure() -> Diagram:
    d = Diagram("Private structure", "control_structure")
    algorithms = {}
    for a in sorted(_rows("algorithms"), key=lambda r: (r["controller_id"], r["order"])):
        algorithms.setdefault(a["controller_id"], []).append((a["id"], a["name"]))
    entries = {}
    for p in sorted(_rows("process_model_entries"), key=lambda r: (r["controller_id"], r["id"])):
        entries.setdefault(p["controller_id"], []).append(p["heading"])
    for c in sorted(_rows("controllers"), key=lambda r: r["order"]):
        pm = (c["process_model_title"], entries.get(c["id"], [])) if c["process_model_title"] else None
        d.controller(c["id"], c["name"], kind=c["kind"], responsibility=c["responsibility"],
                     algorithms=algorithms.get(c["id"], []), process_model=pm)
    signals = {s["signal_id"]: s for s in _rows("signals")}
    for e in _rows("edges"):
        lines = [f"{sid} {signals[sid]['name']}" for sid in e["signal_ids"]]
        (d.control_action if e["kind"] == "control_action" else d.feedback)(e["source_id"], e["target_id"], lines)
    for n in _rows("notes"):
        d.note(n["id"], n["text"], attached_to=n["attached_to"] or None)
    return d


def test_private_structure_builds_renders_and_exports():
    d = _private_structure()
    boxes = [n for n in d.real_nodes() if n.kind != "note"]
    assert len(boxes) == 8
    assert len(d.edges) == 21
    assert sum(len(e.signals) for e in d.edges) == 58
    assert sum(len(n.algorithms) for n in boxes) == 30
    assert sum(len(n.process_model[1]) for n in boxes if n.process_model) == 18
    with warnings.catch_warnings():
        warnings.simplefilter("error", LayoutWarning)       # since 0.2.1 the structure lays out without any issue
        layout(d)
    assert all(e.points for e in d.edges) and d.width > 0 and d.height > 0
    assert [i for i in d.issues if i.kind == "label_overlap"] == [] and d.issues == []
    tiers = {}
    for n in boxes:
        tiers[n.layer] = tiers.get(n.layer, 0) + 1
    assert sorted(tiers) == [0, 1, 2, 3]                                 # four tiers since 0.2.1 ...
    assert [tiers[k] for k in sorted(tiers)] == [3, 2, 1, 2]             # ... of this shape, top to bottom
    assert d.width >= 0.75 * d.height                                    # wider than tall, not a tower
    png, svg = io.BytesIO(), io.BytesIO()
    render(d, png=png, svg=svg)
    assert png.getvalue()[:8] == b"\x89PNG\r\n\x1a\n" and b"<svg" in svg.getvalue()
    xml = to_drawio(d)
    root = ET.fromstring(xml)
    assert root.get("compressed") == "false"
    cells = root.findall("diagram/mxGraphModel/root/mxCell")
    assert sum(1 for c in cells if c.get("vertex") == "1" and c.get("id") != "provenance") == 9   # 8 boxes + 1 note
    assert sum(1 for c in cells if c.get("edge") == "1") == 21
    assert sum(len(c.get("value").split("<br>")) for c in cells if c.get("edge") == "1") == 58



def test_private_structure_is_competent_under_real_ocr(tmp_path):
    d = _private_structure()
    with warnings.catch_warnings():
        warnings.simplefilter("error", LayoutWarning)
        layout(d)
    png = tmp_path / "private.png"
    render(d, png=str(png))
    report = ocr_check(str(png), expected_labels(d))
    if not report.available:
        pytest.skip("Windows OCR engine unavailable")
    assert len(report.expected) > 60 and len(report.lines) > 150
    assert report.competent, f"{len(report.missing)} label(s) unreadable"
