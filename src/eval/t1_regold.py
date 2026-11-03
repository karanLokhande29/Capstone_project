"""Gold-version-aware T1 re-evaluation: score every cached system prediction against any gold file.

The scoring functions, the baselines, the pairs and the bootstrap settings are exactly those of P4-001
(`scripts/run_p4.py cmd_report`, `src/rag/analysis.py`), so the harness reproduces the v1 T1 table on v1 gold.

It adds:
- the `different` F1 and recall;
- the different→same and different→none counts;
- the judgement confusion matrix;
- the count of gold `different` units that every LLM system missed;
- a missing-prediction and LLM-call estimate for a new gold version.

It makes no model calls.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.eval import t1_eval as TE
from src.eval.ci_format import fmt_ci
from src.rag import analysis as A

LLM_SYSTEMS = ("class_blind", "class_aware", "final_agentic", "ablation_a")
BASELINES = ("majority", "p2002_candidates")
PAIRS = [("Ablation A (verifier on): final agentic − class-blind + verifier", "final_agentic", "ablation_a"),
         ("Class filter, no verifier: class-aware − class-blind", "class_aware", "class_blind"),
         ("Ablation C on T1: final agentic − class-aware", "final_agentic", "class_aware"),
         ("Verifier, class-blind: ablation A − class-blind", "ablation_a", "class_blind"),
         ("Class-blind LLM − P2-002 candidates", "class_blind", "p2002_candidates"),
         ("Class-aware LLM − P2-002 candidates", "class_aware", "p2002_candidates"),
         ("Final agentic − P2-002 candidates", "final_agentic", "p2002_candidates"),
         ("Class-blind + verifier − P2-002 candidates", "ablation_a", "p2002_candidates")]
LC_PAIRS = [("Long-context − majority (same items)", "long_context", "majority"),
            ("Long-context − P2-002 candidates (same items)", "long_context", "p2002_candidates"),
            ("Long-context − class-blind (same items)", "long_context", "class_blind"),
            ("Long-context − class-aware (same items)", "long_context", "class_aware"),
            ("Long-context − final agentic (same items)", "long_context", "final_agentic"),
            ("Long-context − class-blind + verifier (same items)", "long_context", "ablation_a")]
OTHERS = ("majority", "p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a")


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def finals(runs_dir: Path, run: str) -> dict[str, dict]:
    d = Path(runs_dir) / f"t1_{run}"
    out = {}
    for p in sorted(d.glob("t1_*.json")) if d.exists() else []:
        x = json.loads(p.read_text())
        out[x["item_id"]] = x["final"]
    return out


def calls_per_item(runs_dir: Path, run: str) -> dict[str, Any]:
    d = Path(runs_dir) / f"t1_{run}"
    calls = [json.loads(p.read_text()).get("calls") for p in sorted(d.glob("t1_*.json"))] if d.exists() else []
    calls = [c for c in calls if isinstance(c, int)]
    return {"n": len(calls), "mean": (sum(calls) / len(calls)) if calls else None, "max": max(calls) if calls else None}


def baseline_predictions(gold: Sequence[Mapping[str, Any]], candidates_by_scid: Mapping[str, Mapping[str, Any]]) -> dict:
    """Majority (in-sample) and P2-002 baselines, recomputed against THIS gold (as P4 did)."""
    maj = TE.majority_predictions(gold)
    p2 = TE.p2002_predictions(gold, candidates_by_scid)
    mapping = TE.default_fixed_mapping(gold)

    def as_final(pred, fixed):
        out, j = {}, 0
        for it, f in zip(gold, pred["flags"]):
            per = {}
            for c in sorted(it["compared_classes"]):
                per[c] = {"judgement": fixed.get(pred["judgements"][j], pred["judgements"][j])}
                j += 1
            out[it["item_id"]] = {"flag": fixed.get(f, f), "per_class": per}
        return out

    return {"majority": as_final(maj, {}), "p2002_candidates": as_final(p2, mapping)}


def long_context_run(runs_dir: Path) -> tuple[str | None, int | None]:
    for cap in (64000, 100000):
        d = Path(runs_dir) / f"t1_long_context_cap{cap // 1000}k"
        if d.exists() and any(d.glob("t1_*.json")):
            return d.name.removeprefix("t1_"), cap
    return None, None


def different_diagnostics(u: Mapping[str, Any]) -> dict[str, Any]:
    pairs = [(g, p) for _, g, p in u["judg"]]
    gd = [p for g, p in pairs if g == "different"]
    pd_ = [g for g, p in pairs if p == "different"]
    tp = sum(1 for p in gd if p == "different")
    rec = tp / len(gd) if gd else None
    prec = tp / len(pd_) if pd_ else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else 0.0 if gd else None
    cats = ("same", "different", "none", "unsure")
    return {"gold_different_units": len(gd), "different_recall": rec, "different_precision": prec, "different_f1": f1,
            "different_to_same": sum(1 for p in gd if p == "same"), "different_to_none": sum(1 for p in gd if p == "none"),
            "different_to_unsure_or_missing": sum(1 for p in gd if p not in ("same", "different", "none")),
            "judgement_confusion": {g: {p: sum(1 for a, b in pairs if a == g and b == p) for p in cats} for g in cats[:3]}}


def missed_by_every_system(U: Mapping[str, Mapping[str, Any]], systems: Sequence[str]) -> dict[str, Any]:
    """Gold `different` class units that no LLM system (with a prediction for the item) labelled `different`."""
    hits: dict[tuple[str, int], list[bool]] = {}
    for s in systems:
        if s not in U:
            continue
        u = U[s]
        seen: Counter = Counter()
        for i, g, p in u["judg"]:
            k = (u["items"][i], seen[i])
            seen[i] += 1
            if g == "different":
                hits.setdefault(k, []).append(p == "different")
    missed = sorted(f"{k[0]}#{k[1]}" for k, v in hits.items() if not any(v))
    return {"gold_different_units": len(hits), "missed_by_every_system": len(missed), "systems": [s for s in systems if s in U]}


def evaluate(gold: Sequence[Mapping[str, Any]], candidates_by_scid: Mapping[str, Mapping[str, Any]], runs_dir: Path, *,
             resamples: int, seed: int) -> dict[str, Any]:
    kw = {"resamples": resamples, "seed": seed}
    preds = baseline_predictions(gold, candidates_by_scid)
    for s in LLM_SYSTEMS:
        f = finals(runs_dir, s)
        if f:
            preds[s] = f
    lc_name, lc_cap = long_context_run(runs_dir)
    if lc_name:
        preds["long_context"] = finals(runs_dir, lc_name)
    U = {s: A.t1_units(gold, p) for s, p in preds.items()}
    t1: dict[str, Any] = {"n_gold_items": len(gold), "systems": {s: A.t1_metrics(u, **kw) for s, u in U.items()}, "paired": {}}
    for label, a, b in PAIRS + (LC_PAIRS if "long_context" in U else []):
        if a in U and b in U:
            t1["paired"][label] = A.t1_paired(U[a], U[b], **kw)
    if "long_context" in U:
        scored = sorted(U["long_context"]["items"])
        t1["long_context_same_items"] = {"n": len(scored), "cap": lc_cap, "systems": {
            s: A.t1_metrics(A.subset_units(U[s], set(scored)), **kw) for s in (*OTHERS, "long_context") if s in U}}
    f150 = finals(runs_dir, "long_context")
    if f150:
        u150 = A.t1_units(gold, f150)
        items150 = set(u150["items"])
        t1["appendix_150k"] = {"label": "superseded by the 100K rerun, shown for completeness", "n": len(items150),
                               "systems": {"long_context_150k": A.t1_metrics(u150, **kw),
                                           **{s: A.t1_metrics(A.subset_units(U[s], items150), **kw) for s in OTHERS if s in U}},
                               "paired_vs_final_agentic": A.t1_paired(u150, U["final_agentic"], **kw) if "final_agentic" in U else None,
                               "paired_vs_every_system": {s: A.t1_paired(u150, U[s], **kw) for s in OTHERS if s in U}}
    t1["different"] = {s: different_diagnostics(u) for s, u in U.items()}
    t1["missed_by_every_llm_system"] = missed_by_every_system(U, (*LLM_SYSTEMS, "long_context"))
    t1["coverage_of_gold"] = {s: {"predicted": len(U[s]["items"]), "missing": len(gold) - len(U[s]["items"])} for s in U}
    return t1


def missing_predictions(gold: Sequence[Mapping[str, Any]], runs_dir: Path) -> dict[str, Any]:
    """Which gold items lack a cached prediction per LLM system, and the calls Phase 4 would need (estimate only)."""
    ids = {g["item_id"] for g in gold}
    out = {}
    lc_name, _ = long_context_run(runs_dir)
    for s, run in [(s, s) for s in LLM_SYSTEMS] + ([("long_context", lc_name)] if lc_name else []):
        have = set(finals(runs_dir, run))
        miss = sorted(ids - have)
        cpi = calls_per_item(runs_dir, run)
        out[s] = {"run": run, "missing_items": miss, "n_missing": len(miss),
                  "observed_calls_per_item": cpi,
                  "estimated_calls_needed": {"at_mean": round(len(miss) * cpi["mean"], 1) if cpi["mean"] else None,
                                             "at_max": len(miss) * cpi["max"] if cpi["max"] else None},
                  "note": ("estimate only; no call made. The recorded `calls` count only uncached calls (verifier systems reused the "
                           "cached first answer; long-context reused 150K-run prompts), so at_mean undercounts for new items; "
                           "at_max (one call per missing item per system, before retries) is the planning figure")}
    return out


def fmt_metric(v: Mapping[str, Any]) -> str:
    return fmt_ci(v["value"], v["ci"][0], v["ci"][1]) if isinstance(v, Mapping) and "ci" in v else str(v)
