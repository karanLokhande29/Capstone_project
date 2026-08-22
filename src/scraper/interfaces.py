"""Corpus acquisition interfaces — implemented by ``phase1/akash-scraper``.

Signatures only. Every function here raises :class:`NotImplementedError`; the
point of the file is to fix the boundary between acquisition and everything
downstream before three people start writing against it.

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
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"discover_documents is implemented by {BRANCH}")


def download_document(record: DocumentRecord, cfg: Mapping[str, Any], **kwargs: Any) -> DocumentRecord:
    """Fetch one document's payload and return the record with payload fields filled.

    Must populate ``local_path``, ``content_hash``, ``format`` and
    ``retrieved_at``, and must validate that the payload is the format it claims
    to be before caching it.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"download_document is implemented by {BRANCH}")


def harvest_corpus(cfg: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Run discovery and download end to end, returning discovered metrics.

    Every count in the returned mapping must be measured from this run. Values
    that could not be measured are reported as the string ``"NOT YET MEASURED"``
    rather than zero, and failures as ``"FAILED — <reason>"``.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"harvest_corpus is implemented by {BRANCH}")


def write_manifest(records: Iterable[DocumentRecord], cfg: Mapping[str, Any]) -> str:
    """Persist the corpus manifest and return the path written.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/akash-scraper``.
    """
    raise NotImplementedError(f"write_manifest is implemented by {BRANCH}")
