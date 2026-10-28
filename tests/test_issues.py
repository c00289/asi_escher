import warnings

import pytest

from asi_escher import Diagram, LayoutIssue, LayoutWarning, build, layout
from asi_escher.layout import _check_edge_crossings


def test_examples_report_no_issues(example):
    with warnings.catch_warnings():
        warnings.simplefilter("error", LayoutWarning)
        layout(example)
    assert example.issues == []


def _crowded_lanes():
    """A tall back-edge label in a narrow lane that spills onto the next lane,
    where every row is occupied, so no spot along the channel is free."""
    d = Diagram("crowded", "activity")
    d.lane("l1", "One")
    d.lane("l2", "Two")
    d.action("a", "A", lane="l1")
    d.action("b", "B", lane="l1")
    d.action("c", "C", lane="l1")
    d.chain("a", "b", "c")
    d.edge("c", "a", "line one\nline two\nline three\nline four")
    d.action("x", "X", lane="l2")
    d.action("y", "Y", lane="l2")
    d.action("z", "Z", lane="l2")
    d.chain("x", "y", "z")
    return d


def test_label_overlap_is_reported_and_warned():
    d = _crowded_lanes()
    with pytest.warns(LayoutWarning, match="crowded"):
        layout(d)
    kinds = {i.kind for i in d.issues}
    assert "label_overlap" in kinds
    issue = next(i for i in d.issues if i.kind == "label_overlap")
    assert issue.edge == ("c", "a")
    assert "overlaps" in issue.message
    back = next(e for e in d.edges if e.src == "c" and e.dst == "a")
    assert back.label_pos is not None                # the label is still drawn


def test_issues_reset_on_relayout():
    d = _crowded_lanes()
    with pytest.warns(LayoutWarning):
        layout(d)
    n = len(d.issues)
    with pytest.warns(LayoutWarning):
        layout(d)
    assert len(d.issues) == n


def test_edge_through_node_detection():
    d = Diagram("x")
    d.action("a", "A")
    d.action("b", "B")
    d.action("c", "C")
    d.edge("a", "b")
    layout(d)
    assert d.issues == []
    # drag the unrelated node onto the a->b edge and re-check
    (x0, y0), (x1, y1) = d.edges[0].points[0], d.edges[0].points[-1]
    d.nodes["c"].x, d.nodes["c"].y = (x0 + x1) / 2, (y0 + y1) / 2
    _check_edge_crossings(d)
    assert [i.kind for i in d.issues] == ["edge_through_node"]
    assert d.issues[0].node == "c" and d.issues[0].edge == ("a", "b")


def test_build_returns_issues(tmp_path):
    with pytest.warns(LayoutWarning):
        res = build(_crowded_lanes(), str(tmp_path), formats=("dot",))
    assert res["issues"] and all(isinstance(i, LayoutIssue) for i in res["issues"])


def test_cli_prints_issues_to_stderr(tmp_path, capsys):
    import json

    from asi_escher.cli import main

    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(_crowded_lanes().to_dict()), encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", LayoutWarning)      # CLI must not let the warning through
        assert main(["build", str(spec), "-o", str(tmp_path), "--formats", "dot"]) == 0
    err = capsys.readouterr().err
    assert "warning:" in err and "overlaps" in err
