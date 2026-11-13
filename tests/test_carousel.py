"""Carousel tests. No Claude, no network, no browser: fixtures and fake replies only."""
import copy
import json
from datetime import datetime, timezone

import pytest
from conftest import ROOT

import carousel
import carousel_plan
import carousel_render
import carousel_text
import dashboard
import official
from carousel_text import LintError, clean_output, lint_text, lint_texts, match_key, quote_found
from classify import OFFICIAL, RUMOR
from dedupe import Story, Store

FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def fresh_plan():
    return copy.deepcopy(FIXTURE["plan"])


def fresh_data():
    return copy.deepcopy(FIXTURE)


# ---- plan parsing ----

def test_fixture_plan_loads_into_three_feature_slides():
    plan = carousel_plan.load_plan(fresh_plan())
    assert len(plan["slides"]) == 3
    assert plan["cover"]["headline"]["text"] == "PHOTOSHOP 2027"


def test_plan_needs_three_to_five_feature_slides():
    data = fresh_plan()
    data["slides"] = data["slides"][:2]
    with pytest.raises(carousel_plan.PlanError, match="3 to 5"):
        carousel_plan.load_plan(data)
    data["slides"] = data["slides"] * 3
    with pytest.raises(carousel_plan.PlanError, match="3 to 5"):
        carousel_plan.load_plan(data)


def test_plan_needs_a_cover_headline():
    data = fresh_plan()
    data["cover"]["headline"] = None
    with pytest.raises(carousel_plan.PlanError, match="cover.headline is required"):
        carousel_plan.load_plan(data)


def test_fact_must_have_text():
    data = fresh_plan()
    data["slides"][0]["body"] = {"quote": "only a quote"}
    with pytest.raises(carousel_plan.PlanError, match="needs a text value"):
        carousel_plan.load_plan(data)


def test_labels_are_short_and_present():
    data = fresh_plan()
    data["slides"][0]["label"] = "X" * 61
    with pytest.raises(carousel_plan.PlanError, match="longer than 60"):
        carousel_plan.load_plan(data)


def test_captions_need_both_accounts_with_hook_and_closing():
    data = fresh_plan()
    del data["captions"]["tpm"]
    with pytest.raises(carousel_plan.PlanError, match="captions.tpm is missing"):
        carousel_plan.load_plan(data)


def test_reply_with_text_around_the_json_is_parsed():
    assert carousel_plan.parse_json_reply('Here you go: {"a": 1} thanks') == {"a": 1}


def test_reply_without_json_is_refused():
    with pytest.raises(carousel_plan.PlanError, match="no JSON"):
        carousel_plan.parse_json_reply("I cannot help with that.")


# ---- fact checking ----

def test_every_fixture_fact_is_confirmed_by_its_quote():
    plan = carousel_plan.load_plan(fresh_plan())
    report = carousel_plan.verify(plan, FIXTURE["official_text"])
    assert all(row["verdict"] in ("CONFIRMED", "NOT A FACT") for row in report)
    assert any(row["verdict"] == "CONFIRMED" for row in report)


def test_unconfirmed_body_is_removed_from_the_slide():
    data = fresh_plan()
    data["slides"][0]["body"]["quote"] = "This sentence is not in the official text at all."
    plan = carousel_plan.load_plan(data)
    report = carousel_plan.verify(plan, FIXTURE["official_text"])
    body_row = next(r for r in report if r["id"] == "slide1.body")
    assert body_row["verdict"] == "NOT CONFIRMED"
    views = carousel_plan.build_views(plan)
    assert views[1]["headline"] == "RELIGHT\nIMAGES"
    assert views[1]["body"] is None


def test_a_claim_the_model_rejects_is_removed_even_with_a_matching_quote():
    plan = carousel_plan.load_plan(fresh_plan())
    verdicts = {f["id"]: {"verdict": "CONFIRMED", "quote": "generate in a new style"} for f in carousel_plan.iter_facts(plan)}
    verdicts["slide2.headline"] = {"verdict": "NOT CONFIRMED", "quote": ""}
    carousel_plan.verify(plan, FIXTURE["official_text"], verdicts)
    views = carousel_plan.build_views(plan)
    assert all(v.get("headline") != "NEW STYLES" for v in views)
    assert len(views) == 3  # the slide with the removed headline is dropped whole


