"""After official alerts, builds carousel drafts within the caps, and says so on Slack.

Caps count only successful builds: at most 1 a Manila calendar day and 3 in any 7 days. A failed
attempt uses up no cap, but a story gets at most 1 failed attempt. Every attempt is recorded in the
carousel_builds table. A story that is built once is never built again.

Stories still waiting (official, sent, 72 hours old or less, no successful build) are tried on later
runs, best first, so a story that was capped on the day it was sent is built the next day.

Nothing here posts anywhere except the Slack notification through the same webhook the alerts use.
Any error is caught: it is reported, and it never stops the hourly alert run.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import activity
import alert
import classify
import runlog

log = logging.getLogger("watcher")
DAILY_CAP = 1
WEEKLY_CAP = 3
MAX_FAILED_ATTEMPTS = 1
PENDING_HOURS = 72
MANILA = timezone(timedelta(hours=8), "Asia/Manila")  # Manila has no daylight saving time.
RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "rules.yaml"
# Best first: camera, lens, Photoshop and Lightroom stories before industry news.
PRIORITY = {"camera": 0, "lens": 1, "photoshop": 2, "lightroom": 3, "industry": 5}
DEFAULT_PRIORITY = 4


def _ok_builds_since(db, since: datetime) -> int:
    row = db.execute(
        "SELECT COUNT(*) FROM carousel_builds WHERE status='ok' AND built_at >= ?", (since.isoformat(),)
    ).fetchone()
    return int(row[0])


def manila_day_start(now: datetime) -> datetime:
    """Midnight at the start of the Manila calendar day that `now` falls in, in UTC."""
    local_day = now.astimezone(MANILA).date()
    return datetime.combine(local_day, datetime.min.time(), tzinfo=MANILA).astimezone(timezone.utc)


def may_build(db_path: Path, now: datetime) -> tuple[bool, str]:
    """(allowed, reason). Only successful builds count toward the caps."""
    db = runlog.connect(db_path)
    try:
        if _ok_builds_since(db, manila_day_start(now)) >= DAILY_CAP:
            return False, f"daily cap reached ({DAILY_CAP} a day)"
        if _ok_builds_since(db, now - timedelta(days=7)) >= WEEKLY_CAP:
            return False, f"weekly cap reached ({WEEKLY_CAP} a week)"
        return True, "within caps"
    finally:
        db.close()


def already_built(db_path: Path, story_id: int) -> bool:
    db = runlog.connect(db_path)
    try:
        row = db.execute("SELECT 1 FROM carousel_builds WHERE story_id=? AND status='ok'", (story_id,)).fetchone()
        return row is not None
    finally:
        db.close()


def failed_attempts(db_path: Path, story_id: int) -> int:
    db = runlog.connect(db_path)
    try:
        row = db.execute(
            "SELECT COUNT(*) FROM carousel_builds WHERE story_id=? AND status='failed'", (story_id,)
        ).fetchone()
        return int(row[0])
    finally:
        db.close()


def _rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as handle:
        return classify.normalize_rules(yaml.safe_load(handle))


def pending_stories(db_path: Path, now: datetime | None = None) -> list[tuple[int, str]]:
    """Official stories already sent, 72 hours old or less, with no successful carousel. Best first."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=PENDING_HOURS)).isoformat()
    db = runlog.connect(db_path)
    try:
        try:
            rows = db.execute(
                "SELECT s.id, s.title FROM stories s "
                "WHERE s.last_alert_label=? AND s.dismissed=0 AND s.first_seen>=? "
                "AND NOT EXISTS (SELECT 1 FROM carousel_builds b WHERE b.story_id=s.id AND b.status='ok')",
                (classify.OFFICIAL, cutoff),
            ).fetchall()
        except sqlite3.OperationalError:
            return []  # no stories table yet: nothing is waiting
    finally:
        db.close()
    rules = _rules()
    ranked = []
    for story_id, title in rows:
        category = classify.rule_category(title, rules)
        rank = PRIORITY.get(category, DEFAULT_PRIORITY)
        ranked.append((rank, -story_id, story_id, title))
    ranked.sort()
    return [(story_id, title) for _, _, story_id, title in ranked]


def record(db_path: Path, story_id: int, now: datetime, status: str, folder: str | None, message: str) -> None:
    db = runlog.connect(db_path)
    try:
        with db:
            db.execute(
                "INSERT INTO carousel_builds(story_id,built_at,status,folder,message) VALUES(?,?,?,?,?)",
                (story_id, now.isoformat(), status, folder, message[:500]),
            )
    finally:
        db.close()


# David's read only copy of the dashboard (GitHub Pages). Kint approves or rejects in her own dashboard.
DASHBOARD_URL = "https://kintlibot-netizen.github.io/tpm-photo-news/"


def ready_message(title: str, result: dict) -> str:
    """The Slack message when a carousel has been built for real and passed every check."""
    design = result.get("design", [])
    fails = sum(f["level"] == "FAIL" for f in design)
    warns = sum(f["level"] == "WARN" for f in design)
    placed = ", ".join(result.get("placed", [])) or "none"
    missing = ", ".join(result.get("missing", [])) or "none"
    removed = len(result.get("removed", []))
    lines = [
        f"Carousel ready for approval: {title}",
        "Made from the official page and checked by code. Nothing is posted automatically.",
        f"Slides: {result['slides']}",
        f"Facts: {result['confirmed']} confirmed, {removed} removed as not confirmed.",
        f"Official images placed: {placed}",
        f"Text only slides (no official image of that feature): {missing}",
        f"Design check: {fails} fail, {warns} warn.",
        "Approve or reject it in your dashboard (Needs your attention).",
        f"Dashboard: {DASHBOARD_URL}",
    ]
    return alert.escape("\n".join(lines))


