# Phase 1 — Meer: Corpus QA, Annotation Pilot, Validation Protocol

> **Protocol change.** From 2026-09-24 this project has a single annotator (karan). The three-annotator roster this report was originally written against no longer exists, so **inter-annotator agreement is not a statistic this project can produce.** Reliability evidence comes instead from a blind test-retest by the primary annotator and, where a second rater is obtainable, a second-rater comparison. Every figure in §5 is labelled by which of those it is. Fleiss' κ is not reported at all below three real raters.

---

## Derived-axis caveat (read before any `subject_family` stratification)

`subject_family` on every `DocumentRecord`/`ParagraphRecord` is a **derived** value, not one harvested from RBI's own listing: RBI publishes no subject-family taxonomy at discovery time, so P1-002 inferred it by stripping the known `entity_class_raw` string out of each title (P1-002-CORRECTIVE, commit `e4013ca`). `entity_class`, by contrast, is raw-sourced with a 0% unresolved rate.

**The two axes do not carry equal evidentiary weight, and nothing in this report treats them as if they did.** Every figure below that involves `subject_family` is marked accordingly. Provenance is queryable from the data itself (`data/metadata/vocabulary_provenance.json`), not only from prose.

---

## 1. Corpus QA (independent of P1-001's own metrics)

_source: `reports/phase1_meer_qa_metrics.json`, written 2026-09-25T11:49:05+00:00_

- Paragraphs checked: **76188** across **381** documents
- Missing `section_id`: **440** (**0.0058**)
- Missing `clause_path`: **438** (**0.0057**)
- Duplicate `paragraph_id`s: **0**
- Empty text: **0**
- Missing `source_url`: **0**
- Missing `entity_class` (raw-sourced axis): **0** (**0.0000**)
- Missing `subject_family` (**derived** axis): **9188** (**0.1206**)
- Records re-validated against `ParagraphRecord` schema: **500**, failing: **0**
- Spot-check sample drawn (for manual comparison against `source_url`): **10** paragraphs, listed in `reports/phase1_meer_all_metrics.json`

This is a second opinion computed from the committed data as it landed on disk, not a re-read of P1-001's reported numbers. They agree, which is itself the finding: no drift between what the pipeline reported and what it wrote.

The `subject_family` gap is materially larger than the `entity_class` gap — a direct consequence of the derivation caveat above, not an extraction defect.

---

## 2. Week-2 cross-class alignment check (the 60% trigger)

_source: `reports/phase1_meer_checks_metrics.json`, written 2026-09-25T11:49:09+00:00_

- Entity classes sampled: ['All India Financial Institutions', 'Commercial Banks', 'Local Area Banks']
- Subject families sampled (**derived axis**): ['Know Your Customer', 'Miscellaneous', 'Asset Liability Management']
- Trigger threshold: **60%**
- Similarity threshold for counting a position as aligned: **0.5** Jaccard

### What 'aligned' means here, and a metric that had to be fixed

Alignment requires **same structural position AND lexical agreement**. An earlier version of this check counted two paragraphs as aligned when they merely shared a `clause_path`. That measured almost nothing: `clause_path` values in this corpus are overwhelmingly bare numbers (`1`, `2`, `3`) that every Direction has, so unrelated Directions scored as aligned by numbering coincidence. The flaw was caught because the false-positive baseline scored *higher* than the signal it was supposed to sit beneath — impossible if the metric were sound. Reporting that 83% as an alignment rate would have handed Phase 2 false confidence.

| Comparison | Paragraph level | Section level |
|---|---|---|
| **Parallel** (same subject, different entity classes — *should* align) | **0.3279** (n=738) | **0.2311** (n=541) |
| **Baseline** (same entity class, different subjects — should *not* align) | 0.0414 (n=604) | 0.0140 (n=573) |

The baseline row is what makes the headline number interpretable: a ~37% parallel rate against a ~5% baseline is real signal (roughly 8x separation), and is still far below the threshold.

### TRIGGER FIRED: **True**

> TRIGGER FIRED — paragraph-level alignment is 32.8%, BELOW the 60% threshold. Paragraph-level cross-class matching is NOT reliable on this evidence. Section-level alignment was measured as the dossier's suggested fallback and does NOT rescue it (23.1% vs 32.8% at paragraph level) — it is marginally more precise (lower false-positive baseline) but no more complete. Phase 2 should therefore NOT assume either structural level supports reliable one-to-one cross-class matching, and should treat semantic matching as load-bearing rather than as a refinement on top of a working structural match.

