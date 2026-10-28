import pytest

from asi_escher import Diagram, layout, to_dot, to_mermaid
from asi_escher.export import _ident, _mid


def test_dot_structure(example):
    dot = to_dot(example)
    assert dot.startswith("digraph ")
    assert dot.count("{") == dot.count("}")
    for n in example.real_nodes():
        assert f'"{n.id}"' in dot
    for e in example.edges:
        assert f'"{e.src}" -> "{e.dst}"' in dot
    if example.lanes:
        assert dot.count("subgraph cluster_") == len(example.lanes)


def test_dot_escapes_quotes_and_html():
    d = Diagram('Say "hi"', "bdd")
    d.block("b", 'A <b> & "c"', values=["x < 1"])
    d.action("a", 'label "q"')
    d.edge("b", "a", 'e "f"')
    dot = to_dot(d)
    assert 'digraph "Say \\"hi\\""' in dot
    assert "&lt;b&gt; &amp;" in dot
    assert 'label="label \\"q\\""' in dot


@pytest.mark.parametrize("kind,header", [
    ("activity", "flowchart TD"), ("flowchart", "flowchart TD"), ("ibd", "flowchart TD"),
    ("state", "stateDiagram-v2"), ("bdd", "classDiagram"), ("req", "classDiagram"),
])
def test_mermaid_picks_diagram_type(kind, header):
    d = Diagram("t", kind)
    d.node("a", "A", "state" if kind == "state" else "block" if kind in ("bdd", "req") else "action")
    assert header in to_mermaid(d)


def test_mermaid_examples_mention_every_node(example):
    mmd = to_mermaid(example)
    assert mmd.startswith("---\ntitle:")
    for n in example.real_nodes():
        if example.kind == "state" and n.kind in ("start", "end"):
            assert "[*]" in mmd
        else:
            assert _mid(n.id) in mmd


def test_mermaid_identifiers_are_safe():
    assert _mid("end") == "end_"
    assert _mid("Start") == "Start_"
    assert _mid("my node") == "my_node"
    assert _ident("1st") == "n_1st"
    assert _ident("") == "n_"


def test_export_uses_author_labels_not_wrapped_ones():
    d = Diagram("t")
    d.action("a", "a fairly long label that the renderer will wrap onto several lines")
    layout(d)
    assert len(d.nodes["a"].lines) > 1
    assert "\\n" not in to_dot(d)
    assert "<br/>" not in to_mermaid(d)


def test_requirement_edges_carry_stereotypes():
    d = Diagram("r", "req")
    d.requirement("r1", "R", "R-1", "t")
    d.block("b")
    d.edge("r1", "b", kind="satisfy")
    d.edge("r1", "b", kind="derive")
    dot, mmd = to_dot(d), to_mermaid(d)
    assert "«satisfy»" in dot and "«deriveReqt»" in dot
    assert "«satisfy»" in mmd and "«deriveReqt»" in mmd
