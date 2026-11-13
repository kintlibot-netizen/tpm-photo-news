"""Phase 3 fix round 3g: a stable slide plan across rebuilds, the Camera Angles override that follows its feature, caption hooks
that the fact check may not remove, the hyphen rule for slide bodies only, and the strip beside the Generative Restyle poster
(two greys, with the Layers panel laid over half of the edge). No network and no Claude. The browser tests are skipped
when Playwright or Chromium is not available."""
import copy
import json

import pytest
from conftest import ROOT

import border_trim
import carousel
import carousel_plan
import carousel_render
import image_override
from carousel_text import lint_texts
from test_phase3_fix3c import H, W, decode_png, make_png, screen_pixel, trimmed_or_skip
from test_phase3_fix3f import STORY

PS = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
CAMERA = json.loads((ROOT / "fixtures" / "carousel" / "canon-eos-r8-mark-ii.json").read_text(encoding="utf-8"))
LIGHT_TEXT = (PS["official_text"] + " Photoshop is introducing new ways to edit. Relight creatively adds new light "
              "sources that dynamically and naturally blend into the scene. Quick Compare makes it easier to review "
              "your edits.")


def no_trim(data):
    return data, {"trimmed": False}


def feature(headline, body="Explore it in the app."):
    quote = "Relight creatively adds new light sources"
    return {"template": "left_body", "label": "NEW TOOL", "headline": {"text": headline, "quote": quote},
            "accent": {"text": "A BENEFIT", "quote": quote}, "body": {"text": body, "quote": quote}, "specs": []}


def plan_with(*headlines):
    data = copy.deepcopy(PS["plan"])
    data["slides"] = [feature(h) for h in headlines]
    return data


# ---- 1. the Camera Angles override follows its feature, not a slide number ----

@pytest.mark.parametrize("order", [
    ["RELIGHT", "GENERATIVE RESTYLE", "REMOVE TOOL", "QUICK COMPARE", "CAMERA ANGLES"],   # slide 06
    ["RELIGHT", "CAMERA ANGLES", "GENERATIVE RESTYLE", "QUICK COMPARE"],                  # slide 03
    ["CAMERA ANGLES", "RELIGHT", "REMOVE TOOL"],                                          # slide 02
])
def test_the_camera_angles_override_is_used_by_the_slide_about_that_feature_whatever_its_number(tmp_path, order):
    views = [{"type": "cover"}] + [{"type": "feature", "headline": name} for name in order]
    number = order.index("CAMERA ANGLES") + 2
    domains = carousel.load_config()["official_domains"]["Adobe"]
    taken, log = image_override.apply_overrides(image_override.for_story(STORY), views, tmp_path, domains,
                                                trim=no_trim)
    assert taken == {f"{number:02d}"}, log
    slots, missing = carousel_render.slot_images(tmp_path / "images", views)
    assert slots[number - 1]["main"] is not None and slots[number - 1]["main"].stem == f"{number:02d}"
    others = [s["main"] for i, s in enumerate(slots) if i != number - 1]
    assert all(main is None for main in others)  # no other slide shows this image
    assert "ps-beta-camera-controls-3" in log[0] and "change-camera-angles.html" in log[0]


def test_the_override_names_the_official_file_and_urls_by_feature():
    entries = image_override.for_story(STORY)
    assert list(entries) == ["CAMERA ANGLES"]
    entry = entries["CAMERA ANGLES"]
    assert entry["file"] == "ps-beta-camera-controls-3.jpg" and (image_override.OVERRIDES_DIR / entry["file"]).is_file()
    assert entry["image_url"] == ("https://helpx-prod.scene7.com/is/image/HelpxProd/ps-beta-camera-controls-3"
                                  "?$pjpeg$&jpegSize=400&wid=2000")
    assert entry["page_url"] == ("https://helpx.adobe.com/photoshop/desktop/crop-resize-transform/"
                                 "transform-manipulate-reshape/change-camera-angles.html")


# ---- 1b. rebuilding with an existing plan.json keeps the same features ----

def write_plan(tmp_path, data):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def features_of(data):
    return [carousel_plan.feature_key(s) for s in data["slides"]]


def test_an_existing_plan_is_reused_and_no_new_draft_is_made(tmp_path):
    previous = plan_with("RELIGHT", "GENERATIVE RESTYLE", "REMOVE TOOL", "QUICK COMPARE", "CAMERA ANGLES")
    path = write_plan(tmp_path, previous)

    def draft():
        raise AssertionError("a plan.json exists: Claude must not draft again")

    data, note = carousel.plan_for_story(path, draft)
    assert data == previous and features_of(data) == ["relight", "generative restyle", "remove tool", "quick compare",
                                                      "camera angles"]
    assert "reused" in note and "5 feature slides" in note


