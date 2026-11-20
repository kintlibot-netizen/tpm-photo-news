"""TPM Carousel Bot: makes the carousels by itself; Kint and David only approve. See src/carousel_bot.py.

    .venv\\Scripts\\python.exe scripts\\carousel_bot.py

The Windows task "TPM Carousel Bot" runs this every hour and at logon, with no window
(scripts/carousel_bot_hidden.vbs). Nothing asks a question and nothing waits for a key. The log is
logs/carousel-bot.log. Nothing is ever posted to Facebook or Instagram.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import carousel_bot  # noqa: E402  (the src folder is added to the path first)

if __name__ == "__main__":
    sys.exit(carousel_bot.main())
