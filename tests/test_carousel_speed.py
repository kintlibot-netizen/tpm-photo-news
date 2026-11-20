"""Carousel round (Nov 20): faster builds and the closing call to action slide. No network, no Claude, no browser."""
import copy
import json
import struct
import threading
import zlib
from datetime import datetime, timezone

import pytest
from conftest import ROOT

import border_trim
import carousel
import carousel_plan
import carousel_render
import carousel_status
import claude_cache
import classify
import design_check
import downloads
import image_pick
import images
import official
import timing
from images import Candidate

FIXTURE = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))
DOMAINS = ["adobe.com", "blog.adobe.com"]
GOOD_IMAGE = json.dumps({"matches_product": True, "is_real_photo_or_official_screenshot": True,
                         "shows_slide_subject": True, "has_watermark": False, "has_people_as_subject": False,
                         "looks_ai_generated": False, "notes": "ok"})


def png(width: int, height: int) -> bytes:
    """A tiny but valid PNG header with the given size (enough for images.image_dimensions)."""
    header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return header + struct.pack(">I", zlib.crc32(header[12:29])) + b"\x00" * 64


def plan():
    return carousel_plan.load_plan(copy.deepcopy(FIXTURE["plan"]))


# ---- timing ----

def test_the_clock_times_each_step_and_writes_a_line_to_the_run_log(caplog):
    ticks = iter([0.0, 1.0, 3.5, 4.0, 10.0, 12.0])
    clock = timing.Clock("story 7", echo=False, now=lambda: next(ticks))
    with caplog.at_level("INFO", logger="watcher"):
        with clock.step("fact check"):
            pass
        with clock.step("render slides"):
            pass
    assert clock.steps == {"fact check": 2.5, "render slides": 6.0}
    assert "Timing: story 7: fact check took 2.5 s" in caplog.text
    assert clock.as_dict() == {"fact check": 2.5, "render slides": 6.0, "total": 12.0}


# ---- Claude answers are remembered ----

def test_the_reply_cache_survives_a_restart_and_ignores_a_broken_file(tmp_path):
    path = tmp_path / "cache" / "folder.json"
    cache = claude_cache.ReplyCache(path)
    key = claude_cache.key_for("sonnet", "prompt", b"image")
    assert cache.get(key) is None
    cache.put(key, "reply")
    assert claude_cache.ReplyCache(path).get(key) == "reply"
    assert claude_cache.key_for("sonnet", "prompt", b"other image") != key
    path.write_text("not json", encoding="utf-8")
    assert claude_cache.ReplyCache(path).get(key) is None


def test_a_rebuild_does_not_ask_claude_to_fact_check_the_same_claims_again(tmp_path, monkeypatch):
    calls = []
    current = plan()
    facts = list(carousel_plan.iter_facts(current))
    reply = json.dumps([{"id": f["id"], "verdict": "CONFIRMED", "quote": ""} for f in facts])
    monkeypatch.setattr(classify, "ask_claude", lambda prompt, model, timeout=0: calls.append(prompt) or reply)
    cache = claude_cache.ReplyCache(tmp_path / "c.json")
    first = carousel.factcheck_with_claude(current, FIXTURE["official_text"], "sonnet", cache=cache)
    again = carousel.factcheck_with_claude(current, FIXTURE["official_text"], "sonnet",
                                           cache=claude_cache.ReplyCache(tmp_path / "c.json"))
    assert first == again and len(calls) == 1
    carousel.factcheck_with_claude(current, FIXTURE["official_text"] + " Changed.", "sonnet", cache=cache)
    assert len(calls) == 2  # the official text changed: Claude is asked again
    carousel.factcheck_with_claude(current, FIXTURE["official_text"], "sonnet")
    assert len(calls) == 3  # no cache given: the old behaviour


def test_an_image_check_is_remembered_only_when_it_was_read(tmp_path, monkeypatch):
    image = tmp_path / "c01.png"
    image.write_bytes(png(1920, 1080))
    slot = image_pick.Slot("02", 2, "Slide about: RELIGHT", "feature", "RELIGHT")
    answers = iter(["not json", GOOD_IMAGE, "should not be asked"])
    calls = []
    monkeypatch.setattr(classify, "ask_claude_read",
                        lambda prompt, model, folder, timeout=0: calls.append(1) or next(answers))
    cache = claude_cache.ReplyCache(tmp_path / "c.json")
    assert carousel.verify_image(image, slot, "text", "Photoshop", "sonnet", cache=cache)["unreadable"]
    assert not carousel.verify_image(image, slot, "text", "Photoshop", "sonnet", cache=cache)["unreadable"]
    assert not carousel.verify_image(image, slot, "text", "Photoshop", "sonnet", cache=cache)["unreadable"]
    assert len(calls) == 2  # the unreadable answer was asked again; the good one was reused
    image.write_bytes(png(2000, 1125))  # a different picture under the same name is checked afresh
    carousel.verify_image(image, slot, "text", "Photoshop", "sonnet", cache=cache)
    assert len(calls) == 3


# ---- the image checks run side by side, with the same result ----

