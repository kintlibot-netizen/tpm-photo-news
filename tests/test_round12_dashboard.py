"""Round 12, the dashboard redesign: four sections with the carousels to review first, recent big brand news, one
short health line, and nothing outdated on the page (run history, activity log, hidden, rejected or skipped stories).
Kint's page and David's read only copy share the same template. Temporary data only."""
import re
from datetime import datetime, timedelta, timezone

import yaml
from conftest import ROOT
from test_dashboard import sample_db

import carousel_status
import dashboard
import dashboard_assets
import runlog
from test_round7_downloads import PASSING, carousel

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
DASHES = ("\u2014", "\u2013")


def build(tmp_path, db=None, carousels_dir=None, **kwargs):
    page, _ = dashboard.build_page(
        db_path=db or tmp_path / "none.sqlite", sources_path=ROOT / "config" / "sources.yaml",
        rules_path=ROOT / "config" / "rules.yaml", now=NOW, carousels_dir=carousels_dir or tmp_path / "carousels",
        samples_dir=tmp_path / "samples", **kwargs)
    return page


def story(title, status, days_ago=0, label="OFFICIAL", story_id=1, brand="Canon"):
    moment = NOW - timedelta(days=days_ago)
    return {"story_id": story_id, "title": title, "brand": brand, "label": label, "status": status, "summary": "",
            "sources": [{"source": "PetaPixel", "link": "https://petapixel.example/x"}], "first_seen": moment,
            "sent_at": moment if status == runlog.ALERTED else None}


def test_both_pages_open_on_the_carousels_and_have_the_same_four_sections(tmp_path):
    db = sample_db(tmp_path / "seen.sqlite")
    carousel(tmp_path / "carousels")
    local = build(tmp_path, db)
    share = build(tmp_path, db, read_only=True, base_for=lambda c: f"carousels/{c['name']}")
    for page in (local, share):
        assert re.findall(r'data-page="([a-z]+)"', page) == ["review", "news", "system", "how"]
        assert 'data-home="review"' in page
        first = page.index('data-page="review"')
        assert first < page.index('data-page="news"') and 'data-page="review">' in page  # the home page is not hidden
        assert page.index('class="tiles"') < page.index('class="carousel-card"')  # the hero stats, then the gallery
    assert "Read only copy. To approve a carousel, tell Kint." in share and 'class="banner"' in share
    assert 'class="banner"' not in local


def test_nothing_outdated_is_on_the_page(tmp_path):
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    for gone in ("Run history", "Start here", "Overview", "Needs your attention", "Every official story and its "
                 "carousel", "Pipeline", "This week", 'id="activity-list"', 'id="story-list"', "Practice run only",
                 "Canon Printer Ink Refill", "Rejected: not relevant", "carousel bot", "Coming in Phase 2",
                 'id="drawer"', "applyStories", "applyActivity"):
        assert gone not in page, gone


def test_the_carousel_card_is_a_gallery_card_with_the_details_folded(tmp_path):
    folder = carousel(tmp_path / "carousels")
    page = build(tmp_path)
    name = folder.name
    assert 'class="slide cover"' in page and 'class="cover-badge"' in page  # the big cover, with the slide count
    assert page.count(f'data-lb="lb-{name}"') == 4 and f'data-lb="lb-{name}-c"' in page  # every slide enlarges
    assert '<details class="caps" open><summary>Captions, ready to copy</summary>' in page
    assert '<details class="more"><summary>Fact check and sources</summary>' in page
    assert page.index('class="caps"') < page.index('class="more"')
    assert 'id="lightbox"' in page and "Download all slides (ZIP)" in page and 'data-kind="caption"' in page


def test_the_review_list_puts_waiting_for_david_first_and_drops_rejected_and_samples(tmp_path):
    base = tmp_path / "carousels"
    rejected = carousel(base, name="2026-11-12-rejected-one")
    carousel_status.set_status(rejected, "rejected", reason="Wrong product")
    carousel(base, name="2026-11-01-waiting-one")
    preview = carousel(tmp_path / "previews", name="2026-11-13-preview-one")
    carousel(tmp_path / "samples", name="2026-11-11-x-sample", build=dict(PASSING, sample=True))
    cards = dashboard.read_carousels(base, tmp_path / "samples", tmp_path / "previews")
    names = [c["name"] for c in dashboard.ready_cards(cards)]
    assert names == ["2026-11-01-waiting-one", preview.name]


