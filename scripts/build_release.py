#!/usr/bin/env python3
"""P5-001 tasks 4-5: build the pointer-only release data under release/ (no RBI text, pseudonymised raters).

    python3 scripts/build_release.py

Reads the working benchmark files (data/benchmark/, data/processed/, data/metadata/, data/supplementary/; none of them is
public) and writes release/data/*. Every item carries md_id, paragraph_id, character offsets, the source URL, the corpus
harvest date and the sha256 of the paragraph text; derived texts (T1 spans, T2 queries, T4 non-LLM answers) are replaced
by a rebuild rule plus the sha256 of the text, which scripts/rehydrate.py checks. Before writing, every rebuild rule is
run against the corpus and must reproduce the stored text exactly, and every output is scanned for a >= 30-word run of
corpus text and for rater names; any failure stops the build with nothing written.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.release.pseudonym import load_map, name_pattern, pseudonymise_text, pseudonymise_value  # noqa: E402
from src.release.rbi_text import CorpusIndex, copied_runs, shorten_copied_runs  # noqa: E402
from src.release.rebuild import concat_rule_spans, negate, offtopic_rule_spans, span_text, spans_text  # noqa: E402

BENCH, OUT = ROOT / "data" / "benchmark", ROOT / "release"
V = "v1"


class ReleaseError(RuntimeError):
    pass


def jl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    rater_map, other_names = load_map()
    if not rater_map:
        raise ReleaseError("STOP: reports/private/rater_map.json is missing; the release must be pseudonymised")
    names = name_pattern(rater_map, other_names)
    manifest = {r["document_id"]: r for r in jl(ROOT / "data" / "metadata" / "document_manifest.jsonl")}
    raw: dict[str, str] = {}
    md_of: dict[str, str] = {}
    for p in sorted((ROOT / "data" / "processed").glob("md_*.jsonl")):
        for r in jl(p):
            raw[r["paragraph_id"]] = r["text"]
            md_of[r["paragraph_id"]] = r["document_id"]
    print(f"corpus: {len(manifest)} Directions, {len(raw):,} paragraphs")

    def doc_ptr(md: str) -> dict:
        m = manifest[md]
        return {"source_url": m["source_url"], "harvest_date": (m.get("retrieved_at") or "")[:10]}

    def para_ptr(pid: str) -> dict:
        return {"paragraph_id": pid, "md_id": md_of[pid], **doc_ptr(md_of[pid]), "paragraph_sha256": sha(raw[pid])}

    files: dict[str, Any] = {}

    # ---- documents and paragraphs
    files["data/documents.jsonl"] = [
        {"md_id": k, "title": v.get("title"), "entity_class": v.get("entity_class"), "subject_family": v.get("subject_family"),
         "update_date": v.get("update_date"), "source_url": v["source_url"], "harvest_date": (v.get("retrieved_at") or "")[:10],
         "retrieved_at": v.get("retrieved_at"), "payload_sha256": v.get("content_hash"), "format": v.get("format")}
        for k, v in sorted(manifest.items())]
    files["data/paragraphs.jsonl"] = [{"paragraph_id": pid, "md_id": md_of[pid], "chars": len(raw[pid]), "text_sha256": sha(raw[pid])}
                                      for pid in sorted(raw)]

    # ---- matrix and vocabularies (derived metadata; copied as is)
    files["data/matrix/matrix_v1.jsonl"] = [
        {**r, "notes": re.sub(r"\s*See reports/\S+\.md\.?", "", r.get("notes") or "") or None}
        for r in jl(ROOT / "data" / "matrix" / "matrix_v1.jsonl")]
    for src, dst in (("data/matrix/matrix_v1_summary.json", "data/matrix/matrix_v1_summary.json"),
                     ("data/metadata/entity_classes.json", "data/metadata/entity_classes.json"),
                     ("data/metadata/subject_families.json", "data/metadata/subject_families.json")):
        files[dst] = ("copy", ROOT / src)

    # ---- T1
    def t1_row(it: dict, *, validated: bool) -> dict:
        sp = it["obligation_span"]
        units = [list(u) for u in sp["units"]]
        rebuilt = span_text(raw[sp["paragraph_id"]], units)
        if rebuilt != sp["text"]:
            raise ReleaseError(f"{it['item_id']}: span rule does not reproduce the stored span text")
        out = {k: v for k, v in it.items() if k not in ("obligation_span",)}
        out["obligation_span"] = {**para_ptr(sp["paragraph_id"]), "units": units, "rule": "span_text", "text_sha256": sha(sp["text"])}
        return pseudonymise_value(out, rater_map) if validated else out

    cand = jl(BENCH / "t1" / "t1_candidate_benchmark_v1.jsonl")
    val = jl(BENCH / "t1" / "t1_validated_v1.jsonl")
    rows_c = [t1_row(it, validated=False) for it in cand]
    half = (len(rows_c) + 1) // 2  # two shards, each under the 50 MB per-file limit
    files["data/t1/candidates_part1.jsonl"], files["data/t1/candidates_part2.jsonl"] = rows_c[:half], rows_c[half:]
    files["data/t1/validated.jsonl"] = [t1_row(it, validated=True) for it in val]
    by_item = {it["item_id"]: it for it in val}

    # ---- T2
    for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        rows = []
        supp = {}
        if s == "t2_supp_p2003":
            for src in ("faq", "enforcement"):
                for r in jl(ROOT / "data" / "supplementary" / src / "items_v1.jsonl"):
                    supp[r["item_id"]] = r
        p2002_key = json.loads((BENCH / "matching" / "p2002_validation_key_v1.json").read_text()) if s == "t2_xclass_p2002" else None
        for q in jl(BENCH / "t2" / f"{s}_{V}.jsonl"):
            out = {k: v for k, v in q.items() if k != "text"}
            out["relevant_pointers"] = [para_ptr(p) for p in sorted(q["relevant"])]
            if s == "t2_xclass_t1":
                it = by_item[q["cluster"]]
                if span_text(raw[it["paragraph_id"]], it["obligation_span"]["units"]) != q["text"]:
                    raise ReleaseError(f"{q['query_id']}: T2 query is not the T1 span")
                out["query"] = {**para_ptr(it["paragraph_id"]), "units": it["obligation_span"]["units"], "rule": "span_text",
                                "text_sha256": sha(q["text"])}
            elif s == "t2_xclass_p2002":
                pairs = p2002_key.get("pairs", p2002_key)
                a, b_ = pairs[q["query_id"]]["source_unit_offsets"]
                if raw[q["source_paragraph_id"]][a:b_] != q["text"]:
                    raise ReleaseError(f"{q['query_id']}: P2-002 slice does not reproduce the query")
                out["query"] = {**para_ptr(q["source_paragraph_id"]), "units": [[a, b_]], "rule": "raw_slice", "text_sha256": sha(q["text"])}
            else:
                it = supp[q["query_id"]]
                out["query"] = {"source": q["source"], "item_id": q["query_id"], "source_url": it["source_url"],
                                "harvest_date": (it.get("retrieved_at") or "")[:10], "payload_sha256": it.get("content_hash"),
                                "text_basis": q.get("text_basis"), "rule": "not rehydrated automatically (text from an RBI "
                                "FAQ page or press release; parser in src/supplementary/)", "text_sha256": sha(q["text"])}
            rows.append(out)
        files[f"data/t2/{s}.jsonl"] = rows

    # ---- T3
    dropped_doc = json.loads((BENCH / "t3" / "t3_dropped_after_check2_v1.json").read_text())
    dropped = set(dropped_doc["dropped_items"])
    amd = {r["item_id"]: r for r in jl(ROOT / "data" / "supplementary" / "amendment" / "items_v1.jsonl")}
    t3_rows, t3_dropped = [], []
    for it in jl(BENCH / "t3" / "t3_items_v1.jsonl"):
        out = {k: v for k, v in it.items()}
        out.update(para_ptr(it["paragraph_id"]))
        amd_id = it["action_id"].split("#")[0]
        out["amendment"] = {"item_id": amd_id, "source_url": amd[amd_id]["source_url"], "published_date": amd[amd_id].get("published_date"),
                            "harvest_date": (amd[amd_id].get("retrieved_at") or "")[:10], "payload_sha256": amd[amd_id].get("content_hash")}
        (t3_dropped if it["t3_id"] in dropped else t3_rows).append(
            {**out, "dropped_reason": dropped_doc["reason"]} if it["t3_id"] in dropped else out)
    files["data/t3/items.jsonl"], files["data/t3/dropped.jsonl"] = t3_rows, t3_dropped

    # ---- T4
    qs = jl(BENCH / "t4" / "t4_questions_v1.jsonl")
    cands4 = {}
    with (BENCH / "candidates" / "t1_candidates_v4.jsonl").open(encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            cands4[r["paragraph_id"]] = r
    files["data/t4/questions.jsonl"] = [
        {"question_id": q["question_id"], "item_id": q["item_id"], **para_ptr(q["paragraph_id"]), "entity_class": q["entity_class"],
         "subject_family": q["subject_family"], "question": q["question"],
         "question_llm": {k: q["llm"][k] for k in ("provider", "model", "model_version")},
         "passages": [p["paragraph_id"] for p in q["passages"]], "retrieval": q["retrieval"]} for q in qs]
    ans = {t: {r["question_id"]: r for r in jl(BENCH / "t4" / f"t4_answers_{t}_{V}.jsonl")}
           for t in ("genuine", "concatenated", "adv_negated", "adv_offtopic")}
    conc_rows, neg_rows, off_rows = [], [], []
    for q in qs:
        qid = q["question_id"]
        spans = concat_rule_spans([p["paragraph_id"] for p in q["passages"]], raw, cands4)
        text = spans_text(spans, raw)
        if text != ans["concatenated"][qid]["answer"]:
            raise ReleaseError(f"{qid}: concatenation rule does not reproduce the answer")
        conc_rows.append({"question_id": qid, "answer_type": "concatenated", "method": ans["concatenated"][qid]["method"],
                          "rule": "spans_text", "spans": [{"paragraph_id": p, "start": a, "end": b} for p, a, b in spans],
                          "text_sha256": sha(text)})
        if negate(text) != ans["adv_negated"][qid]["answer"]:
            raise ReleaseError(f"{qid}: negation rule does not reproduce the answer")
        neg_rows.append({"question_id": qid, "answer_type": "adv_negated", "method": ans["adv_negated"][qid]["method"],
                         "rule": "negate(concatenated)", "text_sha256": sha(ans["adv_negated"][qid]["answer"])})
        o = ans["adv_offtopic"][qid]
        ospans = offtopic_rule_spans(o["offtopic_md_ids"], len(text), raw, md_of, cands4)
        if spans_text(ospans, raw) != o["answer"]:
            raise ReleaseError(f"{qid}: off-topic rule does not reproduce the answer")
        off_rows.append({"question_id": qid, "answer_type": "adv_offtopic", "method": o["method"], "offtopic_md_ids": o["offtopic_md_ids"],
                         "offtopic_families": o["offtopic_families"], "rule": "spans_text",
                         "spans": [{"paragraph_id": p, "start": a, "end": b} for p, a, b in ospans], "text_sha256": sha(o["answer"])})
    files["data/t4/answers_concatenated.jsonl"] = conc_rows
    files["data/t4/answers_adv_negated.jsonl"] = neg_rows
    files["data/t4/answers_adv_offtopic.jsonl"] = off_rows
    index = CorpusIndex.from_texts(raw.values())
    gen_rows = []
    for r in ans["genuine"].values():
        text, cuts = shorten_copied_runs(r["answer"], index)
        gen_rows.append({"question_id": r["question_id"], "answer_type": "genuine", "answer": text,
                         "llm": {k: r["llm"][k] for k in ("provider", "model", "model_version")},
                         "text_sha256": sha(r["answer"]),
                         "redactions": cuts or None,
                         "redaction_note": ("a quotation of 30+ corpus words was cut to 25 words plus '[…]' (P5-001 RBI-text "
                                            "rule); text_sha256 is of the answer as scored") if cuts else None})
    files["data/t4/answers_genuine.jsonl"] = gen_rows
    key = json.loads((BENCH / "t4" / "t4_faithfulness_key_v1.json").read_text())["rows"]
    labels = {r["row_id"]: r for r in jl(BENCH / "t4" / "t4_faithfulness_labels_v1.jsonl")}
    human = {(v["question_id"], v["answer_type"]): {"sheet_row": rid, "faithful": labels[rid]["faithful"],
                                                    "answers_question": labels[rid]["answers_question"],
                                                    "bad_question": labels[rid]["bad_question"], "note": labels[rid]["note"],
                                                    "rater": pseudonymise_text(labels[rid]["rater"], rater_map),
                                                    "label_source": pseudonymise_text(labels[rid]["label_source"], rater_map)}
             for rid, v in key.items()}
    files["data/t4/scores.jsonl"] = [
        {**{k: r[k] for k in ("question_id", "answer_type", "composite_score", "entailment_score", "contradiction_score",
                              "obligation_coverage_score", "lcs_ratio", "overlap_penalty", "relevance", "repaired")},
         "human": human.get((r["question_id"], r["answer_type"]))}
        for r in jl(BENCH / "t4" / "t4_per_answer_v1.jsonl")]

    # ---- provenance files the tables are built from (no RBI text; pseudonymised)
    from scripts.build_tables import PROVENANCE
    for rel in PROVENANCE:
        files[f"provenance/{Path(rel).name}"] = ("text", json.dumps(
            pseudonymise_value(json.loads((ROOT / rel).read_text(encoding="utf-8")), rater_map), indent=1, ensure_ascii=False) + "\n")

    # ---- guidelines (pseudonymised)
    files["guidelines/ANNOTATION_INSTRUCTIONS.md"] = ("text", pseudonymise_text(
        (BENCH / "templates" / "ANNOTATION_INSTRUCTIONS.md").read_text(encoding="utf-8"), rater_map))

    # ---- render, then check everything before writing anything
    rendered: dict[str, bytes] = {}
    for name, v in files.items():
        if isinstance(v, tuple) and v[0] == "copy":
            rendered[name] = v[1].read_bytes()
        elif isinstance(v, tuple) and v[0] == "text":
            rendered[name] = v[1].encode("utf-8")
        else:
            rendered[name] = ("".join(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n" for r in v)).encode("utf-8")
    titles = [(m.get("title") or "") for m in manifest.values()]
    problems = []
    for name, data in rendered.items():
        text = data.decode("utf-8")
        for run in copied_runs(text, index):
            if not any(run.excerpt in " ".join(re.findall(r"[a-z0-9]+", t.lower())) for t in titles):
                problems.append(f"{name}: {run.length}-word copied run: {run.excerpt[:80]}")
        if names.search(text):
            problems.append(f"{name}: a rater name appears: {names.search(text).group(0)!r}")
    if problems:
        print("STOP: release check failed; nothing written:")
        for p in problems[:40]:
            print("  " + p)
        return 1
    dd = OUT / "data"
    if dd.exists():
        shutil.rmtree(dd)
    for name, data in rendered.items():
        p = OUT / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    manifest_out = {name: {"bytes": len(d), "sha256": hashlib.sha256(d).hexdigest(),
                           "rows": d.count(b"\n") if name.endswith(".jsonl") else None} for name, d in sorted(rendered.items())}
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest_out, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(rendered)} files under release/ ({sum(len(d) for d in rendered.values()) / 1e6:.1f} MB); "
          f"raters pseudonymised as {', '.join(sorted(rater_map.values()))}")
    for name in sorted(rendered):
        print(f"  {name}: {manifest_out[name]['rows'] if manifest_out[name]['rows'] is not None else '-'} rows, {len(rendered[name]):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
