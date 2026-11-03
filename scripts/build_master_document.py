#!/usr/bin/env python3
"""FINAL-MASTER-AND-PAPER Part B: reports/final/RBI-ObliBench_Master_Document_v2.md (+ .docx via pandoc).

v2 (Command Center Part A, 2026-10-03): wording fixes A1–A9 and A11 only, listed in "Changes from v1"; no number changes.
v1 is kept unchanged at reports/final/RBI-ObliBench_Master_Document_v1.{md,docx} and in final_push_backups/.

Every number is read by key from the results bundles or metrics files (scripts/docnum.py). Scope decisions 2–4 apply:
- no t1v2 / t1v3 / Phase 4X material;
- gold = t1_validated_v1, single expert;
- reliability = the separate 30-item set + rater_1's P2-004 retest.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import docnum as D  # noqa: E402

OUT_MD = ROOT / "reports/final/RBI-ObliBench_Master_Document_v2.md"
OUT_DOCX = ROOT / "reports/final/RBI-ObliBench_Master_Document_v2.docx"
T = "R2:tables"
P = "R2:phase4"
SYS = [("majority", "Majority (in-sample)"), ("p2002_candidates", "P2-002 candidates"), ("class_blind", "Class-blind LLM"),
       ("class_aware", "Class-aware LLM"), ("final_agentic", "Final agentic (class filter + verifier)"),
       ("ablation_a", "Class-blind + verifier"), ("long_context", "Long-context LLM (100K cap)")]
LLM5 = ["class_blind", "class_aware", "final_agentic", "ablation_a", "long_context"]
SYS_NAME = dict(SYS) | {"comparator": "Structured comparator"}
# A2: "Ablation A/B/C" names toggles only; the `ablation_a` system is shown as "class-blind + verifier".
# A3: both class-filter-on-T1 rows state their verifier condition.
PAIRED_LABEL = {
    "Ablation A (verifier on): final agentic − class-blind + verifier":
        "Class filter, with verifier (ablation A toggle): final agentic − class-blind + verifier",
    "Class filter, no verifier: class-aware − class-blind": "Class filter, without verifier: class-aware − class-blind",
    "Verifier, class-blind: ablation A − class-blind": "Verifier, class-blind: class-blind + verifier − class-blind",
}
CF_NO_VERIFIER = "Class filter, no verifier: class-aware − class-blind"
CF_VERIFIER = "Ablation A (verifier on): final agentic − class-blind + verifier"
HMS_DEF = ("**Hybrid − source class** is the class-blind hybrid RRF with every paragraph of the query's own source class "
           "removed before fusion; it needs no target class, so it separates \"stop returning the source Direction's own "
           "near-duplicates\" from \"know the target class\" (`src/retrieval/systems.py`).")
MAJ_NOTE = ("Majority (in-sample) predicts the most frequent flag and judgement of the gold set itself, so it is an in-sample "
            "reference baseline, not a deployable system.")
CHANGES_V1 = [
    ("A1", "§15 References: LaTeX leftovers (`\\url{}`, accents such as Lù and Büttcher) are converted to plain text."),
    ("A2", "\"Ablation A/B/C\" now names the toggles only; the `ablation_a` system is shown as \"class-blind + verifier\" "
           "(§8, §9.3, §9.8)."),
    ("A3", "Both class-filter-on-T1 numbers state their condition (without verifier / with verifier) in the headline, "
           "§9.3 and §9.7, and §9.7 notes both."),
    ("A4", "§9.2 states how abstentions and unanswered items enter F1 and coverage, as the scoring code does it."),
    ("A5", "§9.2 notes that no CIs were computed for the `different` F1 column (listed as a follow-up)."),
    ("A6", "§2 states how RQ1's compliance question is operationalised (T2 and T1); the RQ text is unchanged."),
    ("A7", "§8 and §9.1 define \"Hybrid − source class\"."),
    ("A8", "§5 explains guideline versioning: v3 family, numbered rules v3.1–v3.10, flag derivation rule v3.6."),
    ("A9", "§8 and §9.2 note that the majority baseline is in-sample, not deployable."),
    ("A11", "Scoring asymmetry (abstentions scored as errors; long-context over-cap items excluded) stated in §9.2 and §10 point 4."),
]
RQ1 = ("Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind "
       "that class, and how much does a class-blind dense retriever lose relative to a class-aware system?")
RQ2 = ("For a subject issued in parallel across entity classes, can the system identify what one entity class is required "
       "to do that another entity class is not?")
RQ3 = ("Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair "
       "makes the metric resistant to concatenation/verbatim extraction?")
FUTURE = [
    ("Test–retest with a proper gap", "Re-label a stratified retest subset after a washout of days, not hours.",
     "The existing retest gap was short, so recall may inflate agreement.", "Low: one annotator, a few hours."),
    ("Second raters on all gold items", "Independent second (and third) ratings on every gold item, with adjudication.",
     "The gold is single-expert; inter-rater agreement is so far measured only on a separate sample.", "High: several annotator-days per rater."),
    ("Cross-encoder reranking", "Rerank retrieved paragraphs with a cross-encoder before judgement.",
     "Tests whether better candidate ordering helps T2 and the T1 judgement.", "Medium: a pinned model and one evaluation run."),
    ("A stronger (frontier) LLM run", "Rerun the T1 systems and the comparator with a frontier model.",
     "All results use Flash-Lite-class models; the `different` failure may shrink with a stronger model.", "Medium: paid API budget."),
    ("An ObliQA baseline", "Run the retrieval baselines on ObliQA as an external reference point.",
     "Positions RBI-ObliBench against an existing regulatory QA benchmark.", "Low–medium: data licence and an evaluation script."),
    ("A broad T3", "Extend T3 beyond cases derivable from Amendment Directions and update stamps.",
     "The current T3 is small and its gold shares a parser with the temporal filter (circular).", "High: manual temporal annotation."),
    ("A bigger T4 study with two raters", "More questions, and at least two blind raters per answer.",
     "T4 has thirty questions and one rater.", "Medium: rating time plus question drafting."),
    ("IndiaFinBench", "Zero-shot transfer evaluation on IndiaFinBench.", "Tests generalisation to SEBI/RBI QA.",
     "Low–medium: data access and an adapter."),
    ("A LangGraph port", "Port the plain-Python orchestration to LangGraph.", "Engineering parity with common agent stacks; no new science.",
     "Medium: dependency compatibility work."),
    ("Full FAQ/enforcement sources", "Use FAQ and enforcement text beyond the alignment samples.",
     "The alignment rates restricted these sources to validation and weak labels.", "High: alignment and cleaning."),
    ("A UI", "Built after the scope ladder: a public inspection interface that reads the sealed outputs only.", "Usability for compliance staff; outside the research questions; it changes no reported result.", "Done (inspection UI)."),
]


def a11_note() -> str:
    """A11: the scoring asymmetry between abstentions (errors) and long-context over-cap items (excluded)."""
    cov = D.get(f"{P}.t1_paired.Ablation C on T1: final agentic − class-aware.coverage.diff")
    return ("Abstentions are scored as errors, so the verifier's loss in F1 reflects both wrong answers and declined correct ones "
            f"(coverage {cov:+.3f}). Long-context items that exceeded the input cap are excluded rather than penalised, and every "
            f"comparison with long-context is made on the same {D.n(P + '.t1_systems.long_context.n_items')} items.")


def table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def build() -> str:
    L: list[str] = []
    w = L.append
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cmp_ok = D.opt(f"{P}.comparator.metrics.n_items", 0) > 0

    # 1 Title
    w("# RBI-ObliBench — Master Document\n")
    w("**A benchmark for entity-class applicability, differential obligations and metric integrity on Reserve Bank of India "
      "Master Directions, with a class- and date-aware retrieval pipeline**\n")
    w("- **Authors:** Karan Lokhande, Akash Goyal, Meer Magia")
    w("- **Institution:** SVKM's NMIMS Mukesh Patel School of Technology Management & Engineering, Mumbai")
    w(f"- **Date:** {now}")
    w("- **Version:** v2 (final-push master record; wording fixes only, see \"Changes from v1\")")
    w("- **Scope of this record:** the gold set is `t1_validated_v1` (single expert). Every number is read from "
      "`reports/results_v2.json`, `reports/final/error_analysis_v1.json` or the phase metrics files.\n")
    w("### Changes from v1\n")
    w("v2 changes wording only; every number is unchanged and still read from the same keys.\n")
    for cid, txt in CHANGES_V1:
        w(f"- **{cid}.** {txt}")
    w("- **Follow-up (not done):** add bootstrap CIs for `different` F1.\n")

    # 2 Executive summary
    w("## 1. Executive summary\n")
    w(f"RBI-ObliBench is built on {D.n(T + '.01_corpus.directions')} RBI Master Directions "
      f"({D.n(T + '.01_corpus.paragraphs')} paragraphs). It has four tasks:")
    w("- **T1:** applicability and differential obligation across entity classes;")
    w("- **T2:** cross-class counterpart retrieval;")
    w("- **T3:** temporal status;")
    w("- **T4:** an audit of the RePASs answer-faithfulness metric.\n")
    w("Around the benchmark we built a class- and date-aware retrieval-and-judgement pipeline as an engineering artefact. "
      "The benchmark is the contribution; the pipeline is evaluated on it.\n")
    w("**Research questions (verbatim):**\n")
    w(f"- **RQ1 — Applicability:** {RQ1}")
    w(f"- **RQ2 — Differential Obligation:** {RQ2}")
    w(f"- **RQ3 — Metric Integrity:** {RQ3}\n")
    w("**Headline findings:**\n")
    w(f"1. **The class filter improves retrieval.** nDCG@10 on `t2_xclass_t1` changes by {D.ci(T + '.06_t2_retrieval.p4_pipeline.t2_xclass_t1.paired')}. "
      "The gain is partly by construction, because relevance was labelled only for the target-class counterpart.")
    w(f"2. **It doesn't translate into better T1 judgement.** Class-aware − class-blind 3-way flag F1 (class filter, without verifier): "
      f"{D.ci(P + '.t1_paired.Class filter, no verifier: class-aware − class-blind.flag_macro_f1')}. "
      "No LLM system beats the P2-002 candidate labels on collapsed flag F1.")
    w(f"3. **`different` is the core failure mode.** Of {D.n('EA:a_different_missed.gold_different_units')} gold `different` "
      f"class units, {D.n(P + '.missed_by_every_llm_system.A_all_five_answered.missed')} are missed by every LLM system "
      f"(all five answered), or {D.n(P + '.missed_by_every_llm_system.B_answered_only.missed')} counting only the systems that answered.")
    w(f"4. **The verifier hurts T1.** Final agentic − class-aware 3-way flag F1: "
      f"{D.ci(P + '.t1_paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1')}.")
    w(f"5. **Long-context is competitive.** It answered {D.n(P + '.t1_systems.long_context.n_items')} items at the 100K cap. "
      f"Long-context − final agentic collapsed F1 on the same items: "
      f"{D.ci(P + '.t1_paired.Long-context − final agentic (same items).collapsed_macro_f1')}.")
    w(f"6. **RePASs concatenation gameability reproduces.** Concatenated − genuine composite: "
      f"{D.ci(T + '.09_t4.paired.concatenated - genuine.composite_score')} (pre-registered verdict: "
      f"{D.get(T + '.09_t4.verdicts.concatenated')}).")
    if cmp_ok:
        w(f"7. **The pairwise structured comparator** (the targeted experiment, frozen before any T1 run) reaches `different` F1 "
          f"{D.f3(P + '.comparator.different.different_f1')} and recall {D.f3(P + '.comparator.different.different_recall')}. "
          f"Comparator − class-aware `different` F1: {D.ci(P + '.preregistered_comparisons.comparator − class_aware.judgement.different_f1')}.")
    w("")

    # 3 RQs and tasks
    w("## 2. Research questions and tasks\n")
    w(f"- **RQ1 — Applicability:** {RQ1}")
    w(f"- **RQ2 — Differential Obligation:** {RQ2}")
    w(f"- **RQ3 — Metric Integrity:** {RQ3}\n")
    w("**Tasks:**")
    w("- **T1 (RQ1, RQ2).** Given a source obligation and its compared entity classes, give a per-class judgement "
      "(`same` / `different` / `none`) with a matched paragraph. The item's differential flag (shared / class-specific / absent) "
      "is derived from the judgements.")
    w("- **T2 (RQ1).** Retrieve the counterpart paragraph in a named target class.")
    w("- **T3.** Give the status of a paragraph (in force, amended, deleted) on an as-of date.")
    w("- **T4 (RQ3).** Score genuine, concatenated, negated and off-topic answers with RePASs, and compare with human faithfulness ratings.\n")
    w("We operationalise RQ1's compliance question as a source obligation plus a declared target class (T2) and as per-class "
      "judgement (T1).\n")

    # 4 Corpus
    w("## 3. Corpus\n")
    w(f"- **Harvest:** {D.n(T + '.01_corpus.directions')} of {D.n(T + '.01_corpus.directions_scanned')} listed Master Directions, "
      f"{D.n(T + '.01_corpus.paragraphs')} paragraphs. P1-004 recovered {D.n(T + '.01_corpus.p1004_recovered.previously_missing')} "
      "Directions missed by an earlier harvest; every later artefact uses the full set. (Source: `reports/results_v2.json` → `tables.01_corpus`.)")
    w("- **Segmentation and IDs:** paragraphs carry stable ids (`md_NNNNN::pNNNNN`) and clause paths; T1 items are `t1_<paragraph id>`.")
    w(f"- **Entity classes:** {D.n(T + '.01_corpus.entity_classes')} headings from RBI's listing: "
      f"{D.n(T + '.01_corpus.core_entity_classes')} regulated-entity classes and {D.n(T + '.01_corpus.function_headings')} RBI function headings.")
    w(f"- **Subject families:** {D.n(T + '.01_corpus.subject_families')}, derived from titles; "
      f"{D.n(T + '.01_corpus.directions_with_subject_family')} Directions have one.")
    w(f"- **Matrix:** {D.n(T + '.01_corpus.matrix.total_cells')} entity class × subject family cells, "
      f"{D.n(T + '.01_corpus.matrix.populated_cells')} populated, {D.n(T + '.01_corpus.matrix.ambiguous_cells')} ambiguous.")
    w(f"- **Known defects:** D2, {len(D.get(T + '.01_corpus.empty_title_directions'))} Directions have empty titles and no subject family.")
    w(f"- **Amended-text-only limitation:** {D.n(T + '.01_corpus.updated_as_on_titles')} titles carry an \"Updated as on\" stamp. "
      "RBI consolidates amendments in place, so the corpus holds only current text: the system can flag a later amendment but "
      "cannot show the pre-amendment wording.\n")

    # 5 Supplementary
    w("## 4. Supplementary sources (P2-003)\n")
    h = T + ".04_supplementary.harvest"
    w(f"- **FAQ:** {D.n(h + '.faq.stored_pages')} pages, {D.n(h + '.faq.items')} items.")
    w(f"- **Enforcement releases:** {D.n(h + '.enforcement.stored_pages')} releases; entity class resolved for "
      f"{D.n(h + '.enforcement.entity_class_resolved')}.")
    w(f"- **Amendment Directions:** {D.n(h + '.amendment.stored_pages')} pages. Withdrawn circulars and the repeal map feed T3.")
    for d in D.get(T + ".04_supplementary.decisions"):
        i = D.get(T + ".04_supplementary.decisions").index(d)
        k = f"{T}.04_supplementary.decisions.{i}"
        lo, hi = d["wilson95"]
        w(f"- **Alignment, {d['source']}:** {D.n(k + '.clean')}/{D.n(k + '.n')} clean = {D.f3(k + '.rate')} "
          f"(Wilson 95% [{lo:.3f}, {hi:.3f}]). Decision under the locked rule: `{d['decision']}`.")
    w("\nFAQ text is used only for validation and motivation; enforcement only as Direction-level weak labels.\n")

    # 6 T1 construction
    w("## 5. T1 benchmark construction\n")
    w(f"- **Candidate extraction (P2-001):** rules {D.get(T + '.02_candidates.rules')} keep "
      f"{D.n(T + '.02_candidates.candidates_kept')} candidates out of {D.n(T + '.02_candidates.paragraphs_with_cue')} paragraphs with a deontic cue.")
    w("- **Precision by rule version:**")
    rows = []
    for i, r in enumerate(D.get(T + ".02_candidates.precision_rounds")):
        k = f"{T}.02_candidates.precision_rounds.{i}"
        lo, hi = r["wilson_95"]
        rows.append([r["rules"], D.n(k + ".n"), D.n(k + ".true"), f"{D.f3(k + '.precision')} [{lo:.3f}, {hi:.3f}]"])
    w(table(["Rules", "n", "true", "precision [Wilson 95%]"], rows) + "\n\n(Source: `tables.02_candidates.precision_rounds`.)\n")
    w(f"- **Cross-class matching (P2-002):** bge-base-en-v1.5 plus lexical similarity, with threshold "
      f"{D.get(T + '.03_matching.threshold.value')}. Counterpart rate on the validation pairs: "
      f"{D.wilson(T + '.03_matching.overall.counterpart_rate')}.")
    w(f"- **Sampling (P2-004):** {D.n(T + '.05_t1_benchmark.sample')} candidates, seeded and stratified by source class, "
      "with at most four compared classes per item.")
    w(f"- **Validated set:** {D.n(T + '.05_t1_benchmark.validated')} validated and {D.n(T + '.05_t1_benchmark.rejected')} rejected "
      f"as not an obligation; the rejection rate is {D.wilson(T + '.05_t1_benchmark.rejection_rate')}.")
    w(f"- **Routes:** adjudicated {D.n(T + '.05_t1_benchmark.route_counts.adjudicated')}, retest-consistent "
      f"{D.n(T + '.05_t1_benchmark.route_counts.retest-consistent')}, single-pass {D.n(T + '.05_t1_benchmark.route_counts.single-pass')}.")
    w(f"- **Flags:** shared {D.n(T + '.05_t1_benchmark.flag_distribution.shared')}, class-specific "
      f"{D.n(T + '.05_t1_benchmark.flag_distribution.class-specific')}, absent {D.n(T + '.05_t1_benchmark.flag_distribution.absent')}.")
    w(f"- **Judgements:** same {D.n(T + '.05_t1_benchmark.judgement_distribution.same')}, different "
      f"{D.n(T + '.05_t1_benchmark.judgement_distribution.different')}, none {D.n(T + '.05_t1_benchmark.judgement_distribution.none')}.")
    w("- **Guidelines v3:** one item row plus one row per compared class; `not_obligation` for spans that impose no duty on a regulated "
      "entity; `same` = the same obligation in substance; `different` = same topic but a different requirement; `none` = no counterpart "
      "among the paragraphs checked. The flag is derived (any `different` → class-specific; otherwise any `same` → shared; all `none` → absent).")
    w("- **Guideline versions:** \"Guidelines v3\" is the guideline family for the per-class sheet; v3.1–v3.10 are its numbered "
      "rules in `data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md`, and the flag derivation used for the gold, every system and "
      "the comparator is rule v3.6 (`src/benchmark/t1.py`, `derive_flag`; only `none` and `unsure` → ambiguous). The file's header "
      "label \"Guidelines version: v3.1\" is a document revision (no minimum wait between retest passes, rule v3.10); it did not "
      "change the label rules.\n")

    # 7 Annotation and reliability
    w("## 6. Annotation and reliability\n")
    w("- **The gold is single-expert.** One annotator (`rater_1`) labelled every T1 item; adjudication was by the same annotator. "
      "No gold item has an independent second-rater label.")
    w("- **Inter-rater agreement on a separate sample (not part of the gold).** Thirty items drawn outside the T1 sample were labelled "
      "independently by three raters (`rater_1`–`rater_3`) before adjudication:")
    irr = T + ".05_t1_benchmark.irr.fleiss"
    w(f"  - Fleiss κ, class-row judgement: {D.kappa(irr + '.per_class_judgement')};")
    w(f"  - Fleiss κ, differential flag: {D.kappa(irr + '.differential_flag')};")
    w(f"  - Fleiss κ, not-obligation: {D.kappa(irr + '.not_obligation')}.")
    rt = T + ".05_t1_benchmark.retest.phase2.all_25"
    w(f"- **Blind test–retest (`rater_1`, {D.n(rt + '.n_items')} items; supplementary).** The actual gap between the passes was "
      f"{D.gap()} (file-level bounds; per-item times were not logged), so recall may inflate agreement:")
    w(f"  - Cohen's κ, flag: {D.kappa(rt + '.differential_flag')};")
    w(f"  - Cohen's κ, class-row judgement: {D.kappa(rt + '.per_class_judgement')}.")
    tr = T + ".05_t1_benchmark.timed_relabel"
    w(f"- **Timed blind re-label (evidence only).** Twenty single-pass items: flag κ {D.kappa(tr + '.differential_flag')}; "
      f"class-row κ {D.kappa(tr + '.per_class_judgement')}.")
    w("- **Candidates shown on the sheets.** Every sheet showed the same two P2-002 candidate paragraphs per compared class "
      "(bge-base-en-v1.5 top-1 and top-2), in random order and with no scores. This may bias judgements toward the P2-002 candidates; "
      "the same bias is disclosed for T2.")
    w("- **An earlier team review.** An earlier team review of thirty overlap items was revised after an AI reviewer's file-level "
      "feedback. It was recorded as not independent, never used for agreement, and used only as one input when `rater_1` adjudicated "
      "a subset of gold items.\n")

    # 8 T2/T3/T4 construction
    w("## 7. T2, T3 and T4 construction\n")
    for s_, lab in (("t2_xclass_t1", "`t2_xclass_t1`"), ("t2_xclass_p2002", "`t2_xclass_p2002`"), ("t2_supp_p2003", "`t2_supp_p2003`")):
        w(f"- **T2 {lab}** (n = {D.n(T + f'.06_t2_retrieval.p3001.{s_}.n_scored')}). Bias: {D.get(T + f'.06_t2_retrieval.p3001.{s_}.bias')}")
    w(f"- **T3:** {D.n(T + '.08_t3.built')} items built from Amendment Directions and update stamps, {D.n(T + '.08_t3.scored')} scored.")
    w(f"  - Parse spot-checks: {D.wilson(T + '.08_t3.precision_v1_human')} for rules v1; independent post-fix check "
      f"{D.wilson(T + '.08_t3.precision_independent_post_fix')}.")
    w("  - Known parser defect: a merged change's recorded old words include the previous change's new words.")
    w("  - **Circularity:** the gold and the temporal filter come from the same deterministic parser.")
    w(f"- **T4:** {D.n(T + '.09_t4.n_questions')} questions × four answer types (genuine, concatenated, negated, off-topic).")
    w(f"  - Human `faithful` / `answers_question` ratings on thirty answers, blind, by one rater; {len(D.get(T + '.09_t4.sensitivity.excluded'))} "
      "questions were flagged as bad questions (sensitivity analysis).")
    w("  - Questions and genuine answers were drafted by an LLM (gpt-oss-120b via Groq).\n")

    # 9 Systems
    w("## 8. Systems\n")
    w("- **Retrieval:** BM25 (bm25s), dense (bge-base-en-v1.5), hybrid reciprocal rank fusion, and a class-aware hybrid that restricts "
      "candidates to the target class's Directions.")
    w(f"  - {HMS_DEF}")
    w("- **T1 judgement systems:**")
    w("  - class-blind LLM;")
    w("  - class-aware LLM;")
    w("  - final agentic (class filter plus an NLI verifier that retries or abstains);")
    w("  - class-blind + verifier (the class-blind LLM plus the NLI verifier);")
    w("  - long-context LLM (all Directions of the compared classes, 100K-token cap);")
    w("  - majority (in-sample) and the P2-002 candidate labels as baselines.")
    w(f"  - {MAJ_NOTE}")
    w("- **Ablations A–C** name toggles only: A = class filter, B = temporal filter, C = verifier.")
    rm = "RM:llm"
    w(f"- **LLM settings:** {D.get(rm + '.p4_model')} for every P4 system and the comparator; temperature {D.get(rm + '.temperature')}; "
      f"thinking {D.get(rm + '.thinking')}; JSON mode; frozen prompts (sha256 in config). NLI verifier: "
      f"{D.get('RM:retrieval.verifier.nli_model')} at a pinned revision.")
    w("- **Pairwise structured comparator (the targeted experiment):**")
    w("  - one call per (item, compared class) over the two shown candidate paragraphs;")
    w("  - the model extracts thirteen fields (actor, action, object, scope, condition, threshold, amount, percentage, frequency, "
      "deadline, exception, documentation, reporting) from both sides and compares them field by field;")
    w("  - a fixed rule decides `same` / `different` / `none` (precedence same > different > none); the model never gives the verdict;")
    hs = D.get(rm + ".comparator.sha256")
    w(f"  - prompt and rule frozen before any T1 run (system prompt `{hs['comparator_system.txt'][:12]}…`, "
      f"rule `{hs['comparator_rule.py'][:12]}…`);")
    w("  - development set: the separate 30-item set (not the gold), with one revision for a field-extraction bug.\n")

    # 10 Results
    w("## 9. Results\n")
    w("CIs are 95% percentile bootstrap intervals over item resamples, labelled by `src/eval/ci_format.py`.\n")
    w("### 9.1 T2 — counterpart retrieval (nDCG@10)\n")
    rows = []
    for k, lab in (("bm25", "BM25"), ("dense", "Dense"), ("hybrid_rrf", "Hybrid RRF"),
                   ("hybrid_minus_source_class", "Hybrid − source class"), ("class_aware", "Class-aware hybrid")):
        rows.append([lab] + [D.ci(T + f".06_t2_retrieval.p3001.{s}.systems.{k}.ndcg") for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003")])
    w(table(["System", "t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"], rows))
    w("\n(Source: `tables.06_t2_retrieval.p3001`.) Class filter, pipeline retrieval stage (ON − OFF): "
      + "; ".join(f"{s} {D.ci(T + f'.06_t2_retrieval.p4_pipeline.{s}.paired')}" for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003")) + ".\n")
    w("Hybrid − source class = hybrid RRF with the query's own source class removed before fusion (defined in §8).\n")

    w(f"### 9.2 T1 — main table (gold: {D.n(T + '.05_t1_benchmark.validated')} items)\n")
    rows = []
    for k, lab in SYS:
        b = f"{P}.t1_systems.{k}"
        rows.append([lab, D.n(b + ".n_items"), D.ci(b + ".flag_macro_f1"), D.ci(b + ".collapsed_macro_f1"),
                     D.ci(b + ".judgement_macro_f1"), D.f3(f"{P}.t1_different.{k}.different_f1"), D.ci(b + ".coverage")])
    if cmp_ok:
        b = f"{P}.comparator.metrics"
        rows.append(["Structured comparator", D.n(b + ".n_items"), D.ci(b + ".flag_macro_f1") + " *", D.ci(b + ".collapsed_macro_f1") + " *",
                     D.ci(b + ".judgement_macro_f1"), D.f3(f"{P}.comparator.different.different_f1"), D.ci(b + ".coverage")])
    w(table(["System", "n", "3-way flag F1", "Collapsed F1", "Judgement macro-F1", "`different` F1", "Coverage"], rows))
    w("\n(Source: `phase4.t1_systems`, `phase4.t1_different`, `phase4.comparator`; the harness reproduces the published v1 table exactly.) "
      "* The comparator's flag is derived from its judgements with the v3.6 rule; its judgement metrics are the pre-registered ones. "
      "CIs were not computed for the `different` F1 column (point estimates).\n")
    w(f"**Scoring asymmetry.** {a11_note()}\n")
    w("**How abstentions are scored.** Abstentions stay in the denominator. A class judgement the system abstained on is scored as "
      "`unsure`, which matches no label: it is a miss for its gold judgement and a hit for none. The item flag is then derived with "
      "rule v3.6; an item whose flag cannot be derived is `ambiguous` and counts as wrong in both 3-way and collapsed flag F1. "
      "Coverage is the share of items whose flag is not `ambiguous`. Items a system never answered are not scored: long-context "
      f"answered {D.n(P + '.t1_systems.long_context.n_items')} of {D.n(T + '.05_t1_benchmark.validated')} items, so its row and "
      "its paired comparisons use those items only (`src/rag/analysis.py`, `src/rag/evaluation.py`).\n")
    w("Majority (in-sample) is a reference baseline built from the gold distribution itself, not a deployable system.\n")
    w("### 9.3 Paired differences (same items)\n")
    rows = [[PAIRED_LABEL.get(k, k), D.n(f"{P}.t1_paired.{k}.n_items"), D.ci(f"{P}.t1_paired.{k}.flag_macro_f1"), D.ci(f"{P}.t1_paired.{k}.collapsed_macro_f1"),
             D.ci(f"{P}.t1_paired.{k}.coverage")] for k in D.get(f"{P}.t1_paired")]
    w(table(["Comparison", "n", "Δ 3-way F1", "Δ collapsed F1", "Δ coverage"], rows) + "\n\n(Source: `phase4.t1_paired`.)\n")
    if cmp_ok:
        w("**Pre-registered comparator comparisons (amendment 3):**\n")
        rows = []
        for b in ("class_aware", "p2002_candidates"):
            k = f"{P}.preregistered_comparisons.comparator − {b}"
            rows.append([f"comparator − {b}", D.n(k + ".judgement.n_items"), D.ci(k + ".judgement.judgement_macro_f1"),
                         D.ci(k + ".judgement.different_f1"), D.ci(k + ".judgement.different_recall"), D.ci(k + ".flag.collapsed_macro_f1")])
        w(table(["Comparison", "n items", "Δ judgement macro-F1", "Δ `different` F1", "Δ `different` recall", "Δ collapsed flag F1"], rows))
        w("\n(Source: `phase4.preregistered_comparisons`.)\n")
    w("### 9.4 Long-context and the verifier\n")
    w(f"- **Long-context:** at the uniform 100K cap, {D.n(P + '.t1_systems.long_context.n_items')} of {D.n(T + '.05_t1_benchmark.validated')} items were answered. On the same "
      f"items, long-context − final agentic: 3-way {D.ci(P + '.t1_paired.Long-context − final agentic (same items).flag_macro_f1')}, "
      f"collapsed {D.ci(P + '.t1_paired.Long-context − final agentic (same items).collapsed_macro_f1')}.")
    w("  - The 150K-cap run is superseded (it stopped during an API outage) and appears only in the release appendix.")
    w(f"- **Verifier (ablation C on T1):** final agentic − class-aware: 3-way {D.ci(P + '.t1_paired.Ablation C on T1: final agentic − class-aware.flag_macro_f1')}, "
      f"coverage {D.ci(P + '.t1_paired.Ablation C on T1: final agentic − class-aware.coverage')}.")
    w(f"  - Class-blind side: {D.ci(P + '.t1_paired.Verifier, class-blind: ablation A − class-blind.flag_macro_f1')}.\n")
    w("### 9.5 T3 and ablation B\n")
    w(f"- **Filter on:** status exact match {D.ci(T + '.08_t3.t3.on.status_exact_match')}. This is **circular by construction**: "
      "the gold and the filter come from the same parser.")
    w(f"- **Filter off:** {D.ci(T + '.08_t3.t3.off.status_exact_match')}; the model answered \"in force, original\" on "
      f"{D.n(T + '.08_t3.t3.off.pred_status.in_force_original')} of {D.n(T + '.08_t3.t3.off.n')} items.")
    w(f"- **Ablation B (ON − OFF):** {D.ci(T + '.08_t3.t3.paired.status_exact_match')}.\n")
    w("### 9.6 T4 — RePASs audit\n")
    rows = [[t, D.ci(T + f".09_t4.by_type.{t}.composite_score")] for t in ("genuine", "concatenated", "adv_negated", "adv_offtopic")]
    w(table(["Answer type", "RePASs composite (mean [95% CI])"], rows) + "\n")
    for t in ("concatenated", "adv_negated", "adv_offtopic"):
        w(f"- {t} − genuine: {D.ci(T + f'.09_t4.paired.{t} - genuine.composite_score')}; pre-registered verdict: "
          f"{D.get(T + f'.09_t4.verdicts.{t}')}.")
    w(f"- RePASs vs human `faithful`: Spearman ρ {D.ci(T + '.09_t4.human.all_rated.spearman_composite_score_vs_faithful')}; "
      f"vs `answers_question`: ρ {D.ci(T + '.09_t4.human.all_rated.spearman_composite_score_vs_answers_question')}.")
    w(f"- **Exploratory repair:** it ranks genuine above concatenated ({D.ci(T + '.09_t4.repair.genuine - concatenated')}), but it no "
      f"longer tracks human faithfulness (ρ {D.ci(T + '.09_t4.human.all_rated.spearman_repaired_vs_faithful')}). It is **not usable** as it stands.\n")
    w("### 9.7 Ablations A–C\n")
    rows = [[r["ablation"], r["toggle"], r["measure"] + (" (with verifier)" if r["ablation"] == "A" and r["measure"].startswith("T1") else ""),
             r["n"], r["on_minus_off"]] for r in D.get(T + ".10_ablations.rows")]
    w(table(["Ablation", "Toggle", "Measure", "n", "ON − OFF"], rows) + "\n\n(Source: `tables.10_ablations.rows`.)\n")
    w(f"Two class-filter-on-T1 numbers exist, one per verifier condition. With the verifier on (final agentic − class-blind + "
      f"verifier, the ablation A row above): {D.ci(f'{P}.t1_paired.{CF_VERIFIER}.flag_macro_f1')}. Without the verifier "
      f"(class-aware − class-blind, headline finding 2): {D.ci(f'{P}.t1_paired.{CF_NO_VERIFIER}.flag_macro_f1')}.\n")
    w("### 9.8 The `different` failure\n")
    m = P + ".missed_by_every_llm_system"
    w(f"- Gold `different` class units: {D.n(m + '.gold_different_units')}.")
    w(f"- **Definition A** (all five LLM systems answered the item, and none said `different`): {D.n(m + '.A_all_five_answered.missed')} missed by all.")
    w(f"- **Definition B** (only the systems that answered are counted, including items long-context never answered): "
      f"{D.n(m + '.B_answered_only.missed')}.")
    if cmp_ok:
        w(f"- The comparator gets {D.n(m + '.A_all_five_answered.comparator_correct')} of the definition-A units and "
          f"{D.n(m + '.B_answered_only.comparator_correct')} of the definition-B units right.")
    w("\n**Retrieval vs reasoning.** An error is a retrieval failure if the gold matched paragraph was not in that system's context, "
      "and a reasoning failure if it was.\n")
    rows = []
    for s in LLM5 + (["comparator"] if cmp_ok else []):
        b = f"{P}.retrieval_vs_reasoning.per_system.{s}"
        rows.append([SYS_NAME[s], f"{D.n(b + '.errors')}/{D.n(b + '.gold_different_units')}", D.opt(b + ".failure_types.retrieval", 0),
                     D.opt(b + ".failure_types.reasoning", 0), D.opt(b + ".error_types.different→same", 0), D.opt(b + ".error_types.different→none", 0)])
    w(table(["System", "Errors", "Retrieval", "Reasoning", "→ same", "→ none"], rows))
    w("\n(Source: `phase4.retrieval_vs_reasoning`.) The human error-category pass was not done, so no category breakdown is reported.\n")
    if cmp_ok:
        w("### 9.9 Comparator: development evidence and T1 result\n")
        w(f"- **Development set** (the separate 30-item set, {D.n(P + '.comparator_dev.final.n_units')} class units; development evidence only): "
          f"judgement macro-F1 {D.f3(P + '.comparator_dev.final.judgement_macro_f1')}, `different` F1 "
          f"{D.f3(P + '.comparator_dev.final.per_label.different.f1')}.")
        w(f"- **T1 gold:** {D.n(P + '.llm_calls.comparator_t1_calls')} class units; `different` recall "
          f"{D.f3(P + '.comparator.different.different_recall')}, precision {D.f3(P + '.comparator.different.different_precision')}; "
          f"different→same {D.n(P + '.comparator.different.different_to_same')}, different→none {D.n(P + '.comparator.different.different_to_none')}.\n")

    # 11 Discussion
    w("## 10. Discussion\n")
    w("Six findings, stated as findings rather than as a claim that our agent wins:\n")
    w("1. **Class-aware filtering improves retrieval.** On T2 the class filter raises nDCG@10 by a wide margin, partly by construction "
      "because relevance covers only the target-class counterpart.")
    w("2. **It doesn't translate into better T1 judgement.** On T1 the class filter has no significant effect, and no LLM system beats "
      "the embedding-based P2-002 candidates on collapsed flag F1. Finding the counterpart is not the hard part.")
    w("3. **`different` is the core failure mode.** Most gold `different` units are missed by every LLM system. In most errors the gold "
      "paragraph was in context, so these are reasoning failures, not retrieval failures.")
    w("4. **The verifier hurts T1.** It lowers 3-way flag F1 and coverage, because it abstains on many correct first answers. Its "
      "whole-paragraph NLI premise is a poor test for a one-sentence rationale. " + a11_note())
    w("5. **Long-context is competitive.** Without retrieval it ties the retrieval systems on 3-way F1 and beats both verifier systems on "
      "collapsed F1. On T1, where the relevant Directions fit in a 100K prompt, retrieval was not the bottleneck.")
    w("6. **RePASs concatenation gameability reproduces** on RBI text. Negated and off-topic answers do not fool it, and RePASs does not "
      "track whether an answer addresses the question.")
    if cmp_ok:
        w("\nThe structured comparator tests whether making the comparison explicit field by field helps on `different`. "
          "Its result is reported in §9.3 and §9.9, against the pre-registered comparisons.")
    w("")

    # 12 Limitations
    w("## 11. Limitations\n")
    lo_, hi_ = D.class_range()
    w(f"- **Size:** {D.n(T + '.05_t1_benchmark.validated')} validated T1 items; source classes have between {lo_} and {hi_} items each, so per-class results have wide intervals.")
    w("- **Single-expert gold:** reliability is measured on a separate sample, not on the gold itself.")
    w(f"- **Short-interval retest:** {D.gap()}, so recall may inflate agreement.")
    w("- **T2 construction bias:** each relevance set favours one retriever; relevance covers only the target-class counterpart.")
    w("- **T3:** circularity, and the old-words parser defect.")
    w("- **Historical text:** the corpus holds only amended text.")
    w("- **T4:** small, with LLM-drafted questions and one rater.")
    w("- **The RePASs repair** is exploratory and not usable.")
    w("- **Models:** Flash-Lite-class models only, on free tiers.")
    w("- **Scope Ladder cuts** (all seven applied):")
    w("  1. IndiaFinBench zero-shot transfer not run;")
    w("  2. no cross-encoder reranking and no LangGraph (plain Python orchestration);")
    w("  3. ObliQA / ObliQA-MP as related-work positioning only;")
    w("  4. FAQ / enforcement hand-alignment reduced to the minimum samples;")
    w("  5. T4 reduced to the smallest n with a usable CI;")
    w("  6. T3 restricted to deterministic cases from Amendment Directions and update stamps;")
    w("  7. release limited to benchmark + code + dataset card. An inspection UI was built after the scope ladder; it reads the sealed outputs only and changes no reported result.\n")

    # 13 Future work
    w("## 12. Future Work (ranked)\n")
    w(table(["Rank", "Item", "What", "Why it matters", "Rough effort"],
            [[i + 1, *row] for i, row in enumerate(FUTURE)]) + "\n")

    # 14 Reproducibility
    w("## 13. Reproducibility and release\n")
    w("- **Pointer-only release:** every item carries a pointer (Direction id, paragraph id, character offsets, source URL, harvest "
      "date, sha256 of the paragraph text). `rehydrate.py` rebuilds the text from RBI's own URLs and checks the hashes.")
    w("- **Release check:** it fails on any excluded path, key-like string, oversized file, or run of thirty or more words copied from the corpus.")
    w("- **Licences:** MIT for the code; CC BY 4.0 for the annotations and derived metadata. RBI documents are \"All Rights Reserved\" "
      "and are not included. Third-party: bge-base-en-v1.5 MIT; nli-deberta-v3-xsmall Apache-2.0; bm25s MIT; deberta-large-mnli MIT; "
      "legal-bert-base-uncased CC BY-SA 4.0; RePASs has no licence file (used unmodified, not redistributed).")
    w("- **Archive:** Zenodo DOI to be assigned (placeholder until deposit).")
    w("- **Commands:** in the README (one command per table; tests; release check).\n")

    # 15 AI use
    w("## 14. AI-use statement\n")
    w("- **Code generation:** Claude Code (Anthropic) wrote the repository code (scraper, preprocessing, candidate extraction, matching, "
      "benchmark tooling, evaluation and statistics scripts) under the authors' direction.")
    w("- **Analysis:** Claude Code wrote and ran the analysis and bootstrap scripts; the authors reviewed the outputs.")
    w("- **Internal reports:** Claude Code drafted the internal phase reports and this record.")
    w("- **Inspection interface:** Claude Code also wrote the inspection interface and its build scripts under the authors' direction.")
    w("- **LLM systems under study (system outputs, never labels):** gemini-3.5-flash-lite (P4 systems, long-context, comparator); "
      "gpt-oss-120b via Groq (T4 question drafting and genuine answers).")
    w("- **Human labels:** every human label is manual. The early team-review file set described in §6 was revised after AI-reviewer "
      "file-level feedback; it was recorded as not independent and never used for agreement.")
    w("- **Provider terms:** under the Gemini API free tier, outputs may be published and were not used to train any model; free-tier "
      "inputs may be used by Google, including human review. Our prompts contained only public RBI text and no personal data. Groq "
      "terms: https://groq.com/terms-of-use.\n")

    # 16 References
    w("## 15. References\n")
    w(refs_md())

    # 17 Appendix timeline
    w("\n## Appendix A. Project timeline\n")
    w(table(["Phase", "Outcome"], [
        ["Phase 0", "Repository audit and plan (`reports/phase0_audit.md`)."],
        ["Phase 1", "Corpus QA, metadata normalisation and the entity class × subject family matrix, annotation protocol, three-rater pilot (`reports/phase1_*`)."],
        ["P1-004", "Corpus repair to the full Direction set; pilot validation."],
        ["P2-001", "Obligation candidate extraction, with four precision rounds."],
        ["P2-002", "Cross-class matching and the threshold decision."],
        ["P2-003", "Supplementary sources (FAQ, enforcement, amendments) and the locked alignment decisions."],
        ["P2-004", "T1 sample, single-expert labelling, retest, the separate 30-item three-rater set, adjudication, gold v1."],
        ["P3-001", "LLM client, T2 relevance sets, retrieval and T1 baselines."],
        ["P3-002", "T4 RePASs audit and the exploratory repair."],
        ["P4-001", "T3 set, class- and date-aware pipeline, system runs, ablations A–C, long-context at the 100K cap."],
        ["P5-001 Part A", "Results consolidation, report draft, dataset card, pointer-only release, error analysis."],
        ["Final push", "Verified references; venue preparation (AISIGH–SD 2026); comparator development and freeze; sealed predictions; "
                       "comparator T1 run and Phase 4 scoring on gold v1; this master document and the paper draft."],
    ]))
    return "\n".join(L) + "\n"


# LaTeX accent command -> Unicode combining mark (pylatexenc is not in the lock, so a small map).
ACCENTS = {"`": "\u0300", "'": "\u0301", "^": "\u0302", "~": "\u0303", "=": "\u0304", "u": "\u0306", ".": "\u0307",
           '"': "\u0308", "H": "\u030b", "v": "\u030c", "c": "\u0327", "k": "\u0328"}


def tex_to_text(s: str) -> str:
    """One bib field value -> plain text: \\url{} / \\href{}{} unwrapped, accents to Unicode, escapes and braces dropped."""
    import re
    import unicodedata
    s = re.sub(r"\\href\{([^}]*)\}\{([^}]*)\}", r"\2 (\1)", s)
    s = re.sub(r"\\url\{([^}]*)\}", r"\1", s)

    def accent(m: re.Match) -> str:
        return m.group(2) + ACCENTS[m.group(1)]
    # {\`u}, \`{u}, \`u, \c{c}, \v s
    s = re.sub(r"\\([`'^~=.\"])\s*\{?([A-Za-z])\}?", accent, s)
    s = re.sub(r"\\([uvHck])(?:\{([A-Za-z])\}|\s+([A-Za-z]))", lambda m: (m.group(2) or m.group(3)) + ACCENTS[m.group(1)], s)
    s = re.sub(r"\\([&%_$#])", r"\1", s)
    s = s.replace("---", "—").replace("--", "–").replace("~", " ")
    s = s.replace("{", "").replace("}", "")
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", s)).strip()


def bib_fields() -> list[tuple[str, dict[str, str]]]:
    import re
    bib = (ROOT / "paper/aisigh/refs_verified.bib").read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", bib, re.S):
        key, body = m.group(1), m.group(2)
        out.append((key, {k.lower(): tex_to_text(v) for k, v in re.findall(r"(\w+)\s*=\s*\{(.*?)\},?\s*\n", body + "\n", re.S)}))
    return out


def refs_md() -> str:
    out = []
    for key, f in bib_fields():
        parts = [f.get("author", ""), f"*{f.get('title', '')}*", f.get("booktitle") or f.get("journal") or f.get("howpublished", ""),
                 f.get("year", "")]
        extra = f.get("doi") and f"doi:{f['doi']}" or (f.get("eprint") and f"arXiv:{f['eprint']}") or f.get("url", "")
        out.append(f"- [{key}] " + ". ".join(p for p in parts if p) + (f". {extra}" if extra else "") + ".")
    return "\n".join(out)


def main() -> int:
    text = build()
    OUT_MD.write_text(text, encoding="utf-8")
    subprocess.run(["pandoc", str(OUT_MD), "-o", str(OUT_DOCX), "--from", "markdown", "--to", "docx"], check=True)
    used = ROOT / "reports/private/scratch/master_document_sources.json"
    used.write_text(json.dumps(D.used_report(), indent=1))
    print(f"{OUT_MD.relative_to(ROOT)} ({len(text.split())} words); {OUT_DOCX.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
