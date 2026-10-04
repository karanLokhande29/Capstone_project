# RBI-ObliBench Command Center — Part B analysis

- **Written:** 2026-10-03.
- **Narrative source:** `reports/final/RBI-ObliBench_Master_Document_v2.md`. **Numbers:** `reports/results_v2.json` (sha256 `339bec85…`, verified at Step 0).
- **Decisions** are logged in [DECISIONS.md](DECISIONS.md); **progress** in [PROGRESS.md](PROGRESS.md).

## 1. Understanding (≤ 15 lines)

1. RBI-ObliBench is a benchmark over 381 RBI Master Directions (76,188 paragraphs). It tests whether systems know **which entity class an obligation binds** (RQ1), **what one class must do that another need not** (RQ2), and **whether RePASs can be gamed** (RQ3).
2. **T1:** 106 single-expert gold items, 412 class units (same 213 / different 78 / none 121).
3. **T2:** three counterpart-retrieval sets, each biased toward one retriever.
4. **T3:** 52 scored temporal items. It is circular by construction.
5. **T4:** an audit of RePASs over 30 questions × 4 answer types.
6. A class- and date-aware RAG pipeline (BM25 / dense / RRF, class filter, temporal filter, LLM judgement, NLI verifier) is the engineering artefact. A long-context variant and a frozen 13-field structured comparator are evaluated alongside it.
7. **What the evidence says:**
   - the class filter wins on retrieval (+0.451, partly by construction) but not on T1 judgement;
   - `different` is the core failure, and mostly a reasoning failure;
   - the verifier hurts T1;
   - long-context is competitive;
   - RePASs concatenation gaming reproduces;
   - the comparator lifts `different` F1 to 0.409 (+0.255 vs class-aware, CI excludes 0).
8. Reliability is indirect: κ is measured on a separate 30-item sample, never on the gold.
9. **Status:** results frozen; Master Document v2 and the paper draft regenerated in Part A; submission due 2026-10-10 (CMT); the authors rewrite the prose by hand from 2026-10-04.
10. **The UI is a read-only layer over these files.** It never recomputes a result, and every number carries its JSON key.

**Found wrong or unverifiable in B1:**
- **Venue line.** B1 says "6 pages (7 fallback, 8 hard max), not anonymous". The venue site says **4–6 pages at submission**; pages 7–8 are paid over-length (shown on the registration page). The site does **not** state a review mode. See `reports/final/venue_check_v1.md`.
- **Camera-ready date.** The site gives two dates: 30/11/2026 and "5th Jan 2026".
- Everything else in B1 matches the files:
  - RQ text, task sizes and the construction funnel;
  - routes 38/6/62, flags 52/40/14, judgements 213/78/121;
  - all seven headline values, and the precision of rules v4.

## 2. File inventory

| §1 source | Readable | Used for |
|---|---|---|
| `reports/results_v2.json` | yes | **Every number.** Keys used:<br>• `tables.01_corpus`, `02_candidates`, `03_matching`, `04_supplementary`, `05_t1_benchmark` (incl. `irr.fleiss`, `retest.phase2.all_25`, `timed_relabel`, `by_source_class`), `06_t2_retrieval.{p3001,p4_pipeline}`, `08_t3`, `09_t4`, `10_ablations.rows`, `11_llm_usage`;<br>• `phase4.{t1_systems, t1_paired, t1_different, comparator, comparator_dev, preregistered_comparisons, missed_by_every_llm_system, retrieval_vs_reasoning, long_context_same_items}`. |
| `reports/results_v1.json` | yes | Snapshot diff (v1 → v2). |
| `reports/final/RBI-ObliBench_Master_Document_v2.md` | yes | Narrative, definitions, limitations, Future Work 1–11, Changes from v1, claim sentences. |
| `paper/aisigh/main.tex`, `tables/*.tex` | yes | Paper claims (auditor), placeholder scan. |
| `data/rag_runs/t1_{class_blind,class_aware,final_agentic,ablation_a}/` | yes | 106 items each, gold v1. |
| `data/rag_runs/t1_long_context_cap100k/` | yes | 102 answered items. |
| `data/rag_runs/sealed_phase4/comparator_t1_gold_v1/` | yes | 412 units, with the 13-field extraction in `raw`. |
| `data/rag_runs/comparator_dev_irr30/` | yes | **Dev set: 92 units, comparator only.** |
| Majority / P2-002 baselines | yes | Recomputed by `src/eval/t1_regold.baseline_predictions`, as the scoring script does. |
| `data/benchmark/t1/t1_validated_v1.jsonl` | yes, read-only | Gold. The fields `raters`, `applies_to_rationale` and `provenance` are **not** ingested. |
| `data/benchmark/t1/p2004_irr_consensus_v1.jsonl` | yes | Dev gold (`judgements`). It reproduces the comparator dev confusion exactly (62/92). |
| `release/data/*` | yes | Pointers (paragraph sha256, URL, harvest date), documents, matrix, metadata (19 classes, 57 families). |
| `data/processed/md_*.jsonl` | yes, local only | ≤ 25-word excerpts under a per-paragraph word budget, and the dist grep test. Never bundled whole. |
| `configs/comparator_v1/*`, `configs/p4_prompts_v1/*`, `src/rag/comparator_rule.py` | yes, read-only | Frozen-hash ledger and the live comparator. |
| `reports/final/error_analysis_v1.json` | yes | Per-system "predicted instead", verifier abstentions. |
| `data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md` | yes | Guideline rules v3.1–v3.10 (flag-derivation diagram). |
| `docs/protocol/` | public files only | `reliability_plan_v2*` is release-excluded and **not** read. |
| `reports/private/**` | **not read** | Privacy rule. Consequence: the claims auditor matches numbers against public sources only (see G-22). |

