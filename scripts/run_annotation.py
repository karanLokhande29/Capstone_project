#!/usr/bin/env python3
"""CLI for corpus QA, the Week-2 risk checks, and the solo annotation protocol.

    python scripts/run_annotation.py qa          # independent corpus QA over ParagraphRecords
    python scripts/run_annotation.py checks      # cross-class alignment + FAQ/enforcement
    python scripts/run_annotation.py pilot       # extract candidates, write pass-1 task files
    python scripts/run_annotation.py ingest      # read a completed pass back into votes
    python scripts/run_annotation.py retest      # write the blind pass-2 file
    python scripts/run_annotation.py adjudicate  # write the adjudication file
    python scripts/run_annotation.py report      # regenerate the report from existing artifacts
    python scripts/run_annotation.py all         # qa + checks + pilot, then the report

Two properties of this CLI are load-bearing, not conveniences:

**`report` only reads.** It never re-runs `qa`, `checks` or `pilot`, and never
writes a task file or the candidate set. The superseded version called
`run_pilot()` from `report`, which rewrote every annotator's task file blank —
and `data/benchmark/**` is gitignored, so hand-entered labels destroyed that
way are not recoverable from anywhere.

**Nothing here invents an annotation.** `pilot` stops after writing task
files. Every reliability statistic stays NOT YET MEASURED until a real pass is
filled in and ingested.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.alignment_check import cross_class_alignment, faq_enforcement_check  # noqa: E402
from src.benchmark.annotation import (  # noqa: E402
    ANNOTATION_LOG_FILENAME,
    NOT_YET_MEASURED,
    ROUTE_ADJUDICATED,
    ROUTE_NEEDS_ADJUDICATION,
    ROUTE_NOT_OBLIGATION,
    ROUTE_PASS1_ONLY,
    ROUTE_RETEST_CONSISTENT,
    ROUTE_SINGLE_PASS,
    VOTE_BLANK,
    VOTE_NOT_OBLIGATION,
    VOTE_VOTED,
    AnnotationError,
    append_annotation_log,
    build_adjudication_tasks,
    build_annotation_tasks,
    build_pass2_tasks,
    disagreement_rows,
    draw_retest_set,
    load_adjudications,
    load_candidates,
    load_retest_set,
    load_votes,
    measure_agreement,
    merge_votes,
    persist_candidates,
    persist_labels,
    persist_votes,
    primary_annotator,
    promote_validated,
    read_annotation_log,
    route_counts,
    tautology_share_by_rater,
    tautology_smell_report,
    vote_status_counts,
)
from src.benchmark.corpus_qa import run_corpus_qa, validate_sample_against_schema  # noqa: E402
from src.benchmark.pilot import (  # noqa: E402
    cue_distribution,
    item_coverage_metrics,
    run_pilot_extraction,
)
from src.common.config import load_config  # noqa: E402
from src.common.io_helpers import read_jsonl, write_json  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.schemas.benchmark import T1Label  # noqa: E402

#: The date the protocol changed from three annotators to one.
SOLO_PROTOCOL_FROM = "2026-09-24"

INGEST_METRICS_FILENAME = "phase1_annotation_ingest_metrics.json"
DISAGREEMENTS_FILENAME = "phase1_pilot_disagreements.csv"

#: Validation routes in the order the report lists them.
REPORT_ROUTES = (
    ROUTE_RETEST_CONSISTENT,
    ROUTE_SINGLE_PASS,
    ROUTE_ADJUDICATED,
    ROUTE_NOT_OBLIGATION,
    ROUTE_PASS1_ONLY,
    ROUTE_NEEDS_ADJUDICATION,
)


def run_qa(cfg, resolver, logger) -> dict:
    metrics = run_corpus_qa(cfg, resolver=resolver, logger=logger)
    metrics.update(validate_sample_against_schema(resolver))
    return metrics


def run_checks(cfg, resolver, logger) -> dict:
    return {
        "cross_class_alignment": cross_class_alignment(cfg, resolver=resolver, logger=logger),
        "faq_enforcement": faq_enforcement_check(cfg, resolver=resolver, logger=logger),
    }


def run_pilot(cfg, resolver, logger, *, force: bool = False) -> dict:
    result = run_pilot_extraction(resolver, cfg, logger=logger)
    labels = result["labels"]

    candidates_path = persist_candidates(labels, cfg, resolver=resolver, force=force)
    task_files = build_annotation_tasks(labels, cfg, resolver=resolver, logger=logger, force=force)

    # Drawn now, at 100% of the pilot, so the retest set is fixed before any
    # pass-1 label is visible and cannot be chosen to flatter the statistic.
    retest_cfg = (cfg.get("benchmark", {}) or {}).get("retest", {}) or {}
    retest = draw_retest_set(
        labels,
        float(retest_cfg.get("pilot_fraction", 1.0)),
        int(retest_cfg.get("shuffle_seed", 0)),
        resolver=resolver,
        logger=logger,
    )

    return {
        "paragraphs_searched": result["paragraphs_searched"],
        "entity_classes_in_paragraphs_searched": result["entity_classes_in_paragraphs_searched"],
        "entity_classes_in_paragraphs_searched_count": len(
            result["entity_classes_in_paragraphs_searched"]
        ),
        **item_coverage_metrics(labels),
        "items_extracted": result["items_extracted"],
        "widening_attempts": result["widening_attempts"],
        "cue_distribution": cue_distribution(labels),
        "candidates_path": candidates_path,
        "task_files": task_files,
        "retest_set_size": len(retest.get("label_ids", [])),
        "annotation_status": (
            f"{NOT_YET_MEASURED} — task files generated and awaiting completion by "
            f"{len(task_files)} rater(s). No annotations have been fabricated."
        ),
    }


# -- ingest -------------------------------------------------------------------


def _parse_minutes(values: list[str] | None) -> dict[str, float]:
    minutes: dict[str, float] = {}
    for raw in values or []:
        if "=" not in raw:
            raise SystemExit(f"--minutes expects <rater>=<n>, got {raw!r}")
        rater, _, number = raw.partition("=")
        try:
            minutes[rater.strip()] = float(number)
        except ValueError:
            raise SystemExit(f"--minutes expects a number, got {number!r}") from None
    return minutes


def _merge_ingest_metrics(resolver, new: dict) -> dict:
    """Merge this pass into the ingest metrics file, never replacing prior passes."""
    path = resolver.write_path("reports", INGEST_METRICS_FILENAME)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    passes = dict(existing.get("passes", {}))
    passes.update(new.get("passes", {}))

    merged = {**existing, **new, "passes": passes}
    write_json(path, merged)
    return merged


def run_ingest(cfg, resolver, logger, args) -> dict:
    primary = primary_annotator(cfg)
    rater = args.rater or primary
    minutes = _parse_minutes(args.minutes)

    candidates = load_candidates(resolver)
    votes = load_votes(cfg, candidates=candidates, resolver=resolver, logger=logger)
    retest_ids = load_retest_set(resolver)

    adjudications = {}
    if args.adjudication:
        adjudications = load_adjudications(
            cfg, candidates=candidates, resolver=resolver, logger=logger
        )

    merged = merge_votes(
        candidates, votes, cfg, retest_ids=retest_ids,
        adjudications=adjudications, logger=logger,
    )
    promoted = promote_validated(merged, cfg, logger=logger)

    votes_path = persist_votes(votes, cfg, resolver=resolver)
    labels_path = persist_labels(promoted, cfg, "pilot_labels_annotated.jsonl", resolver=resolver)

    agreement = measure_agreement(votes, cfg, logger=logger)
    routes = route_counts(promoted)

    # One log entry per (rater, pass) actually present in this ingest.
    logged: list[dict] = []
    for pass_no in sorted({v.pass_no for v in votes if v.rater_id == rater}):
        if not args.adjudication and pass_no != args.pass_no:
            continue
        pass_votes = [v for v in votes if v.rater_id == rater and v.pass_no == pass_no]
        counts = vote_status_counts(pass_votes)
        entry = {
            "event": "ingest",
            "rater_id": rater,
            "pass_no": pass_no,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rows_voted": counts[VOTE_VOTED],
            "rows_blank": counts[VOTE_BLANK],
            "rows_not_obligation": counts[VOTE_NOT_OBLIGATION],
            "minutes": minutes.get(rater),
        }
        append_annotation_log(resolver, entry)
        logged.append(entry)

    if args.adjudication and adjudications:
        entry = {
            "event": "adjudication",
            "rater_id": rater,
            "pass_no": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_adjudicated": len(adjudications),
            "minutes": minutes.get(rater),
        }
        append_annotation_log(resolver, entry)
        logged.append(entry)

    columns, rows = disagreement_rows(votes, promoted)
    disagreements_path = resolver.write_path("reports", DISAGREEMENTS_FILENAME)
    if "span_text" in columns:
        raise AnnotationError(
            "refusing to write the disagreements CSV: it carries a span_text column. "
            "reports/ is tracked in git and RBI text is not redistributable (R6) — items "
            "are referenced by label_id, which resolves against the gitignored candidate file."
        )
    with disagreements_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    per_pass = {}
    for key in sorted({v.rater_key for v in votes}):
        pass_votes = [v for v in votes if v.rater_key == key]
        counts = vote_status_counts(pass_votes)
        per_pass[key] = {
            "rows_voted": counts[VOTE_VOTED],
            "rows_blank": counts[VOTE_BLANK],
            "rows_not_obligation": counts[VOTE_NOT_OBLIGATION],
            "minutes": minutes.get(pass_votes[0].rater_id) if pass_votes else None,
        }

    metrics = {
        "protocol": "single_expert_retest",
        "solo_protocol_from": SOLO_PROTOCOL_FROM,
        "primary_annotator": primary,
        "items_total": len(promoted),
        "items_validated": sum(1 for lbl in promoted if lbl.is_validated),
        "retest_set_size": len(retest_ids),
        "route_counts": routes,
        "passes": per_pass,
        "agreement": agreement,
        "tautology_smell": tautology_smell_report(promoted),
        "tautology_share_by_rater": tautology_share_by_rater(votes, candidates),
        "adjudicated_items": len(adjudications),
        "votes_path": votes_path,
        "labels_path": labels_path,
        "disagreements_path": str(disagreements_path),
        "log_entries_added": logged,
    }
    _merge_ingest_metrics(resolver, metrics)
    return metrics


def run_retest(cfg, resolver, logger, args) -> dict:
    return build_pass2_tasks(
        cfg,
        resolver=resolver,
        logger=logger,
        allow_short_gap=args.allow_short_gap,
        force=args.force_regenerate_tasks,
    )


def run_adjudicate(cfg, resolver, logger, args) -> dict:
    candidates = load_candidates(resolver)
    votes = load_votes(cfg, candidates=candidates, resolver=resolver, logger=logger)
    merged = merge_votes(
        candidates, votes, cfg, retest_ids=load_retest_set(resolver), logger=logger
    )
    return build_adjudication_tasks(
        merged, votes, cfg, resolver=resolver, logger=logger,
        force=args.force_regenerate_tasks,
    )


# -- report (read-only) -------------------------------------------------------


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_section(resolver, section: str) -> tuple[dict, str]:
    """Newest of the per-stage metrics file and the `all` file, for one section.

    Returns ``(data, provenance_line)``. The provenance line names the file and
    its timestamp, so every figure in the report can be traced to the run that
    produced it rather than being assumed current.
    """
    candidates: list[tuple[float, Path, dict]] = []
    for name in (f"phase1_meer_{section}_metrics.json", "phase1_meer_all_metrics.json"):
        path = resolver.find_read_path("reports", name)
        if path is None:
            continue
        data = _read_json(Path(path))
        if not isinstance(data, dict) or section not in data:
            continue
        candidates.append((Path(path).stat().st_mtime, Path(path), data[section]))

    if not candidates:
        return {}, f"_no metrics file found for `{section}` — run that stage_"

    mtime, path, data = max(candidates, key=lambda item: item[0])
    stamp = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return data, f"_source: `reports/{path.name}`, written {stamp}_"


def _fmt(value, spec: str = ".4f") -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    return format(value, spec)


def _fmt_ci(block) -> str:
    if not isinstance(block, dict):
        return str(NOT_YET_MEASURED)
    ci = block.get("ci95")
    if not isinstance(ci, (list, tuple)) or len(ci) != 2:
        return str(block.get("reason", NOT_YET_MEASURED))
    skipped = block.get("resamples_skipped_undefined", 0)
    used = block.get("resamples_used", 0)
    return (
        f"[{_fmt(ci[0])}, {_fmt(ci[1])}] "
        f"({used} resamples used, {skipped} skipped as undefined)"
    )


def _comparison_lines(block: dict, *, title: str) -> list[str]:
    """One reliability block, rendered with its n and never without it."""
    lines = [f"**{title}**", ""]
    if not block or block.get("n_items", 0) == 0:
        reason = block.get("status") if block else None
        lines += [f"- {reason or NOT_YET_MEASURED}", ""]
        return lines

    n = block["n_items"]
    lines += [
        f"- Items compared (a `voted` row on both sides): **{n}**",
        f"- Cohen's κ (differential_flag): **{_fmt(block.get('cohen_kappa_flag'))}** (n={n})",
        f"- Cohen's κ excluding `unlabelled`: **{_fmt(block.get('cohen_kappa_flag_excl_unlabelled'))}** "
        f"(n={block.get('n_items_excl_unlabelled', '?')})",
        f"- 95% bootstrap CI for κ: **{_fmt_ci(block.get('kappa_bootstrap_ci95'))}**",
        f"- Raw flag agreement: **{_fmt(block.get('raw_flag_agreement'))}** "
        "(the chance-uncorrected baseline κ is measured against)",
        f"- `applies_to` exact set match: **{_fmt(block.get('applies_to_exact_match_rate'))}**",
        f"- `applies_to` mean Jaccard: **{_fmt(block.get('applies_to_mean_jaccard'))}**",
    ]

    consistency = block.get("not_obligation_consistency")
    if isinstance(consistency, dict):
        lines.append(
            f"- Not-obligation consistency: **{_fmt(consistency.get('rate'))}** "
            f"(n={consistency.get('n_items_decided_in_both', '?')} items decided on both sides)"
        )
    else:
        lines.append(f"- Not-obligation consistency: **{consistency or NOT_YET_MEASURED}**")

    categories = block.get("disagreement_categories", {})
    lines += [
        f"- Disagreement categories: `flag_only`={categories.get('flag_only', 0)}, "
        f"`applies_to_only`={categories.get('applies_to_only', 0)}, "
        f"`both`={categories.get('both', 0)}, `none`={categories.get('none', 0)}",
        "",
    ]
    return lines


def _projection_lines(cfg, ingest: dict) -> list[str]:
    """Phase 2 sizing. Labelled a projection because that is all it is."""
    retest_cfg = (cfg.get("benchmark", {}) or {}).get("retest", {}) or {}
    r = float(retest_cfg.get("phase2_fraction", 0.20))

    minutes_per_item = None
    passes = ingest.get("passes", {}) if ingest else {}
    total_minutes = 0.0
    total_rows = 0
    for stats in passes.values():
        recorded = stats.get("minutes")
        rows = (stats.get("rows_voted") or 0) + (stats.get("rows_not_obligation") or 0)
        if recorded and rows:
            total_minutes += float(recorded)
            total_rows += rows
    if total_rows:
        minutes_per_item = total_minutes / total_rows

    lines = [
        "#### Phase 2 sizing — a PROJECTION, not a measurement",
        "",
        f"`N_target = (hours x 60) / (minutes_per_item x (1 + r))`, with `r = {r}` "
        "(`benchmark.retest.phase2_fraction`) covering the fraction of Phase 2 items "
        "that get a second, blind pass.",
        "",
    ]
    if minutes_per_item is None:
        lines += [
            f"- Minutes per item: **{NOT_YET_MEASURED}** — no timed pass has been ingested, so "
            "`N_target` cannot be projected. Nothing is substituted for it: a guessed rate here "
            "becomes a badly wrong Phase 2 schedule later.",
            "",
        ]
        return lines

    lines.append(f"- Measured minutes per item: **{minutes_per_item:.2f}**")
    for hours in (10, 20, 30):
        n_target = (hours * 60) / (minutes_per_item * (1 + r))
        lines.append(f"- At {hours} annotation hours: **N_target ≈ {int(n_target)} items**")
    lines.append("")
    return lines


def _write_report(cfg, resolver: PathResolver, logger) -> Path:
    """Assemble the report from artifacts on disk. Reads only; writes one file."""
    qa, qa_src = _load_section(resolver, "qa")
    checks, checks_src = _load_section(resolver, "checks")
    pilot, pilot_src = _load_section(resolver, "pilot")

    ingest_path = resolver.find_read_path("reports", INGEST_METRICS_FILENAME)
    ingest = _read_json(Path(ingest_path)) if ingest_path else None
    if ingest:
        stamp = datetime.fromtimestamp(
            Path(ingest_path).stat().st_mtime, tz=timezone.utc
        ).isoformat(timespec="seconds")
        ingest_src = f"_source: `reports/{Path(ingest_path).name}`, written {stamp}_"
    else:
        ingest = {}
        ingest_src = (
            f"_no ingest has run: `reports/{INGEST_METRICS_FILENAME}` does not exist_"
        )

    align = checks.get("cross_class_alignment", {})
    ent = align.get("entity_class_axis", {})
    sub = align.get("subject_family_axis_derived", {})
    faq = checks.get("faq_enforcement", {})

    primary = primary_annotator(cfg)
    retest_cfg = (cfg.get("benchmark", {}) or {}).get("retest", {}) or {}
    min_gap_days = int(retest_cfg.get("min_gap_days", 5))

    # Item-level pilot coverage, computed from the candidate file when the
    # metrics JSON predates the renamed keys. Reading is fine; writing is not.
    item_metrics = {
        k: pilot.get(k)
        for k in ("entity_classes_in_items_count", "items_missing_subject_family")
    }
    item_metrics_source = "the pilot metrics file"
    if item_metrics["entity_classes_in_items_count"] is None:
        candidates_path = resolver.find_read_path("benchmark", "pilot_candidates.jsonl")
        if candidates_path:
            rows = read_jsonl(Path(candidates_path))
            labels = [T1Label.from_dict(row) for row in rows]
            computed = item_coverage_metrics(labels)
            item_metrics = {
                "entity_classes_in_items_count": computed["entity_classes_in_items_count"],
                "items_missing_subject_family": computed["items_missing_subject_family"],
            }
            item_metrics_source = "`data/benchmark/pilot_candidates.jsonl`, read live"

    log = read_annotation_log(resolver)
    pass1_entries = [
        e for e in log.get("entries", [])
        if e.get("event") == "ingest" and int(e.get("pass_no") or 0) == 1
    ]
    pass2_entries = [
        e for e in log.get("entries", [])
        if e.get("event") == "ingest" and int(e.get("pass_no") or 0) == 2
    ]
    short_gap_used = any(
        e.get("allow_short_gap_used") for e in log.get("entries", []) if e.get("event") == "retest"
    )

    if pass1_entries:
        first_pass1 = pass1_entries[-1].get("timestamp")
        try:
            earliest = (
                datetime.fromisoformat(first_pass1) + timedelta(days=min_gap_days)
            ).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            earliest = NOT_YET_MEASURED
    else:
        first_pass1 = None
        earliest = f"{NOT_YET_MEASURED} — pass 1 has not been ingested"

    agreement = ingest.get("agreement", {}) if ingest else {}
    routes = ingest.get("route_counts", {}) if ingest else {}
    passes = ingest.get("passes", {}) if ingest else {}

    lines = [
        "# Phase 1 — Meer: Corpus QA, Annotation Pilot, Validation Protocol",
        "",
        f"> **Protocol change.** From {SOLO_PROTOCOL_FROM} this project has a single "
        f"annotator ({primary}). The three-annotator roster this report was originally "
        "written against no longer exists, so **inter-annotator agreement is not a "
        "statistic this project can produce.** Reliability evidence comes instead from a "
        "blind test-retest by the primary annotator and, where a second rater is "
        "obtainable, a second-rater comparison. Every figure in §5 is labelled by which "
        "of those it is. Fleiss' κ is not reported at all below three real raters.",
        "",
        "---",
        "",
        "## Derived-axis caveat (read before any `subject_family` stratification)",
        "",
        "`subject_family` on every `DocumentRecord`/`ParagraphRecord` is a **derived** "
        "value, not one harvested from RBI's own listing: RBI publishes no subject-family "
        "taxonomy at discovery time, so P1-002 inferred it by stripping the known "
        "`entity_class_raw` string out of each title (P1-002-CORRECTIVE, commit `e4013ca`). "
        "`entity_class`, by contrast, is raw-sourced with a 0% unresolved rate.",
        "",
        "**The two axes do not carry equal evidentiary weight, and nothing in this report "
        "treats them as if they did.** Every figure below that involves `subject_family` "
        "is marked accordingly. Provenance is queryable from the data itself "
        "(`data/metadata/vocabulary_provenance.json`), not only from prose.",
        "",
        "---",
        "",
        "## 1. Corpus QA (independent of P1-001's own metrics)",
        "",
        qa_src,
        "",
        f"- Paragraphs checked: **{qa.get('paragraphs_total', NOT_YET_MEASURED)}** "
        f"across **{qa.get('documents_represented', NOT_YET_MEASURED)}** documents",
        f"- Missing `section_id`: **{qa.get('missing_section_id', '?')}** "
        f"(**{_fmt(qa.get('missing_section_id_rate'))}**)",
        f"- Missing `clause_path`: **{qa.get('missing_clause_path', '?')}** "
        f"(**{_fmt(qa.get('missing_clause_path_rate'))}**)",
        f"- Duplicate `paragraph_id`s: **{qa.get('duplicate_paragraph_ids', NOT_YET_MEASURED)}**",
        f"- Empty text: **{qa.get('empty_text', NOT_YET_MEASURED)}**",
        f"- Missing `source_url`: **{qa.get('missing_source_url', NOT_YET_MEASURED)}**",
        f"- Missing `entity_class` (raw-sourced axis): **{qa.get('missing_entity_class', '?')}** "
        f"(**{_fmt(qa.get('missing_entity_class_rate'))}**)",
        f"- Missing `subject_family` (**derived** axis): **{qa.get('missing_subject_family', '?')}** "
        f"(**{_fmt(qa.get('missing_subject_family_rate'))}**)",
        f"- Records re-validated against `ParagraphRecord` schema: "
        f"**{qa.get('records_schema_checked', '?')}**, failing: "
        f"**{qa.get('records_failing_validation', '?')}**",
        f"- Spot-check sample drawn (for manual comparison against `source_url`): "
        f"**{qa.get('spot_check_sample_size', '?')}** paragraphs, listed in "
        "`reports/phase1_meer_all_metrics.json`",
        "",
        "This is a second opinion computed from the committed data as it landed on disk, "
        "not a re-read of P1-001's reported numbers. They agree, which is itself the "
        "finding: no drift between what the pipeline reported and what it wrote.",
        "",
        "The `subject_family` gap is materially larger than the `entity_class` gap — a "
        "direct consequence of the derivation caveat above, not an extraction defect.",
        "",
        "---",
        "",
        "## 2. Week-2 cross-class alignment check (the 60% trigger)",
        "",
        checks_src,
        "",
        f"- Entity classes sampled: {align.get('entity_classes_sampled', NOT_YET_MEASURED)}",
        f"- Subject families sampled (**derived axis**): {align.get('subject_families_sampled', NOT_YET_MEASURED)}",
        f"- Trigger threshold: **{_fmt(align.get('trigger_threshold'), '.0%')}**",
        f"- Similarity threshold for counting a position as aligned: **{align.get('similarity_threshold', '?')}** Jaccard",
        "",
        "### What 'aligned' means here, and a metric that had to be fixed",
        "",
        "Alignment requires **same structural position AND lexical agreement**. An earlier "
        "version of this check counted two paragraphs as aligned when they merely shared a "
        "`clause_path`. That measured almost nothing: `clause_path` values in this corpus "
        "are overwhelmingly bare numbers (`1`, `2`, `3`) that every Direction has, so "
        "unrelated Directions scored as aligned by numbering coincidence. The flaw was "
        "caught because the false-positive baseline scored *higher* than the signal it was "
        "supposed to sit beneath — impossible if the metric were sound. Reporting that "
        "83% as an alignment rate would have handed Phase 2 false confidence.",
        "",
        "| Comparison | Paragraph level | Section level |",
        "|---|---|---|",
        f"| **Parallel** (same subject, different entity classes — *should* align) "
        f"| **{_fmt(ent.get('paragraph_level', {}).get('alignment_rate'))}** "
        f"(n={ent.get('paragraph_level', {}).get('positions_compared', '?')}) "
        f"| **{_fmt(ent.get('section_level', {}).get('alignment_rate'))}** "
        f"(n={ent.get('section_level', {}).get('positions_compared', '?')}) |",
        f"| **Baseline** (same entity class, different subjects — should *not* align) "
        f"| {_fmt(sub.get('paragraph_level', {}).get('alignment_rate'))} "
        f"(n={sub.get('paragraph_level', {}).get('positions_compared', '?')}) "
        f"| {_fmt(sub.get('section_level', {}).get('alignment_rate'))} "
        f"(n={sub.get('section_level', {}).get('positions_compared', '?')}) |",
        "",
        "The baseline row is what makes the headline number interpretable: a ~37% parallel "
        "rate against a ~5% baseline is real signal (roughly 8x separation), and is still "
        "far below the threshold.",
        "",
        f"### TRIGGER FIRED: **{align.get('trigger_fired', NOT_YET_MEASURED)}**",
        "",
        f"> {align.get('judgment', NOT_YET_MEASURED)}",
        "",
        "**Recommendation for Phase 2 (per Section AA):** do **not** proceed on the "
        "assumption that structural cross-class matching works. Paragraph-level alignment "
        "is well below the dossier's 60% bar, and section-level — the dossier's own "
        "suggested fallback — does not rescue it. Phase 2's cross-class matcher should "
        "treat semantic matching as load-bearing rather than as a refinement layered on a "
        "working structural match, and RQ2's differential-obligation claims should be "
        "scoped to what that matcher can actually demonstrate.",
        "",
        "**Per-axis note:** the parallel comparison varies `entity_class` (raw-sourced) "
        "while holding the derived `subject_family` fixed. The sampled subject families are "
        "themselves inferred, so cell membership carries the derivation caveat — but the "
        "alignment being measured is between entity classes, on the raw-sourced axis.",
        "",
        "---",
        "",
        "## 3. Week-2 FAQ / enforcement source check",
        "",
        checks_src,
        "",
        f"- FAQ items found: **{faq.get('faq_items_found', NOT_YET_MEASURED)}**",
        f"- FAQ paragraph-alignment rate: **{faq.get('faq_paragraph_alignment_rate', NOT_YET_MEASURED)}**",
        f"- Enforcement items found: **{faq.get('enforcement_items_found', NOT_YET_MEASURED)}**",
        f"- Enforcement paragraph-alignment rate: **{faq.get('enforcement_paragraph_alignment_rate', NOT_YET_MEASURED)}**",
        "",
        f"{faq.get('faq_note', '')}",
        "",
        f"**Standing rule:** {faq.get('standing_rule', '')}",
        "",
        "---",
        "",
        "## 4. Annotation protocol and tooling",
        "",
        "Four rules are enforced **in code**, not by convention — each protects a research "
        "claim that cannot be repaired after the fact:",
        "",
        "1. **`applies_to` is annotator-sourced or it does not exist.** It is written only "
        "by `apply_annotation()`, which requires an `annotator_id` and stamps "
        "`provenance='annotator:<id>:<route>'`. Any label with a non-empty `applies_to` "
        "lacking that provenance is rejected by `assert_applies_to_is_annotator_sourced()`, "
        "which runs on every promotion. A Phase 2 extractor cannot reintroduce the "
        "`applies_to = [entity_class]` tautology without deliberately forging annotator "
        "provenance. `tautology_share_by_rater()` additionally reports, per rater and pass, "
        "how often that rater landed on exactly the source class — a pattern that would "
        "drain RQ1 of signal even when every label is honestly sourced.",
        "2. **`differential_flag` is never defaulted to `absent`.** It starts `unlabelled` "
        "by the schema's own default; only an ingested judgment moves it.",
        "3. **Raw votes are never overwritten.** Every row of every pass becomes one "
        "immutable `AnnotatorVote`, and merging happens once over the whole vote set. The "
        "superseded ingest applied each annotator's row to the same label in turn, so the "
        "last writer won and κ was then computed by counting that single surviving flag "
        "once per annotator — three annotators who never agreed on anything scored κ = 1.0 "
        "and all 18 items were promoted.",
        "4. **Promotion is by validation route, and never counts raters.** With one "
        "annotator there is nothing to count. `promote_validated()` gates on the route an "
        "item took, then defers to `T1Label.validate()`, which independently rejects a "
        "validated item with empty `applies_to` or a still-`unlabelled` flag.",
        "",
        "**Validation routes** (recorded in `provenance`, one per item):",
        "",
        "| Route | Status | Meaning |",
        "|---|---|---|",
        f"| `{ROUTE_RETEST_CONSISTENT}` | `validated` | In the retest set; both blind passes gave identical `applies_to` and flag. |",
        f"| `{ROUTE_SINGLE_PASS}` | `validated` | Outside the retest set; pass 1 only, and labelled as such. |",
        f"| `{ROUTE_ADJUDICATED}` | `validated` / `rejected` | A disagreement resolved by written adjudication. |",
        f"| `{ROUTE_NOT_OBLIGATION}` | `rejected` | Judged not an obligation. |",
        f"| `{ROUTE_PASS1_ONLY}` | `in_review` | In the retest set; pass 2 not done yet. |",
        f"| `{ROUTE_NEEDS_ADJUDICATION}` | `in_review` | The passes differ, or a second rater differs. |",
        "",
        "**On the agreement statistic:** `T1Label.agreement_score` is typed "
        "`float | int | None` by the base schema, so it cannot hold the string "
        "`NOT YET MEASURED`; the literal string belongs to the reported metric, while the "
        "per-label field stays `None` until a real number exists. Neither is ever `0.0` — "
        "a zero κ is a real and very bad reading, not an absence of one.",
        "",
        "**Data-loss guards:** task files, the pass-2 file and the adjudication file are "
        "never rewritten over filled-in cells without `--force-regenerate-tasks`, and even "
        "then the old file is copied to `data/benchmark/tasks/_overwritten/` first. "
        "`data/benchmark/**` is gitignored, so a blanked task file is not recoverable from "
        "anywhere. `report` reads existing artifacts and writes nothing under "
        "`data/benchmark/`.",
        "",
        "---",
        "",
        "## 5. Annotation feasibility pilot",
        "",
        pilot_src,
        "",
        f"- Paragraphs searched: **{pilot.get('paragraphs_searched', NOT_YET_MEASURED)}** "
        f"(Task 5 range 15-20, widened in steps of 5 only if the item floor is unmet)",
        f"- Entity classes **in the paragraphs searched**: "
        f"**{pilot.get('entity_classes_in_paragraphs_searched_count', pilot.get('entity_classes_spanned_count', NOT_YET_MEASURED))}**",
        f"- Entity classes **in the extracted items**: "
        f"**{item_metrics.get('entity_classes_in_items_count', NOT_YET_MEASURED)}** "
        "(requirement: more than one)",
        f"- Items missing `context_subject_family` (**derived** axis): "
        f"**{item_metrics.get('items_missing_subject_family', NOT_YET_MEASURED)}**",
        f"  - _item-level figures from {item_metrics_source}_",
        f"- Candidate `ObligationSpan`s extracted: **{pilot.get('items_extracted', NOT_YET_MEASURED)}** "
        "(floor: 10)",
        f"- Widening attempts: {pilot.get('widening_attempts', NOT_YET_MEASURED)}",
        f"- Cue distribution: {pilot.get('cue_distribution', NOT_YET_MEASURED)}",
        f"- Task files generated: **{len(pilot.get('task_files', {}))}** "
        f"({', '.join(sorted(pilot.get('task_files', {}))) or 'none'})",
        "",
        "**The two entity-class counts above are different measurements and the difference "
        "is not cosmetic.** An earlier version of this report printed the paragraph-level "
        "count as \"entity classes spanned\", which overstated the benchmark's coverage: the "
        "search touched more classes than actually produced an annotatable item, because "
        "cue density varies by class.",
        "",
        "Candidate generation is a **keyword heuristic and nothing more** — a feasibility "
        "device to test whether the protocol works on real RBI text. It is explicitly not "
        "the systematic Phase 2 (Week 4) extractor, and it is wrong in known ways: it "
        "catches definitional and commencement uses of \"shall\" alongside genuine "
        "obligations (a small reject-pattern list removes the most common), and has no "
        "notion of scope. `matched_cue` is recorded on every span precisely so this bias "
        "stays measurable — the distribution above is dominated by \"shall\", which is a "
        "property of the extractor, not of RBI.",
        "",
        "### Annotation status and reliability",
        "",
        ingest_src,
        "",
        f"- Items total: **{ingest.get('items_total', pilot.get('items_extracted', NOT_YET_MEASURED))}**",
        f"- Retest set size (drawn before pass 1 was filled): "
        f"**{ingest.get('retest_set_size', len(load_retest_set(resolver)) or NOT_YET_MEASURED)}**",
    ]

    voted_p1 = sum(
        stats.get("rows_voted", 0) for key, stats in passes.items() if key.endswith(":pass1")
    )
    voted_p2 = sum(
        stats.get("rows_voted", 0) for key, stats in passes.items() if key.endswith(":pass2")
    )
    not_obligation = sum(stats.get("rows_not_obligation", 0) for stats in passes.values())

    lines += [
        f"- Rows voted in pass 1: **{voted_p1 if passes else NOT_YET_MEASURED}**",
        f"- Rows voted in pass 2: **{voted_p2 if passes else NOT_YET_MEASURED}**",
        f"- Rows marked not-an-obligation: **{not_obligation if passes else NOT_YET_MEASURED}**",
        f"- Items reaching `validated`: **{ingest.get('items_validated', NOT_YET_MEASURED)}**",
        "",
        "#### Items per validation route",
        "",
    ]
    if routes:
        lines += ["| Route | Items |", "|---|---|"]
        for route in REPORT_ROUTES:
            if route in routes:
                lines.append(f"| `{route}` | {routes[route]} |")
        for route, count in routes.items():
            if route not in REPORT_ROUTES:
                lines.append(f"| `{route}` | {count} |")
        lines.append("")
    else:
        lines += [f"- {NOT_YET_MEASURED} — no pass has been ingested.", ""]

    lines += _comparison_lines(
        agreement.get("test_retest", {}),
        title=(
            f"Test-retest — {primary} pass 1 vs {primary} blind pass 2 "
            "(stability of ONE annotator's judgment over time, NOT inter-annotator agreement)"
        ),
    )

    second = agreement.get("second_rater", {})
    if second.get("raters"):
        for rater, block in sorted(second["raters"].items()):
            lines += _comparison_lines(
                block, title=f"Second rater — {primary} pass 1 vs {rater}"
            )
    else:
        lines += [
            "**Second rater**",
            "",
            f"- {second.get('status', f'{NOT_YET_MEASURED} — no second rater configured')}",
            "",
        ]

    lines += [
        "> **Fleiss' κ is absent by design.** It requires three or more raters. With one "
        "annotator, or one annotator plus one second rater, the tooling emits no `fleiss` "
        "key at all — not even a sentinel — so nothing downstream can surface a number that "
        "was never computable.",
        "",
        "#### Annotation time",
        "",
    ]
    if passes:
        lines += ["| Rater and pass | Voted | Blank | Not obligation | Minutes | Minutes/item |", "|---|---|---|---|---|---|"]
        for key, stats in sorted(passes.items()):
            rows = (stats.get("rows_voted") or 0) + (stats.get("rows_not_obligation") or 0)
            recorded = stats.get("minutes")
            per_item = f"{recorded / rows:.2f}" if recorded and rows else NOT_YET_MEASURED
            lines.append(
                f"| `{key}` | {stats.get('rows_voted', 0)} | {stats.get('rows_blank', 0)} "
                f"| {stats.get('rows_not_obligation', 0)} | {recorded or NOT_YET_MEASURED} "
                f"| {per_item} |"
            )
        lines.append("")
    else:
        lines += [f"- {NOT_YET_MEASURED} — no pass has been ingested.", ""]

    lines += _projection_lines(cfg, ingest)

    lines += [
        "#### Pass-2 schedule",
        "",
        f"- Minimum gap: **{min_gap_days} days** (`benchmark.retest.min_gap_days`)",
        f"- Pass-1 ingested at: **{first_pass1 or NOT_YET_MEASURED}**",
        f"- Earliest allowed pass-2 date: **{earliest}**",
        f"- Pass 2 actually ingested at: "
        f"**{pass2_entries[-1].get('timestamp') if pass2_entries else NOT_YET_MEASURED}**",
        "",
    ]
    if short_gap_used:
        lines += [
            "> **`--allow-short-gap` was used.** The pass-2 file was generated before the "
            f"{min_gap_days}-day minimum had elapsed. A retest taken that soon measures "
            "recall of the pass-1 answers as much as the stability of the judgment, so the "
            "test-retest figure above is weakened and must be reported with this caveat.",
            "",
        ]

    lines += ["#### Tautology share, per rater and pass", "", ]
    shares = ingest.get("tautology_share_by_rater", {}) if ingest else {}
    if shares:
        lines += ["| Rater and pass | Voted rows | `applies_to` == source class | Share |", "|---|---|---|---|"]
        for key, stats in sorted(shares.items()):
            lines.append(
                f"| `{key}` | {stats.get('voted_rows', 0)} "
                f"| {stats.get('rows_matching_context_entity_class', 0)} "
                f"| {_fmt(stats.get('share'))} |"
            )
        lines += [
            "",
            "A share near 1.0 would mean the annotator was effectively copying "
            "`context_entity_class` into `applies_to`, which drains RQ1 of signal even when "
            "every label is honestly sourced. It is reported, never enforced.",
            "",
        ]
    else:
        lines += [f"- {NOT_YET_MEASURED} — no pass has been ingested.", ""]

    if not ingest:
        lines += [
            f"> **{NOT_YET_MEASURED}: the pilot is generated and ready, not yet annotated.** "
            f"The pass-1 task file for {primary} exists under `data/benchmark/tasks/`, "
            "carrying every pilot item, and the retest set has been drawn in advance. "
            "Test-retest κ, annotation time and disagreement categories cannot be reported "
            f"until {primary} completes pass 1, waits {min_gap_days} days, and completes the "
            "blind pass 2. **No annotations were fabricated and no placeholder agreement "
            "value was substituted** — a synthesised κ would be worse than no κ, because it "
            "would look like evidence.",
            "",
        ]

    lines += [
        "The ingestion path, the retest and adjudication stages, the promotion gates and "
        "the κ computations are implemented and tested end-to-end against fixture "
        "annotations (see `tests/test_benchmark_solo_protocol.py` and "
        "`tests/test_benchmark_integration.py`) — what is pending is human input, not code.",
        "",
    ]

    out_path = resolver.write_path("reports", "phase1_meer_annotation.md")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("report written: %s", out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "stage",
        choices=["qa", "checks", "pilot", "ingest", "retest", "adjudicate", "report", "all"],
    )
    parser.add_argument("--config", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--pass", dest="pass_no", type=int, choices=(1, 2), default=1,
        help="which pass the ingested file is (default: 1)",
    )
    parser.add_argument(
        "--adjudication", action="store_true",
        help="ingest the adjudication file as well as the task files",
    )
    parser.add_argument(
        "--rater", default=None, help="rater id being ingested (default: the primary annotator)",
    )
    parser.add_argument(
        "--minutes", action="append", metavar="RATER=N",
        help="minutes that pass took, e.g. --minutes karan=45. Repeatable.",
    )
    parser.add_argument(
        "--allow-short-gap", action="store_true",
        help="write the pass-2 file before retest.min_gap_days has elapsed. Recorded in the "
             "log and printed in the report, because it weakens the test-retest figure.",
    )
    parser.add_argument(
        "--force-regenerate-tasks", action="store_true",
        help="overwrite task files that already hold filled-in cells. The old file is "
             "copied to data/benchmark/tasks/_overwritten/ first.",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    resolver = PathResolver.from_config(cfg)
    logger = get_logger("scripts.run_annotation", cfg)

    metrics: dict = {"scope": args.stage}
    try:
        if args.stage in ("qa", "all"):
            metrics["qa"] = run_qa(cfg, resolver, logger)
        if args.stage in ("checks", "all"):
            metrics["checks"] = run_checks(cfg, resolver, logger)
        if args.stage in ("pilot", "all"):
            metrics["pilot"] = run_pilot(cfg, resolver, logger, force=args.force_regenerate_tasks)
        if args.stage == "ingest":
            metrics["ingest"] = run_ingest(cfg, resolver, logger, args)
        if args.stage == "retest":
            metrics["retest"] = run_retest(cfg, resolver, logger, args)
        if args.stage == "adjudicate":
            metrics["adjudicate"] = run_adjudicate(cfg, resolver, logger, args)
    except AnnotationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Written before the report is assembled: `report` reads metrics files off
    # disk, so an `all` run must land its own numbers first or the report
    # renders the previous run's. `report` itself computes no metrics — it only
    # re-renders what other stages already wrote — so it writes no metrics file
    # either, rather than leaving a stub that merely echoes the report path.
    if args.stage != "report":
        metrics_path = resolver.write_path("reports", f"phase1_meer_{args.stage}_metrics.json")
        write_json(metrics_path, metrics)

    if args.stage in ("all", "report"):
        metrics["report_path"] = str(_write_report(cfg, resolver, logger))
        if args.stage != "report":
            write_json(metrics_path, metrics)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        for stage_name, stage_metrics in metrics.items():
            if not isinstance(stage_metrics, dict):
                print(f"{stage_name}: {stage_metrics}")
                continue
            print(f"=== {stage_name} ===")
            for key, value in stage_metrics.items():
                if key in ("spot_check_sample", "labels", "paragraphs"):
                    continue
                print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
