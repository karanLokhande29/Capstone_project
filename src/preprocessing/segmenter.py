"""Paragraph segmentation with citation-grade structural provenance.

Implements :func:`~src.preprocessing.interfaces.segment_document` and
:func:`~src.preprocessing.interfaces.segment_corpus`. Splits extracted document
text into :class:`~src.schemas.provenance.ParagraphRecord` units, tracking real
character offsets into the source text and, where the printed structure allows
it, the chapter/paragraph-number/sub-clause path a citation needs.

Structure tracking is a state walk down the document rather than a per-block
regex match in isolation: most paragraph blocks in RBI Master Directions are
continuation text with no marker of their own (a definition's second sentence,
a sub-clause's closing line), and the only way to know which section they
belong to is to have been tracking it since the last marker was seen. A block
that introduces no marker of its own **inherits** the current section/clause
state — this is not a guess, it is exactly what "continuation of the last
numbered paragraph" means. A block is only counted as unparsed structure when
no marker has ever been seen yet in the document (front matter — title, short
title, preamble — before the first numbered paragraph, which is normal and
expected, not a parse failure).

The alpha/roman sub-clause split is a heuristic, not a certainty: "(i)" is
typographically ambiguous between a roman numeral and, rarely, a letter. This
module resolves it by context (a roman-shaped label nests under an active
alpha label; otherwise it is treated as alpha) and reports how many blocks
matched each pattern, so the heuristic's coverage is measurable rather than
assumed.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from src.common.io_helpers import read_jsonl, read_text, write_jsonl
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.schemas.provenance import DocumentRecord, ParagraphRecord, stable_paragraph_id

BRANCH = "phase1/akash-scraper"

#: Below this many characters a non-heading block is treated as noise (running
#: headers, bare page numbers, stray artefacts from PDF extraction) rather than
#: a real paragraph. Chosen low enough that a genuinely short clause survives —
#: RBI definitions are sometimes one short sentence.
MIN_PARAGRAPH_CHARS = 15

CHAPTER_RE = re.compile(
    r"^(?P<kind>CHAPTER|PART)\s+(?P<numeral>[IVXLCDM]+|\d+)\b[ \t.:\-–—]*(?P<title>[^\n]*)",
    re.IGNORECASE,
)
PARA_NUM_RE = re.compile(r"^(?P<number>\d{1,3}(?:\.\d{1,3}){0,4})\.\s+\S")
CLAUSE_ROMAN_RE = re.compile(
    r"^\((?P<label>i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)\)\s+\S",
    re.IGNORECASE,
)
CLAUSE_ALPHA_RE = re.compile(r"^\((?P<label>[a-z])\)\s+\S", re.IGNORECASE)

#: Phrases that typically introduce a cross-reference to another part of the
#: document, followed within a short window by a locator. Matched case-
#: insensitively; the phrase itself is not stored, only used to anchor the
#: locator search that follows it.
XREF_PHRASE_RE = re.compile(
    r"(?:as\s+(?:specified|provided|laid\s+down|stated)\s+in|in\s+terms\s+of|"
    r"referred?\s+to\s+in|pursuant\s+to)\s+"
    r"(?P<locator_text>[^.;\n]{1,120})",
    re.IGNORECASE,
)
LOCATOR_PARA_RE = re.compile(r"\bparagraph\s+(?P<number>\d{1,3}(?:\.\d{1,3}){0,4})\b", re.IGNORECASE)
LOCATOR_CLAUSE_RE = re.compile(r"\bclause\s*\((?P<label>[a-z]|i|ii|iii|iv|v|vi|vii|viii|ix|x)\)", re.IGNORECASE)
LOCATOR_CHAPTER_RE = re.compile(r"\b(?:chapter|part)\s+(?P<numeral>[IVXLCDM]+|\d+)\b", re.IGNORECASE)


@dataclass
class _SegmentState:
    """Structural context tracked while walking a document's blocks."""

    section_id: str | None = None
    section_title: str | None = None
    clause_alpha: str | None = None
    clause_roman: str | None = None
    ever_matched: bool = False
    #: True right after a chapter/part heading whose title was not on the same
    #: line — RBI text commonly prints "Chapter I" and "Preliminary" as two
    #: separate lines. The next non-marker line is then the deferred title.
    awaiting_chapter_title: bool = False


def _clause_path(state: _SegmentState) -> str | None:
    if state.section_id is None and state.clause_alpha is None:
        return None
    parts = [state.section_id or ""]
    if state.clause_alpha:
        parts.append(f"({state.clause_alpha})")
    if state.clause_roman:
        parts.append(f"({state.clause_roman})")
    return "".join(parts) or None


def _is_marker_line(line: str) -> bool:
    """Whether `line` (already stripped) opens a new chapter/paragraph/clause."""
    return bool(
        CHAPTER_RE.match(line)
        or PARA_NUM_RE.match(line)
        or CLAUSE_ALPHA_RE.match(line)
        or CLAUSE_ROMAN_RE.match(line)
    )


