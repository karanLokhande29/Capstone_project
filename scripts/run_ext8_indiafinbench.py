#!/usr/bin/env python3
"""Extension #8 (Amendments 6, 8): IndiaFinBench (CC BY 4.0), frozen P4 answer step with the item's context given.

    python3 scripts/run_ext8_indiafinbench.py plan                    # 0 calls: next positions, ledger
    python3 scripts/run_ext8_indiafinbench.py run --max-calls N       # next positions of the pre-registered order
    python3 scripts/run_ext8_indiafinbench.py score                   # 0 calls

- Items in the pre-registered order (ext8_indiafinbench_run_order_v1.json, sha 60c8bf26…); finished items are
  skipped, so a stop leaves a completed prefix (a stratified subset).
- Prompt adaptation exactly as Amendment 8: frozen answer prompts unchanged; {query} = question + one format line per
  task type; {entity_class} = {as_of} = "not specified"; evidence = the context as `md_00000::p00000`, title
  "IndiaFinBench context". Prediction = the answer's sentences joined by spaces; can_answer false or bad JSON = incorrect.
- Gemini P4 model and parameters, P4 quota ledger (≤ 480 per quota day); stops at --max-calls new calls.
- Scoring: src/eval/indiafinbench.py (the card's four stages, no LLM judge); accuracy with Wilson 95% intervals.
Outputs: data/rag_runs/ext8_indiafinbench/ and reports/private/final_push/extensions/sprint/ext8_indiafinbench.{json,md}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

ORDER = ROOT / "reports/private/final_push/extensions/sprint/ext8_indiafinbench_run_order_v1.json"
ORDER_SHA = "60c8bf26"
DATA = ROOT / "data/raw_ext/indiafinbench/data"
RUNS = ROOT / "data/rag_runs/ext8_indiafinbench"
OUT = ROOT / "reports/private/final_push/extensions/sprint"
PID = "md_00000::p00000"
FORMAT_LINE = {"contradiction_detection": "Begin your answer with Yes or No.",
               "numerical_reasoning": "State the final value with its unit in the first sentence.",
               "regulatory_interpretation": "Answer in one or two short sentences.",
               "temporal_reasoning": "Answer in one or two short sentences."}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load_items() -> dict[str, dict]:
    import pandas as pd

    out = {}
    for split in ("dev", "test"):
        for r in pd.read_parquet(DATA / f"{split}-00000-of-00001.parquet").to_dict("records"):
            out[f"{split}:{r['id']}"] = {**r, "split": split}
    return out


def order() -> list[str]:
    if not sha(ORDER).startswith(ORDER_SHA):
        raise SystemExit("STOP: the pre-registered run order changed")
    return json.loads(ORDER.read_text())["order"]


def out_path(key: str) -> Path:
    return RUNS / f"{key.replace(':', '_')}.json"


def messages(prompts, it: dict) -> list[dict]:
    query = f"{it['question'].strip()} {FORMAT_LINE[it['task_type']]}"
    ev = f"[{PID}] (Direction md_00000: IndiaFinBench context; entity class: not specified)\n{it['context'].strip()}"
    return prompts.messages("answer", query=query, entity_class="not specified", as_of="not specified", evidence=ev)


def cmd_plan(_a) -> int:
    from src.common.config import load_config

    cfg = load_config()
    od = order()
    done = [k for k in od if out_path(k).exists()]
    led = json.loads((ROOT / cfg["p4"]["ledger"]).read_text()).get(str(cfg["llm"]["p4_model"]), {})
    nxt = next((i for i, k in enumerate(od, 1) if not out_path(k).exists()), None)
    print(json.dumps({"items": len(od), "done": len(done), "next_position": nxt, "ledger_recent": dict(list(led.items())[-3:])},
                     indent=1))
    return 0


def cmd_run(a) -> int:
    import run_p4 as R

    from src.common.config import get_required, load_config
    from src.common.logging_setup import get_logger
    from src.common.paths import PathResolver
    from src.llm import client as L
    from src.rag import pipeline as PL

    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    prompts = R.load_prompts(cfg)
    p4 = cfg["p4"]
    ledger = L.QuotaLedger(resolver.working_root / p4["ledger"], soft_cap=int(p4["soft_cap"]))
    model = str(get_required(cfg, "llm.p4_model"))
    client = L.build_client(cfg, resolver, run_id="ext8_indiafinbench", model=model, long_context_model=model,
                            rpm=int(p4["rpm"]), tpm=int(p4["tpm"]),
                            extra_params={"json": bool(p4["json_mode"]), "thinking": p4.get("thinking")},
                            ledger=ledger, verify_models=True, logger=get_logger("llm.client", cfg))
    client.max_calls = min(int(p4["max_calls_per_run"]), a.max_calls)
    items = load_items()
    RUNS.mkdir(parents=True, exist_ok=True)
    new = 0
    for pos, key in enumerate(order(), 1):
        path = out_path(key)
        if path.exists():
            continue
        if new >= a.max_calls:
            print(f"budget of {a.max_calls} new calls reached; next position {pos}")
            break
        it = items[key]
        try:
            c = client.complete(messages(prompts, it), max_output_tokens=int(p4["max_output_tokens"]))
        except (L.RateLimitError, L.QuotaPaused, L.CallCapReached, L.LLMError) as exc:
            print(f"STOP at position {pos} ({type(exc).__name__}): {str(exc)[:200]}; finished items are kept")
            break
        new += not c.cached
        data = PL.parse_json(c.text)
        can, sents = PL.split_answer(data)
        rec = {"key": key, "position": pos, "id": it["id"], "split": it["split"], "task_type": it["task_type"],
               "difficulty": it["difficulty"], "cached": c.cached, "model": c.model, "model_version": c.model_version,
               "raw": c.text, "parse_ok": data is not None, "can_answer": can, "sentences": sents,
               "prediction": " ".join(s["text"] for s in sents) if can else "",
               "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "prompt_sha256": prompts.hashes}
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    n = len(list(RUNS.glob("*.json")))
    print(f"ext8: {n}/406 items written; {new} new calls this run")
    print("run summary:", json.dumps(client.run.summary()))
    return 0


def cmd_score(_a) -> int:
    from src.eval import indiafinbench as F

    items = load_items()
    od = order()
    rows = []
    prefix = 0
    for k in od:
        p = out_path(k)
        if not p.exists():
            break
        prefix += 1
        r = json.loads(p.read_text())
        it = items[k]
        s = F.score(it["reference_answer"], r["prediction"], it["task_type"]) if r["can_answer"] else {"correct": False, "stage": None}
        rows.append({"key": k, "split": it["split"], "task_type": it["task_type"], "can_answer": r["can_answer"],
                     "parse_ok": r["parse_ok"], **s})
    extra = sum(1 for k in od[prefix:] if out_path(k).exists())

    def acc(rs):
        k_, n_ = sum(r["correct"] for r in rs), len(rs)
        return {"n": n_, "correct": k_, "accuracy": k_ / n_ if n_ else None, "wilson95": F.wilson(k_, n_)}

    by = defaultdict(list)
    for r in rows:
        by[r["task_type"]].append(r)
    out = {"extension": "#8 IndiaFinBench", "licence": "CC BY 4.0", "dataset_card_sha256": sha(DATA.parent / "README.md"),
           "run_order_sha256": sha(ORDER), "scored": "completed prefix of the pre-registered order",
           "completed_prefix": prefix, "of": len(od), "items_after_a_gap_not_scored": extra,
           "scoring": "card's four stages, no LLM judge (conservative lower bound); CON scored by stages 1 and 4 only",
           "overall": acc(rows), "test_split": acc([r for r in rows if r["split"] == "test"]),
           "dev_split": acc([r for r in rows if r["split"] == "dev"]),
           "by_task": {t: acc(v) for t, v in sorted(by.items())},
           "stages": dict(Counter(str(r["stage"]) for r in rows)),
           "abstained_or_unparsed": sum(1 for r in rows if not r["can_answer"]),
           "card_reference": {"published_model_range": "70.4–89.7%", "non_specialist_human": "69.0%"}, "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ext8_indiafinbench.json").write_text(json.dumps(out, indent=1))
    f = lambda d: (f"{d['accuracy']:.3f} [{d['wilson95'][0]:.3f}, {d['wilson95'][1]:.3f}] (n = {d['n']})" if d["n"] else "n = 0")
    lines = ["# Extension #8: IndiaFinBench, frozen P4 answer step with the item's context", "",
             f"Completed prefix {prefix}/{len(od)} of the pre-registered stratified order. Scoring: the dataset card's four "
             "automated stages, no LLM judge (a conservative lower bound); accuracy with Wilson 95% intervals.", "",
             f"- Overall: {f(out['overall'])}", f"- Test split: {f(out['test_split'])}", f"- Dev split: {f(out['dev_split'])}"]
    lines += [f"- {t}: {f(v)}" for t, v in out["by_task"].items()]
    lines += [f"- Stage of the match: {out['stages']}; abstained or unparsed: {out['abstained_or_unparsed']}.",
              "- Card reference (its primary automated scores on all 406 items with its own task prompts; not one-to-one "
              "comparable with this adapted frozen prompt on a prefix): twelve models 70.4–89.7%; non-specialist human 69.0% (n = 100)."]
    (OUT / "ext8_indiafinbench.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    r = sub.add_parser("run")
    r.add_argument("--max-calls", type=int, required=True)
    sub.add_parser("score")
    a = ap.parse_args()
    return {"plan": cmd_plan, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
