# RBI-ObliBench — Master Document

**A benchmark for entity-class applicability, differential obligations and metric integrity on Reserve Bank of India Master Directions, with a class- and date-aware retrieval pipeline**

- **Authors:** Karan Lokhande, Akash Goyal, Meer Magia
- **Institution:** SVKM's NMIMS Mukesh Patel School of Technology Management & Engineering, Mumbai
- **Date:** 2026-10-03
- **Version:** v1 (final-push master record)
- **Scope of this record:** the gold set is `t1_validated_v1` (single expert). Every number is read from `reports/results_v2.json`, `reports/final/error_analysis_v1.json` or the phase metrics files.

## 1. Executive summary

RBI-ObliBench is built on 381 RBI Master Directions (76,188 paragraphs). It has four tasks:
- **T1:** applicability and differential obligation across entity classes;
- **T2:** cross-class counterpart retrieval;
- **T3:** temporal status;
- **T4:** an audit of the RePASs answer-faithfulness metric.

Around the benchmark we built a class- and date-aware retrieval-and-judgement pipeline as an engineering artefact. The benchmark is the contribution; the pipeline is evaluated on it.

**Research questions (verbatim):**

- **RQ1 — Applicability:** Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?
- **RQ2 — Differential Obligation:** For a subject issued in parallel across entity classes, can the system identify what one entity class is required to do that another entity class is not?
- **RQ3 — Metric Integrity:** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair makes the metric resistant to concatenation/verbatim extraction?

**Headline findings:**

1. **The class filter improves retrieval.** nDCG@10 on `t2_xclass_t1` changes by +0.451 [+0.421, +0.481] (excludes 0 (above)). The gain is partly by construction, because relevance was labelled only for the target-class counterpart.
2. **It doesn't translate into better T1 judgement.** Class-aware − class-blind 3-way flag F1: -0.050 [-0.133, +0.027] (does not exclude 0). No LLM system beats the P2-002 candidate labels on collapsed flag F1.
3. **`different` is the core failure mode.** Of 78 gold `different` class units, 56 are missed by every LLM system (all five answered), or 58 counting only the systems that answered.
4. **The verifier hurts T1.** Final agentic − class-aware 3-way flag F1: -0.068 [-0.132, -0.012] (excludes 0 (below)).
5. **Long-context is competitive.** It answered 102 items at the 100K cap. Long-context − final agentic collapsed F1 on the same items: +0.126 [+0.016, +0.240] (excludes 0 (above)).
6. **RePASs concatenation gameability reproduces.** Concatenated − genuine composite: +0.375 [+0.325, +0.427] (excludes 0 (above)) (pre-registered verdict: reproduces).
7. **The pairwise structured comparator** (the targeted experiment, frozen before any T1 run) reaches `different` F1 0.409 and recall 0.487. Comparator − class-aware `different` F1: +0.255 [+0.094, +0.411] (excludes 0 (above)).

## 2. Research questions and tasks

- **RQ1 — Applicability:** Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?
- **RQ2 — Differential Obligation:** For a subject issued in parallel across entity classes, can the system identify what one entity class is required to do that another entity class is not?
- **RQ3 — Metric Integrity:** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair makes the metric resistant to concatenation/verbatim extraction?

**Tasks:**
- **T1 (RQ1, RQ2).** Given a source obligation and its compared entity classes, give a per-class judgement (`same` / `different` / `none`) with a matched paragraph. The item's differential flag (shared / class-specific / absent) is derived from the judgements.
- **T2 (RQ1).** Retrieve the counterpart paragraph in a named target class.
- **T3.** Give the status of a paragraph (in force, amended, deleted) on an as-of date.
- **T4 (RQ3).** Score genuine, concatenated, negated and off-topic answers with RePASs, and compare with human faithfulness ratings.

## 3. Corpus

- **Harvest:** 381 of 381 listed Master Directions, 76,188 paragraphs. P1-004 recovered 81 Directions missed by an earlier harvest; every later artefact uses the full set. (Source: `reports/results_v2.json` → `tables.01_corpus`.)
- **Segmentation and IDs:** paragraphs carry stable ids (`md_NNNNN::pNNNNN`) and clause paths; T1 items are `t1_<paragraph id>`.
- **Entity classes:** 19 headings from RBI's listing: 11 regulated-entity classes and 8 RBI function headings.
- **Subject families:** 57, derived from titles; 305 Directions have one.
- **Matrix:** 1,083 entity class × subject family cells, 296 populated, 9 ambiguous.
- **Known defects:** D2, 3 Directions have empty titles and no subject family.
- **Amended-text-only limitation:** 162 titles carry an "Updated as on" stamp. RBI consolidates amendments in place, so the corpus holds only current text: the system can flag a later amendment but cannot show the pre-amendment wording.