**Recommendation for Phase 2 (per Section AA):** do **not** proceed on the assumption that structural cross-class matching works. Paragraph-level alignment is well below the dossier's 60% bar, and section-level — the dossier's own suggested fallback — does not rescue it. Phase 2's cross-class matcher should treat semantic matching as load-bearing rather than as a refinement layered on a working structural match, and RQ2's differential-obligation claims should be scoped to what that matcher can actually demonstrate.

**Per-axis note:** the parallel comparison varies `entity_class` (raw-sourced) while holding the derived `subject_family` fixed. The sampled subject families are themselves inferred, so cell membership carries the derivation caveat — but the alignment being measured is between entity classes, on the raw-sourced axis.

---

## 3. Week-2 FAQ / enforcement source check

_source: `reports/phase1_meer_checks_metrics.json`, written 2026-09-25T11:49:09+00:00_

- FAQ items found: **0**
- FAQ paragraph-alignment rate: **NOT YET MEASURED**
- Enforcement items found: **0**
- Enforcement paragraph-alignment rate: **NOT YET MEASURED**

NOT YET MEASURED — P1-001 reported this sample as not trivially reachable (FAQView.aspx is a category index requiring a second-level crawl into per-category pages), so no sample was harvested and there is nothing to align. Systematic harvesting is Phase 2, Week 4 scope. No rate is fabricated in its absence.

**Standing rule:** FAQ and enforcement items are NOT treated as paragraph-level gold labels regardless of alignment outcome — they remain validation/motivation material only. This holds whether or not the sample exists.

---

## 4. Annotation protocol and tooling

Four rules are enforced **in code**, not by convention — each protects a research claim that cannot be repaired after the fact:

1. **`applies_to` is annotator-sourced or it does not exist.** It is written only by `apply_annotation()`, which requires an `annotator_id` and stamps `provenance='annotator:<id>:<route>'`. Any label with a non-empty `applies_to` lacking that provenance is rejected by `assert_applies_to_is_annotator_sourced()`, which runs on every promotion. A Phase 2 extractor cannot reintroduce the `applies_to = [entity_class]` tautology without deliberately forging annotator provenance. `tautology_share_by_rater()` additionally reports, per rater and pass, how often that rater landed on exactly the source class — a pattern that would drain RQ1 of signal even when every label is honestly sourced.
2. **`differential_flag` is never defaulted to `absent`.** It starts `unlabelled` by the schema's own default; only an ingested judgment moves it.
3. **Raw votes are never overwritten.** Every row of every pass becomes one immutable `AnnotatorVote`, and merging happens once over the whole vote set. The superseded ingest applied each annotator's row to the same label in turn, so the last writer won and κ was then computed by counting that single surviving flag once per annotator — three annotators who never agreed on anything scored κ = 1.0 and all 18 items were promoted.
4. **Promotion is by validation route, and never counts raters.** With one annotator there is nothing to count. `promote_validated()` gates on the route an item took, then defers to `T1Label.validate()`, which independently rejects a validated item with empty `applies_to` or a still-`unlabelled` flag.

**Validation routes** (recorded in `provenance`, one per item):

| Route | Status | Meaning |
|---|---|---|
| `retest-consistent` | `validated` | In the retest set; both blind passes gave identical `applies_to` and flag. |
| `single-pass` | `validated` | Outside the retest set; pass 1 only, and labelled as such. |
| `adjudicated` | `validated` / `rejected` | A disagreement resolved by written adjudication. |
| `not-obligation` | `rejected` | Judged not an obligation. |
| `pass1-only` | `in_review` | In the retest set; pass 2 not done yet. |
| `needs-adjudication` | `in_review` | The passes differ, or a second rater differs. |

**On the agreement statistic:** `T1Label.agreement_score` is typed `float | int | None` by the base schema, so it cannot hold the string `NOT YET MEASURED`; the literal string belongs to the reported metric, while the per-label field stays `None` until a real number exists. Neither is ever `0.0` — a zero κ is a real and very bad reading, not an absence of one.

**Data-loss guards:** task files, the pass-2 file and the adjudication file are never rewritten over filled-in cells without `--force-regenerate-tasks`, and even then the old file is copied to `data/benchmark/tasks/_overwritten/` first. `data/benchmark/**` is gitignored, so a blanked task file is not recoverable from anywhere. `report` reads existing artifacts and writes nothing under `data/benchmark/`.

