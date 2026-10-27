#!/usr/bin/env python3
"""RBI compliance audit generator (local). Decision support only; verify against the official RBI text; not legal advice.

    python3 scripts/auditgen.py generate --profile profile.json [--out DIR]
    python3 scripts/auditgen.py gap --pack PACK_ID --policy FILE [--policy FILE ...] [--families "Know Your Customer|..."]
    python3 scripts/auditgen.py review-import --pack PACK_ID --workbook reviewed.xlsx --signer "Name"
    python3 scripts/auditgen.py refresh --dry-run | --apply [--budget 80]
    python3 scripts/auditgen.py validate                   # recompute the validation box (local models; no API calls)
    python3 scripts/auditgen.py samples                    # the 3 sample packs in outputs/auditgen_samples/
    python3 scripts/auditgen.py serve [--port 8765]        # local backend on 127.0.0.1
    python3 scripts/auditgen.py ai-status                  # is a local model (Ollama on 127.0.0.1) ready?
    python3 scripts/auditgen.py ask --pack PACK_ID --question "..."   # cited, NLI-verified answer from the local model
    python3 scripts/auditgen.py ai-samples [--model M]     # recorded AI outputs for the sample packs (offline replay)

No command makes a remote LLM API call. Gap analysis runs on local models only; the AI commands use a local Ollama
model on the loopback address only (config/auditgen_genai_v1.yaml).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auditgen import ai_features as AI  # noqa: E402
from src.auditgen import exports as EX  # noqa: E402
from src.auditgen import genai as G  # noqa: E402
from src.auditgen import freshness as FR  # noqa: E402
from src.auditgen import gap_analysis as GAP  # noqa: E402
from src.auditgen import pack as PK  # noqa: E402
from src.auditgen import review as RV  # noqa: E402
from src.auditgen import validation as VAL  # noqa: E402
from src.auditgen.corpus import get_store, load_config  # noqa: E402
from src.auditgen.enforcement import risk_by_family  # noqa: E402
from src.auditgen.profile import Profile  # noqa: E402

SAMPLE_PROFILES = [
    Profile("Sample Small Finance Bank", "Small Finance Banks", "", "2025-12-01",
            ["deposits", "lending", "priority_sector", "payments", "outsourcing", "kyc_aml", "it_cyber"], ["Commercial Banks"]),
    Profile("Sample NBFC", "Non-Banking Financial Companies", "", "2025-12-01",
            ["lending", "digital_lending", "co_lending", "outsourcing", "kyc_aml", "it_cyber"], []),
    Profile("Sample Payments Bank", "Payments Banks", "", "2025-12-01",
            ["deposits", "payments", "outsourcing", "kyc_aml", "it_cyber"], ["Small Finance Banks"]),
]
SAMPLE_POLICY = ROOT / "outputs/auditgen_samples/synthetic_sample_policy.md"


def _out(cfg, pack, out: str | None) -> Path:
    d = Path(out) if out else PK.runs_dir(cfg) / pack["pack_id"]
    PK.save(pack, d)
    EX.write_all(pack, d)
    return d


def cmd_generate(a) -> int:
    cfg = load_config()
    s = get_store(cfg)
    p = Profile.load(Path(a.profile)).validate(s.core_classes)
    pk = PK.generate(s, cfg, p)
    d = _out(cfg, pk, a.out)
    print(f"pack {pk['pack_id']}: {pk['summary']['register_visible']} obligations, {pk['summary']['needs_review']} need review -> {d}")
    return 0


def _gap(cfg, s, pk, policies: list[tuple[str, bytes]], families=None) -> dict:
    res = GAP.analyse(s, cfg, pk["register"], policies, families=families, risk=risk_by_family(pk["enforcement"]),
                      md_risk={r["md_id"]: r["penalty_count"] for r in pk["enforcement"]})
    res.pop("_texts", None)
    return res


def cmd_gap(a) -> int:
    cfg = load_config()
    s = get_store(cfg)
    pk = PK.load(cfg, a.pack)
    sid = GAP.new_session(cfg)
    docs = []
    for f in a.policy:
        data = Path(f).read_bytes()
        meta = GAP.save_upload(cfg, sid, Path(f).name, data)
        docs.append((meta["name"], data))
    res = _gap(cfg, s, pk, docs, [x for x in (a.families or "").split("|") if x] or None)
    res["session"] = sid
    pk["gaps"] = res
    pk["summary"] = PK.summarise(pk)
    d = _out(cfg, pk, None)
    print(f"gap analysis: {res['counts']} over {res['obligations']} obligations; uploads in data/auditgen_uploads/{sid}/ -> {d}")
    return 0


def cmd_review_import(a) -> int:
    cfg = load_config()
    pk = PK.load(cfg, a.pack)
    wb = Path(a.workbook)
    updates = RV.read_review_workbook(wb)
    new = RV.signed_off(pk, updates, signer=a.signer, source_name=wb.name, source_sha256=hashlib.sha256(wb.read_bytes()).hexdigest())
    new["summary"] = PK.summarise(new)
    d = _out(cfg, new, None)
    sp = new["signoff"]["progress"]
    print(f"signed-off pack {new['pack_id']} ({sp['reviewed']}/{sp['total']} rows reviewed; original {pk['pack_id']} kept) -> {d}")
    return 0


def cmd_refresh(a) -> int:
    cfg = load_config()
    s = get_store(cfg)
    if a.apply:
        res = FR.apply(s, cfg, budget=a.budget)
        print(json.dumps({k: res[k] for k in ("snapshot", "replaced_or_added_docs", "new_amendments", "failed", "requests")}, indent=1))
    else:
        res = FR.dry_run(s, cfg)
        out = ROOT / "data/auditgen_state" / f"refresh_dry_run_{date.today().isoformat()}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res, indent=1))
        print(f"dry run ({res['requests']} requests): {len(res['new_directions'])} new, {len(res['updated_directions'])} updated, "
              f"{len(res['removed_from_listing'])} no longer listed; amendment directions new: "
              f"{len((res['amendment_directions'] or {}).get('new', []))}; withdrawn new: {len((res['withdrawn_circulars'] or {}).get('new', []))} -> {out}")
    return 0


def _sfb_register(cfg, s):
    from src.auditgen.applicability import build_register

    p = SAMPLE_PROFILES[0]
    p = Profile(p.name, p.entity_class, date.today().isoformat(), p.last_review, list(p.activities), list(p.group_classes)).validate(s.core_classes)
    return build_register(s, cfg, p)


def cmd_validate(_a) -> int:
    cfg = load_config()
    s = get_store(cfg)
    v = VAL.compute_all(s, cfg, sfb_register=_sfb_register(cfg, s))
    print(json.dumps({k: v[k] for k in ("applicability", "temporal", "calendar_sheet", "gap_analysis", "differential")}, indent=1))
    return 0


def cmd_samples(a) -> int:
    cfg = load_config()
    s = get_store(cfg)
    base = ROOT / cfg["paths"]["samples"]
    base.mkdir(parents=True, exist_ok=True)
    today = a.as_of or date.today().isoformat()
    made = []
    for i, p0 in enumerate(SAMPLE_PROFILES):
        p = Profile(p0.name, p0.entity_class, today, p0.last_review, list(p0.activities), list(p0.group_classes)).validate(s.core_classes)
        pk = PK.generate(s, cfg, p)
        pk["pack_id"] = PK.slug(p.name)
        if i == 0:
            policy = SAMPLE_POLICY.read_bytes()
            res = _gap(cfg, s, pk, [(SAMPLE_POLICY.name, policy)], families=["Know Your Customer", "Managing Risks in Outsourcing"])
            res["session"] = None
            res["note"] = "Run on a SYNTHETIC sample policy written for this demo; never on real company data."
            pk["gaps"] = res
        pk["summary"] = PK.summarise(pk)
        d = base / pk["pack_id"]
        if d.exists():
            shutil.rmtree(d)
        _out(cfg, pk, str(d))
        made.append((pk["pack_id"], pk["summary"]["register_visible"], d))
    for pid, n, d in made:
        print(f"sample {pid}: {n} obligations -> {d.relative_to(ROOT)}")
    write_replay(cfg, [pid for pid, _, _ in made])
    return 0


def write_replay(cfg, pack_ids) -> None:
    """Offline replay copies for the UI: ui/public/auditgen/<id>.json.gz plus an index (gitignored, release-excluded)."""
    import gzip

    out = ROOT / "ui/public/auditgen"
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for pid in pack_ids:
        pk = PK.load(cfg, pid)
        raw = json.dumps(pk, ensure_ascii=False, separators=(",", ":")).encode()
        (out / f"{pid}.json.gz").write_bytes(gzip.compress(raw, 9, mtime=0))
        index.append({"pack_id": pid, "profile": pk["profile"], "created_utc": pk["created_utc"],
                      "summary": {k: pk["summary"].get(k) for k in ("register_visible", "needs_review", "changes", "calendar_entries")},
                      "file": f"{pid}.json.gz", "bytes": len(raw)})
    (out / "index.json").write_text(json.dumps({"kind": "auditgen_replay_index", "packs": index,
                                                "disclaimer": cfg["disclaimer"]}, indent=1))
    print(f"replay copies -> {out.relative_to(ROOT)} ({', '.join(p['file'] for p in index)})")


def cmd_ai_status(_a) -> int:
    gcfg = G.load_genai_config()
    st = G.LocalLLM(gcfg).status()
    print(json.dumps({**st, "host": gcfg["llm"]["host"], "genai_version": gcfg["version"]}, indent=1))
    return 0 if st["available"] else 1


def cmd_ask(a) -> int:
    cfg, gcfg = load_config(), G.load_genai_config()
    s = get_store(cfg)
    pk = PK.load(cfg, a.pack)
    res = AI.ask(s, cfg, gcfg, pk, a.question, llm=G.LocalLLM(gcfg), models=GAP.LocalModels.get(cfg), model=a.model)
    G.record(cfg, gcfg, pk["pack_id"], "ask", None, res)
    print(f"Q: {res['question']}\n")
    for x in res["sentences"]:
        if x["verified"]:
            print(f"  ✓ {x['text']}  [{', '.join(src['paragraph_id'] or src['row_id'] for src in x['sources'])}]")
    held = [x for x in res["sentences"] if not x["verified"]]
    if res["abstained"]:
        print(f"  {res['answer']}")
    if held:
        print(f"\n  ({len(held)} unverified sentence(s) held back)")
    print(f"\n  model {res['model']}, {res['seconds']}s, {res['attempts']} attempt(s). {cfg['disclaimer']}")
    for e in res["evidence"]:
        print(f"  {e['label']} {e['paragraph_id']} {e['source_url']}")
    return 0


AI_SAMPLE_QUESTIONS = {
    "sample_small_finance_bank": ["What must the bank do to verify a customer's identity?", "When must fraud be reported to the RBI?"],
    "sample_nbfc": ["What are the requirements for outsourcing to third parties?", "What must be disclosed to borrowers in digital lending?"],
    "sample_payments_bank": ["What are the limits on balances a payments bank customer can hold?", "What must be done when a card is lost or stolen?"],
}


AI_FEATURES = ("ask", "explain", "draft", "suggest", "change", "memo", "plan", "calendar", "diff")


def cmd_ai_samples(a) -> int:
    """Run every AI feature a few times on each sample pack with the real local model; store the outputs next to the
    sample pack and copy them to ui/public/auditgen/ai_<pack_id>.json for offline replay (stripped from public builds)."""
    import time

    cfg, gcfg = load_config(), G.load_genai_config()
    s = get_store(cfg)
    llm, models = G.LocalLLM(gcfg), GAP.LocalModels.get(cfg)
    llm.pick(a.model)
    scfg = {**cfg, "paths": {**cfg["paths"], "runs": cfg["paths"]["samples"]}}
    out = ROOT / "ui/public/auditgen"
    out.mkdir(parents=True, exist_ok=True)
    kw = {"llm": llm, "model": a.model}
    for pid, questions in AI_SAMPLE_QUESTIONS.items():
        try:
            pk = PK.load(cfg, pid)
        except FileNotFoundError:
            print(f"{pid}: no sample pack; run `samples` first")
            continue
        t0 = time.monotonic()
        want = set(a.features.split(",")) if a.features else set(AI_FEATURES)
        if want == set(AI_FEATURES):
            G.save_ai(scfg, pid, {"pack_id": pid, "kind": "ai_outputs", "label": G.LABEL, "recorded": True})
        else:  # re-record only the named features; keep the others
            G.save_ai(scfg, pid, {k: v for k, v in G.load_ai(scfg, pid).items() if k not in want})
        vis = [r for r in pk["register"] if not r["hidden"] and r.get("paragraph_id")]
        rows = [r for r in vis if r.get("deadline_frequency")][:2] or vis[:2]
        history: list[dict] = []
        for q in questions if "ask" in want else []:
            res = AI.ask(s, cfg, gcfg, pk, q, models=models, history=history, **kw)
            G.record(scfg, gcfg, pid, "ask", None, res)
            history.append({"question": q})
        for r in rows if "explain" in want else []:
            G.record(scfg, gcfg, pid, "explain", r["row_id"], AI.explain_obligation(s, cfg, gcfg, pk, r["row_id"], models=models, **kw))
        if "draft" in want:
            G.record(scfg, gcfg, pid, "draft", rows[0]["row_id"], AI.draft_clause(s, cfg, gcfg, pk, rows[0]["row_id"], models=models,
                                                                                 company=pk["profile"]["name"], **kw))
        if "suggest" in want:
            G.record(scfg, gcfg, pid, "suggest", f"register:{rows[0]['row_id']}",
                     AI.review_suggestion(s, cfg, gcfg, pk, "register", rows[0]["row_id"], models=models, **kw))
        ch = next((c for c in pk["changes"] if c.get("paragraph_id")), None)
        if ch and "change" in want:
            G.record(scfg, gcfg, pid, "change", ch["row_id"], AI.explain_change(s, cfg, gcfg, pk, ch["row_id"], models=models, **kw))
        if "memo" in want:
            G.record(scfg, gcfg, pid, "memo", None, AI.memo(s, cfg, gcfg, pk, models=models, **kw))
        if "plan" in want:
            G.record(scfg, gcfg, pid, "plan", None, AI.action_plan(s, cfg, gcfg, pk, models=models, **kw))
        cal = [e["entry_id"] for e in pk["calendar"] if e.get("verify")][: a.calendar]
        if cal and "calendar" in want:
            G.record(scfg, gcfg, pid, "calendar", None, AI.calendar_check(s, cfg, gcfg, pk, cal, **kw))
        d = next((r for r in pk["differential"] if r.get("counterpart_paragraph_id")), None)
        if d and "diff" in want:
            G.record(scfg, gcfg, pid, "diff", d["row_id"], AI.diff_second_opinion(s, cfg, gcfg, pk, d["row_id"], **kw))
        store = G.load_ai(scfg, pid)
        (out / f"ai_{pid}.json").write_text(json.dumps(store, ensure_ascii=False))
        print(f"{pid}: AI samples in {round(time.monotonic() - t0)}s -> {cfg['paths']['samples']}/{pid}/ai.json, ui/public/auditgen/ai_{pid}.json")
    return 0


def cmd_serve(a) -> int:
    from src.auditgen.api import serve

    serve(host=a.host, port=a.port)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--profile", required=True)
    g.add_argument("--out")
    gp = sub.add_parser("gap")
    gp.add_argument("--pack", required=True)
    gp.add_argument("--policy", action="append", required=True)
    gp.add_argument("--families")
    r = sub.add_parser("review-import")
    r.add_argument("--pack", required=True)
    r.add_argument("--workbook", required=True)
    r.add_argument("--signer", required=True)
    rf = sub.add_parser("refresh")
    m = rf.add_mutually_exclusive_group(required=True)
    m.add_argument("--dry-run", action="store_true")
    m.add_argument("--apply", action="store_true")
    rf.add_argument("--budget", type=int, default=80)
    sub.add_parser("validate")
    sm = sub.add_parser("samples")
    sm.add_argument("--as-of")
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8765)
    sub.add_parser("ai-status")
    ak = sub.add_parser("ask")
    ak.add_argument("--pack", required=True)
    ak.add_argument("--question", required=True)
    ak.add_argument("--model")
    ai = sub.add_parser("ai-samples")
    ai.add_argument("--model")
    ai.add_argument("--calendar", type=int, default=5, help="calendar 'verify' entries to check per pack")
    ai.add_argument("--features", help=f"comma-separated subset of {','.join(AI_FEATURES)} to re-record (default: all)")
    a = ap.parse_args()
    return {"generate": cmd_generate, "gap": cmd_gap, "review-import": cmd_review_import, "refresh": cmd_refresh,
            "validate": cmd_validate, "samples": cmd_samples, "serve": cmd_serve, "ai-status": cmd_ai_status,
            "ask": cmd_ask, "ai-samples": cmd_ai_samples}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
