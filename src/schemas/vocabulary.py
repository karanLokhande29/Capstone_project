"""Extensible controlled vocabularies for entity classes and subject families.

**These vocabularies start empty and stay empty until a branch discovers terms
from the corpus.** No entity class or subject family is hard-coded anywhere in
this repository, and a unit test enforces that the constructors return an empty
vocabulary.

That rule exists because the project's planning documents estimate roughly 11
entity classes and 26 subject families. Those are estimates. Encoding them as
constants would turn an estimate into an assumption, and any later count that
disagreed with the corpus would look like a bug rather than a finding. Counts
are reported as discovered, always.

Aliasing is first-class rather than an afterthought: source listings refer to
the same regulated-entity class by several surface forms, and collapsing them
silently at parse time would lose the evidence for how the mapping was made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterable, Iterator, Mapping

from src.common.errors import SchemaValidationError
from src.schemas.base import MATRIX, FieldSpec, SchemaRecord

#: Vocabulary kinds. The two axes of the Subject x Entity-Class Matrix.
ENTITY_CLASS = "entity_class"
SUBJECT_FAMILY = "subject_family"
KNOWN_KINDS = (ENTITY_CLASS, SUBJECT_FAMILY)


def normalise_term(raw: str) -> str:
    """Reduce a surface form to a comparison key.

    Case-folded, whitespace-collapsed, punctuation-stripped. Used only for
    lookup — never for storage. The canonical name keeps its original casing and
    punctuation so it can be shown to an annotator as published.
    """
    folded = (raw or "").strip().casefold()
    folded = re.sub(r"[\s ]+", " ", folded)
    folded = re.sub(r"[^\w\s]", "", folded)
    return folded.strip()


@dataclass
class VocabularyTerm(SchemaRecord):
    """One canonical term plus every surface form that maps to it."""

    term_id: str
    canonical_name: str
    kind: str
    aliases: list[str] = field(default_factory=list)
    source: str | None = None
    definition: str | None = None
    first_seen_document_id: str | None = None
    occurrence_count: int | None = None
    notes: str | None = None

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "term_id", (str,), True, False,
            "Stable slug for this term. Referenced by matrix cells and benchmark labels, so it must not change once assigned.",
            MATRIX,
        ),
        FieldSpec(
            "canonical_name", (str,), True, False,
            "Preferred display form, kept exactly as published rather than normalised.",
            MATRIX,
        ),
        FieldSpec(
            "kind", (str,), True, False,
            f"Which axis this term belongs to. One of: {', '.join(KNOWN_KINDS)}.",
            MATRIX,
        ),
        FieldSpec(
            "aliases", (list,), False, False,
            "Other surface forms observed in the corpus that resolve to this term. Empty list means none observed yet.",
            MATRIX,
        ),
        FieldSpec(
            "source", (str,), False, True,
            "Where the term was discovered, e.g. a listing page URL. Makes the vocabulary auditable rather than asserted.",
            MATRIX,
        ),
        FieldSpec(
            "definition", (str,), False, True,
            "Definition as given by the regulator, where one exists.",
            MATRIX,
        ),
        FieldSpec(
            "first_seen_document_id", (str,), False, True,
            "First document the term was observed in.",
            MATRIX,
        ),
        FieldSpec(
            "occurrence_count", (int,), False, True,
            "How many documents map to this term. A discovered count, never an estimate.",
            MATRIX,
        ),
        FieldSpec(
            "notes", (str,), False, True,
            "Free-text note, typically recording why an ambiguous surface form was resolved this way.",
            MATRIX,
        ),
    )

    def __post_init__(self) -> None:
        if self.kind not in KNOWN_KINDS:
            raise SchemaValidationError(
                f"VocabularyTerm.kind must be one of {KNOWN_KINDS}, got {self.kind!r}"
            )

    def surface_forms(self) -> tuple[str, ...]:
        """Canonical name plus aliases."""
        return (self.canonical_name, *self.aliases)


class Vocabulary:
    """An extensible, initially empty set of :class:`VocabularyTerm`.

    Args:
        kind: One of :data:`KNOWN_KINDS`.
        terms: Optional initial terms. Omitted in normal use — the vocabulary is
            built by discovery, not declaration.
    """

    def __init__(self, kind: str, terms: Iterable[VocabularyTerm] | None = None) -> None:
        if kind not in KNOWN_KINDS:
            raise SchemaValidationError(
                f"Vocabulary.kind must be one of {KNOWN_KINDS}, got {kind!r}"
            )
        self.kind = kind
        self._terms: dict[str, VocabularyTerm] = {}
        self._lookup: dict[str, str] = {}
        for term in terms or ():
            self.add(term)

    # -- population -----------------------------------------------------------

    def add(self, term: VocabularyTerm, *, replace: bool = False) -> VocabularyTerm:
        """Add a term.

        Raises:
            SchemaValidationError: The term's kind does not match, the term_id
                already exists (without ``replace``), or one of its surface
                forms already resolves to a different term. That last case is a
                genuine finding about the corpus, not a nuisance — it means two
                canonical terms are competing for the same surface form, and it
                must be resolved explicitly rather than by insertion order.
        """
        if term.kind != self.kind:
            raise SchemaValidationError(
                f"Cannot add a {term.kind!r} term to a {self.kind!r} vocabulary"
            )
        if term.term_id in self._terms and not replace:
            raise SchemaValidationError(f"Duplicate term_id in {self.kind} vocabulary: {term.term_id!r}")

        for surface in term.surface_forms():
            key = normalise_term(surface)
            if not key:
                continue
            owner = self._lookup.get(key)
            if owner is not None and owner != term.term_id and not replace:
                raise SchemaValidationError(
                    f"Surface form {surface!r} already resolves to {owner!r}; "
                    f"cannot also map it to {term.term_id!r}. Resolve the collision explicitly."
                )

        if replace and term.term_id in self._terms:
            self._drop_lookups(term.term_id)

        self._terms[term.term_id] = term
        for surface in term.surface_forms():
            key = normalise_term(surface)
            if key:
                self._lookup[key] = term.term_id
        return term

    def _drop_lookups(self, term_id: str) -> None:
        for key in [k for k, v in self._lookup.items() if v == term_id]:
            del self._lookup[key]

    # -- lookup ---------------------------------------------------------------

    def resolve(self, surface: str) -> VocabularyTerm | None:
        """Resolve a surface form to its canonical term, or ``None`` if unknown.

        An unknown surface form is expected and informative: it means the
        corpus contains a form the vocabulary has not yet accounted for.
        """
        key = normalise_term(surface)
        term_id = self._lookup.get(key)
        return self._terms.get(term_id) if term_id else None

    def get(self, term_id: str) -> VocabularyTerm | None:
        """Fetch by term_id."""
        return self._terms.get(term_id)

    def canonical_names(self) -> tuple[str, ...]:
        """All canonical names, sorted."""
        return tuple(sorted(t.canonical_name for t in self._terms.values()))

    def terms(self) -> tuple[VocabularyTerm, ...]:
        """All terms, ordered by term_id."""
        return tuple(self._terms[k] for k in sorted(self._terms))

    def __len__(self) -> int:
        return len(self._terms)

    def __iter__(self) -> Iterator[VocabularyTerm]:
        return iter(self.terms())

    def __contains__(self, surface: object) -> bool:
        return isinstance(surface, str) and self.resolve(surface) is not None

    def __repr__(self) -> str:
        return f"Vocabulary(kind={self.kind!r}, terms={len(self)})"

    # -- serialisation --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise, including the discovered term count."""
        return {
            "kind": self.kind,
            "term_count": len(self),
            "terms": [t.to_dict() for t in self.terms()],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Vocabulary":
        """Rebuild from :meth:`to_dict` output."""
        if not isinstance(data, Mapping):
            raise SchemaValidationError(
                f"Vocabulary.from_dict expects a mapping, got {type(data).__name__}"
            )
        if "kind" not in data:
            raise SchemaValidationError("Vocabulary.from_dict requires a 'kind' key")
        vocab = cls(str(data["kind"]))
        for raw in data.get("terms") or ():
            vocab.add(VocabularyTerm.from_dict(raw))
        return vocab


def empty_entity_class_vocabulary() -> Vocabulary:
    """A new, empty entity-class vocabulary.

    Empty by design. Terms are discovered from the corpus by
    ``phase1/karan-matrix``; the planning estimate of ~11 classes is not encoded
    here or anywhere else.
    """
    return Vocabulary(ENTITY_CLASS)


def empty_subject_family_vocabulary() -> Vocabulary:
    """A new, empty subject-family vocabulary.

    Empty by design, for the same reason as
    :func:`empty_entity_class_vocabulary`. The planning estimate of ~26 families
    is not encoded.
    """
    return Vocabulary(SUBJECT_FAMILY)
