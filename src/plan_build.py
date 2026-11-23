"""Carousels without Claude: a person (or Grok Bot) writes the plan, and the existing code checks and renders it.

Claude is never called here. The plan JSON has the same shape as the plan Claude used to draft (see
docs/plan-schema.md), plus a few build fields: the official page, the official images for each slide and,
optionally, the fact and image check verdicts. Everything that does not need Claude still runs exactly as on any
build:

- the official page must be on the brand's official domains (config/carousel.yaml) and long enough to be a source,
- every fact's quote must appear word for word in the official page text (carousel_plan.verify),
- the product name must be written the way the official page writes it,
- no em or en dashes, spaced hyphens, hashtags or overflowing text (carousel_text lint, design check),
- every image must be on an official domain, must really appear on the official page named for it, must download
  as a real JPEG, PNG or WebP of at least 1000px with no AI metadata, and must pass the image check verdict
  (matches the product, real photo or official screenshot, shows the slide's subject, no watermark, no person as
  the subject, not AI generated). A feature slide only takes an image named for its own feature,
- the slides are rendered at 1080 x 1440, with the YOUR TAKE closing slide when there is room,
- the fact check, sources and review files are written, and a draft that passes becomes Waiting for approval.

By default the build is strict: a claim whose quote is not on the official page stops the build with the list of
claims to fix (nothing is silently dropped). --allow-removed keeps the old behaviour (the claim is removed).

python scripts/build_from_plan.py --story 72 --plan data/plans/story-72.json --dry-run
python scripts/build_from_plan.py --story 72 --plan data/plans/story-72.json [--verdicts v.json]

A dry run writes to output/plan-previews/ (never synced, never on the dashboard), sends no Slack message, records
nothing and pushes nothing. A real build writes the carousel folder, records it, sends the existing "Carousel ready
for approval" Slack message (the webhook from .env, never printed) and pushes state/ after the public safety check.
Nothing is ever posted to Facebook or Instagram.
"""
from __future__ import annotations

import contextlib
import copy
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import activity
import border_trim
import carousel
import carousel_plan
import carousel_status
import dashboard
import dedupe
import image_override
import image_pick
import images
import official
import timing

ROOT = Path(__file__).resolve().parent.parent
PLAN_DIR = ROOT / "data" / "plans"  # local only (data/ is never committed)
PREVIEW_ROOT = ROOT / "output" / "plan-previews"  # dry runs: never synced to state/, never on the dashboard
BUILD_KEYS = ("story", "brand", "official_url", "images", "verdicts", "author", "notes")
DEFAULT_AUTHOR = "Grok Bot"
NUMBERED_IMAGE = re.compile(r"^\d\d(-old)?\.(jpg|jpeg|png|webp)$", re.I)


class PlanInputError(carousel.Refused):
    """The plan file or the verdicts file cannot be used as written."""


# ---------- reading the files ----------

