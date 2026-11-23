"""Round 7, section D: Export for David. The pack is built from a temporary project and scanned for secrets, absolute
paths and review commands. No network."""
import json
import zipfile
from datetime import datetime, timezone

import pytest
from conftest import ROOT
from test_dashboard import sample_db

import activity
import carousel_status
import review_server
import share_pack
from test_round7_downloads import PAGE, PASSING, carousel

NOW = datetime(2026, 11, 13, 1, 9, tzinfo=timezone.utc)
SECRET = "sharepacksecret8899"
WEBHOOK = f"https://hooks.slack.com/services/T0SHARE/B0SHARE/{SECRET}"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A small project: config, a database, a .env with the webhook, and four carousels (real, rejected, sample)."""
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    for name in ("sources.yaml", "rules.yaml"):
        (root / "config" / name).write_text((ROOT / "config" / name).read_text(encoding="utf-8"), encoding="utf-8")
    (root / "data").mkdir()
    sample_db(root / "data" / "seen.sqlite")
    (root / ".env").write_text(f"SLACK_WEBHOOK_URL={WEBHOOK}\n", encoding="utf-8")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", WEBHOOK)
    base = root / "output" / "carousels"
    carousel(base, name="2026-11-11-photoshop-2027")
    approved = carousel(base, name="2026-11-12-canon-eos-r6-mark-iii")
    carousel_status.set_status(approved, "approved", approved_by="David", approved_at=NOW.isoformat())
    rejected = carousel(base, name="2026-11-10-old-camera-raw")
    carousel_status.set_status(rejected, "rejected", reason="Facts came from a 2024 post")
    carousel(root / "output" / "samples", name="2026-11-11-canon-eos-r8-mark-ii-sample",
             build=dict(PASSING, sample=True))
    return root


def all_text(folder):
    """Every text file in the pack, and every text file inside its zips."""
    return dict(share_pack._texts(folder))


def test_the_pack_is_a_folder_and_a_zip_with_the_dashboard_slides_and_zips(project):
    result = share_pack.export_pack(now=NOW, root=project)
    folder, zip_path = result["folder"], result["zip"]
    assert folder.name == "TPM-News-Dashboard-2026-11-13" and zip_path.name == "TPM-News-Dashboard-2026-11-13.zip"
    assert folder.parent == project / "output" / "share"
    assert (folder / "index.html").exists() and (folder / "READ ME FIRST.txt").exists()
    for name in ("2026-11-11-photoshop-2027", "2026-11-12-canon-eos-r6-mark-iii"):
        assert (folder / "carousels" / name / "01.png").exists()
        assert (folder / "carousels" / name / f"{name}.zip").exists()
    assert (folder / "carousels" / "TPM-approved-carousels.zip").exists()
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert "TPM-News-Dashboard-2026-11-13/index.html" in names
    assert "TPM-News-Dashboard-2026-11-13/carousels/2026-11-11-photoshop-2027/02.png" in names
    assert result["carousels"] == 4 and result["size_mb"] < 100


def test_every_carousel_is_in_davids_copy_with_its_status(project):
    folder = share_pack.export_pack(now=NOW, root=project)["folder"]
    page = (folder / "index.html").read_text(encoding="utf-8")
    for name in ("2026-11-10-old-camera-raw", "2026-11-11-canon-eos-r8-mark-ii-sample"):
        assert f'id="car-{name}"' in page and (folder / "carousels" / name / "01.png").exists()
    assert "Rejected: Facts came from a 2024 post" in page and "Layout sample not for posting" in page
    assert page.index('data-kind="draft"') < page.index('data-kind="sample"')  # samples come last
    assert 'value="all" selected' in page  # the default view is All carousels


def test_the_page_opens_from_the_pack_with_relative_paths_and_the_read_only_note(project):
    folder = share_pack.export_pack(now=NOW, root=project)["folder"]
    page = (folder / "index.html").read_text(encoding="utf-8")
    assert "Read only copy. To approve a carousel, tell Kint." in page
    assert "Start here" in page and 'data-home="start"' in page
    assert 'src="carousels/2026-11-11-photoshop-2027/view/01.jpg"' in page  # the small preview
    assert 'href="carousels/2026-11-11-photoshop-2027/01.png" download' in page  # the full slide
    assert 'href="carousels/2026-11-11-photoshop-2027/2026-11-11-photoshop-2027.zip"' in page
    assert 'href="carousels/TPM-approved-carousels.zip"' in page
    for src in __import__("re").findall(r'src="([^"]+)"', page):
        assert (folder / src).exists(), src  # every image the page shows is in the pack


def test_the_pack_is_a_static_website_with_relative_links_only(project):
    import re
    folder = share_pack.export_pack(now=NOW, root=project)["folder"]
    page = (folder / "index.html").read_text(encoding="utf-8")
    assert (folder / "index.html").is_file()  # at the root, so a web host serves it as the home page
    links = re.findall(r'(?:src|href|data-src)="([^"#]+)"', page)
    assert links
    for link in links:
        if link.startswith("https://") or link.startswith("http://"):
            continue  # the official sources and news links
        assert not link.startswith(("/", "file:", "C:", "../")) and ":\\" not in link, link
        assert (folder / link).exists(), link  # every download works from the hosted copy too
    assert "<script src" not in page and "<link" not in page and 'name="viewport"' in page


def test_the_latest_folder_always_matches_the_newest_pack(project):
    result = share_pack.export_pack(now=NOW, root=project)
    latest = project / "output" / "share" / "latest"
    assert result["latest"] == latest
    newest = sorted(p.relative_to(result["folder"]).as_posix() for p in result["folder"].rglob("*") if p.is_file())
    assert sorted(p.relative_to(latest).as_posix() for p in latest.rglob("*") if p.is_file()) == newest
    assert (latest / "index.html").read_text(encoding="utf-8") == (result["folder"] / "index.html").read_text(
        encoding="utf-8")
    (latest / "old.txt").write_text("old", encoding="utf-8")
    share_pack.export_pack(now=NOW, root=project)
    assert not (latest / "old.txt").exists()
    assert share_pack.scan_pack(latest, project) == []


def test_previews_for_the_page_and_full_slides_for_the_downloads(project):
    result = share_pack.export_pack(now=NOW, root=project)
    slide_dir = result["folder"] / "carousels" / "2026-11-11-photoshop-2027"
    assert (slide_dir / "view" / "01.jpg").read_bytes() == b"jpg png 1"  # the test preview maker
    assert (slide_dir / "01.png").read_bytes() == b"png 1"  # the full slide, unchanged
    with zipfile.ZipFile(slide_dir / "2026-11-11-photoshop-2027.zip") as archive:
        assert archive.read("01-cover.png") == b"png 1" and not any(n.endswith(".jpg") for n in archive.namelist())
    assert result["previews"] == 16
    event = next(e for e in activity.read_events() if e["type"] == "export")
    assert "16 previews" in event["details"] and "latest folder refreshed" in event["details"]


def test_without_chromium_the_page_shows_the_full_slides(project, monkeypatch):
    monkeypatch.setattr(share_pack.previews, "make_previews", lambda jobs, *a, **k: 0)
    folder = share_pack.export_pack(now=NOW, root=project)["folder"]
    page = (folder / "index.html").read_text(encoding="utf-8")
    assert 'src="carousels/2026-11-11-photoshop-2027/01.png"' in page and "/view/" not in page


def test_the_preview_maker_handles_nothing_to_do():
    from previews import preview_name
    import previews
    assert preview_name("03.png") == "03.jpg"
    assert previews.PREVIEW_WIDTH < 1080 and 0.5 < previews.QUALITY < 1


def test_the_pack_holds_no_secret_no_path_from_this_pc_and_no_review_command(project):
    folder = share_pack.export_pack(now=NOW, root=project)["folder"]
    texts = all_text(folder)
    assert "index.html" in texts and any(name.endswith("captions-tpm-instagram.txt") for name in texts)
    for name, text in texts.items():
        for forbidden in (SECRET, "hooks.slack.com", str(project), str(project).replace("\\", "/"), "C:\\Users",
                          "review.py", "--approve", 'data-action="', "file:///", "\u2014"):
            assert forbidden not in text, (name, forbidden)
    assert share_pack.scan_pack(folder, project) == []


def test_the_pack_page_is_the_read_only_twin_with_no_command_wording(project):
    folder = share_pack.export_pack(now=NOW, root=project)["folder"]
    page = (folder / "index.html").read_text(encoding="utf-8")
    for kept in ('data-nav="overview"', 'data-nav="attention"', 'data-nav="how"', "Run history", "Feed health",
                 '<div class="review-area"><div class="review"><span class="tag'):
        assert kept in page, kept
    for gone in ("powershell", 'data-kind="command"', "data-base=", "python.exe", "export_share_pack", ".bat"):
        assert gone not in page.lower(), gone


def test_a_page_with_command_wording_is_refused(project, tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "index.html").write_text("<p>Command copied. Paste it into PowerShell.</p>", encoding="utf-8")
    assert any("PowerShell wording" in p for p in share_pack.scan_pack(pack, project))
    (pack / "index.html").write_text('<button data-kind="command" data-copy="x">Copy</button>', encoding="utf-8")
    assert any("command copy button" in p for p in share_pack.scan_pack(pack, project))
    (pack / "index.html").write_text("<p>Read only copy. To approve a carousel, tell Kint.</p>", encoding="utf-8")
    assert share_pack.scan_pack(pack, project) == []


def test_a_secret_planted_in_a_caption_stops_the_export_and_leaves_nothing(project):
    captions = project / "output" / "carousels" / "2026-11-11-photoshop-2027" / "captions.txt"
    captions.write_text(captions.read_text(encoding="utf-8").replace("Which would you try?", WEBHOOK),
                        encoding="utf-8")
    with pytest.raises(share_pack.ExportError, match="Slack webhook"):
        share_pack.export_pack(now=NOW, root=project)
    assert not (project / "output" / "share" / "TPM-News-Dashboard-2026-11-13").exists()
    assert not (project / "output" / "share" / "TPM-News-Dashboard-2026-11-13.zip").exists()
    failed = next(e for e in activity.read_events() if e["type"] == "export")
    assert failed["outcome"] == "failed" and SECRET not in activity.LOG_PATH.read_text(encoding="utf-8")


def test_the_export_and_its_size_are_logged(project):
    result = share_pack.export_pack(now=NOW, root=project)
    event = next(e for e in activity.read_events() if e["type"] == "export")
    assert event["outcome"] == "made" and result["zip"].name in event["details"] and " MB" in event["details"]
    assert "4 carousels" in event["details"] and "left out (no slides)" in event["details"]


def test_a_second_export_the_same_day_replaces_the_first(project):
    first = share_pack.export_pack(now=NOW, root=project)
    (first["folder"] / "stale.txt").write_text("old", encoding="utf-8")
    second = share_pack.export_pack(now=NOW, root=project)
    assert second["folder"] == first["folder"] and not (second["folder"] / "stale.txt").exists()


def test_the_size_limit_drops_the_zips_first_then_the_oldest_carousels(project, monkeypatch):
    monkeypatch.setattr(share_pack, "PAGE_ALLOWANCE", 0)
    cards = [c for c in share_pack.dashboard.read_carousels(project / "output" / "carousels") if share_pack._keep(c)]
    slide_bytes = sum((cards[0]["folder"] / s).stat().st_size for s in cards[0]["slides"])
    # room for the first carousel's slides only: its zip and the second carousel are left out
    chosen, notes, with_approved = share_pack.plan_pack(cards, slide_bytes, approved_bytes=10)
    assert len(chosen) == 1 and chosen[0]["zip_data"] is None and not with_approved
    assert any("zip left out" in n for n in notes) and any("left out to stay under" in n for n in notes)


# ---- the Export for David button, through the review server ----

def test_the_export_button_calls_the_export_and_gives_a_download_link(tmp_path, monkeypatch):
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    zip_path = tmp_path / "output" / "share" / "TPM-News-Dashboard-2026-11-13.zip"
    monkeypatch.setattr(share_pack, "export_pack", lambda now=None: {"zip": zip_path, "size_mb": 12.34})
    status, _, body = review_server.handle("POST", "/api/export", PAGE, b"{}", 8765, NOW)
    reply = json.loads(body)
    assert status == 200 and reply["ok"] is True and "12.3 MB" in reply["message"]
    assert reply["download"] == "/output/share/TPM-News-Dashboard-2026-11-13.zip"


def test_the_export_button_is_refused_from_another_site(tmp_path, monkeypatch):
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    monkeypatch.setattr(share_pack, "export_pack", lambda now=None: pytest.fail("must not run"))
    status, _, body = review_server.handle("POST", "/api/export", dict(PAGE, origin="https://evil.example"), b"{}",
                                           8765, NOW)
    assert status == 403 and json.loads(body)["ok"] is False


def test_the_export_script_and_the_bat_file_exist_and_post_nothing():
    script = (ROOT / "scripts" / "export_share_pack.py").read_text(encoding="utf-8")
    bat = (ROOT / "Export for David.bat").read_text(encoding="utf-8")
    assert "share_pack.main()" in script and "scripts\\export_share_pack.py" in bat
    source = (ROOT / "src" / "share_pack.py").read_text(encoding="utf-8")
    assert "requests" not in source and "graph.facebook" not in source
