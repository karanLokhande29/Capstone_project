"""P4-001 Part B analysis: T1 systems, T2 retrieval stage, T3, T4 ablation C, with seeded bootstrap CIs.

Conventions (stated in the report):

* T1 flag, 3-way: Macro-F1 over gold shared / class-specific / absent; a predicted ``ambiguous`` is wrong.
  Collapsed: absent vs present (``ambiguous`` is wrong there too). Judgements: F1 per label over
  same / different / none; a predicted ``unsure`` is wrong. Coverage = share of items not ``ambiguous``.
* Bootstrap: 2,000 resamples of items (T1, T3) or queries/questions (T2, T4), seed ``p4.seeds.bootstrap``;
  a paired difference evaluates both systems on the same resampled indices. T1 judgement metrics resample
  items (all compared classes of a drawn item).
* T3 supersession F1: over (paragraph, governing instrument) pairs where an amendment governs. A prediction
  naming an amendment is a true positive when it is the gold amendment, a false positive otherwise; a gold
  amendment not predicted is a false negative.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from src.eval.ci_format import ci_reading
from src.eval.metrics import bootstrap_indices, f1_scores
from src.rag.evaluation import FLAGS, collapse_flag, collapsed_macro_f1, coverage, flag_macro_f1

JUDG = ("same", "different", "none")


def _ci(draws: Sequence[float]) -> list[float]:
    arr = np.asarray([d for d in draws if d == d], dtype=float)
    lo, hi = np.percentile(arr, [2.5, 97.5])
    return [float(lo), float(hi)]


def boot(n: int, stat: Callable[[np.ndarray], float], *, resamples: int, seed: int) -> dict[str, Any]:
    point = stat(np.arange(n))
    draws = [stat(idx) for idx in bootstrap_indices(n, resamples=resamples, seed=seed)]
    return {"value": float(point), "ci": _ci(draws), "n": n}


def paired(n: int, stat_a: Callable[[np.ndarray], float], stat_b: Callable[[np.ndarray], float], *,
           resamples: int, seed: int) -> dict[str, Any]:
    idx_all = np.arange(n)
    point = stat_a(idx_all) - stat_b(idx_all)
    draws = [stat_a(idx) - stat_b(idx) for idx in bootstrap_indices(n, resamples=resamples, seed=seed)]
    lo, hi = _ci(draws)
    return {"diff": float(point), "ci": [lo, hi], "n": n,
            "reading": ci_reading(lo, hi)}


# -- T1 ---------------------------------------------------------------------------------------


def t1_units(gold_items: Sequence[Mapping[str, Any]], pred: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Aligned gold / predicted flags and judgements for the items present in ``pred`` (item_id -> final)."""
    items = [g for g in gold_items if g["item_id"] in pred]
    gf = [g["differential_flag"] for g in items]
    pf = [pred[g["item_id"]]["flag"] for g in items]
    judg = []  # (item index, gold, pred)
    for i, g in enumerate(items):
        per = pred[g["item_id"]].get("per_class") or {}
        for c in sorted(g["compared_classes"]):
            judg.append((i, g["per_class_judgement"][c], (per.get(c) or {}).get("judgement", "unsure")))
    return {"items": [g["item_id"] for g in items], "gf": gf, "pf": pf, "judg": judg}


def t1_metrics(u: Mapping[str, Any], *, resamples: int, seed: int) -> dict[str, Any]:
    gf, pf, judg = np.array(u["gf"], dtype=object), np.array(u["pf"], dtype=object), u["judg"]
    n = len(gf)
    rows_of = [[k for k, (i, _, _) in enumerate(judg) if i == j] for j in range(n)]
    jg = np.array([g for _, g, _ in judg], dtype=object)
    jp = np.array([p for _, _, p in judg], dtype=object)

    def jrows(idx):
        return np.array([r for j in idx for r in rows_of[j]], dtype=int)

    def j_macro(idx):
        r = jrows(idx)
        return f1_scores(list(jg[r]), list(jp[r]), JUDG)["macro_f1"]

    out = {
        "n_items": n, "n_judgements": len(judg),
        "flag_macro_f1": boot(n, lambda i: flag_macro_f1(gf[i], pf[i]), resamples=resamples, seed=seed),
        "collapsed_macro_f1": boot(n, lambda i: collapsed_macro_f1(gf[i], pf[i]), resamples=resamples, seed=seed),
        "coverage": boot(n, lambda i: coverage(pf[i]), resamples=resamples, seed=seed),
        "judgement_macro_f1": boot(n, j_macro, resamples=resamples, seed=seed),
        "judgement_f1_per_label": {k: v["f1"] for k, v in f1_scores(list(jg), list(jp), JUDG)["per_label"].items()},
        "flag_f1_per_label": {k: v["f1"] for k, v in f1_scores(list(gf), list(pf), FLAGS)["per_label"].items()},
        "pred_flags": dict(Counter(pf)),
        "confusion": {g: {p: int(sum(1 for a, b in zip(gf, pf) if a == g and b == p))
                          for p in (*FLAGS, "ambiguous")} for g in FLAGS},
        "unsure_judgements": int(sum(1 for p in jp if p == "unsure")),
    }
    return out