def test_a_model_quote_that_is_not_in_the_official_text_does_not_confirm():
    data = fresh_plan()
    data["cover"]["headline"]["quote"] = "a sentence the official page never said"
    plan = carousel_plan.load_plan(data)
    verdicts = {f["id"]: {"verdict": "CONFIRMED", "quote": "another sentence the page never said"}
                for f in carousel_plan.iter_facts(plan)}
    report = carousel_plan.verify(plan, FIXTURE["official_text"], verdicts)
    headline = next(r for r in report if r["id"] == "cover.headline")
    assert headline["verdict"] == "NOT CONFIRMED"


def test_cover_headline_removed_means_no_carousel():
    data = fresh_plan()
    data["cover"]["headline"]["quote"] = "words that are not in the text"
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, FIXTURE["official_text"])
    with pytest.raises(carousel_plan.PlanError, match="cover headline was not confirmed"):
        carousel_plan.build_views(plan)


def test_short_quotes_prove_nothing():
    assert not quote_found("Canon", "Canon announces the EOS R8 Mark II.")


def test_fact_check_reply_must_answer_every_fact():
    plan = carousel_plan.load_plan(fresh_plan())
    reply = '[{"id": "product", "verdict": "CONFIRMED", "quote": "Photoshop 2027 brings new tools"}]'
    verdicts = carousel_plan.parse_verdicts(reply, carousel_plan.iter_facts(plan))
    assert verdicts["product"]["verdict"] == "CONFIRMED"
    assert verdicts["cover.headline"]["verdict"] == "NOT CONFIRMED"


def test_unknown_verdict_word_counts_as_not_confirmed():
    plan = carousel_plan.load_plan(fresh_plan())
    reply = '[{"id": "product", "verdict": "PROBABLY", "quote": "x"}]'
    assert carousel_plan.parse_verdicts(reply, carousel_plan.iter_facts(plan))["product"]["verdict"] == "NOT CONFIRMED"


def test_captions_contain_only_confirmed_facts():
    data = fresh_plan()
    data["captions"]["david"]["facts"][0]["quote"] = "a made-up fact the official text does not contain"
    plan = carousel_plan.load_plan(data)
    carousel_plan.verify(plan, FIXTURE["official_text"])
    caption = carousel_plan.build_caption(plan, "david")
    assert "Relight an image with the new tools." not in caption
    assert "excited to check this out" not in caption and "Which of these would you try first?" in caption


def test_caption_order_is_hook_benefits_question_with_no_generic_opener():
    plan = carousel_plan.load_plan(fresh_plan())
    carousel_plan.verify(plan, FIXTURE["official_text"])
    caption = carousel_plan.build_caption(plan, "tpm")
    assert caption.startswith("We like that Photoshop 2027 can relight an image.")  # 3f: "we" is TPM's view, not its edit
    assert "excited to check this out" not in caption
    assert caption.index("We like that") < caption.index("Use the new tools")
    assert caption.endswith("Which feature would you try first?")


# ---- text lint ----

@pytest.mark.parametrize("text", [
    "RELIGHT—AN IMAGE", "24–50MM LENS", "CANON - NEW BODY", "NEW #Canon", "Canon – new",
])
def test_lint_blocks_dashes_and_hashtags(text):
    assert lint_text("slide 01 headline", text)


@pytest.mark.parametrize("text", [
    "5-axis in-body stabilization", "EOS R8 MARK II", "#1 camera in Japan", "A new-style lens", "Up to 7.5 stops",
])
def test_lint_allows_hyphens_numbers_and_hash_numbers(text):
    assert lint_text("slide 01 headline", text) == []


