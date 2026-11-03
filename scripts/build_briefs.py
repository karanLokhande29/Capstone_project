#!/usr/bin/env python3
"""Content briefs for each paper section (NO prose). Each `[[key|fmt]]` resolves against the results bundle and prints
"value (key)", so every number in a brief carries its source.

    python3 scripts/build_briefs.py   -> paper/aisigh/briefs/*.md and paper/aisigh/space_budget.md

Key prefixes:
- `R:` = reports/results_v1.json `tables.*`;
- `EA:` = reports/final/error_analysis_v1.json;
- `{{…}}` = a T1 v2 number filled in Phase 3/4.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "paper/aisigh/briefs"
SRC = {"R": json.loads((ROOT / "reports/results_v1.json").read_text())["tables"],
       "EA": json.loads((ROOT / "reports/final/error_analysis_v1.json").read_text())}


def get(ref: str):
    pre, key = ref.split(":", 1)
    v = SRC[pre]
    for k in key.split("."):
        v = v[int(k)] if isinstance(v, list) else v[k]
    return v


def render(text: str) -> str:
    def sub(m):
        ref, fmt = (m.group(1).split("|") + ["{}"])[:2]
        v = get(ref)
        if isinstance(v, dict) and "value" in v and "ci" in v:
            s = f"{v['value']:.3f} [{v['ci'][0]:.3f}, {v['ci'][1]:.3f}]"
        elif isinstance(v, dict) and "diff" in v:
            s = f"{v['diff']:+.3f} [{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}]"
        elif isinstance(v, dict) and "mean" in v:
            s = f"{v['mean']:+.3f} [{v['ci_low']:+.3f}, {v['ci_high']:+.3f}]"
        elif isinstance(v, dict) and "rho" in v:
            s = f"{v['rho']:.3f} [{v['ci_low']:.3f}, {v['ci_high']:.3f}]"
        elif isinstance(v, dict) and "kappa" in v:
            s = f"{v['kappa']:.3f} [{v['bootstrap']['ci95'][0]:.3f}, {v['bootstrap']['ci95'][1]:.3f}] (n items {v['n_items']})"
        else:
            s = fmt.format(v)
        return f"**{s}** (`{ref}`)"
    return re.sub(r"\[\[([^\]]+)\]\]", sub, text)


T7 = "R:07_t1_systems"
BRIEFS = {
    "00_abstract": ("Abstract", 170, 200, """
**Claims (in order):**
- Problem: obligations in parallel RBI Master Directions for different regulated-entity classes; a counterpart may exist but differ.
- Resource: corpus of [[R:01_corpus.directions]] Directions / [[R:01_corpus.paragraphs|{:,}]] paragraphs; four tasks (T1–T4).
- T1 size {{T1V2-N-items}} with inter-rater reliability on the sample itself: {{P-class-k}} (primary).
- Main finding: no LLM system beats the embedding-matching baseline on collapsed flag F1 (v2: {{…}}); every system is weak on `different` ({{missed-by-all v2}}).
- Targeted experiment: structured comparator result {{cmp-diffF1}}.
- T4: RePASs is gameable by concatenation ([[R:09_t4.paired.concatenated - genuine.composite_score]]).
- Release: pointer-only, no RBI text.

**Must not say:** "three independent annotators" for the v1 gold; "second-rater κ 0.774" for the gold (that set is separate).
"""),
    "01_intro": ("Introduction", 350, 500, """
**Claims:**
- Compliance teams compare duties across entity classes (banks, NBFCs, co-operative banks…).
- RegNLP QA work does not test cross-class differences: ObliQA and the RePASs metric \\cite{gokhan2024regnlp}; ObliQA-MP \\cite{obliqamp}; RIRAG-2025 \\cite{gokhan2025riragtask}; concatenation gameability \\cite{aueb2025rirag}. Indian regulatory QA: IndiaFinBench \\cite{indiafinbench}. Source: \\cite{rbi}.
- Research questions: RQ1 applicability/counterpart retrieval (T2), RQ2 differential obligation (T1), RQ3 metric integrity (T4).
- Contributions, one line each: corpus + class × subject-family matrix; T1 with reliability measured on the sample; T2 sets with stated biases; T3 temporal set; T4 RePASs audit; systems + the targeted structured comparator.

**Numbers:**
- [[R:01_corpus.core_entity_classes]] regulated classes;
- [[R:01_corpus.subject_families]] subject families.
"""),
    "02_related": ("Related work", 180, 350, """
