"""Shared plumbing for the P2-003 source adapters.

* :class:`SupplementaryConfig`: the ``supplementary:`` config block, checked at load.
* :func:`supp_resolver`: registers the ``supplementary`` path key from that block.
* :func:`fetch_url`: one GET/POST through the P1 scraper's session and retry
  policy, returning a :class:`FetchResult` that is either valid content or a
  failure with a recorded reason. A CAPTCHA, error or unexpected page is never
  returned as content.
* :class:`SourceStore`: raw pages, the per-source fetch manifest (resume,
  only-missing) and the failure log.
* Item schema helpers (§P) and the era cut-off.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import requests

from src.common.config import get_required
from src.common.io_helpers import iter_jsonl, write_json, write_jsonl
from src.common.paths import PathResolver
from src.common.retry import RetryPolicy, retry_call

VERSION = "v1"
SOURCES = ("faq", "enforcement", "amendment", "withdrawn")
ERA_PRE = "pre_consolidation"
ERA_POST = "post_consolidation"
ERA_UNKNOWN = "unknown"
UNRESOLVED = "unresolved"

REASON_CAPTCHA = "captcha"
REASON_UNEXPECTED = "unexpected_content"
REASON_TIMEOUT = "timeout"
REASON_CONNECTION = "connection_error"

#: Challenge-page signals. Any of these makes a response a ``captcha`` failure, whatever else it holds.
CAPTCHA_MARKERS = (b"g-recaptcha", b"hcaptcha", b"are you a robot", b"verify you are human", b"incapsula",
                   b"imperva")
#: Seen in challenge and WAF block pages, but also in genuine content: the FLAIR FAQ (topic 176) tells users
#: to "enter the valid captcha code". Counted only when the expected content marker is absent.
BLOCK_MARKERS = (b"captcha", b"access denied", b"request unsuccessful", b"request rejected")
HTML_MARKERS = (b"<!doctype html", b"<html")
PDF_MAGIC = b"%PDF"

ITEM_FIELDS = ("item_id", "source", "source_url", "retrieved_at", "content_hash", "published_date",
               "title", "text", "fields", "cited_directions", "entity_class", "era")
FAILURE_FIELDS = ("url", "reason", "http_status", "retrieved_at")
#: §R: a source stops once at least this many fetches ran and max_failure_rate of them failed.
STOP_MIN_ATTEMPTS = 10


class SupplementaryError(RuntimeError):
    """A stop condition or a broken invariant in P2-003."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupplementaryConfig:
    version: str
    data_dir: str
    expected_corpus: Mapping[str, Any]
    rate_limit_sec: float
    era_cutoff: date
    smoke_items_per_source: int
    max_failure_rate: float
    faq: Mapping[str, Any]
    enforcement: Mapping[str, Any]
    amendments: Mapping[str, Any]
    withdrawn: Mapping[str, Any]
    linking: Mapping[str, Any]
    alignment: Mapping[str, Any]

    @classmethod
    def from_cfg(cls, cfg: Mapping[str, Any]) -> "SupplementaryConfig":
        block = cfg.get("supplementary")
        if not isinstance(block, Mapping):
            raise SupplementaryError("config has no `supplementary:` block")
        rate = float(block["rate_limit_sec"])
        if rate < 1.0:
            raise SupplementaryError(f"supplementary.rate_limit_sec must be >= 1 s, got {rate}")
        threshold = block["linking"]["fuzzy_threshold"]
        if not 0 < float(threshold) <= 1:
            raise SupplementaryError(f"supplementary.linking.fuzzy_threshold must be in (0, 1], got {threshold}")
        return cls(
            version=str(block.get("version", VERSION)),
            data_dir=str(block["data_dir"]),
            expected_corpus=dict(block["expected_corpus"]),
            rate_limit_sec=rate,
            era_cutoff=parse_iso_date(str(block["era_cutoff"])),
            smoke_items_per_source=int(block["smoke_items_per_source"]),
            max_failure_rate=float(block["max_failure_rate"]),
            faq=dict(block["faq"]),
            enforcement=dict(block["enforcement"]),
            amendments=dict(block["amendments"]),
            withdrawn=dict(block["withdrawn"]),
            linking=dict(block["linking"]),
            alignment=dict(block["alignment"]),
        )


def supp_resolver(resolver: PathResolver, sc: SupplementaryConfig) -> PathResolver:
    """``resolver`` with the logical key ``supplementary`` -> ``sc.data_dir``."""
    return dataclasses.replace(resolver, relative_paths={**resolver.relative_paths, "supplementary": sc.data_dir})


