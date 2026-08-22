"""Scraper unit tests using mocked HTML — no live network."""

from pathlib import Path

from src.scraper.rbi_scraper import (
    RBIScraper,
    build_matrix_v0,
    parse_entity_and_subject,
    extract_update_stamp,
    _stable_id_from_url,
)


SAMPLE_LISTING = """
<html><body><table>
<tr><td class="tableheader" colspan="4"><b>Commercial Banks</b></td></tr>
<tr><td class="tableheader" colspan="4"><b>Nov 28, 2025</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=99901">
    Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025
    (Updated as on December 29, 2025)</a></td>
  <td><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/ABCDEF1234567890ABCDEF1234.PDF">PDF</a></td>
</tr>
<tr><td class="tableheader" colspan="4"><b>Small Finance Banks</b></td></tr>
<tr>
  <td><a class="link2" href="BS_ViewMasDirections.aspx?id=99902">
    Reserve Bank of India (Small Finance Banks – Know Your Customer) Directions, 2025</a></td>
  <td><a href="https://rbidocs.rbi.org.in/rdocs/notification/PDFs/FEDCBA0987654321FEDCBA0987.PDF">PDF</a></td>
</tr>
</table></body></html>
"""


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.text = content.decode("utf-8", errors="replace")
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, mapping: dict[str, bytes]):
        self.mapping = mapping
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=60):
        self.calls.append(url)
        if url not in self.mapping:
            # prefix match for PDF
            for k, v in self.mapping.items():
                if url.startswith(k) or k in url:
                    return FakeResponse(v)
            raise RuntimeError(f"unexpected URL {url}")
        return FakeResponse(self.mapping[url])


def test_parse_entity_and_subject():
    e, s = parse_entity_and_subject(
        "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025",
        "Commercial Banks",
    )
    assert e == "Commercial Banks"
    assert "Know Your Customer" in s


def test_parse_entity_keeps_cooperative_hyphen():
    e, s = parse_entity_and_subject(
        "Reserve Bank of India (Urban Co-operative Banks – Know Your Customer) Directions, 2025",
        "Urban Co-operative Banks",
    )
    assert e == "Urban Co-operative Banks"
    assert s.startswith("Know Your Customer")


def test_extract_update_stamp():
    assert "December 29, 2025" in (
        extract_update_stamp("Title (Updated as on December 29, 2025)") or ""
    )


def test_stable_id_from_url():
    assert _stable_id_from_url("https://www.rbi.org.in/Scripts/x.aspx?id=12345") == "md_12345"


def test_discover_listing_mocked(tmp_path, monkeypatch):
    # Point config paths at tmp
    cfg = {
        "paths": {
            "raw": str(tmp_path / "raw"),
            "extracted": str(tmp_path / "extracted"),
            "processed": str(tmp_path / "processed"),
            "metadata": str(tmp_path / "metadata"),
            "matrix": str(tmp_path / "matrix"),
            "benchmark_candidate": str(tmp_path / "cand"),
            "benchmark_validated": str(tmp_path / "val"),
            "reports": str(tmp_path / "reports"),
            "logs": str(tmp_path / "logs"),
        },
        "rbi": {
            "base_url": "https://www.rbi.org.in",
            "master_directions_url": "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx",
            "user_agent": "test",
            "request_timeout_sec": 5,
            "rate_limit_sec": 0,
            "max_retries": 1,
            "backoff_factor": 1,
            "prefer_format": "pdf",
        },
        "scraper": {
            "resumable": True,
            "pilot_download_limit": None,
            "master_directions_subdir": "master_directions",
            "faq_subdir": "faq",
            "amendments_subdir": "amendments",
            "circulars_withdrawn_subdir": "circulars_withdrawn",
            "enforcement_subdir": "enforcement",
        },
        "logging": {"level": "INFO"},
    }
    pdf_bytes = b"%PDF-1.4 fake content for test"
    session = FakeSession(
        {
            "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/ABCDEF1234567890ABCDEF1234.PDF": pdf_bytes,
            "https://rbidocs.rbi.org.in/rdocs/notification/PDFs/FEDCBA0987654321FEDCBA0987.PDF": pdf_bytes,
            "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=99901": b"<html>detail1</html>",
            "https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=99902": b"<html>detail2</html>",
        }
    )
    scraper = RBIScraper(config=cfg, session=session, sleeper=lambda _s: None)
    docs = scraper.discover_listing(html=SAMPLE_LISTING)
    assert len(docs) == 2
    assert docs[0].document_id == "md_99901"
    metrics = scraper.run(html=SAMPLE_LISTING)
    assert metrics["documents_discovered"] == 2
    assert metrics["downloads_successful"] == 2
    assert metrics["downloads_failed"] == 0
    out = build_matrix_v0(docs=docs, out_path=tmp_path / "matrix" / "matrix_v0.csv", config=cfg)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "Commercial Banks" in text
    assert "Know Your Customer" in text
