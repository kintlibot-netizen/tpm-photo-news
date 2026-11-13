"""What the watcher remembers between runs, kept in the small committed folder state/ so the cloud (GitHub Actions)
and Kint's laptop share it.

The design is "each side writes only its own files", so a git pull never has a merge conflict:

  state/seen.sqlite           CLOUD writes it. Stories, alerts sent, run history, health messages.
  state/activity-cloud.csv    CLOUD writes it. The cloud's rows of the activity log.
  state/activity-laptop.csv   LAPTOP writes it. The laptop's rows (carousel builds, reviews, downloads).
  state/laptop-builds.csv     LAPTOP writes it. The carousel builds made on the laptop.
  state/post-log.csv          LAPTOP writes it. Every post Kint logged by hand.
  state/carousels/<folder>/   LAPTOP writes it. Each real carousel: slides, captions, sources, fact check, status
                              (approvals), the download zip. Never samples, never the candidate image folders.

Only the cloud sends Slack alerts (run.py refuses a live check on the laptop while state/CLOUD-ON exists), so the
same alert is never sent twice. The laptop builds the carousels (the fact check and the official image check need
Claude, which runs only on the laptop) and holds the approvals.

  pull --side cloud|laptop   state/ -> data/ and output/ (run it after git pull)
  push --side cloud|laptop   data/ and output/ -> this side's files in state/ (then git add state, commit, push)
  push --side laptop --first-time   also writes state/seen.sqlite once, to start the cloud from the laptop's memory

Nothing written to state/ holds a secret or a path from this PC: carousel folders are stored by name only and every
text is passed through activity.scrub(). scripts/check_public_safe.py checks it again before anything is committed.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
from pathlib import Path

import activity

ROOT = Path(__file__).resolve().parent.parent
SIDES = ("cloud", "laptop")
CLOUD_FLAG = "CLOUD-ON"
BUILD_COLUMNS = ["story_id", "built_at", "status", "folder", "message"]
KEPT_BUILDS = ("ok", "failed")  # "needs_kint" rows are the cloud's and live in state/seen.sqlite
CAROUSEL_SKIP_DIRS = {"candidates", "images", ".work"}
CAROUSEL_SKIP_SUFFIXES = (".tmp",)


def paths(root: Path | None = None) -> dict[str, Path]:
    root = Path(root) if root is not None else ROOT
    state = root / "state"
    return {
        "root": root, "state": state,
        "state_db": state / "seen.sqlite", "local_db": root / "data" / "seen.sqlite",
        "local_activity": root / "data" / "activity-log.csv",
        "state_builds": state / "laptop-builds.csv",
        "state_posts": state / "post-log.csv", "local_posts": root / "output" / "post-log.csv",
        "state_carousels": state / "carousels", "local_carousels": root / "output" / "carousels",
        "flag": state / CLOUD_FLAG,
    }


def activity_file(state: Path, side: str) -> Path:
    return state / f"activity-{side}.csv"


def cloud_is_on(root: Path | None = None) -> bool:
    """True once the cloud watcher is switched on (state/CLOUD-ON is committed)."""
    return paths(root)["flag"].exists()


# ---------- the activity log ----------

def _read_rows(path: Path) -> list[tuple]:
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return [tuple((row.get(c) or "") for c in activity.COLUMNS) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _write_rows(path: Path, rows: list[tuple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(activity.COLUMNS)
        for row in rows:
            writer.writerow([activity.scrub(cell) if i else cell for i, cell in enumerate(row)])
    temp.replace(path)


def _sorted_unique(rows) -> list[tuple]:
    seen, out = set(), []
    for row in rows:
        if row not in seen:
            seen.add(row)
            out.append(row)
    return sorted(out, key=lambda r: (activity.parse_time(r[0]) is None, str(activity.parse_time(r[0]) or ""), r))


def merge_activity(p: dict) -> None:
    """data/activity-log.csv becomes every row of both sides plus any local row not yet pushed."""
    rows = _read_rows(p["local_activity"])
    for side in SIDES:
        rows += _read_rows(activity_file(p["state"], side))
    _write_rows(p["local_activity"], _sorted_unique(rows))


def split_activity(p: dict, side: str) -> None:
    """This side's file becomes every local row that is not already in the other side's file."""
    other = set(_read_rows(activity_file(p["state"], "laptop" if side == "cloud" else "cloud")))
    mine = [row for row in _read_rows(p["local_activity"]) if row not in other]
    _write_rows(activity_file(p["state"], side), _sorted_unique(mine))


# ---------- carousel builds made on the laptop ----------

def _build_rows(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    db = sqlite3.connect(db_path)
    try:
        try:
            rows = db.execute("SELECT story_id, built_at, status, folder, message FROM carousel_builds").fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        db.close()
    return [clean_build(dict(zip(BUILD_COLUMNS, row))) for row in rows if row[2] in KEPT_BUILDS]


def clean_build(row: dict) -> dict:
    """A build row with the folder kept by name only and no secret or local path in the message."""
    folder = row.get("folder")
    name = Path(str(folder).replace("\\", "/")).name if folder else ""
    return {"story_id": int(row["story_id"]), "built_at": str(row["built_at"]), "status": str(row["status"]),
            "folder": name, "message": activity.scrub(row.get("message") or "")}


def read_builds_csv(path: Path) -> list[dict]:
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return [clean_build(row) for row in csv.DictReader(handle) if row.get("status") in KEPT_BUILDS]
    except (OSError, csv.Error, UnicodeDecodeError, ValueError, KeyError):
        return []


def write_builds_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    unique = {(r["story_id"], r["built_at"], r["status"]): r for r in rows}
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BUILD_COLUMNS)
        writer.writeheader()
        for key in sorted(unique, key=lambda k: (k[1], k[0], k[2])):
            writer.writerow(unique[key])


def insert_builds(db_path: Path, rows: list[dict]) -> int:
    """Adds the build rows the database does not have yet. Returns how many were added."""
    if not rows or not db_path.exists():
        return 0
    db = sqlite3.connect(db_path)
    added = 0
    try:
        db.execute("CREATE TABLE IF NOT EXISTS carousel_builds (id INTEGER PRIMARY KEY AUTOINCREMENT, story_id INTEGER, "
                   "built_at TEXT, status TEXT, folder TEXT, message TEXT)")
        with db:
            for row in rows:
                found = db.execute("SELECT 1 FROM carousel_builds WHERE story_id=? AND built_at=? AND status=?",
                                   (row["story_id"], row["built_at"], row["status"])).fetchone()
                if found is None:
                    db.execute("INSERT INTO carousel_builds(story_id,built_at,status,folder,message) VALUES(?,?,?,?,?)",
                               (row["story_id"], row["built_at"], row["status"], row["folder"] or None,
                                row["message"]))
                    added += 1
    finally:
        db.close()
    return added


# ---------- the database ----------

def copy_db(source: Path, target: Path) -> None:
    """A consistent copy (sqlite backup), never a half-written file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    temp.unlink(missing_ok=True)
    src = sqlite3.connect(source)
    dst = sqlite3.connect(temp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    temp.replace(target)


def clean_db(path: Path) -> None:
    """Before state/seen.sqlite is committed: carousel folders by name only, no local path or secret in a message."""
    db = sqlite3.connect(path)
    try:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "carousel_builds" in tables:
            rows = db.execute("SELECT id, folder, message FROM carousel_builds").fetchall()
            with db:
                for row_id, folder, message in rows:
                    name = Path(str(folder).replace("\\", "/")).name if folder else None
                    db.execute("UPDATE carousel_builds SET folder=?, message=? WHERE id=?",
                               (name, activity.scrub(message or ""), row_id))
        db.execute("VACUUM")
    finally:
        db.close()


# ---------- carousel folders ----------

def _carousel_files(folder: Path):
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if not path.is_file() or any(part in CAROUSEL_SKIP_DIRS for part in relative.parts[:-1]):
            continue
        if path.suffix.lower() in CAROUSEL_SKIP_SUFFIXES or path.name == "preview.png":
            continue
        yield path, relative


def _is_sample(folder: Path) -> bool:
    import downloads
    return downloads.is_sample(folder)


def copy_carousels(source: Path, target: Path, mirror: bool) -> int:
    """Copies every real carousel folder's files (no samples, no candidate images). mirror=True also removes folders
    and files from the target that the source no longer has (used for state/, never for the laptop's own folders).
    Returns how many files were written."""
    if not source.exists():
        return 0
    written = 0
    names = []
    for folder in sorted(p for p in source.iterdir() if p.is_dir()):
        if not (folder / "captions.txt").exists() or _is_sample(folder):
            continue
        names.append(folder.name)
        keep = set()
        for path, relative in _carousel_files(folder):
            out = target / folder.name / relative
            keep.add(relative.as_posix())
            if out.exists() and out.stat().st_size == path.stat().st_size and out.read_bytes() == path.read_bytes():
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
            written += 1
        if mirror and (target / folder.name).exists():
            for old, relative in list(_carousel_files(target / folder.name)):
                if relative.as_posix() not in keep:
                    old.unlink()
    if mirror and target.exists():
        for old in target.iterdir():
            if old.is_dir() and old.name not in names:
                shutil.rmtree(old)
    return written


# ---------- pull and push ----------

def pull(side: str, root: Path | None = None) -> list[str]:
    """state/ -> the working folders. Run after git pull, before the watcher or the review server."""
    p = paths(root)
    notes = []
    local_builds = _build_rows(p["local_db"])  # laptop builds not pushed yet are kept, never lost
    if p["state_db"].exists():
        copy_db(p["state_db"], p["local_db"])
        notes.append("seen.sqlite: from state")
    added = insert_builds(p["local_db"], read_builds_csv(p["state_builds"]) + local_builds)
    if added:
        notes.append(f"carousel builds added: {added}")
    merge_activity(p)
    if p["state_posts"].exists():
        p["local_posts"].parent.mkdir(parents=True, exist_ok=True)
        if side == "cloud" or not p["local_posts"].exists() or \
                p["state_posts"].stat().st_size > p["local_posts"].stat().st_size:
            shutil.copyfile(p["state_posts"], p["local_posts"])
    written = copy_carousels(p["state_carousels"], p["local_carousels"], mirror=(side == "cloud"))
    notes.append(f"carousel files updated: {written}")
    return notes


def push(side: str, root: Path | None = None, first_time: bool = False) -> list[str]:
    """The working folders -> this side's files in state/. The caller then commits state/."""
    p = paths(root)
    notes = []
    p["state"].mkdir(parents=True, exist_ok=True)
    if side == "cloud" or first_time:
        if p["local_db"].exists():
            copy_db(p["local_db"], p["state_db"])
            clean_db(p["state_db"])
            notes.append("seen.sqlite: saved")
    split_activity(p, side)
    if side == "laptop":
        write_builds_csv(p["state_builds"], read_builds_csv(p["state_builds"]) + _build_rows(p["local_db"]))
        if p["local_posts"].exists():
            shutil.copyfile(p["local_posts"], p["state_posts"])
        written = copy_carousels(p["local_carousels"], p["state_carousels"], mirror=True)
        notes.append(f"carousel files saved: {written}")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Share the watcher's memory through the committed state/ folder.")
    parser.add_argument("action", choices=["pull", "push", "status"])
    parser.add_argument("--side", choices=SIDES, required=False, default="laptop")
    parser.add_argument("--first-time", action="store_true",
                        help="laptop only: also save seen.sqlite, to start the cloud from the laptop's memory")
    args = parser.parse_args(argv)
    if args.action == "status":
        print("Cloud watcher: " + ("ON (the laptop sends no Slack alerts)" if cloud_is_on() else "off"))
        return 0
    notes = pull(args.side) if args.action == "pull" else push(args.side, first_time=args.first_time)
    for note in notes:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
