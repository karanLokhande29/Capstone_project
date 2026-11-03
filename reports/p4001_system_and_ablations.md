# P4-001 — Class- and date-aware agentic RAG: system runs and ablations A–C

All LLM systems use one model, **`gemini-3.5-flash-lite`** (version `3.5-flash-lite-07-2026`), free tier, temperature 0, JSON output, thinking `{'thinkingLevel': 'minimal'}`, no provider fallback. Prompts are frozen (sha256 in config `p4.prompt_sha256`). The verifier is `cross-encoder/nli-deberta-v3-xsmall` @ `a15087641532…`: a sentence is supported iff the argmax label (read from `id2label`) is entailment, with the cited paragraph(s) as premise. Bootstrap: 2,000 seeded resamples; every paired difference uses the same resampled indices.

## Summary

- The class filter improves T2 retrieval: nDCG@10 ON − OFF t2_xclass_t1 +0.451 [+0.421, +0.481] (excludes 0 (above)), t2_xclass_p2002 +0.423 [+0.336, +0.514] (excludes 0 (above)), t2_supp_p2003 +0.171 [+0.072, +0.273] (excludes 0 (above)). The gain is partly built in: relevance was labelled only for the target-class counterpart.
- The class filter shows no significant effect on T1 judgement: 3-way flag F1 -0.049 [-0.133, +0.036] (does not exclude 0) with the verifier on, -0.050 [-0.133, +0.027] (does not exclude 0) without it (n = 106).
- The verifier lowers T1 3-way flag F1 by -0.068 [-0.132, -0.012] (excludes 0 (below)) and coverage by -0.217 [-0.292, -0.142] (excludes 0 (below)) (n = 106).
- No LLM system significantly beats the P2-002 candidate labels on collapsed F1 (the fair comparison): Class-blind LLM − P2-002 -0.019 [-0.114, +0.072] (does not exclude 0); Class-aware LLM − P2-002 +0.024 [-0.096, +0.135] (does not exclude 0); Final agentic − P2-002 -0.074 [-0.192, +0.036] (does not exclude 0); Class-blind + verifier − P2-002 -0.089 [-0.186, +0.006] (does not exclude 0).
- The class-blind LLM has the highest 3-way flag F1 (0.602).
- Every LLM system is weak on 'different' judgements (F1 class-blind LLM 0.321 / class-aware LLM 0.154 / final agentic 0.047 / class-blind + verifier 0.176), so class-specific differences are the benchmark's hardest case.
- Long-context (100K cap, n = 102) is statistically tied with P2-002, class-blind and class-aware on both flag metrics (paired CIs: P2-002 3-way +0.057 [-0.044, +0.163] (does not exclude 0), collapsed +0.045 [-0.093, +0.176] (does not exclude 0); class-blind 3-way -0.097 [-0.197, +0.010] (does not exclude 0), collapsed +0.054 [-0.047, +0.159] (does not exclude 0); class-aware 3-way -0.035 [-0.128, +0.063] (does not exclude 0), collapsed +0.023 [-0.088, +0.142] (does not exclude 0)), matches final agentic on 3-way F1 (+0.030 [-0.067, +0.129] (does not exclude 0)), and beats final agentic (+0.126 [+0.016, +0.240] (excludes 0 (above))) and class-blind + verifier (+0.127 [+0.018, +0.234] (excludes 0 (above))) on collapsed F1. It is as weak as the other LLM systems on 'different' judgements (F1 0.074).

## Ablation table

| Ablation | Toggle | Measure | ON | OFF | ON − OFF [95% CI] | n |
|---|---|---|---|---|---|---|
| A | class filter | T1 3-way flag Macro-F1 | 0.483 [0.385, 0.568] | 0.532 [0.431, 0.625] | -0.049 [-0.133, +0.036] (does not exclude 0) | 106 |
| A | class filter | T1 collapsed Macro-F1 | 0.710 [0.590, 0.815] | 0.695 [0.572, 0.802] | +0.015 [-0.059, +0.082] (does not exclude 0) | 106 |
| A | class filter | T2 nDCG@10, t2_xclass_t1 | 0.894 [0.866, 0.923] | 0.443 [0.410, 0.478] | +0.451 [+0.421, +0.481] (excludes 0 (above)) | 291 |
| A | class filter | T2 nDCG@10, t2_xclass_p2002 | 0.741 [0.634, 0.848] | 0.319 [0.233, 0.411] | +0.423 [+0.336, +0.514] (excludes 0 (above)) | 53 |
| A | class filter | T2 nDCG@10, t2_supp_p2003 | 0.675 [0.527, 0.814] | 0.504 [0.349, 0.666] | +0.171 [+0.072, +0.273] (excludes 0 (above)) | 25 |
| B | temporal filter | T3 status exact match | 1.000 [1.000, 1.000] | 0.538 [0.404, 0.673] | +0.462 [+0.327, +0.596] (excludes 0 (above)) | 52 |
| B | temporal filter | T3 supersession F1 | 1.000 [1.000, 1.000] | 0.000 [0.0000, 0.0000] | +1.000 [+1.000, +1.000] (excludes 0 (above)) | 52 |
| C | verifier | T1 3-way flag Macro-F1 | 0.483 [0.385, 0.568] | 0.551 [0.445, 0.639] | -0.068 [-0.132, -0.012] (excludes 0 (below)) | 106 |
| C | verifier | T1 coverage | 0.774 [0.689, 0.849] | 0.991 [0.972, 1.000] | -0.217 [-0.292, -0.142] (excludes 0 (below)) | 106 |
| C | verifier | T4 unsupported-sentence rate (NLI proxy) (n=28) | 0.000 [0.0000, 0.0000] | 0.382 [0.214, 0.552] | -0.382 [-0.552, -0.214] (excludes 0 (below)) | 28 |
| C | verifier | T4 abstention rate (n=28) | 0.393 [0.214, 0.571] | 0.000 [0.0000, 0.0000] | +0.393 [+0.214, +0.571] (excludes 0 (above)) | 28 |
| C | verifier | T4 RePASs composite (n=28) | 0.296 [0.223, 0.376] | 0.350 [0.286, 0.412] | -0.055 [-0.121, +0.015] (does not exclude 0) | 28 |

