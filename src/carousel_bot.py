"""TPM Carousel Bot: makes every carousel by itself, so nobody has to run anything. Kint and David only approve.

It runs on this laptop (Claude Code lives here; the cloud has no Claude), every hour and at logon, from the Windows
task "TPM Carousel Bot" (scripts/setup-carousel-bot-task.ps1), in a hidden window. One run:

  1. git pull --rebase                      the cloud's latest news and "being made by the carousel bot" marks
  2. cloud_state pull --side laptop         state/ into data/ and output/
  3. rebuilds each carousel a person rejected with a note, following the note (once per rejection)
  4. builds every waiting official story (the same caps, fact check, official image check and design check as any
     build). A build that fails gets one more try on a later run: a fresh draft that follows the failure reason.
  5. cloud_state push --side laptop         the new carousels and statuses into state/
  6. the public safety check                nothing secret or personal, no PC paths
  7. git commit "Carousel bot: new drafts" (state/ only) and git push, only when the check passed

Slack says when a carousel is ready for approval (the existing webhook from .env, never printed or logged). Nothing is
ever posted to Facebook or Instagram: posting stays manual in Meta Business Suite after approval.

A lock file stops two runs from overlapping. When Claude's usage limit is reached the run stops building, counts
nothing as failed, pushes what it finished and tries again on the next hourly run. Any error is logged; the bot never
crash-loops (the task simply runs again next hour). Log: logs/carousel-bot.log (every step with its time).

python scripts/carousel_bot.py     (the task runs it through scripts/carousel_bot_hidden.vbs, with no window)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import activity
import carousel_auto
import carousel_status
import classify

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "carousel-bot.log"
LOCK_FILE = LOG_DIR / "carousel-bot.lock"
LOCK_STALE_HOURS = 2  # a lock older than this was left by a run that was stopped; the task limit is 55 minutes
BOT_MAX_ATTEMPTS = 2  # a failed build gets one more try (a fresh draft that follows the failure reason)
MAX_REBUILDS_PER_RUN = 2
COMMIT_MESSAGE = "Carousel bot: new drafts"
log = logging.getLogger("watcher")  # the same logger as the watcher and the Timing lines


# ---------- the lock ----------

def acquire_lock(path: Path = LOCK_FILE, now: float | None = None) -> bool:
    """True when this run may go ahead. A lock left behind by a stopped run is taken over after LOCK_STALE_HOURS."""
    now = time.time() if now is None else now
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            with open(path, "x", encoding="utf-8") as handle:
                handle.write(json.dumps({"pid": os.getpid(), "started": now}))
            return True
        except FileExistsError:
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if age < LOCK_STALE_HOURS * 3600:
                return False
            log.warning("Carousel bot: an old lock (%.0f minutes) was left by a stopped run; taking it over.", age / 60)
            path.unlink(missing_ok=True)
    return False


def release_lock(path: Path = LOCK_FILE) -> None:
    path.unlink(missing_ok=True)


# ---------- git ----------

def run_git(args: list[str], root: Path = ROOT) -> tuple[bool, str]:
    """(worked, short output). Never raises. The output is only logged when a step fails."""
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=300, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, type(exc).__name__
    text = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode == 0, activity.scrub(text)[-300:]


def pull(git=run_git, root: Path = ROOT) -> bool:
    ok, output = git(["pull", "--rebase", "--autostash"], root)
    if not ok:
        git(["rebase", "--abort"], root)  # never leave the repository half way through a rebase
        log.error("Carousel bot: git pull did not work (%s). Building from the local state; the push waits.", output)
    return ok


def commit_and_push(git=run_git, root: Path = ROOT) -> str:
    """Commits state/ only (never any other file) and pushes. Returns what happened."""
    ok, output = git(["add", "-A", "--", "state"], root)
    if not ok:
        return f"not committed: git add failed ({output})"
    nothing, _ = git(["diff", "--cached", "--quiet", "--", "state"], root)
    if nothing:
        return "nothing new to commit"
    ok, output = git(["commit", "-m", COMMIT_MESSAGE, "--", "state"], root)
    if not ok:
        return f"not committed ({output})"
    if not pull(git, root):
        return "committed; the push waits for the next run (git pull did not work)"
    ok, output = git(["push"], root)
    return "committed and pushed" if ok else f"committed; the push did not work ({output}), tried again next run"


# ---------- which story a carousel folder belongs to ----------

def story_id_for_folder(db_path: Path, name: str) -> int | None:
    """The story a carousel folder was built for: from the build records, else from the folder name of each story."""
    if not db_path.exists():
        return None
    db = sqlite3.connect(db_path)
    try:
        try:
            for story_id, folder in db.execute("SELECT story_id, folder FROM carousel_builds WHERE status='ok' "
                                               "ORDER BY id DESC"):
                if folder and Path(str(folder).replace("\\", "/")).name == name:
                    return int(story_id)
        except sqlite3.OperationalError:
            pass
        try:
            rows = db.execute("SELECT id, title, first_seen FROM stories").fetchall()
        except sqlite3.OperationalError:
            return None
    finally:
        db.close()
    import carousel
    for story_id, title, first_seen in rows:
        try:
            seen = datetime.fromisoformat(first_seen) if first_seen else None
        except ValueError:
            seen = None
        if carousel.item_folder(title, seen).name == name:
            return int(story_id)
    return None


def last_failure(db_path: Path, story_id: int) -> str | None:
    if not db_path.exists():
        return None
    db = sqlite3.connect(db_path)
    try:
        row = db.execute("SELECT message FROM carousel_builds WHERE story_id=? AND status='failed' ORDER BY id DESC",
                         (story_id,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        db.close()
    return row[0] if row and row[0] else None


# ---------- the two kinds of work ----------

def default_build(db_path: Path):
    """The build used for waiting stories. A story that failed before is drafted afresh, following the reason."""
    def build(story_id: int) -> dict:
        import carousel
        reason = last_failure(db_path, story_id) if carousel_auto.failed_attempts(db_path, story_id) else None
        note = (f"The earlier build of this carousel failed: {reason}. Make a fresh draft that avoids this problem."
                if reason else None)
        return carousel.run_story(str(story_id), None, True, review_note=note)
    return build


def build_waiting(db_path: Path, now: datetime, webhook: str, build=None, notify=None) -> list[str]:
    """Every official story waiting for a carousel (the cloud marked it "being made by the carousel bot"), best first,
    within the caps. A failed story gets one more try. Stops at Claude's usage limit."""
    stories = carousel_auto.pending_stories(db_path, now)
    if not stories:
        return []
    return carousel_auto.after_alerts(db_path, stories, now, webhook, build or default_build(db_path),
                                      notify=notify or carousel_auto.alert.send_to_slack,
                                      max_failed=BOT_MAX_ATTEMPTS)


