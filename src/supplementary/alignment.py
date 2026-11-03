"""C2-C3 and D1-D2: the pre-registered rule, the blind alignment sheet, scoring and decisions.

The order is enforced in code, not left to discipline:

* :func:`write_rule` refuses once a sheet exists, so the thresholds cannot move
  after the sheet is drawn.
* :func:`draw_sheet` refuses without a rule file timestamped before it.
* :func:`score_sheet` refuses a blank label, a changed item column, or a rule
  file whose hash differs from the one recorded in the key when the sheet was
  drawn.

The sheet is blind: TF-IDF scores and ranks, link method and score, the
stratum and the candidate pool live only in the key. Candidate paragraphs are
shuffled per item. A row with a linked Direction offers that Direction's
paragraphs; a row without one offers paragraphs from a corpus-wide search
(``class_corpus`` or ``full_corpus``, see :func:`corpus_pool`).
No LLM or embedding model is used; candidates are ranked by TF-IDF.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.benchmark.candidates import wilson_interval
from src.supplementary.common import ERA_POST, ERA_PRE, UNRESOLVED, SupplementaryError

VERSION = "v1"
RULE_FILE = f"p2003_alignment_rule_{VERSION}.json"
SHEET_FILE = f"p2003_alignment_sheet_{VERSION}.csv"
COMPLETED_FILE = f"p2003_alignment_sheet_{VERSION}_completed.csv"
KEY_FILE = f"p2003_alignment_key_{VERSION}.json"
#: The draw time lives here, not in the key, so a redraw on the same inputs reproduces sheet and key byte for byte.
DRAW_LOG_FILE = f"p2003_alignment_draw_log_{VERSION}.json"
DECISIONS_FILE = f"p2003_source_decisions_{VERSION}.json"
SCORE_FILE = f"p2003_alignment_metrics_{VERSION}.json"

SHEET_COLUMNS = ("item_id", "source", "item_text", "linked_directions", "candidates", "label", "paragraph_ids", "note")
ITEM_COLUMNS = SHEET_COLUMNS[:5]
LABEL_COLUMNS = ("label", "paragraph_ids", "note")
FORBIDDEN_IN_SHEET = ("score", "rank", "tfidf", "method", "stratum", "margin")

LABEL_PARAGRAPH = "paragraph"
LABEL_MULTI = "multi_paragraph"
LABEL_DIRECTION_ONLY = "direction_only"
LABEL_WRONG_DIRECTION = "wrong_direction"
LABEL_UNANCHORED = "unanchored"
LABELS = (LABEL_PARAGRAPH, LABEL_MULTI, LABEL_DIRECTION_ONLY, LABEL_WRONG_DIRECTION, LABEL_UNANCHORED)

DECISION_PARAGRAPH = "paragraph_level_weak_label_or_validation"
DECISION_DIRECTION = "direction_level_weak_label_only"
DECISION_VALIDATION = "validation_or_motivation_only"

SOURCES_ALIGNED = ("faq", "enforcement")

#: Where a row's candidates came from (hidden key only). Linked rows search their linked Direction;
#: rows with no linked Direction search the corpus, within the item's resolved entity class plus the
#: function-heading Directions when it has one, otherwise all Directions (Karan, 2026-09-26).
POOL_LINKED = "linked_direction"
POOL_CLASS = "class_corpus"
POOL_FULL = "full_corpus"
POOLS = (POOL_LINKED, POOL_CLASS, POOL_FULL)
CANDIDATE_MAX_CHARS = 1500

HEADER_NOTE = (
    "# NOTE: label every row. Labels: paragraph | multi_paragraph | direction_only | wrong_direction | unanchored. "
    "For paragraph / multi_paragraph put the paragraph_id(s) in paragraph_ids, separated by ';'. You may enter "
    "ANY paragraph_id from the linked Direction (or, for wrong_direction, the right one), not only the candidates "
    "shown: the whole Direction is open to you. Where linked_directions is 'none', candidates are drawn from "
    "across the corpus. Candidates are shuffled and unranked. Do not open the key file."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# C2: the pre-registered rule
# ---------------------------------------------------------------------------


def decide(rate: float, rule: Mapping[str, Any]) -> str:
    """The point estimate against the lines: >= paragraph line, >= direction line, else validation only."""
    if rate >= float(rule["paragraph_weak_min"]):
        return DECISION_PARAGRAPH
    if rate >= float(rule["direction_weak_min"]):
        return DECISION_DIRECTION
    return DECISION_VALIDATION


def write_rule(path: Path, sheet_path: Path, rule: Mapping[str, Any], *, force: bool = False) -> dict[str, Any]:
    """C2. Refuses once the sheet exists; refuses to overwrite an existing rule without ``force``."""
    if sheet_path.is_file():
        raise SupplementaryError(f"{sheet_path} already exists: the rule is fixed and cannot be rewritten")
    if path.is_file() and not force:
        raise SupplementaryError(f"{path} exists; edit it by hand before drawing the sheet, or pass --force")
    lo, hi = float(rule["direction_weak_min"]), float(rule["paragraph_weak_min"])
    if not 0 <= lo < hi <= 1:
        raise SupplementaryError(f"rule lines must satisfy 0 <= direction_weak_min < paragraph_weak_min <= 1: {rule}")
    body = {
        "created_at": _now(),
        "prompt": "P2-003 C2",
        "rule": {"paragraph_weak_min": hi, "direction_weak_min": lo},
        "decisions": {
            f">= {hi:.0%}": DECISION_PARAGRAPH,
            f"{lo:.0%} to < {hi:.0%}": DECISION_DIRECTION,
            f"< {lo:.0%}": DECISION_VALIDATION,
        },
        "clean_means": "label `paragraph`: the item maps to one specific paragraph",
        "compared": "the point estimate of the clean rate, per source; the report states whether the Wilson 95% "
                    "interval crosses a line",
        "interval_note": "with n of about 30 a Wilson 95% interval is roughly +/-17 points",
        "context": "the 60% line mirrors the dossier's alignment trigger (benchmark.alignment_check.trigger_threshold)",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return body


def read_rule(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SupplementaryError(f"no rule file at {path}: run `rule` before `sheet`")
    body = json.loads(path.read_text(encoding="utf-8"))
    for k in ("created_at", "rule"):
        if k not in body:
            raise SupplementaryError(f"rule file {path} has no {k!r}")
    return body


# ---------------------------------------------------------------------------
# C3: qualification, strata, candidates, sheet and key
# ---------------------------------------------------------------------------


def compile_cues(cues: Sequence[str]) -> list[tuple[str, re.Pattern]]:
    return [(c, re.compile(rf"(?<![\w-]){c}(?![\w-])", re.IGNORECASE)) for c in cues]


def faq_qualifies(answer: str, requirement: Sequence[tuple[str, re.Pattern]],
                  entity: Sequence[tuple[str, re.Pattern]]) -> tuple[bool, list[str], list[str]]:
    req = [c for c, rx in requirement if rx.search(answer)]
    ent = [c for c, rx in entity if rx.search(answer)]
    return bool(req and ent), req, ent


def item_text(item: Mapping[str, Any]) -> str:
    """What the rater reads (and what TF-IDF ranks candidates against)."""
    f = item["fields"]
    if item["source"] == "faq":
        return f"Topic: {f.get('topic_title')}\nQ: {f.get('question')}\nA: {f.get('answer')}"
    cited = "; ".join(item["cited_directions"]) or "(none)"
    statutes = "; ".join(f.get("statutes_cited") or []) or "(none)"
    charges = "\n".join(f"- {d}" for d in f.get("deficiencies") or []) or "(none parsed)"
    return (f"{item['title']} ({item.get('published_date')})\nEntity: {f.get('entity_name')} "
            f"[{item.get('entity_class')}]\nDirections cited: {cited}\nStatutes cited: {statutes}\n"
            f"Charges sustained:\n{charges}")


def _round_robin(groups: Mapping[str, list[Mapping[str, Any]]], n: int) -> list[Mapping[str, Any]]:
    queues = {k: list(v) for k, v in sorted(groups.items())}
    out: list[Mapping[str, Any]] = []
    while len(out) < n and any(queues.values()):
        for k in sorted(queues):
            if queues[k] and len(out) < n:
                out.append(queues[k].pop(0))
    return out


def select_faq(items: Sequence[Mapping[str, Any]], conf: Mapping[str, Any], seed: int) -> dict[str, Any]:
    requirement = compile_cues(conf["faq_requirement_cues"])
    entity = compile_cues(conf["faq_entity_cues"])
    cue_counts = {c: 0 for c, _ in requirement}
    ent_counts = {c: 0 for c, _ in entity}
    qualifying = []
    for it in sorted(items, key=lambda r: r["item_id"]):
        ok, req, ent = faq_qualifies(it["fields"].get("answer") or "", requirement, entity)
        for c in req:
            cue_counts[c] += 1
        for c in ent:
            ent_counts[c] += 1
        if ok:
            qualifying.append(it)
    n = int(conf["faq_items"])
    if len(qualifying) < int(conf["min_faq_items"]):
        raise SupplementaryError(f"only {len(qualifying)} FAQ items qualify (< {conf['min_faq_items']}); "
                                 "the check cannot give a usable rate. Escalate before drawing (P2-003 §AB).")
    rng = random.Random(seed)
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for it in qualifying:
        groups.setdefault(it["fields"].get("category") or "(none)", []).append(it)
    for k in sorted(groups):
        rng.shuffle(groups[k])
    chosen = _round_robin(groups, n)
    return {"chosen": chosen, "qualifying": len(qualifying), "eligible": len(items),
            "shortfall": max(0, n - len(qualifying)), "requirement_cue_counts": cue_counts,
            "entity_cue_counts": ent_counts, "qualifying_by_category": {k: len(v) for k, v in sorted(groups.items())},
            "strata": {it["item_id"]: f"faq:{it['fields'].get('category')}" for it in chosen}}


def select_enforcement(items: Sequence[Mapping[str, Any]], conf: Mapping[str, Any], seed: int) -> dict[str, Any]:
    n = int(conf["enforcement_items"])
    rng = random.Random(seed + 1)
    post = [it for it in items if it["era"] == ERA_POST]
    pre = [it for it in items if it["era"] == ERA_PRE]

    def grouped(pool):
        g: dict[str, list[Mapping[str, Any]]] = {}
        for it in sorted(pool, key=lambda r: r["item_id"]):
            g.setdefault(it["entity_class"] or UNRESOLVED, []).append(it)
        for k in sorted(g):
            rng.shuffle(g[k])
        return g

    chosen = _round_robin(grouped(post), n)
    if len(chosen) < n:
        chosen += _round_robin(grouped(pre), n - len(chosen))
    strata = {it["item_id"]: f"enforcement:{it['era']}:{it['entity_class'] or UNRESOLVED}" for it in chosen}
    return {"chosen": chosen, "eligible": len(items), "post_consolidation": len(post), "pre_consolidation": len(pre),
            "unknown_era": len(items) - len(post) - len(pre), "shortfall": max(0, n - len(chosen)),
            "by_class_post": {k: len(v) for k, v in sorted(grouped(post).items())}, "strata": strata}


def rank_candidates(query: str, paragraphs: Sequence[Mapping[str, Any]], k: int,
                    min_chars: int) -> list[dict[str, Any]]:
    """Top ``k`` paragraphs of one Direction by TF-IDF cosine to ``query``; ties by paragraph_id."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    pool = [p for p in paragraphs if len((p.get("text") or "").strip()) >= min_chars]
    if not pool:
        return []
    vec = TfidfVectorizer(lowercase=True, sublinear_tf=True, token_pattern=r"(?u)\b\w\w+\b")
    matrix = vec.fit_transform([p["text"] for p in pool])
    q = vec.transform([query])
    scores = (matrix @ q.T).toarray().ravel()
    order = sorted(range(len(pool)), key=lambda i: (-scores[i], pool[i]["paragraph_id"]))[:k]
    return [{"paragraph_id": pool[i]["paragraph_id"], "tfidf_score": round(float(scores[i]), 6), "rank": r + 1,
             "text": pool[i]["text"]} for r, i in enumerate(order)]


