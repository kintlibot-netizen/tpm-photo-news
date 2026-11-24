"""Builds dashboard/index.html from the watcher's SQLite data, the carousel folders and the activity log.

The page is one static file with inline CSS, JS, icons and fonts (dashboard_assets.py). It needs no CDN and no network,
and it never contains the Slack webhook or any other secret. run.py rebuilds it at the end of every run.
To rebuild it alone:  python src\\dashboard.py

It is laid out like an app: a sidebar with the sections, a top bar that says when the last check ran, when the next one
is due and whether the watcher is healthy, and one page per section, in the same order as the README:
Start here, Overview, Needs your attention, Stories, Carousels, Activity, Sources, How it works.

Two modes:
  local  Kint's page. Opened through the review server (Open Review Dashboard.bat) the review buttons and downloads
         work directly. Opened as a file, the buttons copy the PowerShell command and the downloads link to the files.
  share  The read only copy for David (share_pack.py, build_page(read_only=True)): the same page, the same look and
         the same sections, rendered from this same template. Only what a public read only copy must not have is
         left out: no approve, reject, review, export or command copy buttons (each card shows its status badge
         instead), no commands, no paths from this PC, relative paths to the copied images and downloads, and the note
         at the top: "Read only copy. To approve a carousel, tell Kint."
"""
from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

import activity
import alert
import carousel_status
import classify
import dashboard_assets
import dedupe
import downloads
import runlog
import schedule_info
from dashboard_assets import icon

ROOT = Path(__file__).resolve().parent.parent
MANILA = timezone(timedelta(hours=8), "Asia/Manila")  # Manila has no daylight saving time.
HISTORY_ROWS = 20
ACTIVITY_ROWS = 500
MODE_NAMES = {"live": "Live", "dry": "Dry run"}
STORY_COLUMNS = (
    "id", "title", "brand", "first_seen", "last_alert_label", "dismissed",
    "claude_label", "skipped", "review_version",
)
STATUS_CLASS = {
    runlog.ALERTED: "st-alert",
    runlog.HELD: "st-held",
    runlog.WAITING_SEND: "st-held",
    runlog.REJECTED: "st-rej",
    runlog.SKIPPED: "st-rej",
    runlog.DRY_ONLY: "st-dry",
    runlog.FAILED: "st-fail",
}
PILL_CLASS = {classify.OFFICIAL: "pill-official", classify.RUMOR: "pill-rumor", "REJECTED": "pill-rejected",
              "SKIPPED": "pill-rejected"}
ALL_STATUSES = [
    runlog.ALERTED, runlog.HELD, runlog.REJECTED, runlog.SKIPPED,
    runlog.DRY_ONLY, runlog.FAILED, runlog.WAITING_SEND,
]
REVIEW_ACCOUNTS = [("tpm-facebook", "TPM Facebook"), ("tpm-instagram", "TPM Instagram"),
                   ("david-facebook", "David Facebook")]
# The sidebar, in the README's order. "start" is the one page explainer, the home page of David's copy.
PAGES = [("start", "Start here", "start"), ("overview", "Overview", "overview"),
         ("attention", "Needs your attention", "attention"), ("stories", "Stories", "stories"),
         ("carousels", "Carousels", "carousels"), ("activity", "Activity", "activity"),
         ("sources", "Sources", "sources"), ("how", "How it works", "how")]
# Where each story is in the flow, from news found to posted by hand. Every story is in one stage at a time.
STAGES = [
    ("found", "News found", "Seen on a site, waiting for a 2nd source or to be sent"),
    ("verified", "Verified, sent", "Official, or 2 sites. Sent to Slack"),
    ("drafted", "Carousel drafted", "Built from the official page"),
    ("checked", "Fact checked", "Facts confirmed, a design fix is needed"),
    ("waiting", "Waiting for David", "Passed every check"),
    ("approved", "Approved", "Ready to post by hand"),
    ("posted", "Posted", "Posted by hand in Meta Business Suite"),
]
STAGE_NAMES = dict((key, name) for key, name, _ in STAGES) | {"out": "Not taken forward"}
STAGE_CLASS = {"found": "st-held", "verified": "st-alert", "drafted": "st-held", "checked": "st-held",
               "waiting": "st-accent", "approved": "st-ok", "posted": "st-ok", "out": "st-rej"}
SHARE_NOTE = "Read only copy. To approve a carousel, tell Kint."
HEALTHY_HOURS = 2


# ---------- small helpers ----------

def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def safe_url(url) -> str | None:
    """Only web links become clickable. Anything else from a feed is shown as plain text."""
    text = str(url or "").strip()
    return text if text.lower().startswith(("http://", "https://")) else None


def parse_time(text) -> datetime | None:
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def show_time(moment) -> str:
    if moment is None:
        return "Not recorded"
    return moment.astimezone(MANILA).strftime("%b %d, %Y, %I:%M %p")


def first_sentence(text, limit: int = 200) -> str:
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    return first if len(first) <= limit else first[: limit - 3].rstrip() + "..."


def title_key(title) -> str:
    return " ".join(str(title).lower().split())


def display_text(text) -> str:
    """Text as the page shows it: no em or en dashes (David dislikes them). " - " between words becomes a comma."""
    value = re.sub(r"\s+[–—-]+\s+", ", ", str(text or ""))
    return value.replace("—", ", ").replace("–", "-")


def category_name(category: str) -> str:
    return alert.CATEGORY_NAMES.get(category, category.replace("-", " ").capitalize())


def parse_sources(text) -> list[dict]:
    try:
        value = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def folder_slug(title: str) -> str:
    """The slug part of a carousel folder name, made the same way as carousel.item_folder."""
    return re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")[:60].strip("-") or "story"


def read_next_run() -> datetime | None:
    """When the Windows task runs next (None when it can't be read). Tests replace this."""
    return schedule_info.next_run_time()


# ---------- reading the data ----------

def configured_feeds(sources_path: Path) -> list[tuple[str, str]]:
    try:
        with open(sources_path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        return [(source["name"], source.get("type", "news")) for source in config["sources"]]
    except (OSError, yaml.YAMLError, KeyError, TypeError):
        return []


def load_rules(rules_path: Path) -> dict | None:
    try:
        with open(rules_path, encoding="utf-8") as handle:
            return classify.normalize_rules(yaml.safe_load(handle))
    except (OSError, yaml.YAMLError, ValueError, KeyError, TypeError):
        return None


def read_database(db_path: Path) -> dict:
    """Reads the watcher's data without changing it. A missing database shows an empty page."""
    data = {"runs": [], "feeds": [], "outcomes": [], "stories": [], "sources": {}, "builds": []}
    if not db_path.exists():
        return data
    db = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "runs" in tables:
            data["runs"] = [dict(r) for r in db.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (HISTORY_ROWS,))]
            if data["runs"] and "feed_results" in tables:
                data["feeds"] = [dict(r) for r in db.execute(
                    "SELECT feed, ok, items, error FROM feed_results WHERE run_id=?",
                    (data["runs"][0]["id"],))]
        if "story_outcomes" in tables and "runs" in tables:
            data["outcomes"] = [dict(r) for r in db.execute(
                "SELECT o.*, r.mode AS mode FROM story_outcomes o JOIN runs r ON r.id = o.run_id "
                "ORDER BY o.id")]
            for row in data["outcomes"]:
                row["status"] = runlog.normalize_status(row["status"])
        if "stories" in tables:
            present = {r[1] for r in db.execute("PRAGMA table_info(stories)")}
            # Databases from before a column existed still open; the missing column reads as empty.
            columns = [c if c in present else f"NULL AS {c}" for c in STORY_COLUMNS]
            data["stories"] = [dict(r) for r in db.execute(f"SELECT {', '.join(columns)} FROM stories")]
        if "sources" in tables:
            for r in db.execute("SELECT story_id, source, source_type, title, url, link, summary FROM sources"):
                data["sources"].setdefault(r["story_id"], []).append({
                    "source": r["source"], "source_type": r["source_type"], "title": r["title"],
                    "link": r["link"] or r["url"], "summary": r["summary"],
                })
        if "carousel_builds" in tables:
            data["builds"] = [dict(r) for r in db.execute(
                "SELECT story_id, built_at, status, folder, message FROM carousel_builds ORDER BY id")]
    finally:
        db.close()
    return data


# ---------- building the story list ----------

def current_brand(stored_brand, sources: list[dict], rules: dict | None) -> str:
    """The brand of the product, read from the stored sources under the current rules.
    Falls back to the stored brand when the sources name none."""
    if rules:
        found = dedupe.brand_from_sources(sources, rules["brands"])
        if found:
            return found
    return stored_brand or ""


def story_from_outcome(row: dict, stored: dict | None, sources: list[dict], rules: dict | None) -> dict:
    """A story whose latest run outcome is known. Title and brand come from the stored story, so a
    later correction shows even when the status did not change."""
    first = parse_time(row.get("first_seen")) or parse_time(row.get("seen_at"))
    return {
        "story_id": stored["id"] if stored else row.get("story_id"),
        "title": stored["title"] if stored else row["title"],
        "brand": current_brand(stored["brand"] if stored else row.get("brand"), sources, rules),
        "category": row.get("category") or "",
        "label": row.get("label") or classify.RUMOR,
        "status": row["status"],
        "reason": row.get("reason") or "",
        "summary": row.get("summary") or (stored["title"] if stored else row["title"]),
        "first_seen": first,
        "sources": sources,
    }