## 4. Supplementary sources (P2-003)

- **FAQ:** 80 pages, 1,845 items.
- **Enforcement releases:** 463 releases; entity class resolved for 455.
- **Amendment Directions:** 333 pages. Withdrawn circulars and the repeal map feed T3.
- **Alignment, faq:** 5/30 clean = 0.167 (Wilson 95% [0.073, 0.336]). Decision under the locked rule: `validation_or_motivation_only`.
- **Alignment, enforcement:** 16/30 clean = 0.533 (Wilson 95% [0.361, 0.698]). Decision under the locked rule: `direction_level_weak_label_only`.

FAQ text is used only for validation and motivation; enforcement only as Direction-level weak labels.

## 5. T1 benchmark construction

- **Candidate extraction (P2-001):** rules v4 keep 28,694 candidates out of 33,507 paragraphs with a deontic cue.
- **Precision by rule version:**
| Rules | n | true | precision [Wilson 95%] |
|---|---|---|---|
| v1 | 40 | 27 | 0.675 [0.520, 0.799] |
| v2 | 40 | 31 | 0.775 [0.625, 0.877] |
| v3 | 40 | 34 | 0.850 [0.709, 0.929] |
| v4 | 28 | 26 | 0.929 [0.774, 0.980] |

(Source: `tables.02_candidates.precision_rounds`.)

- **Cross-class matching (P2-002):** bge-base-en-v1.5 plus lexical similarity, with threshold 0.757567. Counterpart rate on the validation pairs: 53/60 = 0.883 (Wilson 95% [0.778, 0.942]).
- **Sampling (P2-004):** 123 candidates, seeded and stratified by source class, with at most four compared classes per item.
- **Validated set:** 106 validated and 17 rejected as not an obligation; the rejection rate is 17/123 = 0.138 (Wilson 95% [0.088, 0.210]).
- **Routes:** adjudicated 38, retest-consistent 6, single-pass 62.
- **Flags:** shared 52, class-specific 40, absent 14.
- **Judgements:** same 213, different 78, none 121.
- **Guidelines v3:** one item row plus one row per compared class; `not_obligation` for spans that impose no duty on a regulated entity; `same` = the same obligation in substance; `different` = same topic but a different requirement; `none` = no counterpart among the paragraphs checked. The flag is derived (any `different` → class-specific; otherwise any `same` → shared; all `none` → absent).

## 6. Annotation and reliability

- **The gold is single-expert.** One annotator (`rater_1`) labelled every T1 item; adjudication was by the same annotator. No gold item has an independent second-rater label.
- **Inter-rater agreement on a separate sample (not part of the gold).** Thirty items drawn outside the T1 sample were labelled independently by three raters (`rater_1`–`rater_3`) before adjudication:
  - Fleiss κ, class-row judgement: 0.774 [0.645, 0.886] (n = 20 items, 80 units);
  - Fleiss κ, differential flag: 0.571 [0.289, 0.807] (n = 20 items, 20 units);
  - Fleiss κ, not-obligation: 0.392 [-0.015, 0.689] (n = 30 items, 30 units).
- **Blind test–retest (`rater_1`, 25 items; supplementary).** The actual gap between the passes was 11.7–18.6 h (file-level bounds; per-item times were not logged), so recall may inflate agreement:
  - Cohen's κ, flag: 0.426 [0.091, 0.730] (n = 20 items, 20 units);
  - Cohen's κ, class-row judgement: 0.550 [0.333, 0.752] (n = 20 items, 78 units).
- **Timed blind re-label (evidence only).** Twenty single-pass items: flag κ 0.409 [0.042, 0.759] (n = 19 items, 19 units); class-row κ 0.684 [0.506, 0.872] (n = 19 items, 72 units).
- **Candidates shown on the sheets.** Every sheet showed the same two P2-002 candidate paragraphs per compared class (bge-base-en-v1.5 top-1 and top-2), in random order and with no scores. This may bias judgements toward the P2-002 candidates; the same bias is disclosed for T2.
- **An earlier team review.** An earlier team review of thirty overlap items was revised after an AI reviewer's file-level feedback. It was recorded as not independent, never used for agreement, and used only as one input when `rater_1` adjudicated a subset of gold items.

## 7. T2, T3 and T4 construction

