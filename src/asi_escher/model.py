"""Diagram data model: nodes, edges, swimlanes.

A :class:`Diagram` is a plain directed graph with presentation hints.  Nothing
in this module depends on matplotlib, so a diagram can be built, validated and
serialised (``to_dict`` / ``from_dict``) in any process; layout and rendering
are separate steps (see :mod:`asi_escher.layout` and :mod:`asi_escher.render`).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

# Diagram kinds.  The kind selects the Mermaid exporter's diagram type and,
# for ``control_structure``, the layout rules of an STPA control structure
# (top-down by hierarchy, control actions left and feedback right) and, for
# ``chain``, those of a precedence network (left to right by the deepest
# predecessor, the critical path on one row); it is otherwise informational.
DIAGRAM_KINDS = {"activity", "flowchart", "state", "bdd", "ibd", "req", "control_structure", "chain"}

# Node kinds of an STPA control structure: boxes with a responsibility, an
# algorithms section and a process-model section.  The kind drives the box
# style (a double border for the controlled process, a dashed one for the
# environment, a rounded one for a human controller, plain for a controller
# and an external system, small shapes for a sensor and an actuator).
CONTROL_NODE_KINDS = {
    "controller", "human_controller", "controlled_process", "environment",
    "sensor", "actuator", "external_system",
}

# Node kinds of a chain (a precedence network of a plan): an event is a
# rounded box, a milestone a box with pointed ends, a gate a box with a double
# border and an external event (one somebody else delivers) a dashed box.
# The box colour is the event's status, not its kind.
CHAIN_NODE_KINDS = {"event", "milestone", "gate", "external"}

# Statuses of a chain event.  ``blocked`` is derived when not given: a
# pending event whose direct predecessor on a ``blocks`` edge is late, or
# marked blocked, is blocked (see :meth:`Diagram.status`).
CHAIN_STATUSES = {"done", "active", "blocked", "pending", "late"}

# Node kinds understood by the layout engine, renderer and exporters.
NODE_KINDS = {
    "start", "end", "flowfinal", "action", "decision", "merge", "fork", "join",
    "note", "state", "block", "part", "requirement", "object", "io",
    "process", "document", "database", "dummy",
} | CONTROL_NODE_KINDS | CHAIN_NODE_KINDS

# Edge kinds of a control structure: a control action points down the
# hierarchy (red), feedback points up (blue); both carry numbered signals.
CONTROL_EDGE_KINDS = {"control_action", "feedback"}

# Edge kinds of a chain: a predecessor ``blocks`` its successor (solid, an
# arrowhead; the Jira "blocks" link), ``enables`` it (solid, thin) or
# ``informs`` it (dashed; no precedence: it never moves an event).
CHAIN_EDGE_KINDS = {"blocks", "enables", "informs"}

# The chain edge kinds that order events: a successor comes after its
# predecessor.  ``informs`` is left out on purpose.
PRECEDENCE_KINDS = ("blocks", "enables")

# Edge kinds. "flow" is the default control/object flow arrow.
EDGE_KINDS = {
    "flow", "dependency", "composition", "aggregation", "generalization",
    "association", "connector", "satisfy", "derive", "verify", "refine",
    "allocate", "itemflow",
} | CONTROL_EDGE_KINDS | CHAIN_EDGE_KINDS

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
    # control-structure sections: a responsibility text, the algorithms as
    # (code, name) pairs and the process model as (title, [entries]); a note
    # may name the controller it floats beside (``attached_to``)
    responsibility: str = ""
    algorithms: list = field(default_factory=list)
    process_model: tuple | None = None
    attached_to: str | None = None
    # chain event fields: the status as given (``Diagram.status`` derives
    # ``blocked``), the owner and due date drawn as small lines under the
    # title, a free note and an optional effort that weighs the critical path
    status: str = ""
    owner: str = ""
    due: str = ""
    note: str = ""
    effort: int | None = None
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
    # the numbered signals a control action or feedback carries, one per
    # label line ("CA-01 Mission Data"); ``label`` is their join
    signals: list = field(default_factory=list)
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
             touching a node or another label), ``"edge_through_node"`` (an
             edge segment passes through a node it does not connect) or
             ``"cycle"`` (a chain's precedence edges run in a circle; the
             layout breaks it by drawing the named edge backwards).
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
        ``"TB"`` (top to bottom) or ``"LR"`` (left to right); when not given,
        a chain runs left to right and every other kind top to bottom.
    frame:
        Optional SysML frame header, e.g. ``"bdd [Package] Loader"``.  When
        set, the renderer draws a diagram frame with a name tab.
    """

    def __init__(self, title: str, kind: str = "activity", direction: str | None = None,
                 frame: str | None = None):
        if kind not in DIAGRAM_KINDS:
            raise ValueError(f"unknown diagram kind {kind!r}; expected one of {sorted(DIAGRAM_KINDS)}")
        if direction is None:
            direction = "LR" if kind == "chain" else "TB"
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
    def state(self, id, label=None, **kw): return self.node(id, label, "state", **kw)

    def note(self, id, label, lane=None, attached_to=None):
        """A note; ``attached_to`` names the control-structure box it floats beside."""
        if attached_to is not None and attached_to not in self.nodes:
            raise KeyError(f"note {id!r} is attached to unknown node {attached_to!r}")
        return self.node(id, label, "note", lane=lane, attached_to=attached_to)

    # control structures (STPA)
    def controller(self, id, label=None, kind="controller", responsibility="",
                   algorithms=None, process_model=None, **kw):
        """A control-structure box: a controller, human controller, controlled
        process, environment, sensor, actuator or external system.

        ``responsibility`` is free text (newlines kept), ``algorithms`` a list
        of ``(code, name)`` pairs drawn in the orange section and
        ``process_model`` a ``(title, [entries])`` pair drawn in the blue one.
        """
        if kind not in CONTROL_NODE_KINDS:
            raise ValueError(f"unknown controller kind {kind!r}; expected one of {sorted(CONTROL_NODE_KINDS)}")
        algs = [(str(c), str(n)) for c, n in (algorithms or [])]
        pm = None
        if process_model is not None:
            title, entries = process_model
            pm = (str(title), [str(x) for x in entries])
        return self.node(id, label, kind, responsibility=responsibility or "", algorithms=algs,
                         process_model=pm, **kw)

    def control_action(self, src, dst, signals=(), **kw):
        """A red arrow down the hierarchy carrying ``signals`` (one label line each)."""
        return self._signal_edge(src, dst, "control_action", signals, **kw)

    def feedback(self, src, dst, signals=(), **kw):
        """A blue arrow up the hierarchy carrying ``signals`` (one label line each)."""
        return self._signal_edge(src, dst, "feedback", signals, **kw)

    def _signal_edge(self, src, dst, kind, signals, **kw):
        sig = [signals] if isinstance(signals, str) else [str(x) for x in signals]
        return self.edge(src, dst, "\n".join(sig), kind, signals=sig, **kw)

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

    # chains (precedence networks)
    def event(self, id, title=None, *, status="pending", kind="event", owner="", due="",
              note="", effort=None, **kw):
        """An event of a chain: a box with a title and, when given, the owner
        and the due date as small lines under it.

        ``status`` is one of :data:`CHAIN_STATUSES` (the box colour; a
        pending event is drawn blocked when a predecessor that blocks it is
        late or blocked, see :meth:`status`), ``kind`` one of
        :data:`CHAIN_NODE_KINDS` (the box shape), ``effort`` an optional
        non-negative integer that weighs the critical path.
        """
        if status not in CHAIN_STATUSES:
            raise ValueError(f"unknown event status {status!r}; expected one of {sorted(CHAIN_STATUSES)}")
        if kind not in CHAIN_NODE_KINDS:
            raise ValueError(f"unknown event kind {kind!r}; expected one of {sorted(CHAIN_NODE_KINDS)}")
        if effort is not None and (isinstance(effort, bool) or not isinstance(effort, int) or effort < 0):
            raise ValueError(f"effort of event {id!r} must be a non-negative integer, got {effort!r}")
        return self.node(id, title, kind, status=status, owner=str(owner or ""), due=str(due or ""),
                         note=str(note or ""), effort=effort, **kw)

    def blocks(self, predecessor, successor, *, kind="blocks", label="", **kw):
        """A precedence edge from ``predecessor`` to ``successor``: ``blocks``
        (solid, an arrowhead), ``enables`` (solid, thin) or ``informs``
        (dashed; it orders nothing)."""
        if kind not in CHAIN_EDGE_KINDS:
            raise ValueError(f"unknown chain edge kind {kind!r}; expected one of {sorted(CHAIN_EDGE_KINDS)}")
        return self.edge(predecessor, successor, label, kind, **kw)

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
        for n in self.real_nodes():
            if n.attached_to is not None and n.attached_to not in self.nodes:
                raise ValueError(f"note {n.id!r} is attached to unknown node {n.attached_to!r}")
        if self.lanes:
            known = {ln.id for ln in self.lanes}
            for n in self.real_nodes():
                if n.lane is None:
                    raise ValueError(f"node {n.id!r} has no lane but the diagram defines swimlanes")
                if n.lane not in known:
                    raise ValueError(f"node {n.id!r} references unknown lane {n.lane!r}")

    # --- chain queries -------------------------------------------------------
    def _precedence_dfs(self) -> tuple[list[int], list[list[str]]]:
        """Depth-first search over the precedence edges (``blocks`` and
        ``enables``), from the events nobody precedes first, in author order.

        Returns the indices (into ``self.edges``) of the back edges, one per
        cycle found, and each cycle as the ids it runs through in order (the
        back edge closes it on the first id).  A self loop is a cycle of one.
        The layout turns exactly these edges round, so the cycle it reports
        is the one this search found.
        """
        adj: dict[str, list] = defaultdict(list)
        indeg = {nid: 0 for nid in self.nodes}
        for i, e in enumerate(self.edges):
            if e.kind in PRECEDENCE_KINDS:
                adj[e.src].append((e.dst, i))
                if e.src != e.dst:
                    indeg[e.dst] += 1
        color = {nid: 0 for nid in self.nodes}
        backs: list[int] = []
        cycles: list[list[str]] = []
        for root in [n for n in self.nodes if indeg[n] == 0] + list(self.nodes):
            if color[root]:
                continue
            color[root] = 1
            stack = [(root, iter(adj[root]))]
            while stack:
                u, it = stack[-1]
                for v, i in it:
                    if v == u:
                        backs.append(i)
                        cycles.append([u])
                        continue
                    if color[v] == 0:
                        color[v] = 1
                        stack.append((v, iter(adj[v])))
                        break
                    if color[v] == 1:
                        backs.append(i)
                        ids = [nid for nid, _ in stack]
                        cycles.append(ids[ids.index(v):])
                else:
                    color[u] = 2
                    stack.pop()
        return backs, cycles

    def back_edges(self) -> list[Edge]:
        """The precedence edges that close a cycle (empty for an acyclic chain);
        the layout draws them backwards and leaves them out of the ordering."""
        backs, _ = self._precedence_dfs()
        return [self.edges[i] for i in backs]

    def cycles(self) -> list[list[str]]:
        """Every cycle of the precedence edges as the ids it runs through, in
        order; empty for a well-formed chain."""
        return self._precedence_dfs()[1]

    def _forward(self) -> list[Edge]:
        """The precedence edges in dependency direction: no back edge, no self loop."""
        backs = set(self._precedence_dfs()[0])
        return [e for i, e in enumerate(self.edges)
                if e.kind in PRECEDENCE_KINDS and i not in backs and e.src != e.dst]

    def _require(self, id: str) -> None:
        if id not in self.nodes:
            raise KeyError(f"unknown event {id!r}")

    def columns(self) -> dict[str, int]:
        """The column of every event: 0 for one with no predecessor, else one
        past the deepest predecessor on a ``blocks`` or ``enables`` edge
        (``informs`` edges and the back edge of a cycle do not count).  This
        is the column the layout draws it in."""
        preds: dict[str, list] = defaultdict(list)
        succs: dict[str, list] = defaultdict(list)
        for e in self._forward():
            preds[e.dst].append(e.src)
            succs[e.src].append(e.dst)
        indeg = {nid: len(preds[nid]) for nid in self.nodes}
        col = {nid: 0 for nid in self.nodes}
        queue = deque(nid for nid in self.nodes if indeg[nid] == 0)
        while queue:
            u = queue.popleft()
            for v in succs[u]:
                col[v] = max(col[v], col[u] + 1)
                indeg[v] -= 1
                if indeg[v] == 0:
                    queue.append(v)
        return col

    def _dependency_order(self, ids) -> list[str]:
        """``ids`` sorted the way a plan reads them: by column, then as the author listed them."""
        col = self.columns()
        index = {nid: i for i, nid in enumerate(self.nodes)}
        return sorted(ids, key=lambda nid: (col[nid], index[nid]))

    def predecessors(self, id: str) -> list[str]:
        """The events a ``blocks`` or ``enables`` edge leads from into ``id``, in author order."""
        self._require(id)
        return list(dict.fromkeys(e.src for e in self.edges if e.dst == id and e.kind in PRECEDENCE_KINDS))

    def successors(self, id: str) -> list[str]:
        """The events a ``blocks`` or ``enables`` edge leads to from ``id``, in author order."""
        self._require(id)
        return list(dict.fromkeys(e.dst for e in self.edges if e.src == id and e.kind in PRECEDENCE_KINDS))

    def upstream(self, id: str) -> list[str]:
        """Every event that precedes ``id``, directly or through others, in
        dependency order (the earliest first); ``id`` itself is left out."""
        return self._reach(id, backwards=True)

    def downstream(self, id: str) -> list[str]:
        """Every event that follows ``id``, directly or through others, in
        dependency order (the nearest first); ``id`` itself is left out."""
        return self._reach(id, backwards=False)

    def _reach(self, id: str, backwards: bool) -> list[str]:
        self._require(id)
        nxt: dict[str, list] = defaultdict(list)
        for e in self._forward():
            if backwards:
                nxt[e.dst].append(e.src)
            else:
                nxt[e.src].append(e.dst)
        seen: set[str] = set()
        stack = [id]
        while stack:
            u = stack.pop()
            for v in nxt[u]:
                if v not in seen and v != id:
                    seen.add(v)
                    stack.append(v)
        return self._dependency_order(seen)

    def status(self, id: str) -> str:
        """The effective status of an event: the one given, except that a
        ``pending`` event with a direct ``blocks`` predecessor that is late or
        blocked (as given) is ``blocked``."""
        self._require(id)
        n = self.nodes[id]
        given = n.status or "pending"
        if given != "pending":
            return given
        for e in self.edges:
            if e.kind == "blocks" and e.dst == id and e.src != id:
                if (self.nodes[e.src].status or "pending") in ("late", "blocked"):
                    return "blocked"
        return given

    def statuses(self) -> dict[str, str]:
        """The effective status of every chain event (see :meth:`status`)."""
        return {n.id: self.status(n.id) for n in self.real_nodes() if n.kind in CHAIN_NODE_KINDS}

    def blockers(self, id: str) -> list[str]:
        """The events that stand between ``id`` and being workable: every
        upstream event on a chain of ``blocks`` edges that is not done, up to
        the first done one on each chain, nearest first (the direct
        predecessors, then theirs, ...), author order within a distance."""
        self._require(id)
        preds: dict[str, list] = defaultdict(list)
        for e in self._forward():
            if e.kind == "blocks":
                preds[e.dst].append(e.src)
        index = {nid: i for i, nid in enumerate(self.nodes)}
        out: list[str] = []
        seen = {id}
        frontier = [id]
        while frontier:
            level: list[str] = []
            for u in frontier:
                for v in preds[u]:
                    if v in seen or (self.nodes[v].status or "pending") == "done":
                        continue
                    seen.add(v)
                    level.append(v)
            level.sort(key=lambda nid: index[nid])
            out.extend(level)
            frontier = level
        return out

    def critical_path(self) -> list[str]:
        """The longest chain of ``blocks`` / ``enables`` edges, first event
        first: by count, or by the sum of ``effort`` where events carry one
        (an event without effort counts 1).  Ties go to the author's order."""
        if not self.nodes:
            return []
        preds: dict[str, list] = defaultdict(list)
        for e in self._forward():
            preds[e.dst].append(e.src)
        order = self._dependency_order(list(self.nodes))
        best: dict[str, int] = {}
        parent: dict[str, str | None] = {}
        for nid in order:
            n = self.nodes[nid]
            weight = 1 if n.effort is None else n.effort
            best[nid], parent[nid] = weight, None
            for p in preds[nid]:
                if best[p] + weight > best[nid]:
                    best[nid], parent[nid] = best[p] + weight, p
        end = max(order, key=lambda nid: best[nid])        # the first of equals
        path = []
        cur: str | None = end
        while cur is not None:
            path.append(cur)
            cur = parent[cur]
        path.reverse()
        return path

    def critical_edges(self) -> set[tuple[str, str]]:
        """The ``(src, dst)`` pairs along :meth:`critical_path`."""
        path = self.critical_path()
        return set(zip(path, path[1:], strict=False))

    # --- serialisation -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Plain-data form of the diagram (no layout results).  A chain is
        written in its own form, ``events`` and ``edges`` as plain lists (see
        :meth:`_chain_dict`); every other kind as ``nodes`` and ``edges``."""
        if self.kind == "chain":
            return self._chain_dict()
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
            if n.responsibility:
                item["responsibility"] = n.responsibility
            if n.algorithms:
                item["algorithms"] = [[code, name] for code, name in n.algorithms]
            if n.process_model is not None:
                item["process_model"] = [n.process_model[0], list(n.process_model[1])]
            if n.attached_to is not None:
                item["attached_to"] = n.attached_to
            item.update(_event_fields(n))
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
            if e.signals:
                item["signals"] = list(e.signals)
                if e.label == "\n".join(e.signals):
                    item.pop("label", None)
            edges.append(item)
        out: dict[str, Any] = {"title": self.title, "kind": self.kind, "direction": self.direction}
        if self.frame:
            out["frame"] = self.frame
        if self.lanes:
            out["lanes"] = [{"id": ln.id, "title": ln.title} for ln in self.lanes]
        out["nodes"] = nodes
        out["edges"] = edges
        return out

    def _chain_dict(self) -> dict[str, Any]:
        """The chain spec: ``events`` (``id``, ``title`` and, when set, ``kind``,
        ``status``, ``owner``, ``due``, ``note``, ``effort``) and ``edges``
        (``src``, ``dst`` and, when set, ``kind`` and ``label``)."""
        events = []
        for n in self.real_nodes():
            item: dict[str, Any] = {"id": n.id, "title": n.label}
            if n.kind != "event":
                item["kind"] = n.kind
            item.update(_event_fields(n))
            events.append(item)
        edges = []
        for e in self.edges:
            item = {"src": e.src, "dst": e.dst}
            if e.kind != "blocks":
                item["kind"] = e.kind
            if e.label:
                item["label"] = e.label
            edges.append(item)
        return {"title": self.title, "kind": "chain", "direction": self.direction, "events": events,
                "edges": edges}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Diagram:
        """Build a diagram from the structure produced by :meth:`to_dict`: the
        general form (``nodes`` and ``edges``) or a chain spec (``events`` and
        ``edges``; ``kind`` defaults to ``chain`` then)."""
        if "title" not in data:
            raise ValueError("diagram spec needs a 'title'")
        if "events" in data:
            return cls._chain_from_dict(data)
        d = cls(data["title"], data.get("kind", "activity"), data.get("direction"),
                data.get("frame"))
        for ln in data.get("lanes", []):
            d.lane(ln["id"], ln.get("title"))
        for n in data.get("nodes", []):
            if "id" not in n:
                raise ValueError("every node needs an 'id'")
            comps = [(c[0], list(c[1])) for c in n.get("compartments", [])]
            pm = n.get("process_model")
            d.node(n["id"], n.get("label"), n.get("kind", "action"), lane=n.get("lane"),
                   stereotype=n.get("stereotype"), compartments=comps,
                   fill=n.get("fill"), stroke=n.get("stroke"),
                   responsibility=n.get("responsibility", ""),
                   algorithms=[(str(a[0]), str(a[1])) for a in n.get("algorithms", [])],
                   process_model=(str(pm[0]), [str(x) for x in pm[1]]) if pm else None,
                   attached_to=n.get("attached_to"),
                   status=n.get("status", ""), owner=n.get("owner", ""), due=n.get("due", ""),
                   note=n.get("note", ""), effort=n.get("effort"))
        for e in data.get("edges", []):
            if "src" not in e or "dst" not in e:
                raise ValueError("every edge needs 'src' and 'dst'")
            signals = [str(x) for x in e.get("signals", [])]
            label = e.get("label", "\n".join(signals))
            d.edge(e["src"], e["dst"], label, e.get("kind", "flow"),
                   style=e.get("style", "solid"), src_port=e.get("src_port"),
                   dst_port=e.get("dst_port"), signals=signals)
        return d

    @classmethod
    def _chain_from_dict(cls, data: dict[str, Any]) -> Diagram:
        d = cls(data["title"], data.get("kind", "chain"), data.get("direction"), data.get("frame"))
        for ev in data["events"]:
            if "id" not in ev:
                raise ValueError("every event needs an 'id'")
            d.event(ev["id"], ev.get("title", ev.get("label")), status=ev.get("status", "pending"),
                    kind=ev.get("kind", "event"), owner=ev.get("owner", ""), due=ev.get("due", ""),
                    note=ev.get("note", ""), effort=ev.get("effort"))
        for e in data.get("edges", []):
            if "src" not in e or "dst" not in e:
                raise ValueError("every edge needs 'src' and 'dst'")
            d.blocks(e["src"], e["dst"], kind=e.get("kind", "blocks"), label=e.get("label", ""))
        return d


def _event_fields(n: Node) -> dict[str, Any]:
    """The chain event fields of a node that are set, for the dict forms."""
    out: dict[str, Any] = {}
    if n.status and n.status != "pending":
        out["status"] = n.status
    for key in ("owner", "due", "note"):
        if getattr(n, key):
            out[key] = getattr(n, key)
    if n.effort is not None:
        out["effort"] = n.effort
    return out
