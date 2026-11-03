# Table 3. Cross-class matching validation (P2-002)

60 validation pairs (bge-base-en-v1.5 semantic bands; one rater). Counterpart rate (same + related): 53/60 = 0.883 (Wilson 95% [0.778, 0.942]); same: 34/60 = 0.567 (Wilson 95% [0.441, 0.684]).

| Stratum | n | same | related | unrelated | Counterpart rate |
|---|---|---|---|---|---|
| stage1 | 10 | 10 | 0 | 0 | 10/10 = 1.000 (Wilson 95% [0.722, 1.000]) |
| high | 15 | 13 | 2 | 0 | 15/15 = 1.000 (Wilson 95% [0.796, 1.000]) |
| mid | 15 | 9 | 6 | 0 | 15/15 = 1.000 (Wilson 95% [0.796, 1.000]) |
| low | 20 | 2 | 11 | 7 | 13/20 = 0.650 (Wilson 95% [0.433, 0.819]) |

Operating threshold 0.757567 (mid_lower); chosen on the same sample it is scored on. Leakage at the high edge: 7/200 = 0.035 (Wilson 95% [0.017, 0.070]).
