"""Kint's standing rule (round 13): on every carousel slide the official image is bigger than the text, and the text
is moderate. The design check fails a slide whose text covers as much as its image."""
import struct
import zlib
from pathlib import Path

import pytest

import carousel_render
import design_check

ROOT = Path(__file__).resolve().parents[1]
SLIDE = carousel_render.WIDTH * carousel_render.HEIGHT
FONTS = ROOT / "assets" / "fonts"


def png(path: Path, width: int, height: int, pixel) -> Path:
    """A plain RGB PNG; pixel(x, y) gives the colour."""
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(width)) for y in range(height))
    chunk = lambda kind, data: (struct.pack(">I", len(data)) + kind + data  # noqa: E731
                                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


def product_on_white(x, y):  # a dark product in the middle of a flat white background (a typical press shot)
    return (20, 20, 24) if 60 < x < 260 and 50 < y < 140 else (255, 255, 255)


def busy_screenshot(x, y):  # a screenshot: colour right up to every edge
    return ((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256)


def feature(headline="SILKY SWIFT VCM", accent="FAST, PRECISE, SMOOTH AF",
            body="Built to track rapidly moving athletes across the frame."):
    return {"type": "feature", "template": "left_body", "label": "AUTOFOCUS", "headline": headline,
            "accent": accent, "body": body, "product": "NIKKOR Z 120-300MM F/2.8 TC VR S"}


def entry(images, boxes):
    return {"images": [dict(zip(("left", "top", "width", "height"), i)) for i in images],
            "boxes": [dict(zip(("left", "top", "right", "bottom"), b), text="x", lines=1) for b in boxes]}


def test_the_design_check_fails_a_slide_whose_text_is_as_big_as_its_image():
    small_image = entry([(0, 700, 400, 300)], [(64, 200, 1016, 330)])  # 120,000 px image, 123,760 px text
    findings = design_check.image_vs_text(3, small_image)
    assert [f["rule"] for f in findings] == ["image bigger than text"] and findings[0]["level"] == "FAIL"
    assert "must be bigger than the text" in findings[0]["message"]
    big_image = entry([(0, 500, 1080, 800)], [(64, 200, 1016, 330)])
    assert design_check.image_vs_text(3, big_image) == []
    text_only = entry([], [(64, 200, 1016, 900)])  # the closing slide has no image: nothing to compare
    assert design_check.image_vs_text(7, text_only) == []
    assert design_check.has_failures(design_check.check_slides([feature()] * 4, [small_image] * 4))


def test_the_text_is_moderate_and_the_feature_image_area_is_over_half_the_slide():
    assert carousel_render.LB_SIZES[1] <= 84 and carousel_render.LB_SIZES[2] <= 72
    assert carousel_render.LB_BODY_SIZE <= 28 and carousel_render.LB_ACCENT_SIZE <= 30
    assert carousel_render.COVER_HEADLINE_SIZE <= 100 and carousel_render.CLOSING_HEADLINE_SIZE <= 96
    assert carousel_render.TEXT_LED_MAX_SIZE <= 120
    assert carousel_render.TEXT_STYLES["headline"][2] <= 84 and carousel_render.TEXT_STYLES["body"][2] <= 28
    for view in (feature(), feature(headline="BUILT-IN 1.4X TELECONVERTER", body="One switch. " * 6)):
        top = carousel_render.left_body_text_end(view) + carousel_render.LB_IMAGE_GAP
        area = carousel_render.IMAGE_WIDTH * (carousel_render.HERO_BOTTOM - top)
        assert area / SLIDE >= 0.5, view["headline"]
    _, top, width, height = carousel_render.FEATURE_BOX
    assert width * height / SLIDE >= 0.5


def render(tmp_path, views, slots):
    pytest.importorskip("playwright.sync_api")
    documents = [carousel_render.slide_document(v, s, FONTS if FONTS.exists() else None) for v, s in zip(views, slots)]
    log: list = []
    problems = carousel_render.render_pngs(documents, [tmp_path / f"{n}.png" for n in range(len(views))],
                                           tmp_path / "work", measure_log=log)
    assert problems == []
    return log


def test_a_product_shot_on_white_fills_its_image_area_and_beats_the_text_in_the_browser(tmp_path):
    shot = png(tmp_path / "02.png", 320, 190, product_on_white)
    screen = png(tmp_path / "03.png", 320, 180, busy_screenshot)
    log = render(tmp_path, [feature(), feature()], [{"main": shot, "old": None}, {"main": screen, "old": None}])
    flat, busy = log
    assert flat["images"][0]["filled"] is True  # the white card fills the whole image area
    assert busy["images"][0]["filled"] is False  # a screenshot keeps its own shape, never cropped or padded
    image, text = design_check.areas(flat)
    assert image / SLIDE >= carousel_render.IMAGE_SHARE_TARGET and image > 4 * text
    image, text = design_check.areas(busy)
    assert image / SLIDE >= 0.4 and image > 4 * text
    assert design_check.image_vs_text(2, flat) == [] and design_check.image_vs_text(3, busy) == []


def test_the_price_and_cover_slides_put_the_image_first_too(tmp_path):
    shot = png(tmp_path / "06.png", 320, 190, product_on_white)
    price = {"type": "price", "label": "PRICE + AVAILABILITY", "prices": [{"value": "$13,999.95",
             "caption": "SUGGESTED RETAIL PRICE (US)"}], "availability": "AVAILABLE MID-NOVEMBER 2026",
             "quick_take": {"sentence": "Made for sports, from figure skating to soccer.",
                            "question": "Would you pick it?"}, "cta": "SHARE YOUR TAKE IN THE COMMENTS.",
             "product": "NIKKOR Z 120-300MM F/2.8 TC VR S"}
    cover = {"type": "cover", "label": "NIKON", "headline": "NIKKOR Z\n120-300MM F/2.8 TC VR S",
             "subline": "THE WORLD'S FIRST OF ITS KIND", "features": ["BUILT-IN 1.4X TELECONVERTER", "6.5-STOP VR"],
             "product": "NIKKOR Z 120-300MM F/2.8 TC VR S"}
    log = render(tmp_path, [price, cover], [{"main": shot, "old": None}, {"main": shot, "old": None, "collage": []}])
    for slide in log:
        image, text = design_check.areas(slide)
        assert image > 2 * text and image / SLIDE >= 0.35


def test_two_word_cover_name_stays_on_one_line():
    # Kint (Nov 28 2026): 'CLASSIC' must not sit alone on the Lightroom Classic cover.
    import carousel_render as r
    assert r.cover_headline_mode("LIGHTROOM CLASSIC") == "single"
    assert r.cover_headline_mode("PHOTOSHOP 2027") == "split"  # the model number line is on purpose
    assert r.cover_headline_mode("CANON EOS R8 MARK II") == "split"
    parts, _ = r._cover_text({"label": "ADOBE", "headline": "LIGHTROOM CLASSIC"})
    assert 'data-max-lines="1"' in parts[1] and "<br>" not in parts[1]
