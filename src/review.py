"""Review and publish records for carousel folders. Posting itself is done by hand in Meta Business Suite.

python src/review.py --list
python src/review.py --approve <folder> --by "David"
python src/review.py --reject <folder> --reason "..."
python src/review.py --posted <folder> --account tpm-facebook|tpm-instagram|david-facebook --url <post url>

Nothing here posts anywhere. There is no Meta API code. Only the three accounts in config/accounts.yaml
can be logged, and David's personal Instagram is refused by name, in code, with a test.
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

import activity
import carousel_status
import dashboard
import downloads

ROOT = Path(__file__).resolve().parent.parent
CAROUSELS = ROOT / "output" / "carousels"
POST_LOG = ROOT / "output" / "post-log.csv"
ACCOUNTS_PATH = ROOT / "config" / "accounts.yaml"
LOG_COLUMNS = ["logged_at", "folder", "title", "account", "account_name", "url", "approved_by", "approved_at"]
PERSONAL_IG = re.compile(r"(?=.*\b(david|molnar|personal)\b)(?=.*\b(instagram|ig)\b)", re.I)


class ReviewError(ValueError):
    """A plain reason a review step is refused."""


def refuse_personal_instagram(name: str) -> None:
    """David's personal Instagram is never a valid account. Checked on every name, in code."""
    if PERSONAL_IG.search(name.replace("-", " ").replace("_", " ")):
        raise ReviewError(f"{name!r} looks like David's personal Instagram. That account is blocked and can't be used.")


def load_accounts(path: Path = ACCOUNTS_PATH) -> dict[str, dict]:
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    accounts = data.get("accounts") or {}
    for key, value in accounts.items():
        refuse_personal_instagram(key)
        refuse_personal_instagram(str(value.get("label", "")))
    return accounts


def resolve_folder(arg: str) -> Path:
    path = Path(arg)
    if not path.is_absolute() and not path.exists():
        path = CAROUSELS / arg
    if not (path / "captions.txt").exists():
        raise ReviewError(f"{arg!r} is not a carousel folder (no captions.txt).")
    return path


def split_captions(text: str) -> dict[str, str]:
    """The David and TPM captions from captions.txt, keyed 'david' and 'tpm'."""
    parts = {}
    current = None
    for line in text.splitlines():
        if line.startswith("DAVID MOLNAR FACEBOOK"):
            current = "david"
            continue
        if line.startswith("TPM FACEBOOK AND INSTAGRAM"):
            current = "tpm"
            continue
        if current and line.strip():
            parts[current] = line.strip()
    return parts


def refuse_sample(folder: Path, status: dict) -> None:
    """Sample drafts are for checking the layout only. They are never approved or logged as posted."""
    title = str(status.get("build", {}).get("title", ""))
    if folder.name.endswith("-sample") or title.upper().startswith("SAMPLE:"):
        raise ReviewError(f"{folder.name!r} is a sample folder. Samples can't be approved or logged as posted.")


def refresh_dashboard(folder: Path | None = None) -> None:
    """Rebuilds the download zips and the dashboard after a review action. A failure here is logged and never undoes
    the action."""
    if folder is not None:
        downloads.refresh_after_review(folder)
    try:
        dashboard.write_dashboard()
    except Exception as exc:
        logging.getLogger("review").error("Dashboard was not rebuilt: %s", type(exc).__name__)


def list_folders() -> list[str]:
    if not CAROUSELS.exists():
        return ["No carousel folders yet."]
    rows = []
    for folder in sorted(p for p in CAROUSELS.iterdir() if p.is_dir()):
        status = carousel_status.read_status(folder)
        title = status.get("build", {}).get("title", "")
        label = carousel_status.STATUS_LABELS.get(status["status"], status["status"])
        rows.append(f"{folder.name}  [{label}]  {title}")
    return rows or ["No carousel folders yet."]


