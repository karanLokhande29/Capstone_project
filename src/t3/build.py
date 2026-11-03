"""T3 items and the parse spot-check sheet (P4-001 task 1).

An item is a (paragraph, as-of date) pair whose status follows unambiguously:

* the action is ``paragraph_whole`` (substitute / delete) or ``within_paragraph``
  (substitute / delete / insert) in an amendment linked to exactly one Direction;
* the target path matches at least one corpus paragraph of that Direction exactly
  (the first by position is the item's paragraph);
* no other amendment of that Direction parses or cites the same path (so the
  status after the effective date is this amendment's alone);
* the effective date is known (a "whichever is earlier" window is allowed:
  as-of dates are drawn outside it);
* the corpus-version check is ``original`` or ``amended`` (not ``unclear``).

Gold: before the effective date -> ``in_force_original``, governed by the
Direction (md_id); on or after -> ``amended`` (``deleted`` for a whole-paragraph
deletion), governed by the amendment item id.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import math
import random
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from src.benchmark.t1 import parse_paragraph_refs, ref_covers
from src.t3.parser import Action, corpus_version, effective_date

ITEM_SCOPES = ("paragraph_whole", "within_paragraph")
STATUSES = ("in_force_original", "amended", "deleted")
SHEET_COLUMNS = ("row_id", "amendment_id", "direction", "instruction_excerpt", "commencement_excerpt",
                 "parsed_action", "parsed_target", "parsed_effective_date", "correct", "note")
SHEET_NOTE = ("# T3 parse spot-check. Check each parse against the amendment text only. No AI tools. "
              "For each row: is parsed_action (substitute / delete / insert, and whether the whole paragraph or "
              "words within it), parsed_target (the paragraph number(s)) and parsed_effective_date correct for "
              "this instruction? correct: yes or no. If no, say what is wrong in note. Do not edit other columns.")


class T3Error(ValueError):
    pass


def _d(s: str) -> _dt.date:
    return _dt.date.fromisoformat(s)


def target_paragraphs(action: Action, paras_by_md: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, list[str]]:
    """target path -> corpus paragraph ids of that exact clause path, in document order."""
    out: dict[str, list[str]] = {}
    for t in action.targets:
        out[t] = [p["paragraph_id"] for p in paras_by_md.get(action.md_id or "", [])
                  if (p.get("clause_path") or "").lower().replace(" ", "") == t]
    return out


def candidate_rows(actions: Sequence[Action], amendments: Mapping[str, Mapping[str, Any]],
                   paras_by_md: Mapping[str, Sequence[Mapping[str, Any]]], text_of: Mapping[str, str],
                   issue_date: Mapping[str, str | None]) -> tuple[list[dict], Counter]:
    """One row per (action, target) that is eligible for items, plus the exclusion counts."""
    why: Counter = Counter()
    # every amendment's cited or parsed paths per Direction, to find paths touched more than once
    touched: dict[tuple[str, str], set[str]] = defaultdict(set)
    for it in amendments.values():
        f = it.get("fields") or {}
        for md in f.get("linked_md_ids") or []:
            for r in parse_paragraph_refs(f.get("paragraph_refs") or []):
                touched[(md, r)].add(it["item_id"])
    for a in actions:
        if a.md_id:
            for t in a.targets:
                touched[(a.md_id, t)].add(a.item_id)

    rows = []
    for a in actions:
        if a.scope not in ITEM_SCOPES:
            why["scope_new_paragraph"] += 1
            continue
        if not a.md_id:
            why["not_exactly_one_linked_direction"] += 1
            continue
        eff = effective_date(amendments[a.item_id], a.start)
        if eff["date"] is None and eff["window"] is None:
            why[f"effective_{eff['basis']}"] += 1
            continue
        for t, pids in target_paragraphs(a, paras_by_md).items():
            if not pids:
                why["target_not_in_corpus"] += 1
                continue
            others = {i for (md, r), ids in touched.items() if md == a.md_id and (ref_covers(r, t) or ref_covers(t, r))
                      for i in ids} - {a.item_id}
            if others:
                why["path_touched_by_another_amendment"] += 1
                continue
            version = corpus_version(a, text_of[pids[0]], t)
            if version == "unclear":
                why["corpus_version_unclear"] += 1
                continue
            rows.append({"action_id": a.action_id, "item_id": a.item_id, "md_id": a.md_id, "target": t,
                         "paragraph_id": pids[0], "paragraphs_with_path": len(pids), "action": a.action,
                         "scope": a.scope, "effective": eff, "corpus_version": version,
                         "direction_issue_date": issue_date.get(a.md_id)})
    return rows, why


def gold_after(row: Mapping[str, Any]) -> str:
    return "deleted" if row["action"] == "delete" and row["scope"] == "paragraph_whole" else "amended"


def build_items(rows: Sequence[Mapping[str, Any]], *, n: int, seed: int, max_per_direction: int, today: str,
                max_days: int = 120) -> tuple[list[dict], dict[str, Any]]:
    """Paired items (one before, one after the effective date) per chosen target, seeded, <= max per Direction."""
    rng = random.Random(seed)
    today_d = _d(today)
    usable = []
    for r in rows:
        eff = r["effective"]
        start = _d(eff["date"]) if eff["date"] else _d(eff["window"][1])
        before_end = (_d(eff["date"]) if eff["date"] else _d(eff["window"][0])) - _dt.timedelta(days=1)
        lo = _d(r["direction_issue_date"]) if r.get("direction_issue_date") else before_end - _dt.timedelta(days=max_days)
        lo = max(lo, before_end - _dt.timedelta(days=max_days))
        after_hi = min(start + _dt.timedelta(days=max_days), today_d)
        if before_end < lo or after_hi < start:
            continue
        usable.append((r, (lo, before_end), (start, after_hi)))
    rng.shuffle(usable)
    per_md: Counter = Counter()
    seen_para: set[str] = set()
    items = []
    for r, (blo, bhi), (alo, ahi) in usable:
        if len(items) >= n or r["paragraph_id"] in seen_para or per_md[r["md_id"]] + 2 > max_per_direction:
            continue
        seen_para.add(r["paragraph_id"])
        per_md[r["md_id"]] += 2
        for side, (lo, hi) in (("before", (blo, bhi)), ("after", (alo, ahi))):
            as_of = lo + _dt.timedelta(days=rng.randint(0, (hi - lo).days))
            status = "in_force_original" if side == "before" else gold_after(r)
            items.append({
                "t3_id": f"T3-{len(items) + 1:03d}", "paragraph_id": r["paragraph_id"], "md_id": r["md_id"],
                "target_path": r["target"], "as_of": as_of.isoformat(), "side": side,
                "gold_status": status, "gold_governing_instrument": r["md_id"] if side == "before" else r["item_id"],
                "action_id": r["action_id"], "action": r["action"], "scope": r["scope"],
                "effective": r["effective"], "corpus_version": r["corpus_version"],
            })
    log = {"eligible_rows": len(rows), "usable_rows": len(usable), "items": len(items),
           "directions": len(per_md), "max_items_per_direction": max(per_md.values()) if per_md else 0,
           "sides": dict(Counter(i["side"] for i in items)), "gold": dict(Counter(i["gold_status"] for i in items)),
           "corpus_version": dict(Counter(i["corpus_version"] for i in items))}
    return items, log


# -- spot-check sheet ---------------------------------------------------------------------


def draw_spotcheck(actions: Sequence[Action], *, n: int, seed: int) -> list[Action]:
    """Stratified by action type (substitute / delete / insert), as even as the pools allow."""
    rng = random.Random(seed)
    pools = defaultdict(list)
    for a in sorted(actions, key=lambda x: x.action_id):
        pools[a.action].append(a)
    order = sorted(pools)
    quota = {k: 0 for k in order}
    while sum(quota.values()) < n:
        progressed = False
        for k in order:
            if sum(quota.values()) < n and quota[k] < len(pools[k]):
                quota[k] += 1
                progressed = True
        if not progressed:
            raise T3Error("not enough parsed actions for the spot-check")
    out = []
    for k in order:
        out += rng.sample(pools[k], quota[k])
    rng.shuffle(out)
    return out


def describe_action(a: Action) -> str:
    if a.scope == "paragraph_whole":
        return {"substitute": "substitute the whole paragraph", "delete": "delete the whole paragraph"}[a.action]
    if a.scope == "within_paragraph":
        if len(a.changes) > 1:
            n = Counter(c["verb"] for c in a.changes)
            parts = ", ".join(f"{v} {k}" for k, v in (("substitution(s)", n["substitute"]), ("deletion(s)", n["delete"]),
                                                     ("insertion(s)", n["insert"])) if v)
            return f"amend words within the paragraph ({parts})"
        return {"substitute": "substitute words within the paragraph", "delete": "delete words within the paragraph",
                "insert": "insert words / a clause within the paragraph"}[a.action]
    return "insert a new paragraph"


def sheet_rows(sample: Sequence[Action], amendments: Mapping[str, Mapping[str, Any]],
               titles: Mapping[str, str]) -> list[dict[str, str]]:
    rows = []
    for i, a in enumerate(sample, 1):
        eff = effective_date(amendments[a.item_id], a.start)
        eff_s = eff["date"] or (f"window: {eff['window'][0]} to {eff['window'][1]} (whichever earlier)"
                                if eff["window"] else f"unclear ({eff['basis']})")
        rows.append({"row_id": f"S{i:02d}", "amendment_id": a.item_id,
                     "direction": f"{a.md_id}: {titles.get(a.md_id or '', '')}" if a.md_id else "(more than one linked)",
                     "instruction_excerpt": a.instruction[-600:],
                     "commencement_excerpt": (eff.get("sentence") or "(none found)") + f" [published {amendments[a.item_id].get('published_date')}]",
                     "parsed_action": describe_action(a), "parsed_target": "paragraph " + ", ".join(a.targets),
                     "parsed_effective_date": eff_s, "correct": "", "note": ""})
    return rows


def sheet_csv(rows: Sequence[Mapping[str, str]]) -> str:
    buf = io.StringIO()
    buf.write('"' + SHEET_NOTE.replace('"', "'") + '"\n')
    w = csv.DictWriter(buf, fieldnames=SHEET_COLUMNS)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def read_sheet_text(text: str) -> list[dict[str, str]]:
    lines = text.splitlines(keepends=True)
    start = 0
    while start < len(lines) and lines[start].lstrip('"').startswith("#"):
        start += 1
    rows = list(csv.DictReader(io.StringIO("".join(lines[start:]))))
    if not rows or "row_id" not in rows[0]:
        raise T3Error("no row_id column found")
    return [{k: (v or "") for k, v in r.items() if k is not None} for r in rows]


def validate_sheet(completed: Sequence[Mapping[str, str]], blank: Sequence[Mapping[str, str]]) -> list[str]:
    problems = []
    ref = {r["row_id"]: r for r in blank}
    got = {r.get("row_id", "").strip(): r for r in completed}
    if set(got) != set(ref):
        problems.append(f"row ids differ: missing {sorted(set(ref) - set(got))}, extra {sorted(set(got) - set(ref))}")
    for rid in sorted(set(got) & set(ref)):
        for col in ("amendment_id", "parsed_action", "parsed_target", "parsed_effective_date"):
            if " ".join(got[rid].get(col, "").split()) != " ".join(ref[rid][col].split()):
                problems.append(f"{rid}: column {col} was edited")
        v = got[rid].get("correct", "").strip().lower()
        if v not in ("yes", "no"):
            problems.append(f"{rid}: correct must be yes or no, got {v!r}")
        if v == "no" and not got[rid].get("note", "").strip():
            problems.append(f"{rid}: correct = no needs a note saying what is wrong")
    return problems


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (centre - half, centre + half)
