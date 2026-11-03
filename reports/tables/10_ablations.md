# Table 10. Ablations A–C (ON − OFF, everything else at the final agentic setting)

| Ablation | Toggle | Measure | n | ON − OFF [95% CI] (reading) |
|---|---|---|---|---|
| A | class filter | T1 3-way flag Macro-F1 | 106 | -0.049 [-0.133, +0.036] (does not exclude 0) |
| A | class filter | T1 collapsed Macro-F1 | 106 | +0.015 [-0.059, +0.082] (does not exclude 0) |
| A | class filter | T2 nDCG@10, t2_xclass_t1 | 291 | +0.451 [+0.421, +0.481] (excludes 0 (above)) |
| A | class filter | T2 nDCG@10, t2_xclass_p2002 | 53 | +0.423 [+0.336, +0.514] (excludes 0 (above)) |
| A | class filter | T2 nDCG@10, t2_supp_p2003 | 25 | +0.171 [+0.072, +0.273] (excludes 0 (above)) |
| B | temporal filter | T3 status exact match | 52 | +0.462 [+0.327, +0.596] (excludes 0 (above)) |
| B | temporal filter | T3 supersession F1 | 52 | +1.000 [+1.000, +1.000] (excludes 0 (above)) |
| C | verifier | T1 3-way flag Macro-F1 | 106 | -0.068 [-0.132, -0.012] (excludes 0 (below)) |
| C | verifier | T1 coverage | 106 | -0.217 [-0.292, -0.142] (excludes 0 (below)) |
| C | verifier | T4 unsupported-sentence rate (NLI proxy), all 28 | 28 | -0.382 [-0.552, -0.214] (excludes 0 (below)) |
| C | verifier | T4 abstention rate | 28 | +0.393 [+0.214, +0.571] (excludes 0 (above)) |
| C | verifier | T4 RePASs composite | 28 | -0.055 [-0.121, +0.015] (does not exclude 0) |
| C | verifier | T4 unsupported-sentence rate, answered only (ON is 0 by construction) | 17 | -0.129 [-0.300, +0.0000] (does not exclude 0) |
| C | verifier | T4 RePASs composite, answered only | 17 | +0.040 [+0.0000, +0.113] (does not exclude 0) |

No correction for multiple comparisons; read each interval on its own.
