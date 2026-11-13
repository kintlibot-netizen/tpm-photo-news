"""When the hourly Windows task "TPM Photo News Watcher" runs next, for the dashboard's "Next check at".

Read with PowerShell's Get-ScheduledTaskInfo. Any problem (not Windows, no task, PowerShell slow or missing) gives None,
and the dashboard then estimates the next check from the last run (one hour later). Nothing is changed in the task.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone

TASK_NAME = "TPM Photo News Watcher"
COMMAND = (
    f"$i = Get-ScheduledTaskInfo -TaskName '{TASK_NAME}' -ErrorAction Stop; "
    "if ($i.NextRunTime) { $i.NextRunTime.ToUniversalTime().ToString('o') }"
)


def parse_next_run(text: str) -> datetime | None:
    """The first ISO time in PowerShell's answer, in UTC. None for an empty or unreadable answer."""
    for line in (text or "").splitlines():
        value = line.strip()
        if not value:
            continue
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        if "." in value:  # PowerShell gives 7 decimal places; older Pythons read at most 6
            head, _, tail = value.partition(".")
            count = len(tail) - len(tail.lstrip("0123456789"))
            digits, zone = tail[:count], tail[count:]
            value = f"{head}.{digits[:6].ljust(6, '0')}{zone}"
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            continue
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return None


def next_run_time(timeout: float = 15) -> datetime | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", COMMAND],
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return parse_next_run(done.stdout)
