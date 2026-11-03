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
