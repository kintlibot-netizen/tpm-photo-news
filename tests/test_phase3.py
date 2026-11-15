"""Round 3 and Phase 3: edge margin on the ink, headline fitting, the Adobe index, the image check
decisions, the auto-carousel caps, review and posting, the personal Instagram block, and the dashboard view.

Nothing here calls Claude, the network or Meta. Browser checks run only when Playwright is installed.
"""
import copy
import csv
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import ROOT

import carousel
import carousel_auto
import carousel_plan
import carousel_render
import carousel_status
import dashboard
import design_check
import image_pick
import official_index
import review
import runlog
from images import Candidate

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
CAMERA = json.loads((ROOT / "fixtures" / "carousel" / "canon-eos-r8-mark-ii.json").read_text(encoding="utf-8"))
PHOTOSHOP = json.loads((ROOT / "fixtures" / "carousel" / "photoshop-2027.json").read_text(encoding="utf-8"))


# ---- A. edge margin on the ink ----

def box(**kw):
    base = {"name": "text", "text": "Hello", "left": 200, "right": 800, "top": 300, "bottom": 360,
            "lines": 1, "max_lines": 0, "size": 40}
    base.update(kw)
    return base


def test_ink_closer_than_56px_to_the_edge_fails():
    findings = design_check._measured(1, [box(left=40)])
    assert any(f["rule"] == "edge margin" and f["level"] == "FAIL" for f in findings)


def test_ink_at_56px_passes():
    assert design_check._measured(1, [box(left=56, right=1024)]) == []


def test_empty_text_is_never_measured_as_an_edge_problem():
    assert design_check._measured(1, [box(text="", left=0, right=1080, top=0, bottom=1440)]) == []


def test_fit_script_measures_text_nodes_and_skips_blank_ones():
    script = carousel_render.FIT_SCRIPT
    assert "createTreeWalker" in script and "trim()" in script and "getClientRects" in script
    assert "if (!text) return" in script


def test_headline_line_limit_is_reported_in_the_browser_box():
    findings = design_check._measured(2, [box(name="headline", lines=3, max_lines=2)])
    assert any(f["rule"] == "headline lines" and f["level"] == "FAIL" for f in findings)


# ---- B. headline fitting ----

def test_cover_splits_the_product_name_before_the_model_number():
    assert carousel_render.split_headline("CANON EOS R8 MARK II") == ["CANON EOS", "R8 MARK II"]


def test_model_tokens_are_joined_with_non_breaking_spaces():
    assert carousel_render.model_nbsp("R8 MARK II") == "R8 MARK II"
    assert " " not in carousel_render.model_nbsp("STABILIZATION")


def test_comparison_title_with_vs_is_two_lines_and_scales_down():
    # Changed in fix round 3: a title with " vs " is set as two lines (new model / vs old model), so it fits the margins.
    html_doc = carousel_render.gold_headline("EOS R8 MARK II vs EOS R8", 40, 120, 92, max_lines=1)
    assert 'data-max-lines="2"' in html_doc and "font-size:92px" in html_doc
    assert "<br>vs" in html_doc
    assert carousel_render.split_headline("EOS R8 MARK II vs EOS R8", "single") == ["EOS R8 MARK II vs EOS R8"]


def test_cover_headline_is_limited_to_two_lines():
    html_doc = carousel_render.headline_box("CANON EOS R8 MARK II", 226, 340, 160)
    assert 'data-max-lines="2"' in html_doc and "text-wrap:balance" not in html_doc
    assert ".headline{text-wrap:balance" in carousel_render.CSS


def test_stat_headlines_are_one_line():
    assert 'data-max-lines="1"' in carousel_render.headline_box("40 FPS", 200, 250, 196, mode="single", max_lines=1)


def test_design_check_counts_the_comparison_title_as_one_line():
    views = [{"type": "cover", "label": "NEW", "headline": "CANON EOS R8 MARK II", "product": None,
              "subline": None, "footer": "SWIPE"},
             {"type": "comparison", "label": "COMPARE", "title": "EOS R8 MARK II vs EOS R8", "rows": []}]
    findings = design_check.check_slides(views + views)
    assert not any(f["rule"] == "headline lines" and f["slide"] == 2 for f in findings)


# ---- C. the Adobe index ----

