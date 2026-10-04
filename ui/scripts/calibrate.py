#!/usr/bin/env python3
"""§8.2 calibrated confidence for the structured comparator's verdicts (offline; no LLM calls).

    python3 ui/scripts/calibrate.py        (after ui/scripts/ingest.py)

Order of work (each step's file is written before the next step runs):
1. Spec: features, method, band cut points, merge rule, honesty rule and seeds
   -> ui/src/data/confidence_spec_v1.json (sha256 recorded).
2. M2 (comparator-intrinsic) is fitted on the 30-item development set (92 units; data/rag_runs/comparator_dev_irr30 vs
   data/benchmark/t1/p2004_irr_consensus_v1.jsonl). Its parameters are frozen to ui/src/data/confidence_frozen_v1.json
   (sha256 recorded) BEFORE any gold label is read for evaluation.
3. M1 (full signals) is 5-fold cross-fitted on gold, grouped by item: each unit is scored by a model that never saw its item.
4. Evaluation on gold (412 units): per-band n / accuracy / Wilson CI, reliability diagram, ECE, Brier, selective curve.
   -> ui/src/data/confidence_model_v1.json + ui/docs/CALIBRATION.md

Nothing is rescaled, floored or rounded up. A test (ui/src/data/confidence.test.ts) checks that the UI shows exactly these values.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cc_common as C  # noqa: E402

UI, ROOT = C.UI, C.ROOT
DATA = UI / "src/data"
SPEC = DATA / "confidence_spec_v1.json"
FROZEN = DATA / "confidence_frozen_v1.json"
MODEL = DATA / "confidence_model_v1.json"
REPORT = UI / "docs/CALIBRATION.md"
SNAP = DATA / "snapshot.json"
DEV_GOLD = ROOT / "data/benchmark/t1/p2004_irr_consensus_v1.jsonl"

M2_FEATURES = ["pred_different", "pred_none", "n_fields_both_sides", "n_material_diff", "single_field_hinge", "candidates_agree",
               "target_amended_text_only", "ambiguous_matrix_cell"]
M1_EXTRA = ["agree_count_other_llms", "long_context_unanswered", "final_agentic_abstained", "matched_equals_class_aware"]
SPEC_DATA = {
    "version": "confidence-v1",
    "unit": "one comparator class unit (item × compared class)",
    "label": "correct iff the comparator judgement equals the gold judgement; `unsure` / parse failure -> Abstain band (counted as not answered)",
    "method": "L2-regularised logistic regression, C = 1.0 (penalty 1/(2C)·||w||², intercept unpenalised), features standardised with the "
              "training data's mean and sd, Newton solver (numpy), 50 iterations max, tol 1e-10",
    "models": {
        "M2": {"name": "comparator-intrinsic", "features": M2_FEATURES, "fit": "development set: 30-item IRR consensus, 92 comparator units",
               "use": "Showcase, product badges (Obligation Explorer, assistant, live mode, review queue)"},
        "M1": {"name": "full signals (cross-validated on gold)", "features": M2_FEATURES + M1_EXTRA,
               "fit": "5-fold cross-fitting on gold, grouped by item; fold assignment = numpy default_rng(20261003).permutation over sorted item ids, "
                      "fold = position mod 5", "use": "research views only, labelled 'cross-validated on gold'"},
    },
    "bands": {"High": "p >= 0.85", "Medium": "0.60 <= p < 0.85", "Low": "p < 0.60", "Abstain": "comparator unsure / parse failure"},
    "cut_points": {"high": 0.85, "low": 0.60},
    "merge_rule": "a High or Low band with n < 20 on gold is merged into Medium; if Medium then has n < 20 it is hidden (R14)",
    "operating_point": "answer only at High (fixed here, before any gold evaluation)",
    "honesty_rule": "bands are labelled 'experimental' and kept out of the Showcase if the High band's Wilson 95% lower bound is not above the "
                    "Low band's point accuracy, or if ECE (10 equal-width bins) > 0.10",
    "metrics": ["per-band n, accuracy, Wilson 95% CI", "reliability diagram (10 equal-width bins)", "ECE (10 bins, weighted)", "Brier score",
                "selective-prediction curve (accuracy vs coverage, coverage over all 412 units)"],
    "seed": 20261003,
    "dropped_signal": "BM25/dense agreement on the matched paragraph: no per-unit rankings stored (DECISIONS D-04, gap G-23)",
}


def write_json(p: Path, obj) -> str:
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return C.sha256(p)


def wilson(k: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    ph = k / n
    den = 1 + z * z / n
    centre = (ph + z * z / (2 * n)) / den
    half = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def fit_lr(X: np.ndarray, y: np.ndarray, C_: float = 1.0) -> dict:
    mu, sd = X.mean(0), X.std(0)
    sd = np.where(sd > 0, sd, 1.0)
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    reg = np.full(Z.shape[1], 1.0 / C_)
    reg[0] = 0.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) + reg * w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(reg)
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    return {"intercept": float(w[0]), "weights": [float(x) for x in w[1:]], "means": [float(x) for x in mu], "sds": [float(x) for x in sd]}


def predict(m: dict, X: np.ndarray) -> np.ndarray:
    z = m["intercept"] + ((X - np.array(m["means"])) / np.array(m["sds"])) @ np.array(m["weights"])
    return 1 / (1 + np.exp(-z))


def band(p: float | None, cut=SPEC_DATA["cut_points"]) -> str:
    if p is None:
        return "Abstain"
    return "High" if p >= cut["high"] else ("Medium" if p >= cut["low"] else "Low")


# -- features -------------------------------------------------------------------------------------------------------

def context_tables():
    docs = {d["md_id"]: d for d in C.read_jsonl(ROOT / "release/data/documents.jsonl")}
    amended = {k for k, d in docs.items() if "Updated as on" in (d.get("title") or "")}
    cells = {(m["entity_class"], m["subject_family"]): m["ambiguous"] for m in C.read_jsonl(ROOT / "release/data/matrix/matrix_v1.jsonl")}
    return docs, amended, cells


def intrinsic(rec: dict, source_class: str, docs, amended, cells) -> list[float] | None:
    sig = C.comparator_signals(rec)
    if not sig["parse_ok"] or sig["judgement"] not in ("same", "different", "none"):
        return None
    md_src = rec["item_id"].removeprefix("t1_").split("::")[0]
    fam = docs.get(md_src, {}).get("subject_family")
    target_md = (sig["decisive_pid"] or "").split("::")[0]
    return [float(sig["judgement"] == "different"), float(sig["judgement"] == "none"), float(sig["n_both"]), float(sig["n_material_diff"]),
            float(sig["hinge"]), float(sig["candidates_agree"]), float(target_md in amended), float(bool(cells.get((source_class, fam), False)))]


def dev_set(docs, amended, cells):
    gold = {}
    src_class = {}
    for r in C.read_jsonl(DEV_GOLD):
        src_class[r["item_id"]] = r.get("source_class")
        for c, j in (r.get("judgements") or {}).items():
            gold[C.unit_id(r["item_id"], c)] = j if isinstance(j, str) else (j or {}).get("judgement")
    X, y, ab = [], [], 0
    for uid, rec in C.comparator_records(C.CMP_DEV).items():
        f = intrinsic(rec, src_class.get(rec["item_id"]) or "", docs, amended, cells)
        if f is None:
            ab += 1
            continue
        X.append(f)
        y.append(float(rec["judgement"] == gold[uid]))
    return np.array(X), np.array(y), ab


# -- evaluation ------------------------------------------------------------------------------------------------------

def evaluate(probs: dict[str, float | None], correct: dict[str, bool]) -> dict:
    n_all = len(probs)
    by = {"High": [], "Medium": [], "Low": [], "Abstain": []}
    for uid, p in probs.items():
        by[band(p)].append(uid)
    raw_bands = {b: len(v) for b, v in by.items()}
    merged = []
    for b in ("High", "Low"):
        if 0 < len(by[b]) < 20:
            by["Medium"] += by[b]
            by[b] = []
            merged.append(b)
    bands = []
    for b in ("High", "Medium", "Low", "Abstain"):
        ids = by[b]
        k = sum(correct[u] for u in ids)
        bands.append({"band": b, "n": len(ids), "correct": k, "accuracy": (k / len(ids)) if ids else None, "wilsonCI": wilson(k, len(ids)) if ids else None,
                      "hidden": b == "Medium" and 0 < len(ids) < 20})
    answered = [(p, correct[u]) for u, p in probs.items() if p is not None]
    P = np.array([p for p, _ in answered])
    Y = np.array([float(c) for _, c in answered])
    bins, ece = [], 0.0
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        m = (P >= lo) & ((P < hi) if i < 9 else (P <= hi))
        if m.sum():
            conf, acc = float(P[m].mean()), float(Y[m].mean())
            ece += m.sum() / len(P) * abs(conf - acc)
            bins.append({"lo": lo, "hi": hi, "n": int(m.sum()), "meanConfidence": conf, "accuracy": acc, "wilsonCI": wilson(int(Y[m].sum()), int(m.sum()))})
        else:
            bins.append({"lo": lo, "hi": hi, "n": 0, "meanConfidence": None, "accuracy": None, "wilsonCI": None})
    brier = float(np.mean((P - Y) ** 2))
    order = np.argsort(-P, kind="stable")
    curve = []
    for k in range(1, len(order) + 1):
        if k in (1, 2, 5) or k % 10 == 0 or k == len(order):
            sel = Y[order[:k]]
            curve.append({"coverage": k / n_all, "answered": k, "accuracy": float(sel.mean()), "wilsonCI": wilson(int(sel.sum()), k),
                          "threshold": float(P[order[k - 1]])})
    high = next(b for b in bands if b["band"] == "High")
    low = next(b for b in bands if b["band"] == "Low")
    reasons = []
    if not high["n"]:
        reasons.append("no units in the High band")
    elif low["n"] and not (high["wilsonCI"][0] > low["accuracy"]):
        reasons.append(f"High-band Wilson lower bound {high['wilsonCI'][0]:.3f} is not above Low-band accuracy {low['accuracy']:.3f}")
    if ece > 0.10:
        reasons.append(f"ECE {ece:.3f} > 0.10")
    base_k = sum(correct.values())
    op = {"band": "High", "coverage": high["n"] / n_all, "answered": high["n"], "accuracy": high["accuracy"], "wilsonCI": high["wilsonCI"]}
    return {"nUnits": n_all, "baseRate": {"correct": base_k, "n": n_all, "accuracy": base_k / n_all, "wilsonCI": wilson(base_k, n_all)},
            "rawBandCounts": raw_bands, "mergedBands": merged, "bands": bands, "ece": ece, "brier": brier, "reliability": bins,
            "selectiveCurve": curve, "operatingPoint": op, "experimental": bool(reasons), "experimentalReasons": reasons}


def composition(probs, correct, pred_label) -> dict:
    """Per band: how many verdicts of each predicted label, and how many of those were correct."""
    out: dict = {}
    for uid, p in probs.items():
        b = band(p)
        d = out.setdefault(b, {}).setdefault(pred_label[uid], {"n": 0, "correct": 0})
        d["n"] += 1
        d["correct"] += int(correct[uid])
    return out


def within_label_auc(probs, correct, pred_label) -> dict:
    """AUC of the score for right vs wrong, separately within each predicted label (does it rank beyond the label itself?)."""
    out = {}
    for lab in ("same", "different", "none"):
        pos = [probs[u] for u in probs if probs[u] is not None and pred_label[u] == lab and correct[u]]
        neg = [probs[u] for u in probs if probs[u] is not None and pred_label[u] == lab and not correct[u]]
        if not pos or not neg:
            out[lab] = {"auc": None, "nRight": len(pos), "nWrong": len(neg)}
            continue
        wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
        out[lab] = {"auc": wins / (len(pos) * len(neg)), "nRight": len(pos), "nWrong": len(neg)}
    return out


def main() -> int:
    if not SNAP.exists():
        raise SystemExit("snapshot.json missing: run `npm run ingest` first")
    t0 = datetime.now(timezone.utc).isoformat(timespec="seconds")
    spec_sha = write_json(SPEC, SPEC_DATA | {"writtenUtc": t0})
    docs, amended, cells = context_tables()

    # Step 2: M2 on dev, frozen before any gold evaluation.
    Xd, yd, dev_abstain = dev_set(docs, amended, cells)
    m2 = fit_lr(Xd, yd)
    dev_p = predict(m2, Xd)
    frozen = {"specSha256": spec_sha, "frozenUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "M2": {"features": M2_FEATURES, **m2, "devUnits": int(len(yd)) + dev_abstain, "devFitted": int(len(yd)), "devAbstain": dev_abstain,
                     "devAccuracy": float(yd.mean()), "devBrier": float(np.mean((dev_p - yd) ** 2))}}
    frozen_sha = write_json(FROZEN, frozen)
    print(f"spec {spec_sha[:12]}…; M2 frozen {frozen_sha[:12]}… (dev units {len(yd)} + {dev_abstain} abstain, dev accuracy {yd.mean():.3f})")

    # Step 3: gold units (labels read only now).
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    units = snap["classUnits"]
    item_src = {it["id"]: it["sourceClass"] for it in snap["t1Items"]}
    cmp = C.comparator_records(C.CMP_GOLD)
    rows = []
    for u in units:
        f2 = intrinsic(cmp[u["id"]], item_src[u["itemId"]], docs, amended, cells)
        pr = u["predictions"]
        cj = pr["comparator"]["judgement"]
        others = [pr[s]["judgement"] for s in ("class_aware", "class_blind", "long_context")]
        extra = [float(sum(1 for o in others if o == cj)), float(pr["long_context"]["judgement"] == "unanswered"),
                 float(pr["final_agentic"]["judgement"] == "abstain"),
                 float(bool(pr["comparator"].get("matchedPid")) and pr["comparator"].get("matchedPid") == pr["class_aware"].get("matchedPid"))]
        rows.append({"uid": u["id"], "item": u["itemId"], "f2": f2, "f1": None if f2 is None else f2 + extra,
                     "correct": cj == u["goldJudgement"]})
    correct = {r["uid"]: r["correct"] for r in rows}

    # M2 on gold.
    p2 = {r["uid"]: (None if r["f2"] is None else float(predict(m2, np.array([r["f2"]]))[0])) for r in rows}
    # M1: grouped 5-fold cross-fitting.
    items = sorted({r["item"] for r in rows})
    perm = np.random.default_rng(SPEC_DATA["seed"]).permutation(len(items))
    fold_of = {items[j]: pos % 5 for pos, j in enumerate(perm)}
    p1: dict[str, float | None] = {r["uid"]: None for r in rows}
    fold_models = []
    for k in range(5):
        tr = [r for r in rows if fold_of[r["item"]] != k and r["f1"] is not None]
        te = [r for r in rows if fold_of[r["item"]] == k and r["f1"] is not None]
        m = fit_lr(np.array([r["f1"] for r in tr]), np.array([float(r["correct"]) for r in tr]))
        fold_models.append({"fold": k, "nTrain": len(tr), "nTest": len(te), **m})
        for r, p in zip(te, predict(m, np.array([r["f1"] for r in te]))):
            p1[r["uid"]] = float(p)
    m1_all = fit_lr(np.array([r["f1"] for r in rows if r["f1"] is not None]), np.array([float(r["correct"]) for r in rows if r["f1"] is not None]))

    ev2, ev1 = evaluate(p2, correct), evaluate(p1, correct)
    pred_label = {u["id"]: u["predictions"]["comparator"]["judgement"] for u in units}
    for ev, probs in ((ev2, p2), (ev1, p1)):
        ev["bandComposition"] = composition(probs, correct, pred_label)
        ev["withinLabelAUC"] = within_label_auc(probs, correct, pred_label)
    out = {"version": "confidence-v1", "specSha256": spec_sha, "frozenSha256": frozen_sha, "evaluatedUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "order": ["spec written", "M2 fitted on dev and frozen", "gold labels read", "M1 cross-fitted", "evaluation"],
           "models": {
               "M2": {"id": "M2", "name": SPEC_DATA["models"]["M2"]["name"], "label": "fitted on the 30-item dev set, frozen before gold evaluation",
                      "features": M2_FEATURES, **m2, "fittedOn": SPEC_DATA["models"]["M2"]["fit"], "evaluatedOn": "gold v1, 412 comparator units",
                      "use": SPEC_DATA["models"]["M2"]["use"], "eval": ev2},
               "M1": {"id": "M1", "name": SPEC_DATA["models"]["M1"]["name"], "label": "cross-validated on gold",
                      "features": M2_FEATURES + M1_EXTRA, **m1_all, "weightsNote": "weights shown are the all-gold refit; per-unit scores are out-of-fold",
                      "folds": fold_models, "fittedOn": SPEC_DATA["models"]["M1"]["fit"], "evaluatedOn": "gold v1, out-of-fold", "use": SPEC_DATA["models"]["M1"]["use"],
                      "eval": ev1}},
           "bandThresholds": SPEC_DATA["cut_points"],
           "units": {r["uid"]: {"M2": {"p": p2[r["uid"]], "band": band(p2[r["uid"]])}, "M1": {"p": p1[r["uid"]], "band": band(p1[r["uid"]])},
                                "correct": r["correct"]} for r in rows}}
    write_json(MODEL, out)
    write_report(out, frozen)
    for mid in ("M2", "M1"):
        e = out["models"][mid]["eval"]
        print(mid, "ECE %.3f Brier %.3f experimental=%s %s" % (e["ece"], e["brier"], e["experimental"], e["experimentalReasons"]))
        for b in e["bands"]:
            print("   ", b["band"], b["n"], None if b["accuracy"] is None else round(b["accuracy"], 3), b["wilsonCI"] and [round(x, 3) for x in b["wilsonCI"]])
    return 0


def write_report(out: dict, frozen: dict) -> None:
    L = ["# Confidence calibration report (§8.2)", "",
         f"- Spec `ui/src/data/confidence_spec_v1.json` sha256 `{out['specSha256']}`.",
         f"- M2 frozen in `ui/src/data/confidence_frozen_v1.json` sha256 `{out['frozenSha256']}` at {frozen['frozenUtc']} (before gold evaluation, {out['evaluatedUtc']}).",
         "- Unit: one comparator class unit; correct = comparator judgement equals gold. `unsure` / parse failure = Abstain.",
         "- Caveats: single-expert gold; Flash-Lite-class model; 412 units, so intervals are wide.", ""]
    for mid in ("M2", "M1"):
        m = out["models"][mid]
        e = m["eval"]
        L += [f"## {mid}: {m['name']} ({m['label']})", "", f"- Fitted on: {m['fittedOn']}. Used for: {m['use']}.",
              f"- Base rate (all 412 units): {e['baseRate']['correct']}/{e['baseRate']['n']} = {e['baseRate']['accuracy']:.3f} "
              f"[{e['baseRate']['wilsonCI'][0]:.3f}, {e['baseRate']['wilsonCI'][1]:.3f}].",
              f"- ECE (10 bins) {e['ece']:.3f}; Brier {e['brier']:.3f}. Raw band counts {e['rawBandCounts']}; merged: {e['mergedBands'] or 'none'}.",
              f"- **Status: {'EXPERIMENTAL' if e['experimental'] else 'calibrated'}**" + (f" ({'; '.join(e['experimentalReasons'])})" if e['experimental'] else "") + ".", "",
              "| Band | n | correct | accuracy | Wilson 95% |", "|---|---|---|---|---|"]
        for b in e["bands"]:
            acc = "—" if b["accuracy"] is None else f"{b['accuracy']:.3f}"
            ci = "—" if not b["wilsonCI"] else f"[{b['wilsonCI'][0]:.3f}, {b['wilsonCI'][1]:.3f}]"
            L.append(f"| {b['band']}{' (hidden: n < 20)' if b['hidden'] else ''} | {b['n']} | {b['correct']} | {acc} | {ci} |")
        op = e["operatingPoint"]
        if op["answered"]:
            L += ["", f"Operating point (fixed in the spec): answer only at High → coverage {op['coverage']:.3f} ({op['answered']}/412), "
                      f"accuracy {op['accuracy']:.3f} [{op['wilsonCI'][0]:.3f}, {op['wilsonCI'][1]:.3f}]."]
        else:
            L += ["", "Operating point (answer only at High): no unit reached High."]
        comp = e["bandComposition"]
        L += ["", "Band composition by predicted label (correct/n):", ""]
        for b in ("High", "Medium", "Low", "Abstain"):
            if b in comp:
                L.append(f"- {b}: " + ", ".join(f"`{lab}` {v['correct']}/{v['n']}" for lab, v in sorted(comp[b].items())))
        L += ["", "Within-label AUC (does the score separate right from wrong *within* a predicted label?): " +
              "; ".join(f"`{lab}` {('%.3f' % v['auc']) if v['auc'] is not None else 'n/a'} (right {v['nRight']}, wrong {v['nWrong']})"
                        for lab, v in e["withinLabelAUC"].items()) + "."]
        L += ["", "Weights (standardised features):", "", "| feature | weight |", "|---|---|"]
        L += [f"| {f} | {w:+.3f} |" for f, w in zip(m["features"], m["weights"])] + [f"| (intercept) | {m['intercept']:+.3f} |", ""]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