- **T2 `t2_xclass_t1`** (n = 291). Bias: Raters were shown the bge-base-en-v1.5 top-1/top-2 P2-002 candidates for each compared class (they could look up any paragraph), so the labelled counterparts favour the dense retriever.
- **T2 `t2_xclass_p2002`** (n = 53). Bias: Pairs were drawn by bge-base-en-v1.5 semantic-score bands (the same model and revision as the dense system), so the relevant paragraphs favour the dense retriever.
- **T2 `t2_supp_p2003`** (n = 25). Bias: Candidates shown to the rater were ranked by TF-IDF, which favours BM25 (the rater could enter any paragraph id of the Direction).
- **T3:** 60 items built from Amendment Directions and update stamps, 52 scored.
  - Parse spot-checks: 15/20 = 0.750 (Wilson 95% [0.531, 0.888]) for rules v1; independent post-fix check 8/10 = 0.800 (Wilson 95% [0.490, 0.943]).
  - Known parser defect: a merged change's recorded old words include the previous change's new words.
  - **Circularity:** the gold and the temporal filter come from the same deterministic parser.
- **T4:** 30 questions × four answer types (genuine, concatenated, negated, off-topic).
  - Human `faithful` / `answers_question` ratings on thirty answers, blind, by one rater; 2 questions were flagged as bad questions (sensitivity analysis).
  - Questions and genuine answers were drafted by an LLM (gpt-oss-120b via Groq).

## 8. Systems

- **Retrieval:** BM25 (bm25s), dense (bge-base-en-v1.5), hybrid reciprocal rank fusion, and a class-aware hybrid that restricts candidates to the target class's Directions.
- **T1 judgement systems:**
  - class-blind LLM;
  - class-aware LLM;
  - final agentic (class filter plus an NLI verifier that retries or abstains);
  - class-blind + verifier (ablation A);
  - long-context LLM (all Directions of the compared classes, 100K-token cap);
  - majority (in-sample) and the P2-002 candidate labels as baselines.
- **LLM settings:** gemini-3.5-flash-lite for every P4 system and the comparator; temperature 0; thinking {'thinkingLevel': 'minimal'}; JSON mode; frozen prompts (sha256 in config). NLI verifier: cross-encoder/nli-deberta-v3-xsmall at a pinned revision.
- **Pairwise structured comparator (the targeted experiment):**
  - one call per (item, compared class) over the two shown candidate paragraphs;
  - the model extracts thirteen fields (actor, action, object, scope, condition, threshold, amount, percentage, frequency, deadline, exception, documentation, reporting) from both sides and compares them field by field;
  - a fixed rule decides `same` / `different` / `none` (precedence same > different > none); the model never gives the verdict;
  - prompt and rule frozen before any T1 run (system prompt `51f7ea78ed4b…`, rule `83664f8d9d8f…`);
  - development set: the separate 30-item set (not the gold), with one revision for a field-extraction bug.

## 9. Results

CIs are 95% percentile bootstrap intervals over item resamples, labelled by `src/eval/ci_format.py`.

### 9.1 T2 — counterpart retrieval (nDCG@10)

| System | t2_xclass_t1 | t2_xclass_p2002 | t2_supp_p2003 |
|---|---|---|---|
| BM25 | 0.458 [0.424, 0.492] | 0.277 [0.194, 0.369] | 0.616 [0.462, 0.761] |
| Dense | 0.421 [0.385, 0.455] | 0.334 [0.252, 0.428] | 0.362 [0.212, 0.528] |
| Hybrid RRF | 0.443 [0.408, 0.478] | 0.319 [0.234, 0.414] | 0.504 [0.348, 0.673] |
| Hybrid − source class | 0.464 [0.429, 0.497] | 0.337 [0.256, 0.429] | 0.504 [0.348, 0.673] |
| Class-aware hybrid | 0.894 [0.864, 0.922] | 0.741 [0.630, 0.844] | 0.675 [0.535, 0.811] |

(Source: `tables.06_t2_retrieval.p3001`.) Class filter, pipeline retrieval stage (ON − OFF): t2_xclass_t1 +0.451 [+0.421, +0.481] (excludes 0 (above)); t2_xclass_p2002 +0.423 [+0.336, +0.514] (excludes 0 (above)); t2_supp_p2003 +0.171 [+0.072, +0.273] (excludes 0 (above)).

### 9.2 T1 — main table (gold: 106 items)