def _format_candidates(cands: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for c in cands:
        text = " ".join(c["text"].split())
        if len(text) > CANDIDATE_MAX_CHARS:
            text = text[:CANDIDATE_MAX_CHARS].rstrip() + " […]"
        parts.append(f"[{c['paragraph_id']}] {text}")
    return "\n\n".join(parts)


class CorpusCandidates:
    """TF-IDF over the whole corpus (fitted once, lazily), searched within a set of Directions.

    Used only for rows with no linked Direction. Paragraphs shorter than
    ``min_chars`` are never candidates, as for linked rows.
    """

    def __init__(self, paragraphs_by_doc: Mapping[str, Sequence[Mapping[str, Any]]], min_chars: int):
        self._rows = sorted((p for rows in paragraphs_by_doc.values() for p in rows
                             if len((p.get("text") or "").strip()) >= min_chars), key=lambda p: p["paragraph_id"])
        self._vec = self._matrix = None

    def rank(self, query: str, docs: set[str], k: int) -> list[dict[str, Any]]:
        from sklearn.feature_extraction.text import TfidfVectorizer

        if self._vec is None:
            self._vec = TfidfVectorizer(lowercase=True, sublinear_tf=True, token_pattern=r"(?u)\b\w\w+\b")
            self._matrix = self._vec.fit_transform([p["text"] for p in self._rows]) if self._rows else None
        if self._matrix is None:
            return []
        scores = (self._matrix @ self._vec.transform([query]).T).toarray().ravel()
        idx = [i for i, p in enumerate(self._rows) if p["document_id"] in docs]
        order = sorted(idx, key=lambda i: (-scores[i], self._rows[i]["paragraph_id"]))[:k]
        return [{"paragraph_id": self._rows[i]["paragraph_id"], "tfidf_score": round(float(scores[i]), 6),
                 "rank": r + 1, "text": self._rows[i]["text"]} for r, i in enumerate(order)]


def corpus_pool(entity_class: str | None, entity_class_of: Mapping[str, str | None],
                function_headings: Sequence[str]) -> tuple[str, set[str]]:
    """(pool name, Directions searched) for a row with no linked Direction."""
    if entity_class and entity_class != UNRESOLVED:
        allowed = {entity_class, *function_headings}
        return POOL_CLASS, {m for m, c in entity_class_of.items() if c in allowed}
    return POOL_FULL, set(entity_class_of)


def draw_sheet(*, items_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
               links_by_item: Mapping[str, Sequence[Mapping[str, Any]]], titles: Mapping[str, str],
               paragraphs_by_doc: Mapping[str, Sequence[Mapping[str, Any]]], conf: Mapping[str, Any],
               rule_path: Path, sheet_path: Path, key_path: Path, best_link,
               entity_class_of: Mapping[str, str | None], function_headings: Sequence[str],
               force: bool = False) -> dict[str, Any]:
    """C3. Writes the blind sheet and the hidden key; returns the key's meta plus ``drawn_at``.

    ``entity_class_of`` maps every md_id to its raw entity class (the manifest);
    ``function_headings`` are the non-core classes (config ``matching.function_headings``).
    """
    rule = read_rule(rule_path)
    drawn_at = _now()
    if not rule["created_at"] < drawn_at:
        raise SupplementaryError(f"rule file {rule_path} is not timestamped before the sheet ({rule['created_at']})")
    if sheet_path.is_file() and not force:
        raise SupplementaryError(f"{sheet_path} exists; refusing to redraw (pass --force only before labelling)")
    if sheet_path.is_file():
        _refuse_if_labelled(sheet_path)
    seed = int(conf["seed"])
    faq = select_faq(items_by_source.get("faq", []), conf, seed)
    enf = select_enforcement(items_by_source.get("enforcement", []), conf, seed)
    k, min_chars = int(conf["candidates_per_item"]), int(conf["candidate_min_chars"])
    rows, key_items = [], {}
    corpus = CorpusCandidates(paragraphs_by_doc, min_chars)
    for it in list(faq["chosen"]) + list(enf["chosen"]):
        recs = links_by_item.get(it["item_id"], [])
        best = best_link(recs)
        others = sorted({r["md_id"] for r in recs if r["md_id"]} - ({best["md_id"]} if best else set()))
        linked = ([best["md_id"]] if best else []) + others[:2]
        text = item_text(it)
        if best:
            pool, pool_docs = POOL_LINKED, [best["md_id"]]
            cands = rank_candidates(text, paragraphs_by_doc.get(best["md_id"], []), k, min_chars)
        else:
            pool, docs = corpus_pool(it["entity_class"], entity_class_of, function_headings)
            pool_docs = sorted(docs)
            cands = corpus.rank(text, docs, k)
        shown = list(cands)
        random.Random(f"{seed}:{it['item_id']}").shuffle(shown)
        rows.append({
            "item_id": it["item_id"], "source": it["source"], "item_text": text,
            "linked_directions": "\n".join(f"{m} | {titles.get(m) or '(no title)'}" for m in linked) or "none",
            "candidates": _format_candidates(shown), "label": "", "paragraph_ids": "", "note": ""})
        strata = faq["strata"] if it["source"] == "faq" else enf["strata"]
        key_items[it["item_id"]] = {
            "source": it["source"], "stratum": strata[it["item_id"]], "era": it["era"],
            "entity_class": it["entity_class"],
            "link": ({k2: best[k2] for k2 in ("md_id", "method", "score", "basis", "margin", "tied_best")}
                     if best else None),
            "linked_md_ids": linked,
            "candidate_pool": pool, "candidate_pool_directions": len(pool_docs),
            "candidates": [{kk: c[kk] for kk in ("paragraph_id", "tfidf_score", "rank")} for c in cands],
            "shown_order": [c["paragraph_id"] for c in shown]}
    random.Random(seed + 2).shuffle(rows)
    assert_blind(rows)
    write_sheet(rows, sheet_path)
    meta = {
        "seed": seed, "rule_file": rule_path.name, "rule_created_at": rule["created_at"],
        "rule_sha256": sha256_file(rule_path), "sheet_sha256": sha256_file(sheet_path),
        "n": {"faq": len(faq["chosen"]), "enforcement": len(enf["chosen"])},
        "faq": {k2: v for k2, v in faq.items() if k2 not in ("chosen", "strata")},
        "enforcement": {k2: v for k2, v in enf.items() if k2 not in ("chosen", "strata")},
        "candidates_per_item": k, "candidate_min_chars": min_chars,
        "items_without_link": sorted(i for i, v in key_items.items() if v["link"] is None),
        "candidate_pools": {p: sum(v["candidate_pool"] == p for v in key_items.values()) for p in POOLS},
        "function_headings": list(function_headings),
    }
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps({"meta": meta, "items": key_items}, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return {**meta, "drawn_at": drawn_at}


def assert_blind(rows: Sequence[Mapping[str, str]]) -> None:
    for r in rows:
        if tuple(r) != SHEET_COLUMNS:
            raise SupplementaryError(f"sheet columns {tuple(r)} != {SHEET_COLUMNS}")
        if any((r[c] or "").strip() for c in LABEL_COLUMNS):
            raise SupplementaryError(f"{r['item_id']}: label columns must be blank on a drawn sheet")
    for col in SHEET_COLUMNS:
        if any(word in col for word in FORBIDDEN_IN_SHEET):
            raise SupplementaryError(f"sheet column {col!r} would reveal a hidden field")


def write_sheet(rows: Sequence[Mapping[str, str]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(HEADER_NOTE + "\n")
        w = csv.DictWriter(fh, fieldnames=SHEET_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


def read_sheet(path: Path | str) -> list[dict[str, str]]:
    """Excel-saved sheets: ``utf-8-sig`` (BOM), and the header note may come back quoted or comma-padded."""
    text = Path(path).read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)
    start = 0
    while start < len(lines) and lines[start].lstrip('"').startswith("#"):
        start += 1
    rows = list(csv.DictReader(io.StringIO("".join(lines[start:]))))
    if rows and "item_id" not in rows[0]:
        raise SupplementaryError(f"{path}: no item_id column (columns: {list(rows[0])})")
    return rows


def _refuse_if_labelled(path: Path) -> None:
    if any((r.get(c) or "").strip() for r in read_sheet(path) for c in LABEL_COLUMNS):
        raise SupplementaryError(f"{path} already holds labels; refusing to overwrite")


# ---------------------------------------------------------------------------
# D1-D2: scoring and decisions
# ---------------------------------------------------------------------------


def _split_ids(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,\s]+", raw or "") if p.strip()]


def check_labelled(labelled: Sequence[Mapping[str, str]], drawn: Sequence[Mapping[str, str]],
                   paragraph_ids: set[str]) -> list[str]:
    """Every problem that stops scoring. Blank labels first, so the message is the obvious one."""
    blank = [r.get("item_id") for r in labelled if not (r.get("label") or "").strip()]
    if blank:
        return [f"{len(blank)} of {len(labelled)} rows have a blank label (e.g. {blank[:5]}); "
                "score only a fully labelled sheet"]
    problems = []
    drawn_by_id = {r["item_id"]: r for r in drawn}
    if sorted(drawn_by_id) != sorted(r.get("item_id") for r in labelled):
        problems.append("the labelled sheet does not hold exactly the drawn items")
    for r in labelled:
        d = drawn_by_id.get(r.get("item_id"))
        if d is None:
            continue
        changed = [c for c in ITEM_COLUMNS if (r.get(c) or "") != (d.get(c) or "")]
        if changed:
            problems.append(f"{r['item_id']}: {changed} differ from the drawn sheet")
        label = (r.get("label") or "").strip()
        if label not in LABELS:
            problems.append(f"{r['item_id']}: label {label!r} is not one of {LABELS}")
            continue
        ids = _split_ids(r.get("paragraph_ids", ""))
        if label == LABEL_PARAGRAPH and len(ids) != 1:
            problems.append(f"{r['item_id']}: `paragraph` needs exactly one paragraph_id, got {ids}")
        if label == LABEL_MULTI and len(ids) < 2:
            problems.append(f"{r['item_id']}: `multi_paragraph` needs two or more paragraph_ids, got {ids}")
        unknown = [p for p in ids if p not in paragraph_ids]
        if unknown:
            problems.append(f"{r['item_id']}: unknown paragraph_id(s) {unknown}")
    return problems


def _rate(k: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "wilson95": None}
    lo, hi = wilson_interval(k, n)
    return {"k": k, "n": n, "rate": round(k / n, 4), "wilson95": [round(lo, 4), round(hi, 4)]}


def _block_metrics(rows: Sequence[Mapping[str, str]], key_items: Mapping[str, Any]) -> dict[str, Any]:
    labels = [r["label"].strip() for r in rows]
    dist = {lab: labels.count(lab) for lab in LABELS}
    n = len(rows)
    linked = [r for r in rows if key_items[r["item_id"]]["link"]]
    judged = [r for r in linked if r["label"].strip() != LABEL_UNANCHORED]
    correct = [r for r in judged if r["label"].strip() != LABEL_WRONG_DIRECTION]
    chosen, hits = 0, 0
    by_pool = {p: [0, 0] for p in POOLS}
    for r in rows:
        if r["label"].strip() in (LABEL_PARAGRAPH, LABEL_MULTI):
            k = key_items[r["item_id"]]
            shown = set(k["shown_order"])
            ids = _split_ids(r.get("paragraph_ids", ""))
            chosen += len(ids)
            hits += sum(p in shown for p in ids)
            pool = k.get("candidate_pool") or (POOL_LINKED if k["link"] else POOL_FULL)
            by_pool[pool][0] += sum(p in shown for p in ids)
            by_pool[pool][1] += len(ids)
    return {
        "n": n, "label_distribution": dist,
        "clean_rate": _rate(dist[LABEL_PARAGRAPH], n),
        "paragraph_or_multi_rate": _rate(dist[LABEL_PARAGRAPH] + dist[LABEL_MULTI], n),
        "items_with_link": len(linked),
        "direction_link_precision": _rate(len(correct), len(judged)),
        "unanchored_among_linked": sum(r["label"].strip() == LABEL_UNANCHORED for r in linked),
        "candidate_hit_share": _rate(hits, chosen),
        "candidate_hit_share_by_pool": {p: _rate(h, c) for p, (h, c) in by_pool.items()},
        "items_by_pool": {p: sum((key_items[r["item_id"]].get("candidate_pool")
                                  or (POOL_LINKED if key_items[r["item_id"]]["link"] else POOL_FULL)) == p
                                 for r in rows) for p in POOLS},
    }


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    cats = sorted(set(a) | set(b))
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return None if pe == 1 else round((po - pe) / (1 - pe), 4)


def score_sheet(*, labelled_path: Path, drawn_path: Path, key_path: Path, rule_path: Path,
                paragraph_ids: set[str], minutes: float | None = None,
                second_raters: Mapping[str, Path] | None = None) -> dict[str, Any]:
    """D1-D2. Raises on any problem; returns metrics and per-source decisions."""
    labelled = read_sheet(labelled_path)
    drawn = read_sheet(drawn_path)
    problems = check_labelled(labelled, drawn, paragraph_ids)
    if problems:
        raise SupplementaryError("cannot score: " + " | ".join(problems[:10]))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    rule_body = read_rule(rule_path)
    if sha256_file(rule_path) != key["meta"]["rule_sha256"]:
        raise SupplementaryError(f"{rule_path} changed after the sheet was drawn; the pre-registered rule no longer "
                                 "matches the key")
    items = key["items"]
    per_source, by_stratum, decisions = {}, {}, {}
    for source in SOURCES_ALIGNED:
        rows = [r for r in labelled if items[r["item_id"]]["source"] == source]
        m = _block_metrics(rows, items)
        per_source[source] = m
        strata: dict[str, list] = {}
        for r in rows:
            strata.setdefault(items[r["item_id"]]["stratum"], []).append(r)
        by_stratum[source] = {s: {"n": len(rs), "label_distribution": _block_metrics(rs, items)["label_distribution"],
                                  "clean_rate": _block_metrics(rs, items)["clean_rate"]}
                              for s, rs in sorted(strata.items())}
        clean = m["clean_rate"]
        if clean["rate"] is None:
            continue
        lines = {"paragraph_weak_min": rule_body["rule"]["paragraph_weak_min"],
                 "direction_weak_min": rule_body["rule"]["direction_weak_min"]}
        lo, hi = clean["wilson95"]
        decisions[source] = {
            "source": source, "n": clean["n"], "clean": clean["k"], "rate": clean["rate"],
            "wilson95": clean["wilson95"], "decision": decide(clean["rate"], rule_body["rule"]),
            "interval_crosses": sorted(k for k, v in lines.items() if lo < v <= hi),
            "rule_file": rule_path.name, "rule_sha256": key["meta"]["rule_sha256"]}
    kappa = {}
    for rater, path in (second_raters or {}).items():
        theirs = {r["item_id"]: (r.get("label") or "").strip() for r in read_sheet(path)}
        shared = [r for r in labelled if theirs.get(r["item_id"])]
        kappa[rater] = {"n": len(shared), "kappa_label": cohen_kappa(
            [r["label"].strip() for r in shared], [theirs[r["item_id"]] for r in shared])}
    n = len(labelled)
    return {"n": n, "per_source": per_source, "by_stratum": by_stratum,
            "decisions": decisions, "kappa": kappa or None,
            "minutes_total": minutes, "minutes_per_item": round(minutes / n, 2) if minutes and n else None,
            "sheet_sha256": sha256_file(labelled_path), "drawn_sheet_sha256": key["meta"]["sheet_sha256"],
            "rule": rule_body["rule"], "rule_created_at": rule_body["created_at"]}


# ---------------------------------------------------------------------------
# Part D scoring conventions (Karan, fixed before any rate was seen, 2026-09-26)
# ---------------------------------------------------------------------------

_MD_IN_NOTE = re.compile(r"\bmd_\d+\b")


def _note_flag(note: str, word: str) -> bool:
    return re.search(rf"\b{word}\b", note or "", re.IGNORECASE) is not None


def link_verdict(row: Mapping[str, str], key_item: Mapping[str, Any]) -> str | None:
    """Convention 2 for one row with a link (``None`` for an unlinked row).

    Wrong when: the label is ``wrong_direction``; a chosen paragraph lies outside
    the linked Directions; the label is ``unanchored`` although a link existed;
    or a ``direction_only`` note names md_ids none of which is linked (the
    rater points elsewhere). Correct otherwise; a ``direction_only`` row is
    correct when its note names a linked md_id, or names none.
    """
    if not key_item.get("link"):
        return None
    linked = set(key_item.get("linked_md_ids") or [key_item["link"]["md_id"]])
    label = row["label"].strip()
    if label == LABEL_WRONG_DIRECTION:
        return "wrong:wrong_direction"
    if label == LABEL_UNANCHORED:
        return "wrong:unanchored_with_link"
    if label in (LABEL_PARAGRAPH, LABEL_MULTI):
        docs = {p.split("::")[0] for p in _split_ids(row.get("paragraph_ids", ""))}
        return "correct:paragraph_in_linked" if docs <= linked else "wrong:paragraph_outside_linked"
    named = set(_MD_IN_NOTE.findall(row.get("note") or ""))
    if not named:
        return "correct:direction_only_no_note_md"
    return "correct:direction_only_note_matches_link" if named & linked else "wrong:direction_only_note_names_other"


def convention_metrics(labelled: Sequence[Mapping[str, str]], key_items: Mapping[str, Any],
                       rule: Mapping[str, Any], enforcement_items: Sequence[Mapping[str, Any]] = ()) -> dict:
    """Conventions 1-3: strict clean rate and note counts, strict link precision, unparsed charges."""
    out: dict[str, Any] = {"per_source": {}}
    for source in SOURCES_ALIGNED:
        rows = [r for r in labelled if key_items[r["item_id"]]["source"] == source]
        n = len(rows)
        partial = [r for r in rows if _note_flag(r.get("note"), "partial")]
        uncertain = [r for r in rows if _note_flag(r.get("note"), "uncertain")]
        clean = [r for r in rows if r["label"].strip() == LABEL_PARAGRAPH]
        strict = [r for r in clean if not _note_flag(r.get("note"), "partial")]
        primary_rate = len(clean) / n if n else None
        strict_rate = _rate(len(strict), n)
        verdicts: dict[str, int] = {}
        for r in rows:
            v = link_verdict(r, key_items[r["item_id"]])
            if v:
                verdicts[v] = verdicts.get(v, 0) + 1
        correct = sum(c for v, c in verdicts.items() if v.startswith("correct"))
        linked = sum(verdicts.values())
        out["per_source"][source] = {
            "n": n, "partial_notes": len(partial), "uncertain_notes": len(uncertain),
            "partial_among_paragraph": len(clean) - len(strict),
            "strict_clean_rate": strict_rate,
            "strict_decision": decide(strict_rate["rate"], rule) if strict_rate["rate"] is not None else None,
            "primary_decision": decide(primary_rate, rule) if primary_rate is not None else None,
            "strict_same_band": (decide(strict_rate["rate"], rule) == decide(primary_rate, rule))
            if primary_rate is not None else None,
            "link_precision_strict": _rate(correct, linked),
            "link_verdicts": dict(sorted(verdicts.items())),
        }
    if enforcement_items:
        none_parsed = [it["item_id"] for it in enforcement_items if not it["fields"].get("deficiencies")]
        out["enforcement_charges_none_parsed"] = {"k": len(none_parsed), "n": len(enforcement_items)}
    return out


# ---------------------------------------------------------------------------
# Sensitivity: post-stratified clean rate (Karan, 2026-09-26; the sheet itself was drawn with equal allocation)
# ---------------------------------------------------------------------------


def post_stratified(by_stratum: Mapping[str, Mapping[str, Any]], population: Mapping[str, int], prefix: str,
                    primary_rate: float, rule: Mapping[str, Any]) -> dict[str, Any]:
    """Weight each sampled stratum's observed clean rate by its population share.

    ``population`` maps stratum name (without ``prefix``) to its population size.
    Strata with population but no sampled row are listed with their share and
    left out of the weights (the weights are renormalised over sampled strata).
    A point estimate only: no interval is computed.
    """
    total = sum(population.values())
    rows, unsampled = [], []
    for name, size in sorted(population.items()):
        b = by_stratum.get(f"{prefix}{name}")
        if not b or not b["n"]:
            unsampled.append({"stratum": name, "population": size, "share": round(size / total, 4) if total else None})
            continue
        rows.append({"stratum": name, "population": size, "sampled": b["n"], "clean": b["clean_rate"]["k"],
                     "rate": b["clean_rate"]["rate"]})
    covered = sum(r["population"] for r in rows)
    weighted = sum(r["population"] / covered * r["rate"] for r in rows) if covered else None
    unmatched = sorted(k for k in by_stratum if k.startswith(prefix) and k[len(prefix):] not in population)
    return {
        "population_total": total, "population_covered": covered,
        "population_covered_share": round(covered / total, 4) if total else None,
        "strata": rows, "unsampled_strata": unsampled, "sampled_strata_without_population": unmatched,
        "weighted_clean_rate": round(weighted, 4) if weighted is not None else None,
        "weighted_decision": decide(weighted, rule) if weighted is not None else None,
        "primary_decision": decide(primary_rate, rule),
        "same_band_as_primary": (decide(weighted, rule) == decide(primary_rate, rule)) if weighted is not None else None,
        "note": "point estimate; no interval computed",
    }
