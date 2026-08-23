"""Tests for src.matrix.matrix_builder.

Fixtures only — small, hand-built vocabularies and records so every cell in
the resulting grid is checkable by hand.
"""

from __future__ import annotations

import pytest

from src.matrix import matrix_builder as mb
from src.schemas.provenance import DocumentRecord
from src.schemas.vocabulary import ENTITY_CLASS, SUBJECT_FAMILY, Vocabulary, VocabularyTerm

MINIMAL_CONFIG: dict = {}


def _vocab(kind, *names):
    vocab = Vocabulary(kind)
    for i, name in enumerate(names):
        vocab.add(VocabularyTerm(term_id=f"{kind}_{i}", canonical_name=name, kind=kind))
    return vocab


def _doc(document_id, entity_class, subject_family):
    return DocumentRecord(document_id=document_id, entity_class=entity_class, subject_family=subject_family)


# -- build_matrix: full grid coverage ----------------------------------------


def test_build_matrix_emits_a_cell_for_every_axis_pair():
    """2 entity classes x 3 subject families must produce exactly 6 cells,
    including pairs with zero source Directions — an unpopulated cell is a
    measurement, not a missing record."""
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks", "Small Finance Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC", "Fraud Risk Management", "Governance")
    records = [_doc("d1", "Commercial Banks", "KYC")]

    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    assert len(cells) == 6
    pairs = {(c.entity_class, c.subject_family) for c in cells}
    assert pairs == {
        ("Commercial Banks", "KYC"),
        ("Commercial Banks", "Fraud Risk Management"),
        ("Commercial Banks", "Governance"),
        ("Small Finance Banks", "KYC"),
        ("Small Finance Banks", "Fraud Risk Management"),
        ("Small Finance Banks", "Governance"),
    }


def test_build_matrix_unpopulated_cell_has_no_source_directions():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC", "Governance")
    records = [_doc("d1", "Commercial Banks", "KYC")]

    cells = {(c.entity_class, c.subject_family): c for c in mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)}
    governance_cell = cells[("Commercial Banks", "Governance")]
    assert governance_cell.populated is False
    assert governance_cell.source_directions == []
    assert governance_cell.n_documents == 0


def test_build_matrix_populated_cell_has_source_directions():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [_doc("d1", "Commercial Banks", "KYC")]

    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    assert cells[0].populated is True
    assert cells[0].source_directions == ["d1"]
    assert cells[0].n_documents == 1


def test_build_matrix_ignores_records_without_both_normalised_fields():
    """A record missing entity_class or subject_family contributes to no cell —
    it isn't silently forced into one."""
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [
        _doc("d1", "Commercial Banks", None),
        _doc("d2", None, "KYC"),
        _doc("d3", "Commercial Banks", "KYC"),
    ]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    assert cells[0].source_directions == ["d3"]


# -- populated / ambiguous independence --------------------------------------


def test_populated_and_ambiguous_are_independent_single_document_not_ambiguous():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [_doc("d1", "Commercial Banks", "KYC")]
    cell = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)[0]
    assert cell.populated is True
    assert cell.ambiguous is False
    assert cell.ambiguity_reason is None


def test_multiple_documents_in_one_cell_marks_it_ambiguous():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [_doc("d1", "Commercial Banks", "KYC"), _doc("d2", "Commercial Banks", "KYC")]
    cell = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)[0]
    assert cell.populated is True
    assert cell.ambiguous is True
    assert cell.ambiguity_reason == "multiple_candidate_directions"
    assert cell.n_documents == 2


def test_ambiguity_reason_is_only_ever_set_when_ambiguous():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC", "Governance")
    records = [_doc("d1", "Commercial Banks", "KYC"), _doc("d2", "Commercial Banks", "KYC")]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    for cell in cells:
        if cell.ambiguous:
            assert cell.ambiguity_reason is not None
        else:
            assert cell.ambiguity_reason is None


def test_every_cell_passes_schema_validation():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks", "Small Finance Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC", "Governance")
    records = [_doc("d1", "Commercial Banks", "KYC"), _doc("d2", "Commercial Banks", "KYC")]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    for cell in cells:
        assert cell.validate() == []


# -- term-id cross-references ------------------------------------------------


def test_cells_reference_real_term_ids():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [_doc("d1", "Commercial Banks", "KYC")]
    cell = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)[0]
    assert entity_vocab.get(cell.entity_class_term_id) is not None
    assert subject_vocab.get(cell.subject_family_term_id) is not None
    assert entity_vocab.get(cell.entity_class_term_id).canonical_name == "Commercial Banks"


# -- matrix_metrics -----------------------------------------------------------


def test_matrix_metrics_counts_are_consistent():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks", "Small Finance Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC", "Governance")
    records = [_doc("d1", "Commercial Banks", "KYC"), _doc("d2", "Commercial Banks", "KYC")]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    metrics = mb.matrix_metrics(cells)

    assert metrics["total_cells"] == 4
    assert metrics["populated_cells"] == 1
    assert metrics["missing_cells"] == 3
    assert metrics["ambiguous_cells"] == 1
    assert metrics["duplicate_mapping_cells"] == 1
    assert metrics["matrix_coverage"] == pytest.approx(0.25)


def test_matrix_metrics_on_empty_grid_reports_not_yet_measured():
    metrics = mb.matrix_metrics([])
    assert metrics["total_cells"] == 0
    assert metrics["matrix_coverage"] == "NOT YET MEASURED"


# -- route_query ---------------------------------------------------------


def test_route_query_returns_source_directions():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [_doc("d1", "Commercial Banks", "KYC")]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    assert mb.route_query("Commercial Banks", "KYC", cells) == ["d1"]


def test_route_query_empty_list_for_unpopulated_known_cell():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC", "Governance")
    records = [_doc("d1", "Commercial Banks", "KYC")]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    assert mb.route_query("Commercial Banks", "Governance", cells) == []


def test_route_query_raises_for_pair_not_in_matrix():
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [_doc("d1", "Commercial Banks", "KYC")]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    with pytest.raises(KeyError):
        mb.route_query("Nonexistent Class", "KYC", cells)


# -- persist_matrix -----------------------------------------------------------


def test_persist_matrix_writes_jsonl_and_summary(tmp_path):
    from src.common.paths import PathResolver

    cfg = {
        "environment": {
            "mode": "local",
            "local": {"working_root": ".", "input_roots": []},
            "kaggle": {"working_root": "/kaggle/working", "input_root": "/kaggle/input", "input_datasets": []},
        },
        "paths": {k: k for k in ("raw", "extracted", "processed", "metadata", "matrix", "benchmark", "evaluation", "cache", "reports", "logs")},
    }
    resolver = PathResolver.from_config(cfg, repo_root=tmp_path)
    entity_vocab = _vocab(ENTITY_CLASS, "Commercial Banks")
    subject_vocab = _vocab(SUBJECT_FAMILY, "KYC")
    records = [_doc("d1", "Commercial Banks", "KYC")]
    cells = mb.build_matrix(records, entity_vocab, subject_vocab, cfg)

    paths = mb.persist_matrix(cells, cfg, resolver=resolver)

    from src.common.io_helpers import read_json, read_jsonl

    rows = read_jsonl(paths["matrix_path"])
    assert len(rows) == 1
    summary = read_json(paths["summary_path"])
    assert summary["total_cells"] == 1
