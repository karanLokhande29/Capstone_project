"""T1 harness (P3-001): score predictions against ``t1_validated_v1.jsonl``.

Two tasks, both read from the validated set:

* **flag**: the item's ``differential_flag`` (shared | class-specific | absent),
  one unit per item; Macro-F1 over the three labels.
* **judgement**: each compared class's ``per_class_judgement`` (same | different
  | none), one unit per (item, compared class); per-label F1 and Macro-F1.

CIs are seeded percentile bootstraps over **items**: a judgement resample takes
all compared classes of each drawn item, since they share one source text.

Baselines:

* ``majority``: the most frequent flag and the most frequent judgement **of the
  validated set itself** (in-sample, so slightly optimistic by construction).
* ``p2002_candidates`` ("dense within-family"): the P2-002 status per compared
  class, ``matched`` -> counterpart (it cannot tell same from different),
  ``below_threshold`` -> none. Its flag, derived over the item's compared
  classes as in P2-004, is only ``absent`` or ``shared_or_class_specific``.
  It is scored three ways, all reported:
    1. **native (collapsed)**: gold collapsed to what the baseline can express
       (flag: absent vs present; judgement: none vs counterpart);
    2. **fixed mapping (3-label)**: ``shared_or_class_specific`` -> the
       validated set's most frequent non-absent flag, ``counterpart`` -> its
       most frequent counterpart judgement (both stated, both in-sample);
    3. **oracle upper bound (3-label)**: an undecided prediction counts as
       correct whenever gold is one of the labels it covers. No system without
       the gold labels can score higher with these predictions.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np

from src.eval.metrics import bootstrap_indices, confusion, f1_scores

FLAGS = ("shared", "class-specific", "absent")
JUDGEMENTS = ("same", "different", "none")
FLAG_PRESENT, FLAG_UNDECIDED = "present", "shared_or_class_specific"
COUNTERPART = "counterpart"
COLLAPSE_FLAG = {"shared": FLAG_PRESENT, "class-specific": FLAG_PRESENT, "absent": "absent",
                 FLAG_UNDECIDED: FLAG_PRESENT}
COLLAPSE_JUDGEMENT = {"same": COUNTERPART, "different": COUNTERPART, "none": "none", COUNTERPART: COUNTERPART}
COVERS = {FLAG_UNDECIDED: {"shared", "class-specific"}, COUNTERPART: {"same", "different"}}


class T1EvalError(ValueError):
    pass


def gold_units(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    flags, judgements = [], []
    for i, it in enumerate(items):
        if it.get("label_status") != "validated":
            raise T1EvalError(f"{it['item_id']}: not validated")
        flags.append({"item": i, "item_id": it["item_id"], "gold": it["differential_flag"]})
        for cls in sorted(it["compared_classes"]):
            judgements.append({"item": i, "item_id": it["item_id"], "class": cls,
                               "gold": it["per_class_judgement"][cls]})
    return {"flags": flags, "judgements": judgements, "n_items": len(items)}


# -- baselines ----------------------------------------------------------------


def majority_predictions(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    units = gold_units(items)
    flag = Counter(u["gold"] for u in units["flags"]).most_common(1)[0][0]
    judgement = Counter(u["gold"] for u in units["judgements"]).most_common(1)[0][0]
    return {
        "flags": [flag] * len(units["flags"]),
        "judgements": [judgement] * len(units["judgements"]),
        "rule": {"flag": flag, "judgement": judgement, "source": "majority of the validated set itself (in-sample)"},
    }


def p2002_predictions(items: Sequence[Mapping[str, Any]],
                      candidates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """``candidates``: source_candidate_id -> P2-004 candidate record (``per_class_candidate``)."""
    flags, judgements = [], []
    for it in items:
        status = candidates[it["source_candidate_id"]]["per_class_candidate"]
        per = {}
        for cls in sorted(it["compared_classes"]):
            st = status.get(cls)
            if st == "matched":
                per[cls] = COUNTERPART
            elif st == "below_threshold":
                per[cls] = "none"
            else:
                raise T1EvalError(f"{it['item_id']} / {cls}: P2-002 status {st!r} for a compared class")
        flags.append(FLAG_UNDECIDED if COUNTERPART in per.values() else "absent")
        judgements.extend(per[c] for c in sorted(per))
    return {"flags": flags, "judgements": judgements,
            "rule": {"matched": COUNTERPART, "below_threshold": "none",
                     "flag": "shared_or_class_specific if any compared class matched, else absent"}}


# -- scoring ------------------------------------------------------------------


def _resolve(pred: Sequence[str], gold: Sequence[str], mapping: Mapping[str, str] | None, oracle: bool) -> list[str]:
    out = []
    for p, g in zip(pred, gold):
        if p in COVERS:
            if oracle:
                p = g if g in COVERS[p] else sorted(COVERS[p])[0]
            elif mapping is not None:
                p = mapping[p]
        out.append(p)
    return out


def _score_task(gold: Sequence[str], pred: Sequence[str], labels: Sequence[str], item_of: Sequence[int],
                n_items: int, *, resamples: int, seed: int, pred_labels: Sequence[str]) -> dict[str, Any]:
    gold_arr, pred_arr = np.array(gold, dtype=object), np.array(pred, dtype=object)
    item_arr = np.array(item_of)
    rows_of = [np.flatnonzero(item_arr == i) for i in range(n_items)]
    point = f1_scores(gold, pred, labels)

    def stat(item_idx: np.ndarray) -> tuple[float, dict[str, float]]:
        rows = np.concatenate([rows_of[i] for i in item_idx])
        s = f1_scores(list(gold_arr[rows]), list(pred_arr[rows]), labels)
        return s["macro_f1"], {lab: s["per_label"][lab]["f1"] for lab in labels}

    draws = [stat(idx) for idx in bootstrap_indices(n_items, resamples=resamples, seed=seed)]
    macro = np.array([d[0] for d in draws])

    def ci(arr: np.ndarray) -> list[float]:
        lo, hi = np.percentile(arr, [2.5, 97.5])
        return [float(lo), float(hi)]

    per_label = {}
    for lab in labels:
        per_label[lab] = {**point["per_label"][lab], "f1_ci": ci(np.array([d[1][lab] for d in draws]))}
    return {
        "n_units": len(gold),
        "n_items": n_items,
        "labels": list(labels),
        "macro_f1": point["macro_f1"],
        "macro_f1_ci": ci(macro),
        "accuracy": float(np.mean(gold_arr == pred_arr)),
        "per_label": per_label,
        "confusion": confusion(gold, pred, labels, pred_labels),
    }


def evaluate(items: Sequence[Mapping[str, Any]], predictions: Mapping[str, Any], *, resamples: int,
             seed: int, fixed_mapping: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Score one baseline. Undecided predictions are scored natively, by ``fixed_mapping`` and by oracle."""
    units = gold_units(items)
    gf = [u["gold"] for u in units["flags"]]
    gj = [u["gold"] for u in units["judgements"]]
    fi = [u["item"] for u in units["flags"]]
    ji = [u["item"] for u in units["judgements"]]
    pf, pj = list(predictions["flags"]), list(predictions["judgements"])
    if len(pf) != len(gf) or len(pj) != len(gj):
        raise T1EvalError("prediction counts do not match the gold units")
    n = units["n_items"]
    kw = {"resamples": resamples, "seed": seed}
    undecided = any(p in COVERS for p in pf + pj)
    out: dict[str, Any] = {"rule": predictions.get("rule"), "undecided_predictions": undecided}

    out["native_collapsed"] = {
        "flag": _score_task([COLLAPSE_FLAG[g] for g in gf], [COLLAPSE_FLAG[p] for p in pf],
                            ("absent", FLAG_PRESENT), fi, n, pred_labels=("absent", FLAG_PRESENT), **kw),
        "judgement": _score_task([COLLAPSE_JUDGEMENT[g] for g in gj], [COLLAPSE_JUDGEMENT[p] for p in pj],
                                 ("none", COUNTERPART), ji, n, pred_labels=("none", COUNTERPART), **kw),
    }
    if not undecided:
        out["three_label"] = {
            "flag": _score_task(gf, pf, FLAGS, fi, n, pred_labels=FLAGS, **kw),
            "judgement": _score_task(gj, pj, JUDGEMENTS, ji, n, pred_labels=JUDGEMENTS, **kw),
        }
        return out
    if fixed_mapping is None:
        raise T1EvalError("undecided predictions need a fixed_mapping")
    out["confusion_raw"] = {
        "flag": confusion(gf, pf, FLAGS, (*FLAGS, FLAG_UNDECIDED)),
        "judgement": confusion(gj, pj, JUDGEMENTS, (*JUDGEMENTS, COUNTERPART)),
    }
    out["fixed_mapping"] = {"mapping": dict(fixed_mapping), **{
        "flag": _score_task(gf, _resolve(pf, gf, fixed_mapping, False), FLAGS, fi, n, pred_labels=FLAGS, **kw),
        "judgement": _score_task(gj, _resolve(pj, gj, fixed_mapping, False), JUDGEMENTS, ji, n,
                                 pred_labels=JUDGEMENTS, **kw),
    }}
    out["oracle_upper_bound"] = {
        "flag": _score_task(gf, _resolve(pf, gf, None, True), FLAGS, fi, n, pred_labels=FLAGS, **kw),
        "judgement": _score_task(gj, _resolve(pj, gj, None, True), JUDGEMENTS, ji, n, pred_labels=JUDGEMENTS, **kw),
    }
    return out


