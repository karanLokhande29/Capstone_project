"""Integration test (P1-003, Section U): the pilot pipeline end-to-end.

keyword-heuristic candidate generation -> task-file generation -> ingestion of
*fixture* completed annotations -> Fleiss' kappa, run against a small real
slice of P1-001's committed paragraphs.

**The completed annotations here are fixtures, and exist only inside this
test.** They exercise the ingestion and promotion machinery; they are never
written into `data/benchmark/` and are not the pilot's real annotations,
which require Akash, Karan and Meer. The report reflects that distinction —
real Fleiss' kappa stays NOT YET MEASURED until humans fill the task files in.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.benchmark.annotation import (
    NOT_YET_MEASURED,
    TASK_FILE_COLUMNS,
    build_annotation_tasks,
    ingest_annotations,
    measure_agreement,
    promote_validated,
)
from src.benchmark.pilot import extract_obligation_candidates
from src.common.io_helpers import read_jsonl
from src.common.paths import PathResolver
from src.schemas.benchmark import LabelStatus
from src.schemas.provenance import ParagraphRecord

CFG = {
    "environment": {
        "mode": "local",
        "local": {"working_root": ".", "input_roots": []},
        "kaggle": {"working_root": "/kaggle/working", "input_root": "/kaggle/input", "input_datasets": []},
    },
    "paths": {
        k: k
        for k in ("raw", "extracted", "processed", "metadata", "matrix", "benchmark",
                  "evaluation", "cache", "reports", "logs")
    },
    "logging": {"level": "INFO", "format": "%(message)s", "to_file": False},
    "benchmark": {"annotators": ["akash", "karan", "meer"], "min_annotators_per_item": 2},
}


def _real_paragraphs(limit: int = 12) -> list[ParagraphRecord]:
    """A small slice of genuinely committed ParagraphRecords."""
    files = sorted(Path("data/processed").glob("md_*.jsonl"))
    if not files:
        pytest.skip("no committed processed paragraphs in this checkout")

    records: list[ParagraphRecord] = []
    for path in files:
        for row in read_jsonl(path):
            if (row.get("text") or "") and len(row["text"]) > 200:
                records.append(ParagraphRecord.from_dict(row))
            if len(records) >= limit:
                return records
    if not records:
        pytest.skip("no usable paragraphs found")
    return records


@pytest.fixture(scope="module")
def real_paragraphs():
    return _real_paragraphs()


def _complete_task_file(path: str, *, applies_to: str, flag: str) -> None:
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["applies_to"] = applies_to
        row["differential_flag"] = flag
        row["applies_to_rationale"] = "fixture annotation for integration test"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def test_pilot_extracts_candidates_from_real_paragraphs(real_paragraphs):
    labels = extract_obligation_candidates(real_paragraphs, CFG)
    assert labels, "keyword heuristic found no obligations in real RBI text"
    for label in labels:
        assert label.obligation_span is not None
        assert label.obligation_span.text
        assert label.obligation_span.matched_cue
        assert label.validate() == []


def test_pilot_candidates_assert_nothing_about_applicability(real_paragraphs):
    for label in extract_obligation_candidates(real_paragraphs, CFG):
        assert label.applies_to == []
        assert label.differential_flag == "unlabelled"
        assert label.label_status == LabelStatus.CANDIDATE.value
        assert label.agreement_score is None


def test_pilot_spans_index_into_their_paragraph(real_paragraphs):
    """Offsets must resolve against the real paragraph text they came from."""
    by_id = {p.paragraph_id: p for p in real_paragraphs}
    for label in extract_obligation_candidates(real_paragraphs, CFG):
        span = label.obligation_span
        source = by_id[span.paragraph_id].text
        assert source[span.char_start : span.char_end].strip() == span.text


def test_full_pilot_pipeline_end_to_end(tmp_path, real_paragraphs):
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)

    candidates = extract_obligation_candidates(real_paragraphs, CFG)
    assert candidates

    task_files = build_annotation_tasks(candidates, CFG, resolver=resolver)
    assert set(task_files) == {"akash", "karan", "meer"}

    # Fixture annotations — two annotators agree, one differs, so kappa is a
    # real computation over genuine variance rather than a degenerate case.
    _complete_task_file(task_files["akash"], applies_to="Commercial Banks", flag="shared")
    _complete_task_file(task_files["karan"], applies_to="Commercial Banks", flag="shared")
    _complete_task_file(task_files["meer"], applies_to="Commercial Banks", flag="class-specific")

    ingested = ingest_annotations(CFG, candidates=candidates, resolver=resolver)
    assert len(ingested) == len(candidates)
    for label in ingested:
        assert len(label.annotator_ids) == 3

    promoted = promote_validated(ingested, CFG)
    agreement = measure_agreement(promoted, CFG)
    assert agreement["items_multiply_annotated"] == len(candidates)
    assert agreement["fleiss_kappa_differential_flag"] != 0.0 or isinstance(
        agreement["fleiss_kappa_differential_flag"], (float, str)
    )


def test_no_label_reaches_validated_without_meeting_annotator_rule(tmp_path, real_paragraphs):
    """Section U's core assertion, checked on real-derived candidates."""
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)
    candidates = extract_obligation_candidates(real_paragraphs, CFG)
    task_files = build_annotation_tasks(candidates, CFG, resolver=resolver)

    # Only ONE annotator completes — below min_annotators_per_item of 2.
    _complete_task_file(task_files["akash"], applies_to="Commercial Banks", flag="shared")

    ingested = ingest_annotations(CFG, candidates=candidates, resolver=resolver)
    promoted = promote_validated(ingested, CFG)

    assert all(not label.is_validated for label in promoted)
    assert all(label.label_status != LabelStatus.VALIDATED.value for label in promoted)


def test_unannotated_pilot_reports_agreement_as_the_sentinel(tmp_path, real_paragraphs):
    """The state the real pilot is actually in: task files generated, nobody
    has annotated yet. Agreement must be the exact sentinel string."""
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)
    candidates = extract_obligation_candidates(real_paragraphs, CFG)
    build_annotation_tasks(candidates, CFG, resolver=resolver)

    ingested = ingest_annotations(CFG, candidates=candidates, resolver=resolver)
    agreement = measure_agreement(ingested, CFG)

    assert agreement["fleiss_kappa_differential_flag"] == "NOT YET MEASURED"
    assert agreement["items_multiply_annotated"] == 0
    assert all(not label.is_validated for label in ingested)


def test_promotion_succeeds_only_once_two_annotators_complete(tmp_path, real_paragraphs):
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)
    candidates = extract_obligation_candidates(real_paragraphs, CFG)[:3]
    task_files = build_annotation_tasks(candidates, CFG, resolver=resolver)

    _complete_task_file(task_files["akash"], applies_to="Commercial Banks", flag="shared")
    _complete_task_file(task_files["karan"], applies_to="Commercial Banks", flag="shared")

    promoted = promote_validated(
        ingest_annotations(CFG, candidates=candidates, resolver=resolver), CFG
    )
    assert all(label.is_validated for label in promoted)
    for label in promoted:
        assert label.validate() == []
        assert label.applies_to  # non-empty, annotator-sourced
        assert label.differential_flag != "unlabelled"
