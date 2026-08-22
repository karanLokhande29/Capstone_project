"""Tests for src.preprocessing.segmenter and src.preprocessing.cross_references.

Fixture text mirrors real structural patterns observed in RBI Master
Directions text (verified against live downloads while building this module):
a chapter heading running directly into its first numbered paragraph with no
blank line, numbered paragraphs running directly into the next with no blank
line, and lettered sub-clauses. No real network or downloaded documents
involved — the fixture text below is written for this test, not copied from
any RBI Direction.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from src.common.io_helpers import read_jsonl, write_jsonl
from src.common.paths import PathResolver
from src.preprocessing import cross_references as xref_module
from src.preprocessing import segmenter
from src.schemas.provenance import DocumentRecord, ParagraphRecord, stable_paragraph_id

MINIMAL_CONFIG = {
    "environment": {
        "mode": "local",
        "local": {"working_root": ".", "input_roots": []},
        "kaggle": {"working_root": "/kaggle/working", "input_root": "/kaggle/input", "input_datasets": []},
    },
    "paths": {
        k: k
        for k in (
            "raw",
            "extracted",
            "processed",
            "metadata",
            "matrix",
            "benchmark",
            "evaluation",
            "cache",
            "reports",
            "logs",
        )
    },
    "logging": {"level": "INFO", "format": "%(message)s", "to_file": False},
}


def _resolver(tmp_path):
    return PathResolver.from_config(MINIMAL_CONFIG, repo_root=tmp_path)


@contextmanager
def _capture_segmenter_logs(caplog):
    """Reliably route "preprocessing.segmenter" records into `caplog`.

    Two things make a plain `propagate = True` flip ineffective here, verified
    by direct instrumentation before settling on this approach: `get_logger()`
    (src/common/logging_setup.py, base-owned) unconditionally resets
    `propagate = False` on *every* call, and `segment_document` calls
    `get_logger()` again internally whenever it isn't passed an explicit
    `logger=` — so a flip applied before calling it is silently undone before
    the actual `logger.warning(...)` call executes; printing propagate
    immediately before and after the call showed True flipping back to False
    mid-call. Relying instead on pytest's own non-propagating-logger registry
    scan (attaching its handler directly to already-registered
    propagate=False loggers) also isn't safe: it only fires for loggers
    already registered when a test's capture wrapper starts, and it turned
    out to be pytest-version-dependent besides — present in a form that
    happened to make this pass on pytest 9.1 locally, but not on Kaggle's
    pytest 8.4.

    Attaching `caplog.handler` to the logger directly, for the duration of
    this block, sidesteps all of that: capture no longer depends on
    `propagate` being (or staying) True, on registry timing, or on which
    pytest version implements which scan.
    """
    logger = logging.getLogger("preprocessing.segmenter")
    logger.addHandler(caplog.handler)
    try:
        yield
    finally:
        logger.removeHandler(caplog.handler)


# A document text mirroring real RBI structure: a chapter heading running
# straight into its first numbered paragraph (no blank line — this is the
# real-world pattern that broke the first version of the segmenter), two
# numbered paragraphs back to back with no blank line, and lettered
# sub-clauses.
FIXTURE_TEXT = (
    "RESERVE BANK OF INDIA\n"
    "Master Direction Test Document, 2026\n"
    "\n"
    "Chapter I\n"
    "Preliminary\n"
    "1. Short Title and Commencement\n"
    "(1) These Directions shall be called the Test Directions, 2026.\n"
    "(2) They shall come into force with immediate effect.\n"
    "\n"
    "2. Applicability\n"
    "(1) These Directions shall be applicable to Commercial Banks.\n"
    "3. Definitions\n"
    "(1) In these Directions, the terms herein shall bear the meanings assigned below:\n"
    "(a) \"Customer\" means a person who uses a service provided by the bank;\n"
    "(b) \"Complaint\" means a representation alleging deficiency in service;\n"
    "(i) submitted in writing, or\n"
    "(ii) submitted through other modes.\n"
    "\n"
    "Chapter II\n"
    "Obligations\n"
    "4. Reporting\n"
    "(1) As specified in paragraph 3, banks shall maintain records as defined therein.\n"
    "(2) Banks shall also comply in terms of clause (a) of paragraph 3.\n"
)


# -- block splitting / marker detection ---------------------------------------


def test_split_blocks_separates_blank_line_delimited_content():
    spans = segmenter._split_blocks("First paragraph text here.\n\nSecond paragraph text here.")
    assert len(spans) == 2


def test_split_blocks_splits_on_marker_without_blank_line():
    """The exact real-world case: a chapter heading running into a numbered paragraph."""
    text = "Chapter I\nPreliminary\n1. Short title.\n(1) Body text of clause one."
    spans = segmenter._split_blocks(text)
    texts = [text[s:e] for s, e in spans]
    assert texts[0].startswith("Chapter I")
    assert texts[1].startswith("1. Short title.")


def test_split_blocks_splits_consecutive_numbered_paragraphs():
    text = "3. Applicability\n(1) Applies to banks.\n4. Definitions\n(1) Terms defined here."
    spans = segmenter._split_blocks(text)
    texts = [text[s:e] for s, e in spans]
    assert any(t.startswith("3. Applicability") for t in texts)
    assert any(t.startswith("4. Definitions") for t in texts)
    assert not any("4. Definitions" in t and "3. Applicability" in t for t in texts)


def test_split_blocks_splits_lettered_sub_clauses():
    text = "4. Definitions\n(a) First term defined here fully.\n(b) Second term defined here fully."
    spans = segmenter._split_blocks(text)
    texts = [text[s:e] for s, e in spans]
    assert any(t.startswith("(a)") for t in texts)
    assert any(t.startswith("(b)") for t in texts)


def test_split_blocks_offsets_point_at_trimmed_content():
    text = "  \n\n   1. Padded paragraph.   \n\n"
    spans = segmenter._split_blocks(text)
    assert len(spans) == 1
    start, end = spans[0]
    assert text[start:end] == "1. Padded paragraph."


def test_is_marker_line_recognises_all_three_kinds():
    assert segmenter._is_marker_line("Chapter I")
    assert segmenter._is_marker_line("PART IV")
    assert segmenter._is_marker_line("4. Definitions")
    assert segmenter._is_marker_line("(a) some text")
    assert segmenter._is_marker_line("(iii) some text")
    assert not segmenter._is_marker_line("Ordinary continuation sentence.")


# -- segment_document: structure ----------------------------------------------


def _doc_record(document_id="md_test"):
    return DocumentRecord(
        document_id=document_id,
        title="Test Direction",
        source_url="https://example.org/test.pdf",
        update_date="March 1, 2026",
        extraction_source="rbi_master_directions",
    )


def test_segment_document_produces_paragraph_records():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    assert paragraphs
    assert all(isinstance(p, ParagraphRecord) for p in paragraphs)


def test_segment_document_assigns_correct_section_ids_not_the_last_seen_marker():
    """Regression test for the bug this module's docstring documents: text of
    paragraph "2. Applicability" must not be mislabelled with paragraph 3's
    number just because they shared a block before the marker-aware split."""
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    section_2_texts = [p.text for p in paragraphs if p.section_id == "2"]
    section_3_texts = [p.text for p in paragraphs if p.section_id == "3"]
    assert any("Applicability" in t for t in section_2_texts)
    assert not any("Applicability" in t for t in section_3_texts)
    assert any("Definitions" in t for t in section_3_texts)


def test_segment_document_chapter_heading_resets_clause_context():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    chapter_two = next(p for p in paragraphs if p.text.startswith("Chapter II"))
    assert chapter_two.section_id == "Chapter II"
    assert chapter_two.clause_id is None


def test_segment_document_builds_clause_path_with_alpha_and_roman_nesting():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    by_text_prefix = {p.text[:5]: p for p in paragraphs}
    clause_b = by_text_prefix["(b) \""]
    assert clause_b.clause_path == "3(b)"
    roman_i = by_text_prefix["(i) s"]
    assert roman_i.clause_path == "3(b)(i)"
    assert roman_i.clause_id == "i"


def test_segment_document_section_title_carries_from_chapter():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    numbered_one = next(p for p in paragraphs if p.section_id == "1")
    assert numbered_one.section_title == "Preliminary"


def test_segment_document_denormalises_document_fields():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    assert all(p.document_id == "md_test" for p in paragraphs)
    assert all(p.document_title == "Test Direction" for p in paragraphs)
    assert all(p.source_url == "https://example.org/test.pdf" for p in paragraphs)
    assert all(p.update_date == "March 1, 2026" for p in paragraphs)


def test_segment_document_cross_reference_ids_start_empty():
    """Resolution is a separate pass; segment_document alone never fabricates one."""
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    assert all(p.cross_reference_ids == [] for p in paragraphs)


def test_segment_document_offsets_index_into_original_text():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    for p in paragraphs:
        assert FIXTURE_TEXT[p.char_start : p.char_end] == p.text


def test_segment_document_content_hash_matches_text():
    import hashlib

    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    for p in paragraphs:
        assert p.content_hash == hashlib.sha256(p.text.encode("utf-8")).hexdigest()


def test_segment_document_drops_short_non_heading_blocks():
    text = "1. Real Paragraph\nThis is a genuinely long enough paragraph of real content.\n\nx\n"
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, text, {})
    assert all(len(p.text) >= segmenter.MIN_PARAGRAPH_CHARS or p.text.startswith("Chapter") for p in paragraphs)
    assert not any(p.text == "x" for p in paragraphs)


def test_segment_document_keeps_short_chapter_headings():
    text = "Chapter I\nA\n\n1. Body text long enough to survive the minimum length filter here."
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, text, {})
    assert any(p.text.startswith("Chapter I") for p in paragraphs)


def test_segment_document_on_unstructured_text_leaves_everything_null_and_warns(caplog):
    """No chapter/paragraph/clause marker anywhere: fail loudly, don't guess."""
    text = "Just some flowing prose with no numbering at all in this document body text here."
    record = _doc_record()
    with _capture_segmenter_logs(caplog), caplog.at_level("WARNING", logger="preprocessing.segmenter"):
        paragraphs = segmenter.segment_document(record, text, {})
    assert paragraphs
    assert all(p.section_id is None for p in paragraphs)
    assert "no chapter, numbered paragraph, or clause marker" in caplog.text


