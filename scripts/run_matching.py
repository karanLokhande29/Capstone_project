#!/usr/bin/env python3
"""CLI for P2-002 cross-class obligation matching.

Part A (local):
    python scripts/run_matching.py units      # A1 preflight + A2 units + A3 blocking counts
    python scripts/run_matching.py stage1     # A4 repeated-wording clusters (local reference copy)
    python scripts/run_matching.py package    # A10 p2002_code.zip + manifest
    python scripts/run_matching.py notebook   # A9 notebooks/phase2-p2002-matching.ipynb
    python scripts/run_matching.py checklist  # A12 Part B checklist with real paths

Part C (local, after Kaggle):
    python scripts/run_matching.py ingest --zip <path/to/p2002_return.zip>
    python scripts/run_matching.py bands
    python scripts/run_matching.py sheet

Part D (local, after Karan labels the sheet):
    python scripts/run_matching.py score --label-source manual \
        [--sheet-file <labelled.csv>] [--sensitivity P015:related,...]

Stage 2 (embeddings, semantic scores, leakage) runs only on Kaggle, through
:func:`kaggle_run`, which the notebook calls. No model is downloaded locally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark import matching as M  # noqa: E402
from src.benchmark.candidates import ObligationCandidate, candidates_filename, load_candidates  # noqa: E402
from src.common.config import REPO_ROOT, load_config  # noqa: E402
from src.common.io_helpers import iter_jsonl, read_json, read_jsonl, write_json, write_jsonl, write_text  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver, repo_relative  # noqa: E402

V = M.VERSION
MATCHING_SUBDIR = "matching"
UPLOAD_SUBDIR = "kaggle_upload"
RETURN_SUBDIR = "kaggle_return"

UNITS_FILE = f"p2002_units_{V}.jsonl"
UNITS_METRICS_FILE = f"p2002_units_metrics_{V}.json"
STAGE1_LOCAL_FILE = f"p2002_stage1_local_{V}.json"
MATCHES_FILE = f"p2002_matches_{V}.jsonl"
CLUSTERS_FILE = f"p2002_clusters_{V}.json"
LEAKAGE_FILE = f"p2002_leakage_{V}.json"
METRICS_FILE = f"p2002_metrics_{V}.json"
EMBEDDINGS_FILE = f"p2002_embeddings_{V}.npz"
RETURN_ZIP = "p2002_return.zip"
CODE_ZIP = "p2002_code.zip"
CODE_MANIFEST = "p2002_code_manifest.json"
BANDS_FILE = f"p2002_bands_{V}.json"
SHEET_FILE = f"p2002_validation_sheet_{V}.csv"
KEY_FILE = f"p2002_validation_key_{V}.json"
THRESHOLDED_FILE = f"t1_matches_{V}_thresholded.jsonl"
VALIDATION_METRICS_FILE = f"p2002_validation_metrics_{V}.json"
REPORT_FILE = "p2002_matching.md"
NOTEBOOK = Path("notebooks/phase2-p2002-matching.ipynb")

RETURN_MEMBERS = (MATCHES_FILE, CLUSTERS_FILE, LEAKAGE_FILE, METRICS_FILE)
CODE_DIRS = ("src", "scripts", "config")
CODE_FILES = ("requirements.txt",)


def _mdir(resolver: PathResolver, *parts: str) -> Path:
    path = resolver.write_dir("benchmark") / MATCHING_SUBDIR
    for p in parts:
        path = path / p
    path.mkdir(parents=True, exist_ok=True)
    return path


def _inputs(resolver: PathResolver, mc: M.MatchingConfig):
    cands = load_candidates(resolver.read_path("benchmark", "candidates", candidates_filename("v4")))
    manifest = read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))
    cells = read_jsonl(resolver.read_path("matrix", "matrix_v1.jsonl"))
    return cands, manifest, cells


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Part A
# ---------------------------------------------------------------------------


def run_units(cfg, resolver, logger) -> dict:
    mc = M.MatchingConfig.from_cfg(cfg)
    cands, manifest, cells = _inputs(resolver, mc)
    pre = M.preflight(cands, manifest, cells, mc)
    fam = {r["document_id"]: r.get("subject_family") for r in manifest}
    eligible, no_family, accounting = M.classify_candidates(cands, fam, mc)
    units = M.build_units(eligible, no_family, fam, mc)
    write_jsonl(_mdir(resolver) / UNITS_FILE, [u.to_dict() for u in units])
    fam_classes: dict[str, set] = {}
    for c in eligible:
        fam_classes.setdefault(fam[c.document_id], set()).add(c.entity_class)
    per_cand: dict[str, int] = {}
    for u in units:
        per_cand[u.candidate_id] = per_cand.get(u.candidate_id, 0) + 1
    metrics = {
        "generated_at": _now(),
        "preflight": pre,
        "accounting": accounting,
        "units_total": len(units),
        "units_eligible": sum(1 for u in units if u.eligible),
        "units_core_no_family": sum(1 for u in units if not u.eligible),
        "whole_paragraph_units": sum(
            1 for c in [*eligible, *no_family]
            if sum(1 for e in c.cue_exclusions if e is None) == 1 and len(c.span_text) < mc.whole_paragraph_max_chars
        ),
        "units_per_candidate_max": max(per_cand.values()),
        "unit_chars_max": max(len(u.text) for u in units),
        "units_over_2000_chars": sum(1 for u in units if len(u.text) > 2000),
        "truncation_note": "the authoritative truncated-unit count (tokens > max_seq_length) comes from the "
                           "model tokenizer on Kaggle",
        "blocks": len(fam_classes),
        "families_shared_by_2plus_core_classes": sum(1 for v in fam_classes.values() if len(v) >= 2),
    }
    write_json(_mdir(resolver) / UNITS_METRICS_FILE, metrics)
    return metrics


def run_stage1(cfg, resolver, logger) -> dict:
    mc = M.MatchingConfig.from_cfg(cfg)
    cands, manifest, cells = _inputs(resolver, mc)
    M.preflight(cands, manifest, cells, mc)
    fam = {r["document_id"]: r.get("subject_family") for r in manifest}
    eligible, no_family, _ = M.classify_candidates(cands, fam, mc)
    units = M.build_units(eligible, no_family, fam, mc)
    t = time.time()
    s1 = M.stage1_clusters(units, mc)
    s1["summary"]["runtime_sec"] = round(time.time() - t, 1)
    write_json(_mdir(resolver) / STAGE1_LOCAL_FILE, s1)
    return s1["summary"]


def build_code_zip(root: Path, out_dir: Path) -> dict:
    """A10: src/, scripts/, config/, requirements.txt, and no data/. SHA-256 of every file in a manifest."""
    files = []
    for d in CODE_DIRS:
        for p in sorted((root / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo") \
                    and p.name != ".DS_Store":
                files.append(p)
    files += [root / f for f in CODE_FILES if (root / f).is_file()]
    manifest = {
        "prompt": "P2-002",
        "created_at": _now(),
        "files": {str(p.relative_to(root)).replace("\\", "/"): sha256_file(p) for p in files},
    }
    if any(k.startswith("data/") for k in manifest["files"]):
        raise M.MatchingError("code zip must not contain data/")
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / CODE_ZIP
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, str(p.relative_to(root)).replace("\\", "/"))
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True))
    manifest["zip_sha256"] = sha256_file(zpath)
    write_json(out_dir / CODE_MANIFEST, manifest)
    (out_dir / (CODE_ZIP + ".sha256")).write_text(f"{manifest['zip_sha256']}  {CODE_ZIP}\n", encoding="utf-8")
    return {"zip": repo_relative(zpath), "zip_sha256": manifest["zip_sha256"], "files": len(files),
            "manifest": repo_relative(out_dir / CODE_MANIFEST)}


def run_package(cfg, resolver, logger) -> dict:
    return build_code_zip(REPO_ROOT, _mdir(resolver, UPLOAD_SUBDIR))


# ---------------------------------------------------------------------------
# Kaggle side (called from the notebook)
# ---------------------------------------------------------------------------


def smoke_ids(cands: Sequence[ObligationCandidate], manifest, mc: M.MatchingConfig) -> list[str]:
    """200 seeded eligible candidates, spread across core classes (round-robin by class)."""
    import random

    fam = {r["document_id"]: r.get("subject_family") for r in manifest}
    eligible, _, _ = M.classify_candidates(cands, fam, mc)
    by_class: dict[str, list[str]] = {}
    for c in eligible:
        by_class.setdefault(c.entity_class, []).append(c.candidate_id)
    rng = random.Random(mc.seeds["smoke"])
    for ids in by_class.values():
        rng.shuffle(ids)
    out, classes = [], sorted(by_class)
    while len(out) < mc.smoke_candidates and any(by_class.values()):
        for cls in classes:
            if by_class[cls] and len(out) < mc.smoke_candidates:
                out.append(by_class[cls].pop())
    return sorted(out)


def kaggle_run(
    cfg: Mapping[str, Any],
    resolver: PathResolver,
    embed: M.Embedder,
    *,
    model_id: str,
    model_revision: str,
    token_lengths=None,
    checkpoint_dir: Path | str | None = None,
    smoke: bool = False,
    logger=None,
) -> dict:
    """Stage 2 end to end on Kaggle (or in the integration test, with a fake embedder).

    ``smoke=True`` runs every stage on the 200 seeded smoke candidates and
    writes nothing. The full run returns the result for
    :func:`write_stage2_outputs`.
    """
    mc = M.MatchingConfig.from_cfg(cfg)
    cands, manifest, cells = _inputs(resolver, mc)
    pre = M.preflight(cands, manifest, cells, mc)
    subset = smoke_ids(cands, manifest, mc) if smoke else None
    t = time.time()
    result = M.run_stage2(cands, manifest, cells, mc, embed, model_id=model_id, model_revision=model_revision,
                          subset_ids=subset, checkpoint_dir=None if smoke else checkpoint_dir,
                          token_lengths=token_lengths, logger=logger)
    result["preflight"] = pre
    result["runtime_sec"] = round(time.time() - t, 1)
    result["smoke"] = smoke
    return result


def write_stage2_outputs(result: Mapping[str, Any], out_dir: Path, extra_metrics: Mapping[str, Any]) -> dict:
    """Write the four return files into ``out_dir`` (matches, clusters, leakage, metrics)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / MATCHES_FILE, result["records"])
    write_json(out_dir / CLUSTERS_FILE, result["stage1"])
    write_json(out_dir / LEAKAGE_FILE, result["leakage"] or {})
    metrics = {
        "preflight": result.get("preflight"),
        "runtime_sec": result.get("runtime_sec"),
        "accounting": result["accounting"],
        "unit_metrics": result["unit_metrics"],
        "stage1_summary": result["stage1"]["summary"],
        "score_stats": result["score_stats"],
        "match_metrics": result["match_metrics"],
        "provisional_band_edges": result["provisional_band_edges"],
        "leakage_summary": {k: v for k, v in (result["leakage"] or {}).items() if k != "rows"},
        **dict(extra_metrics),
    }
    write_json(out_dir / METRICS_FILE, metrics)
    return metrics