| System | n | 3-way flag F1 | Collapsed F1 | Judgement macro-F1 | `different` F1 | Coverage |
|---|---|---|---|---|---|---|
| Majority (in-sample) | 106 | 0.219 [0.186, 0.246] | 0.465 [0.445, 0.483] | 0.227 [0.202, 0.248] | 0.000 | 1.000 [1.000, 1.000] |
| P2-002 candidates | 106 | 0.459 [0.381, 0.520] | 0.784 [0.671, 0.877] | 0.550 [0.512, 0.583] | 0.000 | 1.000 [1.000, 1.000] |
| Class-blind LLM | 106 | 0.602 [0.497, 0.700] | 0.766 [0.647, 0.873] | 0.664 [0.597, 0.726] | 0.321 | 1.000 [1.000, 1.000] |
| Class-aware LLM | 106 | 0.551 [0.445, 0.639] | 0.808 [0.685, 0.908] | 0.609 [0.553, 0.667] | 0.154 | 0.991 [0.972, 1.000] |
| Final agentic (class filter + verifier) | 106 | 0.483 [0.385, 0.568] | 0.710 [0.590, 0.815] | 0.521 [0.470, 0.570] | 0.047 | 0.774 [0.689, 0.849] |
| Class-blind + verifier | 106 | 0.532 [0.431, 0.625] | 0.695 [0.572, 0.802] | 0.578 [0.520, 0.639] | 0.176 | 0.792 [0.708, 0.868] |
| Long-context LLM (100K cap) | 102 | 0.509 [0.408, 0.600] | 0.819 [0.691, 0.917] | 0.551 [0.496, 0.604] | 0.074 | 1.000 [1.000, 1.000] |
| Structured comparator | 106 | 0.616 [0.512, 0.702] * | 0.838 [0.720, 0.926] * | 0.680 [0.622, 0.732] | 0.409 | 1.000 [1.000, 1.000] |

(Source: `phase4.t1_systems`, `phase4.t1_different`, `phase4.comparator`; the harness reproduces the published v1 table exactly.) * The comparator's flag is derived from its judgements with the v3.6 rule; its judgement metrics are the pre-registered ones.

### 9.3 Paired differences (same items)

| Comparison | n | Δ 3-way F1 | Δ collapsed F1 | Δ coverage |
|---|---|---|---|---|
| Ablation A (verifier on): final agentic − class-blind + verifier | 106 | -0.049 [-0.133, +0.036] (does not exclude 0) | +0.015 [-0.059, +0.082] (does not exclude 0) | -0.019 [-0.075, +0.038] (does not exclude 0) |
| Class filter, no verifier: class-aware − class-blind | 106 | -0.050 [-0.133, +0.027] (does not exclude 0) | +0.043 [-0.030, +0.109] (does not exclude 0) | -0.009 [-0.028, +0.0000] (does not exclude 0) |
| Ablation C on T1: final agentic − class-aware | 106 | -0.068 [-0.132, -0.012] (excludes 0 (below)) | -0.099 [-0.151, -0.053] (excludes 0 (below)) | -0.217 [-0.292, -0.142] (excludes 0 (below)) |
| Verifier, class-blind: ablation A − class-blind | 106 | -0.069 [-0.129, -0.014] (excludes 0 (below)) | -0.071 [-0.105, -0.041] (excludes 0 (below)) | -0.208 [-0.292, -0.132] (excludes 0 (below)) |
| Class-blind LLM − P2-002 candidates | 106 | +0.143 [+0.054, +0.232] (excludes 0 (above)) | -0.019 [-0.114, +0.072] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Class-aware LLM − P2-002 candidates | 106 | +0.092 [-0.002, +0.183] (does not exclude 0) | +0.024 [-0.096, +0.135] (does not exclude 0) | -0.009 [-0.028, +0.0000] (does not exclude 0) |
| Final agentic − P2-002 candidates | 106 | +0.024 [-0.058, +0.106] (does not exclude 0) | -0.074 [-0.192, +0.036] (does not exclude 0) | -0.226 [-0.311, -0.151] (excludes 0 (below)) |
| Class-blind + verifier − P2-002 candidates | 106 | +0.073 [-0.006, +0.157] (does not exclude 0) | -0.089 [-0.186, +0.006] (does not exclude 0) | -0.208 [-0.292, -0.132] (excludes 0 (below)) |
| Long-context − majority (same items) | 102 | +0.290 [+0.188, +0.376] (excludes 0 (above)) | +0.353 [+0.212, +0.454] (excludes 0 (above)) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context − P2-002 candidates (same items) | 102 | +0.057 [-0.044, +0.163] (does not exclude 0) | +0.045 [-0.093, +0.176] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context − class-blind (same items) | 102 | -0.097 [-0.197, +0.010] (does not exclude 0) | +0.054 [-0.047, +0.159] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context − class-aware (same items) | 102 | -0.035 [-0.128, +0.063] (does not exclude 0) | +0.023 [-0.088, +0.142] (does not exclude 0) | +0.010 [+0.0000, +0.039] (does not exclude 0) |
| Long-context − final agentic (same items) | 102 | +0.030 [-0.067, +0.129] (does not exclude 0) | +0.126 [+0.016, +0.240] (excludes 0 (above)) | +0.235 [+0.157, +0.324] (excludes 0 (above)) |
| Long-context − class-blind + verifier (same items) | 102 | -0.020 [-0.131, +0.094] (does not exclude 0) | +0.127 [+0.018, +0.234] (excludes 0 (above)) | +0.216 [+0.137, +0.294] (excludes 0 (above)) |

(Source: `phase4.t1_paired`.)

**Pre-registered comparator comparisons (amendment 3):**