def approve(folder: Path, by: str, now: datetime) -> Path:
    if not by or not by.strip():
        raise ReviewError("--approve needs --by with the name of the person approving.")
    status = carousel_status.read_status(folder)
    refuse_sample(folder, status)
    if status["status"] not in ("draft", "waiting_for_david", "approved"):
        raise ReviewError(f"this folder is {status['status']}; only a draft can be approved.")
    if status.get("build", {}).get("design_fail"):
        raise ReviewError("the design check failed for this draft, so it can't be approved. Rebuild it first.")
    ready = folder / "ready-to-post"
    if ready.exists():
        shutil.rmtree(ready)
    ready.mkdir(parents=True)
    for slide in sorted(folder.glob("[0-9][0-9].png")):
        shutil.copyfile(slide, ready / slide.name)
    captions = split_captions((folder / "captions.txt").read_text(encoding="utf-8"))
    accounts = load_accounts()
    files = {
        "tpm-facebook": ("tpm", "we"),
        "tpm-instagram": ("tpm", "we"),
        "david-facebook": ("david", "I"),
    }
    for account, (who, voice) in files.items():
        if account not in accounts or who not in captions:
            continue
        label = accounts[account].get("label", account)
        (ready / f"{account}.txt").write_text(
            f"Account: {label}\nVoice: {voice}\n\n{captions[who]}\n", encoding="utf-8")
    carousel_status.set_status(folder, "approved", approved_by=by.strip(),
                               approved_at=now.isoformat(timespec="seconds"))
    activity.log_event("review", "approved", f"{_title(status, folder)} ({folder.name})", who=by.strip(), now=now)
    refresh_dashboard(folder)
    return ready


def reject(folder: Path, reason: str, now: datetime, by: str = "") -> None:
    if not reason or not reason.strip():
        raise ReviewError("--reject needs --reason.")
    status = carousel_status.read_status(folder)
    carousel_status.set_status(folder, "rejected", reason=reason.strip(), rejected_at=now.isoformat(timespec="seconds"))
    activity.log_event("review", "rejected", f"{_title(status, folder)} ({folder.name}). Reason: {reason.strip()}",
                       who=by.strip(), now=now)
    refresh_dashboard(folder)


def _title(status: dict, folder: Path) -> str:
    return str(status.get("build", {}).get("title") or folder.name)


def log_post(folder: Path, account: str, url: str, now: datetime, log_path: Path | None = None,
             by: str = "") -> None:
    log_path = log_path or POST_LOG  # read at call time, so a changed POST_LOG is always used
    refuse_personal_instagram(account)
    accounts = load_accounts()
    if account not in accounts:
        raise ReviewError(f"{account!r} is not one of the accounts in config/accounts.yaml: {', '.join(accounts)}.")
    if not url.lower().startswith("https://"):
        raise ReviewError("--url must be the full https link to the post.")
    status = carousel_status.read_status(folder)
    refuse_sample(folder, status)
    if status["status"] not in ("approved", "posted"):
        raise ReviewError("only an approved carousel can be logged as posted.")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with open(log_path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "logged_at": now.isoformat(timespec="seconds"),
            "folder": folder.name,
            "title": status.get("build", {}).get("title", ""),
            "account": account,
            "account_name": accounts[account].get("label", account),
            "url": url,
            "approved_by": status.get("approved_by", ""),
            "approved_at": status.get("approved_at", ""),
        })
    carousel_status.set_status(folder, "posted", posts=status.get("posts", []) + [
        {"account": account, "url": url, "at": now.isoformat(timespec="seconds")}])
    activity.log_event("review", "posted", f"{_title(status, folder)} ({folder.name}) posted by hand to "
                       f"{accounts[account].get('label', account)} ({account}): {url}", who=by.strip(), now=now)
    refresh_dashboard(folder)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review and log carousels. Posts nothing.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--approve", metavar="FOLDER")
    group.add_argument("--reject", metavar="FOLDER")
    group.add_argument("--posted", metavar="FOLDER")
    parser.add_argument("--by", help="who approved (needed with --approve; optional with --reject and --posted)")
    parser.add_argument("--reason", help="why it is rejected (with --reject)")
    parser.add_argument("--account", help="tpm-facebook, tpm-instagram or david-facebook (with --posted)")
    parser.add_argument("--url", help="the link to the post (with --posted)")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if args.list:
            print("\n".join(list_folders()))
        elif args.approve:
            ready = approve(resolve_folder(args.approve), args.by or "", now)
            print(f"Approved by {args.by}. Ready to post in: {ready}")
            print("Post it by hand in Meta Business Suite, then log it with --posted.")
        elif args.reject:
            reject(resolve_folder(args.reject), args.reason or "", now, by=args.by or "")
            print("Rejected.")
        elif args.posted:
            if not args.account or not args.url:
                raise ReviewError("--posted needs --account and --url.")
            log_post(resolve_folder(args.posted), args.account, args.url, now, by=args.by or "")
            print(f"Logged in {POST_LOG}.")
    except ReviewError as exc:
        print(f"Not done: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
