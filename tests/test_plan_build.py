"""Carousels without Claude (Nov 23): a written plan is checked and rendered by the existing code. Temporary folders
only: no Claude, no Slack, no git, no network."""
import json
import os
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import ROOT
from test_carousel_bot import FakeGit, FakeSync, project
from test_phase3 import stored_db

import activity
import carousel
import carousel_auto
import carousel_bot
import carousel_plan
import carousel_status
import classify
import pending_carousels
import plan_build
import run

NOW = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)
FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
FAKE_WEBHOOK = "https://hooks.slack.com/services/T0PLAN/B0PLAN/plantoken1"  # made up, never called
PAGE = "https://blog.adobe.com/max-2026"
IMG = "https://blog.adobe.com/media/relight-demo.jpg"


def jpeg(width=2000, height=1500) -> bytes:
    """A tiny file whose header says it is a JPEG of this size (enough for the size and type checks)."""
    return (b"\xff\xd8" + b"\xff\xe0\x00\x10" + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            + b"\xff\xc0\x00\x11\x08" + struct.pack(">HH", height, width) + b"\x03" + b"\x00" * 9)


PASS_CHECK = {"matches_product": True, "is_real_photo_or_official_screenshot": True, "shows_slide_subject": True,
              "has_watermark": False, "has_people_as_subject": False, "looks_ai_generated": False,
              "notes": "official Relight demo screenshot"}


def views():
    plan = carousel_plan.load_plan(FIXTURE["plan"])
    carousel_plan.verify(plan, FIXTURE["official_text"])
    return carousel_plan.build_views(plan)


def fake_story(story_id=72, brand="Adobe"):
    return SimpleNamespace(id=story_id, title="Photoshop 2027 is here", brand=brand, first_seen=NOW,
                           sources=[{"source": "PetaPixel", "url": "https://petapixel.com/ps-2027", "link": None}],
                           last_alert_label=classify.OFFICIAL, claude_label=None)


def write_plan(tmp_path, **extra) -> Path:
    data = {"story": 72, "official_url": PAGE, **FIXTURE["plan"], **extra}
    path = tmp_path / "plans" / "story-72.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def offline_story(tmp_path, monkeypatch):
    """The story, the official page and the data file are faked; Claude and Slack fail the test if touched."""
    db = stored_db(tmp_path)
    monkeypatch.setattr(carousel, "DATA_PATH", db)
    monkeypatch.setattr(carousel, "find_story", lambda store, key, now: fake_story())
    monkeypatch.setattr(carousel, "check_eligible", lambda story, rules: None)
    monkeypatch.setattr(classify, "ask_claude", lambda *a, **k: pytest.fail("Claude must never be called"))
    monkeypatch.setattr(classify, "ask_claude_read", lambda *a, **k: pytest.fail("Claude must never be called"))
    monkeypatch.setattr(carousel_auto.alert, "send_to_slack", lambda *a, **k: pytest.fail("no Slack in a test"))
    monkeypatch.setattr(carousel, "PAGE_CACHE_DIR", tmp_path / "page-cache")
    monkeypatch.setattr(carousel, "IMAGE_CACHE_DIR", tmp_path / "image-cache")
    text = FIXTURE["official_text"]
    page = carousel.OfficialPage(url=PAGE, text=text, markup=f"<p>{text}</p>", pages=[], terms=["photoshop"])
    return {"db": db, "locate": lambda story, brand, config, url: page}


def build(tmp_path, offline_story, plan_path, **kwargs):
    kwargs.setdefault("dry_run", True)
    return plan_build.build_story(
        "72", plan_path, None, render=False, now=NOW, locate=offline_story["locate"],
        place=lambda entries, checks, views, out_dir, domains: (
            {slot: {} for slot in plan_build.feature_slots(views)}, ["no images in this test"], "# Images\n"),
        preview_root=tmp_path / "previews", **kwargs)


# ---- reading the plan ----

