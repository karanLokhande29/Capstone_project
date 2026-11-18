# RBI-ObliBench: Generative AI Work Report

- **Project:** RBI-ObliBench (capstone), Karan Lokhande, Akash Goyal, Meer Magia, NMIMS MPSTME, Mumbai
- **Branch analysed:** `feat/auditgen-genai` (27 commits, 22 Aug – 27 Oct 2026), plus the uncommitted working tree
- **Date of this report:** 28 Oct 2026
- **Sources:** the code under `src/`, `scripts/`, `configs/`, `config/` and `ui/`, and the committed reports. Every number
  below is copied from a report or metrics file named next to it. Nothing was re-run for this report except the GenAI
  test files (§9).

---

## 1. Summary

Generative AI appears in four places in the project:

1. **A research RAG system.** It is class- and date-aware, and it answers questions about RBI Master Directions. The
   LLM is Gemini `gemini-3.5-flash-lite`. An NLI verifier checks every generated sentence, and five system variants are
   evaluated on a human-labelled benchmark.
2. **An evaluation of a GenAI metric.** This is an audit of RePASs, a faithfulness metric for LLM answers. The LLM
   (Groq `openai/gpt-oss-120b`) drafted the questions and the genuine answers. The answers were scored against concatenated
   and adversarial answers, and the scores were checked against human ratings.
3. **A structured comparator and four extensions.** The comparator is an LLM that extracts 13 fields, and a frozen rule
   gives the verdict. The extensions are a reranker, a second LLM (Groq gpt-oss-120b), the IndiaFinBench transfer test and
   a LangGraph port.
4. **Two applications.**
   - A live web demo on Azure, with a comparator API that calls Gemini.
   - AuditGen, a local compliance-audit generator. Its AI assistant tab offers 9 features, all on a local Ollama model
     (`qwen2.5:7b-instruct`). Every sentence is checked by NLI and cited.

**Headline results**

| Finding | Number | Source |
|---|---|---|
| The structured comparator is the best LLM approach on `different` | `different` F1 0.409, against 0.154 for class-aware. Comparator − class-aware: **+0.255 [+0.094, +0.411]** | Master Document v2 §9.3 |
| The best plain LLM system on the 3-way flag is class-blind | 3-way flag macro-F1 **0.602 [0.497, 0.700]** | `p4001_system_and_ablations.md` |
| The NLI verifier removes unsupported sentences, but it hurts T1 | T4 unsupported-sentence rate falls from 0.382 to 0.000. T1 3-way F1 changes by **−0.068**, coverage by −0.217 | same |
| The temporal filter gives the LLM the right date status | T3 exact match: 1.000 with the filter, 0.538 without | same |
| No LLM system beats the embedding baseline on collapsed F1 | Every CI includes 0 | same |
| Every LLM system misses `different` | 56 of 78 gold `different` units are missed by every LLM system | `tables/13_error_analysis.md` |
| RePASs can be gamed by concatenation on RBI text | Concatenated − genuine: **+0.375 [+0.325, +0.427]** | `p3002_t4_repass_audit.md` |
| Transfer to IndiaFinBench | 0.757 [0.703, 0.805] accuracy, on a 268-item prefix | `ext8_indiafinbench.md` |
| The LangGraph port matches the original | 4 systems × 106 items give byte-identical prompts and outputs: PASS | `ext9_langgraph.md` |

Total hosted LLM calls recorded in Table 11 are 866, all on free tiers. The extension runs add about 700 more (§8).

---

## 2. Where GenAI sits in the pipeline

```
 Phase 1–2 (no LLM)                        Phase 3–4 (GenAI)                          Applications
 ───────────────────                       ─────────────────                          ────────────
 381 Directions, 76,188 paragraphs  ─┐     LLM client (Gemini, Groq fallback)     ┌─> CLI demo (scripts/demo.py)
 Entity-class × subject matrix       │     ├─ P4 RAG pipeline (5 systems)          ├─> Live web demo + comparator API (Azure)
 Obligation candidates (rules)       ├──>  ├─ Long-context baseline (100K)    ────┤
 Cross-class matching (bge)          │     ├─ Structured comparator (13 fields)   └─> AuditGen AI assistant (local Ollama)
 Human gold labels (T1, T3, T4)     ─┘     ├─ T4 RePASs audit (LLM Q&A)
                                           └─ Extensions #3 #4 #8 #9
                         Local NLI verifier: cross-encoder/nli-deberta-v3-xsmall
```

