"""Phase 3 fix round 3f: a manual official image override (slide 06 Camera Angles), the per side strip trim, no hyphens in
body copy and balanced body text, captions in the right voice, and no widow warning for a split model name.
No network and no Claude. The browser tests are skipped when Playwright or Chromium is not available."""
import json
import re

import pytest
import requests
from conftest import ROOT

import border_trim
import carousel
import carousel_plan
import carousel_render
import design_check
import image_override
import images
from carousel_text import hyphenated_words, lint_texts
from test_phase3_fix3c import CAMERA_URL, H, W, decode_png, make_png, screen_pixel, trimmed_or_skip

STORY = "2026-11-11-photoshop-can-now-relight-photos-and-adjusting-the-camera-an"
IMAGE_URL = "https://helpx-prod.scene7.com/is/image/HelpxProd/ps-beta-camera-controls-3?$pjpeg$&jpegSize=400&wid=2000"
ADOBE = ["adobe.com", "helpx-prod.scene7.com"]


def camera_view(headline="CAMERA ANGLES"):
    return {"type": "feature", "headline": headline}


def entry(**changes):
    base = {"feature": "CAMERA ANGLES", "file": "pic.png", "image_url": IMAGE_URL, "page_url": CAMERA_URL}
    return {**base, **changes}


def no_trim(data):
    return data, {"trimmed": False}


# ---- 1. the manual official image override ----

def test_the_real_override_entry_is_valid_and_its_file_is_in_the_project():
    config = carousel.load_config()
    slots = image_override.for_story(STORY)
    assert list(slots) == ["CAMERA ANGLES"]  # keyed by feature name, not by slide number
    problem = image_override.problem_with(slots["CAMERA ANGLES"], camera_view(), config["official_domains"]["Adobe"],
                                          image_override.OVERRIDES_DIR)
    assert problem == ""
    assert slots["CAMERA ANGLES"]["image_url"] == IMAGE_URL and slots["CAMERA ANGLES"]["page_url"] == CAMERA_URL
    assert slots["CAMERA ANGLES"]["file"] == "ps-beta-camera-controls-3.jpg"


def test_overrides_of_other_stories_are_not_used(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps({"other-story": {"CAMERA ANGLES": entry()}}), encoding="utf-8")
    assert image_override.for_story(STORY, path) == {}
    assert image_override.for_story("other-story", path).keys() == {"CAMERA ANGLES"}
    assert image_override.load_overrides(tmp_path / "missing.json") == {}


def test_known_page_images_maps_the_official_page_to_its_og_image(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps({STORY: {"CAMERA ANGLES": entry(page_title="Change camera angles")}}), encoding="utf-8")
    assert image_override.known_page_images(path) == {CAMERA_URL: {"image_url": IMAGE_URL,
                                                                    "title": "Change camera angles"}}


def folder_with_image(tmp_path, name="pic.png"):
    folder = tmp_path / "official"
    folder.mkdir()
    (folder / name).write_bytes(make_png(1200, 600, screen_pixel))
    return folder


def test_a_usable_override_is_placed_for_its_slide_and_records_both_urls(tmp_path):
    folder = folder_with_image(tmp_path)
    out = tmp_path / "out"
    (out / "images").mkdir(parents=True)
    (out / "images" / "06.jpg").write_bytes(b"old")  # an older file of the slot never stays beside the new one
    views = [{"type": "cover"}] + [camera_view("RELIGHT")] * 4 + [camera_view()]
    taken, log = image_override.apply_overrides({"CAMERA ANGLES": entry()}, views, out, ADOBE, trim=no_trim,
                                                folder=folder)
    assert taken == {"06"}
    assert (out / "images" / "06.png").is_file() and not (out / "images" / "06.jpg").exists()
    assert IMAGE_URL in log[0] and CAMERA_URL in log[0] and "automatic image search is skipped" in log[0]


def test_a_trimmed_override_is_saved_as_the_trimmed_png(tmp_path):
    folder = folder_with_image(tmp_path)
    out = tmp_path / "out"
    trimmed = make_png(900, 600, screen_pixel)
    info = {"trimmed": True, "left": 150, "right": 150, "top": 0, "bottom": 0, "inset": 2, "width": 900,
            "height": 600, "source_width": 1200, "source_height": 600}
    views = [{"type": "cover"}] * 5 + [camera_view()]
    image_override.apply_overrides({"CAMERA ANGLES": entry()}, views, out, ADOBE, trim=lambda d: (trimmed, info),
                                   folder=folder)
    assert (out / "images" / "06.png").read_bytes() == trimmed


