"""P2-002 cross-class obligation matching.

For every kept P2-001 candidate (rules v4) in a core entity class, find the best
counterpart candidates in each other core class's Directions on the same subject
family, record how strong each match is and what kind it is, and measure how
reliable those matches are against a blind human judgement.

This module proposes **candidate** matches only. It assigns no ``applies_to`` or
``differential_flag``.

Design rules that are load-bearing:

* **Content, never position.** Phase 1 (P1-004) found paragraph-level positional
  alignment at 32.8% / 41.6%, below the dossier's 60% trigger, so nothing here
  uses clause position. Counterparts are found by what the text says.
* **Two stages, kept distinguishable.** Stage 1 finds repeated wording (the
  consolidated Directions repeat sentences verbatim across entity classes).
  Stage 2 is semantic similarity. ``match_type`` records which one found a pair.
* **Three kinds of result, never collapsed.** ``scored`` (the target class has
  candidates in the family), ``no_candidates_in_family`` (it has a Direction
  there but no kept candidate) and ``no_direction_in_family`` (it has no
  Direction there). The last two are different absences and must stay separate
  for RQ2. No threshold is applied when matching; one is chosen later, on
  validation, and recorded with its source.
* **The embedder is injected.** The notebook passes the pinned bge model; tests
  pass :class:`FakeEmbedder`. No model is ever downloaded locally.
* **Deterministic.** Everything is seeded and sorted. Scores are rounded before
  ranking, so the same inputs and embeddings reproduce the match file byte for byte.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
import logging
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from src.benchmark.candidates import (
    NEAR_DUPLICATE_RATIO,
    ObligationCandidate,
    cue_sentence_bounds,
    normalise_sentence,
    wilson_interval,
)
from src.common.logging_setup import get_logger

BRANCH = "wip/P2-002"
VERSION = "v1"

STATUS_SCORED = "scored"
STATUS_NO_CANDIDATES = "no_candidates_in_family"
STATUS_NO_DIRECTION = "no_direction_in_family"
STATUSES = (STATUS_SCORED, STATUS_NO_CANDIDATES, STATUS_NO_DIRECTION)
STATUS_MATCHED = "matched"
STATUS_BELOW_THRESHOLD = "below_threshold"

MATCH_EXACT = "exact"
MATCH_NEAR_DUPLICATE = "near_duplicate"
MATCH_SEMANTIC = "semantic"
STAGE1_TYPES = (MATCH_EXACT, MATCH_NEAR_DUPLICATE)

EXCLUDED_FUNCTION_HEADING = "function_heading"
EXCLUDED_NO_FAMILY = "no_subject_family"

BAND_HIGH, BAND_MID, BAND_LOW = "high", "mid", "low"
BANDS = (BAND_HIGH, BAND_MID, BAND_LOW)
STRATUM_STAGE1 = "stage1"
STRATA = (STRATUM_STAGE1, BAND_HIGH, BAND_MID, BAND_LOW)

LABEL_SAME, LABEL_RELATED, LABEL_UNRELATED = "same", "related", "unrelated"
LABELS = (LABEL_SAME, LABEL_RELATED, LABEL_UNRELATED)

#: Columns the reviewer sees. Score, band and match type are never among them.
SHEET_COLUMNS = ("pair_id", "subject_family", "class_a", "span_a", "class_b", "span_b", "label", "note")
FORBIDDEN_SHEET_COLUMNS = ("score", "semantic_score", "lexical_score", "band", "stratum", "match_type")

THRESHOLD_SOURCE = "p2002_validation_v1"

Embedder = Callable[[Sequence[str]], np.ndarray]


class MatchingError(RuntimeError):
    """A stop condition or a broken invariant in P2-002."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchingConfig:
    core_classes: tuple[str, ...]
    function_headings: tuple[str, ...]
    expected_kept_candidates: int
    expected_raw_entity_classes: int
    whole_paragraph_max_chars: int
    prefix_min_chars: int
    shingle_words: int
    shingle_max_postings: int
    model_id: str
    model_revision: str
    max_seq_length: int
    batch_size: int
    checkpoint_every_units: int
    top_k: int
    score_decimals: int
    seeds: Mapping[str, int]
    smoke_candidates: int
    leakage_sample: int
    strata: Mapping[str, int]
    counterpart_target: float
    gates: Mapping[str, float]

    @classmethod
    def from_cfg(cls, cfg: Mapping[str, Any]) -> "MatchingConfig":
        m = cfg.get("matching")
        if not isinstance(m, Mapping):
            raise MatchingError("config is missing the `matching:` block (P2-002)")
        model = m["model"]
        return cls(
            core_classes=tuple(m["core_entity_classes"]),
            function_headings=tuple(m["function_headings"]),
            expected_kept_candidates=int(m["expected_kept_candidates"]),
            expected_raw_entity_classes=int(m["expected_raw_entity_classes"]),
            whole_paragraph_max_chars=int(m["units"]["whole_paragraph_max_chars"]),
            prefix_min_chars=int(m["stage1"]["prefix_min_chars"]),
            shingle_words=int(m["stage1"]["shingle_words"]),
            shingle_max_postings=int(m["stage1"]["shingle_max_postings"]),
            model_id=str(model["id"]),
            model_revision=str(model["revision"]),
            max_seq_length=int(model["max_seq_length"]),
            batch_size=int(model["batch_size"]),
            checkpoint_every_units=int(model["checkpoint_every_units"]),
            top_k=int(m["scoring"]["top_k"]),
            score_decimals=int(m["scoring"]["score_decimals"]),
            seeds=dict(m["seeds"]),
            smoke_candidates=int(m["smoke_candidates"]),
            leakage_sample=int(m["leakage_sample"]),
            strata=dict(m["validation"]["strata"]),
            counterpart_target=float(m["validation"]["counterpart_target"]),
            gates=dict(m["gates"]),
        )


# ---------------------------------------------------------------------------
# A1 preflight
# ---------------------------------------------------------------------------


