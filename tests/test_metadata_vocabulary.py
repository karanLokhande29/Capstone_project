"""Tests for src.metadata.vocabulary_discovery.

Fixtures only — no real network, no dependence on the committed corpus (see
tests/test_metadata_matrix_integration.py for that). Titles below are written
for these tests, mirroring real structural patterns confirmed against the
live corpus while building this module (see its docstring), not copied from
any actual RBI Direction.
"""

from __future__ import annotations

import pytest

from src.schemas.provenance import DocumentRecord, ParagraphRecord, stable_paragraph_id
from src.schemas.vocabulary import ENTITY_CLASS, SUBJECT_FAMILY, empty_entity_class_vocabulary, empty_subject_family_vocabulary
from src.metadata import vocabulary_discovery as vd

MINIMAL_CONFIG: dict = {}


def _doc(document_id, entity_class_raw, title, **kwargs):
    return DocumentRecord(document_id=document_id, entity_class_raw=entity_class_raw, title=title, **kwargs)


# -- extract_subject_residual --------------------------------------------


def test_extract_subject_residual_structural_bracket_form():
    title = "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025"
    assert vd.extract_subject_residual(title, "Commercial Banks") == "Know Your Customer"


def test_extract_subject_residual_strips_updated_as_on_stamp():
    title = "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025 (Updated as on July 1, 2026)"
    assert vd.extract_subject_residual(title, "Commercial Banks") == "Know Your Customer"


def test_extract_subject_residual_does_not_leave_dangling_bracket():
    """Regression: a trailing qualifier after the closing paren used to leave
    an orphaned ')' stuck mid-string (fixed by matching the whole bracket
    structure, including its own close, in one regex)."""
    title = "Reserve Bank of India (Commercial Banks – Miscellaneous) Supervisory Directions, 2026"
    residual = vd.extract_subject_residual(title, "Commercial Banks")
    assert residual == "Miscellaneous"
    assert ")" not in residual


def test_extract_subject_residual_word_boundary_prevents_substring_slicing():
    """Regression: "Financial Market" must not match as a prefix of
    "Financial Markets" inside a title (found on the real corpus, md_13343)."""
    title = "Master Direction - Reserve Bank of India (Unique Identifiers in Financial Markets) Directions, 2026"
    residual = vd.extract_subject_residual(title, "Financial Market")
    assert residual is None  # "Financial Market" has no word-boundary match here


def test_extract_subject_residual_fallback_word_match_without_brackets():
    title = "Reserve Bank of India Commercial Banks Branch Licensing Directions, 2025"
    assert vd.extract_subject_residual(title, "Commercial Banks") == "Branch Licensing"


def test_extract_subject_residual_returns_none_when_entity_class_absent():
    """The real "Internal Ombudsman" pattern: the title names a different
    entity class than entity_class_raw. Must not force-match."""
    title = "Reserve Bank of India (Commercial Banks - Internal Ombudsman) Directions, 2026"
    assert vd.extract_subject_residual(title, "Consumer Education and Protection") is None


def test_extract_subject_residual_returns_none_for_missing_inputs():
    assert vd.extract_subject_residual(None, "Commercial Banks") is None
    assert vd.extract_subject_residual("Some title", None) is None
    assert vd.extract_subject_residual("", "") is None


def test_extract_subject_residual_strips_master_direction_prefix():
    title = "Master Direction – Payments Banks – Settlement Directions, 2025"
    assert vd.extract_subject_residual(title, "Payments Banks") == "Settlement"


# -- discover_entity_class_vocabulary --------------------------------------


def test_discover_entity_class_vocabulary_starts_from_empty_class():
    """Phase 0's own enforcement: the constructor returns empty. Asserted at
    the class level (not "stays empty after this branch's tests run") since
    this branch's whole job is to populate instances, not leave the type
    empty forever."""
    assert len(empty_entity_class_vocabulary()) == 0


def test_discover_entity_class_vocabulary_one_term_per_distinct_raw_value():
    records = [
        _doc("d1", "Commercial Banks", "t1"),
        _doc("d2", "Commercial Banks", "t2"),
        _doc("d3", "Small Finance Banks", "t3"),
    ]
    vocab, unresolved = vd.discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    assert len(vocab) == 2
    assert unresolved == []
    term = vocab.resolve("Commercial Banks")
    assert term.occurrence_count == 2
    assert term.first_seen_document_id == "d1"


def test_discover_entity_class_vocabulary_records_null_raw_as_unresolved():
    records = [_doc("d1", None, "t1"), _doc("d2", "Commercial Banks", "t2")]
    vocab, unresolved = vd.discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    assert len(vocab) == 1
    assert unresolved == ["d1"]


def test_discover_entity_class_vocabulary_terms_have_source_and_kind():
    records = [_doc("d1", "Commercial Banks", "t1")]
    vocab, _ = vd.discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    term = vocab.resolve("Commercial Banks")
    assert term.kind == ENTITY_CLASS
    assert term.source
    assert term.is_valid()


# -- discover_subject_family_vocabulary ------------------------------------


def test_discover_subject_family_vocabulary_groups_by_residual():
    records = [
        _doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025"),
        _doc("d2", "Small Finance Banks", "Reserve Bank of India (Small Finance Banks – Know Your Customer) Directions, 2025"),
    ]
    vocab, unresolved = vd.discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    assert len(vocab) == 1
    assert unresolved == []
    term = vocab.resolve("Know Your Customer")
    assert term.occurrence_count == 2