| Comparison | n items | Δ judgement macro-F1 | Δ `different` F1 | Δ `different` recall | Δ collapsed flag F1 |
|---|---|---|---|---|---|
| comparator − class_aware | 106 | +0.071 [+0.001, +0.142] (excludes 0 (above)) | +0.255 [+0.094, +0.411] (excludes 0 (above)) | +0.397 [+0.250, +0.543] (excludes 0 (above)) | +0.030 [-0.061, +0.128] (does not exclude 0) |
| comparator − p2002_candidates | 106 | +0.130 [+0.067, +0.191] (excludes 0 (above)) | +0.409 [+0.282, +0.530] (excludes 0 (above)) | +0.487 [+0.338, +0.632] (excludes 0 (above)) | +0.054 [-0.057, +0.168] (does not exclude 0) |

(Source: `phase4.preregistered_comparisons`.)

### 9.4 Long-context and the verifier

- **Long-context:** at the uniform 100K cap, 102 of 106 items were answered. On the same items, long-context − final agentic: 3-way +0.030 [-0.067, +0.129] (does not exclude 0), collapsed +0.126 [+0.016, +0.240] (excludes 0 (above)).
  - The 150K-cap run is superseded (it stopped during an API outage) and appears only in the release appendix.
- **Verifier (ablation C on T1):** final agentic − class-aware: 3-way -0.068 [-0.132, -0.012] (excludes 0 (below)), coverage -0.217 [-0.292, -0.142] (excludes 0 (below)).
  - Class-blind side: -0.069 [-0.129, -0.014] (excludes 0 (below)).

### 9.5 T3 and ablation B

- **Filter on:** status exact match 1.000 [1.000, 1.000]. This is **circular by construction**: the gold and the filter come from the same parser.
- **Filter off:** 0.538 [0.404, 0.673]; the model answered "in force, original" on 48 of 52 items.
- **Ablation B (ON − OFF):** +0.462 [+0.327, +0.596] (excludes 0 (above)).

### 9.6 T4 — RePASs audit

| Answer type | RePASs composite (mean [95% CI]) |
|---|---|
| genuine | 0.371 [0.311, 0.431] |
| concatenated | 0.746 [0.692, 0.796] |
| adv_negated | 0.049 [0.022, 0.082] |
| adv_offtopic | 0.229 [0.198, 0.257] |

- concatenated − genuine: +0.375 [+0.325, +0.427] (excludes 0 (above)); pre-registered verdict: reproduces.
- adv_negated − genuine: -0.322 [-0.390, -0.243] (excludes 0 (below)); pre-registered verdict: does not reproduce.
- adv_offtopic − genuine: -0.141 [-0.206, -0.080] (excludes 0 (below)); pre-registered verdict: does not reproduce.
- RePASs vs human `faithful`: Spearman ρ 0.731 [0.535, 0.845]; vs `answers_question`: ρ 0.008 [-0.323, 0.339].
- **Exploratory repair:** it ranks genuine above concatenated (+0.208 [+0.168, +0.253] (excludes 0 (above))), but it no longer tracks human faithfulness (ρ -0.126 [-0.477, 0.216]). It is **not usable** as it stands.

### 9.7 Ablations A–C

| Ablation | Toggle | Measure | n | ON − OFF |
|---|---|---|---|---|
| A | class filter | T1 3-way flag Macro-F1 | 106 | -0.049 [-0.133, +0.036] (does not exclude 0) |
| A | class filter | T1 collapsed Macro-F1 | 106 | +0.015 [-0.059, +0.082] (does not exclude 0) |
| A | class filter | T2 nDCG@10, t2_xclass_t1 | 291 | +0.451 [+0.421, +0.481] (excludes 0 (above)) |
| A | class filter | T2 nDCG@10, t2_xclass_p2002 | 53 | +0.423 [+0.336, +0.514] (excludes 0 (above)) |
| A | class filter | T2 nDCG@10, t2_supp_p2003 | 25 | +0.171 [+0.072, +0.273] (excludes 0 (above)) |
| B | temporal filter | T3 status exact match | 52 | +0.462 [+0.327, +0.596] (excludes 0 (above)) |
| B | temporal filter | T3 supersession F1 | 52 | +1.000 [+1.000, +1.000] (excludes 0 (above)) |
| C | verifier | T1 3-way flag Macro-F1 | 106 | -0.068 [-0.132, -0.012] (excludes 0 (below)) |
| C | verifier | T1 coverage | 106 | -0.217 [-0.292, -0.142] (excludes 0 (below)) |
| C | verifier | T4 unsupported-sentence rate (NLI proxy), all 28 | 28 | -0.382 [-0.552, -0.214] (excludes 0 (below)) |
| C | verifier | T4 abstention rate | 28 | +0.393 [+0.214, +0.571] (excludes 0 (above)) |
| C | verifier | T4 RePASs composite | 28 | -0.055 [-0.121, +0.015] (does not exclude 0) |
| C | verifier | T4 unsupported-sentence rate, answered only (ON is 0 by construction) | 17 | -0.129 [-0.300, +0.0000] (does not exclude 0) |
| C | verifier | T4 RePASs composite, answered only | 17 | +0.040 [+0.0000, +0.113] (does not exclude 0) |

