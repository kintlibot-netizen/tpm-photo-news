"""The laptop's git and publishing helpers for a real carousel build (src/plan_build.py publish and sync_first).

Kept from the old carousel bot, which was removed on Nov 24: git pull, commit state/ only and push, the Slack address
(never printed), the dashboard refresh and the public safety check. Nothing here builds a carousel or posts anything.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import activity

ROOT = Path(__file__).resolve().parent.parent
COMMIT_MESSAGE = "Laptop: new carousels"
log = logging.getLogger("watcher")


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
        log.error("Laptop: git pull did not work (%s). Building from the local state; the push waits.", output)
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
        return "committed; the push waits (git pull did not work)"
    ok, output = git(["push"], root)
    return "committed and pushed" if ok else f"committed; the push did not work ({output})"


def webhook_or_none() -> str | None:
    import alert
    try:
        return alert.webhook_url()
    except RuntimeError:
        log.warning("Laptop: no Slack address in .env; the carousel is saved without a Slack message.")
        return None


def refresh_pages(root: Path) -> None:
    """The download zips and Kint's dashboard, so a new carousel shows at once. A problem here never stops a build."""
    try:
        import dashboard
        import downloads
        downloads.ensure_zips(root / "output" / "carousels")
        dashboard.write_dashboard()
    except Exception as exc:
        log.error("Laptop: the dashboard was not refreshed (%s)", type(exc).__name__)


def safety_problems(root: Path) -> list[str]:
    import public_safe
    try:
        return public_safe.scan(public_safe.files_git_would_commit(root), root)
    except RuntimeError as exc:
        return [str(exc)]