def story_from_row(row: dict, sources: list[dict], rules: dict | None) -> dict:
    """A stored story with no run outcome yet. Its status is worked out from the stored flags and
    the current rules, the same way the next run would."""
    probe = dedupe.Story(title=row["title"], brand=row["brand"], kind="product", tokens=frozenset())
    probe.sources = sources
    # An old Claude label does not count under the current rules, as in run.refresh_stored.
    probe.claude_label = row["claude_label"] if row["review_version"] == classify.RULES_VERSION else None
    if rules:
        label = classify.story_label(probe, rules)
    else:
        label = row["last_alert_label"] or classify.RUMOR
    skipped = row["skipped"]
    if rules and not row["last_alert_label"]:
        skipped = classify.story_skip_reason(sources, rules)
    if row["dismissed"]:
        status = runlog.REJECTED
    elif skipped:
        status = runlog.SKIPPED
    elif row["last_alert_label"]:
        status = runlog.ALERTED
    elif label == classify.RUMOR:
        status = runlog.HELD
    else:
        status = runlog.WAITING_SEND
    first_text = sources[0].get("summary") if sources else ""
    return {
        "story_id": row["id"],
        "title": row["title"],
        "brand": current_brand(row["brand"], sources, rules),
        "category": classify.rule_category(row["title"], rules) if rules else "",
        "label": label,
        "status": status,
        "reason": skipped or "",
        "summary": first_sentence(first_text) or row["title"],
        "first_seen": parse_time(row["first_seen"]),
        "sources": sources,
    }


def build_stories(data: dict, rules: dict | None) -> list[dict]:
    latest_real: dict[int, dict] = {}
    latest_dry: dict[str, dict] = {}
    sent_at: dict[int, datetime] = {}
    for row in data["outcomes"]:
        if row["story_id"] is not None:
            latest_real[row["story_id"]] = row
            moment = parse_time(row["seen_at"])
            if row["status"] == runlog.ALERTED and moment:
                if row["story_id"] not in sent_at or moment > sent_at[row["story_id"]]:
                    sent_at[row["story_id"]] = moment
        else:
            latest_dry[title_key(row["title"])] = row

    stories, known_ids, known_titles = [], set(), set()
    stored_by_id = {row["id"]: row for row in data["stories"]}
    for row in data["stories"]:
        known_ids.add(row["id"])
        known_titles.add(title_key(row["title"]))
        sources = data["sources"].get(row["id"], [])
        if row["id"] in latest_real:
            story = story_from_outcome(latest_real[row["id"]], row, sources, rules)
        else:
            story = story_from_row(row, sources, rules)
        story["sent_at"] = sent_at.get(row["id"])
        stories.append(story)
    for story_id, row in latest_real.items():
        if story_id not in known_ids:
            story = story_from_outcome(row, stored_by_id.get(story_id), data["sources"].get(story_id, []), rules)
            story["sent_at"] = sent_at.get(story_id)
            stories.append(story)
    for key, row in latest_dry.items():
        # A practice-run story that is also a saved story is already shown above.
        if key not in known_titles:
            story = story_from_outcome(row, None, parse_sources(row.get("sources")), rules)
            story["sent_at"] = None
            stories.append(story)

    for story in stories:
        if story["status"] == runlog.REJECTED:
            story["pill"] = "REJECTED"
        elif story["status"] == runlog.SKIPPED:
            story["pill"] = "SKIPPED"
        else:
            story["pill"] = story["label"]
    floor = datetime.min.replace(tzinfo=timezone.utc)
    stories.sort(key=lambda s: s["first_seen"] or floor, reverse=True)
    return stories


def summarize(stories: list[dict], now: datetime) -> dict:
    """Every card is counted from the same story list the page shows."""
    today = now.astimezone(MANILA).date()
    week_start = now - timedelta(days=7)
    sent = [s for s in stories if s["status"] == runlog.ALERTED]
    return {
        "today": sum(1 for s in sent if s["sent_at"] and s["sent_at"].astimezone(MANILA).date() == today),
        "week": sum(1 for s in sent if s["sent_at"] and s["sent_at"] >= week_start),
        "undated": sum(1 for s in sent if s["sent_at"] is None),
        "waiting": sum(1 for s in stories if s["status"] == runlog.HELD),
        "rejected": sum(1 for s in stories if s["status"] == runlog.REJECTED),
        "skipped": sum(1 for s in stories if s["status"] == runlog.SKIPPED),
    }


# ---------- carousels ----------

REAL_KINDS = ("draft",)  # a card of any other kind (sample, preview) is never counted, linked to a story or approved


def is_real(card: dict) -> bool:
    return card.get("kind") in REAL_KINDS


PREVIEW_NOTE = "Preview, not sent for approval yet"
SAMPLE_NOTE = "Layout sample not for posting"


def read_carousels(carousels_dir: Path, samples_dir: Path | None = None,
                   previews_dir: Path | None = None) -> list[dict]:
    """Every real carousel folder that has captions.txt: real carousels first (newest name first), then previews.
    Layout samples (fixtures with no official images) are never shown: samples_dir is accepted and ignored."""
    cards = []
    sources = [(carousels_dir, "carousels"), (previews_dir, "plan-previews")]
    for root, base in sources:
        if root is None or not root.exists():
            continue
        for folder in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
            if not (folder / "captions.txt").exists():
                continue
            same = next((c for c in cards if c["name"] == folder.name), None)
            if same is not None:
                if not (base == "plan-previews" and same["status"] in ("rejected", "draft")):
                    continue  # a preview of a carousel sent for review is shown once, as the real carousel
                cards.remove(same)  # a newer preview of a draft or rejected carousel replaces it on the page
            status = carousel_status.read_status(folder)
            if downloads.is_sample(folder, status):
                continue  # a layout sample is a fixture, not a real carousel
            if base == "plan-previews":
                kind = "preview"
            else:
                kind = "draft"
            prebuilt = downloads.prebuilt_zip(folder)
            cards.append({
                "name": folder.name,
                "kind": kind,
                "base": f"../output/{base}/{folder.name}",
                "root": base,
                "folder": folder,
                "status": status["status"],
                "build": status.get("build", {}),
                "slides": sorted(p.name for p in folder.glob("[0-9][0-9].png")),
                "slide_names": {path.name: name for path, name in downloads.slide_entries(folder)},
                "captions": downloads.account_captions(folder),
                "links": downloads.official_links(folder),
                "zip": prebuilt.name if prebuilt else None,
                "approved_by": status.get("approved_by", ""),
                "approved_at": status.get("approved_at", ""),
                "reason": status.get("reason", ""),
                "posts": status.get("posts", []),
            })
    rank = {"draft": 0, "preview": 1, "sample": 2}
    cards.sort(key=lambda c: c["name"], reverse=True)  # newest first
    cards.sort(key=lambda c: rank[c["kind"]])  # real carousels, then previews, then samples
    return cards


CAROUSEL_FILTERS = (("all", "All carousels"), ("waiting_for_david", "Waiting for David"), ("draft", "Draft"),
                    ("preview", "Preview"), ("approved", "Approved"), ("rejected", "Rejected"),
                    ("posted", "Posted"))
GROUP_TITLES = {"preview": "Previews, not sent for approval yet", "sample": "Layout samples, not for posting"}


def slides_without_image(card: dict) -> list[int]:
    """The slide numbers that show no official image. build["missing"] names the empty image slots ("03.jpg",
    "05-old.jpg"); the cover counts as having images when it is a collage of the feature images."""
    build = card.get("build") or {}
    numbers = set()
    for name in build.get("missing") or []:
        head = str(name)[:2]
        if head.isdigit():
            numbers.add(int(head))
    if build.get("cover_collage"):
        numbers.discard(1)
    total = len(card.get("slides") or [])
    return sorted(n for n in numbers if not total or n <= total)


def chip_key(card: dict) -> str:
    """The one status a card is filtered by: preview, sample, or the review status of a real carousel."""
    if card.get("kind") in ("preview", "sample"):
        return card["kind"]
    return card["status"] if card["status"] in carousel_status.STATUSES else "draft"


def _carousel_state(card: dict) -> tuple[str, str]:
    status = card["status"]
    if card.get("kind") == "sample":
        return SAMPLE_NOTE, "st-dry"
    if card.get("kind") == "preview":
        return PREVIEW_NOTE, "st-held"
    if status == "waiting_for_david":
        return "Waiting for David", "st-accent"
    if status == "approved":
        when = (card["approved_at"] or "")[:16].replace("T", " ")
        return f"Approved by {card['approved_by']} on {when}", "st-ok"
    if status == "rejected":
        return f"Rejected: {card['reason']}", "st-fail"
    if status == "posted":
        accounts = ", ".join(sorted({p.get("account", "") for p in card["posts"]}))
        return f"Posted to {accounts}", "st-ok"
    return "Draft, waiting for review", "st-held"


