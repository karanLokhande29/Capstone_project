# RBI compliance audit generator (local)

> **Decision support only; verify against the official RBI text; not legal advice.**

A local tool, built on the RBI-ObliBench corpus and pipeline. A regulated entity's compliance team runs it to produce a
citation-backed audit pack. Every row names its RBI source: the Direction, the paragraph id and the rbi.org.in link.
Nothing in a pack is settled until a reviewer confirms it.

## What it produces

| # | Section | What it is |
|---|---|---|
| 1 | **Applicability register** | Each obligation lists: Direction, clause, an excerpt of at most 25 words, applies-to, as-of status, effective-from, amended-by, deadline/frequency, subject family, link, confidence, review status. Activity flags narrow the list through subject families. Narrowed rows stay in the pack, hidden and labelled "filtered by activity". |
| 2 | **Change-impact log** | What changed between the last review and the as-of date, grouped by Direction: amended, deleted, newly in force, uncertain window, circular withdrawn. Each change names its governing instrument and date. A Direction whose consolidated "Updated as on" date moved gets one Direction-level row; we do not claim which paragraphs changed. |
| 3 | **Compliance calendar** | Rule-based extraction of deadlines and frequencies, each with a confidence. Low-confidence entries are marked **verify**. Outputs a table, a month view in the UI, and an `.ics` file. Event-triggered deadlines ("within 30 days of a change") are listed but not dated. |
| 4 | **Cross-class differential** | For group entities, uses the P2-002 matches to label each obligation in one of four ways: **shared** (near-verbatim counterpart), **possibly different**, **no counterpart found**, or "target class has no Direction in this family". **Every possibly-different or no-counterpart row needs human review.** The benchmark found that LLM systems miss most differential cases. |
| 5 | **Enforcement-risk view** | P2-003 monetary-penalty press releases against the same class, per Direction: count, dates, links. The links are Direction-level weak links. **Prioritisation context only, not a prediction.** |
| 6 | **Policy gap analysis** | Upload PDF/DOCX/TXT/MD. Each applicable obligation is marked **covered / partial / missing**, with the matched clauses and their scores. Missing items are ranked by enforcement risk. **Runs on local models only.** |
| 7 | **Reviewer workflow** | Each row gets unreviewed / confirmed / disputed / not applicable, plus reviewer, note and timestamp, in the UI or in Excel. Re-importing a reviewed Excel file writes a **new signed-off pack** with a review summary; the original pack is kept. |
| 8 | **Exports** | Excel (Summary, Applicability, Changes, Calendar, Differential, Enforcement, Gap analysis, Sources, About, with filters and frozen headers); DOCX and PDF report (executive summary, tables, About box); `.ics`; JSON audit trail (inputs, corpus hash, rule and threshold versions, the source of every row; uploaded files as **hashes only**). |
| 9 | **Corpus freshness** | Snapshot date and age, with a warning past 30 days. `refresh --dry-run` lists what an incremental re-harvest would fetch. `refresh --apply` writes only to `data/auditgen_corpus/`. |

Every output carries the corpus snapshot date and sha256, the tool and rules versions, the as-of date, the entity
profile, the **validation box** (below) and the disclaimer.

## How to run

```bash
# CLI (no API calls in any command)
python3 scripts/auditgen.py generate --profile my_profile.json          # pack + Excel/DOCX/PDF/ICS/JSON in data/auditgen_runs/<id>/
python3 scripts/auditgen.py gap --pack <id> --policy kyc_policy.pdf      # local gap analysis
python3 scripts/auditgen.py review-import --pack <id> --workbook reviewed.xlsx --signer "Name"
python3 scripts/auditgen.py refresh --dry-run                             # <= 4 requests to rbi.org.in, 1.5 s apart, writes nothing
python3 scripts/auditgen.py refresh --apply [--budget 80]                 # writes data/auditgen_corpus/ only
python3 scripts/auditgen.py validate                                      # recompute the validation box
python3 scripts/auditgen.py samples                                       # the 3 sample packs + the UI replay copies
```

