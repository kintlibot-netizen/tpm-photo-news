"""Round 7, section A and B on the page: the app shell, the Activity page, "Last check" and "Next check at", the
pipeline, the carousel gallery with downloads, and David's read only mode. Temporary data only."""
import html
import re
from datetime import datetime, timedelta, timezone

import pytest
from conftest import ROOT
from test_dashboard import SECRET_TOKEN, SECRET_URL, sample_db

import activity
import carousel_status
import dashboard
import downloads
import runlog
import schedule_info
from test_round7_downloads import PASSING, carousel

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def build(tmp_path, db=None, carousels_dir=None, mode="local", **kwargs):
    page, _ = dashboard.build_page(
        db_path=db or tmp_path / "none.sqlite", sources_path=ROOT / "config" / "sources.yaml",
        rules_path=ROOT / "config" / "rules.yaml", now=NOW, carousels_dir=carousels_dir or tmp_path / "carousels",
        samples_dir=tmp_path / "samples", mode=mode, **kwargs)
    return page


def text_of(page: str) -> str:
    """The visible words of the page (tags, styles and scripts removed)."""
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


# ---- the app shell ----

def test_the_sidebar_lists_every_section_in_the_readme_order(tmp_path):
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    nav = re.findall(r'data-nav="([a-z]+)" data-label="([^"]+)"', page)
    assert [label for _, label in nav] == ["Start here", "Overview", "Needs your attention", "Stories", "Carousels",
                                           "Activity", "Sources", "How it works"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Dashboard sections", 1)[1].split("\n## ", 1)[0]
    missing = [label for _, label in nav if f"**{label}**" not in section]
    assert not missing, f"README Dashboard sections does not name: {missing}"
    positions = [section.index(f"**{label}**") for _, label in nav]
    assert positions == sorted(positions)
    for key, _ in nav:
        assert f'data-page="{key}"' in page


def test_kints_page_is_the_restored_pre_g_layout(tmp_path):
    """Restore round: no Advanced area, no "To review" or "News" labels; Kint's page opens on the Overview."""
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    assert 'data-home="overview"' in page and 'class="adv"' not in page and "start-steps" not in page
    assert "Photo news in, ready to post carousels out" in page and "Needs attention now" in page
    assert "The steps in plain words" in page and "The rules that never change" in page


def test_the_top_bar_says_when_the_last_and_next_check_are_and_if_the_watcher_is_well(tmp_path, monkeypatch):
    db = sample_db(tmp_path / "seen.sqlite")
    page = build(tmp_path, db)
    assert "Last check" in page and "Nov 11, 2026, 07:10 PM (Asia/Manila), live run" in page
    assert "Next check at" in page and "(estimated)" in page and "Next check: hourly while this PC is on" in page
    assert "Running, some feeds failed" in page  # the sample run has one failed feed
    monkeypatch.setattr(dashboard, "read_next_run", lambda: datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc))
    page = build(tmp_path, db)
    assert "Nov 11, 2026, 09:00 PM (Asia/Manila)" in page and "(estimated)" not in page


def test_a_watcher_that_stopped_is_shown_as_late():
    latest = {"started_at": (NOW - timedelta(hours=5)).isoformat(), "finished_at": (NOW - timedelta(hours=5)).isoformat(),
              "feeds_ok": 10, "feeds_failed": 0}
    assert dashboard.watcher_state(latest, NOW) == ("Late: last check 5 hours ago", "st-fail")
    assert dashboard.watcher_state(dict(latest, finished_at=NOW.isoformat()), NOW) == ("Running normally", "st-ok")
    assert dashboard.watcher_state(None, NOW)[0] == "No check yet"


def test_the_task_time_from_powershell_is_read_in_utc():
    moment = schedule_info.parse_next_run("2026-11-11T13:00:00.0000000Z\r\n")
    assert moment == datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
    assert schedule_info.parse_next_run("") is None and schedule_info.parse_next_run("not a time") is None


def test_the_page_has_no_em_or_en_dash_and_no_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", SECRET_URL)
    folder = carousel(tmp_path / "carousels", build=dict(PASSING, title="Photoshop can relight – and more — soon"))
    activity.log_event("alert", "sent", f"OFFICIAL: Canon — R6, posted with {SECRET_URL}", now=NOW)
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    assert "—" not in page and "–" not in page
    assert "Photoshop can relight, and more, soon" in page
    assert SECRET_TOKEN not in page and "hooks.slack.com" not in page
    assert folder.name in page


def test_someone_new_sees_what_the_system_does_and_what_needs_doing(tmp_path):
    page = text_of(build(tmp_path, sample_db(tmp_path / "seen.sqlite")))
    assert "Photo news in, ready to post carousels out" in page
    assert "Needs attention now" in page and "Nothing is posted automatically" in page
    assert "David's personal Instagram is never used" in page


# ---- pipeline and carousel coverage ----

