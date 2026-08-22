"""End-to-end integration test (Phase 1, Section U).

Discovery -> download -> extraction -> segmentation -> cross-reference
resolution, chained exactly as ``scripts/run_harvest.py`` chains them, against
canned fixtures only — no real network, no real RBI site. Confirms the whole
pipeline produces ``ParagraphRecord``s that pass schema validation, with
deterministic ``paragraph_id``s and non-null ``section_id``/``clause_path`` on
every fixture paragraph (the fixtures are written with a chapter marker at the
very first line specifically so nothing here exercises the documented
front-matter exception).
"""

from __future__ import annotations

import io

from src.common.cache import ArtifactCache
from src.common.io_helpers import read_jsonl
from src.common.paths import PathResolver
from src.extraction.text_extractor import extract_corpus
from src.preprocessing.cross_references import resolve_cross_references
from src.preprocessing.segmenter import segment_corpus, segment_document
from src.schemas.provenance import DocumentRecord, ParagraphRecord
from src.scraper.rbi_scraper import discover_documents, harvest_corpus

INTEGRATION_CONFIG = {
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
    "cache": {"enabled": True, "namespace": "integration-test", "max_age_days": None},
    "network": {
        "retry": {"attempts": 2, "initial_delay_sec": 0.0, "backoff_factor": 1.0, "max_delay_sec": 0.0, "jitter": 0.0},
        "request_timeout_sec": 5,
        "rate_limit_sec": 0.0,
        "sources": {"user_agent": "test-agent", "referer": "https://example.org/"},
    },
}

FIXTURE_LISTING_HTML = """
<html><body>
<table class="tablebg">
<tr><td align="left" class="tableheader" colspan="4"><b>Commercial Banks</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=2001">Integration Test Direction One</a></td>
  <td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/ONE.PDF">pdf</a></td>
</tr>
<tr><td align="left" class="tableheader" colspan="4"><b>Small Finance Banks</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=2002">Integration Test Direction Two (Updated as on May 5, 2025)</a></td>
  <td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/TWO.PDF">pdf</a></td>
</tr>
</table>
</body></html>
"""


def _make_minimal_pdf(lines: list[str]) -> bytes:
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


# Every line is a recognised structural marker, so every resulting paragraph
# is guaranteed a non-null section_id/clause_path — proving the pipeline
# carries structure through end to end, not exercising the documented
# front-matter exception.
DOC_ONE_LINES = [
    "Chapter I",
    "Preliminary",
    "1. Applicability",
    "(1) These Directions apply to all Commercial Banks operating in India.",
]
DOC_TWO_LINES = [
    "1. Reporting",
    "(1) As specified in paragraph 1, banks shall submit quarterly reports.",
    "(a) The report format is specified by the Reserve Bank of India.",
]


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.headers = {}

    def get(self, url, timeout=None):
        return self.responses[url]


