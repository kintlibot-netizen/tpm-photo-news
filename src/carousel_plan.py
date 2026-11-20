"""The carousel plan: validation, facts, fact-check verdicts, and the text that is left after checking.

Every fact is a {"text", "quote"} pair. The quote is copied from the official page. A fact is kept
only when its quote really appears in the official text (checked here, in code) and the fact-check
call did not reject it. Anything else is removed from the slides and reported.
"""
from __future__ import annotations

import copy
import json
import re

from carousel_text import clean_output, hyphenated_words, match_key, quote_found

FEATURE_MIN, FEATURE_MAX = 3, 5
NAME_FACTS = ("product", "cover.headline")  # the product name must be written as the official page writes it
SPEC_MAX, ROW_MAX, PRICE_MAX = 3, 6, 2
CAPTION_FACTS_MIN, CAPTION_FACTS_MAX = 2, 3
HEADLINE_MAX = 45  # characters, not counting line breaks
BODY_MAX = 140  # characters, one sentence
TEMPLATES = ("left_body", "stat_specs", "stat_hero")
ICONS = ("sensor", "burst", "focus", "stabilize", "video", "battery", "box", "star")
CTA_TEXT = "SHARE YOUR TAKE IN THE COMMENTS."
SWIPE_TEXT = "SWIPE TO SEE WHAT'S NEW →"
COVER_FEATURES_MAX = 4  # feature names listed under the cover headline
VERDICTS = ("CONFIRMED", "NOT CONFIRMED", "NOT A FACT")
OPINION_ENDINGS = (".closing", ".question", ".hook")  # parts that may contain no fact at all (a caption hook may be an opinion)
CAPTION_WORDS_MAX = 50  # a caption is UNDER this many words
CAPTION_HOOK_WORDS_MAX = 9  # the opening hook sentence is under 10 words
HOOK_CHARS_MAX = 52  # the cover hook: two lines of bold caps


class PlanError(ValueError):
    """The draft plan is missing something, has the wrong shape, or breaks a copy rule."""


def _label(value, path: str) -> str:
    if isinstance(value, dict):  # Claude sometimes writes a label as {"text": ..., "quote": ...}
        value = value.get("text")
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{path}: needs a short label")
    if len(value.strip()) > 60:
        raise PlanError(f"{path}: label is longer than 60 characters")
    return clean_output(value.strip())


def _fact(value, path: str) -> dict | None:
    """One checked fact. None when the plan leaves it out."""
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("text"), str) or not value["text"].strip():
        raise PlanError(f"{path}: needs a text value")
    quote = value.get("quote", "")
    if not isinstance(quote, str):
        raise PlanError(f"{path}: quote must be text")
    return {
        "id": path,
        "text": clean_output(value["text"].strip()),
        "quote": quote.strip(),
        "verdict": None,
        "ok": False,
        "matched": "",
    }


def _list(value, path: str, limit: int) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise PlanError(f"{path}: needs a list of at most {limit} items")
    return value


