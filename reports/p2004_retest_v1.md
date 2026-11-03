# P2-004 test-retest reliability (v1)

_Generated 2026-09-27T11:22:55+00:00 by `python scripts/run_t1.py retest-score`. Intra-rater: Karan pass 1 vs pass 2. Bootstrap: 2000 resamples, seed 20260924, resampling whole items._

## Method

Blind test-retest procedure: the retest subset was fixed in advance, independently of pass-1 answers, and pass 2 was done on a shuffled blank sheet without access to pass 1. No washout period was enforced between the passes; a short interval may inflate agreement through recall of pass-1 answers.

This is test-retest (intra-rater) reliability, not inter-annotator agreement.

## Provenance

- Pass 1 (P2-004): `data/benchmark/t1/annotation_p2004_karan_pass1_completed.csv`, sha256 `8f1dd4d1db2b…`, received 2026-09-27T07:19:11+00:00; completed_at: unknown (not logged).
- Pilot pass 1: ingested 2026-09-25T07:02:54.834672+00:00; completed_at: unknown (not logged).
- Pass 2: `data/benchmark/t1/annotation_p2004_karan_pass2_completed_v2.2.csv`, sha256 `2a41142872f2cef0e750501751e7df701400335d5e70e35504a627a5bc502318`, received 2026-09-27T11:21:53+00:00, label source manual; completed_at: unknown (not logged).
- Blank pass-2 sheet written 2026-09-27T08:32:38+00:00; window from then to receipt: **169.2 min**.
- Self-reported pass-2 time: **165.0 min** (self-reported total (Karan, 2026-09-27), not logged per session); 3.84 min/item over the sheet's items.
- **Correction.** This file corrects `data/benchmark/t1/annotation_p2004_karan_pass2_completed.csv` (sha256 `3ea732016ab8…`, unchanged). Reason: The original used function headings in applies_to on three pilot rows, which guidelines v2.2 forbid; Karan corrected those rows only, in a new versioned file (2026-09-27). Only these rows differ, only in input cells:
  - row 2 `t1_pilot_md_13525::p00050_01`: `applies_to`: 'Financial Inclusion and Development' → 'Commercial Banks;Regional Rural Banks;Rural Co-operative Banks;Small Finance Banks'; `applies_to_rationale`: "The KCC insurance process requires the beneficiary's explicit consent before premium is debited from the account." → "Commercial Banks, Regional Rural Banks, Rural Co-operative Banks and Small Finance Banks must obtain the beneficiary's explicit consent at the application stage when the insurance premium is to be paid through the KCC account."; `differential_flag`: 'class-specific' → 'shared'
  - row 10 `t1_pilot_md_13525::p00050_00`: `applies_to`: 'Financial Inclusion and Development' → 'Commercial Banks;Regional Rural Banks;Rural Co-operative Banks;Small Finance Banks'; `applies_to_rationale`: 'The scheme requires beneficiaries to be informed about the insurance cover available to them.' → 'Commercial Banks, Regional Rural Banks, Rural Co-operative Banks and Small Finance Banks must ensure KCC beneficiaries are made aware of the available insurance covers.'
  - row 83 `t1_pilot_md_12061::p00055_00`: `applies_to`: 'Financial Market' → 'Commercial Banks;Non-Banking Financial Companies;Payments Banks;Regional Rural Banks;Rural Co-operative Banks;Small Finance Banks;Urban Co-operative Banks'; `applies_to_rationale`: 'A counterparty that misreports or duplicates an OTC-market deal must immediately notify Clearcorp.' → 'The immediate Clearcorp notification duty applies to eligible OTC money-market counterparties across these regulated classes.'; `differential_flag`: 'class-specific' → 'shared'

Pass-2 timing, side by side (provenance only; nothing is gated on it):

| Figure | Minutes | Basis |
|---|---|---|
| Self-reported labelling time | 165 | self-reported total (Karan, 2026-09-27), not logged per session |
| Blank sheet written → original file last modified | 121.3 | 2026-09-27T08:32:38+00:00 → 2026-09-27T10:33:59+00:00 |
| Blank sheet written → original file received | 133.0 | 2026-09-27T08:32:38+00:00 → 2026-09-27T10:45:37+00:00 |
| Blank sheet written → corrected file received | 169.2 | 2026-09-27T08:32:38+00:00 → 2026-09-27T11:21:53+00:00 (includes the three-row correction) |

The self-reported 165 min exceeds the 133.0 min window up to the original submission. Both are reported as they are; neither is adjusted and neither gates anything.

