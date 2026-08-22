"""Tests for src.extraction.text_extractor and src.extraction.temporal_signals.

PDF fixtures are built at runtime by `_make_minimal_pdf` rather than committed
as binary files — nothing in this repo pulls in a PDF-generation library, and a
hand-built minimal PDF with correctly-computed xref offsets is small, exact,
and reviewable as plain code. No real network or real RBI documents involved.
"""

from __future__ import annotations

import io

import pytest

from src.common.cache import ArtifactCache
from src.common.paths import PathResolver
from src.extraction import text_extractor as extractor
from src.extraction.temporal_signals import extract_update_date_stamp
from src.schemas.provenance import DocumentRecord

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
    "cache": {"enabled": True, "namespace": "test-extraction", "max_age_days": None},
}


def _resolver_and_cache(tmp_path):
    resolver = PathResolver.from_config(MINIMAL_CONFIG, repo_root=tmp_path)
    return resolver, ArtifactCache(resolver, namespace="scraper")


def _make_minimal_pdf(lines: list[str]) -> bytes:
    """Build a minimal single-page PDF with the given text lines.

    Computes xref byte offsets at build time rather than hardcoding them, so
    the fixture stays correct if the lines change.
    """
    content_lines = []
    y = 750
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        content_lines.append(f"BT /F1 12 Tf 50 {y} Td ({escaped}) Tj ET")
        y -= 20
    content = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        b"<</Length " + str(len(content)).encode() + b">>\nstream\n" + content + b"\nendstream",
    ]

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj".encode() + b"\n" + obj + b"\nendobj\n")
    xref_offset = out.tell()
    n = len(objects) + 1
    out.write(f"xref\n0 {n}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n<</Size " + str(n).encode() + b"/Root 1 0 R>>\nstartxref\n" + str(xref_offset).encode() + b"\n%%EOF")
    return out.getvalue()


CORRUPT_PDF = b"%PDF-1.4\nthis is not a real pdf body, no valid xref\n%%EOF"


# -- temporal_signals ---------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Master Direction (Updated as on November 22, 2018)", "November 22, 2018"),
        ("Direction (Updated as on July 1, 2026)", "July 1, 2026"),
        ("No stamp here at all", None),
        (None, None),
        ("", None),
    ],
)
def test_extract_update_date_stamp(text, expected):
    assert extract_update_date_stamp(text) == expected


def test_extract_update_date_stamp_returns_last_when_multiple():
    text = "Title (Updated as on January 1, 2020) ... body (Updated as on June 5, 2021)"
    assert extract_update_date_stamp(text) == "June 5, 2021"


def test_extract_update_date_stamp_is_case_insensitive():
    assert extract_update_date_stamp("(updated AS ON March 3, 2019)") == "March 3, 2019"


# -- PDF extraction -------------------------------------------------------


