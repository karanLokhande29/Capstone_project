# Weeks 1–5 Consolidated Summary — RBI-ObliBench / Corpus Pipeline

## 1. What was actually built and run

Implemented the Week 1–5 engineering pipeline for corpus harvesting and the
T1 **candidate** benchmark construction supporting RBI-ObliBench research.
Agentic RAG / retrieval systems were **not** implemented (correctly deferred).

- Week 1: RBI Master Directions scraper (discover + cached download), metadata schema, Matrix v0
- Week 2: extraction pilot, temporal extractor, alignment risk, FAQ/enforcement check, licensing note, annotation process pilot
- Week 3: full-corpus extract/segment, cross-references, Matrix v1
- Week 4: supplementary harvest, deontic candidates, cross-class matcher, T1 candidates
- Week 5: stratified validation sample, annotation templates for Akash/Karan/Meer, validated file (empty until real labels)

## 2. Metrics table (actual)

| Week | Metric | Value |
|------|--------|-------|
| 1 | documents_discovered | 381 |
| 1 | urls_discovered | 381 |
| 1 | downloads_attempted | 381 |
| 1 | downloads_successful | 381 |
| 1 | downloads_failed | 0 |
| 1 | download_success_rate | 1.0 |
| 1 | pdf_count | 381 |
| 1 | html_count | 0 |
| 1 | duplicate_count | 2 |
| 1 | extraction_readiness_openable | 381 |
| 1 | matrix_v0_row_count | 381 |
| 1 | distinct_entity_classes_raw | 23 |
| 1 | distinct_subject_families_raw | 134 |
| 2 | extraction_success_rate_pilot | 1.0 |
| 2 | temporal_metadata_coverage_pilot | 0.26666666666666666 |
| 2 | cross_class_alignment_rate | 0.9224562216010344 |
| 2 | faq_paragraph_alignment_rate | 0.0 |
| 2 | enforcement_paragraph_alignment_rate | 0.0 |
| 2 | annotation_pilot_item_count | 12 |
| 2 | annotation_pilot_avg_time_per_item_seconds | NOT YET MEASURED |
| 3 | total_documents_discovered | 381 |
| 3 | downloads_successful | 381 |
| 3 | downloads_failed | 0 |
| 3 | total_paragraphs_extracted | 16298 |
| 3 | extraction_failures | 0 |
| 3 | malformed_documents | 0 |
| 3 | cross_reference_count | 1851 |
| 3 | entity_classes_discovered | 23 |
| 3 | subject_families_discovered | 135 |
| 3 | matrix_cells_populated | 380 |
| 3 | matrix_cells_missing | 2725 |
| 3 | duplicate_mappings_count | 1 |
| 3 | ambiguous_mappings_count | 3 |
| 3 | matrix_coverage | 0.12238325281803543 |
| 4 | supplementary_documents_harvested | {"faq": 40, "enforcement": 40, "circulars_withdrawn": 5, "amendments": 40} |
| 4 | candidate_obligation_spans | 68281 |
| 4 | candidate_rejection_rate | 0.014803699482014803 |
| 4 | cross_class_candidate_matches | 928 |
| 4 | matches_by_differential_flag | {"shared": 880, "absent": 39, "class-specific": 9} |
| 4 | match_level_used | paragraph |
| 4 | t1_candidate_count | 68281 |
| 5 | candidate_pool_size | 68281 |
| 5 | stratified_validation_sample_size | 30 |
| 5 | items_annotated_by_ge_2 | 0 |
| 5 | fleiss_kappa | NOT YET MEASURED — annotation not yet completed |
| 5 | validated_benchmark_size | 0 |
| 5 | ambiguity_rate_proxy_absent_share | 0.9342423221686853 |

## 3. NOT YET MEASURED / FAILED

### NOT YET MEASURED

- w2.annotation_pilot_avg_time_per_item_seconds: NOT YET MEASURED
- w5.fleiss_kappa: NOT YET MEASURED — annotation not yet completed

### FAILED

- (none found as literal FAILED strings in walked metrics)

## 4. Cross-class alignment rate and <60% fallback

- Alignment rate: **0.9224562216010344**
- Fallback triggered (<60%): **False**
- Match level used in Week 4: **paragraph**
- Detail: `reports/week2_alignment_risk.md`

## 5. FAQ / enforcement paragraph-alignment findings

- FAQ rate: **0.0**
- Enforcement rate: **0.0**
- Detail: `reports/week2_faq_enforcement_check.md`

## 6. T1 candidate vs validated state

- Candidate pool size: **68281**
- Stratified validation sample: **30**
- Validated benchmark size: **0**
- Fleiss' kappa: **NOT YET MEASURED — annotation not yet completed**
- Candidate file: `data/benchmark/candidate/t1_candidates.csv`
- Validated file: `data/benchmark/validated/t1_validated.csv` (headers only until real multi-annotator labels exist)
- Annotation templates: `data/benchmark/validated/annotation_templates/`

## 7. What's next (description only — not implemented)

- **Week 6:** T4 RePASs metric-integrity audit on Indian regulatory text.
- **Week 7:** BM25 / dense / hybrid retrieval baselines on RBI-ObliBench.

No Week 6+ code was implemented in this run.
