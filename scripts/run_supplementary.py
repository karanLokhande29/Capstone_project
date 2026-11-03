#!/usr/bin/env python3
"""CLI for P2-003 supplementary sources.

Part A (local):
    python scripts/run_supplementary.py preflight     # A1 corpus counts
    python scripts/run_supplementary.py annexes       # A2 local repeal map (no network)
    python scripts/run_supplementary.py package       # A5 p2003_code.zip + manifest
    python scripts/run_supplementary.py notebook      # A4 notebooks/phase2-p2003-supplementary.ipynb
    python scripts/run_supplementary.py checklist     # A7 Part B checklist with real paths

Harvest (normally on Kaggle, through the notebook; also runnable locally):
    python scripts/run_supplementary.py discover [--source faq]
    python scripts/run_supplementary.py fetch [--source faq] [--limit N]

Part C (local, after Kaggle):
    python scripts/run_supplementary.py ingest --zip <path/to/p2003_return.zip>
    python scripts/run_supplementary.py link
    python scripts/run_supplementary.py rule
    python scripts/run_supplementary.py sheet

Part D (local, after Karan labels the sheet):
    python scripts/run_supplementary.py score --minutes <total minutes> [--sheet-file <completed.csv>]

No LLM or embedding model is used anywhere.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import REPO_ROOT, load_config  # noqa: E402
from src.common.io_helpers import iter_jsonl, read_json, read_jsonl, write_json, write_jsonl, write_text  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver, repo_relative  # noqa: E402
from src.supplementary import alignment as AL  # noqa: E402
from src.supplementary import amendments, enforcement, faq, linking, withdrawn  # noqa: E402
from src.supplementary.common import (  # noqa: E402
    SOURCES,
    HarvestContext,
    SupplementaryConfig,
    SupplementaryError,
    supp_resolver,
    validate_payload,
)

V = "v1"
ADAPTERS = {"faq": faq, "enforcement": enforcement, "amendment": amendments, "withdrawn": withdrawn}
MARKER_CONF = {"faq": "faq", "enforcement": "enforcement", "amendment": "amendments", "withdrawn": "withdrawn"}

LINKS_FILE = f"supp_links_{V}.jsonl"
COVERAGE_FILE = f"p2003_link_coverage_{V}.json"
REPEAL_FILE = f"local_repeal_{V}.json"
METRICS_FILE = f"p2003_metrics_{V}.json"
#: Harvest metrics recomputed locally at ingest (Kaggle's copy stays in METRICS_FILE).
HARVEST_FILE = f"p2003_harvest_{V}.json"
RETURN_ZIP = "p2003_return.zip"
CODE_ZIP = "p2003_code.zip"
CODE_MANIFEST = "p2003_code_manifest.json"
UPLOAD_SUBDIR = "kaggle_upload"
REPORT_FILE = "p2003_supplementary_sources.md"
NOTEBOOK = Path("notebooks/phase2-p2003-supplementary.ipynb")
CODE_DIRS = ("src", "scripts", "config")
CODE_FILES = ("requirements.txt",)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def setup(config: str | None = None):
    cfg = load_config(config)
    sc = SupplementaryConfig.from_cfg(cfg)
    resolver = supp_resolver(PathResolver.from_config(cfg), sc)
    logger = get_logger("supplementary", cfg, resolver=resolver)
    return cfg, sc, resolver, logger


def context(cfg, sc, resolver, logger, session=None, sleep_fn=time.sleep) -> HarvestContext:
    if session is None:
        from src.scraper.rbi_scraper import build_session

        session = build_session(cfg)
    return HarvestContext(cfg=cfg, sc=sc, resolver=resolver, session=session, logger=logger, sleep_fn=sleep_fn)


def sdir(resolver: PathResolver, *parts: str) -> Path:
    path = resolver.write_dir("supplementary")
    for p in parts:
        path = path / p
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Corpus inputs and A1
# ---------------------------------------------------------------------------


def load_corpus(resolver: PathResolver) -> tuple[list[dict], dict[str, list[dict]]]:
    manifest = read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))
    by_doc: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(str(resolver.read_path("processed") / "md_*.jsonl"))):
        for row in iter_jsonl(path):
            by_doc.setdefault(row["document_id"], []).append(row)
    return manifest, by_doc


def preflight(sc: SupplementaryConfig, manifest: Sequence[Mapping], by_doc: Mapping[str, Sequence]) -> dict:
    """A1: stop if the corpus is not the P1-004 one."""
    exp = sc.expected_corpus
    classes = {m.get("entity_class_raw") for m in manifest}
    empty = sorted(m["document_id"] for m in manifest if not (m.get("title") or "").strip())
    facts = {"directions": len(manifest), "processed_documents": len(by_doc),
             "paragraphs": sum(len(v) for v in by_doc.values()), "raw_entity_classes": len(classes),
             "empty_title_directions": empty}
    problems = []
    if facts["directions"] != exp["directions"] or facts["processed_documents"] != exp["directions"]:
        problems.append(f"directions {facts['directions']} / processed {facts['processed_documents']} "
                        f"!= {exp['directions']}")
    if facts["paragraphs"] != exp["paragraphs"]:
        problems.append(f"paragraphs {facts['paragraphs']} != {exp['paragraphs']}")
    if facts["raw_entity_classes"] != exp["raw_entity_classes"]:
        problems.append(f"raw entity classes {facts['raw_entity_classes']} != {exp['raw_entity_classes']}")
    if sorted(exp.get("empty_title_directions", [])) != empty:
        problems.append(f"empty-title Directions {empty} != {sorted(exp.get('empty_title_directions', []))}")
    if problems:
        raise SupplementaryError("A1 preflight failed: " + "; ".join(problems))
    return {**facts, "passed": True}


# ---------------------------------------------------------------------------
# Harvest: discover / fetch / parse (Kaggle or local)
# ---------------------------------------------------------------------------


def run_discover(ctx: HarvestContext, sources: Sequence[str]) -> dict[str, Any]:
    out = {}
    for source in sources:
        info = ADAPTERS[source].discover(ctx)
        info["discovered_at"] = _now()
        ctx.store(source).write_discovery(info)
        out[source] = info
        ctx.logger.info("discover %s: %d items", source, info["discovered"])
    return out


def _targets(ctx: HarvestContext, source: str) -> list[dict]:
    store = ctx.store(source)
    if not store.discovery_path.is_file():
        raise SupplementaryError(f"no discovery file for {source}: run `discover` first")
    return read_json(store.discovery_path)["targets"]


def smoke(ctx: HarvestContext, discovery: Mapping[str, Mapping], n: int | None = None) -> dict[str, Any]:
    """A4 smoke: fetch ``n`` items per source; stop on 0 discovered or >= max_failure_rate failures."""
    n = n or ctx.sc.smoke_items_per_source
    result, stops = {}, []
    for source, info in discovery.items():
        summary = ADAPTERS[source].fetch(ctx, info["targets"], limit=n)
        result[source] = {"discovered": info["discovered"], **summary}
        if info["discovered"] == 0:
            stops.append(f"{source}: discovered 0 items ({info.get('listing_failure') or info.get('listing_failures')})")
        elif summary["attempted"] and summary["failure_rate"] >= ctx.sc.max_failure_rate:
            stops.append(f"{source}: smoke failure rate {summary['failure_rate']:.0%} "
                         f"({summary['failure_reasons']})")
    return {"per_source": result, "stops": stops, "ok": not stops}


def run_fetch(ctx: HarvestContext, sources: Sequence[str], limit: int | None = None) -> dict[str, Any]:
    out = {}
    for source in sources:
        out[source] = ADAPTERS[source].fetch(ctx, _targets(ctx, source), limit=limit)
    return out


def run_parse(ctx: HarvestContext, sources: Sequence[str], repeal: Mapping | None = None) -> dict[str, Any]:
    out = {}
    for source in sources:
        out[source] = (withdrawn.parse_all(ctx, repeal) if source == "withdrawn" else ADAPTERS[source].parse_all(ctx))
    return out


def audit_stored(ctx: HarvestContext, sources: Sequence[str]) -> dict[str, Any]:
    """Re-validate every stored raw page. Any bad page is a stop condition (§AB)."""
    out = {}
    for source in sources:
        store = ctx.store(source)
        marker = getattr(ctx.sc, MARKER_CONF[source])["content_marker"]
        bad, hash_mismatch = [], []
        for key, entry in sorted(store.manifest().items()):
            path = store.root / entry["raw_path"]
            data = path.read_bytes() if path.is_file() else b""
            if validate_payload(data, marker=marker):
                bad.append(key)
            if hashlib.sha256(data).hexdigest() != entry["content_hash"]:
                hash_mismatch.append(key)
        out[source] = {"stored": len(store.manifest()), "invalid_content": len(bad), "invalid_examples": bad[:5],
                       "hash_mismatch": len(hash_mismatch)}
    return out


def harvest_metrics(ctx: HarvestContext, sources: Sequence[str], parse: Mapping[str, Any]) -> dict[str, Any]:
    """§Z per-source harvest metrics from what is stored (no network)."""
    out = {}
    for source in sources:
        store = ctx.store(source)
        disc = read_json(store.discovery_path) if store.discovery_path.is_file() else {}
        items = read_jsonl(store.items_path) if store.items_path.is_file() else []
        failures = store.failures()
        reasons: dict[str, int] = {}
        for f in failures:
            reasons[f["reason"]] = reasons.get(f["reason"], 0) + 1
        eras: dict[str, int] = {}
        for it in items:
            eras[it["era"]] = eras.get(it["era"], 0) + 1
        row = {"discovered": disc.get("discovered"), "stored_pages": len(store.manifest()),
               "failures_logged": len(failures), "failure_reasons": dict(sorted(reasons.items())),
               "items": len(items), "items_by_era": dict(sorted(eras.items())),
               "discovery": {k: v for k, v in disc.items() if k != "targets"}}
        if source == "faq":
            topics = parse.get("faq", {}).get("topic_records", [])
            row["faq_topics"] = len(topics)
            row["faq_topics_without_html_items"] = [t["faq_topic_id"] for t in topics if t["status"] != "ok"]
        if source == "enforcement":
            resolved = sum(1 for it in items if it["entity_class"] and it["entity_class"] != "unresolved")
            quoted = [len(it["fields"]["quoted_titles"]) for it in items]
            classes: dict[str, int] = {}
            for it in items:
                classes[it["entity_class"]] = classes.get(it["entity_class"], 0) + 1
            row.update({"entity_class_resolved": resolved,
                        "entity_class_resolution_rate": round(resolved / len(items), 4) if items else None,
                        "entity_classes": dict(sorted(classes.items())),
                        "quoted_titles_total": sum(quoted),
                        "quoted_titles_per_release_mean": round(sum(quoted) / len(items), 3) if items else None,
                        "releases_with_no_quoted_title": sum(1 for q in quoted if q == 0),
                        "releases_with_no_cited_direction": sum(1 for it in items if not it["cited_directions"]),
                        "releases_citing_statute_only": sum(1 for it in items if not it["cited_directions"]
                                                            and it["fields"]["statutes_cited"])})
        if source == "amendment":
            row.update({"with_amended_direction_cited": sum(1 for it in items
                                                            if it["fields"]["amended_directions_cited"]),
                        "with_md_hyperlink": sum(1 for it in items if it["fields"]["linked_md_ids"]),
                        "citing_paragraph_numbers": sum(1 for it in items if it["fields"]["paragraph_refs"])})
        if source == "withdrawn":
            row["online_list_found"] = bool(disc.get("online_list_found"))
        out[source] = row
    return out


# ---------------------------------------------------------------------------
# Kaggle side (called from the notebook)
# ---------------------------------------------------------------------------


def write_return_zip(ctx: HarvestContext, out_path: Path, metrics: Mapping[str, Any]) -> Path:
    """Raw pages, parsed items, manifests, discovery and failure logs, plus the metrics file. No annotation file."""
    root = ctx.resolver.write_dir("supplementary")
    write_json(root / METRICS_FILE, metrics)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != RETURN_ZIP)
    names = [p.relative_to(root).as_posix() for p in files]
    if any("annotation_" in n for n in names):
        raise SupplementaryError("return zip would carry an annotation file")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p, n in zip(files, names):
            zf.write(p, n)
    members = zipfile.ZipFile(out_path).namelist()
    assert not any("annotation_" in n for n in members), "annotation file in the return zip"
    return out_path


# ---------------------------------------------------------------------------
# Part A: package, notebook, checklist, local repeal map
# ---------------------------------------------------------------------------


def build_code_zip(root: Path, out_dir: Path) -> dict:
    """A5: src/, scripts/, config/, requirements.txt; never data/. SHA-256 of every file in a manifest."""
    files = []
    for d in CODE_DIRS:
        for p in sorted((root / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc", ".pyo") \
                    and p.name != ".DS_Store":
                files.append(p)
    files += [root / f for f in CODE_FILES if (root / f).is_file()]
    manifest = {"prompt": "P2-003", "created_at": _now(),
                "files": {p.relative_to(root).as_posix(): sha256_file(p) for p in files}}
    if any(k.startswith("data/") for k in manifest["files"]):
        raise SupplementaryError("code zip must not contain data/")
    out_dir.mkdir(parents=True, exist_ok=True)
    zpath = out_dir / CODE_ZIP
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(root).as_posix())
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True))
    manifest["zip_sha256"] = sha256_file(zpath)
    write_json(out_dir / CODE_MANIFEST, manifest)
    (out_dir / (CODE_ZIP + ".sha256")).write_text(f"{manifest['zip_sha256']}  {CODE_ZIP}\n", encoding="utf-8")
    return {"zip": repo_relative(zpath), "zip_sha256": manifest["zip_sha256"], "files": len(files),
            "manifest": repo_relative(out_dir / CODE_MANIFEST)}


def run_annexes(sc, resolver, logger) -> dict:
    manifest, by_doc = load_corpus(resolver)
    repeal = withdrawn.local_repeal_map(by_doc)
    write_json(sdir(resolver, "withdrawn") / REPEAL_FILE, repeal)
    summary = {"annex_entries": len(repeal["annex_entries"]), "directions_with_annex": repeal["directions_with_annex"],
               "repeal_statements": len(repeal["repeal_statements"]),
               "directions_with_repeal_statement": repeal["directions_with_repeal_statement"],
               "file": repo_relative(sdir(resolver, "withdrawn") / REPEAL_FILE)}
    logger.info("local repeal map: %s", summary)
    return summary


def checklist(resolver: PathResolver, package: Mapping[str, Any] | None) -> str:
    up = sdir(resolver, UPLOAD_SUBDIR)
    zip_sha = package["zip_sha256"] if package else "(run `package` first)"
    return f"""
