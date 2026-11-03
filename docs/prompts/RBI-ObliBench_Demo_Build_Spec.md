# RBI-ObliBench — Demo Build Spec (one-day, all phases)

**For:** the Claude Code session that built the current UI (`ui/`, deployed to the Azure static website `rbioblibench5qbvp2.z29.web.core.windows.net`).
**From:** a review of the live site, its shipped JSON (`snapshot_public-*.json`, `confidence_model_v1-*.json`), the paper PDF and `RBI-ObliBench_Master_Document_v1`. Two reviewers (Claude and GPT) agreed this plan.
**Date written:** 2026-10-04. **Hard deadline in snapshot meta:** 2026-10-10 23:59 IST. **Target:** everything below done in one continuous session.

The one sentence the finished demo must communicate:

> **This is not a chatbot over RBI documents. It is a benchmark and inspection environment for finding, explaining and stress-testing differences between regulatory obligations.**

Every page (Home, Case view, Lab) should reinforce that sentence.

---

## 0. How to run this document

1. Read the whole document once before touching code.
2. Do **Phase A (Audit)** first and write `ui/AUDIT.md`. Several later phases branch on what the audit finds. Branches are spelled out, so pick the branch and keep going — do not stop to ask unless you hit a **HARD STOP** (listed in §0.3).
3. Then execute phases in order. Each phase ends with acceptance checks; run them, fix, move on.
4. Commit after each phase with a message `demo: phase <X> — <summary>`. Keep the site deployable after every commit.
5. If time runs short, use the **cut order** in §15. Whatever is finished must be shippable and honest; half-built features are hidden behind a flag, never shown broken.

### 0.1 Non-negotiable honesty invariants (apply to every phase)

- **Never modify frozen artifacts:** the comparator system prompt, the comparator rule, the gold (`data/benchmark/t1/t1_validated_v1.jsonl`), sealed predictions, `reports/results_v2.json`. The UI reads them; it never rewrites them. Hashes are displayed, and the backend verifies them.
- **Never derive per-unit system predictions from aggregate tables.** Per-unit data comes from run files or it is not shown.
- **Never fake liveness.** No staged "checking threshold…" animation. A field appears only when it has actually been parsed from a streamed model response. Replayed output is labelled *Cached replay*.
- **Never invent the reason for a verdict.** The decision trace comes from the frozen rule's actual evaluation, not from free text.
- **Never imply validation that did not happen.** Pasted text = *Unvalidated input*. Triage slider = *observed trade-off on the evaluated test set*, never "recommended threshold". The confidence model is *Post-paper* unless the paper revision includes it.
- **Never show an end-to-end pipeline that was not evaluated as one.** The structured comparator ran only on the two P2-002 candidates the annotator saw; it never ran on retrieved evidence. Retrieval systems never used the comparator. Show them as separate systems.
- **Pointer-only release stays pointer-only.** The public build shows at most the existing excerpt limit (`excerptWords: 12`, `wordLimit: 25` in snapshot meta). Full RBI text appears only in **local/presenter mode** from a rehydrated corpus. Extend the existing release check (≥30 copied words fails) to scan the built `ui/dist/` assets.
- **No secrets in the client.** API keys live only in the Azure Function's app settings.
- **No chain-of-thought exposure.** Show structured fields, evidence spans located by string match, and rule outputs only.

### 0.2 Status badge taxonomy (build once as a component, use everywhere)

| Badge | Meaning |
|---|---|
| **Benchmark · sealed** | Read from the frozen phase-4 outputs / gold. |
| **Live re-run** | Produced just now by the frozen prompt + rule via the backend. |
| **Cached replay** | A previously recorded live run, replayed (presenter mode / offline). Shows the recorded timestamp. |
| **Unvalidated input** | Text the user pasted or edited; no gold; outside what was evaluated. |
| **Post-paper** (separate tag) | Analysis not in the paper (e.g. confidence model, triage, edit lab). |
| **Live ≠ sealed** (special) | Shown only when a live re-run differs from the sealed benchmark output; opens a field-level diff. |

### 0.3 HARD STOPS (the only reasons to stop and ask the human)

1. An audit check shows the **frozen rule or prompt hash in config does not match** the file on disk.
2. The ingest **number assertions in §3.3 fail** and the cause is in research data, not in UI code.
3. **Deployment credentials** (Azure, Gemini paid key) are missing — build and test everything locally, then ask for credentials only at deploy time.
4. Any change would require editing the **paper's reported numbers**.

---

## Phase A — Audit (do first; write `ui/AUDIT.md`)

Answer each item with file paths, counts, and a short verdict. These decide branches later.

### A1. Per-unit predictions for every system
Find the per-unit outputs for: `p2002_candidates`, `class_blind`, `class_aware`, `final_agentic`, `ablation_a`, `long_context`, `comparator`. For each record: path, format, unit count (expect 412; long_context answered 102 items), how abstentions are represented, and whether `matchedPid` is present.
- **Branch:** if any system's per-unit file is missing, that system's column is rendered as "per-unit output not released" in the case view and Failure Map — never filled from aggregates.

### A2. `inContext` / context paragraph IDs
Find what `phase4.retrieval_vs_reasoning` was computed from (per-unit list of context pids per system). Record path and field names.
- **Branch:** if missing for a system, the Failure Map shows plain red (wrong) for it without the retrieval/reasoning distinction.

