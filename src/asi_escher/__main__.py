"""Allow ``python -m asi_escher``."""
import sys

from .cli import main

sys.exit(main())