def test_the_pipeline_counts_each_story_once_and_shows_a_carousel_stage(tmp_path):
    db = sample_db(tmp_path / "seen.sqlite")
    base = tmp_path / "carousels"
    carousel(base, name="2026-11-11-canon-announces-r6-mark-iii")  # waiting for David, matched by its title
    page = build(tmp_path, db, base)
    stages = dict(re.findall(r'data-stage="([a-z]+)"><span class="stage-num">\d</span><span class="stage-name">'
                             r'[^<]+</span><span class="stage-count">(\d+)</span>', page))
    # the held rumor and the practice-run story are found; the dismissed one is not taken forward
    assert stages["waiting"] == "1" and stages["found"] == "2" and stages["verified"] == "0"
    assert 'data-stage="waiting" data-stagei="4"' in page


def test_an_official_story_without_a_carousel_shows_the_reason(tmp_path):
    db = sample_db(tmp_path / "seen.sqlite")
    conn = runlog.connect(db)
    with conn:
        story_id = conn.execute("SELECT id FROM stories WHERE title='Canon Announces R6 Mark III'").fetchone()[0]
        conn.execute("INSERT INTO carousel_builds(story_id,built_at,status,folder,message) VALUES(?,?,?,?,?)",
                     (story_id, NOW.isoformat(), "failed", None, "No official page for this story was found."))
    conn.close()
    page = build(tmp_path, db)
    assert "Every official story and its carousel" in page
    assert "Not made: No official page for this story was found." in page
    assert "official stories have no carousel" in page  # also listed under Needs your attention


# ---- activity ----

def test_the_activity_page_lists_events_with_filters_and_weekly_counts(tmp_path):
    activity.log_event("check", "ok", "Live check: 40 articles read", now=NOW - timedelta(hours=1))
    activity.log_event("alert", "sent", "OFFICIAL: Canon Announces R6 Mark III", now=NOW - timedelta(minutes=50))
    activity.log_event("review", "approved", "Photoshop 2027", who="Kint", now=NOW - timedelta(minutes=10))
    activity.log_event("export", "made", "TPM-News-Dashboard-2026-11-11.zip, 12.5 MB", now=NOW)
    page = build(tmp_path)
    for element in ('id="a-type"', 'id="a-search"', 'id="a-range"', 'id="activity-list"'):
        assert element in page
    assert page.count('<tr class="ev"') == 4
    assert '<div class="k">Alerts sent</div><div class="v">1</div>' in page
    assert '<div class="k">Approved</div><div class="v">1</div>' in page
    assert "TPM-News-Dashboard-2026-11-11.zip, 12.5 MB" in page and ">Kint<" in page
    for kind, name in activity.TYPES.items():
        assert f'<option value="{kind}">{name}</option>' in page


def test_no_activity_yet_shows_an_empty_state(tmp_path):
    assert "No activity recorded yet" in build(tmp_path)


# ---- the carousel gallery ----

def test_a_carousel_card_has_the_slides_captions_fact_check_sources_and_downloads(tmp_path):
    base = tmp_path / "carousels"
    folder = carousel(base)
    downloads.write_folder_zip(folder)
    page = build(tmp_path, carousels_dir=base)
    name = folder.name
    assert f'data-lb="lb-{name}"' in page and page.count(f'data-lb="lb-{name}"') == 4  # click to enlarge
    assert f'href="../output/carousels/{name}/{name}.zip"' in page  # the prebuilt zip, for the file page
    assert f'data-live-href="/api/download/carousel/{name}"' in page  # the real download, through the server
    assert f'data-live-href="/api/download/slide/{name}/02.png"' in page
    for label in ("TPM Facebook", "TPM Instagram", "David Molnar Facebook"):
        assert f"<h3>{label}</h3>" in page
    assert 'data-kind="caption"' in page and "Fact check" in page and "Sources and image credits" in page
    assert "https://blog.adobe.com/max-2026" in page and "Download all slides (ZIP)" in page


def test_without_a_prebuilt_zip_the_file_page_says_how_to_get_one(tmp_path):
    base = tmp_path / "carousels"
    carousel(base)
    page = build(tmp_path, carousels_dir=base)
    assert 'aria-disabled="true"' in page and "src\\downloads.py --all" in page


def test_layout_samples_are_left_off_the_page(tmp_path):
    carousel(tmp_path / "samples", name="2026-11-11-x-sample", build=dict(PASSING, sample=True))
    page = build(tmp_path)
    assert '<span class="tag tag-sample">SAMPLE</span>' not in page and 'value="sample"' not in page
    assert "2026-11-11-x-sample" not in page


def test_the_all_approved_button_uses_the_server_and_the_prebuilt_zip(tmp_path):
    base = tmp_path / "carousels"
    folder = carousel(base)
    carousel_status.set_status(folder, "approved", approved_by="David", approved_at=NOW.isoformat())
    downloads.write_approved_zip(base)
    page = build(tmp_path, carousels_dir=base)
    assert 'data-live-href="/api/download/approved"' in page
    assert f'href="../output/carousels/{downloads.APPROVED_ZIP_NAME}"' in page
    assert "Download all approved carousels (1)" in page


