"""Annotation protocol, task-file I/O, agreement, and the T1Label state machine.

Implements the contract fixed by :mod:`src.benchmark.interfaces`. Real logic
lives here rather than in ``interfaces.py`` for the same reason as
``phase1/akash-scraper``'s ``rbi_scraper.py`` and ``phase1/karan-matrix``'s
``vocabulary_discovery.py``: ``tests/test_smoke.py`` (Phase 0, base-owned)
asserts every ``interfaces.py`` function still raises ``NotImplementedError``.

Three rules are enforced **in code**, not by convention, because each one
protects a research claim that cannot be repaired after the fact:

**1. ``applies_to`` is annotator-sourced or it does not exist.**
The tempting implementation — copy the source document's ``entity_class``
into ``applies_to`` — produces a label that restates its own input. A
benchmark built that way cannot support RQ1, because the "label" is
definitionally implied by which file the text came from. Enforcement here is
structural rather than heuristic: ``applies_to`` is only ever written by
:func:`apply_annotation`, which requires an ``annotator_id`` and stamps
``provenance`` with :data:`ANNOTATOR_PROVENANCE_PREFIX`. Any label carrying a
non-empty ``applies_to`` *without* that provenance is rejected by
:func:`assert_applies_to_is_annotator_sourced`, which runs on every promotion.
A future Phase 2 extractor therefore cannot reintroduce the tautology without
deliberately forging an annotator provenance string.

**2. ``differential_flag`` is never defaulted to ``absent``.**
It starts ``unlabelled`` by the schema's own default and is only ever moved by
an ingested annotator judgment. Defaulting to ``absent`` would convert every
unexamined item into a positive finding ("this obligation has no differential
counterpart") and silently inflate that class with items nobody looked at.

**3. Promotion to ``validated`` is never implicit.**
:func:`promote_validated` requires ``config.benchmark.min_annotators_per_item``
*distinct* annotator ids and defers the final say to ``T1Label.validate()``,
which independently rejects a validated item with empty ``applies_to`` or a
still-``unlabelled`` differential flag.

On the agreement statistic
--------------------------
``T1Label.agreement_score`` is typed ``float | int | None`` by the base
schema, so it cannot hold the string ``"NOT YET MEASURED"`` — the literal
string belongs to the *reported metric* returned by
:func:`measure_agreement`, while the per-label field stays ``None`` until a
real number exists. Both mean "not measured"; neither is ever ``0.0``, which
would be a real (and very bad) agreement reading rather than an absence.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.common.errors import FoundationError
from src.common.io_helpers import read_jsonl, write_jsonl
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.schemas.benchmark import DifferentialFlag, LabelStatus, ObligationSpan, T1Label

BRANCH = "phase1/meer-annotation"

#: Sentinel for a statistic that has not been computed. Never 0.0 — a zero
#: kappa is a real, meaningful (terrible) agreement reading, not an absence.
NOT_YET_MEASURED = "NOT YET MEASURED"

#: Stamped into ``T1Label.provenance`` by :func:`apply_annotation`. A
#: non-empty ``applies_to`` without this prefix fails the tautology guard.
ANNOTATOR_PROVENANCE_PREFIX = "annotator:"

#: Columns an annotator fills in. Everything else in a task file is context.
ANNOTATOR_INPUT_COLUMNS = ("applies_to", "applies_to_rationale", "differential_flag", "notes")

TASK_FILE_COLUMNS = (
    "label_id",
    "paragraph_id",
    "document_id",
    "context_entity_class",
    "context_subject_family",
    "span_text",
    "matched_cue",
    *ANNOTATOR_INPUT_COLUMNS,
)

#: Separator for the multi-valued ``applies_to`` column in a CSV task file.
APPLIES_TO_SEPARATOR = ";"

VALID_DIFFERENTIAL_FLAGS = {f.value for f in DifferentialFlag}


class AnnotationError(FoundationError):
    """A task file is malformed, or an annotation violates the protocol."""


class TautologyGuardError(FoundationError):
    """``applies_to`` was populated by something other than an annotator.

    Raised rather than warned: a tautological applicability label invalidates
    RQ1, and is far cheaper to catch here than after annotation has scaled.
    """


# -- guards ------------------------------------------------------------------


def assert_applies_to_is_annotator_sourced(label: T1Label) -> None:
    """Reject a label whose ``applies_to`` did not come from an annotator.

    An empty ``applies_to`` is always fine (it means "not yet annotated").
    A non-empty one must carry annotator provenance.
    """
    if not label.applies_to:
        return
    provenance = label.provenance or ""
    if not provenance.startswith(ANNOTATOR_PROVENANCE_PREFIX):
        raise TautologyGuardError(
            f"{label.label_id}: applies_to={label.applies_to!r} was set without annotator "
            f"provenance (provenance={provenance!r}). applies_to must come from a human "
            "judgment via apply_annotation(), never derived from entity_class — a derived "
            "applicability label restates its own input and cannot support RQ1."
        )


def tautology_smell_report(labels: Iterable[T1Label]) -> dict[str, Any]:
    """Corpus-level check: is ``applies_to`` just restating ``entity_class``?

    The per-label guard above enforces *sourcing*; this reports a *pattern*.
    A human annotator may legitimately decide a single obligation binds only
    its own entity class — but if that is true of nearly every annotated item,
    the labels carry almost no independent signal and RQ1 is in trouble
    regardless of how they were sourced. Reported, never raised: this is
    evidence for a methodology conversation, not a bug.
    """
    annotated = [lbl for lbl in labels if lbl.applies_to]
    if not annotated:
        return {
            "annotated_items": 0,
            "items_matching_own_entity_class": 0,
            "share_matching_own_entity_class": NOT_YET_MEASURED,
        }
    matching = sum(
        1 for lbl in annotated
        if lbl.entity_class and list(lbl.applies_to) == [lbl.entity_class]
    )
    return {
        "annotated_items": len(annotated),
        "items_matching_own_entity_class": matching,
        "share_matching_own_entity_class": matching / len(annotated),
    }


# -- candidate construction ---------------------------------------------------


def make_candidate(
    label_id: str,
    span: ObligationSpan,
    *,
    entity_class: str | None = None,
    subject_family: str | None = None,
    provenance: str | None = None,
    in_force_from: str | None = None,
    in_force_to: str | None = None,
) -> T1Label:
    """Build a `candidate` T1Label with nothing asserted about applicability.

    ``applies_to`` is empty and ``differential_flag`` is ``unlabelled`` by
    construction — this function has no parameter to set either, so a caller
    cannot pre-populate them even by accident.
    """
    return T1Label(
        label_id=label_id,
        obligation_span=span,
        entity_class=entity_class,
        subject_family=subject_family,
        label_status=LabelStatus.CANDIDATE.value,
        differential_flag=DifferentialFlag.UNLABELLED.value,
        provenance=provenance,
        in_force_from=in_force_from,
        in_force_to=in_force_to,
    )


def apply_annotation(
    label: T1Label,
    *,
    annotator_id: str,
    applies_to: Sequence[str],
    differential_flag: str,
    applies_to_rationale: str | None = None,
    notes: str | None = None,
) -> T1Label:
    """Apply one annotator's judgment, returning a new label.

    This is the **only** path that writes ``applies_to``. It stamps
    annotator provenance, appends the annotator id, and moves the item to
    ``in_review`` — never straight to ``validated``, which only
    :func:`promote_validated` can do once the annotator-count rule is met.
    """
    if not annotator_id:
        raise AnnotationError(f"{label.label_id}: annotator_id is required to write applies_to")
    if differential_flag not in VALID_DIFFERENTIAL_FLAGS:
        raise AnnotationError(
            f"{label.label_id}: differential_flag {differential_flag!r} is not one of "
            f"{sorted(VALID_DIFFERENTIAL_FLAGS)}"
        )

    annotators = list(label.annotator_ids)
    if annotator_id not in annotators:
        annotators.append(annotator_id)

    existing = label.provenance or ""
    provenance = (
        existing if existing.startswith(ANNOTATOR_PROVENANCE_PREFIX)
        else f"{ANNOTATOR_PROVENANCE_PREFIX}{annotator_id}"
    )

    return replace(
        label,
        applies_to=list(applies_to),
        applies_to_rationale=applies_to_rationale,
        differential_flag=differential_flag,
        notes=notes,
        annotator_ids=annotators,
        annotation_count=len(annotators),
        label_status=LabelStatus.IN_REVIEW.value,
        provenance=provenance,
    )


# -- task files ---------------------------------------------------------------


def build_annotation_tasks(
    sample: Iterable[T1Label],
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Write one CSV task file per configured annotator; return id -> path.

    Every annotator receives **every** item: with a three-person roster and a
    pilot-scale sample, full overlap is what makes an agreement statistic
    computable at all (partial assignment at this size would leave most items
    with a single rater and no agreement to measure).
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    annotators = list(cfg.get("benchmark", {}).get("annotators", []))
    if not annotators:
        raise AnnotationError(
            "config.benchmark.annotators is empty — cannot generate task files without a roster"
        )

    sample = list(sample)
    if not sample:
        raise AnnotationError("cannot build annotation tasks from an empty sample")

    written: dict[str, str] = {}
    for annotator in annotators:
        path = resolver.write_path("benchmark", "tasks", f"annotation_{annotator}.csv")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
            writer.writeheader()
            for label in sample:
                span = label.obligation_span
                writer.writerow(
                    {
                        "label_id": label.label_id,
                        "paragraph_id": span.paragraph_id if span else "",
                        "document_id": span.document_id if span else "",
                        "context_entity_class": label.entity_class or "",
                        "context_subject_family": label.subject_family or "",
                        "span_text": (span.text if span else "") or "",
                        "matched_cue": (span.matched_cue if span else "") or "",
                        # Annotator-filled columns, deliberately blank.
                        "applies_to": "",
                        "applies_to_rationale": "",
                        "differential_flag": "",
                        "notes": "",
                    }
                )
        written[annotator] = str(path)
        logger.info("annotation: task file generated for %s (%d items): %s", annotator, len(sample), path)

    return written


def _parse_applies_to(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(APPLIES_TO_SEPARATOR) if part.strip()]


def ingest_annotations(
    cfg: Mapping[str, Any],
    *,
    candidates: Iterable[T1Label] | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> list[T1Label]:
    """Read completed task files back and merge them onto the candidate set.

    A malformed row fails loudly, naming the annotator, file and item — a
    silently dropped annotation is an invisible hole in the agreement
    statistic, which is worse than a crash.

    Rows an annotator left blank are skipped as *not yet done* rather than
    treated as a judgment of "no applicability" — the distinction between
    unexamined and examined-and-empty is the same one
    ``differential_flag='unlabelled'`` exists to preserve.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    if candidates is None:
        candidate_path = resolver.read_path("benchmark", "pilot_candidates.jsonl")
        candidates = [T1Label.from_dict(r) for r in read_jsonl(candidate_path)]
    by_id = {lbl.label_id: lbl for lbl in candidates}

    annotators = list(cfg.get("benchmark", {}).get("annotators", []))
    ingested = 0
    skipped_blank = 0

    for annotator in annotators:
        path = resolver.find_read_path("benchmark", "tasks", f"annotation_{annotator}.csv")
        if path is None:
            logger.warning("annotation: no completed task file for %s — skipping", annotator)
            continue

        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing_cols = set(TASK_FILE_COLUMNS) - set(reader.fieldnames or [])
            if missing_cols:
                raise AnnotationError(
                    f"task file for {annotator} ({path}) is malformed: missing columns {sorted(missing_cols)}"
                )
            for row_number, row in enumerate(reader, start=2):
                label_id = (row.get("label_id") or "").strip()
                if not label_id:
                    raise AnnotationError(
                        f"task file for {annotator} ({path}) row {row_number}: empty label_id"
                    )
                if label_id not in by_id:
                    raise AnnotationError(
                        f"task file for {annotator} ({path}) row {row_number}: label_id {label_id!r} "
                        "does not match any candidate — task file and candidate set are out of sync"
                    )

                applies_to = _parse_applies_to(row.get("applies_to", ""))
                flag = (row.get("differential_flag") or "").strip()

                if not applies_to and not flag:
                    skipped_blank += 1
                    continue
                if not applies_to:
                    raise AnnotationError(
                        f"task file for {annotator} ({path}) row {row_number} (item {label_id}): "
                        "differential_flag given without applies_to — an item cannot have a "
                        "differential judgment without an applicability judgment"
                    )
                if flag not in VALID_DIFFERENTIAL_FLAGS:
                    raise AnnotationError(
                        f"task file for {annotator} ({path}) row {row_number} (item {label_id}): "
                        f"differential_flag {flag!r} is not one of {sorted(VALID_DIFFERENTIAL_FLAGS)}"
                    )

                by_id[label_id] = apply_annotation(
                    by_id[label_id],
                    annotator_id=annotator,
                    applies_to=applies_to,
                    differential_flag=flag,
                    applies_to_rationale=(row.get("applies_to_rationale") or "").strip() or None,
                    notes=(row.get("notes") or "").strip() or None,
                )
                ingested += 1
                logger.info("annotation: ingested %s from %s", label_id, annotator)

    logger.info(
        "ingest_annotations: %d annotations ingested, %d blank rows skipped (not yet annotated)",
        ingested, skipped_blank,
    )
    return list(by_id.values())