def preflight(
    candidates: Sequence[ObligationCandidate],
    manifest: Sequence[Mapping[str, Any]],
    cells: Sequence[Mapping[str, Any]],
    mc: MatchingConfig,
) -> dict[str, Any]:
    """A1: stop unless the inputs are exactly what P2-001 closed on."""
    raw_classes = {r.get("entity_class_raw") for r in manifest}
    kept = [c for c in candidates if not c.exclusion_reason]
    problems = []
    if len(kept) != mc.expected_kept_candidates:
        problems.append(f"kept candidates {len(kept)} != expected {mc.expected_kept_candidates} (rules v4)")
    if len(raw_classes) != mc.expected_raw_entity_classes:
        problems.append(f"raw entity classes {len(raw_classes)} != expected {mc.expected_raw_entity_classes}")
    outside = sorted({c.entity_class for c in candidates} - raw_classes)
    if outside:
        problems.append(f"candidate entity_class outside the raw classes: {outside}")
    configured = set(mc.core_classes) | set(mc.function_headings)
    if configured != raw_classes:
        problems.append(f"D8 split does not cover the raw classes exactly: "
                        f"missing {sorted(raw_classes - configured)}, unknown {sorted(configured - raw_classes)}")
    if not cells:
        problems.append("matrix_v1.jsonl loaded no cells")
    if problems:
        raise MatchingError("A1 preflight failed: " + "; ".join(problems))
    return {
        "candidates_total": len(candidates),
        "candidates_kept": len(kept),
        "raw_entity_classes": len(raw_classes),
        "matrix_cells": len(cells),
        "matrix_cells_populated": sum(1 for c in cells if c.get("populated")),
    }


# ---------------------------------------------------------------------------
# A2 units, A3 blocking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """One matching unit: the sentence(s) of a kept cue, or a short whole paragraph."""

    unit_id: str
    candidate_id: str
    entity_class: str
    subject_family: str | None
    eligible: bool
    start: int
    end: int
    text: str
    normalised: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def unit_spans(candidate: ObligationCandidate, whole_paragraph_max_chars: int) -> list[tuple[int, int]]:
    """Character spans of a candidate's matching units (A2).

    Only kept cues contribute; an excluded cue's sentence is never a unit. One
    kept cue in a paragraph shorter than ``whole_paragraph_max_chars`` makes the
    whole paragraph one unit. Otherwise each kept cue's sentence is a unit, and
    overlapping sentences are merged.
    """
    text = candidate.span_text
    kept = [pos for pos, exc in zip(candidate.cue_position, candidate.cue_exclusions) if exc is None]
    if not kept:
        return []
    if len(kept) == 1 and len(text) < whole_paragraph_max_chars:
        spans = [(0, len(text))]
    else:
        spans = sorted(cue_sentence_bounds(text, s, e) for s, e in kept)
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out = []
    for s, e in merged:  # trim to content so offsets point at text, not whitespace
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            out.append((s, e))
    return out


def classify_candidates(
    candidates: Sequence[ObligationCandidate],
    doc_family: Mapping[str, str | None],
    mc: MatchingConfig,
) -> tuple[list[ObligationCandidate], list[ObligationCandidate], dict[str, Any]]:
    """A3: split kept candidates into matchable (core + family) and the rest, counted by class.

    Returns ``(eligible, core_without_family, accounting)``. Core candidates
    without a family cannot be blocked, so they are not matched. They are kept
    as leakage targets, because a counterpart in a family-less document is also
    one that blocking misses. Function-heading candidates are counted only.
    """
    core = set(mc.core_classes)
    eligible, core_no_family = [], []
    by_class: dict[str, Counter] = defaultdict(Counter)
    for cand in candidates:
        if cand.exclusion_reason:
            continue
        family = doc_family.get(cand.document_id)
        if cand.entity_class not in core:
            by_class[cand.entity_class][EXCLUDED_FUNCTION_HEADING] += 1
            by_class[cand.entity_class]["function_heading_with_family" if family else "function_heading_no_family"] += 1
        elif not family:
            core_no_family.append(cand)
            by_class[cand.entity_class][EXCLUDED_NO_FAMILY] += 1
        else:
            eligible.append(cand)
            by_class[cand.entity_class]["eligible"] += 1
    eligible.sort(key=lambda c: c.candidate_id)
    core_no_family.sort(key=lambda c: c.candidate_id)
    accounting = {
        "eligible": len(eligible),
        "excluded_no_subject_family_core": len(core_no_family),
        "excluded_function_heading": sum(v[EXCLUDED_FUNCTION_HEADING] for v in by_class.values()),
        "by_class": {cls: dict(sorted(v.items())) for cls, v in sorted(by_class.items())},
        "core_classes": list(mc.core_classes),
        "function_headings": list(mc.function_headings),
    }
    return eligible, core_no_family, accounting


def build_units(
    eligible: Sequence[ObligationCandidate],
    core_no_family: Sequence[ObligationCandidate],
    doc_family: Mapping[str, str | None],
    mc: MatchingConfig,
) -> list[Unit]:
    """Units for every core kept candidate, ordered by candidate_id then offset.

    That order is the row order of every embedding and lexical matrix, and it
    keeps each candidate's units contiguous (required by the max-over-units
    roll-up).
    """
    units: list[Unit] = []
    tagged = [(c, True) for c in eligible] + [(c, False) for c in core_no_family]
    for cand, is_eligible in sorted(tagged, key=lambda t: t[0].candidate_id):
        for k, (s, e) in enumerate(unit_spans(cand, mc.whole_paragraph_max_chars)):
            raw = cand.span_text[s:e]
            units.append(Unit(
                unit_id=f"{cand.candidate_id}#u{k:02d}",
                candidate_id=cand.candidate_id,
                entity_class=cand.entity_class,
                subject_family=doc_family.get(cand.document_id),
                eligible=is_eligible,
                start=s,
                end=e,
                text=raw,
                normalised=normalise_sentence(raw),
            ))
    return units


def embedding_text(unit: Unit) -> str:
    """What the model embeds: the unit text with whitespace collapsed (case kept)."""
    return " ".join(unit.text.split())


# ---------------------------------------------------------------------------
# A4 stage 1: repeated wording
# ---------------------------------------------------------------------------


def stage1_pair(a: str, b: str, prefix_min_chars: int) -> bool:
    """The pairwise test of ``near_duplicate_clusters()`` with one scale guard.

    Same normalisation, same prefix rule, same ``NEAR_DUPLICATE_RATIO``. The
    guard: a prefix match only counts when the shorter text has at least
    ``prefix_min_chars`` characters. At corpus scale, single-link clustering
    would otherwise chain every sentence starting "the bank shall" into one
    cluster through a short unit.
    """
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if a.startswith(b) or b.startswith(a):
        return shorter >= prefix_min_chars
    longer = max(len(a), len(b))
    if 2 * shorter / (shorter + longer) < NEAR_DUPLICATE_RATIO:  # ratio's upper bound
        return False
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < NEAR_DUPLICATE_RATIO or sm.quick_ratio() < NEAR_DUPLICATE_RATIO:
        return False
    return sm.ratio() >= NEAR_DUPLICATE_RATIO


