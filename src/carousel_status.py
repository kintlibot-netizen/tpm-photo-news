"""status.json and README-for-review.txt for each carousel folder.

Statuses: draft (after a build), approved (David or Kint approved it), rejected, posted (logged per account
by review.py). Rebuilding a folder updates the build facts but never resets an approved, rejected or posted
status, so a rebuild cannot silently undo a review.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("draft", "waiting_for_david", "approved", "rejected", "posted")
STATUS_LABELS = {
    "draft": "Draft",
    "waiting_for_david": "Waiting for David",
    "approved": "Approved",
    "rejected": "Rejected",
    "posted": "Posted",
}
STATUS_FILE = "status.json"


def read_status(folder: Path) -> dict:
    path = folder / STATUS_FILE
    if not path.exists():
        return {"status": "draft", "history": [], "build": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "draft", "history": [], "build": {}}
    data.setdefault("status", "draft")
    data.setdefault("history", [])
    data.setdefault("build", {})
    data.setdefault("posts", [])
    return data


def _write(folder: Path, data: dict) -> None:
    (folder / STATUS_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def passes_review(build: dict) -> bool:
    """A draft is ready for David when its fact check and design check passed, and its text fit the slides.
    Claims the fact check could not confirm are removed before this point, so the slides only carry confirmed facts."""
    return (build.get("fact_check_passed") is True and build.get("design_fail", 0) == 0
            and build.get("lint_passed") is True and not build.get("sample"))


def write_build(folder: Path, build: dict) -> dict:
    """Records what the last build produced. A reviewed status (approved, rejected, posted) is kept as it is.
    A draft becomes Waiting for David when it passes the checks, and goes back to Draft when it does not."""
    data = read_status(folder)
    before = data["status"]
    data["build"] = build
    data["built_at"] = _now()
    if data["status"] not in STATUSES:
        data["status"] = "draft"
    if data["status"] in ("draft", "waiting_for_david"):
        data["status"] = "waiting_for_david" if passes_review(build) else "draft"
    if not any(h.get("event") == "built" for h in data["history"]):
        data["history"].append({"event": "built", "at": data["built_at"]})
    _write(folder, data)
    if data["status"] == "waiting_for_david" and before != "waiting_for_david":
        import activity  # imported here: the status file is written first, the log is extra
        activity.log_event("review", "waiting_for_david",
                           f"{build.get('title') or folder.name}: passed the fact and design checks, "
                           f"waiting for David ({folder.name})")
    return data


def set_status(folder: Path, status: str, **fields) -> dict:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    data = read_status(folder)
    data["status"] = status
    data.update(fields)
    data["history"].append({"event": status, "at": _now(), **fields})
    _write(folder, data)
    return data


def review_readme(title: str, folder_name: str, build: dict) -> str:
    """The plain-English note Kint or David reads before approving."""
    lines = [
        f"REVIEW: {title}",
        f"Folder: {folder_name}",
        "",
        "What is here:",
        "  01.png, 02.png ... the slides (1080 x 1440)",
        "  <folder>.zip       the download: slides in order, captions per account, sources",
        "  captions.txt       the captions, one per account",
        "  factcheck.md       every claim and the official quote it matched",
        "  sources.md         the official page used and the images used",
        "  candidates.md      the candidate images that were found",
        "  images\\            the product images on the slides",
        "",
        f"Slides: {build.get('slides', '?')}",
        f"Facts confirmed: {build.get('confirmed', '?')}. Removed as not confirmed: {build.get('removed_count', '?')}.",
        f"Missing images (placeholder shown): {', '.join(build.get('missing', [])) or 'none'}",
        f"Design check: {build.get('design_summary', 'not run')}",
        "",
        "To approve:  .venv\\Scripts\\python.exe src\\review.py --approve <this folder> --by \"Name\"",
        "To reject:   .venv\\Scripts\\python.exe src\\review.py --reject <this folder> --reason \"...\"",
        "Nothing is posted automatically. Posting is done by hand, then logged with --posted.",
        "",
    ]
    return "\n".join(lines)


def write_review_readme(folder: Path, title: str, build: dict) -> None:
    (folder / "README-for-review.txt").write_text(review_readme(title, folder.name, build), encoding="utf-8")