def carousel_stage(card: dict) -> str:
    status = card["status"]
    if status == "posted":
        return "posted"
    if status == "approved":
        return "approved"
    if status == "waiting_for_david":
        return "waiting"
    if status == "rejected":
        return "out"
    return "checked" if card["build"].get("fact_check_passed") else "drafted"


def link_carousels(stories: list[dict], cards: list[dict], builds: list[dict]) -> None:
    """Gives each story its carousel card (story["carousel"]) and last build attempt (story["build_row"]).
    A carousel belongs to a story through the build record, or else through the folder name made from its title."""
    real = [c for c in cards if is_real(c)]
    by_name = {c["name"]: c for c in real}
    last_build: dict[int, dict] = {}
    for row in builds:
        last_build[row["story_id"]] = row
    for story in stories:
        story["carousel"] = None
        story["build_row"] = last_build.get(story.get("story_id"))
        for row in reversed(builds):
            if row["story_id"] == story.get("story_id") and row["status"] == "ok" and row.get("folder"):
                name = Path(str(row["folder"]).replace("\\", "/")).name
                if name in by_name:
                    story["carousel"] = by_name[name]
                    break
        if story["carousel"] is None and story["status"] == runlog.ALERTED:
            slug = folder_slug(story["title"])
            story["carousel"] = next((c for c in real if c["name"][11:] == slug), None)


def story_stage(story: dict) -> str:
    status = story["status"]
    if status in (runlog.REJECTED, runlog.SKIPPED):
        return "out"
    if status != runlog.ALERTED:
        return "found"
    card = story.get("carousel")
    return carousel_stage(card) if card else "verified"


def coverage_reason(story: dict, now: datetime) -> tuple[str, str]:
    """Why a sent official story has no finished carousel (or what it has), as (words, chip class)."""
    card = story.get("carousel")
    if card:
        state, cls = _carousel_state(card)
        return f"{state} ({card['name']})", cls
    row = story.get("build_row")
    if row and row["status"] == "failed":
        return f"Not made: {row.get('message') or 'no reason recorded'}", "st-fail"
    if row and row["status"] == "needs_kint":
        return carousel_status.WAITING_WORDS, "st-held"
    first = story.get("first_seen")
    if first and now - first > timedelta(hours=72):
        return "Not made: older than 72 hours. It can still be made by hand from the official page.", "st-rej"
    return "Not made yet: waiting for a carousel, made by hand from the official page.", "st-held"


# ---------- rendering: pieces ----------

def card(label: str, value, note: str) -> str:
    return (
        '<div class="card">'
        f'<div class="k">{esc(label)}</div>'
        f'<div class="v">{esc(value)}</div>'
        f'<div class="n">{esc(note)}</div>'
        "</div>"
    )


def options(values, first: str, first_value: str = "") -> str:
    items = [f'<option value="{esc(first_value)}">{esc(first)}</option>']
    items += [f'<option value="{esc(v)}">{esc(v)}</option>' for v in values]
    return "".join(items)


def panel(title: str, body: str, count: str = "", extra: str = "") -> str:
    count_html = f'<span class="count">{esc(count)}</span>' if count else ""
    return (f'<div class="panel"><div class="panel-head"><h2>{esc(title)}</h2>{count_html}{extra}</div>'
            f"{body}</div>")


def page_head(title: str, text: str) -> str:
    return f'<div class="page-head"><h1>{esc(title)}</h1><p>{esc(text)}</p></div>'


