"""Claude Code picks each slide's product photo from the official candidates, and checks every pick.

For each slot, candidates are tried largest first. A free Claude CLI call reads the candidate image
(the Read tool only, limited to the candidates folder) together with the official text and the slide
it is for, and answers JSON. A candidate is used only when:
  matches_product = true, is_real_photo_or_official_screenshot = true, shows_slide_subject = true,
  has_watermark = false, has_people_as_subject = false, looks_ai_generated = false.
Official demo video posters (images.gather_posters) and page images whose alt text names a feature are tagged
with the feature they show. A feature slide may ONLY show an image tagged with its own feature. If it has none,
the renderer draws the text-led layout (no image box), never another feature's screenshot, and the run summary and
Slack say so. The cover tries general images first, then reuses the whole frame of a feature poster already placed.
A has_people_as_subject = true verdict does not block an official demo poster on the slide of its own feature
(the person is only the demo photo inside the demo). A candidate is never used on two feature slides.
Every verdict is written to sources.md.

Nothing here generates, edits or background-removes an image.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import carousel_plan
import images
from images import Candidate

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
REQUIRED_TRUE = ("matches_product", "is_real_photo_or_official_screenshot", "shows_slide_subject")
REQUIRED_FALSE = ("has_watermark", "has_people_as_subject", "looks_ai_generated")
MAX_TRIES_PER_SLOT = 6


@dataclass
class Slot:
    name: str  # "01", "02", "03-old"
    number: int
    brief: str  # what this slide shows, from its headline and body
    kind: str = ""  # "cover", "feature", "comparison", "comparison-old" or "price"
    feature: str = ""  # a feature slide's headline: the feature name its image should show
    demo: str = ""  # set while checking an official demo video poster: the video's title


def slots_for(views: list[dict]) -> list[Slot]:
    """One slot per image on the slides, in slide order (a comparison has two)."""
    slots = []
    for number, view in enumerate(views, 1):
        if view["type"] == "cover":
            slots.append(Slot(f"{number:02d}", number, f"Cover: the product, {view['headline']}", "cover"))
        elif view["type"] == "feature":
            text = " ".join(part for part in (view["headline"], view.get("accent"), view.get("body")) if part)
            slots.append(Slot(f"{number:02d}", number, f"Slide about: {text}", "feature", view["headline"]))
        elif view["type"] == "comparison":
            slots.append(Slot(f"{number:02d}", number, f"Comparison, the new model: {view['title']}", "comparison"))
            slots.append(Slot(f"{number:02d}-old", number, "Comparison, the earlier model named in the title",
                              "comparison-old"))
        elif view["type"] == "price":
            slots.append(Slot(f"{number:02d}", number, "Price slide: the product being sold", "price"))
    return slots


def _same_feature(a: str, b: str) -> bool:
    return bool(a and b) and " ".join(images.feature_words(a)) == " ".join(images.feature_words(b))


def is_demo(candidate: Candidate, slot: Slot) -> bool:
    """True for an official demo video poster of this feature slide's own feature."""
    return (slot.kind == "feature" and candidate.kind == "video poster" and bool(candidate.feature)
            and _same_feature(candidate.feature, slot.feature))


def candidates_for(slot: Slot, candidates: list[Candidate]) -> list[Candidate]:
    """The candidates worth checking for this slot, best first.

    A feature slide takes ONLY images tagged with its own feature (official demo posters first, then largest
    first). General images and images of another feature are never offered: a feature slide must not show a
    different feature. The cover tries general images first, then feature posters (a whole frame, uncropped).
    Other slots take everything, largest first.
    """
    by_size = sorted(candidates, key=lambda c: max(c.width, c.height), reverse=True)
    general = [c for c in by_size if not c.feature]
    if slot.kind == "feature":
        if not slot.feature:
            return []
        own = [c for c in by_size if _same_feature(c.feature, slot.feature)]
        # An image with no alt text of its own is still offered when the paragraph written just before it names this
        # feature in full. It is only a possible picture of it: the image check has to see the feature in it.
        hinted = [c for c in by_size
                  if not c.feature and any(_same_feature(f, slot.feature) for f in c.context_features)]
        return sorted(own, key=lambda c: c.kind != "video poster") + hinted
    if slot.kind == "cover":
        return general + [c for c in by_size if c.feature]
    return by_size


