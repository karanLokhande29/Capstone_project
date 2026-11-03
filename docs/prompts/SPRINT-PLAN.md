# RBI-ObliBench — 4-day sprint to 30 Sep 2026

**Decided 2026-09-26 (Karan):**
- Everything is due 2026-09-30: a **code + benchmark release** and the **final report / paper**. No live demo or slides are due, but a small command-line demo ships in the repo (protected core).
- Karan has 8+ h/day. Akash and Meer each label ~30 items by 29 Sep.
- LLM access: an OpenAI, Gemini or Groq key. Code is provider-agnostic; the provider is picked by whichever env var is set.
- Compute is local on the Mac. No GPU is needed anywhere in this plan.

## What stays, what is cut (Scope Ladder applied in order, every cut listed in the report)

| Item | Sprint version |
|---|---|
| Corpus + matrix | done (P1) |
| T1 validated set + reliability | **123 items across all 11 core classes** (the full P2-004 size), pass 1 on Sun + Mon. Second-rater κ from Akash + Meer (30 items); pilot test-retest on 30 Sep (18 items). Phase-2 retest subset drawn and sheet date-locked, but the retest itself can't run before 3 Oct (5-day rule), so it is **NOT YET MEASURED** by the deadline |
| T4 RePASs audit | 30 questions × 3 answer types (genuine / concatenated / adversarial); human faithfulness on 30 answers (Scope Ladder 5) |
| Baselines | BM25, dense class-blind, hybrid RRF, class-aware (T2); majority-class and long-context LLM (T1) |
| T3 | deterministic items from Amendment Directions only (Scope Ladder 6) |
| Agentic RAG | plain Python pipeline: retrieve → class filter → temporal filter → answer with citations → NLI verifier/abstain (Scope Ladder 2: no LangGraph, no cross-encoder reranking) |
| Ablations A–C | class filter, temporal filter, verifier, each ON vs OFF, with bootstrap 95% CIs |
| IndiaFinBench, ObliQA baselines | cut (Scope Ladder 1, 3) |
| FAQ / enforcement | already at minimum (P2-003) |
| Release | benchmark (pointer + offset, no RBI text: R6/D9 still open) + code + dataset card; no UI (Scope Ladder 7) |

**Honesty rules that don't bend:** no AI labels as human labels; no Fleiss' κ unless 3 real raters labelled the same items; every metric with n and a CI; small n stated plainly; a long-context LLM win is reported if it happens.

## Prompts (run in Claude Code, in order, from `docs/prompts/`)

| Prompt | What | Karan's time |
|---|---|---|
| **P2-004 + P2-004-SPRINT** | T1 candidate benchmark, 123-item sample, sheets for Karan / Akash / Meer, then κ, adjudication, validated set | ~7.5 h labelling (Sun + Mon), 1 h adjudication, 1 h pilot retest |
| **P3-001** | LLM client; T2 qrels from existing human labels; BM25, dense, hybrid, class-aware; majority-class T1 | ~0.5 h |
| **P3-002** | T4 RePASs audit | ~1.5 h (faithfulness ratings) |
| **P4-001** | T3 deterministic set, agentic RAG, long-context baseline, T1/T2/T3 system runs, ablations A–C, CLI demo | ~0.5 h (T3 spot-check) |
| **P5-001** | Statistics, tables, report/paper draft, dataset card, release package, final audit bundle | ~3 h (reading and editing the draft) |

## Day by day

| Day | Claude Code | Karan |
|---|---|---|
| **Sat 26 (tonight)** | P2-004 Part A (sprint sizing) → sheets | Send Akash and Meer their blank files and the guidelines tonight |
| **Sun 27** | P3-001 (baselines), then P3-002 Part A (T4 answers + RePASs) | Label T1 pass 1, first ~70 items (in blocks, minutes logged); `checkpoint` after block 1 |
| **Mon 28** | P4-001 Part A build; P2-004 Part C (ingest pass 1) at night | Review 2; finish T1 pass 1 (~50 items); T4 faithfulness ratings (~1.5 h) |
| **Tue 29** | P2-004 Part D (κ, adjudication list); P4-001 runs + ablations | Collect Akash and Meer's files by noon; adjudicate (~1 h); T3 spot-check (15 min) |
| **Wed 30** | Pilot retest ingest; P5-001 (stats, report, release) | Pilot retest (18 items, ~1 h, allowed from 30 Sep); read and edit the report; release |

If something slips, cut in this order: T4 human-faithfulness n (30 → 15); T3 size; the demo polish. **Never** skip T1 human labels or the CIs.

## Git
The release needs the code on GitHub, so git gets used on 30 Sep (P5-001). The D9 question is still open: the public repo's history holds 381 RBI PDFs. Ask your guide whether the history must be purged before the release is made public. P5-001 prepares both options.
