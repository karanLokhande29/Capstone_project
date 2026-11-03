#!/usr/bin/env python3
"""P3-001: T2 relevance sets, retrieval baselines, T1 baselines.

    python3 scripts/run_p3001.py index      # verify 76,188 paragraphs, embed them (bge, pinned), float16 -> data/indexes/
    python3 scripts/run_p3001.py qrels      # the three T2 relevance sets -> data/benchmark/t2/
    python3 scripts/run_p3001.py retrieve   # bm25, dense, hybrid_rrf, class_aware; top 100 -> data/evaluation/p3001/
    python3 scripts/run_p3001.py score      # metrics + bootstrap -> reports/p3001_metrics_v1.json, p3001_retrieval_baselines.md
    python3 scripts/run_p3001.py t1         # T1 baselines -> reports/p3001_t1_baselines.md
    python3 scripts/run_p3001.py all        # qrels, retrieve, score, t1 (the index must exist)
    python3 scripts/run_p3001.py backup     # verified zip of the P3-001 outputs in ../p3001_backups/ (no keys)

Files under data/benchmark/t1/ are only read, never written. No LLM call happens here.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import get_required, load_config  # noqa: E402
from src.common.io_helpers import read_json, write_json  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.retrieval import index as IX  # noqa: E402

VERSION = "v1"
PACKAGES = ("numpy", "scipy", "torch", "transformers", "sentence-transformers", "huggingface-hub", "bm25s",
            "requests", "python-dotenv", "pytest", "PyYAML")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def environment() -> dict[str, Any]:
    versions = {}
    for p in PACKAGES:
        try:
            versions[p] = md.version(p)
        except md.PackageNotFoundError:
            versions[p] = None
    chip = None
    if platform.system() == "Darwin":
        import subprocess

        try:
            chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        except OSError:
            chip = None
    return {"machine": platform.machine(), "cpu": chip or platform.processor(), "os": platform.platform(),
            "python": platform.python_version(), "packages": versions}


def _corpus(cfg: dict, resolver: PathResolver) -> IX.Corpus:
    corpus = IX.load_corpus(resolver.read_path("processed"))
    expected = int(get_required(cfg, "retrieval.expected_paragraphs"))
    if len(corpus) != expected:
        raise SystemExit(f"STOP: {len(corpus)} paragraphs in data/processed, expected {expected}")
    return corpus


# -- index --------------------------------------------------------------------


def cmd_index(cfg: dict, resolver: PathResolver) -> int:
    rc = cfg["retrieval"]
    corpus = _corpus(cfg, resolver)
    print(f"paragraphs: {len(corpus)} (expected {rc['expected_paragraphs']}) OK")
    out_dir = resolver.write_dir("indexes")
    device = IX.pick_device()
    t0 = time.time()
    try:
        model = IX.load_model(rc["embedding_model"], rc["embedding_revision"], device=device,
                              max_seq_length=int(rc["max_seq_length"]))
    except IX.RetrievalError as exc:
        print(exc)
        return 1
    print(f"model {rc['embedding_model']} @ {rc['embedding_revision']} on {device} ({time.time() - t0:.0f}s load)")

    texts = [IX.embedding_text(t) for t in corpus.texts]
    truncated = IX.count_truncated(model, texts, int(rc["max_seq_length"]))
    print(f"truncated at {rc['max_seq_length']} tokens: {truncated}")

    # Projection from a spread-out probe (every 150th paragraph), after a warm-up batch.
    probe = texts[::150]
    IX.encode(model, probe[:32], int(rc["batch_size"]))
    t1 = time.time()
    IX.encode(model, probe, int(rc["batch_size"]))
    projected_h = (time.time() - t1) / len(probe) * len(texts) / 3600
    print(f"projected embedding time: {projected_h * 60:.1f} min (limit {rc['max_embed_hours']} h)")
    if projected_h > float(rc["max_embed_hours"]):
        print("STOP: projected runtime over the compute limit")
        return 1

    def progress(done: int, total: int, secs: float) -> None:
        print(f"  embedded {done}/{total} in {secs / 60:.1f} min", flush=True)

    started = time.time()
    _, info = IX.build_embeddings(
        corpus, lambda xs: IX.encode(model, xs, int(rc["batch_size"])), out_dir,
        meta={"model_id": rc["embedding_model"], "model_revision": rc["embedding_revision"],
              "revision_verified_against_hub": True, "device": device, "max_seq_length": rc["max_seq_length"],
              "batch_size": rc["batch_size"], "normalized": True, "truncated_paragraphs": truncated,
              "projected_minutes": round(projected_h * 60, 1), "computed_locally": True,
              "reused_kaggle_embeddings": False, "built_utc": _now(), "environment": environment()},
        progress=progress,
    )
    info["total_wall_seconds"] = round(time.time() - started, 1)
    write_json(out_dir / IX.EMBEDDINGS_META, info)
    print(f"done: {info['paragraphs']} x {info['dim']} float16 in {info['total_wall_seconds'] / 60:.1f} min "
          f"-> {out_dir / IX.EMBEDDINGS_FILE}")
    return 0


# -- qrels --------------------------------------------------------------------

T1_VALIDATED = ("benchmark", "t1", "t1_validated_v1.jsonl")
T1_CANDIDATES = ("benchmark", "t1", "t1_candidate_benchmark_v1.jsonl")
P2002_KEY = ("benchmark", "matching", "p2002_validation_key_v1.json")
P2002_SHEET = ("benchmark", "matching", "p2002_validation_sheet_v1_completed.csv")
P2003_SHEET = "p2003_alignment_sheet_v1_completed.csv"
P2003_KEY = "p2003_alignment_key_v1.json"
SETS = ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003")


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _supp_dir(cfg: dict) -> Path:
    from src.common.config import REPO_ROOT

    return REPO_ROOT / str(get_required(cfg, "supplementary.data_dir"))


def _t2_dir(resolver: PathResolver) -> Path:
    path = resolver.write_dir("benchmark") / "t2"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cmd_qrels(cfg: dict, resolver: PathResolver) -> int:
    import csv

    from src.eval import qrels as Q
    from src.supplementary.alignment import read_sheet

    corpus = _corpus(cfg, resolver)
    ids = set(corpus.ids)
    text_of = dict(zip(corpus.ids, corpus.texts))
    inputs = {
        "t1_validated": resolver.read_path(*T1_VALIDATED),
        "p2002_key": resolver.read_path(*P2002_KEY),
        "p2002_sheet": resolver.read_path(*P2002_SHEET),
        "p2003_sheet": _supp_dir(cfg) / P2003_SHEET,
        "p2003_key": _supp_dir(cfg) / P2003_KEY,
    }
    t1 = Q.build_t1(_read_jsonl(inputs["t1_validated"]), ids)

    key = read_json(inputs["p2002_key"])["pairs"]
    with inputs["p2002_sheet"].open(encoding="utf-8-sig") as handle:
        sheet = list(csv.DictReader(handle))
    p2002 = Q.build_p2002(key, sheet, text_of)
    # The sheet showed the same span the key's offsets cut from the paragraph (sheet cells may be capped).
    span_a = {r["pair_id"]: " ".join(r["span_a"].split()) for r in sheet}
    mismatched = [q["query_id"] for q in p2002 if not " ".join(q["text"].split()).startswith(span_a[q["query_id"]][:200])]
    if mismatched:
        print(f"STOP: P2-002 source spans differ from the labelled sheet for {mismatched}")
        return 1

    p2003 = Q.build_p2003(read_sheet(inputs["p2003_sheet"]), read_json(inputs["p2003_key"])["items"], ids)
    built = {"t2_xclass_t1": t1, "t2_xclass_p2002": p2002, "t2_supp_p2003": p2003}

    out_dir = _t2_dir(resolver)
    meta: dict[str, Any] = {"version": VERSION, "built_utc": _now(), "pooled": False,
                            "inputs": {k: {"path": str(p.relative_to(resolver.working_root)), "sha256": _sha(p)}
                                       for k, p in inputs.items()},
                            "sets": {}}
    for name, queries in built.items():
        path = out_dir / f"{name}_{VERSION}.jsonl"
        path.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queries), encoding="utf-8")
        meta["sets"][name] = {"file": path.name, "bias": Q.BIAS[name], **Q.summarise(queries)}
        if name == "t2_supp_p2003":
            meta["sets"][name]["text_basis"] = dict(sorted(Counter(q["text_basis"] for q in queries).items()))
        s = meta["sets"][name]
        print(f"{name}: {s['queries']} queries, {s['queries_with_relevant']} with a relevant paragraph, "
              f"{s['relevant_pairs']} relevant pairs (grade 2: {s['grade_counts']['2']}, grade 1: "
              f"{s['grade_counts']['1']}), {s['queries_with_target_class']} with a target class")
    write_json(out_dir / f"t2_qrels_meta_{VERSION}.json", meta)
    return 0


def _load_sets(resolver: PathResolver) -> dict[str, list[dict]]:
    out_dir = _t2_dir(resolver)
    return {name: _read_jsonl(out_dir / f"{name}_{VERSION}.jsonl") for name in SETS}


# -- retrieve -----------------------------------------------------------------


def _eval_dir(resolver: PathResolver) -> Path:
    path = resolver.write_dir("evaluation") / "p3001"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cmd_retrieve(cfg: dict, resolver: PathResolver) -> int:
    import numpy as np

    from src.retrieval import systems as S

    rc = cfg["retrieval"]
    corpus = _corpus(cfg, resolver)
    t0 = time.time()
    bm25 = IX.BM25Index.from_config(corpus.texts, rc["bm25"])
    bm25_secs = time.time() - t0
    emb, emb_meta = IX.load_embeddings(resolver.write_dir("indexes"), corpus)
    emb = emb.astype(np.float32)
    model = IX.load_model(rc["embedding_model"], rc["embedding_revision"], device=emb_meta["device"],
                          max_seq_length=int(rc["max_seq_length"]))
    sets = _load_sets(resolver)
    depth, rrf_k = int(rc["top_k"]), int(rc["rrf_k"])
    summary: dict[str, Any] = {"bm25_index_seconds": round(bm25_secs, 1), "sets": {}}
    for name, queries in sets.items():
        t1 = time.time()
        qvec = IX.encode(model, [IX.embedding_text(q["text"]) for q in queries], int(rc["batch_size"]))
        lines, unreachable, flagged, src_missing, no_source_class = [], [], 0, 0, 0
        for q, qv in zip(queries, qvec):
            src = q.get("source_paragraph_id")
            src_idx = corpus.index_of.get(src) if src else None
            if src and src_idx is None:
                src_missing += 1
            if src and src in q["relevant"]:
                raise SystemExit(f"STOP: {q['query_id']} lists its own source paragraph as relevant")
            target = q.get("target_class")
            source_class = q.get("source_class")
            if source_class is None:
                no_source_class += 1
            ranked = S.run_query(bm25.scores(q["text"]), emb @ qv, entity_class=corpus.entity_class,
                                 source_index=src_idx, target_class=target, rrf_k=rrf_k, depth=depth,
                                 source_class=source_class)
            if target:
                outside = [p for p in q["relevant"] if corpus.entity_class[corpus.index_of[p]] != target]
                if outside:
                    unreachable.append({"query_id": q["query_id"], "outside_target_class": outside})
            else:
                flagged += 1
            for system, r in ranked.items():
                lines.append(json.dumps({
                    "query_id": q["query_id"], "system": system,
                    "ranked": [corpus.ids[i] for i in r.indices],
                    "scores": [round(float(s), 6) for s in r.scores],
                    "class_filter_applied": r.class_filter_applied,
                }))
        path = _eval_dir(resolver) / f"runs_{name}_{VERSION}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        summary["sets"][name] = {
            "queries": len(queries), "seconds": round(time.time() - t1, 1),
            "class_aware_without_target_class": flagged,
            "minus_source_class_without_source_class": no_source_class,
            "relevant_outside_target_class": unreachable,
            "source_paragraph_not_in_corpus": src_missing,
        }
        print(f"{name}: {len(queries)} queries in {time.time() - t1:.0f}s; class filter off (no target class) "
              f"for {flagged}; relevant outside the target class for {len(unreachable)}")
    write_json(_eval_dir(resolver) / f"retrieve_summary_{VERSION}.json", summary)
    return 0


# -- score --------------------------------------------------------------------

METRICS = ("recall", "map", "ndcg")
METRIC_LABEL = {"recall": "Recall@10", "map": "MAP@10", "ndcg": "nDCG@10"}
PAIRS = (("hybrid_rrf", "bm25"), ("hybrid_rrf", "dense"), ("class_aware", "hybrid_rrf"), ("bm25", "dense"),
         ("hybrid_minus_source_class", "hybrid_rrf"), ("class_aware", "hybrid_minus_source_class"))


def score_set(queries: list[dict], runs: dict[str, dict[str, list[str]]], *, k: int, resamples: int, seed: int,
              min_class_n: int) -> dict[str, Any]:
    from src.eval import metrics as M
    from src.retrieval.systems import SYSTEMS

    qrels = {q["query_id"]: q["relevant"] for q in queries}
    scored = [q for q in queries if q["relevant"]]
    qids = [q["query_id"] for q in scored]
    clusters = [q["cluster"] for q in scored]
    per_q = {s: M.per_query_scores(runs[s], qrels, k) for s in SYSTEMS}
    kw = {"resamples": resamples, "seed": seed}
    out: dict[str, Any] = {"n_scored": len(scored), "n_unscored_no_relevant": len(queries) - len(scored),
                           "clusters": len(set(clusters)), "systems": {}, "paired": {}, "by_target_class": {}}
    for s in SYSTEMS:
        out["systems"][s] = {
            m: {**M.bootstrap_mean([per_q[s][m][q] for q in qids], **kw),
                "cluster_ci": {k2: v for k2, v in M.bootstrap_mean(
                    [per_q[s][m][q] for q in qids], clusters=clusters, **kw).items() if k2 in ("ci_low", "ci_high")}}
            for m in METRICS
        }
    for a, b in PAIRS:
        out["paired"][f"{a} - {b}"] = {
            m: {**M.paired_bootstrap([per_q[a][m][q] for q in qids], [per_q[b][m][q] for q in qids], **kw),
                "cluster_ci": {k2: v for k2, v in M.paired_bootstrap(
                    [per_q[a][m][q] for q in qids], [per_q[b][m][q] for q in qids], clusters=clusters,
                    **kw).items() if k2 in ("ci_low", "ci_high")}}
            for m in METRICS
        }
    classes = Counter(q["target_class"] for q in scored if q["target_class"])
    for cls, n in sorted(classes.items()):
        if n < min_class_n:
            out["by_target_class"][cls] = {"n": n, "reported": False}
            continue
        sub = [q["query_id"] for q in scored if q["target_class"] == cls]
        out["by_target_class"][cls] = {"n": n, "reported": True, "systems": {
            s: {m: M.bootstrap_mean([per_q[s][m][q] for q in sub], **kw) for m in METRICS} for s in SYSTEMS}}
    out["per_query"] = {s: {m: per_q[s][m] for m in METRICS} for s in SYSTEMS}
    return out


def cmd_score(cfg: dict, resolver: PathResolver) -> int:
    ev = cfg["retrieval"]["eval"]
    sets = _load_sets(resolver)
    meta = read_json(_t2_dir(resolver) / f"t2_qrels_meta_{VERSION}.json")
    retrieve = read_json(_eval_dir(resolver) / f"retrieve_summary_{VERSION}.json")
    result: dict[str, Any] = {
        "version": VERSION, "scored_utc": _now(),
        "protocol": {"cutoff": ev["cutoff"], "bootstrap_resamples": ev["bootstrap_resamples"],
                     "bootstrap_seed": ev["bootstrap_seed"], "ci": "percentile 95%, resampling queries",
                     "cluster_ci": "sensitivity: resampling source texts (query clusters)",
                     "ndcg_gain": "2^grade - 1", "relevant_for_recall_map": "grade >= 1",
                     "per_class_min_n": ev["per_class_min_n"], "pooled_sets": False},
        "sets": {},
    }
    for name, queries in sets.items():
        runs: dict[str, dict[str, list[str]]] = {}
        for line in (_eval_dir(resolver) / f"runs_{name}_{VERSION}.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            runs.setdefault(r["system"], {})[r["query_id"]] = r["ranked"]
        result["sets"][name] = {"bias": meta["sets"][name]["bias"], "qrels": meta["sets"][name],
                                "retrieval": retrieve["sets"][name],
                                **score_set(queries, runs, k=int(ev["cutoff"]), resamples=int(ev["bootstrap_resamples"]),
                                            seed=int(ev["bootstrap_seed"]), min_class_n=int(ev["per_class_min_n"]))}
    result["environment"] = _environment_block(cfg, resolver)
    write_json(resolver.write_path("reports", f"p3001_metrics_{VERSION}.json"), result)
    from src.eval.report import retrieval_report

    resolver.write_path("reports", "p3001_retrieval_baselines.md").write_text(retrieval_report(result), encoding="utf-8")
    for name, s in result["sets"].items():
        print(f"{name} (n={s['n_scored']}):")
        for sys_name, m in s["systems"].items():
            print("   " + sys_name.ljust(27) + "  ".join(
                f"{METRIC_LABEL[k]} {v['mean']:.3f} [{v['ci_low']:.3f}, {v['ci_high']:.3f}]" for k, v in m.items()))
    print("wrote reports/p3001_metrics_v1.json, reports/p3001_retrieval_baselines.md")
    return 0


def _environment_block(cfg: dict, resolver: PathResolver) -> dict[str, Any]:
    emb_meta = read_json(resolver.write_dir("indexes") / IX.EMBEDDINGS_META)
    models_path = resolver.find_read_path("reports", "p3001_llm_models_v1.json")
    llm = cfg.get("llm") or {}
    return {
        **environment(),
        "device": emb_meta.get("device"),
        "embedding": {k: emb_meta.get(k) for k in ("model_id", "model_revision", "revision_verified_against_hub",
                                                  "max_seq_length", "truncated_paragraphs", "paragraphs",
                                                  "total_wall_seconds", "projected_minutes", "built_utc",
                                                  "computed_locally", "reused_kaggle_embeddings")},
        "bm25": cfg["retrieval"]["bm25"],
        "llm": {"model": llm.get("model"), "long_context_model": llm.get("long_context_model"),
                "fallback_model": llm.get("fallback_model"), "model_versions": llm.get("model_versions"),
                "used_in_p3001_baselines": False,
                "smoke_test": (read_json(models_path).get("smoke_test") if models_path else None)},
    }


# -- T1 -----------------------------------------------------------------------


def cmd_t1(cfg: dict, resolver: PathResolver) -> int:
    from src.eval import t1_eval as T
    from src.eval.report import t1_report

    ev = cfg["retrieval"]["eval"]
    items = _read_jsonl(resolver.read_path(*T1_VALIDATED))
    if len(items) != 106:
        print(f"note: validated set holds {len(items)} items (prompt expects 106)")
    wanted = {it["source_candidate_id"] for it in items}
    candidates = {}
    with resolver.read_path(*T1_CANDIDATES).open(encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if r["source_candidate_id"] in wanted:
                candidates[r["source_candidate_id"]] = r
    result = T.run_baselines(items, candidates, resamples=int(ev["bootstrap_resamples"]),
                             seed=int(ev["bootstrap_seed"]))
    result["inputs"] = {p[-1]: _sha(resolver.read_path(*p)) for p in (T1_VALIDATED, T1_CANDIDATES)}
    result["scored_utc"] = _now()
    write_json(resolver.write_path("reports", f"p3001_t1_baselines_{VERSION}.json"), result)
    resolver.write_path("reports", "p3001_t1_baselines.md").write_text(t1_report(result), encoding="utf-8")
    for name, b in result["baselines"].items():
        view = b.get("three_label") or b["fixed_mapping"]
        print(f"{name}: flag Macro-F1 {view['flag']['macro_f1']:.3f} {view['flag']['macro_f1_ci']}, "
              f"judgement Macro-F1 {view['judgement']['macro_f1']:.3f} {view['judgement']['macro_f1_ci']}")
    print("wrote reports/p3001_t1_baselines.md")
    return 0


def cmd_all(cfg: dict, resolver: PathResolver) -> int:
    for step in (cmd_qrels, cmd_retrieve, cmd_score, cmd_t1):
        rc = step(cfg, resolver)
        if rc:
            return rc
    return 0


# -- backup -------------------------------------------------------------------

BACKUP_FILES = (".gitignore", ".env.example", "config/config.yaml", "scripts/run_p3001.py", "scripts/run_llm_setup.py")
BACKUP_DIRS = ("src/llm", "src/eval", "src/retrieval")
BACKUP_GLOBS = ("tests/test_llm_client.py", "tests/test_eval_*.py", "tests/test_retrieval_*.py", "reports/p3001_*")


def cmd_backup(cfg: dict, resolver: PathResolver) -> int:
    """Zip P3-001's code, config, T2 sets, runs and reports next to the repo; verify it; never include keys.

    Excluded: .env, data/llm_cache/ and the float16 embedding matrix (regenerable with `index`; its meta is kept).
    """
    import hashlib
    import zipfile

    from dotenv import dotenv_values

    root = resolver.working_root
    files = [root / f for f in BACKUP_FILES]
    for d in BACKUP_DIRS:
        files += [p for p in (root / d).rglob("*.py")]
    for g in BACKUP_GLOBS:
        files += sorted(root.glob(g))
    files += sorted(_t2_dir(resolver).glob("*"))
    files += sorted(_eval_dir(resolver).glob("*"))
    files.append(resolver.write_dir("indexes") / IX.EMBEDDINGS_META)
    files = sorted({p for p in files if p.is_file() and p.name != ".env"})

    secrets = [v.strip() for v in dotenv_values(root / ".env").values() if v and v.strip()] if (root / ".env").exists() else []
    leaking = [p for p in files if any(s.encode() in p.read_bytes() for s in secrets)]
    if leaking:
        print(f"STOP: {len(leaking)} file(s) contain an API key value; nothing was backed up")
        return 1

    out_dir = root.parent / "p3001_backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / f"p3001_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(root).as_posix())
    with zipfile.ZipFile(zpath) as zf:
        ok = zf.testzip() is None and all(
            hashlib.sha256(zf.read(p.relative_to(root).as_posix())).hexdigest() == _sha(p) for p in files)
    if not ok:
        print(f"STOP: backup {zpath} failed verification")
        return 1
    print(f"backup: {zpath} ({len(files)} files, {zpath.stat().st_size / 1e6:.1f} MB, verified, no key values)")
    return 0


COMMANDS = {"index": cmd_index, "qrels": cmd_qrels, "retrieve": cmd_retrieve, "score": cmd_score,
            "t1": cmd_t1, "all": cmd_all, "backup": cmd_backup}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS))
    args = parser.parse_args()
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    return COMMANDS[args.command](cfg, resolver)


if __name__ == "__main__":
    raise SystemExit(main())
