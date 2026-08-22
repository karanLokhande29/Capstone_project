"""Supplementary source harvesting: FAQs, amendments, circulars withdrawn, enforcement."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.utils import load_config, resolve_path, setup_logging

# Known RBI listing entry points (structure may change — discovery still parses whatever is present)
SUPPLEMENT_SOURCES = {
    "faq": {
        "url": "https://www.rbi.org.in/Scripts/FAQView.aspx",
        "label_role": "validation/motivation source",
        "extraction_source": "rbi_faq",
    },
    "enforcement": {
        "url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
        "label_role": "validation/motivation source",
        "extraction_source": "rbi_enforcement_press",
    },
    "circulars_withdrawn": {
        "url": "https://www.rbi.org.in/Scripts/BS_CircularsIndexDisplay.aspx",
        "label_role": "validation/motivation source",
        "extraction_source": "rbi_circulars_withdrawn",
    },
    "amendments": {
        # Amendment Directions often appear within Master Directions / notifications listings
        "url": "https://www.rbi.org.in/Scripts/NotificationUser.aspx",
        "label_role": "primary_corpus",
        "extraction_source": "rbi_amendment_directions",
    },
}


@dataclass
class SuppDoc:
    document_id: str
    source_url: str
    title: str
    source_type: str
    label_role: str
    extraction_source: str
    format: str = "HTML"


class SupplementaryHarvester:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] | None = None,
    ):
        self.cfg = config or load_config()
        self.logger = setup_logging("scraper.supplementary", self.cfg)
        self.session = session or requests.Session()
        self.sleeper = sleeper or time.sleep
        rbi = self.cfg["rbi"]
        self.timeout = float(rbi.get("request_timeout_sec", 60))
        self.rate_limit = float(rbi.get("rate_limit_sec", 1.5))
        self.max_retries = int(rbi.get("max_retries", 4))
        self.backoff = float(rbi.get("backoff_factor", 2.0))
        self.base = rbi["base_url"].rstrip("/")
        self.session.headers.update(
            {
                "User-Agent": rbi.get(
                    "user_agent",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": self.base + "/",
            }
        )
        self.raw_root = resolve_path(self.cfg, "raw")
        self.meta = resolve_path(self.cfg, "metadata")
        self._last = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.rate_limit:
            self.sleeper(self.rate_limit - elapsed)

    def fetch(self, url: str) -> requests.Response:
        last_exc = None
        for attempt in range(1, self.max_retries + 1):
            self._wait()
            try:
                self.logger.info("GET %s attempt=%s", url, attempt)
                resp = self.session.get(url, timeout=self.timeout)
                self._last = time.monotonic()
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"status {resp.status_code}")
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                self.sleeper(self.backoff ** attempt)
        raise RuntimeError(f"Failed {url}: {last_exc}")

    def discover(self, source_type: str, html: str | None = None) -> list[SuppDoc]:
        meta = SUPPLEMENT_SOURCES[source_type]
        if html is None:
            resp = self.fetch(meta["url"])
            html = resp.text
            listing = self.raw_root / source_type / f"_listing_{source_type}.html"
            listing.parent.mkdir(parents=True, exist_ok=True)
            listing.write_text(html, encoding="utf-8")
        soup = BeautifulSoup(html, "lxml")
        docs: list[SuppDoc] = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 12:
                continue
            # Filter noisy nav links
            if title.lower() in {"home", "more", "click here", "english", "hindi"}:
                continue
            full = urljoin(meta["url"], href)
            if "rbi.org.in" not in full:
                continue
            # Heuristic: keep notification / press / faq-like links
            keep = False
            if source_type == "faq" and ("FAQ" in href or "faq" in href.lower() or "FAQ" in title):
                keep = True
            if source_type == "enforcement" and (
                "PressRelease" in href or "press" in href.lower() or "enforcement" in title.lower()
                or "penalty" in title.lower() or "monetary penalty" in title.lower()
            ):
                keep = True
            if source_type == "circulars_withdrawn" and (
                "withdraw" in title.lower() or "Circular" in href or "Notification" in href
            ):
                keep = True
            if source_type == "amendments" and (
                "amendment" in title.lower() or "Amendment" in title
            ):
                keep = True
            if not keep:
                continue
            digest = hashlib.sha1(full.encode()).hexdigest()[:12]
            did = f"{source_type}_{digest}"
            if did in seen:
                continue
            seen.add(did)
            docs.append(
                SuppDoc(
                    document_id=did,
                    source_url=full,
                    title=title,
                    source_type=source_type,
                    label_role=meta["label_role"],
                    extraction_source=meta["extraction_source"],
                )
            )
        self.logger.info("Discovered %s links for %s", len(docs), source_type)
        return docs

    def download(self, doc: SuppDoc, limit_chars_save: bool = False) -> dict[str, Any]:
        sub = self.raw_root / doc.source_type
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / f"{doc.document_id}.html"
        ts = datetime.now(timezone.utc).isoformat()
        if path.exists() and path.stat().st_size > 0 and self.cfg["scraper"].get("resumable", True):
            content = path.read_bytes()
            return {
                "document_id": doc.document_id,
                "source_url": doc.source_url,
                "title": doc.title,
                "format": "HTML",
                "download_status": "cached",
                "timestamp": ts,
                "local_path": str(path),
                "content_hash": hashlib.sha256(content).hexdigest(),
                "source_type": doc.source_type,
                "label_role": doc.label_role,
                "extraction_source": doc.extraction_source,
            }
        try:
            resp = self.fetch(doc.source_url)
            path.write_bytes(resp.content)
            return {
                "document_id": doc.document_id,
                "source_url": doc.source_url,
                "title": doc.title,
                "format": "HTML",
                "download_status": "success",
                "timestamp": ts,
                "local_path": str(path),
                "content_hash": hashlib.sha256(resp.content).hexdigest(),
                "source_type": doc.source_type,
                "label_role": doc.label_role,
                "extraction_source": doc.extraction_source,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "document_id": doc.document_id,
                "source_url": doc.source_url,
                "title": doc.title,
                "format": "HTML",
                "download_status": "failed",
                "timestamp": ts,
                "local_path": None,
                "content_hash": None,
                "source_type": doc.source_type,
                "label_role": doc.label_role,
                "extraction_source": doc.extraction_source,
                "failure_reason": str(exc),
            }

    def run(self, per_source_limit: int = 40) -> dict[str, Any]:
        """Harvest supplementary sources; tag FAQ/enforcement as validation/motivation."""
        all_manifest: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        for source_type in SUPPLEMENT_SOURCES:
            try:
                docs = self.discover(source_type)[:per_source_limit]
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Discovery failed for %s: %s", source_type, exc)
                counts[source_type] = 0
                (self.meta / f"supplement_{source_type}_error.txt").write_text(
                    f"FAILED — {exc}", encoding="utf-8"
                )
                continue
            ok = 0
            for d in docs:
                row = self.download(d)
                all_manifest.append(row)
                if row["download_status"] in {"success", "cached"}:
                    ok += 1
            counts[source_type] = ok
            self.logger.info("Supplementary %s downloaded/cached=%s", source_type, ok)

        out = self.meta / "supplementary_manifest.json"
        out.write_text(json.dumps(all_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return {
            "supplementary_documents_harvested": counts,
            "supplementary_manifest_path": str(out),
            "total_supplementary_rows": len(all_manifest),
        }
