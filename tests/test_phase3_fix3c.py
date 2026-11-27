"""Phase 3 fix round 3c: the grey poster border is trimmed, the cover is a collage of the official feature posters,
help pages are image sources, text led slides are typographic and fill the slide, the cover hook has a second choice,
and captions start with a short hook. No network and no Claude. The browser tests are skipped when Playwright or
Chromium is not available. Help pages come from the saved fixtures in fixtures/adobe/."""
import copy
import itertools
import json
import re
import struct
import sys
import zlib
from pathlib import Path

import pytest
import requests
from conftest import ROOT

import border_trim
import carousel
import carousel_plan
import carousel_render
import design_check
import image_pick
import images
from images import Candidate
from test_phase3_fix2 import TEXT, claimed_confirmed, confirming_recheck, fact, make_plan, refusing_recheck

FIXTURES = ROOT / "fixtures" / "adobe"
PS_FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
CAMERA_FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "canon-eos-r8-mark-ii.json").read_text(encoding="utf-8"))
DOMAINS = ["adobe.com"]
FEATURES = ["Relight", "Generative Restyle", "Remove Tool", "Camera Angles", "Quick Compare"]
CAMERA_URL = ("https://helpx.adobe.com/photoshop/desktop/crop-resize-transform/transform-manipulate-reshape/"
              "change-camera-angles.html")
BETA_URL = "https://helpx.adobe.com/photoshop/desktop/whats-new/whats-new-in-photoshop-beta-on-desktop.html"
REMOVE_URL = "https://helpx.adobe.com/photoshop/desktop/repair-retouch/remove-objects/use-the-remove-tool.html"
WHATS_NEW_URL = "https://helpx.adobe.com/photoshop/desktop/whats-new/whats-new.html"
SAVED = {CAMERA_URL: "helpx-camera-angles.html", BETA_URL: "helpx-beta.html", REMOVE_URL: "helpx-remove-tool.html",
         WHATS_NEW_URL: "helpx-whats-new.html"}


# ---- helpers ----

def png_header(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"


def make_png(width: int, height: int, pixel) -> bytes:
    """A real, decodable RGB PNG built in pure Python. pixel(x, y) returns (r, g, b)."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw += bytes(pixel(x, y))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


def decode_png(data: bytes):
    """(width, height, channels, rows) of an 8 bit RGB or RGBA PNG, enough to compare pixels."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat = 8, b""
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", body[:10])
        elif kind == b"IDAT":
            idat += body
    assert depth == 8 and ctype in (2, 6)
    channels = 3 if ctype == 2 else 4
    raw, stride, rows, prev, i = zlib.decompress(idat), width * channels, [], bytearray(width * channels), 0
    for _ in range(height):
        kind, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + a) & 255
            elif kind == 2:
                line[x] = (line[x] + b) & 255
            elif kind == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return width, height, channels, rows


GREY = (221, 221, 221)
W, H, LEFT, RIGHT, TOP, BOTTOM = 400, 300, 40, 40, 24, 26


def screen_pixel(x, y):
    return (10 + (x * 7) % 60, 30 + (y * 5) % 60, 120 + (x + y) % 80)  # blue-ish, never close to the grey


def bordered(x, y):
    if LEFT <= x < W - RIGHT and TOP <= y < H - BOTTOM:
        return screen_pixel(x, y)
    if 365 <= x < 385 and 100 <= y < 140:
        return (250, 200, 120)  # a cursor glow spilling into the right border
    return GREY


def trimmed_or_skip(data: bytes):
    pytest.importorskip("playwright.sync_api")
    new, info = border_trim.trim_border(data)
    if str(info.get("reason", "")).startswith("the browser could not run"):
        pytest.skip(info["reason"])
    return new, info


def fake_fetch(url: str) -> str:
    if url not in SAVED:
        raise requests.ConnectionError(url)
    return (FIXTURES / SAVED[url]).read_text(encoding="utf-8")