PART B CHECKLIST (Karan, kaggle.com, all under your own account)

1. Create -> New Dataset  rbi-oblibench-code-p2003  (Private)
   Upload: {repo_relative(up / CODE_ZIP)}
   Expected SHA-256: {zip_sha}
   (Kaggle may unpack the zip. The notebook then checks every file against MANIFEST.json instead.)
2. Create -> New Notebook -> File -> Import Notebook -> {NOTEBOOK.as_posix()}
   Settings: Internet ON. No GPU needed.
   Add Input: rbi-oblibench-code-p2003  and  rbi-oblibench-corpus-v2-karan
3. Run All interactively (not Save & Run All). Read the discovery smoke output (section 4).
   If it stops, copy the output to Claude Code. Do not re-run blindly.
   If the kernel dies mid-fetch while the session (and /kaggle/working) survives, Run All again:
   fetches resume from the per-source manifests and never re-fetch a stored page.
4. Download p2003_return.zip from /kaggle/working and put it in the repo root.
5. Back in Claude Code:  Run Part C of P2-003.md
   (Part C runs: python scripts/run_supplementary.py ingest --zip p2003_return.zip)
"""


# ---------------------------------------------------------------------------
# Part C: ingest, link, rule, sheet
# ---------------------------------------------------------------------------


def run_ingest(cfg, sc, resolver, logger, zip_path: str) -> dict:
    """C1: unpack, check every stored page against its manifest hash, re-parse locally, compare with Kaggle's items."""
    zpath = Path(zip_path)
    if not zpath.is_file():
        raise SupplementaryError(f"no return zip at {zip_path}")
    root = resolver.write_dir("supplementary")
    with zipfile.ZipFile(zpath) as zf:
        names = zf.namelist()
        if any("annotation_" in n for n in names):
            raise SupplementaryError("return zip carries an annotation file")
        if any(n.startswith("/") or ".." in Path(n).parts for n in names):
            raise SupplementaryError("return zip has an unsafe path")
        zf.extractall(root)
    ctx = context(cfg, sc, resolver, logger, session=object())
    audit = audit_stored(ctx, SOURCES)
    bad = {s: a for s, a in audit.items() if a["invalid_content"] or a["hash_mismatch"]}
    if bad:
        raise SupplementaryError(f"stored pages fail validation or their hash: {bad}")
    kaggle_items = {s: (ctx.store(s).items_path.read_bytes() if ctx.store(s).items_path.is_file() else b"")
                    for s in SOURCES}
    manifest, by_doc = load_corpus(resolver)
    pre = preflight(sc, manifest, by_doc)
    repeal = withdrawn.local_repeal_map(by_doc)
    write_json(sdir(resolver, "withdrawn") / REPEAL_FILE, repeal)
    parse = run_parse(ctx, SOURCES, repeal)
    same = {s: kaggle_items[s] == ctx.store(s).items_path.read_bytes() for s in ("faq", "enforcement", "amendment")}
    metrics = harvest_metrics(ctx, SOURCES, parse)
    write_json(root / HARVEST_FILE, metrics)
    kaggle = read_json(root / METRICS_FILE) if (root / METRICS_FILE).is_file() else {}
    return {"zip": repo_relative(zpath), "zip_sha256": sha256_file(zpath), "members": len(names), "preflight": pre,
            "audit": audit, "reparse_identical_to_kaggle": same, "harvest": metrics,
            "kaggle_counts": {s: (kaggle.get("harvest", {}).get(s, {}) or {}).get("items") for s in SOURCES}}


