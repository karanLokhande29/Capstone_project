"""P3-001 relevance-set builders and the T1 harness, on hand-written fixtures (no RBI text)."""

from __future__ import annotations

import pytest

from src.eval import qrels as Q
from src.eval import t1_eval as T


def _item(n: int, flag: str, judgements: dict[str, str]) -> dict:
    return {
        "item_id": f"t1_md_{n}::p00001",
        "source_candidate_id": f"t1c_md_{n}::p00001",
        "paragraph_id": f"md_{n}::p00001",
        "entity_class": "Src",
        "obligation_span": {"text": f"obligation text {n}"},
        "compared_classes": sorted(judgements),
        "per_class_judgement": judgements,
        "matched_paragraph_id": {c: f"md_{c}::p{n:05d}" for c in judgements},
        "differential_flag": flag,
        "label_status": "validated",
    }


ITEMS = [
    _item(1, "shared", {"A": "same", "B": "same"}),
    _item(2, "class-specific", {"A": "different", "B": "none"}),
    _item(3, "absent", {"A": "none", "B": "none"}),
    _item(4, "shared", {"A": "same", "B": "none"}),
]


def test_t1_qrels_grades_and_none():
    qs = Q.build_t1(ITEMS)
    by_id = {q["query_id"]: q for q in qs}
    assert len(qs) == 8
    assert by_id["t1_md_1::p00001::A"]["relevant"] == {"md_A::p00001": 2}
    assert by_id["t1_md_2::p00001::A"]["relevant"] == {"md_A::p00002": 1}
    assert by_id["t1_md_2::p00001::B"]["relevant"] == {}  # none -> no relevant paragraph
    q = by_id["t1_md_1::p00001::B"]
    assert q["target_class"] == "B" and q["source_paragraph_id"] == "md_1::p00001"
    assert q["text"] == "obligation text 1" and q["cluster"] == "t1_md_1::p00001"
    s = Q.summarise(qs)
    assert s["queries_with_relevant"] == 4 and s["grade_counts"] == {"1": 1, "2": 3}


def test_t1_qrels_refuses_unvalidated_and_unknown_paragraphs():
    with pytest.raises(Q.QrelsError):
        Q.build_t1([{**ITEMS[0], "label_status": "candidate"}])
    with pytest.raises(Q.QrelsError):
        Q.build_t1(ITEMS[:1], paragraph_ids={"md_A::p00001"})


def test_p2002_qrels():
    key = {
        "P1": {"source_candidate_id": "t1c_md_1::p00001", "target_candidate_id": "t1c_md_2::p00003",
               "class_a": "A", "class_b": "B", "source_unit_offsets": [4, 13], "stratum": "high"},
        "P2": {"source_candidate_id": "t1c_md_1::p00002", "target_candidate_id": "t1c_md_3::p00001",
               "class_a": "A", "class_b": "C", "source_unit_offsets": [0, 5]},
        "P3": {"source_candidate_id": "t1c_md_1::p00002", "target_candidate_id": "t1c_md_4::p00001",
               "class_a": "A", "class_b": "D", "source_unit_offsets": [0, 5]},
    }
    sheet = [{"pair_id": "P1", "label": "same"}, {"pair_id": "P2", "label": "related"},
             {"pair_id": "P3", "label": "unrelated"}]
    text = {"md_1::p00001": "xxx shall do it now", "md_1::p00002": "other text"}
    qs = Q.build_p2002(key, sheet, text)
    assert [q["query_id"] for q in qs] == ["P1", "P2"]  # unrelated dropped
    assert qs[0]["text"] == "shall do " and qs[0]["relevant"] == {"md_2::p00003": 2}
    assert qs[0]["target_class"] == "B" and qs[0]["source_paragraph_id"] == "md_1::p00001"
    assert qs[1]["relevant"] == {"md_3::p00001": 1}
    with pytest.raises(Q.QrelsError):
        Q.build_p2002(key, sheet[:2], text)


