"""Phase 3 round 3 fixes: official names in the draft prompt, the safe cover fallback, and one product's
section of a round-up page as the only fact source. No network, no Claude, no browser."""
import copy

import pytest

import carousel
import carousel_plan
import carousel_render
import official
from dedupe import Story

TEXT = (
    "Read on to learn more about what’s new across Creative Cloud at Adobe MAX 2026. "
    "Photoshop is introducing new ways to explore, edit and refine your images. "
    "Relight adds new light sources that blend into the scene. "
    "Generative Restyle lets you refine the intensity with a custom slider. "
    "Quick Compare compares before and after with an on-canvas split screen slider."
)


def fact(text, quote):
    return {"text": text, "quote": quote}


def make_plan(headline="PHOTOSHOP 2027", headline_quote="Photoshop is introducing new ways to explore"):
    relight = "Relight adds new light sources that blend into the scene"
    restyle = "Generative Restyle lets you refine the intensity with a custom slider"
    compare = "Quick Compare compares before and after with an on-canvas split screen slider"
    caption = {"hook": fact("Relight a photo after you take it.", relight),
               "facts": [fact("Restyle has a custom slider.", restyle), fact("Compare before and after.", compare)],
               "closing": fact("Which would you use first?", "")}
    return {
        "product": fact("PHOTOSHOP 2027", "Photoshop is introducing new ways to explore"),
        "cover": {"label": "NEW IN PHOTOSHOP", "headline": fact(headline, headline_quote),
                  "subline": fact("NEW AT ADOBE MAX 2026", "what’s new across Creative Cloud at Adobe MAX 2026")},
        "slides": [
            {"template": "left_body", "label": "NEW TOOL", "headline": fact("RELIGHT", relight)},
            {"template": "left_body", "label": "NEW TOOL", "headline": fact("GENERATIVE RESTYLE", restyle)},
            {"template": "left_body", "label": "NEW TOOL", "headline": fact("QUICK COMPARE", compare)},
        ],
        "comparison": None, "price": None,
        "captions": {"david": copy.deepcopy(caption), "tpm": copy.deepcopy(caption)},
    }


def claimed_confirmed(plan_data):
    """What a lenient fact-check call says: every fact CONFIRMED with the draft's own quote."""
    plan = carousel_plan.load_plan(plan_data)
    return {f["id"]: {"verdict": "CONFIRMED", "quote": f["quote"]} for f in carousel_plan.iter_facts(plan)}


def confirming_recheck(seen):
    def recheck(plan, ids):
        seen.append(set(ids))
        return {f["id"]: {"verdict": "CONFIRMED", "quote": f["quote"]}
                for f in carousel_plan.iter_facts(plan) if f["id"] in ids}
    return recheck


def refusing_recheck(plan, ids):
    return {i: {"verdict": "NOT CONFIRMED", "quote": ""} for i in ids}


# ---- 1. the draft prompt gets the official naming ----

def test_official_names_are_read_from_the_page_not_the_title():
    names = carousel_plan.official_names(TEXT, ["photoshop"])
    assert names == ["Photoshop"]
    assert "Photoshop 2027" not in names


def test_an_old_version_mentioned_once_is_not_the_official_name():
    text = "Photoshop is new. Photoshop adds tools. Photoshop is fast. Photoshop 2026 had fewer tools."
    assert carousel_plan.official_names(text, ["photoshop"]) == ["Photoshop"]


def test_a_version_the_page_really_uses_is_the_official_name():
    text = "Photoshop 27.1 adds tools. Photoshop 27.1 is fast. Photoshop 27.1 ships today."
    assert carousel_plan.official_names(text, ["photoshop"]) == ["Photoshop 27.1"]


def test_draft_prompt_carries_the_official_names_and_makes_the_title_context_only():
    prompt = carousel_plan.draft_prompt("Photoshop 2027 gets Relight", "https://blog.adobe.com/x", TEXT, ["Photoshop"])
    assert 'The official page writes the product as: "Photoshop"' in prompt
    assert "ONLY names, numbers and feature names that appear in the official text" in prompt
    assert "context only" in prompt and "take no names or numbers from it" in prompt
    assert "__NAMES__" not in prompt


def test_draft_prompt_without_a_clear_name_says_so():
    prompt = carousel_plan.draft_prompt("Story", "https://x", "text")
    assert "no clear product name" in prompt


def test_draft_with_claude_sends_the_names(monkeypatch):
    seen = {}

    def ask(prompt, model, timeout=300):
        seen["prompt"] = prompt
        return "{}"

    monkeypatch.setattr(carousel.classify, "ask_claude", ask)
    carousel.draft_with_claude("Photoshop 2027 gets Relight", "https://x", TEXT, "sonnet", ["Photoshop"])
    assert 'writes the product as: "Photoshop"' in seen["prompt"]


# ---- 2. the cover fallback ----

