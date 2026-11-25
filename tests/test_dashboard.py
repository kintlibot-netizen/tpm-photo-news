import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
import requests
import yaml
from conftest import ROOT, make_item

import alert
import dashboard
import run
import runlog
from classify import OFFICIAL, RUMOR
from dedupe import Store, Story

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
SECRET_TOKEN = "supersecrettoken123"
SECRET_URL = f"https://hooks.slack.com/services/T0AAAA/B0BBBB/{SECRET_TOKEN}"
HOSTILE = '<img src=x onerror="alert(1)"><script>alert(2)</script> Canon & Nikon'
COUNTS = {
    "articles": 40, "in_window": 12, "passed_rules": 5, "alerts_ready": 1,
    "alerts_sent": 1, "held": 1, "rejected": 1,
}
FEEDS = [
    {"feed": "PetaPixel", "ok": True, "items": 4, "error": None},
    {"feed": "Fuji Rumors", "ok": False, "items": 0, "error": "The site took too long to answer."},
]


def feed_names():
    with open(ROOT / "config" / "sources.yaml", encoding="utf-8") as handle:
        return [s["name"] for s in yaml.safe_load(handle)["sources"]]


def outcome(story_id, title, status, label=OFFICIAL, **extra):
    row = {
        "story_id": story_id, "title": title, "brand": "Canon", "category": "camera",
        "label": label, "status": status, "reason": "Reports a Canon release.",
        "summary": "Canon released it.", "first_seen": NOW.isoformat(),
        "sources": json.dumps([{"source": "PetaPixel", "link": "https://petapixel.example/r6"}]),
    }
    row.update(extra)
    return row


def sample_db(path, now=NOW):
    """A database with one alerted story, one held rumor, one rejected story and a dry-run story."""
    store = Store(path)
    alerted = Story(title="Canon Announces R6 Mark III", brand="Canon", kind="product", tokens=frozenset({"r6"}))
    alerted.sources = [{
        "url": "https://petapixel.example/r6", "link": "https://petapixel.example/r6?utm_source=x",
        "source": "PetaPixel", "source_type": "news", "title": alerted.title,
        "summary": "Canon says it is out. More text.", "published": now.isoformat(),
    }]
    store.save_story(alerted, now)
    store.mark_alerted(alerted, OFFICIAL)

    held = Story(title="Canon R6 Mark IV rumored specs", brand="Canon", kind="product", tokens=frozenset({"r6"}))
    held.sources = [{
        "url": "https://rumors.example/r6iv", "link": "https://rumors.example/r6iv", "source": "Canon Rumors",
        "source_type": "rumor", "title": held.title, "summary": "Text.", "published": now.isoformat(),
    }]
    store.save_story(held, now)

    dismissed = Story(title="Canon Printer Ink Refill", brand="Canon", kind="product", tokens=frozenset())
    dismissed.sources = [{
        "url": "https://news.example/ink", "link": "https://news.example/ink", "source": "DPReview",
        "source_type": "news", "title": dismissed.title, "summary": "Text.", "published": now.isoformat(),
    }]
    store.save_story(dismissed, now)
    store.mark_dismissed(dismissed)
    store.db.close()

    runlog.record_run(
        path, "live", now - timedelta(hours=1), now - timedelta(minutes=50), COUNTS, FEEDS,
        [
            outcome(alerted.id, alerted.title, runlog.ALERTED),
            outcome(held.id, held.title, runlog.HELD, label=RUMOR, reason="Only one site has reported it so far."),
            outcome(dismissed.id, dismissed.title, runlog.REJECTED, label=OFFICIAL),
            outcome(None, "Canon Dry Story", runlog.DRY_ONLY, sources="[]"),
        ],
    )
    return path


def build(tmp_path, db, now=NOW):
    out = tmp_path / "dashboard" / "index.html"
    dashboard.write_dashboard(
        db_path=db, out_path=out, sources_path=ROOT / "config" / "sources.yaml",
        rules_path=ROOT / "config" / "rules.yaml", now=now,
    )
    return out.read_text(encoding="utf-8")


def test_dashboard_renders_sample_stories_and_required_sections(tmp_path):
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    # Round 12 redesign: the page shows the news worth seeing (sent, or waiting for a 2nd source). Rejected and
    # practice run stories, the run history and the story filters are no longer on the page (their data is kept).
    for text in [
        "TPM Photo News", "Sent to Slack", "Waiting for a 2nd source",
        "Canon Announces R6 Mark III", "Canon R6 Mark IV rumored specs",
        "Feed health", "Carousels", "Photo news", "No carousels to review right now",
    ]:
        assert text in page, text
    for text in ["Rejected: not relevant", "Practice run only", "Canon Dry Story", "Run history", 'id="f-status"']:
        assert text not in page, text
    for name in feed_names():
        assert name in page, name


