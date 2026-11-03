# RBI-ObliBench: the complete project, explained simply

Group 10 · Akash Goyal, Karan Lokhande, Meer Magia · Mentor: Prof. Jish Elizabeth Joy · Co-author: Dr. Hima Deepthi Vankayalapati

This document explains the whole project in plain language: the problem, the data, how it was labelled, how a question
flows from input to output, every model and LLM we used, the tech stack, how the website talks to the backend, why the
project is a benchmark, why we made each big decision, rough time complexity, every number in the presentation, and the
questions the panel is likely to ask. Every number here comes from our results file (`reports/results_v2.json`), the
paper report, or the project data.

## 1. The project in one paragraph

The Reserve Bank of India (RBI) writes a separate Master Direction for each kind of regulated entity: commercial banks,
small finance banks, NBFCs, co-operative banks and so on. The same subject (say, outsourcing or KYC) therefore appears in
several near-parallel Directions, and the duty usually matches, but sometimes it quietly differs: a different approving
body, threshold, deadline or scope, or no counterpart at all. We built **RBI-ObliBench**, a benchmark that measures
whether AI systems can find these cross-class differences, tested five LLM systems and a new structured comparator on
it, audited a popular answer-quality metric, and turned the pipeline into a working **audit generator** product with an
AI assistant, live on the web.

## 2. The problem statement

**In simple words:** if a group owns a bank and an NBFC, can a system tell them, rule by rule, whether the same duty
applies to both, and where it differs?

**Formally:** for an obligation in one entity class's Master Direction, decide for every other class whether a
counterpart exists and whether it imposes the *same* or a *different* requirement; retrieve that counterpart; tell
whether a paragraph is in force on a given date; and test whether the usual faithfulness metric can be gamed on Indian
regulatory text.

**Why it matters:** a false "different" wastes review time; a missed "different" can leave an entity non-compliant, and
RBI publishes monetary-penalty press releases for breaches (for example, a ₹65 lakh penalty on a small finance bank in
January 2025, which is in our enforcement data).

**Research questions**

| RQ | Plain question | Short answer |
|---|---|---|
| RQ1 Applicability | Does telling the system the entity class help? | Yes for finding the right paragraph, no for judging it |
| RQ2 Differential obligation | Can LLMs tell *same* from *different*? | Not yet: they miss most real differences |
| RQ3 Metric integrity | Can the standard faithfulness metric (RePASs) be fooled? | Yes: copying the regulation scores higher than a real answer |

## 3. "RBI has about 240 Master Directions, so how do we have 381?"

Both numbers are right; they count different things.

- In late 2025 RBI consolidated its instructions into a new series of entity-class Directions titled "…Directions,
  2025". Our corpus has **244** of those; that is almost certainly the "about 240" you have heard.
- RBI's **Master Directions listing page** contains more than that series. When we harvested it (August–September
  2026) it also listed:
  - **87** newer "…Directions, 2026" documents issued after the consolidation;
  - **39** older documents titled "Master Direction – …", mostly under function headings such as Foreign Exchange
    Management, Financial Market and payment systems;
  - **11** others (for example licensing guidelines and a few older Directions, such as Prevention of Market Abuse, 2019).
- 244 + 87 + 39 + 11 = **381**, every one a separate PDF with its own URL (381 unique URLs). The listing is organised
  under **19 headings**: our **11 regulated-entity classes** (312 documents) plus **8 function headings** (69 documents).
- An early download run missed 81 of them (the server returned HTML instead of PDFs); we found and repaired that, and
  every later step used the full 381.

**One-line answer for the panel:** "About 240 is RBI's 2025 consolidated series; we took everything on RBI's Master
Directions page at harvest time, which also includes the 2026 Directions and the older function-wise Master Directions:
381 documents in all."

## 4. The dataset

