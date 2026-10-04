#!/usr/bin/env python3
"""Command Center ingest: the repository -> ui/src/data/snapshot.json.

    python3 ui/scripts/ingest.py          (or: cd ui && npm run ingest)

What it does:
- Reads only public or local project files. It never reads reports/private/, the raw annotation sheets, or rater
  identities, and makes no LLM calls.
- Every number stays addressable by its results_v2.json key: the whole results file is embedded as `results`, and
  every derived entity carries `sourceKey`.
- Per-unit predictions are rebuilt with the scoring code's own helpers (src/eval/t1_regold, src/rag/analysis,
  src/eval/different_taxonomy). Their totals are cross-checked against results_v2.json; any mismatch stops the ingest.
- RBI text: at most 25 words per paragraph across everything bundled (cc_common.WordBudget), always with a pointer.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cc_common as C  # noqa: E402

ROOT, UI = C.ROOT, C.UI
sys.path.insert(0, str(ROOT))

from src.benchmark import t1 as T  # noqa: E402
from src.eval import different_taxonomy as DT  # noqa: E402
from src.eval import t1_regold as G  # noqa: E402
from src.eval.ci_format import fmt_ci  # noqa: E402
from src.rag import analysis as A  # noqa: E402
from src.release import stale_numbers as S  # noqa: E402

OUT = UI / "src/data/snapshot.json"
CI_VECTORS = UI / "src/data/ci_vectors.json"
R2P = ROOT / "reports/results_v2.json"
R1P = ROOT / "reports/results_v1.json"
MD2 = ROOT / "reports/final/RBI-ObliBench_Master_Document_v2.md"
TEX = ROOT / "paper/aisigh/main.tex"
TABLES = ROOT / "paper/aisigh/tables"
VENUE = ROOT / "reports/final/venue_check_v1.md"
GOLD = ROOT / "data/benchmark/t1/t1_validated_v1.jsonl"
GOLD_PUBLIC = ROOT / "release/data/t1/validated.jsonl"
CANDS = ROOT / "data/benchmark/t1/t1_candidate_benchmark_v1.jsonl"
EA = ROOT / "reports/final/error_analysis_v1.json"
PUBLIC_METRICS = {"P4": "reports/p4001_metrics_v1.json", "P3": "reports/p3002_metrics_v1.json",
                  "P31": "reports/p3001_metrics_v1.json", "B": "reports/p2004_t1_benchmark_metrics_v1.json"}
# Expected hashes: the Step 0 list in the run instructions (2026-10-03) and configs/comparator_v1/FROZEN.json.
STEP0 = {
    "reports/results_v1.json": "fb875878213daafefc1ce9cd559be58ae31652ad512a3afcf4d8c4ff3e21cee8",
    "reports/results_v2.json": "339bec858af82110fe4f659d0626e1cc715dacb22f598ebf5061aa7ec00cafcd",
    "data/benchmark/t1/t1_validated_v1.jsonl": "67d471a13a266a12fbb55f41500c71c39f1322a0d847011a43be4cc55af45fc5",
    "paper/aisigh/refs_verified.bib": "4a12fba79b137481a318da758f1d38036ce30fdadb16cd152481d94e0d795646",
    "configs/comparator_v1/FROZEN.json": "6509d3f750aba18e93853d9c9069bd7880f801226f144130e054ec6790a7db8d",
}
SYS_NAMES = {"majority": "Majority (in-sample)", "p2002_candidates": "P2-002 candidates", "class_blind": "Class-blind LLM",
             "class_aware": "Class-aware LLM", "final_agentic": "Final agentic (class filter + verifier)",
             "ablation_a": "Class-blind + verifier", "long_context": "Long-context LLM (100K cap)",
             "comparator": "Structured comparator"}
T1_SYSTEMS = list(SYS_NAMES)
RQ_TEXT = {
    "RQ1": ("Applicability", "Given a compliance question and a declared entity class, can a retrieval system return the obligations "
            "that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?"),
    "RQ2": ("Differential Obligation", "For a subject issued in parallel across entity classes, can the system identify what one "
            "entity class is required to do that another entity class is not?"),
    "RQ3": ("Metric Integrity", "Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal "
            "evaluation repair makes the metric resistant to concatenation/verbatim extraction?"),
}
EXCLUDED_PREFIXES = ("reports/private/",)


def rel(p: Path) -> str:
    return str(Path(p).relative_to(ROOT))


def load(p: Path):
    assert not rel(p).startswith(EXCLUDED_PREFIXES), p
    return json.loads(Path(p).read_text(encoding="utf-8"))


def get(obj, key: str):
    v = obj
    for k in key.split("."):
        v = v[int(k)] if isinstance(v, list) else v[k]
    return v


def ci_label(d: dict) -> str:
    if "diff" in d:
        return fmt_ci(d["diff"], d["ci"][0], d["ci"][1], signed=True, reading=True)
    if "value" in d:
        return fmt_ci(d["value"], d["ci"][0], d["ci"][1])
    if "mean" in d:
        signed = d["mean"] < 0 or "share_of_resamples_above_zero" in d
        return fmt_ci(d["mean"], d["ci_low"], d["ci_high"], signed=signed, reading=signed)
    if "kappa" in d:
        lo, hi = d["bootstrap"]["ci95"]
        return fmt_ci(d["kappa"], lo, hi)
    if "rho" in d:
        return fmt_ci(d["rho"], d["ci_low"], d["ci_high"])
    raise KeyError("no CI")


def ci_of(d: dict) -> tuple[float, float, float]:
    if "diff" in d:
        return d["diff"], d["ci"][0], d["ci"][1]
    if "value" in d:
        return d["value"], d["ci"][0], d["ci"][1]
    if "mean" in d:
        return d["mean"], d["ci_low"], d["ci_high"]
    if "kappa" in d:
        return d["kappa"], *d["bootstrap"]["ci95"]
    if "rho" in d:
        return d["rho"], d["ci_low"], d["ci_high"]
    raise KeyError("no CI")


# ---------------------------------------------------------------------------------------------------------------------
# T1 units: gold, every system's prediction, retrieval vs reasoning, comparator fields
# ---------------------------------------------------------------------------------------------------------------------

def build_units(R2: dict):
    gold = G.read_jsonl(GOLD)
    public = {r["item_id"]: r for r in C.read_jsonl(GOLD_PUBLIC)}
    need = {g["source_candidate_id"] for g in gold}
    cands = {}
    with CANDS.open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            if r["source_candidate_id"] in need:
                cands[r["source_candidate_id"]] = r
    cands_by_item = {r["item_id"]: r for r in cands.values()}
    preds = G.baseline_predictions(gold, cands)
    for s in G.LLM_SYSTEMS:
        preds[s] = G.finals(C.RUNS, s)
    lc_name, lc_cap = G.long_context_run(C.RUNS)
    preds["long_context"] = G.finals(C.RUNS, lc_name)
    cmp = C.comparator_records(C.CMP_GOLD)
    cmp_finals = {}
    for g in gold:
        per = {c: {"judgement": cmp[C.unit_id(g["item_id"], c)]["judgement"],
                   "matched_paragraph_id": cmp[C.unit_id(g["item_id"], c)].get("matched_paragraph_id")}
               for c in g["compared_classes"] if C.unit_id(g["item_id"], c) in cmp}
        if len(per) == len(g["compared_classes"]):
            d = T.derive_flag({k: v["judgement"] for k, v in per.items()})
            cmp_finals[g["item_id"]] = {"flag": d["flag"] or T.FLAG_AMBIGUOUS, "per_class": per}
    preds["comparator"] = cmp_finals

    # Cross-check against results_v2 (unit-level rebuild must reproduce the published counts).
    for s in T1_SYSTEMS:
        u = A.t1_units(gold, preds[s])
        n_items = len(u["items"])
        key = f"phase4.comparator.metrics.n_items" if s == "comparator" else f"phase4.t1_systems.{s}.n_items"
        if n_items != get(R2, key):
            raise SystemExit(f"STOP: {s} items {n_items} != {key}")
        jp = Counter((g, p) for _, g, p in u["judg"])
        conf_key = "phase4.comparator.different.judgement_confusion" if s == "comparator" else f"phase4.t1_different.{s}.judgement_confusion"
        conf = get(R2, conf_key)
        for gl, row in conf.items():
            for pl, n in row.items():
                if jp.get((gl, pl), 0) != n:
                    raise SystemExit(f"STOP: {s} confusion {gl}->{pl} {jp.get((gl, pl), 0)} != {n} ({conf_key})")

    # Retrieval vs reasoning on the 78 gold `different` units, with the scoring script's context definitions.
    runs = {s: {json.loads(p.read_text())["item_id"]: json.loads(p.read_text()) for p in sorted((C.RUNS / f"t1_{run}").glob("t1_*.json"))}
            for s, run in {"class_blind": "class_blind", "class_aware": "class_aware", "final_agentic": "final_agentic",
                           "ablation_a": "ablation_a", "long_context": lc_name}.items()}
    runs["comparator"] = {k: {"final": v} for k, v in cmp_finals.items()}
    lc_ctx = long_context_context(gold, lc_cap)

    def in_context(system, u):
        if not u["gold_matched"]:
            return None
        if system == "comparator":
            # The two shown candidates = P2-002 top-1/top-2 (top_targets[:2]); equal to the sealed per_candidate ids on all
            # 410 parsed units, and also defined for the 2 parse-failure units.
            shown = {e.removeprefix("t1c_") for e in cands_by_item[u["item_id"]]["top_targets"].get(u["target_class"], [])[:2]}
            return u["gold_matched"] in shown
        if system == "long_context":
            body = lc_ctx.get(u["item_id"])
            return None if body is None else (f"[{u['gold_matched']}]" in body)
        return u["gold_matched"] in DT.context_ids_rag(u["record"].get("steps"), u["target_class"])

    split = DT.analyse(DT.different_units(gold), runs, in_context, lambda _pid: "")
    for s, summ in split["per_system"].items():
        ref = get(R2, f"phase4.retrieval_vs_reasoning.per_system.{s}")
        if summ["errors"] != ref["errors"] or summ["failure_types"] != ref["failure_types"]:
            raise SystemExit(f"STOP: retrieval/reasoning rebuild for {s} {summ} != {ref}")
    rr = {C.unit_id(r["item_id"], r["target_class"]): r["by_system"] for r in split["units"]}

    # Missed by every LLM system (definitions A and B), unit-level.
    five = list(C.SYSTEMS_LLM)
    units, items = [], []
    for g in gold:
        pub = public[g["item_id"]]
        route = (pub.get("provenance") or "").split(":")[-1]
        unit_ids = []
        for c in sorted(g["compared_classes"]):
            uid = C.unit_id(g["item_id"], c)
            unit_ids.append(uid)
            p = {}
            for s in T1_SYSTEMS:
                fin = preds[s].get(g["item_id"])
                if fin is None:
                    p[s] = {"judgement": "unanswered", "matchedPid": None}
                    continue
                pc = (fin.get("per_class") or {}).get(c) or {}
                j = pc.get("judgement", "unsure")
                p[s] = {"judgement": "abstain" if j == "unsure" else j, "matchedPid": pc.get("matched_paragraph_id")}
            gj = g["per_class_judgement"][c]
            if uid in rr:
                for s, v in rr[uid].items():
                    p[s]["inContext"] = v["gold_in_context"]
                    p[s]["failure"] = v["failure"]
            answered = [s for s in five if p[s]["judgement"] != "unanswered"]
            missed_a = gj == "different" and len(answered) == 5 and all(p[s]["judgement"] != "different" for s in five)
            missed_b = gj == "different" and bool(answered) and all(p[s]["judgement"] != "different" for s in answered)
            units.append({"id": uid, "itemId": g["item_id"], "classId": c, "goldJudgement": gj,
                          "goldMatchedPid": (g.get("matched_paragraph_id") or {}).get(c) or None,
                          "predictions": p, "missedA": missed_a, "missedB": missed_b})
        items.append({"id": g["item_id"], "sourcePid": g["paragraph_id"], "mdId": g["md_id"], "sourceClass": g["entity_class"],
                      "subjectFamily": g.get("subject_family"), "clausePath": g.get("clause_path"),
                      "comparedClasses": sorted(g["compared_classes"]), "route": route, "goldFlag": g["differential_flag"],
                      "unitIds": unit_ids, "inForceFrom": g.get("in_force_from"), "amendedBy": g.get("amended_by") or [],
                      "adjudicatedFields": len(g.get("adjudicated_fields") or [])})
    miss = get(R2, "phase4.missed_by_every_llm_system")
    if sum(u["missedA"] for u in units) != miss["A_all_five_answered"]["missed"] or \
            sum(u["missedB"] for u in units) != miss["B_answered_only"]["missed"]:
        raise SystemExit("STOP: missed-by-every-LLM rebuild does not match results_v2")
    return gold, items, units, cmp, cands_by_item


def long_context_context(gold, cap):
    """item_id -> rebuilt long-context prompt body (the P4 retention rule), or {} when the corpus is unavailable."""
    try:
        from scripts.run_p4 import load_prompts
        from src.common.config import load_config
        from src.rag import pipeline as PL
        from src.retrieval import index as IX
    except Exception as e:  # pragma: no cover - environment specific
        print("long-context context unavailable:", e)
        return {}
    cfg = load_config(None)
    corpus = IX.load_corpus(ROOT / "data/processed")
    manifest = C.read_jsonl(ROOT / "data/metadata/document_manifest.jsonl")
    doc = {r["document_id"]: {"title": r.get("title") or "", "entity_class": r.get("entity_class_raw"),
                              "subject_family": r.get("subject_family")} for r in manifest}
    paras_by_md: dict = {}
    for p in sorted((ROOT / "data/processed").glob("md_*.jsonl")):
        rows = sorted((json.loads(x) for x in p.read_text().splitlines() if x.strip()), key=lambda r: r.get("position") or 0)
        paras_by_md[p.stem] = [{"paragraph_id": r["paragraph_id"], "clause_path": r.get("clause_path")} for r in rows]
    res = PL.Resources(corpus=corpus, bm25=None, emb=None, encoder=None, doc=doc,
                       function_headings=frozenset(cfg["matching"]["function_headings"]), temporal=None,
                       paragraph_max_chars=int(cfg["p4"]["retrieval"]["paragraph_max_chars"]))
    prompts = load_prompts(cfg)
    out = {}
    for g in gold:
        msgs = PL.long_context_messages(prompts, res, g, max_input_tokens=cap, paras_by_md=paras_by_md)
        out[g["item_id"]] = msgs[0][1]["content"]
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Pointers, excerpts and comparator fields under the per-paragraph word budget
# ---------------------------------------------------------------------------------------------------------------------

def build_pointers(items, units, cmp, cands_by_item):
    docs = {d["md_id"]: d for d in C.read_jsonl(ROOT / "release/data/documents.jsonl")}
    pids = set()
    for it in items:
        pids.add(it["sourcePid"])
    for u in units:
        if u["goldMatchedPid"]:
            pids.add(u["goldMatchedPid"])
        pids.update(e.removeprefix("t1c_") for e in cands_by_item[u["itemId"]]["top_targets"].get(u["classId"], [])[:2])
        for s in ("class_aware", "comparator"):
            if u["predictions"][s].get("matchedPid"):
                pids.add(u["predictions"][s]["matchedPid"])
    sha = {}
    with (ROOT / "release/data/paragraphs.jsonl").open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            if r["paragraph_id"] in pids:
                sha[r["paragraph_id"]] = r["text_sha256"]
    text = C.iter_processed(pids)
    budget = C.WordBudget()
    pointers = {}
    for pid in sorted(pids):
        md = pid.split("::")[0]
        d = docs.get(md, {})
        t = text.get(pid, {})
        pointers[pid] = {"id": pid, "mdId": md, "clausePath": t.get("clause_path"), "url": d.get("source_url"),
                         "harvestDate": d.get("harvest_date"), "sha256": sha.get(pid),
                         "excerpt": budget.take(pid, t.get("text"), cap=C.EXCERPT_WORDS)}
    # Comparator 13-field view: statuses always; values only within each paragraph's remaining budget, differing fields first.
    fields = {}
    for u in units:
        rec = cmp.get(u["id"])
        if not rec:
            continue
        df = C.decisive_fields(rec)
        sig = C.comparator_signals(rec)
        if df is None:
            fields[u["id"]] = {"parseOk": False, "perCandidate": [{"pid": p, "verdict": v} for p, v in rec.get("per_candidate", [])],
                               "rows": [], "decisivePid": None, "hinge": False, "nBoth": 0, "nMaterialDiff": 0}
            continue
        src_pid = u["itemId"].removeprefix("t1_")
        order = sorted(df["rows"], key=lambda r: (r["status"] not in ("differs", "only_source", "only_target"), C.FIELDS.index(r["field"])))
        vals = {}
        for r in order:
            sv = budget.take(src_pid, r["source"], cap=6) if r["source"] else None
            tv = budget.take(df["decisivePid"], r["target"], cap=6) if (r["target"] and df["decisivePid"]) else None
            vals[r["field"]] = (sv, tv)
        rows = [{"field": r["field"], "status": r["status"], "material": r["material"],
                 "sourceValue": vals[r["field"]][0], "targetValue": vals[r["field"]][1],
                 "sourcePresent": r["source"] not in (None, ""), "targetPresent": r["target"] not in (None, "")}
                for r in df["rows"]]
        fields[u["id"]] = {"parseOk": sig["parse_ok"], "decisivePid": df["decisivePid"], "addressesSameDuty": df["addressesSameDuty"],
                           "perCandidate": df["perCandidate"], "rows": rows, "hinge": sig["hinge"], "nBoth": sig["n_both"],
                           "nMaterialDiff": sig["n_material_diff"], "rule": rec.get("rule")}
    over = {p: n for p, n in budget.used.items() if n > C.WORD_LIMIT}
    if over:
        raise SystemExit(f"STOP: word budget exceeded {over}")
    return pointers, fields


# ---------------------------------------------------------------------------------------------------------------------
# Corpus atlas
# ---------------------------------------------------------------------------------------------------------------------

def build_corpus(R2):
    docs = C.read_jsonl(ROOT / "release/data/documents.jsonl")
    ec = load(ROOT / "release/data/metadata/entity_classes.json")
    sf = load(ROOT / "release/data/metadata/subject_families.json")
    matrix = C.read_jsonl(ROOT / "release/data/matrix/matrix_v1.jsonl")
    core = set(get(R2, "tables.05_t1_benchmark.by_source_class").keys())
    by_class = get(R2, "tables.01_corpus.paragraphs_by_entity_class")
    classes = [{"id": c, "label": c, "kind": "regulated" if c in core else "rbi_function", "paragraphs": by_class.get(c, 0),
                "paragraphsKey": f"tables.01_corpus.paragraphs_by_entity_class.{c}"} for c in sorted(by_class)]
    fam_labels = sorted({m["subject_family"] for m in matrix})
    families = [{"id": f, "label": f} for f in fam_labels]
    directions = []
    for d in docs:
        title = d.get("title") or ""
        m = re.search(r"Updated as on ([A-Za-z]+ \d{1,2}, \d{4})", title)
        defects = ["D2: empty title, no subject family"] if not title.strip() else []
        words = title.split()
        short = " ".join(words[:20]) + ("…" if len(words) > 20 else "")  # titles are RBI text: capped well under 25 words
        directions.append({"id": d["md_id"], "title": short, "subjectFamilyId": d.get("subject_family"), "classIds": [d.get("entity_class")],
                           "updatedAsOn": m.group(1) if m else None, "defects": defects, "url": d.get("source_url"),
                           "harvestDate": d.get("harvest_date")})
    cells = [{"classId": m["entity_class"], "familyId": m["subject_family"], "populated": m["populated"], "ambiguous": m["ambiguous"],
              "ambiguityReason": m.get("ambiguity_reason"), "directionIds": m.get("source_directions") or []} for m in matrix]
    meta = {"entityClassesSource": "release/data/metadata/entity_classes.json", "subjectFamiliesSource": "release/data/metadata/subject_families.json",
            "nEntityClassTerms": len(ec) if isinstance(ec, list) else len(ec.get("terms", ec)),
            "nSubjectFamilyTerms": len(sf) if isinstance(sf, list) else len(sf.get("terms", sf))}
    return classes, families, directions, cells, meta


# ---------------------------------------------------------------------------------------------------------------------
# Documents: Master Document v2 sections, paper claims, placeholders, venue
# ---------------------------------------------------------------------------------------------------------------------

def md_sections(text: str):
    out, cur, buf = [], None, []
    for line in text.splitlines():
        m = re.match(r"^(#{2,3}) (.+)$", line)
        if m:
            if cur:
                out.append({"id": cur[0], "title": cur[1], "text": "\n".join(buf).strip()})
            num = re.match(r"(\d+(?:\.\d+)?)\.? ", m.group(2))
            sid = num.group(1) if num else re.sub(r"[^a-z0-9]+", "-", m.group(2).lower()).strip("-")
            cur, buf = (sid, m.group(2)), []
        elif cur:
            buf.append(line)
    if cur:
        out.append({"id": cur[0], "title": cur[1], "text": "\n".join(buf).strip()})
    return out


def md_table(section_text: str):
    rows = [l for l in section_text.splitlines() if l.startswith("|")]
    if len(rows) < 3:
        return []
    head = [c.strip() for c in rows[0].strip("|").split("|")]
    return [dict(zip(head, [c.strip() for c in r.strip("|").split("|")])) for r in rows[2:]]


def latex_to_plain(s: str) -> str:
    s = re.sub(r"(?<!\\)%.*", "", s)
    s = s.replace("$-$", "−").replace("$\\rightarrow$", "→").replace("$\\times$", "×").replace("\\%", "%").replace("\\_", "_")
    s = s.replace("\\&", "&").replace("~", " ").replace("``", "\"").replace("''", "\"").replace("--", "–")
    s = re.sub(r"\\(?:textit|textbf|emph|texttt)\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\(?:cite|ref|label)\{[^}]*\}", "", s)
    s = re.sub(r"\$\\kappa\$", "κ", s)
    s = re.sub(r"\$\\rho\$", "ρ", s)
    s = re.sub(r"\$([^$]*)\$", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?", "", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\\])", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


EFFECT_VERBS = re.compile(r"\b(improv\w*|hurt\w*|beat\w*|lower\w*|rais\w*|outperform\w*|lead\w*|win\w*|reproduc\w*|recover\w*|"
                          r"lift\w*|reduc\w*|increas\w*|decreas\w*|helps?|gain\w*|sharply)\b", re.I)


def build_claims(R2):
    srcs = {"R2": R2, "EA": load(EA)}
    for k, p in PUBLIC_METRICS.items():
        srcs[k] = load(ROOT / p)
    bib = (ROOT / "paper/aisigh/refs_verified.bib").read_text(encoding="utf-8")
    srcs["bib"] = {"numbers": re.findall(r"\d[\d.]*", bib)}
    idx = S.build_index(srcs)
    claims = []

    def add(doc, section, sentence, cid):
        nums = []
        for tok in S.numbers_in(sentence):
            key = tok.lstrip("+")
            keys = idx.get(key, []) or (idx.get(key[:-1], []) if key.endswith("%") else [])
            nums.append({"text": tok, "nKeys": len(keys), "keys": [k.replace("R2:", "") for k in keys[:3]]})
        verb = EFFECT_VERBS.search(sentence)
        if not nums and not verb:
            return
        claims.append({"id": cid, "doc": doc, "section": section, "sentence": sentence, "numbers": nums,
                       "effectVerb": verb.group(0) if verb else None})

    tex = TEX.read_text(encoding="utf-8")
    body = tex[tex.index("\\begin{abstract}"):tex.index("\\bibliographystyle")]
    body = re.sub(r"(?s)\\begin\{figure\}.*?\\end\{figure\}", " ", body)
    section = "Abstract"
    n = 0
    for para in re.split(r"\n\s*\n", body):
        m = re.search(r"\\(?:sub)?section\*?\{([^}]*)\}", para)
        if m:
            section = latex_to_plain(m.group(1))
        para = re.sub(r"\\(?:sub)?section\*?\{[^}]*\}(\\label\{[^}]*\})?", "", para)
        para = re.sub(r"\\input\{[^}]*\}", "", para)
        for s in split_sentences(latex_to_plain(para)):
            n += 1
            add("paper", section, s, f"paper:{n}")
    for t in sorted(TABLES.glob("tab_*.tex")):
        tt = t.read_text(encoding="utf-8")
        cap = re.search(r"\\caption\{(.*?)\}\n", tt)
        for i, row in enumerate(re.findall(r"^(.*?)\\\\\s*$", tt, re.M)):
            if "toprule" in row or "midrule" in row:
                continue
            add("table", t.stem, latex_to_plain(row.replace("&", " | ")), f"{t.stem}:{i}")
        note = re.search(r"\\scriptsize (.*?)\}\n", tt)
        if note:
            for j, s in enumerate(split_sentences(latex_to_plain(note.group(1)))):
                add("table", t.stem + " (note)", s, f"{t.stem}:note{j}")
        if cap:
            add("table", t.stem + " (caption)", latex_to_plain(cap.group(1)), f"{t.stem}:caption")
    md = MD2.read_text(encoding="utf-8")
    for sec in md_sections(md):
        if sec["id"] in ("15", "changes-from-v1") or sec["title"].startswith("Appendix"):
            continue
        for k, line in enumerate(sec["text"].splitlines()):
            line = line.strip()
            if not line or line.startswith("|---"):
                continue
            plain = re.sub(r"[*`]", "", line.lstrip("-0123456789. ").strip())
            for j, s in enumerate(split_sentences(plain) if not line.startswith("|") else [plain]):
                add("master", f"§{sec['id']} {sec['title']}", s, f"md:{sec['id']}:{k}:{j}")
    return claims


def build_placeholders():
    out = []
    tex = TEX.read_text(encoding="utf-8")
    for i, line in enumerate(tex.splitlines(), 1):
        for m in re.finditer(r"\\placeholder\{([^}]*)\}", line):
            if "newcommand" not in line:
                out.append({"file": "paper/aisigh/main.tex", "line": i, "text": f"\\placeholder{{{m.group(1)}}}", "kind": "placeholder",
                            "task": "ST-AUTHOR-EMAILS" if "email" in m.group(1) else "ST-DOI"})
    for path in (MD2,):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pat, kind in ((r"DOI to be assigned", "doi_pending"), (r"\bTODO\b", "todo"), (r"\[verify\]", "verify")):
                if re.search(pat, line):
                    out.append({"file": rel(path), "line": i, "text": re.search(pat, line).group(0), "kind": kind, "task": "ST-DOI"})
    bib = (ROOT / "paper/aisigh/refs_verified.bib").read_text(encoding="utf-8")
    for i, line in enumerate(bib.splitlines(), 1):
        if "[verify]" in line:
            out.append({"file": "paper/aisigh/refs_verified.bib", "line": i, "text": "[verify]", "kind": "verify", "task": "ST-AUDIT"})
    return out


def build_venue():
    text = VENUE.read_text(encoding="utf-8")
    sources = dict(re.findall(r"^\| (S\d) \| (\S+)", text, re.M))
    facts = []
    for row in md_table(text.split("## Findings")[1].split("## Differences")[0]):
        srcs = [s.strip() for s in row.get("Source", "").split(",") if s.strip().startswith("S")]
        facts.append({"item": row["Item"], "text": row["What the site says"],
                      "sources": [{"id": s, "url": sources.get(s, "")} for s in srcs], "accessed": f"2026-10-03 {row['Accessed (IST)']} IST"})
    diffs = re.findall(r"^\d\. \*\*(.+?)\*\*", text.split("## Differences")[1], re.M)
    return {"file": rel(VENUE), "facts": facts, "differences": diffs, "checked": "2026-10-03 16:27–16:32 IST"}


# ---------------------------------------------------------------------------------------------------------------------
# Curated research model (every number by key)
# ---------------------------------------------------------------------------------------------------------------------

def caveats():
    C_ = [
        ("single_expert", "single_expert", "T1 gold is single-expert (rater_1). Agreement is measured on a separate 30-item sample, not on the gold.",
         ["task:T1", "dataset:t1_gold_v1"]),
        ("scoring_asymmetry", "scoring", "Abstentions are scored as errors, so the verifier's loss in F1 reflects both wrong answers and declined correct ones "
         "(coverage −0.217). Long-context items that exceeded the input cap are excluded rather than penalised, and every comparison with "
         "long-context is made on the same 102 items.", ["task:T1"]),
        ("by_construction", "by_construction", "T2 relevance was labelled only for the target-class counterpart, so the class filter's gain is partly by construction.",
         ["task:T2"]),
        ("bias_t2_xclass_t1", "bias", "t2_xclass_t1: raters were shown bge-base-en-v1.5 top-1/top-2 P2-002 candidates, so labelled counterparts favour the dense retriever.",
         ["dataset:t2_xclass_t1"]),
        ("bias_t2_xclass_p2002", "bias", "t2_xclass_p2002: pairs drawn by bge-base-en-v1.5 score bands, so relevance favours the dense retriever.", ["dataset:t2_xclass_p2002"]),
        ("bias_t2_supp_p2003", "bias", "t2_supp_p2003: candidates shown to the rater were ranked by TF-IDF, which favours BM25.", ["dataset:t2_supp_p2003"]),
        ("circular", "circular", "T3 gold and the temporal filter come from the same deterministic parser, so filter-on scores are circular by construction.",
         ["task:T3", "ablation:B"]),
        ("t3_parser_defect", "bias", "Known T3 parser defect: a merged change's recorded old words include the previous change's new words.", ["task:T3"]),
        ("small_n_t4", "small_n", "T4 has 30 questions, one blind rater for 30 answers, and LLM-drafted questions; 2 questions were flagged as bad.", ["task:T4"]),
        ("repair_exploratory", "exploratory", "The RePASs repair is exploratory, designed and tested on the same 30 questions, and not usable (ρ with human faithfulness −0.126).",
         ["task:T4"]),
        ("superseded_150k", "superseded", "The 150K-cap long-context run is superseded (stopped during an API outage); it appears only in the release appendix.",
         ["system:long_context"]),
        ("in_sample_majority", "in_sample", "Majority (in-sample) predicts the gold set's own most frequent labels: a reference baseline, not a deployable system.",
         ["system:majority"]),
        ("per_class_small_n", "small_n", "Source classes have 7–15 T1 items each, so per-class results have wide intervals.", ["task:T1"]),
        ("retest_short_gap", "bias", "The blind retest gap was 11.7–18.6 h (file-level bounds), so recall may inflate agreement.", ["reliability:retest"]),
        ("candidates_shown", "bias", "Every annotation sheet showed the same two P2-002 candidates per compared class; this may bias judgements toward them. "
         "The comparator saw the same two candidates.", ["task:T1", "system:comparator"]),
        ("item_set_102", "item_set", "Long-context answered 102 of 106 items at the 100K cap; its comparisons use those 102 items only.", ["system:long_context"]),
        ("flash_lite", "scope", "All LLM results come from gemini-3.5-flash-lite on free tiers.", ["task:T1", "task:T3"]),
        ("no_ci_different_f1", "missing_ci", "Per-system `different` F1 values are point estimates; CIs were not computed (paired comparator deltas do have CIs).",
         ["task:T1"]),
        ("amended_text_only", "scope", "RBI consolidates amendments in place: the corpus holds only current text, so earlier wording cannot be shown.",
         ["task:T3"]),
        ("dev_used_for_development", "exploratory", "The comparator's 30-item development set was used to revise the prompt once (field-extraction bug); "
         "dev numbers are development evidence only.", ["system:comparator"]),
        ("calibration", "small_n", "Confidence is calibrated on 412 single-expert units with a Flash-Lite-class model, so band intervals are wide.",
         ["system:comparator"]),
    ]
    return [{"id": i, "kind": k, "text": t, "appliesTo": a} for i, k, t, a in C_]


def findings(R2):
    P = "phase4"
    F = [
        ("F1", "The class filter improves retrieval.", "tables.06_t2_retrieval.p4_pipeline.t2_xclass_t1.paired",
         ["by_construction", "bias_t2_xclass_t1"], ["RQ1"], ["paper §Results RQ1", "MD §9.1", "MD §1 headline 1"]),
        ("F2", "It doesn't translate into better T1 judgement (class filter, without verifier).",
         f"{P}.t1_paired.Class filter, no verifier: class-aware − class-blind.flag_macro_f1",
         ["single_expert", "scoring_asymmetry"], ["RQ1", "RQ2"], ["paper §Results RQ1", "MD §9.3", "MD §1 headline 2"]),
        ("F3", "`different` is the core failure mode: 56 of 78 gold `different` units are missed by every LLM system (definition A), 58 by definition B; mostly reasoning failures.",
         f"{P}.missed_by_every_llm_system.A_all_five_answered.missed", ["single_expert", "candidates_shown", "scoring_asymmetry"], ["RQ2"],
         ["paper §Results RQ2", "MD §9.8", "MD §1 headline 3"]),
        ("F4", "The verifier hurts T1.", f"{P}.t1_paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1",
         ["scoring_asymmetry", "single_expert"], ["RQ1", "RQ2"], ["paper §Results RQ2", "MD §9.4", "MD §1 headline 4"]),
        ("F5", "Long-context is competitive (collapsed F1 vs final agentic, same 102 items).",
         f"{P}.t1_paired.Long-context − final agentic (same items).collapsed_macro_f1",
         ["item_set_102", "scoring_asymmetry", "single_expert"], ["RQ1"], ["paper §Results RQ2", "MD §9.4", "MD §1 headline 5"]),
        ("F6", "RePASs concatenation gameability reproduces.", "tables.09_t4.paired.concatenated - genuine.composite_score",
         ["small_n_t4"], ["RQ3"], ["paper §Results RQ3", "MD §9.6", "MD §1 headline 6"]),
        ("F7", "The structured comparator lifts `different` F1 (0.409 vs 0.154 for class-aware).",
         f"{P}.preregistered_comparisons.comparator − class_aware.judgement.different_f1",
         ["single_expert", "candidates_shown", "dev_used_for_development", "scoring_asymmetry", "no_ci_different_f1"], ["RQ2"],
         ["paper §Results Targeted experiment", "MD §9.3", "MD §1 headline 7"]),
    ]
    out = []
    for fid, st, key, cav, rqs, locs in F:
        v = get(R2, key)
        entry = {"id": fid, "statement": st, "sourceKey": key, "caveatIds": cav, "rqIds": rqs, "paperLocations": locs}
        if isinstance(v, dict):
            pt, lo, hi = ci_of(v)
            entry |= {"delta": pt, "ci": [lo, hi], "ciLabel": ci_label(v)}
        else:
            entry |= {"count": v}
        out.append(entry)
    return out


# A2/A3 display labels (the JSON keys and ids stay unchanged), as in scripts/build_master_document.py.
PAIRED_LABEL = {
    "Ablation A (verifier on): final agentic − class-blind + verifier": "Class filter, with verifier: final agentic − class-blind + verifier",
    "Class filter, no verifier: class-aware − class-blind": "Class filter, without verifier: class-aware − class-blind",
    "Verifier, class-blind: ablation A − class-blind": "Verifier, class-blind: class-blind + verifier − class-blind",
    "Ablation C on T1: final agentic − class-aware": "Verifier (ablation C): final agentic − class-aware",
}


def paired(R2):
    out = []
    for k, v in get(R2, "phase4.t1_paired").items():
        for m in ("flag_macro_f1", "collapsed_macro_f1", "coverage"):
            d = v[m]
            out.append({"id": f"t1:{k}:{m}", "label": PAIRED_LABEL.get(k, k), "keyLabel": k, "a": k.split(":")[-1].split("−")[0].strip(), "b": k.split("−")[-1].strip(),
                        "n": v["n_items"], "metric": m, "delta": d["diff"], "ci": d["ci"], "ciLabel": ci_label(d),
                        "sourceKey": f"phase4.t1_paired.{k}.{m}", "preregistered": False, "sameItems": "same items" in k, "family": "T1"})
    for comp, v in get(R2, "phase4.preregistered_comparisons").items():
        for part, metrics in (("judgement", ("judgement_macro_f1", "different_f1", "different_recall")), ("flag", ("flag_macro_f1", "collapsed_macro_f1"))):
            for m in metrics:
                d = v[part][m]
                out.append({"id": f"prereg:{comp}:{m}", "label": comp, "a": "comparator", "b": comp.split("−")[-1].strip(), "n": v[part]["n_items"],
                            "metric": m, "delta": d["diff"], "ci": d["ci"], "ciLabel": ci_label(d),
                            "sourceKey": f"phase4.preregistered_comparisons.{comp}.{part}.{m}", "preregistered": part == "judgement",
                            "sameItems": False, "family": "T1"})
    for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        d = get(R2, f"tables.06_t2_retrieval.p4_pipeline.{s}.paired")
        out.append({"id": f"t2:{s}", "label": f"Class filter ON − OFF, nDCG@10, {s}", "a": "class_aware", "b": "hybrid_rrf",
                    "n": get(R2, f"tables.06_t2_retrieval.p4_pipeline.{s}.n"), "metric": "ndcg@10", "delta": d["diff"], "ci": d["ci"],
                    "ciLabel": ci_label(d), "sourceKey": f"tables.06_t2_retrieval.p4_pipeline.{s}.paired", "preregistered": False,
                    "sameItems": False, "family": "T2", "dataset": s})
    d = get(R2, "tables.08_t3.t3.paired.status_exact_match")
    out.append({"id": "t3:status", "label": "Temporal filter ON − OFF, T3 status exact match", "a": "filter_on", "b": "filter_off", "n": d["n"],
                "metric": "status_exact_match", "delta": d["diff"], "ci": d["ci"], "ciLabel": ci_label(d),
                "sourceKey": "tables.08_t3.t3.paired.status_exact_match", "preregistered": False, "sameItems": False, "family": "T3"})
    for t in ("concatenated - genuine", "adv_negated - genuine", "adv_offtopic - genuine"):
        d = get(R2, f"tables.09_t4.paired.{t}.composite_score")
        out.append({"id": f"t4:{t}", "label": f"RePASs composite, {t}", "a": t.split(" - ")[0], "b": "genuine", "n": d["n"], "metric": "composite_score",
                    "delta": d["mean"], "ci": [d["ci_low"], d["ci_high"]], "ciLabel": ci_label(d),
                    "sourceKey": f"tables.09_t4.paired.{t}.composite_score", "preregistered": True, "sameItems": False, "family": "T4"})
    return out


def ablations(R2):
    rows = get(R2, "tables.10_ablations.rows")
    out = []
    for i, r in enumerate(rows):
        m = re.match(r"([+\-−]?\d+\.\d+) \[([+\-−]?\d+\.\d+), ([+\-−]?\d+\.\d+)\]", r["on_minus_off"])
        f = lambda s: float(s.replace("−", "-"))
        cond = "with verifier" if (r["ablation"] == "A" and r["measure"].startswith("T1")) else None
        out.append({"id": f"{r['ablation']}:{i}", "ablation": r["ablation"], "toggle": r["toggle"], "measure": r["measure"], "n": r["n"],
                    "delta": f(m.group(1)), "ci": [f(m.group(2)), f(m.group(3))], "ciLabel": r["on_minus_off"],
                    "sourceKey": f"tables.10_ablations.rows.{i}", "condition": cond,
                    "circular": r["ablation"] == "B"})
    return out


def systems(R2):
    rm = get(R2, "phase4.comparator.frozen")
    d = [
        ("bm25", "BM25", "retrieval", "bm25s lucene variant, k1 1.5, b 0.75, lower-case alphanumeric tokens.", None, ["bm25"]),
        ("dense", "Dense (bge-base-en-v1.5)", "retrieval", "Exact inner product over 76,188 normalised bge-base-en-v1.5 paragraph embeddings.", None, ["dense"]),
        ("hybrid_rrf", "Hybrid RRF", "retrieval", "Reciprocal rank fusion of BM25 and dense (k = 60).", None, ["bm25", "dense", "rrf"]),
        ("hybrid_minus_source_class", "Hybrid − source class", "retrieval",
         "Class-blind hybrid RRF with every paragraph of the query's own source class removed before fusion (src/retrieval/systems.py).", None,
         ["bm25", "dense", "rrf"]),
        ("class_aware_hybrid", "Class-aware hybrid", "retrieval", "Hybrid RRF restricted to the target class's Directions.", None,
         ["class_filter", "bm25", "dense", "rrf"]),
        ("majority", SYS_NAMES["majority"], "baseline", "Most frequent flag and judgement of the gold set itself (in-sample reference).", None, []),
        ("p2002_candidates", SYS_NAMES["p2002_candidates"], "baseline", "P2-002 matched → counterpart, below threshold → none; cannot express shared vs class-specific.",
         None, ["p2002"]),
        ("class_blind", SYS_NAMES["class_blind"], "t1", "LLM judgement over class-blind hybrid retrieval.", "gemini-3.5-flash-lite", ["rrf", "llm"]),
        ("class_aware", SYS_NAMES["class_aware"], "t1", "LLM judgement over class-aware hybrid retrieval.", "gemini-3.5-flash-lite", ["class_filter", "rrf", "llm"]),
        ("final_agentic", SYS_NAMES["final_agentic"], "t1", "Class filter + LLM judgement + NLI verifier that retries or abstains.", "gemini-3.5-flash-lite",
         ["class_filter", "rrf", "llm", "verifier"]),
        ("ablation_a", SYS_NAMES["ablation_a"], "t1", "Class-blind LLM plus the NLI verifier (internal id ablation_a).", "gemini-3.5-flash-lite",
         ["rrf", "llm", "verifier"]),
        ("long_context", SYS_NAMES["long_context"], "t1", "Every Direction of the compared classes in one prompt, 100K-token cap; 102 of 106 items answered.",
         "gemini-3.5-flash-lite", ["long_context"]),
        ("comparator", SYS_NAMES["comparator"], "t1", "13-field extraction on both sides; a fixed rule (same > different > none) decides. Frozen before any T1 run.",
         rm.get("model"), ["comparator"]),
    ]
    return [{"id": i, "displayName": n, "family": f, "description": desc, "model": m, "componentIds": comp,
             "frozenPromptSha": rm["sha256"] if i == "comparator" else None} for i, n, f, desc, m, comp in d]


def metrics(R2):
    out = []
    for s in ("majority", "p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a", "long_context"):
        b = f"phase4.t1_systems.{s}"
        for m in ("flag_macro_f1", "collapsed_macro_f1", "judgement_macro_f1", "coverage"):
            d = get(R2, f"{b}.{m}")
            out.append({"systemId": s, "datasetId": "t1_gold_v1", "metric": m, "value": d["value"], "ci": d["ci"], "ciLabel": ci_label(d),
                        "n": get(R2, f"{b}.n_items"), "sourceKey": f"{b}.{m}"})
        out.append({"systemId": s, "datasetId": "t1_gold_v1", "metric": "different_f1", "value": get(R2, f"phase4.t1_different.{s}.different_f1"),
                    "ci": None, "ciLabel": None, "n": get(R2, f"{b}.n_items"), "sourceKey": f"phase4.t1_different.{s}.different_f1"})
    b = "phase4.comparator.metrics"
    for m in ("flag_macro_f1", "collapsed_macro_f1", "judgement_macro_f1", "coverage"):
        d = get(R2, f"{b}.{m}")
        out.append({"systemId": "comparator", "datasetId": "t1_gold_v1", "metric": m, "value": d["value"], "ci": d["ci"], "ciLabel": ci_label(d),
                    "n": get(R2, f"{b}.n_items"), "sourceKey": f"{b}.{m}"})
    out.append({"systemId": "comparator", "datasetId": "t1_gold_v1", "metric": "different_f1", "value": get(R2, "phase4.comparator.different.different_f1"),
                "ci": None, "ciLabel": None, "n": get(R2, f"{b}.n_items"), "sourceKey": "phase4.comparator.different.different_f1"})
    for ds in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        for s in ("bm25", "dense", "hybrid_rrf", "hybrid_minus_source_class", "class_aware"):
            k = f"tables.06_t2_retrieval.p3001.{ds}.systems.{s}.ndcg"
            d = get(R2, k)
            out.append({"systemId": "class_aware_hybrid" if s == "class_aware" else s, "datasetId": ds, "metric": "ndcg@10", "value": d["mean"],
                        "ci": [d["ci_low"], d["ci_high"]], "ciLabel": ci_label(d), "n": d["n"], "sourceKey": k})
    for side in ("on", "off"):
        k = f"tables.08_t3.t3.{side}.status_exact_match"
        d = get(R2, k)
        out.append({"systemId": f"temporal_filter_{side}", "datasetId": "t3", "metric": "status_exact_match", "value": d["value"], "ci": d["ci"],
                    "ciLabel": ci_label(d), "n": d["n"], "sourceKey": k, "circular": side == "on"})
    for t in ("genuine", "concatenated", "adv_negated", "adv_offtopic"):
        k = f"tables.09_t4.by_type.{t}.composite_score"
        d = get(R2, k)
        out.append({"systemId": t, "datasetId": "t4", "metric": "repass_composite", "value": d["mean"], "ci": [d["ci_low"], d["ci_high"]],
                    "ciLabel": ci_label(d), "n": d["n"], "sourceKey": k})
    return out


def reliability(R2):
    irr = "tables.05_t1_benchmark.irr.fleiss"
    rt = "tables.05_t1_benchmark.retest.phase2.all_25"
    tr = "tables.05_t1_benchmark.timed_relabel"
    rows = [("fleiss_class_row", "Separate 30-item set, 3 raters, independent before adjudication", "Fleiss κ", "class-row judgement", f"{irr}.per_class_judgement", None),
            ("fleiss_flag", "Separate 30-item set, 3 raters", "Fleiss κ", "differential flag", f"{irr}.differential_flag", None),
            ("fleiss_not_obligation", "Separate 30-item set, 3 raters", "Fleiss κ", "not-obligation", f"{irr}.not_obligation", None),
            ("retest_flag", "Blind test–retest (rater_1, supplementary)", "Cohen κ", "differential flag", f"{rt}.differential_flag", "retest_short_gap"),
            ("retest_class_row", "Blind test–retest (rater_1, supplementary)", "Cohen κ", "class-row judgement", f"{rt}.per_class_judgement", "retest_short_gap"),
            ("timed_flag", "Timed blind re-label, 20 single-pass items (evidence only)", "Cohen κ", "differential flag", f"{tr}.differential_flag", None),
            ("timed_class_row", "Timed blind re-label (evidence only)", "Cohen κ", "class-row judgement", f"{tr}.per_class_judgement", None)]
    out = []
    for i, design, stat, what, key, cav in rows:
        d = get(R2, key)
        pt, lo, hi = ci_of(d)
        out.append({"id": i, "design": design, "raters": "rater_1–rater_3" if "fleiss" in i else "rater_1", "statistic": stat, "target": what,
                    "value": pt, "ci": [lo, hi], "ciLabel": ci_label(d), "n": d["n_items"], "nUnits": d.get("n_units"), "inGold": False,
                    "sourceKey": key, "caveat": cav, "ciCrossesZero": lo <= 0 <= hi})
    return out


def construction_steps(R2):
    T = "tables"
    s = [
        ("P1-004", "Corpus repair to the full Direction set", ["RBI listing"], ["381 Directions", "76,188 paragraphs"],
         [f"{T}.01_corpus.directions", f"{T}.01_corpus.paragraphs", f"{T}.01_corpus.p1004_recovered.previously_missing"], []),
        ("P2-001", "Obligation candidate extraction (rules v1–v4)", ["corpus"], ["28,694 candidates"],
         [f"{T}.02_candidates.paragraphs_with_cue", f"{T}.02_candidates.candidates_kept", f"{T}.02_candidates.precision_rounds.3.precision"], ["rules_v4"]),
        ("P2-002", "Cross-class matching (bge-base + lexical)", ["candidates"], ["matched / below threshold per class"],
         [f"{T}.03_matching.threshold.value", f"{T}.03_matching.overall.counterpart_rate.rate"], ["threshold"]),
        ("P2-003", "Supplementary sources and alignment decisions", ["FAQ", "enforcement", "Amendment Directions"], ["T3 inputs", "weak labels"],
         [f"{T}.04_supplementary.decisions.0.rate", f"{T}.04_supplementary.decisions.1.rate"], ["p2003_faq", "p2003_enf"]),
        ("P2-004", "T1 sample, single-expert labelling, retest, separate 30-item IRR set, gold v1", ["candidates"], ["t1_validated_v1 (106)"],
         [f"{T}.05_t1_benchmark.sample", f"{T}.05_t1_benchmark.validated", f"{T}.05_t1_benchmark.rejected"], ["single_expert_gold"]),
        ("P3-001", "LLM client, T2 relevance sets, retrieval and T1 baselines", ["gold v1", "corpus"], ["T2 sets", "baselines"],
         [f"{T}.06_t2_retrieval.p3001.t2_xclass_t1.n_scored"], []),
        ("P3-002", "T4 RePASs audit and exploratory repair", ["30 questions"], ["T4 scores"], [f"{T}.09_t4.n_questions"], []),
        ("P4-001", "T3 set, class- and date-aware pipeline, system runs, ablations A–C, long-context 100K", ["gold v1"], ["system predictions"],
         [f"{T}.08_t3.built", f"{T}.08_t3.scored"], ["llm_100k"]),
        ("P5-001", "Results consolidation, dataset card, pointer-only release, error analysis", ["all results"], ["release/"], [], []),
        ("Final", "Comparator development + freeze, sealed predictions, Phase 4 scoring on gold v1, master document, paper", ["dev set", "gold v1"],
         ["results_v2.json"], ["phase4.comparator.different.different_f1"], ["comparator_freeze"]),
    ]
    out = []
    for i, title, inp, outp, keys, dec in s:
        out.append({"id": i, "title": title, "inputs": inp, "outputs": outp,
                    "metrics": [{"key": k, "value": get(R2, k)} for k in keys], "decisionIds": dec})
    return out


def decisions(R2):
    dd = [
        ("rules_v4", "Candidate rules v4 kept for extraction", "rules v1–v3", "Precision rose to 0.929 [0.774, 0.980] on round 4.", "P2-001",
         "tables.02_candidates.precision_rounds"),
        ("threshold", "Matching threshold 0.757567", "other score bands", "Highest band with acceptable counterpart rate (gates passed).", "P2-002",
         "tables.03_matching.threshold"),
        ("p2003_faq", "FAQ: validation_or_motivation_only", "use as labels", "Alignment 5/30 clean under the locked rule.", "P2-003", "tables.04_supplementary.decisions.0"),
        ("p2003_enf", "Enforcement: direction_level_weak_label_only", "paragraph labels", "Alignment 16/30 clean under the locked rule.", "P2-003",
         "tables.04_supplementary.decisions.1"),
        ("single_expert_gold", "Gold is single-expert; reliability reported on a separate 30-item set", "second raters on gold", "Annotator availability; disclosed.",
         "P2-004", "tables.05_t1_benchmark.irr"),
        ("llm_100k", "Long-context at a uniform 100K cap; the 150K run superseded", "150K cap", "The 150K run stopped during an API outage.", "P4-001",
         "tables.07_t1_systems.long_context_same_items.cap"),
        ("comparator_freeze", "Comparator prompt + rule frozen by sha256 before any T1 run", "tune on gold", "Pre-registration (amendment 3).", "Final",
         "phase4.comparator.frozen"),
        ("scope_ladder", "All seven Scope Ladder cuts applied (incl. no UI in the release)", "—", "Time box for the 10 Oct deadline.", "P5-001", None),
    ]
    return [{"id": i, "decision": d, "alternatives": a, "rationale": r, "record": rec, "sourceKey": k} for i, d, a, r, rec, k in dd]


def future_work(md):
    sec = next(s for s in md_sections(md) if s["id"] == "12")
    rows = md_table(sec["text"])
    extra = {
        1: (["single_expert", "retest_short_gap"], [], ["reliability:retest_flag", "reliability:retest_class_row", "MD §6", "paper §Annotation", "tab_reliability"],
            ["What washout (days) is acceptable for the venue?"], ["F1", "F2", "F3", "F4", "F5", "F7"], []),
        2: (["single_expert"], [1], ["gold v1 → v2", "every T1 metric", "tab_t1_systems", "tab_comparator", "MD §9.2–9.9", "paper §Results", "calibration"],
            ["Who are the second raters?", "Adjudication protocol?"], ["F2", "F3", "F4", "F5", "F7"], ["F3", "F7"]),
        3: (["by_construction"], [], ["tab_t2", "MD §9.1", "T1 judgement runs"], ["Which reranker revision?"], ["F1"], []),
        4: (["flash_lite"], [], ["all T1 systems", "comparator", "tab_t1_systems", "tab_comparator", "calibration"], ["Budget?"], ["F3", "F7"], ["F3", "F4"]),
        5: ([], [], ["related-work positioning"], ["Licence for redistribution?"], [], []),
        6: (["circular", "t3_parser_defect"], [], ["T3 results", "ablation B", "tab_t3_t4_ablation", "MD §9.5"], ["Who annotates temporal status?"], [], []),
        7: (["small_n_t4", "repair_exploratory"], [], ["T4 results", "tab_t3_t4_ablation", "MD §9.6"], ["Second rater for T4?"], ["F6"], []),
        8: ([], [], ["new external table"], ["Data access"], [], []),
        9: ([], [], ["pipeline code only (no reported results)"], ["Python 3.13 env"], [], []),
        10: ([], [], ["T3 inputs", "weak labels"], ["Cleaning effort"], [], []),
        11: ([], [], ["ui/ (this Command Center)"], [], [], []),
    }
    out = []
    for r in rows:
        rank = int(r["Rank"])
        lim, dep, blast, oq, strengthens, could_overturn = extra.get(rank, ([], [], [], [], [], []))
        out.append({"rank": rank, "item": r["Item"], "what": r["What"], "why": r["Why it matters"], "effort": r["Rough effort"],
                    "limitationIds": lim, "dependsOn": dep, "blastRadius": blast, "openQuestions": oq, "strengthens": strengthens,
                    "couldOverturn": could_overturn})
    return out


def limitations(md):
    sec = next(s for s in md_sections(md) if s["id"] == "11")
    out = []
    fw = {"Size": [2], "Single-expert gold": [2, 1], "Short-interval retest": [1], "T2 construction bias": [3], "T3": [6], "Historical text": [6],
          "T4": [7], "The RePASs repair": [7], "Models": [4]}
    for line in sec["text"].splitlines():
        m = re.match(r"- \*\*(.+?):?\*\*:? ?(.*)", line.strip())
        if m:
            name = m.group(1).rstrip(":")
            out.append({"id": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"), "title": name, "text": m.group(2), "futureWorkIds": fw.get(name, [])})
    return out


def submission_tasks():
    return [
        {"id": "ST-PROSE", "title": "Authors rewrite the paper prose by hand (AI content < 20%)", "due": "2026-10-04", "dependsOn": [], "status": "open",
         "verifyCommand": "python3 scripts/check_paper.py --allow-placeholders", "note": "After this date main.tex is never regenerated; use paper/aisigh/PATCHLIST_v1.md."},
        {"id": "ST-OVERLEAF", "title": "Overleaf compile (pdfLaTeX) + page check ≤ 6 pages", "due": "2026-10-05", "dependsOn": ["ST-PROSE"], "status": "open",
         "verifyCommand": "python3 scripts/build_paper_draft.py --zip   # only before the 10-04 rewrite"},
        {"id": "ST-AUDIT", "title": "Number audit: every number matches results_v2.json", "due": "2026-10-06", "dependsOn": ["ST-PROSE"], "status": "open",
         "verifyCommand": "python3 scripts/scan_documents.py"},
        {"id": "ST-DOI", "title": "Zenodo deposit → DOI replaces \\placeholder{Zenodo DOI}", "due": "2026-10-07", "dependsOn": ["ST-AUDIT"], "status": "open",
         "verifyCommand": "python3 scripts/check_paper.py"},
        {"id": "ST-AUTHOR-EMAILS", "title": "Fill the 3 author emails (\\placeholder{email})", "due": "2026-10-07", "dependsOn": [], "status": "open",
         "verifyCommand": "python3 scripts/check_paper.py"},
        {"id": "ST-REPRO", "title": "Reproducibility check (tests, release check, tables)", "due": "2026-10-07", "dependsOn": [], "status": "open",
         "verifyCommand": "python3 -m pytest -q -o addopts= -p no:cacheprovider && python3 scripts/release_check.py && python3 scripts/build_tables.py --check"},
        {"id": "ST-SIMILARITY", "title": "Similarity (< 25% incl. references; screened at submission) and AI-content (< 20%) checks", "due": "2026-10-08",
         "dependsOn": ["ST-PROSE"], "status": "open", "verifyCommand": None},
        {"id": "ST-PDF", "title": "Final PDF (IEEE template, ≤ 6 pages, PDF only)", "due": "2026-10-09", "dependsOn": ["ST-OVERLEAF", "ST-AUDIT", "ST-DOI", "ST-AUTHOR-EMAILS", "ST-SIMILARITY"],
         "status": "open", "verifyCommand": "python3 scripts/check_paper.py"},
        {"id": "ST-CMT", "title": "Submit on CMT (AISIGHSD2026); authors and order cannot change after submission", "due": "2026-10-10", "dependsOn": ["ST-PDF"],
         "status": "open", "verifyCommand": None},
    ]


def gaps():
    G_ = [
        ("G-01", "reliability", "partial", "Gold with independent second-rater labels", "Single-expert gold; κ on a separate 30-item sample", ["MD §6"],
         "Gold has no second-rater label", "Future Work #2", None),
        ("G-02", "validity", "needs_validation", "Independent T3 gold", "Gold and filter share one parser; old-words defect", ["MD §7", "MD §9.5"], "Circular by construction",
         "Future Work #6", None),
        ("G-03", "rq", "partial", "RQ3 repair that tracks human faithfulness", "Repair ρ −0.126; not usable", ["tables.09_t4.human.all_rated.spearman_repaired_vs_faithful"],
         "Repair half of RQ3 not achieved", "Future Work #7", None),
        ("G-04", "analysis", "missing", "Human error-category pass on `different` errors", "Not done", ["MD §9.8"], "Stated in MD", "Label error categories (authors' labelling order, step 1)", None),
        ("G-05", "submission", "missing", "Zenodo DOI + 3 author emails", "4 \\placeholder{} in main.tex", ["paper/aisigh/main.tex"], "check_paper.py", "Authors fill them (A10/A16)",
         "listed (A10, A16)"),
        ("G-06", "terminology", "complete", "One meaning per label", "\"Ablation A\" now names the toggle only", ["MD §8", "MD §9.3"], "R8", "—", "A2"),
        ("G-07", "terminology", "complete", "Condition stated for −0.050 / −0.049", "Both carry with/without verifier", ["MD §9.7"], "R8", "—", "A3"),
        ("G-08", "rq", "complete", "RQ1 operationalisation stated", "Sentence added in MD §2 and paper", ["MD §2"], "—", "—", "A6"),
        ("G-09", "scoring", "complete", "Abstention scoring documented", "MD §9.2, paper §Results, A11 note", ["src/rag/analysis.py"], "R12", "—", "A4, A11"),
        ("G-10", "statistics", "partial", "CIs on `different` F1", "Note \"CIs not computed\"; follow-up open", ["phase4.t1_different"], "R13", "Add bootstrap CIs (follow-up)", "A5"),
        ("G-11", "terminology", "complete", "Guideline versions explained", "v3 family, rules v3.1–v3.10, derivation v3.6", ["MD §5"], "R8", "—", "A8"),
        ("G-12", "terminology", "complete", "\"Hybrid − source class\" defined", "Defined in MD §8/§9.1 and paper", ["src/retrieval/systems.py"], "—", "—", "A7"),
        ("G-13", "baseline", "complete", "Majority flagged in-sample", "Note added", ["MD §9.2"], "—", "—", "A9"),
        ("G-14", "formatting", "complete", "Clean references", "Fixed + unit test", ["MD §15"], "—", "—", "A1"),
        ("G-15", "venue", "partial", "Venue rules verified", "Site read 2026-10-03; CMT behind login", ["reports/final/venue_check_v1.md"], "A15", "Confirm CMT form fields when logged in", "A15"),
        ("G-16", "provenance", "complete", "No main-text number from the superseded 150K run", "Verified: none of 34 150K-only values appear", ["tables.07_t1_systems.appendix_150k"], "ingest check", "—", "verified"),
        ("G-17", "record", "unclear", "Faculty guide named in the record", "Not named", ["MD v2"], "—", "Authors add the guide's name if required", None),
        ("G-18", "calibration", "partial", "Confidence with tight intervals", "412 single-expert units; wide CIs", ["ui/docs/CALIBRATION.md"], "R14", "More gold (Future Work #2)", None),
        ("G-19", "venue", "conflicting", "One camera-ready date", "30/11/2026 (home) vs \"5th Jan 2026\" (camera-ready page)", ["reports/final/venue_check_v1.md"], "A15", "Ask organisers", None),
        ("G-20", "venue", "conflicting", "Page plan matches the CFP", "Checklist: paid 7-page fallback; CFP: 4–6 pages at submission (user: 6 is the hard limit)",
         ["reports/final/venue_check_v1.md"], "A15", "Keep ≤ 6 pages", None),
        ("G-21", "venue", "missing", "Camera-ready steps on the checklist", "PDF eXpress 70672X, copyright notice, eCF, supplementary ZIP, no-show rule missing",
         ["reports/final/venue_check_v1.md"], "A15", "Add to the post-acceptance checklist", None),
        ("G-22", "audit", "needs_validation", "Every document number matched", "Auditor reads public sources only; private constants unseen", ["ui/docs/DECISIONS.md D-07"], "design",
         "Run scripts/scan_documents.py (it reads the constants)", None),
        ("G-23", "calibration", "partial", "BM25/dense agreement signal", "Not available offline", ["ui/docs/DECISIONS.md D-04"], "data", "Store per-unit rankings in a future run", None),
        ("G-24", "formatting", "unclear", "Readable LLM settings in MD §8", "Thinking config printed as a raw dict", ["MD §8"], "R8", "Format the dict in build_master_document.py", None),
        ("G-25", "calibration", "partial", "Dev predictions for every system", "Comparator only on dev", ["data/rag_runs/comparator_dev_irr30"], "data", "Run systems on dev (costs quota)", None),
        ("G-26", "venue", "missing", "Similarity check before submission", "Checklist schedules it for camera-ready only; CFP screens at submission", ["reports/final/venue_check_v1.md"],
         "A15", "Run similarity before 10 Oct", None),
        ("G-28", "privacy", "needs_validation", "No annotator names in publishable results files",
         "reports/results_v2.json (frozen, publishable) contains annotator first names: tables.05_t1_benchmark.pilot_fleiss_flag.raters and the T3 "
         "precision_post_fix_in_sample basis text / note keys", ["reports/results_v2.json"], "UI ingest privacy test",
         "Authors decide whether to pseudonymise in a results_v3 (the UI redacts its copy)", None),
        ("G-27", "scoring", "complete", "Scoring asymmetry stated", "A11 note in MD §9.2, §10 and paper", ["MD §9.2"], "R12", "—", "A11"),
    ]
    return [{"id": i, "category": c, "status": st, "expected": e, "actual": a, "sourceRefs": s, "reasonDetected": r, "suggestedFix": f, "fixedInPartA": p}
            for i, c, st, e, a, s, r, f, p in G_]


def recommendations():
    return [
        {"id": "REC-1", "tier": "REQUIRED", "priority": "MUST", "title": "Fill 3 emails + DOI, then pass check_paper.py", "why": "4 placeholders block the final PDF",
         "evidence": ["gap:G-05"], "unblocks": ["ST-PDF"]},
        {"id": "REC-2", "tier": "REQUIRED", "priority": "MUST", "title": "Run the similarity check before 10 Oct", "why": "The CFP screens every submission before review",
         "evidence": ["gap:G-26"], "unblocks": ["ST-CMT"]},
        {"id": "REC-3", "tier": "REQUIRED", "priority": "MUST", "title": "Keep the PDF ≤ 6 pages after the prose rewrite", "why": "6 pages is the hard limit (CFP 4–6)",
         "evidence": ["gap:G-20"], "unblocks": ["ST-PDF"]},
        {"id": "REC-4", "tier": "ENHANCEMENT", "priority": "SHOULD", "title": "Add bootstrap CIs for `different` F1 (follow-up)", "why": "R13: siblings have CIs",
         "evidence": ["gap:G-10"], "unblocks": []},
        {"id": "REC-5", "tier": "NEW_OPPORTUNITY", "priority": "COULD", "title": "Human-review queue: route low-confidence comparator verdicts to an analyst",
         "why": "Selective prediction as a workflow", "evidence": ["calibration"], "unblocks": []},
        {"id": "REC-6", "tier": "NEW_OPPORTUNITY", "priority": "COULD", "title": "Annotation workbench for Future Work #1–#2 with enforced washout",
         "why": "Removes the short-retest-gap caveat", "evidence": ["gap:G-01"], "unblocks": ["fw:1", "fw:2"]},
    ]


def snapshot_diff(R1, R2):
    a = dict(S.flatten(R1.get("tables", {})))
    b = dict(S.flatten(R2.get("tables", {})))
    changed = [{"key": "tables." + k.replace("[", ".").replace("]", ""), "v1": a[k], "v2": b[k], "kind": "changed"}
               for k in sorted(a.keys() & b.keys()) if abs(a[k] - b[k]) > 1e-12]
    removed = [{"key": "tables." + k, "v1": a[k], "v2": None, "kind": "removed"} for k in sorted(a.keys() - b.keys())]
    added = [{"key": "tables." + k, "v1": None, "v2": b[k], "kind": "added"} for k in sorted(b.keys() - a.keys())]
    top_v1 = sorted(R1.keys())
    top_v2 = sorted(R2.keys())
    return {"v1Sha": C.sha256(R1P), "v2Sha": C.sha256(R2P), "tablesNumericLeaves": len(a), "changed": changed[:200], "removed": removed[:200],
            "added": added[:200], "topLevelV1": top_v1, "topLevelV2": top_v2, "newSections": [k for k in top_v2 if k not in top_v1],
            "phase4Keys": sorted(R2.get("phase4", {}).keys())}


def frozen_ledger():
    rows = [{"path": p, "expectedSha256": e, "expectedSource": "Step 0 list (run instructions, 2026-10-03)"} for p, e in STEP0.items()]
    fz = load(ROOT / "configs/comparator_v1/FROZEN.json")
    for name, e in fz["sha256"].items():
        p = f"src/rag/{name}" if name.endswith(".py") else f"configs/comparator_v1/{name}"
        rows.append({"path": p, "expectedSha256": e, "expectedSource": "configs/comparator_v1/FROZEN.json"})
    rec = json.loads(next((C.RUNS / "t1_class_aware").glob("t1_*.json")).read_text())
    for name, e in rec["prompt_sha256"].items():
        rows.append({"path": f"configs/p4_prompts_v1/{name}", "expectedSha256": e, "expectedSource": "prompt_sha256 recorded in data/rag_runs/t1_class_aware"})
    for r in rows:
        p = ROOT / r["path"]
        r["actualSha256"] = C.sha256(p) if p.exists() else None
        r["status"] = "unreadable" if r["actualSha256"] is None else ("match" if r["actualSha256"] == r["expectedSha256"] else "mismatch")
    return rows, fz


def ci_vectors(R2):
    vec = []
    for p in [x for x in paired(R2)]:
        lo, hi = p["ci"]
        vec.append({"point": p["delta"], "lo": lo, "hi": hi, "signed": True, "reading": True,
                    "expected": fmt_ci(p["delta"], lo, hi, signed=True, reading=True)})
    for m in metrics(R2):
        if m["ci"]:
            vec.append({"point": m["value"], "lo": m["ci"][0], "hi": m["ci"][1], "signed": False, "reading": False,
                        "expected": fmt_ci(m["value"], m["ci"][0], m["ci"][1])})
    for x in (0.0, -0.0003, 0.0004, -0.05, 0.4514, 1.0):
        vec.append({"point": x, "lo": x - 0.0002, "hi": x + 0.0002, "signed": True, "reading": True,
                    "expected": fmt_ci(x, x - 0.0002, x + 0.0002, signed=True, reading=True)})
    return vec


# ---------------------------------------------------------------------------------------------------------------------

NAME_RE = re.compile(r"karan|akash|meer", re.I)  # substring match: also catches keys such as `karan_note`


def redact_names(obj, path=""):
    """The UI never shows annotator names (raters appear only as rater_N). The frozen results file carries a few in strings and
    one key (`karan_note`); the snapshot's embedded copy redacts them. Numbers and numeric key paths are unchanged."""
    if isinstance(obj, dict):
        return {NAME_RE.sub("annotator", k): redact_names(v, f"{path}.{k}") for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_names(v, path) for v in obj]
    if isinstance(obj, str):
        return NAME_RE.sub("[annotator]", obj)
    return obj


