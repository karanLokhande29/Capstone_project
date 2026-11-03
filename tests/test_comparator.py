"""P1: pairwise structured comparator with a mocked LLM (no API)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.rag import comparator as CMP
from src.rag import comparator_rule as RULE

REPO = Path(__file__).resolve().parents[1]
PROMPTS = REPO / "configs" / "comparator_v1"


def cand(pid, same_duty=True, **over):
    fc = {f: "absent" for f in RULE.FIELDS}
    fc.update(action="equal", object="equal")
    fc.update(over)
    return {"paragraph_id": pid, "addresses_same_duty": same_duty, "field_comparison": fc, "fields": {}}


def test_rule_per_candidate_and_precedence():
    assert RULE.candidate_verdict(cand("a")) == "same"
    assert RULE.candidate_verdict(cand("a", same_duty=False, deadline="differs")) == "none"
    assert RULE.candidate_verdict(cand("a", deadline="differs")) == "different"
    assert RULE.candidate_verdict(cand("a", reporting="only_target")) == "different"
    assert RULE.candidate_verdict(cand("a", object="only_source")) == "same"  # not a material field
    v = RULE.class_verdict([cand("d", threshold="differs"), cand("s")])
    assert v["judgement"] == "same" and v["matched_paragraph_id"] == "s"
    v = RULE.class_verdict([cand("n", same_duty=False), cand("d", amount="differs")])
    assert v["judgement"] == "different" and v["matched_paragraph_id"] == "d"
    v = RULE.class_verdict([cand("n", same_duty=False)])
    assert v["judgement"] == "none" and v["matched_paragraph_id"] is None


def test_parse_candidates_cell():
    cell = "[md_00010::p00001] First para\ntext.\n\n[md_00020::p00002] Second."
    assert CMP.parse_candidates(cell) == [("md_00010::p00001", "First para\ntext."), ("md_00020::p00002", "Second.")]


def test_parse_response_validates_ids_and_vocabulary():
    good = json.dumps({"source": {}, "candidates": [cand("md_1::p00001"), cand("md_2::p00002")]})
    out, probs = CMP.parse_response("```json\n" + good + "\n```", ["md_1::p00001", "md_2::p00002"])
    assert probs == [] and len(out) == 2
    out, probs = CMP.parse_response(good, ["md_1::p00001", "md_3::p00003"])
    assert out is None and "missing" in probs[0]
    bad = cand("md_1::p00001", deadline="bigger")
    out, probs = CMP.parse_response(json.dumps({"candidates": [bad]}), ["md_1::p00001"])
    assert out is None and "deadline" in probs[0]
    assert CMP.parse_response("not json", ["x"])[0] is None


@dataclass
class FakeCompletion:
    text: str
    cached: bool = False
    model: str = "gemini-3.5-flash-lite"
    model_version: str = "fake"


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, messages, *, max_output_tokens=None, role="default"):
        self.calls.append(messages)
        return FakeCompletion(self.replies.pop(0))


def test_compare_unit_with_mock_and_evaluate():
    prompts = CMP.Prompts(PROMPTS)
    u = {"item_id": "x1", "source_class": "Commercial Banks", "source_text": "OBLIGATION: report within 7 days",
         "target_class": "Small Finance Banks", "candidates": [("md_1::p00001", "A"), ("md_2::p00002", "B")]}
    llm = FakeLLM([json.dumps({"candidates": [cand("md_1::p00001", same_duty=False), cand("md_2::p00002", deadline="differs")]}),
                   "garbage"])
    r = CMP.compare_unit(llm, prompts, u, max_output_tokens=100)
    assert r["judgement"] == "different" and r["matched_paragraph_id"] == "md_2::p00002"
    user = llm.calls[0][1]["content"]
    assert "Small Finance Banks" in user and "[md_2::p00002] B" in user and "{" not in user.split("CANDIDATE")[0][-5:]
    r2 = CMP.compare_unit(llm, prompts, {**u, "item_id": "x2"}, max_output_tokens=100)
    assert r2["judgement"] == "unsure" and r2["parse_problems"]
    m = CMP.evaluate([r, r2], {("x1", "Small Finance Banks"): "different", ("x2", "Small Finance Banks"): "same"})
    assert m["n_units"] == 2 and m["different_recall"] == 1.0 and m["unsure"] == 1 and m["parse_failures"] == 1


def test_frozen_hash_check_refuses_changes(tmp_path):
    for f in CMP.PROMPT_FILES:
        (tmp_path / f).write_text((PROMPTS / f).read_text())
    h = CMP.frozen_hashes(tmp_path)
    CMP.Prompts(tmp_path, expected=h)
    (tmp_path / "comparator_user.txt").write_text("changed")
    with pytest.raises(CMP.ComparatorError, match="changed"):
        CMP.Prompts(tmp_path, expected=h)