def load_items(resolver: PathResolver, sources: Sequence[str] = SOURCES) -> dict[str, list[dict]]:
    out = {}
    for s in sources:
        path = resolver.write_dir("supplementary") / s / f"items_{V}.jsonl"
        out[s] = read_jsonl(path) if path.is_file() else []
    return out


def run_link(cfg, sc, resolver, logger) -> dict:
    """A3 / C1: every item's citations -> link records; coverage per source and method."""
    manifest, by_doc = load_corpus(resolver)
    repeal_path = sdir(resolver, "withdrawn") / REPEAL_FILE
    repeal = read_json(repeal_path) if repeal_path.is_file() else withdrawn.local_repeal_map(by_doc)
    index = linking.LinkIndex.build(manifest, by_doc, repeal, linking=sc.linking,
                                    core_classes=cfg["matching"]["core_entity_classes"])
    items = [it for rows in load_items(resolver).values() for it in rows]
    records = linking.link_items(index, items)
    write_jsonl(sdir(resolver) / LINKS_FILE, records)
    cov = linking.coverage(items, records)
    pre_names = pre_consolidation_share(items, withdrawn_titles(items), index)
    out = {"records": len(records), "items": len(items), "fuzzy_threshold": index.threshold,
           "coverage": cov, "enforcement_quoted_titles": pre_names,
           "empty_title_directions": index.empty_title,
           "file": repo_relative(sdir(resolver) / LINKS_FILE)}
    write_json(sdir(resolver) / COVERAGE_FILE, out)
    logger.info("link: %d records over %d items", len(records), len(items))
    for source, row in cov.items():
        logger.info("link coverage %s: %s", source, {m: row[m] for m in linking.METHODS} | {"items": row["items"]})
    return out