**Are there per-unit predictions on gold v1 for every system?** Yes, for all 8 T1 systems; long-context covers 102 of 106 items.

**On the 30-item dev set?** **Only the comparator.** So the §8.2 plan uses two models (§7 below).

## 3. Verified gap list

| ID | Status | Finding | Verified | Part A |
|---|---|---|---|---|
| G-01 | Partial | T1 gold is single-expert; agreement is measured on a separate sample | confirmed (MD v2 §6) | — |
| G-02 | Needs validation | T3 is circular and has the old-words parser defect | confirmed (MD v2 §7, §9.5) | — |
| G-03 | Partial | RQ3 repair half not achieved (ρ −0.126) | confirmed (`tables.09_t4.human.all_rated.spearman_repaired_vs_faithful`) | — |
| G-04 | Missing | Human error-category pass not done | confirmed (MD v2 §9.8) | — |
| G-05 | Missing | Zenodo DOI + 3 author emails | confirmed (4 `\placeholder{}`) | A10/A16 listed |
| G-06 | Complete | "Ablation A" toggle vs system | confirmed, fixed | **Fixed in Part A** (A2) |
| G-07 | Complete | −0.050 vs −0.049 | fixed | **Fixed in Part A** (A3) |
| G-08 | Complete | RQ1 wording vs T2 | fixed | **Fixed in Part A** (A6) |
| G-09 | Complete | Abstention scoring undocumented | fixed | **Fixed in Part A** (A4, A11) |
| G-10 | Partial | No CIs on `different` F1 | note added; CIs still not computed | **Fixed in Part A** (A5, note only) |
| G-11 | Complete | Guideline version naming | fixed; it also covers the header "v3.1" collision | **Fixed in Part A** (A8) |
| G-12 | Complete | "Hybrid − source class" undefined | fixed | **Fixed in Part A** (A7) |
| G-13 | Complete | Majority baseline is in-sample | note added | **Fixed in Part A** (A9) |
| G-14 | Complete | Broken reference formatting | fixed + unit test | **Fixed in Part A** (A1) |
| G-15 | Partial | Venue rules | checked on the site (`venue_check_v1.md`); CMT is behind a login | A15 |
| G-16 | Complete | 150K run superseded | verified: no main-text number uses `tables.07_t1_systems.appendix_150k` (MD v2 mentions it only as superseded) | verify |
| G-17 | Unclear | Faculty guide not named in the project record | confirmed: no name in MD v2 | — |
| G-18 | Partial | Calibration rests on single-expert gold with wide CIs | confirmed; see the calibration report | — |
| G-19 | **added**, Conflicting | Venue camera-ready date: 30/11/2026 (home) vs "5th Jan 2026" (camera-ready page) | site | — |
| G-20 | **added**, Conflicting | Page plan: the checklist has a paid 7-page fallback, but the CFP says 4–6 pages at submission | site vs checklist | — |
| G-21 | **added**, Missing | Camera-ready steps absent from the checklist: PDF eXpress ID 70672X, copyright notice, eCF, supplementary ZIP, no-show rule | site | — |
| G-22 | **added**, Needs validation | The claims auditor can match only public sources (private named constants are not read), so some numbers can only be "?" | design | — |
| G-23 | **added**, Partial | The calibration signal "BM25 and dense agree on the matched paragraph" is unavailable offline: no per-unit BM25/dense rankings are stored for T1 units | data | — |
| G-24 | **added**, Unclear | MD v2 §8 prints the thinking config as a raw dict `{'thinkingLevel': 'minimal'}` | MD v2 | — |
| G-25 | **added**, Partial | The dev set has predictions for the comparator only, so the full-signal confidence model must be cross-fitted on gold | data | — |
| G-26 | **added**, Partial | Plagiarism screening happens **at submission** (CFP), but the checklist schedules the similarity check only for the camera-ready | site vs checklist | — |
| G-27 | Complete (A11) | Scoring asymmetry: abstentions are errors; long-context over-cap items are excluded | fixed | **Fixed in Part A** (A11) |

