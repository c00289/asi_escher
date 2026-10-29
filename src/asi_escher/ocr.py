"""The OCR quality gate: read a rendered PNG back and check that every label is legible.

A diagram is only competent when a reader can read it, so after a PNG is
rendered the built-in Windows OCR engine (``Windows.Media.Ocr``, reached
through PowerShell 5.1's WinRT projection, no Tesseract needed) reads it
back and the recognised lines are compared with what the diagram was
supposed to say: every node title, every signal id (``CA-xx`` / ``FB-xx``)
and, for a control structure, every algorithm code.  Each miss becomes a
:class:`~asi_escher.LayoutIssue` of kind ``"ocr"``; when the engine is
unavailable (no Windows, no language pack, PowerShell missing) the report
says ``ocr unavailable`` as one issue and never fails anything.

The match is tolerant: case-insensitive, punctuation, accents and whitespace
ignored, a label found when its words appear in order on one OCR line or
across adjacent lines (so hyphenation and the dash of ``CA-01`` do not
matter), and the engine's usual confusions (``O`` for ``0``, ``I``/``l`` for
``1``, ``rn``/``tn`` for an italic ``m``) are folded on both sides.

The PowerShell side writes UTF-8 and the Python side reads UTF-8, so a label
with a bullet, a dash or an accent (``•``, ``–``, ``é``) comes back intact
instead of as a control byte of the console code page that breaks the JSON.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field

from .model import Diagram, LayoutIssue

OCR_TIMEOUT = 90.0        # seconds; the engine takes one to three on a large diagram

# PowerShell 5.1 script: decode the PNG named by the environment, run the
# engine, print one JSON object.  (-EncodedCommand takes no arguments.)
_PNG_ENV = "ASI_ESCHER_OCR_PNG"
_SCRIPT = r'''
$Path = $env:ASI_ESCHER_OCR_PNG
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try {
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
    $null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
    $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
    $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType=WindowsRuntime]
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    function Await($op, $type) {
        $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
        $null = $task.Wait(-1)
        $task.Result
    }
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new("en-US"))
    if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
    if (-not $engine) { @{available=$false; error="no OCR language installed"} | ConvertTo-Json -Compress; exit 0 }
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
    $streamType = [Windows.Storage.Streams.IRandomAccessStream]
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) $streamType
    $decoderType = [Windows.Graphics.Imaging.BitmapDecoder]
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) $decoderType
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @($result.Lines | ForEach-Object { $_.Text })
    @{available=$true; language=$engine.RecognizerLanguage.LanguageTag; lines=$lines} | ConvertTo-Json -Compress
} catch {
    @{available=$false; error=$_.Exception.Message} | ConvertTo-Json -Compress
}
'''


@dataclass
class OcrReport:
    """What the OCR engine read from a PNG and which expected labels it missed.

    ``available`` is False when the engine could not run (``error`` says why);
    then ``missing`` is empty and the verdict is ``"ocr unavailable"``.
    """
    png: str
    expected: list[str]
    available: bool = False
    language: str = ""
    lines: list[str] = field(default_factory=list)
    found: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def competent(self) -> bool:
        """True when the engine ran and every expected label was found."""
        return self.available and not self.missing

    @property
    def verdict(self) -> str:
        if not self.available:
            return "ocr unavailable" + (f": {self.error}" if self.error else "")
        if not self.missing:
            return "competent"
        return "unreadable: " + ", ".join(self.missing)

    def issues(self) -> list[LayoutIssue]:
        """The report as ``LayoutIssue`` entries of kind ``"ocr"``: one per miss,
        or a single ``ocr unavailable`` entry."""
        if not self.available:
            return [LayoutIssue("ocr", self.verdict)]
        return [LayoutIssue("ocr", f"label {m!r} not readable in the PNG") for m in self.missing]

    def to_dict(self) -> dict:
        return {
            "png": self.png, "available": self.available, "language": self.language,
            "verdict": self.verdict, "competent": self.competent, "line_count": len(self.lines),
            "expected": list(self.expected), "found": list(self.found), "missing": list(self.missing),
            "error": self.error,
        }


def recognize(png_path: str, timeout: float = OCR_TIMEOUT) -> OcrReport:
    """Run the Windows OCR engine on ``png_path`` and return the lines it read
    (``expected`` empty, nothing matched yet)."""
    report = OcrReport(png=str(png_path), expected=[])
    if not os.path.isfile(png_path):
        report.error = f"no such file: {png_path}"
        return report
    exe = shutil.which("powershell")
    if os.name != "nt" or exe is None:
        report.error = "Windows PowerShell is not available on this platform"
        return report
    encoded = base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")
    try:
        proc = subprocess.run(
            [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            env={**os.environ, _PNG_ENV: os.path.abspath(png_path)},
            capture_output=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        report.error = f"OCR did not run: {exc}"
        return report
    text = (proc.stdout or "").strip()
    start = text.find("{")
    try:
        data = json.loads(text[start:]) if start >= 0 else {}
    except json.JSONDecodeError:
        data = {}
    if not data:
        report.error = (proc.stderr or text or f"PowerShell exit code {proc.returncode}").strip()[:300]
        return report
    if not data.get("available"):
        report.error = str(data.get("error") or "OCR engine unavailable")
        return report
    lines = data.get("lines") or []
    if isinstance(lines, str):
        lines = [lines]
    report.available = True
    report.language = str(data.get("language") or "")
    report.lines = [str(line) for line in lines]
    return report


def ocr_check(png_path: str, expected: list[str], timeout: float = OCR_TIMEOUT) -> OcrReport:
    """Read ``png_path`` back and check that every label of ``expected`` is legible."""
    report = recognize(png_path, timeout=timeout)
    report.expected = [str(x) for x in expected if str(x).strip()]
    if not report.available:
        return report
    stream = _token_stream(report.lines)
    for label in report.expected:
        (report.found if _find(_tokens(label), stream) else report.missing).append(label)
    return report


_SIGNAL_ID = re.compile(r"^[A-Za-z]{1,4}-\d+")


def expected_labels(d: Diagram) -> list[str]:
    """What a reader must be able to read in a rendering of ``d``: every node
    title (a block's or box's name, an action's text), every signal id on a
    control action or feedback and, in a control structure, every algorithm
    code (``V1``) and process-model title."""
    out: list[str] = []
    for n in d.real_nodes():
        if n.label.strip() and n.kind != "dummy":
            out.append(n.label)
        if n.kind != "note":
            for code, _name in n.algorithms:
                if code.strip():
                    out.append(code)
            if n.process_model and n.process_model[0].strip():
                out.append(n.process_model[0])
    for e in d.edges:
        for sig in e.signals:
            m = _SIGNAL_ID.match(sig.strip())
            if m:
                out.append(m.group(0))
    seen: set[str] = set()
    unique = []
    for label in out:
        if label not in seen:
            seen.add(label)
            unique.append(label)
    return unique


# ------------------------------------------------------------- matching ----
_CONFUSABLE = str.maketrans({"o": "0", "i": "1", "l": "1", "|": "1"})
_CONFUSABLE_PAIRS = (("rn", "m"), ("tn", "m"))      # what an italic m comes back as


def _tokens(text: str) -> list[str]:
    """Lower-case alphanumeric words, accents stripped, with the engine's
    confusions folded."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    folded = plain.lower()
    for seen, meant in _CONFUSABLE_PAIRS:
        folded = folded.replace(seen, meant)
    return [t for t in re.split(r"[^a-z0-9]+", folded.translate(_CONFUSABLE)) if t]


def _token_stream(lines: list[str]) -> list[str]:
    stream: list[str] = []
    for line in lines:
        stream.extend(_tokens(line))
    return stream


def _find(want: list[str], stream: list[str]) -> bool:
    """True when the concatenation of ``want`` equals the concatenation of a
    run of whole tokens in ``stream`` (so "F B-20" reads as "FB-20" and a
    hyphenated word split over two lines still counts)."""
    if not want:
        return True
    target = "".join(want)
    n = len(stream)
    for i in range(n):
        if not target.startswith(stream[i]):
            continue
        acc = ""
        j = i
        while j < n and len(acc) < len(target) and target.startswith(acc + stream[j]):
            acc += stream[j]
            j += 1
            if acc == target:
                return True
    return False
