#!/usr/bin/env python3
"""RBI-ObliBench V2, milestone 2: the Topic Alignment Agent on the dev set, and system V2-A (alignment override of V1).

    python3 scripts/run_v2.py plan                                        # no API: units, calls, quota, checks
    python3 scripts/run_v2.py dev --gate "gate: v2 alignment dev run"     # ONLY after Karan types that gate
    python3 scripts/run_v2.py evaluate-dev [--run DIR]                    # no API: V1 vs V2-A on the IRR consensus

**Dev set:** the separate IRR-30 set (``run_comparator.dev_units``), 92 units, the same units and candidates as V1's
dev run. Never T1 gold, the 17 rejected items or the packet items.

**V2-A reuses V1's dev outputs** (``data/rag_runs/comparator_dev_irr30/``, read only): the aligner is the only new call,
one per unit.

**Where things go:** aligner records go to ``data/v2_runs/alignment_dev_irr30_<tag>/``, where ``<tag>`` comes from the
sha256 of the prompts and aligner code, so a prompt edit starts a new folder and every dev run is kept. At most
``MAX_DEV_RUNS`` prompt versions may be run on dev (V1 allowed one revision). Reports go to ``data/v2_runs/reports/``.
Neither is under the AuditGen guard's research roots. A dev run does write the LLM cache and quota ledger under
``data/llm_cache``, which the guard covers, as every P4 run does.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_comparator import DEV_RUNS as V1_DEV_RUNS  # noqa: E402
from scripts.run_comparator import _unit_path as v1_unit_path  # noqa: E402
from scripts.run_comparator import dev_units  # noqa: E402
from src.common.config import get_required, load_config  # noqa: E402
from src.rag.v2 import decision_v2 as D  # noqa: E402
from src.rag.v2 import eval_v2 as E  # noqa: E402
from src.rag.v2 import topic_aligner as TA  # noqa: E402

V2_RUNS = ROOT / "data/v2_runs"
REPORTS = V2_RUNS / "reports"
FROZEN = TA.PROMPTS_DIR / "FROZEN.json"
T1_SEALED_V1 = ROOT / "data/rag_runs/sealed_phase4/comparator_t1_gold_v1"
DEV_CAP = 100
MAX_DEV_RUNS = 2
GATE = "gate: v2 alignment dev run"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def prompt_tag(hashes: dict[str, str] | None = None) -> str:
    h = hashes or TA.frozen_hashes()
    return hashlib.sha256(json.dumps(h, sort_keys=True).encode()).hexdigest()[:8]


def run_dir(tag: str | None = None) -> Path:
    return V2_RUNS / f"alignment_dev_irr30_{tag or prompt_tag()}"


def dev_run_dirs() -> list[Path]:
    return sorted(p for p in V2_RUNS.glob("alignment_dev_irr30_*") if p.is_dir() and any(p.glob("*.json")))


def unit_path(u, directory: Path) -> Path:
    return directory / v1_unit_path(u).name


def _ids(u) -> list[str]:
    return [pid for pid, _ in u["candidates"]]


def plan_info() -> dict:
    """Everything ``plan`` prints. Reads local files only: no model, no network."""
    units, gold = dev_units()
    here = run_dir()
    v1 = [u for u in units if v1_unit_path(u).exists()]
    reproduced = sum(1 for u in v1
                     if D.decide_a(json.loads(v1_unit_path(u).read_text()), None, _ids(u))["changed"] is False)
    prompts = TA.Prompts()
    chars = sorted(sum(len(m["content"]) for m in prompts.messages(
        source_id=TA.source_id_of(u), source_class=u["source_class"], source_text=u["source_text"],
        target_class=u["target_class"], candidates=u["candidates"])) for u in units)
    done = [u for u in units if unit_path(u, here).exists()]
    runs = dev_run_dirs()
    return {"units": len(units), "items": len({u["item_id"] for u in units}),
            "candidates_per_unit": dict(Counter(len(u["candidates"]) for u in units)), "dev_gold": dict(Counter(gold.values())),
            "v1_dev_records": len(v1), "v2a_without_aligner_reproduces_v1": reproduced,
            "prompt_tag": prompt_tag(), "run_dir": here.relative_to(ROOT).as_posix(), "done": len(done),
            "calls_needed": len(units) - len(done), "dev_cap": DEV_CAP,
            "dev_runs_used": len(runs), "new_run": here not in runs, "max_dev_runs": MAX_DEV_RUNS,
            "prompt_tokens_rough": {"min": chars[0] // 4, "median": chars[len(chars) // 2] // 4, "max": chars[-1] // 4},
            "frozen": FROZEN.exists(),
            "t1_sealed_v1_records": len(list(T1_SEALED_V1.glob("*.json"))) if T1_SEALED_V1.exists() else 0}


def cmd_plan() -> int:
    p = plan_info()
    cfg = load_config(None)
    from src.common.paths import PathResolver
    from src.llm import client as L

    model = str(get_required(cfg, "llm.p4_model"))
    ledger = L.QuotaLedger(PathResolver.from_config(cfg).working_root / cfg["p4"]["ledger"],
                           soft_cap=int(cfg["p4"]["soft_cap"]))
    print("V2 milestone 2 plan (no calls made)")
    print(f"  dev set: {p['units']} units over {p['items']} IRR-30 items; candidates per unit {p['candidates_per_unit']}; "
          f"dev gold {p['dev_gold']}")
    print(f"  V1 dev records: {p['v1_dev_records']}/{p['units']}; V2-A with no aligner input reproduces V1 on "
          f"{p['v2a_without_aligner_reproduces_v1']}/{p['v1_dev_records']}")
    print(f"  prompt tag {p['prompt_tag']} -> {p['run_dir']}: {p['done']} done, {p['calls_needed']} calls needed "
          f"(cap {p['dev_cap']}); rough prompt tokens {p['prompt_tokens_rough']}")
    print(f"  dev runs used {p['dev_runs_used']} of {p['max_dev_runs']}"
          + ("; this prompt version would be a new one" if p["new_run"] else ""))
    print(f"  model {model} (llm.p4_model); quota day {ledger.quota_day()} Pacific: {ledger.used(model)} used of soft cap "
          f"{cfg['p4']['soft_cap']}")
    print(f"  V2 prompts frozen: {p['frozen']}. T1 (after freezing only): {p['t1_sealed_v1_records']} sealed V1 records, "
          f"so about {p['t1_sealed_v1_records']} aligner calls for V2-A")
    print("  note: a dev run writes the LLM cache and quota ledger under data/llm_cache (an AuditGen guard root)")
    return 0


def cmd_dev(gate: str | None) -> int:
    if gate != GATE:
        print(f"REFUSED: the dev run needs Karan's gate phrase ('{GATE}'), passed as --gate")
        return 1
    if FROZEN.exists():
        print("REFUSED: the V2 prompts are frozen; no further dev runs")
        return 1
    here = run_dir()
    if here not in dev_run_dirs() and len(dev_run_dirs()) >= MAX_DEV_RUNS:
        print(f"REFUSED: {MAX_DEV_RUNS} prompt versions already run on dev; no further revisions")
        return 1
    from scripts.run_p4 import make_llm
    from src.common.paths import PathResolver
    from src.llm import client as L

    cfg = load_config(None)
    resolver = PathResolver.from_config(cfg)
    model = str(get_required(cfg, "llm.p4_model"))
    p4 = cfg["p4"]
    units, _ = dev_units()
    todo = [u for u in units if not unit_path(u, here).exists()]
    ledger = L.QuotaLedger(resolver.working_root / p4["ledger"], soft_cap=int(p4["soft_cap"]))
    print(f"model: {model} (llm.p4_model); settings as P4: json_mode={p4['json_mode']}, thinking={p4.get('thinking')}, "
          f"temperature={cfg['llm'].get('temperature', 0)}, max_output_tokens={p4['max_output_tokens']}, fallback=none")
    print(f"calls: {len(todo)} (units {len(units)}, already done {len(units) - len(todo)}; cap {DEV_CAP}) -> "
          f"{here.relative_to(ROOT)}")
    print(f"quota ledger, today ({ledger.quota_day()} Pacific): {ledger.used(model)} used of soft cap {p4['soft_cap']}")
    if len(todo) > DEV_CAP:
        print("REFUSED: more calls than the cap")
        return 1
    if ledger.used(model) + len(todo) > int(p4["soft_cap"]):
        print("REFUSED: not enough quota left today for the whole run")
        return 1
    L.load_env()
    prov = L.GeminiProvider(L.require_key("GEMINI_API_KEY"))
    listed = {m.id for m in prov.list_models()}
    served = model in listed
    print(f"model-list call: {model} {'IS' if served else 'is NOT'} served ({len(listed)} models listed)")
    if not served:
        print("STOP: the P4 model is not served; not switching models")
        return 2
    client, ledger = make_llm(cfg, resolver, run_id=f"v2_alignment_dev_{_now()}")
    # The client counts HTTP attempts, so a transient-error retry uses one; the dev cap, not the unit count, is the limit.
    client.max_calls = DEV_CAP
    prompts = TA.Prompts()
    hashes = TA.frozen_hashes()
    here.mkdir(parents=True, exist_ok=True)
    done = 0
    for u in todo:
        try:
            r = TA.align_unit(client, prompts, u, max_output_tokens=int(p4["max_output_tokens"]))
        except (L.QuotaPaused, L.CallCapReached, L.LLMError) as exc:
            print(f"STOPPED after {done} calls: {type(exc).__name__}: {str(exc)[:200]}")
            break
        r["prompt_sha256"] = hashes
        r["written_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        unit_path(u, here).write_text(json.dumps(r, ensure_ascii=False, indent=1))
        done += 1
    print(f"dev run: {done} calls made; ledger now {ledger.used(model)}")
    return cmd_evaluate_dev(None)


def evaluate_dev(directory: Path, units=None, gold=None, v1_dir: Path | None = None) -> dict:
    """V1 and V2-A on the dev units that have both a V1 record and an aligner record in ``directory``."""
    if units is None:
        units, gold = dev_units()
    v1_path = (lambda u: v1_dir / v1_unit_path(u).name) if v1_dir else v1_unit_path
    v1, v2, aligned, missing = [], [], [], 0
    for u in units:
        if not (v1_path(u).exists() and unit_path(u, directory).exists()):
            missing += 1
            continue
        r1 = json.loads(v1_path(u).read_text())
        a = json.loads(unit_path(u, directory).read_text())
        v1.append(r1)
        v2.append(D.decide_a(r1, a, _ids(u)))
        aligned.append(a)
    if not v1:
        return {"n_units": 0, "missing": missing}
    return {"note": "DEV SET = separate IRR-30 consensus (not T1 gold); development evidence only. No T1 result.",
            "run_dir": str(directory), "rule": D.RULE_VERSION, "n_units": len(v1), "missing": missing,
            "aligner": TA.summarise(aligned), "v1": E.score(v1, gold), "v2a": E.score(v2, gold),
            "flips": E.flips(v1, v2, gold),
            "duty_source": dict(Counter(t["duty_source"] for r in v2 for t in r["trace"]))}


def cmd_evaluate_dev(run: str | None) -> int:
    directory = Path(run) if run else run_dir()
    m = evaluate_dev(directory if directory.is_absolute() else ROOT / directory)
    if not m["n_units"]:
        print(f"no dev results in {directory}")
        return 1
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / f"alignment_dev_eval_{Path(m['run_dir']).name.rsplit('_', 1)[-1]}_{_now()}.json"
    p.write_text(json.dumps(m, indent=1) + "\n")
    f = m["flips"]
    for name in ("v1", "v2a"):
        s = m[name]
        print(f"{name:>4}: macro-F1 {s['judgement_macro_f1']:.3f}  different F1 {s['per_label']['different']['f1']:.3f}  "
              f"different recall {s['different_recall']:.3f}  none precision {s['none_precision']:.3f}  "
              f"unsure {s['unsure']}")
    print(f"changed {f['changed']} of {f['n_units']}: fixed {f['fixed']}, broken {f['broken']}, other {f['other']}; "
          f"moves {f['moves']}")
    print(f"aligner: {m['aligner']}")
    print(f"-> {p.relative_to(ROOT)} (dev evidence only)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    d = sub.add_parser("dev")
    d.add_argument("--gate")
    e = sub.add_parser("evaluate-dev")
    e.add_argument("--run")
    a = ap.parse_args()
    if a.cmd == "plan":
        return cmd_plan()
    if a.cmd == "dev":
        return cmd_dev(a.gate)
    return cmd_evaluate_dev(a.run)


if __name__ == "__main__":
    raise SystemExit(main())