## T1 (validated set, 106 items)

3-way flag Macro-F1 over gold shared / class-specific / absent (a predicted `ambiguous` is wrong); collapsed = absent vs present; judgement Macro-F1 over same / different / none (`unsure` is wrong); coverage = share not `ambiguous`. CIs resample items.

| System | n | 3-way flag Macro-F1 | Collapsed Macro-F1 | Judgement Macro-F1 | Judgement F1 same / different / none | Coverage | Predicted flags |
|---|---|---|---|---|---|---|---|
| Majority (in-sample) | 106 | 0.219 [0.186, 0.246] | 0.465 [0.445, 0.483] | 0.227 [0.202, 0.248] | 0.682 / 0.000 / 0.000 | 1.000 [1.000, 1.000] | {'shared': 106} |
| P2-002 candidates (dense within-family) | 106 | 0.459 [0.381, 0.520] | 0.784 [0.671, 0.877] | 0.550 [0.512, 0.583] | 0.841 / 0.000 / 0.809 | 1.000 [1.000, 1.000] | {'shared': 80, 'absent': 26} |
| Class-blind LLM | 106 | 0.602 [0.497, 0.700] | 0.766 [0.647, 0.873] | 0.664 [0.597, 0.726] | 0.884 / 0.321 / 0.786 | 1.000 [1.000, 1.000] | {'class-specific': 17, 'shared': 67, 'absent': 22} |
| Class-aware LLM | 106 | 0.551 [0.445, 0.639] | 0.808 [0.685, 0.908] | 0.609 [0.553, 0.667] | 0.887 / 0.154 / 0.785 | 0.991 [0.972, 1.000] | {'shared': 80, 'absent': 16, 'class-specific': 9, 'ambiguous': 1} |
| **Final agentic** | 106 | 0.483 [0.385, 0.568] | 0.710 [0.590, 0.815] | 0.521 [0.470, 0.570] | 0.745 / 0.047 / 0.773 | 0.774 [0.689, 0.849] | {'ambiguous': 24, 'shared': 57, 'absent': 18, 'class-specific': 7} |
| Class-blind + verifier (ablation A) | 106 | 0.532 [0.431, 0.625] | 0.695 [0.572, 0.802] | 0.578 [0.520, 0.639] | 0.763 / 0.176 / 0.796 | 0.792 [0.708, 0.868] | {'ambiguous': 22, 'shared': 54, 'absent': 22, 'class-specific': 8} |
| Long-context LLM | 102 | 0.509 [0.408, 0.600] | 0.819 [0.691, 0.917] | 0.551 [0.496, 0.604] | 0.838 / 0.074 / 0.741 | 1.000 [1.000, 1.000] | {'shared': 81, 'absent': 16, 'class-specific': 5} |

**Paired differences** (same items). The rows against P2-002 candidates: P2-002 cannot express shared vs class-specific (its flag is only absent or shared-or-class-specific, mapped to shared), so 3-way F1 favours the LLM systems by design; **collapsed F1 is the fair comparison**.

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

**Long-context baseline.** Uniform 100,000-token cap (D10). 102 of 106 items scored. 3-way flag Macro-F1 0.509 [0.408, 0.600]. Its paired differences against the other systems on the same items are in the table above.

**Every system on exactly the long-context scored items** (n = 102):

| System | 3-way flag Macro-F1 | Collapsed Macro-F1 | Coverage |
|---|---|---|---|
| Majority (in-sample) | 0.219 [0.188, 0.247] | 0.466 [0.446, 0.482] | 1.000 [1.000, 1.000] |
| P2-002 candidates (dense within-family) | 0.452 [0.371, 0.515] | 0.774 [0.658, 0.873] | 1.000 [1.000, 1.000] |
| Class-blind LLM | 0.606 [0.491, 0.700] | 0.765 [0.635, 0.868] | 1.000 [1.000, 1.000] |
| Class-aware LLM | 0.544 [0.431, 0.641] | 0.796 [0.658, 0.902] | 0.990 [0.961, 1.000] |
| **Final agentic** | 0.479 [0.377, 0.575] | 0.693 [0.559, 0.808] | 0.765 [0.676, 0.843] |
| Class-blind + verifier (ablation A) | 0.529 [0.421, 0.627] | 0.692 [0.556, 0.800] | 0.784 [0.706, 0.863] |
| Long-context LLM | 0.509 [0.408, 0.600] | 0.819 [0.691, 0.917] | 1.000 [1.000, 1.000] |

