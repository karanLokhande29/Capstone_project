#!/usr/bin/env python3
"""Phase 4 core (FINAL-MASTER-AND-PAPER Part A) on gold v1: every system + the frozen structured comparator.

    python3 scripts/run_phase4_scoring.py      -> reports/results_v2.json (results_v1.json is unchanged)

What it computes:
1. Every P4 system and baseline, through the gold-version-aware harness. This must reproduce
   `reports/p4001_metrics_v1.json` exactly (regression).
2. The comparator from its sealed predictions (`data/rag_runs/sealed_phase4/comparator_t1_gold_v1/`):
   - judgement metrics are primary (amendment 3);
   - the flag is derived with the v3.6 rule (any `different` → class-specific; any `same` → shared; all `none` → absent;
     otherwise ambiguous), and flag metrics are secondary.
3. Pre-registered comparisons (amendment 3 / the replan): comparator − class-aware and comparator − P2-002.
   - Paired item-resampled CIs on judgement macro-F1, `different` F1 and `different` recall.
   - Flag metrics through `src/rag/analysis.t1_paired`.
4. "Missed by every LLM system", under two definitions:
   - A: all five systems answered;
   - B: only the systems that answered are counted.
   Plus how many of those units the comparator gets right.
5. The retrieval-vs-reasoning split for every system and the comparator. The comparator's context is the two shown
   candidates; long-context retention uses the rebuilt prompt.

No model calls. Bootstrap: 2,000 item resamples, seed p4.seeds.bootstrap (= the published T1 table's seed).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark import t1 as T  # noqa: E402
from src.common.config import load_config  # noqa: E402
from src.eval import different_taxonomy as DT  # noqa: E402
from src.eval import t1_regold as G  # noqa: E402
from src.eval.ci_format import ci_reading  # noqa: E402
from src.eval.metrics import f1_scores  # noqa: E402
from src.rag import analysis as A  # noqa: E402
from src.rag import comparator as CMP  # noqa: E402

T1 = ROOT / "data/benchmark/t1"
RUNS = ROOT / "data/rag_runs"
CMP_DIR = RUNS / "sealed_phase4/comparator_t1_gold_v1"
OUT = ROOT / "reports/results_v2.json"
JUDG = ("same", "different", "none")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def comparator_finals(gold) -> tuple[dict, dict]:
    frozen = json.loads((ROOT / "configs/comparator_v1/FROZEN.json").read_text())
    finals, stats = {}, {"units": 0, "parse_failures": 0, "prompt_hash_mismatch": 0}
    for g in gold:
        per = {}
        for c in sorted(g["compared_classes"]):
            p = CMP_DIR / f"{g['item_id'].replace('::', '_')}__{c.replace(' ', '_')}.json"
            if not p.exists():
                continue
            r = json.loads(p.read_text())
            stats["units"] += 1
            stats["parse_failures"] += bool(r.get("parse_problems"))
            stats["prompt_hash_mismatch"] += r.get("prompt_sha256") != frozen["sha256"]
            per[c] = {"judgement": r["judgement"], "matched_paragraph_id": r.get("matched_paragraph_id")}
        if len(per) == len(g["compared_classes"]):
            d = T.derive_flag({k: v["judgement"] for k, v in per.items()})
            finals[g["item_id"]] = {"flag": d["flag"] or T.FLAG_AMBIGUOUS, "per_class": per}
    return finals, stats


def judgement_paired(u_a, u_b, *, resamples: int, seed: int) -> dict:
    """System A − system B on judgement macro-F1, `different` F1 and `different` recall; items resampled together."""
    common = [i for i in u_a["items"] if i in set(u_b["items"])]
    ia = {k: j for j, k in enumerate(u_a["items"])}
    ib = {k: j for j, k in enumerate(u_b["items"])}

    def rows(u, idx_map):
        by = {}
        for i, g, p in u["judg"]:
            by.setdefault(u["items"][i], []).append((g, p))
        return [by[k] for k in common]

    ra, rb = rows(u_a, ia), rows(u_b, ib)
    for x, y in zip(ra, rb):
        assert [g for g, _ in x] == [g for g, _ in y], "gold units must align"

    def stats(rr, idx):
        g = [gg for j in idx for gg, _ in rr[j]]
        p = [pp for j in idx for _, pp in rr[j]]
        f = f1_scores(g, p, JUDG)
        nd = sum(1 for x in g if x == "different")
        rec = (sum(1 for x, y in zip(g, p) if x == y == "different") / nd) if nd else float("nan")
        return {"judgement_macro_f1": f["macro_f1"], "different_f1": f["per_label"]["different"]["f1"], "different_recall": rec}

    n = len(common)
    full = list(range(n))
    pa, pb = stats(ra, full), stats(rb, full)
    rng = np.random.default_rng(seed)
    draws = {k: [] for k in pa}
    for idx in rng.integers(0, n, size=(resamples, n)):
        sa, sb = stats(ra, idx), stats(rb, idx)
        for k in draws:
            d = sa[k] - sb[k]
            if not np.isnan(d):
                draws[k].append(d)
    out = {"n_items": n, "n_units": sum(len(x) for x in ra)}
    for k in pa:
        lo, hi = np.percentile(draws[k], [2.5, 97.5])
        out[k] = {"a": pa[k], "b": pb[k], "diff": pa[k] - pb[k], "ci": [float(lo), float(hi)],
                  "reading": ci_reading(float(lo), float(hi)), "resamples_used": len(draws[k])}
    return out


def missed(U: dict, systems: tuple, cmp_u: dict | None) -> dict:
    """Both definitions, over the gold `different` units; plus how many of the missed units the comparator gets right."""
    def unit_preds(u):
        seen, out = {}, {}
        for i, g, p in u["judg"]:
            iid = u["items"][i]
            k = seen.get(iid, 0)
            seen[iid] = k + 1
            out[(iid, k)] = (g, p)
        return out

    P = {s: unit_preds(U[s]) for s in systems if s in U}
    keys = sorted({k for s in P for k, (g, _) in P[s].items() if g == "different"})
    A_ = [k for k in keys if all(k in P[s] for s in P) and all(P[s][k][1] != "different" for s in P)]
    B_ = [k for k in keys if any(k in P[s] for s in P) and all(P[s][k][1] != "different" for s in P if k in P[s])]
    res = {"gold_different_units": len(keys), "systems": list(P),
           "A_all_five_answered": {"missed": len(A_), "definition": "every LLM system answered the item and none said `different`"},
           "B_answered_only": {"missed": len(B_), "definition": "every LLM system that answered the item missed it (items long-context never answered included)"}}
    if cmp_u is not None:
        C = unit_preds(cmp_u)
        for key, lst in (("A_all_five_answered", A_), ("B_answered_only", B_)):
            res[key]["comparator_correct"] = sum(1 for k in lst if k in C and C[k][1] == "different")
            res[key]["comparator_answered"] = sum(1 for k in lst if k in C)
    return res


def main() -> int:
    cfg = load_config(None)
    R, seed = int(cfg["retrieval"]["eval"]["bootstrap_resamples"]), int(cfg["p4"]["seeds"]["bootstrap"])
    gold_path = T1 / "t1_validated_v1.jsonl"
    gold = G.read_jsonl(gold_path)
    need = {g["source_candidate_id"] for g in gold}
    cands = {}
    with (T1 / "t1_candidate_benchmark_v1.jsonl").open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            if r["source_candidate_id"] in need:
                cands[r["source_candidate_id"]] = r
    t1 = G.evaluate(gold, cands, RUNS, resamples=R, seed=seed)
    ref = json.loads((ROOT / "reports/p4001_metrics_v1.json").read_text())["t1"]
    same = lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    regression = {"systems": all(same(t1["systems"][s], ref["systems"][s]) for s in ref["systems"]),
                  "paired": all(same(t1["paired"][k], ref["paired"][k]) for k in ref["paired"])}
    if not all(regression.values()):
        raise SystemExit(f"STOP: harness no longer reproduces the v1 T1 table: {regression}")

    # Unit sets for every system (the harness's own predictions loader).
    preds = G.baseline_predictions(gold, cands)
    for s in G.LLM_SYSTEMS:
        preds[s] = G.finals(RUNS, s)
    lc_name, lc_cap = G.long_context_run(RUNS)
    preds["long_context"] = G.finals(RUNS, lc_name)
    cmp_finals, cmp_stats = comparator_finals(gold)
    U = {s: A.t1_units(gold, p) for s, p in preds.items()}
    U_cmp = A.t1_units(gold, cmp_finals)
    kw = {"resamples": R, "seed": seed}
    comparator = {"metrics": A.t1_metrics(U_cmp, **kw), "different": G.different_diagnostics(U_cmp), "run": cmp_stats,
                  "flag_rule": "v3.6 derivation from the comparator's per-class judgements (secondary metrics)",
                  "frozen": json.loads((ROOT / "configs/comparator_v1/FROZEN.json").read_text())}
    pre = {f"comparator − {b}": {"judgement": judgement_paired(U_cmp, U[b], **kw), "flag": A.t1_paired(U_cmp, U[b], **kw)}
           for b in ("class_aware", "p2002_candidates")}
    miss = missed(U, ("class_blind", "class_aware", "final_agentic", "ablation_a", "long_context"), U_cmp)

    # Retrieval vs reasoning (gold `different` units).
    from scripts.run_p4 import load_prompts
    from src.rag import pipeline as PL
    from src.retrieval import index as IX

    corpus = IX.load_corpus(ROOT / "data/processed")
    pos = {pid: i for i, pid in enumerate(corpus.ids)}
    text_of = lambda pid: corpus.texts[pos[pid]] if pid in pos else ""
    manifest = [json.loads(l) for l in (ROOT / "data/metadata/document_manifest.jsonl").read_text().splitlines() if l.strip()]
    doc = {r["document_id"]: {"title": r.get("title") or "", "entity_class": r.get("entity_class_raw"),
                              "subject_family": r.get("subject_family")} for r in manifest}
    paras_by_md: dict = {}
    for p in sorted((ROOT / "data/processed").glob("md_*.jsonl")):
        rows = sorted((json.loads(x) for x in p.read_text().splitlines() if x.strip()), key=lambda r: r.get("position") or 0)
        paras_by_md[p.stem] = [{"paragraph_id": r["paragraph_id"], "clause_path": r.get("clause_path")} for r in rows]
    res = PL.Resources(corpus=corpus, bm25=None, emb=None, encoder=None, doc=doc,
                       function_headings=frozenset(cfg["matching"]["function_headings"]), temporal=None,
                       paragraph_max_chars=int(cfg["p4"]["retrieval"]["paragraph_max_chars"]))
    prompts = load_prompts(cfg)
    by_id = {g["item_id"]: g for g in gold}
    sheet = T.read_sheet(T1 / T.PASS1_SHEET)
    shown = {(r["item_id"], r["target_class"]): {pid for pid, _ in CMP.parse_candidates(r["target_candidates"])}
             for r in sheet if r["row_type"] == T.ROW_CLASS}
    runs = {s: {json.loads(p.read_text())["item_id"]: json.loads(p.read_text()) for p in sorted((RUNS / f"t1_{run}").glob("t1_*.json"))}
            for s, run in {"class_blind": "class_blind", "class_aware": "class_aware", "final_agentic": "final_agentic",
                           "ablation_a": "ablation_a", "long_context": lc_name}.items()}
    runs["comparator"] = {k: {"final": v} for k, v in cmp_finals.items()}
    lc_body: dict = {}

    def in_context(system, u):
        if not u["gold_matched"]:
            return None
        if system == "comparator":
            return u["gold_matched"] in shown.get((u["item_id"], u["target_class"]), set())
        if system == "long_context":
            iid = u["item_id"]
            if iid not in lc_body:
                lc_body[iid] = PL.long_context_messages(prompts, res, by_id[iid], max_input_tokens=lc_cap,
                                                        paras_by_md=paras_by_md)[0][1]["content"]
            return f"[{u['gold_matched']}]" in lc_body[iid]
        return u["gold_matched"] in DT.context_ids_rag(u["record"].get("steps"), u["target_class"])

    split = DT.analyse(DT.different_units(gold), runs, in_context, text_of)
    five = ("class_blind", "class_aware", "final_agentic", "ablation_a", "long_context")
    split_summary = {"per_system": split["per_system"],
                     "five_llm_systems_total": {"errors": sum(split["per_system"][s]["errors"] for s in five),
                                                "reasoning": sum(split["per_system"][s]["failure_types"].get("reasoning", 0) for s in five),
                                                "retrieval": sum(split["per_system"][s]["failure_types"].get("retrieval", 0) for s in five)},
                     "missed_by_every_system_incl_comparator": split["missed_by_every_system"],
                     "context_definition": {"rag": "gold matched paragraph among the ids shown in any attempt for that class",
                                            "long_context": "gold id present in the rebuilt 100K prompt (P4 retention rule)",
                                            "comparator": "gold id among the two shown candidates"}}

    dev = {}
    for name, pat in (("run1_superseded", "comparator_dev_eval_run1_*.json"), ("final", "comparator_dev_eval_2*.json")):
        f = sorted((ROOT / "reports/private/final_push/p1").glob(pat))
        if f:
            dev[name] = json.loads(f[-1].read_text())
    ledger = json.loads((ROOT / "data/llm_cache/quota_ledger.json").read_text())

    v1 = json.loads((ROOT / "reports/results_v1.json").read_text())
    out = {"version": "v2", "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "based_on": {"results_v1_sha256": sha(ROOT / "reports/results_v1.json"), "gold": str(gold_path.relative_to(ROOT)),
                        "gold_sha256": sha(gold_path)},
           "ci_rule": v1.get("ci_rule"), "tables": v1["tables"],
           "phase4": {"gold": "t1_validated_v1 (106 items, single expert)", "bootstrap": {"resamples": R, "seed": seed},
                      "regression_vs_p4001": regression, "t1_systems": t1["systems"], "t1_paired": t1["paired"],
                      "t1_different": t1["different"], "long_context_same_items": t1.get("long_context_same_items"),
                      "comparator": comparator, "comparator_dev": dev, "preregistered_comparisons": pre,
                      "missed_by_every_llm_system": miss, "retrieval_vs_reasoning": split_summary,
                      "llm_calls": {"model": cfg["llm"]["p4_model"], "ledger": ledger.get(cfg["llm"]["p4_model"]),
                                    "comparator_t1_calls": cmp_stats["units"]}}}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float) + "\n")
    m = comparator["metrics"]
    print(f"regression vs p4001: {regression}")
    print(f"comparator: units {cmp_stats['units']}, parse failures {cmp_stats['parse_failures']}, items {m['n_items']}; "
          f"different F1 {comparator['different']['different_f1']:.3f}, recall {comparator['different']['different_recall']:.3f}; "
          f"judgement macro-F1 {m['judgement_macro_f1']['value']:.3f}; 3-way flag F1 {m['flag_macro_f1']['value']:.3f}; coverage {m['coverage']['value']:.3f}")
    for k, v in pre.items():
        j = v["judgement"]
        print(f"{k}: different F1 {j['different_f1']['diff']:+.3f} {[round(x, 3) for x in j['different_f1']['ci']]} ({j['different_f1']['reading']}); "
              f"macro-F1 {j['judgement_macro_f1']['diff']:+.3f} ({j['judgement_macro_f1']['reading']})")
    print(f"missed: A {miss['A_all_five_answered']}, B {miss['B_answered_only']}")
    print(f"retrieval/reasoning (comparator): {split['per_system'].get('comparator')}")
    print(f"-> {OUT.relative_to(ROOT)} (sha256 {sha(OUT)[:16]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