def test_photo_news_keeps_the_last_two_weeks_of_sent_and_waiting_stories(tmp_path):
    stories = [
        story("Canon R1 Mark II announced", runlog.ALERTED, 1, story_id=1),
        story("Sony A1 III rumored", runlog.HELD, 2, label="RUMOR", story_id=2),
        story("Old launch", runlog.ALERTED, 20, story_id=3),
        story("Printer ink", runlog.REJECTED, 1, story_id=4),
        story("A photo of the week", runlog.SKIPPED, 1, story_id=5),
        story("Practice", runlog.DRY_ONLY, 1, story_id=None),
    ]
    titles = [s["title"] for s in dashboard.recent_news(stories, NOW)]
    assert titles == ["Canon R1 Mark II announced", "Sony A1 III rumored"]
    html = dashboard.news_panel(stories, NOW)
    # sent stories first; rumors waiting for a 2nd source are folded below
    assert html.index("Canon R1 Mark II announced") < html.index("Rumors waiting for a 2nd source (1)")
    assert '<details class="more held">' in html and "Old launch" not in html


def test_photo_news_has_a_friendly_empty_state():
    html = dashboard.news_panel([], NOW)
    assert 'class="empty-state"' in html and "No big brand news in the last two weeks" in html


def test_the_health_line_is_one_short_sentence_in_manila_time():
    latest = {"started_at": (NOW - timedelta(minutes=55)).isoformat(),
              "finished_at": (NOW - timedelta(minutes=50)).isoformat(), "feeds_ok": 13, "feeds_failed": 1}
    text, cls = dashboard.health_line(latest, NOW + timedelta(minutes=10), NOW)
    assert text == "Last check 7:10 PM, 13 of 14 feeds OK, next 8:10 PM (Asia/Manila)" and cls == "st-held"
    assert dashboard.health_line(None, None, NOW)[0] == "No check recorded yet."
    assert dashboard.short_time(NOW - timedelta(days=1), NOW) == "Nov 10, 8:00 PM"


def test_story_67_is_hidden_by_hand_and_stays_in_the_data():
    rules = yaml.safe_load((ROOT / "config" / "rules.yaml").read_text(encoding="utf-8"))
    assert 67 in rules["hidden_story_ids"]  # the Nikon "vibe coding" opinion piece
    stories = [story("Nikon and vibe coding", runlog.ALERTED, story_id=67, brand="Nikon"),
               story("Nikon Z9 II camera announced", runlog.ALERTED, story_id=68, brand="Nikon")]
    shown, hidden = dashboard.split_hidden(stories, dashboard.load_rules(ROOT / "config" / "rules.yaml"))
    assert [s["story_id"] for s in shown] == [68] and [s["story_id"] for s in hidden] == [67]
    assert "Hidden by Kint" in hidden[0]["hidden"]


def test_the_page_is_responsive_accessible_and_has_no_dashes(tmp_path):
    carousel(tmp_path / "carousels")
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    css = dashboard_assets.CSS
    assert "@media (max-width:860px)" in css and "prefers-reduced-motion" in css
    assert ':focus-visible' in css and 'aria-label="Sections"' in page and 'role="dialog"' in page
    assert "details.caps" in dashboard_assets.JS  # phones fold the captions so the slides come first
    for dash in DASHES:
        assert dash not in page


def test_the_read_only_copy_keeps_no_controls(tmp_path):
    carousel(tmp_path / "carousels")
    share = build(tmp_path, sample_db(tmp_path / "seen.sqlite"), read_only=True,
                  base_for=lambda c: f"carousels/{c['name']}")
    for gone in ('id="reviewer"', 'id="export-david"', "data-action=", 'data-kind="command"', "PowerShell"):
        assert gone not in share, gone
    assert '<div class="review-area"><div class="review"><span class="tag st-accent">Waiting for David</span>' in share
