"""Render a laid-out Diagram to PNG / SVG with matplotlib.

All coordinates are pixels with y pointing down (the axes are inverted), so
the figure is exactly diagram.width x diagram.height px at 100 dpi.

The renderer uses the object-oriented matplotlib API (no ``pyplot``), selects
no backend and changes no global rcParams, so it can be embedded in an
application that uses matplotlib for its own purposes.
"""
from __future__ import annotations

import math

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, PathPatch, Polygon, Rectangle
from matplotlib.path import Path

from .metrics import (
    CONTROL_PAD,
    CONTROL_SECTION_GAP,
    DASHED_EDGE_KINDS,
    FONT_FAMILY,
    FONT_PX,
    LINE_H,
    SMALL_PX,
    TITLE_PX,
    control_section_height,
    control_sections,
    edge_label,
    pt,
    text_width,
)
from .model import CONTROL_NODE_KINDS, Diagram, Edge, Node
from .provenance import footer, slug

_RC = {
    "svg.fonttype": "none",      # keep text as text in SVG
    "font.family": FONT_FAMILY,
    "savefig.pad_inches": 0,
}

THEME = {
    "bg": "#FFFFFF",
    "ink": "#1F2933",
    "edge": "#3E4C59",
    "label_bg": "#FFFFFF",
    "action": ("#E6F0FA", "#2F6DB5"),
    "process": ("#E6F0FA", "#2F6DB5"),
    "decision": ("#FFF3DC", "#C98A1B"),
    "merge": ("#FFF3DC", "#C98A1B"),
    "state": ("#E8F5EC", "#2E8B57"),
    "note": ("#FFFBE6", "#B8A24A"),
    "io": ("#EFE9FA", "#6B46C1"),
    "document": ("#F4F4F4", "#5F6B7A"),
    "database": ("#F4F4F4", "#5F6B7A"),
    "block": ("#F1EDFA", "#6B46C1"),
    "part": ("#EEF6FF", "#2F6DB5"),
    "requirement": ("#FDF0F0", "#B83232"),
    "object": ("#F4F4F4", "#5F6B7A"),
    # control structures: box kinds, the two sections and the two arrow kinds
    "controller": ("#FFFFFF", "#37474F"),
    "human_controller": ("#FFFFFF", "#37474F"),
    "controlled_process": ("#FFFFFF", "#37474F"),
    "environment": ("#FAFAFA", "#546E7A"),
    "external_system": ("#F5F5F5", "#78909C"),
    "sensor": ("#F1F8E9", "#558B2F"),
    "actuator": ("#FFF8E1", "#F9A825"),
    "cs_algorithms": ("#FFF3E0", "#EF6C00"),
    "cs_process_model": ("#E3F2FD", "#1565C0"),
    "control_action": "#C62828",
    "feedback": "#1565C0",
    "lane_a": "#FAFBFC",
    "lane_b": "#F1F4F8",
    "lane_line": "#B8C2CC",
    "frame": "#5F6B7A",
    "bar": "#1F2933",
}


def render(d: Diagram, png: str | None = None, svg: str | None = None,
           dpi: int = 160, theme: dict | None = None, provenance: bool = True,
           name: str | None = None) -> Figure:
    """Draw a laid-out diagram.

    Writes ``png`` and/or ``svg`` when given (paths or file-like objects) and
    returns the matplotlib ``Figure`` so callers can embed or save it in other
    formats.  ``theme`` overrides entries of :data:`THEME`.  The diagram must
    have been passed through :func:`asi_escher.layout` first.

    ``provenance`` draws a small grey footer line in the bottom-left corner
    ("asi_escher <version>, <date>; layout shared with <name>.drawio", the
    draw.io file :func:`asi_escher.to_drawio` writes for the same layout);
    ``name`` defaults to the slug of the title.
    """
    th = dict(THEME)
    if theme:
        th.update(theme)
    W, H = max(d.width, 120), max(d.height, 80)
    with matplotlib.rc_context(_RC):
        fig = Figure(figsize=(W / 100.0, H / 100.0), dpi=100)
        FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.set_aspect("equal")
        ax.axis("off")
        fig.patch.set_facecolor(th["bg"])

        _draw_lanes(ax, d, th)
        _draw_frame(ax, d, th)
        for e in d.edges:
            _draw_edge(ax, d, e, th)
        for n in d.nodes.values():
            _draw_node(ax, n, th, d)
        for e in d.edges:
            _draw_edge_label(ax, e, th)
        if provenance:
            _text(ax, 6, H - 5, footer(name or slug(d.title)), size=SMALL_PX - 2, color="#9E9E9E",
                  ha="left", va="bottom", italic=True)

        if png:
            fig.savefig(png, format="png", dpi=dpi, facecolor=th["bg"])
        if svg:
            fig.savefig(svg, format="svg", facecolor=th["bg"])
    return fig


