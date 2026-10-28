"""Export a Diagram as Graphviz DOT and Mermaid source text.

Neither tool needs to be installed to produce the text; the output is meant
for pasting into an online renderer, a Markdown file, or a CI job that has
`dot` / `mmdc` available.
"""
from __future__ import annotations

from .metrics import DASHED_EDGE_KINDS, edge_label
from .model import Diagram, Edge, Node
from .render import THEME


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _html(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("\n", "<BR/>"))


# ====================================================================== DOT
def to_dot(d: Diagram) -> str:
    out = [f"digraph {_q(d.title)} {{"]
    out.append(f'  graph [rankdir={d.direction}, splines=ortho, nodesep=0.4, ranksep=0.55, '
               f'fontname="Helvetica", label={_q(d.frame or d.title)}, labelloc=t, labeljust=l];')
    out.append('  node  [fontname="Helvetica", fontsize=11, style="filled", penwidth=1.3];')
    out.append('  edge  [fontname="Helvetica", fontsize=9, color="#3E4C59", arrowsize=0.8];')
    real = [n for n in d.nodes.values() if n.kind != "dummy"]
    if d.lanes:
        for i, ln in enumerate(d.lanes):
            fill = THEME["lane_a"] if i % 2 == 0 else THEME["lane_b"]
            out.append(f"  subgraph cluster_{_ident(ln.id)} {{")
            out.append(f"    label={_q(ln.title)}; style=filled; fillcolor={_q(fill)}; color=\"#B8C2CC\";")
            for n in real:
                if n.lane == ln.id:
                    out.append("    " + _dot_node(n))
            out.append("  }")
        for n in real:
            if n.lane is None or d.lane_index(n.lane) < 0:
                out.append("  " + _dot_node(n))
    else:
        for n in real:
            out.append("  " + _dot_node(n))
    for e in d.edges:
        out.append("  " + _dot_edge(e))
    out.append("}")
    return "\n".join(out) + "\n"


def _ident(s: str) -> str:
    out = "".join(c if c.isalnum() or c == "_" else "_" for c in s)
    return out if out and not out[0].isdigit() else "n_" + out


def _dot_node(n: Node) -> str:
    k = n.kind
    fill, stroke = THEME.get(k, ("#F4F4F4", "#5F6B7A"))
    fill = n.fill or fill
    stroke = n.stroke or stroke
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


def _dot_edge(e: Edge) -> str:
    attrs = []
    label = edge_label(e)
    if label:
        attrs.append(f"label={_q(label)}")
    if e.kind in DASHED_EDGE_KINDS:
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
    if e.back:
        attrs.append("constraint=false")
    a = f" [{', '.join(attrs)}]" if attrs else ""
    return f"{_q(e.src)} -> {_q(e.dst)}{a};"


# ================================================================== Mermaid
def to_mermaid(d: Diagram) -> str:
    if d.kind == "state":
        return _mermaid_state(d)
    if d.kind in ("bdd", "req"):
        return _mermaid_class(d)
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
    for e in d.edges:
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
    # styling
    for n in real:
        k = n.kind
        if k in ("start", "end"):
            out.append(f"  style {_mid(n.id)} fill:#1F2933,stroke:#1F2933,color:#fff")
        elif k in ("fork", "join"):
            out.append(f"  style {_mid(n.id)} fill:#1F2933,stroke:#1F2933,color:#1F2933")
        elif k in THEME and isinstance(THEME[k], tuple):
            fill, stroke = THEME[k]
            out.append(f"  style {_mid(n.id)} fill:{n.fill or fill},stroke:{n.stroke or stroke}")
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
