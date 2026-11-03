#!/usr/bin/env python3
"""RBI-ObliBench CLI demo: the P4-001 agentic RAG pipeline on one question.

    python3 scripts/demo.py "question" [--class "<entity class>"] [--as-of YYYY-MM-DD]
                            [--no-class-filter] [--no-temporal-filter] [--no-verifier]

Prints the answer (or the abstention), the cited paragraphs with Direction titles and ids, the filters
applied, the verifier verdicts and the LLM calls used. A missing key or an exhausted quota gives a clear
message; the key itself is never printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def render(log: Mapping[str, Any], res: Any, *, calls: int, cache_hits: int, model: str) -> str:
    r = log["result"]
    f = log["flags"]
    out = [f"Question: {log['query']}",
           f"Entity class: {log['entity_class'] or '(not given)'}   As of: {log['as_of'] or '(not given)'}",
           "Filters: class filter " + ("ON" if f["class_filter"] and log["entity_class"] else "OFF")
           + ", temporal filter " + ("ON" if f["temporal_filter"] and log["as_of"] else "OFF")
           + ", verifier " + ("ON" if f["verifier"] else "OFF"), ""]
    if r["abstained_by_verifier"]:
        out.append("Answer: cannot answer reliably (a sentence was still unsupported after one retry).")
    elif not r["can_answer"]:
        out.append("Answer: the evidence does not answer this question.")
    else:
        out.append("Answer:")
        sup = r.get("supported") or [None] * len(r["sentences"])
        for s, ok in zip(r["sentences"], sup):
            verdict = "" if ok is None else ("  [verifier: supported]" if ok else "  [verifier: NOT supported]")
            out.append(f"  - {s['text']} {' '.join('[' + c + ']' for c in s['citations'])}{verdict}")
    out.append("")
    final = log["steps"][-1]
    out.append("Evidence (top 5 after filters):")
    for pid in r["evidence"]:
        md = res.corpus.md_id[res.corpus.index_of[pid]]
        d = res.doc.get(md, {})
        notes = final.get("status", {}).get(pid, {}).get("notes", [])
        out.append(f"  [{pid}] {d.get('title', '')} ({md}; {d.get('entity_class', '')})")
        for n in notes:
            out.append(f"      status: {n}")
    if final.get("dropped_by_temporal"):
        out.append(f"  dropped as deleted on the as-of date: {', '.join(final['dropped_by_temporal'])}")
    out.append("")
    out.append(f"Verifier retries: {len(log['steps']) - 1}. LLM calls: {calls} new, {cache_hits} from cache. Model: {model}.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--class", dest="entity_class")
    parser.add_argument("--as-of", dest="as_of")
    parser.add_argument("--no-class-filter", action="store_true")
    parser.add_argument("--no-temporal-filter", action="store_true")
    parser.add_argument("--no-verifier", action="store_true")
    parser.add_argument("--groq-outage-fallback", action="store_true",
                        help="demo only: use Groq gpt-oss-120b because Gemini is unavailable (never used for evaluation)")
    args = parser.parse_args(argv)

    import importlib.util

    from src.common.config import load_config
    from src.common.paths import PathResolver
    from src.llm.client import LLMError, MissingKeyError, QuotaPaused
    from src.rag import pipeline as PL

    spec = importlib.util.spec_from_file_location("run_p4", Path(__file__).resolve().parent / "run_p4.py")
    run_p4 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_p4)

    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    label = None
    try:
        if args.groq_outage_fallback:
            from src.llm import client as L

            L.load_env()
            model = str(cfg["llm"]["fallback_model"])
            slot = L.ProviderSlot(L.GroqProvider(L.require_key("GROQ_API_KEY"), timeout_sec=120), {"default": model},
                                  rpm=int(cfg["llm"]["providers"]["groq"]["rpm"]), tpm=int(cfg["llm"]["providers"]["groq"]["tpm"]))
            llm = L.LLMClient([slot], cache_dir=resolver.write_dir("llm_cache"), max_calls=20, run_id="p4_demo_groq",
                              backoff_attempts=3, extra_params={"json": True})
            label = f"model: Groq {model.split('/')[-1]} (Gemini outage), not the evaluated configuration"
        else:
            llm, ledger = run_p4.make_llm(cfg, resolver, "p4_demo")
    except MissingKeyError as exc:
        print(f"Cannot run: {exc}. Put the key in .env (see .env.example).")
        return 2
    print("Loading the corpus index and models (about 30 s)...", file=sys.stderr)
    res, _ = run_p4.load_resources(cfg, resolver)
    verifier = None if args.no_verifier else run_p4.load_verifier(cfg)
    prompts = run_p4.load_prompts(cfg)
    acfg = PL.AnswerConfig(class_filter=not args.no_class_filter, temporal_filter=not args.no_temporal_filter,
                           verifier=not args.no_verifier, depth=int(cfg["p4"]["retrieval"]["depth"]),
                           answer_top=int(cfg["p4"]["retrieval"]["answer_top"]),
                           max_output_tokens=int(cfg["p4"]["max_output_tokens"]))
    try:
        log = PL.answer(res, prompts, llm, verifier, args.question, entity_class=args.entity_class,
                        as_of=args.as_of, cfg=acfg)
    except QuotaPaused as exc:
        print(f"The free daily quota is used up. Try again after {exc.resume_after_ist} IST.")
        return 3
    except LLMError as exc:
        print(f"The LLM call failed ({type(exc).__name__}). Check the key in .env and your connection.")
        return 4
    s = llm.run.summary()
    if label:
        print(label)
    print(render(log, res, calls=s["api_calls"], cache_hits=s["cache_hits"],
                 model=label.removeprefix("model: ") if label else cfg["llm"]["p4_model"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
