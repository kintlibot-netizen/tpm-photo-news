"""Downloads of finished carousels: one zip per carousel, single slides, and all approved carousels in one zip.

A carousel zip holds:
  01-cover.png, 02-relight.png ...   the slides, named in order after what each slide shows
  captions-tpm-facebook.txt          the caption for each account (TPM Facebook, TPM Instagram, David Facebook)
  captions-tpm-instagram.txt
  captions-david-facebook.txt
  sources.txt                        the official links the facts and images came from
  README.txt                         what is inside and the posting rule
A sample's zip name starts with SAMPLE, so it is never mistaken for a real draft.

Each carousel build writes its zip into the carousel folder (prebuilt), so the dashboard opened as a plain file can
link straight to it. The review server builds the same zip on request (GET /api/download/...).

python src\\downloads.py --all      Writes the zip for every carousel folder that has slides (old builds included).

Nothing here posts anywhere, and no zip ever holds a secret or a path from this PC: only the slide images, the
caption text, the official links and a fixed README are written.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import carousel_status

ROOT = Path(__file__).resolve().parent.parent
CAROUSELS = ROOT / "output" / "carousels"
SAMPLES = ROOT / "output" / "samples"
ACCOUNTS = (
    ("tpm-facebook", "TPM Facebook", "tpm"),
    ("tpm-instagram", "TPM Instagram", "tpm"),
    ("david-facebook", "David Molnar Facebook", "david"),
)
# captions.txt may end with this block: hashtags for the TPM Instagram caption only (never Facebook, never David's).
HASHTAG_HEADER = "TPM INSTAGRAM HASHTAGS (added to the TPM Instagram caption only)"
FINISHED = ("waiting_for_david", "approved", "posted")
APPROVED = ("approved", "posted")
SLIDE_GLOB = "[0-9][0-9].png"
ZIP_README = """TPM carousel: {title}

Slides: {count}, 1080 x 1440, in posting order (01 is the cover).
Captions: one text file per account. TPM Facebook and TPM Instagram use the "we" caption,
David Molnar Facebook uses David's first person caption.
sources.txt: the official pages every fact and image comes from.

