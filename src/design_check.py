"""Senior-design QA for the slides and captions. Returns FAIL and WARN findings.

FAIL stops the build: more than two headline lines, body text over one sentence, pill or footer in a
different place from slide to slide, text contrast below WCAG AA, text within 64 px of the slide edge
(measured in the browser), fewer than 4 or more than 7 slides, captions of 50 words or more, and a slide with an
official image whose text covers as much of the slide as the image does (Kint's rule: the image is always bigger than
the text; measured in the browser, image area against the ink boxes of all the text).
WARN is printed and written to factcheck.md but does not stop the build: a widow (one word alone on the
last headline line), caption sentences that open with the same word, and a caption hook of 10 words or more.

Contrast uses the palette in carousel_render.TEXT_STYLES: a design-token check, not a pixel sample.
"""
from __future__ import annotations

import re

import carousel_plan
import carousel_render

MIN_SLIDES, MAX_SLIDES = 4, 7
HEADLINE_LINES_MAX = 2
SINGLE_LINE_TEMPLATES = ("stat_specs", "stat_hero", "comparison")  # their headlines stay on one line
EDGE_MARGIN = 56  # minimum distance from the slide edge to the text's ink (the references use about 60 to 70)
SLIDE_W, SLIDE_H = carousel_render.WIDTH, carousel_render.HEIGHT
BODY_SENTENCES_MAX = 1
FEATURE_NAME_WORDS_MAX = 5  # a feature slide's headline is the feature name, not a sentence


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    light, dark = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _finding(level: str, slide, rule: str, message: str) -> dict:
    return {"level": level, "slide": slide, "rule": rule, "message": message}


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


FEATURE_STACK_WORDS = (2, 3)  # a feature name of this many words may be stacked one word per line (REMOVE / TOOL)
WIDOW_WIDTH_SHARE = 0.2  # a body text whose last line is narrower than this share of the box is a widow


def _feature_name_stack(view: dict, headline: str) -> bool:
    """True for a feature slide whose headline is a two or three word feature name. The references stack names like
    'QUICK / COMPARE' on purpose, so a break between its words is a design choice, not a widow."""
    return view.get("type") == "feature" and len(headline.split()) in FEATURE_STACK_WORDS


def _model_name_line(last_line: str) -> bool:
    """True when the last headline line is the model part of a product name ('PHOTOSHOP / 2027', 'EOS R8 / MARK II').
    The renderer splits a name before its model number on purpose, so that line is not a widow."""
    words = last_line.split()
    return len(words) == 1 and carousel_render._is_model_token(words[0])


def check_slides(views: list[dict], measure_log: list | None = None) -> list[dict]:
    findings: list[dict] = []
    count = len(views)
    if not MIN_SLIDES <= count <= MAX_SLIDES:
        findings.append(_finding("FAIL", None, "slide count",
                                 f"{count} slides; a carousel needs {MIN_SLIDES} to {MAX_SLIDES}"))

    pill_tops, footer_tops = set(), set()
    for number, view in enumerate(views, 1):
        layout = carousel_render.slide_layout(view)
        if layout["pill_top"] is not None:
            pill_tops.add(layout["pill_top"])
        if layout["footer_top"] is not None:
            footer_tops.add(layout["footer_top"])
        headline = view.get("headline") or view.get("title")
        if headline:
            single = view.get("template") in SINGLE_LINE_TEMPLATES or view["type"] == "comparison"
            lines = carousel_render.split_headline(headline, "single" if single else "split")
            limit = 1 if single else HEADLINE_LINES_MAX
            if len(lines) > limit:
                findings.append(_finding("FAIL", number, "headline lines",
                                         f"headline has {len(lines)} lines, the limit is {limit}: {headline!r}"))
            if re.search(r"[()\[\]]", headline):
                findings.append(_finding("FAIL", number, "headline brackets",
                                         f"headline has brackets, the feature name stands alone: {headline!r}"))
            if view["type"] == "feature" and len(headline.split()) > FEATURE_NAME_WORDS_MAX:
                findings.append(_finding("WARN", number, "headline length",
                                         f"headline is more than {FEATURE_NAME_WORDS_MAX} words, "
                                         f"it should be the feature name only: {headline!r}"))
            if (len(lines) >= 2 and len(lines[-1].split()) == 1 and not _feature_name_stack(view, headline)
                    and not _model_name_line(lines[-1])):
                findings.append(_finding("WARN", number, "widow",
                                         f"one word alone on the last line: {lines[-1]!r}"))
        if view["type"] == "feature" and not view.get("accent"):
            findings.append(_finding("WARN", number, "cyan line",
                                     "this feature slide has no cyan benefit line (its accent was not confirmed)"))
        body = view.get("body")
        if body:
            if len(_sentences(body)) > BODY_SENTENCES_MAX or len(body) > carousel_plan.BODY_MAX:
                findings.append(_finding("FAIL", number, "body copy",
                                         f"body is more than one short sentence: {body!r}"))
        if measure_log and number - 1 < len(measure_log):
            findings += _measured(number, measure_log[number - 1]["boxes"])
            findings += image_vs_text(number, measure_log[number - 1])

    if len(pill_tops) > 1:
        findings.append(_finding("FAIL", None, "pill position",
                                 f"pills sit at different heights: {sorted(pill_tops)}"))
    if len(footer_tops) > 1:
        findings.append(_finding("FAIL", None, "footer position",
                                 f"footers sit at different heights: {sorted(footer_tops)}"))
    return findings


