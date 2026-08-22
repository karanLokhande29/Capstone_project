# Week 5 — T1 Benchmark Summary

## Candidate pool

- Candidate pool size: see `reports/week5_metrics.json` → `candidate_pool_size`
- Source: `data/benchmark/candidate/t1_candidates.csv` (all rows labeled `label_status=candidate`)
- Per-class and per-differential_flag distributions: `reports/week5_metrics.json`

## Stratified validation sample

- Sample size and rationale: `reports/week5_metrics.json` → `stratified_validation_sample_size`, `sample_size_rationale`
- Sample file: `data/benchmark/candidate/t1_validation_sample.csv`
- Annotation templates (independent): `data/benchmark/validated/annotation_templates/annotation_{akash,karan,meer}.csv`
- Instructions: `data/benchmark/validated/annotation_instructions.md`

## Validation status

- Validated benchmark: `data/benchmark/validated/t1_validated.csv` — **empty (headers only)** until multi-annotator labels are completed
- Fleiss' kappa: **NOT YET MEASURED — annotation not yet completed**
- Items independently annotated by ≥2 annotators: **0**

## Notes

Candidate items must not be treated as gold. Complete independent annotations into the
three template CSVs, then re-run kappa computation via
`src.benchmark.stratified_sampler.try_compute_kappa_from_annotations`.
