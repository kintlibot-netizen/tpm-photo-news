"""Export for David: builds output\\share\\TPM-News-Dashboard-<date>\\ and a matching zip.

    .venv\\Scripts\\python.exe scripts\\export_share_pack.py

A read only copy of the dashboard that David opens by double-clicking index.html, on any computer, with no install,
no server and no internet. No secrets, no paths from this PC and no review commands are in it; the export checks that
itself and refuses to finish otherwise. The work is done by src\\share_pack.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import share_pack  # noqa: E402  (the src folder is added to the path first)

if __name__ == "__main__":
    sys.exit(share_pack.main())
