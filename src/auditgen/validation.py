"""The validation box shown in every output's About section.

- Applicability: precision / recall of the register rule against T1 gold v1 (106 items x 11 core classes, ``applies_to``).
- Temporal status: accuracy against the 52 scored T3 items. Partly circular: the generator and the T3 gold share the
  amendment parser.
- Calendar extraction: precision on 30 random extractions, from a blank check sheet; "pending" until it is labelled.
- Gap analysis: a synthetic check only (a test policy built from known obligations, some removed).
- Differential: the benchmark's ``different`` miss rate, as a caution.
"""

from __future__ import annotations

import csv
import json
import math
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.auditgen import calendar_extract as CAL
from src.auditgen import temporal as TMP
from src.auditgen.corpus import ROOT, CorpusStore, excerpt, read_jsonl

STATE = ROOT / "data/auditgen_state"
CAL_SHEET = STATE / "calendar_check_sheet_v1.csv"
CAL_SEED = 20261015
GAP_SEED = 20261016
VALIDATION_FILE = STATE / "validation_v1.json"


def wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def applicability(store: CorpusStore) -> dict[str, Any]:
    gold = read_jsonl(ROOT / "data/benchmark/t1/t1_validated_v1.jsonl")
    tp = fp = fn = 0
    for g in gold:
        pred = {store.docs[g["md_id"]]["entity_class"]} & set(store.core_classes)
        truth = set(g["applies_to"]) & set(store.core_classes)
        tp += len(pred & truth)
        fp += len(pred - truth)
        fn += len(truth - pred)
    return {"n_items": len(gold), "units": f"{len(gold)} items x {len(store.core_classes)} core classes",
            "precision": round(tp / (tp + fp), 3) if tp + fp else None, "precision_ci": wilson(tp, tp + fp),
            "recall": round(tp / (tp + fn), 3) if tp + fn else None, "recall_ci": wilson(tp, tp + fn),
            "tp": tp, "fp": fp, "fn": fn,
            "note": "The rule assigns a paragraph to its Direction's class; it misses obligations the text extends to other "
                    "classes (3 of the 106 gold items)."}


def temporal(store: CorpusStore) -> dict[str, Any]:
    t3 = ROOT / "data/benchmark/t3"
    items = read_jsonl(t3 / "t3_items_v1.jsonl")
    drop = set(json.loads((t3 / "t3_dropped_after_check2_v1.json").read_text())["dropped_items"])
    items = [i for i in items if i["t3_id"] not in drop]
    ok = sum(TMP.t3_prediction(store, i) == i["gold_status"] for i in items)
    return {"n_items": len(items), "accuracy": round(ok / len(items), 3), "accuracy_ci": wilson(ok, len(items)), "correct": ok,
            "note": "Partly circular: the T3 gold and the generator use the same amendment parser."}


