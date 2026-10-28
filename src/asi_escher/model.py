"""Diagram data model: nodes, edges, swimlanes.

A :class:`Diagram` is a plain directed graph with presentation hints.  Nothing
in this module depends on matplotlib, so a diagram can be built, validated and
serialised (``to_dict`` / ``from_dict``) in any process; layout and rendering
are separate steps (see :mod:`asi_escher.layout` and :mod:`asi_escher.render`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Diagram kinds.  The kind only affects the Mermaid exporter's choice of
# diagram type and is otherwise informational.
DIAGRAM_KINDS = {"activity", "flowchart", "state", "bdd", "ibd", "req"}

# Node kinds understood by the layout engine, renderer and exporters.
NODE_KINDS = {
    "start", "end", "flowfinal", "action", "decision", "merge", "fork", "join",
    "note", "state", "block", "part", "requirement", "object", "io",
    "process", "document", "database", "dummy",
}

# Edge kinds. "flow" is the default control/object flow arrow.
EDGE_KINDS = {
    "flow", "dependency", "composition", "aggregation", "generalization",
    "association", "connector", "satisfy", "derive", "verify", "refine",
    "allocate", "itemflow",
}

EDGE_STYLES = {"solid", "dashed", "dotted"}

DIRECTIONS = {"TB", "LR"}


@dataclass
class Node:
    id: str
    label: str = ""
    kind: str = "action"
    lane: str | None = None
    stereotype: str | None = None
    # list of (compartment title, [lines]) for block-like nodes
    compartments: list = field(default_factory=list)
    fill: str | None = None
    stroke: str | None = None
    # layout results (centre x/y, width/height, layer index, order in layer,
    # and the label as wrapped lines).  The author's ``label`` is never changed.
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    layer: int = 0
    order: int = 0
    lines: list = field(default_factory=list)

    @property
    def left(self) -> float:
        return self.x - self.w / 2

    @property
    def right(self) -> float:
        return self.x + self.w / 2

    @property
    def top(self) -> float:
        return self.y - self.h / 2

    @property
    def bottom(self) -> float:
        return self.y + self.h / 2

    @property
    def text(self) -> str:
        """Label as the renderer draws it (wrapped after layout)."""
        return "\n".join(self.lines) if self.lines else self.label


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    kind: str = "flow"
    style: str = "solid"          # solid | dashed | dotted
    src_port: str | None = None
    dst_port: str | None = None
    # layout results
    back: bool = False
    path: list = field(default_factory=list)     # node ids incl. dummies
    points: list = field(default_factory=list)   # polyline [(x, y), ...]
    label_pos: tuple | None = None
    label_ha: str = "center"                     # text anchors used by renderer
    label_va: str = "center"


@dataclass
class Lane:
    id: str
    title: str
    x0: float = 0.0
    x1: float = 0.0


@dataclass
class LayoutIssue:
    """A place where the layout had to settle for a degraded result.

    kind:    ``"label_overlap"`` (an edge label could not be placed without
             touching a node or another label) or ``"edge_through_node"`` (an
             edge segment passes through a node it does not connect).
    message: human-readable description.
    edge:    ``(src, dst)`` of the edge concerned, when applicable.
    node:    id of the node concerned, when applicable.
    """
    kind: str
    message: str
    edge: tuple | None = None
    node: str | None = None


class Diagram:
    """A directed graph with optional swimlanes plus presentation hints.

    Parameters
    ----------
    title:
        Human-readable title.  Used as the default output file stem.
    kind:
        One of :data:`DIAGRAM_KINDS`.
    direction:
        ``"TB"`` (top to bottom) or ``"LR"`` (left to right).
    frame:
        Optional SysML frame header, e.g. ``"bdd [Package] Loader"``.  When
        set, the renderer draws a diagram frame with a name tab.
    """

    def __init__(self, title: str, kind: str = "activity", direction: str = "TB",
                 frame: str | None = None):
        if kind not in DIAGRAM_KINDS:
            raise ValueError(f"unknown diagram kind {kind!r}; expected one of {sorted(DIAGRAM_KINDS)}")
        if direction not in DIRECTIONS:
            raise ValueError(f"direction must be 'TB' or 'LR', got {direction!r}")
        self.title = title
        self.kind = kind
        self.direction = direction
        self.frame = frame
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.lanes: list[Lane] = []
        # layout results
        self.width = 0.0
        self.height = 0.0
        self.lane_top = 0.0
        self.lane_bottom = 0.0
        self.lane_header = 0.0
        self.issues: list[LayoutIssue] = []

    # --- construction helpers -------------------------------------------
    def node(self, id: str, label: str | None = None, kind: str = "action", **kw) -> Node:
        """Add a node.  ``label`` defaults to ``id``.  Raises on duplicate ids."""
        if kind not in NODE_KINDS:
            raise ValueError(f"unknown node kind {kind!r}; expected one of {sorted(NODE_KINDS)}")
        if id in self.nodes:
            raise ValueError(f"duplicate node id {id!r}")
        n = Node(id=id, label=id if label is None else label, kind=kind, **kw)
        self.nodes[id] = n
        return n

    def edge(self, src: str, dst: str, label: str = "", kind: str = "flow", **kw) -> Edge:
        """Add an edge between two existing nodes."""
        if kind not in EDGE_KINDS:
            raise ValueError(f"unknown edge kind {kind!r}; expected one of {sorted(EDGE_KINDS)}")
        for nid in (src, dst):
            if nid not in self.nodes:
                raise KeyError(f"edge references unknown node {nid!r}")
        e = Edge(src=src, dst=dst, label=label, kind=kind, **kw)
        if e.style not in EDGE_STYLES:
            raise ValueError(f"unknown edge style {e.style!r}; expected one of {sorted(EDGE_STYLES)}")
        self.edges.append(e)
        return e

    def chain(self, *ids: str, labels: list | None = None) -> None:
        """Connect ids in sequence with flow edges."""
        labels = labels or []
        for i in range(len(ids) - 1):
            lab = labels[i] if i < len(labels) else ""
            self.edge(ids[i], ids[i + 1], lab)

    def lane(self, id: str, title: str | None = None) -> Lane:
        """Add a swimlane.  Lanes are drawn in insertion order."""
        if self.lane_index(id) >= 0:
            raise ValueError(f"duplicate lane id {id!r}")
        ln = Lane(id=id, title=title or id)
        self.lanes.append(ln)
        return ln

    # shorthand constructors
    def start(self, id="start", lane=None): return self.node(id, "", "start", lane=lane)
    def end(self, id="end", lane=None): return self.node(id, "", "end", lane=lane)
    def action(self, id, label=None, lane=None, **kw): return self.node(id, label, "action", lane=lane, **kw)
    def decision(self, id, label=None, lane=None, **kw): return self.node(id, label, "decision", lane=lane, **kw)
    def merge(self, id, lane=None): return self.node(id, "", "merge", lane=lane)
    def fork(self, id, lane=None): return self.node(id, "", "fork", lane=lane)
    def join(self, id, lane=None): return self.node(id, "", "join", lane=lane)
    def note(self, id, label, lane=None): return self.node(id, label, "note", lane=lane)
    def state(self, id, label=None, **kw): return self.node(id, label, "state", **kw)

    def block(self, id, label=None, stereotype="block", values=None, parts=None,
              operations=None, **kw):
        comps = []
        if parts:
            comps.append(("parts", list(parts)))
        if values:
            comps.append(("values", list(values)))
        if operations:
            comps.append(("operations", list(operations)))
        return self.node(id, label, "block", stereotype=stereotype, compartments=comps, **kw)

    def requirement(self, id, label, req_id, text, **kw):
        comps = [("", [f"id = \"{req_id}\"", f"text = \"{text}\""])]
        return self.node(id, label, "requirement", stereotype="requirement",
                         compartments=comps, **kw)

    # --- queries -----------------------------------------------------------
    def real_nodes(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind != "dummy"]

    def lane_index(self, lane_id) -> int:
        for i, ln in enumerate(self.lanes):
            if ln.id == lane_id:
                return i
        return -1

    def validate(self) -> None:
        """Raise ``ValueError`` if the diagram cannot be laid out consistently.

        Checked: every edge endpoint exists; when lanes are defined every
        non-dummy node is assigned to a known lane.
        """
        for e in self.edges:
            for nid in (e.src, e.dst):
                if nid not in self.nodes:
                    raise ValueError(f"edge {e.src!r}->{e.dst!r} references unknown node {nid!r}")
        if self.lanes:
            known = {ln.id for ln in self.lanes}
            for n in self.real_nodes():
                if n.lane is None:
                    raise ValueError(f"node {n.id!r} has no lane but the diagram defines swimlanes")
                if n.lane not in known:
                    raise ValueError(f"node {n.id!r} references unknown lane {n.lane!r}")

    # --- serialisation -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Plain-data form of the diagram (no layout results)."""
        nodes = []
        for n in self.real_nodes():
            item: dict[str, Any] = {"id": n.id, "label": n.label, "kind": n.kind}
            if n.lane is not None:
                item["lane"] = n.lane
            if n.stereotype is not None:
                item["stereotype"] = n.stereotype
            if n.compartments:
                item["compartments"] = [[title, list(lines)] for title, lines in n.compartments]
            if n.fill:
                item["fill"] = n.fill
            if n.stroke:
                item["stroke"] = n.stroke
            nodes.append(item)
        edges = []
        for e in self.edges:
            item = {"src": e.src, "dst": e.dst}
            if e.label:
                item["label"] = e.label
            if e.kind != "flow":
                item["kind"] = e.kind
            if e.style != "solid":
                item["style"] = e.style
            if e.src_port:
                item["src_port"] = e.src_port
            if e.dst_port:
                item["dst_port"] = e.dst_port
            edges.append(item)
        out: dict[str, Any] = {"title": self.title, "kind": self.kind, "direction": self.direction}
        if self.frame:
            out["frame"] = self.frame
        if self.lanes:
            out["lanes"] = [{"id": ln.id, "title": ln.title} for ln in self.lanes]
        out["nodes"] = nodes
        out["edges"] = edges
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Diagram:
        """Build a diagram from the structure produced by :meth:`to_dict`."""
        if "title" not in data:
            raise ValueError("diagram spec needs a 'title'")
        d = cls(data["title"], data.get("kind", "activity"), data.get("direction", "TB"),
                data.get("frame"))
        for ln in data.get("lanes", []):
            d.lane(ln["id"], ln.get("title"))
        for n in data.get("nodes", []):
            if "id" not in n:
                raise ValueError("every node needs an 'id'")
            comps = [(c[0], list(c[1])) for c in n.get("compartments", [])]
            d.node(n["id"], n.get("label"), n.get("kind", "action"), lane=n.get("lane"),
                   stereotype=n.get("stereotype"), compartments=comps,
                   fill=n.get("fill"), stroke=n.get("stroke"))
        for e in data.get("edges", []):
            if "src" not in e or "dst" not in e:
                raise ValueError("every edge needs 'src' and 'dst'")
            d.edge(e["src"], e["dst"], e.get("label", ""), e.get("kind", "flow"),
                   style=e.get("style", "solid"), src_port=e.get("src_port"),
                   dst_port=e.get("dst_port"))
        return d