def test_the_build_fields_are_kept_out_of_plan_json():
    plan, meta = plan_build.split_input({"story": 72, "official_url": PAGE, "images": {}, **FIXTURE["plan"]})
    assert "official_url" not in plan and "images" not in plan and plan["cover"] == FIXTURE["plan"]["cover"]
    assert meta == {"story": 72, "official_url": PAGE, "images": {}}


def test_verdicts_must_use_the_known_verdict_words():
    facts, images = plan_build.load_verdicts({"facts": {"slide1.body": {"verdict": "CONFIRMED", "quote": "q"}},
                                              "images": {"RELIGHT IMAGES": PASS_CHECK}})
    assert facts["slide1.body"]["verdict"] == "CONFIRMED" and "RELIGHT IMAGES" in images
    with pytest.raises(plan_build.PlanInputError):
        plan_build.load_verdicts({"facts": {"slide1.body": {"verdict": "LOOKS FINE"}}})


def test_a_plan_is_found_by_story_id(tmp_path):
    assert plan_build.plan_path_for(72, tmp_path) is None
    (tmp_path / "story-72.json").write_text("{}", encoding="utf-8")
    assert plan_build.plan_path_for(72, tmp_path).name == "story-72.json"


# ---- images ----

def test_an_image_must_really_be_on_the_official_page():
    markup = f'<img src="/media/relight-demo.jpg?width=1200" alt="Relight">'
    assert plan_build.image_on_page(IMG, markup, PAGE) == (True, "Relight")
    assert plan_build.image_on_page(IMG, '<script>{"hero":"/media/relight-demo.jpg"}</script>', PAGE)[0]
    assert plan_build.image_on_page(IMG, "<p>no images here</p>", PAGE) == (False, "")


def test_image_keys_point_at_the_cover_or_a_feature_slide():
    v = views()
    assert plan_build.slot_for_key("cover", v) == "01"
    assert plan_build.slot_for_key("RELIGHT IMAGES", v) == "02"
    assert plan_build.slot_for_key("NOT A SLIDE", v) is None and plan_build.slot_for_key("price", v) is None


def place(tmp_path, entries, checks=None, markup=None, data=None):
    return plan_build.place_images(
        entries, checks or {}, views(), tmp_path / "out", ["adobe.com", "blog.adobe.com"],
        fetch_page=lambda url: markup if markup is not None else '<img src="/media/relight-demo.jpg" alt="Relight">',
        fetch_image=lambda url: data if data is not None else jpeg(), trim=None)


def test_a_checked_official_image_is_placed_on_its_feature_slide(tmp_path):
    placed, log, md = place(tmp_path, {"RELIGHT IMAGES": {"image_url": IMG, "page_url": PAGE, "check": PASS_CHECK}})
    assert list(placed) == ["02"] and (tmp_path / "out" / "images" / "02.jpg").is_file()
    assert "official image placed as 02.jpg" in log[0] and IMG in md


@pytest.mark.parametrize("entry, data, words", [
    ({"image_url": "https://example.com/relight.jpg", "page_url": PAGE, "check": PASS_CHECK}, None, "official domain"),
    ({"image_url": "https://blog.adobe.com/media/other.jpg", "page_url": PAGE, "check": PASS_CHECK}, None,
     "does not appear"),
    ({"image_url": IMG, "page_url": PAGE, "check": {**PASS_CHECK, "looks_ai_generated": True}}, None, "did not pass"),
    ({"image_url": IMG, "page_url": PAGE}, None, "no image check"),
    ({"image_url": IMG, "page_url": PAGE, "check": PASS_CHECK}, jpeg(800, 600), "under 1000px"),
    ({"image_url": IMG, "page_url": PAGE, "check": PASS_CHECK}, b"<html>not an image</html>", "not a JPEG"),
])
def test_an_image_that_breaks_a_rule_stops_the_build(tmp_path, entry, data, words):
    with pytest.raises(plan_build.PlanInputError, match=words):
        place(tmp_path, {"RELIGHT IMAGES": entry}, data=data)