def test_stories_keep_all_sources_as_links(tmp_path):
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    assert 'href="https://petapixel.example/r6?utm_source=x"' in page


def test_last_check_is_shown_in_asia_manila_time(tmp_path):
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    # 11:10 UTC is 19:10 in Manila (UTC+8). The health line gives the time alone when the check was today.
    assert "Last check 7:10 PM" in page and "(Asia/Manila)" in page


def test_summary_numbers_are_correct(tmp_path):
    db = sample_db(tmp_path / "seen.sqlite")
    stories = dashboard.build_stories(dashboard.read_database(db), None)
    numbers = dashboard.summarize(stories, NOW)
    assert numbers["today"] == 1 and numbers["week"] == 1 and numbers["undated"] == 0
    assert numbers["waiting"] == 1 and numbers["rejected"] == 1


def test_webhook_secret_never_reaches_the_page(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SECRET_URL)
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    assert SECRET_TOKEN not in page
    assert "hooks.slack.com" not in page


def test_dashboard_code_never_reads_the_secret():
    text = (ROOT / "src" / "dashboard.py").read_text(encoding="utf-8")
    assert "SLACK_WEBHOOK" not in text and "load_dotenv" not in text


def test_headlines_and_feed_text_are_escaped(tmp_path):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    hostile = Story(title=HOSTILE, brand="Canon", kind="product", tokens=frozenset())
    hostile.sources = [{
        "url": "https://evil.example/a", "link": "javascript:alert(3)", "source": "<b>Evil</b>",
        "source_type": "news", "title": HOSTILE, "summary": "<img src=x onerror=alert(4)>", "published": None,
    }]
    store.save_story(hostile, NOW)
    store.db.close()
    runlog.record_run(
        db, "live", NOW - timedelta(hours=1), NOW, COUNTS, FEEDS,
        [outcome(hostile.id, HOSTILE, runlog.ALERTED, summary="<img src=x onerror=alert(4)>",
                 sources=json.dumps([{"source": "<b>Evil</b>", "link": "javascript:alert(3)"}]))],
    )
    page = build(tmp_path, db)
    assert "<img src=x" not in page and "<script>alert(2)" not in page
    assert "&lt;script&gt;alert(2)&lt;/script&gt;" in page
    assert "&lt;b&gt;Evil&lt;/b&gt;" in page
    assert 'href="javascript' not in page


def test_page_needs_no_network_or_server(tmp_path):
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    assert "<link" not in page and "<script src" not in page and "@import" not in page
    assert "<img" not in page and "url(http" not in page
    assert "Content-Security-Policy" in page


def test_missing_database_still_builds_an_empty_page(tmp_path):
    page = build(tmp_path, tmp_path / "none.sqlite")
    assert "No check recorded yet." in page
    assert "No carousels to review right now" in page and "No big brand news in the last two weeks" in page


def test_existing_data_survives_the_new_tables(tmp_path):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    story = Story(title="Canon Announces R6 Mark III", brand="Canon", kind="product", tokens=frozenset({"r6"}))
    story.sources = [{"url": "https://a.example/1", "link": "https://a.example/1", "source": "PetaPixel",
                      "source_type": "news", "title": story.title, "summary": "S.", "published": None}]
    store.save_story(story, NOW)
    store.mark_alerted(story, OFFICIAL)
    store.db.close()

    runlog.record_run(db, "live", NOW, NOW, COUNTS, FEEDS, [])
    runlog.record_run(db, "dry", NOW, NOW, COUNTS, FEEDS, [])
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 1
    assert conn.execute("SELECT last_alert_label FROM stories").fetchone()[0] == OFFICIAL
    conn.close()
    Store(db)  # the watcher still opens its own memory


def test_stories_from_before_run_history_are_still_shown(tmp_path):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    old = Story(title="Adobe Releases Photoshop 27.1", brand="Adobe", kind="product", tokens=frozenset())
    old.sources = [{"url": "https://a.example/ps", "link": "https://a.example/ps", "source": "PetaPixel",
                    "source_type": "news", "title": old.title, "summary": "Adobe shipped it. More.",
                    "published": None}]
    store.save_story(old, NOW)
    store.mark_alerted(old, OFFICIAL)
    store.db.close()
    page = build(tmp_path, db)
    assert "Adobe Releases Photoshop 27.1" in page
    assert "Recorded before run history began" not in page and "Sent to Slack" in page