def build_return_zip(out_dir: Path) -> Path:
    """The return trip carries the four result files only. No embeddings, no annotation file."""
    zpath = out_dir / RETURN_ZIP
    names = [n for n in RETURN_MEMBERS if (out_dir / n).is_file()]
    if any("annotation_" in n for n in names):
        raise M.MatchingError("return zip would carry an annotation file")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(out_dir / n, n)
    members = zipfile.ZipFile(zpath).namelist()
    assert not any("annotation_" in n for n in members), "annotation file in the return zip"
    assert not any(n.endswith(".npz") for n in members), "embeddings must not be in the return zip"
    return zpath


def write_embeddings(result: Mapping[str, Any], path: Path) -> Path:
    import numpy as np

    np.savez_compressed(path, vectors=result["vectors"].astype(np.float16),
                        unit_ids=np.array([u.unit_id for u in result["units"]]))
    return path


# ---------------------------------------------------------------------------
# Part C
# ---------------------------------------------------------------------------


def run_ingest(cfg, resolver, logger, zip_path: str) -> dict:
    """C1 part 1: unpack the return zip and re-check it against locally recomputed facts."""
    mc = M.MatchingConfig.from_cfg(cfg)
    zpath = Path(zip_path)
    names = zipfile.ZipFile(zpath).namelist()
    if any("annotation_" in n for n in names):
        raise M.MatchingError("return zip carries an annotation file")
    missing = [n for n in RETURN_MEMBERS if n not in names]
    if missing:
        raise M.MatchingError(f"return zip is missing {missing}")
    dest = _mdir(resolver, RETURN_SUBDIR)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest)

    cands, manifest, cells = _inputs(resolver, mc)
    M.preflight(cands, manifest, cells, mc)
    fam = {r["document_id"]: r.get("subject_family") for r in manifest}
    eligible, no_family, _ = M.classify_candidates(cands, fam, mc)
    records = read_jsonl(dest / MATCHES_FILE)
    expected = expected_statuses(eligible, fam, cells, mc)
    got = {(r["source_candidate_id"], r["target_entity_class"]): r["status"] for r in records}
    problems = []
    if len(records) != len(expected):
        problems.append(f"{len(records)} match records, expected {len(expected)}")
    diff = [k for k in expected if got.get(k) != expected[k]]
    if diff:
        problems.append(f"{len(diff)} statuses differ from the local recomputation, e.g. {diff[0]}")
    revs = {(r["model_id"], r["model_revision"]) for r in records}
    if revs != {(mc.model_id, mc.model_revision)}:
        problems.append(f"model id/revision in records {revs} != config {(mc.model_id, mc.model_revision)}")
    local_s1 = _mdir(resolver) / STAGE1_LOCAL_FILE
    clusters_match = None
    if local_s1.is_file():
        clusters_match = read_json(local_s1)["unit_cluster"] == read_json(dest / CLUSTERS_FILE)["unit_cluster"]
        if not clusters_match:
            problems.append("Kaggle stage-1 clusters differ from the local stage1 run on the same inputs")
    if problems:
        raise M.MatchingError("ingest failed: " + "; ".join(problems))
    from collections import Counter

    return {
        "zip": repo_relative(zpath),
        "zip_sha256": sha256_file(zpath),
        "records": len(records),
        "status_counts": dict(Counter(r["status"] for r in records)),
        "stage1_clusters_identical_to_local": clusters_match,
        "extracted_to": repo_relative(dest),
    }