Status when this zip was made: {status}.
Nothing is posted automatically. Post by hand in Meta Business Suite, and only after David approves.
David's personal Instagram is never used.
"""


def slug(text: str, limit: int = 40) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return value[:limit].strip("-") or "slide"


def is_sample(folder: Path, status: dict | None = None) -> bool:
    status = status if status is not None else carousel_status.read_status(folder)
    title = str(status.get("build", {}).get("title", ""))
    return (folder.name.endswith("-sample") or folder.parent.name == "samples"
            or title.upper().startswith("SAMPLE:") or bool(status.get("build", {}).get("sample")))


def zip_name(folder: Path, status: dict | None = None) -> str:
    """The zip file name: the folder name, with SAMPLE in front for a sample."""
    return ("SAMPLE-" if is_sample(folder, status) else "") + f"{folder.name}.zip"


def slides(folder: Path) -> list[Path]:
    return sorted(folder.glob(SLIDE_GLOB))


def slide_labels(folder: Path) -> list[str]:
    """What each slide shows, in the order the build renders them: cover, first feature, comparison, the other
    features, price. Read from plan.json; a slide the plan cannot name is called "slide"."""
    try:
        plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        plan = {}
    features = []
    for item in plan.get("slides") or []:
        headline = item.get("headline") if isinstance(item, dict) else None
        text = headline.get("text") if isinstance(headline, dict) else None
        features.append(slug(text) if text else "slide")
    labels = ["cover"] + features[:1]
    if plan.get("comparison"):
        labels.append("comparison")
    labels += features[1:]
    if plan.get("price"):
        labels.append("price")
    if carousel_status.read_status(folder).get("build", {}).get("closing"):
        labels.append("your-take")  # the closing call to action slide (carousel_plan.closing_view)
    return labels


def slide_entries(folder: Path) -> list[tuple[Path, str]]:
    """(slide file, name in the zip) for every rendered slide: 01-cover.png, 02-relight.png ..."""
    files = slides(folder)
    labels = slide_labels(folder)
    if len(labels) != len(files):  # a slide was dropped by the fact check: number them plainly
        labels = ["cover"] + ["slide"] * (len(files) - 1)
    return [(path, f"{path.stem}-{label}.png") for path, label in zip(files, labels)]


def slide_download_name(folder: Path, slide_file: str) -> str | None:
    """The friendly file name of one slide (02-relight.png), or None when the folder has no such slide."""
    for path, name in slide_entries(folder):
        if path.name == slide_file:
            prefix = "SAMPLE-" if is_sample(folder) else ""
            return f"{prefix}{folder.name}-{name}"
    return None


def account_captions(folder: Path) -> dict[str, str]:
    """The caption for each account key, from captions.txt. An account with no caption is left out."""
    try:
        text = (folder / "captions.txt").read_text(encoding="utf-8")
    except OSError:
        return {}
    voices: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("DAVID MOLNAR FACEBOOK"):
            current = "david"
            continue
        if line.startswith("TPM FACEBOOK AND INSTAGRAM"):
            current = "tpm"
            continue
        if line.startswith("TPM INSTAGRAM HASHTAGS"):
            current = "hashtags"
            continue
        if current and line.strip():
            voices[current] = (voices.get(current, "") + " " + line.strip()).strip()
    found = {key: voices[voice] for key, _, voice in ACCOUNTS if voice in voices}
    if voices.get("hashtags") and "tpm-instagram" in found:
        found["tpm-instagram"] += "\n\n" + voices["hashtags"]
    return found


def official_links(folder: Path) -> list[tuple[str, str]]:
    """(what, link) for the official source and every web link in sources.md. Only http and https links."""
    status = carousel_status.read_status(folder)
    links: list[tuple[str, str]] = []
    official = status.get("build", {}).get("official_url")
    if isinstance(official, str) and official.startswith(("http://", "https://")):
        links.append(("Official source for every fact", official))
    try:
        text = (folder / "sources.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    for url in re.findall(r"https?://[^\s)<>\"'|]+", text):
        url = url.rstrip(".,;")
        if all(url != seen for _, seen in links):
            links.append(("Link from sources.md", url))
    return links


def sources_text(folder: Path) -> str:
    status = carousel_status.read_status(folder)
    title = status.get("build", {}).get("title") or folder.name
    lines = [f"Sources: {title}", "",
             "Every fact on the slides and in the captions comes from the official page below.",
             "The news sites are where the story was first seen; they are context only.", ""]
    lines += [f"{what}: {url}" for what, url in official_links(folder)] or ["No official link was recorded."]
    return "\n".join(lines) + "\n"


def zip_bytes(folder: Path) -> bytes:
    """The carousel zip, in memory."""
    status = carousel_status.read_status(folder)
    buffer = io.BytesIO()
    entries = slide_entries(folder)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, name in entries:
            archive.write(path, name, compress_type=zipfile.ZIP_STORED)  # PNGs are already compressed
        for key, _, _ in ACCOUNTS:
            caption = account_captions(folder).get(key)
            if caption:
                archive.writestr(f"captions-{key}.txt", caption + "\n")
        archive.writestr("sources.txt", sources_text(folder))
        label = carousel_status.STATUS_LABELS.get(status.get("status"), status.get("status", "draft"))
        if is_sample(folder, status):
            label = "SAMPLE for checking the layout, never for posting"
        archive.writestr("README.txt", ZIP_README.format(
            title=status.get("build", {}).get("title") or folder.name, count=len(entries), status=label))
    return buffer.getvalue()


def write_folder_zip(folder: Path) -> Path | None:
    """Writes the prebuilt zip into the carousel folder (and removes an older one). None when there are no slides."""
    for old in folder.glob("*.zip"):
        try:
            old.unlink()
        except OSError:
            pass
    if not slides(folder):
        return None
    target = folder / zip_name(folder)
    temp = target.with_name(target.name + ".tmp")
    temp.write_bytes(zip_bytes(folder))
    temp.replace(target)
    return target


def prebuilt_zip(folder: Path) -> Path | None:
    path = folder / zip_name(folder)
    return path if path.exists() else None


def carousel_folders(carousels_dir: Path | None = None, samples_dir: Path | None = None,
                     include_samples: bool = True) -> list[Path]:
    roots = [carousels_dir or CAROUSELS] + ([samples_dir or SAMPLES] if include_samples else [])
    found = []
    for root in roots:
        if root.exists():
            found += sorted(p for p in root.iterdir() if p.is_dir() and (p / "captions.txt").exists())
    return found


def approved_folders(carousels_dir: Path | None = None) -> list[Path]:
    """Real carousels David approved (or already posted). Samples never."""
    return [folder for folder in carousel_folders(carousels_dir, include_samples=False)
            if carousel_status.read_status(folder)["status"] in APPROVED and not is_sample(folder) and slides(folder)]


def approved_zip_bytes(carousels_dir: Path | None = None) -> tuple[bytes, int]:
    """(zip, how many carousels): one subfolder per approved carousel, each with its slides, captions and sources."""
    buffer = io.BytesIO()
    folders = approved_folders(carousels_dir)
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder in folders:
            inner = zipfile.ZipFile(io.BytesIO(zip_bytes(folder)))
            for item in inner.infolist():
                archive.writestr(f"{folder.name}/{item.filename}", inner.read(item.filename),
                                 compress_type=item.compress_type)
        if not folders:
            archive.writestr("README.txt", "No carousel is approved yet.\n")
    return buffer.getvalue(), len(folders)


APPROVED_ZIP_NAME = "TPM-approved-carousels.zip"


def write_approved_zip(carousels_dir: Path | None = None) -> Path | None:
    """Writes every approved carousel in one zip beside the carousel folders (for the dashboard opened as a file).
    Removes it when nothing is approved. Returns the path, or None."""
    root = carousels_dir or CAROUSELS
    target = root / APPROVED_ZIP_NAME
    data, count = approved_zip_bytes(root)
    if not count:
        target.unlink(missing_ok=True)
        return None
    temp = target.with_name(target.name + ".tmp")
    temp.write_bytes(data)
    temp.replace(target)
    return target


def ensure_zips(carousels_dir: Path | None = None, samples_dir: Path | None = None) -> list[Path]:
    """Writes the prebuilt zip for every finished carousel that has slides but no zip yet (for example one built
    before the zips existed), and the approved zip. A carousel whose design check failed gets none, like a build.
    Never raises; returns the zips written."""
    written = []
    for folder in carousel_folders(carousels_dir, samples_dir):
        try:
            build = carousel_status.read_status(folder).get("build", {})
            if prebuilt_zip(folder) or not slides(folder) or build.get("design_fail"):
                continue
            path = write_folder_zip(folder)
            if path:
                written.append(path)
        except (OSError, ValueError):
            continue
    try:
        write_approved_zip(carousels_dir)
    except OSError:
        pass
    return written


def refresh_after_review(folder: Path) -> None:
    """After a review action: the carousel's own zip (its README says the new status) and the approved zip.
    Never raises: a download file is extra, the review itself is already saved."""
    try:
        if slides(folder):
            write_folder_zip(folder)
        write_approved_zip(folder.parent)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Builds the download zips of the carousels. Posts nothing.")
    parser.add_argument("--all", action="store_true", help="write the zip for every carousel folder with slides")
    args = parser.parse_args(argv)
    if not args.all:
        parser.print_help()
        return 0
    made = 0
    for folder in carousel_folders():
        path = write_folder_zip(folder)
        if path:
            made += 1
            print(f"Zip written: {folder.name}\\{path.name}")
    approved = write_approved_zip()
    print(f"{made} zip files written." + (f" All approved carousels: {approved.name}" if approved else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