(Source: `tables.10_ablations.rows`.)

### 9.8 The `different` failure

- Gold `different` class units: 78.
- **Definition A** (all five LLM systems answered the item, and none said `different`): 56 missed by all.
- **Definition B** (only the systems that answered are counted, including items long-context never answered): 58.
- The comparator gets 26 of the definition-A units and 26 of the definition-B units right.

**Retrieval vs reasoning.** An error is a retrieval failure if the gold matched paragraph was not in that system's context, and a reasoning failure if it was.

| System | Errors | Retrieval | Reasoning | → same | → none |
|---|---|---|---|---|---|
| class_blind | 60/78 | 30 | 30 | 18 | 42 |
| class_aware | 71/78 | 12 | 59 | 32 | 39 |
| final_agentic | 76/78 | 12 | 64 | 13 | 44 |
| ablation_a | 70/78 | 30 | 40 | 8 | 41 |
| long_context | 73/78 | 4 | 69 | 43 | 30 |
| comparator | 40/78 | 0 | 40 | 6 | 32 |

(Source: `phase4.retrieval_vs_reasoning`.) The human error-category pass was not done, so no category breakdown is reported.

### 9.9 Comparator: development evidence and T1 result

- **Development set** (the separate 30-item set, 92 class units; development evidence only): judgement macro-F1 0.635, `different` F1 0.348.
- **T1 gold:** 412 class units; `different` recall 0.487, precision 0.352; different→same 6, different→none 32.

## 10. Discussion

Six findings, stated as findings rather than as a claim that our agent wins:

1. **Class-aware filtering improves retrieval.** On T2 the class filter raises nDCG@10 by a wide margin, partly by construction because relevance covers only the target-class counterpart.
2. **It doesn't translate into better T1 judgement.** On T1 the class filter has no significant effect, and no LLM system beats the embedding-based P2-002 candidates on collapsed flag F1. Finding the counterpart is not the hard part.
3. **`different` is the core failure mode.** Most gold `different` units are missed by every LLM system. In most errors the gold paragraph was in context, so these are reasoning failures, not retrieval failures.
4. **The verifier hurts T1.** It lowers 3-way flag F1 and coverage, because it abstains on many correct first answers. Its whole-paragraph NLI premise is a poor test for a one-sentence rationale.
5. **Long-context is competitive.** Without retrieval it ties the retrieval systems on 3-way F1 and beats both verifier systems on collapsed F1. On T1, where the relevant Directions fit in a 100K prompt, retrieval was not the bottleneck.
6. **RePASs concatenation gameability reproduces** on RBI text. Negated and off-topic answers do not fool it, and RePASs does not track whether an answer addresses the question.

The structured comparator tests whether making the comparison explicit field by field helps on `different`. Its result is reported in §9.3 and §9.9, against the pre-registered comparisons.

## 11. Limitations

- **Size:** 106 validated T1 items; source classes have between 7 and 15 items each, so per-class results have wide intervals.
- **Single-expert gold:** reliability is measured on a separate sample, not on the gold itself.
- **Short-interval retest:** 11.7–18.6 h, so recall may inflate agreement.
- **T2 construction bias:** each relevance set favours one retriever; relevance covers only the target-class counterpart.
- **T3:** circularity, and the old-words parser defect.
- **Historical text:** the corpus holds only amended text.
- **T4:** small, with LLM-drafted questions and one rater.
- **The RePASs repair** is exploratory and not usable.
- **Models:** Flash-Lite-class models only, on free tiers.
- **Scope Ladder cuts** (all seven applied):
  1. IndiaFinBench zero-shot transfer not run;
  2. no cross-encoder reranking and no LangGraph (plain Python orchestration);
  3. ObliQA / ObliQA-MP as related-work positioning only;
  4. FAQ / enforcement hand-alignment reduced to the minimum samples;
  5. T4 reduced to the smallest n with a usable CI;
  6. T3 restricted to deterministic cases from Amendment Directions and update stamps;
  7. release limited to benchmark + code + dataset card, with no UI.

## 12. Future Work (ranked)

