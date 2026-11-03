"""P3-002 Part A: sampling, answer transforms, RePASs payload, blind sheet, ingest validation. No LLM, no RBI text."""

from __future__ import annotations

import json
import random
from collections import Counter

import numpy as np
import pytest

from src.retrieval import systems as S
from src.t4 import audit as A


# -- sampling -----------------------------------------------------------------------


def _items(spec: dict[str, int]) -> list[dict]:
    out = []
    for c, n in spec.items():
        for i in range(n):
            out.append({"item_id": f"{c}-{i}", "entity_class": c, "subject_family": f"fam{i % 7}-{c}",
                        "label_status": "validated"})
    return out


def test_allocation_is_proportional_with_a_floor_of_one():
    alloc = A.allocate({"A": 50, "B": 30, "C": 2}, 10)
    assert sum(alloc.values()) == 10 and alloc["C"] >= 1 and alloc["A"] > alloc["B"]


def test_sample_is_stratified_seeded_and_meets_floors():
    items = _items({"A": 15, "B": 15, "C": 11, "D": 9, "E": 8, "F": 7, "G": 7})
    items.append({"item_id": "x", "entity_class": "A", "subject_family": "f", "label_status": "candidate"})
    chosen, log = A.sample_items(items, n=30, seed=5, min_classes=6, min_families=10)
    assert len(chosen) == 30 and log["classes"] >= 6 and log["families"] >= 10
    assert "x" not in {c["item_id"] for c in chosen}  # only validated items
    assert Counter(c["entity_class"] for c in chosen) == Counter(log["allocation"])
    again, _ = A.sample_items(items, n=30, seed=5, min_classes=6, min_families=10)
    assert [c["item_id"] for c in again] == [c["item_id"] for c in chosen]


def test_sample_refuses_when_floors_cannot_be_met():
    items = [{"item_id": f"i{k}", "entity_class": "A", "subject_family": "same", "label_status": "validated"}
             for k in range(40)]
    with pytest.raises(A.T4Error):
        A.sample_items(items, n=30, seed=1, min_classes=6, min_families=10, max_attempts=3)


# -- concatenation ------------------------------------------------------------------

P1 = "1. The entity shall keep records. It may delay. Board approval is required."
P2 = "2. A fee may be charged; the entity must disclose it. The entity shall keep records."


def _cand(pid: str, text: str, keep: list[bool]) -> dict:
    import re

    from src.benchmark.candidates import CUE_RE

    pos = [[m.start(), m.end()] for m in CUE_RE.finditer(text)]
    assert len(pos) == len(keep)
    return {"paragraph_id": pid, "span_text": text, "cue_position": pos,
            "cue_exclusions": [None if k else "definitional" for k in keep], "exclusion_reason": None}


def test_concatenation_takes_kept_cue_sentences_in_passage_order_once():
    cands = {"p1": _cand("p1", P1, [True]), "p2": _cand("p2", P2, [True, True])}
    out = A.concatenated_answer([("p2", P2), ("p1", P1)], cands)
    assert out == "the entity must disclose it. The entity shall keep records."


def test_concatenation_skips_excluded_cues_and_paragraphs_without_candidates():
    cands = {"p2": _cand("p2", P2, [False, True])}
    assert A.concatenated_answer([("p1", P1), ("p2", P2)], cands) == "The entity shall keep records."
    whole = {**_cand("p1", P1, [True]), "exclusion_reason": "excluded_boilerplate"}
    assert A.concatenated_answer([("p1", P1)], {"p1": whole}) == ""


def test_concatenation_refuses_a_text_mismatch():
    with pytest.raises(A.T4Error):
        A.kept_sentences("different text shall", _cand("p1", P1, [True]))


# -- negation ---------------------------------------------------------------------


@pytest.mark.parametrize("src,expected", [
    ("The bank shall report.", "The bank shall not report."),
    ("The bank shall not report.", "The bank shall report."),
    ("It must file. It must not lend.", "It must not file. It must lend."),
    ("It is required to file.", "It is not required to file."),
    ("They are not required to file.", "They are required to file."),
    ("Shall\nnot apply", "Shall apply"),
    ("marshall must", "marshall must not"),
])
def test_polarity_flip(src, expected):
    assert A.negate(src) == expected


def test_numbers_doubled():
    assert A.negate("within 30 days, 2.5 per cent, ₹1,500 crore, para 4") == \
        "within 60 days, 5.0 per cent, ₹3,000 crore, para 8"


# -- off-topic --------------------------------------------------------------------


def test_offtopic_excludes_the_source_family_and_matches_length():
    dirs = [{"md_id": "m1", "subject_family": "KYC", "sentences": ["kyc shall a.", "kyc shall b."]},
            {"md_id": "m2", "subject_family": "Audit", "sentences": ["audit shall a.", "audit shall b."]},
            {"md_id": "m3", "subject_family": None, "sentences": ["none shall."]},
            {"md_id": "m4", "subject_family": "Fraud", "sentences": ["fraud shall a."]}]
    for seed in range(20):
        text, used = A.offtopic_answer(20, source_family="KYC", directions=dirs, rng=random.Random(seed))
        assert "kyc" not in text and "none" not in text
        assert "m1" not in used and "m3" not in used
        assert len(text) >= 20 or set(used) == {"m2", "m4"}
    assert A.offtopic_answer(20, source_family="KYC", directions=dirs, rng=random.Random(3)) == \
        A.offtopic_answer(20, source_family="KYC", directions=dirs, rng=random.Random(3))
    with pytest.raises(A.T4Error):
        A.offtopic_answer(10, source_family="KYC", directions=dirs[:1], rng=random.Random(0))