def test_excel_serial_day_becomes_a_date():
    assert official_index.excel_date(45000).date().isoformat() == "2023-03-15"
    assert official_index.excel_date(None) is None
    assert official_index.excel_date("2026-11-10").date().isoformat() == "2026-11-10"
    assert official_index.excel_date("not a date") is None


INDEX = {"data": [
    {"path": "/en/topics/photoshop-2027-release", "title": "Photoshop 2027 is here", "date": 46328},
    {"path": "/en/topics/photoshop-2026-tips", "title": "Photoshop 2026 tips", "date": 46328},
    {"path": "/en/topics/photoshop-2027-old-beta", "title": "Photoshop 2027 beta", "date": 45000},
    {"path": "/en/topics/photoshop-2027-undated", "title": "Photoshop 2027 notes"},
    {"path": "https://evil.example/x", "title": "Photoshop 2027", "date": 46328},
]}


def test_index_urls_are_built_from_the_base_and_path():
    posts = official_index.parse_index(INDEX, "https://blog.adobe.com")
    assert posts[0]["url"] == "https://blog.adobe.com/en/topics/photoshop-2027-release"
    assert all(p["url"].startswith("https://blog.adobe.com/") for p in posts)  # the absolute path is dropped


def test_newest_post_within_14_days_of_the_story_comes_first():
    posts = official_index.parse_index(INDEX, "https://blog.adobe.com")
    story_day = official_index.excel_date(46330)
    found = official_index.find_posts(posts, ["2027", "photoshop"], story_day, 14)
    assert found[0]["url"].endswith("photoshop-2027-release")
    assert all("2026" not in p["title"] for p in found)


def test_posts_outside_the_window_come_after_the_ones_inside_it():
    posts = official_index.parse_index(INDEX, "https://blog.adobe.com")
    story_day = official_index.excel_date(46330)
    found = official_index.find_posts(posts, ["2027", "photoshop"], story_day, 14)
    inside = [p for p in found if p["date"] is not None and abs((p["date"] - story_day).days) <= 14]
    outside = [p for p in found if p not in inside]
    assert inside and outside  # both kinds are present in this fixture
    assert found == inside + outside


def test_undated_posts_are_kept_but_never_ranked_as_recent():
    posts = official_index.parse_index(INDEX, "https://blog.adobe.com")
    found = official_index.find_posts(posts, ["2027", "photoshop"], official_index.excel_date(46330), 14)
    assert any(p["date"] is None for p in found)
    assert found[-1]["date"] is None or found[-1]["date"] <= found[0]["date"]


def test_helpx_403_counts_as_not_found(monkeypatch):
    class Refused:
        status_code = 403
        text = ""

    monkeypatch.setattr(official_index.requests, "get", lambda *a, **k: Refused())
    status, reason = official_index.helpx_status("https://helpx.adobe.com/photoshop/whats-new.html")
    assert status == "missing" and "403" in reason


def test_config_points_to_the_adobe_index_and_no_guessed_feeds():
    config = carousel.load_config()
    assert config["official_indexes"]["Adobe"]["url"] == "https://blog.adobe.com/en/query-index.json"
    assert "official_feeds" not in config


# ---- D. the image check ----

def test_verdict_parsing_requires_every_yes_no_answer():
    good = {k: v for k, v in zip(
        image_pick.REQUIRED_TRUE + image_pick.REQUIRED_FALSE,
        [True, True, True, False, False, False])}
    assert image_pick.parse_verdict(json.dumps(good))["unreadable"] is False
    missing = dict(good)
    del missing["has_watermark"]
    assert image_pick.parse_verdict(json.dumps(missing))["unreadable"] is True
    assert image_pick.parse_verdict("sorry, I cannot")["unreadable"] is True


def verdict(**overrides):
    base = {"matches_product": True, "is_real_photo_or_official_screenshot": True, "shows_slide_subject": True,
            "has_watermark": False, "has_people_as_subject": False, "looks_ai_generated": False,
            "notes": "", "unreadable": False}
    base.update(overrides)
    return base


def test_only_a_fully_passing_verdict_is_used():
    assert image_pick.decide(verdict())[0] is True


@pytest.mark.parametrize("field", ["matches_product", "is_real_photo_or_official_screenshot", "shows_slide_subject"])
def test_a_required_yes_that_is_no_rejects(field):
    assert image_pick.decide(verdict(**{field: False}))[0] is False


