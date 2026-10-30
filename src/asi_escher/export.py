"""Export a Diagram as Graphviz DOT, Mermaid source text and draw.io XML.

None of the tools needs to be installed to produce the text; DOT and Mermaid
are meant for pasting into an online renderer, a Markdown file, or a CI job
that has `dot` / `mmdc` available.  The draw.io file (:func:`to_drawio`)
carries the positions of asi_escher's own layout, so draw.io (or the VS Code
draw.io extension) opens it with every box exactly where the layout put it
and a person can refine it by hand from there.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from .metrics import DASHED_EDGE_KINDS, SMALL_PX, chain_sublines, control_sections, edge_label, text_box
from .model import CHAIN_NODE_KINDS, CONTROL_NODE_KINDS, Diagram, Edge, Node
from .provenance import drawio_comment, drawio_note, slug
from .render import THEME


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("\n", "<BR/>"))


def _chain_facts(d: Diagram) -> tuple[dict, set]:
    """The effective statuses and the critical-path edges of a chain (empty
    for any other kind), computed once per export."""
    if d.kind != "chain" and not any(n.kind in CHAIN_NODE_KINDS for n in d.nodes.values()):
        return {}, set()
    return d.statuses(), d.critical_edges()


def _status_colours(n: Node, status: str) -> tuple[str, str]:
    fill, stroke = THEME.get("status_" + status, THEME["status_pending"])
    return n.fill or fill, n.stroke or stroke


# ====================================================================== DOT
def to_dot(d: Diagram) -> str:
    out = [f"digraph {_q(d.title)} {{"]
    out.append(f'  graph [rankdir={d.direction}, splines=ortho, nodesep=0.4, ranksep=0.55, '
               f'fontname="Helvetica", label={_q(d.frame or d.title)}, labelloc=t, labeljust=l];')
    out.append('  node  [fontname="Helvetica", fontsize=11, style="filled", penwidth=1.3];')
    out.append('  edge  [fontname="Helvetica", fontsize=9, color="#3E4C59", arrowsize=0.8];')
    real = [n for n in d.nodes.values() if n.kind != "dummy"]
    statuses, critical = _chain_facts(d)
    if d.lanes:
        for i, ln in enumerate(d.lanes):
            fill = THEME["lane_a"] if i % 2 == 0 else THEME["lane_b"]
            out.append(f"  subgraph cluster_{_ident(ln.id)} {{")
            out.append(f"    label={_q(ln.title)}; style=filled; fillcolor={_q(fill)}; color=\"#B8C2CC\";")
            for n in real:
                if n.lane == ln.id:
                    out.append("    " + _dot_node(n, statuses.get(n.id, "pending")))
            out.append("  }")
        for n in real:
            if n.lane is None or d.lane_index(n.lane) < 0:
                out.append("  " + _dot_node(n, statuses.get(n.id, "pending")))
    else:
        for n in real:
            out.append("  " + _dot_node(n, statuses.get(n.id, "pending")))
    for e in d.edges:
        out.append("  " + _dot_edge(e, (e.src, e.dst) in critical))
    out.append("}")
    return "\n".join(out) + "\n"


def _ident(s: str) -> str:
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in s)
    return out if out and not out[0].isdigit() else "n_" + out


def _dot_node(n: Node, status: str = "pending") -> str:
    k = n.kind
    fill, stroke = THEME.get(k, ("#F4F4F4", "#5F6B7A"))
    fill = n.fill or fill
    stroke = n.stroke or stroke
    if k in CHAIN_NODE_KINDS:
        fill, stroke = _status_colours(n, status)
    base = f'fillcolor={_q(fill)}, color={_q(stroke)}'
    if k == "start":
        attrs = 'shape=circle, label="", width=0.22, height=0.22, fixedsize=true, fillcolor="#1F2933", color="#1F2933"'
    elif k == "end":
        attrs = ('shape=doublecircle, label="", width=0.2, height=0.2, fixedsize=true, '
                 'fillcolor="#1F2933", color="#1F2933"')
    elif k == "flowfinal":
        attrs = 'shape=circle, label="X", width=0.26, fixedsize=true, fillcolor="white", color="#1F2933"'
    elif k in ("fork", "join"):
        attrs = 'shape=box, label="", height=0.06, width=1.4, fixedsize=true, fillcolor="#1F2933", color="#1F2933"'
    elif k == "decision":
        attrs = f'shape=diamond, label={_q(n.label)}, {base}'
    elif k == "merge":
        attrs = f'shape=diamond, label="", width=0.3, height=0.3, fixedsize=true, {base}'
    elif k == "note":
        attrs = f'shape=note, label={_q(n.label)}, {base}, fontsize=10'
    elif k == "io":
        attrs = f'shape=parallelogram, label={_q(n.label)}, {base}'
    elif k == "document":
        attrs = f'shape=note, label={_q(n.label)}, {base}'
    elif k == "database":
        attrs = f'shape=cylinder, label={_q(n.label)}, {base}'
    elif k == "state":
        attrs = f'shape=box, style="rounded,filled", label={_q(n.label)}, {base}'
    elif k in ("block", "requirement", "part", "object"):
        attrs = f'shape=plain, label=<{_dot_table(n, fill, stroke)}>'
    elif k in CONTROL_NODE_KINDS:
        style = {"human_controller": "rounded,filled", "environment": "dashed,filled",
                 "sensor": "rounded,filled"}.get(k, "filled")
        extra = ", peripheries=2" if k == "controlled_process" else ""
        attrs = f'shape=box, style="{style}", label=<{_dot_control_table(n)}>, {base}{extra}'
    elif k in CHAIN_NODE_KINDS:
        shape = {"milestone": "hexagon", "gate": "box", "external": "box"}.get(k, "box")
        style = {"event": "rounded,filled", "external": "dashed,filled"}.get(k, "filled")
        extra = ", peripheries=2" if k == "gate" else ""
        label = f"<B>{_html(n.label)}</B>"
        for _kind, text in chain_sublines(n):
            label += f'<BR/><FONT POINT-SIZE="9">{_html(text)}</FONT>'
        attrs = f'shape={shape}, style="{style}", label=<{label}>, {base}{extra}'
    else:  # action / process
        attrs = f'shape=box, style="rounded,filled", label={_q(n.label)}, {base}'
    return f'{_q(n.id)} [{attrs}];'


def _dot_table(n: Node, fill: str, stroke: str) -> str:
    rows = []
    head = ""
    if n.stereotype:
        head += f'<FONT POINT-SIZE="9">&laquo;{_html(n.stereotype)}&raquo;</FONT><BR/>'
    head += f"<B>{_html(n.label)}</B>"
    rows.append(f'<TR><TD BGCOLOR="{fill}" ALIGN="CENTER">{head}</TD></TR>')
    for title, lines in n.compartments:
        body = ""
        if title:
            body += f'<I><FONT POINT-SIZE="9">{_html(title)}</FONT></I><BR ALIGN="CENTER"/>'
        for line in lines:
            body += f'{_html(line)}<BR ALIGN="LEFT"/>'
        rows.append(f'<TR><TD ALIGN="LEFT" BALIGN="LEFT">{body}</TD></TR>')
    return (f'<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6" COLOR="{stroke}">'
            + "".join(rows) + "</TABLE>")


def _dot_control_table(n: Node) -> str:
    """The sections of a control-structure box as the rows of an HTML label."""
    rows = [f'<TR><TD ALIGN="CENTER"><B>{_html(n.label)}</B></TD></TR>']
    for kind, lines in control_sections(n):
        body = "".join(f'{_html(line)}<BR ALIGN="LEFT"/>' for line in lines)
        bg = ""
        if kind in ("algorithms", "process_model"):
            bg = f' BGCOLOR="{THEME["cs_" + kind][0]}"'
        rows.append(f'<TR><TD ALIGN="LEFT" BALIGN="LEFT"{bg}>{body}</TD></TR>')
    return '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">' + "".join(rows) + "</TABLE>"


def _dot_edge(e: Edge, critical: bool = False) -> str:
    attrs = []
    label = edge_label(e)
    if label:
        attrs.append(f"label={_q(label)}")
    if e.kind in ("blocks", "enables"):
        attrs.append(f"penwidth={2.6 if critical else (1.4 if e.kind == 'blocks' else 0.8)}")
    if e.kind == "informs":
        attrs += ["style=dashed, arrowhead=vee", "constraint=false"]      # orders nothing
    elif e.kind in ("control_action", "feedback"):
        color = THEME[e.kind]
        attrs.append(f'color={_q(color)}, fontcolor={_q(color)}, penwidth=1.5')
        if e.kind == "feedback":
            attrs.append("constraint=false")
    elif e.kind in DASHED_EDGE_KINDS:
        attrs.append("style=dashed, arrowhead=vee")
    elif e.kind == "generalization":
        attrs.append("arrowhead=empty")
    elif e.kind == "composition":
        attrs.append("dir=back, arrowtail=diamond")
    elif e.kind == "aggregation":
        attrs.append("dir=back, arrowtail=odiamond")
    elif e.kind in ("association", "connector"):
        attrs.append("arrowhead=none")
    if e.style == "dashed" and "style=" not in " ".join(attrs):
        attrs.append("style=dashed")
    if e.src_port:
        attrs.append(f"taillabel={_q(e.src_port)}")
    if e.dst_port:
        attrs.append(f"headlabel={_q(e.dst_port)}")
    if e.back and "constraint=false" not in attrs:
        attrs.append("constraint=false")
    a = f" [{', '.join(attrs)}]" if attrs else ""
    return f"{_q(e.src)} -> {_q(e.dst)}{a};"


# ================================================================== Mermaid
def to_mermaid(d: Diagram) -> str:
    if d.kind == "state":
        return _mermaid_state(d)
    if d.kind in ("bdd", "req"):
        return _mermaid_class(d)
    if d.kind == "chain":
        return _mermaid_chain(d)
    return _mermaid_flow(d)


_MERMAID_RESERVED = {"end", "subgraph", "graph", "flowchart", "style", "class", "click",
                     "classDef", "linkStyle", "direction", "default", "start", "state"}


def _mid(s: str) -> str:
    i = _ident(s)
    return i + "_" if i.lower() in _MERMAID_RESERVED else i


def _mq(s: str) -> str:
    return '"' + s.replace('"', "#quot;").replace("\n", "<br/>") + '"'


def _mermaid_node(n: Node) -> str:
    k, i, lab = n.kind, _mid(n.id), n.label
    if k == "start":
        return f'{i}((" "))'
    if k == "end":
        return f'{i}(((" ")))'
    if k == "flowfinal":
        return f'{i}(("X"))'
    if k in ("fork", "join"):
        return f'{i}[["&nbsp;"]]'
    if k in ("decision", "merge"):
        return f"{i}{{{_mq(lab or ' ')}}}"
    if k == "io":
        return f"{i}[/{_mq(lab)}/]"
    if k == "database":
        return f"{i}[({_mq(lab)})]"
    if k == "document":
        return f"{i}[{_mq(lab)}]"
    if k == "note":
        return f"{i}>{_mq(lab)}]"
    if k == "state":
        return f"{i}({_mq(lab)})"
    if k == "process":
        return f"{i}[[{_mq(lab)}]]"
    if k in ("block", "requirement", "part", "object"):
        text = (f"\u00ab{n.stereotype}\u00bb<br/>" if n.stereotype else "") + f"<b>{lab}</b>"
        for title, lines in n.compartments:
            text += "<br/>" + (f"<i>{title}</i><br/>" if title else "") + "<br/>".join(lines)
        return f"{i}[{_mq(text)}]"
    if k in CONTROL_NODE_KINDS:
        text = f"<b>{lab}</b>"
        heads = {"responsibility": "", "algorithms": "<i>Algorithms</i><br/>", "process_model": ""}
        for kind, lines in control_sections(n):
            text += "<br/>" + heads[kind] + "<br/>".join(lines)
        if k == "human_controller":
            return f"{i}({_mq(text)})"
        if k == "controlled_process":
            return f"{i}[[{_mq(text)}]]"
        if k == "sensor":
            return f"{i}([{_mq(text)}])"
        return f"{i}[{_mq(text)}]"
    return f"{i}[{_mq(lab)}]"


def _mermaid_flow(d: Diagram) -> str:
    out = [f"---\ntitle: {d.frame or d.title}\n---", f"flowchart {'TD' if d.direction == 'TB' else 'LR'}"]
    real = [n for n in d.nodes.values() if n.kind != "dummy"]
    placed = set()
    for ln in d.lanes:
        out.append(f"  subgraph {_mid(ln.id)} [{_mq(ln.title)}]")
        out.append("    direction " + ("TB" if d.direction == "TB" else "LR"))
        for n in real:
            if n.lane == ln.id:
                out.append("    " + _mermaid_node(n))
                placed.add(n.id)
        out.append("  end")
    for n in real:
        if n.id not in placed:
            out.append("  " + _mermaid_node(n))
    link_styles = []
    for i, e in enumerate(d.edges):
        dashed = e.style == "dashed" or e.kind in DASHED_EDGE_KINDS
        if e.kind in ("association", "connector"):
            arrow = "-.-" if dashed else "---"
        else:
            arrow = "-.->" if dashed else "-->"
        label = edge_label(e)
        if e.src_port or e.dst_port:
            label = " / ".join(x for x in (e.src_port, label, e.dst_port) if x)
        lab = f"|{_mq(label)}|" if label else ""
        out.append(f"  {_mid(e.src)} {arrow}{lab} {_mid(e.dst)}")
        if e.kind in ("control_action", "feedback"):
            link_styles.append(f"  linkStyle {i} stroke:{THEME[e.kind]},color:{THEME[e.kind]}")
    out.extend(link_styles)
    # styling
    for n in real:
        k = n.kind
        if k in ("start", "end"):
            out.append(f"  style {_mid(n.id)} fill:#1F2933,stroke:#1F2933,color:#fff")
        elif k in ("fork", "join"):
            out.append(f"  style {_mid(n.id)} fill:#1F2933,stroke:#1F2933,color:#1F2933")
        elif k in THEME and isinstance(THEME[k], tuple):
            fill, stroke = THEME[k]
            extra = ",stroke-dasharray:6 3" if k == "environment" else ""
            out.append(f"  style {_mid(n.id)} fill:{n.fill or fill},stroke:{n.stroke or stroke}{extra}")
    return "\n".join(out) + "\n"


def _mermaid_chain(d: Diagram) -> str:
    """A chain as ``flowchart LR``: one ``classDef`` per status, every event
    in the class of its effective status, a hexagon for a milestone, a
    subroutine box for a gate, a dashed border for an external event; the
    critical path's links thicker, ``informs`` dotted."""
    out = [f"---\ntitle: {d.title}\n---", f"flowchart {'TD' if d.direction == 'TB' else 'LR'}"]
    statuses, critical = _chain_facts(d)
    real = [n for n in d.nodes.values() if n.kind != "dummy"]
    for n in real:
        text = f"<b>{n.label}</b>" + "".join(f"<br/><small>{text}</small>" for _k, text in chain_sublines(n))
        i = _mid(n.id)
        if n.kind == "milestone":
            shape = f"{i}{{{{{_mq(text)}}}}}"
        elif n.kind == "gate":
            shape = f"{i}[[{_mq(text)}]]"
        else:
            shape = f"{i}[{_mq(text)}]"
        out.append(f"  {shape}:::{statuses.get(n.id, 'pending')}")
    link_styles = []
    for i, e in enumerate(d.edges):
        arrow = "-.->" if e.kind == "informs" or e.style == "dashed" else "-->"
        lab = f"|{_mq(e.label)}|" if e.label else ""
        out.append(f"  {_mid(e.src)} {arrow}{lab} {_mid(e.dst)}")
        if (e.src, e.dst) in critical:
            link_styles.append(f"  linkStyle {i} stroke-width:3px")
        elif e.kind == "enables":
            link_styles.append(f"  linkStyle {i} stroke-width:1px")
    out.extend(link_styles)
    for status in ("done", "active", "blocked", "pending", "late"):
        fill, stroke = THEME["status_" + status]
        out.append(f"  classDef {status} fill:{fill},stroke:{stroke},color:#1F2933")
    for n in real:
        if n.kind == "external":
            out.append(f"  style {_mid(n.id)} stroke-dasharray:6 3")
    return "\n".join(out) + "\n"


