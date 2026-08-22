"""Schema contracts: construction, validation, and the integrity rules.

The tests that matter most here are the ones guarding the two rules that make
the benchmark's research claims meaningful — ``applies_to`` is not derived from
``entity_class``, and ``differential_flag`` is not defaulted to ``absent``.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.common.errors import SchemaValidationError
from src.schemas import ALL_SCHEMAS
from src.schemas.base import KNOWN_OWNERS
from src.schemas.benchmark import DifferentialFlag, LabelStatus, ObligationSpan, T1Label
from src.schemas.matrix import MatrixCell
from src.schemas.provenance import DocumentRecord, ParagraphRecord, stable_paragraph_id


# -- contract hygiene, applied to every schema --------------------------------


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.__name__)
def test_every_field_has_a_spec(schema):
    """A field without a spec has no documented owner, which is how drift starts."""
    declared = set(schema.field_names())
    specified = set(schema.spec_map())
    assert declared == specified, f"spec/field mismatch: {declared ^ specified}"


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.__name__)
def test_every_spec_names_a_known_owner(schema):
    for spec in schema.FIELD_SPECS:
        assert spec.populated_by in KNOWN_OWNERS, f"{schema.__name__}.{spec.name}"


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.__name__)
def test_every_field_is_documented(schema):
    for spec in schema.FIELD_SPECS:
        assert spec.description.strip(), f"{schema.__name__}.{spec.name} has no description"


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.__name__)
def test_spec_table_renders(schema):
    table = schema.spec_table()
    assert table.startswith("| Field |")
    for spec in schema.FIELD_SPECS:
        assert f"`{spec.name}`" in table


@pytest.mark.parametrize("schema", ALL_SCHEMAS, ids=lambda s: s.__name__)
def test_unknown_field_is_rejected(schema):
    """Catching an undeclared field at the boundary beats finding it at integration."""
    payload = {name: "x" for name in schema.required_fields()}
    payload["a_field_nobody_declared"] = 1
    with pytest.raises(SchemaValidationError, match="unknown field"):
        schema.from_dict(payload)


# -- DocumentRecord -----------------------------------------------------------


def test_document_minimal_construction():
    record = DocumentRecord(document_id="md_1")
    assert record.is_valid()
    assert record.source_url is None


def test_document_round_trip():
    record = DocumentRecord(
        document_id="md_1",
        source_url="https://www.rbi.org.in/x.pdf",
        title="Commercial Banks – Know Your Customer Directions",
        entity_class_raw="Commercial Banks",
        format="PDF",
    )
    assert DocumentRecord.from_dict(record.to_dict()) == record


def test_document_id_may_not_be_null():
    assert "document_id: must not be null" in DocumentRecord(document_id=None).validate()


def test_document_missing_required_field_raises():
    with pytest.raises(SchemaValidationError, match="missing required field: document_id"):
        DocumentRecord.from_dict({"title": "no id"})


def test_document_wrong_type_is_reported():
    errors = DocumentRecord(document_id="md_1", title=42).validate()
    assert any("title" in e and "expected" in e for e in errors)


def test_raw_and_normalised_are_separate_fields():
    """Overwriting the raw value in place would make normalisation unauditable."""
    names = set(DocumentRecord.field_names())
    assert {"entity_class_raw", "entity_class"} <= names
    assert {"subject_family_raw", "subject_family"} <= names


# -- ParagraphRecord ----------------------------------------------------------


def test_paragraph_minimal_construction():
    record = ParagraphRecord(paragraph_id="md_1::p00000", document_id="md_1")
    assert record.is_valid()


def test_paragraph_carries_section_and_clause_provenance():
    """A bare paragraph index is not a legal citation; clause_path is."""
    names = set(ParagraphRecord.field_names())
    assert {"section_id", "section_title", "clause_id", "clause_path"} <= names


def test_paragraph_reserves_retrieval_metadata():
    names = set(ParagraphRecord.field_names())
    assert {
        "retrieval_chunk_id",
        "retrieval_chunk_index",
        "retrieval_embedding_model",
        "retrieval_index_id",
    } <= names


def test_cross_references_default_to_empty_not_null():
    """Empty means 'checked, none found'; null would mean 'never checked'."""
    record = ParagraphRecord(paragraph_id="md_1::p00000", document_id="md_1")
    assert record.cross_reference_ids == []
    assert "cross_reference_ids: must not be null" in ParagraphRecord(
        paragraph_id="p", document_id="d", cross_reference_ids=None
    ).validate()


def test_paragraph_round_trip():
    record = ParagraphRecord(
        paragraph_id=stable_paragraph_id("md_1", 7),
        document_id="md_1",
        position=7,
        text="Banks shall maintain records.",
        char_start=0,
        char_end=29,
        clause_path="4.2(a)",
        cross_reference_ids=["md_2::p00003"],
    )
    assert ParagraphRecord.from_dict(record.to_dict()) == record


# -- stable_paragraph_id ------------------------------------------------------


def test_paragraph_id_is_deterministic_and_padded():
    assert stable_paragraph_id("md_1", 3) == "md_1::p00003"
    assert stable_paragraph_id("md_1", 3) == stable_paragraph_id("md_1", 3)


def test_paragraph_ids_sort_in_document_order():
    """Zero-padding means lexical order matches reading order."""
    ids = [stable_paragraph_id("md_1", i) for i in (2, 10, 100)]
    assert ids == sorted(ids)


def test_paragraph_id_rejects_bad_input():
    with pytest.raises(ValueError):
        stable_paragraph_id("", 0)
    with pytest.raises(ValueError):
        stable_paragraph_id("md_1", -1)


# -- MatrixCell ---------------------------------------------------------------


def test_unpopulated_cell_is_valid():
    """An unpopulated cell is the interesting output, not an error."""
    cell = MatrixCell(entity_class="Commercial Banks", subject_family="KYC")
    assert cell.is_valid()
    assert cell.populated is False
    assert cell.source_directions == []


def test_populated_cell_requires_sources():
    cell = MatrixCell(entity_class="E", subject_family="S", populated=True)
    assert any("source_directions" in e for e in cell.validate())


def test_sources_require_populated_flag():
    cell = MatrixCell(entity_class="E", subject_family="S", source_directions=["md_1"])
    assert any("populated" in e for e in cell.validate())


def test_ambiguous_cell_requires_a_reason():
    """An ambiguity without a stated reason is not a finding."""
    cell = MatrixCell(entity_class="E", subject_family="S", ambiguous=True)
    assert any("ambiguity_reason" in e for e in cell.validate())


def test_populated_and_ambiguous_are_independent():
    cell = MatrixCell(
        entity_class="E",
        subject_family="S",
        populated=True,
        source_directions=["md_1", "md_2"],
        ambiguous=True,
        ambiguity_reason="multiple_candidate_directions",
        n_documents=2,
    )
    assert cell.is_valid()


def test_document_count_must_agree_with_source_list():
    cell = MatrixCell(
        entity_class="E",
        subject_family="S",
        populated=True,
        source_directions=["md_1"],
        n_documents=5,
    )
    assert any("n_documents" in e for e in cell.validate())


def test_cell_key():
    assert MatrixCell(entity_class="E", subject_family="S").cell_key == ("E", "S")


# -- ObligationSpan -----------------------------------------------------------


def test_span_construction_and_ref():
    span = ObligationSpan(paragraph_id="md_1::p00000", document_id="md_1", char_start=10, char_end=40)
    assert span.is_valid()
    assert span.span_ref == "md_1::p00000@10:40"


def test_span_end_must_follow_start():
    span = ObligationSpan(paragraph_id="p", document_id="d", char_start=40, char_end=10)
    assert any("char_end" in e for e in span.validate())


def test_span_offsets_must_be_non_negative():
    span = ObligationSpan(paragraph_id="p", document_id="d", char_start=-1, char_end=5)
    assert any("char_start" in e for e in span.validate())


# -- T1Label: the integrity rules --------------------------------------------


def test_new_label_is_a_candidate_with_nothing_asserted():
    label = T1Label(label_id="t1_0001")
    assert label.label_status == LabelStatus.CANDIDATE.value
    assert label.applies_to == []
    assert label.differential_flag == DifferentialFlag.UNLABELLED.value
    assert label.is_validated is False
    assert label.is_valid()


def test_differential_flag_defaults_to_unlabelled_not_absent():
    """Defaulting to 'absent' would assert a finding nobody examined."""
    assert T1Label(label_id="t1").differential_flag != DifferentialFlag.ABSENT.value
    assert T1Label(label_id="t1").differential_flag == "unlabelled"


def test_applies_to_is_independent_of_entity_class():
    """The applicability label must not be implied by the source document's class."""
    label = T1Label(label_id="t1", entity_class="Commercial Banks")
    assert label.applies_to == []
    spec = label.spec_map()["applies_to"]
    assert spec.populated_by == "phase1/meer-annotation"
    assert label.spec_map()["entity_class"].populated_by != spec.populated_by


