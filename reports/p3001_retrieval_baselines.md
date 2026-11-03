# P3-001 — T2 retrieval baselines

Four systems over all 76,188 paragraphs, scored on three human-labelled relevance sets. The sets are built and scored **separately and never pooled**. Each has a known bias, stated beside its results, and the biases point in different directions, so **no winner is declared across sets**.

## Protocol

- Metrics at cutoff 10: Recall@10 and MAP@10 (grade ≥ 1 is relevant), nDCG@10 with graded gain 2^grade - 1. Queries with no relevant paragraph are not scored and are counted.
- 95% CIs: percentile bootstrap, 2000 resamples of queries, seed 20260927. Every system on a set uses the same draws, so the paired differences are true paired bootstraps.
- Sensitivity: a clustered bootstrap that resamples source texts instead of queries (several T1 queries share one obligation text). Those CIs are in `p3001_metrics_v1.json` as `cluster_ci`; where they change a reading, the text says so.
- Systems keep their top 100. The query's own source paragraph is always excluded.
  - `bm25`: bm25s, method `lucene`, k1 = 1.5, b = 0.75, lower-case `[a-z0-9]+` tokens, no stemming or stopwords.
  - `dense`: BAAI/bge-base-en-v1.5 at revision `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a` (checked against the Hub), normalised, whitespace-collapsed text, no query instruction. Class-blind.
  - `hybrid_rrf`: RRF with k = 60 over the BM25 and dense rankings. A paragraph with a BM25 score of 0 gets no BM25 term.
  - `class_aware`: the same fusion, restricted to paragraphs whose Direction's entity class equals the query's target class. BM25 and dense are re-ranked inside that set. With no target class it equals `hybrid_rrf`, and the query is flagged.
  - `hybrid_minus_source_class` (diagnostic, added in P3-002): the class-blind fusion with every paragraph of the query's **own source class** removed, re-ranked inside what remains. It needs no target class. With no source class (P2-003's FAQ and enforcement queries come from outside the corpus) it equals `hybrid_rrf`, and the query is flagged.

## What the class-aware gain does and does not show

Relevance was labelled only for the counterpart **in the query's target class**. The task scored here is therefore *retrieval of the target-class counterpart*, and class-blind systems are partly disadvantaged by construction: the near-identical counterparts they return from other classes (and from the source class itself) count as misses. The class-aware gain shows the value of knowing the target class **for this task**. It is not a general class-blind vs class-aware verdict. `hybrid_minus_source_class` is a fairer diagnostic: it only stops the class-blind system from returning the source class's own paragraphs. The gap that remains between it and class-aware is what knowing the specific target class adds.

## t2_xclass_t1 — main set (P2-004 validated T1 items)

**Known bias:** Raters were shown the bge-base-en-v1.5 top-1/top-2 P2-002 candidates for each compared class (they could look up any paragraph), so the labelled counterparts favour the dense retriever.

- Queries: 412; scored (with a relevant paragraph): **n = 291**; without a relevant paragraph (not scored): 121; distinct source texts: 92.
- Relevant pairs: 291 (grade 2: 213, grade 1: 78).
- Hybrid minus source class: no source class for 0 queries (identical to hybrid there).
- Class-aware: no target class for 0 queries (identical to hybrid there). Relevant paragraphs outside the target class, so the class filter cannot reach them: 0 queries.

| System | Recall@10 | MAP@10 | nDCG@10 |
|---|---|---|---|
| BM25 | 0.821 [0.777, 0.863] | 0.344 [0.308, 0.379] | 0.458 [0.424, 0.492] |
| Dense (class-blind) | 0.773 [0.722, 0.821] | 0.311 [0.275, 0.346] | 0.421 [0.385, 0.455] |
| Hybrid RRF | 0.814 [0.766, 0.859] | 0.328 [0.292, 0.364] | 0.443 [0.408, 0.478] |
| Class-aware hybrid | 0.959 [0.935, 0.979] | 0.873 [0.839, 0.905] | 0.894 [0.864, 0.922] |
| Hybrid minus source class | 0.842 [0.797, 0.883] | 0.346 [0.310, 0.382] | 0.464 [0.429, 0.497] |

Each cell: mean [95% CI], n = 291.

**Paired differences** (same queries, same resamples):