# -- stable_paragraph_id determinism -------------------------------------------


def test_paragraph_ids_are_deterministic_across_two_runs():
    record = _doc_record()
    run_1 = segmenter.segment_document(record, FIXTURE_TEXT, {})
    run_2 = segmenter.segment_document(record, FIXTURE_TEXT, {})
    assert [p.paragraph_id for p in run_1] == [p.paragraph_id for p in run_2]


def test_paragraph_ids_use_stable_paragraph_id_convention():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    for p in paragraphs:
        assert p.paragraph_id == stable_paragraph_id(record.document_id, p.position)


def test_paragraph_ids_are_unique_within_a_document():
    record = _doc_record()
    paragraphs = segmenter.segment_document(record, FIXTURE_TEXT, {})
    ids = [p.paragraph_id for p in paragraphs]
    assert len(ids) == len(set(ids))


# -- segment_corpus -------------------------------------------------------------


def test_segment_corpus_reads_manifest_and_extracted_text_writes_processed(tmp_path):
    resolver = _resolver(tmp_path)
    record = _doc_record()
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [record.to_dict()])
    resolver.write_path("extracted", f"{record.document_id}.txt").write_text(FIXTURE_TEXT, encoding="utf-8")

    metrics = segmenter.segment_corpus({}, resolver=resolver)

    assert metrics["documents_segmented"] == 1
    assert metrics["total_paragraphs"] > 0
    rows = read_jsonl(resolver.read_path("processed", f"{record.document_id}.jsonl"))
    assert len(rows) == metrics["total_paragraphs"]