| Layer | What it is | Size |
|---|---|---|
| Corpus | Every Master Direction on RBI's listing, PDF → text, split into paragraphs with stable ids such as `md_13006::p00135` | 381 Directions, 76,188 paragraphs, 19 headings, 11 entity classes, 57 subject families |
| Deontic-cue paragraphs | Paragraphs containing obligation words ("shall", "must", "is required to") | 33,507 |
| Obligation candidates | Candidate obligations extracted by our rules (version 4) | 28,694 |
| Cross-class matches | For each candidate, the closest paragraphs in other classes' Directions on the same subject (bge embeddings + lexical similarity) | used to build T1 and T2 |
| **T1 gold** | Expert-labelled obligations: for each compared class, *same* / *different* / *none* | 106 items from 123 sampled (17 rejected), **412 class judgements: 213 same, 78 different, 121 none** |
| T2 | Counterpart retrieval relevance sets | 3 sets: 291, 53 and 25 queries |
| T3 | Temporal status items built from RBI Amendment notifications: in force / amended / deleted on a date | 60 built, 52 scored |
| T4 | RePASs metric audit: 30 questions × 4 answer types (genuine, concatenated, negated, off-topic) + 30 human-rated answers | 30 questions |
| Supplementary (P2-003) | RBI penalty press releases, amendment notifications, withdrawn circulars, FAQs | e.g. 463 enforcement press releases |

**Where the T1 items come from (by source class):** Commercial Banks 15, Small Finance Banks 15, AIFIs 11, Urban
Co-op Banks 11, Regional Rural Banks 9, Local Area Banks 8, Payments Banks 8, Rural Co-op Banks 8, ARCs 7, CICs 7,
NBFCs 7.

**Release:** we do not redistribute RBI's full text (an open IPR question). The release is **pointer-only**: paragraph
ids, URLs, character offsets and SHA-256 hashes, so anyone can rebuild the text from rbi.org.in and verify it.

## 5. The annotation process

**What is labelled.** Each row is one candidate obligation. The annotator decides: (1) is it really an obligation;
(2) which entity classes it applies to; (3) for each compared class, is the closest rule the *same* duty, a *different*
duty, or is there *no matching rule* (with the matched paragraph). From these, a fixed rule (v3.6) gives the item flag:
**shared** (same everywhere), **class-specific** (any *different*), or **absent**.

**Who and how.**

- **Guidelines:** written down (version 3.1), with examples, read before labelling. Labels are given in a CSV file.
- **Primary annotator:** Karan labelled the gold. The gold is therefore **single-expert**, and we say so everywhere.
- **Blind test–retest:** Karan labelled items twice in two blind passes (shuffled order, no access to pass 1). Items
  labelled the same way twice were promoted to *validated*.
- **Adjudication:** where the two passes disagreed, the annotator saw both answers side by side and had to write down
  which one is right and why; the tooling refuses a decision without a written reason.
- **Second raters:** Akash and Meer labelled a shared subset independently, starting from blank files, with no
  discussion until all files were returned. In public outputs raters appear only as rater_1, rater_2, rater_3.
- **Pilot first:** an 18-item pilot showed the differential flag was unstable (retest κ was below zero), so the
  guidelines were revised (v2 → v3) before the main labelling.

**How the 106 gold items were finalised (route):** 62 single-pass, 38 adjudicated, 6 retest-consistent.

**How reliable are the labels?** (κ = Cohen's / Fleiss' kappa: 1 = perfect agreement, 0 = chance.)

| Measure | Value | Meaning |
|---|---|---|
| Inter-rater, per-class judgement (Fleiss κ, three raters) | **0.774** | Substantial agreement on same / different / none |
| Inter-rater, differential flag (Fleiss κ) | 0.571 | Moderate: the flag is harder |
| Test–retest, differential flag (Karan, blind) | 0.426 | Moderate: honest evidence the task is hard even for an expert |

## 6. The flow, from input to output

### 6a. Building the benchmark (once)

1. **Harvest** the 381 PDFs from RBI's listing (Python `requests`, `BeautifulSoup`, `lxml`).
2. **Extract** text (`pdfplumber`) and **segment** into 76,188 paragraphs with stable ids and hashes.
3. **Tag** each Direction with its entity class and subject family (the 19 × 57 class-by-subject matrix).
4. **Extract candidates** (28,694) with deontic-cue rules, measuring precision with Wilson confidence intervals.
5. **Match** each candidate to paragraphs in other classes' Directions on the same subject (bge embeddings + lexical).
6. **Sample and annotate** (Section 5) → T1 gold; build T2, T3 and T4 from the matches and the supplementary sources.

### 6b. Evaluating one system on one T1 item

- **Input:** an obligation *o* from class *c*, the list of classes to compare, and (for T3) a date *t*.
- **Hybrid retrieval:** BM25 (keyword) and bge (meaning) each rank paragraphs; reciprocal rank fusion (RRF, k = 60)
  merges the two lists.