| Comparison | Δ Recall@10 | Δ MAP@10 | Δ nDCG@10 |
|---|---|---|---|
| Hybrid RRF − BM25 | -0.007 [-0.034, +0.024] | -0.016 [-0.035, +0.003] | -0.015 [-0.033, +0.003] |
| Hybrid RRF − Dense (class-blind) | +0.041 [+0.010, +0.076] | +0.017 [+0.001, +0.034] | +0.022 [+0.008, +0.039] |
| Class-aware hybrid − Hybrid RRF | +0.144 [+0.106, +0.186] | +0.545 [+0.507, +0.583] | +0.451 [+0.421, +0.484] |
| BM25 − Dense (class-blind) | +0.048 [+0.010, +0.086] | +0.033 [+0.007, +0.062] | +0.037 [+0.013, +0.063] |
| Hybrid minus source class − Hybrid RRF | +0.027 [+0.010, +0.045] | +0.018 [+0.009, +0.030] | +0.021 [+0.011, +0.032] |
| Class-aware hybrid − Hybrid minus source class | +0.117 [+0.082, +0.155] | +0.527 [+0.490, +0.564] | +0.430 [+0.400, +0.462] |

Under the clustered bootstrap, these differences change whether their CI excludes 0: hybrid_rrf - bm25 MAP@10 (clustered CI [-0.032, -0.001]).

**By target class** (n ≥ 5), nDCG@10 [95% CI]:

| Target class | n | BM25 | Dense (class-blind) | Hybrid RRF | Class-aware hybrid | Hybrid minus source class |
|---|---|---|---|---|---|---|
| All India Financial Institutions | 24 | 0.48 [0.37, 0.57] | 0.38 [0.26, 0.51] | 0.41 [0.30, 0.53] | 0.90 [0.81, 0.96] | 0.46 [0.34, 0.58] |
| Commercial Banks | 49 | 0.44 [0.38, 0.51] | 0.48 [0.43, 0.55] | 0.46 [0.40, 0.52] | 0.91 [0.84, 0.97] | 0.47 [0.41, 0.54] |
| Local Area Banks | 37 | 0.52 [0.42, 0.62] | 0.49 [0.39, 0.59] | 0.54 [0.44, 0.65] | 0.93 [0.85, 0.99] | 0.57 [0.47, 0.67] |
| Non-Banking Financial Companies | 27 | 0.52 [0.39, 0.66] | 0.44 [0.32, 0.56] | 0.48 [0.35, 0.60] | 0.88 [0.75, 0.98] | 0.48 [0.35, 0.60] |
| Payments Banks | 32 | 0.48 [0.36, 0.60] | 0.39 [0.28, 0.52] | 0.44 [0.33, 0.55] | 0.92 [0.83, 0.98] | 0.45 [0.35, 0.57] |
| Regional Rural Banks | 25 | 0.30 [0.20, 0.42] | 0.27 [0.17, 0.37] | 0.33 [0.23, 0.44] | 0.80 [0.66, 0.91] | 0.40 [0.29, 0.51] |
| Rural Co-operative Banks | 23 | 0.39 [0.24, 0.53] | 0.34 [0.19, 0.49] | 0.39 [0.23, 0.54] | 0.86 [0.77, 0.95] | 0.39 [0.23, 0.54] |
| Small Finance Banks | 38 | 0.49 [0.40, 0.58] | 0.51 [0.42, 0.60] | 0.48 [0.39, 0.57] | 0.93 [0.86, 0.98] | 0.49 [0.40, 0.57] |
| Urban Co-operative Banks | 31 | 0.43 [0.34, 0.52] | 0.35 [0.26, 0.45] | 0.38 [0.29, 0.48] | 0.85 [0.74, 0.96] | 0.40 [0.31, 0.49] |

Not broken out (n < 5): Asset Reconstruction Companies (3), Credit Information Companies (2).

## t2_xclass_p2002 — P2-002 validation pairs

**Known bias:** Pairs were drawn by bge-base-en-v1.5 semantic-score bands (the same model and revision as the dense system), so the relevant paragraphs favour the dense retriever.

- Queries: 53; scored (with a relevant paragraph): **n = 53**; without a relevant paragraph (not scored): 0; distinct source texts: 53.
- Relevant pairs: 53 (grade 2: 34, grade 1: 19).
- Hybrid minus source class: no source class for 0 queries (identical to hybrid there).
- Class-aware: no target class for 0 queries (identical to hybrid there). Relevant paragraphs outside the target class, so the class filter cannot reach them: 0 queries.

