"""Scoring V2 against V1 on the same units (milestone 2: dev only; the T1 comparison and bootstrap come at milestone 5).

- ``score``: V1's own ``comparator.evaluate`` (macro-F1, per label, ``different`` recall, confusion), plus ``none``
  precision, which shows whether alignment answers ``yes`` too readily.
- ``flips``: the units where V2 and V1 disagree, split by whether each side matches gold: fixed (V1 wrong, V2 right),
  broken (V1 right, V2 wrong) and other (both wrong). A score change is always reported with these counts.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from src.rag import comparator as CMP


def score(results: Sequence[Mapping[str, Any]], gold: Mapping[tuple[str, str], str]) -> dict[str, Any]:
    m = CMP.evaluate(results, gold)
    m["none_precision"] = m["per_label"]["none"]["precision"]
    return m


def flips(v1: Sequence[Mapping[str, Any]], v2: Sequence[Mapping[str, Any]],
          gold: Mapping[tuple[str, str], str]) -> dict[str, Any]:
    a = {(r["item_id"], r["target_class"]): r["judgement"] for r in v1}
    b = {(r["item_id"], r["target_class"]): r["judgement"] for r in v2}
    keys = sorted(k for k in a.keys() & b.keys() if k in gold)
    kinds, moves, units = Counter(), Counter(), []
    for k in keys:
        if a[k] == b[k]:
            continue
        kind = "fixed" if b[k] == gold[k] else "broken" if a[k] == gold[k] else "other"
        kinds[kind] += 1
        moves[f"{a[k]}->{b[k]}"] += 1
        units.append({"item_id": k[0], "target_class": k[1], "gold": gold[k], "v1": a[k], "v2": b[k], "kind": kind})
    return {"n_units": len(keys), "changed": len(units), "fixed": kinds["fixed"], "broken": kinds["broken"],
            "other": kinds["other"], "moves": dict(moves), "units": units}
