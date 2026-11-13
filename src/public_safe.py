"""Checks that nothing secret or personal is in the files git would commit. The repository is public.

It looks at every file git would commit (tracked files, and new files that .gitignore does not exclude), including
binary files (state/seen.sqlite) and the text files inside zips, for:
  - a real Slack webhook address or a Slack, GitHub or API token
  - any value from .env, and the Slack webhook in the environment
  - a Windows or home folder path, such as C:\\Users\\<name>\\ or /Users/<name>/
  - the git author's own email address
  - a .env file itself
It prints each problem (never the secret itself) and fails when it finds one.

python scripts/check_public_safe.py
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_IN_ZIP = (".txt", ".md", ".html", ".csv", ".json")
MAX_BYTES = 60 * 1024 * 1024

PATTERNS = [
    # The real format (T..., B..., a 24 character token). The made-up addresses in the tests are shorter on purpose.
    ("a Slack webhook address", re.compile(rb"hooks\.slack(?:-gov)?\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/"
                                           rb"[A-Za-z0-9]{22,}")),
    ("a Slack token", re.compile(rb"\bxox[abprs]-[0-9]{6,}-[A-Za-z0-9-]{10,}")),
    ("a GitHub token", re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}")),
    ("an API key", re.compile(rb"\bsk-(?:ant-)?[A-Za-z0-9_-]{30,}")),
    ("a folder path from a PC", re.compile(rb"\b[A-Za-z]:(?:\\\\|\\|/)(?:Users|Documents and Settings)(?:\\\\|\\|/)"
                                           rb"[A-Za-z0-9._-]+")),
    ("a folder path from a PC", re.compile(rb"(?<![\w.])/(?:Users|home)/[A-Za-z0-9._-]+/")),
]


def env_values(root: Path) -> list[bytes]:
    """The values in .env (8 characters or more) and the webhook in the environment. Only compared, never printed."""
    values = []
    try:
        for line in (root / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if len(value) >= 8 and "REPLACE" not in value:
                    values.append(value.encode())
    except OSError:
        pass
    webhook = os.environ.get("SLACK_" + "WEBHOOK_URL", "").strip()
    if len(webhook) >= 8:
        values.append(webhook.encode())
    return values


def personal_values(root: Path) -> list[bytes]:
    """The git author's email (read from git config, so it is never written in this file)."""
    try:
        result = subprocess.run(["git", "config", "user.email"], cwd=root, capture_output=True, text=True,
                                timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    email = result.stdout.strip()
    if not email or "noreply" in email or "github-actions" in email:
        return []
    return [email.encode()]


def files_git_would_commit(root: Path) -> list[Path]:
    """Tracked files plus new files .gitignore does not exclude. Raises RuntimeError when git can't answer."""
    try:
        result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                cwd=root, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git could not list the files ({type(exc).__name__})") from exc
    if result.returncode != 0:
        raise RuntimeError("git could not list the files. Run this inside the repository.")
    names = [n for n in result.stdout.decode("utf-8", "replace").split("\0") if n]
    return [root / n for n in names if (root / n).is_file()]


def _blobs(path: Path):
    """(name, bytes) of the file, and of each text file inside it when it is a zip."""
    data = path.read_bytes()[:MAX_BYTES]
    yield path.name, data
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for item in archive.namelist():
                    if item.lower().endswith(TEXT_IN_ZIP):
                        yield f"{path.name}/{item}", archive.read(item)
        except zipfile.BadZipFile:
            pass


def scan(files: list[Path], root: Path, extra: list[bytes] | None = None) -> list[str]:
    """Every problem, as "<file>: contains <what>". Empty when the files are safe to make public."""
    problems = []
    secrets = env_values(root) + personal_values(root) + list(extra or [])
    for path in files:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.name
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            problems.append(f"{relative}: is a .env file and must never be committed")
            continue
        try:
            blobs = list(_blobs(path))
        except OSError:
            continue
        for name, data in blobs:
            where = relative if name == path.name else f"{relative} ({name.split('/', 1)[1]})"
            for what, pattern in PATTERNS:
                if pattern.search(data):
                    problems.append(f"{where}: contains {what}")
            for value in secrets:
                if value in data:
                    problems.append(f"{where}: contains a private value (.env or personal)")
    return sorted(set(problems))


def main(argv: list[str] | None = None) -> int:
    root = ROOT
    try:
        files = files_git_would_commit(root)
    except RuntimeError as exc:
        print(f"Not checked: {exc}")
        return 2
    problems = scan(files, root)
    if problems:
        print(f"NOT SAFE to make public. {len(problems)} problem(s):")
        for line in problems:
            print(f"  {line}")
        print("Remove these, or add the file to .gitignore, then check again.")
        return 1
    print(f"Safe: {len(files)} files checked, nothing secret or personal found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
