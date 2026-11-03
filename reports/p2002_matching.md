# P2-002 — Cross-class obligation matching

_Generated 2026-09-26T14:53:44+00:00 by `python scripts/run_matching.py score --label-source manual --sheet-file data/benchmark/matching/p2002_validation_sheet_v1_completed.csv --sensitivity P015:related,P018:related,P025:related`. Label source: **manual**. Sheet: `p2002_validation_sheet_v1_completed.csv` (sha256 `f7a6cdcebf95…`)._

Candidate matches only. This step assigns no `applies_to` and no `differential_flag`.

## Outcome

- §V proceed condition: **met**. High-band counterpart rate 100.0% (needs ≥ 80%); stage-1 same rate 100.0% (needs ≥ 90%).
- Stop conditions: high < 60% False; stage-1 same < 90% False; leakage > 30% False.
- Operating threshold: **0.757567** (the mid_lower edge; per-band rule, walking down from the high band). Chosen on the same 60-pair sample it is scored on, so the rate at the threshold is optimistic.
- Matched share of scored rows at that threshold: 66.7%.

## Inputs and the D8 split

- Candidates: rules v4, 28,694 kept of 33,507; 19 raw entity classes; matrix 1,083 cells (296 populated).
- The 11 core entity classes are matched against each other. The 8 function headings are a separate cross-cutting pool: counted, not matched.

| | With subject family | No subject family | Total |
|---|---|---|---|
| Core classes | 25,918 (matched) | 1,021 | 26,939 |
| Function headings | 75 | 1,680 | 1,755 |
| **Total kept** | | | **28,694** |

| Class | Eligible | Core, no family | Function heading |
|---|---|---|---|
| All India Financial Institutions | 2,423 | 0 | 0 |
| Asset Reconstruction Companies | 308 | 196 | 0 |
| Banker and Debt Manager to Government | 0 | 0 | 23 |
| Banker to Governments and Banks | 0 | 0 | 48 |
| Commercial Banks | 5,427 | 38 | 0 |
| Consumer Education and Protection | 0 | 0 | 154 |
| Credit Information Companies | 286 | 130 | 0 |
| Financial Inclusion and Development | 0 | 0 | 201 |
| Financial Market | 0 | 0 | 477 |
| Foreign Exchange Management | 0 | 0 | 496 |
| Issuer of Currency | 0 | 0 | 59 |
| Local Area Banks | 2,334 | 0 | 0 |
| Non-Banking Financial Companies | 2,478 | 657 | 0 |
| Payment and Settlement System | 0 | 0 | 297 |
| Payments Banks | 2,339 | 0 | 0 |
| Regional Rural Banks | 1,842 | 0 | 0 |
| Rural Co-operative Banks | 1,503 | 0 | 0 |
| Small Finance Banks | 4,358 | 0 | 0 |
| Urban Co-operative Banks | 2,620 | 0 | 0 |

## Units and blocks

- Units: 34,320 (33,055 eligible, 1,265 core with no family, kept as leakage targets). Truncated at 512 tokens: **0**. Longest unit: 2,303 characters.
- Blocks (subject families): 55. Families shared by 2+ core classes: 40.

## Stage 1: repeated wording

- Clusters: 6,364 in total; **6,292 cross-class** (72 within one class). Cross-class clusters hold 26,101 units and 20,634 candidates; 2,173 are all-identical text.
- Classes spanned per cross-class cluster: 2 classes: 1,869, 3 classes: 1,213, 4 classes: 1,172, 5 classes: 605, 6 classes: 494, 7 classes: 362, 8 classes: 271, 9 classes: 183, 10 classes: 123.
- **With and without boilerplate.** 55 of the 6,292 cross-class clusters contain text matching a non-obligation pattern (repeal/savings 38, State/UT nodal-officer designation 11, data-format table row 6). Without them: **6,237** clusters. Candidates in boilerplate clusters: 366 of 20,634.
- The patterns are a reporting filter only. The extraction rules and match statuses are unchanged; they are recorded for P2-004's filter:
  - `repeal_savings`: `\brepeal\w*\b[^.;]{0,120}\b(shall not in any way prejudicially affect|deemed (?:as|to be) governed)|\bdeemed (?:as|to be) governed by these directions`
  - `state_nodal_officer`: `\b(?:all the )?states?\s*(?:and|/)\s*uts?\b[^.;]{0,40}\b(?:shall|may) (?:notify|appoint|designate)|\b(?:the )?(?:state|central) nodal officers?\b(?:\s*\(\w+\))?\s+shall\b|\bthe cno shall\b`
  - `format_table_row`: `\b(?:alpha[ \t]*-?[ \t]*numeric|character|numeric|decimal)[ \t]+\d{1,4}\b`

