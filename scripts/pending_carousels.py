"""See src/pending_carousels.py for what this does and how to use it.

    .venv\\Scripts\\python.exe scripts\\pending_carousels.py --help

Claude is never called. Nothing is ever posted to Facebook or Instagram.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pending_carousels  # noqa: E402  (the src folder is added to the path first)

if __name__ == "__main__":
    sys.exit(pending_carousels.main())
