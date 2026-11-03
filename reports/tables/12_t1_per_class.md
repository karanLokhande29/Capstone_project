# Table 12. T1 per-class results and confusion structure (106 items; long-context on its 102)

Flag accuracy by source entity class, k/n [Wilson 95%]. Classes with n < 5 would be listed as insufficient n; every source class here has n >= 7.

## Majority

| Source class | Flag accuracy |
|---|---|
| All India Financial Institutions | 1/11 = 0.091 [0.016, 0.377] |
| Asset Reconstruction Companies | 7/7 = 1.000 [0.646, 1.000] |
| Commercial Banks | 7/15 = 0.467 [0.248, 0.699] |
| Credit Information Companies | 4/7 = 0.571 [0.250, 0.842] |
| Local Area Banks | 4/8 = 0.500 [0.215, 0.785] |
| Non-Banking Financial Companies | 1/7 = 0.143 [0.026, 0.513] |
| Payments Banks | 4/8 = 0.500 [0.215, 0.785] |
| Regional Rural Banks | 5/9 = 0.556 [0.267, 0.811] |
| Rural Co-operative Banks | 2/8 = 0.250 [0.071, 0.591] |
| Small Finance Banks | 11/15 = 0.733 [0.480, 0.891] |
| Urban Co-operative Banks | 6/11 = 0.545 [0.280, 0.787] |

## P2-002 candidates

| Source class | Flag accuracy |
|---|---|
| All India Financial Institutions | 3/11 = 0.273 [0.097, 0.566] |
| Asset Reconstruction Companies | 5/7 = 0.714 [0.359, 0.918] |
| Commercial Banks | 13/15 = 0.867 [0.621, 0.963] |
| Credit Information Companies | 4/7 = 0.571 [0.250, 0.842] |
| Local Area Banks | 5/8 = 0.625 [0.306, 0.863] |
| Non-Banking Financial Companies | 3/7 = 0.429 [0.158, 0.750] |
| Payments Banks | 4/8 = 0.500 [0.215, 0.785] |
| Regional Rural Banks | 6/9 = 0.667 [0.354, 0.879] |
| Rural Co-operative Banks | 2/8 = 0.250 [0.071, 0.591] |
| Small Finance Banks | 11/15 = 0.733 [0.480, 0.891] |
| Urban Co-operative Banks | 5/11 = 0.455 [0.213, 0.720] |

## Class-blind LLM

| Source class | Flag accuracy |
|---|---|
| All India Financial Institutions | 6/11 = 0.545 [0.280, 0.787] |
| Asset Reconstruction Companies | 7/7 = 1.000 [0.646, 1.000] |
| Commercial Banks | 11/15 = 0.733 [0.480, 0.891] |
| Credit Information Companies | 5/7 = 0.714 [0.359, 0.918] |
| Local Area Banks | 4/8 = 0.500 [0.215, 0.785] |
| Non-Banking Financial Companies | 3/7 = 0.429 [0.158, 0.750] |
| Payments Banks | 8/8 = 1.000 [0.676, 1.000] |
| Regional Rural Banks | 6/9 = 0.667 [0.354, 0.879] |
| Rural Co-operative Banks | 2/8 = 0.250 [0.071, 0.591] |
| Small Finance Banks | 10/15 = 0.667 [0.417, 0.848] |
| Urban Co-operative Banks | 7/11 = 0.636 [0.354, 0.848] |

## Class-aware LLM

| Source class | Flag accuracy |
|---|---|
| All India Financial Institutions | 3/11 = 0.273 [0.097, 0.566] |
| Asset Reconstruction Companies | 7/7 = 1.000 [0.646, 1.000] |
| Commercial Banks | 11/15 = 0.733 [0.480, 0.891] |
| Credit Information Companies | 5/7 = 0.714 [0.359, 0.918] |
| Local Area Banks | 4/8 = 0.500 [0.215, 0.785] |
| Non-Banking Financial Companies | 3/7 = 0.429 [0.158, 0.750] |
| Payments Banks | 5/8 = 0.625 [0.306, 0.863] |
| Regional Rural Banks | 5/9 = 0.556 [0.267, 0.811] |
| Rural Co-operative Banks | 2/8 = 0.250 [0.071, 0.591] |
| Small Finance Banks | 12/15 = 0.800 [0.548, 0.930] |
| Urban Co-operative Banks | 8/11 = 0.727 [0.434, 0.903] |

## Final agentic

| Source class | Flag accuracy |
|---|---|
| All India Financial Institutions | 1/11 = 0.091 [0.016, 0.377] |
| Asset Reconstruction Companies | 5/7 = 0.714 [0.359, 0.918] |
| Commercial Banks | 9/15 = 0.600 [0.357, 0.802] |
| Credit Information Companies | 4/7 = 0.571 [0.250, 0.842] |
| Local Area Banks | 4/8 = 0.500 [0.215, 0.785] |
| Non-Banking Financial Companies | 3/7 = 0.429 [0.158, 0.750] |
| Payments Banks | 4/8 = 0.500 [0.215, 0.785] |
| Regional Rural Banks | 4/9 = 0.444 [0.189, 0.733] |
| Rural Co-operative Banks | 1/8 = 0.125 [0.022, 0.471] |
| Small Finance Banks | 10/15 = 0.667 [0.417, 0.848] |
| Urban Co-operative Banks | 6/11 = 0.545 [0.280, 0.787] |

