"""asi_escher - pure-Python diagram generator.

Builds activity diagrams, flowcharts, state machines, SysML-style block /
internal-block / requirement diagrams, STPA control structures, chains
(precedence networks of a plan: what blocks what) and gantt charts (the
plan's tasks as bars on a time scale), lays them out with a
built-in layered (Sugiyama-style) algorithm, writes the layout as an editable
draw.io file and renders it to PNG + SVG via matplotlib.  It also
exports Graphviz DOT and Mermaid source so the same diagram can be re-rendered
elsewhere when those toolchains are available.

Typical use::

    from asi_escher import Diagram, build

    d = Diagram("Login", "flowchart")
    d.start(); d.action("check", "Check credentials"); d.end()
    d.chain("start", "check", "end")
    build(d, "out")          # writes out/login.drawio and out/login.png
"""
from .export import to_dot, to_drawio, to_mermaid
from .layout import LayoutOptions, LayoutWarning, layout
from .model import (
    CHAIN_EDGE_KINDS,
    CHAIN_NODE_KINDS,
    CHAIN_STATUSES,
    CONTROL_EDGE_KINDS,
    CONTROL_NODE_KINDS,
    DIAGRAM_KINDS,
    EDGE_KINDS,
    EDGE_STYLES,
    GANTT_EDGE_KINDS,
    GANTT_NODE_KINDS,
    NODE_KINDS,
    Diagram,
    Edge,
    Lane,
    LayoutIssue,
    Node,
    Period,
)
from .ocr import OcrReport, expected_labels, ocr_check
from .pipeline import ALL_FORMATS, DEFAULT_FORMATS, FORMATS, build
from .provenance import package_version
from .render import THEME, render

__version__ = package_version()

__all__ = [
    "Diagram", "Node", "Edge", "Lane", "Period", "LayoutIssue", "LayoutWarning",
    "DIAGRAM_KINDS", "NODE_KINDS", "EDGE_KINDS", "EDGE_STYLES", "CONTROL_NODE_KINDS", "CONTROL_EDGE_KINDS",
    "CHAIN_NODE_KINDS", "CHAIN_EDGE_KINDS", "CHAIN_STATUSES", "GANTT_NODE_KINDS", "GANTT_EDGE_KINDS",
    "LayoutOptions", "layout", "render", "THEME",
    "to_dot", "to_mermaid", "to_drawio", "build",
    "FORMATS", "DEFAULT_FORMATS", "ALL_FORMATS",
    "ocr_check", "expected_labels", "OcrReport",
    "__version__",
]
