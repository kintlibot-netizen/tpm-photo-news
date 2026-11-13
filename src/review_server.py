"""A local server that lets the dashboard approve, reject and log posts with its buttons.

python src\\review_server.py          Serves http://127.0.0.1:8765/ (uses 8766 to 8775 if 8765 is taken).
python src\\review_server.py --open   The same, and opens the page in the default browser.

Standard library only. It listens on 127.0.0.1 only, never on the network.
  - GET serves dashboard/ and output/ read-only. Nothing else on the disk is served.
  - POST /api/review approves, rejects or logs a post, by calling the functions in review.py.
    It needs the request to come from this same page (Origin check), a JSON body, and a Host of 127.0.0.1 or localhost.
  - GET /api/download/... gives a carousel zip, one slide, or every approved carousel in one zip (downloads.py).
  - POST /api/export builds the read only share pack for David (share_pack.py), with the same checks as /api/review.
  - Every refusal is JSON: {"ok": false, "error": "..."}. Every review action and download goes to the activity log.
  - Folder names are checked against output/carousels. Path tricks are refused.
  - Only TPM Facebook, TPM Instagram and David Facebook can be logged, and David's personal Instagram is refused.
Nothing here posts to social media.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import activity
import downloads
import review

ROOT = Path(__file__).resolve().parent.parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_TRIES = 11
MAX_BODY = 16 * 1024
NAME_LIMIT = 60
REASON_LIMIT = 200
URL_LIMIT = 400
ACCOUNTS = ("tpm-facebook", "tpm-instagram", "david-facebook")
ACTIONS = ("approve", "reject", "posted")
FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8", ".json": "application/json",
    ".csv": "text/csv; charset=utf-8", ".css": "text/css", ".zip": "application/zip",
}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}

Response = tuple[int, dict, bytes]


def served_roots() -> dict[str, Path]:
    """The only folders the server reads. The secrets file, the data folder and the code are never served."""
    return {"dashboard": ROOT / "dashboard", "output": ROOT / "output"}


def allowed_hosts(port: int) -> set[str]:
    return {f"{HOST}:{port}", f"localhost:{port}"}


def allowed_origins(port: int) -> set[str]:
    return {f"http://{HOST}:{port}", f"http://localhost:{port}"}


def _json(status: int, payload: dict) -> Response:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return status, {"Content-Type": "application/json; charset=utf-8", **SECURITY_HEADERS}, body


def _refuse(status: int, error: str) -> Response:
    """Every refusal has the same JSON body, so the page can always read the reason."""
    return _json(status, {"ok": False, "error": error})


def serve_file(target: str) -> Response:
    """A file from dashboard/ or output/. Anything outside those two folders is a 404."""
    path = unquote(urlsplit(target).path)
    relative = "dashboard/index.html" if path in ("", "/") else path.lstrip("/")
    parts = relative.split("/")
    roots = served_roots()
    if len(parts) < 2 or parts[0] not in roots or "\\" in relative or "\x00" in relative:
        return _refuse(404, "Not found.")
    base = roots[parts[0]].resolve()
    candidate = base.joinpath(*parts[1:]).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return _refuse(404, "Not found.")
    kind = CONTENT_TYPES.get(candidate.suffix.lower()) or mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return 200, {"Content-Type": kind, **SECURITY_HEADERS}, candidate.read_bytes()


def same_page(headers: dict, port: int) -> bool:
    """Only requests that came from this server's own page. A page on another site cannot send them."""
    host = headers.get("host", "")
    origin = headers.get("origin")
    if host not in allowed_hosts(port) or origin is None or origin not in allowed_origins(port):
        return False
    return headers.get("sec-fetch-site", "same-origin") in ("same-origin", "none")