def test_repeated_status_is_not_saved_again(tmp_path):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    held = Story(title="Canon R6 Mark IV rumored specs", brand="Canon", kind="product", tokens=frozenset())
    store.save_story(held, NOW)
    store.db.close()
    for hour in range(3):
        runlog.record_run(db, "live", NOW + timedelta(hours=hour), NOW, COUNTS, FEEDS,
                          [outcome(held.id, held.title, runlog.HELD, label=RUMOR)])
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM story_outcomes").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3
    conn.close()


def test_the_page_reads_only_the_latest_check_and_shows_no_run_history(tmp_path):
    # Round 12: the 20 row run history table is gone; the health line uses the latest check only.
    db = tmp_path / "seen.sqlite"
    for hour in range(25):
        runlog.record_run(db, "live", NOW + timedelta(hours=hour), NOW, COUNTS, FEEDS, [])
    assert len(dashboard.read_database(db)["runs"]) == 1
    page = build(tmp_path, db)
    assert "Run history" not in page and "<tr><td>" not in page


@pytest.mark.parametrize(
    "raw, plain",
    [
        ("Fuji Rumors: Read timed out.", "The site took too long to answer."),
        ("X: HTTPSConnectionPool(host='x', port=443): Failed to establish a new connection", "Could not connect to the site."),
        ("DPReview: 403 Client Error: Forbidden for url: https://x", "The site returned an error (403)."),
        ("PetaPixel: 503 Server Error: Service Unavailable", "The site returned an error (503)."),
        ("Y: not a readable feed: syntax error", "The site did not return a readable feed. It may have changed."),
        ("Z: feed is larger than 10485760 bytes", "The feed was too large to read."),
    ],
)
def test_feed_errors_are_plain_words(raw, plain):
    assert runlog.plain_error(raw) == plain


def test_dry_run_saves_history_and_rebuilds_the_page(monkeypatch, tmp_path):
    item = make_item("Canon Announces R6 Mark III")
    item.published = datetime.now(timezone.utc) - timedelta(hours=1)
    project(monkeypatch, tmp_path, [item], {"Broken Feed": "Read timed out."})
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SECRET_URL)

    def forbidden(*args, **kwargs):
        raise AssertionError("dry run tried to post")

    monkeypatch.setattr(requests, "post", forbidden)
    assert run.main(["--dry-run", "--no-claude"]) == 0
    page = (tmp_path / "dashboard" / "index.html").read_text(encoding="utf-8")
    # A practice run story is not news, so it is not on the page; the feed health still shows the failed feed.
    assert "Practice run only" not in page
    assert "Broken Feed" in page and "The site took too long to answer." in page
    assert "feeds OK" in page and SECRET_TOKEN not in page


def test_live_run_marks_the_alert_and_rebuilds_the_page(monkeypatch, tmp_path):
    item = make_item("Canon Announces R6 Mark III")
    item.published = datetime.now(timezone.utc) - timedelta(hours=1)
    project(monkeypatch, tmp_path, [item], {})
    # The auto-carousel step after an official alert is tested on its own (test_phase3); here it is off,
    # so the only Slack post this run makes is the alert.
    monkeypatch.setattr(run, "after_official_alerts", lambda *a, **k: [])
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SECRET_URL)
    sent = []

    class Accepted:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "post", lambda url, json, timeout: sent.append(url) or Accepted())
    monkeypatch.setattr(alert.time, "sleep", lambda seconds: None)
    assert run.main(["--no-claude"]) == 0
    assert sent == [SECRET_URL]
    page = (tmp_path / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert "Sent to Slack" in page and "Canon Announces R6 Mark III" in page
    assert SECRET_TOKEN not in page


def test_a_broken_dashboard_never_fails_the_run(monkeypatch, tmp_path):
    item = make_item("Canon Announces R6 Mark III")
    item.published = datetime.now(timezone.utc) - timedelta(hours=1)
    project(monkeypatch, tmp_path, [item], {})

    def broken(**kwargs):
        raise RuntimeError("disk full")

    # run imports the dashboard inside publish(), so the module itself is patched.
    monkeypatch.setattr(dashboard, "write_dashboard", broken)
    assert run.main(["--dry-run", "--no-claude"]) == 0
    assert (tmp_path / "data" / "seen.sqlite").exists()


def project(monkeypatch, tmp_path, items, failures):
    """Points the watcher at a temp folder with copies of the real config, and fakes the feeds."""
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    for name in ("sources.yaml", "rules.yaml"):
        (tmp_path / "config" / name).write_text((ROOT / "config" / name).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(run.fetch, "fetch_all", lambda config: (items, failures))
