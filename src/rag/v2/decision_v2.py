"""V2 deterministic decision rule, milestone 2: the alignment override (system V2-A). Frozen with the V2 prompts.

**Inputs per unit:**
- V1's comparator record for the unit (dev run or sealed T1 run), re-parsed with V1's own parser: per candidate,
  ``addresses_same_duty`` and the 13-field ``field_comparison``;
- the Topic Alignment Agent's record for the same unit (``topic_aligner.align_unit``), or ``None`` if it has none.

**Per candidate, the duty flag is:**
- aligner ``yes`` → ``True``;
- aligner ``no`` → ``False``;
- aligner ``uncertain`` (including every validation downgrade), a candidate missing from the aligner record, or no
  aligner record → V1's own ``addresses_same_duty``.

**Then V1's rule applies unchanged** (``comparator_rule.candidate_verdict`` and ``class_verdict``, precedence
same > different > none) to the V1 fields with the new flag. Nothing else from V1 changes, so every difference from V1
traces to one aligner answer.

**Failure:** if V1's answer for the unit cannot be parsed, there are no fields to decide on, and the unit stays
``unsure`` as in V1. If re-parsing gives a judgement other than the one V1 stored, the record is refused: the V1 input
is not what was sealed.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.rag import comparator as CMP
from src.rag import comparator_rule as RULE

RULE_VERSION = "decision-rule-v2-a"


class DecisionError(ValueError):
    pass


def duty_flag(aligner_label: str | None, v1_flag: bool) -> tuple[bool, str]:
    """(flag, where it came from: ``aligner`` or ``v1``)."""
    if aligner_label == "yes":
        return True, "aligner"
    if aligner_label == "no":
        return False, "aligner"
    return v1_flag, "v1"


def v1_candidates(v1_record: Mapping[str, Any], candidate_ids: Sequence[str]) -> list[dict[str, Any]] | None:
    """V1's validated per-candidate answers, re-parsed from its raw text; ``None`` if V1 could not be parsed.

    Refuses a record whose stored judgement does not follow from its own raw answer under V1's rule.
    """
    parsed, _ = CMP.parse_response(v1_record.get("raw") or "", candidate_ids)
    stored = v1_record.get("judgement")
    again = RULE.class_verdict(parsed)["judgement"] if parsed else "unsure"
    if stored != again:
        raise DecisionError(f"{v1_record.get('item_id')} / {v1_record.get('target_class')}: V1 stored {stored!r} but "
                            f"its raw answer gives {again!r}")
    return parsed


def decide_a(v1_record: Mapping[str, Any], alignment: Mapping[str, Any] | None,
             candidate_ids: Sequence[str]) -> dict[str, Any]:
    """V2-A verdict for one unit, with a per-candidate trace."""
    key = (v1_record.get("item_id"), v1_record.get("target_class"))
    if alignment is not None and (alignment.get("item_id"), alignment.get("target_class")) != key:
        raise DecisionError(f"alignment record {alignment.get('item_id')} / {alignment.get('target_class')} "
                            f"is not for unit {key}")
    base = {"item_id": key[0], "target_class": key[1], "v1_judgement": v1_record.get("judgement"),
            "rule": RULE_VERSION, "v1_rule": RULE.RULE_VERSION, "parse_problems": list(v1_record.get("parse_problems") or [])}
    parsed = v1_candidates(v1_record, candidate_ids)
    if parsed is None:
        return {**base, "judgement": "unsure", "matched_paragraph_id": None, "per_candidate": [], "trace": [],
                "changed": False, "note": "V1 answer unparsed: no fields to decide on"}
    labels = {a["candidate_id"]: a["same_underlying_duty"] for a in (alignment or {}).get("alignments", [])}
    new, trace = [], []
    for c in parsed:
        pid = c["paragraph_id"]
        flag, src = duty_flag(labels.get(pid), c["addresses_same_duty"])
        new.append({**c, "addresses_same_duty": flag})
        trace.append({"candidate_id": pid, "aligner": labels.get(pid), "v1_duty": c["addresses_same_duty"],
                      "duty": flag, "duty_source": src, "v1_verdict": RULE.candidate_verdict(c),
                      "v2_verdict": RULE.candidate_verdict({**c, "addresses_same_duty": flag})})
    v = RULE.class_verdict(new)
    return {**base, "judgement": v["judgement"], "matched_paragraph_id": v["matched_paragraph_id"],
            "per_candidate": v["per_candidate"], "trace": trace, "changed": v["judgement"] != base["v1_judgement"]}
