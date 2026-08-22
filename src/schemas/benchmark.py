"""The T1 benchmark label contract.

T1 is the applicability- and amendment-aware obligation label set that carries
the project's research claims (RQ1 applicability, RQ2 differential obligations).
This module defines its shape only. No logic populates it here.

Two design rules are load-bearing and are enforced, not merely documented:

**1. ``applies_to`` is an annotation target, never a derived field.**
It is tempting to set ``applies_to`` to the entity class of the document a span
came from. That value is a tautology — it restates which file the text was in
and carries no independent signal — and a benchmark built that way cannot
support any applicability claim, because the "label" is definitionally implied
by the input. ``applies_to`` must come from a human annotator judging which
entity classes the obligation actually binds, which is frequently *not* the
class of the containing document (a Direction addressed to one class routinely
carves out or extends to others).

**2. ``differential_flag`` defaults to ``UNLABELLED``, not ``ABSENT``.**
Defaulting to ``ABSENT`` would silently convert "no cross-class match was
attempted or found" into the positive claim "this obligation has no differential
counterpart", inflating the absent class with unexamined items and biasing every
statistic computed over it. Unexamined and examined-and-found-absent are
different states and are kept distinct.

The same principle governs :class:`LabelStatus`: an item is ``CANDIDATE`` until
the required number of independent annotators have labelled it. Nothing in the
pipeline may promote an item to ``VALIDATED`` implicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

from src.schemas.base import ANNOTATION, BASE, MATRIX, SCRAPER, FieldSpec, SchemaRecord


class DifferentialFlag(str, Enum):
    """Whether an obligation differs across entity classes.

    ``UNLABELLED`` is the default and means no determination has been made. It
    is deliberately distinct from ``ABSENT``, which is a positive finding.
    """

    UNLABELLED = "unlabelled"
    SHARED = "shared"  # substantively the same obligation binds other classes
    CLASS_SPECIFIC = "class-specific"  # the obligation differs by entity class
    ABSENT = "absent"  # examined; no counterpart obligation exists elsewhere


class LabelStatus(str, Enum):
    """Where an item sits in the annotation lifecycle."""

    CANDIDATE = "candidate"  # machine-proposed, not yet human-validated
    IN_REVIEW = "in_review"  # some but not enough independent annotations
    VALIDATED = "validated"  # met the multi-annotator threshold
    REJECTED = "rejected"  # annotators judged it not an obligation


@dataclass
class ObligationSpan(SchemaRecord):
    """A character span within a paragraph that states an obligation.

    Stored as offsets into a paragraph rather than as copied text, so benchmark
    artifacts can be published without redistributing RBI text while remaining
    exactly reproducible by anyone holding the corpus.
    """

    paragraph_id: str
    document_id: str
    char_start: int
    char_end: int
    text: str | None = None
    matched_cue: str | None = None

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "paragraph_id", (str,), True, False,
            "Paragraph this span lies within. Joins to ParagraphRecord.paragraph_id.",
            ANNOTATION,
        ),
        FieldSpec(
            "document_id", (str,), True, False,
            "Document the paragraph belongs to. Denormalised so a span is resolvable on its own.",
            ANNOTATION,
        ),
        FieldSpec(
            "char_start", (int,), True, False,
            "Start offset within the paragraph text, zero-based.",
            ANNOTATION,
        ),
        FieldSpec(
            "char_end", (int,), True, False,
            "End offset within the paragraph text, exclusive.",
            ANNOTATION,
        ),
        FieldSpec(
            "text", (str,), False, True,
            "The span text. Convenience for annotation tooling only; offsets are authoritative and are what gets published.",
            ANNOTATION,
        ),
        FieldSpec(
            "matched_cue", (str,), False, True,
            "Deontic cue that surfaced this span, e.g. 'shall'. Recorded so candidate-generation bias is measurable rather than invisible.",
            ANNOTATION,
        ),
    )

    def validate(self) -> list[str]:
        """Type checks plus span-ordering rules."""
        errors = super().validate()
        if isinstance(self.char_start, int) and self.char_start < 0:
            errors.append(f"char_start: must be >= 0, got {self.char_start}")
        if (
            isinstance(self.char_start, int)
            and isinstance(self.char_end, int)
            and self.char_end <= self.char_start
        ):
            errors.append(
                f"char_end: must be greater than char_start "
                f"({self.char_end} <= {self.char_start})"
            )
        return errors

    @property
    def span_ref(self) -> str:
        """Stable, citable reference: ``<paragraph_id>@<start>:<end>``."""
        return f"{self.paragraph_id}@{self.char_start}:{self.char_end}"


@dataclass
class T1Label(SchemaRecord):
    """One T1 benchmark item.

    Constructed as a candidate by machine extraction, then labelled by
    annotators. The fields owned by ``phase1/meer-annotation`` are the research
    contribution; the rest is provenance.
    """

    label_id: str
    obligation_span: ObligationSpan | None = None
    entity_class: str | None = None
    subject_family: str | None = None
    applies_to: list[str] = field(default_factory=list)
    applies_to_rationale: str | None = None
    differential_flag: str = DifferentialFlag.UNLABELLED.value
    differential_counterpart_ids: list[str] = field(default_factory=list)
    in_force_from: str | None = None
    in_force_to: str | None = None
    label_status: str = LabelStatus.CANDIDATE.value
    annotator_ids: list[str] = field(default_factory=list)
    annotation_count: int | None = None
    agreement_score: float | None = None
    provenance: str | None = None
    notes: str | None = None

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "label_id", (str,), True, False,
            "Stable identifier for this benchmark item. Must survive regeneration of the candidate pool, or existing annotations detach.",
            BASE,
        ),
        FieldSpec(
            "obligation_span", (ObligationSpan,), False, True,
            "The span of text stating the obligation. Null only for an item whose span has not yet been fixed.",
            ANNOTATION,
        ),
        FieldSpec(
            "entity_class", (str,), False, True,
            "Entity class of the SOURCE DOCUMENT. Context only. Must not be read as an applicability judgement, and must never be copied into applies_to.",
            MATRIX,
        ),
        FieldSpec(
            "subject_family", (str,), False, True,
            "Subject family of the source document.",
            MATRIX,
        ),
        FieldSpec(
            "applies_to", (list,), False, False,
            "ANNOTATION TARGET. Entity classes this obligation actually binds, as judged by annotators. Empty list means not yet annotated. Deriving this from entity_class makes the label a tautology and invalidates RQ1.",
            ANNOTATION,
        ),
        FieldSpec(
            "applies_to_rationale", (str,), False, True,
            "Annotator's stated reason for the applicability judgement. Required for adjudicating disagreements.",
            ANNOTATION,
        ),
        FieldSpec(
            "differential_flag", (str,), False, False,
            "ANNOTATION TARGET. One of DifferentialFlag. Defaults to 'unlabelled'; never default to 'absent', which would assert an unexamined finding.",
            ANNOTATION,
        ),
        FieldSpec(
            "differential_counterpart_ids", (list,), False, False,
            "label_id values of counterpart obligations in other entity classes. Empty when none identified.",
            ANNOTATION,
        ),
        FieldSpec(
            "in_force_from", (str,), False, True,
            "Date this obligation took effect, verbatim as published. Carries the amendment-awareness claim.",
            SCRAPER,
        ),
        FieldSpec(
            "in_force_to", (str,), False, True,
            "Date this obligation ceased to be in force, or null if still current. Distinguishing 'still in force' from 'never populated' requires checking label_status.",
            SCRAPER,
        ),
        FieldSpec(
            "label_status", (str,), False, False,
            "One of LabelStatus. Starts at 'candidate'. Promotion to 'validated' requires the configured number of independent annotators and is never implicit.",
            ANNOTATION,
        ),
        FieldSpec(
            "annotator_ids", (list,), False, False,
            "Identifiers of annotators who labelled this item. Length drives the validation threshold.",
            ANNOTATION,
        ),
        FieldSpec(
            "annotation_count", (int,), False, True,
            "Number of independent annotations received.",
            ANNOTATION,
        ),
        FieldSpec(
            "agreement_score", (float, int), False, True,
            "Inter-annotator agreement for this item, where computed. Corpus-level Fleiss' kappa is reported separately.",
            ANNOTATION,
        ),
        FieldSpec(
            "provenance", (str,), False, True,
            "Which pipeline stage proposed this candidate, so candidate-generation bias stays attributable.",
            ANNOTATION,
        ),
        FieldSpec(
            "notes", (str,), False, True,
            "Free-text annotator note.",
            ANNOTATION,
        ),
    )

    def validate(self) -> list[str]:
        """Type checks plus the label-integrity rules."""
        errors = super().validate()

        valid_flags = {f.value for f in DifferentialFlag}
        if self.differential_flag not in valid_flags:
            errors.append(
                f"differential_flag: must be one of {sorted(valid_flags)}, got {self.differential_flag!r}"
            )

        valid_statuses = {s.value for s in LabelStatus}
        if self.label_status not in valid_statuses:
            errors.append(
                f"label_status: must be one of {sorted(valid_statuses)}, got {self.label_status!r}"
            )

        # An item cannot be validated without the annotation evidence to back it.
        if self.label_status == LabelStatus.VALIDATED.value:
            if not self.annotator_ids:
                errors.append("label_status: 'validated' requires a non-empty annotator_ids")
            if not self.applies_to:
                errors.append("label_status: 'validated' requires a non-empty applies_to")
            if self.differential_flag == DifferentialFlag.UNLABELLED.value:
                errors.append(
                    "label_status: 'validated' is inconsistent with differential_flag 'unlabelled'"
                )

        if (
            self.annotation_count is not None
            and self.annotator_ids
            and self.annotation_count != len(self.annotator_ids)
        ):
            errors.append(
                f"annotation_count: {self.annotation_count} disagrees with "
                f"len(annotator_ids)={len(self.annotator_ids)}"
            )

        if self.obligation_span is not None:
            errors.extend(f"obligation_span.{e}" for e in self.obligation_span.validate())

        return errors

    def to_dict(self) -> dict[str, object]:
        """Serialise, flattening the nested span via its own ``to_dict``."""
        data = super().to_dict()
        data["obligation_span"] = (
            self.obligation_span.to_dict() if self.obligation_span is not None else None
        )
        return data

    @classmethod
    def from_dict(cls, data, *, strict: bool = True) -> "T1Label":
        """Construct, rebuilding a nested :class:`ObligationSpan` from a mapping."""
        record = super().from_dict(data, strict=strict)
        span = record.obligation_span
        if isinstance(span, dict):
            record.obligation_span = ObligationSpan.from_dict(span, strict=strict)
        return record

    @property
    def is_validated(self) -> bool:
        """Whether this item has cleared annotation. Never infer this from other fields."""
        return self.label_status == LabelStatus.VALIDATED.value