| Rank | Item | What | Why it matters | Rough effort |
|---|---|---|---|---|
| 1 | Test–retest with a proper gap | Re-label a stratified retest subset after a washout of days, not hours. | The existing retest gap was short, so recall may inflate agreement. | Low: one annotator, a few hours. |
| 2 | Second raters on all gold items | Independent second (and third) ratings on every gold item, with adjudication. | The gold is single-expert; inter-rater agreement is so far measured only on a separate sample. | High: several annotator-days per rater. |
| 3 | Cross-encoder reranking | Rerank retrieved paragraphs with a cross-encoder before judgement. | Tests whether better candidate ordering helps T2 and the T1 judgement. | Medium: a pinned model and one evaluation run. |
| 4 | A stronger (frontier) LLM run | Rerun the T1 systems and the comparator with a frontier model. | All results use Flash-Lite-class models; the `different` failure may shrink with a stronger model. | Medium: paid API budget. |
| 5 | An ObliQA baseline | Run the retrieval baselines on ObliQA as an external reference point. | Positions RBI-ObliBench against an existing regulatory QA benchmark. | Low–medium: data licence and an evaluation script. |
| 6 | A broad T3 | Extend T3 beyond cases derivable from Amendment Directions and update stamps. | The current T3 is small and its gold shares a parser with the temporal filter (circular). | High: manual temporal annotation. |
| 7 | A bigger T4 study with two raters | More questions, and at least two blind raters per answer. | T4 has thirty questions and one rater. | Medium: rating time plus question drafting. |
| 8 | IndiaFinBench | Zero-shot transfer evaluation on IndiaFinBench. | Tests generalisation to SEBI/RBI QA. | Low–medium: data access and an adapter. |
| 9 | A LangGraph port | Port the plain-Python orchestration to LangGraph. | Engineering parity with common agent stacks; no new science. | Medium: dependency compatibility work. |
| 10 | Full FAQ/enforcement sources | Use FAQ and enforcement text beyond the alignment samples. | The alignment rates restricted these sources to validation and weak labels. | High: alignment and cleaning. |
| 11 | A UI | A demo interface over the pipeline. | Usability for compliance staff; outside the research questions. | Medium. |

## 13. Reproducibility and release

- **Pointer-only release:** every item carries a pointer (Direction id, paragraph id, character offsets, source URL, harvest date, sha256 of the paragraph text). `rehydrate.py` rebuilds the text from RBI's own URLs and checks the hashes.
- **Release check:** it fails on any excluded path, key-like string, oversized file, or run of thirty or more words copied from the corpus.
- **Licences:** MIT for the code; CC BY 4.0 for the annotations and derived metadata. RBI documents are "All Rights Reserved" and are not included. Third-party: bge-base-en-v1.5 MIT; nli-deberta-v3-xsmall Apache-2.0; bm25s MIT; deberta-large-mnli MIT; legal-bert-base-uncased CC BY-SA 4.0; RePASs has no licence file (used unmodified, not redistributed).
- **Archive:** Zenodo DOI to be assigned (placeholder until deposit).
- **Commands:** in the README (one command per table; tests; release check).

## 14. AI-use statement

- **Code generation:** Claude Code (Anthropic) wrote the repository code (scraper, preprocessing, candidate extraction, matching, benchmark tooling, evaluation and statistics scripts) under the authors' direction.
- **Analysis:** Claude Code wrote and ran the analysis and bootstrap scripts; the authors reviewed the outputs.
- **Internal reports:** Claude Code drafted the internal phase reports and this record.
- **LLM systems under study (system outputs, never labels):** gemini-3.5-flash-lite (P4 systems, long-context, comparator); gpt-oss-120b via Groq (T4 question drafting and genuine answers).
- **Human labels:** every human label is manual. The early team-review file set described in §6 was revised after AI-reviewer file-level feedback; it was recorded as not independent and never used for agreement.
- **Provider terms:** under the Gemini API free tier, outputs may be published and were not used to train any model; free-tier inputs may be used by Google, including human review. Our prompts contained only public RBI text and no personal data. Groq terms: https://groq.com/terms-of-use.

## 15. References