# ---------------------------------------------------------------------------
# Dates and era
# ---------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_DATE_RE = re.compile(
    r"\b(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?"
    r"|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})\b", re.IGNORECASE)


def parse_iso_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def parse_listing_date(raw: str | None) -> str | None:
    """``"Sep 24, 2026"`` / ``"September 24, 2026"`` -> ``"2026-09-24"``; ``None`` when absent."""
    if not raw:
        return None
    m = _DATE_RE.search(raw)
    if not m:
        return None
    try:
        return date(int(m["year"]), _MONTHS[m["mon"][:3].lower()], int(m["day"])).isoformat()
    except ValueError:
        return None


def era_of(published_date: str | None, cutoff: date) -> str:
    """P2-003 §P: on or after the consolidation cut-off is post_consolidation."""
    if not published_date:
        return ERA_UNKNOWN
    return ERA_POST if date.fromisoformat(published_date) >= cutoff else ERA_PRE


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_text(raw: str) -> str:
    """Collapse whitespace (including nbsp); keep everything else verbatim."""
    return " ".join(raw.replace("\xa0", " ").split())


# ---------------------------------------------------------------------------
# Fetching and response validation
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    url: str
    ok: bool
    data: bytes | None
    reason: str | None
    http_status: int | None
    retrieved_at: str
    content_hash: str | None = None

    def failure_record(self) -> dict[str, Any]:
        return {"url": self.url, "reason": self.reason, "http_status": self.http_status,
                "retrieved_at": self.retrieved_at}


class _RetryableStatus(Exception):
    """A 429/5xx response: worth another attempt."""

    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


def validate_payload(data: bytes, *, expect: str = "html", marker: str | None = None) -> str | None:
    """Return a failure reason, or ``None`` when ``data`` is real content.

    * A PDF must start with ``%PDF``.
    * An HTML page must look like HTML and contain ``marker``.
    * A challenge signal (reCAPTCHA / hCaptcha widget, "are you a robot", a
      WAF vendor) anywhere is ``captcha``. The bare word "captcha" or a block
      message is ``captcha`` only when the content marker is missing: a real
      page may mention a captcha in its text.
    """
    lower = data.lower()
    if any(m in lower for m in CAPTCHA_MARKERS):
        return REASON_CAPTCHA
    if expect == "pdf":
        return None if data.startswith(PDF_MAGIC) else REASON_UNEXPECTED
    if not any(m in lower[:4096] for m in HTML_MARKERS):
        return REASON_UNEXPECTED
    if marker and marker.encode("utf-8").lower() not in lower:
        return REASON_CAPTCHA if any(m in lower for m in BLOCK_MARKERS) else REASON_UNEXPECTED
    return None


