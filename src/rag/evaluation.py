"""P4-001 T1 scoring helpers: 3-way flag Macro-F1 (``ambiguous`` counted wrong), collapsed Macro-F1, coverage."""

from __future__ import annotations

from typing import Sequence

from src.eval.metrics import f1_scores

FLAGS = ("shared", "class-specific", "absent")


def flag_macro_f1(gold: Sequence[str], pred: Sequence[str]) -> float:
    """Macro-F1 over the three gold flags. A predicted ``ambiguous`` matches no gold label, so it is always
    a miss for that item's gold flag and never a hit for any label."""
    return f1_scores(list(gold), list(pred), FLAGS)["macro_f1"]


def collapse_flag(flag: str) -> str:
    return "absent" if flag == "absent" else ("ambiguous" if flag == "ambiguous" else "present")


def collapsed_macro_f1(gold: Sequence[str], pred: Sequence[str]) -> float:
    return f1_scores([collapse_flag(g) for g in gold], [collapse_flag(p) for p in pred], ("absent", "present"))["macro_f1"]


def coverage(pred_flags: Sequence[str]) -> float:
    """Share of items not abstained (a flag other than ``ambiguous``)."""
    return sum(1 for p in pred_flags if p != "ambiguous") / len(pred_flags) if len(pred_flags) else float("nan")
