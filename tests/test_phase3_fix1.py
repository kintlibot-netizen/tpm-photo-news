"""Phase 3 round 2 fixes: ink fitting inside the safe area, the Adobe MAX lookup, the product-name rule,
the explicit --official-url fallback, and the image check's command and failure messages.

No network, no Claude, no browser.
"""
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import ROOT

import carousel
import carousel_plan
import carousel_render
import classify
import dedupe
import image_pick
import official
import official_index
from dedupe import Story

PHOTOSHOP = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
STORY_DAY = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
MAX_TITLE = ("Explore new ways to create across Creative Cloud and Adobe Firefly while advancing craft, "
             "precision, choice and control")
MAX_PATH = ("/en/publish/2026/11/10/explore-new-ways-create-across-creative-cloud-adobe-firefly-while-advancing"
            "-craft-precision-choice-control")
MAX_BODY = (
    "Adobe MAX 2026. Photoshop gets Relight: new light sources, non-destructive edits, and control over "
    "position, colour and brightness. Relight works on any photo in Photoshop. "
    "Generative Restyle lets you prompt to edit, convert to a layer and set a custom intensity slider. "
    "Photoshop users can try Relight today. " * 3
)
DECOY_BODY = "Photoshop tips for a quick start. Photoshop has many menus. " * 10


def serial(date: datetime) -> int:
    return (date.replace(tzinfo=None) - datetime(1899, 12, 30)).days


INDEX = {"data": [
    {"path": MAX_PATH, "title": MAX_TITLE, "date": serial(datetime(2026, 11, 10)),
     "description": "New Photoshop and Firefly features for creators.",
     "tags": [{"title": "Photoshop"}, {"title": "Firefly"}]},
    {"path": "/en/topics/photoshop-tips", "title": "Photoshop tips for this week",
     "date": serial(datetime(2026, 11, 9)), "description": "A quick start.", "tags": ["Photoshop"]},
    {"path": "/en/topics/creative-cloud-old", "title": "Creative Cloud news", "date": serial(datetime(2025, 1, 1)),
     "description": "Old news.", "tags": []},
]}


def fake_text(url):
    if url.endswith(MAX_PATH):
        return MAX_BODY
    return DECOY_BODY


# ---- ink fitting ----

def test_fit_script_checks_every_line_against_the_safe_area():
    script = carousel_render.FIT_SCRIPT
    assert "clusterLines" in script and "data-safe-left" in script and "data-safe-right" in script
    assert "const SAFE_L = 64, SAFE_R = 1016" in script
    assert "size -= 1" in script  # shrinks in small steps


def test_price_columns_get_half_the_safe_area_each():
    plan = carousel_plan.load_plan(copy.deepcopy(PHOTOSHOP["plan"]))
    carousel_plan.verify(plan, PHOTOSHOP["official_text"])
    view = {"type": "price", "label": "PRICE", "prices": [{"value": "$1,899", "caption": "BODY ONLY"},
                                                          {"value": "$2,099", "caption": "WITH RF"}],
            "availability": "EXPECTED LATE OCTOBER", "quick_take": None, "cta": "SHARE", "product": None}
    html_doc = carousel_render.price_body(view, {"main": None, "old": None})
    assert 'data-safe-left="64" data-safe-right="520"' in html_doc
    assert 'data-safe-left="560" data-safe-right="1016"' in html_doc


def test_the_cover_keeps_a_space_between_the_words():
    html_doc = carousel_render.headline_html("PHOTOSHOP 2027")
    visible = re.sub(r"<[^>]+>", "", html_doc).replace(" ", " ")
    assert visible == "PHOTOSHOP 2027"
    assert "PHOTOSHOP <br>" in html_doc


def test_model_name_stays_on_one_line_on_the_cover():
    html_doc = carousel_render.headline_html("CANON EOS R8 MARK II")
    assert "R8 MARK II" in html_doc


# ---- the product name must be the official one ----

def test_product_name_not_on_the_official_page_is_not_confirmed():
    data = copy.deepcopy(PHOTOSHOP["plan"])
    data["product"]["text"] = "PHOTOSHOP 2027 PRO"
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, PHOTOSHOP["official_text"])
    assert plan["product"]["ok"] is False


