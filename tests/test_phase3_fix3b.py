"""Phase 3 fix round 3b: a feature slide shows only its own feature's image (else the text-led layout), the
Quick Compare poster is accepted with a person in the demo photo, screenshots are never cropped, one image box for
every feature slide, a cyan line on every feature slide on one line, the cover hook, and the caption opener.
No network, no Claude. The one browser test is skipped when Playwright is not installed."""
import copy
import json
import re
import struct
from pathlib import Path

import pytest
from conftest import ROOT

import carousel_plan
import carousel_render
import design_check
import image_pick
import images
from images import Candidate

FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
PASS = {"matches_product": True, "is_real_photo_or_official_screenshot": True, "shows_slide_subject": True,
        "has_watermark": False, "has_people_as_subject": False, "looks_ai_generated": False,
        "notes": "ok", "unreadable": False}
WITH_PERSON = dict(PASS, has_people_as_subject=True)
FEATURES = ["Relight", "Generative Restyle", "Remove Tool", "Quick Compare"]
ACCENT = "NOW CATCHES SHADOWS AND REFLECTIONS"


def png_bytes(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"


def candidate(tmp_path, name, feature="", kind="video poster", size=(1920, 1080), title=""):
    (tmp_path / "candidates").mkdir(exist_ok=True)
    (tmp_path / "candidates" / name).write_bytes(png_bytes(*size))
    return Candidate(file=f"candidates/{name}", page="https://video.tv.adobe.com/v/1", image_url=f"https://x/{name}",
                     width=size[0], height=size[1], alt="", feature=feature, kind=kind,
                     title=title or (f"PS {feature}" if feature else ""))


def slots():
    return [
        image_pick.Slot("01", 1, "Cover: the product, PHOTOSHOP", "cover"),
        image_pick.Slot("02", 2, "Slide about: RELIGHT", "feature", "RELIGHT"),
        image_pick.Slot("03", 3, "Slide about: REMOVE TOOL", "feature", "REMOVE TOOL"),
        image_pick.Slot("04", 4, "Slide about: QUICK COMPARE", "feature", "QUICK COMPARE"),
    ]


def feature_view(template="left_body", headline="REMOVE TOOL", accent=ACCENT, body="It detects footprints, "
                 "reflections, shadows and waves around an object.", specs=None):
    return {"type": "feature", "template": template, "label": "NEW IN PHOTOSHOP", "headline": headline,
            "accent": accent, "body": body, "specs": specs or [], "product": "PHOTOSHOP"}


def spec(value, caption):
    return {"value": value, "caption": caption, "icon": "star"}


def wide_image(tmp_path, name="02.png"):
    path = tmp_path / name
    path.write_bytes(png_bytes(1920, 1080))
    return path


# ---- A. a feature slide only shows an image tagged with its own feature ----

def test_a_feature_slide_is_only_offered_images_tagged_with_its_own_feature(tmp_path):
    relight = candidate(tmp_path, "c01.png", "Relight")
    compare = candidate(tmp_path, "c02.png", "Quick Compare")
    general = candidate(tmp_path, "c03.png", "", kind="image", size=(2400, 1350))
    offered = {s.name: image_pick.candidates_for(s, [relight, compare, general]) for s in slots()}
    assert offered["02"] == [relight]
    assert offered["03"] == []  # Remove Tool has no image of its own: the general image is NOT offered
    assert offered["04"] == [compare]


def test_no_feature_slide_ends_up_with_another_features_image(tmp_path):
    cands = [candidate(tmp_path, "c01.png", "Relight"), candidate(tmp_path, "c03.png", "", kind="image")]
    choices, log = image_pick.pick_for_slots(slots(), cands, tmp_path, "text", "Photoshop",
                                             lambda path, slot, text, name: PASS)
    assert choices["02"].feature == "Relight"
    assert choices["03"] is None and choices["04"] is None
    assert any(line.startswith("slide 03") and "text-led layout" in line for line in log)
    for placed in (tmp_path / "images").iterdir():
        assert placed.stem in ("01", "02")  # nothing was saved for slides 03 and 04


def test_the_cover_may_reuse_a_whole_feature_frame_but_never_a_person_frame(tmp_path):
    relight = candidate(tmp_path, "c01.png", "Relight")
    compare = candidate(tmp_path, "c02.png", "Quick Compare")

    def verify(path, slot, text, name):
        return WITH_PERSON if "c02" in str(path) else PASS

    choices, log = image_pick.pick_for_slots(slots(), [relight, compare], tmp_path, "t", "Photoshop", verify)
    assert choices["04"] is compare  # a person in the official demo does not block it
    assert choices["01"] is relight  # the cover reuses the Relight frame, not the person frame
    assert (tmp_path / "images" / "01.png").exists() and (tmp_path / "images" / "02.png").exists()
    assert any("whole uncropped frame" in line for line in log)


# ---- the Quick Compare poster is accepted on its own slide with a person in it ----

def test_an_official_demo_with_a_person_in_it_passes_on_its_own_slide(tmp_path):
    compare = candidate(tmp_path, "c04.png", "Quick Compare", title="PS Quick Compare")
    slot = slots()[3]
    assert image_pick.is_demo(compare, slot)
    assert image_pick.decide(WITH_PERSON, demo=True)[0] is True
    choices, _ = image_pick.pick_for_slots([slot], [compare], tmp_path, "t", "Photoshop",
                                           lambda path, s, text, name: WITH_PERSON)
    assert choices["04"] is compare


def test_a_person_still_blocks_anything_that_is_not_an_official_demo_of_the_slide(tmp_path):
    assert image_pick.decide(WITH_PERSON)[0] is False
    page_image = candidate(tmp_path, "c05.png", "Quick Compare", kind="image")
    assert not image_pick.is_demo(page_image, slots()[3])
    relight = candidate(tmp_path, "c06.png", "Relight")
    assert not image_pick.is_demo(relight, slots()[3])  # another feature's poster is not this slide's demo
    cover = image_pick.Slot("01", 1, "cover", "cover")
    assert not image_pick.is_demo(relight, cover)


def test_a_demo_that_fails_another_check_is_still_rejected():
    assert image_pick.decide(dict(WITH_PERSON, has_watermark=True), demo=True)[0] is False
    assert image_pick.decide(dict(WITH_PERSON, shows_slide_subject=False), demo=True)[0] is False


def test_the_checker_is_told_when_the_image_is_an_official_demo_poster():
    slot = image_pick.Slot("04", 4, "Slide about: QUICK COMPARE", "feature", "QUICK COMPARE", demo="PS Quick Compare")
    prompt = image_pick.verifier_prompt(Path("c04.jpg"), slot, "official", "Photoshop")
    assert "official demo video" in prompt and "PS Quick Compare" in prompt
    plain = image_pick.verifier_prompt(Path("c04.jpg"), image_pick.Slot("04", 4, "x", "feature", "X"), "o", "Photoshop")
    assert "official demo video" not in plain


def test_page_images_are_tagged_with_a_feature_only_when_the_whole_name_is_in_the_alt_text():
    tagged = images.tag_image({"src": "https://a/x/img.jpg", "alt": "Remove Tool in Photoshop removing a shadow"},
                              FEATURES)
    assert tagged == "Remove Tool"
    assert images.tag_image({"src": "https://a/x/hero.jpg", "alt": "Remove the clutter"}, FEATURES) == ""
    assert images.tag_image({"src": "https://a/x/quick-compare.jpg", "alt": ""}, FEATURES) == "Quick Compare"


# ---- the text-led layout has no empty image box ----

def test_the_text_led_layout_has_no_image_box_and_keeps_the_hierarchy():
    page = carousel_render.slide_document(feature_view(), {"main": None, "old": None}, None)
    assert "<img" not in page and 'class="hero' not in page and "dashed" not in page
    assert 'class="glow"' in page  # the brand glow treatment
    assert ACCENT in page and "It detects footprints" in page and "REMOVE" in page
    assert page.index("REMOVE") < page.index(ACCENT) < page.index("It detects")  # headline, cyan line, body


def test_the_text_led_block_is_centred_in_the_free_area():
    html_doc = carousel_render.text_led_body(feature_view())
    top = int(re.search(r'class="abs display headline"[^>]*style="top:(\d+)px', html_doc).group(1))
    assert 204 < top < 800  # not stuck under the pill, not pushed down to the footer


def test_a_feature_slide_with_an_image_uses_the_image_layout():
    page = carousel_render.slide_document(feature_view(), {"main": Path("x.png"), "old": None}, None)
    assert "<img" in page


# ---- screenshots are never cropped ----

def test_screenshots_are_shown_whole_with_contain_never_cover(tmp_path):
    assert "object-fit:cover" not in carousel_render.CSS
    assert "object-fit:contain" in carousel_render.CSS
    page = carousel_render.slide_document(feature_view(), {"main": wide_image(tmp_path), "old": None}, None)
    assert 'class="hero screen"' in page
    assert "scale(" not in page and "object-position" not in page and "transform" not in page.split("</style>")[1]


def test_the_crop_machinery_is_gone():
    assert not hasattr(carousel_render, "crop_for") and not hasattr(carousel_render, "CROPS")
    slots_, _ = carousel_render.slot_images(Path("."), [{"type": "cover"}])
    assert "main_crop" not in slots_[0]


def test_the_screenshot_has_a_thin_border_and_glow_not_a_grey_bezel():
    css = carousel_render.CSS
    rule = css[css.index(".hero.screen{"):css.index("}", css.index(".hero.screen{"))]
    assert "border:1px solid rgba(127,220,255" in rule and "box-shadow" in rule and "#aaa" not in rule


# ---- one image box for every feature slide ----

def _screen_style(page: str) -> str:
    return re.search(r'class="hero screen" style="([^"]+)"', page).group(1)


def test_every_feature_slide_uses_the_same_image_box(tmp_path):
    image = wide_image(tmp_path)
    views = [
        feature_view("left_body", "RELIGHT"),
        feature_view("left_body", "GENERATIVE RESTYLE"),
        feature_view("stat_hero", "40 FPS"),
        feature_view("stat_specs", "40 FPS", specs=[spec("40 FPS", "burst"), spec("4K", "video"), spec("7.5", "stops")]),
    ]
    boxes = set()
    for view in views:
        page = carousel_render.slide_document(view, {"main": image, "old": None}, None)
        left, top, width, height = re.search(
            r"left:(\d+)px;top:(\d+)px;width:(\d+)px;height:(\d+)px", _screen_style(page)).groups()
        assert (int(left), int(top), int(width)) == carousel_render.FEATURE_BOX[:3]
        assert abs(int(height) - carousel_render.FEATURE_BOX[3]) <= 1
        boxes.add((left, top, width))
    assert len(boxes) == 1


def test_the_image_box_is_16_by_9_at_full_content_width_and_clear_of_the_footer():
    left, top, width, height = carousel_render.FEATURE_BOX
    assert left == 64 and left + width == 1080 - 64
    assert abs(width / height - 16 / 9) < 0.01
    assert top + height < carousel_render.FOOTER_TOP


def test_text_above_the_image_box_never_reaches_it(tmp_path):
    long_body = "x" * 140
    for headline in ("RELIGHT", "GENERATIVE RESTYLE"):
        html_doc = carousel_render.left_body_body(feature_view(headline=headline, body=long_body),
                                                  {"main": wide_image(tmp_path)})
        body_top = int(re.search(r'class="abs body"[^>]*style="top:(\d+)px;[^"]*height:(\d+)px', html_doc).group(1))
        body_h = int(re.search(r'class="abs body"[^>]*style="top:\d+px;[^"]*height:(\d+)px', html_doc).group(1))
        assert body_top + body_h <= carousel_render.FEATURE_BOX[1]


# ---- every feature slide has a cyan line, on one line ----

def test_every_feature_template_shows_the_cyan_line_with_a_one_line_limit(tmp_path):
    image = wide_image(tmp_path)
    views = [
        feature_view("left_body"),
        feature_view("stat_hero", "40 FPS"),
        feature_view("stat_specs", "40 FPS", specs=[spec("40 FPS", "burst"), spec("4K", "video"), spec("7.5", "stops")]),
    ]
    for view in views:
        for main in (image, None):
            page = carousel_render.slide_document(view, {"main": main, "old": None}, None)
            div = re.search(r'<div class="abs [^"]*accent[^"]*"[^>]*>' + re.escape(ACCENT), page)
            assert div, (view["template"], main)
            assert 'data-max-lines="1"' in div.group(0)


def test_a_feature_slide_without_a_cyan_line_is_flagged():
    views = [FIXTURE_COVER] + [feature_view(accent=None)] * 3
    findings = design_check.check_slides(views)
    assert any(f["rule"] == "cyan line" for f in findings)


FIXTURE_COVER = {"type": "cover", "label": "ADOBE MAX 2026", "headline": "PHOTOSHOP", "subline": None,
                 "features": [], "product": "PHOTOSHOP", "footer": "SWIPE"}


def test_the_cyan_line_and_headlines_fit_in_the_browser(tmp_path):
    pytest.importorskip("playwright.sync_api")
    image = wide_image(tmp_path)
    docs, names = [], []
    for main in (image, None):
        for headline in ("RELIGHT", "REMOVE TOOL", "GENERATIVE RESTYLE"):
            docs.append(carousel_render.slide_document(feature_view(headline=headline), {"main": main, "old": None}, None))
            names.append(f"{headline}-{main is not None}")
    outs = [tmp_path / f"{i}.png" for i in range(len(docs))]
    measure: list = []
    problems = carousel_render.render_pngs(docs, outs, tmp_path / "work", measure_log=measure)
    assert problems == []
    for name, slide in zip(names, measure):
        accent = next(b for b in slide["boxes"] if b["text"] == ACCENT)
        assert accent["lines"] == 1, name


# ---- the cover: hook, two feature lines, a whole hero frame ----

def cover_view(hook="ADD NEW LIGHT SOURCES TO A PHOTO", features=None, headline="PHOTOSHOP"):
    return {"type": "cover", "label": "ADOBE MAX 2026", "headline": headline, "subline": hook,
            "features": features if features is not None else ["RELIGHT", "GENERATIVE RESTYLE", "REMOVE TOOL",
                                                               "QUICK COMPARE"], "product": "PHOTOSHOP",
            "footer": "SWIPE"}


def test_the_cover_shows_the_hook_and_at_most_two_feature_lines(tmp_path):
    html_doc = carousel_render.cover_body(cover_view(), {"main": wide_image(tmp_path, "01.png"), "old": None})
    assert 'class="abs hook"' in html_doc and "ADD NEW LIGHT SOURCES TO A PHOTO" in html_doc
    assert html_doc.count('class="abs feat"') == 2
    assert len(carousel_render.feature_lines(["A", "B", "C", "D", "E"])) == 2


def test_the_cover_hero_is_a_whole_full_width_frame_when_the_text_leaves_room(tmp_path):
    html_doc = carousel_render.cover_body(cover_view(), {"main": wide_image(tmp_path, "01.png")})
    style = _screen_style(html_doc)
    left, top, width, height = (int(v) for v in re.search(
        r"left:(\d+)px;top:(\d+)px;width:(\d+)px;height:(\d+)px", style).groups())
    assert (left, width) == (64, 952)  # full content width, margins 64
    assert top >= 740 and top + height <= carousel_render.HERO_BOTTOM + 1
    assert "object-position" not in html_doc and "scale(" not in html_doc


def test_a_long_cover_text_block_shrinks_the_hero_instead_of_overlapping_it(tmp_path):
    html_doc = carousel_render.cover_body(cover_view(headline="PHOTOSHOP\nFOR EVERYONE"),
                                          {"main": wide_image(tmp_path, "01.png")})
    left, top, width, height = (int(v) for v in re.search(
        r"left:(\d+)px;top:(\d+)px;width:(\d+)px;height:(\d+)px", _screen_style(html_doc)).groups())
    assert width < 952 and left + width / 2 == pytest.approx(540, abs=1)  # smaller, still centred
    assert abs(width / height - 16 / 9) < 0.02


def test_the_confirmed_cover_hook_reaches_the_cover_view():
    plan = carousel_plan.load_plan(copy.deepcopy(FIXTURE["plan"]))
    carousel_plan.verify(plan, FIXTURE["official_text"])
    cover = carousel_plan.build_views(plan)[0]
    assert cover["subline"] == FIXTURE["plan"]["cover"]["subline"]["text"] and cover["features"]


def test_a_cover_fallback_keeps_the_drafted_hook():
    data = copy.deepcopy(FIXTURE["plan"])
    fallback = {"headline": {"text": "PHOTOSHOP", "quote": "Photoshop"}, "subline": None}
    kept = carousel_plan.with_fallback_cover(data, fallback, replace_product=False)
    assert kept["cover"]["subline"]["text"] == FIXTURE["plan"]["cover"]["subline"]["text"]


def test_the_draft_prompt_asks_for_a_hook_and_a_one_line_supported_cyan_line():
    prompt = carousel_plan.draft_prompt("t", "u", "text", ["Photoshop"])
    assert "cover HOOK" in prompt and "ADD LIGHT AFTER THE SHOT" not in prompt
    assert "ONE line" in prompt and "ADD NEW LIGHT SOURCES" in prompt
    assert "excited to check this out" in prompt  # only as the opener to avoid
    assert "code adds" not in prompt.split("Captions, in this order")[1]