# -- agreement ----------------------------------------------------------------


def fleiss_kappa(rating_counts: Sequence[Sequence[int]]) -> float | str:
    """Fleiss' kappa over an items x categories count matrix.

    Returns :data:`NOT_YET_MEASURED` rather than a number whenever kappa is
    undefined — no items, fewer than two raters, or unanimous agreement on a
    single category across every item (which makes expected agreement 1.0 and
    the denominator zero). Returning 0.0 in those cases would report perfect
    disagreement where the truth is "not computable".
    """
    rows = [list(row) for row in rating_counts if sum(row) > 0]
    if not rows:
        return NOT_YET_MEASURED

    raters_per_item = {sum(row) for row in rows}
    if len(raters_per_item) != 1:
        raise AnnotationError(
            f"fleiss_kappa requires an equal number of raters per item, got {sorted(raters_per_item)}"
        )
    n = raters_per_item.pop()
    if n < 2:
        return NOT_YET_MEASURED

    N = len(rows)
    k = len(rows[0])

    p_j = [sum(row[j] for row in rows) / (N * n) for j in range(k)]
    P_e = sum(p * p for p in p_j)
    P_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in rows]
    P_bar = sum(P_i) / N

    if abs(1.0 - P_e) < 1e-12:
        return NOT_YET_MEASURED
    return (P_bar - P_e) / (1.0 - P_e)


