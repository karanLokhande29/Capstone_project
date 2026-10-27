"""Entity profile: class, activity flags, as-of and last-review dates, optional group entities."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

ACTIVITIES = ("deposits", "lending", "digital_lending", "forex", "payments", "priority_sector", "co_lending",
              "outsourcing", "kyc_aml", "it_cyber")
ACTIVITY_LABELS = {"deposits": "Deposits", "lending": "Lending", "digital_lending": "Digital lending", "forex": "Forex",
                   "payments": "Payments", "priority_sector": "Priority-sector lending", "co_lending": "Co-lending",
                   "outsourcing": "Outsourcing", "kyc_aml": "KYC / AML", "it_cyber": "IT / cyber"}


class ProfileError(ValueError):
    pass


@dataclass
class Profile:
    name: str
    entity_class: str
    as_of: str
    last_review: str
    activities: list[str] = field(default_factory=list)
    group_classes: list[str] = field(default_factory=list)

    def validate(self, core_classes: Sequence[str]) -> "Profile":
        problems = []
        if not str(self.name or "").strip():
            problems.append("name is empty")
        if self.entity_class not in core_classes:
            problems.append(f"entity_class {self.entity_class!r} is not one of the {len(core_classes)} core classes")
        for a in self.activities:
            if a not in ACTIVITIES:
                problems.append(f"unknown activity {a!r}")
        for g in self.group_classes:
            if g not in core_classes:
                problems.append(f"group class {g!r} is not a core class")
        try:
            a, r = date.fromisoformat(self.as_of), date.fromisoformat(self.last_review)
            if r > a:
                problems.append("last_review is after as_of")
        except (TypeError, ValueError):
            problems.append("as_of and last_review must be ISO dates (YYYY-MM-DD)")
        if problems:
            raise ProfileError("; ".join(problems))
        self.activities = sorted(set(self.activities), key=ACTIVITIES.index)
        self.group_classes = sorted(set(self.group_classes) - {self.entity_class})
        return self

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Profile":
        known = {"name", "entity_class", "as_of", "last_review", "activities", "group_classes"}
        extra = set(d) - known
        if extra:
            raise ProfileError(f"unknown profile fields: {sorted(extra)}")
        return cls(name=d.get("name", ""), entity_class=d.get("entity_class", ""), as_of=d.get("as_of", ""),
                   last_review=d.get("last_review", ""), activities=list(d.get("activities") or []),
                   group_classes=list(d.get("group_classes") or []))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.as_dict(), indent=1))

    @classmethod
    def load(cls, path: Path) -> "Profile":
        return cls.from_dict(json.loads(path.read_text()))
