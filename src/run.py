"""Runs one full check: fetch, dedupe, classify, alert.

python src/run.py --dry-run     Writes alerts to output/ and sends nothing.
python src/run.py               Sends real alerts to Slack.

Both modes save the run history and rebuild dashboard/index.html at the end. A live run also builds
carousel drafts for sent official stories (and waiting ones) within the caps, and sends at most one
health message a day if no feed works.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

import activity
import alert as alert_step
import classify
import dedupe
import fetch
import health
import runlog
from runlog import ALERTED, DRY_ONLY, FAILED, HELD, READY, REJECTED, SKIPPED

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("watcher")
HELD_REASON = "Only one site has reported it so far."
FREE_RULES_REASON = "Matched by the free rules only. Claude did not review it."


def load_yaml(name: str) -> dict:
    with open(ROOT / "config" / name, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def judgement(story, status, label, category, summary, reason) -> dict:
    """What the run decided about one story, kept for the dashboard."""
    return {
        "story": story, "status": status, "label": label, "category": category,
        "summary": summary, "reason": reason,
    }


def refresh_stored(store: dedupe.Store, rules: dict, now: datetime) -> None:
    """Judges stored stories again under the current rules. Never sends anything.

    Stories already sent only get a corrected brand. Stories not yet sent are marked Skipped when
    no source passes the free rules any more, and an old Claude label is cleared so the current
    rules decide again. Rejections are kept, so nothing that was rejected is reopened. Nothing
    here posts to Slack.
    """
    for story in store.recent_stories(rules["same_story_window_days"], now):
        brand = dedupe.brand_from_sources(story.sources, rules["brands"])
        if brand and brand != story.brand:
            store.set_brand(story, brand)
        if story.last_alert_label:
            continue
        reason = classify.story_skip_reason(story.sources, rules)
        if reason:
            if story.skipped != reason:
                store.mark_skipped(story, reason)
        elif story.skipped:
            store.clear_skipped(story)
        if story.claude_label and story.review_version != classify.RULES_VERSION:
            store.reset_claude_label(story)


def process(
    items: list[fetch.Item], store: dedupe.Store, rules: dict, use_claude: bool,
    now: datetime, model: str = "haiku", asker=classify.ask_claude,
) -> dict:
    """Everything between fetching and delivering. Returns what to alert."""
    fresh = [i for i in items if classify.is_fresh(i, rules["max_age_hours"], now)]
    candidates = [i for i in fresh if classify.is_candidate(i, rules)]
    dedupe.group_into_stories(
        candidates, store, rules["same_story_window_days"],
        rules["title_similarity"], rules["brands"], now,
    )
    refresh_stored(store, rules, now)
    to_alert, held, judged = [], [], []
    # Looks at every remembered story, so a failed Slack send is retried next run.
    for story in store.recent_stories(rules["same_story_window_days"], now):
        send, label, reason = classify.alert_decision(story, rules)
        if send:
            to_alert.append((story, label, reason))
        elif reason.startswith("rumor held"):
            held.append(story)
            judged.append(judgement(
                story, HELD, label, classify.rule_category(story.title, rules),
                classify.feed_summary(story), HELD_REASON,
            ))
        elif reason == "skipped by the free rules":
            judged.append(judgement(
                story, SKIPPED, label, classify.rule_category(story.title, rules),
                classify.feed_summary(story), story.skipped,
            ))

    reviews = classify.review_stories([s for s, _, _ in to_alert], rules, use_claude, model, asker)
    ready, rejected = [], []
    for (story, label, reason), review in zip(to_alert, reviews):
        if not review.relevant:
            store.mark_dismissed(story, classify.RULES_VERSION)
            rejected.append(story)
            judged.append(judgement(
                story, REJECTED, review.label or label, review.category, review.summary,
                review.reason or "Claude judged it not relevant.",
            ))
            continue
        if review.reviewed_by_claude:
            # Claude's label is saved, so the story is not sent to Claude again. The stricter label wins.
            store.set_claude_label(story, review.label, classify.RULES_VERSION)
            send, label, reason = classify.alert_decision(story, rules)
            if not send:
                if reason.startswith("rumor held"):
                    held.append(story)
                    judged.append(judgement(story, HELD, label, review.category, review.summary, review.reason))
                continue
        text = alert_step.format_alert(story, label, review, reason)
        ready.append((story, label, text))
        judged.append(judgement(
            story, READY, label, review.category, review.summary, review.reason or FREE_RULES_REASON,
        ))
    return {
        "items": len(items), "fresh": len(fresh), "candidates": len(candidates),
        "ready": ready, "held": held, "rejected": rejected, "judged": judged,
    }


def details_text(result: dict, failures: dict[str, str]) -> str:
    lines = [
        "RUN DETAILS",
        f"Articles read: {result['items']}",
        f"Published in the time window: {result['fresh']}",
        f"Passed the free rules: {result['candidates']}",
        f"Alerts: {len(result['ready'])}",
        "",
        f"Rumors held, waiting for a second site ({len(result['held'])}):",
    ]
    lines += [f"  {s.title} ({s.sources[0]['source']})" for s in result["held"]] or ["  none"]
    lines += ["", f"Rejected by Claude ({len(result['rejected'])}):"]
    lines += [f"  {s.title}" for s in result["rejected"]] or ["  none"]
    lines += ["", f"Feeds that failed ({len(failures)}):"]
    lines += [f"  {name}: {why}" for name, why in failures.items()] or ["  none"]
    return "\n".join(lines)


def outcome_rows(result: dict, ready_status: dict[int, str], dry: bool, known_max_id: int = 0) -> list[dict]:
    """One row per judged story, for the run history.

    A dry run only keeps a story id for stories that already existed in the real database
    (ids up to known_max_id). Its new stories are not real, so they get no id.
    """
    rows = []
    for entry in result["judged"]:
        story = entry["story"]
        status = entry["status"]
        if status == READY:
            default = DRY_ONLY if dry else FAILED
            status = ready_status.get(id(story), default)
        real_story = story.id is not None and (not dry or story.id <= known_max_id)
        rows.append({
            "story_id": story.id if real_story else None,
            "title": story.title, "brand": story.brand, "category": entry["category"],
            "label": entry["label"], "status": status, "reason": entry["reason"],
            "summary": entry["summary"],
            "first_seen": story.first_seen.isoformat() if story.first_seen else None,
            "sources": json.dumps([
                {"source": s["source"], "link": s.get("link") or s["url"]} for s in story.sources
            ]),
        })
    return rows


def feed_results(settings: dict, items: list[fetch.Item], failures: dict[str, str]) -> list[dict]:
    counts = Counter(item.source for item in items)
    names = [source["name"] for source in settings["sources"]]
    names += [name for name in failures if name not in names]
    return [
        {
            "feed": name, "ok": name not in failures, "items": counts.get(name, 0),
            "error": runlog.plain_error(failures.get(name)),
        }
        for name in names
    ]


def publish(
    mode: str, started: datetime, result: dict, items: list[fetch.Item],
    failures: dict[str, str], settings: dict, outcomes: list[dict], sent: int,
) -> None:
    """Saves the run history and rebuilds the dashboard. A problem here is logged and never fails the run."""
    counts = {
        "articles": result["items"], "in_window": result["fresh"],
        "passed_rules": result["candidates"], "alerts_ready": len(result["ready"]),
        "alerts_sent": sent, "held": len(result["held"]), "rejected": len(result["rejected"]),
    }
    try:
        runlog.record_run(
            ROOT / "data" / "seen.sqlite", mode, started, datetime.now(timezone.utc),
            counts, feed_results(settings, items, failures), outcomes,
        )
    except (sqlite3.Error, OSError) as exc:
        log.error("Run history was not saved: %s", exc)
    try:
        import downloads  # carousels built before round 7 get their prebuilt zip, so the file page can link to it
        downloads.ensure_zips(ROOT / "output" / "carousels", ROOT / "output" / "samples")
    except Exception as exc:  # a download zip is extra; it must never fail a run
        log.error("Download zips were not checked: %s", type(exc).__name__)
    try:
        import dashboard  # imported here, so a dashboard bug can never stop the alert run
        dashboard.write_dashboard(
            db_path=ROOT / "data" / "seen.sqlite",
            out_path=ROOT / "dashboard" / "index.html",
            sources_path=ROOT / "config" / "sources.yaml",
            rules_path=ROOT / "config" / "rules.yaml",
            carousels_dir=ROOT / "output" / "carousels",
            samples_dir=ROOT / "output" / "samples",
            now=datetime.now(timezone.utc),
        )
    except Exception as exc:  # the dashboard is extra; it must never fail a run
        log.error("Dashboard was not rebuilt: %s", exc)


def log_check(mode: str, result: dict, failures: dict[str, str], settings: dict, sent: int) -> None:
    """One Activity row per check: what was read, what was sent, and which feeds failed."""
    feeds = len(settings.get("sources") or [])
    if failures and len(failures) >= feeds > 0:
        outcome = "no feed worked"
    elif failures:
        outcome = "some feeds failed"
    else:
        outcome = "ok"
    kind = "Live check" if mode == "live" else "Practice check (dry run, nothing sent)"
    details = (f"{kind}: {result['items']} articles read, {result['fresh']} in the time window, "
               f"{result['candidates']} passed the free rules, {sent} alerts sent, "
               f"{len(result['held'])} rumors waiting for a 2nd source, {len(failures)} feeds failed")
    if failures:
        details += " (" + ", ".join(sorted(failures)) + ")"
    activity.log_event("check", outcome, details)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Photo news watcher")
    parser.add_argument("--dry-run", action="store_true", help="write alerts to a file, send nothing")
    parser.add_argument("--no-claude", action="store_true", help="use the free rules only")
    parser.add_argument("--cloud", action="store_true",
                        help="the GitHub Actions run: sends the alerts, never builds carousels (they need Claude, "
                             "which runs on Kint's laptop); stories that need one are marked 'needs Kint'")
    parser.add_argument("--carousels-only", action="store_true",
                        help="the laptop with the cloud on: build the waiting carousels, check no news, send no alerts")
    args = parser.parse_args(argv)

    (ROOT / "data").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(ROOT / "data" / "watcher.log", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    load_dotenv(ROOT / ".env")

    if laptop_must_skip(args):
        log.info("The cloud watcher is on (state/CLOUD-ON), so this laptop check sends nothing. "
                 "The cloud sends every Slack alert; use Sync with cloud.bat to build carousels and review.")
        return 0
    if args.carousels_only:
        return carousels_only()

    url = None
    if not args.dry_run:
        try:
            url = alert_step.webhook_url()
        except RuntimeError as exc:
            log.error("%s", exc)
            return 2

    now = datetime.now(timezone.utc)
    if not args.dry_run:
        check_health(now, url)
    settings = load_yaml("sources.yaml")
    rules = classify.normalize_rules(load_yaml("rules.yaml"))
    store = dedupe.Store(ROOT / "data" / "seen.sqlite", read_only_copy=args.dry_run)
    known_max_id = store.db.execute("SELECT COALESCE(MAX(id), 0) FROM stories").fetchone()[0]
    items, failures = fetch.fetch_all(settings)
    result = process(items, store, rules, not args.no_claude, now, rules.get("claude_model", "haiku"))

    if args.dry_run:
        path = alert_step.write_dry_run(
            [text for _, _, text in result["ready"]], details_text(result, failures),
            ROOT / "output", now,
        )
        log.info("Dry run finished. Nothing was sent. See %s", path)
        log_check("dry", result, failures, settings, 0)
        publish("dry", now, result, items, failures, settings,
                outcome_rows(result, {}, dry=True, known_max_id=known_max_id), 0)
        return 0

    sent = 0
    ready_status: dict[int, str] = {}
    for story, label, text in result["ready"]:
        try:
            alert_step.send_to_slack(text, url)
        except requests.RequestException as exc:
            # Not marked as alerted, so the next hourly run tries again.
            log.error("Slack send failed for %r: %s", story.title, type(exc).__name__)
            ready_status[id(story)] = FAILED
            activity.log_event("alert", "failed", f"{label}: {story.title}. Slack did not accept it "
                               f"({type(exc).__name__}); the next check tries again.")
            continue
        store.mark_alerted(story, label)
        ready_status[id(story)] = ALERTED
        sent += 1
        activity.log_event("alert", "sent", f"{label}: {story.title}")
    log.info("Sent %d of %d alerts. Held rumors: %d.", sent, len(result["ready"]), len(result["held"]))
    log_check("live", result, failures, settings, sent)
    publish("live", now, result, items, failures, settings,
            outcome_rows(result, ready_status, dry=False), sent)
    sent_now = [(story.id, story.title) for story, label, _ in result["ready"]
                if label == classify.OFFICIAL and ready_status.get(id(story)) == ALERTED]
    if args.cloud:
        cloud_carousel_step(ROOT / "data" / "seen.sqlite", sent_now, url)
    else:
        carousel_step(ROOT / "data" / "seen.sqlite", sent_now, url)
    return 0


def laptop_must_skip(args) -> bool:
    """With the cloud watcher on, a live check on the laptop would send the same alerts twice, so it is skipped.
    Practice runs and --carousels-only (no news check, no alerts) still run on the laptop."""
    if args.cloud or args.dry_run or args.carousels_only:
        return False
    try:
        import cloud_state
        return cloud_state.cloud_is_on(ROOT)
    except Exception:  # if the check itself fails, the old behaviour (a normal check) stays
        return False


def carousels_only() -> int:
    """The laptop's part when the cloud is on: build the carousels the cloud marked 'needs Kint' (official, sent,
    72 hours old or less, not built yet), within the same caps, then refresh the download zips and the page."""
    try:
        url = alert_step.webhook_url()
    except RuntimeError as exc:
        log.error("%s", exc)
        return 2
    carousel_step(ROOT / "data" / "seen.sqlite", [], url)
    try:
        import downloads
        downloads.ensure_zips(ROOT / "output" / "carousels", ROOT / "output" / "samples")
    except Exception as exc:
        log.error("Download zips were not checked: %s", type(exc).__name__)
    return 0


def cloud_carousel_step(db_path: Path, sent_now: list[tuple[int, str]], url: str) -> None:
    """The cloud never builds a carousel: the fact check and the official image check need Claude, which runs only
    on Kint's laptop, and nothing else may stand in for a real official image. Each story that needs a carousel is
    marked 'needs Kint' once (shown on the dashboard, one Slack note to Kint)."""
    try:
        import carousel_auto
        pending = carousel_auto.pending_stories(db_path, datetime.now(timezone.utc))
        sent_ids = {story_id for story_id, _ in sent_now}
        stories = list(sent_now) + [item for item in pending if item[0] not in sent_ids]
        carousel_auto.mark_needs_kint(db_path, stories, datetime.now(timezone.utc), url)
    except Exception as exc:
        log.error("Carousel step did not run: %s", type(exc).__name__)


def check_health(now: datetime, url: str) -> None:
    """At most one health message a day, to Kint. A problem here never stops the run."""
    try:
        health.run_if_needed(ROOT / "data" / "seen.sqlite", now, url)
    except Exception as exc:
        log.error("Health check did not run: %s", type(exc).__name__)


def carousel_step(db_path: Path, sent_now: list[tuple[int, str]], url: str) -> None:
    """Every live run: the stories sent in this run, plus official stories still waiting for a carousel."""
    try:
        import carousel_auto  # imported here, so a broken carousel module cannot stop the alert run
        pending = carousel_auto.pending_stories(db_path, datetime.now(timezone.utc))
        sent_ids = {story_id for story_id, _ in sent_now}
        stories = list(sent_now) + [item for item in pending if item[0] not in sent_ids]
        after_official_alerts(db_path, stories, datetime.now(timezone.utc), url)
    except Exception as exc:  # the alert run is already done; a carousel problem never fails it
        log.error("Carousel step did not run: %s", type(exc).__name__)


def after_official_alerts(db_path: Path, stories: list, now: datetime, url: str) -> list[str]:
    """Builds carousel drafts for the given (story id, title) pairs, within the caps. Imported here, so a
    broken carousel module cannot stop the alert run from starting."""
    import carousel
    import carousel_auto

    def build(story_id: int) -> dict:
        return carousel.run_story(str(story_id), None, render=True)

    outcomes = carousel_auto.after_alerts(db_path, stories, now, url, build)
    try:
        import dashboard  # a carousel result shows on the page straight away
        dashboard.write_dashboard(
            db_path=db_path,
            out_path=ROOT / "dashboard" / "index.html",
            sources_path=ROOT / "config" / "sources.yaml",
            rules_path=ROOT / "config" / "rules.yaml",
            carousels_dir=ROOT / "output" / "carousels",
            samples_dir=ROOT / "output" / "samples",
            now=datetime.now(timezone.utc),
        )
    except Exception as exc:
        log.error("Dashboard was not rebuilt after carousels: %s", type(exc).__name__)
    return outcomes


if __name__ == "__main__":
    sys.exit(main())