def default_fixed_mapping(items: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """The validated set's most frequent non-absent flag and most frequent counterpart judgement."""
    units = gold_units(items)
    flag = Counter(u["gold"] for u in units["flags"] if u["gold"] != "absent").most_common(1)[0][0]
    judgement = Counter(u["gold"] for u in units["judgements"] if u["gold"] != "none").most_common(1)[0][0]
    return {FLAG_UNDECIDED: flag, COUNTERPART: judgement}


def run_baselines(items: Sequence[Mapping[str, Any]], candidates: Mapping[str, Mapping[str, Any]], *,
                  resamples: int, seed: int) -> dict[str, Any]:
    mapping = default_fixed_mapping(items)
    units = gold_units(items)
    return {
        "n_items": units["n_items"],
        "n_judgements": len(units["judgements"]),
        "gold_flag_counts": dict(Counter(u["gold"] for u in units["flags"])),
        "gold_judgement_counts": dict(Counter(u["gold"] for u in units["judgements"])),
        "bootstrap": {"resamples": resamples, "seed": seed, "unit": "item"},
        "baselines": {
            "majority": evaluate(items, majority_predictions(items), resamples=resamples, seed=seed),
            "p2002_candidates": evaluate(items, p2002_predictions(items, candidates), resamples=resamples,
                                         seed=seed, fixed_mapping=mapping),
        },
    }