Prompt tokens (estimated as characters / 4, after the cap), scored vs unscored items: scored: n=102, median 71727, min 6451, max 100008; unscored: n=4, median 95910, min 27269, max 99863.

**503 policy (audit note 2).** Reported baseline: uniform 100,000-token cap for all 106 items, same proportional per-class truncation. Items whose prompt is under the cap send exactly the prompt of the earlier run and were served from the cache (identical prompt, no new call). Answered: 102/106; unscored: 4 (4%). Truncated at this cap: 33 of the scored items. Unscored items remain, so long-context is reported ONLY on the scored items, with the size distribution of scored vs unscored, and every system is compared on exactly those items (no further cap change, no model switch).

**Did the gold paragraphs survive truncation?** (diagnostic, no LLM calls; cap 100,000) Of 282 gold matched paragraphs in 89 scored items, 263 were in the prompt (93.3%). Long-context flag accuracy: 0.585 on the 82 items with every gold paragraph retained vs 0.143 on the 7 with at least one cut.
Item accounting: 102 scored = 82 (all gold kept) + 7 (at least one cut) + 13 with no gold matched paragraph (13: gold flag absent: every compared-class judgement is 'none', so there is no gold matched paragraph). The 'cut' group has n = 7, too small to support a conclusion.

**Real run time** (active time; the Mac's sleep excluded): long_context_cap100k (cap 100,000): active 0.0 min, wall 0.0 min; long_context_cap100k (cap 100,000): active 54.9 min, wall 54.9 min; long_context_cap100k (cap 100,000): active 6.7 min, wall 6.7 min; long_context_cap100k (cap 100,000): active 18.2 min, wall 18.2 min; long_context_cap100k (cap 100,000): active 27.0 min, wall 27.0 min; long_context_cap100k (cap 100,000): active 19.3 min, wall 19.3 min; lc150k_subset (13:23-14:01): awake 38.2 min of 38.2 wall; lc150k_remainder_run1 (14:23-16:08): awake 6.2 min of 104.3 wall; lc150k_remainder_run2 (16:10-20:12): awake 55.5 min of 242.0 wall.

**Verifier on T1 (pre-planned ablation C, reported as is).** Final agentic − class-aware: 3-way flag F1 -0.068 [-0.132, -0.012] (excludes 0 (below)), coverage -0.217 [-0.292, -0.142] (excludes 0 (below)) (n = 106). The verifier turned judgements into `unsure` (an abstention): final agentic has 86 `unsure` judgements against 1 for class-aware. No threshold or rule was changed.

**Post hoc diagnostics (no LLM calls; diagnostic only, they do not replace the frozen verifier):**

- (a) On the 82 items final agentic did not abstain on: final agentic flag accuracy 0.622, 3-way F1 0.535; class-aware on the same 82 items: accuracy 0.683, 3-way F1 0.616. (Class-aware on its own 105 non-abstained items: accuracy 0.619.) The verifier does **not** raise precision on what it keeps; point estimates only, no CI.
- (b) On the 262 stored first-pass same/different rationales: supported 171 (65.3%) with the whole cited paragraph as premise (the frozen rule) vs 153 (58.4%) with the paragraph's best single sentence (highest entailment probability; sentences split on . ; :). Premises over the NLI model's 512-token limit: 0. So a single-sentence premise would not have raised support: the Part A debug figure (15/27 vs 25/27 with a 3-sentence window, on 5 rejected items) does not carry over, and the premise rule is not the explanation for the abstentions.

Per-label flag F1 and confusion matrices are in `p4001_metrics_v1.json` (`t1.systems.<system>`).

## T2 (retrieval stage, no LLM)

The final pipeline's retrieval stage: hybrid RRF with the class filter (target class + function-heading Directions of the query's subject family), source excluded; T2 queries carry no as-of date, so the temporal filter is inactive. Same relevance sets, metrics and bias notes as P3-001; nDCG@10 [95% CI].

**Read this first (P3-001 framing).** Relevance was labelled only for the counterpart in the query's target class, so the task scored here is retrieval of the target-class counterpart, and class-blind systems are partly disadvantaged by construction: the class filter's gain is partly built in. `hybrid_minus_source_class` (the class-blind fusion with only the source class removed) is shown next to the result as the fairer class-blind comparison; the gap from it to the class filter is what knowing the target class adds for this task. This is not a general class-blind vs class-aware verdict.

