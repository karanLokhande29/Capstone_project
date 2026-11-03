#!/usr/bin/env python3
"""Extension #4 (Amendments 5, 6, 8): T1 class-blind with a larger open-weight model, Groq `openai/gpt-oss-120b`.

    python3 scripts/run_ext4_groq.py [--max-items N]

- Same frozen P4 T1 prompt, retrieval and items as the Gemini class-blind run; reasoning effort "low"; max completion
  tokens 1,500; JSON mode; temperature 0.
- Items in the pre-registered class-stratified order (ext4_groq_run_order_v1.json); finished items are skipped, so the
  run resumes after any stop. If the cut-off arrives first, the completed prefix is a class-stratified subset.
- Skip rule: an item whose Gemini-counted prompt plus 1,500 exceeds 8,000 tokens is recorded as infeasible.
- Groq free tier (30 RPM, 8K TPM, 200K tokens/day): requests are throttled; a 429 is recorded and the run sleeps until
  the stated reset (never a tight loop). Stops at Sat 10 Oct 18:00 IST.
Outputs: data/rag_runs/t1_ext4_groq_gptoss120b/<item>.json and _progress.jsonl.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

IST = timezone(timedelta(hours=5, minutes=30))
CUTOFF = datetime(2026, 10, 10, 18, 0, tzinfo=IST)
MODEL = "openai/gpt-oss-120b"
MAX_OUT = 1500
LIMIT = 8000
ORDER = ROOT / "reports/private/final_push/extensions/sprint/ext4_groq_run_order_v1.json"
ORDER_SHA = "57fbc2a550c47852205fd480d7a5a07e0de302eeb4f6bd2800202fc4f676b812"
OUT = ROOT / "data/rag_runs/t1_ext4_groq_gptoss120b"


def log(obj: dict) -> None:
    obj = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **obj}
    with (OUT / "_progress.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps(obj) + "\n")
    print(json.dumps(obj), flush=True)


def wait_seconds(msg: str) -> float:
    m = re.search(r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", msg)
    if not m or not any(m.groups()):
        return 600.0
    h, mi, s = (float(x) if x else 0.0 for x in m.groups())
    return h * 3600 + mi * 60 + s + 5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=None)
    a = ap.parse_args()
    import hashlib

    import run_p4 as R
    from run_sealed_predictions import _offline_pinned_model_loader
    from src.common.config import load_config
    from src.common.paths import PathResolver
    from src.llm import client as L
    from src.rag import pipeline as PL

    if hashlib.sha256(ORDER.read_bytes()).hexdigest() != ORDER_SHA:
        raise SystemExit("STOP: the pre-registered run order changed")
    OUT.mkdir(parents=True, exist_ok=True)
    _offline_pinned_model_loader()
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    res, _ = R.load_resources(cfg, resolver)
    prompts = R.load_prompts(cfg)
    p4 = cfg["p4"]
    items = {it["item_id"]: it for it in R._items(resolver)}
    order = json.loads(ORDER.read_text())["order"]
    # Prompt size from the Gemini class-blind run (the pre-registered basis of the skip rule).
    gem_params = {"temperature": 0.0, "json": bool(p4["json_mode"]), "thinking": p4.get("thinking"),
                  "max_output_tokens": int(p4["max_output_tokens"])}
    gcfg = copy.deepcopy(cfg)
    gcfg["llm"]["primary"] = "groq"
    gcfg["llm"]["fallback"] = "none"
    client = L.build_client(gcfg, resolver, run_id="ext4_groq_gptoss120b", verify_models=False, model=MODEL,
                            rpm=30, tpm=8000, extra_params={"json": True, "reasoning_effort": "low"})
    client.max_calls = 10_000
    scfg = R.SYSTEMS["class_blind"]
    scfg.per_class = int(p4["retrieval"]["t1_per_class"])
    scfg.depth = int(p4["retrieval"]["depth"])
    scfg.max_output_tokens = MAX_OUT
    done_n = 0
    for pos, iid in enumerate(order, start=1):
        if datetime.now(IST) >= CUTOFF:
            log({"event": "cutoff", "position": pos})
            break
        path = OUT / f"{R._safe(iid)}.json"
        if path.exists():
            continue
        it = items[iid]
        ev, _shown = PL.t1_evidence(res, it, " ".join(it["obligation_span"]["text"].split()), scfg)
        msgs = PL.t1_messages(prompts, res, it, ev)
        gkey = L.LLMClient.cache_key("gemini", str(cfg["llm"]["p4_model"]), msgs, gem_params)
        gpath = resolver.write_dir("llm_cache") / gkey[:2] / f"{gkey}.json"
        gtok = (json.loads(gpath.read_text()).get("completion") or {}).get("input_tokens") if gpath.exists() else None
        if gtok is None:
            gtok = sum(len(m["content"]) for m in msgs) // 3
            basis = "chars/3 (no Gemini count cached)"
        else:
            basis = "Gemini input_tokens of the cached class-blind prompt"
        if gtok + MAX_OUT > LIMIT:
            path.write_text(json.dumps({"item_id": iid, "position": pos, "infeasible": True, "prompt_tokens_estimate": gtok,
                                        "basis": basis, "rule": f"prompt + {MAX_OUT} > {LIMIT}"}, indent=1))
            log({"event": "infeasible", "position": pos, "item": iid, "prompt_tokens_estimate": gtok})
            continue
        while True:
            try:
                rec = PL.run_t1_item(res, prompts, client, None, it, scfg)
                break
            except L.RateLimitError as exc:
                w = wait_seconds(str(exc))
                log({"event": "rate_limited", "position": pos, "sleep_seconds": round(w), "message": str(exc)[:160]})
                if datetime.now(IST) + timedelta(seconds=w) >= CUTOFF:
                    log({"event": "cutoff_during_wait", "position": pos})
                    return 0
                time.sleep(w)
            except L.LLMError as exc:
                msg = str(exc)
                if "413" in msg or "too large" in msg.lower() or "context" in msg.lower():
                    path.write_text(json.dumps({"item_id": iid, "position": pos, "infeasible": True, "error": msg[:200]}, indent=1))
                    log({"event": "infeasible_provider", "position": pos, "item": iid})
                    rec = None
                    break
                log({"event": "error", "position": pos, "message": msg[:200], "sleep_seconds": 120})
                time.sleep(120)
        if rec is None:
            continue
        rec.update({"system": "ext4_groq_gptoss120b_class_blind", "position": pos, "model_requested": MODEL,
                    "reasoning_effort": "low", "max_output_tokens": MAX_OUT, "prompt_tokens_estimate": gtok,
                    "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "prompt_sha256": prompts.hashes})
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        done_n += 1
        log({"event": "done", "position": pos, "item": iid, "calls": rec["calls"],
             "tokens": [s.get("model_version") for s in rec["steps"]][:1]})
        if a.max_items and done_n >= a.max_items:
            break
    log({"event": "stopped", "done_this_run": done_n,
         "finished_total": sum(1 for p in OUT.glob("t1_*.json"))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