def _mermaid_state(d: Diagram) -> str:
    out = [f"---\ntitle: {d.title}\n---", "stateDiagram-v2"]
    if d.direction == "LR":
        out.append("  direction LR")
    real = [n for n in d.nodes.values() if n.kind != "dummy"]
    ids = {}
    for n in real:
        if n.kind in ("start", "end"):
            ids[n.id] = "[*]"
        else:
            ids[n.id] = _mid(n.id)
            if n.label and n.label != n.id:
                out.append(f"  {ids[n.id]} : {n.label.replace(chr(10), ' / ')}")
    for e in d.edges:
        lab = f" : {e.label}" if e.label else ""
        out.append(f"  {ids[e.src]} --> {ids[e.dst]}{lab}")
    return "\n".join(out) + "\n"


def _mermaid_class(d: Diagram) -> str:
    out = [f"---\ntitle: {d.frame or d.title}\n---", "classDiagram"]
    if d.direction == "LR":
        out.append("  direction LR")
    real = [n for n in d.nodes.values() if n.kind != "dummy"]
    for n in real:
        cid = _mid(n.id)
        out.append(f"  class {cid} {{")
        if n.stereotype:
            out.append(f"    <<{n.stereotype}>>")
        for title, lines in n.compartments:
            for line in lines:
                out.append(f"    {line.replace('(', '').replace(')', '') if title != 'operations' else line}")
        out.append("  }")
        if n.label != n.id:
            out.append(f'  class {cid}["{n.label.replace(chr(10), " ")}"]')
    rel = {"composition": "*--", "aggregation": "o--", "generalization": "<|--",
           "association": "--", "dependency": "..>", "satisfy": "..>", "derive": "..>",
           "verify": "..>", "refine": "..>", "allocate": "..>", "flow": "-->"}
    for e in d.edges:
        label = edge_label(e).replace("\n", " ")
        r = rel.get(e.kind, "-->")
        lab = f" : {label}" if label else ""
        if e.kind == "generalization":
            out.append(f"  {_mid(e.dst)} {r} {_mid(e.src)}{lab}")
        else:
            out.append(f"  {_mid(e.src)} {r} {_mid(e.dst)}{lab}")
    return "\n".join(out) + "\n"


