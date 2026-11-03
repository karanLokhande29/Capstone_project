---
title: "RBI-ObliBench: a benchmark for entity-class applicability, differential obligations and metric integrity on Reserve Bank of India Master Directions"
author: "Karan Lokhande"
date: "Draft, 29 September 2026"
---

> **Draft written by Claude Code from the repository's reports; Karan edits it by hand.** Every number is read from `reports/results_v1.json`, `reports/final/error_analysis_v1.json` and the phase metrics files by `scripts/build_report.py`. Tables are in `reports/tables/`. Every interval is a 95% CI; "excludes 0" is used only when an interval is strictly above or below 0 (`src/eval/ci_format.py`).

# 1. Abstract

We build RBI-ObliBench on 381 Reserve Bank of India (RBI) Master Directions (76,188 paragraphs, 11 regulated-entity classes). It has four tasks. T1 asks which entity classes an obligation binds and where parallel Directions differ. It has 106 validated items, labelled by a single expert, with second-rater class-row κ = 0.774 (n = 20 items) and blind test-retest flag κ = 0.426 (n = 20). T2 is cross-class retrieval over three relevance sets. T3 has 52 temporal (as-of date) items. T4 audits the RePASs faithfulness metric on 30 questions. A class filter changes T2 nDCG@10 by +0.451 [+0.421, +0.481] (excludes 0 (above)) on t2_xclass_t1; +0.423 [+0.336, +0.514] (excludes 0 (above)) on t2_xclass_p2002; +0.171 [+0.072, +0.273] (excludes 0 (above)) on t2_supp_p2003. That gain is partly by construction, because relevance was labelled only for the target-class counterpart. The class filter has no significant effect on T1 (3-way flag F1 -0.049 [-0.133, +0.036] (does not exclude 0)). No LLM system significantly beats the P2-002 semantic-matching candidate labels on collapsed flag F1. Every system is weak on `different` judgements (best F1 0.321). The NLI verifier lowers T1 3-way flag F1 by 0.068 (-0.068 [-0.132, -0.012] (excludes 0 (below))). A long-context baseline (100K-token cap, n = 102) is statistically tied with the retrieval systems on 3-way F1. On RBI text, RePASs is gameable by concatenation (concatenated − genuine +0.375 [+0.325, +0.427] (excludes 0 (above))) but not by negated or off-topic answers. It tracks human faithfulness (Spearman ρ 0.731 [0.535, 0.845]) but not whether the answer addresses the question (ρ 0.008 [-0.323, 0.339]). The exploratory repair is not usable. We release annotations, pointers and code; RBI text is rehydrated from RBI's own URLs.

# 2. Introduction and research questions

RBI issues many of its Master Directions in parallel, one per class of regulated entity (commercial banks, small finance banks, NBFCs, co-operative banks and others), often on the same subject. A compliance question is therefore only answerable for a declared entity class: the same paragraph can bind one class, have a counterpart with different content for another, and not exist for a third. Directions are also amended in place, so the answer depends on the date. RBI-ObliBench turns these properties into evaluation tasks and asks whether a retrieval-augmented system, and the metric used to score it, cope with them.

- **RQ1 — Applicability:** Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?
- **RQ2 — Differential Obligation:** For a subject issued in parallel across entity classes, can the system identify what one entity class is required to do that another entity class is not?
- **RQ3 — Metric Integrity:** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair makes the metric resistant to concatenation/verbatim extraction?

Contributions: (i) a pointer-only corpus and entity-class × subject-family matrix; (ii) T1, a validated applicability and differential-obligation set with its reliability evidence; (iii) T2 relevance sets with their construction biases stated; (iv) T3, a deterministic temporal set built from amendment Directions; (v) T4, an audit of RePASs on RBI text; (vi) a class- and date-aware RAG pipeline with ablations A–C and long-context and non-LLM baselines, all with bootstrap 95% CIs.

# 3. Related work

RePASs [1, 2] scores answers to regulatory questions by entailment, contradiction and obligation coverage against the retrieved passages. It was introduced with ObliQA [3] in the RegNLP line of work on financial-regulation QA. At the RIRAG-2025 shared task, a naive obligation-concatenation system scored RePASs 0.947, above human experts, on ObliQA [4]. T4 tests whether that gameability carries over to Indian regulatory text. We use ObliQA and RIRAG for positioning only: their tasks, corpora and metrics are not interchangeable with ours, and we report no cross-benchmark comparison. IndiaFinBench [5] was planned as a transfer baseline and was cut (Section 11).

# 4. Corpus and entity-class × subject-family matrix