def verifier_prompt(image_path: Path, slot: Slot, official_text: str, product: str) -> str:
    return (
        "You check one product image for a photo news carousel. Read the image file at this exact path "
        f"with the Read tool and nothing else: {image_path}\n\n"
        f"The product announced is: {product}. The image must show THIS product (the exact model name, "
        "badge, mount, controls and ports consistent with the announcement), not a predecessor or a "
        "different model.\n"
        f"What the slide needs to show: {getattr(slot, 'brief', '') or 'the product announced'}\n"
        + (f"Provenance: this is the poster frame of Adobe's own official demo video {slot.demo!r} for exactly "
           "this feature, taken from Adobe's official post. A demo frame is an official screenshot of the feature "
           "even when it shows little interface. Report what you see truthfully.\n" if getattr(slot, "demo", "") else "")
        + "Set shows_slide_subject true only if the picture actually shows that view or subject.\n\n"
        "Answer ONLY with a JSON object with these keys: matches_product (true/false), "
        "is_real_photo_or_official_screenshot (true/false: a real camera photo or a real app/official "
        "screenshot, not a render or illustration), has_watermark (true/false), has_people_as_subject "
        "(true/false: true only when a person is the main subject of the picture; an app screenshot that "
        "merely contains a photo with a person in it is false), looks_ai_generated (true/false), "
        "shows_slide_subject (true/false), notes (one short line).\n\n"
        "<untrusted-source-content>\nOfficial text (for reference):\n"
        f"{official_text[:4000]}\n</untrusted-source-content>"
    )


def parse_verdict(reply: str) -> dict:
    """A verdict with every key present as a boolean. Anything else is an unreadable answer."""
    try:
        data = carousel_plan.parse_json_reply(reply)
    except carousel_plan.PlanError:
        return {"unreadable": True, "notes": "image check could not run: the answer was not JSON"}
    if not isinstance(data, dict):
        return {"unreadable": True, "notes": "image check could not run: the answer was not an object"}
    keys = REQUIRED_TRUE + REQUIRED_FALSE
    if any(not isinstance(data.get(k), bool) for k in keys):
        return {"unreadable": True, "notes": "image check could not run: a yes/no answer was missing"}
    return {**{k: data[k] for k in keys}, "notes": str(data.get("notes", ""))[:200], "unreadable": False}


def decide(verdict: dict, demo: bool = False) -> tuple[bool, str]:
    """(use it?, reason). The only rule that accepts an image.

    demo = the image is an official demo video poster of the slide's own feature: a person in the demo photo
    (has_people_as_subject) does not block it. Every other check still applies."""
    if verdict.get("unreadable"):
        return False, verdict.get("notes", "unreadable answer")
    problems = [k for k in REQUIRED_TRUE if verdict[k] is not True]
    problems += [k for k in REQUIRED_FALSE if verdict[k] is not False and not (demo and k == "has_people_as_subject")]
    if problems:
        return False, "fails: " + ", ".join(problems)
    return True, "passes every check" + (" (official demo of this feature, a person in the demo photo is allowed)"
                                          if demo and verdict.get("has_people_as_subject") else "")


def choose(verdicts: list[tuple[Candidate, dict]], used: set[str], slot: Slot | None = None) -> Candidate | None:
    """The first candidate, largest first, that passes and has not been used on another slide."""
    for candidate, verdict in verdicts:
        ok, _ = decide(verdict, demo=slot is not None and is_demo(candidate, slot))
        if ok and candidate.file not in used:
            return candidate
    return None


def place_file(source: Path, images_dir: Path, slot_name: str) -> Path:
    """Copies a chosen candidate to images/<slot><ext> and removes any other file of that slot (for example an older
    untrimmed 02.jpg beside the trimmed 02.png), so the renderer can only find the file that was chosen."""
    target = images_dir / f"{slot_name}{source.suffix}"
    for extension in IMAGE_EXTENSIONS:
        stale = images_dir / f"{slot_name}{extension}"
        if stale != target and stale.is_file():
            stale.unlink()
    shutil.copyfile(source, target)
    return target


