"""IndiaFinBench scoring (Extension #8, Amendment 8): the dataset card's four-stage automated pipeline.

The card's repository was unavailable, so the stages are implemented from the card's "Evaluation Protocol":
1. exact match after case normalisation and punctuation stripping;
2. fuzzy token match: token-set ratio >= 72 (RapidFuzz ``token_set_ratio`` re-implemented with the Indel distance);
3. numerical-extraction match: the number sets of reference and prediction agree (currency symbols, comma separators
   and units removed);
4. contradiction items: leading Yes/No word only.
Contradiction items are scored by stages 1 and 4 only (the card: "CON items use exact Yes/No matching"); stages 2 and 3
would accept a prediction that merely contains the reference word anywhere. No LLM judge is used.
"""

from __future__ import annotations

import math
import re
import string
from typing import Any

THRESHOLD = 72.0
_PUNCT = str.maketrans({c: " " for c in string.punctuation + "₹“”‘’–—"})
_NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?")


def normalise(s: str) -> str:
    return " ".join(str(s).lower().translate(_PUNCT).split())


def _lcs(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if ca == cb else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def indel_distance(a: str, b: str) -> int:
    return len(a) + len(b) - 2 * _lcs(a, b)


def _norm_sim(dist: int, lensum: int) -> float:
    return 100.0 if lensum == 0 else 100.0 - 100.0 * dist / lensum


def token_set_ratio(s1: str, s2: str) -> float:
    """RapidFuzz ``fuzz.token_set_ratio`` (no processor; callers pass normalised text)."""
    a, b = set(s1.split()), set(s2.split())
    if not a or not b:
        return 0.0
    inter, ab, ba = a & b, a - b, b - a
    if inter and (not ab or not ba):
        return 100.0
    d_ab, d_ba = " ".join(sorted(ab)), " ".join(sorted(ba))
    sect = len(" ".join(sorted(inter)))
    sect_ab = sect + bool(sect) + len(d_ab)
    sect_ba = sect + bool(sect) + len(d_ba)
    result = _norm_sim(indel_distance(d_ab, d_ba), sect_ab + sect_ba)
    if not sect:
        return result
    r_ab = _norm_sim(bool(sect) + len(d_ab), sect + sect_ab)
    r_ba = _norm_sim(bool(sect) + len(d_ba), sect + sect_ba)
    return max(result, r_ab, r_ba)


def numbers(s: str) -> set[float]:
    t = re.sub(r"(?i)(?:₹|rs\.?|inr|\$|usd)", " ", str(s))
    t = re.sub(r"(?<=\d),(?=\d)", "", t)  # comma separators, including the Indian 1,00,000 grouping
    return {round(float(x), 6) for x in _NUM.findall(t)}


def leading_yes_no(s: str) -> str | None:
    w = normalise(s).split()
    return w[0] if w and w[0] in ("yes", "no") else None


def score(reference: str, prediction: str, task_type: str) -> dict[str, Any]:
    ref, pred = normalise(reference), normalise(prediction)
    if not pred:
        return {"correct": False, "stage": None}
    if ref == pred:
        return {"correct": True, "stage": 1}
    if task_type == "contradiction_detection":
        lr, lp = leading_yes_no(reference), leading_yes_no(prediction)
        return {"correct": lr is not None and lr == lp, "stage": 4 if lr is not None and lr == lp else None}
    tsr = token_set_ratio(ref, pred)
    if tsr >= THRESHOLD:
        return {"correct": True, "stage": 2, "token_set_ratio": round(tsr, 2)}
    nr, np_ = numbers(reference), numbers(prediction)
    if nr and nr == np_:
        return {"correct": True, "stage": 3, "token_set_ratio": round(tsr, 2)}
    return {"correct": False, "stage": None, "token_set_ratio": round(tsr, 2)}


def wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, c - h), min(1.0, c + h)]