def withdrawn_titles(items: Sequence[Mapping]) -> list[str]:
    return sorted({linking.normalise_title(it["title"]) for it in items
                   if it["source"] == "withdrawn" and it["fields"].get("origin") == withdrawn.ORIGIN_ONLINE})


def _on_withdrawn_list(key: str, withdrawn_keys: Sequence[str]) -> bool:
    """Equal to a withdrawn title, or (with 3+ content words) a whole-phrase part of one."""
    if key in withdrawn_keys:
        return True
    if len(linking.subject_tokens(key)) < 3:
        return False
    rx = re.compile(rf"(?<![\w]){re.escape(key)}(?![\w])")
    return any(rx.search(w) for w in withdrawn_keys)


def pre_consolidation_share(items: Sequence[Mapping], withdrawn_keys: Sequence[str], index: linking.LinkIndex) -> dict:
    """§Z: quoted titles in penalty releases that are pre-consolidation names.

    ``consolidated``: the title equals a manifest title or its subject equals a
    Direction's subject. ``pre_consolidation``: otherwise, it is on the online
    withdrawn list (equal, or with 3+ content words, contained in a withdrawn
    title such as "Master Circular - Management of Advances - UCBs").
    Otherwise ``unknown``.
    """
    subjects = {" ".join(sorted(d.tokens)) for d in index.directions.values() if d.tokens}
    counts = {"consolidated": 0, "pre_consolidation": 0, "unknown": 0}
    for it in items:
        if it["source"] != "enforcement":
            continue
        for q in it["fields"]["quoted_titles"]:
            key = linking.normalise_title(q)
            skey = " ".join(sorted(linking.subject_tokens(linking.subject_of(q))))
            if key in index.by_title or linking.normalise_title(q, drop_year=True) in index.by_title_no_year \
                    or skey in subjects:
                counts["consolidated"] += 1
            elif _on_withdrawn_list(key, withdrawn_keys):
                counts["pre_consolidation"] += 1
            else:
                counts["unknown"] += 1
    total = sum(counts.values())
    return {**counts, "total": total,
            "pre_consolidation_share": round(counts["pre_consolidation"] / total, 4) if total else None,
            "not_consolidated_share": round((total - counts["consolidated"]) / total, 4) if total else None}


def _paths(resolver: PathResolver) -> dict[str, Path]:
    d = sdir(resolver)
    return {"rule": d / AL.RULE_FILE, "sheet": d / AL.SHEET_FILE, "key": d / AL.KEY_FILE,
            "completed": d / AL.COMPLETED_FILE, "decisions": d / AL.DECISIONS_FILE,
            "metrics": d / AL.SCORE_FILE, "draw_log": d / AL.DRAW_LOG_FILE}


def run_rule(cfg, sc, resolver, logger, force: bool = False) -> dict:
    p = _paths(resolver)
    body = AL.write_rule(p["rule"], p["sheet"], sc.alignment["rule"], force=force)
    return {"rule_file": repo_relative(p["rule"]), **body}


def run_sheet(cfg, sc, resolver, logger, force: bool = False) -> dict:
    p = _paths(resolver)
    manifest, by_doc = load_corpus(resolver)
    items = load_items(resolver, ("faq", "enforcement"))
    links_path = sdir(resolver) / LINKS_FILE
    if not links_path.is_file():
        raise SupplementaryError("no link file: run `link` before `sheet`")
    by_item: dict[str, list] = {}
    for r in iter_jsonl(links_path):
        by_item.setdefault(r["item_id"], []).append(r)
    meta = AL.draw_sheet(items_by_source=items, links_by_item=by_item,
                         titles={m["document_id"]: m.get("title") or "" for m in manifest},
                         paragraphs_by_doc=by_doc, conf=sc.alignment, rule_path=p["rule"], sheet_path=p["sheet"],
                         key_path=p["key"], best_link=linking.best_link,
                         entity_class_of={m["document_id"]: m.get("entity_class_raw") for m in manifest},
                         function_headings=cfg["matching"]["function_headings"], force=force)
    write_json(p["draw_log"], {"drawn_at": meta["drawn_at"], "rule_created_at": meta["rule_created_at"],
                               "sheet_sha256": meta["sheet_sha256"], "rule_sha256": meta["rule_sha256"]})
    return {"sheet": repo_relative(p["sheet"]), "key": repo_relative(p["key"]), **meta}


# ---------------------------------------------------------------------------
# Part D: score, decisions, report
# ---------------------------------------------------------------------------


