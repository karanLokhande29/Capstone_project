"""Tests for src.benchmark.annotation — the protocol's enforcement rules.

These guard the three rules that protect research claims: applies_to must be
annotator-sourced, differential_flag must never default to absent, and
promotion must never be implicit. Fixtures only, no network.
"""

from __future__ import annotations

import csv

import pytest

from src.benchmark.annotation import (
    ANNOTATOR_PROVENANCE_PREFIX,
    NOT_YET_MEASURED,
    TASK_FILE_COLUMNS,
    AnnotationError,
    TautologyGuardError,
    apply_annotation,
    assert_applies_to_is_annotator_sourced,
    build_annotation_tasks,
    fleiss_kappa,
    ingest_annotations,
    make_candidate,
    measure_agreement,
    promote_validated,
    tautology_smell_report,
)
from src.common.paths import PathResolver
from src.schemas.benchmark import DifferentialFlag, LabelStatus, ObligationSpan, T1Label

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


def _span(paragraph_id="md_1::p00000", document_id="md_1"):
    return ObligationSpan(
        paragraph_id=paragraph_id, document_id=document_id,
        char_start=0, char_end=40, text="Banks shall maintain records.", matched_cue="shall",
    )


def _candidate(label_id="t1_0001", entity_class="Commercial Banks"):
    return make_candidate(label_id, _span(), entity_class=entity_class, subject_family="KYC")


def _resolver(tmp_path):
    return PathResolver.from_config(CFG, repo_root=tmp_path)


# -- construction defaults ----------------------------------------------------


def test_candidate_asserts_nothing_about_applicability():
    label = _candidate()
    assert label.applies_to == []
    assert label.differential_flag == DifferentialFlag.UNLABELLED.value
    assert label.label_status == LabelStatus.CANDIDATE.value
    assert label.is_valid()


def test_candidate_differential_flag_is_never_absent_by_default():
    """Defaulting to 'absent' would turn every unexamined item into a positive
    finding. It must start 'unlabelled'."""
    assert _candidate().differential_flag != DifferentialFlag.ABSENT.value
    assert _candidate().differential_flag == "unlabelled"


def test_agreement_score_field_starts_none_not_zero():
    """0.0 is a real (terrible) agreement reading, not an absence of one."""
    assert _candidate().agreement_score is None


# -- T1Label.validate() gates (base-schema enforcement) -----------------------


def test_validate_rejects_validated_with_empty_applies_to():
    label = T1Label(
        label_id="t1", label_status=LabelStatus.VALIDATED.value,
        annotator_ids=["akash", "karan"], differential_flag=DifferentialFlag.SHARED.value,
    )
    assert any("applies_to" in e for e in label.validate())


def test_validate_rejects_validated_with_unlabelled_differential_flag():
    label = T1Label(
        label_id="t1", label_status=LabelStatus.VALIDATED.value,
        annotator_ids=["akash", "karan"], applies_to=["Commercial Banks"],
    )
    assert any("unlabelled" in e for e in label.validate())


def test_validate_rejects_validated_with_no_annotators():
    label = T1Label(
        label_id="t1", label_status=LabelStatus.VALIDATED.value,
        applies_to=["Commercial Banks"], differential_flag=DifferentialFlag.SHARED.value,
    )
    assert any("annotator_ids" in e for e in label.validate())


# -- tautology guard ----------------------------------------------------------


def test_tautology_guard_rejects_applies_to_without_annotator_provenance():
    """The exact failure mode: applies_to copy-derived from entity_class."""
    label = T1Label(
        label_id="t1", entity_class="Commercial Banks",
        applies_to=["Commercial Banks"], provenance="pilot:keyword_heuristic_v1",
    )
    with pytest.raises(TautologyGuardError, match="annotator provenance"):
        assert_applies_to_is_annotator_sourced(label)


def test_tautology_guard_allows_empty_applies_to():
    assert_applies_to_is_annotator_sourced(_candidate())  # must not raise


