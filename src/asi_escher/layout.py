"""Layered (Sugiyama-style) layout for asi_escher diagrams.

Steps: size nodes -> remove cycles (DFS back edges) -> longest-path layering
-> dummy nodes for long edges -> barycenter ordering (lane-aware) ->
coordinate assignment -> orthogonal edge routing -> edge-label placement.
Left-to-right layouts are computed as top-to-bottom with swapped node sizes
and then transposed.

The algorithm is deterministic: the same diagram always produces the same
coordinates.
"""
from __future__ import annotations

import warnings
from collections import defaultdict, deque

from .metrics import SMALL_PX, edge_label, size_node, text_box, text_width
from .model import CONTROL_NODE_KINDS, Diagram, Edge, LayoutIssue, Node


class LayoutWarning(UserWarning):
    """Emitted once per ``layout()`` call that produced any :class:`LayoutIssue`."""


class LayoutOptions:
    """Spacing knobs, all in pixels.

    ranksep:      vertical gap between layers
    nodesep:      horizontal gap between nodes in a layer
    margin:       canvas margin
    lane_pad:     padding inside a swimlane
    lane_header:  height of the swimlane title strip
    iterations:   barycenter ordering sweeps
    back_channel: distance of the back-edge channel from the rightmost node
    """

    def __init__(self, ranksep=56.0, nodesep=34.0, margin=36.0, lane_pad=26.0,
                 lane_header=30.0, iterations=16, back_channel=36.0):
        self.ranksep = ranksep
        self.nodesep = nodesep
        self.margin = margin
        self.lane_pad = lane_pad
        self.lane_header = lane_header
        self.iterations = iterations
        self.back_channel = back_channel

    @classmethod
    def for_kind(cls, kind: str) -> LayoutOptions:
        """The defaults ``layout()`` uses for a diagram kind when given no options.

        A control structure gets wider gaps: its boxes are large, its signal
        labels hang beside the arrows and a feedback arrow runs parallel to
        the control action it answers.
        """
        if kind == "control_structure":
            return cls(ranksep=110.0, nodesep=160.0)
        return cls()


def layout(d: Diagram, opts: LayoutOptions | None = None) -> Diagram:
    """Compute node positions, edge polylines and canvas size in place.

    Anything the engine could not do cleanly (a label that had to overlap
    something, an edge that passes through an unrelated node) is recorded in
    ``d.issues`` and summarised in a single :class:`LayoutWarning`, so a host
    application can log it, flag the diagram for review, or silence it with
    ``warnings.filterwarnings("ignore", category=LayoutWarning)``.
    """
    opts = opts or LayoutOptions.for_kind(d.kind)
    d.validate()
    d.issues = []
    # drop stale dummies if re-laying out
    for nid in [k for k, n in d.nodes.items() if n.kind == "dummy"]:
        del d.nodes[nid]
    for n in d.nodes.values():
        n.w, n.h = size_node(n)
        if d.direction == "LR":
            n.w, n.h = n.h, n.w
    for e in d.edges:
        e.back = False
        e.path = []
        e.points = []
        e.label_pos = None
        e.label_ha = e.label_va = "center"
    if not d.nodes:
        _normalize(d, opts, [])
        if d.direction == "LR":
            _transpose(d)
        return d
    control = d.kind == "control_structure"
    order, attached = _detach_notes(d)
    if control:
        # feedback points up the hierarchy: lay it out reversed, beside the
        # control action it answers, and turn it round at the end
        for e in d.edges:
            e.back = e.kind == "feedback" and e.src != e.dst
    _find_back_edges(d)
    reversed_edges = _reverse_back_edges(d) if control else []
    if control:
        _assign_control_layers(d, reversed_edges)
    else:
        _assign_layers(d)
    _insert_dummies(d)
    layers, preds, succs = _order(d, opts)
    lateral_gaps = _lateral_gaps(d, opts) if control else None
    grow = [0.0] * len(layers)
    for _attempt in range(_CHANNEL_ATTEMPTS if control else 1):
        _assign_coordinates(d, layers, preds, succs, opts, lateral_gaps, grow)
        _route_edges(d, layers, opts)
        _attach_notes(d, order, attached, opts)
        d.issues = []
        boxes = _place_labels(d, swap=d.direction == "LR")
        # a control structure's channel between two tiers grows until the
        # signal stacks in it fit, then the layout is redone
        if not control or not _grow_channels(d, layers, grow):
            break
        order, attached = _detach_notes(d)
    _check_edge_crossings(d)
    _normalize(d, opts, boxes)
    for e in reversed_edges:
        e.src, e.dst = e.dst, e.src
        e.path.reverse()
        e.points.reverse()
        e.back = True
        for issue in d.issues:
            if issue.edge == (e.dst, e.src):
                issue.edge = (e.src, e.dst)
    if d.direction == "LR":
        _transpose(d)
    if d.issues:
        warnings.warn(f"{len(d.issues)} layout issue(s) in diagram {d.title!r}: "
                      + "; ".join(i.message for i in d.issues[:3])
                      + (" ..." if len(d.issues) > 3 else ""), LayoutWarning, stacklevel=2)
    return d


