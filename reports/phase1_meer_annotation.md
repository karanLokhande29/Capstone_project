# Phase 1 — Meer: Corpus QA, Annotation Pilot, Validation Protocol

> **Protocol change.** From 2026-09-24 this project has a single annotator (karan). The three-annotator roster this report was originally written against no longer exists, so **inter-annotator agreement is not a statistic this project can produce.** Reliability evidence comes instead from a blind test-retest by the primary annotator and, where a second rater is obtainable, a second-rater comparison. Every figure in §5 is labelled by which of those it is. Fleiss' κ is not reported at all below three real raters.

---

## Derived-axis caveat (read before any `subject_family` stratification)

`subject_family` on every `DocumentRecord`/`ParagraphRecord` is a **derived** value, not one harvested from RBI's own listing: RBI publishes no subject-family taxonomy at discovery time, so P1-002 inferred it by stripping the known `entity_class_raw` string out of each title (P1-002-CORRECTIVE, commit `e4013ca`). `entity_class`, by contrast, is raw-sourced with a 0% unresolved rate.

**The two axes do not carry equal evidentiary weight, and nothing in this report treats them as if they did.** Every figure below that involves `subject_family` is marked accordingly. Provenance is queryable from the data itself (`data/metadata/vocabulary_provenance.json`), not only from prose.

---

## 1. Corpus QA (independent of P1-001's own metrics)

_source: `reports/phase1_meer_all_metrics.json`, written 2026-08-23T11:49:46+00:00_

- Paragraphs checked: **51853** across **299** documents
- Missing `section_id`: **340** (**0.0066**)
- Missing `clause_path`: **340** (**0.0066**)
- Duplicate `paragraph_id`s: **0**
- Empty text: **0**
- Missing `source_url`: **0**
- Missing `entity_class` (raw-sourced axis): **0** (**0.0000**)
- Missing `subject_family` (**derived** axis): **8008** (**0.1544**)
- Records re-validated against `ParagraphRecord` schema: **500**, failing: **0**
- Spot-check sample drawn (for manual comparison against `source_url`): **10** paragraphs, listed in `reports/phase1_meer_all_metrics.json`

This is a second opinion computed from the committed data as it landed on disk, not a re-read of P1-001's reported numbers. They agree, which is itself the finding: no drift between what the pipeline reported and what it wrote.

The `subject_family` gap is materially larger than the `entity_class` gap — a direct consequence of the derivation caveat above, not an extraction defect.

---

## 2. Week-2 cross-class alignment check (the 60% trigger)

_source: `reports/phase1_meer_all_metrics.json`, written 2026-08-23T11:49:46+00:00_

- Entity classes sampled: ['All India Financial Institutions', 'Local Area Banks', 'Non-Banking Financial Companies']
- Subject families sampled (**derived axis**): ['Miscellaneous', 'Fraud Risk Management', 'Know Your Customer']
- Trigger threshold: **60%**
- Similarity threshold for counting a position as aligned: **0.5** Jaccard

### What 'aligned' means here, and a metric that had to be fixed

Alignment requires **same structural position AND lexical agreement**. An earlier version of this check counted two paragraphs as aligned when they merely shared a `clause_path`. That measured almost nothing: `clause_path` values in this corpus are overwhelmingly bare numbers (`1`, `2`, `3`) that every Direction has, so unrelated Directions scored as aligned by numbering coincidence. The flaw was caught because the false-positive baseline scored *higher* than the signal it was supposed to sit beneath — impossible if the metric were sound. Reporting that 83% as an alignment rate would have handed Phase 2 false confidence.

| Comparison | Paragraph level | Section level |
|---|---|---|
| **Parallel** (same subject, different entity classes — *should* align) | **0.3650** (n=811) | **0.3420** (n=614) |
| **Baseline** (same entity class, different subjects — should *not* align) | 0.0470 (n=596) | 0.0236 (n=592) |

The baseline row is what makes the headline number interpretable: a ~37% parallel rate against a ~5% baseline is real signal (roughly 8x separation), and is still far below the threshold.

### TRIGGER FIRED: **True**

