"""Round 7, section B: the activity log (data/activity-log.csv) and where each event is written from.

Every test writes to its own temporary log (conftest patches activity.LOG_PATH). No network, no Slack, no Claude."""
import csv
from datetime import datetime, timedelta, timezone

import pytest
import requests
from conftest import ROOT, make_item

import activity
import carousel_auto
import carousel_status
import health
import review
import run
import runlog

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
WEBHOOK = "https://hooks.slack.com/services/T0ACT/B0ACT/activitysecret99"


def rows(path=None):
    return activity.read_events(path)


# ---- the log itself ----

def test_an_event_is_written_with_its_manila_time_type_and_details(isolated_activity_log):
    assert activity.log_event("alert", "sent", "OFFICIAL: Canon Announces R6 Mark III", now=NOW)
    with open(isolated_activity_log, encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert list(written[0]) == activity.COLUMNS
    assert written[0]["time"] == "2026-11-11T20:00:00+08:00"  # 12:00 UTC is 20:00 in Manila
    assert written[0]["type"] == "alert" and written[0]["outcome"] == "sent"
    assert "Canon Announces R6 Mark III" in written[0]["details"]


def test_secrets_and_paths_from_this_pc_never_reach_the_log(isolated_activity_log):
    activity.log_event("carousel", "failed", f"Could not post to {WEBHOOK}; folder "
                       r"D:\Work\Documents\photo-news-automation\output\carousels\2026-11-11-photoshop "
                       "token xoxb-1234-abcd", now=NOW)
    text = isolated_activity_log.read_text(encoding="utf-8")
    assert "hooks.slack.com" not in text and "activitysecret99" not in text and "xoxb-" not in text
    assert "D:\\Work" not in text and "Documents" not in text
    assert "2026-11-11-photoshop" in text  # only the folder name is kept


def test_a_cell_that_looks_like_a_formula_is_made_harmless(isolated_activity_log):
    activity.log_event("review", "rejected", "=HYPERLINK(\"x\")", now=NOW)
    assert rows()[0]["details"].startswith("'=")


def test_events_are_read_newest_first_and_counted_for_the_week():
    activity.log_event("check", "ok", "Live check", now=NOW - timedelta(days=9))
    activity.log_event("alert", "sent", "OFFICIAL: A", now=NOW - timedelta(days=1))
    activity.log_event("carousel", "built", "Story 1", now=NOW - timedelta(hours=5))
    activity.log_event("review", "approved", "Story 1", who="Kint", now=NOW - timedelta(hours=2))
    activity.log_event("review", "posted", "Story 1", now=NOW - timedelta(hours=1))
    activity.log_event("download", "carousel zip", "x.zip", now=NOW)
    events = rows()
    assert [e["type"] for e in events][:2] == ["download", "review"]
    week = activity.week_counts(events, NOW)
    assert week == {"checks": 0, "alerts": 1, "carousels": 1, "approved": 1, "posted": 1, "downloads": 1}


def test_a_log_that_cannot_be_written_never_raises(tmp_path):
    folder_in_the_way = tmp_path / "activity-log.csv"
    folder_in_the_way.mkdir()
    assert activity.log_event("check", "ok", "x", path=folder_in_the_way) is False


def test_an_unknown_type_is_kept_as_a_check_and_a_missing_log_reads_as_empty(tmp_path):
    assert activity.read_events(tmp_path / "none.csv") == []
    activity.log_event("something", "ok", "x", now=NOW)
    assert rows()[0]["type"] == "check"


# ---- the hourly check and Slack alerts ----

def project(monkeypatch, tmp_path, items, failures):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    for name in ("sources.yaml", "rules.yaml"):
        (tmp_path / "config" / name).write_text((ROOT / "config" / name).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(run.fetch, "fetch_all", lambda config: (items, failures))


def test_a_dry_run_writes_one_check_row(monkeypatch, tmp_path):
    item = make_item("Canon Announces R6 Mark III")
    item.published = datetime.now(timezone.utc) - timedelta(hours=1)
    project(monkeypatch, tmp_path, [item], {"Broken Feed": "Read timed out."})
    assert run.main(["--dry-run", "--no-claude"]) == 0
    checks = [e for e in rows() if e["type"] == "check"]
    assert len(checks) == 1 and checks[0]["outcome"] == "some feeds failed"
    assert "Practice check" in checks[0]["details"] and "Broken Feed" in checks[0]["details"]
    assert not any(e["type"] == "alert" for e in rows())


def test_a_live_run_writes_the_alert_and_the_check(monkeypatch, tmp_path):
    item = make_item("Canon Announces R6 Mark III")
    item.published = datetime.now(timezone.utc) - timedelta(hours=1)
    project(monkeypatch, tmp_path, [item], {})
    monkeypatch.setattr(run, "after_official_alerts", lambda *a, **k: [])
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)

    class Accepted:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(requests, "post", lambda url, json, timeout: Accepted())
    monkeypatch.setattr(run.alert_step.time, "sleep", lambda seconds: None)
    assert run.main(["--no-claude"]) == 0
    alerts = [e for e in rows() if e["type"] == "alert"]
    assert alerts and alerts[0]["outcome"] == "sent" and "Canon Announces R6 Mark III" in alerts[0]["details"]
    check = next(e for e in rows() if e["type"] == "check")
    assert "Live check" in check["details"] and "1 alerts sent" in check["details"]
    assert "activitysecret99" not in activity.LOG_PATH.read_text(encoding="utf-8")


def test_a_failed_slack_send_is_logged_as_failed(monkeypatch, tmp_path):
    item = make_item("Canon Announces R6 Mark III")
    item.published = datetime.now(timezone.utc) - timedelta(hours=1)
    project(monkeypatch, tmp_path, [item], {})
    monkeypatch.setattr(run, "after_official_alerts", lambda *a, **k: [])
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)

    def refused(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(requests, "post", refused)
    monkeypatch.setattr(run.alert_step.time, "sleep", lambda seconds: None)
    assert run.main(["--no-claude"]) == 0
    assert any(e["type"] == "alert" and e["outcome"] == "failed" for e in rows())


# ---- carousel builds, waiting for David, reviews ----

def test_a_carousel_build_and_a_failed_build_are_logged(tmp_path):
    db = tmp_path / "seen.sqlite"
    runlog.connect(db).close()
    folder = tmp_path / "2026-11-11-canon"

    def build(story_id):
        if story_id == 2:
            raise RuntimeError("No official page for this story was found.")
        return {"folder": folder, "slides": 6}

    carousel_auto.after_alerts(db, [(1, "Canon R6 Mark III")], NOW, "", build, notify=lambda text, url: None)
    carousel_auto.after_alerts(db, [(2, "Canon lens")], NOW + timedelta(days=2), "", build,
                               notify=lambda text, url: None)
    events = {e["outcome"]: e for e in rows() if e["type"] == "carousel"}
    assert "2026-11-11-canon" in events["built"]["details"] and "6 slides" in events["built"]["details"]
    assert "No official page" in events["failed"]["details"]
    assert str(tmp_path) not in activity.LOG_PATH.read_text(encoding="utf-8")


PASSING = {"title": "Photoshop 2027", "slides": 2, "fact_check_passed": True, "lint_passed": True,
           "design_fail": 0, "design_summary": "Design check: passed, no findings."}


def draft(base, name="2026-11-11-photoshop-2027"):
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "01.png").write_bytes(b"png")
    (folder / "captions.txt").write_text(
        "DAVID MOLNAR FACEBOOK (first person)\nMy pick.\n\nTPM FACEBOOK AND INSTAGRAM (we)\nWe like it.\n",
        encoding="utf-8")
    return folder


