"""Carousel slides as HTML/CSS, rendered to PNG at 1080 x 1440 with Playwright and Chromium.

One template per reference in reference-slides/:
  cover        01-cover        centred pill, two-line headline, hook, feature names, hero (a collage of the official
                               feature images when there are two or more, else one image), swipe footer
  left_body    02-biggest-upgrade   headline and short body at the left, hero image at the lower right
  stat_specs   04-40fps        centred stat headline, three spec columns with line icons, hero image
  stat_hero    05-4k60p        centred stat headline, sub line, hero image, one short line at the bottom
  comparison   03-comparison   two images and a spec table (only when the official text gives both models)
  price        06-price        two prices split by a divider, availability, hero, quick take, CTA pill
Product images come from images/ in the item folder. A UI screenshot is never cropped: it is shown whole
(object-fit contain) in a 16:9 box. Every feature slide uses the same box (FEATURE_BOX). A feature slide with no
image of its own uses the text-led layout (no image box); it never shows another feature's image. Other slides with
no image draw only the soft glow (never an empty box).
"""
from __future__ import annotations

import html
import math
import re
from pathlib import Path

from images import image_dimensions

WIDTH, HEIGHT = 1080, 1440
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")  # a trimmed PNG is looked for first
SWIPE_TEXT = "SWIPE TO SEE WHAT'S NEW →"
WIDE_ASPECT = 1.3  # an image at least this wide for its height (a screenshot or video frame) is shown whole
# The one image box every feature slide uses: left, top, width, height. Full content width (64px margins), 16:9,
# ending 47px above the footer. A 1920 x 1080 frame fills it exactly, so nothing is cropped.
FEATURE_BOX = (64, 748, 952, 536)
FONT_FILES = {"display": "Inter-Black.ttf", "semibold": "Inter-SemiBold.ttf", "text": "Inter-Regular.ttf"}


class RenderError(RuntimeError):
    """Rendering could not run, for example because Playwright is not installed."""


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


# ---- images ----

def find_image(folder: Path, stem: str) -> Path | None:
    """The image file for a slot. A trimmed PNG (the grey poster border cropped off) always wins over a JPEG of the
    same name, so an untrimmed copy can never be rendered even if one is left in the folder."""
    for extension in IMAGE_EXTENSIONS:
        candidate = folder / f"{stem}{extension}"
        if candidate.exists():
            return candidate
    return None


def slot_images(images_dir: Path, views: list[dict]) -> tuple[list[dict], list[str]]:
    """The image for each slide (01.jpg for slide 1, and so on). Returns the images and the missing names.

    A slide with no image of its own gets None: a feature slide then uses the text-led layout, any other slide
    draws only the soft glow. An image from another slide is never borrowed here (that showed one feature's
    screenshot on another feature's slide). The cover reuse of a whole official frame is done by image_pick.
    """
    slots, missing = [], []
    for number, view in enumerate(views, 1):
        main = old = None
        if view["type"] in ("cover", "feature", "comparison", "price"):
            main = find_image(images_dir, f"{number:02d}")
            if main is None:
                missing.append(f"{number:02d}.jpg")
        if view["type"] == "comparison":
            old = find_image(images_dir, f"{number:02d}-old")
            if old is None:
                missing.append(f"{number:02d}-old.jpg")
        slots.append({"main": main, "old": old})
    # The cover collage uses the feature images (each one is its own feature's official image), in slide order.
    for slot, view in zip(slots, views):
        if view["type"] == "cover":
            slot["collage"] = [s["main"] for s, v in zip(slots, views)
                               if v["type"] == "feature" and s["main"] is not None]
    return slots, missing


def image_aspect(image: Path) -> float | None:
    """Width over height of an image file, or None when it cannot be read."""
    try:
        size = image_dimensions(image.read_bytes())
    except OSError:
        return None
    return size[0] / size[1] if size and size[1] else None


def _glow(left: float, top: float, width: float, height: float) -> str:
    glow_w, glow_h = int(width * 1.15), int(height * 0.9)
    return (
        f'<div class="glow" style="left:{left + (width - glow_w) / 2}px;top:{top + (height - glow_h) / 2}px;'
        f'width:{glow_w}px;height:{glow_h}px"></div>'
    )


def image_uri(image: Path) -> str:
    """A file:// address for an image. The path is resolved first, because a relative path has no file address."""
    return Path(image).resolve().as_uri()


def hero(image: Path | None, left: int, top: int, width: int, height: int) -> str:
    """The product image area. A wide image (a screenshot or demo video frame) is shown WHOLE (object-fit contain,
    never cropped) in a rounded frame with a thin subtle edge and a cyan glow, sized to its own shape inside the
    area. Any other image has no hard border, a soft glow behind and an edge fade.
    Without an image only the soft glow is drawn: never an empty box."""
    glow, element = hero_pair(image, left, top, width, height)
    return glow + element


def hero_pair(image: Path | None, left: int, top: int, width: int, height: int) -> tuple[str, str]:
    """(glow, image element) of a hero. A collage draws every glow first and then every tile, so no glow is painted
    over a neighbouring tile. The element is empty without an image."""
    if image is None:
        return _glow(left, top, width, height), ""
    aspect = image_aspect(image)
    if aspect and aspect >= WIDE_ASPECT:
        w, h = width, round(width / aspect)
        if h > height:
            w, h = round(height * aspect), height
        x, y = left + (width - w) // 2, top + (height - h) // 2
        return (_glow(x, y, w, h), f'<div class="hero screen" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">'
                f'<img src="{esc(image_uri(image))}" alt=""></div>')
    return (_glow(left, top, width, height),
            f'<div class="hero" style="left:{left}px;top:{top}px;width:{width}px;height:{height}px">'
            f'<img src="{esc(image_uri(image))}" alt=""></div>')


def feature_hero(image: Path | None) -> str:
    """The image of a feature slide: always in FEATURE_BOX, so every feature slide has the same box."""
    return hero(image, *FEATURE_BOX)


FEATURE_MAX_HEIGHT = 680  # a screenshot narrower than 16:9 may grow up to this tall, upward from the box bottom


