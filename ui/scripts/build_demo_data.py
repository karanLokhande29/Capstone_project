#!/usr/bin/env python3
"""Demo data layer (Demo Build Spec, Phase C): the repository -> ui/public/data/*.json (per-route shards).

    python3 ui/scripts/build_demo_data.py            (or: cd ui && npm run data)

- Per-unit data comes only from run files (ingest.build_units). Nothing is derived from aggregate tables.
- The frozen comparator rule (src/rag/comparator_rule.py) is imported and wrapped for tracing, never edited. The traced
  verdict must equal the sealed verdict on every unit.
- Build-time assertions (§C3) reproduce the published numbers exactly; any mismatch stops the build.
- RBI text: one global 25-word budget per paragraph across every shard (12-word excerpts, 6-word field values). Values the
  budget cannot hold are marked {"withheld": true}, never silently null.
- No LLM calls and no API key needed.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate as CAL  # noqa: E402
import cc_common as C  # noqa: E402
import ingest as I  # noqa: E402

ROOT, UI = C.ROOT, C.UI
RULE = C.RULE
OUT = UI / "public/data"
CONF = UI / "src/data/confidence_model_v1.json"
LLM5 = ("class_blind", "class_aware", "final_agentic", "ablation_a", "long_context")
SYSTEMS = ("p2002_candidates", *LLM5, "comparator")
SEED = CAL.SPEC_DATA["seed"]  # confidence-work seed (AUDIT.md); results_v2 phase4.bootstrap.seed is 20261011
RESAMPLES = 2000
HERO = "t1_md_12949::p00040|Rural Co-operative Banks"
# Excerpt focus anchors (hero only): the 12-word excerpt starts at the obligation sentence instead of the paragraph start.
FOCUS = {"md_12949::p00040": "(2) Structural Liquidity", "md_12994::p00022": "Structural Liquidity Statement"}

# §C3: the published numbers. Every one must be reproduced from per-unit data.
EXPECT = {
    "items": 106, "units": 412, "gold": {"same": 213, "different": 78, "none": 121},
    "flags": {"shared": 52, "class-specific": 40, "absent": 14},
    "routes": {"adjudicated": 38, "retest-consistent": 6, "single-pass": 62},
    "missedA": 56, "missedB": 58, "recoveredA": 26, "recoveredB": 26, "missedAll": 32,
    "rr": {  # errors, retrieval, reasoning, ->same, ->none on the 78 gold-different units
        "class_blind": (60, 30, 30, 18, 42), "class_aware": (71, 12, 59, 32, 39), "final_agentic": (76, 12, 64, 13, 44),
        "ablation_a": (70, 30, 40, 8, 41), "long_context": (73, 4, 69, 43, 30), "comparator": (40, 0, 40, 6, 32)},
    "cmpDiff": {"tp": 38, "fp": 70, "fn": 40},
    "bands": {"High": (162, 156), "Medium": (123, 95), "Low": (125, 46), "Abstain": (2, 0)},
}

# Entity-name-by-construction detection (AUDIT.md A3): a value is "entity only" when nothing is left after removing
# articles, pronouns and institution words.
ENTITY_WORDS = set("""a an the its it them they their this that such individual concerned
bank banks nbfc nbfcs cic cics arc arcs ucb ucbs aifi aifis rrb rrbs rcb rcbs lab labs pb pbs psb psbs sfb sfbs lender lenders
commercial non banking non-banking financial finance companies company rural co operative co-operative cooperative regional urban local
area areas payments payment small all india institutions institution credit information asset reconstruction primary state district
central stcb dccb""".split())


def entity_only(v) -> bool:
    if not isinstance(v, str) or not v.strip():
        return False
    toks = re.findall(r"[a-z][a-z\-]*", v.lower())
    return bool(toks) and all(t in ENTITY_WORDS or all(p in ENTITY_WORDS for p in t.split("-")) for t in toks)


FFFD_DROPPED = [0]


def wjson(name: str, obj) -> int:
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=float)
    # U+FFFD comes from PDF extraction (e.g. a garbled Devanagari letterhead); it is display noise, so it is dropped.
    # Paragraph hashes are computed on the corpus text, not on these excerpts, and are unaffected.
    FFFD_DROPPED[0] += s.count("\ufffd")
    s = s.replace("\ufffd", "")
    p.write_text(s, encoding="utf-8")
    return len(s.encode())


def shard_name(item_id: str) -> str:
    return item_id.replace("::", "__")


# ---------------------------------------------------------------------------------------------------------------------
# Rule trace (wrap, don't edit)
# ---------------------------------------------------------------------------------------------------------------------

def trace_candidate(c: dict) -> tuple[list[dict], str]:
    official = RULE.candidate_verdict(c)
    steps = [{"step": "addresses the same duty", "fields": [], "result": "pass" if c["addresses_same_duty"] else "fired",
              **({} if c["addresses_same_duty"] else {"verdict": "none"}), "pid": c["paragraph_id"]}]
    mine = "none"
    if c["addresses_same_duty"]:
        fc = c["field_comparison"]
        differs = [f for f in RULE.FIELDS if fc[f] == "differs"]
        one_side = [f for f in RULE.MATERIAL if fc[f] in ("only_source", "only_target")]
        steps.append({"step": "any field differs", "fields": differs, "result": "fired" if differs else "pass",
                      **({"verdict": "different"} if differs else {}), "pid": c["paragraph_id"]})
        if not differs:
            steps.append({"step": "a material field is stated on one side only", "fields": one_side,
                          "result": "fired" if one_side else "pass", **({"verdict": "different"} if one_side else {}), "pid": c["paragraph_id"]})
        mine = "different" if (differs or one_side) else "same"
        if mine == "same":
            steps.append({"step": "no difference found", "fields": [], "result": "fired", "verdict": "same", "pid": c["paragraph_id"]})
    if mine != official:
        raise SystemExit(f"STOP: trace wrapper disagrees with the frozen rule on {c['paragraph_id']}: {mine} != {official}")
    return steps, official


def trace_unit(rec: dict) -> tuple[list[dict], str]:
    raw = C.parse_raw(rec)
    if raw is None or rec.get("parse_problems"):
        return [{"step": "model output could not be read", "fields": [], "result": "fired", "verdict": "abstain"}], "unsure"
    cands = [c for c in raw["candidates"] if isinstance(c, dict)]
    steps = []
    for c in cands:
        s, _ = trace_candidate(c)
        steps += s
    v = RULE.class_verdict(cands)
    steps.append({"step": "precedence same > different > none", "fields": [], "result": "fired", "verdict": v["judgement"],
                  "pid": v["matched_paragraph_id"]})
    return steps, v["judgement"]


def masked_verdict(rec: dict, mask: tuple[str, ...]) -> str:
    """Sensitivity analysis only: the frozen rule's own functions on a copy with the masked fields set to `equal`."""
    raw = C.parse_raw(rec)
    if raw is None or rec.get("parse_problems"):
        return "unsure"
    cands = []
    for c in raw["candidates"]:
        if isinstance(c, dict):
            c2 = dict(c)
            c2["field_comparison"] = {f: ("equal" if f in mask else v) for f, v in c["field_comparison"].items()}
            cands.append(c2)
    return RULE.class_verdict(cands)["judgement"]