# ------------------------------------------------------------ helpers -----
def _text(ax, x, y, s, size=FONT_PX, color="#1F2933", ha="center", va="center",
          bold=False, italic=False, bg=None, rotation=0):
    kw = {}
    if bg:
        kw["bbox"] = dict(boxstyle="round,pad=0.15", fc=bg, ec="none")
    return ax.text(x, y, s, fontsize=pt(size), color=color, ha=ha, va=va,
                   fontweight="bold" if bold else "normal",
                   fontstyle="italic" if italic else "normal",
                   rotation=rotation, zorder=6, **kw)


def _draw_lanes(ax, d, th):
    if not d.lanes:
        return
    hdr = d.lane_header
    for i, ln in enumerate(d.lanes):
        fill = th["lane_a"] if i % 2 == 0 else th["lane_b"]
        if d.direction == "TB":
            x0, x1 = ln.x0, ln.x1
            y0, y1 = d.lane_top, d.lane_bottom
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=fill, ec=th["lane_line"], lw=1.0, zorder=0))
            ax.add_patch(Rectangle((x0, y0), x1 - x0, hdr, fc="#E3E8EE", ec=th["lane_line"], lw=1.0, zorder=0))
            _text(ax, (x0 + x1) / 2, y0 + hdr / 2, ln.title, size=SMALL_PX + 1, bold=True)
        else:
            y0, y1 = ln.x0, ln.x1
            x0, x1 = d.lane_top, d.lane_bottom
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=fill, ec=th["lane_line"], lw=1.0, zorder=0))
            ax.add_patch(Rectangle((x0, y0), hdr, y1 - y0, fc="#E3E8EE", ec=th["lane_line"], lw=1.0, zorder=0))
            _text(ax, x0 + hdr / 2, (y0 + y1) / 2, ln.title, size=SMALL_PX + 1, bold=True, rotation=90)


def _draw_frame(ax, d, th):
    """SysML-style diagram frame with a header tab, e.g. 'bdd [Package] X'."""
    if not d.frame:
        return
    m = 14
    W, H = d.width, d.height
    ax.add_patch(Rectangle((m, m), W - 2 * m, H - 2 * m, fc="none", ec=th["frame"], lw=1.2, zorder=1))
    tw = text_width(d.frame, SMALL_PX + 1, bold=True) + 26
    tab = Path([(m, m), (m + tw, m), (m + tw, m + 16), (m + tw - 10, m + 26), (m, m + 26), (m, m)],
               [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY])
    ax.add_patch(PathPatch(tab, fc="#F1F4F8", ec=th["frame"], lw=1.2, zorder=1))
    _text(ax, m + 10, m + 13, d.frame, size=SMALL_PX + 1, bold=True, ha="left")


