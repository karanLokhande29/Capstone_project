"""P4-001 Part B: T3 parser rules v2, T3/T4 metrics, paired bootstrap. No LLM, no RBI text."""

from __future__ import annotations

import numpy as np
import pytest

from src.rag import analysis as A
from src.t3 import parser as P

AMD = {
    "item_id": "amd_2", "published_date": "2025-12-11", "fields": {"linked_md_ids": ["md_1"]},
    "text": ("6. The provisions shall come into effect from December 15, 2025, except paragraph 7 (iii) (1), which "
             "shall be effective from December 12, 2025.\n"
             "7. These Amendment Directions modify the Directions as under:\n"
             "(i) In paragraph 31, the words 'each Friday' shall be substituted with 'each fortnight', the word 'seven' "
             "shall be substituted with 'five' and the word 'provisional' shall be deleted.\n"
             "(ii) The paragraph 34 shall be deleted.\n"
             "(iii) In paragraph 35, the words 'that Friday' shall be substituted with 'that day'.\n"),
}


def test_v2_merges_the_changes_of_one_item():
    actions, counts = P.parse_amendment(AMD)
    within = [a for a in actions if a.targets == ["31"]]
    assert len(within) == 1 and counts["merged_into_previous"] == 2
    a = within[0]
    assert a.action == "substitute" and [c["verb"] for c in a.changes] == ["substitute", "substitute", "delete"]
    # Known defect (frozen with the T3 set, reported): a merged change's recorded "old" words also pick up the
    # previous change's new words. Old words feed only the corpus-version check, where an extra entry can only
    # make a candidate "unclear" (excluded); it never changes an included item's gold.
    assert a.changes[1] == {"verb": "substitute", "old": ["each fortnight", "seven"], "new": ["five"]}
    assert a.changes[2]["old"] == ["five", "provisional"]  # same known defect


def test_v2_exception_date_applies_only_under_its_item():
    actions, _ = P.parse_amendment(AMD)
    by = {a.targets[0]: a for a in actions}
    assert P.effective_date(AMD, by["31"].start)["date"] == "2025-12-15"
    assert P.effective_date(AMD, by["34"].start)["date"] == "2025-12-15"
    # (iii)(1) is deeper than the item we can resolve: stays a window, never a guess
    e = P.effective_date(AMD, by["35"].start)
    assert e["date"] is None and e["window"] == ["2025-12-12", "2025-12-15"]
    assert P.item_path(AMD["text"], by["35"].start) == ("7", "iii")


def test_v2_ignores_dates_of_other_instruments():
    item = {"published_date": "2026-03-30",
            "text": ("These Directions shall come into force from the date a bank decides to implement the X Directions "
                     "dated March 30, 2026 or from July 1, 2026, whichever is earlier.")}
    e = P.effective_date(item)
    assert e["window"] == ["2026-03-30", "2026-07-01"] and e["basis"] == "earlier_of_date_or_adoption"


def test_supersession_f1():
    gold = ["md_1", "amd_1", "amd_2", "md_3"]
    pred = ["md_1", "amd_1", "md_2", "amd_9"]
    assert A.supersession_counts(gold, pred) == (1, 1, 1)  # tp amd_1; fp amd_9; fn amd_2
    assert A.supersession_f1(gold, pred) == pytest.approx(2 / 4)
    assert A.supersession_f1(["md_1"], ["md_1"]) == 0.0


def test_t3_metrics_by_side():
    items = [{"t3_id": "a", "gold_status": "in_force_original", "gold_governing_instrument": "md_1", "side": "before"},
             {"t3_id": "b", "gold_status": "amended", "gold_governing_instrument": "amd_1", "side": "after"}]
    pred = {"a": {"pred_status": "in_force_original", "pred_governing_instrument": "md_1"},
            "b": {"pred_status": "in_force_original", "pred_governing_instrument": "md_1"}}
    m = A.t3_metrics(items, pred, resamples=50, seed=1)
    assert m["status_exact_match"]["value"] == 0.5
    assert m["by_side"]["before"]["status_exact_match"] == 1.0 and m["by_side"]["after"]["status_exact_match"] == 0.0