def test_one_image_is_never_shown_on_two_feature_slides(tmp_path):
    entry = {"image_url": IMG, "page_url": PAGE, "check": PASS_CHECK}
    with pytest.raises(plan_build.PlanInputError, match="already on"):
        place(tmp_path, {"RELIGHT IMAGES": entry, "NEW STYLES": entry})


def test_old_slide_images_are_removed_so_only_the_plan_images_render(tmp_path):
    images_dir = tmp_path / "out" / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "03.jpg").write_bytes(jpeg())
    (images_dir / "notes.txt").write_text("kept", encoding="utf-8")
    place(tmp_path, {})
    assert not (images_dir / "03.jpg").exists() and (images_dir / "notes.txt").exists()


# ---- the build ----

def test_a_dry_run_builds_into_the_preview_folder_and_logs_nothing(tmp_path, offline_story, isolated_activity_log):
    result = build(tmp_path, offline_story, write_plan(tmp_path))
    folder = Path(result["folder"])
    assert folder.parent == tmp_path / "previews" and result["dry_run"] is True
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    assert "official_url" not in plan and "story" not in plan
    assert "made without Claude" in (folder / "sources.md").read_text(encoding="utf-8")
    assert "DRY RUN" in (folder / "sources.md").read_text(encoding="utf-8")
    status = carousel_status.read_status(folder)
    assert status["status"] == "draft" and status["preview"] is True  # a preview is never sent for approval
    assert status["made_without_claude"] is True
    assert not isolated_activity_log.exists() or "fact_check" not in isolated_activity_log.read_text(encoding="utf-8")


def test_a_quote_that_is_not_on_the_official_page_stops_the_build(tmp_path, offline_story):
    plan = json.loads(json.dumps(FIXTURE["plan"]))
    plan["slides"][0]["body"]["quote"] = "a quote the official page never wrote"
    path = write_plan(tmp_path, **plan)
    with pytest.raises(carousel_plan.PlanError, match="slide1.body"):
        build(tmp_path, offline_story, path)


def test_allow_removed_drops_the_claim_instead(tmp_path, offline_story):
    plan = json.loads(json.dumps(FIXTURE["plan"]))
    plan["slides"][0]["body"]["quote"] = "a quote the official page never wrote"
    result = build(tmp_path, offline_story, write_plan(tmp_path, **plan), allow_removed=True)
    assert [r["id"] for r in result["removed"]] == ["slide1.body"]


def test_a_plan_with_an_em_dash_never_builds(tmp_path, offline_story):
    plan = json.loads(json.dumps(FIXTURE["plan"]))
    plan["captions"]["tpm"]["closing"]["text"] = "Which tool \u2014 would you try first?"
    with pytest.raises(carousel.LintError):
        build(tmp_path, offline_story, write_plan(tmp_path, **plan))


def test_the_plan_needs_its_official_page_and_the_right_story(tmp_path, offline_story):
    path = write_plan(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({k: v for k, v in data.items() if k != "official_url"}), encoding="utf-8")
    with pytest.raises(plan_build.PlanInputError, match="official_url"):
        build(tmp_path, offline_story, path)
    with pytest.raises(plan_build.PlanInputError, match="story 99"):
        build(tmp_path, offline_story, write_plan(tmp_path, story=99))


def test_a_real_build_respects_the_daily_cap(tmp_path, offline_story, monkeypatch):
    monkeypatch.setattr(carousel, "item_folder", lambda title, seen: tmp_path / "carousels" / "2026-11-23-ps")
    carousel_auto.record(offline_story["db"], 5, NOW - timedelta(hours=1), "ok", "other", "draft ready")
    with pytest.raises(carousel.Refused, match="daily cap"):
        build(tmp_path, offline_story, write_plan(tmp_path), dry_run=False)


def test_an_approved_carousel_is_never_rebuilt(tmp_path, offline_story, monkeypatch):
    folder = tmp_path / "carousels" / "2026-11-23-ps"
    folder.mkdir(parents=True)
    carousel_status.set_status(folder, "approved")
    monkeypatch.setattr(carousel, "item_folder", lambda title, seen: folder)
    with pytest.raises(carousel.Refused, match="approved"):
        build(tmp_path, offline_story, write_plan(tmp_path), dry_run=False)


