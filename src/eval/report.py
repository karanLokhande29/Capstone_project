"""Markdown reports for P3-001: retrieval baselines and T1 baselines."""

from __future__ import annotations

from typing import Any, Mapping

SYSTEM_LABEL = {"bm25": "BM25", "dense": "Dense (class-blind)", "hybrid_rrf": "Hybrid RRF",
                "class_aware": "Class-aware hybrid", "hybrid_minus_source_class": "Hybrid minus source class"}
METRIC_LABEL = {"recall": "Recall@10", "map": "MAP@10", "ndcg": "nDCG@10"}
SET_TITLE = {
    "t2_xclass_t1": "t2_xclass_t1 — main set (P2-004 validated T1 items)",
    "t2_xclass_p2002": "t2_xclass_p2002 — P2-002 validation pairs",
    "t2_supp_p2003": "t2_supp_p2003 — P2-003 FAQ / enforcement alignment rows",
}


def _ci(v: Mapping[str, Any], digits: int = 3) -> str:
    if v.get("mean") is None:
        return "n/a"
    return f"{v['mean']:.{digits}f} [{v['ci_low']:.{digits}f}, {v['ci_high']:.{digits}f}]"


def _signed(v: Mapping[str, Any]) -> str:
    return f"{v['mean']:+.3f} [{v['ci_low']:+.3f}, {v['ci_high']:+.3f}]"


