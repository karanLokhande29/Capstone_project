"""Single-Expert Annotation Protocol: per-pass votes, test-retest, promotion.

Implements the contract fixed by :mod:`src.benchmark.interfaces`. Real logic
lives here rather than in ``interfaces.py`` for the same reason as
``phase1/akash-scraper``'s ``rbi_scraper.py`` and ``phase1/karan-matrix``'s
``vocabulary_discovery.py``: ``tests/test_smoke.py`` (Phase 0, base-owned)
asserts every ``interfaces.py`` function still raises ``NotImplementedError``.

From 2026-09-24 (P1-005) this project has **one** annotator. That single fact
drives the design of this module, because the obvious adaptation — keep the
three-annotator machinery and point it at one person — produces numbers that
look like inter-annotator agreement and are not. The protocol implemented here
is instead:

* pass 1 over the whole set;
* a blind pass 2, after a minimum gap, over a **pre-drawn** retest set;
* optional second raters, when someone has actually agreed to label;
* written adjudication of every disagreement;
* a per-item validation route recorded in ``provenance``.

Four rules are enforced **in code**, not by convention, because each one
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

**2. ``differential_flag`` is never defaulted to ``absent``.**
It starts ``unlabelled`` by the schema's own default and is only ever moved by
an ingested annotator judgment. Defaulting to ``absent`` would convert every
unexamined item into a positive finding ("this obligation has no differential
counterpart") and silently inflate that class with items nobody looked at.

**3. Raw votes are never overwritten.**
Every row of every task file becomes one immutable :class:`AnnotatorVote`.
Merging happens once, from the full vote set, in :func:`merge_votes`. The
superseded design applied each annotator's row to the *same* label in turn, so
the last writer won and the "agreement" statistic then counted that single
surviving flag once per annotator — three annotators who never agreed on
anything scored kappa = 1.0 and every item was promoted. Passing votes
sequentially through :func:`apply_annotation` is the bug, not the style.

**4. Promotion is per validation route, and never counts raters.**
With one annotator there is nothing to count. :func:`promote_validated`
gates on which route an item took (:data:`ROUTE_RETEST_CONSISTENT`,
:data:`ROUTE_SINGLE_PASS`, :data:`ROUTE_ADJUDICATED`) and then defers to
``T1Label.validate()``, which independently rejects a validated item with
empty ``applies_to`` or a still-``unlabelled`` differential flag.

On the agreement statistics
---------------------------
With a single rater, inter-annotator agreement **does not exist**, so this
module cannot compute one. What it computes instead is named for what it is:

* ``test_retest`` — the primary annotator's pass 1 against their own blind
  pass 2. This measures the *stability* of one person's judgment, not
  agreement between people, and the report says so.
* ``second_rater`` — the primary against each second rater, where one exists.

Fleiss' kappa needs three or more raters and is therefore **not emitted at
all** below that count: no key, not even a NOT-YET-MEASURED one, so no
downstream reader can find a "fleiss" number that was never earned.

``T1Label.agreement_score`` is typed ``float | int | None`` by the base
schema, so it cannot hold the string ``"NOT YET MEASURED"`` — the literal
string belongs to the *reported metric*, while the per-label field stays
``None`` until a real number exists. Both mean "not measured"; neither is ever
``0.0``, which would be a real (and very bad) reading rather than an absence.
"""

from __future__ import annotations

import csv
import itertools
import json
import logging
import math
import random
import shutil
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.common.errors import FoundationError
from src.common.io_helpers import read_jsonl, write_json, write_jsonl
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

#: Columns the adjudicator fills in on an adjudication file.
ADJUDICATION_INPUT_COLUMNS = (
    "final_applies_to",
    "final_differential_flag",
    "adjudication_rationale",
    "final_not_obligation",
)

#: Separator for the multi-valued ``applies_to`` column in a CSV task file.
APPLIES_TO_SEPARATOR = ";"

VALID_DIFFERENTIAL_FLAGS = {f.value for f in DifferentialFlag}

#: Every category Cohen's / Fleiss' kappa ranges over, in a fixed order.
FLAG_CATEGORIES: tuple[str, ...] = tuple(f.value for f in DifferentialFlag)

# -- vote status --------------------------------------------------------------

#: The annotator filled in a judgment.
VOTE_VOTED = "voted"
#: The row is untouched: no judgment, no note. "Not yet done", not a judgment.
VOTE_BLANK = "blank"
#: Both judgment columns blank but a note given: "this is not an obligation".
VOTE_NOT_OBLIGATION = "not_obligation"

# -- validation routes (recorded in provenance) -------------------------------

ROUTE_RETEST_CONSISTENT = "retest-consistent"
ROUTE_SINGLE_PASS = "single-pass"
ROUTE_NOT_OBLIGATION = "not-obligation"
ROUTE_NEEDS_ADJUDICATION = "needs-adjudication"
ROUTE_PASS1_ONLY = "pass1-only"
ROUTE_ADJUDICATED = "adjudicated"
#: P1-004: two or more independent human raters cast the identical judgment and
#: no other human rater contradicted it.
ROUTE_CONSENSUS = "consensus"
#: Not in the P1-005 table: a second rater voted before the primary's pass 1.
#: Held at ``in_review`` — an item the primary has never seen cannot validate.
ROUTE_AWAITING_PRIMARY = "awaiting-primary"

#: Routes whose items are eligible for ``validated``, subject to ``validate()``.
VALIDATING_ROUTES = frozenset(
    {ROUTE_RETEST_CONSISTENT, ROUTE_SINGLE_PASS, ROUTE_ADJUDICATED, ROUTE_CONSENSUS}
)

# -- label provenance (P1-004) ------------------------------------------------

#: The named rater filled the file themselves, without AI assistance. Only
#: these votes are human votes.
LABEL_SOURCE_MANUAL = "manual"
#: The labels were produced with AI assistance. Reported as a human-AI
#: agreement diagnostic and never as a rater — counting them would fabricate
#: the inter-rater agreement the benchmark's validity rests on.
LABEL_SOURCE_AI = "ai_assisted"
VALID_LABEL_SOURCES = (LABEL_SOURCE_MANUAL, LABEL_SOURCE_AI)

#: Prefix marking a vote that came from an AI diagnostic file rather than a
#: rater. Structurally distinct so it cannot be mistaken for a rater id.
AI_RATER_PREFIX = "ai:"

#: How a minutes figure was obtained. A recalled estimate is not a measurement
#: and every figure derived from one is labelled with its basis.
MINUTES_BASIS_MEASURED = "measured"
MINUTES_BASIS_RECALLED = "recalled_estimate"

# -- artifact filenames -------------------------------------------------------

VOTES_FILENAME = "pilot_votes.jsonl"
RETEST_SET_FILENAME = "retest_set.json"
ANNOTATION_LOG_FILENAME = "annotation_log.json"
OVERWRITTEN_DIRNAME = "_overwritten"


class AnnotationError(FoundationError):
    """A task file is malformed, or an annotation violates the protocol."""


class TautologyGuardError(FoundationError):
    """``applies_to`` was populated by something other than an annotator.

    Raised rather than warned: a tautological applicability label invalidates
    RQ1, and is far cheaper to catch here than after annotation has scaled.
    """


# -- roster ------------------------------------------------------------------


def primary_annotator(cfg: Mapping[str, Any]) -> str:
    """The single expert whose passes carry the protocol. Required."""
    primary = (cfg.get("benchmark", {}) or {}).get("primary_annotator")
    if not primary:
        raise AnnotationError(
            "config.benchmark.primary_annotator is unset — the single-expert protocol "
            "has no roster to fall back on, and guessing one would silently attribute "
            "someone else's judgment to a name nobody chose"
        )
    return str(primary)


def second_raters(cfg: Mapping[str, Any]) -> list[str]:
    """Raters who have actually agreed to label, if any. Usually empty."""
    raters = (cfg.get("benchmark", {}) or {}).get("second_raters") or []
    return [str(r) for r in raters]


def ai_diagnostic_files(cfg: Mapping[str, Any]) -> list[str]:
    """Files read as a human-AI diagnostic, relative to the benchmark path key."""
    files = (cfg.get("benchmark", {}) or {}).get("ai_diagnostic_files") or []
    return [str(f) for f in files]


def configured_raters(cfg: Mapping[str, Any]) -> list[str]:
    """Primary first, then any second raters. De-duplicated, order preserved."""
    ordered = [primary_annotator(cfg), *second_raters(cfg)]
    seen: list[str] = []
    for rater in ordered:
        if rater not in seen:
            seen.append(rater)
    return seen


def _retest_cfg(cfg: Mapping[str, Any]) -> Mapping[str, Any]:
    return (cfg.get("benchmark", {}) or {}).get("retest", {}) or {}


def _agreement_cfg(cfg: Mapping[str, Any]) -> Mapping[str, Any]:
    return (cfg.get("benchmark", {}) or {}).get("agreement", {}) or {}


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


def judgment_column_independence(
    votes: Iterable["AnnotatorVote"], raters: Sequence[str]
) -> dict[str, Any]:
    """Per judgment column: how often every rater gave the identical answer.

    A1's independence check compares the free-text columns, which catches a
    copied file. It does **not** catch a single column being shared while the
    prose around it is written separately — and that is the case that quietly
    destroys a reliability claim, because the column still produces a perfect
    agreement score.

    ``applies_to`` is set-valued over a vocabulary of ~19 classes, so exact
    agreement on a large set is astronomically unlikely by chance: independent
    raters agreeing on the same 12-element subset even once is a coincidence,
    and doing it repeatedly is not. ``suspicious`` flags that pattern. It is
    evidence to investigate and report, never grounds to alter anyone's file.
    """
    by_item: dict[str, dict[str, AnnotatorVote]] = {}
    for vote in votes:
        if vote.pass_no != 1 or vote.rater_id not in raters or not vote.is_decided:
            continue
        by_item.setdefault(vote.label_id, {})[vote.rater_id] = vote

    complete = {i: per for i, per in by_item.items() if len(per) >= 2}
    if not complete:
        return {"status": f"{NOT_YET_MEASURED} — fewer than 2 raters decided any item"}

    applies_identical = sum(
        1 for per in complete.values() if len({v.applies_to for v in per.values()}) == 1
    )
    flag_identical = sum(
        1 for per in complete.values()
        if len({v.differential_flag for v in per.values()}) == 1
    )
    rationale_identical = sum(
        1 for per in complete.values()
        if len({(v.applies_to_rationale or "").strip() for v in per.values()}) == 1
    )

    # Only multi-class sets carry the argument: agreeing that one obvious class
    # applies is ordinary, agreeing on the same 8 of 19 is not.
    multi = {
        i: per for i, per in complete.items()
        if max(len(v.applies_to) for v in per.values()) > 1
    }
    multi_identical = sum(
        1 for per in multi.values() if len({v.applies_to for v in per.values()}) == 1
    )

    suspicious = bool(multi) and multi_identical == len(multi) and len(multi) >= 3

    return {
        "n_items": len(complete),
        "raters": sorted(raters),
        "applies_to_identical_across_all_raters": applies_identical,
        "differential_flag_identical_across_all_raters": flag_identical,
        "applies_to_rationale_identical_across_all_raters": rationale_identical,
        "multi_class_items": len(multi),
        "multi_class_items_identical_across_all_raters": multi_identical,
        "applies_to_independent": not suspicious,
        "note": (
            "applies_to is IDENTICAL across every rater on every multi-class item "
            f"({multi_identical}/{len(multi)}). Independent raters do not converge on the "
            "same large subset of a ~19-class vocabulary repeatedly, so this column has a "
            "single source and its exact-match rate is NOT an agreement measurement. Report "
            "differential_flag agreement only, and treat every applies_to figure as "
            "unreplicated."
            if suspicious else
            "No column shows the one-source pattern."
        ),
    }