## Class-blind + verifier

| Source class | Flag accuracy |
|---|---|
| All India Financial Institutions | 3/11 = 0.273 [0.097, 0.566] |
| Asset Reconstruction Companies | 5/7 = 0.714 [0.359, 0.918] |
| Commercial Banks | 10/15 = 0.667 [0.417, 0.848] |
| Credit Information Companies | 4/7 = 0.571 [0.250, 0.842] |
| Local Area Banks | 4/8 = 0.500 [0.215, 0.785] |
| Non-Banking Financial Companies | 3/7 = 0.429 [0.158, 0.750] |
| Payments Banks | 7/8 = 0.875 [0.529, 0.978] |
| Regional Rural Banks | 6/9 = 0.667 [0.354, 0.879] |
| Rural Co-operative Banks | 1/8 = 0.125 [0.022, 0.471] |
| Small Finance Banks | 8/15 = 0.533 [0.301, 0.752] |
| Urban Co-operative Banks | 5/11 = 0.455 [0.213, 0.720] |

## Long-context (100K)

| Source class | Flag accuracy |
|---|---|
| All India Financial Institutions | 2/11 = 0.182 [0.051, 0.477] |
| Asset Reconstruction Companies | 7/7 = 1.000 [0.646, 1.000] |
| Commercial Banks | 11/13 = 0.846 [0.578, 0.957] |
| Credit Information Companies | 3/6 = 0.500 [0.188, 0.812] |
| Local Area Banks | 4/8 = 0.500 [0.215, 0.785] |
| Non-Banking Financial Companies | 3/7 = 0.429 [0.158, 0.750] |
| Payments Banks | 4/8 = 0.500 [0.215, 0.785] |
| Regional Rural Banks | 6/9 = 0.667 [0.354, 0.879] |
| Rural Co-operative Banks | 2/8 = 0.250 [0.071, 0.591] |
| Small Finance Banks | 10/14 = 0.714 [0.454, 0.883] |
| Urban Co-operative Banks | 7/11 = 0.636 [0.354, 0.848] |

## Judgement recall by gold label (class-row units)

| System | same | different | none |
|---|---|---|---|
| Majority | 213/213 = 1.000 [0.982, 1.000] | 0/78 = 0.000 [0.0000, 0.047] | 0/121 = 0.000 [0.0000, 0.031] |
| P2-002 candidates | 195/213 = 0.915 [0.870, 0.946] | 0/78 = 0.000 [0.0000, 0.047] | 114/121 = 0.942 [0.885, 0.972] |
| Class-blind LLM | 191/213 = 0.897 [0.849, 0.931] | 18/78 = 0.231 [0.151, 0.336] | 110/121 = 0.909 [0.845, 0.948] |
| Class-aware LLM | 205/213 = 0.962 [0.928, 0.981] | 7/78 = 0.090 [0.044, 0.174] | 106/121 = 0.876 [0.806, 0.923] |
| Final agentic | 140/213 = 0.657 [0.591, 0.718] | 2/78 = 0.026 [0.007, 0.089] | 107/121 = 0.884 [0.815, 0.930] |
| Class-blind + verifier | 142/213 = 0.667 [0.601, 0.727] | 8/78 = 0.103 [0.053, 0.190] | 111/121 = 0.917 [0.855, 0.954] |
| Long-context (100K) | 196/206 = 0.951 [0.913, 0.973] | 3/76 = 0.039 [0.014, 0.110] | 90/114 = 0.789 [0.706, 0.854] |

## Flag confusion (rows gold, columns predicted), from reports/p4001_metrics_v1.json

**Majority**

| gold \ pred | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|
| shared | 52 | 0 | 0 | 0 |
| class-specific | 40 | 0 | 0 | 0 |
| absent | 14 | 0 | 0 | 0 |

**P2-002 candidates**

| gold \ pred | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|
| shared | 48 | 0 | 4 | 0 |
| class-specific | 31 | 0 | 9 | 0 |
| absent | 1 | 0 | 13 | 0 |

**Class-blind LLM**

| gold \ pred | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|
| shared | 46 | 5 | 1 | 0 |
| class-specific | 18 | 12 | 10 | 0 |
| absent | 3 | 0 | 11 | 0 |

**Class-aware LLM**

| gold \ pred | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|
| shared | 49 | 3 | 0 | 0 |
| class-specific | 28 | 6 | 6 | 0 |
| absent | 3 | 0 | 10 | 1 |

**Final agentic**

| gold \ pred | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|
| shared | 38 | 4 | 0 | 10 |
| class-specific | 17 | 3 | 8 | 12 |
| absent | 2 | 0 | 10 | 2 |

**Class-blind + verifier**

| gold \ pred | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|
| shared | 39 | 2 | 1 | 10 |
| class-specific | 13 | 6 | 10 | 11 |
| absent | 2 | 0 | 11 | 1 |

**Long-context (100K)**

| gold \ pred | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|
| shared | 46 | 2 | 2 | 0 |
| class-specific | 32 | 3 | 4 | 0 |
| absent | 3 | 0 | 10 | 0 |

