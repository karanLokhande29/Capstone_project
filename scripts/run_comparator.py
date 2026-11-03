#!/usr/bin/env python3
"""Pairwise structured comparator: dev set, gated dev run, freeze, Phase 4 estimate.

    python3 scripts/run_comparator.py plan-dev                       # no API: dev units from the separate IRR-30 set
    python3 scripts/run_comparator.py dev --gate "gate: comparator dev run"   # ONLY after Karan types that gate
    python3 scripts/run_comparator.py evaluate-dev                   # no API: dev metrics vs the IRR consensus
    python3 scripts/run_comparator.py freeze                         # prompt + rule sha256 -> amendments v2 (before any T1 eval)
    python3 scripts/run_comparator.py estimate-phase4                # no API: Phase 4 call count vs the 480 soft cap

Dev set disclosure: the separate 30-item three-rater (IRR) set, drawn outside the T1 sample; never the 106 gold items,
the 17 rejected items or the 93/30 packet items (all of which are in the sample).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark import t1 as T  # noqa: E402
from src.common.config import get_required, load_config  # noqa: E402
from src.rag import comparator as CMP  # noqa: E402

T1 = ROOT / "data/benchmark/t1"
PROMPTS = ROOT / "configs/comparator_v1"
FROZEN = PROMPTS / "FROZEN.json"
DEV_RUNS = ROOT / "data/rag_runs/comparator_dev_irr30"
RUN1 = ROOT / "data/rag_runs/comparator_dev_irr30_run1"
RUN1_PROMPTS = PROMPTS / "dev_run1_superseded"
OUT = ROOT / "reports/private/final_push/p1"
AMEND_V1 = ROOT / "docs/protocol/reliability_plan_v2_amendments.md"
AMEND_V1_SHA = "dd17ec6561ed32e2884ee5643607d861ba69c7c082f3f1e1337438fa19f53995"
AMEND_V2 = ROOT / "docs/protocol/reliability_plan_v2_amendments_v2.md"
DEV_CAP = 100
GATE = "gate: comparator dev run"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def dev_units() -> tuple[list[dict], dict[tuple[str, str], str]]:
    sample = {json.loads(l)["item_id"] for l in (T1 / "p2004_sample_v1.jsonl").read_text().splitlines() if l.strip()}
    rows = T.read_sheet(T1 / T.IRR_BLANK_REFERENCE)
    cons = [json.loads(l) for l in (T1 / "p2004_irr_consensus_v1.jsonl").read_text().splitlines() if l.strip()]
    ids = {c["item_id"] for c in cons}
    if ids & sample:
        raise SystemExit(f"STOP: dev items overlap the T1 sample: {sorted(ids & sample)[:3]}")
    src = {r["item_id"]: r for r in rows if r["row_type"] == T.ROW_ITEM}
    cand = {(r["item_id"], r["target_class"]): r["target_candidates"] for r in rows if r["row_type"] == T.ROW_CLASS}
    units, gold = [], {}
    for c in sorted(cons, key=lambda x: x["item_id"]):
        if c["not_obligation"]:
            continue
        for cls, j in sorted(c["judgements"].items()):
            units.append({"item_id": c["item_id"], "source_class": c["source_class"],
                          "source_text": src[c["item_id"]]["source_span"], "target_class": cls,
                          "candidates": CMP.parse_candidates(cand[(c["item_id"], cls)])})
            gold[(c["item_id"], cls)] = j
    return units, gold


def cmd_plan_dev() -> int:
    units, gold = dev_units()
    from collections import Counter
    print(f"dev units: {len(units)} (cap {DEV_CAP}); items {len({u['item_id'] for u in units})}; "
          f"candidates per unit {Counter(len(u['candidates']) for u in units)}; dev gold {Counter(gold.values())}")
    print("overlap with the 123-item T1 sample (106 gold + 17 rejected; includes all 93/30 packet items): 0")
    return 0


def _unit_path(u) -> Path:
    return DEV_RUNS / f"{u['item_id'].replace('::', '_')}__{u['target_class'].replace(' ', '_')}.json"


def cmd_dev(gate: str | None) -> int:
    if gate != GATE:
        print(f"REFUSED: the dev run needs Karan's gate phrase ('{GATE}'), passed as --gate")
        return 1
    if FROZEN.exists():
        print("REFUSED: the comparator is already frozen; no further dev runs")
        return 1
    units0, _ = dev_units()
    if RUN1.exists() and DEV_RUNS.exists() and all(_unit_path(u).exists() for u in units0):
        print("REFUSED: one revision already used (run 1 archived, run 2 complete); no further dev runs")
        return 1
    from scripts.run_p4 import make_llm
    from src.common.paths import PathResolver
    from src.llm import client as L

    cfg = load_config(None)
    resolver = PathResolver.from_config(cfg)
    model = str(get_required(cfg, "llm.p4_model"))
    p4 = cfg["p4"]
    units, _ = dev_units()
    todo = [u for u in units if not _unit_path(u).exists()]
    ledger = L.QuotaLedger(resolver.working_root / p4["ledger"], soft_cap=int(p4["soft_cap"]))
    print(f"model: {model} (llm.p4_model); settings as P4: json_mode={p4['json_mode']}, thinking={p4.get('thinking')}, "
          f"temperature={cfg['llm'].get('temperature', 0)}, max_output_tokens={p4['max_output_tokens']}, fallback=none")
    print(f"calls: {len(todo)} (units {len(units)}, already done {len(units) - len(todo)}; cap {DEV_CAP})")
    print(f"quota ledger, today ({ledger.quota_day()} Pacific): {ledger.used(model)} used of soft cap {p4['soft_cap']}")
    if len(todo) > DEV_CAP:
        print("REFUSED: more calls than the cap")
        return 1
    L.load_env()
    prov = L.GeminiProvider(L.require_key("GEMINI_API_KEY"))
    listed = {m.id for m in prov.list_models()}
    served = model in listed
    print(f"model-list call: {model} {'IS' if served else 'is NOT'} served ({len(listed)} models listed)")
    if not served:
        print("STOP: the P4 model is not served; not switching models")
        return 2
    client, ledger = make_llm(cfg, resolver, run_id=f"comparator_dev_{_now()}")
    client.max_calls = min(DEV_CAP, len(todo))
    prompts = CMP.Prompts(PROMPTS)
    DEV_RUNS.mkdir(parents=True, exist_ok=True)
    done = 0
    for u in todo:
        try:
            r = CMP.compare_unit(client, prompts, u, max_output_tokens=int(p4["max_output_tokens"]))
        except (L.QuotaPaused, L.CallCapReached, L.LLMError) as exc:
            print(f"STOPPED after {done} calls: {type(exc).__name__}: {str(exc)[:200]}")
            break
        r["prompt_sha256"] = CMP.frozen_hashes(PROMPTS)
        r["written_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _unit_path(u).write_text(json.dumps(r, ensure_ascii=False, indent=1))
        done += 1
    print(f"dev run: {done} calls made; ledger now {ledger.used(model)}")
    return cmd_evaluate_dev()


def cmd_evaluate_dev() -> int:
    units, gold = dev_units()
    res = [json.loads(_unit_path(u).read_text()) for u in units if _unit_path(u).exists()]
    if not res:
        print("no dev results yet")
        return 1
    m = CMP.evaluate(res, gold)
    m["note"] = "DEV SET = separate IRR-30 consensus (not T1 gold); development evidence only"
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"comparator_dev_eval_{_now()}.json"
    p.write_text(json.dumps(m, indent=1) + "\n")
    print(json.dumps(m, indent=1))
    print(f"-> {p.relative_to(ROOT)}")
    return 0


def cmd_freeze() -> int:
    if FROZEN.exists():
        print(f"already frozen: {FROZEN.read_text()}")
        return 0
    units, _ = dev_units()
    have = [u for u in units if _unit_path(u).exists()]
    if not have:
        print("REFUSED: freeze comes after the dev run")
        return 1
    if CMP.sha256_file(AMEND_V1) != AMEND_V1_SHA:
        raise SystemExit("STOP: amendments v1 changed")
    hashes = CMP.frozen_hashes(PROMPTS)
    evals = sorted(p for p in OUT.glob("comparator_dev_eval_*.json") if "_run1_" not in p.name)
    dev = json.loads(evals[-1].read_text()) if evals else {}
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cfg = load_config(None)
    _f = lambda x: f"{x:.3f}" if isinstance(x, (int, float)) else str(x)
    run1_text = ""
    r1 = sorted(OUT.glob("comparator_dev_eval_run1_*.json"))
    if RUN1.exists() and r1:
        d1 = json.loads(r1[-1].read_text())
        h1 = {f: CMP.sha256_file(RUN1_PROMPTS / f) for f in CMP.PROMPT_FILES}
        run1_text = (
            f"- **Dev run 1 (superseded; kept in `data/rag_runs/comparator_dev_irr30_run1/`, prompt in `configs/comparator_v1/dev_run1_superseded/`):** "
            f"prompt sha256 {h1}; 92 calls; judgement macro-F1 {_f(d1.get('judgement_macro_f1'))}, `different` F1 "
            f"{_f(d1.get('per_label', {}).get('different', {}).get('f1'))}, recall {_f(d1.get('different_recall'))}; confusion {d1.get('confusion')}.\n"
            "- **The one revision (a clear field-extraction bug, not a score change):** the prompt did not say that source and candidates are "
            "for different entity classes by design, so the model marked `actor` as 'differs' for the entity class itself (e.g. 'the CIC' vs "
            "'the AIFI'). `actor` triggered 20 of the 25 gold-same → predicted-different units, and was the sole trigger in 10. The revised "
            "system prompt adds one paragraph: treat the entity class itself as equal; compare actor and scope only beyond it. The rule file "
            "is unchanged. The dev set was rerun once (92 calls).\n")
    entry = (
        "\n## Amendment 3: 2 Oct, pairwise structured comparator frozen (before any T1 evaluation)\n\n"
        "- **Targeted experiment:** aimed at the v1-based finding that gold `different` class units are missed by every LLM system: "
        "56 of 78 when all five systems answered (the report's definition), or 58 of 78 also counting 2 units on the 4 items "
        "long-context never answered. It will be recomputed on gold v2 in Phase 4.\n"
        f"- **Method:** one call per (item, compared class), on model `{cfg['llm']['p4_model']}` with the P4 settings. "
        "The model extracts 13 fields from both sides and compares them field by field. The fixed rule `src/rag/comparator_rule.py` "
        "decides same / different / none (precedence same > different > none). The model never gives the verdict.\n"
        "- **Development set:** the separate 30-item three-rater (IRR) set, drawn outside the T1 sample. Its adjudicated "
        f"consensus gives {len(units)} class units. No T1 gold, rejected or packet item was used.\n"
        + run1_text +
        f"- **Dev result, final prompt (development evidence only):** judgement macro-F1 {_f(dev.get('judgement_macro_f1'))}, "
        f"`different` F1 {_f(dev.get('per_label', {}).get('different', {}).get('f1'))}, `different` recall {_f(dev.get('different_recall'))}, "
        f"n units {dev.get('n_units')}, parse failures {dev.get('parse_failures')}; confusion (gold → predicted) {dev.get('confusion')}.\n"
        "- **Frozen sha256:**\n"
        + "".join(f"  - `{k}`: `{v}`\n" for k, v in hashes.items())
        + f"- **Frozen at:** {stamp}. Nothing is changed after freezing. Any T1 run refuses if a hash differs.\n")
    body = AMEND_V1.read_text(encoding="utf-8")
    head = ("# Amendments to the T1 reliability analysis plan v2 — version 2\n\n"
            f"This version repeats amendments 1–2 unchanged from `reliability_plan_v2_amendments.md` (sha256 `{AMEND_V1_SHA}`, "
            "kept read-only) and adds amendment 3.\n\n---\n\n")
    if AMEND_V2.exists():
        raise SystemExit("STOP: amendments v2 exists")
    AMEND_V2.write_text(head + body + entry, encoding="utf-8")
    AMEND_V2.chmod(0o444)
    FROZEN.write_text(json.dumps({"frozen_at_utc": stamp, "sha256": hashes, "model": cfg["llm"]["p4_model"],
                                  "amendments_v2_sha256": CMP.sha256_file(AMEND_V2)}, indent=1) + "\n")
    for f in (FROZEN, *(PROMPTS / x for x in CMP.PROMPT_FILES)):
        f.chmod(0o444)
    print(f"FROZEN: {hashes}\namendments v2 sha256 {CMP.sha256_file(AMEND_V2)}")
    return 0


def cmd_estimate() -> int:
    cfg = load_config(None)
    gold = [json.loads(l) for l in (T1 / "t1_validated_v1.jsonl").read_text().splitlines() if l.strip()]
    units = sum(len(g["compared_classes"]) for g in gold)
    miss = sorted((ROOT / "reports/private/final_push/reeval").glob("missing_predictions_rejected_*.json"))
    rej = json.loads(miss[-1].read_text())["per_system"] if miss else {}
    first = sum(1 for s in ("class_blind", "class_aware", "long_context") if s in rej) * 17
    verifier_extra = sum((rej[s]["observed_calls_per_item"]["mean"] or 0) * rej[s]["n_missing"]
                         for s in ("final_agentic", "ablation_a") if s in rej)
    low = units + first + round(verifier_extra)
    high = units + sum(v["estimated_calls_needed"]["at_max"] or 0 for v in rej.values())
    cap = int(cfg["p4"]["soft_cap"])
    print(f"Phase 4 estimate on {cfg['llm']['p4_model']} (no calls made):")
    print(f"  comparator over all gold v1 class pairs: {units} calls (1 per item × compared class)")
    print(f"  rejected-item system reruns (17 items): {first} first answers (class-blind, class-aware, long-context; the verifier systems reuse "
          f"the cached first answer) + ~{verifier_extra:.0f} verifier retries; upper bound {high - units}")
    print(f"  TOTAL: {low}–{high} calls vs soft cap {cap}/quota day -> "
          + ("fits one quota day" if high <= cap else ("fits only at the low end, with no margin for retries: plan TWO quota days" if low <= cap
                                                       else "does NOT fit one quota day: plan two")))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan-dev")
    d = sub.add_parser("dev")
    d.add_argument("--gate")
    sub.add_parser("evaluate-dev")
    sub.add_parser("freeze")
    sub.add_parser("estimate-phase4")
    a = ap.parse_args()
    return {"plan-dev": cmd_plan_dev, "evaluate-dev": cmd_evaluate_dev, "freeze": cmd_freeze,
            "estimate-phase4": cmd_estimate}.get(a.cmd, lambda: cmd_dev(a.gate))()


if __name__ == "__main__":
    raise SystemExit(main())