def test_extract_text_reads_real_minimal_pdf(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = DocumentRecord(document_id="md_1", format="PDF")
    pdf_bytes = _make_minimal_pdf(["Master Direction Test", "Chapter I - Preliminary", "1. Short title."])
    cache.put(cache.key_for("rbi_master_directions", record.document_id), pdf_bytes, suffix=".pdf")

    text = extractor.extract_text(record, {}, cache=cache, resolver=resolver)
    assert "Master Direction Test" in text
    assert "Chapter I - Preliminary" in text
    assert "1. Short title." in text


def test_extract_text_raises_on_missing_payload(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = DocumentRecord(document_id="md_missing", format="PDF")
    with pytest.raises(extractor.ExtractionError, match="no cached payload"):
        extractor.extract_text(record, {}, cache=cache, resolver=resolver)


def test_extract_text_raises_on_corrupt_pdf(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = DocumentRecord(document_id="md_bad", format="PDF")
    cache.put(cache.key_for("rbi_master_directions", record.document_id), CORRUPT_PDF, suffix=".pdf")

    with pytest.raises(extractor.ExtractionError, match="PDF parsing failed"):
        extractor.extract_text(record, {}, cache=cache, resolver=resolver)


def test_extract_text_falls_back_to_alternate_suffix(tmp_path):
    """format says HTML but payload was actually cached as .pdf — still found."""
    resolver, cache = _resolver_and_cache(tmp_path)
    record = DocumentRecord(document_id="md_1", format="HTML")
    pdf_bytes = _make_minimal_pdf(["Fallback content"])
    cache.put(cache.key_for("rbi_master_directions", record.document_id), pdf_bytes, suffix=".pdf")

    text = extractor.extract_text(record, {}, cache=cache, resolver=resolver)
    assert "Fallback content" in text


# -- HTML extraction ------------------------------------------------------


def test_extract_text_reads_html(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = DocumentRecord(document_id="md_html", format="HTML")
    html = b"<html><body><h1>Title</h1><p>Body paragraph text.</p></body></html>"
    cache.put(cache.key_for("rbi_master_directions", record.document_id), html, suffix=".html")

    text = extractor.extract_text(record, {}, cache=cache, resolver=resolver)
    assert "Title" in text
    assert "Body paragraph text." in text


# -- extract_corpus -----------------------------------------------------------


def test_extract_corpus_processes_manifest_and_writes_files(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)

    records = [
        DocumentRecord(document_id="md_1", format="PDF", content_hash="abc"),
        DocumentRecord(document_id="md_2", format="PDF", content_hash="def"),
    ]
    from src.common.io_helpers import write_jsonl

    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [r.to_dict() for r in records])

    for record in records:
        pdf_bytes = _make_minimal_pdf([f"Document {record.document_id} content here, long enough to count."])
        cache.put(cache.key_for("rbi_master_directions", record.document_id), pdf_bytes, suffix=".pdf")

    metrics = extractor.extract_corpus({}, resolver=resolver, cache=cache)

    assert metrics["documents_considered"] == 2
    assert metrics["extraction_successful"] == 2
    assert metrics["extraction_failures"] == 0
    assert resolver.read_path("extracted", "md_1.txt").exists()
    assert resolver.read_path("extracted", "md_2.txt").exists()


def test_extract_corpus_skips_documents_never_downloaded(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    from src.common.io_helpers import write_jsonl

    # No content_hash => never successfully downloaded.
    records = [DocumentRecord(document_id="md_never", format="PDF", content_hash=None)]
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [r.to_dict() for r in records])

    metrics = extractor.extract_corpus({}, resolver=resolver, cache=cache)
    assert metrics["skipped_not_downloaded"] == 1
    assert metrics["documents_considered"] == 0


def test_extract_corpus_counts_failures_and_continues(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    from src.common.io_helpers import write_jsonl

    records = [
        DocumentRecord(document_id="md_good", format="PDF", content_hash="x"),
        DocumentRecord(document_id="md_bad", format="PDF", content_hash="y"),
    ]
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [r.to_dict() for r in records])

    cache.put(
        cache.key_for("rbi_master_directions", "md_good"),
        _make_minimal_pdf(["Good document with enough real text content."]),
        suffix=".pdf",
    )
    cache.put(cache.key_for("rbi_master_directions", "md_bad"), CORRUPT_PDF, suffix=".pdf")

    metrics = extractor.extract_corpus({}, resolver=resolver, cache=cache)
    assert metrics["extraction_successful"] == 1
    assert metrics["extraction_failures"] == 1
    assert metrics["failures"][0]["document_id"] == "md_bad"


def test_extract_corpus_counts_empty_extraction_separately(tmp_path):
    """A parsed-but-blank PDF (e.g. scanned/image-only) is 'empty', not a failure."""
    resolver, cache = _resolver_and_cache(tmp_path)
    from src.common.io_helpers import write_jsonl

    records = [DocumentRecord(document_id="md_blank", format="PDF", content_hash="z")]
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), [r.to_dict() for r in records])
    cache.put(cache.key_for("rbi_master_directions", "md_blank"), _make_minimal_pdf([]), suffix=".pdf")

    metrics = extractor.extract_corpus({}, resolver=resolver, cache=cache)
    assert metrics["extraction_empty"] == 1
    assert metrics["extraction_failures"] == 0
    assert not resolver.find_read_path("extracted", "md_blank.txt")