# -------------------------------------------------------------- nodes -----
def _draw_node(ax, n: Node, th, d: Diagram):
    k = n.kind
    if k == "dummy":
        return
    x, y, w, h = n.x, n.y, n.w, n.h
    fill, stroke = th.get(k, ("#F4F4F4", "#5F6B7A"))
    fill = n.fill or fill
    stroke = n.stroke or stroke
    z = 4
    if k == "start":
        ax.add_patch(Circle((x, y), w / 2, fc=th["bar"], ec=th["bar"], zorder=z))
    elif k == "end":
        ax.add_patch(Circle((x, y), w / 2, fc="white", ec=th["bar"], lw=1.6, zorder=z))
        ax.add_patch(Circle((x, y), w / 2 - 4.5, fc=th["bar"], ec=th["bar"], zorder=z + 1))
    elif k == "flowfinal":
        ax.add_patch(Circle((x, y), w / 2, fc="white", ec=th["bar"], lw=1.6, zorder=z))
        r = w / 2 * 0.7
        ax.plot([x - r, x + r], [y - r, y + r], color=th["bar"], lw=1.6, zorder=z + 1)
        ax.plot([x - r, x + r], [y + r, y - r], color=th["bar"], lw=1.6, zorder=z + 1)
    elif k in ("fork", "join"):
        ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc=th["bar"], ec=th["bar"], zorder=z))
    elif k in ("decision", "merge"):
        pts = [(x, y - h / 2), (x + w / 2, y), (x, y + h / 2), (x - w / 2, y)]
        ax.add_patch(Polygon(pts, closed=True, fc=fill, ec=stroke, lw=1.4, zorder=z))
        if n.text:
            _text(ax, x, y, n.text)
    elif k == "note":
        f = 10
        pts = [(x - w / 2, y - h / 2), (x + w / 2 - f, y - h / 2), (x + w / 2, y - h / 2 + f),
               (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)]
        ax.add_patch(Polygon(pts, closed=True, fc=fill, ec=stroke, lw=1.1, zorder=z))
        ax.plot([x + w / 2 - f, x + w / 2 - f, x + w / 2], [y - h / 2, y - h / 2 + f, y - h / 2 + f],
                color=stroke, lw=1.0, zorder=z + 1)
        _text(ax, x, y, n.text, size=FONT_PX - 1, italic=True)
    elif k == "io":
        s = 14
        pts = [(x - w / 2 + s, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2 - s, y + h / 2), (x - w / 2, y + h / 2)]
        ax.add_patch(Polygon(pts, closed=True, fc=fill, ec=stroke, lw=1.4, zorder=z))
        _text(ax, x, y, n.text)
    elif k == "document":
        verts = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2 - 8),
                 (x + w / 4, y + h / 2 - 16), (x, y + h / 2 - 8), (x - w / 4, y + h / 2),
                 (x - w / 2, y + h / 2 - 8), (x - w / 2, y - h / 2)]
        codes = [Path.MOVETO, Path.LINETO, Path.LINETO, Path.CURVE3, Path.CURVE3, Path.CURVE3, Path.CURVE3,
                 Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), fc=fill, ec=stroke, lw=1.4, zorder=z))
        _text(ax, x, y - 4, n.text)
    elif k == "database":
        ry = 7
        ax.add_patch(Rectangle((x - w / 2, y - h / 2 + ry), w, h - 2 * ry, fc=fill, ec="none", zorder=z))
        ax.plot([x - w / 2, x - w / 2], [y - h / 2 + ry, y + h / 2 - ry], color=stroke, lw=1.4, zorder=z + 1)
        ax.plot([x + w / 2, x + w / 2], [y - h / 2 + ry, y + h / 2 - ry], color=stroke, lw=1.4, zorder=z + 1)
        ax.add_patch(Ellipse((x, y + h / 2 - ry), w, 2 * ry, fc=fill, ec=stroke, lw=1.4, zorder=z))
        ax.add_patch(Rectangle((x - w / 2 + 1, y - h / 2 + ry), w - 2, h - 2 * ry - ry,
                               fc=fill, ec="none", zorder=z + 1))
        ax.add_patch(Ellipse((x, y - h / 2 + ry), w, 2 * ry, fc=fill, ec=stroke, lw=1.4, zorder=z + 2))
        _text(ax, x, y + 3, n.text)
    elif k in ("block", "requirement", "part", "object"):
        _draw_block(ax, n, fill, stroke, th)
    elif k in CONTROL_NODE_KINDS:
        _draw_control_box(ax, n, fill, stroke, th)
    else:  # action, process, state
        rs = 9 if k != "state" else 14
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                    boxstyle=f"round,pad=0,rounding_size={rs}",
                                    fc=fill, ec=stroke, lw=1.4, zorder=z))
        if k == "process":
            ax.plot([x - w / 2 + 7] * 2, [y - h / 2, y + h / 2], color=stroke, lw=1.0, zorder=z + 1)
            ax.plot([x + w / 2 - 7] * 2, [y - h / 2, y + h / 2], color=stroke, lw=1.0, zorder=z + 1)
        _text(ax, x, y, n.text)


def _draw_block(ax, n: Node, fill, stroke, th):
    x, y, w, h = n.x, n.y, n.w, n.h
    left, top = x - w / 2, y - h / 2
    ax.add_patch(Rectangle((left, top), w, h, fc="white", ec=stroke, lw=1.4, zorder=4))
    cy = top + 6
    if n.stereotype:
        cy += SMALL_PX * 0.65
        _text(ax, x, cy, f"«{n.stereotype}»", size=SMALL_PX)
        cy += SMALL_PX * 0.75
    name_lines = n.text.split("\n")
    head_h = len(name_lines) * TITLE_PX * 1.35
    for i, line in enumerate(name_lines):
        _text(ax, x, cy + TITLE_PX * 0.7 + i * TITLE_PX * 1.35, line, size=TITLE_PX, bold=True,
              italic=(n.kind == "object"))
    cy += head_h + 6
    # header shading
    ax.add_patch(Rectangle((left, top), w, cy - top, fc=fill, ec="none", zorder=4))
    for title, lines in n.compartments:
        ax.plot([left, left + w], [cy, cy], color=stroke, lw=1.0, zorder=5)
        cy += 4
        if title:
            _text(ax, x, cy + SMALL_PX * 0.6, title, size=SMALL_PX, italic=True)
            cy += SMALL_PX * 1.4
        for line in lines:
            _text(ax, left + 10, cy + LINE_H / 2, line, ha="left")
            cy += LINE_H
        cy += 4


