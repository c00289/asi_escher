"""The ``gantt`` kind: tasks as bars on a time scale.

A gantt chart is not a graph layout: every task is a row, its bar runs from
its start date to its end date on a shared day scale, the periods (sprints,
quarters) and the months head the scale, a group opens a band of rows and
the dependencies are drawn as elbows from the end of one bar to the start
of the next.  This module computes that geometry (:func:`layout_gantt`),
which :mod:`asi_escher.layout` dispatches to, and the pieces of the exports
that are specific to the kind.  The renderer's drawing lives in
:mod:`asi_escher.render` with the other kinds.

All geometry is in pixels at 100 dpi, y pointing down, like every other
kind.  Dates are ISO ``YYYY-MM-DD`` strings; an end date is inclusive, so a
one-day task spans one day of the scale.
"""
from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable

from .metrics import FONT_PX, SMALL_PX, text_width
from .model import GANTT_NODE_KINDS, Diagram, LayoutIssue, Node

ROW_H = 26.0            # height of a task row
GROUP_H = 24.0          # height of a group band
BAR_H = 16.0            # height of a task bar
MILESTONE = 14.0        # side of a milestone's diamond
HEADER_H = 22.0         # height of one header band (periods, months)
LABEL_PAD = 8.0         # padding of the title and owner columns
NOTE_GAP = 5.0          # gap between a bar and its note
EDGE_LEAD = 6.0         # the horizontal lead of a dependency out of and into a bar
MIN_TIMELINE = 240.0    # narrowest time scale
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def parse_date(value: str, what: str = "date") -> _dt.date:
    """An ISO ``YYYY-MM-DD`` string as a date; ``ValueError`` names ``what`` otherwise."""
    try:
        return _dt.date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be an ISO date (YYYY-MM-DD), got {value!r}") from exc


def is_task(n: Node) -> bool:
    """True for a node of a gantt chart: a task or a milestone with a start
    date.  A chain's milestone shares the kind name and has no dates, so the
    renderer and the exporters tell the two apart by this."""
    return n.kind in GANTT_NODE_KINDS and bool(n.start)


def task_span(n: Node) -> tuple[_dt.date, _dt.date]:
    return parse_date(n.start, f"start of task {n.id!r}"), parse_date(n.end, f"end of task {n.id!r}")


def rows_of(d: Diagram) -> list[dict]:
    """The rows of the chart in drawing order: a ``group`` row whenever a
    task's group differs from the previous task's, then the ``task`` row.
    Each row is ``{"kind", "id" | "title"}`` before layout; the layout adds
    ``y`` (the row's top) and ``h``."""
    rows: list[dict] = []
    current: str | None = None
    for n in d.real_nodes():
        if n.group and n.group != current:
            rows.append({"kind": "group", "title": n.group})
        current = n.group or current
        rows.append({"kind": "task", "id": n.id})
    return rows