def rejected_to_rebuild(carousels_dir: Path) -> list[tuple[Path, dict]]:
    """Carousels a person rejected with a note that the bot has not rebuilt yet (once per rejection)."""
    found = []
    if not carousels_dir.exists():
        return found
    for folder in sorted(p for p in carousels_dir.iterdir() if p.is_dir()):
        status = carousel_status.read_status(folder)
        marker = status.get("rejected_at") or status.get("reason")
        if (status["status"] == "rejected" and status.get("rebuild_requested") and (status.get("reason") or "").strip()
                and status.get("bot_rebuilt_for") != marker):
            found.append((folder, status))
    return found


def rebuild_rejected(db_path: Path, carousels_dir: Path, now: datetime, webhook: str, build=None,
                     notify=None) -> list[str]:
    """Rebuilds each rejected carousel with its rejection note as the review note: a fresh draft, the same official
    page, and every check again. On success it waits for approval again and Slack says so."""
    if build is None:
        import carousel
        build = carousel.run_story
    notify = notify or carousel_auto.alert.send_to_slack
    outcomes = []
    for folder, status in rejected_to_rebuild(carousels_dir)[:MAX_REBUILDS_PER_RUN]:
        marker = status.get("rejected_at") or status.get("reason")
        note = status["reason"].strip()
        title = status.get("build", {}).get("title") or folder.name
        story_id = story_id_for_folder(db_path, folder.name)
        if story_id is None:
            carousel_status.update_fields(folder, bot_rebuilt_for=marker,
                                          bot_rebuild_problem="the story for this carousel was not found")
            outcomes.append(f"{folder.name}: not rebuilt (story not found)")
            continue
        try:
            result = build(str(story_id), status.get("build", {}).get("official_url"), True, review_note=note)
        except classify.ClaudeUsageLimit as exc:
            log.warning("Carousel bot: rebuild of %s paused: %s", folder.name, exc)
            outcomes.append(f"{folder.name}: {carousel_auto.USAGE_LIMIT_OUTCOME}")
            break
        except Exception as exc:  # the carousel stays rejected; the reason is shown and logged
            reason = str(exc) or type(exc).__name__
            carousel_status.update_fields(folder, bot_rebuilt_for=marker, bot_rebuild_problem=reason[:300])
            activity.log_event("carousel", "failed", f"{title}: rebuild after the review note did not pass: {reason}",
                               now=now)
            carousel_auto._notify_safely(notify, carousel_auto.failed_message(title, reason), webhook)
            outcomes.append(f"{folder.name}: rebuild failed ({reason[:120]})")
            continue
        built = carousel_status.read_status(folder).get("build", {})
        new_status = "waiting_for_david" if carousel_status.passes_review(built) else "draft"
        carousel_status.set_status(folder, new_status, bot_rebuilt_for=marker, rebuilt_after_note=note)
        activity.log_event("carousel", "rebuilt", f"{title}: rebuilt by the carousel bot after the review note "
                                                  f"({folder.name})", now=now)
        if new_status == "waiting_for_david":
            carousel_auto._notify_safely(notify, carousel_auto.ready_message(f"{title} (rebuilt after your note)",
                                                                             result), webhook)
        outcomes.append(f"{folder.name}: rebuilt, {new_status}")
    return outcomes