# ---------------------------------------------------------------- cycles ---
def _find_back_edges(d: Diagram) -> None:
    """Mark the DFS back edges; edges already marked ``back`` are left out of
    the search (a control structure's feedback is decided before it runs)."""
    adj = defaultdict(list)
    for i, e in enumerate(d.edges):
        if not e.back:
            adj[e.src].append((e.dst, i))
    indeg = {nid: 0 for nid in d.nodes}
    for e in d.edges:
        if e.src != e.dst and not e.back:
            indeg[e.dst] += 1
    color = {nid: 0 for nid in d.nodes}
    roots = [n for n in d.nodes if indeg[n] == 0] + list(d.nodes)
    for r in roots:
        if color[r]:
            continue
        color[r] = 1
        stack = [(r, iter(adj[r]))]
        while stack:
            u, it = stack[-1]
            for v, i in it:
                if v == u:
                    d.edges[i].back = True
                    continue
                if color[v] == 0:
                    color[v] = 1
                    stack.append((v, iter(adj[v])))
                    break
                if color[v] == 1:
                    d.edges[i].back = True
            else:
                color[u] = 2
                stack.pop()


def _reverse_back_edges(d: Diagram) -> list[Edge]:
    """Turn every back edge round so the layering, ordering and routing treat
    it as a forward edge running beside its partner; ``layout()`` turns the
    result back.  Self loops stay as they are."""
    out = []
    for e in d.edges:
        if e.back and e.src != e.dst:
            e.src, e.dst = e.dst, e.src
            e.back = False
            out.append(e)
    return out


def _edge_rank(e: Edge) -> int:
    """0 for a control action (kept left of a pair of boxes), 1 for feedback (right)."""
    return 1 if e.kind == "feedback" else 0


# -------------------------------------------------------------- layering ---
def _assign_layers(d: Diagram) -> None:
    preds = defaultdict(list)
    succs = defaultdict(list)
    for e in d.edges:
        if e.back or e.src == e.dst:
            continue
        preds[e.dst].append(e.src)
        succs[e.src].append(e.dst)
    indeg = {nid: len(preds[nid]) for nid in d.nodes}
    layer = {nid: 0 for nid in d.nodes}
    queue = deque(nid for nid in d.nodes if indeg[nid] == 0)
    while queue:
        u = queue.popleft()
        for v in succs[u]:
            layer[v] = max(layer[v], layer[u] + 1)
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    # push side inputs (notes, objects, io) with a single successor right above
    # that successor so they do not float to the top of the drawing
    for nid, n in d.nodes.items():
        if not preds[nid] and len(succs[nid]) == 1 and n.kind in ("note", "object", "io"):
            layer[nid] = max(0, layer[succs[nid][0]] - 1)
    for nid, n in d.nodes.items():
        n.layer = layer[nid]


def _control_actions(d: Diagram) -> list[Edge]:
    """The control actions of the hierarchy (forward, between two boxes)."""
    return [e for e in d.edges if e.kind == "control_action" and not e.back and e.src != e.dst]


def _lateral_edges(d: Diagram) -> set[int]:
    """Ids of the control actions that are requests between peers, not steps
    down the hierarchy.

    A control action from one controller to another is lateral when the
    sender's every other control action reaches past the receiver's own
    subordinates into the receiver's domain (the boxes the receiver controls
    through others): the sender is then not above the receiver but beside
    it, working the same boxes from another side.  A field operator who asks
    the control-room operator for a stop and otherwise commands the vehicle
    controller and the machine, both of them under the control-room
    operator's supervisor, is such a peer.  A sender with no other control
    action, or one that commands a direct subordinate of the receiver (an
    operator who commands the automation and, past it, the process the
    automation commands), is a plain superior.
    """
    actions = _control_actions(d)
    targets = defaultdict(list)
    for e in actions:
        targets[e.src].append(e.dst)

    def domain(v: str) -> set[str]:
        seen: set[str] = set()
        stack = [v]
        while stack:
            u = stack.pop()
            for w in targets[u]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        return seen

    lateral = set()
    for e in actions:
        others = {t for t in targets[e.src] if t != e.dst}
        if others and others <= domain(e.dst) and not others & set(targets[e.dst]):
            lateral.add(id(e))
    return lateral


def _assign_control_layers(d: Diagram, reversed_edges: list) -> None:
    """Layering of a control structure: the control hierarchy decides.

    A box sits one layer below the deepest of its control-action sources; a
    box with no control-action source is a top-level peer of the others and
    shares layer 0 with them; a box reached from two layers sits below both.
    A lateral control action (:func:`_lateral_edges`) keeps its two ends on
    one level.  Feedback never moves a box that takes part in the hierarchy;
    a box that only reports (a sensor, the environment) sits below the boxes
    it reports to, a box that only listens (an external system taking
    reports) just above the nearest box it hears from, and the environment
    at the bottom.  A reversed feedback edge the layering would send upward
    is given back the author's direction (then it points down the drawing).
    """
    lateral = _lateral_edges(d)
    has_ca = set()
    for e in _control_actions(d):
        has_ca.update((e.src, e.dst))
    forward = [e for e in d.edges if not e.back and e.src != e.dst]
    succs = defaultdict(list)
    indeg = {nid: 0 for nid in d.nodes}
    for e in forward:
        succs[e.src].append(e)
        indeg[e.dst] += 1

    def weight(e: Edge):
        """Layers between the ends of ``e`` (None: the edge does not rank)."""
        if e.kind == "control_action":
            return 0 if id(e) in lateral else 1
        if e.kind == "feedback":
            return None if e.dst in has_ca else 1
        return 1

    layer = {nid: 0 for nid in d.nodes}
    queue = deque(nid for nid in d.nodes if indeg[nid] == 0)
    while queue:
        u = queue.popleft()
        for e in succs[u]:
            w = weight(e)
            if w is not None:
                layer[e.dst] = max(layer[e.dst], layer[u] + w)
            indeg[e.dst] -= 1
            if indeg[e.dst] == 0:
                queue.append(e.dst)
    ranked = {e.dst for e in forward if weight(e) is not None}
    for nid in d.nodes:
        if nid in has_ca or nid in ranked or not succs[nid]:
            continue
        layer[nid] = max(0, min(layer[e.dst] for e in succs[nid]) - 1)
    bottom = max((layer[nid] for nid, n in d.nodes.items() if n.kind != "environment"), default=0)
    for nid, n in d.nodes.items():
        if n.kind == "environment" and not any(e.kind == "control_action" for e in succs[nid]):
            below = min((layer[e.dst] - 1 for e in succs[nid]), default=bottom)
            layer[nid] = max(layer[nid], min(bottom, below))
    for nid, n in d.nodes.items():
        n.layer = layer[nid]
    for e in list(reversed_edges):
        if d.nodes[e.src].layer > d.nodes[e.dst].layer:
            e.src, e.dst = e.dst, e.src
            reversed_edges.remove(e)


