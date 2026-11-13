from datetime import timedelta

import pytest
from conftest import make_item

from dedupe import Store, canonical_url, group_into_stories, model_tokens


def group(items, store, rules, now):
    return group_into_stories(
        items, store, rules["same_story_window_days"], rules["title_similarity"], rules["brands"], now
    )


def test_tracking_codes_removed():
    a = canonical_url("https://www.Site.com/a/?utm_source=x&fbclid=1")
    assert a == canonical_url("https://site.com/a")


def test_real_query_kept():
    assert canonical_url("https://site.com/?p=123") != canonical_url("https://site.com/?p=456")


@pytest.mark.parametrize(
    "a,b",
    [
        ("Canon EOS R6 Mark III", "Canon R6III"),
        ("Nikon Z6 III", "Nikon Z6III"),
        ("Fujifilm X-T6", "Fujifilm XT6"),
        ("Sony A7R V", "Sony a7rV"),
        ("Fujifilm X100VI", "Fujifilm X100 VI"),
    ],
)
def test_model_names_match(a, b):
    assert model_tokens(a) == model_tokens(b)


def test_specs_and_years_are_not_model_names():
    assert model_tokens("Best of 2026: 40MP, 8K, 120fps and 24.2MP") == frozenset()


def test_same_story_from_two_sites_groups_once(rules, now):
    store = Store()
    stories = group(
        [make_item("Canon Announces EOS R6 Mark III"),
         make_item("Canon's R6 III Is Here And Announced", source="DPReview")],
        store, rules, now,
    )
    assert len(stories) == 1
    assert {s["source"] for s in stories[0].sources} == {"PetaPixel", "DPReview"}


def test_different_generations_stay_separate(rules, now):
    stories = group(
        [make_item("Canon Announces R6 Mark II"), make_item("Canon Announces R6 Mark III")],
        Store(), rules, now,
    )
    assert len(stories) == 2


def test_different_brands_stay_separate(rules, now):
    stories = group(
        [make_item("Canon Announces 50mm f1.2 lens"), make_item("Sigma Announces 50mm f1.2 lens")],
        Store(), rules, now,
    )
    assert len(stories) == 2


def test_firmware_is_a_separate_story_from_the_launch(rules, now):
    stories = group(
        [make_item("Nikon Announces Z9 II"), make_item("Nikon Z9 II firmware released")],
        Store(), rules, now,
    )
    assert len(stories) == 2


def test_same_url_second_run_is_ignored(rules, now):
    store = Store()
    item = make_item("Canon Announces R6 Mark III")
    assert len(group([item], store, rules, now)) == 1
    assert group([item], store, rules, now + timedelta(hours=1)) == []


def test_later_article_joins_remembered_story(rules, now):
    store = Store()
    group([make_item("Canon Announces R6 Mark III")], store, rules, now)
    later = group(
        [make_item("Canon Launches R6 III", source="Digital Camera World")],
        store, rules, now + timedelta(days=2),
    )
    assert len(later) == 1 and len(later[0].sources) == 2
    assert later[0].id is not None


def test_software_without_model_uses_title_similarity(rules, now):
    stories = group(
        [make_item("Adobe Releases Photoshop Generative Fill Upgrade"),
         make_item("Adobe Releases Photoshop Generative Fill Upgrade Today", source="DPReview"),
         make_item("Adobe Updates Lightroom Masking Tools", source="Fstoppers")],
        Store(), rules, now,
    )
    assert len(stories) == 2


XT6_DELAY = "Fujifilm X-T6 delayed again as 19 November launch date is scrapped"
XT6_SENSOR_RUMOR = "RUMOR: Fujifilm X-T6 Powered by a New 40MP Sensor!"


def test_delay_and_sensor_rumor_about_one_camera_are_not_two_sources(rules, now):
    stories = group(
        [make_item(XT6_DELAY, source="Camera Jabber"),
         make_item(XT6_SENSOR_RUMOR, source="Fuji Rumors", source_type="rumor")],
        Store(), rules, now,
    )
    assert len(stories) == 2
    assert all(len(s.sources) == 1 for s in stories)


def test_two_reports_of_the_same_delay_group_together(rules, now):
    stories = group(
        [make_item(XT6_DELAY, source="Camera Jabber"),
         make_item("Fujifilm X-T6 launch postponed again", source="DPReview")],
        Store(), rules, now,
    )
    assert len(stories) == 1 and len(stories[0].sources) == 2


def test_dry_run_copy_does_not_change_the_real_memory(tmp_path, rules, now):
    path = tmp_path / "seen.sqlite"
    real = Store(path)
    group([make_item("Canon Announces R6 Mark III")], real, rules, now)
    real.db.close()

    copy = Store(path, read_only_copy=True)
    group([make_item("Nikon Announces Z9 II")], copy, rules, now)
    assert len(copy.recent_stories(30, now)) == 2

    again = Store(path)
    assert len(again.recent_stories(30, now)) == 1
