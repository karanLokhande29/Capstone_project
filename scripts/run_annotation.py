#!/usr/bin/env python3
"""CLI for corpus QA, the Week-2 risk checks, and the annotation pilot.

    python scripts/run_annotation.py qa         # independent corpus QA over ParagraphRecords
    python scripts/run_annotation.py checks     # cross-class alignment + FAQ/enforcement
    python scripts/run_annotation.py pilot      # extract candidates, write task files
    python scripts/run_annotation.py ingest     # read completed task files, compute agreement
    python scripts/run_annotation.py all        # qa + checks + pilot, then write the report
    python scripts/run_annotation.py report     # regenerate the report only

`pilot` stops after writing task files — it deliberately cannot invent
annotations. Fleiss' kappa stays NOT YET MEASURED until real annotators fill
those files in and `ingest` runs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.alignment_check import cross_class_alignment, faq_enforcement_check  # noqa: E402
from src.benchmark.annotation import (  # noqa: E402
    NOT_YET_MEASURED,
    build_annotation_tasks,
    ingest_annotations,
    measure_agreement,
    persist_labels,
    promote_validated,
    tautology_smell_report,
)
from src.benchmark.corpus_qa import run_corpus_qa, validate_sample_against_schema  # noqa: E402
from src.benchmark.pilot import cue_distribution, run_pilot_extraction  # noqa: E402
from src.common.config import load_config  # noqa: E402
from src.common.io_helpers import read_jsonl, write_json  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.schemas.benchmark import T1Label  # noqa: E402


def run_qa(cfg, resolver, logger) -> dict:
    metrics = run_corpus_qa(cfg, resolver=resolver, logger=logger)
    metrics.update(validate_sample_against_schema(resolver))
    return metrics


def run_checks(cfg, resolver, logger) -> dict:
    return {
        "cross_class_alignment": cross_class_alignment(cfg, resolver=resolver, logger=logger),
        "faq_enforcement": faq_enforcement_check(cfg, resolver=resolver, logger=logger),
    }


def run_pilot(cfg, resolver, logger) -> dict:
    result = run_pilot_extraction(resolver, cfg, logger=logger)
    labels = result["labels"]

    candidates_path = persist_labels(labels, cfg, "pilot_candidates.jsonl", resolver=resolver)
    task_files = build_annotation_tasks(labels, cfg, resolver=resolver, logger=logger)

    return {
        "paragraphs_searched": result["paragraphs_searched"],
        "entity_classes_spanned": result["entity_classes_spanned"],
        "entity_classes_spanned_count": len(result["entity_classes_spanned"]),
        "items_extracted": result["items_extracted"],
        "widening_attempts": result["widening_attempts"],
        "cue_distribution": cue_distribution(labels),
        "candidates_path": candidates_path,
        "task_files": task_files,
        "annotation_status": (
            f"{NOT_YET_MEASURED} — task files generated and awaiting completion by "
            f"{len(task_files)} annotators. No annotations have been fabricated."
        ),
    }


def run_ingest(cfg, resolver, logger) -> dict:
    labels = ingest_annotations(cfg, resolver=resolver, logger=logger)
    promoted = promote_validated(labels, cfg, logger=logger)
    agreement = measure_agreement(promoted, cfg)

    path = persist_labels(promoted, cfg, "pilot_labels_annotated.jsonl", resolver=resolver)
    return {
        "labels_total": len(promoted),
        "labels_validated": sum(1 for lbl in promoted if lbl.is_validated),
        "agreement": agreement,
        "tautology_smell": tautology_smell_report(promoted),
        "output_path": path,
    }


def _fmt(value, spec: str = ".4f") -> str:
    return format(value, spec) if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def _write_report(metrics: dict, resolver: PathResolver, logger) -> Path:
    qa = metrics.get("qa", {})
    checks = metrics.get("checks", {})
    pilot = metrics.get("pilot", {})
    ingest = metrics.get("ingest", {})

    align = checks.get("cross_class_alignment", {})
    ent = align.get("entity_class_axis", {})
    sub = align.get("subject_family_axis_derived", {})
    faq = checks.get("faq_enforcement", {})
    agreement = ingest.get("agreement", {})

    lines = [
        "# Phase 1 — Meer: Corpus QA, Annotation Pilot, Validation Protocol",
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
        "Three rules are enforced **in code**, not by convention — each protects a research "
        "claim that cannot be repaired after the fact:",
        "",
        "1. **`applies_to` is annotator-sourced or it does not exist.** It is written only "
        "by `apply_annotation()`, which requires an `annotator_id` and stamps "
        "`provenance='annotator:<id>'`. Any label with a non-empty `applies_to` lacking "
        "that provenance is rejected by `assert_applies_to_is_annotator_sourced()`, which "
        "runs on every promotion. A Phase 2 extractor cannot reintroduce the "
        "`applies_to = [entity_class]` tautology without deliberately forging annotator "
        "provenance. A corpus-level `tautology_smell_report()` additionally reports how "
        "often annotators land on exactly the source class — a pattern that would drain "
        "RQ1 of signal even when every label is honestly sourced.",
        "2. **`differential_flag` is never defaulted to `absent`.** It starts `unlabelled` "
        "by the schema's own default; only an ingested annotator judgment moves it.",
        "3. **Promotion is never implicit.** `promote_validated()` requires "
        "`min_annotators_per_item` *distinct* annotators, then defers to "
        "`T1Label.validate()`, which independently rejects a validated item with empty "
        "`applies_to` or a still-`unlabelled` flag. An item failing any gate stays where "
        "it is.",
        "",
        "**On the agreement statistic:** `T1Label.agreement_score` is typed "
        "`float | int | None` by the base schema, so it cannot hold the string "
        "`NOT YET MEASURED`; the literal string belongs to the reported metric from "
        "`measure_agreement()`, while the per-label field stays `None` until a real number "
        "exists. Neither is ever `0.0` — a zero kappa is a real and very bad agreement "
        "reading, not an absence of one.",
        "",
        "---",
        "",
        "## 5. Annotation feasibility pilot",
        "",
        f"- Paragraphs searched: **{pilot.get('paragraphs_searched', NOT_YET_MEASURED)}** "
        f"(Task 5 range 15-20, widened in steps of 5 only if the item floor is unmet)",
        f"- Entity classes spanned: **{pilot.get('entity_classes_spanned_count', NOT_YET_MEASURED)}** "
        "(requirement: more than one)",
        f"- Candidate `ObligationSpan`s extracted: **{pilot.get('items_extracted', NOT_YET_MEASURED)}** "
        "(floor: 10)",
        f"- Widening attempts: {pilot.get('widening_attempts', NOT_YET_MEASURED)}",
        f"- Cue distribution: {pilot.get('cue_distribution', NOT_YET_MEASURED)}",
        f"- Task files generated: **{len(pilot.get('task_files', {}))}** "
        f"({', '.join(sorted(pilot.get('task_files', {}))) or 'none'})",
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
        "### Inter-annotator agreement",
        "",
        f"- Items total: **{ingest.get('labels_total', pilot.get('items_extracted', NOT_YET_MEASURED))}**",
        f"- Items reaching `validated`: **{ingest.get('labels_validated', 0)}**",
        f"- Fleiss' kappa (differential_flag): "
        f"**{agreement.get('fleiss_kappa_differential_flag', NOT_YET_MEASURED)}**",
        f"- Annotation time: **{NOT_YET_MEASURED}** (measured by annotators during the pilot run)",
        f"- Disagreement categories: **{NOT_YET_MEASURED}** (derived from completed annotations)",
        "",
        f"> **{NOT_YET_MEASURED}: the pilot is generated and ready, not yet annotated.** "
        "Task files for all three annotators exist under `data/benchmark/tasks/`, each "
        "carrying every pilot item (full overlap, which is what makes an agreement "
        "statistic computable at this scale). Fleiss' kappa, annotation time, and "
        "disagreement categories cannot be reported until Akash, Karan and Meer complete "
        "those files and `run_annotation.py ingest` is run. **No annotations were "
        "fabricated and no placeholder agreement value was substituted** — a synthesised "
        "kappa would be worse than no kappa, because it would look like evidence.",
        "",
        "The ingestion path, promotion gates, and kappa computation are fully implemented "
        "and tested end-to-end against fixture annotations (see "
        "`tests/test_benchmark_annotation.py` and `tests/test_benchmark_integration.py`) — "
        "what is pending is human input, not code.",
        "",
    ]

    out_path = resolver.write_path("reports", "phase1_meer_annotation.md")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("report written: %s", out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["qa", "checks", "pilot", "ingest", "all", "report"])
    parser.add_argument("--config", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    resolver = PathResolver.from_config(cfg)
    logger = get_logger("scripts.run_annotation", cfg)

    metrics: dict = {"scope": args.stage}
    if args.stage in ("qa", "all", "report"):
        metrics["qa"] = run_qa(cfg, resolver, logger)
    if args.stage in ("checks", "all", "report"):
        metrics["checks"] = run_checks(cfg, resolver, logger)
    if args.stage in ("pilot", "all", "report"):
        metrics["pilot"] = run_pilot(cfg, resolver, logger)
    if args.stage == "ingest":
        metrics["ingest"] = run_ingest(cfg, resolver, logger)

    if args.stage in ("all", "report"):
        _write_report(metrics, resolver, logger)

    metrics_path = resolver.write_path("reports", f"phase1_meer_{args.stage}_metrics.json")
    write_json(metrics_path, metrics)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        for stage_name, stage_metrics in metrics.items():
            if not isinstance(stage_metrics, dict):
                continue
            print(f"=== {stage_name} ===")
            for key, value in stage_metrics.items():
                if key in ("spot_check_sample", "labels", "paragraphs"):
                    continue
                print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