| System | Recall@10 | MAP@10 | nDCG@10 |
|---|---|---|---|
| BM25 | 0.528 [0.377, 0.660] | 0.199 [0.127, 0.285] | 0.277 [0.194, 0.369] |
| Dense (class-blind) | 0.604 [0.472, 0.736] | 0.249 [0.174, 0.341] | 0.334 [0.252, 0.428] |
| Hybrid RRF | 0.585 [0.453, 0.717] | 0.236 [0.159, 0.328] | 0.319 [0.234, 0.414] |
| Class-aware hybrid | 0.830 [0.717, 0.925] | 0.713 [0.596, 0.826] | 0.741 [0.630, 0.844] |
| Hybrid minus source class | 0.642 [0.509, 0.774] | 0.243 [0.170, 0.335] | 0.337 [0.256, 0.429] |

Each cell: mean [95% CI], n = 53.

**Paired differences** (same queries, same resamples):

| Comparison | Δ Recall@10 | Δ MAP@10 | Δ nDCG@10 |
|---|---|---|---|
| Hybrid RRF − BM25 | +0.057 [-0.019, +0.132] | +0.036 [+0.007, +0.077] | +0.042 [+0.007, +0.083] |
| Hybrid RRF − Dense (class-blind) | -0.019 [-0.094, +0.038] | -0.013 [-0.060, +0.036] | -0.015 [-0.056, +0.027] |
| Class-aware hybrid − Hybrid RRF | +0.245 [+0.132, +0.358] | +0.477 [+0.379, +0.577] | +0.423 [+0.336, +0.511] |
| BM25 − Dense (class-blind) | -0.075 [-0.170, +0.000] | -0.049 [-0.118, +0.014] | -0.057 [-0.118, +0.001] |
| Hybrid minus source class − Hybrid RRF | +0.057 [+0.000, +0.132] | +0.008 [+0.001, +0.016] | +0.019 [+0.002, +0.039] |
| Class-aware hybrid − Hybrid minus source class | +0.189 [+0.094, +0.302] | +0.469 [+0.374, +0.565] | +0.404 [+0.324, +0.484] |

The clustered bootstrap does not change whether any paired CI excludes 0.

**By target class** (n ≥ 5), nDCG@10 [95% CI]:

| Target class | n | BM25 | Dense (class-blind) | Hybrid RRF | Class-aware hybrid | Hybrid minus source class |
|---|---|---|---|---|---|---|
| Local Area Banks | 6 | 0.36 [0.12, 0.64] | 0.45 [0.12, 0.81] | 0.31 [0.07, 0.64] | 0.67 [0.33, 1.00] | 0.36 [0.12, 0.64] |
| Payments Banks | 9 | 0.25 [0.10, 0.41] | 0.31 [0.10, 0.53] | 0.34 [0.14, 0.55] | 0.90 [0.75, 1.00] | 0.38 [0.20, 0.57] |
| Regional Rural Banks | 6 | 0.32 [0.11, 0.52] | 0.39 [0.22, 0.54] | 0.37 [0.20, 0.53] | 0.82 [0.62, 1.00] | 0.38 [0.21, 0.53] |
| Small Finance Banks | 9 | 0.30 [0.11, 0.54] | 0.35 [0.13, 0.58] | 0.31 [0.11, 0.55] | 0.59 [0.33, 0.85] | 0.31 [0.11, 0.55] |
| Urban Co-operative Banks | 6 | 0.37 [0.13, 0.64] | 0.37 [0.22, 0.48] | 0.46 [0.22, 0.72] | 1.00 [1.00, 1.00] | 0.51 [0.36, 0.72] |

Not broken out (n < 5): All India Financial Institutions (4), Asset Reconstruction Companies (3), Commercial Banks (2), Credit Information Companies (3), Non-Banking Financial Companies (1), Rural Co-operative Banks (4).

## t2_supp_p2003 — P2-003 FAQ / enforcement alignment rows

**Known bias:** Candidates shown to the rater were ranked by TF-IDF, which favours BM25 (the rater could enter any paragraph id of the Direction).

- Queries: 25; scored (with a relevant paragraph): **n = 25**; without a relevant paragraph (not scored): 0; distinct source texts: 25.
- Relevant pairs: 29 (grade 2: 29, grade 1: 0).
- Hybrid minus source class: no source class for 25 queries (identical to hybrid there).
- Class-aware: no target class for 8 queries (identical to hybrid there). Relevant paragraphs outside the target class, so the class filter cannot reach them: 2 queries.
- Query text basis: {'enforcement_charges': 18, 'faq_qa': 7}.
- **Small n (25).** The CIs are wide; read the direction, not the point estimates.

