"""Generate every bundled example into ./out (same as ``asi-escher gallery``).

    uv run python demos/build_all.py [out_dir]
"""
import os
import sys

from asi_escher.gallery import build_gallery

if __name__ == "__main__":
    build_gallery(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "out"))