# ---------------------------------------------------------------------------------------------------------------------

def main() -> int:
    for p in (I.R2P, I.GOLD):
        if C.sha256(p) != I.STEP0[I.rel(p)]:
            raise SystemExit(f"STOP: {I.rel(p)} sha256 does not match the frozen value")
    frozen = json.loads((ROOT / "configs/comparator_v1/FROZEN.json").read_text())
    for name, e in frozen["sha256"].items():
        p = ROOT / (f"src/rag/{name}" if name.endswith(".py") else f"configs/comparator_v1/{name}")
        if C.sha256(p) != e:
            raise SystemExit(f"HARD STOP: {name} does not match configs/comparator_v1/FROZEN.json")
    R2 = I.load(I.R2P)
    gold, items, units, cmp, cands_by_item = I.build_units(R2)  # already cross-checked against results_v2
    model = json.loads(CONF.read_text())
    M2 = model["models"]["M2"]
    docs, amended, cells = CAL.context_tables()
    goldrec = {g["item_id"]: g for g in gold}
    item_by = {i["id"]: i for i in items}
    gen = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sha = {"prompt": frozen["sha256"]["comparator_system.txt"], "userPrompt": frozen["sha256"]["comparator_user.txt"],
           "rule": frozen["sha256"]["comparator_rule.py"], "gold": C.sha256(I.GOLD), "results": C.sha256(I.R2P),
           "confidenceModel": C.sha256(CONF)}

    # ---- §C3 assertions ------------------------------------------------------------------------------------------
    def check(name, got, want):
        if got != want:
            raise SystemExit(f"STOP (§C3): {name}: got {got}, expected {want}")
    check("items", len(items), EXPECT["items"])
    check("units", len(units), EXPECT["units"])
    check("gold judgements", dict(Counter(u["goldJudgement"] for u in units)), EXPECT["gold"])
    check("flags", dict(Counter(i["goldFlag"] for i in items)), EXPECT["flags"])
    check("routes", dict(Counter(i["route"] for i in items)), EXPECT["routes"])
    # missedA / missedB recomputed per unit from the five LLM systems' own outputs (master doc §9.8 definitions).
    runs_final = {s: {} for s in LLM5}
    lc_name, _ = I.G.long_context_run(C.RUNS)
    for s, run in {**{s: s for s in LLM5[:4]}, "long_context": lc_name}.items():
        for p in sorted((C.RUNS / f"t1_{run}").glob("t1_*.json")):
            r = json.loads(p.read_text())
            runs_final[s][r["item_id"]] = r
    for u in units:
        js = {}
        for s in LLM5:
            r = runs_final[s].get(u["itemId"])
            js[s] = None if r is None else ((r.get("final") or {}).get("per_class") or {}).get(u["classId"], {}).get("judgement", "unsure")
        answered = [s for s in LLM5 if js[s] is not None]
        a = u["goldJudgement"] == "different" and len(answered) == 5 and all(js[s] != "different" for s in LLM5)
        b = u["goldJudgement"] == "different" and bool(answered) and all(js[s] != "different" for s in answered)
        if a != u["missedA"] or b != u["missedB"]:
            raise SystemExit(f"STOP (§C3): missedA/B recomputation differs on {u['id']}")
    check("missedA", sum(u["missedA"] for u in units), EXPECT["missedA"])
    check("missedB", sum(u["missedB"] for u in units), EXPECT["missedB"])
    cmpj = lambda u: u["predictions"]["comparator"]["judgement"]  # noqa: E731
    check("recoveredA", sum(u["missedA"] and cmpj(u) == "different" for u in units), EXPECT["recoveredA"])
    check("recoveredB", sum(u["missedB"] and cmpj(u) == "different" for u in units), EXPECT["recoveredB"])
    check("missed by every system incl. comparator", sum(u["goldJudgement"] == "different" and
          all(u["predictions"][s]["judgement"] != "different" for s in (*LLM5, "comparator")) for u in units), EXPECT["missedAll"])
    diff_units = [u for u in units if u["goldJudgement"] == "different"]
    for s, (err, ret, rea, to_same, to_none) in EXPECT["rr"].items():
        wrong = [u for u in diff_units if u["predictions"][s]["judgement"] not in ("different", "unanswered")]  # unanswered items are not errors
        got = (len(wrong), sum(u["predictions"][s].get("failure") == "retrieval" for u in wrong),
               sum(u["predictions"][s].get("failure") == "reasoning" for u in wrong),
               sum(u["predictions"][s]["judgement"] == "same" for u in wrong), sum(u["predictions"][s]["judgement"] == "none" for u in wrong))
        check(f"retrieval vs reasoning {s}", got, (err, ret, rea, to_same, to_none))
    tp = sum(u["goldJudgement"] == "different" and cmpj(u) == "different" for u in units)
    fp = sum(u["goldJudgement"] != "different" and cmpj(u) == "different" for u in units)
    check("comparator DIFFERENT", {"tp": tp, "fp": fp, "fn": 78 - tp}, EXPECT["cmpDiff"])

    # ---- confidence (M2) with contributions -------------------------------------------------------------------------
    conf = {}
    w, mu, sd = np.array(M2["weights"]), np.array(M2["means"]), np.array(M2["sds"])
    for u in units:
        rec = cmp[u["id"]]
        x = CAL.intrinsic(rec, item_by[u["itemId"]]["sourceClass"], docs, amended, cells)
        stored = model["units"][u["id"]]["M2"]
        if x is None:
            check(f"abstain band {u['id']}", stored["band"], "Abstain")
            conf[u["id"]] = {"model": "M2", "version": model["version"], "p": None, "band": "Abstain", "contributions": []}
            continue
        z = (np.array(x) - mu) / sd
        terms = w * z
        p = float(1 / (1 + math.exp(-(M2["intercept"] + terms.sum()))))
        if abs(p - stored["p"]) > 1e-9 or CAL.band(p) != stored["band"]:
            raise SystemExit(f"STOP: M2 recomputation differs on {u['id']}")
        conf[u["id"]] = {"model": "M2", "version": model["version"], "p": p, "band": stored["band"], "intercept": M2["intercept"],
                         "contributions": [{"feature": f, "value": float(xv), "z": float(zv), "weight": float(wv), "term": float(tv)}
                                           for f, xv, zv, wv, tv in zip(M2["features"], x, z, w, terms)]}
    bands = Counter(c["band"] for c in conf.values())
    for b, (n, k) in EXPECT["bands"].items():
        got_k = sum(1 for u in units if conf[u["id"]]["band"] == b and cmpj(u) == u["goldJudgement"])
        check(f"M2 band {b}", (bands[b], got_k), (n, k))

    # ---- traces and the A3 sensitivity analysis -----------------------------------------------------------------------
    traces = {}
    for u in units:
        steps, v = trace_unit(cmp[u["id"]])
        if v != cmp[u["id"]]["judgement"]:
            raise SystemExit(f"STOP: traced verdict {v} != sealed {cmp[u['id']]['judgement']} on {u['id']}")
        traces[u["id"]] = steps
    sens = {}
    for name, mask in (("frozen", ()), ("actorMasked", ("actor",))):
        tab = Counter((u["goldJudgement"], masked_verdict(cmp[u["id"]], mask)) for u in units)
        sens[name] = {"tp": tab[("different", "different")], "fp": tab[("same", "different")] + tab[("none", "different")],
                      "sameSame": tab[("same", "same")],
                      "confusion": {g: {p: tab[(g, p)] for p in ("same", "different", "none", "unsure")} for g in ("same", "different", "none")}}
    check("sensitivity frozen = published", (sens["frozen"]["tp"], sens["frozen"]["fp"]), (38, 70))
    lost = [u["id"] for u in units if u["goldJudgement"] == "different" and cmpj(u) == "different"
            and masked_verdict(cmp[u["id"]], ("actor",)) != "different"]

    # ---- pointers, excerpts and field values under one global budget -------------------------------------------------
    pids = set()
    shown = {}
    for u in units:
        it = item_by[u["itemId"]]
        pids.add(it["sourcePid"])
        sc = [e.removeprefix("t1c_") for e in cands_by_item[u["itemId"]]["top_targets"].get(u["classId"], [])[:2]]
        shown[u["id"]] = sc
        pids.update(sc)
        if u["goldMatchedPid"]:
            pids.add(u["goldMatchedPid"])
        for s in SYSTEMS:
            if u["predictions"][s].get("matchedPid"):
                pids.add(u["predictions"][s]["matchedPid"])
    text = C.iter_processed(pids)
    para_sha = {}
    with (ROOT / "release/data/paragraphs.jsonl").open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            if r["paragraph_id"] in pids:
                para_sha[r["paragraph_id"]] = r["text_sha256"]
    rdocs = {d["md_id"]: d for d in C.read_jsonl(ROOT / "release/data/documents.jsonl")}
    budget = C.WordBudget()
    pointers = {}
    for pid in sorted(pids):
        md = pid.split("::")[0]
        d = rdocs.get(md, {})
        t = text.get(pid, {}).get("text") or ""
        if pid in FOCUS:
            i = t.find(FOCUS[pid])
            if i < 0:
                raise SystemExit(f"STOP: focus anchor not found in {pid}")
            t = t[i:]
        title_words = (d.get("title") or "").split()
        pointers[pid] = {"id": pid, "mdId": md, "clausePath": text.get(pid, {}).get("clause_path"), "url": d.get("source_url"),
                         "harvestDate": d.get("harvest_date"), "sha256": para_sha.get(pid),
                         "excerpt": budget.take(pid, t, cap=C.EXCERPT_WORDS), "focused": pid in FOCUS,
                         "directionTitle": " ".join(title_words[:20]) + ("…" if len(title_words) > 20 else ""),
                         "entityClass": d.get("entity_class")}

    def value(pid, v):
        if v in (None, ""):
            return None
        got = budget.take(pid, v, cap=6) if pid else None
        return got if got is not None else {"withheld": True}

    rows_by_unit, cmp_meta = {}, {}
    anomalies = 0
    for u in sorted(units, key=lambda x: x["id"] != HERO):  # the hero case claims its paragraphs' budget first
        rec = cmp[u["id"]]
        df = C.decisive_fields(rec)
        src_pid = u["itemId"].removeprefix("t1_")
        if df is None:
            rows_by_unit[u["id"]] = []
            cmp_meta[u["id"]] = {"parseOk": False, "decisivePid": None, "addressesSameDuty": None,
                                 "perCandidate": [{"pid": p, "verdict": "abstain" if v == "unsure" else v, "addressesSameDuty": None}
                                                  for p, v in rec.get("per_candidate", [])]}
            continue
        order = sorted(df["rows"], key=lambda r: (r["status"] not in ("differs", "only_source", "only_target"), not r["material"],
                                                  C.FIELDS.index(r["field"])))
        vals = {r["field"]: (value(src_pid, r["source"]), value(df["decisivePid"], r["target"])) for r in order}
        rows = []
        for r in df["rows"]:
            note = None
            if r["status"] == "differs" and r["source"] in (None, "") and r["target"] in (None, ""):
                note = "extraction_anomaly"
                anomalies += 1
            elif r["field"] in ("actor", "scope") and r["status"] == "differs" and entity_only(r["source"]) and entity_only(r["target"]):
                note = "entity_name_by_construction"
            rows.append({"field": r["field"], "status": r["status"], "material": r["material"],
                         "sourceValue": vals[r["field"]][0], "targetValue": vals[r["field"]][1], **({"note": note} if note else {})})
        rows_by_unit[u["id"]] = rows
        cmp_meta[u["id"]] = {"parseOk": True, "decisivePid": df["decisivePid"], "addressesSameDuty": df["addressesSameDuty"],
                             "perCandidate": [{**p, "verdict": "abstain" if p["verdict"] == "unsure" else p["verdict"]} for p in df["perCandidate"]]}
    over = {p: n for p, n in budget.used.items() if n > C.WORD_LIMIT}
    if over:
        raise SystemExit(f"STOP: word budget exceeded {over}")
    check("extraction anomalies (AUDIT A4)", anomalies, 0)

    # ---- unit objects --------------------------------------------------------------------------------------------------
    retry = defaultdict(dict)
    for s in ("final_agentic", "ablation_a"):
        for item_id, r in runs_final[s].items():
            classes = set()
            for st in (r.get("steps") or [])[1:]:
                classes |= set(st.get("unsupported_classes") or [])
            for c in classes:
                retry[s][C.unit_id(item_id, c)] = True
    # X-Ray (K4): only what the run logs record, per system, never a combined pipeline.
    xray = defaultdict(dict)
    for s in ("class_blind", "class_aware", "final_agentic", "ablation_a"):
        for item_id, r in runs_final[s].items():
            for c in goldrec[item_id]["compared_classes"]:
                attempts = []
                for st in r.get("steps") or []:
                    sh = st.get("shown") or {}
                    if c in sh or "*" in sh:  # class-blind runs log one pooled list under "*"
                        attempts.append({"attempt": st.get("attempt"), "shown": sh.get(c) or sh.get("*"), "pooled": c not in sh,
                                         "retryRequested": c in (st.get("unsupported_classes") or []),
                                         "parseProblems": bool(st.get("parse_problems"))})
                xray[C.unit_id(item_id, c)][s] = {"classFilter": r.get("class_filter"), "verifier": r.get("verifier"),
                                                  "temporalFilter": r.get("temporal_filter"), "attempts": attempts}
    UNIT = {}
    for u in units:
        it = item_by[u["itemId"]]
        rec = cmp[u["id"]]
        preds = {}
        for s in SYSTEMS:
            p = u["predictions"][s]
            j = p["judgement"]
            status = "answered" if j in ("same", "different", "none") else ("abstained" if j == "abstain" else "not_answered")
            preds[s] = {"status": status, **({"judgement": j} if status == "answered" else {}), "matchedPid": p.get("matchedPid"),
                        "inContext": p.get("inContext"), **({"retryUsed": retry[s].get(u["id"], False)} if s in retry else {})}
        UNIT[u["id"]] = {
            "id": u["id"], "itemId": u["itemId"], "sourcePid": it["sourcePid"], "sourceClass": it["sourceClass"], "targetClass": u["classId"],
            "topic": it["subjectFamily"], "route": it["route"], "goldJudgement": u["goldJudgement"], "goldMatchedPid": u["goldMatchedPid"],
            "goldFlag": it["goldFlag"], "shownCandidates": shown[u["id"]], "predictions": preds, "missedA": u["missedA"], "missedB": u["missedB"],
            "comparator": {**cmp_meta[u["id"]], "rows": rows_by_unit[u["id"]], "trace": traces[u["id"]]},
            "confidence": conf[u["id"]], "xray": xray.get(u["id"], {}),
            "provenance": {"prompt_sha256": rec["prompt_sha256"]["comparator_system.txt"], "rule_sha256": rec["prompt_sha256"]["comparator_rule.py"],
                           "model": rec.get("model"), "temperature": 0, "sealed_written_utc": rec.get("written_utc"),
                           "gold_sha256": sha["gold"], "results_sha256": sha["results"], "confidence_model": model["version"],
                           "confidence_model_sha256": sha["confidenceModel"], "snapshot_generated_utc": gen},
        }

    # ---- write shards ----------------------------------------------------------------------------------------------------
    for old in (OUT / "cases").glob("*.json"):
        old.unlink()
    sizes = {}
    for it in items:
        us = [UNIT[uid] for uid in it["unitIds"]]
        need = {it["sourcePid"]}
        for x in us:
            need |= set(x["shownCandidates"]) | {x["goldMatchedPid"], x["comparator"]["decisivePid"]}
            need |= {p.get("matchedPid") for p in x["predictions"].values()}
        need.discard(None)
        g = goldrec[it["id"]]
        sizes[f"cases/{shard_name(it['id'])}.json"] = wjson(f"cases/{shard_name(it['id'])}.json", {
            "item": {"id": it["id"], "sourcePid": it["sourcePid"], "sourceClass": it["sourceClass"], "topic": it["subjectFamily"],
                     "route": it["route"], "goldFlag": it["goldFlag"], "inForceFrom": it["inForceFrom"], "comparedClasses": it["comparedClasses"],
                     "obligationSpanUnits": len((g.get("obligation_span") or {}).get("units") or [])},
            "units": us, "pointers": {p: pointers[p] for p in sorted(need) if p in pointers}})
    index = [{"id": u["id"], "itemId": u["itemId"], "shard": shard_name(u["itemId"]), "src": item_by[u["itemId"]]["sourceClass"],
              "tgt": u["classId"], "topic": item_by[u["itemId"]]["subjectFamily"], "route": item_by[u["itemId"]]["route"],
              "gold": u["goldJudgement"], "missedA": u["missedA"], "missedB": u["missedB"], "band": conf[u["id"]]["band"], "p": conf[u["id"]]["p"],
              "sys": {s: (UNIT[u["id"]]["predictions"][s].get("judgement") or UNIT[u["id"]]["predictions"][s]["status"]) for s in SYSTEMS},
              "inCtx": {s: UNIT[u["id"]]["predictions"][s].get("inContext") for s in SYSTEMS if s != "p2002_candidates"},
              "sameDuty": [p.get("addressesSameDuty") for p in cmp_meta[u["id"]]["perCandidate"]],
              "srcPid": item_by[u["itemId"]]["sourcePid"]} for u in units]
    sizes["cases/index.json"] = wjson("cases/index.json", {"generatedUtc": gen, "systems": list(SYSTEMS), "units": index})

    # Home: the hero case (with its pointers) and headline numbers.
    hero = UNIT[HERO]
    if not (hero["missedA"] and hero["goldJudgement"] == "different" and hero["predictions"]["comparator"].get("judgement") == "different"):
        raise SystemExit("STOP: hero case no longer satisfies the B3 criteria")
    hero_pids = {hero["sourcePid"], hero["comparator"]["decisivePid"], *hero["shownCandidates"]}
    corpus = R2["tables"]["01_corpus"]
    sizes["home.json"] = wjson("home.json", {
        "hero": hero, "heroPointers": {p: pointers[p] for p in hero_pids if p in pointers},
        "stats": {"directions": corpus["directions"], "paragraphs": corpus["paragraphs"], "institutionTypes": corpus["core_entity_classes"],
                  "units": len(units), "items": len(items), "realDifferences": EXPECT["gold"]["different"], "missedA": EXPECT["missedA"],
                  "recovered": EXPECT["recoveredA"], "comparatorFound": tp, "falseAlarms": fp},
        "classes": sorted({u["classId"] for u in units} | {i["sourceClass"] for i in items}),
        "source": {"results": "reports/results_v2.json", "resultsSha256": sha["results"]}, "generatedUtc": gen})

    # Results page: only the results_v2 keys the public pages read (annotator names redacted, numbers untouched).
    keep = ["phase4.comparator", "phase4.t1_different", "phase4.t1_systems", "phase4.missed_by_every_llm_system", "phase4.retrieval_vs_reasoning",
            "phase4.preregistered_comparisons", "phase4.t1_paired", "tables.01_corpus", "tables.02_candidates.candidates_kept",
            "tables.02_candidates.precision_rounds", "tables.05_t1_benchmark.sample", "tables.05_t1_benchmark.validated", "tables.06_t2_retrieval.p3001.t2_xclass_t1",
            "tables.08_t3", "tables.09_t4"]
    pruned: dict = {}
    for k in keep:
        try:
            v = I.get(R2, k)
        except (KeyError, IndexError):
            continue
        cur = pruned
        parts = k.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    snap_rel = [r for r in I.reliability(R2) if r["id"] == "fleiss_class_row"]
    e = M2["eval"]
    dif_ok = [u for u in units if cmpj(u) == "different" and u["goldJudgement"] == "different"]
    conf_summary = {
        "model": "M2", "label": M2["label"], "bands": e["bands"], "ece": e["ece"], "brier": e["brier"], "baseRate": e["baseRate"],
        "coverageHigh": e["operatingPoint"]["coverage"],
        "highBySame": sum(1 for u in units if conf[u["id"]]["band"] == "High" and cmpj(u) == "same"), "highN": bands["High"],
        "differentCorrectByBand": dict(Counter(conf[u["id"]]["band"] for u in dif_ok)),
        "recoveredByBand": dict(Counter(conf[u["id"]]["band"] for u in units if u["missedA"] and cmpj(u) == "different")),
        "differentFlags": {"precision": {"k": tp, "n": tp + fp}, "recall": {"k": tp, "n": EXPECT["gold"]["different"]}},
    }
    check("B1 different-correct bands", conf_summary["differentCorrectByBand"], {"Low": 36, "Medium": 2})
    sizes["results.json"] = wjson("results.json", I.redact_names({"results": pruned, "reliability": snap_rel, "confidence": conf_summary,
                                                                  "resultsSha256": sha["results"]}))

    # Triage grid: precomputed item-level bootstrap CIs at every distinct threshold.
    sizes["triage_grid.json"] = wjson("triage_grid.json", triage_grid(units, conf, M2, model))

    # Method & Trust: hashes, sensitivity analysis, audit counts.
    sizes["method.json"] = wjson("method.json", {
        "hashes": sha, "ledger": [{k: r[k] for k in ("path", "expectedSha256", "actualSha256", "status")} for r in I.frozen_ledger()[0]],
        "model": frozen["model"], "frozenAtUtc": frozen["frozen_at_utc"], "ruleVersion": RULE.RULE_VERSION,
        "fields": list(RULE.FIELDS), "material": list(RULE.MATERIAL),
        "sensitivity": {"label": "Post-paper sensitivity analysis — frozen benchmark result unchanged.", "frozen": sens["frozen"],
                        "actorMasked": sens["actorMasked"], "lostCorrect": lost},
        "withheldNote": "Values withheld by the 25-word excerpt limit are marked; none of the model's `differs` rows had both values empty.",
        "missesSameDuty": Counter(tuple(p["addressesSameDuty"] for p in cmp_meta[u["id"]]["perCandidate"]) == (False, False)
                                  for u in units if u["goldJudgement"] == "different" and cmpj(u) == "none")[True],
        "reliability": [r for r in I.reliability(R2) if r["id"] in ("fleiss_class_row", "fleiss_flag")],
        "generatedUtc": gen})

    sizes["edit_bases.json"] = wjson("edit_bases.json", edit_bases(units, cmp_meta, text, cmpj))
    sizes.update(other_shards(R2, pointers))
    total = sum(sizes.values())
    print(f"ui/public/data: {len(sizes)} files, {total / 1e6:.2f} MB; home.json {sizes['home.json'] / 1e3:.0f} KB; "
          f"index {sizes['cases/index.json'] / 1e3:.0f} KB; §C3 assertions passed; traced 412/412; sensitivity actor-masked "
          f"{sens['actorMasked']['tp']}/38 correct, {sens['actorMasked']['fp']}/70 false alarms; U+FFFD dropped {FFFD_DROPPED[0]}")
    return 0


