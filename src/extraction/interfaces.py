"""Text extraction interfaces — implemented by ``phase1/akash-scraper``.

Converts harvested payloads (PDF, HTML) into plain text, preserving enough
structure for the segmenter to recover section and clause identifiers.

Implementation note: ``ParagraphRecord`` reserves ``section_id``,
``section_title``, ``clause_id`` and ``clause_path``. Those cannot be recovered
after extraction has flattened a document to an undifferentiated string, so
structural cues must be preserved here even though the consumer is downstream.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.schemas.provenance import DocumentRecord

BRANCH = "phase1/akash-scraper"


def extract_text(record: DocumentRecord, cfg: Mapping[str, Any], **kwargs: Any) -> str:
    """Extract plain text from one document's cached payload.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"extract_text is implemented by {BRANCH}")


def extract_corpus(cfg: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Extract text for every harvested document, returning measured metrics.

    Must distinguish three outcomes per document — extracted, extraction failed,
    and extracted-but-empty — because an empty extraction from a scanned PDF is
    a corpus-coverage finding, not a success.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"extract_corpus is implemented by {BRANCH}")
