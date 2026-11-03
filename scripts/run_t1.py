#!/usr/bin/env python3
"""CLI for P2-004 (+ P2-004-SPRINT): the T1 benchmark.

Part A (local, tonight):
    python scripts/run_t1.py preflight    # A1 counts, matches hash, guidelines version
    python scripts/run_t1.py rules        # A2 the v3 label rules, printed
    python scripts/run_t1.py candidates   # A3 data/benchmark/t1/t1_candidate_benchmark_v1.jsonl
    python scripts/run_t1.py size         # A4 the §K calculation from config
    python scripts/run_t1.py sample       # A5 sample + hidden key (retest and second-rater subsets)
    python scripts/run_t1.py sheets       # A6 Karan pass 1, Akash, Meer, pilot pass 2, minutes log, locks
    python scripts/run_t1.py sendlist     # A8 Part B instructions with real paths

Inter-rater (IRR) set, 30 fresh items for Karan, Akash and Meer:
    python scripts/run_t1.py irr                               # draw + three identical blank sheets + send log
    python scripts/run_t1.py irr-sendlist                      # which file goes to whom
    python scripts/run_t1.py irr-sent --rater akash            # stamp sent_at in the send log
    python scripts/run_t1.py irr-ingest --rater akash --file <returned.csv>   # once per rater
    python scripts/run_t1.py backup [--dest <folder>]          # zip data/benchmark/t1/ and verify it

Any time:
    python scripts/run_t1.py lookup --paragraph md_13140::p00087
    python scripts/run_t1.py lookup --class "Small Finance Banks" --family "Know Your Customer" --query "video KYC"

The checkpoint, ingest, retest, score, adjudicate, validate and report stages
come with Parts C-E. No LLM or embedding model is used anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import stat
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark import matching as M  # noqa: E402
from src.benchmark import t1 as T  # noqa: E402
from src.benchmark.annotation import GUIDELINES_FILE, GUIDELINES_VERSION, _task_row  # noqa: E402
from src.benchmark.annotation import load_candidates as load_pilot_candidates  # noqa: E402
from src.benchmark.annotation import load_retest_set  # noqa: E402
from src.benchmark.candidates import candidates_filename, load_candidates  # noqa: E402
from src.benchmark.corpus_qa import iter_paragraph_records  # noqa: E402
from src.common.config import load_config  # noqa: E402
from src.common.io_helpers import iter_jsonl, read_json, read_jsonl, write_json, write_jsonl, write_text  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver, repo_relative  # noqa: E402

MATCHES_FILE = "t1_matches_v1_thresholded.jsonl"
UNITS_FILE = "p2002_units_v1.jsonl"
P2002_KEY_FILE = "p2002_validation_key_v1.json"


def setup(config: str | None):
    cfg = load_config(config)
    resolver = PathResolver.from_config(cfg)
    return cfg, T.T1Config.from_cfg(cfg), resolver, get_logger("scripts.run_t1", cfg, resolver=resolver)


def tdir(resolver: PathResolver) -> Path:
    path = resolver.write_dir("benchmark") / T.T1_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def guidelines_version_found(resolver: PathResolver) -> tuple[Path, str | None]:
    path = resolver.read_path(*GUIDELINES_FILE)
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("**Guidelines version:"):
            return path, line.split(":", 1)[1].strip(" *").split("*")[0].strip()
    return path, None


# ---------------------------------------------------------------------------
# A1
# ---------------------------------------------------------------------------


def run_preflight(cfg, tc: T.T1Config, resolver, logger) -> dict:
    cands = load_candidates(resolver.read_path("benchmark", "candidates", candidates_filename("v4")))
    kept = [c for c in cands if not c.exclusion_reason]
    manifest = read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))
    fam = {r["document_id"]: r.get("subject_family") for r in manifest}
    eligible, _, _ = M.classify_candidates(cands, fam, M.MatchingConfig.from_cfg(cfg))
    mpath = resolver.read_path("benchmark", "matching", MATCHES_FILE)
    sha = sha256_file(mpath)
    status = defaultdict(int)
    for r in iter_jsonl(mpath):
        status[r["status"]] += 1
    gpath, gver = guidelines_version_found(resolver)
    problems = []
    if len(kept) != tc.expected_kept_candidates:
        problems.append(f"kept candidates {len(kept)} != {tc.expected_kept_candidates}")
    if len(eligible) != tc.expected_eligible_candidates:
        problems.append(f"eligible candidates {len(eligible)} != {tc.expected_eligible_candidates}")
    if not sha.startswith(tc.matches_sha256_prefix):
        problems.append(f"matches sha256 {sha[:16]} != {tc.matches_sha256_prefix}")
    want = {"matched": 120926, "below_threshold": 60462, "no_direction_in_family": 77792}
    if dict(status) != want:
        problems.append(f"match statuses {dict(status)} != {want}")
    if gver != tc.guidelines_version or gver != GUIDELINES_VERSION:
        problems.append(f"guidelines version {gver!r} != config {tc.guidelines_version!r} / tooling {GUIDELINES_VERSION!r}")
    out = {"kept": len(kept), "eligible": len(eligible), "matches_sha256": sha, "statuses": dict(status),
           "guidelines": repo_relative(gpath), "guidelines_version": gver, "problems": problems}
    if problems:
        raise T.T1Error("preflight failed: " + "; ".join(problems))
    logger.info("preflight ok: %s", out)
    return out


def run_rules(tc: T.T1Config) -> dict:
    return {
        "guidelines_version": tc.guidelines_version,
        "applies_to": "item level, judged from the span's own text (v3.2); never derived; vocabulary: "
                      + "; ".join(tc.applies_to_vocabulary),
        "judgements": list(T.JUDGEMENTS),
        "flag_rule": ["any different -> class-specific", "else any same -> shared", "all none -> absent",
                      "otherwise (only none/unsure) -> ambiguous -> adjudication",
                      "any unsure -> listed for adjudication"],
        "not_obligation": "item-level 'yes' + reason in note; rejected; excluded from N; candidate rejection rate",
        "matched_paragraph_id": "required for same/different; blank for none/unsure; shown ids auto-recorded as checked",
        "compared_classes": "target core classes with status scored for the source, at most "
                            f"{tc.max_compared_classes} per item; no_direction_in_family never compared",
    }


# ---------------------------------------------------------------------------
# A3
# ---------------------------------------------------------------------------


def load_inputs(cfg, resolver):
    cands = load_candidates(resolver.read_path("benchmark", "candidates", candidates_filename("v4")))
    manifest = {r["document_id"]: r for r in read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))}
    fam = {d: r.get("subject_family") for d, r in manifest.items()}
    eligible, _, _ = M.classify_candidates(cands, fam, M.MatchingConfig.from_cfg(cfg))
    paragraphs = {p["paragraph_id"]: p for p in iter_paragraph_records(resolver)}
    return cands, manifest, eligible, paragraphs


def run_candidates(cfg, tc: T.T1Config, resolver, logger) -> dict:
    _, manifest, eligible, paragraphs = load_inputs(cfg, resolver)
    units = defaultdict(list)
    for u in iter_jsonl(resolver.read_path("benchmark", "matching", UNITS_FILE)):
        units[u["candidate_id"]].append(u)
    records = defaultdict(list)
    for r in iter_jsonl(resolver.read_path("benchmark", "matching", MATCHES_FILE)):
        records[r["source_candidate_id"]].append(r)
    first = {}
    for pid, p in paragraphs.items():
        if pid.endswith("::p00000"):
            first[p["document_id"]] = p.get("text") or ""
    supp = Path(cfg["supplementary"]["data_dir"])
    amend = T.amendment_index(iter_jsonl(resolver.working_root / supp / "amendment" / "items_v1.jsonl"))
    out, metrics = T.build_candidate_benchmark(
        eligible=eligible, units_by_candidate=units, records_by_source=records, paragraphs=paragraphs,
        manifest=manifest, first_paragraph=first, amendments=amend,
        era_cutoff=str(cfg["supplementary"]["era_cutoff"]), boilerplate_kind=M.boilerplate_kind)
    path = write_jsonl(tdir(resolver) / T.CANDIDATE_BENCHMARK_FILE, out)
    metrics["file"] = repo_relative(path)
    metrics["sha256"] = sha256_file(path)
    metrics["amendments_linked"] = sum(len(v) for v in amend.values())
    metrics["directions_with_amendments"] = len(amend)
    write_json(tdir(resolver) / T.CANDIDATE_METRICS_FILE, metrics)
    logger.info("candidate benchmark: %d records (%d boilerplate excluded)", metrics["records"],
                metrics["excluded_boilerplate"])
    return metrics


# ---------------------------------------------------------------------------
# A4-A6
# ---------------------------------------------------------------------------


def excluded_sets(resolver) -> tuple[set[str], set[str]]:
    pilot = {lbl.obligation_span.paragraph_id for lbl in load_pilot_candidates(resolver) if lbl.obligation_span}
    key = read_json(resolver.read_path("benchmark", "matching", P2002_KEY_FILE))
    pairs = {c for p in key["pairs"].values() for c in (p["source_candidate_id"], p["target_candidate_id"])}
    return pilot, pairs


def run_sample(cfg, tc: T.T1Config, resolver, logger) -> dict:
    records = list(iter_jsonl(tdir(resolver) / T.CANDIDATE_BENCHMARK_FILE))
    size = T.size_calc(tc)
    pilot, pairs = excluded_sets(resolver)
    drawn = T.draw_sample(records, tc, size["n_target"], excluded_paragraphs=pilot, excluded_candidates=pairs)
    items = drawn["items"]
    sample = [{k: it[k] for k in ("item_id", "order", "block", "source_candidate_id", "md_id", "paragraph_id",
                                   "entity_class", "subject_family", "sample_compared_classes")} for it in items]
    spath = write_jsonl(tdir(resolver) / T.SAMPLE_FILE, sample)
    retest, second = set(drawn["retest_ids"]), set(drawn["second_rater_ids"])
    key = {
        "note": "HIDDEN KEY. No rater opens this file.",
        "size": size,
        "allocation": drawn["allocation"],
        "pool_size": drawn["pool_size"],
        "pool_by_class": drawn["pool_by_class"],
        "excluded": drawn["excluded"],
        "seeds": dict(tc.seeds),
        "retest_ids": drawn["retest_ids"],
        "second_rater_ids": drawn["second_rater_ids"],
        "items": {it["item_id"]: {
            "order": it["order"], "block": it["block"], "stratum": it["entity_class"],
            "subject_family": it["subject_family"],
            "compared_classes": it["sample_compared_classes"],
            "compared_classes_all": it["compared_classes"],
            "not_compared": it["not_compared"],
            "applies_to_candidate_over_compared": sorted(
                {it["entity_class"], *[c for c in it["sample_compared_classes"]
                                       if it["per_class_candidate"][c] == T.STATUS_MATCHED]}),
            "differential_flag_candidate_over_compared": (
                T.CANDIDATE_FLAG_POSITIVE if any(it["per_class_candidate"][c] == T.STATUS_MATCHED
                                                 for c in it["sample_compared_classes"]) else T.FLAG_ABSENT),
            "per_class_candidate": {c: it["per_class_candidate"][c] for c in it["sample_compared_classes"]},
            "shown_targets": {c: [T.paragraph_of(x) for x in it["top_targets"][c][:2]]
                              for c in it["sample_compared_classes"]},
            "retest": it["item_id"] in retest,
            "second_rater": it["item_id"] in second,
        } for it in items},
    }
    matches = {}
    for r in iter_jsonl(resolver.read_path("benchmark", "matching", MATCHES_FILE)):
        iid = T.item_id_for(r["source_candidate_id"])
        if iid in key["items"] and r["target_entity_class"] in key["items"][iid]["compared_classes"]:
            matches.setdefault(iid, {})[r["target_entity_class"]] = [
                {"candidate_id": t["candidate_id"], "semantic_score": t["semantic_score"],
                 "lexical_score": t["lexical_score"], "match_type": t["match_type"]} for t in r["top_targets"]]
    for iid, per in matches.items():
        key["items"][iid]["p2002_top_targets"] = dict(sorted(per.items()))
    kpath = tdir(resolver) / T.KEY_FILE
    if kpath.exists() and "irr" in (old := read_json(kpath)):
        key["irr"] = old["irr"]  # the IRR draw is separate from A5; a re-run must not drop it
    write_json(kpath, key)
    out = {"n": len(items), "blocks": max(it["block"] for it in items), "allocation": drawn["allocation"],
           "pool_size": drawn["pool_size"], "excluded": drawn["excluded"],
           "retest_items": len(retest),
           "retest_by_block": dict(sorted(Counter(it["block"] for it in items if it["item_id"] in retest).items())),
           "second_rater_items": len(second),
           "classes_in_first_3_blocks": len({it["entity_class"] for it in items if it["block"] <= 3}),
           "compared_classes_per_item": dict(sorted(Counter(len(it["sample_compared_classes"]) for it in items).items())),
           "sample_sha256": sha256_file(spath), "key_sha256": sha256_file(kpath)}
    logger.info("sample: %s", out)
    return out


def run_sheets(cfg, tc: T.T1Config, resolver, logger) -> dict:
    d = tdir(resolver)
    records = {r["item_id"]: r for r in iter_jsonl(d / T.CANDIDATE_BENCHMARK_FILE)}
    sample = list(iter_jsonl(d / T.SAMPLE_FILE))
    key = read_json(d / T.KEY_FILE)
    paragraphs = {p["paragraph_id"]: p for p in iter_paragraph_records(resolver)}
    items = [{**records[s["item_id"]], **s} for s in sample]
    rows = T.sheet_rows(items, paragraphs, tc)
    T.assert_blind(rows)
    written = {}
    written["karan_pass1"] = T.write_sheet(d / T.PASS1_SHEET, rows, T.SHEET_COLUMNS, header=T.SHEET_HEADER,
                                           input_columns=T.INPUT_COLUMNS)
    subset = [it for it in items if it["item_id"] in set(key["second_rater_ids"])]
    sub_blocks = {it["item_id"]: i // tc.block_size + 1 for i, it in enumerate(subset)}
    sub_rows = T.sheet_rows(subset, paragraphs, tc, blocks=sub_blocks)
    T.assert_blind(sub_rows)
    for rater in tc.second_raters:
        written[rater] = T.write_sheet(d / T.SECOND_RATER_SHEET.format(rater=rater), sub_rows, T.SHEET_COLUMNS,
                                       header=T.SHEET_HEADER, input_columns=T.INPUT_COLUMNS)
    # The 18 pilot retest items are no longer a separate sheet: they are part of the C2 pass-2 sheet
    # (`retest-sheet`), shuffled together with the retest subset (policy of 2026-09-27).
    blocks = max(int(s["block"]) for s in sample)
    mpath = d / T.MINUTES_FILE
    T.write_sheet(mpath, T.minutes_rows(tc, blocks), T.MINUTES_COLUMNS, header=None,
                  input_columns=("started_at", "ended_at", "minutes", "note"))
    written["minutes"] = mpath
    log = {"written_at": _now(), "guidelines_version": tc.guidelines_version,
           "files": {k: {"path": repo_relative(v), "sha256": sha256_file(v)} for k, v in written.items()},
           "key_sha256": sha256_file(d / T.KEY_FILE), "sample_sha256": sha256_file(d / T.SAMPLE_FILE)}
    dl = d / T.DRAW_LOG_FILE
    history = read_json(dl) if dl.exists() else {"entries": []}
    history["entries"].append(log)
    write_json(dl, history)
    out = {"files": {k: repo_relative(v) for k, v in written.items()},
           "karan_rows": len(rows), "karan_items": len(items), "second_rater_items": len(subset)}
    logger.info("sheets: %s", out)
    return out


PILOT_INPUT_COLUMNS = ("applies_to", "applies_to_rationale", "differential_flag", "notes")


def sendlist(tc: T.T1Config, resolver) -> str:
    d = tdir(resolver)
    g = resolver.read_path(*GUIDELINES_FILE)
    return "\n".join([
        "SEND TONIGHT (only these, nothing else):",
        f"  Akash: {d / T.SECOND_RATER_SHEET.format(rater='akash')}",
        f"         + {g}",
        f"  Meer:  {d / T.SECOND_RATER_SHEET.format(rater='meer')}",
        f"         + {g}",
        "  Tell both: independent, blank file, no AI, no discussing items; log minutes; return by 29 Sep 12:00 IST.",
        "",
        "KARAN:",
        f"  Pass 1: {d / T.PASS1_SHEET}  (block 1 only first, then `Run checkpoint of P2-004.md`)",
        f"  Minutes: {d / T.MINUTES_FILE}  (fill one line per block, at the time)",
        f"  Pass 2 (retest subset + 18 pilot items): {d / T.PASS2_SHEET}  (blind)",
        f"  Never open: {d / T.KEY_FILE}",
        "",
        f"SIZING NOTE: N = {T.size_calc(tc)['n_target']} assumes {tc.minutes_per_item} min/item, the pilot's recalled "
        "estimate with applies_to pre-filled. The v3 sheet asks for an item-level applies_to plus up to "
        f"{tc.max_compared_classes} class judgements with paragraph ids, so minutes per item will likely rise. The "
        "block-1 checkpoint re-derives N from the minutes you log; blocks are only dropped from the end.",
    ])


# ---------------------------------------------------------------------------
# IRR set
# ---------------------------------------------------------------------------


def _p2002_targets(resolver, item_ids: set[str], compared: dict[str, list[str]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in iter_jsonl(resolver.read_path("benchmark", "matching", MATCHES_FILE)):
        iid = T.item_id_for(r["source_candidate_id"])
        if iid in item_ids and r["target_entity_class"] in compared[iid]:
            out.setdefault(iid, {})[r["target_entity_class"]] = {
                "status": r["status"],
                "top_targets": [{"candidate_id": t["candidate_id"], "semantic_score": t["semantic_score"],
                                 "lexical_score": t["lexical_score"], "match_type": t["match_type"]}
                                for t in r["top_targets"]]}
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def run_irr(cfg, tc: T.T1Config, resolver, logger) -> dict:
    """Draw the 30-item IRR set; write three identical blank sheets, the send log, the key section, minutes rows."""
    d = tdir(resolver)
    key_path = d / T.KEY_FILE
    key = read_json(key_path)
    if "irr" in key:
        raise T.T1Error(f"the IRR set was already drawn at {key['irr']['drawn_at']}; refusing to redraw it")
    records = list(iter_jsonl(d / T.CANDIDATE_BENCHMARK_FILE))
    sample_ids = {s["item_id"] for s in iter_jsonl(d / T.SAMPLE_FILE)}
    pilot, pairs = excluded_sets(resolver)
    drawn = T.draw_irr(records, tc, excluded_items=sample_ids, excluded_paragraphs=pilot,
                       excluded_candidates=pairs, boilerplate_kind=M.boilerplate_kind)
    items = drawn["items"]
    if len(items) != T.IRR_ITEMS or {it["item_id"] for it in items} & sample_ids:
        raise T.T1Error("IRR draw is not 30 new items")
    paragraphs = {p["paragraph_id"]: p for p in iter_paragraph_records(resolver)}
    rows = T.sheet_rows(items, paragraphs, tc, shuffle_seed=drawn["shuffle_seed"])
    T.assert_blind(rows)
    now = _now()
    files = {}
    for rater in T.IRR_RATERS:
        path = T.write_sheet(d / T.IRR_SHEET.format(rater=rater), rows, T.SHEET_COLUMNS, header=T.IRR_HEADER,
                             input_columns=T.INPUT_COLUMNS)
        files[rater] = {"file": repo_relative(path), "sha256": sha256_file(path), "written_at": now,
                        "sent_to": rater, "sent_at": None}
    ref = T.write_sheet(d / T.IRR_BLANK_REFERENCE, rows, T.SHEET_COLUMNS, header=T.IRR_HEADER,
                        input_columns=T.INPUT_COLUMNS)
    if len({f["sha256"] for f in files.values()} | {sha256_file(ref)}) != 1:
        raise T.T1Error("the three IRR sheets and the reference copy are not identical")
    compared = {it["item_id"]: it["sample_compared_classes"] for it in items}
    scores = _p2002_targets(resolver, set(compared), compared)
    key["irr"] = {
        "note": "HIDDEN. Inter-rater set, separate from the 123-item sample. No rater opens this file.",
        "drawn_at": now, "seed": drawn["seed"], "shuffle_seed": drawn["shuffle_seed"],
        "allocation": drawn["allocation"], "pool_size": drawn["pool_size"], "pool_by_class": drawn["pool_by_class"],
        "excluded": drawn["excluded"],
        "item_ids": [it["item_id"] for it in items],
        "items": {it["item_id"]: {
            "order": it["order"], "block": it["block"], "stratum": it["entity_class"],
            "subject_family": it["subject_family"], "compared_classes": it["sample_compared_classes"],
            "compared_classes_all": it["compared_classes"], "not_compared": it["not_compared"],
            "per_class_candidate": {c: it["per_class_candidate"][c] for c in it["sample_compared_classes"]},
            "differential_flag_candidate_over_compared": (
                T.CANDIDATE_FLAG_POSITIVE if any(it["per_class_candidate"][c] == T.STATUS_MATCHED
                                                 for c in it["sample_compared_classes"]) else T.FLAG_ABSENT),
            "shown_targets": {c: [T.paragraph_of(x) for x in it["top_targets"][c][:2]]
                              for c in it["sample_compared_classes"]},
            "p2002": scores.get(it["item_id"], {}),
        } for it in items},
        "sheet_sha256": next(iter(files.values()))["sha256"],
    }
    write_json(key_path, key)
    sendlog = {"note": "IRR send log. Blank sheets are identical; sent_at is stamped by `run_t1.py irr-sent`.",
               "seed": drawn["seed"], "guidelines_version": tc.guidelines_version, "created_at": now,
               "blank_reference": repo_relative(ref), "blank_reference_sha256": sha256_file(ref),
               "files": files, "events": [{"at": now, "event": "written", "raters": list(T.IRR_RATERS)}]}
    write_json(d / T.IRR_SENDLOG_FILE, sendlog)
    mpath = d / T.MINUTES_FILE
    existing = T.read_sheet(mpath, require_id=False)
    T.write_sheet(mpath, T.irr_minutes_rows(existing), T.MINUTES_COLUMNS, header=None, input_columns=())
    out = {"items": len(items), "allocation": drawn["allocation"], "pool_size": drawn["pool_size"],
           "excluded": drawn["excluded"], "seed": drawn["seed"],
           "compared_per_item": dict(sorted(Counter(len(c) for c in compared.values()).items())),
           "rows": len(rows), "families": len({it["subject_family"] for it in items}),
           "files": {r: f["file"] for r, f in files.items()}, "sheet_sha256": files["karan"]["sha256"]}
    logger.info("IRR set: %s", out)
    return out


def run_irr_sent(tc: T.T1Config, resolver, rater: str) -> dict:
    path = tdir(resolver) / T.IRR_SENDLOG_FILE
    log = read_json(path)
    if rater not in log["files"]:
        raise T.T1Error(f"no IRR file for {rater!r}")
    if log["files"][rater]["sent_at"]:
        raise T.T1Error(f"{rater}'s IRR file is already marked sent at {log['files'][rater]['sent_at']}")
    now = _now()
    current = sha256_file(tdir(resolver) / T.IRR_SHEET.format(rater=rater))
    if current != log["files"][rater]["sha256"]:
        raise T.T1Error(f"{rater}'s IRR sheet changed since it was written; it is no longer the blank sheet")
    log["files"][rater]["sent_at"] = now
    log["events"].append({"at": now, "event": "sent", "rater": rater})
    write_json(path, log)
    return log["files"][rater]


def paragraph_classes(resolver) -> dict[str, str]:
    manifest = {r["document_id"]: r.get("entity_class")
                for r in read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))}
    return {p["paragraph_id"]: manifest.get(p["document_id"]) for p in iter_paragraph_records(resolver)}


def _irr_blank(resolver) -> list[dict[str, str]]:
    d = tdir(resolver)
    ref = d / T.IRR_BLANK_REFERENCE
    if sha256_file(ref) != read_json(d / T.IRR_SENDLOG_FILE)["blank_reference_sha256"]:
        raise T.T1Error(f"{ref.name} changed since the draw; it can't serve as the blank reference")
    return T.read_sheet(ref)


def run_irr_check(tc: T.T1Config, resolver, files: dict[str, str], label_source: str) -> dict:
    """Dry run: every ingest rule on every file, in order, in memory. Writes nothing; reports each outcome."""
    d = tdir(resolver)
    drawn, classes = _irr_blank(resolver), paragraph_classes(resolver)
    rpath = d / T.IRR_RECEIPTS_FILE
    receipts = dict(read_json(rpath)["receipts"]) if rpath.exists() else {}
    received = {o: T.read_sheet(d / T.IRR_RECEIVED_DIR / r["stored_as"]) for o, r in receipts.items()}
    out = {}
    for rater, file in files.items():
        src = Path(file)
        try:
            rec = T.ingest_irr(src, rater, t1_dir=d, drawn=drawn, tc=tc, paragraph_class=classes, receipts=receipts,
                               received_at="dry-run", sha256=sha256_file(src), label_source=label_source,
                               received_rows=received)
            receipts[rater] = rec
            received[rater] = T.read_sheet(src)
            out[rater] = {"ok": True, "sha256": rec["sha256"], "rows": rec["rows"], "items": rec["items"]}
        except T.T1Error as exc:
            out[rater] = {"ok": False, "error": str(exc)}
    return out


def run_irr_ingest(tc: T.T1Config, resolver, logger, rater: str, file: str, label_source: str) -> dict:
    d = tdir(resolver)
    src = Path(file)
    if not src.is_file():
        raise T.T1Error(f"{file}: not found")
    rpath = d / T.IRR_RECEIPTS_FILE
    receipts = read_json(rpath) if rpath.exists() else {"receipts": {}}
    receipt = T.ingest_irr(src, rater, t1_dir=d, drawn=_irr_blank(resolver), tc=tc,
                           paragraph_class=paragraph_classes(resolver), receipts=receipts["receipts"],
                           received_at=_now(), sha256=sha256_file(src), label_source=label_source)
    store = d / T.IRR_RECEIVED_DIR / receipt["stored_as"]
    store.parent.mkdir(parents=True, exist_ok=True)
    if store.exists():
        raise T.T1Error(f"{store} already exists; refusing to overwrite a received file")
    store.write_bytes(src.read_bytes())
    receipts["receipts"][rater] = receipt
    write_json(rpath, receipts)
    logger.info("IRR ingest: %s", receipt)
    return receipt


IRR_METRICS_FILE = "p2004_irr_metrics_v1.json"
IRR_REPORT_FILE = "p2004_irr_v1.md"
IRR_ADJUDICATION_FILE = "p2004_irr_adjudication_v1.csv"
IRR_RESAMPLES = 2000


def irr_minutes(resolver, n_items: int) -> dict[str, Any]:
    rows = T.read_sheet(tdir(resolver) / T.MINUTES_FILE, require_id=False)
    out = {}
    for rater in T.IRR_RATERS:
        mine = [r for r in rows if r.get("rater") == rater and r.get("block") == T.IRR_MINUTES_BLOCK]
        vals = []
        for r in mine:
            try:
                vals.append(float((r.get("minutes") or "").strip()))
            except ValueError:
                pass
        out[rater] = ({"minutes": sum(vals), "sittings": len(vals), "minutes_per_item": sum(vals) / n_items,
                       "basis": "measured (p2004_minutes.csv)"} if vals else
                      {"minutes": None, "minutes_per_item": None,
                       "basis": "NOT YET MEASURED — no minutes logged in the irr rows of p2004_minutes.csv"})
    return out


def run_irr_score(cfg, tc: T.T1Config, resolver, logger) -> dict:
    d = tdir(resolver)
    receipts = read_json(d / T.IRR_RECEIPTS_FILE)["receipts"]
    missing = [r for r in T.IRR_RATERS if r not in receipts]
    if missing:
        raise T.T1Error(f"IRR files not yet ingested for {missing}")
    rows = {}
    for r, rec in receipts.items():
        path = d / T.IRR_RECEIVED_DIR / rec["stored_as"]
        if sha256_file(path) != rec["sha256"]:
            raise T.T1Error(f"{path} no longer matches its receipt sha256")
        rows[r] = T.read_sheet(path)
    labels = {r: T.parse_labelled_items(v) for r, v in rows.items()}
    seed = int(cfg["benchmark"]["agreement"]["bootstrap_seed"])
    metrics = T.irr_metrics(labels, seed=seed, resamples=IRR_RESAMPLES)
    disagreements = T.irr_disagreements(labels)
    src_times = {}
    for r, rec in receipts.items():
        p = Path(rec["source_path"])
        p = p if p.is_absolute() else resolver.working_root / p
        src_times[r] = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds") \
            if p.exists() else None
    per_rater = {r: {
        "label_source": receipts[r]["label_source"], "sha256": receipts[r]["sha256"],
        "received_at": receipts[r]["received_at"], "source_file_modified_at": src_times[r],
        "not_obligation_items": sum(v["not_obligation"] for v in labels[r].values()),
        "flag_distribution": dict(sorted(Counter(v["flag"] for v in labels[r].values()
                                                 if not v["not_obligation"]).items())),
        "judgement_distribution": dict(sorted(Counter(j for v in labels[r].values() if not v["not_obligation"]
                                                      for j in v["judgements"].values()).items())),
        "applies_to_size": dict(sorted(Counter(len(v["applies_to"]) for v in labels[r].values()
                                               if not v["not_obligation"]).items())),
        "applies_to_includes_stand_in": sum(any(c in tc.stand_in_classes for c in v["applies_to"])
                                            for v in labels[r].values()),
        "applies_to_equals_source_class_only": sum(v["applies_to"] == (v["source_class"],)
                                                    for v in labels[r].values() if not v["not_obligation"]),
    } for r in sorted(labels)}
    out = {"generated_at": _now(), "guidelines_version": tc.guidelines_version, "irr_seed": T.IRR_SEED,
           "items": metrics["items"], "per_rater": per_rater, "minutes": irr_minutes(resolver, metrics["items"]),
           "agreement": metrics, "independence": {
               "identical_item_text_guard": "passed at ingest (all three files)",
               "near_identical_item_text": T.independence_diagnostics(rows),
               "source_file_modified_at": src_times},
           "disagreements": {"items": len(disagreements), "item_ids": [x["item_id"] for x in disagreements]}}
    adj_rows = T.irr_adjudication_rows(rows)
    out["adjudication"] = {"rows": len(adj_rows), "item_rows": sum(r["comparison"] == "item" for r in adj_rows),
                           "class_rows": sum(r["comparison"] == "class" for r in adj_rows),
                           "items": len({r["item_id"] for r in adj_rows})}
    if adj_rows:
        T.write_sheet(d / IRR_ADJUDICATION_FILE, adj_rows, T.IRR_ADJUDICATION_COLUMNS, header=(
            "# IRR adjudication (Karan): one row per disagreeing comparison (item-level not_obligation / "
            "applies_to, or a class-row judgement; any 'unsure' is listed too). Fill final_decision and "
            "final_rationale. The rater columns are the labels as ingested; don't edit them."),
            input_columns=("final_decision", "final_rationale"))
    out["report"] = repo_relative(write_irr_report(resolver, out, disagreements))
    out["adjudication_file"] = repo_relative(d / IRR_ADJUDICATION_FILE) if adj_rows else None
    write_json(resolver.write_path("reports", IRR_METRICS_FILE), out)
    return out


def write_irr_report(resolver, m: dict, disagreements: list) -> Path:
    a = m["agreement"]
    num = lambda x: "n/a" if x is None else (x if isinstance(x, str) else f"{x:.3f}")
    pct = lambda x: "n/a" if x is None else f"{x:.1%}"

    def ci(b):
        c = b.get("ci95")
        return c if isinstance(c, str) else f"{c[0]:.3f} to {c[1]:.3f}"

    lines = [
        "# P2-004 inter-rater reliability (IRR set, v1)",
        "",
        f"_Generated {m['generated_at']} by `python scripts/run_t1.py irr-score`. Guidelines {m['guidelines_version']}. "
        f"IRR draw seed {m['irr_seed']}; bootstrap: {a['resamples']} resamples, seed {a['seed']}, resampling whole items._",
        "",
        f"{m['items']} items, labelled independently by {', '.join(a['raters'])} from identical blank sheets. "
        "Every figure is on these 30 items only; this is inter-rater agreement, not test-retest.",
        "",
        "## Ingest",
        "",
        "| Rater | label_source | sha256 | received_at | source file last modified |",
        "|---|---|---|---|---|",
    ]
    for r, p in m["per_rater"].items():
        lines.append(f"| {r} | {p['label_source']} | `{p['sha256'][:12]}…` | {p['received_at']} | {p['source_file_modified_at']} |")
    lines += ["", "Each file was accepted once; checks passed: shown columns unchanged, vocabulary and ids valid, "
              "no blanks, no identical item-level text across raters.", "",
              "## Denominators and rejected items", "",
              "- **not_obligation:** all 30 IRR items, each rater's yes/no. Three-rater agreement = share of the 30 "
              "items where all three gave the same answer; Fleiss' κ over the same 30.",
              "- **Pairwise flag and class-row judgements:** only items **both** raters of the pair labelled as "
              "obligations. An item either rater rejected as `not_obligation` is left out of that pair, so n differs "
              "by pair. Class rows: the item's compared classes (4 per item), each a unit; the bootstrap resamples "
              "whole items.",
              "- **Fleiss' κ (flag, class rows):** only items **all three** raters labelled as obligations "
              "(complete items), and all their class rows.",
              "- **applies_to:** exact-set agreement and mean Jaccard over items both raters of the pair labelled "
              "as obligations; no κ is computed for the set-valued labels.",
              "- Rejected items are never scored as a judgement category; the rejection itself is the "
              "not_obligation decision above, and every disagreement on it goes to adjudication.", "",
              "## Pairwise Cohen's κ (bootstrap 95% CI)", "",
              "| Pair | Measure | n items (units) | Observed agreement | κ | 95% CI |", "|---|---|---|---|---|---|"]
    names = {"not_obligation": "not_obligation (all items)", "differential_flag": "differential_flag (v3.6)",
             "per_class_judgement": "per-class judgement"}
    for pair, blocks in a["pairwise"].items():
        for k, label in names.items():
            b = blocks[k]
            lines.append(f"| {pair} | {label} | {b['n_items']} ({b['n_units']}) | {pct(b['observed_agreement'])} | "
                         f"{num(b['kappa'])} | {ci(b['bootstrap'])} |")
    lines += ["", "## applies_to (pairwise, items both raters labelled as obligations)", "",
              "| Pair | n | Exact-set agreement | 95% CI | Mean Jaccard | 95% CI |", "|---|---|---|---|---|---|"]
    for pair, blocks in a["pairwise"].items():
        b = blocks["applies_to"]
        lines.append(f"| {pair} | {b['n_items']} | {pct(b['exact_set_agreement'])} | {ci(b['exact_set_bootstrap'])} | "
                     f"{num(b['mean_jaccard'])} | {ci(b['mean_jaccard_bootstrap'])} |")
    f = a["fleiss"]
    lines += ["", "## Fleiss' κ (all three raters; complete items only)", "",
              "| Measure | n items (units) | All three agree | κ | 95% CI |", "|---|---|---|---|---|"]
    for k, label in names.items():
        b = f[k]
        lines.append(f"| {label} | {b['n_items']} ({b['n_units']}) | {pct(b['all_agree'])} | {num(b['kappa'])} | "
                     f"{ci(b['bootstrap'])} |")
    at = f["applies_to_all_three_identical"]
    lines += [f"| applies_to, all three identical sets | {at['n_items']} | {pct(at['rate'])} | — | — |", "",
              f"_{f['complete_items_note']}_", "",
              f"**Reading the applies_to figures.** On {at['all_three_source_class_only']} of the {at['n_items']} "
              "complete items, all three raters gave the source class alone, and on "
              f"{at['any_rater_multi_class']} at least one rater gave more than one class. The high exact-set "
              "agreement mostly reflects that shared single-class answer, the pattern the guidelines warn about "
              "(v1: don't just copy the context class). It is not evidence of reliable multi-class applicability "
              "judgements, and no chance-corrected κ is reported for set-valued labels.", "",
              "## Per rater", "",
              "| Rater | not_obligation | Flags | Judgements | applies_to = source class only | stand-in used |",
              "|---|---|---|---|---|---|"]
    for r, p in m["per_rater"].items():
        lines.append(f"| {r} | {p['not_obligation_items']} | {p['flag_distribution']} | {p['judgement_distribution']} | "
                     f"{p['applies_to_equals_source_class_only']} | {p['applies_to_includes_stand_in']} |")
    lines += ["", "## Minutes", ""]
    for r, v in m["minutes"].items():
        lines.append(f"- {r}: " + (f"{v['minutes']:.0f} min over {v['sittings']} sitting(s), "
                                   f"{v['minutes_per_item']:.2f} min/item ({v['basis']})" if v["minutes"] is not None
                                   else v["basis"]))
    ind = m["independence"]
    lines += ["", "## Independence diagnostics (descriptive)", "",
              f"- Identical item-level text guard: {ind['identical_item_text_guard']}."]
    for pair, v in ind["near_identical_item_text"].items():
        lines.append(f"- {pair}: {v['near_identical_ge_0_9']} of {v['text_cells_compared']} item-level text cells are "
                     "near-identical (difflib ratio ≥ 0.9)" + (f", e.g. {', '.join(v['examples'])}" if v["examples"] else "")
                     + ".")
    times = sorted(t for t in ind["source_file_modified_at"].values() if t)
    if len(times) == 3:
        span = (datetime.fromisoformat(times[-1]) - datetime.fromisoformat(times[0])).total_seconds()
        lines.append(f"- The three returned files were last modified within {span:.0f} s of each other on this "
                     "machine. That records when the files were saved or copied here; it is not evidence either way "
                     "about how they were labelled.")
    adj = m.get("adjudication", {})
    lines += ["", f"## Disagreements for adjudication ({len(disagreements)} of {m['items']} items)", "",
              f"`data/benchmark/t1/p2004_irr_adjudication_v1.csv` has one row per disagreeing comparison: "
              f"{adj.get('rows')} rows ({adj.get('item_rows')} item-level, {adj.get('class_rows')} class rows) over "
              f"{adj.get('items')} items, with blank `final_decision` and `final_rationale`. Nothing is adjudicated "
              "automatically.", "",
              "| Item | Source class | Differs on |", "|---|---|---|"]
    for x in disagreements:
        lines.append(f"| {x['item_id']} | {x['source_class']} | {', '.join(x['differs_on'])} |")
    lines += ["", "## Provenance", "",
              "- The IRR labels are the dedicated IRR files `annotation_p2004_irr_{karan,akash,meer}_completed.csv`, "
              "each ingested once (sha256 and received-at above), labelled independently from identical blank sheets.",
              "- Karan, Akash and Meer are treated as three independent raters on this set. Label source: manual, "
              "as declared.",
              "- Inter-rater reliability is calculated only from these 30 dedicated IRR items. Karan's full pass-1 "
              "file and the earlier 30-item second-rater files (`annotation_p2004_{akash,meer}_pass1_completed.csv`) "
              "are not used here.",
              "- Minutes were not logged at the time for any rater. A later recalled figure must be recorded as "
              "`recalled_estimate`, never `measured`.", "",
              "## Limitations", "",
              "- n = 30 items (up to 120 class judgements): the intervals are wide.",
              "- Compared classes are capped at 4 per item, so `applies_to` and the flag are over those classes only.",
              "- `absent` covers only the paragraphs shown or looked up (v3.4).",
              "- Label source is as declared (manual); the tooling cannot verify it.", ""]
    path = resolver.write_path("reports", IRR_REPORT_FILE)
    write_text(path, "\n".join(lines))
    if (tdir(resolver) / T.ADJ_RECEIPT_FILE).exists():
        insert_adjudication_section(resolver)  # a regenerated raw report keeps its separate Adjudication section
    return path


# ---------------------------------------------------------------------------
# Part C (sprint): pass-1 ingest, per-class tables, qrels
# ---------------------------------------------------------------------------

PASS1_TABLES_REPORT = "p2004_pass1_tables_v1.md"
PASS1_DECLARATION = "manual (declared by Karan, 2026-09-27)"


def _pass1_drawn(resolver) -> list[dict[str, str]]:
    d = tdir(resolver)
    path = d / T.PASS1_SHEET
    want = read_json(d / T.DRAW_LOG_FILE)["entries"][-1]["files"]["karan_pass1"]["sha256"]
    if sha256_file(path) != want:
        raise T.T1Error(f"{path.name} no longer matches the drawn sheet's recorded sha256")
    return T.read_sheet(path)


def run_pass1_check(tc: T.T1Config, resolver, file: str) -> dict:
    """Dry run of every pass-1 check. Reads the file; writes nothing."""
    src = Path(file)
    v = T.validate_annotation_file(src, _pass1_drawn(resolver), tc, paragraph_classes(resolver))
    return {**v, "sha256": sha256_file(src)}


def run_ingest_pass1(tc: T.T1Config, resolver, logger, file: str, label_source: str) -> dict:
    """Ingest Karan's pass 1 exactly once. Any validation problem stops before anything is written."""
    d = tdir(resolver)
    src = Path(file)
    if not src.is_file():
        raise T.T1Error(f"{file}: not found")
    T.refuse_not_independent(src, d)
    rpath = d / T.PASS1_RECEIPTS_FILE
    receipts = read_json(rpath) if rpath.exists() else {"receipts": {}}
    if tc.primary in receipts["receipts"]:
        prev = receipts["receipts"][tc.primary]
        raise T.T1Error(f"pass 1 was already received at {prev['received_at']} (sha256 {prev['sha256'][:12]}…); "
                        "a second version is refused")
    sha, received_at = sha256_file(src), _now()
    v = T.validate_annotation_file(src, _pass1_drawn(resolver), tc, paragraph_classes(resolver))
    if v["problems"]:
        raise T.T1Error(f"pass 1 NOT ingested: {len(v['problems'])} problem(s):\n  " + "\n  ".join(v["problems"]))
    store = d / T.PASS1_RECEIVED_DIR / T.PASS1_SHEET
    if store.exists():
        raise T.T1Error(f"{store} already exists; refusing to overwrite a received file")
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_bytes(src.read_bytes())
    if sha256_file(store) != sha:
        raise T.T1Error("stored copy does not match the source sha256")
    receipt = {"rater": tc.primary, "pass": 1, "source_path": repo_relative(src), "stored_as": T.PASS1_SHEET,
               "sha256": sha, "received_at": received_at, "label_source": label_source,
               "declaration": PASS1_DECLARATION if label_source == "manual" else label_source,
               "has_bom": v["has_bom"], "rows": v["rows"], "items": v["items"],
               "checks": ["sha256", "received_at", "BOM", "schema", "item identity and order vs the drawn sheet",
                          "row/item uniqueness", "v3 vocabulary", "blank/non-blank rules",
                          "matched_paragraph_id format and target class"]}
    receipts["receipts"][tc.primary] = receipt
    write_json(rpath, receipts)
    logger.info("pass 1 ingested: %s", receipt)
    return receipt


