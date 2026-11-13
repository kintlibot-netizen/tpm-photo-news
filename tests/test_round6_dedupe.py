"""Functional round, item 3: model tokens that catch ZR and "Cine Play 1", merging across rumour and news sites,
and the Sigma name guard. The headlines are real ones from the dry-run records, except where marked."""
import pytest
from conftest import make_item

import dedupe
from classify import OFFICIAL, RUMOR, alert_decision, is_candidate, item_label
from dedupe import Store, find_story_brand, group_into_stories, model_tokens

# Nikon ZR firmware: Nikon Rumors and Digital Camera World (real headlines).
NIKON_ZR_RUMOR_SITE = "YouTuber leaks the release date for the Nikon ZR firmware update 2.0: November 24th"
NIKON_ZR_NEWS_SITE = "Nikon ZR firmware update could be just weeks away, according to YouTube leak"
# Fujifilm X-T5/X-H2 firmware: the Fuji Rumors headline is real. The second headline is written for this test,
# because the database had no second report of it.
FUJI_FIRMWARE = "Firmware Updates for Fujifilm X-T5, X-H2 and X-H2S"
FUJI_SECOND_REPORT = "Fujifilm X-H2S firmware update released"
# Leica Cine Play 1 Plus: Camera Jabber's and the Leica headlines (real).
LEICA_UNVEILS = "Leica Unveils Cine Play 1 Plus 4K Projector With 4,200 Lumens"
LEICA_PRICE = "Leica Cine Play 1 Plus price, specifications and availability announced"


def group(items, store, rules, now):
    return group_into_stories(
        items, store, rules["same_story_window_days"], rules["title_similarity"], rules["brands"], now
    )


def test_zr_is_a_model_token_in_both_nikon_zr_headlines():
    assert "zr" in model_tokens(NIKON_ZR_NEWS_SITE)
    assert "zr" in model_tokens(NIKON_ZR_RUMOR_SITE)


def test_cine_play_number_is_a_model_token_in_both_leica_headlines():
    assert "play 1" in model_tokens(LEICA_UNVEILS)
    assert "play 1" in model_tokens(LEICA_PRICE)


def test_announces_before_a_number_is_not_a_model_name():
    assert model_tokens("Sony Announces 2 cameras") == frozenset()


def test_ai_and_usb_are_not_model_names():
    assert model_tokens("Canon AI autofocus and USB charging announced") == frozenset()


def test_nikon_zr_rumour_site_and_news_site_are_one_story(rules, now):
    stories = group(
        [make_item(NIKON_ZR_RUMOR_SITE, source="Nikon Rumors", source_type="rumor"),
         make_item(NIKON_ZR_NEWS_SITE, source="Digital Camera World")],
        Store(), rules, now,
    )
    assert len(stories) == 1
    assert {s["source"] for s in stories[0].sources} == {"Nikon Rumors", "Digital Camera World"}


def test_fujifilm_firmware_reports_are_one_story(rules, now):
    stories = group(
        [make_item(FUJI_FIRMWARE, source="Fuji Rumors", source_type="rumor"),
         make_item(FUJI_SECOND_REPORT, source="DPReview")],
        Store(), rules, now,
    )
    assert len(stories) == 1 and len(stories[0].sources) == 2


def test_leica_cine_play_reports_are_one_story(rules, now):
    stories = group(
        [make_item(LEICA_UNVEILS, source="Camera Jabber"), make_item(LEICA_PRICE, source="Digital Camera World")],
        Store(), rules, now,
    )
    assert len(stories) == 1 and len(stories[0].sources) == 2


def test_a_rumour_site_and_a_news_site_are_two_independent_sources(rules, now):
    stories = group(
        [make_item(NIKON_ZR_RUMOR_SITE, source="Nikon Rumors", source_type="rumor"),
         make_item(NIKON_ZR_NEWS_SITE, source="Digital Camera World")],
        Store(), rules, now,
    )
    story = stories[0]
    assert alert_decision(story, rules) == (True, RUMOR, "rumor reached the source minimum")


def test_one_rumour_site_alone_is_still_held(rules, now):
    stories = group([make_item(NIKON_ZR_RUMOR_SITE, source="Nikon Rumors", source_type="rumor")],
                    Store(), rules, now)
    assert alert_decision(stories[0], rules)[0] is False


def test_the_zr_rumour_site_item_is_a_candidate(rules):
    assert is_candidate(make_item(NIKON_ZR_RUMOR_SITE, source="Nikon Rumors", source_type="rumor"), rules)


@pytest.mark.parametrize("title", [
    "Sigma 85mm f/1.4 DG DN released",
    "Sigma 24-70mm lens update released",
])
def test_sigma_with_a_lens_or_model_word_is_the_brand(title, rules):
    assert find_story_brand(title, "", rules["brands"]) == "Sigma"


def test_sigma_as_an_ordinary_word_is_not_the_brand(rules):
    assert find_story_brand("Sigma-delta modulation explained", "", rules["brands"]) is None


def test_sigma_as_an_ordinary_word_is_not_a_candidate(rules):
    assert not is_candidate(make_item("Sigma-delta modulation released in new chip"), rules)


def test_a_real_brand_title_still_matches_its_brand_with_the_guard_loaded(rules):
    assert isinstance(rules["brands"], dedupe.BrandMap)
    assert find_story_brand("Canon Announces R6 Mark III", "", rules["brands"]) == "Canon"
