#!/usr/bin/env python3
"""P4-001 runner: prompt freeze, smoke call, T1 system runs (resumable, quota-aware), status.

    python3 scripts/run_p4.py freeze                 # hash configs/p4_prompts_v1/* into config (p4.prompt_sha256)
    python3 scripts/run_p4.py smoke                  # one call on llm.p4_model with the frozen settings
    python3 scripts/run_p4.py debug --n 5            # format debugging on <= 5 REJECTED T1 items (not gold); before freeze
    python3 scripts/run_p4.py t1 --system class_aware|final_agentic|class_blind|ablation_a|long_context [--subset]
    python3 scripts/run_p4.py status                 # calls per quota day, runs done
    python3 scripts/run_p4.py t3 [--temporal on|off]  # ablation B on the frozen T3 set
    python3 scripts/run_p4.py t4 [--verifier off|on]  # ablation C on the P3-002 T4 questions
    python3 scripts/run_p4.py t2                     # T2 retrieval stage + ablation A on T2 (no LLM)
    python3 scripts/run_p4.py demo                   # the report's CLI transcripts
    python3 scripts/run_p4.py report                 # reports/p4001_system_and_ablations.md + p4001_metrics_v1.json
    python3 scripts/run_p4.py backup                 # verified zip in ../p4001_backups/ (no key values)
    python3 scripts/run_p4.py resume                 # continue the Part A runs in priority order

Every run writes one JSON per item to data/rag_runs/<system>/ and skips items already written, so a
quota pause loses nothing. No provider fallback: a daily-quota error or the ledger's soft cap stops
the run with the resume time in IST. Only reads data/benchmark/t1, t2, t4.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import DEFAULT_CONFIG_PATH, REPO_ROOT, get_required, load_config  # noqa: E402
from src.common.io_helpers import read_json, write_json  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.eval.ci_format import ABOVE, ci_reading, fmt_ci  # noqa: E402
from src.rag import pipeline as PL  # noqa: E402

T1_VALIDATED = ("benchmark", "t1", "t1_validated_v1.jsonl")
T1_CANDIDATES = ("benchmark", "t1", "t1_candidate_benchmark_v1.jsonl")
T1_SAMPLE = ("benchmark", "t1", "p2004_sample_v1.jsonl")
SYSTEMS = {
    "class_aware": PL.T1Config(class_filter=True, verifier=False),
    "final_agentic": PL.T1Config(class_filter=True, verifier=True),
    "class_blind": PL.T1Config(class_filter=False, verifier=False),
    "ablation_a": PL.T1Config(class_filter=False, verifier=True),
}
PART_A_ORDER = ("class_aware", "final_agentic", "class_blind", "ablation_a")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as h:
        return [json.loads(x) for x in h if x.strip()]


def _runs_dir(resolver: PathResolver, system: str) -> Path:
    d = resolver.working_root / "data" / "rag_runs" / system
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_failure(out_dir: Path, key: str, exc: BaseException) -> None:
    with (out_dir / "_call_failures.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps({"key": key, "error": type(exc).__name__, "message": str(exc)[:300], "utc": _now()}) + "\n")
    print(f"  call failure on {key}: {type(exc).__name__} (not written; retried on the next run)", flush=True)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


# -- resources ----------------------------------------------------------------------


def load_resources(cfg: dict, resolver: PathResolver) -> tuple[PL.Resources, dict]:
    import numpy as np

    from src.retrieval import index as IX
    from src.t3 import parser as P

    rc = cfg["retrieval"]
    t0 = time.time()
    corpus = IX.load_corpus(resolver.read_path("processed"))
    if len(corpus) != int(rc["expected_paragraphs"]):
        raise SystemExit(f"STOP: {len(corpus)} paragraphs, expected {rc['expected_paragraphs']}")
    bm25 = IX.BM25Index.from_config(corpus.texts, rc["bm25"])
    emb, meta = IX.load_embeddings(resolver.write_dir("indexes"), corpus)
    emb = emb.astype(np.float32)
    model = IX.load_model(rc["embedding_model"], rc["embedding_revision"], device=meta["device"],
                          max_seq_length=int(rc["max_seq_length"]))

    def encoder(q: str):
        return IX.encode(model, [IX.embedding_text(q)], 1)[0]

    manifest = _read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))
    doc = {r["document_id"]: {"title": r.get("title") or "", "entity_class": r.get("entity_class_raw"),
                              "subject_family": r.get("subject_family")} for r in manifest}
    titles = {k: v["title"] for k, v in doc.items()}
    paras_by_md: dict[str, list[dict]] = {}
    for p in sorted(Path(resolver.read_path("processed")).glob("md_*.jsonl")):
        rows = sorted(_read_jsonl(p), key=lambda r: r.get("position") or 0)
        paras_by_md[p.stem] = [{"paragraph_id": r["paragraph_id"], "clause_path": r.get("clause_path")} for r in rows]
    amend_path = REPO_ROOT / str(get_required(cfg, "supplementary.data_dir")) / "amendment" / "items_v1.jsonl"
    amendments = {it["item_id"]: it for it in _read_jsonl(amend_path)}
    actions = [a for it in sorted(amendments.values(), key=lambda x: x["item_id"]) for a in P.parse_amendment(it, titles)[0]]
    temporal = PL.TemporalIndex.build(actions, amendments, paras_by_md)
    res = PL.Resources(corpus=corpus, bm25=bm25, emb=emb, encoder=encoder, doc=doc,
                       function_headings=frozenset(cfg["matching"]["function_headings"]), temporal=temporal,
                       paragraph_max_chars=int(cfg["p4"]["retrieval"]["paragraph_max_chars"]))
    extra = {"paras_by_md": paras_by_md, "load_seconds": round(time.time() - t0, 1),
             "temporal_paragraphs": len(temporal.events), "embedding_device": meta["device"]}
    return res, extra


def load_verifier(cfg: dict) -> PL.NLIVerifier:
    v = cfg["p4"]["verifier"]
    if not v.get("nli_revision"):
        raise SystemExit("STOP: p4.verifier.nli_revision is not pinned")
    return PL.NLIVerifier(v["nli_model"], v["nli_revision"], device="cpu")


def make_llm(cfg: dict, resolver: PathResolver, run_id: str, *, long_context: bool = False):
    from src.common.logging_setup import get_logger
    from src.llm import client as L

    p4 = cfg["p4"]
    if cfg["llm"].get("fallback") not in (None, "none"):
        raise SystemExit("STOP: P4 requires llm.fallback: none")
    ledger = L.QuotaLedger(resolver.working_root / p4["ledger"], soft_cap=int(p4["soft_cap"]))
    model = str(get_required(cfg, "llm.p4_model"))
    client = L.build_client(cfg, resolver, run_id=run_id, model=model, long_context_model=model,
                            rpm=int(p4["rpm"]), tpm=int(p4["tpm"]),
                            extra_params={"json": bool(p4["json_mode"]), "thinking": p4.get("thinking")},
                            ledger=ledger, verify_models=True, logger=get_logger("llm.client", cfg),
                            timeout_sec=float(p4["long_context"]["request_timeout_sec"]) if long_context else None,
                            backoff_attempts=int(p4["long_context"]["attempts_per_run"]) if long_context else None)
    client.max_calls = int(p4["max_calls_per_run"])
    if len(client.slots) != 1:
        raise SystemExit("STOP: more than one provider configured for a P4 run")
    return client, ledger


def load_prompts(cfg: dict, *, require_frozen: bool = True) -> PL.Prompts:
    return PL.Prompts(REPO_ROOT / cfg["p4"]["prompts_dir"], cfg["p4"].get("prompt_sha256") or {},
                      require_frozen=require_frozen)


# -- commands -----------------------------------------------------------------------


def cmd_freeze(cfg: dict, resolver: PathResolver, _args) -> int:
    hashes = PL.prompt_hashes(REPO_ROOT / cfg["p4"]["prompts_dir"])
    if cfg["p4"].get("prompt_sha256"):
        if cfg["p4"]["prompt_sha256"] == hashes:
            print("prompts already frozen; hashes unchanged")
            return 0
        raise SystemExit("STOP: prompts are already frozen and differ from the files; ask Karan before changing a prompt")
    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
    block = "  prompt_sha256:\n" + "".join(f"    {k}: {v}\n" for k, v in sorted(hashes.items()))
    block = f"  # Frozen {_now()}, before any validated-set run.\n" + block
    if text.count("  prompt_sha256: {}\n") != 1:
        raise SystemExit("STOP: could not find the empty prompt_sha256 entry in config")
    DEFAULT_CONFIG_PATH.write_text(text.replace("  prompt_sha256: {}\n", block), encoding="utf-8")
    load_config()
    for k, v in sorted(hashes.items()):
        print(f"  {k}  {v[:16]}…")
    print("frozen")
    return 0


def _outage_window(resolver: PathResolver) -> dict[str, Any]:
    """First and last HTTP 503 of the outage that began on 2026-09-28 evening, from the probe log and the run logs."""
    import re as _re

    times = []
    pl = resolver.working_root / "data" / "rag_runs" / "_probe_log.jsonl"
    probes = [json.loads(x) for x in open(pl)] if pl.exists() else []
    times += [p["ist"] for p in probes if not p["ok"]]
    for logf in ("logs/p4_partB_chain2.log", "logs/p4_lc_chain3.log"):
        f_ = resolver.working_root / logf
        if f_.exists():
            for line in f_.read_text(errors="replace").splitlines():
                m = _re.match(r"(2026-09-2\d \d\d:\d\d:\d\d),\d+ \[WARNING\] llm.client: llm: gemini TransientError", line)
                if m and m.group(1) >= "2026-09-28 20:00:00":
                    times.append(m.group(1))
    times.sort()
    ok_after = [p["ist"] for p in probes if p["ok"] and times and p["ist"] > times[0]]
    return {"first_503_ist": times[0] if times else None, "last_503_ist": times[-1] if times else None,
            "probes": len(probes), "probes_unavailable": sum(1 for p in probes if not p["ok"]),
            "first_ok_after_outage_ist": ok_after[0] if ok_after else None}


def cmd_lcstatus(cfg: dict, resolver: PathResolver, args) -> int:
    """Share of the 106 items without a long-context answer at --cap; exit 10 if above the 20% threshold."""
    d = resolver.working_root / "data" / "rag_runs" / f"t1_long_context_cap{args.cap // 1000}k"
    n = len(_items(resolver))
    k = len(list(d.glob("t1_*.json"))) if d.exists() else 0
    share = (n - k) / n
    print(f"cap {args.cap}: {k}/{n} answered, {n - k} failing ({share:.0%}; threshold > 20%)")
    return 10 if share > float(cfg["p4"]["long_context"]["max_subset_failure_share"]) else 0


def cmd_probe(cfg: dict, resolver: PathResolver, _args) -> int:
    """One uncached, ledger-counted call: exit 0 if the model answers, 2 if it is unavailable, 3 on the quota cap."""
    from src.llm.client import LLMError, QuotaPaused

    client, ledger = make_llm(cfg, resolver, "p4_probe")
    client.backoff = (1, 0.0, 1.0, 0.0)
    try:
        c = client.complete([{"role": "user", "content": f"Health probe {_now()}. Return the JSON object {{\"ok\": true}}."}],
                            max_output_tokens=32)
    except QuotaPaused as exc:
        print(f"quota: resume after {exc.resume_after_ist} IST")
        return 3
    except LLMError as exc:
        _probe_log(resolver, False, type(exc).__name__)
        print(f"unavailable ({type(exc).__name__}); calls today {ledger.used(cfg['llm']['p4_model'])}")
        return 2
    _probe_log(resolver, True, "ok")
    print(f"ok; calls today {ledger.used(c.model)}")
    return 0


def _probe_log(resolver: PathResolver, ok: bool, what: str) -> None:
    from zoneinfo import ZoneInfo

    ist = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    with (resolver.working_root / "data" / "rag_runs" / "_probe_log.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps({"ist": ist, "ok": ok, "what": what}) + "\n")


def cmd_smoke(cfg: dict, resolver: PathResolver, _args) -> int:
    from src.llm.client import LLMError

    client, ledger = make_llm(cfg, resolver, "p4_smoke")
    try:
        c = client.complete([{"role": "user", "content": "P4 smoke test. Return the JSON object {\"ok\": true}."}],
                            max_output_tokens=64)
    except LLMError as exc:
        print(f"gemini\t{cfg['llm']['p4_model']}\tFAIL ({type(exc).__name__})")
        return 1
    ok = (PL.parse_json(c.text) or {}).get("ok") is True
    print(f"gemini\t{c.model}\t{'OK' if ok else 'FAIL'}\tserved={c.model_version}\tcached={c.cached}")
    print(f"calls on quota day {ledger.quota_day()}: {ledger.used(c.model)} (soft cap {ledger.soft_cap})")
    return 0 if ok else 1


def _items(resolver: PathResolver) -> list[dict]:
    return _read_jsonl(resolver.read_path(*T1_VALIDATED))


def _rejected_items(resolver: PathResolver) -> list[dict]:
    """Sampled T1 items that were not validated (rejected): used only for format debugging, never scored."""
    valid = {it["item_id"] for it in _items(resolver)}
    sample = [r for r in _read_jsonl(resolver.read_path(*T1_SAMPLE)) if r["item_id"] not in valid]
    cands = {}
    with resolver.read_path(*T1_CANDIDATES).open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            cands[r["item_id"]] = r
    out = []
    for s in sample:
        c = cands[s["item_id"]]
        out.append({"item_id": s["item_id"], "md_id": c["md_id"], "paragraph_id": c["paragraph_id"],
                    "entity_class": c["entity_class"], "subject_family": c["subject_family"],
                    "obligation_span": c["obligation_span"] if isinstance(c["obligation_span"], dict) else {"text": ""},
                    "compared_classes": s["sample_compared_classes"]})
    return out


def run_t1(cfg: dict, resolver: PathResolver, system: str, items: list[dict], *, prompts: PL.Prompts,
           res: PL.Resources, extra: dict, verifier: PL.NLIVerifier | None, out_dir: Path,
           cap_tokens: int | None = None, cache_only: bool = False) -> dict[str, Any]:
    from src.llm.client import CacheMiss, CallCapReached, LLMError, QuotaPaused

    client, ledger = make_llm(cfg, resolver, f"p4_t1_{system}", long_context=system == "long_context")
    client.cache_only = cache_only
    cache_misses = 0
    active_started = time.monotonic()  # macOS: does not advance while the Mac sleeps
    done = skipped = failed = streak = 0
    cap = int(cap_tokens or cfg["p4"]["long_context"]["max_input_tokens"])
    started = time.time()
    lc = cfg["p4"]["long_context"]
    for it in items:
        path = out_dir / f"{_safe(it['item_id'])}.json"
        if path.exists():
            skipped += 1
            continue
        try:
            if system == "long_context":
                log = PL.run_long_context_item(res, prompts, client, it, max_input_tokens=cap,
                                               paras_by_md=extra["paras_by_md"],
                                               max_output_tokens=int(cfg["p4"]["max_output_tokens"]))
            else:
                scfg = SYSTEMS[system]
                scfg.per_class = int(cfg["p4"]["retrieval"]["t1_per_class"])
                scfg.depth = int(cfg["p4"]["retrieval"]["depth"])
                scfg.max_output_tokens = int(cfg["p4"]["max_output_tokens"])
                log = PL.run_t1_item(res, prompts, client, verifier if scfg.verifier else None, it, scfg)
        except QuotaPaused as exc:
            left = len(items) - done - skipped
            print(f"Quota reached — resume after {exc.resume_after_ist} IST ({left} items left in this system run)")
            return {"system": system, "paused": True, "done": done, "skipped": skipped, "left": left,
                    "resume_after_ist": exc.resume_after_ist}
        except CallCapReached as exc:
            print(f"STOP: {exc}")
            return {"system": system, "paused": True, "done": done, "skipped": skipped, "reason": str(exc)}
        except CacheMiss:
            cache_misses += 1  # cache-only: not a call, not a failure; the item stays for a normal run
            continue
        except LLMError as exc:
            # A call that keeps failing (e.g. repeated 503 on a very large prompt) is a call failure, not an
            # abstention: nothing is written, the item is listed, and a later run retries it.
            _record_failure(out_dir, it["item_id"], exc)
            failed += 1
            streak += 1
            if streak >= 3:
                print("Provider unavailable: 3 consecutive items failed; pausing (probe, then resume)", flush=True)
                return {"system": system, "paused": True, "done": done, "skipped": skipped, "failed": failed,
                        "reason": "provider_unavailable", "seconds": round(time.time() - started, 1),
                        "active_seconds": round(time.monotonic() - active_started, 1)}
            continue
        streak = 0
        log.update({"system": system, "written_utc": _now(), "prompt_sha256": prompts.hashes})
        path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        done += 1
        if done % 10 == 0:
            print(f"  {system}: {done + skipped}/{len(items)} items ({time.time() - started:.0f}s; "
                  f"quota day {ledger.quota_day()}: {ledger.used(client.slots[0].models['default'])} calls)", flush=True)
    summary = {"system": system, "paused": False, "done": done, "skipped": skipped, "failed": failed, "items": len(items),
               "cache_only": cache_only, "cache_misses": cache_misses,
               "run": client.run.summary(), "seconds": round(time.time() - started, 1),
               "active_seconds": round(time.monotonic() - active_started, 1)}
    print(f"{system}: complete ({done} new, {skipped} already written, {failed} call failures); API calls this run "
          f"{summary['run']['api_calls']}, cache hits {summary['run']['cache_hits']}")
    return summary


def run_items(cfg: dict, resolver: PathResolver, run_name: str, items: list[dict], key, work) -> dict[str, Any]:
    """Generic resumable loop: one JSON per item under data/rag_runs/<run_name>/; pauses on quota."""
    from src.llm.client import CallCapReached, LLMError, QuotaPaused

    out_dir = _runs_dir(resolver, run_name)
    client, ledger = make_llm(cfg, resolver, f"p4_{run_name}")
    done = skipped = failed = 0
    for it in items:
        path = out_dir / f"{_safe(key(it))}.json"
        if path.exists():
            skipped += 1
            continue
        try:
            log = work(client, it)
        except QuotaPaused as exc:
            left = len(items) - done - skipped
            print(f"Quota reached — resume after {exc.resume_after_ist} IST ({left} items left in this system run)")
            return {"run": run_name, "paused": True, "done": done, "skipped": skipped, "left": left}
        except CallCapReached as exc:
            print(f"STOP: {exc}")
            return {"run": run_name, "paused": True, "done": done, "skipped": skipped}
        except LLMError as exc:
            _record_failure(out_dir, key(it), exc)
            failed += 1
            continue
        log.update({"run": run_name, "written_utc": _now()})
        path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        done += 1
    s = client.run.summary()
    print(f"{run_name}: complete ({done} new, {skipped} already written, {failed} call failures); "
          f"API calls {s['api_calls']}, cache hits {s['cache_hits']}")
    return {"run": run_name, "paused": False, "done": done, "skipped": skipped, "failed": failed, "api_calls": s["api_calls"]}


def _answer_cfg(cfg: dict, **flags) -> PL.AnswerConfig:
    r = cfg["p4"]["retrieval"]
    return PL.AnswerConfig(depth=int(r["depth"]), answer_top=int(r["answer_top"]),
                           max_output_tokens=int(cfg["p4"]["max_output_tokens"]), **flags)


def cmd_t3(cfg: dict, resolver: PathResolver, args) -> int:
    """Ablation B: T3 with the temporal filter ON and OFF (everything else as final agentic; no verifier on a status)."""
    build = read_json(resolver.write_dir("benchmark") / "t3" / "t3_build_v1.json")
    if build.get("status") != "frozen":
        raise SystemExit("STOP: the T3 set is not frozen (ingest the spot-check and rebuild first)")
    items = _read_jsonl(resolver.write_dir("benchmark") / "t3" / "t3_items_v1.jsonl")
    prompts = load_prompts(cfg)
    res, _ = load_resources(cfg, resolver)
    for mode in (args.temporal or ["on", "off"]):
        on = mode == "on"
        s = run_items(cfg, resolver, f"t3_temporal_{mode}", items, lambda it: it["t3_id"],
                      lambda client, it: PL.run_t3_item(res, prompts, client, it, temporal_filter=on,
                                                        cfg=_answer_cfg(cfg, class_filter=True, temporal_filter=on,
                                                                        verifier=False)))
        if s["paused"]:
            return 1
    return 0


def cmd_t4(cfg: dict, resolver: PathResolver, args) -> int:
    """Ablation C on the P3-002 T4 questions: verifier OFF, then ON (ON's first prompt is OFF's, from the cache)."""
    qs = _read_jsonl(resolver.read_path("benchmark", "t4", "t4_questions_v1.jsonl"))
    prompts = load_prompts(cfg)
    res, _ = load_resources(cfg, resolver)
    verifier = load_verifier(cfg)
    for mode in (args.verifier or ["off", "on"]):
        on = mode == "on"
        acfg = _answer_cfg(cfg, class_filter=True, temporal_filter=True, verifier=on)

        def work(client, q, on=on, acfg=acfg):
            log = PL.answer(res, prompts, client, verifier if on else None, q["question"],
                            entity_class=q["entity_class"], subject_family=q.get("subject_family"), as_of=None, cfg=acfg)
            if not on and log["result"]["can_answer"]:
                # the NLI proxy is measured on OFF answers too (offline, no LLM call)
                final = log["steps"][-1]
                log["result"]["supported"] = PL.verify_sentences(res, final["sentences"], final["shown"], verifier)
            log["question_id"] = q["question_id"]
            return log

        s = run_items(cfg, resolver, f"t4_verifier_{mode}", qs, lambda q: q["question_id"], work)
        if s["paused"]:
            return 1
    return 0


def cmd_t2(cfg: dict, resolver: PathResolver, _args) -> int:
    """T2 (no LLM): the final pipeline's retrieval stage (class filter + function headings of the same family,
    source excluded; T2 has no as-of date, so the temporal filter is inactive) on the three P3-001 relevance sets,
    and ablation A on T2 (class filter off). Rankings written to data/rag_runs/t2/."""
    t2 = resolver.write_dir("benchmark") / "t2"
    fam_t1 = {it["item_id"]: it.get("subject_family") for it in _items(resolver)}
    fam_p2002 = {k: v.get("subject_family") for k, v in
                 read_json(resolver.read_path("benchmark", "matching", "p2002_validation_key_v1.json"))["pairs"].items()}
    res, _ = load_resources(cfg, resolver)
    depth = int(cfg["p4"]["retrieval"]["depth"])
    out = _runs_dir(resolver, "t2")
    for name in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        rows = []
        for q in _read_jsonl(t2 / f"{name}_v1.jsonl"):
            fam = fam_t1.get(q["cluster"]) if name == "t2_xclass_t1" else fam_p2002.get(q["query_id"]) if name == "t2_xclass_p2002" else None
            for system, cf in (("pipeline_class_filter_on", True), ("pipeline_class_filter_off", False)):
                ranked = PL.retrieve(res, q["text"], exclude_pid=q.get("source_paragraph_id"),
                                     entity_class=q.get("target_class"), subject_family=fam,
                                     class_filter=cf and bool(q.get("target_class")), depth=depth)
                rows.append({"query_id": q["query_id"], "system": system, "ranked": ranked,
                             "class_filter_applied": cf and bool(q.get("target_class")), "subject_family": fam})
        (out / f"runs_{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        print(f"{name}: {len(rows) // 2} queries ranked (pipeline ON / OFF)")
    return 0


DEMOS = [
    ("An entity-class-specific query",
     ["What minimum share of the loan portfolio must consist of loans of up to Rs 25 lakh?", "--class", "Small Finance Banks"]),
    ("A date-specific query",
     ["How often must the bank submit its Form B return, and on which day?", "--class", "Rural Co-operative Banks",
      "--as-of", "2025-12-01"]),
    ("One query with the class filter", ["What must be in place before IT services are outsourced?", "--class", "Payments Banks"]),
    ("The same query without the class filter",
     ["What must be in place before IT services are outsourced?", "--class", "Payments Banks", "--no-class-filter"]),
]


def cmd_demo(cfg: dict, resolver: PathResolver, args) -> int:
    """Run scripts/demo.py for the report's transcripts (real CLI output, saved under data/rag_runs/demo/).
    ``--groq-demo``: only after the Gemini outage cutoff; each transcript is labelled as not the evaluated configuration."""
    import subprocess

    out = _runs_dir(resolver, "demo")
    extra = ["--groq-outage-fallback"] if getattr(args, "groq_demo", False) else []
    for n, (title, argv) in enumerate(DEMOS, 1):
        path = out / f"demo_{n}.json"
        if path.exists():
            continue
        argv = [*argv, *extra]
        proc = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "demo.py"), *argv], capture_output=True, text=True)
        text = proc.stdout.strip()
        if proc.returncode != 0:
            # A failed call (quota, 503, network) is not a transcript: nothing is saved; rerun later.
            print(f"demo {n}: not saved (exit {proc.returncode}): {text[-200:]}")
            return 1
        cmd = "python3 scripts/demo.py " + " ".join(f'"{a}"' if " " in a else a for a in argv)
        path.write_text(json.dumps({"title": title + (" (Groq gpt-oss-120b, Gemini outage; not the evaluated configuration)"
                                                      if extra else ""), "command": cmd, "output": text,
                                    "returncode": proc.returncode, "model": "groq" if extra else "gemini"},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"demo {n}: {title} (exit {proc.returncode})")
    return 0


def _finals(resolver: PathResolver, system: str) -> dict[str, dict]:
    d = resolver.working_root / "data" / "rag_runs" / f"t1_{system}"
    return {json.loads(p.read_text())["item_id"]: json.loads(p.read_text())["final"] for p in sorted(d.glob("t1_*.json"))} if d.exists() else {}


def _repass_scores(cfg: dict, resolver: PathResolver, mode: str, logs: dict[str, dict], res) -> dict[str, float]:
    """RePASs composite for T4 ablation-C answers, through the P3-002 wrapper in its own env (their code unchanged)."""
    import subprocess

    out = _runs_dir(resolver, f"t4_verifier_{mode}") / "_repass_scores.json"
    if out.exists():
        return json.loads(out.read_text())
    payload = []
    for qid, log in sorted(logs.items()):
        r = log["result"]
        payload.append({"QuestionID": qid, "RetrievedPassages": [" ".join(res.text(p).split()) for p in r["evidence"]],
                        "Answer": r["answer"]})
    inp = _runs_dir(resolver, f"t4_verifier_{mode}") / "_repass_input.json"
    inp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    group = f"p4001_t4_verifier_{mode}_v1"
    proc = subprocess.run([str(REPO_ROOT / "external" / ".venv-repass" / "bin" / "python"),
                           str(REPO_ROOT / "scripts" / "run_repass.py"), "score", "--input", str(inp), "--group", group],
                          capture_output=True, text=True)
    if proc.returncode:
        raise SystemExit(f"STOP: RePASs scoring failed: {proc.stderr[-1500:]}")
    import csv as _csv

    with (REPO_ROOT / "external" / "RePASs" / "data" / group / "results.csv").open(encoding="utf-8") as h:
        scores = {r["QuestionID"]: float(r["composite_score"]) for r in _csv.DictReader(h)}
    out.write_text(json.dumps(scores, indent=1))
    return scores


def cmd_report(cfg: dict, resolver: PathResolver, _args) -> int:
    import importlib.metadata as md
    import importlib.util
    import platform

    from src.eval import metrics as M
    from src.eval import t1_eval as TE
    from src.llm.client import QuotaLedger
    from src.rag import analysis as A
    from src.rag import p4_report

    R = int(cfg["retrieval"]["eval"]["bootstrap_resamples"])
    seed = int(cfg["p4"]["seeds"]["bootstrap"])
    kw = {"resamples": R, "seed": seed}
    gold = _items(resolver)

    # --- T1
    cands = {}
    with resolver.read_path(*T1_CANDIDATES).open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            cands[r["source_candidate_id"]] = r
    units = TE.gold_units(gold)
    maj = TE.majority_predictions(gold)
    p2 = TE.p2002_predictions(gold, cands)
    mapping = TE.default_fixed_mapping(gold)

    def as_final(pred, fixed):
        out, j = {}, 0
        for it, f in zip(gold, pred["flags"]):
            per = {}
            for c in sorted(it["compared_classes"]):
                per[c] = {"judgement": fixed.get(pred["judgements"][j], pred["judgements"][j])}
                j += 1
            out[it["item_id"]] = {"flag": fixed.get(f, f), "per_class": per}
        return out

    preds = {"majority": as_final(maj, {}), "p2002_candidates": as_final(p2, mapping)}
    # Long-context: the main result comes only from the reduced-cap rerun (64K if the pre-committed step-down ran,
    # else 100K); the 150K run is shown in an appendix as superseded (D10), nothing computed is hidden.
    lc_cap, lc_name = None, None
    for cap_try in (64000, 100000):
        fb_dir = resolver.working_root / "data" / "rag_runs" / f"t1_long_context_cap{cap_try // 1000}k"
        if fb_dir.exists() and any(fb_dir.glob("t1_*.json")):
            lc_name, lc_cap = fb_dir.name.removeprefix("t1_"), cap_try
            break
    for s_ in ("class_blind", "class_aware", "final_agentic", "ablation_a"):
        f = _finals(resolver, s_)
        if f:
            preds[s_] = f
    if lc_name:
        preds["long_context"] = _finals(resolver, lc_name)
    U = {s_: A.t1_units(gold, p) for s_, p in preds.items()}
    t1 = {"systems": {s_: A.t1_metrics(u, **kw) for s_, u in U.items()}, "paired": {}}
    pairs = [("Ablation A (verifier on): final agentic − class-blind + verifier", "final_agentic", "ablation_a"),
             ("Class filter, no verifier: class-aware − class-blind", "class_aware", "class_blind"),
             ("Ablation C on T1: final agentic − class-aware", "final_agentic", "class_aware"),
             ("Verifier, class-blind: ablation A − class-blind", "ablation_a", "class_blind"),
             ("Class-blind LLM − P2-002 candidates", "class_blind", "p2002_candidates"),
             ("Class-aware LLM − P2-002 candidates", "class_aware", "p2002_candidates"),
             ("Final agentic − P2-002 candidates", "final_agentic", "p2002_candidates"),
             ("Class-blind + verifier − P2-002 candidates", "ablation_a", "p2002_candidates")]
    if "long_context" in U:
        pairs += [("Long-context − majority (same items)", "long_context", "majority"),
                  ("Long-context − P2-002 candidates (same items)", "long_context", "p2002_candidates"),
                  ("Long-context − class-blind (same items)", "long_context", "class_blind"),
                  ("Long-context − class-aware (same items)", "long_context", "class_aware"),
                  ("Long-context − final agentic (same items)", "long_context", "final_agentic"),
                  ("Long-context − class-blind + verifier (same items)", "long_context", "ablation_a")]
    for label, a_, b_ in pairs:
        if a_ in U and b_ in U:
            t1["paired"][label] = A.t1_paired(U[a_], U[b_], **kw)
    outage = _outage_window(resolver)
    t1["outage"] = outage
    res_lc, extra_lc = load_resources(cfg, resolver)
    prompts_lc = load_prompts(cfg)
    by_id = {it["item_id"]: it for it in gold}

    def est(k, cap):
        return PL.long_context_messages(prompts_lc, res_lc, by_id[k], max_input_tokens=cap,
                                        paras_by_md=extra_lc["paras_by_md"])[1]["input_chars"] // 4

    def dist(keys, cap):
        v = sorted(est(k, cap) for k in keys)
        return {"n": len(v), "median": v[len(v) // 2], "min": v[0], "max": v[-1]} if v else None

    others = ("majority", "p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a")
    if "long_context" not in U:
        t1["long_context_status"] = (f"pending (API outage since {outage['first_503_ist'] or '20:10 IST'})"
                                     if outage.get("first_503_ist") else "pending (API outage since 20:10 IST)")
    else:
        lc_dir = resolver.working_root / "data" / "rag_runs" / f"t1_{lc_name}"
        lcl = [json.loads(p.read_text()) for p in sorted(lc_dir.glob("t1_*.json"))]
        scored = sorted(U["long_context"]["items"])
        unscored = sorted(set(by_id) - set(scored))
        n_all = len(gold)
        passes_all = {}
        for dname in ("long_context", "long_context_cap100k", "long_context_cap64k"):
            pf_ = resolver.working_root / "data" / "rag_runs" / f"t1_{dname}" / "_passes.jsonl"
            if pf_.exists():
                passes_all[dname] = [json.loads(x) for x in open(pf_)]
        pm = resolver.working_root / "data" / "rag_runs" / "runtime_150k_from_pmset.json"
        runtime = {"passes": passes_all, "pmset_150k": json.loads(pm.read_text()) if pm.exists() else None}
        policy = (f"Reported baseline: uniform {lc_cap:,}-token cap for all {n_all} items, same proportional per-class "
                  f"truncation. Items whose prompt is under the cap send exactly the prompt of the earlier run and were served "
                  f"from the cache (identical prompt, no new call). Answered: {len(scored)}/{n_all}; unscored: {len(unscored)} "
                  f"({len(unscored) / n_all:.0%}). Truncated at this cap: {sum(1 for l in lcl if l['truncation']['truncated'])} "
                  "of the scored items. "
                  + ("Unscored items remain, so long-context is reported ONLY on the scored items, with the size distribution of "
                     "scored vs unscored, and every system is compared on exactly those items (no further cap change, no model switch)."
                     if unscored else "Every item was answered."))
        ret_items = []
        for k in scored:
            it = by_id[k]
            golds = [it["matched_paragraph_id"][c] for c in it["compared_classes"]
                     if it["per_class_judgement"][c] in ("same", "different") and it["matched_paragraph_id"].get(c)]
            if not golds:
                continue
            body = PL.long_context_messages(prompts_lc, res_lc, it, max_input_tokens=lc_cap, paras_by_md=extra_lc["paras_by_md"])[0][1]["content"]
            kept = [g for g in golds if f"[{g}]" in body]
            ret_items.append({"item_id": k, "gold_paragraphs": len(golds), "retained": len(kept),
                              "all_retained": len(kept) == len(golds),
                              "flag_correct": preds["long_context"][k]["flag"] == it["differential_flag"]})

        def acc_(rows):
            return (sum(r["flag_correct"] for r in rows) / len(rows)) if rows else None

        kept_rows = [r for r in ret_items if r["all_retained"]]
        cut_rows = [r for r in ret_items if not r["all_retained"]]
        no_gold = [k for k in scored if not any(by_id[k]["per_class_judgement"][c] in ("same", "different")
                                                for c in by_id[k]["compared_classes"])]
        retention_accounting = {
            "scored": len(scored), "all_gold_kept": len(kept_rows), "at_least_one_cut": len(cut_rows),
            "no_gold_matched_paragraph": len(no_gold),
            "no_gold_reason": dict(Counter(
                "gold flag absent: every compared-class judgement is 'none', so there is no gold matched paragraph"
                if by_id[k]["differential_flag"] == "absent" and set(by_id[k]["per_class_judgement"].values()) == {"none"}
                else "other" for k in no_gold))}
        retention = {"cap": lc_cap, "accounting": retention_accounting, "items_with_gold_paragraphs": len(ret_items),
                     "gold_paragraphs": sum(r["gold_paragraphs"] for r in ret_items),
                     "gold_paragraphs_retained": sum(r["retained"] for r in ret_items),
                     "items_all_retained": len(kept_rows), "items_some_cut": len(cut_rows),
                     "flag_accuracy_all_retained": acc_(kept_rows), "flag_accuracy_some_cut": acc_(cut_rows),
                     "note": "diagnostic, no LLM calls; items whose gold has no same/different class are not counted"}
        same_items = {sname: A.t1_metrics(A.subset_units(U[sname], set(scored)), **kw)
                      for sname in (*others, "long_context") if sname in U}
        t1["long_context_same_items"] = {"n": len(scored), "systems": same_items, "policy": policy, "runtime": runtime,
                                          "gold_retention": retention, "cap": lc_cap,
                                          "token_distribution": {"scored": dist(scored, lc_cap), "unscored": dist(unscored, lc_cap)}}
        same = t1["paired"].get("Long-context − final agentic (same items)")
        win = same and same["flag_macro_f1"]["reading"] == ABOVE
        t1["long_context_note"] = (
            f"Uniform {lc_cap:,}-token cap (D10). {len(scored)} of {n_all} items scored. 3-way flag Macro-F1 "
            f"{_fmt(t1['systems']['long_context']['flag_macro_f1'])}. "
            + ("**The long-context LLM beats the final agentic pipeline on the same items** (paired CI above 0)." if win else
               "Its paired differences against the other systems on the same items are in the table above."))
    # Appendix: the 150K run, superseded by the 100K rerun, shown for completeness (D10).
    d150 = resolver.working_root / "data" / "rag_runs" / "t1_long_context"
    f150 = _finals(resolver, "long_context")
    if f150:
        fl = d150 / "_call_failures.jsonl"
        failed150 = {json.loads(x)["key"] for x in open(fl)} if fl.exists() else set()
        u150 = A.t1_units(gold, f150)
        items150 = set(u150["items"])
        t1["appendix_150k"] = {
            "label": "superseded by the 100K rerun, shown for completeness",
            "n": len(items150),
            "systems": {"long_context_150k": A.t1_metrics(u150, **kw),
                        **{sname: A.t1_metrics(A.subset_units(U[sname], items150), **kw) for sname in others if sname in U}},
            "paired_vs_final_agentic": A.t1_paired(u150, U["final_agentic"], **kw) if "final_agentic" in U else None,
            "paired_vs_every_system": {sname: A.t1_paired(u150, U[sname], **kw) for sname in others if sname in U},
            "token_distribution": {"scored": dist(sorted(items150), 150000),
                                   "attempted, never answered": dist(sorted(failed150 - items150), 150000),
                                   "never attempted (run stopped)": dist(sorted(set(by_id) - items150 - failed150), 150000)},
            "note": "Computed in Claude's session before the rerun decision (D10). The items attempted but never answered are "
                    "the large prompts; the never-attempted items are simply those the run had not reached.",
        }
    unsure = t1["systems"].get("final_agentic", {}).get("unsure_judgements")
    pc_ = t1["paired"].get("Ablation C on T1: final agentic − class-aware")
    t1["verifier_note"] = (
        (f"Final agentic − class-aware: 3-way flag F1 {_pfmt(pc_['flag_macro_f1'])}, coverage {_pfmt(pc_['coverage'])} (n = 106). " if pc_ else "")
        + f"The verifier turned judgements into `unsure` (an abstention): final agentic has {unsure} `unsure` judgements "
        f"against {t1['systems'].get('class_aware', {}).get('unsure_judgements')} for class-aware. No threshold or rule was changed.")
    dpath = resolver.working_root / "data" / "rag_runs" / "verifier_diagnostics_post_hoc.json"
    if dpath.exists():
        t1["verifier_diagnostics"] = json.loads(dpath.read_text())

    # --- T2
    t2dir = resolver.write_dir("benchmark") / "t2"
    p3 = read_json(resolver.read_path("reports", "p3001_metrics_v1.json"))
    bias_short = {"t2_xclass_t1": "favours dense", "t2_xclass_p2002": "favours dense", "t2_supp_p2003": "favours BM25"}
    t2 = {}
    for name in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        qrels = {q["query_id"]: q["relevant"] for q in _read_jsonl(t2dir / f"{name}_v1.jsonl")}
        runs: dict[str, dict] = {}
        for line in (resolver.working_root / "data" / "rag_runs" / "t2" / f"runs_{name}.jsonl").read_text().splitlines():
            r = json.loads(line)
            runs.setdefault(r["system"], {})[r["query_id"]] = r["ranked"]
        per = {s: M.per_query_scores(runs[s], qrels, 10)["ndcg"] for s in runs}
        qids = sorted(per["pipeline_class_filter_on"])
        on = [per["pipeline_class_filter_on"][q] for q in qids]
        off = [per["pipeline_class_filter_off"][q] for q in qids]
        bm_on, bm_off = M.bootstrap_mean(on, **kw), M.bootstrap_mean(off, **kw)
        pb = M.paired_bootstrap(on, off, **kw)
        ps = p3["sets"][name]["systems"]
        t2[name] = {"n": len(qids), "bias_short": bias_short[name],
                    "on": {"value": bm_on["mean"], "ci": [bm_on["ci_low"], bm_on["ci_high"]]},
                    "off": {"value": bm_off["mean"], "ci": [bm_off["ci_low"], bm_off["ci_high"]]},
                    "paired": {"diff": pb["mean"], "ci": [pb["ci_low"], pb["ci_high"]],
                               "reading": ci_reading(pb["ci_low"], pb["ci_high"])},
                    "p3001_class_aware": f"{ps['class_aware']['ndcg']['mean']:.3f}",
                    "p3001_minus_source": f"{ps['hybrid_minus_source_class']['ndcg']['mean']:.3f}"}

    # --- T3
    t3 = None
    t3dir = resolver.write_dir("benchmark") / "t3"
    t3_items = _read_jsonl(t3dir / "t3_items_v1.jsonl")
    dropped = read_json(t3dir / "t3_dropped_after_check2_v1.json")["dropped_items"] if (t3dir / "t3_dropped_after_check2_v1.json").exists() else []
    t3_items = [i for i in t3_items if i["t3_id"] not in set(dropped)]
    b3 = read_json(resolver.write_dir("benchmark") / "t3" / "t3_build_v1.json")
    runs3 = {}
    for mode in ("on", "off"):
        d = resolver.working_root / "data" / "rag_runs" / f"t3_temporal_{mode}"
        runs3[mode] = {json.loads(p.read_text())["t3_id"]: json.loads(p.read_text()) for p in sorted(d.glob("T3-*.json"))} if d.exists() else {}
    if runs3["on"] and runs3["off"]:
        t3 = {"on": A.t3_metrics(t3_items, runs3["on"], **kw), "off": A.t3_metrics(t3_items, runs3["off"], **kw),
              "paired": A.t3_paired(t3_items, runs3["on"], runs3["off"], **kw)}
        win_items = [i for i in t3_items if i["effective"].get("window")]
        no_win = [i for i in t3_items if not i["effective"].get("window")]
        t3["sensitivity_no_window"] = {
            "excluded": len(win_items), "excluded_ids": [i["t3_id"] for i in win_items],
            "excluded_bases": dict(Counter(i["effective"]["basis"] for i in win_items)),
            "on": A.t3_metrics(no_win, runs3["on"], **kw), "off": A.t3_metrics(no_win, runs3["off"], **kw),
            "paired": A.t3_paired(no_win, runs3["on"], runs3["off"], **kw)}
    pr = b3["precision"]
    t3_setup = (f"60 (paragraph, as-of date) items from {b3['items']['directions']} Directions, 30 before and 30 after the "
                f"effective date, gold {b3['items']['gold']}. Parser: {b3['parsed_actions']} parsed actions from "
                f"{b3['instructions']['verbs']} amendment instructions (rules {b3['rules_version']}). Parse precision on Karan's "
                f"20-row spot-check: rules v1 {pr['rules_v1_human']['k']}/20 (Wilson {pr['rules_v1_human']['wilson_95'][0]:.2f}–"
                f"{pr['rules_v1_human']['wilson_95'][1]:.2f}); after one rule fix (merged within-paragraph changes, per-item "
                f"exception dates, 'dated' references ignored), the same 20 rows: {pr['rules_v2_same_20_rows']['k']}/20 "
                f"(Wilson {pr['rules_v2_same_20_rows']['wilson_95'][0]:.2f}–{pr['rules_v2_same_20_rows']['wilson_95'][1]:.2f}), "
                "assessed against Karan's notes, not re-checked by a human. The target paragraph is pinned into the evidence "
                "(a deleted one stays, marked); the verifier does not apply to a status answer.")

    rc2 = t3dir / "t3_spotcheck2_receipt_v1.json"
    acts3 = {a["action_id"]: a for a in _read_jsonl(t3dir / "t3_actions_v1.jsonl")}
    all3 = _read_jsonl(t3dir / "t3_items_v1.jsonl")
    spec3 = importlib.util.spec_from_file_location("run_t3", REPO_ROOT / "scripts" / "run_t3.py")
    rt3 = importlib.util.module_from_spec(spec3)
    spec3.loader.exec_module(rt3)
    checked = rt3._checked_action_ids(t3dir)
    from_checked = [i["t3_id"] for i in all3 if i["action_id"] in checked]
    multi = [i["t3_id"] for i in all3 if len(acts3[i["action_id"]].get("changes") or []) > 1]
    p1 = pr["rules_v1_human"]
    t3_precision = [
        f"**Human-measured parse precision (rules v1): {p1['k']}/{p1['n']} = {p1['value']:.2f}, Wilson 95% [{p1['wilson_95'][0]:.2f}, {p1['wilson_95'][1]:.2f}].**",
        f"Post-fix, same rows the fix was designed on (in-sample): {pr['rules_v2_same_20_rows']['k']}/20. This is Claude's reading of "
        "Karan's notes on the rows that motivated the fix, not an independent measurement.",
        (f"Independent post-fix check (10 seeded parses behind frozen items, none among the first 20): "
         f"{read_json(rc2)['precision']['k']}/{read_json(rc2)['precision']['n']}, Wilson 95% "
         f"[{read_json(rc2)['precision']['wilson_95'][0]:.2f}, {read_json(rc2)['precision']['wilson_95'][1]:.2f}]"
         + (f"; {len(dropped)} dependent items dropped ({', '.join(dropped)}) and T3 recomputed on the remaining {len(t3_items)}."
            if dropped else "; no item dropped.")
         + (" Display note: both parses marked wrong are 'adoption or 1 April 2026, whichever is earlier' amendments. The parser "
            "stores them as a window [publication date, 1 April 2026] (status unknown inside it); the sheet printed that as "
            "'window: 2025-12-04 to 2026-04-01 (whichever earlier)', which the rater read as a claimed effective date of 4 December "
            "2025. The dropped items' as-of dates lie outside the window (before publication / after 1 April 2026), so their gold "
            "would be the same under either reading; the human labels stand as recorded and the drop is kept (conservative)."
            if dropped else "")) if rc2.exists() else
        "Independent post-fix check (10 seeded parses behind frozen items, none among the first 20): **pending**, sheet "
        "`data/benchmark/t3/t3_spotcheck2_sheet_v1.csv` is with Karan.",
        f"Of the 60 frozen items, {len(from_checked)} come from the 20 checked parses ({len(checked & {i['action_id'] for i in all3})} parses: "
        f"{', '.join(from_checked)}); the other {60 - len(from_checked)} rest on parses not in the first check.",
        f"{len(multi)} items come from multi-change instructions affected by the known 'old words' defect (a merged change's "
        f"recorded old words also include the previous change's new words; it can only exclude candidates as corpus-version "
        f"'unclear', never change an included item's gold): {', '.join(multi)}.",
    ]

    # --- T4 ablation C
    t4 = None
    logs4 = {}
    for mode in ("on", "off"):
        d = resolver.working_root / "data" / "rag_runs" / f"t4_verifier_{mode}"
        logs4[mode] = {json.loads(p.read_text())["question_id"]: json.loads(p.read_text()) for p in sorted(d.glob("T4Q*.json"))} if d.exists() else {}
    if len(logs4["on"]) == 30 and len(logs4["off"]) == 30:
        res, _ = load_resources(cfg, resolver)
        rp = {m: _repass_scores(cfg, resolver, m, logs4[m], res) for m in ("on", "off")}
        bad = {"T4Q14", "T4Q30"}
        t4 = {}
        for label, keep in (("n28", [q for q in sorted(logs4["on"]) if q not in bad]), ("n30", sorted(logs4["on"]))):
            rows = {m: [A.t4_per_question(logs4[m][q]) for q in keep] for m in ("on", "off")}
            mets = {m: A.t4_metrics(rows[m], [rp[m][q] for q in keep], **kw) for m in ("on", "off")}
            n = len(keep)
            d_on = {m: np.array([r["delivered_sentences"] for r in rows[m]], float) for m in rows}
            u_on = {m: np.array([r["unsupported_sentences"] for r in rows[m]], float) for m in rows}
            ab = {m: np.array([r["abstained_by_verifier"] or r["model_declined"] for r in rows[m]], float) for m in rows}
            rpa = {m: np.array([rp[m][q] for q in keep], float) for m in rows}

            def rate(m):
                return lambda i: float(u_on[m][i].sum() / d_on[m][i].sum()) if d_on[m][i].sum() else float("nan")

            ans = [j for j, q in enumerate(keep) if rows["on"][j]["answered"]]
            if ans:
                ia = np.array(ans)
                na = len(ans)
                d_a = {m: d_on[m][ia] for m in rows}
                u_a = {m: u_on[m][ia] for m in rows}
                rp_a = {m: rpa[m][ia] for m in rows}

                def rate_a(m):
                    return lambda i: float(u_a[m][i].sum() / d_a[m][i].sum()) if d_a[m][i].sum() else float("nan")

                mets["answered_only"] = {
                    "n": na, "items": [keep[j] for j in ans],
                    "unsupported_sentence_rate": {m: A.boot(na, rate_a(m), **kw) for m in rows},
                    "repass_composite": {m: A.boot(na, (lambda mm: lambda i: float(rp_a[mm][i].mean()))(m), **kw) for m in rows},
                    "paired": {"unsupported_sentence_rate": A.paired(na, rate_a("on"), rate_a("off"), **kw),
                               "repass_composite": A.paired(na, lambda i: float(rp_a["on"][i].mean()),
                                                            lambda i: float(rp_a["off"][i].mean()), **kw)}}
            mets["paired"] = {"unsupported_sentence_rate": A.paired(n, rate("on"), rate("off"), **kw),
                              "abstention_rate": A.paired(n, lambda i: float(ab["on"][i].mean()), lambda i: float(ab["off"][i].mean()), **kw),
                              "repass_composite": A.paired(n, lambda i: float(rpa["on"][i].mean()), lambda i: float(rpa["off"][i].mean()), **kw)}
            t4[label] = mets

    # --- ablation table
    def row(ab_, toggle, measure, on_v, off_v, pv, n):
        return {"ablation": ab_, "toggle": toggle, "measure": measure, "on": _fmt(on_v), "off": _fmt(off_v),
                "diff": _pfmt(pv), "n": n}

    S1, P1 = t1["systems"], t1["paired"]
    table = []
    if "final_agentic" in S1 and "ablation_a" in S1:
        pa = P1["Ablation A (verifier on): final agentic − class-blind + verifier"]
        table.append(row("A", "class filter", "T1 3-way flag Macro-F1", S1["final_agentic"]["flag_macro_f1"], S1["ablation_a"]["flag_macro_f1"], pa["flag_macro_f1"], pa["n_items"]))
        table.append(row("A", "class filter", "T1 collapsed Macro-F1", S1["final_agentic"]["collapsed_macro_f1"], S1["ablation_a"]["collapsed_macro_f1"], pa["collapsed_macro_f1"], pa["n_items"]))
    for name, v in t2.items():
        table.append(row("A", "class filter", f"T2 nDCG@10, {name}", v["on"], v["off"], v["paired"], v["n"]))
    if t3:
        table.append(row("B", "temporal filter", "T3 status exact match", t3["on"]["status_exact_match"], t3["off"]["status_exact_match"], t3["paired"]["status_exact_match"], t3["paired"]["n"]))
        table.append(row("B", "temporal filter", "T3 supersession F1", t3["on"]["supersession_f1"], t3["off"]["supersession_f1"], t3["paired"]["supersession_f1"], t3["paired"]["n"]))
    if "final_agentic" in S1 and "class_aware" in S1:
        pc = P1["Ablation C on T1: final agentic − class-aware"]
        table.append(row("C", "verifier", "T1 3-way flag Macro-F1", S1["final_agentic"]["flag_macro_f1"], S1["class_aware"]["flag_macro_f1"], pc["flag_macro_f1"], pc["n_items"]))
        table.append(row("C", "verifier", "T1 coverage", S1["final_agentic"]["coverage"], S1["class_aware"]["coverage"], pc["coverage"], pc["n_items"]))
    if t4:
        for key, lab in (("unsupported_sentence_rate", "T4 unsupported-sentence rate (NLI proxy)"),
                         ("abstention_rate", "T4 abstention rate"), ("repass_composite", "T4 RePASs composite")):
            table.append(row("C", "verifier", lab + " (n=28)", t4["n28"]["on"][key], t4["n28"]["off"][key], t4["n28"]["paired"][key], 28))

    demo_dir = resolver.working_root / "data" / "rag_runs" / "demo"
    demos = [json.loads(p.read_text()) for p in sorted(demo_dir.glob("demo_*.json"))] if demo_dir.exists() else []
    for d_ in demos:
        if "original in force; amended from" in d_["output"] and "--as-of" in d_["command"]:
            d_["note"] = ("Limitation shown by this transcript: the temporal filter correctly marks the paragraph as 'original in "
                          "force; amended from <date>', but the corpus holds only the current (amended) text of each Direction, so "
                          "the answer states the post-amendment rule for a date before the amendment took effect. The pipeline can "
                          "mark an amendment; it cannot show the pre-amendment wording, which the corpus does not keep.")
    ledger = QuotaLedger(resolver.working_root / cfg["p4"]["ledger"], soft_cap=int(cfg["p4"]["soft_cap"]))
    led = json.loads(ledger.path.read_text()) if ledger.path.exists() else {}
    n_lc = t1["systems"].get("long_context", {}).get("n_items") or t1.get("long_context_status", "pending")
    ow = t1.get("outage") or {}
    limitations = [
        (f"API outage: `{cfg['llm']['p4_model']}` returned HTTP 503 'high demand' to every call from {ow.get('first_503_ist')} IST"
         + (f" until the first successful probe at {ow['first_ok_after_outage_ist']} IST" if ow.get("first_ok_after_outage_ist") else "")
         + f"; intermittent 503s continued during the runs, the last at {ow.get('last_503_ist')} IST ({ow.get('probes_unavailable')} "
         f"of {ow.get('probes')} probes unavailable). The long-context runs paused and resumed around them; no model switch was made."
         if ow.get("first_503_ist") else "No API outage recorded."),
        f"The P4 LLM is a free Flash-Lite-class model (`{cfg['llm']['p4_model']}`); P3-002's genuine answers used Groq "
        "`openai/gpt-oss-120b`. These results describe this model, not frontier models.",
        "The prompt cache is shared between paired systems (see Shared prompts): at temperature 0 this is identical to re-calling.",
        f"Long-context: {n_lc}" + (" items (not the full 106; compare on the same items only)" if isinstance(n_lc, int) and n_lc < 106 else "")
        + "; truncation to the cap is proportional per class and counted per item; call failures are listed, never scored.",
        "T3 circularity: the gold and the temporal filter come from the same parser; T3 measures whether the LLM uses the dates.",
        "Temporal: the corpus holds only the current (amended) text of each Direction. The system can flag that a paragraph was "
        "amended later ('original in force; amended from <date>'), but it cannot show the pre-amendment wording, so for an "
        "as-of date before an amendment it may state the post-amendment rule (see the date-specific demo transcript).",
        "T3 parse precision after the rule fix is Claude's reading of Karan's notes on the same 20 rows, not a new human check.",
        "The T1 verifier (whole cited paragraph as NLI premise, fixed rule) abstains on about a fifth of items and does not raise "
        "precision on the items it keeps (post hoc diagnostic a); a single-sentence premise would not raise support (diagnostic b).",
        "T3 parse precision: only 6 of the 60 frozen items rest on parses in the first human check; the independent check covers "
        "10 more parses (24 items).",
        "The T4 unsupported-sentence rate is an NLI proxy, and the verifier and RePASs share an NLI model.",
        f"n per task: T1 106 items (long-context {n_lc}); T2 {', '.join(f'{k} {v['n']}' for k, v in t2.items())}; T3 "
        f"{t3['paired']['n'] if t3 else 'not run'}; T4 28 primary (30 shown). One human rater for every human label.",
        "The class-aware gain is for retrieving/judging against the named target class; it is not a general class-blind vs "
        "class-aware verdict (P3-001).",
        "The P3-002 gameability verdict uses its pre-registered rule (reproduces iff the CI lies at or above 0). P4 labels use "
        "'excludes 0' only when the CI is strictly above or below 0. No reported P3-002 result lies on the boundary, so the two "
        "conventions never disagree here (checked: none of the 12 P3-002 verdict CIs, 6 gameability and 6 repair ranking, "
        "main and sensitivity, has a bound at 0).",
    ]
    env = {"model": cfg["llm"]["p4_model"], "model_version": cfg["llm"].get("p4_model_version"),
           "thinking": cfg["p4"].get("thinking"), "nli_model": cfg["p4"]["verifier"]["nli_model"],
           "nli_revision": cfg["p4"]["verifier"]["nli_revision"], "ledger": led,
           "machine": platform.platform(), "python": platform.python_version(),
           "packages": {p: _ver(md, p) for p in ("torch", "transformers", "sentence-transformers", "bm25s", "numpy")}}
    summary = []
    if t2:
        summary.append("The class filter improves T2 retrieval: nDCG@10 ON − OFF "
                       + ", ".join(f"{k} {_pfmt(v['paired'])}" for k, v in t2.items())
                       + ". The gain is partly built in: relevance was labelled only for the target-class counterpart.")
    pa_ = t1["paired"].get("Ablation A (verifier on): final agentic − class-blind + verifier")
    pn_ = t1["paired"].get("Class filter, no verifier: class-aware − class-blind")
    if pa_ and pn_:
        summary.append(f"The class filter shows no significant effect on T1 judgement: 3-way flag F1 {_pfmt(pa_['flag_macro_f1'])} "
                       f"with the verifier on, {_pfmt(pn_['flag_macro_f1'])} without it (n = 106).")
    pc2 = t1["paired"].get("Ablation C on T1: final agentic − class-aware")
    if pc2:
        summary.append(f"The verifier lowers T1 3-way flag F1 by {_pfmt(pc2['flag_macro_f1'])} and coverage by "
                       f"{_pfmt(pc2['coverage'])} (n = 106).")
    vs_p2 = {lab: t1["paired"][f"{lab} − P2-002 candidates"] for lab in
             ("Class-blind LLM", "Class-aware LLM", "Final agentic", "Class-blind + verifier") if f"{lab} − P2-002 candidates" in t1["paired"]}
    if vs_p2:
        beats = [lab for lab, v in vs_p2.items() if v["collapsed_macro_f1"]["ci"][0] > 0]
        summary.append(("No LLM system significantly beats the P2-002 candidate labels on collapsed F1 (the fair comparison): "
                        if not beats else f"On collapsed F1, {', '.join(beats)} significantly beat(s) P2-002; the others do not: ")
                       + "; ".join(f"{lab} − P2-002 {_pfmt(v['collapsed_macro_f1'])}" for lab, v in vs_p2.items()) + ".")
    llm_sys = {k: t1["systems"][k] for k in ("class_blind", "class_aware", "final_agentic", "ablation_a") if k in t1["systems"]}
    if llm_sys:
        top = max(llm_sys, key=lambda k: llm_sys[k]["flag_macro_f1"]["value"])
        lab_ = {"class_blind": "class-blind LLM", "class_aware": "class-aware LLM", "final_agentic": "final agentic",
                "ablation_a": "class-blind + verifier"}
        summary.append(f"The {lab_[top]} has the highest 3-way flag F1 ({llm_sys[top]['flag_macro_f1']['value']:.3f}).")
        summary.append("Every LLM system is weak on 'different' judgements (F1 "
                       + " / ".join(f"{lab_[k]} {v['judgement_f1_per_label']['different']:.3f}" for k, v in llm_sys.items())
                       + "), so class-specific differences are the benchmark's hardest case.")
    ap_ = t1.get("appendix_150k")
    if "long_context" in U:
        lab_lc = {"p2002_candidates": "P2-002", "class_blind": "class-blind", "class_aware": "class-aware",
                  "final_agentic": "final agentic", "ablation_a": "class-blind + verifier", "majority": "majority"}
        pp = {k: t1["paired"][f"Long-context − {v} (same items)"] for k, v in
              (("majority", "majority"), ("p2002_candidates", "P2-002 candidates"), ("class_blind", "class-blind"),
               ("class_aware", "class-aware"), ("final_agentic", "final agentic"), ("ablation_a", "class-blind + verifier"))}
        tied = [k for k in ("p2002_candidates", "class_blind", "class_aware")
                if pp[k]["flag_macro_f1"]["reading"] == "does not exclude 0" and pp[k]["collapsed_macro_f1"]["reading"] == "does not exclude 0"]
        fa3 = pp["final_agentic"]["flag_macro_f1"]["reading"] == "does not exclude 0"
        beats = [k for k in ("final_agentic", "ablation_a") if pp[k]["collapsed_macro_f1"]["reading"] == ABOVE]
        n_lc_ = pp["final_agentic"]["n_items"]
        sent = (f"Long-context ({lc_cap // 1000}K cap, n = {n_lc_}) is statistically tied with "
                f"{', '.join(lab_lc[k] for k in tied[:-1])}{' and ' if len(tied) > 1 else ''}{lab_lc[tied[-1]] if tied else 'no system'} "
                "on both flag metrics"
                + (f" (paired CIs: {'; '.join(lab_lc[k] + ' 3-way ' + _pfmt(pp[k]['flag_macro_f1']) + ', collapsed ' + _pfmt(pp[k]['collapsed_macro_f1']) for k in tied)})" if tied else "")
                + (f", matches final agentic on 3-way F1 ({_pfmt(pp['final_agentic']['flag_macro_f1'])})" if fa3 else "")
                + (", and beats " + " and ".join(f"{lab_lc[k]} ({_pfmt(pp[k]['collapsed_macro_f1'])})" for k in beats) + " on collapsed F1" if beats else "")
                + f". It is as weak as the other LLM systems on 'different' judgements (F1 "
                f"{t1['systems']['long_context']['judgement_f1_per_label']['different']:.3f}).")
        summary.append(sent)
    else:
        summary.append("Long-context vs final agentic at the 100K cap: pending (API outage). "
                       + (f"The superseded 150K appendix ({ap_['n']} items) shows parity on 3-way F1 "
                          f"({_pfmt(ap_['paired_vs_final_agentic']['flag_macro_f1'])}) and a collapsed-F1 advantage for long-context "
                          f"({_pfmt(ap_['paired_vs_final_agentic']['collapsed_macro_f1'])})." if ap_ and ap_.get("paired_vs_final_agentic") else ""))
    deviations = [
        {"id": "D1", "kind": "addition, before freeze", "text": "The T1 rationale instruction was reworded after format debugging on 5 rejected (non-gold) items, before the prompt freeze: the model wrote 'The matched paragraph …' meta-sentences that nothing can entail."},
        {"id": "D2", "kind": "deviation, operational", "text": "The client-side throttle estimates tokens as characters / 3 (was / 4) after a per-minute input-token 429 on ~150K-token prompts. The 12 RPM / 200K TPM limits are unchanged."},
        {"id": "D3", "kind": "addition", "text": "A call that keeps failing is recorded as a call failure (not written, not scored, never counted as an abstention) and retried on the next run."},
        {"id": "D4", "kind": "deviation (one rule fix, as the prompt allows)", "text": "T3 parser rules v2 after the spot-check (15/20): merged within-paragraph changes, per-item exception dates, 'dated <date>' references ignored. Known defect frozen with the set: merged changes' old words include the previous change's new words."},
        {"id": "D5", "kind": "addition (audit note 1)", "text": "T3 precision: v1 15/20 reported as the human figure; 20/20 only as in-sample post-fix; an independent 10-parse check (spot-check 2) on parses behind frozen items; items from the checked parses and from defect-affected instructions listed."},
        {"id": "D6", "kind": "deviation (audit note 2)", "text": "Long-context calls: at most 3 attempts per item per run with exponential backoff and jitter, every attempt in the ledger; network drops and read timeouts retried as transient; a 300 s read timeout for these prompts; after the remainder run and one full retry pass, > 20% of the 30-item subset still failing triggers a rerun of the whole baseline at one uniform 100K cap. Prompt-token distributions of scored vs failed items are reported and every system is compared on exactly the scored items."},
        {"id": "D7", "kind": "addition (audit note 3), post hoc", "text": "Verifier diagnostics without LLM calls: precision on non-abstained items, and support under a best-single-sentence premise with the count of premises over 512 tokens. Diagnostic only; the frozen verifier is unchanged."},
        {"id": "D8", "kind": "addition (audit note 4)", "text": "The P3-001 framing paragraph sits directly above the T2 class-filter results, with hybrid_minus_source_class next to them."},
        {"id": "D10", "kind": "deviation (Karan's decision, 2026-09-28)", "text": "The note-2 fallback was triggered EARLY: the long-context baseline is rerun on all 106 items at one uniform 100K cap (same proportional per-class truncation) without first finishing the 150K remainder run and retry pass. The decision was based ONLY on the failure-size evidence: never-answered prompts had a median of about 150K tokens (14 items, range 60K–150K) against about 71K for the 47 scored items (range 6K–132K). Disclosure: long-context scores on those 47 scored items had already been computed and displayed in Claude's session (3-way flag F1 0.515 [0.374, 0.626] against final agentic 0.518 on the same items) before Claude recommended the rerun; Claude's recommendation cited only the size evidence, and Karan decided on that evidence. The 150K run's items are kept only as a record, never reported as the baseline. Items under 100K reuse the cache (identical prompt). Pre-committed next step: if more than 20% of items still fail at 100K after one retry pass, one step down to a uniform 64K cap for all items; if failures remain after that, long-context is reported only on the scored items with the size distribution and every system compared on exactly those items; no further cap changes. A health probe and a 3-consecutive-failure circuit breaker stop provider outages from spending quota."},
        {"id": "D12", "kind": "addition", "text": "Before the outage cutoff, the 37 long-context items whose 100K prompt is byte-identical to a cached 150K prompt were scored from the cache (cache-only mode: no API call, no ledger entry); their outputs are identical to the 150K run. Gemini then recovered overnight and the chain completed the 100K pass and one retry pass: 102 of 106 items answered, 4 still failing (4%, below the 20% step-down threshold, so no 64K rerun). The demo transcripts ran on Gemini; the Groq demo fallback was never used."},
        {"id": "D11", "kind": "correction (compute rule)", "text": "Claude stopped the 150K remainder step on the 3-hour compute rule using wall-clock time (4 h). Measured as actual run time (Mac awake, from the power log), that step ran about 62 minutes (6 + 55 min), so the rule was not reached. Run times in this report are active time (macOS monotonic clock, which stops while the Mac sleeps); wall time is shown alongside."},
        {"id": "D9", "kind": "correction", "text": "The Part A statement that a windowed NLI premise would support far more rationales (15/27 vs 25/27, 5 debug items, 3-sentence window) does not hold on the validation outputs: a best-single-sentence premise supports fewer (see diagnostic b)."},
    ]
    metrics = {"version": "v1", "generated_utc": _now(), "environment": env, "ablation_table": table, "t1": t1, "t2": t2,
               "t3": t3, "t3_setup": t3_setup, "t3_precision": t3_precision, "t4": t4, "demo": demos,
               "limitations": limitations, "deviations": deviations, "summary": summary,
               "prompt_sha256": cfg["p4"]["prompt_sha256"]}
    write_json(resolver.write_path("reports", "p4001_metrics_v1.json"), metrics)
    resolver.write_path("reports", "p4001_system_and_ablations.md").write_text(p4_report.render(metrics), encoding="utf-8")
    print("wrote reports/p4001_system_and_ablations.md, reports/p4001_metrics_v1.json")
    for r in table:
        print(f"  {r['ablation']} {r['measure']}: ON {r['on']} OFF {r['off']} diff {r['diff']} (n={r['n']})")
    return 0


def cmd_backup(cfg: dict, resolver: PathResolver, _args) -> int:
    """Verified zip in ../p4001_backups/: code, frozen prompts, config, T3 set, run logs, quota ledger, reports; no keys."""
    import hashlib
    import zipfile

    from dotenv import dotenv_values

    root = resolver.working_root
    files = [root / f for f in (".gitignore", "config/config.yaml", "scripts/run_p4.py", "scripts/run_t3.py",
                                "scripts/demo.py", "tests/test_p4_pipeline.py", "tests/test_p4_analysis.py",
                                "src/llm/client.py", cfg["p4"]["ledger"])]
    for d in ("src/rag", "src/t3", cfg["p4"]["prompts_dir"], "data/benchmark/t3", "data/rag_runs"):
        files += [p for p in (root / d).rglob("*") if p.is_file()]
    files += sorted(root.glob("reports/p4001_*"))
    files = sorted({p for p in files if p.is_file() and p.name != ".env"})
    env = root / ".env"
    secrets = [v.strip() for v in dotenv_values(env).values() if v and v.strip()] if env.exists() else []
    if [p for p in files if any(s.encode() in p.read_bytes() for s in secrets)]:
        print("STOP: a file holds an API key value; nothing was backed up")
        return 1
    out = root.parent / "p4001_backups"
    out.mkdir(parents=True, exist_ok=True)
    z = out / f"p4001_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    with zipfile.ZipFile(z, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(root).as_posix())
    with zipfile.ZipFile(z) as zf:
        ok = zf.testzip() is None and all(hashlib.sha256(zf.read(p.relative_to(root).as_posix())).hexdigest()
                                          == hashlib.sha256(p.read_bytes()).hexdigest() for p in files)
    if not ok:
        print(f"STOP: backup {z} failed verification")
        return 1
    print(f"backup: {z} ({len(files)} files, {z.stat().st_size / 1e6:.1f} MB, verified, no key values)")
    return 0


def _ver(md, p):
    try:
        return md.version(p)
    except md.PackageNotFoundError:
        return None


def _fmt(v) -> str:
    if not v:
        return "n/a"
    if "value" in v:
        return "n/a" if v["value"] != v["value"] else fmt_ci(v["value"], v["ci"][0], v["ci"][1])
    return str(v)


def _pfmt(v) -> str:
    return fmt_ci(v["diff"], v["ci"][0], v["ci"][1], signed=True, reading=True)


def cmd_debug(cfg: dict, resolver: PathResolver, args) -> int:
    prompts = load_prompts(cfg, require_frozen=False)
    res, extra = load_resources(cfg, resolver)
    verifier = load_verifier(cfg)
    items = _rejected_items(resolver)
    rng = random.Random(20261012)
    chosen = sorted(rng.sample(items, min(args.n, 5, len(items))), key=lambda x: x["item_id"])
    out = _runs_dir(resolver, "debug_rejected")
    print(f"format debugging on {len(chosen)} of {len(items)} rejected (non-gold) items: {[c['item_id'] for c in chosen]}")
    for system in ("class_aware", "class_blind"):
        d = out / system
        d.mkdir(parents=True, exist_ok=True)
        s = run_t1(cfg, resolver, system, chosen, prompts=prompts, res=res, extra=extra, verifier=verifier, out_dir=d)
        if s.get("paused"):
            return 1
    for p in sorted(out.rglob("*.json")):
        log = json.loads(p.read_text())
        st = log["steps"][0]
        print(f"  {p.parent.name}/{p.stem}: problems {st['parse_problems']}; final flag {log['final']['flag']}; "
              f"judgements {[v['judgement'] for v in log['final']['per_class'].values()]}")
    return 0


def cmd_t1(cfg: dict, resolver: PathResolver, args) -> int:
    prompts = load_prompts(cfg)
    res, extra = load_resources(cfg, resolver)
    verifier = load_verifier(cfg)
    items = _items(resolver)
    if args.system == "long_context" and args.subset:
        rng = random.Random(int(cfg["p4"]["seeds"]["long_context_subset"]))
        items = sorted(rng.sample(items, int(cfg["p4"]["long_context"]["subset_n"])), key=lambda x: x["item_id"])
    name = f"t1_{args.system}" + (f"_cap{args.cap // 1000}k" if args.cap else "")
    out_dir = _runs_dir(resolver, name)
    s = run_t1(cfg, resolver, args.system, items, prompts=prompts, res=res, extra=extra, verifier=verifier,
               out_dir=out_dir, cap_tokens=args.cap, cache_only=args.cache_only)
    with (out_dir / "_passes.jsonl").open("a", encoding="utf-8") as h:
        h.write(json.dumps({"utc": _now(), "subset": bool(args.subset), "cap": args.cap or
                            int(cfg["p4"]["long_context"]["max_input_tokens"]),
                            **{k: s.get(k) for k in ("done", "skipped", "failed", "paused", "reason", "seconds",
                                                     "active_seconds", "cache_only", "cache_misses")}}) + "\n")
    return 1 if s.get("paused") else 0


def cmd_resume(cfg: dict, resolver: PathResolver, args) -> int:
    """Part A: priority 1-2 T1 runs in order, sharing one resource load."""
    prompts = load_prompts(cfg)
    res, extra = load_resources(cfg, resolver)
    verifier = load_verifier(cfg)
    items = _items(resolver)
    for system in PART_A_ORDER:
        s = run_t1(cfg, resolver, system, items, prompts=prompts, res=res, extra=extra, verifier=verifier,
                   out_dir=_runs_dir(resolver, f"t1_{system}"))
        if s.get("paused"):
            return 1
    return 0


def cmd_status(cfg: dict, resolver: PathResolver, _args) -> int:
    from src.llm.client import QuotaLedger

    ledger = QuotaLedger(resolver.working_root / cfg["p4"]["ledger"], soft_cap=int(cfg["p4"]["soft_cap"]))
    data = json.loads(ledger.path.read_text()) if ledger.path.exists() else {}
    print(f"quota day now: {ledger.quota_day()} (resets {ledger.next_reset_ist()} IST)")
    for model, days in sorted(data.items()):
        for day, n in sorted(days.items()):
            print(f"  {model} {day}: {n} calls (soft cap {ledger.soft_cap})")
    n = len(_items(resolver))
    for system in (*PART_A_ORDER, "long_context"):
        d = resolver.working_root / "data" / "rag_runs" / f"t1_{system}"
        k = len(list(d.glob("*.json"))) if d.exists() else 0
        print(f"  T1 {system}: {k}/{n} items written")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["freeze", "smoke", "debug", "t1", "resume", "status", "t3", "t4", "t2",
                                            "demo", "report", "backup", "probe", "lcstatus"])
    parser.add_argument("--temporal", action="append", choices=["on", "off"])
    parser.add_argument("--verifier", action="append", choices=["on", "off"])
    parser.add_argument("--system", choices=[*SYSTEMS, "long_context"])
    parser.add_argument("--subset", action="store_true")
    parser.add_argument("--cap", type=int, help="long_context: a uniform lower input cap (audit note 2 fallback)")
    parser.add_argument("--groq-demo", action="store_true", help="demo: Groq fallback after the Gemini outage cutoff only")
    parser.add_argument("--cache-only", action="store_true", help="t1: score only items whose exact prompt is cached; no API call")
    parser.add_argument("--n", type=int, default=5)
    args = parser.parse_args()
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    if args.command == "t1" and not args.system:
        parser.error("t1 needs --system")
    return {"freeze": cmd_freeze, "smoke": cmd_smoke, "debug": cmd_debug, "t1": cmd_t1, "resume": cmd_resume,
            "status": cmd_status, "t3": cmd_t3, "t4": cmd_t4, "t2": cmd_t2,
            "demo": cmd_demo, "report": cmd_report, "backup": cmd_backup, "probe": cmd_probe,
            "lcstatus": cmd_lcstatus}[args.command](cfg, resolver, args)


if __name__ == "__main__":
    raise SystemExit(main())
