"""The ``chain`` kind: builder, derived status, the queries, layout rules, renderer, exports, spec and CLI."""
import io
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from asi_escher import (
    CHAIN_EDGE_KINDS,
    CHAIN_NODE_KINDS,
    CHAIN_STATUSES,
    Diagram,
    LayoutOptions,
    LayoutWarning,
    build,
    layout,
    render,
    to_dot,
    to_drawio,
    to_mermaid,
)
from asi_escher.cli import main
from asi_escher.examples import chain_demo
from asi_escher.metrics import chain_sublines
from asi_escher.ocr import expected_labels

ROOT = Path(__file__).resolve().parent.parent


def _small():
    """a -> b -> d, c -> d, with c late; e dangles off an informs edge."""
    d = Diagram("Small", "chain")
    d.event("a", "First", status="done", owner="Lead", due="2026-01-02")
    d.event("b", "Second", status="active")
    d.event("c", "Third", status="late", kind="external")
    d.event("d", "Fourth", kind="gate")
    d.event("e", "Fifth", kind="milestone", note="a note")
    d.blocks("a", "b")
    d.blocks("b", "d")
    d.blocks("c", "d", label="data")
    d.blocks("d", "e", kind="informs")
    return d


# ------------------------------------------------------------- builder ----
def test_builder_fills_fields_and_defaults():
    d = _small()
    assert d.direction == "LR"                              # a chain runs left to right by default
    a, e = d.nodes["a"], d.nodes["e"]
    assert a.kind == "event" and a.status == "done" and a.owner == "Lead" and a.due == "2026-01-02"
    assert e.kind == "milestone" and e.status == "pending" and e.note == "a note" and e.effort is None
    assert [(x.src, x.dst, x.kind, x.label) for x in d.edges][2:] == [("c", "d", "blocks", "data"),
                                                                      ("d", "e", "informs", "")]
    assert chain_sublines(a) == [("owner", "Lead"), ("due", "due 2026-01-02")]
    assert chain_sublines(e) == [("note", "a note")]
    assert d.event("f", "Weighed", effort=3).effort == 3


def test_kinds_and_statuses_are_registered():
    assert CHAIN_NODE_KINDS == {"event", "milestone", "gate", "external"}
    assert CHAIN_EDGE_KINDS == {"blocks", "enables", "informs"}
    assert CHAIN_STATUSES == {"done", "active", "blocked", "pending", "late"}
    assert Diagram("x").direction == "TB"                   # every other kind as before


def test_builder_rejects_bad_input():
    d = Diagram("k", "chain")
    with pytest.raises(ValueError, match="event status"):
        d.event("x", "X", status="maybe")
    with pytest.raises(ValueError, match="event kind"):
        d.event("x", "X", kind="action")
    with pytest.raises(ValueError, match="effort"):
        d.event("x", "X", effort=-1)
    with pytest.raises(ValueError, match="effort"):
        d.event("x", "X", effort=True)
    d.event("x", "X")
    d.event("y", "Y")
    with pytest.raises(ValueError, match="chain edge kind"):
        d.blocks("x", "y", kind="flow")
    with pytest.raises(KeyError):
        d.blocks("x", "nope")
    with pytest.raises(KeyError, match="unknown event"):
        d.blockers("nope")


# --------------------------------------------------------------- status ---
def test_blocked_is_derived_from_a_late_or_blocked_predecessor():
    d = _small()
    assert d.status("d") == "blocked"                       # c is late and blocks d
    assert d.status("b") == "active" and d.status("c") == "late" and d.status("e") == "pending"
    assert d.statuses() == {"a": "done", "b": "active", "c": "late", "d": "blocked", "e": "pending"}
    d.nodes["c"].status = "pending"
    assert d.status("d") == "pending"                       # a pending predecessor is the normal course
    d.nodes["c"].status = "blocked"
    assert d.status("d") == "blocked"                       # a stuck one is not
    d.nodes["d"].status = "active"
    assert d.status("d") == "active"                        # a given status is kept
    d.blocks("c", "e", kind="enables")
    assert d.status("e") == "pending"                       # only a blocks edge blocks
    assert d.to_dict()["events"][3] == {"id": "d", "title": "Fourth", "kind": "gate", "status": "active"}