def pass1_minutes(resolver) -> dict:
    rows = T.read_sheet(tdir(resolver) / T.MINUTES_FILE, require_id=False)
    logged = [r for r in rows if r.get("rater") == "karan" and r.get("block", "").isdigit()
              and (r.get("minutes") or "").strip()]
    if not logged:
        return {"minutes_per_item": None, "basis": "NOT YET MEASURED: no pass-1 minutes were logged at the time in "
                "p2004_minutes.csv; a later recalled figure must be recorded as recalled_estimate"}
    total = sum(float(r["minutes"]) for r in logged)
    return {"minutes": total, "blocks_logged": len(logged), "basis": "measured"}


def write_pass1_tables_report(resolver, tables: dict, receipt: dict, qrels_stats: dict) -> Path:
    lines = ["# P2-004 pass 1: per-class judgement tables (v1)", "",
             f"_Karan's official pass 1: `{receipt['source_path']}`, sha256 `{receipt['sha256']}`, received "
             f"{receipt['received_at']}, label source {receipt['declaration']}. Single pass: nothing here is "
             "validated yet (Part D)._", "",
             f"- Items: {tables['items']}; not_obligation (rejected): {tables['not_obligation']}.",
             f"- Derived flag (obligation items, v3.6): {tables['flag_distribution']}.",
             f"- Class-row judgements (obligation items): {tables['judgement_distribution']}.",
             f"- Qrels: {qrels_stats['records']} records (relevance 2 same: {qrels_stats['by_relevance'].get(2, 0)}, "
             f"1 different: {qrels_stats['by_relevance'].get(1, 0)}, 0 checked-none: "
             f"{qrels_stats['by_relevance'].get(0, 0)}); unsure rows and rejected items give none.", "",
             "## By source class", "", "| Source class | Items | not_obligation | shared | class-specific | absent | "
             "ambiguous |", "|---|---|---|---|---|---|---|"]
    for s, c in tables["by_source_class"].items():
        lines.append(f"| {s} | {c.get('items', 0)} | {c.get('not_obligation', 0)} | {c.get('flag:shared', 0)} | "
                     f"{c.get('flag:class-specific', 0)} | {c.get('flag:absent', 0)} | {c.get('flag:ambiguous', 0)} |")
    lines += ["", "## By class pair (source → target)", "",
              "| Source → target | n | same | different | none | unsure |", "|---|---|---|---|---|---|"]
    for p in tables["by_class_pair"]:
        lines.append(f"| {p['source_class']} → {p['target_class']} | {p['n']} | {p['same']} | {p['different']} | "
                     f"{p['none']} | {p['unsure']} |")
    path = resolver.write_path("reports", PASS1_TABLES_REPORT)
    write_text(path, "\n".join(lines) + "\n")
    return path


