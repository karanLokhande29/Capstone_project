#!/usr/bin/env python3
"""Extension #3, T1 part (Amendments 5, 6, 8): cross-encoder reranking inside the P4 T1 pipeline.

    python3 scripts/run_ext3_t1_rerank.py plan          # 0 calls: prompts, cache hits, calls needed, ledger
    python3 scripts/run_ext3_t1_rerank.py run           # Gemini, frozen P4 prompts/model/params; resumes
    python3 scripts/run_ext3_t1_rerank.py score         # 0 calls: reranked − not reranked, paired bootstrap

- Reranker: `cross-encoder/ms-marco-MiniLM-L6-v2` @ 233902d2… (Apache-2.0), CPU, max_length 512, loaded from the
  local snapshot named by the pinned commit (no network).
- Method (as pre-registered): the hybrid list returned by retrieval (top 20, or deeper for class-blind items with more
  than four compared classes) has its top 20 reranked by score(query, paragraph text); ranks 21+ keep their order.
  The per-class cut to 5 (class-aware) or 5 x K (class-blind) is applied after reranking. Everything else is unchanged.
- Systems: class_blind and class_aware (no verifier). A prompt identical to the sealed run is served from the cache.
- Scoring against t1_validated_v1 (106): 3-way flag macro-F1, collapsed macro-F1 and `different` recall, each as
  reranked − not reranked, item-resampled paired bootstrap, 2,000 resamples, seed 20261011.
Outputs: data/rag_runs/t1_ext3_rerank_<system>/ and reports/private/final_push/extensions/sprint/ext3_t1_rerank.{json,md}.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

CE_REPO = "cross-encoder/ms-marco-MiniLM-L6-v2"
CE_REV = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
TOP = 20
SEED = 20261011
RESAMPLES = 2000
SYSTEMS = ("class_blind", "class_aware")
OUT = ROOT / "reports/private/final_push/extensions/sprint"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_dir(system: str) -> Path:
    return ROOT / "data/rag_runs" / f"t1_ext3_rerank_{system}"


def setup(*, live: bool):
    import run_p4 as R
    from run_sealed_predictions import _offline_pinned_model_loader
    from sentence_transformers import CrossEncoder

    from src.common.config import load_config
    from src.common.paths import PathResolver
    from src.rag import pipeline as PL

    _offline_pinned_model_loader()
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    res, _ = R.load_resources(cfg, resolver)
    prompts = R.load_prompts(cfg)
    snap = Path.home() / ".cache/huggingface/hub" / f"models--{CE_REPO.replace('/', '--')}" / "snapshots" / CE_REV
    if not snap.is_dir():
        raise SystemExit(f"STOP: pinned snapshot {CE_REV} of {CE_REPO} is not in the local cache")
    ce = CrossEncoder(str(snap), device="cpu", max_length=512)
    original = PL.retrieve
    memo: dict[tuple, list[str]] = {}

    def reranked(res_, query, **kw):
        ranked = original(res_, query, **kw)
        key = (query, tuple(ranked[:TOP]))
        if key not in memo:
            head = ranked[:TOP]
            scores = ce.predict([(query, " ".join(res_.text(p).split())) for p in head], batch_size=32,
                                show_progress_bar=False)
            order = sorted(range(len(head)), key=lambda j: (-float(scores[j]), j))  # ties keep the hybrid order
            memo[key] = [head[j] for j in order]
        return memo[key] + ranked[TOP:]

    PL.retrieve = reranked
    p4 = cfg["p4"]
    scfgs = {}
    for s in SYSTEMS:
        scfgs[s] = dataclasses.replace(R.SYSTEMS[s], per_class=int(p4["retrieval"]["t1_per_class"]),
                                       depth=int(p4["retrieval"]["depth"]), max_output_tokens=int(p4["max_output_tokens"]))
    return R, PL, cfg, resolver, res, prompts, scfgs


def make_client(R, cfg, resolver, *, cache_only: bool):
    from src.common.config import get_required
    from src.common.logging_setup import get_logger
    from src.llm import client as L

    p4 = cfg["p4"]
    ledger = L.QuotaLedger(resolver.working_root / p4["ledger"], soft_cap=int(p4["soft_cap"]))
    model = str(get_required(cfg, "llm.p4_model"))
    client = L.build_client(cfg, resolver, run_id="ext3_t1_rerank", model=model, long_context_model=model,
                            rpm=int(p4["rpm"]), tpm=int(p4["tpm"]),
                            extra_params={"json": bool(p4["json_mode"]), "thinking": p4.get("thinking")},
                            ledger=ledger, verify_models=not cache_only, logger=get_logger("llm.client", cfg))
    client.max_calls = int(p4["max_calls_per_run"])
    if cache_only:
        client.cache_only = True
        client.call_log_path = None
    return client, ledger, model


def cmd_plan(_a) -> int:
    R, PL, cfg, resolver, res, prompts, scfgs = setup(live=False)
    from src.llm import client as L

    p4 = cfg["p4"]
    params = {"temperature": 0.0, "json": bool(p4["json_mode"]), "thinking": p4.get("thinking"),
              "max_output_tokens": int(p4["max_output_tokens"])}
    model = str(cfg["llm"]["p4_model"])
    items = R._items(resolver)
    plan = {}
    for s, scfg in scfgs.items():
        need = changed = 0
        for it in items:
            query = " ".join(it["obligation_span"]["text"].split())
            ev, shown = PL.t1_evidence(res, it, query, scfg)
            msgs = PL.t1_messages(prompts, res, it, ev)
            key = L.LLMClient.cache_key("gemini", model, msgs, params)
            hit = (resolver.write_dir("llm_cache") / key[:2] / f"{key}.json").exists()
            sealed = json.loads((ROOT / "data/rag_runs" / f"t1_{s}" / f"{R._safe(it['item_id'])}.json").read_text())
            changed += shown != sealed["steps"][0]["shown"]
            done = (run_dir(s) / f"{R._safe(it['item_id'])}.json").exists()
            need += not hit and not done
        plan[s] = {"items": len(items), "shown_set_or_order_changed": changed, "calls_needed": need}
    ledger = json.loads((ROOT / p4["ledger"]).read_text()).get(model, {})
    print(json.dumps({"plan": plan, "total_calls_needed": sum(v["calls_needed"] for v in plan.values()),
                      "ledger_recent": dict(list(ledger.items())[-3:]), "soft_cap": p4["soft_cap"]}, indent=1))
    return 0


def cmd_run(a) -> int:
    R, PL, cfg, resolver, res, prompts, scfgs = setup(live=True)
    from src.llm import client as L

    client, ledger, model = make_client(R, cfg, resolver, cache_only=False)
    items = R._items(resolver)
    for s in a.systems:
        d = run_dir(s)
        d.mkdir(parents=True, exist_ok=True)
        for it in items:
            path = d / f"{R._safe(it['item_id'])}.json"
            if path.exists():
                continue
            try:
                rec = PL.run_t1_item(res, prompts, client, None, it, scfgs[s])
            except (L.RateLimitError, L.QuotaPaused, L.CallCapReached) as exc:
                print(f"STOP ({type(exc).__name__}): {str(exc)[:200]} — rerun later; finished items are kept")
                return 1
            except L.LLMError as exc:
                print(f"STOP (LLMError) on {it['item_id']}: {str(exc)[:200]} — rerun later; finished items are kept")
                return 1
            rec.update({"system": f"ext3_rerank_{s}", "reranker": {"repo": CE_REPO, "revision": CE_REV, "top": TOP},
                        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "prompt_sha256": prompts.hashes})
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        n = len(list(d.glob("t1_*.json")))
        print(f"{s}: {n}/{len(items)} items written", flush=True)
    print("run summary:", json.dumps(client.run.summary()))
    return 0


def cmd_score(_a) -> int:
    import run_phase4_scoring as P4S

    from src.eval import t1_regold as G
    from src.rag import analysis as A

    gold_path = ROOT / "data/benchmark/t1/t1_validated_v1.jsonl"
    gold = G.read_jsonl(gold_path)
    kw = {"resamples": RESAMPLES, "seed": SEED}
    out = {"extension": "#3 T1 reranking", "gold": "t1_validated_v1", "gold_sha256": sha(gold_path),
           "reranker": {"repo": CE_REPO, "revision": CE_REV, "top": TOP, "licence": "apache-2.0"},
           "bootstrap": {"resamples": RESAMPLES, "seed": SEED, "unit": "item"}, "systems": {}}
    for s in SYSTEMS:
        base = G.finals(ROOT / "data/rag_runs", s)
        rr = {}
        calls = cached = 0
        for p in sorted(run_dir(s).glob("t1_*.json")):
            r = json.loads(p.read_text())
            rr[r["item_id"]] = r["final"]
            calls += r["calls"]
            cached += all(st["cached"] for st in r["steps"])
        ua, ub = A.t1_units(gold, rr), A.t1_units(gold, base)
        keep = set(ua["items"]) & set(ub["items"])
        ua, ub = A.subset_units(ua, keep), A.subset_units(ub, keep)
        out["systems"][s] = {
            "n_items": len(keep), "new_calls": calls, "items_fully_cached": cached,
            "reranked": A.t1_metrics(ua, **kw), "not_reranked": A.t1_metrics(ub, **kw),
            "paired_flag": A.t1_paired(ua, ub, **kw),
            "paired_judgement": P4S.judgement_paired(ua, ub, **kw)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ext3_t1_rerank.json").write_text(json.dumps(out, indent=1, default=float))

    from src.eval.ci_format import fmt_ci

    def fmt(d):
        return fmt_ci(d["diff"], d["ci"][0], d["ci"][1], signed=True, reading=True)

    lines = ["# Extension #3, T1: cross-encoder reranking inside the P4 pipeline", "",
             f"`{CE_REPO}` @ `{CE_REV[:12]}…` (Apache-2.0), CPU; hybrid top {TOP} reranked before the per-class cut. Frozen P4 "
             f"prompts, model and parameters. Gold `t1_validated_v1`. Paired item bootstrap, {RESAMPLES} resamples, seed {SEED}.", "",
             "| System | n | metric | not reranked | reranked | reranked − not reranked |", "|---|---|---|---|---|---|"]
    for s, v in out["systems"].items():
        pf, pj = v["paired_flag"], v["paired_judgement"]
        ra, rb = v["reranked"], v["not_reranked"]
        for lab, d, a_, b_ in (("3-way flag macro-F1", pf["flag_macro_f1"], ra["flag_macro_f1"]["value"], rb["flag_macro_f1"]["value"]),
                               ("collapsed flag macro-F1", pf["collapsed_macro_f1"], ra["collapsed_macro_f1"]["value"],
                                rb["collapsed_macro_f1"]["value"]),
                               ("`different` recall", pj["different_recall"], pj["different_recall"]["a"], pj["different_recall"]["b"])):
            lines.append(f"| {s} | {v['n_items']} | {lab} | {b_:.3f} | {a_:.3f} | {fmt(d)} |")
    lines += ["", "Calls: " + "; ".join(f"{s} {v['new_calls']} new, {v['items_fully_cached']} items served from the cache"
                                       for s, v in out["systems"].items()) + "."]
    (OUT / "ext3_t1_rerank.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--systems", nargs="*", default=list(SYSTEMS), choices=SYSTEMS)
    sub.add_parser("score")
    a = ap.parse_args()
    return {"plan": cmd_plan, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
