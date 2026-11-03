# P2-003 — Supplementary sources: harvest, link, and the Week-2 alignment check

Direction-level links and a hand-alignment check. No gold labels, no `applies_to`, no `differential_flag`. No LLM or embedding model was used. Paragraph mappings come only from the hand-labelled sheet.

## Outcome

| Source | Clean paragraph-map rate (Wilson 95%) | Decision under the pre-registered rule | Interval crosses |
|---|---|---|---|
| faq | 5/30 = 16.7% (7.3%–33.6%) | **validation_or_motivation_only** | direction_weak_min |
| enforcement | 16/30 = 53.3% (36.1%–69.8%) | **direction_level_weak_label_only** | paragraph_weak_min |

These two rows replace Phase 1's `NOT YET MEASURED` for FAQ / enforcement alignment (Phase 1: "FAQ index needs a second-level crawl").

Rule `p2003_alignment_rule_v1.json` (sha256 `3556d26544f2…`, created 2026-09-26T10:25:13.785027+00:00): clean rate ≥ 60% → paragraph-level weak label / validation; 30% – < 60% → direction-level weak labels only; < 30% → validation / motivation only. The point estimate decides. With n ≈ 30 a Wilson 95% interval is roughly ±17 points. Intervals that cross a decision line: faq, enforcement (that decision is not secure against sampling error).

Label source: **manual** (one rater). Minutes per item: 0.5 (30.0 min total over 60 items; source: recalled_estimate).

## Harvest (Kaggle, Internet on, rate limit 1.5 s)

| Source | Discovered | Stored pages | Failures (reason) | Parsed items | Items by era |
|---|---|---|---|---|---|
| faq | 81 | 81 | 1 {'captcha': 1} | 1915 | {'post_consolidation': 462, 'pre_consolidation': 1453} |
| enforcement | 463 | 463 | 0  | 463 | {'post_consolidation': 186, 'pre_consolidation': 277} |
| amendment | 333 | 333 | 0  | 333 | {'post_consolidation': 333} |
| withdrawn | 9458 | 1 | 0  | 10038 | {'post_consolidation': 216, 'pre_consolidation': 9797, 'unknown': 25} |

- Stored pages re-validated: 877 on Kaggle, all again at ingest; **0 CAPTCHA or error pages stored** (tests `test_captcha_is_never_stored_and_is_counted`, `test_end_to_end`).
- FAQ: 81 topics → 1915 Q&A items. Topics with no HTML Q&A (content only in a PDF, or no question markup): [62, 93, 104, 105].
- Enforcement: 4244 press releases listed for the configured years; 463 monetary-penalty releases (186 post-, 277 pre-consolidation). Near misses excluded: 199 {'cancels_registration': 24, 'cancels_licence': 16, 'directions_section_35a': 158, 'penalty_other': 1, 'compounding': 0}.
- Entity class resolved for 455/463 = 98.3%: {'Commercial Banks': 53, 'Credit Information Companies': 4, 'Non-Banking Financial Companies': 86, 'Payment and Settlement System': 7, 'Payments Banks': 3, 'Regional Rural Banks': 4, 'Rural Co-operative Banks': 105, 'Small Finance Banks': 3, 'Urban Co-operative Banks': 190, 'unresolved': 8}.
- Quoted titles: 566 in 463 releases (mean 1.222); 74 releases quote none; 67 cite no Direction at all, 56 of them only a statute.
- Quoted titles that are pre-consolidation names: 299/566 = 52.8% (on the online withdrawn list); consolidated names 78/566; unknown 189/566.
- Amendment Directions (≥ 2025-11-28): 333 of 867 notifications listed; near misses 42. Target Direction cited in the body: 312/333; linked to a Direction: 333/333; citing paragraph numbers: 302/333.
- Repeal map (local): 391 annex entries in 23 Directions; 189 "stand repealed" statements in 189 Directions. Online withdrawn list found: True (9458 circulars; it names no replacing Direction).
- Charges not parsed: 7/463 releases (see Limitations).