def main() -> int:
    for p in (R2P, R1P, GOLD):
        if C.sha256(p) != STEP0[rel(p)]:
            raise SystemExit(f"STOP: {rel(p)} sha256 does not match the Step 0 value")
    R2, R1 = load(R2P), load(R1P)
    md = MD2.read_text(encoding="utf-8")
    gold, items, units, cmp, cands_by_item = build_units(R2)
    pointers, cmp_fields = build_pointers(items, units, cmp, cands_by_item)
    classes, families, directions, cells, corpus_meta = build_corpus(R2)
    ledger, frozen = frozen_ledger()
    sources = [R2P, R1P, MD2, TEX, *sorted(TABLES.glob("tab_*.tex")), VENUE, GOLD, GOLD_PUBLIC, EA, ROOT / "release/data/documents.jsonl",
               ROOT / "release/data/matrix/matrix_v1.jsonl", ROOT / "configs/comparator_v1/FROZEN.json",
               ROOT / "data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md", *[ROOT / p for p in PUBLIC_METRICS.values()]]
    sections = md_sections(md)
    snap = {
        "meta": {"generatedUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "generator": "ui/scripts/ingest.py",
                 "sources": [{"path": rel(p), "sha256": C.sha256(p)} for p in sources],
                 "wordLimit": C.WORD_LIMIT, "excerptWords": C.EXCERPT_WORDS, "fixture": False,
                 "deadline": "2026-10-10T23:59:00+05:30", "partAStatus": part_a_status(),
                 "redactions": "annotator names in the embedded results copy replaced by [annotator] (raters appear only as rater_N)"},
        "results": redact_names(R2),
        "rqs": [{"id": k, "label": v[0], "text": v[1]} for k, v in RQ_TEXT.items()],
        "findings": findings(R2), "caveats": caveats(), "paired": paired(R2), "ablations": ablations(R2), "systems": systems(R2),
        "metrics": metrics(R2), "reliability": reliability(R2), "constructionSteps": construction_steps(R2), "decisions": decisions(R2),
        "futureWork": future_work(md), "limitations": limitations(md), "submissionTasks": submission_tasks(), "gaps": gaps(),
        "recommendations": recommendations(), "placeholders": build_placeholders(), "venue": build_venue(), "claims": build_claims(R2),
        "diff": snapshot_diff(R1, R2), "frozen": ledger, "frozenComparator": frozen,
        "entityClasses": classes, "subjectFamilies": families, "directions": directions, "matrix": cells, "corpusMeta": corpus_meta,
        "t1Items": items, "classUnits": units, "pointers": pointers, "comparatorFields": cmp_fields,
        "masterSections": [{"id": s["id"], "title": s["title"], "text": s["text"]} for s in sections if s["id"] != "15"],
        "changesV1": [l[2:] for l in next(s for s in sections if s["id"] == "changes-from-v1")["text"].splitlines() if l.startswith("- ")],
        "guidelineRules": guideline_rules(),
    }
    snap = redact_names(snap)  # whole snapshot: strings and keys (claim key paths included); numbers untouched
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":"), default=float), encoding="utf-8")
    CI_VECTORS.write_text(json.dumps(ci_vectors(R2), indent=0), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1e6:.2f} MB; items {len(items)}, units {len(units)}, pointers {len(pointers)}, "
          f"claims {len(snap['claims'])}, directions {len(directions)}, matrix cells {len(cells)}")
    return 0


