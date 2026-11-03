# P3-002 — T4: is RePASs gameable on RBI Master Directions?

**RQ3.** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal repair resists concatenation and verbatim extraction?

## Answer

- **Concatenated (verbatim obligations) − genuine:** RePASs difference +0.375 [+0.325, +0.427], n = 30 questions → **reproduces**.
- **Adversarial: negated − genuine:** RePASs difference -0.322 [-0.390, -0.243], n = 30 questions → **does not reproduce**.
- **Adversarial: off-topic − genuine:** RePASs difference -0.141 [-0.206, -0.080], n = 30 questions → **does not reproduce**.
- **Exploratory repair:** repaired(genuine) − repaired(concatenated) = +0.208 [+0.168, +0.253] → **genuine ranked above**. This works only because the overlap penalty zeroes every verbatim answer. The repaired score no longer tracks human faithfulness (ρ = -0.126 [-0.477, 0.216]), so it is **not** a usable repair as it stands. It was designed with the RIRAG finding in mind and tested on the same 30 questions, so even the ranking result is optimistic.
- **Metric vs human:** Spearman ρ between RePASs and human faithfulness = 0.731 [0.535, 0.845]; between RePASs and human `answers_question` = 0.008 [-0.323, 0.339]; n = 30 rated answers (one rater).

## Interpretation

- **What RePASs rewards.** RePASs tracks faithfulness to the passages, and the human ratings agree that verbatim extracts are faithful: concatenated answers were rated 2.00 on `faithful` against 1.80 for genuine ones. What it does not track is whether the answer addresses the question: concatenated answers were rated 1.30 on `answers_question` against 2.00 for genuine ones, and RePASs' correlation with `answers_question` is near zero. The gameability that reproduces is this one: concatenating the retrieved obligations outscores a genuine answer without answering the question better.
- **Adversarial answers.** RePASs is not fooled by negated or off-topic answers: both score clearly below genuine, mostly through contradiction (negated) and missing entailment and coverage (off-topic).
- **Why genuine answers score low.** Genuine answers carry high contradiction (0.45) and low coverage (0.15). The small NLI model often scores rated-faithful paraphrases as contradictions: one example below (T4Q06, a "No."-style answer with citation markers and bold text) is rated fully faithful by the human and scores contradiction 0.99. Which of these features drives it was not tested. Coverage rewards restating every obligation in the passages, including those irrelevant to the question.
- **The repair.** The relevance term is close to zero for every type (genuine 0.046, concatenated 0.040), so the repaired ordering comes entirely from the overlap penalty. That penalty removes the concatenation advantage by construction. It also sends every faithful verbatim answer to 0, which is why the repaired score correlates with human faithfulness at about zero or below. A repair that resists concatenation without punishing faithful quotation would need a question-relevance signal that actually discriminates; this NLI model does not provide one. That design question belongs to later work and is not settled here.

Prior evidence, for context only: on ObliQA a naive obligation-concatenation system scored RePASs 0.947, above human experts (AUEB-Archimedes at RIRAG-2025, arXiv 2412.11567). Nothing here assumed that result; the verdict rule was fixed before scoring.

## Setup

- **RePASs:** https://github.com/RegNLP/RePASs at commit `821d438d07cfc6747bd657965188d9dde85dcb71`, code unmodified. Their scripts ran in a separate venv (transformers 4.x: their tokenizer call `encode_plus` no longer exists in transformers 5), called through `scripts/run_repass.py`, in their JSON format (`QuestionID`, `RetrievedPassages`, `Answer`).
  - NLI for entailment and contradiction: `cross-encoder/nli-deberta-v3-xsmall`. NLI for obligation coverage: `microsoft/deberta-large-mnli` (entailment above 0.7). Obligation classifier: `nlpaueb/legal-bert-base-uncased` fine-tuned with their `scripts/train_model.py` on their dataset.
  - Composite, as implemented: **(obligation coverage + entailment − contradiction + 1) / 3**. Entailment and contradiction are the mean over answer sentences of the maximum over passage sentences; their code joins the passages into one string first.
  - Classifier training: device mps, seed 42, 10.3 min, early stop after epoch 6.0; best checkpoint validation F1 0.995 (their 80/20 split, not our data).
  - Scoring device: cpu (their code picks CUDA or CPU only).