# -------------------------------------------------------------- queries ---
def test_direct_and_transitive_queries_in_dependency_order():
    d = chain_demo()
    assert d.predecessors("design") == ["reqs", "metrics"]
    assert d.successors("reqs") == ["design", "testplan"]
    assert d.predecessors("testplan") == ["reqs"]           # informs is not precedence
    assert d.upstream("design") == ["scope", "standards", "supplier", "hazards", "metrics", "risk", "concept",
                                    "reqs"]
    assert d.downstream("supplier") == ["metrics", "risk", "concept", "reqs", "design", "testplan", "verification",
                                        "validation", "assessment", "release"]
    assert d.downstream("release") == [] and d.upstream("scope") == []
    assert d.columns() == {"scope": 0, "standards": 0, "supplier": 0, "hazards": 1, "metrics": 1, "risk": 2,
                           "concept": 3, "reqs": 4, "design": 5, "testplan": 5, "verification": 6,
                           "validation": 7, "assessment": 8, "release": 9}


def test_blockers_nearest_first_up_to_the_done_ones():
    d = chain_demo()
    assert d.blockers("design") == ["metrics", "reqs", "supplier", "concept", "risk", "hazards"]
    assert d.blockers("risk") == ["supplier", "hazards"]    # author order; scope is done: the chain stops there
    assert d.blockers("scope") == [] and d.blockers("standards") == []
    assert d.blockers("testplan") == ["reqs", "concept", "risk", "supplier", "hazards"]   # not via informs


def test_critical_path_by_count_then_by_effort():
    d = chain_demo()
    assert d.critical_path() == ["scope", "hazards", "risk", "concept", "reqs", "design", "verification",
                                 "validation", "assessment", "release"]
    assert ("scope", "hazards") in d.critical_edges() and ("reqs", "testplan") not in d.critical_edges()
    w = Diagram("Weighed", "chain")
    w.event("a", "A", effort=1)
    w.event("b", "B", effort=1)
    w.event("c", "C", effort=1)
    w.event("x", "X", effort=5)
    w.blocks("a", "b")
    w.blocks("b", "c")
    w.blocks("a", "x")
    assert w.critical_path() == ["a", "x"]                  # 6 beats 3
    for n in w.nodes.values():
        n.effort = None
    assert w.critical_path() == ["a", "b", "c"]             # by count again
    assert Diagram("empty", "chain").critical_path() == []


def test_cycles_are_reported_and_the_layout_still_completes():
    d = Diagram("Loop", "chain")
    for k in "abc":
        d.event(k, k.upper())
    d.blocks("a", "b")
    d.blocks("b", "c")
    d.blocks("c", "a")
    d.blocks("c", "c")
    assert d.cycles() == [["a", "b", "c"], ["c"]]
    assert [(e.src, e.dst) for e in d.back_edges()] == [("c", "a"), ("c", "c")]
    assert d.critical_path() == ["a", "b", "c"]
    assert d.upstream("a") == [] and d.downstream("c") == []
    with pytest.warns(LayoutWarning, match="cycle"):
        layout(d)
    issues = [i for i in d.issues if i.kind == "cycle"]
    assert [i.edge for i in issues] == [("c", "a"), ("c", "c")]
    assert "a -> b -> c -> a" in issues[0].message and "c->a is drawn backwards" in issues[0].message
    assert d.nodes["a"].x < d.nodes["b"].x < d.nodes["c"].x
    back = next(e for e in d.edges if (e.src, e.dst) == ("c", "a"))
    assert back.back and len(back.points) == 4