def test_validated_requires_annotators():
    label = T1Label(
        label_id="t1",
        label_status=LabelStatus.VALIDATED.value,
        applies_to=["Commercial Banks"],
        differential_flag=DifferentialFlag.SHARED.value,
    )
    assert any("annotator_ids" in e for e in label.validate())


def test_validated_requires_applicability():
    label = T1Label(
        label_id="t1",
        label_status=LabelStatus.VALIDATED.value,
        annotator_ids=["a", "b"],
        differential_flag=DifferentialFlag.SHARED.value,
    )
    assert any("applies_to" in e for e in label.validate())


def test_validated_cannot_remain_unlabelled():
    label = T1Label(
        label_id="t1",
        label_status=LabelStatus.VALIDATED.value,
        annotator_ids=["a", "b"],
        applies_to=["Commercial Banks"],
    )
    assert any("unlabelled" in e for e in label.validate())


def test_fully_annotated_label_is_valid():
    label = T1Label(
        label_id="t1",
        obligation_span=ObligationSpan(
            paragraph_id="md_1::p00004", document_id="md_1", char_start=0, char_end=30
        ),
        entity_class="Commercial Banks",
        applies_to=["Commercial Banks", "Small Finance Banks"],
        applies_to_rationale="Paragraph 4.2 extends the requirement to SFBs.",
        differential_flag=DifferentialFlag.SHARED.value,
        label_status=LabelStatus.VALIDATED.value,
        annotator_ids=["akash", "meer"],
        annotation_count=2,
    )
    assert label.validate() == []
    assert label.is_validated