- **Questions:** 30 obligation paragraphs from the T1 validated set, stratified by class (11 classes, 23 subject families, seed 20261003). One question per paragraph was drafted by the LLM (prompt, model id and output logged in `t4_questions_v1.jsonl`).
- **LLM:** questions and genuine answers ran on **Groq `openai/gpt-oss-120b`**, not the configured Gemini `gemini-3.8-flash`. Gemini's free tier allows 20 requests per day per model, and that quota ran out after 7 questions. Following the P3-002 rule, each step was rerun entirely on the fallback (the 7 Gemini questions were discarded, never mixed). Temperature 0, cached, capped. Calls: questions 30, genuine answers 30.
- **Passages:** the P3-001 class-aware hybrid top 3 for the question (target class = the paragraph's class), plus the source paragraph when it was not in the top 3. The source was in the top 3 for 28/30 questions; ranks: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 3, 3, 3, 4, 4].
- **Answer types** (each in its own file):
  - `genuine`: the LLM answers from the passages only and cites passage ids. The Groq model writes its citations as 【…】 rather than […].
  - `concatenated`: no LLM. Every sentence of the passages that holds a kept P2-001 (rules v4) deontic cue, verbatim, in passage order.
  - `adv_negated`: the concatenated answer with shall/must/is required to flipped and every number doubled (enumerators like "(1)" included).
  - `adv_offtopic`: verbatim kept-cue sentences from seeded random Directions in a different subject family, cut to the concatenated answer's length.

## RePASs by answer type (n = 30 each)

| Answer type | RePASs | Entailment | Contradiction | Obligation coverage |
|---|---|---|---|---|
| Genuine (LLM, passages only) | 0.371 [0.311, 0.431] | 0.415 [0.311, 0.529] | 0.449 [0.327, 0.580] | 0.147 [0.082, 0.211] |
| Concatenated (verbatim obligations) | 0.746 [0.692, 0.796] | 0.953 [0.909, 0.984] | 0.316 [0.230, 0.413] | 0.601 [0.498, 0.701] |
| Adversarial: negated | 0.049 [0.022, 0.082] | 0.096 [0.048, 0.156] | 0.966 [0.936, 0.991] | 0.017 [0.003, 0.034] |
| Adversarial: off-topic | 0.229 [0.198, 0.257] | 0.030 [0.016, 0.046] | 0.342 [0.259, 0.432] | 0.000 [0.000, 0.000] |

Mean [95% CI], bootstrap over questions (2,000 resamples, seeded).

## Paired differences against genuine (same questions, same resamples)

| Comparison | Δ RePASs | Δ Entailment | Δ Contradiction | Δ Obligation coverage | Verdict |
|---|---|---|---|---|---|
| Concatenated (verbatim obligations) − genuine | +0.375 [+0.325, +0.427] | +0.538 [+0.416, +0.649] | -0.133 [-0.210, -0.060] | +0.455 [+0.340, +0.567] | reproduces |
| Adversarial: negated − genuine | -0.322 [-0.390, -0.243] | -0.319 [-0.441, -0.203] | +0.518 [+0.375, +0.646] | -0.130 [-0.196, -0.063] | does not reproduce |
| Adversarial: off-topic − genuine | -0.141 [-0.206, -0.080] | -0.385 [-0.502, -0.279] | -0.107 [-0.253, +0.032] | -0.147 [-0.211, -0.082] | does not reproduce |

Verdict rule (on the RePASs difference): CI entirely ≥ 0 → reproduces; entirely < 0 → does not reproduce; otherwise inconclusive at n = 30. For the adversarial types, "reproduces" means the metric scores the adversarial answer at least as high as the genuine one.

**Sensitivity:** excluding the 2 questions flagged `bad_question` (T4Q14, T4Q30), n = 28: concatenated − genuine +0.367 [+0.314, +0.419] → reproduces; adv_negated − genuine -0.331 [-0.405, -0.252] → does not reproduce; adv_offtopic − genuine -0.152 [-0.221, -0.088] → does not reproduce.

## Human faithfulness vs the metric

One rater (Karan), blind to answer type, scores and model. 30 answers: 10 genuine, 10 concatenated, 5 adv_negated, 5 adv_offtopic. Each question appears once on the sheet.

| Answer type | n | Human `faithful` (0–2) | Human `answers_question` (0–2) |
|---|---|---|---|
| Genuine (LLM, passages only) | 10 | 1.80 [1.40, 2.00] | 2.00 [2.00, 2.00] |
| Concatenated (verbatim obligations) | 10 | 2.00 [2.00, 2.00] | 1.30 [0.80, 1.80] |
| Adversarial: negated | 5 | 0.00 [0.00, 0.00] | 1.60 [1.20, 2.00] |
| Adversarial: off-topic | 5 | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] |

