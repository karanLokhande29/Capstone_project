# Table 6. T2 retrieval baselines (P3-001) and the P4 pipeline retrieval stage

Relevance was labelled only for the counterpart in the query's target class, so class-blind systems are partly disadvantaged by construction. `hybrid_minus_source_class` is the fairer class-blind comparison. Metrics at cutoff 10; 95% CIs from 2,000 query resamples.

## t2_xclass_t1 (n = 291)

**Bias:** Raters were shown the bge-base-en-v1.5 top-1/top-2 P2-002 candidates for each compared class (they could look up any paragraph), so the labelled counterparts favour the dense retriever.

| System | Recall@10 | MAP@10 | nDCG@10 |
|---|---|---|---|
| bm25 | 0.821 [0.777, 0.863] | 0.344 [0.308, 0.379] | 0.458 [0.424, 0.492] |
| dense | 0.773 [0.722, 0.821] | 0.311 [0.275, 0.346] | 0.421 [0.385, 0.455] |
| hybrid_rrf | 0.814 [0.766, 0.859] | 0.328 [0.292, 0.364] | 0.443 [0.408, 0.478] |
| class_aware | 0.959 [0.935, 0.979] | 0.873 [0.839, 0.905] | 0.894 [0.864, 0.922] |
| hybrid_minus_source_class | 0.842 [0.797, 0.883] | 0.346 [0.310, 0.382] | 0.464 [0.429, 0.497] |

Paired differences, nDCG@10:

| Comparison | Δ nDCG@10 |
|---|---|
| hybrid_rrf - bm25 | -0.015 [-0.033, +0.003] (does not exclude 0) |
| hybrid_rrf - dense | +0.022 [+0.008, +0.039] (excludes 0 (above)) |
| class_aware - hybrid_rrf | +0.451 [+0.421, +0.484] (excludes 0 (above)) |
| bm25 - dense | +0.037 [+0.013, +0.063] (excludes 0 (above)) |
| hybrid_minus_source_class - hybrid_rrf | +0.021 [+0.011, +0.032] (excludes 0 (above)) |
| class_aware - hybrid_minus_source_class | +0.430 [+0.400, +0.462] (excludes 0 (above)) |

P4 pipeline retrieval stage (class filter on vs off, ablation A): ON 0.894 [0.866, 0.923], OFF 0.443 [0.410, 0.478], ON − OFF +0.451 [+0.421, +0.481] (excludes 0 (above)).

## t2_xclass_p2002 (n = 53)

**Bias:** Pairs were drawn by bge-base-en-v1.5 semantic-score bands (the same model and revision as the dense system), so the relevant paragraphs favour the dense retriever.

| System | Recall@10 | MAP@10 | nDCG@10 |
|---|---|---|---|
| bm25 | 0.528 [0.377, 0.660] | 0.199 [0.127, 0.285] | 0.277 [0.194, 0.369] |
| dense | 0.604 [0.472, 0.736] | 0.249 [0.174, 0.341] | 0.334 [0.252, 0.428] |
| hybrid_rrf | 0.585 [0.453, 0.717] | 0.236 [0.159, 0.328] | 0.319 [0.234, 0.414] |
| class_aware | 0.830 [0.717, 0.925] | 0.713 [0.596, 0.826] | 0.741 [0.630, 0.844] |
| hybrid_minus_source_class | 0.642 [0.509, 0.774] | 0.243 [0.170, 0.335] | 0.337 [0.256, 0.429] |

Paired differences, nDCG@10:

| Comparison | Δ nDCG@10 |
|---|---|
| hybrid_rrf - bm25 | +0.042 [+0.007, +0.083] (excludes 0 (above)) |
| hybrid_rrf - dense | -0.015 [-0.056, +0.027] (does not exclude 0) |
| class_aware - hybrid_rrf | +0.423 [+0.336, +0.511] (excludes 0 (above)) |
| bm25 - dense | -0.057 [-0.118, +0.001] (does not exclude 0) |
| hybrid_minus_source_class - hybrid_rrf | +0.019 [+0.002, +0.039] (excludes 0 (above)) |
| class_aware - hybrid_minus_source_class | +0.404 [+0.324, +0.484] (excludes 0 (above)) |

P4 pipeline retrieval stage (class filter on vs off, ablation A): ON 0.741 [0.634, 0.848], OFF 0.319 [0.233, 0.411], ON − OFF +0.423 [+0.336, +0.514] (excludes 0 (above)).

## t2_supp_p2003 (n = 25)

**Bias:** Candidates shown to the rater were ranked by TF-IDF, which favours BM25 (the rater could enter any paragraph id of the Direction).

| System | Recall@10 | MAP@10 | nDCG@10 |
|---|---|---|---|
| bm25 | 0.800 [0.640, 0.940] | 0.548 [0.381, 0.706] | 0.616 [0.462, 0.761] |
| dense | 0.500 [0.320, 0.680] | 0.309 [0.159, 0.483] | 0.362 [0.212, 0.528] |
| hybrid_rrf | 0.680 [0.500, 0.840] | 0.437 [0.276, 0.612] | 0.504 [0.348, 0.673] |
| class_aware | 0.820 [0.660, 0.960] | 0.612 [0.468, 0.771] | 0.675 [0.535, 0.811] |
| hybrid_minus_source_class | 0.680 [0.500, 0.840] | 0.437 [0.276, 0.612] | 0.504 [0.348, 0.673] |

Paired differences, nDCG@10:

| Comparison | Δ nDCG@10 |
|---|---|
| hybrid_rrf - bm25 | -0.112 [-0.261, +0.013] (does not exclude 0) |
| hybrid_rrf - dense | +0.143 [+0.059, +0.241] (excludes 0 (above)) |
| class_aware - hybrid_rrf | +0.171 [+0.074, +0.272] (excludes 0 (above)) |
| bm25 - dense | +0.254 [+0.122, +0.405] (excludes 0 (above)) |
| hybrid_minus_source_class - hybrid_rrf | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| class_aware - hybrid_minus_source_class | +0.171 [+0.074, +0.272] (excludes 0 (above)) |

P4 pipeline retrieval stage (class filter on vs off, ablation A): ON 0.675 [0.527, 0.814], OFF 0.504 [0.349, 0.666], ON − OFF +0.171 [+0.072, +0.273] (excludes 0 (above)).