def run_score(cfg, sc, resolver, logger, sheet_file: str | None = None, minutes: float | None = None,
              second_raters: Mapping[str, str] | None = None, label_source: str | None = None,
              minutes_source: str | None = None) -> dict:
    p = _paths(resolver)
    manifest, by_doc = load_corpus(resolver)
    pids = {r["paragraph_id"] for rows in by_doc.values() for r in rows}
    labelled = Path(sheet_file) if sheet_file else p["completed"]
    if not labelled.is_file():
        raise SupplementaryError(f"no labelled sheet at {labelled}")
    result = AL.score_sheet(labelled_path=labelled, drawn_path=p["sheet"], key_path=p["key"], rule_path=p["rule"],
                            paragraph_ids=pids, minutes=minutes,
                            second_raters={k: Path(v) for k, v in (second_raters or {}).items()})
    result["sheet_file"] = repo_relative(labelled)
    result["label_source"] = label_source or "undeclared"
    result["minutes_source"] = minutes_source if minutes is not None else None
    key = read_json(p["key"])
    meta = key["meta"]
    populations = {"faq": ("faq:", meta["faq"]["qualifying_by_category"]),
                   "enforcement": ("enforcement:post_consolidation:", meta["enforcement"]["by_class_post"])}
    result["post_stratified"] = {
        s: AL.post_stratified(result["by_stratum"][s], pop, prefix, result["per_source"][s]["clean_rate"]["rate"],
                              result["rule"])
        for s, (prefix, pop) in populations.items()}
    result["conventions"] = AL.convention_metrics(AL.read_sheet(labelled), key["items"], result["rule"],
                                                  load_items(resolver, ("enforcement",))["enforcement"])
    write_json(p["metrics"], result)
    write_json(p["decisions"], {"decisions": list(result["decisions"].values())})
    report = write_report(resolver, result)
    return {**result, "report": repo_relative(report), "decisions_file": repo_relative(p["decisions"])}


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def _rate_str(r: Mapping[str, Any]) -> str:
    if not r or r.get("rate") is None:
        return "n/a (n = 0)"
    lo, hi = r["wilson95"]
    return f"{r['k']}/{r['n']} = {r['rate']:.1%} (Wilson 95% {lo:.1%}–{hi:.1%})"


def _code_drift(resolver: PathResolver) -> dict[str, Any]:
    """Which packaged code files differ from the zip Kaggle ran (by the upload manifest's hashes)."""
    mpath = sdir(resolver, UPLOAD_SUBDIR) / CODE_MANIFEST
    if not mpath.is_file():
        return {}
    m = read_json(mpath)
    drift = sorted(f for f, h in m["files"].items()
                   if not (REPO_ROOT / f).is_file() or sha256_file(REPO_ROOT / f) != h)
    return {"zip_sha256": m.get("zip_sha256"), "differs": drift}


