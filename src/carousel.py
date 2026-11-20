"""Carousel drafts for one sent story: find the official page, draft, fact-check, design check, render.
Posts nothing, anywhere.

python src/carousel.py --list                          Sent official stories that can make a carousel.
python src/carousel.py --story 12                      Build the carousel for stored story 12.
python src/carousel.py --story https://site/post       Same, found by one of the story's article links.
python src/carousel.py --story 12 --official-url URL   Use this official page instead of searching.
python src/carousel.py --story 12 --skip-render        Write the text files only (no Playwright needed).
python src/carousel.py --sample                        Offline visual check: the Canon EOS R8 Mark II sample (every template).
python src/carousel.py --sample photoshop              Offline visual check: the Photoshop 2027 sample.

Facts always come from the brand's official page. Article sites are only used to find links to it.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

import activity
import border_trim
import carousel_plan
import carousel_render
import carousel_status
import claude_cache
import classify
import dashboard
import dedupe
import design_check
import downloads
import image_override
import image_pick
import images
import official
import official_index
import timing
from carousel_text import LintError, lint_overflow, lint_texts

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "carousel.yaml"
RULES_PATH = ROOT / "config" / "rules.yaml"
DATA_PATH = ROOT / "data" / "seen.sqlite"
OUTPUT_ROOT = ROOT / "output" / "carousels"
SAMPLE_ROOT = ROOT / "output" / "samples"  # offline sample drafts; kept apart from real drafts
FONT_DIR = ROOT / "assets" / "fonts"
SAMPLES = {
    "photoshop": ROOT / "fixtures" / "carousel" / "photoshop-2027.json",
    "camera": ROOT / "fixtures" / "carousel" / "canon-eos-r8-mark-ii.json",
}
DEFAULT_SAMPLE = "camera"
DEFAULT_MODEL = "sonnet"
MIN_OFFICIAL_CHARS = official.MIN_OFFICIAL_CHARS
STOP_ANCHORS = {"the", "and", "for"}
# Product lines a round-up page can cover. A story naming one of them gets only that page section as facts.
PRODUCT_LINES = ("photoshop", "lightroom", "premiere", "illustrator", "indesign", "after effects",
                 "frame.io", "firefly", "camera raw")


def story_product_terms(title: str) -> tuple[list[str], list[str]]:
    """(this story's product lines, the other product lines), from the story title."""
    lowered = title.lower()
    mine = [p for p in PRODUCT_LINES if re.search(rf"\b{re.escape(p)}\b", lowered)]
    return mine, [p for p in PRODUCT_LINES if p not in mine]


class Refused(Exception):
    """A plain reason the carousel cannot be made. Not a bug: it is shown to the user as is."""


@dataclass
class OfficialPage:
    """text is the fact source: for a round-up page, only the sections about this story's product."""
    url: str
    text: str
    markup: str
    pages: list[tuple[str, str]] = field(default_factory=list)  # official pages to search for images
    terms: list[str] = field(default_factory=list)  # the product names looked for in the page
    note: str = ""  # how the fact source was cut from the page, for sources.md


# ---- config and story lookup ----

def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    config.setdefault("use_official_press_images", False)
    config.setdefault("draft_model", DEFAULT_MODEL)
    config.setdefault("factcheck_model", DEFAULT_MODEL)
    config.setdefault("image_check_model", DEFAULT_MODEL)
    config.setdefault("official_domains", {})
    config.setdefault("official_indexes", {})
    config.setdefault("official_pages", {})
    config.setdefault("image_pages", {})
    config.setdefault("image_check_workers", 3)
    config.setdefault("closing_slide", True)
    config.setdefault("page_cache_hours", 6)
    return config


def load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as handle:
        return classify.normalize_rules(yaml.safe_load(handle))


def find_story(store: dedupe.Store, key: str, now: datetime):
    stories = store.recent_stories(3650, now)
    if key.isdigit():
        match = next((s for s in stories if s.id == int(key)), None)
    elif key.lower().startswith(("http://", "https://")):
        target = dedupe.canonical_url(key)
        match = next(
            (s for s in stories for src in s.sources
             if dedupe.canonical_url(src["url"]) == target
             or dedupe.canonical_url(src.get("link") or src["url"]) == target),
            None,
        )
    else:
        raise Refused("--story takes a stored story id (a number) or one of its article links.")
    if match is None:
        raise Refused(f"No stored story matches {key!r}. Run --list to see the ids.")
    return match


def check_eligible(story, rules: dict) -> None:
    """Only a story sent to Slack as OFFICIAL can make a carousel. Rumors never can."""
    if story.last_alert_label == classify.RUMOR:
        raise Refused("This story was sent as a rumor. Rumor stories can never make a carousel.")
    if story.last_alert_label != classify.OFFICIAL:
        raise Refused("This story has not been sent to Slack as an official story yet, so it can't make a carousel.")
    if story.claude_label == classify.RUMOR or classify.story_label(story, rules) != classify.OFFICIAL:
        raise Refused("Its current label is RUMOR, so it can't make a carousel.")


def eligible_stories(store: dedupe.Store, rules: dict, now: datetime) -> list:
    return [
        s for s in store.recent_stories(3650, now)
        if s.last_alert_label == classify.OFFICIAL and classify.story_label(s, rules) == classify.OFFICIAL
    ]


# ---- official page ----

def story_anchors(title: str, brand: str | None) -> list[str]:
    """Words an official post must contain to be this story: model names, years and the product line."""
    lowered = title.lower()
    anchors = set(dedupe.model_tokens(title))
    anchors.update(re.findall(r"\b20\d\d\b", title))
    for product in ("photoshop", "lightroom", "camera raw"):
        if product in lowered:
            anchors.add(product)
    if brand and not anchors:
        anchors.add(brand.lower())
    return sorted(a for a in anchors if a not in STOP_ANCHORS)


def image_pages_for(config: dict, brand: str | None, terms: list[str]) -> list[str]:
    """The official help pages listed in config image_pages for this brand and the product lines of the story
    (for example the Photoshop help pages for a Photoshop story). Empty when none are listed."""
    wanted = {t.lower() for t in terms}
    pages = (config.get("image_pages") or {}).get(brand) or {}
    return [url for product, urls in pages.items() if product.lower() in wanted for url in urls]


def locate_official(story, brand: str | None, config: dict, explicit: str | None) -> OfficialPage:
    """The brand's own page for this story. Article sites give links only, never facts."""
    domains = config["official_domains"].get(brand, []) if brand else []
    if not domains:
        raise Refused(f"No official domains are listed for {brand or 'this brand'} in config/carousel.yaml.")
    checked: list[str] = []
    if explicit:
        if not official.host_allowed(explicit, domains):
            raise Refused(f"{explicit} is not on the official domains for {brand}: {', '.join(domains)}.")
        candidates = [explicit]
        checked.append(f"--official-url {explicit}")
    else:
        candidates = []
        for src in story.sources[:4]:
            article = src.get("link") or src["url"]
            try:
                markup = official.fetch_html(article)
            except (requests.RequestException, ValueError) as exc:
                print(f"  could not read {article}: {type(exc).__name__}")
                continue
            _, links = images.parse_page(markup, article)
            candidates += [link for link in dict.fromkeys(links)
                           if official.host_allowed(link, domains) and link not in candidates]
            checked.append(f"links on {article}")
        anchors = story_anchors(story.title, brand)
        index_cfg = config.get("official_indexes", {}).get(brand)
        if index_cfg:
            try:
                posts = official_index.parse_index(
                    official_index.fetch_index(index_cfg["url"]), index_cfg["base"])
                window = int(index_cfg.get("window_days", 14))
                found = official_index.find_posts(posts, anchors, story.first_seen, window)
                if found:
                    candidates += [p["url"] for p in found[:5] if p["url"] not in candidates]
                    checked.append(f"{index_cfg['url']} (titles containing {', '.join(anchors) or 'the brand'})")
                else:
                    # Titles often do not name the product (e.g. an Adobe MAX post). Read the recent
                    # posts that mention the product, and score their text.
                    product_terms = [t for t in ("photoshop", "lightroom", "camera raw", "firefly", "adobe")
                                     if t in story.title.lower()] or [brand.lower()] if brand else []
                    features = official_index.feature_terms(story.title, product_terms)
                    pool = official_index.candidate_pool(posts, story.first_seen, window, product_terms)
                    best = official_index.best_by_body(
                        pool, lambda url: official.page_text(official.fetch_html(url)), product_terms, features)
                    if best:
                        candidates.append(best["url"])
                        checked.append(f"{index_cfg['url']} (body of '{best['title']}' names the product "
                                       f"{best['product_hits']} times and the features {best['feature_hits']} times)")
                    else:
                        checked.append(f"{index_cfg['url']} (no post within {window} days names the product "
                                       f"and the story's features: checked {len(pool)} posts)")
            except (requests.RequestException, ValueError) as exc:
                checked.append(f"{index_cfg['url']} (could not be read: {type(exc).__name__})")
        for page_url in config.get("official_pages", {}).get(brand, []):
            status, body = official_index.helpx_status(page_url)
            if status == "found" and all(a in body.lower() for a in anchors):
                candidates.append(page_url)
            checked.append(f"{page_url} ({'checked' if status == 'found' else 'not found: ' + body})")
    for url in dict.fromkeys(candidates):
        try:
            markup = official.fetch_html(url)
        except (requests.RequestException, ValueError) as exc:
            print(f"  could not read {url}: {type(exc).__name__}")
            continue
        text = official.page_text(markup)
        if len(text) < MIN_OFFICIAL_CHARS:
            continue
        pages = [(url, markup)]
        press = images.press_pages(images.parse_page(markup, url)[1], domains)
        for extra in press[:3]:
            try:
                pages.append((extra, official.fetch_html(extra)))
            except (requests.RequestException, ValueError):
                continue
        terms, others = story_product_terms(story.title)
        fact_text, note = official.product_text(markup, terms, others)
        return OfficialPage(url=url, text=fact_text, markup=markup, pages=pages, terms=terms, note=note)
    raise Refused(
        "No official page for this story was found. Checked: " + "; ".join(checked or ["nothing configured"])
        + ". Pass --official-url with the brand's own announcement page."
    )


# ---- Claude steps (the same free Claude CLI route as the watcher) ----

def draft_with_claude(title: str, url: str, text: str, model: str, names: list[str] | None = None) -> dict:
    reply = classify.ask_claude(carousel_plan.draft_prompt(title, url, text, names), model, timeout=300)
    return carousel_plan.parse_json_reply(reply)


DRAFT_RETRIES = 2


def read_previous_plan(path: Path) -> dict | None:
    """The plan.json of an earlier build of this story, None when there is none or it is not a JSON object."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("slides"), list) and data["slides"] else None


def plan_for_story(plan_path: Path, draft) -> tuple[dict, str]:
    """The plan to build from: stable across rebuilds. draft() makes a fresh Claude draft.

    When the story already has a plan.json, its slide list, order, features and copy are reused and Claude is not asked
    to draft again (edit plan.json to change the copy of a slide). If that plan no longer passes validation, a fresh draft
    is made but it keeps the earlier plan's features in the earlier order, so a fix never drops or reorders a feature.
    Returns (plan data, a note for sources.md; "" when this is a first build)."""
    previous = read_previous_plan(plan_path)
    if previous is None:
        print("Drafting the slides with Claude...")
        return draft(), ""
    count = len(previous["slides"])
    try:
        carousel_plan.load_plan(previous)
    except carousel_plan.PlanError as exc:
        print("Drafting the slides with Claude (the earlier plan.json no longer passes validation)...")
        fresh = carousel_plan.keep_previous_features(draft(), previous)
        return fresh, (f"slide plan: the earlier plan.json was not reused ({exc}); a fresh draft was made and the same "
                       f"{count} features were kept in the same order")
    return previous, (f"slide plan: reused the earlier plan.json ({count} feature slides, same order and features), "
                      "no new draft was made")


def draft_checked(title: str, url: str, text: str, model: str, names: list[str] | None = None) -> dict:
    """A draft that passes validation. A rejected draft goes back to Claude with the exact errors (up to
    DRAFT_RETRIES times); a missing cover.label then falls back to the official product name."""
    data = draft_with_claude(title, url, text, model, names)
    base = carousel_plan.draft_prompt(title, url, text, names)
    error = ""
    for attempt in range(DRAFT_RETRIES + 1):
        try:
            carousel_plan.load_plan(data)
            print("Draft check: passed first time." if attempt == 0
                  else f"Draft check: fixed by Claude after {attempt} retry with the validation errors.")
            return data
        except carousel_plan.PlanError as exc:
            error = str(exc)
        if attempt == DRAFT_RETRIES:
            break
        print(f"Draft check: {error}. Asking Claude to correct it (retry {attempt + 1} of {DRAFT_RETRIES})...")
        try:
            reply = classify.ask_claude(carousel_plan.redraft_prompt(base, data, error), model, timeout=300)
            data = carousel_plan.parse_json_reply(reply)
        except carousel_plan.PlanError as exc:
            error = str(exc)
    if "cover.label" in error:
        fixed = carousel_plan.with_label_fallback(data, names)
        if fixed is not None:
            carousel_plan.load_plan(fixed)  # any other problem is still reported
            print(f"Draft check: cover.label still missing after {DRAFT_RETRIES} retries. "
                  f"Fallback used: the official product name {fixed['cover']['label']!r}.")
            return fixed
    raise carousel_plan.PlanError(error)


def verify_image(path: Path, slot, official_text: str, product: str, model: str, cache=None) -> dict:
    """One Claude check of one candidate image. A failure is an unreadable answer, never a pass.
    With a claude_cache.ReplyCache, the same image (same bytes), slot and official text is never checked twice."""
    if not path.exists():
        return {"unreadable": True, "notes": f"image check could not run: {path.name} is missing"}
    prompt = image_pick.verifier_prompt(path, slot, official_text, product)
    key = claude_cache.key_for(model, prompt, path.read_bytes()) if cache is not None else None
    reply = cache.get(key) if cache is not None else None
    if reply is None:
        try:
            reply = classify.ask_claude_read(prompt, model, path.parent.resolve(), timeout=240)
        except (RuntimeError, OSError, TimeoutError) as exc:
            return {"unreadable": True, "notes": f"image check could not run: {str(exc)[:200]}"}
    verdict = image_pick.parse_verdict(reply)
    if cache is not None and not verdict.get("unreadable"):
        cache.put(key, reply)  # only an answer that was read is remembered
    return verdict


def factcheck_with_claude(plan: dict, text: str, model: str, only: set[str] | None = None,
                          cache=None) -> dict[str, dict]:
    """One fact-check call. `only` limits it to those fact ids (used to re-check a fallback cover).
    With a claude_cache.ReplyCache, the same claims against the same official text are never sent twice."""
    facts = [f for f in carousel_plan.iter_facts(plan) if only is None or f["id"] in only]
    prompt = carousel_plan.factcheck_prompt(facts, text)
    key = claude_cache.key_for(model, prompt) if cache is not None else None
    reply = cache.get(key) if cache is not None else None
    if reply is None:
        reply = classify.ask_claude(prompt, model, timeout=300)
    verdicts = carousel_plan.parse_verdicts(reply, facts)
    if cache is not None:
        cache.put(key, reply)  # stored only after the reply was read
    return verdicts


def settle_cover(plan_data: dict, text: str, verdicts: dict, names: list[str], recheck) -> tuple[dict, dict, list[str]]:
    """Makes sure the draft has a cover headline the official text confirms.

    When the drafted headline fails, tries a safe fallback: the product name exactly as the official page
    writes it, with an event sub line only when the page names the event. recheck(plan, ids) fact-checks
    just those facts and returns verdicts. Returns (plan_data, verdicts, notes) to carry on with. Raises
    PlanError only when the fallback is not possible or is not confirmed either.
    """
    plan = carousel_plan.load_plan(plan_data)
    carousel_plan.verify(plan, text, verdicts)
    if plan["cover"]["headline"]["ok"]:
        return plan_data, verdicts, []
    drafted = plan["cover"]["headline"]["text"].replace("\n", " ")
    fallback = carousel_plan.cover_fallback(text, names)
    if fallback is None:
        raise carousel_plan.PlanError(
            f"the cover headline {drafted!r} was not confirmed by the official text, and the official text "
            "gives no product name to build a safe fallback cover from, so there is no cover")
    replace_product = not plan["product"]["ok"] if plan["product"] else True
    new_data = carousel_plan.with_fallback_cover(plan_data, fallback, replace_product)
    new_plan = carousel_plan.load_plan(new_data)
    ids = {"cover.headline", "cover.subline"} | ({"product"} if replace_product else set())
    merged = {**verdicts, **recheck(new_plan, ids)}
    carousel_plan.verify(new_plan, text, merged)
    if not new_plan["cover"]["headline"]["ok"]:
        raise carousel_plan.PlanError(
            f"the cover headline {drafted!r} was not confirmed by the official text, and the safe fallback "
            f"{fallback['headline']['text']!r} was not confirmed either, so there is no cover")
    notes = [f"cover headline {drafted!r} was not confirmed; the safe fallback cover "
             f"{fallback['headline']['text']!r} was used and confirmed"]
    if new_plan["cover"]["subline"] is None or not new_plan["cover"]["subline"]["ok"]:
        notes.append("the fallback cover has no sub line (no event or date the official text confirms)")
    return new_data, merged, notes


def settle_hook(plan_data: dict, text: str, verdicts: dict, features: list[str], recheck) -> tuple[dict, dict, list[str]]:
    """Makes sure the cover has a hook the official text confirms, when one can be had.

    The first choice is the drafted hook. If the fact check removed it (or it only repeats the cover label), the second
    choice is tried: the draft's "subline_alt", a more literal hook. If that fails too, the most literal hook the page
    allows is built by code (carousel_plan.literal_hook: the page's own words from a feature name up to the first
    clause word). Each choice is fact-checked again with recheck(plan, ids). Returns (plan_data, verdicts, notes).
    With no confirmed hook the cover simply has none (the notes say so)."""
    plan = carousel_plan.load_plan(plan_data)
    carousel_plan.verify(plan, text, verdicts)
    if carousel_plan.hook_shown(plan):
        return plan_data, verdicts, []
    first = plan["cover"]["subline"]["text"] if plan["cover"]["subline"] else "none drafted"
    choices = []
    alt = plan_data["cover"].get("subline_alt")
    if isinstance(alt, dict):
        choices.append(("the draft's second choice", alt))
    literal = carousel_plan.literal_hook(text, features)
    if literal:
        choices.append(("the most literal hook from the official wording", literal))
    for label, choice in choices:
        data = copy.deepcopy(plan_data)
        data["cover"]["subline"] = dict(choice)
        try:
            new_plan = carousel_plan.load_plan(data)
        except carousel_plan.PlanError:
            continue
        merged = {**verdicts, **recheck(new_plan, {"cover.subline"})}
        carousel_plan.verify(new_plan, text, merged)
        if carousel_plan.hook_shown(new_plan):
            return data, merged, [f"cover hook {first!r} was not confirmed; {label} was used and confirmed: "
                                  f"{new_plan['cover']['subline']['text']!r}"]
    return plan_data, verdicts, [f"cover hook {first!r} was not confirmed and no second choice was: "
                                 "the cover has no hook"]


# ---- writing the folder ----

def clean_cell(text: str) -> str:
    return " ".join(str(text).replace("|", "/").split())


def where_label(fact_id: str) -> str:
    return fact_id.replace(".", " ")


def factcheck_markdown(title: str, url: str, report: list[dict], checked_on: str, design_md: str) -> str:
    confirmed = [r for r in report if r["verdict"] in ("CONFIRMED", "NOT A FACT")]
    removed = [r for r in report if r["verdict"] == "NOT CONFIRMED"]
    lines = [
        f"# Fact-check: {title}", "",
        f"Official source: {url}",
        f"Checked on: {checked_on}", "",
        "Every claim on the slides and in the captions is listed below. A claim marked NOT CONFIRMED "
        "was removed from the slides and captions.", "",
        "| # | Where | Claim | Verdict | Matched quote |",
        "|---|---|---|---|---|",
    ]
    for number, row in enumerate(report, 1):
        lines.append(
            f"| {number} | {clean_cell(where_label(row['id']))} | {clean_cell(row['text'])} | "
            f"{row['verdict']} | {clean_cell(row['quote'] or '-')} |"
        )
    lines += ["", f"Confirmed: {len(confirmed)}. Removed (not confirmed): {len(removed)}.", ""]
    if removed:
        lines += ["## Removed", ""]
        lines += [f"- {where_label(r['id'])}: {r['text']}" for r in removed]
        lines.append("")
    lines.append(design_md)
    return "\n".join(lines)


def sources_markdown(title: str, url: str, article_links: list[tuple[str, str]], text_len: int,
                     images_note: list[str], press_images: bool) -> str:
    lines = [
        f"# Sources: {title}", "",
        f"Official source for every fact on the slides and captions: {url}",
        f"Official page text checked: {text_len} characters.", "",
        "News reports the story came from (context only, not used for facts):",
    ]
    lines += [f"- {name}: {link}" for name, link in article_links] or ["- none recorded"]
    lines += ["", f"Official press images may be auto-placed (use_official_press_images): "
                  f"{'yes' if press_images else 'no'}.", "", "Images:"]
    lines += [f"- {note}" for note in images_note] or ["- none"]
    lines.append("")
    return "\n".join(lines)


def captions_text(captions: dict[str, str]) -> str:
    return (
        "DAVID MOLNAR FACEBOOK (first person)\n" + captions["david"] + "\n\n"
        "TPM FACEBOOK AND INSTAGRAM (we)\n" + captions["tpm"] + "\n"
    )


class DesignFailed(LintError):
    """The design check found a FAIL. Files are still written so Kint can see why."""


def assemble(plan_data, *, title: str, official_text: str, verdicts: dict | None, out_dir: Path,
             official_url: str, article_links: list[tuple[str, str]], press_images: bool,
             render: bool, checked_on: str, extra_notes: list[str] | None = None,
             candidates_md: str | None = None, is_sample: bool = False, closing: bool = False,
             clock: timing.Clock | None = None) -> dict:
    """Checks the facts, lints the text, writes the folder, renders the PNGs and runs the design check.
    closing=True adds the call to action slide at the end when there is room (carousel_plan.closing_view).
    clock (a timing.Clock) times the render and the design check and saves every step's time in status.json."""
    timed = clock is not None
    clock = clock or timing.Clock(title, echo=False)
    plan = carousel_plan.load_plan(plan_data)
    report = carousel_plan.verify(plan, official_text, verdicts)
    views = carousel_plan.build_views(plan)
    closing_slide = carousel_plan.closing_view(views, design_check.MAX_SLIDES) if closing else None
    if closing_slide:
        views.append(closing_slide)
    captions = {who: carousel_plan.build_caption(plan, who) for who in ("david", "tpm")}
    extra_notes = list(extra_notes or []) + [
        f"caption {who}: the drafted hook was not kept, so the fallback hook {carousel_plan.fallback_hook(plan, who)!r} "
        "(an opinion, no product fact) opens the caption"
        for who in ("david", "tpm") if carousel_plan.hook_replaced(plan, who)]
    texts = carousel_plan.slide_texts(views) + [(f"caption {who}", text) for who, text in captions.items()]
    problems = lint_texts(texts)
    if problems:
        raise LintError("; ".join(problems))

    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    slots, missing = carousel_render.slot_images(images_dir, views)
    for stale in out_dir.glob("[0-9][0-9].png"):
        stale.unlink()
    pngs = [out_dir / f"{n:02d}.png" for n in range(1, len(views) + 1)]

    (out_dir / "captions.txt").write_text(captions_text(captions), encoding="utf-8")
    (out_dir / "plan.json").write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
    images_note = []
    for number, slot in enumerate(slots, 1):
        if slot["main"]:
            images_note.append(f"{slot['main'].name}: present, slide {number}")
        if slot["old"]:
            images_note.append(f"{slot['old'].name}: present, slide {number}")
    collage = slots[0].get("collage") if slots else None
    if collage and len(collage) >= 2:
        images_note.append("slide 1 hero: a collage of the official feature images " + ", ".join(p.name for p in collage[:3])
                           + " (first one large, uncropped, same border and glow as the slides)")
    images_note += [f"{name}: missing (a feature slide uses the text-led layout with no image box, the cover and "
                    "other slides show only the soft glow; another feature's image is never shown)"
                    for name in missing]
    images_note += extra_notes or []
    (out_dir / "sources.md").write_text(
        sources_markdown(title, official_url, article_links, len(official_text), images_note, press_images),
        encoding="utf-8",
    )
    if candidates_md is not None:
        (out_dir / "candidates.md").write_text(candidates_md, encoding="utf-8")

    overflow: list[str] = []
    measure_log: list | None = None
    if render:
        with clock.step("render slides (one browser for all)"):
            documents = [carousel_render.slide_document(v, s, FONT_DIR if FONT_DIR.exists() else None)
                         for v, s in zip(views, slots)]
            measure_log = []
            overflow = carousel_render.render_pngs(documents, pngs, out_dir / ".work", measure_log=measure_log)
        # No preview.png contact sheet any more: the dashboard and the download zip show every slide, so the extra
        # render only made each build slower. An old preview.png is removed so it never shows outdated slides.
        (out_dir / "preview.png").unlink(missing_ok=True)
        import shutil
        shutil.rmtree(out_dir / ".work", ignore_errors=True)
    with clock.step("design check"):
        findings = design_check.run_design_check(views, captions, measure_log)
    design_md = design_check.markdown(findings)
    removed = [r for r in report if r["verdict"] == "NOT CONFIRMED"]
    confirmed = sum(1 for r in report if r["verdict"] in ("CONFIRMED", "NOT A FACT"))
    placed = sorted(p.name for p in images_dir.iterdir() if p.is_file() and p.name[:2].isdigit())
    build = {
        "slides": len(views), "confirmed": confirmed, "removed_count": len(removed),
        "removed": [r["text"] for r in removed], "missing": missing, "placed": placed,
        "design_summary": design_check.summary_lines(findings)[0],
        "design_fail": sum(f["level"] == "FAIL" for f in findings),
        "design_warn": sum(f["level"] == "WARN" for f in findings),
        "captions_words": {who: len(text.split()) for who, text in captions.items()},
        "official_url": official_url, "title": title,
        # Read by carousel_status.write_build: a draft that passes all three becomes Waiting for David.
        "fact_check_passed": True, "lint_passed": not overflow, "sample": is_sample,
    }
    if closing_slide:
        build["closing"] = True  # downloads names the last slide NN-your-take.png
    if timed:
        build["timings"] = clock.as_dict()  # seconds per step, to compare builds
    (out_dir / "factcheck.md").write_text(
        factcheck_markdown(title, official_url, report, checked_on, design_md), encoding="utf-8")
    if not is_sample:
        activity.log_event("fact_check", "passed" if not removed else "passed, claims removed",
                           f"{title}: {confirmed} claims confirmed against the official page, {len(removed)} removed "
                           f"as not confirmed ({out_dir.name})")
    carousel_status.write_build(out_dir, build)
    carousel_status.write_review_readme(out_dir, title, build)
    if overflow:
        raise LintError("; ".join(lint_overflow(overflow)))
    # The download zip (slides in order, a caption file per account, sources.txt) is made for a finished build only.
    if render and not design_check.has_failures(findings):
        try:
            downloads.write_folder_zip(out_dir)
        except OSError as exc:
            print(f"The download zip was not written ({type(exc).__name__}); run src\\downloads.py --all later.")
    else:
        for stale in out_dir.glob("*.zip"):
            stale.unlink(missing_ok=True)
    result = {
        "folder": out_dir,
        "slides": len(views),
        "confirmed": sum(1 for r in report if r["verdict"] in ("CONFIRMED", "NOT A FACT")),
        "removed": removed,
        "missing": missing,
        "rendered": render,
        "design": findings,
        "captions": captions,
        "placed": placed,
        # why a slide has no image of its own, word for word as written in sources.md (shown in the build output)
        "no_image": [note for note in (extra_notes or []) if "text-led layout" in note],
    }
    if design_check.has_failures(findings):
        raise DesignFailed("; ".join(f"{f['rule']}: {f['message']}" for f in findings if f["level"] == "FAIL"))
    return result


def print_summary(result: dict) -> None:
    print(f"Carousel folder: {result['folder']}")
    print(f"Slides: {result['slides']}" + ("" if result["rendered"] else " (text only, PNGs not rendered)"))
    print(f"Facts kept: {result['confirmed']}. Removed as not confirmed: {len(result['removed'])}.")
    for row in result["removed"]:
        print(f"  removed ({where_label(row['id'])}): {row['text']}")
    if result["missing"]:
        print("Slides with no image of their own (feature slides use the text-led layout, never another feature's image):")
        print("  " + ", ".join(result["missing"]) + f"  (drop them in {result['folder'] / 'images'})")
        for note in result.get("no_image", []):
            print("  " + note)
    for line in design_check.summary_lines(result["design"]):
        print(line)
    print("Lint: passed (no em or en dashes, spaced hyphens, hashtags or overflowing text).")
    for name, text in result["captions"].items():
        print(f"Caption {name}: {len(text.split())} words")


def item_folder(title: str, first_seen: datetime | None) -> Path:
    day = (first_seen or datetime.now(timezone.utc)).astimezone(dashboard.MANILA).strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-") or "story"
    return OUTPUT_ROOT / f"{day}-{slug}"


# ---- commands ----

PAGE_CACHE_DIR = ROOT / "data" / "page-cache"
IMAGE_CACHE_DIR = ROOT / "data" / "image-cache"


def run_story(key: str, official_url: str | None, render: bool) -> dict:
    """One real build, timed step by step (Timing lines in the run log, totals in status.json). Fetched official pages,
    downloaded official images and Claude's answers are reused from data/ for a rebuild, so only what changed is asked
    again. The caches are switched off again when the build ends."""
    config = load_config()
    clock = timing.Clock(f"story {key}")
    official.enable_page_cache(PAGE_CACHE_DIR, float(config.get("page_cache_hours", 6)))
    images.IMAGE_CACHE_DIR = IMAGE_CACHE_DIR
    try:
        result = _run_story(key, official_url, render, config, clock)
    finally:
        official.disable_page_cache()
        images.IMAGE_CACHE_DIR = None
        print(clock.summary())
    return result


def _run_story(key: str, official_url: str | None, render: bool, config: dict, clock: timing.Clock) -> dict:
    if not DATA_PATH.exists():
        raise Refused("No watcher data yet. Run the watcher first.")
    rules = load_rules()
    now = datetime.now(timezone.utc)
    store = dedupe.Store(DATA_PATH)
    story = find_story(store, key, now)
    check_eligible(story, rules)

    print(f"Finding the official page for {story.brand or 'this brand'}...")
    with clock.step("official page"):
        page = locate_official(story, story.brand, config, official_url)
    print(f"Official page: {page.url}")

    if page.note:
        print(f"Facts come from: {page.note}")
    names = carousel_plan.official_names(page.text, page.terms)
    out_dir = item_folder(story.title, story.first_seen)
    cache = claude_cache.for_folder(out_dir.name)
    with clock.step("slide plan (reused or Claude draft)"):
        plan_data, plan_note = plan_for_story(
            out_dir / "plan.json",
            lambda: draft_checked(story.title, page.url, page.text, config["draft_model"], names))
    if plan_note:
        print(plan_note)
    plan = carousel_plan.load_plan(plan_data)
    print("Fact-checking every claim with Claude...")
    with clock.step("fact check"):
        verdicts = factcheck_with_claude(plan, page.text, config["factcheck_model"], cache=cache)
        plan_data, verdicts, cover_notes = settle_cover(
            plan_data, page.text, verdicts, names,
            lambda new_plan, ids: factcheck_with_claude(new_plan, page.text, config["factcheck_model"], ids,
                                                        cache=cache))
    for line in cover_notes:
        print(line)
    hook_features = [h["text"] for h in (s["headline"] for s in carousel_plan.load_plan(plan_data)["slides"]) if h]
    with clock.step("hook check"):
        plan_data, verdicts, hook_notes = settle_hook(
            plan_data, page.text, verdicts,
            [" ".join(carousel_plan.strip_parentheses(f).split()) for f in hook_features],
            lambda new_plan, ids: factcheck_with_claude(new_plan, page.text, config["factcheck_model"], ids,
                                                        cache=cache))
    for line in hook_notes:
        print(line)
    cover_notes += hook_notes
    # The cover label is the event the official page names (for example ADOBE MAX 2026), read by code from the whole page.
    plan_data = carousel_plan.with_event_label(plan_data, official.page_text(page.markup))
    plan = carousel_plan.load_plan(plan_data)  # the plan as it stands after any cover fallback

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)  # Kint drops product images here
    domains = config["official_domains"].get(story.brand, []) if story.brand else []
    carousel_plan.verify(plan, page.text, verdicts)
    views_now = carousel_plan.build_views(plan)
    features = [v["headline"] for v in views_now if v["type"] == "feature"]
    # Official help pages (config image_pages, plus the help pages the post or the beta page links to for a feature)
    # are searched for images and demo videos like the post itself.
    image_pages: list[tuple[str, str]] = list(page.pages)
    page_tags: dict[str, str] = {}
    help_notes: list[str] = []
    if domains:
        print("Looking for official help pages with images of each feature...")
        with clock.step("official help pages"):
            extra, page_tags, help_notes = images.discover_image_pages(
                page.pages, image_pages_for(config, story.brand, page.terms), features, domains, terms=page.terms,
                fallback_images=image_override.known_page_images())
        image_pages += extra
    print("Looking for product images on the official pages...")
    images.clear_candidates(out_dir)  # nothing from an earlier run stays beside this run's files
    with clock.step("official images (downloads side by side)"):
        accepted, rejected = images.gather(image_pages, domains, out_dir, features=features, page_tags=page_tags)
    video_notes: list[str] = list(help_notes)
    if domains:
        print("Looking for official demo videos (their poster frames are real screenshots of the product)...")
        with clock.step("official demo videos and posters (one browser for all trims)"):
            videos, found_notes = official.discover_videos(image_pages, page.terms)
            video_notes += found_notes
            posters, poster_rejected = images.gather_posters(videos, domains, out_dir, features,
                                                             start=len(accepted), trim=border_trim.trim_border,
                                                             page_tags=page_tags)
        accepted += posters
        rejected += poster_rejected
        video_notes += [f"official demo video {v['url']} (found on {v['found_on']}): title {v['title']!r}, "
                        f"poster {v['poster']}" for v in videos]
        video_notes += [f"{p.file}: {p.trimmed}" for p in posters if p.trimmed]
    candidates_md = images.candidates_markdown(accepted, rejected, [url for url, _ in page.pages])
    notes = [f"candidates: {len(accepted)} saved in images/candidates/ (see candidates.md)"]
    notes += video_notes
    if page.note:
        notes.append(f"fact source: {page.note}")
    notes += cover_notes
    if plan_note:
        notes.append(plan_note)
    # A manual official image (assets/official/overrides.json) is used for its slide and the automatic search skips it.
    overridden, override_log = image_override.apply_overrides(
        image_override.for_story(out_dir.name), views_now, out_dir, domains, trim=border_trim.trim_border)
    notes += override_log
    for line in override_log:
        print(line)
    if config["use_official_press_images"]:
        product = plan["product"]["text"] if plan["product"] and plan["product"]["ok"] else story.title
        slots_to_pick = [s for s in image_pick.slots_for(views_now) if s.name not in overridden]
        print(f"Claude Code is checking {len(accepted)} candidate images for {len(slots_to_pick)} slots...")
        with clock.step("image check"):
            _, log = image_pick.pick_for_slots(
                slots_to_pick, accepted, out_dir, page.text, product,
                lambda path, slot, text, name: verify_image(path, slot, text, name, config["image_check_model"],
                                                            cache=cache),
                workers=int(config.get("image_check_workers", 3)),
            )
        notes += log
    else:
        notes.append("auto-placement is off (use_official_press_images: false). Copy the chosen files to images/.")
    if cache.hits:
        notes.append(f"speed: {cache.hits} answers reused from the earlier build of this carousel (same question, same "
                     "official text, same image), so Claude was not asked again")
    article_links = [(src["source"], src.get("link") or src["url"]) for src in story.sources]
    return assemble(
        plan_data, title=story.title, official_text=page.text, verdicts=verdicts, out_dir=out_dir,
        official_url=page.url, article_links=article_links, press_images=config["use_official_press_images"],
        render=render, checked_on=now.astimezone(dashboard.MANILA).strftime("%Y-%m-%d"), extra_notes=notes,
        candidates_md=candidates_md, closing=bool(config.get("closing_slide", True)), clock=clock,
    )


