"""Phase 3 fix round 3: official demo video posters as feature images, the cover fallback image, the
comparison title layout and the left_body spacing. Uses the saved Adobe fixtures in fixtures/adobe/. No network,
no Claude, no browser."""
import struct
from pathlib import Path

import carousel_render
import image_pick
import images
import official
from images import Candidate

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "adobe"
BLOG_URL = "https://blog.adobe.com/en/publish/2026/11/10/explore-new-ways-create-across-creative-cloud"
PRODUCT_TERMS = ["photoshop"]
FEATURES = ["Relight", "Generative Restyle", "Quick Compare"]
ADOBE_DOMAINS = ["adobe.com"]
RELIGHT = "https://video.tv.adobe.com/v/3508084"
RESTYLE = "https://video.tv.adobe.com/v/3508087"
RELIGHT_POSTER = "https://images-tv.adobe.com/mpcv3/relight/poster_1920x1080.jpg"
RESTYLE_POSTER = "https://images-tv.adobe.com/mpcv3/restyle/poster_1920x1080.jpg"
PASS = {"matches_product": True, "is_real_photo_or_official_screenshot": True, "shows_slide_subject": True,
        "has_watermark": False, "has_people_as_subject": False, "looks_ai_generated": False,
        "notes": "clear product screenshot", "unreadable": False}


def blog_markup() -> str:
    return (FIXTURES / "blog-roundup.html").read_text(encoding="utf-8")


def fixture_fetch(url: str) -> str:
    """Stands in for official.fetch_html: reads the saved video page, or fails like a page that is not saved."""
    video_id = url.rstrip("/").rsplit("/", 1)[-1]
    path = FIXTURES / f"video-{video_id}.html"
    if not path.exists():
        raise ValueError(f"no saved page for {url}")
    return path.read_text(encoding="utf-8")


