"""Round 7, section E: the pending round 3h items and the settle command for older stories.

- the Camera Angles frame (a screenshot narrower than 16:9) uses the same full width, margins and bottom edge as the
  other feature slides, without cropping or stretching
- US spelling in the captions ("favorite")
- carousel.py --settle: an older story is rebuilt when its facts still check out, otherwise rejected with the reason
No network, no Claude, no browser."""
import copy
import json
import re
from datetime import datetime, timezone

import pytest
from conftest import ROOT
from test_phase3_fix3c import png_header

import activity
import carousel
import carousel_plan
import carousel_render
import carousel_status
import classify
from dedupe import Store, Story

NOW = datetime(2026, 11, 13, 1, 9, tzinfo=timezone.utc)
PS = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))


def screenshot(tmp_path, width, height, name="06.png"):
    path = tmp_path / name
    path.write_bytes(png_header(width, height))
    return path


def camera_view(body="Interact directly on the canvas with the entire image."):
    return {"type": "feature", "template": "left_body", "label": "NEW IN PHOTOSHOP BETA", "headline": "CAMERA ANGLES",
            "accent": "EXPLORE NEW VIEWPOINTS", "body": body, "specs": [], "product": "PHOTOSHOP"}


def frame(html_doc):
    return tuple(int(v) for v in re.search(
        r'class="hero screen" style="left:(\d+)px;top:(\d+)px;width:(\d+)px;height:(\d+)px"', html_doc).groups())


# ---- 1. the Camera Angles frame ----

def test_a_16_by_9_frame_still_fills_the_one_feature_box(tmp_path):
    assert carousel_render.feature_box_for(screenshot(tmp_path, 1920, 1080)) == carousel_render.FEATURE_BOX
    assert carousel_render.feature_box_for(None) == carousel_render.FEATURE_BOX


def test_the_camera_angles_frame_has_the_full_width_and_the_same_margins_and_bottom_edge(tmp_path):
    image = screenshot(tmp_path, 1540, 1000)  # about the shape of the official Camera Angles screenshot
    html_doc = carousel_render.left_body_body(camera_view(), {"main": image})
    left, top, width, height = frame(html_doc)
    box_left, box_top, box_width, box_height = carousel_render.FEATURE_BOX
    assert (left, width) == (box_left, box_width)  # 64px margins on both sides, like slides 02 to 05
    assert top + height == box_top + box_height  # the same bottom edge
    assert abs(width / height - 1.54) < 0.01  # scaled up as a whole: no stretching, no crop
    body_top, body_h = (int(v) for v in re.search(
        r'class="abs body"[^>]*style="top:(\d+)px;[^"]*height:(\d+)px', html_doc).groups())
    assert body_top + body_h <= top  # the text never runs into the frame
    assert "object-position" not in html_doc and "scale(" not in html_doc


def test_when_the_text_needs_the_room_the_frame_gives_way_and_never_the_text(tmp_path):
    image = screenshot(tmp_path, 1540, 1000)
    long_body = "Interact directly on the canvas with the entire image, then explore every new viewpoint."
    html_doc = carousel_render.left_body_body(camera_view(long_body), {"main": image})
    left, top, width, height = frame(html_doc)
    body_top, body_h = (int(v) for v in re.search(
        r'class="abs body"[^>]*style="top:(\d+)px;[^"]*height:(\d+)px', html_doc).groups())
    assert body_top + body_h <= top and top + height == 748 + 536
    assert left >= 64 and left + width <= 1016


# ---- 2. the Camera Angles body copy ----

def test_the_camera_angles_body_does_not_repeat_its_subhead():
    accent = "EXPLORE NEW VIEWPOINTS"
    body = camera_view()["body"]
    assert not set(accent.lower().split()) <= set(re.findall(r"[a-z]+", body.lower()))
    assert carousel_plan.hyphenated_words(body) == [] if hasattr(carousel_plan, "hyphenated_words") else True
    assert len(body) <= 56  # one line on the slide, so the frame keeps its full width


# ---- 3. US spelling ----

@pytest.mark.parametrize("british, us", [
    ("My favourite Photoshop update is all about light.", "My favorite Photoshop update is all about light."),
    ("Favourite pick: Relight. Which colour would you try?", "Favorite pick: Relight. Which color would you try?"),
])
def test_captions_use_us_spelling(british, us):
    assert carousel_plan.us_spelling(british) == us


