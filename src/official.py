"""Official announcement pages: which hosts count, reading their text, and the optional hero image.

Only pages on a brand's own domains count as official. Page text is used as the fact source.
The network functions are small and isolated; the parsing functions are plain and tested.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

# A normal desktop browser identity. helpx.adobe.com refuses a plain script identity (HTTPError), and these are public
# official pages, so every official read says it is an ordinary Chrome on Windows.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/131.0.0.0 Safari/537.36")
PAGE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Chrome sends these on every page it opens; helpx.adobe.com answers 403 to a request without them.
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
BROWSER_TIMEOUT_MS = 45_000
MIN_OFFICIAL_CHARS = 300  # a page with less text than this cannot support a carousel
MAX_PAGE_BYTES = 3_000_000
PRESS_WORDS = ("press", "news", "announce", "release")


HEADING_LEVELS = {f"h{n}": n for n in range(1, 7)}
BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "br", "section", "article", "blockquote", "figure", "figcaption",
              "tr", "td", *HEADING_LEVELS}

# Official demo videos. A video page's poster frame is a real frame of the product (an official screenshot).
VIDEO_HOSTS = ("video.tv.adobe.com",)
VIDEO_URL = re.compile(r"(?:https?:)?//video\.tv\.adobe\.com/v/[^\s\"'<>)\]]+", re.I)
MIN_PARAGRAPH_CHARS = 25  # a paragraph shorter than this is not a feature description
TAG_MAX_CHARS = 320


VIDEO_ID = re.compile(r"/v/([\w-]+)", re.I)
MAX_VIDEO_PAGES = 20  # video pages fetched per story


def clean_video_url(url: str) -> str:
    """One address per video: https://video.tv.adobe.com/v/<id>, with any query string or trailing
    punctuation dropped, so the same video linked twice counts once."""
    url = url.strip().rstrip(".,;:")
    url = "https:" + url if url.startswith("//") else url
    found = VIDEO_ID.search(urlsplit(url).path)
    host = urlsplit(url).hostname
    return f"https://{host}/v/{found.group(1)}" if found and host else url


def is_video_url(url: str | None) -> bool:
    if not url or "/v/" not in url:
        return False
    try:
        return urlsplit(clean_video_url(url)).hostname in VIDEO_HOSTS
    except ValueError:
        return False


def feature_name(paragraph: str) -> str:
    """The feature a paragraph introduces: its leading run of capitalised words, so 'Relight creatively adds
    new light sources...' gives 'Relight' and 'With Generative Restyle, you can...' gives 'Generative
    Restyle'. Empty when the paragraph does not open with a name."""
    words = re.sub(r"^(?:With|The|Introducing|Meet|New)\s+", "", paragraph.strip(), flags=re.I).split()
    name: list[str] = []
    for word in words:
        bare = word.rstrip(",.;:!?")
        if not bare or not (bare[0].isupper() or bare[0].isdigit()) or len(name) >= 4:
            break
        name.append(bare)
        if bare != word:  # punctuation ends the name ('Generative Restyle, you can...')
            break
    return " ".join(name)


class _PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "form", "button"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []
        self.hero_image: str | None = None
        self._skip_depth = 0
        # Visible text split at headings: level 0 is the text before the first heading.
        self.sections: list[dict] = [{"level": 0, "heading": [], "parts": [], "videos": []}]
        self._in_heading = False
        # Demo video links, each tagged with the paragraph just before it on the page.
        self._block: list[str] = []
        self._last_block = ""
        self._seen_videos: set[str] = set()

    def _flush_block(self) -> None:
        text = " ".join(" ".join(self._block).split())
        if len(text) >= MIN_PARAGRAPH_CHARS:
            self._last_block = text
        self._block = []

    def _video(self, url: str) -> None:
        url = clean_video_url(url)
        if url in self._seen_videos:
            return
        self._seen_videos.add(url)
        before = " ".join(" ".join(self._block).split())
        tag = before if len(before) >= MIN_PARAGRAPH_CHARS else self._last_block
        self._block = []  # text after the link belongs to the next feature
        self.sections[-1]["videos"].append(
            {"url": url, "tag": tag[-TAG_MAX_CHARS:].strip(), "feature": feature_name(tag)})

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in BLOCK_TAGS and not self._skip_depth:
            self._flush_block()
        if tag in HEADING_LEVELS and not self._skip_depth:
            self.sections.append({"level": HEADING_LEVELS[tag], "heading": [], "parts": [], "videos": []})
            self._in_heading = True
        if not self._skip_depth:
            for value in values.values():
                if is_video_url(value):
                    self._video(value)
        if tag in self.SKIP:
            self._skip_depth += 1
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag == "meta" and values.get("property") == "og:image" and values.get("content"):
            self.hero_image = self.hero_image or values["content"]

    def handle_endtag(self, tag):
        if tag in HEADING_LEVELS:
            self._in_heading = False
        if tag in BLOCK_TAGS and not self._skip_depth:
            self._flush_block()
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)
            self.sections[-1]["parts"].append(data)
            if self._in_heading:
                self.sections[-1]["heading"].append(data)
            # A video address written out as text: the words before it are the feature paragraph.
            position = 0
            for found in VIDEO_URL.finditer(data):
                self._block.append(data[position:found.start()])
                self._video(found.group(0))
                position = found.end()
            self._block.append(data[position:])


