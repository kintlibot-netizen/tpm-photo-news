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
    # Round 12 redesign: four sections, the carousels first.
    assert [label for _, label in nav] == ["Carousels", "Photo news", "System", "How it works"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Dashboard sections", 1)[1].split("\n## ", 1)[0]
    missing = [label for _, label in nav if f"**{label}**" not in section]
    assert not missing, f"README Dashboard sections does not name: {missing}"
    positions = [section.index(f"**{label}**") for _, label in nav]
    assert positions == sorted(positions)
    for key, _ in nav:
        assert f'data-page="{key}"' in page


def test_kints_page_opens_on_the_carousels_with_no_old_sections(tmp_path):
    """Round 12: the page opens on the carousels to review. The Overview counts, the pipeline, the run history, the
    activity log, the coverage table and the long explainers are gone from the page (their data is kept)."""
    page = build(tmp_path, sample_db(tmp_path / "seen.sqlite"))
    assert 'data-home="review"' in page and "Carousels to review" in page and 'class="tiles"' in page
    for gone in ("Run history", "Pipeline: where every story is now", "Every official story and its carousel",
                 "Needs attention now", "Photo news in, ready to post carousels out", "The steps in plain words",
                 'id="activity-list"', 'id="story-list"', "This week", "Start here"):
        assert gone not in page, gone
    assert "The rules that never change" in page


def test_the_top_bar_has_one_short_health_line(tmp_path, monkeypatch):
    db = sample_db(tmp_path / "seen.sqlite")
    page = build(tmp_path, db)
    # 11:10 UTC is 7:10 PM in Manila; the sample run has one failed feed.
    assert 'class="health"' in page and "Last check 7:10 PM" in page and "feeds OK" in page
    assert "(Asia/Manila)" in page and "Running, some feeds failed" in page
    monkeypatch.setattr(dashboard, "read_next_run", lambda: datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc))
    page = build(tmp_path, db)
    assert "next 9:00 PM (Asia/Manila)" in page


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
    assert "Carousels to review" in page and "How it works" in page
    assert "Nothing is posted automatically" in page and "David's personal Instagram is blocked" in page


# ---- photo news ----

def test_a_sent_official_story_shows_its_carousel_status(tmp_path):
    db = sample_db(tmp_path / "seen.sqlite")
    base = tmp_path / "carousels"
    carousel(base, name="2026-11-11-canon-announces-r6-mark-iii")  # waiting for David, matched by its title
    page = build(tmp_path, db, base)
    assert "Carousel: Waiting for David" in page and 'class="news-list"' in page
    assert 'data-stage=' not in page  # the pipeline is gone


def test_an_official_story_without_a_carousel_has_no_red_not_made_chip(tmp_path):
    db = sample_db(tmp_path / "seen.sqlite")
    conn = runlog.connect(db)
    with conn:
        story_id = conn.execute("SELECT id FROM stories WHERE title='Canon Announces R6 Mark III'").fetchone()[0]
        conn.execute("INSERT INTO carousel_builds(story_id,built_at,status,folder,message) VALUES(?,?,?,?,?)",
                     (story_id, NOW.isoformat(), "failed", None, "No official page for this story was found."))
    conn.close()
    page = build(tmp_path, db)
    assert "Canon Announces R6 Mark III" in page and "Not made" not in page
    assert "Every official story and its carousel" not in page


# ---- activity ----

def test_the_activity_log_is_kept_but_not_shown_on_the_page(tmp_path):
    # Round 12: the activity page is gone from the dashboard. Events are still written to the activity file.
    activity.log_event("alert", "sent", "OFFICIAL: Canon Announces R6 Mark III", now=NOW - timedelta(minutes=50))
    activity.log_event("export", "made", "TPM-News-Dashboard-2026-11-11.zip, 12.5 MB", now=NOW)
    assert len(activity.read_events()) == 2
    page = build(tmp_path)
    assert 'id="activity-list"' not in page and "TPM-News-Dashboard-2026-11-11.zip" not in page


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
    assert 'data-home="review"' in page and "Carousels to review" in page and 'class="banner"' in page
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
    for section in ("Feed health", "Carousels to review", "Photo news", "The rules that never change",
                    "Canon Announces R6 Mark III", "Sources and image credits", "Design check",
                    "Running, some feeds failed", folder.name, 'id="carousel-list"', 'class="tiles"'):
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
    for kept in ("Caption copied.", "openLightbox", "show(location.hash"):
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