Phases 1 and 2 made no LLM calls (Table 11). The human gold labels were kept apart from AI output by design (§7.1).

---

## 3. GenAI infrastructure

### 3.1 Provider-agnostic LLM client: `src/llm/client.py` (810 lines)

| Feature | What it does |
|---|---|
| Providers | Gemini is the primary (REST `v1beta`). Groq is the fallback (OpenAI-compatible). There is no SDK lock-in. |
| Determinism | Temperature 0. A disk cache is keyed on sha256(provider, model, messages, params), so a rerun replays from the cache. |
| Quota safety | A client-side RPM/TPM throttle. Exponential back-off on 429 and 5xx. A hard per-run call cap (`llm.max_calls`). A daily `QuotaLedger` with a soft cap of 480 per quota day (Pacific). `QuotaPaused` checkpoints and resumes after the reset. |
| No mixed providers | A run locks to the first provider that answers. A mid-run quota hit raises `ProviderSwitchMidRun`, and the whole system is rerun on the fallback, so answers from two models are never mixed. |
| Key hygiene | Keys come from a gitignored `.env`. They travel in headers, never in URLs. Every provider error is redacted. Errors name only the variable (`GEMINI_API_KEY missing/empty`). |
| Cache-only mode | `CacheMiss` lets a script replay with no key and no network. The LangGraph equivalence test and the AuditGen tests use this. |

### 3.2 Model selection and smoke test: `scripts/run_llm_setup.py`

- The script lists the live models and picks the model by a rule written in the code. The rule is: the newest Gemini
  `flash` tier, stable ids preferred, and for the fallback the Groq model with the largest context window.
- Its first pick (27 Sep) was `gemini-3.8-flash`, with `openai/gpt-oss-120b` as the fallback
  (`reports/p3001_llm_models_v1.json`).
- `gemini-3.8-flash` allows only 20 free-tier requests per day. So P4 and every later system ran on
  `gemini-3.5-flash-lite` (thinking level `minimal`).
- The smoke test made one call per provider; both passed.

### 3.3 Frozen prompts: `configs/p4_prompts_v1/`

There are eight prompt files: the T1 judgement, the answer, the T3 temporal status and the long-context comparison,
each with a system and a user file.

- Every prompt asks for **JSON only**.
- Citations must use the form `md_NNNNN::pNNNNN`, and the model must answer from the evidence only.
- Their sha256 hashes are frozen in config. `Prompts` (`src/rag/pipeline.py`) refuses to run if any file has changed
  ("Stop and ask Karan before changing a prompt").
- The comparator's prompts and rule are frozen in the same way, in `configs/comparator_v1/FROZEN.json` (2 Oct 2026),
  before any T1 run.

---

## 4. The research RAG system (P4-001): `src/rag/pipeline.py`

### 4.1 Pipeline

1. **Retrieve.** Hybrid reciprocal-rank fusion (BM25 + `bge-base-en-v1.5`, k = 60) returns the top 20. The query's own
   source paragraph is excluded.
2. **Class filter.** It keeps paragraphs of the asker's entity class, plus function-heading Directions of the same
   subject family.
3. **Temporal filter.** It drops paragraphs deleted as of the question's date. It attaches the amendment text to amended
   paragraphs, and it marks paragraphs whose amendment takes effect later. The amendment events come from the T3 parser.
4. **Generate.** The LLM answers from the top 5 paragraphs and cites ids, in JSON.
5. **Verify.** `cross-encoder/nli-deberta-v3-xsmall`, at a pinned revision, checks each sentence against the
   paragraph(s) it cites. If a sentence is unsupported, the pipeline re-retrieves once and makes one more answer call.
   If a sentence is still unsupported, it abstains ("cannot answer reliably").

### 4.2 Systems evaluated (T1: 106 items, 412 class judgements)

| System | Class filter | Verifier |
|---|---|---|
| Class-blind LLM | off | off |
| Class-aware LLM | on | off |
| Final agentic | on | on |
| Class-blind + verifier (ablation A) | off | on |
| Long-context LLM | no retrieval; whole Directions up to a 100K-token cap | off |
| Structured comparator | the 2 candidate paragraphs per class; 13 fields; a frozen rule decides | n/a |

