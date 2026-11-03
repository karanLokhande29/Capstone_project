#!/usr/bin/env python3
"""Stale-number scanner: every number in reports/final/*.md, the final-push drafts and reports/tables/*.md -> source key.

    python3 scripts/scan_stale_numbers.py [--extra-json path ...]

Writes reports/private/final_push/p1/stale_number_scan_<UTC>.{json,md}. Read-only on everything it scans.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.release import stale_numbers as S  # noqa: E402

OUT = ROOT / "reports/private/final_push/p1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra-json", nargs="*", default=[])
    a = ap.parse_args()
    sources = {"results_v1": json.loads((ROOT / "reports/results_v1.json").read_text()),
               "error_analysis_v1": json.loads((ROOT / "reports/final/error_analysis_v1.json").read_text())}
    for p in a.extra_json:
        sources[Path(p).stem] = json.loads(Path(p).read_text())
    idx = S.build_index(sources)
    files = (sorted((ROOT / "reports/final").glob("*.md")) + sorted((ROOT / "reports/private/final_push/drafts").glob("*.md"))
             + sorted((ROOT / "reports/tables").glob("*.md")))
    res = {str(f.relative_to(ROOT)): S.scan_text(f.read_text(encoding="utf-8"), idx) for f in files}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT.mkdir(parents=True, exist_ok=True)
    jp = OUT / f"stale_number_scan_{stamp}.json"
    jp.write_text(json.dumps({"sources": list(sources), "files": res}, indent=1, ensure_ascii=False) + "\n")
    L = ["# Stale-number scan", "", f"Sources: {', '.join(sources)}. Generated {stamp}.", "",
         "| File | numbers | sourced | ambiguous | unsourced |", "|---|---|---|---|---|"]
    for f, r in res.items():
        c = r["counts"]
        L.append(f"| {f} | {r['numbers']} | {c.get('sourced', 0)} | {c.get('ambiguous', 0)} | {c.get('unsourced', 0)} |")
    L += ["", "## Unsourced numbers in the report (first 80)", ""]
    rep = res.get("reports/final/rbi_oblibench_report.md", {"rows": []})
    for r in [x for x in rep["rows"] if x["status"] == "unsourced"][:80]:
        L.append(f"- l.{r['line']} `{r['number']}` — {r['context']}")
    mp = OUT / f"stale_number_scan_{stamp}.md"
    mp.write_text("\n".join(L) + "\n")
    print("\n".join(L[:6 + len(res)]))
    print(f"-> {jp.relative_to(ROOT)}\n-> {mp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
