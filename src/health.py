"""Health alerts: one Slack message to Kint when the watcher is not working, at most once a day.

The message is sent when either:
  - every feed failed in the last 2 runs in a row, or
  - the last run where any feed worked finished more than 6 hours ago.
It is checked when the watcher next runs (the check happens at the start of a live run). Each message
sent is saved in the health_alerts table, so no more than one is sent in 24 hours. The webhook is never logged.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests

import activity
import alert
import runlog

log = logging.getLogger("watcher")
STALE_AFTER = timedelta(hours=6)
FAILED_RUNS_IN_A_ROW = 2
ONE_PER_DAY = timedelta(hours=24)
TABLE = """
CREATE TABLE IF NOT EXISTS health_alerts (
    id INTEGER PRIMARY KEY,
    sent_at TEXT NOT NULL,
    reason TEXT NOT NULL);
"""


def _moment(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def reason_for(db_path: Path, now: datetime) -> str | None:
    """The plain reason the watcher looks unhealthy, or None when it is fine (or has no history yet)."""
    db = runlog.connect(db_path)
    try:
        recent = db.execute(
            "SELECT feeds_ok, feeds_failed FROM runs ORDER BY id DESC LIMIT ?", (FAILED_RUNS_IN_A_ROW,)
        ).fetchall()
        if len(recent) == FAILED_RUNS_IN_A_ROW and all(ok == 0 and failed > 0 for ok, failed in recent):
            return f"every feed failed in the last {FAILED_RUNS_IN_A_ROW} runs in a row"
        last_good = db.execute(
            "SELECT finished_at FROM runs WHERE feeds_ok > 0 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        db.close()
    if last_good is None:
        return None  # no run has ever worked, so there is nothing to measure the gap from
    finished = _moment(last_good[0])
    if finished is None:
        return None
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=now.tzinfo)
    if now - finished > STALE_AFTER:
        return f"no feed has worked since {finished:%Y-%m-%d %H:%M} UTC"
    return None


def sent_recently(db, now: datetime) -> bool:
    row = db.execute("SELECT sent_at FROM health_alerts ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return False
    last = _moment(row[0])
    return last is not None and now - last < ONE_PER_DAY


def run_if_needed(db_path: Path, now: datetime, url: str, send=alert.send_to_slack) -> str | None:
    """Sends the health message when needed and not sent in the last 24 hours. Returns the reason sent, or None."""
    reason = reason_for(db_path, now)
    if reason is None:
        return None
    db = runlog.connect(db_path)
    try:
        db.executescript(TABLE)
        if sent_recently(db, now):
            return None
        text = alert.escape(
            "Photo news watcher health check: " + reason + ". "
            "Check data\\watcher.log, and the System page on the dashboard."
        )
        try:
            send(text, url)
        except requests.RequestException as exc:
            log.error("Health message was not sent: %s", type(exc).__name__)
            return None
        with db:
            db.execute("INSERT INTO health_alerts(sent_at, reason) VALUES(?, ?)", (now.isoformat(), reason))
        activity.log_event("health", "sent", f"Health message sent to Slack: {reason}.", now=now)
        return reason
    finally:
        db.close()