| Set (bias) | n | Pipeline, class filter ON | OFF (ablation A) | P3-001 class_aware | P3-001 hybrid_minus_source_class | ON − OFF |
|---|---|---|---|---|---|---|
| t2_xclass_t1 (favours dense) | 291 | 0.894 [0.866, 0.923] | 0.443 [0.410, 0.478] | 0.894 | 0.464 | +0.451 [+0.421, +0.481] (excludes 0 (above)) |
| t2_xclass_p2002 (favours dense) | 53 | 0.741 [0.634, 0.848] | 0.319 [0.233, 0.411] | 0.741 | 0.337 | +0.423 [+0.336, +0.514] (excludes 0 (above)) |
| t2_supp_p2003 (favours BM25) | 25 | 0.675 [0.527, 0.814] | 0.504 [0.349, 0.666] | 0.675 | 0.504 | +0.171 [+0.072, +0.273] (excludes 0 (above)) |

## T3 (temporal: 60 items built, 52 scored after spot-check 2)

60 (paragraph, as-of date) items from 20 Directions, 30 before and 30 after the effective date, gold {'in_force_original': 30, 'amended': 21, 'deleted': 9}. Parser: 196 parsed actions from 988 amendment instructions (rules v2). Parse precision on Karan's 20-row spot-check: rules v1 15/20 (Wilson 0.53–0.89); after one rule fix (merged within-paragraph changes, per-item exception dates, 'dated' references ignored), the same 20 rows: 20/20 (Wilson 0.84–1.00), assessed against Karan's notes, not re-checked by a human. The target paragraph is pinned into the evidence (a deleted one stays, marked); the verifier does not apply to a status answer.

