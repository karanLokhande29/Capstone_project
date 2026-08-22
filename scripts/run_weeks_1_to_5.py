#!/usr/bin/env python3
"""Orchestrate Weeks 1–5 end-to-end with honest metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import load_config, resolve_path, setup_logging
from src.scraper.rbi_scraper import RBIScraper, build_matrix_v0, DiscoveredDocument
from src.scraper.supplementary import SupplementaryHarvester
from src.extraction.text_extractor import TextExtractor
from src.metadata.temporal_extractor import TemporalExtractor
from src.metadata.week2_checks import Week2RiskChecks
from src.preprocessing.segmenter import Segmenter
from src.preprocessing.cross_references import CrossReferenceDetector
from src.matrix.matrix_builder import MatrixBuilder
from src.benchmark.deontic_extractor import DeonticExtractor
from src.benchmark.cross_class_matcher import CrossClassMatcher
from src.benchmark.t1_candidate_builder import T1CandidateBuilder
from src.benchmark.stratified_sampler import StratifiedSampler, try_compute_kappa_from_annotations


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    cfg = load_config()
    log = setup_logging("pipeline.weeks1to5", cfg)
    reports = resolve_path(cfg, "reports")
    meta = resolve_path(cfg, "metadata")

    # ---------- WEEK 1 ----------
    log.info("=== WEEK 1: scrape + matrix v0 ===")
    scraper = RBIScraper(cfg)
    # Discover full catalog first; download all (resumable). Rate-limited.
    w1_metrics = scraper.run(limit=None)
    catalog = json.loads((meta / "discovered_documents.json").read_text(encoding="utf-8"))
    docs = [
        DiscoveredDocument(**{k: v for k, v in row.items() if k in DiscoveredDocument.__dataclass_fields__})
        for row in catalog
    ]
    matrix_v0 = build_matrix_v0(docs=docs, config=cfg)
    import pandas as pd

    m0 = pd.read_csv(matrix_v0)
    w1_metrics.update(
        {
            "matrix_v0_row_count": int(len(m0)),
            "distinct_entity_classes_found_raw": int(m0["entity_class"].nunique()),
            "distinct_subject_families_found_raw": int(m0["subject_family_raw"].nunique()),
            "matrix_v0_path": str(matrix_v0),
            "pass_criterion_notes": (
                "PASS if scraper ran, count discovered (not hard-coded), matrix non-empty. "
                "Download success rate reported honestly even if <90%."
            ),
        }
    )
    if w1_metrics["downloads_attempted"]:
        w1_metrics["download_success_rate"] = (
            w1_metrics["downloads_successful"] / w1_metrics["downloads_attempted"]
        )
    else:
        w1_metrics["download_success_rate"] = "FAILED — no downloads attempted"
    save_json(reports / "week1_metrics.json", w1_metrics)

    # ---------- WEEK 2 ----------
    log.info("=== WEEK 2: extraction pilot + risk checks ===")
    pilot_n = int(cfg.get("extraction", {}).get("pilot_size", 15))
    # Prefer Nov 2025 consolidation-era docs if identifiable; else first N successful
    pilot_ids = [
        r.document_id for r in scraper.manifest if r.download_status in {"success", "cached"}
    ][:pilot_n]
    extract_metrics = TextExtractor(cfg).run_from_manifest(document_ids=pilot_ids, limit=pilot_n)
    # Segment pilot for alignment check
    # Ensure temporal on pilot
    temporal_metrics = TemporalExtractor(cfg).run(document_ids=pilot_ids)

    # Need paragraphs for alignment — segment pilot texts
    from src.preprocessing.segmenter import Segmenter as Seg

    # Temporarily segment whatever extracted exists (pilot)
    seg_partial = Seg(cfg).run()

    checks = Week2RiskChecks(cfg)
    # Harvest a small supplementary set early so FAQ check has something to align
    try:
        supp_early = SupplementaryHarvester(cfg).run(per_source_limit=35)
    except Exception as exc:  # noqa: BLE001
        supp_early = {"supplementary_documents_harvested": {}, "error": f"FAILED — {exc}"}
        log.error("Early supplementary harvest failed: %s", exc)

    align = checks.cross_class_alignment_risk()
    faq_enf = checks.faq_enforcement_alignment_check(max_items=30)
    ann = checks.annotation_feasibility_pilot(n_items=12)
    lic = checks.write_licensing_note()

    w2_metrics = {
        "extraction_success_rate_pilot": extract_metrics.get("extraction_success_rate"),
        "extraction_pilot": extract_metrics,
        "temporal_metadata_coverage_pilot": temporal_metrics.get("temporal_coverage_rate"),
        "temporal_pilot": temporal_metrics,
        "cross_class_alignment_rate": align.get("alignment_rate"),
        "alignment_fallback_triggered": align.get("triggered_fallback_flag"),
        "faq_paragraph_alignment_rate": faq_enf.get("faq", {}).get("paragraph_alignment_rate"),
        "enforcement_paragraph_alignment_rate": faq_enf.get("enforcement", {}).get(
            "paragraph_alignment_rate"
        ),
        "faq_enforcement_check": faq_enf,
        "annotation_pilot_item_count": ann.get("annotation_pilot_item_count"),
        "annotation_pilot_avg_time_per_item_seconds": ann.get("average_time_per_item_seconds"),
        "licensing_note_path": lic,
        "early_supplementary": supp_early,
        "pilot_segmentation_note": seg_partial,
    }
    save_json(reports / "week2_metrics.json", w2_metrics)

    # ---------- WEEK 3 ----------
    log.info("=== WEEK 3: full extract + segment + matrix v1 ===")
    # Ensure full downloads already done in week1; re-run scraper for resume
    w3_scrape = scraper.run(limit=None)
    full_extract = TextExtractor(cfg).run_from_manifest(limit=None)
    # Temporal full
    temporal_full = TemporalExtractor(cfg).run(limit=None)
    seg_metrics = Segmenter(cfg).run()
    xref_metrics = CrossReferenceDetector(cfg).run()
    matrix_metrics = MatrixBuilder(cfg).build_v1()

    w3_metrics = {
        "total_documents_discovered": w3_scrape.get("documents_discovered"),
        "downloads_successful": w3_scrape.get("downloads_successful"),
        "downloads_failed": w3_scrape.get("downloads_failed"),
        "full_extraction": full_extract,
        "total_paragraphs_extracted": seg_metrics.get("total_paragraphs"),
        "extraction_failures": full_extract.get("extraction_failed"),
        "malformed_documents": seg_metrics.get("malformed_documents"),
        "cross_reference_count": xref_metrics.get("cross_reference_count"),
        **{k: matrix_metrics[k] for k in [
            "entity_classes_discovered",
            "subject_families_discovered",
            "matrix_cells_populated",
            "matrix_cells_missing",
            "duplicate_mappings_count",
            "ambiguous_mappings_count",
            "matrix_coverage",
        ]},
        "temporal_full_coverage": temporal_full.get("temporal_coverage_rate"),
    }
    save_json(reports / "week3_metrics.json", w3_metrics)

    # ---------- WEEK 4 ----------
    log.info("=== WEEK 4: supplementary + deontic + T1 candidates ===")
    try:
        supp = SupplementaryHarvester(cfg).run(per_source_limit=40)
    except Exception as exc:  # noqa: BLE001
        supp = {
            "supplementary_documents_harvested": {},
            "error": f"FAILED — {exc}",
        }
    deontic = DeonticExtractor(cfg).run()
    align_rate = align.get("alignment_rate")
    align_f = align_rate if isinstance(align_rate, float) else None
    matcher = CrossClassMatcher(cfg)
    match_metrics = matcher.run(alignment_rate=align_f)
    t1 = T1CandidateBuilder(cfg).run()

    w4_metrics = {
        "supplementary_documents_harvested": supp.get("supplementary_documents_harvested"),
        "candidate_obligation_spans_extracted": deontic.get("candidate_obligation_spans"),
        "candidate_rejection_rate": deontic.get("candidate_rejection_rate"),
        "cross_class_candidate_matches": match_metrics.get("cross_class_candidate_matches"),
        "matches_by_differential_flag": match_metrics.get("matches_by_differential_flag"),
        "match_level_used": match_metrics.get("match_level_used"),
        "t1_candidate_count": t1.get("t1_candidate_count"),
        "t1": t1,
        "deontic": deontic,
        "supplementary": supp,
    }
    save_json(reports / "week4_metrics.json", w4_metrics)

    # ---------- WEEK 5 ----------
    log.info("=== WEEK 5: stratified sample + validation infrastructure ===")
    sampler = StratifiedSampler(cfg)
    sample_metrics = sampler.sample()
    kappa_info = try_compute_kappa_from_annotations(resolve_path(cfg, "benchmark_validated"))

    # Distributions from candidates
    cand_csv = resolve_path(cfg, "benchmark_candidate") / "t1_candidates.csv"
    dist_class = {}
    dist_flag = {}
    ambiguity_rate = "NOT YET MEASURED"
    if cand_csv.exists():
        cdf = pd.read_csv(cand_csv)
        dist_class = cdf["entity_class"].value_counts().to_dict() if len(cdf) else {}
        dist_flag = cdf["differential_flag"].value_counts().to_dict() if len(cdf) else {}
        if len(cdf):
            # Ambiguity proxy: absent flag share among candidates
            ambiguity_rate = float((cdf["differential_flag"] == "absent").mean())

    w5_metrics = {
        "candidate_pool_size": sample_metrics.get("candidate_pool_size"),
        "stratified_validation_sample_size": sample_metrics.get("stratified_validation_sample_size"),
        "sample_size_rationale": sample_metrics.get("sample_size_rationale"),
        "items_independently_annotated_by_ge_2": kappa_info.get("items_annotated_by_ge_2"),
        "fleiss_kappa": kappa_info.get("fleiss_kappa"),
        "disagreement_categories": kappa_info.get("disagreement_categories"),
        "validated_benchmark_size": sample_metrics.get("validated_count"),
        "per_class_distribution_candidate": dist_class,
        "per_differential_flag_distribution_candidate": dist_flag,
        "ambiguity_rate_proxy_absent_share": ambiguity_rate,
    }
    save_json(reports / "week5_metrics.json", w5_metrics)

    # Summary markdown
    summary = reports / "weeks_1_to_5_summary.md"
    _write_summary(summary, w1_metrics, w2_metrics, w3_metrics, w4_metrics, w5_metrics)
    log.info("Wrote consolidated summary -> %s", summary)
    return 0


def _write_summary(path: Path, w1, w2, w3, w4, w5) -> None:
    def fmt(v):
        return v if isinstance(v, (int, float, str)) else json.dumps(v, ensure_ascii=False)

    not_measured = []
    failed = []

    def collect(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                collect(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                collect(v, f"{prefix}[{i}]")
        elif isinstance(obj, str):
            if obj.startswith("NOT YET MEASURED"):
                not_measured.append(f"{prefix}: {obj}")
            elif obj.startswith("FAILED"):
                failed.append(f"{prefix}: {obj}")

    for label, blob in [("w1", w1), ("w2", w2), ("w3", w3), ("w4", w4), ("w5", w5)]:
        collect(blob, label)

    align = w2.get("cross_class_alignment_rate")
    triggered = w2.get("alignment_fallback_triggered")
    lines = [
        "# Weeks 1–5 Consolidated Summary — RBI-ObliBench / Corpus Pipeline",
        "",
        "## 1. What was actually built and run",
        "",
        "Implemented the Week 1–5 engineering pipeline for corpus harvesting and the",
        "T1 **candidate** benchmark construction supporting RBI-ObliBench research.",
        "Agentic RAG / retrieval systems were **not** implemented (correctly deferred).",
        "",
        "- Week 1: RBI Master Directions scraper (discover + cached download), metadata schema, Matrix v0",
        "- Week 2: extraction pilot, temporal extractor, alignment risk, FAQ/enforcement check, licensing note, annotation process pilot",
        "- Week 3: full-corpus extract/segment, cross-references, Matrix v1",
        "- Week 4: supplementary harvest, deontic candidates, cross-class matcher, T1 candidates",
        "- Week 5: stratified validation sample, annotation templates for Akash/Karan/Meer, validated file (empty until real labels)",
        "",
        "## 2. Metrics table (actual)",
        "",
        "| Week | Metric | Value |",
        "|------|--------|-------|",
        f"| 1 | documents_discovered | {fmt(w1.get('documents_discovered'))} |",
        f"| 1 | urls_discovered | {fmt(w1.get('urls_discovered'))} |",
        f"| 1 | downloads_attempted | {fmt(w1.get('downloads_attempted'))} |",
        f"| 1 | downloads_successful | {fmt(w1.get('downloads_successful'))} |",
        f"| 1 | downloads_failed | {fmt(w1.get('downloads_failed'))} |",
        f"| 1 | download_success_rate | {fmt(w1.get('download_success_rate'))} |",
        f"| 1 | pdf_count | {fmt(w1.get('pdf_count'))} |",
        f"| 1 | html_count | {fmt(w1.get('html_count'))} |",
        f"| 1 | duplicate_count | {fmt(w1.get('duplicate_count'))} |",
        f"| 1 | extraction_readiness_openable | {fmt(w1.get('extraction_readiness_openable'))} |",
        f"| 1 | matrix_v0_row_count | {fmt(w1.get('matrix_v0_row_count'))} |",
        f"| 1 | distinct_entity_classes_raw | {fmt(w1.get('distinct_entity_classes_found_raw'))} |",
        f"| 1 | distinct_subject_families_raw | {fmt(w1.get('distinct_subject_families_found_raw'))} |",
        f"| 2 | extraction_success_rate_pilot | {fmt(w2.get('extraction_success_rate_pilot'))} |",
        f"| 2 | temporal_metadata_coverage_pilot | {fmt(w2.get('temporal_metadata_coverage_pilot'))} |",
        f"| 2 | cross_class_alignment_rate | {fmt(align)} |",
        f"| 2 | faq_paragraph_alignment_rate | {fmt(w2.get('faq_paragraph_alignment_rate'))} |",
        f"| 2 | enforcement_paragraph_alignment_rate | {fmt(w2.get('enforcement_paragraph_alignment_rate'))} |",
        f"| 2 | annotation_pilot_item_count | {fmt(w2.get('annotation_pilot_item_count'))} |",
        f"| 2 | annotation_pilot_avg_time_per_item_seconds | {fmt(w2.get('annotation_pilot_avg_time_per_item_seconds'))} |",
        f"| 3 | total_documents_discovered | {fmt(w3.get('total_documents_discovered'))} |",
        f"| 3 | downloads_successful | {fmt(w3.get('downloads_successful'))} |",
        f"| 3 | downloads_failed | {fmt(w3.get('downloads_failed'))} |",
        f"| 3 | total_paragraphs_extracted | {fmt(w3.get('total_paragraphs_extracted'))} |",
        f"| 3 | extraction_failures | {fmt(w3.get('extraction_failures'))} |",
        f"| 3 | malformed_documents | {fmt(w3.get('malformed_documents'))} |",
        f"| 3 | cross_reference_count | {fmt(w3.get('cross_reference_count'))} |",
        f"| 3 | entity_classes_discovered | {fmt(w3.get('entity_classes_discovered'))} |",
        f"| 3 | subject_families_discovered | {fmt(w3.get('subject_families_discovered'))} |",
        f"| 3 | matrix_cells_populated | {fmt(w3.get('matrix_cells_populated'))} |",
        f"| 3 | matrix_cells_missing | {fmt(w3.get('matrix_cells_missing'))} |",
        f"| 3 | duplicate_mappings_count | {fmt(w3.get('duplicate_mappings_count'))} |",
        f"| 3 | ambiguous_mappings_count | {fmt(w3.get('ambiguous_mappings_count'))} |",
        f"| 3 | matrix_coverage | {fmt(w3.get('matrix_coverage'))} |",
        f"| 4 | supplementary_documents_harvested | {fmt(w4.get('supplementary_documents_harvested'))} |",
        f"| 4 | candidate_obligation_spans | {fmt(w4.get('candidate_obligation_spans_extracted'))} |",
        f"| 4 | candidate_rejection_rate | {fmt(w4.get('candidate_rejection_rate'))} |",
        f"| 4 | cross_class_candidate_matches | {fmt(w4.get('cross_class_candidate_matches'))} |",
        f"| 4 | matches_by_differential_flag | {fmt(w4.get('matches_by_differential_flag'))} |",
        f"| 4 | match_level_used | {fmt(w4.get('match_level_used'))} |",
        f"| 4 | t1_candidate_count | {fmt(w4.get('t1_candidate_count'))} |",
        f"| 5 | candidate_pool_size | {fmt(w5.get('candidate_pool_size'))} |",
        f"| 5 | stratified_validation_sample_size | {fmt(w5.get('stratified_validation_sample_size'))} |",
        f"| 5 | items_annotated_by_ge_2 | {fmt(w5.get('items_independently_annotated_by_ge_2'))} |",
        f"| 5 | fleiss_kappa | {fmt(w5.get('fleiss_kappa'))} |",
        f"| 5 | validated_benchmark_size | {fmt(w5.get('validated_benchmark_size'))} |",
        f"| 5 | ambiguity_rate_proxy_absent_share | {fmt(w5.get('ambiguity_rate_proxy_absent_share'))} |",
        "",
        "## 3. NOT YET MEASURED / FAILED",
        "",
        "### NOT YET MEASURED",
        "",
    ]
    if not_measured:
        lines += [f"- {x}" for x in not_measured]
    else:
        lines.append("- (none found as literal NOT YET MEASURED strings in top-level metrics; see nested fields)")
    lines += ["", "### FAILED", ""]
    if failed:
        lines += [f"- {x}" for x in failed]
    else:
        lines.append("- (none found as literal FAILED strings in walked metrics)")
    # Always call out download failures list if present
    fr = w1.get("download_failure_reasons") or []
    if fr:
        lines += ["", "Download failures (Week 1):", ""]
        for item in fr[:50]:
            lines.append(f"- {item}")

    lines += [
        "",
        "## 4. Cross-class alignment rate and <60% fallback",
        "",
        f"- Alignment rate: **{fmt(align)}**",
        f"- Fallback triggered (<60%): **{triggered}**",
        f"- Match level used in Week 4: **{fmt(w4.get('match_level_used'))}**",
        "- Detail: `reports/week2_alignment_risk.md`",
        "",
        "## 5. FAQ / enforcement paragraph-alignment findings",
        "",
        f"- FAQ rate: **{fmt(w2.get('faq_paragraph_alignment_rate'))}**",
        f"- Enforcement rate: **{fmt(w2.get('enforcement_paragraph_alignment_rate'))}**",
        "- Detail: `reports/week2_faq_enforcement_check.md`",
        "",
        "## 6. T1 candidate vs validated state",
        "",
        f"- Candidate pool size: **{fmt(w5.get('candidate_pool_size'))}**",
        f"- Stratified validation sample: **{fmt(w5.get('stratified_validation_sample_size'))}**",
        f"- Validated benchmark size: **{fmt(w5.get('validated_benchmark_size'))}**",
        f"- Fleiss' kappa: **{fmt(w5.get('fleiss_kappa'))}**",
        "- Candidate file: `data/benchmark/candidate/t1_candidates.csv`",
        "- Validated file: `data/benchmark/validated/t1_validated.csv` (headers only until real multi-annotator labels exist)",
        "- Annotation templates: `data/benchmark/validated/annotation_templates/`",
        "",
        "## 7. What's next (description only — not implemented)",
        "",
        "- **Week 6:** T4 RePASs metric-integrity audit on Indian regulatory text.",
        "- **Week 7:** BM25 / dense / hybrid retrieval baselines on RBI-ObliBench.",
        "",
        "No Week 6+ code was implemented in this run.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
