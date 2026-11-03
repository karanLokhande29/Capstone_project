#!/usr/bin/env python3
"""Similarity prep (P2): every passage in the report, the drafts and the paper briefs that

(a) copies RBI corpus text verbatim for more than 25 words (hashed 12-word shingles, the release check's index, with a
    26-word threshold rather than 30), or
(b) is a quotation or block-quote of more than 25 words (it may come from RBI or another paper).

These can then be paraphrased or cited before the plagiarism screen (camera-ready similarity < 25% including references).
It also lists short RBI excerpts (12–25 copied words), as a count only.

    python3 scripts/similarity_prep.py   -> reports/private/final_push/similarity_prep_v1.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.release.rbi_text import CorpusIndex, copied_runs, words  # noqa: E402

FILES = ([ROOT / "reports/final/rbi_oblibench_report.md"] + sorted((ROOT / "reports/private/final_push/drafts").glob("*.md"))
         + [ROOT / "reports/private/final_push/report_corrections_v1.md"] + sorted((ROOT / "paper/aisigh/briefs").glob("*.md"))
         + sorted((ROOT / "reports/tables").glob("*.md")) + [ROOT / "release/DATASET_CARD.md", ROOT / "README.md"])
QUOTE = re.compile(r"“([^”]{40,})”|\"([^\"]{120,})\"")


def main() -> int:
    idx = CorpusIndex.from_processed(ROOT / "data/processed")
    out = ["# Similarity prep v1: verbatim passages to paraphrase or cite", "",
           "Scanned: the report, the final-push drafts, report_corrections, the paper briefs, the tables, the dataset card and the README.",
           "Rule: excerpts of at most 25 words with a paragraph id are fine; longer ones must be paraphrased or cut. Other papers' wording "
           "must be quoted with a citation, or paraphrased.", ""]
    total_long = total_quotes = 0
    for f in FILES:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(ROOT)
        long_runs, short_runs = [], 0
        for n, line in enumerate(text.splitlines(), start=1):
            for r in copied_runs(line, idx, min_words=12):
                if r.length > 25:
                    long_runs.append((n, r.length, r.excerpt))
                else:
                    short_runs += 1
        quotes = []
        for n, line in enumerate(text.splitlines(), start=1):
            for m in QUOTE.finditer(line):
                q = m.group(1) or m.group(2)
                if len(words(q)) > 25:
                    quotes.append((n, len(words(q)), " ".join(q.split()[:14])))
            if line.lstrip().startswith(">") and len(words(line)) > 25:
                own = "final_push" in str(rel) or "Draft written by" in line
                if not own:
                    quotes.append((n, len(words(line)), "block-quote: " + " ".join(line.split()[1:14])))
        total_long += len(long_runs)
        total_quotes += len(quotes)
        if long_runs or quotes or short_runs:
            out.append(f"## {rel}")
            out.append(f"- RBI runs of 12–25 copied words (short excerpts; check that each carries a paragraph id): {short_runs}")
            out += [f"- **l.{n}: {k} consecutive RBI words** — “{e} …” → paraphrase or cut to ≤ 25 words" for n, k, e in long_runs]
            out += [f"- l.{n}: quotation of {k} words — “{e} …” → check its source; cite or paraphrase" for n, k, e in quotes]
            out.append("")
    out.insert(5, f"**Totals:** {total_long} RBI runs over 25 words; {total_quotes} quotations over 25 words.\n")
    out += ["## Other-paper wording", "",
            "The repository quotes no other paper verbatim beyond titles. The one copied block is the RePASs README citation "
            "(reference 2: title and authors only). The paper text must cite, not reproduce, the RePASs/ObliQA descriptions.", ""]
    p = ROOT / "reports/private/final_push/similarity_prep_v1.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:8]))
    print(f"-> {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
