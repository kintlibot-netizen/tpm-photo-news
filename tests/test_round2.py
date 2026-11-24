"""Phase 2 fix round 2: real image candidates, design QA, marketing captions, official lookup, samples.

No network, no Claude, no browser. Requests and feeds are faked.
"""
import copy
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import ROOT

import carousel
import carousel_plan
import carousel_render
import dedupe
import design_check
import images
import official
from dedupe import Story

FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
CAMERA = json.loads((ROOT / "fixtures" / "carousel" / "canon-eos-r8-mark-ii.json").read_text(encoding="utf-8"))


def png_bytes(width, height):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00" + b"0" * 64


def jpeg_bytes(width, height):
    return b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width) + b"\x00" * 40


def webp_vp8x_bytes(width, height):
    return (b"RIFF" + b"\x00" * 4 + b"WEBP" + b"VP8X" + b"\x00" * 4 + b"\x00" * 4
            + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little") + b"\x00" * 20)


# ---- image sizes and rules ----

def test_pixel_size_is_read_from_png_jpeg_and_webp_headers():
    assert images.image_dimensions(png_bytes(1600, 900)) == (1600, 900)
    assert images.image_dimensions(jpeg_bytes(1200, 800)) == (1200, 800)
    assert images.image_dimensions(webp_vp8x_bytes(2048, 1365)) == (2048, 1365)
    assert images.image_dimensions(b"not an image at all") is None


def test_small_images_are_skipped():
    reason = images.reject_reason({"src": "https://www.canon.com/a.jpg", "alt": "R8", "kind": "img"},
                                  jpeg_bytes(800, 600), "https://www.canon.com/p", ["canon.com"])
    assert reason and "under 1000px" in reason


def test_large_official_image_is_accepted():
    assert images.reject_reason({"src": "https://www.canon.com/a.jpg", "alt": "EOS R8 Mark II", "kind": "og"},
                                jpeg_bytes(2400, 1600), "https://www.canon.com/p", ["canon.com"]) is None


@pytest.mark.parametrize("alt, src", [
    ("Firefly generated camera art", "https://www.canon.com/a.jpg"),
    ("AI generated image of a lens", "https://www.canon.com/a.jpg"),
    ("Midjourney render of the camera", "https://www.canon.com/a.jpg"),
])
def test_ai_generated_alt_text_is_skipped(alt, src):
    reason = images.reject_reason({"src": src, "alt": alt, "kind": "img"}, jpeg_bytes(2400, 1600),
                                  "https://www.canon.com/p", ["canon.com"])
    assert reason and "AI-generated" in reason


def test_firefly_app_screenshot_is_kept():
    assert images.reject_reason({"src": "https://helpx.adobe.com/s.png", "alt": "Firefly screenshot of Photoshop",
                                 "kind": "img"}, png_bytes(2400, 1400), "https://helpx.adobe.com/p",
                                ["adobe.com"]) is None


def test_ai_metadata_in_the_file_is_skipped():
    data = jpeg_bytes(2400, 1600) + b"<digitalSourceType>trainedAlgorithmicMedia</digitalSourceType>"
    reason = images.reject_reason({"src": "https://www.canon.com/a.jpg", "alt": "camera", "kind": "img"},
                                  data, "https://www.canon.com/p", ["canon.com"])
    assert reason and "metadata" in reason


@pytest.mark.parametrize("alt", ["photographer holding the R8", "portrait of a model", "family on a beach"])
def test_images_with_people_as_the_subject_are_skipped(alt):
    reason = images.reject_reason({"src": "https://www.canon.com/a.jpg", "alt": alt, "kind": "img"},
                                  jpeg_bytes(2400, 1600), "https://www.canon.com/p", ["canon.com"])
    assert reason and "people" in reason


def test_logos_are_skipped():
    reason = images.reject_reason({"src": "https://www.canon.com/logo.png", "alt": "Canon logo", "kind": "img"},
                                  png_bytes(2400, 1400), "https://www.canon.com/p", ["canon.com"])
    assert reason and "logo" in reason


def test_images_from_other_hosts_are_skipped():
    reason = images.reject_reason({"src": "https://photosite.example/r8.jpg", "alt": "R8", "kind": "img"},
                                  jpeg_bytes(2400, 1600), "https://www.canon.com/p", ["canon.com"])
    assert reason and "official domain" in reason


# ---- gathering candidates from official pages (fake downloads) ----

OFFICIAL_PAGE = """<html><head><meta property="og:image" content="/img/r8-hero.jpg"></head>
<body><img src="/img/r8-side.jpg" alt="EOS R8 Mark II side view" width="2400" height="1600">
<img src="/img/logo.png" alt="Canon logo">
<img src="/img/person.jpg" alt="photographer with the camera">
<img src="/img/small.jpg" alt="thumbnail" width="300" height="200">
<img src="https://other.example/x.jpg" alt="elsewhere">
<a href="/press-kit/r8">press kit</a></body></html>"""


def test_gather_saves_only_accepted_candidates_and_lists_them(tmp_path):
    files = {
        "https://www.canon.com/img/r8-hero.jpg": jpeg_bytes(2400, 1600),
        "https://www.canon.com/img/r8-side.jpg": png_bytes(2400, 1600),
    }

    def fake_fetch(url):
        if url not in files:
            raise ValueError(f"no fake file for {url}")
        return files[url]

    accepted, rejected = images.gather([("https://www.canon.com/en/r8", OFFICIAL_PAGE)],
                                       ["canon.com"], tmp_path, fetch=fake_fetch)
    assert [c.file for c in accepted] == ["candidates/c01.jpg", "candidates/c02.png"]
    assert (tmp_path / "candidates" / "c01.jpg").exists()
    reasons = " ".join(r["reason"] for r in rejected)
    assert "logo" in reasons and "people" in reasons and "declared size" in reasons
    assert "official domain" in reasons


def test_candidates_markdown_lists_file_source_url_and_size(tmp_path):
    accepted = [images.Candidate("candidates/c01.jpg", "https://www.canon.com/en/r8",
                                 "https://www.canon.com/img/r8-hero.jpg", 2400, 1600, "R8")]
    text = images.candidates_markdown(accepted, [], ["https://www.canon.com/en/r8"])
    assert "candidates/c01.jpg" in text and "2400x1600" in text
    assert "https://www.canon.com/en/r8" in text and "https://www.canon.com/img/r8-hero.jpg" in text


def test_nothing_is_placed_on_slides_unless_asked(tmp_path):
    (tmp_path / "candidates").mkdir()
    (tmp_path / "candidates" / "c01.jpg").write_bytes(jpeg_bytes(2400, 1600))
    accepted = [images.Candidate("candidates/c01.jpg", "p", "u", 2400, 1600, "")]
    # Only images.place copies files to images/; gather never does.
    assert not (tmp_path / "images" / "01.jpg").exists()
    lines = images.place(accepted, tmp_path, slides=1)
    assert (tmp_path / "images" / "01.jpg").exists() and "auto-placed" in lines[0]


def test_auto_pick_is_on_in_the_config_and_never_generates():
    assert carousel.load_config()["use_official_press_images"] is True


def test_no_image_generation_code_anywhere():
    # Detection words for AI-made images are allowed (images.AI_WORDS); generation or cut-out code is not.
    banned = ["dall-e(", "images.generate", "rembg", "remove.bg", "background_removal", "firefly_api",
              "openai.images", "stable_diffusion", "diffusers"]
    for path in Path(ROOT, "src").glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for word in banned:
            assert word not in text, f"{path.name} contains {word}"


# ---- design QA ----

def _verified_views(fixture):
    plan = carousel_plan.load_plan(copy.deepcopy(fixture["plan"]))
    carousel_plan.verify(plan, fixture["official_text"])
    return carousel_plan.build_views(plan)


def _views(count, template="left_body", headline="RELIGHT\nIMAGES", body="One short sentence."):
    base = _verified_views(FIXTURE)
    views = [base[0]] + [dict(base[1], template=template, headline=headline, body=body)] * (count - 1)
    return views


def test_design_passes_the_fixtures():
    for fixture in (FIXTURE, CAMERA):
        plan = carousel_plan.load_plan(copy.deepcopy(fixture["plan"]))
        carousel_plan.verify(plan, fixture["official_text"] + " Photoshop 2026 had no relight tool."
                             " Expected availability is late October.")
        views = carousel_plan.build_views(plan)
        captions = {who: carousel_plan.build_caption(plan, who) for who in ("david", "tpm")}
        findings = design_check.run_design_check(views, captions, None)
        assert not design_check.has_failures(findings), findings


def test_three_line_headline_fails():
    findings = design_check.check_slides(_views(4, headline="A\nB\nC"))
    assert any(f["level"] == "FAIL" and f["rule"] == "headline lines" for f in findings)


def test_one_word_on_the_last_line_is_a_warning():
    # since 3e a two or three word feature name stacked on two lines is intended (REMOVE / TOOL); a longer headline
    # with one word alone on its last line is still a widow
    findings = design_check.check_slides(_views(4, headline="NEW LIGHT SOURCES\nTODAY"))
    assert any(f["level"] == "WARN" and f["rule"] == "widow" for f in findings)
    assert not design_check.has_failures(findings)
    assert not any(f["rule"] == "widow" for f in design_check.check_slides(_views(4, headline="RELIGHT\nIMAGES")))


def test_two_sentence_body_fails():
    findings = design_check.check_slides(_views(4, body="One. Two."))
    assert any(f["level"] == "FAIL" and f["rule"] == "body copy" for f in findings)


def test_too_few_or_too_many_slides_fails():
    assert any(f["rule"] == "slide count" for f in design_check.check_slides(_views(3)))
    assert any(f["rule"] == "slide count" for f in design_check.check_slides(_views(8)))
    assert not any(f["rule"] == "slide count" for f in design_check.check_slides(_views(5)))


def test_footer_in_a_different_place_fails(monkeypatch):
    views = _views(4)
    real = carousel_render.slide_layout

    def shifted(view):
        layout = real(view)
        if view is views[2]:
            layout = dict(layout, footer_top=layout["footer_top"] - 40)
        return layout

    monkeypatch.setattr(carousel_render, "slide_layout", shifted)
    findings = design_check.check_slides(views)
    assert any(f["rule"] == "footer position" and f["level"] == "FAIL" for f in findings)


def test_text_within_64px_of_the_edge_fails_when_measured():
    views = _views(4)
    measured = [{"boxes": [{"name": "text", "text": "edge text", "left": 20, "right": 500,
                            "top": 300, "bottom": 360, "lines": 1, "size": 30}]}] * 4
    findings = design_check.check_slides(views, measured)
    assert any(f["rule"] == "edge margin" and f["level"] == "FAIL" for f in findings)


def test_contrast_meets_wcag_aa_for_every_text_style():
    assert design_check.check_contrast() == []
    assert design_check.contrast_ratio("#ffffff", "#000000") > 20


def test_caption_over_60_words_fails():
    long = " ".join(["word"] * 61)
    findings = design_check.check_captions({"david": long, "tpm": "short one."})
    assert any(f["level"] == "FAIL" and f["rule"] == "caption length" for f in findings)


def test_repeated_caption_openers_warn():
    text = "It can generate. It adds beta features. It is fast."
    findings = design_check.check_captions({"david": text, "tpm": "We're here."})
    assert any(f["level"] == "WARN" and f["rule"] == "repeated openers" for f in findings)


def test_design_findings_are_printed_and_written_as_markdown():
    findings = [{"level": "WARN", "slide": 2, "rule": "widow", "message": "one word alone | x"}]
    md = design_check.markdown(findings)
    assert "## Design check" in md and "widow" in md and "/ x" in md
    assert design_check.summary_lines(findings)[0].startswith("Design check:")


# ---- captions ----

@pytest.mark.parametrize("fixture", [FIXTURE, CAMERA])
def test_captions_are_under_60_words_and_have_no_hashtags_or_dashes(fixture):
    plan = carousel_plan.load_plan(copy.deepcopy(fixture["plan"]))
    carousel_plan.verify(plan, fixture["official_text"])
    for who in ("david", "tpm"):
        text = carousel_plan.build_caption(plan, who)
        assert len(text.split()) < 60
        assert "#" not in text and "—" not in text and "–" not in text


def test_camera_caption_opens_with_a_specific_hook_not_a_generic_opener():
    plan = carousel_plan.load_plan(copy.deepcopy(CAMERA["plan"]))
    carousel_plan.verify(plan, CAMERA["official_text"])
    text = carousel_plan.build_caption(plan, "david")
    assert text.startswith("I get up to 7.5 stops of stabilization.")  # changed in 3e: David's first person voice
    assert "excited to check this out" not in text


# ---- official page lookup ----

def test_anchors_come_from_model_names_years_and_product_line():
    anchors = carousel.story_anchors(FIXTURE["title"], "Adobe")
    assert "2027" in anchors and "photoshop" in anchors


def test_no_official_page_is_a_clear_refusal(monkeypatch):
    story = Story(title="Adobe Releases Photoshop 27.1", brand="Adobe", kind="product", tokens=frozenset())
    story.sources = [{"url": "https://news.example/a", "link": "https://news.example/a", "source": "DCW",
                      "source_type": "news", "title": story.title, "summary": "", "published": None}]

    def unreachable(url, *a, **k):
        raise carousel.requests.ConnectionError("offline")

    monkeypatch.setattr(carousel.official, "fetch_html", unreachable)
    config = {"official_domains": {"Adobe": ["adobe.com"]}, "official_feeds": {"Adobe": []}}
    with pytest.raises(carousel.Refused, match="No official page for this story was found"):
        carousel.locate_official(story, "Adobe", config, None)


def test_article_site_is_never_the_fact_source(monkeypatch):
    story = Story(title="Adobe Releases Photoshop 27.1", brand="Adobe", kind="product", tokens=frozenset())
    article = "https://www.digitalcameraworld.example/photoshop"
    story.sources = [{"url": article, "link": article, "source": "DCW", "source_type": "news",
                      "title": story.title, "summary": "", "published": None}]
    pages = {article: '<a href="https://blog.adobe.com/en/relight">Adobe post</a>'
                      '<a href="https://www.digitalcameraworld.example/x">more</a>',
             "https://blog.adobe.com/en/relight": "<p>" + "Adobe text. " * 40 + "</p>"}
    monkeypatch.setattr(carousel.official, "fetch_html", lambda url, *a, **k: pages[url])
    config = {"official_domains": {"Adobe": ["adobe.com"]}, "official_feeds": {"Adobe": []}}
    page = carousel.locate_official(story, "Adobe", config, None)
    assert page.url == "https://blog.adobe.com/en/relight"
    assert "digitalcameraworld" not in page.url


# ---- sample modes ----


