# Table 13. Error analysis: failure cases (pointers plus ≤ 25-word excerpts)

Selection rule: qualifying cases sorted by id; first two shown (first one per retention group for long-context). Full text: rehydrate the paragraph from its pointer (release/rehydrate.py).

## (a) Missed `different` judgements

78 gold `different` class-row units; 56 are missed by every LLM system (class-blind, class-aware, final agentic, class-blind + verifier, long-context).

| System | `different` recall | Predicted instead |
|---|---|---|
| Majority | 0/78 = 0.000 [0.0000, 0.047] | same 78 |
| P2-002 candidates | 0/78 = 0.000 [0.0000, 0.047] | none 29, same 49 |
| Class-blind LLM | 18/78 = 0.231 [0.151, 0.336] | none 42, same 18 |
| Class-aware LLM | 7/78 = 0.090 [0.044, 0.174] | none 39, same 32 |
| Final agentic | 2/78 = 0.026 [0.007, 0.089] | none 44, same 13, unsure 19 |
| Class-blind + verifier | 8/78 = 0.103 [0.053, 0.190] | none 41, same 8, unsure 21 |
| Long-context (100K) | 3/76 = 0.039 [0.014, 0.110] | none 30, same 43 |

- `t1_md_12925::p00061` (Credit Information Companies vs Rural Co-operative Banks; gold `different`, gold counterpart `md_12986::p00025`). Source md_12925::p00061 [[0, 114]]: “commensurate processes to manage those risks. For this purpose, the CIC shall, inter alia, consider the following:”. Predictions: Majority `same`, P2-002 candidates `none`, Class-blind LLM `none`, Class-aware LLM `none`, Final agentic `none`, Class-blind + verifier `none`, Long-context (100K) `none`.

- `t1_md_12945::p00050` (Non-Banking Financial Companies vs Payments Banks; gold `different`, gold counterpart `md_13092::p00184`). Source md_12945::p00050 [[0, 333]]: “21. An NBFC shall make following disclosures in ‘Notes to Accounts’ to the financial statements. (1) Loans against gold and silver collateral i) Details of …”. Predictions: Majority `same`, P2-002 candidates `same`, Class-blind LLM `none`, Class-aware LLM `none`, Final agentic `none`, Class-blind + verifier `none`, Long-context (100K) `none`.

## (b) Verifier abstentions on judgements that were correct before the retry

| System | Abstained judgements | …correct on the first pass | Items: flag right on first pass, wrong after |
|---|---|---|---|
| Final agentic | 81 | 59 | 14 of 106 |
| Class-blind + verifier | 80 | 60 | 15 of 106 |

- Final agentic, `t1_md_12927::p00153`: gold and first-pass flag `shared`, final flag `ambiguous`; abstained on All India Financial Institutions, Commercial Banks, Non-Banking Financial Companies, Small Finance Banks. Source md_12927::p00153 [[0, 186]]: “only after closure of any critical gap found during such tests. Such tests shall also be carried out periodically in conformity with internal / regulatory …”.

- Final agentic, `t1_md_12928::p00016`: gold and first-pass flag `shared`, final flag `ambiguous`; abstained on All India Financial Institutions, Small Finance Banks. Source md_12928::p00016 [[39, 235], [236, 473]]: “(1) Any account included in LWD, where an ARC has entered into a compromise settlement with the borrower, shall be removed from the LWD only …”.

- Class-blind + verifier, `t1_md_12925::p00044`: gold and first-pass flag `class-specific`, final flag `ambiguous`; abstained on Commercial Banks, Non-Banking Financial Companies, Payments Banks, Rural Co-operative Banks. Source md_12925::p00044 [[0, 196]]: “9. A CIC intending to outsource its IT services shall put in place a comprehensive Board-approved IT outsourcing policy, the coverage of which is indicated …”.

- Class-blind + verifier, `t1_md_12927::p00153`: gold and first-pass flag `shared`, final flag `ambiguous`; abstained on All India Financial Institutions, Commercial Banks, Non-Banking Financial Companies, Small Finance Banks. Source md_12927::p00153 [[0, 186]]: “only after closure of any critical gap found during such tests. Such tests shall also be carried out periodically in conformity with internal / regulatory …”.

## (c) Long-context errors by gold retention (cap 100,000 tokens, 102 scored)

| Retention group | Items | Flag errors |
|---|---|---|
| all gold kept | 82 | 34 |
| at least one gold cut | 7 | 6 |
| no gold matched paragraph | 13 | 3 |

- `t1_md_12925::p00044` (all gold kept: 4/4 gold paragraphs in the prompt; about 73,757 tokens): gold `class-specific`, predicted `shared`. Source md_12925::p00044 [[0, 196]]: “9. A CIC intending to outsource its IT services shall put in place a comprehensive Board-approved IT outsourcing policy, the coverage of which is indicated …”.

- `t1_md_12968::p00044` (at least one gold cut: 2/4 gold paragraphs in the prompt; about 99,763 tokens): gold `class-specific`, predicted `shared`. Source md_12968::p00044 [[0, 565]]: “(ii) Default in repayment by the borrower is also a type of non-compliance of material terms and conditions of loan repayment contract by the borrower …”.

## (d) T3 with the temporal filter OFF

24 status errors on 52 items. Predicted statuses with the filter off: deleted 4, in_force_original 48; gold: amended 17, deleted 9, in_force_original 26.

| Error | Count |
|---|---|
| gold amended (after the effective date) → predicted in_force_original | 17 |
| gold deleted (after the effective date) → predicted in_force_original | 6 |
| gold in_force_original (before the effective date) → predicted deleted | 1 |

- `T3-002`: md_13071::p00180 as of 2026-05-18 (after the effective date 2026-05-18); gold `amended` governed by `amd_13453`; predicted `in_force_original` / `md_13071` (corpus version: amended).

- `T3-004`: md_13075::p00048 as of 2026-05-04 (after the effective date 2026-04-01); gold `deleted` governed by `amd_13251`; predicted `in_force_original` / `md_13075` (corpus version: original).

## (e) T4: RePASs vs the human `faithful` rating (30 rated answers)

Rule: human faithful = 2 with RePASs composite < 0.5, or faithful = 0 with composite >= 0.5 (a display threshold chosen for this analysis after scoring, not pre-registered). faithful 2 but metric low: 7 ({'genuine': 6, 'concatenated': 1}); faithful 0 but metric high: 0 ({}).

- `T4Q02` (genuine): faithful 2, answers_question 2; RePASs 0.415 (entailment 0.220, contradiction 0.310, obligation coverage 0.333). Answer excerpt (release/data/t4/answers_genuine.jsonl, T4Q02): “You may proceed only after any critical gap identified in the tests has been closed — the tests must be completed and any critical gaps …”.

- `T4Q06` (genuine): faithful 2, answers_question 2; RePASs 0.140 (entailment 0.209, contradiction 0.989, obligation coverage 0.200). Answer excerpt (release/data/t4/answers_genuine.jsonl, T4Q06): “No. The RBI’s Master Directions require that any penalty imposed for a borrower’s default be levied only as a **penal charge**, not as “penal interest,” …”.
