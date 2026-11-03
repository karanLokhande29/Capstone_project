# Space budget: AISIGH-SD 2026 (IEEEtran two-column)

**Decision (2 Oct):** draft to **6 pages**; the 7-page variant is the fallback (a paid 7th page is approved if needed). The final call comes after the first full draft. The 8-page column below is the upper bound, not the plan.

Assumptions:
- about 880 words per full page of text (10 pt, two columns);
- floats as estimated below;
- 6 pages = standard; 7–8 = paid over-length; hard maximum 8;
- PDF only (no supplementary file): anything not in the PDF goes to the benchmark release docs.

**Text budget:** 3120 words (6-page) / 4840 words (8-page).
**Floats and references (6-page):** ≈ 2.01 pages → text space ≈ 3511 words.
**8-page:** + Fig. 3 (0.3 p), + LC same-items or confusion (0.25 p) → text space ≈ 4787 words.

| Report section | 6 pages | 8 pages (paid) | Brief / destination |
|---|---|---|---|
| 1 Abstract | main | main | 00_abstract |
| 2 Introduction and RQs | main | main | 01_intro |
| 3 Related work | main (short) | main | 02_related |
| 4 Corpus and matrix | main (merged with 5) | main | 03_corpus |
| 4 Matrix figure (57 families × 19 classes) | release-only | release-only (illegible at column width) | release docs |
| 5 T1 construction | main | main | 03_corpus |
| 5 Reliability (separate 30-item set, P2-004 retest, t1v3 if completed, excluded-round disclosure) | main | main | 04_annotation |
| 5 P2-004 retest, timed re-label, pilot κ | release-only (one sentence in main) | pages 7–8 | 04_annotation |
| 5 Candidate-label agreement by band | release-only | release-only | release docs |
| 6 Tasks and metrics | main | main | 05_tasks |
| 7 Systems (Fig. 3 architecture) | main text; Fig. 3 dropped | pages 7–8 (Fig. 3) | 05_tasks |
| 8.1 RQ1 / T2 table | main | main | 06_results |
| 8.2 RQ2 / T1 systems table | main | main | 06_results |
| 8.2 full paired-difference table (14 rows) | release-only | release-only | release docs |
| 8.3 Verifier | main (2 sentences) | main | 06_results |
| 8.4 Long-context same-items table | release-only (1 sentence) | pages 7–8 | 06_results |
| 8.4 150K appendix (superseded) | release-only | release-only | release docs |
| 8.5 T4 (RePASs audit) | main | main | 06_results |
| 8.5 T4 repair (exploratory) | 1 sentence | pages 7–8 (short) | 06_results |
| 8.5 T4 three-rater (T4v3, if completed) | 1 row in tab:t3t4 | main | 06_results |
| 8.6 T3 | main (short) | main | 06_results |
| 8.6 T3 parser appendix | release-only | release-only | release docs |
| 8.7 Error analysis (a)–(e) with examples | release-only (counts in 07) | pages 7–8 (two examples ≤ 25 words) | 07_comparator |
| Targeted experiment (comparator) | main | main | 07_comparator |
| 9 Ablations | rows in tab:t3t4 | main | 06_results |
| 10 Discussion | main (short) | main | 08_discussion |
| 11 Limitations | main | main | 09_limitations |
| 12 Ethics and IPR | main (short) | main | 10_ethics |
| 13 AI-use statement | acknowledgment | acknowledgment | 11_ai_use_ack |
| 14 Reproducibility (commands) | drop (1 sentence + repo URL) | drop | release README |
| Per-class results (Table 12) | release-only | release-only | release docs |
| Confusion matrices | release-only | pages 7–8 (one, class-aware vs gold) | release docs |
| LLM usage / quota table (Table 11) | release-only | release-only | release docs |
| P2-003 supplementary sources (FAQ / enforcement) | drop (1 clause) | release-only | release docs |
| Candidate precision rounds (P2-001) | release-only | release-only | release docs |

## Floats (6-page)

| Float | pages |
|---|---|
| tab:benchmark | 0.15 |
| fig:construction (1 col) | 0.18 |
| fig:provenance (2 col) | 0.3 |
| tab:reliability (2 col) | 0.2 |
| tab:t2 (2 col) | 0.18 |
| tab:t1 (2 col) | 0.3 |
| tab:t3t4 | 0.3 |
| references (10) | 0.4 |

## Cannot fit

- **6 pages:** Fig. 3 architecture; LC same-items table; full paired table; per-class table; confusion matrices; error-analysis examples; P2-004 retest/timed/pilot details; T3 parser appendix; 150K appendix; matrix figure.
- **8 pages:** the matrix figure (57 × 19, illegible); full 14-row paired table; per-class table (11 × 7); 150K appendix; T3 parser appendix; candidate precision rounds; LLM usage table. These go to the release docs.
