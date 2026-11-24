"""Carousel bot round (Nov 21): the TPM Carousel Bot makes every carousel; Kint and David only approve. Temporary
folders only: no git, no Claude, no Slack, no network."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import ROOT
from test_phase3 import ok_result, stored_db
from test_round7_downloads import PASSING, carousel

import activity
import carousel_auto
import carousel_bot
import carousel_plan
import carousel_status
import classify
import cloud_state
import review
import runlog

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)
FAKE_WEBHOOK = "https://hooks.slack.com/services/T0BOT/B0BOT/bottoken1"  # made up, never called


class FakeGit:
    def __init__(self, fail=(), staged=True):
        self.calls, self.fail, self.staged = [], set(fail), staged

    def __call__(self, args, root):
        self.calls.append(" ".join(args))
        name = args[0]
        if name in self.fail:
            return False, f"{name} failed"
        if args[:3] == ["diff", "--cached", "--quiet"]:
            return (not self.staged), ""
        return True, ""


class FakeSync:
    def __init__(self):
        self.calls = []

    def pull(self, side, root):
        self.calls.append(("pull", side))

    def push(self, side, root):
        self.calls.append(("push", side))


def project(tmp_path, cloud_on=True):
    root = tmp_path / "project"
    (root / "state").mkdir(parents=True)
    if cloud_on:
        (root / "state" / cloud_state.CLOUD_FLAG).write_text("on", encoding="utf-8")
    return root


# ---- the lock ----

def test_two_runs_never_overlap_and_a_stale_lock_is_taken_over(tmp_path):
    lock = tmp_path / "logs" / "bot.lock"
    assert carousel_bot.acquire_lock(lock, now=1000.0)
    assert not carousel_bot.acquire_lock(lock, now=1000.0)  # the first run is still going
    old = lock.stat().st_mtime
    assert carousel_bot.acquire_lock(lock, now=old + carousel_bot.LOCK_STALE_HOURS * 3600 + 5)
    carousel_bot.release_lock(lock)
    assert not lock.exists()


# ---- one run ----

def test_a_run_pulls_builds_pushes_state_and_commits_only_state(tmp_path, monkeypatch):
    root = project(tmp_path)
    git, sync, order = FakeGit(), FakeSync(), []
    monkeypatch.setattr(carousel_bot, "webhook_or_none", lambda: None)
    summary = carousel_bot.run_once(
        root, NOW, git=git, sync=sync, safety=lambda r: order.append("safety") or [],
        rebuild=lambda *a, **k: order.append("rebuild") or [],
        build=lambda *a, **k: order.append("build") or ["7: skipped (daily cap reached (1 a day))"])
    assert git.calls[0] == "pull --rebase --autostash"
    assert sync.calls == [("pull", "laptop"), ("push", "laptop")]
    assert order == ["rebuild", "build", "safety"]
    assert "add -A -- state" in git.calls and f"commit -m {carousel_bot.COMMIT_MESSAGE} -- state" in git.calls
    assert git.calls[-1] == "push" and summary["push"] == "committed and pushed"
    assert all("state" in c or c.startswith(("pull", "push", "diff", "rebase")) for c in git.calls)


def test_nothing_is_pushed_when_the_safety_check_finds_a_problem(tmp_path, monkeypatch):
    root = project(tmp_path)
    git = FakeGit()
    monkeypatch.setattr(carousel_bot, "webhook_or_none", lambda: None)
    summary = carousel_bot.run_once(root, NOW, git=git, sync=FakeSync(), rebuild=lambda *a, **k: [],
                                    build=lambda *a, **k: [], safety=lambda r: ["state/x.md: contains a PC path"])
    assert "not pushed" in summary["push"] and not any(c.startswith(("commit", "push")) for c in git.calls)


def test_a_failed_pull_builds_locally_but_waits_to_push(tmp_path, monkeypatch):
    root = project(tmp_path)
    git = FakeGit(fail={"pull"})
    monkeypatch.setattr(carousel_bot, "webhook_or_none", lambda: None)
    summary = carousel_bot.run_once(root, NOW, git=git, sync=FakeSync(), safety=lambda r: [],
                                    rebuild=lambda *a, **k: [], build=lambda *a, **k: [])
    assert "rebase --abort" in git.calls and "not pushed" in summary["push"]
    assert not any(c.startswith("commit") for c in git.calls)


def test_nothing_new_means_no_commit(tmp_path, monkeypatch):
    root = project(tmp_path)
    git = FakeGit(staged=False)
    monkeypatch.setattr(carousel_bot, "webhook_or_none", lambda: None)
    summary = carousel_bot.run_once(root, NOW, git=git, sync=FakeSync(), safety=lambda r: [],
                                    rebuild=lambda *a, **k: [], build=lambda *a, **k: [])
    assert summary["push"] == "nothing new to commit" and not any(c.startswith("commit") for c in git.calls)


def test_the_bot_does_nothing_while_the_cloud_is_off(tmp_path):
    root = project(tmp_path, cloud_on=False)
    git = FakeGit()
    summary = carousel_bot.run_once(root, NOW, git=git, sync=FakeSync(), safety=lambda r: pytest.fail("no"),
                                    rebuild=lambda *a, **k: pytest.fail("no"), build=lambda *a, **k: pytest.fail("no"))
    assert summary["push"] == "cloud off" and git.calls == []


def test_a_usage_limit_stops_building_but_still_pushes_what_was_finished(tmp_path, monkeypatch):
    root = project(tmp_path)
    git = FakeGit()
    monkeypatch.setattr(carousel_bot, "webhook_or_none", lambda: None)
    summary = carousel_bot.run_once(
        root, NOW, git=git, sync=FakeSync(), safety=lambda r: [],
        rebuild=lambda *a, **k: [f"x: {carousel_auto.USAGE_LIMIT_OUTCOME}"],
        build=lambda *a, **k: pytest.fail("no build after the limit"))
    assert summary["usage_limit"] is True and summary["push"] == "committed and pushed"


def test_main_never_raises_and_always_releases_the_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(carousel_bot, "LOCK_FILE", tmp_path / "bot.lock")
    monkeypatch.setattr(carousel_bot, "setup_logging", lambda path=None: None)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)  # the real .env is never read in a test
    monkeypatch.setattr(carousel_bot, "acquire_lock", lambda path=None: True)
    released = []
    monkeypatch.setattr(carousel_bot, "release_lock", lambda path=None: released.append(1))
    monkeypatch.setattr(carousel_bot, "run_once", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert carousel_bot.main() == 0 and released == [1]


# ---- Claude's usage limit ----

@pytest.mark.parametrize("code, out, err", [
    (1, "", "Claude AI usage limit reached|1763700000"),
    (1, "Claude AI usage limit reached. Your limit will reset at 5am.", ""),
    (0, "Claude AI usage limit reached|1763700000", ""),
])
def test_a_usage_limit_answer_is_recognised(code, out, err):
    with pytest.raises(classify.ClaudeUsageLimit):
        classify.check_usage_limit(code, out, err)


def test_a_normal_answer_mentioning_a_limit_is_not_a_usage_limit():
    classify.check_usage_limit(0, '[{"id": "a", "verdict": "CONFIRMED", "quote": "no rate limit on exports"}]' * 20,
                               "")
    classify.check_usage_limit(0, "The new speed limit is 30 fps.", "")
    classify.check_usage_limit(1, "", "Some other error")


def test_a_usage_limit_is_not_a_failed_build_and_stops_the_queue(tmp_path):
    db = stored_db(tmp_path)
    tried = []

    def limited(story_id):
        tried.append(story_id)
        raise classify.ClaudeUsageLimit("Claude usage limit reached")

    outcomes = carousel_auto.after_alerts(db, [(7, "A"), (8, "B")], NOW, "u", build=limited, notify=lambda *a: None)
    assert tried == [7] and carousel_auto.USAGE_LIMIT_OUTCOME in outcomes[0]
    assert carousel_auto.failed_attempts(db, 7) == 0  # tried again next hour, as if nothing happened


def test_an_image_check_at_the_usage_limit_stops_the_build(tmp_path, monkeypatch):
    import carousel
    import image_pick
    image = tmp_path / "c01.jpg"
    image.write_bytes(b"\xff\xd8\xff")

    def limited(*args, **kwargs):
        raise classify.ClaudeUsageLimit("Claude usage limit reached")

    monkeypatch.setattr(classify, "ask_claude_read", limited)
    with pytest.raises(classify.ClaudeUsageLimit):  # never an "unreadable" image, never a text-only slide by mistake
        carousel.verify_image(image, image_pick.Slot("02", 2, "x", "feature", "X"), "t", "P", "sonnet")


# ---- a failed build gets one more try, with the reason ----

def test_the_bot_retries_a_failed_story_once_with_the_reason_as_its_note(tmp_path, monkeypatch):
    db = stored_db(tmp_path)
    carousel_auto.record(db, 7, NOW - timedelta(hours=2), "failed", None, "Design check: headline lines")
    notes = []
    import carousel
    monkeypatch.setattr(carousel, "run_story",
                        lambda key, url, render, review_note=None: notes.append(review_note) or ok_result(tmp_path))
    outcomes = carousel_auto.after_alerts(db, [(7, "A")], NOW, "u", carousel_bot.default_build(db),
                                          notify=lambda *a: None, max_failed=carousel_bot.BOT_MAX_ATTEMPTS)
    assert outcomes[0].startswith("7: draft ready")
    assert "Design check: headline lines" in notes[0] and "fresh draft" in notes[0]
    carousel_auto.record(db, 8, NOW - timedelta(hours=3), "failed", None, "x")
    carousel_auto.record(db, 8, NOW - timedelta(hours=2), "failed", None, "x")
    again = carousel_auto.after_alerts(db, [(8, "B")], NOW + timedelta(days=1), "u", carousel_bot.default_build(db),
                                       notify=lambda *a: None, max_failed=carousel_bot.BOT_MAX_ATTEMPTS)
    assert "not retried" in again[0]  # only one extra try, never a loop


def test_a_review_note_goes_into_a_fresh_draft_only():
    prompt = carousel_plan.draft_prompt("T", "https://x", "Official text.", ["Photoshop"],
                                        note="Make the cover about Relight")
    assert "REVIEW NOTE" in prompt and "Make the cover about Relight" in prompt and "never add a fact" in prompt
    assert "REVIEW NOTE" not in carousel_plan.draft_prompt("T", "https://x", "Official text.", ["Photoshop"])


def test_a_note_always_makes_a_fresh_draft_instead_of_reusing_the_plan(tmp_path):
    import carousel
    (tmp_path / "plan.json").write_text(json.dumps({"slides": [{"x": 1}]}), encoding="utf-8")
    data, note = carousel.plan_for_story(tmp_path / "plan.json", lambda: {"fresh": True}, redraft=True)
    assert data == {"fresh": True} and "fresh draft" in note


# ---- a rejection with a note is rebuilt ----

def rejected_carousel(tmp_path, db, by_person=True):
    base = tmp_path / "carousels"
    folder = carousel(base)
    carousel_auto.record(db, 7, NOW - timedelta(days=1), "ok", str(Path("D:/Work/output/carousels") / folder.name),
                         "draft ready")
    if by_person:
        review.reject(folder, "Use the Relight demo on the cover", NOW, by="Kint")
    else:
        carousel_status.set_status(folder, "rejected", reason="Rebuild check: wrong official page")
    return base, folder


def test_a_carousel_kint_rejected_with_a_note_is_rebuilt_once_and_waits_for_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "refresh_dashboard", lambda folder=None: None)
    db = stored_db(tmp_path)
    base, folder = rejected_carousel(tmp_path, db)
    assert carousel_status.read_status(folder)["rebuild_requested"] is True
    calls, sent = [], []

    def build(key, url, render, review_note=None):
        calls.append((key, url, review_note))
        carousel_status.write_build(folder, dict(PASSING, title="Photoshop 2027"))
        return ok_result(folder)

    outcomes = carousel_bot.rebuild_rejected(db, base, NOW, FAKE_WEBHOOK, build=build,
                                             notify=lambda text, url: sent.append(text))
    assert calls == [("7", "https://blog.adobe.com/max-2026", "Use the Relight demo on the cover")]
    status = carousel_status.read_status(folder)
    assert status["status"] == "waiting_for_david" and outcomes == [f"{folder.name}: rebuilt, waiting_for_david"]
    assert sent[0].startswith("Carousel ready for approval: Photoshop 2027 (rebuilt after your note)")
    assert carousel_bot.rebuild_rejected(db, base, NOW, FAKE_WEBHOOK, build=lambda *a, **k: pytest.fail("again"),
                                         notify=lambda *a: None) == []
    assert any(e["outcome"] == "rebuilt" for e in activity.read_events())


def test_a_system_rejection_is_not_rebuilt(tmp_path):
    db = stored_db(tmp_path)
    base, _ = rejected_carousel(tmp_path, db, by_person=False)
    assert carousel_bot.rejected_to_rebuild(base) == []


def test_a_rebuild_that_fails_keeps_the_rejection_and_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "refresh_dashboard", lambda folder=None: None)
    db = stored_db(tmp_path)
    base, folder = rejected_carousel(tmp_path, db)

    def broken(*args, **kwargs):
        raise RuntimeError("Design check: headline lines")

    outcomes = carousel_bot.rebuild_rejected(db, base, NOW, FAKE_WEBHOOK, build=broken, notify=lambda *a: None)
    status = carousel_status.read_status(folder)
    assert "rebuild failed" in outcomes[0] and status["status"] == "rejected"
    assert "Design check" in status["bot_rebuild_problem"] and carousel_bot.rejected_to_rebuild(base) == []


def test_a_rebuild_at_the_usage_limit_is_tried_again_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "refresh_dashboard", lambda folder=None: None)
    db = stored_db(tmp_path)
    base, folder = rejected_carousel(tmp_path, db)

    def limited(*args, **kwargs):
        raise classify.ClaudeUsageLimit("limit")

    outcomes = carousel_bot.rebuild_rejected(db, base, NOW, FAKE_WEBHOOK, build=limited, notify=lambda *a: None)
    assert carousel_auto.USAGE_LIMIT_OUTCOME in outcomes[0] and len(carousel_bot.rejected_to_rebuild(base)) == 1


def test_the_story_of_a_folder_is_found_from_the_build_records(tmp_path):
    db = tmp_path / "seen.sqlite"
    conn = runlog.connect(db)
    with conn:
        conn.execute("INSERT INTO carousel_builds(story_id,built_at,status,folder,message) VALUES(?,?,?,?,?)",
                     (12, NOW.isoformat(), "ok", "D:\\Work\\output\\carousels\\2026-11-11-photoshop-2027", "ok"))
    conn.close()
    assert carousel_bot.story_id_for_folder(db, "2026-11-11-photoshop-2027") == 12
    assert carousel_bot.story_id_for_folder(db, "unknown-folder") is None


def test_the_hourly_pull_never_undoes_an_approval_kint_just_made(tmp_path):
    root = tmp_path / "laptop"
    folder = carousel(root / "output" / "carousels")
    cloud_state.push("laptop", root)  # state/ now has the carousel, waiting for David
    carousel_status.set_status(folder, "approved", approved_by="Kint", approved_at=NOW.isoformat())
    cloud_state.pull("laptop", root)  # the bot's next run
    assert carousel_status.read_status(folder)["status"] == "approved"
    (folder / "captions.txt").unlink()
    cloud_state.pull("laptop", root)  # a file the laptop does not have is still brought back
    assert (folder / "captions.txt").exists()


# ---- what Kint sees ----

def test_the_ready_message_is_about_approval_with_the_dashboard_link(tmp_path):
    text = carousel_auto.ready_message("Photoshop 2027", ok_result(tmp_path))
    assert text.startswith("Carousel ready for approval: Photoshop 2027")
    assert "https://kintlibot-netizen.github.io/tpm-photo-news/" in text and "Nothing is posted automatically" in text
    assert str(tmp_path) not in text and "—" not in text


def test_how_it_works_says_the_bot_makes_the_carousels():
    import dashboard
    steps = " ".join(dashboard.HOW_IT_WORKS)
    assert "made by hand from the brand's own page" in steps and "carousel bot" not in steps.lower()
    assert "Kint posts by hand in Meta Business Suite" in steps and "sent to david only when kint says so" in steps.lower()
    assert any(title == "Carousel" for _, title, _, _ in dashboard.FLOW_NODES)


# ---- the scheduled task and its launcher ----

def test_the_task_script_registers_a_hidden_hourly_and_logon_task_with_no_pc_paths():
    text = (ROOT / "scripts" / "setup-carousel-bot-task.ps1").read_text(encoding="utf-8")
    for needed in ('-TaskName "TPM Carousel Bot"', "wscript.exe", "carousel_bot_hidden.vbs", "-Hidden",
                   "-RepetitionInterval (New-TimeSpan -Hours 1)", "-AtLogOn", "-StartWhenAvailable",
                   "-MultipleInstances IgnoreNew", "-ExecutionTimeLimit", "$PSScriptRoot"):
        assert needed in text, needed
    assert "C:\\Users" not in text and "Read-Host" not in text and "pause" not in text.lower()
    vbs = (ROOT / "scripts" / "carousel_bot_hidden.vbs").read_text(encoding="utf-8")
    assert "shell.Run" in vbs and ", 0, True" in vbs and "C:\\Users" not in vbs  # 0 = no window
    wrapper = (ROOT / "scripts" / "carousel_bot.py").read_text(encoding="utf-8")
    assert "carousel_bot.main()" in wrapper and "input(" not in wrapper


def test_the_bot_never_posts_to_social_media_and_logs_stay_private():
    source = (ROOT / "src" / "carousel_bot.py").read_text(encoding="utf-8").lower()
    for banned in ("graph.facebook", "instagram.com", "media_publish", "business.facebook"):
        assert banned not in source
    assert "logs/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "—" not in source and "–" not in source
