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


# ---------------------------------------------------------------- tiers ----
def _peers():
    """Two operators side by side (all names invented): the yard operator asks
    the desk operator for a hold (a lateral request) and otherwise commands
    the task executor and the rig, both of them under the desk operator's
    planner."""
    d = Diagram("Peers", "control_structure")
    d.controller("room", "Desk Operator", kind="human_controller")
    d.controller("field", "Yard Operator", kind="human_controller")
    d.controller("source", "Plan Feed", kind="external_system")
    d.controller("supervisor", "Task Planner")
    d.controller("stop", "Halt Path")
    d.controller("vehicle", "Task Executor")
    d.controller("machine", "Rig", kind="controlled_process")
    d.controller("site", "Yard", kind="environment")
    d.control_action("field", "room", ["CA-70 Hold request"])
    d.feedback("room", "field", ["FB-70 Hold taken"])
    d.control_action("field", "vehicle", ["CA-71 Yard halt"])
    d.control_action("field", "machine", ["CA-72 Rig brake"])
    d.control_action("source", "supervisor", ["CA-73 Plan data"])
    d.control_action("room", "supervisor", ["CA-74 Task order"])
    d.control_action("room", "stop", ["CA-75 Halt order"])
    d.control_action("supervisor", "vehicle", ["CA-76 Task command"])
    d.control_action("stop", "vehicle", ["CA-77 Halt activation"])
    d.control_action("vehicle", "machine", ["CA-78 Drive demand"])
    d.feedback("machine", "vehicle", ["FB-78 Rig state"])
    d.feedback("vehicle", "supervisor", ["FB-76 Task state"])
    d.feedback("site", "vehicle", ["FB-80 Scene cue"])
    d.feedback("site", "room", ["FB-81 Scene cue"])
    return d


def test_peers_share_the_top_layer():
    d = Diagram("Two peers", "control_structure")
    d.controller("a", "Operator A", kind="human_controller")
    d.controller("b", "Operator B", kind="human_controller")
    d.controller("c", "Controller")
    d.control_action("a", "c", ["CA-01 Go"])
    d.control_action("b", "c", ["CA-02 Stop"])
    layout(d)
    n = d.nodes
    assert n["a"].layer == n["b"].layer == 0 and n["a"].y == pytest.approx(n["b"].y)
    assert n["c"].layer == 1 and n["c"].y > n["a"].y
    assert d.issues == []


def test_box_reached_from_two_layers_sits_below_both():
    d = Diagram("Deep", "control_structure")
    d.controller("top", "Top")
    d.controller("mid", "Middle")
    d.controller("low", "Low")
    d.control_action("top", "mid", ["CA-01 A"])
    d.control_action("mid", "low", ["CA-02 B"])
    d.control_action("top", "low", ["CA-03 C"])
    layout(d)
    assert [d.nodes[k].layer for k in ("top", "mid", "low")] == [0, 1, 2]
    # commanding the receiver's own subordinate is a superior's bypass; only
    # a sender reaching past the receiver's subordinates is its peer
    d = Diagram("Deeper", "control_structure")
    for k in ("top", "mid", "low", "proc"):
        d.controller(k, k.title())
    d.control_action("top", "mid", ["CA-01 A"])
    d.control_action("mid", "low", ["CA-02 B"])
    d.control_action("low", "proc", ["CA-03 C"])
    d.control_action("top", "proc", ["CA-04 D"])
    layout(d)
    assert [d.nodes[k].layer for k in ("top", "mid", "low", "proc")] == [0, 0, 1, 2]


def test_lateral_request_keeps_peers_level_and_runs_sideways():
    d = _peers()
    layout(d)
    n = d.nodes
    tiers = {}
    for k in ("room", "field", "source", "supervisor", "stop", "vehicle", "machine", "site"):
        tiers.setdefault(n[k].layer, set()).add(k)
    assert tiers == {0: {"room", "field", "source"}, 1: {"supervisor", "stop"}, 2: {"vehicle"},
                     3: {"machine", "site"}}
    assert n["room"].y == pytest.approx(n["field"].y)
    request = next(e for e in d.edges if (e.src, e.dst) == ("field", "room"))
    answer = next(e for e in d.edges if (e.src, e.dst) == ("room", "field"))
    left, right = sorted((n["room"], n["field"]), key=lambda b: b.x)
    for e in (request, answer):
        assert len(e.points) == 2 and e.points[0][1] == pytest.approx(e.points[1][1])   # horizontal
        xs = sorted(x for x, _ in e.points)
        assert xs[0] == pytest.approx(left.right) and xs[1] == pytest.approx(right.left)
    assert request.points[0][1] < answer.points[0][1]                 # the request above its answer
    assert request.label_pos[1] < request.points[0][1] < answer.points[0][1] < answer.label_pos[1]
    assert n["machine"].y == pytest.approx(n["site"].y)               # the bottom tier
    assert d.width >= 0.8 * d.height
    assert d.issues == []


def test_feedback_never_moves_a_box():
    d = _peers()
    layout(d)
    layers = {k: n.layer for k, n in d.nodes.items() if n.kind != "dummy"}
    quiet = _peers()
    quiet.edges = [e for e in quiet.edges if e.kind != "feedback"]
    layout(quiet)
    for k, n in quiet.nodes.items():
        if n.kind != "dummy" and k != "site":
            assert n.layer == layers[k], k                         # the hierarchy alone decides
    # a box that only reports sits below the boxes it reports to, one that
    # only listens just above the nearest box it hears from
    demo = control_structure_demo()
    layout(demo)
    n = demo.nodes
    assert n["perception"].layer == n["vehicle"].layer + 1
    assert n["fleet"].layer == n["vehicle"].layer - 1 and n["fleet"].layer > n["operator"].layer
    assert n["environment"].layer == max(b.layer for b in demo.real_nodes())


def test_demo_is_wide_and_its_labels_never_overlap():
    d = control_structure_demo()
    layout(d)
    assert d.width >= 0.8 * d.height
    assert [i for i in d.issues if i.kind == "label_overlap"] == []
    assert d.issues == []
    assert len({n.layer for n in d.real_nodes() if n.kind != "note"}) == 5


def test_lateral_edge_gets_room_for_its_label():
    d = Diagram("Wide request", "control_structure")
    d.controller("a", "A", kind="human_controller")
    d.controller("b", "B", kind="human_controller")
    d.controller("c", "C")
    d.controller("p", "Process", kind="controlled_process")
    d.control_action("a", "b", ["CA-01 A very long request name that needs a wide channel between the peers"])
    d.control_action("a", "p", ["CA-02 Go"])
    d.control_action("b", "c", ["CA-03 Go"])
    d.control_action("c", "p", ["CA-04 Go"])
    layout(d)
    e = d.edges[0]
    assert d.nodes["a"].layer == d.nodes["b"].layer
    assert abs(e.points[1][0] - e.points[0][0]) > LayoutOptions.for_kind("control_structure").nodesep
    assert d.issues == []