# Edit lab (J): which structured edits a target paragraph supports. Detection only; the texts stay local / server-side.
EDIT_PATTERNS = {
    "frequency": re.compile(r"\b(quarterly|monthly|annually|half-yearly|yearly|weekly)\b", re.I),
    "deadline": re.compile(r"\bwithin (\d+) days\b", re.I),
    "amount": re.compile(r"(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d+)?\s?(?:crore|lakh)?", re.I),
    "percentage": re.compile(r"\b\d+(?:\.\d+)?\s?(?:per cent|percent|%)", re.I),
    "exception": re.compile(r"Provided (?:further )?that[^.]*\.", re.I),
    "condition": re.compile(r"with the prior approval of [^,.;]+", re.I),
    "reporting": re.compile(r"[^.]*\b(?:report|submit)[^.]*\.", re.I),
}


def edit_bases(units, cmp_meta, text, cmpj):
    out = []
    for u in units:
        pid = cmp_meta[u["id"]]["decisivePid"]
        if not pid or not cmp_meta[u["id"]]["parseOk"]:
            continue
        t = (text.get(pid) or {}).get("text") or ""
        kinds = [k for k, rx in EDIT_PATTERNS.items() if rx.search(t)]
        if kinds and cmpj(u) == u["goldJudgement"] and cmpj(u) in ("same", "different"):
            out.append({"unitId": u["id"], "targetPid": pid, "verdict": cmpj(u), "kinds": kinds})
    same = [x for x in out if x["verdict"] == "same"]
    diff = [x for x in out if x["verdict"] == "different"]
    pick = sorted(same, key=lambda x: (-len(x["kinds"]), x["unitId"]))[:6] + sorted(diff, key=lambda x: (-len(x["kinds"]), x["unitId"]))[:3]
    return {"bases": pick, "eligible": {"same": len(same), "different": len(diff)},
            "note": "Base pairs where the comparator matched the expert and the target paragraph contains an editable value. Texts are not bundled."}