def test_number_range_dash_is_cleaned_to_a_hyphen():
    assert clean_output("RF 24–50mm") == "RF 24-50mm"
    assert lint_text("x", clean_output("RF 24–50mm")) == []


def test_match_key_ignores_dash_and_quote_variants():
    assert match_key("24–50mm’s") == match_key("24-50mm's")


def test_fixture_slide_text_passes_the_lint():
    plan = carousel_plan.load_plan(fresh_plan())
    carousel_plan.verify(plan, FIXTURE["official_text"])
    views = carousel_plan.build_views(plan)
    texts = carousel_plan.slide_texts(views) + [("caption", carousel_plan.build_caption(plan, "david"))]
    assert lint_texts(texts) == []


def test_overflow_measurements_become_lint_problems():
    assert carousel_text.lint_overflow(["slide 02: headline text does not fit its box"])[0].startswith("text overflows")


# ---- official pages (parsing only) ----

def test_host_match_allows_subdomains_but_not_lookalikes():
    assert official.host_allowed("https://www.canon.com/en/news", ["canon.com"])
    assert not official.host_allowed("https://canon.com.example.net/x", ["canon.com"])
    assert not official.host_allowed("https://notcanon.com/x", ["canon.com"])


def test_page_text_skips_scripts_and_menus():
    markup = "<html><script>var x=1;</script><nav>Menu</nav><article><h1>Canon</h1><p>Hello  world.</p></article></html>"
    assert official.page_text(markup) == "Canon Hello world."


def test_official_links_keep_only_the_brands_own_site():
    markup = '<a href="/press/r8">R8</a><a href="https://other.example/x">no</a>'
    links = official.official_links(markup, "https://www.canon.com/en/news/a", ["canon.com"])
    assert links == ["https://www.canon.com/press/r8"]


def test_hero_image_comes_from_the_page_meta_tag():
    markup = '<meta property="og:image" content="/img/r8.jpg">'
    assert official.hero_image_url(markup, "https://www.canon.com/en/x") == "https://www.canon.com/img/r8.jpg"


# ---- rumor block and eligibility ----

def sent_story(label, claude=None, title="Adobe Releases Photoshop 27.1"):
    story = Story(title=title, brand="Adobe", kind="product", tokens=frozenset())
    story.sources = [{"url": "https://news.example/ps", "link": "https://news.example/ps", "source": "PetaPixel",
                      "source_type": "news", "title": title, "summary": "Adobe shipped it. More.", "published": None}]
    story.last_alert_label = label
    story.claude_label = claude
    return story


def test_rumor_story_can_never_make_a_carousel(rules):
    with pytest.raises(carousel.Refused, match="Rumor stories can never make a carousel"):
        carousel.check_eligible(sent_story(RUMOR), rules)


def test_story_not_sent_cannot_make_a_carousel(rules):
    with pytest.raises(carousel.Refused, match="not been sent to Slack"):
        carousel.check_eligible(sent_story(None), rules)


def test_a_story_claude_now_calls_rumor_cannot_make_a_carousel(rules):
    with pytest.raises(carousel.Refused, match="RUMOR"):
        carousel.check_eligible(sent_story(OFFICIAL, claude=RUMOR), rules)


def test_sent_official_story_is_eligible(rules):
    carousel.check_eligible(sent_story(OFFICIAL), rules)


def test_dashboard_offers_the_command_only_for_sent_official_stories(tmp_path):
    db = tmp_path / "seen.sqlite"
    store = Store(db)
    official_story = sent_story(OFFICIAL)
    store.save_story(official_story, NOW)
    store.mark_alerted(official_story, OFFICIAL)
    rumor_story = sent_story(RUMOR, title="Canon R6 Mark IV rumored specs")
    store.save_story(rumor_story, NOW)
    store.mark_alerted(rumor_story, RUMOR)
    store.db.close()
    out = dashboard.write_dashboard(
        db_path=db, out_path=tmp_path / "index.html", sources_path=ROOT / "config" / "sources.yaml",
        rules_path=ROOT / "config" / "rules.yaml", now=NOW,
    )
    page = out.read_text(encoding="utf-8")
    assert f"carousel.py --story {official_story.id}" in page
    assert f"carousel.py --story {rumor_story.id}" not in page