- **Filter A (class):** keep only paragraphs from the target class's Directions. **Filter B (temporal):** keep only
  paragraphs in force on date *t*.
- **LLM judge** (gemini-3.5-flash-lite, temperature 0, frozen prompt): for each class, *same*, *different* or *none*,
  with a short rationale and the matched paragraph.
- **Verifier C** (final agentic system only): an NLI model checks whether the cited paragraph entails the rationale;
  if not, retry once, then abstain.
- **Flag rule v3.6:** per-class answers → item flag (shared / class-specific / absent).
- **Output:** the prediction is written to a **sealed** run file before scoring; then the scorer compares it with the
  gold and computes F1 with a paired bootstrap confidence interval.

### 6c. The structured comparator (our main method)

1. For the source obligation and each candidate counterpart, the LLM fills a **13-field table**: actor, action, object,
   scope, condition, threshold, amount, percentage, frequency, deadline, exception, documentation, reporting.
2. **A fixed rule decides,** not the model: if the candidate does not address the same duty → *none*; if it does and
   any field differs, or a material field appears on one side only → *different*; otherwise → *same*.
3. The class verdict is the strongest candidate verdict. It was developed only on a separate 30-item set and frozen by
   hash before the gold was touched.

### 6d. The audit generator (the product)

- **Input:** an entity profile: name, entity class, as-of date, last review date, activities, and optional group classes.
- **Processing** (no AI involved):
  - **Applicability register:** every obligation that applies to the class, with its status on the as-of date.
  - **Change log:** amendments and withdrawals since the last review.
  - **Compliance calendar:** deadlines and frequencies extracted by rules.
  - **Cross-class differential:** where your duties differ from the group classes.
  - **Enforcement context:** past RBI penalties on the class.
  - **Policy gap analysis** (installed version): uploaded policies matched against obligations with bge + NLI.
- **Review:** a named reviewer confirms or disputes rows and signs off; sign-off writes a new pack and keeps the original.
- **Output:** the audit pack on screen, plus Excel, Word, PDF, an `.ics` calendar and a JSON audit trail, each carrying
  the corpus snapshot date and hash.

### 6e. The AI assistant

1. **Question in** (any RBI question, one entity class, or one pack).
2. **Retrieve** RBI paragraphs: bge + BM25 fused by RRF; top 6 become the evidence.
3. **Write:** the LLM answers only from the evidence and cites an evidence label for each sentence.
4. **Verify:** the NLI model checks each sentence against its cited paragraph; numbers must appear in the source.
   Unsupported sentences are held back; if nothing survives, it retries once and then abstains.
5. **Output:** verified sentences with source chips that open the official RBI PDF, the evidence list, and the
   model and verifier ids. Other assistant features (explain an obligation, explain a change, memo, action plan,
   calendar check, differential second opinion, draft clause, review suggestion) follow the same write-then-check pattern.

## 7. Models and LLMs: what we called, where, and how many times

**Three LLMs were called in the research, exactly as you remembered (two Gemini, one Groq):**

| LLM | Provider | Where it was used | Cached responses |
|---|---|---|---|
| **gemini-3.5-flash-lite** | Google (free tier) | Every T1 system (class-blind, class-aware, final agentic, long-context), the structured comparator, extension 3 (reranking) and extension 8 (IndiaFinBench) | **1,986** (13.7 million tokens) |
| **openai/gpt-oss-120b** | Groq (free tier) | T4: the 30 questions and 30 genuine answers; extension 4 (the T1 class-blind rerun with a larger open model, 103 items) | **163** = 30 + 30 + 103 |
| **gemini-3.8-flash** | Google (free tier) | Configured first; passed the smoke test; used for T4 until its free quota (20 requests/day) ran out after 7 questions. Those 7 were **discarded**, and T4 was rerun entirely on gpt-oss-120b | **7** (discarded) |

**LLMs used by the applications (after the research):**

| LLM | Where |
|---|---|
| gemini-3.5-flash-lite | The hosted AI assistant on the public site; the Lab comparator API (the public site replays its recorded runs); the authors' local "Ask RBI-ObliBench" workspace assistant |
| Qwen2.5 7B instruct (1.5B as fallback) | The installed (local) audit generator's AI features, run by Ollama on the user's own machine |