def wilson(k: int, n: int) -> list[float] | None:
    return CAL.wilson(k, n) if n else None


def triage_grid(units, conf, M2, model):
    """Coverage / accuracy at every distinct M2 threshold. CIs: item-level bootstrap over the 106 items (seed in AUDIT.md)."""
    U = [u for u in units]
    correct = np.array([u["predictions"]["comparator"]["judgement"] == u["goldJudgement"] for u in U], dtype=float)
    p = np.array([conf[u["id"]]["p"] if conf[u["id"]]["p"] is not None else -1.0 for u in U])
    verdict = [u["predictions"]["comparator"]["judgement"] for u in U]
    item_ids = sorted({u["itemId"] for u in U})
    idx = {i: k for k, i in enumerate(item_ids)}
    item_of = np.array([idx[u["itemId"]] for u in U])
    rng = np.random.default_rng(SEED)
    counts = rng.multinomial(len(item_ids), [1 / len(item_ids)] * len(item_ids), size=RESAMPLES)  # (R, items)
    W = counts[:, item_of].astype(float)  # (R, units)
    thresholds = sorted({float(x) for x in p if x >= 0}, reverse=True)
    rows = []
    for t in thresholds:
        auto = p >= t
        rev = ~auto
        def ci(mask):
            wn = W[:, mask].sum(1)
            wk = (W[:, mask] * correct[mask]).sum(1)
            ok = wn > 0
            if ok.sum() < RESAMPLES * 0.5:
                return None
            acc = wk[ok] / wn[ok]
            return [float(np.percentile(acc, 2.5)), float(np.percentile(acc, 97.5))]
        n_auto, k_auto = int(auto.sum()), int(correct[auto].sum())
        n_rev, k_rev = int(rev.sum()), int(correct[rev].sum())
        split = {v: {"auto": int(sum(1 for i in range(len(U)) if auto[i] and verdict[i] == v)),
                     "autoCorrect": int(sum(1 for i in range(len(U)) if auto[i] and verdict[i] == v and correct[i])),
                     "total": verdict.count(v)} for v in ("same", "different", "none")}
        rows.append({"t": t, "nAuto": n_auto, "kAuto": k_auto, "accAuto": k_auto / n_auto if n_auto else None, "ciAuto": ci(auto),
                     "nReview": n_rev, "kReview": k_rev, "accReview": k_rev / n_rev if n_rev else None, "ciReview": ci(rev) if n_rev else None,
                     "split": split})
    high = next(r for r in rows if r["t"] == min(t for t in thresholds if t >= model["bandThresholds"]["high"]))
    if (high["nAuto"], high["kAuto"]) != (162, 156):
        raise SystemExit(f"STOP: triage grid at the High boundary gives {high['nAuto']}/{high['kAuto']}, expected 162/156")
    e = M2["eval"]
    return {"n": len(U), "seed": SEED, "seedSource": "ui/scripts/calibrate.py SPEC_DATA.seed (confidence spec)", "resamples": RESAMPLES,
            "unitOfResampling": "T1 item (106)", "rows": rows, "bandThresholds": model["bandThresholds"],
            "presets": {"High": high["t"], "Medium": min(t for t in thresholds if t >= model["bandThresholds"]["low"])},
            "calibration": {"ece": e["ece"], "brier": e["brier"], "reliability": e["reliability"], "baseRate": e["baseRate"], "bands": e["bands"]},
            "features": [{"feature": f, "weight": w, "mean": m, "sd": s} for f, w, m, s in zip(M2["features"], M2["weights"], M2["means"], M2["sds"])],
            "intercept": M2["intercept"], "fittedOn": M2["fittedOn"], "label": M2["label"]}