# Reasons that mean the story's facts or official source do not check out (the carousel is then rejected), as opposed
# to a problem on this PC (no Claude sign-in, no browser for rendering), which only means "try again later".
SETTLE_REJECT = (Refused, carousel_plan.PlanError)


def settle_story(key: str, official_url: str | None = None, render: bool = True,
                 build=None, now: datetime | None = None) -> tuple[str, str]:
    """Rebuilds an older story's carousel when its facts and images still check out, otherwise marks it rejected with
    the reason, so the dashboard always says why a sent official story has no finished carousel.

    Returns (outcome, message): "built", "rejected" or "not settled" (a problem on this PC; nothing was changed).
    build(key, official_url, render) defaults to run_story. A reviewed folder (approved or posted) is never rejected here."""
    build = build or run_story
    now = now or datetime.now(timezone.utc)
    folder = None
    title = f"story {key}"
    try:
        if DATA_PATH.exists():
            store = dedupe.Store(DATA_PATH)
            try:
                story = find_story(store, key, now)
            finally:
                store.db.close()
            title = story.title
            folder = item_folder(story.title, story.first_seen)
    except Refused:
        pass
    try:
        result = build(key, official_url, render)
    except SETTLE_REJECT as exc:
        reason = f"Rebuild check: {exc}"
        if folder is not None and folder.exists():
            current = carousel_status.read_status(folder)["status"]
            if current not in ("approved", "posted"):
                carousel_status.set_status(folder, "rejected", reason=reason,
                                           rejected_at=now.isoformat(timespec="seconds"))
        _record_settle(key, now, "failed", None, reason)
        activity.log_event("carousel", "rejected", f"{title}: {reason}", now=now)
        return "rejected", reason
    except Exception as exc:  # no Claude, no browser, no network: nothing is changed, try again later
        reason = f"{type(exc).__name__}: {exc}"
        activity.log_event("carousel", "failed", f"{title}: not settled, try again later ({reason})", now=now)
        return "not settled", reason
    _record_settle(key, now, "ok", str(result["folder"]), "draft ready (settled)")
    activity.log_event("carousel", "built", f"{title}: rebuilt and checked again ({Path(result['folder']).name})",
                       now=now)
    return "built", str(Path(result["folder"]).name)