> TRIGGER FIRED — paragraph-level alignment is 36.5%, BELOW the 60% threshold. Paragraph-level cross-class matching is NOT reliable on this evidence. Section-level alignment was measured as the dossier's suggested fallback and does NOT rescue it (34.2% vs 36.5% at paragraph level) — it is marginally more precise (lower false-positive baseline) but no more complete. Phase 2 should therefore NOT assume either structural level supports reliable one-to-one cross-class matching, and should treat semantic matching as load-bearing rather than as a refinement on top of a working structural match.

**Recommendation for Phase 2 (per Section AA):** do **not** proceed on the assumption that structural cross-class matching works. Paragraph-level alignment is well below the dossier's 60% bar, and section-level — the dossier's own suggested fallback — does not rescue it. Phase 2's cross-class matcher should treat semantic matching as load-bearing rather than as a refinement layered on a working structural match, and RQ2's differential-obligation claims should be scoped to what that matcher can actually demonstrate.

**Per-axis note:** the parallel comparison varies `entity_class` (raw-sourced) while holding the derived `subject_family` fixed. The sampled subject families are themselves inferred, so cell membership carries the derivation caveat — but the alignment being measured is between entity classes, on the raw-sourced axis.

---

## 3. Week-2 FAQ / enforcement source check

_source: `reports/phase1_meer_all_metrics.json`, written 2026-08-23T11:49:46+00:00_

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

_no ingest has run: `reports/phase1_annotation_ingest_metrics.json` does not exist_

- Items total: **18**
- Retest set size (drawn before pass 1 was filled): **18**
- Rows voted in pass 1: **NOT YET MEASURED**
- Rows voted in pass 2: **NOT YET MEASURED**
- Rows marked not-an-obligation: **NOT YET MEASURED**
- Items reaching `validated`: **NOT YET MEASURED**

#### Items per validation route

- NOT YET MEASURED — no pass has been ingested.

**Test-retest — karan pass 1 vs karan blind pass 2 (stability of ONE annotator's judgment over time, NOT inter-annotator agreement)**

- NOT YET MEASURED

**Second rater**

- NOT YET MEASURED — no second rater configured

> **Fleiss' κ is absent by design.** It requires three or more raters. With one annotator, or one annotator plus one second rater, the tooling emits no `fleiss` key at all — not even a sentinel — so nothing downstream can surface a number that was never computable.

#### Annotation time

- NOT YET MEASURED — no pass has been ingested.

#### Phase 2 sizing — a PROJECTION, not a measurement

`N_target = (hours x 60) / (minutes_per_item x (1 + r))`, with `r = 0.2` (`benchmark.retest.phase2_fraction`) covering the fraction of Phase 2 items that get a second, blind pass.

- Minutes per item: **NOT YET MEASURED** — no timed pass has been ingested, so `N_target` cannot be projected. Nothing is substituted for it: a guessed rate here becomes a badly wrong Phase 2 schedule later.

#### Pass-2 schedule

- Minimum gap: **5 days** (`benchmark.retest.min_gap_days`)
- Pass-1 ingested at: **NOT YET MEASURED**
- Earliest allowed pass-2 date: **NOT YET MEASURED — pass 1 has not been ingested**
- Pass 2 actually ingested at: **NOT YET MEASURED**

#### Tautology share, per rater and pass

- NOT YET MEASURED — no pass has been ingested.

> **NOT YET MEASURED: the pilot is generated and ready, not yet annotated.** The pass-1 task file for karan exists under `data/benchmark/tasks/`, carrying every pilot item, and the retest set has been drawn in advance. Test-retest κ, annotation time and disagreement categories cannot be reported until karan completes pass 1, waits 5 days, and completes the blind pass 2. **No annotations were fabricated and no placeholder agreement value was substituted** — a synthesised κ would be worse than no κ, because it would look like evidence.

The ingestion path, the retest and adjudication stages, the promotion gates and the κ computations are implemented and tested end-to-end against fixture annotations (see `tests/test_benchmark_solo_protocol.py` and `tests/test_benchmark_integration.py`) — what is pending is human input, not code.
