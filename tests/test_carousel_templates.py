"""Round 1 fixes: templates, copy rules, spec icons, quick take, and a visual check of every template.

The text tests need nothing installed. The visual test renders with Playwright and Chromium, and is
skipped only when Playwright itself is not installed.
"""
import copy
import json
import struct
from pathlib import Path

import pytest
from conftest import ROOT

import carousel_plan
import carousel_render
from carousel_plan import PlanError
from carousel_text import lint_texts

FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
# Extra official sentences used only by the template tests, so every test fact has a real quote.
EXTRA_TEXT = (
    " Photoshop 2026 had no relight tool."
    " Photoshop 2027 is available in Creative Cloud."
)


def fresh():
    return copy.deepcopy(FIXTURE["plan"])


def text_with_extras():
    return FIXTURE["official_text"] + EXTRA_TEXT


def fact(text, quote):
    return {"text": text, "quote": quote}


# ---- copy rules ----

def test_headline_is_capped_at_45_characters():
    data = fresh()
    data["slides"][0]["headline"]["text"] = "X" * 46
    with pytest.raises(PlanError, match="headline is longer"):
        carousel_plan.load_plan(data)


def test_body_must_be_one_short_sentence():
    data = fresh()
    data["slides"][0]["body"]["text"] = "New tools relight an image. They also add more."
    with pytest.raises(PlanError, match="one sentence"):
        carousel_plan.load_plan(data)


def test_body_must_not_repeat_the_product_name():
    data = fresh()
    data["slides"][0]["body"]["text"] = "Photoshop 2027 relights an image."
    with pytest.raises(PlanError, match="do not repeat the product name"):
        carousel_plan.load_plan(data)


def test_captions_need_two_or_three_concrete_facts():
    data = fresh()
    data["captions"]["david"]["facts"] = data["captions"]["david"]["facts"][:1]
    with pytest.raises(PlanError, match="2 to 3 concrete facts"):
        carousel_plan.load_plan(data)


def test_template_must_be_known():
    data = fresh()
    data["slides"][0]["template"] = "carousel_of_doom"
    with pytest.raises(PlanError, match="template must be one of"):
        carousel_plan.load_plan(data)


def test_spec_icon_must_be_a_drawn_icon():
    data = fresh()
    data["slides"][1]["specs"] = [{"value": fact("NEW TOOLS", "new tools to relight an image"),
                                   "caption": fact("relight", "relight an image"), "icon": "clipart"}]
    with pytest.raises(PlanError, match="icon must be one of"):
        carousel_plan.load_plan(data)


# ---- template choice ----

def test_specs_choose_the_stat_specs_template():
    assert carousel_plan.resolve_template({"template": None, "body": None}, [{"value": 1}]) == "stat_specs"


def test_stat_specs_without_specs_falls_back_to_stat_hero():
    assert carousel_plan.resolve_template({"template": "stat_specs", "body": None}, []) == "stat_hero"


def test_body_without_template_chooses_left_body():
    assert carousel_plan.resolve_template({"template": None, "body": {"text": "x"}}, []) == "left_body"


# ---- quick take and the question ----

def test_question_in_quick_take_is_an_opinion_and_needs_no_quote():
    plan = carousel_plan.load_plan(_price_plan())
    report = carousel_plan.verify(plan, text_with_extras())
    question = next(r for r in report if r["id"] == "price.question")
    assert question["verdict"] == "NOT A FACT"


def test_quick_take_sentence_is_a_fact_that_must_be_quoted():
    data = _price_plan()
    data["price"]["quick_take"]["sentence"]["quote"] = "words the official page never wrote down"
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, text_with_extras())
    views = carousel_plan.build_views(plan)
    assert views[-1]["quick_take"] is None


def test_availability_only_slide_uses_the_price_template():
    data = _price_plan()
    data["price"]["prices"] = [{"value": fact("AVAILABLE NOW", "Photoshop 2027 is available in Creative Cloud"),
                                "caption": fact("IN CREATIVE CLOUD", "Creative Cloud")}]
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, text_with_extras())
    views = carousel_plan.build_views(plan)
    assert views[-1]["type"] == "price" and views[-1]["prices"][0]["value"] == "AVAILABLE NOW"


def test_quick_take_text_passes_the_lint():
    plan = carousel_plan.load_plan(_price_plan())
    carousel_plan.verify(plan, text_with_extras())
    views = carousel_plan.build_views(plan)
    assert lint_texts(carousel_plan.slide_texts(views)) == []


def _price_plan():
    data = fresh()
    data["comparison"] = None
    data["price"] = {
        "label": "PRICE + AVAILABILITY",
        "prices": [{"value": fact("NEW TOOLS", "new tools to relight an image"),
                    "caption": fact("RELIGHT", "relight an image")}],
        "availability": fact("AVAILABLE IN CREATIVE CLOUD", "available in Creative Cloud"),
        "quick_take": {
            "sentence": fact("Photoshop 2027 brings new tools to relight an image.",
                             "brings new tools to relight an image"),
            "question": {"text": "Would you upgrade?", "quote": ""},
        },
    }
    return data


# ---- icons and spec columns ----

def test_spec_columns_draw_line_icons():
    assert "<svg" in carousel_render.icon_svg("sensor") and 'stroke="#39d3f5"' in carousel_render.icon_svg("sensor")
    assert set(carousel_plan.ICONS) == set(carousel_render.ICON_PATHS)


