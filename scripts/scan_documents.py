#!/usr/bin/env python3
"""Stale-number scan for the master document, the paper (main.tex + tables) and the context dossier.

Sources:
- every file in scripts/docnum.FILES;
- a dossier facts file, if present;
- the bibliography's own numbers (years, pages, volumes, ids — fixed constants);
- `reports/private/final_push/master/doc_constants_v1.json` (named fixed constants, each with its reason).

    python3 scripts/scan_documents.py [files...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import docnum as D  # noqa: E402
from src.release import stale_numbers as S  # noqa: E402

CONSTANTS = ROOT / "reports/private/final_push/master/doc_constants_v1.json"
FACTS = ROOT / "reports/private/final_push/master/dossier_facts_v1.json"
DEFAULT = ["reports/final/RBI-ObliBench_Master_Document_v2.md", "paper/aisigh/main.tex", *sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "paper/aisigh/tables").glob("tab_*.tex"))]


def sources() -> dict:
    src = {k: json.loads((ROOT / v).read_text(encoding="utf-8")) for k, v in D.FILES.items()}
    bib = (ROOT / "paper/aisigh/refs_verified.bib").read_text(encoding="utf-8")
    src["bib"] = {"numbers": [t for t in re.findall(r"\d[\d.]*", bib)]}
    if CONSTANTS.exists():
        src["constants"] = json.loads(CONSTANTS.read_text(encoding="utf-8"))
    if FACTS.exists():
        src["facts"] = json.loads(FACTS.read_text(encoding="utf-8"))
    return src


def main() -> int:
    files = sys.argv[1:] or DEFAULT
    idx = S.build_index(sources())
    total, out = 0, {}
    for f in files:
        p = ROOT / f
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".tex":
            text = re.sub(r"(?m)%.*$", "", text)  # comments are not rendered
            text = re.sub(r"\\(?:label|ref|cite|input|includegraphics|bibliography\w*|documentclass|usepackage)(\[[^\]]*\])?\{[^}]*\}", " ", text)
        res = S.scan_text(text, idx)
        un = [r for r in res["rows"] if r["status"] == "unsourced"]
        total += len(un)
        out[f] = {"numbers": res["numbers"], "counts": res["counts"], "unsourced": un}
        print(f"{f}: {res['numbers']} numbers; {res['counts']}")
        for r in un[:40]:
            print(f"   UNSOURCED l.{r['line']} `{r['number']}`: {r['context'][:110]}")
    rep = ROOT / "reports/private/scratch/scan_documents_last.json"
    rep.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"TOTAL unsourced: {total}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
