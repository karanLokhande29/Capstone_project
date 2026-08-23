"""Pilot-scale deontic candidate extraction — a feasibility device, not the extractor.

**This is deliberately a keyword heuristic and nothing more.** Its only job is
to produce enough real obligation spans to test whether the annotation
protocol works on real RBI text before Phase 2 commits to full-scale
extraction and ~350-400 validated items. The systematic extractor is Phase 2,
Week 4 work and is explicitly out of scope here.

Because it is a heuristic, it is wrong in known ways, and those ways are
recorded rather than papered over:

* It matches deontic cues by regex, so it will catch definitional and
  commencement uses of "shall" ("...shall mean...", "...shall come into
  force...") alongside genuine obligations. A small reject-pattern list
  removes the most common of these; the rest are left for annotators to
  reject, which is itself useful pilot signal about candidate precision.
* It has no notion of scope, so a cue inside a quoted extract or a heading is
  treated the same as one in operative text.
* ``matched_cue`` is recorded on every span precisely so this bias is
  measurable later rather than invisible — if Phase 2's candidate pool turns
  out to be 90% "shall", that is a property of the extractor, not of RBI.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Mapping, Sequence

from src.benchmark.annotation import make_candidate
from src.common.logging_setup import get_logger
from src.schemas.benchmark import ObligationSpan, T1Label
from src.schemas.provenance import ParagraphRecord

BRANCH = "phase1/meer-annotation"

#: Deontic cues, longest first so "shall not" wins over "shall" at the same
#: offset and the stronger (negative) obligation is the one recorded.
DEONTIC_CUES: tuple[str, ...] = (
    "shall not",
    "must not",
    "is required to",
    "are required to",
    "shall",
    "must",
)

#: Uses of a cue that are not obligations. Definitional and commencement
#: language dominates the false positives in RBI text.
REJECT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bshall\s+mean\b", re.IGNORECASE),
    re.compile(r"\bshall\s+be\s+construed\b", re.IGNORECASE),
    re.compile(r"\bshall\s+come\s+into\s+force\b", re.IGNORECASE),
    re.compile(r"\bshall\s+have\s+the\s+(?:same\s+)?meaning\b", re.IGNORECASE),
    re.compile(r"\bshall\s+be\s+called\b", re.IGNORECASE),
)

#: Characters of context captured around a cue as the obligation span. RBI
#: obligations are typically a single sentence; this approximates one without
#: needing a sentence splitter at pilot scale.
SPAN_CONTEXT_CHARS = 260

PILOT_PROVENANCE = "pilot:keyword_heuristic_v1"


def _span_bounds(text: str, cue_start: int, cue_end: int) -> tuple[int, int]:
    """Approximate the sentence containing a cue, clamped to the paragraph."""
    start = text.rfind(".", 0, cue_start)
    start = 0 if start == -1 else start + 1
    start = max(start, cue_start - SPAN_CONTEXT_CHARS)

    end = text.find(".", cue_end)
    end = len(text) if end == -1 else end + 1
    end = min(end, cue_end + SPAN_CONTEXT_CHARS, len(text))
    return start, end


def extract_spans_from_paragraph(paragraph: ParagraphRecord) -> list[ObligationSpan]:
    """Find candidate obligation spans in one paragraph.

    At most one span per cue occurrence, de-duplicated by (start, end) so a
    sentence containing two cues yields one span rather than two overlapping
    near-identical ones.
    """
    text = paragraph.text or ""
    if not text.strip():
        return []

    seen: set[tuple[int, int]] = set()
    spans: list[ObligationSpan] = []

    for cue in DEONTIC_CUES:
        for match in re.finditer(rf"\b{re.escape(cue)}\b", text, re.IGNORECASE):
            start, end = _span_bounds(text, match.start(), match.end())
            if (start, end) in seen:
                continue
            span_text = text[start:end].strip()
            if not span_text:
                continue
            if any(pattern.search(span_text) for pattern in REJECT_PATTERNS):
                continue
            seen.add((start, end))
            spans.append(
                ObligationSpan(
                    paragraph_id=paragraph.paragraph_id,
                    document_id=paragraph.document_id,
                    char_start=start,
                    char_end=end,
                    text=span_text,
                    matched_cue=cue,
                )
            )

    return spans


def extract_obligation_candidates(
    paragraphs: Iterable[ParagraphRecord],
    cfg: Mapping[str, Any] | None = None,
    *,
    logger: logging.Logger | None = None,
    **kwargs: Any,
) -> list[T1Label]:
    """Build `candidate` T1Labels from paragraphs via the pilot heuristic.

    Every returned label has ``applies_to=[]`` and
    ``differential_flag='unlabelled'`` — this function asserts nothing about
    applicability, which is the annotators' job alone.
    """
    logger = logger or get_logger("benchmark.pilot", cfg or {})
    labels: list[T1Label] = []

    for paragraph in paragraphs:
        for index, span in enumerate(extract_spans_from_paragraph(paragraph)):
            labels.append(
                make_candidate(
                    label_id=f"t1_pilot_{paragraph.paragraph_id}_{index:02d}",
                    span=span,
                    entity_class=paragraph.entity_class,
                    subject_family=paragraph.subject_family,
                    provenance=PILOT_PROVENANCE,
                    in_force_from=paragraph.update_date,
                )
            )

    logger.info("pilot: %d candidate spans extracted", len(labels))
    return labels


#: Task 5's bounds: search 15-20 paragraphs, widening by 5 until the pilot
#: yields at least this many items. The paragraph range bounds the *search*;
#: it cannot guarantee an item count, because cue density varies per paragraph.
PILOT_PARAGRAPH_MIN = 15
PILOT_PARAGRAPH_MAX = 20
PILOT_PARAGRAPH_STEP = 5
PILOT_MIN_ITEMS = 10


def select_pilot_paragraphs(
    resolver: Any, *, limit: int, seed: int = 20260823, min_entity_classes: int = 2
) -> list[ParagraphRecord]:
    """Draw `limit` paragraphs spanning at least `min_entity_classes` classes.

    Round-robins across entity classes so the sample cannot collapse onto a
    single class — a pilot drawn from one entity class could not surface
    cross-class applicability disagreement, which is the main thing the
    annotation protocol needs to be tested against.
    """
    import json
    import random
    from collections import defaultdict
    from pathlib import Path

    rng = random.Random(seed)
    by_class: dict[str, list[dict]] = defaultdict(list)

    processed_dir = Path(resolver.write_dir("processed", create=False))
    for path in sorted(processed_dir.glob("md_*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                text = row.get("text") or ""
                # Only paragraphs long enough to plausibly contain an
                # obligation are worth an annotator's time.
                if row.get("entity_class") and len(text) > 200:
                    by_class[row["entity_class"]].append(row)

    classes = sorted(by_class)
    if len(classes) < min_entity_classes:
        raise ValueError(
            f"pilot needs paragraphs from >= {min_entity_classes} entity classes, found {len(classes)}"
        )

    for rows in by_class.values():
        rng.shuffle(rows)

    selected: list[dict] = []
    cursor = 0
    while len(selected) < limit:
        pool = by_class[classes[cursor % len(classes)]]
        if pool:
            selected.append(pool.pop())
        cursor += 1
        if cursor > limit * 10:  # every pool exhausted
            break

    return [ParagraphRecord.from_dict(r) for r in selected[:limit]]


def run_pilot_extraction(
    resolver: Any,
    cfg: Mapping[str, Any] | None = None,
    *,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Select paragraphs and extract candidates, widening the search if needed.

    Implements Task 5's widening rule: start at
    :data:`PILOT_PARAGRAPH_MIN`-:data:`PILOT_PARAGRAPH_MAX` paragraphs, and if
    fewer than :data:`PILOT_MIN_ITEMS` candidate spans come out, widen by
    :data:`PILOT_PARAGRAPH_STEP` and retry — reporting both final counts, so a
    single-digit item count never silently becomes the basis for a kappa.
    """
    logger = logger or get_logger("benchmark.pilot", cfg or {})

    paragraph_count = PILOT_PARAGRAPH_MAX
    attempts: list[dict[str, int]] = []

    while True:
        paragraphs = select_pilot_paragraphs(resolver, limit=paragraph_count)
        labels = extract_obligation_candidates(paragraphs, cfg, logger=logger)
        entity_classes = {p.entity_class for p in paragraphs if p.entity_class}
        attempts.append({"paragraphs_searched": len(paragraphs), "items_extracted": len(labels)})

        if len(labels) >= PILOT_MIN_ITEMS:
            logger.info(
                "pilot: %d items from %d paragraphs across %d entity classes (target met)",
                len(labels), len(paragraphs), len(entity_classes),
            )
            return {
                "paragraphs_searched": len(paragraphs),
                "entity_classes_spanned": sorted(entity_classes),
                "items_extracted": len(labels),
                "widening_attempts": attempts,
                "labels": labels,
                "paragraphs": paragraphs,
            }

        if len(paragraphs) < paragraph_count:  # pool exhausted; cannot widen further
            logger.warning(
                "pilot: only %d items from %d paragraphs and the corpus pool is exhausted",
                len(labels), len(paragraphs),
            )
            return {
                "paragraphs_searched": len(paragraphs),
                "entity_classes_spanned": sorted(entity_classes),
                "items_extracted": len(labels),
                "widening_attempts": attempts,
                "labels": labels,
                "paragraphs": paragraphs,
            }

        paragraph_count += PILOT_PARAGRAPH_STEP
        logger.info(
            "pilot: only %d items (< %d) — widening search to %d paragraphs",
            len(labels), PILOT_MIN_ITEMS, paragraph_count,
        )


def cue_distribution(labels: Sequence[T1Label]) -> dict[str, int]:
    """Count candidates by matched cue — makes extractor bias measurable."""
    counts: dict[str, int] = {}
    for label in labels:
        cue = label.obligation_span.matched_cue if label.obligation_span else None
        if cue:
            counts[cue] = counts.get(cue, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