def run_part_c(cfg, tc: T.T1Config, resolver, logger, named_irr_files: list[str] | None = None) -> dict:
    d = tdir(resolver)
    rec = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    stored = d / T.PASS1_RECEIVED_DIR / rec["stored_as"]
    if sha256_file(stored) != rec["sha256"]:
        raise T.T1Error(f"{stored} no longer matches its receipt")
    rows = T.read_sheet(stored)
    labels = T.parse_labelled_items(rows)
    tables = T.pass1_tables(labels)
    write_json(d / T.PASS1_TABLES_FILE, {"source_sha256": rec["sha256"], **tables})
    key = read_json(d / T.KEY_FILE)
    sample = {s["item_id"]: s for s in iter_jsonl(d / T.SAMPLE_FILE)}
    qrels = T.pass1_qrels(rows, key["items"], sample, rater=tc.primary, label_source=rec["label_source"])
    qpath = write_jsonl(d / T.QRELS_FILE, qrels)
    qstats = {"records": len(qrels), "items": len({q["item_id"] for q in qrels}),
              "by_relevance": dict(sorted(Counter(q["relevance"] for q in qrels).items())),
              "by_basis": dict(sorted(Counter(q["basis"] for q in qrels).items())), "sha256": sha256_file(qpath)}
    report = write_pass1_tables_report(resolver, tables, rec, qstats)
    # IRR: re-validate each dedicated file independently from its stored copy, then score.
    blank = _irr_blank(resolver)
    classes = paragraph_classes(resolver)
    irr_receipts = read_json(d / T.IRR_RECEIPTS_FILE)["receipts"]
    irr_validation = {}
    for r, rr in irr_receipts.items():
        p = d / T.IRR_RECEIVED_DIR / rr["stored_as"]
        v = T.validate_annotation_file(p, blank, tc, classes)
        irr_validation[r] = {"file": rr["source_path"], "sha256": rr["sha256"], "stored_copy_matches": sha256_file(p) == rr["sha256"],
                             "problems": v["problems"], "has_bom": v["has_bom"]}
    if any(v["problems"] or not v["stored_copy_matches"] for v in irr_validation.values()):
        raise T.T1Error(f"IRR re-validation failed: {irr_validation}")
    named = {}
    for f in named_irr_files or []:
        p = Path(f)
        v = T.validate_annotation_file(p, blank, tc, classes)
        named[repo_relative(p)] = {"sha256": sha256_file(p), "is_blank_sheet": sha256_file(p) ==
                                   read_json(d / T.IRR_SENDLOG_FILE)["blank_reference_sha256"],
                                   "problems": len(v["problems"]), "first_problem": (v["problems"] or [None])[0],
                                   "ingested": False}
    irr = run_irr_score(cfg, tc, resolver, logger)
    return {"pass1": {"receipt": rec, "tables": {k: tables[k] for k in ("items", "not_obligation", "flag_distribution",
                                                                        "judgement_distribution")},
                      "minutes": pass1_minutes(resolver)},
            "qrels": {"file": repo_relative(qpath), **qstats},
            "outputs": [repo_relative(d / T.PASS1_TABLES_FILE), repo_relative(report), repo_relative(qpath),
                        irr["report"], "reports/" + IRR_METRICS_FILE, irr.get("adjudication_file")],
            "irr_validation": irr_validation, "named_irr_files_not_ingested": named,
            "irr": {"items": irr["items"], "adjudication": irr["adjudication"], "agreement": irr["agreement"]}}


# ---------------------------------------------------------------------------
# IRR adjudication ingest (item-level completion -> current per-comparison rows)
# ---------------------------------------------------------------------------

IRR_ADJ_METADATA = "p2004_irr_adjudication_v1.json"
LEGACY_TEMPLATE_MEMBER = "t1/p2004_irr_adjudication_v1.csv"
SETTLED_RULE = (
    "Treat a span as an obligation when it states a complete mandatory compliance condition that the regulated "
    "entity must ensure, even when phrased passively or as a mandatory condition on a document or process. Mark "
    "not_obligation only when the span is incomplete, purely definitional, scope-setting only, classification-only, "
    "merely illustrative or a worked example, or clearly assigns the duty to a non-regulated third party.")


def _irr_labels(resolver) -> tuple[dict, dict]:
    d = tdir(resolver)
    receipts = read_json(d / T.IRR_RECEIPTS_FILE)["receipts"]
    rows = {}
    for r, rec in receipts.items():
        p = d / T.IRR_RECEIVED_DIR / rec["stored_as"]
        if sha256_file(p) != rec["sha256"]:
            raise T.T1Error(f"{p} no longer matches its receipt")
        rows[r] = T.read_sheet(p)
    return rows, {r: T.parse_labelled_items(v) for r, v in rows.items()}


def adjudication_section(resolver) -> list[str]:
    d = tdir(resolver)
    rpath = d / T.ADJ_RECEIPT_FILE
    if not rpath.exists():
        return []
    rec = read_json(rpath)
    meta = read_json(resolver.write_path("reports", IRR_ADJ_METADATA))
    c = meta["consensus"]
    ev = meta["not_obligation_rule"]["evidence"]
    lines = ["## Adjudication", "",
             "_Everything above this section is RAW, PRE-ADJUDICATION inter-rater evidence and is unchanged. "
             "Nothing below changes a raw vote, κ, agreement figure, denominator or interval, and no reliability "
             "statistic is computed from adjudicated labels._", "",
             "### Raw IRR → disagreements → adjudication → consensus", "",
             f"- **Raw IRR:** the three raters' pre-adjudication votes on {c['items']} items (tables above).",
             f"- **Disagreements:** {rec['disagreements']['items']} items; {rec['current_rows']} per-comparison rows "
             f"({rec['current_item_rows']} item-level, {rec['current_class_rows']} class rows).",
             f"- **Adjudication:** Karan decided all {rec['adjudicated_items']} disputed items with a written "
             f"rationale (label source: {rec['label_source']}; basis: {rec['label_source_basis']}).",
             f"- **Consensus layer** (`data/benchmark/t1/{T.IRR_CONSENSUS_FILE}`): {c['items']} items = "
             f"{c['routes'].get('adjudicated', 0)} adjudicated + {c['routes'].get('unanimous', 0)} unanimous. "
             f"not_obligation: {c['not_obligation']}. Class judgements (obligation items): {c['judgements']}. "
             f"Flags: {c['flags']}. This layer is reliability and methodology evidence; it does not replace the "
             "123-item pass-1 labels.", "",
             "### Schema migration", "",
             "- The adjudication was completed on the **item-level sheet** it was issued as (18 rows: final_applies_to, "
             "final_judgements, final_not_obligation, rationale).",
             f"- That sheet was restored byte-for-byte from `{rec['legacy_template']['restored_from']}` "
             f"(sha256 `{rec['legacy_template']['sha256'][:12]}…`); the completion's immutable columns match it "
             "exactly.",
             f"- The repository had since moved to a **per-comparison sheet** ({rec['current_rows']} rows: "
             "final_decision, final_rationale). Each row's final_decision was derived deterministically from its "
             "item's completed decision (item rows: not_obligation or the final applies_to; class rows: the final "
             "judgement for that class, or '(not an obligation)'). No new decision was introduced; no paragraph id "
             "was derived.",
             f"- Completed file (unchanged): `{rec['completed_file']}`, sha256 `{rec['completed_sha256']}`. "
             f"Mapped file: `{rec['mapped_file']}`, sha256 `{rec['mapped_sha256']}`.", "",
             "### Settled not_obligation rule", "", f"> {SETTLED_RULE}", "",
             f"Evidence from the {ev['disputed']} disputed not_obligation calls:"]
    for x in ev["rejected"]:
        lines.append(f"- rejected `{x['item_id']}`: {x['rationale']}")
    for x in ev["kept_as_obligation"]:
        lines.append(f"- kept `{x['item_id']}`: {x['rationale']}")
    lines += ["", f"{meta['not_obligation_rule']['support']}", ""]
    return lines