**Non-LLM models:**

| Model | Type | Used for |
|---|---|---|
| BAAI/bge-base-en-v1.5 | Text embedding | Dense retrieval, cross-class matching, assistant search, gap analysis |
| BM25S (Lucene variant) | Keyword ranking (not a neural model) | Lexical retrieval |
| cross-encoder/nli-deberta-v3-xsmall | NLI cross-encoder | Verifier C, checking AI sentences, gap coverage; also RePASs' own NLI model |
| cross-encoder/ms-marco-MiniLM-L6-v2 | Reranker | Extension 3 (reranking test) |
| microsoft/deberta-large-mnli, nlpaueb/legal-bert-base-uncased | Inside RePASs | T4 metric audit (obligation coverage and classifier) |
| Confidence model "M2" | Small statistical model | Probability that a comparator answer is right (Triage page), fitted on the separate 30-item development set |

All LLM calls used temperature 0, frozen prompts whose SHA-256 hashes are recorded, and a response cache, so rerunning
the pipeline costs zero new calls.

## 8. The complete tech stack, in simple terms

| Layer | Tools | What they do for us |
|---|---|---|
| Data collection | Python 3, requests, BeautifulSoup, lxml, pdfplumber | Download RBI pages and PDFs; turn PDFs into text |
| Retrieval | BM25S, bge-base embeddings, reciprocal rank fusion | Find the right paragraph by keywords and by meaning, then merge |
| LLMs | Gemini API, Groq API, Ollama (local) | Judge same / different, extract fields, write drafts |
| Checking | NLI DeBERTa cross-encoder, ONNX Runtime (hosted) | Check that each AI sentence is supported by its source |
| Orchestration | A Python RAG pipeline; a LangGraph port (extension 9, identical outputs) | Run the systems step by step, with retries and abstention |
| Statistics | NumPy, pandas, SciPy, scikit-learn; paired bootstrap (2,000 resamples), Wilson intervals, Cohen's / Fleiss' κ, Spearman's ρ | Honest uncertainty on small samples |
| Research website | React 19, Vite, Tailwind, TypeScript | The public site: cases, results, method, research pages |
| Backends | FastAPI (local audit generator), Azure Functions in Python (hosted comparator and audit generator), Node/TypeScript (local workspace assistant) | Serve the product and the AI features |
| Hosting | Azure Storage static website, Azure Functions (Flex Consumption), Azure Blob Storage | Free-tier public hosting |
| Compute | Apple-silicon MacBook, Kaggle notebooks (embeddings) | No special hardware needed |
| Quality | pytest (1,200+ tests), Vitest (UI tests), `check_dist.py` release checks | Every number and page is tested |

## 9. How the frontend and backend fit together

**1. Research website (static, no server):**
- The Python pipeline writes `reports/results_v2.json` (the single source of truth) and the sealed run files.
- `ui/scripts/build_demo_data.py` turns these into 118 small JSON files (about 4.2 MB) in `ui/public/data/`.
- The React pages fetch those files directly. Every number on the site is a key in the results file.
- Before every deploy, `check_dist.py` blocks the release if any file copies more than 25 consecutive words of RBI text,
  contains a key, or points at a local backend. The build is then uploaded to an Azure Storage static website.

**2. Lab (comparator API):**
- An Azure Function in Python runs the frozen comparator after verifying the prompt and rule hashes; the key stays on
  the server.
- On the public site the live call is switched off for cost reasons, and the page replays recorded runs; it says so.

**3. Audit generator, installed version (local):**
- The browser talks to a **FastAPI** backend on 127.0.0.1:8765 through the Vite dev proxy (`/api/auditgen`).
- The backend reads the corpus files, generates packs, runs bge and NLI in PyTorch, and calls a local **Qwen** model
  through **Ollama** (127.0.0.1:11434). Nothing leaves the machine.

**4. Audit generator, hosted version (the public demo):**
- The website calls an **Azure Function** (`rbiob-audit-5qbvp2`) at its absolute URL.
- The Function generates packs, stores them in **Azure Blob Storage** for 7 days, and runs the AI features. **Gemini**
  writes the drafts, while **ONNX** versions of bge and the NLI verifier retrieve evidence and check every sentence.