def _is_lateral(d: Diagram, e: Edge) -> bool:
    """True for a forward edge between two boxes of one layer (drawn sideways)."""
    return not e.back and e.src != e.dst and d.nodes[e.src].layer == d.nodes[e.dst].layer


def _lateral_gaps(d: Diagram, opts: LayoutOptions) -> dict:
    """Extra separation between the two ends of a lateral edge so its label
    fits on the horizontal arrow between them, keyed by both ``(a, b)`` orders."""
    extra: dict = {}
    for e in d.edges:
        text = edge_label(e)
        if not text or not _is_lateral(d, e):
            continue
        need = text_box(text, SMALL_PX)[0] + 2 * _LABEL_PAD + 24 - opts.nodesep
        if need > 0:
            for key in ((e.src, e.dst), (e.dst, e.src)):
                extra[key] = max(extra.get(key, 0.0), need)
    return extra


def _insert_dummies(d: Diagram) -> None:
    counter = 0
    for e in d.edges:
        if e.back or e.src == e.dst:
            e.path = [e.src, e.dst]
            continue
        ls, ld = d.nodes[e.src].layer, d.nodes[e.dst].layer
        path = [e.src]
        for layer_idx in range(ls + 1, ld):
            counter += 1
            did = f"__d{counter}"
            dn = Node(id=did, label="", kind="dummy", lane=d.nodes[e.dst].lane)
            dn.layer = layer_idx
            d.nodes[did] = dn
            path.append(did)
        path.append(e.dst)
        e.path = path


# -------------------------------------------------------------- ordering ---
def _order(d: Diagram, opts: LayoutOptions):
    nl = max((n.layer for n in d.nodes.values()), default=0) + 1
    layers: list[list[str]] = [[] for _ in range(nl)]
    succs = defaultdict(list)
    preds = defaultdict(list)
    for e in d.edges:
        if e.back or e.src == e.dst or _is_lateral(d, e):
            continue
        for a, b in zip(e.path, e.path[1:], strict=False):
            succs[a].append(b)
            preds[b].append(a)

    # initial order: DFS from the sources (iterative, so long chains are fine)
    visited = set()

    def visit(root):
        stack = [root]
        while stack:
            u = stack.pop()
            if u in visited:
                continue
            visited.add(u)
            layers[d.nodes[u].layer].append(u)
            stack.extend(reversed(succs[u]))

    for nid in d.nodes:
        if not preds[nid]:
            visit(nid)
    for nid in d.nodes:
        visit(nid)

    pos = {}
    # a feedback edge's dummies sort after a control action's when their
    # barycenters tie, so the pair of arrows between two boxes never crosses
    rank = defaultdict(int)
    for e in d.edges:
        for nid in e.path[1:-1]:
            rank[nid] = _edge_rank(e)

    def refresh():
        for layer_nodes in layers:
            for i, nid in enumerate(layer_nodes):
                pos[nid] = i

    refresh()

    def lane_key(nid):
        return d.lane_index(d.nodes[nid].lane) if d.lanes else 0

    def sweep(down: bool):
        rng = range(1, nl) if down else range(nl - 2, -1, -1)
        for li in rng:
            layer_nodes = layers[li]
            nb = preds if down else succs
            keys = {}
            for nid in layer_nodes:
                ns = nb[nid]
                keys[nid] = (sum(pos[v] for v in ns) / len(ns)) if ns else pos[nid]
            layer_nodes.sort(key=lambda nid: (lane_key(nid), keys[nid], rank[nid], pos[nid]))
            for i, nid in enumerate(layer_nodes):
                pos[nid] = i

    for _ in range(opts.iterations):
        sweep(down=True)
        sweep(down=False)
    for layer_nodes in layers:
        layer_nodes.sort(key=lambda nid: (lane_key(nid), pos[nid]))
    refresh()
    if not d.lanes:
        # the two ends of a lateral edge stand side by side so the arrow
        # between them crosses nothing
        for e in d.edges:
            if not _is_lateral(d, e):
                continue
            layer_nodes = layers[d.nodes[e.src].layer]
            i, j = layer_nodes.index(e.src), layer_nodes.index(e.dst)
            if abs(i - j) > 1:
                layer_nodes.pop(j)
                i = layer_nodes.index(e.src)
                layer_nodes.insert(i + 1 if j > i else i, e.dst)
        refresh()
    for layer_nodes in layers:
        for i, nid in enumerate(layer_nodes):
            d.nodes[nid].order = i
    return layers, preds, succs