## Statuses and scores

- Match records: 259,180. `scored` 181,388; `no_candidates_in_family` 0; `no_direction_in_family` 77,792. `no_candidates_in_family` never occurs: every populated core cell has kept candidates.
- Top-1 match type (scored): semantic 97,275; near_duplicate 39,687; exact 44,426.
- Top-1 agreement, semantic vs lexical: 69.0% (n = 181,388).
- Best semantic score (scored rows): q0.000 0.396569, q0.050 0.641148, q0.100 0.668919, q0.250 0.721889, q0.333 0.757567, q0.500 0.888464, q0.667 0.956659, q0.750 0.988102, q0.900 1.0, q0.950 1.0, q1.000 1.000001, mean 0.850997 (n = 181,388).
- Band edges, fixed before sampling (2026-09-25T21:35:50+00:00): low < 0.757567 ≤ mid < 0.95666 ≤ high (tertiles, n = 181,388).

<details><summary>Statuses by class pair (source → target)</summary>

| Source → target | scored | no_candidates_in_family | no_direction_in_family |
|---|---|---|---|
| All India Financial Institutions -> Asset Reconstruction Companies | 355 | 0 | 2,068 |
| All India Financial Institutions -> Commercial Banks | 2,423 | 0 | 0 |
| All India Financial Institutions -> Credit Information Companies | 298 | 0 | 2,125 |
| All India Financial Institutions -> Local Area Banks | 2,112 | 0 | 311 |
| All India Financial Institutions -> Non-Banking Financial Companies | 2,404 | 0 | 19 |
| All India Financial Institutions -> Payments Banks | 1,731 | 0 | 692 |
| All India Financial Institutions -> Regional Rural Banks | 2,051 | 0 | 372 |
| All India Financial Institutions -> Rural Co-operative Banks | 2,113 | 0 | 310 |
| All India Financial Institutions -> Small Finance Banks | 2,423 | 0 | 0 |
| All India Financial Institutions -> Urban Co-operative Banks | 2,351 | 0 | 72 |
| Asset Reconstruction Companies -> All India Financial Institutions | 308 | 0 | 0 |
| Asset Reconstruction Companies -> Commercial Banks | 308 | 0 | 0 |
| Asset Reconstruction Companies -> Credit Information Companies | 0 | 0 | 308 |
| Asset Reconstruction Companies -> Local Area Banks | 308 | 0 | 0 |
| Asset Reconstruction Companies -> Non-Banking Financial Companies | 308 | 0 | 0 |
| Asset Reconstruction Companies -> Payments Banks | 200 | 0 | 108 |
| Asset Reconstruction Companies -> Regional Rural Banks | 291 | 0 | 17 |
| Asset Reconstruction Companies -> Rural Co-operative Banks | 291 | 0 | 17 |
| Asset Reconstruction Companies -> Small Finance Banks | 308 | 0 | 0 |
| Asset Reconstruction Companies -> Urban Co-operative Banks | 308 | 0 | 0 |
| Commercial Banks -> All India Financial Institutions | 3,906 | 0 | 1,521 |
| Commercial Banks -> Asset Reconstruction Companies | 391 | 0 | 5,036 |
| Commercial Banks -> Credit Information Companies | 451 | 0 | 4,976 |
| Commercial Banks -> Local Area Banks | 4,194 | 0 | 1,233 |
| Commercial Banks -> Non-Banking Financial Companies | 4,454 | 0 | 973 |
| Commercial Banks -> Payments Banks | 3,530 | 0 | 1,897 |
| Commercial Banks -> Regional Rural Banks | 4,050 | 0 | 1,377 |
| Commercial Banks -> Rural Co-operative Banks | 4,108 | 0 | 1,319 |
| Commercial Banks -> Small Finance Banks | 4,772 | 0 | 655 |
| Commercial Banks -> Urban Co-operative Banks | 4,656 | 0 | 771 |
| Credit Information Companies -> All India Financial Institutions | 286 | 0 | 0 |
| Credit Information Companies -> Asset Reconstruction Companies | 0 | 0 | 286 |
| Credit Information Companies -> Commercial Banks | 286 | 0 | 0 |
| Credit Information Companies -> Local Area Banks | 65 | 0 | 221 |
| Credit Information Companies -> Non-Banking Financial Companies | 286 | 0 | 0 |
| Credit Information Companies -> Payments Banks | 286 | 0 | 0 |
| Credit Information Companies -> Regional Rural Banks | 2 | 0 | 284 |
| Credit Information Companies -> Rural Co-operative Banks | 65 | 0 | 221 |
| Credit Information Companies -> Small Finance Banks | 286 | 0 | 0 |
| Credit Information Companies -> Urban Co-operative Banks | 286 | 0 | 0 |
| Local Area Banks -> All India Financial Institutions | 1,751 | 0 | 583 |
| Local Area Banks -> Asset Reconstruction Companies | 384 | 0 | 1,950 |
| Local Area Banks -> Commercial Banks | 2,281 | 0 | 53 |
| Local Area Banks -> Credit Information Companies | 218 | 0 | 2,116 |
| Local Area Banks -> Non-Banking Financial Companies | 2,071 | 0 | 263 |
| Local Area Banks -> Payments Banks | 1,806 | 0 | 528 |
| Local Area Banks -> Regional Rural Banks | 2,012 | 0 | 322 |
| Local Area Banks -> Rural Co-operative Banks | 2,163 | 0 | 171 |
| Local Area Banks -> Small Finance Banks | 2,287 | 0 | 47 |
| Local Area Banks -> Urban Co-operative Banks | 2,242 | 0 | 92 |
| Non-Banking Financial Companies -> All India Financial Institutions | 1,790 | 0 | 688 |
| Non-Banking Financial Companies -> Asset Reconstruction Companies | 376 | 0 | 2,102 |
| Non-Banking Financial Companies -> Commercial Banks | 2,051 | 0 | 427 |
| Non-Banking Financial Companies -> Credit Information Companies | 316 | 0 | 2,162 |
| Non-Banking Financial Companies -> Local Area Banks | 1,653 | 0 | 825 |
| Non-Banking Financial Companies -> Payments Banks | 1,324 | 0 | 1,154 |
| Non-Banking Financial Companies -> Regional Rural Banks | 1,525 | 0 | 953 |
| Non-Banking Financial Companies -> Rural Co-operative Banks | 1,678 | 0 | 800 |
| Non-Banking Financial Companies -> Small Finance Banks | 2,051 | 0 | 427 |
| Non-Banking Financial Companies -> Urban Co-operative Banks | 1,997 | 0 | 481 |
| Payments Banks -> All India Financial Institutions | 1,734 | 0 | 605 |
| Payments Banks -> Asset Reconstruction Companies | 249 | 0 | 2,090 |
| Payments Banks -> Commercial Banks | 2,289 | 0 | 50 |
| Payments Banks -> Credit Information Companies | 444 | 0 | 1,895 |
| Payments Banks -> Local Area Banks | 1,999 | 0 | 340 |
| Payments Banks -> Non-Banking Financial Companies | 2,161 | 0 | 178 |
| Payments Banks -> Regional Rural Banks | 1,663 | 0 | 676 |
| Payments Banks -> Rural Co-operative Banks | 1,846 | 0 | 493 |
| Payments Banks -> Small Finance Banks | 2,295 | 0 | 44 |
| Payments Banks -> Urban Co-operative Banks | 2,250 | 0 | 89 |
| Regional Rural Banks -> All India Financial Institutions | 1,550 | 0 | 292 |
| Regional Rural Banks -> Asset Reconstruction Companies | 376 | 0 | 1,466 |
| Regional Rural Banks -> Commercial Banks | 1,836 | 0 | 6 |
| Regional Rural Banks -> Credit Information Companies | 70 | 0 | 1,772 |
| Regional Rural Banks -> Local Area Banks | 1,720 | 0 | 122 |
| Regional Rural Banks -> Non-Banking Financial Companies | 1,624 | 0 | 218 |
| Regional Rural Banks -> Payments Banks | 1,304 | 0 | 538 |
| Regional Rural Banks -> Rural Co-operative Banks | 1,742 | 0 | 100 |
| Regional Rural Banks -> Small Finance Banks | 1,842 | 0 | 0 |
| Regional Rural Banks -> Urban Co-operative Banks | 1,836 | 0 | 6 |
| Rural Co-operative Banks -> All India Financial Institutions | 1,218 | 0 | 285 |
| Rural Co-operative Banks -> Asset Reconstruction Companies | 345 | 0 | 1,158 |
| Rural Co-operative Banks -> Commercial Banks | 1,451 | 0 | 52 |
| Rural Co-operative Banks -> Credit Information Companies | 117 | 0 | 1,386 |
| Rural Co-operative Banks -> Local Area Banks | 1,473 | 0 | 30 |
| Rural Co-operative Banks -> Non-Banking Financial Companies | 1,334 | 0 | 169 |
| Rural Co-operative Banks -> Payments Banks | 1,101 | 0 | 402 |
| Rural Co-operative Banks -> Regional Rural Banks | 1,349 | 0 | 154 |
| Rural Co-operative Banks -> Small Finance Banks | 1,451 | 0 | 52 |
| Rural Co-operative Banks -> Urban Co-operative Banks | 1,456 | 0 | 47 |
| Small Finance Banks -> All India Financial Institutions | 3,532 | 0 | 826 |
| Small Finance Banks -> Asset Reconstruction Companies | 387 | 0 | 3,971 |
| Small Finance Banks -> Commercial Banks | 4,326 | 0 | 32 |
| Small Finance Banks -> Credit Information Companies | 442 | 0 | 3,916 |
| Small Finance Banks -> Local Area Banks | 3,793 | 0 | 565 |
| Small Finance Banks -> Non-Banking Financial Companies | 4,011 | 0 | 347 |
| Small Finance Banks -> Payments Banks | 3,187 | 0 | 1,171 |
| Small Finance Banks -> Regional Rural Banks | 3,624 | 0 | 734 |
| Small Finance Banks -> Rural Co-operative Banks | 3,671 | 0 | 687 |
| Small Finance Banks -> Urban Co-operative Banks | 4,212 | 0 | 146 |
| Urban Co-operative Banks -> All India Financial Institutions | 2,087 | 0 | 533 |
| Urban Co-operative Banks -> Asset Reconstruction Companies | 390 | 0 | 2,230 |
| Urban Co-operative Banks -> Commercial Banks | 2,613 | 0 | 7 |
| Urban Co-operative Banks -> Credit Information Companies | 365 | 0 | 2,255 |
| Urban Co-operative Banks -> Local Area Banks | 2,199 | 0 | 421 |
| Urban Co-operative Banks -> Non-Banking Financial Companies | 2,386 | 0 | 234 |
| Urban Co-operative Banks -> Payments Banks | 1,917 | 0 | 703 |
| Urban Co-operative Banks -> Regional Rural Banks | 2,116 | 0 | 504 |
| Urban Co-operative Banks -> Rural Co-operative Banks | 2,165 | 0 | 455 |
| Urban Co-operative Banks -> Small Finance Banks | 2,613 | 0 | 7 |

