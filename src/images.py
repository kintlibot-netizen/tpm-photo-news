"""Product image candidates from the brand's own official pages.

Rules (Kint's standing rule: real, accurate, nothing AI-made):
- Only images found on the official pages for the story (announcement, product page, newsroom or press kit)
  and hosted on the brand's official domains are candidates.
- A blog media_ image is requested at width 2000, then 1200, before the size rule is applied (the page itself asks
  for width 750, which is only a thumbnail of the same file). An image with no alt text is also tagged with the
  features named in the paragraph just before it (context_features); the image check still has to see the feature.
- Skipped: under 1000 px on the long side, anything whose alt text or file name suggests people as the
  main subject, logos and icons, any image with AI-generation metadata (IPTC trainedAlgorithmicMedia), and
  any image whose alt text or file name says it was made by AI or Firefly, unless it is an app screenshot.
- Nothing is generated, edited or background-removed. Files are saved as the brand published them, with one
  exception: the flat light grey border around an official video poster is cropped off (border_trim.py, a plain
  crop; the published file is kept in candidates/originals/ and sources.md says "uniform border trimmed, no content
  changed").
- Official help pages (helpx.adobe.com, listed in config/carousel.yaml and linked from the post or the beta page) are
  read for images and demo videos the same way as the post (img alt, og:image, video posters).
- With use_official_press_images false, candidates are only listed in candidates.md. Kint copies the
  one he wants to images/01.jpg and so on. Only with the flag true are the best matches placed on slides,
  and then sources.md records each one.

The people and AI checks look at alt text and file names, and at embedded metadata. They can miss things,
so a human looks at every candidate before it goes on a slide.
"""
from __future__ import annotations

import re
import shutil
import struct
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

import border_trim
from official import USER_AGENT, describe_error, fetch_html, host_allowed

MIN_LONG_SIDE = 1000
# The blog serves the same media_ file at any width. The page asks for a small one (width=750), so the real size is
# requested first, the largest that exists, before the size rule is applied.
BLOG_WIDTHS = (2000, 1200)
MAX_BYTES = 15_000_000
PAGE_LIMIT = 6
CANDIDATE_LIMIT = 40
AI_METADATA = (b"trainedAlgorithmicMedia", b"compositeWithTrainedAlgorithmicMedia")
AI_WORDS = re.compile(
    r"\b(firefly|ai[- ]generated|generated (?:by|with) (?:ai|adobe firefly)|midjourney|dall[- ]?e|"
    r"stable diffusion|text[- ]to[- ]image|ai image)\b",
    re.I,
)
SCREENSHOT_WORDS = re.compile(r"\b(screenshot|screen[- ]?grab|user interface|interface)\b", re.I)
PERSON_WORDS = re.compile(
    r"\b(person|people|man|men|woman|women|model|models|photographer|portrait|girl|boy|family|couple|"
    r"child|children|influencer|smiling|selfie)\b",
    re.I,
)
LOGO_WORDS = re.compile(r"\b(logo|favicon|icon|sprite|badge|wordmark)\b", re.I)
PRESS_PATH = re.compile(r"press|newsroom|media|gallery|kit|product|news|announce", re.I)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass
class Candidate:
    file: str
    page: str  # the page the image was found on (for a video poster: the video page)
    image_url: str
    width: int
    height: int
    alt: str
    feature: str = ""  # the slide feature this image shows, matched from its title and caption ("" = general)
    title: str = ""  # a video poster's video title
    kind: str = "image"  # "image", or "video poster" (the poster frame of an official demo video)
    match_text: str = ""  # the title and caption words the feature was matched against
    trimmed: str = ""  # set when a uniform grey border was cropped off at save time (border_trim.describe)
    context: str = ""  # the paragraph written just before the image on its page (a blog image has no alt text)
    context_features: list[str] = field(default_factory=list)  # slide features that paragraph names in full


# ---- tagging video posters with the feature they show ----

GENERIC_WORDS = {"a", "an", "the", "and", "or", "of", "in", "on", "for", "to", "with", "now", "new", "tool", "tools",
                 "feature", "features", "update", "updates", "photoshop", "adobe", "lightroom", "camera", "raw"}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