A profile file looks like this:
`{"name": "My SFB", "entity_class": "Small Finance Banks", "as_of": "2026-10-15", "last_review": "2025-12-01", "activities": ["deposits", "lending", "kyc_aml"], "group_classes": []}`.
- Classes: the 11 core classes.
- Activities: `deposits, lending, digital_lending, forex, payments, priority_sector, co_lending, outsourcing, kyc_aml, it_cyber`.

**Backend and UI**

```bash
python3 scripts/auditgen.py serve                  # FastAPI on http://127.0.0.1:8765 (loopback only; refuses 0.0.0.0)
cd ui && npm run dev                               # http://localhost:5181/auditgen (Vite proxies /api/auditgen to 8765)
```

UI pages (in the local workspace sidebar, under "Audit generator"):
- **Audit pack:** profile form, Generate, then tabs Register / Changes / Calendar / Differential / Enforcement / Gaps / About.
- **Policy gaps:** upload, then coverage with the matched clauses.
- **Review:** row-level review, progress, sign-off.
- **Downloads.**
- **Corpus status:** age, and the refresh dry run.

With the backend stopped, the UI switches to **offline replay** of the three sample packs; generating, uploading and
reviewing are disabled in that mode. The audit pages are not part of the public builds (Azure / Artifact). A build
step strips the replay files from those builds, and `check_dist` fails if they appear.

**Optional local LLM explanations**
- Install: `brew install ollama` (installed: 0.40.4, MIT). Start it with
  `OLLAMA_HOST=127.0.0.1:11434 ollama serve`, then `ollama pull qwen2.5:1.5b-instruct` (986 MB, Apache-2.0).
- The gap page then offers plain-language explanations. Every sentence passes the NLI verifier, and unsupported ones
  are dropped.
- The client refuses any non-loopback host. Without Ollama the option is hidden, and gap analysis still works.

## Privacy guarantees
- **Confidential company documents never leave the machine.** Gap analysis uses bge-base-en-v1.5 (pinned
  `a5beb1e3…`) and the NLI cross-encoder nli-deberta-v3-xsmall (pinned `a1508764…`). Both load from the local
  Hugging Face snapshot with the hub set offline. The optional explainer is a local Ollama model on 127.0.0.1.
- **No document text goes to Gemini, Groq or any remote API. No API calls in default mode at all.** Tests mock every
  LLM client and every non-loopback socket connection to raise.
- Uploads are stored in `data/auditgen_uploads/<session>/`, which is gitignored and excluded from release_check. They
  can be deleted from the UI (files only, or files and results).
- Uploaded text is never written to logs (access logging is off), the LLM cache or the call log. Reports carry
  matched-clause excerpts only; the JSON audit trail carries file hashes only.
- The backend binds to **127.0.0.1** only. No telemetry. FastAPI's docs and OpenAPI routes are off.
- RBI text: excerpts of at most 25 words plus the link. The "full text" toggle reads the local corpus at runtime and is
  labelled "internal use; source: RBI".
- The research artefacts (benchmark data, gold, frozen prompts, sealed predictions, results, amendments, paper, corpus)
  are only read. A hash snapshot taken before the build is checked by the test suite.

## Validation (shown in every report's About box)

| Check | Result | Note |
|---|---|---|
| Applicability vs T1 gold v1 (106 items × 11 core classes, `applies_to`) | precision **1.000** [0.965, 1.000], recall **0.815** [0.740, 0.873] (106 TP, 0 FP, 24 FN) | The rule assigns a paragraph to its Direction's class, so it misses obligations whose text extends to other classes (3 gold items). |
| Temporal status vs T3 (52 scored items) | accuracy **1.000** [0.931, 1.000] | **Partly circular:** T3's gold and the generator share the amendment parser. |
| Calendar extraction (30 random extractions) | **pending** | Blank check sheet for Karan: `data/auditgen_state/calendar_check_sheet_v1.csv`. Fill the `correct (y/n)` column; the box then shows the precision. |
| Gap analysis (synthetic: 60 obligations, 15 removed, 10 distractor clauses) | "missing" precision **1.000**, recall **1.000** [0.796, 1.000]; not-covered precision 0.429; kept obligations marked covered: 0.556 | **Synthetic only:** the test policy restates obligations almost verbatim, so this is an optimistic upper bound. Real policies paraphrase and combine duties. |
| Differential | caution | RBI-ObliBench: 56 of 78 gold `different` units were missed by every LLM system (0.718). Review every differential call. |

