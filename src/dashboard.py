"""Builds dashboard/index.html from the watcher's SQLite data, the carousel folders and the activity log.

The page is one static file with inline CSS, JS, icons and fonts (dashboard_assets.py). It needs no CDN and no network,
and it never contains the Slack webhook or any other secret. run.py rebuilds it at the end of every run.
To rebuild it alone:  python src\\dashboard.py

It is laid out like an app: a sidebar with the sections, a top bar with one short health line (last check, feeds,
next check), and one page per section, in the same order as the README: Carousels (the home page: the carousels to
review), Photo news (big brand stories of the last two weeks),
Inspiration (credited, link only reference photos), System (watcher and feed health) and How it works.
Run history, the activity log and hidden, rejected, skipped or practice run stories are not shown (their data is kept).

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
import inspiration
import runlog
import schedule_info
from dashboard_assets import icon

ROOT = Path(__file__).resolve().parent.parent
MANILA = timezone(timedelta(hours=8), "Asia/Manila")  # Manila has no daylight saving time.
RUNS_READ = 1  # only the latest check is shown (the health line); run history is not on the page
STORY_COLUMNS = (
    "id", "title", "brand", "first_seen", "last_alert_label", "dismissed",
    "claude_label", "skipped", "review_version",
)
REVIEW_ACCOUNTS = [("tpm-facebook", "TPM Facebook"), ("tpm-instagram", "TPM Instagram"),
                   ("david-facebook", "David Facebook")]
# The sidebar. The carousels to review come first: that is the home page of Kint's page and David's copy.
PAGES = [("review", "Carousels", "carousels"), ("news", "Photo news", "stories"),
         ("inspiration", "Inspiration", "image"), ("system", "System", "activity"),
         ("how", "How it works", "how")]
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
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (RUNS_READ,))]
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


def split_hidden(stories: list[dict], rules: dict | None) -> tuple[list[dict], list[dict]]:
    """Kint's big brand and photographer gates (rules.yaml big_brands and photo_relevance). A story that fails them is
    left off the page and David's copy. Nothing is deleted: the story stays in the watcher's data, and it shows again
    if the rules change. Returns (shown, hidden); each hidden story gets its reason in story["hidden"]."""
    shown, hidden = [], []
    by_hand = {int(n) for n in ((rules or {}).get("hidden_story_ids") or [])}
    for story in stories:
        if story.get("story_id") in by_hand:
            story["hidden"] = "Hidden by Kint (rules.yaml hidden_story_ids)"
            hidden.append(story)
            continue
        reason = classify.story_gate_problem(story.get("sources") or [], story.get("brand"), story.get("title") or "",
                                             rules) if rules else None
        if reason:
            story["hidden"] = reason
            hidden.append(story)
        else:
            shown.append(story)
    return shown, hidden


def apply_official_overrides(stories: list[dict], rules: dict | None) -> list[dict]:
    """A story Kint confirmed by hand (rules.yaml official_override_stories) shows as official, with the official
    pages as its only sources and the official headline; the rumor article it was first seen in is left off."""
    table = (rules or {}).get("official_override_stories") or {}
    for story in stories:
        entry = table.get(story.get("story_id")) if story.get("story_id") is not None else None
        if not isinstance(entry, dict) or not entry.get("official_urls"):
            continue
        name = story.get("brand") or "Official"
        story["sources"] = [{"source": f"{name} official", "link": url} for url in entry["official_urls"]]
        story["title"] = story["summary"] = entry.get("title") or story["title"]
        story["label"] = classify.OFFICIAL
        story["official_override"] = True
    return stories


def hide_cards(cards: list[dict], hidden: list[dict]) -> list[dict]:
    """Carousel and preview cards of hidden stories are left off the page too (their folders are kept)."""
    slugs = {folder_slug(story["title"]) for story in hidden if story.get("title")}
    return [c for c in cards if c.get("name", "")[11:] not in slugs]


def hide_events(events: list[dict], hidden: list[dict]) -> list[dict]:
    """Activity rows about hidden stories (their Slack alert, their carousel attempts) are left off the page too.
    The activity files are not changed."""
    keys = [story["title"].lower()[:40] for story in hidden if len(story.get("title") or "") >= 12]
    if not keys:
        return list(events or [])
    return [e for e in (events or []) if not any(k in " ".join(str(v) for v in e.values()).lower() for k in keys)]


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


# ---------- rendering: pieces ----------

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
    """One carousel as a gallery card: a big cover, the slide strip (click any slide to enlarge), the downloads,
    the captions with a copy button, and the fact check and sources folded away. In David's read only copy the
    review area shows the status badge only."""
    name = card["name"]
    group = f"lb-{name}{where}"
    base = card.get("base") or f"../output/carousels/{name}"
    build = card["build"]
    title = display_text(build.get("title") or name)
    state, state_class = _carousel_state(card)
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
            '<div class="tcell">'
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
    zip_href = f"{base}/{card['zip']}" if card.get("zip") else None
    zip_note = ("The zip is made by the next carousel build. Run .venv\\Scripts\\python.exe src\\downloads.py --all, "
                "or open Open Review Dashboard to download it now.") if mode == "local" else "Not included in this copy."
    zip_button = download_link("Download all slides (ZIP)", zip_href, f"/api/download/carousel/{name}", mode,
                               zip_note, primary=True)
    if is_preview:
        actions = ""  # the chip says it: a preview is not sent for approval, so it has no review controls
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
    cover = views.get(card["slides"][0], f"{base}/{card['slides'][0]}") if card["slides"] else ""
    no_image_chip = ""
    if no_image:
        listed = ", ".join(str(n) for n in no_image)
        no_image_chip = (f'<span class="tag st-fail no-image" title="These slides have no official image">'
                         f'No official image on slide{"s" if len(no_image) > 1 else ""} {esc(listed)}</span>')
    count = len(card["slides"])
    cover_html = (
        f'<button type="button" class="slide cover" data-lb="{esc(group)}-c" data-src="{esc(cover)}" '
        f'data-title="{esc(title)}" aria-label="Enlarge the cover"><span class="thumb">'
        f'<img src="{esc(cover)}" alt="Cover of {esc(title)}" loading="lazy" data-fb>'
        '<span class="fb">Image not found</span></span>'
        f'<span class="cover-badge">{icon("image")}{count} slides</span></button>' if card["slides"]
        else '<p class="no-slides">No cover yet.</p>')
    captions = caption_boxes(card)
    return (
        f'<article class="carousel-card" id="car-{esc(name)}{esc(where)}" '
        f'data-kind="{esc(card.get("kind", "draft"))}" data-status="{esc(card["status"])}" '
        f'data-chip="{esc(chip_key(card))}">'
        f'<div class="cc-cover">{cover_html}</div>'
        '<div class="cc-body">'
        f'<div class="cc-head"><div class="chips"><span class="tag {state_class}">{esc(state)}</span>{no_image_chip}'
        f'</div><h2 class="story-title">{esc(title)}</h2></div>'
        f'<div class="strip-label">All slides, click to enlarge</div>{strip}'
        f'<div class="dl-row">{zip_button}<span class="muted small">Slides in order, a caption file per account '
        'and sources.txt</span></div></div>'
        '<div class="cc-foot">'
        + (f'<details class="caps" open><summary>Captions, ready to copy</summary><div class="car-cols">{captions}'
           '</div></details>' if captions else "")
        + f'<details class="more"><summary>Fact check and sources</summary><div class="car-cols">{fact_box}'
        f'{source_box}</div></details>'
        f"{actions}</div>"
        "</article>"
    )


def carousels_panel(cards: list[dict], mode: str = "local", approved_href: str | None = None) -> str:
    cards = ready_cards(cards)
    if not cards:
        return empty_state("carousels", "No carousels to review right now",
                           "A new carousel shows here after an official big brand launch is made into slides.")
    approved = sum(1 for c in cards if is_real(c) and c["status"] in ("approved", "posted"))
    top = ""
    if approved:
        note = ("Every approved carousel in one zip. Through Open Review Dashboard it is made on the spot."
                if mode == "local" else "Not included in this copy.")
        top = ('<div class="toolbar">' + download_link(f"Download all approved carousels ({approved})", approved_href,
                                                        "/api/download/approved", mode, note) + "</div>")
    return top + '<div id="carousel-list" class="car-list">' + "".join(carousel_card(c, mode) for c in cards) + "</div>"


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


def sources_panel(feeds_cfg: list[tuple[str, str]], latest_feeds: list[dict], rules: dict | None) -> str:
    rules = rules or {}
    brands = sorted(rules.get("brands", {}).keys())
    software = rules.get("software_words", [])
    big = rules.get("big_brands") or []
    if big:
        # Kint's allowlist: only the big brands (and their editing software) are shown, the brands the watcher follows.
        allowed = {name.lower() for name in big}
        aliases = {alias.lower() for brand, names in rules.get("brands", {}).items() if brand.lower() in allowed
                   for alias in names}
        brands = list(big)
        software = [word for word in software if word.lower() in allowed or word.lower() in aliases]
    chips = "".join(f'<span class="pill p-brand">{esc(b)}</span>' for b in brands) or "none configured"
    software_text = ", ".join(esc(w) for w in software) or "none configured"
    return (
        panel("Feed health", feeds_panel(feeds_cfg, latest_feeds), f"{len(feeds_cfg)} feeds")
        + panel("Big photography brands the watcher follows", f'<div class="panel-body"><div class="chip-row">{chips}'
                f'</div><p class="muted small">Editing software: {software_text}.</p></div>')
    )


HEALTH_WORD = {"st-ok": "Healthy", "st-held": "Partly OK", "st-fail": "Needs a look", "st-dry": "Not started"}
NEWS_DAYS = 14  # Photo news shows the big brand stories of the last two weeks


def ready_cards(cards: list[dict]) -> list[dict]:
    """The carousels on the home page: real drafts and previews, never layout samples or rejected ones.
    Waiting for David first, then drafts, then previews, then approved and posted."""
    order = {"waiting_for_david": 0, "draft": 1, "preview": 2, "approved": 3, "posted": 4}
    keep = [c for c in cards if c.get("kind") != "sample" and c.get("status") != "rejected"]
    return sorted(keep, key=lambda c: order.get(chip_key(c), 5))


def recent_news(stories: list[dict], now: datetime, days: int = NEWS_DAYS) -> list[dict]:
    """Stories sent to Slack or waiting for a second site, seen in the last `days` days. Rejected, skipped,
    practice run and hidden stories are not news and are left out."""
    start = now - timedelta(days=days)
    keep = []
    for story in stories:
        if story["status"] not in (runlog.ALERTED, runlog.HELD) or story.get("story_id") is None:
            continue
        moment = story.get("sent_at") or story.get("first_seen")
        if moment and moment >= start:
            keep.append(story)
    floor = datetime.min.replace(tzinfo=timezone.utc)
    keep.sort(key=lambda s: s.get("sent_at") or s.get("first_seen") or floor, reverse=True)
    return keep


def stat_tile(icon_name: str, label: str, value, note: str, tone: str = "") -> str:
    return (f'<div class="tile{" " + tone if tone else ""}"><span class="tile-ic">{icon(icon_name)}</span>'
            f'<div><div class="tile-v">{esc(value)}</div><div class="tile-k">{esc(label)}</div>'
            f'<div class="tile-n">{esc(note)}</div></div></div>')


def empty_state(icon_name: str, title: str, text: str) -> str:
    return (f'<div class="empty-state"><span class="empty-ic">{icon(icon_name)}</span>'
            f'<h3>{esc(title)}</h3><p>{esc(text)}</p></div>')


def news_item(story: dict, now: datetime) -> str:
    links = source_links(story)
    first = next((safe_url(s.get("link")) for s in story["sources"] if safe_url(s.get("link"))), None)
    title = esc(display_text(story["title"]))
    title_html = (f'<a href="{esc(first)}" target="_blank" rel="noopener noreferrer">{title}</a>' if first
                  else f"<span>{title}</span>")
    moment = story.get("sent_at") or story.get("first_seen")
    when = show_time(moment) if moment else "Date not known"
    official = story["label"] == classify.OFFICIAL
    kind = '<span class="pill p-official">Official</span>' if official else '<span class="pill p-rumor">Rumor</span>'
    if story.get("official_override"):
        chips = '<span class="tag st-alert">Confirmed on the official page</span>'
    elif story["status"] == runlog.HELD:
        chips = '<span class="tag st-held">Waiting for a 2nd source</span>'
    else:
        chips = '<span class="tag st-alert">Sent to Slack</span>'
    card_ = story.get("carousel")
    if card_:
        state, cls = _carousel_state(card_)
        chips += f'<span class="tag {cls}">Carousel: {esc(state)}</span>'
    summary = display_text(story.get("summary") or "")
    summary_html = (f'<p class="ni-sum">{esc(first_sentence(summary, 180))}</p>'
                    if summary and title_key(summary) != title_key(story["title"]) else "")
    return (f'<li class="news-item"><div class="ni-main"><div class="ni-top">'
            f'<span class="pill p-brand">{esc(story.get("brand") or "Photo")}</span>{kind}'
            f'<span class="ni-when">{esc(when)}</span></div>'
            f'<h3 class="ni-title">{title_html}</h3>{summary_html}'
            f'<div class="ni-src">{icon("sources")}<span>{" ".join(links) or "No source link"}</span></div></div>'
            f'<div class="ni-side">{chips}</div></li>')


def news_panel(stories: list[dict], now: datetime) -> str:
    """The stories sent to Slack, newest first. Rumors still waiting for a second site are folded away below."""
    items = recent_news(stories, now)
    sent = [s for s in items if s["status"] == runlog.ALERTED or s.get("official_override")]
    held = [s for s in items if s["status"] == runlog.HELD and not s.get("official_override")]
    if not items:
        return empty_state("stories", "No big brand news in the last two weeks",
                           "New launches from the big photography brands show here as soon as the watcher finds them.")
    body = (f'<ul class="news-list">{"".join(news_item(s, now) for s in sent)}</ul>' if sent
            else empty_state("stories", "Nothing sent to Slack in the last two weeks",
                             "Official launches from the big photography brands show here when they are sent."))
    if held:
        body += (f'<details class="more held"><summary>Rumors waiting for a 2nd source ({len(held)})</summary>'
                 f'<ul class="news-list">{"".join(news_item(s, now) for s in held)}</ul></details>')
    return body


def short_time(moment: datetime | None, now: datetime) -> str:
    """11:08 PM for today, Nov 24, 11:08 PM for another day (Asia/Manila)."""
    if moment is None:
        return "not known"
    local = moment.astimezone(MANILA)
    clock = local.strftime("%I:%M %p").lstrip("0")
    return clock if local.date() == now.astimezone(MANILA).date() else f"{local.strftime('%b')} {local.day}, {clock}"


def health_line(latest: dict | None, next_run: datetime | None, now: datetime) -> tuple[str, str]:
    """(one short line, chip class): last check, feeds and next check, in Asia/Manila time."""
    _, cls = watcher_state(latest, now)
    if latest is None:
        return "No check recorded yet.", cls
    last = parse_time(latest["finished_at"]) or parse_time(latest["started_at"])
    total = latest["feeds_ok"] + latest["feeds_failed"]
    nxt = next_run
    if nxt is None:
        started = parse_time(latest["started_at"])
        if started:
            nxt = started + timedelta(hours=1)
            while nxt < now:
                nxt += timedelta(hours=1)
    text = f"Last check {short_time(last, now)}, {latest['feeds_ok']} of {total} feeds OK"
    if nxt is not None:
        text += f", next {short_time(nxt, now)}"
    return text + " (Asia/Manila)", cls


def system_panel(feeds_cfg: list[tuple[str, str]], latest: dict | None, latest_feeds: list[dict],
                 rules: dict | None, next_text: str, now: datetime) -> str:
    state, cls = watcher_state(latest, now)
    if latest:
        last = short_time(parse_time(latest["finished_at"]) or parse_time(latest["started_at"]), now)
        feeds = f"{latest['feeds_ok']} of {latest['feeds_ok'] + latest['feeds_failed']}"
        articles = latest["articles"]
    else:
        last, feeds, articles = "No check yet", "n/a", "n/a"
    tiles = "".join([
        stat_tile("clock", "Watcher", HEALTH_WORD.get(cls, "Check"), state, "ok" if cls == "st-ok" else "warn"),
        stat_tile("check", "Last check", last, f"{articles} articles read" if latest else "Asia/Manila"),
        stat_tile("sources", "Feeds OK", feeds, "In the last check"),
        stat_tile("send", "Next check", next_text, "Asia/Manila"),
    ])
    return (f'<section class="tiles">{tiles}</section>'
            + sources_panel(feeds_cfg, latest_feeds, rules))


HOW_IT_WORKS = [
    ("clock", "Hourly check", "The cloud reads the photo news and rumor sites every hour and keeps only big "
     "photography brand stories that matter to photographers."),
    ("send", "Slack alert", "Official launches are sent at once. A rumor is sent only after a second site reports it."),
    ("image", "Carousel", "Made by hand from the brand's own page with real official images, then fact checked "
     "word for word."),
    ("user", "Review and post", "Kint reviews it first. It is sent to David only when Kint says so. After David "
     "approves, Kint posts by hand in Meta Business Suite."),
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
    steps = "".join(
        f'<li class="step"><span class="step-n">{n}</span><span class="step-ic">{icon(name)}</span>'
        f'<h3>{esc(title)}</h3><p>{esc(text)}</p></li>'
        for n, (name, title, text) in enumerate(HOW_IT_WORKS, 1))
    rules = "".join(f'<li>{icon("check")}<span>{esc(rule)}</span></li>' for rule in RULES)
    return (f'<ol class="steps">{steps}</ol>'
            + panel("The rules that never change", f'<ul class="rules">{rules}</ul>'))


def render_page(data: dict, stories: list[dict], numbers: dict,
                feeds_cfg: list[tuple[str, str]], now: datetime, carousels: list[dict] | None = None,
                rules: dict | None = None, events: list[dict] | None = None, mode: str = "local",
                next_run: datetime | None = None, approved_href: str | None = None,
                fonts_dir: Path | None = None) -> str:
    """The whole page. Three things come first: the carousels to review, the recent big brand news, and one
    short line on the watcher's health. Run history, the activity log and hidden stories are not on the page
    (their data stays in the watcher's files)."""
    runs = data["runs"]
    latest = runs[0] if runs else None
    all_cards = carousels or []
    link_carousels(stories, all_cards, data.get("builds", []))
    for story in stories:
        story["official_sent"] = story["status"] == runlog.ALERTED and story["label"] == classify.OFFICIAL
    cards = ready_cards(all_cards)
    news = recent_news(stories, now)
    waiting = sum(1 for c in cards if c["status"] == "waiting_for_david")
    previews = sum(1 for c in cards if c.get("kind") == "preview")
    week = sum(1 for s in news if s["status"] == runlog.ALERTED
               and (s.get("sent_at") or s.get("first_seen")) >= now - timedelta(days=7))
    next_text = next_check_text(latest, next_run, now).replace(" (Asia/Manila)", "")
    if next_run is not None:
        next_text = short_time(next_run, now)
    health, health_cls = health_line(latest, next_run, now)
    state_text, _ = watcher_state(latest, now)

    if mode == "share":
        lead = "Look through the slides and captions, then tell Kint yes or no. Nothing here changes anything."
    else:
        lead = "Preview the slides, copy the captions, download, then approve or reject. Nothing is posted automatically."
    tiles = "".join([
        stat_tile("carousels", "Carousels ready", len(cards), f"{previews} previews" if previews else "To look at"),
        stat_tile("user", "Waiting for David", waiting, "Tell Kint yes or no" if mode == "share"
                  else "Sent to David by Kint"),
        stat_tile("stories", "Sent to Slack", week, "Big brand news, last 7 days"),
        stat_tile("clock", "Watcher", HEALTH_WORD.get(health_cls, "Check"), state_text,
                  "ok" if health_cls == "st-ok" else "warn"),
    ])
    pages = {
        "review": (page_head("Carousels to review", lead) + f'<section class="tiles">{tiles}</section>'
                   + carousels_panel(cards, mode, approved_href)),
        "news": (page_head("Photo news", "Big photography brand news from the last two weeks. Official launches go "
                           "to Slack at once; a rumor waits for a second site.") + news_panel(stories, now)),
        "inspiration": (page_head("Inspiration", "Standout photos from official sources, credited to the photographers, "
                                  "with the lesson and a TPM content idea. Links only, no images copied.")
                        + inspiration.panel()),
        "system": (page_head("System", "Is the watcher running, and are the news feeds working.")
                   + system_panel(feeds_cfg, latest, data["feeds"], rules, next_text, now)),
        "how": page_head("How it works", "From a photo news story to a carousel ready to post, in four steps.")
               + how_panel(),
    }
    home = "review"
    badges = {"review": len(cards), "news": sum(1 for s in news if s["status"] == runlog.ALERTED)}
    nav = "".join(
        f'<button type="button" data-nav="{key}" data-label="{esc(label)}"'
        f'{" aria-current=" + chr(34) + "page" + chr(34) if key == home else ""}>{icon(ico)}<span>{esc(label)}</span>'
        + (f'<span class="badge">{badges[key]}</span>' if key in badges else "")
        + "</button>"
        for key, label, ico in PAGES)
    sections = "".join(
        f'<section class="page" data-page="{key}"{"" if key == home else " hidden"}>{pages[key]}</section>'
        for key, _, _ in PAGES)

    if mode == "share":
        controls = ""
        banner = f'<div class="banner" role="note">{icon("lock")}<span>{esc(SHARE_NOTE)}</span></div>'
        generated = f"Copy made {show_time(now)} (Asia/Manila)."
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
        generated = f"Updated {show_time(now)} (Asia/Manila)."
        side_note = "Nothing is posted automatically. Kint posts by hand after David approves."
        connect = "'self'"
    topbar = (
        f'<header class="topbar"><div class="crumb" id="crumb">{esc(dict((k, l) for k, l, _ in PAGES)[home])}</div>'
        f'<div class="health" title="{esc(health)}"><span class="tag dot {health_cls}">{esc(state_text)}</span>'
        f'<span class="health-text">{esc(health)}</span></div>{controls}</header>'
    )
    sidebar = (
        '<aside class="sidebar"><div class="brand">' + dashboard_assets.BRAND_MARK
        + '<div><div class="brand-name">TPM Photo News</div><div class="brand-sub">The Photo Mentorship</div></div></div>'
        f'<nav class="nav" aria-label="Sections">{nav}</nav>'
        f'<div class="side-foot"><strong>{icon("lock")}Posting stays manual</strong><span>{esc(side_note)}</span>'
        f'<span class="gen">{esc(generated)}</span></div>'
        "</aside>"
    )
    overlays = (
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
        "<title>TPM Photo News</title><style>" + font_css + dashboard_assets.CSS + inspiration.CSS + "</style></head>"
        f'<body data-mode="{mode}" data-home="{home}"><div class="app">' + sidebar
        + '<div class="main">' + topbar + banner
        + f'<div class="content">{sections}</div></div></div>'
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
    stories, hidden = split_hidden(apply_official_overrides(build_stories(data, rules), rules), rules)
    cards = hide_cards(read_carousels(carousels_dir, samples_dir, Path(previews_dir) if previews_dir is not None
                                      else None), hidden)
    if card_filter is not None:
        cards = [c for c in cards if card_filter(c)]
    if base_for is not None:
        for c in cards:
            c["base"] = base_for(c)
    if approved_href == "auto":
        approved_zip = carousels_dir / downloads.APPROVED_ZIP_NAME
        approved_href = f"../output/carousels/{downloads.APPROVED_ZIP_NAME}" if approved_zip.exists() else None
    events = hide_events(activity.read_events(activity_path), hidden)
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
