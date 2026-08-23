"""Provenance-marking tests (P1-002-CORRECTIVE).

The audit finding these guard: `subject_family` values in this corpus are
*inferred from titles*, not harvested from a raw field, and a downstream
consumer must be able to discover that **from the data alone** — not by
reading a module docstring. These tests assert the marker is present, is
correct per axis, and that the assumptions justifying "no schema change
needed" (Task 3) actually hold.
"""

from __future__ import annotations

import pytest

from src.common.io_helpers import read_json, read_jsonl
from src.matrix.matrix_builder import build_matrix
from src.metadata.vocabulary_discovery import (
    ENTITY_SOURCE,
    PROVENANCE_DERIVED,
    PROVENANCE_MIXED,
    PROVENANCE_RAW,
    SUBJECT_SOURCE,
    discover_entity_class_vocabulary,
    discover_subject_family_vocabulary,
    normalise_documents,
    provenance_counts,
    provenance_lookup,
    segmented_unresolved_rates,
    term_provenance,
)
from src.schemas.provenance import DocumentRecord
from src.schemas.vocabulary import ENTITY_CLASS, SUBJECT_FAMILY, VocabularyTerm

MINIMAL_CONFIG: dict = {}


def _doc(document_id, entity_class_raw, title, **kwargs):
    return DocumentRecord(document_id=document_id, entity_class_raw=entity_class_raw, title=title, **kwargs)


# -- term_provenance ---------------------------------------------------------


def test_term_provenance_reads_the_raw_prefix():
    term = VocabularyTerm(term_id="t", canonical_name="X", kind=ENTITY_CLASS, source=ENTITY_SOURCE)
    assert term_provenance(term) == PROVENANCE_RAW


def test_term_provenance_reads_the_derived_prefix():
    term = VocabularyTerm(term_id="t", canonical_name="X", kind=SUBJECT_FAMILY, source=SUBJECT_SOURCE)
    assert term_provenance(term) == PROVENANCE_DERIVED


@pytest.mark.parametrize("source", [None, "", "some free-text source with no prefix"])
def test_term_provenance_reports_mixed_rather_than_guessing(source):
    """An unrecognised source is labelled 'mixed', never silently assigned to
    raw or derived — same 'record, don't force-match' rule this module applies
    to unresolved surface forms."""
    term = VocabularyTerm(term_id="t", canonical_name="X", kind=SUBJECT_FAMILY, source=source)
    assert term_provenance(term) == PROVENANCE_MIXED


def test_source_markers_are_greppable_prefixes():
    """The report documents `grep '"source": "derived:'` as a supported query —
    that only works if the marker is a literal prefix."""
    assert ENTITY_SOURCE.startswith(f"{PROVENANCE_RAW}:")
    assert SUBJECT_SOURCE.startswith(f"{PROVENANCE_DERIVED}:")


# -- axis-level provenance on fixtures ---------------------------------------


def test_every_entity_class_term_is_marked_raw():
    records = [_doc("d1", "Commercial Banks", "t1"), _doc("d2", "Small Finance Banks", "t2")]
    vocab, _ = discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    assert len(vocab) == 2
    for term in vocab:
        assert term_provenance(term) == PROVENANCE_RAW, f"{term.canonical_name} mis-tagged"


def test_every_subject_family_term_is_marked_derived():
    records = [
        _doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025"),
        _doc("d2", "Small Finance Banks", "Reserve Bank of India (Small Finance Banks – Governance) Directions, 2025"),
    ]
    vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    assert len(vocab) == 2
    for term in vocab:
        assert term_provenance(term) == PROVENANCE_DERIVED, f"{term.canonical_name} mis-tagged"


def test_no_entity_class_term_is_mis_tagged_as_derived():
    records = [_doc("d1", "Commercial Banks", "t1")]
    vocab, _ = discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    assert provenance_counts(vocab)[PROVENANCE_DERIVED] == 0


def test_no_subject_family_term_is_mis_tagged_as_raw():
    records = [_doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – KYC) Directions, 2025")]
    vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    assert provenance_counts(vocab)[PROVENANCE_RAW] == 0


def test_derived_terms_carry_an_explanatory_note():
    """The marker is machine-readable; the note is what a human reads next."""
    records = [_doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – KYC) Directions, 2025")]
    vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    term = vocab.resolve("KYC")
    assert term.notes
    assert "DERIVED" in term.notes


def test_provenance_lookup_maps_every_canonical_name():
    records = [
        _doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – KYC) Directions, 2025"),
        _doc("d2", "Small Finance Banks", "Reserve Bank of India (Small Finance Banks – Governance) Directions, 2025"),
    ]
    vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    lookup = provenance_lookup(vocab)
    assert set(lookup) == {t.canonical_name for t in vocab}
    assert set(lookup.values()) == {PROVENANCE_DERIVED}


# -- segmented unresolved rate (Task 4), hand-checkable fixture --------------


def test_segmented_rate_reports_not_measurable_when_no_raw_values_exist():
    """4 documents, none with subject_family_raw, 1 unresolved. The raw-only
    rate must be NOT MEASURABLE — reporting 0.0 would falsely imply raw
    values were examined and found clean."""
    records = [_doc(f"d{i}", "Commercial Banks", f"t{i}") for i in range(4)]
    subject_unresolved = [{"document_id": "d0", "entity_class_raw": "Commercial Banks", "title": "t0", "reason": "r"}]

    rates = segmented_unresolved_rates(records, [], subject_unresolved)

    assert rates["documents_total"] == 4
    assert rates["subject_family_raw_sourced_documents"] == 0
    assert rates["subject_family_derived_documents"] == 4
    assert rates["subject_family_unresolved_rate_combined"] == pytest.approx(0.25)
    assert "NOT MEASURABLE" in rates["subject_family_unresolved_rate_raw_sourced_only"]