### A3. Frozen rule semantics — **most important check**
Locate the comparator rule code (rule hash prefix `83664f8d9d8f…`) and system prompt (prefix `51f7ea78ed4b…`). Document precisely:
- the precedence (`same > different > none` per the master doc) and the exact conditions for each verdict;
- what `material` means and which fields can be material;
- **whether `actor` can trigger DIFFERENT.**

Reason: in the public snapshot, the comparator's correct DIFFERENT on `t1_md_13020::p00031|All India Financial Institutions` has **only** `actor: "A UCB" | "An AIFI"` (material) as a difference. Actor names differ across classes by construction. Elsewhere the model marks actor `equal` for "A CIC" vs "A bank", so it is inconsistent.
- **Branch A3-yes (actor can trigger DIFFERENT):** do **not** change the frozen rule. (1) In the Microscope, actor rows whose two values differ only by entity-class name get an inline note: *"Entity name differs by construction."* (2) Compute and record in `AUDIT.md` and on Method & Trust: how many of the 38 correct DIFFERENT calls and how many of the 70 false alarms remain DIFFERENT when actor-only differences are excluded (re-evaluate the frozen rule function with actor masked — a sensitivity analysis, not a replacement result). (3) Flag this in `AUDIT.md` as a candidate limitation line for the paper.
  - **Mandatory label** wherever this analysis appears (page, table, chart, tooltip, AUDIT.md): **"Post-paper sensitivity analysis — frozen benchmark result unchanged."** It must sit directly above or beside the numbers, never only in a footnote. The headline figures elsewhere on the site (38/78 etc.) stay the frozen ones.
- **Branch A3-no:** document which field(s) actually fired for each correct DIFFERENT and use that in the trace.

### A4. Null values under `differs`
In the public snapshot many rows read `status: differs` with one or both values `null`, e.g. `scope[differs, material]: null | null` is the **only** difference for `t1_md_13327::p00012|Payments Banks`. Compare `comparatorFields` in the snapshot against the **raw comparator JSON** for 10 such rows.
- **Branch A4-redaction (ingest nulls values over the word limit):** add an explicit value state `withheld` (rendered "value withheld — excerpt limit; open in presenter mode") distinct from `null` ("not extracted").
- **Branch A4-raw (model really returned null):** render as "not extracted" and keep the status as the model gave it. Add an "extraction anomaly" marker when `status=differs` and both values are null. Count anomalies in `AUDIT.md`.

### A5. Other artifacts
Record presence/paths of:
- T2 per-query rankings for BM25 / dense / hybrid / hybrid−source / class-aware hybrid on `t2_xclass_t1` (291) — needed for the class-filter animation.
- T3 items (52 scored) with as-of dates, amendment events and per-item predictions with filter on/off.
- Corpus matrix (11 regulated classes × 57 families, 296 populated, 9 ambiguous), Direction titles, subject families. (In the public snapshot `entityClasses`, `subjectFamilies`, `directions`, `matrix` are empty arrays — find out whether the public build strips them or they were never ingested.)
- Retrieval run logs per T1 unit (BM25/dense/RRF candidate lists, filter removals) — needed for X-Ray.
- The 30-item three-rater set with per-rater labels (for "hard for humans too").
- T4 per-answer RePASs scores and the 30 questions.
- `llm_calls` ledger (tokens per call) for the cost meter.
- `rehydrate.py`: can it rebuild one paragraph from its pointer deterministically and reproduce the stored sha256? Test on 5 pointers.

### A6. Current UI inventory
List the framework (looks like Vite + React with lazy routes `Home`, `Demo`, `ui`, `persona`), routes (`/`, `/findings`, `/demo`, `/how-it-works`, `/trust`), how `ui/scripts/ingest.py` builds `snapshot_public` and `confidence_model_v1`, what the persona switcher currently changes, and the deploy command for the `$web` container.

**Acceptance:** `ui/AUDIT.md` exists, every item has a verdict, every branch decision is written down.

---

## Phase B — P0 fixes (copy, confidence, hero, paper)

### B1. Confidence presentation for DIFFERENT verdicts
Facts (from `confidence_model_v1.json`, model M2): of the comparator's **38 correct DIFFERENT calls, 36 are Low and 2 are Medium, 0 High**. All 26 units the comparator recovers from the 56 that every LLM missed are Low. High band is almost entirely SAME answers (155 of 162). Comparator DIFFERENT precision on gold is **38/108 = 0.352**, recall **38/78 = 0.487**.

Change:
- When the comparator verdict is **DIFFERENT**, replace the generic band badge with **"Flagged for review"** and the line: *"When the comparator flags a difference, the expert agreed 35% of the time (38 of 108) and the comparator caught 49% of all real differences (38 of 78). Treat a flag as a reason to look, not a conclusion."* Keep the M2 band visible in a secondary "Confidence details" disclosure.
- When the verdict is SAME or NONE, keep the band badge (High/Medium/Low/Abstain) with its observed accuracy.
- Tag every confidence UI element **Post-paper** until the paper includes the confidence model (see B5).

### B2. Rename systems (everywhere: Results, Case view, Failure Map, charts)
Use these display names; put the internal id in a tooltip.

| id | Display name |
|---|---|
| `p2002_candidates` | Embedding match (P2-002 candidates) |
| `class_blind` | LLM with standard search |
| `class_aware` | LLM with institution-filtered search |
| `final_agentic` | **Our first pipeline** (institution filter + fact-checker) |
| `ablation_a` | LLM with standard search + fact-checker |
| `long_context` | LLM reading whole Directions (100K) |
| `comparator` | **Structured comparator** (pre-registered) |

