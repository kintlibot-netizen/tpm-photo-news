"""Run history, per-feed results and story outcomes, for the dashboard.

These tables live in data/seen.sqlite next to the watcher's memory. They are added only when
missing (CREATE TABLE IF NOT EXISTS), so existing stories, sources and alerts are never touched.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

# Final statuses shown on the dashboard, in plain English.
ALERTED = "Sent to Slack"
HELD = "Waiting for a 2nd source"
REJECTED = "Rejected: not relevant"
SKIPPED = "Skipped"
DRY_ONLY = "Practice run only"
FAILED = "Send failed, will retry"
WAITING_SEND = "Waiting to send"
# Used inside a run only: judged to send, final status decided after delivery.
READY = "ready"

# Status words written by earlier rounds, read as their current names.
LEGACY_STATUS = {
    "Alerted to Slack": ALERTED,
    "Held - waiting for 2nd source": HELD,
    "Rejected": REJECTED,
    "Dry run only": DRY_ONLY,
    "Slack send failed, will retry": FAILED,
}


def normalize_status(status: str) -> str:
    return LEGACY_STATUS.get(status, status)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    articles INTEGER NOT NULL DEFAULT 0,
    in_window INTEGER NOT NULL DEFAULT 0,
    passed_rules INTEGER NOT NULL DEFAULT 0,
    alerts_ready INTEGER NOT NULL DEFAULT 0,
    alerts_sent INTEGER NOT NULL DEFAULT 0,
    held INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    feeds_ok INTEGER NOT NULL DEFAULT 0,
    feeds_failed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS feed_results (
    run_id INTEGER NOT NULL,
    feed TEXT NOT NULL,
    ok INTEGER NOT NULL,
    items INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    PRIMARY KEY (run_id, feed));
CREATE TABLE IF NOT EXISTS story_outcomes (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    story_id INTEGER,
    title TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    label TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    summary TEXT,
    first_seen TEXT,
    seen_at TEXT NOT NULL,
    sources TEXT);
CREATE INDEX IF NOT EXISTS idx_story_outcomes_story ON story_outcomes(story_id);
CREATE TABLE IF NOT EXISTS carousel_builds (
    id INTEGER PRIMARY KEY,
    story_id INTEGER NOT NULL,
    built_at TEXT NOT NULL,
    status TEXT NOT NULL,
    folder TEXT,
    message TEXT);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.executescript(SCHEMA)
    return db


def plain_error(raw: str | None) -> str | None:
    """Turns a technical feed error into one plain line. The full text stays in data/watcher.log."""
    if not raw:
        return None
    text = raw.lower()
    if "timed out" in text or "timeout" in text:
        return "The site took too long to answer."
    if "connection" in text or "resolve" in text or "getaddrinfo" in text or "name or service" in text:
        return "Could not connect to the site."
    match = re.search(r"\b([45]\d\d)\s+(client|server)\s+error", text)
    if match:
        return f"The site returned an error ({match.group(1)})."
    if "readable feed" in text:
        return "The site did not return a readable feed. It may have changed."
    if "larger than" in text:
        return "The feed was too large to read."
    return "Something went wrong reading this feed. Details are in data\\watcher.log."


def _latest_status(db: sqlite3.Connection, story_id: int) -> str | None:
    row = db.execute(
        "SELECT status FROM story_outcomes WHERE story_id=? ORDER BY id DESC LIMIT 1", (story_id,)
    ).fetchone()
    return normalize_status(row[0]) if row else None


def record_run(
    path: str | Path, mode: str, started: datetime, finished: datetime,
    counts: dict, feeds: list[dict], outcomes: list[dict],
) -> int:
    """Saves one run in a single transaction. Returns the new run id.

    A story's outcome is saved only when its status changes, so an hourly "still held" does not
    add a row every hour. Dry-run outcomes have no story id and are always saved.
    """
    db = connect(path)
    try:
        with db:
            cursor = db.execute(
                "INSERT INTO runs(started_at,finished_at,mode,articles,in_window,passed_rules,"
                "alerts_ready,alerts_sent,held,rejected,feeds_ok,feeds_failed) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    started.isoformat(), finished.isoformat(), mode,
                    counts["articles"], counts["in_window"], counts["passed_rules"],
                    counts["alerts_ready"], counts["alerts_sent"], counts["held"], counts["rejected"],
                    sum(1 for f in feeds if f["ok"]), sum(1 for f in feeds if not f["ok"]),
                ),
            )
            run_id = cursor.lastrowid
            db.executemany(
                "INSERT INTO feed_results(run_id,feed,ok,items,error) VALUES(?,?,?,?,?)",
                [(run_id, f["feed"], int(bool(f["ok"])), f["items"], f["error"]) for f in feeds],
            )
            for row in outcomes:
                story_id = row.get("story_id")
                if story_id is not None and _latest_status(db, story_id) == row["status"]:
                    continue
                db.execute(
                    "INSERT INTO story_outcomes(run_id,story_id,title,brand,category,label,status,"
                    "reason,summary,first_seen,seen_at,sources) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id, story_id, row["title"], row.get("brand"), row.get("category"),
                        row.get("label"), row["status"], row.get("reason"), row.get("summary"),
                        row.get("first_seen"), started.isoformat(), row.get("sources") or "[]",
                    ),
                )
        return run_id
    finally:
        db.close()