**Claims:**
- Regulatory QA and retrieval: ObliQA and RePASs \\cite{gokhan2024regnlp} (paper); RePASs code at the pinned commit \\cite{repass} (software citation only); ObliQA-MP \\cite{obliqamp}; the RIRAG-2025 shared task \\cite{gokhan2025riragtask}; AUEB-Archimedes on obligation concatenation \\cite{aueb2025rirag}.
- Indian financial regulatory text: IndiaFinBench \\cite{indiafinbench} (406 QA pairs from SEBI/RBI text; four task types).
- Retrieval: BM25S \\cite{bm25s}, dense bge (C-Pack) \\cite{bge} via Sentence-BERT \\cite{sbert}, reciprocal rank fusion \\cite{rrf}.
- Gap: no benchmark tests "same obligation vs different version across entity classes".

**References:** all verified on 2 Oct (`paper/aisigh/refs_verified.bib`). Cite RePASs-the-metric through `gokhan2024regnlp`, and use `repass` only as the code citation.
"""),
    "03_corpus": ("Corpus and benchmark construction", 250, 400, """
**Claims:**
- Harvest of RBI Master Directions; paragraph segmentation; the entity-class vocabulary mixes [[R:01_corpus.core_entity_classes]] regulated classes and [[R:01_corpus.function_headings]] RBI function headings (D8).
- Candidate obligations by deontic cues: [[R:02_candidates.candidates_kept|{:,}]] kept.
- Cross-class matching (P2-002, bge-base + lexical, thresholded).
- T1 sample of [[R:05_t1_benchmark.sample]] items, seeded and stratified; at most 4 compared classes per item.

**Floats:** Table `tab:benchmark`; Fig. `fig:construction` (single column).

**Disclosures:**
- D1 (81 Directions recovered in P1-004; all P2 work on the full set);
- D2 (3 empty-title Directions);
- subject families are derived from titles.
"""),
    "04_annotation": ("Annotation and reliability", 450, 650, """
**Claims:**
- Guidelines v3/v3.1; per-class judgement same / different / none / unsure; the flag is derived (v3.6).
- Statistics: Fleiss' κ \\cite{fleiss1971}, Cohen's κ \\cite{cohen1960}, bootstrap CIs \\cite{efron1979}, Wilson intervals \\cite{wilson1927}.
- v1 gold labelled by one annotator (rater_1). Routes: adjudicated [[R:05_t1_benchmark.route_counts.adjudicated]], retest-consistent [[R:05_t1_benchmark.route_counts.retest-consistent]], single-pass [[R:05_t1_benchmark.route_counts.single-pass]].
- **State it plainly:** none of the v1 gold items had an independent second rating. This motivated the T1 v2 round.
- T1 v2 design (pre-registered plan v2, sha256 `6e70641d…`, plus dated amendments):
  - two new raters on 93 first-exposure items (79 kept + 14 rejected);
  - 30 seen-before items reported separately;
  - a 15-hour blind short-interval retest (19 each).
- Primary result: Fleiss κ {{P-class-k}} (class), {{P-flag-k}} (flag), {{P-notobl-k}} (not_obligation); kept-only {{Pk…}}; pooled with the separate 30-item set {{S…}}.
- The separate 30-item set, as published: class [[R:05_t1_benchmark.irr.fleiss.per_class_judgement]], flag [[R:05_t1_benchmark.irr.fleiss.differential_flag]].
- Gold-freeze rule outcome: {{n triggered / changed}}; gold v2 = {{T1V2-N-items}}.

**Floats:** Fig. `fig:provenance` (two-column); Table `tab:reliability`.

**Disclosures (required):**
- The same two P2-002 candidates were shown in every pass (bias toward P2-002; as for T2).
- rater_1 could look up other paragraphs; the new raters could not.
- The guidelines do not define incomplete passages, classifications or examples.
- The 26–27 Sep team-review episode (not independent; never in κ).
- The retest is supplementary (recall); the real intervals are {{…}} h.
- The minutes logs are the time record; 5.35 min/item is a lower bound.
- Reliability uses rater_1's frozen pass 1, never the adjudicated gold.
"""),
    "05_tasks": ("Tasks, systems and metrics", 300, 450, """