On Results, Result 1 and Result 5: replace "AI with an automatic fact-checker" with "Our first pipeline (institution filter + fact-checker)". Add one sentence to Result 5: *"This was the system we originally built. It scored lowest on differences, which is why we designed the structured comparator."*

### B3. New homepage hero case
Candidate: **`t1_md_13005::p00071|Commercial Banks`** (topic: Cash Reserve Ratio and Statutory Liquidity Ratio; source class Rural Co-operative Banks). Both excerpts read nearly identically ("…The liabilities mentioned below shall not form part of liabilities of…"), the RCB version carries an extra exclusion the Commercial Banks version lacks (`exception: only_source, material`), it is in `missedA` (all five LLM systems missed it) and the comparator catches it.
Before using it, verify in rehydrated text that the exception is real and legible, and check the stray `scope` difference (it is just the class names — treat like A3).
**Fallback selection (if it fails verification):** from units with `missedA=true` and comparator judgement `different` matching gold, choose the one where (a) both excerpts look most similar (highest token overlap of the 12-word excerpts), (b) the decisive material field is `exception`, `threshold`, `amount`, `percentage`, `deadline` or `frequency` with a non-null value on at least one side, (c) not decided by actor alone. Record the choice and why in `AUDIT.md`.
Hero copy: *"These two rules look the same. They aren't. None of the five AI systems we tested noticed. Can you?"* → the hero becomes the first Spot-the-Difference round (Phase F), inline on Home.

### B4. "How it works" correction
Part 2 currently says "You choose your institution type, a topic or rule, and a date" and walks Search → Date check → Field-by-field comparison as one flow. Replace Part 2 with **two separate lanes**:
- **Lane 1 — Retrieval systems (evaluated on T1/T2/T3):** institution filter → keyword + meaning search → date check (T3) → LLM judgement → optional fact-checker.
- **Lane 2 — Structured comparator (targeted experiment):** the two candidate paragraphs the expert saw → 13-field extraction → fixed rule → verdict → confidence (*Post-paper*).
Add under the lanes: *"These were evaluated separately. The comparator has not yet been run on retrieved evidence; that is future work."*

### B5. Paper / master-document text fixes
Find the LaTeX/Docx sources. Make these edits (do not change any number):
- Limitations, last sentence: replace "…IndiaFinBench transfer or an ObliQA baseline, and the release has no UI." with "…IndiaFinBench transfer or an ObliQA baseline. A public inspection interface accompanies the release; it reads the sealed outputs and does not affect any reported result."
- Future Work: remove "and a user interface" from the list.
- Master doc §11 Scope Ladder item 7 and §12 rank 11: update to say an inspection UI was built after the scope ladder, reading sealed outputs only.
- AI-use statement: add "Claude Code also wrote the inspection interface and its build scripts under the authors' direction."
- **Optional subsection (only if the team wants the confidence model in the paper; otherwise keep it Post-paper):** *"Confidence. A logistic model over eight comparator-intrinsic features was fitted on the separate 30-item set (92 units) and frozen before gold evaluation. On the 412 gold units (base accuracy 297/412 = 0.721 [0.676, 0.762]), the High band was correct on 156/162 (0.963 [0.922, 0.983]), Medium 95/123 (0.772 [0.691, 0.838]), Low 46/125 (0.368 [0.289, 0.455]); ECE 0.087, Brier 0.148. High is assigned almost only to same answers; all but two correct different answers fall in Low."* Verify every number against `confidence_model_v1.json` before inserting.
- If A3-yes: draft (do not insert) a limitation line about actor-name differences for the authors to decide on; put it in `AUDIT.md`.

### B6. Smaller fixes
- Split the 1.5 MB snapshot into per-route chunks (home, results, cases index, per-case shards by itemId, confidence). Home should load < 150 KB of JSON.
- Persona switcher: wire it (see §13).
- Results page "See the comparator on real rules →" goes to `/cases`.

**Acceptance:** grep the built site — no "automatic fact-checker" without "Our first pipeline", no "Low" badge on any comparator DIFFERENT verdict, Home hero is the chosen case, How-it-works shows two lanes, paper diff contains only the text edits above.

---

## Phase C — P1 ingest (data layer for everything else)