def feature_box_for(image: Path | None, max_height: int = FEATURE_MAX_HEIGHT) -> tuple[int, int, int, int]:
    """The image area of a left_body feature slide (round 3h). A 16:9 frame fills FEATURE_BOX exactly. A screenshot
    narrower than 16:9 (the Camera Angles frame, about 1.54:1) keeps the same full content width, the same left and
    right margins, the same corner radius and the same bottom edge as the other slides: its area grows upward into the
    free space above the box instead of shrinking the frame. Nothing is cropped or stretched (object-fit contain).
    If the text above needs that room, the area is capped (max_height) and the frame is then narrower, centred."""
    left, top, width, height = FEATURE_BOX
    bottom = top + height
    aspect = image_aspect(image) if image is not None else None
    if not aspect or aspect < WIDE_ASPECT or aspect >= width / height:
        return FEATURE_BOX
    tall = min(round(width / aspect), max(height, max_height), FEATURE_MAX_HEIGHT)
    return left, bottom - tall, width, tall


# ---- text pieces ----

PILL_TOP = 120  # every slide's pill sits here, so the label does not jump between slides
FOOTER_TOP = 1330  # every slide's footer sits here (text stays 64px or more from the bottom edge)

# Text colours and the background they sit on, for the contrast check in design_check.
# "base" is the lightest part of the slide gradient; "glow" is the hero glow (the worst case).
BASE_BG, GLOW_BG = "#0c2b52", "#2d6fb0"
TEXT_STYLES = {
    "pill": ("#7fe2ff", BASE_BG, 28), "headline": ("#f4f8ff", BASE_BG, 128), "grad": ("#7fd7ff", BASE_BG, 128),
    "accent": ("#39d3f5", BASE_BG, 44), "body": ("#e9f2ff", BASE_BG, 32), "footer": ("#e8f3ff", BASE_BG, 26),
    "spec_caption": ("#cfe7ff", BASE_BG, 28), "gold": ("#f2c94c", BASE_BG, 36), "cyan_line": ("#39d3f5", BASE_BG, 34),
    "feature_names": ("#7fd7ff", BASE_BG, 38), "hook": ("#f4f8ff", BASE_BG, 50),
}


def split_headline(text: str, mode: str = "split") -> list[str]:
    """The lines a headline will show (used by the design check as well as the renderer)."""
    return _split_lines(text, mode)


def slide_layout(view: dict) -> dict:
    """Where the pill and footer sit on this slide, for the consistency check."""
    layout = {"pill_top": None, "footer_top": None}
    if view["type"] == "cover" or view["type"] in ("feature", "comparison", "price", "closing"):
        layout["pill_top"] = PILL_TOP if view["type"] != "comparison" else None
        layout["footer_top"] = FOOTER_TOP
    return layout


NBSP = " "
ROMAN_NUMERAL = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)$")


def _is_model_token(word: str) -> bool:
    return any(c.isdigit() for c in word) or bool(ROMAN_NUMERAL.match(word)) or word in ("MARK", "EOS")


def model_nbsp(line: str) -> str:
    """Joins model tokens with non-breaking spaces, so 'EOS R8 MARK II' never breaks inside the name."""
    out = []
    for word in line.split(" "):
        if out and _is_model_token(word) and _is_model_token(out[-1]):
            out[-1] = out[-1] + NBSP + word
        else:
            out.append(word)
    return " ".join(out)


def _split_lines(text: str, mode: str) -> list[str]:
    if "\n" in text:
        return [line.strip() for line in text.split("\n") if line.strip()]
    words = text.split()
    if mode == "single" or len(words) < 2:
        return [text]
    # Keep the model name together: 'CANON EOS' / 'R8 MARK II', not 'CANON EOS R8' / 'MARK II'.
    model_at = next((i for i, w in enumerate(words) if any(c.isdigit() for c in w)), 0)
    if 0 < model_at < len(words) and len(words) - model_at <= 4:
        return [" ".join(words[:model_at]), " ".join(words[model_at:])]
    half = math.ceil(len(words) / 2)
    return [" ".join(words[:half]), " ".join(words[half:])]


def headline_html(text: str, mode: str = "split") -> str:
    """Headline lines separated by line breaks. The last line gets the light-blue gradient (like
    'STABILIZATION' or 'R8 MARK II'). 'single' keeps one line and puts the gradient on the last word
    (like '40 FPS' or '4K 60P'). Model names are joined with non-breaking spaces."""
    lines = _split_lines(text, mode)
    if len(lines) == 1:
        words = lines[0].split(" ")
        if len(words) > 1:
            head, last = " ".join(words[:-1]), words[-1]
            return f'{esc(model_nbsp(head))}{NBSP if head else ""}<span class="grad">{esc(last)}</span>'
        return esc(model_nbsp(lines[0]))
    # A space before each break keeps the words apart in the text (PHOTOSHOP 2027, not PHOTOSHOP2027).
    body = [esc(model_nbsp(line)) for line in lines[:-1]]
    body.append(f'<span class="grad">{esc(model_nbsp(lines[-1]))}</span>')
    return " <br>".join(body)


def pill(label: str, top: int = PILL_TOP, align: str = "center", left: int = 72) -> str:
    if align == "left":
        return f'<div class="abs" style="top:{top}px;left:{left}px"><span class="pill">{esc(label)}</span></div>'
    return (f'<div class="abs" style="top:{top}px;left:0;width:{WIDTH}px;text-align:center">'
            f'<span class="pill">{esc(label)}</span></div>')


def text_box(cls: str, text: str, top: int, height: int, size: int, left: int = 0, width: int = WIDTH,
             align: str = "center", extra: str = "", safe: tuple[int, int] | None = None,
             max_lines: int | None = None) -> str:
    """A text element. safe = (left, right) is the horizontal area its ink must stay inside."""
    safe_attr = f' data-safe-left="{safe[0]}" data-safe-right="{safe[1]}"' if safe else ""
    safe_attr += f' data-max-lines="{max_lines}"' if max_lines else ""
    return (
        f'<div class="abs {cls}" data-fit="text"{safe_attr} style="top:{top}px;left:{left}px;width:{width}px;'
        f'height:{height}px;font-size:{size}px;text-align:{align};{extra}">{esc(text)}</div>'
    )


def headline_box(text: str, top: int, height: int, size: int, mode: str = "split",
                 left: int = 0, width: int = WIDTH, align: str = "center", max_lines: int = 2) -> str:
    """A headline in a fixed box. The browser shrinks it until it fits within max_lines and the width."""
    return (
        f'<h1 class="abs display headline" data-fit="headline" data-max-lines="{max_lines}" '
        f'style="top:{top}px;left:{left}px;width:{width}px;height:{height}px;font-size:{size}px;'
        f'text-align:{align}">{headline_html(text, mode)}</h1>'
    )


