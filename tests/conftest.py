import pytest

from asi_escher import Diagram, layout, render
from asi_escher.examples import EXAMPLES
from asi_escher.ocr import recognize


@pytest.fixture(params=[name for name, _ in EXAMPLES], ids=[name for name, _ in EXAMPLES])
def example(request):
    """Every bundled example diagram, freshly built."""
    return dict(EXAMPLES)[request.param]()


@pytest.fixture(scope="session")
def ocr_engine(tmp_path_factory):
    """True when the Windows OCR engine runs here; otherwise the dependent tests skip."""
    d = Diagram("Probe")
    d.action("a", "Probe")
    path = tmp_path_factory.mktemp("ocr") / "probe.png"
    render(layout(d), png=str(path))
    return recognize(str(path)).available