Per-type n is 5–10, so these CIs are wide.

| Correlation (Spearman, n rated answers) | All rated | Without bad questions |
|---|---|---|
| RePASs vs `faithful` | 0.731 [0.535, 0.845] (n = 30) | 0.711 [0.476, 0.842] (n = 28) |
| RePASs vs `answers_question` | 0.008 [-0.323, 0.339] (n = 30) | 0.114 [-0.242, 0.444] (n = 28) |
| Repaired score vs `faithful` | -0.126 [-0.477, 0.216] (n = 30) | -0.094 [-0.469, 0.251] (n = 28) |
| Repaired score vs `answers_question` | 0.123 [-0.260, 0.457] (n = 30) | 0.077 [-0.312, 0.413] (n = 28) |

Rating time from the accepted minutes log: 75 min for 30 answers, **2.5 min per answer** (blocks: 25, 25, 25 min).
`bad_question` = yes on 2 of 30 questions (T4Q14, T4Q30); the stop threshold is more than 5.

## Exploratory repair

Declared in config (`t4.repair`) at 2026-09-27T18:25:00+00:00, before any answer was scored:
- `lcs_ratio` = token LCS(answer, retrieved passages) / answer tokens; `penalty` = clip((lcs_ratio − τ) / (1 − τ), 0, 1), τ = 0.8;
- `relevance` = mean over answer sentences of RePASs' own NLI entailment probability, with the question as premise (question ⇒ answer);
- `repaired` = (1 − penalty) × (RePASs + relevance) / 2.

| Answer type | LCS ratio | Penalty | Relevance | Repaired |
|---|---|---|---|---|
| Genuine (LLM, passages only) | 0.516 [0.479, 0.554] | 0.000 [0.000, 0.000] | 0.046 [0.013, 0.089] | 0.208 [0.168, 0.253] |
| Concatenated (verbatim obligations) | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] | 0.040 [0.017, 0.069] | 0.000 [0.000, 0.000] |
| Adversarial: negated | 0.951 [0.943, 0.957] | 0.753 [0.713, 0.787] | 0.016 [0.004, 0.032] | 0.006 [0.003, 0.010] |
| Adversarial: off-topic | 0.200 [0.181, 0.220] | 0.000 [0.000, 0.000] | 0.005 [0.004, 0.006] | 0.117 [0.101, 0.131] |

| Repaired: genuine − | Difference | Reading |
|---|---|---|
| Concatenated (verbatim obligations) | +0.208 [+0.168, +0.253] | genuine ranked above |
| Adversarial: negated | +0.202 [+0.162, +0.246] | genuine ranked above |
| Adversarial: off-topic | +0.091 [+0.050, +0.136] | genuine ranked above |

**Caveat:** τ and the repair were designed with the RIRAG concatenation finding in mind and are tested on the same 30 questions, so the result is optimistic. It is not validated on held-out data. The overlap penalty is aimed squarely at verbatim answers, so it also penalises a genuine answer that quotes heavily. The relevance term uses a small NLI model (`nli-deberta-v3-xsmall`) on question ⇒ sentence pairs, which is not what it was trained for.

## Examples (3 per type, seeded, from the rated answers)

