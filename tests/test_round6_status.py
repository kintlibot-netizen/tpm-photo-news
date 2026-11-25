"""Functional round, items 6 and 7: the Waiting for David status, samples that can't be approved or logged,
and the dashboard's split between real drafts and samples."""
import html
from datetime import datetime, timezone

import pytest

import carousel_status
import dashboard
import review

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
PASSING = {"title": "Photoshop 2027", "slides": 2, "fact_check_passed": True, "lint_passed": True,
           "design_fail": 0, "design_summary": "Design check: passed, no findings."}


def folder_with(base, name="2026-11-11-photoshop-2027"):
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "captions.txt").write_text(
        "DAVID MOLNAR FACEBOOK (first person)\nI'm excited.\n\nTPM FACEBOOK AND INSTAGRAM (we)\nWe're excited.\n",
        encoding="utf-8")
    return folder


def test_a_draft_that_passes_fact_and_design_checks_waits_for_david(tmp_path):
    folder = folder_with(tmp_path)
    carousel_status.write_build(folder, PASSING)
    assert carousel_status.read_status(folder)["status"] == "waiting_for_david"


def test_a_failed_design_check_stays_a_draft(tmp_path):
    folder = folder_with(tmp_path)
    carousel_status.write_build(folder, dict(PASSING, design_fail=1))
    assert carousel_status.read_status(folder)["status"] == "draft"


def test_a_text_that_did_not_fit_stays_a_draft(tmp_path):
    folder = folder_with(tmp_path)
    carousel_status.write_build(folder, dict(PASSING, lint_passed=False))
    assert carousel_status.read_status(folder)["status"] == "draft"


def test_a_rebuild_that_fails_sends_a_waiting_draft_back_to_draft(tmp_path):
    folder = folder_with(tmp_path)
    carousel_status.write_build(folder, PASSING)
    carousel_status.write_build(folder, dict(PASSING, design_fail=2))
    assert carousel_status.read_status(folder)["status"] == "draft"


def test_samples_stay_drafts_even_when_they_pass(tmp_path):
    folder = folder_with(tmp_path, name="2026-11-11-canon-eos-r8-mark-ii-sample")
    carousel_status.write_build(folder, dict(PASSING, sample=True))
    assert carousel_status.read_status(folder)["status"] == "draft"


def test_a_reviewed_status_is_kept_on_rebuild(tmp_path):
    folder = folder_with(tmp_path)
    carousel_status.write_build(folder, PASSING)
    review.approve(folder, "Kint", NOW)
    carousel_status.write_build(folder, PASSING)
    assert carousel_status.read_status(folder)["status"] == "approved"


def test_waiting_for_david_can_be_approved(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CAROUSELS", tmp_path)
    folder = folder_with(tmp_path)
    carousel_status.write_build(folder, PASSING)
    review.approve(folder, "David", NOW)
    assert carousel_status.read_status(folder)["status"] == "approved"


def test_review_list_shows_waiting_for_david(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CAROUSELS", tmp_path)
    carousel_status.write_build(folder_with(tmp_path), PASSING)
    rows = review.list_folders()
    assert any("[Waiting for David]" in row for row in rows)


def test_the_dashboard_shows_waiting_for_david(tmp_path):
    folder_with(tmp_path)
    carousel_status.write_build(tmp_path / "2026-11-11-photoshop-2027", PASSING)
    cards = dashboard.read_carousels(tmp_path)
    page = dashboard.carousels_panel(cards)
    assert "Waiting for David" in page


@pytest.mark.parametrize("name, title", [
    ("2026-11-11-canon-sample", "Canon sample"),
    ("2026-11-11-photoshop-2027", "SAMPLE: Photoshop 2027"),
])
def test_a_sample_by_name_or_by_title_cannot_be_approved(tmp_path, monkeypatch, name, title):
    monkeypatch.setattr(review, "CAROUSELS", tmp_path)
    folder = folder_with(tmp_path, name=name)
    carousel_status.write_build(folder, dict(PASSING, title=title))
    with pytest.raises(review.ReviewError, match="sample"):
        review.approve(folder, "Kint", NOW)


def test_a_sample_cannot_be_logged_as_posted(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CAROUSELS", tmp_path)
    monkeypatch.setattr(review, "POST_LOG", tmp_path / "post-log.csv")
    folder = folder_with(tmp_path, name="2026-11-11-canon-eos-r8-mark-ii-sample")
    carousel_status.write_build(folder, PASSING)
    carousel_status.set_status(folder, "approved", approved_by="Kint", approved_at="2026-11-11T12:00:00+00:00")
    with pytest.raises(review.ReviewError, match="sample"):
        review.log_post(folder, "tpm-facebook", "https://example.com/post", NOW, tmp_path / "post-log.csv")


def test_real_folders_are_listed_and_sample_folders_are_left_off_the_dashboard(tmp_path):
    real_base = tmp_path / "carousels"
    sample_base = tmp_path / "samples"
    folder_with(real_base)
    carousel_status.write_build(real_base / "2026-11-11-photoshop-2027", PASSING)
    folder_with(sample_base, name="2026-11-11-canon-eos-r8-mark-ii-sample")
    carousel_status.write_build(sample_base / "2026-11-11-canon-eos-r8-mark-ii-sample", dict(PASSING, sample=True))
    cards = dashboard.read_carousels(real_base, sample_base)
    assert {card["name"]: card["kind"] for card in cards} == {"2026-11-11-photoshop-2027": "draft"}
    page = dashboard.carousels_panel(cards)
    assert 'data-kind="sample"' not in page and 'data-kind="draft"' in page
    assert "Samples are for checking the layout" not in page


def test_an_old_sample_folder_in_the_real_folder_is_not_shown(tmp_path):
    folder_with(tmp_path, name="2026-11-11-photoshop-2027-sample")
    assert dashboard.read_carousels(tmp_path) == []
