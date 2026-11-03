#!/usr/bin/env python3
"""Gold-version-aware T1 re-evaluation (no model calls).

    python3 scripts/run_t1_reeval.py score --gold data/benchmark/t1/t1_validated_v1.jsonl [--check-v1]
    python3 scripts/run_t1_reeval.py missing --ids rejected      # predictions a gold v2 would lack, + call estimate

Writes to reports/private/final_push/reeval/ (never overwrites).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.config import load_config  # noqa: E402
from src.eval import t1_regold as G  # noqa: E402

T1 = ROOT / "data/benchmark/t1"
RUNS = ROOT / "data/rag_runs"
OUT = ROOT / "reports/private/final_push/reeval"


def _write(name: str, obj) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    if p.exists():
        raise SystemExit(f"STOP: {p} exists")
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def _cands(need: set[str]) -> dict:
    out = {}
    with (T1 / "t1_candidate_benchmark_v1.jsonl").open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            if r["source_candidate_id"] in need:
                out[r["source_candidate_id"]] = r
    return out


def cmd_score(a) -> int:
    cfg = load_config(None)
    R, seed = int(cfg["retrieval"]["eval"]["bootstrap_resamples"]), int(cfg["p4"]["seeds"]["bootstrap"])
    gold = G.read_jsonl(Path(a.gold))
    res = G.evaluate(gold, _cands({g["source_candidate_id"] for g in gold}), RUNS, resamples=R, seed=seed)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {"gold": str(Path(a.gold).resolve().relative_to(ROOT)), "gold_sha256": G.__dict__.get("_sha", None) or
           __import__("hashlib").sha256(Path(a.gold).read_bytes()).hexdigest(), "resamples": R, "seed": seed, "t1": res}
    if a.check_v1:
        ref = json.loads((ROOT / "reports/p4001_metrics_v1.json").read_text())["t1"]
        same = lambda x, y: json.dumps(x, sort_keys=True) == json.dumps(y, sort_keys=True)
        out["regression_vs_p4001"] = {
            "systems": all(same(res["systems"][s], ref["systems"][s]) for s in ref["systems"]),
            "paired": all(same(res["paired"][k], ref["paired"][k]) for k in ref["paired"]),
            "long_context_same_items": all(same(res["long_context_same_items"]["systems"][s], v)
                                           for s, v in ref["long_context_same_items"]["systems"].items()),
            "appendix_150k": same(res["appendix_150k"]["systems"], ref["appendix_150k"]["systems"])}
        print("regression vs p4001_metrics_v1.json:", out["regression_vs_p4001"])
    p = _write(f"reeval_{Path(a.gold).stem}_{stamp}.json", out)
    for s, v in res["systems"].items():
        print(f"  {s:18s} n={v['n_items']:3d}  3-way {G.fmt_metric(v['flag_macro_f1'])}  collapsed {G.fmt_metric(v['collapsed_macro_f1'])}"
              f"  different F1 {res['different'][s]['different_f1']}")
    print(f"  missed by every LLM system: {res['missed_by_every_llm_system']}")
    print(f"-> {p.relative_to(ROOT)}")
    return 0


def cmd_missing(a) -> int:
    sample = [json.loads(l)["item_id"] for l in (T1 / "p2004_sample_v1.jsonl").read_text().splitlines() if l.strip()]
    kept = {json.loads(l)["item_id"] for l in (T1 / "t1_validated_v1.jsonl").read_text().splitlines() if l.strip()}
    ids = sorted(set(sample) - kept) if a.ids == "rejected" else sorted(sample)
    res = G.missing_predictions([{"item_id": i} for i in ids], RUNS)
    cfg = load_config(None)
    out = {"scenario": f"gold v2 includes the {a.ids} items ({len(ids)})", "model": cfg["llm"].get("p4_model"),
           "prompts": "configs/p4_prompts_v1 (frozen)", "per_system": res,
           "total_estimated_calls_at_mean": round(sum((v["estimated_calls_needed"]["at_mean"] or 0) for v in res.values()), 1)}
    p = _write(f"missing_predictions_{a.ids}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json", out)
    for s, v in res.items():
        print(f"  {s:14s} missing {v['n_missing']:3d}; calls/item mean {v['observed_calls_per_item']['mean']}; "
              f"estimated calls {v['estimated_calls_needed']}")
    print(f"  total (at mean): {out['total_estimated_calls_at_mean']} calls on {out['model']}; no call made")
    print(f"-> {p.relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--gold", required=True)
    s.add_argument("--check-v1", action="store_true")
    m = sub.add_parser("missing")
    m.add_argument("--ids", choices=("rejected", "sample"), default="rejected")
    a = ap.parse_args()
    return cmd_score(a) if a.cmd == "score" else cmd_missing(a)


if __name__ == "__main__":
    raise SystemExit(main())
