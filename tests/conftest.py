import pytest

from asi_escher.examples import EXAMPLES


@pytest.fixture(params=[name for name, _ in EXAMPLES], ids=[name for name, _ in EXAMPLES])
def example(request):
    """Every bundled example diagram, freshly built."""
    return dict(EXAMPLES)[request.param]()