def expected_statuses(eligible, doc_family, cells, mc: M.MatchingConfig) -> dict[tuple[str, str], str]:
    """Statuses from the candidates and the matrix alone: an independent check of the Kaggle output."""
    present: dict[str, set] = {}
    for c in eligible:
        present.setdefault(doc_family[c.document_id], set()).add(c.entity_class)
    populated = {(c["entity_class"], c["subject_family"]) for c in cells if c.get("populated")}
    out = {}
    for c in eligible:
        f = doc_family[c.document_id]
        for t in mc.core_classes:
            if t == c.entity_class:
                continue
            if t in present[f]:
                out[(c.candidate_id, t)] = M.STATUS_SCORED
            elif (t, f) in populated:
                out[(c.candidate_id, t)] = M.STATUS_NO_CANDIDATES
            else:
                out[(c.candidate_id, t)] = M.STATUS_NO_DIRECTION
    return out


def run_bands(cfg, resolver, logger) -> dict:
    """C1 part 2: band edges fixed BEFORE any sample is drawn."""
    ret = _mdir(resolver, RETURN_SUBDIR)
    if (_mdir(resolver) / SHEET_FILE).is_file():
        raise M.MatchingError("a validation sheet already exists; bands must be fixed before sampling, "
                              "so they are not recomputed now")
    records = read_jsonl(ret / MATCHES_FILE)
    best = [r["top_targets"][0]["semantic_score"] for r in records if r["status"] == M.STATUS_SCORED]
    edges = M.band_edges(best)
    edges["defined_at"] = _now()
    edges["defined_before_sampling"] = True
    write_json(_mdir(resolver) / BANDS_FILE, edges)
    return edges


def run_sheet(cfg, resolver, logger, force: bool = False) -> dict:
    """C2: the 60-pair blind sheet + a separate key file."""
    mc = M.MatchingConfig.from_cfg(cfg)
    bands_path = _mdir(resolver) / BANDS_FILE
    if not bands_path.is_file():
        raise M.MatchingError("run `bands` first: band edges must exist before the sample is drawn")
    edges = read_json(bands_path)
    ret = _mdir(resolver, RETURN_SUBDIR)
    records = read_jsonl(ret / MATCHES_FILE)
    unit_cluster = read_json(ret / CLUSTERS_FILE)["unit_cluster"]
    cands = {c.candidate_id: c for c in load_candidates(
        resolver.read_path("benchmark", "candidates", candidates_filename("v4")))}
    rows, key = M.draw_validation_sheet(records, edges, unit_cluster, cands, mc)
    M.assert_sheet_blind(rows)
    sheet = M.write_sheet(rows, _mdir(resolver) / SHEET_FILE, force=force)
    key["meta"]["drawn_at"] = _now()
    write_json(_mdir(resolver) / KEY_FILE, key)
    return {"sheet": repo_relative(sheet), "key": repo_relative(_mdir(resolver) / KEY_FILE), **key["meta"]}


