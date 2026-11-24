"""Writes the alert text and delivers it to Slack, or to a file in a dry run."""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import requests

from classify import OFFICIAL, RUMOR, Review, independent_sites
from dedupe import Story

CATEGORY_NAMES = {
    "camera": "Camera", "lens": "Lens", "firmware": "Firmware",
    "photoshop": "Photoshop", "lightroom": "Lightroom", "camera-raw": "Camera Raw",
    "capture-one": "Capture One", "luminar": "Luminar", "dxo": "DxO", "affinity": "Affinity",
    "topaz": "Topaz Labs", "other-software": "Other software", "lighting": "Lighting",
    "storage": "Storage", "gear": "Gear", "industry": "Industry",
}


def escape(text: str) -> str:
    """Stops feed text from triggering Slack mentions or fake links."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def label_line(label: str, story: Story) -> str:
    sites = ", ".join(independent_sites(story))
    if label == RUMOR:
        return f"RUMOR (reported by {sites}. Alert only, no carousel until the brand confirms.)"
    return f"OFFICIAL (reported by {sites}, not yet checked against the brand)"


def format_alert(story: Story, label: str, review: Review, reason: str) -> str:
    lines = []
    if label == OFFICIAL and "official" in reason:
        lines.append("UPDATE: this earlier rumor is now reported as official.")
    lines += [
        f"*{escape(story.title)}*",
        label_line(label, story),
        f"Category: {CATEGORY_NAMES[review.category]}",
        f"Summary: {escape(review.summary)}",
    ]
    if review.reviewed_by_claude and review.reason:
        lines.append(f"Label check: {escape(review.reason)}")
    lines.append("Sources:")
    for source in story.sources:
        link = source.get("link") or source["url"]
        safe = link.replace("|", "%7C").replace("<", "%3C").replace(">", "%3E")
        lines.append(f"- {escape(source['source'])}: {safe}")
    return "\n".join(lines)


def write_dry_run(alerts: list[str], details: str, folder: Path, now: datetime) -> Path:
    """Saves what would have been sent. Nothing goes to Slack."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"dry-run-alerts-{now:%Y%m%d-%H%M%S}.txt"
    divider = "\n\n" + "-" * 60 + "\n\n"
    body = divider.join(alerts) if alerts else "No alerts this run."
    path.write_text(f"DRY RUN. Nothing was sent to Slack.\n\n{body}\n\n{details}\n", encoding="utf-8")
    return path


def webhook_url() -> str:
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url.startswith("https://hooks.slack.com/services/") or "REPLACE" in url:
        raise RuntimeError(
            "SLACK_WEBHOOK_URL is missing or still the placeholder. "
            "Add the real address to .env, or use --dry-run."
        )
    return url


def send_to_slack(text: str, url: str) -> None:
    response = requests.post(url, json={"text": text}, timeout=20)
    response.raise_for_status()
    time.sleep(1.1)  # Stay well under Slack's sending speed limit.
