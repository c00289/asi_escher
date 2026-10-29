import io
import json
import os

import matplotlib
import pytest

from asi_escher import ALL_FORMATS, DEFAULT_FORMATS, FORMATS, Diagram, build, layout, render
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


def test_render_footer_names_the_drawio_file_unless_switched_off():
    d = layout(_small())
    svg = io.BytesIO()
    render(d, svg=svg)
    assert b"layout shared with tiny_flow.drawio" in svg.getvalue() and b"asi_escher" in svg.getvalue()
    svg = io.BytesIO()
    render(d, svg=svg, name="other")
    assert b"layout shared with other.drawio" in svg.getvalue()
    svg = io.BytesIO()
    render(d, svg=svg, provenance=False)
    assert b"layout shared with" not in svg.getvalue()


def test_render_theme_override():
    svg = io.BytesIO()
    render(layout(_small()), svg=svg, theme={"action": ("#123456", "#654321")})
    assert b"#123456" in svg.getvalue()


def test_slug():
    assert slug("Autonomous Load Cycle") == "autonomous_load_cycle"
    assert slug("  ÄÖ ") == "diagram"
    assert slug("ISO 25119 / 13849") == "iso_25119_13849"


def test_format_sets():
    assert FORMATS == ("drawio", "png", "svg")
    assert DEFAULT_FORMATS == ("drawio", "png")
    assert ALL_FORMATS == ("drawio", "png", "svg", "dot", "mmd")


def test_build_defaults_to_drawio_and_png(tmp_path):
    res = build(_small(), str(tmp_path))
    assert set(os.listdir(tmp_path)) == {"tiny_flow.drawio", "tiny_flow.png"}
    assert res["drawio"].endswith("tiny_flow.drawio") and "svg" not in res
    with open(res["drawio"], encoding="utf-8") as f:
        text = f.read()
    assert 'compressed="false"' in text and "tiny_flow.png and tiny_flow.svg" in text


def test_build_writes_all_formats(tmp_path):
    res = build(_small(), str(tmp_path), formats=ALL_FORMATS)
    for fmt in ("drawio", "png", "svg", "dot", "mmd"):
        assert os.path.getsize(res[fmt]) > 0
        assert res[fmt].endswith(f"tiny_flow.{fmt}")
    assert res["nodes"] == 3 and res["edges"] == 2
    assert res["size"][0] > 0
    res = build(_small(), str(tmp_path), name="plain", formats=("svg", "drawio"), provenance=False)
    with open(res["svg"], encoding="utf-8") as f:
        assert "layout shared with" not in f.read()
    with open(res["drawio"], encoding="utf-8") as f:
        assert "<!--" not in f.read()


def test_build_subset_of_formats(tmp_path):
    res = build(_small(), str(tmp_path), name="x", formats=("dot",))
    assert set(os.listdir(tmp_path)) == {"x.dot"}
    assert "png" not in res
    with pytest.raises(ValueError, match="unknown formats"):
        build(_small(), str(tmp_path), formats=("pdf",))


def test_cli_list(capsys):
    assert main(["list"]) == 0
    assert capsys.readouterr().out.split() == [n for n, _ in EXAMPLES]


def test_cli_example(tmp_path):
    assert main(["example", "state_estop_channel", "-o", str(tmp_path), "--formats", "svg,mmd"]) == 0
    assert set(os.listdir(tmp_path)) == {"state_estop_channel.svg", "state_estop_channel.mmd"}
    assert main(["example", "nope", "-o", str(tmp_path)]) == 2


def test_cli_build_spec(tmp_path, capsys):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(_small().to_dict()), encoding="utf-8")
    assert main(["build", str(spec), "-o", str(tmp_path / "out"), "--name", "mine", "--nodesep", "50"]) == 0
    assert set(os.listdir(tmp_path / "out")) == {"mine.drawio", "mine.png", "mine.svg", "mine.dot", "mine.mmd"}
    assert "3 nodes" in capsys.readouterr().out


def test_cli_export_formats_and_defaults(tmp_path, capsys):
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(_small().to_dict()), encoding="utf-8")
    out = tmp_path / "a"
    assert main(["export", str(spec), "--out", str(out)]) == 0
    assert set(os.listdir(out)) == {"tiny_flow.drawio", "tiny_flow.png"}
    assert "tiny_flow.drawio" in capsys.readouterr().out
    out = tmp_path / "b"
    assert main(["export", str(spec), "--out", str(out), "--format", "svg"]) == 0
    assert set(os.listdir(out)) == {"tiny_flow.svg"}
    out = tmp_path / "c"
    assert main(["export", str(spec), "--out", str(out), "--format", "drawio", "--format", "png",
                 "--format", "drawio"]) == 0
    assert set(os.listdir(out)) == {"tiny_flow.drawio", "tiny_flow.png"}
    out = tmp_path / "d"
    assert main(["export", str(spec), "--out", str(out), "--all", "--name", "x", "--no-provenance"]) == 0
    assert set(os.listdir(out)) == {"x.drawio", "x.png", "x.svg"}
    assert "<!--" not in (out / "x.drawio").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["export", str(spec), "--format", "dot"])             # dot is not in the export format set


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
        assert (tmp_path / f"{name}.drawio").exists()
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "control_structure_demo.drawio" in index and "legibility:" in index
