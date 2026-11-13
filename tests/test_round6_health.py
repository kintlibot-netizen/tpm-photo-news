"""Functional round, item 8: health messages. Nothing here uses the network: Slack is a fake."""
from datetime import datetime, timedelta, timezone

import pytest
import requests

import health
import runlog

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
SECRET_URL = "https://hooks.slack.com/services/T0HEALTH/B0HEALTH/healthtoken987"
COUNTS = {"articles": 0, "in_window": 0, "passed_rules": 0, "alerts_ready": 0, "alerts_sent": 0,
          "held": 0, "rejected": 0}


def seed(db, finished, ok, failed):
    feeds = ([{"feed": f"good {i}", "ok": True, "items": 1, "error": None} for i in range(ok)]
             + [{"feed": f"bad {i}", "ok": False, "items": 0, "error": "The site took too long to answer."}
                for i in range(failed)])
    runlog.record_run(db, "live", finished - timedelta(minutes=1), finished, COUNTS, feeds, [])


def collector():
    sent = []

    def send(text, url):
        sent.append((text, url))

    return sent, send


def test_two_runs_in_a_row_with_every_feed_failed_send_one_message(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=2), 0, 3)
    seed(db, NOW - timedelta(hours=1), 0, 3)
    sent, send = collector()
    reason = health.run_if_needed(db, NOW, SECRET_URL, send=send)
    assert reason and "every feed failed" in reason
    assert len(sent) == 1 and sent[0][1] == SECRET_URL


def test_a_second_message_the_same_day_is_not_sent(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=2), 0, 3)
    seed(db, NOW - timedelta(hours=1), 0, 3)
    sent, send = collector()
    health.run_if_needed(db, NOW, SECRET_URL, send=send)
    assert health.run_if_needed(db, NOW + timedelta(hours=1), SECRET_URL, send=send) is None
    assert len(sent) == 1


def test_a_message_can_be_sent_again_after_a_day(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=2), 0, 3)
    seed(db, NOW - timedelta(hours=1), 0, 3)
    sent, send = collector()
    health.run_if_needed(db, NOW, SECRET_URL, send=send)
    health.run_if_needed(db, NOW + timedelta(hours=25), SECRET_URL, send=send)
    assert len(sent) == 2


def test_one_failed_run_alone_is_not_enough(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=2), 2, 1)
    seed(db, NOW - timedelta(minutes=30), 0, 3)
    sent, send = collector()
    assert health.run_if_needed(db, NOW, SECRET_URL, send=send) is None
    assert sent == []


def test_no_feed_working_for_more_than_six_hours_sends_a_message(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=7), 2, 0)
    sent, send = collector()
    reason = health.run_if_needed(db, NOW, SECRET_URL, send=send)
    assert reason and "no feed has worked since" in reason
    assert len(sent) == 1


def test_a_recent_good_run_is_fine(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=5), 2, 0)
    sent, send = collector()
    assert health.run_if_needed(db, NOW, SECRET_URL, send=send) is None
    assert sent == []


def test_a_watcher_with_no_history_sends_nothing(tmp_path):
    sent, send = collector()
    assert health.run_if_needed(tmp_path / "new.sqlite", NOW, SECRET_URL, send=send) is None
    assert sent == []


def test_the_webhook_never_appears_in_the_message(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=2), 0, 3)
    seed(db, NOW - timedelta(hours=1), 0, 3)
    sent, send = collector()
    health.run_if_needed(db, NOW, SECRET_URL, send=send)
    assert "healthtoken987" not in sent[0][0] and "hooks.slack.com" not in sent[0][0]


def test_a_failed_send_is_not_recorded_so_it_is_tried_again(tmp_path):
    db = tmp_path / "seen.sqlite"
    seed(db, NOW - timedelta(hours=2), 0, 3)
    seed(db, NOW - timedelta(hours=1), 0, 3)

    def down(text, url):
        raise requests.ConnectionError("network down")

    assert health.run_if_needed(db, NOW, SECRET_URL, send=down) is None
    sent, send = collector()
    assert health.run_if_needed(db, NOW + timedelta(minutes=5), SECRET_URL, send=send) is not None
    assert len(sent) == 1


@pytest.mark.parametrize("finished_text", ["not a date", None])
def test_a_bad_timestamp_never_crashes_the_check(tmp_path, finished_text):
    db = tmp_path / "seen.sqlite"
    conn = runlog.connect(db)
    with conn:
        conn.execute(
            "INSERT INTO runs(started_at,finished_at,mode,feeds_ok,feeds_failed) VALUES(?,?,?,?,?)",
            ("2026-11-11T11:00:00+00:00", finished_text or "2026-11-11T11:01:00+00:00", "live", 1, 0),
        )
    conn.close()
    sent, send = collector()
    assert health.run_if_needed(db, NOW, SECRET_URL, send=send) is None
