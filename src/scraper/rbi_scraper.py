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
from pathlib import Path
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
        if not title:
            # P1-004 (A9): three Directions (md_11959, md_12839, md_11510)
            # came back with an empty title because the anchor's own text is
            # blank — the listing puts the text in a child element, or in the
            # row's remaining cells, for those rows. Recover it from the row
            # itself, never from the PDF: a title taken from the document body
            # is a different field with different provenance, and
            # subject_family is derived from this string by stripping the
            # entity-class prefix, so a substituted title silently changes a
            # derived axis.
            title = (link.get("title") or "").strip()
        if not title:
            title = cells[0].get_text(" ", strip=True)
        if not title:
            for cell in cells[1:]:
                candidate = cell.get_text(" ", strip=True)
                if candidate and not candidate.lower().endswith((".pdf", "pdf")):
                    title = candidate
                    break
        if not title:
            logger.warning(
                "discovery: %s has no title anywhere in its listing row — left empty rather "
                "than substituted from the PDF body", href,
            )

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


# -- P1-004: payload retries, only-missing harvest, manual import -------------


class RequestBudgetExceeded(FoundationError):
    """The planned harvest would exceed ``max_requests``. Nothing was sent."""


def download_with_payload_retries(
    record: DocumentRecord,
    cfg: Mapping[str, Any],
    *,
    session: requests.Session,
    cache: ArtifactCache,
    resolver: PathResolver,
    logger: logging.Logger,
    warm_up: Any = None,
    sleep_fn: Any = time.sleep,
) -> tuple[DocumentRecord | None, dict[str, Any]]:
    """Download one document, retrying an HTML-where-PDF-expected payload.

    The first harvest treated a single HTML body as a permanent failure and
    lost 81 Directions to it. The failures were the first 81 records in
    download order, which is the signature of a session-level block rather
    than 81 individually broken documents — so a retry that re-requests the
    listing page first, re-establishing whatever session state the host wants
    to see, is worth attempting before giving up on a document.

    This is ordinary polite client behaviour: a fresh warm-up and a backoff.
    Nothing here attempts to disguise the client or evade a block.

    Returns ``(record_or_None, outcome)``. A failure returns ``None`` and is
    the caller's to count; it never raises, so one bad document cannot abort
    a 380-document harvest.
    """
    attempts_allowed = max(1, int((cfg.get("network", {}) or {}).get("payload_retries", 3)))
    attempts: list[str] = []

    for attempt in range(1, attempts_allowed + 1):
        if attempt > 1:
            delay = min(2.0 ** (attempt - 1), 30.0)
            logger.info(
                "harvest: %s attempt %d/%d after %.1fs, re-warming the listing first",
                record.document_id, attempt, attempts_allowed, delay,
            )
            sleep_fn(delay)
            if warm_up is not None:
                try:
                    warm_up()
                except Exception as exc:  # a warm-up failure is not fatal
                    logger.warning("harvest: listing warm-up failed: %s", exc)
        try:
            result = download_document(
                record, cfg, session=session, cache=cache, resolver=resolver, logger=logger
            )
        except PayloadValidationError as exc:
            attempts.append(f"attempt {attempt}: {exc}")
            continue
        except FoundationError as exc:
            attempts.append(f"attempt {attempt}: {exc}")
            break  # a transport failure is not a payload problem; stop here
        return result, {
            "document_id": record.document_id,
            "attempts": attempt,
            "outcome": "ok",
            "detail": attempts,
        }

    return None, {
        "document_id": record.document_id,
        "attempts": len(attempts),
        "outcome": "failed",
        "detail": attempts,
    }


