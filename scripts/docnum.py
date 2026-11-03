"""Shared number rendering for the master document, the context dossier and the paper: every number is read by key
from a results bundle or metrics file; nothing is hand-typed. CIs print through src/eval/ci_format.py.

Source prefixes:
- R2  = reports/results_v2.json (it includes the v1 tables under `tables`);
- EA  = reports/final/error_analysis_v1.json;
- P4  = reports/p4001_metrics_v1.json;
- P3  = reports/p3002_metrics_v1.json;
- P31 = reports/p3001_metrics_v1.json;
- B   = reports/p2004_t1_benchmark_metrics_v1.json;
- RM  = reports/private/final_push/p2/reproducibility_manifest_v1.json;
- PV  = reports/private/final_push/t1_provenance_v2.json (the P2-004 retest gap record).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.ci_format import fmt_ci  # noqa: E402

FILES = {"R2": "reports/results_v2.json", "EA": "reports/final/error_analysis_v1.json", "P4": "reports/p4001_metrics_v1.json",
         "P3": "reports/p3002_metrics_v1.json", "P31": "reports/p3001_metrics_v1.json",
         "B": "reports/p2004_t1_benchmark_metrics_v1.json", "RM": "reports/private/final_push/p2/reproducibility_manifest_v1.json",
         "PV": "reports/private/final_push/t1_provenance_v2.json"}
_CACHE: dict[str, Any] = {}
USED: dict[str, set] = {}


def src(prefix: str) -> Any:
    if prefix not in _CACHE:
        _CACHE[prefix] = json.loads((ROOT / FILES[prefix]).read_text(encoding="utf-8"))
    return _CACHE[prefix]


def get(ref: str) -> Any:
    pre, key = ref.split(":", 1)
    v = src(pre)
    for k in key.split("."):
        if isinstance(v, list):
            v = v[int(k)]
        else:
            v = v[k]
    USED.setdefault(FILES[pre], set()).add(key)
    return v


def n(ref: str, fmt: str = "{:,}") -> str:
    """A plain number (count) — formatted with thousands separators by default."""
    v = get(ref)
    return fmt.format(v)


def f3(ref: str) -> str:
    return f"{get(ref):.3f}"


def pct(ref: str, d: int = 1) -> str:
    return f"{get(ref) * 100:.{d}f}%"


def ci(ref: str) -> str:
    """'x [lo, hi]' for value/ci, mean/ci_low/ci_high, kappa/bootstrap, rho; paired diffs get the reading."""
    v = get(ref)
    if "diff" in v:
        return fmt_ci(v["diff"], v["ci"][0], v["ci"][1], signed=True, reading=True)
    if "value" in v and "ci" in v:
        return fmt_ci(v["value"], v["ci"][0], v["ci"][1])
    if "kappa" in v:
        lo, hi = v["bootstrap"]["ci95"]
        return fmt_ci(v["kappa"], lo, hi)
    if "rho" in v:
        return fmt_ci(v["rho"], v["ci_low"], v["ci_high"])
    if "mean" in v and "ci_low" in v:
        signed = v["mean"] < 0 or "share_of_resamples_above_zero" in v
        return fmt_ci(v["mean"], v["ci_low"], v["ci_high"], signed=signed, reading=signed)
    raise KeyError(f"{ref}: no CI fields")


def kappa(ref: str) -> str:
    v = get(ref)
    lo, hi = v["bootstrap"]["ci95"]
    return f"{fmt_ci(v['kappa'], lo, hi)} (n = {v['n_items']} items, {v['n_units']} units)"


def wilson(ref: str) -> str:
    v = get(ref)
    lo, hi = v.get("wilson_95") or v.get("wilson95")
    rate = v.get("rate", v.get("value", v.get("precision")))
    return f"{v['k']}/{v['n']} = {rate:.3f} (Wilson 95% [{lo:.3f}, {hi:.3f}])"


def used_report() -> dict:
    return {k: sorted(v) for k, v in USED.items()}


def opt(ref: str, default: Any = 0) -> Any:
    try:
        return get(ref)
    except (KeyError, IndexError, TypeError):
        return default


def gap() -> str:
    """The P2-004 retest gap, file-level bounds in hours."""
    return f"{get('PV:existing_retest_gap.min_gap_hours'):.1f}–{get('PV:existing_retest_gap.max_gap_hours'):.1f} h"


def class_range(ref: str = "R2:tables.05_t1_benchmark.by_source_class") -> tuple[int, int]:
    v = [c["validated"] for c in get(ref).values()]
    return min(v), max(v)