Thresholds and rules are fixed in `config/auditgen_v1.yaml` (rules `auditgen-rules-v1`). They were set before any
validation run, and their sha256 is recorded in every output.

## AI assistant (local generative AI)

A separate **AI assistant** tab (`/auditgen/ai`, also in the sidebar) adds generative-AI features on top of a pack. A
**local** language model runs them: Ollama on 127.0.0.1, `qwen2.5:7b-instruct` by default, with `qwen2.5:1.5b-instruct`
as the fallback. The code is in `src/auditgen/genai.py` and `src/auditgen/ai_features.py`, and the settings are in
`config/auditgen_genai_v1.yaml`.

| Sub-tab | What the model does | How it is checked |
|---|---|---|
| **Ask the pack** | Answers a question from the pack's applicable obligations. Retrieval is bge + BM25 over the register, fused by RRF; the top 6 paragraphs go to the model. | Each sentence must cite an evidence paragraph. The NLI verifier checks it against that paragraph. If any sentence fails, the call is retried once; if nothing passes, the assistant abstains and lists the evidence. |
| **Obligation copilot: explain** | Gives a plain-language summary, who must act, the actions and the deadline for one register row. | NLI against the paragraph. The "key quote" must occur in the paragraph. |
| **Obligation copilot: draft clause** | Drafts a policy clause that would satisfy the obligation, from the RBI text only. | The gap analyser's own covered / partial / missing rule scores the draft. Numbers not found in the obligation are flagged. |
| **Obligation copilot: review suggestion** | Suggests confirm / dispute / not applicable, with a reason. | The reason must pass NLI, otherwise the suggestion shows "unsure". It **never changes the row**: a named person has to click "I agree", which calls the normal review endpoint. |
| **Changes explained** | Says what an amendment did to a paragraph, and its impact. | NLI against the old text plus the amendment text. Direction-level "Updated as on" changes are not guessed at. |
| **Memo & action plan** | Drafts an executive memo and a prioritised action plan from numbered facts taken from the pack. DOCX download. | Every number must appear in the facts the sentence cites. Each action must name one deadline, change or gap row, and add no new figures. |
| **Calendar check** | Re-extracts the deadline or frequency for the rule extractor's "verify" entries, as structured JSON. | The quoted words must occur in the paragraph. Agreement with the rule extraction is reported, but it is **not accuracy**. |
| **Differential 2nd opinion** | Compares a matched pair field by field (actor, deadline, threshold, …). | The frozen comparator rule (`src/rag/comparator_rule.py`) makes the call from those fields. Quoted differences are checked. Every call carries the benchmark's caution. |
| **How it works & log** | Shows the privacy rules and the activity log. | — |

Verified sentences are shown with their RBI citation chips. Sentences that fail the check are held back behind a
"Show N unverified sentences" toggle, struck through, with the reason. Every output is labelled "AI draft, needs
review".

**How to run**

```bash
OLLAMA_HOST=127.0.0.1:11434 ollama serve          # local model runtime (loopback only)
ollama pull qwen2.5:7b-instruct                   # ~4.7 GB, Apache-2.0
python3 scripts/auditgen.py ai-status             # is a local model ready?
python3 scripts/auditgen.py serve                 # backend; then cd ui && npm run dev and open /auditgen/ai
python3 scripts/auditgen.py ask --pack sample_nbfc --question "What are the outsourcing requirements?"
python3 scripts/auditgen.py ai-samples            # recorded outputs for the 3 sample packs (offline replay)
```