# ---- David's read only copy ----

def test_the_share_page_is_read_only_with_relative_paths_and_no_commands(tmp_path):
    base = tmp_path / "carousels"
    folder = carousel(base)
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"), base, mode="share",
                 base_for=lambda c: f"carousels/{c['name']}")
    assert "Read only copy. To approve a carousel, tell Kint." in page
    assert 'data-home="start"' in page and "Start here: the TPM photo news system in one minute" in page
    assert f'src="carousels/{folder.name}/01.png"' in page and "../output" not in page
    for forbidden in ("review.py", "data-action=", "--approve", "carousel.py --story", 'id="reviewer"',
                      "export_share_pack", 'data-live-href="', str(dashboard.ROOT), str(tmp_path), "file:///"):
        assert forbidden not in page, forbidden
    assert "connect-src 'none'" in page and 'name="robots" content="noindex,nofollow"' in page


def test_davids_copy_is_a_read_only_twin_of_kints_page(tmp_path):
    """Restore round: the same template with read_only=True. Same sidebar, pages, sections, cards and look; only the
    controls and commands are gone, and each carousel shows its status badge where Kint has the review controls."""
    base = tmp_path / "carousels"
    folder = carousel(base)
    db = sample_db(tmp_path / "seen.sqlite")
    local = build(tmp_path, db, base)
    share = build(tmp_path, db, base, read_only=True, base_for=lambda c: f"carousels/{c['name']}")
    nav = r'data-nav="([a-z]+)" data-label="([^"]+)"'
    assert re.findall(nav, share) == re.findall(nav, local)  # the same sidebar
    assert re.findall(r'data-page="([a-z]+)"', share) == re.findall(r'data-page="([a-z]+)"', local)
    for section in ("Run history", "Feed health", "Pipeline: where every story is now", "The steps in plain words",
                    "Every official story and its carousel", "Carousel drafts to review", "Canon Dry Story",
                    "Sources and image credits", "Design check", "Running, some feeds failed",
                    folder.name, 'id="carousel-list"', 'id="activity-list"' if 'id="activity-list"' in local else ""):
        assert section in share, section  # the same content as Kint's page
    assert local.count('class="carousel-card"') == share.count('class="carousel-card"')
    assert "Read only copy. To approve a carousel, tell Kint." in share and 'data-mode="share"' in share
    # the status badge where the controls were
    assert '<div class="review-area"><div class="review"><span class="tag st-accent">Waiting for David</span>' in share
    # nothing that copies or runs a command
    for gone in ("powershell", 'data-kind="command"', "data-base=", "data-action=", 'id="reviewer"',
                 'id="export-david"', "python", ".bat", "Command copied", '<details class="copy-row"', "file:///",
                 str(dashboard.ROOT)):
        assert gone not in share.lower() if gone == "powershell" else gone not in share, gone
    assert "PowerShell" in local and 'data-kind="command"' in local  # Kint keeps hers
    for button in re.findall(r"<button[^>]*data-copy=[^>]*>", share):
        assert 'data-kind="caption"' in button  # only the post captions can be copied


def test_the_read_only_script_has_no_review_export_or_command_code():
    import dashboard_assets
    local, share = dashboard_assets.script_for("local"), dashboard_assets.script_for("share")
    assert local == dashboard_assets.JS and "PowerShell" in local and "/api/review" in local
    for gone in ("PowerShell", "/api/review", "/api/export", "export-david", "[data-action]", ".bat", "LOCAL-ONLY"):
        assert gone not in share, gone
    for kept in ("Caption copied.", "openLightbox", "applyStories", "applyActivity", "show(location.hash"):
        assert kept in share, kept


def test_davids_copy_shows_small_previews_and_links_the_full_slides(tmp_path):
    base = tmp_path / "carousels"
    folder = carousel(base)

    def place(c):
        c["views"] = {s: f"carousels/{c['name']}/view/{s[:-4]}.jpg" for s in c["slides"]}
        return f"carousels/{c['name']}"

    page = build(tmp_path, carousels_dir=base, mode="share", base_for=place)
    assert f'<img src="carousels/{folder.name}/view/01.jpg"' in page
    assert f'data-src="carousels/{folder.name}/view/02.jpg"' in page
    assert f'href="carousels/{folder.name}/02.png" download' in page  # the full 1080 x 1440 slide
    assert f'<img src="carousels/{folder.name}/02.png"' not in page


def test_the_local_page_keeps_the_review_buttons_and_the_export_button(tmp_path):
    base = tmp_path / "carousels"
    carousel(base)
    page = build(tmp_path, carousels_dir=base)
    assert 'data-action="approve"' in page and 'id="reviewer"' in page and 'id="export-david"' in page
    assert "scripts\\export_share_pack.py" in page and "connect-src 'self'" in page


@pytest.mark.parametrize("mode", ["local", "share"])
def test_the_page_needs_no_network_in_either_mode(tmp_path, mode):
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"), mode=mode)
    assert "<link" not in page and "<script src" not in page and "@import" not in page and "url(http" not in page