def strip_parentheses(text: str) -> str:
    """A headline without brackets: 'REMOVE TOOL (RELATED ELEMENTS)' becomes 'REMOVE TOOL'. Line breaks stay."""
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", line).replace("(", "").replace(")", "")
        line = " ".join(line.replace("[", "").replace("]", "").split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def _headline_check(fact: dict | None, path: str) -> None:
    if fact:
        fact["text"] = strip_parentheses(fact["text"])
        if not fact["text"]:
            raise PlanError(f"{path}: headline is empty once the brackets are removed")
    if fact and len(fact["text"].replace("\n", " ")) > HEADLINE_MAX:
        raise PlanError(f"{path}: headline is longer than {HEADLINE_MAX} characters. Shorten it.")


def _body_check(fact: dict | None, product: str | None, path: str, hyphens: bool = True) -> None:
    """Copy rules for one body sentence. hyphens=False skips the hyphenated word rule: it is for slide bodies, where a
    hyphen breaks a word across two lines, and not for the price quick take (an official term such as in-body)."""
    if fact is None:
        return
    text = fact["text"]
    if len(text) > BODY_MAX:
        raise PlanError(f"{path}: body is longer than {BODY_MAX} characters. Use one short sentence.")
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(sentences) > 1:
        raise PlanError(f"{path}: body must be one sentence")
    if product and product.lower() in text.lower():
        raise PlanError(f"{path}: do not repeat the product name in the body")
    hyphenated = hyphenated_words(text) if hyphens else []
    if hyphenated:
        raise PlanError(f"{path}: the body has a hyphenated word ({', '.join(hyphenated)}). Rewrite it without a "
                        "hyphen, for example 'without prompting again' instead of 'without re-prompting'.")


def _spec(value, path: str) -> dict:
    if not isinstance(value, dict):
        raise PlanError(f"{path} must be an object")
    icon = value.get("icon") or ICONS[0]
    if icon not in ICONS:
        raise PlanError(f"{path}.icon must be one of: {', '.join(ICONS)}")
    return {"value": _fact(value.get("value"), f"{path}.value"),
            "caption": _fact(value.get("caption"), f"{path}.caption"), "icon": icon}


def load_plan(data) -> dict:
    """Checks the draft's shape and copy rules, and turns it into a plan with every fact tagged."""
    if not isinstance(data, dict):
        raise PlanError("the plan must be a JSON object")
    cover = data.get("cover")
    if not isinstance(cover, dict):
        raise PlanError("cover is missing")
    product = _fact(data.get("product"), "product")
    product_text = product["text"] if product else None
    plan = {
        "product": product,
        "cover": {
            "label": _label(cover.get("label"), "cover.label"),
            "headline": _fact(cover.get("headline"), "cover.headline"),
            "subline": _fact(cover.get("subline"), "cover.subline"),
        },
        "slides": [],
        "comparison": None,
        "price": None,
        "captions": {},
    }
    if plan["cover"]["headline"] is None:
        raise PlanError("cover.headline is required")
    _headline_check(plan["cover"]["headline"], "cover.headline")

    slides = data.get("slides")
    if not isinstance(slides, list) or not FEATURE_MIN <= len(slides) <= FEATURE_MAX:
        raise PlanError(f"the plan needs {FEATURE_MIN} to {FEATURE_MAX} feature slides")
    for index, slide in enumerate(slides, 1):
        if not isinstance(slide, dict):
            raise PlanError(f"slide{index} must be an object")
        path = f"slide{index}"
        template = slide.get("template")
        if template is not None and template not in TEMPLATES:
            raise PlanError(f"{path}.template must be one of: {', '.join(TEMPLATES)}")
        item = {
            "template": template,
            "label": _label(slide.get("label"), f"{path}.label"),
            "headline": _fact(slide.get("headline"), f"{path}.headline"),
            "accent": _fact(slide.get("accent"), f"{path}.accent"),
            "body": _fact(slide.get("body"), f"{path}.body"),
            "specs": [_spec(s, f"{path}.spec{j}")
                      for j, s in enumerate(_list(slide.get("specs"), f"{path}.specs", SPEC_MAX), 1)],
        }
        if item["headline"] is None:
            raise PlanError(f"{path}.headline is required")
        _headline_check(item["headline"], f"{path}.headline")
        _body_check(item["body"], product_text, f"{path}.body")
        plan["slides"].append(item)

    comparison = data.get("comparison")
    if comparison:
        if not isinstance(comparison, dict):
            raise PlanError("comparison must be an object or null")
        rows = []
        for j, row in enumerate(_list(comparison.get("rows"), "comparison.rows", ROW_MAX), 1):
            if not isinstance(row, dict):
                raise PlanError(f"comparison.row{j} must be an object")
            rows.append({
                "name": _label(row.get("name"), f"comparison.row{j}.name"),
                "new": _fact(row.get("new"), f"comparison.row{j}.new"),
                "old": _fact(row.get("old"), f"comparison.row{j}.old"),
            })
        plan["comparison"] = {
            "label": _label(comparison.get("label"), "comparison.label"),
            "title": _fact(comparison.get("title"), "comparison.title"),
            "rows": rows,
        }

    price = data.get("price")
    if price:
        if not isinstance(price, dict):
            raise PlanError("price must be an object or null")
        prices = []
        for j, entry in enumerate(_list(price.get("prices"), "price.prices", PRICE_MAX), 1):
            if not isinstance(entry, dict):
                raise PlanError(f"price.{j} must be an object")
            prices.append({
                "value": _fact(entry.get("value"), f"price.{j}.value"),
                "caption": _fact(entry.get("caption"), f"price.{j}.caption"),
            })
        quick = price.get("quick_take")
        quick_take = None
        if quick:
            if not isinstance(quick, dict):
                raise PlanError("price.quick_take must be an object or null")
            quick_take = {
                "sentence": _fact(quick.get("sentence"), "price.quick_take.sentence"),
                "question": _fact(quick.get("question"), "price.question"),
            }
            if quick_take["sentence"] is None or quick_take["question"] is None:
                raise PlanError("price.quick_take needs a sentence and a question")
            _body_check(quick_take["sentence"], None, "price.quick_take.sentence", hyphens=False)
        plan["price"] = {
            "label": _label(price.get("label"), "price.label"),
            "prices": prices,
            "availability": _fact(price.get("availability"), "price.availability"),
            "quick_take": quick_take,
        }

    captions = data.get("captions")
    if not isinstance(captions, dict):
        raise PlanError("captions are missing")
    for who in ("david", "tpm"):
        block = captions.get(who)
        if not isinstance(block, dict):
            raise PlanError(f"captions.{who} is missing")
        facts = [_fact(f, f"captions.{who}.fact{j}")
                 for j, f in enumerate(_list(block.get("facts"), f"captions.{who}.facts", CAPTION_FACTS_MAX), 1)]
        if not CAPTION_FACTS_MIN <= len(facts) <= CAPTION_FACTS_MAX:
            raise PlanError(f"captions.{who} needs {CAPTION_FACTS_MIN} to {CAPTION_FACTS_MAX} concrete facts")
        plan["captions"][who] = {
            "hook": _fact(block.get("hook"), f"captions.{who}.hook"),
            "facts": facts,
            "closing": _fact(block.get("closing"), f"captions.{who}.closing"),
        }
        if plan["captions"][who]["hook"] is None or plan["captions"][who]["closing"] is None:
            raise PlanError(f"captions.{who} needs a hook and a closing line")
    return plan


def iter_facts(plan: dict):
    """Every fact in the plan, as the same dict objects, so verdicts can be written onto them."""
    found = [plan["product"], plan["cover"]["headline"], plan["cover"]["subline"]]
    for slide in plan["slides"]:
        found += [slide["headline"], slide["accent"], slide["body"]]
        for spec in slide["specs"]:
            found += [spec["value"], spec["caption"]]
    if plan["comparison"]:
        found.append(plan["comparison"]["title"])
        for row in plan["comparison"]["rows"]:
            found += [row["new"], row["old"]]
    if plan["price"]:
        for entry in plan["price"]["prices"]:
            found += [entry["value"], entry["caption"]]
        found.append(plan["price"]["availability"])
        if plan["price"]["quick_take"]:
            found += [plan["price"]["quick_take"]["sentence"], plan["price"]["quick_take"]["question"]]
    for block in plan["captions"].values():
        found += [block["hook"], *block["facts"], block["closing"]]
    return [f for f in found if f is not None]


def name_in_text(name: str, official_text: str) -> bool:
    """True when the name (line breaks ignored, case ignored) appears in the official text."""
    return match_key(name.replace("\n", " ")) in match_key(official_text)


def official_names(text: str, terms: list[str]) -> list[str]:
    """How the official text writes the product, most used form first: "Photoshop", or "Photoshop 27" when
    the page really uses a version. A form used less than half as often as the top one (an old version
    mentioned once, say) is left out. Empty when the text does not name the product."""
    forms: dict[str, list] = {}
    for term in terms:
        pattern = rf"\b{re.escape(term)}\b(?:\s+(?:20\d\d|\d{{2}}(?:\.\d+)?|\d\.\d+)\b)?"
        for match in re.finditer(pattern, text, re.I):
            name = " ".join(match.group(0).split())
            forms.setdefault(name.lower(), [name, 0])[1] += 1
    ranked = sorted(forms.values(), key=lambda v: (-v[1], len(v[0])))
    return [name for name, count in ranked if ranked and count * 2 >= ranked[0][1]]


EVENT_PATTERN = re.compile(r"\b(?:Adobe MAX|CES|CP\+|NAB Show|IBC|Photokina|PhotoPlus Expo) 20\d\d\b")


def _snippet(text: str, start: int, length: int) -> str:
    """Words of the official text from `start`, about `length` characters, cut at word edges. Copied as is,
    so it is a real quote."""
    if start > 0 and not text[start - 1].isspace():
        space = text.find(" ", start)
        start = space + 1 if space != -1 else start
    end = start + length
    if end < len(text):
        cut = text.rfind(" ", start, end)
        end = cut if cut > start else end
    return text[start:end].strip()


def cover_fallback(text: str, names: list[str]) -> dict | None:
    """A safe cover from the official text alone: the product name as the page writes it, and an event
    sub line (e.g. "NEW AT ADOBE MAX 2026") only when the page names the event. None without a name.
    Both are ordinary facts with real quotes: they still go through the fact-check."""
    for name in names:
        found = re.search(rf"\b{re.escape(name)}\b", text, re.I)
        if not found:
            continue
        fallback = {"headline": {"text": name.upper(), "quote": _snippet(text, found.start(), 90)}, "subline": None}
        event = EVENT_PATTERN.search(text)
        if event:
            fallback["subline"] = {"text": f"NEW AT {event.group(0).upper()}",
                                   "quote": _snippet(text, max(0, event.start() - 40), 40 + len(event.group(0)) + 10)}
        return fallback
    return None


HOOK_CUT = re.compile(r"[.!?:;,\n]| that | which | using | while | with ", re.I)


def literal_hook(text: str, features: list[str]) -> dict | None:
    """The most literal cover hook the official text allows: the words of the page that open with a feature name, up
    to the first clause word ("Relight creatively adds new light sources", cut before "that dynamically..."). The words
    are copied as the page writes them, so the quote is real. Used when the drafted hook and its second choice were
    not confirmed. None when no feature name opens a clause of at least four words."""
    for feature in features:
        name = " ".join(feature.split())
        for found in re.finditer(rf"\b{re.escape(name)}\b", text, re.I):
            tail = text[found.start():found.start() + 160]
            cut = HOOK_CUT.search(tail, len(name))
            words = (tail[:cut.start()] if cut else tail).split()
            while words and len(" ".join(words)) > HOOK_CHARS_MAX:
                words.pop()
            snippet = " ".join(words)
            if len(words) >= 4 and snippet in " ".join(text.split()):
                return {"text": snippet.upper(), "quote": snippet}
    return None


def hook_shown(plan: dict) -> bool:
    """True when the cover will show a confirmed hook (not one that only repeats the label)."""
    hook = _kept(plan["cover"]["subline"])
    if not hook:
        return False
    label = _words(plan["cover"]["label"])
    return not (label and set(label) <= set(_words(hook)))


def event_label(text: str) -> str | None:
    """The event the official page names ("ADOBE MAX 2026"), in capitals, for the cover label. None when it names none."""
    found = EVENT_PATTERN.search(text or "")
    return found.group(0).upper() if found else None


def with_event_label(plan_data: dict, page_text: str) -> dict:
    """A copy of the plan whose cover label is the event the official page names, when it names one. The label
    is not a claim from the draft: it is read from the page by code."""
    label = event_label(page_text)
    if not label:
        return plan_data
    data = copy.deepcopy(plan_data)
    data["cover"]["label"] = label
    return data


def with_fallback_cover(plan_data: dict, fallback: dict, replace_product: bool) -> dict:
    """A copy of the draft plan with the fallback cover headline and sub line (and the product name, when
    the draft's own was not confirmed)."""
    data = copy.deepcopy(plan_data)
    data["cover"]["headline"] = dict(fallback["headline"])
    # The drafted hook stays when there is one (it is fact-checked again); the event line is only a stand-in.
    if not data["cover"].get("subline"):
        data["cover"]["subline"] = dict(fallback["subline"]) if fallback["subline"] else None
    if replace_product:
        data["product"] = dict(fallback["headline"])
    return data


def _is_opinion(fact_id: str) -> bool:
    return fact_id.endswith(OPINION_ENDINGS)


# A caption hook that only gives an opinion or a reaction ("My favorite Photoshop update is all about light.", "We think
# Relight is the one to try first.") states no product fact, so there is nothing for the fact check to reject. The fact
# check model sometimes answers NOT CONFIRMED for it anyway; this code path keeps it, because it is judged by its words:
# it must open as an opinion, and every other word in it must be an opinion or filler word or a word the official text uses.
OPINION_OPENER = re.compile(
    r"^(?:my\b|our\b|i(?:['’](?:m|ve|d|ll))?\s+(?:love|like|think|believe|am|was|would|can['’]?t)\b"
    r"|we(?:['’](?:re|ve|d|ll))?\s+(?:think|like|love|believe|would|recommend|expect|say|pick|are|have)\b)", re.I)
OPINION_WORDS = frozenset(
    "i i'm i've i'd i'll my me we we're we've we'd our us you your is are was be all about the a an to of it its this that "
    "one ones think thought like love loved favourite favorite favourites favorites pick picks try first best top great "
    "really so cant can't wait and for in on with will would can how what which update updates release part pick "
    "worth excited stand out standout most".split())


def opinion_hook(text: str, official_text: str) -> bool:
    """True when a hook is an opinion or a reaction and states no product fact the official text could contradict."""
    if not OPINION_OPENER.match((text or "").strip()) or re.search(r"\d", text or ""):
        return False
    known = {w.rstrip("s") for w in _words(official_text)}
    return all(w in OPINION_WORDS or w.rstrip("s") in known for w in re.findall(r"[a-z0-9'’]+", text.lower()))


def hook_replaced(plan: dict, who: str) -> bool:
    """True when this caption's drafted hook was not kept (so the caption uses a fallback hook)."""
    return _kept(plan["captions"][who]["hook"]) is None


def fallback_hook(plan: dict, who: str) -> str:
    """A hook in the right voice that states no product fact, only the name of the first feature slide as the official
    page writes it. David's opens with My, TPM's says we."""
    names = [" ".join(n.split()) for n in (_kept(s["headline"]) for s in plan["slides"]) if n]
    feature = names[0].title() if names else ""
    if who == "david":
        return f"My pick from this update is {feature}." if feature else "I have a favorite in this update."
    return f"We think {feature} is the one to try first." if feature else "We have a favorite in this update."


def verify(plan: dict, official_text: str, model_verdicts: dict | None = None) -> list[dict]:
    """Decides every fact and writes the decision onto it. Returns a report, one line per fact.

    model_verdicts comes from the fact-check call, keyed by fact id. With None (sample mode), only
    the quote check decides. A fact is kept only when a quote really appears in the official text.
    Opinion parts (hooks, closings, the quick-take question) may have no quote and no fact.
    """
    report = []
    for fact in iter_facts(plan):
        model = (model_verdicts or {}).get(fact["id"])
        verdict = model["verdict"] if model else None
        candidates = [q for q in (model and model.get("quote"), fact["quote"]) if q]
        matched = next((q for q in candidates if quote_found(q, official_text)), "")
        if fact["id"].endswith(".hook") and verdict == "NOT A FACT":
            # A hook that is an opinion or a reaction states no product fact, so there is nothing to confirm: it stays
            # (a hook that does state a fact comes back CONFIRMED or NOT CONFIRMED and is judged on that fact).
            ok, final = True, "NOT A FACT"
        elif fact["id"].endswith(".hook") and verdict == "NOT CONFIRMED" and opinion_hook(fact["text"], official_text):
            # The fact check removed an opinion hook as "not confirmed". An opinion is not a claim: it stays, and only the
            # product facts inside it are judged (it has none, every word is opinion or comes from the official text).
            ok, final = True, "NOT A FACT"
        elif _is_opinion(fact["id"]) and verdict in (None, "NOT A FACT") and not matched and not fact["quote"]:
            ok, final = True, "NOT A FACT"
        elif verdict == "NOT A FACT" and not _is_opinion(fact["id"]):
            ok, final = False, "NOT CONFIRMED"
        else:
            ok = matched != "" and verdict in (None, "CONFIRMED")
            final = "CONFIRMED" if ok else "NOT CONFIRMED"
        if ok and fact["id"] in NAME_FACTS and not name_in_text(fact["text"], official_text):
            # The product name must be written that way on the official page: no "2027" the page doesn't use.
            ok, final = False, "NOT CONFIRMED"
        fact["ok"], fact["verdict"], fact["matched"] = ok, final, matched
        report.append({"id": fact["id"], "text": fact["text"], "verdict": final, "quote": matched})
    return report


def _kept(fact: dict | None) -> str | None:
    return fact["text"] if fact and fact["ok"] else None


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def resolve_template(slide: dict, specs: list[dict]) -> str:
    """The reference template for a feature slide. Falls back when the plan asks for specs it doesn't have."""
    wanted = slide["template"] or ("stat_specs" if specs else "left_body" if slide["body"] else "stat_hero")
    if wanted == "stat_specs" and not specs:
        wanted = "stat_hero"
    return wanted


def build_views(plan: dict) -> list[dict]:
    """The slides that remain, in reference order. Unconfirmed facts are simply missing from the result."""
    cover_headline = _kept(plan["cover"]["headline"])
    if cover_headline is None:
        raise PlanError("the cover headline was not confirmed by the official text, so there is no cover")
    product = _kept(plan["product"])
    label = plan["cover"]["label"]
    subline = _kept(plan["cover"]["subline"])
    if subline and _words(label) and set(_words(label)) <= set(_words(subline)):
        subline = None  # "NEW AT ADOBE MAX 2026" under the label "ADOBE MAX 2026" says the same thing twice
    names = [h for h in (_kept(s["headline"]) for s in plan["slides"]) if h][:COVER_FEATURES_MAX]
    feature_names = [" ".join(n.split()) for n in names]
    # The cover shows the confirmed hook (the plan's subline) under the headline, then the feature names (the
    # confirmed feature headlines) as at most two light-blue lines. An unconfirmed hook is simply not shown.
    cover = {
        "type": "cover",
        "label": label,
        "headline": cover_headline,
        "subline": subline,
        "features": feature_names,
        "product": product,
        "footer": SWIPE_TEXT,
    }
    features = []
    for slide in plan["slides"]:
        headline = _kept(slide["headline"])
        if headline is None:
            continue  # a slide with no confirmed headline is dropped whole
        specs = []
        for spec in slide["specs"]:
            value, caption = _kept(spec["value"]), _kept(spec["caption"])
            if value and caption:
                specs.append({"value": value, "caption": caption, "icon": spec["icon"]})
        view = {
            "type": "feature",
            "template": resolve_template(slide, specs),
            "label": slide["label"],
            "headline": headline,
            "accent": _kept(slide["accent"]),
            "body": _kept(slide["body"]),
            "specs": specs,
            "product": product,
        }
        features.append(view)
    views = [cover] + features[:1]
    if plan["comparison"]:
        comparison = _comparison_view(plan["comparison"], product)
        if comparison:
            views.append(comparison)
    views += features[1:]
    if plan["price"]:
        price = _price_view(plan["price"], product)
        if price:
            views.append(price)
    return views


CLOSING_LABEL = "YOUR TAKE"
CLOSING_CTA = "SAVE THIS POST. SHARE YOUR TAKE."
BRAND_LINE = "THE PHOTO MENTORSHIP"


def closing_view(views: list[dict], max_slides: int) -> dict | None:
    """The last slide: a clear call to action. It states no product fact at all (only the question, the confirmed
    feature names already on the slides as a recap, the save and comment prompt and the TPM name), so nothing on it can
    be wrong. Left out when the carousel already ends on the price slide (that slide has its own call to action), when
    there is no confirmed feature to recap, or when one more slide would go over the slide limit."""
    if len(views) >= max_slides or any(v["type"] == "price" for v in views):
        return None
    features = [" ".join(v["headline"].split()) for v in views if v["type"] == "feature"]
    if not features:
        return None
    question = "WHICH ONE WOULD YOU TRY FIRST?" if len(features) >= 2 else "WOULD YOU USE THIS?"
    return {
        "type": "closing",
        "label": CLOSING_LABEL,
        "headline": question,
        "features": features[:COVER_FEATURES_MAX],
        "cta": CLOSING_CTA,
        "footer": BRAND_LINE,
        "product": None,
    }


def _comparison_view(comparison: dict, product: str | None) -> dict | None:
    title = _kept(comparison["title"])
    rows = []
    for row in comparison["rows"]:
        new, old = _kept(row["new"]), _kept(row["old"])
        if new or old:
            rows.append({"name": row["name"], "new": new, "old": old})
    if title is None or not rows:
        return None
    return {
        "type": "comparison",
        "label": comparison["label"],
        "title": title,
        "rows": rows,
        "product": product,
    }


def _price_view(price: dict, product: str | None) -> dict | None:
    entries = []
    for entry in price["prices"]:
        value = _kept(entry["value"])
        if value:
            entries.append({"value": value, "caption": _kept(entry["caption"]) or ""})
    if not entries:
        return None
    quick = price["quick_take"]
    quick_view = None
    if quick and _kept(quick["sentence"]) and _kept(quick["question"]):
        quick_view = {"sentence": _kept(quick["sentence"]), "question": _kept(quick["question"])}
    return {
        "type": "price",
        "label": price["label"],
        "prices": entries,
        "availability": _kept(price["availability"]),
        "quick_take": quick_view,
        "cta": CTA_TEXT,
        "product": product,
    }


def build_caption(plan: dict, who: str) -> str:
    """Confirmed hook (a specific line about the most striking feature), confirmed details, then the question.
    Nothing unconfirmed, and no generic opener."""
    block = plan["captions"][who]
    hook = _kept(block["hook"]) or fallback_hook(plan, who)  # a caption never ships without a hook
    parts = [hook] + [_kept(f) for f in block["facts"]] + [_kept(block["closing"])]
    return us_spelling(" ".join(part for part in parts if part))


# The captions are US English, like the official Adobe and camera brand copy ("color"). Opinion words a draft may write
# in British spelling are changed here. Product facts keep the official page's own words, so only these words change.
US_SPELLING = {"favourite": "favorite", "favourites": "favorites", "colour": "color", "colours": "colors"}


def us_spelling(text: str) -> str:
    """The caption with the British spellings in US_SPELLING changed to US spelling, keeping a capital first letter."""
    def swap(match: re.Match) -> str:
        word = match.group(0)
        us = US_SPELLING[word.lower()]
        return us[0].upper() + us[1:] if word[0].isupper() else us
    return re.sub(r"\b(" + "|".join(US_SPELLING) + r")\b", swap, text, flags=re.I)


FIRST_PERSON_OPENER = re.compile(r"^(?:i|i['’](?:m|ve|d|ll)|my|me)\b", re.I)
WE_VOICE = re.compile(r"\b(?:we|we['’](?:re|ve|ll|d)|our|us)\b", re.I)


def caption_voice_problems(captions: dict[str, str]) -> list[str]:
    """David's caption must open in the first person (I, my); TPM's must say "we" (or our, us) somewhere."""
    problems = []
    david, tpm = captions.get("david"), captions.get("tpm")
    if david is not None and not FIRST_PERSON_OPENER.match(david.strip()):
        problems.append("David's caption does not open in the first person (I or my)")
    if tpm is not None and not WE_VOICE.search(tpm):
        problems.append("TPM's caption never says we")
    if tpm is not None and re.search(r"\bwe\s+can\b", tpm, re.I):
        problems.append("TPM's caption says 'we can': TPM is not the one editing, use we for TPM's view or advice")
    if david is not None and len(re.findall(r"(?:^|(?<=[.!?]\s))I can\b", david)) > 1:
        problems.append("David's caption starts more than one sentence with 'I can'")
    return problems


def slide_texts(views: list[dict]) -> list[tuple[str, str]]:
    """Every piece of text that will appear on a slide, for the lint."""
    found: list[tuple[str, str]] = []
    for number, view in enumerate(views, 1):
        where = f"slide {number:02d}"
        for key in ("label", "headline", "subline", "title", "accent", "body", "availability", "product", "footer", "cta"):
            value = view.get(key)
            if isinstance(value, str) and value:
                found.append((f"{where} {key}", value))
        for name in view.get("features", []):
            found.append((f"{where} feature name", name))
        for spec in view.get("specs", []):
            found += [(f"{where} spec value", spec["value"]), (f"{where} spec caption", spec["caption"])]
        for row in view.get("rows", []):
            found.append((f"{where} row", row["name"]))
            found += [(f"{where} row value", v) for v in (row["new"], row["old"]) if v]
        for entry in view.get("prices", []):
            found += [(f"{where} price", entry["value"]), (f"{where} price caption", entry["caption"])]
        if view.get("quick_take"):
            found += [(f"{where} quick take", view["quick_take"]["sentence"]),
                      (f"{where} question", view["quick_take"]["question"])]
    return found


# ---- prompts and replies ----

DRAFT_PROMPT = """You write carousel slide copy for a photography news account, in the style of a
short, punchy news carousel. Use only facts stated in the official text.

Names and numbers: use ONLY names, numbers and feature names that appear in the official text. The story
title is context only: it may use another name, version or year than the official page. Never copy a name,
version or number from the story title unless the official text contains it too.
__NAMES__

Every fact is a pair: "text" (the words for the slide) and "quote" (the exact sentence or phrase from the
official text that supports it, copied word for word). A fact with no supporting quote must be left out.

Copy rules:
- Product name: write it exactly as the official text writes it. Call it "Photoshop 2027" only if the official text says "Photoshop 2027"; otherwise use the product name the text uses. Feature names must be the official ones (for example "Relight", "Generative Restyle"), not your own words.
- Feature slide headline = the official FEATURE NAME ONLY, in UPPERCASE, as the official text writes it: "RELIGHT", "GENERATIVE RESTYLE", "QUICK COMPARE", "5-AXIS IN-BODY STABILIZATION". Max 45 characters, at most two lines (use \\n for a break). No sentence, no verb, no benefit, and no parentheses or brackets in a headline (write "REMOVE TOOL", never "REMOVE TOOL (RELATED ELEMENTS)").
- Accent = the benefit in a few words, shown as a cyan line under the headline (a fact with a quote), ONE line, max 34 characters, UPPERCASE, e.g. "ADD NEW LIGHT SOURCES" or "NOW CATCHES SHADOWS AND REFLECTIONS". Use only words the quote supports: do not add "after the shot", "instantly" or any detail the official text does not state. Give EVERY slide an accent.
- Body: one short sentence, max 140 characters, about 55 to 80 characters so it sets in two balanced lines (never a last line of one word). Do not repeat the product name in the body. NEVER use a hyphenated word in the body: a hyphen breaks a word across two lines. Write "without prompting again", not "without re-prompting"; "refine it", not "fine-tune it"; "non destructive" is not allowed either, so rephrase. Example bodies: "Type a description in Prompt to edit, then refine it without prompting again." and "Compare before and after without hiding layers one by one." Use only facts the quote supports.
- Cover: headline = the product name exactly as the official text writes it (add a version or year only if the official text does). Label = a plain string, never a {"text", "quote"} pair and never left out: the event name when the official text names one (for example "ADOBE MAX 2026"), otherwise "NEW IN <PRODUCT>". Subline = the cover HOOK, a scroll stopping line shown under the headline in bold white (a fact with a quote copied from the official text): UPPERCASE, max 52 characters (two lines), built on the OFFICIAL WORDING of the most striking feature, kept close to it. Drop words if you must, but never add or reword a claim: e.g. "NEW LIGHT SOURCES THAT BLEND NATURALLY INTO THE SCENE" supported by "new light sources that dynamically and naturally blend into the scene". Do not write "to any scene", "instantly", "after the shot" or any detail the quote does not give. No dashes, no parentheses. Also give "subline_alt": a second, even more literal hook (the first words of the same official sentence, max 52 characters, with its own quote), e.g. "RELIGHT CREATIVELY ADDS NEW LIGHT SOURCES"; it is used only if the first hook is not confirmed. The code adds the feature names under the hook (at most two lines).
- Labels (pill text) describe the slide, e.g. "NEW IN PHOTOSHOP". Do not rank ("THE BIGGEST UPGRADE") unless the official text itself says it is the biggest.
- Templates: "left_body" (headline and body at the left, image at the right), "stat_specs" (big stat headline and up to 3 spec columns, each with value, caption and an icon from: sensor, burst, focus, stabilize, video, battery, box, star), "stat_hero" (big stat headline and an image, one short line at the bottom). Use stat_specs only if the official text gives specs.
- Price and availability only if the official text gives them. Quick take: one fact sentence (with quote) plus a bold question to the audience (the question has no quote: "").
- Comparison only if the official text names the earlier model and gives values for both.
- Never use em dashes, en dashes, spaced hyphens used as dashes, or hashtags.
- 3 to 5 feature slides. No closing slide.
__FEATURES__
- Captions, in this order: (1) "hook": a short sentence that makes people stop scrolling, UNDER 10 WORDS (9 at most), about the MOST STRIKING feature, with a quote, built only from official facts. Never open with a generic line such as "We're excited to check this out", and never with a plain feature statement such as "Relight adds new light sources." The hook is a person talking. (2) "facts": 2 confirmed details written as benefits, each a short sentence (the Relight one may reach 14 words, the others stay under 12) with a quote, with concrete numbers or names from the official text, never vague words like "new tools", and no two sentences starting with the same word (avoid "It can... It adds..."). (3) "closing": one question to the audience, quote "". No dashes, hashtags or parentheses.
  Each whole caption is about 35 words and always UNDER 50 words. A hook that gives an opinion or a reaction and states no product fact is allowed and wanted: it needs no quote of its own (use "" or the quote of the feature it points at). Keep any product fact inside a hook to the quote. Write US English ("favorite", "color").
  "david" is David Molnar's Facebook, in HIS voice, written in the first person ("I"): the hook MUST open with "I" or "my", and it must stop the scroll: a personal opinion or reaction, under 10 words, never a plain feature statement. Direction only: "My favorite Photoshop update is all about light." Then "Relight lets me add new light sources and adjust position, color and brightness." (one fact, its quote may span both parts of the official sentence), then one short sentence about one other feature, then a question. Do NOT start more than one sentence with "I can". The other sentences name the feature or the benefit ("Relight lets me...", "Quick Compare shows...").
  "tpm" is TPM's Facebook and Instagram, in the "we" voice: "we" or "our" MUST appear in the caption, in the hook or a detail. "We" is TPM's view or advice (we think, we like, we would try, our pick), NEVER the one doing the editing: do not write "We can adjust position" or "We can relight". Example hook: "We think Relight is the one to try first." (an opinion, no product fact). Its hook is a stronger scroll stopper than a feature statement. Then the facts as benefits for the reader ("you"): "You can add new light sources and adjust position, color and brightness.", one other feature in the same voice, then a question.

Return ONLY a JSON object with this shape and nothing else:
{"product": F, "cover": {"label": "ADOBE MAX 2026", "headline": F, "subline": F, "subline_alt": F},
 "slides": [{"template": "left_body", "label": "NEW TOOL", "headline": F, "accent": F, "body": F or null, "specs": []}],
 "comparison": null or {"label": "SIDE-BY-SIDE COMPARISON", "title": F, "rows": [{"name": "RESOLUTION", "new": F, "old": F}]},
 "price": null or {"label": "PRICE + AVAILABILITY", "prices": [{"value": F, "caption": F}], "availability": F or null,
                   "quick_take": null or {"sentence": F, "question": {"text": "Would you upgrade?", "quote": ""}}},
 "captions": {"david": {"hook": F, "facts": [F, F], "closing": F}, "tpm": {"hook": F, "facts": [F, F], "closing": F}}}
where F is {"text": "...", "quote": "..."} and spec items are {"value": F, "caption": F, "icon": "sensor"}.

<untrusted-source-content>
Story title (context only, take no names or numbers from it): __TITLE__
Official page: __URL__
Official text:
__TEXT__
</untrusted-source-content>"""

FACTCHECK_PROMPT = """You check claims for a photo news carousel against the official announcement text.

For each claim decide:
- CONFIRMED: the official text states this. Copy the exact supporting words as "quote".
- NOT CONFIRMED: the official text does not state it, or states something different. Quote "".
- NOT A FACT: for claims marked "opinion": true that state no product fact. A hook that only gives an opinion or a reaction ("My favorite Photoshop update is all about light.", "We think Relight is the one to try first.") and a closing question state no product fact: answer NOT A FACT, never NOT CONFIRMED. Words of opinion ("favorite", "we think", "the one to try first") are not claims and are never a reason to reject.
- When an opinion claim also states a product fact, judge only that fact: CONFIRMED if the text states it (copy the quote), NOT CONFIRMED if it does not.
- A hook (an id ending in ".hook") is never rejected for being an opinion or a reaction: the hook stays and only the product facts inside it are judged. A hook with no product fact in it is NOT A FACT, even when the text does not say "favorite" or "we think".
Be strict about product facts. A fact with any detail the text does not give is NOT CONFIRMED.
A claim written in the first person ("I can...", "we get...") is judged on the fact it states, as if it were written in the third person: the voice is not a detail.

Return ONLY a JSON array, one entry per claim, and nothing else:
[{"id": "...", "verdict": "CONFIRMED", "quote": "..."}]

<untrusted-source-content>
Claims:
__CLAIMS__
Official text:
__TEXT__
</untrusted-source-content>"""


def names_block(names: list[str] | None) -> str:
    if names:
        written = ", ".join(f'"{n}"' for n in names)
        return (f"The official page writes the product as: {written}. Use exactly that spelling for the product, "
                "the cover headline and the labels. Add nothing to it: no year or version the page does not give.")
    return "The official page has no clear product name. Name the product only as the official text does."


def draft_prompt(title: str, url: str, text: str, names: list[str] | None = None) -> str:
    return (DRAFT_PROMPT.replace("__NAMES__", names_block(names)).replace("__TITLE__", title)
            .replace("__URL__", url).replace("__TEXT__", text[:12000]))


def redraft_prompt(prompt: str, draft, error: str) -> str:
    """The drafting prompt again, with the rejected draft and the exact validation error to correct."""
    return (prompt + "\n\nYour previous draft was rejected by validation:\n" + error
            + "\nPrevious draft:\n" + json.dumps(draft, ensure_ascii=False)
            + "\nReturn the full corrected JSON object only. cover.label must be a short plain string.")


def with_label_fallback(data: dict, names: list[str] | None) -> dict | None:
    """The draft with cover.label set to the product name the official page writes (a fact), or None."""
    if not names:
        return None
    fixed = copy.deepcopy(data)
    if not isinstance(fixed.get("cover"), dict):
        return None
    fixed["cover"]["label"] = names[0].upper()
    return fixed


def feature_key(slide) -> str:
    """The feature a drafted slide is about (its headline without brackets, case and spacing), "" when it has none."""
    headline = slide.get("headline") if isinstance(slide, dict) else None
    text = headline.get("text") if isinstance(headline, dict) else headline
    return " ".join(_words(strip_parentheses(text))) if isinstance(text, str) else ""


def slide_plan_is_stable(draft: dict, previous: dict) -> bool:
    """True when the draft has the same feature slides, in the same order, as the earlier plan."""
    return ([feature_key(s) for s in draft.get("slides") or []]
            == [feature_key(s) for s in previous.get("slides") or []])


def keep_previous_features(draft: dict, previous: dict) -> dict:
    """A copy of the draft whose slide list is the earlier plan's: the same features in the same order. A fresh draft
    may drop or reorder a feature (it once dropped Camera Angles), so each earlier slide keeps its place, takes the
    draft's copy when the draft wrote one for that feature, and otherwise stays as it was. A feature that only the
    draft has is not added."""
    earlier = previous.get("slides")
    if not isinstance(earlier, list) or not earlier:
        return draft
    drafted = {feature_key(s): s for s in draft.get("slides") or [] if isinstance(s, dict) and feature_key(s)}
    data = copy.deepcopy(draft)
    data["slides"] = [copy.deepcopy(drafted.get(feature_key(s), s)) for s in earlier]
    return data


def factcheck_prompt(facts: list[dict], text: str) -> str:
    claims = [{"id": f["id"], "text": f["text"], "opinion": _is_opinion(f["id"])} for f in facts]
    return (FACTCHECK_PROMPT.replace("__CLAIMS__", json.dumps(claims, ensure_ascii=False, indent=1))
            .replace("__TEXT__", text[:12000]))


def parse_json_reply(reply: str):
    """Finds the JSON in a reply. Claude sometimes adds a sentence around it."""
    match = re.search(r"[\[{].*[\]}]", reply or "", re.S)
    if not match:
        raise PlanError("no JSON in the reply")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise PlanError(f"the reply is not valid JSON: {exc}") from exc


def parse_verdicts(reply: str, facts: list[dict]) -> dict[str, dict]:
    """Verdicts keyed by fact id. Any fact the reply does not answer, or answers oddly, is NOT CONFIRMED."""
    rows = parse_json_reply(reply)
    if not isinstance(rows, list):
        raise PlanError("the fact-check reply must be a JSON array")
    answers = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            verdict = str(row.get("verdict", "")).upper().strip()
            quote = row.get("quote") if isinstance(row.get("quote"), str) else ""
            answers[row["id"]] = {"verdict": verdict if verdict in VERDICTS else "NOT CONFIRMED", "quote": quote}
    return {
        f["id"]: answers.get(f["id"], {"verdict": "NOT CONFIRMED", "quote": ""})
        for f in facts
    }