# ---- placeholders and images ----

def build_views():
    plan = carousel_plan.load_plan(fresh_plan())
    carousel_plan.verify(plan, FIXTURE["official_text"])
    return carousel_plan.build_views(plan)


def test_missing_images_are_listed_by_slide_number(tmp_path):
    slots, missing = carousel_render.slot_images(tmp_path, build_views())
    assert missing == ["01.jpg", "02.jpg", "03.jpg", "04.jpg"]
    assert all(slot["main"] is None for slot in slots)


def test_a_dropped_image_replaces_the_placeholder(tmp_path):
    (tmp_path / "02.png").write_bytes(b"not really a png, only a file name check")
    views = build_views()
    slots, missing = carousel_render.slot_images(tmp_path, views)
    assert slots[1]["main"].name == "02.png"
    assert "02.jpg" not in missing and "02.png" not in missing


def test_no_empty_box_is_drawn_when_there_is_no_image(tmp_path):
    views = build_views()
    slots, _ = carousel_render.slot_images(tmp_path, views)
    page = carousel_render.slide_document(views[0], slots[0], None)
    assert "Add official product image" not in page and "hero-ph" not in page and "<img" not in page


def test_an_image_is_embedded_when_present(tmp_path):
    (tmp_path / "01.jpg").write_bytes(b"x")
    views = build_views()
    slots, _ = carousel_render.slot_images(tmp_path, views)
    page = carousel_render.slide_document(views[0], slots[0], None)
    assert "<img" in page and "Add official product image" not in page


def test_slides_follow_the_reference_order():
    kinds = [v["type"] for v in build_views()]
    assert kinds == ["cover", "feature", "feature", "feature"]


def test_slides_are_1080_by_1440():
    assert carousel_render.WIDTH == 1080 and carousel_render.HEIGHT == 1440


# ---- output folder ----

def test_build_writes_the_folder_and_keeps_dropped_images(tmp_path):
    out = tmp_path / "2026-11-11-photoshop-2027"
    (out / "images").mkdir(parents=True)
    (out / "images" / "01.jpg").write_bytes(b"dropped by Kint")
    result = carousel.assemble(
        fresh_data()["plan"], title=FIXTURE["title"], official_text=FIXTURE["official_text"], verdicts=None,
        out_dir=out, official_url="https://example.invalid/page", article_links=[("PetaPixel", "https://p.example/a")],
        press_images=False, render=False, checked_on="2026-11-11",
    )
    names = {p.name for p in out.iterdir()}
    assert {"captions.txt", "factcheck.md", "sources.md", "plan.json", "images"} <= names
    assert not list(out.glob("[0-9][0-9].png"))
    assert (out / "images" / "01.jpg").read_bytes() == b"dropped by Kint"
    assert result["slides"] == 4 and result["missing"] == ["02.jpg", "03.jpg", "04.jpg"]


def test_factcheck_file_lists_every_claim_and_removals(tmp_path):
    data = fresh_data()
    data["plan"]["slides"][0]["body"]["quote"] = "a sentence the official page never said"
    carousel.assemble(
        data["plan"], title=FIXTURE["title"], official_text=FIXTURE["official_text"], verdicts=None,
        out_dir=tmp_path, official_url="https://example.invalid/page", article_links=[],
        press_images=False, render=False, checked_on="2026-11-11",
    )
    text = (tmp_path / "factcheck.md").read_text(encoding="utf-8")
    assert "| NOT CONFIRMED |" in text and "## Removed" in text
    assert "- slide1 body:" in text
    assert "| CONFIRMED |" in text


