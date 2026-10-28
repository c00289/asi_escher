import io
import json
import os

import matplotlib
import pytest

from asi_escher import Diagram, build, layout, render
from asi_escher.cli import main
from asi_escher.examples import EXAMPLES
from asi_escher.pipeline import slug


def _small():
    d = Diagram("Tiny Flow", "flowchart")
    d.start()
    d.action("a", "Do it")
    d.end()
    d.chain("start", "a", "end")
    return d


def test_render_returns_figure_and_writes_bytes():
    d = layout(_small())
    png, svg = io.BytesIO(), io.BytesIO()
    fig = render(d, png=png, svg=svg)
    assert fig.get_size_inches()[0] * 100 == pytest.approx(d.width, abs=1)
    assert png.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
    assert b"<svg" in svg.getvalue() and b"Do it" in svg.getvalue()


def test_render_leaves_global_matplotlib_state_alone():
    before = dict(matplotlib.rcParams)
    render(layout(_small()), png=io.BytesIO())
    assert dict(matplotlib.rcParams) == before


def test_render_theme_override():
    svg = io.BytesIO()
    render(layout(_small()), svg=svg, theme={"action": ("#123456", "#654321")})
    assert b"#123456" in svg.getvalue()


def test_slug():
    assert slug("Autonomous Load Cycle") == "autonomous_load_cycle"
    assert slug("  ÄÖ ") == "diagram"
    assert slug("ISO 25119 / 13849") == "iso_25119_13849"


def test_build_writes_all_formats(tmp_path):
    res = build(_small(), str(tmp_path))
    for fmt in ("png", "svg", "dot", "mmd"):
        assert os.path.getsize(res[fmt]) > 0
        assert res[fmt].endswith(f"tiny_flow.{fmt}")
    assert res["nodes"] == 3 and res["edges"] == 2
    assert res["size"][0] > 0


def test_build_subset_of_formats(tmp_path):
    res = build(_small(), str(tmp_path), name="x", formats=("dot",))
    assert set(os.listdir(tmp_path)) == {"x.dot"}
    assert "png" not in res
    with pytest.raises(ValueError, match="unknown formats"):
        build(_small(), str(tmp_path), formats=("pdf",))


def test_cli_list(capsys):
    assert main(["list"]) == 0
    assert capsys.readouterr().out.split() == [n for n, _ in EXAMPLES]


def test_cli_example(tmp_path, capsys):
    assert main(["example", "state_estop_channel", "-o", str(tmp_path), "--formats", "svg,mmd"]) == 0
    assert set(os.listdir(tmp_path)) == {"state_estop_channel.svg", "state_estop_channel.mmd"}
    assert main(["example", "nope", "-o", str(tmp_path)]) == 2


def test_cli_build_spec(tmp_path, capsys):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(_small().to_dict()), encoding="utf-8")
    assert main(["build", str(spec), "-o", str(tmp_path / "out"), "--name", "mine", "--nodesep", "50"]) == 0
    assert set(os.listdir(tmp_path / "out")) == {"mine.png", "mine.svg", "mine.dot", "mine.mmd"}
    assert "3 nodes" in capsys.readouterr().out


def test_cli_build_bad_spec(tmp_path, capsys):
    spec = tmp_path / "bad.json"
    spec.write_text('{"title": "t", "nodes": [{"id": "a", "kind": "blob"}]}', encoding="utf-8")
    assert main(["build", str(spec), "-o", str(tmp_path)]) == 1
    assert "node kind" in capsys.readouterr().err
    assert main(["build", str(tmp_path / "missing.json")]) == 1


def test_cli_gallery(tmp_path):
    assert main(["gallery", "-o", str(tmp_path), "--dpi", "40"]) == 0
    assert (tmp_path / "index.html").exists()
    for name, _ in EXAMPLES:
        assert (tmp_path / f"{name}.png").exists()