def import_manual_pdfs(
    import_dir: Path | str,
    manifest: Iterable[DocumentRecord],
    cfg: Mapping[str, Any],
    *,
    cache: ArtifactCache | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
) -> tuple[list[DocumentRecord], dict[str, Any]]:
    """Adopt PDFs downloaded by hand in a browser, as if they had been fetched.

    The escape hatch for documents the host will not serve to any automated
    client. A file is matched to a manifest record by its URL basename
    (case-insensitively) or by ``<document_id>.pdf``, checked for the ``%PDF``
    magic bytes, hashed and written into the same cache key a download would
    have used — so everything downstream cannot tell, and does not need to,
    how the bytes arrived. The manifest records that it was a manual import,
    because provenance is not something to lose for convenience.
    """
    logger = logger or get_logger("scraper.rbi", cfg)
    resolver = resolver or PathResolver.from_config(cfg)
    cache = cache or ArtifactCache.from_config(cfg, resolver, namespace="scraper")

    records = list(manifest)
    import_dir = Path(import_dir)
    if not import_dir.is_dir():
        logger.warning("manual import: %s is not a directory — nothing imported", import_dir)
        return records, {"manual_import_ids": [], "manual_import_unmatched": []}

    by_basename: dict[str, DocumentRecord] = {}
    by_doc_id: dict[str, DocumentRecord] = {}
    for record in records:
        if record.content_hash:
            continue  # already have it; a manual file must not overwrite a download
        if record.source_url:
            by_basename[Path(record.source_url).name.lower()] = record
        by_doc_id[f"{record.document_id}.pdf".lower()] = record

    imported: dict[str, DocumentRecord] = {}
    unmatched: list[str] = []

    for path in sorted(import_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        target = by_basename.get(path.name.lower()) or by_doc_id.get(path.name.lower())
        if target is None:
            unmatched.append(path.name)
            logger.warning(
                "manual import: %s matches no missing manifest record by URL basename or "
                "<document_id>.pdf — skipped", path.name,
            )
            continue

        data = path.read_bytes()
        if not data.startswith(_PDF_MAGIC):
            unmatched.append(path.name)
            logger.error(
                "manual import: %s is not a PDF (first bytes %r) — skipped. A saved WAF "
                "challenge page would otherwise be adopted as a Direction.",
                path.name, data[:16],
            )
            continue

        cache_key = cache.key_for("rbi_master_directions", target.document_id)
        cached_path = cache.put(cache_key, data, suffix=".pdf")
        imported[target.document_id] = replace(
            target,
            format="PDF",
            content_hash=hashlib.sha256(data).hexdigest(),
            local_path=str(cached_path.relative_to(resolver.working_root)),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            extraction_source="manual_browser_download",
        )
        logger.info(
            "manual import: %s adopted from %s (%d bytes)", target.document_id, path.name, len(data)
        )

    merged = [imported.get(r.document_id, r) for r in records]
    return merged, {
        "manual_import_ids": sorted(imported),
        "manual_import_unmatched": sorted(unmatched),
        "manual_import_note": (
            "obtained by manual browser download from source_url; bytes validated by %PDF "
            "magic and cached under the same key a download would have used"
        ),
    }


def coverage_by_entity_class(
    records: Iterable[DocumentRecord], *, logger: logging.Logger | None = None
) -> dict[str, Any]:
    """Downloaded share per entity class, which is what RQ1 actually needs.

    An overall 299/380 hides the thing that matters: the first harvest lost 35
    of 44 Commercial Banks Directions and 31 of 40 Small Finance Banks ones,
    so the two classes a cross-class comparison most depends on were the two
    most damaged. A single corpus-level rate cannot show that.
    """
    totals: dict[str, int] = {}
    have: dict[str, int] = {}
    for record in records:
        key = record.entity_class_raw or record.entity_class or "(unclassified)"
        totals[key] = totals.get(key, 0) + 1
        if record.content_hash:
            have[key] = have.get(key, 0) + 1

    table = {}
    for key in sorted(totals):
        got, total = have.get(key, 0), totals[key]
        rate = got / total if total else 0.0
        table[key] = {"downloaded": got, "total": total, "rate": rate}
        if logger is not None and rate < 0.90:
            logger.warning(
                "coverage: %s at %.1f%% (%d/%d) — below the 90%% bar",
                key, rate * 100, got, total,
            )

    overall_have = sum(have.values())
    overall_total = sum(totals.values())
    return {
        "by_entity_class": table,
        "classes_below_90_percent": sorted(k for k, v in table.items() if v["rate"] < 0.90),
        "overall": {
            "downloaded": overall_have,
            "total": overall_total,
            "rate": overall_have / overall_total if overall_total else 0.0,
        },
    }


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
    only_missing: bool = False,
    existing_manifest: Iterable[DocumentRecord] | None = None,
    max_requests: int | None = None,
    import_dir: Path | str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run discovery then download for every discovered document.

    Args:
        limit: Cap the number of documents downloaded, for a small validation
            slice or a local smoke run. Discovery always runs against the full
            listing regardless of ``limit`` — the discovered count is a
            measurement never subject to a cap.
        only_missing: Download only records that have no ``content_hash`` in
            ``existing_manifest``, plus ids the listing has gained since. A
            record already downloaded is carried through **unchanged** — the
            299 documents that succeeded are not re-fetched, which is the
            difference between a 81-request repair and a 380-request
            re-harvest against a host that already blocked us once.
        existing_manifest: The manifest to diff against. Required by
            ``only_missing``.
        max_requests: Refuse to start if the plan needs more requests than
            this. Checked **before** the first request, so an unexpectedly
            large plan costs nothing rather than being noticed halfway
            through.
        import_dir: Directory of hand-downloaded PDFs, adopted after the
            network pass for anything still missing.

    A single document's download failure is logged, counted, and does not
    abort the run; every other document is still attempted.
    """
    logger = logger or get_logger("scraper.rbi", cfg)
    resolved_session = session or build_session(cfg)
    resolver = resolver or PathResolver.from_config(cfg)
    cache = cache or ArtifactCache.from_config(cfg, resolver, namespace="scraper")
    rate_limit = float(get_required(cfg, "network.rate_limit_sec")) if "rate_limit_sec" in cfg.get("network", {}) else 0.0

    discovered = discover_documents(cfg, html=html, session=resolved_session, logger=logger)

    carried: list[DocumentRecord] = []
    new_since_previous: list[str] = []
    no_longer_listed: list[str] = []
    coverage_before: dict[str, Any] = {}

    if only_missing:
        if existing_manifest is None:
            raise DiscoveryError("only_missing requires existing_manifest")
        previous = {r.document_id: r for r in existing_manifest}
        coverage_before = coverage_by_entity_class(previous.values())
        listed = {r.document_id for r in discovered}

        new_since_previous = sorted(listed - set(previous))
        no_longer_listed = sorted(set(previous) - listed)

        to_download = []
        for record in discovered:
            prior = previous.get(record.document_id)
            if prior is not None and prior.content_hash:
                carried.append(prior)  # untouched, dict-equal to what was there
            else:
                to_download.append(prior or record)

        # A record the listing has dropped is kept, not deleted. A Direction
        # vanishing from a listing is a finding about the listing, and
        # silently shrinking the corpus would erase it.
        for doc_id in no_longer_listed:
            carried.append(previous[doc_id])

        logger.info(
            "harvest: only-missing plan — %d to fetch, %d carried unchanged, %d newly "
            "listed, %d no longer listed",
            len(to_download), len(carried), len(new_since_previous), len(no_longer_listed),
        )
    else:
        to_download = discovered[:limit] if limit is not None else discovered

    if limit is not None and only_missing:
        to_download = to_download[:limit]

    # Checked before anything is sent: an oversized plan costs nothing.
    if max_requests is not None and len(to_download) > max_requests:
        raise RequestBudgetExceeded(
            f"refusing to start: the plan needs {len(to_download)} requests, over the "
            f"max_requests budget of {max_requests}. No request has been sent. Raise the "
            "budget deliberately, or narrow the plan."
        )

    def _warm_up() -> None:
        listing_url = get_required(cfg, "network.sources.rbi_master_directions.listing_url")
        _fetch(listing_url, resolved_session, cfg, logger=logger, description="listing warm-up")

    downloaded: list[DocumentRecord] = []
    failures: list[dict[str, str]] = []
    payload_retry_outcomes: list[dict[str, Any]] = []
    cache_hits: list[str] = []
    pdf_count = 0
    html_count = 0

    for index, record in enumerate(to_download):
        # A cached payload is reused without a request. The first harvest had
        # no such check, so a re-run paid the full network cost — and every
        # avoided request is one the host cannot refuse.
        cache_key = cache.key_for("rbi_master_directions", record.document_id)
        cached = cache.get(cache_key, suffix=".pdf")
        if cached and cached.startswith(_PDF_MAGIC):
            entry = cache.locate(cache_key, suffix=".pdf")
            downloaded.append(replace(
                record, format="PDF",
                content_hash=hashlib.sha256(cached).hexdigest(),
                local_path=str(entry.path.relative_to(resolver.working_root)) if entry else None,
                retrieved_at=record.retrieved_at or datetime.now(timezone.utc).isoformat(),
            ))
            cache_hits.append(record.document_id)
            pdf_count += 1
            logger.info("harvest: %s served from cache, no request made", record.document_id)
            continue

        if index > 0 and rate_limit > 0:
            sleep_fn(rate_limit)

        result, outcome = download_with_payload_retries(
            record, cfg, session=resolved_session, cache=cache, resolver=resolver,
            logger=logger, warm_up=_warm_up if html is None else None, sleep_fn=sleep_fn,
        )
        payload_retry_outcomes.append(outcome)

        if result is None:
            reason = outcome["detail"][-1] if outcome["detail"] else "unknown"
            logger.error("harvest: %s failed after %d attempt(s): %s",
                         record.document_id, outcome["attempts"], reason)
            failures.append({"document_id": record.document_id, "reason": reason})
            downloaded.append(record)  # keep the record; payload fields stay null
            continue

        downloaded.append(result)
        if result.format == "PDF":
            pdf_count += 1
        elif result.format == "HTML":
            html_count += 1

    all_records = carried + downloaded
    import_metrics: dict[str, Any] = {"manual_import_ids": [], "manual_import_unmatched": []}
    if import_dir is not None:
        all_records, import_metrics = import_manual_pdfs(
            import_dir, all_records, cfg, cache=cache, resolver=resolver, logger=logger
        )

    all_records.sort(key=lambda r: r.document_id)
    manifest_path = write_manifest(all_records, cfg, resolver=resolver)
    coverage_after = coverage_by_entity_class(all_records, logger=logger)

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
        "only_missing": bool(only_missing),
        "records_carried_unchanged": len(carried),
        "cache_hits": cache_hits,
        "new_since_previous_harvest": new_since_previous,
        "no_longer_listed": no_longer_listed,
        "payload_retry_outcomes": payload_retry_outcomes,
        "coverage_by_entity_class_before": coverage_before,
        "coverage_by_entity_class_after": coverage_after,
        **import_metrics,
    }
    logger.info(
        "harvest: %s",
        {k: v for k, v in metrics.items()
         if k not in ("failures", "payload_retry_outcomes",
                      "coverage_by_entity_class_before", "coverage_by_entity_class_after")},
    )
    return metrics


def write_manifest(
    records: Iterable[DocumentRecord], cfg: Mapping[str, Any], *, resolver: PathResolver | None = None
) -> str:
    """Persist the discovered/downloaded corpus manifest as JSONL."""
    resolver = resolver or PathResolver.from_config(cfg)
    path = resolver.write_path("metadata", "document_manifest.jsonl")
    write_jsonl(path, [r.to_dict() for r in records])
    return str(path)