## Phase-2 retest items

Denominators: not_obligation over all items in the subset; the flag, class-row judgements and applies_to over items labelled as obligations in **both** passes.

| Subset | Measure | n items (units) | Agreement | κ | 95% CI |
|---|---|---|---|---|---|
| all 25 | not_obligation | 25 (25) | 92.0% | 0.702 | 0.000 to 1.000 |
| all 25 | flag (v3.6) | 20 (20) | 65.0% | 0.426 | 0.091 to 0.730 |
| all 25 | class-row judgement | 20 (78) | 70.5% | 0.550 | 0.333 to 0.752 |
| 9 also in the second-rater overlap | not_obligation | 9 (9) | 88.9% | 0.000 | 0.000 to 0.000 |
| 9 also in the second-rater overlap | flag (v3.6) | 8 (8) | 87.5% | 0.758 | 0.429 to 1.000 |
| 9 also in the second-rater overlap | class-row judgement | 8 (31) | 74.2% | 0.572 | 0.248 to 1.000 |
| the other 16 | not_obligation | 16 (16) | 93.8% | 0.818 | 0.256 to 1.000 |
| the other 16 | flag (v3.6) | 12 (12) | 50.0% | 0.234 | -0.224 to 0.625 |
| the other 16 | class-row judgement | 12 (47) | 68.1% | 0.526 | 0.265 to 0.737 |

| Subset | applies_to n | Exact-set agreement | 95% CI | Mean Jaccard | 95% CI |
|---|---|---|---|---|---|
| all 25 | 20 | 90.0% | 0.750 to 1.000 | 0.914 | 0.783 to 1.000 |
| 9 also in the second-rater overlap | 8 | 87.5% | 0.625 to 1.000 | 0.887 | 0.662 to 1.000 |
| the other 16 | 12 | 91.7% | 0.750 to 1.000 | 0.932 | 0.795 to 1.000 |

## Pilot items (18)

Pilot layout (item-level flag). Flag and applies_to over the 16 items labelled as obligations in both passes.

| Measure | n | Agreement | κ | 95% CI |
|---|---|---|---|---|
| not_obligation | 18 | 94.4% | 0.640 | 0.000 to 1.000 |
| differential_flag | 16 | 31.2% | -0.128 | -0.377 to 0.070 |
| applies_to exact-set | 16 | 50.0% | — | 0.250 to 0.750 |
| applies_to mean Jaccard | 16 | 0.585 | — | 0.372 to 0.782 |

**Sensitivity, excluding the 3 corrected pilot items** (`t1_pilot_md_12061::p00055_00`, `t1_pilot_md_13525::p00050_00`, `t1_pilot_md_13525::p00050_01`): corrected after pass-1 answers for these items had been displayed in the session (reversed-ingest report); their corrected pass-2 labels may not be blind. After correction, all three match pass 1 exactly on applies_to.

| Measure | n | Agreement | κ | 95% CI |
|---|---|---|---|---|
| not_obligation | 15 | 93.3% | 0.634 | 0.000 to 1.000 |
| differential_flag | 13 | 23.1% | -0.193 | -0.444 to 0.062 |
| applies_to exact-set | 13 | 38.5% | — | 0.154 to 0.692 |
| applies_to mean Jaccard | 13 | 0.489 | — | 0.279 to 0.729 |

## Items where pass 1 ≠ pass 2 (28 items, 55 rows)

For adjudication: `data/benchmark/t1/p2004_retest_adjudication_v1.csv` (blank `final_decision`, `final_rationale`).