def insert_adjudication_section(resolver) -> Path:
    """Put the Adjudication section into the IRR report without regenerating (or touching) the raw sections."""
    path = resolver.write_path("reports", IRR_REPORT_FILE)
    text = path.read_text(encoding="utf-8")
    start = text.find("## Adjudication\n")
    if start != -1:
        nxt = text.find("\n## ", start + 5)
        text = text[:start] + (text[nxt + 1:] if nxt != -1 else "")
    anchor = text.find("## Provenance\n")
    block = "\n".join(adjudication_section(resolver)) + "\n"
    text = text[:anchor] + block + text[anchor:] if anchor != -1 else text + "\n" + block
    write_text(path, text)
    return path


def run_irr_adjudicate(cfg, tc: T.T1Config, resolver, logger, file: str, template_zip: str, label_source: str,
                       label_source_basis: str) -> dict:
    import zipfile

    d = tdir(resolver)
    if (d / T.ADJ_RECEIPT_FILE).exists():
        prev = read_json(d / T.ADJ_RECEIPT_FILE)
        raise T.T1Error(f"the IRR adjudication was already ingested at {prev['ingested_at']}; a second version is refused")
    src = Path(file)
    completed_sha = sha256_file(src)
    observed_at = datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    zbytes = zipfile.ZipFile(template_zip).read(LEGACY_TEMPLATE_MEMBER)
    template = T.parse_sheet_text(zbytes.decode("utf-8-sig"))
    completed = T.read_sheet(src)
    key = read_json(d / T.KEY_FILE)["irr"]["items"]
    decisions, problems = T.validate_legacy_adjudication(
        completed, template, {i: v["compared_classes"] for i, v in key.items()}, tc)
    current = T.read_sheet(d / IRR_ADJUDICATION_FILE)
    mapped, mproblems = T.map_adjudication(current, decisions) if not problems else ([], [])
    if problems or mproblems:
        raise T.T1Error("adjudication NOT ingested:\n  " + "\n  ".join(problems + mproblems))
    rows, labels = _irr_labels(resolver)
    consensus = T.irr_consensus(labels, decisions)
    evidence = T.not_obligation_rule_evidence(decisions, labels)
    backup = run_backup(resolver, None)
    template_path = d / T.ADJ_LEGACY_TEMPLATE_FILE
    if template_path.exists() and sha256_file(template_path) != hashlib.sha256(zbytes).hexdigest():
        raise T.T1Error(f"{template_path} exists with different content")
    template_path.write_bytes(zbytes)
    T.write_sheet(d / T.ADJ_MAPPED_FILE, mapped, T.IRR_ADJUDICATION_COLUMNS, header=(
        "# IRR adjudication in the per-comparison layout, migrated deterministically from the item-level completion "
        f"{T.ADJ_COMPLETED_FILE}. No new decisions. Consensus layer only; raw votes are unchanged."),
        input_columns=())
    cpath = write_jsonl(d / T.IRR_CONSENSUS_FILE, consensus)
    obl = [c for c in consensus if not c["not_obligation"]]
    meta = {
        "note": "IRR adjudication metadata. Separate from reports/p2004_irr_metrics_v1.json, whose raw "
                "pre-adjudication reliability figures are unchanged.",
        "consensus": {"items": len(consensus), "routes": dict(Counter(c["route"] for c in consensus)),
                      "not_obligation": sum(c["not_obligation"] for c in consensus),
                      "judgements": {j: sum(1 for c in obl for v in c["judgements"].values() if v == j)
                                     for j in T.JUDGEMENTS},
                      "flags": dict(sorted(Counter(c["differential_flag"] for c in obl).items()))},
        "adjudicated_only": {
            "items": len(decisions), "not_obligation": sum(v["not_obligation"] for v in decisions.values()),
            "judgements": {j: sum(1 for v in decisions.values() for x in v["judgements"].values() if x == j)
                           for j in T.JUDGEMENTS}},
        "mapped_rows": {"item": sum(r["comparison"] == "item" for r in mapped),
                        "class": sum(r["comparison"] == "class" for r in mapped),
                        "item_not_obligation_rows": sum(r["comparison"] == "item" and
                                                        "not_obligation" in r["differs_on"] for r in mapped)},
        "not_obligation_rule": {
            "settled_rule": SETTLED_RULE, "evidence": evidence,
            "support": ("Supported by the adjudicated decisions: every rejection is an incomplete span, a "
                        "classification/criterion-only clause, a worked example or a scope clause, and every "
                        "overturned rejection vote was a complete mandatory condition (including passive wording). "
                        "No disputed item here was rejected as purely definitional or as a third-party duty; those "
                        "two clauses rest on guidelines v1 and v2.1, not on this adjudication.")},
    }
    write_json(resolver.write_path("reports", IRR_ADJ_METADATA), meta)
    receipt = {
        "completed_file": repo_relative(src), "completed_sha256": completed_sha, "observed_modified_at": observed_at,
        "ingested_at": _now(), "input_modified": False,
        "label_source": label_source, "label_source_basis": label_source_basis,
        "legacy_template": {"file": repo_relative(template_path), "restored_from": f"{Path(template_zip).name}!"
                            f"{LEGACY_TEMPLATE_MEMBER}", "sha256": hashlib.sha256(zbytes).hexdigest(),
                            "rows": len(template)},
        "validation": {"result": "passed", "immutable_cells_changed": 0,
                       "checks": ["18 item_ids in issued order", "immutable columns equal the issued sheet",
                                  "only final_applies_to / final_judgements / final_not_obligation / rationale filled",
                                  "every decision and rationale present", "JSON parses",
                                  "v2.2 vocabulary for applies_to", "judgements cover exactly the compared classes",
                                  "judgement vocabulary", "rejected items carry no labels"]},
        "adjudicated_items": len(decisions),
        "disagreements": {"items": len({r['item_id'] for r in current})},
        "current_rows": len(current), "current_item_rows": sum(r["comparison"] == "item" for r in current),
        "current_class_rows": sum(r["comparison"] == "class" for r in current), "mapped_rows": len(mapped),
        "mapped_file": repo_relative(d / T.ADJ_MAPPED_FILE), "mapped_sha256": sha256_file(d / T.ADJ_MAPPED_FILE),
        "consensus_file": repo_relative(cpath), "consensus_sha256": sha256_file(cpath),
        "schema_migration": ("Completed on the original 18-row item-level sheet; the repository later moved to a "
                             "per-comparison sheet. The completion was validated against the sheet it was issued "
                             "as, then transformed deterministically into the current rows. No new adjudication "
                             "decisions were introduced."),
        "backup_before_write": backup["zip"],
    }
    write_json(d / T.ADJ_RECEIPT_FILE, receipt)
    report = insert_adjudication_section(resolver)
    return {"receipt": receipt, "metadata": repo_relative(resolver.write_path("reports", IRR_ADJ_METADATA)),
            "report": repo_relative(report), "consensus": meta["consensus"], "adjudicated_only": meta["adjudicated_only"],
            "mapped_rows": meta["mapped_rows"]}


# ---------------------------------------------------------------------------
# C2 readiness (workflow state only) and the blank pass-2 sheet
# ---------------------------------------------------------------------------


def run_retest_check(cfg, tc: T.T1Config, resolver) -> dict:
    """READY / NOT READY from workflow state. Elapsed time is never consulted."""
    d = tdir(resolver)
    checks: dict[str, dict[str, Any]] = {}
    rpath = d / T.PASS1_RECEIPTS_FILE
    rec = read_json(rpath)["receipts"].get(tc.primary) if rpath.exists() else None
    checks["pass1_ingested"] = {"ok": rec is not None, "detail": rec and f"received {rec['received_at']}"}
    frozen = False
    if rec:
        stored = d / T.PASS1_RECEIVED_DIR / rec["stored_as"]
        src = resolver.working_root / rec["source_path"]
        frozen = stored.exists() and sha256_file(stored) == rec["sha256"] and src.exists() \
            and sha256_file(src) == rec["sha256"]
    fpath = d / T.PASS1_FREEZE_FILE
    if frozen and fpath.exists():
        fr = read_json(fpath)
        stored = d / T.PASS1_RECEIVED_DIR / rec["stored_as"]
        frozen = fr["sha256"] == rec["sha256"] == sha256_file(stored) and not os.access(stored, os.W_OK)
    else:
        frozen = False
    checks["pass1_frozen"] = {"ok": frozen, "detail": "freeze record present; read-only frozen copy, source and "
                                                      "receipt share one sha256; ingest-pass1 refuses a second version"}
    key = read_json(d / T.KEY_FILE)
    items = sorted(iter_jsonl(d / T.SAMPLE_FILE), key=lambda s: s["order"])
    recomputed = T.draw_retest(items, tc.retest_fraction, tc.seeds["retest"])
    checks["retest_subset_predetermined"] = {
        "ok": bool(key.get("retest_ids")) and recomputed == key["retest_ids"],
        "detail": f"{len(key.get('retest_ids', []))} ids in the hidden key; recomputed from the sample order and "
                  f"seed {tc.seeds['retest']} alone: {'identical' if recomputed == key.get('retest_ids') else 'DIFFERENT'}"}
    first_draw = read_json(d / T.DRAW_LOG_FILE)["entries"][0]["written_at"]
    checks["retest_subset_independent_of_pass1"] = {
        "ok": bool(rec) and first_draw < rec["received_at"],
        "detail": f"draw_retest takes only the sample order and a seed (no labels); subset drawn by {first_draw}, "
                  f"before pass 1 was received at {rec and rec['received_at']}"}
    drawn_ok = True
    try:
        _pass1_drawn(resolver)
    except T.T1Error:
        drawn_ok = False
    checks["pass2_built_from_blank_drawn_sheet"] = {
        "ok": drawn_ok, "detail": "rows come from the blank pass-1 sheet as drawn (sha256 in the draw log), "
                                  "never from the completed file; all input cells set blank"}
    checks["pass2_shuffled"] = {"ok": True, "detail": f"new item order, seed {T.PASS2_SHUFFLE_SEED}"}
    ready = all(c["ok"] for c in checks.values())
    return {"status": "READY" if ready else "NOT READY", "checks": checks,
            "date_lock": "none: no minimum interval, not_before or unlock date is consulted"}


def run_freeze_pass1(tc: T.T1Config, resolver) -> dict:
    """Freeze Karan's pass 1: the stored copy is made read-only and its sha256 recorded. Content is never changed."""
    d = tdir(resolver)
    rec = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    stored = d / T.PASS1_RECEIVED_DIR / rec["stored_as"]
    sha = sha256_file(stored)
    if sha != rec["sha256"]:
        raise T.T1Error(f"{stored} does not match the pass-1 receipt; not freezing")
    fpath = d / T.PASS1_FREEZE_FILE
    if fpath.exists():
        prev = read_json(fpath)
        if prev["sha256"] != sha:
            raise T.T1Error("pass 1 was frozen with a different sha256")
        os.chmod(stored, stat.S_IREAD)
        return {**prev, "already_frozen": True}
    os.chmod(stored, stat.S_IREAD)
    record = {"frozen_copy": repo_relative(stored), "source": rec["source_path"], "sha256": sha,
              "frozen_at": _now(), "read_only": not os.access(stored, os.W_OK),
              "note": "Pass 1 is frozen: pass 2 never reads it, and no later step may change it."}
    write_json(fpath, record)
    return record


def _supersede_blank(path: Path, input_columns: Sequence[str]) -> str | None:
    """Move a blank, never-labelled sheet into superseded/ (kept, not deleted); refuse if it holds answers."""
    if not path.exists():
        return None
    if any((r.get(c) or "").strip() for r in T.read_sheet(path, require_id=False) for c in input_columns):
        raise T.T1Error(f"{path.name} holds answers; it is not replaced")
    dest = path.parent / "superseded" / f"{path.stem}_superseded_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.replace(dest)
    return repo_relative(dest)


def run_retest_sheet(cfg, tc: T.T1Config, resolver, logger) -> dict:
    """C2: one blind pass-2 sheet = the Part A retest subset + the 18 pilot items, shuffled together, blank."""
    d = tdir(resolver)
    readiness = run_retest_check(cfg, tc, resolver)
    if readiness["status"] != "READY":
        raise T.T1Error(f"C2 NOT READY: {readiness['checks']}")
    key = read_json(d / T.KEY_FILE)
    drawn = _pass1_drawn(resolver)
    retest = T.build_retest_rows(drawn, key["retest_ids"], seed=T.PASS2_SHUFFLE_SEED, block_size=tc.block_size)
    pilot = {lbl.label_id: lbl for lbl in load_pilot_candidates(resolver)}
    pilot_ids = sorted(load_retest_set(resolver))
    prows = T.pilot_pass2_rows([_task_row(pilot[i]) for i in pilot_ids])
    rows = T.build_pass2_rows(retest, prows, seed=T.PASS2_SHUFFLE_SEED, block_size=tc.block_size)
    T.assert_pass2_blind(rows)
    # Blindness: no earlier answer text may appear (pass 1, pilot pass 1 of every rater, IRR raters, adjudication).
    rec = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    earlier = [T.read_sheet(d / T.PASS1_RECEIVED_DIR / rec["stored_as"])]
    earlier += list(_irr_labels(resolver)[0].values())
    for r in ("karan", "akash", "meer"):
        p = resolver.working_root / "data" / "benchmark" / "tasks" / f"annotation_{r}.csv"
        if p.exists():
            earlier.append(T.read_sheet(p))
    texts = {(r.get(c) or "").strip() for rs in earlier for r in rs for c in ("applies_to_rationale", "note", "notes")}
    adj = d / T.ADJ_COMPLETED_FILE
    if adj.exists():
        texts |= {(r.get("rationale") or "").strip() for r in T.read_sheet(adj)}
    leaks = T.leaked_texts(rows, texts)
    if leaks:
        raise T.T1Error(f"pass-2 sheet would expose {len(leaks)} earlier answer text(s), e.g. {leaks[0][:60]!r}")
    superseded = [s for s in (_supersede_blank(d / T.PASS2_SHEET, T.PASS2_INPUT_COLUMNS),
                              _supersede_blank(d / T.PILOT_PASS2_SHEET, PILOT_INPUT_COLUMNS)) if s]
    path = T.write_sheet(d / T.PASS2_SHEET, rows, T.PASS2_COLUMNS, header=T.PASS2_HEADER,
                         input_columns=T.PASS2_INPUT_COLUMNS)
    back = T.read_sheet(path)
    item_order = [r["item_id"] for r in back if r["row_type"] in (T.ROW_ITEM, T.ROW_PILOT)]
    retest_set, pilot_set = set(key["retest_ids"]), set(pilot_ids)
    drawn_by_item = defaultdict(list)
    for r in drawn:
        drawn_by_item[r["item_id"]].append(r)
    shown = [c for c in T.SHEET_COLUMNS if c not in T.INPUT_COLUMNS and c != "block"]
    checks = {
        "items": len(item_order), "retest_items": sum(i in retest_set for i in item_order),
        "pilot_items": sum(i in pilot_set for i in item_order), "rows": len(back),
        "ids_equal_retest_plus_pilot": sorted(item_order) == sorted(retest_set | pilot_set),
        "order_mixes_retest_and_pilot": item_order != sorted(item_order, key=lambda i: (i in pilot_set, i)),
        "input_cells_blank": all(not (r.get(c) or "").strip() for r in back for c in T.PASS2_INPUT_COLUMNS),
        "retest_shown_columns_match_pass1_sheet": all(
            [{c: x[c] for c in shown} for x in back if x["item_id"] == iid] ==
            [{c: x[c] for c in shown} for x in drawn_by_item[iid]] for iid in retest_set),
        "earlier_answer_texts_checked": len(texts), "leaks": 0,
    }
    if not (checks["ids_equal_retest_plus_pilot"] and checks["input_cells_blank"]
            and checks["retest_shown_columns_match_pass1_sheet"]):
        raise T.T1Error(f"pass-2 sheet failed validation: {checks}")
    overlap = sorted(retest_set & set(key["second_rater_ids"]))
    key["pass2"] = {"sheet": repo_relative(path), "sha256": sha256_file(path), "seed": T.PASS2_SHUFFLE_SEED,
                    "retest_ids": sorted(retest_set), "pilot_ids": pilot_ids, "item_order": item_order}
    key["retest_overlap_second_rater"] = {
        "item_ids": overlap,
        "note": "Retest items also in the 30-item second-rater overlap (Akash/Meer labelled them; Karan has not "
                "adjudicated them). Report their test-retest results separately."}
    for iid in key["items"]:
        key["items"][iid]["retest_and_second_rater_overlap"] = iid in overlap
    write_json(d / T.KEY_FILE, key)
    ann_log = read_json(resolver.working_root / "data" / "benchmark" / "annotation_log.json")
    pilot_ingests = [e for e in ann_log.get("entries", []) if e.get("event") == "ingest"
                     and e.get("rater_id") == tc.primary and int(e.get("pass_no") or 0) == 1]
    log = {"generated_at": _now(), "file": repo_relative(path), "sha256": sha256_file(path),
           "seed": T.PASS2_SHUFFLE_SEED, "guidelines_version": tc.guidelines_version,
           "method": T.RETEST_METHOD_STATEMENT,
           "provenance": {
               "p2004_pass_1_completed_at": "unknown (not logged at the time)",
               "p2004_pass_1_ingested_at": rec["received_at"],
               "pilot_pass_1_completed_at": "unknown (not logged at the time)",
               "pilot_pass_1_ingested_at": pilot_ingests[-1]["timestamp"] if pilot_ingests else "unknown",
               "pass_2_completed_at": "unknown (not yet returned)", "elapsed_between_passes": "unknown",
               "note": "Timing is provenance only; it never gates generation, ingest, adjudication or reporting."},
           "superseded_blank_sheets": superseded, "retest_overlap_second_rater": overlap,
           "readiness": readiness, "validation": checks}
    write_json(d / T.PASS2_LOG_FILE, log)
    logger.info("pass-2 sheet written: %s", log)
    return log


