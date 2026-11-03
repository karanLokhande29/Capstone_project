#!/usr/bin/env python3
"""Pointer/offset strategy check (P2; local, read-only, no network). It verifies:

1. every `release/data/paragraphs.jsonl` pointer: the sha256 and the char length of the local corpus paragraph match;
2. every T1 obligation span (validated + candidates):
   - its `paragraph_sha256` matches;
   - its offsets lie within the paragraph;
   - the `span_text` rule rebuilds a text whose sha256 equals `text_sha256`;
3. every file listed in `release/MANIFEST.json` matches its sha256.

    python3 scripts/check_release_pointers.py   -> reports/private/final_push/p2/pointer_check_v1.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.release.rebuild import span_text  # noqa: E402

sha = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> int:
    corpus = {}
    for p in sorted((ROOT / "data/processed").glob("md_*.jsonl")):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                r = json.loads(line)
                corpus[r["paragraph_id"]] = r["text"]
    res = {"paragraphs": {"n": 0, "missing": 0, "sha_mismatch": 0, "len_mismatch": 0}}
    for line in (ROOT / "release/data/paragraphs.jsonl").read_text().splitlines():
        r = json.loads(line)
        res["paragraphs"]["n"] += 1
        t = corpus.get(r["paragraph_id"])
        if t is None:
            res["paragraphs"]["missing"] += 1
        elif sha(t) != r["text_sha256"]:
            res["paragraphs"]["sha_mismatch"] += 1
        elif len(t) != r["chars"]:
            res["paragraphs"]["len_mismatch"] += 1
    for name in ("validated.jsonl", "candidates_part1.jsonl", "candidates_part2.jsonl"):
        c = {"n": 0, "paragraph_sha_mismatch": 0, "offsets_out_of_range": 0, "span_sha_mismatch": 0, "no_span_hash": 0}
        for line in (ROOT / "release/data/t1" / name).read_text().splitlines():
            r = json.loads(line)
            s = r.get("obligation_span") or {}
            c["n"] += 1
            t = corpus.get(s.get("paragraph_id"), "")
            if sha(t) != s.get("paragraph_sha256"):
                c["paragraph_sha_mismatch"] += 1
                continue
            if any(not (0 <= a <= b <= len(t)) for a, b in s.get("units", [])):
                c["offsets_out_of_range"] += 1
                continue
            if not s.get("text_sha256"):
                c["no_span_hash"] += 1
            elif sha(span_text(t, s["units"])) != s["text_sha256"]:
                c["span_sha_mismatch"] += 1
        res[f"t1/{name}"] = c
    man = json.loads((ROOT / "release/MANIFEST.json").read_text())
    bad = [k for k, v in man.items() if isinstance(v, dict) and "sha256" in v
           and hashlib.sha256((ROOT / "release" / k).read_bytes()).hexdigest() != v["sha256"]]
    res["manifest"] = {"files": sum(1 for v in man.values() if isinstance(v, dict) and "sha256" in v), "mismatch": bad}
    ok = (not any(res["paragraphs"][k] for k in ("missing", "sha_mismatch", "len_mismatch"))
          and not any(v for n in ("validated.jsonl", "candidates_part1.jsonl", "candidates_part2.jsonl")
                      for k, v in res[f"t1/{n}"].items() if k != "n")
          and not bad)
    res["PASS"] = ok
    out = ROOT / "reports/private/final_push/p2/pointer_check_v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