def retrieval_report(r: Mapping[str, Any]) -> str:
    env = r["environment"]
    emb = env["embedding"]
    p = r["protocol"]
    L: list[str] = []
    L.append("# P3-001 — T2 retrieval baselines\n")
    L.append(
        "Four systems over all 76,188 paragraphs, scored on three human-labelled relevance sets. The sets are "
        "built and scored **separately and never pooled**. Each has a known bias, stated beside its results, "
        "and the biases point in different directions, so **no winner is declared across sets**.\n")
    L.append("## Protocol\n")
    L.append(f"- Metrics at cutoff {p['cutoff']}: Recall@10 and MAP@10 (grade ≥ 1 is relevant), nDCG@10 "
             f"with graded gain {p['ndcg_gain']}. Queries with no relevant paragraph are not scored and are counted.")
    L.append(f"- 95% CIs: percentile bootstrap, {p['bootstrap_resamples']} resamples of queries, seed "
             f"{p['bootstrap_seed']}. Every system on a set uses the same draws, so the paired differences are "
             "true paired bootstraps.")
    L.append("- Sensitivity: a clustered bootstrap that resamples source texts instead of queries (several T1 "
             "queries share one obligation text). Those CIs are in `p3001_metrics_v1.json` as `cluster_ci`; "
             "where they change a reading, the text says so.")
    L.append("- Systems keep their top 100. The query's own source paragraph is always excluded.")
    L.append("  - `bm25`: bm25s, method `{method}`, k1 = {k1}, b = {b}, lower-case `{token_regex}` tokens, no "
             "stemming or stopwords.".format(**env["bm25"]))
    L.append(f"  - `dense`: {emb['model_id']} at revision `{emb['model_revision']}` (checked against the Hub), "
             "normalised, whitespace-collapsed text, no query instruction. Class-blind.")
    L.append("  - `hybrid_rrf`: RRF with k = 60 over the BM25 and dense rankings. A paragraph with a BM25 score of 0 "
             "gets no BM25 term.")
    L.append("  - `class_aware`: the same fusion, restricted to paragraphs whose Direction's entity class equals the "
             "query's target class. BM25 and dense are re-ranked inside that set. With no target class it equals "
             "`hybrid_rrf`, and the query is flagged.")
    L.append("  - `hybrid_minus_source_class` (diagnostic, added in P3-002): the class-blind fusion with every "
             "paragraph of the query's **own source class** removed, re-ranked inside what remains. It needs no "
             "target class. With no source class (P2-003's FAQ and enforcement queries come from outside the "
             "corpus) it equals `hybrid_rrf`, and the query is flagged.\n")
    L.append("## What the class-aware gain does and does not show\n")
    L.append("Relevance was labelled only for the counterpart **in the query's target class**. The task scored "
             "here is therefore *retrieval of the target-class counterpart*, and class-blind systems are partly "
             "disadvantaged by construction: the near-identical counterparts they return from other classes (and "
             "from the source class itself) count as misses. The class-aware gain shows the value of knowing the "
             "target class **for this task**. It is not a general class-blind vs class-aware verdict. "
             "`hybrid_minus_source_class` is a fairer diagnostic: it only stops the class-blind system from "
             "returning the source class's own paragraphs. The gap that remains between it and class-aware is "
             "what knowing the specific target class adds.\n")

    for name, s in r["sets"].items():
        q = s["qrels"]
        L.append(f"## {SET_TITLE.get(name, name)}\n")
        L.append(f"**Known bias:** {s['bias']}\n")
        L.append(f"- Queries: {q['queries']}; scored (with a relevant paragraph): **n = {s['n_scored']}**; "
                 f"without a relevant paragraph (not scored): {s['n_unscored_no_relevant']}; distinct source "
                 f"texts: {s['clusters']}.")
        L.append(f"- Relevant pairs: {q['relevant_pairs']} (grade 2: {q['grade_counts']['2']}, grade 1: "
                 f"{q['grade_counts']['1']}).")
        ret = s["retrieval"]
        if "minus_source_class_without_source_class" in ret:
            L.append(f"- Hybrid minus source class: no source class for "
                     f"{ret['minus_source_class_without_source_class']} queries (identical to hybrid there).")
        L.append(f"- Class-aware: no target class for {ret['class_aware_without_target_class']} queries "
                 f"(identical to hybrid there). Relevant paragraphs outside the target class, so the class filter "
                 f"cannot reach them: {len(ret['relevant_outside_target_class'])} queries.")
        if q.get("text_basis"):
            L.append(f"- Query text basis: {q['text_basis']}.")
        if s["n_scored"] < 30:
            L.append(f"- **Small n ({s['n_scored']}).** The CIs are wide; read the direction, not the point estimates.")
        L.append("")
        L.append("| System | " + " | ".join(METRIC_LABEL.values()) + " |")
        L.append("|---|" + "---|" * len(METRIC_LABEL))
        for sys_name, m in s["systems"].items():
            L.append(f"| {SYSTEM_LABEL[sys_name]} | " + " | ".join(_ci(m[k]) for k in METRIC_LABEL) + " |")
        L.append(f"\nEach cell: mean [95% CI], n = {s['n_scored']}.\n")
        L.append("**Paired differences** (same queries, same resamples):\n")
        L.append("| Comparison | " + " | ".join(f"Δ {v}" for v in METRIC_LABEL.values()) + " |")
        L.append("|---|" + "---|" * len(METRIC_LABEL))
        for pair, m in s["paired"].items():
            a, b = pair.split(" - ")
            L.append(f"| {SYSTEM_LABEL[a]} − {SYSTEM_LABEL[b]} | " + " | ".join(_signed(m[k]) for k in METRIC_LABEL) + " |")
        flips = []
        for pair, m in s["paired"].items():
            for k in METRIC_LABEL:
                v = m[k]
                excl = v["ci_low"] > 0 or v["ci_high"] < 0
                cl = v["cluster_ci"]
                cl_excl = cl["ci_low"] > 0 or cl["ci_high"] < 0
                if excl != cl_excl:
                    flips.append(f"{pair} {METRIC_LABEL[k]} (clustered CI [{cl['ci_low']:+.3f}, {cl['ci_high']:+.3f}])")
        L.append("")
        if flips:
            L.append("Under the clustered bootstrap, these differences change whether their CI excludes 0: "
                     + "; ".join(flips) + ".\n")
        else:
            L.append("The clustered bootstrap does not change whether any paired CI excludes 0.\n")
        rows = [(c, v) for c, v in s["by_target_class"].items() if v["reported"]]
        skipped = [f"{c} ({v['n']})" for c, v in s["by_target_class"].items() if not v["reported"]]
        if rows:
            L.append("**By target class** (n ≥ 5), nDCG@10 [95% CI]:\n")
            L.append("| Target class | n | " + " | ".join(SYSTEM_LABEL[x] for x in s["systems"]) + " |")
            L.append("|---|---|" + "---|" * len(s["systems"]))
            for c, v in rows:
                L.append(f"| {c} | {v['n']} | " + " | ".join(_ci(v['systems'][x]['ndcg'], 2) for x in s["systems"]) + " |")
            L.append("")
        if skipped:
            L.append(f"Not broken out (n < 5): {', '.join(skipped)}.\n")

    L.append("## Reading across sets\n")
    L.append("Two sets favour dense by construction (their candidates or pairs were chosen with the same bge "
             "model), and one favours BM25 (its candidates came from TF-IDF). A system that wins on one of these "
             "sets may only be winning because of that set's bias. These are baselines, not a ranking of methods. "
             "The class-aware − hybrid row previews Ablation A (class filter on vs off) on each set separately.\n")
    L.append("The T1-derived queries ask for the counterpart **in one named class**. A class-blind system that "
             "returns a correct counterpart from a different class gets no credit, because only the named class's "
             "counterpart was labelled. That is part of what the class-aware row measures.\n")

    L.append("## Environment\n")
    L.append(f"- Machine: {env['cpu']} ({env['machine']}); OS: {env['os']}; Python {env['python']}.")
    L.append("- Packages: " + ", ".join(f"{k} {v}" for k, v in env["packages"].items() if v) + ".")
    L.append(f"- Embedding device: {env['device']}. {emb['paragraphs']} paragraphs embedded fresh, locally, in "
             f"{(emb.get('total_wall_seconds') or 0) / 60:.1f} min (projected {emb['projected_minutes']} min); "
             f"Kaggle P2-002 embeddings not reused. Truncated at {emb['max_seq_length']} tokens: "
             f"{emb['truncated_paragraphs']} paragraphs.")
    llm = env["llm"]
    L.append(f"- LLM (configured; not used by any baseline here): `llm.model` = `{llm['model']}`, "
             f"`llm.long_context_model` = `{llm['long_context_model']}` (Gemini); fallback `{llm['fallback_model']}` "
             f"(Groq). Version strings from the list endpoints: {llm['model_versions']}.")
    L.append("")
    L.append(f"Generated {r['scored_utc']} by `scripts/run_p3001.py score`.")
    return "\n".join(L) + "\n"


