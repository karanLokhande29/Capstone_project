# P1-004 A1 — Pilot annotation file validation

_Generated 2026-09-25T06:49:07+00:00 on branch `wip/P1-004`, read-only: no annotation file was modified._

**Blindness.** Karan's blind pass 2 is still ahead, so this report carries **no labels, rationales or notes from any rater** — only row ids, per-row status, and aggregate counts. Per-item content appears for the first time in Part D's adjudication file, after pass 2.

## Declared provenance (from `docs/prompts/P1-004.md`, filled in by Karan 2026-09-25)

| Rater | File | `label_source` | Minutes | Basis |
|---|---|---|---|---|
| karan | `annotation_karan.csv` | `manual` | 65 | `recalled_estimate` |
| akash | `annotation_akash.csv` | `manual` | 45 | `recalled_estimate` |
| meer | `annotation_meer.csv` | `manual` | 50 | `recalled_estimate` |

Every minutes figure is a **recalled estimate, not a timed measurement**. Every per-item time derived from them is labelled accordingly, and any Phase 2 size projection built on them must say so. The first measured figure comes from Part D, where pass 2 is timed automatically.

## 1. Structural validation

Each file checked against `data/benchmark/pilot_candidates.jsonl` and `data/metadata/entity_classes.json` for: header, the 7 context columns unchanged, no duplicate `label_id`, canonical class names only, valid flags, and no flag without `applies_to`.

| File | Rows | Header | Context cols unchanged | Duplicate ids | Non-canonical classes | Invalid flags | Flag w/o applies_to | BOM |
|---|---|---|---|---|---|---|---|---|
| `annotation_karan.csv` | 18 | OK | yes | 0 | 0 | 0 | 0 | present (handled) |
| `annotation_akash.csv` | 18 | OK | yes | 0 | 0 | 0 | 0 | present (handled) |
| `annotation_meer.csv` | 18 | OK | yes | 0 | 0 | 0 | 0 | present (handled) |

**Result: all three files pass.** No structural error, so nothing is blocked under §AB.

All three carry a UTF-8 BOM (Excel's "CSV UTF-8" export). This is read correctly — the P1-005 ingest opens task files as `utf-8-sig`, which is the D5 repair doing its job. Note that §G of the prompt recorded Karan's file as having no BOM; it has one now, which means the file was re-saved through a spreadsheet after that observation. No content consequence.

## 2. Per-row status

`voted` = both judgment columns filled. `not_obligation` = both blank with a note. `blank` = untouched, read as "not yet done" and excluded from every statistic.

| `label_id` | karan | akash | meer |
|---|---|---|---|
| `t1_pilot_md_12061::p00055_00` | voted | voted | voted |
| `t1_pilot_md_12927::p00046_00` | voted | voted | voted |
| `t1_pilot_md_12958::p00018_00` | voted | voted | voted |
| `t1_pilot_md_12983::p01671_00` | voted | voted | voted |
| `t1_pilot_md_13042::p00070_00` | voted | voted | voted |
| `t1_pilot_md_13042::p00070_01` | voted | voted | voted |
| `t1_pilot_md_13042::p00070_02` | voted | voted | voted |
| `t1_pilot_md_13361::p00015_00` | voted | voted | voted |
| `t1_pilot_md_13361::p00015_01` | voted | voted | voted |
| `t1_pilot_md_13525::p00050_00` | voted | voted | voted |
| `t1_pilot_md_13525::p00050_01` | voted | voted | voted |
| `t1_pilot_md_13526::p00022_00` | voted | voted | voted |
| `t1_pilot_md_13526::p00022_01` | voted | voted | voted |
| `t1_pilot_md_13582::p00008_00` | not_obligation | not_obligation | not_obligation |
| `t1_pilot_md_13633::p00074_00` | voted | voted | voted |
| `t1_pilot_md_13633::p00074_01` | voted | voted | voted |
| `t1_pilot_md_13633::p00074_02` | voted | voted | voted |
| `t1_pilot_md_13644::p00037_00` | voted | voted | voted |

| File | voted | not_obligation | blank |
|---|---|---|---|
| `annotation_karan.csv` | 17 | 1 | 0 |
| `annotation_akash.csv` | 17 | 1 | 0 |
| `annotation_meer.csv` | 17 | 1 | 0 |

All three raters marked the **same single row** as not-an-obligation (`t1_pilot_md_13582::p00008_00`), and voted on the other 17. No rater left a row untouched.

## 3. Independence check (aggregate only)

Per §A1: the share of rows where `applies_to_rationale` or `notes` are identical, or near-identical at token Jaccard >= 0.9. Threshold for a warning is **more than 3** near-identical rows in a pair.

| Pair | Identical rationale | Rationale Jaccard >= 0.9 | Notes Jaccard >= 0.9 | Identical `(applies_to, flag)` | Verdict |
|---|---|---|---|---|---|
| karan vs akash | 0 | 1 | 0 | 14/18 | pass |
| karan vs meer | 0 | 1 | 0 | 15/18 | pass |
| akash vs meer | 0 | 1 | 0 | 13/18 | pass |

**The check does not fire for any pair.** No pair exceeds 3 near-identical rows. The single near-identical rationale in each pair is the shared not-obligation row, where all three raters independently wrote a short note to the same effect — the expected outcome when a row is unambiguous, not evidence of copying.

Supporting evidence for independence, recorded so the audit can weigh it:

- **Zero identical rationales** in any pair, across 17 voted rows each.
- **Different flag distributions**: karan {'shared': 7, '(blank)': 1, 'class-specific': 7, 'absent': 3}; akash {'shared': 11, '(blank)': 1, 'absent': 3, 'class-specific': 3}; meer {'shared': 10, '(blank)': 1, 'class-specific': 4, 'absent': 3}.
- **Genuine disagreement**: 13-15 of 18 judgments match per pair, so between 3 and 5 items per pair go to adjudication. Copied files would match on all 18.

One fact that points the other way, recorded because the audit should see it rather than have it omitted:

- **All three files were written to disk within 4.65 seconds of each other** (2026-09-25T06:35:20+00:00 to 2026-09-25T06:35:25+00:00). This is consistent with Karan copying three received files into `data/benchmark/tasks/` in one action, which is exactly what the prompt instructs him to do, so it carries no information about who authored them. It is recorded only so that no later reader mistakes the mtimes for evidence of three separate labelling sessions.

The ingest proceeds on Karan's written `manual` declaration, which is the mechanism §A2 and the Provenance rule establish for exactly this question. If that declaration is ever withdrawn for a file, that file must be moved to the `ai_assisted` diagnostic path and its votes removed from every reliability statistic; the tooling supports this without a re-ingest of the others.

## 3b. FINDING — `applies_to` is not replicated (declared by Karan 2026-09-25)

The textual check in §3 passes, and it is not sufficient. A per-column check
shows something it cannot see:

| Column | Identical across all three raters |
|---|---|
| `applies_to` | **18/18** |
| `applies_to` on multi-class items only | **14/14** |
| `differential_flag` | 12/18 |
| `applies_to_rationale` | 1/18 |

The `applies_to` sets in this pilot run to 3, 4, 7, 8, 9 and 12 classes out of a
19-class vocabulary. Independent raters do not converge on the same large subset
repeatedly; on 14 such items it is not a coincidence that needs weighing.

**Karan's explanation, given 2026-09-25 and recorded as the project's account:**
he filled `applies_to` once and gave Akash and Meer files with that column
already populated. Each of them then judged `differential_flag` independently
and wrote their own rationale. No AI tool was involved, so `label_source`
remains `manual` for all three; the files are not copies, and the rationales
being almost entirely distinct (1/18 identical) is consistent with that.

### What this costs, and what survives

- **`differential_flag` agreement is a real three-rater measurement.** Each
  rater formed that judgment themselves, they disagree on 6 of 18 items, and
  the three disagreement patterns are distinct. It is reported.
- **Every `applies_to` agreement figure is withdrawn.** The exact-match rate
  would read 1.0 by construction. `measure_agreement()` now detects the
  one-source pattern via `judgment_column_independence()` and **replaces**
  those figures with an explanation rather than emitting a number, so the 1.0
  cannot reach a report even by accident. `applies_to_replicated: false` is
  recorded in the metrics.
- **RQ1 has no inter-rater reliability evidence from this pilot.** The
  applicability labels are one person's judgment, reviewed by nobody. That is a
  real limitation of the pilot and the audit should see it stated, not inferred.
- **The flag agreement is conditional.** Every rater judged "does this
  obligation differ across classes?" against the *same* pre-supplied set of
  classes. The kappa below is agreement given a shared applicability premise,
  not free-standing agreement, and anchoring may have raised it.

### Consequence for Phase 2

Each rater must form `applies_to` independently, from the span text, before
seeing anyone else's. Until that happens no applicability reliability figure
exists for this benchmark.

## 3c. Aggregate agreement (three human raters, guidelines v1)

Per the blindness rule this is aggregate only; no per-item content appears.

**Fleiss' kappa on `differential_flag`: 0.6026** (n=17 items all three
raters voted on, raters akash, karan, meer).