- Slow work (generate, exports, AI) runs as a **background job**: the page starts the job, then polls for the result
  with short, retried requests. This makes the site robust to cold starts and to Azure sending a request to a busy worker.
- Every RBI quote returned is cut to 12 words and linked to the official PDF.

## 10. Do we use a database?

**No database server.** Our data is read-mostly and must be reproducible, so we use versioned files:

- **JSONL / JSON files:** the corpus paragraphs, manifest, candidates, matches, gold labels and `results_v2.json`.
- **A file-based LLM response cache:** 2,156 cached responses keyed by a hash of the request, so a rerun makes 0 new
  calls and gives identical outputs.
- **Azure Blob Storage** (hosted product only): generated packs (auto-deleted after 7 days), AI outputs, background-job
  results and the daily usage counters.
- **Browser localStorage:** which packs a visitor generated (convenience only).

Why no database: files can be hashed, versioned and released as pointers; they need no server; and they cost nothing.

## 11. Why this is a benchmark, and how it compares

**What makes it a benchmark, not just a demo:**
- **Defined tasks:** T1–T4, each with a fixed input and output.
- **Gold labels:** labelled by an expert, with reliability measured.
- **Fixed metrics:** F1, nDCG@10 and Spearman's ρ, all with confidence intervals.
- **Baselines and sealing:** baseline systems, and predictions sealed before scoring.
- **Reproducibility:** frozen, hashed prompts; a pointer-only release; and a public site where anyone can inspect every case.

**How it compares with related work:**

| Work | Domain | What it tests | Cross-class? | Audits the metric? |
|---|---|---|---|---|
| ObliQA / RIRAG | ADGM (Abu Dhabi) regulations | Retrieve and answer from one rulebook | No | Introduces RePASs |
| AUEB-Archimedes (RIRAG-2025) | ADGM | A RAG system | No | Showed concatenation games RePASs |
| ObliQA-MP | ADGM | Multi-passage ranking | No | No |
| IndiaFinBench | SEBI and RBI text | LLM question answering, single documents | No | No |
| LexGLUE | EU / US law | Legal classification | No | No |
| RAGAS | General | A RAG evaluation framework | No | Reference-free metrics |
| **RBI-ObliBench** | **381 RBI Master Directions** | **Applicability, differential, retrieval, temporal** | **Yes** | **Yes (T4)** |

**Why it is better for this problem:**
- It is the **first benchmark for cross-entity-class obligation differences**, the real question for groups, auditors
  and RegTech vendors.
- It covers the whole RBI listing, not a sample.
- It tests time: whether a paragraph is in force on a date.
- It checks its own yardstick: it shows that RePASs can be gamed.

We present it as **complementary** to the other benchmarks, not as beating them at their own tasks.

## 12. The major decisions, and why we made them

| Decision | Why |
|---|---|
| One LLM (gemini-3.5-flash-lite) for every T1 system, at temperature 0 | A fair comparison: only what each system sees changes. Free tier. Repeatable. |
| Frozen, hashed prompts; predictions sealed before scoring; comparisons pre-registered | So we could not tune on the test set, even by accident |
| Hybrid retrieval (BM25 + bge, RRF k = 60) | Regulations need exact terms (BM25) and paraphrase (bge); RRF needs no training and k = 60 is the standard value |
| Class and temporal filters as switchable ablations | To measure each component's value instead of assuming it |
| NLI verifier with retry-then-abstain | To stop unsupported answers; we measured that it costs F1 and coverage on T1, and reported that |
| Structured comparator: the LLM extracts, a fixed rule decides | LLMs judge holistically and miss small field differences; a rule is explainable, testable and consistent |
| Developed on a separate 30-item set, frozen before the gold | An honest estimate of how it generalises |
| Paired bootstrap (2,000 resamples) and Wilson intervals | Our samples are small; we show the uncertainty, not only the point estimate |
| Single-expert gold, plus second raters and test–retest | Time and budget; we measure reliability and disclose the limitation |
| Pointer-only data release; 12-word quotes on the public site | RBI text redistribution is an open IPR question |
| Free tiers and a laptop | Zero cost; anyone can reproduce it |
| Installed version local-first (Ollama); hosted demo uses Gemini + ONNX | Company policies never leave the network; the free cloud has no GPU, so small ONNX models run on CPU |
| Static website + serverless Functions + blob storage | No servers to maintain; costs nothing when idle |

## 13. Time complexity (rough, in simple terms)

