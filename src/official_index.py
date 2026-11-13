"""Finds a brand's official post for a story from its own site index (for Adobe, blog.adobe.com's JSON index).

The index is a JSON file with a "data" list of {path, title, date, image, imageAlt, description, tags}.
"date" is an Excel serial day number (an int), sometimes missing or a text date. Article URL = base + path.
A post matches when its title contains every anchor word (the product name, the year, the model name).
Among matches, posts within window_days of the story come first, newest first.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import requests

from official import USER_AGENT

EXCEL_EPOCH = datetime(1899, 12, 30, tzinfo=timezone.utc)


def excel_date(value) -> datetime | None:
    """An Excel serial day number (or an ISO text date). None when missing or unreadable."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return EXCEL_EPOCH + timedelta(days=float(value))
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _tag_text(tags) -> str:
    if isinstance(tags, list):
        return " ".join(str(t.get("title", t)) if isinstance(t, dict) else str(t) for t in tags)
    return str(tags or "")


def parse_index(data: dict, base: str) -> list[dict]:
    """Posts from the index, with absolute URLs and parsed dates. 'search' is the title, description and tags."""
    posts = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        title = str(item.get("title") or "")
        description = str(item.get("description") or "")
        tags = _tag_text(item.get("tags"))
        posts.append({
            "url": base.rstrip("/") + path,
            "title": title,
            "date": excel_date(item.get("date")),
            "description": description,
            "search": f"{title} {description} {tags}".lower(),
        })
    return posts


STOP_FEATURE_WORDS = {
    "photos", "camera", "biggest", "coming", "updates", "update", "these", "about", "there", "which",
    "their", "with", "from", "that", "this", "would", "could", "should", "photo", "more", "adobe",
}


def feature_terms(title: str, product_terms: list[str]) -> list[str]:
    """Feature words from a story title: longer words that are not the product or generic words."""
    words = set(re.findall(r"[a-z][a-z-]{4,}", title.lower()))
    excluded = {t.lower() for t in product_terms} | STOP_FEATURE_WORDS
    return sorted(w for w in words if w not in excluded)


def candidate_pool(posts: list[dict], story_date: datetime | None, window_days: int,
                   product_terms: list[str]) -> list[dict]:
    """Every post within window_days of the story is a candidate, at most 12. Posts naming the product in
    the title, description or tags come first, then newest first."""
    if story_date is None:
        return []
    terms = [t.lower() for t in product_terms if t]
    # Big launch posts (e.g. Adobe MAX round-ups) often don't name the product in the title or
    # description, so every post in the window is a candidate. Posts naming the product rank first;
    # the body check in best_by_body decides.
    pool = [
        p for p in posts
        if p["date"] is not None and abs((p["date"] - story_date).days) <= window_days
    ]
    pool.sort(key=lambda p: (any(t in p["search"] for t in terms), p["date"]), reverse=True)
    return pool[:12]


def best_by_body(pool: list[dict], fetch_text, product_terms: list[str], features: list[str],
                 min_product: int = 2, min_feature: int = 2) -> dict | None:
    """Fetches each candidate's body and scores it by product and feature mentions.

    Returns the best post that mentions the product at least min_product times and the features at least
    min_feature times, or None. fetch_text(url) returns the page's visible text; failures skip the post.
    """
    best = None
    for post in pool:
        try:
            body = fetch_text(post["url"]).lower()
        except Exception:  # an unreadable post is skipped, never fatal
            continue
        product_hits = sum(body.count(t.lower()) for t in product_terms if t)
        feature_hits = sum(body.count(f) for f in features)
        if product_hits < min_product or feature_hits < min_feature:
            continue
        score = product_hits + feature_hits
        if best is None or score > best["score"]:
            best = {"url": post["url"], "title": post["title"], "score": score,
                    "product_hits": product_hits, "feature_hits": feature_hits}
    return best


def find_posts(posts: list[dict], anchors: list[str], story_date: datetime | None,
               window_days: int = 14) -> list[dict]:
    """Matching posts, best first: within the window of the story date, then newest first."""
    anchors = [a.lower() for a in anchors if a]
    matches = [p for p in posts if anchors and all(a in p["title"].lower() for a in anchors)]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def in_window(post) -> bool:
        if story_date is None or post["date"] is None:
            return False
        return abs((post["date"] - story_date).days) <= window_days

    matches.sort(key=lambda p: p["date"] or epoch, reverse=True)
    return [p for p in matches if in_window(p)] + [p for p in matches if not in_window(p)]


def fetch_index(url: str) -> dict:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    return response.json()


def helpx_status(url: str) -> tuple[str, str]:
    """('found', text) or ('missing', reason). A 403 counts as not found; no hard retries."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    except requests.RequestException as exc:
        return "missing", type(exc).__name__
    if response.status_code == 403:
        return "missing", "403 (the site refuses automated reads)"
    if response.status_code != 200:
        return "missing", f"HTTP {response.status_code}"
    return "found", response.text