@pytest.mark.parametrize("field", ["has_watermark", "has_people_as_subject", "looks_ai_generated"])
def test_a_required_no_that_is_yes_rejects(field):
    assert image_pick.decide(verdict(**{field: True}))[0] is False


def test_unreadable_answer_rejects():
    assert image_pick.decide({"unreadable": True, "notes": "no json"})[0] is False


def cand(name, size=2400):
    return Candidate(file=f"candidates/{name}", page="https://www.canon.com/p", image_url=f"https://www.canon.com/{name}",
                     width=size, height=size, alt="")


def test_a_candidate_is_never_used_on_two_slides(tmp_path):
    (tmp_path / "candidates").mkdir()
    for name in ("c01.jpg", "c02.jpg"):
        (tmp_path / "candidates" / name).write_bytes(b"x")
    slots = [image_pick.Slot("01", 1, "cover"), image_pick.Slot("02", 2, "feature")]
    choices, log = image_pick.pick_for_slots(slots, [cand("c01.jpg", 2400), cand("c02.jpg", 2000)], tmp_path,
                                             "official text", "CANON EOS R8 MARK II",
                                             lambda p, s, t, n: verdict())
    assert choices["01"].file != choices["02"].file
    assert (tmp_path / "images" / "01.jpg").exists() and (tmp_path / "images" / "02.jpg").exists()
    assert any("USED" in line for line in log)


def test_the_next_candidate_is_tried_when_the_first_fails(tmp_path):
    (tmp_path / "candidates").mkdir()
    (tmp_path / "candidates" / "c01.jpg").write_bytes(b"x")
    (tmp_path / "candidates" / "c02.jpg").write_bytes(b"x")
    tried = []

    def verify(path, slot, text, product):
        tried.append(path.name)
        return verdict(has_watermark=True) if path.name == "c01.jpg" else verdict()

    choices, log = image_pick.pick_for_slots([image_pick.Slot("01", 1, "cover")],
                                             [cand("c01.jpg", 2400), cand("c02.jpg", 2000)], tmp_path,
                                             "text", "PRODUCT", verify)
    assert tried == ["c01.jpg", "c02.jpg"]
    assert choices["01"].file == "candidates/c02.jpg"
    assert any("rejected" in line and "has_watermark" in line for line in log)


def test_no_passing_candidate_keeps_the_placeholder_and_says_so(tmp_path):
    (tmp_path / "candidates").mkdir()
    (tmp_path / "candidates" / "c01.jpg").write_bytes(b"x")
    choices, log = image_pick.pick_for_slots([image_pick.Slot("01", 1, "cover")], [cand("c01.jpg")], tmp_path,
                                             "text", "PRODUCT", lambda *a: verdict(looks_ai_generated=True))
    assert choices["01"] is None
    assert not (tmp_path / "images" / "01.jpg").exists()
    assert any("brand glow" in line and "no empty box" in line for line in log)


def test_the_verifier_is_told_the_product_the_slide_and_the_path(tmp_path):
    prompt = image_pick.verifier_prompt(tmp_path / "candidates" / "c01.jpg",
                                        image_pick.Slot("02", 2, "Slide about: 40 FPS"), "official", "CANON EOS R8 MARK II")
    assert "Read tool" in prompt and "c01.jpg" in prompt
    assert "CANON EOS R8 MARK II" in prompt and "40 FPS" in prompt and "matches_product" in prompt


def test_a_comparison_has_two_image_slots():
    views = carousel_plan.build_views(_verified(CAMERA))
    names = [s.name for s in image_pick.slots_for(views)]
    assert "03" in names and "03-old" in names


def _verified(fixture):
    plan = carousel_plan.load_plan(copy.deepcopy(fixture["plan"]))
    carousel_plan.verify(plan, fixture["official_text"])
    return plan


# ---- E. the auto carousel after an alert ----

def stored_db(tmp_path):
    db = tmp_path / "seen.sqlite"
    runlog.connect(db).close()
    return db


def ok_result(folder):
    return {"folder": folder, "slides": 4, "confirmed": 9, "removed": [], "missing": ["02.jpg"],
            "placed": ["01.jpg"], "design": []}


def test_first_build_of_the_day_is_allowed(tmp_path):
    assert carousel_auto.may_build(stored_db(tmp_path), NOW) == (True, "within caps")