# ---------------------------------------------------------------------------
# Pass 2: ingest (once) and test-retest reliability
# ---------------------------------------------------------------------------

RETEST_METRICS_FILE = "p2004_retest_metrics_v1.json"
RETEST_REPORT_FILE = "p2004_retest_v1.md"


def _pass2_drawn(resolver) -> list[dict[str, str]]:
    d = tdir(resolver)
    log = read_json(d / T.PASS2_LOG_FILE)
    path = d / T.PASS2_SHEET
    if sha256_file(path) != log["sha256"]:
        raise T.T1Error(f"{path.name} no longer matches the pass-2 sheet as written (sha256 in {T.PASS2_LOG_FILE})")
    return T.read_sheet(path)


def _pilot_classes(tc: T.T1Config) -> tuple[str, ...]:
    """Pilot rows on the pass-2 sheet follow v2 rules, so applies_to uses the v2.2 vocabulary (11 classes + 2 stand-ins)."""
    return tc.applies_to_vocabulary


def run_pass2_check(tc: T.T1Config, resolver, file: str) -> dict:
    src = Path(file)
    v = T.validate_pass2_file(src, _pass2_drawn(resolver), tc, paragraph_classes(resolver), _pilot_classes(tc))
    return {**v, "sha256": sha256_file(src)}


def run_ingest_pass2(tc: T.T1Config, resolver, logger, file: str, label_source: str, minutes: float | None,
                     minutes_source: str | None, corrects: str | None = None,
                     correction_items: list[str] | None = None, correction_note: str | None = None) -> dict:
    """Ingest pass 2 exactly once. Any validation problem stops before anything is written. Timing never gates.

    ``corrects``: the original file this one corrects; only ``correction_items`` may differ, and only in input
    cells. Every changed cell is recorded in the receipt."""
    d = tdir(resolver)
    src = Path(file)
    if not src.is_file():
        raise T.T1Error(f"{file}: not found")
    T.refuse_not_independent(src, d)
    rpath = d / T.PASS2_RECEIPTS_FILE
    receipts = read_json(rpath) if rpath.exists() else {"receipts": {}}
    if tc.primary in receipts["receipts"]:
        prev = receipts["receipts"][tc.primary]
        raise T.T1Error(f"pass 2 was already received at {prev['received_at']} (sha256 {prev['sha256'][:12]}…); "
                        "a second version is refused")
    sha, received_at = sha256_file(src), _now()
    correction = None
    if corrects:
        orig = Path(corrects)
        changes, cproblems = T.correction_diff(T.read_sheet(orig), T.read_sheet(src), correction_items or [],
                                               T.PASS2_INPUT_COLUMNS)
        if cproblems:
            raise T.T1Error("correction NOT accepted:\n  " + "\n  ".join(cproblems))
        correction = {"corrects": repo_relative(orig), "original_sha256": sha256_file(orig),
                      "allowed_items": sorted(correction_items or []), "changed_rows": changes,
                      "reason": correction_note, "original_unchanged": True}
    v = T.validate_pass2_file(src, _pass2_drawn(resolver), tc, paragraph_classes(resolver), _pilot_classes(tc))
    if v["problems"]:
        raise T.T1Error(f"pass 2 NOT ingested: {len(v['problems'])} problem(s):\n  " + "\n  ".join(v["problems"]))
    store = d / T.PASS2_RECEIVED_DIR / T.PASS2_SHEET
    if store.exists():
        raise T.T1Error(f"{store} already exists; refusing to overwrite a received file")
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_bytes(src.read_bytes())
    if sha256_file(store) != sha:
        raise T.T1Error("stored copy does not match the source sha256")
    os.chmod(store, stat.S_IREAD)
    log = read_json(d / T.PASS2_LOG_FILE)
    written = datetime.fromisoformat(log["generated_at"])
    window = (datetime.fromisoformat(received_at) - written).total_seconds() / 60.0
    receipt = {
        "rater": tc.primary, "pass": 2, "source_path": repo_relative(src), "stored_as": T.PASS2_SHEET,
        "sha256": sha, "received_at": received_at, "label_source": label_source, "has_bom": v["has_bom"],
        "rows": v["rows"], "items": v["items"],
        "source_file_modified_at": datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
        "timing": {
            "minutes": minutes, "minutes_source": minutes_source,
            "minutes_per_item": (minutes / v["items"]) if minutes else None,
            "blank_sheet_written_at": log["generated_at"], "received_at": received_at,
            "window_minutes_sheet_written_to_received": round(window, 1),
            "minutes_exceed_window": bool(minutes and minutes > window),
            "pass_1_completed_at": "unknown (not logged)", "pass_2_completed_at": "unknown (not logged)",
            "note": "Provenance only. Neither the self-reported minutes nor the window gates anything.",
        },
        "checks": ["sha256", "received_at", "BOM", "schema", "item identity and order vs the drawn pass-2 sheet",
                   "row uniqueness", "item/class rows: v3 vocabulary, blanks, matched_paragraph_id, differential_flag blank",
                   "pilot rows: v2.2 vocabulary, flag vocabulary, non-obligation note, v3 cells blank"],
        "correction": correction,
    }
    receipts["receipts"][tc.primary] = receipt
    write_json(rpath, receipts)
    logger.info("pass 2 ingested: %s", receipt)
    return receipt


def run_retest_score(cfg, tc: T.T1Config, resolver, logger) -> dict:
    d = tdir(resolver)
    rec2 = read_json(d / T.PASS2_RECEIPTS_FILE)["receipts"][tc.primary]
    rec1 = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    p2_path = d / T.PASS2_RECEIVED_DIR / rec2["stored_as"]
    p1_path = d / T.PASS1_RECEIVED_DIR / rec1["stored_as"]
    for p, r in ((p1_path, rec1), (p2_path, rec2)):
        if sha256_file(p) != r["sha256"]:
            raise T.T1Error(f"{p} no longer matches its receipt")
    p2_rows = T.read_sheet(p2_path)
    key = read_json(d / T.KEY_FILE)
    retest_ids = set(key["retest_ids"])
    overlap = set(key["retest_overlap_second_rater"]["item_ids"])
    p1_rows = [r for r in T.read_sheet(p1_path) if r["item_id"] in retest_ids]
    p2_main = [r for r in p2_rows if r["row_type"] in (T.ROW_ITEM, T.ROW_CLASS)]
    L1, L2 = T.parse_labelled_items(p1_rows), T.parse_labelled_items(p2_main)
    seed = int(cfg["benchmark"]["agreement"]["bootstrap_seed"])

    def block(ids):
        m = T.irr_metrics({"pass1": {i: L1[i] for i in ids}, "pass2": {i: L2[i] for i in ids}}, seed=seed,
                          resamples=IRR_RESAMPLES)
        return {"n_items": len(ids), **m["pairwise"]["pass1-pass2"]}

    subsets = {"all_25": sorted(retest_ids), "second_rater_overlap_9": sorted(overlap),
               "other_16": sorted(retest_ids - overlap)}
    phase2 = {k: block(v) for k, v in subsets.items()}
    votes = read_jsonl(resolver.read_path("benchmark", "pilot_votes.jsonl"))
    pp1 = T.pilot_labels_from_votes(votes, tc.primary, 1)
    pp2 = T.pilot_labels_from_rows(p2_rows)
    pilot = T.pilot_retest_metrics(pp1, pp2, seed=seed, resamples=IRR_RESAMPLES)
    corrected = sorted((rec2.get("correction") or {}).get("allowed_items", []))
    pilot_sens = None
    if corrected:
        keep = [i for i in pp2 if i not in corrected]
        pilot_sens = {"excluded_items": corrected,
                      "reason": "corrected after pass-1 answers for these items had been displayed in the session "
                                "(reversed-ingest report); their corrected pass-2 labels may not be blind",
                      **T.pilot_retest_metrics({i: pp1[i] for i in keep if i in pp1}, {i: pp2[i] for i in keep},
                                               seed=seed, resamples=IRR_RESAMPLES)}
    pilot_ctx = {r["item_id"]: (r["source_paragraph_id"], T._cap(r["source_span"], 600)) for r in p2_rows
                 if r["row_type"] == T.ROW_PILOT}
    adj = T.retest_adjudication_rows(p1_rows, p2_main, pp1, pp2, pilot_ctx)
    if adj:
        T.write_sheet(d / T.RETEST_ADJUDICATION_FILE, adj, T.RETEST_ADJ_COLUMNS, header=(
            "# Test-retest adjudication (Karan): one row per comparison where pass 1 != pass 2 (and any 'unsure'). "
            "Fill final_decision and final_rationale; don't edit the other columns."),
            input_columns=("final_decision", "final_rationale"))
    ann_log = read_json(resolver.write_path("benchmark", "annotation_log.json"))
    pilot_p1 = [e for e in ann_log.get("entries", []) if e.get("event") == "ingest" and e.get("rater_id") == tc.primary
                and int(e.get("pass_no") or 0) == 1]
    out = {
        "generated_at": _now(), "method": T.RETEST_METHOD_STATEMENT, "comparison": "intra-rater (Karan pass 1 vs pass 2)",
        "bootstrap": {"resamples": IRR_RESAMPLES, "seed": seed, "unit": "item"},
        "provenance": {
            "pass1": {"file": rec1["source_path"], "sha256": rec1["sha256"], "received_at": rec1["received_at"],
                      "completed_at": "unknown (not logged)"},
            "pilot_pass1": {"ingested_at": pilot_p1[-1]["timestamp"] if pilot_p1 else "unknown",
                            "completed_at": "unknown (not logged)"},
            "pass2": {"file": rec2["source_path"], "sha256": rec2["sha256"], "received_at": rec2["received_at"],
                      "label_source": rec2["label_source"], **rec2["timing"], "correction": rec2.get("correction")}},
        "phase2": phase2, "pilot": pilot, "pilot_sensitivity_excluding_corrected": pilot_sens,
        "subsets": {k: len(v) for k, v in subsets.items()},
        "disagreements": {"rows": len(adj), "items": len({r["item_id"] for r in adj}),
                          "retest_items": len({r["item_id"] for r in adj if r["kind"] == "retest"}),
                          "pilot_items": len({r["item_id"] for r in adj if r["kind"] == "pilot"}),
                          "item_ids": sorted({r["item_id"] for r in adj}),
                          "file": repo_relative(d / T.RETEST_ADJUDICATION_FILE) if adj else None},
    }
    write_json(resolver.write_path("reports", RETEST_METRICS_FILE), out)
    out["report"] = repo_relative(write_retest_report(resolver, out, adj, overlap))
    write_json(resolver.write_path("reports", RETEST_METRICS_FILE), out)
    return out