def test_a_fresh_draft_never_drops_or_reorders_the_features_of_the_earlier_plan(tmp_path):
    previous = plan_with("RELIGHT", "GENERATIVE RESTYLE", "REMOVE TOOL", "QUICK COMPARE", "CAMERA ANGLES")
    previous["slides"][1]["body"]["text"] = "Then refine without re-prompting."  # no longer valid: a new draft is needed
    path = write_plan(tmp_path, previous)
    redrafted = plan_with("QUICK COMPARE", "RELIGHT", "GENERATIVE RESTYLE", "REMOVE TOOL")  # dropped CAMERA, reordered
    redrafted["slides"][2]["body"]["text"] = "Refine it without prompting again."
    data, note = carousel.plan_for_story(path, lambda: copy.deepcopy(redrafted))
    assert features_of(data) == features_of(previous)
    assert data["slides"][1]["body"]["text"] == "Refine it without prompting again."  # the draft's new copy is used
    assert data["slides"][4]["headline"]["text"] == "CAMERA ANGLES"  # the dropped feature kept its earlier slide
    carousel_plan.load_plan(data)
    assert "5 features" in note


def test_a_first_build_drafts_the_plan(tmp_path):
    drafted = plan_with("RELIGHT", "QUICK COMPARE", "REMOVE TOOL")
    data, note = carousel.plan_for_story(tmp_path / "plan.json", lambda: drafted)
    assert data is drafted and note == ""