def test_one_build_a_day_is_the_daily_cap(tmp_path):
    db = stored_db(tmp_path)
    carousel_auto.record(db, 1, NOW, "ok", "f", "draft ready")
    allowed, reason = carousel_auto.may_build(db, NOW + timedelta(hours=1))
    assert allowed is False and "daily" in reason


def test_three_builds_in_a_week_is_the_weekly_cap(tmp_path):
    db = stored_db(tmp_path)
    for days_ago in (3, 5, 6):
        carousel_auto.record(db, days_ago, NOW - timedelta(days=days_ago), "ok", "f", "")
    allowed, reason = carousel_auto.may_build(db, NOW)
    assert allowed is False and "weekly" in reason


def test_builds_older_than_a_week_do_not_count(tmp_path):
    db = stored_db(tmp_path)
    for days_ago in (8, 9, 10):
        carousel_auto.record(db, days_ago, NOW - timedelta(days=days_ago), "ok", "f", "")
    assert carousel_auto.may_build(db, NOW)[0] is True


def test_a_successful_build_posts_a_ready_message(tmp_path):
    db = stored_db(tmp_path)
    sent = []
    outcomes = carousel_auto.after_alerts(db, [(7, "Adobe Releases Photoshop 27.1")], NOW, "https://hooks.slack.com/x",
                                          build=lambda sid: ok_result(tmp_path / "f"),
                                          notify=lambda text, url: sent.append((text, url)))
    assert outcomes[0].startswith("7: draft ready")
    text = sent[0][0]
    assert "Carousel draft ready" in text and "Facts: 9 confirmed, 0 removed" in text
    assert "Images missing (placeholder kept): 02.jpg" in text and "Nothing is posted" in text


def test_a_failed_build_says_why_and_never_raises(tmp_path):
    db = stored_db(tmp_path)
    sent = []

    def broken(sid):
        raise carousel.Refused("No official page for this story was found.")

    outcomes = carousel_auto.after_alerts(db, [(7, "Story")], NOW, "u", build=broken,
                                          notify=lambda text, url: sent.append(text))
    assert "failed" in outcomes[0]
    assert "Carousel not made" in sent[0] and "No official page" in sent[0]


def test_a_broken_slack_message_does_not_stop_anything(tmp_path):
    db = stored_db(tmp_path)

    def down(text, url):
        raise OSError("network down")

    outcomes = carousel_auto.after_alerts(db, [(7, "Story")], NOW, "u", build=lambda sid: ok_result(tmp_path),
                                          notify=down)
    assert outcomes[0].startswith("7: draft ready")


def test_the_daily_cap_skips_the_next_story_without_a_message(tmp_path):
    db = stored_db(tmp_path)
    sent = []
    carousel_auto.after_alerts(db, [(7, "A")], NOW, "u", build=lambda sid: ok_result(tmp_path),
                               notify=lambda text, url: sent.append(text))
    outcomes = carousel_auto.after_alerts(db, [(8, "B")], NOW, "u", build=lambda sid: ok_result(tmp_path),
                                          notify=lambda text, url: sent.append(text))
    assert "skipped" in outcomes[0] and len(sent) == 1


def test_a_story_is_built_only_once(tmp_path):
    db = stored_db(tmp_path)
    carousel_auto.after_alerts(db, [(7, "A")], NOW, "u", build=lambda sid: ok_result(tmp_path),
                               notify=lambda *a: None)
    later = NOW + timedelta(days=2)
    outcomes = carousel_auto.after_alerts(db, [(7, "A")], later, "u", build=lambda sid: ok_result(tmp_path),
                                          notify=lambda *a: None)
    assert outcomes == ["7: already built"]


def test_the_alert_message_is_escaped_for_slack(tmp_path):
    text = carousel_auto.ready_message("<!channel> Canon", ok_result(tmp_path))
    assert "<!channel>" not in text and "&lt;!channel&gt;" in text


# ---- F. review, approval and posting ----