@pytest.mark.parametrize("changes, view, reason", [
    ({}, camera_view("RELIGHT"), "no feature slide for that feature"),
    ({"page_url": "https://example.com/p.html"}, camera_view(), "page_url is not on an official domain"),
    ({"image_url": "https://cdn.example.com/p.jpg"}, camera_view(), "image_url is not on an official domain"),
    ({"file": "missing.png"}, camera_view(), "is not in"),
    ({"page_url": ""}, camera_view(), "no page_url"),
    ({}, {"type": "cover"}, "no feature slide for that feature"),
])
def test_an_override_that_does_not_fit_is_skipped_with_the_reason(tmp_path, changes, view, reason):
    folder = folder_with_image(tmp_path)
    out = tmp_path / "out"
    views = [{"type": "cover"}] * 5 + [view]
    taken, log = image_override.apply_overrides({"CAMERA ANGLES": entry(**changes)}, views, out, ADOBE, trim=no_trim,
                                                folder=folder)
    assert taken == set() and reason in log[0] and "automatic search runs" in log[0]
    assert not list((out / "images").glob("06.*"))


def test_an_override_for_a_feature_the_story_does_not_have_is_skipped(tmp_path):
    folder = folder_with_image(tmp_path)
    taken, log = image_override.apply_overrides({"CAMERA ANGLES": entry()}, [{"type": "cover"}], tmp_path / "out", ADOBE,
                                                trim=no_trim, folder=folder)
    assert taken == set() and "no feature slide for that feature" in log[0]


def test_the_automatic_search_skips_a_slot_that_has_an_override():
    source = (ROOT / "src" / "carousel.py").read_text(encoding="utf-8")
    assert "if s.name not in overridden" in source and "image_override.apply_overrides" in source


# ---- 1b. scene7 images and the helpx 403 ----

def test_a_scene7_image_is_tried_at_a_larger_wid_then_as_published():
    small = IMAGE_URL.replace("wid=2000", "wid=800")
    urls = images.larger_urls(small)
    assert urls[0].endswith("wid=2000") and "$pjpeg$&jpegSize=400" in urls[0] and urls[-1] == small
    assert images.larger_urls(IMAGE_URL) == [IMAGE_URL]  # already at 2000: nothing larger to try


def test_a_helpx_page_that_returns_403_still_offers_its_known_og_image():
    def refusing(url):
        raise requests.HTTPError("403")

    known = {CAMERA_URL: {"image_url": IMAGE_URL, "title": "Change camera angles in Photoshop on desktop"}}
    pages, tags, notes = images.discover_image_pages([], [CAMERA_URL], ["Camera Angles"], ADOBE, fetch=refusing,
                                                     fallback_images=known)
    assert len(pages) == 1 and pages[0][0] == CAMERA_URL
    found, _ = images.parse_page(pages[0][1], CAMERA_URL)
    assert [i["src"] for i in found] == [IMAGE_URL]
    assert tags == {CAMERA_URL: "Camera Angles"}
    assert any("known official og:image" in n for n in notes)
    # with no known image the page is skipped as before
    pages, _, notes = images.discover_image_pages([], [CAMERA_URL], ["Camera Angles"], ADOBE, fetch=refusing)
    assert pages == [] and "skipped" in notes[0]


def test_the_scene7_host_is_an_official_adobe_domain():
    assert "helpx-prod.scene7.com" in carousel.load_config()["official_domains"]["Adobe"]


# ---- 2. the strip trim judges each side on its own ----