def _record_settle(key: str, now: datetime, status: str, folder: str | None, message: str) -> None:
    """Notes the settle result in carousel_builds, so the dashboard shows the reason next to the story."""
    if not key.isdigit() or not DATA_PATH.exists():
        return
    try:
        import carousel_auto
        carousel_auto.record(DATA_PATH, int(key), now, status, folder, message)
    except Exception as exc:  # the record is extra; the status file already says it
        print(f"The build record was not saved ({type(exc).__name__}).")


def run_sample(name: str = DEFAULT_SAMPLE, render: bool = True) -> dict:
    """Offline. The fixture's official_text is a stand-in, marked SAMPLE in every output file."""
    fixture = json.loads(SAMPLES[name].read_text(encoding="utf-8"))
    out_dir = SAMPLE_ROOT / f"{fixture['date']}-{fixture['slug']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    return assemble(
        fixture["plan"], title=fixture["title"], official_text=fixture["official_text"], verdicts=None,
        out_dir=out_dir, official_url=fixture["official_url"], article_links=[],
        press_images=False, render=render, checked_on=fixture["date"], extra_notes=[fixture["note"]],
        is_sample=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carousel drafts with a fact-check pass. Posts nothing.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list sent official stories that can make a carousel")
    group.add_argument("--story", help="stored story id, or one of its article links")
    group.add_argument("--sample", nargs="?", const=DEFAULT_SAMPLE, choices=sorted(SAMPLES),
                       help="offline visual check from a saved fixture (default: camera)")
    group.add_argument("--settle", metavar="STORY",
                       help="rebuild an older story if its facts and images still check out, otherwise reject it "
                            "with the reason")
    parser.add_argument("--official-url", help="the brand's own announcement page to use")
    parser.add_argument("--skip-render", action="store_true", help="write the text files without rendering PNGs")
    args = parser.parse_args(argv)
    load_dotenv(ROOT / ".env")
    render = not args.skip_render
    try:
        if args.list:
            if not DATA_PATH.exists():
                print("No watcher data yet.")
                return 0
            stories = eligible_stories(dedupe.Store(DATA_PATH), load_rules(), datetime.now(timezone.utc))
            if not stories:
                print("No sent official stories yet.")
            for story in stories:
                day = (story.first_seen or datetime.now(timezone.utc)).astimezone(dashboard.MANILA)
                print(f"{story.id:>5}  {day:%Y-%m-%d}  {story.brand or 'Unbranded':<12} {story.title}")
            return 0
        if args.settle:
            outcome, message = settle_story(args.settle, args.official_url, render)
            print(f"Story {args.settle}: {outcome}. {message}")
            return 0 if outcome != "not settled" else 1
        if args.sample:
            result = run_sample(args.sample, render)
        else:
            result = run_story(args.story, args.official_url, render)
            activity.log_event("carousel", "built", f"Story {args.story} built by hand: {result['folder'].name}, "
                               f"{result['slides']} slides")
        print_summary(result)
        return 0
    except Refused as exc:
        _log_manual_failure(args, exc)
        print(f"Not made: {exc}")
        return 2
    except carousel_plan.PlanError as exc:
        _log_manual_failure(args, exc)
        print(f"The draft plan needs fixing: {exc}")
        return 1
    except DesignFailed as exc:
        _log_manual_failure(args, exc)
        print(f"Design check failed, see factcheck.md: {exc}")
        return 1
    except LintError as exc:
        _log_manual_failure(args, exc)
        print(f"Lint failed, nothing is ready: {exc}")
        return 1
    except carousel_render.RenderError as exc:
        _log_manual_failure(args, exc)
        print(str(exc))
        return 3


def _log_manual_failure(args, exc: Exception) -> None:
    if getattr(args, "story", None):
        activity.log_event("carousel", "failed", f"Story {args.story} built by hand: {exc}")


if __name__ == "__main__":
    sys.exit(main())
