"""Functional round, item 4 (rumour-site headlines, how-to and opinion skips) and item 11 (more brands, editing
software, lighting and storage makers, and the false-match guards for RED, Affinity, Kodak, GIMP, Luminar, Sigma, ON1)."""
import pytest
from conftest import make_item

import classify
from classify import OFFICIAL, RUMOR, item_label
from dedupe import find_story_brand


# ---- item 4: a rumour site's release headline is an official candidate ----

def test_rumor_site_release_headline_is_an_official_candidate(rules):
    item = make_item("Fujifilm X-T6 firmware update released", source="Fuji Rumors", source_type="rumor")
    assert classify.is_candidate(item, rules)
    assert item_label({"title": item.title, "source_type": "rumor",
                       "summary": "Reports say the update may follow."}, rules) == OFFICIAL


def test_rumor_site_headline_with_a_rumour_word_stays_rumor(rules):
    headline = "Fujifilm X-T6 firmware update could be released"
    assert item_label({"title": headline, "source_type": "rumor", "summary": ""}, rules) == RUMOR


@pytest.mark.parametrize("headline", [
    "Fujifilm X-T6 firmware update leaked and released",
    "Fujifilm X-T6 firmware update expected to be released",
])
def test_other_rumour_words_keep_a_rumor_site_headline_a_rumor(headline, rules):
    assert item_label({"title": headline, "source_type": "rumor", "summary": ""}, rules) == RUMOR


@pytest.mark.parametrize("headline", [
    "How to Update Fujifilm X-T5 firmware released",
    "Is It Worth It? Fujifilm X-T5 firmware update released",
    "Canon R6 III vs R6 II firmware update released",
    "Canon R6 III review: firmware update released",
])
def test_how_to_opinion_and_comparison_headlines_are_not_alert_worthy(headline, rules):
    assert not classify.is_candidate(make_item(headline, source="Fuji Rumors", source_type="rumor"), rules)
    assert not classify.is_candidate(make_item(headline), rules)


# ---- item 11: more camera, lens, lighting and storage makers ----

@pytest.mark.parametrize("title, brand", [
    ("Zeiss Otus 55mm f/1.4 now available", "Zeiss"),
    ("Voigtländer Nokton 35mm launches", "Voigtlander"),
    ("Venus Optics Laowa 15mm f/2 announced", "Laowa"),
    ("TTArtisan 35mm f/1.4 launches", "TTArtisan"),
    ("7Artisans 25mm f/1.8 launches", "7Artisans"),
    ("Meike 85mm lens announced", "Meike"),
    ("Sirui announces new tripod", "Sirui"),
    ("Phase One XF 100MP camera announced", "Phase One"),
    ("Ilford announces new film", "Ilford"),
    ("Blackmagic Design updates camera", "Blackmagic Design"),
    ("RED Komodo 6K firmware update released", "RED"),
    ("Insta360 launches new camera", "Insta360"),
    ("GoPro announces new Hero", "GoPro"),
    ("Godox AD600 launches", "Godox"),
    ("Profoto announces new light", "Profoto"),
    ("Nanlite launches new panel", "Nanlite"),
    ("Aputure launches new light", "Aputure"),
    ("SanDisk launches new card", "SanDisk"),
    ("Lexar announces new card", "Lexar"),
    ("ProGrade announces new card", "ProGrade"),
])
def test_new_makers_are_brands(title, brand, rules):
    assert find_story_brand(title, "", rules["brands"]) == brand


@pytest.mark.parametrize("title", [
    "The red carpet at the awards announced",
    "Red light therapy device released",
])
def test_red_is_only_the_brand_with_a_red_product_name(title, rules):
    assert find_story_brand(title, "", rules["brands"]) is None


def test_red_digital_cinema_names_are_the_brand(rules):
    assert find_story_brand("RED Digital Cinema announces new firmware", "", rules["brands"]) == "RED"
    assert find_story_brand("RED V-Raptor gets firmware update", "", rules["brands"]) == "RED"


def test_affinity_is_only_affinity_photo_or_by_canva(open_rules):
    rules = open_rules  # not big brands, so the round 10 gate is off here
    assert classify.software_hit("Affinity Photo 2.5 released", rules) == "affinity photo"
    assert classify.software_hit("Affinity by Canva gets AI tools released", rules) == "affinity by canva"
    assert classify.software_hit("Affinity Designer 2 released", rules) is None
    assert classify.is_candidate(make_item("Affinity Photo 2.5 released"), rules)
    assert not classify.is_candidate(make_item("Affinity Designer 2 released"), rules)


def test_kodak_needs_a_camera_film_or_photo_word(rules):
    assert find_story_brand("Kodak announces new camera", "", rules["brands"]) == "Kodak"
    assert find_story_brand("Kodak Ektar film returns", "", rules["brands"]) == "Kodak"
    assert find_story_brand("Kodak shares jump after earnings", "", rules["brands"]) is None
    assert not classify.is_candidate(make_item("Kodak shares jump after earnings announced"), rules)


def test_gimp_needs_a_context_word(open_rules):
    rules = open_rules  # not big brands, so the round 10 gate is off here
    assert classify.is_candidate(make_item("GIMP 3.0 update released"), rules)
    assert not classify.is_candidate(make_item("A gimp costume released in Japan"), rules)


def test_luminar_needs_a_context_word(rules):
    assert classify.is_candidate(make_item("Luminar Neo 1.20 released"), rules)
    assert not classify.is_candidate(make_item("Luminar lidar sensor announced for cars"), rules)


def test_sigma_guard_is_in_the_loaded_rules(rules):
    assert rules["name_guards"]["sigma"]
    assert "kodak" in rules["name_guards"]


@pytest.mark.parametrize("title, category", [
    ("Capture One 16 released", "capture-one"),
    ("DxO PhotoLab 8 now available", "dxo"),
    ("Nik Collection 7 released by DxO", "dxo"),
    ("Topaz Photo AI 4 released", "topaz"),
    ("Affinity Photo 2.5 released", "affinity"),
    ("Photomator 4 update released", "other-software"),
    ("Pixelmator Pro 4 released", "other-software"),
    ("darktable 5.0 released", "other-software"),
    ("ON1 Photo RAW 2026 released", "other-software"),
    ("Godox AD600 launches", "lighting"),
    ("SanDisk Extreme Pro CFexpress card launches", "storage"),
])
def test_editing_software_and_gear_get_their_own_category(title, category, open_rules):
    rules = open_rules  # not big brands, so the round 10 gate is off here
    assert classify.is_candidate(make_item(title), rules)
    assert classify.rule_category(title, rules) == category


def test_every_rule_category_is_a_category_the_pipeline_knows(rules):
    ids = {category["id"] for category in rules["categories"]}
    assert ids <= classify.CATEGORIES


def test_adobe_bridge_and_firefly_photo_editing_are_in_scope(rules):
    assert classify.is_candidate(make_item("Adobe Bridge 15 released"), rules)
    assert classify.is_candidate(make_item("Adobe Firefly photo editing tools released"), rules)


def test_unrelated_adobe_news_is_still_skipped(rules):
    assert not classify.is_candidate(make_item("Adobe Premiere Pro 25 released"), rules)
    assert not classify.is_candidate(make_item("Adobe Acrobat update released"), rules)
    assert not classify.is_candidate(make_item("Adobe earnings announced for the quarter"), rules)
