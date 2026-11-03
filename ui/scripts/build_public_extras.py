#!/usr/bin/env python3
"""Public-site data for the research pages and the read-only audit generator demo (Azure build only).

    python3 ui/scripts/build_public_extras.py      (run by `npm run build:azure`)

1. src/data/public_snapshot.json: the research snapshot without the authors' internal sections (submission tasks,
   gap list, recommendations, placeholders, venue notes, claim index, snapshot diff, master-document sections).
2. .public-auditgen/: the sample packs (one per entity class) and their recorded AI outputs from public/auditgen/, with
   every string that quotes the RBI corpus cut to its first 12 words (the public site's quote limit). Links to the RBI
   PDFs are kept. Each capped pack's exports (Excel, DOCX, PDF, ICS, JSON audit trail) go to exports/<pack_id>/, and
   their extracted text is checked for RBI runs longer than 12 words.

Both outputs are generated, git-ignored and checked again by scripts/check_dist.py after the build.
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from src.release.rbi_text import CorpusIndex, copied_runs  # noqa: E402

QUOTE_WORDS = 12
INTERNAL = {"submissionTasks": [], "gaps": [], "recommendations": [], "placeholders": [], "claims": [], "masterSections": [],
            "changesV1": [], "venue": {"file": "", "facts": [], "differences": [], "checked": ""}}


def public_snapshot() -> None:
    snap = json.loads((UI / "src/data/snapshot.json").read_text())
    for k, empty in INTERNAL.items():
        if k in snap:
            snap[k] = empty
    if isinstance(snap.get("diff"), dict):
        snap["diff"] = {k: ([] if isinstance(v, list) else v) for k, v in snap["diff"].items()}
    snap["meta"]["public"] = True
    (UI / "src/data/public_snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    print("public_snapshot.json written")


def cap(value, index: CorpusIndex, stats: dict):
    if isinstance(value, dict):
        return {k: cap(v, index, stats) for k, v in value.items()}
    if isinstance(value, list):
        return [cap(v, index, stats) for v in value]
    if isinstance(value, str) and any(copied_runs(value, index, min_words=QUOTE_WORDS + 1)):
        # Cut by whitespace words, then shorten further while the checker's tokeniser (which splits "2.1.3.i" into four
        # words) still finds a run longer than the limit.
        words = value.split()
        n = min(QUOTE_WORDS, len(words))
        while n > 1 and any(copied_runs(" ".join(words[:n]), index, min_words=QUOTE_WORDS + 1)):
            n -= 1
        stats["capped"] += 1
        return " ".join(words[:n]) + " …"
    return value


def public_auditgen() -> None:
    src, out = UI / "public/auditgen", UI / ".public-auditgen"
    if not (src / "index.json").exists():
        raise SystemExit("public/auditgen/index.json missing: run `python3 scripts/auditgen.py samples` first")
    index = CorpusIndex.from_processed(ROOT / "data/processed")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    for p in sorted(src.iterdir()):
        stats = {"capped": 0}
        if p.name.endswith(".json.gz"):
            data = cap(json.loads(gzip.open(p, "rt", encoding="utf-8").read()), index, stats)
            with gzip.open(out / p.name, "wt", encoding="utf-8", compresslevel=9) as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            exports(data, out / "exports" / data["pack_id"], index)
        elif p.suffix == ".json":
            data = cap(json.loads(p.read_text()), index, stats)
            (out / p.name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        else:
            continue
        print(f"{p.name}: {stats['capped']} strings cut to {QUOTE_WORDS} words")


def export_text(path: Path) -> str:
    if path.suffix == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True)
        return "\n".join(str(c) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for c in row if c is not None)
    if path.suffix == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n".join([p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells])
    if path.suffix == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path))
        return "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
    return path.read_text(encoding="utf-8")


def exports(pack: dict, directory: Path, index: CorpusIndex) -> None:
    from src.auditgen.exports import write_all

    for path in map(Path, write_all(pack, directory).values()):
        # Per line (one spreadsheet or table cell per line, PDF text lines), so neighbouring cells are not read as one run.
        bad = [r for line in export_text(path).splitlines() if len(line.split()) > QUOTE_WORDS
               for r in copied_runs(line, index, min_words=QUOTE_WORDS + 1)]
        if bad:
            raise SystemExit(f"{path}: {len(bad)} RBI runs longer than {QUOTE_WORDS} words, e.g. {bad[0].excerpt[:80]}")
    print(f"  exports for {pack['pack_id']}: {', '.join(p.name for p in sorted(directory.iterdir()))}")


if __name__ == "__main__":
    public_snapshot()
    public_auditgen()