def test_product_name_on_the_page_is_confirmed():
    plan = carousel_plan.load_plan(copy.deepcopy(PHOTOSHOP["plan"]))
    carousel_plan.verify(plan, PHOTOSHOP["official_text"])
    assert plan["product"]["ok"] is True and plan["cover"]["headline"]["ok"] is True


def test_draft_prompt_tells_claude_to_use_the_official_names():
    prompt = carousel_plan.draft_prompt("Story", "https://blog.adobe.com/x", "text")
    assert "Relight" in prompt and "Generative Restyle" in prompt
    assert 'Call it "Photoshop 2027" only if the official text says' in prompt


# ---- the Adobe MAX lookup ----

def test_the_max_post_is_found_from_its_body_not_its_title():
    posts = official_index.parse_index(INDEX, "https://blog.adobe.com")
    terms = ["photoshop"]
    features = official_index.feature_terms(PHOTOSHOP["title"], terms)
    assert "relight" in features and "photoshop" not in features
    pool = official_index.candidate_pool(posts, STORY_DAY, 14, terms)
    assert pool[0]["url"].endswith(MAX_PATH)  # newest, within 14 days, mentions Photoshop
    assert all(abs((p["date"] - STORY_DAY).days) <= 14 for p in pool)
    best = official_index.best_by_body(pool, fake_text, terms, features)
    assert best and best["url"].endswith(MAX_PATH)
    assert best["product_hits"] >= 2 and best["feature_hits"] >= 2


def test_every_post_in_the_window_is_a_candidate_product_posts_first():
    unnamed = {"path": "/en/x/unnamed", "title": "Big launch round-up", "date": serial(datetime(2026, 11, 11)),
               "description": "Creative tools.", "tags": []}
    posts = official_index.parse_index({"data": INDEX["data"] + [unnamed]}, "https://blog.adobe.com")
    pool = official_index.candidate_pool(posts, STORY_DAY, 14, ["photoshop"])
    urls = [p["url"] for p in pool]
    assert any(u.endswith("/unnamed") for u in urls)  # a post that does not name the product is still read
    assert urls[-1].endswith("/unnamed")  # but ranks after the posts that do
    assert not any(u.endswith("creative-cloud-old") for u in urls)  # outside the window
    many = official_index.parse_index({"data": [
        {"path": f"/p{i}", "title": f"Post {i}", "date": serial(datetime(2026, 11, 10))} for i in range(30)]},
        "https://blog.adobe.com")
    assert len(official_index.candidate_pool(many, STORY_DAY, 14, ["photoshop"])) == 12


def test_a_post_without_the_features_is_not_picked():
    posts = official_index.parse_index({"data": [INDEX["data"][1]]}, "https://blog.adobe.com")
    pool = official_index.candidate_pool(posts, STORY_DAY, 14, ["photoshop"])
    assert official_index.best_by_body(pool, fake_text, ["photoshop"], ["relight"]) is None


def test_unreadable_candidate_posts_are_skipped_not_fatal():
    posts = official_index.parse_index(INDEX, "https://blog.adobe.com")
    pool = official_index.candidate_pool(posts, STORY_DAY, 14, ["photoshop"])

    def broken(url):
        raise RuntimeError("down")

    assert official_index.best_by_body(pool, broken, ["photoshop"], ["relight"]) is None


def test_locate_official_finds_the_max_page_for_the_photoshop_story(monkeypatch):
    story = Story(title=PHOTOSHOP["title"], brand="Adobe", kind="product", tokens=frozenset())
    story.first_seen = STORY_DAY
    story.sources = [{"url": "https://dcw.example/a", "link": "https://dcw.example/a", "source": "DCW",
                      "source_type": "news", "title": story.title, "summary": "", "published": None}]
    long_page = "<p>" + MAX_BODY + "</p>"
    pages = {"https://dcw.example/a": "<p>no links</p>",
             "https://blog.adobe.com" + MAX_PATH: long_page}

    def fetch_html(url, *a, **k):
        if url == "https://blog.adobe.com/en/query-index.json":
            raise AssertionError("the index is read as JSON, not as a page")
        return pages.get(url, "<p>" + DECOY_BODY * 20 + "</p>")

    monkeypatch.setattr(carousel.official, "fetch_html", fetch_html)
    monkeypatch.setattr(carousel.official_index, "fetch_index", lambda url: INDEX)
    config = {"official_domains": {"Adobe": ["adobe.com"]},
              "official_indexes": {"Adobe": {"url": "https://blog.adobe.com/en/query-index.json",
                                             "base": "https://blog.adobe.com", "window_days": 14}},
              "official_pages": {}}
    page = carousel.locate_official(story, "Adobe", config, None)
    assert page.url == "https://blog.adobe.com" + MAX_PATH
    assert "Relight" in page.text


