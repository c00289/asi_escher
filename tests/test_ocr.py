"""The OCR quality gate: the matcher, the unavailable path, build() and the CLI, and the demo's legibility."""
import json
import subprocess

import pytest

from asi_escher import Diagram, OcrReport, build, layout, ocr_check, render
from asi_escher.cli import main
from asi_escher.examples import control_structure_demo
from asi_escher.ocr import _SCRIPT, _find, _token_stream, _tokens, recognize


def _found(label, lines):
    return _find(_tokens(label), _token_stream(lines))


def test_matcher_is_tolerant():
    assert _found("CA-01 Mission Start", ["CA-Ol Mission Start"])            # l for 1, dash ignored
    assert _found("FB-20", ["F B-20 Stop Request State"])                      # a split token
    assert _found("V1", ["VI Trajectory planning"])                            # I for 1
    assert _found("CA-10", ["CA-IO Mission Data"])                             # O for 0
    assert _found("Site Supervisor", ["site supervisor"])                      # case
    assert _found("Vehicle Controller", ["... Vehicle", "Controller ..."])     # across adjacent lines
    assert _found("Supervisor", ["Super-", "visor"])                           # hyphenation
    assert _found("Bucket fill > 85%?", ["Bucket fill 85%"])                    # punctuation ignored


def test_matcher_needs_whole_tokens():
    assert not _found("M1", ["Mission start"])                                 # not inside "m1ss10n"
    assert not _found("CA-01", ["CA-02 Mission Stop"])
    assert not _found("Loader Machine", ["Loader", "Perception Unit", "Machine"])
    assert _found("", ["anything"])


def test_unavailable_engine_never_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("asi_escher.ocr.shutil.which", lambda name: None)
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    report = ocr_check(str(png), ["A label"])
    assert not report.available and not report.competent and report.missing == []
    assert report.verdict.startswith("ocr unavailable")
    issues = report.issues()
    assert len(issues) == 1 and issues[0].kind == "ocr" and "ocr unavailable" in issues[0].message
    assert report.to_dict()["verdict"] == report.verdict
    missing_file = ocr_check(str(tmp_path / "none.png"), ["A"])
    assert not missing_file.available and "no such file" in missing_file.error


def test_report_verdicts_and_issues():
    ok = OcrReport("p.png", ["A", "B"], available=True, lines=["A", "B"], found=["A", "B"])
    assert ok.competent and ok.verdict == "competent" and ok.issues() == []
    bad = OcrReport("p.png", ["A", "B"], available=True, lines=["A"], found=["A"], missing=["B"])
    assert not bad.competent and bad.verdict == "unreadable: B"
    assert [(i.kind, i.message) for i in bad.issues()] == [("ocr", "label 'B' not readable in the PNG")]
    assert bad.to_dict()["line_count"] == 1


def _fake_recognize(lines):
    def fake(png_path, timeout=0.0):
        return OcrReport(png=str(png_path), expected=[], available=True, language="en-US", lines=list(lines))
    return fake


def test_build_with_ocr_reports_in_result_and_issues(monkeypatch, tmp_path):
    d = Diagram("Tiny", "flowchart")
    d.action("a", "First step")
    d.action("b", "Second step")
    d.edge("a", "b")
    monkeypatch.setattr("asi_escher.ocr.recognize", _fake_recognize(["First step", "Second step"]))
    res = build(d, str(tmp_path), formats=("png",), ocr=True)
    assert res["ocr"].competent and res["ocr"].verdict == "competent" and res["issues"] == []
    monkeypatch.setattr("asi_escher.ocr.recognize", _fake_recognize(["First step"]))
    res = build(d, str(tmp_path), formats=("png",), ocr=True)
    assert res["ocr"].missing == ["Second step"]
    assert [i.kind for i in res["issues"]] == ["ocr"] and d.issues == res["issues"]
    res = build(d, str(tmp_path), formats=("png",))
    assert "ocr" not in res                                               # the gate is opt-in