## Direction-level link coverage (A3)

`title_fuzzy` threshold 0.75 (config, fixed in Part A before any labelling). Each item counts once, by its best link.

| Source | Items | exact_ref | repeal_map | title_fuzzy | none | Linked | Fuzzy margin n / min / median / max / zero |
|---|---|---|---|---|---|---|---|
| amendment | 333 | 329 | 4 | 0 | 0 | 333/333 = 100.0% | 0 / None / None / None / 0 |
| enforcement | 463 | 0 | 36 | 203 | 224 | 239/463 = 51.6% | 203 / 0.0 / 0.75188 / 0.8 / 7 |
| faq | 1915 | 392 | 56 | 99 | 1368 | 547/1915 = 28.6% | 99 / 0.0 / 0.0 / 0.666667 / 70 |
| withdrawn:local_annex | 391 | 0 | 391 | 0 | 0 | 391/391 = 100.0% | 0 / None / None / None / 0 |
| withdrawn:local_repeal_statement | 189 | 0 | 189 | 0 | 0 | 189/189 = 100.0% | 0 / None / None / None / 0 |
| withdrawn:online_list | 9458 | 4 | 625 | 422 | 8407 | 1051/9458 = 11.1% | 422 / 0.0 / 0.0 / 0.723077 / 283 |

A zero margin means the same subject exists for several entity classes and the item had no resolved class (FAQ, withdrawn list); the tie is broken by the configured class order.

## Alignment check (C3 / D1)

Seed 20261001. FAQ: 462 of 1915 items qualify under the deterministic cue filter; 30 drawn, round-robin across categories. Enforcement: 186 post-consolidation releases (preferred) and 277 pre-consolidation; 30 drawn, round-robin across entity classes; eras drawn: post_consolidation. Candidate pools: {'linked_direction': 20, 'class_corpus': 13, 'full_corpus': 27}.

| Source | n | paragraph | multi_paragraph | direction_only | wrong_direction | unanchored | Clean rate | paragraph + multi | Direction-link precision (locked) | Candidate-hit share |
|---|---|---|---|---|---|---|---|---|---|---|
| faq | 30 | 5 | 2 | 4 | 0 | 19 | 5/30 = 16.7% (Wilson 95% 7.3%–33.6%) | 7/30 = 23.3% (Wilson 95% 11.8%–40.9%) | 3/3 = 100.0% (Wilson 95% 43.9%–100.0%) | 9/9 = 100.0% (Wilson 95% 70.1%–100.0%) |
| enforcement | 30 | 16 | 2 | 10 | 1 | 1 | 16/30 = 53.3% (Wilson 95% 36.1%–69.8%) | 18/30 = 60.0% (Wilson 95% 42.3%–75.4%) | 14/15 = 93.3% (Wilson 95% 70.2%–98.8%) | 16/20 = 80.0% (Wilson 95% 58.4%–91.9%) |

Locked direction-link precision: over items that had a link and were not labelled `unanchored`, the share not labelled `wrong_direction`. Candidate-hit share: chosen paragraph ids that were among the 8 shown candidates.

### Candidate-hit share by candidate pool

Linked rows offer the linked Direction's paragraphs; rows with no linked Direction offer a corpus-wide TF-IDF search (within the item's entity class plus function-heading Directions, or all Directions).

| Source | Pool | Items | Candidate-hit share |
|---|---|---|---|
| faq | linked_direction | 5 | 2/2 = 100.0% (Wilson 95% 34.2%–100.0%) |
| faq | class_corpus | 0 | n/a (n = 0) |
| faq | full_corpus | 25 | 7/7 = 100.0% (Wilson 95% 64.6%–100.0%) |
| enforcement | linked_direction | 15 | 10/12 = 83.3% (Wilson 95% 55.2%–95.3%) |
| enforcement | class_corpus | 13 | 5/7 = 71.4% (Wilson 95% 35.9%–91.8%) |
| enforcement | full_corpus | 2 | 1/1 = 100.0% (Wilson 95% 20.6%–100.0%) |

