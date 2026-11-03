#!/usr/bin/env python3
"""P3-002 Part A: the T4 RePASs audit inputs, answers, scores and the blind faithfulness sheet.

    python3 scripts/run_t4.py sample      # 30 validated T1 items, stratified by class       -> t4_sample_v1.json
    python3 scripts/run_t4.py questions   # LLM drafts one question per paragraph (logged)     -> t4_questions_v1.jsonl
    python3 scripts/run_t4.py retrieve    # class-aware hybrid top 3 + source paragraph        -> (adds passages)
    python3 scripts/run_t4.py answers     # genuine (LLM), concatenated, adv_negated, adv_offtopic -> t4_answers_<type>_v1.jsonl
    python3 scripts/run_t4.py score       # RePASs (their code, unchanged, own venv)           -> t4_repass_scores_v1.jsonl
    python3 scripts/run_t4.py sheet       # blind sheet + key + minutes log                    -> t4_faithfulness_sheet_v1.csv
    python3 scripts/run_t4.py ingest --file <completed.csv>   # once; refuses a re-submission
    python3 scripts/run_t4.py partA       # sample .. sheet in order
    python3 scripts/run_t4.py analyze     # Part B: verdicts, human vs metric, repair -> reports/p3002_*
    python3 scripts/run_t4.py backup      # verified zip in ../p3002_backups/ (no key values)

Outputs go to data/benchmark/t4/. data/benchmark/t1/ is only read. Every step that
exists already is refused rather than overwritten (delete the file to redo it).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import REPO_ROOT, get_required, load_config  # noqa: E402
from src.common.io_helpers import read_json, write_json  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.release.rbi_text import shorten  # noqa: E402
from src.t4 import audit as A  # noqa: E402

V = "v1"
T1_VALIDATED = ("benchmark", "t1", "t1_validated_v1.jsonl")
CANDIDATES_V4 = ("benchmark", "candidates", "t1_candidates_v4.jsonl")
REPASS_PY = REPO_ROOT / "external" / ".venv-repass" / "bin" / "python"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _t4(resolver: PathResolver) -> Path:
    d = resolver.write_dir("benchmark") / "t4"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(x) for x in handle if x.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _refuse(path: Path) -> None:
    if path.exists():
        raise SystemExit(f"STOP: {path.name} exists; delete it to redo this step")


def _corpus(resolver: PathResolver):
    from src.retrieval import index as IX

    return IX.load_corpus(resolver.read_path("processed"))


# -- sample ---------------------------------------------------------------------


def cmd_sample(cfg: dict, resolver: PathResolver) -> int:
    t4 = cfg["t4"]
    out = _t4(resolver) / f"t4_sample_{V}.json"
    _refuse(out)
    items = _read_jsonl(resolver.read_path(*T1_VALIDATED))
    chosen, log = A.sample_items(items, n=int(t4["n_questions"]), seed=int(t4["seeds"]["sample"]),
                                 min_classes=int(t4["min_classes"]), min_families=int(t4["min_families"]))
    write_json(out, {"created_utc": _now(), "source": "t1_validated_v1.jsonl", **log,
                     "item_ids": [it["item_id"] for it in chosen]})
    print(f"sampled {len(chosen)} items: {log['classes']} classes, {log['families']} families "
          f"(draw attempt {log['attempt']}, seed {log['seed_used']}); allocation {log['allocation']}")
    return 0


def _sampled(resolver: PathResolver) -> list[dict]:
    ids = read_json(_t4(resolver) / f"t4_sample_{V}.json")["item_ids"]
    items = {it["item_id"]: it for it in _read_jsonl(resolver.read_path(*T1_VALIDATED))}
    return [items[i] for i in ids]


# -- questions ------------------------------------------------------------------

QUESTION_SYSTEM = (
    "You write evaluation questions for a benchmark on Reserve Bank of India (RBI) Master Directions. "
    "Reply with the question only: one sentence ending in a question mark, no preamble, no quotation marks."
)


def question_messages(item: dict, paragraph_text: str, title: str) -> list[dict]:
    user = (
        f"Regulated entity class: {item['entity_class']}\n"
        f"Master Direction: {title}\n"
        f"Paragraph [{item['paragraph_id']}]:\n{A.collapse(paragraph_text)}\n\n"
        f"Write ONE question that a compliance officer at a {item['entity_class']} entity would ask and that "
        "this paragraph answers. The question must be answerable from this paragraph alone. Do not mention "
        "paragraph numbers, the paragraph id or the name of the Direction, and do not copy long phrases from "
        "the paragraph."
    )
    return [{"role": "system", "content": QUESTION_SYSTEM}, {"role": "user", "content": user}]


PROVIDER: dict[str, Any] = {"force": None, "reason": None}


def _client(cfg: dict, resolver: PathResolver, run_id: str):
    from src.common.logging_setup import get_logger
    from src.llm.client import build_client

    return build_client(cfg, resolver, run_id=run_id, force_provider=PROVIDER["force"],
                        logger=get_logger("llm.client", cfg))


def _run_record(client) -> dict:
    s = {**client.run.summary(), "forced_provider": PROVIDER["force"], "force_reason": PROVIDER["reason"]}
    if s["status"] != "ok":
        print(f"NOTE: run {s['run_id']} status {s['status']}; fallback events {s['fallback_events']}")
    return s


def cmd_questions(cfg: dict, resolver: PathResolver) -> int:
    from src.llm.client import CallCapReached, ProviderSwitchMidRun

    out = _t4(resolver) / f"t4_questions_{V}.jsonl"
    _refuse(out)
    items = _sampled(resolver)
    corpus = _corpus(resolver)
    text_of = dict(zip(corpus.ids, corpus.texts))
    titles = {r["document_id"]: r.get("title") or "" for r in
              _read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))}
    client = _client(cfg, resolver, "p3002_t4_questions_v1")
    rows = []
    try:
        for n, it in enumerate(items, 1):
            msgs = question_messages(it, text_of[it["paragraph_id"]], titles.get(it["md_id"], ""))
            c = client.complete(msgs, max_output_tokens=int(cfg["t4"]["question_max_output_tokens"]))
            question = " ".join(c.text.split()).strip().strip('"').strip()
            if not question:
                raise SystemExit(f"STOP: empty question for {it['item_id']}")
            rows.append({
                "question_id": f"T4Q{n:02d}", "item_id": it["item_id"], "paragraph_id": it["paragraph_id"],
                "md_id": it["md_id"], "entity_class": it["entity_class"], "subject_family": it["subject_family"],
                "question": question,
                "llm": {"provider": c.provider, "model": c.model, "model_version": c.model_version,
                        "cached": c.cached, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                        "messages": msgs, "raw_output": c.text},
            })
            print(f"  {rows[-1]['question_id']} {it['entity_class']}: {question}", flush=True)
    except (CallCapReached, ProviderSwitchMidRun) as exc:
        print(f"STOP: {type(exc).__name__}: {exc}")
        return 1
    _write_jsonl(out, rows)
    write_json(_t4(resolver) / f"t4_questions_run_{V}.json", _run_record(client))
    return 0


# -- retrieval ------------------------------------------------------------------


def cmd_retrieve(cfg: dict, resolver: PathResolver) -> int:
    import numpy as np

    from src.retrieval import index as IX
    from src.retrieval import systems as S

    path = _t4(resolver) / f"t4_questions_{V}.jsonl"
    rows = _read_jsonl(path)
    if all("passages" in r for r in rows):
        raise SystemExit("STOP: passages already retrieved; delete them to redo")
    rc = cfg["retrieval"]
    corpus = _corpus(resolver)
    bm25 = IX.BM25Index.from_config(corpus.texts, rc["bm25"])
    emb, meta = IX.load_embeddings(resolver.write_dir("indexes"), corpus)
    emb = emb.astype(np.float32)
    model = IX.load_model(rc["embedding_model"], rc["embedding_revision"], device=meta["device"],
                          max_seq_length=int(rc["max_seq_length"]))
    qvec = IX.encode(model, [IX.embedding_text(r["question"]) for r in rows], int(rc["batch_size"]))
    top = int(cfg["t4"]["retrieval_top"])
    for r, qv in zip(rows, qvec):
        # The question is not a corpus paragraph, so nothing is excluded; the target class is the item's class.
        ranked = S.run_query(bm25.scores(r["question"]), emb @ qv, entity_class=corpus.entity_class,
                             source_index=None, target_class=r["entity_class"], rrf_k=int(rc["rrf_k"]),
                             depth=int(rc["top_k"]))["class_aware"]
        ids = [corpus.ids[i] for i in ranked.indices]
        rank = ids.index(r["paragraph_id"]) + 1 if r["paragraph_id"] in ids else None
        chosen = ids[:top] + ([] if r["paragraph_id"] in ids[:top] else [r["paragraph_id"]])
        r["retrieval"] = {"system": "class_aware (P3-001 hybrid RRF, k=60, target class = item class)",
                          "top3": ids[:top], "source_rank": rank, "source_rank_note": None if rank else
                          f"not in top {rc['top_k']}", "source_appended": r["paragraph_id"] not in ids[:top]}
        r["passages"] = [{"paragraph_id": p, "text": A.collapse(corpus.texts[corpus.index_of[p]])} for p in chosen]
    _write_jsonl(path, rows)
    ranks = [r["retrieval"]["source_rank"] for r in rows]
    print(f"source paragraph in top 3 for {sum(1 for x in ranks if x and x <= top)}/{len(rows)}; "
          f"ranks {sorted(ranks, key=lambda x: (x is None, x or 0))}")
    return 0


# -- answers --------------------------------------------------------------------

GENUINE_SYSTEM = (
    "You answer compliance questions about Reserve Bank of India Master Directions using ONLY the passages "
    "provided. Do not use outside knowledge. Cite every claim with the id of the passage that supports it, in "
    "square brackets exactly as given, e.g. [md_12345::p00012]. If the passages do not answer the question, "
    "say so."
)


def genuine_messages(q: dict) -> list[dict]:
    return [{"role": "system", "content": GENUINE_SYSTEM},
            {"role": "user", "content": f"Question: {q['question']}\n\nPassages:\n\n{A.format_passages(q['passages'])}"}]


def _candidates_for(resolver: PathResolver, wanted: set[str] | None = None) -> dict[str, dict]:
    out = {}
    with resolver.read_path(*CANDIDATES_V4).open(encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if wanted is None or r["paragraph_id"] in wanted:
                out[r["paragraph_id"]] = r
    return out


def cmd_answers(cfg: dict, resolver: PathResolver) -> int:
    from src.llm.client import CallCapReached, ProviderSwitchMidRun

    d = _t4(resolver)
    for t in A.ANSWER_TYPES:
        _refuse(d / f"t4_answers_{t}_{V}.jsonl")
    qs = _read_jsonl(d / f"t4_questions_{V}.jsonl")
    if not all("passages" in q for q in qs):
        raise SystemExit("STOP: run `retrieve` first")
    corpus = _corpus(resolver)
    raw = dict(zip(corpus.ids, corpus.texts))
    cands = _candidates_for(resolver)
    out: dict[str, list[dict]] = {t: [] for t in A.ANSWER_TYPES}

    # concatenated + adv_negated (no LLM)
    for q in qs:
        text = A.concatenated_answer([(p["paragraph_id"], raw[p["paragraph_id"]]) for p in q["passages"]], cands)
        out["concatenated"].append({"question_id": q["question_id"], "answer_type": "concatenated", "answer": text,
                                    "method": "kept P2-001 v4 cue sentences, verbatim, passage order", "llm": None})
        out["adv_negated"].append({"question_id": q["question_id"], "answer_type": "adv_negated",
                                   "answer": A.negate(text), "method": "concatenated, polarity flipped, numbers x2",
                                   "llm": None})
    empty = [r["question_id"] for r in out["concatenated"] if not r["answer"]]
    if empty:
        print(f"NOTE: no kept-cue sentence in the passages of {empty} (empty concatenated answers)")

    # adv_offtopic: Directions in a different subject family, kept sentences in document order
    manifest = _read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))
    family = {r["document_id"]: r.get("subject_family") for r in manifest}
    by_md: dict[str, list[str]] = {}
    for pid in corpus.ids:
        c = cands.get(pid)
        if c:
            by_md.setdefault(corpus.md_id[corpus.index_of[pid]], []).extend(A.kept_sentences(raw[pid], c))
    directions = [{"md_id": m, "subject_family": family.get(m), "sentences": s} for m, s in sorted(by_md.items())]
    rng = random.Random(int(cfg["t4"]["seeds"]["offtopic"]))
    for q, conc in zip(qs, out["concatenated"]):
        text, used = A.offtopic_answer(len(conc["answer"]), source_family=q["subject_family"],
                                       directions=directions, rng=rng)
        out["adv_offtopic"].append({"question_id": q["question_id"], "answer_type": "adv_offtopic", "answer": text,
                                    "method": "kept cue sentences of random Directions in another subject family",
                                    "offtopic_md_ids": used,
                                    "offtopic_families": sorted({family.get(m) for m in used}), "llm": None})

    # genuine (LLM), one run for the whole answer type
    client = _client(cfg, resolver, "p3002_t4_genuine_v1")
    try:
        for q in qs:
            msgs = genuine_messages(q)
            c = client.complete(msgs, max_output_tokens=int(cfg["t4"]["answer_max_output_tokens"]))
            if not c.text.strip():
                raise SystemExit(f"STOP: empty genuine answer for {q['question_id']}")
            out["genuine"].append({"question_id": q["question_id"], "answer_type": "genuine", "answer": c.text.strip(),
                                   "llm": {"provider": c.provider, "model": c.model, "model_version": c.model_version,
                                           "cached": c.cached, "input_tokens": c.input_tokens,
                                           "output_tokens": c.output_tokens, "messages": msgs}})
            print(f"  genuine {q['question_id']}: {len(c.text)} chars", flush=True)
    except (CallCapReached, ProviderSwitchMidRun) as exc:
        print(f"STOP: {type(exc).__name__}: {exc} (genuine answers incomplete)")
        return 1
    for t, rows in out.items():
        _write_jsonl(d / f"t4_answers_{t}_{V}.jsonl", rows)
    write_json(d / f"t4_genuine_run_{V}.json", _run_record(client))
    for t, rows in out.items():
        lens = [len(r["answer"]) for r in rows]
        print(f"{t}: {len(rows)} answers, chars median {sorted(lens)[len(lens) // 2]}, min {min(lens)}, max {max(lens)}")
    return 0


# -- RePASs scoring ---------------------------------------------------------------


def cmd_score(cfg: dict, resolver: PathResolver) -> int:
    d = _t4(resolver)
    out = d / f"t4_repass_scores_{V}.jsonl"
    _refuse(out)
    qs = {q["question_id"]: q for q in _read_jsonl(d / f"t4_questions_{V}.jsonl")}
    rows, runs = [], {}
    for t in A.ANSWER_TYPES:
        answers = _read_jsonl(d / f"t4_answers_{t}_{V}.jsonl")
        payload = A.repass_payload(answers, qs)
        inp = d / f"t4_repass_input_{t}_{V}.json"
        inp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        group = f"p3002_t4_{t}_{V}"
        started = time.time()
        proc = subprocess.run([str(REPASS_PY), str(REPO_ROOT / "scripts" / "run_repass.py"), "score", "--input", str(inp),
                               "--group", group], capture_output=True, text=True)
        if proc.returncode:
            print(proc.stdout[-2000:], proc.stderr[-4000:])
            raise SystemExit(f"STOP: RePASs scoring failed for {t}")
        tail = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
        runs[t] = {**(json.loads(tail[-1]) if tail else {}), "wall_seconds": round(time.time() - started, 1)}
        res = REPO_ROOT / "external" / "RePASs" / "data" / group / "results.csv"
        with res.open(encoding="utf-8") as handle:
            scored = {r["QuestionID"]: r for r in csv.DictReader(handle)}
        for a in answers:
            r = scored.get(a["question_id"])
            rows.append({"question_id": a["question_id"], "answer_type": t, "scored": r is not None,
                         **({k: float(r[k]) for k in ("entailment_score", "contradiction_score",
                                                       "obligation_coverage_score", "composite_score")} if r else {})})
        print(f"{t}: scored {sum(1 for x in rows if x['answer_type'] == t and x['scored'])}/{len(answers)} "
              f"in {runs[t]['wall_seconds'] / 60:.1f} min on {runs[t].get('device')}", flush=True)
    _write_jsonl(out, rows)
    write_json(d / f"t4_repass_run_{V}.json", {"scored_utc": _now(), "runs": runs,
                                                 "commit": cfg["t4"]["repass"]["commit"],
                                                 "results_dirs": [f"external/RePASs/data/p3002_t4_{t}_{V}" for t in A.ANSWER_TYPES]})
    return 0


# -- sheet ----------------------------------------------------------------------


def cmd_sheet(cfg: dict, resolver: PathResolver) -> int:
    d = _t4(resolver)
    sheet_path = d / f"t4_faithfulness_sheet_{V}.csv"
    _refuse(sheet_path)
    t4 = cfg["t4"]
    qs = _read_jsonl(d / f"t4_questions_{V}.jsonl")
    answers = {t: {a["question_id"]: a for a in _read_jsonl(d / f"t4_answers_{t}_{V}.jsonl")} for t in A.ANSWER_TYPES}
    quotas = {t: int(t4["sheet"][t]) for t in A.ANSWER_TYPES}
    assignment = A.assign_sheet_types([q["question_id"] for q in qs], quotas, int(t4["seeds"]["sheet_draw"]))
    rows, key = A.build_sheet(qs, answers, assignment, order_seed=int(t4["seeds"]["sheet_order"]),
                              block_size=int(t4["sheet"]["block_size"]))
    A.assert_blind(rows)
    too_long = [r["row_id"] for r in rows if max(len(r[c]) for c in ("passages", "answer")) > 32000]
    if too_long:
        raise SystemExit(f"STOP: cells over Excel's limit in {too_long}")
    # BOM, so Excel reads the ₹ signs and curly quotes as UTF-8.
    sheet_path.write_text(A.sheet_csv(rows), encoding="utf-8-sig")
    write_json(d / f"t4_faithfulness_key_{V}.json", {
        "created_utc": _now(), "sheet": sheet_path.name, "sheet_sha256": A.sha256_bytes(sheet_path.read_bytes()),
        "quotas": quotas, "seeds": {"draw": t4["seeds"]["sheet_draw"], "order": t4["seeds"]["sheet_order"]},
        "rows": key, "note": "Do not open while rating. Scores and model ids are in the answer and score files."})
    minutes = d / "t4_faithfulness_minutes.csv"
    if not minutes.exists():
        minutes.write_text("block,started_at,ended_at\n1,,\n2,,\n3,,\n", encoding="utf-8-sig")
    print(f"sheet: {sheet_path}")
    print(f"minutes log: {minutes}")
    print(f"types on sheet: {dict(Counter(v['answer_type'] for v in key.values()))} (hidden in the key file)")
    return 0


WITHDRAWN = [{
    "sha256": "54733120d88b8e7cb73144f1652a4a14b00c23c3c5961115f5eaddbe162f90cd",
    "received_local": "2026-09-28T00:52:44+05:30",
    "status": "withdrawn before ingest; never ingested",
    "why_not_ingested": "its minutes log (blocks 2-3 at 00:56-01:43) post-dated the file's arrival (00:52)",
    "karan_statement": "a mock / garbage file, deleted; replaced by the final manually annotated file",
}]


def _read_minutes(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    out = []
    for r in rows:
        a = datetime.strptime(r["started_at"].strip(), "%Y-%m-%d %H:%M")
        b = datetime.strptime(r["ended_at"].strip(), "%Y-%m-%d %H:%M")
        if b <= a:
            raise SystemExit(f"REJECTED: block {r['block']} ends before it starts")
        out.append({"block": int(r["block"]), "started_at": r["started_at"].strip(), "ended_at": r["ended_at"].strip(),
                    "minutes": (b - a).total_seconds() / 60})
    if sorted(x["block"] for x in out) != [1, 2, 3]:
        raise SystemExit("REJECTED: the minutes log must hold blocks 1, 2 and 3")
    return out


def cmd_ingest(cfg: dict, resolver: PathResolver, file: str, minutes_file: str | None = None) -> int:
    d = _t4(resolver)
    receipt = d / f"t4_faithfulness_receipt_{V}.json"
    if receipt.exists():
        print(f"REFUSED: a completed sheet was already accepted ({read_json(receipt)['sha256']}); "
              "re-submissions are not accepted")
        return 1
    src = Path(file)
    data = src.read_bytes()
    had_bom = data.startswith(b"\xef\xbb\xbf")
    completed = A.read_sheet_text(data.decode("utf-8-sig"))
    blank = A.read_sheet_text((d / f"t4_faithfulness_sheet_{V}.csv").read_text(encoding="utf-8-sig"))
    problems = A.validate_completed(completed, blank)
    if problems:
        print("REJECTED (nothing recorded):")
        for p in problems:
            print(f"  - {p}")
        return 1
    if not minutes_file:
        print("REJECTED: --minutes is required (the block times feed the per-answer rating time)")
        return 1
    mpath = Path(minutes_file)
    minutes = _read_minutes(mpath)
    arrived = datetime.fromtimestamp(src.stat().st_mtime)
    last_end = max(datetime.strptime(m["ended_at"], "%Y-%m-%d %H:%M") for m in minutes)
    if last_end > arrived:
        print(f"REJECTED: the minutes log ends at {last_end:%H:%M}, after the sheet was saved here ({arrived:%H:%M})")
        return 1
    received = _now()
    sha = A.sha256_bytes(data)
    keep = d / f"t4_faithfulness_sheet_{V}_accepted.csv"
    keep.write_bytes(data)
    (d / f"t4_faithfulness_minutes_{V}_accepted.csv").write_bytes(mpath.read_bytes())
    labels = [{"row_id": r["row_id"].strip(), "faithful": int(r["faithful"]), "answers_question": int(r["answers_question"]),
               "bad_question": (r.get("bad_question") or "").strip().lower() == "yes", "note": (r.get("note") or "").strip(),
               "label_source": "manual", "rater": "karan", "received_utc": received, "file_sha256": sha}
              for r in completed]
    _write_jsonl(d / f"t4_faithfulness_labels_{V}.jsonl", labels)
    write_json(receipt, {"received_utc": received, "sha256": sha, "file": str(src), "stored_as": keep.name,
                         "file_saved_local": arrived.isoformat(timespec="seconds"),
                         "had_bom": had_bom, "rows": len(labels), "label_source": "manual", "rater": "karan",
                         "declared_by_karan": "manually annotated, final and complete; no AI tools",
                         "minutes_file": str(mpath), "minutes_sha256": A.sha256_bytes(mpath.read_bytes()),
                         "minutes": minutes, "withdrawn_submissions": WITHDRAWN})
    print(f"accepted {len(labels)} rows (sha256 {sha[:12]}…, BOM {'yes' if had_bom else 'no'}); "
          f"bad_question = yes on {sum(l['bad_question'] for l in labels)}")
    return 0


# -- Part B: analysis ---------------------------------------------------------------

GAMING = ("concatenated", "adv_negated", "adv_offtopic")
COMPONENTS = ("composite_score", "entailment_score", "contradiction_score", "obligation_coverage_score")


def _relevance(d: Path, qs: dict, answers: dict) -> dict[str, float]:
    """RePASs' NLI model, question => each answer sentence; computed once, then read back."""
    path = d / f"t4_relevance_{V}.json"
    if not path.exists():
        payload = [{"id": f"{t}:{qid}", "question": qs[qid]["question"], "answer": a["answer"]}
                   for t in A.ANSWER_TYPES for qid, a in sorted(answers[t].items())]
        inp = d / f"t4_relevance_input_{V}.json"
        inp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        proc = subprocess.run([str(REPASS_PY), str(REPO_ROOT / "scripts" / "run_repass.py"), "relevance", "--input",
                               str(inp), "--output", str(path)], capture_output=True, text=True)
        if proc.returncode:
            print(proc.stderr[-3000:])
            raise SystemExit("STOP: relevance scoring failed")
    return {r["id"]: r["relevance"] for r in json.loads(path.read_text(encoding="utf-8"))}


