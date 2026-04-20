"""Extract a theme pool for the puzzle generator from drafted article bodies
and topic names. Bias toward capitalized nouns (proper names, product names,
model names) and topic shorthand so the fill-in / word-search feel connected
to today's content."""

import re
from collections import Counter

_STOPWORDS = {
    "THE",
    "AND",
    "OR",
    "FOR",
    "BUT",
    "WITH",
    "FROM",
    "INTO",
    "OVER",
    "BY",
    "TO",
    "OF",
    "IN",
    "ON",
    "AT",
    "IS",
    "WAS",
    "ARE",
    "WERE",
    "BE",
    "BEEN",
    "BEING",
    "HAS",
    "HAVE",
    "HAD",
    "DO",
    "DOES",
    "DID",
    "NOT",
    "NO",
    "THAN",
    "THEN",
    "ALSO",
    "THIS",
    "THAT",
    "THESE",
    "THOSE",
    "WILL",
    "WOULD",
    "CAN",
    "COULD",
    "MAY",
    "MIGHT",
    "MUST",
    "SHALL",
    "SHOULD",
    "ITS",
    "IT",
    "ITS",
    "THEIR",
    "THEY",
    "THEM",
    "WHICH",
    "WHAT",
    "WHO",
    "WHOM",
    "WHERE",
    "WHEN",
    "WHY",
    "HOW",
    "ABOUT",
    "AFTER",
    "BEFORE",
    "DURING",
    "BETWEEN",
    "AGAINST",
    "WITHIN",
}

_CAP_TOKEN_RE = re.compile(r"[A-Z][A-Za-z-]{2,9}")
_ANY_WORD_RE = re.compile(r"[A-Za-z-]{3,10}")


def _clean(word: str) -> str:
    return word.strip("-").upper()


def _is_good(word: str) -> bool:
    if not (3 <= len(word) <= 10):
        return False
    if not word.isalpha():
        return False
    if word in _STOPWORDS:
        return False
    return True


def extract_theme_pool(
    drafts: list[dict],
    topic_names: list[str],
    target_count: int = 30,
) -> list[str]:
    """Return a flat list of up to `target_count` themed puzzle words,
    ordered by rough prominence. Falls back to an empty list if the drafts
    are too sparse -- the build_puzzles layer then reverts to defaults."""
    counts: Counter[str] = Counter()

    # Weight topic names heavily (they're the defining vocabulary of the issue).
    for name in topic_names:
        for token in _ANY_WORD_RE.findall(name):
            w = _clean(token)
            if _is_good(w):
                counts[w] += 5

    # Capitalized tokens from drafted content (proper nouns, product names).
    for d in drafts:
        text = " ".join([d.get("rendered_title") or "", d.get("body") or ""])
        for token in _CAP_TOKEN_RE.findall(text):
            w = _clean(token)
            if _is_good(w):
                counts[w] += 2

        for token in _ANY_WORD_RE.findall(text):
            w = _clean(token)
            if _is_good(w):
                counts[w] += 1

    return [w for w, _ in counts.most_common(target_count)]


_PHRASE_CHARS_RE = re.compile(r"[^A-Z ]+")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _sanitize_phrase(raw: str) -> str:
    """Uppercase, strip everything but letters and single spaces. Collapses
    whitespace. Returns '' if the result isn't a usable phrase."""
    up = _PHRASE_CHARS_RE.sub(" ", raw.upper())
    up = _MULTI_SPACE_RE.sub(" ", up).strip()
    return up


def _phrase_is_usable(p: str) -> bool:
    """Cryptogram sweet spot: 20-50 chars, 3-5 words, >=8 unique letters.
    Max five words so the phrase fits on a single line and feels like a
    tight headline. Too short is trivial; too-few-unique-letters means
    the cipher collapses to a handful of symbols. Also rejects phrases
    where a single word dominates length (e.g. stray code or URLs)."""
    if not (20 <= len(p) <= 50):
        return False
    words = p.split()
    if not (3 <= len(words) <= 5):
        return False
    if any(len(w) > 14 for w in words):
        return False
    if len(set(c for c in p if c.isalpha())) < 8:
        return False
    return True


def extract_crypto_phrases(
    drafts: list[dict],
    editorial: str | None = None,
    max_phrases: int = 12,
) -> list[str]:
    """Pull cryptogram-worthy phrases from today's drafted titles + the
    editorial's first sentence. Returns a deduplicated list ordered by
    rough quality (more unique letters first). Falls back to an empty
    list if nothing qualifies; build_puzzles then reverts to defaults."""
    candidates: list[str] = []

    for d in drafts:
        title = d.get("rendered_title") or ""
        phrase = _sanitize_phrase(title)
        if _phrase_is_usable(phrase):
            candidates.append(phrase)

    if editorial:
        first_dot = editorial.find(". ")
        head = editorial if first_dot == -1 else editorial[:first_dot]
        phrase = _sanitize_phrase(head)
        if _phrase_is_usable(phrase):
            candidates.append(phrase)

    seen: set[str] = set()
    unique: list[str] = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    unique.sort(key=lambda p: -len(set(c for c in p if c.isalpha())))
    return unique[:max_phrases]