Baselines without an LLM: a majority-class baseline (in-sample) and the P2-002 embedding candidates.

### 4.3 Results

T1 results come from the Master Document v2 §9.2 and `p4001_system_and_ablations.md`. The bracketed ranges are bootstrap
95% CIs from 2,000 resamples.

| System | n | 3-way flag F1 | Collapsed F1 | Judgement F1 | `different` F1 | Coverage |
|---|---|---|---|---|---|---|
| Majority (in-sample) | 106 | 0.219 | 0.465 | 0.227 | 0.000 | 1.000 |
| P2-002 candidates (no LLM) | 106 | 0.459 | 0.784 | 0.550 | 0.000 | 1.000 |
| Class-blind LLM | 106 | **0.602** | 0.766 | 0.664 | 0.321 | 1.000 |
| Class-aware LLM | 106 | 0.551 | 0.808 | 0.609 | 0.154 | 0.991 |
| Final agentic | 106 | 0.483 | 0.710 | 0.521 | 0.047 | 0.774 |
| Class-blind + verifier | 106 | 0.532 | 0.695 | 0.578 | 0.176 | 0.792 |
| Long-context (100K) | 102 | 0.509 | 0.819 | 0.551 | 0.074 | 1.000 |
| **Structured comparator** | 106 | 0.616* | **0.838*** | **0.680** | **0.409** | 1.000 |

\* The comparator's flag is derived from its judgements by rule v3.6.

**Ablations** (ON − OFF, same items):

| Ablation | Measure | Δ [95% CI] | Reading |
|---|---|---|---|
| A: class filter | T2 nDCG@10, `t2_xclass_t1` (n = 291) | +0.451 [+0.421, +0.481] | Large retrieval gain. Part of it is built in, because relevance was labelled only for the target class. |
| A: class filter | T1 3-way F1 (no verifier) | −0.050 [−0.133, +0.027] | No significant effect on judgement |
| B: temporal filter | T3 status exact match (n = 52) | +0.462 [+0.327, +0.596] | The LLM uses the date information it is given |
| C: verifier | T4 unsupported-sentence rate (n = 28) | −0.382 [−0.552, −0.214] | Mostly abstention, plus 0 by construction |
| C: verifier | T4 abstention rate | +0.393 [+0.214, +0.571] | The cost of the drop above |
| C: verifier | T1 3-way F1 | −0.068 [−0.132, −0.012] | Hurts. It abstained on 59 judgements that were correct on the first pass. |

**Demo CLI** (`scripts/demo.py`). It prints the answer or an abstention, the cited paragraphs, the filters applied, the
verifier verdicts and the LLM calls used. A date-specific query (Form B return, Rural Co-operative Banks, as of
2025-12-01) was answered with two verified, cited sentences. A Small Finance Bank query abstained after one retry.
Both transcripts are in the P4 report.

---

## 5. Evaluating a GenAI metric: the T4 RePASs audit (P3-002)

- **Question (RQ3).** Can RePASs, a faithfulness metric for LLM answers, be gamed on Indian regulatory text?
- **GenAI use.**
  - The LLM drafted 30 questions from obligation paragraphs, stratified over 11 classes and 23 subject families.
  - The LLM wrote genuine answers from the passages only, with citations.
  - Both steps ran on Groq `gpt-oss-120b`. Gemini's quota ran out after 7 questions, and those 7 were discarded, not
    mixed in.
- **Answer types compared:**
  - genuine, from the LLM;
  - concatenated: verbatim obligation sentences, no LLM;
  - negated: the concatenated answer with its obligations flipped and its numbers doubled;
  - off-topic.
- **RePASs setup.** Upstream code, unmodified, at a pinned commit, in its own venv. Its LegalBERT obligation classifier
  was retrained locally (validation F1 0.995).

| Answer type | RePASs |
|---|---|
| Genuine (LLM) | 0.371 [0.311, 0.431] |
| Concatenated | **0.746** [0.692, 0.796] |
| Negated | 0.049 |
| Off-topic | 0.229 |

**Findings**

- **Concatenation gameability reproduces:** +0.375 [+0.325, +0.427]. The verdict rule was fixed before scoring.
- Negated and off-topic answers do **not** fool RePASs.
- RePASs tracks human faithfulness (ρ = 0.731). It does not track whether the answer addresses the question
  (ρ = 0.008).
