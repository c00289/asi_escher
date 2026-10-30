"""Build every example diagram into a directory plus an index.html gallery."""
from __future__ import annotations

import html
import os
import time
from collections.abc import Callable, Iterable

from .examples import EXAMPLES
from .model import Diagram
from .pipeline import ALL_FORMATS, build

# The diagram kinds the gallery runs the OCR gate on by default: the ones a
# reader must be able to read every title of.
OCR_KINDS = ("control_structure", "chain", "gantt")

_CSS = """
 body{font-family:Segoe UI,Helvetica,Arial,sans-serif;margin:24px;background:#f6f7f9;color:#1f2933}
 h1{font-size:22px} h2{font-size:17px;margin:40px 0 8px}
 .card{background:#fff;border:1px solid #d9dee5;border-radius:8px;padding:16px;margin-bottom:28px}
 .meta{color:#52606d;font-size:13px;margin-bottom:10px}
 img{max-width:100%;height:auto;border:1px solid #e3e8ee}
 details{margin-top:10px} summary{cursor:pointer;color:#2f6db5}
 pre{background:#f1f4f8;padding:10px;border-radius:6px;overflow:auto;font-size:12px}
 a{color:#2f6db5}
 nav a{margin-right:12px;font-size:13px}
"""


def build_gallery(out_dir: str,
                  examples: Iterable[tuple[str, Callable[[], Diagram]]] = EXAMPLES,
                  dpi: int = 160, log: Callable[[str], None] | None = print,
                  formats: tuple[str, ...] = ALL_FORMATS, provenance: bool = True,
                  ocr: bool | str | tuple[str, ...] = OCR_KINDS) -> list[dict]:
    """Render ``examples`` into ``out_dir`` and write ``index.html``.

    ``ocr`` runs the OCR quality gate (:mod:`asi_escher.ocr`) on the written
    PNGs: ``True`` for every diagram, ``False`` for none, a diagram kind or a
    tuple of kinds (the default, :data:`OCR_KINDS`) for the diagrams of those
    kinds.

    Returns one result dict per diagram (see :func:`asi_escher.build`) with
    the extra keys ``name``, ``title``, ``kind``, ``direction`` and ``seconds``.
    """
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    t0 = time.time()
    for name, builder in examples:
        t = time.time()
        d = builder()
        gate = ocr is True or (isinstance(ocr, str) and ocr == d.kind) or (isinstance(ocr, tuple) and d.kind in ocr)
        res = build(d, out_dir, name, dpi=dpi, formats=formats, provenance=provenance,
                    ocr=gate and "png" in formats)
        res.update(name=name, title=d.title, kind=d.kind, direction=d.direction,
                   seconds=time.time() - t)
        rows.append(res)
        if log:
            log(f"{name:32s} {res['nodes']:3d} nodes {res['edges']:3d} edges "
                f"{res['size'][0]:5d}x{res['size'][1]:<5d} {res['seconds']:5.2f}s"
                + (f"  ({len(res['issues'])} issue(s))" if res["issues"] else "")
                + (f"  legibility: {res['ocr'].verdict}" if "ocr" in res else ""))
    if log:
        log(f"{len(rows)} diagrams in {time.time() - t0:.1f}s -> {out_dir}")
    _write_index(out_dir, rows)
    return rows


def _write_index(out_dir: str, rows: list[dict]) -> None:
    parts = [f"""<!doctype html><html><head><meta charset="utf-8">
<title>asi_escher gallery</title>
<style>{_CSS}</style></head><body>
<h1>asi_escher example gallery</h1>
<p>Each diagram was laid out and rendered by the pure-Python engine (PNG + SVG).
The DOT and Mermaid blocks are exported source for Graphviz / Mermaid renderers.</p>
<nav>"""]
    for r in rows:
        parts.append(f'<a href="#{r["name"]}">{html.escape(r["title"])}</a>')
    parts.append("</nav>")
    labels = {"drawio": "draw.io", "png": "PNG", "svg": "SVG", "dot": "DOT", "mmd": "Mermaid"}
    for r in rows:
        name = r["name"]
        links = " · ".join(f'<a href="{name}.{fmt}">{labels[fmt]}</a>' for fmt in ALL_FORMATS if fmt in r)
        legibility = f' · legibility: {html.escape(r["ocr"].verdict)}' if "ocr" in r else ""
        parts.append(f"""
<div class="card" id="{name}">
<h2>{html.escape(r["title"])}</h2>
<div class="meta">{r["kind"]} · {r["direction"]} · {r["nodes"]} nodes · {r["edges"]} edges ·
 {r["size"][0]}×{r["size"][1]} px · {r["seconds"]:.2f}s · {links}{legibility}</div>""")
        if "png" in r:
            parts.append(f'<img src="{name}.png" alt="{html.escape(r["title"])}">')
        for fmt, title in (("dot", "Graphviz DOT source"), ("mmd", "Mermaid source")):
            if fmt in r:
                with open(r[fmt], encoding="utf-8") as f:
                    parts.append(f"<details><summary>{title}</summary><pre>{html.escape(f.read())}</pre></details>")
        parts.append("</div>")
    parts.append("</body></html>")
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