**Claims:**
- T1: per-class judgement and derived flag. Metrics: 3-way flag Macro-F1 (a predicted `ambiguous` is wrong) and collapsed absent-vs-present Macro-F1 (the fair comparison with P2-002).
- T2: counterpart retrieval, nDCG@10, three relevance sets with stated biases.
- T3: status exact match and supersession F1.
- T4: RePASs composite paired differences; human faithful/answers_question ratings.
- Systems: majority (in-sample), P2-002 candidates, class-blind LLM, class-aware LLM, final agentic (class filter + NLI verifier), ablation A, long-context (100K cap).
- LLM: gemini-3.5-flash-lite, temperature 0, minimal thinking, frozen prompts (sha256).
- CIs: 2,000 item resamples (bootstrap \\cite{efron1979}); Wilson intervals for proportions \\cite{wilson1927}; paired differences via the one CI rule (`src/eval/ci_format.py`).
- Citations: the LLMs \\cite{gemini35fl,gptoss}; the verifier NLI model \\cite{nlideberta} (DeBERTaV3 \\cite{debertav3}); RePASs \\cite{gokhan2024regnlp,repass}, whose obligation classifier is fine-tuned from LEGAL-BERT \\cite{legalbert}.

**Floats:** Fig. 3 (architecture) is in the 8-page variant only.
"""),
    "06_results": ("Results", 650, 950, """
**RQ1 / T2:**
- The class filter gain is [[R:06_t2_retrieval.p4_pipeline.t2_xclass_t1.paired]] on xclass_t1, **partly by construction**.
- Dense [[R:06_t2_retrieval.p3001.t2_xclass_t1.systems.dense.ndcg.mean|{:.3f}]] vs BM25 [[R:06_t2_retrieval.p3001.t2_xclass_t1.systems.bm25.ndcg.mean|{:.3f}]] (xclass_t1).

**RQ2 / T1** (all v2 numbers are placeholders; v1 for orientation only):
- No LLM system beats P2-002 on collapsed F1 (v1: class-blind − P2-002 [[R:07_t1_systems.paired.Class-blind LLM − P2-002 candidates.collapsed_macro_f1]]). v2: {{…}}.
- Every system is weak on `different`:
  - v1 different F1 class-blind [[R:07_t1_systems.systems.class_blind.judgement_f1_per_label.different|{:.3f}]];
  - v1 missed by all five systems [[EA:a_different_missed.missed_by_every_llm_system]] of [[EA:a_different_missed.gold_different_units]] (definition: all five answered).
  - v2: {{…}}.
- Verifier (ablation C): v1 3-way [[R:07_t1_systems.paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1]], coverage [[R:07_t1_systems.paired.Ablation C on T1: final agentic − class-aware.coverage]]. v2: {{…}}.
- Long-context: v1 [[R:07_t1_systems.systems.long_context.n_items]] of 106 answered at the 100K cap. v2: {{…}}.

**RQ3 / T4:**
- Concatenated − genuine [[R:09_t4.paired.concatenated - genuine.composite_score]] (pre-registered: reproduces the gameability reported by \\cite{aueb2025rirag}; metric \\cite{gokhan2024regnlp}).
- Negated [[R:09_t4.paired.adv_negated - genuine.composite_score]]; off-topic [[R:09_t4.paired.adv_offtopic - genuine.composite_score]].
- ρ(RePASs, faithful) [[R:09_t4.human.all_rated.spearman_composite_score_vs_faithful]]; ρ(answers_question) [[R:09_t4.human.all_rated.spearman_composite_score_vs_answers_question]].
- Three-rater T4: {{T4-3rater}}.

**T3:**
- Filter on [[R:08_t3.t3.on.status_exact_match]] — **circular by construction**; filter off [[R:08_t3.t3.off.status_exact_match]].

**Floats:** `tab:t2`, `tab:t1`, `tab:t3t4`.
"""),
    "07_comparator": ("Targeted experiment: structured comparator", 220, 350, """
**Claims:**
- Motivation: `different` units are missed by every LLM system (v1 count above; v2 {{…}}). In the v1 dry run, 27 of 58 were reasoning failures for every system that erred (the gold paragraph was in context).
- Method:
  - the LLM extracts 13 fields per side and compares them field by field;
  - a fixed rule decides (same > different > none);
  - frozen before any T1 run (amendment 3; sha256 system `51f7ea78…`, rule `83664f8d…`).
- Development set: the separate 30-item set (disclosed), with one revision for a field-extraction bug.
  - dev macro-F1 0.635, `different` F1 0.348 (development evidence only; source `reports/private/final_push/p1/comparator_dev_eval_20261002T131911Z.json`).
- Result on gold v2: {{cmp-diffF1}}, {{cmp vs class-aware paired}}.

**Disclosures:** dev on the IRR set; one revision and its reason; sealed predictions (manifest sha256).
"""),
    "08_discussion": ("Discussion", 180, 350, """
