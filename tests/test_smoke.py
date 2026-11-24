"""End to end, offline. Fetch -> classify -> dedupe -> alert (Slack faked) -> carousel decision (build faked) -> dashboard.

No network, no Claude, no Slack. The feeds are fixtures, the webhook is a fake, and the carousel build is a fake
that writes a real status file. The page must show the story and its status, and must not show the webhook.
"""
import email.utils
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
import requests
from conftest import ROOT

import activity
import alert
import carousel
import carousel_status
import downloads
import fetch
import review
import review_server
import run
import share_pack

SECRET = "smoketoken4455"
WEBHOOK = f"https://hooks.slack.com/services/T0SMOKE/B0SMOKE/{SECRET}"
NEWS_URL = "https://news.example/feed"
RUMOR_URL = "https://rumors.example/feed"
OFFICIAL_TITLE = "Canon Announces EOS R6 Mark III"
RUMOR_TITLE = "Fujifilm X-T6 rumored with a new sensor"
HOW_TO_TITLE = "How to use the new Fujifilm X-T6 focus modes"
SOURCES_YAML = f"""sources:
  - {{name: "PetaPixel", type: news, url: "{NEWS_URL}"}}
  - {{name: "Fuji Rumors", type: rumor, url: "{RUMOR_URL}"}}
fetch:
  timeout_seconds: 5
  retries: 0
  retry_pause_seconds: 0
  max_feed_megabytes: 10
  user_agent: "smoke-test"
"""


def feed(items):
    """A small RSS feed, published an hour ago so it is inside the 72 hour window."""
    published = email.utils.format_datetime(datetime.now(timezone.utc) - timedelta(hours=1))
    entries = "".join(
        f"<item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{published}</pubDate><description>{summary}</description></item>"
        for title, link, summary in items
    )
    return (f'<?xml version="1.0"?><rss version="2.0"><channel><title>feed</title>'
            f"<link>https://example.com</link>{entries}</channel></rss>").encode("utf-8")


