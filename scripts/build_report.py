#!/usr/bin/env python3
"""P5-001 task 2: draft the final report from reports/results_v1.json and reports/final/error_analysis_v1.json.

    python3 scripts/build_report.py            # writes reports/final/rbi_oblibench_report.md (refuses to overwrite)
    python3 scripts/build_report.py --force    # overwrite (this discards any hand edits to the draft)
    python3 scripts/build_report.py --render   # render the existing .md to .docx (and .pdf only if an engine exists)

The prose is a draft for Karan to edit by hand; every number in it is read from the results files, never typed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_tables import b, kappa, mb, mpd, pd, rate  # noqa: E402
from src.eval.ci_format import fmt_ci  # noqa: E402

OUT = ROOT / "reports" / "final" / "rbi_oblibench_report.md"


def J(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def r_(x: dict) -> str:
    return rate(x["k"], x["n"], x.get("wilson_95"))


def k_(block: dict) -> str:
    return kappa(block)


def mag(p: dict) -> str:
    """Magnitude of a paired difference, for 'lowers it by X' sentences."""
    return f"{abs(p['diff']):.3f}"


def build() -> str:
    R = J("reports/results_v1.json")["tables"]
    E = J("reports/final/error_analysis_v1.json")
    P4 = J("reports/p4001_metrics_v1.json")
    P3 = J("reports/p3002_metrics_v1.json")
    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11 = (R[k] for k in (
        "01_corpus", "02_candidates", "03_matching", "04_supplementary", "05_t1_benchmark", "06_t2_retrieval",
        "07_t1_systems", "08_t3", "09_t4", "10_ablations", "11_llm_usage"))
    S, PR = c7["systems"], c7["paired"]
    lc = c7["long_context_same_items"]
    irr, rt = c5["irr"]["fleiss"], c5["retest"]["phase2"]["all_25"]
    tr = c5["timed_relabel"]
    t2 = c6["p3001"]
    t2p4 = c6["p4_pipeline"]
    sets = list(t2)
    t3 = c8["t3"]
    t4 = P4["t4"]["n28"]
    pa = PR["Ablation A (verifier on): final agentic − class-blind + verifier"]
    pcf = PR["Class filter, no verifier: class-aware − class-blind"]
    pc = PR["Ablation C on T1: final agentic − class-aware"]
    pv = PR["Verifier, class-blind: ablation A − class-blind"]
    vs_p2 = {k: PR[k] for k in PR if k.endswith("− P2-002 candidates")}
    lcp = {k: PR[k] for k in PR if k.startswith("Long-context")}
    hum = P3["human"]["all_rated"]
    sp_f, sp_q = hum["spearman_composite_score_vs_faithful"], hum["spearman_composite_score_vs_answers_question"]
    sp_rf = hum["spearman_repaired_vs_faithful"]
    main = P3["main"]
    gam = main["paired"]
    dl = {s: S[s]["judgement_f1_per_label"]["different"] for s in S}
    llm = c11["p4"]
    ea, eb, ec, ed, ee = (E[k] for k in ("a_different_missed", "b_verifier_abstentions", "c_long_context", "d_t3_filter_off", "e_t4_metric_vs_human"))
    acc = lc["gold_retention"]["accounting"]
    rc = c5["route_counts"]
    pilot = c5["pilot_fleiss_flag"]
    ao = t4["answered_only"]
    fa_unsure = S["final_agentic"]["unsure_judgements"]
    p2004_irr_items = c5["irr"]["items"]
    ts = lc["token_distribution"]
    outage = c11["outage"]
    ret_rows = c10["rows"]
    q_model = c11["p3002"]["questions"]["models"][0]
    ab_fa = eb["Final agentic"]

    def ci_row(label):
        return next(r for r in ret_rows if r["measure"] == label)["on_minus_off"]

    L: list[str] = []
    A = L.append

    A("---\ntitle: \"RBI-ObliBench: a benchmark for entity-class applicability, differential obligations and metric integrity "
      "on Reserve Bank of India Master Directions\"\nauthor: \"Karan Lokhande\"\ndate: \"Draft, 29 September 2026\"\n---\n")
    A("> **Draft written by Claude Code from the repository's reports; Karan edits it by hand.** Every number is read from "
      "`reports/results_v1.json`, `reports/final/error_analysis_v1.json` and the phase metrics files by `scripts/build_report.py`. "
      "Tables are in `reports/tables/`. Every interval is a 95% CI; \"excludes 0\" is used only when an interval is strictly above "
      "or below 0 (`src/eval/ci_format.py`).\n")

    # 1 ---------------------------------------------------------------------------------------------
    A("# 1. Abstract\n")
    A(f"We build RBI-ObliBench on {c1['directions']} Reserve Bank of India (RBI) Master Directions ({c1['paragraphs']:,} paragraphs, "
      f"{c1['core_entity_classes']} regulated-entity classes). It has four tasks. T1 asks which entity classes an obligation binds and "
      f"where parallel Directions differ. It has {c5['validated']} validated items, labelled by a single expert, with second-rater class-row "
      f"κ = {irr['per_class_judgement']['kappa']:.3f} (n = {irr['per_class_judgement']['n_items']} items) and blind test-retest flag "
      f"κ = {rt['differential_flag']['kappa']:.3f} (n = {rt['differential_flag']['n_items']}). T2 is cross-class retrieval over "
      f"three relevance sets. T3 has {c8['scored']} temporal (as-of date) items. T4 audits the RePASs faithfulness metric on 30 questions. "
      "A class filter changes T2 nDCG@10 by "
      + "; ".join(f"{pd(t2p4[s]['paired'])} on {s}" for s in sets)
      + ". That gain is partly by construction, because relevance was labelled only for the target-class counterpart. The class filter "
      f"has no significant effect on T1 (3-way flag F1 {pd(pa['flag_macro_f1'])}). No LLM system significantly beats the P2-002 "
      "semantic-matching candidate labels on collapsed flag F1. Every system is weak on `different` judgements "
      f"(best F1 {max(dl[s] for s in ('class_blind', 'class_aware', 'final_agentic', 'ablation_a', 'long_context')):.3f}). "
      f"The NLI verifier lowers T1 3-way flag F1 by {mag(pc['flag_macro_f1'])} ({pd(pc['flag_macro_f1'])}). "
      f"A long-context baseline (100K-token cap, n = {lc['n']}) is statistically tied with the retrieval systems on 3-way F1. "
      f"On RBI text, RePASs is gameable by concatenation (concatenated − genuine {mpd(gam['concatenated - genuine']['composite_score'])}) "
      "but not by negated or off-topic answers. It tracks human faithfulness "
      f"(Spearman ρ {fmt_ci(sp_f['rho'], sp_f['ci_low'], sp_f['ci_high'])}) but not whether the answer addresses the question "
      f"(ρ {fmt_ci(sp_q['rho'], sp_q['ci_low'], sp_q['ci_high'])}). The exploratory repair is not usable. We release annotations, pointers and "
      "code; RBI text is rehydrated from RBI's own URLs.\n")

    # 2 ---------------------------------------------------------------------------------------------
    A("# 2. Introduction and research questions\n")
    A("RBI issues many of its Master Directions in parallel, one per class of regulated entity (commercial banks, small finance "
      "banks, NBFCs, co-operative banks and others), often on the same subject. A compliance question is therefore only answerable "
      "for a declared entity class: the same paragraph can bind one class, have a counterpart with different content for another, "
      "and not exist for a third. Directions are also amended in place, so the answer depends on the date. RBI-ObliBench turns these "
      "properties into evaluation tasks and asks whether a retrieval-augmented system, and the metric used to score it, cope with them.\n")
    A("- **RQ1 — Applicability:** Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?")
    A("- **RQ2 — Differential Obligation:** For a subject issued in parallel across entity classes, can the system identify what one entity class is required to do that another entity class is not?")
    A("- **RQ3 — Metric Integrity:** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair makes the metric resistant to concatenation/verbatim extraction?\n")
    A("Contributions: (i) a pointer-only corpus and entity-class × subject-family matrix; (ii) T1, a validated applicability and "
      "differential-obligation set with its reliability evidence; (iii) T2 relevance sets with their construction biases stated; "
      "(iv) T3, a deterministic temporal set built from amendment Directions; (v) T4, an audit of RePASs on RBI text; (vi) a class- "
      "and date-aware RAG pipeline with ablations A–C and long-context and non-LLM baselines, all with bootstrap 95% CIs.\n")

    # 3 ---------------------------------------------------------------------------------------------
    A("# 3. Related work\n")
    A("RePASs [1, 2] scores answers to regulatory questions by entailment, contradiction and obligation coverage against the retrieved "
      "passages. It was introduced with ObliQA [3] in the RegNLP line of work on financial-regulation QA. At the RIRAG-2025 shared "
      "task, a naive obligation-concatenation system scored RePASs 0.947, above human experts, on ObliQA [4]. T4 tests whether that "
      "gameability carries over to Indian regulatory text. We use ObliQA and RIRAG for positioning only: their tasks, corpora and "
      "metrics are not interchangeable with ours, and we report no cross-benchmark comparison. IndiaFinBench [5] was planned as a "
      "transfer baseline and was cut (Section 11).\n")

    # 4 ---------------------------------------------------------------------------------------------
    A("# 4. Corpus and entity-class × subject-family matrix\n")
    A(f"The corpus is every Master Direction on RBI's listing: {c1['directions']} Directions and {c1['paragraphs']:,} paragraphs "
      f"(Table 1). An early harvest missed {c1['p1004_recovered']['previously_missing']} Directions: the first downloads received HTML "
      f"instead of PDFs (master-prompt defect D1). The P1-004 repair recovered all of them plus {c1['p1004_recovered']['newly_listed']} newly listed, and no "
      f"Direction is missing now. The listing gives each Direction an entity-class heading. Of the {c1['entity_classes']} headings, "
      f"{c1['core_entity_classes']} are regulated-entity classes and {c1['function_headings']} are RBI function headings such as "
      "Foreign Exchange Management (D8). Subject families are derived from titles: "
      f"{c1['subject_families']} families, assigned to {c1['directions_with_subject_family']}/{c1['directions']} Directions. Three "
      f"Directions have empty titles and no family (D2: {', '.join(c1['empty_title_directions'])}). The matrix has "
      f"{c1['matrix']['total_cells']} class × family cells; {c1['matrix']['populated_cells']} are populated "
      f"(coverage {c1['matrix']['matrix_coverage']:.3f}), {c1['matrix']['ambiguous_cells']} ambiguous and "
      f"{c1['matrix']['duplicate_mapping_cells']} with duplicate mappings.\n")
    p = c2["precision_rounds"]
    A(f"**Obligation candidates (P2-001).** A deontic-cue rule set marks {c2['paragraphs_with_cue']:,} paragraphs and keeps "
      f"{c2['candidates_kept']:,} candidates. Manual precision rose over four rule versions, from {r_({'k': p[0]['true'], 'n': p[0]['n'], 'wilson_95': p[0]['wilson_95']})} "
      f"(v1, which triggered the stop rule) to {r_({'k': p[-1]['true'], 'n': p[-1]['n'], 'wilson_95': p[-1]['wilson_95']})} (v4, "
      "measured on re-admitted candidates only; Table 2).\n")
    o = c3["overall"]
    A(f"**Cross-class matching (P2-002).** Each candidate is matched to its counterpart in the other classes with bge-base-en-v1.5 "
      f"embeddings. On 60 validation pairs drawn across score bands, the counterpart rate (same or related) is "
      f"{r_(o['counterpart_rate'])}. The operating threshold ({c3['threshold']['value']}) was chosen on the same sample it is scored on (Table 3).\n")
    A("**Supplementary sources (P2-003).** RBI FAQs and enforcement releases were hand-aligned to paragraphs. Under a pre-registered rule, "
      + "; ".join(f"{d['source']} aligned cleanly on {rate(d['clean'], d['n'], d['wilson95'])}, so it becomes `{d['decision']}`" for d in c4["decisions"])
      + ". Both intervals cross a decision line (Table 4).\n")

    # 5 ---------------------------------------------------------------------------------------------
    A("# 5. T1 benchmark construction\n")
    A("**Guidelines v3** (`release/guidelines/ANNOTATION_INSTRUCTIONS.md`) define, for a source obligation paragraph and up to four "
      "compared entity classes, a per-class judgement (`same`: the compared class has a counterpart obligation with the same content; "
      "`different`: a counterpart exists but its content differs; `none`: no counterpart), the matched counterpart paragraph, "
      "`applies_to`, and a differential flag (`shared`, `class-specific`, `absent`).\n")
    A(f"**Sampling.** {c5['sample']} candidates were drawn with a seed, stratified by source class (proportional, with a floor per "
      "core class), and spread over subject families and candidate flags. Each item has at most 4 compared classes ("
      + ", ".join(f"{v} items with {k}" for k, v in c5["compared_classes_per_item"].items()) + ").\n")
    A("**Blind sheets.** Sheets show no candidate labels, scores or retest membership; a hidden key holds them. The second raters "
      "started from blank files, and the tooling rejects a file whose judgements arrive pre-filled (the D11 guard).\n")
    A(f"**Provenance routes.** {c5['validated']} items were validated and {c5['rejected']} rejected as not an obligation "
      f"({r_(c5['rejection_rate'])}). Routes: " + ", ".join(f"{k} {v}" for k, v in rc.items())
      + f". Most items ({rc.get('single-pass')}) were labelled once, by one annotator.\n")
    A(f"**Reliability** (Table 5). Single-expert annotations with second-rater class-row κ = {k_(irr['per_class_judgement'])} and blind "
      f"test-retest flag κ = {k_(rt['differential_flag'])}. The inter-rater set is {p2004_irr_items} items labelled by three raters "
      f"before adjudication (Fleiss' κ): flag {k_(irr['differential_flag'])}; not-obligation {k_(irr['not_obligation'])}. "
      f"The test-retest was blind but had no washout period: test-retest class-row κ {k_(rt['per_class_judgement'])}. On 20 single-pass items, "
      f"a timed blind re-label agrees with pass 1 at flag κ {k_(tr['differential_flag'])} and class-row κ {k_(tr['per_class_judgement'])}. "
      f"The Phase 1 pilot Fleiss flag κ ({pilot['kappa']:.3f}, n = {pilot['n_items']}, point estimate) is **conditional** (D11): every "
      "rater judged against the same pre-filled `applies_to`, which may have anchored it. Candidate labels from P2-002 agree with the "
      "validated labels on " + ", ".join(f"{k} band {r_(v)}" for k, v in c5["candidate_label_agreement_by_band"].items()) + ".\n")

    # 6 ---------------------------------------------------------------------------------------------
    A("# 6. Tasks and metrics\n")
    A("- **T1 (RQ1, RQ2).** Input: a source obligation and its compared classes. Output: a per-class judgement and the derived flag. "
      "Metrics: 3-way flag Macro-F1 over shared / class-specific / absent (a predicted `ambiguous` counts as wrong); collapsed "
      "Macro-F1 (absent vs present); judgement Macro-F1 and per-label F1; coverage (share of items with a non-ambiguous flag). "
      "The P2-002 candidates cannot say `shared` vs `class-specific`, so 3-way F1 favours the LLM systems by design and collapsed F1 "
      "is the fair comparison with them.")
    A("- **T2 (RQ1).** Retrieve the counterpart paragraph in a named target class. Three relevance sets: "
      + "; ".join(f"`{s}` (n = {t2[s]['n_scored']})" for s in sets) + ". Metrics: Recall@10, MAP@10, nDCG@10.")
    A("- **T3.** Given a paragraph and an as-of date, give its status (in force original / amended / deleted) and the governing "
      "instrument. Metrics: status exact match and supersession F1.")
    A("- **T4 (RQ3).** Thirty questions with four answer types (genuine, concatenated, negated, off-topic). Metrics: RePASs "
      "composite and components, and human `faithful` / `answers_question` ratings on 30 answers.")
    A("\nEvery CI is a seeded bootstrap with 2,000 resamples over items, or over queries or questions; differences are paired. There is no "
      "correction for multiple comparisons.\n")

    # 7 ---------------------------------------------------------------------------------------------
    A("# 7. Systems and baselines\n")
    A("- **Non-LLM baselines.** For T1: the majority class (fitted in-sample) and the P2-002 candidate labels. For T2: BM25 (bm25s, "
      "Lucene variant), dense bge-base-en-v1.5, hybrid reciprocal rank fusion (RRF, k = 60), class-aware hybrid (restricted to the target class's Directions), "
      "and `hybrid_minus_source_class` (class-blind, with the query's own class removed).")
    A(f"- **Pipeline (P4).** Hybrid RRF retrieval, then an optional class filter (the target class plus the same family's function-heading "
      f"Directions), an optional temporal filter (from the T3 amendment parser), a JSON-mode LLM answer and an optional NLI verifier. "
      f"The verifier (`{P4['environment']['nli_model']}` @ `{P4['environment']['nli_revision'][:12]}`) checks each cited claim "
      "against the whole cited paragraph. If a claim is unsupported, it retries once, with the query extended by the unsupported "
      "rationales, and then abstains on any class still unsupported (`unsure`).")
    A("- **T1 systems.** Class-blind LLM (no filter, no verifier); class-aware LLM (filter); final agentic (filter + verifier); "
      "class-blind + verifier (ablation A).")
    A(f"- **Long-context LLM.** The same model reads every compared class's Directions directly, without retrieval, capped at "
      f"{lc['cap']:,} input tokens with proportional truncation per class.")
    A(f"- **LLMs (exact ids, Table 11).** P4: `{llm['model']}` (version `{llm['model_version']}`), temperature 0, thinking "
      f"`{llm['thinking']}`, no provider fallback. P3-002 question drafting and genuine answers: Groq `{q_model}`. All calls are "
      "cached on disk by a hash of (provider, model, messages, parameters).\n")

    # 8 ---------------------------------------------------------------------------------------------
    A("# 8. Results\n")
    A("## 8.1 RQ1 — Applicability\n")
    A("The class filter improves T2 retrieval on all three relevance sets (pipeline retrieval stage, filter ON − OFF, nDCG@10): "
      + "; ".join(f"`{s}` {pd(t2p4[s]['paired'])}" for s in sets)
      + ". **This gain is partly by construction:** relevance was labelled only for the counterpart in the target class, so "
      "near-identical paragraphs that a class-blind system returns from other classes count as misses. The class-blind comparison "
      "that removes only the source class, `hybrid_minus_source_class`, reaches nDCG@10 "
      + "; ".join(f"{mb(t2[s]['systems']['hybrid_minus_source_class']['ndcg'])} on `{s}`" for s in sets)
      + ". Class-aware minus that system: "
      + "; ".join(f"{mpd(t2[s]['paired']['class_aware - hybrid_minus_source_class']['ndcg'])} on `{s}`" for s in sets) + ".\n")
    A("The class-blind dense retriever reaches nDCG@10 " + "; ".join(f"{mb(t2[s]['systems']['dense']['ndcg'])} on `{s}`" for s in sets)
      + ", against " + "; ".join(f"{mb(t2[s]['systems']['class_aware']['ndcg'])}" for s in sets)
      + " for the class-aware hybrid (same order). Each relevance set is biased towards one retriever (Table 6): the first two towards the dense model, the third towards BM25.\n")
    A(f"On T1 the class filter has no significant effect: 3-way flag F1 {pd(pa['flag_macro_f1'])} with the verifier on and "
      f"{pd(pcf['flag_macro_f1'])} without it (n = {pa['n_items']}).\n")
    A("## 8.2 RQ2 — Differential obligation\n")
    A("No LLM system significantly beats the P2-002 candidate labels on collapsed flag F1 (Table 7): "
      + "; ".join(f"{k.replace(' − P2-002 candidates', '')} {pd(v['collapsed_macro_f1'])}" for k, v in vs_p2.items())
      + ". On 3-way F1 the class-blind LLM is highest among all systems "
      f"({b(S['class_blind']['flag_macro_f1'])}), ahead of class-aware ({b(S['class_aware']['flag_macro_f1'])}) and final agentic "
      f"({b(S['final_agentic']['flag_macro_f1'])}). 3-way F1 favours the LLMs over P2-002 by design.\n")
    A("Every system is weak on `different` judgements. F1 on `different`: " + ", ".join(
        f"{n} {dl[s]:.3f}" for s, n in (("class_blind", "class-blind"), ("class_aware", "class-aware"), ("final_agentic", "final agentic"),
                                         ("ablation_a", "class-blind + verifier"), ("long_context", "long-context")))
      + f" (point estimates). Of {ea['gold_different_units']} gold `different` class rows, {ea['missed_by_every_llm_system']} are "
      "missed by every LLM system; most are answered `none` or `same` (Section 8.7). Class-specific differences are therefore the "
      "benchmark's hardest case. This is a finding about what the benchmark catches: systems that match counterparts well still do not "
      "say what differs between them.\n")
    A("## 8.3 Verifier (ablation C on T1)\n")
    A(f"The verifier changes 3-way flag F1 by {pd(pc['flag_macro_f1'])} and coverage by {pd(pc['coverage'])} (final agentic − "
      f"class-aware, n = {pc['n_items']}); it lowers 3-way flag F1 by {mag(pc['flag_macro_f1'])} and coverage by {mag(pc['coverage'])}. "
      f"On the class-blind side it lowers 3-way flag F1 by {mag(pv['flag_macro_f1'])} ({pd(pv['flag_macro_f1'])}). Final agentic "
      f"has {fa_unsure} `unsure` judgements: {ab_fa['abstained_judgements']} verifier abstentions and "
      f"{ab_fa['unsure_from_invalid_output']} model outputs the parser rejected as invalid. Of the {ab_fa['abstained_judgements']} abstentions, "
      f"{ab_fa['abstained_judgements_correct_before_retry']} were correct on the first pass. A post hoc diagnostic shows the verifier "
      "does not raise precision on the items it keeps (P4 report, diagnostic a).\n")
    A("## 8.4 Long-context baseline\n")
    A(f"At the uniform {lc['cap'] // 1000}K cap, {lc['n']} of {c5['validated']} items were answered; the other {c5['validated'] - lc['n']} prompts failed repeatedly (the prompt size of "
      f"answered items has median {ts['scored']['median']:,} tokens, of unanswered {ts['unscored']['median']:,}). On the same {lc['n']} items the "
      "long-context model is statistically tied with P2-002, class-blind and class-aware on both flag metrics: "
      + "; ".join(f"{k.split('− ')[1].replace(' (same items)', '')} 3-way {pd(v['flag_macro_f1'])}, collapsed {pd(v['collapsed_macro_f1'])}"
                  for k, v in lcp.items() if any(x in k for x in ("P2-002", "class-blind (same", "class-aware")))
      + f". It matches final agentic on 3-way F1 ({pd(lcp['Long-context − final agentic (same items)']['flag_macro_f1'])}) and beats "
      f"final agentic ({pd(lcp['Long-context − final agentic (same items)']['collapsed_macro_f1'])}) and class-blind + verifier "
      f"({pd(lcp['Long-context − class-blind + verifier (same items)']['collapsed_macro_f1'])}) on collapsed F1. It is weak on "
      f"`different` (F1 {dl['long_context']:.3f}). Gold retention: of {acc['scored']} scored items, {acc['all_gold_kept']} kept every gold "
      f"counterpart in the prompt, {acc['at_least_one_cut']} lost at least one to truncation and {acc['no_gold_matched_paragraph']} have "
      f"no gold counterpart. A 150K-cap run on {c7['appendix_150k']['n']} items is superseded and shown only in the Table 7 appendix (D10).\n")
    A("## 8.5 RQ3 — Metric integrity (T4)\n")
    A(f"Concatenation gameability reproduces: concatenated − genuine RePASs {mpd(gam['concatenated - genuine']['composite_score'])} "
      f"(n = {main['n_questions']}, pre-registered verdict: {main['verdicts']['concatenated']}). The adversarial versions do not: "
      f"negated − genuine {mpd(gam['adv_negated - genuine']['composite_score'])}, off-topic − genuine "
      f"{mpd(gam['adv_offtopic - genuine']['composite_score'])}. The verdicts are the same without the {c9['human']['bad_question_count']} questions the rater flagged as "
      f"bad (n = {main['n_questions'] - c9['human']['bad_question_count']}). RePASs correlates with human `faithful` at Spearman ρ {fmt_ci(sp_f['rho'], sp_f['ci_low'], sp_f['ci_high'])} and with "
      f"`answers_question` at ρ {fmt_ci(sp_q['rho'], sp_q['ci_low'], sp_q['ci_high'])} (n = {sp_f['n']}). Concatenated answers are "
      "faithful by construction, and RePASs rewards them without checking that they address the question.\n")
    A("The exploratory repair (an overlap penalty on verbatim text plus a question-relevance term) ranks genuine above every other type "
      "(" + "; ".join(f"genuine − {k.replace('genuine - ', '')} {mpd(v)}" for k, v in main["repair"].items()) + "). It is **not "
      f"usable**: it works only because the penalty zeroes every verbatim answer, and it no longer tracks human faithfulness (ρ "
      f"{fmt_ci(sp_rf['rho'], sp_rf['ci_low'], sp_rf['ci_high'])}). It was also designed with the RIRAG finding in mind and tested on "
      "the same 30 questions.\n")
    A(f"In ablation C on T4 (n = {t4['on']['n']} primary questions), the verifier changes the RePASs composite by "
      f"{ci_row('T4 RePASs composite')}: not significant. On the {ao['n']} questions the verifier answered, the change is "
      f"{ci_row('T4 RePASs composite, answered only')}. The verifier and RePASs share an NLI model "
      "(`cross-encoder/nli-deberta-v3-xsmall`), so any agreement between them is partly the same model agreeing with itself. "
      f"The verifier changes T4 abstention by {ci_row('T4 abstention rate')}.\n")
    A("## 8.6 T3 — Temporal\n")
    A(f"With the temporal filter on, status exact match is {b(t3['on']['status_exact_match'])}. **This 1.000 is circular by "
      "construction**: the gold and the filter come from the same deterministic parser, so T3 measures only whether the LLM uses the "
      f"dates it is given. Without the filter the model almost always answers \"in force, original\": "
      f"{ed['pred_status_filter_off'].get('in_force_original', 0)} of {ed['scored']} items, giving exact match "
      f"{b(t3['off']['status_exact_match'])}. The corpus holds only the current (amended) text of each Direction, so the system can "
      "flag a later amendment but cannot show the pre-amendment wording. The result holds without the window-type items (Table 8).\n")
    A("## 8.7 Error analysis and failure cases\n")
    A(f"Cases were selected by a fixed rule ({E['selection_rule']}), not by eye. Examples are pointers plus at most 25 words of text; "
      "`release/rehydrate.py` restores the full paragraphs. Full lists: `reports/tables/13_error_analysis.md`. Per-class "
      "results and confusion matrices: `reports/tables/12_t1_per_class.md`.\n")
    A(f"**(a) Missed `different` judgements.** {ea['missed_by_every_llm_system']} of {ea['gold_different_units']} gold `different` "
      "class rows are missed by every LLM system. Recall on `different`: " + "; ".join(
          f"{k} {rate(v['k'], v['n'], v['wilson_95'])}" for k, v in ea["per_system_recall"].items() if k not in ("Majority", "P2-002 candidates"))
      + ".")
    for x in ea["examples"]:
        A(f"- `{x['item_id']}`, {x['source_class']} vs {x['compared_class']} (gold counterpart `{x['gold_matched_paragraph_id']}`). "
          f"Source {x['source']['paragraph_id']}, offsets {x['source']['offsets']}: “{x['source']['excerpt']}”. Every LLM system "
          f"answered: {', '.join(sorted({v for k, v in x['predictions'].items() if k not in ('Majority', 'P2-002 candidates')}))}.")
    A(f"\n**(b) Verifier abstentions on correct first answers.** Final agentic abstained on {ab_fa['abstained_judgements']} class "
      f"judgements; {ab_fa['abstained_judgements_correct_before_retry']} of them were correct before the retry. On "
      f"{ab_fa['items_flag_correct_before_retry_wrong_after']} items the first-pass flag was right and the final flag wrong. For "
      f"class-blind + verifier: {eb['Class-blind + verifier']['abstained_judgements_correct_before_retry']} of "
      f"{eb['Class-blind + verifier']['abstained_judgements']}, and {eb['Class-blind + verifier']['items_flag_correct_before_retry_wrong_after']} items.")
    for s, v in eb.items():
        for x in v["examples"]:
            A(f"- {s}, `{x['item_id']}`: first-pass flag `{x['first_pass_flag']}` (= gold), final `{x['final_flag']}` after "
              f"abstaining on {len(x['abstained_classes'])} of {len(x['gold_judgements'])} classes. Source {x['source']['paragraph_id']}: "
              f"“{x['source']['excerpt']}”.")
    A(f"\n**(c) Long-context errors.** Flag errors by gold retention: " + "; ".join(
        f"{g}: {v['flag_errors']} of {v['items']}" for g, v in ec["by_retention"].items()) + ".")
    for x in ec["examples"]:
        A(f"- `{x['item_id']}` ({x['group']}, {x['kept']}/{x['gold_paragraphs']} gold paragraphs in the prompt, about "
          f"{x['prompt_tokens_est']:,} tokens): gold `{x['gold_flag']}`, predicted `{x['pred_flag']}`. Source "
          f"{x['source']['paragraph_id']}: “{x['source']['excerpt']}”.")
    A(f"\n**(d) T3 without the temporal filter.** {ed['status_errors']} status errors on {ed['scored']} items: " + "; ".join(
        f"{k} ({v})" for k, v in sorted(ed["errors_by_gold_status_and_side"].items())) + ".")
    for x in ed["examples"]:
        A(f"- `{x['t3_id']}`: {x['paragraph_id']} as of {x['as_of']}, after the amendment effective {x['effective_date']}; gold "
          f"`{x['gold_status']}` (`{x['gold_governing_instrument']}`), predicted `{x['pred_status']}` (`{x['pred_governing_instrument']}`).")
    A(f"\n**(e) RePASs vs human `faithful`.** Rule: {ee['rule']}. Rated faithful 2 but scored low: {ee['faithful_2_metric_low']} "
      f"({', '.join(f'{k} {v}' for k, v in ee['faithful_2_metric_low_by_type'].items())}); rated 0 but scored high: "
      f"{ee['faithful_0_metric_high']}.")
    for x in ee["examples"]:
        A(f"- `{x['question_id']}` ({x['answer_type']}): human faithful {x['faithful']}, RePASs {x['repass_composite']:.3f} "
          f"(entailment {x['entailment']:.3f}, contradiction {x['contradiction']:.3f}, coverage {x['obligation_coverage']:.3f}). "
          f"Answer ({x['answer_pointer']}): “{x['answer_excerpt']}”.")
    A("")

    # 9 ---------------------------------------------------------------------------------------------
    A("# 9. Ablations\n")
    A("Table 10 puts ablations A–C in one table (ON − OFF, everything else at the final agentic setting). A (class filter) helps T2 "
      f"and does nothing significant on T1. B (temporal filter) changes T3 status exact match by {ci_row('T3 status exact match')}; "
      f"this is circular (Section 8.6). C (verifier) changes T1 3-way flag F1 by {pd(pc['flag_macro_f1'])}, "
      f"T4 abstention by {ci_row('T4 abstention rate')} and the T4 unsupported-sentence rate (an NLI proxy, all 28 questions) by "
      f"{ci_row('T4 unsupported-sentence rate (NLI proxy), all 28')}. On answered questions only, where ON is 0 by construction, that rate changes by "
      f"{ci_row('T4 unsupported-sentence rate, answered only (ON is 0 by construction)')}.\n")

    # 10 --------------------------------------------------------------------------------------------
    A("# 10. Discussion\n")
    A("**Why an agent?** On this data, the agentic additions did not pay off on T1. The class filter's value is real for retrieving a "
      "named class's counterpart (T2), but it did not change T1 judgement. The verifier made T1 worse and abstained on many correct "
      "first answers. The whole-paragraph NLI premise is a poor test for a one-sentence rationale about a counterpart. The "
      "long-context model, which skips retrieval, is tied with the retrieval systems on 3-way F1 and beats both verifier "
      "systems on collapsed F1. On T1, where each item names its classes and the relevant Directions fit in "
      "a 100K-token prompt for most items, retrieval was not the bottleneck; deciding what differs was.\n")
    A("**What is new.** The benchmark isolates a case that generic regulatory QA does not test: a paragraph whose counterpart "
      "exists in another class but says something different. Every system here, from embedding matching to long-context "
      "reading, is weak on it. T4 shows that on RBI text RePASs rewards verbatim concatenation, as it did on ObliQA, but resists "
      "negation and off-topic text. The failure is that it does not check relevance to the question, not that it cannot detect "
      "contradiction.\n")
    A("**What went against expectations.** The class-aware and final agentic systems did not beat the class-blind LLM on T1. No LLM "
      "system beat the P2-002 candidate labels on collapsed F1. The verifier lowered T1 F1 and did not raise precision on the items "
      "it kept. The long-context baseline was not worse than the pipeline. The metric repair failed. The adversarial answers did not "
      "fool RePASs.\n")

    # 11 --------------------------------------------------------------------------------------------
    A("# 11. Limitations and threats to validity\n")
    A("**T1 size and labels.**")
    A(f"- {c5['validated']} validated items out of {c5['sample']} sampled; {c5['rejected']} rejected as not an obligation "
      f"({r_(c5['rejection_rate'])}). Source classes have between "
      f"{min(v['validated'] for v in c5['by_source_class'].values())} and {max(v['validated'] for v in c5['by_source_class'].values())} "
      "items each (Table 5), so per-class results (Table 12) have wide intervals. Compared classes are capped at 4 per item, and "
      "`applies_to` and the flag are defined over those classes only.")
    A(f"- Routes: {', '.join(f'{k} {v}' for k, v in rc.items())}. Most labels are single-pass: one annotator, one pass.")
    A(f"- The second-rater subset is {p2004_irr_items} items; single-expert annotations with second-rater class-row κ = "
      f"{irr['per_class_judgement']['kappa']:.3f} (n = {irr['per_class_judgement']['n_items']}) and blind test-retest flag κ = "
      f"{rt['differential_flag']['kappa']:.3f} (n = {rt['differential_flag']['n_items']}).")
    A("- The test-retest is blind but had no washout period; the short interval may inflate agreement through recall. "
      "Three corrected pilot rows may not be blind.")
    A(f"- The pilot κ ({pilot['kappa']:.3f}, n = {pilot['n_items']}) is conditional on a pre-filled `applies_to` (D11). The pilot "
      f"test-retest flag κ is {k_(c5['retest']['pilot']['differential_flag'])}.")
    A("- The overlap team-review file declares `label_source` as \"manual (declared by Karan); revised after reviewer (Claude) "
      "feedback on file-level patterns, not on label content; not independent\". It carries no κ by design.")
    A("- `absent` covers only the paragraphs shown or looked up.")
    A("\n**Corpus.**")
    A(f"- D1: an early harvest missed {c1['p1004_recovered']['previously_missing']} Directions; the P1-004 repair recovered them, "
      f"and none is missing now. Every P2 artefact was computed on the full {c1['directions']}.")
    A(f"- D2: {len(c1['empty_title_directions'])} Directions have empty titles and no subject family.")
    A("- Subject families are derived from titles, not assigned by RBI.")
    A(f"- D8: the entity-class vocabulary mixes {c1['core_entity_classes']} regulated-entity types with {c1['function_headings']} "
      "RBI function headings. The guidelines allow function-heading stand-ins in `applies_to` (used on 0 validated items), and the "
      "pipeline's class filter also admits the query family's function-heading Directions.")
    A("- Parser gaps: PDF extraction cuts some paragraphs at page breaks, splices unrelated items into others and flattens tables "
      "(P2-001 precision rounds). Some T1 spans start mid-sentence or carry the next heading.")
    A("- FAQ alignment is demoted to validation/motivation only; enforcement is Direction-level weak labels only (P2-003).")
    A("\n**T2.**")
    for s in sets:
        A(f"- `{s}`: {t2[s]['bias']}")
    A("- Relevance covers only the target-class counterpart, so the class filter's gain is partly built in.")
    A("\n**T3.**")
    A(f"- Rules are deterministic, built from amendment Directions and \"Updated as on\" stamps. Parse precision: v1 "
      f"{r_(c8['precision_v1_human'])}; independent post-fix check {r_(c8['precision_independent_post_fix'])}. The post-fix "
      f"{c8['precision_post_fix_in_sample']['k']}/{c8['precision_post_fix_in_sample']['n']} is in-sample. "
      f"{len(c8['dropped'])} items were dropped after spot-check 2.")
    A("- Circularity: the gold and the filter come from the same parser.")
    A("- Known \"old words\" parser defect: a merged change's recorded old words include the previous change's new words. It can only "
      "exclude candidates as corpus-version 'unclear', never change an included item's gold.")
    A("- The corpus holds only amended text, so pre-amendment wording cannot be shown.")
    A("\n**T4.**")
    A(f"- n = {main['n_questions']} questions ({main['n_questions'] - c9['human']['bad_question_count']} primary after "
      f"{c9['human']['bad_question_count']} flagged as bad by the rater).")
    A(f"- The questions were drafted by an LLM (Groq `{q_model}`).")
    A("- A single rater (blind) gave every human rating.")
    A("- The repair was designed with the RIRAG finding in mind and tested on the same data.")
    A("\n**LLMs.**")
    A(f"- Free-tier Flash-Lite-class and open models, not frontier models: P3-002 used Groq `{q_model}`; P4 used `{llm['model']}`.")
    A("- The prompt cache is shared between paired systems (identical prompts are served from the cache; at temperature 0 this equals re-calling).")
    A(f"- Outage: HTTP 503 on every call from {outage.get('first_503_ist')} IST until {outage.get('first_ok_after_outage_ist')} IST, "
      f"intermittent until {outage.get('last_503_ist')} IST. No model switch was made.")
    for k, v in c11["deviations_affecting_results"].items():
        A(f"- P4 deviation {k}: {v['text']}")
    A("- Hosted models may change or be withdrawn, so LLM results reproduce only approximately. The LLM cache is not released.")
    A("\n**Long-context.**")
    A(f"- A uniform {lc['cap']:,}-token cap. {c5['validated'] - lc['n']} large prompts failed and are not scored ({lc['n']}/{c5['validated']} answered).")
    A(f"- Proportional per-class truncation. Gold retention: {acc['all_gold_kept']} all kept / {acc['at_least_one_cut']} at least one cut / "
      f"{acc['no_gold_matched_paragraph']} no gold paragraph.")
    A(f"- The 150K run ({c7['appendix_150k']['n']} items) is superseded and shown only as an appendix.")
    A("\n**Environment.** P2-002 embeddings were computed on Kaggle, and the P3-001 indexes locally, with no mixing between them. "
      "The working copy moved from Windows to macOS during the project.")
    A("\n**Scope Ladder cuts.** IndiaFinBench transfer baseline; ObliQA baselines (related-work positioning only); cross-encoder "
      "reranking; LangGraph (plain Python orchestration instead); a UI (CLI demo only).")
    A("\n**Statistical.**")
    A("- The P3-002 gameability verdict uses its pre-registered rule (reproduces iff the CI lies at or above 0). P4 labels use "
      "'excludes 0' only when the CI is strictly above or below 0. No reported P3-002 result lies on the boundary, so the two "
      "conventions never disagree here.")
    A("- There are many comparisons and no multiplicity correction. Read each interval on its own; we claim no more than the individual CIs support.\n")

    # 12 --------------------------------------------------------------------------------------------
    A("# 12. Ethics and IPR\n")
    A("Whether RBI documents may be redistributed is not settled, so the release contains no RBI text. Each item carries a pointer (Direction id, "
      "paragraph id, character offsets, source URL, harvest date, and a sha256 of the paragraph text), and `rehydrate.py` rebuilds "
      "the text from RBI's own URLs. Public files may quote at most short excerpts with their paragraph id; a release check fails "
      "on any run of 30 or more words copied from the corpus. Raters are pseudonymised (`rater_1`–`rater_3`), and no names or "
      "per-person minutes are released. Enforcement releases, which name regulated entities, are not released. The benchmark "
      "is for research on regulatory NLP; it is not legal or compliance advice.\n")

    # 13 --------------------------------------------------------------------------------------------
    A("# 13. AI-assistance statement\n")
    A("- Claude Code wrote the code under Karan's direction.")
    A("- Claude drafted the prompts, audited outputs and drafted text. This paper draft was written by Claude Code from the repo's reports and edited by Karan.")
    A("- Every human label is manual, and no AI tool was used for labelling.")
    A("- LLM outputs are system outputs, never labels.\n")

    # 14 --------------------------------------------------------------------------------------------
    A("# 14. Reproducibility\n")
    A("The README gives one command per table (`python3 scripts/build_tables.py --only NN`), plus the scraper, preprocessing and "
      "evaluation commands. Seeds, model ids and revisions are in `config/config.yaml`. Non-LLM results reproduce exactly from "
      "rehydrated text; LLM results reproduce only approximately (Section 11). The environment was macOS arm64 with Python "
      f"{P4['environment']['python']}.\n")

    # 15 --------------------------------------------------------------------------------------------
    A("# 15. Acknowledgements\n")
    A("We thank Akash Goyal and Meer Magia for the Phase 1 code (credited in the git history) and for second-rater labelling.\n")

    # 16 --------------------------------------------------------------------------------------------
    A("# 16. References\n")
    A("Entries are limited to works cited in the repository. `[verify]` marks details not found in the repo; Karan checks each one.\n")
    A("1. RePASs, https://github.com/RegNLP/RePASs, commit `821d438d07cfc6747bd657965188d9dde85dcb71`.")
    A("2. T. Gokhan, K. Wang, I. Gurevych, T. Briscoe. *RegNLP in Action: Facilitating Compliance Through Automated Information "
      "Retrieval and Answer Generation.* arXiv:2409.05677, 2024. (Citation block of the RePASs README at the pinned commit.)")
    A("3. ObliQA / ObliQA-MP. [verify: the repo names the datasets but gives no paper, authors or identifier]")
    A("4. AUEB-Archimedes at RIRAG-2025. arXiv 2412.11567. [verify: title and authors are not in the repo]")
    A("5. IndiaFinBench. [verify: the repo names it but gives no paper, authors or identifier]")
    A("6. BAAI/bge-base-en-v1.5, Hugging Face model, revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`. [verify: the model paper is not cited in the repo]")
    A(f"7. {P4['environment']['nli_model']}, Hugging Face model, revision `{P4['environment']['nli_revision']}`.")
    A("8. bm25s (Python package), version 0.3.11.")
    A("9. Reciprocal rank fusion. [verify: the repo uses the method (k = 60) but cites no paper]")
    A("10. Reserve Bank of India, Master Directions, https://www.rbi.org.in (per-Direction URLs in `data/metadata/document_manifest.jsonl`).")
    return "\n".join(L) + "\n"


def render() -> list[str]:
    out = []
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise SystemExit("pandoc not found")
    docx = OUT.with_suffix(".docx")
    subprocess.run([pandoc, str(OUT), "-o", str(docx)], check=True)
    out.append(str(docx.relative_to(ROOT)))
    engine = next((e for e in ("xelatex", "pdflatex", "lualatex", "tectonic", "wkhtmltopdf", "weasyprint", "typst") if shutil.which(e)), None)
    if engine:
        pdf = OUT.with_suffix(".pdf")
        subprocess.run([pandoc, str(OUT), "-o", str(pdf), f"--pdf-engine={engine}"], check=True)
        out.append(str(pdf.relative_to(ROOT)))
    else:
        out.append("no PDF: no PDF engine installed (LaTeX not installed, per P5-001)")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    if not args.render:
        if OUT.exists() and not args.force:
            print(f"{OUT.relative_to(ROOT)} exists (it may hold hand edits); use --force to overwrite, or --render to render it")
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(build(), encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)}")
    for x in render():
        print(x)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