def test_cli_verify(monkeypatch, tmp_path, capsys):
    png = tmp_path / "p.png"
    render(layout(Diagram("x")), png=str(png))
    monkeypatch.setattr("asi_escher.ocr.recognize", _fake_recognize(["Alpha beta", "Gamma"]))
    assert main(["verify", str(png), "--expect", "Alpha", "Gamma"]) == 0
    assert capsys.readouterr().out.startswith("competent (2 OCR lines)")
    assert main(["verify", str(png), "--expect", "Alpha", "Delta", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["missing"] == ["Delta"] and data["verdict"] == "unreadable: Delta"
    monkeypatch.setattr("asi_escher.ocr.recognize",
                        lambda p, timeout=0.0: OcrReport(png=str(p), expected=[], error="no engine"))
    assert main(["verify", str(png), "--expect", "Alpha"]) == 3
    assert "ocr unavailable" in capsys.readouterr().out


def test_cli_build_with_ocr_prints_the_verdict(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("asi_escher.ocr.recognize", _fake_recognize(["Remote Operator"]))
    assert main(["example", "control_structure_demo", "-o", str(tmp_path), "--formats", "png", "--ocr"]) == 0
    out, err = capsys.readouterr()
    assert "legibility: unreadable:" in out and "not readable in the PNG" in err


@pytest.fixture(scope="session")
def ocr_engine(tmp_path_factory):
    """True when the Windows OCR engine runs here; otherwise the dependent tests skip."""
    d = Diagram("Probe")
    d.action("a", "Probe")
    path = tmp_path_factory.mktemp("ocr") / "probe.png"
    render(layout(d), png=str(path))
    return recognize(str(path)).available


def test_demo_is_competent_under_real_ocr(ocr_engine, tmp_path):
    if not ocr_engine:
        pytest.skip("Windows OCR engine unavailable")
    res = build(control_structure_demo(), str(tmp_path), formats=("png",), ocr=True)
    report = res["ocr"]
    assert report.available and len(report.lines) > 40
    assert report.competent, report.verdict
    assert res["issues"] == []


# ------------------------------------------------------------- UTF-8 ----
def test_tokens_fold_accents_and_italic_confusions():
    assert _tokens("• Café – Résumé") == ["cafe", "resume"]
    assert _found("Café – open", ["Cafe - open"])
    assert _found("human embedded", ["hutnan", "ernbedded"])                # an italic m


def test_recognize_reads_the_powershell_output_as_utf8(monkeypatch, tmp_path):
    png = tmp_path / "x.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    payload = b'{"available":true,"language":"en-US","lines":["\xe2\x80\xa2 Caf\xc3\xa9 \xe2\x80\x93 ouvert","Plain"]}'

    def fake_run(args, **kw):
        assert kw["encoding"] == "utf-8"
        return subprocess.CompletedProcess(args, 0, stdout=payload.decode(kw["encoding"]), stderr="")

    monkeypatch.setattr("asi_escher.ocr.shutil.which", lambda name: "powershell")
    monkeypatch.setattr("asi_escher.ocr.os.name", "nt")
    monkeypatch.setattr("asi_escher.ocr.subprocess.run", fake_run)
    report = ocr_check(str(png), ["• Café – ouvert", "Plain", "Missing"])
    assert report.available and report.lines == ["• Café – ouvert", "Plain"]
    assert report.found == ["• Café – ouvert", "Plain"] and report.missing == ["Missing"]
    assert json.loads(json.dumps(report.to_dict()))["found"][0] == "• Café – ouvert"
    assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in _SCRIPT
    assert "$OutputEncoding = [System.Text.Encoding]::UTF8" in _SCRIPT


def test_non_ascii_labels_are_competent_under_real_ocr(ocr_engine, tmp_path):
    if not ocr_engine:
        pytest.skip("Windows OCR engine unavailable")
    d = Diagram("Accents", "flowchart")
    d.action("a", "• Start here")
    d.action("b", "Café – open")
    d.action("c", "Résumé of the day")
    d.chain("a", "b", "c")
    res = build(d, str(tmp_path), formats=("png",), ocr=True)
    report = res["ocr"]
    assert report.available and report.error is None
    assert report.competent, report.verdict
