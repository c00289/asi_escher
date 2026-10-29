"""asi_escher - pure-Python diagram generator.

Builds activity diagrams, flowcharts, state machines, SysML-style block /
internal-block / requirement diagrams and STPA control structures, lays them
out with a built-in layered (Sugiyama-style) algorithm, writes the layout as
an editable draw.io file and renders it to PNG + SVG via matplotlib.  It also
exports Graphviz DOT and Mermaid source so the same diagram can be re-rendered
elsewhere when those toolchains are available.

Typical use::

    from asi_escher import Diagram, build

    d = Diagram("Login", "flowchart")
    d.start(); d.action("check", "Check credentials"); d.end()
    d.chain("start", "check", "end")
    build(d, "out")          # writes out/login.drawio and out/login.png
"""
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from .export import to_dot, to_drawio, to_mermaid
from .layout import LayoutOptions, LayoutWarning, layout
from .model import (
    CONTROL_EDGE_KINDS,
    CONTROL_NODE_KINDS,
    DIAGRAM_KINDS,
    EDGE_KINDS,
    EDGE_STYLES,
    NODE_KINDS,
    Diagram,
    Edge,
    Lane,
    LayoutIssue,
    Node,
)
from .ocr import OcrReport, expected_labels, ocr_check
from .pipeline import ALL_FORMATS, DEFAULT_FORMATS, FORMATS, build
from .render import THEME, render

try:
    __version__ = _version("asi_escher")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

__all__ = [
    "Diagram", "Node", "Edge", "Lane", "LayoutIssue", "LayoutWarning",
    "DIAGRAM_KINDS", "NODE_KINDS", "EDGE_KINDS", "EDGE_STYLES", "CONTROL_NODE_KINDS", "CONTROL_EDGE_KINDS",
    "LayoutOptions", "layout", "render", "THEME",
    "to_dot", "to_mermaid", "to_drawio", "build",
    "FORMATS", "DEFAULT_FORMATS", "ALL_FORMATS",
    "ocr_check", "expected_labels", "OcrReport",
    "__version__",
]
