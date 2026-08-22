"""Intra-document cross-reference resolution.

Implements :func:`~src.preprocessing.interfaces.resolve_cross_references`. Runs
as a second pass, after :mod:`src.preprocessing.segmenter` has produced every
document's full paragraph set — resolving a reference to "paragraph 4.2"
requires already knowing which paragraph, if any, carries ``section_id ==
"4.2"``, and that index cannot exist until the whole document is segmented.

Scope is deliberately narrow: **within one document only.** A reference to
another Direction entirely ("as specified in the Master Direction on KYC") is
detected as a phrase but has no target paragraph_id this pass can resolve —
cross-document reference resolution needs the normalised entity/subject
vocabulary from ``phase1/karan-matrix`` and is out of scope here.

A detected phrase that cannot be resolved to an existing ``paragraph_id`` is
**not** recorded. ``ParagraphRecord.cross_reference_ids`` holds actual paragraph
identifiers, not free-text guesses, and fabricating a plausible-looking ID that
does not correspond to a real paragraph would be worse than recording nothing —
it would look like a resolved reference when it is not.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from src.common.io_helpers import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.preprocessing.segmenter import (
    LOCATOR_CHAPTER_RE,
    LOCATOR_CLAUSE_RE,
    LOCATOR_PARA_RE,
    XREF_PHRASE_RE,
)
from src.schemas.provenance import DocumentRecord, ParagraphRecord

BRANCH = "phase1/akash-scraper"


def _build_locator_index(paragraphs: list[ParagraphRecord]) -> dict[str, str]:
    """Map every locator string a reference might name to a paragraph_id.

    Includes both the bare section number ("4.2") and the full clause path
    ("4.2(a)"), each pointing at the *first* paragraph carrying it — a
    reference to a paragraph number almost always means the paragraph as a
    whole, not a specific later sub-clause that happens to share the number.
    """
    index: dict[str, str] = {}
    for paragraph in paragraphs:
        if paragraph.section_id and paragraph.section_id not in index:
            index[paragraph.section_id] = paragraph.paragraph_id
        if paragraph.clause_path and paragraph.clause_path not in index:
            index[paragraph.clause_path] = paragraph.paragraph_id
    return index


def _resolve_locator(locator_text: str, index: Mapping[str, str]) -> str | None:
    """Best-effort resolution of one reference phrase's locator text."""
    clause_match = LOCATOR_CLAUSE_RE.search(locator_text)
    para_match = LOCATOR_PARA_RE.search(locator_text)
    if para_match and clause_match:
        combined = f"{para_match.group('number')}({clause_match.group('label').lower()})"
        if combined in index:
            return index[combined]
    if para_match and para_match.group("number") in index:
        return index[para_match.group("number")]

    chapter_match = LOCATOR_CHAPTER_RE.search(locator_text)
    if chapter_match:
        for kind in ("Chapter", "Part"):
            key = f"{kind} {chapter_match.group('numeral').upper()}"
            if key in index:
                return index[key]
    return None


def _detect_cross_references(text: str, index: Mapping[str, str]) -> list[str]:
    """Every distinct, resolved paragraph_id referenced from `text`."""
    resolved: list[str] = []
    for match in XREF_PHRASE_RE.finditer(text or ""):
        target = _resolve_locator(match.group("locator_text"), index)
        if target and target not in resolved:
            resolved.append(target)
    return resolved


def resolve_cross_references(
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Detect and resolve intra-document cross-references across the corpus.

    Rewrites each ``data/processed/<document_id>.jsonl`` in place with
    ``cross_reference_ids`` populated, and refreshes
    ``data/processed/paragraphs_index.jsonl`` to match.
    """
    logger = logger or get_logger("preprocessing.cross_references", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    manifest_path = resolver.read_path("metadata", "document_manifest.jsonl")
    records = [DocumentRecord.from_dict(r) for r in read_jsonl(manifest_path)]

    phrases_detected = 0
    references_resolved = 0
    documents_processed = 0
    index_rows: list[dict[str, Any]] = []

    for record in records:
        doc_path = resolver.find_read_path("processed", f"{record.document_id}.jsonl")
        if doc_path is None:
            continue

        paragraphs = [ParagraphRecord.from_dict(r) for r in read_jsonl(doc_path)]
        if not paragraphs:
            continue

        index = _build_locator_index(paragraphs)
        updated: list[ParagraphRecord] = []
        for paragraph in paragraphs:
            phrase_count = len(XREF_PHRASE_RE.findall(paragraph.text or ""))
            phrases_detected += phrase_count
            resolved_ids = _detect_cross_references(paragraph.text or "", index)
            references_resolved += len(resolved_ids)
            paragraph.cross_reference_ids = resolved_ids
            updated.append(paragraph)

        write_jsonl(doc_path, [p.to_dict() for p in updated])
        for paragraph in updated:
            slim = paragraph.to_dict()
            slim.pop("text", None)
            slim["text_char_count"] = len(paragraph.text or "")
            index_rows.append(slim)
        documents_processed += 1

    if index_rows:
        index_path = resolver.write_path("processed", "paragraphs_index.jsonl")
        write_jsonl(index_path, index_rows)

    metrics = {
        "documents_processed": documents_processed,
        "cross_reference_phrases_detected": phrases_detected,
        "cross_reference_count": references_resolved,
        "resolution_rate": (references_resolved / phrases_detected) if phrases_detected else "NOT YET MEASURED",
    }
    logger.info("resolve_cross_references: %s", metrics)
    return metrics