- **Human-measured parse precision (rules v1): 15/20 = 0.75, Wilson 95% [0.53, 0.89].**
- Post-fix, same rows the fix was designed on (in-sample): 20/20. This is Claude's reading of Karan's notes on the rows that motivated the fix, not an independent measurement.
- Independent post-fix check (10 seeded parses behind frozen items, none among the first 20): 8/10, Wilson 95% [0.49, 0.94]; 8 dependent items dropped (T3-005, T3-006, T3-015, T3-016, T3-051, T3-052, T3-059, T3-060) and T3 recomputed on the remaining 52. Display note: both parses marked wrong are 'adoption or 1 April 2026, whichever is earlier' amendments. The parser stores them as a window [publication date, 1 April 2026] (status unknown inside it); the sheet printed that as 'window: 2025-12-04 to 2026-04-01 (whichever earlier)', which the rater read as a claimed effective date of 4 December 2025. The dropped items' as-of dates lie outside the window (before publication / after 1 April 2026), so their gold would be the same under either reading; the human labels stand as recorded and the drop is kept (conservative).
- Of the 60 frozen items, 6 come from the 20 checked parses (3 parses: T3-003, T3-004, T3-025, T3-026, T3-057, T3-058); the other 54 rest on parses not in the first check.
- 14 items come from multi-change instructions affected by the known 'old words' defect (a merged change's recorded old words also include the previous change's new words; it can only exclude candidates as corpus-version 'unclear', never change an included item's gold): T3-017, T3-018, T3-019, T3-020, T3-025, T3-026, T3-027, T3-028, T3-035, T3-036, T3-045, T3-046, T3-057, T3-058.

| Temporal filter | n | Status exact match | Supersession F1 | Before-date EM | After-date EM | Predicted statuses |
|---|---|---|---|---|---|---|
| ON | 52 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 1.000 (n=26) | 1.000 (n=26) | {'in_force_original': 26, 'amended': 17, 'deleted': 9} |
| OFF | 52 | 0.538 [0.404, 0.673] | 0.000 [0.0000, 0.0000] | 0.962 (n=26) | 0.115 (n=26) | {'in_force_original': 48, 'deleted': 4} |

ON − OFF: status exact match +0.462 [+0.327, +0.596] (excludes 0 (above)); supersession F1 +1.000 [+1.000, +1.000] (excludes 0 (above)).

The supersession F1 CIs are degenerate ([1, 1] with the filter ON, [0, 0] OFF): on this set the outcomes are deterministic (ON names the governing amendment on every after-date item, {'tp': 26, 'fp': 0, 'fn': 0}; OFF never names one, {'tp': 0, 'fp': 0, 'fn': 26}), so every resample gives the same value.

**Sensitivity: without window-type effective dates** (6 of 52 items excluded: {'earlier_of_date_or_adoption': 6}; n = 46): status exact match ON 1.000 [1.000, 1.000] vs OFF 0.543 [0.391, 0.696], ON − OFF +0.457 [+0.304, +0.609] (excludes 0 (above)); supersession F1 ON 1.000 [1.000, 1.000] vs OFF 0.000 [0.0000, 0.0000], ON − OFF +1.000 [+1.000, +1.000] (excludes 0 (above)).

**Circularity.** The T3 gold comes from the same parser that the temporal filter uses, so no rule-only system is reported as a T3 result (it would be right by construction). T3 measures whether the LLM pipeline uses the date information it is given.

## T4 ablation C (verifier ON vs OFF, P3-002 questions)

Primary n = 28 (T4Q14 and T4Q30, flagged `bad_question` in P3-002, excluded); n = 30 also shown. `entity_class` = the question's source class; class filter on; no as-of date.

**How abstentions enter.** (a) Unsupported-sentence rate = unsupported delivered sentences / delivered sentences, pooled over questions. An abstained answer delivers no sentences, so it adds 0 to both the numerator and the denominator: it drops out of the rate, it is not counted as a supported answer. With the verifier on, every delivered sentence has passed the same NLI check that defines 'unsupported', so the ON rate is 0 by construction. (b) RePASs: an abstained answer is scored as its literal text ('cannot answer reliably') against the shown evidence, which RePASs scores low.

**Answered-only (lead figure):** on the 17 questions the verifier ON answered (not abstained, not declined), against the same questions with the verifier OFF: unsupported-sentence rate ON 0.000 [0.0000, 0.0000] vs OFF 0.129 [0.0000, 0.300], ON − OFF -0.129 [-0.300, +0.0000] (does not exclude 0) (ON is 0 by construction); RePASs ON 0.421 [0.337, 0.504] vs OFF 0.381 [0.303, 0.457], ON − OFF +0.040 [+0.0000, +0.113] (does not exclude 0). The headline unsupported-rate drop on all 28 questions below is mostly abstention plus the by-construction zero, not better answers.

| Measure | ON (n=28) | OFF (n=28) | ON − OFF (n=28) | ON − OFF (n=30) |
|---|---|---|---|---|
| Unsupported-sentence rate (NLI proxy) | 0.000 [0.0000, 0.0000] | 0.382 [0.214, 0.552] | -0.382 [-0.552, -0.214] (excludes 0 (below)) | -0.386 [-0.552, -0.219] (excludes 0 (below)) |
| Abstention rate | 0.393 [0.214, 0.571] | 0.000 [0.0000, 0.0000] | +0.393 [+0.214, +0.571] (excludes 0 (above)) | +0.400 [+0.233, +0.567] (excludes 0 (above)) |
| RePASs composite | 0.296 [0.223, 0.376] | 0.350 [0.286, 0.412] | -0.055 [-0.121, +0.015] (does not exclude 0) | -0.060 [-0.121, +0.010] (does not exclude 0) |

Verifier abstentions: 10 of 28; model declined to answer: ON 1, OFF 0; retried: 14.

**Say plainly:** the unsupported-sentence rate is an NLI proxy, not human judgement; and the verifier's NLI model is the same model RePASs uses for entailment and contradiction, so any RePASs gain from the verifier would partly be the same model agreeing with itself. Here RePASs did not rise: ON − OFF is shown above, with a CI that includes 0.

## Shared prompts (cache)

Two pairs reuse the same first prompt through the disk cache, at no extra quota: final agentic sends the class-aware LLM's first prompt, and ablation A sends the class-blind LLM's. At temperature 0 this is identical to re-calling and keeps the pairs exactly paired; only verifier retries cost new calls. Likewise T4 verifier ON sends OFF's first prompt. A retry whose re-retrieved top 5 equals the first attempt's is an identical prompt, so it returns the same answer from the cache.

## CLI demo transcripts

### An entity-class-specific query

```
$ python3 scripts/demo.py "What minimum share of the loan portfolio must consist of loans of up to Rs 25 lakh?" --class "Small Finance Banks"
Question: What minimum share of the loan portfolio must consist of loans of up to Rs 25 lakh?
Entity class: Small Finance Banks   As of: (not given)
Filters: class filter ON, temporal filter OFF, verifier ON

Answer: cannot answer reliably (a sentence was still unsupported after one retry).

Evidence (top 5 after filters):
  [md_13135::p00047] Reserve Bank of India (Small Finance Banks – Licensing) Guidelines, 2025 (md_13135; Small Finance Banks)
  [md_13120::p00052] Reserve Bank of India (Small Finance Banks – Concentration Risk Management) Directions, 2025 (Updated as on July 01, 2026) (md_13120; Small Finance Banks)
  [md_13135::p00048] Reserve Bank of India (Small Finance Banks – Licensing) Guidelines, 2025 (md_13135; Small Finance Banks)
  [md_13135::p00087] Reserve Bank of India (Small Finance Banks – Licensing) Guidelines, 2025 (md_13135; Small Finance Banks)
  [md_13124::p00222] Reserve Bank of India (Small Finance Banks – Credit Facilities) Directions, 2025 (Updated as on July 15, 2026) (md_13124; Small Finance Banks)

Verifier retries: 1. LLM calls: 2 new, 0 from cache. Model: gemini-3.5-flash-lite.
```

### A date-specific query

```
$ python3 scripts/demo.py "How often must the bank submit its Form B return, and on which day?" --class "Rural Co-operative Banks" --as-of 2025-12-01
Question: How often must the bank submit its Form B return, and on which day?
Entity class: Rural Co-operative Banks   As of: 2025-12-01
Filters: class filter ON, temporal filter ON, verifier ON

Answer:
  - Every Scheduled State Co-operative bank shall submit to the Reserve Bank a Return in Form B at the close of business on the last day of each fortnight. [md_13005::p00108]  [verifier: supported]
  - The Form B return must be submitted within five days after the date of the relevant fortnight to which it relates. [md_13005::p00108]  [verifier: supported]

Evidence (top 5 after filters):
  [md_13005::p00108] Reserve Bank of India (Rural Co-operative Banks – Cash Reserve Ratio and Statutory Liquidity Ratio) Directions, 2025 (Updated as on June 19, 2026) (md_13005; Rural Co-operative Banks)
      status: original in force; amended from 2025-12-15 by amendment amd_13228 (substitute (within paragraph))
  [md_13005::p00110] Reserve Bank of India (Rural Co-operative Banks – Cash Reserve Ratio and Statutory Liquidity Ratio) Directions, 2025 (Updated as on June 19, 2026) (md_13005; Rural Co-operative Banks)
      status: original in force; amended from 2025-12-15 by amendment amd_13228 (delete (within paragraph))
  [md_13005::p00117] Reserve Bank of India (Rural Co-operative Banks – Cash Reserve Ratio and Statutory Liquidity Ratio) Directions, 2025 (Updated as on June 19, 2026) (md_13005; Rural Co-operative Banks)
      status: original in force; amended from 2025-12-15 by amendment amd_13228 (substitute (within paragraph))
  [md_13005::p00107] Reserve Bank of India (Rural Co-operative Banks – Cash Reserve Ratio and Statutory Liquidity Ratio) Directions, 2025 (Updated as on June 19, 2026) (md_13005; Rural Co-operative Banks)
  [md_13005::p00024] Reserve Bank of India (Rural Co-operative Banks – Cash Reserve Ratio and Statutory Liquidity Ratio) Directions, 2025 (Updated as on June 19, 2026) (md_13005; Rural Co-operative Banks)

Verifier retries: 0. LLM calls: 1 new, 0 from cache. Model: gemini-3.5-flash-lite.
```

**Note.** Limitation shown by this transcript: the temporal filter correctly marks the paragraph as 'original in force; amended from <date>', but the corpus holds only the current (amended) text of each Direction, so the answer states the post-amendment rule for a date before the amendment took effect. The pipeline can mark an amendment; it cannot show the pre-amendment wording, which the corpus does not keep.

### One query with the class filter

```
$ python3 scripts/demo.py "What must be in place before IT services are outsourced?" --class "Payments Banks"
Question: What must be in place before IT services are outsourced?
Entity class: Payments Banks   As of: (not given)
Filters: class filter ON, temporal filter OFF, verifier ON

Answer:
  - A bank intending to outsource any of its IT services must put in place a comprehensive Board-approved IT outsourcing policy. [md_13088::p00189]  [verifier: supported]

Evidence (top 5 after filters):
  [md_13088::p00189] Reserve Bank of India (Payments Banks – Managing Risks in Outsourcing) Directions, 2025 (md_13088; Payments Banks)
  [md_13088::p00247] Reserve Bank of India (Payments Banks – Managing Risks in Outsourcing) Directions, 2025 (md_13088; Payments Banks)
  [md_13088::p00205] Reserve Bank of India (Payments Banks – Managing Risks in Outsourcing) Directions, 2025 (md_13088; Payments Banks)
  [md_13088::p00207] Reserve Bank of India (Payments Banks – Managing Risks in Outsourcing) Directions, 2025 (md_13088; Payments Banks)
  [md_13088::p00256] Reserve Bank of India (Payments Banks – Managing Risks in Outsourcing) Directions, 2025 (md_13088; Payments Banks)

Verifier retries: 0. LLM calls: 1 new, 0 from cache. Model: gemini-3.5-flash-lite.
```

### The same query without the class filter

```
$ python3 scripts/demo.py "What must be in place before IT services are outsourced?" --class "Payments Banks" --no-class-filter
Question: What must be in place before IT services are outsourced?
Entity class: Payments Banks   As of: (not given)
Filters: class filter OFF, temporal filter OFF, verifier ON

Answer: the evidence does not answer this question.

Evidence (top 5 after filters):
  [md_12939::p00328] Reserve Bank of India (Housing Finance Companies) Directions, 2025 (Updated as on April 15, 2026) (md_12939; Non-Banking Financial Companies)
  [md_13062::p00044] Reserve Bank of India (Local Area Banks – Managing Risks in Outsourcing) Directions, 2025 (md_13062; Local Area Banks)
  [md_13062::p00157] Reserve Bank of India (Local Area Banks – Managing Risks in Outsourcing) Directions, 2025 (md_13062; Local Area Banks)
  [md_12925::p00157] Reserve Bank of India (Credit Information Companies – Managing Risks in Outsourcing) Directions, 2025 (md_12925; Credit Information Companies)
  [md_12967::p00156] Reserve Bank of India (All India Financial Institutions – Managing Risks in Outsourcing) Directions, 2025 (md_12967; All India Financial Institutions)

Verifier retries: 0. LLM calls: 1 new, 0 from cache. Model: gemini-3.5-flash-lite.
```

## Deviations and additions (logged)

- **D1 (addition, before freeze).** The T1 rationale instruction was reworded after format debugging on 5 rejected (non-gold) items, before the prompt freeze: the model wrote 'The matched paragraph …' meta-sentences that nothing can entail.
- **D2 (deviation, operational).** The client-side throttle estimates tokens as characters / 3 (was / 4) after a per-minute input-token 429 on ~150K-token prompts. The 12 RPM / 200K TPM limits are unchanged.
- **D3 (addition).** A call that keeps failing is recorded as a call failure (not written, not scored, never counted as an abstention) and retried on the next run.
- **D4 (deviation (one rule fix, as the prompt allows)).** T3 parser rules v2 after the spot-check (15/20): merged within-paragraph changes, per-item exception dates, 'dated <date>' references ignored. Known defect frozen with the set: merged changes' old words include the previous change's new words.
- **D5 (addition (audit note 1)).** T3 precision: v1 15/20 reported as the human figure; 20/20 only as in-sample post-fix; an independent 10-parse check (spot-check 2) on parses behind frozen items; items from the checked parses and from defect-affected instructions listed.
- **D6 (deviation (audit note 2)).** Long-context calls: at most 3 attempts per item per run with exponential backoff and jitter, every attempt in the ledger; network drops and read timeouts retried as transient; a 300 s read timeout for these prompts; after the remainder run and one full retry pass, > 20% of the 30-item subset still failing triggers a rerun of the whole baseline at one uniform 100K cap. Prompt-token distributions of scored vs failed items are reported and every system is compared on exactly the scored items.
- **D7 (addition (audit note 3), post hoc).** Verifier diagnostics without LLM calls: precision on non-abstained items, and support under a best-single-sentence premise with the count of premises over 512 tokens. Diagnostic only; the frozen verifier is unchanged.
- **D8 (addition (audit note 4)).** The P3-001 framing paragraph sits directly above the T2 class-filter results, with hybrid_minus_source_class next to them.
- **D9 (correction).** The Part A statement that a windowed NLI premise would support far more rationales (15/27 vs 25/27, 5 debug items, 3-sentence window) does not hold on the validation outputs: a best-single-sentence premise supports fewer (see diagnostic b).
- **D10 (deviation (Karan's decision, 2026-09-28)).** The note-2 fallback was triggered EARLY: the long-context baseline is rerun on all 106 items at one uniform 100K cap (same proportional per-class truncation) without first finishing the 150K remainder run and retry pass. The decision was based ONLY on the failure-size evidence: never-answered prompts had a median of about 150K tokens (14 items, range 60K–150K) against about 71K for the 47 scored items (range 6K–132K). Disclosure: long-context scores on those 47 scored items had already been computed and displayed in Claude's session (3-way flag F1 0.515 [0.374, 0.626] against final agentic 0.518 on the same items) before Claude recommended the rerun; Claude's recommendation cited only the size evidence, and Karan decided on that evidence. The 150K run's items are kept only as a record, never reported as the baseline. Items under 100K reuse the cache (identical prompt). Pre-committed next step: if more than 20% of items still fail at 100K after one retry pass, one step down to a uniform 64K cap for all items; if failures remain after that, long-context is reported only on the scored items with the size distribution and every system compared on exactly those items; no further cap changes. A health probe and a 3-consecutive-failure circuit breaker stop provider outages from spending quota.
- **D11 (correction (compute rule)).** Claude stopped the 150K remainder step on the 3-hour compute rule using wall-clock time (4 h). Measured as actual run time (Mac awake, from the power log), that step ran about 62 minutes (6 + 55 min), so the rule was not reached. Run times in this report are active time (macOS monotonic clock, which stops while the Mac sleeps); wall time is shown alongside.
- **D12 (addition).** Before the outage cutoff, the 37 long-context items whose 100K prompt is byte-identical to a cached 150K prompt were scored from the cache (cache-only mode: no API call, no ledger entry); their outputs are identical to the 150K run. Gemini then recovered overnight and the chain completed the 100K pass and one retry pass: 102 of 106 items answered, 4 still failing (4%, below the 20% step-down threshold, so no 64K rerun). The demo transcripts ran on Gemini; the Groq demo fallback was never used.

## Appendix: long-context at the 150K cap (superseded by the 100K rerun, shown for completeness)

Computed in Claude's session before the rerun decision (D10). The items attempted but never answered are the large prompts; the never-attempted items are simply those the run had not reached. n = 47 scored items. Prompt tokens at the 150K cap: scored: n=47, median 71067, min 6451, max 132443; attempted, never answered: n=14, median 149622, min 59600, max 149962; never attempted (run stopped): n=45, median 55276, min 10624, max 149873.

| System (same items) | 3-way flag Macro-F1 | Collapsed Macro-F1 | Coverage |
|---|---|---|---|
| Long-context LLM, 150K cap (superseded) | 0.515 [0.374, 0.626] | 0.866 [0.664, 1.000] | 1.000 [1.000, 1.000] |
| Majority (in-sample) | 0.206 [0.153, 0.249] | 0.472 [0.440, 0.495] | 1.000 [1.000, 1.000] |
| P2-002 candidates (dense within-family) | 0.464 [0.328, 0.553] | 0.802 [0.598, 0.949] | 1.000 [1.000, 1.000] |
| Class-blind LLM | 0.631 [0.465, 0.770] | 0.774 [0.570, 0.925] | 1.000 [1.000, 1.000] |
| Class-aware LLM | 0.560 [0.403, 0.696] | 0.802 [0.598, 0.936] | 1.000 [1.000, 1.000] |
| **Final agentic** | 0.518 [0.370, 0.642] | 0.658 [0.452, 0.814] | 0.766 [0.638, 0.872] |
| Class-blind + verifier (ablation A) | 0.502 [0.353, 0.617] | 0.666 [0.461, 0.821] | 0.723 [0.596, 0.851] |

Long-context (150K) minus each system, same 47 items:

| Comparison | Δ 3-way F1 | Δ collapsed F1 | Δ coverage |
|---|---|---|---|
| Long-context (150K) − Majority (in-sample) | +0.309 [+0.163, +0.411] (excludes 0 (above)) | +0.394 [+0.175, +0.534] (excludes 0 (above)) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context (150K) − P2-002 candidates (dense within-family) | +0.052 [-0.021, +0.145] (does not exclude 0) | +0.064 [-0.061, +0.200] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context (150K) − Class-blind LLM | -0.116 [-0.223, -0.0003] (excludes 0 (below)) | +0.092 [+0.0000, +0.204] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context (150K) − Class-aware LLM | -0.045 [-0.149, +0.050] (does not exclude 0) | +0.064 [-0.054, +0.200] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context (150K) − **Final agentic** | -0.002 [-0.096, +0.093] (does not exclude 0) | +0.208 [+0.099, +0.349] (excludes 0 (above)) | +0.234 [+0.128, +0.362] (excludes 0 (above)) |
| Long-context (150K) − Class-blind + verifier (ablation A) | +0.013 [-0.092, +0.135] (does not exclude 0) | +0.200 [+0.099, +0.334] (excludes 0 (above)) | +0.277 [+0.149, +0.404] (excludes 0 (above)) |

## Limitations

- API outage: `gemini-3.5-flash-lite` returned HTTP 503 'high demand' to every call from 2026-09-28 20:09:51 IST until the first successful probe at 2026-09-28 22:19:25 IST; intermittent 503s continued during the runs, the last at 2026-09-29 01:59:44 IST (5 of 12 probes unavailable). The long-context runs paused and resumed around them; no model switch was made.
- The P4 LLM is a free Flash-Lite-class model (`gemini-3.5-flash-lite`); P3-002's genuine answers used Groq `openai/gpt-oss-120b`. These results describe this model, not frontier models.
- The prompt cache is shared between paired systems (see Shared prompts): at temperature 0 this is identical to re-calling.
- Long-context: 102 items (not the full 106; compare on the same items only); truncation to the cap is proportional per class and counted per item; call failures are listed, never scored.
- T3 circularity: the gold and the temporal filter come from the same parser; T3 measures whether the LLM uses the dates.
- Temporal: the corpus holds only the current (amended) text of each Direction. The system can flag that a paragraph was amended later ('original in force; amended from <date>'), but it cannot show the pre-amendment wording, so for an as-of date before an amendment it may state the post-amendment rule (see the date-specific demo transcript).
- T3 parse precision after the rule fix is Claude's reading of Karan's notes on the same 20 rows, not a new human check.
- The T1 verifier (whole cited paragraph as NLI premise, fixed rule) abstains on about a fifth of items and does not raise precision on the items it keeps (post hoc diagnostic a); a single-sentence premise would not raise support (diagnostic b).
- T3 parse precision: only 6 of the 60 frozen items rest on parses in the first human check; the independent check covers 10 more parses (24 items).
- The T4 unsupported-sentence rate is an NLI proxy, and the verifier and RePASs share an NLI model.
- n per task: T1 106 items (long-context 102); T2 t2_xclass_t1 291, t2_xclass_p2002 53, t2_supp_p2003 25; T3 52; T4 28 primary (30 shown). One human rater for every human label.
- The class-aware gain is for retrieving/judging against the named target class; it is not a general class-blind vs class-aware verdict (P3-001).
- The P3-002 gameability verdict uses its pre-registered rule (reproduces iff the CI lies at or above 0). P4 labels use 'excludes 0' only when the CI is strictly above or below 0. No reported P3-002 result lies on the boundary, so the two conventions never disagree here (checked: none of the 12 P3-002 verdict CIs, 6 gameability and 6 repair ranking, main and sensitivity, has a bound at 0).

## Environment and quota

- Calls per quota day (Pacific date; resets 12:30 IST): {'gemini-3.5-flash-lite': {'2026-09-27': 317, '2026-09-28': 480}}.
- Machine: macOS-26.3.1-arm64-arm-64bit-Mach-O; Python 3.14.3; packages {'torch': '2.11.0', 'transformers': '5.4.0', 'sentence-transformers': '6.1.0', 'bm25s': '0.3.11', 'numpy': '2.4.3'}.

Generated 2026-09-28T21:28:16+00:00 by `scripts/run_p4.py report`.