| Pair | Cohen's kappa | n | Raw agreement | 95% bootstrap CI |
|---|---|---|---|---|
| akash vs karan | **0.6264** | 17 | 0.7647 | [0.301, 0.904] |
| akash vs meer | **0.4620** | 17 | 0.7059 | [-0.034, 0.817] |
| karan vs meer | **0.7198** | 17 | 0.8235 | [0.387, 1.000] |

`applies_to` exact-match and Jaccard are **withdrawn** for the reason in §3b.

**Is-it-an-obligation agreement: 1.0000** (n=18; unanimous
obligation 17, unanimous not-an-obligation 1, split 0). All three raters
independently rejected the same single candidate, and accepted the other 17.
This is the pilot's cleanest result: it measures candidate precision, which is
what a keyword heuristic is most likely to get wrong, and it was formed without
any shared premise.

The pairwise CIs are wide — akash vs meer includes zero — which is what n=17
buys. The kappas should be read as "moderate, imprecisely estimated", not as a
settled figure.

**Minutes per item — all recalled estimates, not measurements:**

| Rater | Minutes | Items | Min/item | Basis |
|---|---|---|---|---|
| akash | 45 | 18 | 2.50 | `recalled_estimate` |
| karan | 65 | 18 | 3.61 | `recalled_estimate` |
| meer | 50 | 18 | 2.78 | `recalled_estimate` |
| **mean** | 160 | 54 | **2.96** | `recalled_estimate` |

No Phase 2 size projection may be quoted from these without the words "based on
recalled estimates". The first measured figure comes from Part D.

**Promotion:** {'consensus': 11, 'needs-adjudication': 6, 'not-obligation': 1}, so 11/18 items reached `validated`
on the consensus route and 6 go to adjudication in Part D.

## 4. Guidelines version

All three files were labelled under **guidelines v1** — the instructions as they stood before A4. The v2 rules (obligated party, function headings, counterpart citation, as-of rule) postdate them and are **not** applied retroactively; the files are not edited. Expect some `applies_to` disagreement to come from guideline ambiguity rather than genuine disagreement, particularly on the function-heading names A4 now rules out. That is a known limitation of the pilot and is reported as such.

