# Table 7. T1 systems (106 validated items; long-context on its scored items)

3-way flag Macro-F1 over shared / class-specific / absent (a predicted `ambiguous` is wrong); collapsed = absent vs present. P2-002 cannot express shared vs class-specific, so 3-way F1 favours the LLM systems by design; collapsed F1 is the fair comparison. CIs: 2,000 item resamples.

| System | n | 3-way flag Macro-F1 | Collapsed Macro-F1 | Judgement Macro-F1 | F1 same / different / none | Coverage |
|---|---|---|---|---|---|---|
| Majority (in-sample) | 106 | 0.219 [0.186, 0.246] | 0.465 [0.445, 0.483] | 0.227 [0.202, 0.248] | 0.682 / 0.000 / 0.000 (point estimates) | 1.000 [1.000, 1.000] |
| P2-002 candidates | 106 | 0.459 [0.381, 0.520] | 0.784 [0.671, 0.877] | 0.550 [0.512, 0.583] | 0.841 / 0.000 / 0.809 (point estimates) | 1.000 [1.000, 1.000] |
| Class-blind LLM | 106 | 0.602 [0.497, 0.700] | 0.766 [0.647, 0.873] | 0.664 [0.597, 0.726] | 0.884 / 0.321 / 0.786 (point estimates) | 1.000 [1.000, 1.000] |
| Class-aware LLM | 106 | 0.551 [0.445, 0.639] | 0.808 [0.685, 0.908] | 0.609 [0.553, 0.667] | 0.887 / 0.154 / 0.785 (point estimates) | 0.991 [0.972, 1.000] |
| Final agentic | 106 | 0.483 [0.385, 0.568] | 0.710 [0.590, 0.815] | 0.521 [0.470, 0.570] | 0.745 / 0.047 / 0.773 (point estimates) | 0.774 [0.689, 0.849] |
| Class-blind + verifier | 106 | 0.532 [0.431, 0.625] | 0.695 [0.572, 0.802] | 0.578 [0.520, 0.639] | 0.763 / 0.176 / 0.796 (point estimates) | 0.792 [0.708, 0.868] |
| Long-context LLM (100K cap) | 102 | 0.509 [0.408, 0.600] | 0.819 [0.691, 0.917] | 0.551 [0.496, 0.604] | 0.838 / 0.074 / 0.741 (point estimates) | 1.000 [1.000, 1.000] |

## Paired differences (same items)

| Comparison | n | Δ 3-way F1 | Δ collapsed F1 | Δ coverage |
|---|---|---|---|---|
| Ablation A (verifier on): final agentic − class-blind + verifier | 106 | -0.049 [-0.133, +0.036] (does not exclude 0) | +0.015 [-0.059, +0.082] (does not exclude 0) | -0.019 [-0.075, +0.038] (does not exclude 0) |
| Class filter, no verifier: class-aware − class-blind | 106 | -0.050 [-0.133, +0.027] (does not exclude 0) | +0.043 [-0.030, +0.109] (does not exclude 0) | -0.009 [-0.028, +0.0000] (does not exclude 0) |
| Ablation C on T1: final agentic − class-aware | 106 | -0.068 [-0.132, -0.012] (excludes 0 (below)) | -0.099 [-0.151, -0.053] (excludes 0 (below)) | -0.217 [-0.292, -0.142] (excludes 0 (below)) |
| Verifier, class-blind: ablation A − class-blind | 106 | -0.069 [-0.129, -0.014] (excludes 0 (below)) | -0.071 [-0.105, -0.041] (excludes 0 (below)) | -0.208 [-0.292, -0.132] (excludes 0 (below)) |
| Class-blind LLM − P2-002 candidates | 106 | +0.143 [+0.054, +0.232] (excludes 0 (above)) | -0.019 [-0.114, +0.072] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Class-aware LLM − P2-002 candidates | 106 | +0.092 [-0.002, +0.183] (does not exclude 0) | +0.024 [-0.096, +0.135] (does not exclude 0) | -0.009 [-0.028, +0.0000] (does not exclude 0) |
| Final agentic − P2-002 candidates | 106 | +0.024 [-0.058, +0.106] (does not exclude 0) | -0.074 [-0.192, +0.036] (does not exclude 0) | -0.226 [-0.311, -0.151] (excludes 0 (below)) |
| Class-blind + verifier − P2-002 candidates | 106 | +0.073 [-0.006, +0.157] (does not exclude 0) | -0.089 [-0.186, +0.006] (does not exclude 0) | -0.208 [-0.292, -0.132] (excludes 0 (below)) |
| Long-context − majority (same items) | 102 | +0.290 [+0.188, +0.376] (excludes 0 (above)) | +0.353 [+0.212, +0.454] (excludes 0 (above)) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context − P2-002 candidates (same items) | 102 | +0.057 [-0.044, +0.163] (does not exclude 0) | +0.045 [-0.093, +0.176] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context − class-blind (same items) | 102 | -0.097 [-0.197, +0.010] (does not exclude 0) | +0.054 [-0.047, +0.159] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Long-context − class-aware (same items) | 102 | -0.035 [-0.128, +0.063] (does not exclude 0) | +0.023 [-0.088, +0.142] (does not exclude 0) | +0.010 [+0.0000, +0.039] (does not exclude 0) |
| Long-context − final agentic (same items) | 102 | +0.030 [-0.067, +0.129] (does not exclude 0) | +0.126 [+0.016, +0.240] (excludes 0 (above)) | +0.235 [+0.157, +0.324] (excludes 0 (above)) |
| Long-context − class-blind + verifier (same items) | 102 | -0.020 [-0.131, +0.094] (does not exclude 0) | +0.127 [+0.018, +0.234] (excludes 0 (above)) | +0.216 [+0.137, +0.294] (excludes 0 (above)) |