</details>

## Blocking leakage

- 7/200 = **3.5%** (Wilson 1.7%–7.0%) of sampled eligible candidates have their best cross-class match, searched without blocking, outside their own family and at or above the high edge 0.95666. Criterion ≤ 30%: **met**.
- Best cross-class match outside the family at any score: 27/200 (3 of them in a document with no family). Seed 20260927.

## Validation (60 blind pairs)

Labels: `same`, `related`, `unrelated`; label source **manual**; the reviewer did not open the key.

| Stratum | n | same | related | unrelated | Counterpart rate (Wilson 95%) | Same rate (Wilson 95%) | Related share |
|---|---|---|---|---|---|---|---|
| stage1 | 10 | 10 | 0 | 0 | 100.0% (72.2%–100.0%) | 100.0% (72.2%–100.0%) | 0.0% |
| high | 15 | 13 | 2 | 0 | 100.0% (79.6%–100.0%) | 86.7% (62.1%–96.3%) | 13.3% |
| mid | 15 | 9 | 6 | 0 | 100.0% (79.6%–100.0%) | 60.0% (35.7%–80.2%) | 40.0% |
| low | 20 | 2 | 11 | 7 | 65.0% (43.3%–81.9%) | 10.0% (2.8%–30.1%) | 55.0% |
| overall | 60 | 34 | 19 | 7 | 88.3% (77.8%–94.2%) | 56.7% (44.1%–68.4%) | 31.7% |

