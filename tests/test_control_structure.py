"""The ``control_structure`` kind: builder, model, layout rules, renderer, DOT and Mermaid."""
import io

import pytest

from asi_escher import (
    CONTROL_EDGE_KINDS,
    CONTROL_NODE_KINDS,
    Diagram,
    LayoutOptions,
    layout,
    render,
    to_dot,
    to_mermaid,
)
from asi_escher.examples import control_structure_demo
from asi_escher.metrics import control_sections
from asi_escher.ocr import expected_labels


def _pair():
    d = Diagram("Pair", "control_structure")
    d.controller("top", "Top Controller", responsibility="Commands the process.",
                 algorithms=[("T1", "Decide"), ("T2", "Watch")],
                 process_model=("Top model", ["State (updated by FB-01)"]))
    d.controller("low", "Low Process", kind="controlled_process")
    d.control_action("top", "low", ["CA-01 Command", "CA-02 Other command"])
    d.feedback("low", "top", ["FB-01 State"])
    return d


def test_builder_fills_sections_and_signals():
    d = _pair()
    top = d.nodes["top"]
    assert top.kind == "controller" and top.responsibility == "Commands the process."
    assert top.algorithms == [("T1", "Decide"), ("T2", "Watch")]
    assert top.process_model == ("Top model", ["State (updated by FB-01)"])
    assert [k for k, _ in control_sections(top)] == ["responsibility", "algorithms", "process_model"]
    assert control_sections(d.nodes["low"]) == []
    ca, fb = d.edges
    assert ca.kind == "control_action" and ca.signals == ["CA-01 Command", "CA-02 Other command"]
    assert ca.label == "CA-01 Command\nCA-02 Other command"       # one signal per label line
    assert fb.kind == "feedback" and fb.label == "FB-01 State"
    assert d.control_action("low", "top", "CA-03 Single").signals == ["CA-03 Single"]


def test_kinds_are_registered():
    assert CONTROL_NODE_KINDS == {"controller", "human_controller", "controlled_process", "environment",
                                  "sensor", "actuator", "external_system"}
    assert CONTROL_EDGE_KINDS == {"control_action", "feedback"}
    d = Diagram("k", "control_structure")
    for kind in sorted(CONTROL_NODE_KINDS):
        d.controller(kind, kind.replace("_", " ").title(), kind=kind)
    assert len(d.real_nodes()) == len(CONTROL_NODE_KINDS)


def test_builder_rejects_bad_input():
    d = Diagram("k", "control_structure")
    with pytest.raises(ValueError, match="controller kind"):
        d.controller("x", kind="action")
    d.controller("c", "C")
    with pytest.raises(KeyError, match="attached to unknown"):
        d.note("n", "text", attached_to="nope")
    d.note("n", "text", attached_to="c")
    d.nodes["n"].attached_to = "gone"
    with pytest.raises(ValueError, match="attached to unknown"):
        d.validate()


def test_dict_roundtrip_keeps_sections_and_signals():
    d = control_structure_demo()
    data = d.to_dict()
    op = next(n for n in data["nodes"] if n["id"] == "operator")
    assert op["kind"] == "human_controller" and op["algorithms"][0] == ["O1", "Mission start / stop decision"]
    assert op["process_model"][0] == "Operator process model"
    note = next(n for n in data["nodes"] if n["id"] == "note_vehicle")
    assert note["attached_to"] == "vehicle"
    e = data["edges"][0]
    assert e["kind"] == "control_action" and e["signals"] == ["CA-01 Mission Start", "CA-02 Mission Stop"]
    assert "label" not in e                                # the label is the join of the signals
    d2 = Diagram.from_dict(data)
    assert d2.to_dict() == data
    assert d2.edges[0].label == d.edges[0].label
    assert d2.nodes["operator"].process_model == d.nodes["operator"].process_model


def test_pair_of_arrows_keeps_distinct_x_control_left_feedback_right():
    d = _pair()
    layout(d)
    ca, fb = d.edges
    top, low = d.nodes["top"], d.nodes["low"]
    assert top.y < low.y                                   # hierarchy top-down
    assert fb.back and not ca.back
    # the control action leaves the top box downwards, the feedback arrives from below
    assert ca.points[0][1] == pytest.approx(top.bottom) and ca.points[-1][1] == pytest.approx(low.top)
    assert fb.points[0][1] == pytest.approx(low.top) and fb.points[-1][1] == pytest.approx(top.bottom)
    assert fb.points[-1][1] < fb.points[0][1]              # feedback points up
    xs_ca = {round(x) for x, _ in ca.points}
    xs_fb = {round(x) for x, _ in fb.points}
    assert xs_ca.isdisjoint(xs_fb)                         # the two arrows never share a vertical
    assert max(xs_ca) < min(xs_fb)                         # control action left, feedback right
    assert ca.label_pos[0] < fb.label_pos[0]
    assert d.issues == []


