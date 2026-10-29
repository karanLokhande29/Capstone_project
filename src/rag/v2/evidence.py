"""Evidence helpers shared by the V2 agents: quote checks and number extraction.

- ``quote_in``: a model's quotation counts only if, after normalisation (case, punctuation, spacing), it occurs in the
  text it claims to quote and is at least ``MIN_QUOTE_WORDS`` words long, so a quote such as "the bank shall" proves
  nothing.
- ``numbers``: digits and English number words ("fifteen" == "15"), for the field verifier's numeric check.
"""

from __future__ import annotations

import re

MIN_QUOTE_WORDS = 4

_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)")
_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def quote_in(quote: str | None, text: str | None, *, min_words: int = MIN_QUOTE_WORDS) -> bool:
    q = norm(quote)
    return bool(q) and len(q.split()) >= min_words and f" {q} " in f" {norm(text)} "


def numbers(text: str | None) -> set[str]:
    """Numbers stated in ``text``, normalised: thousands separators and leading zeros removed, number words as digits."""
    out = set()
    for m in _NUM.finditer(text or ""):
        n = m.group(1).replace(",", "").rstrip(".")
        out.add(n if "." in n else (n.lstrip("0") or "0"))
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if w in _WORDS:
            out.add(str(_WORDS[w]))
    return out
