"""reports/p4001_system_and_ablations.md from the metrics JSON (P4-001 Part B)."""

from __future__ import annotations

from typing import Any, Mapping

from src.eval.ci_format import fmt_ci

T1_LABEL = {"majority": "Majority (in-sample)", "p2002_candidates": "P2-002 candidates (dense within-family)",
            "class_blind": "Class-blind LLM", "class_aware": "Class-aware LLM", "final_agentic": "**Final agentic**",
            "ablation_a": "Class-blind + verifier (ablation A)", "long_context": "Long-context LLM"}


def _b(v: Mapping[str, Any] | None, d: int = 3) -> str:
    if not v or v.get("value") is None or v["value"] != v["value"]:
        return "n/a"
    return fmt_ci(v["value"], v["ci"][0], v["ci"][1])


def _p(v: Mapping[str, Any]) -> str:
    """Paired difference with its reading, from the one shared rule (src/eval/ci_format.py)."""
    return fmt_ci(v["diff"], v["ci"][0], v["ci"][1], signed=True, reading=True)


_p4 = _p


def render(m: Mapping[str, Any]) -> str:
    L: list[str] = ["# P4-001 — Class- and date-aware agentic RAG: system runs and ablations A–C\n"]
    env = m["environment"]
    L.append(f"All LLM systems use one model, **`{env['model']}`** (version `{env['model_version']}`), free tier, "
             f"temperature 0, JSON output, thinking `{env['thinking']}`, no provider fallback. Prompts are frozen "
             f"(sha256 in config `p4.prompt_sha256`). The verifier is `{env['nli_model']}` @ `{env['nli_revision'][:12]}…`: "
             "a sentence is supported iff the argmax label (read from `id2label`) is entailment, with the cited paragraph(s) "
             "as premise. Bootstrap: 2,000 seeded resamples; every paired difference uses the same resampled indices.\n")

    if m.get("summary"):
        L.append("## Summary\n")
        for x in m["summary"]:
            L.append(f"- {x}")
        L.append("")
    L.append("## Ablation table\n")
    L.append("| Ablation | Toggle | Measure | ON | OFF | ON − OFF [95% CI] | n |")
    L.append("|---|---|---|---|---|---|---|")
    for row in m["ablation_table"]:
        L.append(f"| {row['ablation']} | {row['toggle']} | {row['measure']} | {row['on']} | {row['off']} | {row['diff']} | {row['n']} |")
    L.append("")

    t1 = m["t1"]
    L.append("## T1 (validated set, 106 items)\n")
    L.append("3-way flag Macro-F1 over gold shared / class-specific / absent (a predicted `ambiguous` is wrong); collapsed = absent vs present; "
             "judgement Macro-F1 over same / different / none (`unsure` is wrong); coverage = share not `ambiguous`. "
             "CIs resample items.\n")
    L.append("| System | n | 3-way flag Macro-F1 | Collapsed Macro-F1 | Judgement Macro-F1 | Judgement F1 same / different / none | Coverage | Predicted flags |")
    L.append("|---|---|---|---|---|---|---|---|")
    for k, v in t1["systems"].items():
        jl = v["judgement_f1_per_label"]
        L.append(f"| {T1_LABEL.get(k, k)} | {v['n_items']} | {_b(v['flag_macro_f1'])} | {_b(v['collapsed_macro_f1'])} | "
                 f"{_b(v['judgement_macro_f1'])} | {jl['same']:.3f} / {jl['different']:.3f} / {jl['none']:.3f} | "
                 f"{_b(v['coverage'])} | {v['pred_flags']} |")
    L.append("")
    L.append("**Paired differences** (same items). The rows against P2-002 candidates: P2-002 cannot express shared vs "
             "class-specific (its flag is only absent or shared-or-class-specific, mapped to shared), so 3-way F1 favours the "
             "LLM systems by design; **collapsed F1 is the fair comparison**.\n")
    L.append("| Comparison | n | Δ 3-way F1 | Δ collapsed F1 | Δ coverage |")
    L.append("|---|---|---|---|---|")
    for k, v in t1["paired"].items():
        L.append(f"| {k} | {v['n_items']} | {_p(v['flag_macro_f1'])} | {_p(v['collapsed_macro_f1'])} | {_p(v['coverage'])} |")
    L.append("")
    if t1.get("long_context_status"):
        L.append(f"**Long-context baseline: {t1['long_context_status']}.** The 150K run is superseded (D10); see the appendix.\n")
    lc = t1.get("long_context_note")
    if lc:
        L.append(f"**Long-context baseline.** {lc}\n")
    lcs = t1.get("long_context_same_items")
    if lcs:
        L.append(f"**Every system on exactly the long-context scored items** (n = {lcs['n']}):\n")
        L.append("| System | 3-way flag Macro-F1 | Collapsed Macro-F1 | Coverage |")
        L.append("|---|---|---|---|")
        for k, v in lcs["systems"].items():
            L.append(f"| {T1_LABEL.get(k, k)} | {_b(v['flag_macro_f1'])} | {_b(v['collapsed_macro_f1'])} | {_b(v['coverage'])} |")
        L.append("")
        td = lcs.get("token_distribution")
        if td:
            L.append("Prompt tokens (estimated as characters / 4, after the cap), scored vs unscored items: "
                     + "; ".join(f"{k}: n={v['n']}, median {v['median']}, min {v['min']}, max {v['max']}" for k, v in td.items() if v) + ".\n")
        if lcs.get("policy"):
            L.append(f"**503 policy (audit note 2).** {lcs['policy']}\n")
        gr = lcs.get("gold_retention")
        if gr and gr.get("items_with_gold_paragraphs"):
            fa = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
            L.append(f"**Did the gold paragraphs survive truncation?** (diagnostic, no LLM calls; cap {gr['cap']:,}) Of "
                     f"{gr['gold_paragraphs']} gold matched paragraphs in {gr['items_with_gold_paragraphs']} scored items, "
                     f"{gr['gold_paragraphs_retained']} were in the prompt "
                     f"({gr['gold_paragraphs_retained'] / gr['gold_paragraphs']:.1%}). Long-context flag accuracy: "
                     f"{fa(gr['flag_accuracy_all_retained'])} on the {gr['items_all_retained']} items with every gold paragraph "
                     f"retained vs {fa(gr['flag_accuracy_some_cut'])} on the {gr['items_some_cut']} with at least one cut.")
            ac = gr.get("accounting")
            if ac:
                L.append(f"Item accounting: {ac['scored']} scored = {ac['all_gold_kept']} (all gold kept) + "
                         f"{ac['at_least_one_cut']} (at least one cut) + {ac['no_gold_matched_paragraph']} with no gold matched "
                         f"paragraph ({'; '.join(f'{v}: {k}' for k, v in ac['no_gold_reason'].items())}). The 'cut' group has "
                         f"n = {ac['at_least_one_cut']}, too small to support a conclusion.")
            L.append("")
        rt = lcs.get("runtime")
        if rt:
            parts = []
            for dname, ps in rt["passes"].items():
                for x in ps:
                    if x.get("active_seconds") is not None:
                        parts.append(f"{dname} (cap {x['cap']:,}): active {x['active_seconds'] / 60:.1f} min, wall {x['seconds'] / 60:.1f} min")
            pm = rt.get("pmset_150k") or {}
            parts += [f"{k}: awake {v['awake_min']} min of {v['wall_min']} wall" for k, v in pm.items() if isinstance(v, dict)]
            if parts:
                L.append("**Real run time** (active time; the Mac's sleep excluded): " + "; ".join(parts) + ".\n")
    L.append(f"**Verifier on T1 (pre-planned ablation C, reported as is).** {t1['verifier_note']}\n")
    dg = t1.get("verifier_diagnostics")
    if dg:
        a, b = dg["a_kept_items"], dg["b_best_sentence"]
        L.append("**Post hoc diagnostics (no LLM calls; diagnostic only, they do not replace the frozen verifier):**\n")
        L.append(f"- (a) On the {a['n_kept_by_final_agentic']} items final agentic did not abstain on: final agentic flag "
                 f"accuracy {a['final_agentic']['accuracy']:.3f}, 3-way F1 {a['final_agentic']['flag_macro_f1']:.3f}; "
                 f"class-aware on the same {a['n_kept_by_final_agentic']} items: accuracy {a['class_aware_same_items']['accuracy']:.3f}, "
                 f"3-way F1 {a['class_aware_same_items']['flag_macro_f1']:.3f}. (Class-aware on its own {a['class_aware_own_non_abstained']['n']} "
                 f"non-abstained items: accuracy {a['class_aware_own_non_abstained']['accuracy']:.3f}.) The verifier does **not** raise "
                 "precision on what it keeps; point estimates only, no CI.")
        L.append(f"- (b) On the {b['n']} stored first-pass same/different rationales: supported {b['supported_whole_paragraph']} "
                 f"({b['rate_whole']:.1%}) with the whole cited paragraph as premise (the frozen rule) vs {b['supported_best_sentence']} "
                 f"({b['rate_best_sentence']:.1%}) with the paragraph's best single sentence (highest entailment probability; "
                 f"sentences split on . ; :). Premises over the NLI model's 512-token limit: {b['premises_over_512_tokens']}. "
                 "So a single-sentence premise would not have raised support: the Part A debug figure (15/27 vs 25/27 with a "
                 "3-sentence window, on 5 rejected items) does not carry over, and the premise rule is not the explanation "
                 "for the abstentions.\n")
    L.append("Per-label flag F1 and confusion matrices are in `p4001_metrics_v1.json` (`t1.systems.<system>`).\n")

    t2 = m["t2"]
    L.append("## T2 (retrieval stage, no LLM)\n")
    L.append("The final pipeline's retrieval stage: hybrid RRF with the class filter (target class + function-heading "
             "Directions of the query's subject family), source excluded; T2 queries carry no as-of date, so the temporal "
             "filter is inactive. Same relevance sets, metrics and bias notes as P3-001; nDCG@10 [95% CI].\n")
    L.append("**Read this first (P3-001 framing).** Relevance was labelled only for the counterpart in the query's "
             "target class, so the task scored here is retrieval of the target-class counterpart, and class-blind "
             "systems are partly disadvantaged by construction: the class filter's gain is partly built in. "
             "`hybrid_minus_source_class` (the class-blind fusion with only the source class removed) is shown next to "
             "the result as the fairer class-blind comparison; the gap from it to the class filter is what knowing the "
             "target class adds for this task. This is not a general class-blind vs class-aware verdict.\n")
    L.append("| Set (bias) | n | Pipeline, class filter ON | OFF (ablation A) | P3-001 class_aware | P3-001 hybrid_minus_source_class | ON − OFF |")
    L.append("|---|---|---|---|---|---|---|")
    for name, v in t2.items():
        L.append(f"| {name} ({v['bias_short']}) | {v['n']} | {_b(v['on'])} | {_b(v['off'])} | {v['p3001_class_aware']} | "
                 f"{v['p3001_minus_source']} | {_p(v['paired'])} |")
    L.append("")

    t3 = m.get("t3")
    L.append("## T3 (temporal: 60 items built, 52 scored after spot-check 2)\n")
    L.append(m["t3_setup"] + "\n")
    tp = m.get("t3_precision")
    if tp:
        for x in tp:
            L.append(f"- {x}")
        L.append("")
    if t3:
        L.append("| Temporal filter | n | Status exact match | Supersession F1 | Before-date EM | After-date EM | Predicted statuses |")
        L.append("|---|---|---|---|---|---|---|")
        for k in ("on", "off"):
            v = t3[k]
            L.append(f"| {k.upper()} | {v['n']} | {_b(v['status_exact_match'])} | {_b(v['supersession_f1'])} | "
                     f"{v['by_side']['before']['status_exact_match']:.3f} (n={v['by_side']['before']['n']}) | "
                     f"{v['by_side']['after']['status_exact_match']:.3f} (n={v['by_side']['after']['n']}) | {v['pred_status']} |")
        L.append(f"\nON − OFF: status exact match {_p(t3['paired']['status_exact_match'])}; supersession F1 "
                 f"{_p(t3['paired']['supersession_f1'])}.\n")
        L.append("The supersession F1 CIs are degenerate ([1, 1] with the filter ON, [0, 0] OFF): on this set the outcomes are "
                 f"deterministic (ON names the governing amendment on every after-date item, {t3['on']['supersession_counts']}; "
                 f"OFF never names one, {t3['off']['supersession_counts']}), so every resample gives the same value.\n")
        sv = t3.get("sensitivity_no_window")
        if sv:
            L.append(f"**Sensitivity: without window-type effective dates** ({sv['excluded']} of {t3['paired']['n']} items "
                     f"excluded: {sv['excluded_bases']}; n = {sv['paired']['n']}): status exact match ON "
                     f"{_b(sv['on']['status_exact_match'])} vs OFF {_b(sv['off']['status_exact_match'])}, ON − OFF "
                     f"{_p(sv['paired']['status_exact_match'])}; supersession F1 ON {_b(sv['on']['supersession_f1'])} vs OFF "
                     f"{_b(sv['off']['supersession_f1'])}, ON − OFF {_p(sv['paired']['supersession_f1'])}.\n")
    L.append("**Circularity.** The T3 gold comes from the same parser that the temporal filter uses, so no rule-only "
             "system is reported as a T3 result (it would be right by construction). T3 measures whether the LLM "
             "pipeline uses the date information it is given.\n")

    t4 = m.get("t4")
    L.append("## T4 ablation C (verifier ON vs OFF, P3-002 questions)\n")
    if t4:
        L.append("Primary n = 28 (T4Q14 and T4Q30, flagged `bad_question` in P3-002, excluded); n = 30 also shown. "
                 "`entity_class` = the question's source class; class filter on; no as-of date.\n")
        L.append("**How abstentions enter.** (a) Unsupported-sentence rate = unsupported delivered sentences / delivered "
                 "sentences, pooled over questions. An abstained answer delivers no sentences, so it adds 0 to both the "
                 "numerator and the denominator: it drops out of the rate, it is not counted as a supported answer. With the "
                 "verifier on, every delivered sentence has passed the same NLI check that defines 'unsupported', so the ON "
                 "rate is 0 by construction. (b) RePASs: an abstained answer is scored as its literal text ('cannot answer "
                 "reliably') against the shown evidence, which RePASs scores low.\n")
        ao = t4["n28"].get("answered_only")
        if ao:
            L.append(f"**Answered-only (lead figure):** on the {ao['n']} questions the verifier ON answered (not abstained, not "
                     f"declined), against the same questions with the verifier OFF: unsupported-sentence rate ON "
                     f"{_b(ao['unsupported_sentence_rate']['on'])} vs OFF {_b(ao['unsupported_sentence_rate']['off'])}, "
                     f"ON − OFF {_p(ao['paired']['unsupported_sentence_rate'])} (ON is 0 by construction); RePASs ON "
                     f"{_b(ao['repass_composite']['on'])} vs OFF {_b(ao['repass_composite']['off'])}, ON − OFF "
                     f"{_p4(ao['paired']['repass_composite'])}. The headline unsupported-rate drop on all 28 questions below is "
                     "mostly abstention plus the by-construction zero, not better answers.\n")
        L.append("| Measure | ON (n=28) | OFF (n=28) | ON − OFF (n=28) | ON − OFF (n=30) |")
        L.append("|---|---|---|---|---|")
        for key, lab in (("unsupported_sentence_rate", "Unsupported-sentence rate (NLI proxy)"),
                         ("abstention_rate", "Abstention rate"), ("repass_composite", "RePASs composite")):
            L.append(f"| {lab} | {_b(t4['n28']['on'].get(key))} | {_b(t4['n28']['off'].get(key))} | "
                     f"{_p(t4['n28']['paired'][key])} | {_p(t4['n30']['paired'][key])} |")
        L.append(f"\nVerifier abstentions: {t4['n28']['on']['abstained_by_verifier']} of 28; model declined to answer: "
                 f"ON {t4['n28']['on']['model_declined']}, OFF {t4['n28']['off']['model_declined']}; retried: {t4['n28']['on']['retried']}.\n")
    L.append("**Say plainly:** the unsupported-sentence rate is an NLI proxy, not human judgement; and the verifier's NLI "
             "model is the same model RePASs uses for entailment and contradiction, so any RePASs gain from the verifier "
             "would partly be the same model agreeing with itself. Here RePASs did not rise: ON − OFF is shown above, "
             "with a CI that includes 0.\n")

    L.append("## Shared prompts (cache)\n")
    L.append("Two pairs reuse the same first prompt through the disk cache, at no extra quota: final agentic sends the "
             "class-aware LLM's first prompt, and ablation A sends the class-blind LLM's. At temperature 0 this is "
             "identical to re-calling and keeps the pairs exactly paired; only verifier retries cost new calls. "
             "Likewise T4 verifier ON sends OFF's first prompt. A retry whose re-retrieved top 5 equals the first "
             "attempt's is an identical prompt, so it returns the same answer from the cache.\n")

    L.append("## CLI demo transcripts\n")
    if not m.get("demo"):
        L.append("Not produced: every demo call has returned HTTP 503 since the outage began, and no cached answers exist for "
                 "the demo queries (none ever succeeded), so no transcript can be recorded from the cache. Planned: an "
                 "entity-class-specific query; a date-specific query; one query with and without the class filter.\n")
    for t in m.get("demo", []):
        L.append(f"### {t['title']}\n\n```\n$ {t['command']}\n{t['output']}\n```\n")
        if t.get("note"):
            L.append(f"**Note.** {t['note']}\n")

    L.append("## Deviations and additions (logged)\n")
    for x in sorted(m.get("deviations", []), key=lambda d: int(d["id"][1:])):
        L.append(f"- **{x['id']} ({x['kind']}).** {x['text']}")
    L.append("")
    ap = t1.get("appendix_150k")
    if ap:
        L.append("## Appendix: long-context at the 150K cap (superseded by the 100K rerun, shown for completeness)\n")
        L.append(f"{ap['note']} n = {ap['n']} scored items. Prompt tokens at the 150K cap: "
                 + "; ".join(f"{k}: n={v['n']}, median {v['median']}, min {v['min']}, max {v['max']}" for k, v in ap["token_distribution"].items() if v) + ".\n")
        L.append("| System (same items) | 3-way flag Macro-F1 | Collapsed Macro-F1 | Coverage |")
        L.append("|---|---|---|---|")
        for k, v in ap["systems"].items():
            L.append(f"| {T1_LABEL.get(k, 'Long-context LLM, 150K cap (superseded)' if k == 'long_context_150k' else k)} | "
                     f"{_b(v['flag_macro_f1'])} | {_b(v['collapsed_macro_f1'])} | {_b(v['coverage'])} |")
        if ap.get("paired_vs_every_system"):
            L.append(f"\nLong-context (150K) minus each system, same {ap['n']} items:\n")
            L.append("| Comparison | Δ 3-way F1 | Δ collapsed F1 | Δ coverage |")
            L.append("|---|---|---|---|")
            for k, pv in ap["paired_vs_every_system"].items():
                L.append(f"| Long-context (150K) − {T1_LABEL.get(k, k)} | {_p(pv['flag_macro_f1'])} | {_p(pv['collapsed_macro_f1'])} | {_p(pv['coverage'])} |")
            L.append("")
    L.append("## Limitations\n")
    for x in m["limitations"]:
        L.append(f"- {x}")
    L.append("")
    L.append("## Environment and quota\n")
    L.append(f"- Calls per quota day (Pacific date; resets 12:30 IST): {env['ledger']}.")
    L.append(f"- Machine: {env.get('machine')}; Python {env.get('python')}; packages {env.get('packages')}.")
    L.append(f"\nGenerated {m['generated_utc']} by `scripts/run_p4.py report`.")
    return "\n".join(L) + "\n"