feature_words = _words  # public name: image_pick compares feature names word by word


def feature_score(feature: str, text: str) -> int:
    """How well some title or caption text names a feature: 0 for no match. The whole feature name as a phrase
    ("generative restyle") scores highest; otherwise every distinctive word of it must appear."""
    wanted, found = _words(feature), _words(text)
    distinctive = [w for w in wanted if w not in GENERIC_WORDS]
    if not distinctive:
        return 0
    if f" {' '.join(wanted)} " in f" {' '.join(found)} ":
        return 100 + len(wanted)
    if all(w in found for w in distinctive):
        return 50 + len(distinctive)
    return 0


def video_text(video: dict) -> str:
    """The words a video is matched on: its title, the feature name and heading near its link, and the
    paragraph written before the link."""
    return " ".join(part for part in (video.get("title"), video.get("feature"), video.get("heading"),
                                      video.get("tag")) if part)


def tag_feature(video: dict, features: list[str]) -> str:
    """The slide feature (one of `features`) a video shows, or "". The video's own title counts most, then the
    feature name and heading next to its link, then the paragraph before it. The best score wins and the first
    listed feature wins a tie."""
    best, best_score = "", 0
    for feature in features:
        score = max(3 * feature_score(feature, video.get("title", "")),
                    2 * feature_score(feature, video.get("feature", "")),
                    2 * feature_score(feature, video.get("heading", "")),
                    feature_score(feature, video.get("tag", "")))
        if score > best_score:
            best, best_score = feature, score
    return best


def tag_image(image: dict, features: list[str]) -> str:
    """The slide feature a page image shows, read from its alt text and file name only. "" when no feature matches.
    The whole feature name must appear, so a loose word never tags a picture."""
    name = urlsplit(image.get("src", "")).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    text = f"{image.get('alt', '')} {name.replace('-', ' ').replace('_', ' ')}"
    best, best_score = "", 0
    for feature in features:
        score = feature_score(feature, text)
        if score >= 100 and score > best_score:
            best, best_score = feature, score
    return best


def context_features(context: str, features: list[str]) -> list[str]:
    """The slide features whose whole name appears in the paragraph written before an image. An image with no alt text
    is only a possible picture of these: the image check still has to see the feature in it."""
    return [f for f in features if feature_score(f, context) >= 100]


SCENE7_WID = re.compile(r"([?&]wid=)(\d+)", re.I)


def scene7_larger_urls(src: str) -> list[str]:
    """An official help page image (helpx-prod.scene7.com) at a larger wid first, then as the page gave it. The address
    is only edited in its wid setting; every other part (such as $pjpeg$) stays exactly as published."""
    found = SCENE7_WID.search(src)
    if not found:
        return [src]
    current = int(found.group(2))
    larger = [SCENE7_WID.sub(lambda m, w=width: f"{m.group(1)}{w}", src, count=1) for width in BLOG_WIDTHS if width > current]
    return larger + [src]


def og_image_markup(image_url: str, title: str = "") -> str:
    """A tiny page with only the og:image (and title) of an official page that could not be read."""
    from html import escape
    return (f'<html><head><meta property="og:title" content="{escape(title, quote=True)}">'
            f'<meta property="og:image" content="{escape(image_url, quote=True)}"></head><body></body></html>')


def larger_urls(src: str) -> list[str]:
    """The addresses to try for an official blog image, largest first, ending with the address the page gave. Only a
    blog media_ file with a width setting has larger versions: the same file at width 2000, then 1200."""
    parts = urlsplit(src)
    if (parts.hostname or "").endswith("scene7.com") and "/is/image/" in parts.path:
        return scene7_larger_urls(src)
    if "/media_" not in parts.path:
        return [src]
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(key == "width" for key, _ in query):
        return [src]
    try:
        current = int(next(value for key, value in query if key == "width"))
    except ValueError:
        return [src]
    urls = []
    for width in BLOG_WIDTHS:
        if width > current:
            urls.append(urlunsplit(parts._replace(query=urlencode(
                [(key, str(width) if key == "width" else value) for key, value in query]))))
    return urls + [src]


