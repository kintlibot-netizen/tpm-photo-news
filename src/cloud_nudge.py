"""Laptop backup for the cloud watcher: if GitHub has skipped the hourly runs, start one.

`python src/run.py --nudge-cloud` calls nudge(). It never checks news, never builds a carousel, never sends Slack,
never prints a token or an environment value, and always exits 0. Every subprocess call has a timeout.

It asks GitHub (through the gh command line tool, already signed in on the laptop) for the last watch.yml runs.
If one is queued or running, or the newest started less than 90 minutes ago, it does nothing. Otherwise it starts one
run with `gh workflow run watch.yml` and writes a "cloud, nudged" row to the activity log.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import activity

log = logging.getLogger("watcher")

WORKFLOW = "watch.yml"
QUIET_MINUTES = 90  # a run this recent means the cloud is alive
TIMEOUT = 60  # seconds, for every subprocess call
GH_FALLBACK = r"C:\Program Files\GitHub CLI\gh.exe"
ACTIVE = {"queued", "in_progress", "waiting", "requested", "pending"}


def find_gh() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    return GH_FALLBACK if Path(GH_FALLBACK).exists() else None


def _run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd)


def repo_from_remote(cwd: Path | None = None) -> str | None:
    """owner/name from `git remote get-url origin` (an https or ssh GitHub address), None when it cannot be read."""
    try:
        result = _run(["git", "remote", "get-url", "origin"], cwd)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
        if url.startswith(prefix):
            name = url[len(prefix):]
            break
    else:
        host_at = url.find("@github.com/")  # https://user@github.com/owner/name
        if host_at < 0:
            return None
        name = url[host_at + len("@github.com/"):]
    name = name.removesuffix(".git").strip("/")
    return name if re.fullmatch(r"[\w.-]+/[\w.-]+", name) else None


def minutes_since(created_at: str, now: datetime) -> float | None:
    try:
        moment = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (now - moment).total_seconds() / 60


def decide(runs: list[dict], now: datetime) -> tuple[bool, float | None]:
    """(nudge?, minutes since the newest run). No nudge when a run is active or the newest one is recent."""
    if any(str(r.get("status", "")).lower() in ACTIVE for r in runs):
        return False, 0.0
    ages = [a for a in (minutes_since(r.get("createdAt", ""), now) for r in runs) if a is not None]
    if not ages:
        return True, None
    newest = min(ages)
    return newest >= QUIET_MINUTES, newest


def nudge(now: datetime | None = None, cwd: Path | None = None) -> str:
    """Starts the cloud watcher once when it has been quiet. Returns what happened, in one plain line."""
    now = now or datetime.now(timezone.utc)
    gh = find_gh()
    if gh is None:
        message = "Cloud backup: the gh tool is not installed, so nothing was done."
        log.info(message)
        return message
    try:
        auth = _run([gh, "auth", "status"], cwd)
    except (OSError, subprocess.SubprocessError):
        auth = None
    if auth is None or auth.returncode != 0:
        message = "Cloud backup: gh is not signed in, so nothing was done."
        log.info(message)
        return message
    repo = repo_from_remote(cwd)
    rflag = ["-R", repo] if repo else []
    try:
        listed = _run([gh, "run", "list", *rflag, "--workflow", WORKFLOW, "-L", "5", "--json", "status,createdAt"], cwd)
        runs = json.loads(listed.stdout) if listed.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        runs = None
    if not isinstance(runs, list):
        message = "Cloud backup: the run list could not be read, so nothing was done."
        log.info(message)
        return message
    start, age = decide(runs, now)
    if not start:
        message = "Cloud backup: the cloud watcher ran recently or is running, so nothing was done."
        log.info(message)
        return message
    try:
        started = _run([gh, "workflow", "run", WORKFLOW, *rflag], cwd)
    except (OSError, subprocess.SubprocessError):
        started = None
    if started is None or started.returncode != 0:
        message = "Cloud backup: the cloud run could not be started."
        log.info(message)
        return message
    quiet = f"{int(age)} minutes" if age is not None else "a long time"
    message = f"Nudged the cloud: no run for {quiet}"
    log.info(message)
    activity.log_event("cloud", "nudged", message, now=now)
    return message
