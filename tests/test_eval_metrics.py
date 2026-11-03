"""P3-001 ranking metrics, bootstrap and F1, against hand-computed values."""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.eval import metrics as M

RANKED = ["a", "x", "b", "y", "c"]


def test_recall_at_k():
    rel = {"a": 2, "b": 1, "z": 2}
    assert M.recall_at_k(RANKED, rel, 3) == pytest.approx(2 / 3)
    assert M.recall_at_k(RANKED, rel, 1) == pytest.approx(1 / 3)
    assert M.recall_at_k(RANKED, {"a": 0, "b": 1}, 10) == 1.0  # grade 0 is not relevant


def test_average_precision_at_k():
    # hits at ranks 1 and 3: (1/1 + 2/3) / min(3, 5) = 0.5556
    rel = {"a": 2, "b": 1, "z": 2}
    assert M.average_precision_at_k(RANKED, rel, 5) == pytest.approx((1 + 2 / 3) / 3)
    # cutoff 2: only rank 1 counts; normaliser min(3, 2) = 2
    assert M.average_precision_at_k(RANKED, rel, 2) == pytest.approx(1 / 2)


def test_ndcg_graded():
    rel = {"b": 2, "a": 1}
    # DCG = (2^1-1)/log2(2) + (2^2-1)/log2(4) = 1 + 1.5 = 2.5 ; IDCG = 3/1 + 1/log2(3)
    idcg = 3 + 1 / math.log2(3)
    assert M.ndcg_at_k(RANKED, rel, 10) == pytest.approx(2.5 / idcg)
    assert M.ndcg_at_k(["b", "a"], rel, 10) == pytest.approx(1.0)
    assert M.ndcg_at_k(["q"], rel, 10) == 0.0


def test_undefined_without_relevant():
    for fn in M.RANKING_METRICS.values():
        with pytest.raises(ValueError):
            fn(RANKED, {"a": 0}, 10)


def test_per_query_scores_skips_queries_without_relevant():
    out = M.per_query_scores({"q1": ["a"], "q2": ["b"]}, {"q1": {"a": 2}, "q2": {}}, 10)
    assert out["recall"] == {"q1": 1.0}


def test_bootstrap_is_deterministic_and_seeded():
    vals = [0.0, 1.0, 0.5, 0.25, 1.0, 0.0]
    a = M.bootstrap_mean(vals, resamples=500, seed=7)
    b = M.bootstrap_mean(vals, resamples=500, seed=7)
    c = M.bootstrap_mean(vals, resamples=500, seed=8)
    assert a == b
    assert a != c
    assert a["mean"] == pytest.approx(np.mean(vals)) and a["n"] == 6
    assert a["ci_low"] <= a["mean"] <= a["ci_high"]


def test_constant_values_have_a_degenerate_ci():
    out = M.bootstrap_mean([0.4] * 9, resamples=200, seed=1)
    assert out["ci_low"] == pytest.approx(0.4) and out["ci_high"] == pytest.approx(0.4)


def test_paired_bootstrap_uses_the_same_draws():
    a = [1.0, 0.0, 1.0, 1.0]
    b = [0.0, 0.0, 1.0, 0.0]
    out = M.paired_bootstrap(a, b, resamples=300, seed=3)
    assert out["mean"] == pytest.approx(0.5)
    idx = M.bootstrap_indices(4, resamples=300, seed=3)
    diff = (np.array(a) - np.array(b))[idx].mean(axis=1)
    assert out["ci_low"] == pytest.approx(np.percentile(diff, 2.5))
    assert out["share_of_resamples_above_zero"] == pytest.approx((diff > 0).mean())


def test_cluster_bootstrap_resamples_whole_clusters():
    vals = [1.0, 1.0, 0.0, 0.0]
    out = M.bootstrap_mean(vals, resamples=200, seed=5, clusters=["x", "x", "y", "y"])
    # Each resample holds whole clusters, so every draw mean is 0, 0.5 or 1.
    assert out["ci_low"] in (0.0, 0.5) and out["ci_high"] in (0.5, 1.0)
    assert out == M.bootstrap_mean(vals, resamples=200, seed=5, clusters=["x", "x", "y", "y"])


def test_f1_and_confusion():
    gold = ["a", "a", "b", "c"]
    pred = ["a", "b", "b", "b"]
    s = M.f1_scores(gold, pred, ("a", "b", "c"))
    assert s["per_label"]["a"]["f1"] == pytest.approx(2 / 3)  # p=1, r=.5
    assert s["per_label"]["b"]["f1"] == pytest.approx(0.5)  # p=1/3, r=1
    assert s["per_label"]["c"]["f1"] == 0.0
    assert s["macro_f1"] == pytest.approx((2 / 3 + 0.5) / 3)
    conf = M.confusion(gold, pred, ("a", "b", "c"), ("a", "b", "c"))
    assert conf["a"] == {"a": 1, "b": 1, "c": 0} and conf["c"]["b"] == 1
