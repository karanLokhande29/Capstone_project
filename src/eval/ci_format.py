"""One rule for reading and printing confidence intervals in the P4 report and metrics JSON.

A CI excludes 0 iff its lower bound is > 0 ("excludes 0 (above)") or its upper bound is < 0 ("excludes 0 (below)").
Otherwise it does not exclude 0, including when a bound is exactly 0.

Numbers print to 3 decimals; a CI bound with |value| < 0.0005 (so it would print as ±0.000, exact zero included)
prints to 4 decimals.

(P3-002's T4 verdict is a separate, pre-registered rule, "reproduces" iff lower >= 0, and does not use this.)
"""

from __future__ import annotations

ABOVE, BELOW, NEITHER = "excludes 0 (above)", "excludes 0 (below)", "does not exclude 0"


def ci_reading(lo: float, hi: float) -> str:
    if lo > 0:
        return ABOVE
    if hi < 0:
        return BELOW
    return NEITHER


def excludes_zero(lo: float, hi: float) -> bool:
    return ci_reading(lo, hi) != NEITHER


def fmt_bound(x: float, *, signed: bool) -> str:
    d = 4 if abs(x) < 0.0005 else 3
    return f"{x:+.{d}f}" if signed else f"{x:.{d}f}"


def fmt_ci(point: float, lo: float, hi: float, *, signed: bool = False, reading: bool = False) -> str:
    p = f"{point:+.3f}" if signed else f"{point:.3f}"
    out = f"{p} [{fmt_bound(lo, signed=signed)}, {fmt_bound(hi, signed=signed)}]"
    return f"{out} ({ci_reading(lo, hi)})" if reading else out
