"""Reusable text helpers for LegalEase.

These functions are pure (no I/O) so they are easy to test and are shared by
the backend (cleaning AI output) and the document formatters (TXT/DOCX/PDF).
"""

from __future__ import annotations

import re

# Canonical notice appended to every generated document.
REVIEW_NOTICE_HEADING = "REVIEW NOTICE"
REVIEW_NOTICE_TEXT = (
    "This is an AI-assisted legal document draft. It should be reviewed by a "
    "qualified legal professional for applicable jurisdiction-specific "
    "requirements before use."
)

MISSING_INFO_TOKEN = "[MISSING INFORMATION]"

# --- quote / dash / whitespace normalisation tables ------------------------
_QUOTE_MAP = {
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u00ab": '"', "\u00bb": '"',
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
}
_DASH_MAP = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",  # hyphens / en dash
    "\u2212": "-",                                                # minus sign
    "\u2014": " - ", "\u2015": " - ",                             # em dash / horizontal bar
}
_INVISIBLE_CHARS = {
    "\u00a0": " ",   # non-breaking space
    "\u200b": "",    # zero-width space
    "\u200c": "",
    "\u200d": "",
    "\ufeff": "",    # BOM / zero-width no-break space
}

_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_MARKDOWN_BULLET = re.compile(r"^(\s*)[*+]\s+", re.MULTILINE)
_MARKDOWN_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,})\s*$", re.MULTILINE)
_MARKDOWN_FENCE = re.compile(r"^\s*```.*$", re.MULTILINE)
_MARKDOWN_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MARKDOWN_BOLD_UNDERSCORE = re.compile(r"(?<!\w)__(?=[^_\s])(.+?)(?<=[^_\s])__(?!\w)")
_MARKDOWN_ITALIC = re.compile(r"(?<![\w*])\*(\S(?:[^*\n]*?\S)?)\*(?![\w*])")

_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+[A-Z][^.;:!?]*$")


def normalize_quotes(text: str) -> str:
    """Replace typographic (curly) quotation marks with straight ones."""
    return text.translate(str.maketrans(_QUOTE_MAP))


def normalize_dashes(text: str) -> str:
    """Replace en/em dashes and similar characters with plain hyphens."""
    return text.translate(str.maketrans(_DASH_MAP))


def clean_whitespace(text: str) -> str:
    """Normalise line endings and spacing.

    * converts CRLF / CR to LF
    * replaces non-breaking / zero-width characters
    * collapses runs of spaces and tabs inside a line
    * strips leading and trailing spaces on every line
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(str.maketrans(_INVISIBLE_CHARS))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)


def remove_excessive_blank_lines(text: str, max_blank_lines: int = 1) -> str:
    """Allow at most ``max_blank_lines`` consecutive blank lines."""
    limit = max(0, max_blank_lines)
    pattern = r"\n{" + str(limit + 2) + r",}"
    return re.sub(pattern, "\n" * (limit + 1), text)


def strip_markdown(text: str) -> str:
    """Remove common Markdown syntax so the text is clean plain text.

    Headings become UPPERCASE lines, bullets become ``- `` and emphasis
    markers are removed. Signature lines made of underscores are preserved.
    """
    text = _MARKDOWN_FENCE.sub("", text)
    text = _MARKDOWN_RULE.sub("", text)
    text = _MARKDOWN_HEADING.sub(lambda m: m.group(1).strip().upper(), text)
    text = _MARKDOWN_BULLET.sub(lambda m: f"{m.group(1)}- ", text)
    text = _MARKDOWN_BOLD.sub(r"\1", text)
    text = _MARKDOWN_BOLD_UNDERSCORE.sub(r"\1", text)
    text = _MARKDOWN_ITALIC.sub(r"\1", text)
    return text.replace("`", "")


def sanitize_text(text: str | None) -> str:
    """Full clean-up pipeline applied to AI output before it is shown."""
    if not text:
        return ""
    text = strip_markdown(text)
    text = normalize_quotes(text)
    text = normalize_dashes(text)
    text = clean_whitespace(text)
    text = remove_excessive_blank_lines(text)
    return text.strip()


def split_terms(terms: str | None) -> list[str]:
    """Split a terms string into individual items.

    Items are separated by semicolons and/or new lines. Leading bullet
    markers are removed and empty items are dropped.
    """
    if not terms:
        return []
    items: list[str] = []
    for chunk in re.split(r"[;\n]", terms.replace("\r", "\n")):
        item = re.sub(r"^\s*(?:[-*\u2022\u25cf\u25aa]\s+)", "", chunk).strip()
        if item:
            items.append(item)
    return items


def is_heading(line: str) -> bool:
    """Heuristic: does this single line look like a section heading?

    A heading is a short line that is fully UPPERCASE (e.g. ``1. PAYMENT`` or
    ``REVIEW NOTICE``) or a short numbered title such as ``2. Payment Terms``.
    Sentences ending in punctuation are never headings.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("[") or len(stripped) > 90:
        return False
    if stripped[-1] in ".;,":
        return False
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) >= 3 and all(c.isupper() for c in letters):
        return True
    if _NUMBERED_HEADING.match(stripped) and len(stripped.split()) <= 7 and len(stripped) <= 60:
        return True
    return False


def ensure_review_notice(text: str) -> str:
    """Guarantee the document ends with the canonical REVIEW NOTICE block.

    Any REVIEW NOTICE section written by the model is replaced so the wording
    is always identical.
    """
    matches = list(
        re.finditer(rf"(?im)^\s*{re.escape(REVIEW_NOTICE_HEADING)}\s*:?\s*$", text)
    )
    body = text[: matches[-1].start()] if matches else text
    body = body.rstrip()
    return f"{body}\n\n{REVIEW_NOTICE_HEADING}\n\n{REVIEW_NOTICE_TEXT}"


def count_missing_information(text: str) -> int:
    """Count ``[MISSING INFORMATION]`` placeholders left in the text."""
    return text.count(MISSING_INFO_TOKEN)
