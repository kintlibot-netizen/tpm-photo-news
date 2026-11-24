"""Round 8: the false NO IMAGE warning for a collage cover, honest wording now the carousel bot and Claude are off,
and end to end checks of the features that had no single test. No network, no Claude, no browser."""
import re

import alert
import carousel
import carousel_status
import dashboard
import review
from classify import OFFICIAL, Review
from test_alert_and_run import no_claude_story
from test_carousel import FIXTURE, fresh_data
from test_phase3_fix3b import png_bytes
from test_round7_downloads import PASSING, carousel as make_folder

DASH = ("—", "–")


def test_a_collage_cover_is_not_reported_as_missing_an_image(tmp_path):
    out = tmp_path / "2026-11-11-photoshop-2027"
    (out / "images").mkdir(parents=True)
    for n in (2, 3, 4):
        (out / "images" / f"{n:02d}.png").write_bytes(png_bytes(1920, 1080))
    result = carousel.assemble(
        fresh_data()["plan"], title=FIXTURE["title"], official_text=FIXTURE["official_text"], verdicts=None,
        out_dir=out, official_url="https://example.invalid/page", article_links=[], press_images=False,
        render=False, checked_on="2026-11-11")
    assert result["missing"] == []  # slide 1 is a collage of 02, 03 and 04, so it has official images
    assert "01.jpg: missing" not in (out / "sources.md").read_text(encoding="utf-8")
    card = {"build": {"missing": ["01.jpg", "03.jpg"], "cover_collage": True}, "slides": ["01.png"] * 4}
    assert dashboard.slides_without_image(card) == [3]  # the dashboard tag follows the same rule


def test_the_alert_has_no_claude_line_and_no_dash():
    text = alert.format_alert(no_claude_story(), OFFICIAL, Review(True, "camera", "A summary.", False), "new")
    assert "Claude" not in text and not any(d in text for d in DASH)


def test_dashboard_wording_matches_the_flow_of_today(tmp_path):
    from test_round7_dashboard import build
    plain = re.sub(r"<(script|style)\b.*?</\1>", " ", build(tmp_path), flags=re.S)
    for stale in ("carousel bot", "Claude did not review", "Matched by the free rules only", "Sync with cloud"):
        assert stale not in plain, stale
    assert "reviewed by Kint" in plain.replace("\n", " ") or "Kint reviews" in plain
    assert not any(d in plain for d in DASH)


def test_the_waiting_words_are_plain_and_name_no_bot():
    words = carousel_status.WAITING_WORDS
    assert "by hand" in words and "bot" not in words.lower() and not any(d in words for d in DASH)


def test_every_status_chip_renders_in_both_copies(tmp_path):
    from test_round7_dashboard import NOW, build
    base = tmp_path / "carousels"
    waiting = make_folder(base, name="2026-11-11-waiting")
    approved = make_folder(base, name="2026-11-12-approved")
    carousel_status.set_status(approved, "approved", approved_by="David", approved_at=NOW.isoformat())
    rejected = make_folder(base, name="2026-11-10-rejected")
    carousel_status.set_status(rejected, "rejected", reason="Wrong product")
    posted = make_folder(base, name="2026-11-09-posted")
    carousel_status.set_status(posted, "posted", posts=[{"account": "tpm-facebook"}])
    make_folder(base, name="2026-11-08-draft", build=dict(PASSING, fact_check_passed=False))
    assert waiting.exists()
    for mode in ("local", "share"):
        page = build(tmp_path, carousels_dir=base, mode=mode)
        for chip in ("Waiting for David", "Approved by David", "Rejected: Wrong product", "Posted to tpm-facebook",
                     "Draft, waiting for review"):
            assert chip in page, (mode, chip)


def test_david_instagram_is_refused_and_posted_needs_approval(tmp_path):
    import pytest
    folder = make_folder(tmp_path, name="2026-11-11-x")
    from test_round6_status import NOW
    with pytest.raises(review.ReviewError):
        review.log_post(folder, "david-instagram", "https://example.com/p", NOW, tmp_path / "post-log.csv")
