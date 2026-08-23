"""Integration test (Phase 1, Section U): full normalization + matrix pipeline
against a real slice of Akash's committed corpus — not a synthetic fixture.

Confirms:
- every emitted MatrixCell references a term that exists in the discovered
  vocabulary
- no cell is silently dropped for an unpopulated pair (full grid present)
- no DocumentRecord/ParagraphRecord's *_raw field changed value

Reads directly from the repository's own committed
`data/metadata/document_manifest.jsonl` — this is real, currently-committed
data, not a fixture, satisfying Section U's "not a synthetic fixture"
requirement without needing network access or Kaggle.
"""

from __future__ import annotations

import copy

import pytest

from src.common.io_helpers import read_jsonl
from src.common.paths import PathResolver
from src.matrix.matrix_builder import build_matrix, matrix_metrics
from src.metadata.vocabulary_discovery import (
    discover_entity_class_vocabulary,
    discover_subject_family_vocabulary,
    normalise_documents,
)
from src.schemas.provenance import DocumentRecord

MANIFEST_PATH = "data/metadata/document_manifest.jsonl"
SLICE_SIZE = 40  # real committed records, not a fixture; kept small for a fast test


def _load_real_slice() -> list[DocumentRecord]:
    try:
        rows = read_jsonl(MANIFEST_PATH)
    except Exception:  # noqa: BLE001
        pytest.skip(f"{MANIFEST_PATH} not present in this checkout")
    if not rows:
        pytest.skip(f"{MANIFEST_PATH} is empty")
    return [DocumentRecord.from_dict(r) for r in rows[:SLICE_SIZE]]


@pytest.fixture(scope="module")
def real_slice() -> list[DocumentRecord]:
    return _load_real_slice()


def test_real_slice_has_at_least_one_document(real_slice):
    assert len(real_slice) > 0


def test_full_pipeline_every_cell_references_a_real_vocabulary_term(real_slice):
    entity_vocab, _ = discover_entity_class_vocabulary(real_slice, {})
    subject_vocab, _ = discover_subject_family_vocabulary(real_slice, {})
    normalised = normalise_documents(real_slice, entity_vocab, subject_vocab)

    cells = build_matrix(normalised, entity_vocab, subject_vocab, {})
    assert cells

    for cell in cells:
        entity_term = entity_vocab.get(cell.entity_class_term_id)
        subject_term = subject_vocab.get(cell.subject_family_term_id)
        assert entity_term is not None, f"cell references unknown entity term {cell.entity_class_term_id}"
        assert subject_term is not None, f"cell references unknown subject term {cell.subject_family_term_id}"
        assert entity_term.canonical_name == cell.entity_class
        assert subject_term.canonical_name == cell.subject_family


def test_full_pipeline_full_grid_present_no_silent_drops(real_slice):
    entity_vocab, _ = discover_entity_class_vocabulary(real_slice, {})
    subject_vocab, _ = discover_subject_family_vocabulary(real_slice, {})
    normalised = normalise_documents(real_slice, entity_vocab, subject_vocab)
    cells = build_matrix(normalised, entity_vocab, subject_vocab, {})

    expected_pairs = {
        (e.canonical_name, s.canonical_name) for e in entity_vocab for s in subject_vocab
    }
    actual_pairs = {(c.entity_class, c.subject_family) for c in cells}
    assert actual_pairs == expected_pairs
    assert len(cells) == len(entity_vocab) * len(subject_vocab)

    # Unpopulated pairs must still be present as real cells, not omitted.
    unpopulated = [c for c in cells if not c.populated]
    for cell in unpopulated:
        assert cell.source_directions == []
        assert cell.n_documents == 0


def test_full_pipeline_raw_fields_never_change(real_slice):
    originals = copy.deepcopy(real_slice)
    entity_vocab, _ = discover_entity_class_vocabulary(real_slice, {})
    subject_vocab, _ = discover_subject_family_vocabulary(real_slice, {})
    normalised = normalise_documents(real_slice, entity_vocab, subject_vocab)

    by_id = {r.document_id: r for r in normalised}
    for original in originals:
        result = by_id[original.document_id]
        assert result.entity_class_raw == original.entity_class_raw
        assert result.subject_family_raw == original.subject_family_raw
        # original objects passed in are also untouched (normalise_documents
        # must return new records, never mutate its input)
        for record in real_slice:
            if record.document_id == original.document_id:
                assert record.entity_class_raw == original.entity_class_raw
                assert record.subject_family_raw == original.subject_family_raw


def test_full_pipeline_every_cell_passes_schema_validation(real_slice):
    entity_vocab, _ = discover_entity_class_vocabulary(real_slice, {})
    subject_vocab, _ = discover_subject_family_vocabulary(real_slice, {})
    normalised = normalise_documents(real_slice, entity_vocab, subject_vocab)
    cells = build_matrix(normalised, entity_vocab, subject_vocab, {})
    for cell in cells:
        errors = cell.validate()
        assert errors == [], f"{cell.entity_class}/{cell.subject_family}: {errors}"


def test_full_pipeline_metrics_are_internally_consistent(real_slice):
    entity_vocab, _ = discover_entity_class_vocabulary(real_slice, {})
    subject_vocab, _ = discover_subject_family_vocabulary(real_slice, {})
    normalised = normalise_documents(real_slice, entity_vocab, subject_vocab)
    cells = build_matrix(normalised, entity_vocab, subject_vocab, {})
    metrics = matrix_metrics(cells)

    assert metrics["total_cells"] == len(cells)
    assert metrics["populated_cells"] + metrics["missing_cells"] == metrics["total_cells"]
    assert metrics["populated_cells"] == sum(1 for c in cells if c.populated)
    assert metrics["ambiguous_cells"] == sum(1 for c in cells if c.ambiguous)


def test_full_pipeline_entity_class_coverage_is_non_zero(real_slice):
    """Engineering sanity check only (Section V.4) — not a research claim."""
    entity_vocab, _ = discover_entity_class_vocabulary(real_slice, {})
    subject_vocab, _ = discover_subject_family_vocabulary(real_slice, {})
    normalised = normalise_documents(real_slice, entity_vocab, subject_vocab)
    coverage = sum(1 for r in normalised if r.entity_class) / len(normalised)
    assert coverage > 0.0
