"""Entity-class and subject-family vocabulary discovery and normalization.

Implements the design fixed by :mod:`src.metadata.interfaces`
(``discover_vocabulary``, ``normalise_documents``, ``persist_vocabularies``).
Real logic lives here rather than in ``interfaces.py`` for the same reason as
``phase1/akash-scraper``'s ``rbi_scraper.py``: ``tests/test_smoke.py``
(Phase 0, base-owned) asserts every ``interfaces.py`` function still raises
``NotImplementedError`` naming its branch, so un-stubbing that file would fail
a test this branch has no authority to change.

Two vocabularies, two very different discovery methods
--------------------------------------------------------

**Entity class** is a direct, 1:1 construction from ``entity_class_raw``: the
RBI listing's category headings are already clean, mutually distinct strings
(verified against the full 380-document corpus — zero normalised-key
collisions), so each raw value becomes its own :class:`VocabularyTerm` with no
alias resolution needed. The code still runs collision detection rather than
assuming this holds, so a future corpus with genuinely messy entity-class
strings degrades to reported ambiguity instead of a silent wrong merge.

**Subject family** has no raw source at all — confirmed empirical fact, not an
assumption: `subject_family_raw` is null for all 380 documents, because the
RBI listing page has no subject/topic column (see
`src.scraper.rbi_scraper`'s module docstring, which investigated this during
Phase 1). Akash's own hand-off explicitly named the fallback: "Subject-family
construction is left to phase1/karan-matrix, which can work from paragraph
text." This module implements the simplest version of that which is still
fully mechanical rather than an invented semantic judgment: RBI titles
follow the pattern ``Reserve Bank of India (<entity class> – <subject>)
Directions, <year>``, so the *already-known* `entity_class_raw` string can be
matched and stripped out of the title, leaving the subject as a residual.

This is deliberately **not** NLP or topic modeling — it is not free-text
subject-family invention, it is a structural transformation of two fields
Akash already discovered (`entity_class_raw`, `title`), using string matching
alone. It is also not the same mistake as the pre-Phase-0 implementation
(documented in `src.scraper.rbi_scraper`'s module docstring), which split on
a bare dash character with no verification and truncated names like "Urban
Co-operative Banks" to "Urban Co" — this module only ever removes the
*exact*, *already-verified* `entity_class_raw` string, matched on a word
boundary so it cannot slice into a longer word (e.g. "Financial Market"
inside "Financial Markets" — hit and fixed while validating this against the
real corpus).

A title where the entity-class substring cannot be found at all — the
"Internal Ombudsman" directions are the clearest real example, filed under
the `entity_class_raw` "Consumer Education and Protection" while their titles
name a *different* entity class ("Commercial Banks - Internal Ombudsman")
because the ombudsman rule applies to that class, not the filing category —
is recorded as **unresolved**, never force-matched. Validated against the
real 380-document corpus: 304 resolved into 56 distinct subject-family terms
(zero normalised-key collisions — no alias merging needed there either), 76
honestly unresolved (~20%).
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any, Iterable, Mapping

from src.common.io_helpers import write_json
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.schemas.provenance import DocumentRecord, ParagraphRecord
from src.schemas.vocabulary import (
    ENTITY_CLASS,
    SUBJECT_FAMILY,
    Vocabulary,
    VocabularyTerm,
    empty_entity_class_vocabulary,
    empty_subject_family_vocabulary,
    normalise_term,
)

BRANCH = "phase1/karan-matrix"

# -- provenance markers (P1-002-CORRECTIVE) ----------------------------------
#
# `VocabularyTerm.source` carries a machine-readable provenance prefix so a
# downstream consumer can separate "harvested from a raw field and normalised"
# from "inferred from the title" **from the data itself**, without reading any
# docstring. The prose explanation lives in `.notes`; `.source` stays greppable.
#
#     grep '"source": "derived:' data/metadata/subject_families.json
#
PROVENANCE_RAW = "raw"
PROVENANCE_DERIVED = "derived"
#: A term whose aliases came from BOTH a raw field and a derivation. Does not
#: occur in the current corpus (asserted by a test); see `term_provenance`.
PROVENANCE_MIXED = "mixed"

#: entity_class comes straight from a real harvested field (`entity_class_raw`).
ENTITY_SOURCE = f"{PROVENANCE_RAW}:rbi_listing_entity_class_heading"
ENTITY_SOURCE_NOTES = (
    "Harvested verbatim from the RBI Master Directions listing's entity-class "
    "heading (BS_ViewMasDirections.aspx) via DocumentRecord.entity_class_raw, "
    "then normalised 1:1 (no aliasing needed for this corpus)."
)

#: subject_family has NO raw source field — see the module docstring and the
#: dated finding in reports/phase1_karan_matrix.md. Every subject_family term
#: is INFERRED from the title, and is marked as such here.
SUBJECT_SOURCE = f"{PROVENANCE_DERIVED}:title_strip_entity_class"
SUBJECT_SOURCE_NOTES = (
    "DERIVED, not harvested: DocumentRecord.subject_family_raw is null for "
    "every document in this corpus (RBI's listing carries no subject-family "
    "taxonomy). This term was inferred by removing the known entity_class_raw "
    "string from DocumentRecord.title on a word boundary and stripping "
    "RBI/Directions/date boilerplate from the residual. Treat as inferred "
    "metadata, not as RBI's own classification."
)


def term_provenance(term: VocabularyTerm) -> str:
    """Return `"raw"`, `"derived"`, or `"mixed"` for a term's `source` marker.

    `"mixed"` is returned when a term's source carries neither recognised
    prefix cleanly — the honest label for a term whose provenance cannot be
    resolved to a single origin, rather than silently picking one (the same
    "record, don't force-match" rule this module applies to unresolved
    surface forms).
    """
    source = (term.source or "").strip()
    if source.startswith(f"{PROVENANCE_RAW}:"):
        return PROVENANCE_RAW
    if source.startswith(f"{PROVENANCE_DERIVED}:"):
        return PROVENANCE_DERIVED
    return PROVENANCE_MIXED

# -- subject-family title-residual extraction --------------------------------

_UPDATED_RE = re.compile(r"\(\s*Updated\s+as\s+on\s+[^)]*\)", re.IGNORECASE)
_TRAILING_YEAR_RE = re.compile(r"\bDirections?,?\s*\d{4}\b", re.IGNORECASE)
_RBI_PREFIX_RE = re.compile(
    r"^\s*(Master\s+Directions?\s*[-–—]?\s*)?(Reserve\s+Bank\s+of\s+India\b\s*[-–—]?)?",
    re.IGNORECASE,
)
_EDGE_PUNCT = " -–—()[]:,."


def extract_subject_residual(title: str | None, entity_class_raw: str | None) -> str | None:
    """Derive a subject-family candidate by removing `entity_class_raw` from `title`.

    Returns `None` when `entity_class_raw` cannot be found in `title` on a word
    boundary — never a guessed or partial match. Two structural forms are
    tried, in order:

    1. ``(<entity_class_raw> – <subject>)`` / ``[<entity_class_raw> ... <subject>]``
       — the common case, captured directly so the closing bracket is
       consumed with it (an earlier version of this function stripped the
       substring and cleaned up brackets in a separate pass, which left
       orphaned ``)`` characters stranded mid-string whenever trailing text
       followed the parenthetical, e.g. "... – Miscellaneous) Supervisory
       Directions" — fixed by matching the whole bracket structure at once).
    2. A bare word-boundary match, when the structural form isn't present.

    Both matches require `entity_class_raw` to end at a word boundary, so
    "Financial Market" cannot match as a prefix of "Financial Markets" inside
    a title — hit and fixed while validating this function against the real
    corpus (`md_13343`, "Unique Identifiers in Financial Markets").
    """
    if not title or not entity_class_raw:
        return None

    text = _UPDATED_RE.sub("", title)
    escaped = re.escape(entity_class_raw)

    structural = re.search(
        rf"[\(\[]\s*{escaped}\b\s*[-–—]\s*(?P<subject>[^)\]]+?)\s*[\)\]]", text, re.IGNORECASE
    )
    if structural:
        residual = structural.group("subject")
    else:
        word_match = re.search(rf"\b{escaped}\b", text, re.IGNORECASE)
        if not word_match:
            return None
        residual = text[: word_match.start()] + text[word_match.end() :]

    residual = _TRAILING_YEAR_RE.sub("", residual)
    residual = _RBI_PREFIX_RE.sub("", residual)
    residual = re.sub(r"\s+", " ", residual).strip(_EDGE_PUNCT).strip()
    return residual or None


# -- vocabulary discovery ------------------------------------------------


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "term"


def _add_or_extend(vocab: Vocabulary, term_id: str, canonical_name: str, surface: str, *, source: str,
                    notes: str, first_seen_document_id: str, kind: str, logger: logging.Logger) -> VocabularyTerm:
    """Add a new term, or extend an existing one's aliases/count if `surface`
    already resolves there. Collision-safe: if `surface`'s normalised key
    already belongs to a *different* term, this raises inside `Vocabulary.add`
    rather than silently merging — the caller decides how to handle that.

    If an existing term is extended with a surface form carrying a *different*
    provenance than the term already has, the term's provenance is downgraded
    to `PROVENANCE_MIXED` and logged as a warning rather than keeping whichever
    label happened to land first (Section R: record the ambiguity, don't
    force-match). This does not occur in the current corpus.
    """
    existing = vocab.resolve(surface)
    if existing is not None:
        if surface not in existing.surface_forms():
            existing.aliases.append(surface)
            logger.info(
                "vocabulary: %s alias added to %r: %r (from %s)",
                kind, existing.canonical_name, surface, first_seen_document_id,
            )
        if existing.source != source:
            logger.warning(
                "vocabulary: %s term %r has MIXED provenance — existing source %r, "
                "incoming source %r (from %s). Recording as %r rather than choosing one.",
                kind, existing.canonical_name, existing.source, source,
                first_seen_document_id, PROVENANCE_MIXED,
            )
            existing.source = f"{PROVENANCE_MIXED}:{existing.source}|{source}"
            existing.notes = (
                f"{existing.notes or ''} MIXED PROVENANCE: this term's surface forms came "
                f"from more than one origin; see source field."
            ).strip()
        existing.occurrence_count = (existing.occurrence_count or 0) + 1
        return existing

    term = VocabularyTerm(
        term_id=term_id,
        canonical_name=canonical_name,
        kind=kind,
        source=source,
        notes=notes,
        first_seen_document_id=first_seen_document_id,
        occurrence_count=1,
    )
    vocab.add(term)
    logger.info(
        "vocabulary: new %s term %r (term_id=%s, provenance=%s, source=%r, first seen %s)",
        kind, canonical_name, term_id, term_provenance(term), source, first_seen_document_id,
    )
    return term


def discover_entity_class_vocabulary(
    records: Iterable[DocumentRecord], cfg: Mapping[str, Any], *, logger: logging.Logger | None = None
) -> tuple[Vocabulary, list[str]]:
    """Discover the entity-class vocabulary from `entity_class_raw` values.

    Returns `(vocabulary, unresolved_document_ids)` — `unresolved` holds
    document_ids with a null `entity_class_raw` (none in the corpus this was
    built against, but a real, checked case rather than an assumption).
    """
    logger = logger or get_logger("metadata.vocabulary", cfg)
    vocab = empty_entity_class_vocabulary()
    unresolved: list[str] = []

    for record in records:
        raw = record.entity_class_raw
        if not raw:
            unresolved.append(record.document_id)
            continue
        term_id = f"ec_{_slug(raw)}"
        try:
            _add_or_extend(
                vocab, term_id, raw, raw,
                source=ENTITY_SOURCE, notes=ENTITY_SOURCE_NOTES,
                first_seen_document_id=record.document_id,
                kind=ENTITY_CLASS, logger=logger,
            )
        except Exception as exc:  # noqa: BLE001 - a genuine collision is a finding, not a crash
            logger.warning("vocabulary: entity_class collision on %r (%s): %s", raw, record.document_id, exc)
            unresolved.append(record.document_id)

    logger.info(
        "discover_entity_class_vocabulary: %d terms discovered, %d documents unresolved",
        len(vocab), len(unresolved),
    )
    return vocab, unresolved


def discover_subject_family_vocabulary(
    records: Iterable[DocumentRecord], cfg: Mapping[str, Any], *, logger: logging.Logger | None = None
) -> tuple[Vocabulary, list[dict[str, str]]]:
    """Discover the subject-family vocabulary via title-residual extraction.

    Returns `(vocabulary, unresolved)` where `unresolved` is a list of
    ``{"document_id", "entity_class_raw", "title", "reason"}`` dicts — kept
    detailed (not just IDs) because the whole point of recording unresolved
    cases is that they are queryable evidence of normalisation coverage, not
    a discard pile.
    """
    logger = logger or get_logger("metadata.vocabulary", cfg)
    vocab = empty_subject_family_vocabulary()
    unresolved: list[dict[str, str]] = []

    for record in records:
        residual = extract_subject_residual(record.title, record.entity_class_raw)
        if residual is None:
            reason = (
                "no title" if not record.title
                else "no entity_class_raw" if not record.entity_class_raw
                else "entity_class_raw not found in title on a word boundary"
            )
            unresolved.append(
                {
                    "document_id": record.document_id,
                    "entity_class_raw": record.entity_class_raw or "",
                    "title": record.title or "",
                    "reason": reason,
                }
            )
            continue

        term_id = f"sf_{_slug(residual)}"
        try:
            _add_or_extend(
                vocab, term_id, residual, residual,
                source=SUBJECT_SOURCE, notes=SUBJECT_SOURCE_NOTES,
                first_seen_document_id=record.document_id,
                kind=SUBJECT_FAMILY, logger=logger,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("vocabulary: subject_family collision on %r (%s): %s", residual, record.document_id, exc)
            unresolved.append(
                {
                    "document_id": record.document_id,
                    "entity_class_raw": record.entity_class_raw or "",
                    "title": record.title or "",
                    "reason": f"normalisation collision: {exc}",
                }
            )

    logger.info(
        "discover_subject_family_vocabulary: %d terms discovered, %d documents unresolved",
        len(vocab), len(unresolved),
    )
    return vocab, unresolved


def discover_vocabulary(
    records: Iterable[DocumentRecord], kind: str, cfg: Mapping[str, Any], **kwargs: Any
) -> Vocabulary:
    """Dispatch to the appropriate discovery method for `kind`.

    Matches the signature :mod:`src.metadata.interfaces` declares. Prefer
    calling :func:`discover_entity_class_vocabulary` /
    :func:`discover_subject_family_vocabulary` directly when the unresolved
    list is also needed — this wrapper discards it.
    """
    records = list(records)
    if kind == ENTITY_CLASS:
        vocab, _ = discover_entity_class_vocabulary(records, cfg, **kwargs)
        return vocab
    if kind == SUBJECT_FAMILY:
        vocab, _ = discover_subject_family_vocabulary(records, cfg, **kwargs)
        return vocab
    raise ValueError(f"discover_vocabulary: unknown kind {kind!r}")


# -- normalization ---------------------------------------------------------


def normalise_documents(
    records: Iterable[DocumentRecord],
    entity_vocab: Vocabulary,
    subject_vocab: Vocabulary,
    **kwargs: Any,
) -> list[DocumentRecord]:
    """Resolve each record's raw surface forms onto the vocabularies.

    Returns new records (`entity_class_raw`/`subject_family_raw` untouched —
    `replace()` is used specifically so the original is never mutated) with
    `entity_class`/`subject_family` populated where resolution succeeded.
    """
    results: list[DocumentRecord] = []
    for record in records:
        entity_term = entity_vocab.resolve(record.entity_class_raw) if record.entity_class_raw else None
        subject_residual = extract_subject_residual(record.title, record.entity_class_raw)
        subject_term = subject_vocab.resolve(subject_residual) if subject_residual else None
        results.append(
            replace(
                record,
                entity_class=entity_term.canonical_name if entity_term else None,
                subject_family=subject_term.canonical_name if subject_term else None,
            )
        )
    return results


def normalise_paragraphs(
    paragraphs: Iterable[ParagraphRecord], document_lookup: Mapping[str, DocumentRecord]
) -> list[ParagraphRecord]:
    """Propagate each paragraph's parent document's normalised classes onto it.

    `document_lookup` must map document_id -> the *normalised* DocumentRecord
    (i.e. one already passed through :func:`normalise_documents`).
    """
    results: list[ParagraphRecord] = []
    for paragraph in paragraphs:
        parent = document_lookup.get(paragraph.document_id)
        results.append(
            replace(
                paragraph,
                entity_class=parent.entity_class if parent else None,
                subject_family=parent.subject_family if parent else None,
            )
        )
    return results


# -- provenance queries (P1-002-CORRECTIVE) ----------------------------------


def provenance_counts(vocab: Vocabulary) -> dict[str, int]:
    """Count a vocabulary's terms by provenance: raw / derived / mixed."""
    counts = {PROVENANCE_RAW: 0, PROVENANCE_DERIVED: 0, PROVENANCE_MIXED: 0}
    for term in vocab:
        counts[term_provenance(term)] += 1
    return counts