def test_a_cover_the_page_does_not_confirm_falls_back_to_the_product_name_and_event():
    data = make_plan()
    verdicts = claimed_confirmed(data)  # even a lenient fact-check cannot save "PHOTOSHOP 2027": code checks the name
    seen: list = []
    new_data, merged, notes = carousel.settle_cover(
        data, TEXT, verdicts, ["Photoshop"], confirming_recheck(seen))
    assert new_data["cover"]["headline"]["text"] == "PHOTOSHOP"
    assert new_data["cover"]["subline"]["text"] == "NEW AT ADOBE MAX 2026"
    assert new_data["product"]["text"] == "PHOTOSHOP"  # the drafted product name failed too
    assert seen == [{"cover.headline", "cover.subline", "product"}]  # only the cover is re-checked
    assert any("fallback" in n for n in notes)
    plan = carousel_plan.load_plan(new_data)
    carousel_plan.verify(plan, TEXT, merged)
    cover = carousel_plan.build_views(plan)[0]
    # Changed in fix round 3b: the drafted hook (the plan's subline) stays on the cover, with the feature names
    # as light-blue lines under it.
    assert cover["headline"] == "PHOTOSHOP" and cover["subline"] == "NEW AT ADOBE MAX 2026" and cover["features"]


def test_the_fallback_headline_quote_is_real_page_text():
    fallback = carousel_plan.cover_fallback(TEXT, ["Photoshop"])
    assert fallback["headline"]["text"] == "PHOTOSHOP"
    from carousel_text import quote_found
    assert quote_found(fallback["headline"]["quote"], TEXT)
    assert quote_found(fallback["subline"]["quote"], TEXT)


def test_the_fallback_has_no_event_line_when_the_page_names_no_event():
    text = "Photoshop is introducing new ways to explore, edit and refine your images today."
    fallback = carousel_plan.cover_fallback(text, ["Photoshop"])
    assert fallback["subline"] is None


def test_a_confirmed_cover_is_left_alone():
    data = make_plan(headline="RELIGHT", headline_quote="Relight adds new light sources that blend")
    data["product"]["text"] = "PHOTOSHOP"
    seen: list = []
    new_data, _, notes = carousel.settle_cover(
        data, TEXT, claimed_confirmed(data), ["Photoshop"], confirming_recheck(seen))
    assert new_data is data and notes == [] and seen == []


def test_the_build_stops_only_when_the_fallback_fails_too():
    data = make_plan()
    with pytest.raises(carousel_plan.PlanError) as info:
        carousel.settle_cover(data, TEXT, claimed_confirmed(data), ["Photoshop"], refusing_recheck)
    assert "fallback" in str(info.value) and "'PHOTOSHOP'" in str(info.value) and "no cover" in str(info.value)


def test_no_fallback_without_a_product_name_on_the_page():
    data = make_plan()
    with pytest.raises(carousel_plan.PlanError, match="no product name"):
        carousel.settle_cover(data, TEXT, claimed_confirmed(data), [], confirming_recheck([]))


def test_factcheck_can_be_limited_to_some_facts(monkeypatch):
    seen = {}

    def ask(prompt, model, timeout=300):
        seen["prompt"] = prompt
        return "[]"

    monkeypatch.setattr(carousel.classify, "ask_claude", ask)
    plan = carousel_plan.load_plan(make_plan())
    verdicts = carousel.factcheck_with_claude(plan, TEXT, "sonnet", {"cover.headline"})
    assert list(verdicts) == ["cover.headline"]
    assert '"cover.headline"' in seen["prompt"] and '"slide1.headline"' not in seen["prompt"]


# ---- 3. only the product's section of a round-up page ----

PAD = "It brings more control and precision to the way you work every day. " * 6
ROUNDUP = (
    "<html><body><nav>Menu Photoshop Lightroom</nav>"
    "<h1>Explore new ways to create across Creative Cloud</h1>"
    f"<p>Intro for every app. {PAD}</p>"
    "<h2>Photoshop enables greater precision</h2>"
    f"<p>Relight adds new light sources to a photo. {PAD}</p>"
    "<h3>Quick Compare</h3>"
    f"<p>Compare before and after with a slider. {PAD}</p>"
    "<h2>Premiere streamlines workflows</h2>"
    f"<p>Color Mode is a new grading experience. {PAD}</p>"
    "<h2>Achieve your best shots with new Lightroom capabilities</h2>"
    f"<p>Glow adds soft cinematic light. {PAD}</p>"
    "<h2>Deeper integration to take on the busy work</h2>"
    f"<p>MCP integrations call Photoshop and Premiere. {PAD}</p>"
    "</body></html>"
)
TITLE = "Adobe Photoshop 2027 adds Relight"


def test_story_product_terms_come_from_the_title():
    mine, others = carousel.story_product_terms(TITLE)
    assert mine == ["photoshop"] and "lightroom" in others and "photoshop" not in others