# ---- official help pages (helpx.adobe.com) as extra image sources ----

MAX_FEATURE_PAGES = 4  # help pages followed from links, per story
FEATURE_PAGE_LINKS = 2  # help pages followed per feature
MAX_WHATS_NEW_PAGES = 1  # extra what's new help pages followed from links
WHATS_NEW = re.compile(r"whats-new|what-s-new", re.I)


class _HelpParser(HTMLParser):
    """The heading of a page (first h1, else og:title, else title) and its links with their text."""

    def __init__(self) -> None:
        super().__init__()
        self.h1 = ""
        self.og_title = ""
        self.title = ""
        self.links: list[tuple[str, str]] = []
        self._open: str | None = None
        self._href: str | None = None
        self._text: list[str] = []
        self._seen_h1 = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("property") == "og:title" and values.get("content"):
            self.og_title = self.og_title or values["content"]
        elif tag in ("h1", "title"):
            if tag == "h1" and self._seen_h1:
                return
            self._open = tag
        elif tag == "a" and values.get("href"):
            self._href, self._text = values["href"], []

    def handle_endtag(self, tag):
        if tag == self._open:
            if tag == "h1":
                self._seen_h1 = True
            self._open = None
        elif tag == "a" and self._href is not None:
            self.links.append((" ".join("".join(self._text).split()), self._href))
            self._href = None

    def handle_data(self, data):
        if self._open == "h1" and not self._seen_h1:
            self.h1 += data
        elif self._open == "title":
            self.title += data
        if self._href is not None:
            self._text.append(data)


def _help_parse(markup: str) -> _HelpParser:
    parser = _HelpParser()
    parser.feed(markup)
    parser.close()
    return parser


def page_title(markup: str) -> str:
    """What a page says it is about: its first h1, else og:title, else title."""
    parser = _help_parse(markup)
    return " ".join((parser.h1 or parser.og_title or parser.title).split())


def page_feature(markup: str, features: list[str]) -> str:
    """The slide feature a help page is about, from its heading: the WHOLE feature name must be in the heading
    ("Change camera angles in Photoshop" is about "Camera Angles"). "" for a what's new page or any page whose heading
    names no feature."""
    title = page_title(markup)
    best, best_score = "", 0
    for feature in features:
        score = feature_score(feature, title)
        if score >= 100 and score > best_score:
            best, best_score = feature, score
    return best


def feature_links(markup: str, page_url: str, features: list[str], domains: list[str]) -> list[tuple[str, str]]:
    """(feature, url) for links on a page, on an official domain, whose link text or address names a feature in
    full ("Remove tool", .../remove-tool.html). This is how the Remove Tool help page is found from the beta page or
    the blog post: it is read from a real link, never guessed. A what's new page is never followed."""
    found: list[tuple[str, str]] = []
    for text, href in _help_parse(markup).links:
        url = urljoin(page_url, href).split("#")[0]
        path = urlsplit(url).path
        if (urlsplit(url).scheme not in ("http", "https") or url == page_url or not host_allowed(url, domains)
                or path.lower().endswith(IMAGE_EXTENSIONS) or WHATS_NEW.search(path)):
            continue
        slug = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
        for feature in features:
            if max(feature_score(feature, text), feature_score(feature, slug)) >= 100 and (feature, url) not in found:
                if sum(1 for f, _ in found if f == feature) < FEATURE_PAGE_LINKS:
                    found.append((feature, url))
    return found


def whats_new_links(markup: str, page_url: str, domains: list[str], terms: list[str]) -> list[str]:
    """Links to the official what's new help page of the story's product ("photoshop" in the address), for example
    the Photoshop desktop what's new page that the beta page or the post links to. Its images are tagged only by
    their own alt text or file name (it is about many features)."""
    found: list[str] = []
    for _, href in _help_parse(markup).links:
        url = urljoin(page_url, href).split("#")[0]
        path = urlsplit(url).path.lower()
        if (urlsplit(url).scheme in ("http", "https") and url != page_url and host_allowed(url, domains)
                and WHATS_NEW.search(path) and any(t.lower().replace(" ", "-") in path for t in terms)
                and not path.endswith(IMAGE_EXTENSIONS) and url not in found):
            found.append(url)
    return found


