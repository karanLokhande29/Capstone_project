"""Stale-number scanner (Phase 5 support): map every number in the report, the drafts and the tables to a source key.

**Sources:** keys in the results bundle (`reports/results_v1.json` and `reports/final/error_analysis_v1.json`, plus any
JSON passed in). A number is **sourced** if some numeric leaf formats to it, in one of the forms the report uses:
- 3 or 4 decimals;
- rounded to 1–2 decimals;
- an integer, with or without thousands separators;
- a percentage of a rate;
- the magnitude of a negative value;
- a number inside a preformatted string leaf (e.g. "-0.049 [-0.133, +0.036]").

**Excluded as structural:** dates, paragraph ids (`md_…::p…`), versions (`v3.1`), section, table and figure numbers,
and `{{placeholders}}`.

**Output, per number:** `sourced` (with up to 3 keys), `ambiguous` (more than 20 keys share the value), or `unsourced`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable, Mapping

NUM_RE = re.compile(r"(?<![\w.\-:/])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![\w:])")
STRUCTURAL = [
    re.compile(r"^\s*#+\s*\d+(?:\.\d+)*"),
    re.compile(r"\{\{[^}]*\}\}"),
    re.compile(r"md_\d+(?:::p\d+)?|t1_\w+::p\d+|T4Q\d+|T3-\d+|amd_\d+"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ][\d:]+Z?)?"),
    re.compile(r"\bv\d+(?:\.\d+)*\b"),
    re.compile(r"(?:§|Section |Table |Figure |Fig\. |Appendix |task |Task |P\d-)\s?\d+(?:\.\d+)*", re.I),
    re.compile(r"\b[0-9a-f]{8,}\b"),
    re.compile(r"\bD\d+\b|\brater_\d\b|\bQ\d\b"),
]


def flatten(obj: Any, prefix: str = "") -> Iterable[tuple[str, float]]:
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, f"{prefix}[{i}]")
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield prefix, float(obj)
    elif isinstance(obj, str) and len(obj) < 400:
        for j, tok in enumerate(NUM_RE.findall(obj)):
            try:
                yield f"{prefix}<str#{j}>", float(tok.replace(",", "").replace("−", "-").rstrip("%"))
            except ValueError:
                continue


def renderings(v: float) -> set[str]:
    out = set()
    for d in (0, 1, 2, 3, 4):
        s = f"{v:.{d}f}"
        out.add(s)
        if d == 0 and abs(v) >= 1000:
            out.add(f"{v:,.0f}")
    if float(v).is_integer():
        out.add(str(int(v)))
    else:
        out.add(f"{v:g}")  # the value exactly as stored (e.g. a threshold of 0.757567)
    if 0 <= v <= 1:
        for d in (0, 1):
            out.add(f"{v * 100:.{d}f}%")
    if v < 0:
        out |= renderings(-v)  # prose often states a negative difference as a positive magnitude ("lowers by 0.217")
    return {s.lstrip("+") for s in out}


def build_index(sources: Mapping[str, Any]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = defaultdict(list)
    for name, obj in sources.items():
        for key, v in flatten(obj):
            for r in renderings(v):
                idx[r].append(f"{name}:{key}")
    return idx


def numbers_in(line: str) -> list[str]:
    masked = line
    for pat in STRUCTURAL:
        masked = pat.sub(lambda m: " " * len(m.group(0)), masked)
    return [m.group(0).replace("−", "-") for m in NUM_RE.finditer(masked)]


def scan_text(text: str, idx: Mapping[str, list[str]], *, ambiguous_over: int = 20) -> dict[str, Any]:
    rows = []
    for ln, line in enumerate(text.splitlines(), start=1):
        for tok in numbers_in(line):
            key = tok.lstrip("+")
            keys = idx.get(key, [])
            if not keys and key.endswith("%"):
                keys = idx.get(key[:-1], [])
            status = "unsourced" if not keys else ("ambiguous" if len(keys) > ambiguous_over else "sourced")
            rows.append({"line": ln, "number": tok, "status": status, "keys": keys[:3], "n_keys": len(keys),
                         "context": line.strip()[:160]})
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    return {"numbers": len(rows), "counts": dict(counts), "rows": rows}
