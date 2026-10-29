"""The version is written in four places; a half-done bump must fail the suite."""
import re
import tomllib
from pathlib import Path

from asi_escher import __version__

ROOT = Path(__file__).resolve().parent.parent


def test_version_is_the_same_everywhere():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    readme_version = re.search(r"Version \*\*(\d+\.\d+\.\d+)\*\*", readme).group(1)
    top_entry = re.search(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", changelog, re.M).group(1)
    assert pyproject == readme_version == top_entry == __version__
    assert f'tag = "v{pyproject}"' in readme            # the git-source example pins the current release