def _candidate_text_pairs(texts: Sequence[str], mc: MatchingConfig) -> set[tuple[int, int]]:
    """Pairs of distinct texts worth the pairwise test.

    Two sources, so the pairwise test runs on proposals, not on all n^2 pairs:

    * a shared leading ``prefix_min_chars`` characters (every qualifying prefix
      match shares them);
    * a shared word ``shingle_words``-gram whose posting list is at most
      ``shingle_max_postings`` long. Two long texts that are at least 90%
      similar share many 5-grams, and the rare ones among them propose the pair.
    """
    pairs: set[tuple[int, int]] = set()
    by_prefix: dict[str, list[int]] = defaultdict(list)
    postings: dict[tuple[str, ...], list[int]] = defaultdict(list)
    n = mc.shingle_words
    for i, t in enumerate(texts):
        if len(t) >= mc.prefix_min_chars:
            by_prefix[t[: mc.prefix_min_chars]].append(i)
        words = t.split()
        for g in {tuple(words[j:j + n]) for j in range(max(0, len(words) - n + 1))}:
            postings[g].append(i)
    for group in by_prefix.values():
        for x in range(len(group)):
            for y in range(x + 1, len(group)):
                pairs.add((group[x], group[y]))
    for plist in postings.values():
        if 1 < len(plist) <= mc.shingle_max_postings:
            for x in range(len(plist)):
                for y in range(x + 1, len(plist)):
                    pairs.add((plist[x], plist[y]))
    return pairs


def _star_clusters(texts: Sequence[str], mc: MatchingConfig) -> list[int]:
    """Leader index for each text: star clustering, not single link.

    Texts are visited longest first. Each joins the first existing leader it
    passes :func:`stage1_pair` with directly, or becomes a leader itself. Every
    member is therefore a direct near-duplicate of its cluster's leader.

    Single link (``near_duplicate_clusters()``) was measured on this corpus and
    rejected. 26% of multi-text clusters then held a pair of texts less than 90%
    similar, some as low as 0.09. A truncated fragment ("for opening an account
    of a partnership firm, the bank shall obtain the certified") chained the
    partnership-firm and trust document lists, two different obligations, into
    one cluster.
    """
    neighbours: dict[int, set[int]] = defaultdict(set)
    for i, j in _candidate_text_pairs(texts, mc):
        neighbours[i].add(j)
        neighbours[j].add(i)
    order = sorted(range(len(texts)), key=lambda i: (-len(texts[i]), texts[i]))
    rank = {i: r for r, i in enumerate(order)}
    leader = [-1] * len(texts)
    for i in order:
        for j in sorted((n for n in neighbours[i] if leader[n] == n), key=rank.__getitem__):
            if stage1_pair(texts[i], texts[j], mc.prefix_min_chars):
                leader[i] = j
                break
        else:
            leader[i] = i
    return leader


def stage1_clusters(units: Sequence[Unit], mc: MatchingConfig) -> dict[str, Any]:
    """Near-duplicate clusters of eligible units, per subject-family block.

    Clusters are formed over ALL eligible units in a block, same class included,
    because the validation sheet needs every repeat of a text to keep one pair
    per text. Only clusters that span two or more core classes produce stage-1
    matches, and only those are the cross-class headline. The normalisation and
    the pairwise test are ``near_duplicate_clusters()``'s. The linkage is star,
    not single link (see :func:`_star_clusters`).
    """
    by_family: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        if u.eligible:
            by_family[u.subject_family].append(u)

    clusters: list[dict[str, Any]] = []
    for family in sorted(by_family):
        members = by_family[family]
        texts = sorted({u.normalised for u in members})
        index = {t: i for i, t in enumerate(texts)}
        leader = _star_clusters(texts, mc)
        comps: dict[int, list[Unit]] = defaultdict(list)
        for u in members:
            comps[leader[index[u.normalised]]].append(u)
        for comp in comps.values():
            if len(comp) < 2:
                continue
            comp.sort(key=lambda u: u.unit_id)
            classes = sorted({u.entity_class for u in comp})
            clusters.append({
                "subject_family": family,
                "unit_ids": [u.unit_id for u in comp],
                "candidate_ids": sorted({u.candidate_id for u in comp}),
                "entity_classes": classes,
                "n_classes": len(classes),
                "distinct_texts": len({u.normalised for u in comp}),
            })
    clusters.sort(key=lambda c: (c["subject_family"], c["unit_ids"][0]))
    for k, c in enumerate(clusters, start=1):
        c["cluster_id"] = f"s1c_{k:05d}"
    unit_cluster = {uid: c["cluster_id"] for c in clusters for uid in c["unit_ids"]}
    cross = [c for c in clusters if c["n_classes"] >= 2]
    summary = {
        "clusters_total": len(clusters),
        "clusters_cross_class": len(cross),
        "clusters_within_one_class": len(clusters) - len(cross),
        "cross_class_span_distribution": dict(sorted(Counter(c["n_classes"] for c in cross).items())),
        "units_in_cross_class_clusters": sum(len(c["unit_ids"]) for c in cross),
        "candidates_in_cross_class_clusters": len({cid for c in cross for cid in c["candidate_ids"]}),
        "cross_class_clusters_all_identical": sum(1 for c in cross if c["distinct_texts"] == 1),
        "eligible_units": sum(len(v) for v in by_family.values()),
        "prefix_min_chars": mc.prefix_min_chars,
        "near_duplicate_ratio": NEAR_DUPLICATE_RATIO,
    }
    return {"summary": summary, "clusters": clusters, "unit_cluster": unit_cluster}


# ---------------------------------------------------------------------------
# A5 embeddings, A6 lexical baseline
# ---------------------------------------------------------------------------


class FakeEmbedder:
    """Deterministic stand-in for tests: hashed bag of words, L2-normalised.

    Texts sharing words get similar vectors, so ranking behaviour is testable
    without a model. Never used for a real run.
    """

    model_id = "fake-hashing-embedder"
    model_revision = "test"

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"[a-z0-9]+", t.lower()):
                h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
                out[i, h % self.dim] += 1.0 if (h >> 64) % 2 else -1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