def test_p2003_qrels():
    sheet = [
        {"item_id": "faq_1", "source": "faq", "item_text": "Topic: T\nQ: q?\nA: a.", "label": "paragraph",
         "paragraph_ids": "md_1::p00001"},
        {"item_id": "enf_1", "source": "enforcement", "label": "multi_paragraph", "paragraph_ids": "md_2::p1; md_2::p2",
         "item_text": "Title\nEntity: E [B]\nCharges sustained:\n- failed to do X;\n- failed to do Y."},
        {"item_id": "enf_2", "source": "enforcement", "label": "direction_only", "paragraph_ids": "",
         "item_text": "Title"},
        {"item_id": "enf_3", "source": "enforcement", "label": "paragraph", "paragraph_ids": "md_3::p1",
         "item_text": "Title\nCharges sustained:\n(none parsed)"},
    ]
    key = {"faq_1": {"entity_class": None}, "enf_1": {"entity_class": "B"}, "enf_2": {"entity_class": "B"},
           "enf_3": {"entity_class": "unresolved"}}
    qs = {q["query_id"]: q for q in Q.build_p2003(sheet, key)}
    assert set(qs) == {"faq_1", "enf_1", "enf_3"}
    assert qs["enf_1"]["text"] == "- failed to do X;\n- failed to do Y." and qs["enf_1"]["text_basis"] == "enforcement_charges"
    assert qs["enf_1"]["relevant"] == {"md_2::p1": 2, "md_2::p2": 2} and qs["enf_1"]["target_class"] == "B"
    assert qs["faq_1"]["target_class"] is None and qs["faq_1"]["text_basis"] == "faq_qa"
    assert qs["enf_3"]["target_class"] is None and qs["enf_3"]["text_basis"] == "enforcement_full_item_text"
    assert all(q["source_paragraph_id"] is None for q in qs.values())


def test_bias_is_stated_for_every_set():
    assert set(Q.BIAS) == {"t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"}


# -- T1 harness -------------------------------------------------------------------


CANDIDATES = {
    "t1c_md_1::p00001": {"per_class_candidate": {"A": "matched", "B": "matched", "Z": "matched"}},
    "t1c_md_2::p00001": {"per_class_candidate": {"A": "matched", "B": "below_threshold"}},
    "t1c_md_3::p00001": {"per_class_candidate": {"A": "below_threshold", "B": "below_threshold"}},
    "t1c_md_4::p00001": {"per_class_candidate": {"A": "below_threshold", "B": "below_threshold"}},
}


def test_majority_baseline_uses_the_validated_set():
    pred = T.majority_predictions(ITEMS)
    assert pred["rule"]["flag"] == "shared" and pred["flags"] == ["shared"] * 4
    assert pred["rule"]["judgement"] == "none"  # 4 none vs 3 same vs 1 different


def test_p2002_predictions_use_compared_classes_only():
    pred = T.p2002_predictions(ITEMS, CANDIDATES)
    assert pred["flags"] == ["shared_or_class_specific", "shared_or_class_specific", "absent", "absent"]
    assert pred["judgements"] == ["counterpart", "counterpart", "counterpart", "none", "none", "none", "none", "none"]
    with pytest.raises(T.T1EvalError):
        T.p2002_predictions(ITEMS, {**CANDIDATES, "t1c_md_4::p00001": {"per_class_candidate": {"A": "matched"}}})


def test_t1_harness_scores_all_views():
    out = T.run_baselines(ITEMS, CANDIDATES, resamples=200, seed=11)
    maj = out["baselines"]["majority"]
    # flag: majority "shared" -> F1 shared = 2*.5*1/1.5 = 2/3, others 0
    assert maj["three_label"]["flag"]["macro_f1"] == pytest.approx((2 / 3) / 3)
    p2 = out["baselines"]["p2002_candidates"]
    assert p2["fixed_mapping"]["mapping"] == {"shared_or_class_specific": "shared", "counterpart": "same"}
    # native collapsed flag: gold present,present,absent,present vs pred present,present,absent,absent
    nat = p2["native_collapsed"]["flag"]
    assert nat["accuracy"] == pytest.approx(0.75)
    assert nat["confusion"]["present"] == {"absent": 1, "present": 2}
    # oracle >= fixed mapping, always
    for task in ("flag", "judgement"):
        assert p2["oracle_upper_bound"][task]["macro_f1"] >= p2["fixed_mapping"][task]["macro_f1"]
    assert p2["confusion_raw"]["flag"]["class-specific"]["shared_or_class_specific"] == 1
    lo, hi = maj["three_label"]["judgement"]["macro_f1_ci"]
    assert lo <= maj["three_label"]["judgement"]["macro_f1"] <= hi


def test_t1_harness_is_deterministic():
    a = T.run_baselines(ITEMS, CANDIDATES, resamples=100, seed=3)
    b = T.run_baselines(ITEMS, CANDIDATES, resamples=100, seed=3)
    assert a == b
