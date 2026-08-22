"""Vocabulary discovery and normalisation — implemented by ``phase1/karan-matrix``.

Builds the entity-class and subject-family vocabularies from the harvested
corpus and resolves each document's raw surface forms onto them.

Implementation notes:

* Vocabularies are **discovered**. Start from
  :func:`~src.schemas.vocabulary.empty_entity_class_vocabulary` and add what the
  corpus contains. Do not seed from the planning estimates (~11 classes, ~26
  families) — a discovered count that disagrees with the estimate is a finding
  to report, not an error to correct.
* Write normalised values to ``entity_class`` / ``subject_family`` and leave the
  ``*_raw`` fields untouched. Normalisation is a research decision, and
  overwriting the evidence for it in place makes it unauditable.
* Record every unresolved surface form. The unresolved set is the honest measure
  of normalisation coverage.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from src.schemas.provenance import DocumentRecord
from src.schemas.vocabulary import Vocabulary

BRANCH = "phase1/karan-matrix"


def discover_vocabulary(
    records: Iterable[DocumentRecord], kind: str, cfg: Mapping[str, Any], **kwargs: Any
) -> Vocabulary:
    """Build a vocabulary of the given kind from observed surface forms.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"discover_vocabulary is implemented by {BRANCH}")


def normalise_documents(
    records: Iterable[DocumentRecord],
    entity_vocab: Vocabulary,
    subject_vocab: Vocabulary,
    **kwargs: Any,
) -> list[DocumentRecord]:
    """Resolve each record's raw surface forms onto the vocabularies.

    Returns records with ``entity_class`` / ``subject_family`` populated where
    resolution succeeded, and left null where it did not.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"normalise_documents is implemented by {BRANCH}")


def extract_temporal_metadata(cfg: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Extract in-force dates and amendment stamps, returning measured coverage.

    Coverage is the metric that matters here: the amendment-awareness claim is
    only as strong as the share of the corpus carrying a usable date.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"extract_temporal_metadata is implemented by {BRANCH}")


def persist_vocabularies(
    entity_vocab: Vocabulary, subject_vocab: Vocabulary, cfg: Mapping[str, Any]
) -> dict[str, str]:
    """Write both vocabularies to the paths named in ``config.vocabulary``.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"persist_vocabularies is implemented by {BRANCH}")