def t1_paired(u_a: Mapping[str, Any], u_b: Mapping[str, Any], *, resamples: int, seed: int) -> dict[str, Any]:
    """System A minus system B on the items both have (same gold)."""
    common = [i for i in u_a["items"] if i in set(u_b["items"])]
    ia = {k: j for j, k in enumerate(u_a["items"])}
    ib = {k: j for j, k in enumerate(u_b["items"])}
    gf = np.array([u_a["gf"][ia[k]] for k in common], dtype=object)
    pa = np.array([u_a["pf"][ia[k]] for k in common], dtype=object)
    pb = np.array([u_b["pf"][ib[k]] for k in common], dtype=object)
    n = len(common)
    kw = {"resamples": resamples, "seed": seed}
    return {
        "n_items": n,
        "flag_macro_f1": paired(n, lambda i: flag_macro_f1(gf[i], pa[i]), lambda i: flag_macro_f1(gf[i], pb[i]), **kw),
        "collapsed_macro_f1": paired(n, lambda i: collapsed_macro_f1(gf[i], pa[i]),
                                     lambda i: collapsed_macro_f1(gf[i], pb[i]), **kw),
        "coverage": paired(n, lambda i: coverage(pa[i]), lambda i: coverage(pb[i]), **kw),
    }


def subset_units(u: Mapping[str, Any], keep: set[str]) -> dict[str, Any]:
    idx = [j for j, k in enumerate(u["items"]) if k in keep]
    remap = {old: new for new, old in enumerate(idx)}
    return {"items": [u["items"][j] for j in idx], "gf": [u["gf"][j] for j in idx], "pf": [u["pf"][j] for j in idx],
            "judg": [(remap[i], g, p) for i, g, p in u["judg"] if i in remap]}


# -- T3 ---------------------------------------------------------------------------------------


def supersession_counts(gold_gov: Sequence[str], pred_gov: Sequence[str]) -> tuple[int, int, int]:
    tp = fp = fn = 0
    for g, p in zip(gold_gov, pred_gov):
        g_amd, p_amd = g.startswith("amd_"), p.startswith("amd_")
        if p_amd and p == g:
            tp += 1
        elif p_amd:
            fp += 1
            if g_amd:
                fn += 1
        elif g_amd:
            fn += 1
    return tp, fp, fn


def supersession_f1(gold_gov: Sequence[str], pred_gov: Sequence[str]) -> float:
    tp, fp, fn = supersession_counts(gold_gov, pred_gov)
    return 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0


def t3_metrics(items: Sequence[Mapping[str, Any]], pred: Mapping[str, Mapping[str, Any]], *, resamples: int,
               seed: int) -> dict[str, Any]:
    ids = [i["t3_id"] for i in items if i["t3_id"] in pred]
    gold = {i["t3_id"]: i for i in items}
    gs = np.array([gold[k]["gold_status"] for k in ids], dtype=object)
    ps = np.array([pred[k]["pred_status"] for k in ids], dtype=object)
    gg = np.array([gold[k]["gold_governing_instrument"] for k in ids], dtype=object)
    pg = np.array([pred[k]["pred_governing_instrument"] for k in ids], dtype=object)
    n = len(ids)
    kw = {"resamples": resamples, "seed": seed}
    by_side = {}
    for side in ("before", "after"):
        sel = np.array([j for j, k in enumerate(ids) if gold[k]["side"] == side])
        by_side[side] = {"n": int(len(sel)), "status_exact_match": float(np.mean(gs[sel] == ps[sel])) if len(sel) else None}
    return {"n": n,
            "status_exact_match": boot(n, lambda i: float(np.mean(gs[i] == ps[i])), **kw),
            "supersession_f1": boot(n, lambda i: supersession_f1(gg[i], pg[i]), **kw),
            "supersession_counts": dict(zip(("tp", "fp", "fn"), supersession_counts(gg, pg))),
            "by_side": by_side, "pred_status": dict(Counter(ps))}