Notation: P = paragraphs (76,188), C = candidates (28,694), d = embedding size (768), q = query words, k = items
returned, L = tokens in a text, B = bootstrap resamples (2,000), n = items scored.

| Step | Complexity | In words |
|---|---|---|
| Harvest and extract | O(total pages) | Linear in the size of the PDFs |
| Segment and hash | O(total characters) | One pass over the text |
| Candidate extraction (rules) | O(P) | One pass over the paragraphs |
| Embedding every paragraph (bge) | O(P × L²) per transformer pass, once | The one expensive step; done once and cached |
| BM25 search | about O(q × postings) with an inverted index | Only paragraphs containing the query words are touched |
| Dense search (brute force) | O(P × d) per query | About 58 million multiply-adds: milliseconds |
| RRF fusion | O(k log k) | Merging two short ranked lists |
| LLM judge | 1 call per item per system | The cost is API latency, not computation; cached afterwards |
| Structured comparator | O(candidates) LLM calls per class pair | 2 candidates per class here |
| NLI verification | O(sentences × citations) cross-encoder passes, each O(L²) with L ≤ 512 | A few passes per answer |
| Bootstrap confidence interval | O(B × n) | 2,000 × 106 ≈ 212,000 cheap steps |
| Audit pack generation | O(obligations for the class + differential rows) | About 1–3 s for one pack |
| Assistant search | O(N × q) BM25 + O(N × d) dense over about 28,000 obligation paragraphs | Under a second |
| 12-word quote check | O(L) per string (hashed word shingles) | Linear in the text length |

## 14. Every result number in the presentation, explained

**Slide 3 (Introduction):** 381 Directions, 76,188 paragraphs, 11 regulated-entity classes (Section 3).

**Slide 4 (Literature review and problem statement):**
- **T1:** 106 items and 412 class judgements.
- **T2:** 291, 53 and 25 queries in its three relevance sets.
- **T3:** 52 items.
- **T4:** 30 questions × 4 answer types.

**Slide 5 (Block diagram):** 28,694 candidates; T1 gold of 106 items.

**Slide 7 (Structured comparator), compared with the class-aware LLM:**
- **‘Different’ F1 rises from 0.154 to 0.409.** F1 combines precision and recall; it is measured only on the
  *different* label.
- **‘Different’ recall improves by +0.397, with 95% CI [+0.250, +0.543].** The interval excludes 0, so the
  improvement is real.
- **26 of 56:** of the 56 real differences that every LLM system missed, the comparator found 26.
- **40 of 78:** of all 78 real differences, the comparator still misses 40. That is our honest limit.

**Slide 8 (Five LLM systems; 3-way flag F1 / ‘different’ F1 on the 106-item gold):**
- Class-blind: 0.602 / 0.321
- Class-aware: 0.551 / 0.154
- Final agentic: 0.483 / 0.047. It abstains on some items: coverage 0.774, meaning it gives a definite answer on 77.4%
  of items.
- Long-context: 0.509 / 0.074, scored on 102 items because 4 prompts failed repeatedly at the 100,000-token cap.
- Structured comparator: 0.616 / 0.409, best on both.

**Slide 11 (RQ1 and RQ2):**
- **The class filter lifts counterpart nDCG@10 by +0.451, from 0.443 to 0.894, with 95% CI [+0.421, +0.481].** It
  also helps on the other two sets: 0.319 → 0.741 and 0.504 → 0.675.
  - Part of this gain is by construction, because relevance was labelled only for the target class.
  - "Hybrid − source class" (0.464) shows that just removing your own class is not enough.
- **On T1 judgement, the class filter changes F1 by −0.050, with 95% CI [−0.133, +0.027].** The interval includes 0,
  so there is no significant effect.
- **56 of 78:** gold ‘different’ units that every LLM system missed.
- **262 of 350:** ‘different’ errors made while the correct counterpart was already in the model's context. So this
  is a reasoning failure, not a retrieval failure.
- **No LLM beats the embedding baseline on collapsed F1:** class-blind −0.019 [−0.114, +0.072]; class-aware +0.024
  [−0.096, +0.135].

**Slide 12 (RQ3, the RePASs audit):**
- **Mean RePASs score by answer type:** genuine 0.371, concatenated 0.746, negated 0.049, off-topic 0.229.
- **Concatenated − genuine = +0.375, with 95% CI [+0.325, +0.427].** This test was pre-registered. Simply pasting the
  retrieved obligations scores double a real answer.
