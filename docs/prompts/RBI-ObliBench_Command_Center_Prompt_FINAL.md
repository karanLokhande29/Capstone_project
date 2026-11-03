# RBI-ObliBench Command Center — FINAL Build Prompt (v3)

> Paste this into Claude Code, run from the RBI-ObliBench repository root, and attach `reports/final/RBI-ObliBench_Master_Document_v1.md`.
> Order of work: **Part A (fix the deliverables) → Part B (analysis) → Part C (build)**. Stop for "go" between parts unless told to run straight through.

---

## 0. MISSION

Build the **RBI-ObliBench Command Center**: an interactive, explainable product layer over an existing research project, presentable both as a research tool and as a credible compliance product.

RBI-ObliBench is a benchmark built on 381 Reserve Bank of India Master Directions (76,188 paragraphs). It tests whether retrieval and LLM systems can tell **which regulated entity class an obligation binds**, **what one class must do that another need not**, **what a paragraph's status is on a date**, and **whether the RePASs faithfulness metric can be gamed**. A class- and date-aware RAG pipeline is evaluated on it. **The benchmark is the research contribution; the pipeline is the engineering artefact.** In research views, never invert that framing. In the Product views, the pipeline and comparator are the product, and the benchmark is the evidence behind it.

The product has three faces:
1. **Research Command Center** (REQUIRED): makes the project understandable, traceable, auditable and actionable for the authors, the faculty guide and reviewers.
2. **Obligation Explorer + Ask RBI-ObliBench assistant** (NEW OPPORTUNITY; Future Work #11 "A UI"): the compliance use case, with a **calibrated confidence score** on every answer.
3. **Product showcase** (NEW OPPORTUNITY): a pitch-quality overview that presents the strongest *true* results attractively, with the evidence one click away.

Work as a senior product manager, UX architect, staff frontend engineer, research-tooling engineer and ML-evaluation methodologist at once.

---

## 1. SOURCES OF TRUTH (in this order)

1. `reports/results_v2.json`: **every number**. Each displayed number carries its JSON key path (e.g. `phase4.t1_systems`, `tables.06_t2_retrieval.p3001`, `tables.10_ablations.rows`), shown on hover.
2. `reports/final/RBI-ObliBench_Master_Document_v1.md` (v2 after Part A): narrative, definitions, findings, limitations, the Future Work ranking.
3. `paper/aisigh/main.tex` + `paper/aisigh/tables/*.tex`: the paper's claims.
4. `data/rag_runs/` (system predictions on gold v1, including `sealed_phase4/comparator_t1_gold_v1/`), `data/benchmark/t1/t1_validated_v1.jsonl` (read-only): per-item data for the explorers and for confidence calibration.
5. `release/`, `configs/comparator_v1/`, `configs/p4_prompts_v1/`, `docs/protocol/`, `data/benchmark/templates/ANNOTATION_INSTRUCTIONS.md`: provenance, frozen prompts, pre-registration, guidelines.
6. `reports/final/error_analysis_v1.json`, `reports/tables/`.

If two sources disagree, never pick one silently. Log the disagreement as `Conflicting` in the Gap Analysis, with both paths.

---

## 2. HARD RULES (non-negotiable)

- **Frozen files are read-only:** `t1_validated_v1.jsonl`, `configs/comparator_v1/*`, `configs/p4_prompts_v1/*`, `results_v1.json`, `results_v2.json`, `refs_verified.bib`, the input manifests, and every reliability-plan file and amendment. Never write to them.
- **Write scope:**
  - Part A may edit only the *build scripts and generated outputs* listed in Part A.
  - Part C builds only inside a new top-level `ui/` directory.
- **Archive, never overwrite:** before regenerating any deliverable, copy the current version to an archive path with a timestamp suffix (the project's existing convention).
- **No git operations** unless the user explicitly asks.
- **LLM calls:**
  - Parts A and B, and the whole Research Command Center, make **zero** LLM calls.
  - Only the opt-in assistant and the live Obligation Explorer may call an LLM, and then only under the safeguards in §8.3.
- **Privacy:** never read, index or display anything under `reports/private/`, any rater-identity mapping, `data/benchmark/t1/t1v2_excluded/`, or `reports/private/final_push/extensions/`. Raters appear only as `rater_1`–`rater_3`. Never show absolute local paths, machine details or API keys.
- **RBI text:** "All Rights Reserved". Show **at most 25 words** of any paragraph, always with its pointer (`md_NNNNN::pNNNNN`, URL, harvest date, sha256). Fuller text appears only when rehydrated locally via `release/rehydrate.py`, and is never bundled into the build.
- **After every part:** `python3 -m pytest -q -o addopts= -p no:cacheprovider`, `python3 scripts/release_check.py`, `python3 scripts/check_paper.py`, `python3 scripts/build_tables.py --check` must all pass. If `ui/` trips the release check, add it to the documented exclusions; never weaken the check.
- **Never fabricate:**
  - No invented per-item predictions, business impact, accuracy figures or confidence values.
  - **Every confidence number must be computed by the method in §8.2 and validated against gold.** Never hard-code, floor, rescale or round up a confidence to make it look higher.
- **CIs are shown exactly as the project labels them** (`src/eval/ci_format.py` style, e.g. `+0.451 [+0.421, +0.481] (excludes 0 (above))`).

---

## PART A — FIX THE DELIVERABLES FIRST (before anything else)

**Timing.** The authors start rewriting the paper prose by hand on 2026-10-04. If `main.tex` has already been hand-edited after its generated timestamp (compare its mtime and contents against a fresh `build_paper_draft.py` output in a scratch dir), **do not regenerate it**. Produce `paper/aisigh/PATCHLIST_v1.md` with exact before/after sentences for the authors to apply by hand. The Master Document can always be regenerated.

Fix each issue **in the generator** (`scripts/build_master_document.py`, `scripts/build_paper_draft.py`, `scripts/build_paper_tables_final.py`, or the relevant brief/template they read), then regenerate. Never hand-edit a generated file.

| # | Issue | Fix |
|---|---|---|
| A1 | The Master Document's §15 References has LaTeX → Markdown leftovers: `urlhttps://…`, ``Xing Han L`u``, `Stefan B"uttcher` | Fix the bib → Markdown conversion: handle `\url{}`, `\href{}`, and LaTeX accents (`` \`u `` → ù, `\"u` → ü, etc.), e.g. via `pylatexenc` if available in the lock, or a small accent map. Add a unit test over all 20 entries asserting no backslashes, stray braces or `url` prefixes remain. Check the `.docx` too. |
| A2 | "Ablation A" names both a *toggle* (class filter, §9.7) and a *system* (`ablation_a` = class-blind + verifier, §9.3 / §9.8) | Keep "Ablation A/B/C" for **toggles only**. Display the system everywhere as **"class-blind + verifier"**: in the §9.3 row label, the §9.8 table, the paper and the tables. Internal ids stay unchanged. |
| A3 | Two class-filter-on-T1 numbers appear without context: −0.050 (no verifier, headline 2) and −0.049 (verifier on, ablation A) | Wherever either appears, state the condition: "class filter, without verifier" / "class filter, with verifier". Add one sentence in §9.7 noting both. |
| A4 | How abstentions / unanswered items enter F1 for the verifier systems (coverage 0.774–0.792) is never stated | Read the scoring code in `src/eval/`, and add one factual sentence in Master Document §9.2 and paper §Results describing exactly what the code does. Do not change the scoring. |
| A5 | The `different` F1 column has no CIs in the main T1 table, while the other columns do | If `results_v2.json` already contains CIs for it, show them. If not, **don't compute new statistics into frozen results**: add a table note "CIs not computed for this column", and list "add bootstrap CIs for `different` F1" under follow-ups. |
| A6 | RQ1 is worded around a "compliance question", but T2 operationalises it as counterpart retrieval from a source paragraph | Add one sentence in Master Document §2 and paper §Benchmark: "We operationalise RQ1's compliance question as a source obligation plus a declared target class (T2) and as per-class judgement (T1)." The RQ text stays verbatim. |
| A7 | "Hybrid − source class" is undefined | Read the retrieval code and add a one-line definition in §8 / §9.1. |
| A8 | Guideline versioning: "Guidelines v3" vs the "v3.6 rule" vs rules v3.1–v3.10 in the instructions file | Add one sentence clarifying that v3 is the guideline family, v3.x are rule revisions, and the flag derivation used is v3.6 (verify which in code). |
| A9 | "Majority (in-sample)" uses the gold distribution | Add a note that it is an in-sample reference baseline, not a deployable system. |
| A10 | Placeholders: 3 author emails + 1 Zenodo DOI | **Do not invent values.** List them in the readiness report; leave the `\placeholder{}` in place. |

**Bump the Master Document to v2** (`RBI-ObliBench_Master_Document_v2.md/.docx`; archive v1). Add a short "Changes from v1" section listing A1–A9.

Then rerun `scripts/scan_documents.py`, `scripts/check_paper.py`, the tests and the release check. **Every number in the documents must still match `results_v2.json` exactly.** Part A changes wording, never results.

**Part A report:** each fix as file:line before → after, the commands run with their results, and anything you could not fix and why.

---

## PART B — ANALYSIS BEFORE CODE

### B1. Project model (pre-digested; verify every line against the files)

**Research questions (verbatim, never paraphrase):**
- **RQ1 (Applicability):** Given a compliance question and a declared entity class, can a retrieval system return the obligations that bind that class, and how much does a class-blind dense retriever lose relative to a class-aware system?
- **RQ2 (Differential Obligation):** For a subject issued in parallel across entity classes, can the system identify what one entity class is required to do that another entity class is not?
- **RQ3 (Metric Integrity):** Does the documented gameability of RePASs reproduce on Indian regulatory text, and what minimal evaluation repair makes the metric resistant to concatenation/verbatim extraction?

**Tasks:**
- T1 (RQ1, RQ2): per-class `same` / `different` / `none` + matched paragraph; derived flag `shared` / `class-specific` / `absent`.
- T2 (RQ1): counterpart retrieval. Three sets: `t2_xclass_t1` n=291, `t2_xclass_p2002` n=53, `t2_supp_p2003` n=25, each with a documented retriever bias.
- T3: status on an as-of date; 60 built, 52 scored; circular by construction.
- T4 (RQ3): RePASs over genuine / concatenated / negated / off-topic answers; 30 questions, one rater, 2 flagged questions.

**Corpus:** 381/381 Directions, 76,188 paragraphs; 19 entity-class headings (11 regulated + 8 RBI function); 57 subject families; matrix of 1,083 cells, 296 populated, 9 ambiguous; defect D2 (3 empty titles); 162 "Updated as on" stamps; amended text only.

**Construction funnel:** 33,507 deontic-cue paragraphs → 28,694 candidates (rules v4, precision 0.929 [0.774, 0.980]) → matching (bge-base-en-v1.5 + lexical, threshold 0.757567, counterpart rate 0.883) → 123 sampled → 106 validated / 17 rejected. Routes 38 / 6 / 62. Flags 52 / 40 / 14. Judgements same 213 / different 78 / none 121.

**Systems:**
- Retrieval: BM25, dense, hybrid RRF, hybrid − source class, class-aware hybrid.
- T1: majority (in-sample), P2-002 candidates, class-blind LLM, class-aware LLM, final agentic (class filter + NLI verifier), class-blind + verifier, long-context (100K cap, 102/106 answered), and the **structured comparator** (13 fields; a fixed rule decides; frozen before any T1 run).
- All LLM systems: gemini-3.5-flash-lite, temperature 0, minimal thinking, JSON mode, frozen prompts.

**Seven headline findings.** Each is a first-class `Finding`:
1. The class filter improves retrieval: +0.451 [+0.421, +0.481] on `t2_xclass_t1` (partly by construction).
2. It doesn't translate into better T1 judgement: class filter without verifier −0.050 [−0.133, +0.027].
3. `different` is the core failure: 56/78 units missed by every LLM system (def. A), 58 (def. B). Mostly reasoning failures, not retrieval.
4. The verifier hurts T1: −0.068 [−0.132, −0.012]; coverage −0.217.
5. Long-context is competitive: +0.126 [+0.016, +0.240] collapsed F1 vs final agentic (same 102 items).
6. RePASs concatenation gameability reproduces: +0.375 [+0.325, +0.427]; negated and off-topic don't; ρ with `answers_question` 0.008.
7. The structured comparator: `different` F1 0.409, +0.255 [+0.094, +0.411] vs class-aware.

**Status (2026-10-03):** Phase 4 is scored on gold v1, and the master document and paper draft are written. **Venue: AISIGH–SD 2026, CMT deadline 2026-10-10**, IEEEtran, 6 pages (7 fallback, 8 hard max), not anonymous, similarity < 25%, AI content < 20%.

### B2. Personas

| Persona | Job | What they must see within 10 seconds |
|---|---|---|
| **Author team** (3 co-authors) | Ship by 2026-10-10 with no wrong number or over-claim | Days left, blockers, fragile claims |
| **Faculty guide / evaluator** | Judge rigour and each phase's contribution | The RQs, what was answered and what wasn't, and why |
| **Reviewer / researcher** | Decide whether to trust and reuse the benchmark | Construction, reliability, biases, reproduction |
| **Future maintainer** | Extend the benchmark (Future Work 1–11) | Dependencies, and the blast radius of a change |
| **Compliance analyst** (product persona) | "What must my entity class do here that an NBFC needn't?" | A field-by-field diff, source pointers, calibrated confidence |
| **Product evaluator / investor / jury** | "Is this a credible product?" | The strongest true results, a live demo, the trust and audit story |

### B3. Deliver this analysis, then wait for "go"

1. Your understanding of the project in 15 lines or fewer, plus anything in B1 you found to be wrong.
2. A file inventory: which §1 sources exist and are readable, and which keys and fields you'll use, including **whether per-unit predictions exist for every system on gold v1 and on the 30-item dev set** (needed for §8.2).
3. The verified gap list (seeds in §10: confirmed, rejected or added).
4. The final data model (§5), with any changes.
5. Information architecture: sitemap, navigation, deep-link scheme.
6. The screens, with their MUST / SHOULD / COULD tier and their empty states.
7. The intelligence rules (§8.1) and the confidence-calibration plan (§8.2), with the exact features, the data split and the validation metrics.
8. Technical architecture and folder structure.
9. Implementation phases and what each one proves.
10. Risks and assumptions: release-check interaction, missing data, RBI-text exposure, quota, and calibration sample size.

---

## PART C — BUILD

### 5. Data model (TypeScript types in `ui/src/domain/`)

```
ResearchQuestion { id: RQ1|RQ2|RQ3, text (verbatim), answeredStatus: answered|partial|unanswered, statusReason, findingIds[] }
Task             { id: T1..T4, rqIds[], datasetIds[], metrics[], caveatIds[] }
Dataset          { id, task, n, constructionStepIds[], biasStatement, sourcePath }
ConstructionStep { id (P1-004, P2-001..P2-004, P3-001, P3-002, P4-001, P5-001, Final), inputs[], outputs[], metrics[], decisionIds[] }
EntityClass      { id, label, kind: regulated|rbi_function }                       // 19
SubjectFamily    { id, label }                                                      // 57
MatrixCell       { classId, familyId, populated, ambiguous, directionIds[] }
Direction        { id md_NNNNN, title, subjectFamilyId?, classIds[], updatedAsOn?, defects[] }
ParagraphPointer { id md_NNNNN::pNNNNN, clausePath, url, harvestDate, sha256, excerpt (≤25 words)? }
T1Item           { id t1_<pid>, sourceClass, comparedClasses[≤4], route, goldFlag, classUnitIds[] }
ClassUnit        { itemId, classId, goldJudgement, goldMatchedPid?, predictions: {systemId: {judgement|abstain|unanswered, inContext}}, comparatorFields?, confidence? }
System           { id, displayName, family: retrieval|t1|baseline, description, model?, frozenPromptSha?, componentIds[] }
MetricResult     { systemId, datasetId, metric, value, ci?, ciLabel?, n, sourceKey }
PairedComparison { a, b, n, metric, delta, ci, ciLabel, sourceKey, preregistered }
Ablation         { id A|B|C, toggle, measure, n, delta, ci, ciLabel, sourceKey }
Finding          { id F1..F7, statement, evidenceIds[], caveatIds[], rqIds[], paperLocations[] }
Caveat           { id, kind: by_construction|circular|single_expert|small_n|bias|superseded|exploratory|in_sample, text, appliesTo[] }
Limitation       { id, text, futureWorkIds[] }
FutureWorkItem   { rank 1..11, item, what, why, effort, limitationIds[], dependsOn[], blastRadius[] }
ReliabilityStudy { id, design, raters, statistic, value, ci, n, inGold:false, caveat }
Decision         { id, decision, alternatives, rationale, date, record }
FrozenArtifact   { path, expectedSha256, actualSha256?, status: match|mismatch|unreadable }
PaperClaim       { id, section, sentence, numbers[], linkedEvidence[], lintFindings[] }
SubmissionTask   { id, title, due, dependsOn[], status, verifyCommand? }
GapFinding       { id, category, status: complete|partial|missing|unclear|conflicting|duplicate|needs_validation, expected, actual, sourceRefs[], reasonDetected, suggestedFix, fixedInPartA? }
Recommendation   { id, tier: REQUIRED|ENHANCEMENT|NEW_OPPORTUNITY, priority: MUST|SHOULD|COULD, why, evidence[] }
ConfidenceModel  { version, features[], bandThresholds, fittedOn, evaluatedOn, bands: [{band, n, accuracy, wilsonCI}], ece, brier, coverageCurve[] }
AssistantAnswer  { question, route: palette|grounded_llm|pipeline, answer, citations[], confidence: {band, empiricalAccuracy, ci, basis}, caveats[] }
```

**Data layer:**
- A `ProjectRepository` interface.
- `RepoAdapter`: `ui/scripts/ingest.ts` (or a Python ingest under `ui/scripts/`) reads the real files into a typed snapshot, `ui/src/data/snapshot.json`. It holds numbers, structure, pointers and predictions, plus at most 25-word excerpts. Every value records its file and key, and the snapshot records its timestamp and source sha256s.
- `FixtureAdapter`: uses only numbers printed in the Master Document. Any per-item fixture rows show a visible **"synthetic fixture"** watermark.

### 6. Traceability (the spine)

**Forward:** `RQ → Task → Dataset → Construction Step → System → Metric / Paired Comparison → Finding → Paper Claim → Caveat → Limitation → Future Work`
**Backward:** the reverse, from any node.

Chains that must work on day one:
- **RQ2 →** T1 → gold (106 items, 78 `different` units) → P2-002 + P2-004 → comparator vs class-aware → `different` F1 0.409 vs 0.154 → Finding 7 → paper §Results "Targeted experiment" → caveats (single-expert gold; P2-002 candidates shown on the sheets) → Limitation → Future Work #2.
- **Finding 1 ←** class-aware hybrid 0.894 vs hybrid RRF 0.443 → `t2_xclass_t1` → bias statement + target-class-only relevance → caveat `by_construction`.
- **T3 →** ablation B +0.462 → caveat `circular` → Future Work #6.
- **RQ3 →** T4 → concatenated − genuine +0.375 → repair ρ −0.126 → RQ3 = partial → Future Work #7.

Every node opens in a **right-side drawer** with tabs: *Overview · Evidence · Upstream · Downstream · Caveats · Source*. Breadcrumbs track the path, and all state is URL-addressable.

### 7. Screens

#### 7.1 Command Center (home) — MUST
Eight panels, each drilling down:
- **Where are we?** Phase timeline, and a live countdown to 2026-10-10.
- **What have we built?** Corpus, 4 tasks, 8 T1 systems, 5 retrievers, 3 ablations, the release.
- **What are we building?** Open tasks.
- **What is left?** The checklist and the Future Work count.
- **What is blocked?** Dependency-aware, e.g. "CMT ← final PDF ← DOI + page check ← prose rewrite".
- **What is wrong?** The top gaps, with reasons.
- **What next?** The top 3 actions, each with why and what it unblocks.
- **What can this become?** The top opportunities, tagged NEW OPPORTUNITY.

Below: a **Findings strip** of 7 cards, each with delta, CI, a ±0 marker and caveat chips.

#### 7.2 Research Question Explorer — MUST
Per RQ: the verbatim text → tasks → findings → answer status with reason (RQ3's repair half = partial) → the operationalisation note (A6).

#### 7.3 Results Lab — MUST
Tabs: T1 · T2 · Paired differences · Ablations · T3 · T4.
- The long-context row gets a "102 items" badge, and its comparisons auto-use the same-items numbers.
- A **forest plot** of all paired comparisons, with a zero line, coloured by excludes-0 direction, and a "pre-registered only" filter.
- T2 bias statements are pinned above their charts.
- T3's 1.000 is shown only with its circularity caveat.
- T4: RePASs vs human scatter (if per-answer data exists; otherwise ρ values + an empty-state note).
- Every cell: hover shows the source key; click opens the drawer.

#### 7.4 `different` Failure Explorer — MUST
- A grid of 78 gold `different` units × systems, coloured by prediction (✓ different / →same / →none / abstain / unanswered).
- A Definition A/B toggle (56 vs 58), with the definitions verbatim.
- Retrieval-vs-reasoning stacked bars (Master Document §9.8). Note that the comparator has 0 retrieval failures by design.
- Unit drawer:
  - the source vs compared class;
  - the gold pointer;
  - every system's answer;
  - the comparator's **13-field side-by-side** (actor, action, object, scope, condition, threshold, amount, percentage, frequency, deadline, exception, documentation, reporting) with differing fields highlighted;
  - the rule's decision path (same > different > none);
  - the unit's calibrated confidence band (§8.2).

#### 7.5 Benchmark Construction — SHOULD
- The funnel: 381 → 76,188 → 33,507 → 28,694 → 123 → 106 (17 rejected).
- Precision by rules v1–v4, with Wilson intervals.
- Routes, flags and judgements.
- The guidelines, with a flag-derivation diagram.
- P2-003 source decisions: FAQ 5/30 → validation only; enforcement 16/30 → weak labels.

#### 7.6 Annotation & Reliability — MUST
- Banner: **"Gold is single-expert. Agreement below is measured on a separate 30-item sample, not on the gold."**
- κ cards with n, CI and "in gold: no": class-row Fleiss 0.774, flag 0.571, not-obligation 0.392 (CI crosses 0), retest 0.426 / 0.550 (gap 11.7–18.6 h, recall caveat), timed re-label.
- The disclosure about candidates shown on the sheets.

#### 7.7 Corpus Atlas — SHOULD
- A 19 × 57 class × family heatmap (296 populated, 9 ambiguous). Clicking a cell lists its Directions.
- Defects: D2, and the 162 update stamps with the amended-text-only explanation.

#### 7.8 System Architecture Map — SHOULD
React Flow: query + class + as-of date → class filter → temporal filter → BM25 / dense / RRF → LLM judgement → NLI verifier (retry/abstain), plus the comparator path, the long-context path and the **confidence layer**. Clicking a node shows the systems using it, its ablation and its measured effect. Model revisions and prompt hashes sit in the node drawer.

#### 7.9 Claims ↔ Evidence Auditor — SHOULD (high value before 10 Oct)
- Parse `main.tex`, the table `.tex` files and the Master Document. Link every number to a `results_v2.json` key.
- Status: ✓ matched · ⚠ CI includes 0 but the wording asserts an effect · ✗ not found · ? ambiguous.
- Reuse `scripts/scan_documents.py` and `scripts/check_paper.py` logic or outputs; don't duplicate them.

#### 7.10 Gap Analysis — MUST
- Statuses: Complete / Partial / Missing / Unclear / Conflicting / Duplicate / Needs validation.
- Each finding opens to: Expected · Actual · Source · Reason detected · Suggested fix · *Fixed in Part A?*
- Seeded from §10. Verify each seed first.

#### 7.11 What Should We Build Next? — MUST
- **Before submission (dated)** lane.
- **After submission** lane: Future Work 1–11 in the authors' order. You may suggest a re-ranking only in a separate, marked panel.
- Each item shows: what, why, the limitation addressed, the findings it strengthens or could overturn, dependencies, effort, open questions, and the **blast radius** (results, tables, figures and paper sections to regenerate).

#### 7.12 Submission Readiness — MUST
- Dated checklist: 10-04 prose rewrite → 10-05 Overleaf compile + page check → 10-06 number audit → 10-07 Zenodo DOI + reproducibility check → 10-08 similarity / AI-content check → 10-09 final PDF → 10-10 CMT.
- Critical path, plus overdue flags against today's date.
- Live placeholder scan (currently 3 emails + 1 DOI).
- Venue constraints panel; unverified items are marked *Needs validation*.
- Each task's `verifyCommand` has a copy button. The UI never executes commands.
- A **Part A status** card.

#### 7.13 Provenance & Freeze Ledger — SHOULD
- Frozen artifacts with expected vs recomputed sha256.
- A pre-registration timeline: plan → amendments → comparator frozen on the dev set (one bug-fix revision) → sealed predictions → gold scoring. Make it visible that the freeze came **before** gold scoring.
- Decision log (public records only).
- LLM settings card.

#### 7.14 Obligation Explorer — COULD (product)
- Choose an entity class, a subject family, an as-of date and a comparison class.
- See obligations (pointers + excerpts of 25 words or fewer), the counterpart, the 13-field diff, a temporal badge with the amended-text-only warning, and a **confidence badge** (§8.2).
- **Offline mode** (default): browses the benchmark items and existing predictions only.
- **Live mode** (opt-in, §8.3): runs the real class-aware retrieval and the frozen comparator on a new query.
- Fixed footer: "Research system. Not legal or compliance advice."

#### 7.15 Ask RBI-ObliBench assistant — COULD (product)
A side panel; details in §8.3.

#### 7.16 Product Showcase — COULD (product)
Details in §9.

#### Global — MUST
- **⌘K command palette** (cmdk) with typed deterministic queries, at least:
  - "Which claims rest on a CI that includes 0?"
  - "Show everything that depends on the single-expert gold"
  - "Trace Finding 4 back to its RQ"
  - "Show `different` units missed by every LLM (definition A)"
  - "What breaks if the T3 parser is fixed?"
  - "Show all by-construction caveats"
  - "What's left before 10 Oct?"
  - "Compare comparator vs class-aware"
  - "Open Future Work #3"
  - "Show high-confidence answers that were wrong"
- Global search over ids (`t1_…`, `md_…`), entities, systems, findings, caveats and paper sentences.
- Deep links everywhere.
- Light and dark themes; keyboard navigation; responsive to 360 px (tables become cards).

### 8. Intelligence

#### 8.1 Deterministic rules (`ui/src/intelligence/`, pure functions with unit tests)
Every output carries `{rule, inputs, reason, sourceRefs}` and renders like this:

> **Claim check (R1)**: "The verifier hurts T1"
> Evidence: final agentic − class-aware, 3-way flag F1 −0.068 [−0.132, −0.012] (excludes 0 (below)). Source `phase4.t1_paired`.
> Verdict: supported ✓. Reason: the effect verb "hurts" is backed by a CI that excludes 0 in the asserted direction.

| ID | Rule | Trigger | Output |
|---|---|---|---|
| R1 | CI over-claim | Effect verb + a number whose CI includes 0, or excludes 0 in the opposite direction | ⚠, with the CI and a suggested hedge |
| R2 | By-construction | Any T2 result | Attaches the dataset's bias statement + target-class-only relevance |
| R3 | Circularity | Any T3 filter-on result | Attaches the caveat; blocks it from every "wins" or showcase view |
| R4 | Item-set mismatch | Long-context (n=102) mixed with n=106 numbers | Redirects to the same-items comparison |
| R5 | Single-expert dependency | Any T1-derived node | Inherits the caveat; feeds the blast radius |
| R6 | Number drift | A document number with no `results_v2.json` match (within rounding) | ✗ Conflicting, with both values |
| R7 | Placeholder | `\placeholder{}`, "DOI to be assigned", TODO, [verify] | Missing, linked to its task |
| R8 | Terminology collision | One label used for two things | Unclear (should be clear after A2) |
| R9 | Small-n slice | A per-source-class T1 view (7–15 items) | Wide-CI warning, or the slice disabled |
| R10 | Freeze integrity | Recomputed sha256 ≠ expected | Red banner on the ledger and everything downstream |
| R11 | Deadline risk | Past due, or slack < 1 day on the critical path | Escalates on home |
| R12 | Undefined scoring | Undocumented abstention handling | Unclear (should be clear after A4) |
| R13 | Missing CI | A metric without an interval where its siblings have one | Unclear (see A5) |
| R14 | Confidence honesty | A confidence shown without its band's empirical accuracy + CI, or a band with n < 20 | Blocks the display; shows "insufficient evidence" |

No numeric "health" or "risk" scores unless they come from a stated formula.

#### 8.2 Calibrated confidence score (MUST be honest; this is the product's main trust feature)

**Purpose.** Every judgement in the `different` Explorer, the Obligation Explorer and the assistant shows a confidence that means something checkable: **"Answers in this band were correct X% of the time on the RBI-ObliBench gold [Wilson 95% CI], n = N."**

**Unit:** one class unit (item × compared class), 412 on gold v1.

**Signals.** All of them come from predictions that already exist, so computing them needs **no new LLM calls**:
- **System agreement:** how many of {class-aware LLM, class-blind LLM, long-context, comparator} gave the same judgement as the displayed system.
- **Comparator decisiveness:** the number of the 13 fields extracted on both sides, the number of differing fields, and whether the rule's decision hinged on a single field.
- **Retrieval support:** whether the matched paragraph is the class-aware hybrid's top-1, and whether BM25 and dense agree on it.
- **Verifier signal:** NLI entailment / abstention, if the system recorded it.
- **Context penalties:** a long-context unit with no answer; amended-text-only Directions; ambiguous matrix cells.

**Method** (in the project's own pre-registration style):
1. Build a simple, transparent score: a weighted sum or a small logistic regression over the signals above. No black boxes. The weights must be readable in the UI.
2. **Fit and choose band thresholds on the separate 30-item development set (92 units)** if predictions exist there for the needed systems. If they don't, use **5-fold cross-fitting grouped by item** on gold, so no unit is scored by a model that saw it.
3. **Freeze** the score and thresholds (write `ui/src/data/confidence_model_v1.json` with its sha256) **before** evaluating on gold.
4. Evaluate on gold: per-band n, accuracy and Wilson CI; reliability diagram; ECE; Brier score; a **selective-prediction curve** (accuracy vs coverage).
5. Use three bands, **High / Medium / Low**, plus **"Abstain: insufficient evidence"**. A band with n < 20 is merged or not shown (R14).

**How to present it so it is both impressive and true:**
- Lead with the **selective-prediction result**: "When the system answers only at High confidence, it is correct X% [CI] of the time on Y% of cases." Choose the operating point on the dev set, never on gold, and report gold numbers. This is the highest accuracy you can honestly claim, and it's what compliance teams buy: *know when to trust it, and route the rest to a human*.
- Show the **reliability diagram** as a feature ("our confidence means what it says"), not something buried in an appendix.
- Show per-band accuracy next to every badge, e.g. `High · 8x% correct in benchmark [CI] · n=…` (the real numbers, whatever they are).
- **Never** rescale, floor, round up, or hard-code confidence. Never show a raw LLM self-reported probability as "confidence". If calibration turns out weak (e.g. High-band accuracy isn't clearly above Low), say so plainly on the screen and in your report, show the bands as "experimental", and don't use them in the showcase.
- Caveats on every confidence view: single-expert gold; Flash-Lite-class models; 412 units, so the intervals are wide.

#### 8.3 Ask RBI-ObliBench assistant + live mode (opt-in)

**Routing:**
1. **Palette route** (default, free): if the question matches a deterministic query or entity, answer from the snapshot with exact citations. Confidence basis: "exact: read from `<key>`".
2. **Grounded-LLM route** (opt-in): for open questions ("why does the verifier hurt T1?").
   - Retrieve from the snapshot plus Master Document sections (BM25 over local chunks), and pass only those chunks.
   - The model must answer only from them, cite each claim as `[key]` or `[MD §x]`, and reply "Not in the project record" if they don't support an answer.
   - Post-check every number in the answer against the snapshot. A mismatch blocks the answer and shows the R6 explanation.
   - Grounding badge: *Exact* (every claim cited and matched) / *Partial* (some sentences uncited) / *Unsupported* (blocked). Do not show a percentage here.
3. **Pipeline route** (live Obligation Explorer, opt-in): run the real class-aware retrieval + the frozen comparator prompt and rule on a new query. Attach the §8.2 confidence band from the frozen confidence model, and label it "calibrated on benchmark; new queries may differ".

**Quota and safety:**
- Off by default; enabled by a settings toggle.
- Uses **a separate env var (`ASSISTANT_GEMINI_API_KEY`) and a separate Google Cloud project** from the experiments, so it never touches the experiment quota.
- Its own daily cap (default 50), a response cache keyed by prompt hash, a visible counter, and graceful "quota reached" and offline states.
- Keys are read server-side only, through a tiny local proxy (`ui/server/`). Never put them in the browser bundle, never log them, never commit them.
- Every assistant answer has "Copy with citations" and "Open evidence".

### 9. Product Showcase (the "sellable" view; true numbers only)

A polished landing-style page inside the app (`/product`), separate from the research views. It presents the strongest **verified** results attractively, with a footnote marker on every number that opens its caveat and source.

**Positioning:** *"Entity-class-aware compliance intelligence for RBI Master Directions: it tells you what applies to **your** class, what's different from others, and when to trust the answer."*

**Hero proof points.** Use these exact values from `results_v2.json`, each with its caveat footnote:
- **Finds the right counterpart obligation:** class-aware retrieval nDCG@10 **0.894** vs 0.443 for standard hybrid search on `t2_xclass_t1` (footnote: by-construction bias).
- **Best-in-benchmark differential reasoning:** the structured comparator leads every system on 3-way flag F1 (0.616), collapsed F1 (0.838), judgement macro-F1 (0.680) and `different` F1 (0.409). On finding *what's different* it beats the class-aware LLM by **+0.255** `different` F1 (CI excludes 0). Footnote: point estimates; some pairwise CIs include 0; single-expert gold.
- **Explainable by design:** a 13-field side-by-side diff; the verdict comes from a fixed rule, not model guesswork.
- **Knows when to trust itself:** the calibrated confidence + selective-prediction result from §8.2. Show it only if the evaluation supports it.
- **Date-aware:** without the temporal filter, the LLM called 48 of 52 amended or deleted paragraphs "in force, original". Show this as the problem the product solves; **never** show the circular 1.000.
- **Audit-ready:** every answer has a paragraph pointer, a source URL, a harvest date and a sha256; prompts are frozen and hash-verified.
- **Tested against gamed metrics:** we showed that a popular faithfulness metric (RePASs) can be gamed by concatenation (+0.375), so our evaluation doesn't rely on it blindly.

**Sections:**
- the problem (the same subject regulated differently per class; amendments consolidated in place);
- how it works (an architecture graphic);
- a live demo (embedded Obligation Explorer);
- trust and evidence (reliability diagram, benchmark, limitations summary);
- roadmap (Future Work as the product roadmap: frontier models, cross-encoder reranking, broader temporal coverage, second-rater gold);
- coverage (381 Directions, 76,188 paragraphs, 19 entity classes, 57 subject families).

**Rules for the showcase:**
- Only numbers that pass R1 / R3 / R6 / R14.
- Every number has a footnote.
- A "View the evidence" button on every claim opens the research drawer.
- No invented customers, testimonials, ROI, time savings or market figures. If a commercial claim isn't measured, write it as a capability ("routes low-confidence answers to a human"), not a statistic.

### 10. Seed gap findings (verify each one; mark the Part A fixes)

| ID | Status | Finding | Part A |
|---|---|---|---|
| G-01 | Partial | T1 gold is single-expert; agreement is on a separate sample only | — |
| G-02 | Needs validation | T3 is circular (shared parser) and has the old-words parser defect | — |
| G-03 | Partial | RQ3's repair half isn't achieved (repair ρ −0.126, "not usable") | — |
| G-04 | Missing | Human error-category pass not done | — |
| G-05 | Missing | Zenodo DOI + 3 author-email placeholders | A10 (listed) |
| G-06 | Conflicting | "Ablation A" toggle vs system | A2 |
| G-07 | Unclear | −0.050 vs −0.049 class-filter numbers | A3 |
| G-08 | Unclear | RQ1 wording vs T2 operationalisation | A6 |
| G-09 | Unclear | Abstention scoring undocumented | A4 |
| G-10 | Unclear | No CIs on `different` F1 | A5 |
| G-11 | Unclear | Guideline version naming | A8 |
| G-12 | Unclear | "Hybrid − source class" undefined | A7 |
| G-13 | Needs validation | Majority baseline is in-sample | A9 |
| G-14 | Conflicting | Broken reference formatting in the Master Document | A1 |
| G-15 | Needs validation | Venue rules (registration, presentation, PDF eXpress, copyright) not verified on the venue site | — |
| G-16 | Partial | The 150K long-context run is superseded; check that no main-text number uses it | verify |
| G-17 | Unclear | Faculty guide not named in the project record | — |
| G-18 | Partial | Calibration rests on 412 single-expert units; confidence intervals are wide | — |

### 11. "If I were building this product" (produce this section; keep only ideas with a clear user benefit)

Seeds:
- **Pre-submission gate:** "0 unmatched numbers · 0 over-claims · 4 placeholders".
- **Blast-radius graph.**
- **Reviewer / viva mode:** a guided, deep-linkable tour.
- **Comparator field heatmap:** which of the 13 fields decide `different`.
- **Annotation workbench** for Future Work #1–#2, with enforced washout timers and per-item timestamps.
- **Snapshot diff** between results versions.
- **Human-review queue:** low-confidence answers routed to an analyst (the selective-prediction story as a workflow).
- **Exports:** PNG/SVG for slides; the gap list as Markdown.

Reject anything that only sounds impressive: no fake activity feeds, no invented velocity metrics, no ungrounded "AI insights".

### 12. Prioritisation

- **MUST:** Command Center, traceability drawer, Results Lab, `different` Explorer, Reliability, Gap Analysis, Submission Readiness, palette, R1–R7, R14.
  *Reason:* these answer "is it sound, and what's left before 10 Oct?"
- **SHOULD:** Claims Auditor, Construction, Corpus Atlas, Architecture Map, Provenance Ledger, blast radius, R8–R13, **confidence calibration (§8.2) computed offline**.
- **COULD:** Obligation Explorer, the assistant, the Product Showcase, reviewer mode, snapshot diff, annotation workbench, review queue, exports.
  *Reason:* product opportunities beyond the research questions; Scope Ladder cut 7 kept the UI out of the paper.

Explain any deviation.

### 13. Implementation

**Stack:** Vite + React + TypeScript (strict), Tailwind CSS, shadcn/ui, Lucide, Recharts, @xyflow/react, cmdk, TanStack Table, Zustand, React Router, Vitest + Testing Library. The local proxy for the opt-in LLM routes is minimal Node (Hono or Express).

**Visual direction:** original, dense-but-calm, inspired by the usability of Linear, Vercel, Stripe and GitHub. Not a dashboard template. CI-aware number components are the visual signature: a point, an interval bar and a zero tick.

**Folder structure:**
```
ui/
  scripts/ingest.ts             # repo → src/data/snapshot.json (numbers, structure, pointers, predictions; ≤25-word excerpts)
  scripts/calibrate.ts|py       # §8.2: fit on dev (or grouped CV), freeze, evaluate on gold → confidence_model_v1.json + report
  server/                       # opt-in assistant/pipeline proxy; keys server-side only
  src/domain/                   # §5 types
  src/data/                     # ProjectRepository, RepoAdapter, FixtureAdapter, snapshot.json, confidence_model_v1.json
  src/intelligence/             # R1–R14 + tests
  src/features/<screen>/        # one folder per §7 screen
  src/components/               # drawer, CICell, CaveatChip, ForestPlot, ConfidenceBadge, ProvenanceTooltip
  src/lib/ci.ts                 # parse/format CIs exactly like src/eval/ci_format.py
  README.md                     # ingest, calibrate, run, test; what is shown and what isn't, and why
```

**Phases:**
1. **Part A fixes + verification** (proves: the deliverables are clean).
2. **Ingest + domain + CI component** (proves: every number traces to a key).
3. **Command Center + Results Lab + drawer** (proves: the core loop works).
4. **`different` Explorer + Reliability + Gap Analysis** (proves: the hard findings are explorable).
5. **Submission Readiness + Claims Auditor + R1–R14** (proves: it protects the 10 Oct submission).
6. **Confidence calibration offline** (proves: the confidence is honest; report the numbers *before* any UI uses them).
7. **Atlas, Architecture, Provenance, palette queries.**
8. **COULD:** Obligation Explorer (offline first, then live), the assistant, the Product Showcase.

**States for every screen:** loading skeletons; empty states naming the missing file and the command that produces it; error states for unreadable or hash-mismatched files; a synthetic-fixture watermark; assistant states for off / quota reached / offline / blocked (unsupported).

**Tests:** unit tests for R1–R14, the CI parser and the confidence model. A test that greps `ui/dist` for any RBI run of more than 25 words and for key-like strings. A test that confidence values in the UI equal the frozen model's outputs (no post-hoc scaling).

### 14. Quality bar (review as the product lead)

- Can a new reader state the 3 RQs and the 7 findings after 60 seconds on home?
- Does every number show its source key and CI, read correctly against 0?
- Can I go from "+0.255" to the RQ, the 78 units, the 13-field diff and the single-expert caveat in ≤ 4 clicks, and back?
- Is it impossible to see T3's 1.000 or T2's +0.451 without their caveats?
- Does every confidence badge show its band's empirical accuracy, CI and n? Was the model frozen before the gold evaluation?
- Could a sceptical reviewer verify every showcase number in one click?
- Does the assistant refuse rather than guess, and does it never spend experiment quota?
- Does home tell the authors exactly what blocks submission today?
- Is there zero RBI text over 25 words in `ui/dist`, and do pytest, release_check, check_paper and build_tables --check all pass?
- Are product and showcase views clearly separated from research results?
- Is anything on screen that doesn't serve a persona in B2? Remove it.

**Final report:**
- the Part A fixes, as before/after;
- what you built;
- the calibration results: the real numbers, including if they're weak;
- the commands run and their results;
- what you couldn't do and why.

**The goal:** Master Document → fixed deliverables → verified product model → traceable, explainable, honestly calibrated views → a credible research tool and a credible product.
