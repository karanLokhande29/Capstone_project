"""P1-004: consistency checks that must hold across a corpus repair.

The repair re-segments the whole corpus, including the 299 documents that were
already fine. That is the right thing to do — segmenting 299 documents with
one version of the segmenter and 81 with another would leave a corpus whose
paragraph boundaries depend on when a document happened to be downloaded — but
it puts every existing `paragraph_id` at risk, and two things are pinned to
those ids:

* the 18 pilot `ObligationSpan`s, which store ``paragraph_id`` plus character
  offsets. If a paragraph's text shifts by one character, the span silently
  points at different words and three people's annotation work is quietly
  invalidated rather than loudly broken.
* the Subject x Entity-Class matrix, which joins on document and paragraph.

So the repair asserts, rather than hopes, that re-segmentation changed nothing
for the documents whose input did not change. Both checks below are hard
stops: a corpus that fails them must not be published, because the damage is
invisible in every downstream metric — the paragraph counts still look right.

Fingerprints are **text-free**: a SHA-256 of each paragraph's text, never the
text. The file can therefore be committed and compared without redistributing
RBI material (R6).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.common.errors import FoundationError
from src.common.io_helpers import read_jsonl, write_json
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver

BRANCH = "phase1/meer-annotation"

FINGERPRINTS_BEFORE = "p1004_paragraph_fingerprints_before.json"


class ConsistencyError(FoundationError):
    """A repair changed something it was required to leave alone."""


def _fingerprint(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def paragraph_fingerprints(resolver: PathResolver) -> dict[str, list[list[str]]]:
    """``document_id -> [[paragraph_id, sha256(text)], ...]``, text-free."""
    processed = Path(resolver.write_dir("processed", create=False))
    out: dict[str, list[list[str]]] = {}
    for path in sorted(processed.glob("md_*.jsonl")):
        for row in read_jsonl(path):
            doc = row.get("document_id") or path.stem
            out.setdefault(doc, []).append(
                [row.get("paragraph_id") or "", _fingerprint(row.get("text"))]
            )
    return out


def write_fingerprints(
    resolver: PathResolver, *, filename: str = FINGERPRINTS_BEFORE,
    logger: logging.Logger | None = None,
) -> str:
    """Snapshot the current segmentation, to compare against after the repair."""
    logger = logger or get_logger("preprocessing.consistency", {})
    prints = paragraph_fingerprints(resolver)
    path = resolver.write_path("metadata", filename)
    write_json(path, prints)
    logger.info(
        "consistency: fingerprinted %d document(s), %d paragraph(s) -> %s",
        len(prints), sum(len(v) for v in prints.values()), path,
    )
    return str(path)


def check_stable_ids(
    resolver: PathResolver,
    *,
    filename: str = FINGERPRINTS_BEFORE,
    logger: logging.Logger | None = None,
    raise_on_drift: bool = True,
) -> dict[str, Any]:
    """Every previously-segmented document must come back byte-identical.

    Only documents present in the *before* snapshot are checked: the repaired
    corpus gains documents, and a new one having no prior fingerprint is the
    expected case, not drift.
    """
    logger = logger or get_logger("preprocessing.consistency", {})
    path = resolver.find_read_path("metadata", filename)
    if path is None:
        return {
            "status": "NOT YET MEASURED — no before-snapshot exists",
            "documents_checked": 0,
            "passed": None,
        }

    before = json.loads(Path(path).read_text(encoding="utf-8"))
    after = paragraph_fingerprints(resolver)

    drift: list[dict[str, str]] = []
    missing_documents: list[str] = []

    for doc_id, rows in sorted(before.items()):
        if doc_id not in after:
            missing_documents.append(doc_id)
            continue
        now = {pid: fp for pid, fp in after[doc_id]}
        for pid, fp in rows:
            if pid not in now:
                drift.append({"document_id": doc_id, "paragraph_id": pid,
                              "problem": "paragraph disappeared after re-segmentation"})
            elif now[pid] != fp:
                drift.append({"document_id": doc_id, "paragraph_id": pid,
                              "problem": "paragraph text changed after re-segmentation"})

    result = {
        "documents_checked": len(before),
        "paragraphs_checked": sum(len(v) for v in before.values()),
        "documents_missing_after": missing_documents,
        "drift": drift[:50],
        "drift_count": len(drift),
        "passed": not drift and not missing_documents,
    }

    if not result["passed"]:
        first = (drift or [{"document_id": d, "paragraph_id": "-",
                            "problem": "document disappeared"} for d in missing_documents])[0]
        message = (
            f"stable-ID check FAILED: {len(drift)} paragraph(s) changed and "
            f"{len(missing_documents)} document(s) vanished after re-segmentation. First: "
            f"{first['document_id']} / {first['paragraph_id']} — {first['problem']}. "
            "Existing annotations and the matrix join on these ids, so the corpus must not "
            "be published until this is explained."
        )
        logger.error("consistency: %s", message)
        if raise_on_drift:
            raise ConsistencyError(message)
    else:
        logger.info(
            "consistency: stable-ID check passed — %d document(s), %d paragraph(s) identical",
            result["documents_checked"], result["paragraphs_checked"],
        )
    return result


def check_pilot_join(
    resolver: PathResolver,
    *,
    candidates_filename: str = "pilot_candidates.jsonl",
    logger: logging.Logger | None = None,
    raise_on_break: bool = True,
) -> dict[str, Any]:
    """Every pilot span must still resolve to the same paragraph and text.

    The check the annotation work depends on. A span stores offsets into a
    paragraph, so it is only meaningful while that paragraph's text is
    unchanged; if it shifts, the span still "resolves" and returns different
    words, which no count of paragraphs or documents would reveal.
    """
    logger = logger or get_logger("preprocessing.consistency", {})
    candidates_path = resolver.find_read_path("benchmark", candidates_filename)
    if candidates_path is None:
        return {
            "status": "NOT YET MEASURED — no pilot candidates on this machine",
            "spans_checked": 0,
            "passed": None,
        }

    paragraphs: dict[str, str] = {}
    processed = Path(resolver.write_dir("processed", create=False))
    for path in sorted(processed.glob("md_*.jsonl")):
        for row in read_jsonl(path):
            if row.get("paragraph_id"):
                paragraphs[row["paragraph_id"]] = row.get("text") or ""

    broken: list[dict[str, str]] = []
    checked = 0
    for row in read_jsonl(Path(candidates_path)):
        span = row.get("obligation_span") or {}
        pid = span.get("paragraph_id")
        if not pid:
            continue
        checked += 1
        text = paragraphs.get(pid)
        if text is None:
            broken.append({"label_id": row.get("label_id", "?"), "paragraph_id": pid,
                           "problem": "paragraph no longer exists"})
            continue
        start, end = span.get("char_start"), span.get("char_end")
        expected = (span.get("text") or "").strip()
        if not isinstance(start, int) or not isinstance(end, int) or end > len(text):
            broken.append({"label_id": row.get("label_id", "?"), "paragraph_id": pid,
                           "problem": f"offsets {start}:{end} fall outside a {len(text)}-char paragraph"})
            continue
        if expected and text[start:end].strip() != expected:
            broken.append({"label_id": row.get("label_id", "?"), "paragraph_id": pid,
                           "problem": "the text at those offsets is no longer the annotated span"})

    result = {
        "spans_checked": checked,
        "broken": broken[:50],
        "broken_count": len(broken),
        "passed": not broken,
    }

    if broken:
        message = (
            f"pilot-join check FAILED: {len(broken)} of {checked} pilot span(s) no longer "
            f"resolve. First: {broken[0]['label_id']} — {broken[0]['problem']}. Three "
            "people's annotations are keyed to these spans, so the repaired corpus must "
            "not replace the old one until this is explained."
        )
        logger.error("consistency: %s", message)
        if raise_on_break:
            raise ConsistencyError(message)
    else:
        logger.info("consistency: pilot-join check passed — %d span(s) still resolve", checked)
    return result
