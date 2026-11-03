#!/usr/bin/env python3
"""P4-001 task 1: the T3 deterministic temporal set from the P2-003 Amendment Directions.

    python3 scripts/run_t3.py build     # parse -> actions, corpus-version counts, items, spot-check sheet (seeded)
    python3 scripts/run_t3.py ingest --file <completed.csv>   # once; parse precision with a Wilson CI
    python3 scripts/run_t3.py rebuild   # after one rule fix: rebuild with the current rules and freeze the set
    python3 scripts/run_t3.py sheet2    # independent post-fix check: 10 unchecked parses behind frozen items
    python3 scripts/run_t3.py ingest --sheet 2 --file <completed.csv>   # once; no further rule changes

Outputs in data/benchmark/t3/. Deterministic rules only; no LLM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import REPO_ROOT, get_required, load_config  # noqa: E402
from src.common.io_helpers import read_json, write_json  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.t3 import build as B  # noqa: E402
from src.t3 import parser as P  # noqa: E402

V = "v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as h:
        return [json.loads(x) for x in h if x.strip()]


def _dir(resolver: PathResolver) -> Path:
    d = resolver.write_dir("benchmark") / "t3"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_inputs(cfg: dict, resolver: PathResolver):
    from src.benchmark.t1 import _parse_long_date

    amend_path = REPO_ROOT / str(get_required(cfg, "supplementary.data_dir")) / "amendment" / "items_v1.jsonl"
    amendments = {it["item_id"]: it for it in _read_jsonl(amend_path)}
    paras_by_md: dict[str, list[dict]] = {}
    text_of: dict[str, str] = {}
    for p in sorted(Path(resolver.read_path("processed")).glob("md_*.jsonl")):
        rows = sorted(_read_jsonl(p), key=lambda r: r.get("position") or 0)
        paras_by_md[p.stem] = [{"paragraph_id": r["paragraph_id"], "clause_path": r.get("clause_path")} for r in rows]
        for r in rows:
            text_of[r["paragraph_id"]] = r["text"]
    manifest = {r["document_id"]: r for r in _read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))}
    issue = {}
    for md, rows in paras_by_md.items():
        first = text_of[rows[0]["paragraph_id"]] if rows else ""
        issue[md] = _parse_long_date(first[:600])
    titles = {md: (r.get("title") or "") for md, r in manifest.items()}
    return amend_path, amendments, paras_by_md, text_of, issue, titles


def cmd_build(cfg: dict, resolver: PathResolver) -> int:
    t3 = cfg["t3"]
    d = _dir(resolver)
    sheet = d / f"t3_spotcheck_sheet_{V}.csv"
    if (d / f"t3_spotcheck_receipt_{V}.json").exists():
        raise SystemExit("STOP: the spot-check was already ingested; the set is rebuilt only by `ingest` fixes")
    amend_path, amendments, paras_by_md, text_of, issue, titles = load_inputs(cfg, resolver)
    actions, counts = [], Counter()
    for it in sorted(amendments.values(), key=lambda x: x["item_id"]):
        acts, c = P.parse_amendment(it, titles)
        actions += acts
        counts.update(c)
    (d / f"t3_actions_{V}.jsonl").write_text("".join(json.dumps(a.to_dict(), ensure_ascii=False) + "\n"
                                                    for a in actions), encoding="utf-8")
    rows, why = B.candidate_rows(actions, amendments, paras_by_md, text_of, issue)
    items, log = B.build_items(rows, n=int(t3["n_items"]), seed=int(t3["seeds"]["items"]),
                               max_per_direction=int(t3["max_items_per_direction"]), today=str(t3["today"]))
    (d / f"t3_items_{V}.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items),
                                           encoding="utf-8")
    all_versions = Counter()
    for a in actions:
        if a.md_id and a.scope in B.ITEM_SCOPES:
            for t, pids in B.target_paragraphs(a, paras_by_md).items():
                if pids:
                    all_versions[P.corpus_version(a, text_of[pids[0]], t)] += 1
    eff = Counter(P.effective_date(it)["basis"] for it in amendments.values())
    meta = {"built_utc": _now(), "amendments": len(amendments),
            "amendments_with_paragraph_refs": sum(1 for it in amendments.values() if (it.get("fields") or {}).get("paragraph_refs")),
            "amendment_source": str(amend_path.relative_to(REPO_ROOT)),
            "amendment_source_sha256": hashlib.sha256(amend_path.read_bytes()).hexdigest(),
            "instructions": dict(counts), "parsed_actions": len(actions),
            "parsed_by_type": {f"{k[0]}/{k[1]}": v for k, v in sorted(Counter((a.action, a.scope) for a in actions).items())},
            "effective_date_basis": dict(eff),
            "corpus_version_all_mapped_targets": dict(all_versions),
            "exclusions": dict(why), "items": log, "status": "draft_until_spotcheck"}
    write_json(d / f"t3_build_{V}.json", meta)

    if not sheet.exists():
        sample = B.draw_spotcheck(actions, n=int(t3["spotcheck_n"]), seed=int(t3["seeds"]["spotcheck"]))
        srows = B.sheet_rows(sample, amendments, titles)
        sheet.write_text(B.sheet_csv(srows), encoding="utf-8-sig")
        write_json(d / f"t3_spotcheck_key_{V}.json", {"created_utc": _now(), "rows": {r["row_id"]: a.to_dict()
                                                      for r, a in zip(srows, sample)},
                                                      "sheet_sha256": hashlib.sha256(sheet.read_bytes()).hexdigest(),
                                                      "by_type": dict(Counter(a.action for a in sample))})
    print(f"instructions {counts['verbs']}: parsed {counts['parsed']}, unparsed {counts['unparsed']}")
    print(f"parsed by type: {meta['parsed_by_type']}")
    print(f"corpus version (all mapped targets): {dict(all_versions)}")
    print(f"eligible (action, target) rows {len(rows)}; exclusions {dict(why)}")
    print(f"items {log['items']} from {log['directions']} Directions; sides {log['sides']}; gold {log['gold']}")
    print(f"spot-check sheet: {sheet}")
    return 0


def cmd_ingest(cfg: dict, resolver: PathResolver, file: str, sheet_no: int = 1) -> int:
    d = _dir(resolver)
    tag = "spotcheck" if sheet_no == 1 else "spotcheck2"
    receipt = d / f"t3_{tag}_receipt_{V}.json"
    if receipt.exists():
        print("REFUSED: a spot-check was already accepted; re-submissions are not accepted")
        return 1
    raw = Path(file).read_bytes()
    completed = B.read_sheet_text(raw.decode("utf-8-sig"))
    blank = B.read_sheet_text((d / f"t3_{tag}_sheet_{V}.csv").read_text(encoding="utf-8-sig"))
    problems = B.validate_sheet(completed, blank)
    if problems:
        print("REJECTED (nothing recorded):")
        for p in problems:
            print(f"  - {p}")
        return 1
    k = sum(1 for r in completed if r["correct"].strip().lower() == "yes")
    lo, hi = B.wilson(k, len(completed))
    labels = [{"row_id": r["row_id"], "correct": r["correct"].strip().lower(), "note": r.get("note", "").strip(),
               "label_source": "manual", "rater": "karan"} for r in completed]
    (d / f"t3_{tag}_labels_{V}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels), encoding="utf-8")
    (d / f"t3_{tag}_sheet_{V}_accepted.csv").write_bytes(raw)
    write_json(receipt, {"received_utc": _now(), "sha256": hashlib.sha256(raw).hexdigest(), "file": file,
                         "had_bom": raw.startswith(b"\xef\xbb\xbf"), "rows": len(labels), "label_source": "manual",
                         "precision": {"k": k, "n": len(completed), "value": k / len(completed), "wilson_95": [lo, hi]}})
    print(f"parse precision {k}/{len(completed)} = {k / len(completed):.2f}, Wilson 95% [{lo:.2f}, {hi:.2f}]")
    if sheet_no == 1 and k < int(cfg["t3"]["min_precision_k"]):
        print("NOTE: below the 18/20 bar; fix the rule once, rebuild, report both precisions")
    if sheet_no == 2 and k < len(completed):
        key2 = read_json(d / f"t3_spotcheck2_key_{V}.json")
        drop = sorted(t for r in completed if r["correct"].strip().lower() == "no" for t in key2["items_behind"][r["row_id"]])
        write_json(d / f"t3_dropped_after_check2_{V}.json", {"dropped_items": drop, "reason": "their parse was marked wrong in spot-check 2"})
        print(f"NOTE: {len(completed) - k} parse(s) wrong; {len(drop)} dependent T3 items dropped from scoring: {drop}")
    return 0


def cmd_rebuild(cfg: dict, resolver: PathResolver) -> int:
    """One rule fix after the spot-check: rebuild actions and items with the current rules, keep the sheet and key,
    record both precisions (the fixed rule's on the same 20 rows only), and freeze the set."""
    import shutil

    d = _dir(resolver)
    receipt = read_json(d / f"t3_spotcheck_receipt_{V}.json")
    build = read_json(d / f"t3_build_{V}.json")
    if build.get("status") == "frozen":
        raise SystemExit("STOP: the T3 set is already frozen")
    comparison = json.loads((d / "t3_spotcheck_v2_comparison.json").read_text(encoding="utf-8"))
    sup = d / "superseded"
    sup.mkdir(exist_ok=True)
    for name in (f"t3_actions_{V}.jsonl", f"t3_items_{V}.jsonl", f"t3_build_{V}.json"):
        shutil.move(str(d / name), str(sup / name.replace(f"_{V}", f"_{V}_rules_v1_draft")))
    amend_path, amendments, paras_by_md, text_of, issue, titles = load_inputs(cfg, resolver)
    actions, counts = [], Counter()
    for it in sorted(amendments.values(), key=lambda x: x["item_id"]):
        acts, c = P.parse_amendment(it, titles)
        actions += acts
        counts.update(c)
    (d / f"t3_actions_{V}.jsonl").write_text("".join(json.dumps(a.to_dict(), ensure_ascii=False) + "\n"
                                                    for a in actions), encoding="utf-8")
    rows, why = B.candidate_rows(actions, amendments, paras_by_md, text_of, issue)
    t3 = cfg["t3"]
    items, log = B.build_items(rows, n=int(t3["n_items"]), seed=int(t3["seeds"]["items"]),
                               max_per_direction=int(t3["max_items_per_direction"]), today=str(t3["today"]))
    (d / f"t3_items_{V}.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items),
                                           encoding="utf-8")
    fixed_ok = sum(1 for r in comparison if (r["v1_correct"] == "yes" and not r["changed_fields"])
                   or (r["v1_correct"] == "no" and r["changed_fields"]))
    lo, hi = B.wilson(fixed_ok, len(comparison))
    meta = {"built_utc": _now(), "status": "frozen", "rules_version": P.RULES_VERSION,
            "amendment_source": str(amend_path.relative_to(REPO_ROOT)),
            "amendment_source_sha256": hashlib.sha256(amend_path.read_bytes()).hexdigest(),
            "instructions": dict(counts), "parsed_actions": len(actions),
            "parsed_by_type": {f"{k[0]}/{k[1]}": v for k, v in sorted(Counter((a.action, a.scope) for a in actions).items())},
            "exclusions": dict(why), "items": log,
            "precision": {
                "rules_v1_human": receipt["precision"],
                "rules_v2_same_20_rows": {"k": fixed_ok, "n": len(comparison), "value": fixed_ok / len(comparison),
                                          "wilson_95": [lo, hi],
                                          "basis": "the 15 rows Karan marked correct are unchanged under v2; the 5 he "
                                                   "marked wrong change exactly as his notes describe. Assessed by "
                                                   "Claude against Karan's notes, not re-checked by a human.",
                                          "rows": comparison}},
            "rule_fix": ["within-paragraph changes of one enumerated item merged into one action",
                         "per-instruction commencement date: an 'except paragraph N (item)' date applies only under "
                         "that item of the amendment's own numbering; deeper exceptions stay a window",
                         "full commencement sentence; 'dated <date>' of another instrument ignored"]}
    write_json(d / f"t3_build_{V}.json", meta)
    print(f"rules {P.RULES_VERSION}: instructions {counts['verbs']}, parsed {counts['parsed']} "
          f"(+{counts['merged_into_previous']} merged), unparsed {counts['unparsed']}")
    print(f"items {log['items']} from {log['directions']} Directions; sides {log['sides']}; gold {log['gold']}")
    print(f"precision: v1 {receipt['precision']['k']}/{receipt['precision']['n']}; v2 on the same rows {fixed_ok}/{len(comparison)} "
          f"(Wilson [{lo:.2f}, {hi:.2f}]); set frozen")
    return 0


def _checked_action_ids(d: Path) -> set[str]:
    acts = {json.loads(l)["action_id"]: json.loads(l) for l in open(d / f"t3_actions_{V}.jsonl", encoding="utf-8")}
    key = read_json(d / f"t3_spotcheck_key_{V}.json")["rows"]

    def same(a, b):
        return a["item_id"] == b["item_id"] and (a["instruction"][:60] in b["instruction"] or b["instruction"][:60] in a["instruction"])

    return {aid for aid, a in acts.items() if any(same(a, k) for k in key.values())}


def cmd_sheet2(cfg: dict, resolver: PathResolver) -> int:
    """Audit note 1: 10 seeded parses that sit behind frozen T3 items and are not among the first 20."""
    import random as _r

    d = _dir(resolver)
    sheet = d / f"t3_spotcheck2_sheet_{V}.csv"
    if sheet.exists():
        raise SystemExit(f"STOP: {sheet.name} exists")
    if read_json(d / f"t3_build_{V}.json").get("status") != "frozen":
        raise SystemExit("STOP: the T3 set is not frozen")
    items = _read_jsonl(d / f"t3_items_{V}.jsonl")
    acts = {a["action_id"]: a for a in _read_jsonl(d / f"t3_actions_{V}.jsonl")}
    checked = _checked_action_ids(d)
    pool = sorted({i["action_id"] for i in items} - checked)
    sample_ids = sorted(_r.Random(int(cfg["t3"]["seeds"]["spotcheck2"])).sample(pool, int(cfg["t3"]["spotcheck2_n"])))
    _, amendments, _, _, _, titles = load_inputs(cfg, resolver)
    sample = [P.Action(**acts[a]) for a in sample_ids]
    rows = B.sheet_rows(sample, amendments, titles)
    sheet.write_text(B.sheet_csv(rows), encoding="utf-8-sig")
    write_json(d / f"t3_spotcheck2_key_{V}.json", {
        "created_utc": _now(), "rules_version": P.RULES_VERSION, "pool": len(pool), "seed": cfg["t3"]["seeds"]["spotcheck2"],
        "rows": {r["row_id"]: a.to_dict() for r, a in zip(rows, sample)},
        "items_behind": {r["row_id"]: [i["t3_id"] for i in items if i["action_id"] == a.action_id] for r, a in zip(rows, sample)},
        "sheet_sha256": hashlib.sha256(sheet.read_bytes()).hexdigest()})
    print(f"sampled {len(sample)} of {len(pool)} unchecked parses behind frozen items")
    print(f"spot-check 2 sheet: {sheet}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["build", "ingest", "rebuild", "sheet2"])
    parser.add_argument("--sheet", type=int, choices=[1, 2], default=1)
    parser.add_argument("--file")
    args = parser.parse_args()
    cfg = load_config()
    resolver = PathResolver.from_config(cfg)
    if args.command == "ingest":
        if not args.file:
            parser.error("ingest needs --file")
        return cmd_ingest(cfg, resolver, args.file, args.sheet)
    if args.command == "rebuild":
        return cmd_rebuild(cfg, resolver)
    if args.command == "sheet2":
        return cmd_sheet2(cfg, resolver)
    return cmd_build(cfg, resolver)


if __name__ == "__main__":
    raise SystemExit(main())