# --------------------------------------------------------------- layout ---
def test_column_rule_and_informs_does_not_move_an_event():
    d = _small()
    layout(d)
    n = d.nodes
    assert n["a"].layer == n["c"].layer == 0 and n["b"].layer == 1 and n["d"].layer == 2
    assert n["e"].layer == 0                                # only an informs edge leads to it
    assert n["a"].x == pytest.approx(n["c"].x) == pytest.approx(n["e"].x)
    assert n["a"].x < n["b"].x < n["d"].x
    informs = next(e for e in d.edges if e.kind == "informs")
    assert informs.back and len(informs.points) == 4       # drawn back through the channel
    assert d.issues == []
    f = Diagram("Forward informs", "chain")
    f.event("a", "A")
    f.event("b", "B")
    f.event("c", "C")
    f.blocks("a", "b")
    f.blocks("b", "c")
    f.blocks("a", "c", kind="informs")
    layout(f)
    assert [f.nodes[k].layer for k in "abc"] == [0, 1, 2]
    assert not next(e for e in f.edges if e.kind == "informs").back    # a forward one is a plain dashed edge
    assert f.issues == []


def test_demo_keeps_the_critical_path_on_one_straight_row():
    d = chain_demo()
    layout(d)
    path = d.critical_path()
    assert len({round(d.nodes[k].y, 3) for k in path}) == 1
    xs = [d.nodes[k].x for k in path]
    assert xs == sorted(xs)
    for a, b in zip(path, path[1:], strict=False):
        e = next(e for e in d.edges if (e.src, e.dst) == (a, b))
        assert len(e.points) == 2 and e.points[0][1] == pytest.approx(e.points[1][1])   # straight
    assert d.issues == []
    assert d.width > 3 * d.height
    assert LayoutOptions.for_kind("chain").nodesep < LayoutOptions.for_kind("control_structure").nodesep


# ------------------------------------------------------------- renderer ---
def test_render_svg_shows_status_colours_and_kind_shapes():
    d = layout(chain_demo())
    png, svg = io.BytesIO(), io.BytesIO()
    render(d, png=png, svg=svg)
    assert png.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
    text = svg.getvalue().decode("utf-8").lower()
    assert "#f4c2c2" in text                               # blocked
    assert "#ffe3a8" in text and "#dce5dc" in text and "#d6e6f7" in text    # late, done, active
    for title in ("Scope definition", "Supplier failure", "Safety assessment"):   # a long title wraps
        assert title.lower() in text
    assert "programme lead" in text and "due 2027-04-23" in text and "second reminder sent" in text
    assert "stroke-dasharray" in text                       # the external event and the informs edge
    assert "stroke-width: 2.85" in text                     # the critical path's blocks arrows, 1.5 x 1.9
    assert "stroke-width: 0.9" in text                      # an enables edge


def test_focus_dims_everything_but_the_blocker_chain():
    d = layout(chain_demo())
    plain, focused = io.BytesIO(), io.BytesIO()
    render(d, svg=plain)
    render(d, svg=focused, focus="risk")
    assert b"opacity: 0.22" not in plain.getvalue()
    text = focused.getvalue().decode("utf-8")
    assert text.count("opacity: 0.22") > 20                 # most of the drawing is dimmed
    with pytest.raises(KeyError, match="unknown event"):
        render(d, svg=io.BytesIO(), focus="nope")
    with pytest.raises(ValueError, match="chain"):
        render(layout(Diagram("x")), svg=io.BytesIO(), focus="a")


def test_expected_labels_are_the_titles():
    assert expected_labels(_small()) == ["First", "Second", "Third", "Fourth", "Fifth"]


# -------------------------------------------------------------- exports ---
def test_dot_export_of_the_kind():
    d = chain_demo()
    dot = to_dot(d)
    assert "rankdir=LR" in dot
    assert '"release" [shape=hexagon' in dot
    assert '"assessment" [shape=box, style="filled"' in dot and "peripheries=2" in dot
    assert '"supplier" [shape=box, style="dashed,filled"' in dot and 'fillcolor="#FFE3A8"' in dot
    assert 'fillcolor="#F4C2C2"' in dot
    assert '<B>Scope definition</B><BR/><FONT POINT-SIZE="9">Programme lead</FONT>' in dot
    assert '"scope" -> "hazards" [penwidth=2.6];' in dot    # the critical path
    assert '"standards" -> "reqs" [penwidth=0.8];' in dot   # enables
    assert '"risk" -> "testplan" [style=dashed, arrowhead=vee, constraint=false];' in dot
    assert '"supplier" -> "metrics" [label="failure rates", penwidth=1.4];' in dot