def test_a_grey_strip_on_one_side_only_is_trimmed_and_nothing_else():
    strip = 15
    data = make_png(W, H, lambda x, y: (150, 150, 150) if x >= W - strip else screen_pixel(x, y))
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is True
    assert (info["left"], info["right"], info["top"], info["bottom"]) == (0, strip, 0, 0)
    width, height, channels, rows = decode_png(new)
    assert (width, height) == (W - strip - border_trim.INSET, H)
    for x, y in ((0, 0), (10, 40), (width - 1, height - 1), (width // 2, height // 2)):
        assert tuple(rows[y][x * channels:x * channels + 3]) == screen_pixel(x, y)


def test_a_dark_strip_on_one_side_is_trimmed_too():
    data = make_png(W, H, lambda x, y: (28, 28, 28) if x < 10 else screen_pixel(x, y))
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is True and (info["left"], info["right"]) == (10, 0)


def test_white_bars_left_and_right_are_trimmed_with_a_slightly_noisy_edge():
    bars = 80  # 20 percent of the width, like the camera angles screenshot
    data = make_png(400, H, lambda x, y: (255 - (x + y) % 3, 255, 254) if x < bars or x >= 400 - bars
                    else screen_pixel(x, y))
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is True and (info["left"], info["right"], info["top"], info["bottom"]) == (bars, bars, 0, 0)


def test_a_wide_dark_panel_is_never_cut_into():
    data = make_png(W, H, lambda x, y: (30, 30, 30) if x < 100 else screen_pixel(x, y))  # 25 percent of the width
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is False and new == data


def test_a_coloured_edge_is_not_a_strip():
    data = make_png(W, H, lambda x, y: (200, 30, 30) if x < 20 else screen_pixel(x, y))
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is False and new == data


# ---- 3 and 4. no hyphens in body copy, balanced text ----

def test_hyphenated_words_are_found_but_number_ranges_are_not():
    assert hyphenated_words("then refine without re-prompting") == ["re-prompting"]
    assert hyphenated_words("a non-destructive, fine-tune step") == ["non-destructive", "fine-tune"]
    assert hyphenated_words("24-50 mm and 4K 60p") == []


def test_the_lint_fails_on_a_hyphenated_word_in_slide_body_copy_only():
    assert lint_texts([("slide 03 body", "Refine it without re-prompting.")])
    assert lint_texts([("slide 03 body", "Type a description in Prompt to edit, then refine it without prompting again.")]) == []
    assert lint_texts([("slide 02 headline", "5-AXIS IN-BODY STABILIZATION")]) == []


def test_a_draft_with_a_hyphenated_body_word_is_rejected_so_claude_rewrites_it():
    plan = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))["plan"]
    plan["slides"][0]["body"] = {"text": "Then refine without re-prompting.", "quote": "x"}
    with pytest.raises(carousel_plan.PlanError, match="hyphenated word"):
        carousel_plan.load_plan(plan)


def test_all_text_has_hyphens_none_and_body_copy_is_balanced():
    css = carousel_render.CSS
    assert re.search(r"\*\{[^}]*hyphens:none", css)
    line = next(l for l in css.splitlines() if "text-wrap:balance" in l and ".body" in l)
    assert ".text" in line and ".quick-sentence" in line


def test_the_draft_prompt_asks_for_a_two_line_body_without_hyphenated_words():
    prompt = carousel_plan.DRAFT_PROMPT
    assert "NEVER use a hyphenated word in the body" in prompt
    assert "Type a description in Prompt to edit, then refine it without prompting again." in prompt
    assert "Compare before and after without hiding layers one by one." in prompt


# ---- 5. captions ----

def test_the_draft_prompt_asks_for_a_scroll_stopping_david_hook_and_a_tpm_that_is_not_the_editor():
    prompt = carousel_plan.DRAFT_PROMPT
    assert 'Do NOT start more than one sentence with "I can"' in prompt
    assert "My favorite Photoshop update is all about light." in prompt
    assert "NEVER the one doing the editing" in prompt
    assert "We think Relight is the one to try first." in prompt


def test_tpm_saying_we_can_and_david_repeating_i_can_are_flagged():
    problems = carousel_plan.caption_voice_problems({
        "david": "I can add light. I can adjust color. Which?", "tpm": "We can adjust position. Which?"})
    assert len(problems) == 2 and "we can" in problems[0] and "I can" in problems[1]
    ok = {"david": "My favourite update is all about light. Relight lets me add light. Which would you try?",
          "tpm": "We think Relight will change how you fix flat light. Which would you try?"}
    assert carousel_plan.caption_voice_problems(ok) == []
    assert carousel_plan.caption_voice_problems({"david": "I can add light. Relight lets me move it. Which?",
                                                 "tpm": "We would try Relight first."}) == []


# ---- 7. the split model name on the cover is not a widow ----

def test_a_cover_headline_split_before_its_model_number_is_not_a_widow():
    cover = {"type": "cover", "label": "L", "headline": "PHOTOSHOP 2027", "subline": None, "features": [],
             "product": "P", "footer": "SWIPE"}
    assert [f for f in design_check.check_slides([cover] * 4) if f["rule"] == "widow"] == []
    odd = dict(cover, headline="NEW LIGHT SOURCES\nTODAY")
    assert [f for f in design_check.check_slides([odd] * 4) if f["rule"] == "widow"]