def part_a_status():
    return [
        {"id": f"A{i}", "status": "present", "note": n} for i, n in [
            (1, "References clean (accent map + unit test)"), (2, "\"Ablation A\" = toggle only; system = class-blind + verifier"),
            (3, "Class-filter conditions stated (−0.050 without / −0.049 with verifier)"), (4, "Abstention scoring stated"),
            (5, "\"CIs not computed\" note on `different` F1"), (6, "RQ1 operationalisation sentence"), (7, "Hybrid − source class defined"),
            (8, "Guideline versions explained"), (9, "Majority flagged in-sample"), (11, "Scoring-asymmetry note (MD §9.2, §10, paper, T1 table)"),
            (12, "scan_documents / dossier point at MD v2"), (13, "deliverables_2026-10-03 rebuilt"), (14, "Prompt copied to docs/prompts/"),
            (15, "Venue check written (reports/final/venue_check_v1.md)")]] + [
        {"id": "A10", "status": "listed", "note": "3 author emails + Zenodo DOI left as \\placeholder{} (authors' action)"},
        {"id": "A16", "status": "listed", "note": "Placeholders not invented; listed for the authors"}]


def guideline_rules():
    text = (ROOT / "data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md").read_text(encoding="utf-8")
    names = re.compile(r"\s*\([^)]*\b(?:Karan|Akash|Meer)\b[^)]*\)|\b(?:Karan|Akash|Meer)\b", re.I)  # raters appear only as rater_N
    return [{"id": m.group(1), "title": names.sub("", m.group(2)).strip()} for m in re.finditer(r"^## (v3\.\d+) (.+)$", text, re.M)]


if __name__ == "__main__":
    raise SystemExit(main())
