"""P3-002 Part A: questions, the four answer types, and the blind faithfulness sheet.

Everything here is deterministic and seeded; the LLM is called only by the
runner (``scripts/run_t4.py``), through ``src/llm/client.py``.

Answer types:

* ``genuine``: the LLM answers from the retrieved passages only, citing ids.
* ``concatenated``: no LLM. Every sentence of the passages that holds a **kept**
  P2-001 (rules v4) deontic cue, verbatim (whitespace collapsed), in passage
  order, each sentence once. Sentence bounds are P2-001's ``cue_sentence_bounds``.
* ``adv_negated``: the concatenated answer with deontic polarity flipped
  (shall <-> shall not, must <-> must not, is/are required to <-> is/are not
  required to) and every number doubled.
* ``adv_offtopic``: verbatim kept-cue sentences from seeded random Directions in
  a **different** subject family, added until the concatenated answer's length
  (characters) is reached.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import random
import re
from collections import Counter
from typing import Any, Mapping, Sequence

from src.benchmark.candidates import cue_sentence_bounds

ANSWER_TYPES = ("genuine", "concatenated", "adv_negated", "adv_offtopic")
SHEET_COLUMNS = ("row_id", "block", "question", "passages", "answer", "faithful", "answers_question",
                 "bad_question", "note")
LABEL_COLUMNS = ("faithful", "answers_question", "bad_question", "note")
SCORE_VOCAB = ("0", "1", "2")
BAD_QUESTION_VOCAB = ("yes", "no", "")
SHEET_NOTE = (
    "# T4 faithfulness sheet. For each row read the question, the retrieved passages and the answer, then fill: "
    "faithful: 2 = every claim in the answer is supported by the passages; 1 = partly supported; "
    "0 = unsupported or contradicted by the passages. answers_question: 2 = fully answers the question; "
    "1 = partly; 0 = does not. bad_question: yes if the question itself is flawed (unanswerable from the "
    "passages, ambiguous, or not what a compliance officer would ask); otherwise leave blank. note: optional. "
    "Judge only against the passages shown, not outside knowledge. No AI tools. Work in the three blocks of "
    "10 (column block) and log each block's start and end time in t4_faithfulness_minutes.csv. "
    "Do not edit any other column."
)


class T4Error(ValueError):
    pass


def collapse(text: str) -> str:
    return " ".join((text or "").split())


# -- sampling -----------------------------------------------------------------


def allocate(counts: Mapping[str, int], n: int) -> dict[str, int]:
    """Proportional allocation by largest remainder, at least 1 per class (ties by class name)."""
    total = sum(counts.values())
    if n < len(counts):
        raise T4Error(f"cannot give {len(counts)} classes at least one of {n}")
    quotas = {c: n * k / total for c, k in counts.items()}
    alloc = {c: max(1, math.floor(q)) for c, q in quotas.items()}
    while sum(alloc.values()) < n:
        c = max(sorted(quotas), key=lambda x: (quotas[x] - alloc[x], x))
        alloc[c] += 1
    while sum(alloc.values()) > n:
        c = min((x for x in sorted(quotas) if alloc[x] > 1), key=lambda x: (quotas[x] - alloc[x], x))
        alloc[c] -= 1
    for c in alloc:
        alloc[c] = min(alloc[c], counts[c])
    if sum(alloc.values()) != n:
        raise T4Error("allocation cannot reach n within class sizes")
    return dict(sorted(alloc.items()))


def sample_items(items: Sequence[Mapping[str, Any]], *, n: int, seed: int, min_classes: int,
                 min_families: int, max_attempts: int = 100) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """Stratified by class (proportional, >= 1 each); redraw with seed + k until the family floor holds."""
    pool = [it for it in items if it.get("label_status") == "validated" and not it.get("not_obligation")]
    by_class: dict[str, list[Mapping[str, Any]]] = {}
    for it in sorted(pool, key=lambda x: x["item_id"]):
        by_class.setdefault(it["entity_class"], []).append(it)
    alloc = allocate({c: len(v) for c, v in by_class.items()}, n)
    for attempt in range(max_attempts):
        rng = random.Random(seed + attempt)
        chosen = [it for c in sorted(alloc) for it in rng.sample(by_class[c], alloc[c])]
        classes = {it["entity_class"] for it in chosen}
        families = {it["subject_family"] for it in chosen}
        if len(classes) >= min_classes and len(families) >= min_families:
            return sorted(chosen, key=lambda x: x["item_id"]), {
                "pool": len(pool), "allocation": alloc, "seed": seed, "attempt": attempt,
                "seed_used": seed + attempt, "classes": len(classes), "families": len(families),
                "family_counts": dict(sorted(Counter(it["subject_family"] for it in chosen).items())),
            }
    raise T4Error(f"no draw met >= {min_classes} classes and >= {min_families} families in {max_attempts} attempts")


# -- concatenation and adversarial transforms ------------------------------------


def kept_sentence_spans(text: str, cue_positions: Sequence[Sequence[int]],
                        cue_exclusions: Sequence[str | None]) -> list[tuple[int, int]]:
    """Merged raw sentence spans around every kept cue, in text order.

    Spans are trimmed before merging: P2-001's right bound keeps the trailing
    space that the next sentence's left bound starts on, so untrimmed adjacent
    sentences would overlap by one character and merge (defeating de-duplication).
    """
    spans = []
    for (s, e), exc in zip(cue_positions, cue_exclusions):
        if exc is not None:
            continue
        a, b = cue_sentence_bounds(text, s, e)
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        spans.append((a, b))
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def kept_sentences(text: str, candidate: Mapping[str, Any] | None) -> list[str]:
    """Kept-cue sentences of one paragraph (none if P2-001 made no candidate or excluded it whole)."""
    if not candidate or candidate.get("exclusion_reason"):
        return []
    if candidate.get("span_text") is not None and candidate["span_text"] != text:
        raise T4Error(f"{candidate.get('paragraph_id')}: candidate text differs from the corpus paragraph")
    return [s for s in (collapse(text[a:b]) for a, b in kept_sentence_spans(
        text, candidate["cue_position"], candidate["cue_exclusions"])) if s]


def concatenated_answer(passages: Sequence[tuple[str, str]], candidates: Mapping[str, Mapping[str, Any]]) -> str:
    """``passages``: (paragraph_id, raw text) in passage order."""
    seen: set[str] = set()
    out: list[str] = []
    for pid, text in passages:
        for sent in kept_sentences(text, candidates.get(pid)):
            if sent not in seen:
                seen.add(sent)
                out.append(sent)
    return " ".join(out)


_POLARITY = re.compile(
    r"(?<![\w-])(?:(shall)\s+not|(must)\s+not|(is|are)\s+not\s+required\s+to|(is|are)\s+required\s+to|(shall)|(must))(?![\w-])",
    re.IGNORECASE,
)


def _flip(m: re.Match) -> str:
    g = m.groups()
    if g[0]:
        return g[0]
    if g[1]:
        return g[1]
    if g[2]:
        return f"{g[2]} required to"
    if g[3]:
        return f"{g[3]} not required to"
    if g[4]:
        return f"{g[4]} not"
    return f"{g[5]} not"


_NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.])\d+(?:\.\d+)?(?![\w])")


def _double(m: re.Match) -> str:
    raw = m.group(0)
    plain = raw.replace(",", "")
    decimals = len(plain.split(".")[1]) if "." in plain else 0
    value = float(plain) * 2
    body = f"{value:.{decimals}f}"
    if "," in raw:
        whole, _, frac = body.partition(".")
        body = f"{int(whole):,}" + (f".{frac}" if frac else "")
    return body


def negate(text: str) -> str:
    """Flip deontic polarity, then double every number."""
    return _NUMBER.sub(_double, _POLARITY.sub(_flip, text))


def offtopic_answer(target_chars: int, *, source_family: str | None, directions: Sequence[Mapping[str, Any]],
                    rng: random.Random) -> tuple[str, list[str]]:
    """``directions``: [{md_id, subject_family, sentences}] in a fixed order. Returns (text, md_ids used)."""
    eligible = [d for d in directions if d["subject_family"] and d["subject_family"] != source_family
                and d["sentences"]]
    if not eligible:
        raise T4Error("no Direction in a different subject family has kept sentences")
    order = list(eligible)
    rng.shuffle(order)
    parts: list[str] = []
    used: list[str] = []
    for d in order:
        used.append(d["md_id"])
        for sent in d["sentences"]:
            parts.append(sent)
            if len(" ".join(parts)) >= target_chars:
                return " ".join(parts), used
    return " ".join(parts), used


# -- RePASs input ----------------------------------------------------------------


def repass_payload(answers: Sequence[Mapping[str, Any]], questions: Mapping[str, Mapping[str, Any]]) -> list[dict]:
    """Their input format, exactly: ``QuestionID``, ``RetrievedPassages`` (list of passage texts), ``Answer``."""
    return [{"QuestionID": a["question_id"],
             "RetrievedPassages": [p["text"] for p in questions[a["question_id"]]["passages"]],
             "Answer": a["answer"]} for a in answers]


# -- the blind sheet -------------------------------------------------------------


def assign_sheet_types(question_ids: Sequence[str], quotas: Mapping[str, int], seed: int) -> dict[str, str]:
    """Each question appears once on the sheet, with one answer type (seeded)."""
    if sum(quotas.values()) != len(question_ids):
        raise T4Error("sheet quotas must cover every question exactly once")
    ids = sorted(question_ids)
    random.Random(seed).shuffle(ids)
    out, i = {}, 0
    for t in ANSWER_TYPES:
        for q in ids[i:i + quotas.get(t, 0)]:
            out[q] = t
        i += quotas.get(t, 0)
    return out


def format_passages(passages: Sequence[Mapping[str, str]]) -> str:
    return "\n\n".join(f"[{p['paragraph_id']}] {p['text']}" for p in passages)


def build_sheet(questions: Sequence[Mapping[str, Any]], answers: Mapping[str, Mapping[str, Mapping[str, Any]]],
                assignment: Mapping[str, str], *, order_seed: int, block_size: int) -> tuple[list[dict], dict]:
    """Rows in a seeded order with opaque row ids, plus the key (type, ids) that stays out of the sheet."""
    by_id = {q["question_id"]: q for q in questions}
    qids = sorted(assignment)
    random.Random(order_seed).shuffle(qids)
    rows, key = [], {}
    for i, qid in enumerate(qids):
        q = by_id[qid]
        t = assignment[qid]
        row_id = f"F{i + 1:02d}"
        rows.append({
            "row_id": row_id, "block": str(i // block_size + 1), "question": q["question"],
            "passages": format_passages(q["passages"]), "answer": answers[t][qid]["answer"],
            "faithful": "", "answers_question": "", "bad_question": "", "note": "",
        })
        key[row_id] = {"question_id": qid, "answer_type": t}
    return rows, key


def assert_blind(rows: Sequence[Mapping[str, str]], hidden_values: Sequence[str] = ANSWER_TYPES) -> None:
    for r in rows:
        if set(r) != set(SHEET_COLUMNS):
            raise T4Error(f"sheet columns {sorted(r)} are not {sorted(SHEET_COLUMNS)}")
        if any(r[c] for c in LABEL_COLUMNS):
            raise T4Error(f"{r['row_id']}: label columns must be blank")
        for v in (r["row_id"], r["block"]):
            if any(h in v for h in hidden_values):
                raise T4Error(f"{r['row_id']}: id or block reveals the answer type")


def sheet_csv(rows: Sequence[Mapping[str, str]]) -> str:
    buf = io.StringIO()
    buf.write('"' + SHEET_NOTE.replace('"', "'") + '"\n')
    writer = csv.DictWriter(buf, fieldnames=SHEET_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def read_sheet_text(text: str) -> list[dict[str, str]]:
    """Excel-saved sheets: BOM stripped by the caller's utf-8-sig; the note line may come back quoted or padded."""
    lines = text.splitlines(keepends=True)
    start = 0
    while start < len(lines) and lines[start].lstrip('"').startswith("#"):
        start += 1
    rows = list(csv.DictReader(io.StringIO("".join(lines[start:]))))
    if not rows or "row_id" not in rows[0]:
        raise T4Error("no row_id column found")
    return [{k: (v or "") for k, v in r.items() if k is not None} for r in rows]