def discover_image_pages(seed_pages: list[tuple[str, str]], extra_urls: list[str], features: list[str],
                         domains: list[str], fetch=None,
                         terms: list[str] | None = None,
                         fallback_images: dict[str, dict] | None = None
                         ) -> tuple[list[tuple[str, str]], dict[str, str], list[str]]:
    """More official pages to look for images and demo videos on: the configured help pages (extra_urls), then the
    help pages for a feature that the seed pages (the blog post, the beta page) link to, and the product's what's new
    help page when one of them links to it.

    Returns (new pages as (url, markup), page tags {url: feature} for the help pages that are about one feature,
    notes for sources.md). A page that cannot be read (helpx often refuses bots) is named in the notes and skipped.
    `fetch` reads a page (default official.fetch_html), so tests need no network.
    """
    fetch = fetch or fetch_html
    have = {url for url, _ in seed_pages}
    pages: list[tuple[str, str]] = []
    notes: list[str] = []

    def read(url: str, why: str) -> None:
        if url in have:
            return
        have.add(url)
        if not host_allowed(url, domains):
            notes.append(f"help page {url} is not on an official domain: not used")
            return
        try:
            pages.append((url, fetch(url)))
            notes.append(f"help page read for images ({why}): {url}")
        except (requests.RequestException, ValueError) as exc:
            known = (fallback_images or {}).get(url)
            if known and host_allowed(known["image_url"], domains):
                # helpx refuses scripts (403) but its image host (scene7) answers a normal request, so the page's
                # known og:image is still offered as a candidate for this page.
                pages.append((url, og_image_markup(known["image_url"], known.get("title", ""))))
                notes.append(f"help page {url} could not be read ({describe_error(exc)}): its known official "
                             f"og:image {known['image_url']} is tried instead")
            else:
                notes.append(f"help page {url} could not be read ({describe_error(exc)}): skipped")

    for url in extra_urls:
        read(url, "configured")
    followed = 0
    for page_url, markup in list(seed_pages) + list(pages):
        for feature, link in feature_links(markup, page_url, features, domains):
            if followed >= MAX_FEATURE_PAGES:
                break
            if link not in have:
                followed += 1
                read(link, f"linked from {page_url} for {feature}")
    if terms:
        whats_new = 0
        for page_url, markup in list(seed_pages) + list(pages):
            for link in whats_new_links(markup, page_url, domains, terms):
                if whats_new < MAX_WHATS_NEW_PAGES and link not in have:
                    whats_new += 1
                    read(link, f"the what's new page linked from {page_url}")
    tags = {}
    for url, markup in pages:
        if not WHATS_NEW.search(urlsplit(url).path):
            feature = page_feature(markup, features)
            if feature:
                tags[url] = feature
                notes.append(f"help page {url} is about {feature!r}: its images are tagged with it")
    return pages, tags, notes


TEXT_BLOCKS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "blockquote"}
CONTEXT_MIN_CHARS = 25
CONTEXT_MAX_CHARS = 400


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict] = []
        self.links: list[str] = []
        self._skip = 0
        self._buffer: list[str] = []
        self._last = ""  # the last paragraph of real text before this point

    def _flush(self) -> None:
        text = " ".join(" ".join(self._buffer).split())
        if len(text) >= CONTEXT_MIN_CHARS:
            self._last = text[-CONTEXT_MAX_CHARS:]
        self._buffer = []

    def _context(self) -> str:
        text = " ".join(" ".join(self._buffer).split())
        return text[-CONTEXT_MAX_CHARS:] if len(text) >= CONTEXT_MIN_CHARS else self._last

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag in TEXT_BLOCKS and not self._skip:
            self._flush()
        if tag == "meta" and values.get("property") in ("og:image", "og:image:secure_url") and values.get("content"):
            self.images.append({"src": values["content"], "alt": "", "kind": "og",
                                "w": None, "h": None, "context": ""})
        elif tag == "img":
            src = values.get("src") or values.get("data-src") or values.get("data-lazy-src")
            if src:
                self.images.append({"src": src, "alt": values.get("alt") or "", "kind": "img",
                                    "w": values.get("width"), "h": values.get("height"),
                                    "context": self._context()})
        elif tag == "a" and values.get("href"):
            self.links.append(values["href"])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if tag in TEXT_BLOCKS and not self._skip:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buffer.append(data)