### Semantic vs lexical

- On the 50 semantic-stratum pairs, top 30 by semantic score: 30/30 counterparts (22 same, 8 related). Top 30 by lexical score: 29/30 (24 same, 5 related).
- At equal coverage of all scored rows (66.7%): semantic ≥ 0.757567 gives 30/30 = 100.0% (Wilson 88.6%–100.0%); lexical ≥ 0.260598 gives 31/32 = 96.9% (Wilson 84.3%–99.4%). Caveat: validation pairs were drawn by semantic band; the lexical figure uses the pair's lexical score for the semantic top-1 target.

### Threshold (D2)

Rule: walk down from the high band; a band's lower edge qualifies when that band's own counterpart rate is ≥ 80.0% and every band above it qualified.

| Edge | Value | Band | Band counterpart rate | Qualifies |
|---|---|---|---|---|
| high_lower | 0.95666 | high | 100.0% | True |
| mid_lower | 0.757567 | mid | 100.0% | True |
| min | 0.396569 | low | 65.0% | False |

- Chosen: **0.757567** (mid_lower). 11 of the 19 `related` pairs score below it; the highest `unrelated` pair scores 0.733454. Chosen on the validation sample it is scored on; the rate at the threshold is optimistic.
- `t1_matches_v1_thresholded.jsonl`: 259,180 records; `below_threshold` 60,462; `matched` 120,926; `no_direction_in_family` 77,792. Matched share of scored rows: **66.7%**. Pure semantic cut on the top-1 score: a stage-1 top-1 pair gets no exemption, so 56 rows (43 distinct pairs) whose top target is a near-duplicate prefix match are `below_threshold` (these are mostly fragments; the stage-1 validation stratum never sampled them). Below-threshold rows keep their top-3 targets.

