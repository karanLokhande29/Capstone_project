"""Final push P0-5: gold-version-aware T1 re-evaluation (fixtures + exact regression on the v1 T1 table)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.eval import t1_regold as G

REPO = Path(__file__).resolve().parents[1]
T1 = REPO / "data" / "benchmark" / "t1"
RUNS = REPO / "data" / "rag_runs"
P4 = REPO / "reports" / "p4001_metrics_v1.json"
CB, SFB, PB = "Commercial Banks", "Small Finance Banks", "Payments Banks"


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.skipif(not (RUNS.exists() and (T1 / "t1_candidate_benchmark_v1.jsonl").exists() and P4.exists()),
                    reason="cached predictions / gitignored candidate benchmark not present")
def test_regression_reproduces_the_v1_t1_table_exactly():
    gold = G.read_jsonl(T1 / "t1_validated_v1.jsonl")
    need = {g["source_candidate_id"] for g in gold}
    cands = {}
    with (T1 / "t1_candidate_benchmark_v1.jsonl").open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            if r["source_candidate_id"] in need:
                cands[r["source_candidate_id"]] = r
    res = G.evaluate(gold, cands, RUNS, resamples=2000, seed=20261011)
    ref = json.loads(P4.read_text())["t1"]
    for s in ref["systems"]:
        assert _same(res["systems"][s], ref["systems"][s]), s
    assert set(res["paired"]) == set(ref["paired"])
    for k in ref["paired"]:
        assert _same(res["paired"][k], ref["paired"][k]), k
    for s in ref["long_context_same_items"]["systems"]:
        assert _same(res["long_context_same_items"]["systems"][s], ref["long_context_same_items"]["systems"][s]), s
    a = ref["appendix_150k"]
    assert _same(res["appendix_150k"]["systems"], a["systems"])
    assert _same(res["appendix_150k"]["paired_vs_every_system"], a["paired_vs_every_system"])
    assert round(res["different"]["class_blind"]["different_f1"], 3) == round(ref["systems"]["class_blind"]["judgement_f1_per_label"]["different"], 3)


def _gold(i, flag, judg):
    return {"item_id": i, "source_candidate_id": "c" + i, "label_status": "validated", "differential_flag": flag,
            "compared_classes": sorted(judg), "per_class_judgement": judg}


def _write_run(runs: Path, run: str, preds: dict, calls: int = 1):
    d = runs / f"t1_{run}"
    d.mkdir(parents=True)
    for i, f in preds.items():
        (d / f"t1_{i}.json").write_text(json.dumps({"item_id": i, "final": f, "calls": calls}))


def test_fixture_evaluation_diagnostics_and_missing_report(tmp_path):
    gold = [_gold("a", "class-specific", {SFB: "different", PB: "same"}), _gold("b", "shared", {CB: "same"}),
            _gold("c", "absent", {CB: "none"}), _gold("d", "class-specific", {CB: "different"})]
    cands = {"c" + g["item_id"]: {"per_class_candidate": {c: "matched" for c in g["compared_classes"]}} for g in gold}
    runs = tmp_path / "runs"
    fin = lambda flag, **pc: {"flag": flag, "per_class": {k.replace("_", " "): {"judgement": v} for k, v in pc.items()}}
    _write_run(runs, "class_blind", {"a": fin("class-specific", Small_Finance_Banks="different", Payments_Banks="same"),
                                     "b": fin("shared", Commercial_Banks="same"), "c": fin("absent", Commercial_Banks="none"),
                                     "d": fin("shared", Commercial_Banks="same")}, calls=2)
    _write_run(runs, "class_aware", {"a": fin("shared", Small_Finance_Banks="same", Payments_Banks="same"),
                                     "b": fin("shared", Commercial_Banks="same"), "c": fin("absent", Commercial_Banks="none")})
    res = G.evaluate(gold, cands, runs, resamples=50, seed=1)
    d = res["different"]["class_blind"]
    assert d["gold_different_units"] == 2 and d["different_recall"] == 0.5 and d["different_to_same"] == 1
    assert res["different"]["class_aware"]["different_to_same"] == 1
    assert res["missed_by_every_llm_system"] == {"gold_different_units": 2, "missed_by_every_system": 1,
                                                 "systems": ["class_blind", "class_aware"]}
    assert res["coverage_of_gold"]["class_aware"] == {"predicted": 3, "missing": 1}
    assert "Class filter, no verifier: class-aware − class-blind" in res["paired"]
    miss = G.missing_predictions(gold + [_gold("e", "absent", {CB: "none"})], runs)
    assert miss["class_blind"]["missing_items"] == ["e"] and miss["class_blind"]["estimated_calls_needed"]["at_mean"] == 2.0
    assert miss["class_aware"]["n_missing"] == 2