| System | Recall@10 | MAP@10 | nDCG@10 |
|---|---|---|---|
| BM25 | 0.800 [0.640, 0.940] | 0.548 [0.381, 0.706] | 0.616 [0.462, 0.761] |
| Dense (class-blind) | 0.500 [0.320, 0.680] | 0.309 [0.159, 0.483] | 0.362 [0.212, 0.528] |
| Hybrid RRF | 0.680 [0.500, 0.840] | 0.437 [0.276, 0.612] | 0.504 [0.348, 0.673] |
| Class-aware hybrid | 0.820 [0.660, 0.960] | 0.612 [0.468, 0.771] | 0.675 [0.535, 0.811] |
| Hybrid minus source class | 0.680 [0.500, 0.840] | 0.437 [0.276, 0.612] | 0.504 [0.348, 0.673] |

Each cell: mean [95% CI], n = 25.

**Paired differences** (same queries, same resamples):

| Comparison | Δ Recall@10 | Δ MAP@10 | Δ nDCG@10 |
|---|---|---|---|
| Hybrid RRF − BM25 | -0.120 [-0.280, +0.040] | -0.111 [-0.258, +0.011] | -0.112 [-0.261, +0.013] |
| Hybrid RRF − Dense (class-blind) | +0.180 [+0.040, +0.340] | +0.128 [+0.039, +0.237] | +0.143 [+0.059, +0.241] |
| Class-aware hybrid − Hybrid RRF | +0.140 [-0.020, +0.320] | +0.176 [+0.078, +0.287] | +0.171 [+0.074, +0.272] |
| BM25 − Dense (class-blind) | +0.300 [+0.140, +0.480] | +0.239 [+0.097, +0.401] | +0.254 [+0.122, +0.405] |
| Hybrid minus source class − Hybrid RRF | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] | +0.000 [+0.000, +0.000] |
| Class-aware hybrid − Hybrid minus source class | +0.140 [-0.020, +0.320] | +0.176 [+0.078, +0.287] | +0.171 [+0.074, +0.272] |

The clustered bootstrap does not change whether any paired CI excludes 0.

**By target class** (n ≥ 5), nDCG@10 [95% CI]:

| Target class | n | BM25 | Dense (class-blind) | Hybrid RRF | Class-aware hybrid | Hybrid minus source class |
|---|---|---|---|---|---|---|
| Non-Banking Financial Companies | 5 | 0.59 [0.31, 0.87] | 0.33 [0.06, 0.67] | 0.59 [0.31, 0.86] | 0.85 [0.70, 1.00] | 0.59 [0.31, 0.86] |

Not broken out (n < 5): Commercial Banks (4), Credit Information Companies (3), Regional Rural Banks (1), Rural Co-operative Banks (2), Urban Co-operative Banks (2).

## Reading across sets

Two sets favour dense by construction (their candidates or pairs were chosen with the same bge model), and one favours BM25 (its candidates came from TF-IDF). A system that wins on one of these sets may only be winning because of that set's bias. These are baselines, not a ranking of methods. The class-aware − hybrid row previews Ablation A (class filter on vs off) on each set separately.

The T1-derived queries ask for the counterpart **in one named class**. A class-blind system that returns a correct counterpart from a different class gets no credit, because only the named class's counterpart was labelled. That is part of what the class-aware row measures.

## Environment

- Machine: Apple M5 (arm64); OS: macOS-26.3.1-arm64-arm-64bit-Mach-O; Python 3.14.3.
- Packages: numpy 2.4.3, scipy 1.17.1, torch 2.11.0, transformers 5.4.0, sentence-transformers 6.1.0, huggingface-hub 1.8.0, bm25s 0.3.11, requests 2.33.0, python-dotenv 1.2.2, pytest 9.1.1, PyYAML 6.0.3.
- Embedding device: mps. 76188 paragraphs embedded fresh, locally, in 37.7 min (projected 23.4 min); Kaggle P2-002 embeddings not reused. Truncated at 512 tokens: 688 paragraphs.
- LLM (configured; not used by any baseline here): `llm.model` = `gemini-3.8-flash`, `llm.long_context_model` = `gemini-3.8-flash` (Gemini); fallback `openai/gpt-oss-120b` (Groq). Version strings from the list endpoints: {'gemini-3.8-flash': '3.0', 'openai/gpt-oss-120b': None}.

Generated 2026-09-27T18:20:08+00:00 by `scripts/run_p3001.py score`.