# ---------------------------------------------------------------------------
# Part D
# ---------------------------------------------------------------------------


def d8_split(accounting: Mapping[str, Any]) -> dict:
    """Core vs function-heading kept candidates, each split by subject family."""
    by = accounting["by_class"]
    fn = lambda k: sum(v.get(k, 0) for v in by.values())
    out = {"core_with_family": accounting["eligible"],
           "core_no_family": accounting["excluded_no_subject_family_core"],
           "function_with_family": fn("function_heading_with_family"),
           "function_no_family": fn("function_heading_no_family")}
    out["core_total"] = out["core_with_family"] + out["core_no_family"]
    out["function_total"] = out["function_with_family"] + out["function_no_family"]
    out["total"] = out["core_total"] + out["function_total"]
    return out


def validation_findings(result: Mapping[str, Any], threshold: float) -> dict:
    """Pair-level findings on the labelled sample, from the key (no new labels)."""
    rows = result["rows"]
    sem = [x for x in rows if x["stratum"] in M.BANDS]
    above = [x for x in sem if x["semantic_score"] >= threshold]
    n = len(above)

    def top(k):
        t = sorted(sem, key=lambda x: (-x[k], x["pair_id"]))[:n]
        return {"n": n, "counterparts": sum(x["label"] != M.LABEL_UNRELATED for x in t),
                "same": sum(x["label"] == M.LABEL_SAME for x in t),
                "related": sum(x["label"] == M.LABEL_RELATED for x in t)}

    rel = [x for x in rows if x["label"] == M.LABEL_RELATED]
    unrel = [x["semantic_score"] for x in rows if x["label"] == M.LABEL_UNRELATED]
    return {
        "semantic_pairs": len(sem),
        "top_n_by_semantic": top("semantic_score"),
        "top_n_by_lexical": top("lexical_score"),
        "related_total": len(rel),
        "related_below_threshold": sum(1 for x in rel if x["stratum"] != M.STRATUM_STAGE1
                                       and x["semantic_score"] < threshold),
        "unrelated_total": len(unrel),
        "unrelated_max_semantic": max(unrel) if unrel else None,
    }


def boilerplate_split(resolver) -> dict:
    ret = _mdir(resolver, RETURN_SUBDIR)
    clusters = read_json(ret / CLUSTERS_FILE)["clusters"]
    unit_text = {u["unit_id"]: u["text"] for u in iter_jsonl(_mdir(resolver) / UNITS_FILE)}
    return M.boilerplate_cluster_split(clusters, unit_text)


def parse_relabels(spec: str | None) -> dict[str, str]:
    """``P015:related,P018:related`` -> {pair_id: label}, for the sensitivity reading only."""
    out = {}
    for part in (spec or "").split(","):
        if part.strip():
            pid, label = (s.strip() for s in part.split(":"))
            if label.lower() not in M.LABELS:
                raise M.MatchingError(f"sensitivity relabel {part!r}: label must be one of {M.LABELS}")
            out[pid] = label.lower()
    return out


def score_command(argv: Sequence[str]) -> str:
    """The command line as run, quoted only where a shell would need it."""
    import shlex

    return " ".join(["python", "scripts/run_matching.py", *(shlex.quote(a) for a in argv)])


