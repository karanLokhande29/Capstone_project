"""Corpus acquisition interfaces — implemented by ``phase1/akash-scraper``.

Signatures only. Every function here raises :class:`NotImplementedError`; the
point of the file is to fix the boundary between acquisition and everything
downstream before three people start writing against it.

**Implementation note (P1-001).** This file is left as literal stubs
deliberately, even though ``phase1/akash-scraper`` has now implemented the real
functionality — it lives in :mod:`src.scraper.rbi_scraper` instead. Reason:
``tests/test_smoke.py`` (Phase 0, base-owned, outside this branch's file scope)
asserts every function in every ``*.interfaces`` module still raises
``NotImplementedError`` naming its branch — that assertion is exactly what
protected all three branches' interface stubs from a broken import during
Phase 0, but it also means un-stubbing this file would fail a base-owned test
this branch has no authority to change. Import the real implementation from
:mod:`src.scraper.rbi_scraper` directly. Superseding this file (or updating the
base smoke test's expectations) is a base-branch decision for whoever
integrates all three Phase 1 branches, not something to resolve unilaterally
from one branch.

Implementation notes for the branch owner:

* Use :func:`src.common.retry.retry_call` for every network call rather than a
  local retry loop, so backoff behaviour is uniform and configurable.
* Use :class:`src.common.cache.ArtifactCache` for downloaded payloads. On Kaggle
  this reads previously-harvested documents from an attached Dataset and writes
  new ones to ``/kaggle/working``, which makes a re-run cheap instead of a
  second full harvest.
* Validate payloads before caching them. A bot-challenge HTML page saved under a
  ``.pdf`` name is a cache hit forever after, and is far more expensive to
  detect later than at download time.
* Never construct paths by hand — resolve keys through
  :class:`src.common.paths.PathResolver`.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from src.schemas.provenance import DocumentRecord

BRANCH = "phase1/akash-scraper"


def discover_documents(cfg: Mapping[str, Any], **kwargs: Any) -> list[DocumentRecord]:
    """Enumerate source documents without downloading them.

    Discovery is separated from download so the corpus inventory is established
    and reviewable before any bytes are fetched, and so a download failure never
    silently shrinks the recorded corpus size.

    Returns:
        One :class:`DocumentRecord` per discovered document, with the
        ``*_raw`` provenance fields populated and payload fields left null.

    Raises:
        NotImplementedError: Always. See :func:`src.scraper.rbi_scraper.discover_documents`
            for the real implementation.
    """
    raise NotImplementedError(
        f"discover_documents is implemented by {BRANCH}; see src.scraper.rbi_scraper.discover_documents"
    )


def download_document(record: DocumentRecord, cfg: Mapping[str, Any], **kwargs: Any) -> DocumentRecord:
    """Fetch one document's payload and return the record with payload fields filled.

    Must populate ``local_path``, ``content_hash``, ``format`` and
    ``retrieved_at``, and must validate that the payload is the format it claims
    to be before caching it.

    Raises:
        NotImplementedError: Always. See :func:`src.scraper.rbi_scraper.download_document`
            for the real implementation.
    """
    raise NotImplementedError(
        f"download_document is implemented by {BRANCH}; see src.scraper.rbi_scraper.download_document"
    )


def harvest_corpus(cfg: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Run discovery and download end to end, returning discovered metrics.

    Every count in the returned mapping must be measured from this run. Values
    that could not be measured are reported as the string ``"NOT YET MEASURED"``
    rather than zero, and failures as ``"FAILED — <reason>"``.

    Raises:
        NotImplementedError: Always. See :func:`src.scraper.rbi_scraper.harvest_corpus`
            for the real implementation.
    """
    raise NotImplementedError(
        f"harvest_corpus is implemented by {BRANCH}; see src.scraper.rbi_scraper.harvest_corpus"
    )


def write_manifest(records: Iterable[DocumentRecord], cfg: Mapping[str, Any]) -> str:
    """Persist the corpus manifest and return the path written.

    Raises:
        NotImplementedError: Always. See :func:`src.scraper.rbi_scraper.write_manifest`
            for the real implementation.
    """
    raise NotImplementedError(
        f"write_manifest is implemented by {BRANCH}; see src.scraper.rbi_scraper.write_manifest"
    )