The corpus is every Master Direction on RBI's listing: 381 Directions and 76,188 paragraphs (Table 1). An early harvest missed 81 Directions: the first downloads received HTML instead of PDFs (master-prompt defect D1). The P1-004 repair recovered all of them plus 1 newly listed, and no Direction is missing now. The listing gives each Direction an entity-class heading. Of the 19 headings, 11 are regulated-entity classes and 8 are RBI function headings such as Foreign Exchange Management (D8). Subject families are derived from titles: 57 families, assigned to 305/381 Directions. Three Directions have empty titles and no family (D2: md_11510, md_11959, md_12839). The matrix has 1083 class × family cells; 296 are populated (coverage 0.273), 9 ambiguous and 9 with duplicate mappings.

**Obligation candidates (P2-001).** A deontic-cue rule set marks 33,507 paragraphs and keeps 28,694 candidates. Manual precision rose over four rule versions, from 27/40 = 0.675 (Wilson 95% [0.520, 0.799]) (v1, which triggered the stop rule) to 26/28 = 0.929 (Wilson 95% [0.774, 0.980]) (v4, measured on re-admitted candidates only; Table 2).

**Cross-class matching (P2-002).** Each candidate is matched to its counterpart in the other classes with bge-base-en-v1.5 embeddings. On 60 validation pairs drawn across score bands, the counterpart rate (same or related) is 53/60 = 0.883 (Wilson 95% [0.778, 0.942]). The operating threshold (0.757567) was chosen on the same sample it is scored on (Table 3).

**Supplementary sources (P2-003).** RBI FAQs and enforcement releases were hand-aligned to paragraphs. Under a pre-registered rule, faq aligned cleanly on 5/30 = 0.167 (Wilson 95% [0.073, 0.336]), so it becomes `validation_or_motivation_only`; enforcement aligned cleanly on 16/30 = 0.533 (Wilson 95% [0.361, 0.698]), so it becomes `direction_level_weak_label_only`. Both intervals cross a decision line (Table 4).

# 5. T1 benchmark construction

**Guidelines v3** (`release/guidelines/ANNOTATION_INSTRUCTIONS.md`) define, for a source obligation paragraph and up to four compared entity classes, a per-class judgement (`same`: the compared class has a counterpart obligation with the same content; `different`: a counterpart exists but its content differs; `none`: no counterpart), the matched counterpart paragraph, `applies_to`, and a differential flag (`shared`, `class-specific`, `absent`).

**Sampling.** 123 candidates were drawn with a seed, stratified by source class (proportional, with a floor per core class), and spread over subject families and candidate flags. Each item has at most 4 compared classes (3 items with 2, 6 items with 3, 97 items with 4).

**Blind sheets.** Sheets show no candidate labels, scores or retest membership; a hidden key holds them. The second raters started from blank files, and the tooling rejects a file whose judgements arrive pre-filled (the D11 guard).

**Provenance routes.** 106 items were validated and 17 rejected as not an obligation (17/123 = 0.138 (Wilson 95% [0.088, 0.210])). Routes: adjudicated 38, retest-consistent 6, single-pass 62. Most items (62) were labelled once, by one annotator.

