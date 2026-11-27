"""The Inspiration section of the dashboard: credited reference cards from official photo sources (data/inspiration/).

Each card names the photographer exactly as the source credits them, links to the official page, and gives the
photo lesson and a TPM content idea. The cards are link only: no image from the source is copied, embedded or
hot-linked, and the copyright note always sits at the top. The same cards show on Kint's page and David's copy.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from dashboard_assets import icon

ROOT = Path(__file__).resolve().parent.parent
INSPIRATION_DIR = ROOT / "data" / "inspiration"
REQUIRED = ("title", "photographer", "location", "category", "lesson", "tpm_idea", "url")
DASHES = ("\u2014", "\u2013")


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _official(url) -> str | None:
    """Only https links to nationalgeographic.com are shown."""
    if isinstance(url, str) and url.startswith("https://www.nationalgeographic.com/"):
        return url
    return None


def load_boards(folder: Path | None = None) -> list[dict]:
    """Every board in the folder, with only the cards that carry every required field and an official link."""
    folder = Path(folder) if folder is not None else INSPIRATION_DIR
    boards = []
    if not folder.is_dir():
        return boards
    for path in sorted(folder.glob("*.json")):
        try:
            board = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = [i for i in board.get("items", [])
                 if all(i.get(k) for k in REQUIRED) and _official(i.get("url"))]
        if items and board.get("copyright_note"):
            boards.append(dict(board, items=items))
    return boards


def _clean(text) -> str:
    text = str(text or "")
    for dash in DASHES:
        text = text.replace(f" {dash} ", ", ").replace(dash, ", ")
    return text


def card(item: dict) -> str:
    url = _official(item["url"])
    more = item.get("more") or {}
    more_url = _official(more.get("url"))
    more_html = (f'<a class="insp-more" href="{esc(more_url)}" target="_blank" rel="noopener noreferrer">'
                 f'{esc(_clean(more.get("label") or "More on National Geographic"))}</a>' if more_url else "")
    credit = item.get("credit") or f'Photo by {item["photographer"]} for National Geographic'
    return (f'<li class="insp-card" data-cat="{esc(item["category"])}">'
            f'<div class="insp-top"><span class="pill p-official">{esc(_clean(item["category"]))}</span>'
            f'<span class="insp-loc">{esc(_clean(item["location"]))}</span></div>'
            f'<h3 class="insp-title"><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">'
            f'{esc(_clean(item["title"]))}</a></h3>'
            f'<p class="insp-credit">{icon("image")}<span>{esc(_clean(credit))}</span></p>'
            + (f'<p class="insp-sub">{esc(_clean(item["subject"]))}</p>' if item.get("subject") else "")
            + f'<dl class="insp-dl"><dt>Lesson</dt><dd>{esc(_clean(item["lesson"]))}</dd>'
            f'<dt>TPM idea</dt><dd>{esc(_clean(item["tpm_idea"]))}</dd></dl>'
            f'<div class="insp-links"><a class="insp-src" href="{esc(url)}" target="_blank" '
            f'rel="noopener noreferrer">View on National Geographic</a>{more_html}</div></li>')


def panel(boards: list[dict] | None = None) -> str:
    boards = load_boards() if boards is None else boards
    if not boards:
        return ""
    out = []
    for board in boards:
        items = board["items"]
        cats = []
        for i in items:
            if i["category"] not in cats:
                cats.append(i["category"])
        chips = "".join(f'<span class="tag st-accent">{esc(_clean(c))}: '
                        f'{sum(1 for i in items if i["category"] == c)}</span>' for c in cats)
        links = "".join(f'<li><a href="{esc(_official(l.get("url")))}" target="_blank" rel="noopener noreferrer">'
                        f'{esc(_clean(l.get("label")))}</a></li>'
                        for l in board.get("links", []) if _official(l.get("url")))
        out.append(
            f'<div class="insp-note" role="note">{icon("lock")}<span>{esc(_clean(board["copyright_note"]))}</span></div>'
            f'<div class="insp-head"><h2>{esc(_clean(board.get("name")))}</h2>'
            f'<span class="count">{len(items)} picks</span></div>'
            f'<div class="insp-chips">{chips}</div>'
            f'<ul class="insp-grid">{"".join(card(i) for i in items)}</ul>'
            + (f'<p class="insp-format">Credit format for TPM posts: '
               f'{esc(_clean(board.get("credit_format")))}</p>' if board.get("credit_format") else "")
            + (f'<ul class="insp-sources">{links}</ul>' if links else ""))
    return "".join(out)


CSS = r"""
/* Inspiration: link only reference cards, no images */
.insp-note{display:flex;gap:10px;align-items:flex-start;padding:12px 16px;border-radius:var(--r2);
background:var(--accent-tint);border:1px solid var(--accent-line);color:var(--accent-ink);font-size:var(--t-sm)}
.insp-note .ic{width:17px;height:17px;margin-top:2px}
.insp-head{display:flex;align-items:baseline;gap:var(--s2);margin-top:var(--s3)}
.insp-head h2{font-size:var(--t-xl);font-weight:600;margin-right:auto}
.insp-head .count{font-size:var(--t-xs);color:var(--muted);font-weight:600}
.insp-chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 var(--s2)}
.insp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:var(--s2)}
.insp-card{display:flex;flex-direction:column;gap:8px;padding:18px;background:var(--surface);border:1px solid var(--line);
border-radius:var(--r3);box-shadow:var(--shadow);border-top:3px solid var(--accent);transition:box-shadow .15s}
.insp-card:hover{box-shadow:var(--shadow-hover)}
.insp-top{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.insp-loc{font-size:var(--t-xs);color:var(--muted)}
.insp-title{font-size:var(--t-lg);font-weight:600;line-height:1.35}
.insp-title a{color:var(--ink);text-decoration:none}
.insp-title a:hover{color:var(--accent);text-decoration:underline}
.insp-credit{display:flex;align-items:center;gap:6px;font-size:var(--t-sm);font-weight:600;color:var(--accent-ink)}
.insp-credit .ic{width:15px;height:15px}
.insp-sub{font-size:var(--t-sm);color:var(--ink-2)}
.insp-dl{display:grid;grid-template-columns:auto 1fr;gap:6px 10px;font-size:var(--t-sm)}
.insp-dl dt{font-weight:600;color:var(--muted);font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.04em;padding-top:2px}
.insp-dl dd{color:var(--ink-2)}
.insp-links{display:flex;flex-wrap:wrap;gap:8px 14px;margin-top:auto;padding-top:6px;font-size:var(--t-sm);font-weight:600}
.insp-format{margin-top:var(--s3);font-size:var(--t-sm);color:var(--muted)}
.insp-sources{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:8px;font-size:var(--t-sm)}
@media (max-width:720px){.insp-grid{grid-template-columns:1fr}.insp-card{padding:14px}}
"""