def test_mermaid_export_of_the_kind():
    d = chain_demo()
    mmd = to_mermaid(d)
    assert mmd.startswith("---\ntitle: Demo Safety Programme Chain\n---\nflowchart LR")
    assert 'risk["<b>Risk assessment</b><br/><small>Safety engineer</small>' in mmd and ':::blocked' in mmd
    assert 'release{{"<b>Release for operation</b>' in mmd and 'assessment[["<b>Safety assessment</b>' in mmd
    assert "classDef blocked fill:#F4C2C2,stroke:#B83232" in mmd
    assert "classDef late fill:#FFE3A8" in mmd
    assert "  risk -.-> testplan" in mmd and '  supplier -->|"failure rates"| metrics' in mmd
    assert "  linkStyle 0 stroke-width:3px" in mmd and "  linkStyle 6 stroke-width:1px" in mmd
    assert "  style supplier stroke-dasharray:6 3" in mmd


def test_drawio_export_parsed_back_matches_the_layout_and_carries_the_styles():
    d = layout(chain_demo())
    root = ET.fromstring(to_drawio(d))
    cells = {c.get("id"): c for c in root.findall("diagram/mxGraphModel/root/mxCell")}
    for n in d.real_nodes():
        g = cells[n.id].find("mxGeometry")
        assert (float(g.get("x")), float(g.get("y")), float(g.get("width")), float(g.get("height"))) == \
            pytest.approx((n.left, n.top, n.w, n.h), abs=0.01), n.id
    assert "shape=hexagon" in cells["release"].get("style")
    assert "shape=ext;double=1" in cells["assessment"].get("style")
    assert "dashed=1" in cells["supplier"].get("style") and "fillColor=#FFE3A8" in cells["supplier"].get("style")
    assert "fillColor=#F4C2C2" in cells["risk"].get("style")
    assert cells["scope"].get("value").startswith("<b>Scope definition</b><br><font")
    edges = {(c.get("source"), c.get("target")): c for c in cells.values() if c.get("edge") == "1"}
    assert "strokeWidth=2.6" in edges[("scope", "hazards")].get("style")
    assert "strokeWidth=0.8" in edges[("standards", "reqs")].get("style")
    informs = edges[("risk", "testplan")].get("style")
    assert "dashed=1" in informs and "endArrow=open" in informs
    assert edges[("supplier", "metrics")].get("value") == "failure rates"


# ----------------------------------------------------------------- spec ---
def test_dict_roundtrip_is_the_events_form():
    d = chain_demo()
    data = d.to_dict()
    assert set(data) == {"title", "kind", "direction", "events", "edges"}
    assert data["events"][2] == {"id": "supplier", "title": "Supplier failure data", "kind": "external",
                                 "status": "late", "owner": "Supplier", "due": "2026-10-16",
                                 "note": "second reminder sent"}
    assert data["edges"][3] == {"src": "supplier", "dst": "metrics", "label": "failure rates"}
    assert data["edges"][10] == {"src": "risk", "dst": "testplan", "kind": "informs"}
    d2 = Diagram.from_dict(data)
    assert d2.to_dict() == data and d2.kind == "chain" and d2.direction == "LR"
    assert d2.statuses() == d.statuses() and d2.critical_path() == d.critical_path()
    bare = Diagram.from_dict({"title": "t", "events": [{"id": "a", "title": "A"}]})   # kind defaults to chain
    assert bare.kind == "chain" and bare.nodes["a"].kind == "event"
    with pytest.raises(ValueError, match="'id'"):
        Diagram.from_dict({"title": "t", "events": [{"title": "A"}]})