---

## 5. Annotation feasibility pilot

_source: `reports/phase1_meer_all_metrics.json`, written 2026-08-23T11:49:46+00:00_

- Paragraphs searched: **20** (Task 5 range 15-20, widened in steps of 5 only if the item floor is unmet)
- Entity classes **in the paragraphs searched**: **16**
- Entity classes **in the extracted items**: **11** (requirement: more than one)
- Items missing `context_subject_family` (**derived** axis): **7**
  - _item-level figures from `data/benchmark/pilot_candidates.jsonl`, read live_
- Candidate `ObligationSpan`s extracted: **18** (floor: 10)
- Widening attempts: [{'paragraphs_searched': 20, 'items_extracted': 18}]
- Cue distribution: {'shall': 15, 'must': 2, 'are required to': 1}
- Task files generated: **3** (akash, karan, meer)

**The two entity-class counts above are different measurements and the difference is not cosmetic.** An earlier version of this report printed the paragraph-level count as "entity classes spanned", which overstated the benchmark's coverage: the search touched more classes than actually produced an annotatable item, because cue density varies by class.

Candidate generation is a **keyword heuristic and nothing more** — a feasibility device to test whether the protocol works on real RBI text. It is explicitly not the systematic Phase 2 (Week 4) extractor, and it is wrong in known ways: it catches definitional and commencement uses of "shall" alongside genuine obligations (a small reject-pattern list removes the most common), and has no notion of scope. `matched_cue` is recorded on every span precisely so this bias stays measurable — the distribution above is dominated by "shall", which is a property of the extractor, not of RBI.

### Annotation status and reliability

_source: `reports/phase1_annotation_ingest_metrics.json`, written 2026-09-25T07:03:33+00:00_

- Items total: **18**
- Retest set size (drawn before pass 1 was filled): **18**
- Rows voted in pass 1: **51**
- Rows voted in pass 2: **0**
- Rows marked not-an-obligation: **3**
- Items reaching `validated`: **11**

#### Items per validation route

| Route | Items |
|---|---|
| `consensus` | 11 |
| `not-obligation` | 1 |
| `needs-adjudication` | 6 |

#### Inter-rater agreement — independent human raters

Unlike the test-retest block below, **this is genuine inter-rater agreement**: different people labelling the same items. Each rater's pass 1 is used, so no pair is contaminated by the retest.

**akash vs karan**

- Items compared (a `voted` row on both sides): **17**
- Cohen's κ (differential_flag): **0.6264** (n=17)
- Cohen's κ excluding `unlabelled`: **0.6264** (n=17)
- 95% bootstrap CI for κ: **[0.3014, 0.9045] (1000 resamples used, 0 skipped as undefined)**
- Raw flag agreement: **0.7647** (the chance-uncorrected baseline κ is measured against)
- `applies_to` exact set match: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- `applies_to` mean Jaccard: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- Not-obligation consistency: **1.0000** (n=18 items decided on both sides)
- Disagreement categories: `flag_only`=4, `applies_to_only`=0, `both`=0, `none`=13

**akash vs meer**

- Items compared (a `voted` row on both sides): **17**
- Cohen's κ (differential_flag): **0.4620** (n=17)
- Cohen's κ excluding `unlabelled`: **0.4620** (n=17)
- 95% bootstrap CI for κ: **[-0.0338, 0.8172] (1000 resamples used, 0 skipped as undefined)**
- Raw flag agreement: **0.7059** (the chance-uncorrected baseline κ is measured against)
- `applies_to` exact set match: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- `applies_to` mean Jaccard: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- Not-obligation consistency: **1.0000** (n=18 items decided on both sides)
- Disagreement categories: `flag_only`=5, `applies_to_only`=0, `both`=0, `none`=12

**karan vs meer**

- Items compared (a `voted` row on both sides): **17**
- Cohen's κ (differential_flag): **0.7198** (n=17)
- Cohen's κ excluding `unlabelled`: **0.7198** (n=17)
- 95% bootstrap CI for κ: **[0.3866, 1.0000] (1000 resamples used, 0 skipped as undefined)**
- Raw flag agreement: **0.8235** (the chance-uncorrected baseline κ is measured against)
- `applies_to` exact set match: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- `applies_to` mean Jaccard: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- Not-obligation consistency: **1.0000** (n=18 items decided on both sides)
- Disagreement categories: `flag_only`=3, `applies_to_only`=0, `both`=0, `none`=14