| Item | Kind | Comparison | Class | Differs on | Pass 1 | Pass 2 |
|---|---|---|---|---|---|---|
| t1_md_13100::p00041 | retest | class | Rural Co-operative Banks | judgement; unsure | unsure | different |
| t1_md_13094::p00185 | retest | class | All India Financial Institutions | judgement; unsure | unsure | none |
| t1_md_13030::p00071 | retest | class | Non-Banking Financial Companies | judgement; unsure | unsure | none |
| t1_md_12975::p00064 | retest (overlap) | class | Regional Rural Banks | judgement; unsure | unsure | different |
| t1_md_12975::p00064 | retest (overlap) | class | Rural Co-operative Banks | judgement | different | none |
| t1_md_12975::p00064 | retest (overlap) | class | Small Finance Banks | judgement | different | none |
| t1_md_12975::p00064 | retest (overlap) | class | Urban Co-operative Banks | judgement; unsure | unsure | different |
| t1_md_13605::p00068 | retest | item |  | not_obligation; applies_to; differential_flag (derived) | applies_to: Local Area Banks | flag: shared | not_obligation | flag: None |
| t1_md_13605::p00068 | retest | class | Commercial Banks | judgement | same | (not an obligation) |
| t1_md_13605::p00068 | retest | class | Rural Co-operative Banks | judgement | none | (not an obligation) |
| t1_md_13605::p00068 | retest | class | Small Finance Banks | judgement | same | (not an obligation) |
| t1_md_13605::p00068 | retest | class | Urban Co-operative Banks | judgement | none | (not an obligation) |
| t1_md_13608::p00026 | retest | item |  | differential_flag (derived) | applies_to: Local Area Banks | flag: shared | applies_to: Local Area Banks | flag: class-specific |
| t1_md_13608::p00026 | retest | class | Urban Co-operative Banks | judgement | none | different |
| t1_md_13122::p00115 | retest | item |  | applies_to | applies_to: Credit Information Companies; Small Finance Banks | flag: shared | applies_to: All India Financial Institutions; Asset Reconstruction Companies; Commercial Banks; Credit Information Companies; Local Area Banks; Non-Banking Financial Companies; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: shared |
| t1_md_12973::p00166 | retest | item |  | differential_flag (derived) | applies_to: All India Financial Institutions | flag: shared | applies_to: All India Financial Institutions | flag: class-specific |
| t1_md_12973::p00166 | retest | class | Non-Banking Financial Companies | judgement | none | different |
| t1_md_12973::p00166 | retest | class | Urban Co-operative Banks | judgement | none | different |
| t1_md_13111::p00157 | retest (overlap) | item |  | not_obligation; applies_to; differential_flag (derived) | not_obligation | flag: None | applies_to: Small Finance Banks | flag: shared |
| t1_md_13111::p00157 | retest (overlap) | class | Local Area Banks | judgement | (not an obligation) | same |
| t1_md_13111::p00157 | retest (overlap) | class | Non-Banking Financial Companies | judgement | (not an obligation) | none |
| t1_md_13111::p00157 | retest (overlap) | class | Rural Co-operative Banks | judgement | (not an obligation) | same |
| t1_md_13111::p00157 | retest (overlap) | class | Urban Co-operative Banks | judgement | (not an obligation) | same |
| t1_md_12953::p00098 | retest | item |  | differential_flag (derived) | applies_to: Non-Banking Financial Companies | flag: ambiguous | applies_to: Non-Banking Financial Companies | flag: class-specific |
| t1_md_12953::p00098 | retest | class | All India Financial Institutions | judgement; unsure | unsure | different |
| t1_md_12980::p00044 | retest (overlap) | item |  | applies_to | applies_to: All India Financial Institutions | flag: shared | applies_to: All India Financial Institutions; Asset Reconstruction Companies; Commercial Banks; Local Area Banks; Non-Banking Financial Companies; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: shared |
| t1_md_13159::p00778 | retest | item |  | differential_flag (derived) | applies_to: Commercial Banks | flag: class-specific | applies_to: Commercial Banks | flag: ambiguous |
| t1_md_13159::p00778 | retest | class | All India Financial Institutions | judgement | different | none |
| t1_md_13159::p00778 | retest | class | Local Area Banks | judgement; unsure | unsure | none |
| t1_md_13159::p00778 | retest | class | Payments Banks | judgement; unsure | different | unsure |
| t1_md_13020::p00033 | retest (overlap) | item |  | differential_flag (derived) | applies_to: Urban Co-operative Banks | flag: ambiguous | applies_to: Urban Co-operative Banks | flag: class-specific |
| t1_md_13020::p00033 | retest (overlap) | class | All India Financial Institutions | judgement; unsure | unsure | different |
| t1_md_13020::p00033 | retest (overlap) | class | Commercial Banks | judgement; unsure | unsure | none |
| t1_md_13020::p00033 | retest (overlap) | class | Payments Banks | judgement; unsure | unsure | different |
| t1_md_13020::p00033 | retest (overlap) | class | Regional Rural Banks | judgement; unsure | unsure | different |
| t1_md_13328::p00018 | retest | item |  | differential_flag (derived) | applies_to: Small Finance Banks | flag: shared | applies_to: Small Finance Banks | flag: class-specific |
| t1_md_13328::p00018 | retest | class | Regional Rural Banks | judgement | same | different |
| t1_md_12927::p00108 | retest | item |  | differential_flag (derived) | applies_to: Asset Reconstruction Companies | flag: class-specific | applies_to: Asset Reconstruction Companies | flag: shared |
| t1_md_12927::p00108 | retest | class | All India Financial Institutions | judgement | different | same |
| t1_md_12927::p00108 | retest | class | Commercial Banks | judgement | different | same |
| t1_md_12927::p00108 | retest | class | Local Area Banks | judgement | different | same |
| t1_md_12927::p00108 | retest | class | Urban Co-operative Banks | judgement | different | same |
| t1_pilot_md_12061::p00055_00 | pilot | item |  | differential_flag | applies_to: Commercial Banks; Non-Banking Financial Companies; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: class-specific | applies_to: Commercial Banks; Non-Banking Financial Companies; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: shared |
| t1_pilot_md_12927::p00046_00 | pilot | item |  | not_obligation; applies_to; differential_flag | applies_to: All India Financial Institutions; Asset Reconstruction Companies; Commercial Banks; Foreign Exchange Management; Local Area Banks; Non-Banking Financial Companies; Payment and Settlement System; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: shared | not_obligation |
| t1_pilot_md_12958::p00018_00 | pilot | item |  | differential_flag | applies_to: Non-Banking Financial Companies | flag: absent | applies_to: Non-Banking Financial Companies | flag: class-specific |
| t1_pilot_md_12983::p01671_00 | pilot | item |  | applies_to; differential_flag | applies_to: All India Financial Institutions; Commercial Banks; Small Finance Banks | flag: shared | applies_to: All India Financial Institutions | flag: class-specific |
| t1_pilot_md_13042::p00070_00 | pilot | item |  | applies_to; differential_flag | applies_to: All India Financial Institutions; Commercial Banks; Local Area Banks; Non-Banking Financial Companies; Regional Rural Banks; Small Finance Banks; Urban Co-operative Banks | flag: class-specific | applies_to: Regional Rural Banks | flag: shared |
| t1_pilot_md_13042::p00070_01 | pilot | item |  | applies_to; differential_flag | applies_to: All India Financial Institutions; Commercial Banks; Local Area Banks; Non-Banking Financial Companies; Regional Rural Banks; Small Finance Banks; Urban Co-operative Banks | flag: class-specific | applies_to: Regional Rural Banks | flag: shared |
| t1_pilot_md_13042::p00070_02 | pilot | item |  | applies_to; differential_flag | applies_to: All India Financial Institutions; Commercial Banks; Local Area Banks; Non-Banking Financial Companies; Regional Rural Banks; Small Finance Banks; Urban Co-operative Banks | flag: class-specific | applies_to: Regional Rural Banks | flag: shared |
| t1_pilot_md_13526::p00022_00 | pilot | item |  | differential_flag | applies_to: Payment and Settlement System | flag: absent | applies_to: Payment and Settlement System | flag: class-specific |
| t1_pilot_md_13526::p00022_01 | pilot | item |  | differential_flag | applies_to: Payment and Settlement System | flag: absent | applies_to: Payment and Settlement System | flag: class-specific |
| t1_pilot_md_13633::p00074_00 | pilot | item |  | applies_to; differential_flag | applies_to: Commercial Banks; Local Area Banks; Non-Banking Financial Companies; Payment and Settlement System; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: class-specific | applies_to: Small Finance Banks | flag: shared |
| t1_pilot_md_13633::p00074_01 | pilot | item |  | applies_to; differential_flag | applies_to: Commercial Banks; Local Area Banks; Non-Banking Financial Companies; Payment and Settlement System; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: class-specific | applies_to: Small Finance Banks | flag: shared |
| t1_pilot_md_13633::p00074_02 | pilot | item |  | applies_to; differential_flag | applies_to: Commercial Banks; Local Area Banks; Non-Banking Financial Companies; Payments Banks; Regional Rural Banks; Rural Co-operative Banks; Small Finance Banks; Urban Co-operative Banks | flag: class-specific | applies_to: Small Finance Banks | flag: shared |
| t1_pilot_md_13644::p00037_00 | pilot | item |  | applies_to | applies_to: Commercial Banks; Local Area Banks; Payments Banks; Small Finance Banks | flag: shared | applies_to: Commercial Banks | flag: shared |

## Limitations

- n is small (25 retest items, 18 pilot items); the intervals are wide.
- No washout period: a short interval may inflate agreement through recall of pass-1 answers.
- pass_1_completed_at is unknown (not logged); pass-2 timing is self-reported.
- The pilot's pass 1 was labelled under guidelines v1; pass 2 under v3.1 (same item-level definitions).
- The 9 overlap items are reported separately because their second-rater labels are not yet adjudicated.
