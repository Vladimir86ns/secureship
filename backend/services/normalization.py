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
    """Canonical E.164 digits (no "+"), so common formatting variants match.

    Customers are stored in E.164 (Section 4.4, e.g. +15550100123). A visitor may type
    the same number with or without the country code, so:
      - keep digits only;
      - a leading international "00" prefix is dropped ("001 555 ..." -> "1555...");
      - exactly 10 digits = a NANP (US/Canada) number without the country code -> "1" is added.
    Anything else is kept as typed (it already carries its country code). A non-NANP
    number must therefore be typed with its country code.
    """
    digits = _NON_DIGIT_RE.sub("", value)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:
        digits = "1" + digits
    return digits