COMPARISON_MIN_SIZE = 56  # a one-line comparison title is never shown smaller than this
COMPARISON_TITLE_TOP = 84  # keeps the title's ink inside the 64px top margin (see comparison_body)


def comparison_two_lines(text: str) -> str | None:
    """'EOS R8 MARK II vs EOS R8' as two lines: 'EOS R8 MARK II' / 'vs EOS R8'. None when there is no ' vs '."""
    if " vs " not in text:
        return None
    new_name, old_name = text.split(" vs ", 1)
    return f'<span class="gold">{esc(model_nbsp(new_name))}<br>vs {esc(model_nbsp(old_name))}</span>'


def gold_headline(text: str, top: int, height: int, size: int, max_lines: int = 1) -> str:
    """The comparison title, gold. A title with ' vs ' is set on two lines from the start (new model, then
    'vs' and the old model), so it never runs past the side margins; the browser still shrinks it if needed.
    A title without ' vs ' is one line that shrinks to fit (down to COMPARISON_MIN_SIZE)."""
    alt = comparison_two_lines(text)
    alt_attrs = f' data-alt-html="{esc(alt)}" data-min-size="{COMPARISON_MIN_SIZE}"' if alt else ""
    if alt:
        max_lines = 2
        inner = alt
    else:
        inner = f'<span class="gold">{esc(model_nbsp(text))}</span>'
    return (
        f'<h2 class="abs display headline" data-fit="headline" data-max-lines="{max_lines}"{alt_attrs} '
        f'style="top:{top}px;left:64px;width:952px;height:{height}px;font-size:{size}px;text-align:center">'
        f'{inner}</h2>'
    )


def footer(product: str | None, swipe: bool = False) -> str:
    """Thin cyan lines either side of the product name, spaced caps, centred."""
    text = SWIPE_TEXT if swipe else product
    if not text:
        return ""
    return (
        f'<div class="abs footer" style="top:{FOOTER_TOP}px">'
        '<span class="fline"></span>'
        f'<span class="ftext" data-fit="footer">{esc(text)}</span>'
        '<span class="fline"></span></div>'
    )


# ---- icons (line art, cyan) ----

ICON_PATHS = {
    "sensor": '<rect x="8" y="16" width="48" height="32" rx="3"/><path d="M8 26h48M20 16v32M44 16v32"/>',
    "burst": '<rect x="18" y="6" width="36" height="26" rx="3"/><rect x="11" y="19" width="36" height="26" rx="3"/>'
             '<rect x="4" y="32" width="36" height="24" rx="3"/>',
    "focus": '<path d="M8 20V8h12M44 8h12v12M56 44v12H44M20 56H8V44"/><circle cx="32" cy="32" r="5"/>',
    "stabilize": '<circle cx="32" cy="32" r="22"/><path d="M32 4v12M32 48v12M4 32h12M48 32h12"/>'
                 '<circle cx="32" cy="32" r="3"/>',
    "video": '<rect x="6" y="16" width="36" height="32" rx="4"/><path d="M42 28l16-10v24l-16-10"/>',
    "battery": '<rect x="6" y="20" width="46" height="24" rx="3"/><path d="M56 28v8"/><path d="M14 28h14M14 36h8"/>',
    "box": '<path d="M32 6l24 13v26L32 58 8 45V19z"/><path d="M8 19l24 13 24-13M32 32v26"/>',
    "star": '<path d="M32 6l7.5 16 17.5 2-13 12 3.5 17L32 44 16 53l3.5-17-13-12 17.5-2z"/>',
}