def _draw_control_box(ax, n: Node, fill, stroke, th):
    """A control-structure box: the title, then the responsibility, the
    algorithms (orange) and the process model (blue) as stacked sections.
    The kind sets the border: double for the controlled process, dashed for
    the environment, rounded for a human controller, plain otherwise; a
    sensor is an ellipse-ended box and an actuator a box with a thick side."""
    x, y, w, h = n.x, n.y, n.w, n.h
    left, top = x - w / 2, y - h / 2
    k = n.kind
    z = 4
    if k == "human_controller":
        ax.add_patch(FancyBboxPatch((left, top), w, h, boxstyle="round,pad=0,rounding_size=12",
                                    fc=fill, ec=stroke, lw=1.5, zorder=z))
    elif k == "environment":
        ax.add_patch(Rectangle((left, top), w, h, fc=fill, ec=stroke, lw=1.5, ls=(0, (6, 3)), zorder=z))
    elif k == "controlled_process":
        ax.add_patch(Rectangle((left, top), w, h, fc=fill, ec=stroke, lw=1.5, zorder=z))
        ax.add_patch(Rectangle((left + 3.5, top + 3.5), w - 7, h - 7, fc="none", ec=stroke, lw=1.2, zorder=z + 1))
    elif k == "sensor":
        ax.add_patch(FancyBboxPatch((left, top), w, h, boxstyle=f"round,pad=0,rounding_size={h / 2}",
                                    fc=fill, ec=stroke, lw=1.5, zorder=z))
    elif k == "actuator":
        ax.add_patch(Rectangle((left, top), w, h, fc=fill, ec=stroke, lw=1.5, zorder=z))
        ax.add_patch(Rectangle((left, top), 6, h, fc=stroke, ec=stroke, lw=0, zorder=z + 1))
    else:  # controller, external_system
        ax.add_patch(Rectangle((left, top), w, h, fc=fill, ec=stroke, lw=1.5, zorder=z))
    sections = control_sections(n)
    title_lines = n.lines or [n.label]
    title_h = len(title_lines) * TITLE_PX * 1.35
    if not sections:
        for i, line in enumerate(title_lines):
            _text(ax, x, y - title_h / 2 + TITLE_PX * 0.7 + i * TITLE_PX * 1.35, line, size=TITLE_PX, bold=True)
        return
    cy = top + CONTROL_PAD
    for i, line in enumerate(title_lines):
        _text(ax, x, cy + TITLE_PX * 0.7 + i * TITLE_PX * 1.35, line, size=TITLE_PX, bold=True)
    cy += title_h + CONTROL_PAD * 0.6
    inset = 4.0 if k == "controlled_process" else 0.0
    for kind, lines in sections:
        sh = control_section_height(lines)
        if kind in ("algorithms", "process_model"):
            sfill, sstroke = th["cs_" + kind]
            ax.add_patch(Rectangle((left + inset, cy), w - 2 * inset, sh, fc=sfill, ec=sstroke, lw=0.9,
                                   zorder=z + 2))
        else:
            ax.plot([left + inset, left + w - inset], [cy, cy], color=stroke, lw=0.8, zorder=z + 2)
        ty = cy + CONTROL_SECTION_GAP
        for j, line in enumerate(lines):
            bold = kind == "process_model" and j == 0 and bool(n.process_model and n.process_model[0])
            _text(ax, left + CONTROL_PAD, ty + LINE_H / 2 + j * LINE_H, line, ha="left", bold=bold)
        cy += sh


