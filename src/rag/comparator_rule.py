"""Pairwise structured comparator: the deterministic decision rule (frozen by sha256 after the dev run; never edited after).

**Input:** the model's field-level answers for each candidate paragraph.

**Per-candidate verdict:**
- `none` if the candidate does not address the same duty;
- otherwise `different` if any field `differs`, or if a material field is stated on one side only;
- otherwise `same`.

**Class verdict:** the strongest per-candidate verdict, with `same` > `different` > `none` (the guidelines' `same`: the
class has the same obligation in substance in some shown paragraph). The matched paragraph is the first candidate with
that verdict.

**Failure:** an unreadable or incomplete answer gives `unsure`.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

RULE_VERSION = "comparator-rule-v1"
FIELDS = ("actor", "action", "object", "scope", "condition", "threshold", "amount", "percentage", "frequency",
          "deadline", "exception", "documentation", "reporting")
MATERIAL = ("actor", "scope", "condition", "threshold", "amount", "percentage", "frequency", "deadline", "exception",
            "documentation", "reporting")
COMPARISONS = ("equal", "differs", "only_source", "only_target", "absent")
PRECEDENCE = ("same", "different", "none")


def candidate_verdict(c: Mapping[str, Any]) -> str:
    if not c["addresses_same_duty"]:
        return "none"
    fc = c["field_comparison"]
    if any(fc[f] == "differs" for f in FIELDS):
        return "different"
    if any(fc[f] in ("only_source", "only_target") for f in MATERIAL):
        return "different"
    return "same"


def class_verdict(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    per = [(c["paragraph_id"], candidate_verdict(c)) for c in candidates]
    for v in PRECEDENCE:
        hit = next((pid for pid, x in per if x == v), None)
        if hit is not None:
            return {"judgement": v, "matched_paragraph_id": hit if v != "none" else None, "per_candidate": per,
                    "rule": RULE_VERSION}
    return {"judgement": "unsure", "matched_paragraph_id": None, "per_candidate": per, "rule": RULE_VERSION}