## 4. Data model

The model is §5 unchanged, with these additions:
- `Snapshot { generatedUtc, sources: [{path, sha256}], ... }` holds every entity.
- `ValueRef { value, key, file }`: every displayed number is a `ValueRef`, or a `MetricResult` / `PairedComparison` with `sourceKey`.
- `ClassUnit.predictions[system]` carries `{judgement, matchedPid, inContext, failure}`. `inContext` comes from the scoring code's own definitions.
- `ComparatorFields { side: source|candidate, field, status: equal|differs|only_source|only_target|absent, value? }`. Values are trimmed to the per-paragraph 25-word budget, with differing fields first.
- `ConfidenceModel` (§5) gets `id: M1|M2`, `weights[]` (standardised), `means[]`, `sds[]`, `specSha256`.
- `SnapshotDiff { key, v1, v2, kind }` holds the results v1 → v2 numeric diff.
- `VenueFact { item, text, sourceUrl, accessed }`, parsed from `venue_check_v1.md`.
- `GraphEdge { from, to, kind }`: one typed edge list drives traceability, the blast radius and the drawer's Upstream / Downstream tabs.

## 5. Information architecture

**Sitemap (React Router, hash-free paths; Vite preview / dev serves the SPA):**

| Group | Routes |
|---|---|
| Home | `/` Command Center |
| Research | `/rq/:id?` · `/results/:tab?` (t1, t2, paired, ablations, t3, t4) · `/different` · `/construction` · `/reliability` · `/atlas` · `/architecture` |
| Audit | `/claims` · `/gaps` · `/provenance` · `/diff` (snapshot diff) |
| Plan | `/next` · `/readiness` · `/workbench` (annotation workbench) · `/review-queue` |
| Product | `/product` (Showcase) · `/explorer` (Obligation Explorer) · `/assistant` |
| Guided | `/tour/:step?` (reviewer / viva mode) |

**Deep links:**
- `?node=<kind>:<id>&tab=<overview|evidence|upstream|downstream|caveats|source>` opens the right-side drawer on any route. Examples: `node=finding:F7`, `node=unit:t1_md_12925::p00044|Commercial Banks`, `node=system:comparator`, `node=caveat:by_construction`.
- `&trail=` keeps the breadcrumb path.
- Filters live in the query string: e.g. `/different?def=A&sys=comparator`, `/results/paired?prereg=1`.

**Navigation:**
- a left rail grouped as above;
- ⌘K palette (cmdk) with typed deterministic queries and global id search;
- the assistant is a toggleable side panel;
- a theme toggle (light / dark / system).

## 6. Screens

All screens have:
- a loading skeleton;
- an empty state naming the missing file and the command that produces it;
- an error state for unreadable or hash-mismatched sources;
- a synthetic-fixture watermark when the FixtureAdapter is active.

