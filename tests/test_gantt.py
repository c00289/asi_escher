"""The ``gantt`` kind: builder, derived status, rows and bars, the header, dependencies, renderer, exports,
spec and CLI."""
import io
import json
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from asi_escher import (
    GANTT_EDGE_KINDS,
    GANTT_NODE_KINDS,
    Diagram,
    LayoutOptions,
    LayoutWarning,
    Period,
    build,
    layout,
    render,
    to_dot,
    to_drawio,
    to_mermaid,
)
from asi_escher.cli import main
from asi_escher.examples import chain_demo, gantt_demo
from asi_escher.gantt import EDGE_LEAD, GROUP_H, HEADER_H, MILESTONE, ROW_H, is_task, rows_of

ROOT = Path(__file__).resolve().parent.parent


def _small():
    """Two groups, four tasks and a milestone under two sprints, today in the second; b depends on a,
    d on c and the milestone on d; e depends on b although it starts earlier (a back edge)."""
    d = Diagram("Small plan", "gantt")
    d.period("S1", "2026-01-05", "2026-01-18")
    d.period("S2", "2026-01-19", "2026-02-01")
    d.mark("2026-01-20")
    d.task("a", "First", "2026-01-05", "2026-01-09", status="done", owner="Lead", group="One")
    d.task("b", "Second", "2026-01-12", "2026-01-23", status="active", owner="Engineer", group="One",
           note="in review")
    d.task("c", "Third", "2026-01-12", "2026-01-16", group="Two")
    d.task("d", "Fourth", "2026-01-26", "2026-01-30", group="Two")
    d.task("e", "Fifth", "2026-01-19", "2026-01-21", group="Two")
    d.milestone("m", "Done", "2026-02-03", group="Two")
    d.depends("a", "b")
    d.depends("c", "d")
    d.depends("d", "m")
    d.depends("b", "e")
    return d


# ------------------------------------------------------------- builder ----
def test_builder_fills_fields_and_defaults():
    d = _small()
    assert d.direction == "LR"
    a, m = d.nodes["a"], d.nodes["m"]
    assert a.kind == "task" and a.start == "2026-01-05" and a.end == "2026-01-09" and a.group == "One"
    assert a.status == "done" and a.owner == "Lead" and a.effort is None
    assert m.kind == "milestone" and m.start == m.end == "2026-02-03"
    assert d.task("one_day", "One day", "2026-03-01").end == "2026-03-01"          # end defaults to start
    assert [(e.src, e.dst, e.kind) for e in d.edges][:2] == [("a", "b", "depends"), ("c", "d", "depends")]
    assert [(p.label, p.start, p.end) for p in d.periods] == [("S1", "2026-01-05", "2026-01-18"),
                                                               ("S2", "2026-01-19", "2026-02-01")]
    assert isinstance(d.periods[0], Period) and d.today == "2026-01-20"
    assert GANTT_NODE_KINDS == {"task", "milestone"} and GANTT_EDGE_KINDS == {"depends"}
    assert d.task("w", "Weighed", "2026-03-02", "2026-03-04", effort=3).effort == 3


def test_builder_rejects_bad_input():
    d = Diagram("x", "gantt")
    with pytest.raises(ValueError, match="status"):
        d.task("a", "A", "2026-01-01", status="odd")
    with pytest.raises(ValueError, match="kind"):
        d.task("a", "A", "2026-01-01", kind="bar")
    with pytest.raises(ValueError, match="ISO date"):
        d.task("a", "A", "January 1st")
    with pytest.raises(ValueError, match="ends .* before it starts"):
        d.task("a", "A", "2026-01-05", "2026-01-04")
    with pytest.raises(ValueError, match="period 'P' ends"):
        d.period("P", "2026-01-05", "2026-01-04")
    with pytest.raises(ValueError, match="effort"):
        d.task("a", "A", "2026-01-01", effort=-1)
    with pytest.raises(ValueError, match="today"):
        d.mark("tomorrow")


def test_rows_follow_author_order_with_a_group_row_per_change():
    assert [(r["kind"], r.get("id", r.get("title"))) for r in rows_of(_small())] == [
        ("group", "One"), ("task", "a"), ("task", "b"), ("group", "Two"), ("task", "c"), ("task", "d"),
        ("task", "e"), ("task", "m"),
    ]


# ------------------------------------------------------------- status -----
def test_late_is_derived_from_today():
    d = _small()
    assert d.status("c") == "late"                 # pending, ended 01-16, today is 01-20
    assert d.status("a") == "done"                 # done stays done
    assert d.status("b") == "active"               # ends 01-23, not yet past
    assert d.status("e") == "pending"
    assert set(d.statuses()) == {"a", "b", "c", "d", "e", "m"}
    d.mark(None)
    assert d.today is None and d.status("c") == "pending"
    d.mark("2026-03-01")
    assert d.status("b") == "late" and d.status("m") == "late" and d.status("a") == "done"


def test_a_chain_milestone_is_not_a_task():
    assert all(is_task(n) for n in gantt_demo().real_nodes())
    assert not any(is_task(n) for n in chain_demo().real_nodes())


