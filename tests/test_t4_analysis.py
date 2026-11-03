"""P3-002 Part B: verdict logic at the CI boundaries, bootstrap, LCS repair, Spearman, minutes, mocked LLM prompts."""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

from src.eval.metrics import paired_bootstrap
from src.llm import client as L
from src.t4 import analysis as N

ROOT = Path(__file__).resolve().parents[1]


def _run_t4():
    spec = importlib.util.spec_from_file_location("run_t4", ROOT / "scripts" / "run_t4.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# -- verdicts at the CI boundaries --------------------------------------------------


@pytest.mark.parametrize("lo,hi,expected", [
    (0.0, 0.3, "reproduces"),            # entirely at or above 0: the boundary counts
    (0.01, 0.3, "reproduces"),
    (-0.3, -0.0001, "does not reproduce"),
    (-0.3, 0.0, "inconclusive at n = 30"),  # touches 0 from below: not entirely below
    (-0.1, 0.1, "inconclusive at n = 30"),
])
def test_verdict_boundaries(lo, hi, expected):
    assert N.verdict(lo, hi, 30) == expected


@pytest.mark.parametrize("lo,hi,expected", [
    (0.0001, 0.2, "genuine ranked above"),
    (0.0, 0.2, "inconclusive at n = 28"),
    (-0.2, -0.01, "genuine ranked below"),
])
def test_ranking_verdict_boundaries(lo, hi, expected):
    assert N.ranking_verdict(lo, hi, 28) == expected


def test_verdict_from_a_seeded_paired_bootstrap():
    rng = np.random.default_rng(0)
    genuine = rng.uniform(0.2, 0.5, 30)
    concat = genuine + 0.3
    out = paired_bootstrap(concat, genuine, resamples=2000, seed=20261007)
    assert out == paired_bootstrap(concat, genuine, resamples=2000, seed=20261007)  # deterministic
    assert N.verdict(out["ci_low"], out["ci_high"], 30) == "reproduces"
    same = paired_bootstrap(genuine, genuine, resamples=500, seed=1)
    # identical scores: CI is exactly [0, 0], which the rule reads as "reproduces" (at or above 0)
    assert same["ci_low"] == 0 and same["ci_high"] == 0
    assert N.verdict(same["ci_low"], same["ci_high"], 30) == "reproduces"


# -- repair -----------------------------------------------------------------------------


def test_lcs_hand_computed():
    assert N.lcs_length(list("ABCBDAB"), list("BDCABA")) == 4
    assert N.lcs_length([], ["a"]) == 0


def test_lcs_ratio_verbatim_and_paraphrase():
    passages = ["The bank shall report lapses within two months.", "Other text."]
    assert N.lcs_ratio("The bank shall report lapses within two months.", passages) == 1.0
    # tokens: report within two months md 1 p00001 (7); LCS = report within two months (4)
    assert N.lcs_ratio("Report within two months [md_1::p00001].", passages) == pytest.approx(4 / 7)
    assert N.lcs_ratio("", passages) == 0.0


def test_penalty_and_repaired_score():
    assert N.overlap_penalty(0.8, 0.8) == 0.0
    assert N.overlap_penalty(0.9, 0.8) == pytest.approx(0.5)
    assert N.overlap_penalty(1.0, 0.8) == 1.0
    assert N.overlap_penalty(0.2, 0.8) == 0.0
    with pytest.raises(ValueError):
        N.overlap_penalty(0.5, 1.0)
    assert N.repaired_score(0.6, 0.2, 0.0) == pytest.approx(0.4)
    assert N.repaired_score(0.9, 0.9, 1.0) == 0.0


# -- Spearman -----------------------------------------------------------------------------


def test_spearman_matches_scipy_with_ties():
    from scipy.stats import spearmanr

    x = [0.1, 0.4, 0.4, 0.9, 0.3, 0.7]
    y = [0, 2, 1, 2, 0, 2]
    assert N.spearman(x, y) == pytest.approx(spearmanr(x, y).statistic)
    assert N.spearman([1, 1, 1], [0, 1, 2]) is None


def test_spearman_bootstrap_is_deterministic_and_counts_degenerate_draws():
    x = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    y = [0, 0, 1, 1, 2, 2]
    a = N.spearman_bootstrap(x, y, resamples=300, seed=4)
    assert a == N.spearman_bootstrap(x, y, resamples=300, seed=4)
    assert a["rho"] == pytest.approx(N.spearman(x, y)) and a["n"] == 6
    assert a["ci_low"] <= a["rho"] <= a["ci_high"] and a["degenerate_resamples"] >= 0


# -- minutes log ---------------------------------------------------------------------------


def test_minutes_log_parsing_and_rejection(tmp_path):
    mod = _run_t4()
    good = tmp_path / "m.csv"
    good.write_text("﻿block,started_at,ended_at\n1,2026-09-28 00:38,2026-09-28 01:03\n"
                    "2,2026-09-28 01:03,2026-09-28 01:28\n3,2026-09-28 01:28,2026-09-28 01:53\n", encoding="utf-8")
    rows = mod._read_minutes(good)
    assert [r["minutes"] for r in rows] == [25.0, 25.0, 25.0]
    bad = tmp_path / "b.csv"
    bad.write_text("block,started_at,ended_at\n1,2026-09-28 01:00,2026-09-28 00:50\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod._read_minutes(bad)
    short = tmp_path / "s.csv"
    short.write_text("block,started_at,ended_at\n1,2026-09-28 00:38,2026-09-28 01:03\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod._read_minutes(short)


# -- the LLM steps, with the LLM mocked ------------------------------------------------------


class _Fake:
    name = "groq"

    def __init__(self):
        self.seen = []

    def list_models(self):
        return []

    def generate(self, model, messages, params):
        self.seen.append(messages)
        return L.Completion(text="What must the bank report?", provider="groq", model=model, model_version="v",
                            input_tokens=1, output_tokens=1)


def test_question_and_genuine_prompts_through_a_mocked_client(tmp_path):
    mod = _run_t4()
    fake = _Fake()
    client = L.LLMClient([L.ProviderSlot(fake, {"default": "m"}, rpm=100, tpm=10**6)], cache_dir=tmp_path,
                         max_calls=5, sleep=lambda s: None)
    item = {"entity_class": "Payments Banks", "paragraph_id": "md_1::p00002"}
    q = client.complete(mod.question_messages(item, "The bank\n shall   report.", "A Direction"))
    assert q.text.endswith("?") and fake.seen[0][0]["role"] == "system"
    user = fake.seen[0][1]["content"]
    assert "Payments Banks" in user and "[md_1::p00002]" in user and "The bank shall report." in user
    g = mod.genuine_messages({"question": "Q?", "passages": [{"paragraph_id": "md_1::p00002", "text": "T"}]})
    assert "ONLY the passages" in g[0]["content"] and "[md_1::p00002] T" in g[1]["content"]
    client.complete(g)
    assert client.run.provider == "groq" and client.run.http_attempts == 2
    assert not math.isnan(client.run.summary()["input_tokens"])