def parse_page(markup: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(markup)
    parser.close()
    return parser


def page_text(markup: str) -> str:
    """The visible words of a page, with spacing tidied."""
    return " ".join(" ".join(parse_page(markup).parts).split())


def _tidy(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


def page_sections(markup: str) -> list[dict]:
    """The page split at its headings: [{"level", "heading", "text"}]. Level 0 is the text before the
    first heading. A section's text starts with its own heading and stops at the next heading."""
    return [{"level": s["level"], "heading": _tidy(s["heading"]), "text": _tidy(s["parts"])}
            for s in parse_page(markup).sections if _tidy(s["parts"])]


def _names(text: str, terms: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(t)}\b", text, re.I) for t in terms)


def product_text(markup: str, terms: list[str], others: list[str] = ()) -> tuple[str, str]:
    """(text, note): the part of a page about the story's product.

    A round-up page (Photoshop, Lightroom, Premiere...) is split at its headings and only the sections
    whose heading names the product are kept, with the sub-sections under them. A section that holds
    several products (an overall title over a heading per product) is not kept itself: only its own
    product sections are. `others` are the other product names, used to spot such a section.
    With no terms, no heading naming the product, or too little text left, the whole page is used and
    the note says so.
    """
    whole = page_text(markup)
    terms = [t for t in terms if t]
    if not terms:
        return whole, ""
    sections = page_sections(markup)

    def span_end(i: int) -> int:
        level = sections[i]["level"]
        return next((k for k in range(i + 1, len(sections)) if 0 < sections[k]["level"] <= level), len(sections))

    matched = [i for i, s in enumerate(sections) if s["level"] and _names(s["heading"], terms)]
    if not matched:
        return whole, f"no heading names {', '.join(terms)}: the whole page is used as the fact source"
    keep: set[int] = set()
    for i in matched:
        end = span_end(i)
        inner = range(i + 1, end)
        multi = any(sections[k]["level"] and _names(sections[k]["heading"], list(others))
                    and not _names(sections[k]["heading"], terms) for k in inner) if others else False
        if multi:
            continue  # a round-up container: its product sections are matched on their own
        keep.update(range(i, end))
    text = " ".join(sections[k]["text"] for k in sorted(keep))
    if len(text) < MIN_OFFICIAL_CHARS:
        return whole, (f"the sections naming {', '.join(terms)} are too short ({len(text)} characters): "
                       "the whole page is used as the fact source")
    if len(text) >= len(whole):
        return whole, ""
    return text, (f"only the sections about {', '.join(terms)} are used as facts "
                  f"({len(text)} of {len(whole)} characters of the page)")


def host_allowed(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def official_links(markup: str, base_url: str, domains: list[str]) -> list[str]:
    """Links on a news page that lead to the brand's own site, press-looking links first."""
    found: list[str] = []
    for href in parse_page(markup).links:
        absolute = urljoin(base_url, href).split("#")[0]
        if urlsplit(absolute).scheme in ("http", "https") and host_allowed(absolute, domains):
            if absolute not in found:
                found.append(absolute)
    return sorted(found, key=lambda u: not any(word in u.lower() for word in PRESS_WORDS))


def is_home_page(url: str) -> bool:
    """True for a site's front page (no path), which is never an announcement."""
    return urlsplit(url).path.strip("/") == ""


def product_match_score(markup: str, terms: list[str], url: str = "") -> int:
    """How much a page is about the product named by `terms`: 0 means it is not.

    A term in the page title or a heading counts 3 and one in the body counts 1. With no term in the title or
    headings, the body must name at least two different terms (all of them when there are fewer)."""
    terms = [t for t in terms if t]
    if not terms:
        return 0
    meta = _MetaParser()
    meta.feed(markup)
    meta.close()
    path_words = re.sub(r"[^A-Za-z0-9.]+", " ", urlsplit(url).path)  # "luminar-neo-relight" names the product too
    head = " ".join([meta.meta.get("og:title", ""), meta.title, path_words]
                    + [s["heading"] for s in page_sections(markup)])
    in_head = [t for t in terms if _names(head, [t])]
    body = page_text(markup)
    in_body = [t for t in terms if _names(body, [t])]
    if in_head:
        return 3 * len(in_head) + len(in_body)
    return len(in_body) if len(in_body) >= min(2, len(terms)) else 0


def hero_image_url(markup: str, base_url: str) -> str | None:
    image = parse_page(markup).hero_image
    return urljoin(base_url, image) if image else None


def video_links(markup: str, terms: list[str] = ()) -> list[dict]:
    """The official demo videos linked or embedded in a page, in page order.

    Each is {"url", "tag", "feature", "heading", "in_product"}: the video address, the paragraph written just
    before it, the feature name that paragraph opens with, the nearest heading above it, and whether it sits in
    a section about the story's product (always true with no terms). Videos in the product's section come first.
    """
    found: list[dict] = []
    active: int | None = None  # level of the heading naming the product whose section we are in
    for section in parse_page(markup).sections:
        level, heading = section["level"], _tidy(section["heading"])
        if level:
            if active is not None and level <= active:
                active = None
            if active is None and terms and heading and _names(heading, list(terms)):
                active = level
        for video in section["videos"]:
            found.append({**video, "heading": heading, "in_product": not terms or active is not None})
    return sorted(found, key=lambda v: not v["in_product"])


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.poster: str | None = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key and values.get("content"):
                self.meta.setdefault(key.lower(), values["content"])
        elif tag == "video" and values.get("poster"):
            self.poster = self.poster or values["poster"]
        elif tag == "link" and (values.get("rel") or "").lower() == "image_src" and values.get("href"):
            self.meta.setdefault("image_src", values["href"])
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def video_meta(markup: str, page_url: str) -> dict:
    """{"poster", "title", "description"} of one official video page. The poster is the page's og:image
    (else its twitter:image or the video element's poster): a real frame from the demo. Empty strings when absent."""
    parser = _MetaParser()
    parser.feed(markup)
    parser.close()
    poster = (parser.meta.get("og:image") or parser.meta.get("og:image:secure_url")
              or parser.meta.get("twitter:image") or parser.poster or parser.meta.get("image_src") or "")
    title = parser.meta.get("og:title") or " ".join(parser.title.split())
    return {
        "poster": urljoin(page_url, poster) if poster else "",
        "title": " ".join(title.split()),
        "description": " ".join(parser.meta.get("og:description", parser.meta.get("description", "")).split()),
    }


def _has_product_heading(markup: str, terms) -> bool:
    """True when some heading on the page names one of the product terms."""
    return any(section["level"] and _names(_tidy(section["heading"]), list(terms))
               for section in parse_page(markup).sections)


def discover_videos(pages: list[tuple[str, str]], terms: list[str] = (), fetch=None,
                    limit: int = MAX_VIDEO_PAGES) -> tuple[list[dict], list[str]]:
    """Official demo videos found in the given pages (page URL, markup), each with its video page read.

    Returns (videos, notes). A video is {"url", "poster", "title", "description", "tag", "feature", "heading",
    "found_on"}; one whose page cannot be read, or that has no poster, is left out and named in the notes.
    `fetch` reads a page (default fetch_html), so tests need no network.
    """
    fetch = fetch or fetch_html
    videos: list[dict] = []
    notes: list[str] = []
    seen: set[str] = set()
    # On a round-up page with a section for the product, only that product's videos are used: another product's
    # demo would be a wrong picture for this story. A page with no product section keeps every video (as its text does).
    links = []
    for page_url, markup in pages:
        product_section = bool(terms) and _has_product_heading(markup, terms)
        links += [(page_url, link) for link in video_links(markup, terms) if link["in_product"] or not product_section]
    links.sort(key=lambda pair: not pair[1]["in_product"])
    for page_url, link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        if len(seen) > limit:
            notes.append(f"video pages beyond the first {limit} were not read")
            break
        try:
            meta = video_meta(fetch(link["url"]), link["url"])
        except (requests.RequestException, ValueError) as exc:
            notes.append(f"video page {link['url']} could not be read ({type(exc).__name__})")
            continue
        if not meta["poster"]:
            notes.append(f"video page {link['url']} has no poster image")
            continue
        videos.append({**meta, "url": link["url"], "tag": link["tag"], "feature": link["feature"],
                       "heading": link["heading"], "found_on": page_url})
    return videos, notes


class PageUnreadable(requests.RequestException):
    """A page that neither a plain request nor the Chromium browser could read. The message says what happened."""


def describe_error(exc: BaseException) -> str:
    """A short reason for a notes line: the exception name, or for an unreadable page what each attempt got."""
    return str(exc) if isinstance(exc, PageUnreadable) and str(exc) else type(exc).__name__


def _plain_error(exc: requests.RequestException) -> str:
    response = getattr(exc, "response", None)
    return f"HTTP {response.status_code}" if response is not None else type(exc).__name__


def fetch_html_browser(url: str) -> str:
    """Reads a public page with the Playwright Chromium the project already uses for rendering. Used when a plain
    request is refused. Raises PageUnreadable (with the reason) when the browser is missing or the page does not load."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PageUnreadable("Playwright is not installed") from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_context(user_agent=USER_AGENT, locale="en-US").new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                if response is not None and response.status >= 400:
                    raise PageUnreadable(f"HTTP {response.status} in the browser")
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:  # a page that never goes quiet is still read as it stands
                    pass
                markup = page.content()
            finally:
                browser.close()
    except PageUnreadable:
        raise
    except Exception as exc:
        raise PageUnreadable(f"the browser could not load it ({type(exc).__name__})") from exc
    if len(markup) > MAX_PAGE_BYTES:
        raise ValueError(f"page is larger than {MAX_PAGE_BYTES} bytes: {url}")
    return markup


PAGE_CACHE = {"dir": None, "hours": 6.0, "memo": {}, "failed": {}}


def enable_page_cache(directory, hours: float = 6.0) -> None:
    """Turns on the page cache for this run (carousel.run_story does). A page read once is not fetched again: within the
    run from memory, and for `hours` from data/page-cache on disk. A page that could not be read (a helpx 403 that also
    fails in Chromium, which costs a browser start and up to 45 s) is not tried again within the same hours."""
    PAGE_CACHE.update({"dir": Path(directory), "hours": hours, "memo": {}, "failed": {}})


def disable_page_cache() -> None:
    PAGE_CACHE.update({"dir": None, "memo": {}, "failed": {}})


def _cache_path(url: str) -> Path:
    import hashlib
    return PAGE_CACHE["dir"] / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json")


def _cached_page(url: str):
    """("ok", markup), ("failed", reason) or None, from memory, then from disk."""
    if url in PAGE_CACHE["memo"]:
        return "ok", PAGE_CACHE["memo"][url]
    if url in PAGE_CACHE["failed"]:
        return "failed", PAGE_CACHE["failed"][url]
    import json
    import time
    try:
        path = _cache_path(url)
        if time.time() - path.stat().st_mtime > PAGE_CACHE["hours"] * 3600:
            return None
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if entry.get("url") != url:
        return None
    if "markup" in entry:
        PAGE_CACHE["memo"][url] = entry["markup"]
        return "ok", entry["markup"]
    if "error" in entry:
        PAGE_CACHE["failed"][url] = entry["error"]
        return "failed", entry["error"]
    return None


def _store_page(url: str, markup: str | None = None, error: str | None = None) -> None:
    import json
    if markup is not None:
        PAGE_CACHE["memo"][url] = markup
    else:
        PAGE_CACHE["failed"][url] = error
    try:
        path = _cache_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"url": url, "markup": markup} if markup is not None else {"url": url, "error": error}
        path.write_text(json.dumps(entry), encoding="utf-8")
    except OSError:
        pass  # the cache is only a speedup


def fetch_html(url: str) -> str:
    """One official page: a plain request with a normal browser identity first; when that is refused (helpx answers
    403 to scripts), the same page is loaded in Chromium. If both fail, PageUnreadable says what each one got.
    With the page cache on (enable_page_cache), a page is read at most once per run and once per cache window."""
    if PAGE_CACHE["dir"] is None:
        return _fetch_html_uncached(url)
    hit = _cached_page(url)
    if hit is not None:
        kind, value = hit
        if kind == "ok":
            return value
        raise PageUnreadable(value)
    try:
        markup = _fetch_html_uncached(url)
    except PageUnreadable as exc:
        _store_page(url, error=str(exc))
        raise
    _store_page(url, markup=markup)
    return markup


def _fetch_html_uncached(url: str) -> str:
    try:
        return fetch_html_plain(url)
    except requests.RequestException as exc:
        plain = _plain_error(exc)
    try:
        return fetch_html_browser(url)
    except PageUnreadable as exc:
        raise PageUnreadable(f"{plain} for a plain request, and the Chromium browser failed too: {exc}") from exc


def fetch_html_plain(url: str) -> str:
    response = requests.get(url, headers=PAGE_HEADERS, timeout=25, stream=True)
    response.raise_for_status()
    data = bytearray()
    for chunk in response.iter_content(65536):
        data.extend(chunk)
        if len(data) > MAX_PAGE_BYTES:
            raise ValueError(f"page is larger than {MAX_PAGE_BYTES} bytes: {url}")
    response.encoding = response.encoding or "utf-8"
    return bytes(data).decode(response.encoding, errors="replace")


def download_image(url: str, destination) -> None:
    """Saves one image. Only used when use_official_press_images is true."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    if not response.headers.get("content-type", "").startswith("image/"):
        raise ValueError(f"not an image: {url}")
    destination.write_bytes(response.content)
