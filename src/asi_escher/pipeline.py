"""One-call pipeline: layout -> draw.io / PNG / SVG (and DOT + Mermaid on request).

``FORMATS`` is the format set shared with the sibling tools (asi_dewey's
export dialog offers exactly these): ``drawio`` (the editable draw.io file,
positions from the layout), ``png`` and ``svg`` (asi_escher's renderings of
the same layout).  ``DEFAULT_FORMATS`` is the pair written when nothing is
chosen, the file to edit and the picture to look at.  ``build`` also writes
``dot`` and ``mmd`` when asked (``ALL_FORMATS``).
"""
from __future__ import annotations

import os

from .export import to_dot, to_drawio, to_mermaid
from .layout import LayoutOptions, layout
from .model import Diagram
from .provenance import slug
from .render import render

FORMATS = ("drawio", "png", "svg")
DEFAULT_FORMATS = ("drawio", "png")
ALL_FORMATS = FORMATS + ("dot", "mmd")

__all__ = ["FORMATS", "DEFAULT_FORMATS", "ALL_FORMATS", "build", "slug"]


def build(d: Diagram, out_dir: str, name: str | None = None,
          opts: LayoutOptions | None = None, dpi: int = 160,
          formats: tuple[str, ...] = DEFAULT_FORMATS, provenance: bool = True,
          ocr: bool = False) -> dict:
    """Lay out ``d`` and write ``<name>.<fmt>`` into ``out_dir``.

    ``name`` defaults to a slug of the diagram title.  ``formats`` selects any
    subset of ``drawio``, ``png``, ``svg``, ``dot`` and ``mmd``; the default
    is :data:`DEFAULT_FORMATS` (``drawio`` and ``png``).  ``provenance``
    switches the footer of the renderings and the comment and note of the
    draw.io file (see :mod:`asi_escher.provenance`).  ``ocr`` reads the
    written PNG back with the Windows OCR engine and checks every expected
    label (:func:`asi_escher.ocr.ocr_check`); the misses are added to the
    issues and the report returned under ``"ocr"``.

    Returns a dict with one path per written format plus ``size`` (canvas
    width, height in px), ``nodes`` and ``edges`` counts and ``issues`` (the
    list of :class:`~asi_escher.LayoutIssue` recorded during layout, plus the
    OCR issues when ``ocr`` is on).
    """
    unknown = set(formats) - set(ALL_FORMATS)
    if unknown:
        raise ValueError(f"unknown formats {sorted(unknown)}; expected a subset of {ALL_FORMATS}")
    name = name or slug(d.title)
    os.makedirs(out_dir, exist_ok=True)
    layout(d, opts)
    paths = {fmt: os.path.join(out_dir, f"{name}.{fmt}") for fmt in formats}
    if "png" in paths or "svg" in paths:
        render(d, png=paths.get("png"), svg=paths.get("svg"), dpi=dpi, provenance=provenance, name=name)
    if "drawio" in paths:
        with open(paths["drawio"], "w", encoding="utf-8") as f:
            f.write(to_drawio(d, provenance=provenance, name=name))
    if "dot" in paths:
        with open(paths["dot"], "w", encoding="utf-8") as f:
            f.write(to_dot(d))
    if "mmd" in paths:
        with open(paths["mmd"], "w", encoding="utf-8") as f:
            f.write(to_mermaid(d))
    result: dict = dict(paths)
    result["size"] = (round(d.width), round(d.height))
    result["nodes"] = len(d.real_nodes())
    result["edges"] = len(d.edges)
    result["issues"] = list(d.issues)
    if ocr and "png" in paths:
        from .ocr import expected_labels, ocr_check

        report = ocr_check(paths["png"], expected_labels(d))
        d.issues.extend(report.issues())
        result["issues"] = list(d.issues)
        result["ocr"] = report
    return result