# ------------------------------------------------------------- layout -----
def test_layout_places_bars_by_date_and_rows_in_order():
    d = layout(_small())
    g = d.gantt
    ppd = g["ppd"]
    a, b, c, m = d.nodes["a"], d.nodes["b"], d.nodes["c"], d.nodes["m"]
    assert g["t0"] == "2026-01-04" and g["t1"] == "2026-02-04"            # a day of air at both ends
    assert a.left == pytest.approx(g["x0"] + ppd) and a.w == pytest.approx(5 * ppd)
    assert b.y - a.y == pytest.approx(ROW_H) and c.y - b.y == pytest.approx(ROW_H + GROUP_H)
    assert m.w == m.h == MILESTONE and m.x == pytest.approx(g["x0"] + 30 * ppd + ppd / 2)
    assert g["rows_top"] == pytest.approx(g["y0"] + 2 * HEADER_H)             # periods, then months
    assert [r["h"] for r in g["rows"] if r["kind"] == "group"] == [GROUP_H, GROUP_H]
    assert [label for label, _x, _x2 in g["periods"]] == ["S1", "S2"]
    assert [label for label, _x in g["months"]] == ["Jan 2026", "Feb 2026"]
    assert b.left < g["today_x"] < b.right                                     # 01-20 is inside b's bar
    assert [(nid, note) for nid, _x, _y, note in g["notes"]] == [("b", "in review")]
    assert d.width >= g["x1"] and d.height == pytest.approx(g["rows_bottom"] + 36)
    assert g["title_x"] < g["owner_x"] < g["x0"] < g["x1"]


def test_day_px_sets_the_scale_once_the_timeline_is_wide_enough():
    d = layout(_small(), LayoutOptions(day_px=10))
    assert d.gantt["ppd"] == pytest.approx(10)
    narrow = layout(_small(), LayoutOptions(day_px=1))
    assert narrow.gantt["x1"] - narrow.gantt["x0"] == pytest.approx(240)     # the narrowest scale


def test_dependencies_are_elbows_forward_and_loops_back():
    d = layout(_small())
    ab = next(e for e in d.edges if (e.src, e.dst) == ("a", "b"))
    a, b = d.nodes["a"], d.nodes["b"]
    assert not ab.back
    assert ab.points == [(a.right, a.y), (b.left - EDGE_LEAD, a.y), (b.left - EDGE_LEAD, b.y), (b.left, b.y)]
    be = next(e for e in d.edges if (e.src, e.dst) == ("b", "e"))
    assert be.back and len(be.points) == 6                                     # out, along the boundary, back in
    for e in d.edges:
        for p, q in zip(e.points, e.points[1:], strict=False):
            assert abs(p[0] - q[0]) < 0.5 or abs(p[1] - q[1]) < 0.5
    assert d.issues == []


def test_a_dependency_through_a_bar_is_an_issue():
    d = Diagram("crowded", "gantt")
    d.task("p", "P", "2026-01-05", "2026-01-09")
    d.task("q", "Q", "2026-01-05", "2026-01-30")
    d.task("r", "R", "2026-01-12", "2026-01-16")
    d.depends("p", "r")
    with pytest.warns(LayoutWarning, match="crowded"):
        layout(d)
    assert [(i.kind, i.node, i.edge) for i in d.issues] == [("edge_through_node", "q", ("p", "r"))]


def test_layout_is_repeatable_and_resets_issues():
    d = _small()
    layout(d)
    first = {n.id: (n.x, n.y, n.w) for n in d.real_nodes()}
    layout(d)
    assert {n.id: (n.x, n.y, n.w) for n in d.real_nodes()} == first and d.issues == []


# ----------------------------------------------------------- rendering ----
def test_render_svg_shows_the_chrome_and_the_status_colours():
    svg = io.BytesIO()
    render(layout(_small()), svg=svg)
    text = svg.getvalue().decode("utf-8")
    for s in ("First", "Second", "Lead", "Engineer", "in review", "S1", "S2", "Jan 2026", "today", "One", "Two"):
        assert s in text, s
    lower = text.lower()                                                    # matplotlib writes hex in lowercase
    assert "#dce5dc" in lower and "#d6e6f7" in lower and "#ffe3a8" in lower  # done, active, late
    assert "#c62828" in lower                                               # the today line
    with pytest.raises(ValueError, match="focus"):
        render(layout(_small()), svg=io.BytesIO(), focus="a")


# ------------------------------------------------------------- exports ----
def test_dot_export_has_every_task_with_its_dates():
    d = _small()
    dot = to_dot(d)
    for n in d.real_nodes():
        assert f'"{n.id}"' in dot
    assert "2026-01-05 to 2026-01-09" in dot and "shape=diamond" in dot and '"a" -> "b"' in dot
    assert 'fillcolor="#DCE5DC"' in dot and 'fillcolor="#FFE3A8"' in dot