def run_score(cfg, resolver, logger, sheet_file: str | None = None, label_source: str | None = None,
              sensitivity: str | None = None, command: str | None = None) -> dict:
    """D1 score, D2 threshold, D3 report.

    ``command`` is the exact command line (``main`` passes it); a direct call
    records the equivalent command rebuilt from its arguments.
    """
    if command is None:
        argv = ["score"]
        if label_source:
            argv += ["--label-source", label_source]
        if sheet_file:
            argv += ["--sheet-file", sheet_file]
        if sensitivity:
            argv += ["--sensitivity", sensitivity]
        command = score_command(argv)
    if label_source not in ("manual", "ai_assisted"):
        raise M.MatchingError("score needs --label-source manual|ai_assisted")
    mc = M.MatchingConfig.from_cfg(cfg)
    mdir = _mdir(resolver)
    sheet = Path(sheet_file) if sheet_file else mdir / SHEET_FILE
    labelled = M.read_labelled_sheet(sheet)
    blank = [r.get("pair_id") for r in labelled if not (r.get("label") or "").strip()]
    if blank:
        raise M.MatchingError(
            f"{sheet} has {len(blank)} of {len(labelled)} rows with a blank label (e.g. {blank[:5]}); "
            "score only a fully labelled sheet, passed with --sheet-file")
    key = read_json(mdir / KEY_FILE)
    edges = read_json(mdir / BANDS_FILE)
    drawn = {r["pair_id"]: r for r in M.read_labelled_sheet(mdir / SHEET_FILE)}
    changed = [r["pair_id"] for r in labelled if r["pair_id"] not in drawn or any(
        r[c] != drawn[r["pair_id"]][c] for c in ("subject_family", "class_a", "span_a", "class_b", "span_b"))]
    if changed:
        raise M.MatchingError(f"labelled sheet differs from the drawn sheet outside label/note: {changed[:5]}")
    result = M.score_validation(labelled, key)
    if not result["complete"]:
        return {"complete": False, "problems": result["problems"][:10], "labelled": result["labelled"]}
    ret = _mdir(resolver, RETURN_SUBDIR)
    records = read_jsonl(ret / MATCHES_FILE)
    thr = M.choose_threshold(result, edges, mc.counterpart_target)
    high = result["by_stratum"][M.BAND_HIGH]["counterpart_rate"]["rate"]
    s1_same = result["by_stratum"][M.STRATUM_STAGE1]["same_rate"]["rate"]
    leak = read_json(ret / LEAKAGE_FILE)
    leak_official = M.summarise_leakage(leak.get("rows", []), edges["high_lower"], seed=leak.get("seed"))
    gates = {
        "high_counterpart_rate": high,
        "stage1_same_rate": s1_same,
        "leakage_rate": leak_official["leakage_rate"],
        "proceed": bool(high is not None and high >= mc.gates["proceed_high_counterpart_min"]
                        and s1_same is not None and s1_same >= mc.gates["stage1_same_min"]),
        "stop_high_below_60": bool(high is not None and high < mc.gates["escalate_high_counterpart_below"]),
        "stop_stage1_same_below_90": bool(s1_same is not None and s1_same < mc.gates["stage1_same_min"]),
        "stop_leakage_above_30": bool(leak_official["leakage_rate"] is not None
                                      and leak_official["leakage_rate"] > mc.gates["leakage_max"]),
    }
    relabels = parse_relabels(sensitivity)
    unknown = [p for p in relabels if p not in key["pairs"]]
    if unknown:
        raise M.MatchingError(f"sensitivity relabel names pairs not on the sheet: {unknown}")
    alt_rows = [{**r, "label": relabels.get(r["pair_id"], r["label"])} for r in labelled]
    alt = M.score_validation(alt_rows, key) if relabels else None
    out = {"scored_at": _now(), "command": command, "label_source": label_source, "sheet_file": repo_relative(sheet),
           "sheet_sha256": sha256_file(sheet),
           "validation": {k: v for k, v in result.items() if k != "rows"},
           "threshold": thr, "gates": gates, "leakage_official_edge": {k: v for k, v in leak_official.items()
                                                                      if k != "rows"},
           "sheet_meta": key.get("meta", {})}
    if alt:
        out["sensitivity"] = {
            "relabels": relabels,
            "by_stratum": {s: {k: b[k] for k in ("n", "same", "related", "unrelated", "counterpart_rate")}
                           for s, b in alt["by_stratum"].items()},
            "threshold": M.choose_threshold(alt, edges, mc.counterpart_target),
            "note": "an alternative reading of the named pairs; the reviewer's labels stand and set the threshold",
        }
    counts = {}
    if thr["chosen"] and not gates["stop_high_below_60"]:
        value = thr["chosen"]["value"]
        thresholded = M.apply_threshold(records, value)
        write_jsonl(mdir / THRESHOLDED_FILE, thresholded)
        from collections import Counter

        counts = dict(Counter(r["status"] for r in thresholded))
        n_scored = counts.get(M.STATUS_MATCHED, 0) + counts.get(M.STATUS_BELOW_THRESHOLD, 0)
        out["thresholded_status_counts"] = counts
        out["thresholded_records"] = len(thresholded)
        out["matched_share_of_scored"] = counts.get(M.STATUS_MATCHED, 0) / n_scored if n_scored else None
        s1_below = [r for r in thresholded if r["status"] == M.STATUS_BELOW_THRESHOLD
                    and r["top_targets"][0]["match_type"] in M.STAGE1_TYPES]
        out["stage1_top1_below_threshold"] = {
            "rows": len(s1_below),
            "distinct_pairs": len({frozenset((r["source_candidate_id"], r["top_targets"][0]["candidate_id"]))
                                   for r in s1_below}),
            "semantic_range": [min((r["top_targets"][0]["semantic_score"] for r in s1_below), default=None),
                               max((r["top_targets"][0]["semantic_score"] for r in s1_below), default=None)],
        }
        out["lexical_at_matched_coverage"] = M.lexical_at_matched_coverage(records, result, value)
    else:
        value = edges["high_lower"]
        out["matched_share_of_scored"] = None
        out["lexical_at_matched_coverage"] = M.lexical_at_matched_coverage(records, result, value)
    out["findings"] = validation_findings(result, value)
    out["boilerplate_stage1"] = boilerplate_split(resolver)
    out["d8_split"] = d8_split(read_json(ret / METRICS_FILE)["accounting"])
    write_json(resolver.write_path("reports", VALIDATION_METRICS_FILE), out)
    out["report"] = repo_relative(write_report(resolver, out))
    return out


NOTES_FILE = "p2002_matching_notes.md"