Endpoints: `GET /api/auditgen/ai/status`, `GET /api/auditgen/ai/packs/{id}` (stored outputs),
`POST /api/auditgen/ai/packs/{id}/{ask|explain|change|memo|plan|draft|calendar|diff|suggest}`,
`GET /api/auditgen/ai/packs/{id}/memo.docx` and `GET /api/auditgen/ai/activity`. With the backend stopped, the tab
replays the recorded outputs in `ui/public/auditgen/ai_<pack>.json`. Public builds strip these files.

**Privacy guarantees (AI features)**
- **Local model only.** The client refuses any model host that is not 127.0.0.1, ::1 or localhost before it sends a
  request. No feature calls Gemini, Groq or any remote API. Tests mock remote sockets and LLM clients so that any such
  call raises.
- **Inputs** are RBI paragraphs from the local corpus and the pack's own rows. These features never send an uploaded
  company policy to the model. Gap-analysis explanations are a separate opt-in on the Policy gaps page.
- **No text in logs.** `data/auditgen_state/genai/activity.jsonl` records the feature, model, timing, verified and
  unverified counts, and sha256 hashes of the input and output. It never records the question, the prompt or the answer.
  The embedding cache (`data/auditgen_state/genai/emb_*.npz`) holds vectors of RBI paragraphs only.
- **Storage.** Outputs are stored per pack in `data/auditgen_runs/<pack>/ai.json`, which is gitignored. The research
  artefacts are not touched; the research-hash guard test still covers them.

**Limitations (AI features)**
- The verifier is a small NLI model (`nli-deberta-v3-xsmall`), so "verified" means "entailed by the cited paragraph
  according to that model", not "legally correct". It is strict on paraphrase, so correct sentences are sometimes held
  back, and it can still pass a sentence that is wrong in substance.
- Speed: measured with `qwen2.5:7b-instruct` on an Apple M5 with 16 GB on 24 Oct 2026.

  | Feature | Time |
  |---|---|
  | Ask | 2–8 s (up to ~40 s with a retry) |
  | Explain | ~5 s |
  | Memo | ~25 s |
  | Action plan | ~100 s |
  | Calendar check | ~8 s per entry |
  | Differential | 25–80 s per pair |

  The first question on a pack also embeds its register on the CPU, and the vectors are then cached. That step was not
  timed separately: the full sample run took about 13 minutes for the ~5,000-row Small Finance Bank pack, against 4–5
  minutes for the other two packs.
- Retrieval is limited to the pack's register, so a question about something outside the profile gets an abstention.
  In the recorded samples, 3 of 6 questions were answered with verified, cited sentences, and 3 abstained.
- Memo checking is numeric and citation-based, not semantic. Recommendations without figures pass if they cite a fact.
- None of the AI outputs has been evaluated against gold labels. Treat them as drafts for a reviewer.

## Limitations
- **Applicability is Direction-level.** It is not clause-level legal reasoning. Sub-type Directions (e.g. Housing
  Finance Companies inside the NBFC class) and cross-cutting function-heading Directions get lower confidence and a
  "check that this applies" note.
- **Change log:** new paragraphs added by an amendment and changes inside a consolidated "Updated as on" text are not
  resolved to paragraph level.
- **Calendar extraction** is rule-based. Most extracted entries fall below the confidence threshold and are marked
  "verify". Its precision is unmeasured until the check sheet is labelled.
- **Differential** inherits P2-002's limit: it cannot detect that two matched paragraphs differ in substance.
  "Possibly different" is a lexical signal, not a judgement.
- **Enforcement links** are weak and Direction-level (P2-003: 53.3% clean alignment). Few releases name some classes
  (e.g. 3 for Small Finance Banks).
- **Gap analysis** is only as good as bge retrieval and a small NLI model, which are weak on long, combined or
  paraphrased duties. Its validation is synthetic.
- **Corpus freshness:** the research snapshot is dated 25 Sep 2026. On 15 Oct the dry run found 2 new and 134 updated
  Directions and 10 new Amendment Directions. Run `refresh --apply` before relying on a pack.
- A Direction with no title in the corpus (md_11959) is dropped from packs under the "no citation, no row" rule; the
  About box reports the count.

> **Decision support only; verify against the official RBI text; not legal advice.**