Answer excerpts are limited to 25 words (P5-001 RBI-text policy); the full answers are pointers into the T4 answer files, rebuilt locally by `release/rehydrate.py`.

### Genuine (LLM, passages only)

- **T4Q06** — Can penal charges for a borrower’s default be subject to interest or be capitalized?  
  Passages: md_12968::p00044, md_12968::p00042, md_12968::p00050  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_genuine_v1.jsonl, T4Q06): “No. The RBI’s Master Directions require that any penalty imposed for a borrower’s default be levied only as a **penal charge**, not as “penal interest,” …”  
  RePASs 0.140 (entail 0.209, contra 0.989, coverage 0.200); repaired 0.070; human faithful 2, answers_question 2
- **T4Q16** — What minimum percentage of the bank’s loan portfolio must consist of loans up to ₹ 25 lakh, and does compliance assessment consider only new loans or the entire portfolio at the start of operations?  
  Passages: md_13120::p00052, md_13135::p00048, md_13135::p00047  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_genuine_v1.jsonl, T4Q16): “The Directions require that **at least 50 percent** of the bank’s loan portfolio be made up of loans and advances of up to ₹ 25 …”  
  RePASs 0.708 (entail 0.993, contra 0.035, coverage 0.167); repaired 0.586; human faithful 2, answers_question 2
- **T4Q21** — What factors must the Board of Directors evaluate when deciding on a dividend proposal for the bank?  
  Passages: md_13327::p00012, md_13327::p00018, md_13327::p00011  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_genuine_v1.jsonl, T4Q21): “When the Board of Directors reviews a proposal to declare a dividend, it must evaluate the following factors: 1. **The divergence in asset classification and …”  
  RePASs 0.268 (entail 0.367, contra 0.564, coverage 0.000); repaired 0.151; human faithful 2, answers_question 2

### Concatenated (verbatim obligations)

- **T4Q11** — Which portal must a UCB use to apply for permission to deploy its own POS terminals and act as a POS acquiring bank?  
  Passages: md_13033::p00083, md_13033::p00079, md_13033::p00080  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_concatenated_v1.jsonl, T4Q11): “A UCB desirous to deploy their own POS terminals and act as POS acquiring bank shall apply through PRAVAAH Portal (https://pravaah.rbi.org.in) to Department of Regulation, …”  
  RePASs 0.823 (entail 0.983, contra 0.013, coverage 0.500); repaired 0.000; human faithful 2, answers_question 2
- **T4Q15** — Where must the bank post the financing framework and the external reviewer’s opinion prior to its implementation?  
  Passages: md_13106::p00026, md_13119::p00081, md_13127::p01437  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_concatenated_v1.jsonl, T4Q15): “Before the implementation of FF, a copy of the FF shall be made available on the website of the bank along with the opinion of …”  
  RePASs 0.890 (entail 0.990, contra 0.320, coverage 1.000); repaired 0.000; human faithful 2, answers_question 2
- **T4Q28** — How soon after the annual audit must the bank notify the RBI of any serious audit lapses?  
  Passages: md_13621::p00092, md_13621::p00100, md_13621::p00021  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_concatenated_v1.jsonl, T4Q28): “The Board / ACB of the bank shall review the performance of SCAs / SAs on an annual basis. The bank shall report any serious …”  
  RePASs 0.834 (entail 0.986, contra 0.151, coverage 0.667); repaired 0.000; human faithful 2, answers_question 2

### Adversarial: negated

- **T4Q01** — Does a CIC need to have a Board‑approved IT outsourcing policy before outsourcing its IT services?  
  Passages: md_12925::p00067, md_12925::p00043, md_12925::p00044  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_adv_negated_v1.jsonl, T4Q01): “A CIC intending to outsource any of its IT services shall not put in place a comprehensive Board-approved IT outsourcing policy incorporating, inter alia, the …”  
  RePASs 0.002 (entail 0.004, contra 0.998, coverage 0.000); repaired 0.001; human faithful 0, answers_question 2