# ---- publishing ----

def test_a_dry_run_is_never_published():
    with pytest.raises(ValueError):
        plan_build.publish({"dry_run": True, "folder": "x", "story": 1, "title": "t"})


def test_publish_records_sends_the_ready_message_and_pushes_state(tmp_path, monkeypatch):
    root = project(tmp_path)
    (root / "data").mkdir()
    db = stored_db(root / "data")
    folder = root / "output" / "carousels" / "2026-11-23-ps"
    folder.mkdir(parents=True)
    carousel_status.write_build(folder, {"fact_check_passed": True, "lint_passed": True, "design_fail": 0,
                                         "title": "Photoshop 2027 is here"})
    monkeypatch.setattr(carousel_bot, "_refresh_pages", lambda root: None)
    sent, git, sync = [], FakeGit(), FakeSync()
    result = {"dry_run": False, "folder": folder, "story": 72, "title": "Photoshop 2027 is here", "slides": 5,
              "confirmed": 12, "removed": [], "missing": [], "placed": ["02.jpg"], "design": []}
    summary = plan_build.publish(result, NOW, root=root, git=git, sync=sync, safety=lambda r: [],
                                 notify=lambda text, url: sent.append(text), webhook=FAKE_WEBHOOK)
    assert carousel_auto.already_built(db, 72)
    assert len(sent) == 1 and sent[0].startswith("Carousel ready for approval: Photoshop 2027 is here")
    assert sync.calls == [("push", "laptop")] and summary["push"] == "committed and pushed"


def test_publish_does_not_push_when_the_safety_check_fails(tmp_path, monkeypatch):
    root = project(tmp_path)
    (root / "data").mkdir()
    stored_db(root / "data")
    folder = root / "output" / "carousels" / "x"
    folder.mkdir(parents=True)
    monkeypatch.setattr(carousel_bot, "_refresh_pages", lambda root: None)
    git = FakeGit()
    summary = plan_build.publish({"dry_run": False, "folder": folder, "story": 3, "title": "t", "slides": 4,
                                  "confirmed": 1, "removed": [], "missing": [], "placed": [], "design": []},
                                 NOW, root=root, git=git, sync=FakeSync(), safety=lambda r: ["a PC path"],
                                 notify=lambda *a: pytest.fail("a draft is not announced"), webhook=FAKE_WEBHOOK)
    assert "not pushed" in summary["push"] and not any(c.startswith("commit") for c in git.calls)
    assert "not waiting" in summary["slack"]


# ---- the bot and the watcher with Claude off ----

def test_only_stories_with_a_plan_are_built_and_a_failed_plan_waits_for_a_new_one(tmp_path):
    db = stored_db(tmp_path)
    plans = tmp_path / "plans"
    plans.mkdir()
    (plans / "story-2.json").write_text("{}", encoding="utf-8")
    ready, skipped = plan_build.stories_with_plans(db, [(1, "a"), (2, "b")], plans)
    assert ready == [(2, "b")] and "no plan written yet" in skipped[0]
    carousel_auto.record(db, 2, datetime.now(timezone.utc) + timedelta(minutes=1), "failed", None, "quote not found")
    ready, skipped = plan_build.stories_with_plans(db, [(2, "b")], plans)
    assert ready == [] and "save a fixed plan" in skipped[0]
    later = time.time() + 3600
    os.utime(plans / "story-2.json", (later, later))
    assert plan_build.stories_with_plans(db, [(2, "b")], plans)[0] == [(2, "b")]


