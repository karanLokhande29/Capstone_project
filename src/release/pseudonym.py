"""Rater pseudonymisation for the public release (P5-001 task 4).

The real name -> rater-id mapping lives only in the gitignored ``reports/private/rater_map.json``
({"map": {name: rater_id}, "other_names": [...]}); nothing public holds it. Without that file the functions
are identity maps, so the public repo builds but cannot reproduce the private mapping.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_MAP = ROOT / "reports" / "private" / "rater_map.json"


def load_map(path: Path = PRIVATE_MAP) -> tuple[dict[str, str], list[str]]:
    if not path.exists():
        return {}, []
    d = json.loads(path.read_text(encoding="utf-8"))
    return {k.lower(): v for k, v in d["map"].items()}, [n.lower() for n in d.get("other_names", [])]


def _pattern(names) -> re.Pattern | None:
    names = sorted({n for n in names if n}, key=len, reverse=True)
    return re.compile(r"(?<![a-z])(" + "|".join(map(re.escape, names)) + r")(?![a-z])", re.IGNORECASE) if names else None


def name_pattern(mapping: Mapping[str, str], other_names=()) -> re.Pattern | None:
    return _pattern([*mapping, *other_names])


def pseudonymise_text(text: str, mapping: Mapping[str, str]) -> str:
    pat = _pattern(mapping)
    return pat.sub(lambda m: mapping[m.group(0).lower()], text) if pat else text


def pseudonymise_value(obj: Any, mapping: Mapping[str, str]) -> Any:
    """Replace every name, in keys and string values, recursively."""
    if isinstance(obj, str):
        return pseudonymise_text(obj, mapping)
    if isinstance(obj, list):
        return [pseudonymise_value(x, mapping) for x in obj]
    if isinstance(obj, dict):
        return {pseudonymise_text(k, mapping): pseudonymise_value(v, mapping) for k, v in obj.items()}
    return obj
