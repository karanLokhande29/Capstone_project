# P2-004 pass 1: per-class judgement tables (v1)

_Karan's official pass 1: `data/benchmark/t1/annotation_p2004_karan_pass1_completed.csv`, sha256 `8f1dd4d1db2b10146f54d5c51ba0a5cd464aa43270ecb8cd4a6dc776ba10a098`, received 2026-09-27T07:19:11+00:00, label source manual (declared by Karan, 2026-09-27). Single pass: nothing here is validated yet (Part D)._

- Items: 123; not_obligation (rejected): 18.
- Derived flag (obligation items, v3.6): {'shared': 54, 'class-specific': 31, 'absent': 12, 'ambiguous': 8}.
- Class-row judgements (obligation items): {'same': 196, 'different': 58, 'none': 114, 'unsure': 41}.
- Qrels: 482 records (relevance 2 same: 196, 1 different: 58, 0 checked-none: 228); unsure rows and rejected items give none.

## By source class

| Source class | Items | not_obligation | shared | class-specific | absent | ambiguous |
|---|---|---|---|---|---|---|
| All India Financial Institutions | 12 | 1 | 3 | 6 | 2 | 0 |
| Asset Reconstruction Companies | 7 | 0 | 6 | 1 | 0 | 0 |
| Commercial Banks | 17 | 2 | 7 | 2 | 4 | 2 |
| Credit Information Companies | 7 | 0 | 4 | 3 | 0 | 0 |
| Local Area Banks | 11 | 2 | 7 | 1 | 1 | 0 |
| Non-Banking Financial Companies | 11 | 5 | 0 | 2 | 2 | 2 |
| Payments Banks | 11 | 3 | 3 | 5 | 0 | 0 |
| Regional Rural Banks | 10 | 1 | 5 | 2 | 2 | 0 |
| Rural Co-operative Banks | 9 | 1 | 2 | 5 | 0 | 1 |
| Small Finance Banks | 16 | 2 | 11 | 2 | 1 | 0 |
| Urban Co-operative Banks | 12 | 1 | 6 | 2 | 0 | 3 |

## By class pair (source → target)