- **Fleiss' κ over 3 human raters (akash, karan, meer): 0.6026** (n=17 items every rater voted on)

- **Is-it-an-obligation agreement: 1.0000** (n=18; unanimous obligation 17, unanimous not-an-obligation 1, split 0). This measures candidate precision — whether the keyword heuristic surfaced a real obligation — which is the question the pilot is best placed to answer.

**Test-retest — karan pass 1 vs karan blind pass 2 (stability of ONE annotator's judgment over time, NOT inter-annotator agreement)**

- NOT YET MEASURED — pass 2 has not been ingested; run `retest` on or after the earliest allowed date, then `ingest --pass 2`

**Second rater — karan pass 1 vs akash**

- Items compared (a `voted` row on both sides): **17**
- Cohen's κ (differential_flag): **0.6264** (n=17)
- Cohen's κ excluding `unlabelled`: **0.6264** (n=17)
- 95% bootstrap CI for κ: **[0.3014, 0.9045] (1000 resamples used, 0 skipped as undefined)**
- Raw flag agreement: **0.7647** (the chance-uncorrected baseline κ is measured against)
- `applies_to` exact set match: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- `applies_to` mean Jaccard: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- Not-obligation consistency: **1.0000** (n=18 items decided on both sides)
- Disagreement categories: `flag_only`=4, `applies_to_only`=0, `both`=0, `none`=13

**Second rater — karan pass 1 vs meer**

- Items compared (a `voted` row on both sides): **17**
- Cohen's κ (differential_flag): **0.7198** (n=17)
- Cohen's κ excluding `unlabelled`: **0.7198** (n=17)
- 95% bootstrap CI for κ: **[0.3866, 1.0000] (1000 resamples used, 0 skipped as undefined)**
- Raw flag agreement: **0.8235** (the chance-uncorrected baseline κ is measured against)
- `applies_to` exact set match: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- `applies_to` mean Jaccard: **NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every rater's file. Each rater judged differential_flag only, so there is nothing to agree about here and the exact-match rate would read 1.0 by construction.**
- Not-obligation consistency: **1.0000** (n=18 items decided on both sides)
- Disagreement categories: `flag_only`=3, `applies_to_only`=0, `both`=0, `none`=14

> **Fleiss' κ is absent by design.** It requires three or more raters. With one annotator, or one annotator plus one second rater, the tooling emits no `fleiss` key at all — not even a sentinel — so nothing downstream can surface a number that was never computable.

#### Annotation time

| Rater and pass | Voted | Blank | Not obligation | Minutes | Minutes/item |
|---|---|---|---|---|---|
| `akash:pass1` | 17 | 0 | 1 | 45.0 | 2.50 |
| `karan:pass1` | 17 | 0 | 1 | 65.0 | 3.61 |
| `meer:pass1` | 17 | 0 | 1 | 50.0 | 2.78 |

#### Phase 2 sizing — a PROJECTION, not a measurement

`N_target = (hours x 60) / (minutes_per_item x (1 + r))`, with `r = 0.2` (`benchmark.retest.phase2_fraction`) covering the fraction of Phase 2 items that get a second, blind pass.

- Measured minutes per item: **2.96**
- At 10 annotation hours: **N_target ≈ 168 items**
- At 20 annotation hours: **N_target ≈ 337 items**
- At 30 annotation hours: **N_target ≈ 506 items**

#### Pass-2 schedule

- Minimum gap: **5 days** (`benchmark.retest.min_gap_days`)
- Pass-1 ingested at: **2026-09-25T07:03:33.733164+00:00**
- Earliest allowed pass-2 date: **2026-09-30T07:03:33+00:00**
- Pass 2 actually ingested at: **NOT YET MEASURED**

#### Tautology share, per rater and pass

| Rater and pass | Voted rows | `applies_to` == source class | Share |
|---|---|---|---|
| `akash:pass1` | 17 | 3 | 0.1765 |
| `karan:pass1` | 17 | 3 | 0.1765 |
| `meer:pass1` | 17 | 3 | 0.1765 |

A share near 1.0 would mean the annotator was effectively copying `context_entity_class` into `applies_to`, which drains RQ1 of signal even when every label is honestly sourced. It is reported, never enforced.

The ingestion path, the retest and adjudication stages, the promotion gates and the κ computations are implemented and tested end-to-end against fixture annotations (see `tests/test_benchmark_solo_protocol.py` and `tests/test_benchmark_integration.py`) — what is pending is human input, not code.
