# Table 5. T1 benchmark: labels, provenance, reliability (P2-004)

- Sample 123; validated 106; rejected as not an obligation 17/123 = 0.138 (Wilson 95% [0.088, 0.210]).
- Provenance routes: adjudicated 38, retest-consistent 6, single-pass 62.
- Flags: {'shared': 52, 'class-specific': 40, 'absent': 14, 'ambiguous': 0}. Class-row judgements: {'same': 213, 'different': 78, 'none': 121, 'unsure': 0}.
- applies_to is the source class alone on 103/106 = 0.972 (Wilson 95% [0.920, 0.990]).
- Compared classes per item (capped at 4): 2 classes: 3 items, 3 classes: 6 items, 4 classes: 97 items.

## Labels by source class (validated items; per-class shown where n >= 5)

| Source class | Validated | Rejected | shared | class-specific | absent |
|---|---|---|---|---|---|
| All India Financial Institutions | 11 | 1 | 1 | 8 | 2 |
| Asset Reconstruction Companies | 7 | 0 | 7 | 0 | 0 |
| Commercial Banks | 15 | 2 | 7 | 2 | 6 |
| Credit Information Companies | 7 | 0 | 4 | 3 | 0 |
| Local Area Banks | 8 | 3 | 4 | 3 | 1 |
| Non-Banking Financial Companies | 7 | 4 | 1 | 4 | 2 |
| Payments Banks | 8 | 3 | 4 | 4 | 0 |
| Regional Rural Banks | 9 | 1 | 5 | 2 | 2 |
| Rural Co-operative Banks | 8 | 1 | 2 | 6 | 0 |
| Small Finance Banks | 15 | 1 | 11 | 3 | 1 |
| Urban Co-operative Banks | 11 | 1 | 6 | 5 | 0 |

Insufficient n (< 5): none.

## Reliability

Single-expert annotations (rater_1) with a second-rater set (30 items, rater_1–rater_3, pre-adjudication) and a blind test-retest (no washout period).

| Measure | Field | κ [95% bootstrap CI] |
|---|---|---|
| Inter-rater, Fleiss (3 raters) | class-row judgement | 0.774 [0.645, 0.886] (n = 20 items, 80 units) |
| Inter-rater, Fleiss (3 raters) | differential_flag | 0.571 [0.289, 0.807] (n = 20 items, 20 units) |
| Inter-rater, Fleiss (3 raters) | not_obligation | 0.392 [-0.015, 0.689] (n = 30 items, 30 units) |
| Inter-rater, Cohen rater_2–rater_1 | per_class_judgement | 0.762 [0.654, 0.872] (n = 20 items, 80 units) |
| Inter-rater, Cohen rater_2–rater_1 | differential_flag | 0.444 [0.180, 0.739] (n = 20 items, 20 units) |
| Inter-rater, Cohen rater_2–rater_1 | not_obligation | 0.250 [0.0000, 0.571] (n = 30 items, 30 units) |
| Inter-rater, Cohen rater_2–rater_3 | per_class_judgement | 0.792 [0.673, 0.894] (n = 26 items, 104 units) |
| Inter-rater, Cohen rater_2–rater_3 | differential_flag | 0.602 [0.337, 0.858] (n = 26 items, 26 units) |
| Inter-rater, Cohen rater_2–rater_3 | not_obligation | 0.634 [0.0000, 1.000] (n = 30 items, 30 units) |
| Inter-rater, Cohen rater_1–rater_3 | per_class_judgement | 0.777 [0.639, 0.903] (n = 20 items, 80 units) |
| Inter-rater, Cohen rater_1–rater_3 | differential_flag | 0.733 [0.423, 1.000] (n = 20 items, 20 units) |
| Inter-rater, Cohen rater_1–rater_3 | not_obligation | 0.471 [0.129, 0.793] (n = 30 items, 30 units) |
| Test-retest (blind, no washout), all 25 | differential_flag | 0.426 [0.091, 0.730] (n = 20 items, 20 units) |
| Test-retest (blind, no washout), all 25 | class-row judgement | 0.550 [0.333, 0.752] (n = 20 items, 78 units) |
| Test-retest (blind, no washout), 9 overlap items | differential_flag | 0.758 [0.429, 1.000] (n = 8 items, 8 units) |
| Test-retest (blind, no washout), 9 overlap items | class-row judgement | 0.572 [0.248, 1.000] (n = 8 items, 31 units) |
| Test-retest (blind, no washout), other 16 | differential_flag | 0.234 [-0.224, 0.625] (n = 12 items, 12 units) |
| Test-retest (blind, no washout), other 16 | class-row judgement | 0.526 [0.265, 0.737] (n = 12 items, 47 units) |
| Pilot test-retest (v1 → v3.1 guidelines) | differential_flag | -0.128 [-0.377, 0.070] (n = 16 items, 16 units) |
| Pilot inter-rater, Fleiss (3 raters), CONDITIONAL (D11: applies_to pre-filled) | differential_flag | 0.603 (point estimate) (n = 17 items) |
| Pilot inter-rater, Cohen rater_2–rater_1, CONDITIONAL (D11) | differential_flag | 0.626 [0.301, 0.904] (n = 17 items) |
| Pilot inter-rater, Cohen rater_2–rater_3, CONDITIONAL (D11) | differential_flag | 0.462 [-0.034, 0.817] (n = 17 items) |
| Pilot inter-rater, Cohen rater_1–rater_3, CONDITIONAL (D11) | differential_flag | 0.720 [0.387, 1.000] (n = 17 items) |
| Timed re-label vs pass 1 (20 single-pass items) | differential_flag | 0.409 [0.042, 0.759] (n = 19 items, 19 units) |
| Timed re-label vs pass 1 (20 single-pass items) | class-row judgement | 0.684 [0.506, 0.872] (n = 19 items, 72 units) |

## Candidate-label agreement with the validated labels, by P2-002 band

| Band | Agreement |
|---|---|
| high | 119/119 = 1.000 (Wilson 95% [0.969, 1.000]) |
| mid | 125/132 = 0.947 (Wilson 95% [0.895, 0.974]) |
| low | 114/161 = 0.708 (Wilson 95% [0.634, 0.773]) |

