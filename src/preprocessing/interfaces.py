"""Segmentation and cross-reference interfaces — implemented by ``phase1/akash-scraper``.

Turns extracted document text into :class:`~src.schemas.provenance.ParagraphRecord`
units, the atom of retrieval and annotation.

Implementation note: paragraph IDs must come from
:func:`src.schemas.provenance.stable_paragraph_id` and nothing else. Annotations
are keyed on that value, so an ID scheme that changes between runs silently
detaches completed annotation work from the text it described.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.schemas.provenance import DocumentRecord, ParagraphRecord

BRANCH = "phase1/akash-scraper"


def segment_document(
    record: DocumentRecord, text: str, cfg: Mapping[str, Any], **kwargs: Any
) -> list[ParagraphRecord]:
    """Split one document's text into paragraph records.

    Must populate ``paragraph_id``, ``document_id``, ``position``,
    ``char_start``/``char_end``, and the section/clause fields where the source
    structure allows.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"segment_document is implemented by {BRANCH}")


def segment_corpus(cfg: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Segment every extracted document, returning measured metrics.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"segment_corpus is implemented by {BRANCH}")


def resolve_cross_references(cfg: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Populate ``ParagraphRecord.cross_reference_ids`` across the corpus.

    Note the schema's non-nullable empty-list default: a paragraph with no
    resolved references is a measurement, and must not be confused with one that
    was never examined.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"resolve_cross_references is implemented by {BRANCH}")
