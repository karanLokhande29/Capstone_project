#!/usr/bin/env python3
"""Sealed Phase 4 predictions. No metric, and no comparison with any gold, rejected-item label or rater file, until Phase 4.

    python3 scripts/run_sealed_predictions.py rejected        # (a) current quota day: 17 rejected items through every P4 system
                                                               #     + long-context, and the frozen comparator on their class pairs
    python3 scripts/run_sealed_predictions.py comparator-t1 --gate "gate: comparator t1 run"
                                                               # (b) frozen comparator on the 106 gold items' 412 class pairs;
                                                               #     refuses before the next quota day (Sat 12:30 IST)
    python3 scripts/run_sealed_predictions.py manifest        # (c) every prediction file + sha256 -> Phase 4 input manifest

How calls are made:
- the same client, cache, quota ledger and throttle as P4 (`scripts/run_p4.py`);
- the frozen P4 prompts, settings and model;
- a 503 or quota error backs off and pauses for resume; the model is never switched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # local embedding model only; never download
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark import t1 as T  # noqa: E402
from src.common.config import get_required, load_config  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.rag import comparator as CMP  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
T1 = ROOT / "data/benchmark/t1"
SEALED = ROOT / "data/rag_runs/sealed_phase4"
PROMPTS = ROOT / "configs/comparator_v1"
FROZEN = PROMPTS / "FROZEN.json"
MANIFEST_V1 = ROOT / "reports/private/final_push/phase4_input_manifest_v1.json"  # kept unchanged (record)
MANIFEST = ROOT / "reports/private/final_push/phase4_input_manifest_v2.json"
DAY_LIMIT = 400  # Karan: the day's total including the dev run stays <= 400
SYSTEMS = ("class_blind", "class_aware", "final_agentic", "ablation_a", "long_context")
GATE_T1 = "gate: comparator t1 run"


def _offline_pinned_model_loader() -> None:
    """Load the pinned embedding model from the local HF cache snapshot named by its commit (no network).

    `src.retrieval.index.load_model` verifies the pin with a Hub `model_info` call. Here the snapshot directory name *is*
    the pinned commit hash, which gives the same guarantee offline; nothing is downloaded.
    """
    from src.retrieval import index as IX

    def load_model(model_id: str, revision: str, *, device: str, max_seq_length: int):
        from sentence_transformers import SentenceTransformer

        snap = Path.home() / ".cache/huggingface/hub" / f"models--{model_id.replace('/', '--')}" / "snapshots" / revision
        if not snap.is_dir():
            raise SystemExit(f"STOP: pinned snapshot {revision} of {model_id} is not in the local cache")
        model = SentenceTransformer(str(snap), device=device)
        model.max_seq_length = max_seq_length
        return model

    IX.load_model = load_model

    import huggingface_hub
    from types import SimpleNamespace

    original = huggingface_hub.model_info

    def model_info(model_id: str, revision: str | None = None, **kw):
        import re as _re

        if not (revision and _re.fullmatch(r"[0-9a-f]{40}", str(revision)) and not Path(str(model_id)).exists()):
            return original(model_id, revision=revision, **kw)  # not a pinned-commit lookup: unchanged behaviour
        snap = Path.home() / ".cache/huggingface/hub" / f"models--{model_id.replace('/', '--')}" / "snapshots" / str(revision)
        if not snap.is_dir():
            raise SystemExit(f"STOP: pinned snapshot {revision} of {model_id} is not in the local cache")
        return SimpleNamespace(sha=revision)  # the snapshot directory name is the commit hash: same pin check, offline

    huggingface_hub.model_info = model_info


def _frozen_prompts() -> CMP.Prompts:
    if not FROZEN.exists():
        raise SystemExit("STOP: the comparator is not frozen")
    return CMP.Prompts(PROMPTS, expected=json.loads(FROZEN.read_text())["sha256"])


def _units(items: list[dict], classes_of) -> list[dict]:
    rows = T.read_sheet(T1 / T.PASS1_SHEET)
    want = json.loads((T1 / T.DRAW_LOG_FILE).read_text())["entries"][-1]["files"]["karan_pass1"]["sha256"]
    if CMP.sha256_file(T1 / T.PASS1_SHEET) != want:
        raise SystemExit("STOP: blank pass-1 sheet changed")
    src = {r["item_id"]: r for r in rows if r["row_type"] == T.ROW_ITEM}
    cand = {(r["item_id"], r["target_class"]): r["target_candidates"] for r in rows if r["row_type"] == T.ROW_CLASS}
    out = []
    for it in items:
        for cls in classes_of(it):
            out.append({"item_id": it["item_id"], "source_class": src[it["item_id"]]["source_class"],
                        "source_text": src[it["item_id"]]["source_span"], "target_class": cls,
                        "candidates": CMP.parse_candidates(cand[(it["item_id"], cls)])})
    return out


def _unit_path(d: Path, u) -> Path:
    return d / f"{u['item_id'].replace('::', '_')}__{u['target_class'].replace(' ', '_')}.json"


def run_comparator(cfg, resolver, units: list[dict], out_dir: Path, run_id: str, cap: int) -> dict:
    from scripts.run_p4 import make_llm
    from src.llm import client as L

    prompts = _frozen_prompts()
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [u for u in units if not _unit_path(out_dir, u).exists()]
    client, ledger = make_llm(cfg, resolver, run_id)
    client.max_calls = cap
    done = failed = 0
    for u in todo:
        try:
            r = CMP.compare_unit(client, prompts, u, max_output_tokens=int(cfg["p4"]["max_output_tokens"]))
        except L.QuotaPaused as exc:
            print(f"Quota reached — resume after {exc.resume_after_ist} IST ({len(todo) - done} units left)")
            break
        except L.CallCapReached as exc:
            print(f"STOP: {exc}")
            break
        except L.LLMError as exc:
            failed += 1
            (out_dir / "_call_failures.jsonl").open("a").write(json.dumps({"unit": [u["item_id"], u["target_class"]], "error": str(exc)[:300]}) + "\n")
            continue
        r.update(prompt_sha256=json.loads(FROZEN.read_text())["sha256"], written_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        p = _unit_path(out_dir, u)
        p.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        p.chmod(0o444)
        done += 1
    s = client.run.summary()
    print(f"comparator {out_dir.name}: {done} new, {len(units) - len(todo)} already written, {failed} failures; "
          f"API calls {s['api_calls']}, cache hits {s['cache_hits']}")
    return {"done": done, "failed": failed, "api_calls": s["api_calls"]}


def cmd_rejected() -> int:
    import scripts.run_p4 as P4
    from src.llm import client as L

    cfg = load_config(None)
    resolver = PathResolver.from_config(cfg)
    model = str(get_required(cfg, "llm.p4_model"))
    _frozen_prompts()
    ledger = L.QuotaLedger(resolver.working_root / cfg["p4"]["ledger"], soft_cap=int(cfg["p4"]["soft_cap"]))
    items = P4._rejected_items(resolver)
    units = _units(items, lambda it: it["compared_classes"])
    n = len(items)
    lc_attempts = int(cfg["p4"]["long_context"]["attempts_per_run"])
    nominal = {"class_blind": n, "class_aware": n, "final_agentic": f"0–{n} (first answer from the class-aware cache; verifier retries only)",
               "ablation_a": f"0–{n} (first answer from the class-blind cache; verifier retries only)",
               "long_context": f"{n}–{n * lc_attempts} (up to {lc_attempts} attempts per item on 503/timeout)", "comparator": len(units)}
    upper = n * 4 + n * lc_attempts + len(units)
    used = ledger.used(model)
    print(f"(a) model {model}; quota day {ledger.quota_day()} (Pacific; ends 12:30 IST); ledger today {used}")
    print(f"    17 rejected items; planned calls: {nominal}")
    print(f"    exact first-answer calls {n * 3 + len(units)} (class-blind, class-aware, long-context, comparator); "
          f"upper bound incl. verifier retries and LC re-attempts {upper}; cached prompts cost 0")
    print(f"    day total would be at most {used + upper} (limit {DAY_LIMIT})")
    if used + upper > DAY_LIMIT:
        print("REFUSED: could exceed the day limit")
        return 1
    _offline_pinned_model_loader()
    res, extra = P4.load_resources(cfg, resolver)
    prompts = P4.load_prompts(cfg)
    verifier = P4.load_verifier(cfg)
    print(f"resources loaded offline (pinned snapshots); embedding + NLI verifier ready", flush=True)
    for system in SYSTEMS:
        out_dir = SEALED / "rejected17" / system
        out_dir.mkdir(parents=True, exist_ok=True)
        if ledger.used(model) >= DAY_LIMIT:
            print(f"STOP: day limit {DAY_LIMIT} reached before {system}")
            return 1
        s = P4.run_t1(cfg, resolver, system, items, prompts=prompts, res=res, extra=extra, verifier=verifier,
                      out_dir=out_dir, cap_tokens=100000 if system == "long_context" else None)
        if s.get("paused"):
            print(f"{system} paused: {s}")
            return 1
    run_comparator(cfg, resolver, units, SEALED / "rejected17" / "comparator", "sealed_comparator_rejected17",
                   cap=max(0, DAY_LIMIT - ledger.used(model)))
    print(f"ledger today now {ledger.used(model)}")
    return cmd_manifest()


def cmd_comparator_t1(gate: str | None) -> int:
    from src.llm import client as L

    if gate != GATE_T1:
        print(f"REFUSED: needs Karan's gate phrase ('{GATE_T1}') as --gate")
        return 1
    cfg = load_config(None)
    resolver = PathResolver.from_config(cfg)
    model = str(get_required(cfg, "llm.p4_model"))
    ledger = L.QuotaLedger(resolver.working_root / cfg["p4"]["ledger"], soft_cap=int(cfg["p4"]["soft_cap"]))
    opens = datetime(2026, 10, 3, 12, 30, tzinfo=IST)
    if datetime.now(timezone.utc) < opens or ledger.quota_day() <= "2026-10-02":
        print(f"REFUSED: the T1 comparator run waits for the new quota day ({opens:%a %d %b %H:%M} IST); "
              f"current quota day {ledger.quota_day()}")
        return 1
    gold = [json.loads(l) for l in (T1 / "t1_validated_v1.jsonl").read_text().splitlines() if l.strip()]
    units = _units(gold, lambda g: sorted(g["compared_classes"]))
    out_dir = SEALED / "comparator_t1_gold_v1"
    todo = [u for u in units if not _unit_path(out_dir, u).exists()]
    print(f"(b) model {model}; class pairs {len(units)}; calls to make {len(todo)}; quota day {ledger.quota_day()}; "
          f"ledger today {ledger.used(model)} of soft cap {cfg['p4']['soft_cap']}")
    cap = int(cfg["p4"]["soft_cap"]) - ledger.used(model)
    if cap <= 0:
        print("REFUSED: no quota left today")
        return 1
    run_comparator(cfg, resolver, units, out_dir, "sealed_comparator_t1", cap=min(cap, len(todo)))
    print(f"ledger today now {ledger.used(model)}")
    return cmd_manifest()


def cmd_manifest() -> int:
    files = sorted(p for p in SEALED.rglob("*.json")) if SEALED.exists() else []
    dev = sorted((ROOT / "data/rag_runs/comparator_dev_irr30").glob("*.json")) + sorted((ROOT / "data/rag_runs/comparator_dev_irr30_run1").glob("*.json"))
    for p in files:
        p.chmod(0o444)  # sealed: read-only
    entries = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files + dev}
    by_dir: dict[str, int] = {}
    for k in entries:
        d = str(Path(k).parent)
        by_dir[d] = by_dir.get(d, 0) + 1
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else (json.loads(MANIFEST_V1.read_text()) if MANIFEST_V1.exists() else {"history": []})
    out = {"note": "Phase 4 input manifest: SEALED predictions. No metric or gold comparison until Phase 4.",
           "updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "comparator_frozen": json.loads(FROZEN.read_text()) if FROZEN.exists() else None,
           "p4_prompts": "configs/p4_prompts_v1 (frozen; config p4.prompt_sha256)",
           "disclosures": ["5 of the 17 rejected items (t1_md_12940::p00022, t1_md_12999::p00016, t1_md_13011::p00041, "
                           "t1_md_13096::p00012, t1_md_13638::p00055) were used in P4 Part A format debugging before the P4 prompts "
                           "were frozen (data/rag_runs/debug_rejected); their sealed predictions use the frozen prompts."],
           "files_by_dir": by_dir, "files": entries,
           "history": prev.get("history", []) + [{"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "n_files": len(entries)}]}
    MANIFEST.write_text(json.dumps(out, indent=1) + "\n")
    print(f"manifest: {len(entries)} files -> {MANIFEST.relative_to(ROOT)} (sha256 {hashlib.sha256(MANIFEST.read_bytes()).hexdigest()[:16]}…)")
    for d, n in by_dir.items():
        print(f"  {d}: {n}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rejected")
    c = sub.add_parser("comparator-t1")
    c.add_argument("--gate")
    sub.add_parser("manifest")
    a = ap.parse_args()
    if a.cmd == "rejected":
        return cmd_rejected()
    if a.cmd == "comparator-t1":
        return cmd_comparator_t1(a.gate)
    return cmd_manifest()


if __name__ == "__main__":
    raise SystemExit(main())