def _recorded_llm_config(resolver: PathResolver) -> dict | None:
    for path in (resolver.write_dir("reports") / "private" / "p3002_metrics_v1_original.json",
                 resolver.write_dir("reports") / f"p3002_metrics_{V}.json"):
        if path.exists():
            rec = (read_json(path).get("provenance") or {}).get("llm_config")
            if rec:
                return rec
    return None


def cmd_analyze(cfg: dict, resolver: PathResolver) -> int:
    from src.eval.metrics import bootstrap_mean, paired_bootstrap
    from src.t4 import analysis as N
    from src.t4.report import audit_report

    d = _t4(resolver)
    t4 = cfg["t4"]
    receipt_path = d / f"t4_faithfulness_receipt_{V}.json"
    if not receipt_path.exists():
        raise SystemExit("STOP: no accepted faithfulness sheet; run `ingest` first")
    receipt = read_json(receipt_path)
    R = int(cfg["retrieval"]["eval"]["bootstrap_resamples"])
    seed = int(t4["seeds"]["bootstrap"])
    tau = float(t4["repair"]["lcs_tau"])
    kw = {"resamples": R, "seed": seed}

    qs = {q["question_id"]: q for q in _read_jsonl(d / f"t4_questions_{V}.jsonl")}
    qids = sorted(qs)
    answers = {t: {a["question_id"]: a for a in _read_jsonl(d / f"t4_answers_{t}_{V}.jsonl")} for t in A.ANSWER_TYPES}
    scores = {(r["answer_type"], r["question_id"]): r for r in _read_jsonl(d / f"t4_repass_scores_{V}.jsonl")}
    if not all(r["scored"] for r in scores.values()) or len(scores) != 4 * len(qids):
        raise SystemExit("STOP: not every answer has a RePASs score")
    key = read_json(d / f"t4_faithfulness_key_{V}.json")["rows"]
    labels = {key[l["row_id"]]["question_id"]: {**l, "answer_type": key[l["row_id"]]["answer_type"]}
              for l in _read_jsonl(d / f"t4_faithfulness_labels_{V}.jsonl")}
    bad = sorted(q for q, l in labels.items() if l["bad_question"])
    if len(bad) > 5:
        raise SystemExit(f"STOP: {len(bad)} questions flagged bad_question (> 5); redraw them before the analysis")
    rel = _relevance(d, qs, answers)

    rows: dict[str, dict[str, dict]] = {t: {} for t in A.ANSWER_TYPES}
    for t in A.ANSWER_TYPES:
        for qid in qids:
            s = scores[(t, qid)]
            ratio = N.lcs_ratio(answers[t][qid]["answer"], [p["text"] for p in qs[qid]["passages"]])
            pen = N.overlap_penalty(ratio, tau)
            r = rel[f"{t}:{qid}"]
            lab = labels.get(qid) if labels.get(qid, {}).get("answer_type") == t else None
            rows[t][qid] = {"question_id": qid, "answer_type": t, **{c: s[c] for c in COMPONENTS},
                            "lcs_ratio": ratio, "overlap_penalty": pen, "relevance": r,
                            "repaired": N.repaired_score(s["composite_score"], r, pen),
                            "on_sheet": lab is not None, "faithful": lab["faithful"] if lab else None,
                            "answers_question": lab["answers_question"] if lab else None,
                            "bad_question": qid in bad}
    _write_jsonl(d / f"t4_per_answer_{V}.jsonl", [rows[t][q] for t in A.ANSWER_TYPES for q in qids])

    def block(qset: list[str]) -> dict:
        n = len(qset)
        out: dict[str, Any] = {"n_questions": n, "by_type": {}, "paired": {}, "verdicts": {}, "repair": {}}
        for t in A.ANSWER_TYPES:
            out["by_type"][t] = {f: bootstrap_mean([rows[t][q][f] for q in qset], **kw)
                                 for f in (*COMPONENTS, "lcs_ratio", "overlap_penalty", "relevance", "repaired")}
        for t in GAMING:
            out["paired"][f"{t} - genuine"] = {f: paired_bootstrap([rows[t][q][f] for q in qset],
                                                                    [rows["genuine"][q][f] for q in qset], **kw)
                                               for f in COMPONENTS}
            c = out["paired"][f"{t} - genuine"]["composite_score"]
            out["verdicts"][t] = N.verdict(c["ci_low"], c["ci_high"], n)
            p = paired_bootstrap([rows["genuine"][q]["repaired"] for q in qset], [rows[t][q]["repaired"] for q in qset], **kw)
            out["repair"][f"genuine - {t}"] = {**p, "verdict": N.ranking_verdict(p["ci_low"], p["ci_high"], n)}
        return out

    main_block = block(qids)
    sens_block = block([q for q in qids if q not in bad])

    sheet_rows = [rows[l["answer_type"]][q] for q, l in sorted(labels.items())]

    def human(rs: list[dict]) -> dict:
        out: dict[str, Any] = {"n": len(rs), "by_type": {}}
        for t in A.ANSWER_TYPES:
            sub = [r for r in rs if r["answer_type"] == t]
            out["by_type"][t] = {f: bootstrap_mean([r[f] for r in sub], **kw) for f in ("faithful", "answers_question")}
        for metric in ("composite_score", "repaired"):
            for h in ("faithful", "answers_question"):
                out[f"spearman_{metric}_vs_{h}"] = N.spearman_bootstrap([r[metric] for r in rs], [r[h] for r in rs], **kw)
        return out

    minutes = receipt["minutes"]
    total_min = sum(m["minutes"] for m in minutes)
    rng = random.Random(seed)
    examples = {}
    for t in A.ANSWER_TYPES:
        on = sorted(q for q, l in labels.items() if l["answer_type"] == t)
        # P5-001 task 3: an example carries a pointer and a <= 25-word excerpt, never the full answer (the answers of the
        # non-LLM types are verbatim RBI text). Full originals: gitignored reports/private/.
        examples[t] = [{**rows[t][q], "question": qs[q]["question"],
                        "answer_excerpt": shorten(answers[t][q]["answer"], 25),
                        "answer_pointer": {"question_id": q, "answer_type": t, "file": f"t4_answers_{t}_{V}.jsonl"},
                        "passage_ids": [p["paragraph_id"] for p in qs[q]["passages"]]} for q in sorted(rng.sample(on, 3))]

    def _json(path: Path) -> dict | None:
        return read_json(path) if path.exists() else None

    train = _json(REPO_ROOT / "external" / "RePASs" / "models" / "p3002_train_info.json") or {}
    first_genuine = _json(d / "superseded" / "t4_genuine_run_v1_pre_trimfix.json")
    metrics = {
        "version": V, "analysed_utc": _now(),
        "protocol": {"bootstrap_resamples": R, "bootstrap_seed": seed, "ci": "percentile 95%, resampling questions",
                     "verdict_rule": "type - genuine composite CI >= 0 reproduces; < 0 does not; else inconclusive",
                     "repair": {**t4["repair"], "status": "exploratory; declared before scoring; same 30 questions"}},
        "main": main_block,
        "sensitivity_without_bad_questions": {"excluded": bad, **sens_block},
        "human": {"all_rated": human(sheet_rows),
                  "without_bad_questions": human([r for r in sheet_rows if not r["bad_question"]]),
                  "bad_question_count": len(bad), "bad_questions": bad,
                  "sheet_quotas": {t: sum(1 for l in labels.values() if l["answer_type"] == t) for t in A.ANSWER_TYPES},
                  "minutes": {"blocks": minutes, "total": total_min, "per_answer": total_min / len(labels),
                              "source": "t4_faithfulness_minutes (accepted with the sheet)"},
                  "receipt": {k: receipt[k] for k in ("sha256", "received_utc", "file_saved_local", "label_source",
                                                      "rater", "declared_by_karan", "withdrawn_submissions")}},
        "examples": examples,
        "provenance": {
            "sample": read_json(d / f"t4_sample_{V}.json"),
            "questions_run": _json(d / f"t4_questions_run_{V}.json"),
            "genuine_run_api": first_genuine, "genuine_run_final": _json(d / f"t4_genuine_run_{V}.json"),
            "retrieval_source_ranks": {q: qs[q]["retrieval"]["source_rank"] for q in qids},
            "repass": {**t4["repass"], "scoring": _json(d / f"t4_repass_run_{V}.json"), "training": train},
            # The config in force when P3-002 ran; a later re-run (e.g. P5 re-rendering) keeps the recorded one.
            "llm_config": _recorded_llm_config(resolver) or {k: cfg["llm"].get(k) for k in
                                                             ("model", "long_context_model", "fallback_model", "model_versions")},
        },
    }
    write_json(resolver.write_path("reports", f"p3002_metrics_{V}.json"), metrics)
    resolver.write_path("reports", "p3002_t4_repass_audit.md").write_text(audit_report(metrics), encoding="utf-8")
    for t in GAMING:
        c = main_block["paired"][f"{t} - genuine"]["composite_score"]
        rp = main_block["repair"][f"genuine - {t}"]
        print(f"{t} - genuine: {c['mean']:+.3f} [{c['ci_low']:+.3f}, {c['ci_high']:+.3f}] -> {main_block['verdicts'][t]}; "
              f"repaired genuine - {t}: {rp['mean']:+.3f} [{rp['ci_low']:+.3f}, {rp['ci_high']:+.3f}] -> {rp['verdict']}")
    sp = metrics["human"]["all_rated"]["spearman_composite_score_vs_faithful"]
    print(f"Spearman RePASs vs faithful: {sp['rho']:.3f} [{sp['ci_low']:.3f}, {sp['ci_high']:.3f}] n={sp['n']}")
    print("wrote reports/p3002_t4_repass_audit.md, reports/p3002_metrics_v1.json")
    return 0


