"""Subject x Entity-Class Matrix interfaces — implemented by ``phase1/karan-matrix``.

Builds the coverage matrix and routes a (entity class, subject family) query to
the governing Master Directions.

Implementation notes:

* Emit a :class:`~src.schemas.matrix.MatrixCell` for **every** pair on the
  discovered axes, including unpopulated ones. An unpopulated cell is the
  interesting output — dropping it turns a measured gap into a silent absence.
* Compute the grid size from the discovered vocabularies. Never from the
  planning estimate.
* ``populated`` and ``ambiguous`` are independent. A cell can be both.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from src.schemas.matrix import MatrixCell
from src.schemas.provenance import DocumentRecord
from src.schemas.vocabulary import Vocabulary

BRANCH = "phase1/karan-matrix"


def build_matrix(
    records: Iterable[DocumentRecord],
    entity_vocab: Vocabulary,
    subject_vocab: Vocabulary,
    cfg: Mapping[str, Any],
    **kwargs: Any,
) -> list[MatrixCell]:
    """Build the full matrix, one cell per axis pair.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"build_matrix is implemented by {BRANCH}")


def matrix_metrics(cells: Iterable[MatrixCell]) -> dict[str, Any]:
    """Compute coverage metrics over a built matrix.

    Must report populated, unpopulated and ambiguous counts separately, plus
    coverage as populated / total. Reporting coverage alone hides whether the
    remainder is a regulatory gap or a normalisation failure.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"matrix_metrics is implemented by {BRANCH}")


def route_query(
    entity_class: str, subject_family: str, cells: Iterable[MatrixCell], **kwargs: Any
) -> list[str]:
    """Return the document_ids governing a given cell.

    An empty result must be distinguishable from an unknown cell: the former is
    a measured gap, the latter an out-of-vocabulary query.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"route_query is implemented by {BRANCH}")


def persist_matrix(cells: Iterable[MatrixCell], cfg: Mapping[str, Any]) -> dict[str, str]:
    """Write the matrix and its cell detail, returning the paths written.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/karan-matrix``.
    """
    raise NotImplementedError(f"persist_matrix is implemented by {BRANCH}")