# ----------------------------------------------------------- coordinates ---
def _gap_for_labels(d: Diagram, nlayers: int) -> list[float]:
    """Minimum gap below each layer so the labels of edges leaving it fit.

    Only matters for left-to-right diagrams, where a label's width has to fit
    between two columns; in top-to-bottom diagrams label height is small.
    """
    swap = d.direction == "LR"
    control = d.kind == "control_structure"
    need = [0.0] * nlayers
    for e in d.edges:
        if e.back or e.src == e.dst or _is_lateral(d, e):
            continue
        text = edge_label(e)
        if not text:
            continue
        w, h = text_box(text, SMALL_PX)
        extent = (w if swap else h) + 2 * _LABEL_PAD + 12
        if control:
            # the stack hangs beside the vertical run below the jog (_CONTROL_JOG)
            extent += _CONTROL_JOG + 16
        li = d.nodes[e.src].layer
        need[li] = max(need[li], extent)
    return need


_CHANNEL_ATTEMPTS = 4     # layouts of a control structure with growing channels


def _grow_channels(d: Diagram, layers, grow: list) -> bool:
    """Widen the channel under every layer whose signal stacks overlapped, by
    the height of the overlapping label; True when any channel grew."""
    tops = [min((d.nodes[n].top for n in layer_nodes), default=0.0) for layer_nodes in layers]
    grown = False
    for issue in d.issues:
        if issue.kind != "label_overlap" or issue.edge is None:
            continue
        e = next((e for e in d.edges if (e.src, e.dst) == issue.edge), None)
        if e is None or e.label_pos is None or e.src == e.dst or e.back:
            continue
        li = max((i for i, top in enumerate(tops) if top <= e.label_pos[1]), default=0)
        if li >= len(layers) - 1:
            continue
        grow[li] += text_box(edge_label(e), SMALL_PX)[1] + 2 * _LABEL_PAD
        grown = True
    return grown


def _assign_coordinates(d: Diagram, layers, preds, succs, opts: LayoutOptions, extra=None,
                        grow=None) -> None:
    nodes = d.nodes
    gaps = _gap_for_labels(d, len(layers))
    if grow:
        gaps = [g + extra_gap for g, extra_gap in zip(gaps, grow, strict=True)]
    y = opts.margin + (opts.lane_header if (d.lanes and d.direction == "TB") else 0) + 10
    for li, layer_nodes in enumerate(layers):
        hmax = max((nodes[n].h for n in layer_nodes), default=0.0)
        hmax = max(hmax, 10.0)
        for nid in layer_nodes:
            n = nodes[nid]
            n.y = y + hmax / 2
            if n.kind == "dummy":
                # a dummy spans its whole layer band so edges through it stay
                # vertical across the band and only jog in the gaps between layers
                n.h = hmax
        y += hmax + max(opts.ranksep, gaps[li])
    if d.lanes:
        _lane_coordinates(d, layers, preds, succs, opts)
    else:
        _free_coordinates(d, layers, preds, succs, opts, extra)


def _pack(ids, nodes, gap, start=0.0, extra=None):
    x = start
    prev = None
    for nid in ids:
        n = nodes[nid]
        if prev is not None and extra:
            x += extra.get((prev, nid), 0.0)
        n.x = x + n.w / 2
        x += n.w + gap
        prev = nid
    return x - gap


def _components(d: Diagram, preds, succs) -> list[list[str]]:
    """Connected components (ignoring direction), in first-seen node order."""
    seen = set()
    comps = []
    for root in d.nodes:
        if root in seen:
            continue
        comp = []
        stack = [root]
        seen.add(root)
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in preds[u] + succs[u]:
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        comps.append(comp)
    return comps


def _balance(layers, nodes, preds, succs, gap, rounds=24, extra=None) -> None:
    """Iteratively move nodes toward the mean x of their neighbours while
    keeping the in-layer order and minimum separation (``extra`` adds to the
    separation of a named pair of neighbours)."""
    extra = extra or {}
    for rnd in range(rounds):
        order = range(len(layers)) if rnd % 2 == 0 else range(len(layers) - 1, -1, -1)
        for li in order:
            layer_nodes = layers[li]
            if not layer_nodes:
                continue
            desired = {}
            for nid in layer_nodes:
                if rnd > 1:
                    nb = preds[nid] + succs[nid]
                else:
                    nb = preds[nid] if rnd % 2 == 0 else succs[nid]
                nb = [v for v in nb if nodes[v].layer != nodes[nid].layer]
                desired[nid] = sum(nodes[v].x for v in nb) / len(nb) if nb else nodes[nid].x
            xs = [desired[nid] for nid in layer_nodes]
            for i in range(1, len(layer_nodes)):
                a, b = nodes[layer_nodes[i - 1]], nodes[layer_nodes[i]]
                g = gap if (a.kind != "dummy" and b.kind != "dummy") else gap * 0.6
                sep = (a.w + b.w) / 2 + g + extra.get((a.id, b.id), 0.0)
                if xs[i] < xs[i - 1] + sep:
                    xs[i] = xs[i - 1] + sep
            shift = sum(xs[i] - desired[layer_nodes[i]] for i in range(len(layer_nodes))) / len(layer_nodes)
            for i, nid in enumerate(layer_nodes):
                nodes[nid].x = xs[i] - shift


def _free_coordinates(d, layers, preds, succs, opts, extra=None) -> None:
    """Place each connected component independently, then pack the components
    side by side.  Balancing components together lets unconnected parts drift
    apart a little every round, which compounds into large empty gaps."""
    nodes = d.nodes
    gap = opts.nodesep
    offset = 0.0
    cpreds, csuccs = preds, succs
    if extra is not None:
        # a control structure: the ends of a lateral edge belong to one component
        cpreds = defaultdict(list, {k: list(v) for k, v in preds.items()})
        csuccs = defaultdict(list, {k: list(v) for k, v in succs.items()})
        for e in d.edges:
            if _is_lateral(d, e):
                csuccs[e.src].append(e.dst)
                cpreds[e.dst].append(e.src)
    for comp in _components(d, cpreds, csuccs):
        member = set(comp)
        sub = [[nid for nid in layer_nodes if nid in member] for layer_nodes in layers]
        for layer_nodes in sub:
            width = _pack(layer_nodes, nodes, gap, extra=extra)
            for nid in layer_nodes:
                nodes[nid].x -= width / 2
        _balance(sub, nodes, preds, succs, gap, extra=extra)
        _snap(sub, nodes, preds, succs, gap, extra=extra)
        minx = min(nodes[nid].left for nid in comp)
        maxx = max(nodes[nid].right for nid in comp)
        for nid in comp:
            nodes[nid].x += offset - minx
        offset += (maxx - minx) + gap * 2


