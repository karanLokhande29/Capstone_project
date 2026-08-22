"""The Subject x Entity-Class Matrix cell contract.

The matrix is the project's map of regulatory coverage: for each (entity class,
subject family) pair, which Master Directions govern it. Its most interesting
output is the *unpopulated* cells — a pair with no governing Direction is either
a genuine regulatory gap or a normalisation failure, and the schema keeps those
two possibilities distinguishable rather than collapsing them.

Hence three separate flags, none of which is inferable from the others:

* ``populated`` — at least one source Direction was found.
* ``ambiguous`` — the mapping itself is uncertain, whether or not it is populated.
* ``ambiguity_reason`` — why. An ambiguous cell without a reason is not a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from src.schemas.base import MATRIX, FieldSpec, SchemaRecord

#: Documented values for ``ambiguity_reason``. Open-ended by design: a reason not
#: on this list is more interesting than one that is, and should be recorded
#: verbatim rather than forced into an existing bucket.
KNOWN_AMBIGUITY_REASONS = (
    "unresolved_entity_class",  # surface form did not resolve to a vocabulary term
    "unresolved_subject_family",
    "multiple_candidate_directions",  # more than one Direction claims the cell
    "cross_class_direction",  # one Direction covers several entity classes at once
    "superseded_unclear",  # unclear which of several versions is in force
)


@dataclass
class MatrixCell(SchemaRecord):
    """One (entity class, subject family) cell of the coverage matrix."""

    entity_class: str
    subject_family: str
    populated: bool = False
    source_directions: list[str] = field(default_factory=list)
    ambiguous: bool = False
    ambiguity_reason: str | None = None
    n_documents: int | None = None
    entity_class_term_id: str | None = None
    subject_family_term_id: str | None = None
    notes: str | None = None

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "entity_class", (str,), True, False,
            "Normalised entity class naming this cell's row. Non-nullable: a cell without both axes is not addressable.",
            MATRIX,
        ),
        FieldSpec(
            "subject_family", (str,), True, False,
            "Normalised subject family naming this cell's column.",
            MATRIX,
        ),
        FieldSpec(
            "populated", (bool,), False, False,
            "Whether at least one Master Direction was found governing this pair. False is a measurement, not a missing value, so this is non-nullable.",
            MATRIX,
        ),
        FieldSpec(
            "source_directions", (list,), False, False,
            "document_id values of the Directions governing this cell. Empty list when unpopulated.",
            MATRIX,
        ),
        FieldSpec(
            "ambiguous", (bool,), False, False,
            "Whether the mapping into this cell is uncertain. Independent of `populated`: a populated cell can still be ambiguous.",
            MATRIX,
        ),
        FieldSpec(
            "ambiguity_reason", (str,), False, True,
            f"Why the cell is ambiguous. Null when `ambiguous` is False. Known values: {', '.join(KNOWN_AMBIGUITY_REASONS)}.",
            MATRIX,
        ),
        FieldSpec(
            "n_documents", (int,), False, True,
            "Count of source Directions. Redundant with len(source_directions) but retained for matrices exported without the ID list.",
            MATRIX,
        ),
        FieldSpec(
            "entity_class_term_id", (str,), False, True,
            "term_id of the entity class in the discovered vocabulary. Survives renaming of the display form.",
            MATRIX,
        ),
        FieldSpec(
            "subject_family_term_id", (str,), False, True,
            "term_id of the subject family in the discovered vocabulary.",
            MATRIX,
        ),
        FieldSpec(
            "notes", (str,), False, True,
            "Free-text observation about this cell, typically the evidence behind an ambiguity call.",
            MATRIX,
        ),
    )

    def validate(self) -> list[str]:
        """Type checks plus the cross-field consistency rules for a cell."""
        errors = super().validate()
        if self.ambiguous and not self.ambiguity_reason:
            errors.append("ambiguity_reason: required when ambiguous is True")
        if self.populated and not self.source_directions:
            errors.append("source_directions: must be non-empty when populated is True")
        if not self.populated and self.source_directions:
            errors.append("populated: must be True when source_directions is non-empty")
        if (
            self.n_documents is not None
            and self.source_directions
            and self.n_documents != len(self.source_directions)
        ):
            errors.append(
                f"n_documents: {self.n_documents} disagrees with "
                f"len(source_directions)={len(self.source_directions)}"
            )
        return errors

    @property
    def cell_key(self) -> tuple[str, str]:
        """The (row, column) identity of this cell."""
        return (self.entity_class, self.subject_family)
