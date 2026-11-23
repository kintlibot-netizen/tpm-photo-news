"""Export for David: a read only copy of the dashboard that is a fully static website. It opens from a web link on any
computer or phone (upload the folder to any web host as is), or by double-clicking index.html after unzipping. No
install, no server, no internet needed to view it.

Builds output/share/TPM-News-Dashboard-<date>/ and output/share/TPM-News-Dashboard-<date>.zip, and refreshes
output/share/latest/ with the same contents (the folder to upload):
  index.html                  Kint's dashboard, rendered from the same template with read_only=True: the same look,
                              sidebar, pages and sections, at the root, relative paths only, all CSS, JS and fonts
                              inline, the note at the top ("Read only copy. To approve a carousel, tell Kint."), and
                              no approve, reject, review, export or command copy buttons, no commands, no paths
  READ ME FIRST.txt           how to open it or put it on the web
  carousels/<folder>/view/01.jpg  small previews the page shows, so it loads fast on a phone
  carousels/<folder>/01.png   the full 1080 x 1440 slides, for the single slide downloads
  carousels/<folder>/<zip>    the same download zip the dashboard offers (full slides, captions, sources)
  carousels/TPM-approved-carousels.zip   every approved carousel in one zip, when any is approved

The pack stays under 100 MB: samples and rejected carousels are never included, and when the slides would go over the
limit the per carousel zips are left out first, then the oldest carousels. Before the pack is kept, every text file in
it (and every text file inside its zips) is scanned for the Slack webhook, the .env values, review commands and file
paths from this PC. If anything is found, the pack is deleted and the export fails with the reason.
The export and its size are written to the activity log.

python scripts\\export_share_pack.py     (or double-click "Export for David.bat", or the button on the dashboard)
"""
from __future__ import annotations

import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import activity
import dashboard
import downloads
import previews

LIMIT_MB = 100
PAGE_ALLOWANCE = 6 * 1024 * 1024  # room kept for index.html (fonts included) and the previews inside the limit
TEXT_SUFFIXES = (".html", ".txt", ".md", ".csv", ".json")
LATEST = "latest"
README = """TPM Photo News, read only copy for David

To look at it:
1. If you got a web link, just open it. It works on a computer or a phone.
2. If you got a zip, unzip it and double-click index.html. It opens in your web browser. No install needed.
3. Start with the "Start here" page.

Read only copy. To approve a carousel, tell Kint.
Nothing is ever posted automatically. Kint posts by hand in Meta Business Suite after you approve.

To put it on the web (Kint): upload everything in this folder, as it is, to any web host. index.html must stay at
the top level. Nothing else is needed: no server code, no database.

Made on {made} (Asia/Manila).
"""


class ExportError(RuntimeError):
    """The export could not be made safely. Nothing is left behind."""


def pack_name(now: datetime) -> str:
    return f"TPM-News-Dashboard-{now.astimezone(activity.MANILA):%Y-%m-%d}"


