"""P2-004: the T1 candidate benchmark, the validation sample and the annotation sheets.

Label rules are Guidelines v3 (data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md):

* ``applies_to`` is an item-level human judgement read from the span's own text.
  It is never derived from the per-class judgements.
* Per compared class the rater gives ``same | different | none | unsure`` plus a
  ``matched_paragraph_id`` for same/different. These are counterpart evidence.
* ``differential_flag`` is derived from the per-class judgements (v3.6):
  any different -> class-specific; else any same -> shared; all none -> absent;
  otherwise (only none/unsure) -> ambiguous, which goes to adjudication.
* ``not_obligation = yes`` rejects the item (v3.3).

Candidate labels come from P2-002 matches and are always ``label_status:
candidate``. ``matched`` cannot tell ``same`` from ``different``, so the automatic
flag is only ``absent`` or ``shared_or_class_specific``.

Compared classes are the target core classes whose status for the source is
``scored`` (``matched`` / ``below_threshold``). ``no_direction_in_family`` classes
are never compared and never become ``none``.

Everything here is deterministic and seeded; no LLM or embedding call.
"""

from __future__ import annotations

import csv
import io
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.common.errors import FoundationError

VERSION = "v1"
T1_SUBDIR = "t1"
CANDIDATE_BENCHMARK_FILE = f"t1_candidate_benchmark_{VERSION}.jsonl"
CANDIDATE_METRICS_FILE = f"t1_candidate_benchmark_metrics_{VERSION}.json"
SAMPLE_FILE = f"p2004_sample_{VERSION}.jsonl"
KEY_FILE = f"p2004_key_{VERSION}.json"
DRAW_LOG_FILE = f"p2004_draw_log_{VERSION}.json"
PASS1_SHEET = "annotation_p2004_karan_pass1.csv"
SECOND_RATER_SHEET = "annotation_p2004_{rater}.csv"
PILOT_PASS2_SHEET = "annotation_pilot_karan_pass2.csv"
MINUTES_FILE = "p2004_minutes.csv"

JUDGE_SAME, JUDGE_DIFFERENT, JUDGE_NONE, JUDGE_UNSURE = "same", "different", "none", "unsure"
JUDGEMENTS = (JUDGE_SAME, JUDGE_DIFFERENT, JUDGE_NONE, JUDGE_UNSURE)
FLAG_SHARED, FLAG_CLASS_SPECIFIC, FLAG_ABSENT = "shared", "class-specific", "absent"
FLAG_AMBIGUOUS = "ambiguous"
CANDIDATE_FLAG_POSITIVE = "shared_or_class_specific"
STATUS_MATCHED, STATUS_BELOW, STATUS_NO_DIRECTION = "matched", "below_threshold", "no_direction_in_family"
NOT_OBLIGATION_YES = "yes"
LABEL_STATUS_CANDIDATE = "candidate"
PROVENANCE_CANDIDATE = "auto:p2002_matches_v1"

ROW_ITEM, ROW_CLASS = "item", "class"
SHEET_COLUMNS = ("item_id", "block", "row_type", "source_class", "subject_family", "source_paragraph_id",
                 "source_span", "target_class", "target_candidates", "applies_to", "applies_to_rationale",
                 "not_obligation", "judgement", "matched_paragraph_id", "note")
ITEM_INPUT_COLUMNS = ("applies_to", "applies_to_rationale", "not_obligation", "note")
CLASS_INPUT_COLUMNS = ("judgement", "matched_paragraph_id", "note")
INPUT_COLUMNS = ("applies_to", "applies_to_rationale", "not_obligation", "judgement", "matched_paragraph_id", "note")
#: Column-name fragments that would reveal hidden fields (scores, bands, statuses, candidate labels, strata).
FORBIDDEN_COLUMN_WORDS = ("score", "band", "status", "rank", "stratum", "retest", "semantic", "lexical",
                          "applies_to_candidate", "per_class_candidate", "differential", "flag", "subset")
MINUTES_COLUMNS = ("rater", "block", "started_at", "ended_at", "minutes", "note")
APPLIES_TO_SEPARATOR = ";"
PARAGRAPH_ID_RE = re.compile(r"^md_\d+::p\d{5}$")

SHEET_HEADER = (
    "# Guidelines v3 (data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md). Item rows: applies_to (from the span's "
    "own text; names separated by ';'), applies_to_rationale, not_obligation (yes, with the reason in note), note. "
    "Class rows: judgement = same | different | none | unsure, and matched_paragraph_id for same/different. "
    "Candidates are shown in random order with no scores. No AI tools. Don't open anyone else's file or the key."
)


class T1Error(FoundationError):
    """A P2-004 stop condition or a broken invariant."""


@dataclass(frozen=True)
class T1Config:
    annotation_hours: float
    minutes_per_item: float
    minutes_per_item_basis: str
    retest_fraction: float
    pilot_retest_items: int
    underpowered_below: int
    per_class_floor: int
    min_compared_classes: int
    max_compared_classes: int
    block_size: int
    second_raters: tuple[str, ...]
    second_rater_items: int
    second_rater_blocks: int
    primary: str
    source_paragraph_max_chars: int
    target_paragraph_max_chars: int
    seeds: Mapping[str, int]
    core_classes: tuple[str, ...]
    stand_in_classes: tuple[str, ...]
    guidelines_version: str
    matches_sha256_prefix: str
    expected_kept_candidates: int
    expected_eligible_candidates: int

    @classmethod
    def from_cfg(cls, c: Mapping[str, Any]) -> "T1Config":
        t = c["t1"]
        return cls(
            annotation_hours=float(t["annotation_hours"]),
            minutes_per_item=float(t["minutes_per_item"]),
            minutes_per_item_basis=str(t["minutes_per_item_basis"]),
            retest_fraction=float(t["retest_fraction"]),
            pilot_retest_items=int(t["pilot_retest_items"]),
            underpowered_below=int(t["underpowered_below"]),
            per_class_floor=int(t["per_class_floor"]),
            min_compared_classes=int(t["min_compared_classes"]),
            max_compared_classes=int(t["max_compared_classes"]),
            block_size=int(t["block_size"]),
            second_raters=tuple(t["second_raters"]),
            second_rater_items=int(t["second_rater_items"]),
            second_rater_blocks=int(t["second_rater_blocks"]),
            primary=str(t["primary"]),
            source_paragraph_max_chars=int(t["source_paragraph_max_chars"]),
            target_paragraph_max_chars=int(t["target_paragraph_max_chars"]),
            seeds={k: int(v) for k, v in t["seeds"].items()},
            core_classes=tuple(c["matching"]["core_entity_classes"]),
            stand_in_classes=("Payment and Settlement System", "Foreign Exchange Management"),
            guidelines_version=str(t["guidelines_version"]),
            matches_sha256_prefix=str(t["matches_sha256_prefix"]),
            expected_kept_candidates=int(t["expected_kept_candidates"]),
            expected_eligible_candidates=int(t["expected_eligible_candidates"]),
        )

    @property
    def applies_to_vocabulary(self) -> tuple[str, ...]:
        """v2.2 / v3.2: the 11 core classes plus the two stand-ins."""
        return self.core_classes + self.stand_in_classes


# ---------------------------------------------------------------------------
# A2 label rules (v3.6) and candidate labels
# ---------------------------------------------------------------------------


def derive_flag(judgements: Mapping[str, str]) -> dict[str, Any]:
    """v3.6: the item flag from its per-class judgements.

    Returns ``flag`` (None when ambiguous), ``ambiguous`` and
    ``needs_adjudication`` (any ``unsure``, or ambiguous).
    """
    vals = list(judgements.values())
    bad =[j for j in vals if j not in JUDGEMENTS]
    if bad or not vals:
        raise T1Error(f"cannot derive a flag from judgements {dict(judgements)}")
    if JUDGE_DIFFERENT in vals:
        flag = FLAG_CLASS_SPECIFIC
    elif JUDGE_SAME in vals:
        flag = FLAG_SHARED
    elif all(j == JUDGE_NONE for j in vals):
        flag = FLAG_ABSENT
    else:
        flag = None
    return {"flag": flag, "ambiguous": flag is None,
            "needs_adjudication": flag is None or JUDGE_UNSURE in vals}


def candidate_labels(source_class: str, per_class_status: Mapping[str, str]) -> dict[str, Any]:
    """A3: automatic labels from P2-002 statuses; ``matched`` reads as same-or-different, ``below_threshold`` as none."""
    for cls, st in per_class_status.items():
        if st not in (STATUS_MATCHED, STATUS_BELOW):
            raise T1Error(f"{cls}: only scored classes are compared, got status {st!r}")
    matched = sorted(c for c, s in per_class_status.items() if s == STATUS_MATCHED)
    return {
        "applies_to_candidate": sorted({source_class, *matched}),
        "differential_flag_candidate": CANDIDATE_FLAG_POSITIVE if matched else FLAG_ABSENT,
        "per_class_candidate": dict(sorted(per_class_status.items())),
        "label_status": LABEL_STATUS_CANDIDATE,
        "provenance": PROVENANCE_CANDIDATE,
    }


# ---------------------------------------------------------------------------
# A3 temporal metadata (deterministic only)
# ---------------------------------------------------------------------------

_PATH = r"\d+(?:\.\d+)*(?:\s?\([0-9a-z]+\))*"
_REF_RE = re.compile(rf"(?:sub-)?paragraphs?\s+(?P<a>{_PATH})(?:\s*(?:to|-|–)\s*(?P<b>{_PATH}))?", re.I)
#: "<ref> ... shall be deleted/omitted/substituted", with no other paragraph, sub-para, clause or item
#: mentioned in between (so "in Paragraph 4: (i) Sub-paragraph 4 (6) shall be substituted" and
#: "In paragraph 4, a) Sub-para (1) shall be substituted" do not end paragraph 4).
_DELETE_RE = re.compile(
    rf"(?:sub-)?paragraphs?\s+(?P<list>{_PATH}(?:\s*(?:,|and|to|-|–)\s*{_PATH})*)"
    r"(?:(?!para|clause|item)[^.;]){0,160}?\bshall\s+be\s+(?P<how>deleted|omitted|substituted)", re.I)
_LIST_PART_RE = re.compile(rf"(?P<a>{_PATH})(?:\s*(?:to|-|–)\s*(?P<b>{_PATH}))?", re.I)


def _expand(a: str, b: str | None) -> list[str]:
    """A numeric range expands only between plain integers; anything else keeps its endpoints."""
    a, b = re.sub(r"\s+", "", a).lower(), re.sub(r"\s+", "", b or "").lower()
    if b and a.isdigit() and b.isdigit() and int(a) <= int(b) and int(b) - int(a) <= 200:
        return [str(n) for n in range(int(a), int(b) + 1)]
    return [a, b] if b else [a]


def _expand_list(raw: str) -> list[str]:
    """``"28, 30 and 33"`` / ``"408 to 416 and 442 to 454"`` -> every clause path named."""
    return [p for m in _LIST_PART_RE.finditer(raw) for p in _expand(m["a"], m["b"])]


def parse_paragraph_refs(refs: Iterable[str]) -> set[str]:
    """``["paragraph 4", "sub-paragraph 4 (10)", "paragraphs 86 to 92"]`` -> clause paths."""
    out: set[str] = set()
    for ref in refs:
        for m in _REF_RE.finditer(ref or ""):
            out.update(_expand(m["a"], m["b"]))
    return out


def ref_covers(ref: str, clause_path: str | None) -> bool:
    """A cited paragraph covers this paragraph when it is the same path or an ancestor of it."""
    if not clause_path:
        return False
    cp = clause_path.lower()
    return cp == ref or cp.startswith(ref + "(") or cp.startswith(ref + ".")


def _parse_long_date(raw: str | None) -> str | None:
    from src.supplementary.common import parse_listing_date

    return parse_listing_date(raw)


def in_force_from(doc: Mapping[str, Any], first_paragraph_text: str | None) -> tuple[str | None, str]:
    """``(iso date, basis)``: the "(Updated as on ...)" date if the Direction has one, else its letterhead date."""
    stamp = _parse_long_date(doc.get("update_date"))
    if stamp:
        return stamp, "updated_as_on"
    head = _parse_long_date((first_paragraph_text or "")[:600])
    if head:
        return head, "issue_date_letterhead"
    return None, "none"


