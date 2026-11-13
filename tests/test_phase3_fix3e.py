"""Phase 3 fix round 3e: the trimmed PNG is the only image a slide can use, a bigger cover collage, official pages read
with a browser identity (and Chromium when refused), blog images fetched at their large size, the reason a slide has no
image, captions in David's and TPM's voice, and no widow warning for a stacked feature name.
No network, no Claude, no browser."""
import copy
import itertools
import re
import struct

import pytest
import requests
from conftest import ROOT

import carousel
import carousel_plan
import carousel_render
import design_check
import image_pick
import images
import official
from images import Candidate
from test_phase3_fix3b import PASS, candidate, feature_view, png_bytes, slots
from test_phase3_fix3c import (BETA_URL, CAMERA_FIXTURE, DOMAINS, FEATURES, PS_FIXTURE, VIDEO, cover_view, overlaps,
                               tiles_in, wide)

BLOG_POST = "https://blog.adobe.com/en/publish/2026/11/10/explore-new-ways"


def jpeg_bytes(width: int, height: int) -> bytes:
    """A JPEG header that image_dimensions can read (enough for the size rules; never decoded)."""
    return b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", height, width) + b"\x00" * 24


# ---- 1. a trimmed PNG always wins over an untrimmed JPEG ----

def both(folder, stem, size=(1705, 941)):
    (folder / f"{stem}.jpg").write_bytes(png_bytes(1920, 1080))  # the untrimmed copy
    (folder / f"{stem}.png").write_bytes(png_bytes(*size))  # the trimmed one


def test_find_image_takes_the_trimmed_png_not_the_jpg(tmp_path):
    both(tmp_path, "02")
    assert carousel_render.find_image(tmp_path, "02").suffix == ".png"
    (tmp_path / "05.jpg").write_bytes(png_bytes(1920, 1080))
    assert carousel_render.find_image(tmp_path, "05").suffix == ".jpg"  # a lone jpg is still used


def test_a_rendered_slide_and_the_cover_collage_use_the_trimmed_png_when_a_jpg_is_beside_it(tmp_path):
    for n in (2, 3, 4):
        both(tmp_path, f"0{n}")
    views = [{"type": "cover"}, {"type": "feature"}, {"type": "feature"}, {"type": "feature"}]
    slots_, _ = carousel_render.slot_images(tmp_path, views)
    assert [s["main"].name for s in slots_[1:]] == ["02.png", "03.png", "04.png"]
    assert [p.name for p in slots_[0]["collage"]] == ["02.png", "03.png", "04.png"]
    cover = carousel_render.cover_body(cover_view(), slots_[0])
    assert all(f"0{n}.png" in cover for n in (2, 3, 4)) and ".jpg" not in cover
    page = carousel_render.slide_document(feature_view(), slots_[1], None)
    assert "02.png" in page and "02.jpg" not in page


def test_placing_an_image_removes_an_older_untrimmed_copy_of_the_same_slide(tmp_path):
    relight = candidate(tmp_path, "c01.png", "Relight")
    (tmp_path / "images").mkdir()
    for stale in ("01.jpg", "02.jpg", "02.webp"):
        (tmp_path / "images" / stale).write_bytes(png_bytes(1920, 1080))
    image_pick.pick_for_slots(slots(), [relight], tmp_path, "text", "Photoshop", lambda *a: PASS)
    assert sorted(p.name for p in (tmp_path / "images").iterdir()) == ["01.png", "02.png"]


def test_candidates_of_an_earlier_run_are_cleared_but_other_files_stay(tmp_path):
    (tmp_path / "candidates" / "originals").mkdir(parents=True)
    for name in ("c01.jpg", "c02.jpg", "c02.png", "originals/c02.jpg", "notes.txt"):
        (tmp_path / "candidates" / name).write_bytes(b"x")
    images.clear_candidates(tmp_path)
    assert sorted(p.name for p in (tmp_path / "candidates").iterdir() if p.is_file()) == ["notes.txt"]
    assert list((tmp_path / "candidates" / "originals").iterdir()) == []


def test_a_trimmed_poster_leaves_no_untrimmed_copy_in_candidates(tmp_path):
    (tmp_path / "candidates").mkdir()
    (tmp_path / "candidates" / "c01.jpg").write_bytes(b"old")
    original = jpeg_bytes(1920, 1080)
    trim = lambda data: (png_bytes(1705, 941), {"trimmed": True, "left": 104, "right": 107, "top": 67, "bottom": 68,
                                                "inset": 2, "width": 1705, "height": 941, "source_width": 1920,
                                                "source_height": 1080})
    accepted, _ = images.gather_posters([VIDEO], DOMAINS, tmp_path, FEATURES, fetch=lambda url: original, trim=trim)
    assert accepted[0].file == "candidates/c01.png"
    assert not (tmp_path / "candidates" / "c01.jpg").exists()
    assert (tmp_path / "candidates" / "originals" / "c01.jpg").read_bytes() == original


