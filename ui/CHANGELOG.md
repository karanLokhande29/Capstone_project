# Changelog

## 2026-10-04: Demo build (Demo Build Spec, all must-ship phases)

Branch `demo-build`; commits contain `ui/` only (plus `paper/aisigh/PATCHLIST_v1.md`). Details and branch decisions are in `ui/AUDIT.md`.

### User-visible changes

**Navigation**
- New top navigation: **Home · Cases · Lab · Triage · Results · Method & Trust**.
- The hidden `/present` is the presenter mode.
- Old URLs redirect: `/findings` → `/results`, `/how-it-works` → `/method`, `/trust` → `/method#limits`, `/demo` → `/cases`.

**Home**
- The hero is a playable Spot-the-Difference round on a verified case (`t1_md_12949::p00040|Rural Co-operative Banks`).
- Below it: the one-sentence positioning, four stats, and persona-ordered cards.
- The persona switcher only reorders cards and sets default filters; the compliance persona can pick an institution type.

**Cases**
- Three choice cards (Play, Failure Map, Inspect).
- Explore with eight filters plus a paragraph-id search; "Next case" walks the current filter.
- **Case view `/case/:unitId`:**
  - two paragraph cards;
  - a predictions strip for 7 systems plus the expert, with "gold paragraph was in context";
  - the 13-field Microscope, where clicking a row highlights the value by string match only, with entity-name and withheld-value notes;
  - the decision trace from the frozen rule;
  - B1 confidence ("Flagged for review" on DIFFERENT);
  - a "Why can I trust this?" provenance drawer;
  - X-Ray of what each LLM system was given (from the run logs only).
- **Failure Map:** 78 real differences × 7 systems. Cells are caught / reasoning failure / retrieval implicated (hatched) / abstained / never answered / n/a. Icons and patterns mean state never relies on colour alone. Includes a "Why the comparator misses" drill-down.
- **Play:** curated (56 cases every LLM missed) or random draw. Scored only over rounds played, against the best of the five LLM systems over the same rounds.
- **Atlas:** 11 regulated classes × 57 topics, with ambiguous cells marked and a comparison of two classes.

**Triage** (post-paper)
- A threshold slider over the M2 probability.
- Coverage, accuracy of what is handled, and what goes to review, each with item-level bootstrap 95% ranges. Split by verdict.
- A reliability diagram, plus feature weights and per-case contributions.
- Never called a recommendation.

**Lab**
- Re-run a benchmark pair (sealed vs live, with a "Live ≠ sealed" diff), Paste (unvalidated, with a privacy warning) and an Edit lab (read-only explainer in public).
- A cost meter in tokens; no price is recorded.
- Without a backend: "Live service unavailable — showing cached replays."

**Results**
- System names follow B2, e.g. "Our first pipeline (institution filter + fact-checker)".
- Result 5 now explains that the first pipeline scored lowest, which is why the comparator was designed.
- Added the T3 amendment timeline (stored answers only at the asked date), the T2 institution-filter animation and a static RePASs playground.

**Method & Trust**
- Two separately evaluated lanes (retrieval systems vs structured comparator).
- Safeguards, the actor-masked sensitivity analysis (labelled *Post-paper sensitivity analysis — frozen benchmark result unchanged.*), limits, the cost meter, the frozen-file hash ledger and licences.

**Status badges everywhere:** Benchmark · sealed / Live re-run / Cached replay / Unvalidated input / Post-paper / Live ≠ sealed.

**Accessibility**
- axe-core reports 0 violations on all pages in light and dark mode.
- Inline links are underlined.
- Light-theme `ink-3`, `pos` and `warn` were darkened slightly for 4.5:1 contrast.

**Performance and privacy**
- Public builds no longer ship the research snapshot. Home loads 10 KB of JSON; JS, CSS and JSON are served gzipped.
- The public build contains no full-text endpoint (checked by `check_dist`).

### Every number the UI displays, and where it comes from

All per-unit numbers are rebuilt by `ui/scripts/build_demo_data.py` from run files and asserted equal to the published values (§C3); the build stops on any mismatch.