def _log(can=True, abstained=False, supported=(True, False), declined=False, steps=1):
    sents = [{"text": "s", "citations": ["md_1::p00001"]} for _ in supported] if can else []
    return {"result": {"can_answer": can and not abstained, "abstained_by_verifier": abstained, "sentences": sents,
                       "supported": list(supported) if can else None},
            "steps": [{"can_answer": not declined}] * steps}


def test_t4_per_question_accounting():
    r = A.t4_per_question(_log())
    assert (r["delivered_sentences"], r["unsupported_sentences"], r["abstained_by_verifier"]) == (2, 1, False)
    ab = A.t4_per_question(_log(abstained=True, steps=2))
    assert ab["delivered_sentences"] == 0 and ab["unsupported_sentences"] == 0 and ab["retried"]
    dec = A.t4_per_question(_log(can=False, declined=True))
    assert dec["model_declined"] and dec["delivered_sentences"] == 0


def test_paired_reading_and_determinism():
    a = np.array([1.0, 1.0, 0.0, 1.0])
    b = np.array([0.0, 0.0, 0.0, 0.0])
    p = A.paired(4, lambda i: float(a[i].mean()), lambda i: float(b[i].mean()), resamples=300, seed=3)
    assert p["diff"] == 0.75 and p == A.paired(4, lambda i: float(a[i].mean()), lambda i: float(b[i].mean()),
                                               resamples=300, seed=3)
    same = A.paired(4, lambda i: float(a[i].mean()), lambda i: float(a[i].mean()), resamples=100, seed=3)
    assert same["reading"] == "does not exclude 0"
    assert p["reading"] == "excludes 0 (above)"


def test_t1_units_and_metrics_count_unsure_and_ambiguous_as_wrong():
    gold = [{"item_id": "i1", "differential_flag": "shared", "compared_classes": ["A"], "per_class_judgement": {"A": "same"}},
            {"item_id": "i2", "differential_flag": "absent", "compared_classes": ["A"], "per_class_judgement": {"A": "none"}}]
    pred = {"i1": {"flag": "ambiguous", "per_class": {"A": {"judgement": "unsure"}}},
            "i2": {"flag": "absent", "per_class": {"A": {"judgement": "none"}}}}
    u = A.t1_units(gold, pred)
    m = A.t1_metrics(u, resamples=50, seed=1)
    assert m["coverage"]["value"] == 0.5 and m["unsure_judgements"] == 1
    assert m["confusion"]["shared"]["ambiguous"] == 1


def test_ci_reading_rule_and_four_decimal_bounds():
    from src.eval.ci_format import ci_reading, fmt_ci

    assert ci_reading(0.01, 0.2) == "excludes 0 (above)"        # entirely above
    assert ci_reading(-0.132, -0.012) == "excludes 0 (below)"   # entirely below (the verifier's T1 effect)
    assert ci_reading(-0.2229, -0.0003) == "excludes 0 (below)"
    assert ci_reading(-0.1, 0.2) == "does not exclude 0"        # straddling
    assert ci_reading(0.0, 0.1132) == "does not exclude 0"      # lower bound exactly 0
    assert ci_reading(-0.3, 0.0) == "does not exclude 0"        # upper bound exactly 0
    assert fmt_ci(-0.1157, -0.2229, -0.0003, signed=True, reading=True) == "-0.116 [-0.223, -0.0003] (excludes 0 (below))"
    assert fmt_ci(0.092, 0.0, 0.204, signed=True) == "+0.092 [+0.0000, +0.204]"
    assert fmt_ci(0.5, 0.49, 0.51) == "0.500 [0.490, 0.510]"