def test_discover_subject_family_vocabulary_records_unresolved_with_reason():
    records = [
        _doc(
            "d1", "Consumer Education and Protection",
            "Reserve Bank of India (Commercial Banks - Internal Ombudsman) Directions, 2026",
        )
    ]
    vocab, unresolved = vd.discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    assert len(vocab) == 0
    assert len(unresolved) == 1
    assert unresolved[0]["document_id"] == "d1"
    assert "reason" in unresolved[0] and unresolved[0]["reason"]


def test_discover_subject_family_vocabulary_starts_from_empty_class():
    assert len(empty_subject_family_vocabulary()) == 0


def test_discover_subject_family_vocabulary_never_seeded_with_dossier_estimate():
    """No hard-coded ~26 subject families anywhere — an empty corpus discovers
    nothing, not a pre-populated placeholder set."""
    vocab, _ = vd.discover_subject_family_vocabulary([], MINIMAL_CONFIG)
    assert len(vocab) == 0


# -- normalise_documents ----------------------------------------------------


def test_normalise_documents_writes_entity_class_and_subject_family():
    records = [
        _doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025")
    ]
    entity_vocab, _ = vd.discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    subject_vocab, _ = vd.discover_subject_family_vocabulary(records, MINIMAL_CONFIG)

    normalised = vd.normalise_documents(records, entity_vocab, subject_vocab)
    assert normalised[0].entity_class == "Commercial Banks"
    assert normalised[0].subject_family == "Know Your Customer"


def test_normalise_documents_never_touches_raw_fields():
    original = _doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – KYC) Directions, 2025", subject_family_raw=None)
    entity_vocab, _ = vd.discover_entity_class_vocabulary([original], MINIMAL_CONFIG)
    subject_vocab, _ = vd.discover_subject_family_vocabulary([original], MINIMAL_CONFIG)

    normalised = vd.normalise_documents([original], entity_vocab, subject_vocab)[0]
    assert normalised.entity_class_raw == original.entity_class_raw
    assert normalised.subject_family_raw == original.subject_family_raw
    assert original.entity_class is None  # original object itself is untouched


def test_normalise_documents_leaves_unresolved_fields_null():
    records = [_doc("d1", "Consumer Education and Protection", "Reserve Bank of India (Commercial Banks - Internal Ombudsman) Directions, 2026")]
    entity_vocab, _ = vd.discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    subject_vocab, _ = vd.discover_subject_family_vocabulary(records, MINIMAL_CONFIG)

    normalised = vd.normalise_documents(records, entity_vocab, subject_vocab)[0]
    assert normalised.entity_class == "Consumer Education and Protection"
    assert normalised.subject_family is None


def test_normalise_documents_returns_new_objects_not_mutations():
    original = _doc("d1", "Commercial Banks", "t1")
    entity_vocab, _ = vd.discover_entity_class_vocabulary([original], MINIMAL_CONFIG)
    subject_vocab, _ = vd.discover_subject_family_vocabulary([original], MINIMAL_CONFIG)
    normalised = vd.normalise_documents([original], entity_vocab, subject_vocab)[0]
    assert normalised is not original


# -- normalise_paragraphs ---------------------------------------------------


def test_normalise_paragraphs_inherits_from_parent_document():
    doc = _doc("d1", "Commercial Banks", "t1")
    normalised_doc = doc.__class__(**{**doc.to_dict(), "entity_class": "Commercial Banks", "subject_family": "KYC"})
    paragraph = ParagraphRecord(paragraph_id=stable_paragraph_id("d1", 0), document_id="d1", position=0, text="body")

    result = vd.normalise_paragraphs([paragraph], {"d1": normalised_doc})[0]
    assert result.entity_class == "Commercial Banks"
    assert result.subject_family == "KYC"
    assert result.text == "body"


def test_normalise_paragraphs_null_when_parent_missing():
    paragraph = ParagraphRecord(paragraph_id=stable_paragraph_id("d1", 0), document_id="d1", position=0, text="body")
    result = vd.normalise_paragraphs([paragraph], {})[0]
    assert result.entity_class is None
    assert result.subject_family is None


def test_normalise_paragraphs_does_not_mutate_input():
    doc = _doc("d1", "Commercial Banks", "t1")
    normalised_doc = doc.__class__(**{**doc.to_dict(), "entity_class": "Commercial Banks"})
    paragraph = ParagraphRecord(paragraph_id=stable_paragraph_id("d1", 0), document_id="d1", position=0, text="body")
    vd.normalise_paragraphs([paragraph], {"d1": normalised_doc})
    assert paragraph.entity_class is None


# -- persist_vocabularies ---------------------------------------------------


def test_persist_vocabularies_writes_both_files(tmp_path):
    from src.common.paths import PathResolver

    cfg = {
        "environment": {
            "mode": "local",
            "local": {"working_root": ".", "input_roots": []},
            "kaggle": {"working_root": "/kaggle/working", "input_root": "/kaggle/input", "input_datasets": []},
        },
        "paths": {k: k for k in ("raw", "extracted", "processed", "metadata", "matrix", "benchmark", "evaluation", "cache", "reports", "logs")},
        "vocabulary": {"entity_class_file": "data/metadata/entity_classes.json", "subject_family_file": "data/metadata/subject_families.json"},
    }
    resolver = PathResolver.from_config(cfg, repo_root=tmp_path)
    entity_vocab = empty_entity_class_vocabulary()
    subject_vocab = empty_subject_family_vocabulary()

    paths = vd.persist_vocabularies(entity_vocab, subject_vocab, cfg, resolver=resolver)
    # fixture maps paths.metadata -> "metadata" (not "data/metadata"); persist_vocabularies
    # strips a configured "data/metadata/" prefix before resolving through that key.
    assert (tmp_path / "metadata" / "entity_classes.json").exists()
    assert (tmp_path / "metadata" / "subject_families.json").exists()
    assert paths["entity_class_file"] and paths["subject_family_file"]
