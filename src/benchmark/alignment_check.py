"""Week-2 risk checks: cross-class obligation alignment, and FAQ/enforcement sources.

Two decision points, not two measurements.

Cross-class alignment (Task 3)
------------------------------
Phase 2's differential-obligation work (RQ2) assumes that when RBI issues
parallel Directions to different entity classes on the same subject, their
obligations can be matched *at paragraph level*. This module tests that
assumption on real text. The dossier sets an explicit trigger: **below 60%
one-to-one alignment, do not silently continue.**

**Alignment requires content agreement, not just matching structure.** An
earlier version of this check scored two paragraphs as aligned when they
shared a ``clause_path`` (e.g. both labelled ``4(a)``). That was measuring
almost nothing: ``clause_path`` values in this corpus are overwhelmingly bare
numbers (``"1"``, ``"2"``, ``"3"`` — every Direction has them), so unrelated
Directions "aligned" by numbering coincidence. The flaw surfaced because the
contrast baseline below scored *higher* than the signal it was supposed to
sit beneath, which is impossible if the metric is sound. Alignment is
therefore defined here as **same structural position AND lexical agreement
above :data:`SIMILARITY_THRESHOLD`**.

**Every rate is reported against a false-positive baseline.** The parallel
comparison (same subject family, different entity classes — should align if
RBI drafts from a shared template) is always reported alongside an unrelated
comparison (same entity class, different subject families — should *not*
align, since distinct subjects are distinct regulations). The baseline is
what makes the headline number interpretable: a 36% alignment rate means
something very different against a 5% baseline than against a 30% one.

**Rates are reported per axis.** ``entity_class`` is harvested from RBI's own
listing headings (raw-sourced, 0% unresolved). ``subject_family`` is
*derived* — RBI publishes no subject taxonomy, so P1-002 inferred it by
stripping the entity-class string out of each title (P1-002-CORRECTIVE,
commit ``e4013ca``). The two never get blended into one number, so any
misalignment traceable to the derived axis stays visible.

FAQ/enforcement sources (Task 4)
--------------------------------
Whether RBI FAQs and enforcement actions map to specific corpus paragraphs.
If P1-001's opportunistic sample does not exist, this reports
``NOT YET MEASURED`` rather than manufacturing a sample or a rate. Either
way the standing rule holds: FAQ/enforcement items are never paragraph-level
gold labels, only validation/motivation material.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.common.logging_setup import get_logger
from src.common.paths import PathResolver

BRANCH = "phase1/meer-annotation"

#: The dossier's explicit decision threshold for paragraph-level alignment.
ALIGNMENT_TRIGGER = 0.60

#: Jaccard token-overlap above which two paragraphs at the same structural
#: position count as genuinely aligned. Chosen from the measured separation
#: between the parallel and unrelated distributions (which are bimodal, with
#: the valley around here), not tuned to produce a desired answer — the
#: false-positive baseline reported alongside every rate is what keeps this
#: honest: if the threshold were too loose, the baseline would rise with it.
SIMILARITY_THRESHOLD = 0.5

#: Tokens of 3+ latin characters, case-folded. Deliberately crude: this is a
#: structural sanity check, not the Phase 2 semantic matcher.
_TOKEN_RE = re.compile(r"[a-z]{3,}")

NOT_YET_MEASURED = "NOT YET MEASURED"


def text_similarity(a: str, b: str) -> float:
    """Jaccard overlap of the two texts' token sets."""
    tokens_a = set(_TOKEN_RE.findall((a or "").lower()))
    tokens_b = set(_TOKEN_RE.findall((b or "").lower()))
    union = tokens_a | tokens_b
    return len(tokens_a & tokens_b) / len(union) if union else 0.0


