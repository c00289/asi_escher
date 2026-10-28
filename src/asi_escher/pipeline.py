"""One-call pipeline: layout -> render PNG/SVG -> write DOT + Mermaid."""
from __future__ import annotations

import os
import re

from .export import to_dot, to_mermaid
from .layout import LayoutOptions, layout
from .model import Diagram
from .render import render

FORMATS = ("png", "svg", "dot", "mmd")


def slug(title: str) -> str:
    """File-system-safe stem derived from a diagram title."""
    s = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return s or "diagram"


def build(d: Diagram, out_dir: str, name: str | None = None,
          opts: LayoutOptions | None = None, dpi: int = 160,
          formats: tuple[str, ...] = FORMATS) -> dict:
    """Lay out ``d`` and write ``<name>.<fmt>`` into ``out_dir``.

    ``name`` defaults to a slug of the diagram title.  ``formats`` selects any
    subset of ``png``, ``svg``, ``dot`` and ``mmd``.

    Returns a dict with one path per written format plus ``size`` (canvas
    width, height in px), ``nodes`` and ``edges`` counts and ``issues`` (the
    list of :class:`~asi_escher.LayoutIssue` recorded during layout).
    """
    unknown = set(formats) - set(FORMATS)
    if unknown:
        raise ValueError(f"unknown formats {sorted(unknown)}; expected a subset of {FORMATS}")
    name = name or slug(d.title)
    os.makedirs(out_dir, exist_ok=True)
    layout(d, opts)
    paths = {fmt: os.path.join(out_dir, f"{name}.{fmt}") for fmt in formats}
    if "png" in paths or "svg" in paths:
        render(d, png=paths.get("png"), svg=paths.get("svg"), dpi=dpi)
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
    return result
