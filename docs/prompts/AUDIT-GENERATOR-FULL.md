# AUDIT GENERATOR — FULL BUILD (all features + UI integration), one pass

## Purpose
Build, in one pass, a complete **RBI compliance audit generator** that a regulated entity's compliance team can run locally. Each run produces a useful, citation-backed audit pack:
1. **Applicability register:** which obligations apply, as of a date.
2. **Change-impact log:** what changed since the last review.
3. **Compliance calendar:** what to file and do, and when.
4. **Cross-class differential:** for groups with several entity types.
5. **Enforcement-risk view:** where RBI has penalised similar entities.
6. **Policy gap analysis:** the company uploads its policies; each obligation is marked covered / partial / missing, with evidence.
7. **Reviewer workflow:** confirm or dispute rows, then sign off.
8. **Exports:** Excel, PDF/DOCX, ICS, JSON audit trail.
9. **Corpus freshness:** status and a safe refresh.

Everything is integrated into the existing React UI in `ui/` through a local backend.

**Karan's permissions (15 Oct):** build everything at once; install the needed packages and models; build the backend and UI. The guardrails below still apply.

## Guardrails (non-negotiable)
- **Research is untouched.** Don't modify benchmark data, gold, frozen prompts, sealed predictions, results bundles, amendments, the paper, the master document, the audit bundle or the research corpus in `data/processed/`. The audit generator **reads** them; it never writes to them. Run the full suite at the end: every existing test must still pass.
- **No git changes.** Never print or log keys.
- **Confidential company documents never leave the machine.**
  - Policy gap analysis runs on **local models only**: bge embeddings plus the NLI cross-encoders already cached, and optionally a local LLM (below).
  - **No document text goes to Gemini, Groq or any remote API.**
  - Uploaded files are stored in gitignored `data/auditgen_uploads/<session>/`, can be deleted from the UI, are never written to the call logs or the LLM cache, and are excluded from release_check.
- **No free-tier API calls on company data. No API calls in default mode at all.** An optional "plain-language summary" may use the local LLM only, never a remote one.
- **Every row cites its source** (`md_id`, `paragraph_id`, Direction title, rbi.org.in URL, as-of status, governing instrument, dates). **No citation, no row.**
- **RBI text:** default excerpts ≤ 25 words plus the link. A "full text" toggle reads the local corpus at runtime, labelled "internal use; source: RBI".
- **Every output carries:**
  - corpus snapshot date and sha256;
  - tool version;
  - as-of date;
  - entity profile;
  - the validation box (below);
  - the disclaimer: "Decision support only; verify against the official RBI text; not legal advice."
- **Honesty about weak spots:**
  - every `different` / class-specific judgement and every gap-analysis "covered" call shows its confidence and is marked **"needs human review"** when below threshold;
  - nothing is presented as settled unless a reviewer confirms it.
- **Local only:** the backend binds to **127.0.0.1**, never 0.0.0.0. No telemetry.

---

## Architecture
- `src/auditgen/`:
  - `profile.py`; `applicability.py`; `temporal.py`; `changes.py`; `calendar_extract.py`; `differential.py`; `enforcement.py`;
  - `gap_analysis.py`; `review.py`; `exports.py`; `freshness.py`; `validation.py`; `summary_llm.py` (optional, local only).
- `scripts/auditgen.py`: the CLI (`generate`, `gap`, `review-import`, `refresh --dry-run|--apply`, `validate`, `samples`).
- `app_api/` or `src/auditgen/api.py`: a **FastAPI** backend on 127.0.0.1 (pinned version; record the licence).
- `ui/`: new React pages wired to the backend, plus an **offline replay mode** that loads the sample packs when the backend isn't running.
- `tests/test_auditgen_*.py`.

## Features (build all)

### 1. Entity profile
- **Class:** one of the 11 core classes.
- **Activity flags:** deposits, lending, digital lending, forex, payments, priority-sector, co-lending, outsourcing, KYC/AML, IT/cyber.
- **As-of date** and **last review date**.
- **Optional:** group entities (for the differential).

Validate against the project vocabulary. Save and load profiles as JSON.

### 2. Applicability register
- Built from the deontic candidates that bind the class, using the class filter, the Direction applicability rules and the temporal status as of the date.
- **Columns:** obligation ID, Direction, section/clause, excerpt, applies-to, status, effective-from, amended-by, deadline/frequency, subject family, source URL, confidence, review status.
- **Activity flags narrow the list through subject families.** Narrowed rows are kept, marked "filtered by activity" and hidden by default; they're never deleted.

### 3. Change-impact log (last review → as-of)
Every obligation whose status changed (amended, newly in force, deleted or withdrawn), with the governing instrument and its date, grouped by Direction.

### 4. Compliance calendar
- Rule-based extraction of deadlines and frequencies ("within N days", monthly, quarterly, half-yearly, annually, "by <date>", returns and submissions).
- Each entry gets a confidence; low-confidence ones are marked "verify".
- Outputs a table and an `.ics` file. The UI shows a month view.

### 5. Cross-class differential
- For two or more classes: obligations shared vs class-specific, using the P2-002 matches.
- Every `different` call is marked "needs human review", with a note: "the benchmark found LLM systems miss most differential cases".

### 6. Enforcement-risk view
- Uses the P2-003 penalty records (Direction-level, entity class resolved): the count, the dates and the press-release links per Direction, for the same class.
- Prioritisation context only, labelled "not a prediction".