def _snap(layers, nodes, preds, succs, gap, bounds=None, max_jog=90.0, extra=None) -> None:
    """Straighten single-neighbour chains: move a node onto its only
    predecessor's x (or only successor's) when that does not collide."""
    extra = extra or {}
    for _ in range(4):
        for layer_nodes in layers:
            for i, nid in enumerate(layer_nodes):
                n = nodes[nid]
                p, s = preds[nid], succs[nid]
                target = None
                if len(p) == 1 and len(succs[p[0]]) == 1:
                    target = nodes[p[0]].x
                elif not p and len(s) == 1 and len(preds[s[0]]) == 1:
                    target = nodes[s[0]].x
                elif len(p) == 1 and n.kind == "dummy":
                    target = nodes[p[0]].x
                if target is None or abs(target - n.x) < 0.5 or abs(target - n.x) > max_jog:
                    continue
                lo, hi = -1e9, 1e9
                if i > 0:
                    m = nodes[layer_nodes[i - 1]]
                    lo = m.x + (m.w + n.w) / 2 + gap + extra.get((m.id, nid), 0.0)
                if i < len(layer_nodes) - 1:
                    m = nodes[layer_nodes[i + 1]]
                    hi = m.x - (m.w + n.w) / 2 - gap - extra.get((nid, m.id), 0.0)
                if bounds:
                    blo, bhi = bounds(n)
                    lo, hi = max(lo, blo + n.w / 2), min(hi, bhi - n.w / 2)
                if lo <= target <= hi:
                    n.x = target


def _lane_coordinates(d, layers, preds, succs, opts) -> None:
    nodes = d.nodes
    gap = opts.nodesep
    nlanes = len(d.lanes)
    req = [0.0] * nlanes
    for layer_nodes in layers:
        by_lane = defaultdict(list)
        for nid in layer_nodes:
            by_lane[d.lane_index(nodes[nid].lane)].append(nid)
        for li, ids in by_lane.items():
            w = sum(nodes[i].w for i in ids) + gap * (len(ids) - 1)
            req[li] = max(req[li], w)
    for i, ln in enumerate(d.lanes):
        req[i] = max(req[i] + 2 * opts.lane_pad, text_width(ln.title, SMALL_PX) + 40, 150.0)
    x = opts.margin
    for i, ln in enumerate(d.lanes):
        ln.x0 = x
        ln.x1 = x + req[i]
        x = ln.x1
    for layer_nodes in layers:
        by_lane = defaultdict(list)
        for nid in layer_nodes:
            by_lane[d.lane_index(nodes[nid].lane)].append(nid)
        for li, ids in by_lane.items():
            ln = d.lanes[li]
            w = sum(nodes[i].w for i in ids) + gap * (len(ids) - 1)
            _pack(ids, nodes, gap, start=(ln.x0 + ln.x1) / 2 - w / 2)
    for _ in range(10):
        for layer_nodes in layers:
            by_lane = defaultdict(list)
            for nid in layer_nodes:
                by_lane[d.lane_index(nodes[nid].lane)].append(nid)
            for li, ids in by_lane.items():
                ln = d.lanes[li]
                lo, hi = ln.x0 + opts.lane_pad, ln.x1 - opts.lane_pad
                desired = []
                for nid in ids:
                    nb = [v for v in preds[nid] + succs[nid] if nodes[v].lane == nodes[nid].lane]
                    desired.append(sum(nodes[v].x for v in nb) / len(nb) if nb else nodes[nid].x)
                for i in range(1, len(ids)):
                    sep = (nodes[ids[i - 1]].w + nodes[ids[i]].w) / 2 + gap
                    desired[i] = max(desired[i], desired[i - 1] + sep)
                first_left = desired[0] - nodes[ids[0]].w / 2
                last_right = desired[-1] + nodes[ids[-1]].w / 2
                shift = 0.0
                if first_left < lo:
                    shift = lo - first_left
                elif last_right > hi:
                    shift = hi - last_right
                for i, nid in enumerate(ids):
                    nodes[nid].x = desired[i] + shift

    def bounds(n):
        ln = d.lanes[d.lane_index(n.lane)]
        return ln.x0 + opts.lane_pad, ln.x1 - opts.lane_pad

    _snap(layers, nodes, preds, succs, gap, bounds=bounds)


# ---------------------------------------------------------------- routing ---
_CONTROL_JOG = 12.0       # a control-structure arrow jogs this far below its source box


