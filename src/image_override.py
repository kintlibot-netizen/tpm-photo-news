"""Manual official image overrides: a real official image that was saved by hand for one slide of one story.

Some official pages cannot be read by the build (helpx.adobe.com answers 403 to scripts), so their images are never
found by the automatic search. When a person has found the real image, it is saved in assets/official/ and named in
assets/official/overrides.json:

{
  "<story folder name>": {
    "CAMERA ANGLES": {"file": "ps-beta-camera-controls-3.jpg",
           "image_url": "https://helpx-prod.scene7.com/is/image/HelpxProd/ps-beta-camera-controls-3?...",
           "page_url": "https://helpx.adobe.com/photoshop/.../change-camera-angles.html",
           "page_title": "Change camera angles in Photoshop (beta) on desktop"}
  }
}

The story folder name is the name of the output folder (for example 2026-11-11-photoshop-can-now-relight-...). The
key under it is the FEATURE name, not a slide number, so the override follows its feature when slides are reordered.
The build finds the feature slide whose headline is that feature and then:
- uses that file for that slide, trims uniform grey, white or dark side strips (a plain crop, nothing else changes),
  and saves it as images/NN.png (or the original file when there is nothing to trim),
- records the image URL and the official page URL in sources.md,
- skips the automatic image search for that slide.

An override is used only when: its file exists and is a real JPEG, PNG or WebP of at least 1000px with no AI metadata,
both URLs are on an official domain of the brand, and the story has a feature slide for that feature. Otherwise it is skipped with the reason written to sources.md, and the automatic search runs as usual.
Nothing here generates, edits or retouches an image.
"""
from __future__ import annotations

import json
from pathlib import Path

import border_trim
import image_pick
import images
from images import AI_METADATA, MIN_LONG_SIDE, extension_for, host_allowed, image_dimensions

ROOT = Path(__file__).resolve().parent.parent
OVERRIDES_DIR = ROOT / "assets" / "official"
OVERRIDES_PATH = OVERRIDES_DIR / "overrides.json"
REQUIRED = ("file", "image_url", "page_url")


def load_overrides(path: Path = OVERRIDES_PATH) -> dict:
    """The whole overrides file, {} when there is none or it is not valid JSON."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def for_story(story_folder: str, path: Path = OVERRIDES_PATH) -> dict[str, dict]:
    """The overrides of one story, {"CAMERA ANGLES": entry}, keyed by feature name."""
    entries = load_overrides(path).get(story_folder)
    if not isinstance(entries, dict):
        return {}
    return {str(key): value for key, value in entries.items() if isinstance(value, dict)}


def slot_for_feature(feature: str, views: list[dict]) -> str | None:
    """The slide number ("06") of the feature slide about this feature, whatever its position. None when there is none."""
    for number, view in enumerate(views, 1):
        if view.get("type") == "feature" and image_pick._same_feature(feature, view.get("headline", "")):
            return f"{number:02d}"
    return None


def known_page_images(path: Path = OVERRIDES_PATH) -> dict[str, dict]:
    """{official page URL: {"image_url", "title"}} for every override. The automatic search uses this when it cannot
    read the page itself: the image host (scene7) answers a normal request even when helpx refuses the page."""
    found: dict[str, dict] = {}
    for entries in load_overrides(path).values():
        if not isinstance(entries, dict):
            continue
        for entry in entries.values():
            if isinstance(entry, dict) and entry.get("page_url") and entry.get("image_url"):
                found[entry["page_url"]] = {"image_url": entry["image_url"], "title": entry.get("page_title", "")}
    return found


def problem_with(entry: dict, view: dict | None, domains: list[str], folder: Path) -> str:
    """Why an override cannot be used ("" when it can)."""
    missing = [key for key in REQUIRED if not entry.get(key)]
    if missing:
        return f"the entry has no {', '.join(missing)}"
    if view is None:
        return "the story has no feature slide for that feature"
    if view.get("type") != "feature":
        return "that slide is not a feature slide"
    if entry.get("feature") and not image_pick._same_feature(entry["feature"], view.get("headline", "")):
        return f"slide is about {view.get('headline')!r}, not {entry['feature']!r}"
    for key in ("image_url", "page_url"):
        if not host_allowed(entry[key], domains):
            return f"{key} is not on an official domain"
    path = folder / entry["file"]
    if not path.is_file():
        return f"the file {entry['file']} is not in {folder}"
    data = path.read_bytes()
    size = image_dimensions(data)
    if extension_for(data) is None:
        return "the file is not a JPEG, PNG or WebP image"
    if size is None or max(size) < MIN_LONG_SIDE:
        return f"the image is under {MIN_LONG_SIDE}px on the long side"
    if any(marker in data for marker in AI_METADATA):
        return "embedded metadata says it is AI-generated"
    return ""


def _save(images_dir: Path, slot: str, data: bytes) -> Path:
    """images/<slot>.<ext>, with any other file of that slot removed so only this one can be rendered."""
    target = images_dir / f"{slot}{extension_for(data)}"
    for extension in image_pick.IMAGE_EXTENSIONS:
        stale = images_dir / f"{slot}{extension}"
        if stale != target and stale.is_file():
            stale.unlink()
    target.write_bytes(data)
    return target


def apply_overrides(entries: dict[str, dict], views: list[dict], out_dir: Path, domains: list[str],
                    trim=border_trim.trim_border, folder: Path = OVERRIDES_DIR) -> tuple[set[str], list[str]]:
    """Places each usable override as images/NN.png. Returns (slot names the automatic search must skip, log lines
    for sources.md). A skipped override is named in the log and its slide is left to the automatic search."""
    taken: set[str] = set()
    log: list[str] = []
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for feature, entry in sorted(entries.items()):
        slot = slot_for_feature(feature, views)
        view = views[int(slot) - 1] if slot else None
        entry = {"feature": feature, **entry}
        reason = problem_with(entry, view, domains, folder)
        if reason:
            where = f"slide {slot} ({feature})" if slot else f"feature {feature}"
            log.append(f"{where}: manual official image override not used ({reason}); the automatic search runs")
            continue
        data = (folder / entry["file"]).read_bytes()
        placed, info = trim(data)
        target = _save(images_dir, slot, placed)
        size = image_dimensions(placed)
        note = border_trim.describe(info) if info.get("trimmed") else "no strip to trim, used as published"
        log.append(f"slide {slot} ({feature}): manual official image override placed as {target.name} ({size[0]}x{size[1]}). "
                   f"Image: {entry['image_url']}. Official page: {entry['page_url']}. "
                   f"File {entry['file']}. {note}. The automatic image search is skipped for this slide")
        taken.add(slot)
    return taken, log
