# Phase 1 — Meer: Corpus QA, Annotation Pilot, Validation Protocol

---

## Derived-axis caveat (read before any `subject_family` stratification)

`subject_family` on every `DocumentRecord`/`ParagraphRecord` is a **derived** value, not one harvested from RBI's own listing: RBI publishes no subject-family taxonomy at discovery time, so P1-002 inferred it by stripping the known `entity_class_raw` string out of each title (P1-002-CORRECTIVE, commit `e4013ca`). `entity_class`, by contrast, is raw-sourced with a 0% unresolved rate.

**The two axes do not carry equal evidentiary weight, and nothing in this report treats them as if they did.** Every figure below that involves `subject_family` is marked accordingly. Provenance is queryable from the data itself (`data/metadata/vocabulary_provenance.json`), not only from prose.

---

## 1. Corpus QA (independent of P1-001's own metrics)

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

- FAQ items found: **0**
- FAQ paragraph-alignment rate: **NOT YET MEASURED**
- Enforcement items found: **0**
- Enforcement paragraph-alignment rate: **NOT YET MEASURED**

NOT YET MEASURED — P1-001 reported this sample as not trivially reachable (FAQView.aspx is a category index requiring a second-level crawl into per-category pages), so no sample was harvested and there is nothing to align. Systematic harvesting is Phase 2, Week 4 scope. No rate is fabricated in its absence.

**Standing rule:** FAQ and enforcement items are NOT treated as paragraph-level gold labels regardless of alignment outcome — they remain validation/motivation material only. This holds whether or not the sample exists.

---

## 4. Annotation protocol and tooling

Three rules are enforced **in code**, not by convention — each protects a research claim that cannot be repaired after the fact:

1. **`applies_to` is annotator-sourced or it does not exist.** It is written only by `apply_annotation()`, which requires an `annotator_id` and stamps `provenance='annotator:<id>'`. Any label with a non-empty `applies_to` lacking that provenance is rejected by `assert_applies_to_is_annotator_sourced()`, which runs on every promotion. A Phase 2 extractor cannot reintroduce the `applies_to = [entity_class]` tautology without deliberately forging annotator provenance. A corpus-level `tautology_smell_report()` additionally reports how often annotators land on exactly the source class — a pattern that would drain RQ1 of signal even when every label is honestly sourced.
2. **`differential_flag` is never defaulted to `absent`.** It starts `unlabelled` by the schema's own default; only an ingested annotator judgment moves it.
3. **Promotion is never implicit.** `promote_validated()` requires `min_annotators_per_item` *distinct* annotators, then defers to `T1Label.validate()`, which independently rejects a validated item with empty `applies_to` or a still-`unlabelled` flag. An item failing any gate stays where it is.

**On the agreement statistic:** `T1Label.agreement_score` is typed `float | int | None` by the base schema, so it cannot hold the string `NOT YET MEASURED`; the literal string belongs to the reported metric from `measure_agreement()`, while the per-label field stays `None` until a real number exists. Neither is ever `0.0` — a zero kappa is a real and very bad agreement reading, not an absence of one.

---

## 5. Annotation feasibility pilot

- Paragraphs searched: **20** (Task 5 range 15-20, widened in steps of 5 only if the item floor is unmet)
- Entity classes spanned: **16** (requirement: more than one)
- Candidate `ObligationSpan`s extracted: **18** (floor: 10)
- Widening attempts: [{'paragraphs_searched': 20, 'items_extracted': 18}]
- Cue distribution: {'shall': 15, 'must': 2, 'are required to': 1}
- Task files generated: **3** (akash, karan, meer)

Candidate generation is a **keyword heuristic and nothing more** — a feasibility device to test whether the protocol works on real RBI text. It is explicitly not the systematic Phase 2 (Week 4) extractor, and it is wrong in known ways: it catches definitional and commencement uses of "shall" alongside genuine obligations (a small reject-pattern list removes the most common), and has no notion of scope. `matched_cue` is recorded on every span precisely so this bias stays measurable — the distribution above is dominated by "shall", which is a property of the extractor, not of RBI.

### Inter-annotator agreement

- Items total: **18**
- Items reaching `validated`: **0**
- Fleiss' kappa (differential_flag): **NOT YET MEASURED**
- Annotation time: **NOT YET MEASURED** (measured by annotators during the pilot run)
- Disagreement categories: **NOT YET MEASURED** (derived from completed annotations)

> **NOT YET MEASURED: the pilot is generated and ready, not yet annotated.** Task files for all three annotators exist under `data/benchmark/tasks/`, each carrying every pilot item (full overlap, which is what makes an agreement statistic computable at this scale). Fleiss' kappa, annotation time, and disagreement categories cannot be reported until Akash, Karan and Meer complete those files and `run_annotation.py ingest` is run. **No annotations were fabricated and no placeholder agreement value was substituted** — a synthesised kappa would be worse than no kappa, because it would look like evidence.

The ingestion path, promotion gates, and kappa computation are fully implemented and tested end-to-end against fixture annotations (see `tests/test_benchmark_annotation.py` and `tests/test_benchmark_integration.py`) — what is pending is human input, not code.