def test_annotation_count_must_agree_with_annotator_list():
    label = T1Label(label_id="t1", annotator_ids=["a"], annotation_count=3)
    assert any("annotation_count" in e for e in label.validate())


def test_invalid_flag_value_is_rejected():
    label = T1Label(label_id="t1", differential_flag="maybe")
    assert any("differential_flag" in e for e in label.validate())


def test_invalid_status_value_is_rejected():
    label = T1Label(label_id="t1", label_status="probably_fine")
    assert any("label_status" in e for e in label.validate())


def test_nested_span_errors_are_surfaced():
    label = T1Label(
        label_id="t1",
        obligation_span=ObligationSpan(paragraph_id="p", document_id="d", char_start=9, char_end=1),
    )
    assert any(e.startswith("obligation_span.") for e in label.validate())


def test_label_round_trip_rebuilds_nested_span():
    label = T1Label(
        label_id="t1",
        obligation_span=ObligationSpan(
            paragraph_id="md_1::p00000", document_id="md_1", char_start=0, char_end=10
        ),
        applies_to=["Commercial Banks"],
    )
    restored = T1Label.from_dict(label.to_dict())
    assert isinstance(restored.obligation_span, ObligationSpan)
    assert restored == label


def test_require_valid_raises_on_invalid():
    with pytest.raises(SchemaValidationError):
        T1Label(label_id="t1", differential_flag="nope").require_valid()


def test_require_valid_returns_self():
    label = T1Label(label_id="t1")
    assert label.require_valid() is label


# -- ownership introspection --------------------------------------------------


def test_owned_by_partitions_the_annotation_targets():
    owned = set(T1Label.owned_by("phase1/meer-annotation"))
    assert {"applies_to", "differential_flag", "label_status"} <= owned


def test_schemas_are_dataclasses():
    for schema in ALL_SCHEMAS:
        assert dataclasses.is_dataclass(schema)