def draft_folder(tmp_path, name="2026-11-11-photoshop-2027", design_fail=0):
    folder = tmp_path / name
    (folder / "images").mkdir(parents=True)
    for n in (1, 2):
        (folder / f"{n:02d}.png").write_bytes(b"png")
    (folder / "captions.txt").write_text(
        "DAVID MOLNAR FACEBOOK (first person)\nI'm excited to check this out! Relight an image.\n\n"
        "TPM FACEBOOK AND INSTAGRAM (we)\nWe're excited to check this out! New tools.\n", encoding="utf-8")
    carousel_status.write_build(folder, {"title": "Photoshop 2027", "slides": 2, "design_fail": design_fail,
                                         "design_summary": "Design check: passed, no findings."})
    return folder


def test_approval_records_who_and_when_and_makes_the_ready_folder(tmp_path):
    folder = draft_folder(tmp_path)
    ready = review.approve(folder, "David", NOW)
    status = carousel_status.read_status(folder)
    assert status["status"] == "approved" and status["approved_by"] == "David"
    assert status["approved_at"].startswith("2026-11-11")
    assert (ready / "01.png").exists() and (ready / "02.png").exists()
    assert (ready / "tpm-facebook.txt").read_text(encoding="utf-8").count("We're excited") == 1
    assert (ready / "tpm-instagram.txt").exists()
    assert "I'm excited" in (ready / "david-facebook.txt").read_text(encoding="utf-8")


def test_a_design_failure_cannot_be_approved(tmp_path):
    folder = draft_folder(tmp_path, design_fail=1)
    with pytest.raises(review.ReviewError, match="design check failed"):
        review.approve(folder, "David", NOW)


def test_approval_needs_a_name(tmp_path):
    with pytest.raises(review.ReviewError, match="--by"):
        review.approve(draft_folder(tmp_path), "  ", NOW)


def test_reject_records_the_reason(tmp_path):
    folder = draft_folder(tmp_path)
    review.reject(folder, "Too many words on slide 2", NOW)
    status = carousel_status.read_status(folder)
    assert status["status"] == "rejected" and status["reason"].startswith("Too many")


