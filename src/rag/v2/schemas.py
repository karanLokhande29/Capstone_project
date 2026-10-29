"""V2 label vocabularies and result records.

- **Agent 1 (topic alignment):** per candidate, ``same_underlying_duty`` is ``yes`` / ``no`` / ``uncertain``, with five
  alignment dimensions and one quotation from each side.
- **Agent 3 (field verifier, milestone 3):** the four claim states are reserved here so every module shares them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DUTY_LABELS = ("yes", "no", "uncertain")
DIMENSIONS = ("actor", "action", "object", "regulated_activity", "purpose")
DIMENSION_LABELS = ("same", "different", "unclear")

CLAIM_STATES = ("supported", "contradicted", "insufficient_evidence", "uncertain")


@dataclass
class CandidateAlignment:
    """One candidate's alignment after validation.

    ``model_label`` is what the model said; ``same_underlying_duty`` is what downstream code may use. They differ only
    when validation failed (a quote not found, a bad dimension), which downgrades the label to ``uncertain``.
    """

    candidate_id: str
    same_underlying_duty: str
    model_label: str | None
    dimensions: dict[str, str] = field(default_factory=dict)
    source_evidence: str | None = None
    candidate_evidence: str | None = None
    evidence_ok: bool = False
    reason: str = ""
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def uncertain(candidate_id: str, problem: str) -> CandidateAlignment:
    """The fallback for a candidate the model's answer does not cover usably."""
    return CandidateAlignment(candidate_id=candidate_id, same_underlying_duty="uncertain", model_label=None,
                              problems=[problem])
