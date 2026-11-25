"""Round 11 (Nov 25 evening): health check fixes. A third party app "for iPhone" is not Apple news, the page lists only
the big brands, the cloud workflow uses current GitHub Actions and is scheduled twice an hour."""
from pathlib import Path

import classify
import dashboard
from fetch import Item
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 25, 14, 0, tzinfo=timezone.utc)
MASOC = "masoc RAW photo and video editor for iPhone, iPad and Mac price and availability announced"


def item(title, summary=""):
    return Item(source="Test", source_type="news", title=title, url="https://example.com/a", summary=summary,
                published=NOW)


def test_an_app_for_iphone_is_not_apple_news(rules):
    assert classify.find_story_brand(MASOC, "", rules["brands"]) is None
    assert not classify.is_candidate(item(MASOC), rules)


def test_apple_camera_news_still_counts(rules):
    assert classify.is_candidate(item("Apple announces iPhone 18 Pro with a new 48MP camera"), rules)


def test_an_old_story_stored_under_a_wrong_brand_is_hidden(rules):
    story = {"title": MASOC, "brand": "Apple", "status": "alerted",
             "sources": [{"source": "Photo Rumors", "title": MASOC, "summary": "Edit Apple ProRAW photos."}]}
    shown, hidden = dashboard.split_hidden([story], rules)
    assert shown == [] and "not a big photography brand" in story["hidden"]


def test_a_story_with_no_source_text_uses_its_stored_brand(rules):
    assert classify.story_gate_problem([], "Sigma", "Sigma fp2 demand outstrips supply in Japan", rules) is None


def test_the_sources_page_lists_only_the_big_brands(rules):
    page = dashboard.sources_panel([], [], rules)
    assert "Big photography brands the watcher follows" in page
    for name in ("Canon", "Leica", "Capture One"):
        assert name in page
    for name in ("Sirui", "TTArtisan", "Thypoch", "Meike", "Voigtlander", "darktable"):
        assert name not in page
    assert "luminar" in page


def test_the_workflow_uses_node_24_actions_and_two_schedules():
    text = (ROOT / ".github" / "workflows" / "watch.yml").read_text(encoding="utf-8")
    for old in ("checkout@v4", "setup-python@v5", "upload-pages-artifact@v3", "deploy-pages@v4"):
        assert old not in text
    for new in ("actions/checkout@v7", "actions/setup-python@v7", "actions/upload-pages-artifact@v5",
                "actions/deploy-pages@v5"):
        assert new in text
    assert '"7 * * * *"' in text and '"37 * * * *"' in text