- **ρ 0.731:** RePASs agrees well with human ratings of faithfulness.
- **ρ 0.008:** RePASs has essentially no agreement with "does it answer the question?". It measures copying, not
  relevance.
- **Our exploratory repair ranked genuine answers first but lost agreement with human faithfulness (ρ −0.126).** We
  report it as not usable.

**Slide 13 (Additional experiments, all pre-registered):**
- **Extension 3, cross-encoder reranker:** class-blind 3-way F1 falls 0.602 → 0.538, a change of −0.064 with 95% CI
  [−0.115, −0.017]. Reranking hurts.
- **Extension 4, gpt-oss-120b on 103 items:** 3-way F1 0.614 against Gemini's 0.624, no significant change; ‘different’
  F1 0.289 against 0.353. A bigger model does not fix the core failure.
- **Extension 8, IndiaFinBench, 268 of 406 items:**
  - Accuracy 0.757, with 95% CI [0.703, 0.805].
  - By question type: regulatory interpretation 0.951, temporal 0.742, contradiction 0.729, numerical 0.561.
  - The dataset's own reference is not directly comparable: twelve models scored 70.4–89.7%, non-specialist humans 69.0%.
- **Extension 9, LangGraph port:** identical prompts and outputs on 4 systems × 106 items.

**Website-only results (the /results page):**
- With high confidence, the comparator was right 96% of the time on the test set. This is observed, not a recommended
  threshold.
- Without a date check, an LLM said 23 of 26 already-changed rules were still "in force, unchanged".
- With the temporal filter, T3 status was exactly right on 52 of 52 items, against 0.538 without it.

**Annotation (Section 5):** κ 0.774 inter-rater on class judgements; κ 0.426 test–retest on the flag.

## 15. Metrics glossary

| Metric | Plain meaning |
|---|---|
| Precision / recall / F1 | Of what the system called X, how much was right / of all real X, how much it found / their balance |
| Macro-F1 | F1 averaged over the labels, so rare labels count equally |
| 3-way flag F1 | Macro-F1 over shared / class-specific / absent (an *ambiguous* answer counts as wrong) |
| Collapsed F1 | Macro-F1 over absent vs present (an easier, two-way view) |
| ‘Different’ F1 / recall | F1 / recall on the *different* label only: the hardest and most important case |
| Coverage | Share of items where the system gave a definite answer (did not abstain) |
| nDCG@10 | How high the correct paragraph ranks in the top 10 results (1 = always first) |
| 95% confidence interval [a, b] | The range the true value plausibly lies in; if it excludes 0, a difference is significant |
| Paired bootstrap | Resample the same items 2,000 times and recompute the difference, to get that interval |
| κ (kappa) | Agreement corrected for chance (above 0.6 substantial, 0.4–0.6 moderate) |
| ρ (Spearman) | Rank correlation: 1 = same order, 0 = unrelated |

## 16. Honest limitations

- The **gold is single-expert**; second-rater agreement is measured only on a subset.
- The comparator **still misses 40 of 78** differences.
- **Small sets:** 106 T1 items, 52 T3 items and 30 T4 questions, so our confidence intervals are wide.
- **Enforcement links are weak labels:** only 53.3% were clean on a 30-item check, and 212 of 463 releases cite
  pre-2026 circulars with no current Direction.
- **Free-tier models only;** frontier models were not tested.
- **Hosted demo limits:** the public demo is limited to 30 AI answers and 40 packs per day, and policy uploads exist
  only in the installed version.

## 17. Questions the panel may ask, with short answers

**About the problem and data**

1. **What exactly is the problem?** Whether a duty in one entity class's Master Direction is the same, different or absent for another class, and finding that counterpart.
2. **Why does it matter?** Groups with a bank and an NBFC, auditors and RegTech vendors must know where duties differ; a missed difference can mean non-compliance and penalties.
3. **RBI has about 240 Master Directions; why 381?** About 240 is the 2025 consolidated series (we have 244); RBI's listing page also has 87 Directions issued in 2026, 39 older function-wise Master Directions and 11 others. We took everything on the page.
4. **Where did the data come from?** rbi.org.in, harvested August–September 2026, PDFs converted with pdfplumber and split into 76,188 paragraphs.
5. **Can we share the dataset?** We release pointers (ids, URLs, offsets, hashes), not RBI's text, because redistribution is an open IPR question.
6. **Why only 106 gold items?** Each item needs expert judgements for every compared class (412 in total); we report confidence intervals so the uncertainty is visible.
7. **Who labelled the data, and is it reliable?** Karan as primary annotator, with blind test–retest and written adjudication; Akash and Meer as independent second raters. Inter-rater κ is 0.774 on class judgements.

