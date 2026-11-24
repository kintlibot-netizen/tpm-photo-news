"""Stories waiting for a carousel, with what a plan writer needs: id, title, brand, article links, the brand's official
domains, the last failure, whether a plan exists, and (with --locate) the official page text the facts must be quoted
from. Claude is never called. Nothing is sent or pushed.

python scripts/pending_carousels.py                 the waiting stories (official, sent, 72 hours old or less, no carousel)
python scripts/pending_carousels.py --json          the same as JSON
python scripts/pending_carousels.py --all           every sent official story, not only the last 72 hours
python scripts/pending_carousels.py --sync          git pull and the state pull first (the cloud's latest stories)
python scripts/pending_carousels.py --locate        also find each story's official page and save its text
python scripts/pending_carousels.py --story 72 --official-url URL    save that official page's text for story 72

The official page text is saved as data/plans/story-<id>.official.txt (fact source: every quote must be in it) and
the official images found on the page as data/plans/story-<id>.images.txt.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import carousel
import classify
import carousel_auto
import dashboard
import dedupe
import images
import plan_build

ROOT = Path(__file__).resolve().parent.parent


def _failures(db_path: Path, story_id: int) -> tuple[int, str | None]:
    db = sqlite3.connect(db_path)
    try:
        rows = db.execute("SELECT message FROM carousel_builds WHERE story_id=? AND status='failed' ORDER BY id",
                          (story_id,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        db.close()
    return len(rows), (rows[-1][0] if rows else None)


def describe(story, db_path: Path, config: dict, plan_dir: Path | None = None) -> dict:
    count, last = _failures(db_path, story.id)
    day = (story.first_seen or datetime.now(timezone.utc)).astimezone(dashboard.MANILA)
    plan = plan_build.plan_path_for(story.id, plan_dir)
    return {
        "key": story.id,
        "title": story.title,
        "brand": story.brand,
        "first_seen_manila": day.strftime("%Y-%m-%d %H:%M"),
        "label": story.last_alert_label,
        "sources": [{"site": s["source"], "url": s.get("link") or s["url"]} for s in story.sources],
        "official_domains": config["official_domains"].get(story.brand, []) if story.brand else [],
        "failed_attempts": count,
        "last_failure": last,
        "plan": str(plan.relative_to(ROOT)) if plan and plan.is_relative_to(ROOT) else (str(plan) if plan else None),
        "folder": carousel.item_folder(story.title, story.first_seen).name,
    }


def save_official(story, config: dict, official_url: str | None, plan_dir: Path, locate=None) -> dict:
    """Finds (or reads the given) official page and saves its fact text and its image list. Never raises."""
    locate = locate or carousel.locate_official
    try:
        page = locate(story, story.brand, config, official_url)
    except Exception as exc:
        return {"official_url": None, "official_problem": str(exc)}
    plan_dir.mkdir(parents=True, exist_ok=True)
    text_path = plan_dir / f"story-{story.id}.official.txt"
    text_path.write_text(f"OFFICIAL PAGE: {page.url}\nFACT SOURCE: {page.note or 'the whole page'}\n\n{page.text}\n",
                         encoding="utf-8")
    found = []
    for url, markup in page.pages:
        for item in images.parse_page(markup, url)[0]:
            if not item["src"].lower().split("?")[0].endswith(".svg"):
                found.append(f"{item['src']}\t(on {url})\talt: {item.get('alt', '')}")
    image_path = plan_dir / f"story-{story.id}.images.txt"
    image_path.write_text("\n".join(dict.fromkeys(found)) + "\n", encoding="utf-8")
    return {"official_url": page.url, "official_text_path": str(text_path), "official_text_chars": len(page.text),
            "official_images_path": str(image_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stories waiting for a carousel plan. No Claude, sends nothing.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--all", action="store_true", help="every sent official story, not only the waiting ones")
    parser.add_argument("--sync", action="store_true", help="git pull and the state pull first")
    parser.add_argument("--locate", action="store_true", help="find each story's official page and save its text")
    parser.add_argument("--story", help="only this story id")
    parser.add_argument("--official-url", help="with --story: save this official page's text")
    parser.add_argument("--plan-dir", help="where plans are kept (default data/plans)")
    args = parser.parse_args(argv)
    plan_dir = Path(args.plan_dir) if args.plan_dir else plan_build.PLAN_DIR
    if args.sync:
        plan_build.sync_first()
    db_path = carousel.DATA_PATH
    if not db_path.exists():
        print("No watcher data yet. Run with --sync.")
        return 1
    now = datetime.now(timezone.utc)
    config = carousel.load_config()
    store = dedupe.Store(db_path)
    try:
        if args.all or args.story:
            stories = carousel.eligible_stories(store, carousel.load_rules(), now)
        else:
            waiting = {sid for sid, _ in carousel_auto.pending_stories(db_path, now)}
            order = [sid for sid, _ in carousel_auto.pending_stories(db_path, now)]
            by_id = {s.id: s for s in store.recent_stories(3650, now) if s.id in waiting}
            stories = [by_id[sid] for sid in order if sid in by_id]
    finally:
        store.db.close()
    if not args.story:
        # Kint's big brand and photographer gates: a story that fails them is not offered for a carousel.
        rules = carousel.load_rules()
        stories = [s for s in stories
                   if not classify.story_gate_problem(s.sources, s.brand, s.title, rules)]
    if args.story:
        stories = [s for s in stories if str(s.id) == str(args.story)]
        if not stories:
            print(f"Story {args.story} is not a sent official story.")
            return 1
    rows = []
    for story in stories:
        row = describe(story, db_path, config, plan_dir)
        if args.locate or args.official_url:
            row.update(save_official(story, config, args.official_url, plan_dir))
        rows.append(row)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("No stories are waiting for a carousel.")
    for row in rows:
        print(f"{row['key']:>5}  {row['first_seen_manila']}  {row['brand'] or 'NO BRAND':<12} {row['title']}")
        for src in row["sources"]:
            print(f"       article: {src['site']}: {src['url']}")
        print(f"       official domains: {', '.join(row['official_domains']) or 'none listed (add them to config/carousel.yaml)'}")
        if row["failed_attempts"]:
            print(f"       failed {row['failed_attempts']} time(s), last: {row['last_failure']}")
        print(f"       plan: {row['plan'] or 'none yet'}")
        if "official_url" in row:
            if row["official_url"]:
                print(f"       official page: {row['official_url']} ({row['official_text_chars']} characters)")
                print(f"       fact text: {row['official_text_path']}")
                print(f"       official images: {row['official_images_path']}")
            else:
                print(f"       official page not found: {row['official_problem']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