def test_segment_corpus_writes_text_free_index(tmp_path):
    resolver = _resolver(tmp_path)
    record = _doc_record()
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [record.to_dict()])
    resolver.write_path("extracted", f"{record.document_id}.txt").write_text(FIXTURE_TEXT, encoding="utf-8")

    segmenter.segment_corpus({}, resolver=resolver)

    index_rows = read_jsonl(resolver.read_path("processed", "paragraphs_index.jsonl"))
    assert all("text" not in row for row in index_rows)
    assert all("text_char_count" in row for row in index_rows)


def test_segment_corpus_counts_missing_extracted_text(tmp_path):
    resolver = _resolver(tmp_path)
    record = _doc_record("md_missing")
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [record.to_dict()])
    # No extracted/md_missing.txt written.

    metrics = segmenter.segment_corpus({}, resolver=resolver)
    assert metrics["documents_missing_extracted_text"] == 1
    assert metrics["documents_segmented"] == 0


def test_segment_corpus_reports_coverage_metrics(tmp_path):
    resolver = _resolver(tmp_path)
    record = _doc_record()
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [record.to_dict()])
    resolver.write_path("extracted", f"{record.document_id}.txt").write_text(FIXTURE_TEXT, encoding="utf-8")

    metrics = segmenter.segment_corpus({}, resolver=resolver)
    assert 0.0 < metrics["section_id_coverage"] <= 1.0
    assert 0.0 < metrics["clause_path_coverage"] <= 1.0


