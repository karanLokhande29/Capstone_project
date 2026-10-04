"""Shared helpers for the Command Center ingest and calibration (no LLM calls, no writes outside ui/).

- Comparator parsing: the 13-field extraction in a sealed comparator record's `raw`, plus the frozen rule's verdicts.
- Unit ids: `<item_id>|<class>`.
- The RBI word budget: at most 25 words of any paragraph across everything bundled, counted with the release check's
  tokeniser.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from src.rag import comparator_rule as RULE  # noqa: E402  (frozen; sha-checked in ingest)
from src.release.rbi_text import words as rbi_words  # noqa: E402

FIELDS = RULE.FIELDS
MATERIAL = RULE.MATERIAL
SYSTEMS_LLM = ("class_blind", "class_aware", "final_agentic", "ablation_a", "long_context")
RUNS = ROOT / "data/rag_runs"
CMP_GOLD = RUNS / "sealed_phase4/comparator_t1_gold_v1"
CMP_DEV = RUNS / "comparator_dev_irr30"
WORD_LIMIT = 25
EXCERPT_WORDS = 12


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def unit_id(item_id: str, cls: str) -> str:
    return f"{item_id}|{cls}"


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def comparator_records(directory: Path) -> dict[str, dict]:
    """unit id -> sealed comparator record."""
    out = {}
    for p in sorted(Path(directory).glob("t1_*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        out[unit_id(r["item_id"], r["target_class"])] = r
    return out


def parse_raw(rec: dict) -> dict | None:
    try:
        raw = json.loads(rec.get("raw") or "")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("candidates"), list):
        return None
    return raw


def comparator_signals(rec: dict) -> dict[str, Any]:
    """Comparator-intrinsic signals for one unit (used by calibration and the explorer)."""
    raw = parse_raw(rec)
    judgement = rec.get("judgement")
    out = {"judgement": judgement, "parse_ok": raw is not None and not rec.get("parse_problems"),
           "n_both": 0, "n_material_diff": 0, "hinge": False, "candidates_agree": False, "decisive_pid": None}
    if raw is None:
        return out
    cands = [c for c in raw["candidates"] if isinstance(c, dict)]
    verdicts = []
    for c in cands:
        try:
            verdicts.append(RULE.candidate_verdict(c))
        except (KeyError, TypeError):
            verdicts.append("unsure")
    out["candidates_agree"] = len(set(verdicts)) == 1 and len(verdicts) >= 2
    pid = rec.get("matched_paragraph_id") or (cands[0].get("paragraph_id") if cands else None)
    dec = next((c for c in cands if c.get("paragraph_id") == pid), cands[0] if cands else None)
    out["decisive_pid"] = pid
    if dec is None:
        return out
    src_f = raw.get("source", {}) or {}
    tgt_f = dec.get("fields", {}) or {}
    fc = dec.get("field_comparison", {}) or {}
    out["n_both"] = sum(1 for f in FIELDS if src_f.get(f) not in (None, "") and tgt_f.get(f) not in (None, ""))
    diffs = [f for f in FIELDS if fc.get(f) == "differs"] + [f for f in MATERIAL if fc.get(f) in ("only_source", "only_target")]
    out["n_material_diff"] = len(set(diffs))
    out["hinge"] = judgement == "different" and len(set(diffs)) == 1
    return out


def decisive_fields(rec: dict) -> dict[str, Any] | None:
    """Per-field statuses and raw values for the decisive candidate (values are trimmed later by the budget)."""
    raw = parse_raw(rec)
    if raw is None:
        return None
    cands = [c for c in raw["candidates"] if isinstance(c, dict)]
    pid = rec.get("matched_paragraph_id") or (cands[0].get("paragraph_id") if cands else None)
    dec = next((c for c in cands if c.get("paragraph_id") == pid), cands[0] if cands else None)
    if dec is None:
        return None
    src_f = raw.get("source", {}) or {}
    tgt_f = dec.get("fields", {}) or {}
    fc = dec.get("field_comparison", {}) or {}
    per_candidate = []
    for c in cands:
        try:
            v = RULE.candidate_verdict(c)
        except (KeyError, TypeError):
            v = "unsure"
        per_candidate.append({"pid": c.get("paragraph_id"), "verdict": v, "addressesSameDuty": bool(c.get("addresses_same_duty"))})
    return {"decisivePid": dec.get("paragraph_id"), "addressesSameDuty": bool(dec.get("addresses_same_duty")),
            "rows": [{"field": f, "status": fc.get(f, "absent"), "material": f in MATERIAL,
                      "source": src_f.get(f), "target": tgt_f.get(f)} for f in FIELDS],
            "perCandidate": per_candidate}


class WordBudget:
    """At most WORD_LIMIT release-check words per paragraph, across every bundled use."""

    def __init__(self, limit: int = WORD_LIMIT):
        self.limit = limit
        self.used: dict[str, int] = {}

    def take(self, pid: str, text: str | None, cap: int | None = None) -> str | None:
        if not text:
            return None
        left = self.limit - self.used.get(pid, 0)
        if cap is not None:
            left = min(left, cap)
        if left <= 0:
            return None
        out, n = [], 0
        toks = str(text).split()
        for t in toks:
            k = len(rbi_words(t))
            if n + k > left:
                break
            out.append(t)
            n += k
        if not out:
            return None
        self.used[pid] = self.used.get(pid, 0) + n
        s = " ".join(out)
        return s + ("…" if len(out) < len(toks) else "")


def iter_processed(pids: Iterable[str]) -> dict[str, dict]:
    """Paragraph records (text, clause path) for the requested ids, read from data/processed (local only)."""
    want: dict[str, set[str]] = {}
    for pid in pids:
        want.setdefault(pid.split("::")[0], set()).add(pid)
    out = {}
    for md, ids in want.items():
        p = ROOT / "data/processed" / f"{md}.jsonl"
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as h:
            for line in h:
                r = json.loads(line)
                if r["paragraph_id"] in ids:
                    out[r["paragraph_id"]] = {"text": r.get("text") or "", "clause_path": r.get("clause_path")}
    return out