def fetch_url(
    url: str,
    session: requests.Session,
    cfg: Mapping[str, Any],
    *,
    marker: str | None,
    expect: str = "html",
    method: str = "GET",
    data: Mapping[str, str] | None = None,
    logger: logging.Logger | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """One request with the P1 retry policy. Never raises for a bad response.

    429 and 5xx are retried; other non-200 statuses are final (``http_<code>``).
    A 200 whose body fails :func:`validate_payload` is a failure too, and its
    body is dropped here so it can never be stored.
    """
    timeout = get_required(cfg, "network.request_timeout_sec")
    status: dict[str, int | None] = {"code": None}

    def attempt() -> bytes:
        response = session.post(url, data=data, timeout=timeout) if method == "POST" \
            else session.get(url, timeout=timeout)
        status["code"] = response.status_code
        if response.status_code == 429 or response.status_code >= 500:
            raise _RetryableStatus(response.status_code)
        return response.content if response.status_code == 200 else b""

    retrieved_at = utc_now()
    try:
        body = retry_call(attempt, policy=RetryPolicy.from_config(cfg),
                          retry_on=(requests.exceptions.RequestException, _RetryableStatus),
                          description=f"{method} {url}", sleep_fn=sleep_fn, logger=logger)
    except Exception as exc:  # RetryExhaustedError: classify its last cause
        cause = getattr(exc, "last_exception", None) or exc.__cause__ or exc
        if isinstance(cause, _RetryableStatus):
            reason = f"http_{cause.status}"
        elif isinstance(cause, requests.exceptions.Timeout):
            reason = REASON_TIMEOUT
        else:
            reason = REASON_CONNECTION
        return FetchResult(url, False, None, reason, status["code"], retrieved_at)
    if status["code"] != 200:
        return FetchResult(url, False, None, f"http_{status['code']}", status["code"], retrieved_at)
    reason = validate_payload(body, expect=expect, marker=marker)
    if reason:
        if logger:
            logger.warning("rejected %s: %s", url, reason)
        return FetchResult(url, False, None, reason, status["code"], retrieved_at)
    return FetchResult(url, True, body, None, status["code"], retrieved_at, sha256_bytes(body))


def aspnet_form(html: bytes | str) -> dict[str, str]:
    """The hidden inputs an ASP.NET listing needs for its year/month POST."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    return {i["name"]: i.get("value", "") for i in soup.find_all("input") if i.get("name")}


# ---------------------------------------------------------------------------
# Per-source storage
# ---------------------------------------------------------------------------


class SourceStore:
    """``data/supplementary/<source>/``: raw pages, fetch manifest, failures, items.

    Only-missing: :meth:`has_good` is true when a manifest entry exists and the
    raw file on disk still hashes to it, so a resumed run never re-fetches or
    overwrites a good record.
    """

    def __init__(self, resolver: PathResolver, source: str, version: str = VERSION):
        self.source = source
        self.version = version
        self.root = resolver.write_dir("supplementary") / source
        self.raw_dir = self.root / "raw"
        self.discovery_dir = self.root / "discovery"
        self.manifest_path = self.root / f"fetch_manifest_{version}.jsonl"
        self.failures_path = self.root / f"failures_{version}.jsonl"
        self.items_path = self.root / f"items_{version}.jsonl"
        self.discovery_path = self.root / f"discovery_{version}.json"
        self._manifest: dict[str, dict[str, Any]] | None = None

    # -- manifest -------------------------------------------------------------
    def manifest(self) -> dict[str, dict[str, Any]]:
        if self._manifest is None:
            self._manifest = {r["item_key"]: r for r in iter_jsonl(self.manifest_path)} \
                if self.manifest_path.is_file() else {}
        return self._manifest

    def raw_path(self, item_key: str, suffix: str = ".html") -> Path:
        return self.raw_dir / f"{item_key}{suffix}"

    def has_good(self, item_key: str) -> bool:
        entry = self.manifest().get(item_key)
        if not entry:
            return False
        path = self.root / entry["raw_path"]
        return path.is_file() and sha256_bytes(path.read_bytes()) == entry["content_hash"]

    def read_raw(self, item_key: str) -> bytes:
        return (self.root / self.manifest()[item_key]["raw_path"]).read_bytes()

    def save(self, item_key: str, result: FetchResult, extra: Mapping[str, Any] | None = None,
             suffix: str = ".html") -> dict[str, Any]:
        if not result.ok or result.data is None:
            raise SupplementaryError(f"refusing to store a failed fetch for {item_key}: {result.reason}")
        path = self.raw_path(item_key, suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.data)
        entry = {"item_key": item_key, "url": result.url, "retrieved_at": result.retrieved_at,
                 "content_hash": result.content_hash, "http_status": result.http_status,
                 "raw_path": path.relative_to(self.root).as_posix(), **dict(extra or {})}
        self.manifest()[item_key] = entry
        self.flush_manifest()
        return entry

    def flush_manifest(self) -> None:
        write_jsonl(self.manifest_path, [self.manifest()[k] for k in sorted(self.manifest())])

    # -- discovery pages --------------------------------------------------------
    def save_discovery_page(self, name: str, result: FetchResult) -> dict[str, Any]:
        path = self.discovery_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.data or b"")
        return {"page": name, "url": result.url, "retrieved_at": result.retrieved_at,
                "content_hash": result.content_hash}

    # -- failures ---------------------------------------------------------------
    def failures(self) -> list[dict[str, Any]]:
        return list(iter_jsonl(self.failures_path)) if self.failures_path.is_file() else []

    def record_failures(self, records: Iterable[Mapping[str, Any]]) -> None:
        rows = self.failures() + [dict(r) for r in records]
        write_jsonl(self.failures_path, rows)

    def write_items(self, items: Sequence[Mapping[str, Any]]) -> Path:
        for item in items:
            check_item(item)
        return write_jsonl(self.items_path, sorted(items, key=lambda r: r["item_id"]))

    def write_discovery(self, info: Mapping[str, Any]) -> Path:
        return write_json(self.discovery_path, info)


# ---------------------------------------------------------------------------
# Item schema (§P)
# ---------------------------------------------------------------------------


def make_item(*, item_id: str, source: str, source_url: str, retrieved_at: str | None, content_hash: str | None,
              published_date: str | None, title: str, text: str, fields: Mapping[str, Any],
              cited_directions: Sequence[str], entity_class: str | None, cutoff: date) -> dict[str, Any]:
    item = {
        "item_id": item_id, "source": source, "source_url": source_url, "retrieved_at": retrieved_at,
        "content_hash": content_hash, "published_date": published_date, "title": title, "text": text,
        "fields": dict(fields), "cited_directions": list(dict.fromkeys(cited_directions)),
        "entity_class": entity_class, "era": era_of(published_date, cutoff),
    }
    check_item(item)
    return item


def check_item(item: Mapping[str, Any]) -> None:
    if tuple(item) != ITEM_FIELDS:
        raise SupplementaryError(f"item fields {tuple(item)} != {ITEM_FIELDS}")
    if item["source"] not in SOURCES:
        raise SupplementaryError(f"unknown source {item['source']!r}")
    if item["era"] not in (ERA_PRE, ERA_POST, ERA_UNKNOWN):
        raise SupplementaryError(f"bad era {item['era']!r}")


@dataclass
class HarvestContext:
    """Everything an adapter's ``discover`` / ``fetch`` needs. Tests pass a fake session and a no-op sleep."""

    cfg: Mapping[str, Any]
    sc: SupplementaryConfig
    resolver: PathResolver
    session: Any
    logger: logging.Logger
    sleep_fn: Callable[[float], None] = time.sleep
    _last_request: list[float] = field(default_factory=list)

    def get(self, url: str, *, marker: str | None, expect: str = "html", method: str = "GET",
            data: Mapping[str, str] | None = None) -> FetchResult:
        """:func:`fetch_url` with the polite rate limit between successive requests."""
        if self._last_request:
            self.sleep_fn(self.sc.rate_limit_sec)
        self._last_request[:] = [time.monotonic()]
        return fetch_url(url, self.session, self.cfg, marker=marker, expect=expect, method=method, data=data,
                         logger=self.logger, sleep_fn=self.sleep_fn)

    def store(self, source: str) -> SourceStore:
        return SourceStore(self.resolver, source, self.sc.version)


def fetch_items(ctx: HarvestContext, source: str, targets: Sequence[Mapping[str, Any]], *, marker: str | None,
                limit: int | None = None) -> dict[str, Any]:
    """Fetch discovered items not already stored (only-missing). Returns counts by outcome and reason.

    The source stops early (§R) once ``STOP_MIN_ATTEMPTS`` fetches ran and the
    failure rate reached ``max_failure_rate``; the summary says so in ``stopped``.

    ``targets`` rows carry ``item_key`` and ``url``; every other key is kept
    in the manifest as listing metadata. A failed item is logged to the
    failure file and never stored.
    """
    store = ctx.store(source)
    todo = [t for t in targets if not store.has_good(t["item_key"])]
    skipped = len(targets) - len(todo)
    if limit is not None:
        todo = todo[:limit]
    ok, failures, attempted, stopped = 0, [], 0, None
    for t in todo:
        res = ctx.get(t["url"], marker=marker)
        attempted += 1
        if res.ok:
            store.save(t["item_key"], res, {k: v for k, v in t.items() if k not in ("item_key", "url")})
            ok += 1
        else:
            failures.append({**res.failure_record(), "item_key": t["item_key"]})
        if attempted >= STOP_MIN_ATTEMPTS and len(failures) / attempted >= ctx.sc.max_failure_rate:
            stopped = (f"stopped after {attempted} attempts: failure rate {len(failures) / attempted:.0%} "
                       f">= {ctx.sc.max_failure_rate:.0%}")
            ctx.logger.error("fetch %s %s", source, stopped)
            break
    store.record_failures(failures)
    reasons: dict[str, int] = {}
    for f in failures:
        reasons[f["reason"]] = reasons.get(f["reason"], 0) + 1
    summary = {"source": source, "targets": len(targets), "already_stored": skipped, "attempted": attempted,
               "fetched": ok, "failed": len(failures), "failure_reasons": dict(sorted(reasons.items())),
               "failure_rate": round(len(failures) / attempted, 4) if attempted else 0.0, "stopped": stopped}
    ctx.logger.info("fetch %s: %s", source, summary)
    return summary