def _route_edges(d: Diagram, layers, opts: LayoutOptions) -> None:
    nodes = d.nodes
    control = d.kind == "control_structure"
    band_bottom = [max((nodes[n].bottom for n in layer_nodes), default=0.0) for layer_nodes in layers]
    for e in d.edges:
        e.points = []
    out_edges = defaultdict(list)
    in_edges = defaultdict(list)
    lateral = defaultdict(list)
    for e in d.edges:
        if e.back or e.src == e.dst:
            continue
        if _is_lateral(d, e):
            lateral[frozenset((e.src, e.dst))].append(e)
            continue
        out_edges[e.src].append(e)
        in_edges[e.dst].append(e)

    def spread(node, edges, outgoing):
        if node.kind in ("decision", "start", "end", "flowfinal", "merge", "dummy"):
            return {id(e): 0.0 for e in edges}
        if len(edges) <= 1:
            return {id(e): 0.0 for e in edges}
        if outgoing:
            es = sorted(edges, key=lambda e: (nodes[e.path[1]].x, _edge_rank(e)))
        else:
            es = sorted(edges, key=lambda e: (nodes[e.path[-2]].x, _edge_rank(e)))
        # a control-structure box spreads its arrows over more of its width so
        # the signal stacks beside them have room
        span = node.w * (0.7 if node.kind in ("fork", "join") or node.kind in CONTROL_NODE_KINDS else 0.5)
        n = len(es)
        return {id(e): -span / 2 + span * i / (n - 1) for i, e in enumerate(es)}

    # a lateral edge runs straight between two boxes of one layer; a pair of
    # them (a request and its answer) runs as two parallel lines, the control
    # action above the feedback
    for es in lateral.values():
        es.sort(key=_edge_rank)
        for k, e in enumerate(es):
            s, t = nodes[e.src], nodes[e.dst]
            y = s.y + (k - (len(es) - 1) / 2) * 16.0
            e.points = [(s.right, y), (t.left, y)] if s.x < t.x else [(s.left, y), (t.right, y)]

    out_off, in_off = {}, {}
    for nid, es in out_edges.items():
        out_off.update(spread(nodes[nid], es, True))
    for nid, es in in_edges.items():
        in_off.update(spread(nodes[nid], es, False))

    # channel offsets between layers so parallel horizontals do not overlap
    gap_edges = defaultdict(list)
    for e in d.edges:
        if e.back or e.src == e.dst or e.points:
            continue
        for a, b in zip(e.path, e.path[1:], strict=False):
            if abs(nodes[a].x - nodes[b].x) > 1.0:
                gap_edges[nodes[a].layer].append((e, a, b))
    chan = {}
    for items in gap_edges.values():
        items.sort(key=lambda t: (nodes[t[1]].x, nodes[t[2]].x))
        n = len(items)
        step = min(8.0, (opts.ranksep * 0.6) / max(1, n))
        for i, (e, a, b) in enumerate(items):
            chan[(id(e), a, b)] = (i * step) if control else (i - (n - 1) / 2) * step

    for e in d.edges:
        if e.src == e.dst:
            n = nodes[e.src]
            r = n.right
            e.points = [(r, n.y - 8), (r + 28, n.y - 8), (r + 28, n.y + 8), (r, n.y + 8)]
            continue
        if e.back or e.points:
            continue
        pts = []
        src = nodes[e.path[0]]
        first_x = nodes[e.path[1]].x
        sx = src.x + out_off.get(id(e), 0.0)
        side_exit = False
        span_lo = min(src.x, first_x) - nodes[e.path[1]].w / 2 - 6
        span_hi = max(src.x, first_x) + nodes[e.path[1]].w / 2 + 6
        if src.kind == "decision" and abs(first_x - src.x) > src.w * 0.75 and not any(
                nodes[o].kind != "dummy" and nodes[o].right > span_lo and nodes[o].left < span_hi
                for o in layers[src.layer] if o != e.path[0]):
            # leave a decision sideways when the target is clearly off to one
            # side and no other node in the row is in the way
            side = 1 if first_x > src.x else -1
            pts.append((src.x + side * src.w / 2, src.y))
            side_exit = True
        else:
            pts.append((sx, src.bottom))
        path = e.path
        for i in range(len(path) - 1):
            a, b = nodes[path[i]], nodes[path[i + 1]]
            bx = b.x + (in_off.get(id(e), 0.0) if i == len(path) - 2 else 0.0)
            ax_ = pts[-1][0]
            if i == 0 and side_exit:
                pts.append((bx, src.y))
                pts.append((bx, b.top))
                continue
            if abs(ax_ - bx) > 1.0:
                # a control-structure arrow jogs just under its source so one
                # long vertical run reaches the target with its signal stack
                # hanging beside it in the channel between the two boxes
                ymid = (band_bottom[a.layer] + _CONTROL_JOG) if control else (a.bottom + b.top) / 2
                ymid += chan.get((id(e), path[i], path[i + 1]), 0.0)
                pts.append((ax_, ymid))
                pts.append((bx, ymid))
            else:
                bx = ax_          # keep sub-pixel drift from slanting the line
            pts.append((bx, b.top))
        e.points = _simplify(pts)

    backs = [e for e in d.edges if e.back and e.src != e.dst]
    backs.sort(key=lambda e: nodes[e.src].layer - nodes[e.dst].layer)
    used = 0
    for e in backs:
        s, t = nodes[e.src], nodes[e.dst]
        lo, hi = min(s.layer, t.layer), max(s.layer, t.layer)
        right = max((nodes[n].right for layer_nodes in layers[lo:hi + 1] for n in layer_nodes), default=0)
        if d.lanes:
            ln = d.lanes[d.lane_index(s.lane)]
            lane_nodes = [nodes[n] for layer_nodes in layers[lo:hi + 1] for n in layer_nodes
                          if nodes[n].lane == s.lane]
            right = max((n.right for n in lane_nodes), default=s.right)
            right = min(right, ln.x1 - 30)
        used += 1
        xch = right + opts.back_channel * 0.6 + 14 * used
        e.points = [(s.right, s.y), (xch, s.y), (xch, t.y), (t.right, t.y)]