def test_posted_is_logged_to_the_csv_with_the_approval(tmp_path):
    folder = draft_folder(tmp_path)
    review.approve(folder, "David", NOW)
    log_path = tmp_path / "post-log.csv"
    review.log_post(folder, "tpm-facebook", "https://www.facebook.com/tpm/posts/1", NOW, log_path)
    with open(log_path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["account"] == "tpm-facebook" and rows[0]["approved_by"] == "David"
    assert rows[0]["url"].endswith("/1") and rows[0]["account_name"] == "TPM Facebook"
    assert carousel_status.read_status(folder)["status"] == "posted"


def test_only_approved_carousels_can_be_logged_as_posted(tmp_path):
    with pytest.raises(review.ReviewError, match="only an approved"):
        review.log_post(draft_folder(tmp_path), "tpm-facebook", "https://x.example/p", NOW, tmp_path / "l.csv")


def test_unknown_accounts_are_refused(tmp_path):
    folder = draft_folder(tmp_path)
    review.approve(folder, "David", NOW)
    with pytest.raises(review.ReviewError, match="not one of the accounts"):
        review.log_post(folder, "random-page", "https://x.example/p", NOW, tmp_path / "l.csv")


def test_posting_link_must_be_https(tmp_path):
    folder = draft_folder(tmp_path)
    review.approve(folder, "David", NOW)
    with pytest.raises(review.ReviewError, match="https"):
        review.log_post(folder, "tpm-facebook", "http://x.example/p", NOW, tmp_path / "l.csv")


@pytest.mark.parametrize("name", ["david-instagram", "David Molnar Instagram", "molnar_ig", "personal instagram"])
def test_davids_personal_instagram_is_blocked_by_name(name):
    with pytest.raises(review.ReviewError, match="blocked"):
        review.refuse_personal_instagram(name)


@pytest.mark.parametrize("name", ["tpm-instagram", "david-facebook", "TPM Facebook", "digital"])
def test_allowed_names_pass_the_personal_check(name):
    review.refuse_personal_instagram(name)


def test_the_personal_instagram_cannot_be_logged(tmp_path):
    folder = draft_folder(tmp_path)
    review.approve(folder, "David", NOW)
    with pytest.raises(review.ReviewError, match="blocked"):
        review.log_post(folder, "david-instagram", "https://www.instagram.com/x", NOW, tmp_path / "l.csv")


def test_the_configured_accounts_are_exactly_the_three_allowed():
    assert set(review.load_accounts()) == {"tpm-facebook", "tpm-instagram", "david-facebook"}


def test_rebuild_keeps_an_approved_status(tmp_path):
    folder = draft_folder(tmp_path)
    review.approve(folder, "David", NOW)
    carousel_status.write_build(folder, {"title": "Photoshop 2027", "slides": 3})
    assert carousel_status.read_status(folder)["status"] == "approved"


def test_review_readme_is_written_with_the_commands(tmp_path):
    folder = draft_folder(tmp_path)
    carousel_status.write_review_readme(folder, "Photoshop 2027", {"slides": 2, "missing": ["02.jpg"]})
    text = (folder / "README-for-review.txt").read_text(encoding="utf-8")
    assert "--approve" in text and "Missing images" in text and "02.jpg" in text


# ---- G. the dashboard's Carousels view ----

def test_dashboard_card_shows_status_facts_design_and_copy_buttons(tmp_path):
    folders = tmp_path / "carousels"
    folders.mkdir()
    folder = draft_folder(folders)
    review.approve(folder, "David", NOW)
    cards = dashboard.read_carousels(folders)
    html_doc = dashboard.carousels_panel(cards)
    assert "Approved by David" in html_doc
    assert "../output/carousels/2026-11-11-photoshop-2027/01.png" in html_doc
    assert "Design check: passed" in html_doc and "data-copy=" in html_doc
    assert "--approve output\\carousels\\2026-11-11-photoshop-2027" in html_doc


def test_dashboard_without_carousels_keeps_the_placeholder(tmp_path):
    assert "Coming in Phase 2" in dashboard.carousels_panel([])


def test_dashboard_card_status_words_for_each_state(tmp_path):
    base = {"name": "x", "build": {}, "slides": [], "approved_by": "", "approved_at": "", "reason": "",
            "posts": []}
    assert dashboard._carousel_state(dict(base, status="draft"))[0] == "Draft, waiting for review"
    assert dashboard._carousel_state(dict(base, status="rejected", reason="words"))[0] == "Rejected: words"
    posted = dict(base, status="posted", posts=[{"account": "tpm-instagram"}])
    assert dashboard._carousel_state(posted)[0] == "Posted to tpm-instagram"


# ---- H. browser checks (skipped when Playwright is not installed) ----

def test_camera_sample_renders_with_no_design_failures(tmp_path):
    pytest.importorskip("playwright.sync_api")
    plan = _verified(CAMERA)
    views = carousel_plan.build_views(plan)
    slots = [{"main": None, "old": None} for _ in views]
    font_dir = ROOT / "assets" / "fonts"
    documents = [carousel_render.slide_document(v, s, font_dir if font_dir.exists() else None)
                 for v, s in zip(views, slots)]
    out = [tmp_path / f"{n:02d}.png" for n in range(1, len(views) + 1)]
    measure_log: list = []
    problems = carousel_render.render_pngs(documents, out, tmp_path / "work", measure_log=measure_log)
    assert problems == []
    captions = {who: carousel_plan.build_caption(plan, who) for who in ("david", "tpm")}
    findings = design_check.run_design_check(views, captions, measure_log)
    assert not design_check.has_failures(findings), findings


def test_photoshop_sample_renders_with_no_design_failures(tmp_path):
    pytest.importorskip("playwright.sync_api")
    plan = _verified(PHOTOSHOP)
    views = carousel_plan.build_views(plan)
    slots = [{"main": None, "old": None} for _ in views]
    documents = [carousel_render.slide_document(v, s, None) for v, s in zip(views, slots)]
    out = [tmp_path / f"{n:02d}.png" for n in range(1, len(views) + 1)]
    measure_log: list = []
    carousel_render.render_pngs(documents, out, tmp_path / "work", measure_log=measure_log)
    captions = {who: carousel_plan.build_caption(plan, who) for who in ("david", "tpm")}
    assert not design_check.has_failures(design_check.run_design_check(views, captions, measure_log))


def test_sample_writes_status_and_review_readme(tmp_path, monkeypatch):
    monkeypatch.setattr(carousel, "SAMPLE_ROOT", tmp_path)
    carousel.run_sample("camera", render=False)
    folder = tmp_path / "2026-11-11-canon-eos-r8-mark-ii-sample"
    assert carousel_status.read_status(folder)["status"] == "draft"
    assert (folder / "README-for-review.txt").exists()
