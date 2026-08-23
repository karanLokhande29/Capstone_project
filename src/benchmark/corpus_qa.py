"""Independent corpus QA over the committed ParagraphRecord set.

This is a **second opinion** on P1-001's pipeline, not a re-run of its own
metrics: it streams the committed per-document JSONL files and recomputes
quality figures from the data as it actually landed on disk, so a discrepancy
between these numbers and Akash's reported ones would itself be the finding.

Streams rather than loads: the corpus is ~52k paragraphs, and materialising
it wholesale is both slow and (per this prompt's context guardrail)
unnecessary — only aggregates and a small sample ever need to exist at once.
"""

from __future__ import annotations

import json
import logging
import random
from collections import Counter
from pathlib import Path
from typing import Any, Iterator, Mapping

from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.schemas.provenance import ParagraphRecord

BRANCH = "phase1/meer-annotation"


def iter_paragraph_records(resolver: PathResolver) -> Iterator[dict[str, Any]]:
    """Stream every committed paragraph record, one dict at a time."""
    processed_dir = resolver.write_dir("processed", create=False)
    for path in sorted(Path(processed_dir).glob("md_*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def run_corpus_qa(
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    spot_check_size: int = 10,
    seed: int = 20260823,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Recompute corpus quality aggregates and draw a spot-check sample.

    The spot-check sample is drawn with a fixed seed via reservoir sampling
    (so it is reproducible and needs one pass, not two) and carries each
    paragraph's ``source_url`` so a human can compare the extracted text
    against the published PDF — the one check that cannot be automated.
    """
    logger = logger or get_logger("benchmark.corpus_qa", cfg)
    resolver = resolver or PathResolver.from_config(cfg)
    rng = random.Random(seed)

    total = 0
    missing_section_id = 0
    missing_clause_path = 0
    missing_text = 0
    missing_source_url = 0
    missing_entity_class = 0
    missing_subject_family = 0
    id_counts: Counter[str] = Counter()
    documents: set[str] = set()
    entity_classes: Counter[str] = Counter()
    reservoir: list[dict[str, Any]] = []

    for record in iter_paragraph_records(resolver):
        total += 1
        id_counts[record["paragraph_id"]] += 1
        documents.add(record["document_id"])

        if not record.get("section_id"):
            missing_section_id += 1
        if not record.get("clause_path"):
            missing_clause_path += 1
        if not (record.get("text") or "").strip():
            missing_text += 1
        if not record.get("source_url"):
            missing_source_url += 1
        if not record.get("entity_class"):
            missing_entity_class += 1
        else:
            entity_classes[record["entity_class"]] += 1
        if not record.get("subject_family"):
            missing_subject_family += 1

        if len(reservoir) < spot_check_size:
            reservoir.append(record)
        else:
            j = rng.randrange(total)
            if j < spot_check_size:
                reservoir[j] = record

    duplicates = {pid: count for pid, count in id_counts.items() if count > 1}

    spot_check = [
        {
            "paragraph_id": r["paragraph_id"],
            "document_id": r["document_id"],
            "source_url": r.get("source_url"),
            "section_id": r.get("section_id"),
            "clause_path": r.get("clause_path"),
            "text_excerpt": (r.get("text") or "")[:240],
        }
        for r in reservoir
    ]

    def rate(n: int) -> Any:
        return (n / total) if total else "NOT YET MEASURED"

    metrics = {
        "paragraphs_total": total,
        "documents_represented": len(documents),
        "distinct_entity_classes_in_paragraphs": len(entity_classes),
        "missing_section_id": missing_section_id,
        "missing_section_id_rate": rate(missing_section_id),
        "missing_clause_path": missing_clause_path,
        "missing_clause_path_rate": rate(missing_clause_path),
        "empty_text": missing_text,
        "missing_source_url": missing_source_url,
        "missing_entity_class": missing_entity_class,
        "missing_entity_class_rate": rate(missing_entity_class),
        "missing_subject_family": missing_subject_family,
        "missing_subject_family_rate": rate(missing_subject_family),
        "duplicate_paragraph_ids": len(duplicates),
        "duplicate_examples": dict(list(duplicates.items())[:5]),
        "spot_check_sample_size": len(spot_check),
        "spot_check_sample": spot_check,
    }

    logger.info(
        "corpus_qa: %d paragraphs across %d documents; missing section_id %.4f, "
        "duplicate ids %d, empty text %d",
        total, len(documents), metrics["missing_section_id_rate"]
        if isinstance(metrics["missing_section_id_rate"], float) else -1.0,
        len(duplicates), missing_text,
    )
    return metrics


def validate_sample_against_schema(resolver: PathResolver, limit: int = 500) -> dict[str, Any]:
    """Round-trip a slice of committed records through ParagraphRecord.validate().

    Catches drift between what the pipeline wrote and what the shared schema
    says it should have written — a class of error that the producing branch's
    own metrics would not surface.
    """
    checked = 0
    invalid: list[dict[str, Any]] = []
    for record in iter_paragraph_records(resolver):
        if checked >= limit:
            break
        checked += 1
        errors = ParagraphRecord.from_dict(record).validate()
        if errors:
            invalid.append({"paragraph_id": record.get("paragraph_id"), "errors": errors})

    return {
        "records_schema_checked": checked,
        "records_failing_validation": len(invalid),
        "failures": invalid[:5],
    }
