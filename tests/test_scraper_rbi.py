"""Tests for src.scraper.rbi_scraper.

No real network calls: discovery is tested against a fixture HTML page that
mirrors the actual structure of ``BS_ViewMasDirections.aspx`` (verified against
the live site while building the scraper — see the module docstring), and
downloads are tested against a mocked session.
"""

from __future__ import annotations

import hashlib

import pytest
import requests

from src.common.cache import ArtifactCache
from src.common.errors import RetryExhaustedError
from src.common.paths import PathResolver
from src.schemas.provenance import DocumentRecord
from src.scraper import rbi_scraper as scraper

# A compact fixture mirroring the real listing's structure: category heading,
# date sub-heading, document rows — including one entity-class heading that
# repeats (as genuinely happens on the live page, with no distinguishing
# marker) and one title carrying an "(Updated as on ...)" stamp.
FIXTURE_LISTING_HTML = """
<html><body>
<table class="tablebg">
<tr><td align="left" class="tableheader" colspan="4"><b>Commercial Banks</b></td></tr>
<tr><td align="left" class="tableheader" colspan="4"><b>Jul 03, 2018</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=1001">Master Direction on KYC</a></td>
  <td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/AAA.PDF">pdf</a></td>
</tr>
<tr><td align="left" class="tableheader" colspan="4"><b>Nov 22, 2018</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=1002">Master Direction on Loans (Updated as on November 22, 2018)</a></td>
  <td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/BBB.PDF">pdf</a></td>
</tr>
<tr><td align="left" class="tableheader" colspan="4"><b>Small Finance Banks</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=1003">Master Direction on Capital</a></td>
  <td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/CCC.PDF">pdf</a></td>
</tr>
<tr><td align="left" class="tableheader" colspan="4"><b>Payments Banks</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=1004">Master Direction on Settlement</a></td>
  <td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/DDD.PDF">pdf</a></td>
</tr>
<tr><td align="left" class="tableheader" colspan="4"><b>Commercial Banks</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=1005">Master Direction on Ombudsman</a></td>
  <td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/EEE.PDF">pdf</a></td>
</tr>
</table>
</body></html>
"""

FIXTURE_LISTING_WITH_DUPLICATE_ID = FIXTURE_LISTING_HTML.replace(
    '<tr><td align="left" class="tableheader" colspan="4"><b>Payments Banks</b></td></tr>',
    '<tr><td align="left" class="tableheader" colspan="4"><b>Payments Banks</b></td></tr>\n'
    '<tr><td><a class="link2" href="BS_ViewMasDirections.aspx?id=1001">Duplicate of KYC</a></td>'
    '<td colspan="3" nowrap=""><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/DUP.PDF">pdf</a></td></tr>',
)

