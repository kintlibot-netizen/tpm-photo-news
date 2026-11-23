"""See src/plan_build.py for what this does and how to use it.

    .venv\\Scripts\\python.exe scripts\\build_from_plan.py --help

Claude is never called. Nothing is ever posted to Facebook or Instagram.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import plan_build  # noqa: E402  (the src folder is added to the path first)

if __name__ == "__main__":
    sys.exit(plan_build.main())
