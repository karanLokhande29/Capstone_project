# P2-004 T1 benchmark (v1)

_Generated 2026-09-27T13:11:59+00:00 by `python scripts/run_t1.py part-d`. Guidelines v3.1; adjudication rules `data/benchmark/t1/p2004_adjudication_rules.md`._

## Outcome

- Validated set: **106** of 123 sample items (`data/benchmark/t1/t1_validated_v1.jsonl`).
- Rejected as not an obligation: 17 (17/123 = 13.8% (Wilson 8.8%–21.0%) candidate rejection rate).
- In review (excluded): 0.
- Provenance routes: `annotator:karan:adjudicated` 38; `annotator:karan:retest-consistent` 6; `annotator:karan:single-pass` 62.
- Most validated items are single-pass: labelled once by Karan, with no retest and no adjudication.
- Pass-1 support for single-pass items: a timed blind re-label of 20 of them agrees with frozen pass 1 at flag κ 0.409 (n = 19), class-row κ 0.684 (72 rows), applies_to exact-set 89.5% (n = 19), not_obligation agreement 95.0% (n = 20). Evidence only; no validated label was changed.

## Size

- Planned: N = 123 from 600 min at 3.61 min/item (recalled pilot estimate), retest 25.
- Measured pass-1 minutes per item: NOT YET MEASURED (not logged at the time). Pass 2: 165 min self-reported (3.84 min/item; self-reported total (Karan, 2026-09-27), not logged per session).
- Blocks labelled: 7 of 7 (all 123 items).

## Labels (validated set)

- differential_flag: shared 52, class-specific 40, absent 14, ambiguous 0; ambiguity rate 0/106 = 0.0% (Wilson -0.0%–3.5%).
- Class-row judgements: same 213, different 78, none 121, unsure 0.
- applies_to is the source class alone on 103/106 = 97.2% (Wilson 92.0%–99.0%); stand-ins used on 0 items.
- same/different judgements without a matched_paragraph_id: 0.

| Source class | Validated | Rejected | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|---|---|
| All India Financial Institutions | 11 | 1 | 1 | 8 | 2 | 0 |
| Asset Reconstruction Companies | 7 | 0 | 7 | 0 | 0 | 0 |
| Commercial Banks | 15 | 2 | 7 | 2 | 6 | 0 |
| Credit Information Companies | 7 | 0 | 4 | 3 | 0 | 0 |
| Local Area Banks | 8 | 3 | 4 | 3 | 1 | 0 |
| Non-Banking Financial Companies | 7 | 4 | 1 | 4 | 2 | 0 |
| Payments Banks | 8 | 3 | 4 | 4 | 0 | 0 |
| Regional Rural Banks | 9 | 1 | 5 | 2 | 2 | 0 |
| Rural Co-operative Banks | 8 | 1 | 2 | 6 | 0 | 0 |
| Small Finance Banks | 15 | 1 | 11 | 3 | 1 | 0 |
| Urban Co-operative Banks | 11 | 1 | 6 | 5 | 0 | 0 |

## Reliability

### Inter-rater (IRR set: 30 items, Karan, Akash, Meer; pre-adjudication)

- Fleiss' κ, class-row judgements: 0.774 (0.645 to 0.886), 80 rows / 20 items.
- Fleiss' κ, flag: 0.571 (0.289 to 0.807), n = 20; not_obligation: 0.392 (-0.015 to 0.689), n = 30.
- Full pairwise table: `reports/p2004_irr_v1.md`.

### Test-retest (Karan pass 1 vs pass 2; blind; no washout period)

- all 25: flag κ 0.426 (0.091 to 0.730), n = 20; class-row κ 0.550 (0.333 to 0.752), 78 rows.
- 9 overlap items: flag κ 0.758 (0.429 to 1.000), n = 8; class-row κ 0.572 (0.248 to 1.000), 31 rows.
- other 16: flag κ 0.234 (-0.224 to 0.625), n = 12; class-row κ 0.526 (0.265 to 0.737), 47 rows.
- Pilot (18 items): flag κ -0.128 (-0.377 to 0.070), n = 16; applies_to exact-set 50.0%.

**Intra-rater agreement is below inter-rater agreement** in this study: test-retest class-row κ 0.550 vs IRR Fleiss 0.774; flag 0.426 vs 0.571. The two are measured on different items (25 retest vs 30 IRR), with wide, overlapping intervals.

**The pilot flag is not comparable across guideline versions:** pilot pass 1 was labelled under v1 (applies_to pre-filled, no per-class rows, no v2.2 vocabulary), pass 2 under v3.1. Its κ describes the guideline change as much as the rater.

Method: blind test-retest procedure; no washout period was enforced; a short interval may inflate agreement through recall. Full tables: `reports/p2004_retest_v1.md`.

### Timed blind re-label (Phase 2 closing check; evidence only)