## Every system on the long-context scored items (n = 102)

| System | n | 3-way flag Macro-F1 | Collapsed Macro-F1 | Judgement Macro-F1 | F1 same / different / none | Coverage |
|---|---|---|---|---|---|---|
| Majority (in-sample) | 102 | 0.219 [0.188, 0.247] | 0.466 [0.446, 0.482] | 0.228 [0.204, 0.250] | 0.684 / 0.000 / 0.000 (point estimates) | 1.000 [1.000, 1.000] |
| P2-002 candidates | 102 | 0.452 [0.371, 0.515] | 0.774 [0.658, 0.873] | 0.548 [0.509, 0.581] | 0.842 / 0.000 / 0.801 (point estimates) | 1.000 [1.000, 1.000] |
| Class-blind LLM | 102 | 0.606 [0.491, 0.700] | 0.765 [0.635, 0.868] | 0.668 [0.601, 0.729] | 0.888 / 0.336 / 0.780 (point estimates) | 1.000 [1.000, 1.000] |
| Class-aware LLM | 102 | 0.544 [0.431, 0.641] | 0.796 [0.658, 0.902] | 0.607 [0.548, 0.668] | 0.886 / 0.157 / 0.776 (point estimates) | 0.990 [0.961, 1.000] |
| Final agentic | 102 | 0.479 [0.377, 0.575] | 0.693 [0.559, 0.808] | 0.517 [0.467, 0.568] | 0.740 / 0.049 / 0.763 (point estimates) | 0.765 [0.676, 0.843] |
| Class-blind + verifier | 102 | 0.529 [0.421, 0.627] | 0.692 [0.556, 0.800] | 0.577 [0.517, 0.641] | 0.761 / 0.180 / 0.791 (point estimates) | 0.784 [0.706, 0.863] |
| Long-context LLM (100K cap) | 102 | 0.509 [0.408, 0.600] | 0.819 [0.691, 0.917] | 0.551 [0.496, 0.604] | 0.838 / 0.074 / 0.741 (point estimates) | 1.000 [1.000, 1.000] |

Prompt tokens: scored: n = 102, median 71727, range 6451–100008; unscored: n = 4, median 95910, range 27269–99863.
Gold-retention accounting: 102 scored = 82 all gold kept + 7 at least one cut + 13 with no gold matched paragraph.


## Appendix: long-context at the 150K cap — superseded by the 100K rerun, shown for completeness (n = 47)

| System | n | 3-way flag Macro-F1 | Collapsed Macro-F1 | Judgement Macro-F1 | F1 same / different / none | Coverage |
|---|---|---|---|---|---|---|
| Long-context LLM, 150K cap (superseded) | 47 | 0.515 [0.374, 0.626] | 0.866 [0.664, 1.000] | 0.539 [0.457, 0.611] | 0.833 / 0.041 / 0.742 (point estimates) | 1.000 [1.000, 1.000] |
| Majority (in-sample) | 47 | 0.206 [0.153, 0.249] | 0.472 [0.440, 0.495] | 0.223 [0.182, 0.257] | 0.669 / 0.000 / 0.000 (point estimates) | 1.000 [1.000, 1.000] |
| P2-002 candidates | 47 | 0.464 [0.328, 0.553] | 0.802 [0.598, 0.949] | 0.539 [0.472, 0.595] | 0.821 / 0.000 / 0.796 (point estimates) | 1.000 [1.000, 1.000] |
| Class-blind LLM | 47 | 0.631 [0.465, 0.770] | 0.774 [0.570, 0.925] | 0.672 [0.565, 0.773] | 0.916 / 0.361 / 0.739 (point estimates) | 1.000 [1.000, 1.000] |
| Class-aware LLM | 47 | 0.560 [0.403, 0.696] | 0.802 [0.598, 0.936] | 0.586 [0.494, 0.689] | 0.886 / 0.151 / 0.722 (point estimates) | 1.000 [1.000, 1.000] |
| Final agentic | 47 | 0.518 [0.370, 0.642] | 0.658 [0.452, 0.814] | 0.504 [0.429, 0.571] | 0.753 / 0.041 / 0.719 (point estimates) | 0.766 [0.638, 0.872] |
| Class-blind + verifier | 47 | 0.502 [0.353, 0.617] | 0.666 [0.461, 0.821] | 0.532 [0.450, 0.618] | 0.750 / 0.082 / 0.764 (point estimates) | 0.723 [0.596, 0.851] |

| Long-context (150K) − | Δ 3-way F1 | Δ collapsed F1 | Δ coverage |
|---|---|---|---|
| Majority (in-sample) | +0.309 [+0.163, +0.411] (excludes 0 (above)) | +0.394 [+0.175, +0.534] (excludes 0 (above)) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| P2-002 candidates | +0.052 [-0.021, +0.145] (does not exclude 0) | +0.064 [-0.061, +0.200] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Class-blind LLM | -0.116 [-0.223, -0.0003] (excludes 0 (below)) | +0.092 [+0.0000, +0.204] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Class-aware LLM | -0.045 [-0.149, +0.050] (does not exclude 0) | +0.064 [-0.054, +0.200] (does not exclude 0) | +0.000 [+0.0000, +0.0000] (does not exclude 0) |
| Final agentic | -0.002 [-0.096, +0.093] (does not exclude 0) | +0.208 [+0.099, +0.349] (excludes 0 (above)) | +0.234 [+0.128, +0.362] (excludes 0 (above)) |
| Class-blind + verifier | +0.013 [-0.092, +0.135] (does not exclude 0) | +0.200 [+0.099, +0.334] (excludes 0 (above)) | +0.277 [+0.149, +0.404] (excludes 0 (above)) |
