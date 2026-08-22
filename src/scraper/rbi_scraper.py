"""RBI Master Directions discovery and download.

Implements the contract fixed by :mod:`src.scraper.interfaces`. Two site-specific
facts drove the design, both confirmed against the live site while building this
module (not assumed from the dossier):

**The listing page has no subject-family axis.**
``BS_ViewMasDirections.aspx`` groups documents under an entity-class heading
(e.g. "Commercial Banks") and, within that, a date sub-heading. There is no
third column or heading level naming a subject/topic. Task 4 of the governing
prompt calls for ``subject_family_raw`` to be recorded "exactly as listed" —
faithfully honouring that here means leaving it ``None``, not inventing a value
by parsing it out of the title, which is what produced the bugs documented in
the project's own history (`week3_issues.md` in the pre-Phase-0 implementation
split titles on the wrong dash character and truncated names such as
"Urban Co-operative Banks" to "Urban Co"). Subject-family construction is left
to ``phase1/karan-matrix``, which can draw on paragraph text rather than a
listing column that does not exist.

**The same 11-entity-class heading list appears twice, with no distinguishing
marker anywhere in the HTML** (checked: no wrapping section element, no anchor,
no dropdown, no id difference). The second pass skews toward much more recent
dates. This is recorded as a discovery finding (``category_pass`` is logged and
counted, though not persisted onto ``DocumentRecord`` — no schema field exists
for it, and adding one is a base-branch decision, not this branch's to make
unilaterally). It does not block discovery: ``entity_class_raw`` is still
recorded faithfully as the heading text under which each document appeared.

**The PDF host WAF fingerprints the client beyond the User-Agent header.**
A plain ``curl`` request to ``rbidocs.rbi.org.in`` with a spoofed browser
User-Agent still had its connection dropped after a clean TLS handshake
("Empty reply from server"), while the same headers sent through Python's
``requests`` succeeded consistently. This module therefore requires
``requests`` and a real ``Session`` — do not reimplement the HTTP layer with
a lower-level client without re-verifying against the live site.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import requests
from bs4 import BeautifulSoup

from src.common.cache import ArtifactCache
from src.common.config import get_required
from src.common.errors import FoundationError
from src.common.io_helpers import write_jsonl
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.common.retry import RetryPolicy, retry_call
from src.extraction.temporal_signals import extract_update_date_stamp
from src.schemas.provenance import DocumentRecord

BRANCH = "phase1/akash-scraper"

#: Row matches an RBI entity-class or subject grouping heading if it is a lone
#: `<td class="tableheader">` cell that does NOT look like a date.
DATE_HEADER_RE = re.compile(r"^[A-Za-z]{3}\s+\d{1,2},\s*\d{4}$")

#: Extracts the RBI-assigned document id from a detail-page href.
ID_RE = re.compile(r"[?&]id=(\d+)")


class PayloadValidationError(FoundationError):
    """A downloaded payload does not match its expected format.

    Raised for anything that isn't a genuine PDF/HTML payload — most often the
    RBI PDF host's WAF returning a challenge or block page instead of the
    document. Deliberately distinct from a network error: this is a successful
    HTTP response carrying the wrong content, not a failed request.
    """


class DiscoveryError(FoundationError):
    """Discovery could not retrieve or parse the listing page at all."""


def build_session(cfg: Mapping[str, Any]) -> requests.Session:
    """A `requests.Session` carrying the headers the live site requires.

    See the module docstring: User-Agent alone is not sufficient against
    ``rbidocs.rbi.org.in``'s WAF, but has been sufficient in combination with
    `requests`' TLS stack in every observation made while building this module.
    """
    sources = cfg.get("network", {}).get("sources", {})
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": sources.get(
                "user_agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ),
            "Referer": sources.get("referer", "https://www.rbi.org.in/"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def _retry_policy(cfg: Mapping[str, Any]) -> RetryPolicy:
    return RetryPolicy.from_config(cfg)


def _fetch(
    url: str,
    session: requests.Session,
    cfg: Mapping[str, Any],
    *,
    logger: logging.Logger,
    description: str,
) -> bytes:
    """GET ``url`` through retry_call, returning the response body."""
    timeout = get_required(cfg, "network.request_timeout_sec")

    def attempt() -> bytes:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content

    return retry_call(
        attempt,
        policy=_retry_policy(cfg),
        retry_on=(requests.exceptions.RequestException,),
        description=description,
        logger=logger,
    )


# -- discovery ------------------------------------------------------------


def _row_entity_heading(row) -> str | None:
    """Return heading text if `row` is a category/date heading row, else None."""
    cells = row.find_all("td")
    if len(cells) != 1:
        return None
    classes = cells[0].get("class") or []
    if "tableheader" not in classes:
        return None
    text = cells[0].get_text(strip=True)
    if DATE_HEADER_RE.match(text):
        return None  # a date sub-heading, not an entity-class heading
    return text


def _parse_listing(html: str, *, logger: logging.Logger) -> list[dict[str, Any]]:
    """Parse the Master Directions listing into raw row dicts.

    Pure function of the HTML text, so it is directly testable against a
    fixture without a network call. Tracks which pass (first or second
    unexplained repetition) of the entity-class heading list each row belongs
    to, purely for the discovery-findings log line — not persisted to any
    schema, since no field exists for it.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        raise DiscoveryError("listing page has no <table> element; site layout may have changed")

    rows: list[dict[str, Any]] = []
    current_entity: str | None = None
    seen_entities: dict[str, int] = {}
    current_pass = 0
    seen_ids: set[str] = set()
    duplicate_count = 0
    uncategorised = 0

    for tr in tables[0].find_all("tr"):
        heading = _row_entity_heading(tr)
        if heading is not None:
            current_entity = heading
            seen_entities[heading] = seen_entities.get(heading, 0) + 1
            current_pass = seen_entities[heading]
            continue

        cells = tr.find_all("td")
        if not cells:
            continue
        link = cells[0].find("a", class_="link2")
        if link is None:
            continue

        href = link.get("href", "")
        match = ID_RE.search(href)
        if not match:
            logger.warning("discovery: doc row with unparseable href, skipping: %r", href)
            continue
        rbi_id = match.group(1)
        document_id = f"md_{rbi_id}"

        title = link.get_text(" ", strip=True)

        pdf_url: str | None = None
        fmt: str | None = None
        if len(cells) > 1:
            pdf_link = cells[1].find("a")
            if pdf_link is not None:
                pdf_href = pdf_link.get("href", "")
                pdf_url = pdf_href
                fmt = "PDF" if pdf_href.upper().endswith(".PDF") else "HTML"

        if document_id in seen_ids:
            duplicate_count += 1
            logger.warning("discovery: duplicate document_id %s, keeping first occurrence", document_id)
            continue
        seen_ids.add(document_id)

        if current_entity is None:
            uncategorised += 1
            logger.warning("discovery: document %s has no preceding entity-class heading", document_id)

        rows.append(
            {
                "document_id": document_id,
                "title": title,
                "entity_class_raw": current_entity,
                "category_pass": current_pass,
                "pdf_url": pdf_url,
                "format": fmt,
            }
        )

    logger.info(
        "discovery: parsed %d documents, %d duplicate ids skipped, %d uncategorised, "
        "%d distinct entity-class headings across %d total heading occurrences",
        len(rows),
        duplicate_count,
        uncategorised,
        len(seen_entities),
        sum(seen_entities.values()),
    )
    repeated = {k: v for k, v in seen_entities.items() if v > 1}
    if repeated:
        logger.warning(
            "discovery: %d entity-class headings appear more than once with no "
            "distinguishing marker in the source HTML (see rbi_scraper module docstring): %s",
            len(repeated),
            sorted(repeated),
        )

    return rows


