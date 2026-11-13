"""Round 7, section C: carousel zips, single slides, all approved carousels, and the download endpoints of the review
server. Temporary folders only; no socket is opened."""
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

import activity
import carousel_status
import downloads
import review
import review_server

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
NAME = "2026-11-11-photoshop-2027"
PAGE = {"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765", "content-type": "application/json",
        "sec-fetch-site": "same-origin"}
PLAN = {
    "slides": [
        {"headline": {"text": "RELIGHT", "quote": "q"}},
        {"headline": {"text": "GENERATIVE RESTYLE", "quote": "q"}},
        {"headline": {"text": "QUICK COMPARE", "quote": "q"}},
    ],
    "comparison": None, "price": None,
}
PASSING = {"title": "Photoshop 2027", "slides": 4, "fact_check_passed": True, "lint_passed": True, "design_fail": 0,
           "design_summary": "Design check: passed, no findings.", "official_url": "https://blog.adobe.com/max-2026"}


def carousel(base, name=NAME, slides=4, plan=PLAN, build=PASSING):
    folder = base / name
    folder.mkdir(parents=True, exist_ok=True)
    for n in range(1, slides + 1):
        (folder / f"{n:02d}.png").write_bytes(f"png {n}".encode())
    (folder / "captions.txt").write_text(
        "DAVID MOLNAR FACEBOOK (first person)\nMy favorite update is all about light. Which would you try?\n\n"
        "TPM FACEBOOK AND INSTAGRAM (we)\nWe think Relight is the one to try first. Would you?\n", encoding="utf-8")
    (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (folder / "sources.md").write_text(
        "# Sources\n\nOfficial source for every fact: https://blog.adobe.com/max-2026\n"
        "- PetaPixel: https://petapixel.com/photoshop-2027\n", encoding="utf-8")
    carousel_status.write_build(folder, build)
    return folder


def open_zip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


# ---- the carousel zip ----

def test_the_zip_has_the_slides_in_order_a_caption_per_account_and_the_sources(tmp_path):
    folder = carousel(tmp_path)
    archive = open_zip(downloads.zip_bytes(folder))
    names = archive.namelist()
    assert names[:4] == ["01-cover.png", "02-relight.png", "03-generative-restyle.png", "04-quick-compare.png"]
    assert {"captions-tpm-facebook.txt", "captions-tpm-instagram.txt", "captions-david-facebook.txt",
            "sources.txt", "README.txt"} <= set(names)
    assert archive.read("02-relight.png") == b"png 2"
    assert archive.read("captions-david-facebook.txt").decode().startswith("My favorite update")
    assert archive.read("captions-tpm-instagram.txt").decode().startswith("We think Relight")
    sources = archive.read("sources.txt").decode()
    assert "https://blog.adobe.com/max-2026" in sources and "https://petapixel.com/photoshop-2027" in sources
    readme = archive.read("README.txt").decode()
    assert "Waiting for David" in readme and "Nothing is posted automatically" in readme
    for name in names:
        if name.endswith(".txt"):
            text = archive.read(name).decode()
            assert str(tmp_path) not in text and "—" not in text


def test_a_slide_dropped_by_the_fact_check_gets_plain_numbers(tmp_path):
    folder = carousel(tmp_path, slides=3)  # the plan names 4 slides, only 3 were rendered
    assert [name for _, name in downloads.slide_entries(folder)] == ["01-cover.png", "02-slide.png", "03-slide.png"]


def test_a_sample_zip_is_labelled_sample(tmp_path):
    folder = carousel(tmp_path, name="2026-11-11-canon-eos-r8-mark-ii-sample", build=dict(PASSING, sample=True))
    assert downloads.zip_name(folder).startswith("SAMPLE-")
    readme = open_zip(downloads.zip_bytes(folder)).read("README.txt").decode()
    assert "SAMPLE" in readme and "never for posting" in readme
    titled = carousel(tmp_path, name="2026-11-11-other", build=dict(PASSING, title="SAMPLE: Photoshop"))
    assert downloads.zip_name(titled).startswith("SAMPLE-")
    assert downloads.zip_name(carousel(tmp_path, name="2026-11-11-real")) == "2026-11-11-real.zip"


def test_the_prebuilt_zip_is_written_into_the_folder_and_replaces_an_old_one(tmp_path):
    folder = carousel(tmp_path)
    (folder / "old-name.zip").write_bytes(b"old")
    path = downloads.write_folder_zip(folder)
    assert path == folder / f"{NAME}.zip" and path.exists()
    assert not (folder / "old-name.zip").exists()
    assert downloads.prebuilt_zip(folder) == path
    empty = tmp_path / "2026-11-11-empty"
    empty.mkdir()
    (empty / "captions.txt").write_text("x", encoding="utf-8")
    assert downloads.write_folder_zip(empty) is None


def test_older_carousels_get_their_missing_zip_and_a_failed_design_gets_none(tmp_path):
    base, samples = tmp_path / "carousels", tmp_path / "samples"
    old = carousel(base, name="2026-11-11-built-before-zips")
    failed = carousel(base, name="2026-11-11-design-failed", build=dict(PASSING, design_fail=1))
    done = carousel(base, name="2026-11-11-already-zipped")
    first = downloads.write_folder_zip(done)
    stamp = first.stat().st_mtime_ns
    sample = carousel(samples, name="2026-11-11-x-sample", build=dict(PASSING, sample=True))
    written = downloads.ensure_zips(base, samples)
    assert sorted(p.name for p in written) == ["2026-11-11-built-before-zips.zip", "SAMPLE-2026-11-11-x-sample.zip"]
    assert downloads.prebuilt_zip(old) and downloads.prebuilt_zip(sample)
    assert downloads.prebuilt_zip(failed) is None and first.stat().st_mtime_ns == stamp
    assert downloads.ensure_zips(tmp_path / "missing", tmp_path / "missing-too") == []


def test_every_run_writes_the_missing_zips_before_the_page_is_rebuilt():
    import inspect

    import run
    source = inspect.getsource(run.publish)
    assert 'downloads.ensure_zips(ROOT / "output" / "carousels", ROOT / "output" / "samples")' in source
    assert source.index("downloads.ensure_zips(") < source.index("dashboard.write_dashboard(")


def test_single_slide_names_follow_the_zip_names(tmp_path):
    folder = carousel(tmp_path)
    assert downloads.slide_download_name(folder, "02.png") == f"{NAME}-02-relight.png"
    assert downloads.slide_download_name(folder, "09.png") is None


def test_all_approved_carousels_go_in_one_zip_and_samples_never(tmp_path, monkeypatch):
    monkeypatch.setattr(review, "CAROUSELS", tmp_path)
    approved = carousel(tmp_path)
    review.approve(approved, "Kint", NOW)
    carousel(tmp_path, name="2026-11-11-waiting")
    sample = carousel(tmp_path, name="2026-11-11-x-sample", build=dict(PASSING, sample=True))
    carousel_status.set_status(sample, "approved")  # even a sample marked approved by hand stays out
    data, count = downloads.approved_zip_bytes(tmp_path)
    names = open_zip(data).namelist()
    assert count == 1 and all(n.startswith(f"{NAME}/") for n in names)
    assert f"{NAME}/01-cover.png" in names
    # approving wrote the approved zip beside the folders, for the dashboard opened as a file
    assert (tmp_path / downloads.APPROVED_ZIP_NAME).exists()


# ---- the review server ----

@pytest.fixture
def served(tmp_path, monkeypatch):
    base = tmp_path / "output" / "carousels"
    base.mkdir(parents=True)
    monkeypatch.setattr(review, "CAROUSELS", base)
    monkeypatch.setattr(review, "POST_LOG", tmp_path / "post-log.csv")
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    return base


def get(path, headers=None):
    return review_server.handle("GET", path, headers or PAGE, b"", 8765, NOW)


def test_the_carousel_zip_downloads_as_an_attachment_and_is_logged(served):
    carousel(served)
    status, headers, body = get(f"/api/download/carousel/{NAME}")
    assert status == 200 and headers["Content-Type"] == "application/zip"
    assert headers["Content-Disposition"] == f'attachment; filename="{NAME}.zip"'
    assert "01-cover.png" in open_zip(body).namelist()
    event = next(e for e in activity.read_events() if e["type"] == "download")
    assert event["outcome"] == "carousel zip" and NAME in event["details"]


def test_a_single_slide_downloads_with_its_friendly_name(served):
    carousel(served)
    status, headers, body = get(f"/api/download/slide/{NAME}/03.png")
    assert status == 200 and headers["Content-Type"] == "image/png" and body == b"png 3"
    assert f'filename="{NAME}-03-generative-restyle.png"' in headers["Content-Disposition"]
    assert next(e for e in activity.read_events() if e["type"] == "download")["outcome"] == "slide"


def test_a_sample_downloads_from_the_samples_folder_with_sample_in_the_name(served, tmp_path):
    carousel(tmp_path / "output" / "samples", name="2026-11-11-x-sample", build=dict(PASSING, sample=True))
    status, headers, _ = get("/api/download/carousel/2026-11-11-x-sample")
    assert status == 200 and 'filename="SAMPLE-2026-11-11-x-sample.zip"' in headers["Content-Disposition"]


def test_all_approved_carousels_download_in_one_zip(served):
    folder = carousel(served)
    review.approve(folder, "Kint", NOW)
    status, headers, body = get("/api/download/approved")
    assert status == 200 and headers["Content-Disposition"].startswith('attachment; filename="TPM-approved-carousels-')
    assert f"{NAME}/02-relight.png" in open_zip(body).namelist()
    assert any(e["outcome"] == "approved zip" for e in activity.read_events())


@pytest.mark.parametrize("path", [
    "/api/download/carousel/..%2F..%2Fconfig", "/api/download/carousel/missing", "/api/download/slide/x/../../.env",
    f"/api/download/slide/{NAME}/1.png", f"/api/download/slide/{NAME}/09.png", "/api/download/other",
    "/api/download/carousel/..",
])
def test_path_tricks_and_unknown_downloads_are_refused_with_a_json_reason(served, path):
    carousel(served)
    status, headers, body = get(path)
    assert status == 404 and headers["Content-Type"].startswith("application/json")
    assert json.loads(body)["ok"] is False


def test_a_download_started_from_another_site_is_refused(served):
    carousel(served)
    status, _, body = get(f"/api/download/carousel/{NAME}", dict(PAGE, **{"sec-fetch-site": "cross-site"}))
    assert status == 403 and json.loads(body)["ok"] is False
    status, _, _ = get(f"/api/download/carousel/{NAME}", {"host": "evil.example:8765"})
    assert status == 403
    assert not any(e["type"] == "download" for e in activity.read_events())