def texts_fingerprint(texts: Sequence[str]) -> str:
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def embed_with_checkpoints(
    texts: Sequence[str],
    embed: Embedder,
    checkpoint_dir: Path | str | None = None,
    every: int = 5000,
    logger: logging.Logger | None = None,
) -> np.ndarray:
    """Embed in chunks of ``every`` texts, saving each chunk so a dead session resumes.

    A checkpoint is reused only if it was written for exactly these texts
    (fingerprint check). A chunk from another run is never silently mixed in.
    """
    logger = logger or get_logger("benchmark.matching")
    if checkpoint_dir is None:
        return np.asarray(embed(list(texts)), dtype=np.float32)
    ckpt = Path(checkpoint_dir)
    ckpt.mkdir(parents=True, exist_ok=True)
    meta_path = ckpt / "meta.json"
    fp = texts_fingerprint(texts)
    if meta_path.is_file() and json.loads(meta_path.read_text(encoding="utf-8")).get("fingerprint") != fp:
        for stale in ckpt.glob("emb_*.npy"):
            stale.unlink()
        logger.warning("embedding checkpoints were for different texts; discarded")
    meta_path.write_text(json.dumps({"fingerprint": fp, "n": len(texts), "every": every}), encoding="utf-8")
    parts = []
    for start in range(0, len(texts), every):
        path = ckpt / f"emb_{start:07d}.npy"
        chunk = texts[start:start + every]
        if path.is_file():
            arr = np.load(path)
            if arr.shape[0] == len(chunk):
                parts.append(arr)
                logger.info("embeddings %d-%d: resumed from checkpoint", start, start + len(chunk))
                continue
        arr = np.asarray(embed(list(chunk)), dtype=np.float32)
        np.save(path, arr)
        parts.append(arr)
        logger.info("embeddings %d-%d: computed", start, start + len(chunk))
    return np.vstack(parts) if parts else np.zeros((0, 0), dtype=np.float32)


