"""Round 4 tuning: confirmed releases are not held, hands-on pieces are skipped, and '?' is narrowed."""
import pytest
from conftest import make_item

import run
from classify import OFFICIAL, RUMOR, is_candidate, item_label
from dedupe import Store

# Exact headlines from the round 3 dry run.
XT_FIRMWARE = "Firmware Updates for Fujifilm X-T5, X-H2 and X-H2S"
MITAKON = "Mitakon Zhong Yi 45mm f/1.4 for Fujifilm GFX Available"
SONY_KIT = (
    "Can compact, lightweight camera gear be any good at wildlife photography? "
    "I took a 2.5lb / 1kg Sony kit..."
)
# Soft words only, no hard rumor words, so the only thing that could force RUMOR is the excerpt.
SOFT_EXCERPT = "The update could fix autofocus issues and might add new video modes. It possibly lands soon."


def test_hedge_words_are_a_separate_list_from_hard_rumor_words(rules):
    assert {"might", "could", "possibly", "may be"} <= set(rules["hedge_words"])
    for word in ("might", "could", "possibly", "may be"):
        assert word not in rules["rumor_words"]
    for word in ("rumor", "leak", "reportedly", "unconfirmed", "delayed", "scrapped", "suspect"):
        assert word in rules["rumor_words"]


@pytest.mark.parametrize("title", [XT_FIRMWARE, MITAKON])
def test_confirmed_release_with_soft_excerpt_is_official(rules, title):
    item = make_item(title, source="Fuji Rumors", source_type="rumor", summary=SOFT_EXCERPT)
    assert is_candidate(item, rules)
    assert item_label({"title": item.title, "summary": item.summary}, rules) == OFFICIAL


def test_both_confirmed_releases_alert_at_once_not_held(rules, now):
    store = Store()
    items = [
        make_item(title, source="Fuji Rumors", source_type="rumor", summary=SOFT_EXCERPT)
        for title in (XT_FIRMWARE, MITAKON)
    ]
    result = run.process(items, store, rules, False, now)
    assert sorted(label for _, label, _ in result["ready"]) == [OFFICIAL, OFFICIAL]
    assert result["held"] == []


def test_hard_rumor_word_in_excerpt_still_forces_rumor(rules):
    excerpt = "Fujifilm has reportedly delayed the update."
    assert item_label({"title": XT_FIRMWARE, "summary": excerpt}, rules) == RUMOR


def test_hard_rumor_word_in_headline_still_forces_rumor(rules):
    assert item_label({"title": "Fujifilm firmware update unconfirmed"}, rules) == RUMOR
    assert item_label({"title": "Fujifilm X-T6 update scrapped"}, rules) == RUMOR


def test_hedge_word_in_headline_still_forces_rumor(rules):
    assert item_label({"title": "Fujifilm might release new firmware"}, rules) == RUMOR


@pytest.mark.parametrize("source_type", ["news", "rumor"])
def test_hands_on_question_is_skipped_not_held(rules, now, source_type):
    assert not is_candidate(make_item(SONY_KIT, source_type=source_type), rules)
    store = Store()
    item = make_item(SONY_KIT, source="Sony Alpha Rumors", source_type=source_type)
    result = run.process([item], store, rules, False, now)
    assert result["candidates"] == 0
    assert result["ready"] == [] and result["held"] == []


def test_question_about_an_unreleased_product_is_still_rumor(rules, now):
    unreleased = "Is the Canon R7 III coming?"
    assert item_label({"title": unreleased}, rules) == RUMOR
    assert is_candidate(make_item(unreleased, source_type="rumor"), rules)
    store = Store()
    result = run.process([make_item(unreleased, source="Canon Rumors", source_type="rumor")], store, rules, False, now)
    assert result["ready"] == [] and len(result["held"]) == 1


def test_question_mark_does_not_hold_a_clear_release(rules, now):
    release = "Canon Announces R6 III: what's new?"
    assert item_label({"title": release}, rules) == OFFICIAL
    store = Store()
    result = run.process([make_item(release, source="PetaPixel")], store, rules, False, now)
    assert [label for _, label, _ in result["ready"]] == [OFFICIAL]


def test_question_in_excerpt_does_not_hold_a_clear_release(rules):
    summary = "Is it worth the price? Here is what changed."
    assert item_label({"title": "Canon Announces R6 III", "summary": summary}, rules) == OFFICIAL