| Screen | Tier | Empty state |
|---|---|---|
| 7.1 Command Center | MUST | snapshot missing → `npm run ingest` |
| 7.2 RQ Explorer | MUST | — |
| 7.3 Results Lab (T1 · T2 · paired + forest plot · ablations · T3 · T4) | MUST | T4 scatter: "per-answer human ratings not in the public snapshot", showing ρ values only |
| 7.4 `different` Failure Explorer (+ comparator field heatmap) | MUST | unit predictions missing → `npm run ingest` |
| 7.5 Benchmark Construction | SHOULD | — |
| 7.6 Annotation & Reliability | MUST | — |
| 7.7 Corpus Atlas | SHOULD | matrix missing → `release/data/matrix` |
| 7.8 Architecture Map (React Flow) | SHOULD | — |
| 7.9 Claims ↔ Evidence Auditor | SHOULD | — |
| 7.10 Gap Analysis (+ Markdown export) | MUST | — |
| 7.11 What Should We Build Next? (lanes, blast radius, separate re-rank panel) | MUST | — |
| 7.12 Submission Readiness (+ Part A card, venue panel, pre-submission gate) | MUST | — |
| 7.13 Provenance & Freeze Ledger | SHOULD | — |
| 7.14 Obligation Explorer (offline, plus opt-in live) | COULD | live off → explains how to enable it |
| 7.15 Ask RBI-ObliBench assistant | COULD | off / quota reached / offline / blocked states |
| 7.16 Product Showcase | COULD | experimental bands are hidden |
| Reviewer mode, snapshot diff, annotation workbench, human-review queue, exports | COULD | — |

## 7. Intelligence rules and confidence plan

### R1–R14

R1–R14 are pure TypeScript functions in `ui/src/intelligence/`. Each returns `{rule, inputs, reason, sourceRefs, verdict}` and has unit tests.

| Rule | How it works |
|---|---|
| R1 (over-claim) | An effect-verb lexicon (*improves, hurts, beats, lowers, raises, outperforms, leads, wins, reproduces*) is applied to claim sentences. The linked CI comes from the number → key index; a CI that includes 0, or is opposite in sign, gives ⚠ plus a hedge. |
| R2 | Attaches the dataset's bias statement to every T2 node. |
| R3 | T3 filter-on: attaches `circular` and blocks showcase / "wins" use. |
| R4 | `n=102` mixed with `n=106` redirects to the same-items key. |
| R5 | Every T1-derived node inherits `single_expert`. |
| R6 | A number with no key match within the rounding tolerance of its printed decimals gives ✗. |
| R7 | Placeholders (`\placeholder{}`, "DOI to be assigned", TODO, `[verify]`). |
| R8 | One label with two referents (dictionary; "Ablation A" stays resolved after A2). |
| R9 | Per-source-class slices with n < 20 get a wide-CI warning. |
| R10 | sha256 mismatch → red banner. |
| R11 | Overdue, or slack < 1 day on the critical path. |
| R12 | Abstention handling documented? (yes after A4). |
| R13 | A metric without a CI where its siblings have one (`different` F1). |
| R14 | A confidence with no band accuracy + CI, or a band with n < 20, is blocked. |

### Confidence calibration (§8.2)

Everything below is frozen in `ui/src/data/confidence_spec_v1.json`, and its sha256 is recorded **before** any gold evaluation.

- **Unit:** one comparator class unit. The comparator is the product's verdict engine. Confidence is shown **only** for comparator verdicts; other systems' answers say "not calibrated".
- **Label:** correct when the comparator judgement equals the gold judgement. `unsure` counts as incorrect and goes to the Abstain band.
- **Models:**
  - **M2, comparator-intrinsic.** Used for live mode and as the clean transfer test. **Fitted on the dev set (92 units)**, then frozen, then evaluated on all 412 gold units. Features:
    - predicted label (one-hot `different`, `none`; `same` is the reference);
    - n fields extracted on both sides for the decisive candidate;
    - n material fields differing or one-sided;
    - the single-field hinge;
    - whether the two candidates gave the same verdict;
    - target Direction carries "Updated as on" (amended-text-only);
    - the source class × family matrix cell is ambiguous.
  - **M1, full signals.** Used for benchmark units in the explorers. Features: M2's features, plus
    - agreement count with {class-aware, class-blind, long-context} (0–3);
    - long-context unanswered;
    - final agentic abstained on this unit (verifier signal);
    - the comparator's matched paragraph equals the class-aware LLM's matched paragraph (retrieval support).

    The dev set lacks these systems, so M1 uses **5-fold cross-fitting grouped by item** on gold (fixed seed). Each unit is scored by a model that never saw its item.
- **Method:** L2-regularised logistic regression (C = 1, standardised features, Newton solver, numpy). The weights are shown in the UI.
- **Bands:**
  - **Fixed probability cut points:** High ≥ 0.85, Medium 0.60–0.85, Low < 0.60, plus **Abstain** (comparator `unsure` / parse failure).
  - **Merge rule:** a band with n < 20 on gold merges into Medium (or the band is hidden: R14).