| Source → target | n | same | different | none | unsure |
|---|---|---|---|---|---|
| All India Financial Institutions → Commercial Banks | 10 | 7 | 1 | 2 | 0 |
| All India Financial Institutions → Local Area Banks | 7 | 3 | 1 | 2 | 1 |
| All India Financial Institutions → Non-Banking Financial Companies | 4 | 2 | 0 | 2 | 0 |
| All India Financial Institutions → Payments Banks | 3 | 1 | 2 | 0 | 0 |
| All India Financial Institutions → Regional Rural Banks | 4 | 2 | 0 | 0 | 2 |
| All India Financial Institutions → Rural Co-operative Banks | 4 | 0 | 4 | 0 | 0 |
| All India Financial Institutions → Small Finance Banks | 5 | 1 | 2 | 2 | 0 |
| All India Financial Institutions → Urban Co-operative Banks | 7 | 4 | 0 | 2 | 1 |
| Asset Reconstruction Companies → All India Financial Institutions | 6 | 5 | 1 | 0 | 0 |
| Asset Reconstruction Companies → Commercial Banks | 6 | 5 | 1 | 0 | 0 |
| Asset Reconstruction Companies → Local Area Banks | 2 | 1 | 1 | 0 | 0 |
| Asset Reconstruction Companies → Non-Banking Financial Companies | 4 | 4 | 0 | 0 | 0 |
| Asset Reconstruction Companies → Payments Banks | 1 | 1 | 0 | 0 | 0 |
| Asset Reconstruction Companies → Regional Rural Banks | 2 | 2 | 0 | 0 | 0 |
| Asset Reconstruction Companies → Small Finance Banks | 3 | 3 | 0 | 0 | 0 |
| Asset Reconstruction Companies → Urban Co-operative Banks | 4 | 3 | 1 | 0 | 0 |
| Commercial Banks → All India Financial Institutions | 7 | 1 | 1 | 5 | 0 |
| Commercial Banks → Credit Information Companies | 2 | 1 | 0 | 1 | 0 |
| Commercial Banks → Local Area Banks | 4 | 3 | 0 | 0 | 1 |
| Commercial Banks → Non-Banking Financial Companies | 7 | 2 | 1 | 3 | 1 |
| Commercial Banks → Payments Banks | 6 | 2 | 1 | 3 | 0 |
| Commercial Banks → Regional Rural Banks | 6 | 2 | 0 | 4 | 0 |
| Commercial Banks → Rural Co-operative Banks | 7 | 2 | 0 | 5 | 0 |
| Commercial Banks → Small Finance Banks | 10 | 5 | 0 | 4 | 1 |
| Commercial Banks → Urban Co-operative Banks | 8 | 1 | 0 | 7 | 0 |
| Credit Information Companies → All India Financial Institutions | 2 | 2 | 0 | 0 | 0 |
| Credit Information Companies → Commercial Banks | 5 | 4 | 1 | 0 | 0 |
| Credit Information Companies → Local Area Banks | 2 | 1 | 1 | 0 | 0 |
| Credit Information Companies → Non-Banking Financial Companies | 3 | 0 | 1 | 2 | 0 |
| Credit Information Companies → Payments Banks | 6 | 4 | 2 | 0 | 0 |
| Credit Information Companies → Rural Co-operative Banks | 2 | 1 | 0 | 0 | 1 |
| Credit Information Companies → Small Finance Banks | 3 | 3 | 0 | 0 | 0 |
| Credit Information Companies → Urban Co-operative Banks | 5 | 3 | 2 | 0 | 0 |
| Local Area Banks → All India Financial Institutions | 1 | 1 | 0 | 0 | 0 |
| Local Area Banks → Asset Reconstruction Companies | 1 | 1 | 0 | 0 | 0 |
| Local Area Banks → Commercial Banks | 6 | 5 | 1 | 0 | 0 |
| Local Area Banks → Credit Information Companies | 1 | 1 | 0 | 0 | 0 |
| Local Area Banks → Non-Banking Financial Companies | 4 | 3 | 0 | 1 | 0 |
| Local Area Banks → Payments Banks | 4 | 3 | 0 | 1 | 0 |
| Local Area Banks → Regional Rural Banks | 2 | 0 | 0 | 1 | 1 |
| Local Area Banks → Rural Co-operative Banks | 4 | 0 | 0 | 2 | 2 |
| Local Area Banks → Small Finance Banks | 7 | 6 | 0 | 1 | 0 |
| Local Area Banks → Urban Co-operative Banks | 5 | 2 | 0 | 3 | 0 |
| Non-Banking Financial Companies → All India Financial Institutions | 3 | 0 | 1 | 1 | 1 |
| Non-Banking Financial Companies → Commercial Banks | 2 | 0 | 1 | 1 | 0 |
| Non-Banking Financial Companies → Local Area Banks | 2 | 0 | 0 | 2 | 0 |
| Non-Banking Financial Companies → Payments Banks | 2 | 0 | 1 | 0 | 1 |
| Non-Banking Financial Companies → Regional Rural Banks | 5 | 0 | 1 | 2 | 2 |
| Non-Banking Financial Companies → Rural Co-operative Banks | 3 | 0 | 1 | 1 | 1 |
| Non-Banking Financial Companies → Small Finance Banks | 4 | 0 | 1 | 2 | 1 |
| Non-Banking Financial Companies → Urban Co-operative Banks | 3 | 0 | 0 | 2 | 1 |
| Payments Banks → All India Financial Institutions | 3 | 0 | 0 | 2 | 1 |
| Payments Banks → Commercial Banks | 3 | 2 | 1 | 0 | 0 |
| Payments Banks → Local Area Banks | 7 | 5 | 2 | 0 | 0 |
| Payments Banks → Non-Banking Financial Companies | 2 | 0 | 1 | 1 | 0 |
| Payments Banks → Regional Rural Banks | 4 | 0 | 4 | 0 | 0 |
| Payments Banks → Rural Co-operative Banks | 2 | 1 | 0 | 0 | 1 |
| Payments Banks → Small Finance Banks | 5 | 5 | 0 | 0 | 0 |
| Payments Banks → Urban Co-operative Banks | 5 | 2 | 0 | 3 | 0 |
| Regional Rural Banks → All India Financial Institutions | 1 | 0 | 0 | 1 | 0 |
| Regional Rural Banks → Commercial Banks | 5 | 4 | 0 | 0 | 1 |
| Regional Rural Banks → Credit Information Companies | 1 | 0 | 0 | 1 | 0 |
| Regional Rural Banks → Local Area Banks | 5 | 3 | 1 | 1 | 0 |
| Regional Rural Banks → Non-Banking Financial Companies | 3 | 1 | 0 | 2 | 0 |
| Regional Rural Banks → Payments Banks | 6 | 1 | 1 | 3 | 1 |
| Regional Rural Banks → Rural Co-operative Banks | 3 | 1 | 0 | 2 | 0 |
| Regional Rural Banks → Small Finance Banks | 7 | 4 | 2 | 1 | 0 |
| Regional Rural Banks → Urban Co-operative Banks | 4 | 0 | 1 | 3 | 0 |
| Rural Co-operative Banks → All India Financial Institutions | 2 | 1 | 1 | 0 | 0 |
| Rural Co-operative Banks → Commercial Banks | 5 | 1 | 1 | 2 | 1 |
| Rural Co-operative Banks → Local Area Banks | 4 | 3 | 1 | 0 | 0 |
| Rural Co-operative Banks → Non-Banking Financial Companies | 4 | 1 | 1 | 1 | 1 |
| Rural Co-operative Banks → Payments Banks | 3 | 1 | 1 | 1 | 0 |
| Rural Co-operative Banks → Regional Rural Banks | 2 | 0 | 1 | 1 | 0 |
| Rural Co-operative Banks → Small Finance Banks | 5 | 2 | 1 | 2 | 0 |
| Rural Co-operative Banks → Urban Co-operative Banks | 5 | 2 | 1 | 2 | 0 |
| Small Finance Banks → All India Financial Institutions | 3 | 2 | 0 | 1 | 0 |
| Small Finance Banks → Asset Reconstruction Companies | 1 | 1 | 0 | 0 | 0 |
| Small Finance Banks → Commercial Banks | 7 | 7 | 0 | 0 | 0 |
| Small Finance Banks → Credit Information Companies | 1 | 0 | 0 | 1 | 0 |
| Small Finance Banks → Local Area Banks | 8 | 4 | 1 | 2 | 1 |
| Small Finance Banks → Non-Banking Financial Companies | 5 | 4 | 0 | 1 | 0 |
| Small Finance Banks → Payments Banks | 7 | 4 | 1 | 2 | 0 |
| Small Finance Banks → Regional Rural Banks | 7 | 4 | 0 | 2 | 1 |
| Small Finance Banks → Rural Co-operative Banks | 7 | 4 | 0 | 3 | 0 |
| Small Finance Banks → Urban Co-operative Banks | 7 | 3 | 0 | 2 | 2 |
| Urban Co-operative Banks → All India Financial Institutions | 7 | 3 | 1 | 1 | 2 |
| Urban Co-operative Banks → Asset Reconstruction Companies | 1 | 1 | 0 | 0 | 0 |
| Urban Co-operative Banks → Commercial Banks | 9 | 5 | 0 | 3 | 1 |
| Urban Co-operative Banks → Local Area Banks | 5 | 2 | 0 | 1 | 2 |
| Urban Co-operative Banks → Non-Banking Financial Companies | 5 | 2 | 0 | 0 | 3 |
| Urban Co-operative Banks → Payments Banks | 4 | 1 | 2 | 0 | 1 |
| Urban Co-operative Banks → Regional Rural Banks | 5 | 2 | 0 | 1 | 2 |
| Urban Co-operative Banks → Rural Co-operative Banks | 4 | 2 | 1 | 0 | 1 |
| Urban Co-operative Banks → Small Finance Banks | 4 | 2 | 0 | 1 | 1 |