def t3_paired(items, pred_on, pred_off, *, resamples: int, seed: int) -> dict[str, Any]:
    ids = [i["t3_id"] for i in items if i["t3_id"] in pred_on and i["t3_id"] in pred_off]
    gold = {i["t3_id"]: i for i in items}
    gs = np.array([gold[k]["gold_status"] for k in ids], dtype=object)
    gg = np.array([gold[k]["gold_governing_instrument"] for k in ids], dtype=object)
    on_s = np.array([pred_on[k]["pred_status"] for k in ids], dtype=object)
    off_s = np.array([pred_off[k]["pred_status"] for k in ids], dtype=object)
    on_g = np.array([pred_on[k]["pred_governing_instrument"] for k in ids], dtype=object)
    off_g = np.array([pred_off[k]["pred_governing_instrument"] for k in ids], dtype=object)
    n = len(ids)
    kw = {"resamples": resamples, "seed": seed}
    return {"n": n,
            "status_exact_match": paired(n, lambda i: float(np.mean(gs[i] == on_s[i])),
                                         lambda i: float(np.mean(gs[i] == off_s[i])), **kw),
            "supersession_f1": paired(n, lambda i: supersession_f1(gg[i], on_g[i]),
                                      lambda i: supersession_f1(gg[i], off_g[i]), **kw)}


# -- T4 ablation C ------------------------------------------------------------------------------------


def t4_per_question(log: Mapping[str, Any]) -> dict[str, Any]:
    r = log["result"]
    sents = r["sentences"] if r["can_answer"] else []
    sup = r.get("supported") or []
    delivered = len(sents) if not r["abstained_by_verifier"] else 0
    unsupported = 0 if r["abstained_by_verifier"] else sum(1 for ok in sup[:len(sents)] if not ok)
    return {"abstained_by_verifier": bool(r["abstained_by_verifier"]),
            "model_declined": not log["steps"][-1]["can_answer"],
            "answered": bool(r["can_answer"]), "delivered_sentences": delivered, "unsupported_sentences": unsupported,
            "retried": len(log["steps"]) > 1}


def t4_metrics(rows: Sequence[Mapping[str, Any]], repass: Sequence[float] | None, *, resamples: int, seed: int) -> dict[str, Any]:
    n = len(rows)
    d = np.array([r["delivered_sentences"] for r in rows], dtype=float)
    u = np.array([r["unsupported_sentences"] for r in rows], dtype=float)
    ab = np.array([r["abstained_by_verifier"] or r["model_declined"] for r in rows], dtype=float)
    kw = {"resamples": resamples, "seed": seed}
    out = {"n": n,
           "unsupported_sentence_rate": boot(n, lambda i: float(u[i].sum() / d[i].sum()) if d[i].sum() else float("nan"), **kw),
           "abstention_rate": boot(n, lambda i: float(ab[i].mean()), **kw),
           "abstained_by_verifier": int(sum(r["abstained_by_verifier"] for r in rows)),
           "model_declined": int(sum(r["model_declined"] for r in rows)),
           "retried": int(sum(r["retried"] for r in rows))}
    if repass is not None:
        rp = np.array(repass, dtype=float)
        out["repass_composite"] = boot(n, lambda i: float(rp[i].mean()), **kw)
    return out


# -- post hoc verifier diagnostics (audit note 3; no LLM calls, never replace the frozen rule) -----------------

import re as _re

_SENT = _re.compile(r"(?<=[.;:])\s+")


def sentences_of(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT.split(" ".join(text.split())) if p.strip()]
    return parts or [text]


def best_sentence_support(verifier: Any, premise_text: str, hypothesis: str) -> tuple[bool, bool]:
    """(supported under the frozen whole-paragraph rule, supported if the premise were the paragraph's best single
    sentence: the sentence with the highest entailment probability, supported iff its argmax is entailment)."""
    whole = verifier.supported([(premise_text, hypothesis)])[0]
    sents = sentences_of(premise_text)
    p, arg = verifier.probs([(s_, hypothesis) for s_ in sents])
    j = int(np.argmax(p))
    return whole, bool(arg[j] == verifier.entail)


def kept_items_diagnostic(u_fa: Mapping[str, Any], u_ca: Mapping[str, Any]) -> dict[str, Any]:
    """On the items final agentic did not abstain on: flag accuracy and 3-way F1, final agentic vs class-aware."""
    keep = [k for k, p in zip(u_fa["items"], u_fa["pf"]) if p != "ambiguous"]
    fa, ca = subset_units(u_fa, set(keep)), subset_units(u_ca, set(keep))
    acc = lambda u: float(np.mean([g == p for g, p in zip(u["gf"], u["pf"])]))  # noqa: E731
    ca_own = [k for k, p in zip(u_ca["items"], u_ca["pf"]) if p != "ambiguous"]
    cao = subset_units(u_ca, set(ca_own))
    return {"n_kept_by_final_agentic": len(keep),
            "final_agentic": {"accuracy": acc(fa), "flag_macro_f1": flag_macro_f1(fa["gf"], fa["pf"])},
            "class_aware_same_items": {"accuracy": acc(ca), "flag_macro_f1": flag_macro_f1(ca["gf"], ca["pf"])},
            "class_aware_own_non_abstained": {"n": len(ca_own), "accuracy": acc(cao),
                                              "flag_macro_f1": flag_macro_f1(cao["gf"], cao["pf"])}}
