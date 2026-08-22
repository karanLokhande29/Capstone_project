"""Shared record contracts.

This package deliberately sits at the top of ``src/`` rather than inside
``src/metadata/``. Placing it under one workstream's package would imply that
workstream owns it; in fact all three Phase 1 branches read and write these
records, and a change here affects every branch at once. An owner-neutral
location makes that ownership explicit, and keeps the file physically outside
every branch's edit scope so the contract is not modified by accident.

Modifying anything in this package is a base-branch change requiring agreement
across all three owners.
"""

from src.schemas.base import (
    ANNOTATION,
    BASE,
    KNOWN_OWNERS,
    LATER,
    MATRIX,
    SCRAPER,
    FieldSpec,
    SchemaRecord,
)
from src.schemas.benchmark import DifferentialFlag, LabelStatus, ObligationSpan, T1Label
from src.schemas.matrix import KNOWN_AMBIGUITY_REASONS, MatrixCell
from src.schemas.provenance import (
    KNOWN_DOCUMENT_ROLES,
    KNOWN_EXTRACTION_SOURCES,
    DocumentRecord,
    ParagraphRecord,
    stable_paragraph_id,
)
from src.schemas.vocabulary import (
    ENTITY_CLASS,
    SUBJECT_FAMILY,
    Vocabulary,
    VocabularyTerm,
    empty_entity_class_vocabulary,
    empty_subject_family_vocabulary,
    normalise_term,
)

#: Every shared record contract. Iterated by the smoke test and by the audit
#: report generator, so a new schema is documented automatically.
ALL_SCHEMAS = (
    DocumentRecord,
    ParagraphRecord,
    MatrixCell,
    ObligationSpan,
    T1Label,
    VocabularyTerm,
)

__all__ = [
    "ALL_SCHEMAS",
    "ANNOTATION",
    "BASE",
    "DifferentialFlag",
    "DocumentRecord",
    "ENTITY_CLASS",
    "FieldSpec",
    "KNOWN_AMBIGUITY_REASONS",
    "KNOWN_DOCUMENT_ROLES",
    "KNOWN_EXTRACTION_SOURCES",
    "KNOWN_OWNERS",
    "LATER",
    "LabelStatus",
    "MATRIX",
    "MatrixCell",
    "ObligationSpan",
    "ParagraphRecord",
    "SCRAPER",
    "SUBJECT_FAMILY",
    "SchemaRecord",
    "T1Label",
    "Vocabulary",
    "VocabularyTerm",
    "empty_entity_class_vocabulary",
    "empty_subject_family_vocabulary",
    "normalise_term",
    "stable_paragraph_id",
]