def _measured(number: int, boxes: list[dict]) -> list[dict]:
    """Browser measurements. Each box is the ink of one text element (empty text was never measured)."""
    findings = []
    for box in boxes:
        if not box.get("text"):
            continue
        limit = box.get("max_lines") or 0
        if limit and box["lines"] > limit:
            findings.append(_finding("FAIL", number, "headline lines",
                                     f"headline wraps to {box['lines']} lines in the browser, the limit is {limit}"))
        # A real widow in body text: a short sentence whose last line is only a word or two (measured in the browser).
        if (box.get("name") == "text" and box["lines"] >= 2 and box.get("width")
                and box.get("last_width", box["width"]) < WIDOW_WIDTH_SHARE * box["width"]):
            findings.append(_finding("WARN", number, "widow",
                                     f"body text ends with a very short last line: {box['text'][:60]!r}"))
        if (box["left"] < EDGE_MARGIN or box["right"] > SLIDE_W - EDGE_MARGIN
                or box["top"] < EDGE_MARGIN or box["bottom"] > SLIDE_H - EDGE_MARGIN):
            findings.append(_finding("FAIL", number, "edge margin",
                                     f"text ink is closer than {EDGE_MARGIN}px to the edge: {box['text'][:40]!r}"))
    return findings


def areas(entry: dict) -> tuple[float, float]:
    """(image area, text area) of one measured slide, in square pixels: the images as shown (a flat-edged image's card
    counts whole) and the ink box of every text element."""
    image = sum(max(0.0, i["width"]) * max(0.0, i["height"]) for i in entry.get("images") or [])
    text = sum(max(0.0, b["right"] - b["left"]) * max(0.0, b["bottom"] - b["top"]) for b in entry.get("boxes") or [])
    return image, text


def image_vs_text(number: int, entry: dict) -> list[dict]:
    """Kint's standing rule: on a slide with an official image, the image takes more of the slide than the text."""
    image, text = areas(entry)
    if not entry.get("images") or image > text:
        return []
    slide = SLIDE_W * SLIDE_H
    return [_finding("FAIL", number, "image bigger than text",
                     f"the image covers {image / slide:.0%} of the slide and the text {text / slide:.0%}; "
                     "the image must be bigger than the text")]


def check_contrast() -> list[dict]:
    findings = []
    for style, (colour, background, size) in carousel_render.TEXT_STYLES.items():
        needed = 3.0 if size >= 24 else 4.5  # WCAG AA: large text 3:1, normal text 4.5:1
        ratio = contrast_ratio(colour, background)
        if ratio < needed:
            findings.append(_finding("FAIL", None, "contrast",
                                     f"{style} text is {ratio:.2f}:1 on its background, needs {needed}:1"))
    return findings


def check_captions(captions: dict[str, str]) -> list[dict]:
    findings = []
    for who, text in captions.items():
        words = len(text.split())
        if words >= carousel_plan.CAPTION_WORDS_MAX:
            findings.append(_finding("FAIL", None, "caption length",
                                     f"{who} caption is {words} words; it must be under {carousel_plan.CAPTION_WORDS_MAX}"))
        first = _sentences(text)[0] if _sentences(text) else ""
        if len(first.split()) > carousel_plan.CAPTION_HOOK_WORDS_MAX:
            findings.append(_finding("WARN", None, "caption hook",
                                     f"{who} caption opens with a {len(first.split())} word sentence; the hook must be "
                                     f"under {carousel_plan.CAPTION_HOOK_WORDS_MAX + 1} words"))
        openers = [s.split()[0].lower().strip("'\"") for s in _sentences(text) if s.split()]
        repeated = sorted({w for w in openers if openers.count(w) > 1})
        if repeated:
            findings.append(_finding("WARN", None, "repeated openers",
                                     f"{who} caption opens several sentences with: {', '.join(repeated)}"))
    return findings


def check_caption_voice(captions: dict[str, str]) -> list[dict]:
    """WARN when David's caption is not in the first person or TPM's caption never says we."""
    return [_finding("WARN", None, "caption voice", problem) for problem in carousel_plan.caption_voice_problems(captions)]


def run_design_check(views: list[dict], captions: dict[str, str], measure_log: list | None = None) -> list[dict]:
    findings = (check_slides(views, measure_log) + check_contrast() + check_captions(captions)
                + check_caption_voice(captions))
    if measure_log is None:
        findings.append(_finding("WARN", None, "edge margin",
                                 "not measured: run without --skip-render to check text edges in the browser"))
    return findings


def has_failures(findings: list[dict]) -> bool:
    return any(f["level"] == "FAIL" for f in findings)


def summary_lines(findings: list[dict]) -> list[str]:
    if not findings:
        return ["Design check: passed, no findings."]
    lines = [f"Design check: {sum(f['level'] == 'FAIL' for f in findings)} fail, "
             f"{sum(f['level'] == 'WARN' for f in findings)} warn."]
    for f in findings:
        where = f"slide {f['slide']:02d}" if f["slide"] else "all slides"
        lines.append(f"  {f['level']} ({f['rule']}, {where}): {f['message']}")
    return lines


def markdown(findings: list[dict]) -> str:
    lines = ["## Design check", ""]
    if not findings:
        lines.append("Passed. No findings.")
    else:
        lines += ["| Level | Rule | Where | Finding |", "|---|---|---|---|"]
        for f in findings:
            where = f"slide {f['slide']:02d}" if f["slide"] else "all"
            lines.append(f"| {f['level']} | {f['rule']} | {where} | {f['message'].replace('|', '/')} |")
    lines.append("")
    return "\n".join(lines)