@pytest.fixture
def project(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "sources.yaml").write_text(SOURCES_YAML, encoding="utf-8")
    (tmp_path / "config" / "rules.yaml").write_text(
        (ROOT / "config" / "rules.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    bodies = {
        NEWS_URL: feed([(OFFICIAL_TITLE, "https://news.example/r6-mark-iii", "Canon says the camera is out now.")]),
        RUMOR_URL: feed([
            (RUMOR_TITLE, "https://rumors.example/x-t6-sensor", "Rumored specs, unconfirmed."),
            (HOW_TO_TITLE, "https://rumors.example/how-to-x-t6", "A short guide."),
        ]),
    }
    monkeypatch.setattr(fetch, "_download", lambda url, settings: bodies[url])
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    monkeypatch.setattr(alert.time, "sleep", lambda seconds: None)
    posts = []

    class Accepted:
        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        posts.append((url, kwargs["json"]["text"]))
        return Accepted()

    monkeypatch.setattr(requests, "post", fake_post)
    return tmp_path, posts


@pytest.fixture
def fake_build(monkeypatch, project):
    root, _ = project
    folder = root / "output" / "carousels" / "2026-11-11-canon-eos-r6-mark-iii"

    def run_story(key, official_url, render):
        folder.mkdir(parents=True, exist_ok=True)
        for n in (1, 2):
            (folder / f"{n:02d}.png").write_bytes(f"png {n}".encode())
        (folder / "captions.txt").write_text(
            "DAVID MOLNAR FACEBOOK (first person)\nA short hook.\n\nTPM FACEBOOK AND INSTAGRAM (we)\nA short hook.\n",
            encoding="utf-8")
        (folder / "sources.md").write_text(
            "# Sources\n\nOfficial source for every fact: https://www.canon.example/r6-mark-iii\n", encoding="utf-8")
        carousel_status.write_build(folder, {
            "title": OFFICIAL_TITLE, "slides": 2, "confirmed": 5, "removed_count": 0, "removed": [],
            "missing": [], "placed": [], "design_summary": "Design check: passed, no findings.",
            "design_fail": 0, "fact_check_passed": True, "lint_passed": True,
            "official_url": "https://www.canon.example/r6-mark-iii",
        })
        downloads.write_folder_zip(folder)  # the real build writes the prebuilt zip for a finished carousel
        return {"folder": folder, "slides": 2, "confirmed": 5, "removed": [], "missing": [],
                "placed": [], "design": []}

    monkeypatch.setattr(carousel, "run_story", run_story)
    return folder


def test_the_whole_live_pipeline_runs_offline_and_the_page_shows_it(project, fake_build):
    root, posts = project
    assert run.main(["--no-claude"]) == 0

    # Slack: every message goes to the one webhook, the official story is alerted, the rumor is held.
    assert {url for url, _ in posts} == {WEBHOOK}
    texts = [text for _, text in posts]
    alerts = [t for t in texts if OFFICIAL_TITLE in t and "OFFICIAL" in t]
    assert len(alerts) == 1
    assert any(t.startswith(f"Carousel ready for approval: {OFFICIAL_TITLE}") for t in texts)
    assert not any(RUMOR_TITLE in t for t in texts), "a rumor reported by one site is held, not sent"
    assert not any(HOW_TO_TITLE in t for t in texts), "how-to headlines are not alert-worthy"
    assert not any("health" in t.lower() for t in texts)

    # Carousel: one successful build, recorded, and the draft is waiting for David.
    db = sqlite3.connect(root / "data" / "seen.sqlite")
    try:
        assert db.execute("SELECT status FROM carousel_builds").fetchall() == [("ok",)]
    finally:
        db.close()
    assert carousel_status.read_status(fake_build)["status"] == "waiting_for_david"

    # Dashboard: the story, its status and the carousel status are on the page. No secret is.
    page = (root / "dashboard" / "index.html").read_text(encoding="utf-8")
    for text in [OFFICIAL_TITLE, "Sent to Slack", "Waiting for David", "Waiting for a 2nd source",
                 "PetaPixel", "Fuji Rumors", "Zeiss", "capture one", "connect-src 'self'", "Run history"]:
        assert text in page, text
    assert SECRET not in page
    assert "hooks.slack.com" not in page


REVIEW_PAGE = {"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765", "content-type": "application/json",
               "sec-fetch-site": "same-origin"}


def test_check_alert_build_zip_approve_download_activity_and_share_pack(project, fake_build, monkeypatch):
    """Section F of round 7: the whole day in one test. Hourly check, Slack alert, carousel build with its zip,
    approval through the review server, a download, the activity log, and the Export for David pack, which is then
    scanned for secrets and paths from this PC."""
    import io
    import json
    import zipfile

    root, posts = project
    (root / ".env").write_text(f"SLACK_WEBHOOK_URL={WEBHOOK}\n", encoding="utf-8")
    monkeypatch.setattr(review, "CAROUSELS", root / "output" / "carousels")
    monkeypatch.setattr(review, "POST_LOG", root / "output" / "post-log.csv")
    monkeypatch.setattr(review_server, "ROOT", root)

    # 1. hourly check, alert, carousel build
    assert run.main(["--no-claude"]) == 0
    assert any(OFFICIAL_TITLE in t and "OFFICIAL" in t for _, t in posts)

    # 2. the prebuilt zip is in the carousel folder, slides in order
    prebuilt = downloads.prebuilt_zip(fake_build)
    assert prebuilt is not None and prebuilt.exists()
    with zipfile.ZipFile(prebuilt) as archive:
        names = archive.namelist()
    assert names[0].startswith("01-") and names[1].startswith("02-")
    assert {"captions-tpm-facebook.txt", "captions-tpm-instagram.txt", "captions-david-facebook.txt",
            "sources.txt"} <= set(names)

    # 3. approve through the review server
    body = json.dumps({"action": "approve", "folder": fake_build.name, "reviewer": "Kint"}).encode()
    status, _, reply = review_server.handle("POST", "/api/review", REVIEW_PAGE, body, 8765)
    assert status == 200 and json.loads(reply)["ok"] is True
    assert carousel_status.read_status(fake_build)["status"] == "approved"

    # 4. the download endpoints
    status, headers, data = review_server.handle("GET", f"/api/download/carousel/{fake_build.name}", REVIEW_PAGE,
                                                 b"", 8765)
    assert status == 200 and headers["Content-Type"] == "application/zip"
    assert "01-cover.png" in zipfile.ZipFile(io.BytesIO(data)).namelist()
    status, _, data = review_server.handle("GET", "/api/download/approved", REVIEW_PAGE, b"", 8765)
    assert status == 200 and any(n.startswith(f"{fake_build.name}/") for n in
                                 zipfile.ZipFile(io.BytesIO(data)).namelist())

    # 5. the share pack, scanned for secrets, absolute paths and review commands
    result = share_pack.export_pack(root=root)
    assert result["carousels"] == 1 and result["size_mb"] < 100 and result["zip"].exists()
    assert share_pack.scan_pack(result["folder"], root) == []
    page = (result["folder"] / "index.html").read_text(encoding="utf-8")
    assert "Read only copy. To approve a carousel, tell Kint." in page and OFFICIAL_TITLE in page
    for name, text in share_pack._texts(result["folder"]):
        for forbidden in (SECRET, "hooks.slack.com", str(root), str(root).replace("\\", "/"), "C:\\Users",
                          "review.py", "--approve", 'data-action="', "file:///", "\u2014"):
            assert forbidden not in text, (name, forbidden)
    with zipfile.ZipFile(result["zip"]) as archive:
        for name in archive.namelist():
            assert not name.startswith("/") and ":" not in name and ".." not in name, name
    # the web copy: output/share/latest is the same static site, ready to upload, with previews and full slides
    latest = root / "output" / "share" / "latest"
    assert (latest / "index.html").read_text(encoding="utf-8") == page
    assert f"carousels/{fake_build.name}/view/01.jpg" in page and (latest / "carousels" / fake_build.name / "01.png").exists()
    assert share_pack.scan_pack(latest, root) == []
    # David's copy is the read only twin of Kint's page: the same sections, no command and no PowerShell wording
    for kept in ("Feed health", "Run history", "Needs your attention", "The steps in plain words"):
        assert kept in page, kept
    assert "powershell" not in page.lower() and 'data-kind="command"' not in page and "data-base=" not in page

    # 6. every step is in the activity log, and nothing secret is
    events = activity.read_events()
    kinds = {(e["type"], e["outcome"]) for e in events}
    for expected in [("alert", "sent"), ("carousel", "built"), ("review", "approved"), ("download", "carousel zip"),
                     ("download", "approved zip"), ("export", "made")]:
        assert expected in kinds, expected
    assert any(e["type"] == "check" for e in events)
    assert any(e["type"] == "review" and e["who"] == "Kint" for e in events)
    export = next(e for e in events if e["type"] == "export")
    assert " MB" in export["details"]
    log_text = activity.LOG_PATH.read_text(encoding="utf-8")
    assert SECRET not in log_text and "hooks.slack.com" not in log_text


def test_a_second_run_sends_nothing_new_and_builds_nothing_new(project, fake_build):
    root, posts = project
    assert run.main(["--no-claude"]) == 0
    first_count = len(posts)
    assert run.main(["--no-claude"]) == 0
    assert len(posts) == first_count
