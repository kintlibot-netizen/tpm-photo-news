"""Functional round, item 6: the review server's request handler, called directly. No socket is opened.

Every test runs against a temporary carousel folder and a temporary post log, so nothing real is approved or logged.
"""
import json
from datetime import datetime, timezone

import pytest

import carousel_status
import review
import review_server

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
PORT = 8765
PAGE = {
    "host": "127.0.0.1:8765",
    "origin": "http://127.0.0.1:8765",
    "content-type": "application/json",
    "sec-fetch-site": "same-origin",
}
NAME = "2026-11-11-photoshop-2027"


@pytest.fixture
def carousels(tmp_path, monkeypatch):
    base = tmp_path / "carousels"
    base.mkdir()
    monkeypatch.setattr(review, "CAROUSELS", base)
    monkeypatch.setattr(review, "POST_LOG", tmp_path / "post-log.csv")
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    return base


def draft(base, name=NAME):
    folder = base / name
    (folder / "images").mkdir(parents=True)
    for number in (1, 2):
        (folder / f"{number:02d}.png").write_bytes(b"png")
    (folder / "captions.txt").write_text(
        "DAVID MOLNAR FACEBOOK (first person)\nI'm excited to check this out.\n\n"
        "TPM FACEBOOK AND INSTAGRAM (we)\nWe're excited to check this out.\n", encoding="utf-8")
    carousel_status.write_build(folder, {"title": "Photoshop 2027", "slides": 2, "design_fail": 0,
                                         "design_summary": "Design check: passed, no findings."})
    return folder


def post(body, headers=None, port=PORT, raw=None):
    payload = raw if raw is not None else json.dumps(body).encode("utf-8")
    return review_server.handle("POST", "/api/review", headers or PAGE, payload, port, NOW)


def reply(response):
    status, _, body = response
    return status, json.loads(body.decode("utf-8"))


def status_of(folder):
    return carousel_status.read_status(folder)["status"]


# ---- approve, reject and post from the page ----

def test_approve_from_the_page_records_the_typed_name(carousels):
    folder = draft(carousels)
    status, data = reply(post({"action": "approve", "folder": NAME, "reviewer": "Kint"}))
    assert status == 200 and data["ok"] is True
    saved = carousel_status.read_status(folder)
    assert saved["status"] == "approved" and saved["approved_by"] == "Kint"


def test_approve_without_a_name_is_refused(carousels):
    folder = draft(carousels)
    status, data = reply(post({"action": "approve", "folder": NAME, "reviewer": "  "}))
    assert status == 400 and "Your name" in data["error"]
    assert status_of(folder) == "draft"


def test_reject_needs_a_reason_and_records_it(carousels):
    folder = draft(carousels)
    status, _ = reply(post({"action": "reject", "folder": NAME, "reason": ""}))
    assert status == 400 and status_of(folder) == "draft"
    status, _ = reply(post({"action": "reject", "folder": NAME, "reason": "Too many words on slide 2"}))
    assert status == 200
    assert carousel_status.read_status(folder)["reason"].startswith("Too many")


def test_a_post_to_a_team_account_is_logged(carousels, tmp_path):
    folder = draft(carousels)
    review.approve(folder, "Kint", NOW)
    status, _ = reply(post({"action": "posted", "folder": NAME, "account": "tpm-instagram",
                            "url": "https://www.instagram.com/p/abc123/"}))
    assert status == 200
    assert status_of(folder) == "posted"
    assert "tpm-instagram" in (tmp_path / "post-log.csv").read_text(encoding="utf-8")


@pytest.mark.parametrize("account", ["tpm-facebook", "tpm-instagram", "david-facebook"])
def test_the_three_allowed_accounts_are_accepted(carousels, account):
    folder = draft(carousels)
    review.approve(folder, "Kint", NOW)
    status, _ = reply(post({"action": "posted", "folder": NAME, "account": account,
                            "url": "https://example.com/post"}))
    assert status == 200


@pytest.mark.parametrize("account", ["david-instagram", "david-personal-instagram", "someone-else", ""])
def test_other_accounts_and_davids_personal_instagram_are_refused(carousels, tmp_path, account):
    folder = draft(carousels)
    review.approve(folder, "Kint", NOW)
    status, _ = reply(post({"action": "posted", "folder": NAME, "account": account,
                            "url": "https://example.com/post"}))
    assert status == 400
    assert not (tmp_path / "post-log.csv").exists()
    assert status_of(folder) == "approved"


