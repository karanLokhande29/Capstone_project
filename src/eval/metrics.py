"""Ranking and classification metrics with seeded bootstrap CIs (P3-001).

Ranking metrics take a ranked list of paragraph ids and a relevance map
``{paragraph_id: grade}`` with grade 2 (same / chosen) or 1 (different /
related). A grade >= 1 counts as relevant for Recall and MAP; nDCG uses the
grades with exponential gain ``2**g - 1`` and a ``log2(rank + 1)`` discount.

Queries with no relevant paragraph are not scored (their metrics are
undefined); the caller counts and reports them.

Bootstrap: percentile 95% CIs from ``resamples`` draws made with
``numpy.random.default_rng(seed)``. One index matrix per (seed, n), so every
system scored on the same query list is resampled identically and the paired
differences use exactly the same draws. With ``clusters`` given, whole clusters
are resampled instead of single queries (a sensitivity check when several
queries share one source text).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Hashable, Mapping, Sequence

import numpy as np


# -- ranking ------------------------------------------------------------------


def _relevant(rel: Mapping[str, int]) -> set[str]:
    return {p for p, g in rel.items() if g > 0}


def recall_at_k(ranked: Sequence[str], rel: Mapping[str, int], k: int) -> float:
    relevant = _relevant(rel)
    if not relevant:
        raise ValueError("recall is undefined without a relevant paragraph")
    return len(relevant.intersection(ranked[:k])) / len(relevant)


def average_precision_at_k(ranked: Sequence[str], rel: Mapping[str, int], k: int) -> float:
    """AP@k normalised by ``min(|relevant|, k)``."""
    relevant = _relevant(rel)
    if not relevant:
        raise ValueError("AP is undefined without a relevant paragraph")
    hits, total = 0, 0.0
    for i, pid in enumerate(ranked[:k], start=1):
        if pid in relevant:
            hits += 1
            total += hits / i
    return total / min(len(relevant), k)


def ndcg_at_k(ranked: Sequence[str], rel: Mapping[str, int], k: int) -> float:
    grades = sorted((g for g in rel.values() if g > 0), reverse=True)
    if not grades:
        raise ValueError("nDCG is undefined without a relevant paragraph")
    dcg = sum((2 ** rel.get(pid, 0) - 1) / math.log2(i + 1) for i, pid in enumerate(ranked[:k], start=1))
    idcg = sum((2 ** g - 1) / math.log2(i + 1) for i, g in enumerate(grades[:k], start=1))
    return dcg / idcg


RANKING_METRICS = {"recall": recall_at_k, "map": average_precision_at_k, "ndcg": ndcg_at_k}


def per_query_scores(
    runs: Mapping[str, Sequence[str]], qrels: Mapping[str, Mapping[str, int]], k: int
) -> dict[str, dict[str, float]]:
    """``{metric: {query_id: value}}`` over the queries that have a relevant paragraph."""
    out: dict[str, dict[str, float]] = {m: {} for m in RANKING_METRICS}
    for qid, rel in qrels.items():
        if not _relevant(rel):
            continue
        ranked = runs.get(qid, [])
        for name, fn in RANKING_METRICS.items():
            out[name][qid] = fn(ranked, rel, k)
    return out


# -- bootstrap ----------------------------------------------------------------


def bootstrap_indices(n: int, *, resamples: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, n, size=(resamples, n))


def _cluster_draws(clusters: Sequence[Hashable], resamples: int, seed: int) -> list[np.ndarray]:
    keys = sorted(set(clusters), key=str)
    members = {c: np.array([i for i, x in enumerate(clusters) if x == c]) for c in keys}
    picks = np.random.default_rng(seed).integers(0, len(keys), size=(resamples, len(keys)))
    return [np.concatenate([members[keys[j]] for j in row]) for row in picks]


def _summary(point: float, draws: np.ndarray, n: int) -> dict[str, Any]:
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {"mean": float(point), "ci_low": float(lo), "ci_high": float(hi), "n": int(n)}


def bootstrap_mean(
    values: Sequence[float],
    *,
    resamples: int,
    seed: int,
    clusters: Sequence[Hashable] | None = None,
) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n == 0:
        return {"mean": None, "ci_low": None, "ci_high": None, "n": 0}
    if clusters is None:
        draws = arr[bootstrap_indices(n, resamples=resamples, seed=seed)].mean(axis=1)
    else:
        draws = np.array([arr[idx].mean() for idx in _cluster_draws(clusters, resamples, seed)])
    return _summary(arr.mean(), draws, n)


def paired_bootstrap(
    a: Sequence[float],
    b: Sequence[float],
    *,
    resamples: int,
    seed: int,
    clusters: Sequence[Hashable] | None = None,
) -> dict[str, Any]:
    """Mean of ``a - b`` over the same queries, with a CI from identical resamples."""
    diff = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    out = bootstrap_mean(diff, resamples=resamples, seed=seed, clusters=clusters)
    if out["n"]:
        if clusters is None:
            draws = diff[bootstrap_indices(len(diff), resamples=resamples, seed=seed)].mean(axis=1)
        else:
            draws = np.array([diff[idx].mean() for idx in _cluster_draws(clusters, resamples, seed)])
        out["share_of_resamples_above_zero"] = float((draws > 0).mean())
    return out


# -- classification -----------------------------------------------------------


def f1_scores(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> dict[str, Any]:
    """Per-label precision / recall / F1 and macro-F1 over ``labels``.

    A label with no gold and no predicted instance gets F1 = 0 and is still
    averaged in: macro-F1 is always over the stated label set.
    """
    per: dict[str, dict[str, float]] = {}
    for lab in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(gold, pred) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(gold, pred) if g == lab and p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return {"per_label": per, "macro_f1": sum(v["f1"] for v in per.values()) / len(labels)}


def macro_f1(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str]) -> float:
    return f1_scores(gold, pred, labels)["macro_f1"]


def confusion(gold: Sequence[str], pred: Sequence[str], gold_labels: Sequence[str],
              pred_labels: Sequence[str]) -> dict[str, dict[str, int]]:
    """``{gold: {pred: count}}``; prediction labels may differ from the gold set."""
    counts = Counter(zip(gold, pred))
    return {g: {p: counts.get((g, p), 0) for p in pred_labels} for g in gold_labels}


def bootstrap_statistic(
    n_units: int,
    statistic: Any,
    *,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Percentile CI for ``statistic(indices)`` evaluated on resampled unit indices."""
    point = statistic(np.arange(n_units))
    draws = np.array([statistic(idx) for idx in bootstrap_indices(n_units, resamples=resamples, seed=seed)])
    return _summary(point, draws, n_units)