def _simplify(pts):
    out = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 0.5 and abs(out[-1][1] - p[1]) < 0.5:
            continue
        out.append(p)
    if len(out) < 3:
        return out
    res = [out[0]]
    for i in range(1, len(out) - 1):
        a, b, c = res[-1], out[i], out[i + 1]
        if (abs(a[0] - b[0]) < 0.5 and abs(b[0] - c[0]) < 0.5) or \
           (abs(a[1] - b[1]) < 0.5 and abs(b[1] - c[1]) < 0.5):
            continue
        res.append(b)
    res.append(out[-1])
    return res


# ----------------------------------------------------------------- labels ---
_LABEL_PAD = 4.0
_LABEL_T = (0.5, 0.35, 0.65, 0.2, 0.8)
# a control structure slides a stack along its arrow in finer steps
_LABEL_T_FINE = (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.1, 0.9)


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _place_labels(d: Diagram, swap: bool) -> list:
    """Choose ``label_pos`` for every labelled edge.

    Labels sit centred on the longest segment of their edge.  If that spot
    collides with a node or an already placed label, other points along the
    edge's segments (longest first) are tried; the last resort is to hang the
    label beside the segment.  Returns the placed label boxes so the canvas can
    be sized to contain them.
    """
    obstacles = [(n.left - 2, n.top - 2, n.right + 2, n.bottom + 2) for n in d.real_nodes()]
    placed: list = []

    def box_of(text):
        w, h = text_box(text, SMALL_PX)
        if swap:
            w, h = h, w
        return w + 2 * _LABEL_PAD, h + 2 * _LABEL_PAD

    def rect(cx, cy, w, h, ha="center", va="center"):
        x0 = cx if ha == "left" else cx - w / 2
        y0 = cy if va == "top" else cy - h / 2
        return (x0, y0, x0 + w, y0 + h)

    def overlap_area(r):
        total = 0.0
        for o in obstacles + placed:
            if _overlaps(r, o):
                total += (min(r[2], o[2]) - max(r[0], o[0])) * (min(r[3], o[3]) - max(r[1], o[1]))
        return total

    control = d.kind == "control_structure"
    steps = _LABEL_T_FINE if control else _LABEL_T
    edges = list(d.edges)
    if control:
        # the tallest stacks take their place first
        edges.sort(key=lambda e: -len(edge_label(e).split("\n")))
    for e in edges:
        text = edge_label(e)
        if not text or not e.points:
            continue
        w, h = box_of(text)
        if e.src == e.dst:
            n = d.nodes[e.src]
            e.label_pos, e.label_ha = (n.right + 34, n.y), "left"
            r = rect(*e.label_pos, w, h, ha="left")
            _note_overlap(d, e, text, overlap_area(r))
            placed.append(r)
            continue
        if e.back:
            # hang the label to the right of the vertical channel, sliding
            # along it to the least crowded spot
            (xch, y1), (_, y2) = e.points[1], e.points[2]
            best, best_area = None, None
            for t in _LABEL_T:
                r = rect(xch + 6, y1 + (y2 - y1) * t, w, h, ha="left")
                area = overlap_area(r)
                if best_area is None or area < best_area:
                    best, best_area = (r[0], y1 + (y2 - y1) * t), area
                if area == 0.0:
                    break
            e.label_pos, e.label_ha = best, "left"
            _note_overlap(d, e, text, best_area)
            placed.append(rect(*best, w, h, ha="left"))
            continue
        segs = sorted(zip(e.points, e.points[1:], strict=False),
                      key=lambda s: -(abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1])))
        # candidates: points along each segment (longest first), centred on the
        # line, then hanging beside it; the first collision-free one wins and
        # otherwise the one with the least overlap
        best, best_area = None, None
        side = {"control_action": -1.0, "feedback": 1.0}.get(e.kind)
        for a, b in segs:
            vertical = abs(a[0] - b[0]) < abs(a[1] - b[1])
            if side is not None and vertical:
                # a signal label hangs beside its arrow, control actions on
                # the left and feedback on the right, so the two labels of a
                # pair of arrows sit on opposite sides and never meet
                offsets = ((side * (w / 2 + 4), 0), (-side * (w / 2 + 4), 0))
            elif side is not None:
                # on a horizontal run the control action's label sits above
                # the line and the feedback's below it
                offsets = ((0, side * (h / 2 + 2)), (0, -side * (h / 2 + 2)))
            else:
                offsets = ((0, 0), (w / 2 + 4, 0) if vertical else (0, -(h / 2 + 2)))
            for t in steps:
                cx, cy = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                for dx, dy in offsets:
                    area = overlap_area(rect(cx + dx, cy + dy, w, h))
                    if best_area is None or area < best_area:
                        best, best_area = (cx + dx, cy + dy), area
                    if area == 0.0:
                        break
                if best_area == 0.0:
                    break
            if best_area == 0.0:
                break
        e.label_pos = best
        _note_overlap(d, e, text, best_area)
        placed.append(rect(*best, w, h))
    return placed


def _note_overlap(d: Diagram, e, text: str, area: float) -> None:
    if area > 0.0:
        d.issues.append(LayoutIssue(
            "label_overlap",
            f"label {text!r} on edge {e.src}->{e.dst} overlaps a node or another label "
            f"({area:.0f} px\u00b2)",
            edge=(e.src, e.dst)))