- **T4Q03** — What condition must be satisfied before an account opened through V‑CIP can be made operational?  
  Passages: md_12927::p00216, md_12927::p00154, md_12927::p00171  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_adv_negated_v1.jsonl, T4Q03): “The ARC shall not undertake the following EDD measures for non-face-to-face customer onboarding (other than customer onboarding in terms of paragraph 44): (2) If the …”  
  RePASs 0.018 (entail 0.053, contra 0.998, coverage 0.000); repaired 0.005; human faithful 0, answers_question 1
- **T4Q17** — What must the CI or CIC communicate to a complainant when a complaint is rejected?  
  Passages: md_13122::p00115, md_13132::p00185, md_13122::p00114  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_adv_negated_v1.jsonl, T4Q17): “(6) The complainant shall not be advised by the CI / CIC of the action taken on the complaint in all cases, including the cases …”  
  RePASs 0.003 (entail 0.006, contra 0.996, coverage 0.000); repaired 0.001; human faithful 0, answers_question 2

### Adversarial: off-topic

- **T4Q05** — What is the maximum risk weight allowed for a loan secured by a commercial mortgage at the portfolio cut‑off date?  
  Passages: md_12951::p00144, md_12951::p00145, md_12937::p00090  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_adv_offtopic_v1.jsonl, T4Q05): “The bank shall provide the highest level of 'read only' access to its Information Technology systems and manpower assistance, if required, to RBI’s officers. The …”  
  RePASs 0.219 (entail 0.063, contra 0.407, coverage 0.000); repaired 0.113; human faithful 0, answers_question 0
- **T4Q10** — What must a UCB introduce to address liquidity, interest rate, and currency risks?  
  Passages: md_13020::p00031, md_13020::p00072, md_13020::p00050  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_adv_offtopic_v1.jsonl, T4Q10): “Policies and Procedures Banks shall put in place comprehensive policy(ies) for all digital banking channels keeping in account all statutory and regulatory requirements (including on …”  
  RePASs 0.335 (entail 0.014, contra 0.008, coverage 0.000); repaired 0.175; human faithful 0, answers_question 0
- **T4Q13** — May the facility be limited to specific customer groups or classes?  
  Passages: md_13084::p00168, md_13063::p00196, md_13063::p00077  
  Answer (excerpt, ≤ 25 words; full text via t4_answers_adv_offtopic_v1.jsonl, T4Q13): “(2) ‘Current or Valid Credit Rating’ for the purpose of determining rated security means a credit rating granted by a credit rating agency in India, …”  
  RePASs 0.307 (entail 0.113, contra 0.193, coverage 0.000); repaired 0.161; human faithful 0, answers_question 0

## Limitations

- **n = 30 questions**, and 5–10 rated answers per type. Point estimates are unstable.
- **One rater.** No agreement statistic exists for the faithfulness labels.
- **LLM-drafted questions.** 2 of 30 were flagged `bad_question`; results without them are under Sensitivity.
- **The repair is not validated on held-out data** (see its caveat).
- **Model ids.** Questions and genuine answers: Groq `openai/gpt-oss-120b` (Gemini's free daily quota was exhausted). RePASs models as listed under Setup. A different generator could change the genuine scores.
- **Blinding is partial.** Type, scores and model were hidden, but LLM answers read differently from verbatim extracts (citations, paraphrase), so a rater can infer the rough type.
- **Sheet provenance.** The accepted sheet (sha256 `d2cc4209dce7…`, saved 2026-09-28T02:08:39) was declared by Karan as manually annotated, final and complete. An earlier submission (sha256 `54733120d88b…`) was not ingested because its minutes log post-dated its own arrival. Karan later described it as a mock file.
- **Genuine answers were scored as written,** including the model's 【…】 citation markers and markdown bold. These may depress their NLI scores. A rescoring with markers stripped was not run.
- RePASs was run on the CPU (their code), and its NLI inputs truncate long passages.

Generated 2026-09-28T21:56:23+00:00 by `scripts/run_t4.py analyze`. Raw per-answer scores: `data/benchmark/t4/t4_per_answer_v1.jsonl` and `t4_repass_scores_v1.jsonl`.