def icon_svg(name: str) -> str:
    body = ICON_PATHS.get(name, ICON_PATHS["sensor"])
    return (f'<svg class="icon" viewBox="0 0 64 64" width="72" height="72" fill="none" stroke="#39d3f5" '
            f'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


# ---- templates ----

HERO_BOTTOM = 1296  # a hero image area ends here, clear of the footer


def feature_lines(names: list[str]) -> list[str]:
    """The feature names under the cover headline, as one or two centred lines: 'RELIGHT  ·  GENERATIVE RESTYLE'."""
    joiner = "  ·  "
    if len(names) <= 2:
        return [joiner.join(names)] if names else []
    half = math.ceil(len(names) / 2)
    return [joiner.join(names[:half]), joiner.join(names[half:])]


def _cover_text(view: dict) -> tuple[list[str], int]:
    """The cover's pill, headline, hook and feature lines, and the y where the hero space starts."""
    one_line = len(_split_lines(view["headline"], "split")) == 1
    head_top, head_h = (240, 164) if one_line else (226, 340)  # a one line name sits snug so the images get the room
    y = head_top + head_h + (0 if one_line else 10)
    parts = [pill(view["label"], PILL_TOP), headline_box(view["headline"], head_top, head_h, 160)]
    hook = view.get("subline")
    if hook:
        hook_h = hook_lines(hook) * 58 + 6
        parts.append(text_box("hook", hook, y, hook_h, 50, left=64, width=952, safe=(64, 1016), max_lines=2))
        y += hook_h + 14
    lines = feature_lines(view.get("features") or [])[:2]
    for number, line in enumerate(lines):
        parts.append(text_box("feat", line, y + number * 58, 54, 38))
    if lines:
        y += len(lines) * 58
    return parts, y


def cover_hero_images(view: dict, slots: dict) -> list[Path]:
    """The official images the cover hero shows: the collage tiles, else its own image, else (when the collage does
    not fit) the first feature's official image on its own. [] means the cover shows only the soft glow."""
    _, y = _cover_text(view)
    tiles = collage_tiles(slots.get("collage") or [], y + 20)
    if tiles:
        return [image for image, _ in tiles]
    main = slots.get("main") or next(iter(slots.get("collage") or []), None)
    return [main] if main else []


def cover_body(view: dict, slots: dict) -> str:
    """Pill (the event, or the label), headline, the hook (the confirmed scroll stopping line), at most two lines of
    light-blue feature names, then the hero: a whole, uncropped 16:9 frame at full content width when it fits."""
    parts, y = _cover_text(view)
    # With two or more official feature images the hero is a collage of them: the first (Relight) large on top, the
    # next two side by side under it across the full 952px content width. Otherwise it is one 16:9 box at full content
    # width, ending at HERO_BOTTOM. A tall text block makes it smaller (and centred); every image is still shown whole.
    tiles = collage_tiles(slots.get("collage") or [], y + 20)
    if tiles:
        pairs = [hero_pair(image, *rect) for image, rect in tiles]
        parts += [glow for glow, _ in pairs] + [element for _, element in pairs]
    else:
        top = max(HERO_BOTTOM - COVER_HERO_H, y + 30)
        height = HERO_BOTTOM - top
        width = min(952, round(height * 16 / 9))
        # No room for the collage and no cover image of its own: the first feature's official image, shown whole.
        main = slots.get("main") or next(iter(slots.get("collage") or []), None)
        parts.append(hero(main, 64 + (952 - width) // 2, top, width, height))
    parts.append(footer(view.get("product"), swipe=True))
    return "".join(parts)


COVER_HERO_H = 536  # the cover hero is a full-width 16:9 box when the text above leaves room for it
COLLAGE_GAP = 20  # between collage tiles: 16 to 24px
COLLAGE_MIN_SMALL = 300  # a small collage tile is never narrower than this (readable on a phone); else one hero
COLLAGE_BIG_RATIO = 1.25  # the first tile is at least this many times as wide as each of the others
COLLAGE_MAX_TILES = 3


def collage_layout(aspects: list[float], top: int, bottom: int = HERO_BOTTOM, left: int = 64, width: int = 952,
                   gap: int = COLLAGE_GAP) -> list[tuple[int, int, int, int]]:
    """Tile boxes (left, top, width, height) for a cover collage. The first aspect is the large tile.

    Three tiles: the large one on top, centred, and the other two side by side under it. The two lower tiles are as wide
    as the content area allows (each (width - gap) / 2, so 466px in 952px), and the large tile takes all the height that
    is left, never less than COLLAGE_BIG_RATIO times as wide as one lower tile (the lower tiles shrink first if the
    space is short). Two tiles: stacked, the same width, as large as the space allows. Every tile keeps its own aspect
    ratio, so nothing is cropped, and the block is centred in the space between `top` and `bottom`. Returns [] when there
    are not 2 or 3 tiles or the smaller tiles would be narrower than COLLAGE_MIN_SMALL."""
    if not 2 <= len(aspects) <= COLLAGE_MAX_TILES or any(a <= 0 for a in aspects):
        return []
    space = bottom - top
    big, small = aspects[0], aspects[1:]
    # Sizes are rounded down and positions rounded, so tiles never overlap and never leave the margins.
    if len(small) == 1:
        w = min(width, (space - gap) / (1 / big + 1 / small[0]))
        if w < COLLAGE_MIN_SMALL:
            return []
        h1, h2 = int(w / big), int(w / small[0])
        x, y = round(left + (width - w) / 2), round(top + (space - (h1 + gap + h2)) / 2)
        return [(x, y, int(w), h1), (x, y + h1 + gap, int(w), h2)]
    narrow = min(small)
    # Largest lower tile width s that keeps the large tile (the rest of the height) COLLAGE_BIG_RATIO times as wide.
    s = min((width - gap) / 2, big * (space - gap) / (COLLAGE_BIG_RATIO + big / narrow))
    if s < COLLAGE_MIN_SMALL:
        return []
    row_h = max(int(s / a) for a in small)
    big_h = min(space - gap - row_h, int(width / big))
    big_w = int(big_h * big)
    y0 = top + (space - (big_h + gap + row_h)) / 2
    y_row = round(y0) + big_h + gap
    x_row = left + (width - (2 * int(s) + gap)) / 2
    return [(round(left + (width - big_w) / 2), round(y0), big_w, big_h),
            (round(x_row), y_row, int(s), int(s / small[0])),
            (round(x_row) + int(s) + gap, y_row, int(s), int(s / small[1]))]


def collage_tiles(images: list[Path], top: int) -> list[tuple[Path, tuple[int, int, int, int]]]:
    """The cover collage as (image, box) pairs, or [] when the cover keeps its single hero. Only wide images (a
    screenshot or video frame) go in, in slide order: the first feature is the large tile."""
    wide = [(image, image_aspect(image)) for image in images]
    wide = [(image, aspect) for image, aspect in wide if aspect and aspect >= WIDE_ASPECT][:COLLAGE_MAX_TILES]
    rects = collage_layout([aspect for _, aspect in wide], top)
    return [(image, rect) for (image, _), rect in zip(wide, rects)]


def hook_lines(text: str) -> int:
    """How many lines the cover hook needs at 50px across 952px: one up to about 22 characters, otherwise two."""
    return 1 if len(text) <= 22 else 2


TEXT_BOTTOM = FEATURE_BOX[1] - 28  # the text above the feature image box ends by here


def _body_height(text: str, per_line: int, line_h: int) -> int:
    return math.ceil(len(text) / per_line) * line_h + 8


def left_body_body(view: dict, slots: dict) -> str:
    """Label, feature name, ONE cyan benefit line, one short sentence, then the image in FEATURE_BOX (the same
    box on every feature slide). With no image of its own the slide uses the text-led layout instead."""
    if slots.get("main") is None:
        return text_led_body(view)
    lines = max(1, min(2, len(_split_lines(view["headline"], "split"))))
    accent = view.get("accent")
    body = view.get("body")
    size = 148 if lines == 1 else 120
    box = feature_box_for(slots.get("main"))
    text_bottom = box[1] - 28
    while True:  # shrink the headline a little if a long body would crowd the image box
        head_top, head_h = 236, round(lines * size * 0.93) + 24
        end = head_top + head_h + 36
        end += 56 + 28 if accent else 0
        end += _body_height(body, 56, 42) if body else 0
        if end <= text_bottom or size <= 96:
            break
        size -= 8
    if end > text_bottom:  # the text needs the room: the taller frame gives way, never the text
        box = feature_box_for(slots.get("main"), max_height=FEATURE_BOX[1] + FEATURE_BOX[3] - (end + 28))
    parts = [
        pill(view["label"], PILL_TOP, align="left", left=64),
        headline_box(view["headline"], head_top, head_h, size, left=64, width=952, align="left"),
    ]
    # Hierarchy: headline, a 36px gap, the cyan benefit line (one line), a 28px gap, the body.
    y = head_top + head_h + 36
    if accent:
        parts.append(text_box("accent", accent, y, 56, 40, left=64, width=952, align="left", max_lines=1))
        y += 56 + 28
    if body:
        parts.append(text_box("body", body, y, _body_height(body, 56, 42), 30, left=64, width=952, align="left"))
    parts.append(hero(slots.get("main"), *box))
    parts.append(footer(view.get("product")))
    return "".join(parts)


TEXT_LED_TOP, TEXT_LED_BOTTOM = 204, HERO_BOTTOM  # the free area under the pill and above the footer
TEXT_LED_MIN_BLOCK = 700  # a block shorter than this gets roomier gaps (see text_led_body)
TEXT_LED_WIDTH_SHARE = 0.8  # the headline fills about 80% of the content width
TEXT_LED_BODY_SIZE = 38  # the body is at least 34px
TEXT_LED_BODY_LINE = 54
TEXT_LED_BODY_CHARS = 36  # characters per line used to reserve height (an estimate, on the safe side)
HEADLINE_EM = 0.68  # average width of a heavy uppercase letter, in em (an estimate; the browser shrinks any overshoot)
ACCENT_EM = 0.64


def text_led_headline_size(headline: str) -> int:
    """Font size at which the longest line of the headline fills about 80% of the 952px content width."""
    lines = _split_lines(headline, "split")[:2]
    longest = max(len(line) for line in lines)
    return max(96, min(200, round(TEXT_LED_WIDTH_SHARE * 952 / (longest * HEADLINE_EM))))


def text_led_accent_size(accent: str) -> int:
    """The cyan line starts large (up to 56px) and one line; the browser shrinks it only if it would be wider than 952px."""
    return max(40, min(56, int(952 / (max(1, len(accent)) * ACCENT_EM))))


def text_led_body(view: dict) -> str:
    """A feature slide with no official image of its own: no image box and no other feature's picture. It is a
    typographic slide: the feature name fills about 80% of the width, with the cyan line (up to 56px) and the sentence
    (38px) under it, on a soft brand glow. The block is centred in the free area, so the space above and below it
    is balanced and there is no large empty area. Same 64px margins as every slide."""
    lines = max(1, min(2, len(_split_lines(view["headline"], "split"))))
    size = text_led_headline_size(view["headline"])
    accent, body = view.get("accent"), view.get("body")
    accent_size = text_led_accent_size(accent) if accent else 0
    accent_h = round(accent_size * 1.3) if accent else 0
    body_h = (math.ceil(len(body) / TEXT_LED_BODY_CHARS) * TEXT_LED_BODY_LINE + 8) if body else 0
    free = TEXT_LED_BOTTOM - TEXT_LED_TOP
    gaps = 1 + (1 if accent else 0) + (1 if body else 0)  # rule to headline, headline to cyan line, cyan line to body
    while True:  # keep the whole block inside the free area, with 60px or more to spare at each end
        head_h = round(lines * size * 0.93) + 24
        block = 3 + 32 + head_h + ((44 + accent_h) if accent else 0) + ((36 + body_h) if body else 0)
        if block <= free - 120 or size <= 96:
            break
        size -= 8
    # A short block (a one word headline, a short sentence) gets roomier gaps, up to 48px more each, so it does not
    # float in a big empty slide.
    spare = min(48, max(0, TEXT_LED_MIN_BLOCK - block) // gaps)
    block += spare * gaps
    top = TEXT_LED_TOP + max(0, (free - block) // 2)
    parts = [_glow(64, top - 140, 952, block + 280), pill(view["label"], PILL_TOP)]
    parts.append(f'<div class="abs" style="top:{top}px;left:490px;width:100px;height:3px;background:#39d3f5"></div>')
    y = top + 3 + 32 + spare
    parts.append(headline_box(view["headline"], y, head_h, size, left=64, width=952, align="center"))
    y += head_h
    if accent:
        y += 44 + spare
        parts.append(text_box("accent", accent, y, accent_h, accent_size, left=64, width=952, align="center",
                              max_lines=1))
        y += accent_h
    if body:
        y += 36 + spare
        parts.append(text_box("body", body, y, body_h, TEXT_LED_BODY_SIZE, left=100, width=880, align="center"))
    parts.append(footer(view.get("product")))
    return "".join(parts)


def stat_specs_body(view: dict, slots: dict) -> str:
    parts = [
        pill(view["label"], PILL_TOP),
        headline_box(view["headline"], 200, 250, 196, mode="single", max_lines=1),
    ]
    if view.get("accent"):
        parts.append(text_box("spaced accent", view["accent"], 456, 60, 40, left=64, width=952, max_lines=1))
    specs = view["specs"]
    column = 952 // len(specs)
    for index, spec in enumerate(specs):
        left = 64 + index * column
        parts.append(
            f'<div class="abs spec" style="top:530px;left:{left}px;width:{column}px;height:200px">'
            f'{icon_svg(spec["icon"])}'
            f'<div class="spec-value" data-fit="text">{esc(spec["value"])}</div>'
            f'<div class="spec-caption" data-fit="text">{esc(spec["caption"])}</div></div>'
        )
        if index:
            parts.append(f'<div class="abs vdiv" style="top:546px;left:{left}px;height:150px"></div>')
    parts.append(feature_hero(slots.get("main")))
    parts.append(footer(view.get("product")))
    return "".join(parts)


def stat_hero_body(view: dict, slots: dict) -> str:
    parts = [
        pill(view["label"], PILL_TOP),
        headline_box(view["headline"], 200, 250, 208, mode="single", max_lines=1),
    ]
    if view.get("accent"):
        parts.append(text_box("spaced accent", view["accent"], 470, 60, 40, left=64, width=952, max_lines=1))
    if view.get("body"):
        parts.append(text_box("body center", view["body"], 566, 100, 32, left=100, width=880))
    parts.append(feature_hero(slots.get("main")))
    parts.append(footer(view.get("product")))
    return "".join(parts)


def comparison_body(view: dict, slots: dict) -> str:
    title = view["title"]
    if " vs " in title:
        new_name, old_name = title.split(" vs ", 1)
    else:
        new_name, old_name = title, ""
    # The title's ink must start 64px or more from the top edge. A line's text box is taller than its
    # line height, so the title box sits at 84px, not 40px (at 40px the ink started near 30px and could never fit).
    # Two-line title (new model / vs old model) at 92px: two lines need about 171px, so the box is 200px.
    parts = [
        gold_headline(title, COMPARISON_TITLE_TOP, 200, 92, max_lines=2),
        text_box("spaced cyan", view["label"], 292, 50, 28),
        hero(slots.get("main"), 60, 356, 440, 224),
        hero(slots.get("old"), 580, 356, 440, 224),
        '<div class="abs table" style="top:612px;left:60px;width:960px;height:680px">',
        f'<div class="row head"><div class="cell gold" data-fit="cell">{esc(model_nbsp(new_name))}</div>'
        '<div class="cell mid"></div>'
        f'<div class="cell" data-fit="cell">{esc(model_nbsp(old_name))}</div></div>',
    ]
    for row in view["rows"]:
        parts.append(
            '<div class="row">'
            f'<div class="cell gold" data-fit="cell">{esc(row["new"] or "")}</div>'
            f'<div class="cell mid spaced-small">{esc(row["name"])}</div>'
            f'<div class="cell" data-fit="cell">{esc(row["old"] or "")}</div>'
            "</div>"
        )
    parts.append("</div>")
    parts.append(footer(view.get("product")))
    return "".join(parts)


def price_body(view: dict, slots: dict) -> str:
    entries = view["prices"]
    column = WIDTH // len(entries)
    parts = [pill(view["label"], PILL_TOP)]
    for index, entry in enumerate(entries):
        left = index * column
        # Each column gets half the safe area (64 to 1016) minus a 20px gap either side of the divider.
        if len(entries) == 2:
            safe = (64, 520) if index == 0 else (560, 1016)
        else:
            safe = (64, 1016)
        parts.append(text_box("price", entry["value"], 196, 150, 140, left=left, width=column, safe=safe))
        if entry.get("caption"):
            parts.append(text_box("spaced caption", entry["caption"], 348, 40, 28, left=left, width=column,
                                  safe=safe))
    if len(entries) == 2:
        parts.append(f'<div class="abs vdiv" style="top:200px;left:539px;height:190px"></div>')
    if view.get("availability"):
        parts.append(
            '<div class="abs avail" style="top:414px;left:72px;width:936px">'
            '<span class="rule"></span>'
            f'<span class="spaced cyan" data-fit="text">{esc(view["availability"])}</span>'
            '<span class="rule"></span></div>'
        )
    quick = view.get("quick_take")
    hero_height = 430 if quick else 600
    parts.append(hero(slots.get("main"), 150, 480, 780, hero_height))
    if quick:
        parts.append(
            '<div class="abs quick-label" style="top:938px;left:72px;width:936px">'
            '<span class="rule"></span><span class="spaced cyan">Our quick take</span><span class="rule"></span></div>'
        )
        parts.append(text_box("quick-sentence", quick["sentence"], 984, 90, 34, left=110, width=860))
        parts.append(headline_box(quick["question"], 1080, 110, 52, mode="single", left=60, width=960, max_lines=1))
    parts.append(
        f'<div class="abs" style="top:1206px;left:0;width:{WIDTH}px;text-align:center">'
        f'<span class="pill cta">{esc(view["cta"])}</span></div>'
    )
    parts.append(footer(view.get("product")))
    return "".join(parts)


CLOSING_HEADLINE_TOP, CLOSING_HEADLINE_H = 300, 340  # two lines of the question, centred in the upper third
CLOSING_RECAP_TOP = 712  # the "In this post" rule, then the feature names
CLOSING_RECAP_STEP = 76
CLOSING_RECAP_STEP_5 = 68
CLOSING_RECAP_MAX = 5
CLOSING_CTA_TOP = 1150  # the call to action pill, clear of the footer at FOOTER_TOP


def closing_body(view: dict, slots: dict) -> str:
    """The last slide, a clear call to action: the pill, the question as a two-line headline (last line in the brand
    gradient), a recap of the feature names already shown (one per line, light blue), the save and comment pill, and
    the TPM name in the footer. Every line keeps the 64px safe margin, so nothing is cut off in the Facebook or
    Instagram feed. No product image and no product fact: it is the same on every carousel."""
    parts = [pill(view["label"], PILL_TOP), _glow(140, CLOSING_HEADLINE_TOP, 800, CLOSING_HEADLINE_H)]
    parts.append(headline_box(view["headline"], CLOSING_HEADLINE_TOP, CLOSING_HEADLINE_H, 124,
                              left=64, width=952, max_lines=2))
    if view.get("features"):
        parts.append(
            f'<div class="abs quick-label" style="top:{CLOSING_RECAP_TOP}px;left:72px;width:936px">'
            '<span class="rule"></span><span class="spaced cyan">In this post</span><span class="rule"></span></div>')
        names = view["features"][:CLOSING_RECAP_MAX]
        step = CLOSING_RECAP_STEP if len(names) <= 4 else CLOSING_RECAP_STEP_5  # 5 lines end at 1116, above the CTA
        for index, name in enumerate(names):
            parts.append(text_box("feat", name, CLOSING_RECAP_TOP + 72 + index * step, 60, 40,
                                  left=64, width=952, safe=(64, 1016), max_lines=1))
    parts.append(
        f'<div class="abs" style="top:{CLOSING_CTA_TOP}px;left:0;width:{WIDTH}px;text-align:center">'
        f'<span class="pill cta">{esc(view["cta"])}</span></div>')
    parts.append(footer(view.get("footer")))
    return "".join(parts)


BODY = {
    "cover": cover_body,
    "left_body": left_body_body,
    "stat_specs": stat_specs_body,
    "stat_hero": stat_hero_body,
    "comparison": comparison_body,
    "price": price_body,
    "closing": closing_body,
}


def template_key(view: dict) -> str:
    return view["template"] if view["type"] == "feature" else view["type"]


def slide_css(font_dir: Path | None) -> str:
    faces = []
    if font_dir is not None:
        for name, file in FONT_FILES.items():
            path = font_dir / file
            if path.exists():
                weight = {"display": 900, "semibold": 600, "text": 400}[name]
                family = "TPMDisplay" if name == "display" else "TPMText"
                faces.append(f'@font-face{{font-family:"{family}";src:url("{path.resolve().as_uri()}");font-weight:{weight};}}')
    return "\n".join(faces) + CSS


CSS = """
*{margin:0;padding:0;box-sizing:border-box;hyphens:none;-webkit-hyphens:none}
html,body{width:1080px;height:1440px;overflow:hidden;background:#02050c}
.slide{position:relative;width:1080px;height:1440px;overflow:hidden;color:#f4f8ff;
font-family:"TPMText","Inter","Segoe UI",Arial,sans-serif;
background:radial-gradient(60% 34% at 50% 58%,rgba(44,146,255,.42),rgba(44,146,255,0) 72%),
linear-gradient(180deg,#0c2b52 0%,#071a35 42%,#040c1c 78%,#02050c 100%)}
.abs{position:absolute}
.display,.headline{font-family:"TPMDisplay","Inter","Arial Black","Segoe UI Black",Arial,sans-serif;
font-weight:900;text-transform:uppercase;line-height:.93;letter-spacing:-.02em;color:#f4f8ff;overflow:hidden}
.headline{position:absolute}
.headline{text-wrap:balance;white-space:normal}
.grad{background:linear-gradient(180deg,#f0fbff 0%,#7fd7ff 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.gold{background:linear-gradient(180deg,#fff3c4 0%,#f2c94c 100%);-webkit-background-clip:text;background-clip:text;color:transparent}
.pill{display:inline-block;height:84px;line-height:78px;padding:0 42px;border:3px solid #39d3f5;border-radius:999px;
color:#7fe2ff;text-transform:uppercase;letter-spacing:.26em;font-weight:600;font-size:28px;white-space:nowrap;
box-shadow:0 0 22px rgba(57,211,245,.22)}
.pill.cta{letter-spacing:.2em;font-size:28px}
.spaced{text-transform:uppercase;letter-spacing:.2em;font-weight:500}
.spaced-small{text-transform:uppercase;letter-spacing:.12em;font-size:18px;font-weight:500;color:#39d3f5}
.sub{color:#f4f8ff;font-weight:500;text-transform:uppercase;letter-spacing:.2em;white-space:nowrap}
.accent{color:#39d3f5;font-weight:600;text-transform:uppercase;letter-spacing:.03em;white-space:nowrap}
.spaced.accent,.spaced-accent{letter-spacing:.14em}
.cyan{color:#39d3f5}
.body,.text,.quick-sentence,.caption,.hook,.accent-wrap{text-wrap:balance}
.body{color:#e9f2ff;line-height:1.38;font-weight:400}
.body center{color:#e9f2ff}
.text{color:#f4f8ff}
.glow{position:absolute;border-radius:50%;
background:radial-gradient(closest-side,rgba(64,165,255,.40),rgba(64,165,255,.12) 55%,rgba(64,165,255,0) 100%)}
.hero{position:absolute;overflow:hidden}
.hero img{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:contain;display:block;
-webkit-mask-image:radial-gradient(closest-side at 50% 48%,#000 70%,rgba(0,0,0,0) 100%);
mask-image:radial-gradient(closest-side at 50% 48%,#000 70%,rgba(0,0,0,0) 100%)}
.hero.screen{border-radius:20px;border:1px solid rgba(127,220,255,.38);
box-shadow:0 0 64px rgba(64,165,255,.32),0 24px 56px rgba(0,0,0,.5)}
.hero.screen img{object-fit:contain;-webkit-mask-image:none;mask-image:none}
.hook{color:#f4f8ff;font-weight:800;text-transform:uppercase;letter-spacing:.04em;line-height:1.1;white-space:normal}
.feat{color:#7fd7ff;font-weight:700;text-transform:uppercase;letter-spacing:.12em;white-space:nowrap}
.accent-wrap{white-space:normal;line-height:1.12;letter-spacing:.02em}
.footer{left:0;right:0;height:40px;display:flex;align-items:center;justify-content:center;gap:26px}
.fline{flex:0 0 170px;height:2px;background:#39d3f5;opacity:.9}
.ftext{font-size:26px;letter-spacing:.3em;text-transform:uppercase;white-space:nowrap;color:#e8f3ff;font-weight:500}
.spec{text-align:center}
.spec .icon{display:block;margin:0 auto 14px auto}
.spec-value{font-family:"TPMDisplay","Inter","Arial Black",Arial,sans-serif;font-weight:900;font-size:44px;
line-height:1.05;text-transform:uppercase;color:#f4f8ff;padding:0 10px;overflow:hidden;white-space:nowrap}
.spec-caption{font-size:28px;color:#cfe7ff;margin-top:8px;padding:0 10px;overflow:hidden;white-space:nowrap}
.vdiv{position:absolute;width:1.5px;height:190px;background:linear-gradient(180deg,rgba(57,211,245,0),rgba(57,211,245,.8),rgba(57,211,245,0))}
.avail{display:flex;align-items:center;gap:24px;height:50px}
.avail .rule,.quick-label .rule{flex:1;height:2px;background:#39d3f5;opacity:.85}
.avail span.spaced{font-size:34px;letter-spacing:.2em;white-space:nowrap}
.quick-label{display:flex;align-items:center;gap:24px;height:40px}
.quick-label span.spaced{font-size:24px;letter-spacing:.24em;white-space:nowrap}
.quick-sentence{color:#e9f2ff;line-height:1.35;font-weight:400}
.price{font-family:"TPMDisplay","Inter","Arial Black",Arial,sans-serif;font-weight:900;text-transform:none;
color:#f4f8ff;white-space:nowrap;line-height:1;letter-spacing:-.02em;overflow:hidden}
.caption{color:#e9f2ff}
.table{border-top:1px solid rgba(143,211,255,.25)}
.row{display:flex;align-items:center;height:96px;border-bottom:1px solid rgba(143,211,255,.22)}
.row.head{height:120px;align-items:flex-start;padding-top:12px;border-bottom:1px solid rgba(143,211,255,.3)}
.cell{width:400px;text-align:center;font-size:36px;font-weight:600;text-transform:uppercase;line-height:1.2;
padding:0 10px;overflow:hidden;color:#f4f8ff}
.cell.gold{color:#f2c94c}
.cell.mid{width:160px;font-size:19px;font-weight:500;color:#39d3f5;letter-spacing:.12em}
.row.head .cell{font-size:44px;font-weight:900;letter-spacing:-.01em;white-space:nowrap}
"""

FIT_SCRIPT = """() => {
  // Ink = the boxes of the non-empty text nodes only (not element boxes, not empty strings).
  // Every line of ink is checked against its safe area: x from data-safe-left to data-safe-right
  // (default 64 to 1016 on a 1080 slide), y from 64 to 1376. Lines are the clusters of ink rects.
  const SAFE_L = 64, SAFE_R = 1016, SAFE_T = 64, SAFE_B = 1376;
  const inkRects = (el) => {
    const rects = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) {
        if (r.width > 0 && r.height > 0) rects.push(r);
      }
    }
    return rects;
  };
  const clusterLines = (rects) => {
    const sorted = rects.slice().sort((a, b) => a.top - b.top);
    const lines = [];
    for (const r of sorted) {
      const last = lines[lines.length - 1];
      if (last && r.top < last.bottom - 2) {
        last.left = Math.min(last.left, r.left);
        last.right = Math.max(last.right, r.right);
        last.top = Math.min(last.top, r.top);
        last.bottom = Math.max(last.bottom, r.bottom);
      } else {
        lines.push({left: r.left, right: r.right, top: r.top, bottom: r.bottom});
      }
    }
    return lines;
  };
  const measure = (el) => {
    const rects = inkRects(el);
    const lines = clusterLines(rects);
    const safeL = parseFloat(el.dataset.safeLeft || SAFE_L);
    const safeR = parseFloat(el.dataset.safeRight || SAFE_R);
    const maxLines = parseInt(el.dataset.maxLines || '0', 10);
    // Text that is cut off by its own box (too tall, or too wide for a no-wrap box) also counts as not fitting.
    const heightOverflow = el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
    const inside = lines.every((l) => l.left >= safeL && l.right <= safeR && l.top >= SAFE_T && l.bottom <= SAFE_B);
    const countOk = !maxLines || lines.length <= maxLines;
    return {rects, lines, maxLines, ok: inside && countOk && !heightOverflow};
  };
  const result = {problems: [], boxes: []};
  document.querySelectorAll('[data-fit]').forEach((el) => {
    const text = el.textContent.trim();
    if (!text) return;
    let size = parseFloat(getComputedStyle(el).fontSize);
    const startSize = size;
    const floor = size * 0.5;
    // data-alt-html + data-min-size: shrink on one line down to the minimum size; if it still does not
    // fit, switch to the two-line version (max 2 lines) and shrink that from the starting size.
    const altHtml = el.dataset.altHtml;
    const minSize = parseFloat(el.dataset.minSize || '0');
    const stopAt = altHtml && minSize ? minSize : floor;
    let m = measure(el);
    while (!m.ok && size > stopAt) {
      size -= 1;
      el.style.fontSize = size + 'px';
      m = measure(el);
    }
    if (!m.ok && altHtml && minSize) {
      el.innerHTML = altHtml;
      el.dataset.maxLines = '2';
      size = startSize;
      el.style.fontSize = size + 'px';
      m = measure(el);
      while (!m.ok && size > floor) {
        size -= 1;
        el.style.fontSize = size + 'px';
        m = measure(el);
      }
    }
    if (!m.ok) {
      result.problems.push(el.dataset.fit + ' "' + text.slice(0, 40) + '"');
    }
    if (m.rects.length === 0) return;
    result.boxes.push({
      name: el.dataset.fit, text: text,
      left: Math.min(...m.lines.map((l) => l.left)), right: Math.max(...m.lines.map((l) => l.right)),
      top: Math.min(...m.lines.map((l) => l.top)), bottom: Math.max(...m.lines.map((l) => l.bottom)),
      lines: m.lines.length, max_lines: m.maxLines, size: size,
      width: el.clientWidth, last_width: m.lines[m.lines.length - 1].right - m.lines[m.lines.length - 1].left,
    });
  });
  return result;
}"""


def slide_document(view: dict, slots: dict, font_dir: Path | None) -> str:
    body = BODY[template_key(view)](view, slots)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<style>{slide_css(font_dir)}</style></head><body><div class=\"slide\">{body}</div></body></html>"
    )


# ---- browser steps ----

def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RenderError(
            "Playwright is not installed. Run: pip install playwright, then: playwright install chromium"
        ) from exc
    return sync_playwright


def render_pngs(documents: list[str], out_paths: list[Path], work_dir: Path,
                measure_log: list | None = None) -> list[str]:
    """Writes each slide to a PNG at 1080 x 1440. Returns overflow problems (empty when all fit).

    When measure_log is a list, one entry per slide is appended: {"boxes": [...measured text boxes]}.
    Each box has name, text, left, right, top, bottom, lines and the final font size.
    """
    sync_playwright = _playwright()
    work_dir.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            for number, (document, out_path) in enumerate(zip(documents, out_paths), 1):
                source = work_dir / f"slide-{number:02d}.html"
                source.write_text(document, encoding="utf-8")
                page.goto(source.resolve().as_uri(), wait_until="load")
                page.evaluate("() => document.fonts.ready.then(() => true)")
                result = page.evaluate(FIT_SCRIPT)
                problems += [f"slide {number:02d}: text does not fit its box: {p}" for p in result["problems"]]
                if measure_log is not None:
                    measure_log.append({"boxes": result["boxes"]})
                page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
        finally:
            browser.close()
    return problems


def render_contact_sheet(pngs: list[Path], out_path: Path, work_dir: Path) -> None:
    """All slides side by side (two rows when there are more than six)."""
    sync_playwright = _playwright()
    cell_w, cell_h, gap = 300, 400, 24
    columns = len(pngs) if len(pngs) <= 6 else math.ceil(len(pngs) / 2)
    rows = math.ceil(len(pngs) / columns)
    width = columns * cell_w + (columns + 1) * gap
    height = rows * cell_h + (rows + 1) * gap
    tiles = "".join(
        f'<img src="{esc(image_uri(p))}" style="width:{cell_w}px;height:{cell_h}px;object-fit:cover;'
        'border-radius:6px;display:block">'
        for p in pngs
    )
    document = (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        "html,body{margin:0;background:#050b16}"
        f"#sheet{{display:grid;grid-template-columns:repeat({columns},{cell_w}px);gap:{gap}px;padding:{gap}px;"
        f"width:{width}px}}"
        "</style></head><body>"
        f'<div id="sheet">{tiles}</div></body></html>'
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    source = work_dir / "contact-sheet.html"
    source.write_text(document, encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
            page.goto(source.resolve().as_uri(), wait_until="load")
            page.screenshot(path=str(out_path), full_page=True)
        finally:
            browser.close()
