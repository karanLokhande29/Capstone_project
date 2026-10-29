"""V2 milestone 2: the V2-A decision rule (alignment override of V1), dev scoring and the gated runner. No API calls.

The paragraphs and V1 answers here are fabricated (tests/fixtures/v2/alignment_examples.json plus hand-built V1 JSON).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import run_v2 as RV
from src.rag import comparator_rule as RULE
from src.rag.v2 import decision_v2 as D
from src.rag.v2 import eval_v2 as E
from src.rag.v2 import topic_aligner as TA

REPO = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((REPO / "tests/fixtures/v2/alignment_examples.json").read_text(encoding="utf-8"))["cases"]
CASE = "same_duty_different_deadline"
C1, C2 = "md_90002::p00020", "md_90002::p00021"
HAVE_DEV = (REPO / "data/rag_runs/comparator_dev_irr30").exists() and (REPO / "data/benchmark/t1").exists()


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


def unit(case=CASE):
    u = copy.deepcopy(FIXTURES[case]["unit"])
    u["candidates"] = [tuple(c) for c in u["candidates"]]
    return u


def fields(**diff):
    fc = {f: "equal" if f in ("actor", "action", "object") else "absent" for f in RULE.FIELDS}
    fc.update(diff)
    return fc


def v1_record(duties, fcs=None, u=None, raw=None):
    """A V1 comparator record whose stored judgement follows from its raw answer, as in the sealed runs."""
    u = u or unit()
    ids = [p for p, _ in u["candidates"]]
    fcs = fcs or [fields(deadline="differs"), fields()]
    cands = [{"paragraph_id": p, "addresses_same_duty": d, "field_comparison": fc} for p, d, fc in zip(ids, duties, fcs)]
    v = RULE.class_verdict(cands)
    return {"item_id": u["item_id"], "target_class": u["target_class"], "judgement": v["judgement"],
            "matched_paragraph_id": v["matched_paragraph_id"], "per_candidate": v["per_candidate"],
            "rule": RULE.RULE_VERSION, "parse_problems": [],
            "raw": json.dumps({"candidates": cands}) if raw is None else raw}


def aligned(labels_by_id=None, u=None):
    """An aligner record from the fixture reply, with the final labels optionally overridden."""
    u = u or unit()
    rec = TA.align_unit(FakeLLM([json.dumps(FIXTURES[CASE]["reply"])]), TA.Prompts(), u, max_output_tokens=800)
    for a in rec["alignments"]:
        if labels_by_id and a["candidate_id"] in labels_by_id:
            a["same_underlying_duty"] = labels_by_id[a["candidate_id"]]
    return rec


def ids():
    return [C1, C2]


# -- the rule ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("label,v1,expected", [
    ("yes", False, (True, "aligner")), ("no", True, (False, "aligner")),
    ("uncertain", True, (True, "v1")), ("uncertain", False, (False, "v1")), (None, True, (True, "v1")),
])
def test_duty_flag(label, v1, expected):
    assert D.duty_flag(label, v1) == expected


def test_aligner_yes_turns_a_v1_none_into_different():
    # V1 missed the duty match; the fields already show the deadline differs. This is the targeted failure.
    r1 = v1_record([False, False])
    assert r1["judgement"] == "none"
    out = D.decide_a(r1, aligned(), ids())
    assert out["judgement"] == "different" and out["matched_paragraph_id"] == C1 and out["changed"] is True
    t = {x["candidate_id"]: x for x in out["trace"]}
    assert t[C1]["duty_source"] == "aligner" and t[C1]["v1_verdict"] == "none" and t[C1]["v2_verdict"] == "different"
    assert t[C2]["duty"] is False and t[C2]["v2_verdict"] == "none"
    assert out["rule"] == D.RULE_VERSION and out["v1_rule"] == RULE.RULE_VERSION and out["v1_judgement"] == "none"


def test_aligner_no_overrides_a_v1_match():
    r1 = v1_record([True, True], [fields(), fields()])
    assert r1["judgement"] == "same"
    out = D.decide_a(r1, aligned({C1: "no", C2: "no"}), ids())
    assert out["judgement"] == "none" and out["matched_paragraph_id"] is None


def test_uncertain_and_missing_alignment_keep_v1():
    r1 = v1_record([False, True], [fields(deadline="differs"), fields()])
    for a in (aligned({C1: "uncertain", C2: "uncertain"}), None,
              {**aligned(), "alignments": []}):
        out = D.decide_a(r1, a, ids())
        assert (out["judgement"], out["matched_paragraph_id"], out["changed"]) == ("same", C2, False)
        assert {t["duty_source"] for t in out["trace"]} == {"v1"}


def test_v1_precedence_still_applies():
    # Aligner says yes to both; candidate 2 has equal fields, so same beats different, as in V1.
    out = D.decide_a(v1_record([False, False]), aligned({C1: "yes", C2: "yes"}), ids())
    assert out["judgement"] == "same" and out["matched_paragraph_id"] == C2


def test_unparsed_v1_stays_unsure():
    r1 = {**v1_record([True, True]), "raw": "not json", "judgement": "unsure", "matched_paragraph_id": None,
          "per_candidate": [], "parse_problems": ["not JSON"]}
    out = D.decide_a(r1, aligned(), ids())
    assert out["judgement"] == "unsure" and out["changed"] is False and out["trace"] == []


def test_tampered_v1_record_or_wrong_unit_is_refused():
    r1 = {**v1_record([False, False]), "judgement": "same"}
    with pytest.raises(D.DecisionError, match="stored 'same'"):
        D.decide_a(r1, aligned(), ids())
    with pytest.raises(D.DecisionError, match="is not for unit"):
        D.decide_a(v1_record([False, False]), {**aligned(), "target_class": "Payments Banks"}, ids())


# -- scoring ----------------------------------------------------------------------------------------------------------


def test_flips_and_none_precision():
    gold = {("a", "X"): "different", ("b", "X"): "none", ("c", "X"): "same", ("d", "X"): "same"}
    v1 = [{"item_id": k[0], "target_class": k[1], "judgement": j, "parse_problems": []}
          for k, j in zip(gold, ("none", "none", "different", "same"))]
    v2 = [{**r, "judgement": j} for r, j in zip(v1, ("different", "different", "none", "same"))]
    f = E.flips(v1, v2, gold)
    assert (f["changed"], f["fixed"], f["broken"], f["other"]) == (3, 1, 1, 1)
    assert f["moves"] == {"none->different": 2, "different->none": 1}
    assert E.score(v1, gold)["none_precision"] == 0.5 and E.score(v2, gold)["none_precision"] == 0.0


# -- the runner (no API) ----------------------------------------------------------------------------------------------


def test_dev_refuses_without_gate_frozen_or_too_many_runs(tmp_path, monkeypatch, capsys):
    assert RV.cmd_dev(None) == 1 and RV.cmd_dev("gate: comparator dev run") == 1
    frozen = tmp_path / "FROZEN.json"
    frozen.write_text("{}")
    monkeypatch.setattr(RV, "FROZEN", frozen)
    assert RV.cmd_dev(RV.GATE) == 1 and "frozen" in capsys.readouterr().out
    monkeypatch.setattr(RV, "FROZEN", tmp_path / "absent.json")
    monkeypatch.setattr(RV, "V2_RUNS", tmp_path)
    for tag in ("aaaaaaaa", "bbbbbbbb"):
        (tmp_path / f"alignment_dev_irr30_{tag}").mkdir()
        (tmp_path / f"alignment_dev_irr30_{tag}" / "x.json").write_text("{}")
    assert RV.cmd_dev(RV.GATE) == 1 and "no further revisions" in capsys.readouterr().out


def test_prompt_tag_follows_the_prompt_hashes():
    h = TA.frozen_hashes()
    assert RV.prompt_tag(h) == RV.prompt_tag() and len(RV.prompt_tag()) == 8
    assert RV.prompt_tag({**h, "topic_alignment_system.txt": "0" * 64}) != RV.prompt_tag(h)


def test_evaluate_dev_end_to_end_on_fixtures(tmp_path):
    u = unit()
    v1_dir, run = tmp_path / "v1", tmp_path / "run"
    v1_dir.mkdir()
    run.mkdir()
    (v1_dir / RV.unit_path(u, v1_dir).name).write_text(json.dumps(v1_record([False, False])))
    RV.unit_path(u, run).write_text(json.dumps(aligned()))
    m = RV.evaluate_dev(run, [u], {(u["item_id"], u["target_class"]): "different"}, v1_dir=v1_dir)
    assert m["n_units"] == 1 and m["missing"] == 0
    assert m["flips"]["fixed"] == 1 and m["flips"]["moves"] == {"none->different": 1}
    assert m["v1"]["confusion"]["different"]["none"] == 1 and m["v2a"]["different_recall"] == 1.0
    assert m["duty_source"] == {"aligner": 2} and "not T1 gold" in m["note"]


# -- regression on real V1 outputs (local data; no gold is read for T1) ------------------------------------------------


@pytest.mark.skipif(not HAVE_DEV, reason="local benchmark data not present")
def test_v2a_without_aligner_reproduces_v1_on_dev_and_sealed_t1():
    p = RV.plan_info()
    assert p["units"] == 92 and p["v1_dev_records"] == 92 and p["v2a_without_aligner_reproduces_v1"] == 92
    assert p["done"] + p["calls_needed"] == 92
    sealed = sorted(RV.T1_SEALED_V1.glob("*.json"))
    assert len(sealed) == 412
    for f in sealed:
        r = json.loads(f.read_text())
        out = D.decide_a(r, None, [pid for pid, _ in r["per_candidate"]])
        assert out["judgement"] == r["judgement"] and out["changed"] is False