def parse_page(markup: str, page_url: str) -> tuple[list[dict], list[str]]:
    """Image references and links on a page, made absolute."""
    parser = _Parser()
    parser.feed(markup)
    parser.close()
    images = []
    for item in parser.images:
        item = dict(item, src=urljoin(page_url, item["src"]))
        if urlsplit(item["src"]).scheme in ("http", "https"):
            images.append(item)
    links = [urljoin(page_url, href).split("#")[0] for href in parser.links]
    return images, links


def press_pages(links: list[str], domains: list[str]) -> list[str]:
    """Links from an official page to other official pages (press kits, product galleries)."""
    found: list[str] = []
    for link in links:
        path = urlsplit(link).path.lower()
        if (urlsplit(link).scheme in ("http", "https") and host_allowed(link, domains)
                and PRESS_PATH.search(path) and not path.endswith(IMAGE_EXTENSIONS) and link not in found):
            found.append(link)
    return found[:PAGE_LIMIT]


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """Pixel width and height read from the file header. None when the format is not recognised."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 4 <= len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker == 0xFF:
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if i + 9 > len(data):
                    return None
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return width, height
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8 ":
            width, height = struct.unpack("<HH", data[26:30])
            return width & 0x3FFF, height & 0x3FFF
        if chunk == b"VP8L":
            bits = struct.unpack("<I", data[21:25])[0]
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X":
            return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    return None


def extension_for(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def reject_reason(image: dict, data: bytes | None, page_url: str, domains: list[str]) -> str | None:
    """Why this image cannot be a candidate. None when it can."""
    if not host_allowed(image["src"], domains) and urlsplit(image["src"]).hostname != urlsplit(page_url).hostname:
        return "image is not hosted on an official domain"
    text = f"{image['alt']} {image['src']}"
    if AI_WORDS.search(text) and not SCREENSHOT_WORDS.search(text):
        return "alt text or file name says it is AI-generated"
    if LOGO_WORDS.search(text):
        return "logo or icon"
    if PERSON_WORDS.search(text):
        return "may show people as the main subject"
    if data is None:
        return "could not be downloaded"
    if any(marker in data for marker in AI_METADATA):
        return "embedded metadata says it is AI-generated"
    if extension_for(data) is None:
        return "not a JPEG, PNG or WebP file"
    size = image_dimensions(data)
    if size is None:
        return "could not read the pixel size"
    if max(size) < MIN_LONG_SIDE:
        return f"under {MIN_LONG_SIDE}px on the long side ({size[0]}x{size[1]})"
    return None


def fetch_bytes(url: str) -> bytes:
    """Downloads one image, up to MAX_BYTES. Only used for official pages' images."""
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25, stream=True)
    response.raise_for_status()
    data = bytearray()
    for chunk in response.iter_content(65536):
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise ValueError("image is too large")
    return bytes(data)


