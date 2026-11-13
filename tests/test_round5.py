"""Round 5: brand from the product, stored stories judged again under current rules, plain status words."""
import sqlite3
from datetime import timedelta

import pytest
import requests
from conftest import NOW, ROOT, make_item

import classify
import dashboard
import run
import runlog
from classify import OFFICIAL, RUMOR
from dedupe import Store, Story, find_story_brand

# Exact headline from the Round 5 review.
JAPAN = (
    "Just released and already the #1 camera in Japan: This full-frame mirrorless "
    "has even beaten Sony's record-breaking 33MP camera"
)
JAPAN_SUMMARY = (
    "Canon's newest full-frame camera only started shipping in October. Just a few weeks later, "
    "it's already sitting at the top of this camera chart in Japan"
)
SONY_KIT = (
    "Can compact, lightweight camera gear be any good at wildlife photography? "
    "I took a 2.5lb / 1kg Sony kit..."
)
XT_FIRMWARE = "Firmware Updates for Fujifilm X-T5, X-H2 and X-H2S"
SOFT = "The update could fix autofocus issues and might add new video modes. It possibly lands soon."


def save(store, title, brand, source_type="rumor", source="Fuji Rumors", summary="Text.", now=NOW):
    """Stores a story the way the watcher does, with one source."""
    story = Story(title=title, brand=brand, kind="product", tokens=frozenset())
    slug = "".join(c for c in title.lower() if c.isalnum())[:60]
    story.sources = [{
        "url": f"https://{source.replace(' ', '').lower()}.example/{slug}",
        "link": f"https://{source.replace(' ', '').lower()}.example/{slug}",
        "source": source, "source_type": source_type, "title": title,
        "summary": summary, "published": None,
    }]
    store.save_story(story, now)
    return story


def stored(store, now=NOW):
    return store.recent_stories(180, now)


# ---- brand comes from the product ----

def test_comparison_brand_is_not_the_product_brand(rules):
    assert find_story_brand(JAPAN, JAPAN_SUMMARY, rules["brands"]) == "Canon"
    assert find_story_brand(JAPAN, "", rules["brands"]) is None


def test_brand_named_first_as_the_product_still_wins(rules):
    assert find_story_brand("Sony beats Canon in autofocus", "", rules["brands"]) == "Sony"


def test_japan_headline_is_stored_as_canon(rules, now):
    store = Store()
    run.process([make_item(JAPAN, source="Digital Camera World", summary=JAPAN_SUMMARY)], store, rules, False, now)
    assert stored(store, now)[0].brand == "Canon"