def _check_edge_crossings(d: Diagram) -> None:
    """Record every routed edge segment that passes through an unrelated node."""
    real = d.real_nodes()
    for e in d.edges:
        if e.back or e.src == e.dst or len(e.points) < 2:
            continue
        hit = None
        for (x0, y0), (x1, y1) in zip(e.points, e.points[1:], strict=False):
            for n in real:
                if n.id in (e.src, e.dst):
                    continue
                if abs(x0 - x1) < 0.5:
                    inside = (n.left + 1 < x0 < n.right - 1
                              and min(y0, y1) < n.bottom - 1 and max(y0, y1) > n.top + 1)
                else:
                    inside = (n.top + 1 < y0 < n.bottom - 1
                              and min(x0, x1) < n.right - 1 and max(x0, x1) > n.left + 1)
                if inside:
                    hit = n.id
                    break
            if hit:
                break
        if hit:
            d.issues.append(LayoutIssue(
                "edge_through_node", f"edge {e.src}->{e.dst} passes through node {hit!r}",
                edge=(e.src, e.dst), node=hit))


# ---------------------------------------------------------------- notes ----
def _detach_notes(d: Diagram):
    """Take the notes attached to a box out of the graph for the core steps;
    ``_attach_notes`` puts them back beside their box."""
    order = list(d.nodes)
    attached = {nid: n for nid, n in d.nodes.items()
                if n.kind == "note" and n.attached_to is not None and n.attached_to in d.nodes}
    for nid in attached:
        del d.nodes[nid]
    return order, attached


def _attach_notes(d: Diagram, order, attached, opts: LayoutOptions) -> None:
    """Float each attached note beside its box: to the right of it, level with
    its top, else to the left, else further right past whatever is in the way."""
    if not attached:
        return
    others = [n for n in d.nodes.values() if n.kind != "dummy"]
    gap = opts.nodesep * 0.3 + 8
    for note in attached.values():
        host = d.nodes[note.attached_to]
        note.layer = host.layer
        note.y = host.top + note.h / 2
        right, left = host.right + gap + note.w / 2, host.left - gap - note.w / 2
        step = note.w + gap
        candidates = [right, left] + [right + step * k for k in range(1, 6)] + [left - step * k for k in range(1, 6)]
        clear = [x for x in candidates if not _note_hits(note, x, others, d)]
        if clear:
            note.x = clear[0]
        else:
            # no clear spot beside the host: the first one free of other boxes
            note.x = next((x for x in candidates if not _note_hits(note, x, others, None)), right)
        others.append(note)
    # restore the author's node order
    rest = dict(d.nodes)
    d.nodes.clear()
    for nid in order:
        d.nodes[nid] = attached[nid] if nid in attached else rest.pop(nid)
    d.nodes.update(rest)      # the dummies


def _note_hits(note: Node, x: float, others, d: Diagram | None) -> bool:
    """True when the note at centre ``x`` touches another box or, when ``d``
    is given, a routed edge segment."""
    note.x = x
    if any(_boxes_touch(note, o) for o in others):
        return True
    if d is None:
        return False
    pad = 6.0
    for e in d.edges:
        for (x0, y0), (x1, y1) in zip(e.points, e.points[1:], strict=False):
            if (max(x0, x1) >= note.left - pad and min(x0, x1) <= note.right + pad
                    and max(y0, y1) >= note.top - pad and min(y0, y1) <= note.bottom + pad):
                return True
    return False


def _boxes_touch(a: Node, b: Node, pad: float = 4.0) -> bool:
    return not (a.right + pad <= b.left or b.right + pad <= a.left
                or a.bottom + pad <= b.top or b.bottom + pad <= a.top)


# ------------------------------------------------------------- finishing ---
def _normalize(d: Diagram, opts: LayoutOptions, label_boxes) -> None:
    nodes = list(d.nodes.values())
    xs = [n.left for n in nodes] + [p[0] for e in d.edges for p in e.points] + [b[0] for b in label_boxes]
    ys = [n.top for n in nodes] + [p[1] for e in d.edges for p in e.points] + [b[1] for b in label_boxes]
    xs2 = [n.right for n in nodes] + [p[0] for e in d.edges for p in e.points] + [b[2] for b in label_boxes]
    ys2 = [n.bottom for n in nodes] + [p[1] for e in d.edges for p in e.points] + [b[3] for b in label_boxes]
    if d.lanes:
        xs += [ln.x0 for ln in d.lanes]
        xs2 += [ln.x1 for ln in d.lanes]
    minx, miny = min(xs, default=0.0), min(ys, default=0.0)
    maxx, maxy = max(xs2, default=0.0), max(ys2, default=0.0)
    header = (opts.lane_header + 4) if d.lanes else 0
    if d.frame:
        header += 34
    dx = opts.margin - minx
    dy = opts.margin + header - miny
    for n in nodes:
        n.x += dx
        n.y += dy
    for e in d.edges:
        e.points = [(x + dx, y + dy) for x, y in e.points]
        if e.label_pos:
            e.label_pos = (e.label_pos[0] + dx, e.label_pos[1] + dy)
    for ln in d.lanes:
        ln.x0 += dx
        ln.x1 += dx
    d.width = maxx + dx + opts.margin
    d.height = maxy + dy + opts.margin
    d.lane_top = opts.margin + (34 if d.frame else 0)
    d.lane_bottom = d.height - opts.margin + 6
    d.lane_header = opts.lane_header


def _transpose(d: Diagram) -> None:
    for n in d.nodes.values():
        n.x, n.y = n.y, n.x
        n.w, n.h = n.h, n.w
    for e in d.edges:
        e.points = [(y, x) for x, y in e.points]
        if e.label_pos:
            e.label_pos = (e.label_pos[1], e.label_pos[0])
            if e.label_ha == "left":
                # "right of a vertical channel" becomes "below a horizontal one"
                e.label_ha, e.label_va = "center", "top"
    d.width, d.height = d.height, d.width