### Scoring conventions (fixed by Karan before any rate was seen)

1. Primary clean rate = label `paragraph` as labelled (the locked rule; it decides). Strict rate also excludes `paragraph` rows whose note says "partial".
2. Strict direction-link precision, over rows that had a link: wrong if `wrong_direction`, a chosen paragraph outside the linked Directions, `unanchored` despite a link, or a `direction_only` note naming only other Directions; a `direction_only` note naming a linked md_id (or none) is correct.

| Source | Strict clean rate | Band (same as primary?) | "partial" notes | "uncertain" notes | Strict link precision | Link verdicts (n) |
|---|---|---|---|---|---|---|
| faq | 5/30 = 16.7% (Wilson 95% 7.3%–33.6%) | validation_or_motivation_only (same) | 0 | 2 | 3/5 = 60.0% (Wilson 95% 23.1%–88.2%) | correct:direction_only_note_matches_link 2; correct:paragraph_in_linked 1; wrong:unanchored_with_link 2 |
| enforcement | 10/30 = 33.3% (Wilson 95% 19.2%–51.2%) | direction_level_weak_label_only (same) | 7 | 6 | 12/15 = 80.0% (Wilson 95% 54.8%–93.0%) | correct:direction_only_note_matches_link 3; correct:paragraph_in_linked 9; wrong:paragraph_outside_linked 2; wrong:wrong_direction 1 |

### By stratum

| Stratum | n | paragraph | multi | direction_only | wrong_direction | unanchored |
|---|---|---|---|---|---|---|
| faq:Banker and Debt Manager to Government | 3 | 0 | 0 | 0 | 0 | 3 |
| faq:Commercial Banking | 3 | 1 | 0 | 2 | 0 | 0 |
| faq:Consumer Education and Protection | 3 | 1 | 0 | 0 | 0 | 2 |
| faq:Deposit Insurance and Credit Guarantee Corporation | 3 | 0 | 0 | 0 | 0 | 3 |
| faq:Financial Inclusion and Development | 3 | 0 | 0 | 1 | 0 | 2 |
| faq:Financial Market | 3 | 0 | 0 | 1 | 0 | 2 |
| faq:Foreign Exchange Management | 3 | 1 | 1 | 0 | 0 | 1 |
| faq:Issuer of Currency | 3 | 0 | 1 | 0 | 0 | 2 |
| faq:Non-banking | 2 | 2 | 0 | 0 | 0 | 0 |
| faq:Payment and Settlement System | 2 | 0 | 0 | 0 | 0 | 2 |
| faq:Research | 2 | 0 | 0 | 0 | 0 | 2 |
| enforcement:post_consolidation:Commercial Banks | 5 | 4 | 0 | 1 | 0 | 0 |
| enforcement:post_consolidation:Credit Information Companies | 3 | 3 | 0 | 0 | 0 | 0 |
| enforcement:post_consolidation:Non-Banking Financial Companies | 5 | 5 | 0 | 0 | 0 | 0 |
| enforcement:post_consolidation:Payment and Settlement System | 4 | 0 | 0 | 4 | 0 | 0 |
| enforcement:post_consolidation:Payments Banks | 1 | 0 | 0 | 1 | 0 | 0 |
| enforcement:post_consolidation:Regional Rural Banks | 2 | 1 | 0 | 0 | 1 | 0 |
| enforcement:post_consolidation:Rural Co-operative Banks | 4 | 2 | 0 | 1 | 0 | 1 |
| enforcement:post_consolidation:Urban Co-operative Banks | 4 | 0 | 2 | 2 | 0 | 0 |
| enforcement:post_consolidation:unresolved | 2 | 1 | 0 | 1 | 0 | 0 |

