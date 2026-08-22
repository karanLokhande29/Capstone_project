#!/usr/bin/env python3
"""CLI entry point for the corpus acquisition pipeline.

Usable both locally against a small ``--limit`` slice (for validation, or for
producing real data another branch can build against without a full harvest)
and on Kaggle at full corpus scale with no limit. Every stage can be run
independently or chained with ``all``; each stage reads what the previous one
wrote through the standard path resolver, so re-running a later stage after an
earlier one requires no extra plumbing.

    python scripts/run_harvest.py discover
    python scripts/run_harvest.py all --limit 12          # small slice
    python scripts/run_harvest.py all                     # full corpus (Kaggle)
    python scripts/run_harvest.py report                  # write the summary report only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.cache import ArtifactCache  # noqa: E402
from src.common.config import load_config  # noqa: E402
from src.common.io_helpers import read_jsonl, write_json  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.extraction.text_extractor import extract_corpus  # noqa: E402
from src.preprocessing.cross_references import resolve_cross_references  # noqa: E402
from src.preprocessing.segmenter import segment_corpus  # noqa: E402
from src.scraper.rbi_scraper import build_session, harvest_corpus  # noqa: E402


def _write_report(cfg, resolver, metrics: dict, logger) -> Path:
    """Render `metrics` (from `run_pipeline`) as reports/phase1_akash_corpus.md."""
    m = metrics
    discover = m.get("discover", {})
    extract = m.get("extract", {})
    segment = m.get("segment", {})
    xref = m.get("xref", {})

    manifest_path = discover.get("manifest_path")
    entity_classes: set[str] = set()
    dated_count = 0
    manifest_rows: list[dict] = []
    if manifest_path and Path(manifest_path).exists():
        manifest_rows = read_jsonl(manifest_path)
        for row in manifest_rows:
            if row.get("entity_class_raw"):
                entity_classes.add(row["entity_class_raw"])
            if row.get("update_date"):
                dated_count += 1

    is_slice = m.get("limit") is not None
    scope_label = f"small validation slice, limit={m['limit']}" if is_slice else "full corpus"

    lines = [
        "# Phase 1 — Akash: Corpus Acquisition, Extraction, Segmentation",
        "",
        f"Run scope: **{scope_label}** (pipeline stage: `{m.get('scope', 'unknown')}`)",
        "",
    ]
    if is_slice:
        lines += [
            "This is the Task 7 small validation slice — real network calls against "
            "the live RBI site, a strict subset of the eventual full corpus, produced "
            "so `phase1/meer-annotation` (P1-003) has real `ParagraphRecord`s to build "
            "its Week-2 checks against rather than waiting on the full harvest.",
            "",
            "The full-corpus harvest (Task 8, Week 3) is a Kaggle-execution deliverable, "
            "not a local one — see `notebooks/phase1-akash-corpus.ipynb` §5 and Section U "
            "of the governing prompt (\"The full-network, full-corpus run is not a local "
            "test — it is reported from the Kaggle execution\"). Its metrics are "
            "**NOT YET MEASURED** here; they will be reported after that notebook runs.",
            "",
        ]
    lines += [
        "## Discovery",
        "",
        f"- Documents discovered: **{discover.get('documents_discovered', 'NOT YET MEASURED')}**",
        f"- Downloads attempted: **{discover.get('downloads_attempted', 'NOT YET MEASURED')}**",
        f"- Downloads successful: **{discover.get('downloads_successful', 'NOT YET MEASURED')}**",
        f"- Downloads failed: **{discover.get('downloads_failed', 'NOT YET MEASURED')}**",
        f"- Download success rate: **{discover.get('download_success_rate', 'NOT YET MEASURED')}**",
        f"- PDF count: **{discover.get('pdf_count', 'NOT YET MEASURED')}**",
        f"- HTML count: **{discover.get('html_count', 'NOT YET MEASURED')}**",
        f"- Distinct entity classes (raw, this run's downloaded slice): **{len(entity_classes)}**",
        f"  - {sorted(entity_classes)}",
        "",
        "### Subject-family axis: not present on the source listing",
        "",
        "`subject_family_raw` is `null` for every discovered document. The RBI "
        "Master Directions listing (`BS_ViewMasDirections.aspx`) groups documents "
        "only by an entity-class heading and, within that, a date sub-heading — "
        "there is no subject/topic column or heading level anywhere on the page "
        "(confirmed: no dropdown, no anchor, no distinguishing id on any heading "
        "row). This is a discovery finding, not a parsing gap: recording it "
        "faithfully as absent, rather than deriving a value from the title, "
        "avoids repeating the bug in this project's pre-Phase-0 history where "
        "title-based subject splitting truncated names like "
        '"Urban Co-operative Banks" to "Urban Co". Subject-family construction is '
        "left to `phase1/karan-matrix`, which can work from paragraph text.",
        "",
        "### Duplicate entity-class heading blocks",
        "",
        "A number of entity-class headings on the listing page (e.g. "
        '"Commercial Banks") appear more than once, as non-adjacent blocks with no '
        "distinguishing marker anywhere in the HTML — see the WARNING-level log "
        "line from `discover_documents` for the exact count and names on this run. "
        "`entity_class_raw` is recorded faithfully as the heading text either way, "
        "so this does not affect correctness of what's captured — but it means two "
        "documents sharing `entity_class_raw` may come from different, unlabelled "
        "listing passes. See `src/scraper/rbi_scraper.py` module docstring for the "
        "full investigation.",
        "",
        "## Extraction",
        "",
        f"- Documents considered: **{extract.get('documents_considered', 'NOT YET MEASURED')}**",
        f"- Extraction successful: **{extract.get('extraction_successful', 'NOT YET MEASURED')}**",
        f"- Extraction failures: **{extract.get('extraction_failures', 'NOT YET MEASURED')}**",
        f"- Extracted empty (parsed, no usable text): **{extract.get('extraction_empty', 'NOT YET MEASURED')}**",
        f"- Skipped (not downloaded): **{extract.get('skipped_not_downloaded', 'NOT YET MEASURED')}**",
        f"- Extraction success rate: **{extract.get('extraction_success_rate', 'NOT YET MEASURED')}**",
        "",
        "## Segmentation",
        "",
        f"- Documents segmented: **{segment.get('documents_segmented', 'NOT YET MEASURED')}**",
        f"- Total paragraphs: **{segment.get('total_paragraphs', 'NOT YET MEASURED')}**",
        f"- section_id coverage: **{segment.get('section_id_coverage', 'NOT YET MEASURED')}**",
        f"- clause_path coverage: **{segment.get('clause_path_coverage', 'NOT YET MEASURED')}**",
        f"- Documents with no recognised structure: **{segment.get('documents_with_no_recognised_structure', 'NOT YET MEASURED')}**",
        "",
        "## Cross-references",
        "",
        f"- Phrases detected: **{xref.get('cross_reference_phrases_detected', 'NOT YET MEASURED')}**",
        f"- Resolved (intra-document only): **{xref.get('cross_reference_count', 'NOT YET MEASURED')}**",
        f"- Resolution rate: **{xref.get('resolution_rate', 'NOT YET MEASURED')}**",
        "",
        "Cross-document references (to other Directions, circulars, or the Banking "
        "Regulation Act) are detected as phrases but never resolved to a "
        "`paragraph_id` outside this scope — a low resolution rate is therefore "
        "expected and is not itself a defect; most legal cross-references in RBI "
        "text point outside the referencing document.",
        "",
        "## Temporal signal (`update_date`)",
        "",
        f"- Documents carrying an \"(Updated as on ...)\" stamp in this run's manifest: "
        f"**{dated_count} / {len(manifest_rows)}**"
        + (f" ({dated_count / len(manifest_rows):.3f})" if manifest_rows else ""),
        "- Extracted verbatim from the title via `src.extraction.temporal_signals`; "
        "not parsed into a structured date, and not cross-checked against the "
        "listing's own per-block date sub-heading (see that module's docstring for "
        "why the two are not interchangeable).",
        "",
        "## FAQ / enforcement supplementary sample",
        "",
        "**NOT YET MEASURED.** `FAQView.aspx` (the FAQ index) was reachable, but "
        "is a category index requiring a second-level crawl into per-category "
        "pages to reach actual FAQ text — not \"trivially reachable\" in the sense "
        "Task 7 intends, and building that crawl would be the systematic "
        "harvester this prompt explicitly says not to build here. Left for "
        "Phase 2, Week 4 as scoped.",
        "",
    ]
    out_path = resolver.write_path("reports", "phase1_akash_corpus.md")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("report written: %s", out_path)
    return out_path


def run_pipeline(cfg, *, scope: str, limit: int | None, logger) -> dict:
    """Run the requested pipeline stage(s), returning a metrics dict per stage."""
    resolver = PathResolver.from_config(cfg)
    session = build_session(cfg)
    cache = ArtifactCache.from_config(cfg, resolver, namespace="scraper")

    metrics: dict = {"scope": scope, "limit": limit}

    if scope in ("discover", "download", "all"):
        metrics["discover"] = harvest_corpus(
            cfg, limit=limit, session=session, resolver=resolver, cache=cache, logger=logger
        )
    if scope in ("extract", "all"):
        metrics["extract"] = extract_corpus(cfg, resolver=resolver, cache=cache, logger=logger)
    if scope in ("segment", "all"):
        metrics["segment"] = segment_corpus(cfg, resolver=resolver, logger=logger)
    if scope in ("xref", "all"):
        metrics["xref"] = resolve_cross_references(cfg, resolver=resolver, logger=logger)

    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "stage",
        choices=["discover", "download", "extract", "segment", "xref", "all", "report"],
        help="Pipeline stage to run. 'download' is an alias for 'discover' (download is part of harvest_corpus). "
        "'all' runs discover+download, extract, segment, xref in sequence. 'report' only regenerates "
        "reports/phase1_akash_corpus.md from whatever has already been produced.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap documents downloaded (small slice / smoke run).")
    parser.add_argument("--config", default=None, help="Path to an alternative config.yaml.")
    parser.add_argument("--json", action="store_true", help="Print metrics as JSON instead of a summary.")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    logger = get_logger("scripts.run_harvest", cfg)

    if args.stage == "report":
        resolver = PathResolver.from_config(cfg)
        manifest_path = resolver.find_read_path("metadata", "document_manifest.jsonl")
        metrics = {"scope": "report-only", "limit": None, "discover": {}, "extract": {}, "segment": {}, "xref": {}}
        if manifest_path:
            metrics["discover"]["manifest_path"] = str(manifest_path)
            metrics["discover"]["documents_discovered"] = len(read_jsonl(manifest_path))
        _write_report(cfg, resolver, metrics, logger)
        return 0

    metrics = run_pipeline(cfg, scope=args.stage, limit=args.limit, logger=logger)

    resolver = PathResolver.from_config(cfg)
    metrics_path = resolver.write_path("reports", f"phase1_akash_{args.stage}_metrics.json")
    write_json(metrics_path, metrics)

    if args.stage == "all":
        _write_report(cfg, resolver, metrics, logger)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        for stage_name, stage_metrics in metrics.items():
            if not isinstance(stage_metrics, dict):
                continue
            print(f"=== {stage_name} ===")
            for key, value in stage_metrics.items():
                if key in ("failures", "empty_document_ids"):
                    continue
                print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