def write_report(resolver: PathResolver, score: Mapping[str, Any]) -> Path:
    """D3. Every §Z metric with its n, the decisions, provenance and the limitations. No timestamps."""
    root = resolver.write_dir("supplementary")
    kaggle = read_json(root / METRICS_FILE) if (root / METRICS_FILE).is_file() else {}
    harvest = read_json(root / HARVEST_FILE) if (root / HARVEST_FILE).is_file() else kaggle.get("harvest", {})
    cov = read_json(root / COVERAGE_FILE) if (root / COVERAGE_FILE).is_file() else {}
    repeal = read_json(root / "withdrawn" / REPEAL_FILE) if (root / "withdrawn" / REPEAL_FILE).is_file() else {}
    recovery = read_json(root / "faq" / "recovery_v1.json") if (root / "faq" / "recovery_v1.json").is_file() else None
    key_meta = read_json(root / AL.KEY_FILE)["meta"]
    conv = score.get("conventions") or {}
    per, dec = score["per_source"], score["decisions"]
    crossing = [s for s, d in dec.items() if d["interval_crosses"]]
    key_items = read_json(root / AL.KEY_FILE)["items"]
    enf_eras = sorted({v["era"] for v in key_items.values() if v["source"] == "enforcement"})
    H = lambda s: harvest.get(s, {})  # noqa: E731
    faq_h, enf_h, amd_h, wdr_h = H("faq"), H("enforcement"), H("amendment"), H("withdrawn")
    enf_d, amd_d = enf_h.get("discovery", {}), amd_h.get("discovery", {})
    c = cov.get("coverage", {})
    q = cov.get("enforcement_quoted_titles", {})
    lines = [
        "# P2-003 — Supplementary sources: harvest, link, and the Week-2 alignment check", "",
        "Direction-level links and a hand-alignment check. No gold labels, no `applies_to`, no `differential_flag`. "
        "No LLM or embedding model was used. Paragraph mappings come only from the hand-labelled sheet.", "",
        "## Outcome", "",
        "| Source | Clean paragraph-map rate (Wilson 95%) | Decision under the pre-registered rule | Interval crosses |",
        "|---|---|---|---|"]
    for s, d in dec.items():
        lines.append(f"| {s} | {d['clean']}/{d['n']} = {d['rate']:.1%} ({d['wilson95'][0]:.1%}–{d['wilson95'][1]:.1%}) "
                     f"| **{d['decision']}** | {', '.join(d['interval_crosses']) or 'no line'} |")
    lines += ["", "These two rows replace Phase 1's `NOT YET MEASURED` for FAQ / enforcement alignment "
              "(Phase 1: \"FAQ index needs a second-level crawl\").", "",
              f"Rule `{key_meta['rule_file']}` (sha256 `{key_meta['rule_sha256'][:12]}…`, created "
              f"{key_meta['rule_created_at']}): clean rate ≥ 60% → paragraph-level weak label / validation; 30% – < 60% "
              "→ direction-level weak labels only; < 30% → validation / motivation only. The point estimate decides. "
              "With n ≈ 30 a Wilson 95% interval is roughly ±17 points. Intervals that cross a decision line: "
              + (", ".join(crossing) + " (that decision is not secure against sampling error)." if crossing
                 else "none."),
              "", f"Label source: **{score.get('label_source', 'undeclared')}** (one rater). Minutes per item: "
              + (f"{score['minutes_per_item']} ({score['minutes_total']} min total over {score['n']} items; source: "
                 f"{score.get('minutes_source') or 'undeclared'})." if score.get("minutes_per_item")
                 is not None else "not recorded (re-run `score --minutes N` to add it; nothing else changes)."),
              "", "## Harvest (Kaggle, Internet on, rate limit "
              f"{(kaggle.get('kaggle') or {}).get('rate_limit_sec', '?')} s)", "",
              "| Source | Discovered | Stored pages | Failures (reason) | Parsed items | Items by era |",
              "|---|---|---|---|---|---|"]
    for s in SOURCES:
        h = H(s)
        lines.append(f"| {s} | {h.get('discovered')} | {h.get('stored_pages')} | {h.get('failures_logged')} "
                     f"{h.get('failure_reasons') or ''} | {h.get('items')} | {h.get('items_by_era')} |")
    audit = kaggle.get("audit", {})
    lines += ["", f"- Stored pages re-validated: {sum(a.get('stored', 0) for a in audit.values())} on Kaggle, all again "
              "at ingest; **0 CAPTCHA or error pages stored** (tests `test_captcha_is_never_stored_and_is_counted`, "
              "`test_end_to_end`).",
              f"- FAQ: {faq_h.get('faq_topics')} topics → {faq_h.get('items')} Q&A items. Topics with no HTML Q&A "
              f"(content only in a PDF, or no question markup): {faq_h.get('faq_topics_without_html_items')}.",
              f"- Enforcement: {enf_d.get('press_releases_listed')} press releases listed for the configured years; "
              f"{enf_h.get('items')} monetary-penalty releases ({(enf_h.get('items_by_era') or {}).get('post_consolidation')} "
              f"post-, {(enf_h.get('items_by_era') or {}).get('pre_consolidation')} pre-consolidation). Near misses excluded: "
              f"{enf_d.get('near_misses_excluded')} {enf_d.get('near_miss_by_pattern')}.",
              f"- Entity class resolved for {enf_h.get('entity_class_resolved')}/{enf_h.get('items')} = "
              f"{(enf_h.get('entity_class_resolution_rate') or 0):.1%}: {enf_h.get('entity_classes')}.",
              f"- Quoted titles: {enf_h.get('quoted_titles_total')} in {enf_h.get('items')} releases "
              f"(mean {enf_h.get('quoted_titles_per_release_mean')}); {enf_h.get('releases_with_no_quoted_title')} releases "
              f"quote none; {enf_h.get('releases_with_no_cited_direction')} cite no Direction at all, "
              f"{enf_h.get('releases_citing_statute_only')} of them only a statute.",
              f"- Quoted titles that are pre-consolidation names: {q.get('pre_consolidation')}/{q.get('total')} = "
              f"{(q.get('pre_consolidation_share') or 0):.1%} (on the online withdrawn list); consolidated names "
              f"{q.get('consolidated')}/{q.get('total')}; unknown {q.get('unknown')}/{q.get('total')}.",
              f"- Amendment Directions (≥ 2025-11-28): {amd_h.get('items')} of {amd_d.get('notifications_listed')} "
              f"notifications listed; near misses {amd_d.get('near_misses_excluded')}. Target Direction cited in the body: "
              f"{amd_h.get('with_amended_direction_cited')}/{amd_h.get('items')}; linked to a Direction: "
              f"{(c.get('amendment') or {}).get('linked')}/{(c.get('amendment') or {}).get('items')}; citing paragraph "
              f"numbers: {amd_h.get('citing_paragraph_numbers')}/{amd_h.get('items')}.",
              f"- Repeal map (local): {len(repeal.get('annex_entries', []))} annex entries in "
              f"{repeal.get('directions_with_annex')} Directions; {len(repeal.get('repeal_statements', []))} "
              f"\"stand repealed\" statements in {repeal.get('directions_with_repeal_statement')} Directions. Online "
              f"withdrawn list found: {wdr_h.get('online_list_found')} "
              f"({wdr_h.get('discovery', {}).get('discovered')} circulars; it names no replacing Direction).",
              f"- Charges not parsed: {(conv.get('enforcement_charges_none_parsed') or {}).get('k')}/"
              f"{(conv.get('enforcement_charges_none_parsed') or {}).get('n')} releases (see Limitations).",
              "", "## Direction-level link coverage (A3)", "",
              f"`title_fuzzy` threshold {cov.get('fuzzy_threshold')} (config, fixed in Part A before any labelling). "
              "Each item counts once, by its best link.", "",
              "| Source | Items | exact_ref | repeal_map | title_fuzzy | none | Linked | Fuzzy margin n / min / median / max / zero |",
              "|---|---|---|---|---|---|---|---|"]
    for s, row in c.items():
        m = row["fuzzy_margin"]
        lines.append(f"| {s} | {row['items']} | {row['exact_ref']} | {row['repeal_map']} | {row['title_fuzzy']} | "
                     f"{row['none']} | {row['linked']}/{row['items']} = {_pct(row['link_rate'])} | "
                     f"{m['n']} / {m['min']} / {m['median']} / {m['max']} / {m['zero_margin']} |")
    lines += ["", "A zero margin means the same subject exists for several entity classes and the item had no "
              "resolved class (FAQ, withdrawn list); the tie is broken by the configured class order.", "",
              "## Alignment check (C3 / D1)", "",
              f"Seed {key_meta['seed']}. FAQ: {key_meta['faq']['qualifying']} of {key_meta['faq']['eligible']} items "
              f"qualify under the deterministic cue filter; 30 drawn, round-robin across categories. Enforcement: "
              f"{key_meta['enforcement']['post_consolidation']} post-consolidation releases (preferred) and "
              f"{key_meta['enforcement']['pre_consolidation']} pre-consolidation; 30 drawn, round-robin across entity "
              f"classes; eras drawn: {', '.join(enf_eras)}. Candidate pools: {key_meta.get('candidate_pools')}.", "",
              "| Source | n | paragraph | multi_paragraph | direction_only | wrong_direction | unanchored | Clean rate | "
              "paragraph + multi | Direction-link precision (locked) | Candidate-hit share |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s, m in per.items():
        d = m["label_distribution"]
        lines.append(f"| {s} | {m['n']} | {d['paragraph']} | {d['multi_paragraph']} | {d['direction_only']} | "
                     f"{d['wrong_direction']} | {d['unanchored']} | {_rate_str(m['clean_rate'])} | "
                     f"{_rate_str(m['paragraph_or_multi_rate'])} | {_rate_str(m['direction_link_precision'])} | "
                     f"{_rate_str(m['candidate_hit_share'])} |")
    lines += ["", "Locked direction-link precision: over items that had a link and were not labelled `unanchored`, "
              "the share not labelled `wrong_direction`. Candidate-hit share: chosen paragraph ids that were among the "
              "8 shown candidates.", "", "### Candidate-hit share by candidate pool", "",
              "Linked rows offer the linked Direction's paragraphs; rows with no linked Direction offer a corpus-wide "
              "TF-IDF search (within the item's entity class plus function-heading Directions, or all Directions).",
              "", "| Source | Pool | Items | Candidate-hit share |", "|---|---|---|---|"]
    for s, m in per.items():
        for pool, rate in m["candidate_hit_share_by_pool"].items():
            lines.append(f"| {s} | {pool} | {m['items_by_pool'][pool]} | {_rate_str(rate)} |")
    if conv:
        lines += ["", "### Scoring conventions (fixed by Karan before any rate was seen)", "",
                  "1. Primary clean rate = label `paragraph` as labelled (the locked rule; it decides). Strict rate also "
                  "excludes `paragraph` rows whose note says \"partial\".",
                  "2. Strict direction-link precision, over rows that had a link: wrong if `wrong_direction`, a chosen "
                  "paragraph outside the linked Directions, `unanchored` despite a link, or a `direction_only` note "
                  "naming only other Directions; a `direction_only` note naming a linked md_id (or none) is correct.",
                  "", "| Source | Strict clean rate | Band (same as primary?) | \"partial\" notes | \"uncertain\" notes | "
                  "Strict link precision | Link verdicts (n) |", "|---|---|---|---|---|---|---|"]
        for s, cc in conv["per_source"].items():
            verdicts = "; ".join(f"{k} {v}" for k, v in cc["link_verdicts"].items())
            lines.append(f"| {s} | {_rate_str(cc['strict_clean_rate'])} | {cc['strict_decision']} "
                         f"({'same' if cc['strict_same_band'] else 'different'}) | {cc['partial_notes']} | "
                         f"{cc['uncertain_notes']} | {_rate_str(cc['link_precision_strict'])} | {verdicts} |")
    lines += ["", "### By stratum", "", "| Stratum | n | paragraph | multi | direction_only | wrong_direction | "
              "unanchored |", "|---|---|---|---|---|---|---|"]
    for s in per:
        for stratum, b in score["by_stratum"][s].items():
            d = b["label_distribution"]
            lines.append(f"| {stratum} | {b['n']} | {d['paragraph']} | {d['multi_paragraph']} | {d['direction_only']} | "
                         f"{d['wrong_direction']} | {d['unanchored']} |")
    ps = score.get("post_stratified")
    if ps:
        lines += ["", "### Sensitivity: post-stratified clean rate", "",
                  "The labelled sheet was drawn with equal (round-robin) allocation across strata; it was not redrawn. "
                  "This sensitivity weights each sampled stratum's observed clean rate by its population share "
                  "(FAQ: qualifying items per category; enforcement: post-consolidation releases per entity class). "
                  "Strata with population but no sampled row are excluded from the weights and listed. The weighted "
                  "rate is a **point estimate; no interval is computed**. The locked primary decision is unchanged."]
        for s, r in ps.items():
            lines += ["", f"**{s}**: weighted clean rate **{r['weighted_clean_rate']:.1%}** → {r['weighted_decision']} "
                      f"({'same band as' if r['same_band_as_primary'] else 'different band from'} the primary "
                      f"{r['primary_decision']}). Population covered by sampled strata: {r['population_covered']}/"
                      f"{r['population_total']} = {r['population_covered_share']:.1%}.", "",
                      "| Stratum | Population | Share | Sampled n | Clean | Rate |", "|---|---|---|---|---|---|"]
            for row in r["strata"]:
                lines.append(f"| {row['stratum']} | {row['population']} | {row['population'] / r['population_total']:.1%} "
                             f"| {row['sampled']} | {row['clean']} | {row['rate']:.1%} |")
            for u in r["unsampled_strata"]:
                lines.append(f"| {u['stratum']} (not sampled, excluded) | {u['population']} | {u['share']:.1%} | 0 | – | – |")
            if r["sampled_strata_without_population"]:
                lines.append(f"\nSampled strata with no population entry: {r['sampled_strata_without_population']}.")
    lines += ["", "Inter-rater agreement: " + (json.dumps(score["kappa"]) if score.get("kappa")
                                                else "not measured (the optional second-rater subset was not labelled).")]
    drift = _code_drift(resolver)
    k = kaggle.get("kaggle") or {}
    lines += ["", "## Provenance", "",
              f"- Kaggle run: {k.get('runtime_sec')} s; code {k.get('code_source')}; versions {k.get('versions')}.",
              f"- Uploaded code zip sha256 `{drift.get('zip_sha256')}`. Code files that differ from it now: "
              f"{', '.join(f'`{f}`' for f in drift.get('differs', [])) or 'none'}. `alignment.py` and "
              "`run_supplementary.py` changed for the Part C sheet fix and Part D scoring (never called on Kaggle); "
              "`common.py` changed for the validator fix below."]
    if recovery:
        lines.append(f"- FAQ topic {int(recovery['item_key'].split('_')[-1])} was rejected on Kaggle as `captcha`. "
                     f"Diagnosis: {recovery['diagnosis']}. Fix: {recovery['fix']}. Re-fetched locally "
                     f"on Karan's decision ({recovery['recovered']['retrieved_at']}, sha256 "
                     f"`{recovery['recovered']['content_hash'][:12]}…`), recovering {recovery['items_recovered']} items. "
                     "The Kaggle failure record is kept in the log.")
    lines += ["", "## Limitations", "",
              "- **n ≈ 30 per source, one rater.** Wilson intervals are about ±17 points"
              + (f"; {', '.join(crossing)} cross a decision line" if crossing else "")
              + ". No agreement figure exists unless the optional second-rater subset is labelled.",
              "- **Equal allocation across strata.** Categories and entity classes got round-robin (near-equal) slots, "
              "not slots proportional to their size, so each rate is stratum-balanced, not population-weighted. Small "
              "strata (e.g. an FAQ category with 3 qualifying items) weigh as much as large ones.",
              f"- **Enforcement sample eras: {', '.join(enf_eras)}.** "
              f"{key_meta['enforcement']['pre_consolidation']} pre-consolidation releases were harvested and counted"
              + (" but not labelled; their alignment may be lower, since they cite pre-consolidation instruction names."
                 if enf_eras == ["post_consolidation"] else "."),
              "- **FAQ items were filtered** to answers with a requirement cue and a regulated-entity cue "
              f"({key_meta['faq']['qualifying']} of {key_meta['faq']['eligible']}); the rate describes those, not all FAQ content (much of which covers schemes and "
              "markets with no Master Direction).",
              "- **Parsers are deterministic heuristics.** Charges were not parsed for "
              f"{(conv.get('enforcement_charges_none_parsed') or {}).get('k')} releases: FEMA Authorised Dealer "
              "releases with no charge paragraph, and releases stating the charge inside the \"RBI found that the "
              "charge … was sustained\" sentence. Entity class is unresolved for "
              f"{(enf_h.get('items') or 0) - (enf_h.get('entity_class_resolved') or 0)} releases (\"ARC\" and "
              "\"Asset Care & Reconstruction\" names, \"BR Act\" abbreviations, FEMA AD-bank releases). FAQ topics "
              f"{faq_h.get('faq_topics_without_html_items')} yield no HTML Q&A.",
              "- **Linking is by title and reference only.** Pre-consolidation names often have no deterministic link; "
              "the candidate pools for unlinked rows are a retrieval aid, not a link, and their hit share is reported "
              "separately.",
              "- **This step gives direction-level evidence and source decisions only.** No supplementary source is "
              "used as a gold label here (P2-004).",
              "", "## Files for `wip/P2-003`", "",
              "- `docs/prompts/P2-003.md`",
              "- `src/supplementary/` (`__init__`, `common`, `faq`, `enforcement`, `amendments`, `withdrawn`, `linking`, "
              "`alignment`)",
              "- `scripts/run_supplementary.py`, `scripts/build_supplementary_notebook.py`",
              "- `notebooks/phase2-p2003-supplementary.ipynb`",
              "- `tests/test_supplementary_{common,sources,linking,alignment,integration}.py`, "
              "`tests/supplementary_support.py`, `tests/fixtures/supplementary/` (hand-written, no RBI text)",
              "- `reports/p2003_supplementary_sources.md`",
              "- `config/config.yaml` (`supplementary:` block), `.gitignore` (`data/supplementary/**`, `*_return.zip`)",
              "", "**Gitignored data, to back up by hand.** All of `data/supplementary/` (R6: raw RBI pages):",
              "- `kaggle_return/p2003_return.zip` (the Kaggle bundle, sha256 `0245fc80…`)",
              "- `kaggle_upload/` (`p2003_code.zip` + `.sha256` + manifest)",
              "- `faq/`, `enforcement/`, `amendment/`, `withdrawn/` (raw pages, discovery pages and logs, fetch "
              "manifests, failure logs, `items_v1.jsonl`; `faq/recovery_v1.json`; `withdrawn/local_repeal_v1.json`)",
              "- `supp_links_v1.jsonl`, `p2003_link_coverage_v1.json`, `p2003_metrics_v1.json`, `p2003_harvest_v1.json`",
              "- `p2003_alignment_rule_v1.json`, `p2003_alignment_sheet_v1.csv`, `p2003_alignment_sheet_v1_completed.csv`, "
              "`p2003_alignment_key_v1.json`, `p2003_alignment_draw_log_v1.json`, `p2003_alignment_metrics_v1.json`, "
              "`p2003_source_decisions_v1.json`", ""]
    path = resolver.write_path("reports", REPORT_FILE)
    write_text(path, "\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=("preflight", "annexes", "package", "notebook", "checklist", "discover",
                                          "fetch", "ingest", "link", "rule", "sheet", "score"))
    parser.add_argument("--config", default=None)
    parser.add_argument("--source", choices=SOURCES, default=None, help="discover/fetch: one source only")
    parser.add_argument("--limit", type=int, default=None, help="fetch: at most N items per source")
    parser.add_argument("--zip", default=None, help="ingest: path to p2003_return.zip")
    parser.add_argument("--force", action="store_true", help="rule/sheet: overwrite (never a labelled sheet)")
    parser.add_argument("--sheet-file", default=None, help="score: the labelled sheet")
    parser.add_argument("--minutes", type=float, default=None, help="score: total labelling minutes")
    parser.add_argument("--minutes-source", default=None,
                        help="score: how the minutes were obtained, e.g. timed or recalled_estimate (recorded as declared)")
    parser.add_argument("--second-rater", action="append", default=[], help="score: name=path (optional κ)")
    parser.add_argument("--label-source", choices=("manual", "ai_assisted"), default=None,
                        help="score: how the sheet was labelled (recorded as declared)")
    args = parser.parse_args(argv)
    cfg, sc, resolver, logger = setup(args.config)
    sources = [args.source] if args.source else list(SOURCES)
    try:
        if args.stage == "preflight":
            out = preflight(sc, *load_corpus(resolver))
        elif args.stage == "annexes":
            out = run_annexes(sc, resolver, logger)
        elif args.stage == "package":
            out = build_code_zip(REPO_ROOT, sdir(resolver, UPLOAD_SUBDIR))
            logger.info("code zip %s sha256=%s (%d files)", out["zip"], out["zip_sha256"], out["files"])
        elif args.stage == "notebook":
            from scripts.build_supplementary_notebook import build

            out = {"notebook": repo_relative(build(REPO_ROOT / NOTEBOOK))}
        elif args.stage == "checklist":
            mpath = sdir(resolver, UPLOAD_SUBDIR) / CODE_MANIFEST
            print(checklist(resolver, read_json(mpath) if mpath.is_file() else None))
            return 0
        elif args.stage == "discover":
            out = {s: {k: v for k, v in d.items() if k != "targets"}
                   for s, d in run_discover(context(cfg, sc, resolver, logger), sources).items()}
        elif args.stage == "fetch":
            ctx = context(cfg, sc, resolver, logger)
            out = {"fetch": run_fetch(ctx, sources, args.limit), "parse": run_parse(ctx, sources),
                   "audit": audit_stored(ctx, sources)}
        elif args.stage == "ingest":
            if not args.zip:
                raise SupplementaryError("ingest needs --zip <path to p2003_return.zip>")
            out = run_ingest(cfg, sc, resolver, logger, args.zip)
        elif args.stage == "link":
            out = run_link(cfg, sc, resolver, logger)
        elif args.stage == "rule":
            out = run_rule(cfg, sc, resolver, logger, force=args.force)
        elif args.stage == "sheet":
            out = run_sheet(cfg, sc, resolver, logger, force=args.force)
        else:
            raters = dict(s.split("=", 1) for s in args.second_rater)
            out = run_score(cfg, sc, resolver, logger, args.sheet_file, args.minutes, raters, args.label_source,
                            args.minutes_source)
    except SupplementaryError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