### Sensitivity: post-stratified clean rate

The labelled sheet was drawn with equal (round-robin) allocation across strata; it was not redrawn. This sensitivity weights each sampled stratum's observed clean rate by its population share (FAQ: qualifying items per category; enforcement: post-consolidation releases per entity class). Strata with population but no sampled row are excluded from the weights and listed. The weighted rate is a **point estimate; no interval is computed**. The locked primary decision is unchanged.

**faq**: weighted clean rate **26.0%** → validation_or_motivation_only (same band as the primary validation_or_motivation_only). Population covered by sampled strata: 462/462 = 100.0%.

| Stratum | Population | Share | Sampled n | Clean | Rate |
|---|---|---|---|---|---|
| Banker and Debt Manager to Government | 38 | 8.2% | 3 | 0 | 0.0% |
| Commercial Banking | 142 | 30.7% | 3 | 1 | 33.3% |
| Consumer Education and Protection | 4 | 0.9% | 3 | 1 | 33.3% |
| Deposit Insurance and Credit Guarantee Corporation | 3 | 0.6% | 3 | 0 | 0.0% |
| Financial Inclusion and Development | 42 | 9.1% | 3 | 0 | 0.0% |
| Financial Market | 12 | 2.6% | 3 | 0 | 0.0% |
| Foreign Exchange Management | 65 | 14.1% | 3 | 1 | 33.3% |
| Issuer of Currency | 12 | 2.6% | 3 | 0 | 0.0% |
| Non-banking | 50 | 10.8% | 2 | 2 | 100.0% |
| Payment and Settlement System | 88 | 19.0% | 2 | 0 | 0.0% |
| Research | 6 | 1.3% | 2 | 0 | 0.0% |

**enforcement**: weighted clean rate **48.5%** → direction_level_weak_label_only (same band as the primary direction_level_weak_label_only). Population covered by sampled strata: 186/186 = 100.0%.

| Stratum | Population | Share | Sampled n | Clean | Rate |
|---|---|---|---|---|---|
| Commercial Banks | 21 | 11.3% | 5 | 4 | 80.0% |
| Credit Information Companies | 3 | 1.6% | 3 | 3 | 100.0% |
| Non-Banking Financial Companies | 51 | 27.4% | 5 | 5 | 100.0% |
| Payment and Settlement System | 5 | 2.7% | 4 | 0 | 0.0% |
| Payments Banks | 1 | 0.5% | 1 | 0 | 0.0% |
| Regional Rural Banks | 2 | 1.1% | 2 | 1 | 50.0% |
| Rural Co-operative Banks | 35 | 18.8% | 4 | 2 | 50.0% |
| Urban Co-operative Banks | 66 | 35.5% | 4 | 0 | 0.0% |
| unresolved | 2 | 1.1% | 2 | 1 | 50.0% |

Inter-rater agreement: not measured (the optional second-rater subset was not labelled).

## Provenance

- Kaggle run: 2485.6 s; code dataset (unpacked by Kaggle) /kaggle/input/datasets/meermagia1/rbi-oblibench-code-p2003  | manifest sha256=1c17dd06c584a5032389cd1e04e4faaa3bbd13b0e423d29a5a307c96c086ad00  (64 files verified); versions {'python': '3.12.13', 'requests': '2.32.4', 'bs4': '4.13.5', 'lxml': '6.1.0.0'}.
- Uploaded code zip sha256 `8cc48046b730b56160377d403735516639e8e63be63c4e4e7f2f12ec34e03940`. Code files that differ from it now: `scripts/run_supplementary.py`, `src/supplementary/alignment.py`, `src/supplementary/common.py`. `alignment.py` and `run_supplementary.py` changed for the Part C sheet fix and Part D scoring (never called on Kaggle); `common.py` changed for the validator fix below.
- FAQ topic 176 was rejected on Kaggle as `captcha`. Diagnosis: false positive: the genuine FLAIR FAQ text says 'enter ... valid captcha code'; the Part A validator rejected any page containing the word 'captcha'. Fix: src/supplementary/common.py validate_payload: the bare word 'captcha' counts only when the content marker is missing; challenge widgets / 'are you a robot' / WAF vendors still reject any page. Re-fetched locally on Karan's decision (2026-09-26T10:28:04+00:00, sha256 `60f9ba808b3b…`), recovering 70 items. The Kaggle failure record is kept in the log.

