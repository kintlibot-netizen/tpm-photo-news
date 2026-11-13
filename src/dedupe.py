"""Recognizes when two articles are the same story, and remembers what was alerted."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fetch import Item

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref", "source")
NON_MODEL = re.compile(r"^(\d+(mp|fps|k|p|gb|tb|bit|x)|(19|20)\d\d|\d+(st|nd|rd|th)|\d+)$")
ROMAN = {"ii", "iii", "iv", "v", "vi", "vii"}
# Two-capital words that are not model names (AI, USB...). Other two-capital words, such as ZR, are model names.
CAPS_STOP = {
    "AI", "TV", "UK", "US", "EU", "PC", "OK", "AM", "PM", "VS", "NO", "OR", "IT", "IS", "TO", "OF", "IN",
    "ON", "AT", "UP", "BY", "GO", "DO", "HD", "UI", "VR", "AF", "AE", "ND", "BW", "ID", "AN", "WE", "ME",
    "MY", "II", "VI",
}
# Words that come before a bare number as a verb, not as a product name ("Announces 2 lenses").
VERBS = {
    "announces", "announced", "announcing", "unveils", "unveiled", "launches", "launched", "introduces",
    "introduced", "releases", "released", "debuts", "reveals", "revealed", "brings", "adds", "gets", "has",
    "is", "offers", "delivers", "ships", "updates", "updated", "teases", "lists", "sells", "drops", "with",
    "for", "and", "the", "a", "an", "of", "to", "in", "at", "on", "from", "by", "as",
}


def canonical_url(url: str) -> str:
    """Removes tracking codes so the same link always looks the same."""
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(TRACKING_PREFIXES)
    ]
    host = parts.netloc.lower().removeprefix("www.")
    return urlunsplit(("https", host, parts.path.rstrip("/").lower(), urlencode(query), ""))


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


class BrandMap(dict):
    """Brand name -> list of aliases. `guards` maps an alias that is also an ordinary word (Sigma, Kodak)
    to the context words that must appear in the same text before it counts as the brand."""

    guards: dict[str, list[str]] = {}


def guard_ok(alias: str, text: str, guards: dict[str, list[str]]) -> bool:
    """True when an alias with a guard has one of its context words, or a model number right after it."""
    words = guards.get(alias.lower())
    if not words:
        return True
    pattern = "|".join(re.escape(word) for word in words)
    if re.search(rf"\b(?:{pattern})\b", text, re.I):
        return True
    return re.search(rf"\b{re.escape(alias)}\s+\d", text, re.I) is not None


def find_brand(title: str, brands: dict[str, list[str]]) -> str | None:
    """Returns the brand named first in a title."""
    lowered = title.lower()
    guards = getattr(brands, "guards", {})
    best: tuple[int, str] | None = None
    for brand, aliases in brands.items():
        for alias in aliases:
            if not guard_ok(alias, title, guards):
                continue
            match = re.search(rf"\b{re.escape(alias.lower())}\b", lowered)
            if match and (best is None or match.start() < best[0]):
                best = (match.start(), brand)
    return best[1] if best else None


# A brand right after one of these words is a comparison, not the product's maker ("beaten Sony's").
COMPARISON_BEFORE = re.compile(
    r"\b(beaten|beats?|beat|than|vs\.?|versus|rivals?|outsell\w*|against|surpass\w*)\s+(?:\S+\s+){0,2}$",
    re.I,
)


def _named_brands(text: str, brands: dict[str, list[str]]) -> list[tuple[bool, str]]:
    """Every brand named in a text, in order, marked True when it only appears as a comparison."""
    found: list[tuple[int, bool, str]] = []
    guards = getattr(brands, "guards", {})
    for brand, aliases in brands.items():
        for alias in aliases:
            if not guard_ok(alias, text, guards):
                continue
            for match in re.finditer(rf"\b{re.escape(alias.lower())}\b", text.lower()):
                before = text[max(0, match.start() - 40):match.start()]
                found.append((match.start(), bool(COMPARISON_BEFORE.search(before)), brand))
    return [(compared, brand) for _, compared, brand in sorted(found)]


def find_story_brand(title: str, excerpt: str, brands: dict[str, list[str]]) -> str | None:
    """The brand of the product in a story, not a brand named only as a comparison.

    "...has even beaten Sony's 33MP camera" names Sony only as a comparison. Then the first
    product brand in the excerpt is used instead.
    """
    named = _named_brands(title, brands)
    if not named:
        return None
    for compared, brand in named:
        if not compared:
            return brand
    for compared, brand in _named_brands(excerpt or "", brands):
        if not compared:
            return brand
    return None


def brand_from_sources(sources: list[dict], brands: dict[str, list[str]]) -> str | None:
    for src in sources:
        found = find_story_brand(src.get("title") or "", src.get("summary") or "", brands)
        if found:
            return found
    return None


def model_tokens(title: str) -> frozenset[str]:
    """Pulls out model parts, so 'EOS R6 Mark III' and 'R6III' match."""
    text = title.lower().replace("’", "'").replace("f/", "f")
    text = re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9])", "", text)
    text = re.sub(r"\b\d+(\.\d+)?\s*(mp|megapixels?)\b", " ", text)
    text = re.sub(r"\b([a-z]+\d+[a-z]??)(iii|ii|iv|vii|vi|v)\b", r"\1 \2", text)
    text = re.sub(r"\bmark\s+", " ", text)
    words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text)
    tokens: set[str] = set()
    for index, word in enumerate(words):
        has_digit = any(c.isdigit() for c in word)
        if has_digit and not NON_MODEL.match(word):
            tokens.add(word)
        elif word in ROMAN and index and any(c.isdigit() for c in words[index - 1]):
            tokens.add(word)
    # Two-capital product codes such as "ZR" in "Nikon ZR firmware".
    for word in re.findall(r"\b[A-Z]{2}\b", title):
        if word not in CAPS_STOP:
            tokens.add(word.lower())
    # A bare number that names a product, such as "1" in "Cine Play 1 Plus". Not a verb before a number
    # ("Announces 2 lenses"), and only when a capitalized word follows it, as in a product name.
    original = re.findall(r"[A-Za-z0-9]+(?:\.[0-9]+)?", title)
    for index in range(1, len(original) - 1):
        number, before, after = original[index], original[index - 1], original[index + 1]
        if (number.isdigit() and len(number) <= 2 and before.isalpha() and before[0].isupper()
                and before.lower() not in VERBS and after[0].isupper()):
            tokens.add(f"{before.lower()} {number}")
    return frozenset(tokens)


def story_kind(title: str) -> str:
    return "firmware" if re.search(r"\bfirmware\b", title, re.I) else "product"


SCHEDULE_WORDS = re.compile(
    r"\b(delay|delays|delayed|postponed|pushed back|slipped|scrapped|cancelled|canceled|off the table)\b",
    re.I,
)


def story_claim(title: str) -> str:
    """A report about timing (delay, cancellation) is a different claim from product news about the same model."""
    return "schedule" if SCHEDULE_WORDS.search(title) else "product"


def title_similarity(a: str, b: str) -> float:
    left, right = set(normalize_title(a).split()), set(normalize_title(b).split())
    return len(left & right) / len(left | right) if left and right else 0.0


@dataclass
class Story:
    """One piece of news, possibly reported by several sites."""

    title: str
    brand: str | None
    kind: str
    tokens: frozenset[str]
    id: int | None = None
    last_alert_label: str | None = None
    claude_label: str | None = None
    dismissed: bool = False
    first_seen: datetime | None = None
    sources: list[dict] = field(default_factory=list)
    has_new_item: bool = False
    skipped: str | None = None  # why the current rules skip it (set when it was never alerted)
    review_version: str | None = None  # the rules version Claude's label or rejection was made under


def same_story(a: Story, b: Story, threshold: float) -> bool:
    if story_claim(a.title) != story_claim(b.title):
        # Two different claims about one camera (a delay vs. a spec rumor) are not two sources for each other.
        return False
    if a.brand and a.brand == b.brand and a.kind == b.kind and a.tokens and b.tokens:
        return a.tokens <= b.tokens or b.tokens <= a.tokens
    if a.tokens and b.tokens and a.brand and b.brand:
        return False
    return title_similarity(a.title, b.title) >= threshold


class Store:
    """The watcher's memory, kept in data/seen.sqlite."""

    def __init__(self, path: str | Path = ":memory:", read_only_copy: bool = False):
        if read_only_copy:
            # Dry runs work on a throwaway copy, so a later real run still alerts.
            self.db = sqlite3.connect(":memory:")
            if Path(path).exists():
                disk = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
                disk.backup(self.db)
                disk.close()
        else:
            if str(path) != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(str(path))
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY, title TEXT, brand TEXT, kind TEXT,
                tokens TEXT, last_alert_label TEXT, dismissed INTEGER DEFAULT 0,
                first_seen TEXT);
            CREATE TABLE IF NOT EXISTS sources (
                url TEXT PRIMARY KEY, story_id INTEGER, source TEXT, source_type TEXT,
                title TEXT, summary TEXT, published TEXT, link TEXT);
            """
        )
        # Older databases get new columns added once. Existing values are kept.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(stories)").fetchall()}
        for name in ("claude_label", "skipped", "review_version"):
            if name not in columns:
                self.db.execute(f"ALTER TABLE stories ADD COLUMN {name} TEXT")
        self.db.commit()

    def url_seen(self, url: str) -> bool:
        row = self.db.execute("SELECT 1 FROM sources WHERE url=?", (url,)).fetchone()
        return row is not None

    def recent_stories(self, window_days: int, now: datetime) -> list[Story]:
        cutoff = (now - timedelta(days=window_days)).isoformat()
        stories = []
        for row in self.db.execute(
            "SELECT id,title,brand,kind,tokens,last_alert_label,dismissed,first_seen,claude_label,"
            "skipped,review_version FROM stories WHERE first_seen>=?",
            (cutoff,),
        ).fetchall():
            story = Story(
                title=row[1], brand=row[2], kind=row[3],
                tokens=frozenset(json.loads(row[4])), id=row[0],
                last_alert_label=row[5], dismissed=bool(row[6]),
                first_seen=datetime.fromisoformat(row[7]), claude_label=row[8],
                skipped=row[9], review_version=row[10],
            )
            story.sources = [
                dict(zip(("url", "source", "source_type", "title", "summary", "published", "link"), r))
                for r in self.db.execute(
                    "SELECT url,source,source_type,title,summary,published,link "
                    "FROM sources WHERE story_id=?",
                    (story.id,),
                ).fetchall()
            ]
            stories.append(story)
        return stories

    def save_story(self, story: Story, now: datetime) -> None:
        if story.id is None:
            story.first_seen = now
            cursor = self.db.execute(
                "INSERT INTO stories(title,brand,kind,tokens,first_seen) VALUES(?,?,?,?,?)",
                (story.title, story.brand, story.kind,
                 json.dumps(sorted(story.tokens)), now.isoformat()),
            )
            story.id = cursor.lastrowid
        for src in story.sources:
            self.db.execute(
                "INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?)",
                (src["url"], story.id, src["source"], src["source_type"],
                 src["title"], src["summary"], src["published"], src.get("link")),
            )
        self.db.commit()

    def mark_alerted(self, story: Story, label: str) -> None:
        story.last_alert_label = label
        self.db.execute("UPDATE stories SET last_alert_label=? WHERE id=?", (label, story.id))
        self.db.commit()

    def set_claude_label(self, story: Story, label: str, version: str | None = None) -> None:
        story.claude_label = label
        story.review_version = version
        self.db.execute(
            "UPDATE stories SET claude_label=?, review_version=? WHERE id=?", (label, version, story.id))
        self.db.commit()

    def mark_dismissed(self, story: Story, version: str | None = None) -> None:
        story.dismissed = True
        story.review_version = version
        self.db.execute(
            "UPDATE stories SET dismissed=1, review_version=? WHERE id=?", (version, story.id))
        self.db.commit()

    def mark_skipped(self, story: Story, reason: str) -> None:
        story.skipped = reason
        self.db.execute("UPDATE stories SET skipped=? WHERE id=?", (reason, story.id))
        self.db.commit()

    def clear_skipped(self, story: Story) -> None:
        story.skipped = None
        self.db.execute("UPDATE stories SET skipped=NULL WHERE id=?", (story.id,))
        self.db.commit()

    def reset_claude_label(self, story: Story) -> None:
        """Forgets an old Claude label, so the current rules decide again. Rejections are kept."""
        story.claude_label = None
        story.review_version = None
        self.db.execute(
            "UPDATE stories SET claude_label=NULL, review_version=NULL WHERE id=?", (story.id,))
        self.db.commit()

    def set_brand(self, story: Story, brand: str) -> None:
        story.brand = brand
        self.db.execute("UPDATE stories SET brand=? WHERE id=?", (brand, story.id))
        self.db.commit()


def group_into_stories(
    items: list[Item], store: Store, window_days: int, threshold: float,
    brands: dict[str, list[str]], now: datetime | None = None,
) -> list[Story]:
    """Attaches new articles to known stories, or starts new ones.

    Returns the stories that gained at least one new article in this run.
    """
    now = now or datetime.now(timezone.utc)
    stories = store.recent_stories(window_days, now)
    urls_this_run: set[str] = set()
    changed: list[Story] = []
    for item in items:
        url = canonical_url(item.url)
        if url in urls_this_run or store.url_seen(url):
            continue
        urls_this_run.add(url)
        candidate = Story(
            title=item.title, brand=find_story_brand(item.title, item.summary, brands),
            kind=story_kind(item.title), tokens=model_tokens(item.title),
        )
        story = next((s for s in stories if same_story(s, candidate, threshold)), None)
        if story is None:
            story = candidate
            stories.append(story)
        story.sources.append(
            {
                "url": url, "link": item.url, "source": item.source,
                "source_type": item.source_type, "title": item.title,
                "summary": item.summary,
                "published": item.published.isoformat() if item.published else None,
            }
        )
        if not story.has_new_item:
            story.has_new_item = True
            changed.append(story)
    for story in changed:
        store.save_story(story, now)
    return changed
