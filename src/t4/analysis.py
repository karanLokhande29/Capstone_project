"""P3-002 Part B: verdicts, the exploratory repair, and human-vs-metric statistics.

Verdict rule (fixed by the prompt, applied to a paired difference ``type - genuine``):
    CI entirely >= 0  -> "reproduces" (the metric scores the gaming answer at least as high);
    CI entirely <  0  -> "does not reproduce";
    otherwise         -> "inconclusive at n = <n>".

Repair (declared in config ``t4.repair`` before any answer was scored):
    lcs_ratio = token LCS(answer, retrieved passages joined) / answer tokens  ([a-z0-9]+, lower-case)
    penalty   = clip((lcs_ratio - tau) / (1 - tau), 0, 1)
    repaired  = (1 - penalty) * (composite + relevance) / 2
where ``relevance`` is the mean over answer sentences of RePASs' own NLI entailment
probability with the question as premise.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

import numpy as np

from src.eval.metrics import bootstrap_indices

_TOKEN = re.compile(r"[a-z0-9]+")


def verdict(ci_low: float, ci_high: float, n: int) -> str:
    if ci_low >= 0:
        return "reproduces"
    if ci_high < 0:
        return "does not reproduce"
    return f"inconclusive at n = {n}"


def ranking_verdict(ci_low: float, ci_high: float, n: int) -> str:
    """For ``genuine - other`` under the repaired score."""
    if ci_low > 0:
        return "genuine ranked above"
    if ci_high < 0:
        return "genuine ranked below"
    return f"inconclusive at n = {n}"


def tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    """Longest common subsequence of two token lists (O(len(a) * len(b)), one row of memory)."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, start=1):
            cur.append(prev[j - 1] + 1 if x == y else (prev[j] if prev[j] >= cur[j - 1] else cur[j - 1]))
        prev = cur
    return prev[-1]


def lcs_ratio(answer: str, passages: Sequence[str]) -> float:
    ans = tokens(answer)
    if not ans:
        return 0.0
    return lcs_length(ans, tokens(" ".join(passages))) / len(ans)


def overlap_penalty(ratio: float, tau: float) -> float:
    if not 0 <= tau < 1:
        raise ValueError("tau must be in [0, 1)")
    return float(min(1.0, max(0.0, (ratio - tau) / (1 - tau))))


def repaired_score(composite: float, relevance: float, penalty: float) -> float:
    return (1 - penalty) * (composite + relevance) / 2


def _rank(x: np.ndarray) -> np.ndarray:
    """Average ranks (ties share the mean rank), as Spearman needs."""
    order = np.argsort(x, kind="stable")
    ranks = np.empty(len(x))
    sorted_x = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sorted_x[j + 1] == sorted_x[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(xa) < 3 or np.all(xa == xa[0]) or np.all(ya == ya[0]):
        return None
    rx, ry = _rank(xa), _rank(ya)
    return float(np.corrcoef(rx, ry)[0, 1])


def spearman_bootstrap(x: Sequence[float], y: Sequence[float], *, resamples: int, seed: int) -> dict[str, Any]:
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    point = spearman(xa, ya)
    draws = [spearman(xa[idx], ya[idx]) for idx in bootstrap_indices(len(xa), resamples=resamples, seed=seed)]
    valid = np.array([d for d in draws if d is not None])
    lo, hi = (np.percentile(valid, [2.5, 97.5]) if len(valid) else (None, None))
    return {"rho": point, "ci_low": None if lo is None else float(lo), "ci_high": None if hi is None else float(hi),
            "n": len(xa), "degenerate_resamples": resamples - len(valid)}