- **Operating point:** "answer only at High", fixed in the spec.
- **Evaluation on gold:**
  - per-band n, accuracy and Wilson 95% CI;
  - reliability diagram (10 equal-width bins);
  - ECE (10 bins) and Brier score;
  - selective-prediction curve (accuracy vs coverage);
  - base rate (comparator accuracy 297/412 = 0.721).
- **Honesty rule:**
  - if the High band's Wilson CI does not sit above the Low band's point accuracy, **or** ECE > 0.10, the bands are labelled **experimental** and removed from the Showcase;
  - no rescaling or flooring;
  - a test asserts that UI values equal the frozen model outputs.

## 8. Technical architecture

```
ui/
  scripts/ingest.py          repo → src/data/snapshot.json (numbers by key, structure, pointers, unit predictions, ≤25-word excerpts)
  scripts/calibrate.py       §8.2: write spec (sha) → fit M2 on dev, cross-fit M1 on gold → evaluate → confidence_model_v1.json + docs/CALIBRATION.md
  scripts/check_dist.py      dist/ + src/data grep: RBI run > 25 words (corpus shingles), key-like strings
  scripts/tests/             pytest for ingest budget, calibration and the bridge (run explicitly; not in the repo's testpaths)
  server/                    Hono proxy (off by default): /api/status, /api/assistant, /api/pipeline; quota, cache, grounding post-check; keys server-side
  server/pipeline_bridge.py  persistent Python bridge: real class-aware RRF over data/processed + stored bge embeddings, frozen comparator prompt + rule
  src/domain/                §5 types
  src/data/                  ProjectRepository, RepoAdapter, FixtureAdapter, snapshot.json, confidence files
  src/intelligence/          R1–R14 + tests
  src/lib/                   ci.ts (mirrors src/eval/ci_format.py), graph.ts (traceability + blast radius), export.ts
  src/components/            Drawer, CICell, CaveatChip, ForestPlot, ConfidenceBadge, ProvenanceTooltip, ui/* (shadcn-style)
  src/features/<screen>/     one folder per screen
```

**Stack:** Vite, React 19, TypeScript strict, Tailwind v4, shadcn-style components (Radix primitives), lucide-react, Recharts, @xyflow/react, cmdk, TanStack Table, Zustand, React Router, Vitest + Testing Library, Hono + @hono/node-server, tsx.

## 9. Implementation phases

| Phase | Work | What it proves |
|---|---|---|
| 1 | Part A | Done. |
| 2 | Ingest, domain, CI component | Every number traces to a key; the ingest cross-checks unit-level counts against `results_v2.json`. |
| 3 | Command Center, Results Lab, drawer | The core loop. |
| 4 | `different` Explorer, Reliability, Gap Analysis | The hard findings are explorable. |
| 5 | Readiness, Claims Auditor, R1–R14 | Protects 10 Oct. |
| 6 | Calibration offline | The numbers are reported before any UI uses them. |
| 7 | Atlas, Architecture, Provenance, palette queries | — |
| 8 | Explorer (offline + live), assistant, Showcase, tour, diff, workbench, review queue, exports | — |

## 10. Risks and assumptions

- **Release check.** `ui/.gitignore` excludes `node_modules/`, `dist/`, `.env`, `server/.state/` and `server/.cache/`. `snapshot.json` is publishable and is scanned by the 30-word rule; its excerpts are ≤ 25 words with pointers. TS/TSX files are not in the release check's text suffixes, so `check_dist.py` scans `src/data` and `dist`.
- **RBI text.** The per-paragraph budget is 25 words across *all* uses: excerpt plus comparator field values. The full text is never bundled; `release/rehydrate.py` is the path to full text.
- **Missing data:**
  - no per-answer T4 human ratings in public files → ρ only;
  - no per-unit BM25/dense rankings → G-23;
  - private constants are unreadable → G-22.
- **Quota.** Zero LLM calls during the build. The assistant and live mode use `ASSISTANT_GEMINI_API_KEY` only (never `GEMINI_API_KEY`), with a daily cap of 50, a hash-keyed cache, and are off by default. Tests use a mock client.
- **Calibration sample size.** Dev has 92 units (M2 fit) and gold 412. Band CIs will be wide; the honesty rule above decides "experimental".
- **Live retrieval.**
  - The dense query is the source paragraph's stored bge embedding, because no encoder is loaded; this avoids touching the model cache outside the repo. Free-text queries are therefore BM25-led and labelled as such.
  - Live mode needs `data/processed` and `data/indexes`, which are local and gitignored; it is off otherwise.
- **Dates.** "Today" in the UI is the browser's date. Overdue flags compare against it.
