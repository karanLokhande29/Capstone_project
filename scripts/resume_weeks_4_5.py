#!/usr/bin/env python3
"""Resume Weeks 4–5 using existing Week 1–3 artifacts (after matcher fix)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.utils import load_config, resolve_path, setup_logging
from src.benchmark.deontic_extractor import DeonticExtractor
from src.benchmark.cross_class_matcher import CrossClassMatcher
from src.benchmark.t1_candidate_builder import T1CandidateBuilder
from src.benchmark.stratified_sampler import StratifiedSampler, try_compute_kappa_from_annotations
from scripts.run_weeks_1_to_5 import save_json, _write_summary


def main() -> int:
    cfg = load_config()
    log = setup_logging("pipeline.resume_w4w5", cfg)
    reports = resolve_path(cfg, "reports")

    w1 = json.loads((reports / "week1_metrics.json").read_text(encoding="utf-8"))
    w2 = json.loads((reports / "week2_metrics.json").read_text(encoding="utf-8"))
    w3 = json.loads((reports / "week3_metrics.json").read_text(encoding="utf-8"))

    log.info("=== WEEK 4 resume: deontic (if needed) + matcher + T1 ===")
    cand_path = resolve_path(cfg, "benchmark_candidate") / "obligation_candidates.jsonl"
    if cand_path.exists() and cand_path.stat().st_size > 1000:
        # Recompute counts from existing file
        kept = rejected = 0
        with cand_path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("rejected"):
                    rejected += 1
                else:
                    kept += 1
        total = kept + rejected
        deontic = {
            "candidate_obligation_spans": kept,
            "candidate_spans_total_including_rejected": total,
            "candidate_rejection_rate": (rejected / total) if total else 0.0,
            "output_path": str(cand_path),
            "note": "reused existing obligation_candidates.jsonl",
        }
        log.info("Reusing deontic candidates kept=%s rejected=%s", kept, rejected)
    else:
        deontic = DeonticExtractor(cfg).run()

    align_rate = w2.get("cross_class_alignment_rate")
    align_f = align_rate if isinstance(align_rate, float) else None
    match_metrics = CrossClassMatcher(cfg).run(alignment_rate=align_f)
    t1 = T1CandidateBuilder(cfg).run()

    # Supplementary counts from existing manifest if present
    supp_path = resolve_path(cfg, "metadata") / "supplementary_manifest.json"
    counts = {}
    if supp_path.exists():
        rows = json.loads(supp_path.read_text(encoding="utf-8"))
        for r in rows:
            if r.get("download_status") in {"success", "cached"}:
                counts[r.get("source_type", "unknown")] = counts.get(r.get("source_type", "unknown"), 0) + 1

    w4 = {
        "supplementary_documents_harvested": counts,
        "candidate_obligation_spans_extracted": deontic.get("candidate_obligation_spans"),
        "candidate_rejection_rate": deontic.get("candidate_rejection_rate"),
        "cross_class_candidate_matches": match_metrics.get("cross_class_candidate_matches"),
        "matches_by_differential_flag": match_metrics.get("matches_by_differential_flag"),
        "match_level_used": match_metrics.get("match_level_used"),
        "t1_candidate_count": t1.get("t1_candidate_count"),
        "t1": t1,
        "deontic": deontic,
        "matcher_caps": match_metrics.get("matcher_caps"),
    }
    save_json(reports / "week4_metrics.json", w4)

    log.info("=== WEEK 5 ===")
    sample_metrics = StratifiedSampler(cfg).sample()
    kappa_info = try_compute_kappa_from_annotations(resolve_path(cfg, "benchmark_validated"))
    cand_csv = resolve_path(cfg, "benchmark_candidate") / "t1_candidates.csv"
    dist_class, dist_flag = {}, {}
    ambiguity_rate: float | str = "NOT YET MEASURED"
    if cand_csv.exists():
        try:
            cdf = pd.read_csv(cand_csv)
        except pd.errors.EmptyDataError:
            cdf = pd.DataFrame()
        if len(cdf):
            dist_class = cdf["entity_class"].value_counts().to_dict()
            dist_flag = cdf["differential_flag"].value_counts().to_dict()
            ambiguity_rate = float((cdf["differential_flag"] == "absent").mean())

    w5 = {
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
    save_json(reports / "week5_metrics.json", w5)

    summary = reports / "weeks_1_to_5_summary.md"
    _write_summary(summary, w1, w2, w3, w4, w5)
    log.info("Wrote %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
