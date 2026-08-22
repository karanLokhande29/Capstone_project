"""Vocabularies: extensible, discovered, and empty until the corpus fills them."""

from __future__ import annotations

import pytest

from src.common.errors import SchemaValidationError
from src.schemas.vocabulary import (
    ENTITY_CLASS,
    SUBJECT_FAMILY,
    Vocabulary,
    VocabularyTerm,
    empty_entity_class_vocabulary,
    empty_subject_family_vocabulary,
    normalise_term,
)


def term(term_id: str, name: str, kind: str = ENTITY_CLASS, **kwargs) -> VocabularyTerm:
    return VocabularyTerm(term_id=term_id, canonical_name=name, kind=kind, **kwargs)


# -- the no-hard-coding rule --------------------------------------------------


def test_entity_vocabulary_starts_empty():
    """The ~11-class planning estimate must not be encoded anywhere."""
    vocab = empty_entity_class_vocabulary()
    assert len(vocab) == 0
    assert vocab.canonical_names() == ()


def test_subject_vocabulary_starts_empty():
    """The ~26-family planning estimate must not be encoded anywhere."""
    assert len(empty_subject_family_vocabulary()) == 0


def test_vocabularies_know_their_axis():
    assert empty_entity_class_vocabulary().kind == ENTITY_CLASS
    assert empty_subject_family_vocabulary().kind == SUBJECT_FAMILY


def test_invalid_kind_rejected():
    with pytest.raises(SchemaValidationError):
        Vocabulary("something_else")
    with pytest.raises(SchemaValidationError):
        VocabularyTerm(term_id="t", canonical_name="T", kind="not_an_axis")


# -- normalisation ------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Commercial Banks", "commercial banks"),
        ("  COMMERCIAL   BANKS  ", "commercial banks"),
        ("Non-Banking Financial Companies", "nonbanking financial companies"),
        ("Urban Co-operative Banks", "urban cooperative banks"),
        ("", ""),
    ],
)
def test_normalise_term(raw, expected):
    assert normalise_term(raw) == expected


def test_normalisation_is_lookup_only_not_storage():
    """The canonical name keeps its published form so annotators see it verbatim."""
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("nbfc", "Non-Banking Financial Companies"))
    assert vocab.resolve("non-banking financial companies").canonical_name == (
        "Non-Banking Financial Companies"
    )


# -- population and lookup ----------------------------------------------------


def test_add_and_resolve():
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("comm_banks", "Commercial Banks"))
    assert len(vocab) == 1
    assert vocab.resolve("Commercial Banks").term_id == "comm_banks"
    assert "commercial banks" in vocab


def test_aliases_resolve_to_the_canonical_term():
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("ucb", "Urban Co-operative Banks", aliases=["UCBs", "Urban Cooperative Banks"]))
    assert vocab.resolve("UCBs").term_id == "ucb"
    assert vocab.resolve("urban cooperative banks").term_id == "ucb"


def test_unknown_surface_form_returns_none():
    """An unresolved form is a finding about corpus coverage, not an exception."""
    assert empty_entity_class_vocabulary().resolve("Something Unseen") is None


def test_duplicate_term_id_rejected():
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("t1", "A"))
    with pytest.raises(SchemaValidationError, match="Duplicate term_id"):
        vocab.add(term("t1", "B"))


def test_conflicting_surface_form_rejected():
    """Two canonical terms competing for one surface form must be resolved explicitly."""
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("t1", "Commercial Banks"))
    with pytest.raises(SchemaValidationError, match="already resolves"):
        vocab.add(term("t2", "Other", aliases=["commercial banks"]))


def test_replace_updates_lookups():
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("t1", "Old Name", aliases=["stale"]))
    vocab.add(term("t1", "New Name", aliases=["fresh"]), replace=True)
    assert vocab.resolve("New Name").term_id == "t1"
    assert vocab.resolve("fresh").term_id == "t1"
    assert vocab.resolve("stale") is None


def test_wrong_kind_rejected():
    vocab = empty_entity_class_vocabulary()
    with pytest.raises(SchemaValidationError, match="Cannot add"):
        vocab.add(term("t1", "KYC", kind=SUBJECT_FAMILY))


def test_get_by_term_id():
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("t1", "A"))
    assert vocab.get("t1").canonical_name == "A"
    assert vocab.get("missing") is None


def test_iteration_is_ordered_by_term_id():
    vocab = empty_entity_class_vocabulary()
    for tid in ("c", "a", "b"):
        vocab.add(term(tid, tid.upper()))
    assert [t.term_id for t in vocab] == ["a", "b", "c"]


def test_contains_rejects_non_strings():
    assert (123 in empty_entity_class_vocabulary()) is False


# -- serialisation ------------------------------------------------------------


def test_round_trip_preserves_terms_and_aliases():
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("t1", "Commercial Banks", aliases=["CBs"], source="https://example.org"))
    vocab.add(term("t2", "Payments Banks", occurrence_count=12))

    restored = Vocabulary.from_dict(vocab.to_dict())
    assert len(restored) == 2
    assert restored.resolve("CBs").term_id == "t1"
    assert restored.get("t2").occurrence_count == 12


def test_serialised_form_reports_a_discovered_count():
    """Counts are reported as measured, never asserted from an estimate."""
    vocab = empty_entity_class_vocabulary()
    vocab.add(term("t1", "A"))
    assert vocab.to_dict()["term_count"] == 1


def test_from_dict_requires_kind():
    with pytest.raises(SchemaValidationError, match="kind"):
        Vocabulary.from_dict({"terms": []})


def test_from_dict_rejects_non_mapping():
    with pytest.raises(SchemaValidationError):
        Vocabulary.from_dict(["not", "a", "mapping"])


def test_empty_vocabulary_round_trips():
    restored = Vocabulary.from_dict(empty_entity_class_vocabulary().to_dict())
    assert len(restored) == 0
    assert restored.kind == ENTITY_CLASS


def test_repr_reports_size():
    assert "terms=0" in repr(empty_entity_class_vocabulary())
