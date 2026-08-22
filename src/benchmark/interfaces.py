"""Benchmark construction and annotation — implemented by ``phase1/meer-annotation``.

Produces T1 candidates, runs the annotation protocol, measures agreement, and
promotes items to validated. This is the critical path for the project's
research contribution: without validated labels and a measured agreement
statistic, RBI-ObliBench is a candidate pool, not a benchmark.

Implementation notes — these are correctness requirements, not style preferences:

* **Never derive ``applies_to`` from ``entity_class``.** Copying the source
  document's class into the applicability label produces a field that restates
  the input, which cannot support any applicability claim. ``applies_to`` comes
  from annotators judging which classes an obligation actually binds.
* **Never default ``differential_flag`` to ``absent``.** Leave it
  ``unlabelled`` until examined. Defaulting to ``absent`` converts unexamined
  items into a positive finding and inflates that class with items nobody
  looked at.
* **Never promote to ``validated`` implicitly.** Promotion requires
  ``config.benchmark.min_annotators_per_item`` independent annotations. An
  unannotated benchmark of size zero is an honest result; a benchmark of
  machine-labelled items presented as validated is not.
* Report agreement as ``"NOT YET MEASURED"`` until it has actually been
  computed, never as ``0.0``.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from src.schemas.benchmark import T1Label
from src.schemas.provenance import ParagraphRecord

BRANCH = "phase1/meer-annotation"


def extract_obligation_candidates(
    paragraphs: Iterable[ParagraphRecord], cfg: Mapping[str, Any], **kwargs: Any
) -> list[T1Label]:
    """Propose candidate obligation spans from paragraph text.

    Returns items with ``label_status='candidate'``, ``applies_to=[]`` and
    ``differential_flag='unlabelled'``.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/meer-annotation``.
    """
    raise NotImplementedError(f"extract_obligation_candidates is implemented by {BRANCH}")


def sample_for_annotation(
    candidates: Iterable[T1Label], cfg: Mapping[str, Any], **kwargs: Any
) -> list[T1Label]:
    """Draw a stratified annotation sample from the candidate pool.

    Stratification must not use ``differential_flag`` while it is still
    ``unlabelled`` for most items — stratifying on an unmeasured field samples
    the extractor's blind spots rather than the corpus.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/meer-annotation``.
    """
    raise NotImplementedError(f"sample_for_annotation is implemented by {BRANCH}")


def build_annotation_tasks(
    sample: Iterable[T1Label], cfg: Mapping[str, Any], **kwargs: Any
) -> dict[str, str]:
    """Write per-annotator task files, returning annotator id -> path.

    Assignment must give each item to at least
    ``config.benchmark.min_annotators_per_item`` distinct annotators, or
    agreement cannot be computed for it.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/meer-annotation``.
    """
    raise NotImplementedError(f"build_annotation_tasks is implemented by {BRANCH}")


def ingest_annotations(cfg: Mapping[str, Any], **kwargs: Any) -> list[T1Label]:
    """Read completed annotation files back into labels.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/meer-annotation``.
    """
    raise NotImplementedError(f"ingest_annotations is implemented by {BRANCH}")


def measure_agreement(labels: Iterable[T1Label], **kwargs: Any) -> dict[str, Any]:
    """Compute inter-annotator agreement over multiply-annotated items.

    Returns ``"NOT YET MEASURED"`` for any statistic with insufficient data,
    never a numeric placeholder.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/meer-annotation``.
    """
    raise NotImplementedError(f"measure_agreement is implemented by {BRANCH}")


def promote_validated(labels: Iterable[T1Label], cfg: Mapping[str, Any], **kwargs: Any) -> list[T1Label]:
    """Promote items meeting the annotation threshold to ``validated``.

    Every promotion must satisfy :meth:`T1Label.validate`, which rejects a
    validated item lacking annotators, applicability, or a differential
    determination.

    Raises:
        NotImplementedError: Always. Implemented by ``phase1/meer-annotation``.
    """
    raise NotImplementedError(f"promote_validated is implemented by {BRANCH}")