**About the method and models**

8. **Which LLMs did you use?** gemini-3.5-flash-lite for every T1 system and the comparator (1,986 responses); gpt-oss-120b on Groq for T4 and a replication (163); gemini-3.8-flash for 7 T4 questions that were discarded when its quota ran out. Locally, Qwen2.5 runs the installed product.
9. **Why that model?** One free-tier model for every system makes the comparison fair and repeatable; the larger gpt-oss-120b did not do better.
10. **What is hybrid retrieval?** BM25 finds exact words, bge finds meaning, and reciprocal rank fusion merges the two rankings.
11. **What does the NLI verifier do?** It checks whether the cited paragraph actually supports each sentence; unsupported sentences are held back.
12. **Why did the verifier make T1 worse?** It abstained on many correct answers: the whole-paragraph premise is a poor test for a one-sentence rationale. We report it as measured.
13. **What is new about the structured comparator?** The LLM only extracts 13 fields; a fixed, inspectable rule decides same / different, which lifted ‘different’ F1 from 0.154 to 0.409.
14. **Isn't the comparator tuned to the test set?** No: developed on a separate 30-item set, one bug-fix revision, frozen by hash before we saw the gold, comparisons pre-registered.
15. **What is RePASs, and what did you find?** A faithfulness metric for regulatory answers; copying the regulation scores 0.375 higher than a genuine answer, so it rewards copying.
16. **Is this a RAG system or an agent?** Both: a RAG pipeline with agent-like steps (filters, verification, retry, abstain); we measured that the agentic additions did not help T1.

**About results and statistics**

17. **What is your headline result?** LLM systems miss 56 of 78 real differences, mostly with the right paragraph in context; our comparator recovers 26 of them.
18. **What does the confidence interval mean?** The plausible range of the true difference; if it excludes 0, the effect is significant (2,000-resample paired bootstrap).
19. **Did knowing the entity class help?** For retrieval, a lot (+0.451 nDCG@10); for the same / different judgement, not significantly (−0.050).
20. **Why is the long-context system scored on 102 items?** Four very long prompts failed repeatedly at the uniform 100,000-token cap; every system is compared on exactly the same 102 items.

**About the product and engineering**

21. **How does the frontend talk to the backend?** The research site reads pre-built JSON files; the audit generator calls a FastAPI backend locally or an Azure Function when hosted, with slow work run as polled background jobs.
22. **Do you use a database?** No database server: versioned JSON / JSONL files, a hashed LLM response cache, and Azure Blob Storage for hosted packs.
23. **Is it legal advice?** No: decision support. Every row cites RBI, rows needing judgement are flagged, and a named person must confirm and sign off.
24. **What about confidential company documents?** Policy uploads exist only in the installed version, inside the user's network; the public demo sends only RBI text and the question to Gemini.
25. **How do you keep the corpus up to date?** The installed version can check rbi.org.in for new or amended Directions (a dry run first); every pack shows the snapshot date and hash.
26. **What did it cost?** Nothing: free tiers for Gemini and Groq, Kaggle for embeddings, a student Azure subscription with daily caps.
27. **How do you prevent hallucination?** Answers are written only from retrieved RBI text, every sentence is checked by NLI, numbers must appear in the source, and unsupported sentences are held back or the assistant abstains.

**About the paper and impact**

28. **What is the status of the paper?** Submitted on 10 Oct 2026 to AISIGH-SD 2026 (IEEE Bhubaneswar Section), Paper ID 1954, under review; the decision is due 15 Nov.
29. **Which SDGs does it map to?** 16 (transparent, accountable institutions), 8 (strong domestic financial institutions), 9 (research and innovation).
30. **What would you do next?** Independent second raters for all items, frontier models, a comparator that uses retrieved evidence, larger T3 / T4, and a real pilot with a compliance team.