def gather(pages: list[tuple[str, str]], domains: list[str], out_dir: Path,
           fetch=fetch_bytes, features: list[str] | None = None,
           page_tags: dict[str, str] | None = None) -> tuple[list[Candidate], list[dict]]:
    """Candidates from the given official pages (page URL, page markup). Saves the accepted files.
    With `features`, an image whose alt text or file name names a feature is tagged with it. `page_tags` maps a help
    page about one feature to that feature: an image on it with no feature of its own gets the page's feature."""
    seen: set[str] = set()
    accepted: list[Candidate] = []
    rejected: list[dict] = []
    all_images: list[tuple[dict, str]] = []
    for page_url, markup in pages:
        images, _ = parse_page(markup, page_url)
        for image in images:
            if image["src"] not in seen:
                seen.add(image["src"])
                all_images.append((image, page_url))
    all_images.sort(key=lambda pair: pair[0]["kind"] != "og")  # the page's main image first
    folder = out_dir / "candidates"
    for image, page_url in all_images[:CANDIDATE_LIMIT]:
        if image["w"] and image["h"] and str(image["w"]).isdigit() and str(image["h"]).isdigit():
            if max(int(image["w"]), int(image["h"])) < MIN_LONG_SIDE:
                rejected.append({"image_url": image["src"], "page": page_url,
                                 "reason": "declared size under 1000px"})
                continue
        # 1. Rules that need only the page's own text: host, AI wording, logos, people.
        early = reject_reason(image, None, page_url, domains)
        if early and early != "could not be downloaded":
            rejected.append({"image_url": image["src"], "page": page_url, "reason": early})
            continue
        # 2. Download the file. A failed download is recorded, not fatal.
        # A blog image is asked for at its largest width first (2000, then 1200, then the width the page gave).
        data, download_error, used_url = None, None, image["src"]
        for url in larger_urls(image["src"]):
            try:
                data, used_url = fetch(url), url
                break
            except (requests.RequestException, ValueError) as exc:
                download_error = type(exc).__name__
        # 3. Rules that need the file: metadata, format and pixel size.
        if data is None:
            rejected.append({"image_url": image["src"], "page": page_url,
                             "reason": f"could not be downloaded ({download_error or 'no data'})"})
            continue
        reason = reject_reason(image, data, page_url, domains)
        if reason:
            rejected.append({"image_url": used_url, "page": page_url, "reason": reason})
            continue
        folder.mkdir(parents=True, exist_ok=True)
        extension = extension_for(data)
        number = len(accepted) + 1
        name = f"c{number:02d}{extension}"
        (folder / name).write_bytes(data)
        width, height = image_dimensions(data)
        context = image.get("context", "")
        accepted.append(Candidate(file=f"candidates/{name}", page=page_url, image_url=used_url,
                                  width=width, height=height, alt=image["alt"],
                                  feature=tag_image(image, features or []) or (page_tags or {}).get(page_url, ""),
                                  context=context, context_features=context_features(context, features or [])))
    return accepted, rejected


def clear_candidates(out_dir: Path) -> None:
    """Removes the candidate files of an earlier run (candidates/cNN.* and candidates/originals/cNN.*), so a stale
    file never sits beside this run's files with the same number. Nothing else in the folder is touched."""
    folder = out_dir / "candidates"
    for where in (folder, folder / "originals"):
        if where.is_dir():
            for old in where.glob("c[0-9][0-9].*"):
                if old.is_file():
                    old.unlink()