- The exploratory repair (an overlap penalty) ranks genuine answers above concatenated ones. But it destroys the link to
  human faithfulness (ρ = −0.126), so the report says plainly that it is not a usable repair.

---

## 6. Extensions and the comparator

| Extension | What was tested | Result | Source |
|---|---|---|---|
| **Structured comparator** (`src/rag/comparator.py`, `comparator_rule.py`) | One call per (item, class) pair. The LLM extracts 13 fields per side (actor, action, threshold, deadline, exception and others) and marks each field equal, different or one-sided. A fixed rule gives same / different / none. It was developed on a separate 30-item IRR set and frozen by sha256 before T1. | `different` recall 0.487, precision 0.352. Against class-aware: judgement F1 +0.071 [+0.001, +0.142], `different` F1 +0.255 [+0.094, +0.411]. | Master Doc v2 §9.3, §9.9 |
| **#3 Cross-encoder reranking** (`ms-marco-MiniLM-L6-v2`) | Rerank the hybrid top 20 before the per-class cut | Class-blind 3-way F1 changes by **−0.064** [−0.115, −0.017], and `different` recall by −0.077. **Reranking hurts.** | `ext3_t1_rerank.md` |
| **#4 Larger open model** (Groq `gpt-oss-120b`, class-blind T1) | The same frozen prompt on 103 feasible items | 3-way F1 0.614, tied with Gemini (−0.010 [−0.094, +0.084]). Collapsed F1 +0.055 [+0.012, +0.112], **better**. `different` F1 0.289, no better. | `ext4_groq.json` |
| **#8 IndiaFinBench transfer** | The frozen answer prompt, scored with the dataset card's rules (no LLM judge) | 0.757 overall (n = 268 of 406). Regulatory interpretation 0.951; numerical reasoning 0.561 (the weakest). | `ext8_indiafinbench.md` |
| **#9 LangGraph port** (`src/rag/graph_t1.py`) | The pipeline rebuilt as graph nodes (evidence → generate → verify → retry → finalize), replayed from the cache only | 4 systems × 106 items: byte-identical prompts and identical outputs. **PASS**, with 0 API calls. | `ext9_langgraph.md` |
| **Sealed predictions** (`scripts/run_sealed_predictions.py`) | Predictions on the 17 rejected items and the comparator's 412 T1 pairs were written, hashed and sealed before any scoring | A manifest with sha256 per file | script |

---

## 7. Responsible-AI and integrity controls

The project went beyond calling an LLM. These controls are enforced in code, not left as notes.

### 7.1 Human labels kept apart from AI output (the AI-label firewall)

- Each rater has a `label_source` of `manual` or `ai_assisted` (`src/benchmark/annotation.py`).
- Any rater recorded as `ai_assisted` is excluded from every human agreement statistic, and reported only as a human-AI
  diagnostic.
- The applicability column was byte-identical across the three raters' pilot files. It had been filled once, by hand,
  and given to the other two raters. The code detects that pattern (`judgment_column_independence()`) and suppresses
  the agreement figure that would have read 1.0 by construction.
- LLM outputs are always "system outputs, never labels" (Master Doc v2).

### 7.2 Pre-registration and freezes