def provenance_lookup(vocab: Vocabulary) -> dict[str, str]:
    """Map canonical_name -> provenance label, for downstream consumers.

    Persisted alongside the vocabularies so a consumer (e.g. Meer's P1-003
    stratification) can classify a record's `subject_family` value without
    parsing the full vocabulary file — one small dict lookup instead.
    """
    return {term.canonical_name: term_provenance(term) for term in vocab}


def segmented_unresolved_rates(
    records: Iterable[DocumentRecord],
    entity_unresolved: Iterable[str],
    subject_unresolved: Iterable[Mapping[str, str]],
) -> dict[str, Any]:
    """Split the unresolved-surface-form rate by raw-sourced vs derived origin.

    P1-002 reported a single combined subject-family unresolved rate
    (76/380). That number conflates two very different things, so this
    separates them:

    * **entity_class** resolves from a genuinely harvested field
      (`entity_class_raw`), so its unresolved rate measures real
      normalisation difficulty.
    * **subject_family** has no raw field at all, so *every* value is
      derived and its unresolved rate measures the reach of the derivation
      method, not normalisation difficulty.

    The raw-sourced subject-family rate is therefore reported as
    ``"NOT MEASURABLE"`` rather than ``0.0`` when no raw values exist —
    reporting 0% would imply raw values were examined and found clean, when
    in fact there were none to examine.
    """
    records = list(records)
    total = len(records)
    entity_unresolved = list(entity_unresolved)
    subject_unresolved = list(subject_unresolved)

    raw_sourced_subject = sum(1 for r in records if r.subject_family_raw)
    raw_sourced_entity = sum(1 for r in records if r.entity_class_raw)

    if raw_sourced_subject:
        unresolved_raw_subject = sum(
            1 for u in subject_unresolved
            if any(r.document_id == u["document_id"] and r.subject_family_raw for r in records)
        )
        subject_raw_rate: Any = unresolved_raw_subject / raw_sourced_subject
    else:
        subject_raw_rate = (
            "NOT MEASURABLE — no raw-sourced subject_family values exist in this corpus"
        )

    return {
        "documents_total": total,
        "entity_class_raw_sourced_documents": raw_sourced_entity,
        "entity_class_unresolved": len(entity_unresolved),
        "entity_class_unresolved_rate_raw_sourced": (
            len(entity_unresolved) / raw_sourced_entity if raw_sourced_entity else "NOT MEASURABLE"
        ),
        "subject_family_raw_sourced_documents": raw_sourced_subject,
        "subject_family_derived_documents": total - raw_sourced_subject,
        "subject_family_unresolved_combined": len(subject_unresolved),
        "subject_family_unresolved_rate_combined": (len(subject_unresolved) / total) if total else "NOT MEASURABLE",
        "subject_family_unresolved_rate_raw_sourced_only": subject_raw_rate,
    }


