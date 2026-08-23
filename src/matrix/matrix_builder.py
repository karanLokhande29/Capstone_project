"""Subject x Entity-Class Matrix construction.

Implements the design fixed by :mod:`src.matrix.interfaces`
(``build_matrix``, ``matrix_metrics``, ``route_query``, ``persist_matrix``).
Real logic lives here rather than in ``interfaces.py`` for the same reason as
``phase1/akash-scraper``'s ``rbi_scraper.py`` and
``phase1/karan-matrix``'s ``vocabulary_discovery.py``: ``tests/test_smoke.py``
(Phase 0, base-owned) requires every ``interfaces.py`` function to keep
raising ``NotImplementedError``.

A cell is built for **every** ``(entity_class, subject_family)`` pair across
the two discovered vocabularies, including pairs with zero source Directions
— an unpopulated cell is a measurement (this exact combination of regulated
entity and topic has no RBI Direction), not a gap in this module's output. On
the validated 380-document corpus this means the full grid is
19 entity classes x 56 subject families = 1,064 cells, of which only a few
hundred are actually populated — the rest is the coverage matrix's headline
finding, not noise to hide.

``ambiguous`` policy: a cell is marked ambiguous with reason
``multiple_candidate_directions`` when more than one Direction maps to it.
Normally one (entity class, subject family) pair should correspond to at most
one governing Direction; more than one is either a genuine coexistence (e.g.
an original Direction plus a later amendment that was harvested as a separate
document) or a normalisation collision, and either way it is exactly the kind
of finding a coverage matrix exists to surface, not something to silently
average or overwrite.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Iterable, Mapping

from src.common.io_helpers import write_json, write_jsonl
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.metadata.vocabulary_discovery import PROVENANCE_DERIVED, term_provenance
from src.schemas.matrix import MatrixCell
from src.schemas.provenance import DocumentRecord
from src.schemas.vocabulary import Vocabulary

BRANCH = "phase1/karan-matrix"


def build_matrix(
    records: Iterable[DocumentRecord],
    entity_vocab: Vocabulary,
    subject_vocab: Vocabulary,
    cfg: Mapping[str, Any],
    *,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> list[MatrixCell]:
    """Build the full matrix: one cell per (entity_class, subject_family) pair.

    Requires `records` to already carry normalised `entity_class`/
    `subject_family` values (i.e. already passed through
    :func:`src.metadata.vocabulary_discovery.normalise_documents`) — this
    function only aggregates, it does not resolve raw values itself.
    """
    logger = logger or get_logger("matrix.builder", cfg)
    ambiguous_threshold = int(
        cfg.get("metadata", {}).get("matrix_ambiguous_source_direction_threshold", 1)
    )

    cell_docs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for record in records:
        if record.entity_class and record.subject_family:
            cell_docs[(record.entity_class, record.subject_family)].append(record.document_id)

    entity_terms = {t.canonical_name: t for t in entity_vocab}
    subject_terms = {t.canonical_name: t for t in subject_vocab}

    cells: list[MatrixCell] = []
    for entity_name, entity_term in sorted(entity_terms.items()):
        for subject_name, subject_term in sorted(subject_terms.items()):
            doc_ids = sorted(cell_docs.get((entity_name, subject_name), []))
            populated = len(doc_ids) > 0
            ambiguous = len(doc_ids) > ambiguous_threshold
            ambiguity_reason = "multiple_candidate_directions" if ambiguous else None

            if ambiguous:
                logger.warning(
                    "matrix: cell (%s, %s) ambiguous — %d source Directions: %s",
                    entity_name, subject_name, len(doc_ids), doc_ids,
                )

            # Provenance marker (P1-002-CORRECTIVE): a cell's axes can rest on
            # a harvested-and-normalised term or an inferred one. Recorded per
            # cell so the matrix is auditable standalone, without joining back
            # to the vocabulary files.
            entity_provenance = term_provenance(entity_term)
            subject_provenance = term_provenance(subject_term)
            notes = (
                f"provenance: entity_class={entity_provenance}, "
                f"subject_family={subject_provenance}"
            )
            if subject_provenance == PROVENANCE_DERIVED or entity_provenance == PROVENANCE_DERIVED:
                notes += (
                    " — DERIVED axis present: this cell rests partly on inferred "
                    "metadata, not RBI's own taxonomy. See "
                    "reports/phase1_karan_matrix.md."
                )

            cells.append(
                MatrixCell(
                    entity_class=entity_name,
                    subject_family=subject_name,
                    populated=populated,
                    source_directions=doc_ids,
                    ambiguous=ambiguous,
                    ambiguity_reason=ambiguity_reason,
                    n_documents=len(doc_ids),
                    entity_class_term_id=entity_term.term_id,
                    subject_family_term_id=subject_term.term_id,
                    notes=notes,
                )
            )

    derived_axis_cells = sum(1 for c in cells if c.notes and "DERIVED axis present" in c.notes)
    logger.info(
        "build_matrix: %d cells (%d entity classes x %d subject families), %d populated, "
        "%d resting on at least one derived axis",
        len(cells), len(entity_terms), len(subject_terms),
        sum(1 for c in cells if c.populated), derived_axis_cells,
    )
    return cells


def matrix_metrics(cells: Iterable[MatrixCell]) -> dict[str, Any]:
    """Coverage metrics over a built matrix.

    Reports populated, unpopulated and ambiguous counts *separately* —
    coverage alone would hide whether the remainder is a genuine regulatory
    gap or a normalisation failure, which is exactly the distinction this
    matrix exists to make visible.
    """
    cells = list(cells)
    total = len(cells)
    populated = sum(1 for c in cells if c.populated)
    ambiguous = sum(1 for c in cells if c.ambiguous)
    duplicate = sum(1 for c in cells if c.populated and (c.n_documents or 0) > 1)

    return {
        "total_cells": total,
        "populated_cells": populated,
        "missing_cells": total - populated,
        "ambiguous_cells": ambiguous,
        "duplicate_mapping_cells": duplicate,
        "matrix_coverage": (populated / total) if total else "NOT YET MEASURED",
    }


def route_query(entity_class: str, subject_family: str, cells: Iterable[MatrixCell], **kwargs: Any) -> list[str]:
    """Return the document_ids governing (entity_class, subject_family).

    An empty result and an unknown cell are deliberately distinguishable: an
    empty *list* means the cell exists and is measured as unpopulated (a
    regulatory gap); a `KeyError` means the pair isn't in the matrix at all
    (an out-of-vocabulary query), which is a different, more surprising thing
    for a caller to hit.
    """
    for cell in cells:
        if cell.entity_class == entity_class and cell.subject_family == subject_family:
            return list(cell.source_directions)
    raise KeyError(f"({entity_class!r}, {subject_family!r}) is not a cell in this matrix")


def persist_matrix(
    cells: Iterable[MatrixCell], cfg: Mapping[str, Any], *, resolver: PathResolver | None = None
) -> dict[str, str]:
    """Write the matrix as JSONL, returning the path written."""
    resolver = resolver or PathResolver.from_config(cfg)
    cells = list(cells)
    path = resolver.write_path("matrix", "matrix_v1.jsonl")
    write_jsonl(path, [c.to_dict() for c in cells])

    summary_path = resolver.write_path("matrix", "matrix_v1_summary.json")
    write_json(summary_path, matrix_metrics(cells))

    return {"matrix_path": str(path), "summary_path": str(summary_path)}
