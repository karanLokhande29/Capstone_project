"""Research-integrity guard: the audit generator reads research artefacts and must never change them.

``snapshot()`` hashes every research file; ``compare()`` reports files that were modified or deleted since a snapshot.
Live annotation collection folders (the sprint inbox, packets, frozen copies, receipts and supervision logs) are
excluded because they legitimately receive files during a rating round; everything else under the roots is covered.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ROOTS = ("data/processed", "data/benchmark", "data/metadata", "data/supplementary", "data/rag_runs",
                  "data/indexes", "data/matrix", "data/llm_cache", "configs", "reports", "docs/protocol", "paper")
LIVE_COLLECTION = ("data/benchmark/t1/sprint_", "data/benchmark/sprint_supervision",
                   # Regenerated on every run of scripts/release_check.py (a required final check), not research data.
                   "reports/final/release_check.txt",
                   # Daily LLM usage counter, rewritten by src/llm/client.py on every API call, not research data.
                   "data/llm_cache/quota_ledger.json")
SNAPSHOT = ROOT / "data/auditgen_state/research_hashes_before.json"


def _files(root: Path = ROOT) -> Iterable[Path]:
    for r in RESEARCH_ROOTS:
        base = root / r
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(root).as_posix()
            if p.is_file() and p.name != ".DS_Store" and not rel.startswith(LIVE_COLLECTION) and "/__pycache__/" not in rel:
                yield p


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: Path = ROOT) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in _files(root)}


def compare(before: dict[str, str], root: Path = ROOT) -> dict[str, list[str]]:
    changed, deleted = [], []
    for rel, h in before.items():
        p = root / rel
        if not p.exists():
            deleted.append(rel)
        elif sha256_file(p) != h:
            changed.append(rel)
    return {"changed": changed, "deleted": deleted}


def added(before: dict[str, str], root: Path = ROOT) -> list[str]:
    """Files or directories that appeared under a research root since the snapshot (live collection excluded)."""
    known_dirs = {Path(k).parent.as_posix() for k in before}
    since = SNAPSHOT.stat().st_mtime if SNAPSHOT.exists() else 0.0
    out = []
    for r in RESEARCH_ROOTS:
        base = root / r
        if not base.exists():
            continue
        for p in base.rglob("*"):
            rel = p.relative_to(root).as_posix()
            if p.name == ".DS_Store" or rel.startswith(LIVE_COLLECTION) or "__pycache__" in rel:
                continue
            new_dir = p.is_dir() and p.stat().st_ctime > since and not any(k == rel or k.startswith(rel + "/") for k in known_dirs)
            if (p.is_file() and rel not in before) or new_dir:
                out.append(rel)
    return sorted(out)


def write_snapshot(path: Path = SNAPSHOT) -> int:
    snap = snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"files": snap}, indent=0))
    return len(snap)