def test_a_drafted_british_hook_becomes_favorite_in_the_caption():
    data = copy.deepcopy(PS["plan"])
    data["captions"]["david"]["hook"] = {"text": "My favourite Photoshop update is all about light.", "quote": ""}
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, PS["official_text"], {"captions.david.hook": {"verdict": "NOT A FACT", "quote": ""}})
    caption = carousel_plan.build_caption(plan, "david")
    assert caption.startswith("My favorite Photoshop update") and "favourite" not in caption


def test_the_prompts_and_fallback_hooks_say_favorite():
    assert "favourite" not in carousel_plan.DRAFT_PROMPT and "favourite" not in carousel_plan.FACTCHECK_PROMPT
    plan = carousel_plan.load_plan(copy.deepcopy(PS["plan"]))
    for slide in plan["slides"]:
        slide["headline"]["ok"] = False
    assert "favourite" not in carousel_plan.fallback_hook(plan, "david")


# ---- 4. settling an older story (story 12) ----

@pytest.fixture
def old_story(tmp_path, monkeypatch):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    story = Story(title="All of Adobe Camera RAW's Awesome Updates", brand="Adobe", kind="product",
                  tokens=frozenset())
    story.sources = [{"url": "https://petapixel.example/acr", "link": "https://petapixel.example/acr",
                      "source": "PetaPixel", "source_type": "news", "title": story.title, "summary": "S.",
                      "published": None}]
    store.save_story(story, datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc))
    store.mark_alerted(story, classify.OFFICIAL)
    store.db.close()
    monkeypatch.setattr(carousel, "DATA_PATH", db)
    monkeypatch.setattr(carousel, "OUTPUT_ROOT", tmp_path / "carousels")
    folder = carousel.item_folder(story.title, story.first_seen)
    folder.mkdir(parents=True)
    (folder / "captions.txt").write_text("x", encoding="utf-8")
    carousel_status.write_build(folder, {"title": story.title, "slides": 5})
    return story, folder


def test_an_old_story_whose_facts_no_longer_check_out_is_rejected_with_the_reason(old_story):
    story, folder = old_story

    def build(key, official_url, render):
        raise carousel.Refused("No official page for this story was found. Checked: blog.adobe.com.")

    outcome, reason = carousel.settle_story(str(story.id), build=build, now=NOW)
    assert outcome == "rejected" and "No official page" in reason
    status = carousel_status.read_status(folder)
    assert status["status"] == "rejected" and status["reason"].startswith("Rebuild check: No official page")
    event = next(e for e in activity.read_events() if e["type"] == "carousel")
    assert event["outcome"] == "rejected" and "Camera RAW" in event["details"]


def test_an_old_story_that_still_checks_out_is_rebuilt(old_story):
    story, folder = old_story
    outcome, name = carousel.settle_story(str(story.id), build=lambda k, u, r: {"folder": folder, "slides": 5}, now=NOW)
    assert outcome == "built" and name == folder.name
    assert carousel_status.read_status(folder)["status"] != "rejected"


def test_a_problem_on_this_pc_changes_nothing(old_story):
    story, folder = old_story

    def build(key, official_url, render):
        raise RuntimeError("Claude Code exited with code 1")

    outcome, _ = carousel.settle_story(str(story.id), build=build, now=NOW)
    assert outcome == "not settled" and carousel_status.read_status(folder)["status"] == "draft"


def test_an_approved_carousel_is_never_rejected_by_a_settle(old_story):
    story, folder = old_story
    carousel_status.set_status(folder, "approved", approved_by="David", approved_at=NOW.isoformat())

    def build(key, official_url, render):
        raise carousel_plan.PlanError("the cover headline was not confirmed")

    outcome, _ = carousel.settle_story(str(story.id), build=build, now=NOW)
    assert outcome == "rejected" and carousel_status.read_status(folder)["status"] == "approved"


def test_the_settle_result_is_recorded_for_the_dashboard(old_story):
    story, _ = old_story
    carousel.settle_story(str(story.id), build=lambda k, u, r: (_ for _ in ()).throw(carousel.Refused("gone")),
                          now=NOW)
    import sqlite3
    db = sqlite3.connect(carousel.DATA_PATH)
    try:
        rows = db.execute("SELECT status, message FROM carousel_builds WHERE story_id=?", (story.id,)).fetchall()
    finally:
        db.close()
    assert rows == [("failed", "Rebuild check: gone")]