def tautology_share_by_rater(
    votes: Iterable["AnnotatorVote"], labels: Iterable[T1Label]
) -> dict[str, Any]:
    """Per (rater, pass): the share of ``voted`` rows that copy the source class.

    Computed from raw votes rather than merged labels, so a second rater who
    copies ``context_entity_class`` on every row is visible even when their
    votes never reach a promoted label. The superseded implementation read the
    merged label and therefore only ever saw the last annotator ingested.
    """
    entity_class = {lbl.label_id: lbl.entity_class for lbl in labels}
    totals: dict[str, int] = {}
    matching: dict[str, int] = {}

    for vote in votes:
        if vote.status != VOTE_VOTED:
            continue
        key = vote.rater_key
        totals[key] = totals.get(key, 0) + 1
        own = entity_class.get(vote.label_id)
        if own and vote.applies_to == (own,):
            matching[key] = matching.get(key, 0) + 1

    return {
        key: {
            "voted_rows": total,
            "rows_matching_context_entity_class": matching.get(key, 0),
            "share": matching.get(key, 0) / total if total else NOT_YET_MEASURED,
        }
        for key, total in sorted(totals.items())
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
    """Apply **one** merged judgment, returning a new label.

    This is the only path that writes ``applies_to``. It stamps annotator
    provenance, appends the annotator id, and moves the item to ``in_review``
    — never straight to ``validated``, which only :func:`promote_validated`
    can do.

    It is deliberately **not** called once per rater or once per pass:
    :func:`merge_votes` calls it at most once per item, with values already
    reconciled across every vote. Chaining calls is what made the superseded
    ingest last-writer-wins.
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


# -- the vote record ----------------------------------------------------------


@dataclass(frozen=True)
class AnnotatorVote:
    """One row of one task file, exactly as the rater left it.

    Frozen and module-local on purpose. Frozen because a vote is evidence:
    once read off disk nothing in the pipeline may adjust it, and the
    last-writer-wins defect this replaces was precisely a mutable judgment.
    Module-local because ``src/schemas/**`` is the cross-branch contract and a
    per-pass vote is an implementation detail of *this* protocol, not a record
    other branches consume.
    """

    rater_id: str
    pass_no: int
    label_id: str
    applies_to: tuple[str, ...]
    differential_flag: str | None
    applies_to_rationale: str | None
    notes: str | None
    status: str
    source_file: str
    row_number: int

    @property
    def rater_key(self) -> str:
        """Stable identity of one rater's one pass, e.g. ``karan:pass1``."""
        return f"{self.rater_id}:pass{self.pass_no}"

    @property
    def judgment(self) -> tuple[str, tuple[str, ...], str | None]:
        """What this vote asserts, comparably. Blank rows assert nothing."""
        if self.status == VOTE_VOTED:
            return (VOTE_VOTED, self.applies_to, self.differential_flag)
        return (self.status, (), None)

    @property
    def is_decided(self) -> bool:
        """Whether the rater made any call at all on this item."""
        return self.status in (VOTE_VOTED, VOTE_NOT_OBLIGATION)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rater_id": self.rater_id,
            "pass_no": self.pass_no,
            "label_id": self.label_id,
            "applies_to": list(self.applies_to),
            "differential_flag": self.differential_flag,
            "applies_to_rationale": self.applies_to_rationale,
            "notes": self.notes,
            "status": self.status,
            "source_file": self.source_file,
            "row_number": self.row_number,
        }


@dataclass(frozen=True)
class Adjudication:
    """One adjudicated item: the written resolution of a disagreement."""

    label_id: str
    applies_to: tuple[str, ...]
    differential_flag: str | None
    rationale: str
    not_obligation: bool
    source_file: str
    row_number: int


# -- entity-class vocabulary --------------------------------------------------


def load_entity_class_names(
    resolver: PathResolver, *, cfg: Mapping[str, Any] | None = None
) -> tuple[str, ...]:
    """Canonical entity-class names, from the discovered vocabulary file.

    Hard-fails when the file is absent rather than skipping validation. A
    silently unvalidated ``applies_to`` column is how free-text spelling drift
    ("Commercial banks", "commercial Banks") gets into the labels, and the
    resulting classes cannot be joined against the matrix afterwards.
    """
    filename = "entity_classes.json"
    if cfg:
        configured = (cfg.get("vocabulary", {}) or {}).get("entity_class_file")
        if configured:
            filename = Path(str(configured)).name

    path = resolver.find_read_path("metadata", filename)
    if path is None:
        searched = "\n".join(f"  - {p}" for p in resolver.candidate_read_paths("metadata", filename))
        raise AnnotationError(
            f"entity-class vocabulary {filename!r} not found, so applies_to names cannot be "
            f"validated. Searched:\n{searched}\n"
            "Run the phase1/karan-matrix vocabulary discovery first — ingesting against no "
            "vocabulary would let misspelled classes through silently."
        )

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = tuple(
        str(term["canonical_name"])
        for term in data.get("terms", [])
        if term.get("canonical_name")
    )
    if not names:
        raise AnnotationError(f"entity-class vocabulary at {path} lists no canonical_name terms")
    return names


# -- task files ---------------------------------------------------------------


def _task_row(label: T1Label) -> dict[str, str]:
    """One task-file row: context filled, annotator columns deliberately blank."""
    span = label.obligation_span
    return {
        "label_id": label.label_id,
        "paragraph_id": span.paragraph_id if span else "",
        "document_id": span.document_id if span else "",
        "context_entity_class": label.entity_class or "",
        "context_subject_family": label.subject_family or "",
        "span_text": (span.text if span else "") or "",
        "matched_cue": (span.matched_cue if span else "") or "",
        "applies_to": "",
        "applies_to_rationale": "",
        "differential_flag": "",
        "notes": "",
    }


def _filled_input_cells(path: Path, input_columns: Sequence[str]) -> int:
    """How many annotator-input cells in an existing file are non-empty."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error):
        # Unreadable is treated as "might hold work": the guard refuses, and
        # the operator decides with --force-regenerate-tasks.
        return 1
    return sum(
        1
        for row in rows
        for column in input_columns
        if (row.get(column) or "").strip()
    )


def _backup_before_overwrite(path: Path, logger: logging.Logger) -> Path:
    """Copy a file about to be overwritten into ``tasks/_overwritten/``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = path.parent / OVERWRITTEN_DIRNAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.name}.{stamp}.csv"
    shutil.copy2(path, backup)
    logger.warning("annotation: %s backed up to %s before overwrite", path.name, backup)
    return backup


def guard_task_overwrite(
    path: Path,
    *,
    force: bool,
    logger: logging.Logger,
    input_columns: Sequence[str] = ANNOTATOR_INPUT_COLUMNS,
) -> None:
    """Refuse to blank a task file that already holds hand-entered labels.

    ``data/benchmark/**`` is gitignored, so an overwritten task file is gone —
    not recoverable from git, and not re-derivable by anything, because the
    content was a person's judgment. The superseded ``pilot``/``all``/``report``
    stages all rewrote every task file blank on every run.
    """
    if not path.exists():
        return

    filled = _filled_input_cells(path, input_columns)
    if filled == 0:
        return

    if not force:
        raise AnnotationError(
            f"refusing to overwrite {path}: it already holds {filled} filled annotator "
            "cell(s), and data/benchmark/** is gitignored so the content is not "
            "recoverable. Pass --force-regenerate-tasks (force=True) to overwrite anyway; "
            f"the current file is copied to {path.parent / OVERWRITTEN_DIRNAME}/ first."
        )

    _backup_before_overwrite(path, logger)


def _write_task_file(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def build_annotation_tasks(
    sample: Iterable[T1Label],
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    force: bool = False,
    **kwargs: Any,
) -> dict[str, str]:
    """Write one pass-1 CSV task file per configured rater; return id -> path.

    The roster is the primary annotator plus any second raters who have
    actually agreed to label. Every rater receives every item: at pilot scale
    partial assignment would leave most items with a single rater and nothing
    to compare.

    Existing files holding filled cells are refused unless ``force``; see
    :func:`guard_task_overwrite`.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    raters = configured_raters(cfg)
    sample = list(sample)
    if not sample:
        raise AnnotationError("cannot build annotation tasks from an empty sample")

    rows = [_task_row(label) for label in sample]

    written: dict[str, str] = {}
    for rater in raters:
        path = resolver.write_path("benchmark", "tasks", f"annotation_{rater}.csv")
        guard_task_overwrite(path, force=force, logger=logger)
        _write_task_file(path, rows)
        written[rater] = str(path)
        logger.info(
            "annotation: pass-1 task file generated for %s (%d items): %s",
            rater, len(sample), path,
        )

    return written


# -- retest set and the blind pass-2 file -------------------------------------


def _stratum_quota(size: int, fraction: float) -> int:
    """How many of a stratum's items the retest set takes."""
    if fraction <= 0 or size == 0:
        return 0
    if fraction >= 1:
        return size
    return min(size, max(1, round(size * fraction)))


def draw_retest_set(
    labels: Iterable[T1Label],
    fraction: float,
    seed: int,
    *,
    resolver: PathResolver,
    force: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Draw the retest set, stratified by ``entity_class``, deterministically.

    Drawn **before** pass 2 is looked at and written down, so the retest set
    cannot be chosen after the fact to flatter the statistic. Refuses to
    redraw over an existing file unless ``force``, for the same reason.
    """
    logger = logger or get_logger("benchmark.annotation", {})
    path = resolver.write_path("benchmark", RETEST_SET_FILENAME)

    if path.exists() and not force:
        existing = json.loads(path.read_text(encoding="utf-8"))
        logger.info(
            "annotation: retest set already drawn (%d items, seed=%s) — keeping it",
            len(existing.get("label_ids", [])), existing.get("seed"),
        )
        return existing

    by_class: dict[str, list[str]] = {}
    for label in labels:
        by_class.setdefault(label.entity_class or "", []).append(label.label_id)

    rng = random.Random(seed)
    selected: list[str] = []
    for entity_class in sorted(by_class):
        stratum = sorted(by_class[entity_class])
        rng.shuffle(stratum)
        selected.extend(stratum[: _stratum_quota(len(stratum), float(fraction))])

    record = {
        "label_ids": sorted(selected),
        "fraction": float(fraction),
        "seed": int(seed),
        "drawn_at": datetime.now(timezone.utc).isoformat(),
        "strata": {k or "(none)": len(v) for k, v in sorted(by_class.items())},
    }
    write_json(path, record)
    logger.info(
        "annotation: retest set drawn — %d of %d items at fraction %s (seed=%s): %s",
        len(record["label_ids"]), sum(len(v) for v in by_class.values()), fraction, seed, path,
    )
    return record


def load_retest_set(resolver: PathResolver) -> set[str]:
    """The drawn retest set, or an empty set when none has been drawn."""
    path = resolver.find_read_path("benchmark", RETEST_SET_FILENAME)
    if path is None:
        return set()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(data.get("label_ids", []))


# -- the annotation log -------------------------------------------------------


def read_annotation_log(resolver: PathResolver) -> dict[str, Any]:
    """Every recorded ingest and retest event, oldest first."""
    path = resolver.find_read_path("benchmark", ANNOTATION_LOG_FILENAME)
    if path is None:
        return {"entries": []}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.setdefault("entries", [])
    return data


def append_annotation_log(resolver: PathResolver, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Append one event to the log and persist it."""
    log = read_annotation_log(resolver)
    log["entries"].append(dict(entry))
    write_json(resolver.write_path("benchmark", ANNOTATION_LOG_FILENAME), log)
    return log


def last_pass1_ingest(resolver: PathResolver, rater_id: str) -> dict[str, Any] | None:
    """The most recent recorded pass-1 ingest for ``rater_id``, if any."""
    entries = [
        entry
        for entry in read_annotation_log(resolver).get("entries", [])
        if entry.get("event") == "ingest"
        and entry.get("rater_id") == rater_id
        and int(entry.get("pass_no") or 0) == 1
    ]
    return entries[-1] if entries else None


def rater_label_sources(resolver: PathResolver) -> dict[str, str]:
    """Each rater's most recently recorded ``label_source``.

    Latest entry wins, so re-ingesting a file after re-declaring its source
    corrects the record without needing the log to be edited by hand.
    """
    sources: dict[str, str] = {}
    for entry in read_annotation_log(resolver).get("entries", []):
        rater = entry.get("rater_id")
        source = entry.get("label_source")
        if rater and source:
            sources[str(rater)] = str(source)
    return sources


def human_raters(
    cfg: Mapping[str, Any], resolver: PathResolver, *, logger: logging.Logger | None = None
) -> list[str]:
    """Configured raters whose labels are their own work.

    A rater recorded as ``ai_assisted`` is dropped here and therefore never
    reaches pairwise kappa, Fleiss' kappa or a promotion. This is the single
    chokepoint for that rule: everything downstream asks this function who the
    humans are rather than reading the roster directly.
    """
    sources = rater_label_sources(resolver)
    humans: list[str] = []
    for rater in configured_raters(cfg):
        if sources.get(rater) == LABEL_SOURCE_AI:
            if logger is not None:
                logger.warning(
                    "agreement: excluding %s from every human statistic — their labels are "
                    "recorded as %s in %s. They are reported only as a human-AI diagnostic.",
                    rater, LABEL_SOURCE_AI, ANNOTATION_LOG_FILENAME,
                )
            continue
        humans.append(rater)
    return humans


def _parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def pass2_task_path(cfg: Mapping[str, Any], resolver: PathResolver) -> Path:
    return resolver.write_path(
        "benchmark", "tasks", f"annotation_{primary_annotator(cfg)}_pass2.csv"
    )


def build_pass2_tasks(
    cfg: Mapping[str, Any],
    *,
    candidates: Iterable[T1Label] | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    allow_short_gap: bool = False,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Write the blind pass-2 file: retest items only, shuffled, blank.

    Three refusals, each protecting the blindness of the retest:

    * **pass 1 not ingested** — there is nothing to retest against, and a
      pass-2 file written first invites both passes in one sitting;
    * **gap shorter than ``retest.min_gap_days``** — a retest taken too soon
      measures recall of the earlier answers rather than stability of the
      judgment. ``--allow-short-gap`` overrides it, and is then recorded in
      the log and printed in the report, so the caveat travels with the number;
    * **the pass-2 file already exists** — regenerating it would blank work in
      progress.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)
    now = now or datetime.now(timezone.utc)

    primary = primary_annotator(cfg)
    retest = _retest_cfg(cfg)
    min_gap_days = int(retest.get("min_gap_days", 5))
    shuffle_seed = int(retest.get("shuffle_seed", 0))

    record = last_pass1_ingest(resolver, primary)
    if record is None:
        raise AnnotationError(
            f"cannot write the pass-2 file: no pass-1 ingest for {primary!r} is recorded in "
            f"{ANNOTATION_LOG_FILENAME}. Run `ingest --pass 1` first — a pass-2 file written "
            "before pass 1 has been read back invites both passes in one sitting, which is "
            "not a retest."
        )

    ingested_at = _parse_timestamp(record.get("timestamp"))
    gap_days = (now - ingested_at).total_seconds() / 86400.0 if ingested_at else None
    earliest = (ingested_at + timedelta(days=min_gap_days)).isoformat() if ingested_at else None

    short_gap = gap_days is not None and gap_days < min_gap_days
    if short_gap and not allow_short_gap:
        raise AnnotationError(
            f"refusing to write the pass-2 file: only {gap_days:.2f} day(s) since the pass-1 "
            f"ingest at {record.get('timestamp')}, and retest.min_gap_days is {min_gap_days}. "
            f"The earliest allowed date is {earliest}. A retest taken sooner measures recall "
            "of your pass-1 answers, not the stability of the judgment. Pass "
            "--allow-short-gap to override; the short gap is then recorded in the log and "
            "printed in the report."
        )
    if short_gap:
        logger.warning(
            "annotation: writing the pass-2 file after only %.2f day(s) (min_gap_days=%d) "
            "because --allow-short-gap was given — the test-retest figure is weakened and "
            "the report will say so",
            gap_days, min_gap_days,
        )

    if candidates is None:
        candidates = load_candidates(resolver)
    by_id = {label.label_id: label for label in candidates}

    retest_ids = load_retest_set(resolver)
    if not retest_ids:
        raise AnnotationError(
            f"cannot write the pass-2 file: no retest set has been drawn "
            f"({RETEST_SET_FILENAME} is absent). Draw it with draw_retest_set() — choosing "
            "the retest items after seeing pass 2 would let the sample be picked to flatter "
            "the statistic."
        )

    missing = sorted(retest_ids - set(by_id))
    if missing:
        raise AnnotationError(
            f"retest set names {len(missing)} label_id(s) absent from the candidate set, "
            f"first: {missing[:3]} — the retest set and candidates are out of sync"
        )

    rows = [_task_row(by_id[label_id]) for label_id in sorted(retest_ids)]
    random.Random(shuffle_seed).shuffle(rows)

    path = pass2_task_path(cfg, resolver)
    if path.exists():
        if not force:
            raise AnnotationError(
                f"refusing to overwrite the existing pass-2 file {path}. Pass "
                "--force-regenerate-tasks (force=True) to regenerate it; the current file is "
                f"copied to {path.parent / OVERWRITTEN_DIRNAME}/ first."
            )
        _backup_before_overwrite(path, logger)

    _write_task_file(path, rows)
    logger.info(
        "annotation: pass-2 file written for %s — %d retest items, order shuffled with "
        "seed=%d: %s",
        primary, len(rows), shuffle_seed, path,
    )

    result = {
        "path": str(path),
        "rater_id": primary,
        "items": len(rows),
        "shuffle_seed": shuffle_seed,
        "pass1_ingested_at": record.get("timestamp"),
        "gap_days": gap_days,
        "min_gap_days": min_gap_days,
        "earliest_allowed": earliest,
        "allow_short_gap_used": bool(short_gap),
    }
    append_annotation_log(
        resolver,
        {
            "event": "retest",
            "rater_id": primary,
            "pass_no": 2,
            "timestamp": now.isoformat(),
            "items": len(rows),
            "gap_days": gap_days,
            "min_gap_days": min_gap_days,
            "allow_short_gap_used": bool(short_gap),
        },
    )
    return result


# -- reading votes ------------------------------------------------------------


def _parse_applies_to(raw: str) -> tuple[str, ...]:
    """Split, strip, de-duplicate and sort the multi-valued column."""
    parts = [part.strip() for part in (raw or "").split(APPLIES_TO_SEPARATOR) if part.strip()]
    return tuple(sorted(dict.fromkeys(parts)))


def _read_vote_file(
    path: Path,
    *,
    rater_id: str,
    pass_no: int,
    valid_label_ids: set[str],
    valid_classes: Sequence[str],
    logger: logging.Logger,
) -> list[AnnotatorVote]:
    """Read one task file into votes. Every defect fails loudly and locally.

    ``utf-8-sig`` and ``newline=""`` between them accept Excel's "CSV UTF-8"
    export (which prepends a BOM, breaking a plain header comparison) and
    either CRLF or LF line endings.
    """
    where = f"{rater_id} pass {pass_no} ({path.name})"
    valid_class_set = set(valid_classes)
    votes: list[AnnotatorVote] = []
    seen_ids: dict[str, int] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_cols = set(TASK_FILE_COLUMNS) - set(reader.fieldnames or [])
        if missing_cols:
            raise AnnotationError(
                f"task file for {where} is malformed: missing columns {sorted(missing_cols)}"
            )

        for row_number, row in enumerate(reader, start=2):
            label_id = (row.get("label_id") or "").strip()
            if not label_id:
                raise AnnotationError(f"task file for {where} row {row_number}: empty label_id")
            if label_id not in valid_label_ids:
                raise AnnotationError(
                    f"task file for {where} row {row_number}: label_id {label_id!r} does not "
                    "match any candidate — task file and candidate set are out of sync"
                )
            if label_id in seen_ids:
                raise AnnotationError(
                    f"task file for {where} row {row_number}: label_id {label_id!r} already "
                    f"appears at row {seen_ids[label_id]}. A duplicated item would be counted "
                    "twice in the agreement statistic and silently resolved by whichever row "
                    "was read last."
                )
            seen_ids[label_id] = row_number

            applies_to = _parse_applies_to(row.get("applies_to", ""))
            flag = (row.get("differential_flag") or "").strip()
            rationale = (row.get("applies_to_rationale") or "").strip() or None
            notes = (row.get("notes") or "").strip() or None

            if not applies_to and not flag:
                status = VOTE_NOT_OBLIGATION if notes else VOTE_BLANK
                votes.append(
                    AnnotatorVote(
                        rater_id=rater_id,
                        pass_no=pass_no,
                        label_id=label_id,
                        applies_to=(),
                        differential_flag=None,
                        applies_to_rationale=rationale,
                        notes=notes,
                        status=status,
                        source_file=str(path),
                        row_number=row_number,
                    )
                )
                continue

            if not applies_to:
                raise AnnotationError(
                    f"task file for {where} row {row_number} (item {label_id}): "
                    "differential_flag given without applies_to — an item cannot have a "
                    "differential judgment without an applicability judgment"
                )
            if flag not in VALID_DIFFERENTIAL_FLAGS:
                raise AnnotationError(
                    f"task file for {where} row {row_number} (item {label_id}): "
                    f"differential_flag {flag!r} is not one of {sorted(VALID_DIFFERENTIAL_FLAGS)}"
                )

            unknown = [name for name in applies_to if name not in valid_class_set]
            if unknown:
                raise AnnotationError(
                    f"task file for {where} row {row_number} (item {label_id}): "
                    f"applies_to names {unknown} are not entity classes. Valid names are "
                    f"exactly: {sorted(valid_class_set)}. Spelling must match the discovered "
                    "vocabulary or the label cannot be joined to the matrix."
                )

            votes.append(
                AnnotatorVote(
                    rater_id=rater_id,
                    pass_no=pass_no,
                    label_id=label_id,
                    applies_to=applies_to,
                    differential_flag=flag,
                    applies_to_rationale=rationale,
                    notes=notes,
                    status=VOTE_VOTED,
                    source_file=str(path),
                    row_number=row_number,
                )
            )

    counts = vote_status_counts(votes)
    logger.info(
        "annotation: read %s — %d voted, %d blank, %d not_obligation",
        where, counts[VOTE_VOTED], counts[VOTE_BLANK], counts[VOTE_NOT_OBLIGATION],
    )
    return votes


def vote_status_counts(votes: Iterable[AnnotatorVote]) -> dict[str, int]:
    """Rows by status, with every status key always present."""
    counts = {VOTE_VOTED: 0, VOTE_BLANK: 0, VOTE_NOT_OBLIGATION: 0}
    for vote in votes:
        counts[vote.status] = counts.get(vote.status, 0) + 1
    return counts


def load_candidates(resolver: PathResolver) -> list[T1Label]:
    """The pilot candidate set from ``data/benchmark/pilot_candidates.jsonl``."""
    path = resolver.read_path("benchmark", "pilot_candidates.jsonl")
    return [T1Label.from_dict(row) for row in read_jsonl(path)]


def load_votes(
    cfg: Mapping[str, Any],
    *,
    candidates: Iterable[T1Label] | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    valid_entity_classes: Sequence[str] | None = None,
) -> list[AnnotatorVote]:
    """Read every configured rater's file into immutable per-pass votes.

    Reads, in order: the primary's pass-1 file, their pass-2 file when it
    exists, then each configured second rater's file as pass 1. Files
    belonging to people who are not on the current roster (the superseded
    three-person roster's ``annotation_akash.csv`` and ``annotation_meer.csv``)
    are ignored with a warning and **never deleted** — they may yet hold work,
    and adding that person to ``second_raters`` picks their file straight up.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    if candidates is None:
        candidates = load_candidates(resolver)
    valid_label_ids = {label.label_id for label in candidates}

    if valid_entity_classes is None:
        valid_entity_classes = load_entity_class_names(resolver, cfg=cfg)

    primary = primary_annotator(cfg)
    wanted: list[tuple[str, int, str]] = [(primary, 1, f"annotation_{primary}.csv")]
    pass2_name = f"annotation_{primary}_pass2.csv"
    wanted.append((primary, 2, pass2_name))
    for rater in second_raters(cfg):
        if rater == primary:
            continue
        wanted.append((rater, 1, f"annotation_{rater}.csv"))

    expected_names = {name for _, _, name in wanted}
    votes: list[AnnotatorVote] = []

    for rater_id, pass_no, filename in wanted:
        path = resolver.find_read_path("benchmark", "tasks", filename)
        if path is None:
            if pass_no == 2:
                logger.info(
                    "annotation: no pass-2 file yet for %s (%s) — retest not started",
                    rater_id, filename,
                )
            else:
                logger.warning("annotation: no task file for %s (%s) — skipping", rater_id, filename)
            continue
        votes.extend(
            _read_vote_file(
                Path(path),
                rater_id=rater_id,
                pass_no=pass_no,
                valid_label_ids=valid_label_ids,
                valid_classes=valid_entity_classes,
                logger=logger,
            )
        )

    tasks_dir = resolver.find_read_path("benchmark", "tasks")
    if tasks_dir is not None:
        for path in sorted(Path(tasks_dir).glob("annotation_*.csv")):
            if path.name in expected_names:
                continue
            logger.warning(
                "annotation: ignoring %s — not a configured rater under the single-expert "
                "protocol. The file is left untouched; add that person to "
                "config.benchmark.second_raters to have it read.",
                path.name,
            )

    return votes


def load_ai_diagnostic_votes(
    cfg: Mapping[str, Any],
    *,
    candidates: Iterable[T1Label] | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    valid_entity_classes: Sequence[str] | None = None,
) -> list[AnnotatorVote]:
    """Read every configured AI-assisted file as a diagnostic, never as a rater.

    The returned votes carry an :data:`AI_RATER_PREFIX` rater id, which is not
    a legal rater name, so a vote from here cannot be confused with a human's
    anywhere downstream. They are deliberately **not** returned by
    :func:`load_votes`: a caller has to ask for them by name.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    files = ai_diagnostic_files(cfg)
    if not files:
        return []

    if candidates is None:
        candidates = load_candidates(resolver)
    valid_label_ids = {label.label_id for label in candidates}
    if valid_entity_classes is None:
        valid_entity_classes = load_entity_class_names(resolver, cfg=cfg)

    votes: list[AnnotatorVote] = []
    for relative in files:
        parts = Path(relative).parts
        path = resolver.find_read_path("benchmark", *parts)
        if path is None:
            logger.warning("annotation: AI diagnostic file %s not found — skipping", relative)
            continue
        rater_id = f"{AI_RATER_PREFIX}{Path(relative).stem}"
        logger.warning(
            "annotation: reading %s as a human-AI DIAGNOSTIC under rater id %r. These votes "
            "are excluded from pairwise kappa, Fleiss' kappa and every promotion.",
            relative, rater_id,
        )
        votes.extend(
            _read_vote_file(
                Path(path), rater_id=rater_id, pass_no=1,
                valid_label_ids=valid_label_ids, valid_classes=valid_entity_classes,
                logger=logger,
            )
        )
    return votes


def persist_votes(
    votes: Iterable[AnnotatorVote],
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
) -> str:
    """Write every raw vote to ``data/benchmark/pilot_votes.jsonl``."""
    resolver = resolver or PathResolver.from_config(cfg)
    path = resolver.write_path("benchmark", VOTES_FILENAME)
    write_jsonl(path, [vote.to_dict() for vote in votes])
    return str(path)


# -- adjudication -------------------------------------------------------------


def _vote_column_prefix(vote_key: str) -> str:
    return vote_key.replace(":", "_")


def adjudication_task_path(cfg: Mapping[str, Any], resolver: PathResolver) -> Path:
    return resolver.write_path(
        "benchmark", "tasks", f"adjudication_{primary_annotator(cfg)}.csv"
    )


def build_adjudication_tasks(
    labels: Iterable[T1Label],
    votes: Iterable[AnnotatorVote],
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Write the adjudication file for every ``needs-adjudication`` item.

    Each row shows every vote side by side — which is the point: adjudication
    is a written decision between specific recorded alternatives, not a third
    guess made in ignorance of the first two.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    votes = list(votes)
    labels = list(labels)
    by_id = {label.label_id: label for label in labels}

    needs = [
        label.label_id
        for label in labels
        if (label.provenance or "").endswith(f":{ROUTE_NEEDS_ADJUDICATION}")
    ]

    vote_keys = sorted({vote.rater_key for vote in votes if vote.is_decided})
    columns = ["label_id", "span_text"]
    for key in vote_keys:
        prefix = _vote_column_prefix(key)
        columns += [f"{prefix}_applies_to", f"{prefix}_differential_flag", f"{prefix}_rationale"]
    columns += list(ADJUDICATION_INPUT_COLUMNS)

    votes_by_item: dict[str, dict[str, AnnotatorVote]] = {}
    for vote in votes:
        votes_by_item.setdefault(vote.label_id, {})[vote.rater_key] = vote

    rows: list[dict[str, str]] = []
    for label_id in sorted(needs):
        label = by_id[label_id]
        span = label.obligation_span
        row = {
            "label_id": label_id,
            "span_text": (span.text if span else "") or "",
            **{column: "" for column in ADJUDICATION_INPUT_COLUMNS},
        }
        for key in vote_keys:
            prefix = _vote_column_prefix(key)
            vote = votes_by_item.get(label_id, {}).get(key)
            if vote is None:
                row[f"{prefix}_applies_to"] = ""
                row[f"{prefix}_differential_flag"] = ""
                row[f"{prefix}_rationale"] = ""
            elif vote.status == VOTE_NOT_OBLIGATION:
                row[f"{prefix}_applies_to"] = ""
                row[f"{prefix}_differential_flag"] = VOTE_NOT_OBLIGATION
                row[f"{prefix}_rationale"] = vote.notes or ""
            else:
                row[f"{prefix}_applies_to"] = APPLIES_TO_SEPARATOR.join(vote.applies_to)
                row[f"{prefix}_differential_flag"] = vote.differential_flag or ""
                row[f"{prefix}_rationale"] = vote.applies_to_rationale or ""
        rows.append(row)

    path = adjudication_task_path(cfg, resolver)
    guard_task_overwrite(
        path, force=force, logger=logger, input_columns=ADJUDICATION_INPUT_COLUMNS
    )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("annotation: adjudication file written with %d item(s): %s", len(rows), path)
    return {"path": str(path), "items": len(rows), "columns": columns}


def load_adjudications(
    cfg: Mapping[str, Any],
    *,
    candidates: Iterable[T1Label] | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    valid_entity_classes: Sequence[str] | None = None,
) -> dict[str, Adjudication]:
    """Read the adjudication file. A decision without a reason is refused.

    ``adjudication_rationale`` is mandatory whenever anything else on the row
    is filled: an adjudicated item overrides recorded disagreement, and an
    override with no written reason is indistinguishable from a typo when the
    paper has to defend it.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    path = resolver.find_read_path(
        "benchmark", "tasks", f"adjudication_{primary_annotator(cfg)}.csv"
    )
    if path is None:
        logger.info("annotation: no adjudication file — nothing to read")
        return {}

    if candidates is None:
        candidates = load_candidates(resolver)
    valid_label_ids = {label.label_id for label in candidates}

    if valid_entity_classes is None:
        valid_entity_classes = load_entity_class_names(resolver, cfg=cfg)
    valid_class_set = set(valid_entity_classes)

    primary = primary_annotator(cfg)
    where = f"{primary} adjudication ({Path(path).name})"
    results: dict[str, Adjudication] = {}

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_cols = set(ADJUDICATION_INPUT_COLUMNS) | {"label_id"}
        missing_cols -= set(reader.fieldnames or [])
        if missing_cols:
            raise AnnotationError(
                f"adjudication file for {where} is malformed: missing columns {sorted(missing_cols)}"
            )

        for row_number, row in enumerate(reader, start=2):
            label_id = (row.get("label_id") or "").strip()
            if not label_id:
                raise AnnotationError(
                    f"adjudication file for {where} row {row_number}: empty label_id"
                )
            if label_id not in valid_label_ids:
                raise AnnotationError(
                    f"adjudication file for {where} row {row_number}: label_id {label_id!r} "
                    "does not match any candidate — adjudication file and candidate set are "
                    "out of sync"
                )
            if label_id in results:
                raise AnnotationError(
                    f"adjudication file for {where} row {row_number}: label_id {label_id!r} "
                    "appears more than once"
                )

            applies_to = _parse_applies_to(row.get("final_applies_to", ""))
            flag = (row.get("final_differential_flag") or "").strip()
            rationale = (row.get("adjudication_rationale") or "").strip()
            not_obligation = (row.get("final_not_obligation") or "").strip().lower() in (
                "yes", "y", "true", "1",
            )

            if not any((applies_to, flag, rationale, not_obligation)):
                continue  # untouched row: the item stays in_review

            if not rationale:
                raise AnnotationError(
                    f"adjudication file for {where} row {row_number} (item {label_id}): "
                    "adjudication_rationale is empty. An adjudication overrides recorded "
                    "disagreement, so the written reason is mandatory — leave the whole row "
                    "blank to defer the item instead."
                )

            if not_obligation:
                if applies_to or flag:
                    raise AnnotationError(
                        f"adjudication file for {where} row {row_number} (item {label_id}): "
                        "final_not_obligation is set alongside final_applies_to / "
                        "final_differential_flag. An item is either not an obligation or it "
                        "has an applicability judgment, not both."
                    )
                results[label_id] = Adjudication(
                    label_id=label_id, applies_to=(), differential_flag=None,
                    rationale=rationale, not_obligation=True,
                    source_file=str(path), row_number=row_number,
                )
                continue

            if not applies_to:
                raise AnnotationError(
                    f"adjudication file for {where} row {row_number} (item {label_id}): "
                    "final_differential_flag given without final_applies_to — an item cannot "
                    "have a differential judgment without an applicability judgment"
                )
            if flag not in VALID_DIFFERENTIAL_FLAGS:
                raise AnnotationError(
                    f"adjudication file for {where} row {row_number} (item {label_id}): "
                    f"final_differential_flag {flag!r} is not one of "
                    f"{sorted(VALID_DIFFERENTIAL_FLAGS)}"
                )
            unknown = [name for name in applies_to if name not in valid_class_set]
            if unknown:
                raise AnnotationError(
                    f"adjudication file for {where} row {row_number} (item {label_id}): "
                    f"final_applies_to names {unknown} are not entity classes. Valid names "
                    f"are exactly: {sorted(valid_class_set)}."
                )

            results[label_id] = Adjudication(
                label_id=label_id, applies_to=applies_to, differential_flag=flag,
                rationale=rationale, not_obligation=False,
                source_file=str(path), row_number=row_number,
            )

    logger.info("annotation: %d adjudicated item(s) read from %s", len(results), path)
    return results


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


def cohen_kappa(
    pairs: Sequence[tuple[str, str]], categories: Sequence[str] = FLAG_CATEGORIES
) -> float | str:
    """Cohen's kappa for two raters (or two passes) over paired categorical calls.

    ``(p_o - p_e) / (1 - p_e)``, with ``p_e`` the chance agreement implied by
    the two raters' own marginals. Returns :data:`NOT_YET_MEASURED` when there
    are no pairs or when ``p_e`` is 1.0 (both sides unanimous on one category,
    so the denominator vanishes) — never 0.0, which is a real reading meaning
    "no better than chance".
    """
    pairs = [(a, b) for a, b in pairs]
    if not pairs:
        return NOT_YET_MEASURED

    n = len(pairs)
    p_o = sum(1 for a, b in pairs if a == b) / n

    p_e = 0.0
    for category in categories:
        p_a = sum(1 for a, _ in pairs if a == category) / n
        p_b = sum(1 for _, b in pairs if b == category) / n
        p_e += p_a * p_b

    if abs(1.0 - p_e) < 1e-12:
        return NOT_YET_MEASURED
    return (p_o - p_e) / (1.0 - p_e)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile over an already-sorted sequence."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[int(position)]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def bootstrap_kappa_ci95(
    pairs: Sequence[tuple[str, str]],
    *,
    seed: int,
    resamples: int,
    categories: Sequence[str] = FLAG_CATEGORIES,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Percentile bootstrap over items for Cohen's kappa.

    Resamples that come back undefined (every resampled item landing on one
    category, so ``p_e`` is 1.0) are **skipped and counted**, not silently
    treated as zero. At pilot n that share can be large, and the report says
    how many were dropped so the interval is read for what it is.
    """
    n = len(pairs)
    if n < 2 or resamples < 1:
        return {
            "ci95": NOT_YET_MEASURED,
            "reason": (
                f"{NOT_YET_MEASURED} — a bootstrap interval needs at least 2 compared items, "
                f"got {n}"
            ),
            "resamples_requested": int(resamples),
            "resamples_used": 0,
            "resamples_skipped_undefined": 0,
        }

    rng = random.Random(seed)
    values: list[float] = []
    skipped = 0
    for _ in range(resamples):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        kappa = cohen_kappa(sample, categories)
        if isinstance(kappa, str):
            skipped += 1
        else:
            values.append(kappa)

    if skipped and logger is not None:
        logger.warning(
            "agreement: %d of %d bootstrap resamples were undefined (expected agreement 1.0) "
            "and were skipped rather than counted as zero",
            skipped, resamples,
        )

    if not values:
        return {
            "ci95": NOT_YET_MEASURED,
            "reason": (
                f"{NOT_YET_MEASURED} — every one of the {resamples} resamples was undefined "
                "(expected agreement 1.0)"
            ),
            "resamples_requested": int(resamples),
            "resamples_used": 0,
            "resamples_skipped_undefined": skipped,
        }

    values.sort()
    return {
        "ci95": [_percentile(values, 0.025), _percentile(values, 0.975)],
        "seed": int(seed),
        "resamples_requested": int(resamples),
        "resamples_used": len(values),
        "resamples_skipped_undefined": skipped,
    }


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 1.0


def _by_item(votes: Iterable[AnnotatorVote]) -> dict[str, AnnotatorVote]:
    return {vote.label_id: vote for vote in votes}


def _comparison_block(
    left: Mapping[str, AnnotatorVote],
    right: Mapping[str, AnnotatorVote],
    *,
    cfg: Mapping[str, Any],
    label: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Every paired statistic for one comparison, each named for what it is."""
    agreement = _agreement_cfg(cfg)
    seed = int(agreement.get("bootstrap_seed", 0))
    resamples = int(agreement.get("bootstrap_resamples", 1000))

    common = sorted(set(left) & set(right))
    decided = [i for i in common if left[i].is_decided and right[i].is_decided]
    both_voted = [i for i in common if left[i].status == VOTE_VOTED and right[i].status == VOTE_VOTED]

    not_obligation_consistency: Any = NOT_YET_MEASURED
    if decided:
        matched = sum(1 for i in decided if left[i].status == right[i].status)
        not_obligation_consistency = {
            "n_items_decided_in_both": len(decided),
            "both_agree_on_not_obligation_vs_obligation": matched,
            "rate": matched / len(decided),
        }

    if not both_voted:
        return {
            "comparison": label,
            "n_items": 0,
            "status": (
                f"{NOT_YET_MEASURED} — no item has a 'voted' row on both sides of this "
                "comparison yet"
            ),
            "not_obligation_consistency": not_obligation_consistency,
            "disagreement_categories": {"flag_only": 0, "applies_to_only": 0, "both": 0, "none": 0},
        }

    flag_pairs = [
        (left[i].differential_flag or "", right[i].differential_flag or "") for i in both_voted
    ]
    unlabelled = DifferentialFlag.UNLABELLED.value
    excl_pairs = [(a, b) for a, b in flag_pairs if a != unlabelled and b != unlabelled]

    exact = sum(1 for i in both_voted if set(left[i].applies_to) == set(right[i].applies_to))
    jaccards = [_jaccard(left[i].applies_to, right[i].applies_to) for i in both_voted]

    categories = {"flag_only": 0, "applies_to_only": 0, "both": 0, "none": 0}
    for i in both_voted:
        flag_differs = left[i].differential_flag != right[i].differential_flag
        set_differs = set(left[i].applies_to) != set(right[i].applies_to)
        if flag_differs and set_differs:
            categories["both"] += 1
        elif flag_differs:
            categories["flag_only"] += 1
        elif set_differs:
            categories["applies_to_only"] += 1
        else:
            categories["none"] += 1

    return {
        "comparison": label,
        "n_items": len(both_voted),
        "cohen_kappa_flag": cohen_kappa(flag_pairs),
        "cohen_kappa_flag_excl_unlabelled": cohen_kappa(excl_pairs),
        "n_items_excl_unlabelled": len(excl_pairs),
        "raw_flag_agreement": sum(1 for a, b in flag_pairs if a == b) / len(flag_pairs),
        "applies_to_exact_match_rate": exact / len(both_voted),
        "applies_to_mean_jaccard": sum(jaccards) / len(jaccards),
        "kappa_bootstrap_ci95": bootstrap_kappa_ci95(
            flag_pairs, seed=seed, resamples=resamples, logger=logger
        ),
        "not_obligation_consistency": not_obligation_consistency,
        "disagreement_categories": categories,
    }


def _rater_pass1(votes: Sequence[AnnotatorVote], rater: str) -> dict[str, AnnotatorVote]:
    """One rater's pass-1 votes by item. The primary's pass 1 is their vote."""
    return _by_item(v for v in votes if v.rater_id == rater and v.pass_no == 1)


def pairwise_agreement(
    votes: Sequence[AnnotatorVote],
    raters: Sequence[str],
    cfg: Mapping[str, Any],
    *,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Cohen's kappa and friends for every pair of human raters.

    This is the statistic the pilot was always supposed to produce and the
    superseded tooling could not: two people labelling the same item, compared
    without either overwriting the other. For the primary annotator it is pass
    1 that enters the comparison, so a pair is never contaminated by the
    retest.
    """
    blocks: dict[str, Any] = {}
    for left, right in itertools.combinations(sorted(raters), 2):
        blocks[f"{left}__vs__{right}"] = _comparison_block(
            _rater_pass1(votes, left), _rater_pass1(votes, right),
            cfg=cfg, label=f"{left} vs {right} (independent human raters)", logger=logger,
        )
    return blocks


def not_obligation_agreement(
    votes: Sequence[AnnotatorVote], raters: Sequence[str]
) -> dict[str, Any]:
    """How often the human raters agree that an item is not an obligation.

    Reported separately from the flag kappa because it is a different question
    — whether the extractor's candidate is an obligation at all — and it is the
    one the pilot is best placed to answer, candidate precision being exactly
    what a keyword heuristic gets wrong.
    """
    by_item: dict[str, dict[str, AnnotatorVote]] = {}
    for vote in votes:
        if vote.pass_no != 1 or vote.rater_id not in raters or not vote.is_decided:
            continue
        by_item.setdefault(vote.label_id, {})[vote.rater_id] = vote

    complete = {i: per for i, per in by_item.items() if len(per) >= 2}
    if not complete:
        return {
            "status": f"{NOT_YET_MEASURED} — no item was decided by two or more human raters",
            "n_items": 0,
        }

    unanimous_obligation = unanimous_not = split = 0
    for per in complete.values():
        statuses = {v.status for v in per.values()}
        if statuses == {VOTE_NOT_OBLIGATION}:
            unanimous_not += 1
        elif statuses == {VOTE_VOTED}:
            unanimous_obligation += 1
        else:
            split += 1

    return {
        "n_items": len(complete),
        "raters": sorted(raters),
        "unanimous_is_an_obligation": unanimous_obligation,
        "unanimous_not_an_obligation": unanimous_not,
        "split": split,
        "agreement_rate": (unanimous_obligation + unanimous_not) / len(complete),
    }


def human_ai_diagnostic(
    human_votes: Sequence[AnnotatorVote],
    ai_votes: Sequence[AnnotatorVote],
    raters: Sequence[str],
    cfg: Mapping[str, Any],
    *,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Each human rater against each AI-assisted file.

    **This is not a reliability statistic and must never be reported as one.**
    An AI label is not an independent observer of the same construct: it is a
    model's output on the same text, and agreement with it measures how
    model-like the human's labels are, not how reliable they are. It is
    computed because a high value is worth knowing about — it would suggest
    either that the task is easy or that the human labels were not independent
    — not because it licenses any claim.
    """
    ai_raters = sorted({v.rater_id for v in ai_votes})
    if not ai_raters:
        return {
            "status": f"{NOT_YET_MEASURED} — no AI-assisted file is configured",
            "is_a_reliability_statistic": False,
        }

    combined = list(human_votes) + list(ai_votes)
    blocks: dict[str, Any] = {}
    for human in sorted(raters):
        for ai in ai_raters:
            blocks[f"{human}__vs__{ai}"] = _comparison_block(
                _rater_pass1(combined, human), _rater_pass1(combined, ai),
                cfg=cfg, label=f"{human} vs {ai} (human-AI DIAGNOSTIC, not reliability)",
                logger=logger,
            )
    return {
        "is_a_reliability_statistic": False,
        "warning": (
            "NOT a reliability statistic. An AI-assisted file is not an independent rater; "
            "agreement with it measures how model-like the human labels are, not how "
            "reliable they are. It never enters pairwise or Fleiss' kappa and can never "
            "promote an item."
        ),
        "comparisons": blocks,
    }


#: What an applies_to figure is replaced with when the column is not replicated.
APPLIES_TO_NOT_REPLICATED = (
    "NOT A MEASUREMENT — applies_to was pre-filled from a single source and copied to every "
    "rater's file. Each rater judged differential_flag only, so there is nothing to agree "
    "about here and the exact-match rate would read 1.0 by construction."
)


def _suppress_applies_to_figures(block: Any) -> Any:
    """Blank the applies_to agreement figures in a comparison block, in place.

    Called when :func:`judgment_column_independence` reports that the column
    has one source. The figures are replaced rather than deleted so that a
    reader who goes looking for them finds the reason instead of a gap — and a
    downstream consumer gets a string where it expected a float, which fails
    loudly rather than quietly plotting a 1.0.
    """
    if not isinstance(block, dict):
        return block
    for key in ("applies_to_exact_match_rate", "applies_to_mean_jaccard"):
        if key in block:
            block[key] = APPLIES_TO_NOT_REPLICATED
    categories = block.get("disagreement_categories")
    if isinstance(categories, dict):
        categories["note"] = (
            "applies_to_only and both are 0 by construction: every rater held the same "
            "applies_to. Only flag_only and none carry information."
        )
    return block


def measure_agreement(
    votes: Iterable[AnnotatorVote],
    cfg: Mapping[str, Any] | None = None,
    *,
    logger: logging.Logger | None = None,
    resolver: PathResolver | None = None,
    ai_votes: Iterable[AnnotatorVote] | None = None,
    raters: Sequence[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Reliability statistics, computed from raw votes and never from labels.

    Two comparisons, each labelled for what it actually measures:

    * ``test_retest`` — the primary's pass 1 against their own blind pass 2.
      This is **stability of one person's judgment over time**, not agreement
      between people, and nothing here calls it inter-annotator agreement.
    * ``second_rater`` — the primary's pass 1 against each second rater.

    ``fleiss_kappa_flag`` appears only when three or more real raters have
    labelled the same items. Below that there is no key at all, so nothing
    downstream can surface a Fleiss number that was never computable.
    """
    cfg = cfg or {}
    votes = list(votes)
    primary = primary_annotator(cfg) if cfg.get("benchmark") else None

    unlabelled_votes: dict[str, int] = {}
    for vote in votes:
        if vote.status == VOTE_VOTED and vote.differential_flag == DifferentialFlag.UNLABELLED.value:
            unlabelled_votes[vote.rater_key] = unlabelled_votes.get(vote.rater_key, 0) + 1
    for vote in votes:
        unlabelled_votes.setdefault(vote.rater_key, 0)

    primary_p1 = _by_item(v for v in votes if v.rater_id == primary and v.pass_no == 1)
    primary_p2 = _by_item(v for v in votes if v.rater_id == primary and v.pass_no == 2)

    if primary_p2:
        test_retest = _comparison_block(
            primary_p1, primary_p2, cfg=cfg,
            label=f"{primary} pass 1 vs {primary} pass 2 (blind retest)", logger=logger,
        )
    else:
        test_retest = {
            "comparison": f"{primary} pass 1 vs {primary} pass 2 (blind retest)",
            "n_items": 0,
            "status": (
                f"{NOT_YET_MEASURED} — pass 2 has not been ingested; run `retest` on or after "
                "the earliest allowed date, then `ingest --pass 2`"
            ),
        }

    configured_seconds = [r for r in second_raters(cfg) if r != primary] if cfg.get("benchmark") else []
    rater_blocks: dict[str, Any] = {}
    raters_with_votes = sorted({v.rater_id for v in votes if v.status == VOTE_VOTED})

    for rater in configured_seconds:
        their_votes = _by_item(v for v in votes if v.rater_id == rater and v.pass_no == 1)
        if not their_votes:
            rater_blocks[rater] = {
                "comparison": f"{primary} pass 1 vs {rater}",
                "n_items": 0,
                "status": f"{NOT_YET_MEASURED} — {rater} has not returned a task file",
            }
            continue
        rater_blocks[rater] = _comparison_block(
            primary_p1, their_votes, cfg=cfg,
            label=f"{primary} pass 1 vs {rater}", logger=logger,
        )

    if not configured_seconds:
        second_rater: dict[str, Any] = {
            "status": f"{NOT_YET_MEASURED} — no second rater configured",
            "raters": {},
        }
    else:
        second_rater = {"raters": rater_blocks}

    # Fleiss' kappa needs >= 3 real raters. Below that the key is absent
    # entirely: a NOT-YET-MEASURED "fleiss" entry is still something a reader
    # can mistake for a statistic this protocol is able to produce.
    # There is exactly ONE Fleiss key in the output, `fleiss_three_raters`,
    # added below over human raters only. The P1-005 version lived here and
    # counted the configured roster, which would have emitted a three-rater
    # figure for two humans plus an ai_assisted one — the precise thing the
    # provenance rule exists to prevent.

    # -- P1-004: three independent human raters ------------------------------
    #
    # `raters` is the list of people whose labels are their own work. It is
    # passed in (from human_raters()) rather than read off the roster here, so
    # an ai_assisted rater is filtered out at exactly one place and cannot
    # re-enter through any of the blocks below.
    if raters is None:
        raters = human_raters(cfg, resolver, logger=logger) if (resolver and cfg.get("benchmark")) \
            else ([primary, *configured_seconds] if primary else [])
    humans = [r for r in raters if not r.startswith(AI_RATER_PREFIX)]
    human_votes = [v for v in votes if v.rater_id in humans]
    ai_votes = list(ai_votes or [])

    # Two different populations, and conflating them loses a real case. A flag
    # kappa needs raters who cast a FLAG, so it uses `voting_humans`. Whether
    # an item is an obligation at all is answered just as much by a rater who
    # said "not an obligation", so that block uses `deciding_humans`.
    voting_humans = sorted({
        v.rater_id for v in human_votes if v.pass_no == 1 and v.status == VOTE_VOTED
    })
    deciding_humans = sorted({
        v.rater_id for v in human_votes if v.pass_no == 1 and v.is_decided
    })

    result = {
        "protocol": (cfg.get("benchmark", {}) or {}).get("promotion_policy", "single_expert_retest"),
        "primary_annotator": primary,
        "second_raters_configured": configured_seconds,
        "human_raters": humans,
        "human_raters_with_votes": voting_humans,
        "raters_with_votes": raters_with_votes,
        "interpretation": (
            "test_retest measures the stability of ONE annotator's judgment across two blind "
            "passes; it is not inter-annotator agreement. `pairwise` and `fleiss_three_raters` "
            "ARE inter-rater agreement, over independent human raters only. "
            "`human_ai_diagnostic` is neither and must not be reported as a reliability figure."
        ),
        "test_retest": test_retest,
        "second_rater": second_rater,
        "unlabelled_votes": dict(sorted(unlabelled_votes.items())),
        "pairwise": (
            pairwise_agreement(human_votes, voting_humans, cfg, logger=logger)
            if len(voting_humans) >= 2
            else {
                "status": (
                    f"{NOT_YET_MEASURED} — pairwise agreement needs 2 or more human raters "
                    f"with votes, found {len(voting_humans)}"
                )
            }
        ),
        "not_obligation_agreement": not_obligation_agreement(human_votes, deciding_humans),
        "human_ai_diagnostic": human_ai_diagnostic(
            human_votes, ai_votes, voting_humans, cfg, logger=logger
        ),
    }

    # Fleiss' kappa needs three or more real human raters. Below that there is
    # no key at all, so nothing downstream can surface a number that was never
    # computable — and an AI file can never make up the third.
    if len(voting_humans) >= 3:
        result["fleiss_three_raters"] = _fleiss_over_raters(human_votes, voting_humans)

    # If a judgment column turns out to have a single source, every agreement
    # figure computed from it is arithmetic on one answer counted N times.
    # Suppressing those figures here, rather than trusting a reader to notice
    # the caveat, is the only way the number cannot reach a paper.
    independence = judgment_column_independence(human_votes, deciding_humans)
    result["column_independence"] = independence
    if independence.get("applies_to_independent") is False:
        result["applies_to_replicated"] = False
        for block in list(result.get("pairwise", {}).values()):
            _suppress_applies_to_figures(block)
        for block in list((result.get("second_rater", {}) or {}).get("raters", {}).values()):
            _suppress_applies_to_figures(block)
        _suppress_applies_to_figures(result.get("test_retest"))
        if logger is not None:
            logger.warning(
                "agreement: applies_to is identical across every rater on %d/%d multi-class "
                "items — the column has one source, so its agreement figures are suppressed. "
                "Only differential_flag agreement is reported.",
                independence.get("multi_class_items_identical_across_all_raters", 0),
                independence.get("multi_class_items", 0),
            )
    else:
        result["applies_to_replicated"] = True

    return result


def _fleiss_over_raters(votes: Sequence[AnnotatorVote], raters: Sequence[str]) -> dict[str, Any]:
    """Fleiss' kappa over items every one of ``raters`` voted on (pass 1)."""
    by_item: dict[str, dict[str, AnnotatorVote]] = {}
    for vote in votes:
        if vote.pass_no != 1 or vote.status != VOTE_VOTED or vote.rater_id not in raters:
            continue
        by_item.setdefault(vote.label_id, {})[vote.rater_id] = vote

    complete = [
        item for item, per_rater in sorted(by_item.items()) if len(per_rater) == len(raters)
    ]
    if not complete:
        return {
            "kappa": NOT_YET_MEASURED,
            "n_items": 0,
            "raters": list(raters),
            "reason": f"{NOT_YET_MEASURED} — no item was voted on by all {len(raters)} raters",
        }

    index = {category: i for i, category in enumerate(FLAG_CATEGORIES)}
    matrix = []
    for item in complete:
        row = [0] * len(FLAG_CATEGORIES)
        for vote in by_item[item].values():
            row[index[vote.differential_flag]] += 1
        matrix.append(row)

    return {
        "kappa": fleiss_kappa(matrix),
        "n_items": len(complete),
        "raters": list(raters),
    }


def disagreement_rows(
    votes: Iterable[AnnotatorVote], labels: Iterable[T1Label]
) -> tuple[list[str], list[dict[str, str]]]:
    """Per-item vote comparison for ``reports/phase1_pilot_disagreements.csv``.

    Carries **no** ``span_text``: the report directory is tracked, and RBI text
    is not redistributable (R6). Items are referenced by ``label_id``, which
    resolves against the gitignored candidate file.
    """
    votes = list(votes)
    labels = list(labels)
    vote_keys = sorted({vote.rater_key for vote in votes})

    columns = ["label_id"]
    for key in vote_keys:
        prefix = _vote_column_prefix(key)
        columns += [f"{prefix}_differential_flag", f"{prefix}_applies_to"]
    columns.append("category")

    by_item: dict[str, dict[str, AnnotatorVote]] = {}
    for vote in votes:
        by_item.setdefault(vote.label_id, {})[vote.rater_key] = vote

    route_of = {
        label.label_id: (label.provenance or "").rsplit(":", 1)[-1] for label in labels
    }

    rows: list[dict[str, str]] = []
    for label_id in sorted(by_item):
        row = {"label_id": label_id, "category": route_of.get(label_id, "")}
        for key in vote_keys:
            prefix = _vote_column_prefix(key)
            vote = by_item[label_id].get(key)
            if vote is None:
                row[f"{prefix}_differential_flag"] = ""
                row[f"{prefix}_applies_to"] = ""
            elif vote.status == VOTE_VOTED:
                row[f"{prefix}_differential_flag"] = vote.differential_flag or ""
                row[f"{prefix}_applies_to"] = APPLIES_TO_SEPARATOR.join(vote.applies_to)
            else:
                row[f"{prefix}_differential_flag"] = vote.status
                row[f"{prefix}_applies_to"] = ""
        rows.append(row)

    return columns, rows


# -- merge and promotion ------------------------------------------------------


def _route_provenance(primary: str, route: str) -> str:
    return f"{ANNOTATOR_PROVENANCE_PREFIX}{primary}:{route}"


def _merged_label(
    label: T1Label,
    *,
    primary: str,
    route: str,
    status: str,
    applies_to: Sequence[str],
    flag: str | None,
    rationale: str | None,
    notes: str | None,
    raters: Sequence[str],
    agreement_score: float | None,
) -> T1Label:
    """Build the single merged label for an item from its reconciled values."""
    if applies_to:
        # The only writer of applies_to, called exactly once per item.
        label = apply_annotation(
            label,
            annotator_id=primary,
            applies_to=list(applies_to),
            differential_flag=flag or DifferentialFlag.UNLABELLED.value,
            applies_to_rationale=rationale,
            notes=notes,
        )
    else:
        label = replace(
            label,
            applies_to=[],
            applies_to_rationale=rationale,
            differential_flag=DifferentialFlag.UNLABELLED.value,
            notes=notes,
        )

    return replace(
        label,
        label_status=status,
        annotator_ids=list(raters),
        annotation_count=len(raters),
        agreement_score=agreement_score,
        provenance=_route_provenance(primary, route),
    )


def merge_votes(
    candidates: Iterable[T1Label],
    votes: Iterable[AnnotatorVote],
    cfg: Mapping[str, Any],
    *,
    retest_ids: Iterable[str] | None = None,
    adjudications: Mapping[str, Adjudication] | None = None,
    logger: logging.Logger | None = None,
    human_rater_ids: Sequence[str] | None = None,
) -> list[T1Label]:
    """Build **one** merged label per item from that item's full vote set.

    This is the repair for the last-writer-wins defect: every vote is read
    together and reconciled once, rather than each rater's row being applied
    to the same label in turn. The validation route each item takes is
    recorded in ``provenance``, so a reader can always ask *why* an item is
    validated — retest-consistent, single-pass, or adjudicated.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    primary = primary_annotator(cfg)
    retest_ids = set(retest_ids or ())
    adjudications = adjudications or {}

    # Whose votes may promote an item. Defaults to the configured roster; the
    # CLI passes human_raters(), which drops anyone recorded as ai_assisted.
    # An AI diagnostic rater id can never appear here.
    humans = [
        r for r in (human_rater_ids if human_rater_ids is not None else configured_raters(cfg))
        if not r.startswith(AI_RATER_PREFIX)
    ]

    votes_by_item: dict[str, list[AnnotatorVote]] = {}
    dropped: set[str] = set()
    for vote in votes:
        # The firewall sits here, before anything is routed, so it covers every
        # branch below rather than only the consensus one. A vote from an AI
        # diagnostic file, or from a rater whose labels are recorded as
        # ai_assisted, never reaches a label at all — including through the
        # single-expert fallback, where an ai_assisted PRIMARY would otherwise
        # have promoted items on their own.
        if vote.rater_id.startswith(AI_RATER_PREFIX) or vote.rater_id not in humans:
            dropped.add(vote.rater_id)
            continue
        votes_by_item.setdefault(vote.label_id, []).append(vote)
    for rater in sorted(dropped):
        logger.warning(
            "merge: every vote from %r was excluded — not a human rater under the current "
            "label_source records. Their labels cannot promote any item.", rater,
        )

    merged: list[T1Label] = []
    for label in candidates:
        item_votes = votes_by_item.get(label.label_id, [])
        voted_raters = sorted({v.rater_id for v in item_votes if v.status == VOTE_VOTED})

        p1 = next(
            (v for v in item_votes if v.rater_id == primary and v.pass_no == 1 and v.is_decided),
            None,
        )
        p2 = next(
            (v for v in item_votes if v.rater_id == primary and v.pass_no == 2 and v.is_decided),
            None,
        )
        seconds = [v for v in item_votes if v.rater_id != primary and v.is_decided]

        in_retest = label.label_id in retest_ids
        agreement_score: float | None = None
        if in_retest and p1 is not None and p2 is not None:
            agreement_score = 1.0 if p1.judgment == p2.judgment else 0.0

        second_differs = p1 is not None and any(v.judgment != p1.judgment for v in seconds)

        adjudication = adjudications.get(label.label_id)
        if adjudication is not None:
            raters = sorted(set(voted_raters) | {primary})
            if adjudication.not_obligation:
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_ADJUDICATED,
                        status=LabelStatus.REJECTED.value, applies_to=(), flag=None,
                        rationale=None, notes=adjudication.rationale,
                        raters=[], agreement_score=agreement_score,
                    )
                )
            else:
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_ADJUDICATED,
                        status=LabelStatus.VALIDATED.value,
                        applies_to=adjudication.applies_to,
                        flag=adjudication.differential_flag,
                        rationale=adjudication.rationale, notes=None,
                        raters=raters, agreement_score=agreement_score,
                    )
                )
            continue

        if p1 is None and p2 is None and not seconds:
            merged.append(label)  # nothing voted: candidate, untouched
            continue

        # -- P1-004 consensus routing ------------------------------------
        #
        # With two or more independent human raters, promotion is a consensus
        # question rather than a retest question. An item validates only when
        # every human rater who made a call made the SAME call: "at least 2
        # agree AND nobody contradicts" is unanimity among those who voted,
        # and anything less goes to adjudication rather than being carried by
        # a majority. A 2-1 split is exactly the case a written adjudication
        # exists to resolve, and silently taking the majority would discard
        # the dissent that makes the disagreement informative.
        human_calls = {
            v.rater_id: v
            for v in item_votes
            if v.rater_id in humans and v.is_decided and v.pass_no == 1
        }
        if len(human_calls) >= 2:
            judgments = {v.judgment for v in human_calls.values()}
            agreeing = sorted(human_calls)
            retest_conflict = (
                p2 is not None and p1 is not None and p1.judgment != p2.judgment
            )
            provenance_ids = "+".join(agreeing)

            if len(judgments) > 1 or retest_conflict:
                reason = "raters disagree" if len(judgments) > 1 else "primary's retest differs"
                logger.info(
                    "merge: %s -> needs-adjudication (%s; %d human calls)",
                    label.label_id, reason, len(human_calls),
                )
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_NEEDS_ADJUDICATION,
                        status=LabelStatus.IN_REVIEW.value, applies_to=(), flag=None,
                        rationale=None, notes=None, raters=voted_raters,
                        agreement_score=agreement_score,
                    )
                )
                continue

            call = next(iter(human_calls.values()))
            consensus_provenance = (
                f"{ANNOTATOR_PROVENANCE_PREFIX}{ROUTE_CONSENSUS}:{provenance_ids}"
            )
            if call.status == VOTE_NOT_OBLIGATION:
                # Rejection is not promotion, so it keeps the ordinary
                # not-obligation provenance rather than the consensus form.
                # Overwriting it with `annotator:consensus:<ids>` would make
                # label_route() read the item as a consensus *validation* and
                # the route counts would stop adding up.
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_NOT_OBLIGATION,
                        status=LabelStatus.REJECTED.value, applies_to=(), flag=None,
                        rationale=None, notes=call.notes, raters=[],
                        agreement_score=agreement_score,
                    )
                )
            else:
                merged.append(
                    replace(
                        _merged_label(
                            label, primary=primary, route=ROUTE_CONSENSUS,
                            status=LabelStatus.VALIDATED.value, applies_to=call.applies_to,
                            flag=call.differential_flag, rationale=call.applies_to_rationale,
                            notes=call.notes, raters=agreeing,
                            agreement_score=agreement_score,
                        ),
                        provenance=consensus_provenance,
                    )
                )
            continue

        if p1 is None:
            # A second rater got there first, or only pass 2 exists. Either way
            # the primary's pass 1 — which the whole table is anchored on — is
            # missing, so the item is held rather than routed.
            logger.warning(
                "merge: %s has votes but no decided pass-1 row from %s — held at in_review",
                label.label_id, primary,
            )
            merged.append(
                _merged_label(
                    label, primary=primary, route=ROUTE_AWAITING_PRIMARY,
                    status=LabelStatus.IN_REVIEW.value, applies_to=(), flag=None,
                    rationale=None, notes=None, raters=voted_raters,
                    agreement_score=agreement_score,
                )
            )
            continue

        if in_retest and p2 is not None:
            if p1.judgment != p2.judgment or second_differs:
                route, status = ROUTE_NEEDS_ADJUDICATION, LabelStatus.IN_REVIEW.value
                merged.append(
                    _merged_label(
                        label, primary=primary, route=route, status=status,
                        applies_to=(), flag=None, rationale=None, notes=None,
                        raters=voted_raters, agreement_score=agreement_score,
                    )
                )
            elif p1.status == VOTE_NOT_OBLIGATION:
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_NOT_OBLIGATION,
                        status=LabelStatus.REJECTED.value, applies_to=(), flag=None,
                        rationale=None, notes=p1.notes, raters=[],
                        agreement_score=agreement_score,
                    )
                )
            else:
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_RETEST_CONSISTENT,
                        status=LabelStatus.VALIDATED.value, applies_to=p1.applies_to,
                        flag=p1.differential_flag, rationale=p1.applies_to_rationale,
                        notes=p1.notes, raters=voted_raters, agreement_score=agreement_score,
                    )
                )
            continue

        if in_retest:  # pass 2 not done yet
            if second_differs:
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_NEEDS_ADJUDICATION,
                        status=LabelStatus.IN_REVIEW.value, applies_to=(), flag=None,
                        rationale=None, notes=None, raters=voted_raters,
                        agreement_score=agreement_score,
                    )
                )
            elif p1.status == VOTE_NOT_OBLIGATION:
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_PASS1_ONLY,
                        status=LabelStatus.IN_REVIEW.value, applies_to=(), flag=None,
                        rationale=None, notes=p1.notes, raters=[],
                        agreement_score=agreement_score,
                    )
                )
            else:
                merged.append(
                    _merged_label(
                        label, primary=primary, route=ROUTE_PASS1_ONLY,
                        status=LabelStatus.IN_REVIEW.value, applies_to=p1.applies_to,
                        flag=p1.differential_flag, rationale=p1.applies_to_rationale,
                        notes=p1.notes, raters=voted_raters, agreement_score=agreement_score,
                    )
                )
            continue

        # Outside the retest set: pass 1 is the whole evidence base.
        if second_differs:
            merged.append(
                _merged_label(
                    label, primary=primary, route=ROUTE_NEEDS_ADJUDICATION,
                    status=LabelStatus.IN_REVIEW.value, applies_to=(), flag=None,
                    rationale=None, notes=None, raters=voted_raters,
                    agreement_score=agreement_score,
                )
            )
        elif p1.status == VOTE_NOT_OBLIGATION:
            merged.append(
                _merged_label(
                    label, primary=primary, route=ROUTE_NOT_OBLIGATION,
                    status=LabelStatus.REJECTED.value, applies_to=(), flag=None,
                    rationale=None, notes=p1.notes, raters=[],
                    agreement_score=agreement_score,
                )
            )
        else:
            merged.append(
                _merged_label(
                    label, primary=primary, route=ROUTE_SINGLE_PASS,
                    status=LabelStatus.VALIDATED.value, applies_to=p1.applies_to,
                    flag=p1.differential_flag, rationale=p1.applies_to_rationale,
                    notes=p1.notes, raters=voted_raters, agreement_score=agreement_score,
                )
            )

    return merged


def label_route(label: T1Label) -> str | None:
    """The validation route recorded in ``provenance``, if any.

    Two provenance shapes exist. The single-expert routes are
    ``annotator:<rater>:<route>``. A consensus item is
    ``annotator:consensus:<id>+<id>``, where the middle field is the literal
    word and the last field names the agreeing raters — so the route is read
    from the middle field in that case and the ids stay recoverable via
    :func:`consensus_raters`.
    """
    provenance = label.provenance or ""
    if not provenance.startswith(ANNOTATOR_PROVENANCE_PREFIX):
        return None
    parts = provenance.split(":")
    if len(parts) >= 3 and parts[1] == ROUTE_CONSENSUS:
        return ROUTE_CONSENSUS
    return parts[2] if len(parts) >= 3 else None


def consensus_raters(label: T1Label) -> list[str]:
    """The raters named in an ``annotator:consensus:<ids>`` provenance."""
    provenance = label.provenance or ""
    parts = provenance.split(":")
    if len(parts) >= 3 and parts[1] == ROUTE_CONSENSUS:
        return sorted(x for x in parts[2].split("+") if x)
    return []


def route_counts(labels: Iterable[T1Label]) -> dict[str, int]:
    """Items per validation route, with ``candidate`` for anything unvoted."""
    counts: dict[str, int] = {}
    for label in labels:
        key = label_route(label) or "unvoted-candidate"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def promote_validated(
    labels: Iterable[T1Label],
    cfg: Mapping[str, Any],
    *,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> list[T1Label]:
    """Confirm or withdraw each item's route-assigned status.

    Promotion is by **validation route**, never by counting raters — with one
    annotator there is nothing to count, and the superseded threshold rule
    would have promoted all 18 pilot items off three mutually contradictory
    task files.

    Two independent gates still run on anything routed to ``validated``: the
    tautology guard, and ``T1Label.validate()``. An item failing ``validate()``
    falls back to ``in_review`` with the reason logged — never
    warned-and-allowed.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)

    results: list[T1Label] = []
    promoted = withdrawn = 0

    for label in labels:
        # Runs before anything else, and on every label rather than only on the
        # ones claiming 'validated': a forged applies_to must raise here, not be
        # quietly downgraded to in_review and left in the set looking ordinary.
        assert_applies_to_is_annotator_sourced(label)

        if label.label_status != LabelStatus.VALIDATED.value:
            results.append(label)
            continue

        route = label_route(label)
        if route not in VALIDATING_ROUTES:
            logger.warning(
                "promotion: %s carries status 'validated' on route %r, which is not a "
                "validating route — withdrawn to in_review",
                label.label_id, route,
            )
            results.append(replace(label, label_status=LabelStatus.IN_REVIEW.value))
            withdrawn += 1
            continue

        errors = label.validate()
        if errors:
            logger.warning(
                "promotion: %s NOT promoted — validate() rejected it: %s", label.label_id, errors
            )
            results.append(replace(label, label_status=LabelStatus.IN_REVIEW.value))
            withdrawn += 1
            continue

        logger.info("promotion: %s validated via route %r", label.label_id, route)
        results.append(label)
        promoted += 1

    logger.info(
        "promote_validated: %d validated, %d withdrawn to in_review", promoted, withdrawn
    )
    return results


# -- persistence --------------------------------------------------------------


def persist_labels(
    labels: Iterable[T1Label],
    cfg: Mapping[str, Any],
    filename: str,
    *,
    resolver: PathResolver | None = None,
) -> str:
    """Write a label set to ``data/benchmark/<filename>``."""
    resolver = resolver or PathResolver.from_config(cfg)
    path = resolver.write_path("benchmark", filename)
    write_jsonl(path, [lbl.to_dict() for lbl in labels])
    return str(path)


def persist_candidates(
    labels: Iterable[T1Label],
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    force: bool = False,
    filename: str = "pilot_candidates.jsonl",
) -> str:
    """Write the candidate set, refusing to silently change which items exist.

    ``label_id`` is what links a hand-filled task file back to an item. If the
    candidate set is regenerated with a different id set, every existing
    annotation detaches — so a changed set is refused rather than written.
    """
    resolver = resolver or PathResolver.from_config(cfg)
    labels = list(labels)
    path = resolver.write_path("benchmark", filename)

    if path.exists() and not force:
        existing = {row.get("label_id") for row in read_jsonl(path)}
        incoming = {label.label_id for label in labels}
        if existing != incoming:
            added = sorted(incoming - existing)
            removed = sorted(existing - incoming)
            raise AnnotationError(
                f"refusing to overwrite {path}: the candidate label_id set has changed "
                f"({len(added)} added, {len(removed)} removed; first added {added[:3]}, first "
                f"removed {removed[:3]}). label_id is what links a filled task file back to "
                "an item, so rewriting the set detaches existing annotations. Pass "
                "--force-regenerate-tasks (force=True) if that is genuinely intended."
            )

    write_jsonl(path, [lbl.to_dict() for lbl in labels])
    return str(path)


# -- the composed ingest ------------------------------------------------------


def ingest_annotations(
    cfg: Mapping[str, Any],
    *,
    candidates: Iterable[T1Label] | None = None,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
    votes: Iterable[AnnotatorVote] | None = None,
    retest_ids: Iterable[str] | None = None,
    adjudications: Mapping[str, Adjudication] | None = None,
    valid_entity_classes: Sequence[str] | None = None,
    **kwargs: Any,
) -> list[T1Label]:
    """Read every task file back and merge it into one label per item.

    Convenience composition of :func:`load_votes`, :func:`merge_votes` and
    :func:`promote_validated`, for callers that want labels and nothing else.
    The CLI uses the three separately, because it also reports on the votes.
    """
    logger = logger or get_logger("benchmark.annotation", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    if candidates is None:
        candidates = load_candidates(resolver)
    candidates = list(candidates)

    if votes is None:
        votes = load_votes(
            cfg, candidates=candidates, resolver=resolver, logger=logger,
            valid_entity_classes=valid_entity_classes,
        )
    if retest_ids is None:
        retest_ids = load_retest_set(resolver)

    merged = merge_votes(
        candidates, votes, cfg, retest_ids=retest_ids,
        adjudications=adjudications, logger=logger,
    )
    return promote_validated(merged, cfg, logger=logger)