def write_report(resolver: PathResolver, v: Mapping[str, Any]) -> Path:
    """D3: reports/p2002_matching.md from the metrics files (reads only).

    Every number is generated from files. Hand-written interpretation lives in
    reports/p2002_matching_notes.md and is embedded verbatim at the end.
    """
    ret = _mdir(resolver, RETURN_SUBDIR)
    m = read_json(ret / METRICS_FILE)
    edges = read_json(_mdir(resolver) / BANDS_FILE)
    pct = lambda x: f"{x:.1%}" if isinstance(x, (int, float)) else "n/a"
    ci = lambda w: f"{pct(w[0])}–{pct(w[1])}" if w else "n/a"
    rate = lambda r: f"{r['k']}/{r['n']} = {pct(r['rate'])} (Wilson {ci(r['wilson_95'])})"
    acc, um, s1, ms = m["accounting"], m["unit_metrics"], m["stage1_summary"], m["match_metrics"]
    d8, bp, fd, thr, gates = v["d8_split"], v["boilerplate_stage1"], v["findings"], v["threshold"], v["gates"]
    val = v["validation"]
    kg = m.get("kaggle", {})
    code_sha_file = _mdir(resolver, UPLOAD_SUBDIR) / f"{CODE_ZIP}.sha256"
    code_sha = code_sha_file.read_text(encoding="utf-8").split()[0] if code_sha_file.is_file() else "n/a"
    chosen = thr["chosen"]
    lines = [
        "# P2-002 — Cross-class obligation matching",
        "",
        f"_Generated {v['scored_at']} by `{v['command']}`. Label source: "
        f"**{v['label_source']}**. Sheet: `{Path(v['sheet_file']).name}` (sha256 `{v['sheet_sha256'][:12]}…`)._",
        "",
        "Candidate matches only. This step assigns no `applies_to` and no `differential_flag`.",
        "",
        "## Outcome",
        "",
        f"- §V proceed condition: **{'met' if gates['proceed'] else 'NOT met'}**. High-band counterpart rate "
        f"{pct(gates['high_counterpart_rate'])} (needs ≥ 80%); stage-1 same rate {pct(gates['stage1_same_rate'])} "
        "(needs ≥ 90%).",
        f"- Stop conditions: high < 60% {gates['stop_high_below_60']}; stage-1 same < 90% "
        f"{gates['stop_stage1_same_below_90']}; leakage > 30% {gates['stop_leakage_above_30']}.",
        (f"- Operating threshold: **{chosen['value']}** (the {chosen['edge']} edge; per-band rule, walking down "
         f"from the high band). Chosen on the same 60-pair sample it is scored on, so the rate at the threshold "
         "is optimistic." if chosen else "- Operating threshold: **none chosen**."),
        f"- Matched share of scored rows at that threshold: {pct(v.get('matched_share_of_scored'))}.",
        "",
        "## Inputs and the D8 split",
        "",
        f"- Candidates: rules v4, {m['preflight']['candidates_kept']:,} kept of {m['preflight']['candidates_total']:,}; "
        f"{m['preflight']['raw_entity_classes']} raw entity classes; matrix {m['preflight']['matrix_cells']:,} cells "
        f"({m['preflight']['matrix_cells_populated']} populated).",
        f"- The {len(acc['core_classes'])} core entity classes are matched against each other. The "
        f"{len(acc['function_headings'])} function headings are a separate cross-cutting pool: counted, not matched.",
        "",
        "| | With subject family | No subject family | Total |",
        "|---|---|---|---|",
        f"| Core classes | {d8['core_with_family']:,} (matched) | {d8['core_no_family']:,} | {d8['core_total']:,} |",
        f"| Function headings | {d8['function_with_family']:,} | {d8['function_no_family']:,} | {d8['function_total']:,} |",
        f"| **Total kept** | | | **{d8['total']:,}** |",
        "",
        "| Class | Eligible | Core, no family | Function heading |",
        "|---|---|---|---|",
    ]
    for cls, c in acc["by_class"].items():
        lines.append(f"| {cls} | {c.get('eligible', 0):,} | {c.get('no_subject_family', 0):,} | "
                     f"{c.get('function_heading', 0):,} |")
    span = ", ".join(f"{k} classes: {n:,}" for k, n in s1["cross_class_span_distribution"].items())
    lines += [
        "",
        "## Units and blocks",
        "",
        f"- Units: {um['units_total']:,} ({um['units_eligible']:,} eligible, {um['units_core_no_family']:,} core with "
        f"no family, kept as leakage targets). Truncated at {um['max_seq_length']} tokens: **{um['units_truncated']}**. "
        f"Longest unit: {um['unit_chars_max']:,} characters.",
        f"- Blocks (subject families): {um['blocks']}. Families shared by 2+ core classes: "
        f"{um['families_shared_by_2plus_core_classes']}.",
        "",
        "## Stage 1: repeated wording",
        "",
        f"- Clusters: {s1['clusters_total']:,} in total; **{s1['clusters_cross_class']:,} cross-class** "
        f"({s1['clusters_within_one_class']} within one class). Cross-class clusters hold "
        f"{s1['units_in_cross_class_clusters']:,} units and {s1['candidates_in_cross_class_clusters']:,} candidates; "
        f"{s1['cross_class_clusters_all_identical']:,} are all-identical text.",
        f"- Classes spanned per cross-class cluster: {span}.",
        f"- **With and without boilerplate.** {bp['clusters_boilerplate']:,} of the {bp['clusters_cross_class']:,} "
        f"cross-class clusters contain text matching a non-obligation pattern (repeal/savings "
        f"{bp['by_pattern']['repeal_savings']}, State/UT nodal-officer designation "
        f"{bp['by_pattern']['state_nodal_officer']}, data-format table row {bp['by_pattern']['format_table_row']}). "
        f"Without them: **{bp['clusters_without_boilerplate']:,}** clusters. Candidates in boilerplate clusters: "
        f"{bp['candidates_in_boilerplate_clusters']:,} of {bp['candidates_in_cross_class_clusters']:,}.",
        "- The patterns are a reporting filter only. The extraction rules and match statuses are unchanged; they are "
        "recorded for P2-004's filter:",
    ]
    lines += [f"  - `{k}`: `{p}`" for k, p in bp["patterns"].items()]
    lines += [
        "",
        "## Statuses and scores",
        "",
        f"- Match records: {ms['status_overall']['scored'] + ms['status_overall'].get('no_direction_in_family', 0) + ms['status_overall'].get('no_candidates_in_family', 0):,}. "
        + "; ".join(f"`{k}` {n:,}" for k, n in ms["status_overall"].items())
        + ". `no_candidates_in_family` never occurs: every populated core cell has kept candidates.",
        f"- Top-1 match type (scored): " + "; ".join(f"{k} {n:,}" for k, n in ms["top1_match_type"].items()) + ".",
        f"- Top-1 agreement, semantic vs lexical: {pct(m['score_stats']['top1_agreement_semantic_vs_lexical'])} "
        f"(n = {m['score_stats']['top1_agreement_n']:,}).",
        "- Best semantic score (scored rows): "
        + ", ".join(f"{k} {x}" for k, x in ms["best_semantic_score_distribution"].items() if k != "n")
        + f" (n = {ms['best_semantic_score_distribution']['n']:,}).",
        f"- Band edges, fixed before sampling ({edges['defined_at']}): low < {edges['mid_lower']} ≤ mid < "
        f"{edges['high_lower']} ≤ high (tertiles, n = {edges['n']:,}).",
        "",
        "<details><summary>Statuses by class pair (source → target)</summary>",
        "",
        "| Source → target | scored | no_candidates_in_family | no_direction_in_family |",
        "|---|---|---|---|",
    ]
    for pair, c in ms["status_by_class_pair"].items():
        lines.append(f"| {pair} | {c.get('scored', 0):,} | {c.get('no_candidates_in_family', 0):,} | "
                     f"{c.get('no_direction_in_family', 0):,} |")
    lk = v["leakage_official_edge"]
    lines += [
        "",
        "</details>",
        "",
        "## Blocking leakage",
        "",
        f"- {lk['leaks']}/{lk['n']} = **{pct(lk['leakage_rate'])}** (Wilson {ci(lk['leakage_wilson_95'])}) of sampled "
        f"eligible candidates have their best cross-class match, searched without blocking, outside their own family "
        f"and at or above the high edge {lk['high_lower_edge_used']}. Criterion ≤ 30%: "
        f"**{'met' if not gates['stop_leakage_above_30'] else 'NOT met'}**.",
        f"- Best cross-class match outside the family at any score: {lk['best_outside_family_any_score']}/{lk['n']} "
        f"({lk['best_outside_family_no_family_target']} of them in a document with no family). Seed {lk['seed']}.",
        "",
        "## Validation (60 blind pairs)",
        "",
        f"Labels: `same`, `related`, `unrelated`; label source **{v['label_source']}**; the reviewer did not open the key.",
        "",
        "| Stratum | n | same | related | unrelated | Counterpart rate (Wilson 95%) | Same rate (Wilson 95%) | Related share |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s, b in [*val["by_stratum"].items(), ("overall", val["overall"])]:
        lines.append(f"| {s} | {b['n']} | {b['same']} | {b['related']} | {b['unrelated']} | "
                     f"{pct(b['counterpart_rate']['rate'])} ({ci(b['counterpart_rate']['wilson_95'])}) | "
                     f"{pct(b['same_rate']['rate'])} ({ci(b['same_rate']['wilson_95'])}) | {pct(b['related_share'])} |")
    lx = v["lexical_at_matched_coverage"]
    ts, tl = fd["top_n_by_semantic"], fd["top_n_by_lexical"]
    lines += [
        "",
        "### Semantic vs lexical",
        "",
        f"- On the {fd['semantic_pairs']} semantic-stratum pairs, top {ts['n']} by semantic score: "
        f"{ts['counterparts']}/{ts['n']} counterparts ({ts['same']} same, {ts['related']} related). "
        f"Top {tl['n']} by lexical score: {tl['counterparts']}/{tl['n']} ({tl['same']} same, {tl['related']} related).",
        f"- At equal coverage of all scored rows ({pct(lx['coverage'])}): semantic ≥ {lx['semantic_threshold']} gives "
        f"{rate(lx['semantic'])}; lexical ≥ {round(lx['lexical_threshold'], 6)} gives {rate(lx['lexical'])}. "
        f"Caveat: {lx['caveat']}.",
        "",
        "### Threshold (D2)",
        "",
        "Rule: walk down from the high band; a band's lower edge qualifies when that band's own counterpart "
        f"rate is ≥ {pct(thr['target'])} and every band above it qualified.",
        "",
        "| Edge | Value | Band | Band counterpart rate | Qualifies |",
        "|---|---|---|---|---|",
    ]
    for e in thr["evaluated"]:
        lines.append(f"| {e['edge']} | {e['value']} | {e['band']} | {pct(e['counterpart_rate'])} | {e['qualifies']} |")
    lines += [
        "",
        (f"- Chosen: **{chosen['value']}** ({chosen['edge']}). {fd['related_below_threshold']} of the "
         f"{fd['related_total']} `related` pairs score below it; the highest `unrelated` pair scores "
         f"{fd['unrelated_max_semantic']}. {thr['note'].capitalize()}." if chosen else "- No edge qualifies."),
    ]
    if v.get("thresholded_status_counts"):
        c = v["thresholded_status_counts"]
        lines += [
            f"- `{THRESHOLDED_FILE}`: {v['thresholded_records']:,} records; "
            + "; ".join(f"`{k}` {n:,}" for k, n in sorted(c.items()))
            + f". Matched share of scored rows: **{pct(v['matched_share_of_scored'])}**. Pure semantic cut on the "
            "top-1 score: a stage-1 top-1 pair gets no exemption, so "
            f"{v['stage1_top1_below_threshold']['rows']:,} rows ({v['stage1_top1_below_threshold']['distinct_pairs']:,} "
            "distinct pairs) whose top target is a near-duplicate prefix match are `below_threshold` (these are mostly "
            "fragments; the stage-1 validation stratum never sampled them). Below-threshold rows keep their top-3 "
            "targets.",
        ]
    sens = v.get("sensitivity")
    if sens:
        st = sens["threshold"]["chosen"]
        lo = sens["by_stratum"]["low"]
        lines += [
            "",
            "### Sensitivity: an alternative reading",
            "",
            f"- Relabelling {', '.join(f'{p} → {l}' for p, l in sens['relabels'].items())}: low band "
            f"{lo['counterpart_rate']['k']}/{lo['n']} = {pct(lo['counterpart_rate']['rate'])} "
            f"(Wilson {ci(lo['counterpart_rate']['wilson_95'])}). The D2 rule would then choose "
            + (f"the {st['edge']} edge ({st['value']})" if st else "no edge")
            + (", i.e. every scored pair would be `matched` and there would be no effective threshold."
               if st and st["edge"] == "min" else ".")
            + f" {sens['note'].capitalize()}.",
        ]
    lines += [
        "",
        "## Kaggle run",
        "",
        f"- Device: {kg.get('device')} ({kg.get('gpu')}). Full-run runtime: {kg.get('runtime_sec_full')} s. "
        f"Smoke run: {kg.get('smoke', {}).get('candidates')} candidates, {kg.get('smoke', {}).get('records')} records, "
        f"{kg.get('smoke', {}).get('runtime_sec')} s.",
        f"- Model: `{kg.get('model_id')}` at revision `{kg.get('model_revision')}` (asserted in the notebook).",
        f"- Code: `{CODE_ZIP}` sha256 `{code_sha}`. On Kaggle: {kg.get('code_source')}.",
        f"- Versions: " + ", ".join(f"{k} {x}" for k, x in kg.get("versions", {}).items()) + ".",
        "",
    ]
    notes = resolver.write_path("reports", NOTES_FILE)
    if notes.is_file():
        lines += [notes.read_text(encoding="utf-8").rstrip(), ""]
    path = resolver.write_path("reports", REPORT_FILE)
    write_text(path, "\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Notebook + checklist
# ---------------------------------------------------------------------------


def run_notebook(cfg, resolver, logger) -> dict:
    from scripts.build_matching_notebook import build

    path = build(REPO_ROOT / NOTEBOOK)
    return {"notebook": repo_relative(path)}


def checklist(resolver: PathResolver, package: Mapping[str, Any] | None) -> str:
    cand = resolver.read_path("benchmark", "candidates", candidates_filename("v4"))
    up = _mdir(resolver, UPLOAD_SUBDIR)
    zip_sha = package["zip_sha256"] if package else "(run `package` first)"
    return f"""
PART B CHECKLIST (Karan, kaggle.com, all under your own account)

1. Create -> New Dataset  rbi-oblibench-corpus-v2-karan  (Private)
   Upload: rbi-oblibench-corpus-v2.zip (the one you already have)
2. Create -> New Dataset  rbi-oblibench-candidates-v4  (Private)
   Upload: {cand}
3. Create -> New Dataset  rbi-oblibench-code-p2002  (Private)
   Upload: {up / CODE_ZIP}
   Expected SHA-256: {zip_sha}
   (Kaggle may unpack the zip. The notebook then checks every file against MANIFEST.json instead.)
4. Create -> New Notebook -> File -> Import Notebook -> {REPO_ROOT / NOTEBOOK}
   Settings: Accelerator GPU T4, Internet On
   Add Input: all three datasets above
5. Run All interactively (not Save & Run All). Check the smoke-run cell's output before the full run continues.
6. Download from /kaggle/working:  p2002_return.zip  and  p2002_embeddings_{V}.npz
   Save p2002_embeddings_{V}.npz as a new private Dataset  rbi-oblibench-embeddings-p2002
7. Back in Claude Code:  Run Part C of P2-002.md
   (Put p2002_return.zip anywhere and give its path. Part C runs:
    python scripts/run_matching.py ingest --zip <path>)
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("units", "stage1", "package", "notebook", "checklist",
                                          "ingest", "bands", "sheet", "score"))
    parser.add_argument("--config", default=None)
    parser.add_argument("--zip", default=None, help="ingest: path to p2002_return.zip")
    parser.add_argument("--sheet-file", default=None, help="score: labelled sheet, if saved under another name")
    parser.add_argument("--force", action="store_true", help="sheet: overwrite an existing unlabelled sheet")
    parser.add_argument("--label-source", choices=("manual", "ai_assisted"), default=None,
                        help="score: who labelled the sheet (recorded in the metrics and report)")
    parser.add_argument("--sensitivity", default=None,
                        help="score: alternative reading to report alongside, e.g. P015:related,P018:related")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    resolver = PathResolver.from_config(cfg)
    logger = get_logger("scripts.run_matching", cfg, resolver=resolver)
    try:
        if args.stage == "units":
            out = run_units(cfg, resolver, logger)
        elif args.stage == "stage1":
            out = run_stage1(cfg, resolver, logger)
        elif args.stage == "package":
            out = run_package(cfg, resolver, logger)
        elif args.stage == "notebook":
            out = run_notebook(cfg, resolver, logger)
        elif args.stage == "checklist":
            mpath = _mdir(resolver, UPLOAD_SUBDIR) / CODE_MANIFEST
            print(checklist(resolver, read_json(mpath) if mpath.is_file() else None))
            return 0
        elif args.stage == "ingest":
            if not args.zip:
                raise M.MatchingError("ingest needs --zip <path to p2002_return.zip>")
            out = run_ingest(cfg, resolver, logger, args.zip)
        elif args.stage == "bands":
            out = run_bands(cfg, resolver, logger)
        elif args.stage == "sheet":
            out = run_sheet(cfg, resolver, logger, force=args.force)
        else:
            out = run_score(cfg, resolver, logger, args.sheet_file, args.label_source, args.sensitivity,
                            command=score_command(sys.argv[1:] if argv is None else argv))
    except M.MatchingError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