def build_calendar_sheet(store: CorpusStore, path: Path = CAL_SHEET, n: int = 30) -> dict[str, Any]:
    """A blank check sheet of n random calendar extractions over the 11 core classes (seeded). Never overwritten."""
    if path.exists():
        return {"path": path.relative_to(ROOT).as_posix(), "created": False}
    pool = []
    core = set(store.core_classes)
    for c in store.candidates():
        if (store.docs.get(c["document_id"]) or {}).get("entity_class") not in core:
            continue
        sent = store.obligation_sentence(c)
        for k, e in enumerate(CAL.extract(sent)):
            pool.append((c, k, e, sent))
    rng = random.Random(CAL_SEED)
    pick = rng.sample(pool, min(n, len(pool)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["check_id", "paragraph_id", "direction_title", "source_url", "extracted", "kind", "confidence", "phrase",
                    "correct (y/n)", "notes"])
        for i, (c, k, e, sent) in enumerate(pick, 1):
            w.writerow([f"CAL-{i:02d}", c["paragraph_id"], store.title(c["document_id"]), store.url(c["document_id"]),
                        CAL.summary([e]), e["kind"], e["confidence"], e["phrase"], "", ""])
    return {"path": path.relative_to(ROOT).as_posix(), "created": True, "pool": len(pool), "n": len(pick)}


def calendar(path: Path = CAL_SHEET) -> dict[str, Any]:
    if not path.exists():
        return {"status": "pending", "note": "check sheet not built"}
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    labels = [r["correct (y/n)"].strip().lower()[:1] for r in rows]
    if not rows or any(l not in ("y", "n") for l in labels):
        return {"status": "pending", "sheet": path.relative_to(ROOT).as_posix(), "labelled": sum(l in ("y", "n") for l in labels),
                "n": len(rows), "note": "Precision is shown once Karan labels the 30-row check sheet."}
    k = labels.count("y")
    return {"status": "done", "sheet": path.relative_to(ROOT).as_posix(), "n": len(rows), "precision": round(k / len(rows), 3),
            "precision_ci": wilson(k, len(rows))}


def differential_caution() -> dict[str, Any]:
    r = json.loads((ROOT / "reports/results_v2.json").read_text())["phase4"]["missed_by_every_llm_system"]
    missed, total = r["A_all_five_answered"]["missed"], r["gold_different_units"]
    return {"gold_different_units": total, "missed_by_every_llm_system": missed, "miss_rate": round(missed / total, 3),
            "note": f"RBI-ObliBench: {missed} of {total} gold 'different' units were missed by every LLM system; "
                    "differential calls here are not LLM-based but are equally unvalidated: review every one."}


# -- synthetic gap check ---------------------------------------------------------------------------

DISTRACTORS = [
    "The Company shall maintain a register of visitors at every office and review it at least once a year.",
    "Employees are encouraged to complete the annual wellness survey circulated by Human Resources.",
    "Travel claims must be submitted with original receipts within the month in which the travel took place.",
    "The canteen committee meets every quarter to review the menu and the hygiene inspection report.",
    "Marketing material shall follow the brand guidelines approved by the Corporate Communications team.",
    "Office assets such as laptops shall be returned to the IT helpdesk when an employee leaves the Company.",
    "The fire safety officer will conduct an evacuation drill twice a year at each premises.",
    "Interns are assigned a mentor who meets them at least fortnightly during the internship.",
    "Parking slots are allotted to employees on a first-come, first-served basis each financial year.",
    "The Company supports volunteering and allows two days of paid volunteering leave per year.",
]
_SUBJ = re.compile(r"\b(?:the|a|every|each|all)\s+(?:bank|banks|SFB|SFBs|NBFC|NBFCs|payments bank|regulated entity|regulated entities|RE|REs)\b", re.I)


def to_policy_clause(sentence: str) -> str:
    s = re.sub(r"^\s*(?:\(?[0-9ivxa-z]{1,4}[.)]\s*)+", "", " ".join(sentence.split()))
    s = _SUBJ.sub("the Company", s)
    s = re.sub(r"\bshall\b", "will", s)
    return s[0].upper() + s[1:] if s else s


def synthetic_gap(store: CorpusStore, cfg: Mapping[str, Any], register, *, n: int = 60, removed_share: float = 0.25,
                  models=None) -> dict[str, Any]:
    from src.auditgen import gap_analysis as GAP

    rng = random.Random(GAP_SEED)
    pool = [r for r in register if not r["hidden"]]
    sample = rng.sample(pool, min(n, len(pool)))
    removed = set(r["obligation_id"] for r in rng.sample(sample, int(round(len(sample) * removed_share))))
    by_id = {c["candidate_id"]: c for c in store.candidates()}
    kept_clauses = [to_policy_clause(store.obligation_sentence(by_id[r["obligation_id"]])) for r in sample if r["obligation_id"] not in removed]
    lines = kept_clauses + DISTRACTORS
    rng.shuffle(lines)
    policy = "SYNTHETIC TEST POLICY (built from known obligations; not a real policy)\n\n" + "\n\n".join(f"{i + 1}. {t}" for i, t in enumerate(lines))
    res = GAP.analyse(store, cfg, sample, [("synthetic_policy.txt", policy.encode())], models=models)
    res.pop("_texts", None)
    pred = {x["obligation_id"]: x["coverage"] for x in res["rows"]}
    flagged_missing = {k for k, v in pred.items() if v == "missing"}
    not_covered = {k for k, v in pred.items() if v != "covered"}
    tp = len(flagged_missing & removed)
    tp2 = len(not_covered & removed)
    kept = [r["obligation_id"] for r in sample if r["obligation_id"] not in removed]
    return {"kind": "synthetic", "n_obligations": len(sample), "removed": len(removed), "kept": len(kept),
            "distractor_clauses": len(DISTRACTORS), "seed": GAP_SEED,
            "missing_precision": round(tp / len(flagged_missing), 3) if flagged_missing else None,
            "missing_recall": round(tp / len(removed), 3) if removed else None,
            "missing_recall_ci": wilson(tp, len(removed)),
            "not_covered_precision": round(tp2 / len(not_covered), 3) if not_covered else None,
            "not_covered_recall": round(tp2 / len(removed), 3) if removed else None,
            "kept_marked_covered": round(sum(pred[k] == "covered" for k in kept) / len(kept), 3) if kept else None,
            "counts": res["counts"], "thresholds": res["thresholds"],
            "note": ("Synthetic check only: the test policy restates known obligations almost verbatim (subject replaced, "
                     "'shall' -> 'will') plus unrelated distractor clauses, so these numbers are an optimistic upper bound "
                     "for real policies, which paraphrase and combine duties.")}


def compute_all(store: CorpusStore, cfg: Mapping[str, Any], *, sfb_register=None, models=None) -> dict[str, Any]:
    out = {"computed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rules_version": cfg["version"],
           "corpus_sha256": store.snapshot.sha256, "applicability": applicability(store), "temporal": temporal(store),
           "calendar_sheet": build_calendar_sheet(store), "differential": differential_caution()}
    if sfb_register is not None:
        out["gap_analysis"] = synthetic_gap(store, cfg, sfb_register, models=models)
    STATE.mkdir(parents=True, exist_ok=True)
    VALIDATION_FILE.write_text(json.dumps(out, indent=1))
    return out


def box(store: CorpusStore | None = None) -> dict[str, Any]:
    """The validation box: cached numbers plus the live calendar-sheet status."""
    v = json.loads(VALIDATION_FILE.read_text()) if VALIDATION_FILE.exists() else {}
    return {"applicability": v.get("applicability", {"status": "not computed"}),
            "temporal": v.get("temporal", {"status": "not computed"}),
            "calendar": calendar(),
            "gap_analysis": v.get("gap_analysis", {"status": "not computed"}),
            "differential": v.get("differential", {"status": "not computed"}),
            "computed_utc": v.get("computed_utc"), "computed_on_corpus": v.get("corpus_sha256")}
