"""Round 10 (Nov 25): Kint's big brand allowlist and photographer relevance gate, both kept in config/rules.yaml.
Items that fail are not new stories, are never alerted on Slack, and old ones are hidden from the dashboard and
David's page without deleting anything."""
from datetime import datetime, timezone

import pytest

import classify
import dashboard
from fetch import Item

NOW = datetime(2026, 11, 25, 3, 0, tzinfo=timezone.utc)


def item(title, summary=""):
    return Item(source="Test", source_type="news", title=title, url="https://example.com/a", summary=summary,
                published=NOW)


def test_the_allowlist_and_the_gate_live_in_the_rules_file(rules):
    big = set(rules["big_brands"])
    for name in ("Canon", "Nikon", "Sony", "Fujifilm", "Panasonic", "OM System", "Leica", "Hasselblad", "Sigma",
                 "Tamron", "DJI", "GoPro", "Insta360", "Adobe", "Capture One", "Skylum", "Apple", "Google",
                 "Blackmagic Design"):
        assert name in big
    assert not {"Sirui", "Meike", "TTArtisan", "7Artisans", "Thypoch", "Voigtlander", "Ricoh"} & big
    for key in classify.RELEVANCE_KEYS:
        assert rules["photo_relevance"][key], key


@pytest.mark.parametrize("title", [
    "Canon announces the EOS R7 Mark II",
    "Sony launches the FE 50mm f/1.4 GM II lens",
    "Leica announced M-A and M11-P Hammertone Special Edition cameras",
    "Fujifilm releases firmware update with new film simulation for the X-T5",
    "Adobe Lightroom update adds a new Glow tool",
    "Capture One 17 released with new AI masking",
    "Skylum Luminar has been updated with new tools",
    "DJI launches the Mavic 5 Pro drone with a Hasselblad camera",
    "Apple announces iPhone 18 Pro with a new 48MP telephoto camera",
])
def test_big_brand_photo_news_still_gets_through(rules, title):
    assert classify.candidate_problem(item(title), rules) is None


@pytest.mark.parametrize("title,why", [
    ("SIRUI Aurora 15mm F1.6 lens price and availability announced", "not a big photography brand"),
    ("Just announced: New TTArtisan AF 12mm f/2.8 FE lens", "not a big photography brand"),
    ("Mitakon Zhong Yi 45mm f/1.4 for Fujifilm GFX Available", "made by Mitakon"),
    ("Vistilen AF 35mm f/1.8 lens for Canon cameras announced", "made by Vistilen"),
    ("Owlkrown released a new grip for the Fujifilm X-E5 cameras", "made by Owlkrown"),
    ("Ricoh firmware updates 11 GR cameras", "not a big photography brand"),
])
def test_small_and_third_party_brands_are_filtered(rules, title, why):
    problem = classify.candidate_problem(item(title), rules)
    assert problem and why in problem


@pytest.mark.parametrize("title,summary,why", [
    ("DJI ROMO P2 UK price and availability announced", "The robot vacuum mops and cleans on its own.",
     "not for photographers"),
    ("Leica Unveils Cine Play 1 Plus 4K Projector With 4,200 Lumens", "", "not for photographers"),
    ("Fujifilm announces record revenue of $5.6 billion", "", "corporate, financial"),
    ("GoPro announces merger with Starman", "", "corporate, financial"),
    ("Sony A7 IV open gate vibe coded firmware is now available", "", "unofficial"),
    ("Sony ECM-W5 firmware 1.1 released, fixes wireless monitoring audio interruptions", "", "minor bug fix"),
    ("Fujifilm firmware update released for three X series cameras, bug fixed", "", "minor bug fix"),
    ("DJI launches new Mic 3 wireless microphone", "Two transmitters and a receiver.", "no camera or photo angle"),
])
def test_off_topic_news_is_filtered(rules, title, summary, why):
    problem = classify.candidate_problem(item(title, summary), rules)
    assert problem and why in problem.lower()


def test_a_kit_that_mentions_headphones_in_the_excerpt_is_still_shown(rules):
    title = "Canon EOS C50 and C80 lens kits price, specifications and availability announced"
    assert classify.candidate_problem(item(title, "The kit adds a lens, a mic and headphones."), rules) is None


def test_phone_news_with_no_camera_angle_is_not_a_story(rules):
    assert not classify.is_candidate(item("Apple announces new iPhone 18 colors"), rules)


def test_without_the_lists_nothing_is_gated(rules):
    open_rules = dict(rules, big_brands=[], photo_relevance={key: [] for key in classify.RELEVANCE_KEYS})
    assert classify.gate_problem("SIRUI Aurora 15mm lens announced", "", "Sirui", open_rules) is None


def test_a_filtered_item_is_never_a_candidate_so_never_reaches_slack(rules):
    assert not classify.is_candidate(item("DJI ROMO P2 robot vacuum launches in the UK"), rules)
    assert classify.is_candidate(item("Nikon announces the Z5 III camera"), rules)


def test_stored_stories_are_skipped_with_the_gate_reason(rules):
    sources = [{"source": "Site", "title": "Meike AF 58mm f/1.2 MIX price, specifications and availability announced",
                "summary": ""}]
    reason = classify.story_skip_reason(sources, rules)
    assert reason and "not a big photography brand" in reason


def story(title, brand, status="alerted", summary=""):
    return {"title": title, "brand": brand, "status": status,
            "sources": [{"source": "Site", "title": title, "summary": summary}]}


def test_the_dashboard_hides_old_stories_that_fail_without_deleting_them(rules):
    keep = story("Sigma fp2 demand outstrips supply in Japan ahead of 11 November launch", "Sigma")
    sirui = story("SIRUI Unveils the Swift Series: Compact, All-Glass Full-Frame Autofocus Lenses", "Sirui")
    romo = story("DJI ROMO P2 UK price and availability announced", "DJI",
                 summary="DJI's ROMO P2 robot vacuum is now on sale in the UK.")
    shown, hidden = dashboard.split_hidden([keep, sirui, romo], rules)
    assert shown == [keep] and hidden == [sirui, romo]
    assert "not a big photography brand" in sirui["hidden"] and "robot vacuum" in romo["hidden"]


def test_cards_of_hidden_stories_are_left_off_the_page(rules):
    romo = story("DJI ROMO P2 UK price and availability announced", "DJI", summary="A robot vacuum.")
    cards = [{"name": "2026-11-19-" + dashboard.folder_slug(romo["title"])},
             {"name": "2026-11-11-sigma-fp2-demand-outstrips-supply-in-japan-ahead-of-11-novem"}]
    kept = dashboard.hide_cards(cards, [romo])
    assert [c["name"] for c in kept] == ["2026-11-11-sigma-fp2-demand-outstrips-supply-in-japan-ahead-of-11-novem"]


def test_no_gate_reason_uses_a_dash(rules):
    reasons = [classify.candidate_problem(item(t, s), rules) for t, s in (
        ("SIRUI lens announced", ""), ("DJI ROMO P2 announced", "robot vacuum"),
        ("Canon revenue up", ""), ("Sony firmware fixes bugs", ""))]
    assert all(r and "\u2013" not in r and "\u2014" not in r and " - " not in r for r in reasons)