def test_stat_specs_slide_has_three_icon_columns():
    data = fresh()
    data["slides"][1]["template"] = "stat_specs"  # the fixture asks for stat_hero, and an explicit template wins
    data["slides"][1]["specs"] = [
        {"value": fact("NEW TOOLS", "new tools to relight an image"), "caption": fact("relight", "relight an image"), "icon": "sensor"},
        {"value": fact("NEW STYLE", "generate in a new style"), "caption": fact("generate", "generate in a new style"), "icon": "burst"},
        {"value": fact("BETA", "a long list of new beta features"), "caption": fact("beta", "a long list of new beta features"), "icon": "star"},
    ]
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, text_with_extras())
    views = carousel_plan.build_views(plan)
    html_doc = carousel_render.slide_document(views[2], {"main": None, "old": None}, None)
    assert html_doc.count('class="icon"') == 3 and "spec-value" in html_doc


# ---- no slide ever shows an empty box ----

def test_a_slide_with_no_image_draws_only_the_soft_glow_never_an_empty_box():
    plan = carousel_plan.load_plan(fresh())
    carousel_plan.verify(plan, FIXTURE["official_text"])
    views = carousel_plan.build_views(plan)
    html_doc = carousel_render.slide_document(views[1], {"main": None, "old": None}, None)
    assert 'class="glow"' in html_doc and "hero-ph" not in html_doc and "Add official product image" not in html_doc
    assert "dashed" not in html_doc and "<img" not in html_doc


def test_footer_names_the_product_with_lines_either_side():
    html_doc = carousel_render.footer("PHOTOSHOP 2027")
    assert html_doc.count('class="fline"') == 2 and "PHOTOSHOP 2027" in html_doc


def test_swipe_footer_on_the_cover():
    assert "SWIPE TO SEE WHAT&#x27;S NEW →" in carousel_render.footer(None, swipe=True)
    assert carousel_render.SWIPE_TEXT == carousel_plan.SWIPE_TEXT


def test_every_template_is_selectable():
    assert set(carousel_plan.TEMPLATES) == {"left_body", "stat_specs", "stat_hero"}
    assert {"cover", "comparison", "price"} <= set(carousel_render.BODY)


# ---- visual check: each template renders to 1080 x 1440 with a centred headline ----

def _png_size(path: Path) -> tuple[int, int]:
    with open(path, "rb") as handle:
        header = handle.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", header[16:24])


def _template_views():
    """One view per template, built from the fixture plus test-only facts that have real quotes."""
    views = {}
    plan = carousel_plan.load_plan(fresh())
    carousel_plan.verify(plan, text_with_extras())
    base = carousel_plan.build_views(plan)
    views["cover"] = base[0]
    views["left_body"] = base[1]
    views["stat_hero"] = base[2]

    data = fresh()
    data["slides"][1]["template"] = "stat_specs"
    data["slides"][1]["specs"] = [
        {"value": fact("NEW TOOLS", "new tools to relight an image"), "caption": fact("relight", "relight an image"), "icon": "sensor"},
        {"value": fact("NEW STYLE", "generate in a new style"), "caption": fact("generate", "generate in a new style"), "icon": "burst"},
        {"value": fact("BETA", "a long list of new beta features"), "caption": fact("beta", "a long list of new beta features"), "icon": "star"},
    ]
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, text_with_extras())
    views["stat_specs"] = carousel_plan.build_views(plan)[2]

    data = fresh()
    data["comparison"] = {
        "label": "SIDE-BY-SIDE COMPARISON",
        "title": fact("PHOTOSHOP 2027 vs PHOTOSHOP 2026", "Photoshop 2027 brings new tools"),
        "rows": [{"name": "RELIGHT", "new": fact("YES", "new tools to relight an image"),
                  "old": fact("NO", "Photoshop 2026 had no relight tool.")}],
    }
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, text_with_extras())
    views["comparison"] = next(v for v in carousel_plan.build_views(plan) if v["type"] == "comparison")

    plan = carousel_plan.load_plan(_price_plan())
    carousel_plan.verify(plan, text_with_extras())
    views["price"] = carousel_plan.build_views(plan)[-1]
    return views


CENTRED = ("cover", "stat_specs", "stat_hero", "comparison")
REAL_FONTS = ROOT / "assets" / "fonts"  # the same fonts the real build uses, when they have been fetched


def _render_all(tmp_path):
    views = _template_views()
    names = list(views)
    font_dir = REAL_FONTS if REAL_FONTS.exists() else None
    documents = [carousel_render.slide_document(views[n], {"main": None, "old": None}, font_dir) for n in names]
    out_paths = [tmp_path / f"{n}.png" for n in names]
    measure_log: list = []
    problems = carousel_render.render_pngs(documents, out_paths, tmp_path / "work", measure_log=measure_log)
    return names, out_paths, problems, measure_log


def test_visual_templates_render_at_1080_by_1440(tmp_path):
    pytest.importorskip("playwright.sync_api")
    names, out_paths, problems, _ = _render_all(tmp_path)
    assert problems == []
    for name, path in zip(names, out_paths):
        assert _png_size(path) == (1080, 1440), name


def test_visual_headlines_are_centred(tmp_path):
    pytest.importorskip("playwright.sync_api")
    names, _, _, measure_log = _render_all(tmp_path)
    for name, slide in zip(names, measure_log):
        if name not in CENTRED:
            continue
        headline = next((b for b in slide["boxes"] if b["name"] == "headline"), None)
        assert headline is not None, f"{name} has no headline"
        centre = (headline["left"] + headline["right"]) / 2
        assert abs(centre - 540) <= 20, f"{name} headline centre is {centre:.0f}px, not 540"
