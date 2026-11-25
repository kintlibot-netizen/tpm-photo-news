"""The activity log: one row per event, in data/activity-log.csv, kept as the record of every step (no longer shown on the dashboard).

Every hourly check, Slack alert, carousel build, fact check, review action, download, export and health message is
written here with its time in Manila, its type, its outcome and a short plain description.

Safety: a row never holds a secret or a path from this PC. scrub() removes Slack webhook addresses, tokens and
local file paths before anything is written, and logging never raises: a full disk or a locked file only skips the
row, so the watcher, the review buttons and the downloads keep working.
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "activity-log.csv"
MANILA = timezone(timedelta(hours=8), "Asia/Manila")  # Manila has no daylight saving time.
COLUMNS = ["time", "type", "outcome", "details", "who"]
DETAILS_LIMIT = 400

# Event types, with their plain names.
TYPES = {
    "check": "Hourly check",
    "alert": "Slack alert",
    "carousel": "Carousel build",
    "fact_check": "Fact check",
    "review": "Review",
    "download": "Download",
    "export": "Export for David",
    "health": "Health message",
    "cloud": "Cloud backup",
}

log = logging.getLogger("watcher")

_WEBHOOK = re.compile(r"https?://hooks\.slack(?:-gov)?\.com/\S*", re.I)
_TOKEN = re.compile(r"\bxox[a-z]-[A-Za-z0-9-]+|\b(?:sk|pk)-[A-Za-z0-9_-]{16,}", re.I)
_WINDOWS_PATH = re.compile(r"\b[A-Za-z]:[\\/](?:[^\s,;\"'<>|]+[\\/])*([^\s,;\"'<>|\\/]*)")
_HOME_PATH = re.compile(r"(?<![\w.:/])/(?:Users|home|mnt|tmp|var|private)/(?:[^\s,;\"'<>|]+/)*([^\s,;\"'<>|/]*)")


def scrub(text) -> str:
    """The text with webhook addresses, tokens and local paths removed. A path keeps only its last part (the file
    or folder name), so "D:\\Work\\...\\2026-11-11-photoshop" becomes "2026-11-11-photoshop"."""
    value = " ".join(str(text or "").split())
    value = _WEBHOOK.sub("[hidden]", value)
    value = _TOKEN.sub("[hidden]", value)
    value = _WINDOWS_PATH.sub(lambda m: m.group(1) or "[folder]", value)
    value = _HOME_PATH.sub(lambda m: m.group(1) or "[folder]", value)
    if len(value) > DETAILS_LIMIT:
        value = value[: DETAILS_LIMIT - 3].rstrip() + "..."
    return value


def _cell(text) -> str:
    """A CSV cell that a spreadsheet will not run as a formula."""
    value = scrub(text)
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def manila_time(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MANILA).isoformat(timespec="seconds")


def log_event(kind: str, outcome: str, details: str, who: str = "", now: datetime | None = None,
              path: Path | None = None) -> bool:
    """Appends one event. Returns True when it was written. Never raises."""
    target = Path(path) if path is not None else LOG_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        is_new = not target.exists() or target.stat().st_size == 0
        with open(target, "a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow({
                "time": manila_time(now),
                "type": kind if kind in TYPES else "check",
                "outcome": _cell(outcome),
                "details": _cell(details),
                "who": _cell(who),
            })
        return True
    except (OSError, ValueError, csv.Error) as exc:
        log.error("Activity log row was not written: %s", type(exc).__name__)
        return False


def parse_time(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=MANILA)


def read_events(path: Path | None = None, limit: int | None = None) -> list[dict]:
    """Every event, newest first. A missing or unreadable log is an empty list. Each row gets "at" (a datetime)."""
    target = Path(path) if path is not None else LOG_PATH
    try:
        with open(target, encoding="utf-8", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []
    events = []
    for row in rows:
        at = parse_time(row.get("time"))
        if at is None:
            continue
        events.append({
            "at": at, "type": row.get("type") or "check", "outcome": row.get("outcome") or "",
            "details": row.get("details") or "", "who": row.get("who") or "",
        })
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit] if limit else events


def week_counts(events: list[dict], now: datetime | None = None) -> dict[str, int]:
    """Counts for the last 7 days: checks, alerts sent, carousels built, approved, posted, downloads."""
    since = (now or datetime.now(timezone.utc)) - timedelta(days=7)
    recent = [e for e in events if e["at"] >= since]

    def count(kind: str, outcomes: tuple[str, ...] | None = None) -> int:
        return sum(1 for e in recent if e["type"] == kind and (outcomes is None or e["outcome"] in outcomes))

    return {
        "checks": count("check"),
        "alerts": count("alert", ("sent",)),
        "carousels": count("carousel", ("built",)),
        "approved": count("review", ("approved",)),
        "posted": count("review", ("posted",)),
        "downloads": count("download"),
    }