def discover_documents(
    cfg: Mapping[str, Any],
    *,
    html: str | None = None,
    session: requests.Session | None = None,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> list[DocumentRecord]:
    """Enumerate Master Directions from the RBI listing page.

    Args:
        html: Pre-fetched listing HTML. Tests pass a fixture here; omitted in
            production, which fetches the live page.
        session: Reuse an existing session (e.g. for a shared connection pool
            across discovery and download). One is built from config if omitted.

    Discovery is entirely separate from download: this function makes at most
    one network call (the listing page itself), so a download failure later
    can never shrink what is recorded as discovered.
    """
    logger = logger or get_logger("scraper.rbi", cfg)
    resolved_session = session or build_session(cfg)

    if html is None:
        listing_url = get_required(cfg, "network.sources.rbi_master_directions.listing_url")
        html = _fetch(listing_url, resolved_session, cfg, logger=logger, description="fetch listing page").decode(
            "utf-8", errors="replace"
        )

    raw_rows = _parse_listing(html, logger=logger)
    if not raw_rows:
        raise DiscoveryError(
            "discovery found zero documents — this indicates the parser or the page "
            "structure is broken, not that the corpus is small"
        )

    records = []
    for row in raw_rows:
        update_date = extract_update_date_stamp(row["title"])
        records.append(
            DocumentRecord(
                document_id=row["document_id"],
                source_url=row["pdf_url"],
                title=row["title"],
                entity_class_raw=row["entity_class_raw"],
                subject_family_raw=None,  # not present on this listing; see module docstring
                update_date=update_date,
                extraction_source="rbi_master_directions",
                document_role="primary_corpus",
                format=row["format"],
            )
        )
    return records


# -- download ---------------------------------------------------------------

#: Magic-byte / content checks for validating a payload before it is cached.
_PDF_MAGIC = b"%PDF-"
_HTML_MARKERS = (b"<!doctype html", b"<html")
#: Substrings seen in WAF/bot-challenge pages, for a clearer log message than
#: "malformed payload" when that is what actually happened.
_WAF_MARKERS = (b"incapsula", b"imperva", b"are you a robot", b"access denied", b"request unsuccessful")


def _validate_payload(data: bytes, expected_format: str | None) -> tuple[bool, str]:
    """Check `data` actually is what `expected_format` claims it is.

    Returns ``(is_valid, detected_format_or_reason)``. Checked by magic bytes,
    not by trusting the URL extension or a content-type header — a WAF
    challenge page served at a ``.PDF`` URL still needs to be caught here.
    """
    head = data[:2048].lower()
    if data.startswith(_PDF_MAGIC):
        return True, "PDF"
    if any(marker in head for marker in _HTML_MARKERS):
        if any(marker in head for marker in _WAF_MARKERS):
            return False, "WAF/bot-challenge page detected in place of the document"
        if expected_format == "HTML":
            return True, "HTML"
        return False, "received HTML where a PDF was expected"
    return False, f"unrecognised payload (first bytes: {data[:16]!r})"


def download_document(
    record: DocumentRecord,
    cfg: Mapping[str, Any],
    *,
    session: requests.Session | None = None,
    cache: ArtifactCache | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> DocumentRecord:
    """Download, validate, hash and cache one document's payload.

    Returns a new record with ``local_path``, ``content_hash``, ``format`` and
    ``retrieved_at`` populated. Raises rather than returning a partially-filled
    record on failure, so the caller's failure accounting cannot mistake a
    failed download for a successful one with empty fields.

    Raises:
        PayloadValidationError: The response body is not a genuine document —
            most often a WAF challenge page. Never cached under the target name.
        RetryExhaustedError: The request failed on every retry attempt.
    """
    if not record.source_url:
        raise PayloadValidationError(f"{record.document_id}: no source_url to download from")

    logger = logger or get_logger("scraper.rbi", cfg)
    resolved_session = session or build_session(cfg)
    resolver = resolver or PathResolver.from_config(cfg)
    cache = cache or ArtifactCache.from_config(cfg, resolver, namespace="scraper")

    data = _fetch(
        record.source_url,
        resolved_session,
        cfg,
        logger=logger,
        description=f"download {record.document_id}",
    )

    is_valid, detail = _validate_payload(data, record.format)
    if not is_valid:
        logger.error("download: %s payload rejected: %s", record.document_id, detail)
        raise PayloadValidationError(f"{record.document_id}: {detail}")

    fmt = detail  # "PDF" or "HTML", as confirmed by _validate_payload
    content_hash = hashlib.sha256(data).hexdigest()

    cache_key = cache.key_for("rbi_master_directions", record.document_id)
    suffix = ".pdf" if fmt == "PDF" else ".html"
    cached_path = cache.put(cache_key, data, suffix=suffix)
    local_path = str(cached_path.relative_to(resolver.working_root))

    logger.info(
        "download: %s ok (%s, %d bytes, sha256=%s...)",
        record.document_id,
        fmt,
        len(data),
        content_hash[:12],
    )

    return replace(
        record,
        format=fmt,
        content_hash=content_hash,
        local_path=local_path,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
    )


# -- orchestration ------------------------------------------------------------


def harvest_corpus(
    cfg: Mapping[str, Any],
    *,
    limit: int | None = None,
    session: requests.Session | None = None,
    resolver: PathResolver | None = None,
    cache: ArtifactCache | None = None,
    logger: logging.Logger | None = None,
    sleep_fn: Any = time.sleep,
    html: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run discovery then download for every discovered document.

    Args:
        limit: Cap the number of documents downloaded, for a small validation
            slice or a local smoke run. Discovery always runs against the full
            listing regardless of ``limit`` — the discovered count is a
            measurement never subject to a cap.

    A single document's download failure is logged, counted, and does not
    abort the run; every other document is still attempted.
    """
    logger = logger or get_logger("scraper.rbi", cfg)
    resolved_session = session or build_session(cfg)
    resolver = resolver or PathResolver.from_config(cfg)
    cache = cache or ArtifactCache.from_config(cfg, resolver, namespace="scraper")
    rate_limit = float(get_required(cfg, "network.rate_limit_sec")) if "rate_limit_sec" in cfg.get("network", {}) else 0.0

    discovered = discover_documents(cfg, html=html, session=resolved_session, logger=logger)
    to_download = discovered[:limit] if limit is not None else discovered

    downloaded: list[DocumentRecord] = []
    failures: list[dict[str, str]] = []
    pdf_count = 0
    html_count = 0

    for index, record in enumerate(to_download):
        if index > 0 and rate_limit > 0:
            sleep_fn(rate_limit)
        try:
            result = download_document(
                record, cfg, session=resolved_session, cache=cache, resolver=resolver, logger=logger
            )
        except FoundationError as exc:
            logger.error("harvest: %s failed: %s", record.document_id, exc)
            failures.append({"document_id": record.document_id, "reason": str(exc)})
            downloaded.append(record)  # keep the discovery-time record; payload fields stay null
            continue
        downloaded.append(result)
        if result.format == "PDF":
            pdf_count += 1
        elif result.format == "HTML":
            html_count += 1

    manifest_path = write_manifest(downloaded, cfg, resolver=resolver)

    metrics = {
        "documents_discovered": len(discovered),
        "downloads_attempted": len(to_download),
        "downloads_successful": len(to_download) - len(failures),
        "downloads_failed": len(failures),
        "download_success_rate": (
            (len(to_download) - len(failures)) / len(to_download) if to_download else "NOT YET MEASURED"
        ),
        "pdf_count": pdf_count,
        "html_count": html_count,
        "manifest_path": manifest_path,
        "failures": failures,
    }
    logger.info("harvest: %s", {k: v for k, v in metrics.items() if k != "failures"})
    return metrics


def write_manifest(
    records: Iterable[DocumentRecord], cfg: Mapping[str, Any], *, resolver: PathResolver | None = None
) -> str:
    """Persist the discovered/downloaded corpus manifest as JSONL."""
    resolver = resolver or PathResolver.from_config(cfg)
    path = resolver.write_path("metadata", "document_manifest.jsonl")
    write_jsonl(path, [r.to_dict() for r in records])
    return str(path)