# ---- 2. the cover collage: bigger, readable tiles ----

SIZES = ((2, (1705, 941)), (3, (1687, 922)), (4, (1920, 1080)))


def cover_tiles(tmp_path, view=None):
    images_ = [wide(tmp_path, f"0{n}.png", size) for n, size in SIZES]
    return tiles_in(carousel_render.cover_body(view or cover_view(), {"main": None, "collage": images_}))


def test_the_small_cover_tiles_are_at_least_420_wide_and_span_the_content_width(tmp_path):
    big, left, right = cover_tiles(tmp_path)
    assert left[2] >= 420 and right[2] >= 420
    assert left[1] == right[1] and big[1] + big[3] < left[1]  # one row under the large tile
    assert left[0] <= 66 and right[0] + right[2] >= 1014  # the row fills the 952px content width
    assert 16 <= right[0] - (left[0] + left[2]) <= 24 and 16 <= left[1] - (big[1] + big[3]) <= 24
    assert big[2] > left[2] and big[2] <= 952


def test_the_cover_collage_uses_the_space_down_to_the_footer_and_never_overlaps(tmp_path):
    tiles = cover_tiles(tmp_path)
    for a, b in itertools.combinations(tiles, 2):
        assert not overlaps(a, b)
    assert max(t[1] + t[3] for t in tiles) >= carousel_render.HERO_BOTTOM - 16
    assert max(t[1] + t[3] for t in tiles) <= carousel_render.HERO_BOTTOM
    assert all(t[0] >= 64 and t[0] + t[2] <= 1016 for t in tiles)


def test_two_feature_images_are_stacked_and_a_cramped_space_keeps_the_single_hero():
    rects = carousel_render.collage_layout([1.8, 1.8], top=700)
    assert len(rects) == 2 and rects[0][1] < rects[1][1] and rects[0][2] >= 300
    assert carousel_render.collage_layout([1.8, 1.8, 1.8], top=1100) == []


# ---- 3. official pages: browser identity, Chromium when refused, large blog images ----

def test_official_pages_are_read_with_a_normal_browser_identity():
    assert "Chrome/" in official.USER_AGENT and "compatible" not in official.USER_AGENT
    assert official.PAGE_HEADERS["User-Agent"] == official.USER_AGENT


def refused(status=403):
    return requests.HTTPError("refused", response=type("R", (), {"status_code": status})())


def test_a_refused_page_is_loaded_in_chromium_instead(monkeypatch):
    calls = []
    monkeypatch.setattr(official, "fetch_html_plain", lambda url: (_ for _ in ()).throw(refused()))
    monkeypatch.setattr(official, "fetch_html_browser", lambda url: calls.append(url) or "<html>read</html>")
    assert official.fetch_html("https://helpx.adobe.com/x.html") == "<html>read</html>"
    assert calls == ["https://helpx.adobe.com/x.html"]


def test_a_page_that_reads_normally_does_not_start_a_browser(monkeypatch):
    monkeypatch.setattr(official, "fetch_html_plain", lambda url: "<html>plain</html>")
    monkeypatch.setattr(official, "fetch_html_browser", lambda url: pytest.fail("the browser must not run"))
    assert official.fetch_html("https://helpx.adobe.com/x.html") == "<html>plain</html>"


def test_a_page_neither_way_can_read_says_what_each_attempt_got(monkeypatch):
    monkeypatch.setattr(official, "fetch_html_plain", lambda url: (_ for _ in ()).throw(refused(403)))
    monkeypatch.setattr(official, "fetch_html_browser",
                        lambda url: (_ for _ in ()).throw(official.PageUnreadable("HTTP 404 in the browser")))
    with pytest.raises(requests.RequestException) as caught:
        official.fetch_html("https://helpx.adobe.com/x.html")
    assert "HTTP 403" in str(caught.value) and "HTTP 404 in the browser" in str(caught.value)
    _, _, notes = images.discover_image_pages([], [BETA_URL], FEATURES, DOMAINS,
                                              fetch=lambda url: official.fetch_html(url))
    assert any("could not be read" in n and "HTTP 403" in n and "Chromium" in n for n in notes)


BLOG_IMG = "https://blog.adobe.com/en/publish/2026/11/10/media_1abc.jpg?width=750&format=jpg&optimize=medium"


