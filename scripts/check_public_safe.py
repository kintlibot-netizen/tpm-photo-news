"""Fails when a file git would commit holds a secret, a .env value, a personal detail or a path from a PC.
The repository is public, so run this before every commit (the cloud workflow runs it before it commits too).

    python scripts/check_public_safe.py

The work is done by src/public_safe.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import public_safe  # noqa: E402  (the src folder is added to the path first)

if __name__ == "__main__":
    sys.exit(public_safe.main())
