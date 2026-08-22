"""PDF/HTML to plain text.

Implements the contract fixed by :mod:`src.extraction.interfaces`. Reads
payloads back through the same :class:`~src.common.cache.ArtifactCache` that
:mod:`src.scraper.rbi_scraper` cached them into, re-deriving the cache key from
``document_id`` rather than parsing ``DocumentRecord.local_path`` as a raw
filesystem path — the cache's own read-through order (attached Kaggle Dataset
first, then the working directory) is what makes extraction work on a fresh
Kaggle session that reads a previous session's harvest from an input Dataset,
and re-parsing the path string would silently bypass that.

Three distinct failure/edge modes are tracked separately, per Task 3 of the
governing prompt, because they mean different things:

* **not yet downloaded** — no cached payload exists (a prior download failure).
  Not this step's problem to fix.
* **extraction failed** — the parser raised (a genuinely malformed PDF/HTML).
* **extracted empty** — the parser succeeded but produced no usable text (a
  scanned/image-only PDF is the common cause). A corpus-coverage finding, not
  an error.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Mapping

from bs4 import BeautifulSoup
import pdfplumber

from src.common.cache import ArtifactCache
from src.common.errors import FoundationError
from src.common.io_helpers import read_jsonl, write_text
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.schemas.provenance import DocumentRecord

BRANCH = "phase1/akash-scraper"

#: Below this many characters, a "successful" extraction is treated as empty.
#: Short enough that a genuinely brief Direction is never misclassified, high
#: enough to catch a PDF that parsed to page-number noise and nothing else.
MIN_USABLE_CHARS = 20


class ExtractionError(FoundationError):
    """A payload could not be converted to text."""


def _cached_bytes(
    record: DocumentRecord, cache: ArtifactCache
) -> tuple[bytes, str]:
    """Fetch the cached payload for `record`, trying both known suffixes.

    `record.format` names the format at download time, but a record loaded
    back from the manifest is trusted at face value; trying the alternate
    suffix on a miss costs one extra lookup and avoids a spurious failure if
    format detection ever disagrees with the cached suffix.
    """
    key = cache.key_for("rbi_master_directions", record.document_id)
    fmt = (record.format or "PDF").upper()
    primary_suffix = ".pdf" if fmt == "PDF" else ".html"
    data = cache.get(key, suffix=primary_suffix)
    if data is not None:
        return data, fmt

    fallback_suffix = ".html" if primary_suffix == ".pdf" else ".pdf"
    data = cache.get(key, suffix=fallback_suffix)
    if data is not None:
        return data, "HTML" if fallback_suffix == ".html" else "PDF"

    raise ExtractionError(
        f"{record.document_id}: no cached payload found (tried {primary_suffix} and "
        f"{fallback_suffix}); run download_document before extraction"
    )


def _extract_pdf_text(data: bytes, *, document_id: str) -> str:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:  # noqa: BLE001 - pdfplumber/pdfminer raise assorted types
        raise ExtractionError(f"{document_id}: PDF parsing failed: {type(exc).__name__}: {exc}") from exc
    return "\n\n".join(pages)


def _extract_html_text(data: bytes, *, document_id: str) -> str:
    try:
        soup = BeautifulSoup(data, "lxml")
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"{document_id}: HTML parsing failed: {type(exc).__name__}: {exc}") from exc
    return soup.get_text("\n\n", strip=True)


def extract_text(
    record: DocumentRecord,
    cfg: Mapping[str, Any],
    *,
    cache: ArtifactCache | None = None,
    resolver: PathResolver | None = None,
    **kwargs: Any,
) -> str:
    """Extract plain text from one document's cached payload.

    Raises:
        ExtractionError: No cached payload exists, or the payload could not
            be parsed.
    """
    resolver = resolver or PathResolver.from_config(cfg)
    cache = cache or ArtifactCache.from_config(cfg, resolver, namespace="scraper")

    data, fmt = _cached_bytes(record, cache)
    if fmt == "PDF":
        return _extract_pdf_text(data, document_id=record.document_id)
    return _extract_html_text(data, document_id=record.document_id)


def extract_corpus(
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    cache: ArtifactCache | None = None,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Extract text for every downloaded document in the manifest.

    Reads ``data/metadata/document_manifest.jsonl`` (written by
    :func:`src.scraper.rbi_scraper.write_manifest`) and writes one
    ``data/extracted/<document_id>.txt`` per successful extraction.
    """
    logger = logger or get_logger("extraction.text", cfg)
    resolver = resolver or PathResolver.from_config(cfg)
    cache = cache or ArtifactCache.from_config(cfg, resolver, namespace="scraper")

    manifest_path = resolver.read_path("metadata", "document_manifest.jsonl")
    records = [DocumentRecord.from_dict(r) for r in read_jsonl(manifest_path)]

    considered = 0
    successful = 0
    failures: list[dict[str, str]] = []
    empty: list[str] = []
    skipped_not_downloaded: list[str] = []

    for record in records:
        if not record.content_hash:
            skipped_not_downloaded.append(record.document_id)
            continue
        considered += 1
        try:
            text = extract_text(record, cfg, cache=cache, resolver=resolver)
        except ExtractionError as exc:
            logger.error("extraction: %s failed: %s", record.document_id, exc)
            failures.append({"document_id": record.document_id, "reason": str(exc)})
            continue

        if len(text.strip()) < MIN_USABLE_CHARS:
            logger.warning(
                "extraction: %s parsed but produced only %d usable characters (likely scanned/image PDF)",
                record.document_id,
                len(text.strip()),
            )
            empty.append(record.document_id)
            continue

        target = resolver.write_path("extracted", f"{record.document_id}.txt")
        write_text(target, text)
        successful += 1

    metrics = {
        "documents_considered": considered,
        "extraction_successful": successful,
        "extraction_failures": len(failures),
        "extraction_empty": len(empty),
        "skipped_not_downloaded": len(skipped_not_downloaded),
        "extraction_success_rate": (successful / considered) if considered else "NOT YET MEASURED",
        "failures": failures,
        "empty_document_ids": empty,
    }
    logger.info("extraction: %s", {k: v for k, v in metrics.items() if k not in ("failures", "empty_document_ids")})
    return metrics