def wide(tmp_path: Path, name: str, size=(1708, 942)) -> Path:
    path = tmp_path / name
    path.write_bytes(png_header(*size))
    return path


# ---- the failing test of round 3b: a relative path has no file address until it is resolved ----

def test_a_relative_image_path_gets_a_file_address():
    html_doc = carousel_render.hero(Path("x.png"), 64, 700, 952, 536)
    assert "file:///" in html_doc and "x.png" in html_doc


def test_every_file_address_in_the_renderer_is_resolved():
    source = (ROOT / "src" / "carousel_render.py").read_text(encoding="utf-8")
    assert source.count(".as_uri()") == source.count(".resolve().as_uri()") > 0


# ---- 1. the grey bezel is trimmed at save time ----

def test_a_uniform_grey_border_is_cropped_to_the_inner_screen_and_no_pixel_changes():
    new, info = trimmed_or_skip(make_png(W, H, bordered))
    assert info["trimmed"] is True
    assert (info["left"], info["right"], info["top"], info["bottom"]) == (LEFT, RIGHT, TOP, BOTTOM)
    width, height, channels, rows = decode_png(new)
    inset = border_trim.INSET
    assert (width, height) == (W - LEFT - RIGHT - 2 * inset, H - TOP - BOTTOM - 2 * inset)
    # Every sampled pixel is the source pixel, only moved: the crop changed no content.
    for x, y in ((0, 0), (5, 9), (width - 1, height - 1), (width // 2, height // 2), (width - 1, 0)):
        got = tuple(rows[y][x * channels:x * channels + 3])
        assert got == screen_pixel(x + LEFT + inset, y + TOP + inset)


def test_the_trim_note_for_sources_md_says_nothing_changed():
    _, info = trimmed_or_skip(make_png(W, H, bordered))
    note = border_trim.describe(info)
    assert note.startswith("uniform border trimmed, no content changed")
    assert "40px left" in note and "24px top" in note


def test_an_image_with_no_border_is_left_exactly_as_it_is():
    data = make_png(W, H, screen_pixel)
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is False and new == data


def test_a_border_on_only_two_sides_is_trimmed_on_those_two_sides_only():
    # since round 3f every side is judged on its own (it used to need all four)
    data = make_png(W, H, lambda x, y: screen_pixel(x, y) if LEFT <= x < W - RIGHT else GREY)
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is True
    assert (info["left"], info["right"], info["top"], info["bottom"]) == (LEFT, RIGHT, 0, 0)
    width, height, _, _ = decode_png(new)
    assert (width, height) == (W - LEFT - RIGHT - 2 * border_trim.INSET, H)


def test_a_mostly_grey_picture_is_not_eaten():
    data = make_png(W, H, lambda x, y: screen_pixel(x, y) if 150 <= x < 250 and 100 <= y < 200 else GREY)
    new, info = trimmed_or_skip(data)
    assert info["trimmed"] is False and new == data


def test_without_a_browser_the_image_is_kept(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    data = make_png(120, 120, screen_pixel)
    new, info = border_trim.trim_border(data)
    assert new == data and info["trimmed"] is False


VIDEO = {"url": "https://video.tv.adobe.com/v/1", "poster": "https://images-tv.adobe.com/mpcv3/relight/p.png",
         "title": "PS Relight", "tag": "", "feature": "Relight", "heading": "", "found_on": "https://blog.adobe.com/x"}


def test_a_trimmed_poster_is_saved_trimmed_with_the_original_kept_and_the_note_recorded(tmp_path):
    original = png_header(1920, 1080)

    def fake_trim(data):
        return png_header(1708, 942), {"trimmed": True, "left": 106, "right": 106, "top": 68, "bottom": 70,
                                       "inset": 2, "width": 1708, "height": 942, "source_width": 1920,
                                       "source_height": 1080}

    accepted, _ = images.gather_posters([VIDEO], DOMAINS, tmp_path, FEATURES, fetch=lambda url: original, trim=fake_trim)
    poster = accepted[0]
    assert (poster.width, poster.height) == (1708, 942)
    assert poster.trimmed.startswith("uniform border trimmed, no content changed")
    assert (tmp_path / poster.file).read_bytes() == png_header(1708, 942)
    assert (tmp_path / "candidates" / "originals" / "c01.png").read_bytes() == original
    # sources.md gets the note through the placed line
    slot = image_pick.Slot("02", 2, "Slide about: RELIGHT", "feature", "RELIGHT")
    ok = {"matches_product": True, "is_real_photo_or_official_screenshot": True, "shows_slide_subject": True,
          "has_watermark": False, "has_people_as_subject": False, "looks_ai_generated": False, "unreadable": False,
          "notes": ""}
    _, log = image_pick.pick_for_slots([slot], accepted, tmp_path, "t", "Photoshop", lambda *a: ok)
    assert any("uniform border trimmed, no content changed" in line for line in log)


def test_a_poster_is_not_trimmed_without_a_trim_function_and_not_when_it_would_become_too_small(tmp_path):
    original = png_header(1920, 1080)
    accepted, _ = images.gather_posters([VIDEO], DOMAINS, tmp_path, FEATURES, fetch=lambda url: original)
    assert accepted[0].trimmed == "" and (tmp_path / accepted[0].file).read_bytes() == original
    small = lambda data: (png_header(900, 500), {"trimmed": True, "left": 1, "right": 1, "top": 1, "bottom": 1,
                                                 "inset": 2, "width": 900, "height": 500, "source_width": 1920,
                                                 "source_height": 1080})
    other = tmp_path / "other"
    accepted, _ = images.gather_posters([VIDEO], DOMAINS, other, FEATURES, fetch=lambda url: original, trim=small)
    assert accepted[0].trimmed == "" and (other / accepted[0].file).read_bytes() == original


# ---- 2. the cover collage ----

def cover_view(hook="ADD NEW LIGHT SOURCES TO A PHOTO", headline="PHOTOSHOP"):
    return {"type": "cover", "label": "ADOBE MAX 2026", "headline": headline, "subline": hook,
            "features": ["RELIGHT", "GENERATIVE RESTYLE", "REMOVE TOOL", "QUICK COMPARE"], "product": "PHOTOSHOP",
            "footer": "SWIPE"}


def tiles_in(html_doc: str):
    return [tuple(int(v) for v in m) for m in re.findall(
        r'class="hero screen[^"]*"(?: data-box="[^"]*")? style="left:(\d+)px;top:(\d+)px;width:(\d+)px;height:(\d+)px"', html_doc)]


def overlaps(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def test_the_collage_layout_has_no_overlap_stays_inside_the_margins_and_keeps_even_gaps():
    for aspects in ([16 / 9] * 3, [1708 / 942] * 3, [16 / 9, 1.6, 2.0], [16 / 9] * 2):
        rects = carousel_render.collage_layout(aspects, top=726)
        assert len(rects) == len(aspects)
        for rect in rects:
            assert rect[0] >= 64 and rect[0] + rect[2] <= 1080 - 64
            assert rect[1] >= 726 and rect[1] + rect[3] <= carousel_render.HERO_BOTTOM
        for a, b in itertools.combinations(rects, 2):
            assert not overlaps(a, b)
        # since round 3e: the first tile on top, the others under it (side by side when there are two of them)
        assert 16 <= rects[1][1] - (rects[0][1] + rects[0][3]) <= 24
        if len(rects) == 3:
            assert 16 <= rects[2][0] - (rects[1][0] + rects[1][2]) <= 24
            assert rects[1][1] == rects[2][1]
        # centred inside the 64px margins
        left, right = min(r[0] for r in rects) - 64, 1016 - max(r[0] + r[2] for r in rects)
        assert abs(left - right) <= 3


def test_the_collage_keeps_every_tile_shape_so_nothing_is_cropped():
    aspects = [16 / 9, 1.6, 2.0]
    for (_, _, w, h), aspect in zip(carousel_render.collage_layout(aspects, top=726), aspects):
        assert abs(w / h - aspect) < 0.03


def test_the_first_tile_is_the_large_one_and_a_tight_space_gives_no_collage():
    rects = carousel_render.collage_layout([16 / 9] * 3, top=726)
    assert rects[0][2] > rects[1][2] and rects[0][2] > rects[2][2]
    assert rects[0][1] < rects[1][1]  # the large tile is above the other two
    assert carousel_render.collage_layout([16 / 9] * 3, top=1200) == []
    assert carousel_render.collage_layout([16 / 9], top=726) == []
    assert carousel_render.collage_layout([16 / 9] * 4, top=726) == []


def test_the_cover_with_three_feature_images_is_a_collage_of_whole_tiles(tmp_path):
    images_ = [wide(tmp_path, f"0{n}.png") for n in (2, 3, 4)]
    html_doc = carousel_render.cover_body(cover_view(), {"main": wide(tmp_path, "01.png"), "collage": images_})
    tiles = tiles_in(html_doc)
    assert len(tiles) == 3
    for a, b in itertools.combinations(tiles, 2):
        assert not overlaps(a, b)
    for left, top, width, height in tiles:
        assert left >= 40 and left + width <= 1040 and top + height <= carousel_render.HERO_BOTTOM
    assert all(f"0{n}.png" in html_doc for n in (2, 3, 4)) and "01.png" not in html_doc
    assert "object-position" not in html_doc and "scale(" not in html_doc


def test_collage_tiles_have_the_rounded_corners_and_cyan_glow_of_every_screen():
    css = carousel_render.CSS
    rule = css[css.index(".hero.screen{"):css.index("}", css.index(".hero.screen{"))]
    assert "border-radius:20px" in rule and "box-shadow:0 0 64px rgba(64,165,255" in rule


def test_with_one_feature_image_the_cover_keeps_a_single_hero(tmp_path):
    html_doc = carousel_render.cover_body(
        cover_view(), {"main": wide(tmp_path, "01.png"), "collage": [wide(tmp_path, "02.png")]})
    assert len(tiles_in(html_doc)) == 1 and "01.png" in html_doc
    none = carousel_render.cover_body(cover_view(), {"main": wide(tmp_path, "01.png")})
    assert len(tiles_in(none)) == 1


def test_a_two_line_headline_still_leaves_the_collage_inside_its_space(tmp_path):
    images_ = [wide(tmp_path, f"0{n}.png") for n in (2, 3, 4)]
    html_doc = carousel_render.cover_body(cover_view(headline="PHOTOSHOP\nFOR EVERYONE"),
                                          {"main": None, "collage": images_})
    for a, b in itertools.combinations(tiles_in(html_doc), 2):
        assert not overlaps(a, b)


def test_slot_images_gives_the_cover_the_feature_images_in_slide_order(tmp_path):
    for n in (2, 3, 5):
        (tmp_path / f"0{n}.png").write_bytes(png_header(1920, 1080))
    views = [{"type": "cover"}, {"type": "feature"}, {"type": "feature"}, {"type": "comparison"}, {"type": "feature"}]
    slots, _ = carousel_render.slot_images(tmp_path, views)
    assert [p.name for p in slots[0]["collage"]] == ["02.png", "03.png", "05.png"]
    assert "collage" not in slots[1]


# ---- 3. official help pages as image sources, from saved fixtures ----

def markup(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_a_help_page_about_one_feature_is_tagged_from_its_heading():
    assert images.page_title(markup("helpx-camera-angles.html")) == "Change camera angles in Photoshop"
    assert images.page_feature(markup("helpx-camera-angles.html"), FEATURES) == "Camera Angles"
    assert images.page_feature(markup("helpx-remove-tool.html"), FEATURES) == "Remove Tool"
    assert images.page_feature(markup("helpx-beta.html"), FEATURES) == ""  # a what's new page is about many features


def test_the_remove_tool_page_is_found_from_a_real_link_on_the_beta_page():
    found = images.feature_links(markup("helpx-beta.html"), BETA_URL, FEATURES, DOMAINS)
    assert ("Remove Tool", REMOVE_URL) in found and ("Camera Angles", CAMERA_URL) in found
    urls = [url for _, url in found]
    assert WHATS_NEW_URL not in urls  # a what's new page is not a feature page
    assert not any("example.com" in url or url.endswith(".jpg") for url in urls)  # official pages only, no image files


def test_the_product_whats_new_page_is_found_from_a_link():
    assert images.whats_new_links(markup("helpx-beta.html"), BETA_URL, DOMAINS, ["photoshop"]) == [WHATS_NEW_URL]
    assert images.whats_new_links(markup("helpx-beta.html"), BETA_URL, DOMAINS, ["lightroom"]) == []


def test_discovery_reads_the_configured_pages_then_follows_feature_links_without_the_network():
    pages, tags, notes = images.discover_image_pages([], [CAMERA_URL, BETA_URL], FEATURES, DOMAINS,
                                                     fetch=fake_fetch, terms=["photoshop"])
    urls = [url for url, _ in pages]
    assert urls[:2] == [CAMERA_URL, BETA_URL]
    assert REMOVE_URL in urls and WHATS_NEW_URL in urls
    assert tags == {CAMERA_URL: "Camera Angles", REMOVE_URL: "Remove Tool"}  # what's new pages carry no page tag
    assert any("help page read for images" in n for n in notes)


def test_a_help_page_that_cannot_be_read_is_skipped_and_noted():
    pages, tags, notes = images.discover_image_pages(
        [], [CAMERA_URL, "https://helpx.adobe.com/missing.html", "https://example.com/x.html"], FEATURES, DOMAINS,
        fetch=fake_fetch)
    assert [url for url, _ in pages] == [CAMERA_URL]
    assert any("missing.html" in n and "could not be read" in n for n in notes)
    assert any("example.com" in n and "not on an official domain" in n for n in notes)


def test_images_on_a_help_page_are_tagged_by_alt_text_or_by_the_page_feature(tmp_path):
    pages = [(CAMERA_URL, markup("helpx-camera-angles.html")), (BETA_URL, markup("helpx-beta.html"))]
    accepted, _ = images.gather(pages, DOMAINS, tmp_path, fetch=lambda url: png_header(1600, 900), features=FEATURES,
                                page_tags={CAMERA_URL: "Camera Angles"})
    by_page = {}
    for c in accepted:
        by_page.setdefault(c.page, []).append(c)
    assert {c.feature for c in by_page[CAMERA_URL]} == {"Camera Angles"}  # even the picture with no alt text
    beta = {c.image_url.rsplit("/", 1)[-1]: c.feature for c in by_page[BETA_URL]}
    assert beta["camera-angles-beta.jpg"] == "Camera Angles"
    assert beta["timelapse.jpg"] == "" and beta["beta-hero.jpg"] == ""  # no feature of the story: not offered


def test_a_demo_video_on_a_feature_help_page_takes_the_page_feature(tmp_path):
    video = dict(VIDEO, title="Camera view", feature="", found_on=CAMERA_URL)
    accepted, _ = images.gather_posters([video], DOMAINS, tmp_path, FEATURES, fetch=lambda u: png_header(1920, 1080),
                                        page_tags={CAMERA_URL: "Camera Angles"})
    assert accepted[0].feature == "Camera Angles"


def test_a_feature_slide_takes_a_help_page_image_of_its_own_feature_only(tmp_path):
    (tmp_path / "candidates").mkdir()
    cands = []
    for n, feature in enumerate(["Camera Angles", "Remove Tool"], 1):
        (tmp_path / "candidates" / f"c0{n}.png").write_bytes(png_header(1600, 900))
        cands.append(Candidate(f"candidates/c0{n}.png", CAMERA_URL, f"https://helpx.adobe.com/{n}.png", 1600, 900,
                               "", feature=feature, kind="image"))
    slot = image_pick.Slot("06", 6, "Slide about: CAMERA ANGLES", "feature", "CAMERA ANGLES")
    assert image_pick.candidates_for(slot, cands) == [cands[0]]


def test_the_real_config_lists_both_help_pages_for_photoshop_stories():
    config = carousel.load_config()
    pages = carousel.image_pages_for(config, "Adobe", ["photoshop"])
    assert CAMERA_URL in pages and BETA_URL in pages
    assert carousel.image_pages_for(config, "Adobe", ["lightroom"]) == []
    assert carousel.image_pages_for(config, "Canon", ["photoshop"]) == []
    assert not any("remove" in url for url in pages)  # the Remove Tool page is found from a link, not guessed


# ---- 3b. text led slides: bigger, centred, no large empty area ----

def feature_view(headline="REMOVE TOOL", accent="NOW CATCHES SHADOWS AND REFLECTIONS",
                 body="It detects footprints, reflections, shadows and waves around an object."):
    return {"type": "feature", "template": "left_body", "label": "NEW IN PHOTOSHOP", "headline": headline,
            "accent": accent, "body": body, "specs": [], "product": "PHOTOSHOP"}


@pytest.mark.parametrize("headline", ["REMOVE TOOL", "CAMERA ANGLES", "RELIGHT", "GENERATIVE RESTYLE", "QUICK COMPARE"])
def test_the_text_led_headline_fills_about_80_percent_of_the_width(headline):
    size = carousel_render.text_led_headline_size(headline)
    longest = max(len(line) for line in carousel_render.split_headline(headline))
    share = size * longest * carousel_render.HEADLINE_EM / 952
    # Round 13: moderate text. The name fills up to about 80% of the width, capped at TEXT_LED_MAX_SIZE.
    assert share <= 0.9 and (share >= 0.7 or size == carousel_render.TEXT_LED_MAX_SIZE), (headline, size, share)
    assert 72 <= size <= carousel_render.TEXT_LED_MAX_SIZE


def test_the_text_led_cyan_line_and_body_are_moderate_and_readable():
    assert 30 <= carousel_render.text_led_accent_size("ADD NEW LIGHT SOURCES") <= 40
    assert 30 <= carousel_render.text_led_accent_size("NOW CATCHES SHADOWS AND REFLECTIONS") <= 40
    assert 28 <= carousel_render.TEXT_LED_BODY_SIZE <= 32
    html_doc = carousel_render.text_led_body(feature_view())
    assert 28 <= int(re.search(r'class="abs body"[^>]*font-size:(\d+)px', html_doc).group(1)) <= 32


@pytest.mark.parametrize("headline,body", [
    ("REMOVE TOOL", "It detects footprints, reflections, shadows and waves around an object."),
    ("CAMERA ANGLES", "Explore new viewpoints of an entire image through direct, on-canvas interactions."),
    ("RELIGHT", "x" * 140),
])
def test_the_text_led_block_is_centred_with_balanced_space_and_no_large_empty_area(headline, body):
    html_doc = carousel_render.text_led_body(feature_view(headline=headline, body=body))
    rule_top = int(re.search(r'style="top:(\d+)px;left:490px;width:100px;height:3px', html_doc).group(1))
    body_top, body_h = (int(v) for v in re.search(
        r'class="abs body"[^>]*style="top:(\d+)px;[^"]*height:(\d+)px', html_doc).groups())
    gap_above = rule_top - carousel_render.TEXT_LED_TOP
    gap_below = carousel_render.TEXT_LED_BOTTOM - (body_top + body_h)
    assert abs(gap_above - gap_below) <= 4  # balanced
    assert gap_above <= 330 and gap_below <= 330  # no very large empty area (the free area is 1096px tall)
    assert gap_above >= 40  # but never pushed against the pill


def test_the_text_led_block_keeps_the_64px_margins():
    html_doc = carousel_render.text_led_body(feature_view())
    for left, width in re.findall(r'class="abs [^"]*"[^>]*style="top:\d+px;left:(\d+)px;width:(\d+)px', html_doc):
        assert int(left) >= 64 and int(left) + int(width) <= 1080 - 64


def test_the_text_led_slide_fits_and_is_large_in_the_browser(tmp_path):
    pytest.importorskip("playwright.sync_api")
    view = feature_view(accent="ADD NEW LIGHT SOURCES")
    out = tmp_path / "s.png"
    measure: list = []
    try:
        problems = carousel_render.render_pngs(
            [carousel_render.slide_document(view, {"main": None, "old": None}, None)], [out], tmp_path / "w",
            measure_log=measure)
    except Exception as exc:  # no Chromium installed
        pytest.skip(f"browser not available: {type(exc).__name__}")
    assert problems == []
    boxes = measure[0]["boxes"]
    headline = next(b for b in boxes if b["name"] == "headline")
    assert headline["right"] - headline["left"] >= 0.45 * 952  # still a clear title (fallback fonts differ a little)
    assert 72 <= headline["size"] <= carousel_render.TEXT_LED_MAX_SIZE
    body = next(b for b in boxes if b["text"].startswith("It detects"))
    assert body["size"] >= 28
    accent = next(b for b in boxes if b["text"] == "ADD NEW LIGHT SOURCES")
    assert 30 <= accent["size"] <= 40 and accent["lines"] == 1


# ---- 2b. the cover hook, with a second choice ----

def with_bad_hook(**extra):
    data = make_plan(headline="PHOTOSHOP")  # the page writes "Photoshop", not "Photoshop 2027"
    data["cover"]["subline"] = fact("ADD LIGHT AFTER THE SHOT", "Relight adds light after the shot")
    data["cover"].update(extra)
    return data


def test_a_confirmed_hook_needs_no_second_choice():
    data = make_plan(headline="PHOTOSHOP")
    data["cover"]["subline"] = fact("NEW LIGHT SOURCES BLEND INTO THE SCENE", "new light sources that blend into the scene")
    seen: list = []
    new_data, _, notes = carousel.settle_hook(data, TEXT, claimed_confirmed(data), ["RELIGHT"], confirming_recheck(seen))
    assert new_data is data and seen == [] and notes == []


def test_when_the_first_hook_is_removed_the_second_choice_is_tried():
    data = with_bad_hook(subline_alt=fact("RELIGHT ADDS NEW LIGHT SOURCES", "Relight adds new light sources"))
    seen: list = []
    new_data, merged, notes = carousel.settle_hook(data, TEXT, claimed_confirmed(data), ["RELIGHT"],
                                                   confirming_recheck(seen))
    assert new_data["cover"]["subline"]["text"] == "RELIGHT ADDS NEW LIGHT SOURCES"
    assert seen == [{"cover.subline"}] and "second choice" in notes[0]
    plan = carousel_plan.load_plan(new_data)
    carousel_plan.verify(plan, TEXT, merged)
    assert carousel_plan.build_views(plan)[0]["subline"] == "RELIGHT ADDS NEW LIGHT SOURCES"


def test_with_no_usable_second_choice_the_most_literal_official_wording_is_tried():
    data = with_bad_hook()
    new_data, _, notes = carousel.settle_hook(data, TEXT, claimed_confirmed(data), ["RELIGHT"], confirming_recheck([]))
    assert new_data["cover"]["subline"]["text"] == "RELIGHT ADDS NEW LIGHT SOURCES"
    assert "literal" in notes[0]
    from carousel_text import quote_found
    assert quote_found(new_data["cover"]["subline"]["quote"], TEXT)  # the quote is the page's own words


def test_a_second_choice_that_the_fact_check_removes_too_falls_through_and_then_gives_up():
    data = with_bad_hook(subline_alt=fact("RELIGHT ADDS NEW LIGHT SOURCES", "Relight adds new light sources"))
    new_data, _, notes = carousel.settle_hook(data, TEXT, claimed_confirmed(data), ["RELIGHT"], refusing_recheck)
    assert new_data is data and "no hook" in notes[0]


def test_the_literal_hook_is_cut_before_the_first_clause_word_and_fits_two_lines():
    text = ("Relight creatively adds new light sources that dynamically and naturally blend into the scene "
            "using non-destructive control.")
    hook = carousel_plan.literal_hook(text, ["RELIGHT"])
    assert hook["text"] == "RELIGHT CREATIVELY ADDS NEW LIGHT SOURCES"
    assert hook["quote"] == "Relight creatively adds new light sources"
    assert len(hook["text"]) <= carousel_plan.HOOK_CHARS_MAX
    assert carousel_plan.literal_hook("Relight is here.", ["RELIGHT"]) is None  # too short to be a hook
    assert carousel_plan.literal_hook("nothing", ["RELIGHT"]) is None


def test_the_draft_prompt_asks_for_a_hook_close_to_the_official_words_and_a_second_choice():
    prompt = carousel_plan.draft_prompt("t", "u", "text", ["Photoshop"])
    assert "cover HOOK" in prompt and "OFFICIAL WORDING" in prompt and "subline_alt" in prompt
    assert "NEW LIGHT SOURCES THAT BLEND NATURALLY INTO THE SCENE" in prompt
    assert "ADD NEW LIGHT SOURCES TO ANY SCENE" not in prompt  # the removed hook is not offered as the example
    assert '"subline_alt": F' in prompt


# ---- 4. captions start with a short hook ----

def test_the_caption_prompt_asks_for_a_hook_under_10_words_and_a_caption_under_50():
    block = carousel_plan.draft_prompt("t", "u", "text", ["Photoshop"]).split("Captions, in this order")[1]
    assert "UNDER 10 WORDS" in block and "UNDER 50 words" in block
    assert 'first person ("I")' in block and '"we" voice' in block
    assert "No dashes, hashtags or parentheses" in block
    assert "code adds" not in block


def test_a_caption_hook_of_10_words_or_more_is_flagged_and_9_is_not():
    nine = "One two three four five six seven eight nine. Then a detail."
    ten = "One two three four five six seven eight nine ten. Then a detail."
    ok = design_check.check_captions({"david": nine, "tpm": nine})
    assert not any(f["rule"] == "caption hook" for f in ok)
    flagged = design_check.check_captions({"david": ten, "tpm": nine})
    assert [f["rule"] for f in flagged if f["level"] == "WARN"].count("caption hook") == 1


def test_a_caption_must_be_under_50_words():
    assert not any(f["rule"] == "caption length"
                   for f in design_check.check_captions({"david": "Short hook. " + "word " * 46, "tpm": "Hi there."}))
    fifty = "Short hook. " + "word " * 48  # 50 words
    assert len(fifty.split()) == 50
    assert any(f["level"] == "FAIL" and f["rule"] == "caption length"
               for f in design_check.check_captions({"david": fifty, "tpm": "Hi there."}))


@pytest.mark.parametrize("fixture", [PS_FIXTURE, CAMERA_FIXTURE])
def test_the_sample_captions_open_with_a_hook_under_10_words_and_stay_under_50_words(fixture):
    plan = carousel_plan.load_plan(copy.deepcopy(fixture["plan"]))
    carousel_plan.verify(plan, fixture["official_text"])
    for who in ("david", "tpm"):
        text = carousel_plan.build_caption(plan, who)
        hook = plan["captions"][who]["hook"]["text"]
        assert len(hook.split()) <= carousel_plan.CAPTION_HOOK_WORDS_MAX
        assert text.startswith(hook) and len(text.split()) < carousel_plan.CAPTION_WORDS_MAX
        assert not [f for f in design_check.check_captions({who: text})]
        assert not re.search(r"[#()–—]", text)