def test_tautology_guard_allows_annotator_sourced_applies_to():
    label = apply_annotation(
        _candidate(), annotator_id="akash",
        applies_to=["Commercial Banks"], differential_flag=DifferentialFlag.SHARED.value,
    )
    assert_applies_to_is_annotator_sourced(label)  # must not raise
    assert label.provenance.startswith(ANNOTATOR_PROVENANCE_PREFIX)


def test_tautology_smell_report_flags_applies_to_matching_own_class():
    labels = [
        apply_annotation(_candidate("t1"), annotator_id="a",
                         applies_to=["Commercial Banks"], differential_flag="shared"),
        apply_annotation(_candidate("t2"), annotator_id="a",
                         applies_to=["Commercial Banks", "Small Finance Banks"],
                         differential_flag="shared"),
    ]
    report = tautology_smell_report(labels)
    assert report["annotated_items"] == 2
    assert report["items_matching_own_entity_class"] == 1
    assert report["share_matching_own_entity_class"] == pytest.approx(0.5)


def test_tautology_smell_report_on_unannotated_set():
    report = tautology_smell_report([_candidate()])
    assert report["annotated_items"] == 0
    assert report["share_matching_own_entity_class"] == NOT_YET_MEASURED


# -- apply_annotation ---------------------------------------------------------


