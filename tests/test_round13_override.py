"""Kint's one-off official override (rules.yaml official_override_stories): only story 21 may skip the rumor rule."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import carousel
import classify
import dashboard
import runlog

ROOT = Path(__file__).resolve().parents[1]
NIKON_GLOBAL = "https://www.nikon.com/company/news/2026/1029_01/"
NIKON_USA = "https://www.nikonusa.com/press-room/NIKKOR-Z-120-300mm"


def rules():
    return carousel.load_rules()


def rumor_story(story_id):
    return SimpleNamespace(id=story_id, last_alert_label=None, claude_label=classify.RUMOR, sources=[],
                           title="The new Nikon lens is expected to ship tomorrow", brand="Nikon")


def test_only_story_21_is_on_the_override_list_with_the_official_nikon_pages():
    table = rules()["official_override_stories"]
    assert list(table) == [21]
    assert table[21]["official_urls"] == [NIKON_GLOBAL, NIKON_USA]
    assert carousel.official_override(21, rules())["approved_by"] == "Kint"
    for other in (20, 22, 67, "21x", None):
        assert carousel.official_override(other, rules()) is None


def test_story_21_may_make_a_carousel_and_every_other_rumor_is_still_refused():
    carousel.check_eligible(rumor_story(21), rules())
    for other in (2, 20, 22, 99):
        with pytest.raises(carousel.Refused):
            carousel.check_eligible(rumor_story(other), rules())
    sent_as_rumor = rumor_story(22)
    sent_as_rumor.last_alert_label = classify.RUMOR
    with pytest.raises(carousel.Refused, match="rumor"):
        carousel.check_eligible(sent_as_rumor, rules())


def test_an_entry_with_no_official_page_lets_nothing_through():
    loose = {"official_override_stories": {30: {"approved_by": "Kint"}}}
    assert carousel.official_override(30, loose) is None
    with pytest.raises(carousel.Refused):
        carousel.check_eligible(rumor_story(30), loose)


def held(story_id, now):
    return {"story_id": story_id, "title": "Nikon lens is expected to ship tomorrow", "brand": "Nikon",
            "category": "", "label": classify.RUMOR, "status": runlog.HELD, "reason": "", "summary": "",
            "first_seen": now - timedelta(days=2),
            "sources": [{"source": "Nikon Rumors", "link": "https://nikonrumors.com/2026/11/11/lens/"}]}


def test_the_page_shows_the_official_nikon_source_for_story_21_not_the_rumor_article():
    now = datetime(2026, 11, 27, tzinfo=timezone.utc)
    stories = dashboard.apply_official_overrides([held(21, now), held(22, now)], rules())
    nikon, other = stories
    assert [s["link"] for s in nikon["sources"]] == [NIKON_GLOBAL, NIKON_USA]
    assert nikon["label"] == classify.OFFICIAL and nikon["title"].startswith("Nikon releases the NIKKOR Z 120-300mm")
    assert other["label"] == classify.RUMOR and "nikonrumors" in other["sources"][0]["link"]
    html = dashboard.news_panel(stories, now)
    main, folded = html.split("Rumors waiting for a 2nd source")
    assert NIKON_GLOBAL in main and "Confirmed on the official page" in main
    assert "nikonrumors.com/2026/11/11/lens" not in main
    assert "nikonrumors" in folded and NIKON_GLOBAL not in folded