def no_image_reason(slot: Slot, offered: list[Candidate], verdicts: list[tuple[Candidate, dict]],
                    total: int) -> str:
    """Exactly why a feature slide has no image: nothing was tagged with its feature, or what the checks said."""
    if not offered:
        return (f"none of the {total} saved official images and demo video posters is tagged with {slot.feature!r} "
                "(no alt text, file name, video title, help page heading or paragraph before the image names it)")
    seen = "; ".join(f"{c.file}: {decide(v, demo=is_demo(c, slot))[1]}" for c, v in verdicts)
    left = len(offered) - len(verdicts)
    return (f"{len(verdicts)} candidate(s) were checked and none passed ({seen})"
            + (f"; {left} more were not checked (the limit is {MAX_TRIES_PER_SLOT} per slide)" if left > 0 else ""))


def checked_slot_for(candidate: Candidate, slot: Slot) -> Slot:
    """The slot as the image check sees it: for a feature's own demo poster it names the demo video."""
    return replace(slot, demo=candidate.title or candidate.alt or "demo") if is_demo(candidate, slot) else slot


def first_checks(order: list[Slot], candidates: list[Candidate]) -> list[tuple[Candidate, Slot]]:
    """(candidate, slot as checked) for the first candidate each slot will try, in slot order. The cover's first
    candidate is left out when a feature slide tries it first (the feature slide is likely to use it)."""
    jobs: list[tuple[Candidate, Slot]] = []
    taken: set[str] = set()
    for slot in order:
        offered = candidates_for(slot, candidates)
        if not offered:
            continue
        candidate = offered[0]
        if slot.kind == "cover" and candidate.file in taken:
            continue
        taken.add(candidate.file)
        jobs.append((candidate, checked_slot_for(candidate, slot)))
    return jobs


def prefetch_verify(verify, jobs: list[tuple[Candidate, Slot]], out_dir: Path, official_text: str, product: str,
                    workers: int):
    """Runs the given checks side by side, then returns a verify function that answers those from memory (each once)
    and asks verify for anything else. A check that raised is simply asked again later, in order."""
    def run(job):
        candidate, checked = job
        try:
            return verify(out_dir / candidate.file, checked, official_text, product)
        except Exception:  # the sequential pick asks again and handles it as before
            return None

    memo = {}
    for (candidate, checked), verdict in zip(jobs, images.parallel_map(run, jobs, workers)):
        if verdict is not None:
            memo[(str(out_dir / candidate.file), repr(checked))] = verdict

    def remembered(path, slot, text, name):
        key = (str(path), repr(slot))
        if key in memo:
            return memo.pop(key)
        return verify(path, slot, text, name)

    return remembered