def candidates():
    return [Candidate(file=f"candidates/c0{n}.png", page="https://blog.adobe.com/p", image_url=f"https://blog.adobe.com/{n}.png",
                      width=1920, height=1080, alt="", feature=feature, title=feature, kind="video poster")
            for n, feature in ((1, "RELIGHT"), (2, "QUICK COMPARE"), (3, ""))]


def slots():
    return [image_pick.Slot("01", 1, "Cover: Photoshop", "cover"),
            image_pick.Slot("02", 2, "Slide about: RELIGHT", "feature", "RELIGHT"),
            image_pick.Slot("03", 3, "Slide about: QUICK COMPARE", "feature", "QUICK COMPARE")]


def setup_files(folder):
    (folder / "candidates").mkdir(parents=True)
    for n in (1, 2, 3):
        (folder / "candidates" / f"c0{n}.png").write_bytes(png(1920, 1080))


def test_parallel_image_checks_pick_exactly_what_the_one_at_a_time_checks_pick(tmp_path):
    good = image_pick.parse_verdict(GOOD_IMAGE)
    results = {}
    for workers in (1, 3):
        folder = tmp_path / f"w{workers}"
        setup_files(folder)
        calls, lock = [], threading.Lock()

        def verify(path, slot, text, name):
            with lock:
                calls.append((path.name, slot.name))
            return dict(good)

        choices, log = image_pick.pick_for_slots(slots(), candidates(), folder, "text", "Photoshop", verify,
                                                 workers=workers)
        results[workers] = ({k: (v.file if v else None) for k, v in choices.items()},
                            [line for line in log if "USED" in line or "rejected" in line], sorted(calls))
    assert results[1] == results[3]
    assert len(results[3][2]) == len(set(results[3][2]))  # no candidate was checked twice for the same slide


def test_the_first_checks_are_one_per_slide_and_skip_the_covers_duplicate():
    jobs = image_pick.first_checks(slots()[1:] + slots()[:1], candidates())
    assert [(c.file, s.name) for c, s in jobs] == [("candidates/c01.png", "02"), ("candidates/c02.png", "03"),
                                                   ("candidates/c03.png", "01")]
    assert jobs[0][1].demo == "RELIGHT"  # a feature's own demo poster is checked as a demo, as in the pick


# ---- downloads side by side, one browser for all poster trims ----

def page_with_images(count):
    tags = "".join(f'<img src="https://blog.adobe.com/media/{n}.png" alt="Relight in Photoshop {n}" '
                   'width="2000" height="1125">' for n in range(count))
    return [("https://blog.adobe.com/post", f"<html><body>{tags}</body></html>")]


def test_parallel_downloads_keep_the_page_order_and_the_same_candidates(tmp_path, monkeypatch):
    def fetch(url):
        if url.endswith("3.png"):
            raise images.requests.RequestException("refused")
        return png(2000, 1125)

    monkeypatch.setattr(images, "DOWNLOAD_WORKERS", 1)
    one, one_rejected = images.gather(page_with_images(5), DOMAINS, tmp_path / "a", fetch=fetch)
    monkeypatch.setattr(images, "DOWNLOAD_WORKERS", 6)
    many, many_rejected = images.gather(page_with_images(5), DOMAINS, tmp_path / "b", fetch=fetch)
    assert [c.image_url for c in one] == [c.image_url for c in many] and len(many) == 4
    assert one_rejected == many_rejected and "could not be downloaded" in many_rejected[0]["reason"]
    assert [c.file for c in many] == [f"candidates/c0{n}.png" for n in range(1, 5)]


def test_every_poster_is_trimmed_in_one_batch(tmp_path):
    batches = []

    def trim(data):
        raise AssertionError("the batch version must be used")

    trim.many = lambda datas: batches.append(len(datas)) or [(d, {"trimmed": False}) for d in datas]
    videos = [{"url": f"https://video.tv.adobe.com/v/{n}", "poster": f"https://images-tv.adobe.com/{n}.png",
               "title": "PS Relight", "found_on": "https://blog.adobe.com/post"} for n in range(4)]
    accepted, rejected = images.gather_posters(videos, ["adobe.com"], tmp_path, ["RELIGHT"],
                                               fetch=lambda url: png(1920, 1080), trim=trim)
    assert batches == [4] and len(accepted) == 4 and not rejected
    assert [c.file for c in accepted] == [f"candidates/c0{n}.png" for n in range(1, 5)]


def test_border_trim_offers_its_batch_version():
    assert border_trim.trim_border.many is border_trim.trim_many
    assert images.trim_all(None, [b"a", b"b"]) == [None, None]
    assert images.trim_all(lambda d: (d, {}), [b"a"]) == [(b"a", {})]


# ---- an official page is read once ----