def test_waiting_for_david_is_logged_once(tmp_path):
    folder = draft(tmp_path)
    carousel_status.write_build(folder, PASSING)
    carousel_status.write_build(folder, PASSING)  # a rebuild that still passes is not a new event
    waiting = [e for e in rows() if e["outcome"] == "waiting_for_david"]
    assert len(waiting) == 1 and "Photoshop 2027" in waiting[0]["details"]


def test_approve_reject_and_posted_are_logged_with_the_name_and_account(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CAROUSELS", tmp_path)
    folder = draft(tmp_path)
    carousel_status.write_build(folder, PASSING)
    review.approve(folder, "Kint", NOW)
    review.log_post(folder, "tpm-instagram", "https://www.instagram.com/p/abc/", NOW, tmp_path / "post-log.csv",
                    by="Kint")
    other = draft(tmp_path, "2026-11-11-canon")
    review.reject(other, "Too many words on slide 2", NOW, by="David")
    by_outcome = {e["outcome"]: e for e in rows() if e["type"] == "review"}
    assert by_outcome["approved"]["who"] == "Kint"
    assert "tpm-instagram" in by_outcome["posted"]["details"] and by_outcome["posted"]["who"] == "Kint"
    assert by_outcome["rejected"]["who"] == "David" and "Too many words" in by_outcome["rejected"]["details"]


# ---- health messages ----

def test_a_health_message_is_logged(tmp_path):
    db = tmp_path / "seen.sqlite"
    counts = {"articles": 0, "in_window": 0, "passed_rules": 0, "alerts_ready": 0, "alerts_sent": 0,
              "held": 0, "rejected": 0}
    failed = [{"feed": "PetaPixel", "ok": False, "items": 0, "error": "x"}]
    for hour in (2, 1):
        runlog.record_run(db, "live", NOW - timedelta(hours=hour), NOW - timedelta(hours=hour), counts, failed, [])
    sent = []
    assert health.run_if_needed(db, NOW, WEBHOOK, send=lambda text, url: sent.append(text))
    event = next(e for e in rows() if e["type"] == "health")
    assert event["outcome"] == "sent" and "every feed failed" in event["details"]
    assert "activitysecret99" not in activity.LOG_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", sorted(activity.TYPES))
def test_every_type_has_a_plain_name(kind):
    assert activity.TYPES[kind] and "_" not in activity.TYPES[kind]
