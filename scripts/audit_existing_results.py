#!/usr/bin/env python3
"""Existing-results audit (P1, light): the T2 / T2 ON-OFF / long-context / verifier / T3 / T4 numbers in the report
(§§8–9 and the T2–T4 limitations) against their metrics files. It also checks that the required disclosures are present.

    python3 scripts/audit_existing_results.py

Read-only. Writes reports/private/final_push/p1/existing_results_audit_<UTC>.md.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.release import stale_numbers as S  # noqa: E402

REPORT = ROOT / "reports/final/rbi_oblibench_report.md"
METRICS = {"p3001": "reports/p3001_metrics_v1.json", "p3002": "reports/p3002_metrics_v1.json",
           "p4001": "reports/p4001_metrics_v1.json", "results_v1": "reports/results_v1.json",
           "error_analysis_v1": "reports/final/error_analysis_v1.json"}
SECTIONS = ("## 8.1", "## 8.2", "## 8.3", "## 8.4", "## 8.5", "## 8.6", "# 9.", "**T2.**", "**T3.**", "**T4.**")
DISCLOSURES = {
    "T2 class-filter gain partly by construction": "partly by construction",
    "T2 relevance-set retriever bias": "biased towards one retriever",
    "T3 circularity": "circular by construction",
    "T3 old-words parser defect": "old words",
    "T3 corpus holds only amended text": "only amended text",
    "T4 concatenation verdict pre-registered": "pre-registered verdict",
    "T4 bad-question sensitivity": "flagged as bad",
    "T4 repair not usable": "not usable",
    "verifier/RePASs share an NLI model": "share an NLI model",
    "long-context 100K cap and unanswered items": "102 of 106",
    "150K run superseded": "150K",
}


def section_lines(text: str) -> list[tuple[int, str, str]]:
    out, cur = [], None
    for n, line in enumerate(text.splitlines(), start=1):
        if line.startswith("#") or line.startswith("**T"):
            cur = next((s for s in SECTIONS if line.startswith(s)), None if line.startswith("#") else cur)
        if cur:
            out.append((n, cur, line))
    return out


def main() -> int:
    text = REPORT.read_text(encoding="utf-8")
    idx = S.build_index({k: json.loads((ROOT / v).read_text()) for k, v in METRICS.items()})
    rows = []
    for n, sec, line in section_lines(text):
        for r in S.scan_text(line, idx)["rows"]:
            rows.append({**r, "line": n, "section": sec})
    by_sec: dict[str, dict[str, int]] = {}
    for r in rows:
        by_sec.setdefault(r["section"], {}).setdefault(r["status"], 0)
        by_sec[r["section"]][r["status"]] += 1
    found = {k: (v in text) for k, v in DISCLOSURES.items()}
    ea = json.loads((ROOT / METRICS["error_analysis_v1"]).read_text())["a_different_missed"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["# Existing-results audit (light) — report §§8–9 and T2–T4 limitations vs metrics files", "",
         f"Generated {stamp}. Sources: {', '.join(METRICS.values())}. Read-only.", "",
         "| Section | sourced | ambiguous | unsourced |", "|---|---|---|---|"]
    for s in SECTIONS:
        c = by_sec.get(s, {})
        L.append(f"| {s} | {c.get('sourced', 0)} | {c.get('ambiguous', 0)} | {c.get('unsourced', 0)} |")
    L += ["", "## Unsourced numbers (to check by hand)", ""]
    L += [f"- l.{r['line']} ({r['section']}) `{r['number']}`: {r['context'][:140]}" for r in rows if r["status"] == "unsourced"] or ["- none"]
    L += ["", "## Required disclosures present in the report", ""]
    L += [f"- {'yes' if ok else '**MISSING**'}: {k}" for k, ok in found.items()]
    L += ["", "## Definitions to state explicitly", "",
          f"- **'Missed by every LLM system'.** The report's {ea['missed_by_every_llm_system']}/{ea['gold_different_units']} "
          "(`scripts/build_error_analysis.py`) counts a unit only if **all five** LLM systems predicted it and none said "
          "`different`. The re-evaluation harness and taxonomy give 58/78 because they also count 2 units on the 4 items "
          "long-context never answered, where every system that answered missed. Both are correct under their own definitions; "
          "the targeted-experiment framing must name its count. Recommended: report 56 (all five predicted) and note 58 under "
          "the answered-only definition."]
    OUT = ROOT / "reports/private/final_push/p1"
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"existing_results_audit_{stamp}.md"
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"-> {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
