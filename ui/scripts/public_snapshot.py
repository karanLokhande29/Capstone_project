#!/usr/bin/env python3
"""Slim snapshot for the public pitch site: only what the five public pages read.

    python3 ui/scripts/public_snapshot.py   ->   ui/src/data/snapshot_public.json

Kept: meta, the (already redacted) results file, expert-agreement figures, freeze statuses, the benchmark items, the
comparator's saved answers with gold labels, field comparisons and paragraph pointers (≤ 25 words each).
Dropped: author-only material (gap list, paper sentences, submission checklist, venue notes, decisions, Master Document
text, Direction titles, matrix) and every system's answers except the comparator's.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "src/data"
EMPTY_LISTS = ("findings", "caveats", "paired", "ablations", "systems", "metrics", "constructionSteps", "decisions", "futureWork",
               "limitations", "submissionTasks", "gaps", "recommendations", "placeholders", "claims", "entityClasses",
               "subjectFamilies", "directions", "matrix", "masterSections", "changesV1", "guidelineRules", "rqs")


def main() -> int:
    s = json.loads((DATA / "snapshot.json").read_text(encoding="utf-8"))
    out = {k: [] for k in EMPTY_LISTS}
    out |= {
        "meta": {**s["meta"], "sources": [x for x in s["meta"]["sources"] if x["path"].startswith(("reports/results", "release/"))],
                 "partAStatus": [], "public": True},
        "results": s["results"],
        "reliability": [r for r in s["reliability"] if r["id"].startswith("fleiss")],
        "frozen": [{"path": f["path"], "status": f["status"], "expectedSha256": f["expectedSha256"], "actualSha256": f["actualSha256"],
                    "expectedSource": ""} for f in s["frozen"]],
        "frozenComparator": s["frozenComparator"],
        "t1Items": s["t1Items"],
        "classUnits": [{**u, "predictions": {"comparator": u["predictions"]["comparator"]}} for u in s["classUnits"]],
        "comparatorFields": s["comparatorFields"],
        "pointers": s["pointers"],
        "venue": {"file": "", "facts": [], "differences": [], "checked": ""},
        "diff": {"v1Sha": "", "v2Sha": "", "tablesNumericLeaves": 0, "changed": [], "removed": [], "added": [], "topLevelV1": [],
                 "topLevelV2": [], "newSections": [], "phase4Keys": []},
        "corpusMeta": {},
    }
    p = DATA / "snapshot_public.json"
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{p.name}: {p.stat().st_size / 1e6:.2f} MB (full snapshot {(DATA / 'snapshot.json').stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
