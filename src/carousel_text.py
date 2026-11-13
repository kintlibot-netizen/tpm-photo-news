"""Text rules for carousels: matching quotes to official text, and the dash, hashtag and overflow lint.

Nothing here calls Claude or the network, so it can be tested with plain strings.
"""
from __future__ import annotations

import re

# Every dash-like character that could be read as a dash. Matching treats them all as a plain hyphen.
_DASH_VARIANTS = "‐‑‒–—―−"

MIN_QUOTE_LENGTH = 12  # shorter quotes match too much ("Canon") to prove a fact


class LintError(ValueError):
    """Raised when slide or caption text breaks a rule. The build stops."""


def match_key(text: str) -> str:
    """A form of the text that ignores case, spacing, curly quotes and dash variants."""
    text = text.replace("​", "")
    for dash in _DASH_VARIANTS:
        text = text.replace(dash, "-")
    text = (
        text.replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
    )
    return " ".join(text.lower().split())


def quote_found(quote: str, official_text: str) -> bool:
    """True when the quote's words appear in the official text. Long enough to prove something."""
    key = match_key(quote or "")
    return len(key) >= MIN_QUOTE_LENGTH and key in match_key(official_text)


def clean_output(text: str) -> str:
    """Number ranges such as 24–50 use a plain hyphen. Other dashes are left for the lint to catch."""
    return re.sub(r"(?<=\d)[‒–](?=\d)", "-", text)


_LINT_RULES = [
    (re.compile("—"), "em dash"),
    (re.compile("–"), "en dash"),
    (re.compile(r"(^|\s)[-‒−](\s|$)"), "spaced hyphen used as a dash"),
    (re.compile(r"(?<!\w)#[A-Za-z]\w*"), "hashtag"),
]


def lint_text(where: str, text: str) -> list[str]:
    """Problems in one piece of output text. An empty list means it passes."""
    problems = []
    for pattern, label in _LINT_RULES:
        if pattern.search(text):
            problems.append(f"{where}: {label} in {text!r}")
    return problems


HYPHENATED_WORD = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)+")


def hyphenated_words(text: str) -> list[str]:
    """Words joined with a hyphen ('re-prompting', 'non-destructive'). A hyphen can break a word across two lines, so
    body copy may not contain one. Number ranges such as 24-50 are not words and are not listed."""
    return HYPHENATED_WORD.findall(text or "")


def lint_texts(items: list[tuple[str, str]]) -> list[str]:
    problems: list[str] = []
    for where, text in items:
        problems.extend(lint_text(where, text))
        if where.endswith(" body"):  # slide body copy only: a headline such as 5-AXIS keeps its official spelling
            problems.extend(f"{where}: hyphenated word {word!r} in {text!r}" for word in hyphenated_words(text))
    return problems


def lint_overflow(overflowing: list[str]) -> list[str]:
    """Browser measurements: each entry names a text box that still overflows at its smallest size."""
    return [f"text overflows its box: {name}" for name in overflowing]
