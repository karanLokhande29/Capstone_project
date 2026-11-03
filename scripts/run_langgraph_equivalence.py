#!/usr/bin/env python3
"""Extension #9 equivalence test (Amendments 5 and 6): LangGraph port vs the original P4 T1 pipeline.

    external/.venv-langgraph313/bin/python scripts/run_langgraph_equivalence.py [--systems final_agentic ...]

For every T1 gold item (106) and every RAG system, both implementations run in this process against the response
cache only: no key is loaded (a dummy value builds the provider), cache misses raise, and nothing is appended to the
call log. Pass criteria (pre-registered): byte-identical prompts, every response from the cache (0 calls), identical
outputs on all 106 items. The original outputs are also compared with the sealed run files in data/rag_runs/t1_<system>.
Writes reports/private/final_push/extensions/sprint/ext9_langgraph.{json,md}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "reports/private/final_push/extensions/sprint"


class Recorder:
    """Wraps the cache-only client and records every prompt it is asked."""

    def __init__(self, client):
        self.client, self.prompts = client, []

    def complete(self, messages, **kw):
        self.prompts.append(json.dumps(messages, ensure_ascii=False, sort_keys=True))
        return self.client.complete(messages, **kw)


def strip_volatile(log: dict) -> dict:
    return json.loads(json.dumps(log, ensure_ascii=False, sort_keys=True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="*", default=["final_agentic", "class_aware", "class_blind", "ablation_a"])
    args = ap.parse_args()
    os.environ["GEMINI_API_KEY"] = "cache-only-harness-no-key"  # never a real key: misses raise, nothing is sent
    import run_p4 as R
    from importlib.metadata import version
    from src.common.config import load_config
    from src.common.paths import PathResolver
    from src.llm import client as L
    from src.rag import graph_t1 as G
    from src.rag import pipeline as PL

    from run_sealed_predictions import _offline_pinned_model_loader

    _offline_pinned_model_loader()  # pinned models from the local cache by commit; no network
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    t0 = time.time()
    res, _extra = R.load_resources(cfg, resolver)
    verifier = R.load_verifier(cfg)
    prompts = R.load_prompts(cfg)
    p4 = cfg["p4"]
    client = L.build_client(cfg, resolver, run_id="ext9_langgraph_equivalence", env_file=ROOT / ".no-env-file",
                            model=str(cfg["llm"]["p4_model"]), long_context_model=str(cfg["llm"]["p4_model"]),
                            rpm=int(p4["rpm"]), tpm=int(p4["tpm"]), verify_models=False,
                            extra_params={"json": bool(p4["json_mode"]), "thinking": p4.get("thinking")})
    client.cache_only = True
    client.call_log_path = None  # do not append cache hits to logs/llm_calls.jsonl
    client.max_calls = 0
    items = R._items(resolver)
    report = {"python": sys.version.split()[0], "platform": platform.platform(), "langgraph": version("langgraph"),
              "items": len(items), "systems": {}, "load_seconds": round(time.time() - t0, 1)}
    all_ok = True
    for system in args.systems:
        scfg = R.SYSTEMS[system]
        scfg.per_class = int(p4["retrieval"]["t1_per_class"])
        scfg.depth = int(p4["retrieval"]["depth"])
        scfg.max_output_tokens = int(p4["max_output_tokens"])
        ver = verifier if scfg.verifier else None
        orig_llm, graph_llm = Recorder(client), Recorder(client)
        graph = G.build_t1_graph(res, prompts, graph_llm, ver, scfg)
        s = {"items": 0, "prompts_identical": 0, "outputs_identical": 0, "sealed_final_identical": 0, "cache_misses": 0,
             "mismatches": []}
        t1 = time.time()
        for it in items:
            n0, m0 = len(orig_llm.prompts), len(graph_llm.prompts)
            try:
                a = PL.run_t1_item(res, prompts, orig_llm, ver, it, scfg)
                b = G.run_t1_item_graph(graph, it)
            except L.CacheMiss:
                s["cache_misses"] += 1
                s["mismatches"].append({"item": it["item_id"], "why": "cache miss"})
                continue
            s["items"] += 1
            pa, pb = orig_llm.prompts[n0:], graph_llm.prompts[m0:]
            same_p = pa == pb
            same_o = strip_volatile(a) == strip_volatile(b)
            s["prompts_identical"] += same_p
            s["outputs_identical"] += same_o
            sealed_path = ROOT / "data/rag_runs" / f"t1_{system}" / f"{R._safe(it['item_id'])}.json"
            sealed = json.loads(sealed_path.read_text()) if sealed_path.exists() else None
            same_sealed = bool(sealed) and strip_volatile(sealed["final"]) == strip_volatile(b["final"])
            s["sealed_final_identical"] += same_sealed
            if not (same_p and same_o and same_sealed):
                s["mismatches"].append({"item": it["item_id"], "prompts": same_p, "outputs": same_o, "sealed_final": same_sealed})
        s["prompt_sha256_graph"] = hashlib.sha256("\n".join(graph_llm.prompts).encode()).hexdigest()
        s["prompt_sha256_original"] = hashlib.sha256("\n".join(orig_llm.prompts).encode()).hexdigest()
        s["llm_prompts"] = len(graph_llm.prompts)
        s["seconds"] = round(time.time() - t1, 1)
        s["pass"] = s["items"] == len(items) and s["prompts_identical"] == s["outputs_identical"] == len(items)
        all_ok &= s["pass"]
        report["systems"][system] = s
        print(f"{system}: items {s['items']}/{len(items)} · prompts identical {s['prompts_identical']} · outputs identical "
              f"{s['outputs_identical']} · sealed final identical {s['sealed_final_identical']} · cache misses {s['cache_misses']} · "
              f"{'PASS' if s['pass'] else 'FAIL'}", flush=True)
    report["api_calls"] = client.run.summary().get("api_calls")
    report["pass"] = all_ok
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ext9_langgraph.json").write_text(json.dumps(report, indent=1))
    lines = ["# Extension #9: LangGraph port, equivalence test", "",
             f"- Python {report['python']} ({report['platform']}), langgraph {report['langgraph']}; module `src/rag/graph_t1.py`.",
             f"- {report['items']} T1 gold items; cache-only, API calls this run: {report['api_calls']}.", ""]
    for k, s in report["systems"].items():
        lines.append(f"- **{k}**: {s['items']}/{report['items']} items; prompts identical {s['prompts_identical']}; outputs identical "
                     f"{s['outputs_identical']}; final verdicts identical to the sealed run {s['sealed_final_identical']}; "
                     f"cache misses {s['cache_misses']}; {'PASS' if s['pass'] else 'FAIL'}.")
    lines += ["", f"**Overall: {'PASS' if all_ok else 'FAIL'}** (pass = byte-identical prompts and identical outputs on all items, 0 calls)."]
    (OUT / "ext9_langgraph.md").write_text("\n".join(lines) + "\n")
    print("overall:", "PASS" if all_ok else "FAIL", "| api calls:", report["api_calls"])
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
