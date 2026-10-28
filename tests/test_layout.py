import itertools

from asi_escher import Diagram, LayoutOptions, layout
from asi_escher.metrics import edge_label


def _rects_overlap(a, b, slack=0.5):
    return not (a.right <= b.left + slack or b.right <= a.left + slack
                or a.bottom <= b.top + slack or b.bottom <= a.top + slack)


def _segment_crosses_rect(p, q, n, slack=1.0):
    """True if the axis-aligned segment p-q passes through node n's interior."""
    (x0, y0), (x1, y1) = p, q
    if abs(x0 - x1) < 0.5:                      # vertical
        if not (n.left + slack < x0 < n.right - slack):
            return False
        lo, hi = min(y0, y1), max(y0, y1)
        return lo < n.bottom - slack and hi > n.top + slack
    if abs(y0 - y1) < 0.5:                      # horizontal
        if not (n.top + slack < y0 < n.bottom - slack):
            return False
        lo, hi = min(x0, x1), max(x0, x1)
        return lo < n.right - slack and hi > n.left + slack
    return False


def test_examples_have_no_node_overlap(example):
    layout(example)
    nodes = example.real_nodes()
    for a, b in itertools.combinations(nodes, 2):
        assert not _rects_overlap(a, b), f"{a.id} overlaps {b.id}"


def test_examples_fit_canvas(example):
    layout(example)
    W, H = example.width, example.height
    assert W > 0 and H > 0
    for n in example.real_nodes():
        assert 0 <= n.left and n.right <= W, n.id
        assert 0 <= n.top and n.bottom <= H, n.id
    for e in example.edges:
        assert len(e.points) >= 2, (e.src, e.dst)
        for x, y in e.points:
            assert 0 <= x <= W and 0 <= y <= H, (e.src, e.dst)
        if edge_label(e):
            assert e.label_pos is not None
            x, y = e.label_pos
            assert 0 <= x <= W and 0 <= y <= H


def test_examples_edges_are_orthogonal(example):
    layout(example)
    for e in example.edges:
        for p, q in zip(e.points, e.points[1:], strict=False):
            assert abs(p[0] - q[0]) < 0.5 or abs(p[1] - q[1]) < 0.5, (e.src, e.dst, p, q)


def test_examples_edges_do_not_cross_unrelated_nodes(example):
    layout(example)
    for e in example.edges:
        if e.back or e.src == e.dst:
            continue
        others = [n for n in example.real_nodes() if n.id not in (e.src, e.dst)]
        for p, q in zip(e.points, e.points[1:], strict=False):
            for n in others:
                assert not _segment_crosses_rect(p, q, n), f"edge {e.src}->{e.dst} crosses {n.id}"


def test_examples_labels_are_not_mutated(example):
    before = {n.id: n.label for n in example.real_nodes()}
    layout(example)
    assert {n.id: n.label for n in example.real_nodes()} == before
    for n in example.real_nodes():
        if n.kind not in ("start", "end", "flowfinal", "merge", "fork", "join"):
            assert "".join(n.text.split()) == "".join(n.label.split())


def test_layout_is_deterministic_and_repeatable(example):
    layout(example)
    first = {n.id: (n.x, n.y) for n in example.real_nodes()}
    size = (example.width, example.height)
    dummies = sum(1 for n in example.nodes.values() if n.kind == "dummy")
    layout(example)
    assert {n.id: (n.x, n.y) for n in example.real_nodes()} == first
    assert (example.width, example.height) == size
    assert sum(1 for n in example.nodes.values() if n.kind == "dummy") == dummies


def test_empty_diagram():
    d = Diagram("empty")
    layout(d)
    assert d.width > 0 and d.height > 0


def test_single_node():
    d = Diagram("one")
    d.action("a", "Only")
    layout(d)
    assert d.nodes["a"].w > 0 and d.width > d.nodes["a"].w


def test_cycle_and_self_loop():
    d = Diagram("loop")
    d.action("a")
    d.action("b")
    d.edge("a", "b")
    d.edge("b", "a", "again")
    d.edge("a", "a", "spin")
    layout(d)
    backs = [e for e in d.edges if e.back]
    assert {(e.src, e.dst) for e in backs} == {("b", "a"), ("a", "a")}
    assert d.nodes["a"].layer < d.nodes["b"].layer
    assert all(e.label_pos for e in backs)


def test_disconnected_components_are_packed_side_by_side():
    d = Diagram("two")
    for i in range(2):
        d.action(f"a{i}")
        d.action(f"b{i}")
        d.edge(f"a{i}", f"b{i}")
    layout(d)
    gap = d.nodes["a1"].left - d.nodes["a0"].right
    assert 0 < gap < 200


def test_lr_transposes():
    tb = Diagram("x", direction="TB")
    lr = Diagram("x", direction="LR")
    for d in (tb, lr):
        d.action("a", "first")
        d.action("b", "second")
        d.edge("a", "b", "go")
        layout(d)
    assert tb.nodes["b"].y > tb.nodes["a"].y
    assert lr.nodes["b"].x > lr.nodes["a"].x
    assert abs(lr.nodes["a"].y - lr.nodes["b"].y) < 1


def test_long_chain_does_not_hit_recursion_limit():
    d = Diagram("chain")
    n = 3000
    for i in range(n):
        d.action(f"n{i}", "x")
    for i in range(n - 1):
        d.edge(f"n{i}", f"n{i + 1}")
    layout(d)
    assert d.nodes[f"n{n - 1}"].layer == n - 1


def test_layout_options_change_spacing():
    def make():
        d = Diagram("x")
        d.action("a")
        d.action("b")
        d.edge("a", "b")
        return d

    tight, loose = make(), make()
    layout(tight, LayoutOptions(ranksep=20))
    layout(loose, LayoutOptions(ranksep=200))
    assert loose.height > tight.height + 150