def cmd_backup(cfg: dict, resolver: PathResolver) -> int:
    """Verified zip of P3-002's code, config, T4 data, RePASs outputs and reports; refuses if a key value is inside."""
    import hashlib
    import zipfile

    from dotenv import dotenv_values

    root = resolver.working_root
    files = [p for p in _t4(resolver).rglob("*") if p.is_file()]
    files += [root / f for f in (".gitignore", "config/config.yaml", "scripts/run_t4.py", "scripts/run_repass.py",
                                 "scripts/run_p3001.py", "tests/test_t4_audit.py", "tests/test_t4_analysis.py",
                                 "src/eval/report.py", "src/retrieval/systems.py")]
    files += list((root / "src" / "t4").glob("*.py")) + sorted(root.glob("reports/p3001_*")) + sorted(root.glob("reports/p3002_*"))
    files += [root / "external" / "RePASs" / "models" / "p3002_train_info.json"]
    files += [p for p in (root / "external" / "RePASs" / "data").glob("p3002_t4_*/*")]
    files = sorted({p for p in files if p.is_file() and p.name != ".env"})
    env = root / ".env"
    secrets = [v.strip() for v in dotenv_values(env).values() if v and v.strip()] if env.exists() else []
    if [p for p in files if any(s.encode() in p.read_bytes() for s in secrets)]:
        print("STOP: a file holds an API key value; nothing was backed up")
        return 1
    out = root.parent / "p3002_backups"
    out.mkdir(parents=True, exist_ok=True)
    z = out / f"p3002_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    with zipfile.ZipFile(z, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(root).as_posix())
    with zipfile.ZipFile(z) as zf:
        ok = zf.testzip() is None and all(hashlib.sha256(zf.read(p.relative_to(root).as_posix())).hexdigest()
                                          == A.sha256_bytes(p.read_bytes()) for p in files)
    if not ok:
        print(f"STOP: backup {z} failed verification")
        return 1
    print(f"backup: {z} ({len(files)} files, {z.stat().st_size / 1e6:.1f} MB, verified, no key values)")
    return 0