def clean_text(value, limit: int, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise review.ReviewError(f"{what} is needed.")
    text = " ".join(value.split())
    if len(text) > limit:
        raise review.ReviewError(f"{what} is too long (at most {limit} characters).")
    return text


def optional_name(value) -> str:
    """The reviewer name typed on the page, when there is one (it is only recorded in the activity log)."""
    if not isinstance(value, str) or not value.strip():
        return ""
    return " ".join(value.split())[:NAME_LIMIT]


def carousel_folder(name) -> Path:
    """The folder named in the request, which must be a plain name directly inside output/carousels."""
    if not isinstance(name, str) or not FOLDER_NAME.match(name):
        raise review.ReviewError("That is not a carousel folder name.")
    base = review.CAROUSELS.resolve()
    folder = (base / name).resolve()
    if folder.parent != base or not folder.is_dir():
        raise review.ReviewError("No carousel folder has that name.")
    return review.resolve_folder(str(folder))


def api_review(headers: dict, body: bytes, port: int, now: datetime) -> Response:
    if not same_page(headers, port):
        return _refuse(403, "Refused: this request did not come from the review page.")
    content_type = headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return _refuse(415, "The review page must send JSON.")
    if len(body) > MAX_BODY:
        return _refuse(413, "The request is too large.")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _refuse(400, "The request was not readable JSON.")
    if not isinstance(data, dict):
        return _refuse(400, "The request was not in the expected form.")
    action = data.get("action")
    if action not in ACTIONS:
        return _refuse(400, "Unknown action.")
    try:
        folder = carousel_folder(data.get("folder"))
        if action == "approve":
            reviewer = clean_text(data.get("reviewer"), NAME_LIMIT, "Your name")
            review.approve(folder, reviewer, now)
            message = f"Approved by {reviewer}. The files are in ready-to-post. Post them by hand, then log the post."
        elif action == "reject":
            reason = clean_text(data.get("reason"), REASON_LIMIT, "A reason")
            review.reject(folder, reason, now, by=optional_name(data.get("reviewer")))
            message = "Rejected. The reason is saved with the draft."
        else:
            account = data.get("account")
            if account not in ACCOUNTS:
                review.refuse_personal_instagram(str(account or ""))
                raise review.ReviewError("Choose TPM Facebook, TPM Instagram or David Facebook.")
            url = clean_text(data.get("url"), URL_LIMIT, "The link to the post")
            review.log_post(folder, account, url, now, review.POST_LOG, by=optional_name(data.get("reviewer")))
            message = f"Logged the post to {account}."
    except review.ReviewError as exc:
        return _refuse(400, str(exc))
    return _json(200, {"ok": True, "message": message})


def download_folder(name) -> Path:
    """A carousel or sample folder named in a download address. Plain names only, no path tricks."""
    if not isinstance(name, str) or not FOLDER_NAME.match(name):
        raise review.ReviewError("That is not a carousel folder name.")
    for base in (review.CAROUSELS, ROOT / "output" / "samples"):
        root = base.resolve()
        folder = (root / name).resolve()
        if folder.parent == root and folder.is_dir() and (folder / "captions.txt").exists():
            return folder
    raise review.ReviewError("No carousel folder has that name.")


def _attachment(kind: str, filename: str, body: bytes) -> Response:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "download"
    return 200, {"Content-Type": kind, "Content-Disposition": f'attachment; filename="{safe}"',
                 **SECURITY_HEADERS}, body


def api_download(path: str, headers: dict, now: datetime) -> Response:
    """GET /api/download/carousel/<folder>       the carousel zip (slides in order, captions, sources)
       GET /api/download/slide/<folder>/<NN>.png one slide, with its friendly name
       GET /api/download/approved                every approved carousel in one zip
    A link on another site cannot start one (Sec-Fetch-Site). Each download is written to the activity log."""
    if headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        return _refuse(403, "Refused: downloads start from the review page.")
    parts = [unquote(p) for p in path.split("/")[3:]]
    try:
        if parts == ["approved"]:
            data, count = downloads.approved_zip_bytes(review.CAROUSELS)
            name = f"TPM-approved-carousels-{now.astimezone(activity.MANILA):%Y-%m-%d}.zip"
            activity.log_event("download", "approved zip", f"All approved carousels ({count}) as {name}", now=now)
            return _attachment("application/zip", name, data)
        if len(parts) == 2 and parts[0] == "carousel":
            folder = download_folder(parts[1])
            if not downloads.slides(folder):
                raise review.ReviewError("This carousel has no slides yet.")
            name = downloads.zip_name(folder)
            data = downloads.zip_bytes(folder)
            activity.log_event("download", "carousel zip", f"{name} ({len(data) // 1024} KB)", now=now)
            return _attachment("application/zip", name, data)
        if len(parts) == 3 and parts[0] == "slide" and re.fullmatch(r"\d\d\.png", parts[2]):
            folder = download_folder(parts[1])
            name = downloads.slide_download_name(folder, parts[2])
            if name is None:
                raise review.ReviewError("No slide has that number.")
            activity.log_event("download", "slide", name, now=now)
            return _attachment("image/png", name, (folder / parts[2]).read_bytes())
    except review.ReviewError as exc:
        return _refuse(404, str(exc))
    return _refuse(404, "Not found.")


def api_export(headers: dict, body: bytes, port: int, now: datetime) -> Response:
    """POST /api/export: builds the read only share pack for David (output/share). Same checks as the review buttons."""
    if not same_page(headers, port):
        return _refuse(403, "Refused: this request did not come from the review page.")
    content_type = headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return _refuse(415, "The review page must send JSON.")
    import share_pack  # imported here: the export is only loaded when it is asked for
    try:
        result = share_pack.export_pack(now=now)
    except share_pack.ExportError as exc:
        return _refuse(500, f"The export was not made: {exc}")
    zip_name = result["zip"].name
    return _json(200, {
        "ok": True,
        "message": (f"Export ready: {zip_name} ({result['size_mb']:.1f} MB). Send this zip to David, or upload "
                    "the output\\share\\latest folder to a web host and send him the link."),
        "download": f"/output/share/{zip_name}",
    })


def handle(method: str, target: str, headers: dict, body: bytes, port: int = DEFAULT_PORT,
           now: datetime | None = None) -> Response:
    """Every request goes through here, so the tests can call it without opening a socket."""
    now = now or datetime.now(timezone.utc)
    if headers.get("host", "") not in allowed_hosts(port):
        return _refuse(403, "Refused: the host name is not this server.")
    path = urlsplit(target).path
    if method == "GET" and path.startswith("/api/download/"):
        return api_download(path, headers, now)
    if method == "GET":
        return serve_file(target)
    if method == "POST" and path == "/api/review":
        return api_review(headers, body, port, now)
    if method == "POST" and path == "/api/export":
        return api_export(headers, body, port, now)
    if method == "POST":
        return _refuse(404, "Not found.")
    return _refuse(405, "Only GET and POST are used here.")


class Handler(BaseHTTPRequestHandler):
    server_version = "TPMReview"
    sys_version = ""

    def do_GET(self) -> None:
        self._reply(handle("GET", self.path, self._headers(), b"", self.server.server_port))

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._reply(_refuse(413, "The request is too large."))
            return
        body = self.rfile.read(length) if length else b""
        self._reply(handle("POST", self.path, self._headers(), body, self.server.server_port))

    def do_HEAD(self) -> None:
        self._reply(_refuse(405, "Only GET and POST are used here."))

    def _headers(self) -> dict:
        return {key.lower(): value for key, value in self.headers.items()}

    def _reply(self, response: Response) -> None:
        status, headers, body = response
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args) -> None:  # keeps the console quiet; request details are never logged
        return


def bind(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Listens on 127.0.0.1 only, on the first free port from `port` up to 10 more."""
    last_error: OSError | None = None
    for candidate in range(port, port + PORT_TRIES):
        try:
            return ThreadingHTTPServer((HOST, candidate), Handler)
        except OSError as exc:
            last_error = exc
    raise OSError(f"No free port from {port} to {port + PORT_TRIES - 1}: {last_error}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local review server for the dashboard. Posts nothing.")
    parser.add_argument("--open", action="store_true", help="open the dashboard in the browser")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="first port to try (default 8765)")
    args = parser.parse_args(argv)
    try:
        import dashboard  # the page is rebuilt first, so it shows the latest data and the activity log
        dashboard.write_dashboard()
    except Exception as exc:  # an old page still works; the next watcher run rebuilds it
        print(f"The dashboard page was not rebuilt ({type(exc).__name__}). Showing the last saved page.")
    try:
        server = bind(args.port)
    except OSError as exc:
        print(f"Could not start the review server: {exc}")
        return 1
    url = f"http://{HOST}:{server.server_port}/"
    print(f"Review dashboard running at {url}")
    print("Keep this window open while you review. Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