def source_links(story: dict) -> str:
    links = []
    for src in story["sources"]:
        name = esc(src.get("source") or "Source")
        url = safe_url(src.get("link"))
        if url:
            links.append(f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{name}</a>')
        else:
            links.append(f"<span>{name}</span>")
    return links


def story_drawer(story: dict, number: int, mode: str) -> str:
    """The detail drawer of one story: summary, why, sources, its carousel and fact check."""
    status = story["status"]
    parts = [f'<template id="d-{number}">',
             f'<h2>{esc(display_text(story["title"]))}</h2>',
             '<div class="chips">'
             f'<span class="pill {PILL_CLASS.get(story["pill"], "pill-rumor")}">{esc(story["pill"])}</span>'
             f'<span class="tag {STATUS_CLASS.get(status, "st-dry")}">{esc(status)}</span>'
             f'<span class="tag stage {STAGE_CLASS[story["stage"]]}">{esc(STAGE_NAMES[story["stage"]])}</span></div>']
    if story["summary"]:
        parts.append(f'<div><h3>Summary</h3><p class="summary">{esc(display_text(story["summary"]))}</p></div>')
    if story["reason"] and not story["reason"].startswith("Matched by the free rules only"):  # old rows: noise
        prefix = "" if status == runlog.SKIPPED else "Label check: "
        parts.append(f'<div><h3>Why</h3><p class="why">{esc(prefix + story["reason"])}</p></div>')
    rows = [
        ("Brand", story["brand"] or "Unbranded"),
        ("Category", category_name(story["category"]) if story["category"] else "Not set"),
        ("First seen", f"{show_time(story['first_seen'])} (Asia/Manila)"),
        ("Sent to Slack", f"{show_time(story['sent_at'])} (Asia/Manila)" if story.get("sent_at") else "Not sent"),
    ]
    parts.append('<dl class="kv">' + "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in rows) + "</dl>")
    links = source_links(story)
    items = "".join(f"<li>{link}</li>" for link in links) or "<li>None recorded.</li>"
    parts.append(f'<div><h3>Sources</h3><ul class="src-list">{items}</ul></div>')
    card_ = story.get("carousel")
    if card_:
        build = card_["build"]
        state, cls = _carousel_state(card_)
        parts.append(
            '<div><h3>Carousel and fact check</h3>'
            f'<p><span class="tag {cls}">{esc(state)}</span></p>'
            f'<p class="summary">Facts: {esc(build.get("confirmed", "n/a"))} confirmed against the official page, '
            f'{esc(build.get("removed_count", "n/a"))} removed as not confirmed. '
            f'{esc(build.get("design_summary", ""))}</p>'
            f'<p><button type="button" class="btn small" data-go="carousels" data-target="car-{esc(card_["name"])}">'
            'Open the carousel</button></p></div>')
    elif story.get("official_sent"):
        reason, cls = coverage_reason(story, story["now"])
        parts.append(f'<div><h3>Carousel</h3><p><span class="tag {cls}">{esc(reason)}</span></p></div>')
    if mode == "local" and status == runlog.ALERTED and story["label"] == classify.OFFICIAL and story.get("story_id"):
        command = f"python src\\carousel.py --story {int(story['story_id'])}"
        parts.append(f'<div><h3>Make a carousel by hand</h3><p class="make">Copy and run: <code>{esc(command)}</code>'
                     f'</p></div>')
    parts.append("</template>")
    return "".join(parts)


def story_row(story: dict, number: int) -> str:
    status = story["status"]
    pill = story["pill"]
    brand = story["brand"] or "Unbranded"
    search = display_text(" ".join([
        story["title"], brand, story["category"], status, pill, story["reason"], story["summary"],
        STAGE_NAMES[story["stage"]], " ".join(s.get("source") or "" for s in story["sources"]),
    ])).lower()
    stamp = int(story["first_seen"].timestamp() * 1000) if story["first_seen"] else 0
    stage_index = [key for key, _, _ in STAGES].index(story["stage"]) if story["stage"] != "out" else -1
    tags = [f'<span class="tag {STATUS_CLASS.get(status, "st-dry")}">{esc(status)}</span>']
    if story["category"]:
        tags.append(f'<span class="tag tag-plain">{esc(category_name(story["category"]))}</span>')
    links = " ".join(source_links(story)[:3]) or '<span class="muted">none recorded</span>'
    return (
        f'<tr class="story" data-label="{esc(pill)}" data-brand="{esc(brand)}" data-status="{esc(status)}" '
        f'data-stage="{esc(story["stage"])}" data-stagei="{stage_index}" data-ts="{stamp}" '
        f'data-title="{esc(title_key(display_text(story["title"])))}" data-text="{esc(search)}">'
        f'<td><button type="button" class="row-title" data-drawer="d-{number}">{esc(display_text(story["title"]))}'
        f'</button><div class="row-tags">{"".join(tags)}</div></td>'
        f'<td>{esc(brand)}</td>'
        f'<td><span class="pill {PILL_CLASS.get(pill, "pill-rumor")}">{esc(pill)}</span></td>'
        f'<td><span class="tag stage {STAGE_CLASS[story["stage"]]}">{esc(STAGE_NAMES[story["stage"]])}</span></td>'
        f'<td class="when">{esc(show_time(story["first_seen"]))}</td>'
        f"<td>{links}</td></tr>"
    )


def stories_panel(stories: list[dict], mode: str = "local") -> str:
    brands = sorted({s["brand"] or "Unbranded" for s in stories})
    labels = [classify.OFFICIAL, classify.RUMOR, "REJECTED", "SKIPPED"]
    stage_options = '<option value="">All stages</option>' + "".join(
        f'<option value="{esc(key)}">{esc(name)}</option>' for key, name, _ in STAGES
    ) + '<option value="out">Not taken forward</option>'
    toolbar = (
        '<div class="toolbar">'
        '<input id="search" type="search" placeholder="Search headlines, brands, sources" aria-label="Search stories">'
        f'<select id="f-label" aria-label="Label">{options(labels, "All labels")}</select>'
        f'<select id="f-brand" aria-label="Brand">{options(brands, "All brands")}</select>'
        f'<select id="f-stage" aria-label="Stage">{stage_options}</select>'
        f'<select id="f-status" aria-label="Status">{options(ALL_STATUSES, "All statuses")}</select>'
        '<select id="f-range" aria-label="Date range">'
        '<option value="all">All time</option><option value="7d">Last 7 days</option>'
        '<option value="24h">Last 24 hours</option></select>'
        '<span id="count" class="count-note"></span>'
        "</div>"
    )

    def sortable(label: str, key: str, col: str) -> str:
        return (f'<th data-col="{col}" aria-sort="none"><button type="button" class="sort" data-sort="{key}">'
                f'{esc(label)}<span class="arr"></span></button></th>')

    head = ("<thead><tr>" + sortable("Story", "title", "title") + sortable("Brand", "brand", "brand")
            + sortable("Type", "label", "label") + sortable("Stage", "stagei", "stagei")
            + sortable("First seen", "ts", "ts") + "<th>Sources</th></tr></thead>")
    rows = "".join(story_row(s, n) for n, s in enumerate(stories, 1))
    drawers = "".join(story_drawer(s, n, mode) for n, s in enumerate(stories, 1))
    if not rows:
        empty = '<div class="empty">No stories recorded yet. The next run will fill this in.</div>'
        return f'<div class="panel">{toolbar}{empty}<table id="story-table"><tbody id="story-list"></tbody></table></div>'
    return (f'<div class="panel">{toolbar}<div class="table-wrap"><table id="story-table">{head}'
            f'<tbody id="story-list">{rows}</tbody></table></div></div>{drawers}')


def feeds_panel(feeds_cfg: list[tuple[str, str]], latest_feeds: list[dict]) -> str:
    by_name = {f["feed"]: f for f in latest_feeds}
    types = dict(feeds_cfg)
    names = [name for name, _ in feeds_cfg] + [n for n in by_name if n not in types]
    rows = []
    for name in names:
        kind = ("Rumor site" if types.get(name) == "rumor" else "News site") if name in types else "Other"
        feed = by_name.get(name)
        if feed is None:
            state, items, error = ("Not checked yet", "st-dry"), "n/a", "n/a"
        elif feed["ok"]:
            state, items, error = ("OK", "st-ok"), str(feed["items"]), "No error"
        else:
            state, items, error = ("Failed", "st-fail"), str(feed["items"]), feed["error"] or "Unknown problem."
        rows.append(
            f'<tr><td class="name">{esc(name)}</td><td>{esc(kind)}</td>'
            f'<td><span class="tag {state[1]}">{esc(state[0])}</span></td>'
            f'<td>{esc(items)}</td><td class="muted">{esc(error)}</td></tr>'
        )
    if not rows:
        rows = ['<tr class="none"><td colspan="5" class="empty-cell">No feeds configured.</td></tr>']
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Feed</th><th>Type</th><th>Last run</th><th>Items</th><th>Last error</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def history_panel(runs: list[dict]) -> str:
    rows = []
    for run in runs:
        when = show_time(parse_time(run["started_at"]))
        mode = MODE_NAMES.get(run["mode"], run["mode"])
        cells = [
            esc(when), esc(mode), esc(run["articles"]), esc(run["in_window"]), esc(run["passed_rules"]),
            esc(run["alerts_ready"]), esc(run["alerts_sent"]), esc(run["held"]),
            esc(run["rejected"]), esc(run["feeds_failed"]),
        ]
        rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    if not rows:
        rows = ['<tr class="none"><td colspan="10" class="empty-cell">No runs recorded yet.</td></tr>']
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>When (Asia/Manila)</th><th>Mode</th><th>Articles read</th><th>In time window</th>"
        "<th>Passed free rules</th><th>Alerts ready</th><th>Sent to Slack</th><th>Waiting</th>"
        "<th>Rejected</th><th>Feeds failed</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def project_command(action_args: str, folder_arg: str) -> str:
    """A full PowerShell command that starts by going to the project folder."""
    return f'cd "{ROOT}"; .venv\\Scripts\\python.exe src\\review.py {action_args} {folder_arg}'


def review_controls(name: str, status: str) -> str:
    """Approve, reject and log-as-posted controls. The page calls the review server when it is open over
    http. Opened as a file, the buttons copy the full PowerShell command with the typed name or reason."""
    folder_arg = f"output\\carousels\\{name}"
    controls = []
    if status in ("draft", "waiting_for_david", "approved"):
        base = project_command("--approve", folder_arg)
        controls.append(
            f'<button type="button" class="act" data-action="approve" data-folder="{esc(name)}" '
            f'data-base="{esc(base)}">Approve</button>'
        )
    base_reject = project_command("--reject", folder_arg)
    controls.append(
        '<span class="review-group">'
        '<input class="reason" type="text" maxlength="200" placeholder="Reason to reject" aria-label="Reason to reject">'
        f'<button type="button" class="act secondary" data-action="reject" data-folder="{esc(name)}" '
        f'data-base="{esc(base_reject)}">Reject</button></span>'
    )
    if status in ("approved", "posted"):
        base_post = project_command("--posted", folder_arg)
        options_html = "".join(f'<option value="{esc(key)}">{esc(label)}</option>' for key, label in REVIEW_ACCOUNTS)
        controls.append(
            '<span class="review-group">'
            f'<select class="account" aria-label="Account the post went to">{options_html}</select>'
            '<input class="post-url" type="url" maxlength="400" placeholder="https://link-to-the-post" '
            'aria-label="Link to the post">'
            f'<button type="button" class="act secondary" data-action="posted" data-folder="{esc(name)}" '
            f'data-base="{esc(base_post)}">Log as posted</button></span>'
        )
    return f'<div class="review">{"".join(controls)}</div>'


def download_link(label: str, file_href: str | None, live_href: str | None, mode: str, note: str,
                  primary: bool = False) -> str:
    """A download button. Through the review server it uses live_href (a real download, logged). As a file or in
    David's copy it links to the prebuilt file; with no prebuilt file it explains how to get one."""
    cls = "btn small primary" if primary else "btn small"
    live_attr = f' data-live-href="{esc(live_href)}"' if (live_href and mode == "local") else ""
    if file_href:
        return (f'<a class="{cls}" href="{esc(file_href)}" download{live_attr}>{icon("download")}'
                f'<span>{esc(label)}</span></a>')
    return (f'<a class="{cls}" href="#" aria-disabled="true" title="{esc(note)}"{live_attr}>{icon("download")}'
            f'<span>{esc(label)}</span></a>')


def caption_boxes(card_: dict) -> str:
    boxes = []
    for key, label, _ in downloads.ACCOUNTS:
        text = card_.get("captions", {}).get(key)
        if text is None:
            continue
        boxes.append(
            '<div class="box"><div class="box-top">'
            f'<h3>{esc(label)}</h3>'
            f'<button type="button" class="btn small copy" data-kind="caption" data-copy="{esc(text)}">Copy</button>'
            f'</div><p class="cap">{esc(text)}</p></div>')
    return "".join(boxes)


def carousel_card(card: dict, mode: str = "local", where: str = "") -> str:
    """One carousel. `where` keeps the element id and the slide viewer group apart when the same carousel is also
    shown on the Needs your attention page. In David's read only copy the review area shows the status badge only."""
    name = card["name"]
    group = f"lb-{name}{where}"
    base = card.get("base") or f"../output/carousels/{name}"
    build = card["build"]
    title = display_text(build.get("title") or name)
    state, state_class = _carousel_state(card)
    is_sample = card.get("kind") == "sample"
    is_preview = card.get("kind") == "preview"
    slide_names = card.get("slide_names", {})
    views = card.get("views") or {}  # David's copy may show the same slide as a smaller JPEG; downloads stay full PNG
    thumbs = []
    no_image = slides_without_image(card)
    for number, slide in enumerate(card["slides"], 1):
        src = f"{base}/{slide}"
        view = views.get(slide, src)
        file_name = slide_names.get(slide, slide)
        single = download_link(
            "PNG", src, f"/api/download/slide/{name}/{slide}", mode, "This slide is not saved yet.")
        thumbs.append(
            '<div>'
            f'<button type="button" class="slide" data-lb="{esc(group)}" data-src="{esc(view)}" '
            f'data-title="{esc(title)}" data-alt="Slide {number}: {esc(file_name)}" aria-label="Enlarge slide {number}">'
            f'<span class="thumb"><img src="{esc(view)}" alt="Slide {number}" loading="lazy" data-fb>'
            '<span class="fb">Image not found</span></span></button>'
            f'<span class="slide-n">{number:02d} {single}</span>'
            + ('<span class="tag st-fail no-image">NO IMAGE</span>' if number in no_image else '')
            + '</div>')
    strip = (f'<div class="thumbs">{"".join(thumbs)}</div>' if thumbs
             else '<p class="no-slides">No slides rendered yet.</p>')
    removed = build.get("removed") or []
    missing = build.get("missing") or []
    facts = f"{build.get('confirmed', 'n/a')} confirmed, {build.get('removed_count', 'n/a')} removed as not confirmed"
    fact_box = (
        '<div class="box"><h3>Fact check</h3><dl class="facts">'
        f"<dt>Facts</dt><dd>{esc(facts)}</dd>"
        f"<dt>Removed</dt><dd>{esc('; '.join(removed) or 'none')}</dd>"
        f"<dt>Missing images</dt><dd>{esc(', '.join(missing) or 'none')}</dd>"
        f"<dt>Design check</dt><dd>{esc(build.get('design_summary', 'not run'))}</dd>"
        "</dl></div>")
    links = "".join(
        f'<li>{esc(what)}: <a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(url)}</a></li>'
        for what, url in card.get("links", []) if safe_url(url)) or "<li>No official link recorded.</li>"
    placed = ", ".join(build.get("placed") or []) or "none"
    source_box = (f'<div class="box"><h3>Sources and image credits</h3><ul>{links}</ul>'
                  f'<p class="muted small">Images on the slides ({esc(placed)}) are official product images and demo '
                  'video frames from the brand\'s own pages. Nothing is AI generated.</p></div>')
    zip_label = "Download all slides (ZIP)"
    zip_href = f"{base}/{card['zip']}" if card.get("zip") else None
    zip_note = ("The zip is made by the next carousel build. Run .venv\\Scripts\\python.exe src\\downloads.py --all, "
                "or open Open Review Dashboard to download it now.") if mode == "local" else "Not included in this copy."
    downloads_box = (
        '<div class="box"><h3>Downloads</h3><div class="dl-row">'
        + download_link(zip_label, zip_href, f"/api/download/carousel/{name}", mode, zip_note, primary=True)
        + '</div><p class="muted small">Slides named in order (01-cover.png ...), one caption file per account and '
        'sources.txt. Single slides: the PNG link under each slide.</p></div>')
    if is_sample:
        actions = ('<div class="sample-banner">Samples are for checking the layout. They can\'t be approved or posted.'
                   '</div>')
    elif is_preview:
        actions = ('<div class="sample-banner">Preview made from a written plan. It has not been sent for approval yet, '
                   'so it can\'t be approved or posted from here.</div>')
    elif mode == "share":
        # Read only: where the approve, reject and posted controls are on Kint's page, only the status badge.
        actions = (f'<div class="review-area"><div class="review"><span class="tag {state_class}">{esc(state)}</span>'
                   '</div></div>')
    else:
        folder_arg = f"output\\carousels\\{name}"
        copy_commands = [
            ("Copy approve command", project_command("--approve", folder_arg) + ' --by "Name"'),
            ("Copy reject command", project_command("--reject", folder_arg) + ' --reason "..."'),
            ("Copy posted command", project_command("--posted", folder_arg)
             + ' --account tpm-facebook --url "PASTE LINK"'),
        ]
        copies = "".join(
            f'<button type="button" class="btn small copy" data-kind="command" data-copy="{esc(cmd)}">{esc(label)}'
            '</button>'
            for label, cmd in copy_commands
        )
        actions = ('<div class="review-area">' + review_controls(name, card["status"])
                   + f'<details class="copy-row"><summary>PowerShell commands</summary>{copies}</details></div>')
    kind_label = "Sample" if is_sample else "Preview" if is_preview else "Draft"
    sample_tag = ('<span class="tag tag-sample">SAMPLE</span>' if is_sample
                  else '<span class="tag tag-sample">PREVIEW</span>' if is_preview else "")
    cover = views.get(card["slides"][0], f"{base}/{card['slides'][0]}") if card["slides"] else ""
    no_image_chip = ""
    if no_image:
        listed = ", ".join(str(n) for n in no_image)
        no_image_chip = (f'<span class="tag st-fail no-image" title="These slides have no official image">'
                         f'No official image on slide{"s" if len(no_image) > 1 else ""} {esc(listed)}</span>')
    return (
        f'<article class="carousel-card" id="car-{esc(name)}{esc(where)}" '
        f'data-kind="{esc(card.get("kind", "draft"))}" data-status="{esc(card["status"])}" '
        f'data-chip="{esc(chip_key(card))}">'
        f'<div class="card-head"><h2 class="story-title">{esc(title)}</h2>'
        f'<div class="chips">{sample_tag}<span class="tag {state_class}">{esc(state)}</span>{no_image_chip}</div></div>'
        f'<p class="meta">{esc(kind_label)}: {esc(name)}</p>'
        f'<div class="car-body"><div><div class="strip-label">Cover</div>'
        + (f'<button type="button" class="slide" data-lb="{esc(group)}-c" data-src="{esc(cover)}" '
           f'data-title="{esc(title)}" aria-label="Enlarge the cover"><span class="thumb">'
           f'<img src="{esc(cover)}" alt="Cover" loading="lazy" data-fb>'
           '<span class="fb">Image not found</span></span></button>' if card["slides"]
           else '<p class="no-slides">No cover yet.</p>')
        + f'</div><div class="car-right"><div class="strip-label">All slides, click to enlarge</div>{strip}'
        f'{downloads_box}</div></div>'
        f'<div class="car-cols">{caption_boxes(card)}{fact_box}{source_box}</div>'
        f"{actions}"
        "</article>"
    )


def carousels_panel(cards: list[dict], mode: str = "local", approved_href: str | None = None) -> str:
    if not cards:
        return (
            '<div class="panel empty carousel"><h2>Carousels</h2>'
            "<p>Coming in Phase 2: ready-to-post slides and captions will appear here.</p></div>"
        )
    approved = sum(1 for c in cards if is_real(c) and c["status"] in ("approved", "posted"))
    note = ("Every approved carousel in one zip. Through Open Review Dashboard it is made on the spot."
            if mode == "local" else "Not included in this copy.")
    all_button = download_link(f"Download all approved carousels ({approved})", approved_href,
                               "/api/download/approved", mode, note, primary=False)
    counts: dict[str, int] = {}
    for c in cards:
        counts[chip_key(c)] = counts.get(chip_key(c), 0) + 1
    options = "".join(
        f'<option value="{key}"{" selected" if key == "all" else ""}>{esc(label)} ({counts.get(key, 0) if key != "all" else len(cards)})</option>'
        for key, label in CAROUSEL_FILTERS)
    kinds = (
        '<div class="panel"><div class="toolbar"><label class="muted" for="carousel-kind">Show</label>'
        f'<select id="carousel-kind" aria-label="Show carousels by status">{options}</select>'
        f'<span class="count-note">{all_button}</span></div></div>'
    )
    body, group = [], None
    for c in cards:
        if c["kind"] != group and c["kind"] in GROUP_TITLES:
            body.append(f'<h2 class="section-title car-group" data-group="{c["kind"]}">{esc(GROUP_TITLES[c["kind"]])}</h2>')
        group = c["kind"]
        body.append(carousel_card(c, mode))
    return kinds + '<div id="carousel-list" class="car-list">' + "".join(body) + "</div>"


def coverage_panel(stories: list[dict], now: datetime) -> str:
    """Every sent official story and its carousel, or the reason it has none."""
    rows = []
    for story in stories:
        if not story.get("official_sent"):
            continue
        reason, cls = coverage_reason(story, now)
        rows.append(
            f'<tr class="cov"><td class="name">{esc(display_text(story["title"]))}</td>'
            f'<td class="when">{esc(show_time(story["sent_at"] or story["first_seen"]))}</td>'
            f'<td><span class="tag {cls}">{esc(display_text(reason))}</span></td></tr>')
    if not rows:
        return ""
    body = ('<div class="table-wrap"><table><thead><tr><th>Official story sent to Slack</th><th>Sent</th>'
            f'<th>Carousel</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    return panel("Every official story and its carousel", body, f"{len(rows)} stories")


# ---------- rendering: pages ----------

def watcher_state(latest: dict | None, now: datetime) -> tuple[str, str]:
    """(words, chip class) saying whether the watcher looks alive."""
    if latest is None:
        return "No check yet", "st-dry"
    finished = parse_time(latest["finished_at"]) or parse_time(latest["started_at"])
    if finished and now - finished > timedelta(hours=HEALTHY_HOURS):
        hours = int((now - finished).total_seconds() // 3600)
        return f"Late: last check {hours} hours ago", "st-fail"
    if latest["feeds_ok"] == 0 and latest["feeds_failed"] > 0:
        return "Feeds failing", "st-fail"
    if latest["feeds_failed"]:
        return "Running, some feeds failed", "st-held"
    return "Running normally", "st-ok"


def next_check_text(latest: dict | None, next_run: datetime | None, now: datetime) -> str:
    if next_run is not None:
        return f"{show_time(next_run)} (Asia/Manila)"
    if latest is not None:
        started = parse_time(latest["started_at"])
        if started:
            guess = started + timedelta(hours=1)
            while guess < now:
                guess += timedelta(hours=1)
            return f"About {show_time(guess)} (estimated)"
    return "Not known yet"


def attention_items(cards: list[dict], stories: list[dict], latest_feeds: list[dict], mode: str) -> list[tuple]:
    """(icon colour, title, note, go to page, target id) for everything that needs a person."""
    real = [c for c in cards if is_real(c)]
    items = []
    for c in real:
        title = display_text(c["build"].get("title") or c["name"])
        if c["status"] == "waiting_for_david":
            items.append(("amber", f"Waiting for David: {title}", "Passed the fact and design checks. "
                          + ("Tell Kint to approve or reject it." if mode == "share"
                             else "Approve or reject it on the Carousels page."), "carousels", f"car-{c['name']}"))
        elif c["status"] == "approved":
            items.append(("green", f"Approved, post it by hand: {title}", "Post in Meta Business Suite, then log "
                          "the post with its link.", "carousels", f"car-{c['name']}"))
        elif c["status"] == "draft":
            items.append(("red", f"Draft needs a fix: {title}", c["build"].get("design_summary")
                          or "Check factcheck.md in its folder, then rebuild it.", "carousels", f"car-{c['name']}"))
    held = [s for s in stories if s["status"] == runlog.HELD]
    if held:
        items.append(("blue", f"{len(held)} rumors waiting for a 2nd source",
                      "Nothing to do: each one is sent when a second site reports it.", "stories", ""))
    missing = [s for s in stories if s.get("official_sent") and not s.get("carousel")
               and s.get("build_row") and s["build_row"]["status"] == "failed"]
    if missing:
        items.append(("red", f"{len(missing)} official stories have no carousel",
                      "Each reason is on the Carousels page, under Every official story and its carousel.",
                      "carousels", ""))
    for_kint = [s for s in stories if s.get("official_sent") and not s.get("carousel")
                and s.get("build_row") and s["build_row"]["status"] == "needs_kint"]
    if for_kint:
        items.append(("blue", f"{len(for_kint)} official stories waiting for a carousel",
                      "Nothing to do here: each one is made by hand from the official page, and Slack says when it is "
                      "ready for approval.", "carousels", ""))
    for feed in latest_feeds:
        if not feed["ok"]:
            items.append(("red", f"Feed failed: {feed['feed']}", feed["error"] or "Unknown problem.", "sources", ""))
    return items


def attention_list(items: list[tuple]) -> str:
    if not items:
        return ('<div class="panel"><div class="all-clear"><span class="att-ic green">' + icon("check")
                + "</span><div>Nothing needs you right now.</div></div></div>")
    rows = "".join(
        f'<li><span class="att-ic {colour}">{icon("attention" if colour in ("red", "amber") else "check")}</span>'
        f'<div class="att-text"><div class="att-title">{esc(display_text(title))}</div>'
        f'<div class="att-note">{esc(display_text(note))}</div></div>'
        f'<button type="button" class="btn small" data-go="{esc(go)}" data-target="{esc(target)}">Open</button></li>'
        for colour, title, note, go, target in items)
    return f'<div class="panel"><ul class="attention">{rows}</ul></div>'


def attention_panel(cards: list[dict], latest_feeds: list[dict], stories: list[dict] | None = None,
                    mode: str = "local") -> str:
    items = attention_items(cards, stories or [], latest_feeds, mode)
    waiting = [c for c in cards if is_real(c) and c["status"] in ("waiting_for_david", "draft", "approved")]
    parts = [attention_list(items)]
    if waiting:
        parts.append('<h2 class="section-title">Carousel drafts to review</h2>'
                     + "".join(carousel_card(c, mode, where="-review") for c in waiting))
    else:
        parts.append('<div class="panel empty"><p>No carousel drafts are waiting for review.</p></div>')
    failed = [f for f in latest_feeds if not f["ok"]]
    if failed:
        items_html = "".join(f"<li><strong>{esc(f['feed'])}</strong>: {esc(f['error'] or 'Unknown problem.')}</li>"
                             for f in failed)
        parts.append(panel("Feeds that failed in the last run",
                           f'<div class="panel-body"><ul class="src-list">{items_html}</ul></div>'))
    return "".join(parts)


def pipeline_panel(stories: list[dict]) -> str:
    counts = {key: 0 for key, _, _ in STAGES}
    for story in stories:
        if story["stage"] in counts:
            counts[story["stage"]] += 1
    boxes = "".join(
        f'<li><button type="button" class="stage-box{" is-wait" if key == "waiting" and counts[key] else ""}" '
        f'data-go="stories" data-stage="{esc(key)}"><span class="stage-num">{n}</span>'
        f'<span class="stage-name">{esc(name)}</span><span class="stage-count">{counts[key]}</span>'
        f'<span class="stage-hint">{esc(hint)}</span></button></li>'
        for n, (key, name, hint) in enumerate(STAGES, 1))
    out = sum(1 for s in stories if s["stage"] == "out")
    return panel("Pipeline: where every story is now",
                 f'<div class="panel-body"><ol class="flow">{boxes}</ol>'
                 f'<p class="muted small" style="margin-top:16px">{out} more were not taken forward (skipped by the '
                 'free rules, or judged not relevant). Click a stage to see its stories.</p></div>')


def activity_counts(events: list[dict], now: datetime) -> str:
    week = activity.week_counts(events, now)
    return "".join([
        card("Checks run", week["checks"], "Last 7 days"),
        card("Alerts sent", week["alerts"], "Last 7 days, to Slack"),
        card("Carousels built", week["carousels"], "Last 7 days"),
        card("Approved", week["approved"], "Last 7 days"),
        card("Posted", week["posted"], "Last 7 days, by hand"),
        card("Downloads", week["downloads"], "Last 7 days"),
    ])


def activity_panel(events: list[dict], now: datetime) -> str:
    rows = []
    for event in events[:ACTIVITY_ROWS]:
        kind = activity.TYPES.get(event["type"], event["type"])
        text = display_text(" ".join([kind, event["outcome"], event["details"], event["who"]])).lower()
        outcome = event["outcome"]
        cls = ("st-fail" if any(w in outcome for w in ("fail", "rejected", "no feed"))
               else "st-held" if "waiting" in outcome or "some" in outcome else "st-ok")
        rows.append(
            f'<tr class="ev" data-type="{esc(event["type"])}" data-ts="{int(event["at"].timestamp() * 1000)}" '
            f'data-text="{esc(text)}"><td class="when">{esc(show_time(event["at"]))}</td><td>{esc(kind)}</td>'
            f'<td><span class="tag {cls}">{esc(outcome.replace("_", " "))}</span></td>'
            f'<td>{esc(display_text(event["details"]))}</td><td>{esc(event["who"])}</td></tr>')
    type_options = '<option value="">All types</option>' + "".join(
        f'<option value="{esc(key)}">{esc(name)}</option>' for key, name in activity.TYPES.items())
    toolbar = (
        '<div class="toolbar">'
        '<input id="a-search" type="search" placeholder="Search the activity" aria-label="Search the activity">'
        f'<select id="a-type" aria-label="Type">{type_options}</select>'
        '<select id="a-range" aria-label="Date range"><option value="all">All time</option>'
        '<option value="7d">Last 7 days</option><option value="24h">Last 24 hours</option></select>'
        '<span id="a-count" class="count-note"></span></div>')
    if not rows:
        table = '<div class="empty">No activity recorded yet. The next check adds the first row.</div>'
    else:
        table = ('<div class="table-wrap"><table id="activity-table"><thead><tr><th>When (Asia/Manila)</th><th>Type</th>'
                 '<th>Outcome</th><th>Details</th><th>Who</th></tr></thead>'
                 f'<tbody id="activity-list">{"".join(rows)}</tbody></table></div>')
    return (f'<section class="cards">{activity_counts(events, now)}</section>'
            f'<div class="panel">{toolbar}{table}</div>')


def sources_panel(feeds_cfg: list[tuple[str, str]], latest_feeds: list[dict], rules: dict | None) -> str:
    brands = sorted((rules or {}).get("brands", {}).keys())
    software = (rules or {}).get("software_words", [])
    brand_text = ", ".join(esc(b) for b in brands) or "none configured"
    software_text = ", ".join(esc(s) for s in software) or "none configured"
    return (
        panel("Feed health", feeds_panel(feeds_cfg, latest_feeds), f"{len(feeds_cfg)} feeds")
        + panel("Brands the watcher knows", f'<div class="panel-body"><p>{brand_text}</p></div>')
        + panel("Editing software the watcher knows", f'<div class="panel-body"><p>{software_text}</p>'
                '<p class="muted">Adobe Photoshop, Lightroom, Camera Raw, Bridge and Firefly (photo editing) are '
                'checked too.</p></div>')
    )


HOW_IT_WORKS = [
    "Once an hour, the watcher reads the photo news feeds listed under Sources.",
    "It keeps only stories published in the last 72 hours that name a known brand or editing software.",
    "Rumors are sent to Slack only after a second site reports them. Official launches are sent at once.",
    "After an official alert, the carousel is made by hand from the brand's own page. It is first built as a preview "
    "that nobody is asked to approve.",
    "Every fact on it is checked against the brand's own page, word for word. Claims that are not confirmed are "
    "removed. Every image is a real official image of that feature.",
    "Kint reviews the carousel. It is sent to David only when Kint says so, and Slack says when one is ready for "
    "approval. Kint approves or rejects it here; David approves by telling Kint.",
    "After approval, Kint posts by hand in Meta Business Suite, then logs it here with the account and link.",
    "If no feed works for two runs in a row, or none has worked for 6 hours, one health message is sent to Slack a day.",
]
FLOW_NODES = [
    ("clock", "Hourly check", "The cloud reads the photo news and rumor sites every hour.", False),
    ("send", "Slack alert", "Official launches at once. A rumor only after a second site reports it.", False),
    ("image", "Carousel", "Made by hand from the brand's own page, with real official product images only. "
     "Built as a preview first.", False),
    ("check", "Fact check", "Every claim is checked against the official text. Anything unconfirmed is removed.",
     False),
    ("user", "Kint reviews, David approves", "Sent to David only when Kint says so. Nothing moves without a yes.",
     True),
    ("share", "Posted by hand", "Kint posts in Meta Business Suite, then logs the link here.", True),
    ("activity", "Tracked", "Every step is written to the Activity page with its time.", False),
    ("lock", "Never automatic", "Nothing is ever posted by the system. David's personal Instagram is never used.",
     False),
]
RULES = [
    "Nothing is auto-posted to social media. Posting is always by hand, after David approves.",
    "David's personal Instagram is blocked in the code and can never be logged.",
    "Facts come only from the brand's own page. A claim the page does not support is left out.",
    "Slides use real official product images or demo video frames. Nothing is AI generated.",
    "Only TPM Facebook, TPM Instagram and David Molnar's Facebook are used.",
    "No secret (the Slack address) is ever written into the page, the downloads or the copy for David.",
]


def how_panel() -> str:
    nodes = "".join(
        f'<div class="node{" human" if human else ""}"><span class="nic">{icon(name)}</span>'
        f'<h3>{esc(title)}</h3><p>{esc(text)}</p></div>' for name, title, text, human in FLOW_NODES)
    steps = "".join(f"<li><p>{esc(line)}</p></li>" for line in HOW_IT_WORKS)
    rules = "".join(f'<li>{icon("check")}<span>{esc(rule)}</span></li>' for rule in RULES)
    return (f'<div class="nodes">{nodes}</div>'
            + panel("The steps in plain words", f'<ol class="steps">{steps}</ol>')
            + f'<h2 class="section-title">The rules that never change</h2><ul class="rules">{rules}</ul>')


def start_panel(mode: str, counts: dict) -> str:
    who = "David" if mode == "share" else "you"
    lines = [
        ("What it is", "A cloud watcher that reads the photo news every hour and sends the real launches to Slack. "
                       "Each official launch becomes a ready to post carousel for TPM, made from the official page."),
        ("What is checked", "Every fact on a carousel comes from the brand's own page and is checked before anyone sees "
                            "it. Images are real official product images. Nothing is AI generated."),
        ("What needs " + who, "Carousels marked Waiting for David. "
         + ("Look at the slides and captions on the Carousels page, then tell Kint yes or no."
            if mode == "share" else "Open the Carousels page to approve or reject them.")),
        ("What never happens", "Nothing is posted automatically. Kint posts by hand in Meta Business Suite after "
                               "David approves. David's personal Instagram is never used."),
    ]
    blocks = "".join(f'<div class="node"><h3>{esc(t)}</h3><p>{esc(p)}</p></div>' for t, p in lines)
    waiting = counts.get("waiting_david", 0)
    head = ("Start here: the TPM photo news system in one minute" if mode == "share"
            else "Start here: what this system does")
    note = (f"{SHARE_NOTE} " if mode == "share" else "") + (
        f"Right now {waiting} carousel{'s are' if waiting != 1 else ' is'} waiting for David.")
    return (f'<div class="start-hero"><h1>{esc(head)}</h1><p>{esc(note)}</p>'
            '<p><button type="button" class="btn primary" data-go="carousels">See the carousels</button> '
            '<button type="button" class="btn" data-go="overview">See the overview</button></p></div>'
            f'<div class="nodes">{blocks}</div>' + how_panel())


def intro_panel(items: list[tuple], mode: str) -> str:
    todo = len(items)
    return (
        '<div class="intro"><div><h2>Photo news in, ready to post carousels out</h2>'
        '<p>Every hour the cloud reads the photo news and sends official launches to Slack. Each carousel is made from '
        'the brand\'s own page, fact checked, reviewed by Kint, and sent to David only when Kint says so. Nothing is '
        'posted automatically.</p><ol>'
        '<li><b>1</b><span>Hourly check of the news and rumor sites</span></li>'
        '<li><b>2</b><span>Slack alert for official launches (rumors need 2 sites)</span></li>'
        '<li><b>3</b><span>Carousel made from the official page and fact checked</span></li>'
        '<li><b>4</b><span>Kint reviews, David approves, then Kint posts by hand</span></li></ol></div>'
        f'<div class="todo"><h3>Needs attention now</h3><div class="big">{todo}</div>'
        f'<p class="muted">{"item" if todo == 1 else "items"} on the Needs your attention page.</p>'
        '<p><button type="button" class="btn primary" data-go="attention">Open the list</button></p></div></div>')


def render_page(data: dict, stories: list[dict], numbers: dict,
                feeds_cfg: list[tuple[str, str]], now: datetime, carousels: list[dict] | None = None,
                rules: dict | None = None, events: list[dict] | None = None, mode: str = "local",
                next_run: datetime | None = None, approved_href: str | None = None,
                fonts_dir: Path | None = None) -> str:
    runs = data["runs"]
    latest = runs[0] if runs else None
    if latest:
        last_when = show_time(parse_time(latest["finished_at"]) or parse_time(latest["started_at"]))
        run_mode = MODE_NAMES.get(latest["mode"], latest["mode"])
        last_text = f"{last_when} (Asia/Manila), {run_mode.lower()} run"
        run_note = f"{run_mode} run, {last_when}"
        feed_value = f"{latest['feeds_ok']} / {latest['feeds_failed']}"
        articles = latest["articles"]
    else:
        last_text = "no check recorded yet"
        run_note, feed_value, articles = "No check recorded yet", "n/a", "n/a"
    all_cards = carousels or []
    events = events or []
    link_carousels(stories, all_cards, data.get("builds", []))
    for story in stories:
        story["stage"] = story_stage(story)
        story["official_sent"] = story["status"] == runlog.ALERTED and story["label"] == classify.OFFICIAL
        story["now"] = now
    real = [c for c in all_cards if is_real(c)]
    counts = {
        "drafted": len(real),
        "waiting_david": sum(1 for c in real if c["status"] == "waiting_for_david"),
        "posted": sum(1 for c in real if c["status"] == "posted"),
    }
    items = attention_items(all_cards, stories, data["feeds"], mode)

    undated_note = (
        f"{numbers['undated']} sent before run history began (no date)"
        if numbers["undated"] else "Sent to Slack"
    )
    news_cards = "".join([
        card("Articles read, last run", articles, run_note),
        card("Sent to Slack today", numbers["today"], "Asia/Manila calendar day"),
        card("Sent to Slack, last 7 days", numbers["week"], undated_note),
        card("Waiting for a 2nd source", numbers["waiting"], "Rumors held until a second site reports them"),
        card("Rejected: not relevant", numbers["rejected"], "Judged not relevant, all stored stories"),
        card("Skipped", numbers["skipped"], "Not news under the current rules"),
        card("Feeds OK / failed", feed_value, "Last run"),
    ])
    carousel_cards = "".join([
        card("Carousels drafted", counts["drafted"], "Real drafts, samples not counted"),
        card("Waiting for David", counts["waiting_david"], "Passed the fact and design checks"),
        card("Posted", counts["posted"], "Posted by hand and logged"),
    ])
    state_text, state_class = watcher_state(latest, now)
    next_text = next_check_text(latest, next_run, now)

    pages = {
        "start": start_panel(mode, counts),
        "overview": (
            page_head("Overview", "What the watcher found, what it sent, and where every story is now.")
            + intro_panel(items, mode)
            + '<h2 class="section-title">News</h2>' + f'<section class="cards">{news_cards}</section>'
            + '<h2 class="section-title">Carousels</h2>' + f'<section class="cards">{carousel_cards}</section>'
            + '<h2 class="section-title">This week</h2>'
            + f'<section class="cards">{activity_counts(events, now)}</section>'
            + pipeline_panel(stories)
            + panel("Run history", history_panel(runs), f"last {HISTORY_ROWS} checks")
        ),
        "attention": (page_head("Needs your attention", "Carousels to review or post, rumors waiting for a second "
                                "site, and feeds that failed.")
                      + attention_panel(all_cards, data["feeds"], stories, mode)),
        "stories": (page_head("Stories", "Every story the watcher kept. Click a story for its summary, sources and "
                              "fact check.") + stories_panel(stories, mode)),
        "carousels": (page_head("Carousels", "Each carousel with its slides, captions for every account, fact check, "
                                "sources and downloads.")
                      + coverage_panel(stories, now) + carousels_panel(all_cards, mode, approved_href)),
        "activity": (page_head("Activity", "Every check, alert, carousel build, fact check, review, download and "
                               "export, with its time in Manila.") + activity_panel(events, now)),
        "sources": (page_head("Sources", "The feeds the watcher reads, how each did in the last check, and the "
                              "brands and software it knows.") + sources_panel(feeds_cfg, data["feeds"], rules)),
        "how": (page_head("How it works", "The whole system on one page.") + how_panel()),
    }
    home = "start" if mode == "share" else "overview"
    badges = {"attention": len(items), "carousels": counts["waiting_david"]}
    nav = "".join(
        f'<button type="button" data-nav="{key}" data-label="{esc(label)}"'
        f'{" aria-current=" + chr(34) + "page" + chr(34) if key == home else ""}>{icon(ico)}<span>{esc(label)}</span>'
        + (f'<span class="badge{" alert" if badges[key] else ""}">{badges[key]}</span>' if key in badges else "")
        + "</button>"
        for key, label, ico in PAGES)
    sections = "".join(
        f'<section class="page" data-page="{key}"{"" if key == home else " hidden"}>{pages[key]}</section>'
        for key, _, _ in PAGES)

    if mode == "share":
        controls = ""
        banner = f'<div class="banner" role="note">{icon("lock")}<span>{esc(SHARE_NOTE)}</span></div>'
        generated = f"Copy made {show_time(now)} (Asia/Manila). Read only: nothing here changes anything."
        side_note = "Read only copy for David. To approve a carousel, tell Kint."
        connect = "'none'"
    else:
        export_cmd = f'cd "{ROOT}"; .venv\\Scripts\\python.exe scripts\\export_share_pack.py'
        controls = (
            '<div class="who"><label for="reviewer">Your name, for approvals</label>'
            '<input id="reviewer" type="text" maxlength="60" placeholder="Type your name" autocomplete="name"></div>'
            f'<button type="button" class="btn primary" id="export-david" data-copy="{esc(export_cmd)}">'
            f'{icon("share")}<span>Export for David</span></button>')
        banner = ""
        generated = f"Generated {show_time(now)} (Asia/Manila). Rebuilt at the end of every run."
        side_note = "Nothing is posted automatically. Posting is by hand in Meta Business Suite after David approves."
        connect = "'self'"
    topbar = (
        f'<header class="topbar"><div class="crumb" id="crumb">{esc(dict((k, l) for k, l, _ in PAGES)[home])}</div>'
        f'<div class="stat"><span class="lbl">Last check</span><span class="val">{esc(last_text)}</span></div>'
        f'<div class="stat"><span class="lbl">Next check at</span><span class="val">{esc(next_text)}</span>'
        '<span class="sub">Next check: hourly while this PC is on</span></div>'
        f'<div class="stat"><span class="lbl">Watcher</span><span class="val"><span class="tag dot {state_class}">'
        f'{esc(state_text)}</span></span></div>{controls}</header>'
    )
    sidebar = (
        '<aside class="sidebar"><div class="brand">' + dashboard_assets.BRAND_MARK
        + '<div><div class="brand-name">TPM Photo News</div><div class="brand-sub">The Photo Mentorship</div></div></div>'
        f'<nav class="nav" aria-label="Sections">{nav}</nav>'
        f'<div class="side-foot"><strong>{icon("lock")}Posting stays manual</strong><span>{esc(side_note)}</span></div>'
        "</aside>"
    )
    overlays = (
        '<div id="scrim" class="scrim" hidden></div>'
        '<aside id="drawer" class="drawer" role="dialog" aria-modal="true" aria-label="Story details" hidden>'
        '<div class="drawer-head"><span>Story details</span>'
        '<button type="button" class="btn small" id="drawer-close">Close</button></div>'
        '<div id="drawer-body" class="drawer-body"></div></aside>'
        '<div id="lightbox" class="lightbox" role="dialog" aria-modal="true" aria-label="Slide viewer" hidden>'
        '<div class="lb-bar"><span id="lb-title" class="lb-title"></span><span id="lb-count"></span>'
        '<button type="button" class="btn small" id="lb-prev">Previous</button>'
        '<button type="button" class="btn small" id="lb-next">Next</button>'
        '<button type="button" class="btn small" id="lb-close">Close</button></div>'
        '<div id="lb-stage" class="lb-stage"></div></div>'
        '<div id="toast" class="toast" role="status" aria-live="polite" hidden></div>'
    )
    font_css = dashboard_assets.font_face_css(fonts_dir) if fonts_dir else ""
    # David's copy: kept out of search engines on the web host, and its script has no review, export or
    # command copy code at all (dashboard_assets.script_for).
    robots = "<meta name=\"robots\" content=\"noindex,nofollow\">" if mode == "share" else ""
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" + robots +
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; "
        f"script-src 'unsafe-inline'; connect-src {connect}; img-src data: file: 'self'; font-src data:; "
        "base-uri 'none'; form-action 'none'\">"
        "<title>TPM Photo News</title><style>" + font_css + dashboard_assets.CSS + "</style></head>"
        f'<body data-mode="{mode}" data-home="{home}"><div class="app">' + sidebar
        + '<div class="main">' + topbar + banner
        + f'<div class="content"><p class="generated">{esc(generated)}</p>{sections}</div></div></div>'
        + overlays + "<script>" + dashboard_assets.script_for(mode) + "</script></body></html>\n"
    )


# ---------- entry points ----------

def build_page(db_path=None, sources_path=None, rules_path=None, now=None, carousels_dir=None, samples_dir=None,
               activity_path=None, mode: str = "local", card_filter=None, base_for=None,
               approved_href: str | None = "auto", read_only: bool = False,
               previews_dir=None) -> tuple[str, list[dict]]:
    """(page HTML, the carousel cards on it). card_filter(card) keeps a card; base_for(card) gives its image folder.
    approved_href is the link of the "Download all approved carousels" button ("auto": the prebuilt zip, if any).
    read_only=True is David's copy: the same template as Kint's page, without any control or command."""
    if read_only:
        mode = "share"
    db_path = Path(db_path) if db_path is not None else ROOT / "data" / "seen.sqlite"
    sources_path = Path(sources_path) if sources_path is not None else ROOT / "config" / "sources.yaml"
    rules_path = Path(rules_path) if rules_path is not None else ROOT / "config" / "rules.yaml"
    if previews_dir is None and carousels_dir is None:
        previews_dir = ROOT / "output" / "plan-previews"  # a caller that names its own folders names the previews too
    carousels_dir = Path(carousels_dir) if carousels_dir is not None else ROOT / "output" / "carousels"
    samples_dir = Path(samples_dir) if samples_dir is not None else ROOT / "output" / "samples"
    now = now or datetime.now(timezone.utc)

    data = read_database(db_path)
    rules = load_rules(rules_path)
    stories = build_stories(data, rules)
    cards = read_carousels(carousels_dir, samples_dir, Path(previews_dir) if previews_dir is not None else None)
    if card_filter is not None:
        cards = [c for c in cards if card_filter(c)]
    if base_for is not None:
        for c in cards:
            c["base"] = base_for(c)
    if approved_href == "auto":
        approved_zip = carousels_dir / downloads.APPROVED_ZIP_NAME
        approved_href = f"../output/carousels/{downloads.APPROVED_ZIP_NAME}" if approved_zip.exists() else None
    events = activity.read_events(activity_path)
    try:
        next_run = read_next_run()
    except Exception:  # the next check time is a nice to have; the page is built without it
        next_run = None
    page = render_page(data, stories, summarize(stories, now), configured_feeds(sources_path), now, cards, rules,
                       events, mode, next_run, approved_href, ROOT / "assets" / "fonts")
    return page, cards


def write_dashboard(db_path=None, out_path=None, sources_path=None, rules_path=None, now=None,
                    carousels_dir=None, samples_dir=None, activity_path=None, previews_dir=None) -> Path:
    """Reads the data and writes the page. Paths default to the project folders."""
    out_path = Path(out_path) if out_path is not None else ROOT / "dashboard" / "index.html"
    page, _ = build_page(db_path, sources_path, rules_path, now, carousels_dir, samples_dir, activity_path,
                         previews_dir=previews_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp = out_path.with_name(out_path.name + ".tmp")
    temp.write_text(page, encoding="utf-8")
    os.replace(temp, out_path)  # swap in the finished file, so a half-written page is never opened
    return out_path


def main() -> int:
    path = write_dashboard()
    print(f"Dashboard written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