# ---- the folder name, and the same-page check ----

@pytest.mark.parametrize("name", ["../../config", "..", "a/b", "C:\\Windows", "", None, 42])
def test_path_tricks_and_odd_folder_names_are_refused(carousels, name):
    draft(carousels)
    status, _ = reply(post({"action": "approve", "folder": name, "reviewer": "Kint"}))
    assert status == 400


def test_a_sample_folder_cannot_be_approved(carousels):
    draft(carousels, name="2026-11-11-canon-eos-r8-mark-ii-sample")
    status, data = reply(post({"action": "approve", "folder": "2026-11-11-canon-eos-r8-mark-ii-sample",
                               "reviewer": "Kint"}))
    assert status == 400 and "sample" in data["error"]


def test_a_request_from_another_site_is_refused_and_changes_nothing(carousels):
    folder = draft(carousels)
    evil = dict(PAGE, origin="https://evil.example")
    status, _ = reply(post({"action": "approve", "folder": NAME, "reviewer": "Kint"}, headers=evil))
    assert status == 403 and status_of(folder) == "draft"


def test_a_request_with_no_origin_is_refused(carousels):
    folder = draft(carousels)
    no_origin = {key: value for key, value in PAGE.items() if key != "origin"}
    status, _ = reply(post({"action": "approve", "folder": NAME, "reviewer": "Kint"}, headers=no_origin))
    assert status == 403 and status_of(folder) == "draft"


def test_a_cross_site_fetch_is_refused_even_with_a_matching_origin(carousels):
    draft(carousels)
    headers = dict(PAGE, **{"sec-fetch-site": "cross-site"})
    status, _ = reply(post({"action": "approve", "folder": NAME, "reviewer": "Kint"}, headers=headers))
    assert status == 403


def test_a_request_addressed_to_another_host_name_is_refused(carousels):
    draft(carousels)
    headers = dict(PAGE, host="evil.example:8765")
    status, _ = reply(post({"action": "approve", "folder": NAME, "reviewer": "Kint"}, headers=headers))
    assert status == 403


def test_the_body_must_be_json(carousels):
    draft(carousels)
    status, _ = reply(post(None, headers=dict(PAGE, **{"content-type": "text/plain"}), raw=b"{}"))
    assert status == 415
    status, _ = reply(post(None, raw=b"not json"))
    assert status == 400


def test_an_unknown_action_is_refused(carousels):
    draft(carousels)
    status, _ = reply(post({"action": "delete", "folder": NAME}))
    assert status == 400


# ---- what the server will read from the disk ----

def test_only_the_dashboard_and_output_folders_are_served(tmp_path, monkeypatch):
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "index.html").write_text("<html>page</html>", encoding="utf-8")
    (tmp_path / "output" / "carousels" / NAME).mkdir(parents=True)
    (tmp_path / "output" / "carousels" / NAME / "01.png").write_bytes(b"png")
    (tmp_path / ".env").write_text("SLACK_WEBHOOK_URL=https://hooks.slack.com/services/x", encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "rules.yaml").write_text("x: 1", encoding="utf-8")
    headers = {"host": "127.0.0.1:8765"}

    status, kind, body = review_server.handle("GET", "/", headers, b"", PORT)
    assert status == 200 and b"page" in body and kind["Content-Type"].startswith("text/html")
    status, kind, _ = review_server.handle("GET", f"/output/carousels/{NAME}/01.png", headers, b"", PORT)
    assert status == 200 and kind["Content-Type"] == "image/png"
    for target in ("/.env", "/config/rules.yaml", "/output/../.env", "/dashboard/../.env",
                   "/output/..%2F.env", "/data/seen.sqlite", "/output\\..\\.env"):
        assert review_server.handle("GET", target, headers, b"", PORT)[0] == 404, target


def test_get_from_another_host_name_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    status, _, _ = review_server.handle("GET", "/", {"host": "evil.example"}, b"", PORT)
    assert status == 403


def test_other_methods_are_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr(review_server, "ROOT", tmp_path)
    status, _, _ = review_server.handle("DELETE", "/api/review", PAGE, b"", PORT)
    assert status == 405


def test_the_server_only_listens_on_the_loopback_address():
    assert review_server.HOST == "127.0.0.1"
    assert review_server.allowed_hosts(8765) == {"127.0.0.1:8765", "localhost:8765"}