def test_the_page_cache_reads_a_page_once_and_does_not_retry_a_refused_page(tmp_path, monkeypatch):
    plain, browser = [], []

    def fake_plain(url):
        plain.append(url)
        if "helpx" in url:
            raise images.requests.HTTPError("403")
        return "<html>post</html>"

    def fake_browser(url):
        browser.append(url)
        raise official.PageUnreadable("HTTP 403 in the browser")

    monkeypatch.setattr(official, "fetch_html_plain", fake_plain)
    monkeypatch.setattr(official, "fetch_html_browser", fake_browser)
    official.enable_page_cache(tmp_path / "pages", 6)
    try:
        assert official.fetch_html("https://blog.adobe.com/post") == "<html>post</html>"
        assert official.fetch_html("https://blog.adobe.com/post") == "<html>post</html>"
        for _ in range(2):
            with pytest.raises(official.PageUnreadable):
                official.fetch_html("https://helpx.adobe.com/x.html")
        assert plain.count("https://blog.adobe.com/post") == 1 and len(browser) == 1
        official.enable_page_cache(tmp_path / "pages", 6)  # a new run: read back from disk, not fetched again
        assert official.fetch_html("https://blog.adobe.com/post") == "<html>post</html>"
        assert plain.count("https://blog.adobe.com/post") == 1
    finally:
        official.disable_page_cache()
    assert official.fetch_html("https://blog.adobe.com/post") == "<html>post</html>"  # off: fetched as before
    assert plain.count("https://blog.adobe.com/post") == 2


# ---- the closing call to action slide ----

def views_with(features: int, price: bool = False):
    views = [{"type": "cover", "headline": "PHOTOSHOP 2027"}]
    views += [{"type": "feature", "headline": f"FEATURE {n}"} for n in range(features)]
    if price:
        views.append({"type": "price"})
    return views


def test_the_closing_slide_recaps_the_features_and_states_no_fact():
    view = carousel_plan.closing_view(views_with(3), design_check.MAX_SLIDES)
    assert view["type"] == "closing" and view["headline"] == "WHICH ONE WOULD YOU TRY FIRST?"
    assert view["features"] == ["FEATURE 0", "FEATURE 1", "FEATURE 2"]
    assert view["cta"] == "SAVE THIS POST. SHARE YOUR TAKE." and view["footer"] == "THE PHOTO MENTORSHIP"
    assert carousel_plan.closing_view(views_with(1), 7)["headline"] == "WOULD YOU USE THIS?"


def test_no_closing_slide_after_a_price_slide_at_the_limit_or_without_features():
    assert carousel_plan.closing_view(views_with(2, price=True), 7) is None  # the price slide has its own CTA
    assert carousel_plan.closing_view(views_with(6), 7) is None  # already 7 slides
    assert carousel_plan.closing_view(views_with(0), 7) is None


def test_the_closing_slide_keeps_the_safe_margins_the_pill_and_the_footer():
    view = carousel_plan.closing_view(views_with(4), 7)
    html = carousel_render.closing_body(view, {"main": None, "old": None})
    assert "SAVE THIS POST. SHARE YOUR TAKE." in html and "THE PHOTO MENTORSHIP" in html and "<img" not in html
    assert 'data-safe-left="64" data-safe-right="1016"' in html and "In this post" in html
    assert carousel_render.slide_layout(view) == {"pill_top": carousel_render.PILL_TOP,
                                                  "footer_top": carousel_render.FOOTER_TOP}
    assert carousel_render.template_key(view) == "closing"
    findings = design_check.check_slides(views_with(4)[:1] + [dict(v, label="NEW", template="left_body",
                                                                   accent="X") for v in views_with(4)[1:]] + [view])
    assert not [f for f in findings if f["level"] == "FAIL"]
    assert "—" not in html and "–" not in html
    assert carousel_render.slot_images(ROOT / "nowhere", [view]) == ([{"main": None, "old": None}], [])


def test_a_build_ends_with_the_closing_slide_and_names_it_in_the_zip(tmp_path):
    data = copy.deepcopy(FIXTURE)
    loaded = carousel_plan.load_plan(copy.deepcopy(data["plan"]))
    carousel_plan.verify(loaded, data["official_text"], None)
    base = carousel_plan.build_views(loaded)
    expected = carousel_plan.closing_view(base, design_check.MAX_SLIDES)
    try:
        result = carousel.assemble(
            data["plan"], title=data["title"], official_text=data["official_text"], verdicts=None, out_dir=tmp_path,
            official_url="https://example.invalid/page", article_links=[], press_images=False, render=False,
            checked_on="2026-11-20", closing=True, clock=timing.Clock("t", echo=False))
        slides = result["slides"]
    except carousel.DesignFailed:
        slides = carousel_status.read_status(tmp_path)["build"]["slides"]
    build = carousel_status.read_status(tmp_path)["build"]
    assert slides == len(base) + (1 if expected else 0)
    assert build.get("closing", False) == bool(expected) and "render slides (one browser for all)" not in build["timings"]
    assert "design check" in build["timings"] and "total" in build["timings"]
    if expected:
        assert downloads.slide_labels(tmp_path)[-1] == "your-take"  # the zip names it NN-your-take.png


def test_the_config_turns_on_the_speedups_and_the_closing_slide():
    config = carousel.load_config()
    assert config["closing_slide"] is True and config["image_check_workers"] == 3 and config["page_cache_hours"] == 6