def cmd_part_a(cfg: dict, resolver: PathResolver) -> int:
    for step in (cmd_sample, cmd_questions, cmd_retrieve, cmd_answers, cmd_score, cmd_sheet):
        rc = step(cfg, resolver)
        if rc:
            return rc
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["sample", "questions", "retrieve", "answers", "score", "sheet", "ingest",
                                            "partA", "analyze", "backup"])
    parser.add_argument("--file")
    parser.add_argument("--minutes", help="ingest: the completed minutes log")
    parser.add_argument("--provider", choices=["gemini", "groq"],
                        help="run a whole LLM step on one provider (e.g. after the primary's quota is exhausted)")
    parser.add_argument("--provider-reason", help="recorded with the run when --provider is given")
    args = parser.parse_args()
    if args.provider and not args.provider_reason:
        parser.error("--provider needs --provider-reason")
    PROVIDER.update(force=args.provider, reason=args.provider_reason)
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    get_required(cfg, "t4.repass.commit")
    if args.command == "ingest":
        if not args.file:
            parser.error("ingest needs --file")
        return cmd_ingest(cfg, resolver, args.file, args.minutes)
    return {"sample": cmd_sample, "questions": cmd_questions, "retrieve": cmd_retrieve, "answers": cmd_answers,
            "score": cmd_score, "sheet": cmd_sheet, "partA": cmd_part_a, "analyze": cmd_analyze,
            "backup": cmd_backup}[args.command](cfg, resolver)


if __name__ == "__main__":
    raise SystemExit(main())