def read_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanInputError(f"cannot read {Path(path).name}: {type(exc).__name__}") from exc
    except ValueError as exc:
        raise PlanInputError(f"{Path(path).name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanInputError(f"{Path(path).name} must hold one JSON object")
    return data


def split_input(data: dict) -> tuple[dict, dict]:
    """(the plan exactly as Claude used to draft it, the build fields). plan.json in the folder keeps only the plan."""
    plan = {k: copy.deepcopy(v) for k, v in data.items() if k not in BUILD_KEYS}
    meta = {k: copy.deepcopy(data[k]) for k in BUILD_KEYS if k in data}
    return plan, meta


def plan_path_for(story_id, plan_dir: Path | None = None) -> Path | None:
    """data/plans/story-<id>.json (or <id>.json). None when no plan was written for the story."""
    folder = Path(plan_dir) if plan_dir else PLAN_DIR
    for name in (f"story-{story_id}.json", f"{story_id}.json"):
        if (folder / name).is_file():
            return folder / name
    return None


def verdicts_path_for(plan_path: Path) -> Path | None:
    """story-72.verdicts.json beside story-72.json, when there is one."""
    candidate = plan_path.with_name(plan_path.stem + ".verdicts.json")
    return candidate if candidate.is_file() else None


def load_verdicts(data: dict | None) -> tuple[dict[str, dict], dict[str, dict]]:
    """({fact id: {"verdict", "quote"}}, {image key: check}) from a verdicts object.

    {"facts": {"slide1.body": {"verdict": "CONFIRMED", "quote": "..."}}, "images": {"ENHANCE": {...}}}
    Facts not listed are decided by the quote check alone (the quote must be on the official page)."""
    if not data:
        return {}, {}
    facts_in = data.get("facts") or {}
    images_in = data.get("images") or {}
    if not isinstance(facts_in, dict) or not isinstance(images_in, dict):
        raise PlanInputError("verdicts: facts and images must be JSON objects")
    facts = {}
    for fact_id, value in facts_in.items():
        if not isinstance(value, dict) or value.get("verdict") not in carousel_plan.VERDICTS:
            raise PlanInputError(f"verdicts: {fact_id} needs a verdict, one of {', '.join(carousel_plan.VERDICTS)}")
        facts[str(fact_id)] = {"verdict": value["verdict"], "quote": str(value.get("quote") or "")}
    return facts, {str(k): v for k, v in images_in.items()}


# ---------- images ----------

def _url_key(url: str) -> str:
    parts = urlsplit(url if "//" in url else "https://" + url.lstrip("/"))
    return f"{(parts.hostname or '').lower()}{parts.path}"


def image_on_page(image_url: str, markup: str, page_url: str) -> tuple[bool, str]:
    """(found, alt text): the image really appears on the official page (an img, srcset, og:image, or the file's
    address anywhere in the page source, ignoring the size query)."""
    found, _ = images.parse_page(markup, page_url)
    want = _url_key(image_url)
    for item in found:
        if _url_key(item["src"]) == want:
            return True, item.get("alt", "")
    path = urlsplit(image_url).path
    if path and len(path) > 8 and path in markup:
        return True, ""
    return False, ""


def slot_for_key(key: str, views: list[dict]) -> str | None:
    """The image slot ("03", "05-old") a plan image key points at: cover, price, comparison, comparison-old, or a
    feature slide's headline (the feature name, so the image follows its feature)."""
    wanted = key.strip().lower()
    for number, view in enumerate(views, 1):
        if wanted == "cover" and view["type"] == "cover":
            return f"{number:02d}"
        if wanted in ("price", "comparison") and view["type"] == wanted:
            return f"{number:02d}"
        if wanted == "comparison-old" and view["type"] == "comparison":
            return f"{number:02d}-old"
    if wanted in ("cover", "price", "comparison", "comparison-old"):
        return None
    return image_override.slot_for_feature(key, views)


def feature_slots(views: list[dict]) -> dict[str, str]:
    """{slot: headline} of every feature slide ("02": "RELIGHT")."""
    return {f"{number:02d}": view.get("headline", "") for number, view in enumerate(views, 1)
            if view.get("type") == "feature"}


def require_feature_images(placed: dict, views: list[dict]) -> None:
    """Every feature slide must show its own checked official image. A slide with none stops the build: find a real
    official image of that feature, or leave the feature out. The cover may be a collage of the feature images, and
    the YOUR TAKE closing slide states no product fact."""
    bare = [f"slide {slot} ({' '.join(str(head).split())})" for slot, head in feature_slots(views).items()
            if slot not in placed]
    if bare:
        raise PlanInputError(
            f"{len(bare)} feature slide(s) have no official image: {', '.join(bare)}. Every feature slide needs its "
            "own real official image (add it under images, keyed by the slide's headline), or drop that slide")


def place_images(entries: dict, checks: dict, views: list[dict], out_dir: Path, domains: list[str],
                 fetch_page=None, fetch_image=None, trim=border_trim.trim_border) -> tuple[dict, list[str], str]:
    """Checks and places every image the plan names. Returns ({slot: entry}, log lines for sources.md, candidates.md).

    Strict: an image that fails any rule stops the build with the reason, so a wrong photo is never shown."""
    fetch_page = fetch_page or official.fetch_html
    fetch_image = fetch_image or images.fetch_bytes
    if entries and not isinstance(entries, dict):
        raise PlanInputError("images must be a JSON object: {\"FEATURE NAME\": {\"image_url\", \"page_url\"}}")
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for stale in images_dir.iterdir():  # only this plan's images can be rendered
        if stale.is_file() and NUMBERED_IMAGE.match(stale.name):
            stale.unlink()
    pages: dict[str, str] = {}
    chosen: list[tuple[str, str, dict, bytes, str]] = []
    used_on_features: dict[str, str] = {}
    for key, entry in (entries or {}).items():
        if not isinstance(entry, dict) or not entry.get("image_url") or not entry.get("page_url"):
            raise PlanInputError(f"image {key!r}: needs image_url and page_url")
        image_url, page_url = entry["image_url"], entry["page_url"]
        slot = slot_for_key(key, views)
        if slot is None:
            raise PlanInputError(f"image {key!r}: no slide is about that (use cover, price, comparison, "
                                 "comparison-old or a feature slide's headline)")
        if not official.host_allowed(page_url, domains):
            raise PlanInputError(f"image {key!r}: the page {page_url} is not on an official domain ({', '.join(domains)})")
        if not (official.host_allowed(image_url, domains)
                or urlsplit(image_url).hostname == urlsplit(page_url).hostname):
            raise PlanInputError(f"image {key!r}: {image_url} is not hosted on an official domain")
        view = views[int(slot[:2]) - 1]
        if view["type"] == "feature":
            if image_url in used_on_features:
                raise PlanInputError(f"image {key!r}: the same image is already on the {used_on_features[image_url]} "
                                     "slide; a feature slide only shows its own feature")
            used_on_features[image_url] = view["headline"]
        if page_url not in pages:
            try:
                pages[page_url] = fetch_page(page_url)
            except Exception as exc:
                raise PlanInputError(f"image {key!r}: the official page {page_url} could not be read "
                                     f"({type(exc).__name__})") from exc
        found, alt = image_on_page(image_url, pages[page_url], page_url)
        if not found:
            raise PlanInputError(f"image {key!r}: {image_url} does not appear on the official page {page_url}")
        try:
            data = fetch_image(image_url)
        except Exception as exc:
            raise PlanInputError(f"image {key!r}: could not be downloaded ({type(exc).__name__})") from exc
        reason = images.reject_reason({"src": image_url, "alt": alt or entry.get("alt", "")}, data, page_url, domains)
        if reason:
            raise PlanInputError(f"image {key!r}: {reason}")
        check = checks.get(key, entry.get("check"))
        verdict = image_pick.parse_verdict(json.dumps(check)) if isinstance(check, dict) else {
            "unreadable": True, "notes": "no image check was written for it"}
        ok, why = image_pick.decide(verdict, demo=bool(entry.get("demo")))
        if not ok:
            raise PlanInputError(f"image {key!r}: the image check did not pass ({why})")
        chosen.append((key, slot, entry, data, verdict.get("notes", "")))
    log: list[str] = []
    placed: dict[str, dict] = {}
    trimmed = images.trim_all(trim, [data for _, _, _, data, _ in chosen])
    for (key, slot, entry, data, notes), result in zip(chosen, trimmed):
        final, info = result if result is not None else (data, {})
        target = image_override._save(images_dir, slot, final)
        size = images.image_dimensions(final) or (0, 0)
        note = border_trim.describe(info) if info.get("trimmed") else "no strip to trim, used as published"
        log.append(f"slide {slot} ({key}): official image placed as {target.name} ({size[0]}x{size[1]}). "
                   f"Image: {entry['image_url']}. Official page: {entry['page_url']}. {note}. "
                   f"Image check (written by the plan author): passes every check. {notes}".rstrip())
        placed[slot] = entry
    md = ["# Images chosen for this plan", "",
          "Every image was picked by the plan author from the brand's official pages and checked by code: official "
          "domain, present on the named official page, real JPEG, PNG or WebP of at least 1000px, no AI metadata, "
          "and a passing image check.", ""]
    md += [f"- slide {slot}: {entry['image_url']} (on {entry['page_url']})" for slot, entry in sorted(placed.items())]
    return placed, log, "\n".join(md + [""])


# ---------- the build ----------

@contextlib.contextmanager
def quiet_activity(enabled: bool):
    """A dry run writes nothing to the Activity log (it is synced and shown on the dashboard)."""
    if not enabled:
        yield
        return
    original = activity.log_event
    activity.log_event = lambda *args, **kwargs: False
    try:
        yield
    finally:
        activity.log_event = original


def strict_check(plan_data: dict, official_text: str, verdicts: dict) -> None:
    """Every claim must match the official page word for word, or the build stops with the list to fix."""
    plan = carousel_plan.load_plan(plan_data)
    report = carousel_plan.verify(plan, official_text, verdicts)
    bad = [r for r in report if r["verdict"] == "NOT CONFIRMED"]
    if bad:
        lines = "; ".join(f"{r['id']} ({r['text']!r})" for r in bad)
        raise carousel_plan.PlanError(
            f"{len(bad)} claim(s) do not match the official page word for word, fix the quote or leave the claim "
            f"out: {lines}")


def build_story(key: str, plan_path: Path, verdicts_path: Path | None = None, *, dry_run: bool = True,
                render: bool = True, allow_removed: bool = False, rebuild: bool = False, ignore_cap: bool = False,
                now: datetime | None = None, config: dict | None = None, locate=None, place=None,
                preview_root: Path | None = None) -> dict:
    """Builds one story's carousel from a written plan. Returns the assemble result plus "dry_run" and "story".
    Raises carousel.Refused, carousel_plan.PlanError, carousel.DesignFailed or LintError like any build."""
    now = now or datetime.now(timezone.utc)
    config = config or carousel.load_config()
    locate = locate or carousel.locate_official
    clock = timing.Clock(f"story {key} (plan)")
    if not carousel.DATA_PATH.exists():
        raise carousel.Refused("No watcher data yet. Run scripts\\pending_carousels.py --sync first.")
    store = dedupe.Store(carousel.DATA_PATH)
    try:
        story = carousel.find_story(store, str(key), now)
    finally:
        store.db.close()
    carousel.check_eligible(story, carousel.load_rules())
    data = read_json(plan_path)
    plan_data, meta = split_input(data)
    if meta.get("story") not in (None, story.id, str(story.id)):
        raise PlanInputError(f"the plan is for story {meta['story']}, not story {story.id}")
    if verdicts_path:
        facts, checks = load_verdicts(read_json(verdicts_path))
    else:
        facts, checks = load_verdicts(meta.get("verdicts"))
    brand = meta.get("brand") or story.brand
    if not brand:
        raise carousel.Refused("The story has no brand. Add \"brand\" to the plan and the brand's official domains "
                               "to config/carousel.yaml.")
    if not meta.get("official_url"):
        raise PlanInputError("the plan needs official_url: the brand's own page every fact is quoted from")
    official.enable_page_cache(carousel.PAGE_CACHE_DIR, float(config.get("page_cache_hours", 6)))
    images.IMAGE_CACHE_DIR = carousel.IMAGE_CACHE_DIR
    try:
        with clock.step("official page"):
            page = locate(story, brand, config, meta["official_url"])
        carousel_plan.load_plan(plan_data)  # shape and copy rules first, with the exact error
        if not allow_removed:
            strict_check(plan_data, page.text, facts)
        recheck = lambda new_plan, ids: {i: v for i, v in facts.items() if i in ids}  # noqa: E731
        names = carousel_plan.official_names(page.text, page.terms)
        plan_data, verdicts, notes = carousel.settle_cover(plan_data, page.text, dict(facts), names, recheck)
        heads = [h["text"] for h in (s["headline"] for s in carousel_plan.load_plan(plan_data)["slides"]) if h]
        plan_data, verdicts, hook_notes = carousel.settle_hook(
            plan_data, page.text, verdicts, [" ".join(carousel_plan.strip_parentheses(f).split()) for f in heads],
            recheck)
        notes += hook_notes
        plan_data = carousel_plan.with_event_label(plan_data, official.page_text(page.markup))
        plan = carousel_plan.load_plan(plan_data)
        carousel_plan.verify(plan, page.text, verdicts)
        views = carousel_plan.build_views(plan)

        folder = carousel.item_folder(story.title, story.first_seen)
        out_dir = (Path(preview_root) if preview_root else PREVIEW_ROOT) / folder.name if dry_run else folder
        if not dry_run:
            current = carousel_status.read_status(out_dir)["status"] if out_dir.exists() else None
            if current in ("approved", "posted"):
                raise carousel.Refused(f"This carousel is already {current}; it is not rebuilt.")
            import carousel_auto
            if carousel_auto.already_built(carousel.DATA_PATH, story.id) and not rebuild:
                raise carousel.Refused("This story already has a carousel. Pass --rebuild to replace the draft.")
            if not ignore_cap and not carousel_auto.already_built(carousel.DATA_PATH, story.id):
                allowed, reason = carousel_auto.may_build(carousel.DATA_PATH, now)
                if not allowed:
                    raise carousel.Refused(f"Not built now: {reason}. Try again tomorrow or pass --ignore-cap.")
        out_dir.mkdir(parents=True, exist_ok=True)
        domains = config["official_domains"].get(brand, [])
        with clock.step("official images (checked plan images)"):
            placer = place or place_images
            placed, image_log, candidates_md = placer(meta.get("images") or {}, checks, views, out_dir, domains)
        if config.get("require_feature_images", True):
            require_feature_images(placed or {}, views)
        author = meta.get("author") or DEFAULT_AUTHOR
        extra = [f"made without Claude: the plan was written by {author} from the official page and checked by code "
                 "(quotes word for word, official images, lint, design check)"]
        if meta.get("brand") and meta["brand"] != story.brand:
            extra.append(f"brand: {meta['brand']} (the story was filed under {story.brand or 'no brand'})")
        if page.note:
            extra.append(f"fact source: {page.note}")
        extra += notes + image_log
        if dry_run:
            extra.append("DRY RUN: not recorded, no Slack message, nothing pushed, not on the dashboard")
        article_links = [(src["source"], src.get("link") or src["url"]) for src in story.sources]
        with quiet_activity(dry_run):
            result = carousel.assemble(
                plan_data, title=story.title, official_text=page.text, verdicts=verdicts, out_dir=out_dir,
                official_url=page.url, article_links=article_links, press_images=True, render=render,
                checked_on=now.astimezone(dashboard.MANILA).strftime("%Y-%m-%d"), extra_notes=extra,
                candidates_md=candidates_md, closing=bool(config.get("closing_slide", True)), clock=clock)
    finally:
        official.disable_page_cache()
        images.IMAGE_CACHE_DIR = None
    carousel_status.update_fields(out_dir, made_by=author, made_without_claude=True)
    if dry_run:
        # A preview is never sent for approval: it stays a draft until a real build, whatever the checks said.
        carousel_status.update_fields(out_dir, status="draft", preview=True)
    result.update({"dry_run": dry_run, "story": story.id, "title": story.title})
    return result


# ---------- publishing a real build ----------

def publish(result: dict, now: datetime | None = None, *, root: Path = ROOT, git=None, sync=None, safety=None,
            notify=None, webhook=None) -> dict:
    """Records the build, sends the existing "Carousel ready for approval" Slack message and pushes state/ after the
    public safety check (the carousel bot's own steps). Never called for a dry run."""
    import carousel_auto
    import carousel_bot
    import cloud_state
    if result.get("dry_run"):
        raise ValueError("a dry run is never published")
    now = now or datetime.now(timezone.utc)
    db_path = root / "data" / "seen.sqlite"
    folder = Path(result["folder"])
    summary = {"slack": "not sent", "push": "not tried"}
    status = carousel_status.read_status(folder)
    carousel_auto.record(db_path, int(result["story"]), now, "ok", str(folder), "draft ready (plan, no Claude)")
    activity.log_event("carousel", "built", f"Story {result['story']}, {result['title']}: draft ready in "
                       f"{folder.name}, {result.get('slides', '?')} slides (plan written without Claude)", now=now)
    if status["status"] == "waiting_for_david":
        url = webhook if webhook is not None else carousel_bot.webhook_or_none()
        if url:
            carousel_auto._notify_safely(notify or carousel_auto.alert.send_to_slack,
                                         carousel_auto.ready_message(result["title"], result), url,
                                         sent_line="Carousel ready for approval sent")
            summary["slack"] = "sent"
        else:
            summary["slack"] = "not sent (no Slack address in .env)"
    else:
        summary["slack"] = f"not sent (status is {status['status']}, not waiting for approval)"
    carousel_bot._refresh_pages(root)
    (sync or cloud_state).push("laptop", root)
    problems = (safety or carousel_bot._safety)(root)
    if problems:
        summary["push"] = "not pushed: the safety check found " + "; ".join(problems[:3])
        return summary
    summary["push"] = carousel_bot.commit_and_push(git or carousel_bot.run_git, root)
    return summary


def sync_first(root: Path = ROOT, git=None, sync=None) -> bool:
    """git pull and state/ into data/ and output/, so the build sees the cloud's latest stories."""
    import carousel_bot
    import cloud_state
    pulled = carousel_bot.pull(git or carousel_bot.run_git, root)
    (sync or cloud_state).pull("laptop", root)
    return pulled


# ---------- the carousel bot and the watcher with Claude off ----------

def last_failure_at(db_path: Path, story_id: int) -> datetime | None:
    if not Path(db_path).exists():
        return None
    db = sqlite3.connect(db_path)
    try:
        row = db.execute("SELECT built_at FROM carousel_builds WHERE story_id=? AND status='failed' "
                         "ORDER BY built_at DESC", (story_id,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        db.close()
    try:
        return datetime.fromisoformat(row[0]) if row and row[0] else None
    except ValueError:
        return None


def stories_with_plans(db_path: Path, stories: list[tuple[int, str]], plan_dir: Path | None = None
                       ) -> tuple[list[tuple[int, str]], list[str]]:
    """(stories that have a plan to build from, outcome lines for the rest). A plan that already failed is only
    tried again once the plan file is saved again (newer than the failure), so a broken plan is never retried hourly."""
    ready, skipped = [], []
    for story_id, title in stories:
        path = plan_path_for(story_id, plan_dir)
        if path is None:
            skipped.append(f"{story_id}: skipped (no plan written yet; Claude is off)")
            continue
        failed = last_failure_at(db_path, story_id)
        changed = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if failed is not None and failed >= changed:
            skipped.append(f"{story_id}: skipped (its plan failed; save a fixed plan to try again)")
            continue
        ready.append((story_id, title))
    return ready, skipped


def plan_builder(plan_dir: Path | None = None):
    """build(story_id) for carousel_auto.after_alerts: a real build from the story's plan (recorded and announced by
    after_alerts itself). Claude is never called."""
    def build(story_id: int) -> dict:
        path = plan_path_for(story_id, plan_dir)
        if path is None:
            raise carousel.Refused("no plan written for this story")
        return build_story(str(story_id), path, verdicts_path_for(path), dry_run=False, ignore_cap=True,
                           rebuild=False)
    return build


def build_waiting_from_plans(db_path: Path, now: datetime, webhook, notify=None, plan_dir: Path | None = None,
                             stories: list[tuple[int, str]] | None = None) -> list[str]:
    """Every waiting official story that has a plan, within the caps (after_alerts checks them). No Claude."""
    import carousel_auto
    if stories is None:
        stories = carousel_auto.pending_stories(db_path, now)
    ready, skipped = stories_with_plans(db_path, stories, plan_dir)
    outcomes = list(skipped)
    if ready:
        outcomes += carousel_auto.after_alerts(db_path, ready, now, webhook, plan_builder(plan_dir),
                                               notify=notify or carousel_auto.alert.send_to_slack,
                                               max_failed=10 ** 6)
    return outcomes


# ---------- the command ----------

def main(argv: list[str] | None = None) -> int:
    import argparse

    from dotenv import load_dotenv

    from carousel_text import LintError
    parser = argparse.ArgumentParser(description="Build a carousel from a written plan, without Claude. Posts nothing.")
    parser.add_argument("--story", required=True, help="stored story id (see scripts/pending_carousels.py)")
    parser.add_argument("--plan", help="the plan JSON (default: data/plans/story-<id>.json)")
    parser.add_argument("--verdicts", help="fact and image check verdicts JSON (default: story-<id>.verdicts.json "
                                           "beside the plan, or the plan's own \"verdicts\")")
    parser.add_argument("--dry-run", action="store_true",
                        help="write to output/plan-previews only: no record, no Slack, no push")
    parser.add_argument("--skip-render", action="store_true", help="write the text files without rendering PNGs")
    parser.add_argument("--allow-removed", action="store_true",
                        help="remove claims that do not match the official page instead of stopping")
    parser.add_argument("--rebuild", action="store_true", help="replace a draft this story already has")
    parser.add_argument("--ignore-cap", action="store_true", help="build even when the 1 a day cap is reached")
    parser.add_argument("--no-sync", action="store_true", help="real build: skip git pull and the state pull first")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    plan_path = Path(args.plan) if args.plan else plan_path_for(args.story)
    if plan_path is None:
        print(f"No plan for story {args.story}. Write data/plans/story-{args.story}.json (see docs/plan-schema.md).")
        return 2
    verdicts = Path(args.verdicts) if args.verdicts else verdicts_path_for(plan_path)
    try:
        if not args.dry_run and not args.no_sync:
            if not sync_first():
                print("git pull did not work; nothing was built. Try again, or pass --no-sync.")
                return 1
        result = build_story(args.story, plan_path, verdicts, dry_run=args.dry_run, render=not args.skip_render,
                             allow_removed=args.allow_removed, rebuild=args.rebuild, ignore_cap=args.ignore_cap)
    except carousel.Refused as exc:
        print(f"Not made: {exc}")
        return 2
    except carousel_plan.PlanError as exc:
        print(f"The plan needs fixing: {exc}")
        return 1
    except carousel.DesignFailed as exc:
        print(f"Design check failed, see factcheck.md: {exc}")
        return 1
    except LintError as exc:
        print(f"Lint failed, nothing is ready: {exc}")
        return 1
    carousel.print_summary(result)
    status = carousel_status.read_status(Path(result["folder"]))["status"]
    print(f"Status: {carousel_status.STATUS_LABELS.get(status, status)}")
    if args.dry_run:
        print("Dry run: nothing recorded, no Slack message, nothing pushed, not on the dashboard.")
        return 0
    summary = publish(result)
    print(f"Slack: {summary['slack']}. Push: {summary['push']}.")
    return 0