def env_values(root: Path) -> list[str]:
    """The values in .env and the Slack webhook from the environment: read only to check that none of them is in the
    pack. They are never written anywhere."""
    values = []
    try:
        for line in (root / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if len(value) >= 8:
                    values.append(value)
    except OSError:
        pass
    webhook = os.environ.get("SLACK_" + "WEBHOOK_URL", "")
    if len(webhook) >= 8:
        values.append(webhook)
    return values


def forbidden_patterns(root: Path) -> list[tuple[str, re.Pattern]]:
    """(what, pattern) that must never be in the pack."""
    home = str(Path.home())
    checks = [
        ("a Slack webhook address", re.compile(r"hooks\.slack(?:-gov)?\.com", re.I)),
        ("a Slack token", re.compile(r"\bxox[a-z]-", re.I)),
        ("a path from this PC", re.compile(r"\b[A-Za-z]:\\\\?(?:Users|Documents and Settings)\\", re.I)),
        ("a file address from this PC", re.compile(r"file:///", re.I)),
        ("a review command", re.compile(r"review\.py|--approve\b|--posted\b|data-action=\"", re.I)),
        ("the project folder", re.compile(re.escape(str(root)), re.I)),
        ("the project folder", re.compile(re.escape(str(root).replace("\\", "/")), re.I)),
        ("the home folder", re.compile(re.escape(home), re.I)),
    ]
    checks += [("a value from .env", re.compile(re.escape(value))) for value in env_values(root)]
    return checks


def _texts(path: Path):
    """(name, text) of every text file in the pack, including the text files inside its zips."""
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        relative = file.relative_to(path).as_posix()
        if file.suffix.lower() in TEXT_SUFFIXES:
            yield relative, file.read_text(encoding="utf-8", errors="replace")
        elif file.suffix.lower() == ".zip":
            with zipfile.ZipFile(file) as archive:
                for item in archive.namelist():
                    if item.lower().endswith(TEXT_SUFFIXES):
                        yield f"{relative}/{item}", archive.read(item).decode("utf-8", errors="replace")


def scan_pack(path: Path, root: Path) -> list[str]:
    """Every problem found in the pack: a secret, a path from this PC or a review command. Empty when it is clean."""
    problems = []
    checks = forbidden_patterns(root)
    for name, text in _texts(path):
        for what, pattern in checks:
            if pattern.search(text):
                problems.append(f"{name} contains {what}")
        if name.endswith(".html"):
            for what, pattern in PAGE_ONLY_CHECKS:
                if pattern.search(text):
                    problems.append(f"{name} contains {what}")
    return problems


# The page David sees must hold no command and no control: checked on every .html file of the pack.
PAGE_ONLY_CHECKS = [
    ("PowerShell wording", re.compile(r"powershell", re.I)),
    ("a command copy button", re.compile(r'data-kind="command"|data-base="|id="export-david"|id="reviewer"')),
    ("a command", re.compile(r"python\.exe|\.venv\\|src\\[a-z_]+\.py|scripts\\[a-z_]+\.py|\.bat\b", re.I)),
]


def _keep(card: dict) -> bool:
    """David's copy shows every carousel that has slides: real ones, rejected ones (with the reason), previews and
    layout samples, each with its plain status chip."""
    return bool(card["slides"])


def plan_pack(cards: list[dict], limit_bytes: int, approved_bytes: int) -> tuple[list[dict], list[str], bool]:
    """(cards to include, with "zip_data" or None each; notes on what was left out; include the approved zip)."""
    budget = limit_bytes - PAGE_ALLOWANCE
    used = 0
    chosen, notes = [], []
    for card in cards:  # newest first, so the oldest are the ones left out when the limit is reached
        folder = card["folder"]
        slide_bytes = sum((folder / name).stat().st_size for name in card["slides"])
        zip_data = downloads.zip_bytes(folder)
        if used + slide_bytes + len(zip_data) <= budget:
            used += slide_bytes + len(zip_data)
            chosen.append(dict(card, zip_data=zip_data))
        elif used + slide_bytes <= budget:
            used += slide_bytes
            chosen.append(dict(card, zip_data=None))
            notes.append(f"{card['name']}: zip left out to stay under {limit_bytes // (1024 * 1024)} MB")
        else:
            notes.append(f"{card['name']}: left out to stay under {limit_bytes // (1024 * 1024)} MB")
    with_approved = approved_bytes > 0 and used + approved_bytes <= budget
    if approved_bytes > 0 and not with_approved:
        notes.append("the all approved carousels zip was left out to stay under the size limit")
    return chosen, notes, with_approved


def export_pack(now: datetime | None = None, root: Path | None = None, out_root: Path | None = None,
                limit_mb: int = LIMIT_MB, log_made: bool = True) -> dict:
    """Builds the share pack and its zip. Returns {"folder", "zip", "size_mb", "carousels", "notes"}.
    Raises ExportError (and removes the pack) when it would hold a secret or a path from this PC."""
    now = now or datetime.now(timezone.utc)
    root = Path(root) if root is not None else dashboard.ROOT
    out_root = Path(out_root) if out_root is not None else root / "output" / "share"
    carousels_dir = root / "output" / "carousels"
    name = pack_name(now)
    folder = out_root / name
    zip_path = out_root / f"{name}.zip"
    if folder.exists():
        shutil.rmtree(folder)
    zip_path.unlink(missing_ok=True)
    folder.mkdir(parents=True)
    try:
        previews_dir = root / "output" / "plan-previews"
        found = dashboard.read_carousels(carousels_dir, root / "output" / "samples", previews_dir)
        all_cards = [c for c in found if _keep(c)]
        left_out = len(found) - len(all_cards)
        approved_data, approved_count = downloads.approved_zip_bytes(carousels_dir)
        chosen, notes, with_approved = plan_pack(all_cards, limit_mb * 1024 * 1024,
                                                 len(approved_data) if approved_count else 0)
        keep_names = {c["name"]: c for c in chosen}
        jobs = []
        for card in chosen:
            target = folder / "carousels" / card["name"]
            target.mkdir(parents=True)
            for slide in card["slides"]:
                shutil.copyfile(card["folder"] / slide, target / slide)
                jobs.append((target / slide, target / "view" / previews.preview_name(slide)))
            if card["zip_data"] is not None:
                (target / downloads.zip_name(card["folder"])).write_bytes(card["zip_data"])
        if with_approved:
            (folder / "carousels" / downloads.APPROVED_ZIP_NAME).parent.mkdir(parents=True, exist_ok=True)
            (folder / "carousels" / downloads.APPROVED_ZIP_NAME).write_bytes(approved_data)
        # Small previews for the page; the full PNGs stay for the downloads. A slide without a preview shows its PNG.
        made_previews = previews.make_previews(jobs)

        def place(card: dict) -> str:
            chosen_card = keep_names[card["name"]]
            card["zip"] = downloads.zip_name(card["folder"]) if chosen_card["zip_data"] is not None else None
            view_dir = folder / "carousels" / card["name"] / "view"
            card["views"] = {slide: f"carousels/{card['name']}/view/{previews.preview_name(slide)}"
                             for slide in card["slides"] if (view_dir / previews.preview_name(slide)).exists()}
            return f"carousels/{card['name']}"

        page, _ = dashboard.build_page(
            db_path=root / "data" / "seen.sqlite", sources_path=root / "config" / "sources.yaml",
            rules_path=root / "config" / "rules.yaml", now=now, carousels_dir=carousels_dir,
            samples_dir=root / "output" / "samples", previews_dir=previews_dir, read_only=True,
            card_filter=lambda c: c["name"] in keep_names, base_for=place,
            approved_href=f"carousels/{downloads.APPROVED_ZIP_NAME}" if with_approved else None)
        (folder / "index.html").write_text(page, encoding="utf-8")
        (folder / "READ ME FIRST.txt").write_text(
            README.format(made=now.astimezone(activity.MANILA).strftime("%b %d, %Y, %I:%M %p")), encoding="utf-8")

        problems = scan_pack(folder, root)
        if problems:
            raise ExportError("the copy would contain private details, so it was deleted: " + "; ".join(problems[:5]))

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(p for p in folder.rglob("*") if p.is_file()):
                stored = file.suffix.lower() in (".png", ".zip", ".jpg")
                archive.write(file, f"{name}/{file.relative_to(folder).as_posix()}",
                              compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        if size_mb > limit_mb:
            raise ExportError(f"the zip is {size_mb:.1f} MB, over the {limit_mb} MB limit")
        latest = refresh_latest(folder, out_root)
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        activity.log_event("export", "failed", f"Export for David not made: {exc}", now=now)
        if isinstance(exc, ExportError):
            raise
        raise ExportError(f"{type(exc).__name__}: {exc}") from exc

    skipped = f"{left_out} left out (no slides)"
    extra = f"; {'; '.join(notes)}" if notes else ""
    if log_made:
        activity.log_event("export", "made", f"{zip_path.name}, {size_mb:.1f} MB, {len(chosen)} carousels, "
                           f"{made_previews} previews, {skipped}, {LATEST} folder refreshed{extra}", now=now)
    return {"folder": folder, "zip": zip_path, "size_mb": size_mb, "carousels": len(chosen), "notes": notes,
            "latest": latest, "previews": made_previews}


def refresh_latest(folder: Path, out_root: Path) -> Path:
    """output/share/latest/ always holds the newest pack, ready to upload to a web host as is."""
    latest = out_root / LATEST
    temp = out_root / f".{LATEST}-new"
    shutil.rmtree(temp, ignore_errors=True)
    shutil.copytree(folder, temp)
    shutil.rmtree(latest, ignore_errors=True)
    os.replace(temp, latest)
    return latest


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Export for David: the read only static copy of the dashboard.")
    parser.add_argument("--cloud", action="store_true",
                        help="the hourly GitHub Actions copy for the web link: a made copy is not written to the "
                             "activity log (a failed one still is)")
    args = parser.parse_args(argv)
    try:
        result = export_pack(log_made=not args.cloud)
    except ExportError as exc:
        print(f"Not made: {exc}")
        return 1
    print(f"Export for David ready: {result['zip'].name} (in output\\share)")
    print(f"Size: {result['size_mb']:.1f} MB, {result['carousels']} carousels, {result['previews']} slide previews.")
    for note in result["notes"]:
        print(f"  {note}")
    print("Web link: upload everything in output\\share\\latest to a web host, then send David the link.")
    print("Or send David the zip. He unzips it and double-clicks index.html.")
    return 0
