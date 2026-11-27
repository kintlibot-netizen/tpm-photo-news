"""A feature carousel (Nov 27): a plan with its own "title" makes a second preview of one story about one feature
(Lightroom Glow from the Lightroom release story) in its own folder, so the story's main preview is kept. Temporary
folders only: no Claude, no Slack, no git, no network."""
import json
from pathlib import Path

import pytest
from test_plan_build import FIXTURE, build, offline_story, write_plan  # noqa: F401  (offline_story is a fixture)

import carousel
import carousel_status
import official
import plan_build

GLOW_TITLE = "Lightroom Classic adds Glow: Bloom, Halation, Diffusion, Motion and Streak"


def test_the_title_is_a_build_field_and_stays_out_of_plan_json():
    plan, meta = plan_build.split_input({"story": 2, "title": GLOW_TITLE, **FIXTURE["plan"]})
    assert "title" not in plan and meta["title"] == GLOW_TITLE
    assert plan_build.feature_title(meta) == GLOW_TITLE
    assert plan_build.feature_title({}) is None


@pytest.mark.parametrize("bad", ["Too short", "x" * 120, "Lightroom Classic \u2014 Glow is here now",
                                 "Lightroom Classic - Glow is here now"])
def test_a_bad_title_stops_the_build(bad):
    with pytest.raises(plan_build.PlanInputError, match="title"):
        plan_build.feature_title({"title": bad})


def test_a_feature_carousel_gets_its_own_preview_folder_and_title(tmp_path, offline_story, isolated_activity_log):
    main = Path(build(tmp_path, offline_story, write_plan(tmp_path))["folder"])
    feature = build(tmp_path, offline_story, write_plan(tmp_path, title=GLOW_TITLE))
    folder = Path(feature["folder"])
    assert folder.parent == main.parent and folder.name != main.name
    assert folder.name.endswith("lightroom-classic-adds-glow-bloom-halation-diffusion-motion")
    assert main.exists() and (main / "captions.txt").exists()  # the story's own preview is kept
    assert feature["title"] == GLOW_TITLE
    assert carousel_status.read_status(folder)["build"]["title"] == GLOW_TITLE
    assert "feature carousel of story 72" in (folder / "sources.md").read_text(encoding="utf-8")
    assert "title" not in json.loads((folder / "plan.json").read_text(encoding="utf-8"))


def test_a_feature_carousel_is_a_preview_only(tmp_path, offline_story):
    with pytest.raises(carousel.Refused, match="preview only"):
        build(tmp_path, offline_story, write_plan(tmp_path, title=GLOW_TITLE), dry_run=False)


def test_official_pages_are_read_with_the_headers_chrome_sends():
    headers = official.PAGE_HEADERS
    assert headers["User-Agent"].startswith("Mozilla/5.0") and "Chrome/" in headers["User-Agent"]
    assert headers["Sec-Fetch-Mode"] == "navigate" and headers["Sec-Fetch-Dest"] == "document"
    assert headers["Upgrade-Insecure-Requests"] == "1"