### Sensitivity: an alternative reading

- Relabelling P015 → related, P018 → related, P025 → related: low band 16/20 = 80.0% (Wilson 58.4%–91.9%). The D2 rule would then choose the min edge (0.396569), i.e. every scored pair would be `matched` and there would be no effective threshold. An alternative reading of the named pairs; the reviewer's labels stand and set the threshold.

## Kaggle run

- Device: cuda (Tesla T4). Full-run runtime: 374.7 s. Smoke run: 200 candidates, 2000 records, 4.8 s.
- Model: `BAAI/bge-base-en-v1.5` at revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a` (asserted in the notebook).
- Code: `p2002_code.zip` sha256 `6c389787faa8fa69a3c91164de529f10bafb2c0c077f26f5142ae3106985c93e`. On Kaggle: dataset (unpacked by Kaggle) /kaggle/input/datasets/akashgoyalll/rbi-oblibench-code-p2002  | manifest sha256=e7e45dc0081fda29e470e11944b48979332fdd77377aa9b55d83057f25bd3936  (54 files verified).
- Versions: python 3.12.13, sentence_transformers 5.4.1, torch 2.10.0+cu128, numpy 2.0.2, sklearn 1.6.1, huggingface_hub 1.11.0.

## Findings

_Hand-written section, embedded verbatim by `write_report`. Every number here was re-checked against the key and the labelled sheet on 2026-09-26._

### `related` is the differential signal
- 19 of the 60 validated pairs are `related`: the same topic, but a different requirement. Examples:
  - **P036:** an NBFC prepares its balance sheet under the Companies Act, 2013; an RRB under the BR Act, 1949.
  - **P037:** Upper Tier 2 vs Tier 2 instruments in foreign currency (Payments Banks vs AIFIs).
  - **P041:** PDI vs Upper Tier 2 conditions (Rural Co-operative Banks vs Payments Banks).
- **11 of the 19 `related` pairs score below the operating threshold.** Thresholding keeps precision (30/30 validated pairs above it are counterparts) but drops most of the differential pairs.
- **Do not discard below-threshold pairs.** `t1_matches_v1_thresholded.jsonl` keeps every `below_threshold` row with its top-3 targets, so P2-004 can sample them.

### A matched pair is not the same obligation
- In the mid band, only 9 of 15 pairs (60%) are `same`; the other 6 are `related`. In the high band, 13 of 15 are `same`.
- `matched` means **a counterpart candidate: the same obligation or a related one**. P2-004 must not read `matched` as "shared" (same obligation in both classes).

### Semantic vs lexical
- On the 50 semantic-stratum pairs, semantic ranking's top 30 are all counterparts (22 same, 8 related). Lexical ranking's top 30 are 29/30 (24 same, 5 related).
- Semantic's advantage on this sample is small. It shows mainly on `related` pairs, where the wording differs but the topic is the same. Lexical ranks slightly more `same` pairs into its top 30.
- The sample was drawn by semantic band, which favours the semantic method (see the caveat above).

### Boilerplate in stage 1
- 4 of the 10 stage-1 pairs are not obligations of a regulated entity. Their `same` labels are correct, because the text really is identical.
  - Repeal/savings clauses: P003, P044, P050.
  - A data-format table row: P016.
- The semantic strata contain more of the same kind: P011 (format table row), P013 (repeal/savings), P049 (State/UT nodal-officer designation).
- These are known v4 misses from P2-001. The cluster counts with and without them are in the stage-1 section above.
- The extraction rules are unchanged. The three patterns are recorded for P2-004's filter.

### Sensitivity: an alternative reading
- Claude's reading of three low-band pairs differs from the reviewer's. P015, P018 and P025 are the same topic with a different requirement, so Claude would label them `related`, not `unrelated`.
- That reading lifts the low band to 16/20 = 80%. The D2 rule would then qualify the bottom edge, so every scored pair would be `matched` and there would be no effective threshold.
- **The reviewer's labels stand.** The conservative threshold (0.757567) is the one applied. Both readings are reported above.

## Decisions and corrections made in Part D

- **Label source:** manual (Karan, 2026-09-26). Karan did not open the key.
  - The completed sheet, `p2002_validation_sheet_v1_completed.csv`, was saved by Excel with a UTF-8 BOM. It is read with `utf-8-sig`, and a unit test covers this.
  - `score` checks that the sheet's text columns are byte-identical to the drawn sheet.
- **Threshold rule (correction).** The Part A implementation compared the *mean* of the band rates at and above an edge with 80%.
  - With these labels (high 100%, mid 100%, low 65%), that mean is 88% at the bottom edge, which would have matched every scored pair.
  - It now walks down band by band: an edge qualifies when its own band reaches 80% and every band above it did. This is the reading in the Part D addendum.
  - This reading was fixed after the labels were in. Under a pooled reading (the rate of all semantic-stratum pairs at or above an edge), the bottom edge would qualify at 43/50 = 86% and no threshold would be set. See Limitations.
- **Pure semantic cut (Karan's decision, 2026-09-26).** `apply_threshold` first also marked a row `matched` whenever its top target was a stage-1 wording match.
  - That added 56 rows (43 distinct pairs). All of them are near-duplicate prefix matches scoring 0.703–0.752, and they are mostly fragments, e.g. "(ii) Disclosures shall be required under the Standard only when:".
  - The stage-1 validation stratum never sampled that low-score group.
  - Now every `scored` row is `matched` exactly when its top-1 semantic score is ≥ the threshold.
- **Validation sheet redraw (Part C).**
  - Draw 1 tried subject families in alphabetical order within each class pair, which put 26/60 rows in Asset Liability Management.
  - This was fixed with a seeded family shuffle plus a regression test, and redrawn with the same seed and band edges before anyone saw the sheet. The redraw covers 21 families; the largest has 10 rows.
  - Draw 1 is kept in `data/benchmark/matching/discarded/`, and the reason is recorded in the key's `meta.redraw`.

## Deviations from the prompt (from Part A, raised for audit)

- Stage 1 uses **star** clustering around a leader, not `near_duplicate_clusters()`'s single link. Single link chained different obligations: 26% of multi-text clusters had a pair below 0.9.
- A prefix match needs the shorter text to be at least 40 characters.
- A stage-1 pair must pass the pairwise test directly.
- Match records carry two extra fields: `lexical_best_candidate_id` and `lexical_best_score`.
- The Kaggle run used the `p2002_code.zip` built in Part A. The Part C/D changes (sheet family order, threshold rule, pure semantic cut, report) touch only local steps. None of them changes anything Kaggle computed.

## Limitations

- **The threshold was chosen on the sample it is scored on.** The 30/30 above it is optimistic.
- **The threshold rule was settled after labelling.** D2 as written ("the lowest band edge at which the counterpart rate is ≥ 80%") allows a per-band or a pooled reading. The per-band walk-down gives 0.757567; the pooled reading gives no threshold (43/50 = 86% at the bottom edge). The per-band reading is the more conservative one and matches §AB's per-band stop rule, but it was chosen with the labels visible.
- **The sample is small and has one rater.** There are 60 pairs (10–20 per stratum), so the Wilson intervals are wide: the high band's lower bound is 79.6%, and the low band's interval is 43–82%. One rater labelled them, and the sensitivity reading shows the `related`/`unrelated` line is contestable.
- **The validation sample does not cover every case.** It was drawn per band and per class pair, not in proportion to the scored population. Low-scoring stage-1 prefix matches were not sampled.
- **Blocking is by subject family.** Leakage is low (3.5%, n = 200), but counterparts in family-less documents (1,021 core candidates) are never matched.
- **The boilerplate patterns are heuristics.** They are reported, not applied. Their precision was checked by reading every distinct text of every flagged cluster: all 38 repeal/savings, 11 nodal-officer and 6 format-table clusters. All 38 repeal/savings clusters are the savings clause ("the repeal of these directions … shall not in any way prejudicially affect"); 8 of them also carry the "deemed as governed by these Directions" sentence. The repeal/savings clusters were read during the audit fix, after the first version of this report. Recall is unknown.
- **This step matches only.** It assigns no `applies_to` and no `differential_flag`; that is P2-004.

## Hand-off to P2-004

- Use `data/benchmark/matching/t1_matches_v1_thresholded.jsonl`: `threshold_value` 0.757567, `threshold_source` `p2002_validation_v1`.
- Treat `matched` as "counterpart candidate", not "same obligation".
- Sample from `below_threshold` too: it holds most of the `related` (differential) pairs.
- Filter or down-weight the three boilerplate patterns before counting shared wording.

## Tests

Real pytest 9.1.1 on the Mac (Python 3.14.3), 2026-09-26, run from the repo root as `python3 -m pytest -q -rs -o addopts=`.

- Full suite: **934 passed, 0 skipped, 0 failed**. The suite now also holds the P2-003 tests; `nbformat` is installed here, so the harvest-repair notebook tests run.
- `tests/test_benchmark_matching.py`: 26 passed.
- The P2-001 byte regressions pass: v1–v3 by the test, and v4 by re-extracting in memory and comparing bytes with `t1_candidates_v4.jsonl`.
- Earlier run, for the record: real pytest 9.1.1 on Windows (Python 3.12) gave 819 passed, 2 skipped (the notebook tests, without `nbformat`).
- Two failures from an earlier real-pytest run are fixed OS-independently:
  - `validate_config` treats a path key as absolute if it is absolute under POSIX or Windows rules.
  - `write_json` serialises `Path` values with `as_posix()`.
- Before pytest was installed, a stand-in runner was used. Its failure counts earlier in P2-002 came from gaps in that runner and from packages missing at the time (`bs4`, `lxml`, `pdfplumber`).

## Files for `wip/P2-002`

**New:**
- `src/benchmark/matching.py`
- `scripts/run_matching.py`
- `scripts/build_matching_notebook.py`
- `notebooks/phase2-p2002-matching.ipynb`
- `tests/test_benchmark_matching.py`
- `reports/p2002_matching.md`
- `reports/p2002_matching_notes.md`
- `reports/p2002_validation_metrics_v1.json`

**Modified:**
- `config/config.yaml`: the `matching:` block only.
- `src/benchmark/candidates.py`: helpers exposed. Behaviour is unchanged; the byte regressions pass.

**Gitignored data, to back up by hand.** All under `data/benchmark/matching/`:
- `p2002_units_v1.jsonl`
- `p2002_units_metrics_v1.json`
- `p2002_stage1_local_v1.json`
- `kaggle_upload/` (`p2002_code.zip` + `.sha256` + manifest; the corpus zip + `.sha256`)
- `kaggle_return/` (the 4 result files, plus `p2002_return.zip` itself, sha256 `de39b43f…`)
- `p2002_bands_v1.json`
- `p2002_validation_sheet_v1.csv` (blank)
- `p2002_validation_sheet_v1_completed.csv` (labelled)
- `p2002_validation_key_v1.json`
- `discarded/`
- `t1_matches_v1_thresholded.jsonl`
- `p2002_embeddings_v1.npz` (34,320 × 768 float16, sha256 `33a46eee…`; `unit_ids` match `p2002_units_v1.jsonl`). The embeddings are also on Kaggle as `rbi-oblibench-embeddings-p2002`.

`.gitignore` also ignores `*_return.zip` wherever it is saved (added in P2-003).