MINIMAL_CONFIG = {
    "network": {
        "retry": {"attempts": 2, "initial_delay_sec": 0.0, "backoff_factor": 1.0, "max_delay_sec": 0.0, "jitter": 0.0},
        "request_timeout_sec": 5,
        "rate_limit_sec": 0.0,
        "sources": {
            "user_agent": "test-agent",
            "referer": "https://example.org/",
            "rbi_master_directions": {"listing_url": "https://example.org/listing.aspx"},
        },
    },
    "cache": {"enabled": True, "namespace": "test-scraper", "max_age_days": None},
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


def _resolver_and_cache(tmp_path):
    resolver = PathResolver.from_config(MINIMAL_CONFIG, repo_root=tmp_path)
    return resolver, ArtifactCache(resolver, namespace="scraper")


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


class FakeSession:
    """A minimal stand-in for requests.Session, keyed by URL."""

    def __init__(self, responses: dict[str, FakeResponse | Exception]):
        self.responses = responses
        self.calls: list[str] = []
        self.headers: dict[str, str] = {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        result = self.responses.get(url)
        if result is None:
            raise AssertionError(f"unexpected URL requested: {url}")
        if isinstance(result, Exception):
            raise result
        return result


# -- discovery ------------------------------------------------------------


def test_parse_listing_extracts_all_documents():
    import logging

    rows = scraper._parse_listing(FIXTURE_LISTING_HTML, logger=logging.getLogger("test"))
    assert len(rows) == 5
    assert [r["document_id"] for r in rows] == ["md_1001", "md_1002", "md_1003", "md_1004", "md_1005"]


def test_parse_listing_records_entity_class_raw_exactly_as_listed():
    import logging

    rows = scraper._parse_listing(FIXTURE_LISTING_HTML, logger=logging.getLogger("test"))
    assert rows[0]["entity_class_raw"] == "Commercial Banks"
    assert rows[2]["entity_class_raw"] == "Small Finance Banks"
    assert rows[3]["entity_class_raw"] == "Payments Banks"
    assert rows[4]["entity_class_raw"] == "Commercial Banks"  # second, unmarked pass


def test_parse_listing_does_not_confuse_date_headers_with_categories():
    import logging

    rows = scraper._parse_listing(FIXTURE_LISTING_HTML, logger=logging.getLogger("test"))
    # The date sub-headings ("Jul 03, 2018" etc.) must never end up as an
    # entity_class_raw value.
    assert all(not scraper.DATE_HEADER_RE.match(r["entity_class_raw"] or "") for r in rows)


def test_parse_listing_tracks_category_pass_without_persisting_it():
    """The duplicate-heading finding is tracked for logging, not the schema."""
    import logging

    rows = scraper._parse_listing(FIXTURE_LISTING_HTML, logger=logging.getLogger("test"))
    passes = {r["document_id"]: r["category_pass"] for r in rows}
    assert passes["md_1001"] == 1  # first "Commercial Banks" block
    assert passes["md_1005"] == 2  # second "Commercial Banks" block


def test_parse_listing_deduplicates_repeated_ids():
    import logging

    rows = scraper._parse_listing(FIXTURE_LISTING_WITH_DUPLICATE_ID, logger=logging.getLogger("test"))
    ids = [r["document_id"] for r in rows]
    assert ids.count("md_1001") == 1


def test_parse_listing_raises_on_missing_table():
    import logging

    with pytest.raises(scraper.DiscoveryError):
        scraper._parse_listing("<html><body>no table here</body></html>", logger=logging.getLogger("test"))


def test_discover_documents_builds_document_records_from_fixture(base_config):
    records = scraper.discover_documents(base_config, html=FIXTURE_LISTING_HTML)
    assert len(records) == 5
    assert all(isinstance(r, DocumentRecord) for r in records)
    assert records[0].document_id == "md_1001"
    assert records[0].entity_class_raw == "Commercial Banks"


def test_discover_documents_leaves_subject_family_raw_null(base_config):
    """The listing has no subject-family axis; recording None is faithful, not a bug."""
    records = scraper.discover_documents(base_config, html=FIXTURE_LISTING_HTML)
    assert all(r.subject_family_raw is None for r in records)


def test_discover_documents_leaves_normalised_and_payload_fields_null(base_config):
    """entity_class/subject_family are Karan's; local_path/content_hash are set at download, not discovery."""
    records = scraper.discover_documents(base_config, html=FIXTURE_LISTING_HTML)
    for r in records:
        assert r.entity_class is None
        assert r.subject_family is None
        assert r.content_hash is None
        assert r.local_path is None
        assert r.retrieved_at is None


def test_discover_documents_extracts_updated_as_on_stamp_from_title(base_config):
    records = scraper.discover_documents(base_config, html=FIXTURE_LISTING_HTML)
    by_id = {r.document_id: r for r in records}
    assert by_id["md_1002"].update_date == "November 22, 2018"
    assert by_id["md_1001"].update_date is None


def test_discover_documents_sets_document_role_and_source(base_config):
    records = scraper.discover_documents(base_config, html=FIXTURE_LISTING_HTML)
    assert all(r.document_role == "primary_corpus" for r in records)
    assert all(r.extraction_source == "rbi_master_directions" for r in records)


def test_discover_documents_raises_on_zero_documents(base_config):
    """Zero discovered documents means discovery is broken, not that the corpus is small."""
    with pytest.raises(scraper.DiscoveryError):
        scraper.discover_documents(base_config, html="<html><body><table></table></body></html>")


def test_discover_documents_fetches_live_when_no_html_given():
    listing_url = MINIMAL_CONFIG["network"]["sources"]["rbi_master_directions"]["listing_url"]
    session = FakeSession({listing_url: FakeResponse(FIXTURE_LISTING_HTML.encode("utf-8"))})
    records = scraper.discover_documents(MINIMAL_CONFIG, session=session)
    assert len(records) == 5
    assert session.calls == [listing_url]


# -- payload validation -----------------------------------------------------


def test_validate_payload_accepts_real_pdf_magic():
    is_valid, fmt = scraper._validate_payload(b"%PDF-1.4 rest of file", "PDF")
    assert is_valid and fmt == "PDF"


def test_validate_payload_rejects_html_challenge_page_at_pdf_url():
    """The exact failure mode this module exists to catch."""
    challenge = b"<!doctype html><html><body>Access Denied - Imperva</body></html>"
    is_valid, reason = scraper._validate_payload(challenge, "PDF")
    assert not is_valid
    assert "WAF" in reason or "bot-challenge" in reason


def test_validate_payload_rejects_generic_html_where_pdf_expected():
    is_valid, reason = scraper._validate_payload(b"<html><body>Not found</body></html>", "PDF")
    assert not is_valid


def test_validate_payload_accepts_html_when_html_expected():
    is_valid, fmt = scraper._validate_payload(b"<!doctype html><html>content</html>", "HTML")
    assert is_valid and fmt == "HTML"


def test_validate_payload_rejects_unrecognised_bytes():
    is_valid, reason = scraper._validate_payload(b"\x00\x01\x02garbage", "PDF")
    assert not is_valid
    assert "unrecognised" in reason


# -- download -----------------------------------------------------------------


def _record(document_id="md_1001", source_url="https://rbidocs.rbi.org.in/x.PDF"):
    return DocumentRecord(document_id=document_id, source_url=source_url, format="PDF")


def test_download_document_validates_and_populates_fields(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = _record()
    session = FakeSession({record.source_url: FakeResponse(b"%PDF-1.4 real pdf content")})

    result = scraper.download_document(record, MINIMAL_CONFIG, session=session, cache=cache, resolver=resolver)

    assert result.format == "PDF"
    assert result.content_hash == hashlib.sha256(b"%PDF-1.4 real pdf content").hexdigest()
    assert result.local_path is not None
    assert result.retrieved_at is not None
    assert (resolver.working_root / result.local_path).exists()


def test_download_document_rejects_waf_challenge_and_does_not_cache(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = _record()
    challenge = b"<!doctype html>Access Denied - Imperva bot challenge"
    session = FakeSession({record.source_url: FakeResponse(challenge)})

    with pytest.raises(scraper.PayloadValidationError):
        scraper.download_document(record, MINIMAL_CONFIG, session=session, cache=cache, resolver=resolver)

    key = cache.key_for("rbi_master_directions", record.document_id)
    assert not cache.has(key, suffix=".pdf")


def test_download_document_retries_transient_failures(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = _record()

    call_count = {"n": 0}

    class FlakySession(FakeSession):
        def get(self, url, timeout=None):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise requests.exceptions.ConnectionError("blip")
            return FakeResponse(b"%PDF-1.4 ok")

    session = FlakySession({})
    result = scraper.download_document(record, MINIMAL_CONFIG, session=session, cache=cache, resolver=resolver)
    assert result.content_hash is not None
    assert call_count["n"] == 2


def test_download_document_exhausts_retries_and_raises(tmp_path):
    resolver, cache = _resolver_and_cache(tmp_path)
    record = _record()
    session = FakeSession({record.source_url: requests.exceptions.ConnectionError("down")})

    with pytest.raises(RetryExhaustedError):
        scraper.download_document(record, MINIMAL_CONFIG, session=session, cache=cache, resolver=resolver)


def test_download_document_requires_source_url(tmp_path):
    resolver, _cache = _resolver_and_cache(tmp_path)
    record = DocumentRecord(document_id="md_1", source_url=None)
    with pytest.raises(scraper.PayloadValidationError):
        scraper.download_document(record, MINIMAL_CONFIG, resolver=resolver)


# -- harvest orchestration ----------------------------------------------------


def test_harvest_corpus_continues_after_one_failure(tmp_path):
    cfg = MINIMAL_CONFIG
    resolver, cache = _resolver_and_cache(tmp_path)

    responses = {
        "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/AAA.PDF": FakeResponse(b"%PDF-1.4 ok"),
        "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/BBB.PDF": FakeResponse(b"not a pdf at all"),
        "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/CCC.PDF": FakeResponse(b"%PDF-1.4 ok too"),
        "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/DDD.PDF": FakeResponse(b"%PDF-1.4 also ok"),
        "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/EEE.PDF": FakeResponse(b"%PDF-1.4 fine"),
    }
    session = FakeSession(responses)

    metrics = scraper.harvest_corpus(
        cfg, html=FIXTURE_LISTING_HTML, session=session, resolver=resolver, cache=cache, sleep_fn=lambda s: None
    )

    assert metrics["documents_discovered"] == 5
    assert metrics["downloads_attempted"] == 5
    assert metrics["downloads_successful"] == 4
    assert metrics["downloads_failed"] == 1
    assert len(metrics["failures"]) == 1


def test_harvest_corpus_respects_limit(tmp_path):
    cfg = MINIMAL_CONFIG
    resolver, cache = _resolver_and_cache(tmp_path)
    session = FakeSession({"https://rbidocs.rbi.org.in/rdocs/notification/PDFs/AAA.PDF": FakeResponse(b"%PDF-1.4 ok")})

    metrics = scraper.harvest_corpus(
        cfg, html=FIXTURE_LISTING_HTML, limit=1, session=session, resolver=resolver, cache=cache, sleep_fn=lambda s: None
    )

    assert metrics["documents_discovered"] == 5  # discovery is never capped
    assert metrics["downloads_attempted"] == 1


def test_harvest_corpus_writes_manifest(tmp_path):
    cfg = MINIMAL_CONFIG
    resolver, cache = _resolver_and_cache(tmp_path)
    session = FakeSession({"https://rbidocs.rbi.org.in/rdocs/notification/PDFs/AAA.PDF": FakeResponse(b"%PDF-1.4 ok")})

    metrics = scraper.harvest_corpus(
        cfg, html=FIXTURE_LISTING_HTML, limit=1, session=session, resolver=resolver, cache=cache, sleep_fn=lambda s: None
    )

    from src.common.io_helpers import read_jsonl

    rows = read_jsonl(metrics["manifest_path"])
    assert len(rows) == 1
    assert rows[0]["document_id"] == "md_1001"
