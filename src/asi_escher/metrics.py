"""Text measurement + node sizing shared by layout and renderer.

All geometry is in "pixels": one data unit is one pixel at 100 dpi.  Text is
measured with matplotlib's TextPath using the bundled DejaVu Sans font, so
sizes are identical on every machine regardless of installed system fonts.
"""
from __future__ import annotations

import textwrap
from functools import lru_cache

from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

from .model import CHAIN_NODE_KINDS, CONTROL_NODE_KINDS, Edge, Node

FONT_PX = 12.5            # body text height in px
SMALL_PX = 10.5           # edge labels / stereotypes
TITLE_PX = 13.5           # block names
FONT_FAMILY = "DejaVu Sans"
LINE_H = FONT_PX * 1.3

WRAP_WIDTH = 24           # characters per line for action-like nodes
WRAP_WIDTH_DECISION = 20
WRAP_WIDTH_CONTROL = 42   # characters per line inside a control-structure box
CONTROL_PAD = 10.0        # inner padding of a control-structure box
CONTROL_SECTION_GAP = 5.0
CONTROL_MIN_WIDTH = 150.0             # narrowest control-structure box ...
CONTROL_WIDTH_PER_ALGORITHM = 12.0    # ... plus this much per algorithm line
WRAP_WIDTH_CHAIN = 18     # characters per title line of a chain event
WRAP_WIDTH_CHAIN_NOTE = 24
CHAIN_PAD = 11.0          # inner padding of a chain event box
CHAIN_MIN_WIDTH = 112.0
CHAIN_POINT = 13.0        # how far a milestone's pointed ends stick out
CHAIN_GATE_INSET = 4.0    # the gap between the two borders of a gate

_prop = FontProperties(family=FONT_FAMILY)
_prop_b = FontProperties(family=FONT_FAMILY, weight="bold")

# UML stereotype shown on requirement-relationship edges
EDGE_STEREOTYPES = {
    "satisfy": "satisfy", "derive": "deriveReqt", "verify": "verify",
    "refine": "refine", "allocate": "allocate",
}

# Edge kinds drawn as dashed lines whatever the author's ``style`` (UML
# dependencies, the requirement relationships and a chain's ``informs``);
# shared by the renderer and the exporters.
DASHED_EDGE_KINDS = ("dependency", "satisfy", "derive", "verify", "refine", "allocate", "informs")


def pt(px: float) -> float:
    """px -> matplotlib points (for fontsize) at 100 dpi."""
    return px * 72.0 / 100.0


@lru_cache(maxsize=4096)
def text_width(s: str, size: float = FONT_PX, bold: bool = False) -> float:
    if not s:
        return 0.0
    tp = TextPath((0, 0), s, size=size, prop=_prop_b if bold else _prop)
    bb = tp.get_extents()
    return float(bb.width) + size * 0.15


def text_box(s: str, size: float = FONT_PX, bold: bool = False) -> tuple[float, float]:
    """(width, height) of a possibly multi-line string."""
    lines = s.split("\n") if s else [""]
    w = max(text_width(line, size, bold) for line in lines)
    return w, len(lines) * size * 1.3


def wrap(label: str, width: int = WRAP_WIDTH) -> list[str]:
    """Wrap ``label`` to ``width`` characters, honouring explicit newlines."""
    lines = []
    for para in label.split("\n"):
        lines.extend(textwrap.wrap(para, width=width) or [""])
    return lines


def block_width(lines: list[str], size: float = FONT_PX) -> float:
    return max((text_width(line, size) for line in lines), default=0.0)


def edge_label(e: Edge) -> str:
    """Text drawn on an edge: the stereotype (if any) plus the author's label."""
    stereo = EDGE_STEREOTYPES.get(e.kind)
    if stereo is None:
        return e.label
    return f"«{stereo}»" + (f"\n{e.label}" if e.label else "")


def size_node(n: Node) -> tuple[float, float]:
    """Return (w, h) for a node based on its kind and label.

    Also fills ``n.lines`` with the wrapped label the renderer will draw; the
    author's ``n.label`` is left untouched.
    """
    k = n.kind
    n.lines = []
    if k == "dummy":
        return 0.0, 0.0
    if k == "start":
        return 22.0, 22.0
    if k in ("end", "flowfinal"):
        return 28.0, 28.0
    if k == "merge":
        return 26.0, 26.0
    if k in ("fork", "join"):
        return 120.0, 7.0
    if k in ("block", "requirement", "part", "object"):
        n.lines = n.label.split("\n")
        return _size_block(n)
    if k in CONTROL_NODE_KINDS:
        n.lines = wrap(n.label, 30) if n.label else [""]
        return _size_control(n)
    if k in CHAIN_NODE_KINDS:
        n.lines = wrap(n.label, WRAP_WIDTH_CHAIN) if n.label else [""]
        return _size_chain(n)

    lines = wrap(n.label, WRAP_WIDTH_DECISION if k == "decision" else WRAP_WIDTH)
    n.lines = lines
    tw = block_width(lines)
    th = len(lines) * LINE_H
    if k == "decision":
        # diamond: inscribed text needs ~2x the box
        w = max(90.0, tw * 1.6 + 30)
        h = max(56.0, th * 1.8 + 20)
        return w, h
    if k == "note":
        # a note floating beside a control-structure box gets more room under
        # its italic text: the OCR engine drops a last line set tight on the border
        return max(90.0, tw + 30), th + (30 if n.attached_to is not None else 22)
    if k == "io":
        return max(100.0, tw + 50), th + 22
    if k == "document":
        return max(100.0, tw + 30), th + 30
    if k == "database":
        return max(90.0, tw + 30), th + 34
    if k == "state":
        return max(100.0, tw + 36), th + 26
    # action / process (default)
    return max(96.0, tw + 30), th + 24


