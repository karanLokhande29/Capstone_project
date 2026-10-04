# Confidence calibration report (§8.2)

- Spec `ui/src/data/confidence_spec_v1.json` sha256 `1eeb26e45a733067f4725bba6833e4761c66042d5826af38f6397b7b3f3eb480`.
- M2 frozen in `ui/src/data/confidence_frozen_v1.json` sha256 `a9f00055d2713b175f14a7c0f755df580ade4b8aff3211cc6efd43f73f7ee7fa` at 2026-10-03T11:26:31+00:00 (before gold evaluation, 2026-10-03T11:26:31+00:00).
- Unit: one comparator class unit; correct = comparator judgement equals gold. `unsure` / parse failure = Abstain.
- Caveats: single-expert gold; Flash-Lite-class model; 412 units, so intervals are wide.

## M2: comparator-intrinsic (fitted on the 30-item dev set, frozen before gold evaluation)

- Fitted on: development set: 30-item IRR consensus, 92 comparator units. Used for: Showcase, product badges (Obligation Explorer, assistant, live mode, review queue).
- Base rate (all 412 units): 297/412 = 0.721 [0.676, 0.762].
- ECE (10 bins) 0.087; Brier 0.148. Raw band counts {'High': 162, 'Medium': 123, 'Low': 125, 'Abstain': 2}; merged: none.
- **Status: calibrated**.

| Band | n | correct | accuracy | Wilson 95% |
|---|---|---|---|---|
| High | 162 | 156 | 0.963 | [0.922, 0.983] |
| Medium | 123 | 95 | 0.772 | [0.691, 0.838] |
| Low | 125 | 46 | 0.368 | [0.289, 0.455] |
| Abstain | 2 | 0 | 0.000 | [0.000, 0.658] |

Operating point (fixed in the spec): answer only at High → coverage 0.393 (162/412), accuracy 0.963 [0.922, 0.983].

Band composition by predicted label (correct/n):

- High: `none` 7/7, `same` 149/155
- Medium: `different` 2/3, `none` 93/120
- Low: `different` 36/105, `none` 10/20
- Abstain: `abstain` 0/2

Within-label AUC (does the score separate right from wrong *within* a predicted label?): `same` 0.374 (right 149, wrong 6); `different` 0.536 (right 38, wrong 70); `none` 0.679 (right 110, wrong 37).

Weights (standardised features):

| feature | weight |
|---|---|
| pred_different | -1.574 |
| pred_none | -1.219 |
| n_fields_both_sides | -0.182 |
| n_material_diff | +0.438 |
| single_field_hinge | -0.669 |
| candidates_agree | -0.289 |
| target_amended_text_only | +0.003 |
| ambiguous_matrix_cell | +0.750 |
| (intercept) | +1.035 |

## M1: full signals (cross-validated on gold) (cross-validated on gold)

- Fitted on: 5-fold cross-fitting on gold, grouped by item; fold assignment = numpy default_rng(20261003).permutation over sorted item ids, fold = position mod 5. Used for: research views only, labelled 'cross-validated on gold'.
- Base rate (all 412 units): 297/412 = 0.721 [0.676, 0.762].
- ECE (10 bins) 0.037; Brier 0.139. Raw band counts {'High': 197, 'Medium': 93, 'Low': 120, 'Abstain': 2}; merged: none.
- **Status: calibrated**.

| Band | n | correct | accuracy | Wilson 95% |
|---|---|---|---|---|
| High | 197 | 184 | 0.934 | [0.890, 0.961] |
| Medium | 93 | 69 | 0.742 | [0.645, 0.820] |
| Low | 120 | 44 | 0.367 | [0.286, 0.456] |
| Abstain | 2 | 0 | 0.000 | [0.000, 0.658] |

Operating point (fixed in the spec): answer only at High → coverage 0.478 (197/412), accuracy 0.934 [0.890, 0.961].

Band composition by predicted label (correct/n):

- High: `different` 0/1, `none` 36/42, `same` 148/154
- Medium: `different` 7/12, `none` 61/80, `same` 1/1
- Low: `different` 31/95, `none` 13/25
- Abstain: `abstain` 0/2

Within-label AUC (does the score separate right from wrong *within* a predicted label?): `same` 0.714 (right 149, wrong 6); `different` 0.586 (right 38, wrong 70); `none` 0.688 (right 110, wrong 37).

Weights (standardised features):

| feature | weight |
|---|---|
| pred_different | -1.128 |
| pred_none | -1.385 |
| n_fields_both_sides | +0.120 |
| n_material_diff | +0.302 |
| single_field_hinge | +0.110 |
| candidates_agree | -0.034 |
| target_amended_text_only | +0.115 |
| ambiguous_matrix_cell | +0.519 |
| agree_count_other_llms | +0.884 |
| long_context_unanswered | -0.036 |
| final_agentic_abstained | -0.252 |
| matched_equals_class_aware | -0.359 |
| (intercept) | +1.493 |

