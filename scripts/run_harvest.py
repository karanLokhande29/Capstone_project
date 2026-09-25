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

P1-004 repair stages:

    python scripts/run_harvest.py diagnose --from-failures --max 5
    python scripts/run_harvest.py export-missing
    python scripts/run_harvest.py repair --import-dir ~/missing_pdfs --max-requests 150

`repair` recovers the 81 Directions the first harvest lost to what looks like
a session-level block, WITHOUT re-downloading the 299 that succeeded, and
stops at the first failed consistency check rather than publishing a corpus
whose paragraph ids have silently moved under three people's annotations.
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
from src.preprocessing.consistency import (  # noqa: E402
    ConsistencyError,
    check_pilot_join,
    check_stable_ids,
    write_fingerprints,
)
from src.schemas.provenance import DocumentRecord  # noqa: E402
from src.scraper.rbi_scraper import (  # noqa: E402
    RequestBudgetExceeded,
    _fetch,
    _validate_payload,
    build_session,
    coverage_by_entity_class,
    harvest_corpus,
)


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

    # A11: per-class coverage. An overall 299/380 hides that the first harvest
    # lost 35/44 Commercial Banks and 31/40 Small Finance Banks Directions —
    # the two classes a cross-class comparison most depends on.
    coverage = {}
    if manifest_rows:
        records = [DocumentRecord.from_dict(r) for r in manifest_rows]
        coverage = coverage_by_entity_class(records, logger=logger)

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
    if coverage:
        repair = m.get("repair", {})
        before = repair.get("coverage_before", {}).get("by_entity_class", {})
        lines += [
            "",
            "---",
            "",
            "## Coverage by entity class",
            "",
            "_Repaired by P1-004 (Karan, solo)._ A corpus-level download rate is not enough "
            "for RQ1: the first harvest's 81 failures were not spread evenly, they fell "
            "almost entirely on Commercial Banks and Small Finance Banks, which is exactly "
            "where a cross-class comparison needs coverage most.",
            "",
            "| Entity class | Before | After | Rate |",
            "|---|---|---|---|",
        ]
        for cls, stats in sorted(coverage["by_entity_class"].items()):
            was = before.get(cls, {})
            was_txt = f"{was.get('downloaded')}/{was.get('total')}" if was else "—"
            flag = " **(below 90%)**" if stats["rate"] < 0.90 else ""
            lines.append(
                f"| {cls} | {was_txt} | {stats['downloaded']}/{stats['total']} "
                f"| {stats['rate']:.1%}{flag} |"
            )
        overall = coverage["overall"]
        lines += [
            f"| **Overall** | — | **{overall['downloaded']}/{overall['total']}** "
            f"| **{overall['rate']:.1%}** |",
            "",
        ]
        if coverage["classes_below_90_percent"]:
            lines += [
                f"**WARNING — {len(coverage['classes_below_90_percent'])} class(es) below "
                f"90%:** {', '.join(coverage['classes_below_90_percent'])}. Any RQ1 or RQ2 "
                "claim scoped to these classes rests on a partial corpus, and the audit "
                "should read it that way.",
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


# -- P1-004 repair stages -----------------------------------------------------


def _load_manifest(resolver) -> list[DocumentRecord]:
    path = resolver.find_read_path("metadata", "document_manifest.jsonl")
    if path is None:
        return []
    return [DocumentRecord.from_dict(r) for r in read_jsonl(path)]


def run_diagnose(cfg, resolver, logger, *, from_failures: bool, max_docs: int) -> dict:
    """Fetch a few failed documents twice — cold, then after a listing warm-up.

    The 81 failures were the first 81 records in download order, which is the
    signature of a session-level block rather than 81 broken documents. That
    is an inference, and this stage is what turns it into a measurement:
    if a warm-up fixes a cold failure, the block is session-level and the
    repair's retry strategy is the right one. If both fail identically, it is
    not, and the manual-import path is the honest fallback.

    Nothing here disguises the client. It sends ordinary requests and records
    what comes back.
    """
    records = _load_manifest(resolver)
    targets = [r for r in records if not r.content_hash] if from_failures else records
    targets = targets[:max_docs]

    log_dir = Path(resolver.write_dir("logs", create=True)) / "harvest_diagnose"
    log_dir.mkdir(parents=True, exist_ok=True)

    listing_url = cfg["network"]["sources"]["rbi_master_directions"]["listing_url"]
    observations = []

    for record in targets:
        for mode in ("cold", "warmed"):
            session = build_session(cfg)
            if mode == "warmed":
                try:
                    _fetch(listing_url, session, cfg, logger=logger, description="listing warm-up")
                except Exception as exc:
                    logger.warning("diagnose: warm-up failed: %s", exc)
            try:
                data = _fetch(
                    record.source_url, session, cfg, logger=logger,
                    description=f"diagnose {record.document_id} ({mode})",
                )
            except Exception as exc:
                observations.append({
                    "document_id": record.document_id, "mode": mode,
                    "outcome": "transport_error", "detail": str(exc)[:300],
                })
                continue

            ok, detail = _validate_payload(data, record.format)
            title = ""
            if not ok and b"<" in data[:2048]:
                body = data[:4096]
                (log_dir / f"{record.document_id}.{mode}.html").write_bytes(body)
                import re as _re
                found = _re.search(rb"<title[^>]*>(.*?)</title>", data[:8192], _re.I | _re.S)
                title = found.group(1).decode("utf-8", "replace").strip()[:200] if found else ""

            observations.append({
                "document_id": record.document_id,
                "mode": mode,
                "outcome": "pdf" if ok else "rejected",
                "detail": detail,
                "length": len(data),
                "first_16_bytes": repr(data[:16]),
                "html_title": title,
            })

    cold_ok = sum(1 for o in observations if o["mode"] == "cold" and o["outcome"] == "pdf")
    warm_ok = sum(1 for o in observations if o["mode"] == "warmed" and o["outcome"] == "pdf")
    warm_up_helped = warm_ok > cold_ok

    result = {
        "documents_probed": len(targets),
        "cold_successes": cold_ok,
        "warmed_successes": warm_ok,
        "warm_up_helped": warm_up_helped,
        "observations": observations,
        "log_dir": str(log_dir),
        "conclusion": (
            "A listing warm-up recovered documents a cold session could not, so the block is "
            "session-level and the only-missing retry path should recover most of the 81."
            if warm_up_helped else
            "A warm-up made no difference on this sample. The block is not session-level, or "
            "is no longer active. If the retries still fail, the manual-import path is the "
            "remaining route and no evasion should be attempted."
        ) if targets else "No documents probed.",
    }
    logger.info("diagnose: cold %d/%d ok, warmed %d/%d ok, warm-up helped=%s",
                cold_ok, len(targets), warm_ok, len(targets), warm_up_helped)
    return result


def run_export_missing(cfg, resolver, logger) -> dict:
    """List what is still missing, so it can be fetched by hand in a browser."""
    import csv as _csv
    records = _load_manifest(resolver)
    missing = [r for r in records if not r.content_hash]
    path = resolver.write_path("reports", "p1004_missing_documents.csv")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=[
            "document_id", "source_url", "url_basename", "entity_class_raw", "title"])
        writer.writeheader()
        for r in sorted(missing, key=lambda x: x.document_id):
            writer.writerow({
                "document_id": r.document_id,
                "source_url": r.source_url or "",
                "url_basename": Path(r.source_url).name if r.source_url else "",
                "entity_class_raw": r.entity_class_raw or "",
                "title": (r.title or "").strip(),
            })
    logger.info("export-missing: %d document(s) -> %s", len(missing), path)
    return {"missing_count": len(missing), "path": str(path),
            "document_ids": [r.document_id for r in missing]}