def persist_vocabularies(
    entity_vocab: Vocabulary, subject_vocab: Vocabulary, cfg: Mapping[str, Any], *, resolver: PathResolver | None = None
) -> dict[str, str]:
    """Write both vocabularies, plus a provenance lookup, to configured paths."""
    resolver = resolver or PathResolver.from_config(cfg)
    vocab_cfg = cfg.get("vocabulary", {})

    entity_rel = vocab_cfg.get("entity_class_file", "data/metadata/entity_classes.json")
    subject_rel = vocab_cfg.get("subject_family_file", "data/metadata/subject_families.json")

    entity_path = resolver.write_path("metadata", *_strip_data_metadata(entity_rel))
    subject_path = resolver.write_path("metadata", *_strip_data_metadata(subject_rel))

    write_json(entity_path, entity_vocab.to_dict())
    write_json(subject_path, subject_vocab.to_dict())

    # Standalone provenance lookup so a consumer can classify a normalised
    # value without parsing either full vocabulary file.
    provenance_path = resolver.write_path("metadata", "vocabulary_provenance.json")
    write_json(
        provenance_path,
        {
            "entity_class": {
                "counts": provenance_counts(entity_vocab),
                "by_canonical_name": provenance_lookup(entity_vocab),
            },
            "subject_family": {
                "counts": provenance_counts(subject_vocab),
                "by_canonical_name": provenance_lookup(subject_vocab),
            },
        },
    )

    return {
        "entity_class_file": str(entity_path),
        "subject_family_file": str(subject_path),
        "vocabulary_provenance_file": str(provenance_path),
    }


def _strip_data_metadata(configured_path: str) -> tuple[str, ...]:
    """`config.yaml` writes vocabulary paths as `data/metadata/<file>`, but
    `resolver.write_path("metadata", ...)` already resolves the `data/metadata`
    prefix from the `paths.metadata` key — strip it if present so the two
    don't compound into `data/metadata/data/metadata/<file>`.
    """
    parts = configured_path.split("/")
    if parts[:2] == ["data", "metadata"]:
        parts = parts[2:]
    return tuple(parts) if parts else (configured_path,)
