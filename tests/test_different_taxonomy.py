"""P1: `different` error taxonomy tooling and the retrieval/reasoning separator (fixtures only)."""

from __future__ import annotations

from src.eval import different_taxonomy as DT

SRC = "The bank shall report the incident to RBI within 6 hours and maintain a record."
TGT_PCT = "The NBFC shall maintain a minimum CRAR of 15 per cent and report to RBI within 6 hours, maintain a record."


def test_candidate_categories_are_cue_differences():
    cats = DT.candidate_categories(SRC, TGT_PCT)
    assert "percentages" in cats and "thresholds" in cats and "deadlines" not in cats
    assert DT.candidate_categories("The bank shall act.", "The bank shall act.") == ["similar wording, different legal effect"]
    assert "prohibition vs permission" in DT.candidate_categories("The bank shall not lend.", "The bank may lend.")
    assert set(DT.CUES) <= set(DT.CATEGORIES)


def test_error_types():
    assert DT.error_type("different") is None
    assert DT.error_type("same") == "different→same" and DT.error_type("none") == "different→none"
    assert DT.error_type(None) == DT.error_type("unsure") == "different→unsure/missing"


def test_context_ids_union_over_attempts_and_class_blind():
    steps = [{"shown": {"CB": ["md_1::p00001"]}}, {"shown": {"*": ["md_2::p00001"], "SFB": ["md_3::p00001"]}}]
    assert DT.context_ids_rag(steps, "CB") == {"md_1::p00001", "md_2::p00001"}


def test_analyse_separates_retrieval_from_reasoning_and_missed_by_all():
    gold = [{"item_id": "a", "compared_classes": ["CB", "SFB"], "per_class_judgement": {"CB": "different", "SFB": "same"},
             "matched_paragraph_id": {"CB": "md_1::p00001", "SFB": "md_2::p00001"}, "obligation_span": {"text": SRC}},
            {"item_id": "b", "compared_classes": ["CB"], "per_class_judgement": {"CB": "different"},
             "matched_paragraph_id": {"CB": "md_9::p00001"}, "obligation_span": {"text": SRC}}]
    units = DT.different_units(gold)
    assert [(u["item_id"], u["target_class"]) for u in units] == [("a", "CB"), ("b", "CB")]
    rec = lambda j, shown: {"final": {"per_class": {"CB": {"judgement": j}}}, "steps": [{"shown": {"CB": shown}}]}
    runs = {"s1": {"a": rec("same", ["md_1::p00001"]), "b": rec("different", [])},
            "s2": {"a": rec("none", []), "b": rec("none", ["md_9::p00001"])},
            "lc": {"a": rec("same", [])}}

    def in_ctx(system, u):
        return u["gold_matched"] in DT.context_ids_rag(u["record"]["steps"], u["target_class"])

    out = DT.analyse(units, runs, in_ctx, lambda pid: TGT_PCT)
    a, b = out["units"]
    assert a["by_system"]["s1"]["failure"] == "reasoning" and a["by_system"]["s2"]["failure"] == "retrieval"
    assert a["missed_by_every_system"] and not b["missed_by_every_system"]
    assert b["by_system"]["lc"]["error"] == "no prediction"
    assert out["per_system"]["s2"]["error_types"] == {"different→none": 2}
    assert out["missed_by_every_system"] == 1 and a["final_category"] == ""