### C1. Unit schema (one JSON shard per T1 item, `ui/public/data/cases/<itemId>.json`)
```ts
type Judgement = "same" | "different" | "none";
type SystemId = "p2002_candidates"|"class_blind"|"class_aware"|"final_agentic"|"ablation_a"|"long_context"|"comparator";

interface Unit {
  id: string;                 // "t1_md_13005::p00071|Commercial Banks"
  itemId: string;
  sourcePid: string; sourceClass: string; targetClass: string;
  topic: string;              // subject family
  route: "single-pass"|"retest-consistent"|"adjudicated";
  goldJudgement: Judgement; goldMatchedPid: string|null; goldFlag: "shared"|"class-specific"|"absent";
  shownCandidates: string[];  // the two P2-002 pids on the annotator sheet
  predictions: Partial<Record<SystemId, {
    status: "answered"|"abstained"|"not_run";
    judgement?: Judgement; matchedPid?: string|null;
    inContext?: boolean|null;           // gold matched pid in this system's context
    retryUsed?: boolean;                // verifier systems
  }>>;
  missedA: boolean; missedB: boolean;
  comparator: {
    parseOk: boolean; decisivePid: string|null; addressesSameDuty: boolean|null;
    perCandidate: {pid: string; verdict: Judgement; addressesSameDuty: boolean}[];
    rows: {                              // exactly 13, fixed order below
      field: Field; status: "equal"|"differs"|"only_source"|"only_target"|"absent";
      material: boolean;
      sourceValue: string|null|{withheld:true}; targetValue: string|null|{withheld:true};
      note?: "entity_name_by_construction"|"extraction_anomaly";
    }[];
    trace: RuleStep[];                   // from running the frozen rule in Python at ingest
  };
  confidence?: { model: "M2"; version: "confidence-v1"; p: number; band: "High"|"Medium"|"Low"|"Abstain";
                 contributions: {feature: string; value: number; z: number; weight: number; term: number}[] };
  provenance: { prompt_sha256: string; rule_sha256: string; model: "gemini-3.5-flash-lite";
                gold_sha256: string; results_sha256: string; snapshot_generated_utc: string };
}
type Field = "actor"|"action"|"object"|"scope"|"condition"|"threshold"|"amount"|"percentage"|"frequency"|"deadline"|"exception"|"documentation"|"reporting";
interface RuleStep { step: string; fields: Field[]; result: "pass"|"fail"|"fired"; verdict?: Judgement }
```
Pointers stay in a separate `pointers.json` (`id, mdId, clausePath, url, harvestDate, sha256, excerpt, directionTitle`).