- [gokhan2024regnlp] Tuba Gokhan and Kexin Wang and Iryna Gurevych and Ted Briscoe. *RIRAG: Regulatory Information Retrieval and Answer Generation*. 2024. doi:10.48550/arXiv.2409.05677.
- [repass] RegNLP. *RePASs: Regulatory Passage Answer Stability Score*. urlhttps://github.com/RegNLP/RePASs. 2024.
- [gokhan2025riragtask] Tuba Gokhan and Kexin Wang and Iryna Gurevych and Ted Briscoe. *Shared Task RIRAG-2025: Regulatory Information Retrieval and Answer Generation*. Proceedings of the 1st Regulatory NLP Workshop (RegNLP 2025). 2025. https://aclanthology.org/2025.regnlp-1.1/.
- [obliqamp] Tuba Gokhan and Ted Briscoe. *Grounded Answers from Multi-Passage Regulations: Learning-to-Rank for Regulatory RAG*. Proceedings of the Natural Legal Language Processing Workshop 2025. 2025. doi:10.18653/v1/2025.nllp-1.10.
- [aueb2025rirag] Ioannis Chasandras and Odysseas S. Chlapanis and Ion Androutsopoulos. *AUEB-Archimedes at RIRAG-2025: Is Obligation Concatenation Really All You Need?*. Proceedings of the 1st Regulatory NLP Workshop (RegNLP 2025). 2025. https://aclanthology.org/2025.regnlp-1.8/.
- [indiafinbench] Rajveer Singh Pall. *IndiaFinBench: An Evaluation Benchmark for Large Language Model Performance on Indian Financial Regulatory Text*. 2026. arXiv:2604.19298.
- [bge] Shitao Xiao and Zheng Liu and Peitian Zhang and Niklas Muennighoff and Defu Lian and Jian-Yun Nie. *C-Pack: Packed Resources For General Chinese Embeddings*. Proceedings of the 47th International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '24). 2024.
- [nlideberta] Sentence-Transformers. *cross-encoder/nli-deberta-v3-xsmall*. urlhttps://huggingface.co/cross-encoder/nli-deberta-v3-xsmall. 2023.
- [debertav3] Pengcheng He and Jianfeng Gao and Weizhu Chen. *DeBERTaV3: Improving DeBERTa using ELECTRA-Style Pre-Training with Gradient-Disentangled Embedding Sharing*. International Conference on Learning Representations (ICLR). 2023.
- [sbert] Nils Reimers and Iryna Gurevych. *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks*. Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing (EMNLP-IJCNLP). 2019.
- [bm25s] Xing Han L`u. *BM25S: Orders of Magnitude Faster Lexical Search via Eager Sparse Scoring*. 2024. arXiv:2407.03618.
- [rrf] Gordon V. Cormack and Charles L. A. Clarke and Stefan B"uttcher. *Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods*. Proceedings of the 32nd International ACM SIGIR Conference on Research and Development in Information Retrieval. 2009. doi:10.1145/1571941.1572114.
- [gemini35fl] Google DeepMind. *Gemini 3.5 Flash-Lite Model Card*. urlhttps://deepmind.google/models/model-cards/gemini-3-5-flash-lite/. 2026.
- [gptoss] OpenAI. *gpt-oss-120b & gpt-oss-20b Model Card*. 2025. arXiv:2508.10925.
- [fleiss1971] Joseph L. Fleiss. *Measuring Nominal Scale Agreement Among Many Raters*. Psychological Bulletin. 1971.
- [cohen1960] Jacob Cohen. *A Coefficient of Agreement for Nominal Scales*. Educational and Psychological Measurement. 1960.
- [efron1979] Bradley Efron. *Bootstrap Methods: Another Look at the Jackknife*. The Annals of Statistics. 1979.
- [wilson1927] Edwin B. Wilson. *Probable Inference, the Law of Succession, and Statistical Inference*. Journal of the American Statistical Association. 1927.
- [rbi] Reserve Bank of India. *Master Directions*. urlhttps://www.rbi.org.in. 2026.
- [legalbert] Ilias Chalkidis and Manos Fergadiotis and Prodromos Malakasiotis and Nikolaos Aletras and Ion Androutsopoulos. *LEGAL-BERT: The Muppets straight out of Law School*. Findings of the Association for Computational Linguistics: EMNLP 2020. 2020. doi:10.18653/v1/2020.findings-emnlp.261.

## Appendix A. Project timeline

| Phase | Outcome |
|---|---|
| Phase 0 | Repository audit and plan (`reports/phase0_audit.md`). |
| Phase 1 | Corpus QA, metadata normalisation and the entity class × subject family matrix, annotation protocol, three-rater pilot (`reports/phase1_*`). |
| P1-004 | Corpus repair to the full Direction set; pilot validation. |
| P2-001 | Obligation candidate extraction, with four precision rounds. |
| P2-002 | Cross-class matching and the threshold decision. |
| P2-003 | Supplementary sources (FAQ, enforcement, amendments) and the locked alignment decisions. |
| P2-004 | T1 sample, single-expert labelling, retest, the separate 30-item three-rater set, adjudication, gold v1. |
| P3-001 | LLM client, T2 relevance sets, retrieval and T1 baselines. |
| P3-002 | T4 RePASs audit and the exploratory repair. |
| P4-001 | T3 set, class- and date-aware pipeline, system runs, ablations A–C, long-context at the 100K cap. |
| P5-001 Part A | Results consolidation, report draft, dataset card, pointer-only release, error analysis. |
| Final push | Verified references; venue preparation (AISIGH–SD 2026); comparator development and freeze; sealed predictions; comparator T1 run and Phase 4 scoring on gold v1; this master document and the paper draft. |