def layout_gantt(d: Diagram, opts) -> Diagram:
    """Fill every task's bar geometry, the dependency polylines, the canvas
    size and ``d.gantt`` (the chart's chrome: the columns, the header, the
    rows, the period and month marks, the today line, the notes)."""
    d.validate()
    d.issues = []
    for nid in [k for k, n in d.nodes.items() if n.kind == "dummy"]:
        del d.nodes[nid]
    for e in d.edges:
        e.back = False
        e.path = []
        e.points = []
        e.label_pos = None
        e.label_ha = e.label_va = "center"
    tasks = d.real_nodes()
    for n in tasks:
        n.lines = [n.label] if n.label else [""]
    ppd = float(getattr(opts, "day_px", 4.0))
    margin = float(opts.margin)

    # the time scale: every date on the chart, a day of air at both ends
    dates: list[_dt.date] = []
    spans = {n.id: task_span(n) for n in tasks}
    for a, b in spans.values():
        dates += [a, b]
    for p in d.periods:
        dates += [parse_date(p.start, f"start of period {p.label!r}"), parse_date(p.end, f"end of period {p.label!r}")]
    today = parse_date(d.today, "today") if d.today else None
    if today:
        dates.append(today)
    if not dates:
        dates = [_dt.date.today()]
    t0, t1 = min(dates) - _dt.timedelta(days=1), max(dates) + _dt.timedelta(days=1)
    timeline = max(MIN_TIMELINE, ((t1 - t0).days + 1) * ppd)
    ppd = timeline / ((t1 - t0).days + 1)

    def xof(day: _dt.date, end: bool = False) -> float:
        """The x of a day's left edge, or of its right edge when ``end``."""
        return x0 + ((day - t0).days + (1 if end else 0)) * ppd

    # the columns: titles (bold), owners (small), then the scale
    rows = rows_of(d)
    titles = [n.label for n in tasks] + [r["title"] for r in rows if r["kind"] == "group"]
    title_w = max([text_width(t, FONT_PX, bold=True) for t in titles] + [60.0]) + 2 * LABEL_PAD
    owners = [n.owner for n in tasks if n.owner]
    owner_w = (max(text_width(o, SMALL_PX) for o in owners) + 2 * LABEL_PAD) if owners else 0.0
    x0 = margin + title_w + owner_w
    x1 = x0 + timeline
    header = HEADER_H * (2 if d.periods else 1)
    y0 = margin
    rows_top = y0 + header

    # the rows
    y = rows_top
    for r in rows:
        r["y"] = y
        r["h"] = GROUP_H if r["kind"] == "group" else ROW_H
        y += r["h"]
    rows_bottom = y
    centre = {r["id"]: r["y"] + r["h"] / 2 for r in rows if r["kind"] == "task"}
    for n in tasks:
        a, b = spans[n.id]
        n.y = centre[n.id]
        if n.kind == "milestone":
            n.w = n.h = MILESTONE
            n.x = xof(a) + ppd / 2
        else:
            left, right = xof(a), xof(b, end=True)
            n.w, n.h = max(right - left, 2.0), BAR_H
            n.x = (left + right) / 2

    # the notes hang right of the bars; the canvas grows to hold them
    notes = []
    right_most = x1
    for n in tasks:
        if n.note:
            nx = n.right + NOTE_GAP
            notes.append((n.id, nx, n.y, n.note))
            right_most = max(right_most, nx + text_width(n.note, SMALL_PX))

    # the header marks: periods by their dates, months at their first day
    periods = [(p.label, xof(parse_date(p.start)), xof(parse_date(p.end), end=True)) for p in d.periods]
    months = []
    day = t0.replace(day=1)
    while day <= t1:
        nxt = (day.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
        label = f"{MONTHS[day.month - 1]} {day.year}"
        at = max(day, t0)
        # the month the scale starts in is labelled at the start, when what is left of it has room
        if day >= t0 or (min(nxt, t1) - at).days * ppd >= text_width(label, SMALL_PX - 1) + 8:
            months.append((label, xof(at)))
        day = nxt
    today_x = xof(today) + ppd / 2 if today else None

    # the dependencies: an elbow from the end of one bar to the start of the next
    for e in d.edges:
        _route_dependency(d, e, rows, centre)

    d.width = right_most + margin
    d.height = rows_bottom + margin
    d.lane_top = d.lane_bottom = d.lane_header = 0.0
    d.gantt = {
        "title_x": margin + LABEL_PAD, "owner_x": margin + title_w + LABEL_PAD, "x0": x0, "x1": x1,
        "y0": y0, "rows_top": rows_top, "rows_bottom": rows_bottom, "ppd": ppd, "t0": t0.isoformat(),
        "t1": t1.isoformat(), "periods": periods, "months": months, "today_x": today_x, "rows": rows,
        "notes": notes,
    }
    return d


def _route_dependency(d: Diagram, e, rows: list[dict], centre: dict) -> None:
    p, s = d.nodes[e.src], d.nodes[e.dst]
    a = (p.right, p.y)
    b = (s.left, s.y)
    if e.src == e.dst:
        e.points = [a, (a[0] + EDGE_LEAD, a[1]), (a[0] + EDGE_LEAD, a[1] - BAR_H), (a[0], a[1] - BAR_H)]
        e.back = True
        return
    if abs(a[1] - b[1]) < 0.5:
        e.points = [a, b] if b[0] > a[0] else [a, (a[0] + EDGE_LEAD, a[1]), (a[0] + EDGE_LEAD, a[1] - BAR_H),
                                                (b[0] - EDGE_LEAD, a[1] - BAR_H), (b[0] - EDGE_LEAD, b[1]), b]
        e.back = b[0] <= a[0]
        return
    index = {r["id"]: i for i, r in enumerate(rows) if r["kind"] == "task"}
    lo, hi = sorted((index[e.src], index[e.dst]))
    between = [d.nodes[r["id"]] for r in rows[lo + 1:hi] if r["kind"] == "task"]

    def crossings(cx: float) -> int:
        return sum(1 for n in between if n.left - 2 <= cx <= n.right + 2)

    if b[0] >= a[0]:
        # forward: one vertical channel in the gap between the bars, just before the successor unless a
        # bar sits there; a gap too tight for a lead at both ends (the next day at a few px a day, the
        # normal course of a plan) takes its middle
        gap = b[0] - a[0]
        candidates = [b[0] - EDGE_LEAD, a[0] + EDGE_LEAD] if gap >= 2 * EDGE_LEAD else [a[0] + gap / 2]
        cx = min(candidates, key=lambda c: (crossings(c), candidates.index(c)))
        e.points = [a, (cx, a[1]), (cx, b[1]), b]
    else:
        # the successor starts before the predecessor ends: out, along a row boundary, back in
        boundary = rows[index[e.src]]["y"] + (rows[index[e.src]]["h"] if b[1] > a[1] else 0.0)
        cx1, cx2 = a[0] + EDGE_LEAD, b[0] - EDGE_LEAD
        e.points = [a, (cx1, a[1]), (cx1, boundary), (cx2, boundary), (cx2, b[1]), b]
        e.back = True
        cx = cx2
    hit = [n.id for n in between if n.left - 2 <= cx <= n.right + 2]
    for nid in hit:
        d.issues.append(LayoutIssue("edge_through_node", f"dependency {e.src}->{e.dst} passes through the bar "
                                    f"of {nid}", edge=(e.src, e.dst), node=nid))


# ------------------------------------------------------------- exports -----
def mermaid_gantt(d: Diagram, mid, statuses: dict) -> str:
    """The chart as Mermaid ``gantt`` source: one ``section`` per group, one
    task line per bar with its status as the tag (``done``, ``active``,
    ``crit`` for blocked and late) and ``milestone`` for a milestone."""
    out = [f"---\ntitle: {d.title}\n---", "gantt", "  dateFormat YYYY-MM-DD", "  axisFormat %d %b"]
    if d.periods:
        out.append("  %% periods: " + "; ".join(f"{p.label} {p.start} to {p.end}" for p in d.periods))
    if d.today:
        out.append(f"  %% today: {d.today}")
    current: str | None = None
    for n in d.real_nodes():
        if n.group and n.group != current:
            out.append(f"  section {_mermaid_text(n.group)}")
            current = n.group
        tags = []
        status = statuses.get(n.id, "pending")
        if n.kind == "milestone":
            tags.append("milestone")
        if status in ("done", "active"):
            tags.append(status)
        elif status in ("blocked", "late"):
            tags.append("crit")
        tags.append(mid(n.id))
        span = f"{n.start}, 0d" if n.kind == "milestone" else f"{n.start}, {_mermaid_end(n.end)}"
        out.append(f"  {_mermaid_text(n.label)} :{', '.join(tags)}, {span}")
    deps = [f"  %% {mid(e.src)} -> {mid(e.dst)}" for e in d.edges]
    if deps:
        out.append("  %% dependencies (Mermaid draws none)")
        out.extend(deps)
    return "\n".join(out) + "\n"


def _mermaid_text(s: str) -> str:
    return s.replace(":", " -").replace("\n", " ")


def _mermaid_end(end: str) -> str:
    """Mermaid's end date is exclusive; the chart's is inclusive."""
    return (parse_date(end) + _dt.timedelta(days=1)).isoformat()


def dot_label(n: Node) -> str:
    """The HTML label of a task in DOT: the title, the owner, the dates."""
    from .export import _html

    label = f"<B>{_html(n.label)}</B>"
    if n.owner:
        label += f'<BR/><FONT POINT-SIZE="9">{_html(n.owner)}</FONT>'
    span = n.start if n.kind == "milestone" or n.start == n.end else f"{n.start} to {n.end}"
    label += f'<BR/><FONT POINT-SIZE="9">{_html(span)}</FONT>'
    if n.note:
        label += f'<BR/><FONT POINT-SIZE="9"><I>{_html(n.note)}</I></FONT>'
    return label


def drawio_chrome(d: Diagram, theme: dict) -> Iterable[tuple[str, str, str, tuple[float, float, float, float]]]:
    """The draw.io cells of the chart that are not bars or dependencies:
    ``(id, value, style, (x, y, w, h))`` for the header bands, the group
    bands, the row stripes, the grid lines, the titles, the owners, the notes
    and the today line, in drawing order (background first)."""
    g = d.gantt
    x0, x1, y0 = g["x0"], g["x1"], g["y0"]
    rows_top, rows_bottom = g["rows_top"], g["rows_bottom"]
    cells = []
    text = "text;html=1;strokeColor=none;fillColor=none;whiteSpace=wrap;"
    small = theme["chain_small"]
    for i, r in enumerate(g["rows"]):
        if r["kind"] == "group":
            cells.append((f"group_{i}", f"<b>{_x(r['title'])}</b>",
                          f"rounded=0;html=1;align=left;spacingLeft={LABEL_PAD:.0f};fontStyle=1;"
                          f"fillColor={theme['gantt_group']};strokeColor=none;",
                          (g["title_x"] - LABEL_PAD, r["y"], d.width - 2 * (g["title_x"] - LABEL_PAD), r["h"])))
        elif i % 2:
            cells.append((f"stripe_{i}", "", f"rounded=0;fillColor={theme['lane_b']};strokeColor=none;",
                          (g["title_x"] - LABEL_PAD, r["y"], d.width - 2 * (g["title_x"] - LABEL_PAD), r["h"])))
    for i, (label, xa, xb) in enumerate(g["periods"]):
        fill = theme["gantt_header"] if i % 2 == 0 else theme["lane_b"]
        cells.append((f"period_{i}", f"<b>{_x(label)}</b>",
                      f"rounded=0;html=1;align=center;fontSize=9;fontStyle=1;fillColor={fill};"
                      f"strokeColor={theme['gantt_grid']};", (xa, y0, xb - xa, HEADER_H)))
        cells.append((f"grid_{i}", "", f"rounded=0;fillColor={theme['gantt_grid']};strokeColor=none;",
                      (xa, rows_top, 1.0, rows_bottom - rows_top)))
    months_y = y0 + (HEADER_H if g["periods"] else 0.0)
    cells.append(("months", "", f"rounded=0;fillColor=none;strokeColor={theme['gantt_grid']};",
                  (x0, months_y, x1 - x0, HEADER_H)))
    for i, (label, x) in enumerate(g["months"]):
        cells.append((f"month_{i}", _x(label), f"{text}align=left;fontSize=9;spacingLeft=2;",
                      (x, months_y, max(HEADER_H * 3, 70.0), HEADER_H)))
        cells.append((f"tick_{i}", "", f"rounded=0;fillColor={theme['gantt_grid']};strokeColor=none;",
                      (x, months_y, 1.0, rows_bottom - months_y)))
    for n in d.real_nodes():
        cells.append((f"title_{n.id}", f"<b>{_x(n.label)}</b>", f"{text}align=left;",
                      (g["title_x"], n.y - ROW_H / 2, g["owner_x"] - g["title_x"] - LABEL_PAD, ROW_H)))
        if n.owner:
            cells.append((f"owner_{n.id}", _x(n.owner), f"{text}align=left;fontSize=9;fontColor={small};",
                          (g["owner_x"], n.y - ROW_H / 2, x0 - g["owner_x"] - LABEL_PAD, ROW_H)))
    for nid, nx, ny, note in g["notes"]:
        # a white backing, so a dependency's channel running past the bar does not cross the words
        cells.append((f"note_{nid}", _x(note), f"{text}align=left;fontSize=9;fontColor={small};"
                      f"labelBackgroundColor={theme['label_bg']};",
                      (nx, ny - ROW_H / 2, text_width(note, SMALL_PX) + 8, ROW_H)))
    if g["today_x"] is not None:
        cells.append(("today", "", f"rounded=0;fillColor={theme['today']};strokeColor=none;",
                      (g["today_x"] - 1, months_y, 2.0, rows_bottom - months_y)))
        cells.append(("today_label", "today", f"{text}align=left;fontSize=9;fontColor={theme['today']};",
                      (g["today_x"] + 3, rows_top, 40.0, 14.0)))
    return cells


def _x(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