### 7. Policy gap analysis (local only)
- **Upload:** PDF / DOCX / TXT / MD. Text extraction runs locally (pdfplumber / python-docx; already installed or pinned).
- **Segmentation:** split into clauses.
- **Matching:** for each applicable obligation, retrieve the top-k policy clauses with **bge** (local), then score coverage with the local **NLI cross-encoder** (entailment = covered, partial overlap = partial, nothing above threshold = missing).
- **Thresholds:** fixed before evaluation and recorded in config. **Every row shows the matched clause(s) and the scores.**
- **Optional local LLM explanation:**
  - Only if a local runtime is available (for example Ollama, with a small instruction model).
  - Installing it is permitted **if disk space allows; check first and report**.
  - Explanations pass the NLI verifier; an unsupported sentence is dropped.
  - If no local LLM is available, the feature is hidden; gap analysis still works without it.
- **Output:** coverage per obligation and per Direction, with "missing" items ranked by enforcement risk.

### 8. Reviewer workflow
- In the UI and in Excel: `review_status` (unreviewed / confirmed / disputed / not applicable), `reviewer`, `note`, `timestamp`.
- **Re-import** of a reviewed Excel file produces a signed-off pack with a review summary; the original is kept.
- The UI shows review progress.

### 9. Exports
- **Excel:** sheets Summary, Applicability, Changes, Calendar, Differential, Enforcement, Gap analysis, Sources, About. Filters and frozen headers.
- **PDF/DOCX report:** executive summary (counts by status and by Direction, top changes, next 90 days of deadlines, highest-risk gaps), the tables, and the About box.
- **`.ics`.**
- **JSON audit trail:** inputs, corpus hash, rule and threshold versions, the source of every row; for gap analysis, the uploaded file hashes only, never their text.

### 10. Corpus freshness and refresh
- **Status:** the snapshot date, its age, and a warning when it's older than 30 days.
- **`refresh --dry-run`:** what an incremental re-harvest would fetch (new or updated Directions, Amendment Directions, withdrawn circulars).
- **`--apply` (permitted):**
  - writes **only** to a separate `data/auditgen_corpus/`, never to `data/processed/`;
  - uses the existing scraper with its rate limit (≥ 1.5 s/request) and request-budget guard;
  - after applying, the generator uses the new snapshot and records the new hash.
  - Research results always stay tied to the original corpus.

### 11. UI integration (`ui/`)

**Pages:**
- **Audit pack:** profile form → Generate → tabs for Register / Changes / Calendar / Differential / Enforcement / Gaps / About.
- **Policy gaps:** upload, then coverage results with the matched clauses.
- **Review:** row-level review, progress, sign-off.
- **Downloads:** Excel, PDF/DOCX, ICS, JSON.
- **Corpus status:** snapshot age, plus the refresh dry-run.

**Requirements:**
- Every row has a link to its RBI source.
- "Needs human review" badges.
- The disclaimer is always visible.
- **Offline replay mode** shows the 3 sample packs without the backend.

**UI tests:** a smoke test per page, using the existing UI test setup; add a minimal one if none exists.

## Validation, shown in every report's About box
- **Applicability:** precision/recall against T1 gold v1 (106 items, `applies_to`).
- **Temporal status:** accuracy against T3 (52 items), noting that T3 is partly circular with the temporal filter.
- **Calendar extraction:** precision on 30 random extractions. Build a blank check sheet for Karan; until he labels it, show "pending".
- **Gap analysis:** a synthetic check. Build a test policy from known obligations with some removed, and report the detection precision/recall. State clearly that this is synthetic.
- **Differential:** report the benchmark's `different` miss rate as a caution.

## Tests
Unit and integration tests for:
- profile validation; applicability; temporal status; the change window;
- calendar extraction; differential flagging; enforcement linking;
- gap analysis on fixtures; review re-import; exports (sheets present; files open);
- freshness dry-run; API endpoints; the citation-required rule; the 25-word excerpt limit; the disclaimer on every output.

And these safety tests:
- **no remote API call** in default and gap-analysis modes (mock them to raise);
- **uploaded text never appears in logs, the cache or the exports**, other than the matched-clause excerpts in the user's own report;
- **the backend binds to 127.0.0.1**;
- **the research files are unchanged** (compare hashes before and after the build).

## Samples and docs
- Sample packs for 3 profiles (SFB, NBFC, Payments Bank), as of today, last review 2025-12-01, in `outputs/auditgen_samples/`. Include one gap analysis run on a synthetic sample policy; **never on real company data**.
- `docs/AUDITGEN_README.md`:
  - what it does; how to run the CLI, the backend and the UI;
  - privacy guarantees; the validation numbers; limitations;
  - the disclaimer.

## Final checks
- Full suite passes (existing plus new tests).
- release_check passes: uploads, the auditgen corpus and samples containing RBI text are excluded where needed.
- Research artefact hashes are unchanged.
- No keys anywhere.
- Backup: `final_push_backups/auditgen_<UTC>.zip`, verified.

## STOP — print
- the features built (each item 1–11: done / partial, with the reason);
- the packages and models installed, with versions and licences;
- disk used;
- the test count;
- the validation numbers;
- how to launch the backend and UI;
- the sample paths;
- known limitations.

Then stop.