# -- RePASs payload -----------------------------------------------------------------


def test_repass_payload_is_their_format():
    qs = {"Q1": {"passages": [{"paragraph_id": "p1", "text": "one"}, {"paragraph_id": "p2", "text": "two"}]}}
    payload = A.repass_payload([{"question_id": "Q1", "answer": "ans", "answer_type": "genuine"}], qs)
    assert payload == [{"QuestionID": "Q1", "RetrievedPassages": ["one", "two"], "Answer": "ans"}]
    assert json.loads(json.dumps(payload))[0].keys() == {"QuestionID", "RetrievedPassages", "Answer"}


# -- blind sheet ----------------------------------------------------------------------


def _sheet():
    qs = [{"question_id": f"Q{i:02d}", "question": f"question {i}?",
           "passages": [{"paragraph_id": f"p{i}", "text": f"text {i}"}]} for i in range(12)]
    answers = {t: {q["question_id"]: {"answer": f"{t}-answer-{q['question_id']}"} for q in qs} for t in A.ANSWER_TYPES}
    quotas = {"genuine": 4, "concatenated": 4, "adv_negated": 2, "adv_offtopic": 2}
    assignment = A.assign_sheet_types([q["question_id"] for q in qs], quotas, seed=1)
    rows, key = A.build_sheet(qs, answers, assignment, order_seed=2, block_size=4)
    return qs, answers, assignment, rows, key


def test_sheet_assignment_covers_each_question_once_with_the_quotas():
    _, _, assignment, rows, key = _sheet()
    assert Counter(assignment.values()) == {"genuine": 4, "concatenated": 4, "adv_negated": 2, "adv_offtopic": 2}
    assert len({k["question_id"] for k in key.values()}) == len(rows) == 12
    assert [r["block"] for r in rows] == ["1"] * 4 + ["2"] * 4 + ["3"] * 4


def test_sheet_hides_type_scores_and_model():
    _, _, _, rows, key = _sheet()
    A.assert_blind(rows)
    for r in rows:
        assert list(r) == list(A.SHEET_COLUMNS)
        assert not any(k in r for k in ("answer_type", "score", "composite_score", "model", "question_id"))
        assert key[r["row_id"]]["answer_type"] in A.ANSWER_TYPES
    text = A.sheet_csv(rows)
    assert text.startswith('"# T4 faithfulness sheet')
    assert "composite" not in text and "gpt" not in text and "gemini" not in text
    with pytest.raises(A.T4Error):
        A.assert_blind([{**rows[0], "row_id": "genuine-1"}])
    with pytest.raises(A.T4Error):
        A.assert_blind([{**rows[0], "faithful": "2"}])


def test_sheet_order_is_seeded():
    assert _sheet()[3] == _sheet()[3]


# -- ingest validation ------------------------------------------------------------------


def _filled(rows, **overrides):
    out = []
    for r in rows:
        f = {**r, "faithful": "2", "answers_question": "1", "bad_question": ""}
        f.update(overrides.get(r["row_id"], {}))
        out.append(f)
    return out


def test_completed_sheet_roundtrip_with_bom_and_quoted_note():
    _, _, _, rows, _ = _sheet()
    text = "﻿" + A.sheet_csv(_filled(rows))
    parsed = A.read_sheet_text(text.encode("utf-8").decode("utf-8-sig"))
    assert A.validate_completed(parsed, rows) == []


def test_validation_catches_vocab_blanks_edits_and_ids():
    _, _, _, rows, _ = _sheet()
    bad = _filled(rows, F01={"faithful": "3"}, F02={"answers_question": ""}, F03={"answer": "edited"},
                  F04={"bad_question": "maybe"})
    problems = "\n".join(A.validate_completed(bad[:-1], rows))
    assert "F01: faithful '3'" in problems
    assert "F02: answers_question is blank" in problems
    assert "F03: column answer was edited" in problems
    assert "F04: bad_question" in problems
    assert "row ids differ" in problems


# -- P3-001 follow-up: hybrid_minus_source_class ---------------------------------------------


def test_hybrid_minus_source_class_drops_the_source_class_only():
    classes = np.array(["A", "A", "B", "C", "A"], dtype=object)
    bm25 = np.array([5.0, 4.0, 1.0, 2.0, 3.0])
    dense = np.array([0.9, 0.8, 0.1, 0.5, 0.7])
    out = S.run_query(bm25, dense, entity_class=classes, source_index=0, target_class="B", rrf_k=60, depth=5,
                      source_class="A")
    r = out["hybrid_minus_source_class"]
    assert set(r.indices) == {2, 3} and r.class_filter_applied
    assert list(out["class_aware"].indices) == [2]
    none = S.run_query(bm25, dense, entity_class=classes, source_index=0, target_class=None, rrf_k=60, depth=5)
    assert list(none["hybrid_minus_source_class"].indices) == list(none["hybrid_rrf"].indices)
    assert not none["hybrid_minus_source_class"].class_filter_applied