def _split_blocks(text: str) -> list[tuple[int, int]]:
    """Paragraph-unit spans, trimmed to content (no surrounding whitespace).

    A blank line always ends the current unit, same as before. But a
    structural marker line — a new chapter, a new numbered paragraph, or a new
    lettered/roman sub-clause — *also* ends the current unit even with no
    blank line separating them, because PDF extraction frequently runs a
    heading straight into the paragraph that follows it, or one numbered
    paragraph straight into the next, with no blank line at all. Without this,
    two or more logically distinct numbered paragraphs collapse into a single
    record carrying only the *last* one's number — which mislabels the first
    paragraph's text with the second paragraph's citation. See
    ``_apply_markers`` for why markers are also checked line-by-line rather
    than only at a unit's first line.

    Numeric sub-items in parentheses — "(1)", "(2)" — are deliberately not
    treated as markers here or anywhere in this module (see the module
    docstring): they stay folded into their parent numbered paragraph's unit,
    consistent with this module's documented scope of only the alpha/roman
    sub-clause level, not a third numeric-in-parens nesting level.
    """
    lines = text.splitlines(keepends=True)

    spans: list[tuple[int, int]] = []
    unit_start: int | None = None
    unit_has_content = False
    cursor = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if unit_start is not None and unit_has_content:
                spans.append((unit_start, cursor))
            unit_start = None
            unit_has_content = False
        elif _is_marker_line(stripped) and unit_start is not None and unit_has_content:
            spans.append((unit_start, cursor))
            unit_start = cursor
            unit_has_content = True
        else:
            if unit_start is None:
                unit_start = cursor
            unit_has_content = True
        cursor += len(line)

    if unit_start is not None and unit_has_content:
        spans.append((unit_start, cursor))

    trimmed: list[tuple[int, int]] = []
    for start, end in spans:
        raw = text[start:end]
        lstripped = raw.lstrip()
        lead = len(raw) - len(lstripped)
        content = lstripped.rstrip()
        if not content:
            continue
        trimmed.append((start + lead, start + lead + len(content)))
    return trimmed


def _apply_one_line(line: str, state: _SegmentState) -> bool:
    """Update `state` from a single line's leading marker, if it has one.

    Order matters: a chapter heading resets sub-clause context, a new numbered
    paragraph resets sub-clause context, a clause label only ever narrows or
    extends the current paragraph's context.
    """
    match = CHAPTER_RE.match(line)
    if match:
        numeral = match.group("numeral").upper()
        kind = match.group("kind").capitalize()
        state.section_id = f"{kind} {numeral}"
        title = match.group("title").strip(" -–—:.")
        if title:
            state.section_title = title
            state.awaiting_chapter_title = False
        else:
            # Title is on the next line — common in RBI text, e.g. "Chapter I"
            # and "Preliminary" printed as two separate lines.
            state.awaiting_chapter_title = True
        state.clause_alpha = None
        state.clause_roman = None
        state.ever_matched = True
        return True

    if state.awaiting_chapter_title:
        state.awaiting_chapter_title = False
        if not _is_marker_line(line):
            # A genuine deferred title line, not another marker (e.g. the
            # chapter heading was immediately followed by "1. Short title"
            # with no separate title line at all).
            state.section_title = line.strip(" -–—:.")
            return True

    match = PARA_NUM_RE.match(line)
    if match:
        state.section_id = match.group("number")
        state.clause_alpha = None
        state.clause_roman = None
        state.ever_matched = True
        return True

    roman_match = CLAUSE_ROMAN_RE.match(line)
    if roman_match and state.clause_alpha is not None:
        # A roman-shaped label with an active alpha context nests under it.
        state.clause_roman = roman_match.group("label").lower()
        state.ever_matched = True
        return True

    alpha_match = CLAUSE_ALPHA_RE.match(line)
    if alpha_match:
        state.clause_alpha = alpha_match.group("label").lower()
        state.clause_roman = None
        state.ever_matched = True
        return True

    if roman_match:
        # Roman-shaped label with no active alpha context: treat as the
        # top-level sub-clause rather than discarding the marker.
        state.clause_alpha = roman_match.group("label").lower()
        state.clause_roman = None
        state.ever_matched = True
        return True

    return False


def _apply_markers(block_text: str, state: _SegmentState) -> bool:
    """Update `state` in place from every structural marker in `block_text`.

    PDF extraction frequently yields a block spanning a heading transition
    plus the paragraph that immediately follows it, with no blank line between
    them (e.g. "Chapter II\\nOffice of the Ombudsman\\n5. Appointment...\\n(1) The
    IO shall..."). Checking only the block's first line would miss the "5."
    marker entirely and leave the whole block mis-attributed to whatever
    section preceded it. Each line is checked independently and markers are
    applied in order, so the block's *final* recorded position is its deepest
    actual structural location — which is also what state carries forward into
    the next block.

    Scanning every line (rather than only the first) risks a false match on
    body text that happens to start a line with something marker-shaped after
    a coincidental wrap. This is judged an acceptable and rare risk here
    because pdfplumber's line breaks come from the PDF's own line/word
    positions, not word-wrapping — a line beginning "(a)" in the extracted
    text corresponds to a line beginning that way in the typeset original.
    """
    matched_any = False
    for line in block_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if _apply_one_line(line, state):
            matched_any = True
    return matched_any


