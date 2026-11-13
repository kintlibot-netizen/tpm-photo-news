"""One-time setup: copies the free Inter font (SIL Open Font License) into assets/fonts/.

Run once from the project folder:  .venv\\Scripts\\python.exe scripts\\fetch_fonts.py
Until it runs, the slides fall back to Arial or Segoe UI.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "assets" / "fonts"
URL = "https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip"
WANTED = {"Inter-Black.ttf", "Inter-SemiBold.ttf", "Inter-Regular.ttf"}
OPTIONAL = {"LICENSE.txt"}


def main() -> int:
    print(f"Downloading {URL}")
    response = requests.get(URL, timeout=120)
    response.raise_for_status()
    TARGET.mkdir(parents=True, exist_ok=True)
    found = set()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for member in archive.namelist():
            name = Path(member).name
            if name in WANTED and "/ttf/" in member.replace("\\", "/"):
                (TARGET / name).write_bytes(archive.read(member))
                found.add(name)
            elif name in OPTIONAL:
                (TARGET / name).write_bytes(archive.read(member))
    missing = WANTED - found
    if missing:
        print(f"Not found in the archive: {', '.join(sorted(missing))}")
        return 1
    print(f"Fonts saved to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