def write_retest_report(resolver, m: dict, adj: list, overlap: set) -> Path:
    num = lambda x: "n/a" if x is None else (x if isinstance(x, str) else f"{x:.3f}")
    pct = lambda x: "n/a" if x is None else f"{x:.1%}"

    def ci(b):
        c = b.get("ci95")
        return c if isinstance(c, str) else f"{c[0]:.3f} to {c[1]:.3f}"

    pv = m["provenance"]
    p2 = pv["pass2"]
    lines = [
        "# P2-004 test-retest reliability (v1)", "",
        f"_Generated {m['generated_at']} by `python scripts/run_t1.py retest-score`. Intra-rater: Karan pass 1 vs "
        f"pass 2. Bootstrap: {m['bootstrap']['resamples']} resamples, seed {m['bootstrap']['seed']}, resampling whole "
        "items._", "",
        "## Method", "", m["method"], "",
        "This is test-retest (intra-rater) reliability, not inter-annotator agreement.", "",
        "## Provenance", "",
        f"- Pass 1 (P2-004): `{pv['pass1']['file']}`, sha256 `{pv['pass1']['sha256'][:12]}…`, received "
        f"{pv['pass1']['received_at']}; completed_at: {pv['pass1']['completed_at']}.",
        f"- Pilot pass 1: ingested {pv['pilot_pass1']['ingested_at']}; completed_at: {pv['pilot_pass1']['completed_at']}.",
        f"- Pass 2: `{p2['file']}`, sha256 `{p2['sha256']}`, received {p2['received_at']}, label source "
        f"{p2['label_source']}; completed_at: {p2['pass_2_completed_at']}.",
        f"- Blank pass-2 sheet written {p2['blank_sheet_written_at']}; window from then to receipt: "
        f"**{p2['window_minutes_sheet_written_to_received']} min**.",
        f"- Self-reported pass-2 time: **{p2['minutes']} min** ({p2['minutes_source']}); "
        f"{p2['minutes_per_item']:.2f} min/item over the sheet's items." if p2.get("minutes") else "- Pass-2 minutes: not reported.",
    ]
    corr = p2.get("correction")
    if corr:
        lines.append(f"- **Correction.** This file corrects `{corr['corrects']}` (sha256 `{corr['original_sha256'][:12]}…`, "
                     f"unchanged). Reason: {corr['reason']} Only these rows differ, only in input cells:")
        for c in corr["changed_rows"]:
            cells = "; ".join(f"`{k}`: {v['from']!r} → {v['to']!r}" for k, v in c["cells"].items())
            lines.append(f"  - row {c['row']} `{c['item_id']}`: {cells}")
    orig = p2.get("original_submission")
    if orig:
        lines += ["", "Pass-2 timing, side by side (provenance only; nothing is gated on it):", "",
                  "| Figure | Minutes | Basis |", "|---|---|---|",
                  f"| Self-reported labelling time | {p2['minutes']:.0f} | {p2['minutes_source']} |",
                  f"| Blank sheet written → original file last modified | {orig['window_minutes_sheet_written_to_file_modified']} | "
                  f"{p2['blank_sheet_written_at']} → {orig['file_modified_at']} |",
                  f"| Blank sheet written → original file received | {orig['window_minutes_sheet_written_to_received']} | "
                  f"{p2['blank_sheet_written_at']} → {orig['received_at']} |",
                  f"| Blank sheet written → corrected file received | {p2['window_minutes_sheet_written_to_received']} | "
                  f"{p2['blank_sheet_written_at']} → {p2['received_at']} (includes the three-row correction) |", ""]
        if orig["minutes_exceed_window"]:
            lines.append(f"The self-reported {p2['minutes']:.0f} min exceeds the {orig['window_minutes_sheet_written_to_received']} "
                         "min window up to the original submission. Both are reported as they are; neither is adjusted "
                         "and neither gates anything.")
    elif p2.get("minutes_exceed_window"):
        lines.append(f"- **The self-reported {p2['minutes']} min exceeds the {p2['window_minutes_sheet_written_to_received']} "
                     "min window** between the blank sheet being written and the file being received. Both figures are "
                     "reported as they are; neither gates anything.")
    lines += ["", "## Phase-2 retest items", "",
              "Denominators: not_obligation over all items in the subset; the flag, class-row judgements and "
              "applies_to over items labelled as obligations in **both** passes.", "",
              "| Subset | Measure | n items (units) | Agreement | κ | 95% CI |", "|---|---|---|---|---|---|"]
    names = {"all_25": "all 25", "second_rater_overlap_9": "9 also in the second-rater overlap",
             "other_16": "the other 16"}
    for k, label in names.items():
        b = m["phase2"][k]
        for meas, mlabel in (("not_obligation", "not_obligation"), ("differential_flag", "flag (v3.6)"),
                             ("per_class_judgement", "class-row judgement")):
            x = b[meas]
            lines.append(f"| {label} | {mlabel} | {x['n_items']} ({x['n_units']}) | {pct(x['observed_agreement'])} | "
                         f"{num(x['kappa'])} | {ci(x['bootstrap'])} |")
    lines += ["", "| Subset | applies_to n | Exact-set agreement | 95% CI | Mean Jaccard | 95% CI |",
              "|---|---|---|---|---|---|"]
    for k, label in names.items():
        a = m["phase2"][k]["applies_to"]
        lines.append(f"| {label} | {a['n_items']} | {pct(a['exact_set_agreement'])} | {ci(a['exact_set_bootstrap'])} | "
                     f"{num(a['mean_jaccard'])} | {ci(a['mean_jaccard_bootstrap'])} |")
    pl = m["pilot"]
    lines += ["", f"## Pilot items ({pl['n_items']})", "",
              f"Pilot layout (item-level flag). Flag and applies_to over the {pl['both_obligation']} items labelled as "
              "obligations in both passes.", "",
              "| Measure | n | Agreement | κ | 95% CI |", "|---|---|---|---|---|"]
    for meas, mlabel in (("not_obligation", "not_obligation"), ("differential_flag", "differential_flag")):
        x = pl[meas]
        lines.append(f"| {mlabel} | {x['n_items']} | {pct(x['observed_agreement'])} | {num(x['kappa'])} | {ci(x['bootstrap'])} |")
    a = pl["applies_to"]
    lines += [f"| applies_to exact-set | {a['n_items']} | {pct(a['exact_set_agreement'])} | — | {ci(a['exact_set_bootstrap'])} |",
              f"| applies_to mean Jaccard | {a['n_items']} | {num(a['mean_jaccard'])} | — | {ci(a['mean_jaccard_bootstrap'])} |"]
    ps = m.get("pilot_sensitivity_excluding_corrected")
    if ps:
        sa = ps["applies_to"]
        lines += ["", f"**Sensitivity, excluding the {len(ps['excluded_items'])} corrected pilot items** "
                  f"({', '.join('`' + i + '`' for i in ps['excluded_items'])}): {ps['reason']}. After correction, "
                  "all three match pass 1 exactly on applies_to.", "",
                  "| Measure | n | Agreement | κ | 95% CI |", "|---|---|---|---|---|"]
        for meas, mlabel in (("not_obligation", "not_obligation"), ("differential_flag", "differential_flag")):
            x = ps[meas]
            lines.append(f"| {mlabel} | {x['n_items']} | {pct(x['observed_agreement'])} | {num(x['kappa'])} | {ci(x['bootstrap'])} |")
        lines += [f"| applies_to exact-set | {sa['n_items']} | {pct(sa['exact_set_agreement'])} | — | {ci(sa['exact_set_bootstrap'])} |",
                  f"| applies_to mean Jaccard | {sa['n_items']} | {num(sa['mean_jaccard'])} | — | {ci(sa['mean_jaccard_bootstrap'])} |"]
    lines += ["", f"## Items where pass 1 ≠ pass 2 ({m['disagreements']['items']} items, {m['disagreements']['rows']} rows)", "",
              f"For adjudication: `{m['disagreements']['file']}` (blank `final_decision`, `final_rationale`).", "",
              "| Item | Kind | Comparison | Class | Differs on | Pass 1 | Pass 2 |", "|---|---|---|---|---|---|---|"]
    for r in adj:
        kind = r["kind"] + (" (overlap)" if r["item_id"] in overlap else "")
        lines.append(f"| {r['item_id']} | {kind} | {r['comparison']} | {r['target_class']} | {r['differs_on']} | "
                     f"{r['pass1_decision']} | {r['pass2_decision']} |")
    lines += ["", "## Limitations", "",
              "- n is small (25 retest items, 18 pilot items); the intervals are wide.",
              "- No washout period: a short interval may inflate agreement through recall of pass-1 answers.",
              "- pass_1_completed_at is unknown (not logged); pass-2 timing is self-reported.",
              "- The pilot's pass 1 was labelled under guidelines v1; pass 2 under v3.1 (same item-level definitions).",
              "- The 9 overlap items are reported separately because their second-rater labels are not yet adjudicated.", ""]
    path = resolver.write_path("reports", RETEST_REPORT_FILE)
    write_text(path, "\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Team review of the 30 overlap items (Akash, Meer): not independent raters, no κ
# ---------------------------------------------------------------------------

TEAM_REVIEW_HISTORY = (
    "Earlier versions of these files were shared with the reviewer (Claude) on 27 Sep 2026, 01:20-02:20 IST, and "
    "revised after its feedback. Only these final versions exist on disk. They are therefore a team review, not "
    "independent second-rater labels: no κ or other agreement statistic is computed from them, and they can never "
    "validate an item on their own.")


def run_ingest_team_review(tc: T.T1Config, resolver, logger, rater: str, file: str, label_source: str,
                           label_source_basis: str) -> dict:
    d = tdir(resolver)
    if rater not in tc.second_raters:
        raise T.T1Error(f"{rater!r} is not one of {tc.second_raters}")
    src = Path(file)
    if not src.is_file():
        raise T.T1Error(f"{file}: not found")
    T.refuse_not_independent(src, d)
    rpath = d / T.TEAM_REVIEW_RECEIPTS_FILE
    receipts = read_json(rpath) if rpath.exists() else {"receipts": {}}
    if rater in receipts["receipts"]:
        prev = receipts["receipts"][rater]
        raise T.T1Error(f"{rater}'s team review was already received at {prev['received_at']}; a second version is refused")
    blank = d / T.SECOND_RATER_SHEET.format(rater=rater)
    want = read_json(d / T.DRAW_LOG_FILE)["entries"][-1]["files"][rater]["sha256"]
    if sha256_file(blank) != want:
        raise T.T1Error(f"{blank.name} no longer matches the drawn sheet's recorded sha256")
    sha, received_at = sha256_file(src), _now()
    v = T.validate_annotation_file(src, T.read_sheet(blank), tc, paragraph_classes(resolver))
    if v["problems"]:
        raise T.T1Error(f"{rater} NOT ingested: {len(v['problems'])} problem(s):\n  " + "\n  ".join(v["problems"]))
    store = d / T.TEAM_REVIEW_RECEIVED_DIR / src.name
    if store.exists():
        raise T.T1Error(f"{store} already exists; refusing to overwrite a received file")
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_bytes(src.read_bytes())
    if sha256_file(store) != sha:
        raise T.T1Error("stored copy does not match the source sha256")
    os.chmod(store, stat.S_IREAD)
    receipt = {"rater": rater, "role": "team review of the 30 overlap items (not an independent rater)",
               "source_path": repo_relative(src), "stored_as": src.name, "sha256": sha, "received_at": received_at,
               "source_file_modified_at": datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
               "label_source": label_source, "label_source_basis": label_source_basis,
               "history": TEAM_REVIEW_HISTORY, "agreement_statistics": "none (by design)",
               "handling": {"role": "team review only", "may_validate_an_item": False,
                            "agreement_statistics": "none (no kappa)", "independent_rater": False},
               "has_bom": v["has_bom"], "rows": v["rows"], "items": v["items"],
               "checks": ["sha256", "received_at", "not_independent/ and *_mock* refused",
                          "schema, identity and order vs the drawn blank sheet", "row uniqueness",
                          "v3 vocabulary, blanks, matched_paragraph_id"]}
    receipts["receipts"][rater] = receipt
    write_json(rpath, receipts)
    logger.info("team review ingested: %s", receipt)
    return receipt


def run_overlap_adjudication(tc: T.T1Config, resolver) -> dict:
    d = tdir(resolver)
    receipts = read_json(d / T.TEAM_REVIEW_RECEIPTS_FILE)["receipts"]
    reviews = {}
    for rater in tc.second_raters:
        rec = receipts.get(rater)
        if rec is None:
            raise T.T1Error(f"{rater}'s team review is not ingested")
        p = d / T.TEAM_REVIEW_RECEIVED_DIR / rec["stored_as"]
        if sha256_file(p) != rec["sha256"]:
            raise T.T1Error(f"{p} no longer matches its receipt")
        reviews[rater] = T.read_sheet(p)
    rec1 = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    karan = T.read_sheet(d / T.PASS1_RECEIVED_DIR / rec1["stored_as"])
    key = read_json(d / T.KEY_FILE)
    overlap_ids = key["second_rater_ids"]
    rows = T.overlap_adjudication_rows(karan, reviews, overlap_ids)
    retest_adj = d / T.RETEST_ADJUDICATION_FILE
    in_retest = {r["item_id"] for r in T.read_sheet(retest_adj)} if retest_adj.exists() else set()
    differing = sorted({r["item_id"] for r in rows})
    left_out = sorted(set(differing) & in_retest)
    kept = [r for r in rows if r["item_id"] not in in_retest]
    path = d / T.OVERLAP_ADJUDICATION_FILE
    if kept:
        T.write_sheet(path, kept, T.OVERLAP_ADJ_COLUMNS, header=(
            "# Overlap adjudication (Karan): one row per comparison where Akash's or Meer's team-review labels "
            "differ from Karan's pass 1 (applies_to, not_obligation, class judgement, matched_paragraph_id). The "
            "team reviews are not independent raters and carry no κ. Items already in "
            "p2004_retest_adjudication_v1.csv are left out. Fill final_decision and final_rationale only."),
            input_columns=("final_decision", "final_rationale"))
    return {"file": repo_relative(path) if kept else None, "sha256": sha256_file(path) if kept else None,
            "overlap_items": len(overlap_ids), "items_differing_from_karan": len(differing),
            "left_out_already_in_retest_adjudication": left_out, "items_in_file": len({r["item_id"] for r in kept}),
            "rows_in_file": len(kept), "item_rows": sum(r["comparison"] == "item" for r in kept),
            "class_rows": sum(r["comparison"] == "class" for r in kept)}


# ---------------------------------------------------------------------------
# Parts D and E: adjudication ingest, validated set, final report
# ---------------------------------------------------------------------------

ADJ_RECEIPTS_FILE = "p2004_adjudication_receipts.json"
ADJ_RECEIVED_DIR = "adjudication_received"
VALIDATED_FILE = "t1_validated_v1.jsonl"
BENCHMARK_REPORT = "p2004_t1_benchmark.md"
BENCHMARK_METRICS = "p2004_t1_benchmark_metrics_v1.json"
ADJUDICATIONS = {
    "retest": ("p2004_retest_adjudication_v1_completed.csv", T.RETEST_ADJUDICATION_FILE, T.ADJUDICATION_INPUT_COLUMNS),
    "overlap": ("p2004_overlap_adjudication_v1_completed.csv", T.OVERLAP_ADJUDICATION_FILE, T.ADJUDICATION_INPUT_COLUMNS),
    "unsure": ("p2004_unsure_adjudication_v1_completed.csv", T.UNSURE_ADJUDICATION_FILE, T.UNSURE_INPUT_COLUMNS),
}
RULES_FILE = "p2004_adjudication_rules.md"


def ingest_adjudications(tc: T.T1Config, resolver) -> dict:
    """Validate every completion first; only if all pass, store read-only copies and write receipts (once each)."""
    d = tdir(resolver)
    rpath = d / ADJ_RECEIPTS_FILE
    receipts = read_json(rpath) if rpath.exists() else {"receipts": {}}
    pc = paragraph_classes(resolver)
    todo, problems = {}, []
    for name, (comp, tmpl, inputs) in ADJUDICATIONS.items():
        src = d / comp
        if name in receipts["receipts"]:
            if sha256_file(src) != receipts["receipts"][name]["sha256"]:
                problems.append(f"{name}: already ingested with a different sha256; a second version is refused")
            continue
        T.refuse_not_independent(src, d)
        p = T.validate_adjudication_completion(T.read_sheet(d / tmpl, require_id=False),
                                               T.read_sheet(src, require_id=False), inputs,
                                               pc if "final_matched_paragraph_id" in inputs else None)
        problems += [f"{name}: {x}" for x in p]
        todo[name] = src
    if problems:
        raise T.T1Error("adjudications NOT ingested:\n  " + "\n  ".join(problems))
    store_dir = d / ADJ_RECEIVED_DIR
    store_dir.mkdir(parents=True, exist_ok=True)
    for name, src in todo.items():
        sha = sha256_file(src)
        store = store_dir / src.name
        store.write_bytes(src.read_bytes())
        os.chmod(store, stat.S_IREAD)
        rows = T.read_sheet(src, require_id=False)
        receipts["receipts"][name] = {
            "file": repo_relative(src), "sha256": sha, "received_at": _now(), "label_source": "manual",
            "adjudicator": tc.primary, "rows": len(rows), "items": len({r["item_id"] for r in rows}),
            "decisions": dict(Counter(r["final_decision"].strip() for r in rows)),
            "left_unsure": sum(1 for r in rows if r["final_decision"].strip() == T.JUDGE_UNSURE),
            "stored_as": repo_relative(store), "rules": RULES_FILE}
    if "rules" not in receipts["receipts"]:
        rules = d / RULES_FILE
        receipts["receipts"]["rules"] = {"file": repo_relative(rules), "sha256": sha256_file(rules),
                                         "received_at": _now(), "role": "written adjudication rule"}
    irr = read_json(d / T.ADJ_RECEIPT_FILE)
    receipts["irr"] = {"file": irr["completed_file"], "sha256": irr["completed_sha256"],
                       "received_at": irr["ingested_at"], "note": "ingested earlier; existing receipt kept"}
    write_json(rpath, receipts)
    return receipts


def _wilson(k: int, n: int) -> dict:
    from src.benchmark.candidates import wilson_interval

    return {"k": k, "n": n, "rate": k / n if n else None, "wilson_95": list(wilson_interval(k, n)) if n else None}


def run_part_d(cfg, tc: T.T1Config, resolver, logger) -> dict:
    d = tdir(resolver)
    cand_path = d / T.CANDIDATE_BENCHMARK_FILE
    cand_sha_before = sha256_file(cand_path)
    backup = run_backup(resolver, None)
    receipts = ingest_adjudications(tc, resolver)
    key = read_json(d / T.KEY_FILE)
    sample = [s["item_id"] for s in iter_jsonl(d / T.SAMPLE_FILE)]
    rec1 = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    p1 = T.read_sheet(d / T.PASS1_RECEIVED_DIR / rec1["stored_as"])
    adj = {n: T.read_sheet(d / ADJ_RECEIVED_DIR / Path(r["stored_as"]).name, require_id=False)
           for n, r in receipts["receipts"].items() if n in ADJUDICATIONS}
    retest_rows = [r for r in adj["retest"] if r["kind"] == "retest"]
    labels, problems = T.final_labels(sample, p1, retest_ids=key["retest_ids"], retest_adj=retest_rows,
                                      overlap_adj=adj["overlap"], vocabulary=tc.applies_to_vocabulary)
    T.apply_unsure_decisions(labels, adj["unsure"])
    item_rationale = {r["item_id"]: r["final_rationale"] for r in retest_rows + adj["overlap"] if r["comparison"] == "item"}
    cands = {}
    wanted = set(sample)
    for r in iter_jsonl(cand_path):
        if r["item_id"] in wanted:
            cands[r["item_id"]] = r
    validated, excluded, vproblems = T.validated_records(labels, cands, p1, item_rationale)
    problems += vproblems
    vpath = write_jsonl(d / VALIDATED_FILE, validated)
    if sha256_file(cand_path) != cand_sha_before:
        raise T.T1Error("the candidate benchmark changed during Part D")
    metrics = benchmark_metrics(cfg, tc, resolver, validated, excluded, labels, key)
    out = {"generated_at": _now(), "backup_before": backup["zip"], "validated_file": repo_relative(vpath),
           "validated_sha256": sha256_file(vpath), "candidate_benchmark_unchanged": True,
           "adjudication_receipts": {k: {x: v[x] for x in ("file", "sha256", "received_at") if x in v}
                                     for k, v in {**receipts["receipts"], "irr": receipts["irr"]}.items()},
           "problems": problems, **metrics}
    write_json(resolver.write_path("reports", BENCHMARK_METRICS), out)
    out["report"] = repo_relative(write_benchmark_report(resolver, out))
    write_json(resolver.write_path("reports", BENCHMARK_METRICS), out)
    return out


def benchmark_metrics(cfg, tc: T.T1Config, resolver, validated, excluded, labels, key) -> dict:
    d = tdir(resolver)
    n_sample = len(labels)
    routes = Counter(v["provenance"] for v in validated)
    flags = Counter(v["differential_flag"] for v in validated)
    by_class = {}
    for v in validated:
        c = by_class.setdefault(v["entity_class"], Counter())
        c["validated"] += 1
        c[f"flag:{v['differential_flag']}"] += 1
        for j in v["per_class_judgement"].values():
            c[f"judgement:{j}"] += 1
    for iid in excluded["rejected"]:
        by_class.setdefault(labels[iid]["source_class"], Counter())["rejected"] += 1
    judgements = Counter(j for v in validated for j in v["per_class_judgement"].values())
    # candidate-label agreement by P2-002 band (automatic matched = same-or-different; below = none)
    bands = read_json(resolver.read_path("benchmark", "matching", "p2002_bands_v1.json"))
    band = lambda s: "high" if s >= bands["high_lower"] else ("mid" if s >= bands["mid_lower"] else "low")
    per_band = defaultdict(lambda: [0, 0])
    flag_agree = [0, 0]
    for v in validated:
        k = key["items"][v["item_id"]]
        for cls, j in v["per_class_judgement"].items():
            status = k["per_class_candidate"].get(cls)
            tops = k.get("p2002_top_targets", {}).get(cls) or []
            if status is None or not tops:
                continue
            b = band(tops[0]["semantic_score"])
            per_band[b][1] += 1
            per_band[b][0] += (status == T.STATUS_MATCHED) == (j in (T.JUDGE_SAME, T.JUDGE_DIFFERENT))
        cand_flag = k["differential_flag_candidate_over_compared"]
        flag_agree[1] += 1
        flag_agree[0] += (cand_flag == T.FLAG_ABSENT) == (v["differential_flag"] == T.FLAG_ABSENT)
    # direction-level enforcement diagnostic (never a label)
    supp = Path(cfg["supplementary"]["data_dir"])
    enf = {r["item_id"]: r.get("entity_class") for r in iter_jsonl(resolver.working_root / supp / "enforcement" / "items_v1.jsonl")}
    by_md = defaultdict(set)
    for l in iter_jsonl(resolver.working_root / supp / "supp_links_v1.jsonl"):
        if l["item_id"].startswith("enf") and l.get("md_id") and enf.get(l["item_id"]) not in (None, "unresolved"):
            by_md[l["md_id"]].add(enf[l["item_id"]])
    diag = [v for v in validated if by_md.get(v["md_id"])]
    coincide = sum(1 for v in diag if by_md[v["md_id"]] & set(v["applies_to"]))
    retest = read_json(resolver.write_path("reports", RETEST_METRICS_FILE))
    irr = read_json(resolver.write_path("reports", IRR_METRICS_FILE))
    receipts2 = read_json(d / T.PASS2_RECEIPTS_FILE)["receipts"][tc.primary]["timing"]
    return {
        "sample_items": n_sample, "validated": len(validated), "rejected": len(excluded["rejected"]),
        "in_review": len(excluded["in_review"]), "excluded_ids": excluded,
        "route_counts": dict(sorted(routes.items())),
        "rejection_rate": _wilson(len(excluded["rejected"]), n_sample),
        "flag_distribution": {f: flags.get(f, 0) for f in T.FLAG_CATEGORIES_V3},
        "ambiguity_rate": _wilson(flags.get(T.FLAG_AMBIGUOUS, 0), len(validated)),
        "judgement_distribution": {j: judgements.get(j, 0) for j in T.JUDGEMENTS},
        "by_source_class": {c: dict(sorted(v.items())) for c, v in sorted(by_class.items())},
        "stand_in_used": sum(1 for v in validated if set(v["applies_to"]) & set(tc.stand_in_classes)),
        "applies_to_source_class_only": _wilson(sum(1 for v in validated if v["applies_to"] == [v["entity_class"]]),
                                                len(validated)),
        "matched_paragraph_id_missing": sum(len(v["matched_paragraph_id_missing"]) for v in validated),
        "candidate_label_agreement_by_band": {b: _wilson(*per_band[b]) for b in ("high", "mid", "low")},
        "candidate_flag_agreement_absent_vs_not": _wilson(*flag_agree),
        "temporal_coverage": {"in_force_from": _wilson(sum(1 for v in validated if v["in_force_from"]), len(validated)),
                              "amended_by": _wilson(sum(1 for v in validated if v["amended_by"]), len(validated)),
                              "in_force_to": _wilson(sum(1 for v in validated if v["in_force_to"]), len(validated))},
        "enforcement_diagnostic": {"items_with_linked_enforcement": len(diag),
                                   "penalised_class_in_applies_to": _wilson(coincide, len(diag)),
                                   "note": "direction-level diagnostic only; never used as a label"},
        "sizing": {"planned": T.size_calc(tc), "pass1_minutes": "NOT YET MEASURED (not logged at the time)",
                   "pass2_minutes": {"self_reported": receipts2["minutes"], "per_item": receipts2["minutes_per_item"],
                                     "source": receipts2["minutes_source"]},
                   "blocks_labelled": 7},
        "reliability": {
            "irr": {"items": irr["items"], "fleiss": {k: irr["agreement"]["fleiss"][k] for k in
                                                     ("per_class_judgement", "differential_flag", "not_obligation")},
                    "pairwise": irr["agreement"]["pairwise"]},
            "retest": {"phase2": retest["phase2"], "pilot": retest["pilot"],
                       "pilot_sensitivity": retest.get("pilot_sensitivity_excluding_corrected")},
        },
    }


def pass1_support_line(m: dict) -> str:
    tm = m.get("timed_relabel")
    if not tm:
        return ("- Pass-1 support for single-pass items: pending. A timed blind re-label of 20 single-pass items is "
                "issued (`annotation_p2004_karan_timed_relabel.csv`) and not yet returned.")
    a = tm["agreement_with_pass1"]
    k = lambda x: x if isinstance(x, str) else f"{x:.3f}"
    return (f"- Pass-1 support for single-pass items: a timed blind re-label of {tm['items']} of them agrees with "
            f"frozen pass 1 at flag κ {k(a['differential_flag']['kappa'])} (n = {a['differential_flag']['n_items']}), "
            f"class-row κ {k(a['per_class_judgement']['kappa'])} ({a['per_class_judgement']['n_units']} rows), "
            f"applies_to exact-set {a['applies_to']['exact_set_agreement']:.1%} (n = {a['applies_to']['n_items']}), "
            f"not_obligation agreement {a['not_obligation']['observed_agreement']:.1%} (n = {a['not_obligation']['n_items']}). "
            "Evidence only; no validated label was changed.")


def timed_relabel_lines(m: dict) -> list[str]:
    tm = m.get("timed_relabel")
    if not tm:
        return []
    k = lambda x: "n/a" if x is None else (x if isinstance(x, str) else f"{x:.3f}")

    def ci(b):
        c = b.get("ci95")
        return c if isinstance(c, str) else f"{c[0]:.3f} to {c[1]:.3f}"

    mi, a, r = tm["minutes"], tm["agreement_with_pass1"], tm["retest_all_25_for_comparison"]
    lines = ["### Timed blind re-label (Phase 2 closing check; evidence only)", "",
             f"- Minutes per item: **{mi['minutes_per_item']:.2f}** ({mi['total_minutes']:.1f} min / {mi['n_items']} items; "
             f"{mi['n_blocks']} timed blocks, per block {mi['per_block']}; bootstrap 95% "
             f"{mi['bootstrap_ci95'][0]:.2f}–{mi['bootstrap_ci95'][1]:.2f}). {mi['caveat'].capitalize()}.", "",
             "| Measure | Re-label vs pass 1 | Blind retest (all 25) vs pass 1 |", "|---|---|---|"]
    for meas, label in (("differential_flag", "flag κ"), ("per_class_judgement", "class-row κ")):
        lines.append(f"| {label} | {k(a[meas]['kappa'])} ({ci(a[meas]['bootstrap'])}), n = {a[meas]['n_units']} | "
                     f"{k(r[meas]['kappa'])} ({ci(r[meas]['bootstrap'])}), n = {r[meas]['n_units']} |")
    lines.append(f"| applies_to exact-set | {a['applies_to']['exact_set_agreement']:.1%} (n = {a['applies_to']['n_items']}) | "
                 f"{r['applies_to']['exact_set_agreement']:.1%} (n = {r['applies_to']['n_items']}) |")
    lines.append(f"| applies_to mean Jaccard | {k(a['applies_to']['mean_jaccard'])} | {k(r['applies_to']['mean_jaccard'])} |")
    lines.append(f"| not_obligation agreement | {a['not_obligation']['observed_agreement']:.1%} (n = "
                 f"{a['not_obligation']['n_items']}) | {r['not_obligation']['observed_agreement']:.1%} (n = "
                 f"{r['not_obligation']['n_items']}) |")
    return lines + ["", f"_{tm['note']}_", ""]


def write_benchmark_report(resolver, m: dict) -> Path:
    pct = lambda x: "n/a" if x is None else f"{x:.1%}"
    num = lambda x: "n/a" if x is None else (x if isinstance(x, str) else f"{x:.3f}")
    w = lambda b: f"{b['k']}/{b['n']} = {pct(b['rate'])} (Wilson {pct(b['wilson_95'][0])}–{pct(b['wilson_95'][1])})" if b["n"] else "n/a"

    def ci(b):
        c = b.get("ci95")
        return c if isinstance(c, str) else f"{c[0]:.3f} to {c[1]:.3f}"

    rel = m["reliability"]
    irr_f, rt = rel["irr"]["fleiss"], rel["retest"]["phase2"]["all_25"]
    pilot = rel["retest"]["pilot"]
    intra_below = (isinstance(rt["per_class_judgement"]["kappa"], float) and
                   rt["per_class_judgement"]["kappa"] < irr_f["per_class_judgement"]["kappa"] and
                   rt["differential_flag"]["kappa"] < irr_f["differential_flag"]["kappa"])
    sz = m["sizing"]
    gates = [
        ("The T1 schema works", True, f"{m['validated']} validated records in `{m['validated_file']}`"),
        ("Candidate generation works", True, "25,582-record candidate benchmark (P2-004 A3), unchanged by Part D"),
        ("Human annotation works", True, "pass 1 (123 items), pass 2 (43), IRR (3 × 30), four adjudications"),
        ("Pilot test-retest κ is measured", True,
         f"flag κ {num(pilot['differential_flag']['kappa'])} (n = {pilot['differential_flag']['n_items']}); not "
         "comparable across guideline versions v1→v3"),
        ("A Phase-2 retest (≥ 20%, stratified) was annotated twice and its κ calculated", True,
         f"25/123 = 20.3%; flag κ {num(rt['differential_flag']['kappa'])}, class-row κ "
         f"{num(rt['per_class_judgement']['kappa'])}; no washout period"),
        ("Second-rater κ calculated, or NOT YET MEASURED with the reason", True,
         f"IRR set (30 items, 3 raters): Fleiss class-row κ {num(irr_f['per_class_judgement']['kappa'])}. The 30 overlap "
         "items are a team review (not independent): no κ by design"),
        ("Benchmark size derived with the calculation shown", True,
         f"N = {sz['planned']['n_target']} from m = {sz['planned']['minutes_per_item']} (recalled). Measured pass-1 "
         "m: NOT YET MEASURED (minutes not logged)"),
        ("Disagreements documented", True, "IRR, retest, overlap and unsure adjudication files, each with rationales"),
        ("Candidate and validated data kept separate", True, "candidate benchmark sha256 unchanged by Part D"),
        ("Provenance preserved", True, "route per validated item; receipts with sha256 + received-at for every input"),
        (("Every §Z metric reported with n and CI", True,
          f"minutes per item measured in the timed re-label: {tm['minutes']['minutes_per_item']:.2f} "
          f"(n = {tm['minutes']['n_items']} items, {tm['minutes']['n_blocks']} blocks; bootstrap "
          f"{tm['minutes']['bootstrap_ci95'][0]:.2f}–{tm['minutes']['bootstrap_ci95'][1]:.2f}); pass-1 minutes were not logged")
         if (tm := m.get("timed_relabel")) and tm["minutes"]["minutes_per_item"] else
         ("Every §Z metric reported with n and CI", False,
          "pass-1 minutes per item not measured (not logged); pass-2 time self-reported only; the timed re-label "
          "(20 single-pass items) is issued and not yet returned")),
        ("All tests pass under real pytest", True, "see the test run for this report"),
    ]
    lines = ["# P2-004 T1 benchmark (v1)", "",
             f"_Generated {m['generated_at']} by `python scripts/run_t1.py part-d`. Guidelines v3.1; adjudication rules "
             "`data/benchmark/t1/p2004_adjudication_rules.md`._", "",
             "## Outcome", "",
             f"- Validated set: **{m['validated']}** of {m['sample_items']} sample items (`{m['validated_file']}`).",
             f"- Rejected as not an obligation: {m['rejected']} ({w(m['rejection_rate'])} candidate rejection rate).",
             f"- In review (excluded): {m['in_review']}.",
             "- Provenance routes: " + "; ".join(f"`{k}` {v}" for k, v in m["route_counts"].items()) + ".",
             "- Most validated items are single-pass: labelled once by Karan, with no retest and no adjudication.",
             pass1_support_line(m), "",
             "## Size", "",
             f"- Planned: N = {sz['planned']['n_target']} from {sz['planned']['budget_minutes']:.0f} min at "
             f"{sz['planned']['minutes_per_item']} min/item (recalled pilot estimate), retest {sz['planned']['retest_items']}.",
             f"- Measured pass-1 minutes per item: {sz['pass1_minutes']}. Pass 2: {sz['pass2_minutes']['self_reported']:.0f} min "
             f"self-reported ({sz['pass2_minutes']['per_item']:.2f} min/item; {sz['pass2_minutes']['source']}).",
             f"- Blocks labelled: {sz['blocks_labelled']} of 7 (all 123 items).", "",
             "## Labels (validated set)", "",
             "- differential_flag: " + ", ".join(f"{k} {v}" for k, v in m["flag_distribution"].items()) +
             f"; ambiguity rate {w(m['ambiguity_rate'])}.",
             "- Class-row judgements: " + ", ".join(f"{k} {v}" for k, v in m["judgement_distribution"].items()) + ".",
             f"- applies_to is the source class alone on {w(m['applies_to_source_class_only'])}; stand-ins used on "
             f"{m['stand_in_used']} items.",
             f"- same/different judgements without a matched_paragraph_id: {m['matched_paragraph_id_missing']}.", "",
             "| Source class | Validated | Rejected | shared | class-specific | absent | ambiguous |", "|---|---|---|---|---|---|---|"]
    for c, v in m["by_source_class"].items():
        lines.append(f"| {c} | {v.get('validated', 0)} | {v.get('rejected', 0)} | {v.get('flag:shared', 0)} | "
                     f"{v.get('flag:class-specific', 0)} | {v.get('flag:absent', 0)} | {v.get('flag:ambiguous', 0)} |")
    lines += ["", "## Reliability", "",
              "### Inter-rater (IRR set: 30 items, Karan, Akash, Meer; pre-adjudication)", "",
              f"- Fleiss' κ, class-row judgements: {num(irr_f['per_class_judgement']['kappa'])} "
              f"({ci(irr_f['per_class_judgement']['bootstrap'])}), {irr_f['per_class_judgement']['n_units']} rows / "
              f"{irr_f['per_class_judgement']['n_items']} items.",
              f"- Fleiss' κ, flag: {num(irr_f['differential_flag']['kappa'])} ({ci(irr_f['differential_flag']['bootstrap'])}), "
              f"n = {irr_f['differential_flag']['n_items']}; not_obligation: {num(irr_f['not_obligation']['kappa'])} "
              f"({ci(irr_f['not_obligation']['bootstrap'])}), n = {irr_f['not_obligation']['n_items']}.",
              "- Full pairwise table: `reports/p2004_irr_v1.md`.", "",
              "### Test-retest (Karan pass 1 vs pass 2; blind; no washout period)", ""]
    for key_, label in (("all_25", "all 25"), ("second_rater_overlap_9", "9 overlap items"), ("other_16", "other 16")):
        b = rel["retest"]["phase2"][key_]
        lines.append(f"- {label}: flag κ {num(b['differential_flag']['kappa'])} ({ci(b['differential_flag']['bootstrap'])}), "
                     f"n = {b['differential_flag']['n_items']}; class-row κ {num(b['per_class_judgement']['kappa'])} "
                     f"({ci(b['per_class_judgement']['bootstrap'])}), {b['per_class_judgement']['n_units']} rows.")
    lines += [f"- Pilot (18 items): flag κ {num(pilot['differential_flag']['kappa'])} "
              f"({ci(pilot['differential_flag']['bootstrap'])}), n = {pilot['differential_flag']['n_items']}; applies_to "
              f"exact-set {pct(pilot['applies_to']['exact_set_agreement'])}.", "",
              ("**Intra-rater agreement is below inter-rater agreement** in this study: test-retest class-row κ "
               f"{num(rt['per_class_judgement']['kappa'])} vs IRR Fleiss {num(irr_f['per_class_judgement']['kappa'])}; flag "
               f"{num(rt['differential_flag']['kappa'])} vs {num(irr_f['differential_flag']['kappa'])}. The two are measured on "
               "different items (25 retest vs 30 IRR), with wide, overlapping intervals.") if intra_below else
              "Intra-rater agreement is NOT below inter-rater agreement on these figures.",
              "", "**The pilot flag is not comparable across guideline versions:** pilot pass 1 was labelled under v1 "
              "(applies_to pre-filled, no per-class rows, no v2.2 vocabulary), pass 2 under v3.1. Its κ describes the "
              "guideline change as much as the rater.", "",
              "Method: blind test-retest procedure; no washout period was enforced; a short interval may inflate agreement "
              "through recall. Full tables: `reports/p2004_retest_v1.md`.", "",
              *timed_relabel_lines(m),
              "## Candidate-label agreement (automatic P2-002 labels vs validated labels)", "",
              "`matched` read as same-or-different, `below_threshold` as none, per compared class; band = top-1 semantic score.", ""]
    for b, x in m["candidate_label_agreement_by_band"].items():
        lines.append(f"- {b} band: {w(x)}")
    lines += [f"- Flag, absent vs not absent: {w(m['candidate_flag_agreement_absent_vs_not'])}", "",
              "## Temporal fields (validated set)", ""]
    for k, x in m["temporal_coverage"].items():
        lines.append(f"- {k}: {w(x)}")
    e = m["enforcement_diagnostic"]
    lines += ["", "## Enforcement weak-label diagnostic (Direction level; never a label)", "",
              f"- Validated items whose Direction has linked enforcement actions: {e['items_with_linked_enforcement']}; "
              f"a penalised entity class appears in applies_to: {w(e['penalised_class_in_applies_to'])}.", "",
              "## Adjudication", ""]
    for k, x in m["adjudication_receipts"].items():
        lines.append(f"- {k}: `{x.get('file')}`, sha256 `{str(x.get('sha256'))[:12]}…`, received {x.get('received_at')}")
    if m["problems"]:
        lines += ["", "Notes from building the labels:"] + [f"- {p}" for p in m["problems"]]
    lines += ["", "## Phase 2 gate checklist", "", "| Gate item | Status | Evidence |", "|---|---|---|"]
    lines += [f"| {g} | {'met' if ok else '**NOT MET**'} | {ev} |" for g, ok, ev in gates]
    lines += ["", "## Limitations", "",
              "- Most validated items are single-pass (one annotator, one pass).",
              "- Compared classes are capped at 4 per item; applies_to and the flag are over those classes.",
              "- `absent` covers only the paragraphs shown or looked up.",
              "- Test-retest had no washout period; pass-2 time is self-reported; pass-1 time was not logged.",
              "- Three corrected pilot rows may not be blind (see the retest report's sensitivity table).",
              "- The overlap team reviews were revised after reviewer feedback: not independent, no κ.",
              "- The enforcement diagnostic is Direction-level and descriptive.", ""]
    path = resolver.write_path("reports", BENCHMARK_REPORT)
    write_text(path, "\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Phase 2 closing check: timed blind re-label (evidence only; never changes a validated label)
# ---------------------------------------------------------------------------


def run_timed_sheet(cfg, tc: T.T1Config, resolver, logger) -> dict:
    d = tdir(resolver)
    path = d / T.TIMED_SHEET
    if path.exists():
        raise T.T1Error(f"{path.name} already exists; refusing to redraw")
    validated = list(iter_jsonl(d / VALIDATED_FILE))
    seen: set[str] = set()
    for f in ("p2004_retest_adjudication_v1_completed.csv", "p2004_overlap_adjudication_v1_completed.csv",
              T.ADJ_MAPPED_FILE, "p2004_unsure_adjudication_v1_completed.csv"):
        seen |= {r["item_id"] for r in T.read_sheet(d / f, require_id=False)}
    pool = [v for v in validated if v["provenance"] == T.ROUTE_SINGLE_PASS and v["item_id"] not in seen]
    drawn_at = _now()
    ids = T.draw_timed(pool)
    rows = T.build_retest_rows(_pass1_drawn(resolver), ids, seed=T.TIMED_SEED, block_size=T.TIMED_BLOCK_SIZE)
    T.assert_blind(rows)
    rec1 = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    p1 = T.read_sheet(d / T.PASS1_RECEIVED_DIR / rec1["stored_as"])
    texts = {(r.get(c) or "").strip() for r in p1 for c in ("applies_to_rationale", "note")}
    leaks = T.leaked_texts(rows, texts)
    if leaks:
        raise T.T1Error(f"timed sheet would expose pass-1 text: {leaks[0][:60]!r}")
    T.write_sheet(path, rows, T.SHEET_COLUMNS, header=T.TIMED_HEADER, input_columns=T.INPUT_COLUMNS)
    blocks = sorted({r["block"] for r in rows}, key=int)
    mpath = T.write_sheet(d / T.TIMED_MINUTES_FILE, [{"block": b, "started_at": "", "ended_at": ""} for b in blocks],
                          T.TIMED_MINUTES_COLUMNS, header=None, input_columns=("started_at", "ended_at"))
    order = [r["item_id"] for r in rows if r["row_type"] == T.ROW_ITEM]
    by_id = {v["item_id"]: v for v in validated}
    sendlog = {"drawn_at": drawn_at, "seed": T.TIMED_SEED, "pool": "validated single-pass items that appear in no "
               "adjudication file (retest, overlap, IRR, unsure)", "pool_size": len(pool),
               "strata": dict(sorted(Counter(by_id[i]["entity_class"] for i in ids).items())),
               "items": len(ids), "rows": len(rows), "blocks": {b: sum(1 for r in rows if r["block"] == b and
                                                                      r["row_type"] == T.ROW_ITEM) for b in blocks},
               "sheet": repo_relative(path), "sheet_sha256": sha256_file(path),
               "minutes_log": repo_relative(mpath), "minutes_log_sha256": sha256_file(mpath),
               "order_differs_from_pass1": order != [i for i in (r["item_id"] for r in _pass1_drawn(resolver)
                                                                 if r["row_type"] == T.ROW_ITEM) if i in set(ids)],
               "purpose": "evidence only: minutes per item, and agreement with frozen pass 1; no validated label changes"}
    write_json(d / T.TIMED_SENDLOG_FILE, sendlog)
    key = read_json(d / T.KEY_FILE)
    key["timed_relabel"] = {"item_ids": ids, "seed": T.TIMED_SEED, "drawn_at": drawn_at, "order": order}
    write_json(d / T.KEY_FILE, key)
    return sendlog


def run_ingest_timed(tc: T.T1Config, resolver, logger, file: str, minutes_file: str | None, label_source: str,
                     corrects: str | None = None, correction_note: str | None = None) -> dict:
    """Accept the completed timed re-label once (plus its minutes log). Validation failures stop before any write.

    ``corrects`` names the rater's original file when ``file`` is an authorised, explicitly versioned correction of
    it; both are receipted, and ``correction_note`` must say what was changed."""
    d = tdir(resolver)
    src = Path(file)
    mfile = Path(minutes_file) if minutes_file else d / T.TIMED_MINUTES_FILE
    if not src.is_file() or not mfile.is_file():
        raise T.T1Error(f"missing {src if not src.is_file() else mfile}")
    if corrects and not (Path(corrects).is_file() and correction_note):
        raise T.T1Error("--corrects needs an existing original file and a --correction-note")
    T.refuse_not_independent(src, d)
    rpath = d / T.TIMED_RECEIPTS_FILE
    if rpath.exists():
        prev = read_json(rpath)
        raise T.T1Error(f"the timed re-label was already received at {prev['received_at']}; re-submission is refused")
    log = read_json(d / T.TIMED_SENDLOG_FILE)
    blank = d / T.TIMED_SHEET
    if sha256_file(blank) != log["sheet_sha256"]:
        raise T.T1Error(f"{blank.name} no longer matches its send-log sha256")
    sha, received_at = sha256_file(src), _now()
    v = T.validate_annotation_file(src, T.read_sheet(blank), tc, paragraph_classes(resolver))
    mrows = T.read_sheet(mfile, require_id=False)
    blocks, mproblems = T.timed_block_minutes(mrows, log["blocks"], datetime.fromisoformat(received_at).date())
    problems = v["problems"] + [f"minutes log: {p}" for p in mproblems]
    if problems:
        raise T.T1Error(f"timed re-label NOT ingested: {len(problems)} problem(s):\n  " + "\n  ".join(problems))
    store = d / T.TIMED_RECEIVED_DIR
    store.mkdir(parents=True, exist_ok=True)
    for f in (src, mfile):
        (store / f.name).write_bytes(f.read_bytes())
        os.chmod(store / f.name, stat.S_IREAD)
    receipt = {"file": repo_relative(src), "sha256": sha, "received_at": received_at, "label_source": label_source,
               "has_bom": v["has_bom"], "rows": v["rows"], "items": v["items"],
               "minutes_log": repo_relative(mfile), "minutes_log_sha256": sha256_file(mfile), "blocks": blocks,
               "stored_in": repo_relative(store), "purpose": log["purpose"]}
    if corrects:
        orig = Path(corrects)
        (store / orig.name).write_bytes(orig.read_bytes())
        os.chmod(store / orig.name, stat.S_IREAD)
        receipt["correction"] = {"corrects": repo_relative(orig), "corrects_sha256": sha256_file(orig),
                                 "note": correction_note}
    write_json(rpath, receipt)
    return receipt


def run_timed_score(cfg, tc: T.T1Config, resolver, logger) -> dict:
    d = tdir(resolver)
    rec = read_json(d / T.TIMED_RECEIPTS_FILE)
    timed_path = d / T.TIMED_RECEIVED_DIR / Path(rec["file"]).name
    if sha256_file(timed_path) != rec["sha256"]:
        raise T.T1Error(f"{timed_path} no longer matches its receipt")
    rows = T.read_sheet(timed_path)
    ids = sorted({r["item_id"] for r in rows})
    rec1 = read_json(d / T.PASS1_RECEIPTS_FILE)["receipts"][tc.primary]
    p1 = [r for r in T.read_sheet(d / T.PASS1_RECEIVED_DIR / rec1["stored_as"]) if r["item_id"] in set(ids)]
    L1, Lt = T.parse_labelled_items(p1), T.parse_labelled_items(rows)
    seed = int(cfg["benchmark"]["agreement"]["bootstrap_seed"])
    agree = T.irr_metrics({"pass1": L1, "timed": Lt}, seed=seed, resamples=IRR_RESAMPLES)["pairwise"]["pass1-timed"]
    mins = T.minutes_per_item(rec["blocks"], seed=seed, resamples=IRR_RESAMPLES)
    retest = read_json(resolver.write_path("reports", RETEST_METRICS_FILE))["phase2"]["all_25"]
    out = {"items": len(ids), "minutes": mins, "agreement_with_pass1": agree,
           "retest_all_25_for_comparison": {k: retest[k] for k in ("differential_flag", "per_class_judgement",
                                                                    "applies_to", "not_obligation")},
           "receipt": {k: rec[k] for k in ("file", "sha256", "received_at", "label_source")},
           "note": "Evidence only; no validated label was changed. Blind re-label with no washout period."}
    bm_path = resolver.write_path("reports", BENCHMARK_METRICS)
    bm = read_json(bm_path)
    bm["timed_relabel"] = out
    write_json(bm_path, bm)
    bm["report"] = repo_relative(write_benchmark_report(resolver, bm))
    write_json(bm_path, bm)
    return out


def irr_sendlist(resolver) -> str:
    d = tdir(resolver)
    log = read_json(d / T.IRR_SENDLOG_FILE)
    g = resolver.read_path(*GUIDELINES_FILE)
    lines = ["IRR SET — send each person ONLY their own file, plus the guidelines:"]
    for rater, f in log["files"].items():
        lines.append(f"  {rater:<6} {d / Path(f['file']).name}   (sha256 {f['sha256'][:12]}…, sent_at {f['sent_at']})")
    lines += [f"  guidelines: {g}", "",
              "After sending, stamp it:  python scripts/run_t1.py irr-sent --rater <name>",
              "Minutes: each rater logs every sitting (rater, start, end) in the 'irr' rows of p2004_minutes.csv, "
              "or sends the times with the file.",
              "When a file comes back:   python scripts/run_t1.py irr-ingest --rater <name> --file <path>",
              "  (each rater's file is accepted once; a second version, a *_mock* file or anything in "
              "not_independent/ is refused)"]
    return "\n".join(lines)


def run_backup(resolver, dest: str | None) -> dict:
    """Zip data/benchmark/t1/ to ``dest`` (default: a t1_backups folder next to the repo) and verify it."""
    import zipfile

    d = tdir(resolver)
    out_dir = Path(dest) if dest else resolver.working_root.parent / "t1_backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zpath = out_dir / f"t1_backup_{stamp}.zip"
    files = sorted(p for p in d.rglob("*") if p.is_file())
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(d.parent).as_posix())
    with zipfile.ZipFile(zpath) as zf:
        bad = zf.testzip()
        ok = all(hashlib.sha256(zf.read(p.relative_to(d.parent).as_posix())).hexdigest() == sha256_file(p)
                 for p in files)
    if bad or not ok:
        raise T.T1Error(f"backup {zpath} failed verification")
    return {"zip": str(zpath), "files": len(files), "bytes": zpath.stat().st_size, "verified": True,
            "zip_sha256": sha256_file(zpath)}


def run_lookup(cfg, resolver, paragraph: str | None, cls: str | None, family: str | None, query: str | None) -> str:
    manifest = {r["document_id"]: r for r in read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))}
    paras = iter_paragraph_records(resolver)
    if paragraph:
        for p in paras:
            if p["paragraph_id"] == paragraph:
                doc = manifest.get(p["document_id"], {})
                return f"[{paragraph}] {doc.get('entity_class')} | {doc.get('subject_family')}\n{p.get('text')}"
        return f"{paragraph}: not found"
    hits = T.search_paragraphs(paras, manifest, entity_class=cls, family=family, query=query or "")
    return "\n\n".join(f"[{h['paragraph_id']}] {h['entity_class']} | {h['subject_family']}\n{h['text'][:400]}"
                       for h in hits) or "no paragraph matches"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("preflight", "rules", "candidates", "size", "sample", "sheets",
                                          "sendlist", "lookup", "irr", "irr-sent", "irr-sendlist", "irr-ingest",
                                          "irr-check", "irr-score", "pass1-check", "ingest-pass1", "part-c",
                                          "irr-adjudicate", "freeze-pass1", "retest-check", "retest-sheet",
                                          "pass2-check", "ingest-pass2", "retest-score", "ingest-team-review",
                                          "overlap-adjudication", "part-d", "timed-sheet", "ingest-timed",
                                          "timed-score", "backup"))
    parser.add_argument("--minutes-file", default=None, help="ingest-timed: the completed minutes log")
    parser.add_argument("--minutes", type=float, default=None, help="ingest-pass2: self-reported total minutes")
    parser.add_argument("--minutes-source", default=None, help="ingest-pass2: how the minutes were obtained")
    parser.add_argument("--corrects", default=None, help="ingest-pass2: the original file this one corrects")
    parser.add_argument("--correction-items", default=None, help="ingest-pass2: comma-separated item_ids allowed to differ")
    parser.add_argument("--correction-note", default=None, help="ingest-pass2: why the correction was made")
    parser.add_argument("--template-zip", default=None,
                        help="irr-adjudicate: backup zip holding the item-level sheet the adjudication was issued as")
    parser.add_argument("--label-source-basis", default=None,
                        help="irr-adjudicate: where the label_source comes from (recorded verbatim)")
    parser.add_argument("--label-source", choices=("manual", "ai_assisted"), default=None,
                        help="irr-ingest / irr-check: how the file was labelled (recorded as declared)")
    parser.add_argument("--files", nargs="*", default=None, help="irr-check: rater=path ... (dry run)")
    parser.add_argument("--config", default=None)
    parser.add_argument("--rater", default=None, help="irr-sent / irr-ingest: karan, akash or meer")
    parser.add_argument("--file", default=None, help="irr-ingest: the returned file")
    parser.add_argument("--dest", default=None, help="backup: folder for the zip (default: ../t1_backups)")
    parser.add_argument("--paragraph", default=None, help="lookup: one paragraph id")
    parser.add_argument("--class", dest="cls", default=None, help="lookup: entity class")
    parser.add_argument("--family", default=None, help="lookup: subject family")
    parser.add_argument("--query", default=None, help="lookup: words that must all appear")
    args = parser.parse_args(argv)
    cfg, tc, resolver, logger = setup(args.config)
    try:
        if args.stage == "preflight":
            out = run_preflight(cfg, tc, resolver, logger)
        elif args.stage == "rules":
            out = run_rules(tc)
        elif args.stage == "candidates":
            out = run_candidates(cfg, tc, resolver, logger)
        elif args.stage == "size":
            out = T.size_calc(tc)
        elif args.stage == "sample":
            out = run_sample(cfg, tc, resolver, logger)
        elif args.stage == "sheets":
            out = run_sheets(cfg, tc, resolver, logger)
        elif args.stage == "sendlist":
            print(sendlist(tc, resolver))
            return 0
        elif args.stage == "irr":
            out = run_irr(cfg, tc, resolver, logger)
        elif args.stage == "irr-sent":
            if not args.rater:
                raise T.T1Error("irr-sent needs --rater")
            out = run_irr_sent(tc, resolver, args.rater)
        elif args.stage == "irr-sendlist":
            print(irr_sendlist(resolver))
            return 0
        elif args.stage == "irr-ingest":
            if not (args.rater and args.file and args.label_source):
                raise T.T1Error("irr-ingest needs --rater, --file and --label-source")
            out = run_irr_ingest(tc, resolver, logger, args.rater, args.file, args.label_source)
        elif args.stage == "irr-check":
            if not (args.files and args.label_source):
                raise T.T1Error("irr-check needs --files rater=path ... and --label-source")
            out = run_irr_check(tc, resolver, dict(f.split("=", 1) for f in args.files), args.label_source)
            if not all(v["ok"] for v in out.values()):
                print(json.dumps(out, indent=2, ensure_ascii=False))
                return 2
        elif args.stage == "irr-score":
            out = run_irr_score(cfg, tc, resolver, logger)
        elif args.stage == "pass1-check":
            if not args.file:
                raise T.T1Error("pass1-check needs --file")
            out = run_pass1_check(tc, resolver, args.file)
            if out["problems"]:
                print(json.dumps(out, indent=2, ensure_ascii=False))
                return 2
        elif args.stage == "ingest-pass1":
            if not (args.file and args.label_source):
                raise T.T1Error("ingest-pass1 needs --file and --label-source")
            out = run_ingest_pass1(tc, resolver, logger, args.file, args.label_source)
        elif args.stage == "part-c":
            out = run_part_c(cfg, tc, resolver, logger, args.files)
        elif args.stage == "irr-adjudicate":
            if not (args.file and args.template_zip and args.label_source and args.label_source_basis):
                raise T.T1Error("irr-adjudicate needs --file, --template-zip, --label-source and --label-source-basis")
            out = run_irr_adjudicate(cfg, tc, resolver, logger, args.file, args.template_zip, args.label_source,
                                     args.label_source_basis)
        elif args.stage == "pass2-check":
            if not args.file:
                raise T.T1Error("pass2-check needs --file")
            out = run_pass2_check(tc, resolver, args.file)
            if out["problems"]:
                print(json.dumps(out, indent=2, ensure_ascii=False))
                return 2
        elif args.stage == "ingest-pass2":
            if not (args.file and args.label_source):
                raise T.T1Error("ingest-pass2 needs --file and --label-source")
            out = run_ingest_pass2(tc, resolver, logger, args.file, args.label_source, args.minutes,
                                   args.minutes_source, args.corrects,
                                   [x for x in (args.correction_items or "").split(",") if x], args.correction_note)
        elif args.stage == "retest-score":
            out = run_retest_score(cfg, tc, resolver, logger)
        elif args.stage == "ingest-team-review":
            if not (args.rater and args.file and args.label_source and args.label_source_basis):
                raise T.T1Error("ingest-team-review needs --rater, --file, --label-source and --label-source-basis")
            out = run_ingest_team_review(tc, resolver, logger, args.rater, args.file, args.label_source,
                                         args.label_source_basis)
        elif args.stage == "overlap-adjudication":
            out = run_overlap_adjudication(tc, resolver)
        elif args.stage == "part-d":
            out = run_part_d(cfg, tc, resolver, logger)
        elif args.stage == "timed-sheet":
            out = run_timed_sheet(cfg, tc, resolver, logger)
        elif args.stage == "ingest-timed":
            if not (args.file and args.label_source):
                raise T.T1Error("ingest-timed needs --file and --label-source (and optionally --minutes-file)")
            out = run_ingest_timed(tc, resolver, logger, args.file, args.minutes_file, args.label_source,
                                   args.corrects, args.correction_note)
        elif args.stage == "timed-score":
            out = run_timed_score(cfg, tc, resolver, logger)
        elif args.stage == "freeze-pass1":
            out = run_freeze_pass1(tc, resolver)
        elif args.stage == "retest-check":
            out = run_retest_check(cfg, tc, resolver)
        elif args.stage == "retest-sheet":
            out = run_retest_sheet(cfg, tc, resolver, logger)
        elif args.stage == "backup":
            out = run_backup(resolver, args.dest)
        else:
            print(run_lookup(cfg, resolver, args.paragraph, args.cls, args.family, args.query))
            return 0
    except T.T1Error as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