- Prompts, comparator prompts and the comparator rule are hash-frozen before evaluation.
- Verdict rules (T4) and run orders (#4, #8) are pre-registered.
- Sealed predictions are hashed before any gold comparison.
- Deviations are logged as decisions, for example D10–D12 for the long-context cap and the outage handling, including the
  fact that Claude had already seen some interim numbers.

### 7.3 Hallucination controls

- **Cite or drop.** Every generated sentence must cite a paragraph id and pass NLI entailment against it (P4 and
  AuditGen).
- **Numbers check** (AuditGen). A sentence with a number that is not in its evidence is unsupported.
- **Quote check.** Quoted "key quotes" and calendar phrases must occur verbatim in the source paragraph.
- **Abstention** instead of an unverified answer.

### 7.4 Privacy and security (AuditGen)

- **Local model only.** `LocalLLM` refuses any host that is not 127.0.0.1, ::1 or localhost before it sends a request.
  Tests mock non-loopback sockets so that any such call raises.
- **No text in logs.** `activity.jsonl` stores the feature, the model, timings and sha256 hashes only, never the
  question, the prompt or the answer.
- **AI never decides.** Output is labelled "AI draft, needs review", and a review suggestion never changes a row by
  itself.
- **Research-integrity guard** (`src/auditgen/guard.py`). It hashes every research artefact so that AuditGen can be shown
  not to have changed any of them.
- The live demo's Gemini key lives only in the Azure Function's app settings, and is never written to a file.

### 7.5 Reproducibility

- Temperature 0, a response cache, pinned model revisions, frozen prompts and seeded bootstraps.
- `results_v2.json` and `build_tables.py` regenerate every table.
- The release ships pointers only, with no RBI text, plus a rehydrate script.

---

## 8. LLM usage and cost

Table 11 (`reports/tables/11_llm_usage.md`):

| Phase | Model | Calls |
|---|---|---|
| P3-001 smoke tests | gemini-3.8-flash, gpt-oss-120b | 2 |
| P3-002 questions (discarded, quota) | gemini-3.8-flash | 7 |
| P3-002 questions and genuine answers | gpt-oss-120b (Groq) | 60 |
| P4, all systems (2 quota days) | gemini-3.5-flash-lite | 797 |
| **Total in Table 11** | | **866** |

Later runs, counted from their own reports:

| Run | Calls |
|---|---|
| #3 rerank | 212 Gemini |
| #4 | 103 Groq |
| #8 | 268 items, one Gemini call each |
| Comparator | 412 T1 pairs, plus dev and rejected items |
| AuditGen | 38 logged calls on the local `qwen2.5:7b-instruct`, at no cost |

Everything ran on **free tiers**. An HTTP 503 outage on 28–29 Sep was handled by pausing and resuming, with no model
switch.

---

## 9. AuditGen AI assistant (latest work, commit `910fd75`, 27 Oct)

| # | Feature | What the LLM does | Check |
|---|---|---|---|
| 1 | Ask the pack | Cited answer over the pack's obligations (bge + BM25 → RRF → top 6) | NLI per sentence, one retry, abstain |
| 2 | Explain obligation | Plain-language summary, who must act, the actions, the deadline | NLI, plus the key quote must occur in the paragraph |
| 3 | Draft policy clause | A clause that would satisfy the obligation | Scored by the gap analyser's covered / partial / missing rule; new numbers flagged |
| 4 | Review suggestion | Confirm / dispute / not applicable, with a reason | The reason must pass NLI. A human must click "I agree". |
| 5 | Change explainer | What an amendment changed, and its impact | NLI against the old text plus the amendment |
| 6 | Executive memo (DOCX) | A memo built from numbered pack facts | Every number must appear in the cited facts |
| 7 | Action plan | Prioritised actions | Each action must point to a deadline, change or gap row |
| 8 | Calendar check | Re-extracts the deadline or frequency as JSON | The quote must occur in the paragraph; agreement with the rule extractor is reported |
| 9 | Differential 2nd opinion | Field-level comparison of a matched pair | Decided by the frozen comparator rule |

The model runtime is Ollama 0.40.4, with `qwen2.5:7b-instruct` (fallback `1.5b`), temperature 0 and a fixed seed.

**What else was built**

- A FastAPI backend (`/api/auditgen/ai/*`).
- A React tab (`/auditgen/ai`), with offline replay of recorded outputs.
- CLI commands: `ai-status`, `ask` and `ai-samples`.

**Measured speed** (Apple M5, 16 GB)

| Feature | Time |
|---|---|
| Ask | 2–8 s |
| Memo | ~25 s |
| Action plan | ~100 s |
| Differential | 25–80 s per pair |

**Recorded samples.** 3 of 6 questions were answered with verified, cited sentences, and 3 abstained.

**Tests.** At the commit, 1,263 Python tests and 115 UI tests passed; 14 of the Python tests are new GenAI tests.

**Tests re-run for this report.** The 8 GenAI-related test files (`test_auditgen_genai`, `test_comparator`,
`test_llm_client`, `test_p4_pipeline`, `test_p4_analysis`, `test_t4_audit`, `test_t4_analysis`,
`test_indiafinbench_scoring`) ran **117 tests, all passed**. They make no network calls and use no keys.

---

## 10. Critical analysis

### What worked

- **The comparator is the one GenAI idea that clearly helped.** Splitting the comparison into explicit fields (LLM
  extraction plus a deterministic rule) raised `different` F1 from 0.154 to 0.409. Free-form judgement could not do this
  with any model, filter or context size.
- **Grounding the LLM in structured metadata works.** The temporal filter turned T3 from 0.538 into 1.000. The LLM uses
  date status well when it is given that status explicitly. (The T3 gold comes from the same parser, so this measures
  whether the LLM uses the information, not whether the parser is right.)
- **Engineering rigour.** The project has caching, quota ledgers, frozen prompts, sealed predictions, a reproducible
  LangGraph port and the AI-label firewall. Few student LLM projects have these, and they make every number auditable.
- **Honest negative results.** The verifier hurts T1, reranking hurts, and the RePASs repair fails. The project reports
  all three with CIs instead of hiding them.

### What did not work, or is weak

- **`different` remains unsolved.** 56 of 78 gold `different` units are missed by every LLM system. The error analysis
  shows the gold paragraph was usually in context, so this is a reasoning failure, not a retrieval failure.
- **The NLI verifier is too strict for this domain.** It is a small model (xsmall). It rejects correct paraphrases: 59
  correct first-pass judgements turned into abstentions. The same model is also inside RePASs, so the verifier and the
  metric are not independent.
- **LLMs give no clear gain over embeddings on the fair metric.** No LLM system beats the P2-002 candidates on collapsed
  F1.
- **Model scale.** Every main result is on a free Flash-Lite-class model. The one larger-model run (#4, gpt-oss-120b)
  was no better on `different`. A frontier model was not tested (budget).
- **Small n.** The test sets are small (T1 106 items, T4 30 questions, T3 52 items), so many CIs are wide. The T1 gold
  comes from a single expert.
- **AuditGen's AI outputs have not been evaluated against gold labels.** They are demonstrated and tested for safety
  properties, not measured for accuracy.

---

## 11. Recommended next steps

1. Run the T1 systems and the comparator on a frontier model, to test whether the `different` failure shrinks with
   scale. The Master Document lists this as future work.
2. Replace the whole-paragraph NLI premise with a stronger or domain-tuned entailment model, or with the comparator's
   field-level check. Re-measure the abstention cost.
3. Add bootstrap CIs for `different` F1. This is listed as a follow-up in Master Document v2.
4. Build a small gold set for AuditGen's Ask and Explain features (for example 30 questions), so the assistant has
   measured accuracy and not only safety guarantees.
5. Finish IndiaFinBench: 138 of 406 items are still to run.
6. Commit the remaining working-tree files: the paper, `submissions/capstone/`, `release/` and the reports.

---

## 12. File index (GenAI)

| Area | Files |
|---|---|
| LLM client | `src/llm/client.py`, `scripts/run_llm_setup.py`, `.env.example` |
| RAG pipeline | `src/rag/pipeline.py`, `src/rag/analysis.py`, `src/rag/p4_report.py`, `scripts/run_p4.py`, `scripts/demo.py`, `configs/p4_prompts_v1/` |
| Comparator | `src/rag/comparator.py`, `src/rag/comparator_rule.py`, `scripts/run_comparator.py`, `configs/comparator_v1/` |
| T4 RePASs audit | `src/t4/`, `scripts/run_t4.py`, `scripts/run_repass.py`, `reports/p3002_t4_repass_audit.md` |
| Extensions | `scripts/run_ext3_t1_rerank.py`, `run_ext4_groq.py`, `run_ext8_indiafinbench.py`, `run_langgraph_equivalence.py`, `src/rag/graph_t1.py`, `src/eval/indiafinbench.py` |
| Integrity | `src/benchmark/annotation.py` (label firewall), `scripts/run_sealed_predictions.py`, `src/auditgen/guard.py` |
| AuditGen AI | `src/auditgen/genai.py`, `ai_features.py`, `summary_llm.py`, `api.py`, `config/auditgen_genai_v1.yaml`, `docs/AUDITGEN_README.md`, `ui/src/features/auditgen/` |
| Live demo | `ui/README.md`, `ui/api/` (comparator API, Azure Function) |
| Results | `reports/p4001_system_and_ablations.md`, `reports/final/RBI-ObliBench_Master_Document_v2.md`, `reports/results_v2.json`, `reports/tables/` |
| Tests | `tests/test_llm_client.py`, `test_p4_pipeline.py`, `test_p4_analysis.py`, `test_comparator.py`, `test_t4_*.py`, `test_indiafinbench_scoring.py`, `test_auditgen_genai.py` |