def test_demo_hierarchy_is_top_down_and_pairs_never_overlap():
    d = control_structure_demo()
    layout(d)
    n = d.nodes
    assert n["operator"].y < n["supervisor"].y < n["vehicle"].y < n["machine"].y < n["environment"].y
    assert n["operator"].y < n["safety"].y < n["machine"].y                   # the stop path
    assert n["vehicle"].y < n["perception"].y < n["environment"].y            # a sensor sits below its controller
    pairs = {}
    for e in d.edges:
        pairs.setdefault(frozenset((e.src, e.dst)), []).append(e)
    both = [es for es in pairs.values() if len(es) == 2]
    assert len(both) >= 4
    for es in both:
        ca = next(e for e in es if e.kind == "control_action")
        fb = next(e for e in es if e.kind == "feedback")
        upper = ca.src
        x_ca = ca.points[0][0]                                       # where the control action leaves the upper box
        x_fb = fb.points[-1][0]                                      # where the feedback arrives at it
        assert x_ca < x_fb, (upper, x_ca, x_fb)
        assert {round(x) for x, _ in ca.points}.isdisjoint({round(x) for x, _ in fb.points})
    assert d.issues == []


def test_note_floats_beside_its_box_and_off_the_arrows():
    d = control_structure_demo()
    layout(d)
    note, host = d.nodes["note_vehicle"], d.nodes["vehicle"]
    assert note.top == pytest.approx(host.top)
    assert note.right < host.left or note.left > host.right
    for other in d.real_nodes():
        if other.id != note.id:
            assert note.right <= other.left or other.right <= note.left or \
                note.bottom <= other.top or other.bottom <= note.top
    assert [n.id for n in d.real_nodes()] == [n["id"] for n in d.to_dict()["nodes"]]   # author order kept


def test_default_layout_options_depend_on_kind():
    assert LayoutOptions.for_kind("control_structure").nodesep > LayoutOptions.for_kind("activity").nodesep
    assert LayoutOptions.for_kind("activity").ranksep == LayoutOptions().ranksep


def test_render_png_and_svg_show_sections_and_signals():
    d = layout(control_structure_demo())
    png, svg = io.BytesIO(), io.BytesIO()
    render(d, png=png, svg=svg)
    assert png.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
    text = svg.getvalue().decode("utf-8").lower()
    assert "#fff3e0" in text and "#ef6c00" in text         # the orange algorithms section
    assert "#e3f2fd" in text and "#1565c0" in text         # the blue process model, blue feedback
    assert "#c62828" in text                               # red control actions
    for signal in ("CA-01 Mission Start", "FB-12 Drive Inhibit State", "CA-31 Drive Inhibit"):
        assert signal.lower() in text
    assert "o1 mission start / stop decision" in text
    assert "operator process model" in text


def test_dot_export_of_the_kind():
    d = control_structure_demo()
    dot = to_dot(d)
    assert 'peripheries=2' in dot                           # controlled process: double border
    assert 'style="dashed,filled"' in dot                   # environment
    assert 'style="rounded,filled"' in dot                  # human controller
    assert 'BGCOLOR="#FFF3E0"' in dot and 'BGCOLOR="#E3F2FD"' in dot
    assert 'color="#C62828"' in dot and 'color="#1565C0"' in dot
    assert 'label="CA-01 Mission Start\\nCA-02 Mission Stop"' in dot
    assert '"machine" -> "vehicle" [label="FB-10 Machine State\\nFB-12 Drive Inhibit State"' in dot
    assert "constraint=false" in dot                        # feedback does not rank


def test_mermaid_export_of_the_kind():
    d = control_structure_demo()
    mmd = to_mermaid(d)
    assert mmd.startswith("---\ntitle: Demo Loader Control Structure\n---\nflowchart TD")
    assert "<b>Remote Operator</b><br/>Starts and stops the mission" in mmd
    assert "<i>Algorithms</i><br/>O1 Mission start / stop decision" in mmd
    assert "linkStyle 0 stroke:#C62828,color:#C62828" in mmd
    assert "linkStyle 1 stroke:#1565C0,color:#1565C0" in mmd
    assert 'operator -->|"CA-01 Mission Start<br/>CA-02 Mission Stop"| supervisor' in mmd
    assert "stroke-dasharray:6 3" in mmd                   # the environment box


def test_expected_labels_of_a_control_structure():
    labels = expected_labels(_pair())
    assert labels == ["Top Controller", "T1", "T2", "Top model", "Low Process", "CA-01", "CA-02", "FB-01"]
