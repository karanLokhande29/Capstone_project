# P3-001 — T1 baselines on the validated set

Scored on `t1_validated_v1.jsonl`: **106 items** and **412 (item, compared class) judgements**. Gold flags: {'class-specific': 40, 'shared': 52, 'absent': 14}. Gold judgements: {'different': 78, 'same': 213, 'none': 121}.

95% CIs: percentile bootstrap, 2000 resamples of **items**, seed 20260927. A judgement resample takes every compared class of each drawn item.

## Baselines

- **Majority class.** Always predicts flag `shared` and judgement `same`: the most frequent labels **of the validated set itself**. That is in-sample, so the baseline is slightly optimistic by construction.
- **P2-002 candidate labels ("dense within-family").** P2-002's bge within-family match status per compared class. `matched` means a counterpart exists but can't say `same` or `different`; `below_threshold` reads as `none`. The flag is derived over the item's compared classes, as P2-004 does: `shared_or_class_specific` if any class matched, else `absent`.

### How the P2-002 baseline is scored

Its predictions are coarser than the gold labels, so it is scored three ways:
1. **Native (collapsed).** Gold is collapsed to what the baseline can express: flag `absent` vs `present`, judgement `none` vs `counterpart`. This is the fair comparison. The majority baseline is scored the same way.
2. **Fixed mapping, 3 labels.** `shared_or_class_specific` → `shared` and `counterpart` → `same`: the validated set's most frequent non-absent flag and most frequent counterpart judgement (in-sample, like the majority baseline).
3. **Oracle upper bound, 3 labels.** An undecided prediction counts as correct whenever gold is one of the labels it covers. It is a ceiling, not a result.

## Flag (`differential_flag`)

| Baseline / scoring | Macro-F1 | F1 shared | F1 class-specific | F1 absent | Accuracy |
|---|---|---|---|---|---|
| Majority | 0.219 [0.189, 0.246] | 0.658 [0.568, 0.738] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.491 |
| P2-002, fixed mapping | 0.459 [0.382, 0.518] | 0.727 [0.639, 0.808] | 0.000 [0.000, 0.000] | 0.650 [0.452, 0.800] | 0.575 |
| P2-002, oracle upper bound | 0.824 [0.737, 0.897] | 0.960 [0.915, 0.990] | 0.861 [0.767, 0.933] | 0.650 [0.452, 0.800] | 0.868 |

n = 106 items.

Collapsed (absent vs present):

| Baseline | Macro-F1 | F1 absent | F1 present | Accuracy |
|---|---|---|---|---|
| Majority | 0.465 [0.445, 0.480] | 0.000 [0.000, 0.000] | 0.929 [0.890, 0.961] | 0.868 |
| P2-002 (native) | 0.784 [0.675, 0.877] | 0.650 [0.452, 0.800] | 0.919 [0.872, 0.955] | 0.868 |

## Per-class judgements (`per_class_judgement`)

| Baseline / scoring | Macro-F1 | F1 same | F1 different | F1 none | Accuracy |
|---|---|---|---|---|---|
| Majority | 0.227 [0.204, 0.249] | 0.682 [0.612, 0.747] | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | 0.517 |
| P2-002, fixed mapping | 0.550 [0.512, 0.582] | 0.841 [0.780, 0.895] | 0.000 [0.000, 0.000] | 0.809 [0.728, 0.875] | 0.750 |
| P2-002, oracle upper bound | 0.832 [0.772, 0.886] | 0.956 [0.917, 0.985] | 0.731 [0.602, 0.835] | 0.809 [0.728, 0.875] | 0.869 |

n = 412 judgements from 106 items.

Collapsed (none vs counterpart):

| Baseline | Macro-F1 | F1 none | F1 counterpart | Accuracy |
|---|---|---|---|---|
| Majority | 0.414 [0.387, 0.437] | 0.000 [0.000, 0.000] | 0.828 [0.774, 0.874] | 0.706 |
| P2-002 (native) | 0.854 [0.799, 0.904] | 0.809 [0.728, 0.875] | 0.900 [0.858, 0.938] | 0.869 |

## Confusion matrices

Majority, flag (rows gold, columns predicted):

| gold \ pred | shared | class-specific | absent |
|---|---|---|---|
| shared | 52 | 0 | 0 |
| class-specific | 40 | 0 | 0 |
| absent | 14 | 0 | 0 |

P2-002, flag (raw predictions) (rows gold, columns predicted):

| gold \ pred | shared | class-specific | absent | shared_or_class_specific |
|---|---|---|---|---|
| shared | 0 | 0 | 4 | 48 |
| class-specific | 0 | 0 | 9 | 31 |
| absent | 0 | 0 | 13 | 1 |

Majority, judgement (rows gold, columns predicted):

| gold \ pred | same | different | none |
|---|---|---|---|
| same | 213 | 0 | 0 |
| different | 78 | 0 | 0 |
| none | 121 | 0 | 0 |

P2-002, judgement (raw predictions) (rows gold, columns predicted):

| gold \ pred | same | different | none | counterpart |
|---|---|---|---|---|
| same | 0 | 0 | 18 | 195 |
| different | 0 | 0 | 29 | 49 |
| none | 0 | 0 | 114 | 7 |

## Caveats

- The P2-002 candidates are not independent of the gold labels: raters saw the bge top-1/top-2 candidates while labelling, so agreement with this baseline may be inflated.
- n = 106 items is small. The per-label F1 CIs for the rarer labels are wide.
- The long-context LLM T1 baseline comes in P4-001. The configured model ids are in `p3001_retrieval_baselines.md` (Environment).

Inputs (sha256): {'t1_validated_v1.jsonl': '67d471a13a266a12fbb55f41500c71c39f1322a0d847011a43be4cc55af45fc5', 't1_candidate_benchmark_v1.jsonl': '8463e9951a7c207db9bbe5d91f438191371a7d2f67ac630b53403e27990671cd'}. Generated 2026-09-27T17:30:20+00:00 by `scripts/run_p3001.py t1`.
