# P2-002 Part D — addendum (run together with Part D of P2-002.md)

## 1. Input handling
- The completed sheet is `p2002_validation_sheet_v1_completed.csv`, saved by Excel **with a UTF-8 BOM**. Read it with `utf-8-sig`, and add a unit test for this.
- Record `label_source: manual` (Karan, 2026-09-26). Karan did not open the key.

## 2. Expected scores (Claude's independent tally; stop and report any difference)

| Stratum | n | same | related | unrelated | Counterpart (Wilson 95%) | Same (Wilson 95%) |
|---|---|---|---|---|---|---|
| Stage 1 | 10 | 10 | 0 | 0 | 100% (72–100) | 100% (72–100) |
| High | 15 | 13 | 2 | 0 | 100% (80–100) | 87% (62–96) |
| Mid | 15 | 9 | 6 | 0 | 100% (80–100) | 60% (36–80) |
| Low | 20 | 2 | 11 | 7 | 65% (43–82) | 10% (3–30) |

- **§V proceed condition:** met. The high band's counterpart rate is 100% (≥ 80%) and stage 1's same rate is 100% (≥ 90%). No §AB stop condition fires from validation.
- **D2 threshold:** the lowest band edge with a counterpart rate ≥ 80% is the mid band's lower edge, **0.757567**. All 30 validated pairs above it are counterparts, and all 7 `unrelated` pairs score ≤ 0.733. The threshold was chosen on this sample, so state that 30/30 is optimistic.

## 3. Report these findings in `reports/p2002_matching.md`
- **Semantic vs lexical on the 50 semantic-stratum pairs.** The top 30 by semantic score are 30/30 counterparts (22 same, 8 related). The top 30 by lexical score are 29/30 (24 same, 5 related). Semantic's advantage here is small; it mainly shows up on `related` pairs.
- **`related` is the differential signal.** 19 of 60 pairs are `related`.
  - Examples: P036 (NBFC balance sheet under the Companies Act vs RRB under the BR Act); P037 (Upper Tier 2 vs Tier 2 foreign-currency cap); P041 (PDI vs Upper Tier 2 conditions).
  - **11 of the 19 `related` pairs score below the threshold.** Thresholding keeps precision but drops most differential pairs.
  - **So do not discard below-threshold pairs.** Keep their top 3 targets flagged `below_threshold` for P2-004 to sample.
- **A matched pair is not the same obligation.** In the mid band only 60% of pairs are `same`. `matched` means "a counterpart candidate: the same obligation or a related one". P2-004 must not read `matched` as `shared`.
- **Boilerplate in stage 1.** 4 of the 10 stage-1 pairs are not obligations:
  - repeal / savings clauses (P003, P044, P050);
  - a data-format table row (P016).

  Semantic strata contain more of the same kind: P011, P013, P049. These patterns are known v4 misses from P2-001. Report the number of stage-1 cross-class clusters **with and without** clusters whose text matches the repeal/savings, nodal-officer and format-table patterns. Without that split, the "shared wording" headline is inflated. Don't change the extraction rules here; record it for P2-004's filter.
- **Sensitivity.** Claude would read three low-band pairs as `related` rather than `unrelated`: P015, P018 and P025, all same topic but different requirement. That would lift the low band to 16/20 = 80%, and the D2 rule would then set no threshold at all. Karan's labels stand; report both readings. The conservative threshold (0.757567) is the one used.

## 4. Also include from Parts A–C, if not yet reported
- the leakage rate (n = 200) against the ≤ 30% criterion;
- the stage-1 cluster class-span distribution;
- the D8 split counts (core vs function-heading candidates);
- units truncated;
- Kaggle device and runtime;
- model id and revision;
- the code-zip hash;
- test results (real pytest or the stand-in runner);
- the file list.

## 5. Expected values from `p2002_return.zip` (Claude's independent pass, 2026-09-26; stop and report any difference)
- `t1_matches_v1_thresholded.jsonl`: 259,180 records. Of 181,388 `scored` rows, **120,926 `matched`** (66.7%) and **60,462 `below_threshold`**. Rows with other statuses are unchanged (0 `no_candidates_in_family`, 77,792 `no_direction_in_family`).
- Leakage: 7/200 = 3.5% (Wilson 1.7–7.0%).
- D8 split: core 25,918 eligible + 1,021 no family = 26,939; function headings 1,755 (1,680 no family, 75 with family). Total 28,694.
- Stage 1: 6,364 clusters, 6,292 cross-class, 2,173 of them fully identical.
- Top-1 agreement, semantic vs lexical: 69.0% (n = 181,388).
- Units: 34,320 total, 33,055 eligible, 0 truncated.
- Code source in the return bundle is `/kaggle/input/datasets/akashgoyalll/rbi-oblibench-code-p2002`, manifest SHA-256 `e7e45dc0…3936`, 54 files.
- Tests: run the full suite and say whether it was real pytest or the stand-in runner.