def test_captions_file_has_both_accounts_and_no_dashes(tmp_path):
    carousel.assemble(
        fresh_data()["plan"], title=FIXTURE["title"], official_text=FIXTURE["official_text"], verdicts=None,
        out_dir=tmp_path, official_url="https://example.invalid/page", article_links=[],
        press_images=False, render=False, checked_on="2026-11-11",
    )
    text = (tmp_path / "captions.txt").read_text(encoding="utf-8")
    assert "DAVID MOLNAR FACEBOOK" in text and "TPM FACEBOOK AND INSTAGRAM" in text
    assert "#" not in text and "—" not in text and "–" not in text


def test_lint_failure_stops_the_build(tmp_path):
    data = fresh_data()
    data["plan"]["slides"][0]["headline"]["text"] = "RELIGHT—AN IMAGE"
    with pytest.raises(LintError, match="em dash"):
        carousel.assemble(
            data["plan"], title=FIXTURE["title"], official_text=FIXTURE["official_text"], verdicts=None,
            out_dir=tmp_path, official_url="https://example.invalid/page", article_links=[],
            press_images=False, render=False, checked_on="2026-11-11",
        )


def test_overflowing_text_fails_the_render(tmp_path, monkeypatch):
    monkeypatch.setattr(
        carousel_render, "render_pngs",
        lambda documents, paths, work, **kwargs: ["slide 02: headline text does not fit its box"],
    )
    monkeypatch.setattr(carousel_render, "render_contact_sheet", lambda *a, **k: None)
    with pytest.raises(LintError, match="does not fit"):
        carousel.assemble(
            fresh_data()["plan"], title=FIXTURE["title"], official_text=FIXTURE["official_text"], verdicts=None,
            out_dir=tmp_path, official_url="https://example.invalid/page", article_links=[],
            press_images=False, render=True, checked_on="2026-11-11",
        )


def test_a_build_no_longer_renders_the_slow_contact_sheet(tmp_path, monkeypatch):
    """Round 7, section I: preview.png added a second render to every build and nothing used it any more."""
    monkeypatch.setattr(carousel_render, "render_pngs",
                        lambda documents, paths, work, **kwargs: ["slide 02: headline text does not fit its box"])
    monkeypatch.setattr(carousel_render, "render_contact_sheet",
                        lambda *a, **k: pytest.fail("the contact sheet must not be rendered"))
    (tmp_path / "preview.png").write_bytes(b"old sheet")
    with pytest.raises(LintError):
        carousel.assemble(
            fresh_data()["plan"], title=FIXTURE["title"], official_text=FIXTURE["official_text"], verdicts=None,
            out_dir=tmp_path, official_url="https://example.invalid/page", article_links=[],
            press_images=False, render=True, checked_on="2026-11-11",
        )
    assert not (tmp_path / "preview.png").exists()  # an outdated sheet is removed, never shown


def test_sample_mode_builds_offline_into_its_own_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(carousel, "SAMPLE_ROOT", tmp_path)
    result = carousel.run_sample("photoshop", render=False)
    folder = tmp_path / "2026-11-11-photoshop-2027-sample"
    assert result["folder"] == folder and folder.is_dir()
    sources = (folder / "sources.md").read_text(encoding="utf-8")
    assert "SAMPLE" in sources
    assert (folder / "captions.txt").exists() and (folder / "factcheck.md").exists()


def test_sample_refuses_hashtags_and_dashes_in_its_own_text(tmp_path, monkeypatch):
    monkeypatch.setattr(carousel, "SAMPLE_ROOT", tmp_path)
    carousel.run_sample("photoshop", render=False)
    for name in ("captions.txt",):
        text = (tmp_path / "2026-11-11-photoshop-2027-sample" / name).read_text(encoding="utf-8")
        assert lint_text(name, text) == []


def test_item_folder_uses_the_date_and_a_slug(tmp_path, monkeypatch):
    monkeypatch.setattr(carousel, "OUTPUT_ROOT", tmp_path)
    folder = carousel.item_folder("Adobe Releases Photoshop 27.1!", datetime(2026, 11, 11, 12, tzinfo=timezone.utc))
    assert folder == tmp_path / "2026-11-11-adobe-releases-photoshop-27-1"