def test_a_blog_image_is_requested_at_width_2000_then_1200_then_as_the_page_gave_it():
    urls = images.larger_urls(BLOG_IMG)
    assert "width=2000" in urls[0] and "width=1200" in urls[1] and urls[-1] == BLOG_IMG
    assert all("format=jpg" in u and "optimize=medium" in u for u in urls)
    assert images.larger_urls("https://blog.adobe.com/x/hero.jpg?width=750") == ["https://blog.adobe.com/x/hero.jpg?width=750"]
    assert images.larger_urls(BLOG_IMG.replace("width=750", "width=2400")) == [BLOG_IMG.replace("width=750", "width=2400")]


def blog_page(alt="Remove Tool in Photoshop"):
    return [(BLOG_POST, f'<p>Text before.</p><img src="{BLOG_IMG}" alt="{alt}">')]


def test_a_blog_image_that_is_only_small_at_width_750_is_kept_at_its_large_size(tmp_path):
    asked = []

    def fetch(url):
        asked.append(url)
        return jpeg_bytes(2000, 1125) if "width=2000" in url else jpeg_bytes(750, 422)

    accepted, rejected = images.gather(blog_page(), DOMAINS, tmp_path, fetch=fetch, features=FEATURES)
    assert rejected == [] and len(accepted) == 1
    assert (accepted[0].width, accepted[0].height) == (2000, 1125) and "width=2000" in accepted[0].image_url
    assert accepted[0].feature == "Remove Tool"
    assert len(asked) == 1  # the first, largest request was enough


def test_the_next_width_is_tried_when_the_largest_is_refused_and_a_truly_small_image_is_still_skipped(tmp_path):
    def fetch(url):
        if "width=2000" in url:
            raise requests.ConnectionError("no such width")
        return jpeg_bytes(1200, 674) if "width=1200" in url else jpeg_bytes(750, 422)

    accepted, _ = images.gather(blog_page(), DOMAINS, tmp_path, fetch=fetch, features=FEATURES)
    assert accepted[0].width == 1200 and "width=1200" in accepted[0].image_url
    accepted, rejected = images.gather(blog_page(), DOMAINS, tmp_path / "b", fetch=lambda url: jpeg_bytes(750, 422),
                                       features=FEATURES)
    assert accepted == [] and "under 1000px" in rejected[0]["reason"]


def test_an_image_without_alt_text_remembers_the_features_its_paragraph_names(tmp_path):
    markup = ('<p>The Remove Tool now detects footprints, reflections and shadows around an object.</p>'
              f'<p><img src="{BLOG_IMG}" alt=""></p>')
    parsed, _ = images.parse_page(markup, BLOG_POST)
    assert "Remove Tool" in parsed[0]["context"]
    accepted, _ = images.gather([(BLOG_POST, markup)], DOMAINS, tmp_path, fetch=lambda url: jpeg_bytes(2000, 1125),
                                features=FEATURES)
    assert accepted[0].feature == "" and accepted[0].context_features == ["Remove Tool"]


def hinted(tmp_path, features=("Remove Tool",)):
    (tmp_path / "candidates").mkdir(parents=True, exist_ok=True)
    (tmp_path / "candidates" / "c05.png").write_bytes(png_bytes(2000, 1125))
    return Candidate(file="candidates/c05.png", page=BLOG_POST, image_url="https://blog.adobe.com/m.jpg", width=2000,
                     height=1125, alt="", context_features=list(features))


def test_a_hinted_image_is_offered_only_to_the_slide_of_the_feature_its_paragraph_names(tmp_path):
    image = hinted(tmp_path)
    offered = {s.name: image_pick.candidates_for(s, [image]) for s in slots()}
    assert offered["03"] == [image] and offered["02"] == [] and offered["04"] == []


def test_a_hinted_image_is_used_only_when_the_image_check_sees_the_feature(tmp_path):
    image = hinted(tmp_path)
    choices, log = image_pick.pick_for_slots(slots(), [image], tmp_path, "t", "Photoshop", lambda *a: PASS)
    assert choices["03"] is image
    assert any(l.startswith("slide 03") and "paragraph before it" in l and "https://blog.adobe.com/m.jpg" in l
               for l in log)
    wrong = dict(PASS, shows_slide_subject=False)
    choices, log = image_pick.pick_for_slots(slots(), [hinted(tmp_path / "b")], tmp_path / "b", "t", "Photoshop",
                                             lambda *a: wrong)
    assert choices["03"] is None
    line = next(l for l in log if l.startswith("slide 03") and "text-led layout" in l)
    assert "Why:" in line and "shows_slide_subject" in line and "c05.png" in line