def run_repair(cfg, resolver, logger, *, import_dir, max_requests) -> dict:
    """The full repair, stopping at the first failed check.

    Ordered so that nothing irreversible happens after something unverified:
    the fingerprint snapshot is taken BEFORE re-segmentation, and the
    consistency checks run before the xref and coverage stages, so a corpus
    that moved a paragraph id never reaches the reports.
    """
    metrics: dict = {"stages_run": []}

    before = _load_manifest(resolver)
    metrics["coverage_before"] = coverage_by_entity_class(before)
    metrics["documents_before"] = len(before)
    metrics["missing_before"] = sum(1 for r in before if not r.content_hash)

    # 1-3. only-missing harvest with payload retries, then manual import.
    try:
        metrics["harvest"] = harvest_corpus(
            cfg, resolver=resolver, logger=logger, only_missing=True,
            existing_manifest=before, max_requests=max_requests, import_dir=import_dir,
        )
    except RequestBudgetExceeded as exc:
        metrics["stopped_at"] = "request_budget"
        metrics["error"] = str(exc)
        logger.error("repair: %s", exc)
        return metrics
    metrics["stages_run"].append("harvest")

    after = _load_manifest(resolver)
    newly = sorted(
        {r.document_id for r in after if r.content_hash}
        - {r.document_id for r in before if r.content_hash}
    )
    metrics["newly_available_ids"] = newly

    # 4. Extract ONLY the new documents. On Kaggle the 299 previously-extracted
    #    PDFs are not attached, so an unfiltered pass would report a corpus-wide
    #    extraction failure that did not happen.
    metrics["extract"] = extract_corpus(
        cfg, resolver=resolver, logger=logger, only_ids=newly
    ) if newly else {"skipped": "no newly available documents"}
    metrics["stages_run"].append("extract")

    # 5. Fingerprint BEFORE re-segmenting, or there is nothing to compare to.
    metrics["fingerprints_path"] = write_fingerprints(resolver, logger=logger)
    metrics["segment"] = segment_corpus(cfg, resolver=resolver, logger=logger)
    metrics["stages_run"].append("segment")

    # 6. Hard stops. A corpus that fails either must not be published.
    try:
        metrics["stable_id_check"] = check_stable_ids(resolver, logger=logger)
        metrics["pilot_join_check"] = check_pilot_join(resolver, logger=logger)
    except ConsistencyError as exc:
        metrics["stopped_at"] = "consistency"
        metrics["error"] = str(exc)
        logger.error("repair: %s", exc)
        return metrics
    metrics["stages_run"].append("consistency")

    # 7-8. Only now: cross-references and the coverage report.
    metrics["xref"] = resolve_cross_references(cfg, resolver=resolver, logger=logger)
    metrics["coverage_after"] = coverage_by_entity_class(after, logger=logger)
    metrics["stages_run"] += ["xref", "coverage"]
    metrics["still_missing"] = sorted(r.document_id for r in after if not r.content_hash)
    return metrics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "stage",
        choices=["discover", "download", "extract", "segment", "xref", "all", "report",
                 "diagnose", "repair", "export-missing"],
        help="Pipeline stage to run. 'download' is an alias for 'discover' (download is part of harvest_corpus). "
        "'all' runs discover+download, extract, segment, xref in sequence. 'report' only regenerates "
        "reports/phase1_akash_corpus.md from whatever has already been produced.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap documents downloaded (small slice / smoke run).")
    parser.add_argument("--config", default=None, help="Path to an alternative config.yaml.")
    parser.add_argument("--json", action="store_true", help="Print metrics as JSON instead of a summary.")
    parser.add_argument("--from-failures", action="store_true",
                        help="diagnose: probe documents that have no content_hash.")
    parser.add_argument("--max", type=int, default=5, help="diagnose: how many documents to probe.")
    parser.add_argument("--import-dir", default=None,
                        help="repair: directory of hand-downloaded PDFs to adopt.")
    parser.add_argument("--max-requests", type=int, default=150,
                        help="repair: refuse to start if the plan needs more requests than this.")
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

    if args.stage in ("diagnose", "repair", "export-missing"):
        resolver = PathResolver.from_config(cfg)
        if args.stage == "diagnose":
            metrics = {"scope": "diagnose",
                       "diagnose": run_diagnose(cfg, resolver, logger,
                                                from_failures=args.from_failures, max_docs=args.max)}
        elif args.stage == "export-missing":
            metrics = {"scope": "export-missing",
                       "export_missing": run_export_missing(cfg, resolver, logger)}
        else:
            metrics = {"scope": "repair",
                       "repair": run_repair(cfg, resolver, logger,
                                            import_dir=args.import_dir,
                                            max_requests=args.max_requests)}
        write_json(resolver.write_path("reports", f"phase1_akash_{args.stage}_metrics.json"), metrics)
        print(json.dumps(metrics, indent=2, default=str) if args.json
              else json.dumps({k: v for k, v in metrics.items()}, indent=2, default=str)[:4000])
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
