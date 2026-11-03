"""`different` error taxonomy tooling and the retrieval-failure vs reasoning-failure separator (P1; final analysis Phase 4).

For every gold `different` class unit and every system:
- **Error type** (the predicted judgement): different→same, different→none, or unsure/missing.
- **Context:** was the gold matched paragraph in that system's context?
  - RAG systems: the paragraph ids shown in any attempt for that class (or class-blind `*`).
  - Long-context: the gold id appears in the rebuilt prompt, as P4-001 computed retention.
- **Failure type:** an error with the gold paragraph out of context is a *retrieval failure*; with it in context, a
  *reasoning failure*.
- **Candidate categories:** pre-tagged by deterministic cue differences between the source span and the gold counterpart.
  They are candidates for a human to confirm (the `final_category` column is left blank). They are never a label.

No model calls. Only T1 v1 errors are used, for a tooling dry run; the analysis is recomputed on gold v2 in Phase 4.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Callable, Iterable, Mapping, Sequence

CATEGORIES = ("thresholds", "amounts", "percentages", "scope", "actors", "timing", "deadlines", "frequency", "conditions",
              "exceptions", "reporting", "documentation", "additional obligations", "prohibition vs permission",
              "similar wording, different legal effect")

_NUM = r"\d+(?:[.,]\d+)*"
CUES: dict[str, re.Pattern] = {
    "percentages": re.compile(rf"{_NUM}\s*(?:%|per\s?cent)", re.I),
    "amounts": re.compile(rf"(?:₹|rs\.?|inr|usd|\$)\s*{_NUM}|{_NUM}\s*(?:crore|lakh|million|billion)", re.I),
    "deadlines": re.compile(rf"within\s+{_NUM}\s+\w+|not later than[^.;,]*|by\s+(?:the\s+)?(?:end|close)\s+of[^.;,]*|"
                            rf"before\s+the\s+[^.;,]*date|{_NUM}\s+(?:working\s+)?days?\s+(?:of|from|after|before)", re.I),
    "frequency": re.compile(r"\b(?:annual(?:ly)?|quarterly|monthly|half[- ]yearly|weekly|daily|fortnightly|"
                            r"at least once (?:a|in|every)\s+\w+|every\s+(?:year|quarter|month|week)|periodic(?:ally)?)\b", re.I),
    "timing": re.compile(r"\b(?:immediately|forthwith|promptly|in advance|prior to|before|after|at the time of|"
                         r"on or before|as soon as)\b", re.I),
    "thresholds": re.compile(rf"\b(?:exceed(?:ing|s)?|above|below|minimum|maximum|at least|not less than|not more than|"
                             rf"up to|upto|ceiling|limit|cap)\b[^.;]*?{_NUM}", re.I),
    "conditions": re.compile(r"\b(?:if|where|provided that|subject to|in case|in the event|when|unless otherwise)\b", re.I),
    "exceptions": re.compile(r"\b(?:except|unless|other than|notwithstanding|exempt(?:ed|ion)?|excluding|shall not apply)\b", re.I),
    "reporting": re.compile(r"\b(?:report(?:ed|ing)?|submit(?:ted)?|furnish(?:ed)?|inform(?:ed)?|notify|intimat\w+|"
                            r"disclos\w+|return(?:s)?)\b", re.I),
    "documentation": re.compile(r"\b(?:record(?:s|ed)?|maintain(?:ed)?|document(?:ed|ation)?|register|retain(?:ed)?|"
                                r"preserv\w+|policy|board[- ]approved)\b", re.I),
    "prohibition vs permission": re.compile(r"\b(?:shall not|must not|may not|prohibited|not permitted|not allowed|"
                                            r"shall be permitted|may|permitted|allowed)\b", re.I),
    "actors": re.compile(r"\b(?:board|chief executive|ceo|md|managing director|whole[- ]time director|compliance officer|"
                         r"principal officer|nodal officer|audit committee|statutory auditor|internal auditor|"
                         r"senior management|customer|borrower|rbi|reserve bank)\b", re.I),
}


def cue_set(text: str, cue: re.Pattern) -> set[str]:
    return {" ".join(m.group(0).lower().split()) for m in cue.finditer(text or "")}


def candidate_categories(source: str, target: str) -> list[str]:
    """Categories whose cues differ between the two texts (a candidate list for a human, not a label)."""
    out = []
    for cat, cue in CUES.items():
        a, b = cue_set(source, cue), cue_set(target, cue)
        if a != b and (a or b):
            out.append(cat)
    shalls = lambda t: len(re.findall(r"\bshall\b|\bmust\b", t or "", re.I))
    if shalls(target) > shalls(source) + 1:
        out.append("additional obligations")
    if not out:
        out.append("similar wording, different legal effect")
    return out


def context_ids_rag(steps: Sequence[Mapping[str, Any]] | None, cls: str) -> set[str]:
    ids: set[str] = set()
    for st in steps or []:
        shown = st.get("shown") or {}
        ids.update(shown.get(cls, []))
        ids.update(shown.get("*", []))
    return ids


def different_units(gold: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"item_id": g["item_id"], "target_class": c, "gold_matched": g["matched_paragraph_id"].get(c, ""),
             "source_span": g["obligation_span"]["text"]}
            for g in gold for c in sorted(g["compared_classes"]) if g["per_class_judgement"][c] == "different"]


def error_type(pred: str | None) -> str | None:
    if pred == "different":
        return None
    if pred == "same":
        return "different→same"
    if pred == "none":
        return "different→none"
    return "different→unsure/missing"


def analyse(units: Sequence[Mapping[str, Any]], runs: Mapping[str, Mapping[str, Mapping[str, Any]]],
            in_context: Callable[[str, Mapping[str, Any]], bool | None], text_of: Callable[[str], str]
            ) -> dict[str, Any]:
    """runs: system -> item_id -> run record ({'final': ..., 'steps': ...}); in_context(system, unit) -> bool | None."""
    rows = []
    for u in units:
        r = {**u, "candidate_categories": candidate_categories(u["source_span"], text_of(u["gold_matched"]) if u["gold_matched"] else ""),
             "final_category": "", "by_system": {}}
        for s, recs in runs.items():
            rec = recs.get(u["item_id"])
            if rec is None:
                r["by_system"][s] = {"pred": None, "error": "no prediction", "gold_in_context": None, "failure": None}
                continue
            pred = ((rec.get("final") or {}).get("per_class") or {}).get(u["target_class"], {}).get("judgement")
            et = error_type(pred)
            ctx = in_context(s, {**u, "record": rec})
            r["by_system"][s] = {"pred": pred, "error": et, "gold_in_context": ctx,
                                 "failure": None if et is None else ("unknown" if ctx is None else
                                                                     ("reasoning" if ctx else "retrieval"))}
        predicted = [v for v in r["by_system"].values() if v["error"] != "no prediction"]
        r["missed_by_every_system"] = bool(predicted) and all(v["error"] is not None for v in predicted)
        rows.append(r)
    summary = {}
    for s in runs:
        vals = [r["by_system"][s] for r in rows]
        errs = [v for v in vals if v["error"] and v["error"] != "no prediction"]
        summary[s] = {"gold_different_units": len(vals), "errors": len(errs),
                      "error_types": dict(Counter(v["error"] for v in errs)),
                      "failure_types": dict(Counter(v["failure"] for v in errs)),
                      "no_prediction": sum(1 for v in vals if v["error"] == "no prediction")}
    missed = [r for r in rows if r["missed_by_every_system"]]
    return {"units": rows, "per_system": summary, "missed_by_every_system": len(missed),
            "missed_by_every_system_candidate_categories": dict(Counter(c for r in missed for c in r["candidate_categories"])),
            "missed_by_every_system_reasoning_in_all_systems": sum(
                1 for r in missed if all(v["failure"] == "reasoning" for v in r["by_system"].values() if v["error"] != "no prediction"))}
