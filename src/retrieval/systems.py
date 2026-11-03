"""The four P3-001 retrieval systems over one candidate mask per query.

* ``bm25`` and ``dense`` rank every allowed paragraph by their score.
* ``hybrid_rrf``: reciprocal-rank fusion, ``sum 1 / (k + rank)`` over the BM25
  and dense rankings (1-based ranks within the allowed set). A paragraph with
  BM25 score 0 shares no token with the query and gets no BM25 term.
* ``class_aware``: the same fusion, with BM25 and dense re-ranked inside the
  paragraphs whose Direction's entity class equals the query's target class.
  With no target class it is identical to ``hybrid_rrf`` and flagged.
* ``hybrid_minus_source_class`` (P3-002 diagnostic): the class-blind fusion
  with the paragraphs of the query's **own source class** removed, re-ranked
  inside what remains. It needs no target class, so it separates "stop
  returning the source Direction's own near-duplicates" from "know the target
  class". With no source class it is identical to ``hybrid_rrf`` and flagged.

The query's own source paragraph is always removed from the allowed set. Ties
break by corpus order (stable sort), so every run is reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

SYSTEMS = ("bm25", "dense", "hybrid_rrf", "class_aware", "hybrid_minus_source_class")


@dataclass
class Ranked:
    indices: np.ndarray  # corpus row numbers, best first
    scores: np.ndarray
    class_filter_applied: bool = False


def allowed_mask(n: int, *, exclude: int | None = None, entity_class: np.ndarray | None = None,
                 target_class: str | None = None, drop_class: str | None = None) -> np.ndarray:
    mask = np.ones(n, dtype=bool)
    if entity_class is not None and target_class is not None:
        mask &= entity_class == target_class
    if entity_class is not None and drop_class is not None:
        mask &= entity_class != drop_class
    if exclude is not None:
        mask[exclude] = False
    return mask


def top_k(scores: np.ndarray, mask: np.ndarray, k: int) -> Ranked:
    """Highest scores among allowed rows; ties go to the lower row number."""
    idx = np.flatnonzero(mask)
    order = np.argsort(-scores[idx], kind="stable")[:k]
    chosen = idx[order]
    return Ranked(chosen, scores[chosen])


def ranks_within(scores: np.ndarray, mask: np.ndarray, *, zero_is_unranked: bool = False) -> np.ndarray:
    """1-based rank of each allowed row (inf for disallowed or, optionally, zero-score rows)."""
    ranks = np.full(scores.shape[0], np.inf)
    eligible = mask & (scores > 0) if zero_is_unranked else mask
    idx = np.flatnonzero(eligible)
    order = idx[np.argsort(-scores[idx], kind="stable")]
    ranks[order] = np.arange(1, len(order) + 1)
    return ranks


def rrf_scores(rank_lists: list[np.ndarray], k: int) -> np.ndarray:
    total = np.zeros(rank_lists[0].shape[0])
    for ranks in rank_lists:
        total += np.where(np.isfinite(ranks), 1.0 / (k + ranks), 0.0)
    return total


def rrf(bm25: np.ndarray, dense: np.ndarray, mask: np.ndarray, *, k: int, depth: int) -> Ranked:
    fused = rrf_scores([ranks_within(bm25, mask, zero_is_unranked=True), ranks_within(dense, mask)], k)
    fused = np.where(mask, fused, -np.inf)
    return top_k(fused, mask, depth)


def run_query(bm25: np.ndarray, dense: np.ndarray, *, entity_class: np.ndarray, source_index: int | None,
              target_class: str | None, rrf_k: int, depth: int,
              source_class: str | None = None) -> Mapping[str, Ranked]:
    n = bm25.shape[0]
    blind = allowed_mask(n, exclude=source_index)
    out = {
        "bm25": top_k(bm25, blind, depth),
        "dense": top_k(dense, blind, depth),
        "hybrid_rrf": rrf(bm25, dense, blind, k=rrf_k, depth=depth),
    }
    if target_class is None:
        out["class_aware"] = Ranked(out["hybrid_rrf"].indices, out["hybrid_rrf"].scores, False)
    else:
        scoped = allowed_mask(n, exclude=source_index, entity_class=entity_class, target_class=target_class)
        ranked = rrf(bm25, dense, scoped, k=rrf_k, depth=depth)
        ranked.class_filter_applied = True
        out["class_aware"] = ranked
    if source_class is None:
        out["hybrid_minus_source_class"] = Ranked(out["hybrid_rrf"].indices, out["hybrid_rrf"].scores, False)
    else:
        scoped = allowed_mask(n, exclude=source_index, entity_class=entity_class, drop_class=source_class)
        ranked = rrf(bm25, dense, scoped, k=rrf_k, depth=depth)
        ranked.class_filter_applied = True
        out["hybrid_minus_source_class"] = ranked
    return out