def _row(label: str, view: Mapping[str, Any], labels: tuple[str, ...]) -> str:
    cells = [f"{view['macro_f1']:.3f} [{view['macro_f1_ci'][0]:.3f}, {view['macro_f1_ci'][1]:.3f}]"]
    for lab in labels:
        pl = view["per_label"][lab]
        cells.append(f"{pl['f1']:.3f} [{pl['f1_ci'][0]:.3f}, {pl['f1_ci'][1]:.3f}]")
    return f"| {label} | " + " | ".join(cells) + f" | {view['accuracy']:.3f} |"


def _confusion(title: str, m: Mapping[str, Mapping[str, int]]) -> list[str]:
    preds = list(next(iter(m.values())).keys())
    out = [f"{title} (rows gold, columns predicted):\n", "| gold \\ pred | " + " | ".join(preds) + " |",
           "|---|" + "---|" * len(preds)]
    out += [f"| {g} | " + " | ".join(str(row[p]) for p in preds) + " |" for g, row in m.items()]
    return out + [""]


def t1_report(r: Mapping[str, Any]) -> str:
    maj = r["baselines"]["majority"]
    p2 = r["baselines"]["p2002_candidates"]
    flags, judg = ("shared", "class-specific", "absent"), ("same", "different", "none")
    L: list[str] = ["# P3-001 — T1 baselines on the validated set\n"]
    L.append(f"Scored on `t1_validated_v1.jsonl`: **{r['n_items']} items** and **{r['n_judgements']} (item, compared "
             f"class) judgements**. Gold flags: {r['gold_flag_counts']}. Gold judgements: {r['gold_judgement_counts']}.\n")
    L.append(f"95% CIs: percentile bootstrap, {r['bootstrap']['resamples']} resamples of **items**, seed "
             f"{r['bootstrap']['seed']}. A judgement resample takes every compared class of each drawn item.\n")
    L.append("## Baselines\n")
    L.append(f"- **Majority class.** Always predicts flag `{maj['rule']['flag']}` and judgement "
             f"`{maj['rule']['judgement']}`: the most frequent labels **of the validated set itself**. That is "
             "in-sample, so the baseline is slightly optimistic by construction.")
    L.append("- **P2-002 candidate labels (\"dense within-family\").** P2-002's bge within-family match status per "
             "compared class. `matched` means a counterpart exists but can't say `same` or `different`; "
             "`below_threshold` reads as `none`. The flag is derived over the item's compared classes, as P2-004 "
             "does: `shared_or_class_specific` if any class matched, else `absent`.\n")
    L.append("### How the P2-002 baseline is scored\n")
    L.append("Its predictions are coarser than the gold labels, so it is scored three ways:")
    L.append("1. **Native (collapsed).** Gold is collapsed to what the baseline can express: flag `absent` vs "
             "`present`, judgement `none` vs `counterpart`. This is the fair comparison. The majority baseline is "
             "scored the same way.")
    fm = p2["fixed_mapping"]["mapping"]
    L.append(f"2. **Fixed mapping, 3 labels.** `shared_or_class_specific` → `{fm['shared_or_class_specific']}` and "
             f"`counterpart` → `{fm['counterpart']}`: the validated set's most frequent non-absent flag and most "
             "frequent counterpart judgement (in-sample, like the majority baseline).")
    L.append("3. **Oracle upper bound, 3 labels.** An undecided prediction counts as correct whenever gold is one of "
             "the labels it covers. It is a ceiling, not a result.\n")

    L.append("## Flag (`differential_flag`)\n")
    L.append("| Baseline / scoring | Macro-F1 | " + " | ".join(f"F1 {x}" for x in flags) + " | Accuracy |")
    L.append("|---|---|" + "---|" * len(flags) + "---|")
    L.append(_row("Majority", maj["three_label"]["flag"], flags))
    L.append(_row("P2-002, fixed mapping", p2["fixed_mapping"]["flag"], flags))
    L.append(_row("P2-002, oracle upper bound", p2["oracle_upper_bound"]["flag"], flags))
    L.append(f"\nn = {r['n_items']} items.\n")
    L.append("Collapsed (absent vs present):\n")
    L.append("| Baseline | Macro-F1 | F1 absent | F1 present | Accuracy |")
    L.append("|---|---|---|---|---|")
    L.append(_row("Majority", maj["native_collapsed"]["flag"], ("absent", "present")))
    L.append(_row("P2-002 (native)", p2["native_collapsed"]["flag"], ("absent", "present")))
    L.append("")
    L.append("## Per-class judgements (`per_class_judgement`)\n")
    L.append("| Baseline / scoring | Macro-F1 | " + " | ".join(f"F1 {x}" for x in judg) + " | Accuracy |")
    L.append("|---|---|" + "---|" * len(judg) + "---|")
    L.append(_row("Majority", maj["three_label"]["judgement"], judg))
    L.append(_row("P2-002, fixed mapping", p2["fixed_mapping"]["judgement"], judg))
    L.append(_row("P2-002, oracle upper bound", p2["oracle_upper_bound"]["judgement"], judg))
    L.append(f"\nn = {r['n_judgements']} judgements from {r['n_items']} items.\n")
    L.append("Collapsed (none vs counterpart):\n")
    L.append("| Baseline | Macro-F1 | F1 none | F1 counterpart | Accuracy |")
    L.append("|---|---|---|---|---|")
    L.append(_row("Majority", maj["native_collapsed"]["judgement"], ("none", "counterpart")))
    L.append(_row("P2-002 (native)", p2["native_collapsed"]["judgement"], ("none", "counterpart")))
    L.append("")
    L.append("## Confusion matrices\n")
    L += _confusion("Majority, flag", maj["three_label"]["flag"]["confusion"])
    L += _confusion("P2-002, flag (raw predictions)", p2["confusion_raw"]["flag"])
    L += _confusion("Majority, judgement", maj["three_label"]["judgement"]["confusion"])
    L += _confusion("P2-002, judgement (raw predictions)", p2["confusion_raw"]["judgement"])
    L.append("## Caveats\n")
    L.append("- The P2-002 candidates are not independent of the gold labels: raters saw the bge top-1/top-2 "
             "candidates while labelling, so agreement with this baseline may be inflated.")
    L.append(f"- n = {r['n_items']} items is small. The per-label F1 CIs for the rarer labels are wide.")
    L.append("- The long-context LLM T1 baseline comes in P4-001. The configured model ids are in "
             "`p3001_retrieval_baselines.md` (Environment).\n")
    L.append(f"Inputs (sha256): {r['inputs']}. Generated {r['scored_utc']} by `scripts/run_p3001.py t1`.")
    return "\n".join(L) + "\n"
