#!/usr/bin/env python3
"""P5-001 task 5: check everything git would publish (not the working directory).

    python3 scripts/release_check.py                 # tracked + untracked-but-not-ignored files
    python3 scripts/release_check.py --tracked-only  # only files already in the index (7a / 7c)
    python3 scripts/release_check.py --corpus <processed_dir>   # corpus for the copied-text check (default data/processed)

Fails (exit 1) on: an excluded path, a key-like string, a file over 50 MB, or a run of >= 30 consecutive words copied
from the corpus (hashed 12-word shingles; Direction titles allowed). Writes the result to reports/final/release_check.txt.
Without a corpus directory (e.g. in the public clone) the copied-text check cannot run and the result says so.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.release.check import scan  # noqa: E402
from src.release.rbi_text import CorpusIndex  # noqa: E402


def publishable(tracked_only: bool) -> list[str]:
    cmd = ["git", "-C", str(ROOT), "ls-files", "--cached"] + ([] if tracked_only else ["--others", "--exclude-standard"])
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted({p for p in out if (ROOT / p).is_file()})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tracked-only", action="store_true")
    ap.add_argument("--corpus", default=str(ROOT / "data" / "processed"))
    ap.add_argument("--out", default=str(ROOT / "reports" / "final" / "release_check.txt"))
    args = ap.parse_args()
    paths = publishable(args.tracked_only)
    corpus = Path(args.corpus)
    have_corpus = corpus.is_dir() and any(corpus.glob("md_*.jsonl"))
    index = CorpusIndex.from_processed(corpus) if have_corpus else CorpusIndex(set())
    mf = ROOT / "data" / "metadata" / "document_manifest.jsonl"
    titles = [json.loads(x).get("title") or "" for x in mf.read_text(encoding="utf-8").splitlines() if x.strip()] if mf.exists() else []
    files = [(p, (ROOT / p).stat().st_size, (lambda p=p: (ROOT / p).read_bytes())) for p in paths]
    problems = scan(files, index, titles)
    total = sum(s for _, s, _ in files)
    lines = [f"release_check: {len(paths)} publishable files ({total / 1e6:.1f} MB), "
             f"{'tracked only' if args.tracked_only else 'tracked + untracked not ignored'}",
             f"copied-text check: {'ON, ' + format(len(index.hashes), ',') + ' corpus shingles' if have_corpus else 'NOT RUN (no corpus directory)'}"]
    by_kind: dict[str, int] = {}
    for pr in problems:
        by_kind[pr.kind] = by_kind.get(pr.kind, 0) + 1
    lines.append("RESULT: " + ("PASS" if not problems else "FAIL " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items()))))
    lines += [f"  [{pr.kind}] {pr.path}: {pr.detail}" for pr in problems]
    text = "\n".join(lines) + "\n"
    print(text, end="")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