| Number(s) | Shown on | Source |
|---|---|---|
| 381 Directions, 76,188 paragraphs, 11 institution types | Home, Results, Method | `reports/results_v2.json` → `tables.01_corpus` |
| 412 comparisons, 106 obligations; same 213 / different 78 / none 121; flags 52/40/14; routes 38/6/62 | Home, Cases, Method | `data/benchmark/t1/t1_validated_v1.jsonl` (asserted) |
| 56 missed by all five LLMs (def. A), 58 (def. B); comparator recovers 26; 32 missed by every system | Home, Failure Map, Results | per-unit run files `data/rag_runs/t1_*` and `sealed_phase4/comparator_t1_gold_v1`; equal to `phase4.missed_by_every_llm_system` |
| Errors / retrieval / reasoning per system (60/30/30 … comparator 40/0/40); 262 of 350 LLM errors with the gold paragraph in context | Failure Map | same; equal to `phase4.retrieval_vs_reasoning` |
| Comparator 38/78 found, 70 false alarms; 38 of 108 flags right (35%), 38 of 78 caught (49%) | Home, Case view, Results | `sealed_phase4/comparator_t1_gold_v1` vs gold; equal to `phase4.comparator.different` |
| LLM systems' differences found / false alarms / agreement / answered share | Results | `phase4.t1_different.*.judgement_confusion`, `phase4.t1_systems.*.coverage` |
| Pre-registered comparator − institution-filtered LLM on `different` F1, with 95% range | Results fine print | `phase4.preregistered_comparisons` |
| Fact-checker change on flag macro-F1 | Results fine print | `phase4.t1_paired` |
| T2 top-10 recall: 82% / 77% / 81% / 96%; nDCG 0.46 / 0.42 / 0.44 / 0.89; 291 scored queries; per-query ranks | Results | `tables.06_t2_retrieval.p3001.t2_xclass_t1`; ranks from `data/evaluation/p3001/runs_t2_xclass_t1_v1.jsonl` (recall@10 re-derived and asserted) |
| T3: before-change 25/26 right; after-change 23/26 called unchanged; 48 of 52 "in force, original" without the date check | Results | `tables.08_t3.t3.off.by_side`; items `release/data/t3/items.jsonl`; answers `data/rag_runs/t3_temporal_{off,on}` (52/48 asserted) |
| T4 RePASs: genuine 0.371, pasted 0.746, negated, off-topic; gap +0.375 [+0.325, +0.427]; per-question scores | Results, Present | `tables.09_t4`; `release/data/t4/scores.jsonl` |
| M2 bands High 156/162, Medium 95/123, Low 46/125, Abstain 0/2; ECE 0.087; Brier 0.148; base 297/412; High = 155 same + 7 none; correct DIFFERENT 36 Low + 2 Medium | Case view, Results, Triage | `ui/src/data/confidence_model_v1.json` (M2 recomputed per unit and asserted) |
| Triage coverage / accuracy / review at every threshold, with 95% ranges | Triage | `ui/public/data/triage_grid.json`: item-level bootstrap, 2,000 resamples, seed 20261003 (asserted 162/156 at High) |
| Actor-masked sensitivity 37 of 38 correct, 62 of 70 false alarms | Method | the frozen rule re-run on the sealed outputs with `actor` masked (`build_demo_data.py`) |
| 32 of 32 comparator "no match" errors judge neither paragraph the same duty | Failure Map, Method | `sealed_phase4/comparator_t1_gold_v1` |
| κ 0.774 (class row), 0.571 (flag) on the separate 30-item set | Results, Method, Runbook | `tables.05_t1_benchmark.irr.fleiss` |
| Atlas: 294 populated regulated cells (296 incl. a function heading), 9 ambiguous | Atlas | `release/data/matrix/matrix_v1.jsonl` |
| Tokens per comparator call (1,300 in / 733 out), full run 535,706 / 301,815; dev runs | Lab, Method | `logs/llm_calls.jsonl` |
| Hashes (prompt, rule, gold, results, confidence model; 16-file ledger) | Case drawer, Method | `configs/comparator_v1/FROZEN.json` + sha256 of the files at build time |