def failed_message(title: str, reason: str) -> str:
    return alert.escape(f"Carousel not made for: {title}\nReason: {reason}")


USAGE_LIMIT_OUTCOME = "Claude usage limit"


def after_alerts(db_path: Path, stories: list[tuple[int, str]], now: datetime, webhook: str,
                 build, notify=alert.send_to_slack, max_failed: int = MAX_FAILED_ATTEMPTS) -> list[str]:
    """stories: (story id, title), in the order to try them. Returns what happened, per story.

    build(story_id) returns the assemble result (a dict) or raises. notify(text, webhook) posts to Slack.
    max_failed: how many failed builds a story may have before it is no longer tried (one more try is allowed when
    a caller asks for it). When Claude's usage limit is reached, nothing is recorded
    (it is not the story's fault) and the remaining stories wait for the next run.
    """
    outcomes = []
    for story_id, title in stories:
        try:
            if already_built(db_path, story_id):
                outcomes.append(f"{story_id}: already built")
                continue
            if failed_attempts(db_path, story_id) >= max_failed:
                outcomes.append(f"{story_id}: skipped (failed before, not retried)")
                continue
            allowed, reason = may_build(db_path, now)
            if not allowed:
                log.info("Carousel skipped for story %s: %s", story_id, reason)
                outcomes.append(f"{story_id}: skipped ({reason})")
                continue
            try:
                result = build(story_id)
            except classify.ClaudeUsageLimit as exc:
                log.warning("Carousel paused for story %s: %s. Trying again on the next run.", story_id, exc)
                outcomes.append(f"{story_id}: {USAGE_LIMIT_OUTCOME} (not counted, tried again next run)")
                break
            except Exception as exc:  # any build failure is reported, never raised
                reason = str(exc) or type(exc).__name__
                record(db_path, story_id, now, "failed", None, reason)
                log.error("Carousel not made for story %s: %s", story_id, reason)
                activity.log_event("carousel", "failed", f"Story {story_id}, {title}: {reason}", now=now)
                _notify_safely(notify, failed_message(title, reason), webhook)
                outcomes.append(f"{story_id}: failed ({reason})")
                continue
            record(db_path, story_id, now, "ok", str(result["folder"]), "draft ready")
            activity.log_event("carousel", "built", f"Story {story_id}, {title}: draft ready in "
                               f"{Path(str(result['folder'])).name}, {result.get('slides', '?')} slides", now=now)
            _notify_safely(notify, ready_message(title, result), webhook, sent_line="Carousel ready for approval sent")
            outcomes.append(f"{story_id}: draft ready at {result['folder']}")
        except Exception as exc:  # the alert run must never stop
            log.error("Carousel step failed for story %s: %s", story_id, type(exc).__name__)
            outcomes.append(f"{story_id}: step failed ({type(exc).__name__})")
    return outcomes


NEEDS_KINT = "needs_kint"  # the stored status name; the words shown are "Waiting for a carousel"
BOT_OUTCOME = "waiting for a carousel"
NEEDS_KINT_REASON = "Waiting for a carousel. It is made by hand from the official page, then Kint reviews it."


def needs_kint_marked(db_path: Path, story_id: int) -> bool:
    db = runlog.connect(db_path)
    try:
        row = db.execute("SELECT 1 FROM carousel_builds WHERE story_id=? AND status=?",
                         (story_id, NEEDS_KINT)).fetchone()
        return row is not None
    finally:
        db.close()


def needs_kint_message(title: str) -> str:
    return alert.escape(f"Waiting for a carousel: {title}\nThe cloud found an official story for a carousel. It is "
                        "made by hand from the official page, then Kint reviews it, and Slack says when it is ready "
                        "for approval. Nothing to do now. Nothing is posted automatically.")


def mark_needs_kint(db_path: Path, stories: list[tuple[int, str]], now: datetime, webhook: str,
                    notify=None) -> list[str]:
    """The cloud run: marks each story that still needs a carousel as 'needs Kint', once. The row does not count as
    a build or a failed attempt, so the laptop still builds it. Nothing is built and no image is ever used here."""
    notify = notify or alert.send_to_slack
    outcomes = []
    for story_id, title in stories:
        try:
            if already_built(db_path, story_id):
                outcomes.append(f"{story_id}: already built")
                continue
            if failed_attempts(db_path, story_id) >= MAX_FAILED_ATTEMPTS:
                outcomes.append(f"{story_id}: skipped (failed before, not retried)")
                continue
            if needs_kint_marked(db_path, story_id):
                outcomes.append(f"{story_id}: {BOT_OUTCOME} (already marked)")
                continue
            record(db_path, story_id, now, NEEDS_KINT, None, NEEDS_KINT_REASON)
            activity.log_event("carousel", BOT_OUTCOME, f"Story {story_id}, {title}: {NEEDS_KINT_REASON}", now=now)
            _notify_safely(notify, needs_kint_message(title), webhook)
            outcomes.append(f"{story_id}: {BOT_OUTCOME}")
        except Exception as exc:  # the alert run must never stop
            log.error("Carousel step failed for story %s: %s", story_id, type(exc).__name__)
            outcomes.append(f"{story_id}: step failed ({type(exc).__name__})")
    return outcomes


def _notify_safely(notify, text: str, webhook: str, sent_line: str | None = None) -> None:
    try:
        notify(text, webhook)
    except Exception as exc:
        log.error("Carousel message was not sent: %s", type(exc).__name__)
        return
    if sent_line:
        log.info(sent_line)