def test_page_is_split_at_its_headings():
    sections = official.page_sections(ROUNDUP)
    assert [s["heading"] for s in sections if s["level"] == 2][:2] == [
        "Photoshop enables greater precision", "Premiere streamlines workflows"]
    assert "Menu" not in official.page_text(ROUNDUP)  # nav is still skipped


def test_only_the_product_section_is_kept_with_its_subsections():
    mine, others = carousel.story_product_terms(TITLE)
    text, note = official.product_text(ROUNDUP, mine, others)
    assert "Relight adds new light sources" in text and "Quick Compare" in text  # the h3 under the h2
    for other in ("Color Mode", "Glow adds", "MCP integrations", "Intro for every app"):
        assert other not in text
    assert "only the sections about photoshop" in note


def test_a_title_that_names_the_product_over_a_round_up_does_not_pull_in_every_product():
    markup = ROUNDUP.replace("Explore new ways to create across Creative Cloud",
                             "Photoshop, Premiere and Lightroom: new tools")
    mine, others = carousel.story_product_terms(TITLE)
    text, _ = official.product_text(markup, mine, others)
    assert "Relight adds" in text and "Color Mode" not in text and "Glow adds" not in text


def test_a_single_product_page_is_used_whole():
    markup = ("<html><body><h1>Photoshop 2027 is here</h1>" f"<p>Relight is new. {PAD}</p>"
              f"<h2>Relight</h2><p>Light sources. {PAD}</p></body></html>")
    text, note = official.product_text(markup, ["photoshop"], ["lightroom"])
    assert text == official.page_text(markup) and note == ""


def test_a_page_with_no_heading_naming_the_product_is_used_whole_and_says_so():
    markup = f"<html><body><h2>Everything new</h2><p>Photoshop gets Relight. {PAD}</p></body></html>"
    text, note = official.product_text(markup, ["photoshop"], ["lightroom"])
    assert text == official.page_text(markup) and "whole page" in note


def test_without_product_terms_the_whole_page_is_used():
    text, note = official.product_text(ROUNDUP, [], [])
    assert text == official.page_text(ROUNDUP) and note == ""


def test_the_located_page_hands_over_only_the_product_section(monkeypatch):
    story = Story(title=TITLE, brand="Adobe", kind="product", tokens=frozenset())
    story.sources = []
    monkeypatch.setattr(carousel.official, "fetch_html", lambda url, *a, **k: ROUNDUP)
    config = {"official_domains": {"Adobe": ["adobe.com"]}}
    page = carousel.locate_official(story, "Adobe", config, "https://blog.adobe.com/en/publish/2026/11/10/max")
    assert "Relight adds" in page.text and "Color Mode" not in page.text and "Glow adds" not in page.text
    assert page.terms == ["photoshop"] and "only the sections" in page.note
    assert "Color Mode" in official.page_text(page.markup)  # the full page is still there for the image search


def test_the_drafter_and_the_fact_checker_never_see_the_other_products(monkeypatch):
    story = Story(title=TITLE, brand="Adobe", kind="product", tokens=frozenset())
    story.sources = []
    monkeypatch.setattr(carousel.official, "fetch_html", lambda url, *a, **k: ROUNDUP)
    page = carousel.locate_official(story, "Adobe", {"official_domains": {"Adobe": ["adobe.com"]}},
                                    "https://blog.adobe.com/en/publish/2026/11/10/max")
    prompts = []

    def ask(prompt, model, timeout=300):
        prompts.append(prompt)
        return "[]" if len(prompts) == 2 else "{}"

    monkeypatch.setattr(carousel.classify, "ask_claude", ask)
    carousel.draft_with_claude(TITLE, page.url, page.text, "sonnet", carousel_plan.official_names(page.text, page.terms))
    carousel.factcheck_with_claude(carousel_plan.load_plan(make_plan()), page.text, "sonnet")
    assert len(prompts) == 2
    for prompt in prompts:
        assert "Relight adds new light sources" in prompt
        assert "Color Mode" not in prompt and "Glow adds" not in prompt and "MCP integrations" not in prompt


# ---- the comparison title ----

def test_comparison_title_has_a_two_line_form_and_a_minimum_size():
    html_doc = carousel_render.gold_headline("EOS R8 MARK II vs EOS R8", 40, 120, 92)
    assert f'data-min-size="{carousel_render.COMPARISON_MIN_SIZE}"' in html_doc
    assert "data-alt-html" in html_doc and "vs EOS" in html_doc and "&lt;br&gt;" in html_doc
    assert "if (!m.ok && altHtml && minSize)" in carousel_render.FIT_SCRIPT


def test_a_title_without_vs_has_no_two_line_form():
    assert "data-alt-html" not in carousel_render.gold_headline("EOS R8 MARK II", 40, 120, 92)
