"""Functional round, item 2: the carousel backlog, caps that count only successful builds, one retry, live-run wiring."""
import logging
from datetime import datetime, timedelta, timezone

import pytest
from conftest import ROOT

import carousel_auto
import run
import runlog
from classify import OFFICIAL, RUMOR
from dedupe import Store, Story

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
SECRET_URL = "https://hooks.slack.com/services/T0BACKLOG/B0BACKLOG/backlogtoken123"


def stored_db(tmp_path):
    db = tmp_path / "seen.sqlite"
    runlog.connect(db).close()
    return db


def add_story(db, title, label=OFFICIAL, first_seen=NOW, dismissed=False):
    store = Store(db)
    story = Story(title=title, brand="Canon", kind="product", tokens=frozenset())
    store.save_story(story, first_seen)
    if label:
        store.mark_alerted(story, label)
    if dismissed:
        store.mark_dismissed(story)
    store.db.close()
    return story.id


def ok_result(folder):
    return {"folder": folder, "slides": 4, "confirmed": 9, "removed": [], "missing": [], "placed": [],
            "design": []}


def no_message(text, url):
    return None


# ---- a capped story waits, then gets built the next day ----

def test_a_capped_story_is_built_the_next_day(tmp_path):
    db = stored_db(tmp_path)
    first = add_story(db, "Canon Announces R6 Mark III")
    second = add_story(db, "Nikon Announces Z9 II")
    built = []

    def build(story_id):
        built.append(story_id)
        return ok_result(tmp_path)

    carousel_auto.after_alerts(db, [(first, "Canon Announces R6 Mark III")], NOW, "u", build=build, notify=no_message)
    capped = carousel_auto.after_alerts(db, [(second, "Nikon Announces Z9 II")], NOW + timedelta(hours=1), "u",
                                        build=build, notify=no_message)
    assert "skipped" in capped[0] and built == [first]

    tomorrow = NOW + timedelta(days=1)
    waiting = carousel_auto.pending_stories(db, tomorrow)
    assert second in [story_id for story_id, _ in waiting]
    outcomes = carousel_auto.after_alerts(db, waiting, tomorrow, "u", build=build, notify=no_message)
    assert f"{second}: draft ready" in outcomes[0] and built == [first, second]


# ---- a failure does not use up the day ----

def test_a_failed_build_does_not_use_up_the_day(tmp_path):
    db = stored_db(tmp_path)
    first = add_story(db, "Canon Announces R6 Mark III")
    second = add_story(db, "Nikon Announces Z9 II")

    def broken(story_id):
        raise RuntimeError("No official page for this story was found.")

    failed = carousel_auto.after_alerts(db, [(first, "A")], NOW, "u", build=broken, notify=no_message)
    assert failed[0].startswith(f"{first}: failed")
    later = carousel_auto.after_alerts(db, [(second, "B")], NOW + timedelta(hours=1), "u",
                                       build=lambda sid: ok_result(tmp_path), notify=no_message)
    assert later[0].startswith(f"{second}: draft ready")


def test_a_story_gets_only_one_failed_attempt(tmp_path):
    db = stored_db(tmp_path)
    story = add_story(db, "Canon Announces R6 Mark III")

    def broken(story_id):
        raise RuntimeError("No official page")

    carousel_auto.after_alerts(db, [(story, "A")], NOW, "u", build=broken, notify=no_message)
    again = carousel_auto.after_alerts(db, [(story, "A")], NOW + timedelta(days=1), "u",
                                       build=lambda sid: ok_result(tmp_path), notify=no_message)
    assert again == [f"{story}: skipped (failed before, not retried)"]
    assert carousel_auto.failed_attempts(db, story) == 1


def test_only_successful_builds_count_toward_the_daily_cap(tmp_path):
    db = stored_db(tmp_path)
    carousel_auto.record(db, 1, NOW, "failed", None, "boom")
    assert carousel_auto.may_build(db, NOW + timedelta(hours=1)) == (True, "within caps")
    carousel_auto.record(db, 2, NOW, "ok", "f", "draft ready")
    assert carousel_auto.may_build(db, NOW + timedelta(hours=1))[0] is False


# ---- what is waiting, best first ----

def test_pending_is_official_recent_unbuilt_and_best_first(tmp_path):
    db = stored_db(tmp_path)
    lightroom = add_story(db, "Adobe Updates Lightroom Masking Tools")
    camera = add_story(db, "Canon Announces R6 Mark III")
    lens = add_story(db, "Canon Announces 50mm lens")
    add_story(db, "Canon R7 rumored specs", label=RUMOR)
    add_story(db, "Canon Announces R5 Mark II", first_seen=NOW - timedelta(hours=73))
    add_story(db, "Canon Announces R1 Mark II", dismissed=True)
    done = add_story(db, "Canon Announces R3 Mark II")
    carousel_auto.record(db, done, NOW, "ok", "f", "draft ready")
    assert [story_id for story_id, _ in carousel_auto.pending_stories(db, NOW)] == [camera, lens, lightroom]


def test_pending_is_empty_before_any_stories_exist(tmp_path):
    assert carousel_auto.pending_stories(tmp_path / "new.sqlite", NOW) == []


def test_a_sent_ready_message_is_logged(tmp_path, caplog):
    db = stored_db(tmp_path)
    story = add_story(db, "Canon Announces R6 Mark III")
    caplog.set_level(logging.INFO, logger="watcher")
    carousel_auto.after_alerts(db, [(story, "A")], NOW, "u", build=lambda sid: ok_result(tmp_path),
                               notify=no_message)
    assert "Carousel ready for approval sent" in caplog.text
    assert SECRET_URL not in caplog.text


# ---- the live run asks for the waiting stories every time ----

def project(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    for name in ("sources.yaml", "rules.yaml"):
        (tmp_path / "config" / name).write_text((ROOT / "config" / name).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(run.fetch, "fetch_all", lambda config: ([], {}))


def test_a_live_run_with_nothing_new_still_offers_the_waiting_stories(monkeypatch, tmp_path):
    project(monkeypatch, tmp_path)
    db = tmp_path / "data" / "seen.sqlite"
    # run.main reads the real clock, so the story must be recent by the real clock too.
    waiting = add_story(db, "Canon Announces R6 Mark III", first_seen=datetime.now(timezone.utc))
    calls = []
    monkeypatch.setattr(run, "after_official_alerts", lambda db_path, stories, now, url: calls.append(stories) or [])
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SECRET_URL)
    assert run.main(["--no-claude"]) == 0
    assert calls == [[(waiting, "Canon Announces R6 Mark III")]]
