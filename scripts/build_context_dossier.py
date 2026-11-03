#!/usr/bin/env python3
"""FINAL-CONTEXT-DOSSIER: reports/private/RBI-ObliBench_Context_Dossier_<date>.md (+ .docx). Private; repo records only.

Every factual line is tagged:
- [CONFIRMED] = backed by a file or output, with the path cited;
- [PLANNED] = specified but not run;
- [ASSUMED] = inferred, with the reason given.

Numbers come from the results bundles and metrics files (scripts/docnum.py), or from
`reports/private/final_push/master/dossier_facts_v1.json`, which this script writes from live read-only checks
(pytest, release_check, git HEAD, ledger, hashes). It prints no key values and no rater-id mapping.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import docnum as D  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime.now(IST)
OUT_MD = ROOT / f"reports/private/RBI-ObliBench_Context_Dossier_{NOW:%Y-%m-%d}.md"
FACTS = ROOT / "reports/private/final_push/master/dossier_facts_v1.json"
T, P = "R2:tables", "R2:phase4"
C, PL, AS = "[CONFIRMED]", "[PLANNED]", "[ASSUMED]"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(cmd: list[str], timeout=900) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout).stdout


def facts() -> dict:
    py = run([sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider"]).strip().splitlines()[-1]
    rc = run([sys.executable, "scripts/release_check.py", "--out", "reports/private/scratch/release_check_dossier.txt"]).strip().splitlines()
    cp = run([sys.executable, "scripts/check_paper.py"]).strip().splitlines()
    ledger = json.loads((ROOT / "data/llm_cache/quota_ledger.json").read_text())
    frozen = {
        "t1_validated_v1.jsonl": "data/benchmark/t1/t1_validated_v1.jsonl",
        "comparator FROZEN.json": "configs/comparator_v1/FROZEN.json",
        "comparator_system.txt": "configs/comparator_v1/comparator_system.txt",
        "comparator_user.txt": "configs/comparator_v1/comparator_user.txt",
        "comparator_rule.py": "src/rag/comparator_rule.py",
        "refs_verified.bib": "paper/aisigh/refs_verified.bib",
        "results_v1.json": "reports/results_v1.json",
        "results_v2.json": "reports/results_v2.json",
        "phase4_input_manifest_v1.json": "reports/private/final_push/phase4_input_manifest_v1.json",
        "phase4_input_manifest_v2.json": "reports/private/final_push/phase4_input_manifest_v2.json",
        **{p.name: str(p.relative_to(ROOT)) for p in sorted((ROOT / "docs/protocol").glob("*.md"))},
    }
    f = {"generated_ist": NOW.strftime("%Y-%m-%d %H:%M IST"), "repo": str(ROOT), "machine": platform.platform(),
         "python": platform.python_version(), "git_head": run(["git", "rev-parse", "--short", "HEAD"]).strip(),
         "git_head_date": run(["git", "log", "-1", "--format=%cd", "--date=short"]).strip(),
         "pytest_summary": py, "tests_passed": int(re.search(r"(\d+) passed", py).group(1)) if "passed" in py else None,
         "release_check": [l for l in rc if l.startswith("RESULT")][-1] if rc else None,
         "release_publishable_files": int(re.search(r"(\d+) publishable", rc[0]).group(1)) if rc else None,
         "check_paper": cp[0] if cp else None, "ledger": ledger, "frozen_sha256": {k: sha(ROOT / v) for k, v in frozen.items() if (ROOT / v).exists()},
         "frozen_paths": frozen}
    m = re.search(r"placeholders: (\d+)", f["check_paper"] or "")
    f["paper_placeholders"] = int(m.group(1)) if m else None
    FACTS.parent.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps(f, indent=1, default=str) + "\n")
    return f


def table(h, rows):
    return "\n".join(["| " + " | ".join(h) + " |", "|" + "|".join("---" for _ in h) + "|"] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def publish_status(path: str) -> str:
    from src.release.check import excluded_reason
    ign = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0
    return "private" if ign or excluded_reason(path) else "public"


def build(F: dict) -> str:
    L = []
    w = L.append
    cmp_ok = D.opt(f"{P}.comparator.metrics.n_items", 0) > 0
    pa = f"{P}.t1_paired"
    m = f"{P}.missed_by_every_llm_system"

    w(f"# RBI-ObliBench — Context-transfer dossier ({NOW:%Y-%m-%d})\n")
    w("> PRIVATE. Lives in `reports/private/`; excluded from the release; never copied into `paper/` or `release/`.\n")

    # 1
    w("## 1. How to read this document\n")
    w(f"- {C} **Evidence tags:** {C} = backed by a file or output (path cited); {PL} = specified but not run; {AS} = inferred (reason given).")
    w(f"- {C} **Generated:** {F['generated_ist']} by `scripts/build_context_dossier.py` from repo records only (`dossier_facts_v1.json`).")
    w(f"- {C} **Repo:** `{F['repo']}`; machine `{F['machine']}`; Python {F['python']}.")
    w(f"- {C} **Git HEAD** (read-only): `{F['git_head']}` ({F['git_head_date']}). Nothing after Phase 1 is committed; no git actions were taken in the final push.")
    w(f"- {C} **Tests:** `{F['pytest_summary']}`. **release_check:** `{F['release_check']}` ({F['release_publishable_files']} publishable files).\n")

    # 2
    w("## 2. One-page summary\n")
    w(f"- {C} **Project:** RBI-ObliBench, a benchmark built on {D.n(T + '.01_corpus.directions')} RBI Master Directions "
      f"({D.n(T + '.01_corpus.paragraphs')} paragraphs), plus a class- and date-aware RAG pipeline evaluated on it (`reports/final/rbi_oblibench_report.md`).")
    w(f"- {C} **RQ1 — Applicability:** Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system? (`docs/prompts/RBI-ObliBench-Master-Prompt-SOLO.md`)")
    w(f"- {C} **RQ2 — Differential Obligation:** For a subject issued in parallel across entity classes, can the system identify what one entity class is required to do that another entity class is not?")
    w(f"- {C} **RQ3 — Metric Integrity:** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair makes the metric resistant to concatenation/verbatim extraction?")
    w(f"- {C} **Headline results** (`reports/results_v2.json`):")
    w(f"  - class filter on T2 `t2_xclass_t1`: {D.ci(T + '.06_t2_retrieval.p4_pipeline.t2_xclass_t1.paired')};")
    w(f"  - no LLM beats P2-002 on collapsed T1 F1;")
    w(f"  - `different` missed by every LLM system: {D.n(m + '.A_all_five_answered.missed')}/{D.n(m + '.gold_different_units')} (all five answered), "
      f"{D.n(m + '.B_answered_only.missed')} (answered only);")
    w(f"  - verifier hurts T1: {D.ci(pa + '.Ablation C on T1: final agentic − class-aware.flag_macro_f1')};")
    w(f"  - RePASs concatenation gameability reproduces: {D.ci(T + '.09_t4.paired.concatenated - genuine.composite_score')}.")
    if cmp_ok:
        w(f"  - comparator − class-aware `different` F1: {D.ci(P + '.preregistered_comparisons.comparator − class_aware.judgement.different_f1')}.")
    w(f"- {C} **Where things stand:** the Phase 4 core is scored on gold v1; the master document and the full paper draft are written "
      "(`reports/final/RBI-ObliBench_Master_Document_v2.md`, `paper/aisigh/main.tex`).")
    w(f"- {PL} **Next three actions:**")
    w("  1. The authors rewrite the paper prose in their own words.")
    w("  2. Page check and number audit on Overleaf.")
    w("  3. Zenodo deposit and DOI, then CMT submission by 2026-10-10.\n")

    # 3
    w("## 3. Project overview\n")
    w(f"- {C} **Capstone title:** \"An Agentic RAG Compliance System for RBI Master Directions\" (`docs/prompts/RBI-ObliBench-Master-Prompt-SOLO.md`).")
    w(f"- {C} **Research artefact:** RBI-ObliBench, with tasks T1–T4 (`reports/final/rbi_oblibench_report.md` §6).")
    w(f"- {C} **Framing rule:** the benchmark is the contribution; the agent is the engineering artefact evaluated on it (`docs/prompts/P5-001.md`, `docs/prompts/FINAL-MASTER-AND-PAPER.md`).")
    w(f"- {C} **Tasks:**")
    w("  - T1: per-class same/different/none judgements plus a derived flag;")
    w("  - T2: counterpart retrieval;")
    w("  - T3: temporal status;")
    w("  - T4: a RePASs audit.\n")

    # 4
    w("## 4. People and roles\n")
    w(f"- {C} **Authors (balanced co-authors):** Karan Lokhande, Akash Goyal, Meer Magia. Author order confirmed 2026-10-02 (`paper/aisigh/main.tex` author block).")
    w(f"- {C} **Phase 1, Akash:** corpus acquisition, extraction, paragraph segmentation and the full-corpus Kaggle harvest (git log: \"Phase 1 (Akash)…\", \"Sync Akash's full-corpus Kaggle harvest\"; `reports/phase1_akash_corpus.md`; tag `p1-akash-complete`).")
    w(f"- {C} **Phase 1, Meer:** corpus QA, annotation protocol, Week-2 risk checks, pilot (git log \"Phase 1 (Meer)…\"; `reports/phase1_meer_annotation.md`; tag `p1-meer-complete`).")
    w(f"- {C} **Phase 1, Karan:** metadata normalisation and the Subject × Entity-Class matrix (git log \"Phase 1 (Karan)…\"; `reports/phase1_karan_matrix.md`). From P1-004 on, Karan directed every phase (git log; `docs/prompts/`).")
    w(f"- {C} **Annotation:** rater_1 labelled the T1 gold; rater_1–rater_3 labelled the separate 30-item set (`reports/p2004_irr_v1.md`). The rater-id mapping is in `reports/private/` (path: `reports/private/rater_map.json`).")
    w(f"- {AS} **Guide:** not named in any repo record (searched `docs/`, `reports/`); see §19.")
    w(f"- {C} **Claude (web):** prompts and audits. **Claude Code:** execution (code, runs, reports), per the prompts and the AI-use statement (`paper/aisigh/briefs/11_ai_use_ack.md`).\n")

    # 5
    w("## 5. Environment and tooling\n")
    rm = "RM:"
    w(f"- {C} **Paths:** repo `{F['repo']}` (one laptop, one repo, one session; `reports/private/final_push/state_manifest_v1.md`).")
    pk = D.get("RM:environment.packages")
    w(f"- {C} **Python {D.get('RM:environment.python')}**; packages: " + ", ".join(f"{k} {v}" for k, v in pk.items() if v)
      + " (`reports/private/final_push/p2/reproducibility_manifest_v1.json`; locks `requirements-lock.txt`, `requirements-repass-lock.txt`).")
    w(f"- {C} **Pinned models:**")
    w(f"  - {D.get('RM:retrieval.embedding_model')} @ `{D.get('RM:retrieval.embedding_revision')}` (MIT);")
    w(f"  - {D.get('RM:retrieval.verifier.nli_model')} @ `{D.get('RM:retrieval.verifier.nli_revision')}` (Apache-2.0);")
    w("  - deberta-large-mnli (MIT) and legal-bert-base-uncased (CC BY-SA 4.0) inside RePASs.")
    w("  (Licences: `reports/private/final_push/p2/licensing_notes_v3.md`.)")
    w(f"- {C} **LLMs by phase:**")
    w("  - P3-001 smoke: gemini-3.8-flash and Groq `openai/gpt-oss-120b`;")
    w("  - P3-002: questions and genuine answers forced to Groq gpt-oss-120b after the Gemini free-tier daily quota ran out (`tables.11_llm_usage.p3002`);")
    w(f"  - P4 and the comparator: {D.get('RM:llm.p4_model')}, temperature {D.get('RM:llm.temperature')}, thinking {D.get('RM:llm.thinking')}, JSON mode, no fallback.")
    w(f"- {C} **Quota:** per project and model; the quota day resets at 12:30 IST (Pacific midnight); soft cap {D.get('RM:llm.soft_cap_per_quota_day')} per day (`config/config.yaml` `p4.soft_cap`). No second accounts.")
    w(f"- {C} **Ledger now** (`data/llm_cache/quota_ledger.json`): " + "; ".join(f"{d}: {c}" for d, c in F["ledger"].get(D.get('RM:llm.p4_model'), {}).items()) + ".")
    w(f"- {C} **Env var names only:** `GEMINI_API_KEY`, `GROQ_API_KEY` (in the gitignored `.env`).")
    w(f"- {C} **Key config keys:** `llm.p4_model`, `p4.prompt_sha256`, `p4.soft_cap`, `p4.seeds.bootstrap`, `retrieval.eval.bootstrap_resamples`, `t1.seeds`, `t4.seeds` (`config/config.yaml`).\n")

    # 6
    w("## 6. Venue\n")
    w(f"- {C} **AISIGH–SD 2026**, IEEE Bhubaneswar Section co-sponsored, submissions via CMT (`paper/aisigh/main.tex` header; `reports/private/final_push/p2/submission_checklist_v2.md`).")
    w(f"- {C} **Deadline 2026-10-10 (final).** IEEEtran two-column; 4–6 pages standard, 7–8 paid, hard maximum 8; PDF only, no supplementary file; not anonymous (author list fixed at submission).")
    w(f"- {C} **At camera-ready:** similarity under 25% including references; AI-generated content under 20% (`submission_checklist_v2.md`).")
    w(f"- {AS} **Registration and presentation requirement; camera-ready steps (PDF eXpress, IEEE copyright notice); the URL** "
      "(aisigh-sd.co.in, as given in Karan's 2026-10-02 chat message). Not recorded in a repo file; check on the venue site (§19).\n")

    # 7
    w("## 7. Data and sources\n")
    w(f"- {C} **Corpus:** {D.n(T + '.01_corpus.directions')}/{D.n(T + '.01_corpus.directions_scanned')} Directions, {D.n(T + '.01_corpus.paragraphs')} paragraphs; P1-004 recovered {D.n(T + '.01_corpus.p1004_recovered.previously_missing')} previously missing Directions.")
    w(f"  - {D.n(T + '.01_corpus.entity_classes')} entity-class headings ({D.n(T + '.01_corpus.core_entity_classes')} regulated + {D.n(T + '.01_corpus.function_headings')} function headings); {D.n(T + '.01_corpus.subject_families')} subject families.")
    w(f"  - Matrix: {D.n(T + '.01_corpus.matrix.populated_cells')} of {D.n(T + '.01_corpus.matrix.total_cells')} cells populated.")
    w("  - Defects: D2 (empty titles); amended text only.")
    w("  - IDs `md_NNNNN::pNNNNN`. (`tables.01_corpus`.)")
    for i, d in enumerate(D.get(T + ".04_supplementary.decisions")):
        k = f"{T}.04_supplementary.decisions.{i}"
        w(f"- {C} **Supplementary {d['source']}:** {D.n(k + '.clean')}/{D.n(k + '.n')} clean → `{d['decision']}` (`tables.04_supplementary`).")
    w(f"- {C} **Candidates:** rules {D.get(T + '.02_candidates.rules')}, {D.n(T + '.02_candidates.candidates_kept')} kept. **Matching:** threshold {D.get(T + '.03_matching.threshold.value')}; counterpart rate {D.wilson(T + '.03_matching.overall.counterpart_rate')}.")
    w(f"- {C} **T1:** sample {D.n(T + '.05_t1_benchmark.sample')}; validated {D.n(T + '.05_t1_benchmark.validated')}; rejected {D.n(T + '.05_t1_benchmark.rejected')}. Routes: adjudicated {D.n(T + '.05_t1_benchmark.route_counts.adjudicated')}, retest-consistent {D.n(T + '.05_t1_benchmark.route_counts.retest-consistent')}, single-pass {D.n(T + '.05_t1_benchmark.route_counts.single-pass')} (`data/benchmark/t1/t1_validated_v1.jsonl`).")
    for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        w(f"- {C} **T2 `{s}`** n = {D.n(T + f'.06_t2_retrieval.p3001.{s}.n_scored')}; bias: {D.get(T + f'.06_t2_retrieval.p3001.{s}.bias')}")
    w(f"- {C} **T3:** {D.n(T + '.08_t3.built')} built, {D.n(T + '.08_t3.scored')} scored; spot-checks {D.wilson(T + '.08_t3.precision_v1_human')} and {D.wilson(T + '.08_t3.precision_independent_post_fix')}; circular by construction.")
    w(f"- {C} **T4:** {D.n(T + '.09_t4.n_questions')} questions × four answer types; one blind rater.")
    w(f"- {C} **Schemas:** `src/schemas/`. **Guidelines v3/v3.1:** `data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md` (rules v3.1–v3.10).\n")

    # 8
    w("## 8. Work completed (chronological)\n")
    phases = [
        ("Phase 0", "reports/phase0_audit.md", "foundation and audit; 232 tests recorded in the report"),
        ("Phase 1 (Akash, Meer, Karan)", "reports/phase1_*.md", "corpus, QA, protocol, matrix; tags `p1-*-complete`, `v0.1-phase1`"),
        ("P1-004 / P1-005", "reports/p1004_audit_bundle.md", "corpus repair to the full Direction set; three-rater pilot; solo protocol; 509 tests recorded"),
        ("P2-001", "reports/p2001_candidate_extraction.md", "candidate extraction, four precision rounds"),
        ("P2-002", "reports/p2002_matching.md", "cross-class matching; threshold; 934 tests recorded"),
        ("P2-003", "reports/p2003_supplementary_sources.md", "supplementary sources; locked alignment decisions"),
        ("P2-004", "reports/p2004_t1_benchmark.md", "T1 sample, labels, retest, separate 30-item set, adjudication, gold v1; backups `t1_backups/` (outside the repo)"),
        ("P3-001", "reports/p3001_retrieval_baselines.md", "LLM client, T2 sets, retrieval and T1 baselines"),
        ("P3-002", "reports/p3002_t4_repass_audit.md", "T4 RePASs audit; backup `p3002_backups/p3002_backup_20260927T204558Z.zip` (cited in records)"),
        ("P4-001", "reports/p4001_system_and_ablations.md", "T3, the pipeline, system runs, ablations A–C, long-context"),
        ("P5-001 Part A", "reports/final/rbi_oblibench_report.md", "results bundle `reports/results_v1.json`, tables, error analysis, release package, report draft"),
        ("Final push, Phase 1", "reports/private/final_push/state_manifest_v2.md", "state audit; 1161 tests; checkpoint `final_push_backups/phase1_checkpoint_20261002T113902Z.zip`"),
        ("Final push, Phase 2 P0/P1/P2", "reports/private/final_push/karan_worklist_v4.md", "ingest/reliability/re-eval tools, corrections, drafts, figures, scanner, venue prep, paper skeleton and briefs, reference verification"),
        ("Comparator dev + freeze", "docs/protocol/reliability_plan_v2_amendments_v2.md", "two dev runs on the separate 30-item set; one bug-fix revision; frozen (`configs/comparator_v1/FROZEN.json`)"),
        ("Sealed predictions", "reports/private/final_push/phase4_input_manifest_v1.json", "rejected-17 predictions (archived, unscored)"),
        ("Phase 4 scoring (gold v1)", "reports/results_v2.json", "comparator T1 run, all systems scored, pre-registered comparisons, missed-unit definitions, retrieval/reasoning split"),
        ("Master document + paper draft", "reports/final/RBI-ObliBench_Master_Document_v2.md; paper/aisigh/main.tex", "this push's final deliverables"),
    ]
    w(table(["Phase", "Record", "What ran / outputs / notes"], [[a, f"`{b}`", f"{C} {c}"] for a, b, c in phases]))
    w(f"\n- {C} Test counts not listed above were not recorded in a repo report; the current count is `{F['pytest_summary']}`.\n")

    # 9
    w("## 9. All results\n")
    w(f"**T2 nDCG@10** (`tables.06_t2_retrieval.p3001`; class filter `p4_pipeline.*.paired`)\n")
    rows = [[k] + [D.ci(T + f".06_t2_retrieval.p3001.{s}.systems.{k}.ndcg") for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003")]
            for k in ("bm25", "dense", "hybrid_rrf", "hybrid_minus_source_class", "class_aware")]
    rows.append(["class filter ON − OFF"] + [D.ci(T + f".06_t2_retrieval.p4_pipeline.{s}.paired") for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003")])
    w(table(["System", "xclass_t1", "xclass_p2002", "supp_p2003"], rows))
    w(f"\n**T1 main table** (`phase4.t1_systems`, `phase4.comparator`)\n")
    rows = []
    for k in ("majority", "p2002_candidates", "class_blind", "class_aware", "final_agentic", "ablation_a", "long_context"):
        b = f"{P}.t1_systems.{k}"
        rows.append([k, D.n(b + ".n_items"), D.ci(b + ".flag_macro_f1"), D.ci(b + ".collapsed_macro_f1"), D.f3(f"{P}.t1_different.{k}.different_f1"), D.ci(b + ".coverage")])
    if cmp_ok:
        b = f"{P}.comparator.metrics"
        rows.append(["comparator", D.n(b + ".n_items"), D.ci(b + ".flag_macro_f1"), D.ci(b + ".collapsed_macro_f1"), D.f3(f"{P}.comparator.different.different_f1"), D.ci(b + ".coverage")])
    w(table(["System", "n", "3-way F1", "Collapsed F1", "`different` F1", "Coverage"], rows))
    w(f"\n**Paired differences** (`phase4.t1_paired`)\n")
    w(table(["Comparison", "Δ 3-way", "Δ collapsed", "Δ coverage"],
            [[k, D.ci(f"{pa}.{k}.flag_macro_f1"), D.ci(f"{pa}.{k}.collapsed_macro_f1"), D.ci(f"{pa}.{k}.coverage")] for k in D.get(pa)]))
    w(f"\n- {C} **Long-context:** 100K main ({D.n(P + '.t1_systems.long_context.n_items')} answered); the 150K run is superseded (appendix only, `reports/tables/07_t1_systems.md`).")
    w(f"- {C} **T3:** on {D.ci(T + '.08_t3.t3.on.status_exact_match')} (circular); off {D.ci(T + '.08_t3.t3.off.status_exact_match')}; ablation B {D.ci(T + '.08_t3.t3.paired.status_exact_match')}.")
    for t in ("genuine", "concatenated", "adv_negated", "adv_offtopic"):
        w(f"- {C} **T4 {t}** composite {D.ci(T + f'.09_t4.by_type.{t}.composite_score')}" + ("" if t == "genuine" else
          f"; {t} − genuine {D.ci(T + f'.09_t4.paired.{t} - genuine.composite_score')} ({D.get(T + f'.09_t4.verdicts.{t}')})"))
    w(f"- {C} **T4 correlations:** ρ faithful {D.ci(T + '.09_t4.human.all_rated.spearman_composite_score_vs_faithful')}; ρ answers_question {D.ci(T + '.09_t4.human.all_rated.spearman_composite_score_vs_answers_question')}; repair ρ {D.ci(T + '.09_t4.human.all_rated.spearman_repaired_vs_faithful')} (not usable).")
    w(f"- {C} **Ablations** (`tables.10_ablations.rows`): " + "; ".join(f"{r['ablation']} {r['measure']}: {r['on_minus_off']}" for r in D.get(T + ".10_ablations.rows")))
    w(f"- {C} **`different` analysis:** definition A {D.n(m + '.A_all_five_answered.missed')}; definition B {D.n(m + '.B_answered_only.missed')}; of {D.n(m + '.gold_different_units')} (`phase4.missed_by_every_llm_system`). "
      "Retrieval vs reasoning per system: `phase4.retrieval_vs_reasoning`. Human error categories: not done.")
    if cmp_ok:
        w(f"- {C} **Comparator dev** (separate 30-item set): judgement macro-F1 {D.f3(P + '.comparator_dev.final.judgement_macro_f1')}; `different` F1 {D.f3(P + '.comparator_dev.final.per_label.different.f1')}.")
        w(f"- {C} **Comparator T1:** `different` F1 {D.f3(P + '.comparator.different.different_f1')}, recall {D.f3(P + '.comparator.different.different_recall')}; vs class-aware: {D.ci(P + '.preregistered_comparisons.comparator − class_aware.judgement.different_f1')}; vs P2-002: {D.ci(P + '.preregistered_comparisons.comparator − p2002_candidates.judgement.different_f1')}.")
    irr = T + ".05_t1_benchmark.irr.fleiss"
    rt = T + ".05_t1_benchmark.retest.phase2.all_25"
    w(f"- {C} **Reliability (as in the master document):** the separate 30-item set (not part of the gold): class Fleiss κ {D.kappa(irr + '.per_class_judgement')}; flag {D.kappa(irr + '.differential_flag')}. rater_1 blind retest, gap {D.gap()}: flag {D.kappa(rt + '.differential_flag')} (supplementary; recall caveat).\n")

    # 10
    w("## 10. Decisions and rationale\n")
    dec = [
        ("T1 gold = single expert; reliability on a separate sample", "second raters on the gold", "rater time; the 2–3 Oct round was excluded", "2026-10-03", "Karan (`docs/prompts/FINAL-MASTER-AND-PAPER.md`)"),
        ("P2-002 threshold and the source decisions (FAQ validation-only; enforcement weak labels)", "lower thresholds; paragraph-level use", "locked rule outcomes", "2026-09-26", "rule + Karan (`tables.04_supplementary`)"),
        ("Long-context at a uniform 100K cap (150K superseded)", "finish the 150K run", "API outage; failure share", "2026-09-28", "Karan (P4 D10, `reports/p4001_system_and_ablations.md`)"),
        ("Comparator: one revision on the dev set, then frozen", "more tuning", "pre-registration; no tuning on gold", "2026-10-02", "Karan + amendment 3"),
        ("Venue AISIGH–SD 2026; 6 pages, 7-page fallback", "8 pages", "cost and focus", "2026-10-02", "Karan (`submission_checklist_v2.md`)"),
        ("Licences: MIT code, CC BY 4.0 annotations, pointer-only RBI", "redistribute text", "RBI All Rights Reserved", "2026-10-02", "Karan (`licensing_notes_v3.md`)"),
        ("Release per-rater pseudonymous ratings", "withhold", "reproducibility of κ", "2026-10-02", "Karan (`release_prep_v2.md`)"),
        ("Exclude the 2–3 Oct second-rater round and unused extensions everywhere", "use them", "see §14", "2026-10-03", "Karan (amendment 4, `docs/protocol/reliability_plan_v2_amendments_v3.md`; FINAL-MASTER-AND-PAPER scope decisions)"),
        ("Future Work order 1–11", "—", "priority for the paper", "2026-10-03", "Karan (FINAL-MASTER-AND-PAPER)"),
    ]
    w(table(["Decision", "Alternatives", "Why", "Date", "Who / record"], [[f"{C} {a}", b, c, d, e] for a, b, c, d, e in dec]) + "\n")

    # 11
    w("## 11. Constraints and rules in force\n")
    for r in ("free tiers only, with no second accounts", "one model per comparison (no provider fallback in P4)",
              "prompts frozen by sha256; no tuning on gold; pre-registration before runs (`docs/protocol/`, `configs/comparator_v1/FROZEN.json`)",
              "RBI text: excerpts of at most 25 words; pointer-only release (`src/release/check.py`)",
              "raters pseudonymised (`rater_1`–`rater_3`)", "archive, never overwrite",
              "venue rules (§6)", "authors rewrite the paper prose before submission (the `main.tex` header comment)",
              "repo-only file access; no git changes during the final push"):
        w(f"- {C} {r}.")
    w("")

    # 12
    w("## 12. Current state\n")
    w(f"- {C} **Phase:** the final deliverables (master document, paper draft and this dossier) are done; author revision is next.")
    w(f"- {C} **Gates:** `gate: comparator t1 run` was used on 2026-10-03. The rater, t1v3 and extension gates are closed or cancelled (§14).")
    w(f"- {C} **Frozen (sha256):**")
    for k, v in F["frozen_sha256"].items():
        w(f"  - `{k}`: `{v}`")
    w(f"- {C} **Ledger:** " + "; ".join(f"{d} {c}" for d, c in F["ledger"].get(D.get('RM:llm.p4_model'), {}).items()) + ".")
    w(f"- {C} **Paper:** `{F['check_paper']}`; placeholders remaining {F['paper_placeholders']} (author emails, Zenodo DOI).")
    w(f"- {C} **Master document:** `reports/final/RBI-ObliBench_Master_Document_v2.md` (+ `.docx`).\n")

    # 13
    w("## 13. File map\n")
    fm = [
        ("data/benchmark/t1/t1_validated_v1.jsonl", "T1 gold v1"), ("data/benchmark/t1/t1_candidate_benchmark_v1.jsonl", "T1 candidates"),
        ("data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md", "guidelines v3.1"), ("data/rag_runs/", "system predictions (archive)"),
        ("data/rag_runs/sealed_phase4/comparator_t1_gold_v1/", "comparator T1 predictions"), ("reports/results_v1.json", "results bundle v1"),
        ("reports/results_v2.json", "results bundle v2 (Phase 4)"), ("reports/tables/", "generated tables"),
        ("reports/final/rbi_oblibench_report.md", "P5 report draft (unchanged)"), ("reports/final/RBI-ObliBench_Master_Document_v2.md", "master document"),
        ("reports/private/final_push/", "final-push records, drafts, figures"), ("paper/aisigh/main.tex", "paper draft"),
        ("paper/aisigh/refs_verified.bib", "verified bibliography"), ("paper/aisigh/RBI-ObliBench_AISIGH_overleaf.zip", "Overleaf zip"),
        ("release/", "pointer-only release v1"), ("configs/comparator_v1/", "frozen comparator prompts"), ("configs/p4_prompts_v1/", "frozen P4 prompts"),
        ("docs/prompts/", "phase prompts"), ("docs/protocol/", "plan and amendments (private)"), ("scripts/", "runners and builders"),
        ("src/", "library code"), ("tests/", "test suite"), ("final_push_backups/", "backups (inside the repo, gitignored)"),
    ]
    rows = []
    for p_, why in fm:
        h = sha(ROOT / p_)[:16] + "…" if (ROOT / p_).is_file() and p_ in F["frozen_paths"].values() else ""
        rows.append([f"`{p_}`", why, publish_status(p_), h])
    w(table(["Path", "Purpose", "Public/private", "sha256 (frozen files)"], rows) + "\n")

    # 14
    w("## 14. Excluded data — never use\n")
    w(f"- {C} The 2026-10-02/03 second-rater (t1v2) files, and everything derived from them, are excluded from every statistic, the gold, the paper and the release (`data/benchmark/t1/t1v2_excluded/`, amendment 4 `docs/protocol/reliability_plan_v2_amendments_v3.md`).")
    w(f"- {C} Reason: the returned files could not be treated as independent ratings (the investigation record is `reports/private/final_push/integrity_flag1_investigation_v1.md`).")
    w(f"- {C} The t1v3 classmate round was not carried out; its pre-registration is archived only (`docs/protocol/reliability_plan_v2_amendments_v4.md`).")
    w(f"- {C} Phase 4X: outputs of two extension runs exist (`reports/private/final_push/extensions/ext3_t2_rerank.*`, `ext5_obliqa.*`), but per the 2026-10-03 scope decision they are not used anywhere; the other extension runs were not carried out. (See §19.)")
    w(f"- {C} This section is not copied into the master document, the paper or the release.\n")

    # 15
    w("## 15. Future Work (ranked)\n")
    fw = [
        ("Test–retest with a proper gap", "re-label after a washout of days", "the current gap is short (recall)", "low", "a retest subset (existing draw tooling)"),
        ("Second raters on all gold items", "independent ratings and adjudication", "the gold is single-expert", "high", "raters' time; blind sheets (P2-004 tooling)"),
        ("Cross-encoder reranking", "rerank before judgement", "candidate ordering", "medium", "reranker licence noted in `extensions/phase4x_step1_status_v1.md`"),
        ("Stronger (frontier) LLM run", "rerun T1 systems + comparator", "Flash-Lite-only results", "medium", "paid API; prompt-size limits (100K cap)"),
        ("ObliQA baseline", "external reference point", "positioning", "low–medium", "ObliQA has no licence: evaluation only (`phase4x_step1_status_v1.md`)"),
        ("Broad T3", "beyond deterministic cases", "circularity and size", "high", "manual temporal labels"),
        ("Bigger T4 with two raters", "more questions, two raters", "n and single rater", "medium", "rater time"),
        ("IndiaFinBench", "transfer evaluation", "generalisation", "low–medium", "CC BY 4.0 dataset (cite, don't redistribute)"),
        ("LangGraph port", "framework port", "engineering parity", "medium", "langgraph lists Python ≤ 3.13 (status file)"),
        ("Full FAQ/enforcement", "beyond the alignment samples", "source coverage", "high", "alignment work"),
        ("UI", "demo interface", "usability", "medium", "none"),
    ]
    w(table(["Rank", "Item", "What", "Why", "Effort", "Prerequisites / existing checks"], [[i + 1, *r] for i, r in enumerate(fw)]) + f"\n\n- {PL} None of these is run.\n")

    # 16
    w("## 16. Remaining steps to submission\n")
    for d, s in (("2026-10-04", "authors rewrite the prose in their own words (AI-content limit)"), ("2026-10-05", "Overleaf compile; page check (6 pages, 7-page fallback)"),
                 ("2026-10-06", "number audit: `scripts/scan_documents.py`; `scripts/check_paper.py`"), ("2026-10-07", "Zenodo deposit; replace the DOI placeholder (`phase6_checklist_v1.md`)"),
                 ("2026-10-07", "reproducibility check: tests, release_check, rehydrate on a sample"), ("2026-10-08", "similarity / AI-content check"),
                 ("2026-10-09", "final PDF via Overleaf"), ("2026-10-10", "CMT submission (deadline)"), ("after acceptance", "registration; camera-ready (PDF eXpress, copyright)")):
        w(f"- [ ] {PL} {d}: {s}.")
    w("")

    # 17
    w("## 17. How to resume\n")
    w("```bash\npython3 -m pytest -q -o addopts= -p no:cacheprovider\npython3 scripts/release_check.py --out reports/private/scratch/release_check.txt\n"
      "python3 scripts/check_paper.py\npython3 scripts/build_tables.py --check\npython3 scripts/run_phase4_scoring.py\n"
      "python3 scripts/build_paper_tables_final.py && python3 scripts/build_paper_draft.py --zip --docx\npython3 scripts/build_master_document.py\n"
      "python3 release/rehydrate.py --help\n```")
    w(f"- {C} **Gates:** Karan types a gate phrase in chat; scripts refuse without it (e.g. `run_sealed_predictions.py comparator-t1 --gate …`).")
    w(f"- {C} **New Claude chat:** paste §2, plus the sections relevant to the task, and attach this file.\n")

    # 18
    w("## 18. Prompt index\n")
    status = {"FINAL-CONTEXT-DOSSIER.md": "done (this file)", "FINAL-MASTER-AND-PAPER.md": "done", "FINAL-PHASE-2.md": "superseded (round excluded)",
              "P5-001.md": "Part A done; Part B not run", "SPRINT-PLAN.md": "superseded", "RBI-ObliBench-Master-Prompt-SOLO.md": "master plan (reference)",
              "P2-004-SPRINT.md": "done"}
    rows = []
    for p_ in sorted((ROOT / "docs/prompts").glob("*.md")):
        dt = datetime.fromtimestamp(p_.stat().st_mtime, IST).strftime("%Y-%m-%d")
        title = (p_.read_text(encoding="utf-8").splitlines() or [""])[0].lstrip("# ")[:90]
        rows.append([f"`{p_.name}`", dt, title, status.get(p_.name, "done")])
    w(table(["File", "Date", "Purpose", "Status"], rows))
    w(f"\n- {C} Referenced but not in `docs/prompts/`: FINAL-PHASE-1, FINAL-PHASE-4, FINAL-PHASE-4X (records: `state_manifest_v2.md`, `replan_phases3_4_v1.md`).\n")

    # 19
    w("## 19. Open questions / unknowns\n")
    for q in ("The faculty guide is not named in any repo record.",
              "Venue registration, presentation requirement, PDF eXpress / copyright steps and URL: from chat, not in repo files; verify on the venue site.",
              "The FINAL-CONTEXT-DOSSIER prompt says the Phase 4X runs were not carried out, but outputs of two runs exist in `extensions/`; they are unused by decision.",
              "Prompts FINAL-PHASE-1/4/4X are not in `docs/prompts/` (only referenced).",
              "Pre-2026-10-02 backups live outside the repo; under the repo-only rule they were not listed or checked here.",
              "The human error-category pass (`gate: categories done`) was not done; categories are left out of both documents."):
        w(f"- {AS} {q}")
    return "\n".join(L) + "\n"


def main() -> int:
    F = facts()
    text = build(F)
    OUT_MD.write_text(text, encoding="utf-8")
    docx = OUT_MD.with_suffix(".docx")
    subprocess.run(["pandoc", str(OUT_MD), "-o", str(docx)], check=True)
    tags = {t: text.count(t) for t in (C, PL, AS)}
    print(f"{OUT_MD.relative_to(ROOT)}: {len(text.split())} words; tags {tags}; sha256 {sha(OUT_MD)}")
    print(f"{docx.relative_to(ROOT)}: sha256 {sha(docx)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