**Claims (v2-dependent wording only after Phase 4):**
- Retrieval is not the bottleneck on T1; deciding what differs is.
- The verifier's whole-paragraph NLI premise is a poor test for one-sentence rationales.
- What the benchmark catches that generic RegQA does not.
- Whether structured comparison helps: {{…}}.
"""),
    "09_limitations": ("Limitations", 200, 350, """
**Must include:**
- The v1 gold is single-annotator; v2 changes items only via the pre-registered rule.
- Compared classes are capped at 4; `absent` covers only the paragraphs shown or looked up.
- The T2 relevance-set biases.
- T3 circularity and the old-words parser defect; the corpus holds only amended text.
- T4: n = 30, LLM-drafted questions; the repair is not usable.
- Free-tier Flash-Lite models; the outage window (no model switch).
- Short retest interval; the candidates shown may bias raters.
- CIs resample items, not Directions.
"""),
    "10_ethics": ("Ethics, licensing and AI use", 120, 200, """
**Claims:**
- The release holds no RBI text: pointers (ids, offsets, URL, sha256) plus `rehydrate.py`.
- Excerpts are at most 25 words; the release check fails on a copied run of 30 or more words.
- Raters are pseudonymised; no per-person minutes.
- Enforcement releases are not released. Not legal advice.
- The licence for RBI text redistribution is unsettled (see `licensing_notes_v1.md`).
"""),
    "11_ai_use_ack": ("AI-use statement and acknowledgements (for the authors to word)", 80, 120, """
**Where AI tools were used (factual list; the authors word it):**
- **Code generation:** Claude Code (Anthropic) wrote the repository code (scraper, preprocessing, candidate extraction, matching, benchmark tooling, ingest/freeze tools, evaluation and statistics scripts) under the authors' direction.
- **Analysis scripts:** Claude Code wrote and ran the analysis and bootstrap scripts; the authors reviewed the outputs.
- **Internal reports:** Claude Code drafted the internal phase reports, the methods/limitations briefs and the report_corrections file.
- **LLM systems under study (system outputs, not labels):**
  - gemini-3.5-flash-lite (P4 systems, long-context, structured comparator);
  - Groq openai/gpt-oss-120b (T4 question drafting and genuine answers, P3).
