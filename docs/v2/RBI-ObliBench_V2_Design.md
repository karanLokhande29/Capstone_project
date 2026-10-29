# RBI-ObliBench V2: topic alignment and field-level evidence verification

- **Status:** design; milestones 1–2 built; both allowed dev runs used (29 Oct). **On the IRR-30 dev set, run 1 made
  V2-A worse than V1 and run 2 (revised prompt) made it better; run 2's gain is dev evidence only, partly tuned on
  the dev errors and not significant** (see §9). No T1 run, no T1 result, no improvement claimed.
- **Date:** 29 Oct 2026
- **Rule zero:** V1 is frozen. V2 lives in new modules (`src/rag/v2/`, with its prompts in `src/rag/v2/prompts/`) and writes new run folders
  under `data/v2_runs/` (outside the guard's roots). It never edits these:
  - `src/rag/comparator.py` or `src/rag/comparator_rule.py`;
  - `configs/comparator_v1/` or `configs/p4_prompts_v1/`;
  - the sealed runs or any gold file.
- A regression test (`tests/test_v2_alignment.py::test_v1_frozen_artefacts_unchanged`) checks the V1 hashes on every
  run.
- **Why the prompts are not under `configs/`:** AuditGen's research-integrity guard
  (`tests/test_auditgen_core.py::test_research_files_unchanged_since_the_build_snapshot`) fails on any new file under
  its research roots (`configs/`, `reports/`, …) relative to the 15 Oct build snapshot. V2 therefore keeps its files
  outside those roots. Its own freeze record (`src/rag/v2/prompts/FROZEN.json`, checked by `Prompts(expected=…)`)
  protects the frozen V2 prompts, as `FROZEN.json` does for V1.

## 1. What V2 targets, from the committed numbers

Error counts come from Master Document v2 §9.8–9.9. The "Problem" column is the design hypothesis, not a finding.

| Failure | V1 evidence | V2 component | Problem the component addresses |
|---|---|---|---|
| The comparator misses gold `different` units | 40 of 78 missed (`different` recall 0.487, precision 0.352) | A | — |
| …most of them as `none` | 32 of the 40 → `none`, 6 → `same`, and 0 retrieval failures, because both candidates are fixed | A | V1 decides `addresses_same_duty` and the 13 fields in one call. A differing requirement may be read as "not the same duty". |
| The P4 NLI verifier rejects correct answers | 59 correct first-pass judgements became abstentions (final agentic). Coverage −0.217. | D | A whole-paragraph NLI premise is a poor test for a one-sentence claim |

Two corrections to the brief:

- **The 59 abstentions belong to the P4 verifier, not the comparator.** The comparator has no verifier. Option D is a new
  verifier for V2's field claims. Its design target is the P4 failure mode, so its "correct claims rejected" count is
  measured against the P4 verifier rule run on the same claims.
- **LangGraph runs only in `external/.venv-langgraph313`** (Python 3.10–3.13). The main environment is Python 3.14. So
  V2 follows the extension #9 pattern: a plain-Python pipeline is the reference, a LangGraph port re-expresses it, and a
  cache-only equivalence test must pass on every unit. No reported number may depend on the graph.

## 2. Reusable components (actual interfaces)

| Component | File | Interface V2 uses |
|---|---|---|
| LLM client | `src/llm/client.py` | `LLMClient.complete(messages, *, role="default", max_output_tokens=None) -> Completion(text, provider, model, model_version, input_tokens, output_tokens, cached)`. Disk cache, quota ledger (soft cap 480 per Pacific day), call cap, no provider mixing. Built by `scripts/run_p4.py::make_llm(cfg, resolver, run_id=…)`. |
| V1 comparator | `src/rag/comparator.py` | `Prompts(dir, expected)`, `parse_candidates(cell) -> [(pid, text)]`, `parse_response(text, ids)`, `compare_unit(llm, prompts, unit, *, max_output_tokens)`, `evaluate(results, gold)`. A unit is `{item_id, source_class, source_text, target_class, candidates: [(pid, text)]}`. |
| V1 rule | `src/rag/comparator_rule.py` | `FIELDS` (13), `MATERIAL` (11), `COMPARISONS`, `candidate_verdict(c)`, `class_verdict(cands)`, `RULE_VERSION = "comparator-rule-v1"` |
| Sealed V1 comparator outputs | `data/rag_runs/sealed_phase4/comparator_t1_gold_v1/*.json` (412) | Each `raw` holds the model's JSON with `fields` and `field_comparison` for **every** candidate, including candidates judged not the same duty. V2-A can therefore reuse V1's field comparisons unchanged. |
| Dev set | `scripts/run_comparator.py::dev_units()` | The 30-item IRR set, 92 class units, with adjudicated consensus. No overlap with the T1 sample is checked by the code. The only data V2 may be developed on. |
| V1 dev run outputs | `data/rag_runs/comparator_dev_irr30/` (92) | The same structure as the sealed outputs. V2-A dev runs reuse them. |
| NLI verifier | `src/rag/pipeline.py::NLIVerifier` | `cross-encoder/nli-deberta-v3-xsmall` at a pinned revision. Argmax entailment. |
| Evidence helpers | `src/auditgen/genai.py` (`norm`, `quote_in`, `numbers`) | Same idea, re-implemented in `src/rag/v2/evidence.py`, so that `src/rag` does not import the application layer |
| Metrics and bootstrap | `src/eval/metrics.py`, `src/rag/analysis.py` | `f1_scores`, and a paired item bootstrap (2,000 resamples, seeded) |
| LangGraph pattern | `src/rag/graph_t1.py`, `scripts/run_langgraph_equivalence.py` | Nodes call the plain-Python functions. Equivalence is checked cache-only. |

## 3. New modules

| File | Milestone | Role |
|---|---|---|
| `src/rag/v2/schemas.py` | 1 ✅ | Label vocabularies and dataclasses for alignment results (verifier states are reserved here for M3) |
| `src/rag/v2/evidence.py` | 1 ✅ | Quote normalisation and checking, and number extraction (word numbers included, for M3) |
| `src/rag/v2/topic_aligner.py` | 1 ✅ | Agent 1: prompts, rendering, strict parsing and validation, `align_unit` |
| `src/rag/v2/prompts/topic_alignment_{system,user}.txt` | 1 ✅ | Agent 1 prompt, **draft**. It is frozen by sha256 after the dev run and before any T1 call. |
| `src/rag/v2/field_comparator.py` | 3 | Agent 2's new extraction, which carries an evidence span per field (V2-D, V2-A+D). V2-A needs no new module: `decision_v2.v1_candidates` re-parses V1's own answer with V1's parser. |
| `src/rag/v2/decision_v2.py` | 2 ✅ (A); 3 (D) | The deterministic rule. M2 has `decision-rule-v2-a`: the alignment override, then V1's rule unchanged, with a per-candidate trace. It refuses a V1 record whose stored judgement does not follow from its raw answer. M3 adds the verifier states. It is frozen with the prompts. |
| `src/rag/v2/eval_v2.py` | 2 ✅ | `score` (V1's `comparator.evaluate` plus `none` precision) and `flips` (fixed / broken / other, with moves) |
| `src/rag/v2/field_verifier.py` | 3 | Agent 3: span check, then numeric check, then NLI on the short span, then one bounded repair |
| `src/rag/v2/pipeline_v2.py` | 4 | The plain-Python reference orchestration |
| `src/rag/v2/graph_v2.py` | 4 | The LangGraph port (runs in the 3.13 venv) |
| `scripts/run_v2.py` | 2 ✅; 3–5 | M2: `plan` (0 calls), `dev` (gated; 92 calls; cap 100; refuses if frozen, over the day's quota, or after 2 prompt versions), `evaluate-dev` (0 calls). Later: `freeze`, `t1`. |
| `scripts/eval_v2.py` | 5 | Scores all four systems on T1, with paired bootstrap against V1 |
| `tests/test_v2_alignment.py` | 1 ✅ | Mock LLM. Same-duty, different-duty, ambiguous, fabricated-quote and failure cases. V1 hash regression. |
| `tests/test_v2_decision.py` | 2 ✅ | The override table; V1 none → V2-A different; aligner `no`; `uncertain`/missing keep V1; precedence; unparsed V1; tampered V1 refused; flips; runner refusals; fixture end-to-end; V2-A with no aligner input reproduces V1 on all 92 dev and 412 sealed T1 units |
| `tests/test_v2_verifier.py`, `tests/test_v2_graph.py` | 3, 4 | — |

## 4. Data flow

```
unit {item_id, source_class, source_text, target_class, candidates[(pid, text)] ×≤2}   ← the same fixed candidates as V1
  │
  ├─ Agent 1  topic_aligner.align_unit ──── 1 LLM call per unit (both candidates in one call)
  │           → per candidate: same_underlying_duty yes|no|uncertain, 5 dimensions, 2 quotes
  │           → code checks: ids, vocabulary, quotes occur verbatim (normalised) → else downgrade to "uncertain"
  │
  ├─ Agent 2  field_comparator
  │           V2-A: V1's sealed field_comparison per candidate (0 calls)
  │           V2-D / A+D: new extraction, each field value with an evidence span (1 call per unit)
  │
  ├─ Agent 3  field_verifier (V2-D, A+D) ── 0 LLM calls by default; ≤1 repair call per unit
  │           per claim: span-in-text → numbers agree → NLI(short span ⇒ claim) → supported | contradicted |
  │           insufficient_evidence | uncertain
  │
  ├─ decision_v2 (deterministic, frozen) → same | different | none | unsure, matched_paragraph_id, trace
  │
  └─ explanation (optional, demo only): verified sentences citing the spans; never feeds the verdict
```

**Decision rule for alignment** (to be frozen in `decision_v2.py` at milestone 2). Per candidate, the duty flag is:

- `yes` → `True`;
- `no` → `False`;
- `uncertain`, or a failed parse → V1's own `addresses_same_duty` for that candidate.

The V1 per-candidate and class precedence then applies unchanged. So V2-A changes V1 only where the aligner is
confident and its quotes check out, and every change can be traced to one aligner answer.

## 5. JSON schemas

### Agent 1 output (model → code)

```json
{"source_id": "md_NNNNN::pNNNNN",
 "alignments": [
   {"candidate_id": "md_NNNNN::pNNNNN",
    "dimensions": {"actor": "same|different|unclear", "action": "…", "object": "…",
                   "regulated_activity": "…", "purpose": "…"},
    "same_underlying_duty": "yes|no|uncertain",
    "source_evidence": "exact quotation from the source, or null",
    "candidate_evidence": "exact quotation from this candidate, or null",
    "reason": "one short sentence"}]}
```

This departs from the brief's single-pair schema on purpose. One call covers both candidates of a unit, so T1 costs 412
calls, not 824 (the soft cap is 480 per quota day).

### Agent 1 record (code → disk), one file per unit

| Key | Meaning |
|---|---|
| `item_id`, `source_id`, `target_class` | Which unit this is |
| `alignments[]` | One entry per candidate: `candidate_id`, `same_underlying_duty` (after validation), `model_label` (before validation), `dimensions`, `source_evidence`, `candidate_evidence`, `evidence_ok`, `reason`, `problems[]` |
| `parse_problems[]` | Unit-level problems; non-empty means every candidate is `uncertain` |
| `raw`, `cached`, `model`, `model_version` | As the model answered |
| `prompt_sha256` | Added by the runner |

### Agent 3 claim (milestone 3)

```json
{"claim_id": "…", "candidate_id": "…", "field": "deadline", "side": "source|target",
 "value": "within 15 days", "evidence_span": "within fifteen days",
 "checks": {"span_found": true, "numbers": "match|mismatch|none", "nli": "entailment|neutral|contradiction|skipped"},
 "status": "supported|contradicted|insufficient_evidence|uncertain", "repaired": false}
```

## 6. Implementation order

1. **M1, Topic Alignment Agent** (done ✅): schemas, evidence helpers, prompt draft, aligner, unit tests.
2. **M2, decision rule and V2-A, dev only:**
   - `decision_v2.py` (alignment override) and `run_v2.py plan|dev|evaluate-dev` (built ✅; the dev run itself waits
     for the gate);
   - every prompt version gets its own folder, `data/v2_runs/alignment_dev_irr30_<tag>/` (tag from the prompt and
     code sha256), so all dev runs are kept; at most 2 versions, following V1's one-revision precedent;
   - the dev run writes the LLM cache and quota ledger under `data/llm_cache`, a guard root, as every P4 run does; the
     guard test will then report it, and refreshing the snapshot is Karan's call;
   - 92 dev units, about 92 calls, scored against the IRR consensus;
   - prompt edits allowed only on dev, and every dev run kept.
3. **M3, field verifier:**
   - deterministic checks first, then local NLI on short spans;
   - a bounded repair: at most one call per unit, and only for `uncertain` claims;
   - fixture tests for paraphrase-accepted, number-mismatch, missing-span and contradiction cases.
4. **M4, orchestration:** `pipeline_v2.py`, then `graph_v2.py`, then the cache-only equivalence test on the 92 dev
   units.
5. **Freeze:** sha256 of the prompts, `decision_v2.py` and `field_verifier.py`, written to
   `src/rag/v2/prompts/FROZEN.json` **before any T1 call**.
6. **M5, T1 evaluation:** the four systems on the 412 T1 units with V1's fixed candidates. This takes about 412 calls for
   V2-A and about 412 more for D's extraction, so 2–3 quota days.
7. **M6, demo:** V1 against V2 on a case V1 got wrong, chosen by a rule written before looking at V2 outputs.

## 7. Evaluation and regression plan

**Systems** (same 412 units, the same two candidates per class, the same model and parameters):

| System | Alignment | Fields | Verifier |
|---|---|---|---|
| V1 comparator | V1 (in the same call) | V1 | none |
| V2-A | Agent 1 | V1 sealed | none |
| V2-D | V1 | new extraction with spans | Agent 3 |
| V2-A+D | Agent 1 | new extraction with spans | Agent 3 |

**Measures** (paired item bootstrap, 2,000 resamples, seed fixed in advance):

- `different` precision, recall and F1;
- judgement macro-F1 and 3-way flag macro-F1 (rule v3.6);
- coverage;
- **`none` precision**, the guard against an aligner that simply says "yes" more often;
- for D: the unsupported-claim rate, and correct claims rejected, compared with the P4 rule on the same claims.

**Pre-registered comparisons:**

- V2-A − V1;
- V2-D − V1;
- V2-A+D − V1;
- V2-A+D − V2-A.

All are written into `src/rag/v2/prompts/FROZEN.json` with the freeze.

**Integrity rules:**

- Develop only on the IRR-30 dev set and on fabricated fixtures, never on T1 gold, the rejected-17 or the packet items.
- Seal the T1 predictions (sha256 manifest) before scoring.
- Report the result whatever its sign. The brief's 0.55 `different` F1 is a target, not an expectation.

**Regression tests (every run):**

- the V1 frozen hashes (comparator prompts and rule) still match `configs/comparator_v1/FROZEN.json`;
- the P4 prompt hashes still match `p4.prompt_sha256` in config;
- the full test suite still passes.

**A second, end-to-end experiment (later, labelled exploratory):** V2 with newly retrieved candidates. The gold covers
only the two shown candidates, so new matches need fresh labels before they count.

## 8. Risks

- **The aligner says `yes` too freely.** Gold `none` makes up 121 of the 412 T1 judgements. Reporting `none` precision
  makes this visible.
- **Flash-Lite JSON reliability** with a longer schema. Parse failures fall back to V1 behaviour, and the count is
  reported.
- **Quota.** 480 per day, shared with nothing else. `run_v2.py plan` prints the calls needed before any run.
- **Quote checking is lexical.** A model can quote real text that does not support its label. The quote proves the
  evidence exists, not that the reasoning is right.

## 9. Dev runs (IRR-30, development evidence only)

### Run 1

Prompt tag `016a4418`, model `gemini-3.5-flash-lite` at the P4 settings, 92 calls, 0 parse failures, 3 of 184
candidates downgraded by the quote check. Records: `data/v2_runs/alignment_dev_irr30_016a4418/`; report:
`data/v2_runs/reports/alignment_dev_eval_016a4418_20261029T043808Z.json`.

| System | Macro-F1 | `different` F1 | `different` recall | `none` precision |
|---|---|---|---|---|
| V1 | 0.635 | 0.348 | 0.364 | 0.696 |
| V2-A | 0.596 | 0.267 | 0.273 | 0.660 |

- V2-A changed 3 of 92 units: 0 fixed, 3 broken (one gold-`none` → `different`, two gold-`different` → `none`).
- The aligner agreed with V1's duty flag on 172 of 184 candidates (aligner `yes` 52, `no` 129, `uncertain` 3).
- On all 14 gold-`different` units V1 missed, the aligner also said `no` to both candidates, and in all 14 at least
  one rater cited one of the two shown candidates as the counterpart. So the miss is not retrieval and not a parse
  problem: the right paragraph was in front of the model.
- **Diagnosis (hypothesis, to be tested only on dev):** the prompt asks a stricter question than the gold. The
  guidelines (v3.4) define `different` as "same topic, but the requirement differs", while the aligner prompt says a
  shared topic is not enough and asks for the same actor, action and object. Example: a UCB's audit approach to
  customer service against a bank's duty to assess its customer-service systems — raters `different`, aligner `no`
  (action and object "different").
- The design hypothesis in §1 ("a differing requirement is read as not the same duty") is therefore **not supported**
  as stated: the aligner judged these to be different duties even when told that differing details do not matter.
- One prompt revision remains (`MAX_DEV_RUNS = 2`). Aligning the prompt with the v3.4 definition would raise
  `different` recall only if it does not cost more in `none` precision (33 gold `none` units); that is what a second
  dev run would measure.

### Run 2 (the one allowed revision)

Prompt tag `ffe7011f`; run 1's prompt is archived in `docs/v2/dev_run1_prompts/` (its sha256 matches the run 1
records). Only the system prompt changed: `same_underlying_duty` now asks whether the candidate is the target class's
**counterpart**, regulating the same specific matter, with the action or object allowed to differ; a broad shared area
is still not enough. The user prompt, the output format, the evidence rule, the parser and the decision rule are
unchanged. 92 units, 93 HTTP attempts (one transient-error retry), 0 parse failures. Report:
`data/v2_runs/reports/alignment_dev_eval_ffe7011f_20261029T045721Z.json`.

| System | Macro-F1 | `different` F1 | `different` recall | `none` precision |
|---|---|---|---|---|
| V1 | 0.635 | 0.348 | 0.364 | 0.696 |
| V2-A, run 1 | 0.596 | 0.267 | 0.273 | 0.660 |
| V2-A, run 2 | 0.712 | 0.528 | 0.636 | 0.795 |

- V2-A changed 7 of 92 units, all `none` → `different`: 6 fixed, 1 broken (a gold-`none` unit).
- **Caveats, all of which keep this from being a result:**
  - **Tuned on dev.** The revision was written after reading the dev errors, and its "yes" example (a policy on one side,
    a review on the same matter on the other; differing audit arrangements) resembles units I read. 3 of the 6 fixes
    are the customer-service audit item quoted in run 1's diagnosis, and 2 more are the IS-audit item I also read.
  - **Clustered and small.** The 6 fixes come from 3 source items. On the 7 changed units, an exact two-sided sign test
    gives p = 0.125.
  - **The quote check cost answers.** 15 of 184 candidates were downgraded to `uncertain` (run 1: 3), 8 of them
    model `yes`. The failures are quotes joined with "...", quotes under four words, or quotes of a heading. These fall
    back to V1, so they can only hide gains, not create them.
- The T1 evaluation (412 units, frozen prompt, pre-registered comparisons in §7) is the only test of V2-A. No more dev
  revisions are allowed (`MAX_DEV_RUNS = 2`), so this prompt is the one to freeze.
- **Runner fix found in this run:** the client counts HTTP attempts, and `run_v2.py dev` had set the call limit to the
  number of units, so one retry stopped the run at 91 units. The limit is now the dev cap (100). The missing unit was
  completed by resuming the same run (1 call; ledger 185 of 480 for the quota day).