# -- cross-reference resolution -------------------------------------------------


def test_resolve_cross_references_resolves_paragraph_locator(tmp_path):
    resolver = _resolver(tmp_path)
    record = _doc_record()
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [record.to_dict()])
    resolver.write_path("extracted", f"{record.document_id}.txt").write_text(FIXTURE_TEXT, encoding="utf-8")
    segmenter.segment_corpus({}, resolver=resolver)

    metrics = xref_module.resolve_cross_references({}, resolver=resolver)
    assert metrics["cross_reference_phrases_detected"] >= 1
    assert metrics["cross_reference_count"] >= 1

    rows = read_jsonl(resolver.read_path("processed", f"{record.document_id}.jsonl"))
    paragraph_4 = next(r for r in rows if r["section_id"] == "4" and r["clause_id"] is None)
    assert paragraph_4["cross_reference_ids"]
    target_id = paragraph_4["cross_reference_ids"][0]
    target = next(r for r in rows if r["paragraph_id"] == target_id)
    assert target["section_id"] == "3"


def test_resolve_cross_references_never_fabricates_unresolved_targets(tmp_path):
    """A detected phrase with no matching in-document locator resolves to nothing,
    never a guessed paragraph_id."""
    resolver = _resolver(tmp_path)
    record = _doc_record()
    text = "1. Somewhat\n(1) As specified in the Banking Regulation Act, banks shall comply.\n"
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [record.to_dict()])
    resolver.write_path("extracted", f"{record.document_id}.txt").write_text(text, encoding="utf-8")
    segmenter.segment_corpus({}, resolver=resolver)

    xref_module.resolve_cross_references({}, resolver=resolver)

    rows = read_jsonl(resolver.read_path("processed", f"{record.document_id}.jsonl"))
    assert all(r["cross_reference_ids"] == [] for r in rows)


def test_resolve_cross_references_is_intra_document_only(tmp_path):
    """A reference naming a locator that only exists in a DIFFERENT document's
    index must not resolve across documents."""
    resolver = _resolver(tmp_path)
    doc_a = _doc_record("md_a")
    doc_b = _doc_record("md_b")
    write_jsonl(
        resolver.write_path("metadata", "document_manifest.jsonl"), [doc_a.to_dict(), doc_b.to_dict()]
    )
    resolver.write_path("extracted", "md_a.txt").write_text(
        "9. Something\n(1) As specified in paragraph 9, this applies.\n", encoding="utf-8"
    )
    resolver.write_path("extracted", "md_b.txt").write_text(
        "1. Other\n(1) Unrelated content with no matching number nine here.\n", encoding="utf-8"
    )
    segmenter.segment_corpus({}, resolver=resolver)
    xref_module.resolve_cross_references({}, resolver=resolver)

    rows_b = read_jsonl(resolver.read_path("processed", "md_b.jsonl"))
    assert all(r["cross_reference_ids"] == [] for r in rows_b)


def test_locator_index_prefers_first_paragraph_for_a_repeated_section_id(tmp_path):
    from src.preprocessing.cross_references import _build_locator_index

    paragraphs = [
        ParagraphRecord(paragraph_id="d::p00000", document_id="d", section_id="5", position=0, text="first"),
        ParagraphRecord(paragraph_id="d::p00001", document_id="d", section_id="5", position=1, text="second"),
    ]
    index = _build_locator_index(paragraphs)
    assert index["5"] == "d::p00000"