def test_mermaid_export_is_a_native_gantt():
    mmd = to_mermaid(_small())
    assert mmd.startswith("---\ntitle: Small plan\n---\ngantt\n  dateFormat YYYY-MM-DD")
    assert "  section One\n  First :done, a, 2026-01-05, 2026-01-10\n" in mmd    # Mermaid's end is exclusive
    assert "Second :active, b, 2026-01-12, 2026-01-24" in mmd
    assert "Third :crit, c, 2026-01-12, 2026-01-17" in mmd                       # late
    assert "Done :milestone, m, 2026-02-03, 0d" in mmd
    assert "%% today: 2026-01-20" in mmd and "%% a -> b" in mmd


def test_drawio_export_carries_the_chrome_and_the_bars_where_the_layout_put_them():
    d = layout(_small())
    root = ET.fromstring(to_drawio(d))
    cells = {c.get("id"): c for c in root.findall("diagram/mxGraphModel/root/mxCell")}
    for n in d.real_nodes():
        g = cells[n.id].find("mxGeometry")
        assert (float(g.get("x")), float(g.get("y")), float(g.get("width")), float(g.get("height"))) == \
            pytest.approx((n.left, n.top, n.w, n.h), abs=0.01), n.id
        assert cells[n.id].get("value") == ""                               # the title is in the column
    assert cells["title_a"].get("value") == "<b>First</b>" and cells["owner_a"].get("value") == "Lead"
    assert cells["group_0"].get("value") == "<b>One</b>" and cells["note_b"].get("value") == "in review"
    assert cells["period_0"].get("value") == "<b>S1</b>" and "today" in cells and "today_label" in cells
    assert "rhombus" in cells["m"].get("style") and "fillColor=#DCE5DC" in cells["a"].get("style")
    assert "fillColor=#FFE3A8" in cells["c"].get("style")
    edges = [c for c in cells.values() if c.get("edge") == "1"]
    assert len(edges) == 4 and "endArrow=block" in edges[0].get("style")


# ---------------------------------------------------------------- spec ----
def test_spec_round_trip():
    d = _small()
    data = d.to_dict()
    assert data["kind"] == "gantt" and data["today"] == "2026-01-20" and len(data["periods"]) == 2
    assert data["tasks"][0] == {"id": "a", "title": "First", "start": "2026-01-05", "end": "2026-01-09",
                                "status": "done", "owner": "Lead", "group": "One"}
    assert data["tasks"][-1]["kind"] == "milestone" and data["edges"][0] == {"src": "a", "dst": "b"}
    again = Diagram.from_dict(json.loads(json.dumps(data)))
    assert again.to_dict() == data and again.kind == "gantt"
    with pytest.raises(ValueError, match="'start'"):
        Diagram.from_dict({"title": "t", "tasks": [{"id": "a"}]})
    with pytest.raises(ValueError, match="period"):
        Diagram.from_dict({"title": "t", "periods": [{"label": "P"}], "tasks": []})
    with pytest.raises(ValueError, match="src"):
        Diagram.from_dict({"title": "t", "tasks": [{"id": "a", "start": "2026-01-01"}], "edges": [{"dst": "a"}]})


def test_docs_spec_is_the_demo():
    with open(ROOT / "docs" / "gantt_spec.json", encoding="utf-8") as f:
        data = json.load(f)
    assert data == gantt_demo().to_dict()


# ----------------------------------------------------------------- CLI ----
def test_cli_exports_a_gantt_spec_with_its_scale(tmp_path, capsys):
    spec = tmp_path / "plan.json"
    spec.write_text(json.dumps(_small().to_dict()), encoding="utf-8")
    assert main(["export", str(spec), "--out", str(tmp_path), "--format", "png", "--format", "svg",
                 "--day-px", "6"]) == 0
    assert (tmp_path / "small_plan.png").exists() and (tmp_path / "small_plan.svg").exists()
    assert "6 nodes, 4 edges" in capsys.readouterr().out
    assert main(["example", "gantt_demo", "-o", str(tmp_path), "--formats", "mmd", "--day-px", "3"]) == 0
    assert "gantt" in (tmp_path / "gantt_demo.mmd").read_text(encoding="utf-8").splitlines()[3]
    assert "gantt_demo" in [line for line in (main(["list"]), capsys.readouterr().out)[1].split()]


# ------------------------------------------------------------- example ----
def test_demo_has_the_promised_shape():
    d = gantt_demo()
    assert len(d.real_nodes()) == 13 and len(d.edges) == 13 and len(d.periods) == 4
    statuses = d.statuses()
    assert statuses["scope"] == statuses["standards"] == "done"
    assert statuses["hazards"] == "active" and statuses["supplier"] == "late"
    assert sum(1 for s in statuses.values() if s == "pending") == 9
    assert d.nodes["release"].kind == "milestone"
    with warnings.catch_warnings():
        warnings.simplefilter("error", LayoutWarning)
        layout(d)
    assert d.issues == [] and not any(e.back for e in d.edges)


def test_demo_is_competent_under_real_ocr(ocr_engine, tmp_path):
    if not ocr_engine:
        pytest.skip("Windows OCR engine unavailable")
    res = build(gantt_demo(), str(tmp_path), formats=("png",), ocr=True)
    assert res["ocr"].available and res["ocr"].competent, res["ocr"].verdict
    assert res["issues"] == []
