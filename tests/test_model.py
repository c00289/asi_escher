import pytest

from asi_escher import Diagram
from asi_escher.examples import EXAMPLES


def test_unknown_diagram_kind():
    with pytest.raises(ValueError, match="diagram kind"):
        Diagram("x", "sequence")


def test_bad_direction():
    with pytest.raises(ValueError, match="direction"):
        Diagram("x", direction="RL")


def test_unknown_node_kind():
    d = Diagram("x")
    with pytest.raises(ValueError, match="node kind"):
        d.node("a", "A", "hexagon")


def test_duplicate_node_id():
    d = Diagram("x")
    d.action("a")
    with pytest.raises(ValueError, match="duplicate node id"):
        d.action("a")


def test_duplicate_lane_id():
    d = Diagram("x")
    d.lane("l1")
    with pytest.raises(ValueError, match="duplicate lane id"):
        d.lane("l1")


def test_edge_to_unknown_node():
    d = Diagram("x")
    d.action("a")
    with pytest.raises(KeyError):
        d.edge("a", "b")


def test_unknown_edge_kind_and_style():
    d = Diagram("x")
    d.action("a")
    d.action("b")
    with pytest.raises(ValueError, match="edge kind"):
        d.edge("a", "b", kind="teleport")
    with pytest.raises(ValueError, match="edge style"):
        d.edge("a", "b", style="wavy")


def test_label_defaults_to_id():
    d = Diagram("x")
    assert d.action("Do thing").label == "Do thing"
    assert d.action("b", "").label == ""


def test_chain_with_labels():
    d = Diagram("x")
    for i in "abc":
        d.action(i)
    d.chain("a", "b", "c", labels=["first"])
    assert [(e.src, e.dst, e.label) for e in d.edges] == [("a", "b", "first"), ("b", "c", "")]


def test_validate_requires_lanes_for_every_node():
    d = Diagram("x")
    d.lane("l1")
    d.action("a", lane="l1")
    d.action("b")
    with pytest.raises(ValueError, match="no lane"):
        d.validate()
    d.nodes["b"].lane = "nope"
    with pytest.raises(ValueError, match="unknown lane"):
        d.validate()


def test_block_and_requirement_compartments():
    d = Diagram("x", "bdd")
    b = d.block("b", "Block", values=["v : int"], parts=["p"], operations=["op()"])
    assert [t for t, _ in b.compartments] == ["parts", "values", "operations"]
    r = d.requirement("r", "Req", "R-1", "Shall do it.")
    assert r.stereotype == "requirement"
    assert r.compartments[0][1] == ['id = "R-1"', 'text = "Shall do it."']


@pytest.mark.parametrize("name,builder", EXAMPLES, ids=[n for n, _ in EXAMPLES])
def test_dict_roundtrip(name, builder):
    d = builder()
    data = d.to_dict()
    d2 = Diagram.from_dict(data)
    assert d2.to_dict() == data
    assert [n.id for n in d2.real_nodes()] == [n.id for n in d.real_nodes()]
    assert [(e.src, e.dst, e.kind) for e in d2.edges] == [(e.src, e.dst, e.kind) for e in d.edges]


def test_from_dict_errors():
    with pytest.raises(ValueError, match="title"):
        Diagram.from_dict({})
    with pytest.raises(ValueError, match="'id'"):
        Diagram.from_dict({"title": "t", "nodes": [{"label": "x"}]})
    with pytest.raises(ValueError, match="src"):
        Diagram.from_dict({"title": "t", "nodes": [{"id": "a"}], "edges": [{"src": "a"}]})
