# Demo build: Phase A audit

Spec: `docs/prompts/RBI-ObliBench_Demo_Build_Spec.md` (received 2026-10-04). All paths are relative to the repo root. Every number below was computed from repository files while writing this audit; the scratch scripts are in `logs/command_center_scratch/` (gitignored).

**Hard-stop check 1 (frozen hashes): passed.** These files hash to the values in `configs/comparator_v1/FROZEN.json` and the Step 0 list:

| File | sha256 (prefix) |
|---|---|
| `src/rag/comparator_rule.py` | `83664f8d9d8f` |
| `configs/comparator_v1/comparator_system.txt` | `51f7ea78ed4b` |
| `configs/comparator_v1/comparator_user.txt` | `cde2087182da` |
| `reports/results_v2.json` | `339bec858af8` |
| `data/benchmark/t1/t1_validated_v1.jsonl` | `67d471a13a26` |

## A1. Per-unit predictions

Unit = (T1 item, compared class). There are 106 items and 412 units.

| System | Per-unit source | Format | Units with output | Abstention representation | `matchedPid` |
|---|---|---|---|---|---|
| `p2002_candidates` | `data/benchmark/t1/t1_candidate_benchmark_v1.jsonl` (`top_targets`), turned into judgements by `src/eval/t1_regold.baseline_predictions` | JSONL, one record per candidate | 412 (same 251, none 161) | cannot abstain; cannot output *different* | none (rule-based baseline) |
| `class_blind` | `data/rag_runs/t1_class_blind/t1_*.json` | one JSON per item; `final.per_class[cls]` | 412 (different 34, same 219, none 159) | `judgement: "unsure"` → shown as *Abstained* | 253 |
| `class_aware` | `data/rag_runs/t1_class_aware/` | same | 412 (different 13, same 249, none 149, abstain 1) | `unsure` | 262 |
| `final_agentic` | `data/rag_runs/t1_final_agentic/` | same, with `retried` | 412 (different 7, same 163, none 156, abstain 86) | verifier declines → `unsure` | 170 |
| `ablation_a` | `data/rag_runs/t1_ablation_a/` | same | 412 (different 13, same 159, none 158, abstain 82) | `unsure` | 172 |
| `long_context` | `data/rag_runs/t1_long_context_cap100k/` (104 files; 102 items answered) | same | 396; 16 units (4 items) never answered | missing item → `unanswered` (*Not answered*) | 267 |
| `comparator` | `data/rag_runs/sealed_phase4/comparator_t1_gold_v1/` (412 files, `raw` = the model's JSON) | one JSON per unit | 412 (different 108, same 155, none 147, abstain 2 = parse failures) | `judgement: "unsure"` when `raw` is unparseable | 263 |

**Verdict:** per-unit output exists for every system, so no column needs the "per-unit output not released" state. The state is still built (for safety), but nothing uses it. Rationales (free text) exist in the run files. They are **never shown** (no chain-of-thought exposure).

## A2. `inContext`

`phase4.retrieval_vs_reasoning` is computed by `src/eval/different_taxonomy.analyse`, using the context definitions from `scripts/run_phase4_scoring.py`:
- **RAG systems:** `DT.context_ids_rag(record.steps, target_class)`; `steps[i].shown[target_class]` lists the paragraph ids given to the model.
- **Long context:** the rebuilt prompt body (`src/rag/pipeline.long_context_messages`, 100K cap) contains `[<gold pid>]`. Two units are `None` (item never answered).
- **Comparator:** the two P2-002 candidates (`top_targets[cls][:2]`). The gold pid is in context for all 78.

`ui/scripts/ingest.py` already rebuilds this per unit and asserts it equals `results_v2.json` (errors and failure types per system).

**Verdict:** available for every system. The Failure Map uses the solid vs hatched distinction everywhere except P2-002 (it cannot say *different*; greyed).

## A3. Frozen rule semantics (most important)

`src/rag/comparator_rule.py` (sha `83664f8d…`):
- **Per candidate:** `none` if `addresses_same_duty` is false. Otherwise `different` if **any of the 13 fields** has `differs`, or if any **material** field is `only_source` / `only_target`. Otherwise `same`.
- **Material fields (11):** actor, scope, condition, threshold, amount, percentage, frequency, deadline, exception, documentation, reporting. `action` and `object` are not material, but a `differs` on them still fires.
- **Class verdict:** precedence `same > different > none` over the candidates. The matched paragraph is the first candidate with the winning verdict; `unsure` on unreadable output.
- **`actor` can trigger DIFFERENT: yes** (any `differs` fires, and actor is material). **Branch A3-yes.**

Re-evaluating the frozen rule on all 410 parseable sealed outputs reproduces the stored verdict on **410/410**; the 2 parse failures stay `unsure`. The rule file is imported, never edited.

### Sensitivity analysis

**Post-paper sensitivity analysis — frozen benchmark result unchanged.**

The frozen rule was re-run with `actor` comparisons masked to `equal`. Everything else is unchanged, including candidate precedence.

| | Frozen rule | Actor masked |
|---|---|---|
| Correct DIFFERENT calls (of 78 gold *different*) | 38 | **37** (37 of the 38 remain) |
| False alarms (DIFFERENT on gold same/none) | 70 | **62** (62 of the 70 remain) |
| Gold *same* called *same* | 149 | 157 |

The one correct call lost is `t1_md_13020::p00031|All India Financial Institutions`: its only difference is `actor: "A UCB" | "An AIFI"`.

For comparison only (not requested), masking `actor` and `scope` gives 33 correct and 52 false alarms.

**Candidate limitation line for the authors (drafted, not inserted):**
> "The comparator's fixed rule treats any extracted `actor` difference as material; because institution names differ across classes by construction, 8 of its 70 false alarms and 1 of its 38 correct *different* calls rest on actor wording alone (post-hoc sensitivity analysis; the reported result uses the frozen rule)."

**UI treatment:**
- In the Microscope, actor rows whose two values differ only by an entity-class name or generic institution word carry the note *"Entity name differs by construction."* The detection is a deterministic alias list in `ui/scripts/build_demo_data.py`.
- The headline figures stay 38/78 and 70 false alarms.

## A4. Null values under `differs`

There are 642 `differs` rows in the raw sealed comparator JSON (decisive candidate):

| Raw values | Rows |
|---|---|
| Both sides present | 609 |
| Source present, target null | 21 |
| Target present, source null | 12 |
| **Both null** | **0** |

So every `differs` row that shows `null | null` in the public snapshot (e.g. `t1_md_13327::p00012|Payments Banks`, `scope`) is an **ingest redaction**: the per-paragraph 25-word budget was exhausted. It is not a model output.

**Branch A4-redaction.** Values carry an explicit state:
- `withheld`: rendered "value withheld — excerpt limit; open in presenter mode";
- `null`: rendered "not extracted";
- `extraction_anomaly` is reserved for `differs` with both raw values null. Count: 0.

## A5. Other artifacts

| Artifact | Path | Verdict |
|---|---|---|
| T2 per-query rankings, `t2_xclass_t1` | `data/evaluation/p3001/runs_t2_xclass_t1_v1.jsonl` (2,060 lines = 412 queries × 5 retrievers: bm25, dense, hybrid_rrf, hybrid_minus_source, class_aware). Relevance: `release/data/t2/t2_xclass_t1.jsonl`. 291 queries are scored. | Available → K3 |
| T3 items and runs | `release/data/t3/items.jsonl` (52 scored: as-of, side before/after, amendment action and effective date, gold status); predictions in `data/rag_runs/t3_temporal_{off,on}/T3-*.json` (60 each; 52 scored) | Available → K2 |
| Corpus matrix | `release/data/matrix/matrix_v1.jsonl`, `documents.jsonl`, `metadata/*.json` | Ingested into `snapshot.json`. **The public build strips them** (`ui/scripts/public_snapshot.py`, D-23); they were not missing. → K1 |
| Retrieval run logs per T1 unit | `steps[].shown` per class (final context only). No separate BM25/dense/RRF lists and no filter-removal log per T1 unit. | Partial. K4 X-Ray shows only what is logged (context given to the LLM, retries, abstain); the BM25/dense/RRF stages are hidden. |
| 30-item three-rater set | Per-rater labels exist only in files named after the raters (`data/benchmark/t1/annotation_p2004_irr_<name>*.csv`); the anonymous consensus is in `p2004_irr_consensus_v1.jsonl`. | Not used. Building rater_1–3 from name-labelled files would create a rater-identity mapping, which the project's privacy rule forbids. **K5 is not built.** The κ values stay on Method & Trust. |
| T4 | `release/data/t4/{questions,answers_*,scores}.jsonl` (30 questions, 120 scored answers) | Available → K7 static |
| LLM ledger | `logs/llm_calls.jsonl` (1,743 calls). Comparator T1: 412 calls, 535,706 input / 301,815 output tokens; dev: 92 calls per run. | Tokens available. **No price is recorded anywhere in the repo**, so the cost meter shows tokens only (no invented ₹/US$). |
| Rehydration | `release/rehydrate.py` → `scripts/rehydrate.py` | Deterministic. Offline (`--offline data/processed --sample 5`): 603/603 paragraph hashes matched. Online (`--md md_12949 md_12994`, fetched from rbi.org.in 2026-10-04): 317/317 matched, payload identical to harvest. **H4 is feasible.** |

## A6. Current UI inventory

- **Stack:** Vite 7, React 19, TypeScript strict, Tailwind v4, react-router 7 (browser router; hash router for the claude.ai copy).
- **Public build** (`npm run build:azure` → `dist-azure/`): pitch-only routes `/`, `/findings`, `/demo`, `/how-it-works`, `/trust`, lazy-loaded (`Home`, `Findings`, `Demo`, `HowItWorks`, `Trust`, shared `ui`, `persona`).
- **Local-only author workspace:** `/workspace` and research routes (`npm run dev`).
- **Data:**
  - `ui/scripts/ingest.py` builds `src/data/snapshot.json` (2.5 MB), cross-checked against `results_v2.json`;
  - `ui/scripts/public_snapshot.py` slims it to `snapshot_public.json` (1.55 MB) for public builds;
  - `ui/scripts/calibrate.py` writes `src/data/confidence_model_v1.json` (M2 fitted on dev, frozen; M1 cross-validated on gold).
- **Persona switcher:** changes the Home hero text, the order of the Results sections and the "Suggested for you" cards. It is stored in localStorage `cc-persona`.
- **Deploy:** `cd ui && npm run deploy:azure` runs `scripts/deploy_azure.sh` and uploads `dist-azure/` to the `$web` container of storage account `rbioblibench5qbvp2`, with an `index.html` copy per route.

## Branch decisions and choices

| Item | Decision |
|---|---|
| A1 | All seven systems have per-unit output; no column is filled from aggregates. |
| A2 | `inContext` is available for all LLM systems and the comparator. |
| A3 | **A3-yes.** Entity-name note in the Microscope; sensitivity analysis above, labelled; limitation line drafted, not inserted. |
| A4 | **A4-redaction.** `withheld` state; anomaly marker is implemented and fires 0 times. |
| B3 hero | **The proposed case fails verification and is replaced.** Details below. |
| Triage bootstrap seed | `20261003`: the seed in the confidence spec (`ui/scripts/calibrate.py`, `SPEC_DATA["seed"]`), as the spec prefers a confidence-specific seed over `results_v2.json → phase4.bootstrap.seed` (`20261011`). 2,000 item-level resamples over the 106 items. |
| K5 | Not built (privacy rule; see A5). |
| Cost | Tokens only; no prices exist in the repo. |
| Commits | The repo is on `main` with 158 uncommitted author changes since P1-004. Phase commits go to a separate branch, `demo-build`, and contain **only `ui/`**, so nothing of the authors' pending work is committed. |

### B3 hero choice

**Proposed case rejected:** `t1_md_13005::p00071|Commercial Banks`.
- It is in `missedA`, and the comparator calls DIFFERENT, matching gold. But its decisive candidate `md_13160::p00076` is a **page-break fragment**: the paragraph text stops mid-sentence ("…borrowings through instruments qualifying for Tier 1 and").
- The comparator's `exception: only_source` lists the additional-Tier1 proviso, which the Commercial Banks Direction **does** contain (in the next paragraph, `md_13160::p00077`).
- The `scope` difference is just the class names ("Rural Co-operative Banks" | "Commercial Banks").
- So the caught difference is partly a segmentation artifact; not legible as a hero.
- The second-ranked fallback (`…|Small Finance Banks`, `md_13128::p00078`) is the same kind of fragment and is also rejected.

**Chosen hero:** `t1_md_12949::p00040|Rural Co-operative Banks` (topic: Asset Liability Management).
- **Source (NBFC):** "(2) Structural Liquidity and Interest Rate Sensitivity return (DNBS04B) at monthly interval", with submission timelines in the Filing of Supervisory Returns Directions, 2024.
- **Target (RCB, `md_12994::p00022`, also the gold matched paragraph):** "…Structural Liquidity Statement (SLS) and Interest Rate Sensitivity (IRS) Statement at quarterly intervals", with timelines from NABARD guidelines.
- `missedA` and `missedB` are true: all five LLM systems answered and none said *different*.
- The comparator says DIFFERENT, and gold says different.
- Decisive material fields: `frequency differs` and `deadline differs` (`object` also differs). `actor` is `equal`, so the call does not rest on actor.
- Checked against the full local text of both paragraphs.
- **Public display:** for these two pointers the 12-word excerpt is taken at the obligation sentence (an ingest focus anchor) instead of the paragraph start; it stays inside the 12-word excerpt and 25-word paragraph limits.

### Phase H / J decisions (no credentials)

- `.env` holds only the experiments' `GEMINI_API_KEY` and `GROQ_API_KEY`. The project rule forbids using the experiments' key for the UI, and no `ASSISTANT_GEMINI_API_KEY` exists. This is **hard stop 3 at deploy time.**
- **H:** built and tested locally with a mocked model; not deployed until a key and approval arrive.
- **Replays:** no live runs → no cached replays → presenter mode ships only its non-live steps; nothing is labelled Live.
- **J:** the control-run reproducibility check (≥ 5 live runs) cannot run, so J ships as a **read-only explainer**.

### Comparator misses (E drill-down)

All 32 DIFFERENT→NONE errors have `addresses_same_duty = false` on **both** candidates (32/32). This supports the caption.

---

## Decisions taken while building (Phases B–K)

| Item | Decision |
|---|---|
| **H streaming** | The local server (`ui/api/server.py`) ships **incremental** streaming. `field` events come only from values `jsonstream.JsonStream` has fully parsed; on any parse problem the run continues **buffered**, with no per-field events (tested). The Azure Function wrapper (`ui/api/function_app.py`) is **buffered** (no HTTP-streaming extension), and its `/api/health` says so. The UI copy matches each mode. |
| **H deployment** | **Not deployed (hard stop 3).** There is no demo-dedicated model key, and the experiments' `GEMINI_API_KEY` must not be used. Built and tested locally with a mocked model: 19 API tests, including 5 benchmark units end to end that reproduce the sealed output, a mid-stream network loss, the rate limit, and paste privacy (a marker string never reaches the cache or the logs). The public site has no API, so it is replay-only with the "Live service unavailable" banner. |
| **Replays** | Recorded only from real live runs. Runs from the dev test double (`MOCK_LLM=sealed`) are stored apart and are never served as replays. None exist yet, so presenter mode hides the live step unless a model is configured. |
| **Inputs for live runs** | Exactly the sealed run's inputs: the source span and two candidates from the blank pass-1 sheet, sha-checked against the draw log as `scripts/run_sealed_predictions.py` does. They are written to `ui/api/.data/` (gitignored, server-side only). The call shape is the same as the sealed run: temperature 0, JSON mode, `thinkingLevel: minimal`, 4,096 output tokens. |
| **J edit lab** | **Read-only explainer** on the public site. The control-run reproducibility check (≥ 5 live runs) could not be run without a key. In local presenter mode with a live model the full flow (control-run gate, structured edits, conclusion) is enabled. Edit runs are logged to `lab_runs.jsonl` locally, or to an append blob behind `CACHE_CONNECTION`. 9 curated base pairs (6 *same*, 3 *different*; 55 / 19 eligible). |
| **H4 freshness** | Local presenter only: the repository's own fetch → re-segment → hash path (`scripts/rehydrate.py`), cached for 24 h, with exactly three outcomes. The Azure wrapper answers "Could not verify" because the pipeline is not bundled there. |
| **K1 Atlas** | Built. The matrix has **294** populated cells over the 11 regulated classes; the published **296** includes 2 cells under "Foreign Exchange Management", an RBI function heading. The page states both. |
| **K2 T3 timeline** | Built. Dragging the as-of date shows the amendment record's status; the model's stored answers appear only at the date that was actually asked. Nothing is generated. |
| **K3 T2 animation** | Built from `data/evaluation/p3001/runs_t2_xclass_t1_v1.jsonl`. Recall@10 is re-derived and asserted equal to `results_v2.json`. |
| **K4 X-Ray** | Partial, from the logs that exist: the context given to each LLM system per attempt, retries and the final answer. The BM25 / dense / RRF stages were not logged per case and are not shown. One view per system. |
| **K5** | Not built (privacy rule; see A5). |
| **K6 cost** | Tokens from the ledger. **No price** exists in the repository, so none is shown. |
| **K7** | The static part is built. Live RePASs scoring is not attempted (optional). |
| **K8 audience poll** | Not built: it needs the backend and a store. |
| **Release check on `ui/dist`** | `ui/scripts/check_dist.py` (25-word limit, stricter than the release check's 30) scans every build plus `public/data`. It also runs the §14.2 honesty grep and fails if a public build contains the full-text endpoint. `npm run deploy:azure` refuses to deploy when it fails. |
| **Commits** | Branch `demo-build`. Commits contain `ui/` plus `paper/aisigh/PATCHLIST_v1.md` (B5). The paper and generator files themselves are untracked in this repository and were not committed. |

## QA (§14), 2026-10-04

| # | Check | Result |
|---|---|---|
| 1 | Ingest assertions (§C3) | Pass: 412/412 traced, M2 recomputed per unit, every published count reproduced. |
| 2 | Honesty grep on all builds | Pass. |
| 3 | No RBI run ≥ 26 words in any build or data shard; no full-text endpoint in public builds | Pass (`check_dist`). |
| 4 | Every route at 375 / 768 / 1280 px, light and dark | No horizontal scroll; tables scroll inside their own containers. Keyboard: cells, rows and choices are focusable. Failure Map states are icon or pattern plus label. |
| 5 | Accessibility | axe-core 4.10: 0 violations on all 13 routes in light and dark. **Lighthouse itself was not run** (no Lighthouse CLI here). Home transfer ≈ 156 KB gzipped, of which 2 KB is JSON (budget 150 KB of JSON). |
| 6 | Backend | Hash verification, the 503 on mismatch, rate limit and paste privacy are covered by tests. CORS is restricted to the listed origins. Not deployed. |
| 7 | Presenter preflight | Green for sealed data and hashes. Live and replay are skipped without a key, and the live step is then hidden. |
| 8 | Click-through | Home hero → reveal → Microscope → (re-run disabled: no model) → Failure Map cell → case → Triage → Results → Method: OK on the deployed site. |

**Tests:** vitest 101; Python 26 (UI scripts + API); repo pytest 1211; `release_check` PASS; `build_tables --check` up to date; `check_paper --allow-placeholders` PASS; `scan_documents` 0 unsourced.