def validate_completed(completed: Sequence[Mapping[str, str]], blank: Sequence[Mapping[str, str]]) -> list[str]:
    """Every problem found: ids, untouched input columns, vocabulary, blanks."""
    problems: list[str] = []
    ref = {r["row_id"]: r for r in blank}
    got = {r.get("row_id", "").strip(): r for r in completed}
    if set(got) != set(ref):
        problems.append(f"row ids differ: missing {sorted(set(ref) - set(got))}, extra {sorted(set(got) - set(ref))}")
    for rid in sorted(set(got) & set(ref)):
        r = got[rid]
        for col in ("block", "question", "passages", "answer"):
            if collapse(r.get(col, "")) != collapse(ref[rid][col]):
                problems.append(f"{rid}: column {col} was edited")
        for col in ("faithful", "answers_question"):
            v = (r.get(col) or "").strip()
            if not v:
                problems.append(f"{rid}: {col} is blank")
            elif v not in SCORE_VOCAB:
                problems.append(f"{rid}: {col} {v!r} is not one of {SCORE_VOCAB}")
        bq = (r.get("bad_question") or "").strip().lower()
        if bq not in BAD_QUESTION_VOCAB:
            problems.append(f"{rid}: bad_question {bq!r} must be yes or blank")
    return problems


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