def _size_block(n: Node) -> tuple[float, float]:
    name_lines = n.lines
    widths = [text_width(line, TITLE_PX, bold=True) for line in name_lines]
    if n.stereotype:
        widths.append(text_width(f"«{n.stereotype}»", SMALL_PX))
    h = 10 + (SMALL_PX * 1.3 if n.stereotype else 0) + len(name_lines) * TITLE_PX * 1.35 + 8
    for title, lines in n.compartments:
        if title:
            widths.append(text_width(title, SMALL_PX))
            h += SMALL_PX * 1.4
        for line in lines:
            widths.append(text_width(line, FONT_PX))
        h += len(lines) * LINE_H + 8
    w = max(110.0, max(widths) + 28)
    return w, max(44.0, h)


# ------------------------------------------------- control structures -----
def control_sections(n: Node) -> list[tuple[str, list[str]]]:
    """The stacked sections of a control-structure box as wrapped lines.

    Returns ``[(kind, lines), ...]`` with kind ``"responsibility"``,
    ``"algorithms"`` (``"V1  Name"`` per algorithm) or ``"process_model"``
    (the title first, then one line per entry), in drawing order; a section
    without content is left out.  Shared by the sizing, the renderer and the
    exporters so every output agrees on the text of a box.
    """
    out: list[tuple[str, list[str]]] = []
    if n.responsibility:
        out.append(("responsibility", wrap(n.responsibility, WRAP_WIDTH_CONTROL)))
    if n.algorithms:
        lines: list[str] = []
        for code, name in n.algorithms:
            lines.extend(wrap(f"{code} {name}" if code else name, WRAP_WIDTH_CONTROL))
        out.append(("algorithms", lines))
    if n.process_model is not None:
        title, entries = n.process_model
        lines = wrap(title, WRAP_WIDTH_CONTROL) if title else []
        for entry in entries:
            lines.extend(wrap(entry, WRAP_WIDTH_CONTROL))
        if lines:
            out.append(("process_model", lines))
    return out


def control_section_height(lines: list[str]) -> float:
    return len(lines) * LINE_H + 2 * CONTROL_SECTION_GAP


# ------------------------------------------------------------- chains -----
def chain_sublines(n: Node) -> list[tuple[str, str]]:
    """The small lines under a chain event's title: ``("owner", text)``,
    ``("due", "due <date>")`` and one ``("note", line)`` per wrapped note
    line, each only when set.  Shared by the sizing, the renderer and the
    exporters so every output agrees on the text of a box."""
    out: list[tuple[str, str]] = []
    if n.owner:
        out.append(("owner", n.owner))
    if n.due:
        out.append(("due", f"due {n.due}"))
    if n.note:
        out.extend(("note", line) for line in wrap(n.note, WRAP_WIDTH_CHAIN_NOTE))
    return out


def _size_chain(n: Node) -> tuple[float, float]:
    """Size of a chain event box: the title in bold, the small lines under it;
    a milestone is wider by its two points, a gate by its inner border."""
    subs = chain_sublines(n)
    widths = [text_width(line, TITLE_PX, bold=True) for line in n.lines]
    widths.extend(text_width(text, SMALL_PX) for _, text in subs)
    h = 2 * CHAIN_PAD + len(n.lines) * TITLE_PX * 1.35
    if subs:
        h += 3 + len(subs) * SMALL_PX * 1.3
    w = max(CHAIN_MIN_WIDTH, max(widths) + 2 * CHAIN_PAD)
    if n.kind == "milestone":
        w += 2 * CHAIN_POINT
    elif n.kind == "gate":
        w += 2 * CHAIN_GATE_INSET
        h += 2 * CHAIN_GATE_INSET
    return w, max(40.0, h)


def _size_control(n: Node) -> tuple[float, float]:
    """Size of a control-structure box: the title, then its sections."""
    widths = [text_width(line, TITLE_PX, bold=True) for line in n.lines]
    h = CONTROL_PAD + len(n.lines) * TITLE_PX * 1.35 + CONTROL_PAD * 0.6
    sections = control_sections(n)
    for _, lines in sections:
        widths.extend(text_width(line, FONT_PX) for line in lines)
        h += control_section_height(lines)
    h += CONTROL_PAD * 0.6 if sections else 0.0
    if n.kind in ("sensor", "actuator") and not sections:
        return max(96.0, max(widths) + 36), max(36.0, h)
    # a box with many algorithms is a busy one: the wider it is, the further
    # apart the arrows on its edge and the more room their signal stacks get
    min_w = CONTROL_MIN_WIDTH + CONTROL_WIDTH_PER_ALGORITHM * len(n.algorithms)
    return max(min_w, max(widths) + 2 * CONTROL_PAD + 6), max(44.0, h)
