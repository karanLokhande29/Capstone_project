#!/usr/bin/env python3
"""The ui/dist grep test: no run of more than 25 consecutive words copied from the RBI corpus, no key-like string, the
Demo Build Spec §14 honesty grep, and no full-text endpoint in the public builds.

    python3 ui/scripts/check_dist.py          (cd ui && npm run check:dist)

Scans every text file in ui/dist (the built app) and ui/src/data (the bundled snapshot and model files) with the release
check's tokeniser and hashed shingles (src/release/rbi_text.py), using a stricter limit: 26+ words fails. Unlike the release check,
Direction titles get no allowance here. Exit 1 on any finding.
"""

from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from src.release.rbi_text import CorpusIndex, copied_runs  # noqa: E402

LIMIT = 25
KEY_PATTERNS = [re.compile(p) for p in (r"AIza[0-9A-Za-z_\-]{30,}", r"gsk_[0-9A-Za-z]{20,}", r"sk-[A-Za-z0-9]{32,}", r"ya29\.[0-9A-Za-z_\-]{20,}",
                                        r"-----BEGIN [A-Z ]*PRIVATE KEY-----")]
TEXT = {".js", ".css", ".html", ".json", ".svg", ".txt", ".md", ".map", ".ics"}
# §14.2 honesty grep (built sites only). "not a recommended threshold" is the required disclaimer, so it is allowed.
HONESTY = [re.compile(r"(?<!not a )recommended threshold", re.I), re.compile(r"optimal threshold", re.I), re.compile(r"checking threshold", re.I)]
FACT_CHECKER = re.compile(r"automatic fact-checker", re.I)
PUBLIC_DISTS = ("dist-azure", "dist-artifact")
# The local build's replay packs (sample and AI-assistant outputs, ui/dist/auditgen) carry RBI excerpts by design and never
# upload, so the RBI-text limit is not applied to them; the key and honesty checks still are. The Azure build ships capped copies.
LOCAL_ONLY_RBI_TEXT = ("dist/auditgen/",)
FULL_TEXT = re.compile(r"/api/rehydrate")
LOCAL_AUDIT = re.compile(r"[\"'`]/api/auditgen")  # a quoted same-origin path; the hosted service is an absolute URL


def files():
    for base in (UI / "dist", UI / "dist-artifact", UI / "dist-azure", UI / "src/data", UI / "public/data"):
        if base.exists():
            yield from (p for p in sorted(base.rglob("*")) if p.is_file() and (p.suffix in TEXT or p.name.endswith(".json.gz")))


def read(p: Path) -> str:
    if p.name.endswith(".gz"):
        return gzip.open(p, "rt", encoding="utf-8", errors="replace").read()
    return p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    corpus = ROOT / "data/processed"
    if not any(corpus.glob("md_*.jsonl")):
        print("check_dist: data/processed missing; cannot run the RBI-text check")
        return 1
    if not (UI / "dist").exists():
        print("check_dist: ui/dist missing; run `npm run build` first")
        return 1
    index = CorpusIndex.from_processed(corpus)
    problems = []
    n = 0
    for p in files():
        n += 1
        text = read(p)
        for pat in KEY_PATTERNS:
            if pat.search(text):
                problems.append(f"[key] {p.relative_to(UI)}: matches {pat.pattern}")
        rel = p.relative_to(UI)
        if rel.parts[0].startswith("dist"):
            for pat in HONESTY:
                for m in pat.finditer(text):
                    problems.append(f"[honesty] {rel}: “{text[max(0, m.start() - 30):m.end() + 10]}”")
            for m in FACT_CHECKER.finditer(text):
                if "Our first pipeline" not in text[max(0, m.start() - 80):m.start()]:
                    problems.append(f"[honesty] {rel}: “automatic fact-checker” without “Our first pipeline”")
            if rel.parts[0] in PUBLIC_DISTS and FULL_TEXT.search(text):
                problems.append(f"[full-text] {rel}: the public build references the full-text endpoint")
        if rel.as_posix().startswith(LOCAL_ONLY_RBI_TEXT):
            continue
        for run in copied_runs(text, index, min_words=LIMIT + 1):
            problems.append(f"[rbi_text] {p.relative_to(UI)}: {run.length} words: {run.excerpt[:80]}…")
    # Public builds never reference the local audit backend (a same-origin "/api/auditgen" path); the Azure build may call the
    # hosted service at its absolute URL (VITE_AUDIT_API). Only the Azure build ships the demo packs, which are the
    # 12-word-capped copies (scanned by the RBI-text check above like any other file); the Artifact build ships none.
    for d in PUBLIC_DISTS:
        base = UI / d
        if not base.exists():
            continue
        if d == "dist-artifact" and (base / "auditgen").exists():
            problems.append(f"[auditgen] {d}/auditgen/: replay packs must not ship in the Artifact build")
        for js in base.rglob("*.js"):
            if LOCAL_AUDIT.search(js.read_text(encoding="utf-8", errors="replace")):
                problems.append(f"[auditgen] {js.relative_to(UI)}: the public build references the local audit backend")
    print(f"check_dist: {n} files scanned in ui/dist + ui/src/data; corpus shingles {len(index.hashes):,}; limit {LIMIT} words")
    for pr in problems:
        print("  " + pr)
    print("RESULT:", "PASS" if not problems else f"FAIL ({len(problems)})")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