def fit_lexical(units: Sequence[Unit]):
    """A6: TF-IDF over the whole unit set, L2-normalised rows (cosine = dot product)."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(lowercase=True, sublinear_tf=True, norm="l2", token_pattern=r"(?u)\b\w\w+\b")
    return vec.fit_transform([u.normalised for u in units])


# ---------------------------------------------------------------------------
# A5-A7 scoring
# ---------------------------------------------------------------------------


def _groups(units: Sequence[Unit], rows: Sequence[int]) -> tuple[list[str], np.ndarray]:
    """(candidate ids in order, start offsets of each candidate's rows) for contiguous rows."""
    ids, starts = [], []
    for k, r in enumerate(rows):
        cid = units[r].candidate_id
        if not ids or ids[-1] != cid:
            ids.append(cid)
            starts.append(k)
    return ids, np.asarray(starts, dtype=np.int64)


def _rollup(sim: np.ndarray, src_starts: np.ndarray, tgt_starts: np.ndarray) -> np.ndarray:
    """Paragraph-pair score = max over their unit pairs."""
    per_tgt = np.maximum.reduceat(sim, tgt_starts, axis=1)
    return np.maximum.reduceat(per_tgt, src_starts, axis=0)


def _stage1_link(
    src_units: Sequence[Unit], tgt_units: Sequence[Unit], unit_cluster: Mapping[str, str], prefix_min_chars: int
) -> tuple[str, str, Unit, Unit] | None:
    """A stage-1 link between two candidates: (type, cluster_id, source unit, target unit).

    Needs a unit pair in the same cluster that ALSO passes the pairwise test
    directly. Two members of one star cluster are each close to the leader but
    not necessarily to each other.
    """
    best = None
    for su in src_units:
        cs = unit_cluster.get(su.unit_id)
        if cs is None:
            continue
        for tu in tgt_units:
            if unit_cluster.get(tu.unit_id) != cs:
                continue
            if not stage1_pair(su.normalised, tu.normalised, prefix_min_chars):
                continue
            kind = MATCH_EXACT if su.normalised == tu.normalised else MATCH_NEAR_DUPLICATE
            cand = (0 if kind == MATCH_EXACT else 1, su.unit_id, tu.unit_id, kind, cs, su, tu)
            if best is None or cand[:3] < best[:3]:
                best = cand
    if best is None:
        return None
    return best[3], best[4], best[5], best[6]


def score_matches(
    units: Sequence[Unit],
    vectors: np.ndarray,
    lexical,
    unit_cluster: Mapping[str, str],
    populated_cells: set[tuple[str, str]],
    mc: MatchingConfig,
    *,
    model_id: str,
    model_revision: str,
    logger: logging.Logger | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """A5 + A6 + A7: one record per (eligible source candidate, other core class).

    Semantic paragraph-pair score = max cosine over unit pairs. The top
    ``top_k`` targets per target class are kept, ranked by semantic score, then
    lexical score, then candidate_id. The lexical top-1 is recorded too, for the
    top-1 agreement metric. Absences get one of the two absence statuses. No
    threshold is applied.
    """
    logger = logger or get_logger("benchmark.matching")
    d = mc.score_decimals
    if vectors.shape[0] != len(units) or lexical.shape[0] != len(units):
        raise MatchingError("vectors / lexical rows do not align with units")

    by_block_class: dict[tuple[str, str], list[int]] = defaultdict(list)
    units_by_cand: dict[str, list[Unit]] = defaultdict(list)
    for i, u in enumerate(units):
        if u.eligible:
            by_block_class[(u.subject_family, u.entity_class)].append(i)
            units_by_cand[u.candidate_id].append(u)
    families = sorted({f for f, _ in by_block_class})
    core = list(mc.core_classes)

    records: list[dict[str, Any]] = []
    agree = scored_n = 0
    for family in families:
        present = {cls: by_block_class[(family, cls)] for cls in core if (family, cls) in by_block_class}
        grouped = {cls: _groups(units, rows) for cls, rows in present.items()}
        for src_cls in sorted(present):
            src_rows = present[src_cls]
            src_ids, src_starts = grouped[src_cls]
            for tgt_cls in core:
                if tgt_cls == src_cls:
                    continue
                if tgt_cls not in present:
                    status = STATUS_NO_CANDIDATES if (tgt_cls, family) in populated_cells else STATUS_NO_DIRECTION
                    for sid in src_ids:
                        records.append(_record(sid, src_cls, family, tgt_cls, status, [], None, None,
                                               None, None, model_id, model_revision))
                    continue
                tgt_rows = present[tgt_cls]
                tgt_ids, tgt_starts = grouped[tgt_cls]
                sim = vectors[src_rows] @ vectors[tgt_rows].T
                sem = np.round(_rollup(sim.astype(np.float64), src_starts, tgt_starts), d)
                lex_sim = (lexical[src_rows] @ lexical[tgt_rows].T).toarray()
                lex = np.round(_rollup(lex_sim, src_starts, tgt_starts), d)
                rank = np.broadcast_to(np.arange(len(tgt_ids)), sem.shape)
                order = np.lexsort((rank, -lex, -sem), axis=1)[:, : mc.top_k]
                lex_top = np.lexsort((rank, -sem, -lex), axis=1)[:, 0]
                src_bounds = list(src_starts) + [len(src_rows)]
                tgt_bounds = list(tgt_starts) + [len(tgt_rows)]
                for a, sid in enumerate(src_ids):
                    tops = []
                    for b in order[a]:
                        tid = tgt_ids[b]
                        link = _stage1_link(units_by_cand[sid], units_by_cand[tid], unit_cluster,
                                            mc.prefix_min_chars)
                        if link is not None:
                            kind, cluster_id, su, tu = link
                        else:
                            block = sim[src_bounds[a]:src_bounds[a + 1], tgt_bounds[b]:tgt_bounds[b + 1]]
                            ia, ib = np.unravel_index(int(np.argmax(block)), block.shape)
                            su = units[src_rows[src_bounds[a] + ia]]
                            tu = units[tgt_rows[tgt_bounds[b] + ib]]
                            kind, cluster_id = MATCH_SEMANTIC, None
                        tops.append({
                            "candidate_id": tid,
                            "semantic_score": float(sem[a, b]),
                            "lexical_score": float(lex[a, b]),
                            "match_type": kind,
                            "source_unit_offsets": [su.start, su.end],
                            "target_unit_offsets": [tu.start, tu.end],
                            "near_dup_cluster_id": cluster_id,
                        })
                    margin = round(tops[0]["semantic_score"] - tops[1]["semantic_score"], d) if len(tops) > 1 else None
                    lb = int(lex_top[a])
                    scored_n += 1
                    agree += int(tgt_ids[lb] == tops[0]["candidate_id"])
                    records.append(_record(
                        sid, src_cls, family, tgt_cls, STATUS_SCORED, tops, tops[0]["near_dup_cluster_id"],
                        margin, tgt_ids[lb], float(lex[a, lb]), model_id, model_revision,
                    ))
    records.sort(key=lambda r: (r["source_candidate_id"], r["target_entity_class"]))
    stats = {
        "records": len(records),
        "scored_records": scored_n,
        "top1_agreement_semantic_vs_lexical": (agree / scored_n) if scored_n else None,
        "top1_agreement_n": scored_n,
    }
    logger.info("score_matches: %s", stats)
    return records, stats


def _record(source_id, source_cls, family, target_cls, status, tops, cluster_id, margin,
            lex_best_id, lex_best_score, model_id, model_revision) -> dict[str, Any]:
    return {
        "source_candidate_id": source_id,
        "source_entity_class": source_cls,
        "subject_family": family,
        "target_entity_class": target_cls,
        "status": status,
        "top_targets": tops,
        "near_dup_cluster_id": cluster_id,
        "margin_top1_top2": margin,
        # Additions to the P2-002 §P schema, needed by A6 (lexical top-1
        # agreement, and precision at matched coverage):
        "lexical_best_candidate_id": lex_best_id,
        "lexical_best_score": lex_best_score,
        "model_id": model_id,
        "model_revision": model_revision,
    }


def match_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Status counts overall and by class pair, plus the best-score distribution."""
    overall = Counter(r["status"] for r in records)
    by_pair: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        by_pair[f"{r['source_entity_class']} -> {r['target_entity_class']}"][r["status"]] += 1
    best = np.array([r["top_targets"][0]["semantic_score"] for r in records if r["status"] == STATUS_SCORED])
    types = Counter(r["top_targets"][0]["match_type"] for r in records if r["status"] == STATUS_SCORED)
    dist = None
    if best.size:
        qs = [0.0, 0.05, 0.1, 0.25, 0.333333, 0.5, 0.666667, 0.75, 0.9, 0.95, 1.0]
        dist = {f"q{q:.3f}": round(float(np.quantile(best, q)), 6) for q in qs}
        dist["mean"] = round(float(best.mean()), 6)
        dist["n"] = int(best.size)
    return {
        "status_overall": {s: overall.get(s, 0) for s in STATUSES},
        "status_by_class_pair": {k: {s: v.get(s, 0) for s in STATUSES} for k, v in sorted(by_pair.items())},
        "best_semantic_score_distribution": dist,
        "top1_match_type": dict(types),
    }


# ---------------------------------------------------------------------------
# Bands (C1), leakage (A8)
# ---------------------------------------------------------------------------


def band_edges(best_scores: Sequence[float]) -> dict[str, Any]:
    """Tertile edges of the best-match semantic scores of ``scored`` rows.

    high = score >= high_lower (top third); mid = mid_lower <= score < high_lower;
    low = score < mid_lower. Defined before any validation sample is drawn.
    """
    s = sorted(float(x) for x in best_scores)
    if len(s) < 3:
        raise MatchingError("need at least 3 scored rows to define tertile bands")
    n = len(s)
    return {
        "rule": "tertiles_of_best_scored",
        "n": n,
        "mid_lower": s[n // 3],
        "high_lower": s[(2 * n) // 3],
        "min": s[0],
        "max": s[-1],
    }


def band_of(score: float, edges: Mapping[str, Any]) -> str:
    if score >= edges["high_lower"]:
        return BAND_HIGH
    if score >= edges["mid_lower"]:
        return BAND_MID
    return BAND_LOW


def leakage_check(
    units: Sequence[Unit],
    vectors: np.ndarray,
    mc: MatchingConfig,
    high_lower: float,
) -> dict[str, Any]:
    """A8: search 200 seeded core candidates against ALL other core classes, unblocked.

    Targets include core candidates whose document has no subject family: a
    counterpart there is also one blocking cannot see. A source leaks when its
    best cross-class match is outside its own family and scores at or above the
    high-band lower edge.
    """
    d = mc.score_decimals
    cand_rows: dict[str, list[int]] = defaultdict(list)
    for i, u in enumerate(units):
        cand_rows[u.candidate_id].append(i)
    meta = {u.candidate_id: (u.entity_class, u.subject_family, u.eligible) for u in units}
    pool = sorted(cid for cid, (_c, _f, elig) in meta.items() if elig)
    sample = sorted(random.Random(mc.seeds["leakage"]).sample(pool, min(mc.leakage_sample, len(pool))))
    all_rows = np.arange(len(units))
    all_ids, all_starts = _groups(units, all_rows)
    rows = []
    for sid in sample:
        src_cls, src_fam, _ = meta[sid]
        srows = cand_rows[sid]
        sim = vectors[srows] @ vectors.T
        para = np.round(np.maximum.reduceat(sim.astype(np.float64), all_starts, axis=1).max(axis=0), d)
        best = None
        best_in = None
        for j, tid in enumerate(all_ids):
            tcls, tfam, _ = meta[tid]
            if tcls == src_cls:
                continue
            key = (-para[j], tid)
            if best is None or key < best[0]:
                best = (key, tid, tfam, float(para[j]))
            if tfam == src_fam and (best_in is None or key < best_in[0]):
                best_in = (key, tid, float(para[j]))
        _, tid, tfam, score = best
        rows.append({
            "source_candidate_id": sid,
            "source_entity_class": src_cls,
            "source_family": src_fam,
            "best_candidate_id": tid,
            "best_family": tfam,
            "best_score": score,
            "best_in_family_score": best_in[2] if best_in else None,
            "outside_family": tfam != src_fam,
        })
    return summarise_leakage(rows, high_lower, seed=mc.seeds["leakage"])


def summarise_leakage(rows: Sequence[Mapping[str, Any]], high_lower: float, *, seed: int | None = None) -> dict[str, Any]:
    """Recomputable from the per-source rows, so Part C re-applies the official band edge."""
    n = len(rows)
    leaks = [r for r in rows if r["outside_family"] and r["best_score"] >= high_lower]
    k = len(leaks)
    return {
        "n": n,
        "seed": seed,
        "high_lower_edge_used": high_lower,
        "leaks": k,
        "leakage_rate": (k / n) if n else None,
        "leakage_wilson_95": list(wilson_interval(k, n)) if n else None,
        "best_outside_family_any_score": sum(1 for r in rows if r["outside_family"]),
        "best_outside_family_no_family_target": sum(1 for r in rows if r["outside_family"] and not r["best_family"]),
        "rows": list(rows),
    }


# ---------------------------------------------------------------------------
# Orchestration (used by the notebook and by the integration test)
# ---------------------------------------------------------------------------


def run_stage2(
    candidates: Sequence[ObligationCandidate],
    manifest: Sequence[Mapping[str, Any]],
    cells: Sequence[Mapping[str, Any]],
    mc: MatchingConfig,
    embed: Embedder,
    *,
    model_id: str,
    model_revision: str,
    subset_ids: Iterable[str] | None = None,
    checkpoint_dir: Path | str | None = None,
    token_lengths: Callable[[Sequence[str]], Sequence[int]] | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Units -> blocking -> stage 1 -> embeddings -> scoring -> leakage, in one call.

    ``subset_ids`` restricts the run to those candidates (the 200-candidate smoke
    run). ``token_lengths`` (the model tokenizer) counts units that exceed
    ``max_seq_length``. Those are truncated by the model, not dropped.
    """
    logger = logger or get_logger("benchmark.matching")
    doc_family = {r["document_id"]: r.get("subject_family") for r in manifest}
    pool = candidates
    if subset_ids is not None:
        keep = set(subset_ids)
        pool = [c for c in candidates if c.candidate_id in keep]
    eligible, core_no_family, accounting = classify_candidates(pool, doc_family, mc)
    units = build_units(eligible, core_no_family, doc_family, mc)
    texts = [embedding_text(u) for u in units]
    truncated = None
    if token_lengths is not None:
        lengths = list(token_lengths(texts))
        truncated = sum(1 for n in lengths if n > mc.max_seq_length)
    stage1 = stage1_clusters(units, mc)
    vectors = embed_with_checkpoints(texts, embed, checkpoint_dir, mc.checkpoint_every_units, logger)
    lexical = fit_lexical(units)
    populated = {(c["entity_class"], c["subject_family"]) for c in cells if c.get("populated")}
    records, stats = score_matches(units, vectors, lexical, stage1["unit_cluster"], populated, mc,
                                   model_id=model_id, model_revision=model_revision, logger=logger)
    metrics = match_metrics(records)
    edges = None
    leakage = None
    best = [r["top_targets"][0]["semantic_score"] for r in records if r["status"] == STATUS_SCORED]
    if len(best) >= 3:
        edges = band_edges(best)
        leakage = leakage_check(units, vectors, mc, edges["high_lower"])
    blocks = {u.subject_family for u in units if u.eligible}
    fam_classes: dict[str, set] = defaultdict(set)
    for u in units:
        if u.eligible:
            fam_classes[u.subject_family].add(u.entity_class)
    unit_metrics = {
        "units_total": len(units),
        "units_eligible": sum(1 for u in units if u.eligible),
        "units_core_no_family": sum(1 for u in units if not u.eligible),
        "units_truncated": truncated,
        "max_seq_length": mc.max_seq_length,
        "unit_chars_max": max((len(t) for t in texts), default=0),
        "blocks": len(blocks),
        "families_shared_by_2plus_core_classes": sum(1 for v in fam_classes.values() if len(v) >= 2),
        "units_fingerprint": texts_fingerprint(texts),
    }
    return {
        "units": units,
        "vectors": vectors,
        "records": records,
        "stage1": stage1,
        "accounting": accounting,
        "unit_metrics": unit_metrics,
        "score_stats": stats,
        "match_metrics": metrics,
        "provisional_band_edges": edges,
        "leakage": leakage,
    }


# ---------------------------------------------------------------------------
# C2 validation sheet
# ---------------------------------------------------------------------------


def _take_first_free(bucket: list, cand_clusters, used_cands: set, used_clusters: set):
    """Pop pairs until one shares no candidate and no stage-1 cluster with those already chosen."""
    while bucket:
        p = bucket.pop()
        ids = {p["source_candidate_id"], p["target_candidate_id"]}
        cl = cand_clusters[p["source_candidate_id"]] | cand_clusters[p["target_candidate_id"]]
        if ids & used_cands or cl & used_clusters:
            continue
        used_cands |= ids
        used_clusters |= cl
        return p
    return None


def _unit_text(cands: Mapping[str, ObligationCandidate], cid: str, offsets: Sequence[int]) -> str:
    return " ".join(cands[cid].span_text[offsets[0]:offsets[1]].split())


def draw_validation_sheet(
    records: Sequence[Mapping[str, Any]],
    edges: Mapping[str, Any],
    unit_cluster: Mapping[str, str],
    cands: Mapping[str, ObligationCandidate],
    mc: MatchingConfig,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """C2: 60 blind pairs (10 stage-1, 15 high, 15 mid, 20 low), seeded.

    Each scored record contributes its top-1 pair. A pair is sampled at most
    once, whichever direction it was scored in. Within a stratum, pairs are
    taken round-robin over class pairs (then families, in a seeded random
    order), so the sheet spreads across classes and families. No two sampled pairs may share a candidate or a stage-1
    cluster on either side, so the reviewer never judges the same text twice.
    """
    cand_clusters: dict[str, set[str]] = defaultdict(set)
    for uid, cid in unit_cluster.items():
        cand_clusters[uid.split("#u")[0]].add(cid)

    seen: set[frozenset] = set()
    pools: dict[str, list[dict[str, Any]]] = {s: [] for s in STRATA}
    for r in sorted(records, key=lambda r: (r["source_candidate_id"], r["target_entity_class"])):
        if r["status"] != STATUS_SCORED:
            continue
        top = r["top_targets"][0]
        key = frozenset((r["source_candidate_id"], top["candidate_id"]))
        if key in seen:
            continue
        seen.add(key)
        stratum = STRATUM_STAGE1 if top["match_type"] in STAGE1_TYPES else band_of(top["semantic_score"], edges)
        pools[stratum].append({
            "source_candidate_id": r["source_candidate_id"],
            "target_candidate_id": top["candidate_id"],
            "class_a": r["source_entity_class"],
            "class_b": r["target_entity_class"],
            "subject_family": r["subject_family"],
            "semantic_score": top["semantic_score"],
            "lexical_score": top["lexical_score"],
            "match_type": top["match_type"],
            "band": band_of(top["semantic_score"], edges),
            "stratum": stratum,
            "source_unit_offsets": top["source_unit_offsets"],
            "target_unit_offsets": top["target_unit_offsets"],
            "near_dup_cluster_id": top["near_dup_cluster_id"],
        })

    rng = random.Random(mc.seeds["validation_sheet"])
    used_cands: set[str] = set()
    used_clusters: set[str] = set()
    chosen: list[dict[str, Any]] = []
    shortfall = {}
    for stratum in STRATA:
        want = int(mc.strata[stratum])
        pool = pools[stratum][:]
        rng.shuffle(pool)
        by_group: dict[tuple, list] = defaultdict(list)
        for p in pool:
            by_group[(tuple(sorted((p["class_a"], p["class_b"]))), p["subject_family"])].append(p)
        by_pair: dict[tuple, list[tuple]] = defaultdict(list)
        for g in sorted(by_group):
            by_pair[g[0]].append(g)
        pair_keys = sorted(by_pair)
        rng.shuffle(pair_keys)
        for pk in pair_keys:  # seeded family order: alphabetical order would favour "A..." families
            rng.shuffle(by_pair[pk])
        taken = 0
        progress = True
        while taken < want and progress:
            progress = False
            for pk in pair_keys:  # one pair per class pair per round
                if taken >= want:
                    break
                families = by_pair[pk]
                for gi, g in enumerate(families):
                    accepted = _take_first_free(by_group[g], cand_clusters, used_cands, used_clusters)
                    if accepted is None:
                        continue
                    chosen.append(accepted)
                    taken += 1
                    progress = True
                    families.append(families.pop(gi))  # rotate so the next round tries another family
                    break
        if taken < want:
            shortfall[stratum] = {"wanted": want, "drawn": taken, "pool": len(pools[stratum])}

    rng.shuffle(chosen)
    rows, key = [], {}
    for k, p in enumerate(chosen, start=1):
        pid = f"P{k:03d}"
        rows.append({
            "pair_id": pid,
            "subject_family": p["subject_family"],
            "class_a": p["class_a"],
            "span_a": _unit_text(cands, p["source_candidate_id"], p["source_unit_offsets"]),
            "class_b": p["class_b"],
            "span_b": _unit_text(cands, p["target_candidate_id"], p["target_unit_offsets"]),
            "label": "",
            "note": "",
        })
        key[pid] = p
    meta = {
        "seed": mc.seeds["validation_sheet"],
        "strata_wanted": dict(mc.strata),
        "strata_drawn": dict(Counter(p["stratum"] for p in chosen)),
        "pool_sizes": {s: len(v) for s, v in pools.items()},
        "shortfall": shortfall,
        "band_edges": dict(edges),
    }
    return rows, {"meta": meta, "pairs": key}


def assert_sheet_blind(rows: Sequence[Mapping[str, str]]) -> None:
    """Stop condition: the sheet must not reveal score, band or match type."""
    if not rows:
        raise MatchingError("validation sheet is empty")
    cols = tuple(rows[0].keys())
    if cols != SHEET_COLUMNS:
        raise MatchingError(f"sheet columns {cols} != {SHEET_COLUMNS}")
    leaked = [c for c in cols if any(f in c.lower() for f in FORBIDDEN_SHEET_COLUMNS)]
    if leaked:
        raise MatchingError(f"sheet would reveal {leaked}")
    if any((r.get("label") or r.get("note")) for r in rows):
        raise MatchingError("sheet must be written with blank label and note")


def write_sheet(rows: Sequence[Mapping[str, str]], path: Path | str, *, force: bool = False) -> Path:
    path = Path(path)
    if path.is_file() and not force:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            if any((r.get("label") or "").strip() or (r.get("note") or "").strip() for r in csv.DictReader(fh)):
                raise MatchingError(f"{path} already holds labels; refusing to overwrite")
    assert_sheet_blind(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# D1 scoring, D2 threshold
# ---------------------------------------------------------------------------


def _rate(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, "rate": (k / n) if n else None, "wilson_95": list(wilson_interval(k, n)) if n else None}


def read_labelled_sheet(path: Path | str) -> list[dict[str, str]]:
    """The labelled sheet as saved by Excel: ``utf-8-sig`` so a BOM never sticks to ``pair_id``."""
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if rows and "pair_id" not in rows[0]:
        raise MatchingError(f"{path}: no pair_id column (columns: {list(rows[0])})")
    return rows


def score_validation(labelled: Sequence[Mapping[str, str]], key: Mapping[str, Any]) -> dict[str, Any]:
    """D1: per stratum counterpart rate ((same + related) / n), same rate, related share."""
    pairs = key["pairs"]
    problems = []
    rows = []
    for r in labelled:
        label = (r.get("label") or "").strip().lower()
        if label not in LABELS:
            problems.append(f"{r.get('pair_id')}: {label!r}")
            continue
        p = pairs.get(r["pair_id"])
        if p is None:
            problems.append(f"{r.get('pair_id')}: not in key")
            continue
        rows.append({**p, "label": label, "pair_id": r["pair_id"]})
    if problems:
        return {"complete": False, "problems": problems, "labelled": len(rows)}
    if len(rows) != len(pairs):
        return {"complete": False, "problems": [f"{len(rows)} labelled of {len(pairs)}"], "labelled": len(rows)}

    def block(rs):
        n = len(rs)
        same = sum(1 for x in rs if x["label"] == LABEL_SAME)
        rel = sum(1 for x in rs if x["label"] == LABEL_RELATED)
        return {"n": n, "same": same, "related": rel, "unrelated": n - same - rel,
                "counterpart_rate": _rate(same + rel, n), "same_rate": _rate(same, n),
                "related_share": (rel / n) if n else None}

    by_stratum = {s: block([x for x in rows if x["stratum"] == s]) for s in STRATA}
    return {"complete": True, "overall": block(rows), "by_stratum": by_stratum, "rows": rows}


def choose_threshold(result: Mapping[str, Any], edges: Mapping[str, Any], target: float) -> dict[str, Any]:
    """D2: the lowest band edge whose counterpart rate reaches ``target``.

    Per band, walking down from the top: a band's lower edge qualifies when that
    band's own counterpart rate reaches ``target`` and every band above it
    qualified too. (An average over the bands at and above an edge would let a
    weak low band ride on the strong bands above it.) Chosen on the same sample
    it is scored on, so the rate at the threshold is optimistic.
    """
    rates = {b: result["by_stratum"][b]["counterpart_rate"]["rate"] for b in BANDS}
    candidates = [("high_lower", edges["high_lower"], BAND_HIGH),
                  ("mid_lower", edges["mid_lower"], BAND_MID),
                  ("min", edges["min"], BAND_LOW)]
    evaluated = []
    chosen = None
    open_ = True
    for name, value, band in candidates:
        rate = rates[band]
        ok = open_ and rate is not None and rate >= target
        evaluated.append({"edge": name, "value": value, "band": band, "counterpart_rate": rate, "qualifies": ok})
        if ok:
            chosen = {"edge": name, "value": value, "band": band, "counterpart_rate": rate}
        else:
            open_ = False
    return {"target": target, "rule": "per_band_walk_down", "evaluated": evaluated, "chosen": chosen,
            "note": "chosen on the validation sample it is scored on; the rate at the threshold is optimistic"}


def apply_threshold(records: Sequence[Mapping[str, Any]], threshold: float) -> list[dict[str, Any]]:
    """D2 output: scored rows become matched / below_threshold on the top-1 semantic score alone.

    A stage-1 top-1 pair gets no exemption: low-scoring near-duplicates are mostly
    prefix fragments, which the stage-1 validation stratum never sampled. Every
    row keeps its top-3 targets and their match types.
    """
    out = []
    for r in records:
        r = dict(r)
        if r["status"] == STATUS_SCORED:
            if r["top_targets"][0]["semantic_score"] >= threshold:
                r["status"] = STATUS_MATCHED
            else:
                r["status"] = STATUS_BELOW_THRESHOLD
        r["threshold_value"] = threshold
        r["threshold_source"] = THRESHOLD_SOURCE
        out.append(r)
    return out


def lexical_at_matched_coverage(
    records: Sequence[Mapping[str, Any]], result: Mapping[str, Any], threshold: float
) -> dict[str, Any]:
    """A6 on the validation sample: both methods' counterpart rate at the same coverage.

    Coverage = share of scored rows whose best semantic score is >= threshold.
    The lexical cut-off covers the same share of scored rows, taken over the
    same quantity it is applied to: the lexical score of each row's semantic
    top-1 target (not ``lexical_best_score``, which may belong to another
    target). The validation pairs were drawn by semantic band, so this
    comparison favours the semantic method; it is reported as such.
    """
    scored = [r for r in records if r["status"] == STATUS_SCORED]
    sem = sorted((r["top_targets"][0]["semantic_score"] for r in scored), reverse=True)
    lexs = sorted((r["top_targets"][0]["lexical_score"] for r in scored), reverse=True)
    covered = sum(1 for s in sem if s >= threshold)
    coverage = covered / len(sem) if sem else 0.0
    lex_cut = lexs[covered - 1] if covered else float("inf")
    rows = [x for x in result["rows"] if x["stratum"] in BANDS]
    cp = lambda rs: _rate(sum(1 for x in rs if x["label"] in (LABEL_SAME, LABEL_RELATED)), len(rs))
    return {
        "coverage": coverage,
        "semantic_threshold": threshold,
        "lexical_threshold": lex_cut,
        "semantic": cp([x for x in rows if x["semantic_score"] >= threshold]),
        "lexical": cp([x for x in rows if x["lexical_score"] >= lex_cut]),
        "caveat": "validation pairs were drawn by semantic band; the lexical figure uses the pair's lexical "
                  "score for the semantic top-1 target",
    }


# Reporting only: text that repeats across classes without being a regulated-entity
# obligation. Known v4 misses from P2-001; recorded here for P2-004's filter, never
# used to change the extraction rules or the match statuses.
BOILERPLATE_PATTERNS: dict[str, re.Pattern] = {
    "repeal_savings": re.compile(
        r"\brepeal\w*\b[^.;]{0,120}\b(shall not in any way prejudicially affect|deemed (?:as|to be) governed)"
        r"|\bdeemed (?:as|to be) governed by these directions", re.I),
    # a government actor, not the regulated entity, is the one who "shall"
    "state_nodal_officer": re.compile(
        r"\b(?:all the )?states?\s*(?:and|/)\s*uts?\b[^.;]{0,40}\b(?:shall|may) (?:notify|appoint|designate)"
        r"|\b(?:the )?(?:state|central) nodal officers?\b(?:\s*\(\w+\))?\s+shall\b|\bthe cno shall\b", re.I),
    # data-dictionary row: field type then field length on the same line ("Alpha Numeric 10", "Character 200")
    "format_table_row": re.compile(
        r"\b(?:alpha[ \t]*-?[ \t]*numeric|character|numeric|decimal)[ \t]+\d{1,4}\b", re.I),
}


def boilerplate_kind(text: str) -> str | None:
    for kind, pat in BOILERPLATE_PATTERNS.items():
        if pat.search(text):
            return kind
    return None


def boilerplate_cluster_split(clusters: Sequence[Mapping[str, Any]], unit_text: Mapping[str, str]) -> dict[str, Any]:
    """Stage-1 cross-class clusters with and without boilerplate text (any unit matching a pattern)."""
    cross = [c for c in clusters if c["n_classes"] >= 2]
    kinds: Counter = Counter()
    all_cands: set[str] = set()
    flagged_cands: set[str] = set()
    for c in cross:
        all_cands.update(c["candidate_ids"])
        found = [k for k in (boilerplate_kind(unit_text[u]) for u in c["unit_ids"]) if k]
        if found:
            kinds[Counter(found).most_common(1)[0][0]] += 1
            flagged_cands.update(c["candidate_ids"])
    flagged = sum(kinds.values())
    return {
        "clusters_cross_class": len(cross),
        "clusters_boilerplate": flagged,
        "clusters_without_boilerplate": len(cross) - flagged,
        "by_pattern": {k: kinds.get(k, 0) for k in BOILERPLATE_PATTERNS},
        "candidates_in_cross_class_clusters": len(all_cands),
        "candidates_in_boilerplate_clusters": len(flagged_cands),
        "patterns": {k: p.pattern for k, p in BOILERPLATE_PATTERNS.items()},
    }
