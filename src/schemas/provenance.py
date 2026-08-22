"""Provenance contracts: the document and paragraph records.

Every downstream artifact — matrix cells, obligation candidates, T1 labels,
retrieval results — must trace back to a :class:`ParagraphRecord`, and every
paragraph back to a :class:`DocumentRecord`. That chain is what makes the
benchmark auditable, and it is also what lets the project publish
offsets-and-identifiers rather than republishing RBI text, which the licensing
position requires.

Nullability policy at Phase 0
-----------------------------
Per the Phase 0 specification, fields are nullable because no branch has
populated them yet. Two exceptions are made deliberately:

* ``document_id`` on both records
* ``paragraph_id`` on :class:`ParagraphRecord`

These are the join keys. A record whose identifier is null cannot be referenced
by any other artifact, so permitting null there would define a record that
nothing downstream could ever use. Every other field, including text and source
URL, may legitimately be absent during an intermediate pipeline stage.

Raw vs normalised
-----------------
``entity_class_raw`` / ``subject_family_raw`` hold exactly what the source page
said. ``entity_class`` / ``subject_family`` hold the normalised value. They are
separate fields on purpose: normalisation is a Week 3 research decision owned by
one branch, and overwriting the raw value in place would make that decision
unauditable and irreversible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from src.schemas.base import LATER, MATRIX, SCRAPER, FieldSpec, SchemaRecord

#: Documented values for ``extraction_source``. Not an enum: the set of sources
#: is discovered during harvesting, and a closed enum here would force a base
#: branch change every time a new source type is found.
KNOWN_EXTRACTION_SOURCES = (
    "rbi_master_directions",
    "rbi_faq",
    "rbi_circulars",
    "rbi_circulars_withdrawn",
    "rbi_enforcement",
    "rbi_amendments",
)

#: Documented values for ``document_role``.
KNOWN_DOCUMENT_ROLES = (
    "primary_corpus",  # in-scope Master Directions
    "supplementary",  # FAQs, circulars, enforcement — context, not corpus
    "validation",  # used to check the corpus, not to build it
)


@dataclass
class DocumentRecord(SchemaRecord):
    """One harvested source document and its provenance."""

    document_id: str
    source_url: str | None = None
    title: str | None = None
    entity_class_raw: str | None = None
    subject_family_raw: str | None = None
    entity_class: str | None = None
    subject_family: str | None = None
    update_date: str | None = None
    extraction_source: str | None = None
    document_role: str | None = None
    format: str | None = None
    local_path: str | None = None
    content_hash: str | None = None
    retrieved_at: str | None = None

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "document_id", (str,), True, False,
            "Stable identifier for this document, unique across the corpus. The join key every other artifact references.",
            SCRAPER,
        ),
        FieldSpec(
            "source_url", (str,), False, True,
            "Canonical URL the document was retrieved from. Retained so downstream artifacts can cite a source without redistributing text.",
            SCRAPER,
        ),
        FieldSpec(
            "title", (str,), False, True,
            "Document title exactly as published by the source.",
            SCRAPER,
        ),
        FieldSpec(
            "entity_class_raw", (str,), False, True,
            "Regulated-entity class exactly as it appeared on the source listing, before any normalisation.",
            SCRAPER,
        ),
        FieldSpec(
            "subject_family_raw", (str,), False, True,
            "Subject/topic exactly as it appeared on the source listing, before any normalisation.",
            SCRAPER,
        ),
        FieldSpec(
            "entity_class", (str,), False, True,
            "Normalised entity class, resolved against the discovered entity-class vocabulary.",
            MATRIX,
        ),
        FieldSpec(
            "subject_family", (str,), False, True,
            "Normalised subject family, resolved against the discovered subject-family vocabulary.",
            MATRIX,
        ),
        FieldSpec(
            "update_date", (str,), False, True,
            "Last-updated date stamp as published, kept verbatim as a string because source formats are inconsistent. Parsing is a downstream concern.",
            SCRAPER,
        ),
        FieldSpec(
            "extraction_source", (str,), False, True,
            f"Which source family this came from. Known values: {', '.join(KNOWN_EXTRACTION_SOURCES)}.",
            SCRAPER,
        ),
        FieldSpec(
            "document_role", (str,), False, True,
            f"Role in the study. Known values: {', '.join(KNOWN_DOCUMENT_ROLES)}. Distinguishes corpus from context.",
            SCRAPER,
        ),
        FieldSpec(
            "format", (str,), False, True,
            "Retrieved file format, e.g. PDF or HTML.",
            SCRAPER,
        ),
        FieldSpec(
            "local_path", (str,), False, True,
            "Path the payload was cached at, relative to the active working root. Never an absolute Kaggle path.",
            SCRAPER,
        ),
        FieldSpec(
            "content_hash", (str,), False, True,
            "SHA-256 of the retrieved bytes. Detects silent source changes and duplicate documents published under two IDs.",
            SCRAPER,
        ),
        FieldSpec(
            "retrieved_at", (str,), False, True,
            "ISO-8601 timestamp of retrieval. Establishes the corpus snapshot date for amendment-awareness claims.",
            SCRAPER,
        ),
    )


@dataclass
class ParagraphRecord(SchemaRecord):
    """One paragraph of one document, with full provenance back to its source.

    This is the unit of retrieval and the unit obligations are anchored to.
    """

    paragraph_id: str
    document_id: str
    document_title: str | None = None
    source_url: str | None = None
    entity_class: str | None = None
    subject_family: str | None = None
    update_date: str | None = None
    extraction_source: str | None = None
    section_id: str | None = None
    section_title: str | None = None
    clause_id: str | None = None
    clause_path: str | None = None
    position: int | None = None
    text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    content_hash: str | None = None
    cross_reference_ids: list[str] = field(default_factory=list)
    retrieval_chunk_id: str | None = None
    retrieval_chunk_index: int | None = None
    retrieval_embedding_model: str | None = None
    retrieval_index_id: str | None = None

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "paragraph_id", (str,), True, False,
            "Stable, deterministic identifier for this paragraph. Must be reproducible from (document_id, position) so re-running extraction does not invalidate existing annotations.",
            SCRAPER,
        ),
        FieldSpec(
            "document_id", (str,), True, False,
            "Identifier of the DocumentRecord this paragraph came from.",
            SCRAPER,
        ),
        FieldSpec(
            "document_title", (str,), False, True,
            "Denormalised document title, carried for annotator context without a second lookup.",
            SCRAPER,
        ),
        FieldSpec(
            "source_url", (str,), False, True,
            "Denormalised source URL, so a benchmark item is citable on its own.",
            SCRAPER,
        ),
        FieldSpec(
            "entity_class", (str,), False, True,
            "Normalised entity class inherited from the parent document. NOT an applicability judgement — see T1Label.applies_to.",
            MATRIX,
        ),
        FieldSpec(
            "subject_family", (str,), False, True,
            "Normalised subject family inherited from the parent document.",
            MATRIX,
        ),
        FieldSpec(
            "update_date", (str,), False, True,
            "Update date inherited from the parent document, kept verbatim as a string.",
            SCRAPER,
        ),
        FieldSpec(
            "extraction_source", (str,), False, True,
            "Source family inherited from the parent document.",
            SCRAPER,
        ),
        FieldSpec(
            "section_id", (str,), False, True,
            "Section number as printed, e.g. '4' or 'Chapter III'. Required for citation-grade provenance; a bare paragraph index is not a legal reference.",
            SCRAPER,
        ),
        FieldSpec(
            "section_title", (str,), False, True,
            "Section heading text as printed.",
            SCRAPER,
        ),
        FieldSpec(
            "clause_id", (str,), False, True,
            "Innermost clause label as printed, e.g. '(a)' or '(iii)'.",
            SCRAPER,
        ),
        FieldSpec(
            "clause_path", (str,), False, True,
            "Full hierarchical path to the clause, e.g. '4.2(a)(iii)'. This is what a compliance answer must cite.",
            SCRAPER,
        ),
        FieldSpec(
            "position", (int,), False, True,
            "Zero-based ordinal of this paragraph within its document. Combined with document_id, determines paragraph_id.",
            SCRAPER,
        ),
        FieldSpec(
            "text", (str,), False, True,
            "Paragraph text. Held for processing; excluded from any redistributable artifact pending the licensing decision.",
            SCRAPER,
        ),
        FieldSpec(
            "char_start", (int,), False, True,
            "Start offset of this paragraph in the document's extracted text.",
            SCRAPER,
        ),
        FieldSpec(
            "char_end", (int,), False, True,
            "End offset (exclusive) of this paragraph in the document's extracted text.",
            SCRAPER,
        ),
        FieldSpec(
            "content_hash", (str,), False, True,
            "SHA-256 of the paragraph text. Detects whether an amendment changed this paragraph between corpus snapshots.",
            SCRAPER,
        ),
        FieldSpec(
            "cross_reference_ids", (list,), False, False,
            "Paragraph IDs this paragraph refers to. Empty list means none found, which is a measurement; null would mean not yet checked, so this field is non-nullable.",
            SCRAPER,
        ),
        FieldSpec(
            "retrieval_chunk_id", (str,), False, True,
            "Identifier of the retrieval chunk containing this paragraph. Reserved for the retrieval phase.",
            LATER,
        ),
        FieldSpec(
            "retrieval_chunk_index", (int,), False, True,
            "Ordinal of this paragraph within its retrieval chunk, when chunks span paragraphs.",
            LATER,
        ),
        FieldSpec(
            "retrieval_embedding_model", (str,), False, True,
            "Identifier of the embedding model used to index this paragraph. Recorded per record because ablations compare indexes built with different models.",
            LATER,
        ),
        FieldSpec(
            "retrieval_index_id", (str,), False, True,
            "Identifier of the index build this record belongs to, so evaluation results are attributable to a specific index.",
            LATER,
        ),
    )


def stable_paragraph_id(document_id: str, position: int) -> str:
    """Derive the canonical paragraph identifier.

    Defined on the base branch, not in the segmenter, because annotations are
    keyed on this value: if two branches derived it differently, previously
    annotated items would silently detach from their paragraphs.

    Format: ``<document_id>::p<position zero-padded to 5>``.
    """
    if not document_id:
        raise ValueError("document_id must be non-empty to derive a paragraph_id")
    if position < 0:
        raise ValueError(f"position must be non-negative, got {position}")
    return f"{document_id}::p{position:05d}"
