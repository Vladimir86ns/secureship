import re

_PUNCT_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")
_NON_DIGIT_RE = re.compile(r"\D")


def normalize_text(value: str) -> str:
    """trim + casefold + collapse whitespace + strip punctuation.

    Deliberately basic — no abbreviation/postal standardization. "St" and
    "Street" are NOT treated as equivalent; seed data and visitor input must
    use the same spelling to match.
    """
    no_punct = _PUNCT_RE.sub("", value)
    collapsed = _WHITESPACE_RE.sub(" ", no_punct.strip())
    return collapsed.casefold()


def normalize_phone(value: str) -> str:
    """Strip everything but digits, so common formatting variants match."""
    return _NON_DIGIT_RE.sub("", value)