def png_bytes(width: int, height: int) -> bytes:
    """The start of a PNG file: signature and IHDR header, enough for the pixel size check."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00"


def discovered() -> dict[str, dict]:
    videos, _ = official.discover_videos([(BLOG_URL, blog_markup())], PRODUCT_TERMS, fetch=fixture_fetch)
    return {video["url"]: video for video in videos}


# ---- finding the demo videos in the official post ----

def test_the_product_section_links_its_demo_videos():
    links = {link["url"]: link for link in official.video_links(blog_markup(), PRODUCT_TERMS)}
    assert links[RELIGHT]["in_product"] is True
    assert links[RELIGHT]["feature"] == "Relight"
    assert links[RESTYLE]["in_product"] is True
    assert links[RESTYLE]["feature"] == "Generative Restyle"
    assert links["https://video.tv.adobe.com/v/3508090"]["feature"] == "Quick Compare"  # a bare text address


def test_the_menu_video_is_not_a_demo_and_the_premiere_video_is_not_the_product():
    links = {link["url"]: link for link in official.video_links(blog_markup(), PRODUCT_TERMS)}
    assert "https://video.tv.adobe.com/v/9999999" not in links  # inside the page's navigation
    assert links["https://video.tv.adobe.com/v/3508100"]["in_product"] is False


def test_a_video_linked_twice_is_read_once():
    urls = [link["url"] for link in official.video_links(blog_markup(), PRODUCT_TERMS)]
    assert urls.count("https://video.tv.adobe.com/v/3508101") == 1


# ---- reading each video page for its poster and title ----

def test_each_video_page_gives_its_poster_frame_and_title():
    videos = discovered()
    assert videos[RELIGHT]["poster"] == RELIGHT_POSTER
    assert videos[RELIGHT]["title"] == "Relight in Photoshop"
    assert videos[RELIGHT]["found_on"] == BLOG_URL
    assert videos[RESTYLE]["poster"] == RESTYLE_POSTER
    assert videos[RESTYLE]["title"] == "Generative Restyle in Photoshop"


def test_a_video_page_that_cannot_be_read_is_named_and_skipped():
    videos, notes = official.discover_videos([(BLOG_URL, blog_markup())], PRODUCT_TERMS, fetch=fixture_fetch)
    assert "https://video.tv.adobe.com/v/3508101" not in {v["url"] for v in videos}
    assert any("3508101" in note and "could not be read" in note for note in notes)


# ---- tagging each poster with the feature it shows ----

def test_each_poster_is_tagged_with_the_feature_in_its_title():
    videos = discovered()
    assert images.tag_feature(videos[RELIGHT], FEATURES) == "Relight"
    assert images.tag_feature(videos[RESTYLE], FEATURES) == "Generative Restyle"


def test_a_poster_for_another_feature_is_not_tagged_with_this_one():
    videos = discovered()
    assert images.tag_feature(videos[RESTYLE], ["Relight"]) == ""


def test_posters_are_saved_as_candidates_with_their_video_page_and_tag(tmp_path):
    videos = list(discovered().values())
    accepted, _ = images.gather_posters(videos, ADOBE_DOMAINS, tmp_path, FEATURES,
                                        fetch=lambda url: png_bytes(1920, 1080))
    by_image = {c.image_url: c for c in accepted}
    relight = by_image[RELIGHT_POSTER]
    assert relight.kind == "video poster"
    assert relight.feature == "Relight"
    assert relight.page == RELIGHT
    assert (tmp_path / relight.file).exists()
    assert by_image[RESTYLE_POSTER].feature == "Generative Restyle"


# ---- placing the posters on the slides ----

def _poster_candidates(tmp_path):
    videos = list(discovered().values())
    accepted, _ = images.gather_posters(videos, ADOBE_DOMAINS, tmp_path, FEATURES,
                                        fetch=lambda url: png_bytes(1920, 1080))
    return accepted


def _slots():
    return [
        image_pick.Slot("01", 1, "Cover: the product, PHOTOSHOP", "cover"),
        image_pick.Slot("02", 2, "Slide about: RELIGHT", "feature", "RELIGHT"),
        image_pick.Slot("03", 3, "Slide about: GENERATIVE RESTYLE", "feature", "GENERATIVE RESTYLE"),
    ]


def test_each_feature_slide_takes_the_poster_of_its_own_feature(tmp_path):
    candidates = _poster_candidates(tmp_path)
    choices, log = image_pick.pick_for_slots(_slots(), candidates, tmp_path, "official text", "Photoshop",
                                             lambda path, slot, text, name: PASS)
    assert choices["02"].feature == "Relight"
    assert choices["03"].feature == "Generative Restyle"
    # The test posters are PNG data, so pick_for_slots saves them as images/<slot>.png (the extension follows the file).
    assert (tmp_path / "images" / "02.png").exists()
    assert (tmp_path / "images" / "03.png").exists()
    placed = [line for line in log if "placed 02.png" in line][0]
    assert RELIGHT_POSTER in placed and RELIGHT in placed and "'Relight in Photoshop'" in placed


def test_the_cover_takes_the_best_general_image_before_any_poster(tmp_path):
    candidates = _poster_candidates(tmp_path)
    general = tmp_path / "candidates" / "c99.jpg"
    general.write_bytes(png_bytes(2400, 1350))
    candidates.append(Candidate(file="candidates/c99.jpg", page=BLOG_URL,
                                image_url="https://blog.adobe.com/hero.jpg", width=2400, height=1350, alt=""))
    choices, _ = image_pick.pick_for_slots(_slots(), candidates, tmp_path, "official text", "Photoshop",
                                           lambda path, slot, text, name: PASS)
    assert choices["01"].file == "candidates/c99.jpg"
    assert choices["02"].feature == "Relight"


def test_a_feature_slide_without_its_own_poster_gets_the_text_led_layout(tmp_path):
    # Only the Relight poster exists: the Restyle slide has no image of its own and must not borrow another one.
    candidates = [c for c in _poster_candidates(tmp_path) if c.feature == "Relight"]
    choices, log = image_pick.pick_for_slots(_slots(), candidates, tmp_path, "official text", "Photoshop",
                                             lambda path, slot, text, name: PASS)
    assert choices["03"] is None
    assert any(line.startswith("slide 03") and "text-led layout" in line for line in log)
    assert not list((tmp_path / "images").glob("03.*"))


# ---- slides never borrow another slide's image ----

def test_a_slide_without_an_image_does_not_borrow_another_slides_image(tmp_path):
    views = [{"type": "cover"}, {"type": "feature"}, {"type": "feature"}]
    (tmp_path / "02.jpg").write_bytes(b"x")
    slots, missing = carousel_render.slot_images(tmp_path, views)
    assert slots[0]["main"] is None and slots[2]["main"] is None
    assert slots[1]["main"].name == "02.jpg"
    assert "01.jpg" in missing and "03.jpg" in missing


def test_a_cover_with_its_own_image_is_not_changed(tmp_path):
    views = [{"type": "cover"}, {"type": "feature"}]
    (tmp_path / "01.jpg").write_bytes(b"x")
    slots, _ = carousel_render.slot_images(tmp_path, views)
    assert slots[0]["main"].name == "01.jpg"


# ---- the comparison title and the comparison layout ----

def test_the_comparison_title_is_set_on_two_lines_inside_the_margins():
    html_doc = carousel_render.gold_headline("EOS R8 MARK II vs EOS R8", 84, 200, 92, max_lines=2)
    assert "<br>vs" in html_doc
    assert 'data-max-lines="2"' in html_doc
    assert f'data-min-size="{carousel_render.COMPARISON_MIN_SIZE}"' in html_doc
    assert "width:952px" in html_doc and "left:64px" in html_doc


def test_the_comparison_blocks_stack_without_overlap():
    view = {"title": "EOS R8 MARK II vs EOS R8", "label": "Side-by-side comparison", "product": None,
            "rows": [{"new": "40 fps", "name": "Burst", "old": "6 fps"}]}
    html_doc = carousel_render.comparison_body(view, {"main": None, "old": None})
    # Round 13 (image first): title 84 to 234, label 240 to 276, pictures 292 to 692, table 720 to 1300,
    # footer from 1330. The literal positions below are the title, label and table boxes.
    for style in ("top:84px", "top:240px", "top:720px"):
        assert style in html_doc
    assert "height:150px" in html_doc and "height:580px" in html_doc