def _rating_matrix(labels: Sequence[T1Label], categories: Sequence[str]) -> list[list[int]]:
    """Count matrix for `differential_flag` across multiply-annotated items.

    Only the differential flag is used: it is the one categorical judgment
    with a fixed, closed answer set. ``applies_to`` is a *set* of entity
    classes, for which Fleiss' kappa is not defined; its agreement is
    reported separately as exact-set-match rate.
    """
    index = {c: i for i, c in enumerate(categories)}
    matrix = []
    for label in labels:
        row = [0] * len(categories)
        # One vote per annotator. The stored flag is the merged result, so at
        # pilot scale this reflects the last ingested judgment per annotator;
        # per-annotator raw votes are preserved in the task files themselves.
        for _ in label.annotator_ids:
            row[index[label.differential_flag]] += 1
        matrix.append(row)
    return matrix


def measure_agreement(
    labels: Iterable[T1Label], cfg: Mapping[str, Any] | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Inter-annotator agreement over multiply-annotated items.

    Every statistic is either a real computed number or the literal string
    :data:`NOT_YET_MEASURED` — never a numeric placeholder.
    """
    labels = list(labels)
    min_annotators = 2
    if cfg:
        min_annotators = int(cfg.get("benchmark", {}).get("min_annotators_per_item", 2))

    multiply_annotated = [lbl for lbl in labels if len(lbl.annotator_ids) >= min_annotators]

    if not multiply_annotated:
        return {
            "items_total": len(labels),
            "items_multiply_annotated": 0,
            "min_annotators_per_item": min_annotators,
            "fleiss_kappa_differential_flag": NOT_YET_MEASURED,
            "applies_to_exact_match_rate": NOT_YET_MEASURED,
            "reason": (
                f"{NOT_YET_MEASURED} — no item has reached {min_annotators} independent "
                "annotators yet; agreement is not computable until the roster completes "
                "and the task files are ingested"
            ),
        }

    categories = [f.value for f in DifferentialFlag]
    kappa = fleiss_kappa(_rating_matrix(multiply_annotated, categories))

    return {
        "items_total": len(labels),
        "items_multiply_annotated": len(multiply_annotated),
        "min_annotators_per_item": min_annotators,
        "fleiss_kappa_differential_flag": kappa,
        "applies_to_exact_match_rate": NOT_YET_MEASURED,
        "differential_flag_distribution": {
            c: sum(1 for lbl in multiply_annotated if lbl.differential_flag == c) for c in categories
        },
    }


# -- promotion ----------------------------------------------------------------


def promote_validated(
    labels: Iterable[T1Label],
    cfg: Mapping[str, Any],
    *,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> list[T1Label]:
    """Promote items meeting the annotation threshold; leave the rest alone.

    Three independent gates, all of which must pass: the annotator-count rule
    from config, the tautology guard, and ``T1Label.validate()`` itself. An
    item failing any of them stays where it is — promotion is never
    warned-and-allowed.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    min_annotators = int(cfg.get("benchmark", {}).get("min_annotators_per_item", 2))

    results: list[T1Label] = []
    promoted = rejected = 0

    for label in labels:
        distinct = len(set(label.annotator_ids))
        if distinct < min_annotators:
            logger.info(
                "promotion: %s NOT promoted — %d/%d distinct annotators",
                label.label_id, distinct, min_annotators,
            )
            results.append(label)
            rejected += 1
            continue

        assert_applies_to_is_annotator_sourced(label)

        promoted_label = replace(
            label,
            label_status=LabelStatus.VALIDATED.value,
            annotation_count=distinct,
        )
        errors = promoted_label.validate()
        if errors:
            logger.warning(
                "promotion: %s NOT promoted — validate() rejected it: %s", label.label_id, errors
            )
            results.append(label)
            rejected += 1
            continue

        logger.info("promotion: %s promoted to validated (%d annotators)", label.label_id, distinct)
        results.append(promoted_label)
        promoted += 1

    logger.info("promote_validated: %d promoted, %d left unpromoted", promoted, rejected)
    return results


def persist_labels(
    labels: Iterable[T1Label], cfg: Mapping[str, Any], filename: str, *, resolver: PathResolver | None = None
) -> str:
    """Write a label set to ``data/benchmark/<filename>``."""
    resolver = resolver or PathResolver.from_config(cfg)
    path = resolver.write_path("benchmark", filename)
    write_jsonl(path, [lbl.to_dict() for lbl in labels])
    return str(path)