def pick_for_slots(slots: list[Slot], candidates: list[Candidate], out_dir: Path, official_text: str,
                   product: str, verify, workers: int = 1) -> tuple[dict[str, Candidate | None], list[str]]:
    """Picks an image for every slot. verify(image_path, slot, official_text, product) returns a verdict dict.

    Copies each chosen image to images/<slot>.<ext>. Returns (choices by slot, log lines for sources.md).
    """
    used: set[str] = set()
    choices: dict[str, Candidate | None] = {}
    log: list[str] = [f"Auto image pick (Claude Code checks each candidate; rules: {', '.join(REQUIRED_TRUE)} "
                      f"must be yes; {', '.join(REQUIRED_FALSE)} must be no)."]
    tagged = [f"{c.file} shows {c.feature!r}" for c in candidates if c.feature]
    if tagged:
        log.append("Video posters tagged with a slide feature: " + "; ".join(tagged) + ".")
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    cover_slot = next((s for s in slots if s.kind == "cover" or s.name == "01"), None)
    # The cover is picked last, so each feature slide first takes its own tagged demo poster and the cover
    # takes the best general image left (or, with none left, a poster no slide is waiting for).
    order = [s for s in slots if s is not cover_slot] + ([cover_slot] if cover_slot is not None else [])
    if workers > 1:
        # Speed: the first check of every slot (almost always the one that is used) runs side by side; the picking
        # below is unchanged and simply reads those answers. Any further check still runs one at a time, in order.
        verify = prefetch_verify(verify, first_checks(order, candidates), out_dir, official_text, product, workers)
    unplaced: list[Slot] = []
    placed: list[tuple[Slot, Candidate, dict]] = []
    why: dict[str, str] = {}
    for slot in order:
        verdicts: list[tuple[Candidate, dict]] = []
        offered = candidates_for(slot, candidates)
        for candidate in offered:
            if len(verdicts) >= MAX_TRIES_PER_SLOT:
                break
            if candidate.file in used:
                continue
            demo = is_demo(candidate, slot)
            checked_slot = replace(slot, demo=candidate.title or candidate.alt or "demo") if demo else slot
            verdict = verify(out_dir / candidate.file, checked_slot, official_text, product)
            verdicts.append((candidate, verdict))
            ok, reason = decide(verdict, demo=demo)
            log.append(f"slide {slot.name}: {candidate.file} ({candidate.width}x{candidate.height}) "
                       f"{'USED' if ok else 'rejected'}: {reason}. {verdict.get('notes', '')}")
            if ok:
                break
        unreadable = sum(1 for _, v in verdicts if v.get("unreadable"))
        if unreadable:
            log.append(f"slide {slot.name}: image check could not run for {unreadable} candidate(s); "
                       "the reasons are on the lines above.")
        chosen = choose(verdicts, used, slot)
        choices[slot.name] = chosen
        if chosen is None:
            unplaced.append(slot)
            why[slot.name] = no_image_reason(slot, [c for c in offered if c.file not in used], verdicts, len(candidates))
            continue
        used.add(chosen.file)
        placed.append((slot, chosen, next(v for c, v in verdicts if c is chosen)))
        target = place_file(out_dir / chosen.file, images_dir, slot.name)
        origin = (f", official demo video {chosen.page}, video title {chosen.title!r}, tagged {chosen.feature!r}"
                  if chosen.kind == "video poster" else "")
        if chosen.kind != "video poster" and slot.kind == "feature" and not chosen.feature:
            origin = (", an image with no alt text of its own, offered because the paragraph before it on the page names "
                      f"{slot.feature!r}; the image check confirmed the feature is in the picture")
        trimmed = f", {chosen.trimmed}" if chosen.trimmed else ""
        log.append(f"slide {slot.name}: placed {target.name} from {chosen.image_url} (on {chosen.page}){origin}{trimmed}")
    # A cover with no image of its own reuses the WHOLE frame of an official feature poster already placed on a
    # slide (never cropped), as long as the check saw no person as its subject.
    if cover_slot is not None and choices.get(cover_slot.name) is None:
        donor = next(((s, c) for s, c, v in placed
                      if c.kind == "video poster" and v.get("has_people_as_subject") is False), None)
        if donor is not None:
            slot, candidate = donor
            target = place_file(out_dir / candidate.file, images_dir, cover_slot.name)
            choices[cover_slot.name] = candidate
            unplaced = [s for s in unplaced if s is not cover_slot]
            trimmed = f", {candidate.trimmed}" if candidate.trimmed else ""
            log.append(f"slide {cover_slot.name}: placed {target.name}, the whole uncropped frame of the official demo "
                       f"poster also used on slide {slot.name} ({candidate.image_url}, on {candidate.page}){trimmed}")
    # Notes for the slides with no image. A feature slide with no image of its own gets the text-led layout.
    for slot in unplaced:
        if slot.kind == "feature":
            log.append(f"slide {slot.name}: no official image of this feature passed, so the slide uses the "
                       f"text-led layout with no image box. Why: {why.get(slot.name, 'no candidate was checked')}. "
                       "It never shows another feature's image. Add an image by hand to replace it.")
        elif slot is cover_slot:
            log.append(f"slide {slot.name}: no cover image passed; the cover shows only the brand glow "
                       "(no empty box). Add an image by hand to replace it.")
        else:
            log.append(f"slide {slot.name}: no image passed; the placeholder stays. Add an image by hand.")
    return choices, log