## Limitations

- **n ≈ 30 per source, one rater.** Wilson intervals are about ±17 points; faq, enforcement cross a decision line. No agreement figure exists unless the optional second-rater subset is labelled.
- **Equal allocation across strata.** Categories and entity classes got round-robin (near-equal) slots, not slots proportional to their size, so each rate is stratum-balanced, not population-weighted. Small strata (e.g. an FAQ category with 3 qualifying items) weigh as much as large ones.
- **Enforcement sample eras: post_consolidation.** 277 pre-consolidation releases were harvested and counted but not labelled; their alignment may be lower, since they cite pre-consolidation instruction names.
- **FAQ items were filtered** to answers with a requirement cue and a regulated-entity cue (462 of 1915); the rate describes those, not all FAQ content (much of which covers schemes and markets with no Master Direction).
- **Parsers are deterministic heuristics.** Charges were not parsed for 7 releases: FEMA Authorised Dealer releases with no charge paragraph, and releases stating the charge inside the "RBI found that the charge … was sustained" sentence. Entity class is unresolved for 8 releases ("ARC" and "Asset Care & Reconstruction" names, "BR Act" abbreviations, FEMA AD-bank releases). FAQ topics [62, 93, 104, 105] yield no HTML Q&A.
- **Linking is by title and reference only.** Pre-consolidation names often have no deterministic link; the candidate pools for unlinked rows are a retrieval aid, not a link, and their hit share is reported separately.
- **This step gives direction-level evidence and source decisions only.** No supplementary source is used as a gold label here (P2-004).

## Files for `wip/P2-003`

- `docs/prompts/P2-003.md`
- `src/supplementary/` (`__init__`, `common`, `faq`, `enforcement`, `amendments`, `withdrawn`, `linking`, `alignment`)
- `scripts/run_supplementary.py`, `scripts/build_supplementary_notebook.py`
- `notebooks/phase2-p2003-supplementary.ipynb`
- `tests/test_supplementary_{common,sources,linking,alignment,integration}.py`, `tests/supplementary_support.py`, `tests/fixtures/supplementary/` (hand-written, no RBI text)
- `reports/p2003_supplementary_sources.md`
- `config/config.yaml` (`supplementary:` block), `.gitignore` (`data/supplementary/**`, `*_return.zip`)

**Gitignored data, to back up by hand.** All of `data/supplementary/` (R6: raw RBI pages):
- `kaggle_return/p2003_return.zip` (the Kaggle bundle, sha256 `0245fc80…`)
- `kaggle_upload/` (`p2003_code.zip` + `.sha256` + manifest)
- `faq/`, `enforcement/`, `amendment/`, `withdrawn/` (raw pages, discovery pages and logs, fetch manifests, failure logs, `items_v1.jsonl`; `faq/recovery_v1.json`; `withdrawn/local_repeal_v1.json`)
- `supp_links_v1.jsonl`, `p2003_link_coverage_v1.json`, `p2003_metrics_v1.json`, `p2003_harvest_v1.json`
- `p2003_alignment_rule_v1.json`, `p2003_alignment_sheet_v1.csv`, `p2003_alignment_sheet_v1_completed.csv`, `p2003_alignment_key_v1.json`, `p2003_alignment_draw_log_v1.json`, `p2003_alignment_metrics_v1.json`, `p2003_source_decisions_v1.json`