def test_stored_sony_brand_is_corrected_without_a_send(rules, now, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("refresh tried to post")

    monkeypatch.setattr(requests, "post", forbidden)
    store = Store()
    story = save(store, JAPAN, "Sony", source_type="news", source="Digital Camera World", summary=JAPAN_SUMMARY, now=now)
    store.mark_alerted(story, OFFICIAL)  # already sent, so only the brand may change
    result = run.process([], store, rules, False, now)
    assert result["ready"] == []
    assert stored(store, now)[0].brand == "Canon"


def test_dashboard_shows_the_corrected_brand_for_a_stored_story(tmp_path, rules, now):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    save(store, JAPAN, "Sony", source_type="news", source="Digital Camera World", summary=JAPAN_SUMMARY, now=now)
    store.db.close()
    out = dashboard.write_dashboard(
        db_path=db, out_path=tmp_path / "index.html", sources_path=ROOT / "config" / "sources.yaml",
        rules_path=ROOT / "config" / "rules.yaml", now=now,
    )
    page = out.read_text(encoding="utf-8")
    assert 'data-brand="Canon"' in page and 'data-brand="Sony"' not in page


# ---- stored stories are judged again under the current rules ----

def test_stored_hands_on_piece_becomes_skipped_with_reason(rules, now):
    store = Store()
    save(store, SONY_KIT, "Sony", source="Sony Alpha Rumors", now=now)
    result = run.process([], store, rules, False, now)
    assert result["ready"] == [] and result["held"] == []
    assert [j["status"] for j in result["judged"]] == [runlog.SKIPPED]
    reason = stored(store, now)[0].skipped
    assert reason and "i took" in reason.lower()


def test_stored_held_firmware_is_judged_again_and_can_alert(rules, now):
    store = Store()
    story = save(store, XT_FIRMWARE, "Fujifilm", summary=SOFT, now=now)
    store.set_claude_label(story, RUMOR)  # an old label, with no rules version
    result = run.process([], store, rules, False, now)
    assert [label for _, label, _ in result["ready"]] == [OFFICIAL]
    assert stored(store, now)[0].claude_label is None


def test_claude_label_from_the_current_rules_is_kept(rules, now):
    store = Store()
    story = save(store, XT_FIRMWARE, "Fujifilm", summary=SOFT, now=now)
    store.set_claude_label(story, RUMOR, classify.RULES_VERSION)
    result = run.process([], store, rules, False, now)
    assert result["ready"] == [] and len(result["held"]) == 1
    assert stored(store, now)[0].claude_label == RUMOR


def test_alerted_story_is_never_resent_or_skipped(rules, now, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("re-evaluation tried to post")

    monkeypatch.setattr(requests, "post", forbidden)
    store = Store()
    story = save(store, SONY_KIT, "Sony", source="Sony Alpha Rumors", now=now)
    store.mark_alerted(story, RUMOR)
    result = run.process([], store, rules, False, now)
    assert result["ready"] == [] and result["judged"] == []
    saved = stored(store, now)[0]
    assert saved.skipped is None and saved.last_alert_label == RUMOR


def test_rejections_stay_rejected_and_are_not_asked_again(rules, now):
    store = Store()
    story = save(store, "Canon Announces R6 III", "Canon", source="PetaPixel", now=now)
    store.mark_dismissed(story)  # made before this round, so it has no rules version
    calls = []

    def accept(prompt, model):
        calls.append(1)
        return ('[{"id": 0, "relevant": true, "category": "camera", "summary": "Canon camera.", '
                '"label": "OFFICIAL", "reason": "Brand announced it."}]')

    result = run.process([], store, rules, True, now, asker=accept)
    assert calls == [] and result["ready"] == []
    assert stored(store, now)[0].dismissed is True


def test_dry_run_only_keeps_ids_of_real_stories():
    result = {"judged": [{
        "story": type("S", (), {"id": 9, "title": "A", "brand": None, "sources": [], "first_seen": None})(),
        "status": "ready", "label": OFFICIAL, "category": "camera", "summary": "s", "reason": "r",
    }]}
    assert run.outcome_rows(result, {}, dry=True, known_max_id=5)[0]["story_id"] is None
    assert run.outcome_rows(result, {}, dry=True, known_max_id=9)[0]["story_id"] == 9
    assert run.outcome_rows(result, {}, dry=True, known_max_id=9)[0]["status"] == runlog.DRY_ONLY


# ---- plain English status words ----

def test_status_words_are_plain_english():
    assert runlog.ALERTED == "Sent to Slack"
    assert runlog.HELD == "Waiting for a 2nd source"
    assert runlog.REJECTED == "Rejected: not relevant"
    assert runlog.SKIPPED == "Skipped"
    assert runlog.DRY_ONLY == "Practice run only"


@pytest.mark.parametrize("old, new", [
    ("Alerted to Slack", runlog.ALERTED),
    ("Held - waiting for 2nd source", runlog.HELD),
    ("Rejected", runlog.REJECTED),
    ("Dry run only", runlog.DRY_ONLY),
    ("Slack send failed, will retry", runlog.FAILED),
])
def test_old_status_words_are_read_as_the_new_ones(old, new):
    assert runlog.normalize_status(old) == new


# ---- layout, counts and reasons on the page ----

def build(tmp_path, db, now=NOW):
    out = dashboard.write_dashboard(
        db_path=db, out_path=tmp_path / "index.html", sources_path=ROOT / "config" / "sources.yaml",
        rules_path=ROOT / "config" / "rules.yaml", now=now,
    )
    return out.read_text(encoding="utf-8")


def test_cards_and_list_come_from_the_same_stories(tmp_path, now):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    waiting = save(store, "Canon R6 Mark IV rumored specs", "Canon", source="Canon Rumors", now=now)
    skipped = save(store, SONY_KIT, "Sony", source="Sony Alpha Rumors", now=now)
    store.mark_skipped(skipped, 'Skipped by the free rules: contains "i took".')
    store.db.close()
    page = build(tmp_path, db)
    assert '<div class="k">Waiting for a 2nd source</div><div class="v">1</div>' in page
    assert '<div class="k">Skipped</div><div class="v">1</div>' in page
    assert '<span class="tag st-held">Waiting for a 2nd source</span>' in page
    assert '<span class="tag st-rej">Skipped</span>' in page
    assert "Skipped by the free rules: contains &quot;i took&quot;." in page
    assert waiting.id and skipped.id


def test_stories_are_cards_not_a_cramped_table(tmp_path, now):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    save(store, JAPAN, "Sony", source_type="news", source="Digital Camera World", summary=JAPAN_SUMMARY, now=now)
    store.db.close()
    page = build(tmp_path, db)
    assert 'id="story-list"' in page and 'class="story"' in page
    assert "<th>Claude's label reason</th>" not in page and "<th>Headline</th>" not in page
    assert "max-width:1100px" in page and "overflow-wrap:anywhere" in page


def test_page_shows_current_rules_before_the_next_run(tmp_path, now):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    save(store, SONY_KIT, "Sony", source="Sony Alpha Rumors", now=now)
    firmware = save(store, XT_FIRMWARE, "Fujifilm", summary=SOFT, now=now)
    store.set_claude_label(firmware, RUMOR)  # an old label, made under no rules version
    store.db.close()
    page = build(tmp_path, db)
    assert '<span class="tag st-rej">Skipped</span>' in page
    assert '<span class="tag st-held">Waiting for a 2nd source</span>' not in page
    assert '<span class="tag st-held">Waiting to send</span>' in page


def test_no_placeholder_reason_when_there_is_none(tmp_path, now):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    story = save(store, JAPAN, "Canon", source_type="news", source="Digital Camera World", summary=JAPAN_SUMMARY, now=now)
    store.mark_alerted(story, OFFICIAL)
    store.db.close()
    page = build(tmp_path, db)
    assert 'class="why"' not in page
    assert "Recorded before run history began" not in page


def test_status_words_on_the_page_are_plain(tmp_path, now):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    alerted = save(store, JAPAN, "Canon", source_type="news", source="Digital Camera World", summary=JAPAN_SUMMARY, now=now)
    store.mark_alerted(alerted, OFFICIAL)
    store.db.close()
    runlog.record_run(
        db, "dry", now - timedelta(hours=1), now, {"articles": 1, "in_window": 1, "passed_rules": 1,
        "alerts_ready": 0, "alerts_sent": 0, "held": 0, "rejected": 0},
        [{"feed": "PetaPixel", "ok": True, "items": 1, "error": None}],
        [{"story_id": None, "title": "Dry Only", "brand": "Canon", "category": "camera",
          "label": OFFICIAL, "status": runlog.DRY_ONLY, "reason": "r", "summary": "s",
          "first_seen": now.isoformat(), "sources": "[]"}],
    )
    page = build(tmp_path, db)
    assert "Sent to Slack" in page and "Practice run only" in page
    for old in ("Alerted to Slack", "Held - waiting", "Dry run only"):
        assert old not in page


def test_old_database_without_the_new_columns_still_renders(tmp_path, now):
    db = tmp_path / "seen.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE stories (id INTEGER PRIMARY KEY, title TEXT, brand TEXT, kind TEXT,
            tokens TEXT, last_alert_label TEXT, dismissed INTEGER DEFAULT 0, first_seen TEXT);
        CREATE TABLE sources (url TEXT PRIMARY KEY, story_id INTEGER, source TEXT, source_type TEXT,
            title TEXT, summary TEXT, published TEXT, link TEXT);
        INSERT INTO stories(id,title,brand,kind,tokens,last_alert_label,dismissed,first_seen)
            VALUES(1,'Canon Announces R6 III','Canon','product','[]',NULL,0,'2026-11-10T10:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()
    runlog.record_run(db, "live", now, now, {"articles": 0, "in_window": 0, "passed_rules": 0,
        "alerts_ready": 0, "alerts_sent": 0, "held": 0, "rejected": 0}, [], [])
    page = build(tmp_path, db)
    assert "Canon Announces R6 III" in page
