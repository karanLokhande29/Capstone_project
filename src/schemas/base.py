"""Schema machinery: self-documenting, validating record contracts.

Every shared schema in this package declares a ``FIELD_SPECS`` table alongside
its dataclass fields. The table records, per field: type, whether it is
required, whether it may be null, what it means, and **which branch is expected
to populate it**. That last column is what makes these contracts rather than
merely dataclasses — it is the machine-readable answer to "whose job is this
field?", which is the question that otherwise gets answered differently on three
branches at once.

A unit test asserts the table and the dataclass fields stay in lockstep, so a
branch cannot add a field without declaring its owner.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, TypeVar

from src.common.errors import SchemaValidationError

T = TypeVar("T", bound="SchemaRecord")

# -- Branch ownership labels used in FieldSpec.populated_by -------------------

BASE = "phase0-base"
SCRAPER = "phase1/akash-scraper"
MATRIX = "phase1/karan-matrix"
ANNOTATION = "phase1/meer-annotation"
LATER = "phase2+"

#: Every legal value of ``FieldSpec.populated_by``. Validated by a unit test so
#: a typo cannot quietly create a fourth, non-existent owner.
KNOWN_OWNERS = (BASE, SCRAPER, MATRIX, ANNOTATION, LATER)


@dataclass(frozen=True)
class FieldSpec:
    """Documentation and validation rules for one schema field.

    Attributes:
        name: Field name, matching the dataclass field exactly.
        types: Accepted Python types. ``()`` accepts anything.
        required: Whether the key must be present when constructing from a dict.
        nullable: Whether ``None`` is an acceptable value.
        description: What the field means. Written for a reader who has not seen
            the code.
        populated_by: Which branch is expected to fill this in. One of
            :data:`KNOWN_OWNERS`.
    """

    name: str
    types: tuple[type, ...]
    required: bool
    nullable: bool
    description: str
    populated_by: str

    @property
    def type_label(self) -> str:
        """Human-readable type, e.g. ``"str | None"``."""
        if not self.types:
            return "any"
        base = " | ".join(t.__name__ for t in self.types)
        return f"{base} | None" if self.nullable else base


class SchemaRecord:
    """Mixin for dataclass-based shared records.

    Subclasses must be decorated with :func:`dataclasses.dataclass` and must set
    :attr:`FIELD_SPECS`.
    """

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = ()

    # -- introspection --------------------------------------------------------

    @classmethod
    def spec_map(cls) -> dict[str, FieldSpec]:
        """Field name -> spec."""
        return {spec.name: spec for spec in cls.FIELD_SPECS}

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        """Declared field names, in declaration order."""
        return tuple(f.name for f in dataclasses.fields(cls))  # type: ignore[arg-type]

    @classmethod
    def required_fields(cls) -> tuple[str, ...]:
        """Fields that must be present when constructing from a dict."""
        return tuple(spec.name for spec in cls.FIELD_SPECS if spec.required)

    @classmethod
    def owned_by(cls, owner: str) -> tuple[str, ...]:
        """Fields a given branch is expected to populate."""
        return tuple(spec.name for spec in cls.FIELD_SPECS if spec.populated_by == owner)

    # -- conversion -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON/JSONL."""
        return dataclasses.asdict(self)  # type: ignore[call-overload]

    @classmethod
    def from_dict(cls: type[T], data: Mapping[str, Any], *, strict: bool = True) -> T:
        """Construct from a mapping.

        Args:
            data: Source mapping.
            strict: Reject keys not declared in the schema. Left on by default:
                an undeclared key almost always means one branch has extended
                the record without updating the shared contract, and catching
                that at the boundary is far cheaper than discovering it at
                integration time.

        Raises:
            SchemaValidationError: A required key is missing, or (under
                ``strict``) an unknown key is present.
        """
        if not isinstance(data, Mapping):
            raise SchemaValidationError(
                f"{cls.__name__}.from_dict expects a mapping, got {type(data).__name__}"
            )

        known = set(cls.field_names())
        errors: list[str] = []

        missing = [name for name in cls.required_fields() if name not in data]
        errors.extend(f"missing required field: {name}" for name in missing)

        if strict:
            unknown = sorted(set(data) - known)
            errors.extend(
                f"unknown field: {name} (add it to {cls.__name__}.FIELD_SPECS "
                "on the base branch before using it)"
                for name in unknown
            )

        if errors:
            raise SchemaValidationError(
                f"Cannot build {cls.__name__}: " + "; ".join(errors), errors=errors
            )

        kwargs = {name: data[name] for name in known if name in data}
        return cls(**kwargs)  # type: ignore[arg-type]

    # -- validation -----------------------------------------------------------

    def validate(self) -> list[str]:
        """Return every problem with this record. Empty list means valid."""
        errors: list[str] = []
        specs = self.spec_map()
        for name in self.field_names():
            value = getattr(self, name)
            spec = specs.get(name)
            if spec is None:
                errors.append(f"{name}: no FieldSpec declared")
                continue
            if value is None:
                if not spec.nullable:
                    errors.append(f"{name}: must not be null")
                continue
            if spec.types and not isinstance(value, spec.types):
                errors.append(
                    f"{name}: expected {spec.type_label}, got {type(value).__name__}"
                )
        return errors

    def require_valid(self: T) -> T:
        """Return ``self``, or raise if invalid. Useful in a fluent chain."""
        errors = self.validate()
        if errors:
            raise SchemaValidationError(
                f"Invalid {type(self).__name__}: " + "; ".join(errors), errors=errors
            )
        return self

    def is_valid(self) -> bool:
        """Whether the record passes :meth:`validate`."""
        return not self.validate()

    # -- documentation --------------------------------------------------------

    @classmethod
    def spec_table(cls) -> str:
        """Render :attr:`FIELD_SPECS` as a Markdown table.

        Used to generate the field documentation in ``reports/phase0_audit.md``,
        so the report cannot drift from the code.
        """
        header = (
            "| Field | Type | Required | Nullable | Populated by | Description |\n"
            "|---|---|---|---|---|---|\n"
        )
        rows = "".join(
            f"| `{s.name}` | {s.type_label} | {'yes' if s.required else 'no'} "
            f"| {'yes' if s.nullable else 'no'} | {s.populated_by} | {s.description} |\n"
            for s in cls.FIELD_SPECS
        )
        return header + rows