- **Provider terms (disclosure):** Gemini API (free tier) terms: outputs may be published, and they were not used to train any model; free-tier inputs may be used by Google, including human review. The prompts contained only public RBI text and no personal data. Groq (gpt-oss-120b) terms: https://groq.com/terms-of-use.
- **Not AI:** every human label (T1, T3 spot-checks, T4 faithfulness) is manual. One early team-review file set was revised after AI-reviewer file-level feedback; it was recorded as not independent and never used for agreement.
- **The paper text:** written by the authors (the venue requires AI-generated content < 20% at camera-ready).
- **Authors:** Karan Lokhande, Akash Goyal, Meer Magia (order confirmed 2 Oct). The second raters are co-authors, so there is no acknowledgement line for them. The paper must **not** map authors to rater ids (release rule).
"""),
}

BUDGET = [  # (report section, decision 6p, decision 8p, where)
    ("1 Abstract", "main", "main", "00_abstract"),
    ("2 Introduction and RQs", "main", "main", "01_intro"),
    ("3 Related work", "main (short)", "main", "02_related"),
    ("4 Corpus and matrix", "main (merged with 5)", "main", "03_corpus"),
    ("4 Matrix figure (57 families × 19 classes)", "release-only", "release-only (illegible at column width)", "release docs"),
    ("5 T1 construction", "main", "main", "03_corpus"),
    ("5 Reliability (T1 v2)", "main", "main", "04_annotation"),
    ("5 P2-004 retest, timed re-label, pilot κ", "release-only (one sentence in main)", "pages 7–8", "04_annotation"),
    ("5 Candidate-label agreement by band", "release-only", "release-only", "release docs"),
    ("6 Tasks and metrics", "main", "main", "05_tasks"),
    ("7 Systems (Fig. 3 architecture)", "main text; Fig. 3 dropped", "pages 7–8 (Fig. 3)", "05_tasks"),
    ("8.1 RQ1 / T2 table", "main", "main", "06_results"),
    ("8.2 RQ2 / T1 systems table", "main", "main", "06_results"),
    ("8.2 full paired-difference table (14 rows)", "release-only", "release-only", "release docs"),
    ("8.3 Verifier", "main (2 sentences)", "main", "06_results"),
    ("8.4 Long-context same-items table", "release-only (1 sentence)", "pages 7–8", "06_results"),
    ("8.4 150K appendix (superseded)", "release-only", "release-only", "release docs"),
    ("8.5 T4 (RePASs audit)", "main", "main", "06_results"),
    ("8.5 T4 repair (exploratory)", "1 sentence", "pages 7–8 (short)", "06_results"),
    ("8.5 T4 three-rater (amendment 2)", "1 row in tab:t3t4", "main", "06_results"),
    ("8.6 T3", "main (short)", "main", "06_results"),
    ("8.6 T3 parser appendix", "release-only", "release-only", "release docs"),
    ("8.7 Error analysis (a)–(e) with examples", "release-only (counts in 07)", "pages 7–8 (two examples ≤ 25 words)", "07_comparator"),
    ("Targeted experiment (comparator)", "main", "main", "07_comparator"),
    ("9 Ablations", "rows in tab:t3t4", "main", "06_results"),
    ("10 Discussion", "main (short)", "main", "08_discussion"),
    ("11 Limitations", "main", "main", "09_limitations"),
    ("12 Ethics and IPR", "main (short)", "main", "10_ethics"),
    ("13 AI-use statement", "acknowledgment", "acknowledgment", "11_ai_use_ack"),
    ("14 Reproducibility (commands)", "drop (1 sentence + repo URL)", "drop", "release README"),
    ("Per-class results (Table 12)", "release-only", "release-only", "release docs"),
    ("Confusion matrices", "release-only", "pages 7–8 (one, class-aware vs gold)", "release docs"),
    ("LLM usage / quota table (Table 11)", "release-only", "release-only", "release docs"),
    ("P2-003 supplementary sources (FAQ / enforcement)", "drop (1 clause)", "release-only", "release docs"),
    ("Candidate precision rounds (P2-001)", "release-only", "release-only", "release docs"),
]

FLOAT_PAGES_6 = {"tab:benchmark": 0.15, "fig:construction (1 col)": 0.18, "fig:provenance (2 col)": 0.3, "tab:reliability (2 col)": 0.2,
                 "tab:t2 (2 col)": 0.18, "tab:t1 (2 col)": 0.3, "tab:t3t4": 0.3, "references (10)": 0.4}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    total6 = total8 = 0
    for name, (title, w6, w8, body) in BRIEFS.items():
        (OUT / f"{name}.md").write_text(
            f"# Brief: {title}\n\nWord budget: **{w6} words** (6-page) / {w8} (8-page, paid). Prose is written by the authors.\n"
            + render(body) + "\n", encoding="utf-8")
        total6 += w6
        total8 += w8
    fl = sum(FLOAT_PAGES_6.values())
    L = ["# Space budget: AISIGH-SD 2026 (IEEEtran two-column)", "",
         "**Decision (2 Oct):** draft to **6 pages**; the 7-page variant is the fallback (a paid 7th page is approved if needed). The final call comes after the first full draft. The 8-page column below is the upper bound, not the plan.", "",
         "Assumptions:",
         "- about 880 words per full page of text (10 pt, two columns);",
         "- floats as estimated below;",
         "- 6 pages = standard; 7–8 = paid over-length; hard maximum 8;",
         "- PDF only (no supplementary file): anything not in the PDF goes to the benchmark release docs.", "",
         f"**Text budget:** {total6} words (6-page) / {total8} words (8-page).",
         f"**Floats and references (6-page):** ≈ {fl:.2f} pages → text space ≈ {(6 - fl) * 880:.0f} words.",
         f"**8-page:** + Fig. 3 (0.3 p), + LC same-items or confusion (0.25 p) → text space ≈ {(8 - fl - 0.55) * 880:.0f} words.", "",
         "| Report section | 6 pages | 8 pages (paid) | Brief / destination |", "|---|---|---|---|"]
    L += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in BUDGET]
    L += ["", "## Floats (6-page)", "", "| Float | pages |", "|---|---|"] + [f"| {k} | {v} |" for k, v in FLOAT_PAGES_6.items()]
    L += ["", "## Cannot fit", "",
          "- **6 pages:** Fig. 3 architecture; LC same-items table; full paired table; per-class table; confusion matrices; error-analysis examples; P2-004 retest/timed/pilot details; T3 parser appendix; 150K appendix; matrix figure.",
          "- **8 pages:** the matrix figure (57 × 19, illegible); full 14-row paired table; per-class table (11 × 7); 150K appendix; T3 parser appendix; candidate precision rounds; LLM usage table. These go to the release docs."]
    (OUT.parent / "space_budget.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"briefs: {len(BRIEFS)}; text budget {total6} (6p) / {total8} (8p); floats {fl:.2f} p; "
          f"text space 6p ≈ {(6 - fl) * 880:.0f} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