def gather_posters(videos: list[dict], domains: list[str], out_dir: Path, features: list[str],
                   fetch=fetch_bytes, start: int = 0, trim=None,
                   page_tags: dict[str, str] | None = None) -> tuple[list[Candidate], list[dict]]:
    """Candidates from the poster frames of official demo videos (see official.discover_videos).

    A poster is a real frame of the product's own app, so the word rules for people, logos and AI wording
    that read alt text do not apply to it (the video title says what the demo is about, not what the picture
    is). It still has to be on an official domain, be a JPEG, PNG or WebP of at least 1000 px with no AI
    metadata, and the image check still looks at it. Each one is tagged with the slide feature it shows.
    Files are numbered on from `start` (the number of candidates already saved).

    trim(data) -> (bytes, info), for example border_trim.trim_border: crops the flat light grey border Adobe puts
    around its posters (a plain crop, no content changed). The file as published is kept in candidates/originals/,
    and the candidate's `trimmed` note says what was cropped. Without `trim` nothing is cropped.
    """
    accepted: list[Candidate] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    folder = out_dir / "candidates"
    for video in videos:
        poster = video.get("poster") or ""
        if not poster or poster in seen:
            continue
        seen.add(poster)
        page = video.get("url", "")
        if not host_allowed(poster, domains):
            rejected.append({"image_url": poster, "page": page, "reason": "image is not hosted on an official domain"})
            continue
        try:
            data = fetch(poster)
        except (requests.RequestException, ValueError) as exc:
            rejected.append({"image_url": poster, "page": page,
                             "reason": f"could not be downloaded ({type(exc).__name__})"})
            continue
        reason = None
        size = image_dimensions(data)
        if any(marker in data for marker in AI_METADATA):
            reason = "embedded metadata says it is AI-generated"
        elif extension_for(data) is None:
            reason = "not a JPEG, PNG or WebP file"
        elif size is None:
            reason = "could not read the pixel size"
        elif max(size) < MIN_LONG_SIDE:
            reason = f"under {MIN_LONG_SIDE}px on the long side ({size[0]}x{size[1]})"
        if reason:
            rejected.append({"image_url": poster, "page": page, "reason": reason})
            continue
        folder.mkdir(parents=True, exist_ok=True)
        number = start + len(accepted) + 1
        trimmed_note = ""
        if trim is not None:
            new_data, info = trim(data)
            new_size = image_dimensions(new_data) if info.get("trimmed") else None
            if new_size and max(new_size) >= MIN_LONG_SIDE:
                (folder / "originals").mkdir(exist_ok=True)
                (folder / "originals" / f"c{number:02d}{extension_for(data)}").write_bytes(data)
                data, size = new_data, new_size
                trimmed_note = border_trim.describe(info)
        name = f"c{number:02d}{extension_for(data)}"
        (folder / name).write_bytes(data)
        for other in IMAGE_EXTENSIONS:  # an untrimmed copy of the same candidate never stays beside the trimmed one
            sibling = folder / f"c{number:02d}{other}"
            if sibling.name != name and sibling.is_file():
                sibling.unlink()
        accepted.append(Candidate(
            file=f"candidates/{name}", page=page, image_url=poster, width=size[0], height=size[1],
            alt=video.get("title", ""),
            feature=tag_feature(video, features) or (page_tags or {}).get(video.get("found_on", ""), ""),
            title=video.get("title", ""),
            kind="video poster", match_text=video_text(video), trimmed=trimmed_note))
    return accepted, rejected


def candidates_markdown(accepted: list[Candidate], rejected: list[dict], pages: list[str]) -> str:
    lines = [
        "# Image candidates", "",
        "Taken only from the brand's official pages below. Nothing was generated, edited or cut out.",
        "Copy the one you want to images/01.jpg, 02.jpg and so on. Check each one before using it.", "",
        "Official pages searched:",
    ]
    lines += [f"- {page}" for page in pages] or ["- none"]
    lines += ["", "## Candidates", ""]
    if accepted:
        lines += ["| File | Size | Kind | Feature | Source page | Image URL |", "|---|---|---|---|---|---|"]
        for c in accepted:
            lines.append(f"| {c.file} | {c.width}x{c.height} | {c.kind} | {c.feature or '-'} | {c.page} | {c.image_url} |")
    else:
        lines.append("No candidates passed the rules.")
    lines += ["", "## Skipped", ""]
    lines += [f"- {r['image_url']} (on {r['page']}): {r['reason']}" for r in rejected] or ["- none"]
    lines.append("")
    return "\n".join(lines)


def auto_place(accepted: list[Candidate], slides: int) -> list[tuple[int, Candidate]]:
    """With use_official_press_images true: the largest candidates, one per slide, in slide order."""
    ranked = sorted(accepted, key=lambda c: max(c.width, c.height), reverse=True)
    return [(number, candidate) for number, candidate in enumerate(ranked[:slides], 1)]


def place(accepted: list[Candidate], out_dir: Path, slides: int) -> list[str]:
    """Copies the auto-placed candidates to images/NN.ext. Returns lines for sources.md."""
    lines = []
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for number, candidate in auto_place(accepted, slides):
        source = out_dir / candidate.file
        target = images_dir / f"{number:02d}{source.suffix}"
        shutil.copyfile(source, target)
        lines.append(f"{target.name}: auto-placed from {candidate.image_url} (on {candidate.page}), "
                     f"{candidate.width}x{candidate.height}")
    return lines