def test_no_match_says_what_was_checked(monkeypatch):
    story = Story(title=PHOTOSHOP["title"], brand="Adobe", kind="product", tokens=frozenset())
    story.first_seen = STORY_DAY
    story.sources = []
    monkeypatch.setattr(carousel.official_index, "fetch_index", lambda url: {"data": []})
    config = {"official_domains": {"Adobe": ["adobe.com"]},
              "official_indexes": {"Adobe": {"url": "https://blog.adobe.com/en/query-index.json",
                                             "base": "https://blog.adobe.com", "window_days": 14}}}
    with pytest.raises(carousel.Refused) as info:
        carousel.locate_official(story, "Adobe", config, None)
    assert "query-index.json" in str(info.value) and "--official-url" in str(info.value)


# ---- --official-url as the fallback ----

def test_official_url_on_an_official_domain_is_used(monkeypatch):
    story = Story(title="Adobe Releases Photoshop 27.1", brand="Adobe", kind="product", tokens=frozenset())
    story.sources = []
    monkeypatch.setattr(carousel.official, "fetch_html", lambda url, *a, **k: "<p>" + "Adobe text. " * 40 + "</p>")
    config = {"official_domains": {"Adobe": ["adobe.com"]}}
    page = carousel.locate_official(story, "Adobe", config, "https://helpx.adobe.com/photoshop/whats-new.html")
    assert page.url == "https://helpx.adobe.com/photoshop/whats-new.html"


def test_official_url_on_another_site_is_refused():
    story = Story(title="Adobe Releases Photoshop 27.1", brand="Adobe", kind="product", tokens=frozenset())
    story.sources = []
    config = {"official_domains": {"Adobe": ["adobe.com"]}}
    with pytest.raises(carousel.Refused, match="not on the official domains"):
        carousel.locate_official(story, "Adobe", config, "https://digitalcameraworld.example/x")


# ---- the image check: command and failure messages ----

def test_claude_is_called_with_add_dir_and_read_only(monkeypatch, tmp_path):
    seen = {}

    class Done:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(command, **kwargs):
        seen["command"] = command
        return Done()

    monkeypatch.setattr(classify, "find_claude", lambda: "claude")
    monkeypatch.setattr(classify.subprocess, "run", fake_run)
    classify.ask_claude_read("prompt", "sonnet", tmp_path)
    command = seen["command"]
    assert "--allowedTools" in command and command[command.index("--allowedTools") + 1] == "Read"
    assert "--add-dir" in command and command[command.index("--add-dir") + 1] == str(tmp_path)
    assert "--tools" not in command


def test_a_failed_claude_call_says_the_image_check_could_not_run(monkeypatch, tmp_path):
    image = tmp_path / "c01.jpg"
    image.write_bytes(b"x")

    def broken(prompt, model, folder, timeout=240):
        raise RuntimeError("Claude Code exited with code 1: unknown option --tools")

    monkeypatch.setattr(carousel.classify, "ask_claude_read", broken)
    slot = image_pick.Slot("01", 1, "Cover: the product")
    verdict = carousel.verify_image(image, slot, "text", "PRODUCT", "sonnet")
    assert verdict["unreadable"] is True
    assert verdict["notes"].startswith("image check could not run")


def test_the_image_prompt_survives_a_slot_without_a_brief():
    prompt = image_pick.verifier_prompt(Path("c01.jpg"), SimpleNamespace(name="01"), "text", "PRODUCT")
    assert "PRODUCT" in prompt


def test_a_missing_image_file_says_the_check_could_not_run(tmp_path):
    verdict = carousel.verify_image(tmp_path / "gone.jpg", SimpleNamespace(name="01"), "t", "P", "sonnet")
    assert verdict["unreadable"] is True and "could not run" in verdict["notes"]