def test_the_bot_with_claude_off_never_calls_claude(tmp_path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.setattr(carousel_bot, "webhook_or_none", lambda: None)
    monkeypatch.setattr(carousel_auto, "pending_stories", lambda db, now: [(5, "Story with no plan")])
    monkeypatch.setattr(carousel, "run_story", lambda *a, **k: pytest.fail("Claude build must never run"))
    monkeypatch.setattr(classify, "ask_claude", lambda *a, **k: pytest.fail("Claude must never be called"))
    summary = carousel_bot.run_once(root, NOW, git=FakeGit(staged=False), sync=FakeSync(), safety=lambda r: [],
                                    no_claude=True, plan_dir=tmp_path / "plans")
    assert summary["built"] == ["5: skipped (no plan written yet; Claude is off)"]
    assert summary["rebuilt"] == []


def test_the_watcher_plans_only_mode_never_starts_a_claude_build(tmp_path, monkeypatch):
    db = stored_db(tmp_path)
    monkeypatch.setattr(carousel, "run_story", lambda *a, **k: pytest.fail("Claude build must never run"))
    monkeypatch.setattr(run, "ROOT", tmp_path)
    outcomes = run.after_official_alerts(db, [(9, "x")], NOW, FAKE_WEBHOOK, no_claude=True,
                                         plan_dir=str(tmp_path / "plans"))
    assert outcomes == ["9: skipped (no plan written yet; Claude is off)"]


# ---- the pending list ----

def test_the_pending_list_saves_the_official_text_for_the_plan_writer(tmp_path):
    db = stored_db(tmp_path)
    story = fake_story()
    config = {"official_domains": {"Adobe": ["adobe.com"]}}
    row = pending_carousels.describe(story, db, config, tmp_path)
    assert row["key"] == 72 and row["official_domains"] == ["adobe.com"] and row["plan"] is None
    page = carousel.OfficialPage(url=PAGE, text="Photoshop 2027 brings new tools.",
                                 markup=f'<p>x</p><img src="{IMG}" alt="Relight">', pages=[(PAGE, f'<img src="{IMG}">')])
    saved = pending_carousels.save_official(story, config, None, tmp_path, locate=lambda *a: page)
    assert "Photoshop 2027 brings new tools." in Path(saved["official_text_path"]).read_text(encoding="utf-8")
    assert IMG in Path(saved["official_images_path"]).read_text(encoding="utf-8")
    failed = pending_carousels.save_official(story, config, None, tmp_path,
                                             locate=lambda *a: (_ for _ in ()).throw(carousel.Refused("none found")))
    assert failed == {"official_url": None, "official_problem": "none found"}


# ---- every feature slide has an official image; previews are never sent for approval ----

def test_a_feature_slide_without_an_official_image_stops_the_build(tmp_path, offline_story):
    path = write_plan(tmp_path)
    with pytest.raises(plan_build.PlanInputError, match="no official image"):
        plan_build.build_story(
            "72", path, None, render=False, now=NOW, locate=offline_story["locate"],
            place=lambda entries, checks, views, out_dir, domains: ({}, [], "# Images\n"),
            preview_root=tmp_path / "previews", dry_run=True)


def test_require_feature_images_names_each_bare_slide():
    views = [{"type": "cover"}, {"type": "feature", "headline": "RELIGHT"}, {"type": "feature", "headline": "REMOVE"}]
    plan_build.require_feature_images({"02": {}, "03": {}}, views)  # every feature slide has its image
    with pytest.raises(plan_build.PlanInputError, match=r"slide 03 \(REMOVE\)"):
        plan_build.require_feature_images({"02": {}}, views)


def test_a_dry_run_preview_is_never_marked_waiting_for_david(tmp_path, offline_story, isolated_activity_log):
    result = build(tmp_path, offline_story, write_plan(tmp_path))
    status = carousel_status.read_status(Path(result["folder"]))
    assert status["status"] == "draft" and status.get("preview") is True


def test_a_decimal_number_keeps_a_body_one_sentence():
    plan = json.loads(json.dumps(FIXTURE["plan"]))
    plan["slides"][0]["body"]["text"] = "Its arm has a 7.8 cm wider reach than before."
    carousel_plan.load_plan(plan)  # no "one sentence" error for the decimal point
    plan["slides"][0]["body"]["text"] = "Its arm is wider. It reaches more."
    with pytest.raises(carousel_plan.PlanError, match="one sentence"):
        carousel_plan.load_plan(plan)
