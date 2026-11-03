#!/usr/bin/env python3
"""P5-001 task 1: consolidate every reported metric into reports/results_v1.json and reports/tables/*.md.

    python3 scripts/build_tables.py            # all tables
    python3 scripts/build_tables.py --check    # rebuild in memory and fail if the files on disk differ

Every number is re-read from the phase metrics files; nothing is retyped. Every CI label and bound comes from
src/eval/ci_format.py. Per-class figures are shown only where n >= 5; smaller classes are listed as insufficient n.
Raters appear as rater_1..rater_3 (mapping in gitignored reports/private/). The output is deterministic (no clocks).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.eval.ci_format import ci_reading, fmt_bound, fmt_ci  # noqa: E402
from src.release.pseudonym import load_map  # noqa: E402

RATER, _ = load_map()  # name -> rater id, from gitignored reports/private/ only (identity without it)
MIN_N = 5


class MissingSource(RuntimeError):
    pass


# Sources outside the public tree have public copies: small provenance files in release/provenance/ (copied,
# pseudonymised, by scripts/build_release.py) and the pointer-only T1 set. A public clone rebuilds every table from these.
PUBLIC_COPY = {"data/benchmark/t1/t1_validated_v1.jsonl": "release/data/t1/validated.jsonl"}
PROVENANCE = ("data/supplementary/p2003_source_decisions_v1.json", "data/supplementary/p2003_metrics_v1.json",
              "data/benchmark/t3/t3_build_v1.json", "data/benchmark/t3/t3_spotcheck_receipt_v1.json",
              "data/benchmark/t3/t3_spotcheck2_receipt_v1.json", "data/benchmark/t3/t3_dropped_after_check2_v1.json",
              "data/benchmark/t4/t4_questions_run_v1.json", "data/benchmark/t4/superseded/t4_genuine_run_v1_pre_trimfix.json")


def load(rel: str) -> Any:
    p = ROOT / rel
    if not p.exists():
        alt = PUBLIC_COPY.get(rel) or (f"release/provenance/{Path(rel).name}" if rel in PROVENANCE else None)
        if alt and (ROOT / alt).exists():
            p = ROOT / alt
    if not p.exists():
        raise MissingSource(f"STOP: required source file missing: {rel}")
    if p.suffix == ".jsonl":
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return json.loads(p.read_text(encoding="utf-8"))


def rate(k: int, n: int, w: list[float] | None) -> str:
    base = f"{k}/{n} = {k / n:.3f}" if n else f"{k}/{n}"
    return f"{base} (Wilson 95% [{fmt_bound(w[0], signed=False)}, {fmt_bound(w[1], signed=False)}])" if w else base + " (point estimate)"


def ci(v: float | None, lo: float | None, hi: float | None, signed: bool = False, reading: bool = False) -> str:
    if v is None:
        return "n/a"
    if lo is None or hi is None:
        return (f"{v:+.3f}" if signed else f"{v:.3f}") + " (point estimate)"
    return fmt_ci(v, lo, hi, signed=signed, reading=reading)


def kappa(block: dict | None) -> str:
    if not block or block.get("kappa") is None:
        return "n/a"
    b = block.get("bootstrap") or block.get("kappa_bootstrap_ci95") or {}
    c = b.get("ci95")
    units = block.get("n_units", block.get("n_items"))
    return (fmt_ci(block["kappa"], c[0], c[1]) if c else f"{block['kappa']:.3f} (point estimate)") + \
        f" (n = {block.get('n_items')} items, {units} units)"


def table(header: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def pd(v: dict) -> str:
    """A paired-difference block {diff, ci} with its reading."""
    return fmt_ci(v["diff"], v["ci"][0], v["ci"][1], signed=True, reading=True)


def b(v: dict | None) -> str:
    """A bootstrap block {value, ci, n}."""
    if not v or v.get("value") is None or v["value"] != v["value"]:
        return "n/a"
    return fmt_ci(v["value"], v["ci"][0], v["ci"][1])


def mb(v: dict) -> str:
    """A P3-001/P3-002 bootstrap block {mean, ci_low, ci_high}."""
    return fmt_ci(v["mean"], v["ci_low"], v["ci_high"])


def mpd(v: dict) -> str:
    return fmt_ci(v["mean"], v["ci_low"], v["ci_high"], signed=True, reading=True)


# --------------------------------------------------------------------------------------------------------------------


def t01_corpus() -> tuple[dict, str]:
    cand = load("reports/p2001_candidate_metrics_v4.json")
    pre = load("data/supplementary/p2003_metrics_v1.json")["preflight"]
    matrix = load("data/matrix/matrix_v1_summary.json")
    ec = load("data/metadata/entity_classes.json")
    sf = load("data/metadata/subject_families.json")
    manifest = load("data/metadata/document_manifest.jsonl")
    cfg = __import__("yaml").safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    core = set(cfg["matching"]["core_entity_classes"])
    with (ROOT / "reports" / "p1004_missing_documents.csv").open(encoding="utf-8") as h:
        missing_rows = list(csv.DictReader(h))
    import re

    m_rec = re.search(r"Recovered: (\d+) previously-missing \+ (\d+) newly-listed", (ROOT / "reports" / "p1004_audit_bundle.md").read_text(encoding="utf-8"))
    if not m_rec:
        raise MissingSource("STOP: recovery counts not found in reports/p1004_audit_bundle.md")
    rec = (int(m_rec.group(1)), int(m_rec.group(2)))
    res = {
        "p1004_recovered": {"previously_missing": rec[0], "newly_listed": rec[1]},
        "directions": cand["documents_in_manifest"], "directions_scanned": cand["documents_scanned"],
        "paragraphs": cand["paragraphs_scanned"], "preflight_paragraphs": pre["paragraphs"],
        "entity_classes": ec["term_count"], "core_entity_classes": len(core),
        "function_headings": len(cfg["matching"]["function_headings"]),
        "subject_families": sf["term_count"],
        "directions_with_subject_family": sum(1 for r in manifest if r.get("subject_family")),
        "empty_title_directions": pre["empty_title_directions"],
        "updated_as_on_titles": sum(1 for r in manifest if "updated as on" in (r.get("title") or "").lower()),
        "matrix": matrix,
        "p1004_missing_documents_file_rows": len(missing_rows),
        "paragraphs_by_entity_class": cand["paragraphs_by_entity_class"],
    }
    rows = [[c, n, "core" if c in core else "function heading"] for c, n in sorted(cand["paragraphs_by_entity_class"].items())]
    md = (f"# Table 1. Corpus and entity-class × subject-family matrix\n\n"
          f"- Directions: {res['directions']} (all scanned: {res['directions_scanned']}); paragraphs: {res['paragraphs']:,} "
          f"(P2-003 preflight: {res['preflight_paragraphs']:,}).\n"
          f"- Directions still missing after the P1-004 repair: {len(missing_rows)} (reports/p1004_missing_documents.csv has "
          f"{len(missing_rows)} rows; the P1-004 repair recovered {rec[0]} previously-missing Directions plus {rec[1]} newly listed, D1).\n"
          f"- Entity classes: {res['entity_classes']} raw ({res['core_entity_classes']} regulated-entity classes + "
          f"{res['function_headings']} RBI function headings, D8). Subject families: {res['subject_families']}, derived from titles; "
          f"{res['directions_with_subject_family']}/{res['directions']} Directions have one.\n"
          f"- Empty-title Directions (D2): {', '.join(res['empty_title_directions'])}. Titles with an 'Updated as on' stamp: "
          f"{res['updated_as_on_titles']}.\n"
          f"- Matrix: {matrix['total_cells']} cells, {matrix['populated_cells']} populated, {matrix['ambiguous_cells']} ambiguous, "
          f"{matrix['duplicate_mapping_cells']} duplicate-mapping (coverage {matrix['matrix_coverage']:.3f}, point estimate).\n\n"
          + table(["Entity class", "Paragraphs", "Kind"], rows) + "\n")
    return res, md


def t02_candidates() -> tuple[dict, str]:
    cand = load("reports/p2001_candidate_metrics_v4.json")
    rounds = [load(f"reports/p2001_precision_metrics_v{r}.json") for r in (1, 2, 3, 4)]
    res = {"rules": "v4", "paragraphs_with_cue": cand["paragraphs_with_cue"], "candidates_kept": cand["candidates_kept"],
           "candidates_excluded": cand["candidates_excluded"], "cue_level_rejection_rate": cand["rejection_rate_cue_level"],
           "precision_rounds": [{"rules": f"v{i + 1}", "n": r["sample_size"], "true": r["true_obligation"],
                                 "precision": r["precision"], "wilson_95": r["wilson_95"],
                                 "stop_triggered": r["precision_stop_triggered"]} for i, r in enumerate(rounds)]}
    rows = [[p["rules"], rate(p["true"], p["n"], p["wilson_95"]), "yes" if p["stop_triggered"] else "no"] for p in res["precision_rounds"]]
    md = ("# Table 2. Candidate extraction precision (P2-001)\n\n"
          f"Rules v4: {res['paragraphs_with_cue']:,} of {cand['paragraphs_scanned']:,} paragraphs carry a deontic cue; "
          f"{res['candidates_kept']:,} candidates kept, {res['candidates_excluded']:,} excluded.\n\n"
          + table(["Rules", "Precision (true obligations / sample)", "Stop triggered"], rows)
          + "\n\nThe v4 sample is re-admitted candidates only (kept by v4, excluded by v3), not a sample of all kept candidates. "
            "Label source: manual (one rater).\n")
    return res, md


def t03_matching() -> tuple[dict, str]:
    v = load("reports/p2002_validation_metrics_v1.json")
    o = v["validation"]["overall"]
    res = {"overall": o, "by_stratum": v["validation"]["by_stratum"], "threshold": v["threshold"]["chosen"],
           "leakage": v["leakage_official_edge"], "gates": v["gates"], "thresholded_status_counts": v["thresholded_status_counts"]}
    rows = [[s, x["n"], x["same"], x["related"], x["unrelated"],
             rate(x["counterpart_rate"]["k"], x["counterpart_rate"]["n"], x["counterpart_rate"]["wilson_95"])]
            for s, x in v["validation"]["by_stratum"].items()]
    lk = v["leakage_official_edge"]
    md = ("# Table 3. Cross-class matching validation (P2-002)\n\n"
          f"60 validation pairs (bge-base-en-v1.5 semantic bands; one rater). Counterpart rate (same + related): "
          f"{rate(o['counterpart_rate']['k'], o['counterpart_rate']['n'], o['counterpart_rate']['wilson_95'])}; same: "
          f"{rate(o['same_rate']['k'], o['same_rate']['n'], o['same_rate']['wilson_95'])}.\n\n"
          + table(["Stratum", "n", "same", "related", "unrelated", "Counterpart rate"], rows)
          + f"\n\nOperating threshold {v['threshold']['chosen']['value']} ({v['threshold']['chosen']['edge']}); chosen on the same "
            f"sample it is scored on. Leakage at the high edge: {rate(lk['leaks'], lk['n'], lk['leakage_wilson_95'])}.\n")
    return res, md


def t04_supplementary() -> tuple[dict, str]:
    d = load("data/supplementary/p2003_source_decisions_v1.json")["decisions"]
    h = load("data/supplementary/p2003_metrics_v1.json")["harvest"]
    res = {"decisions": d, "harvest": {k: {kk: vv for kk, vv in v.items() if not isinstance(vv, (dict, list))} for k, v in h.items()}}
    rows = [[x["source"], rate(x["clean"], x["n"], x["wilson95"]), x["decision"], ", ".join(x["interval_crosses"])] for x in d]
    md = ("# Table 4. Supplementary-source decisions (P2-003)\n\n"
          + table(["Source", "Clean paragraph-level alignment", "Decision (pre-registered rule)", "CI crosses"], rows)
          + f"\n\nHarvest: FAQ {h['faq']['items']} Q&A items from {h['faq']['faq_topics']} topics; enforcement {h['enforcement']['items']} "
            f"releases; amendments {h['amendment']['items']} ({h['amendment']['citing_paragraph_numbers']} cite paragraph numbers); "
            f"withdrawn list {h['withdrawn']['items']} entries. The point estimate decides; both intervals cross a decision line.\n")
    return res, md


def _pair(k: str) -> str:
    a, c = k.replace("__vs__", "-").split("-")
    return f"{RATER.get(a, a)}–{RATER.get(c, c)}"


def t05_t1_benchmark() -> tuple[dict, str]:
    m = load("reports/p2004_t1_benchmark_metrics_v1.json")
    pilot = load("reports/phase1_annotation_ingest_metrics.json")["agreement"]
    rel = m["reliability"]
    irr, rt = rel["irr"], rel["retest"]
    tr = m["timed_relabel"]["agreement_with_pass1"]
    res = {"sample": m["sample_items"], "validated": m["validated"], "rejected": m["rejected"],
           "rejection_rate": m["rejection_rate"], "route_counts": {k.split(":")[-1]: v for k, v in m["route_counts"].items()},
           "flag_distribution": m["flag_distribution"], "judgement_distribution": m["judgement_distribution"],
           "applies_to_source_class_only": m["applies_to_source_class_only"],
           "irr": {"items": irr["items"], "fleiss": irr["fleiss"],
                   "pairwise": {_pair(k): v for k, v in irr["pairwise"].items()}},
           "retest": rt, "pilot_fleiss_flag": pilot.get("fleiss_three_raters"),
           "pilot_pairwise_flag": {_pair(k): {"kappa": v.get("cohen_kappa_flag"), "n_items": v.get("n_items"),
                                              "ci95": (v.get("kappa_bootstrap_ci95") or {}).get("ci95")}
                                   for k, v in (pilot.get("pairwise") or {}).items()},
           "timed_relabel": tr, "candidate_label_agreement_by_band": m["candidate_label_agreement_by_band"],
           "by_source_class": m["by_source_class"],
           "compared_classes_per_item": {str(k): v for k, v in sorted(Counter(
               len(g["compared_classes"]) for g in load("data/benchmark/t1/t1_validated_v1.jsonl")).items())}}
    if not res["pilot_fleiss_flag"]:
        raise MissingSource("STOP: pilot Fleiss kappa missing from phase1_annotation_ingest_metrics.json")
    L = ["# Table 5. T1 benchmark: labels, provenance, reliability (P2-004)\n"]
    L.append(f"- Sample {m['sample_items']}; validated {m['validated']}; rejected as not an obligation "
             f"{rate(m['rejection_rate']['k'], m['rejection_rate']['n'], m['rejection_rate']['wilson_95'])}.")
    L.append("- Provenance routes: " + ", ".join(f"{k} {v}" for k, v in res["route_counts"].items()) + ".")
    L.append(f"- Flags: {m['flag_distribution']}. Class-row judgements: {m['judgement_distribution']}.")
    a = m["applies_to_source_class_only"]
    L.append(f"- applies_to is the source class alone on {rate(a['k'], a['n'], a['wilson_95'])}.")
    L.append("- Compared classes per item (capped at 4): " + ", ".join(f"{k} classes: {v} items" for k, v in res["compared_classes_per_item"].items()) + ".\n")
    L.append("## Labels by source class (validated items; per-class shown where n >= 5)\n")
    rows, small = [], []
    for c, x in sorted(m["by_source_class"].items()):
        n = x.get("validated", 0)
        if n < MIN_N:
            small.append(f"{c} ({n})")
            continue
        rows.append([c, n, x.get("rejected", 0), x.get("flag:shared", 0), x.get("flag:class-specific", 0), x.get("flag:absent", 0)])
    L.append(table(["Source class", "Validated", "Rejected", "shared", "class-specific", "absent"], rows))
    L.append(f"\nInsufficient n (< 5): {', '.join(small) if small else 'none'}.\n")
    L.append("## Reliability\n")
    L.append("Single-expert annotations (rater_1) with a second-rater set (30 items, rater_1–rater_3, pre-adjudication) and a blind "
             "test-retest (no washout period).\n")
    rows = [["Inter-rater, Fleiss (3 raters)", "class-row judgement", kappa(irr["fleiss"]["per_class_judgement"])],
            ["Inter-rater, Fleiss (3 raters)", "differential_flag", kappa(irr["fleiss"]["differential_flag"])],
            ["Inter-rater, Fleiss (3 raters)", "not_obligation", kappa(irr["fleiss"]["not_obligation"])]]
    for k, v in irr["pairwise"].items():
        for fld in ("per_class_judgement", "differential_flag", "not_obligation"):
            rows.append([f"Inter-rater, Cohen {_pair(k)}", fld, kappa(v.get(fld))])
    for grp, lab in (("all_25", "all 25"), ("second_rater_overlap_9", "9 overlap items"), ("other_16", "other 16")):
        g = rt["phase2"][grp]
        rows.append([f"Test-retest (blind, no washout), {lab}", "differential_flag", kappa(g["differential_flag"])])
        rows.append([f"Test-retest (blind, no washout), {lab}", "class-row judgement", kappa(g["per_class_judgement"])])
    rows.append(["Pilot test-retest (v1 → v3.1 guidelines)", "differential_flag", kappa(rt["pilot"]["differential_flag"])])
    pf = res["pilot_fleiss_flag"]
    rows.append(["Pilot inter-rater, Fleiss (3 raters), CONDITIONAL (D11: applies_to pre-filled)", "differential_flag",
                 f"{pf['kappa']:.3f} (point estimate) (n = {pf['n_items']} items)"])
    for k, v in res["pilot_pairwise_flag"].items():
        c = v["ci95"]
        rows.append([f"Pilot inter-rater, Cohen {k}, CONDITIONAL (D11)", "differential_flag",
                     (fmt_ci(v["kappa"], c[0], c[1]) if c else f"{v['kappa']:.3f} (point estimate)") + f" (n = {v['n_items']} items)"])
    rows.append(["Timed re-label vs pass 1 (20 single-pass items)", "differential_flag", kappa(tr["differential_flag"])])
    rows.append(["Timed re-label vs pass 1 (20 single-pass items)", "class-row judgement", kappa(tr["per_class_judgement"])])
    L.append(table(["Measure", "Field", "κ [95% bootstrap CI]"], rows))
    L.append("\n## Candidate-label agreement with the validated labels, by P2-002 band\n")
    L.append(table(["Band", "Agreement"], [[k, rate(v["k"], v["n"], v["wilson_95"])] for k, v in m["candidate_label_agreement_by_band"].items()]))
    L.append("")
    return res, "\n".join(L) + "\n"


def t06_t2() -> tuple[dict, str]:
    p3 = load("reports/p3001_metrics_v1.json")
    p4 = load("reports/p4001_metrics_v1.json")
    res = {"p3001": {k: {"bias": v["bias"], "n_scored": v["n_scored"], "systems": v["systems"], "paired": v["paired"]}
                     for k, v in p3["sets"].items()}, "p4_pipeline": p4["t2"]}
    L = ["# Table 6. T2 retrieval baselines (P3-001) and the P4 pipeline retrieval stage\n",
         "Relevance was labelled only for the counterpart in the query's target class, so class-blind systems are partly "
         "disadvantaged by construction. `hybrid_minus_source_class` is the fairer class-blind comparison. Metrics at cutoff 10; "
         "95% CIs from 2,000 query resamples.\n"]
    for name, s in p3["sets"].items():
        L.append(f"## {name} (n = {s['n_scored']})\n\n**Bias:** {s['bias']}\n")
        rows = [[sysn, mb(v["recall"]), mb(v["map"]), mb(v["ndcg"])] for sysn, v in s["systems"].items()]
        L.append(table(["System", "Recall@10", "MAP@10", "nDCG@10"], rows))
        rows = [[pn, mpd(v["ndcg"])] for pn, v in s["paired"].items()]
        L.append("\nPaired differences, nDCG@10:\n\n" + table(["Comparison", "Δ nDCG@10"], rows))
        pp = p4["t2"][name]
        L.append(f"\nP4 pipeline retrieval stage (class filter on vs off, ablation A): ON {b(pp['on'])}, OFF {b(pp['off'])}, "
                 f"ON − OFF {pd(pp['paired'])}.\n")
    return res, "\n".join(L) + "\n"


T1_ORDER = ("majority", "p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a", "long_context")
T1_LAB = {"majority": "Majority (in-sample)", "p2002_candidates": "P2-002 candidates", "class_blind": "Class-blind LLM",
          "class_aware": "Class-aware LLM", "final_agentic": "Final agentic", "ablation_a": "Class-blind + verifier",
          "long_context": "Long-context LLM (100K cap)", "long_context_150k": "Long-context LLM, 150K cap (superseded)"}


def _t1_row(k: str, v: dict) -> list:
    jl = v["judgement_f1_per_label"]
    return [T1_LAB.get(k, k), v["n_items"], b(v["flag_macro_f1"]), b(v["collapsed_macro_f1"]), b(v["judgement_macro_f1"]),
            f"{jl['same']:.3f} / {jl['different']:.3f} / {jl['none']:.3f} (point estimates)", b(v["coverage"])]


def t07_t1_systems() -> tuple[dict, str]:
    t1 = load("reports/p4001_metrics_v1.json")["t1"]
    res = {"systems": t1["systems"], "paired": t1["paired"], "long_context_same_items": t1.get("long_context_same_items"),
           "appendix_150k": t1.get("appendix_150k")}
    hdr = ["System", "n", "3-way flag Macro-F1", "Collapsed Macro-F1", "Judgement Macro-F1", "F1 same / different / none", "Coverage"]
    L = ["# Table 7. T1 systems (106 validated items; long-context on its scored items)\n",
         "3-way flag Macro-F1 over shared / class-specific / absent (a predicted `ambiguous` is wrong); collapsed = absent vs present. "
         "P2-002 cannot express shared vs class-specific, so 3-way F1 favours the LLM systems by design; collapsed F1 is the fair "
         "comparison. CIs: 2,000 item resamples.\n"]
    L.append(table(hdr, [_t1_row(k, t1["systems"][k]) for k in T1_ORDER if k in t1["systems"]]))
    L.append("\n## Paired differences (same items)\n")
    L.append(table(["Comparison", "n", "Δ 3-way F1", "Δ collapsed F1", "Δ coverage"],
                   [[k, v["n_items"], pd(v["flag_macro_f1"]), pd(v["collapsed_macro_f1"]), pd(v["coverage"])] for k, v in t1["paired"].items()]))
    lc = t1.get("long_context_same_items")
    if lc:
        L.append(f"\n## Every system on the long-context scored items (n = {lc['n']})\n")
        L.append(table(hdr, [_t1_row(k, v) for k, v in lc["systems"].items()]))
        td = lc["token_distribution"]
        L.append("\nPrompt tokens: " + "; ".join(f"{k}: n = {v['n']}, median {v['median']}, range {v['min']}–{v['max']}" for k, v in td.items() if v) + ".")
        ac = lc["gold_retention"].get("accounting") or {}
        L.append(f"Gold-retention accounting: {ac.get('scored')} scored = {ac.get('all_gold_kept')} all gold kept + "
                 f"{ac.get('at_least_one_cut')} at least one cut + {ac.get('no_gold_matched_paragraph')} with no gold matched paragraph.\n")
    ap = t1.get("appendix_150k")
    if ap:
        L.append(f"\n## Appendix: long-context at the 150K cap — {ap['label']} (n = {ap['n']})\n")
        L.append(table(hdr, [_t1_row(k, v) for k, v in ap["systems"].items()]))
        L.append("\n" + table(["Long-context (150K) −", "Δ 3-way F1", "Δ collapsed F1", "Δ coverage"],
                              [[T1_LAB.get(k, k), pd(v["flag_macro_f1"]), pd(v["collapsed_macro_f1"]), pd(v["coverage"])]
                               for k, v in ap["paired_vs_every_system"].items()]))
    return res, "\n".join(L) + "\n"


def t08_t3() -> tuple[dict, str]:
    p4 = load("reports/p4001_metrics_v1.json")
    build = load("data/benchmark/t3/t3_build_v1.json")
    r1 = load("data/benchmark/t3/t3_spotcheck_receipt_v1.json")["precision"]
    r2 = load("data/benchmark/t3/t3_spotcheck2_receipt_v1.json")["precision"]
    dropped = load("data/benchmark/t3/t3_dropped_after_check2_v1.json")["dropped_items"]
    t3 = p4["t3"]
    res = {"built": build["items"]["items"], "scored": t3["paired"]["n"], "dropped": dropped,
           "precision_v1_human": r1, "precision_independent_post_fix": r2,
           "precision_post_fix_in_sample": build["precision"]["rules_v2_same_20_rows"], "t3": t3}
    L = ["# Table 8. T3 temporal set and ablation B\n"]
    L.append(f"- Built {res['built']} items; {len(dropped)} dropped after spot-check 2 ({', '.join(dropped)}); scored {res['scored']}.")
    L.append(f"- Parse precision, human (rules v1): {rate(r1['k'], r1['n'], r1['wilson_95'])}.")
    L.append(f"- Parse precision, independent post-fix check (10 parses not in the first check): {rate(r2['k'], r2['n'], r2['wilson_95'])}.")
    ps = build["precision"]["rules_v2_same_20_rows"]
    L.append(f"- Post-fix on the same 20 rows the fix was designed on (in-sample, Claude's reading of the rater's notes): {ps['k']}/{ps['n']}.\n")
    rows = []
    for k in ("on", "off"):
        v = t3[k]
        rows.append([k.upper(), v["n"], b(v["status_exact_match"]), b(v["supersession_f1"]),
                     f"{v['by_side']['before']['status_exact_match']:.3f} (n = {v['by_side']['before']['n']}, point estimate)",
                     f"{v['by_side']['after']['status_exact_match']:.3f} (n = {v['by_side']['after']['n']}, point estimate)"])
    L.append(table(["Temporal filter", "n", "Status exact match", "Supersession F1", "Before-date EM", "After-date EM"], rows))
    L.append(f"\nON − OFF: status exact match {pd(t3['paired']['status_exact_match'])}; supersession F1 {pd(t3['paired']['supersession_f1'])} "
             "(degenerate CIs: the outcomes are deterministic on this set). Circular by construction: the gold and the filter come from the same parser.")
    sv = t3["sensitivity_no_window"]
    L.append(f"\nSensitivity without the {sv['excluded']} window-type items (n = {sv['paired']['n']}): status exact match ON − OFF "
             f"{pd(sv['paired']['status_exact_match'])}; supersession F1 ON − OFF {pd(sv['paired']['supersession_f1'])}.\n")
    return res, "\n".join(L) + "\n"


def t09_t4() -> tuple[dict, str]:
    m = load("reports/p3002_metrics_v1.json")
    main, hum = m["main"], m["human"]
    res = {"n_questions": main["n_questions"], "by_type": main["by_type"], "paired": main["paired"], "verdicts": main["verdicts"],
           "sensitivity": {"excluded": m["sensitivity_without_bad_questions"]["excluded"],
                           "verdicts": m["sensitivity_without_bad_questions"]["verdicts"]},
           "repair": main["repair"], "human": {k: hum[k] for k in ("all_rated", "bad_question_count", "sheet_quotas")},
           "rating_minutes_total": hum["minutes"]["total"], "rating_minutes_per_answer": hum["minutes"]["per_answer"],
           "llm": m["provenance"]["questions_run"]["models"] if m["provenance"].get("questions_run") else None}
    types = ("genuine", "concatenated", "adv_negated", "adv_offtopic")
    comps = ("composite_score", "entailment_score", "contradiction_score", "obligation_coverage_score")
    L = [f"# Table 9. T4 RePASs audit (P3-002; n = {main['n_questions']} questions)\n"]
    L.append(table(["Answer type", "RePASs", "Entailment", "Contradiction", "Obligation coverage"],
                   [[t] + [mb(main["by_type"][t][c]) for c in comps] for t in types]))
    L.append("\nGameability verdict (pre-registered: reproduces iff the CI of type − genuine lies at or above 0):\n")
    L.append(table(["Comparison", "Δ RePASs", "Verdict", "Sensitivity (n = 28) verdict"],
                   [[k, mpd(v["composite_score"]), main["verdicts"][k.split(" - ")[0]],
                     m["sensitivity_without_bad_questions"]["verdicts"][k.split(" - ")[0]]] for k, v in main["paired"].items()]))
    L.append("\nHuman vs metric (one rater, blind; 30 rated answers):\n")
    rows = [[t, hum["all_rated"]["by_type"][t]["faithful"]["n"], mb(hum["all_rated"]["by_type"][t]["faithful"]),
             mb(hum["all_rated"]["by_type"][t]["answers_question"])] for t in types]
    L.append(table(["Answer type", "n", "faithful (0–2)", "answers_question (0–2)"], rows))
    sp = [(k, v) for k, v in hum["all_rated"].items() if k.startswith("spearman_")]
    L.append("\n" + table(["Spearman", "ρ [95% CI] (n)"],
                          [[k.replace("spearman_", "").replace("_vs_", " vs "),
                            (fmt_ci(v["rho"], v["ci_low"], v["ci_high"]) if v["rho"] is not None else "undefined") + f" (n = {v['n']})"]
                           for k, v in sp]))
    L.append("\nExploratory repair (designed with the RIRAG finding in mind, tested on the same questions; not usable, see text):\n")
    L.append(table(["Repaired: genuine −", "Difference", "Reading"],
                   [[k.replace("genuine - ", ""), mpd(v), v["verdict"]] for k, v in main["repair"].items()]))
    L.append(f"\nRating time: {hum['minutes']['total']:.0f} min for 30 answers ({hum['minutes']['per_answer']:.1f} min per answer); "
             f"`bad_question` = yes on {hum['bad_question_count']} of 30.\n")
    return res, "\n".join(L) + "\n"


def t10_ablations() -> tuple[dict, str]:
    p4 = load("reports/p4001_metrics_v1.json")
    t1, t2, t3, t4 = p4["t1"], p4["t2"], p4["t3"], p4["t4"]
    pa = t1["paired"]["Ablation A (verifier on): final agentic − class-blind + verifier"]
    pc = t1["paired"]["Ablation C on T1: final agentic − class-aware"]
    rows = [["A", "class filter", "T1 3-way flag Macro-F1", pa["n_items"], pd(pa["flag_macro_f1"])],
            ["A", "class filter", "T1 collapsed Macro-F1", pa["n_items"], pd(pa["collapsed_macro_f1"])]]
    rows += [["A", "class filter", f"T2 nDCG@10, {k}", v["n"], pd(v["paired"])] for k, v in t2.items()]
    rows += [["B", "temporal filter", "T3 status exact match", t3["paired"]["n"], pd(t3["paired"]["status_exact_match"])],
             ["B", "temporal filter", "T3 supersession F1", t3["paired"]["n"], pd(t3["paired"]["supersession_f1"])],
             ["C", "verifier", "T1 3-way flag Macro-F1", pc["n_items"], pd(pc["flag_macro_f1"])],
             ["C", "verifier", "T1 coverage", pc["n_items"], pd(pc["coverage"])]]
    for key, lab in (("unsupported_sentence_rate", "T4 unsupported-sentence rate (NLI proxy), all 28"),
                     ("abstention_rate", "T4 abstention rate"), ("repass_composite", "T4 RePASs composite")):
        rows.append(["C", "verifier", lab, 28, pd(t4["n28"]["paired"][key])])
    ao = t4["n28"]["answered_only"]
    rows.append(["C", "verifier", "T4 unsupported-sentence rate, answered only (ON is 0 by construction)", ao["n"],
                 pd(ao["paired"]["unsupported_sentence_rate"])])
    rows.append(["C", "verifier", "T4 RePASs composite, answered only", ao["n"], pd(ao["paired"]["repass_composite"])])
    res = {"rows": [dict(zip(("ablation", "toggle", "measure", "n", "on_minus_off"), r)) for r in rows]}
    md = ("# Table 10. Ablations A–C (ON − OFF, everything else at the final agentic setting)\n\n"
          + table(["Ablation", "Toggle", "Measure", "n", "ON − OFF [95% CI] (reading)"], rows)
          + "\n\nNo correction for multiple comparisons; read each interval on its own.\n")
    return res, md


def t11_llm() -> tuple[dict, str]:
    p3m = load("reports/p3001_llm_models_v1.json")
    qrun = load("data/benchmark/t4/t4_questions_run_v1.json")
    grun = load("data/benchmark/t4/superseded/t4_genuine_run_v1_pre_trimfix.json")
    p4 = load("reports/p4001_metrics_v1.json")
    ledger = p4["environment"]["ledger"]
    devs = {d["id"]: d for d in p4["deviations"]}
    res = {"p3001_smoke": p3m.get("smoke_test"),
           "p3002": {"questions": {k: qrun.get(k) for k in ("provider", "models", "api_calls", "status", "force_reason")},
                     "genuine_answers": {k: grun.get(k) for k in ("provider", "models", "api_calls", "status", "force_reason")}},
           "p4": {"model": p4["environment"]["model"], "model_version": p4["environment"]["model_version"],
                  "thinking": p4["environment"]["thinking"], "calls_per_quota_day": ledger},
           "outage": p4["t1"].get("outage"), "deviations_affecting_results": {k: devs[k] for k in ("D10", "D11", "D12") if k in devs}}
    import re

    m_disc = re.search(r"after (\d+) of (\d+) questions", qrun.get("force_reason") or "")
    disc_model = re.match(r"(\S+) free-tier", qrun.get("force_reason") or "")
    rows = [[f"P3-001 smoke test ({p3m['smoke_test']['utc'][:10]})", r["model"], 1, f"{r['provider']}, status {r['status']}"]
            for r in (p3m.get("smoke_test") or {}).get("results", [])]
    if m_disc and disc_model:
        rows.append(["P3-002 question drafting, discarded", disc_model.group(1), int(m_disc.group(1)),
                     "Gemini free-tier daily quota ran out; these questions were discarded, never mixed"])
    rows += [["P3-002 question drafting", ", ".join(qrun.get("models") or []), qrun.get("api_calls"), "Groq, whole step rerun on the fallback"],
             ["P3-002 genuine answers", ", ".join(grun.get("models") or []), grun.get("api_calls"), "Groq, whole step on the fallback"]]
    for model, days in ledger.items():
        for day, n in sorted(days.items()):
            rows.append([f"P4 (all systems), quota day {day} (Pacific)", model, n, "Gemini; soft cap 480"])
    ow = res["outage"] or {}
    md = ("# Table 11. LLM usage\n\n"
          + table(["Phase", "Model id", "Calls", "Note"], rows)
          + "\n\nP1–P2 made no LLM calls. RePASs and the P4 verifier use local NLI models (NOTICE.md), not hosted LLMs.\n\n"
          + f"P4 model: `{res['p4']['model']}` (version `{res['p4']['model_version']}`), thinking {res['p4']['thinking']}, temperature 0, "
            f"no provider fallback. Outage: HTTP 503 on every call from {ow.get('first_503_ist')} IST until {ow.get('first_ok_after_outage_ist')} IST; "
            f"intermittent 503s until {ow.get('last_503_ist')} IST.\n\n"
          + "\n".join(f"- **{k}.** {v['text']}" for k, v in res["deviations_affecting_results"].items()) + "\n")
    return res, md


BUILDERS: list[tuple[str, Callable[[], tuple[dict, str]]]] = [
    ("01_corpus", t01_corpus), ("02_candidates", t02_candidates), ("03_matching", t03_matching),
    ("04_supplementary", t04_supplementary), ("05_t1_benchmark", t05_t1_benchmark), ("06_t2_retrieval", t06_t2),
    ("07_t1_systems", t07_t1_systems), ("08_t3", t08_t3), ("09_t4", t09_t4), ("10_ablations", t10_ablations),
    ("11_llm_usage", t11_llm)]


def build() -> tuple[dict, dict[str, str]]:
    results: dict = OrderedDict(version="v1", ci_rule="src/eval/ci_format.py: excludes 0 only when strictly above or below; "
                                                        "bounds with |value| < 0.0005 print to 4 decimals", tables={})
    mds = {}
    for name, fn in BUILDERS:
        r, md = fn()
        results["tables"][name] = r
        mds[name] = md
    return results, mds


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", help="build one table, e.g. --only 07 (prints it; results_v1.json is not rewritten)")
    args = ap.parse_args()
    if args.only:
        fn = dict(BUILDERS).get(next((k for k, _ in BUILDERS if k.startswith(args.only.zfill(2))), ""))
        if fn is None:
            ap.error(f"no table {args.only}")
        print(fn()[1])
        return 0
    try:
        results, mds = build()
    except MissingSource as exc:
        print(exc)
        return 1
    out_json = json.dumps(results, indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    tdir = ROOT / "reports" / "tables"
    if args.check:
        same = (ROOT / "reports" / "results_v1.json").read_text(encoding="utf-8") == out_json and all(
            (tdir / f"{k}.md").read_text(encoding="utf-8") == v for k, v in mds.items())
        print("tables up to date" if same else "tables DIFFER from the sources")
        return 0 if same else 1
    tdir.mkdir(parents=True, exist_ok=True)
    (ROOT / "reports" / "results_v1.json").write_text(out_json, encoding="utf-8")
    for k, v in mds.items():
        (tdir / f"{k}.md").write_text(v, encoding="utf-8")
    print(f"wrote reports/results_v1.json and {len(mds)} tables in reports/tables/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