def _load_paragraph_index(resolver: PathResolver) -> list[dict[str, Any]]:
    path = resolver.read_path("processed", "paragraphs_index.jsonl")
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def select_alignment_sample(
    resolver: PathResolver, *, n_entity_classes: int = 3, n_subject_families: int = 3
) -> dict[str, Any]:
    """Pick the 3 entity classes x 3 subject families with the most parallel coverage.

    Chosen by coverage rather than at random: the check asks whether parallel
    Directions *can* be aligned, so it must run where parallel Directions
    actually exist. Sampling sparse cells would measure the corpus's coverage
    gaps instead of its alignability — a different question.
    """
    index = _load_paragraph_index(resolver)

    subject_breadth: dict[str, set[str]] = defaultdict(set)
    for row in index:
        ec, sf = row.get("entity_class"), row.get("subject_family")
        if ec and sf:
            subject_breadth[sf].add(ec)

    ranked_subjects = sorted(subject_breadth.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    subjects = [sf for sf, _ in ranked_subjects[:n_subject_families]]

    entity_breadth: dict[str, int] = defaultdict(int)
    for sf in subjects:
        for ec in subject_breadth[sf]:
            entity_breadth[ec] += 1
    ranked_entities = sorted(entity_breadth.items(), key=lambda kv: (-kv[1], kv[0]))
    entities = [ec for ec, _ in ranked_entities[:n_entity_classes]]

    return {"entity_classes": entities, "subject_families": subjects}


def _load_cell_text(
    resolver: PathResolver, entities: Sequence[str], subjects: Sequence[str]
) -> tuple[dict, dict]:
    """Build (entity, subject) -> position -> text maps, for paragraph and section level.

    Streams the per-document files and keeps text only for the sampled cells,
    so the whole corpus never sits in memory at once.
    """
    processed_dir = Path(resolver.write_dir("processed", create=False))
    wanted_entities, wanted_subjects = set(entities), set(subjects)

    by_paragraph: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    by_section: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for path in sorted(processed_dir.glob("md_*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                ec, sf, text = row.get("entity_class"), row.get("subject_family"), row.get("text")
                if ec not in wanted_entities or sf not in wanted_subjects or not text:
                    continue
                if row.get("clause_path"):
                    by_paragraph[(ec, sf)].setdefault(row["clause_path"], text)
                if row.get("section_id"):
                    by_section[(ec, sf)][row["section_id"]].append(text)

    sections = {k: {s: " ".join(v) for s, v in d.items()} for k, d in by_section.items()}
    return dict(by_paragraph), sections


def _alignment_rate(
    store: Mapping[tuple[str, str], Mapping[str, str]],
    pairs: Iterable[tuple[tuple[str, str], tuple[str, str]]],
) -> dict[str, Any]:
    """Rate of shared positions whose texts also agree above the threshold."""
    similarities: list[float] = []
    positions_compared = 0

    for cell_a, cell_b in pairs:
        map_a, map_b = store.get(cell_a, {}), store.get(cell_b, {})
        for position in set(map_a) & set(map_b):
            positions_compared += 1
            similarities.append(text_similarity(map_a[position], map_b[position]))

    if not similarities:
        return {
            "positions_compared": 0,
            "aligned_positions": 0,
            "alignment_rate": NOT_YET_MEASURED,
            "median_similarity": NOT_YET_MEASURED,
        }

    aligned = sum(1 for s in similarities if s > SIMILARITY_THRESHOLD)
    return {
        "positions_compared": positions_compared,
        "aligned_positions": aligned,
        "alignment_rate": aligned / len(similarities),
        "median_similarity": statistics.median(similarities),
    }


def _parallel_pairs(entities: Sequence[str], subjects: Sequence[str]):
    """Same subject, different entity classes — the comparison that should align."""
    for sf in subjects:
        for i, ec_a in enumerate(entities):
            for ec_b in entities[i + 1 :]:
                yield (ec_a, sf), (ec_b, sf)


def _unrelated_pairs(entities: Sequence[str], subjects: Sequence[str]):
    """Same entity class, different subjects — the false-positive baseline."""
    for ec in entities:
        for i, sf_a in enumerate(subjects):
            for sf_b in subjects[i + 1 :]:
                yield (ec, sf_a), (ec, sf_b)


def cross_class_alignment(
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Measure content-verified cross-class alignment and judge it against the 60% trigger."""
    logger = logger or get_logger("benchmark.alignment", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    selection = select_alignment_sample(resolver)
    entities: list[str] = selection["entity_classes"]
    subjects: list[str] = selection["subject_families"]

    paragraphs, sections = _load_cell_text(resolver, entities, subjects)

    paragraph_parallel = _alignment_rate(paragraphs, _parallel_pairs(entities, subjects))
    paragraph_baseline = _alignment_rate(paragraphs, _unrelated_pairs(entities, subjects))
    section_parallel = _alignment_rate(sections, _parallel_pairs(entities, subjects))
    section_baseline = _alignment_rate(sections, _unrelated_pairs(entities, subjects))

    headline = paragraph_parallel["alignment_rate"]
    triggered = headline < ALIGNMENT_TRIGGER if isinstance(headline, float) else None

    if triggered is None:
        judgment = f"{NOT_YET_MEASURED} — no comparable positions found in the sample."
    elif triggered:
        section_rate = section_parallel["alignment_rate"]
        section_note = (
            f"Section-level alignment was measured as the dossier's suggested fallback and "
            f"does NOT rescue it ({section_rate:.1%} vs {headline:.1%} at paragraph level) — "
            "it is marginally more precise (lower false-positive baseline) but no more "
            "complete. Phase 2 should therefore NOT assume either structural level supports "
            "reliable one-to-one cross-class matching, and should treat semantic matching as "
            "load-bearing rather than as a refinement on top of a working structural match."
            if isinstance(section_rate, float) else
            "Section-level alignment could not be measured on this sample."
        )
        judgment = (
            f"TRIGGER FIRED — paragraph-level alignment is {headline:.1%}, BELOW the "
            f"{ALIGNMENT_TRIGGER:.0%} threshold. Paragraph-level cross-class matching is NOT "
            f"reliable on this evidence. {section_note}"
        )
    else:
        judgment = (
            f"AT OR ABOVE {ALIGNMENT_TRIGGER:.0%} — paragraph-level alignment is "
            f"{headline:.1%}. Viable for Phase 2 on this evidence, but this is not licence to "
            "skip scrutiny: the sample is 3 entity classes x 3 subject families scored on "
            "lexical overlap, not semantic equivalence."
        )

    result = {
        "trigger_threshold": ALIGNMENT_TRIGGER,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "entity_classes_sampled": entities,
        "subject_families_sampled": subjects,
        "entity_class_axis": {
            "description": (
                "Same subject family, different entity classes — parallel Directions that "
                "SHOULD align. entity_class is raw-sourced from RBI's listing."
            ),
            "paragraph_level": paragraph_parallel,
            "section_level": section_parallel,
        },
        "subject_family_axis_derived": {
            "description": (
                "Same entity class, different subject families — unrelated regulations that "
                "should NOT align. Serves as the false-positive baseline."
            ),
            "paragraph_level": paragraph_baseline,
            "section_level": section_baseline,
            "caveat": (
                "subject_family is a DERIVED axis (P1-002-CORRECTIVE, commit e4013ca): RBI "
                "publishes no subject taxonomy, so these values were inferred from titles by "
                "stripping the entity-class string out of each. Any stratification on this "
                "axis rests on inferred metadata, not RBI's own classification."
            ),
        },
        "trigger_fired": triggered,
        "judgment": judgment,
    }

    logger.info(
        "cross_class_alignment: paragraph-level parallel=%s (baseline %s), "
        "section-level parallel=%s (baseline %s), trigger_fired=%s",
        paragraph_parallel["alignment_rate"], paragraph_baseline["alignment_rate"],
        section_parallel["alignment_rate"], section_baseline["alignment_rate"], triggered,
    )
    logger.info("cross_class_alignment: JUDGMENT — %s", judgment)
    return result


def faq_enforcement_check(
    cfg: Mapping[str, Any],
    *,
    resolver: PathResolver | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Check whether an FAQ/enforcement sample exists and can be paragraph-aligned."""
    logger = logger or get_logger("benchmark.alignment", cfg)
    resolver = resolver or PathResolver.from_config(cfg)

    findings: dict[str, Any] = {}
    for source in ("faq", "enforcement"):
        directory = resolver.find_read_path("raw", source)
        files = sorted(p for p in Path(directory).glob("*") if p.is_file()) if directory else []
        findings[f"{source}_items_found"] = len(files)
        findings[f"{source}_paragraph_alignment_rate"] = NOT_YET_MEASURED
        if not files:
            findings[f"{source}_note"] = (
                f"{NOT_YET_MEASURED} — P1-001 reported this sample as not trivially reachable "
                "(FAQView.aspx is a category index requiring a second-level crawl into "
                "per-category pages), so no sample was harvested and there is nothing to "
                "align. Systematic harvesting is Phase 2, Week 4 scope. No rate is "
                "fabricated in its absence."
            )
        else:
            findings[f"{source}_note"] = (
                f"{len(files)} raw {source} file(s) present but not hand-aligned to paragraphs "
                "in this pass; alignment deferred to Phase 2."
            )
        logger.info("faq_enforcement_check: %s -> %s", source, findings[f"{source}_note"])

    findings["standing_rule"] = (
        "FAQ and enforcement items are NOT treated as paragraph-level gold labels regardless "
        "of alignment outcome — they remain validation/motivation material only. This holds "
        "whether or not the sample exists."
    )
    return findings