def amendment_index(items: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """md_id -> amendments linked to it, each with its parsed paragraph refs and explicit deletions/substitutions."""
    by_md: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        fields = it.get("fields") or {}
        refs = parse_paragraph_refs(fields.get("paragraph_refs") or [])
        ends = {}
        for m in _DELETE_RE.finditer(it.get("text") or ""):
            for ref in _expand_list(m["list"]):
                ends.setdefault(ref, m["how"].lower())
        for md in fields.get("linked_md_ids") or []:
            by_md[md].append({"item_id": it["item_id"], "published_date": it.get("published_date"),
                              "refs": refs, "ends": ends})
    for md in by_md:
        by_md[md].sort(key=lambda a: a["item_id"])
    return by_md


def temporal_fields(md_id: str, clause_path: str | None, from_date: str | None,
                    amendments: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """A3: ``amended_by`` (refs covering this clause path) and ``in_force_to`` (explicit, later deletion/substitution)."""
    amended_by, end = [], None
    for a in amendments.get(md_id, ()):
        if any(ref_covers(r, clause_path) for r in a["refs"]):
            amended_by.append(a["item_id"])
        hits = [how for r, how in a["ends"].items() if ref_covers(r, clause_path)]
        if hits and from_date and a["published_date"] and a["published_date"] > from_date:
            if end is None or a["published_date"] < end["date"]:
                end = {"date": a["published_date"], "item_id": a["item_id"], "how": sorted(set(hits))[0]}
    return {"amended_by": amended_by, "in_force_to": end["date"] if end else None,
            "in_force_to_basis": end}


def era_of(iso: str | None, cutoff: str) -> str:
    from src.supplementary.common import ERA_POST, ERA_PRE, ERA_UNKNOWN

    if not iso:
        return ERA_UNKNOWN
    return ERA_POST if date.fromisoformat(iso) >= date.fromisoformat(cutoff) else ERA_PRE


# ---------------------------------------------------------------------------
# A3 candidate benchmark
# ---------------------------------------------------------------------------


def item_id_for(candidate_id: str) -> str:
    return "t1_" + candidate_id.removeprefix("t1c_")


def paragraph_of(candidate_id: str) -> str:
    return candidate_id.removeprefix("t1c_")


def build_candidate_benchmark(
    *,
    eligible: Sequence[Any],
    units_by_candidate: Mapping[str, Sequence[Mapping[str, Any]]],
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    paragraphs: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Mapping[str, Any]],
    first_paragraph: Mapping[str, str],
    amendments: Mapping[str, Sequence[Mapping[str, Any]]],
    era_cutoff: str,
    boilerplate_kind: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """One record per eligible, non-boilerplate core candidate (§P schema)."""
    out, boiler = [], Counter()
    for cand in sorted(eligible, key=lambda c: c.candidate_id):
        units = sorted(units_by_candidate.get(cand.candidate_id, ()), key=lambda u: u["start"])
        kinds = [k for k in (boilerplate_kind(u["text"]) for u in units) if k]
        if kinds:
            boiler[kinds[0]] += 1
            continue
        recs = records_by_source.get(cand.candidate_id, ())
        status = {r["target_entity_class"]: r["status"] for r in recs}
        scored = {c: s for c, s in status.items() if s in (STATUS_MATCHED, STATUS_BELOW)}
        not_compared = {c: s for c, s in sorted(status.items()) if s == STATUS_NO_DIRECTION}
        other = {c: s for c, s in status.items() if c not in scored and c not in not_compared}
        if other:
            raise T1Error(f"{cand.candidate_id}: unexpected statuses {other}")
        para = paragraphs[cand.paragraph_id]
        doc = manifest[cand.document_id]
        start, basis = in_force_from(doc, first_paragraph.get(cand.document_id))
        temporal = temporal_fields(cand.document_id, para.get("clause_path"), start, amendments)
        top = {r["target_entity_class"]: [t["candidate_id"] for t in r["top_targets"]]
               for r in recs if r["target_entity_class"] in scored}
        out.append({
            "item_id": item_id_for(cand.candidate_id),
            "source_candidate_id": cand.candidate_id,
            "md_id": cand.document_id,
            "paragraph_id": cand.paragraph_id,
            "entity_class": cand.entity_class,
            "subject_family": doc.get("subject_family"),
            "section_id": para.get("section_id"),
            "clause_path": para.get("clause_path"),
            "obligation_span": {"paragraph_id": cand.paragraph_id,
                                "units": [[u["start"], u["end"]] for u in units],
                                "text": " … ".join(" ".join(u["text"].split()) for u in units)},
            "compared_classes": sorted(scored),
            "not_compared": not_compared,
            **candidate_labels(cand.entity_class, scored),
            "top_targets": dict(sorted(top.items())),
            "in_force_from": start,
            "in_force_from_basis": basis,
            "in_force_to": temporal["in_force_to"],
            "in_force_to_basis": temporal["in_force_to_basis"],
            "amended_by": temporal["amended_by"],
            "era": era_of(start, era_cutoff),
        })
    n = len(out)
    cover = lambda pred: {"k": sum(1 for r in out if pred(r)), "n": n}
    metrics = {
        "eligible_candidates": len(eligible),
        "excluded_boilerplate": sum(boiler.values()),
        "excluded_boilerplate_by_pattern": dict(sorted(boiler.items())),
        "records": n,
        "compared_classes_distribution": dict(sorted(Counter(len(r["compared_classes"]) for r in out).items())),
        "records_with_2plus_compared": sum(1 for r in out if len(r["compared_classes"]) >= 2),
        "differential_flag_candidate": dict(sorted(Counter(r["differential_flag_candidate"] for r in out).items())),
        "temporal_coverage": {
            "in_force_from": cover(lambda r: r["in_force_from"]),
            "in_force_from_basis": dict(sorted(Counter(r["in_force_from_basis"] for r in out).items())),
            "amended_by_nonempty": cover(lambda r: r["amended_by"]),
            "in_force_to": cover(lambda r: r["in_force_to"]),
            "era": dict(sorted(Counter(r["era"] for r in out).items())),
        },
        "by_class": {cls: dict(sorted(Counter(len(r["compared_classes"]) >= 2 for r in out
                                              if r["entity_class"] == cls).items()))
                     for cls in sorted({r["entity_class"] for r in out})},
    }
    return out, metrics


# ---------------------------------------------------------------------------
# A4 size and the checkpoint re-derivation
# ---------------------------------------------------------------------------


def size_calc(tc: T1Config, minutes_per_item: float | None = None, budget_minutes: float | None = None) -> dict[str, Any]:
    """§K: N = floor(remaining / (m (1 + r))) after the pilot retest is taken out of the budget."""
    m = tc.minutes_per_item if minutes_per_item is None else float(minutes_per_item)
    budget = tc.annotation_hours * 60 if budget_minutes is None else float(budget_minutes)
    pilot = tc.pilot_retest_items * m
    remaining = budget - pilot
    per_item = m * (1 + tc.retest_fraction)
    n = max(0, math.floor(remaining / per_item)) if per_item > 0 else 0
    retest = math.ceil(tc.retest_fraction * n)
    return {
        "budget_minutes": budget, "minutes_per_item": m, "pilot_retest_minutes": pilot,
        "remaining_minutes": remaining, "minutes_per_item_with_retest": per_item,
        "n_target": n, "retest_items": retest,
        "pass1_minutes": n * m, "retest_minutes": retest * m,
        "total_minutes": n * m + retest * m + pilot,
        "underpowered": n < tc.underpowered_below,
        "blocks": math.ceil(n / tc.block_size) if n else 0,
    }


def checkpoint(tc: T1Config, measured_minutes: float, items_done: int, sample_size: int) -> dict[str, Any]:
    """B2: re-derive N from measured m; only whole blocks are ever dropped, from the end."""
    if items_done <= 0:
        raise T1Error("checkpoint needs at least one labelled item")
    m = measured_minutes / items_done
    calc = size_calc(tc, minutes_per_item=m)
    n = min(calc["n_target"], sample_size)
    keep_blocks = n // tc.block_size if n < sample_size else math.ceil(sample_size / tc.block_size)
    return {**calc, "measured_minutes_per_item": m, "items_done": items_done,
            "blocks_to_keep": keep_blocks, "items_kept": min(sample_size, keep_blocks * tc.block_size),
            "flag_underpowered": calc["n_target"] < tc.underpowered_below}


# ---------------------------------------------------------------------------
# A5 sample
# ---------------------------------------------------------------------------


def allocate(pool_sizes: Mapping[str, int], n: int, floor: int) -> dict[str, int]:
    """Proportional allocation with a floor for classes whose pool has at least ``floor`` items (largest remainder)."""
    alloc = {c: (floor if s >= floor else 0) for c, s in pool_sizes.items()}
    left = n - sum(alloc.values())
    if left < 0:
        raise T1Error(f"n={n} is below the floors ({sum(alloc.values())})")
    while left > 0:
        room = {c: s - alloc[c] for c, s in pool_sizes.items() if s > alloc[c]}
        if not room:
            break
        rt = sum(pool_sizes[c] for c in room)
        raw = {c: left * pool_sizes[c] / rt for c in room}
        add = {c: min(room[c], math.floor(v)) for c, v in raw.items()}
        rem = left - sum(add.values())
        for c in sorted(raw, key=lambda c: (-(raw[c] - math.floor(raw[c])), c)):
            if rem <= 0:
                break
            if add[c] < room[c]:
                add[c] += 1
                rem -= 1
        if sum(add.values()) == 0:
            break
        for c, v in add.items():
            alloc[c] += v
        left = n - sum(alloc.values())
    return dict(sorted(alloc.items()))


def _round_robin(groups: Mapping[Any, list], k: int, rng: random.Random) -> list:
    order = sorted(groups)
    rng.shuffle(order)
    queues = {g: list(groups[g]) for g in order}
    out = []
    while len(out) < k and any(queues.values()):
        for g in order:
            if queues[g] and len(out) < k:
                out.append(queues[g].pop(0))
    return out


def interleave(by_class: Mapping[str, Sequence[Any]], seed: int) -> list[Any]:
    """Stratum-interleaved order: item i of a class with n items sits at (i + offset) / n, so any prefix stays stratified."""
    rng = random.Random(seed)
    placed = []
    for cls in sorted(by_class):
        items = list(by_class[cls])
        off = rng.random()
        placed.extend(((i + off) / len(items), cls, i, it) for i, it in enumerate(items))
    placed.sort(key=lambda t: (t[0], t[1], t[2]))
    return [t[3] for t in placed]


def draw_sample(records: Sequence[Mapping[str, Any]], tc: T1Config, n: int, *, excluded_paragraphs: set[str],
                excluded_candidates: set[str]) -> dict[str, Any]:
    """A5: pool, stratified draw, compared classes (K), interleaved blocks, retest and second-rater subsets."""
    seeds = tc.seeds
    excl = Counter()
    pool = []
    for r in records:
        if len(r["compared_classes"]) < tc.min_compared_classes:
            excl["fewer_than_min_compared"] += 1
        elif r["paragraph_id"] in excluded_paragraphs:
            excl["pilot"] += 1
        elif r["source_candidate_id"] in excluded_candidates:
            excl["p2002_validation_pair"] += 1
        else:
            pool.append(r)
    by_class: dict[str, list] = defaultdict(list)
    for r in sorted(pool, key=lambda r: r["item_id"]):
        by_class[r["entity_class"]].append(r)
    alloc = allocate({c: len(v) for c, v in by_class.items()}, n, tc.per_class_floor)

    rng = random.Random(seeds["sample"])
    chosen: dict[str, list] = {}
    for cls in sorted(by_class):
        groups: dict[tuple, list] = defaultdict(list)
        for r in by_class[cls]:
            groups[(r["subject_family"], r["differential_flag_candidate"])].append(r)
        for g in groups.values():
            rng.shuffle(g)
        chosen[cls] = _round_robin(groups, alloc[cls], rng)

    rng_k = random.Random(seeds["compared"])
    items = []
    for cls in sorted(chosen):
        for r in sorted(chosen[cls], key=lambda r: r["item_id"]):
            comp = sorted(r["compared_classes"])
            k = min(tc.max_compared_classes, len(comp))
            items.append({**r, "sample_compared_classes": sorted(rng_k.sample(comp, k))})
    by_cls_items = defaultdict(list)
    for it in items:
        by_cls_items[it["entity_class"]].append(it)
    rng_o = random.Random(seeds["order"])
    for cls in sorted(by_cls_items):
        rng_o.shuffle(by_cls_items[cls])
    ordered = interleave(by_cls_items, seeds["order"])
    for pos, it in enumerate(ordered):
        it["order"] = pos + 1
        it["block"] = pos // tc.block_size + 1

    retest = draw_retest(ordered, tc.retest_fraction, seeds["retest"])
    second = draw_second_rater(ordered, tc.second_rater_items, tc.second_rater_blocks, seeds["second_rater"])
    return {"items": ordered, "retest_ids": retest, "second_rater_ids": second, "allocation": alloc,
            "pool_size": len(pool), "pool_by_class": {c: len(v) for c, v in sorted(by_class.items())},
            "excluded": dict(sorted(excl.items()))}


def _largest_remainder(sizes: Mapping[str, int], total: int, fraction_of: int) -> dict[str, int]:
    raw = {c: total * s / fraction_of for c, s in sizes.items()} if fraction_of else {c: 0 for c in sizes}
    q = {c: min(sizes[c], math.floor(v)) for c, v in raw.items()}
    rem = total - sum(q.values())
    for c in sorted(raw, key=lambda c: (-(raw[c] - math.floor(raw[c])), c)):
        if rem <= 0:
            break
        if q[c] < sizes[c]:
            q[c] += 1
            rem -= 1
    return q


def draw_retest(ordered: Sequence[Mapping[str, Any]], fraction: float, seed: int) -> list[str]:
    """A5: ceil(fraction * n), stratified by class, evenly spaced through each class's order so it spans blocks."""
    total = math.ceil(fraction * len(ordered))
    by_cls = defaultdict(list)
    for it in ordered:
        by_cls[it["entity_class"]].append(it)
    quota = _largest_remainder({c: len(v) for c, v in by_cls.items()}, total, len(ordered))
    rng = random.Random(seed)
    out = []
    for cls in sorted(by_cls):
        items, q = by_cls[cls], quota[cls]
        if not q:
            continue
        off = rng.random()
        idx = sorted({min(len(items) - 1, math.floor((j + off) * len(items) / q)) for j in range(q)})
        out.extend(items[i]["item_id"] for i in idx)
    return sorted(out)


def draw_second_rater(ordered: Sequence[Mapping[str, Any]], n: int, blocks: int, seed: int) -> list[str]:
    """Sprint §4: n items from the first ``blocks`` blocks, stratified by class."""
    head = [it for it in ordered if it["block"] <= blocks]
    by_cls = defaultdict(list)
    for it in head:
        by_cls[it["entity_class"]].append(it)
    quota = _largest_remainder({c: len(v) for c, v in by_cls.items()}, min(n, len(head)), len(head))
    rng = random.Random(seed)
    out = []
    for cls in sorted(by_cls):
        out.extend(it["item_id"] for it in rng.sample(by_cls[cls], quota[cls]))
    return sorted(out)


# ---------------------------------------------------------------------------
# A6 sheets
# ---------------------------------------------------------------------------


def _cap(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def sheet_rows(items: Sequence[Mapping[str, Any]], paragraphs: Mapping[str, Mapping[str, Any]], tc: T1Config,
               *, blocks: Mapping[str, int] | None = None, shuffle_seed: int | None = None) -> list[dict[str, str]]:
    """Long format: one item row, then one row per compared class; every input cell blank."""
    rng = random.Random(tc.seeds["target_shuffle"] if shuffle_seed is None else shuffle_seed)
    rows = []
    for it in items:
        block = str((blocks or {}).get(it["item_id"], it["block"]))
        para = paragraphs[it["paragraph_id"]]
        span = (f"OBLIGATION: {it['obligation_span']['text']}\n\n"
                f"PARAGRAPH [{it['paragraph_id']}]: {_cap(para['text'], tc.source_paragraph_max_chars)}")
        base = {c: "" for c in SHEET_COLUMNS}
        rows.append({**base, "item_id": it["item_id"], "block": block, "row_type": ROW_ITEM,
                     "source_class": it["entity_class"], "subject_family": it["subject_family"] or "",
                     "source_paragraph_id": it["paragraph_id"], "source_span": span})
        for cls in it["sample_compared_classes"]:
            ids = [paragraph_of(c) for c in it["top_targets"][cls][:2]]
            rng.shuffle(ids)
            shown = "\n\n".join(f"[{pid}] {_cap(paragraphs[pid]['text'], tc.target_paragraph_max_chars)}" for pid in ids)
            rows.append({**base, "item_id": it["item_id"], "block": block, "row_type": ROW_CLASS,
                         "source_class": it["entity_class"], "subject_family": it["subject_family"] or "",
                         "target_class": cls, "target_candidates": shown})
    return rows


def assert_blind(rows: Sequence[Mapping[str, str]]) -> None:
    """§AB: a drawn sheet reveals no score, band, status or candidate label, and every input cell is blank."""
    if not rows:
        raise T1Error("empty sheet")
    for r in rows:
        if tuple(r) != SHEET_COLUMNS:
            raise T1Error(f"sheet columns {tuple(r)} != {SHEET_COLUMNS}")
        filled = [c for c in INPUT_COLUMNS if (r[c] or "").strip()]
        if filled:
            raise T1Error(f"{r['item_id']}: input cells {filled} must be blank on a drawn sheet")
    for col in SHEET_COLUMNS:
        if col in INPUT_COLUMNS:
            continue
        if any(w in col for w in FORBIDDEN_COLUMN_WORDS):
            raise T1Error(f"sheet column {col!r} would reveal a hidden field")


def read_sheet(path: Path | str, *, require_id: bool = True) -> list[dict[str, str]]:
    """Excel-saved sheets: ``utf-8-sig`` (BOM) and leading ``# ...`` note lines, possibly quoted, are skipped."""
    rows = parse_sheet_text(Path(path).read_bytes().decode("utf-8-sig"))
    if require_id and rows and "item_id" not in rows[0] and "label_id" not in rows[0]:
        raise T1Error(f"{path}: no item_id column (columns: {list(rows[0])})")
    return rows


def parse_sheet_text(text: str) -> list[dict[str, str]]:
    """CSV text after any leading ``# ...`` note lines (possibly quoted by Excel)."""
    lines = text.splitlines(keepends=True)
    start = 0
    while start < len(lines) and lines[start].lstrip('"').startswith("#"):
        start += 1
    return list(csv.DictReader(io.StringIO("".join(lines[start:]), newline="")))


def refuse_if_labelled(path: Path, input_columns: Sequence[str]) -> None:
    """Never overwrite a sheet that holds a person's work (data/benchmark/** is gitignored)."""
    if path.exists():
        filled = sum(1 for r in read_sheet(path, require_id=False) for c in input_columns if (r.get(c) or "").strip())
        if filled:
            raise T1Error(f"refusing to overwrite {path}: it holds {filled} filled cell(s)")


def write_sheet(path: Path, rows: Sequence[Mapping[str, str]], columns: Sequence[str], *, header: str | None,
                input_columns: Sequence[str]) -> Path:
    refuse_if_labelled(path, input_columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    # BOM: Excel (Windows and Mac) only decodes UTF-8 CSVs correctly with one; every reader uses utf-8-sig.
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        if header:
            fh.write(header + "\n")
        w = csv.DictWriter(fh, fieldnames=list(columns))
        w.writeheader()
        w.writerows(rows)
    return path


def minutes_rows(tc: T1Config, blocks: int) -> list[dict[str, str]]:
    """The minutes log: one pre-listed line per Karan block, one per second rater (filled in at the time)."""
    rows = [{"rater": tc.primary, "block": str(b), "started_at": "", "ended_at": "", "minutes": "", "note": ""}
            for b in range(1, blocks + 1)]
    rows += [{"rater": r, "block": "subset", "started_at": "", "ended_at": "", "minutes": "", "note": ""}
             for r in tc.second_raters]
    return rows


# ---------------------------------------------------------------------------
# Ingest-side guards (used from Part C; tested now)
# ---------------------------------------------------------------------------


def validate_labelled(rows: Sequence[Mapping[str, str]], tc: T1Config, paragraph_class: Mapping[str, str]) -> list[str]:
    """C1 checks: vocabulary, blanks, not_obligation notes, matched_paragraph_id format and class. Returns problems."""
    problems = []
    items: dict[str, dict[str, Any]] = {}
    for n, r in enumerate(rows, start=2):
        iid = r.get("item_id", "")
        kind = r.get("row_type", "")
        where = f"row {n} ({iid}, {kind}{' ' + r.get('target_class', '') if kind == ROW_CLASS else ''})"
        if kind == ROW_ITEM:
            not_obl = (r.get("not_obligation") or "").strip().lower()
            items[iid] = {"not_obligation": not_obl == NOT_OBLIGATION_YES}
            if not_obl and not_obl != NOT_OBLIGATION_YES:
                problems.append(f"{where}: not_obligation must be 'yes' or blank, got {not_obl!r}")
            names = [p.strip() for p in (r.get("applies_to") or "").split(APPLIES_TO_SEPARATOR) if p.strip()]
            if not_obl == NOT_OBLIGATION_YES:
                if names:
                    problems.append(f"{where}: not_obligation = yes but applies_to is filled")
                if not (r.get("note") or "").strip():
                    problems.append(f"{where}: not_obligation = yes needs the reason in note (v3.3)")
                continue
            if not names:
                problems.append(f"{where}: applies_to is blank")
            bad = [x for x in names if x not in tc.applies_to_vocabulary]
            if bad:
                problems.append(f"{where}: applies_to names not in the v2.2 vocabulary: {bad}")
            if not (r.get("applies_to_rationale") or "").strip():
                problems.append(f"{where}: applies_to_rationale is blank")
        elif kind == ROW_CLASS:
            if items.get(iid, {}).get("not_obligation"):
                continue
            j = (r.get("judgement") or "").strip().lower()
            mid = (r.get("matched_paragraph_id") or "").strip()
            if j not in JUDGEMENTS:
                problems.append(f"{where}: judgement {j!r} is not one of {JUDGEMENTS}" if j
                                else f"{where}: judgement is blank")
                continue
            if j in (JUDGE_SAME, JUDGE_DIFFERENT):
                if not mid:
                    problems.append(f"{where}: matched_paragraph_id is required for {j}")
                elif not PARAGRAPH_ID_RE.match(mid):
                    problems.append(f"{where}: matched_paragraph_id {mid!r} is not md_NNNNN::pNNNNN")
                elif paragraph_class.get(mid) != r.get("target_class"):
                    problems.append(f"{where}: {mid} is not a paragraph of {r.get('target_class')!r} "
                                    f"(it belongs to {paragraph_class.get(mid)!r})")
            elif mid:
                problems.append(f"{where}: matched_paragraph_id must be blank for {j}")
        elif kind == ROW_PILOT:
            continue  # pilot rows follow the pilot's own rules: validate_pilot_rows
        else:
            problems.append(f"{where}: row_type must be item or class")
    return problems


def assert_second_rater_independent(primary: Sequence[Mapping[str, str]], second: Sequence[Mapping[str, str]],
                                    rater: str, *, min_text_chars: int = 15, max_identical_texts: int = 2) -> None:
    """D11: refuse a second-rater file carrying another rater's cells.

    Independent people don't write identical free text: more than
    ``max_identical_texts`` identical non-trivial rationales/notes, or an
    ``applies_to`` identical on every multi-class item (at least 3), is refused.
    """
    key = lambda r: (r.get("item_id"), r.get("row_type"), r.get("target_class", ""))
    a = {key(r): r for r in primary}
    same_text, multi, multi_same = 0, 0, 0
    for r in second:
        p = a.get(key(r))
        if p is None:
            continue
        for col in ("applies_to_rationale", "note"):
            t = (r.get(col) or "").strip()
            if len(t) >= min_text_chars and t == (p.get(col) or "").strip():
                same_text += 1
        if r.get("row_type") == ROW_ITEM:
            sa = {x.strip() for x in (r.get("applies_to") or "").split(";") if x.strip()}
            sp = {x.strip() for x in (p.get("applies_to") or "").split(";") if x.strip()}
            if max(len(sa), len(sp)) > 1:
                multi += 1
                multi_same += sa == sp
    if same_text > max_identical_texts:
        raise T1Error(f"{rater}: {same_text} free-text cells are identical to the primary's file; "
                      "a second-rater file must be formed independently (D11 / v2.5)")
    if multi >= 3 and multi_same == multi:
        raise T1Error(f"{rater}: applies_to is identical to the primary's on all {multi} multi-class items (D11)")


# ---------------------------------------------------------------------------
# Inter-rater (IRR) set: 30 fresh items labelled by Karan, Akash and Meer
# ---------------------------------------------------------------------------

#: config/config.yaml is edited by another session, so the IRR draw's seed lives here and is recorded
#: in the key and the send log. Streams: +0 selection, +1 compared classes, +2 order, +3 target shuffle.
IRR_SEED = 20260927
IRR_ITEMS = 30
IRR_FLOOR = 2
IRR_RATERS = ("karan", "akash", "meer")
IRR_SHEET = "annotation_p2004_irr_{rater}.csv"
#: An unsent copy of the blank sheet: ingest checks returned files against it (a rater may fill theirs in place).
IRR_BLANK_REFERENCE = "p2004_irr_blank_reference.csv"
IRR_SENDLOG_FILE = "p2004_irr_sendlog.json"
IRR_RECEIPTS_FILE = "p2004_irr_receipts.json"
IRR_RECEIVED_DIR = "irr_received"
NOT_INDEPENDENT_DIR = "not_independent"
IRR_MINUTES_BLOCK = "irr"
IRR_HEADER = (SHEET_HEADER + " IRR set: label independently; this file goes to one person only and is ingested once.")
#: Wording the guidelines prescribe (v2.1 / v3.3), which independent raters may legitimately repeat verbatim.
PRESCRIBED_TEXT_RE = re.compile(r"^(?:not an RE obligation\s*[—–-]\s*duty on\s+.{1,60}|definitional, not an obligation)$", re.I)


def draw_irr(records: Sequence[Mapping[str, Any]], tc: T1Config, *, n: int = IRR_ITEMS, floor: int = IRR_FLOOR,
             seed: int = IRR_SEED, excluded_items: set[str], excluded_paragraphs: set[str],
             excluded_candidates: set[str], boilerplate_kind: Any = None) -> dict[str, Any]:
    """30 new items: pool as A5 minus the 123-item sample; >= ``floor`` per class where available; K compared."""
    excl = Counter()
    pool = []
    for r in records:
        if r["item_id"] in excluded_items:
            excl["main_sample"] += 1
        elif len(r["compared_classes"]) < tc.min_compared_classes:
            excl["fewer_than_min_compared"] += 1
        elif r["paragraph_id"] in excluded_paragraphs:
            excl["pilot"] += 1
        elif r["source_candidate_id"] in excluded_candidates:
            excl["p2002_validation_pair"] += 1
        elif boilerplate_kind and boilerplate_kind(r["obligation_span"]["text"]):
            excl["boilerplate"] += 1
        else:
            pool.append(r)
    by_class: dict[str, list] = defaultdict(list)
    for r in sorted(pool, key=lambda r: r["item_id"]):
        by_class[r["entity_class"]].append(r)
    alloc = allocate({c: len(v) for c, v in by_class.items()}, n, floor)
    rng = random.Random(seed)
    chosen = []
    for cls in sorted(by_class):
        groups: dict[tuple, list] = defaultdict(list)
        for r in by_class[cls]:
            groups[(r["subject_family"], r["differential_flag_candidate"])].append(r)
        for g in groups.values():
            rng.shuffle(g)
        chosen.extend(_round_robin(groups, alloc[cls], rng))
    rng_k = random.Random(seed + 1)
    by_cls_items: dict[str, list] = defaultdict(list)
    for r in sorted(chosen, key=lambda r: r["item_id"]):
        comp = sorted(r["compared_classes"])
        by_cls_items[r["entity_class"]].append(
            {**r, "sample_compared_classes": sorted(rng_k.sample(comp, min(tc.max_compared_classes, len(comp))))})
    rng_o = random.Random(seed + 2)
    for cls in sorted(by_cls_items):
        rng_o.shuffle(by_cls_items[cls])
    ordered = interleave(by_cls_items, seed + 2)
    for pos, it in enumerate(ordered):
        it["order"] = pos + 1
        it["block"] = pos // tc.block_size + 1
    return {"items": ordered, "allocation": alloc, "pool_size": len(pool),
            "pool_by_class": {c: len(v) for c, v in sorted(by_class.items())}, "excluded": dict(sorted(excl.items())),
            "seed": seed, "shuffle_seed": seed + 3}


def irr_minutes_rows(existing: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Append one blank IRR session line per rater, keeping every existing row (and anything filled in) as is."""
    have = {(r.get("rater"), r.get("block")) for r in existing}
    rows = [dict(r) for r in existing]
    rows += [{"rater": r, "block": IRR_MINUTES_BLOCK, "started_at": "", "ended_at": "", "minutes": "",
              "note": "IRR set; add one line per sitting"}
             for r in IRR_RATERS if (r, IRR_MINUTES_BLOCK) not in have]
    return rows


def refuse_not_independent(path: Path, t1_dir: Path) -> None:
    """Files kept in ``not_independent/`` or named ``*_mock*`` are never ingested as a rater's work."""
    resolved = path.resolve()
    if (t1_dir / NOT_INDEPENDENT_DIR).resolve() in resolved.parents:
        raise T1Error(f"{path}: files in {NOT_INDEPENDENT_DIR}/ are never ingested")
    if "_mock" in path.name.lower():
        raise T1Error(f"{path}: a *_mock* file is never ingested as a rater's labels")


def item_text_cells(rows: Sequence[Mapping[str, str]]) -> dict[tuple[str, str], str]:
    """(item_id, column) -> non-empty item-level free text, excluding the wording the guidelines prescribe."""
    out = {}
    for r in rows:
        if r.get("row_type") != ROW_ITEM:
            continue
        for col in ("applies_to_rationale", "note"):
            text = " ".join((r.get(col) or "").split())
            if text and not PRESCRIBED_TEXT_RE.match(text):
                out[(r["item_id"], col)] = text
    return out


def refuse_identical_item_text(rows: Sequence[Mapping[str, str]], rater: str,
                               others: Mapping[str, Sequence[Mapping[str, str]]]) -> None:
    """D11-style guard: any item-level text field identical to another rater's refuses the file."""
    mine = item_text_cells(rows)
    for other, other_rows in sorted(others.items()):
        theirs = item_text_cells(other_rows)
        same = sorted(k for k, v in mine.items() if theirs.get(k, "").lower() == v.lower())
        if same:
            raise T1Error(f"{rater}: {len(same)} item-level text field(s) identical to {other}'s file, "
                          f"e.g. {same[0][0]} {same[0][1]}; IRR files must be formed independently (D11 / v2.5)")


def check_irr_shown_columns(rows: Sequence[Mapping[str, str]], drawn: Sequence[Mapping[str, str]]) -> None:
    """The returned file must be the drawn sheet with only input cells filled: same rows, order and shown text."""
    if len(rows) != len(drawn):
        raise T1Error(f"returned file has {len(rows)} rows; the drawn sheet has {len(drawn)}")
    shown = [c for c in SHEET_COLUMNS if c not in INPUT_COLUMNS]
    for n, (r, d) in enumerate(zip(rows, drawn), start=2):
        diff = [c for c in shown if (r.get(c) or "") != (d.get(c) or "")]
        if diff:
            raise T1Error(f"row {n}: shown column(s) {diff} differ from the drawn sheet")


def ingest_irr(path: Path, rater: str, *, t1_dir: Path, drawn: Sequence[Mapping[str, str]], tc: T1Config,
               paragraph_class: Mapping[str, str], receipts: Mapping[str, Any], received_at: str,
               sha256: str, label_source: str = "manual",
               received_rows: Mapping[str, Sequence[Mapping[str, str]]] | None = None) -> dict[str, Any]:
    """Accept one returned IRR file exactly once. Returns the receipt; raises T1Error on any refusal.

    Refusals: an unknown rater; a rater already received (a second version is never taken); a file whose
    sha256 was already received; files in not_independent/ or named *_mock*; shown columns changed;
    blank or invalid cells (v3 validation); any item-level text identical to another rater's received file.
    """
    if rater not in IRR_RATERS:
        raise T1Error(f"unknown IRR rater {rater!r}; expected one of {IRR_RATERS}")
    if label_source not in ("manual", "ai_assisted"):
        raise T1Error(f"label_source must be manual or ai_assisted, got {label_source!r}")
    refuse_not_independent(path, t1_dir)
    if rater in receipts:
        prev = receipts[rater]
        raise T1Error(f"{rater}'s IRR file was already received at {prev['received_at']} "
                      f"(sha256 {prev['sha256'][:12]}…); a second version is refused")
    for other, rec in receipts.items():
        if rec["sha256"] == sha256:
            raise T1Error(f"{path.name} is byte-identical to {other}'s received file")
    rows = read_sheet(path)
    check_irr_shown_columns(rows, drawn)
    problems = validate_labelled(rows, tc, paragraph_class)
    if problems:
        raise T1Error(f"{rater}: {len(problems)} problem(s), first: " + "; ".join(problems[:5]))
    others = dict(received_rows) if received_rows is not None else {
        o: read_sheet(t1_dir / IRR_RECEIVED_DIR / rec["stored_as"]) for o, rec in receipts.items()}
    refuse_identical_item_text(rows, rater, others)
    return {"rater": rater, "source_path": path.as_posix(), "stored_as": IRR_SHEET.format(rater=rater),
            "sha256": sha256, "received_at": received_at, "label_source": label_source, "rows": len(rows),
            "items": len({r["item_id"] for r in rows})}


# ---------------------------------------------------------------------------
# IRR scoring (κ, Fleiss, bootstrap: the P1-005 implementations, resampled by item)
# ---------------------------------------------------------------------------

FLAG_CATEGORIES_V3 = (FLAG_SHARED, FLAG_CLASS_SPECIFIC, FLAG_ABSENT, FLAG_AMBIGUOUS)
NOT_OBL_CATEGORIES = ("yes", "no")


def parse_labelled_items(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, Any]]:
    """item_id -> one rater's labels: not_obligation, applies_to set, rationale, per-class judgements and ids, flag."""
    items: dict[str, dict[str, Any]] = {}
    for r in rows:
        iid = r["item_id"]
        if r["row_type"] == ROW_ITEM:
            items[iid] = {
                "source_class": r["source_class"],
                "not_obligation": (r.get("not_obligation") or "").strip().lower() == NOT_OBLIGATION_YES,
                "applies_to": tuple(sorted({x.strip() for x in (r.get("applies_to") or "").split(APPLIES_TO_SEPARATOR)
                                            if x.strip()})),
                "rationale": (r.get("applies_to_rationale") or "").strip(),
                "note": (r.get("note") or "").strip(),
                "judgements": {}, "matched": {},
            }
        else:
            j = (r.get("judgement") or "").strip().lower()
            if j:
                items[iid]["judgements"][r["target_class"]] = j
                items[iid]["matched"][r["target_class"]] = (r.get("matched_paragraph_id") or "").strip()
    for it in items.values():
        if it["not_obligation"] or not it["judgements"]:
            it["flag"] = None
            it["needs_adjudication"] = False
        else:
            d = derive_flag(it["judgements"])
            it["flag"] = d["flag"] or FLAG_AMBIGUOUS
            it["needs_adjudication"] = d["needs_adjudication"]
    return items


def _cluster_bootstrap(clusters: Sequence[Sequence[Any]], stat: Any, *, seed: int, resamples: int) -> dict[str, Any]:
    """Percentile bootstrap resampling whole items (clusters); undefined resamples are skipped and counted."""
    from src.benchmark.annotation import NOT_YET_MEASURED, _percentile

    n = len(clusters)
    if n < 2:
        return {"ci95": NOT_YET_MEASURED, "reason": f"needs at least 2 items, got {n}", "resamples_used": 0}
    rng = random.Random(seed)
    values, skipped = [], 0
    for _ in range(resamples):
        units = [u for _ in range(n) for u in clusters[rng.randrange(n)]]
        v = stat(units)
        if isinstance(v, str) or v is None:
            skipped += 1
        else:
            values.append(v)
    if not values:
        return {"ci95": NOT_YET_MEASURED, "reason": "every resample was undefined", "resamples_used": 0,
                "resamples_skipped_undefined": skipped}
    values.sort()
    return {"ci95": [_percentile(values, 0.025), _percentile(values, 0.975)], "seed": seed,
            "resamples_requested": resamples, "resamples_used": len(values), "resamples_skipped_undefined": skipped}


def _cohen_block(clusters: Sequence[Sequence[tuple[str, str]]], categories: Sequence[str], *, seed: int,
                 resamples: int) -> dict[str, Any]:
    from src.benchmark.annotation import cohen_kappa

    units = [u for c in clusters for u in c]
    return {"n_items": len(clusters), "n_units": len(units),
            "observed_agreement": (sum(a == b for a, b in units) / len(units)) if units else None,
            "kappa": cohen_kappa(units, categories),
            "bootstrap": _cluster_bootstrap(clusters, lambda us: cohen_kappa(us, categories), seed=seed,
                                            resamples=resamples)}


def _fleiss_block(clusters: Sequence[Sequence[tuple[str, ...]]], categories: Sequence[str], *, seed: int,
                  resamples: int) -> dict[str, Any]:
    from src.benchmark.annotation import fleiss_kappa

    def stat(units):
        return fleiss_kappa([[sum(1 for x in u if x == c) for c in categories] for u in units])

    units = [u for c in clusters for u in c]
    return {"n_items": len(clusters), "n_units": len(units),
            "all_agree": (sum(len(set(u)) == 1 for u in units) / len(units)) if units else None,
            "kappa": stat(units) if units else None,
            "bootstrap": _cluster_bootstrap(clusters, stat, seed=seed, resamples=resamples)}


def _jaccard_sets(a: Sequence[str], b: Sequence[str]) -> float:
    sa, sb = set(a), set(b)
    return 1.0 if not sa and not sb else len(sa & sb) / len(sa | sb)


def _set_block(pairs: Sequence[tuple[tuple, tuple]], *, seed: int, resamples: int) -> dict[str, Any]:
    exact = lambda ps: sum(a == b for a, b in ps) / len(ps) if ps else None
    jac = lambda ps: sum(_jaccard_sets(a, b) for a, b in ps) / len(ps) if ps else None
    clusters = [[p] for p in pairs]
    return {"n_items": len(pairs),
            "exact_set_agreement": exact(pairs),
            "exact_set_bootstrap": _cluster_bootstrap(clusters, exact, seed=seed, resamples=resamples),
            "mean_jaccard": jac(pairs),
            "mean_jaccard_bootstrap": _cluster_bootstrap(clusters, jac, seed=seed, resamples=resamples)}


def irr_metrics(labels: Mapping[str, Mapping[str, Mapping[str, Any]]], *, seed: int, resamples: int) -> dict[str, Any]:
    """Pairwise Cohen's and Fleiss' (complete items only) on flag, per-class judgements, applies_to and not_obligation."""
    raters = sorted(labels)
    item_ids = sorted(set.intersection(*(set(v) for v in labels.values())))
    out: dict[str, Any] = {"raters": raters, "items": len(item_ids), "seed": seed, "resamples": resamples,
                           "pairwise": {}, "fleiss": {}}
    for i, a in enumerate(raters):
        for b in raters[i + 1:]:
            A, B = labels[a], labels[b]
            both_obl = [x for x in item_ids if not A[x]["not_obligation"] and not B[x]["not_obligation"]]
            per_class = [[(A[x]["judgements"][c], B[x]["judgements"][c])
                          for c in sorted(set(A[x]["judgements"]) & set(B[x]["judgements"]))] for x in both_obl]
            out["pairwise"][f"{a}-{b}"] = {
                "not_obligation": _cohen_block(
                    [[("yes" if A[x]["not_obligation"] else "no", "yes" if B[x]["not_obligation"] else "no")]
                     for x in item_ids], NOT_OBL_CATEGORIES, seed=seed, resamples=resamples),
                "differential_flag": _cohen_block([[(A[x]["flag"], B[x]["flag"])] for x in both_obl],
                                                  FLAG_CATEGORIES_V3, seed=seed, resamples=resamples),
                "per_class_judgement": _cohen_block([c for c in per_class if c], JUDGEMENTS, seed=seed,
                                                    resamples=resamples),
                "applies_to": _set_block([(A[x]["applies_to"], B[x]["applies_to"]) for x in both_obl],
                                         seed=seed, resamples=resamples),
            }
    L = [labels[r] for r in raters]
    all_obl = [x for x in item_ids if not any(l[x]["not_obligation"] for l in L)]
    common = lambda x: sorted(set.intersection(*(set(l[x]["judgements"]) for l in L)))
    out["fleiss"] = {
        "not_obligation": _fleiss_block([[tuple("yes" if l[x]["not_obligation"] else "no" for l in L)]
                                         for x in item_ids], NOT_OBL_CATEGORIES, seed=seed, resamples=resamples),
        "differential_flag": _fleiss_block([[tuple(l[x]["flag"] for l in L)] for x in all_obl], FLAG_CATEGORIES_V3,
                                           seed=seed, resamples=resamples),
        "per_class_judgement": _fleiss_block([c for c in ([tuple(l[x]["judgements"][k] for l in L) for k in common(x)]
                                                          for x in all_obl) if c], JUDGEMENTS,
                                             seed=seed, resamples=resamples),
        "applies_to_all_three_identical": {
            "n_items": len(all_obl),
            "rate": (sum(len({l[x]["applies_to"] for l in L}) == 1 for x in all_obl) / len(all_obl)) if all_obl else None,
            # Agreement on "the source class only" is the case the guidelines warn about (v1: don't just copy
            # context_entity_class); it says little about multi-class applicability.
            "all_three_source_class_only": sum(all(l[x]["applies_to"] == (l[x]["source_class"],) for l in L)
                                               for x in all_obl),
            "any_rater_multi_class": sum(any(len(l[x]["applies_to"]) > 1 for l in L) for x in all_obl),
        },
        "complete_items_note": "Fleiss' κ only over items every rater labelled as an obligation (complete items).",
    }
    return out


def irr_disagreements(labels: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Every item where raters differ on not_obligation, flag, applies_to or any per-class judgement, or with unsure."""
    raters = sorted(labels)
    out = []
    for x in sorted(set.intersection(*(set(v) for v in labels.values()))):
        L = {r: labels[r][x] for r in raters}
        why = []
        if len({v["not_obligation"] for v in L.values()}) > 1:
            why.append("not_obligation")
        if len({v["flag"] for v in L.values()}) > 1:
            why.append("differential_flag")
        if len({v["applies_to"] for v in L.values()}) > 1:
            why.append("applies_to")
        classes = sorted(set().union(*(v["judgements"] for v in L.values())))
        diff_cls = [c for c in classes if len({v["judgements"].get(c) for v in L.values()}) > 1]
        if diff_cls:
            why.append("judgement:" + "|".join(diff_cls))
        if any(JUDGE_UNSURE in v["judgements"].values() or v["flag"] == FLAG_AMBIGUOUS for v in L.values()):
            why.append("unsure_or_ambiguous")
        if why:
            out.append({"item_id": x, "source_class": next(iter(L.values()))["source_class"], "differs_on": why,
                        "by_rater": {r: {"not_obligation": v["not_obligation"], "applies_to": list(v["applies_to"]),
                                         "flag": v["flag"], "judgements": v["judgements"]} for r, v in L.items()}})
    return out


def independence_diagnostics(rows_by_rater: Mapping[str, Sequence[Mapping[str, str]]]) -> dict[str, Any]:
    """Descriptive only: near-identical item-level text between raters (difflib ratio >= 0.9)."""
    import difflib

    texts = {r: item_text_cells(rows) for r, rows in rows_by_rater.items()}
    raters = sorted(texts)
    out = {}
    for i, a in enumerate(raters):
        for b in raters[i + 1:]:
            keys = sorted(set(texts[a]) & set(texts[b]))
            near = [k for k in keys if difflib.SequenceMatcher(None, texts[a][k].lower(), texts[b][k].lower()).ratio() >= 0.9]
            out[f"{a}-{b}"] = {"text_cells_compared": len(keys), "near_identical_ge_0_9": len(near),
                               "examples": [f"{k[0]} {k[1]}" for k in near[:3]]}
    return out


# ---------------------------------------------------------------------------
# Part C: pass-1 ingest, per-class tables, qrels, IRR adjudication rows
# ---------------------------------------------------------------------------

PASS1_RECEIPTS_FILE = "p2004_pass1_receipts.json"
PASS1_RECEIVED_DIR = "pass1_received"
PASS1_TABLES_FILE = "p2004_pass1_tables_v1.json"
QRELS_FILE = "t1_pairs_qrels_v1.jsonl"
IRR_ADJUDICATION_COLUMNS = (
    "item_id", "comparison", "target_class", "source_paragraph_id", "source_context", "differs_on",
    "karan_decision", "akash_decision", "meer_decision",
    "karan_matched_paragraph_id", "akash_matched_paragraph_id", "meer_matched_paragraph_id",
    "karan_item_decision", "akash_item_decision", "meer_item_decision",
    "final_decision", "final_rationale")
QRELS_GRADE = {JUDGE_SAME: 2, JUDGE_DIFFERENT: 1, JUDGE_NONE: 0}


def structure_problems(rows: Sequence[Mapping[str, str]], drawn: Sequence[Mapping[str, str]]) -> list[str]:
    """Schema, item identity and order against the drawn sheet, and (item, row, class) uniqueness."""
    problems = []
    if rows and tuple(rows[0]) != SHEET_COLUMNS:
        problems.append(f"columns {tuple(rows[0])} != {SHEET_COLUMNS}")
        return problems
    if len(rows) != len(drawn):
        problems.append(f"{len(rows)} rows; the drawn sheet has {len(drawn)}")
    shown = [c for c in SHEET_COLUMNS if c not in INPUT_COLUMNS]
    for n, (r, d) in enumerate(zip(rows, drawn), start=2):
        diff = [c for c in shown if (r.get(c) or "") != (d.get(c) or "")]
        if diff:
            problems.append(f"row {n} ({r.get('item_id')}): shown column(s) {diff} differ from the drawn sheet")
    seen: dict[tuple, int] = {}
    item_rows = Counter()
    for n, r in enumerate(rows, start=2):
        k = (r.get("item_id"), r.get("row_type"), r.get("target_class", ""))
        if k in seen:
            problems.append(f"row {n}: duplicate {k} (first at row {seen[k]})")
        seen.setdefault(k, n)
        if r.get("row_type") == ROW_ITEM:
            item_rows[r.get("item_id")] += 1
    problems += [f"{i}: {c} item rows (expected 1)" for i, c in sorted(item_rows.items()) if c != 1]
    return problems


def validate_annotation_file(path: Path, drawn: Sequence[Mapping[str, str]], tc: T1Config,
                             paragraph_class: Mapping[str, str]) -> dict[str, Any]:
    """Everything checked before an ingest; ``problems`` empty means the file may be ingested. Never modifies it."""
    raw = path.read_bytes()
    rows = read_sheet(path)
    problems = structure_problems(rows, drawn)
    if not problems:
        problems += validate_labelled(rows, tc, paragraph_class)
    return {"file": path.as_posix(), "has_bom": raw[:3] == b"\xef\xbb\xbf", "rows": len(rows),
            "items": len({r["item_id"] for r in rows}), "problems": problems}


def pass1_tables(labels: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Per source class: items, rejections, flags; per (source, target) class: judgement counts."""
    by_src: dict[str, Counter] = defaultdict(Counter)
    pair: dict[tuple, Counter] = defaultdict(Counter)
    overall = Counter()
    flags = Counter()
    for it in labels.values():
        s = it["source_class"]
        by_src[s]["items"] += 1
        if it["not_obligation"]:
            by_src[s]["not_obligation"] += 1
            continue
        by_src[s][f"flag:{it['flag']}"] += 1
        flags[it["flag"]] += 1
        for cls, j in it["judgements"].items():
            pair[(s, cls)][j] += 1
            overall[j] += 1
    return {
        "items": len(labels),
        "not_obligation": sum(it["not_obligation"] for it in labels.values()),
        "flag_distribution": {f: flags.get(f, 0) for f in FLAG_CATEGORIES_V3},
        "judgement_distribution": {j: overall.get(j, 0) for j in JUDGEMENTS},
        "by_source_class": {s: dict(sorted(c.items())) for s, c in sorted(by_src.items())},
        "by_class_pair": [{"source_class": s, "target_class": t, **{j: c.get(j, 0) for j in JUDGEMENTS},
                           "n": sum(c.values())} for (s, t), c in sorted(pair.items())],
    }


_CHECKED_RE = re.compile(r"md_\d+::p\d{5}")


def pass1_qrels(rows: Sequence[Mapping[str, str]], key_items: Mapping[str, Mapping[str, Any]],
                sample: Mapping[str, Mapping[str, Any]], *, rater: str, label_source: str) -> list[dict[str, Any]]:
    """One qrel per judged (item, target class, paragraph): same = 2, different = 1 (matched_paragraph_id),
    none = 0 for every paragraph checked (the shown ids plus ids cited in the note). unsure and rejected items give none."""
    labels = parse_labelled_items(rows)
    notes = {(r["item_id"], r["target_class"]): r.get("note") or "" for r in rows if r["row_type"] == ROW_CLASS}
    out = []
    for iid in sorted(labels):
        it = labels[iid]
        if it["not_obligation"]:
            continue
        s = sample[iid]
        for cls, j in sorted(it["judgements"].items()):
            if j == JUDGE_UNSURE:
                continue
            base = {"item_id": iid, "source_candidate_id": s["source_candidate_id"],
                    "source_paragraph_id": s["paragraph_id"], "source_class": it["source_class"],
                    "subject_family": s["subject_family"], "target_class": cls, "judgement": j,
                    "rater": rater, "pass": 1, "label_source": label_source,
                    "provenance": f"annotator:{rater}:single-pass"}
            if j in (JUDGE_SAME, JUDGE_DIFFERENT):
                out.append({**base, "paragraph_id": it["matched"][cls], "relevance": QRELS_GRADE[j],
                            "basis": "matched_paragraph_id"})
            else:
                checked = list(key_items[iid]["shown_targets"][cls])
                checked += [p for p in _CHECKED_RE.findall(notes.get((iid, cls), "")) if p not in checked]
                out += [{**base, "paragraph_id": p, "relevance": 0,
                         "basis": "shown" if p in key_items[iid]["shown_targets"][cls] else "note_checked"}
                        for p in checked]
    return out


def irr_adjudication_rows(rows_by_rater: Mapping[str, Sequence[Mapping[str, str]]]) -> list[dict[str, str]]:
    """Every IRR comparison needing adjudication: item rows (not_obligation / applies_to) and class rows
    (judgement differs, or any rater said unsure). Decision columns are blank."""
    raters = ("karan", "akash", "meer")
    labels = {r: parse_labelled_items(rows_by_rater[r]) for r in raters}
    first = rows_by_rater["karan"]
    context = {r["item_id"]: (r["source_paragraph_id"], _cap(r["source_span"], 600))
               for r in first if r["row_type"] == ROW_ITEM}
    item_dec = lambda it: "not_obligation" if it["not_obligation"] else "applies_to: " + "; ".join(it["applies_to"])
    out = []
    for r in first:
        iid = r["item_id"]
        L = {x: labels[x][iid] for x in raters}
        base = {c: "" for c in IRR_ADJUDICATION_COLUMNS}
        base.update(item_id=iid, source_paragraph_id=context[iid][0], source_context=context[iid][1],
                    **{f"{x}_item_decision": item_dec(L[x]) for x in raters})
        if r["row_type"] == ROW_ITEM:
            why = [w for w, vals in (("not_obligation", {v["not_obligation"] for v in L.values()}),
                                     ("applies_to", {v["applies_to"] for v in L.values() if not v["not_obligation"]}))
                   if len(vals) > 1]
            if why:
                out.append({**base, "comparison": "item", "differs_on": "; ".join(why),
                            **{f"{x}_decision": item_dec(L[x]) for x in raters}})
        else:
            cls = r["target_class"]
            dec = {x: ("(not an obligation)" if L[x]["not_obligation"] else L[x]["judgements"].get(cls, ""))
                   for x in raters}
            why = []
            if len(set(dec.values())) > 1:
                why.append("judgement")
            if JUDGE_UNSURE in dec.values():
                why.append("unsure")
            if why:
                out.append({**base, "comparison": "class", "target_class": cls, "differs_on": "; ".join(why),
                            **{f"{x}_decision": dec[x] for x in raters},
                            **{f"{x}_matched_paragraph_id": L[x]["matched"].get(cls, "") for x in raters}})
    return out


# ---------------------------------------------------------------------------
# IRR adjudication: validate the item-level completion, migrate it to the per-comparison rows
# ---------------------------------------------------------------------------

#: The schema the adjudication was completed under (18 rows, one per item), later superseded by
#: IRR_ADJUDICATION_COLUMNS (one row per disagreeing comparison).
LEGACY_ADJ_COLUMNS = ("item_id", "source_class", "differs_on", "akash", "karan", "meer",
                      "final_applies_to", "final_judgements", "final_not_obligation", "rationale")
LEGACY_ADJ_FIXED = LEGACY_ADJ_COLUMNS[:6]
LEGACY_ADJ_INPUT = LEGACY_ADJ_COLUMNS[6:]
ADJ_COMPLETED_FILE = "p2004_irr_adjudication_v1_completed.csv"
ADJ_LEGACY_TEMPLATE_FILE = "p2004_irr_adjudication_v1_item_level_template.csv"
ADJ_MAPPED_FILE = "p2004_irr_adjudication_v1_mapped.csv"
ADJ_RECEIPT_FILE = "p2004_irr_adjudication_receipt_v1.json"
IRR_CONSENSUS_FILE = "p2004_irr_consensus_v1.jsonl"
FINAL_NOT_OBLIGATION = "(not an obligation)"


def validate_legacy_adjudication(completed: Sequence[Mapping[str, str]], template: Sequence[Mapping[str, str]],
                                 compared: Mapping[str, Sequence[str]], tc: T1Config
                                 ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Check the item-level completion against the sheet it was issued as; return (decisions, problems)."""
    import json as _json

    problems: list[str] = []
    if not completed or tuple(completed[0]) != LEGACY_ADJ_COLUMNS:
        return {}, [f"columns {tuple(completed[0]) if completed else ()} != {LEGACY_ADJ_COLUMNS}"]
    if tuple(template[0]) != LEGACY_ADJ_COLUMNS:
        return {}, [f"template columns {tuple(template[0])} != {LEGACY_ADJ_COLUMNS}"]
    if len(completed) != len(template):
        problems.append(f"{len(completed)} rows; the issued sheet has {len(template)}")
    for n, t in enumerate(template, start=3):
        filled = [c for c in LEGACY_ADJ_INPUT if (t[c] or "").strip()]
        if filled:
            problems.append(f"template row {n} ({t['item_id']}): issued with {filled} already filled")
    decisions: dict[str, dict[str, Any]] = {}
    for n, (r, t) in enumerate(zip(completed, template), start=3):
        iid = r["item_id"]
        for c in LEGACY_ADJ_FIXED:
            if r[c] != t[c]:
                problems.append(f"row {n} ({iid}) {c}: expected {t[c][:80]!r}, observed {r[c][:80]!r}")
        no = (r["final_not_obligation"] or "").strip()
        if no not in ("true", "false"):
            problems.append(f"row {n} ({iid}) final_not_obligation: expected 'true' or 'false', observed {no!r}")
            continue
        if not (r["rationale"] or "").strip():
            problems.append(f"row {n} ({iid}) rationale: blank")
        try:
            applies = _json.loads(r["final_applies_to"])
            judg = _json.loads(r["final_judgements"])
        except ValueError as exc:
            problems.append(f"row {n} ({iid}): final_applies_to / final_judgements is not valid JSON ({exc})")
            continue
        if not isinstance(applies, list) or not all(isinstance(x, str) for x in applies):
            problems.append(f"row {n} ({iid}) final_applies_to: expected a JSON list of class names")
            continue
        if not isinstance(judg, dict):
            problems.append(f"row {n} ({iid}) final_judgements: expected a JSON object")
            continue
        if no == "true":
            if applies or judg:
                problems.append(f"row {n} ({iid}): final_not_obligation is true but applies_to/judgements are filled")
        else:
            bad = [x for x in applies if x not in tc.applies_to_vocabulary]
            if not applies or bad:
                problems.append(f"row {n} ({iid}) final_applies_to: "
                                + (f"names not in the v2.2 vocabulary: {bad}" if bad else "empty for an obligation"))
            want = sorted(compared.get(iid, ()))
            if sorted(judg) != want:
                problems.append(f"row {n} ({iid}) final_judgements: expected classes {want}, observed {sorted(judg)}")
            badj = {k: v for k, v in judg.items() if v not in JUDGEMENTS}
            if badj:
                problems.append(f"row {n} ({iid}) final_judgements: values not in {JUDGEMENTS}: {badj}")
        decisions[iid] = {"not_obligation": no == "true", "applies_to": sorted(applies),
                          "judgements": dict(sorted(judg.items())), "rationale": (r["rationale"] or "").strip()}
    return decisions, problems


def map_adjudication(current: Sequence[Mapping[str, str]], decisions: Mapping[str, Mapping[str, Any]]
                     ) -> tuple[list[dict[str, str]], list[str]]:
    """Fill final_decision / final_rationale of each current row from the item's completed decision. No new calls."""
    problems: list[str] = []
    out = []
    items = {r["item_id"] for r in current}
    if items != set(decisions):
        problems.append(f"items differ: only in current sheet {sorted(items - set(decisions))}, "
                        f"only in the adjudication {sorted(set(decisions) - items)}")
    for n, r in enumerate(current, start=3):
        filled = [c for c in ("final_decision", "final_rationale") if (r.get(c) or "").strip()]
        if filled:
            problems.append(f"current row {n}: {filled} already filled")
        d = decisions.get(r["item_id"])
        if d is None:
            problems.append(f"current row {n} ({r['item_id']}): no adjudicated decision")
            continue
        if r["comparison"] == "item":
            final = "not_obligation" if d["not_obligation"] else "applies_to: " + "; ".join(d["applies_to"])
        elif r["comparison"] == "class":
            if d["not_obligation"]:
                final = FINAL_NOT_OBLIGATION
            elif r["target_class"] in d["judgements"]:
                final = d["judgements"][r["target_class"]]
            else:
                problems.append(f"current row {n} ({r['item_id']}, {r['target_class']}): the adjudication has no "
                                "judgement for this class")
                continue
        else:
            problems.append(f"current row {n}: unknown comparison {r['comparison']!r}")
            continue
        out.append({**r, "final_decision": final, "final_rationale": d["rationale"]})
    return out, problems


def irr_consensus(labels: Mapping[str, Mapping[str, Mapping[str, Any]]],
                  decisions: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The IRR consensus layer: adjudicated decisions where raters disagreed, the unanimous labels elsewhere.
    Reliability evidence only; never used as main-benchmark labels."""
    disputed = {x["item_id"] for x in irr_disagreements(labels)}
    raters = sorted(labels)
    out = []
    for iid in sorted(set.intersection(*(set(v) for v in labels.values()))):
        if iid in decisions:
            d = decisions[iid]
            rec = {"not_obligation": d["not_obligation"], "applies_to": d["applies_to"],
                   "judgements": d["judgements"], "route": "adjudicated", "rationale": d["rationale"]}
        else:
            if iid in disputed:
                raise T1Error(f"{iid} is disputed but has no adjudicated decision")
            v = labels[raters[0]][iid]
            rec = {"not_obligation": v["not_obligation"], "applies_to": list(v["applies_to"]),
                   "judgements": dict(sorted(v["judgements"].items())) if not v["not_obligation"] else {},
                   "route": "unanimous", "rationale": None}
        flag = None if rec["not_obligation"] else (derive_flag(rec["judgements"])["flag"] or FLAG_AMBIGUOUS)
        out.append({"item_id": iid, "source_class": labels[raters[0]][iid]["source_class"], **rec,
                    "differential_flag": flag, "layer": "irr_consensus",
                    "note": "IRR reliability evidence; not a main-benchmark label"})
    return out


def not_obligation_rule_evidence(decisions: Mapping[str, Mapping[str, Any]],
                                 labels: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, Any]:
    """The adjudicated not_obligation calls, split into rejections and rejection votes that were overturned."""
    rejected, kept = [], []
    for iid, d in sorted(decisions.items()):
        votes = {r: labels[r][iid]["not_obligation"] for r in sorted(labels)}
        if len(set(votes.values())) < 2:
            continue
        (rejected if d["not_obligation"] else kept).append({"item_id": iid, "rejection_votes": votes,
                                                             "rationale": d["rationale"]})
    return {"disputed": len(rejected) + len(kept), "rejected": rejected, "kept_as_obligation": kept}


# ---------------------------------------------------------------------------
# C2: the blind pass-2 (retest) sheet. No date lock: readiness is workflow state only.
# ---------------------------------------------------------------------------

PASS2_SHEET = "annotation_p2004_karan_pass2.csv"
PASS2_LOG_FILE = "p2004_pass2_log_v1.json"
PASS1_FREEZE_FILE = "p2004_pass1_freeze_v1.json"
#: Seed for the pass-2 item order (config is shared with another session, so it lives here and is logged).
PASS2_SHUFFLE_SEED = 20261003
ROW_PILOT = "pilot_item"
#: Pass 2 = the retest subset (v3 layout) + the 18 pilot items (the pilot's own item-level layout, so they
#: stay comparable with pilot pass 1). ``differential_flag`` is filled on pilot rows only.
PASS2_COLUMNS = ("item_id", "block", "row_type", "source_class", "subject_family", "source_paragraph_id",
                 "source_span", "target_class", "target_candidates", "applies_to", "applies_to_rationale",
                 "not_obligation", "differential_flag", "judgement", "matched_paragraph_id", "note")
PASS2_INPUT_COLUMNS = INPUT_COLUMNS + ("differential_flag",)
RETEST_METHOD_STATEMENT = (
    "Blind test-retest procedure: the retest subset was fixed in advance, independently of pass-1 answers, and "
    "pass 2 was done on a shuffled blank sheet without access to pass 1. No washout period was enforced between "
    "the passes; a short interval may inflate agreement through recall of pass-1 answers.")
PASS2_HEADER = (
    "# Pass 2 (retest), blind (guidelines v3.1, v3.10). Don't open pass 1, your notes, IRR or adjudication files, "
    "or any earlier answer. row_type item / class = the v3 layout: item rows applies_to, applies_to_rationale, "
    "not_obligation, note; class rows judgement (same | different | none | unsure) and matched_paragraph_id for "
    "same/different. row_type pilot_item = the pilot layout (v1/v2): applies_to, applies_to_rationale, "
    "differential_flag (shared | class-specific | absent), note; for a non-obligation leave applies_to and "
    "differential_flag blank and give the reason in note. Leave differential_flag blank on item/class rows.")


def build_retest_rows(drawn: Sequence[Mapping[str, str]], retest_ids: Sequence[str], *, seed: int,
                      block_size: int) -> list[dict[str, str]]:
    """The retest items' rows from the blank drawn pass-1 sheet, items in a new seeded order, blocks renumbered."""
    wanted = set(retest_ids)
    by_item: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in drawn:
        if r["item_id"] in wanted:
            by_item[r["item_id"]].append(dict(r))
    missing = sorted(wanted - set(by_item))
    if missing:
        raise T1Error(f"retest items not on the drawn pass-1 sheet: {missing[:5]}")
    order = sorted(by_item)
    random.Random(seed).shuffle(order)
    rows = []
    for pos, iid in enumerate(order):
        for r in by_item[iid]:
            rows.append({**r, "block": str(pos // block_size + 1), **{c: "" for c in INPUT_COLUMNS}})
    return rows


def pilot_pass2_rows(pilot_rows: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Pilot task rows (item-level P1 layout, blank) as ``pilot_item`` rows of the pass-2 sheet."""
    out = []
    for p in pilot_rows:
        filled = [c for c in ("applies_to", "applies_to_rationale", "differential_flag", "notes") if (p.get(c) or "").strip()]
        if filled:
            raise T1Error(f"pilot row {p.get('label_id')} carries answers {filled}")
        out.append({**{c: "" for c in PASS2_COLUMNS}, "item_id": p["label_id"], "row_type": ROW_PILOT,
                    "source_class": p["context_entity_class"], "subject_family": p["context_subject_family"],
                    "source_paragraph_id": p["paragraph_id"], "source_span": f"OBLIGATION: {p['span_text']}"})
    return out


def build_pass2_rows(retest_rows: Sequence[Mapping[str, str]], pilot_rows: Sequence[Mapping[str, str]], *,
                     seed: int, block_size: int) -> list[dict[str, str]]:
    """Retest items (with their class rows) and pilot items shuffled together as whole items; blocks renumbered."""
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in retest_rows:
        groups[r["item_id"]].append({c: r.get(c, "") for c in PASS2_COLUMNS})
    for r in pilot_rows:
        if r["item_id"] in groups:
            raise T1Error(f"{r['item_id']} is both a retest and a pilot item")
        groups[r["item_id"]].append(dict(r))
    order = sorted(groups)
    random.Random(seed).shuffle(order)
    rows = []
    for pos, iid in enumerate(order):
        for r in groups[iid]:
            rows.append({**r, "block": str(pos // block_size + 1), **{c: "" for c in PASS2_INPUT_COLUMNS}})
    return rows


def assert_pass2_blind(rows: Sequence[Mapping[str, str]]) -> None:
    """Like assert_blind, for the pass-2 layout (its extra input column is differential_flag)."""
    if not rows:
        raise T1Error("empty sheet")
    for r in rows:
        if tuple(r) != PASS2_COLUMNS:
            raise T1Error(f"sheet columns {tuple(r)} != {PASS2_COLUMNS}")
        filled = [c for c in PASS2_INPUT_COLUMNS if (r[c] or "").strip()]
        if filled:
            raise T1Error(f"{r['item_id']}: input cells {filled} must be blank on a drawn sheet")
        if r["row_type"] not in (ROW_ITEM, ROW_CLASS, ROW_PILOT):
            raise T1Error(f"{r['item_id']}: unknown row_type {r['row_type']!r}")
    for col in PASS2_COLUMNS:
        if col not in PASS2_INPUT_COLUMNS and any(w in col for w in FORBIDDEN_COLUMN_WORDS):
            raise T1Error(f"sheet column {col!r} would reveal a hidden field")


# -- pass-2 ingest and test-retest ------------------------------------------------

PASS2_RECEIPTS_FILE = "p2004_pass2_receipts.json"
PASS2_RECEIVED_DIR = "pass2_received"
RETEST_ADJUDICATION_FILE = "p2004_retest_adjudication_v1.csv"
PILOT_FLAG_CATEGORIES = ("shared", "class-specific", "absent", "unlabelled")
RETEST_ADJ_COLUMNS = ("item_id", "kind", "comparison", "target_class", "source_paragraph_id", "source_context",
                      "differs_on", "pass1_decision", "pass2_decision", "pass1_matched_paragraph_id",
                      "pass2_matched_paragraph_id", "final_decision", "final_rationale")


def validate_pilot_rows(rows: Sequence[Mapping[str, str]], pilot_classes: Sequence[str]) -> list[str]:
    """Pilot rows on the pass-2 sheet, pilot rules (v1/v2): classes + flag, or a non-obligation note; v3 cells blank."""
    problems = []
    ok_classes = set(pilot_classes)
    for n, r in enumerate(rows, start=2):
        if r.get("row_type") != ROW_PILOT:
            if (r.get("differential_flag") or "").strip():
                problems.append(f"row {n} ({r.get('item_id')}, {r.get('row_type')}): differential_flag must be blank "
                                "on item/class rows (the v3 flag is derived)")
            continue
        where = f"row {n} ({r['item_id']}, pilot_item)"
        stray = [c for c in ("not_obligation", "judgement", "matched_paragraph_id") if (r.get(c) or "").strip()]
        if stray:
            problems.append(f"{where}: {stray} must be blank on pilot rows")
        names = [x.strip() for x in (r.get("applies_to") or "").split(APPLIES_TO_SEPARATOR) if x.strip()]
        flag = (r.get("differential_flag") or "").strip()
        note = (r.get("note") or "").strip()
        if not names and not flag:
            if not note:
                problems.append(f"{where}: blank row with no note (a non-obligation needs its reason in note)")
            continue
        if flag and not names:
            problems.append(f"{where}: differential_flag without applies_to")
        bad = [x for x in names if x not in ok_classes]
        if bad:
            problems.append(f"{where}: applies_to names not allowed under v2.2 (function headings are never "
                            f"applies_to answers): {bad}")
        if flag and flag not in PILOT_FLAG_CATEGORIES[:3]:
            problems.append(f"{where}: differential_flag {flag!r} is not one of {PILOT_FLAG_CATEGORIES[:3]}")
    return problems


def validate_pass2_file(path: Path, drawn: Sequence[Mapping[str, str]], tc: T1Config,
                        paragraph_class: Mapping[str, str], pilot_classes: Sequence[str]) -> dict[str, Any]:
    """Every pass-2 check, per row type. ``problems`` empty means the file may be ingested. Never modifies it."""
    raw = path.read_bytes()
    rows = read_sheet(path)
    problems: list[str] = []
    if rows and tuple(rows[0]) != PASS2_COLUMNS:
        problems.append(f"columns {tuple(rows[0])} != {PASS2_COLUMNS}")
    else:
        if len(rows) != len(drawn):
            problems.append(f"{len(rows)} rows; the drawn sheet has {len(drawn)}")
        shown = [c for c in PASS2_COLUMNS if c not in PASS2_INPUT_COLUMNS]
        for n, (r, d) in enumerate(zip(rows, drawn), start=2):
            diff = [c for c in shown if (r.get(c) or "") != (d.get(c) or "")]
            if diff:
                problems.append(f"row {n} ({r.get('item_id')}): shown column(s) {diff} differ from the drawn sheet")
        seen: dict[tuple, int] = {}
        for n, r in enumerate(rows, start=2):
            k = (r.get("item_id"), r.get("row_type"), r.get("target_class", ""))
            if k in seen:
                problems.append(f"row {n}: duplicate {k} (first at row {seen[k]})")
            seen.setdefault(k, n)
        if not problems:
            problems += validate_labelled(rows, tc, paragraph_class)
            problems += validate_pilot_rows(rows, pilot_classes)
    return {"file": path.as_posix(), "has_bom": raw[:3] == b"\xef\xbb\xbf", "rows": len(rows),
            "items": len({r["item_id"] for r in rows}), "problems": problems}


def correction_diff(original: Sequence[Mapping[str, str]], corrected: Sequence[Mapping[str, str]],
                    allowed_items: Iterable[str], input_columns: Sequence[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Cell-level diff of a corrected file against the original it corrects. Returns (changes, problems):
    rows, order and every non-input cell must match; only input cells of ``allowed_items`` may differ."""
    allowed = set(allowed_items)
    problems: list[str] = []
    if len(original) != len(corrected):
        problems.append(f"{len(corrected)} rows; the original has {len(original)}")
    changes = []
    for n, (a, b) in enumerate(zip(original, corrected), start=2):
        if tuple(a) != tuple(b):
            problems.append(f"row {n}: columns differ from the original")
            continue
        diff = [c for c in a if a[c] != b[c]]
        if not diff:
            continue
        if a["item_id"] != b["item_id"] or a["item_id"] not in allowed:
            problems.append(f"row {n} ({b['item_id']}): changed {diff}, but only {sorted(allowed)} may change")
            continue
        shown = [c for c in diff if c not in input_columns]
        if shown:
            problems.append(f"row {n} ({b['item_id']}): shown column(s) {shown} changed")
            continue
        changes.append({"row": n, "item_id": b["item_id"], "cells": {c: {"from": a[c], "to": b[c]} for c in diff}})
    return changes, problems


def pilot_labels_from_rows(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, Any]]:
    """Pilot pass-2 rows -> {label_id: {not_obligation, applies_to, flag}} (pilot rules)."""
    out = {}
    for r in rows:
        if r.get("row_type") != ROW_PILOT:
            continue
        names = tuple(sorted({x.strip() for x in (r.get("applies_to") or "").split(APPLIES_TO_SEPARATOR) if x.strip()}))
        flag = (r.get("differential_flag") or "").strip()
        no = not names and not flag
        out[r["item_id"]] = {"not_obligation": no, "applies_to": names,
                             "flag": None if no else (flag or "unlabelled"), "note": (r.get("note") or "").strip()}
    return out


def pilot_labels_from_votes(votes: Iterable[Mapping[str, Any]], rater: str, pass_no: int) -> dict[str, dict[str, Any]]:
    out = {}
    for v in votes:
        if v["rater_id"] != rater or int(v["pass_no"]) != pass_no:
            continue
        no = v["status"] == "not_obligation"
        out[v["label_id"]] = {"not_obligation": no, "applies_to": tuple(sorted(v.get("applies_to") or ())),
                              "flag": None if no else (v.get("differential_flag") or "unlabelled"),
                              "note": (v.get("notes") or "").strip()}
    return out


def pilot_retest_metrics(p1: Mapping[str, Mapping[str, Any]], p2: Mapping[str, Mapping[str, Any]], *,
                         seed: int, resamples: int) -> dict[str, Any]:
    """Pilot test-retest: κ on the flag and applies_to set agreement over items both passes labelled; rejection agreement."""
    ids = sorted(set(p1) & set(p2))
    both = [i for i in ids if not p1[i]["not_obligation"] and not p2[i]["not_obligation"]]
    return {
        "n_items": len(ids), "both_obligation": len(both),
        "not_obligation": _cohen_block([[("yes" if p1[i]["not_obligation"] else "no",
                                          "yes" if p2[i]["not_obligation"] else "no")] for i in ids],
                                       NOT_OBL_CATEGORIES, seed=seed, resamples=resamples),
        "differential_flag": _cohen_block([[(p1[i]["flag"], p2[i]["flag"])] for i in both], PILOT_FLAG_CATEGORIES,
                                          seed=seed, resamples=resamples),
        "applies_to": _set_block([(p1[i]["applies_to"], p2[i]["applies_to"]) for i in both], seed=seed,
                                 resamples=resamples),
    }


def retest_adjudication_rows(p1_rows: Sequence[Mapping[str, str]], p2_rows: Sequence[Mapping[str, str]],
                             p1_pilot: Mapping[str, Mapping[str, Any]], p2_pilot: Mapping[str, Mapping[str, Any]],
                             pilot_context: Mapping[str, tuple[str, str]]) -> list[dict[str, str]]:
    """Every comparison where pass 1 != pass 2 (plus any unsure in pass 2), with blank decision columns."""
    L1, L2 = parse_labelled_items(p1_rows), parse_labelled_items(p2_rows)
    ctx = {r["item_id"]: (r["source_paragraph_id"], _cap(r["source_span"], 600)) for r in p2_rows
           if r["row_type"] == ROW_ITEM}
    dec = lambda it: "not_obligation" if it["not_obligation"] else "applies_to: " + "; ".join(it["applies_to"])
    base = {c: "" for c in RETEST_ADJ_COLUMNS}
    out = []
    for r in p2_rows:
        iid = r["item_id"]
        if r["row_type"] not in (ROW_ITEM, ROW_CLASS):
            continue
        a, b = L1[iid], L2[iid]
        row = {**base, "item_id": iid, "kind": "retest", "source_paragraph_id": ctx[iid][0], "source_context": ctx[iid][1]}
        if r["row_type"] == ROW_ITEM:
            why = [w for w, x, y in (("not_obligation", a["not_obligation"], b["not_obligation"]),
                                     ("applies_to", a["applies_to"], b["applies_to"])) if x != y]
            if a["flag"] != b["flag"]:
                why.append("differential_flag (derived)")
            if why:
                out.append({**row, "comparison": "item", "differs_on": "; ".join(why),
                            "pass1_decision": f"{dec(a)} | flag: {a['flag']}", "pass2_decision": f"{dec(b)} | flag: {b['flag']}"})
        else:
            cls = r["target_class"]
            j1 = FINAL_NOT_OBLIGATION if a["not_obligation"] else a["judgements"].get(cls, "")
            j2 = FINAL_NOT_OBLIGATION if b["not_obligation"] else b["judgements"].get(cls, "")
            why = (["judgement"] if j1 != j2 else []) + (["unsure"] if JUDGE_UNSURE in (j1, j2) else [])
            if why:
                out.append({**row, "comparison": "class", "target_class": cls, "differs_on": "; ".join(why),
                            "pass1_decision": j1, "pass2_decision": j2,
                            "pass1_matched_paragraph_id": a["matched"].get(cls, ""),
                            "pass2_matched_paragraph_id": b["matched"].get(cls, "")})
    pdec = lambda it: "not_obligation" if it["not_obligation"] else f"applies_to: {'; '.join(it['applies_to'])} | flag: {it['flag']}"
    for iid in sorted(set(p1_pilot) & set(p2_pilot)):
        a, b = p1_pilot[iid], p2_pilot[iid]
        why = [w for w, x, y in (("not_obligation", a["not_obligation"], b["not_obligation"]),
                                 ("applies_to", a["applies_to"], b["applies_to"]),
                                 ("differential_flag", a["flag"], b["flag"])) if x != y]
        if why:
            out.append({**base, "item_id": iid, "kind": "pilot", "comparison": "item",
                        "source_paragraph_id": pilot_context[iid][0], "source_context": pilot_context[iid][1],
                        "differs_on": "; ".join(why), "pass1_decision": pdec(a), "pass2_decision": pdec(b)})
    return out


# -- team review of the 30 overlap items (Akash, Meer): not independent raters, no κ -------------

TEAM_REVIEW_RECEIPTS_FILE = "p2004_team_review_receipts.json"
TEAM_REVIEW_RECEIVED_DIR = "team_review_received"
TEAM_REVIEW_SHEET = "annotation_p2004_{rater}_pass1_completed.csv"
OVERLAP_ADJUDICATION_FILE = "p2004_overlap_adjudication_v1.csv"
OVERLAP_ADJ_COLUMNS = IRR_ADJUDICATION_COLUMNS


def overlap_adjudication_rows(karan_rows: Sequence[Mapping[str, str]],
                              reviews: Mapping[str, Sequence[Mapping[str, str]]],
                              item_ids: Iterable[str]) -> list[dict[str, str]]:
    """Every overlap comparison where Akash's or Meer's labels differ from Karan's pass 1: item rows
    (applies_to, not_obligation) and class rows (judgement, matched_paragraph_id). Decision columns blank."""
    wanted = set(item_ids)
    K = parse_labelled_items([r for r in karan_rows if r["item_id"] in wanted])
    R = {name: parse_labelled_items(rows) for name, rows in reviews.items()}
    ctx = {r["item_id"]: (r["source_paragraph_id"], _cap(r["source_span"], 600)) for r in karan_rows
           if r["row_type"] == ROW_ITEM and r["item_id"] in wanted}
    item_dec = lambda it: "not_obligation" if it["not_obligation"] else "applies_to: " + "; ".join(it["applies_to"])
    base = {c: "" for c in OVERLAP_ADJ_COLUMNS}
    out = []
    for r in karan_rows:
        iid = r["item_id"]
        if iid not in wanted:
            continue
        k = K[iid]
        others = {n: R[n][iid] for n in R}
        people = {"karan": k, **others}
        row = {**base, "item_id": iid, "source_paragraph_id": ctx[iid][0], "source_context": ctx[iid][1],
               **{f"{p}_item_decision": item_dec(v) for p, v in people.items()}}
        if r["row_type"] == ROW_ITEM:
            why = [f for f, get in (("not_obligation", lambda v: v["not_obligation"]),
                                    ("applies_to", lambda v: v["applies_to"]))
                   if any(get(o) != get(k) for o in others.values())]
            if why:
                out.append({**row, "comparison": "item", "differs_on": "; ".join(why),
                            **{f"{p}_decision": item_dec(v) for p, v in people.items()}})
        elif r["row_type"] == ROW_CLASS:
            cls = r["target_class"]
            dec = lambda v: FINAL_NOT_OBLIGATION if v["not_obligation"] else v["judgements"].get(cls, "")
            mid = lambda v: "" if v["not_obligation"] else v["matched"].get(cls, "")
            why = [f for f, get in (("judgement", dec), ("matched_paragraph_id", mid))
                   if any(get(o) != get(k) for o in others.values())]
            if why:
                out.append({**row, "comparison": "class", "target_class": cls, "differs_on": "; ".join(why),
                            **{f"{p}_decision": dec(v) for p, v in people.items()},
                            **{f"{p}_matched_paragraph_id": mid(v) for p, v in people.items()}})
    return out


# -- Part D: final labels for the 123 sample items ------------------------------------------

UNSURE_ADJUDICATION_FILE = "p2004_unsure_adjudication_v1.csv"
ROUTE_RETEST_CONSISTENT = "annotator:karan:retest-consistent"
ROUTE_ADJUDICATED = "annotator:karan:adjudicated"
ROUTE_SINGLE_PASS = "annotator:karan:single-pass"
_ITEM_DECISION_RE = re.compile(r"^(?:applies_to: (?P<a>.+?)(?: \| flag: (?P<f>[\w-]+))?|not_obligation(?: \| flag: None)?)$")


def parse_item_decision(text: str, vocabulary: Sequence[str]) -> dict[str, Any]:
    """'applies_to: A; B [| flag: F]' or 'not_obligation [| flag: None]' -> labels; raises on anything else."""
    m = _ITEM_DECISION_RE.match((text or "").strip())
    if not m:
        raise T1Error(f"unreadable item decision {text!r}")
    if m["a"] is None:
        return {"not_obligation": True, "applies_to": (), "stated_flag": None}
    names = tuple(sorted({x.strip() for x in m["a"].split(";") if x.strip()}))
    bad = [x for x in names if x not in vocabulary]
    if bad or not names:
        raise T1Error(f"item decision {text!r}: names not in the v2.2 vocabulary: {bad}")
    return {"not_obligation": False, "applies_to": names, "stated_flag": m["f"]}


def final_labels(sample_ids: Sequence[str], pass1_rows: Sequence[Mapping[str, str]], *,
                 retest_ids: Iterable[str], retest_adj: Sequence[Mapping[str, str]] | None,
                 overlap_adj: Sequence[Mapping[str, str]], vocabulary: Sequence[str]
                 ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Karan's final labels per sample item: pass 1, overridden by his adjudications (retest, overlap).
    Team reviews never validate; only Karan's written decisions change a label. Returns (labels, problems)."""
    L1 = parse_labelled_items([r for r in pass1_rows if r["item_id"] in set(sample_ids)])
    retest = set(retest_ids)
    by_item: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for r in list(retest_adj or []) + list(overlap_adj):
        by_item[r["item_id"]].append(r)
    problems: list[str] = []
    out = {}
    for iid in sample_ids:
        b = L1[iid]
        rec = {"source_class": b["source_class"], "not_obligation": b["not_obligation"],
               "applies_to": tuple(b["applies_to"]), "judgements": dict(b["judgements"]),
               "matched": dict(b["matched"]), "adjudicated": [], "stated_flag": None,
               "retest": iid in retest, "pending": None}
        rows = by_item.get(iid, [])
        if iid in retest and retest_adj is None:
            rec["pending"] = "retest adjudication file not available"
        for r in rows:
            fd = (r.get("final_decision") or "").strip()
            if r["comparison"] == "item":
                try:
                    d = parse_item_decision(fd, vocabulary)
                except T1Error as exc:
                    problems.append(f"{iid}: {exc}")
                    continue
                rec.update(not_obligation=d["not_obligation"], applies_to=d["applies_to"], stated_flag=d["stated_flag"])
            else:
                cls = r["target_class"]
                if fd == FINAL_NOT_OBLIGATION:
                    rec["judgements"].pop(cls, None)
                elif fd in JUDGEMENTS:
                    if rec["judgements"].get(cls) != fd:
                        rec["matched"].pop(cls, None)  # pass-1 citation belonged to a different judgement
                        for who in ("pass2", "karan", "akash", "meer"):
                            j = (r.get(f"{who}_decision") or "").strip()
                            mid = (r.get(f"{who}_matched_paragraph_id") or "").strip()
                            if j == fd and mid and fd in (JUDGE_SAME, JUDGE_DIFFERENT):
                                rec["matched"][cls] = mid
                                rec.setdefault("matched_source", {})[cls] = who
                                break
                    rec["judgements"][cls] = fd
                else:
                    problems.append(f"{iid} {cls}: unreadable class decision {fd!r}")
            rec["adjudicated"].append(r["comparison"] + (":" + r["target_class"] if r.get("target_class") else ""))
        if rec["not_obligation"]:
            rec["judgements"], rec["matched"] = {}, {}
        rec["unsure_classes"] = sorted(c for c, j in rec["judgements"].items() if j == JUDGE_UNSURE)
        out[iid] = rec
    return out, problems


def unsure_adjudication_rows(labels: Mapping[str, Mapping[str, Any]], pass1_rows: Sequence[Mapping[str, str]]
                             ) -> list[dict[str, str]]:
    """One row per unresolved 'unsure' class judgement, with the item's context and blank final columns."""
    ctx = {r["item_id"]: r for r in pass1_rows if r["row_type"] == ROW_ITEM}
    cands = {(r["item_id"], r["target_class"]): r.get("target_candidates", "") for r in pass1_rows
             if r["row_type"] == ROW_CLASS}
    out = []
    for iid, rec in sorted(labels.items()):
        if rec["not_obligation"] or rec.get("pending"):
            continue
        for cls in rec["unsure_classes"]:
            c = ctx[iid]
            out.append({"item_id": iid, "block": c["block"], "source_class": c["source_class"],
                        "subject_family": c["subject_family"], "source_paragraph_id": c["source_paragraph_id"],
                        "source_context": _cap(c["source_span"], 900), "applies_to": "; ".join(rec["applies_to"]),
                        "target_class": cls, "target_candidates": _cap(cands.get((iid, cls), ""), 1600),
                        "pass1_judgement": JUDGE_UNSURE, "final_decision": "", "final_matched_paragraph_id": "",
                        "final_rationale": ""})
    return out


UNSURE_INPUT_COLUMNS = ("final_decision", "final_matched_paragraph_id", "final_rationale")
ADJUDICATION_INPUT_COLUMNS = ("final_decision", "final_rationale")


def validate_adjudication_completion(template: Sequence[Mapping[str, str]], completed: Sequence[Mapping[str, str]],
                                     input_columns: Sequence[str], paragraph_class: Mapping[str, str] | None = None
                                     ) -> list[str]:
    """Completed adjudication vs the sheet as issued: same rows/columns, immutable cells unchanged, every
    decision and rationale present, class decisions in the vocabulary, matched ids valid where given."""
    problems = []
    if not completed or list(template[0]) != list(completed[0]):
        return [f"columns {list(completed[0]) if completed else []} != {list(template[0])}"]
    if len(template) != len(completed):
        problems.append(f"{len(completed)} rows; the issued sheet has {len(template)}")
    for n, (a, b) in enumerate(zip(template, completed), start=3):
        where = f"row {n} ({b.get('item_id')}{' ' + b['target_class'] if b.get('target_class') else ''})"
        changed = [c for c in a if c not in input_columns and a[c] != b.get(c)]
        if changed:
            problems.append(f"{where}: immutable cell(s) {changed} changed")
        fd = (b.get("final_decision") or "").strip()
        if not fd:
            problems.append(f"{where}: final_decision blank")
        if not (b.get("final_rationale") or "").strip():
            problems.append(f"{where}: final_rationale blank")
        if b.get("comparison", "class") == "class" and fd and fd not in JUDGEMENTS + (FINAL_NOT_OBLIGATION,) \
                and not fd.startswith(("applies_to:", "not_obligation")):
            problems.append(f"{where}: final_decision {fd!r} not in {JUDGEMENTS}")
        if "final_matched_paragraph_id" in input_columns and paragraph_class is not None:
            mid = (b.get("final_matched_paragraph_id") or "").strip()
            if fd in (JUDGE_SAME, JUDGE_DIFFERENT):
                if not PARAGRAPH_ID_RE.match(mid):
                    problems.append(f"{where}: final_matched_paragraph_id {mid!r} is not md_NNNNN::pNNNNN")
                elif paragraph_class.get(mid) != b.get("target_class"):
                    problems.append(f"{where}: {mid} is not a paragraph of {b.get('target_class')!r} "
                                    f"(it belongs to {paragraph_class.get(mid)!r})")
            elif mid:
                problems.append(f"{where}: final_matched_paragraph_id must be blank for {fd!r}")
    return problems


def apply_unsure_decisions(labels: dict[str, dict[str, Any]], unsure_rows: Sequence[Mapping[str, str]]) -> None:
    """Karan's unsure adjudication: class judgement (and its citation) per row; 'unsure' stays unsure."""
    for r in unsure_rows:
        rec = labels[r["item_id"]]
        cls, fd = r["target_class"], r["final_decision"].strip()
        rec["judgements"][cls] = fd
        rec["matched"].pop(cls, None)
        if fd in (JUDGE_SAME, JUDGE_DIFFERENT):
            rec["matched"][cls] = r["final_matched_paragraph_id"].strip()
            rec.setdefault("matched_source", {})[cls] = "unsure_adjudication"
        rec["adjudicated"].append(f"unsure:{cls}")
        rec["unsure_classes"] = sorted(c for c, j in rec["judgements"].items() if j == JUDGE_UNSURE)


def validated_records(labels: Mapping[str, Mapping[str, Any]], candidates: Mapping[str, Mapping[str, Any]],
                      pass1_rows: Sequence[Mapping[str, str]], adj_rationales: Mapping[str, str]
                      ) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[str]]:
    """(validated records, {'rejected': ids, 'in_review': ids}, problems). Candidate records are never modified."""
    rationale = {r["item_id"]: (r.get("applies_to_rationale") or "").strip() for r in pass1_rows if r["row_type"] == ROW_ITEM}
    out, excluded, problems = [], {"rejected": [], "in_review": []}, []
    for iid, rec in sorted(labels.items()):
        if rec["not_obligation"]:
            excluded["rejected"].append(iid)
            continue
        if rec["unsure_classes"] or rec.get("pending"):
            excluded["in_review"].append(iid)
            continue
        if not rec["judgements"] or not rec["applies_to"]:
            problems.append(f"{iid}: obligation with no judgements or no applies_to")
            excluded["in_review"].append(iid)
            continue
        d = derive_flag(rec["judgements"])
        flag = d["flag"] or FLAG_AMBIGUOUS
        if rec.get("stated_flag") and rec["stated_flag"] != flag:
            problems.append(f"{iid}: adjudicated flag {rec['stated_flag']!r} != flag derived from the final "
                            f"judgements {flag!r} (v3.6 derivation used)")
        missing = sorted(c for c, j in rec["judgements"].items() if j in (JUDGE_SAME, JUDGE_DIFFERENT)
                         and not rec["matched"].get(c))
        route = ROUTE_ADJUDICATED if rec["adjudicated"] else (ROUTE_RETEST_CONSISTENT if rec["retest"] else ROUTE_SINGLE_PASS)
        c = candidates[iid]
        out.append({
            **{k: c[k] for k in ("item_id", "source_candidate_id", "md_id", "paragraph_id", "entity_class",
                                 "subject_family", "section_id", "clause_path", "obligation_span", "in_force_from",
                                 "in_force_from_basis", "in_force_to", "amended_by", "era")},
            "compared_classes": sorted(rec["judgements"]),
            "applies_to": list(rec["applies_to"]), "applies_to_rationale": adj_rationales.get(iid) or rationale.get(iid),
            "differential_flag": flag, "ambiguous": flag == FLAG_AMBIGUOUS,
            "per_class_judgement": dict(sorted(rec["judgements"].items())),
            "matched_paragraph_id": dict(sorted(rec["matched"].items())),
            "matched_paragraph_id_missing": missing,
            "label_status": "validated", "provenance": route, "label_source": "manual",
            "raters": {"karan": ["pass1"] + (["pass2"] if rec["retest"] else [])},
            "adjudicated_fields": rec["adjudicated"],
        })
    return out, excluded, problems


# -- Phase 2 closing check: timed blind re-label of single-pass items (evidence only) ----------------

TIMED_SEED = 20261004
TIMED_ITEMS = 20
TIMED_BLOCK_SIZE = 10
TIMED_SHEET = "annotation_p2004_karan_timed_relabel.csv"
TIMED_MINUTES_FILE = "p2004_timed_relabel_minutes.csv"
TIMED_SENDLOG_FILE = "p2004_timed_relabel_sendlog.json"
TIMED_RECEIPTS_FILE = "p2004_timed_relabel_receipts.json"
TIMED_RECEIVED_DIR = "timed_relabel_received"
TIMED_MINUTES_COLUMNS = ("block", "started_at", "ended_at")
TIMED_HEADER = (
    "# Timed blind re-label (Phase 2 closing check). Label as in pass 1 (v3.1): item rows applies_to, "
    "applies_to_rationale, not_obligation, note; class rows judgement (same | different | none | unsure) and "
    "matched_paragraph_id for same/different. Don't open pass 1, your notes, or any adjudication, IRR or report file. "
    "Time each block: write the clock time in p2004_timed_relabel_minutes.csv when you START the block and when you "
    "END it (e.g. 2026-09-27 19:05). Evidence only: no validated label changes.")
_CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?$")


def draw_timed(pool: Sequence[Mapping[str, Any]], *, n: int = TIMED_ITEMS, seed: int = TIMED_SEED) -> list[str]:
    """Seeded, class-stratified draw (at least one per class that has items; the rest proportional)."""
    by_class: dict[str, list[str]] = defaultdict(list)
    for r in sorted(pool, key=lambda r: r["item_id"]):
        by_class[r["entity_class"]].append(r["item_id"])
    alloc = allocate({c: len(v) for c, v in by_class.items()}, min(n, len(pool)), 1)
    rng = random.Random(seed)
    out = []
    for cls in sorted(by_class):
        out.extend(rng.sample(by_class[cls], alloc[cls]))
    return sorted(out)


def parse_clock(raw: str, day: date) -> "datetime":
    """'2026-09-27 19:05', an ISO timestamp, or a bare '19:05' / '7:05 PM' on ``day``."""
    from datetime import datetime as _dt

    s = (raw or "").strip()
    if not s:
        raise T1Error("blank time")
    try:
        return _dt.fromisoformat(s.replace("T", " "))
    except ValueError:
        pass
    m = _CLOCK_RE.match(s)
    if not m:
        raise T1Error(f"unreadable time {raw!r} (use e.g. 2026-09-27 19:05)")
    h, mi, se = int(m[1]), int(m[2]), int(m[3] or 0)
    if m[4]:
        h = h % 12 + (12 if m[4].lower() == "pm" else 0)
    return _dt(day.year, day.month, day.day, h, mi, se)


def timed_block_minutes(rows: Sequence[Mapping[str, str]], items_per_block: Mapping[str, int], day: date
                        ) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-block logged minutes. Returns (blocks, problems); never guesses a missing or reversed time."""
    blocks, problems = [], []
    for r in rows:
        b = str(r.get("block", "")).strip()
        try:
            s, e = parse_clock(r.get("started_at", ""), day), parse_clock(r.get("ended_at", ""), day)
        except T1Error as exc:
            problems.append(f"block {b}: {exc}")
            continue
        mins = (e - s).total_seconds() / 60
        if mins <= 0:
            problems.append(f"block {b}: ended_at is not after started_at")
            continue
        blocks.append({"block": b, "started_at": s.isoformat(sep=" "), "ended_at": e.isoformat(sep=" "),
                       "minutes": round(mins, 2), "items": items_per_block.get(b, 0)})
    listed = {str(r.get("block", "")).strip() for r in rows}
    problems += [f"block {b}: no row in the minutes log" for b in sorted(set(items_per_block) - listed)]
    return blocks, problems


def minutes_per_item(blocks: Sequence[Mapping[str, Any]], *, seed: int, resamples: int) -> dict[str, Any]:
    """Mean minutes per item (total minutes / total items) with a bootstrap over blocks; n = items and blocks."""
    from src.benchmark.annotation import _percentile

    tot_m, tot_i = sum(b["minutes"] for b in blocks), sum(b["items"] for b in blocks)
    rng = random.Random(seed)
    vals = []
    for _ in range(resamples):
        s = [blocks[rng.randrange(len(blocks))] for _ in blocks]
        if sum(b["items"] for b in s):
            vals.append(sum(b["minutes"] for b in s) / sum(b["items"] for b in s))
    vals.sort()
    return {"minutes_per_item": tot_m / tot_i if tot_i else None, "total_minutes": tot_m, "n_items": tot_i,
            "n_blocks": len(blocks), "per_block": [round(b["minutes"] / b["items"], 3) for b in blocks if b["items"]],
            "bootstrap_ci95": [_percentile(vals, 0.025), _percentile(vals, 0.975)] if vals else None,
            "resamples": resamples, "seed": seed, "basis": "measured (clock times logged per block)",
            "caveat": f"the bootstrap resamples {len(blocks)} blocks, so with few blocks the interval is close to the "
                      "range of the per-block rates"}


def leaked_texts(rows: Sequence[Mapping[str, str]], forbidden: Iterable[str], *, min_chars: int = 15) -> list[str]:
    """Any earlier answer text (rationales, notes) that appears anywhere in a sheet meant to be blind."""
    blob = "\n".join(v for r in rows for v in r.values())
    return sorted({t for t in forbidden if len(t) >= min_chars and t in blob})


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------


def search_paragraphs(paragraphs: Iterable[Mapping[str, Any]], manifest: Mapping[str, Mapping[str, Any]], *,
                      entity_class: str | None, family: str | None, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Paragraphs of a class (and family) containing every query word, in paragraph-id order."""
    words = [w.lower() for w in re.findall(r"\w+", query or "")]
    out = []
    for p in paragraphs:
        doc = manifest.get(p["document_id"], {})
        if entity_class and doc.get("entity_class") != entity_class:
            continue
        if family and doc.get("subject_family") != family:
            continue
        text = (p.get("text") or "").lower()
        if all(w in text for w in words):
            out.append({"paragraph_id": p["paragraph_id"], "entity_class": doc.get("entity_class"),
                        "subject_family": doc.get("subject_family"), "text": p.get("text") or ""})
    out.sort(key=lambda x: x["paragraph_id"])
    return out[:limit]