def test_a_slide_with_no_candidate_for_its_feature_says_so(tmp_path):
    relight = candidate(tmp_path, "c01.png", "Relight")
    _, log = image_pick.pick_for_slots(slots(), [relight], tmp_path, "t", "Photoshop", lambda *a: PASS)
    line = next(l for l in log if l.startswith("slide 03") and "text-led layout" in l)
    assert "Why: none of the 1 saved official images and demo video posters is tagged with 'REMOVE TOOL'" in line


def test_the_build_output_prints_why_a_slide_has_no_image(capsys):
    result = {"folder": ROOT, "slides": 6, "rendered": True, "confirmed": 26, "removed": [], "missing": ["04.jpg"],
              "design": [], "captions": {}, "no_image": ["slide 04: no official image of this feature passed. Why: x"]}
    carousel.print_summary(result)
    assert "slide 04: no official image of this feature passed. Why: x" in capsys.readouterr().out


# ---- 4. captions in David's and TPM's voice ----

def test_the_draft_prompt_asks_for_david_in_the_first_person_and_tpm_in_the_we_voice():
    prompt = carousel_plan.DRAFT_PROMPT
    assert 'the hook MUST open with "I" or "my"' in prompt
    assert '"we" or "our" MUST appear' in prompt
    assert "UNDER 10 WORDS" in prompt and "never with a plain feature statement" in prompt


def test_caption_voice_problems():
    ok = {"david": "I can add new light sources to my photo. Which would you try?",
          "tpm": "Relight adds light to your scene. Which update would we try first?"}
    assert carousel_plan.caption_voice_problems(ok) == []
    bad = {"david": "Photoshop adds new light sources.", "tpm": "Relight adds new light sources to your scene."}
    problems = carousel_plan.caption_voice_problems(bad)
    assert len(problems) == 2 and "first person" in problems[0] and "we" in problems[1]
    assert carousel_plan.caption_voice_problems({"david": "My edits changed. Which?", "tpm": "Our pick: Relight."}) == []


def test_a_wrong_voice_is_a_warning_not_a_failure():
    findings = design_check.check_caption_voice({"david": "Photoshop adds light.", "tpm": "Relight adds light."})
    assert len(findings) == 2 and all(f["level"] == "WARN" and f["rule"] == "caption voice" for f in findings)


@pytest.mark.parametrize("fixture", [PS_FIXTURE, CAMERA_FIXTURE])
def test_the_sample_captions_are_in_the_right_voice(fixture):
    plan = carousel_plan.load_plan(copy.deepcopy(fixture["plan"]))
    carousel_plan.verify(plan, fixture["official_text"])
    captions = {who: carousel_plan.build_caption(plan, who) for who in ("david", "tpm")}
    assert design_check.check_caption_voice(captions) == []
    assert design_check.check_captions(captions) == []


def test_a_first_person_claim_is_judged_on_its_fact():
    assert "first person" in carousel_plan.FACTCHECK_PROMPT


# ---- 5. widow warnings ----

def widow_findings(*headlines):
    views = [cover_view()] + [feature_view(headline=h) for h in headlines]
    return [f for f in design_check.check_slides(views) if f["rule"] == "widow"]


def test_a_two_or_three_word_feature_name_stacked_on_two_lines_is_not_a_widow():
    assert widow_findings("GENERATIVE RESTYLE", "REMOVE TOOL", "QUICK COMPARE", "AI ASSISTED EDITOR") == []
    assert widow_findings("REMOVE\nTOOL", "AI ASSISTED\nEDITOR") == []


def test_a_longer_headline_with_one_word_on_its_last_line_still_warns():
    found = widow_findings("NEW LIGHT SOURCES\nTODAY")
    assert len(found) == 1 and found[0]["level"] == "WARN"


def measured_box(last_width, lines=2):
    return {"name": "text", "text": "One short sentence that wraps.", "left": 64, "right": 1000, "top": 600,
            "bottom": 700, "lines": lines, "max_lines": 0, "size": 32, "width": 952, "last_width": last_width}


def test_body_text_with_a_very_short_last_line_is_still_a_widow_warning():
    short = design_check._measured(2, [measured_box(60)])
    assert [f["rule"] for f in short] == ["widow"] and short[0]["level"] == "WARN"
    assert design_check._measured(2, [measured_box(400)]) == []
    assert design_check._measured(2, [measured_box(60, lines=1)]) == []  # one line cannot be a widow


def test_the_browser_measure_reports_the_last_line_width():
    assert "last_width" in carousel_render.FIT_SCRIPT and "width: el.clientWidth" in carousel_render.FIT_SCRIPT
