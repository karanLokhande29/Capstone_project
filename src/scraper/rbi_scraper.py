"""RBI Master Directions scraper — discovery + cached download with rate limiting."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.utils import load_config, resolve_path, setup_logging

UPDATED_AS_ON_RE = re.compile(
    r"\(Updated as on\s+([^)]+)\)", re.IGNORECASE
)
# Titles like: Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025
# Split ONLY on en/em dash so "Co-operative" ASCII hyphens stay inside the entity name.
ENTITY_SUBJECT_RE = re.compile(
    r"Reserve Bank of India\s*\(([^–—]+)[–—]\s*([^)]+)\)\s*(?:Directions|Guidelines)",
    re.IGNORECASE,
)
ENTITY_ONLY_RE = re.compile(
    r"Reserve Bank of India\s*\(([^)]+)\)\s*(?:Directions|Guidelines)",
    re.IGNORECASE,
)

KNOWN_ENTITY_PREFIXES = [
    "Non-Bank Prepaid Payment Instruments Issuers",
    "All India Financial Institutions",
    "Non-Banking Financial Companies",
    "Asset Reconstruction Companies",
    "Credit Information Companies",
    "Urban Co-operative Banks",
    "Rural Co-operative Banks",
    "Regional Rural Banks",
    "Small Finance Banks",
    "Commercial Banks",
    "Payments Banks",
    "Local Area Banks",
    "Universal Banks",
]


@dataclass
class DiscoveredDocument:
    document_id: str
    source_url: str
    title: str
    format: str  # HTML | PDF
    entity_class_raw: str
    subject_family_raw: str
    category_heading: str
    update_date_stamp: str | None = None
    pdf_url: str | None = None
    html_url: str | None = None
    listing_date: str | None = None


@dataclass
class ManifestRow:
    document_id: str
    source_url: str
    title: str
    format: str
    download_status: str
    timestamp: str
    local_path: str | None
    content_hash: str | None
    entity_class_raw: str = ""
    subject_family_raw: str = ""
    category_heading: str = ""
    failure_reason: str | None = None
    extraction_source: str = "rbi_master_directions"
    label_role: str = "primary_corpus"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_id_from_url(url: str, title: str = "") -> str:
    """Deterministic id from RBI query id or content hash of URL+title."""
    m = re.search(r"[?&]id=(\d+)", url, re.IGNORECASE)
    if m:
        return f"md_{m.group(1)}"
    m2 = re.search(r"/([A-F0-9]{20,})\.PDF", url, re.IGNORECASE)
    if m2:
        return f"pdf_{m2.group(1)[:24]}"
    digest = hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()[:16]
    return f"doc_{digest}"


def parse_entity_and_subject(title: str, category_heading: str) -> tuple[str, str]:
    """Extract raw entity class and subject family from title / category."""
    m = ENTITY_SUBJECT_RE.search(title)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    m2 = ENTITY_ONLY_RE.search(title)
    if m2:
        inside = m2.group(1).strip()
        for ent in sorted(KNOWN_ENTITY_PREFIXES, key=len, reverse=True):
            if inside.lower().startswith(ent.lower()):
                rest = inside[len(ent) :].strip(" –—-")
                return ent, rest or inside
        for sep in ("–", "—"):
            if sep in inside:
                left, right = inside.split(sep, 1)
                return left.strip(), right.strip()

    entity = category_heading.strip() if category_heading else ""
    subject = title
    for prefix in (
        "Reserve Bank of India",
        "Master Direction –",
        "Master Direction -",
        "Master Directions on",
        "Master Direction",
    ):
        if subject.lower().startswith(prefix.lower()):
            subject = subject[len(prefix) :].strip(" –-")
    subject = UPDATED_AS_ON_RE.sub("", subject).strip()
    subject = re.sub(r"\s*Directions?,?\s*\d{4}.*$", "", subject, flags=re.I).strip()
    subject = re.sub(r"\s*Guidelines?,?\s*\d{4}.*$", "", subject, flags=re.I).strip()
    if entity and subject.lower().startswith(entity.lower()):
        subject = subject[len(entity) :].strip(" –-")
    return entity or "UNKNOWN", subject or title


def extract_update_stamp(title: str) -> str | None:
    m = UPDATED_AS_ON_RE.search(title)
    return m.group(1).strip() if m else None


class RBIScraper:
    """Discover and download RBI Master Directions with caching and rate limits."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.cfg = config or load_config()
        self.logger = setup_logging("scraper.rbi", self.cfg)
        self.session = session or requests.Session()
        self.sleeper = sleeper or time.sleep
        rbi = self.cfg["rbi"]
        self.base_url = rbi["base_url"].rstrip("/")
        self.listing_url = rbi["master_directions_url"]
        self.timeout = float(rbi.get("request_timeout_sec", 60))
        self.rate_limit = float(rbi.get("rate_limit_sec", 1.5))
        self.max_retries = int(rbi.get("max_retries", 4))
        self.backoff = float(rbi.get("backoff_factor", 2.0))
        self.session.headers.update(
            {
                "User-Agent": rbi.get(
                    "user_agent",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ),
                "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": self.base_url + "/",
            }
        )
        self.raw_root = resolve_path(self.cfg, "raw")
        self.meta_root = resolve_path(self.cfg, "metadata")
        self.md_dir = self.raw_root / self.cfg["scraper"]["master_directions_subdir"]
        self.md_dir.mkdir(parents=True, exist_ok=True)
        self._last_request_ts = 0.0
        self.manifest: list[ManifestRow] = []

    def _rate_limit_wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < self.rate_limit:
            self.sleeper(self.rate_limit - elapsed)

    def fetch(self, url: str) -> requests.Response:
        """GET with polite rate-limit and exponential backoff."""
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._rate_limit_wait()
            try:
                self.logger.info("GET attempt=%s url=%s", attempt, url)
                resp = self.session.get(url, timeout=self.timeout)
                self._last_request_ts = time.monotonic()
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"retryable status {resp.status_code}", response=resp)
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001 — log and retry
                last_exc = exc
                wait = self.backoff ** attempt
                self.logger.warning("Request failed (%s); backoff %.1fs", exc, wait)
                self.sleeper(wait)
        raise RuntimeError(f"Failed to fetch {url} after {self.max_retries} retries: {last_exc}")

    def discover_listing(self, html: str | None = None) -> list[DiscoveredDocument]:
        """Parse Master Directions listing; discover actual document count (no hard-code)."""
        if html is None:
            resp = self.fetch(self.listing_url)
            # Cache listing page
            listing_path = self.md_dir / "_listing_BS_ViewMasDirections.html"
            listing_path.write_bytes(resp.content)
            html = resp.text
            self.logger.info("Cached listing page -> %s", listing_path)

        soup = BeautifulSoup(html, "lxml")
        docs: list[DiscoveredDocument] = []
        seen_ids: set[str] = set()
        current_category = "UNCATEGORIZED"
        current_date: str | None = None

        # Walk table rows in document order
        for tr in soup.find_all("tr"):
            header_td = tr.find("td", class_="tableheader")
            if header_td:
                text = header_td.get_text(" ", strip=True)
                # Date rows are short / look like "Nov 28, 2025"
                if re.match(
                    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}$",
                    text,
                ):
                    current_date = text
                elif text and not re.match(r"^\d+\s*kb$", text, re.I):
                    current_category = text
                continue

            link = tr.find("a", class_="link2")
            if not link:
                continue
            title = link.get_text(" ", strip=True)
            href = link.get("href") or ""
            html_url = urljoin(self.base_url + "/Scripts/", href)
            pdf_url = None
            for a in tr.find_all("a"):
                h = a.get("href") or ""
                if ".pdf" in h.lower() or "rbidocs.rbi.org.in" in h.lower():
                    pdf_url = h.strip("'\"")
                    if pdf_url.startswith("//"):
                        pdf_url = "https:" + pdf_url
                    break

            prefer = (self.cfg.get("rbi") or {}).get("prefer_format", "pdf").lower()
            if prefer == "pdf" and pdf_url:
                source_url, fmt = pdf_url, "PDF"
            else:
                source_url, fmt = html_url, "HTML"
                if pdf_url:
                    # still record pdf
                    pass

            entity, subject = parse_entity_and_subject(title, current_category)
            doc_id = _stable_id_from_url(html_url or source_url, title)
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            docs.append(
                DiscoveredDocument(
                    document_id=doc_id,
                    source_url=source_url,
                    title=title,
                    format=fmt,
                    entity_class_raw=entity,
                    subject_family_raw=subject,
                    category_heading=current_category,
                    update_date_stamp=extract_update_stamp(title),
                    pdf_url=pdf_url,
                    html_url=html_url,
                    listing_date=current_date,
                )
            )

        self.logger.info("Discovered %s Master Direction entries from listing", len(docs))
        return docs

    def _cache_path(self, doc: DiscoveredDocument) -> Path:
        ext = ".pdf" if doc.format.upper() == "PDF" else ".html"
        return self.md_dir / f"{doc.document_id}{ext}"

    def _is_valid_cached_file(self, path: Path, fmt: str) -> bool:
        if not path.exists() or path.stat().st_size < 100:
            return False
        head = path.read_bytes()[:16]
        if fmt.upper() == "PDF":
            return head.startswith(b"%PDF")
        # HTML should not be a bot-challenge only page if we rely on it; accept DOCTYPE/html
        return b"<html" in head.lower() or b"<!doctype" in head.lower()

    def download_document(self, doc: DiscoveredDocument) -> ManifestRow:
        """Download one document if not already cached; return manifest row."""
        path = self._cache_path(doc)
        ts = _utc_now()
        if (
            self._is_valid_cached_file(path, doc.format)
            and self.cfg["scraper"].get("resumable", True)
        ):
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            self.logger.info("CACHE HIT %s -> %s", doc.document_id, path)
            return ManifestRow(
                document_id=doc.document_id,
                source_url=doc.source_url,
                title=doc.title,
                format=doc.format,
                download_status="cached",
                timestamp=ts,
                local_path=str(path),
                content_hash=digest,
                entity_class_raw=doc.entity_class_raw,
                subject_family_raw=doc.subject_family_raw,
                category_heading=doc.category_heading,
            )
        # Invalidate false-positive caches (e.g., bot-challenge HTML saved as .pdf)
        if path.exists() and not self._is_valid_cached_file(path, doc.format):
            self.logger.warning(
                "Invalid cached file for %s (not a real %s); re-downloading",
                doc.document_id,
                doc.format,
            )
            path.unlink(missing_ok=True)

        try:
            resp = self.fetch(doc.source_url)
            content = resp.content
            if doc.format.upper() == "PDF" and not content.startswith(b"%PDF"):
                ctype = (resp.headers.get("Content-Type") or "").lower()
                raise RuntimeError(
                    f"Expected PDF magic bytes, got content-type={ctype!r} "
                    f"head={content[:40]!r}"
                )
            path.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            self.logger.info("DOWNLOADED %s bytes=%s -> %s", doc.document_id, len(content), path)
            return ManifestRow(
                document_id=doc.document_id,
                source_url=doc.source_url,
                title=doc.title,
                format=doc.format,
                download_status="success",
                timestamp=ts,
                local_path=str(path),
                content_hash=digest,
                entity_class_raw=doc.entity_class_raw,
                subject_family_raw=doc.subject_family_raw,
                category_heading=doc.category_heading,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error("DOWNLOAD FAILED %s: %s", doc.document_id, exc)
            return ManifestRow(
                document_id=doc.document_id,
                source_url=doc.source_url,
                title=doc.title,
                format=doc.format,
                download_status="failed",
                timestamp=ts,
                local_path=None,
                content_hash=None,
                entity_class_raw=doc.entity_class_raw,
                subject_family_raw=doc.subject_family_raw,
                category_heading=doc.category_heading,
                failure_reason=str(exc),
            )

    def run(
        self,
        limit: int | None = None,
        html: str | None = None,
    ) -> dict[str, Any]:
        """Discover + download; write manifest and return metrics dict."""
        docs = self.discover_listing(html=html)
        # Persist discovery catalog (always, even before downloads)
        catalog_path = self.meta_root / "discovered_documents.json"
        catalog_path.write_text(
            json.dumps([asdict(d) for d in docs], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        download_limit = limit
        if download_limit is None:
            download_limit = self.cfg["scraper"].get("pilot_download_limit")

        to_download = docs if download_limit is None else docs[: int(download_limit)]
        self.manifest = []
        for doc in to_download:
            row = self.download_document(doc)
            # Normalize local_path to absolute string for provenance
            if row.local_path is None and row.download_status in {"success", "cached"}:
                row.local_path = str(self._cache_path(doc))
            elif row.local_path and not Path(row.local_path).is_absolute():
                row.local_path = str(self._cache_path(doc))
            self.manifest.append(row)

        manifest_path = self.meta_root / "scrape_manifest.json"
        manifest_path.write_text(
            json.dumps([asdict(r) for r in self.manifest], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Also CSV-friendly copy
        try:
            import pandas as pd

            pd.DataFrame([asdict(r) for r in self.manifest]).to_csv(
                self.meta_root / "scrape_manifest.csv", index=False
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not write CSV manifest: %s", exc)

        return self.compute_metrics(docs_discovered=docs)

    def compute_metrics(self, docs_discovered: list[DiscoveredDocument]) -> dict[str, Any]:
        attempted = len(self.manifest)
        successful = sum(1 for r in self.manifest if r.download_status in {"success", "cached"})
        failed = [r for r in self.manifest if r.download_status == "failed"]
        pdf_count = sum(1 for r in self.manifest if r.format.upper() == "PDF")
        html_count = sum(1 for r in self.manifest if r.format.upper() == "HTML")
        # Duplicate discovery by title
        titles = [d.title for d in docs_discovered]
        duplicate_count = len(titles) - len(set(titles))

        openable = 0
        for r in self.manifest:
            if r.local_path and Path(r.local_path).exists() and Path(r.local_path).stat().st_size > 0:
                openable += 1

        return {
            "documents_discovered": len(docs_discovered),
            "urls_discovered": len({d.source_url for d in docs_discovered}),
            "downloads_attempted": attempted,
            "downloads_successful": successful,
            "downloads_failed": len(failed),
            "download_failure_reasons": [
                {"document_id": r.document_id, "reason": r.failure_reason} for r in failed
            ],
            "pdf_count": pdf_count,
            "html_count": html_count,
            "duplicate_count": duplicate_count,
            "extraction_readiness_openable": openable,
            "distinct_entity_classes_raw": len(
                {d.entity_class_raw for d in docs_discovered if d.entity_class_raw}
            ),
            "distinct_subject_families_raw": len(
                {d.subject_family_raw for d in docs_discovered if d.subject_family_raw}
            ),
            "manifest_path": str(self.meta_root / "scrape_manifest.json"),
            "catalog_path": str(self.meta_root / "discovered_documents.json"),
        }


def build_matrix_v0(
    docs: list[DiscoveredDocument] | None = None,
    catalog_path: Path | None = None,
    out_path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> Path:
    """Build rough Subject × Entity-Class Matrix v0 from site structure / titles."""
    cfg = config or load_config()
    if docs is None:
        catalog_path = catalog_path or (resolve_path(cfg, "metadata") / "discovered_documents.json")
        raw = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        docs = [DiscoveredDocument(**{k: v for k, v in row.items() if k in DiscoveredDocument.__dataclass_fields__}) for row in raw]

    rows = []
    for d in docs:
        rows.append(
            {
                "entity_class": d.entity_class_raw,
                "subject_family_raw": d.subject_family_raw,
                "document_id": d.document_id,
                "source_url": d.source_url,
                "title": d.title,
                "category_heading": d.category_heading,
            }
        )
    import pandas as pd

    out = Path(out_path) if out_path else (resolve_path(cfg, "matrix") / "matrix_v0.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out
