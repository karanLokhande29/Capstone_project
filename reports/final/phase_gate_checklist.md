# Master-prompt Phase 5 and Phase 6 gate checklist (P5-001 addendum 3)

Draft of 29 September 2026, written at the end of P5-001 Part A. It goes into `reports/final/audit_bundle.md` in Part B
(task 8), with the Part B evidence (commits, clean repo, push) added. Gate items are quoted from
`docs/prompts/RBI-ObliBench-Master-Prompt-SOLO.md`. Each is marked **met** or **not met**, with the evidence path.

## Phase 5 — Ablations + Statistics + Paper

| Gate item | Status | Evidence |
|---|---|---|
| All required experiments completed | met | T1: `reports/p4001_metrics_v1.json` (`t1`), Table 7. T2: `reports/p3001_metrics_v1.json`, Table 6. T3: Table 8. T4: `reports/p3002_metrics_v1.json`, Table 9. Protected-core baselines: BM25, dense class-blind, hybrid RRF (Table 6); majority class and long-context (Table 7). Scope-Ladder cuts are listed as limitations in report §11. |
| All ablations completed (A class filter, B temporal filter, C verifier) | met | `reports/tables/10_ablations.md`; report §9 |
| Confidence intervals generated | met | every table in `reports/tables/`; CI labels from `src/eval/ci_format.py`, checked by `tests/test_release.py::test_every_table_ci_label_follows_the_strict_rule` and `reports/p4001_ci_audit.txt` |
| Per-class analysis completed | met | T1 per source class and per label, with confusion matrices: `reports/tables/12_t1_per_class.md`. T2 per target class: `reports/p3001_retrieval_baselines.md` (per-set "Target class" tables). Classes with n < 5 would be marked insufficient n; none has n < 7. |
| Failure cases documented | met | `reports/tables/13_error_analysis.md`, `reports/final/error_analysis_v1.json`, report §8.7. It covers types (a)–(e) with counts and at least 2 examples each; (c) has one example per retention group. |
| Paper tables generated | met | `reports/tables/01_corpus.md` … `13_error_analysis.md`, `reports/results_v1.json` (`scripts/build_tables.py`, `scripts/build_error_analysis.py`) |
| Claims supported by actual results | met, pending Karan's review of the draft | every number in `reports/final/rbi_oblibench_report.md` is read from the results files by `scripts/build_report.py` |
| Required metrics — T1 Macro-F1, per-class F1, confusion structure | met | Table 7 (Macro-F1, per-label F1); Table 12 (per class, confusion) |
| Required metrics — T2 Recall@10, MAP@10, nDCG@10 | met | Table 6 |
| Required metrics — T3 exact match, supersession F1 | met | Table 8 |
| Required metrics — T4 RePASs, human faithfulness, adversarial scores | met | Table 9 |
| Week 13: methodology, results, discussion, limitations, threats to validity, paper draft | met (draft) | `reports/final/rbi_oblibench_report.md` §4–§11; `.docx` alongside |
| Week 13: plagiarism / AI-similarity checks per faculty requirements | **not met** | Karan's action after editing the draft (P5-001 Part A → Karan) |

## Phase 6 — Release + Final Demo

| Gate item | Status | Evidence |
|---|---|---|
| RBI-ObliBench benchmark | met | `release/data/t1/`, `t2/`, `t3/`, `t4/`; `release/MANIFEST.json` |
| Annotations | met | `release/data/t1/validated.jsonl`, `t4/scores.jsonl` (human ratings), T2 relevance sets; raters pseudonymised |
| Subject × Entity-Class Matrix | met | `release/data/matrix/matrix_v1.jsonl`, `matrix_v1_summary.json`; schema in `release/DATASET_CARD.md` |
| Scraper | met | `src/scraper/`; `python3 scripts/run_harvest.py all` (README) |
| Preprocessing pipeline | met | `src/extraction/`, `src/preprocessing/`; the same `run_harvest.py all` command, plus `scripts/run_matrix.py all` (README) |
| Evaluation harness | met | `src/eval/`, `src/rag/analysis.py`, `scripts/build_tables.py` (README, one command per table) |
| Dataset card | met | `release/DATASET_CARD.md` |
| Documentation | met | `README.md`, `NOTICE.md`, `release/guidelines/ANNOTATION_INSTRUCTIONS.md` |
| Reproducibility instructions | met | `README.md` (setup, lock files, rehydrate, commands); report §14 |
| Limitations | met | report §11; dataset card "Known biases" |
| RBI text not redistributed (pointers, ids, offsets, hashes) | met | `release/` holds pointers only; `scripts/rehydrate.py`: offline 76,188/76,188 matched, 26,243 derived texts rebuilt; live checks on 5 T1 items (2 Directions, 603 paragraphs) and 5 distinct Directions (1,061 paragraphs), all matched; `scripts/release_check.py` PASS (`reports/final/release_check.txt`) |
| Release on a clean public repo | **not met (Part B)** | P5-001 task 7: clean-history copy, then STOP 1 / STOP 2 |

### Final demo items → P4 demo transcripts

The transcripts are real CLI output on `gemini-3.5-flash-lite`, in `reports/p4001_system_and_ablations.md` ("CLI demo
transcripts") and `reports/p4001_metrics_v1.json` (`demo`).

| # | Final-demo item | Status | Transcript |
|---|---|---|---|
| 1 | Entity-class-specific question | met | demo 1 (Small Finance Banks), demo 3 (Payments Banks) |
| 2 | Date-specific question | met, with the stated limit | demo 2 (`--as-of 2025-12-01`, Rural Co-operative Banks, temporal filter on). The corpus holds only amended text (report §11). |
| 3 | Retrieved evidence | met | every demo prints its top 5 paragraphs after the filters |
| 4 | RBI citation | met | demos 2 and 3 cite `[md_…::p…]` paragraph ids, with Direction titles in the evidence list |
| 5 | Generated answer | met | demos 2 and 3 |
| 6 | Verifier result | met | demos 2 and 3 (`[verifier: supported]` per sentence); demo 1 (unsupported after one retry) |
| 7 | Abstention example where appropriate | met | demo 1 (the verifier abstains); demo 4 (the model says the evidence does not answer) |
| 8 | Ablation comparison | met | demo 3 vs demo 4 (the same query with the class filter on and off); full table in `reports/tables/10_ablations.md` |
| — | Review 3 live demonstration | **not met (future)** | Karan runs `scripts/demo.py` live at the viva |