def test_bundled_spec_is_the_demo():
    with open(ROOT / "docs" / "chain_spec.json", encoding="utf-8") as f:
        data = json.load(f)
    assert data == chain_demo().to_dict()


def test_other_kinds_write_no_event_fields():
    d = Diagram("x", "flowchart")
    d.action("a", "A")
    assert set(d.to_dict()["nodes"][0]) == {"id", "label", "kind"}
    d.node("b", "B", "action", status="done", owner="me")   # the fields travel on any node when set
    assert d.to_dict()["nodes"][1] == {"id": "b", "label": "B", "kind": "action", "status": "done", "owner": "me"}
    assert Diagram.from_dict(d.to_dict()).nodes["b"].owner == "me"


# ------------------------------------------------------------------ CLI ---
def test_cli_chain_verb_prints_blockers_and_the_critical_path(tmp_path, capsys):
    spec = tmp_path / "chain.json"
    spec.write_text(json.dumps(chain_demo().to_dict()), encoding="utf-8")
    assert main(["chain", str(spec), "--blockers", "design"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["critical_path"][0] == "scope" and data["critical_path"][-1] == "release"
    assert data["blockers"] == {"design": ["metrics", "reqs", "supplier", "concept", "risk", "hazards"]}
    assert data["cycles"] == [] and data["statuses"]["risk"] == "blocked" and data["events"] == 14
    assert main(["chain", str(spec)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "scope" not in data["blockers"] and data["blockers"]["risk"] == ["supplier", "hazards"]
    assert main(["chain", str(spec), "--blockers", "nope"]) == 1
    assert "unknown event" in capsys.readouterr().err
    other = tmp_path / "flow.json"
    other.write_text(json.dumps(Diagram("f").to_dict()), encoding="utf-8")
    assert main(["chain", str(other)]) == 2


def test_cli_export_of_a_chain_spec_with_focus(tmp_path, capsys):
    assert main(["export", str(ROOT / "docs" / "chain_spec.json"), "--out", str(tmp_path), "--all",
                 "--focus", "design"]) == 0
    assert set(os.listdir(tmp_path)) == {"demo_safety_programme_chain.drawio", "demo_safety_programme_chain.png",
                                         "demo_safety_programme_chain.svg"}
    assert "14 nodes, 16 edges" in capsys.readouterr().out
    assert "opacity: 0.22" in (tmp_path / "demo_safety_programme_chain.svg").read_text(encoding="utf-8")
    assert main(["list"]) == 0
    assert "chain_demo" in capsys.readouterr().out.split()


# ---------------------------------------------------------------- demo ----
def test_demo_has_the_promised_shape_and_no_issues():
    d = chain_demo()
    assert len(d.real_nodes()) == 14 and len(d.edges) == 16
    kinds = {n.id: n.kind for n in d.real_nodes()}
    assert [k for k, v in kinds.items() if v == "external"] == ["supplier"]
    assert [k for k, v in kinds.items() if v == "gate"] == ["assessment"]
    assert [k for k, v in kinds.items() if v == "milestone"] == ["release"]
    st = d.statuses()
    assert sorted(k for k, v in st.items() if v == "done") == ["scope", "standards"]
    assert [k for k, v in st.items() if v == "active"] == ["hazards"]
    assert sorted(k for k, v in st.items() if v == "blocked") == ["metrics", "risk"]
    assert [k for k, v in st.items() if v == "late"] == ["supplier"]
    assert [e.kind for e in d.edges].count("informs") == 1 and [e.kind for e in d.edges].count("enables") == 2
    assert [e.label for e in d.edges if e.label] == ["failure rates"]
    layout(d)
    assert d.issues == []


def test_demo_is_competent_under_real_ocr(ocr_engine, tmp_path):
    if not ocr_engine:
        pytest.skip("Windows OCR engine unavailable")
    res = build(chain_demo(), str(tmp_path), formats=("png",), ocr=True)
    report = res["ocr"]
    assert report.available and len(report.lines) > 30
    assert report.competent, report.verdict
    assert res["issues"] == []
