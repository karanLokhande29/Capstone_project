#!/usr/bin/env python3
"""Build the comparator API bundle (Demo Build Spec, Phase H). Run locally; makes no LLM calls.

    python3 ui/api/build_bundle.py

Writes:
- ui/api/bundle/ (committed; no RBI text): the frozen comparator prompts, the frozen rule, the comparator module (one
  import line rewritten to the bundle package), FROZEN.json, the M2 confidence model and the context tables M2 needs.
- ui/api/.data/ (gitignored; server-side only, never in a public build): the exact inputs of the sealed T1 run for each
  of the 412 units (source span and the two shown candidates, read from the blank pass-1 sheet exactly as
  scripts/run_sealed_predictions.py did, with the same sha256 check), and the paragraph texts presenter mode may show.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

API = Path(__file__).resolve().parent
UI = API.parent
ROOT = UI.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UI / "scripts"))

BUNDLE = API / "bundle"
DATA = API / ".data"
IMPORT_LINE = "from src.rag import comparator_rule as RULE"
BUNDLE_IMPORT = "from obli_frozen import comparator_rule as RULE  # bundle copy; identical to src/rag/comparator.py otherwise"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    import cc_common as C
    from src.benchmark import t1 as T
    from src.rag import comparator as CMP

    frozen = json.loads((ROOT / "configs/comparator_v1/FROZEN.json").read_text())
    pkg = BUNDLE / "obli_frozen"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text('"""Frozen comparator files, copied by ui/api/build_bundle.py and verified by sha256 at start-up."""\n')
    shutil.copyfile(ROOT / "src/rag/comparator_rule.py", pkg / "comparator_rule.py")
    src = (ROOT / "src/rag/comparator.py").read_text(encoding="utf-8")
    if src.count(IMPORT_LINE) != 1:
        raise SystemExit("STOP: src/rag/comparator.py import line changed; update build_bundle.py")
    (pkg / "comparator.py").write_text(src.replace(IMPORT_LINE, BUNDLE_IMPORT), encoding="utf-8")
    for f in ("comparator_system.txt", "comparator_user.txt"):
        shutil.copyfile(ROOT / "configs/comparator_v1" / f, pkg / f)
    shutil.copyfile(ROOT / "configs/comparator_v1/FROZEN.json", pkg / "FROZEN.json")
    for name, expected in frozen["sha256"].items():
        if sha(pkg / name) != expected:
            raise SystemExit(f"HARD STOP: bundled {name} does not match FROZEN.json")

    model = json.loads((UI / "src/data/confidence_model_v1.json").read_text())
    m2 = {k: model["models"]["M2"][k] for k in ("id", "label", "features", "intercept", "weights", "means", "sds")}
    (BUNDLE / "confidence_m2.json").write_text(json.dumps({"version": model["version"], "bandThresholds": model["bandThresholds"], "M2": m2}, indent=1))
    docs = {d["md_id"]: d for d in C.read_jsonl(ROOT / "release/data/documents.jsonl")}
    amended = sorted(k for k, d in docs.items() if "Updated as on" in (d.get("title") or ""))
    cells = {f"{m['entity_class']}|{m['subject_family']}": bool(m["ambiguous"]) for m in C.read_jsonl(ROOT / "release/data/matrix/matrix_v1.jsonl")}
    family = {k: d.get("subject_family") for k, d in docs.items()}
    (BUNDLE / "context.json").write_text(json.dumps({"amended": amended, "ambiguousCells": cells, "familyOfDirection": family,
                                                     "model": frozen["model"], "temperature": 0, "maxOutputTokens": 4096,
                                                     "thinking": {"thinkingLevel": "minimal"}, "jsonMode": True}, indent=0))

    # Server-side inputs: the exact sealed-run inputs (blank pass-1 sheet, sha-checked like the sealed run).
    T1 = ROOT / "data/benchmark/t1"
    want = json.loads((T1 / T.DRAW_LOG_FILE).read_text())["entries"][-1]["files"]
    sheet_key = next(k for k in want if k.endswith("pass1") and "sha256" in want[k])
    if CMP.sha256_file(T1 / T.PASS1_SHEET) != want[sheet_key]["sha256"]:
        raise SystemExit("STOP: blank pass-1 sheet changed since the draw log")
    rows = T.read_sheet(T1 / T.PASS1_SHEET)
    srcrow = {r["item_id"]: r for r in rows if r["row_type"] == T.ROW_ITEM}
    cand = {(r["item_id"], r["target_class"]): r["target_candidates"] for r in rows if r["row_type"] == T.ROW_CLASS}
    gold = C.read_jsonl(T1 / "t1_validated_v1.jsonl")
    sealed = C.comparator_records(C.CMP_GOLD)
    inputs = {}
    for g in gold:
        for cls in sorted(g["compared_classes"]):
            uid = C.unit_id(g["item_id"], cls)
            cands = CMP.parse_candidates(cand[(g["item_id"], cls)])
            ids = [p for p, _ in cands]
            if [p for p, _ in sealed[uid].get("per_candidate") or []] not in ([], ids):
                raise SystemExit(f"STOP: shown candidates differ from the sealed record for {uid}")
            inputs[uid] = {"item_id": g["item_id"], "source_class": srcrow[g["item_id"]]["source_class"], "source_text": srcrow[g["item_id"]]["source_span"],
                           "target_class": cls, "candidates": cands, "source_md": g["md_id"], "sealed_matched": sealed[uid].get("matched_paragraph_id")}
    pids = {p for u in inputs.values() for p, _ in u["candidates"]} | {u["item_id"].removeprefix("t1_") for u in inputs.values()}
    text = C.iter_processed(pids)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "inputs.json").write_text(json.dumps(inputs, ensure_ascii=False))
    (DATA / "paragraphs.json").write_text(json.dumps({p: t["text"] for p, t in text.items()}, ensure_ascii=False))
    print(f"bundle: frozen files verified ({', '.join(frozen['sha256'])}); inputs for {len(inputs)} units; {len(text)} paragraphs (server-side only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