**Reliability** (Table 5). Single-expert annotations with second-rater class-row κ = 0.774 [0.645, 0.886] (n = 20 items, 80 units) and blind test-retest flag κ = 0.426 [0.091, 0.730] (n = 20 items, 20 units). The inter-rater set is 30 items labelled by three raters before adjudication (Fleiss' κ): flag 0.571 [0.289, 0.807] (n = 20 items, 20 units); not-obligation 0.392 [-0.015, 0.689] (n = 30 items, 30 units). The test-retest was blind but had no washout period: test-retest class-row κ 0.550 [0.333, 0.752] (n = 20 items, 78 units). On 20 single-pass items, a timed blind re-label agrees with pass 1 at flag κ 0.409 [0.042, 0.759] (n = 19 items, 19 units) and class-row κ 0.684 [0.506, 0.872] (n = 19 items, 72 units). The Phase 1 pilot Fleiss flag κ (0.603, n = 17, point estimate) is **conditional** (D11): every rater judged against the same pre-filled `applies_to`, which may have anchored it. Candidate labels from P2-002 agree with the validated labels on high band 119/119 = 1.000 (Wilson 95% [0.969, 1.000]), mid band 125/132 = 0.947 (Wilson 95% [0.895, 0.974]), low band 114/161 = 0.708 (Wilson 95% [0.634, 0.773]).

# 6. Tasks and metrics

- **T1 (RQ1, RQ2).** Input: a source obligation and its compared classes. Output: a per-class judgement and the derived flag. Metrics: 3-way flag Macro-F1 over shared / class-specific / absent (a predicted `ambiguous` counts as wrong); collapsed Macro-F1 (absent vs present); judgement Macro-F1 and per-label F1; coverage (share of items with a non-ambiguous flag). The P2-002 candidates cannot say `shared` vs `class-specific`, so 3-way F1 favours the LLM systems by design and collapsed F1 is the fair comparison with them.
- **T2 (RQ1).** Retrieve the counterpart paragraph in a named target class. Three relevance sets: `t2_xclass_t1` (n = 291); `t2_xclass_p2002` (n = 53); `t2_supp_p2003` (n = 25). Metrics: Recall@10, MAP@10, nDCG@10.
- **T3.** Given a paragraph and an as-of date, give its status (in force original / amended / deleted) and the governing instrument. Metrics: status exact match and supersession F1.
- **T4 (RQ3).** Thirty questions with four answer types (genuine, concatenated, negated, off-topic). Metrics: RePASs composite and components, and human `faithful` / `answers_question` ratings on 30 answers.

Every CI is a seeded bootstrap with 2,000 resamples over items, or over queries or questions; differences are paired. There is no correction for multiple comparisons.

# 7. Systems and baselines

- **Non-LLM baselines.** For T1: the majority class (fitted in-sample) and the P2-002 candidate labels. For T2: BM25 (bm25s, Lucene variant), dense bge-base-en-v1.5, hybrid reciprocal rank fusion (RRF, k = 60), class-aware hybrid (restricted to the target class's Directions), and `hybrid_minus_source_class` (class-blind, with the query's own class removed).
- **Pipeline (P4).** Hybrid RRF retrieval, then an optional class filter (the target class plus the same family's function-heading Directions), an optional temporal filter (from the T3 amendment parser), a JSON-mode LLM answer and an optional NLI verifier. The verifier (`cross-encoder/nli-deberta-v3-xsmall` @ `a15087641532`) checks each cited claim against the whole cited paragraph. If a claim is unsupported, it retries once, with the query extended by the unsupported rationales, and then abstains on any class still unsupported (`unsure`).
- **T1 systems.** Class-blind LLM (no filter, no verifier); class-aware LLM (filter); final agentic (filter + verifier); class-blind + verifier (ablation A).
- **Long-context LLM.** The same model reads every compared class's Directions directly, without retrieval, capped at 100,000 input tokens with proportional truncation per class.
- **LLMs (exact ids, Table 11).** P4: `gemini-3.5-flash-lite` (version `3.5-flash-lite-07-2026`), temperature 0, thinking `{'thinkingLevel': 'minimal'}`, no provider fallback. P3-002 question drafting and genuine answers: Groq `openai/gpt-oss-120b`. All calls are cached on disk by a hash of (provider, model, messages, parameters).

# 8. Results

## 8.1 RQ1 — Applicability

The class filter improves T2 retrieval on all three relevance sets (pipeline retrieval stage, filter ON − OFF, nDCG@10): `t2_xclass_t1` +0.451 [+0.421, +0.481] (excludes 0 (above)); `t2_xclass_p2002` +0.423 [+0.336, +0.514] (excludes 0 (above)); `t2_supp_p2003` +0.171 [+0.072, +0.273] (excludes 0 (above)). **This gain is partly by construction:** relevance was labelled only for the counterpart in the target class, so near-identical paragraphs that a class-blind system returns from other classes count as misses. The class-blind comparison that removes only the source class, `hybrid_minus_source_class`, reaches nDCG@10 0.464 [0.429, 0.497] on `t2_xclass_t1`; 0.337 [0.256, 0.429] on `t2_xclass_p2002`; 0.504 [0.348, 0.673] on `t2_supp_p2003`. Class-aware minus that system: +0.430 [+0.400, +0.462] (excludes 0 (above)) on `t2_xclass_t1`; +0.404 [+0.324, +0.484] (excludes 0 (above)) on `t2_xclass_p2002`; +0.171 [+0.074, +0.272] (excludes 0 (above)) on `t2_supp_p2003`.

The class-blind dense retriever reaches nDCG@10 0.421 [0.385, 0.455] on `t2_xclass_t1`; 0.334 [0.252, 0.428] on `t2_xclass_p2002`; 0.362 [0.212, 0.528] on `t2_supp_p2003`, against 0.894 [0.864, 0.922]; 0.741 [0.630, 0.844]; 0.675 [0.535, 0.811] for the class-aware hybrid (same order). Each relevance set is biased towards one retriever (Table 6): the first two towards the dense model, the third towards BM25.

On T1 the class filter has no significant effect: 3-way flag F1 -0.049 [-0.133, +0.036] (does not exclude 0) with the verifier on and -0.050 [-0.133, +0.027] (does not exclude 0) without it (n = 106).

## 8.2 RQ2 — Differential obligation

No LLM system significantly beats the P2-002 candidate labels on collapsed flag F1 (Table 7): Class-blind LLM -0.019 [-0.114, +0.072] (does not exclude 0); Class-aware LLM +0.024 [-0.096, +0.135] (does not exclude 0); Final agentic -0.074 [-0.192, +0.036] (does not exclude 0); Class-blind + verifier -0.089 [-0.186, +0.006] (does not exclude 0). On 3-way F1 the class-blind LLM is highest among all systems (0.602 [0.497, 0.700]), ahead of class-aware (0.551 [0.445, 0.639]) and final agentic (0.483 [0.385, 0.568]). 3-way F1 favours the LLMs over P2-002 by design.

Every system is weak on `different` judgements. F1 on `different`: class-blind 0.321, class-aware 0.154, final agentic 0.047, class-blind + verifier 0.176, long-context 0.074 (point estimates). Of 78 gold `different` class rows, 56 are missed by every LLM system; most are answered `none` or `same` (Section 8.7). Class-specific differences are therefore the benchmark's hardest case. This is a finding about what the benchmark catches: systems that match counterparts well still do not say what differs between them.

## 8.3 Verifier (ablation C on T1)

The verifier changes 3-way flag F1 by -0.068 [-0.132, -0.012] (excludes 0 (below)) and coverage by -0.217 [-0.292, -0.142] (excludes 0 (below)) (final agentic − class-aware, n = 106); it lowers 3-way flag F1 by 0.068 and coverage by 0.217. On the class-blind side it lowers 3-way flag F1 by 0.069 (-0.069 [-0.129, -0.014] (excludes 0 (below))). Final agentic has 86 `unsure` judgements: 81 verifier abstentions and 5 model outputs the parser rejected as invalid. Of the 81 abstentions, 59 were correct on the first pass. A post hoc diagnostic shows the verifier does not raise precision on the items it keeps (P4 report, diagnostic a).

## 8.4 Long-context baseline

At the uniform 100K cap, 102 of 106 items were answered; the other 4 prompts failed repeatedly (the prompt size of answered items has median 71,727 tokens, of unanswered 95,910). On the same 102 items the long-context model is statistically tied with P2-002, class-blind and class-aware on both flag metrics: P2-002 candidates 3-way +0.057 [-0.044, +0.163] (does not exclude 0), collapsed +0.045 [-0.093, +0.176] (does not exclude 0); class-blind 3-way -0.097 [-0.197, +0.010] (does not exclude 0), collapsed +0.054 [-0.047, +0.159] (does not exclude 0); class-aware 3-way -0.035 [-0.128, +0.063] (does not exclude 0), collapsed +0.023 [-0.088, +0.142] (does not exclude 0). It matches final agentic on 3-way F1 (+0.030 [-0.067, +0.129] (does not exclude 0)) and beats final agentic (+0.126 [+0.016, +0.240] (excludes 0 (above))) and class-blind + verifier (+0.127 [+0.018, +0.234] (excludes 0 (above))) on collapsed F1. It is weak on `different` (F1 0.074). Gold retention: of 102 scored items, 82 kept every gold counterpart in the prompt, 7 lost at least one to truncation and 13 have no gold counterpart. A 150K-cap run on 47 items is superseded and shown only in the Table 7 appendix (D10).

## 8.5 RQ3 — Metric integrity (T4)

Concatenation gameability reproduces: concatenated − genuine RePASs +0.375 [+0.325, +0.427] (excludes 0 (above)) (n = 30, pre-registered verdict: reproduces). The adversarial versions do not: negated − genuine -0.322 [-0.390, -0.243] (excludes 0 (below)), off-topic − genuine -0.141 [-0.206, -0.080] (excludes 0 (below)). The verdicts are the same without the 2 questions the rater flagged as bad (n = 28). RePASs correlates with human `faithful` at Spearman ρ 0.731 [0.535, 0.845] and with `answers_question` at ρ 0.008 [-0.323, 0.339] (n = 30). Concatenated answers are faithful by construction, and RePASs rewards them without checking that they address the question.

The exploratory repair (an overlap penalty on verbatim text plus a question-relevance term) ranks genuine above every other type (genuine − concatenated +0.208 [+0.168, +0.253] (excludes 0 (above)); genuine − adv_negated +0.202 [+0.162, +0.246] (excludes 0 (above)); genuine − adv_offtopic +0.091 [+0.050, +0.136] (excludes 0 (above))). It is **not usable**: it works only because the penalty zeroes every verbatim answer, and it no longer tracks human faithfulness (ρ -0.126 [-0.477, 0.216]). It was also designed with the RIRAG finding in mind and tested on the same 30 questions.

In ablation C on T4 (n = 28 primary questions), the verifier changes the RePASs composite by -0.055 [-0.121, +0.015] (does not exclude 0): not significant. On the 17 questions the verifier answered, the change is +0.040 [+0.0000, +0.113] (does not exclude 0). The verifier and RePASs share an NLI model (`cross-encoder/nli-deberta-v3-xsmall`), so any agreement between them is partly the same model agreeing with itself. The verifier changes T4 abstention by +0.393 [+0.214, +0.571] (excludes 0 (above)).

## 8.6 T3 — Temporal

With the temporal filter on, status exact match is 1.000 [1.000, 1.000]. **This 1.000 is circular by construction**: the gold and the filter come from the same deterministic parser, so T3 measures only whether the LLM uses the dates it is given. Without the filter the model almost always answers "in force, original": 48 of 52 items, giving exact match 0.538 [0.404, 0.673]. The corpus holds only the current (amended) text of each Direction, so the system can flag a later amendment but cannot show the pre-amendment wording. The result holds without the window-type items (Table 8).

## 8.7 Error analysis and failure cases

Cases were selected by a fixed rule (qualifying cases sorted by id; first two shown (first one per retention group for long-context)), not by eye. Examples are pointers plus at most 25 words of text; `release/rehydrate.py` restores the full paragraphs. Full lists: `reports/tables/13_error_analysis.md`. Per-class results and confusion matrices: `reports/tables/12_t1_per_class.md`.

**(a) Missed `different` judgements.** 56 of 78 gold `different` class rows are missed by every LLM system. Recall on `different`: Class-blind LLM 18/78 = 0.231 (Wilson 95% [0.151, 0.336]); Class-aware LLM 7/78 = 0.090 (Wilson 95% [0.044, 0.174]); Final agentic 2/78 = 0.026 (Wilson 95% [0.007, 0.089]); Class-blind + verifier 8/78 = 0.103 (Wilson 95% [0.053, 0.190]); Long-context (100K) 3/76 = 0.039 (Wilson 95% [0.014, 0.110]).
- `t1_md_12925::p00061`, Credit Information Companies vs Rural Co-operative Banks (gold counterpart `md_12986::p00025`). Source md_12925::p00061, offsets [[0, 114]]: “commensurate processes to manage those risks. For this purpose, the CIC shall, inter alia, consider the following:”. Every LLM system answered: none.
- `t1_md_12945::p00050`, Non-Banking Financial Companies vs Payments Banks (gold counterpart `md_13092::p00184`). Source md_12945::p00050, offsets [[0, 333]]: “21. An NBFC shall make following disclosures in ‘Notes to Accounts’ to the financial statements. (1) Loans against gold and silver collateral i) Details of …”. Every LLM system answered: none.

**(b) Verifier abstentions on correct first answers.** Final agentic abstained on 81 class judgements; 59 of them were correct before the retry. On 14 items the first-pass flag was right and the final flag wrong. For class-blind + verifier: 60 of 80, and 15 items.
- Final agentic, `t1_md_12927::p00153`: first-pass flag `shared` (= gold), final `ambiguous` after abstaining on 4 of 4 classes. Source md_12927::p00153: “only after closure of any critical gap found during such tests. Such tests shall also be carried out periodically in conformity with internal / regulatory …”.
- Final agentic, `t1_md_12928::p00016`: first-pass flag `shared` (= gold), final `ambiguous` after abstaining on 2 of 4 classes. Source md_12928::p00016: “(1) Any account included in LWD, where an ARC has entered into a compromise settlement with the borrower, shall be removed from the LWD only …”.
- Class-blind + verifier, `t1_md_12925::p00044`: first-pass flag `class-specific` (= gold), final `ambiguous` after abstaining on 4 of 4 classes. Source md_12925::p00044: “9. A CIC intending to outsource its IT services shall put in place a comprehensive Board-approved IT outsourcing policy, the coverage of which is indicated …”.
- Class-blind + verifier, `t1_md_12927::p00153`: first-pass flag `shared` (= gold), final `ambiguous` after abstaining on 4 of 4 classes. Source md_12927::p00153: “only after closure of any critical gap found during such tests. Such tests shall also be carried out periodically in conformity with internal / regulatory …”.

**(c) Long-context errors.** Flag errors by gold retention: all gold kept: 34 of 82; at least one gold cut: 6 of 7; no gold matched paragraph: 3 of 13.
- `t1_md_12925::p00044` (all gold kept, 4/4 gold paragraphs in the prompt, about 73,757 tokens): gold `class-specific`, predicted `shared`. Source md_12925::p00044: “9. A CIC intending to outsource its IT services shall put in place a comprehensive Board-approved IT outsourcing policy, the coverage of which is indicated …”.
- `t1_md_12968::p00044` (at least one gold cut, 2/4 gold paragraphs in the prompt, about 99,763 tokens): gold `class-specific`, predicted `shared`. Source md_12968::p00044: “(ii) Default in repayment by the borrower is also a type of non-compliance of material terms and conditions of loan repayment contract by the borrower …”.

**(d) T3 without the temporal filter.** 24 status errors on 52 items: gold amended (after the effective date) → predicted in_force_original (17); gold deleted (after the effective date) → predicted in_force_original (6); gold in_force_original (before the effective date) → predicted deleted (1).
- `T3-002`: md_13071::p00180 as of 2026-05-18, after the amendment effective 2026-05-18; gold `amended` (`amd_13453`), predicted `in_force_original` (`md_13071`).
- `T3-004`: md_13075::p00048 as of 2026-05-04, after the amendment effective 2026-04-01; gold `deleted` (`amd_13251`), predicted `in_force_original` (`md_13075`).

**(e) RePASs vs human `faithful`.** Rule: human faithful = 2 with RePASs composite < 0.5, or faithful = 0 with composite >= 0.5 (a display threshold chosen for this analysis after scoring, not pre-registered). Rated faithful 2 but scored low: 7 (genuine 6, concatenated 1); rated 0 but scored high: 0.
- `T4Q02` (genuine): human faithful 2, RePASs 0.415 (entailment 0.220, contradiction 0.310, coverage 0.333). Answer (release/data/t4/answers_genuine.jsonl, T4Q02): “You may proceed only after any critical gap identified in the tests has been closed — the tests must be completed and any critical gaps …”.
- `T4Q06` (genuine): human faithful 2, RePASs 0.140 (entailment 0.209, contradiction 0.989, coverage 0.200). Answer (release/data/t4/answers_genuine.jsonl, T4Q06): “No. The RBI’s Master Directions require that any penalty imposed for a borrower’s default be levied only as a **penal charge**, not as “penal interest,” …”.

# 9. Ablations

Table 10 puts ablations A–C in one table (ON − OFF, everything else at the final agentic setting). A (class filter) helps T2 and does nothing significant on T1. B (temporal filter) changes T3 status exact match by +0.462 [+0.327, +0.596] (excludes 0 (above)); this is circular (Section 8.6). C (verifier) changes T1 3-way flag F1 by -0.068 [-0.132, -0.012] (excludes 0 (below)), T4 abstention by +0.393 [+0.214, +0.571] (excludes 0 (above)) and the T4 unsupported-sentence rate (an NLI proxy, all 28 questions) by -0.382 [-0.552, -0.214] (excludes 0 (below)). On answered questions only, where ON is 0 by construction, that rate changes by -0.129 [-0.300, +0.0000] (does not exclude 0).

# 10. Discussion

**Why an agent?** On this data, the agentic additions did not pay off on T1. The class filter's value is real for retrieving a named class's counterpart (T2), but it did not change T1 judgement. The verifier made T1 worse and abstained on many correct first answers. The whole-paragraph NLI premise is a poor test for a one-sentence rationale about a counterpart. The long-context model, which skips retrieval, is tied with the retrieval systems on 3-way F1 and beats both verifier systems on collapsed F1. On T1, where each item names its classes and the relevant Directions fit in a 100K-token prompt for most items, retrieval was not the bottleneck; deciding what differs was.

**What is new.** The benchmark isolates a case that generic regulatory QA does not test: a paragraph whose counterpart exists in another class but says something different. Every system here, from embedding matching to long-context reading, is weak on it. T4 shows that on RBI text RePASs rewards verbatim concatenation, as it did on ObliQA, but resists negation and off-topic text. The failure is that it does not check relevance to the question, not that it cannot detect contradiction.

**What went against expectations.** The class-aware and final agentic systems did not beat the class-blind LLM on T1. No LLM system beat the P2-002 candidate labels on collapsed F1. The verifier lowered T1 F1 and did not raise precision on the items it kept. The long-context baseline was not worse than the pipeline. The metric repair failed. The adversarial answers did not fool RePASs.

# 11. Limitations and threats to validity

**T1 size and labels.**
- 106 validated items out of 123 sampled; 17 rejected as not an obligation (17/123 = 0.138 (Wilson 95% [0.088, 0.210])). Source classes have between 7 and 15 items each (Table 5), so per-class results (Table 12) have wide intervals. Compared classes are capped at 4 per item, and `applies_to` and the flag are defined over those classes only.
- Routes: adjudicated 38, retest-consistent 6, single-pass 62. Most labels are single-pass: one annotator, one pass.
- The second-rater subset is 30 items; single-expert annotations with second-rater class-row κ = 0.774 (n = 20) and blind test-retest flag κ = 0.426 (n = 20).
- The test-retest is blind but had no washout period; the short interval may inflate agreement through recall. Three corrected pilot rows may not be blind.
- The pilot κ (0.603, n = 17) is conditional on a pre-filled `applies_to` (D11). The pilot test-retest flag κ is -0.128 [-0.377, 0.070] (n = 16 items, 16 units).
- The overlap team-review file declares `label_source` as "manual (declared by Karan); revised after reviewer (Claude) feedback on file-level patterns, not on label content; not independent". It carries no κ by design.
- `absent` covers only the paragraphs shown or looked up.

**Corpus.**
- D1: an early harvest missed 81 Directions; the P1-004 repair recovered them, and none is missing now. Every P2 artefact was computed on the full 381.
- D2: 3 Directions have empty titles and no subject family.
- Subject families are derived from titles, not assigned by RBI.
- D8: the entity-class vocabulary mixes 11 regulated-entity types with 8 RBI function headings. The guidelines allow function-heading stand-ins in `applies_to` (used on 0 validated items), and the pipeline's class filter also admits the query family's function-heading Directions.
- Parser gaps: PDF extraction cuts some paragraphs at page breaks, splices unrelated items into others and flattens tables (P2-001 precision rounds). Some T1 spans start mid-sentence or carry the next heading.
- FAQ alignment is demoted to validation/motivation only; enforcement is Direction-level weak labels only (P2-003).

**T2.**
- `t2_xclass_t1`: Raters were shown the bge-base-en-v1.5 top-1/top-2 P2-002 candidates for each compared class (they could look up any paragraph), so the labelled counterparts favour the dense retriever.
- `t2_xclass_p2002`: Pairs were drawn by bge-base-en-v1.5 semantic-score bands (the same model and revision as the dense system), so the relevant paragraphs favour the dense retriever.
- `t2_supp_p2003`: Candidates shown to the rater were ranked by TF-IDF, which favours BM25 (the rater could enter any paragraph id of the Direction).
- Relevance covers only the target-class counterpart, so the class filter's gain is partly built in.

**T3.**
- Rules are deterministic, built from amendment Directions and "Updated as on" stamps. Parse precision: v1 15/20 = 0.750 (Wilson 95% [0.531, 0.888]); independent post-fix check 8/10 = 0.800 (Wilson 95% [0.490, 0.943]). The post-fix 20/20 is in-sample. 8 items were dropped after spot-check 2.
- Circularity: the gold and the filter come from the same parser.
- Known "old words" parser defect: a merged change's recorded old words include the previous change's new words. It can only exclude candidates as corpus-version 'unclear', never change an included item's gold.
- The corpus holds only amended text, so pre-amendment wording cannot be shown.

**T4.**
- n = 30 questions (28 primary after 2 flagged as bad by the rater).
- The questions were drafted by an LLM (Groq `openai/gpt-oss-120b`).
- A single rater (blind) gave every human rating.
- The repair was designed with the RIRAG finding in mind and tested on the same data.

**LLMs.**
- Free-tier Flash-Lite-class and open models, not frontier models: P3-002 used Groq `openai/gpt-oss-120b`; P4 used `gemini-3.5-flash-lite`.
- The prompt cache is shared between paired systems (identical prompts are served from the cache; at temperature 0 this equals re-calling).
- Outage: HTTP 503 on every call from 2026-09-28 20:09:51 IST until 2026-09-28 22:19:25 IST, intermittent until 2026-09-29 01:59:44 IST. No model switch was made.
- P4 deviation D10: The note-2 fallback was triggered EARLY: the long-context baseline is rerun on all 106 items at one uniform 100K cap (same proportional per-class truncation) without first finishing the 150K remainder run and retry pass. The decision was based ONLY on the failure-size evidence: never-answered prompts had a median of about 150K tokens (14 items, range 60K–150K) against about 71K for the 47 scored items (range 6K–132K). Disclosure: long-context scores on those 47 scored items had already been computed and displayed in Claude's session (3-way flag F1 0.515 [0.374, 0.626] against final agentic 0.518 on the same items) before Claude recommended the rerun; Claude's recommendation cited only the size evidence, and Karan decided on that evidence. The 150K run's items are kept only as a record, never reported as the baseline. Items under 100K reuse the cache (identical prompt). Pre-committed next step: if more than 20% of items still fail at 100K after one retry pass, one step down to a uniform 64K cap for all items; if failures remain after that, long-context is reported only on the scored items with the size distribution and every system compared on exactly those items; no further cap changes. A health probe and a 3-consecutive-failure circuit breaker stop provider outages from spending quota.
- P4 deviation D11: Claude stopped the 150K remainder step on the 3-hour compute rule using wall-clock time (4 h). Measured as actual run time (Mac awake, from the power log), that step ran about 62 minutes (6 + 55 min), so the rule was not reached. Run times in this report are active time (macOS monotonic clock, which stops while the Mac sleeps); wall time is shown alongside.
- P4 deviation D12: Before the outage cutoff, the 37 long-context items whose 100K prompt is byte-identical to a cached 150K prompt were scored from the cache (cache-only mode: no API call, no ledger entry); their outputs are identical to the 150K run. Gemini then recovered overnight and the chain completed the 100K pass and one retry pass: 102 of 106 items answered, 4 still failing (4%, below the 20% step-down threshold, so no 64K rerun). The demo transcripts ran on Gemini; the Groq demo fallback was never used.
- Hosted models may change or be withdrawn, so LLM results reproduce only approximately. The LLM cache is not released.

**Long-context.**
- A uniform 100,000-token cap. 4 large prompts failed and are not scored (102/106 answered).
- Proportional per-class truncation. Gold retention: 82 all kept / 7 at least one cut / 13 no gold paragraph.
- The 150K run (47 items) is superseded and shown only as an appendix.

**Environment.** P2-002 embeddings were computed on Kaggle, and the P3-001 indexes locally, with no mixing between them. The working copy moved from Windows to macOS during the project.

**Scope Ladder cuts.** IndiaFinBench transfer baseline; ObliQA baselines (related-work positioning only); cross-encoder reranking; LangGraph (plain Python orchestration instead); a UI (CLI demo only).

**Statistical.**
- The P3-002 gameability verdict uses its pre-registered rule (reproduces iff the CI lies at or above 0). P4 labels use 'excludes 0' only when the CI is strictly above or below 0. No reported P3-002 result lies on the boundary, so the two conventions never disagree here.
- There are many comparisons and no multiplicity correction. Read each interval on its own; we claim no more than the individual CIs support.

# 12. Ethics and IPR

Whether RBI documents may be redistributed is not settled, so the release contains no RBI text. Each item carries a pointer (Direction id, paragraph id, character offsets, source URL, harvest date, and a sha256 of the paragraph text), and `rehydrate.py` rebuilds the text from RBI's own URLs. Public files may quote at most short excerpts with their paragraph id; a release check fails on any run of 30 or more words copied from the corpus. Raters are pseudonymised (`rater_1`–`rater_3`), and no names or per-person minutes are released. Enforcement releases, which name regulated entities, are not released. The benchmark is for research on regulatory NLP; it is not legal or compliance advice.

# 13. AI-assistance statement

- Claude Code wrote the code under Karan's direction.
- Claude drafted the prompts, audited outputs and drafted text. This paper draft was written by Claude Code from the repo's reports and edited by Karan.
- Every human label is manual, and no AI tool was used for labelling.
- LLM outputs are system outputs, never labels.

# 14. Reproducibility

The README gives one command per table (`python3 scripts/build_tables.py --only NN`), plus the scraper, preprocessing and evaluation commands. Seeds, model ids and revisions are in `config/config.yaml`. Non-LLM results reproduce exactly from rehydrated text; LLM results reproduce only approximately (Section 11). The environment was macOS arm64 with Python 3.14.3.

# 15. Acknowledgements

We thank Akash Goyal and Meer Magia for the Phase 1 code (credited in the git history) and for second-rater labelling.

# 16. References

Entries are limited to works cited in the repository. `[verify]` marks details not found in the repo; Karan checks each one.

1. RePASs, https://github.com/RegNLP/RePASs, commit `821d438d07cfc6747bd657965188d9dde85dcb71`.
2. T. Gokhan, K. Wang, I. Gurevych, T. Briscoe. *RegNLP in Action: Facilitating Compliance Through Automated Information Retrieval and Answer Generation.* arXiv:2409.05677, 2024. (Citation block of the RePASs README at the pinned commit.)
3. ObliQA / ObliQA-MP. [verify: the repo names the datasets but gives no paper, authors or identifier]
4. AUEB-Archimedes at RIRAG-2025. arXiv 2412.11567. [verify: title and authors are not in the repo]
5. IndiaFinBench. [verify: the repo names it but gives no paper, authors or identifier]
6. BAAI/bge-base-en-v1.5, Hugging Face model, revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`. [verify: the model paper is not cited in the repo]
7. cross-encoder/nli-deberta-v3-xsmall, Hugging Face model, revision `a150876415327c80daeff35ca6f68f5ed8cf5c24`.
8. bm25s (Python package), version 0.3.11.
9. Reciprocal rank fusion. [verify: the repo uses the method (k = 60) but cites no paper]
10. Reserve Bank of India, Master Directions, https://www.rbi.org.in (per-Direction URLs in `data/metadata/document_manifest.jsonl`).