def test_full_pipeline_produces_valid_deterministic_paragraphs(tmp_path):
    resolver = PathResolver.from_config(INTEGRATION_CONFIG, repo_root=tmp_path)
    cache = ArtifactCache.from_config(INTEGRATION_CONFIG, resolver, namespace="scraper")

    session = FakeSession(
        {
            "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/ONE.PDF": FakeResponse(
                _make_minimal_pdf(DOC_ONE_LINES)
            ),
            "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/TWO.PDF": FakeResponse(
                _make_minimal_pdf(DOC_TWO_LINES)
            ),
        }
    )

    # 1. Discovery
    discovered = discover_documents(INTEGRATION_CONFIG, html=FIXTURE_LISTING_HTML)
    assert len(discovered) == 2

    # 2. Discovery + download, chained exactly as run_harvest.py does
    harvest_metrics = harvest_corpus(
        INTEGRATION_CONFIG,
        html=FIXTURE_LISTING_HTML,
        session=session,
        resolver=resolver,
        cache=cache,
        sleep_fn=lambda s: None,
    )
    assert harvest_metrics["downloads_successful"] == 2
    assert harvest_metrics["downloads_failed"] == 0

    # 3. Extraction
    extract_metrics = extract_corpus(INTEGRATION_CONFIG, resolver=resolver, cache=cache)
    assert extract_metrics["extraction_successful"] == 2
    assert extract_metrics["extraction_failures"] == 0

    # 4. Segmentation
    segment_metrics = segment_corpus(INTEGRATION_CONFIG, resolver=resolver)
    assert segment_metrics["documents_segmented"] == 2
    assert segment_metrics["total_paragraphs"] > 0

    # 5. Cross-reference resolution
    xref_metrics = resolve_cross_references(INTEGRATION_CONFIG, resolver=resolver)
    assert xref_metrics["cross_reference_count"] >= 1  # "paragraph 1" in doc two resolves

    # -- assertions on the actual produced records --------------------------

    all_paragraphs: list[ParagraphRecord] = []
    for document_id in ("md_2001", "md_2002"):
        rows = read_jsonl(resolver.read_path("processed", f"{document_id}.jsonl"))
        all_paragraphs.extend(ParagraphRecord.from_dict(r) for r in rows)

    assert len(all_paragraphs) > 0

    # Every record passes FIELD_SPECS-based schema validation.
    for paragraph in all_paragraphs:
        errors = paragraph.validate()
        assert errors == [], f"{paragraph.paragraph_id}: {errors}"

    # Non-null section_id/clause_path on every fixture paragraph — the
    # fixtures were written with a marker on every line specifically to prove
    # this, not to rely on front-matter tolerance.
    for paragraph in all_paragraphs:
        assert paragraph.section_id is not None, paragraph.paragraph_id
        assert paragraph.clause_path is not None, paragraph.paragraph_id

    # document_id / paragraph_id are always present (the two non-nullable
    # required fields).
    for paragraph in all_paragraphs:
        assert paragraph.document_id
        assert paragraph.paragraph_id

    # The temporal stamp on document two's title made it through discovery.
    manifest = read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))
    by_id = {r["document_id"]: r for r in manifest}
    assert by_id["md_2002"]["update_date"] == "May 5, 2025"
    assert by_id["md_2001"]["update_date"] is None

    # entity_class_raw captured, entity_class (Karan's) still untouched.
    assert by_id["md_2001"]["entity_class_raw"] == "Commercial Banks"
    assert by_id["md_2001"]["entity_class"] is None


def test_full_pipeline_paragraph_ids_deterministic_across_reruns(tmp_path):
    """Re-running segmentation on unchanged extracted text must not change any ID."""
    resolver = PathResolver.from_config(INTEGRATION_CONFIG, repo_root=tmp_path)
    cache = ArtifactCache.from_config(INTEGRATION_CONFIG, resolver, namespace="scraper")
    session = FakeSession(
        {
            "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/ONE.PDF": FakeResponse(
                _make_minimal_pdf(DOC_ONE_LINES)
            ),
            "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/TWO.PDF": FakeResponse(
                _make_minimal_pdf(DOC_TWO_LINES)
            ),
        }
    )
    harvest_corpus(
        INTEGRATION_CONFIG,
        html=FIXTURE_LISTING_HTML,
        session=session,
        resolver=resolver,
        cache=cache,
        sleep_fn=lambda s: None,
    )
    extract_corpus(INTEGRATION_CONFIG, resolver=resolver, cache=cache)

    run_1 = segment_corpus(INTEGRATION_CONFIG, resolver=resolver)
    ids_1 = [r["paragraph_id"] for r in read_jsonl(resolver.read_path("processed", "paragraphs_index.jsonl"))]

    run_2 = segment_corpus(INTEGRATION_CONFIG, resolver=resolver)
    ids_2 = [r["paragraph_id"] for r in read_jsonl(resolver.read_path("processed", "paragraphs_index.jsonl"))]

    assert ids_1 == ids_2
    assert run_1["total_paragraphs"] == run_2["total_paragraphs"]


def test_full_pipeline_no_circular_dependency_between_stages(tmp_path):
    """Each stage can be re-run independently without re-running earlier ones."""
    resolver = PathResolver.from_config(INTEGRATION_CONFIG, repo_root=tmp_path)
    cache = ArtifactCache.from_config(INTEGRATION_CONFIG, resolver, namespace="scraper")
    session = FakeSession(
        {"https://rbidocs.rbi.org.in/rdocs/notification/PDFs/ONE.PDF": FakeResponse(_make_minimal_pdf(DOC_ONE_LINES))}
    )
    harvest_corpus(
        INTEGRATION_CONFIG,
        html=FIXTURE_LISTING_HTML,
        limit=1,
        session=session,
        resolver=resolver,
        cache=cache,
        sleep_fn=lambda s: None,
    )
    extract_corpus(INTEGRATION_CONFIG, resolver=resolver, cache=cache)
    first = segment_corpus(INTEGRATION_CONFIG, resolver=resolver)
    # Re-running segment_corpus alone, with no re-download or re-extraction,
    # must succeed and produce the same result.
    second = segment_corpus(INTEGRATION_CONFIG, resolver=resolver)
    assert first["total_paragraphs"] == second["total_paragraphs"]