### C2. Rule trace
Import the frozen rule function from the repo in `ingest.py` and evaluate it on each stored comparator output with tracing enabled (wrap, don't edit). Assert the traced verdict equals the stored verdict for all 412 units; fail the build otherwise. Store `trace`. The UI renders the trace; it never recomputes the rule in JS.

### C3. Build-time assertions (fail the build on any mismatch)
These are published numbers; ingest must reproduce them **exactly** from per-unit data:
- 106 items, 412 units; gold judgements same 213 / different 78 / none 121; flags shared 52 / class-specific 40 / absent 14; routes adjudicated 38 / retest-consistent 6 / single-pass 62.
- `missedA` = 56, `missedB` = 58; comparator correct on 26 of each; missed by every system incl. comparator = 32.
- **Recompute `missedA` and `missedB` per unit** from the ingested per-unit outputs of the five LLM systems (`class_blind`, `class_aware`, `final_agentic`, `ablation_a`, `long_context`), using the definitions in the master doc §9.8 (A: all five answered and none said *different*; B: count only systems that answered). Assert the recomputed boolean equals the stored flag **for every one of the 78 units**, not just the totals. The hero case and the game's "every AI missed this" claim depend on it; never trust the snapshot boolean alone.
- Retrieval vs reasoning on the 78 gold-different units:

| System | Errors | Retrieval | Reasoning | →same | →none |
|---|---|---|---|---|---|
| class_blind | 60 | 30 | 30 | 18 | 42 |
| class_aware | 71 | 12 | 59 | 32 | 39 |
| final_agentic | 76 | 12 | 64 | 13 | 44 |
| ablation_a | 70 | 30 | 40 | 8 | 41 |
| long_context | 73 | 4 | 69 | 43 | 30 |
| comparator | 40 | 0 | 40 | 6 | 32 |

- Comparator DIFFERENT: TP 38, FP 70, FN 40.
- M2 bands: High 162 (156 correct), Medium 123 (95), Low 125 (46), Abstain 2 (0).

If an assertion fails because of a UI-side join bug, fix it. If it fails because the research files disagree with the paper, **HARD STOP**.

### C4. Other ingests (as available per audit)
- `matrix.json`: classes × families with Direction ids and T1 item ids per cell.
- `t3.json`: 52 items: pid, as-of date, amendment events (date, type), gold status, prediction with filter on/off.
- `t2_rankings.json`: per query, the rank of the gold counterpart under each retriever (top-50 is enough).
- `irr30.json`: the 30-item three-rater set with per-rater labels (anonymised as rater 1–3).
- `t4.json`: per question, the four answer types' RePASs composite and human ratings.
- `triage_grid.json`: see Phase G.
- `cost.json`: tokens and estimated ₹/US$ per comparator call and for the full 412 run from the `llm_calls` ledger.

**Acceptance:** `npm run build` runs ingest, all assertions pass, the cases index lists 412 units, and a random sample of 10 units matches the raw files by hand.

---

## Phase D — P2 Case view `/case/:unitId` (the Diff Microscope)

Deep link format: `/case/<url-encoded unit id>?system=<SystemId>` (preselects that system in the predictions strip).

Layout, top to bottom:
1. **Header:** topic · source class → target class · badges (Benchmark · sealed) · gold route.
2. **Two paragraph cards** side by side (stacked on mobile): source and target excerpts (public) or full text (presenter/local), "Read the official text" link, paragraph id.
3. **Predictions strip:** one chip per system: verdict (or *Abstained* / *Not released*), ✓/✗ vs gold, and for wrong answers a small marker *"gold paragraph was in context"* when `inContext=true`. Expert verdict chip last, visually distinct. The selected system is highlighted.
4. **13-field Microscope:** fixed field order. Each row: field name · source value · target value · status chip (equal / differs / one side only / absent) · `material` marker · notes (entity name by construction, extraction anomaly, withheld). Clicking a row highlights that value in both paragraph cards **only if** it can be located by exact or normalised string match in the displayed text; label the highlight *"located by string match"*; otherwise show *"not located in displayed text"*.
5. **Decision trace** directly under the grid, rendered from `trace`:
   ```
   exception = only in source  [material]
   deadline  = equal
   scope     = equal
        ↓
   fixed rule (sha 83664f8d…) → DIFFERENT
   ```
   Caption: *"The model only extracts the fields. This fixed rule, frozen before any test run, decides the verdict."*
6. **Confidence:** B1 treatment; "Confidence details" disclosure shows the M2 feature contributions as a horizontal bar list (term = weight × z), the band thresholds, and the Post-paper tag.
7. **Provenance drawer ("Why can I trust this?"):** paragraph ids, Direction title, entity classes, source URL, harvest date, paragraph sha256, gold route, model + temperature, prompt sha256, rule sha256, confidence model version, results sha256, snapshot timestamp, and the current status badge.
8. **Actions:** "Re-run live" (Phase H; disabled with tooltip if backend offline), "Try an edit" (Phase I, presenter/local only), "Next case" within the current filter.

**Cases landing `/cases`:** must not open as a database browser. Lead with three large choice cards, full width on mobile:
1. **Can you spot the difference?** — *Challenge yourself on regulatory pairs.* → `/cases/play`
2. **Where do the models fail?** — *Explore the 78 real differences.* → `/cases/failures`
3. **Inspect a specific case** — *Search the benchmark.* → scrolls to the Explore section below.

Below the cards: the **Explore** section (filters: source class, target class, topic, gold judgement, comparator correct/incorrect, `missedA`, band, route; search by paragraph id), then sub-nav links to Failure Map, Play (and Atlas if K1 ships).

**Acceptance:** every one of the 412 units opens without errors; the hero case renders the expected trace; keyboard navigable; works at 375 px width and in dark mode.

---

## Phase E — P2 Failure Map `/cases/failures`

- Rows: the 78 gold-DIFFERENT units. Columns: the 6 LLM/comparator systems (+ P2-002 greyed, since it cannot output *different*).
- Cell states: **caught** (green), **wrong, gold in context → reasoning failure** (red, solid), **wrong, gold not in context → retrieval implicated** (red, hatched), **abstained** (grey), **not released** (outline only). Never use colour alone: add an icon/pattern and an accessible label.
- Row markers: a bracket/border on the 56 `missedA` rows; a star where the comparator recovers one.
- Sorting: default groups — recovered by comparator (26) → missed by everyone (32 incl. comparator) → others. Alternate sorts: by source class, topic.
- Header summary (computed from the data, must match §C3): "56 differences no LLM system caught · the comparator recovered 26 · in most errors the right paragraph was already in context."
- Click a cell → `/case/:unitId?system=<column>`.
- Drill-down toggle **"Why the comparator misses"**: filters to the comparator's 32 DIFFERENT→NONE errors and groups them by `addressesSameDuty` (per candidate), with the caption *"In most remaining misses the model decided the two paragraphs were not about the same duty — topic matching, not field extraction, is the next bottleneck."* Only show that caption if the data supports it (count and print the split).

**Acceptance:** cell counts per column match the errors column in §C3; clicking any cell lands on the right case with the system preselected.

---

## Phase F — P3 Spot-the-Difference `/cases/play` (and Home hero)

- Two modes, clearly labelled: **Curated hard cases** (drawn from `missedA`) and **Random draw** (uniform over all 412 units). Note under curated: *"Chosen because every AI system missed them; your score here is not comparable to overall accuracy."*
- Round flow: show both excerpts (or full text in presenter mode) with class names; hide every label. User picks Same / Different / No matching rule. Then reveal in this order with short delays (presentation only, not liveness claims): user's answer → expert → each system's chip → comparator → the decisive fields from the trace → link "Open in Microscope".
- Score only over rounds played: *"You 3/5 · best single AI system 1/5 · structured comparator 4/5"* where "best single AI system" is the best of the five LLM systems **over the same rounds**.
- Session score in memory; optionally remembered in `localStorage` inside try/catch (works without it).
- Home hero = round 1 of curated mode with the B3 case, inline.

**Acceptance:** no label leaks into the DOM before the guess (check with view-source/devtools); scores recompute correctly on a scripted run of 5 rounds.

---

## Phase G — P3 Triage simulator `/triage`

Heading: **"How much could a team let the system handle?"** Sub-heading: *"Observed trade-off on the evaluated test set — not a recommended threshold."* Tag: **Post-paper**.

- **Slider** over the M2 probability threshold *t* (0–1, snapping to observed probability values). For units with p ≥ t (auto-handled) show:
  - **Coverage:** % of the 412 units auto-handled.
  - **Accuracy among auto-handled** with 95% CI.
  - **Sent to review:** count and the accuracy of what's sent (to show review is where the errors are).
  - Split by comparator verdict (same / different / none) in a small table — makes visible that DIFFERENT almost never clears a high threshold.
- **CIs:** item-level bootstrap (resample the 106 items, 2,000 resamples), **precomputed at ingest**. Seed: use the evaluation seed the repo records (`results_v2.json → phase4.bootstrap.seed`, which reads `20261011` in the shipped snapshot); if the repo records a different one for confidence work, use that. Write in `AUDIT.md` which seed was used and where it came from. Do not describe it as "the paper's seed" — the paper text does not state a seed.
- CIs are computed for every distinct threshold → `triage_grid.json`. No bootstrapping in the browser.
- **Calibration panel:** reliability diagram from the `reliability` bins in `confidence_model_v1.json` (bins with n=0 shown as gaps), ECE 0.087, Brier 0.148, base accuracy 297/412.
- **How the score is computed:** list the 8 features with weights; pick any unit to see its contributions (reuse the Case view component).
- Presets: "Band thresholds as frozen" (snaps to the M2 band boundaries).

**Acceptance:** at the frozen High boundary the panel shows 162 units, 156 correct; numbers match `confidence_model_v1.json`; no text anywhere says "recommended", "optimal" or "safe".

---

## Phase H — P4 Backend + live comparator

### H1. Azure Function App (Python, Consumption plan)
The static website on Storage cannot host APIs, so create a separate Function App and set `VITE_API_BASE` in the UI build. CORS: allow only the site origin (+ `http://localhost:5173` for dev). App settings: `GEMINI_API_KEY`, `MODE=public|presenter`, `CACHE_CONNECTION`, `RATE_LIMIT_PER_MIN=6`.

Endpoints:
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | model reachable, prompt/rule hashes verified, cache reachable |
| POST | `/api/compare` | stream a comparator run (SSE) |
| GET | `/api/replay/{cacheKey}` | return a recorded run |
| GET | `/api/rehydrate/{pid}` | presenter mode only: full paragraph text via `rehydrate.py` |
| GET | `/api/freshness/{pid}` | Phase H4 |

### H2. `/api/compare`
- Body: `{ mode: "benchmark", unitId }` or `{ mode: "edit", unitId, edits: Edit[] }` or `{ mode: "paste", textA, textB, classA, classB }`.
- On cold start, load the frozen prompt and rule from the repo package, compute sha256, compare with the config hashes; if mismatch → `/api/health` reports failure and `/api/compare` returns 503. (Mirror of HARD STOP 1.)
- Benchmark mode: rehydrate the source paragraph and the two shown candidates server-side; call `gemini-3.5-flash-lite`, temperature 0, minimal thinking, JSON mode, frozen prompt, **streaming**. Same call shape as the sealed run (one call per unit over the two candidates).
- Stream to the client as SSE events: `status` ("receiving structured output…"), `field` (emitted **only** when a field object has fully parsed from the partial JSON — use an incremental JSON parser), `verdict` (after running the frozen Python rule with trace on the complete JSON), `confidence` (M2 computed server-side from the same features), `done` (cacheKey, latency, tokens), `error`.
- **Streaming fallback (decide during H, don't get stuck):** if the structured JSON cannot be parsed incrementally and reliably (partial chunks, SDK behaviour, Azure response buffering), switch to buffered mode: keep showing only *"Receiving structured output…"*, wait for the complete valid JSON, then render all 13 fields together. **Never manufacture per-field events** from a buffered response. Record which mode shipped in `AUDIT.md`; the UI copy must match it (no "fields appear as the model writes them" text in buffered mode).
- Cache key: `sha256(prompt_sha + rule_sha + model + mode + payload)`. Store full event log for benchmark and edit modes.
- **Paste-mode privacy (all required, test each):**
  - the cache stores only the input hash and the structured output — never the pasted text;
  - no request-body logging anywhere (Function logging level for this route excludes bodies);
  - no pasted text in Application Insights / custom telemetry / custom dimensions;
  - exception handlers and error traces must not include request payloads (strip `textA`/`textB` before logging any error);
  - the hash may identify a repeat input but the input itself is never retained.
  Verify by running paste mode with a unique marker string, then searching cache storage and App Insights logs for that marker; it must not appear.
- Rate limit per IP; return a friendly 429 that offers the cached replay.

### H3. Client — `/lab`
- **Re-run a benchmark pair:** pick a unit (or arrive from a case). Left: sealed output (Benchmark · sealed). Right: live stream (Live re-run). Rows appear as `field` events arrive; before that a neutral *"Receiving structured output…"* state — no per-field "checking…" text. When done, compare row by row with sealed; if anything differs show **Live ≠ sealed** with the field-level diff. Do not replace one with the other.
- **Paste mode:** two text areas + class selectors. Prominent warning above: *"Do not paste confidential or internal text. This runs on a third-party model API. Results on pasted text are unvalidated."* (If the team uses a paid API key with no-training terms, the first sentence may be softened; otherwise keep it.) Badge: Unvalidated input.
- If `/api/health` fails: Lab switches to replay-only with a banner *"Live service unavailable — showing cached replays."*

### H4. Freshness check (P4b — only if A5 showed `rehydrate.py` is deterministic)
- In the provenance drawer: button "Check against RBI's current source".
- Server fetches the RBI PDF from the pointer URL, re-segments with the repo's own code, finds the paragraph by clause path, normalises exactly as at harvest, hashes.
- Exactly three outcomes and copy:
  - **Matches benchmark snapshot** — *"The text at RBI's URL still hashes to the value in the benchmark (harvested <date>)."*
  - **Source differs from benchmark snapshot** — *"The text at RBI's URL no longer matches the harvested hash. This can mean an amendment, a re-issued PDF or a formatting change; it is not by itself evidence that the rule changed."*
  - **Could not verify** — fetch failed, PDF structure changed, or paragraph not located.
- Cache results 24 h. Never write "RBI amended this rule".

**Acceptance:** run 5 benchmark units live end-to-end locally; sealed vs live comparison renders; killing the network mid-stream yields a clean error and a replay offer; paste mode never persists text (inspect the cache).

---

## Phase I — P5 Presenter mode `/present` (not in nav)

- Full-screen, large type (min 24 px body), high-contrast theme, no nav chrome.
- **Preflight screen** before step 1: checks `/api/health`, warms the cache by running every live step once, verifies every replay exists, shows a green/red checklist. Button "Start".
- Scripted steps (→ next, ← back, `R` restart, `L` toggle live/replay, `B` big text, `F` fullscreen). Default script (~3 min):
  1. **Guess** — hero case, audience guesses.
  2. **Reveal** — expert + five systems missed it + comparator caught it.
  3. **Microscope** — 13 fields + decision trace.
  4. **Live re-run** — stream the comparator on the same pair; sealed vs live.
  5. **Edit** — one counterfactual edit, re-run (Phase J).
  6. **Triage** — slider moment.
  7. **Failure Map** — zoom out: it wasn't one case.
  8. **Close** — RePASs: copying the evidence scores 0.746 vs 0.371 for a genuine answer.
- Every live step has a recorded replay; in replay the Cached replay badge is visible on screen (honesty in front of an audience matters most).
- Presenter mode may show full RBI text from `/api/rehydrate` (or a local rehydrated corpus when run with `npm run present:local`). Public build must never include it.

**Acceptance:** the full script runs with Wi-Fi off using replays; the same script runs live with Wi-Fi on; timings fit 3 minutes.

---

## Phase J — P6 Counterfactual Edit Lab `/lab/edit` (presenter/local mode; public shows a read-only explainer)

- **Base pairs:** curate 6–10 units where the target paragraph actually contains an editable value for at least one of: frequency, deadline, threshold/amount/percentage, exception, approval/condition. Note: in the public data only 3 of the 38 correct DIFFERENT calls involve a numeric field (all frequency), so most base pairs should be SAME pairs (edit introduces a difference) plus a few DIFFERENT pairs (edit removes it). Optionally add a small **authored synthetic set** ("RBI-style", written by the team, licensed CC BY) badged *Synthetic*.
- **Structured edit buttons per field type** (no free-text editor in v1). Each edit is a deterministic text transform on the rehydrated target paragraph, previewed as a diff before running:
  - frequency: quarterly → monthly / annually
  - deadline: "within N days" → "within M days"
  - amount/threshold: change the number, keep units
  - percentage: change the number
  - exception: remove an exception clause / add "except where …"
  - condition/approval: remove "with the prior approval of …"
  - documentation/reporting: remove the reporting line
- **Control-run gate:** Step 1 always re-runs the unedited pair live. If the live output ≠ sealed output (any field status or verdict), show *"Control did not reproduce the sealed result — this edit cannot be interpreted"* and disable the conclusion panel (the edit can still be run, labelled uninterpretable).
- If control reproduces: run the edited pair. Result panel: *Was the edited field detected?* (its status changed to differs/one-side), *Did the verdict change?*, *Which other fields changed?* (side effects). Badges: Live re-run + Unvalidated input + Post-paper.
- Log every edit run (unit, edit, control result, outcome) for a future pre-registered minimal-pair study: **`lab_runs.jsonl` locally / in presenter-local mode; in deployed mode use the durable store behind `CACHE_CONNECTION` (Azure Table or append blob)** — never file appends inside a Function instance, since multiple instances make that unreliable. Add a note on the page: *"Exploratory. A formal minimal-pair sensitivity study would freeze the edit set before any run."*

**Acceptance:** each edit type runs once end-to-end on a base pair; the gate blocks interpretation when the control diverges (test by forcing a mismatch).

---

## Phase K — Remaining features (do all if time allows; otherwise cut per §15)

### K1. Class × Topic Atlas `/cases/atlas`
Heatmap 11 regulated classes × 57 subject families; filled = has Directions (296 cells), shade = number of T1 items. Click a cell → its Directions (titles, pointer links) and T1 items. Select a second class → highlight topics both classes have (parallel rules). Mark the 9 ambiguous cells. Data from A5/C4; if unavailable, skip.

### K2. T3 amendment timeline (Results → "Dates matter")
Per T3 item: horizontal timeline of amendment events with a draggable as-of marker. Two columns: *with date check* (status from the temporal filter) and *without* (the model's stored answer — "in force, original" on 48 of 52). State plainly: *"Earlier wording isn't available: RBI consolidates amendments in place, so the corpus has only current text."* Also show the circularity caveat (gold and filter share one parser).

### K3. T2 class-filter animation (Results → "Finding the rule")
Requires `t2_rankings.json`. One toggle **Institution filter OFF/ON**; for a selected query, animate the gold counterpart's rank from the hybrid run to the class-aware run, plus the distribution of ranks over all 291 queries. Use the real query only; caption that relevance labels cover only the target-class counterpart (gain partly by construction).

### K4. X-Ray per system (Case view → "How this system saw it")
Only from saved run logs. For retrieval systems: BM25 top-k, dense top-k, RRF merge, items removed by the institution filter (struck through), temporal state, the context given to the LLM, its answer, verifier retry/abstain. For the comparator: the two shown candidates → JSON → rule trace. **One view per system; never a combined pipeline.** If logs are missing, hide the tab.

### K5. "Hard for humans too" (Cases → Play, extra mode)
Rounds from the separate 30-item three-rater set where raters disagreed before adjudication; reveal each rater's label (anonymised) and the κ values (class judgement 0.774, flag 0.571). Caption that this set is outside the gold.

### K6. Cost & latency meter (Lab sidebar + Method & Trust)
Tokens and estimated cost per comparator call and for the full 412-unit run from the ledger; live calls show measured latency/tokens from the `done` event.

### K7. RePASs playground (Results → "Gamed metrics")
**Static part (ship this):** the four answer types for a chosen T4 question with their stored scores and the headline: concatenated − genuine = +0.375 [+0.325, +0.427].
**Live scorer: optional and outside the one-day critical path.** Attempt only after everything else is deployed and green. If attempted: a second Function or container with the pinned RePASs commit (`821d438d…`), DeBERTa-large-MNLI and LEGAL-BERT, CPU; a text box "write your own answer" and a button "paste the rule's sentences" to show the score jump. RePASs has no licence file — run it unmodified server-side only, do not redistribute it. Badge Unvalidated input.

### K8. Audience poll (presenter mode, optional)
QR code on the Guess step → mobile vote page → live histogram next to the systems' answers. Store votes in Azure Table keyed by session; display only, never used as data. Auto-expire after 24 h.

---

## 13. Final information architecture

Top nav: **Home · Cases · Lab · Triage · Results · Method & Trust**. Hidden: `/present`.

| Route | Content |
|---|---|
| `/` | Hero Spot-the-Difference round (B3) → the one-sentence positioning → 4 stats → three cards: Explore cases / Run the comparator live / See the trade-off |
| `/cases` | tabs **Explore · Failure Map · Play** (+ **Atlas** if K1 ships) |
| `/case/:unitId` | Microscope (Phase D) |
| `/lab` | Re-run benchmark pair · Paste (unvalidated) · Edit Lab (presenter/local) |
| `/triage` | Phase G |
| `/results` | existing Findings (rename route from `/findings`, keep a redirect) + K2/K3/K7 |
| `/method` | merged How it works (two lanes) + Trust & limits + licences + hashes + sensitivity analyses (A3) — redirect `/how-it-works` and `/trust` here |
| `/present` | Phase I |

Persona switcher (keep on Home): **Compliance** → highlight Triage + Explore filtered by your class; **Researcher/reviewer** → Failure Map + Method & Trust + "Hard for humans too"; **Evaluating the product** → Lab + cost meter. It only reorders Home cards and sets default filters; it never hides caveats.

---

## 14. QA, release checks and deploy

Run before every deploy:
1. `ingest` assertions (§C3) pass.
2. Honesty grep on `ui/dist`: fails on "recommended threshold", "optimal threshold", "automatic fact-checker" not preceded by "Our first pipeline", "checking threshold", any API key pattern.
3. Release check extended to `ui/dist/**`: no run of ≥30 words copied from the corpus; full-text endpoints absent from the public build.
4. Every route at 375 px, 768 px, 1280 px; light and dark; no horizontal scroll; keyboard navigation; colour-independent states in Failure Map.
5. Lighthouse: performance ≥ 85 on Home (after snapshot split), accessibility ≥ 95.
6. Backend: `/api/health` green; hash verification on; CORS restricted; rate limit tested; paste-mode cache contains no text.
7. Presenter preflight green with Wi-Fi on and replay-only run green with Wi-Fi off.
8. Click through: Home hero → reveal → Microscope → Re-run live → Failure Map cell → case → Triage → Results → Method.

Deploy: build with `VITE_API_BASE` set; upload `ui/dist` to the `$web` container (existing command from A6); deploy the Function App; smoke-test production with the checklist above. Write `ui/DEMO_RUNBOOK.md` with: how to start presenter mode, preflight, keyboard shortcuts, what to do if live fails (press `L`), and the 3-minute script.

---

## 15. Order of execution and cut order

Execute in this order: **A → B → C → D → E → F → G → H (H1–H3) → I → J → H4 → K1 → K2 → K3 → K6 → K5 → K4 → K7 static → K8 → K7 live.**

**Locked tiers:**
- **Must ship: A → B → C → D → E → F → G.** This needs no backend and alone turns the site into an interactive research demo. Deploy it as soon as G passes, before starting H.
- **Then, if infrastructure cooperates: H + I.** The static experience must keep working with the Function App down — every live control degrades to replay or a disabled state with a clear message. If H is not deployed, I still ships with its non-live steps (Guess, Reveal, Microscope, Triage, Failure Map, RePASs static); live steps are hidden and nothing is labelled Live.
- **Then J**, only if the control run reproduces the sealed output reliably in H testing (run the control on ≥5 benchmark pairs; if fewer than 4 reproduce, ship J as a read-only explainer and note it in `AUDIT.md`).
- **Everything in K is bonus**; K7 live scoring is last and fully optional.

If time runs out, cut **from the end** of the order above. Never cut A–G or the honesty invariants.

Final deliverables:
- Updated site deployed; Function App deployed (if H done).
- `ui/AUDIT.md` (audit answers, branch decisions, hero choice, A3/A4 counts, sensitivity analysis).
- `ui/DEMO_RUNBOOK.md`.
- Paper/master-doc text edits as a separate commit for the authors to review.
- A short `CHANGELOG` entry listing every user-visible change and every number the UI displays with its source file.