# ================================================================== draw.io
def to_drawio(d: Diagram, provenance: bool = True, name: str | None = None) -> str:
    """The diagram as an uncompressed draw.io file (mxGraph XML).

    One vertex ``mxCell`` per node, its ``mxGeometry`` the x, y, width and
    height of asi_escher's layout; one edge ``mxCell`` per edge with the
    routed polyline as ``mxPoint`` waypoints and the label (the signal lines
    of a control action or feedback) as its value; swimlanes and a SysML
    frame as background rectangles; a control-structure box's sections as an
    HTML label with the renderer's colours.  Lays the diagram out first when
    that has not been done.  The text opens in draw.io and in the VS Code
    draw.io extension, every box where the layout put it.

    ``provenance`` writes an XML comment after the ``<mxfile>`` opening and a
    small grey note under the drawing saying that escher placed the boxes
    and that the ``<name>.png`` / ``<name>.svg`` beside the file are
    escher's renderings of this layout, not draw.io exports; ``name``
    defaults to the slug of the title.
    """
    if not d.width or not d.height:
        from .layout import layout
        layout(d)
    name = name or slug(d.title)
    ids = _DrawioIds()
    mxfile = ET.Element("mxfile", host="asi_escher", agent="asi_escher", type="device", compressed="false")
    if provenance:
        mxfile.append(ET.Comment(drawio_comment(name)))
    diagram = ET.SubElement(mxfile, "diagram", id=ids.take("diagram"), name=d.title)
    model = ET.SubElement(diagram, "mxGraphModel", dx="0", dy="0", grid="1", gridSize="10", guides="1",
                          tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1",
                          pageWidth=_num(d.width), pageHeight=_num(d.height), math="0", shadow="0")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    ids.take("0")
    ids.take("1")
    if d.frame:
        m = 14.0
        cell = ET.SubElement(root, "mxCell", id=ids.take("frame"), value=_xhtml(d.frame),
                             style="rounded=0;whiteSpace=wrap;html=1;align=left;verticalAlign=top;fontStyle=1;"
                                   f"fillColor=none;strokeColor={THEME['frame']};spacingLeft=6;",
                             vertex="1", parent="1")
        _geometry(cell, m, m, d.width - 2 * m, d.height - 2 * m)
    for i, ln in enumerate(d.lanes):
        fill = THEME["lane_a"] if i % 2 == 0 else THEME["lane_b"]
        if d.direction == "TB":
            x, y, w, h = ln.x0, d.lane_top, ln.x1 - ln.x0, d.lane_bottom - d.lane_top
            style = "verticalAlign=top;"
        else:
            x, y, w, h = d.lane_top, ln.x0, d.lane_bottom - d.lane_top, ln.x1 - ln.x0
            style = "horizontal=0;verticalAlign=top;"
        cell = ET.SubElement(root, "mxCell", id=ids.take(f"lane_{ln.id}"), value=_xhtml(ln.title),
                             style=f"rounded=0;whiteSpace=wrap;html=1;fontStyle=1;{style}"
                                   f"fillColor={fill};strokeColor={THEME['lane_line']};",
                             vertex="1", parent="1")
        _geometry(cell, x, y, w, h)
    statuses, critical = _chain_facts(d)
    node_ids = {}
    for n in d.real_nodes():
        node_ids[n.id] = ids.take(n.id)
        cell = ET.SubElement(root, "mxCell", id=node_ids[n.id], value=_drawio_label(n),
                             style=_drawio_node_style(n, statuses.get(n.id, "pending")), vertex="1", parent="1")
        _geometry(cell, n.left, n.top, n.w, n.h)
    for i, e in enumerate(d.edges, start=1):
        label = edge_label(e)
        if e.src_port or e.dst_port:
            label = " / ".join(x for x in (e.src_port, label, e.dst_port) if x)
        cell = ET.SubElement(root, "mxCell", id=ids.take(f"e{i}"), value=_xhtml(label),
                             style=_drawio_edge_style(e, d, (e.src, e.dst) in critical), edge="1", parent="1",
                             source=node_ids[e.src], target=node_ids[e.dst])
        geo = ET.SubElement(cell, "mxGeometry", relative="1")
        geo.set("as", "geometry")
        if e.points:
            pos = _drawio_label_position(e, label)
            if pos is not None:
                geo.set("x", _num(pos[0]))
                geo.set("y", "0")
            _point(geo, e.points[0], "sourcePoint")
            _point(geo, e.points[-1], "targetPoint")
            arr = ET.SubElement(geo, "Array")
            arr.set("as", "points")
            for x, y in e.points[1:-1]:
                _point(arr, (x, y))
            if pos is not None:
                _point(geo, pos[1], "offset")
    if provenance:
        cell = ET.SubElement(root, "mxCell", id=ids.take("provenance"), value=_xhtml(drawio_note(name)),
                             style="text;html=1;align=left;verticalAlign=middle;fontStyle=2;fontSize=9;"
                                   "fontColor=#9E9E9E;strokeColor=none;fillColor=none;whiteSpace=wrap;",
                             vertex="1", parent="1")
        _geometry(cell, 8, d.height + 4, max(d.width - 16, 200), 20)
    ET.indent(mxfile, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(mxfile, encoding="unicode") + "\n"


class _DrawioIds:
    """Unique cell ids: a node keeps its own id unless it is taken."""

    def __init__(self):
        self.used: set[str] = set()

    def take(self, wanted: str) -> str:
        cid = wanted or "cell"
        k = 1
        while cid in self.used:
            k += 1
            cid = f"{wanted}_{k}"
        self.used.add(cid)
        return cid


def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def _geometry(cell, x, y, w, h):
    g = ET.SubElement(cell, "mxGeometry", x=_num(x), y=_num(y), width=_num(w), height=_num(h))
    g.set("as", "geometry")


def _point(parent, pt, role: str | None = None):
    p = ET.SubElement(parent, "mxPoint", x=_num(pt[0]), y=_num(pt[1]))
    if role:
        p.set("as", role)
    return p


def _xhtml(s: str) -> str:
    """Text for an ``html=1`` label: escaped, newlines as ``<br>``."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")


def _drawio_label(n: Node) -> str:
    k = n.kind
    if k in ("start", "end", "fork", "join", "merge"):
        return ""
    if k == "flowfinal":
        return "X"
    if k in ("block", "requirement", "part", "object"):
        head = (f'<font style="font-size:9px">&laquo;{_xhtml(n.stereotype)}&raquo;</font><br>' if n.stereotype else "")
        head += f"<b>{_xhtml(n.label)}</b>"
        for title, lines in n.compartments:
            body = (f'<i><font style="font-size:9px">{_xhtml(title)}</font></i><br>' if title else "")
            body += "<br>".join(_xhtml(line) for line in lines)
            head += f'<div style="text-align:left;border-top:1px solid;padding:2px 6px">{body}</div>'
        return head
    if k in CONTROL_NODE_KINDS:
        stroke = n.stroke or THEME[k][1]
        head = f"<b>{_xhtml(n.label)}</b>"
        for kind, lines in control_sections(n):
            body = "<br>".join(_xhtml(line) for line in lines)
            if kind == "algorithms":
                fill, border = THEME["cs_algorithms"]
                css = f"background:{fill};border:1px solid {border};"
            elif kind == "process_model":
                fill, border = THEME["cs_process_model"]
                css = f"background:{fill};border:1px solid {border};"
                if n.process_model and n.process_model[0]:
                    first, _, rest = body.partition("<br>")
                    body = f"<b>{first}</b>" + (f"<br>{rest}" if rest else "")
            else:
                css = f"border-top:1px solid {stroke};"
            head += f'<div style="text-align:left;margin-top:4px;padding:3px 6px;{css}">{body}</div>'
        return head
    if k in CHAIN_NODE_KINDS:
        head = f"<b>{_xhtml(n.label)}</b>"
        for kind, text in chain_sublines(n):
            style = f"font-size:9px;color:{THEME['chain_small']}" + (";font-style:italic" if kind == "note" else "")
            head += f'<br><font style="{style}">{_xhtml(text)}</font>'
        return head
    return _xhtml(n.label)


def _drawio_node_style(n: Node, status: str = "pending") -> str:
    k = n.kind
    fill, stroke = THEME.get(k, ("#F4F4F4", "#5F6B7A"))
    fill = n.fill or fill
    stroke = n.stroke or stroke
    if k in CHAIN_NODE_KINDS:
        fill, stroke = _status_colours(n, status)
    colours = f"fillColor={fill};strokeColor={stroke};"
    text = "whiteSpace=wrap;html=1;"
    if k == "start":
        return f"ellipse;fillColor={THEME['bar']};strokeColor={THEME['bar']};"
    if k == "end":
        return f"ellipse;shape=doubleEllipse;fillColor={THEME['bar']};strokeColor={THEME['bar']};"
    if k == "flowfinal":
        return f"ellipse;fillColor=#FFFFFF;strokeColor={THEME['bar']};fontStyle=1;"
    if k in ("fork", "join"):
        return f"rounded=0;fillColor={THEME['bar']};strokeColor={THEME['bar']};"
    if k in ("decision", "merge"):
        return f"rhombus;{text}{colours}"
    if k == "note":
        return f"shape=note;size=12;{text}fontStyle=2;{colours}"
    if k == "io":
        return f"shape=parallelogram;perimeter=parallelogramPerimeter;{text}{colours}"
    if k == "document":
        return f"shape=document;boundedLbl=1;{text}{colours}"
    if k == "database":
        return f"shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=7;{text}{colours}"
    if k == "state":
        return f"rounded=1;arcSize=30;{text}{colours}"
    if k in ("block", "requirement", "part", "object"):
        return f"rounded=0;{text}verticalAlign=top;align=center;{colours}"
    if k in CONTROL_NODE_KINDS:
        sections = bool(control_sections(n))
        valign = "verticalAlign=top;spacingTop=2;" if sections else "verticalAlign=middle;"
        shape = {
            "human_controller": "rounded=1;arcSize=10;",
            "controlled_process": "shape=ext;double=1;",
            "environment": "rounded=0;dashed=1;dashPattern=6 3;",
            "sensor": "rounded=1;arcSize=50;",
            "actuator": "rounded=0;strokeWidth=2;",
        }.get(k, "rounded=0;")
        width = "" if "strokeWidth" in shape else "strokeWidth=1.5;"
        return f"{shape}{text}{valign}align=center;fontStyle=1;{colours}{width}"
    if k in CHAIN_NODE_KINDS:
        shape = {
            "milestone": "shape=hexagon;perimeter=hexagonPerimeter2;size=0.2;",
            "gate": "shape=ext;double=1;",
            "external": "rounded=0;dashed=1;dashPattern=6 3;",
        }.get(k, "rounded=1;arcSize=10;")
        return f"{shape}{text}align=center;{colours}strokeWidth=1.5;"
    if k == "process":
        return f"shape=process;{text}{colours}"
    return f"rounded=1;arcSize=12;{text}{colours}"


def _drawio_edge_style(e: Edge, d: Diagram, critical: bool = False) -> str:
    parts = ["html=1", "rounded=0", "labelBackgroundColor=#FFFFFF", f"strokeColor={THEME['edge']}"]
    k = e.kind
    if k in ("blocks", "enables"):
        parts += [f"strokeWidth={2.6 if critical else (1.5 if k == 'blocks' else 0.8)}", "endArrow=block", "endFill=1"]
    elif k in ("control_action", "feedback"):
        colour = THEME[k]
        parts += [f"strokeColor={colour}", f"fontColor={colour}", "strokeWidth=1.5", "endArrow=block", "endFill=1"]
    elif k in DASHED_EDGE_KINDS:
        parts += ["dashed=1", "endArrow=open", "endFill=0"]
    elif k == "generalization":
        parts += ["endArrow=block", "endFill=0", "endSize=10"]
    elif k == "composition":
        parts += ["startArrow=diamondThin", "startFill=1", "startSize=12", "endArrow=none"]
    elif k == "aggregation":
        parts += ["startArrow=diamondThin", "startFill=0", "startSize=12", "endArrow=none"]
    elif k in ("association", "connector"):
        parts += ["endArrow=none"]
    else:
        parts += ["endArrow=block", "endFill=1"]
    if e.style == "dashed" and "dashed=1" not in parts:
        parts.append("dashed=1")
    elif e.style == "dotted":
        parts += ["dashed=1", "dashPattern=1 2"]
    if e.points and e.src in d.nodes and e.dst in d.nodes:
        src, dst = d.nodes[e.src], d.nodes[e.dst]
        parts += _anchor("exit", src, e.points[0]) + _anchor("entry", dst, e.points[-1])
    return ";".join(parts) + ";"


def _anchor(prefix: str, n: Node, pt) -> list[str]:
    """exit/entry constraints so the edge leaves and arrives exactly where the layout routed it."""
    if n.w <= 0 or n.h <= 0:
        return []
    fx = min(1.0, max(0.0, (pt[0] - n.left) / n.w))
    fy = min(1.0, max(0.0, (pt[1] - n.top) / n.h))
    return [f"{prefix}X={fx:.3f}", f"{prefix}Y={fy:.3f}", f"{prefix}Dx=0", f"{prefix}Dy=0"]


def _drawio_label_position(e: Edge, label: str):
    """``(x, offset)`` of the label in mxGraph's relative edge geometry: ``x``
    in -1..1 along the edge, ``offset`` the pixel shift from that point, so
    the label sits where the layout placed it."""
    if not label or not e.label_pos or len(e.points) < 2:
        return None
    w, h = text_box(label, SMALL_PX)
    cx, cy = e.label_pos
    if e.label_ha == "left":
        cx += w / 2 + 4
    if e.label_va == "top":
        cy += h / 2 + 4
    segs = list(zip(e.points, e.points[1:], strict=False))
    lengths = [abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in segs]
    total = sum(lengths) or 1.0
    best, best_d, run = (0.5, (cx, cy)), None, 0.0
    for (a, b), length in zip(segs, lengths, strict=False):
        if length <= 0:
            continue
        t = ((cx - a[0]) * (b[0] - a[0]) + (cy - a[1]) * (b[1] - a[1])) / (length * length)
        t = min(1.0, max(0.0, t))
        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        dist = abs(cx - px) + abs(cy - py)
        if best_d is None or dist < best_d:
            best, best_d = ((run + t * length) / total, (px, py)), dist
        run += length
    frac, (px, py) = best
    return 2 * frac - 1, (cx - px, cy - py)