def test_an_unreadable_plan_json_is_ignored(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("{not json", encoding="utf-8")
    drafted = plan_with("RELIGHT", "QUICK COMPARE", "REMOVE TOOL")
    assert carousel.plan_for_story(path, lambda: drafted)[0] is drafted


def test_the_story_build_reads_the_earlier_plan_before_drafting():
    source = (ROOT / "src" / "carousel.py").read_text(encoding="utf-8")
    assert source.index("plan_note = plan_for_story(") < source.index("factcheck_with_claude(plan, page.text")

# ---- 2. caption hooks are opinions, not claims ----

VERDICTS_REJECTING_HOOKS = {
    "captions.david.hook": {"verdict": "NOT CONFIRMED", "quote": ""},
    "captions.tpm.hook": {"verdict": "NOT CONFIRMED", "quote": ""},
}


def caption_plan(david_hook, tpm_hook):
    data = copy.deepcopy(PS["plan"])
    data["captions"]["david"]["hook"] = {"text": david_hook, "quote": ""}
    data["captions"]["tpm"]["hook"] = {"text": tpm_hook, "quote": ""}
    return carousel_plan.load_plan(data)


def test_an_opinion_hook_the_fact_check_called_not_confirmed_is_kept_as_not_a_fact():
    plan = caption_plan("My favourite Photoshop update is all about light.", "We think Relight is the one to try first.")
    report = carousel_plan.verify(plan, LIGHT_TEXT, VERDICTS_REJECTING_HOOKS)
    verdicts = {r["id"]: r["verdict"] for r in report}
    assert verdicts["captions.david.hook"] == "NOT A FACT" and verdicts["captions.tpm.hook"] == "NOT A FACT"
    # US spelling in the copy (round 3h): a British "favourite" in the draft becomes "favorite" in the caption.
    assert carousel_plan.build_caption(plan, "david").startswith("My favorite Photoshop update is all about light.")
    assert carousel_plan.build_caption(plan, "tpm").startswith("We think Relight is the one to try first.")
    assert not carousel_plan.hook_replaced(plan, "david") and not carousel_plan.hook_replaced(plan, "tpm")


@pytest.mark.parametrize("hook", [
    "My favourite update removes red eye in 2 seconds.",   # a number the text never gives
    "My favourite Photoshop update is the instant one.",   # "instant" is not in the official text
    "Relight adds new light sources.",                     # a plain feature line is a fact, not an opinion
])
def test_a_hook_that_states_a_fact_the_text_does_not_give_is_still_removed(hook):
    plan = caption_plan(hook, "We think Relight is the one to try first.")
    report = carousel_plan.verify(plan, LIGHT_TEXT, VERDICTS_REJECTING_HOOKS)
    assert {r["id"]: r["verdict"] for r in report}["captions.david.hook"] == "NOT CONFIRMED"


def test_a_caption_whose_hook_was_removed_gets_a_hook_in_the_right_voice():
    plan = caption_plan("My favourite update removes red eye in 2 seconds.", "Your photos can now get 3 new things.")
    carousel_plan.verify(plan, LIGHT_TEXT, VERDICTS_REJECTING_HOOKS)
    captions = {who: carousel_plan.build_caption(plan, who) for who in ("david", "tpm")}
    assert carousel_plan.hook_replaced(plan, "david") and carousel_plan.hook_replaced(plan, "tpm")
    assert captions["david"].startswith("My pick from this update is Relight Images.")
    assert captions["tpm"].startswith("We think Relight Images is the one to try first.")
    assert carousel_plan.caption_voice_problems(captions) == []
    assert "removes red eye" not in captions["david"]


def test_a_plan_with_no_feature_still_gets_a_hook_in_each_voice():
    plan = carousel_plan.load_plan(copy.deepcopy(PS["plan"]))
    for slide in plan["slides"]:
        slide["headline"]["ok"] = False
    assert carousel_plan.fallback_hook(plan, "david").split()[0] in ("I", "My")
    assert "we" in carousel_plan.fallback_hook(plan, "tpm").lower().split()


def test_the_factcheck_prompt_says_a_hook_is_judged_on_its_facts_only():
    prompt = carousel_plan.FACTCHECK_PROMPT
    assert ".hook" in prompt and "never rejected for being an opinion" in prompt
    assert "My favorite Photoshop update is all about light." in prompt
    claims = carousel_plan.factcheck_prompt(carousel_plan.iter_facts(caption_plan("My favourite update.", "We think so.")),
                                            LIGHT_TEXT)
    assert '"opinion": true' in claims


def test_the_build_notes_a_replaced_hook_in_sources_md():
    source = (ROOT / "src" / "carousel.py").read_text(encoding="utf-8")
    assert "carousel_plan.hook_replaced(plan, who)" in source and "fallback hook" in source


def test_the_draft_prompt_describes_both_caption_voices():
    prompt = carousel_plan.DRAFT_PROMPT
    assert "Relight lets me add new light sources and adjust position, color and brightness." in prompt
    assert "You can add new light sources and adjust position, color and brightness." in prompt
    assert 'MUST open with "I" or "my"' in prompt and '"we" or "our" MUST appear' in prompt


# ---- 3. the hyphen rule is for slide bodies, not for an official term in a quick take ----

def test_the_camera_sample_builds_with_no_hyphen_problem_and_official_terms_keep_their_hyphen():
    plan = carousel_plan.load_plan(copy.deepcopy(CAMERA["plan"]))
    carousel_plan.verify(plan, CAMERA["official_text"])
    views = carousel_plan.build_views(plan)
    assert lint_texts(carousel_plan.slide_texts(views)) == []
    data = copy.deepcopy(CAMERA["plan"])
    data["price"]["quick_take"]["sentence"]["text"] = "The original EOS R8 has no in-body stabilization."
    carousel_plan.load_plan(data)  # a quick take may carry an official term with a hyphen
    data["slides"][0]["body"]["text"] = "Shoot steadier with in-body stabilization."
    with pytest.raises(carousel_plan.PlanError, match="hyphenated word"):
        carousel_plan.load_plan(data)  # a slide body may not


# ---- 4. the strip beside the Generative Restyle poster ----

PANEL = (50, 50, 50)
BEZEL = (150, 150, 150)
STRIP = (190, 190, 190)


def test_a_light_strip_under_a_panel_laid_over_half_of_the_edge_is_still_trimmed():
    strip = 15
    top, bottom = 40, 190  # the Layers panel: half of the rows, dark, reaching the right edge over the strip

    def pixel(x, y):
        if x >= 250 and top <= y < bottom:
            return PANEL
        return STRIP if x >= W - strip else screen_pixel(x, y)

    new, info = trimmed_or_skip(make_png(W, H, pixel))
    assert info["trimmed"] is True
    assert (info["left"], info["right"], info["top"], info["bottom"]) == (0, strip, 0, 0)
    width, height, _, _ = decode_png(new)
    assert (width, height) == (W - strip - border_trim.INSET, H)


def test_a_second_grey_strip_beside_the_bezel_goes_in_a_second_pass():
    bezel, strip = 30, 14

    def pixel(x, y):
        if x >= W - strip:
            return STRIP
        if x >= W - strip - bezel:
            return BEZEL
        return screen_pixel(x, y)

    new, info = trimmed_or_skip(make_png(W, H, pixel))
    assert info["trimmed"] is True and info["right"] == bezel + strip and info["passes"] == 2
    assert (info["left"], info["top"], info["bottom"]) == (0, 0, 0)
    width, _, channels, rows = decode_png(new)
    assert width == W - bezel - strip - 2 * border_trim.INSET
    last = tuple(rows[10][(width - 1) * channels:(width - 1) * channels + 3])
    assert last == screen_pixel(width - 1, 10)  # the last column is picture, not grey


def test_the_second_pass_never_cuts_into_a_dark_panel_beside_the_strip():
    strip = 12

    def pixel(x, y):
        if x >= W - strip:
            return STRIP
        if x >= 250 and 40 <= y < 190:
            return PANEL
        return screen_pixel(x, y)

    new, info = trimmed_or_skip(make_png(W, H, pixel))
    assert info["trimmed"] is True and info["right"] == strip and info["passes"] == 1


def test_the_trim_describes_a_second_pass():
    info = {"left": 0, "right": 44, "top": 0, "bottom": 0, "inset": 2, "passes": 2, "width": 352, "height": 300,
            "source_width": 400, "source_height": 300}
    assert "in each of 2 passes" in border_trim.describe(info)
    assert "passes" not in border_trim.describe({**info, "passes": 1})
