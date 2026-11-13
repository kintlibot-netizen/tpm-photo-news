"""Downloads each news feed and turns it into a simple list of items."""
from __future__ import annotations

import calendar
import html
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import requests

log = logging.getLogger(__name__)


@dataclass
class Item:
    source: str
    source_type: str  # "news" or "rumor"
    title: str
    url: str
    summary: str
    published: datetime | None


def clean_text(raw: str) -> str:
    """Removes HTML tags and extra spaces from feed text."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", raw or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _entry_date(entry) -> datetime | None:
    # A missing date stays missing. We never guess one.
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)


def parse_feed(content: bytes, source: dict) -> list[Item]:
    """Turns raw feed data into items, skipping any without a usable link."""
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"not a readable feed: {parsed.get('bozo_exception')}")
    items = []
    for entry in parsed.entries:
        url = (entry.get("link") or "").strip()
        title = clean_text(entry.get("title", ""))
        if not title or not url.lower().startswith(("http://", "https://")):
            continue
        items.append(
            Item(
                source=source["name"],
                source_type=source["type"],
                title=title,
                url=url,
                summary=clean_text(entry.get("summary", "")),
                published=_entry_date(entry),
            )
        )
    return items


def _download(url: str, settings: dict) -> bytes:
    limit = int(settings.get("max_feed_megabytes", 10)) * 1024 * 1024
    with requests.get(
        url,
        headers={"User-Agent": settings["user_agent"]},
        timeout=settings.get("timeout_seconds", 25),
        stream=True,
    ) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError(f"feed is larger than {limit} bytes")
    return bytes(data)


def fetch_source(source: dict, settings: dict) -> list[Item]:
    attempts = int(settings.get("retries", 1)) + 1
    pause = float(settings.get("retry_pause_seconds", 5))
    error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(pause)  # a short wait, so a brief network drop can clear before the retry
        try:
            return parse_feed(_download(source["url"], settings), source)
        except Exception as exc:  # any single feed problem is a failed feed, never a crash
            error = exc
    raise RuntimeError(f"{source['name']}: {error or 'no attempt was made'}")


def fetch_all(config: dict) -> tuple[list[Item], dict[str, str]]:
    """Fetches every source. One broken or missing feed is skipped and listed as failed; the others still run."""
    items: list[Item] = []
    failures: dict[str, str] = {}
    for source in config["sources"]:
        name = source.get("name", "unnamed feed")
        try:
            found = fetch_source(source, config["fetch"])
            log.info("%s: %d items", name, len(found))
            items.extend(found)
        except Exception as exc:  # a feed that cannot load must never stop the run
            log.warning("feed failed: %s", exc)
            failures[name] = str(exc)
    return items, failures