def other_shards(R2, pointers):
    sizes = {}
    # T3: amendment timeline, with and without the date check.
    t3 = C.read_jsonl(ROOT / "release/data/t3/items.jsonl")
    off = {json.loads(p.read_text())["t3_id"]: json.loads(p.read_text()) for p in (C.RUNS / "t3_temporal_off").glob("T3-*.json")}
    on = {json.loads(p.read_text())["t3_id"]: json.loads(p.read_text()) for p in (C.RUNS / "t3_temporal_on").glob("T3-*.json")}
    rows = [{"id": x["t3_id"], "pid": x["paragraph_id"], "asOf": x["as_of"], "side": x["side"], "gold": x["gold_status"],
             "action": x["action"], "scope": x["scope"], "effective": (x.get("effective") or {}).get("date"),
             "published": (x.get("amendment") or {}).get("published_date"), "amendmentUrl": (x.get("amendment") or {}).get("source_url"),
             "url": x.get("source_url"), "off": off[x["t3_id"]]["pred_status"], "on": on[x["t3_id"]]["pred_status"]} for x in t3]
    n_orig = sum(r["off"] == "in_force_original" for r in rows)
    if (len(rows), n_orig) != (52, 48):
        raise SystemExit(f"STOP: T3 rebuild {len(rows)} items / {n_orig} in-force-original, expected 52 / 48")
    sizes["t3.json"] = wjson("t3.json", {"items": rows, "source": "release/data/t3/items.jsonl + data/rag_runs/t3_temporal_{off,on}"})

    # T2: rank of the gold counterpart under each retriever (scored queries only).
    rel = {r["query_id"]: r for r in C.read_jsonl(ROOT / "release/data/t2/t2_xclass_t1.jsonl")}
    ranks = defaultdict(dict)
    for line in (ROOT / "data/evaluation/p3001/runs_t2_xclass_t1_v1.jsonl").read_text().splitlines():
        r = json.loads(line)
        q = rel.get(r["query_id"])
        if not q or not q.get("relevant"):
            continue
        gold_pids = set(q["relevant"])
        ranks[r["query_id"]][r["system"]] = next((i + 1 for i, pid in enumerate(r["ranked"]) if pid in gold_pids), None)
    qs = [{"id": k, "src": rel[k]["source_class"], "tgt": rel[k]["target_class"], "judgement": rel[k].get("judgement"),
           "srcPid": rel[k]["source_paragraph_id"], "gold": sorted(rel[k]["relevant"]), "ranks": v} for k, v in sorted(ranks.items())]
    n_scored = I.get(R2, "tables.06_t2_retrieval.p3001.t2_xclass_t1.n_scored")
    if len(qs) != n_scored:
        raise SystemExit(f"STOP: T2 rankings for {len(qs)} queries, results_v2 scores {n_scored}")
    for sysid in ("bm25", "dense", "hybrid_rrf", "class_aware"):
        rec10 = sum(1 for q in qs if q["ranks"].get(sysid) and q["ranks"][sysid] <= 10) / len(qs)
        ref = I.get(R2, f"tables.06_t2_retrieval.p3001.t2_xclass_t1.systems.{sysid}.recall.mean")
        if abs(rec10 - ref) > 1e-9:
            raise SystemExit(f"STOP: T2 recall@10 rebuild for {sysid} {rec10} != {ref}")
    sizes["t2_rankings.json"] = wjson("t2_rankings.json", {"queries": qs, "depth": 100,
                                                           "source": "data/evaluation/p3001/runs_t2_xclass_t1_v1.jsonl"})

    # T4: scores per question and answer type (no answer texts: the concatenated answers are RBI text).
    sc = C.read_jsonl(ROOT / "release/data/t4/scores.jsonl")
    by = defaultdict(dict)
    for s in sc:
        by[s["question_id"]][s["answer_type"]] = {"composite": s["composite_score"], "human": s.get("human")}
    t4 = I.get(R2, "tables.09_t4")
    qs4 = {q["question_id"]: q for q in C.read_jsonl(ROOT / "release/data/t4/questions.jsonl")}  # model-written questions, not RBI text
    gap = t4["paired"]["concatenated - genuine"]["composite_score"]
    sizes["t4.json"] = wjson("t4.json", {"questions": [{"id": k, "question": qs4[k]["question"], "entityClass": qs4[k].get("entity_class"),
                                                        "topic": qs4[k].get("subject_family"), "url": qs4[k].get("source_url"), "pid": qs4[k].get("paragraph_id"),
                                                        "scores": v} for k, v in sorted(by.items())],
                                         "byType": t4.get("by_type"), "gap": {"mean": gap["mean"], "ci": [gap["ci_low"], gap["ci_high"]],
                                                                               "key": "tables.09_t4.paired.concatenated - genuine.composite_score"},
                                         "source": "release/data/t4/scores.jsonl"})

    # Atlas: classes x families.
    classes, families, directions, cells, _ = I.build_corpus(R2)
    t1_by_cell = defaultdict(list)
    for g in C.read_jsonl(I.GOLD):
        t1_by_cell[(g["entity_class"], g.get("subject_family"))].append(g["item_id"])
    core = [c for c in classes if c["kind"] == "regulated"]
    sizes["matrix.json"] = wjson("matrix.json", {
        "classes": [c["id"] for c in core], "families": [f["id"] for f in families],
        "cells": [{**c, "t1Items": t1_by_cell.get((c["classId"], c["familyId"]), [])} for c in cells if c["classId"] in {x["id"] for x in core}],
        "directions": {d["id"]: {"title": d["title"], "url": d["url"]} for d in directions}})

    # Cost meter: tokens from the call ledger (no prices are recorded in the repository).
    led = defaultdict(lambda: [0, 0, 0])
    for line in (ROOT / "logs/llm_calls.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["run_id"] in ("sealed_comparator_t1",) or r["run_id"].startswith("comparator_dev_"):
            k = "t1" if r["run_id"] == "sealed_comparator_t1" else "dev"
            led[k][0] += 1
            led[k][1] += r.get("input_tokens") or 0
            led[k][2] += r.get("output_tokens") or 0
    t1 = led["t1"]
    sizes["cost.json"] = wjson("cost.json", {"t1": {"calls": t1[0], "inputTokens": t1[1], "outputTokens": t1[2],
                                                    "perCall": {"input": t1[1] / t1[0], "output": t1[2] / t1[0]}},
                                             "dev": {"calls": led["dev"][0], "inputTokens": led["dev"][1], "outputTokens": led["dev"][2]},
                                             "price": None, "priceNote": "No price is recorded in the repository; tokens only.",
                                             "source": "logs/llm_calls.jsonl"})
    return sizes


if __name__ == "__main__":
    raise SystemExit(main())
