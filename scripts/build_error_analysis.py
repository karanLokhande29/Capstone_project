#!/usr/bin/env python3
"""P5-001 addendum: T1 per-class results, confusion structure and documented failure cases (no LLM calls).

    python3 scripts/build_error_analysis.py

Reads the stored P4 run outputs (data/rag_runs/, not released; regenerate with scripts/run_p4.py), the gold sets and
the P3-002 per-answer scores, and writes reports/final/error_analysis_v1.json plus reports/tables/12_t1_per_class.md
and reports/tables/13_error_analysis.md.

Example selection is fixed in advance, never by eye: within each error type, the qualifying cases are sorted by id and
the first two are shown. Every example is a pointer (paragraph_id, character offsets, run file) plus an excerpt of at
most 25 words (P5-001 task 3).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.candidates import wilson_interval  # noqa: E402
from src.common.config import load_config  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.eval import t1_eval as TE  # noqa: E402
from src.eval.ci_format import fmt_bound  # noqa: E402
from src.rag import pipeline as PL  # noqa: E402
from src.release.rbi_text import shorten_words as shorten  # noqa: E402  (counts words as the copied-text check does)

RUNS = ROOT / "data" / "rag_runs"
BENCH = ROOT / "data" / "benchmark"
MIN_N = 5
LLM_SYSTEMS = ("class_blind", "class_aware", "final_agentic", "ablation_a", "long_context")
LAB = {"majority": "Majority", "p2002_candidates": "P2-002 candidates", "class_blind": "Class-blind LLM",
       "class_aware": "Class-aware LLM", "final_agentic": "Final agentic", "ablation_a": "Class-blind + verifier",
       "long_context": "Long-context (100K)"}
DISAGREE_HIGH, DISAGREE_LOW = 0.5, 0.5  # RePASs composite thresholds for the T4 human-vs-metric disagreement rule


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def rate(k: int, n: int) -> dict:
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "value": k / n if n else None, "wilson_95": [lo, hi]}


def rate_s(r: dict) -> str:
    if not r["n"]:
        return "0/0"
    return f"{r['k']}/{r['n']} = {r['value']:.3f} [{fmt_bound(r['wilson_95'][0], signed=False)}, {fmt_bound(r['wilson_95'][1], signed=False)}]"


def span_pointer(it: dict) -> dict:
    sp = it["obligation_span"]
    return {"paragraph_id": sp["paragraph_id"], "offsets": sp["units"], "excerpt": shorten(" ".join(sp["text"].split()), 25)}


def logs(system_dir: str) -> dict[str, dict]:
    d = RUNS / system_dir
    return {json.loads(p.read_text())["item_id"]: json.loads(p.read_text()) for p in sorted(d.glob("t1_*.json"))}


def main() -> int:
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    gold = jl(BENCH / "t1" / "t1_validated_v1.jsonl")
    by_id = {g["item_id"]: g for g in gold}
    cands = {r["source_candidate_id"]: r for r in jl(BENCH / "t1" / "t1_candidate_benchmark_v1.jsonl")}
    maj, p2 = TE.majority_predictions(gold), TE.p2002_predictions(gold, cands)
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

    L = {s: logs(f"t1_{s}") for s in ("class_blind", "class_aware", "final_agentic", "ablation_a")}
    L["long_context"] = logs("t1_long_context_cap100k")
    finals = {"majority": as_final(maj, {}), "p2002_candidates": as_final(p2, mapping),
              **{s: {k: v["final"] for k, v in L[s].items()} for s in L}}

    # ---- per-class (source entity class) flag accuracy, and `different` recall per compared class
    classes = sorted({g["entity_class"] for g in gold})
    per_class: dict = {}
    for s, fin in finals.items():
        rows = {}
        for c in classes:
            its = [g for g in gold if g["entity_class"] == c and g["item_id"] in fin]
            if len(its) < MIN_N:
                rows[c] = {"n": len(its), "insufficient_n": True}
                continue
            rows[c] = {"flag_accuracy": rate(sum(fin[g["item_id"]]["flag"] == g["differential_flag"] for g in its), len(its))}
        per_class[s] = rows
    judg: dict = {}
    for s, fin in finals.items():
        units = [(g, c) for g in gold if g["item_id"] in fin for c in sorted(g["compared_classes"])]
        pred = lambda g, c: (fin[g["item_id"]]["per_class"].get(c) or {}).get("judgement", "unsure")  # noqa: E731
        judg[s] = {lab: {"recall": rate(sum(pred(g, c) == lab for g, c in units if g["per_class_judgement"][c] == lab),
                                        sum(1 for g, c in units if g["per_class_judgement"][c] == lab)),
                         "predicted_instead": dict(Counter(pred(g, c) for g, c in units
                                                           if g["per_class_judgement"][c] == lab and pred(g, c) != lab))}
                   for lab in ("same", "different", "none")}

    # ---- (a) `different` judgements missed
    diff_units = [(g, c) for g in gold for c in sorted(g["compared_classes"]) if g["per_class_judgement"][c] == "different"]
    missed_all = [(g, c) for g, c in diff_units
                  if all(g["item_id"] in finals[s] and (finals[s][g["item_id"]]["per_class"].get(c) or {}).get("judgement") != "different"
                         for s in LLM_SYSTEMS)]
    ex_a = []
    for g, c in sorted(missed_all, key=lambda x: (x[0]["item_id"], x[1]))[:2]:
        ex_a.append({"item_id": g["item_id"], "source_class": g["entity_class"], "compared_class": c,
                     "gold_matched_paragraph_id": g["matched_paragraph_id"].get(c), "source": span_pointer(g),
                     "predictions": {LAB[s]: (finals[s][g["item_id"]]["per_class"].get(c) or {}).get("judgement") for s in finals},
                     "run_files": [f"data/rag_runs/t1_{s if s != 'long_context' else 'long_context_cap100k'}/t1_{g['item_id'][3:].replace('::', '_')}.json"
                                   for s in LLM_SYSTEMS]})
    a = {"gold_different_units": len(diff_units), "missed_by_every_llm_system": len(missed_all),
         "per_system_recall": {LAB[s]: judg[s]["different"]["recall"] for s in finals},
         "per_system_predicted_instead": {LAB[s]: judg[s]["different"]["predicted_instead"] for s in finals}, "examples": ex_a}

    # ---- (b) verifier abstentions on judgements / items that were correct before the retry
    b: dict = {}
    for s in ("final_agentic", "ablation_a"):
        abst_units = right_before = invalid_unsure = 0
        items_flip = []
        for k, lg in sorted(L[s].items()):
            g = by_id[k]
            first = lg["steps"][0]["per_class"]
            fin = lg["final"]["per_class"]
            for c in sorted(g["compared_classes"]):
                if (fin.get(c) or {}).get("judgement") == "unsure" and not (fin.get(c) or {}).get("abstained"):
                    invalid_unsure += 1
                if (fin.get(c) or {}).get("abstained"):
                    abst_units += 1
                    right_before += (first.get(c) or {}).get("judgement") == g["per_class_judgement"][c]
            first_flag = PL.derive({c: {"judgement": (v or {}).get("judgement", "unsure")} for c, v in first.items()}, g["entity_class"])["flag"]
            if first_flag == g["differential_flag"] and lg["final"]["flag"] != g["differential_flag"]:
                items_flip.append(k)
        ex = []
        for k in items_flip[:2]:
            lg, g = L[s][k], by_id[k]
            ex.append({"item_id": k, "source": span_pointer(g), "gold_flag": g["differential_flag"],
                       "first_pass_flag": g["differential_flag"], "final_flag": lg["final"]["flag"],
                       "abstained_classes": sorted(c for c, v in lg["final"]["per_class"].items() if v.get("abstained")),
                       "gold_judgements": g["per_class_judgement"],
                       "first_pass_judgements": {c: (v or {}).get("judgement") for c, v in lg["steps"][0]["per_class"].items()},
                       "run_file": f"data/rag_runs/t1_{s}/t1_{k[3:].replace('::', '_')}.json"})
        b[LAB[s]] = {"abstained_judgements": abst_units, "unsure_from_invalid_output": invalid_unsure, "abstained_judgements_correct_before_retry": right_before,
                     "items_flag_correct_before_retry_wrong_after": len(items_flip), "items_scored": len(L[s]), "examples": ex}

    # ---- (c) long-context errors by gold retention (same computation as scripts/run_p4.py report)
    from scripts.run_p4 import load_prompts, load_resources

    res, extra = load_resources(cfg, resolver)
    prompts = load_prompts(cfg)
    cap = 100000
    lc_rows = []
    for k, lg in sorted(L["long_context"].items()):
        g = by_id[k]
        golds = [g["matched_paragraph_id"][c] for c in g["compared_classes"]
                 if g["per_class_judgement"][c] in ("same", "different") and g["matched_paragraph_id"].get(c)]
        msgs, info = PL.long_context_messages(prompts, res, g, max_input_tokens=cap, paras_by_md=extra["paras_by_md"])
        body = msgs[1]["content"]
        kept = [x for x in golds if f"[{x}]" in body]
        group = "no gold matched paragraph" if not golds else ("all gold kept" if len(kept) == len(golds) else "at least one gold cut")
        lc_rows.append({"item_id": k, "group": group, "gold_paragraphs": len(golds), "kept": len(kept),
                        "prompt_tokens_est": info["input_chars"] // 4, "gold_flag": g["differential_flag"],
                        "pred_flag": lg["final"]["flag"], "correct": lg["final"]["flag"] == g["differential_flag"]})
    c_counts = {grp: {"items": sum(1 for r in lc_rows if r["group"] == grp),
                      "flag_errors": sum(1 for r in lc_rows if r["group"] == grp and not r["correct"])}
                for grp in ("all gold kept", "at least one gold cut", "no gold matched paragraph")}
    ex_c = []
    for grp in ("all gold kept", "at least one gold cut"):
        for r in [r for r in lc_rows if r["group"] == grp and not r["correct"]][:1]:
            g = by_id[r["item_id"]]
            ex_c.append({**r, "source": span_pointer(g),
                         "gold_judgements": g["per_class_judgement"],
                         "pred_judgements": {c: v.get("judgement") for c, v in L["long_context"][r["item_id"]]["final"]["per_class"].items()},
                         "run_file": f"data/rag_runs/t1_long_context_cap100k/t1_{r['item_id'][3:].replace('::', '_')}.json"})
    c = {"cap": cap, "scored": len(lc_rows), "by_retention": c_counts, "examples": ex_c}

    # ---- (d) T3 temporal filter OFF errors
    dropped = set(json.loads((BENCH / "t3" / "t3_dropped_after_check2_v1.json").read_text())["dropped_items"])
    t3 = [i for i in jl(BENCH / "t3" / "t3_items_v1.jsonl") if i["t3_id"] not in dropped]
    off = {json.loads(p.read_text())["t3_id"]: json.loads(p.read_text()) for p in sorted((RUNS / "t3_temporal_off").glob("T3-*.json"))}
    errs = [i for i in t3 if off[i["t3_id"]]["pred_status"] != i["gold_status"]]
    d = {"scored": len(t3), "status_errors": len(errs),
         "pred_status_filter_off": dict(Counter(off[i["t3_id"]]["pred_status"] for i in t3)),
         "gold_status": dict(Counter(i["gold_status"] for i in t3)),
         "errors_by_gold_status_and_side": dict(Counter(f"gold {i['gold_status']} ({i['side']} the effective date) → predicted {off[i['t3_id']]['pred_status']}" for i in errs)),
         "examples": [{"t3_id": i["t3_id"], "paragraph_id": i["paragraph_id"], "as_of": i["as_of"], "side": i["side"],
                       "effective_date": i["effective"]["date"], "gold_status": i["gold_status"],
                       "gold_governing_instrument": i["gold_governing_instrument"],
                       "pred_status": off[i["t3_id"]]["pred_status"], "pred_governing_instrument": off[i["t3_id"]]["pred_governing_instrument"],
                       "corpus_version": i["corpus_version"], "run_file": f"data/rag_runs/t3_temporal_off/{i['t3_id']}.json"}
                      for i in sorted(errs, key=lambda x: x["t3_id"])[:2]]}

    # ---- (e) T4: RePASs vs human `faithful`
    per = [r for r in jl(BENCH / "t4" / "t4_per_answer_v1.jsonl") if r["on_sheet"]]
    answers = {}
    for t in ("genuine", "concatenated", "adv_negated", "adv_offtopic"):
        for r in jl(BENCH / "t4" / f"t4_answers_{t}_v1.jsonl"):
            answers[(r["question_id"], t)] = r["answer"]
    hi_lo = [r for r in per if r["faithful"] == 2 and r["composite_score"] < DISAGREE_LOW]
    lo_hi = [r for r in per if r["faithful"] == 0 and r["composite_score"] >= DISAGREE_HIGH]

    def t4ex(r):
        return {"question_id": r["question_id"], "answer_type": r["answer_type"], "faithful": r["faithful"],
                "answers_question": r["answers_question"], "repass_composite": r["composite_score"],
                "entailment": r["entailment_score"], "contradiction": r["contradiction_score"],
                "obligation_coverage": r["obligation_coverage_score"],
                "answer_excerpt": shorten(" ".join(answers[(r["question_id"], r["answer_type"])].split()), 25),
                "answer_pointer": f"release/data/t4/answers_{r['answer_type']}.jsonl, {r['question_id']}"}

    e = {"rated": len(per), "rule": f"human faithful = 2 with RePASs composite < {DISAGREE_LOW}, or faithful = 0 with composite >= {DISAGREE_HIGH} "
                 "(a display threshold chosen for this analysis after scoring, not pre-registered)",
         "faithful_2_metric_low": len(hi_lo), "faithful_0_metric_high": len(lo_hi),
         "faithful_2_metric_low_by_type": dict(Counter(r["answer_type"] for r in hi_lo)),
         "faithful_0_metric_high_by_type": dict(Counter(r["answer_type"] for r in lo_hi)),
         "examples": [t4ex(r) for r in sorted(hi_lo, key=lambda r: (r["question_id"], r["answer_type"]))[:2]]
                     + [t4ex(r) for r in sorted(lo_hi, key=lambda r: (r["question_id"], r["answer_type"]))[:2]]}

    m4 = json.loads((ROOT / "reports" / "p4001_metrics_v1.json").read_text())
    conf = {LAB[s]: m4["t1"]["systems"][s]["confusion"] for s in finals if s in m4["t1"]["systems"]}
    flag_f1 = {LAB[s]: m4["t1"]["systems"][s]["flag_f1_per_label"] for s in finals if s in m4["t1"]["systems"]}
    out = {"version": "v1", "selection_rule": "qualifying cases sorted by id; first two shown (first one per retention group for long-context)",
           "per_class_flag_accuracy": {LAB[s]: v for s, v in per_class.items()},
           "judgement_recall": {LAB[s]: v for s, v in judg.items()},
           "flag_confusion": conf, "flag_f1_per_label": flag_f1,
           "a_different_missed": a, "b_verifier_abstentions": b, "c_long_context": c, "d_t3_filter_off": d, "e_t4_metric_vs_human": e}
    (ROOT / "reports" / "final").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports" / "final" / "error_analysis_v1.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_tables(out)
    print("wrote reports/final/error_analysis_v1.json, reports/tables/12_t1_per_class.md, reports/tables/13_error_analysis.md")
    return 0


def _tab(header, rows):
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows])


def write_tables(o: dict) -> None:
    systems = list(o["per_class_flag_accuracy"])
    classes = sorted(next(iter(o["per_class_flag_accuracy"].values())))
    L = ["# Table 12. T1 per-class results and confusion structure (106 items; long-context on its 102)\n",
         "Flag accuracy by source entity class, k/n [Wilson 95%]. Classes with n < 5 would be listed as insufficient n; "
         "every source class here has n >= 7.\n"]
    for s in systems:
        L.append(f"## {s}\n")
        L.append(_tab(["Source class", "Flag accuracy"],
                      [[c, "insufficient n" if o["per_class_flag_accuracy"][s][c].get("insufficient_n") else
                        rate_s(o["per_class_flag_accuracy"][s][c]["flag_accuracy"])] for c in classes]))
        L.append("")
    L.append("## Judgement recall by gold label (class-row units)\n")
    L.append(_tab(["System", "same", "different", "none"],
                  [[s] + [rate_s(o["judgement_recall"][s][lab]["recall"]) for lab in ("same", "different", "none")] for s in systems]))
    L.append("\n## Flag confusion (rows gold, columns predicted), from reports/p4001_metrics_v1.json\n")
    for s, cm in o["flag_confusion"].items():
        cols = list(next(iter(cm.values())))
        L.append(f"**{s}**\n\n" + _tab(["gold \\ pred", *cols], [[g, *[cm[g][p] for p in cols]] for g in cm]) + "\n")
    (ROOT / "reports" / "tables" / "12_t1_per_class.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    a, b, c, d, e = (o[k] for k in ("a_different_missed", "b_verifier_abstentions", "c_long_context", "d_t3_filter_off", "e_t4_metric_vs_human"))
    M = ["# Table 13. Error analysis: failure cases (pointers plus ≤ 25-word excerpts)\n",
         f"Selection rule: {o['selection_rule']}. Full text: rehydrate the paragraph from its pointer (release/rehydrate.py).\n",
         f"## (a) Missed `different` judgements\n\n{a['gold_different_units']} gold `different` class-row units; "
         f"{a['missed_by_every_llm_system']} are missed by every LLM system (class-blind, class-aware, final agentic, class-blind + verifier, long-context).\n",
         _tab(["System", "`different` recall", "Predicted instead"],
              [[s, rate_s(r), ", ".join(f"{k} {v}" for k, v in sorted(a["per_system_predicted_instead"][s].items()))] for s, r in a["per_system_recall"].items()])]
    for x in a["examples"]:
        M.append(f"\n- `{x['item_id']}` ({x['source_class']} vs {x['compared_class']}; gold `different`, gold counterpart "
                 f"`{x['gold_matched_paragraph_id']}`). Source {x['source']['paragraph_id']} {x['source']['offsets']}: “{x['source']['excerpt']}”. "
                 "Predictions: " + ", ".join(f"{k} `{v}`" for k, v in x["predictions"].items()) + ".")
    M.append("\n## (b) Verifier abstentions on judgements that were correct before the retry\n")
    M.append(_tab(["System", "Abstained judgements", "…correct on the first pass", "Items: flag right on first pass, wrong after"],
                  [[s, v["abstained_judgements"], v["abstained_judgements_correct_before_retry"],
                    f"{v['items_flag_correct_before_retry_wrong_after']} of {v['items_scored']}"] for s, v in b.items()]))
    for s, v in b.items():
        for x in v["examples"]:
            M.append(f"\n- {s}, `{x['item_id']}`: gold and first-pass flag `{x['gold_flag']}`, final flag `{x['final_flag']}`; "
                     f"abstained on {', '.join(x['abstained_classes'])}. Source {x['source']['paragraph_id']} {x['source']['offsets']}: “{x['source']['excerpt']}”.")
    M.append(f"\n## (c) Long-context errors by gold retention (cap {c['cap']:,} tokens, {c['scored']} scored)\n")
    M.append(_tab(["Retention group", "Items", "Flag errors"], [[g, v["items"], v["flag_errors"]] for g, v in c["by_retention"].items()]))
    for x in c["examples"]:
        M.append(f"\n- `{x['item_id']}` ({x['group']}: {x['kept']}/{x['gold_paragraphs']} gold paragraphs in the prompt; about "
                 f"{x['prompt_tokens_est']:,} tokens): gold `{x['gold_flag']}`, predicted `{x['pred_flag']}`. Source "
                 f"{x['source']['paragraph_id']} {x['source']['offsets']}: “{x['source']['excerpt']}”.")
    M.append(f"\n## (d) T3 with the temporal filter OFF\n\n{d['status_errors']} status errors on {d['scored']} items. Predicted statuses "
             f"with the filter off: " + ", ".join(f"{k} {v}" for k, v in sorted(d["pred_status_filter_off"].items())) + "; gold: "
             + ", ".join(f"{k} {v}" for k, v in sorted(d["gold_status"].items())) + ".\n")
    M.append(_tab(["Error", "Count"], [[k, v] for k, v in sorted(d["errors_by_gold_status_and_side"].items())]))
    for x in d["examples"]:
        M.append(f"\n- `{x['t3_id']}`: {x['paragraph_id']} as of {x['as_of']} ({x['side']} the effective date {x['effective_date']}); "
                 f"gold `{x['gold_status']}` governed by `{x['gold_governing_instrument']}`; predicted `{x['pred_status']}` / "
                 f"`{x['pred_governing_instrument']}` (corpus version: {x['corpus_version']}).")
    M.append(f"\n## (e) T4: RePASs vs the human `faithful` rating ({e['rated']} rated answers)\n\nRule: {e['rule']}. "
             f"faithful 2 but metric low: {e['faithful_2_metric_low']} ({e['faithful_2_metric_low_by_type']}); "
             f"faithful 0 but metric high: {e['faithful_0_metric_high']} ({e['faithful_0_metric_high_by_type']}).")
    for x in e["examples"]:
        M.append(f"\n- `{x['question_id']}` ({x['answer_type']}): faithful {x['faithful']}, answers_question {x['answers_question']}; "
                 f"RePASs {x['repass_composite']:.3f} (entailment {x['entailment']:.3f}, contradiction {x['contradiction']:.3f}, "
                 f"obligation coverage {x['obligation_coverage']:.3f}). Answer excerpt ({x['answer_pointer']}): “{x['answer_excerpt']}”.")
    (ROOT / "reports" / "tables" / "13_error_analysis.md").write_text("\n".join(M) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