- Minutes per item: **5.35** (107.0 min / 20 items; 2 timed blocks, per block [5.2, 5.5]; bootstrap 95% 5.20–5.50). The bootstrap resamples 2 blocks, so with few blocks the interval is close to the range of the per-block rates.

| Measure | Re-label vs pass 1 | Blind retest (all 25) vs pass 1 |
|---|---|---|
| flag κ | 0.409 (0.042 to 0.759), n = 19 | 0.426 (0.091 to 0.730), n = 20 |
| class-row κ | 0.684 (0.506 to 0.872), n = 72 | 0.550 (0.333 to 0.752), n = 78 |
| applies_to exact-set | 89.5% (n = 19) | 90.0% (n = 20) |
| applies_to mean Jaccard | 0.905 | 0.914 |
| not_obligation agreement | 95.0% (n = 20) | 92.0% (n = 25) |

_Evidence only; no validated label was changed. Blind re-label with no washout period._

## Candidate-label agreement (automatic P2-002 labels vs validated labels)

`matched` read as same-or-different, `below_threshold` as none, per compared class; band = top-1 semantic score.

- high band: 119/119 = 100.0% (Wilson 96.9%–100.0%)
- mid band: 125/132 = 94.7% (Wilson 89.5%–97.4%)
- low band: 114/161 = 70.8% (Wilson 63.4%–77.3%)
- Flag, absent vs not absent: 92/106 = 86.8% (Wilson 79.0%–92.0%)

## Temporal fields (validated set)

- in_force_from: 106/106 = 100.0% (Wilson 96.5%–100.0%)
- amended_by: 10/106 = 9.4% (Wilson 5.2%–16.5%)
- in_force_to: 1/106 = 0.9% (Wilson 0.2%–5.2%)

## Enforcement weak-label diagnostic (Direction level; never a label)

- Validated items whose Direction has linked enforcement actions: 9; a penalised entity class appears in applies_to: 9/9 = 100.0% (Wilson 70.1%–100.0%).

## Adjudication

- retest: `data/benchmark/t1/p2004_retest_adjudication_v1_completed.csv`, sha256 `6dac0de74436…`, received 2026-09-27T13:11:59+00:00
- overlap: `data/benchmark/t1/p2004_overlap_adjudication_v1_completed.csv`, sha256 `a527ab769e74…`, received 2026-09-27T13:11:59+00:00
- unsure: `data/benchmark/t1/p2004_unsure_adjudication_v1_completed.csv`, sha256 `080047468aaf…`, received 2026-09-27T13:11:59+00:00
- rules: `data/benchmark/t1/p2004_adjudication_rules.md`, sha256 `3a711cbbbf21…`, received 2026-09-27T13:11:59+00:00
- irr: `data/benchmark/t1/p2004_irr_adjudication_v1_completed.csv`, sha256 `5fa1b1a864a4…`, received 2026-09-27T08:05:46+00:00

## Phase 2 gate checklist

| Gate item | Status | Evidence |
|---|---|---|
| The T1 schema works | met | 106 validated records in `data/benchmark/t1/t1_validated_v1.jsonl` |
| Candidate generation works | met | 25,582-record candidate benchmark (P2-004 A3), unchanged by Part D |
| Human annotation works | met | pass 1 (123 items), pass 2 (43), IRR (3 × 30), four adjudications |
| Pilot test-retest κ is measured | met | flag κ -0.128 (n = 16); not comparable across guideline versions v1→v3 |
| A Phase-2 retest (≥ 20%, stratified) was annotated twice and its κ calculated | met | 25/123 = 20.3%; flag κ 0.426, class-row κ 0.550; no washout period |
| Second-rater κ calculated, or NOT YET MEASURED with the reason | met | IRR set (30 items, 3 raters): Fleiss class-row κ 0.774. The 30 overlap items are a team review (not independent): no κ by design |
| Benchmark size derived with the calculation shown | met | N = 123 from m = 3.61 (recalled). Measured pass-1 m: NOT YET MEASURED (minutes not logged) |
| Disagreements documented | met | IRR, retest, overlap and unsure adjudication files, each with rationales |
| Candidate and validated data kept separate | met | candidate benchmark sha256 unchanged by Part D |
| Provenance preserved | met | route per validated item; receipts with sha256 + received-at for every input |
| Every §Z metric reported with n and CI | met | minutes per item measured in the timed re-label: 5.35 (n = 20 items, 2 blocks; bootstrap 5.20–5.50); pass-1 minutes were not logged |
| All tests pass under real pytest | met | see the test run for this report |

## Limitations

- Most validated items are single-pass (one annotator, one pass).
- Compared classes are capped at 4 per item; applies_to and the flag are over those classes.
- `absent` covers only the paragraphs shown or looked up.
- Test-retest had no washout period; pass-2 time is self-reported; pass-1 time was not logged.
- Three corrected pilot rows may not be blind (see the retest report's sensitivity table).
- The overlap team reviews were revised after reviewer feedback: not independent, no κ.
- The enforcement diagnostic is Direction-level and descriptive.