def test_apply_annotation_moves_to_in_review_never_straight_to_validated():
    label = apply_annotation(_candidate(), annotator_id="akash",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    assert label.label_status == LabelStatus.IN_REVIEW.value
    assert label.label_status != LabelStatus.VALIDATED.value


def test_apply_annotation_requires_annotator_id():
    with pytest.raises(AnnotationError, match="annotator_id"):
        apply_annotation(_candidate(), annotator_id="",
                         applies_to=["Commercial Banks"], differential_flag="shared")


def test_apply_annotation_rejects_invalid_differential_flag():
    with pytest.raises(AnnotationError, match="differential_flag"):
        apply_annotation(_candidate(), annotator_id="akash",
                         applies_to=["Commercial Banks"], differential_flag="probably")


def test_apply_annotation_accumulates_distinct_annotators():
    label = apply_annotation(_candidate(), annotator_id="akash",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    label = apply_annotation(label, annotator_id="karan",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    label = apply_annotation(label, annotator_id="akash",  # repeat must not double-count
                             applies_to=["Commercial Banks"], differential_flag="shared")
    assert label.annotator_ids == ["akash", "karan"]
    assert label.annotation_count == 2


# -- promotion ----------------------------------------------------------------


def test_promotion_rejected_below_min_annotators():
    label = apply_annotation(_candidate(), annotator_id="akash",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    result = promote_validated([label], CFG)[0]
    assert result.label_status == LabelStatus.IN_REVIEW.value
    assert not result.is_validated


def test_promotion_succeeds_at_min_annotators():
    label = apply_annotation(_candidate(), annotator_id="akash",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    label = apply_annotation(label, annotator_id="karan",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    result = promote_validated([label], CFG)[0]
    assert result.is_validated
    assert result.validate() == []


def test_promotion_rejects_forged_applies_to_even_with_enough_annotators():
    """Annotator count alone is not sufficient — the tautology guard also runs."""
    forged = T1Label(
        label_id="t1", entity_class="Commercial Banks", applies_to=["Commercial Banks"],
        differential_flag="shared", annotator_ids=["akash", "karan"],
        provenance="machine:copied_from_entity_class",
    )
    with pytest.raises(TautologyGuardError):
        promote_validated([forged], CFG)


def test_promotion_rejects_item_failing_schema_validation():
    """Enough annotators but still 'unlabelled' -> validate() blocks it."""
    label = T1Label(
        label_id="t1", applies_to=["Commercial Banks"],
        differential_flag=DifferentialFlag.UNLABELLED.value,
        annotator_ids=["akash", "karan"], provenance=f"{ANNOTATOR_PROVENANCE_PREFIX}akash",
    )
    result = promote_validated([label], CFG)[0]
    assert not result.is_validated


def test_promotion_respects_a_higher_configured_threshold():
    cfg = {**CFG, "benchmark": {**CFG["benchmark"], "min_annotators_per_item": 3}}
    label = apply_annotation(_candidate(), annotator_id="akash",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    label = apply_annotation(label, annotator_id="karan",
                             applies_to=["Commercial Banks"], differential_flag="shared")
    assert not promote_validated([label], cfg)[0].is_validated


# -- Fleiss' kappa ------------------------------------------------------------


def test_fleiss_kappa_perfect_agreement():
    assert fleiss_kappa([[3, 0], [0, 3]]) == pytest.approx(1.0)


def test_fleiss_kappa_total_disagreement():
    assert fleiss_kappa([[1, 1], [1, 1]]) == pytest.approx(-1.0)


def test_fleiss_kappa_not_measurable_when_no_items():
    assert fleiss_kappa([]) == NOT_YET_MEASURED


def test_fleiss_kappa_not_measurable_with_single_rater():
    assert fleiss_kappa([[1, 0], [0, 1]]) == NOT_YET_MEASURED


def test_fleiss_kappa_not_measurable_when_expected_agreement_is_one():
    """Unanimous on one category across every item: kappa is undefined
    (zero denominator), not 0.0."""
    assert fleiss_kappa([[3, 0], [3, 0]]) == NOT_YET_MEASURED


def test_fleiss_kappa_rejects_unequal_rater_counts():
    with pytest.raises(AnnotationError, match="equal number of raters"):
        fleiss_kappa([[3, 0], [2, 0]])


# -- measure_agreement --------------------------------------------------------


def test_measure_agreement_is_exactly_the_sentinel_string_when_unannotated():
    """Strict equality on the exact string — never 0.0, None, NaN, or any
    other falsy placeholder that a truthiness check would let through."""
    result = measure_agreement([_candidate()], CFG)
    kappa = result["fleiss_kappa_differential_flag"]
    assert kappa == "NOT YET MEASURED"
    assert isinstance(kappa, str)
    assert kappa is not None
    assert kappa != 0.0
    assert kappa is not False


def test_measure_agreement_reports_zero_multiply_annotated():
    result = measure_agreement([_candidate()], CFG)
    assert result["items_multiply_annotated"] == 0
    assert NOT_YET_MEASURED in result["reason"]


def test_measure_agreement_computes_once_items_are_multiply_annotated():
    labels = []
    for i, flag in enumerate(["shared", "class-specific"]):
        label = apply_annotation(_candidate(f"t{i}"), annotator_id="akash",
                                 applies_to=["Commercial Banks"], differential_flag=flag)
        label = apply_annotation(label, annotator_id="karan",
                                 applies_to=["Commercial Banks"], differential_flag=flag)
        labels.append(label)
    result = measure_agreement(labels, CFG)
    assert result["items_multiply_annotated"] == 2
    assert isinstance(result["fleiss_kappa_differential_flag"], (float, str))


# -- task files: generation and ingestion round-trip --------------------------


def test_build_annotation_tasks_writes_one_file_per_annotator(tmp_path):
    resolver = _resolver(tmp_path)
    paths = build_annotation_tasks([_candidate()], CFG, resolver=resolver)
    assert set(paths) == {"akash", "karan", "meer"}
    for path in paths.values():
        assert tmp_path in __import__("pathlib").Path(path).parents


def test_task_files_leave_annotator_columns_blank(tmp_path):
    resolver = _resolver(tmp_path)
    paths = build_annotation_tasks([_candidate()], CFG, resolver=resolver)
    with open(paths["akash"], newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert list(row) == list(TASK_FILE_COLUMNS)
    assert row["applies_to"] == ""
    assert row["differential_flag"] == ""
    assert row["label_id"] == "t1_0001"
    assert row["context_entity_class"] == "Commercial Banks"


def test_build_annotation_tasks_rejects_empty_roster(tmp_path):
    cfg = {**CFG, "benchmark": {"annotators": [], "min_annotators_per_item": 2}}
    with pytest.raises(AnnotationError, match="annotators"):
        build_annotation_tasks([_candidate()], cfg, resolver=_resolver(tmp_path))


def test_build_annotation_tasks_rejects_empty_sample(tmp_path):
    with pytest.raises(AnnotationError, match="empty sample"):
        build_annotation_tasks([], CFG, resolver=_resolver(tmp_path))


def _fill_task_file(path, *, applies_to, flag, rationale="because"):
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["applies_to"] = applies_to
        row["differential_flag"] = flag
        row["applies_to_rationale"] = rationale
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def test_task_file_round_trip(tmp_path):
    resolver = _resolver(tmp_path)
    candidates = [_candidate()]
    paths = build_annotation_tasks(candidates, CFG, resolver=resolver)
    _fill_task_file(paths["akash"], applies_to="Commercial Banks;Small Finance Banks", flag="shared")
    _fill_task_file(paths["karan"], applies_to="Commercial Banks;Small Finance Banks", flag="shared")

    ingested = ingest_annotations(CFG, candidates=candidates, resolver=resolver)
    assert len(ingested) == 1
    label = ingested[0]
    assert label.applies_to == ["Commercial Banks", "Small Finance Banks"]
    assert label.differential_flag == "shared"
    assert set(label.annotator_ids) == {"akash", "karan"}


def test_ingestion_skips_blank_rows_as_not_yet_annotated(tmp_path):
    resolver = _resolver(tmp_path)
    candidates = [_candidate()]
    build_annotation_tasks(candidates, CFG, resolver=resolver)
    ingested = ingest_annotations(CFG, candidates=candidates, resolver=resolver)
    assert ingested[0].applies_to == []
    assert ingested[0].label_status == LabelStatus.CANDIDATE.value


def test_ingestion_fails_loudly_on_unknown_label_id(tmp_path):
    resolver = _resolver(tmp_path)
    candidates = [_candidate()]
    paths = build_annotation_tasks(candidates, CFG, resolver=resolver)
    with open(paths["akash"], newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["label_id"] = "t1_does_not_exist"
    rows[0]["applies_to"] = "Commercial Banks"
    rows[0]["differential_flag"] = "shared"
    with open(paths["akash"], "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(AnnotationError, match="out of sync"):
        ingest_annotations(CFG, candidates=candidates, resolver=resolver)


def test_ingestion_fails_loudly_on_missing_columns(tmp_path):
    resolver = _resolver(tmp_path)
    candidates = [_candidate()]
    paths = build_annotation_tasks(candidates, CFG, resolver=resolver)
    with open(paths["akash"], "w", newline="", encoding="utf-8") as handle:
        handle.write("label_id,applies_to\nt1_0001,Commercial Banks\n")

    with pytest.raises(AnnotationError, match="malformed"):
        ingest_annotations(CFG, candidates=candidates, resolver=resolver)


def test_ingestion_rejects_flag_without_applies_to(tmp_path):
    resolver = _resolver(tmp_path)
    candidates = [_candidate()]
    paths = build_annotation_tasks(candidates, CFG, resolver=resolver)
    _fill_task_file(paths["akash"], applies_to="", flag="shared")

    with pytest.raises(AnnotationError, match="without applies_to"):
        ingest_annotations(CFG, candidates=candidates, resolver=resolver)


def test_ingestion_rejects_invalid_flag_value(tmp_path):
    resolver = _resolver(tmp_path)
    candidates = [_candidate()]
    paths = build_annotation_tasks(candidates, CFG, resolver=resolver)
    _fill_task_file(paths["akash"], applies_to="Commercial Banks", flag="definitely")

    with pytest.raises(AnnotationError, match="not one of"):
        ingest_annotations(CFG, candidates=candidates, resolver=resolver)