# ---------- one run ----------

def webhook_or_none() -> str | None:
    try:
        return carousel_auto.alert.webhook_url()
    except RuntimeError:
        log.warning("Carousel bot: no Slack address in .env; carousels are still made, without Slack messages.")
        return None


def run_once(root: Path = ROOT, now: datetime | None = None, git=run_git, build=None, rebuild=None,
             safety=None, sync=None) -> dict:
    """One bot run. Every part can be replaced for tests (git, build, rebuild, safety, sync)."""
    import timing
    now = now or datetime.now(timezone.utc)
    clock = timing.Clock("carousel bot", echo=False)
    summary: dict = {"built": [], "rebuilt": [], "usage_limit": False, "push": "not tried"}
    import cloud_state
    if not cloud_state.cloud_is_on(root):
        log.info("Carousel bot: the cloud watcher is off (no state/CLOUD-ON), so the hourly watcher on this laptop "
                 "builds carousels itself. Nothing to do.")
        summary["push"] = "cloud off"
        return summary
    sync = sync or cloud_state
    with clock.step("git pull"):
        pulled = pull(git, root)
    with clock.step("state pull"):
        sync.pull("laptop", root)
    db_path = root / "data" / "seen.sqlite"
    url = webhook_or_none()
    notify = carousel_auto.alert.send_to_slack if url else (lambda text, webhook: None)
    with clock.step("rebuild rejected carousels"):
        summary["rebuilt"] = (rebuild or rebuild_rejected)(db_path, root / "output" / "carousels", now, url,
                                                          notify=notify)
    limit = any(carousel_auto.USAGE_LIMIT_OUTCOME in line for line in summary["rebuilt"])
    if not limit:
        with clock.step("build waiting carousels"):
            summary["built"] = (build or build_waiting)(db_path, now, url, notify=notify)
        limit = any(carousel_auto.USAGE_LIMIT_OUTCOME in line for line in summary["built"])
    summary["usage_limit"] = limit
    if limit:
        log.warning("Carousel bot: Claude's usage limit was reached. Nothing was counted as failed; the bot tries "
                    "again on its next hourly run.")
    worked = [line for line in summary["built"] + summary["rebuilt"] if "draft ready" in line or "rebuilt" in line]
    if worked:
        _refresh_pages(root)
    with clock.step("state push"):
        sync.push("laptop", root)
    with clock.step("public safety check"):
        problems = (safety or _safety)(root)
    if problems:
        summary["push"] = "not pushed: the safety check found " + "; ".join(problems[:3])
        log.error("Carousel bot: NOT pushed, the public safety check failed: %s", "; ".join(problems[:5]))
    elif not pulled:
        summary["push"] = "not pushed: git pull did not work, tried again next run"
    else:
        with clock.step("commit and push"):
            summary["push"] = commit_and_push(git, root)
    log.info("Carousel bot: built %s; rebuilt %s; %s. %s", summary["built"] or "nothing", summary["rebuilt"] or
             "nothing", summary["push"], clock.summary())
    return summary


def _refresh_pages(root: Path) -> None:
    """The download zips and Kint's dashboard, so a new carousel shows at once. A problem here never stops the bot."""
    try:
        import dashboard
        import downloads
        downloads.ensure_zips(root / "output" / "carousels", root / "output" / "samples")
        dashboard.write_dashboard()
    except Exception as exc:
        log.error("Carousel bot: the dashboard was not refreshed (%s)", type(exc).__name__)


def _safety(root: Path) -> list[str]:
    import public_safe
    try:
        return public_safe.scan(public_safe.files_git_would_commit(root), root)
    except RuntimeError as exc:
        return [str(exc)]


def setup_logging(path: Path = LOG_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(argv: list[str] | None = None) -> int:
    """Always returns 0, so the task never retries in a loop; every problem is in logs/carousel-bot.log."""
    from dotenv import load_dotenv
    setup_logging()
    load_dotenv(ROOT / ".env")
    if not acquire_lock():
        log.info("Carousel bot: the previous run is still going; this run is skipped.")
        return 0
    try:
        log.info("Carousel bot: run started.")
        run_once()
    except Exception as exc:  # logged, never raised: the next hourly run starts clean
        log.exception("Carousel bot: the run stopped with an error: %s", type(exc).__name__)
    finally:
        release_lock()
    return 0


if __name__ == "__main__":
    sys.exit(main())
