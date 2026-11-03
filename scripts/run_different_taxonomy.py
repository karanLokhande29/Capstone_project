#!/usr/bin/env python3
"""`different` error taxonomy + retrieval/reasoning separator. DRY RUN on gold v1 (tooling only; final analysis Phase 4).

    python3 scripts/run_different_taxonomy.py [--gold data/benchmark/t1/t1_validated_v1.jsonl]

No model calls. The long-context retention check rebuilds each prompt locally (corpus + document metadata only), the
same way P4-001 computed retention. Writes reports/private/final_push/p1/ (never overwrites).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common.config import load_config  # noqa: E402
from src.eval import different_taxonomy as DT  # noqa: E402

RUNS = ROOT / "data/rag_runs"
OUT = ROOT / "reports/private/final_push/p1"
SYSTEMS = {"class_blind": "class_blind", "class_aware": "class_aware", "final_agentic": "final_agentic",
           "ablation_a": "ablation_a", "long_context": "long_context_cap100k"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(ROOT / "data/benchmark/t1/t1_validated_v1.jsonl"))
    a = ap.parse_args()
    cfg = load_config(None)
    from scripts.run_p4 import load_prompts
    from src.rag import pipeline as PL
    from src.retrieval import index as IX

    gold = [json.loads(l) for l in Path(a.gold).read_text().splitlines() if l.strip()]
    by_id = {g["item_id"]: g for g in gold}
    corpus = IX.load_corpus(ROOT / "data/processed")
    pos = {pid: i for i, pid in enumerate(corpus.ids)}
    text_of = lambda pid: corpus.texts[pos[pid]] if pid in pos else ""
    manifest = [json.loads(l) for l in (ROOT / "data/metadata/document_manifest.jsonl").read_text().splitlines() if l.strip()]
    doc = {r["document_id"]: {"title": r.get("title") or "", "entity_class": r.get("entity_class_raw"),
                              "subject_family": r.get("subject_family")} for r in manifest}
    paras_by_md: dict[str, list] = {}
    for p in sorted((ROOT / "data/processed").glob("md_*.jsonl")):
        rows = sorted((json.loads(x) for x in p.read_text().splitlines() if x.strip()), key=lambda r: r.get("position") or 0)
        paras_by_md[p.stem] = [{"paragraph_id": r["paragraph_id"], "clause_path": r.get("clause_path")} for r in rows]
    res = PL.Resources(corpus=corpus, bm25=None, emb=None, encoder=None, doc=doc,
                       function_headings=frozenset(cfg["matching"]["function_headings"]), temporal=None,
                       paragraph_max_chars=int(cfg["p4"]["retrieval"]["paragraph_max_chars"]))
    prompts = load_prompts(cfg)
    lc_cap = 100000
    lc_body: dict[str, str] = {}

    runs = {}
    for s, run in SYSTEMS.items():
        d = RUNS / f"t1_{run}"
        runs[s] = {json.loads(p.read_text())["item_id"]: json.loads(p.read_text()) for p in sorted(d.glob("t1_*.json"))}

    def in_context(system: str, u) -> bool | None:
        if not u["gold_matched"]:
            return None
        if system == "long_context":
            iid = u["item_id"]
            if iid not in lc_body:
                lc_body[iid] = PL.long_context_messages(prompts, res, by_id[iid], max_input_tokens=lc_cap,
                                                        paras_by_md=paras_by_md)[0][1]["content"]
            return f"[{u['gold_matched']}]" in lc_body[iid]
        return u["gold_matched"] in DT.context_ids_rag(u["record"].get("steps"), u["target_class"])

    units = DT.different_units(gold)
    out = DT.analyse(units, runs, in_context, text_of)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"label": "DRY RUN on gold v1 — tooling only; v1-based; final analysis in Phase 4 on gold v2",
            "gold": str(Path(a.gold).relative_to(ROOT)), "systems": SYSTEMS, "lc_cap": lc_cap,
            "categories": DT.CATEGORIES, "note": "candidate_categories are cue-difference pre-tags for a human, never labels"}
    jp = OUT / f"different_taxonomy_dryrun_v1_{stamp}.json"
    jp.write_text(json.dumps({"meta": meta, **out}, indent=1, ensure_ascii=False) + "\n")
    cp = OUT / f"different_taxonomy_sheet_dryrun_v1_{stamp}.csv"
    with cp.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "target_class", "gold_matched", "missed_by_every_system", "candidate_categories",
                    *[f"{s}_pred" for s in SYSTEMS], *[f"{s}_failure" for s in SYSTEMS], "final_category", "note"])
        for r in out["units"]:
            w.writerow([r["item_id"], r["target_class"], r["gold_matched"], r["missed_by_every_system"],
                        "; ".join(r["candidate_categories"]), *[r["by_system"][s]["pred"] for s in SYSTEMS],
                        *[r["by_system"][s]["failure"] for s in SYSTEMS], "", ""])
    print(meta["label"])
    for s, v in out["per_system"].items():
        print(f"  {s:14s} errors {v['errors']}/{v['gold_different_units']}  {v['error_types']}  failures {v['failure_types']}"
              f"  no prediction {v['no_prediction']}")
    print(f"  missed by every system: {out['missed_by_every_system']}; of those, reasoning failure in every system: "
          f"{out['missed_by_every_system_reasoning_in_all_systems']}")
    print(f"  candidate-category pre-tags among the missed: {out['missed_by_every_system_candidate_categories']}")
    print(f"-> {jp.relative_to(ROOT)}\n-> {cp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