def segment_document(
    record: DocumentRecord,
    text: str,
    cfg: Mapping[str, Any],
    *,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> list[ParagraphRecord]:
    """Split one document's extracted text into paragraph records.

    Returns records with ``cross_reference_ids`` left empty — resolving them
    requires the full paragraph set of the document, which is only available
    after this function returns; see :func:`resolve_cross_references`.
    """
    logger = logger or get_logger("preprocessing.segmenter", cfg)
    spans = _split_blocks(text)

    state = _SegmentState()
    paragraphs: list[ParagraphRecord] = []
    position = 0
    dropped_short = 0
    unparsed_preamble = 0

    for start, end in spans:
        block_text = text[start:end]
        first_line = block_text.split("\n", 1)[0].strip()
        is_heading = CHAPTER_RE.match(first_line) is not None
        _apply_markers(block_text, state)

        if not is_heading and len(block_text) < MIN_PARAGRAPH_CHARS:
            dropped_short += 1
            continue

        if state.section_id is None:
            unparsed_preamble += 1

        paragraph_id = stable_paragraph_id(record.document_id, position)
        paragraphs.append(
            ParagraphRecord(
                paragraph_id=paragraph_id,
                document_id=record.document_id,
                document_title=record.title,
                source_url=record.source_url,
                update_date=record.update_date,
                extraction_source=record.extraction_source,
                section_id=state.section_id,
                section_title=state.section_title,
                clause_id=state.clause_roman or state.clause_alpha,
                clause_path=_clause_path(state),
                position=position,
                text=block_text,
                char_start=start,
                char_end=end,
                content_hash=hashlib.sha256(block_text.encode("utf-8")).hexdigest(),
                cross_reference_ids=[],
            )
        )
        position += 1

    if unparsed_preamble:
        logger.info(
            "segmentation: %s has %d front-matter paragraph(s) before any recognised "
            "section marker (expected for title/short-title/preamble text)",
            record.document_id,
            unparsed_preamble,
        )
    if not state.ever_matched:
        logger.warning(
            "segmentation: %s — no chapter, numbered paragraph, or clause marker "
            "recognised anywhere in the document; every paragraph lacks section_id/clause_path. "
            "This may indicate a document layout the parsing rules don't cover.",
            record.document_id,
        )

    logger.info(
        "segmentation: %s -> %d paragraphs (%d short blocks dropped, %d front-matter)",
        record.document_id,
        len(paragraphs),
        dropped_short,
        unparsed_preamble,
    )
    return paragraphs


def segment_corpus(
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Segment every extracted document into paragraph records.

    Reads ``data/metadata/document_manifest.jsonl`` and
    ``data/extracted/<document_id>.txt``, writes one
    ``data/processed/<document_id>.jsonl`` per document plus a text-free
    ``data/processed/paragraphs_index.jsonl`` across the whole corpus.
    """
    logger = logger or get_logger("preprocessing.segmenter", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    manifest_path = resolver.read_path("metadata", "document_manifest.jsonl")
    records = [DocumentRecord.from_dict(r) for r in read_jsonl(manifest_path)]

    total_paragraphs = 0
    documents_segmented = 0
    documents_missing_text = 0
    documents_no_structure = 0
    section_id_present = 0
    clause_path_present = 0
    index_rows: list[dict[str, Any]] = []

    for record in records:
        extracted = resolver.find_read_path("extracted", f"{record.document_id}.txt")
        if extracted is None:
            documents_missing_text += 1
            continue

        text = read_text(extracted)
        paragraphs = segment_document(record, text, cfg, logger=logger)
        if not paragraphs:
            continue

        if all(p.section_id is None for p in paragraphs):
            documents_no_structure += 1

        out_path = resolver.write_path("processed", f"{record.document_id}.jsonl")
        write_jsonl(out_path, [p.to_dict() for p in paragraphs])

        for paragraph in paragraphs:
            total_paragraphs += 1
            if paragraph.section_id is not None:
                section_id_present += 1
            if paragraph.clause_path is not None:
                clause_path_present += 1
            slim = paragraph.to_dict()
            slim.pop("text", None)
            slim["text_char_count"] = len(paragraph.text or "")
            index_rows.append(slim)

        documents_segmented += 1

    index_path = resolver.write_path("processed", "paragraphs_index.jsonl")
    write_jsonl(index_path, index_rows)

    metrics = {
        "documents_segmented": documents_segmented,
        "documents_missing_extracted_text": documents_missing_text,
        "documents_with_no_recognised_structure": documents_no_structure,
        "total_paragraphs": total_paragraphs,
        "section_id_coverage": (section_id_present / total_paragraphs) if total_paragraphs else "NOT YET MEASURED",
        "clause_path_coverage": (clause_path_present / total_paragraphs) if total_paragraphs else "NOT YET MEASURED",
        "index_path": str(index_path),
    }
    logger.info("segment_corpus: %s", metrics)
    return metrics