def test_segmented_rate_computes_a_real_raw_only_rate_when_raw_values_exist():
    """Same shape, but 2 of 4 documents DO carry subject_family_raw and one of
    those is unresolved -> raw-only rate is a real 0.5, not NOT MEASURABLE."""
    records = [
        _doc("d0", "Commercial Banks", "t0", subject_family_raw="KYC"),
        _doc("d1", "Commercial Banks", "t1", subject_family_raw="Governance"),
        _doc("d2", "Commercial Banks", "t2"),
        _doc("d3", "Commercial Banks", "t3"),
    ]
    subject_unresolved = [{"document_id": "d0", "entity_class_raw": "Commercial Banks", "title": "t0", "reason": "r"}]

    rates = segmented_unresolved_rates(records, [], subject_unresolved)

    assert rates["subject_family_raw_sourced_documents"] == 2
    assert rates["subject_family_derived_documents"] == 2
    assert rates["subject_family_unresolved_rate_raw_sourced_only"] == pytest.approx(0.5)


def test_segmented_rate_entity_class_rate_is_measured_on_raw_values():
    records = [_doc(f"d{i}", "Commercial Banks", f"t{i}") for i in range(4)]
    rates = segmented_unresolved_rates(records, ["d0"], [])
    assert rates["entity_class_raw_sourced_documents"] == 4
    assert rates["entity_class_unresolved_rate_raw_sourced"] == pytest.approx(0.25)


# -- MatrixCell provenance marking ------------------------------------------


def test_matrix_cells_record_both_axes_provenance():
    records = [
        _doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – KYC) Directions, 2025")
    ]
    entity_vocab, _ = discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    subject_vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    normalised = normalise_documents(records, entity_vocab, subject_vocab)

    cells = build_matrix(normalised, entity_vocab, subject_vocab, MINIMAL_CONFIG)
    assert cells
    for cell in cells:
        assert cell.notes
        assert f"entity_class={PROVENANCE_RAW}" in cell.notes
        assert f"subject_family={PROVENANCE_DERIVED}" in cell.notes
        assert "DERIVED axis present" in cell.notes


def test_matrix_cells_still_pass_schema_validation_with_notes():
    records = [_doc("d1", "Commercial Banks", "Reserve Bank of India (Commercial Banks – KYC) Directions, 2025")]
    entity_vocab, _ = discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    subject_vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    normalised = normalise_documents(records, entity_vocab, subject_vocab)
    for cell in build_matrix(normalised, entity_vocab, subject_vocab, MINIMAL_CONFIG):
        assert cell.validate() == []


# -- the real corpus: assumptions behind "no schema change needed" -----------


def _real_records() -> list[DocumentRecord]:
    try:
        rows = read_jsonl("data/metadata/document_manifest.jsonl")
    except Exception:  # noqa: BLE001
        pytest.skip("document_manifest.jsonl not present in this checkout")
    if not rows:
        pytest.skip("document_manifest.jsonl is empty")
    return [DocumentRecord.from_dict(r) for r in rows]


def test_real_corpus_has_no_mixed_provenance_term():
    """Section R / Task 3 guard. 'No schema change needed' rests on every term
    having exactly one provenance. If a future corpus ever breaks that, this
    fails loudly and the per-record `subject_family_source` field becomes
    genuinely necessary — see the schema-question answer in
    reports/phase1_karan_matrix.md."""
    records = _real_records()
    entity_vocab, _ = discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    subject_vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)

    mixed = [
        t.canonical_name
        for t in list(entity_vocab) + list(subject_vocab)
        if term_provenance(t) == PROVENANCE_MIXED
    ]
    assert mixed == [], f"mixed-provenance terms found — schema change now required: {mixed}"


def test_real_corpus_provenance_join_is_total():
    """The other half of 'no schema change needed': every normalised value on a
    record must resolve to exactly one vocabulary term, or provenance would be
    unrecoverable for some records."""
    records = _real_records()
    entity_vocab, _ = discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    subject_vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)
    normalised = normalise_documents(records, entity_vocab, subject_vocab)

    subject_names = {r.subject_family for r in normalised if r.subject_family}
    entity_names = {r.entity_class for r in normalised if r.entity_class}

    assert subject_names - set(provenance_lookup(subject_vocab)) == set()
    assert entity_names - set(provenance_lookup(entity_vocab)) == set()


def test_real_corpus_subject_family_raw_is_absent_everywhere():
    """The finding itself, asserted as a test so it cannot silently change
    without someone noticing."""
    records = _real_records()
    assert all(r.subject_family_raw is None for r in records)


def test_committed_provenance_artifact_matches_the_vocabularies():
    """vocabulary_provenance.json is what downstream consumers are told to
    read — it must not drift from the vocabulary files it summarises."""
    try:
        artifact = read_json("data/metadata/vocabulary_provenance.json")
    except Exception:  # noqa: BLE001
        pytest.skip("vocabulary_provenance.json not present in this checkout")

    records = _real_records()
    entity_vocab, _ = discover_entity_class_vocabulary(records, MINIMAL_CONFIG)
    subject_vocab, _ = discover_subject_family_vocabulary(records, MINIMAL_CONFIG)

    assert artifact["entity_class"]["counts"] == provenance_counts(entity_vocab)
    assert artifact["subject_family"]["counts"] == provenance_counts(subject_vocab)