# -------------------------------------------------------------- edges -----
def _draw_edge(ax, d: Diagram, e: Edge, th):
    if not e.points:
        return
    pts = list(e.points)
    color = th[e.kind] if e.kind in ("control_action", "feedback") else th["edge"]
    ls = {"solid": "-", "dashed": (0, (5, 3)), "dotted": (0, (1.5, 2.5))}[e.style]
    if e.kind in DASHED_EDGE_KINDS:
        ls = (0, (5, 3))
    lw = 1.5 if e.kind in ("control_action", "feedback") else 1.3
    head = {"flow": "filled", "dependency": "open", "satisfy": "open", "derive": "open",
            "verify": "open", "refine": "open", "allocate": "open", "generalization": "triangle",
            "composition": "none", "aggregation": "none", "association": "none",
            "connector": "none", "itemflow": "filled",
            "control_action": "filled", "feedback": "filled"}[e.kind]
    tail = {"composition": "fdiamond", "aggregation": "odiamond"}.get(e.kind, "none")

    # shorten line for decorations
    if head == "triangle":
        pts[-1] = _back_off(pts[-2], pts[-1], 13)
    if tail != "none":
        pts[0] = _back_off(pts[1], pts[0], 15)
    xs, ys = zip(*pts, strict=True)
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, zorder=2, solid_capstyle="round", solid_joinstyle="round")

    # ports (IBD connectors)
    if e.src_port:
        _port(ax, e.points[0], e.src_port, th, e.points[1])
    if e.dst_port:
        _port(ax, e.points[-1], e.dst_port, th, e.points[-2])

    if head == "filled":
        _arrow(ax, e.points[-2], e.points[-1], color, filled=True)
    elif head == "open":
        _arrow(ax, e.points[-2], e.points[-1], color, filled=False)
    elif head == "triangle":
        _triangle(ax, e.points[-2], e.points[-1], color)
    if tail == "fdiamond":
        _diamond(ax, e.points[1], e.points[0], color, filled=True)
    elif tail == "odiamond":
        _diamond(ax, e.points[1], e.points[0], color, filled=False)


def _draw_edge_label(ax, e: Edge, th):
    """Draw the label where :func:`asi_escher.layout` placed it.

    The text is the same :func:`~asi_escher.metrics.edge_label` the layout
    measured, anchored with the ``label_ha`` / ``label_va`` it chose (a back
    edge's label hangs right of its vertical channel, or below it after a
    left-to-right transpose), so the drawn box is the one the layout kept
    clear of nodes and other labels.
    """
    label = edge_label(e)
    if not label or not e.label_pos:
        return
    x, y = e.label_pos
    color = th[e.kind] if e.kind in ("control_action", "feedback") else th["ink"]
    _text(ax, x, y, label, size=SMALL_PX, color=color, ha=e.label_ha, va=e.label_va, bg=th["label_bg"])


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return dx / L, dy / L


def _back_off(a, b, dist):
    ux, uy = _unit(a, b)
    return (b[0] - ux * dist, b[1] - uy * dist)


def _arrow(ax, a, b, color, filled=True, size=11.0):
    ux, uy = _unit(a, b)
    px, py = -uy, ux
    tip = b
    base = (b[0] - ux * size, b[1] - uy * size)
    lt = (base[0] + px * size * 0.42, base[1] + py * size * 0.42)
    r = (base[0] - px * size * 0.42, base[1] - py * size * 0.42)
    if filled:
        ax.add_patch(Polygon([tip, lt, r], closed=True, fc=color, ec=color, lw=1.0, zorder=3))
    else:
        ax.plot([lt[0], tip[0], r[0]], [lt[1], tip[1], r[1]], color=color, lw=1.3, zorder=3)


def _triangle(ax, a, b, color, size=14.0):
    ux, uy = _unit(a, b)
    px, py = -uy, ux
    base = (b[0] - ux * size, b[1] - uy * size)
    lt = (base[0] + px * size * 0.5, base[1] + py * size * 0.5)
    r = (base[0] - px * size * 0.5, base[1] - py * size * 0.5)
    ax.add_patch(Polygon([b, lt, r], closed=True, fc="white", ec=color, lw=1.3, zorder=3))


def _diamond(ax, a, b, color, filled=True, size=16.0):
    """Diamond with its tip at b, pointing away from a."""
    ux, uy = _unit(a, b)
    px, py = -uy, ux
    mid = (b[0] - ux * size / 2, b[1] - uy * size / 2)
    back = (b[0] - ux * size, b[1] - uy * size)
    lt = (mid[0] + px * size * 0.33, mid[1] + py * size * 0.33)
    r = (mid[0] - px * size * 0.33, mid[1] - py * size * 0.33)
    ax.add_patch(Polygon([b, lt, back, r], closed=True, fc=color if filled else "white",
                         ec=color, lw=1.2, zorder=3))


def _port(ax, p, name, th, toward):
    s = 10
    ax.add_patch(Rectangle((p[0] - s / 2, p[1] - s / 2), s, s, fc="white", ec=th["edge"], lw=1.2, zorder=5))
    ux, uy = _unit(p, toward)
    # label beside the port, offset perpendicular to the connector
    if abs(ux) > abs(uy):
        _text(ax, p[0] + ux * 4, p[1] - 11, name, size=SMALL_PX - 1.5, ha="center", va="bottom")
    else:
        _text(ax, p[0] + 9, p[1] + uy * 4, name, size=SMALL_PX - 1.5, ha="left")
