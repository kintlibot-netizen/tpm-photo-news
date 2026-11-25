"""The laptop side (the carousel bot was removed on Nov 24): git helpers, usage limits, review notes, the pull that
keeps approvals, the ready message and the rejection flow. Temporary folders only: no git, no Claude, no Slack, no network."""
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
import laptop_sync
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


# ---- one run ----


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


# ---- the scheduled task and its launcher ----




# ---- the publishing helpers (src/laptop_sync.py) ----

def test_commit_and_push_commits_only_state():
    git = FakeGit()
    assert laptop_sync.commit_and_push(git, Path(".")) == "committed and pushed"
    assert "add -A -- state" in git.calls and f"commit -m {laptop_sync.COMMIT_MESSAGE} -- state" in git.calls


def test_nothing_new_means_no_commit_and_a_failed_pull_waits():
    git = FakeGit(staged=False)
    assert laptop_sync.commit_and_push(git, Path(".")) == "nothing new to commit"
    assert not any(c.startswith("commit") for c in git.calls)
    git = FakeGit(fail={"pull"})
    assert "push waits" in laptop_sync.commit_and_push(git, Path(".")) and "push" not in git.calls
    assert "rebase --abort" in git.calls


# ---- rejecting a carousel now simply rejects it ----

def test_a_rejection_is_recorded_with_its_reason_and_never_queued_for_an_automatic_rebuild(tmp_path):
    folder = carousel(tmp_path / "carousels")
    review.reject(folder, "Cover headline too long", NOW, by="Kint")
    status = carousel_status.read_status(folder)
    assert status["status"] == "rejected" and status["reason"] == "Cover headline too long"
    assert "rebuild_requested" not in status
    with pytest.raises(review.ReviewError):
        review.reject(folder, "  ", NOW)


def test_the_carousel_bot_is_gone():
    for gone in ("src/carousel_bot.py", "scripts/carousel_bot.py", "scripts/carousel_bot_hidden.vbs",
                 "scripts/setup-carousel-bot-task.ps1"):
        assert not (ROOT / gone).exists(), gone
    import dashboard
    steps = " ".join(f"{title} {text}" for _, title, text in dashboard.HOW_IT_WORKS)  # round 12: (icon, title, text)
    assert "made by hand from the brand's own page" in steps.lower() and "carousel bot" not in steps.lower()
    assert "Kint posts by hand in Meta Business Suite" in steps and "sent to david only when kint says so" in steps.lower()
