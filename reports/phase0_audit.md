# Phase 0 — Repository Audit & Implementation Blueprint

**Prompt ID:** P0-001 · **Branch:** `base` · **Model:** Opus · **Date:** 2026-08-22
**Classification:** PASS

---

## 1. Repository audit (Tasks 1–2)

### 1.1 State at start

The working tree was **empty**. Only `.git/` existed; `git status` was clean.

The repository was not, however, without history:

| Commit | Effect |
|---|---|
| `3ef0a68` | `README.md` only |
| `8f3ead5` | 1,394 files — a prior Weeks 1–5 implementation |
| `c309e63` | **Delete all files from repository** ← `HEAD`, on `main` and `origin/main` |

The prior implementation covered scraping, extraction, segmentation, temporal
metadata, matrix construction, deontic candidate extraction and annotation
scaffolding, together with a harvested corpus of 381 documents and ~68k
candidate obligation spans.

### 1.2 Decision taken

The audit was presented with four options. The project owner directed that the
project be built **entirely from scratch**, with no code, data, or reports
restored or referenced from `8f3ead5`, and with a dual-mode pathing abstraction
for Kaggle.

Phase 0 was therefore executed as a true greenfield: `8f3ead5` remains reachable
in history, but nothing in this branch derives from it.

### 1.3 Inventory findings

| Finding | Count |
|---|---|
| Files in working tree at start | 0 |
| Reusable code adopted | **0** (greenfield, by direction) |
| Existing files modified | **0** (nothing existed to modify) |
| Dependency conflicts found | 0 |
| Data available at start | none in the working tree |

Two structural problems in the prior history informed decisions here even though
its code was not reused:

* **No `.gitignore` existed**, so `.DS_Store`, `__pycache__/` and ~275 MB of
  corpus data were committed. A `.gitignore` is created in this branch, and
  `data/raw/**` and `data/extracted/**` are excluded.
* **Corpus PDFs were committed to a public repository** while the project's own
  position is that RBI redistribution rights are unsettled. This branch keeps
  source documents out of git entirely and stores benchmark references as
  offsets rather than text.

---

## 2. Architecture (Tasks 3, 6)

### 2.1 Structure created

```
config/config.yaml       src/common/          src/schemas/
data/{raw,extracted,     src/scraper/         tests/
  processed,metadata,    src/extraction/      scripts/
  matrix,benchmark,      src/preprocessing/   notebooks/
  evaluation,cache}/     src/metadata/        reports/
                         src/matrix/
                         src/benchmark/
```

### 2.2 Deviations from the proposed skeleton, with justification

| Deviation | Reason |
|---|---|
| No nested `rbi-compliance-rag/` directory | The repository root *is* the project root. Nesting would put every path one level deeper for no benefit and complicate the Kaggle clone. |
| **Added `src/common/`** | The proposed skeleton had no home for shared utilities. Placing them in any workstream package would give one branch ownership of code all three depend on. |
| **Added `src/schemas/`** | Section N suggested `src/metadata/schemas.py`. Rejected: `src/metadata/` is owned by `phase1/karan-matrix`, and putting the shared contract inside one branch's edit scope is precisely the collision risk Phase 0 exists to prevent. An owner-neutral top-level package makes shared ownership explicit and keeps the contract physically outside every branch's file scope. |
| **Omitted `src/retrieval/`, `src/temporal/`, `src/evaluation/`, `src/agent/`** | Task 3: "Do not create modules with no near-term purpose." These serve Weeks 6–15. Empty packages invite premature commitment to a structure the research has not yet justified. Their `data/` directories are still created, because those define the data contract at negligible cost. |
| **Added `data/cache/`** | Required by the caching helper (Task 5). Not in the proposed list. |
| **Added `.gitignore`** | Not in the proposed list, but its absence in the prior history caused both problems in §1.3. |
| Test config in `pyproject.toml`, not `pytest.ini` | One fewer config file; `[tool.pytest.ini_options]` is equivalent. |

### 2.3 Dual-mode pathing

The central architectural decision. On Kaggle, attached Datasets mount
**read-only** at `/kaggle/input/<slug>`; only `/kaggle/working` is writable.
Code that resolves one path and then both reads and writes it works locally and
fails on Kaggle — typically deep into a long run.

`PathResolver` therefore separates the two operations:

| Operation | Local | Kaggle |
|---|---|---|
| `write_path(key, …)` | repo root | `/kaggle/working` **only** |
| `read_path(key, …)` | repo root | `/kaggle/input/<slug>` first, then `/kaggle/working` |

Mode is detected from `KAGGLE_KERNEL_RUN_TYPE` / `KAGGLE_URL_BASE`, falling back
to probing for `/kaggle/working`, and can be forced via `environment.mode`.
Both the env mapping and the probe root are injectable, so tests exercise Kaggle
behaviour against a fake `/kaggle` tree under `tmp_path` rather than mocking the
filesystem module.

This read-order also gives the cache its cross-session behaviour: a corpus
harvested in one session and saved as a Kaggle Dataset is a cache **hit** in the
next, so a re-run costs nothing rather than re-downloading the corpus.

---

## 3. Shared schemas (Task 4, Section P)

Six contracts, **77 fields**, each documented with type, requiredness,
nullability, description, and the branch expected to populate it.

| Schema | Fields | Purpose |
|---|---|---|
| `DocumentRecord` | 14 | Harvested source document provenance |
| `ParagraphRecord` | 22 | Paragraph unit — the atom of retrieval and annotation |
| `MatrixCell` | 10 | One (entity class, subject family) coverage cell |
| `ObligationSpan` | 6 | Character span stating an obligation |
| `T1Label` | 16 | One T1 benchmark item |
| `VocabularyTerm` | 9 | One discovered canonical term |

### 3.1 Required-field coverage

Every field required by Task 4 is present:

| Requirement | Field(s) | Status |
|---|---|---|
| source URL | `source_url` | present |
| document ID | `document_id` | present |
| document title | `document_title` / `title` | present |
| entity class | `entity_class`, `entity_class_raw` | present |
| subject family | `subject_family`, `subject_family_raw` | present |
| paragraph ID | `paragraph_id` | present |
| update date | `update_date` | present |
| extraction source | `extraction_source` | present |
| **section/clause info** | `section_id`, `section_title`, `clause_id`, `clause_path` | present |
| **retrieval metadata** | `retrieval_chunk_id`, `retrieval_chunk_index`, `retrieval_embedding_model`, `retrieval_index_id` | present |
| entity-class vocabulary (extensible) | `Vocabulary(ENTITY_CLASS)` | present, **empty** |
| subject-family vocabulary (extensible) | `Vocabulary(SUBJECT_FAMILY)` | present, **empty** |
| matrix cell: entity_class, subject_family, populated, source Directions, ambiguity | `MatrixCell` | present |
| T1: entity_class, subject_family, obligation_span, applies_to, differential_flag, in_force_from, in_force_to | `T1Label` | present |

**Missing required fields: none.**

### 3.2 Design decisions worth recording

**Nullability.** Task 4 specifies all fields nullable at this stage. Two
exceptions are made: `document_id` (both records) and `paragraph_id`. These are
the join keys — a record whose identifier is null cannot be referenced by any
downstream artifact, so permitting null there would define a record nothing
could ever use. Three list fields (`cross_reference_ids`, `applies_to`,
`source_directions`) are also non-nullable with empty-list defaults, because
empty means *checked, none found* while null would mean *never checked*, and
conflating them destroys the distinction a coverage metric depends on.

**Raw vs normalised are separate fields.** `entity_class_raw` holds exactly what
the source said; `entity_class` holds the normalised value. Normalisation is a
research decision, and overwriting the evidence for it in place would make it
unauditable and irreversible.

**`applies_to` is an annotation target, not a derived field.** The natural
implementation — copying the source document's `entity_class` into `applies_to`
— produces a field that restates its own input. A benchmark built that way
cannot support any applicability claim, because the label is definitionally
implied by which file the text came from. RQ1 requires annotators to judge which
entity classes an obligation actually binds, which is frequently not the class
of the containing document. `T1Label.validate()` rejects a `validated` item with
an empty `applies_to`, and a unit test asserts the field's declared owner is the
annotation branch, not the matrix branch.

**`differential_flag` defaults to `unlabelled`, never `absent`.** Defaulting to
`absent` silently converts "no cross-class match was attempted or found" into
the positive claim "this obligation has no differential counterpart". That
inflates the absent class with items nobody examined and biases every statistic
computed over it. `validate()` rejects a `validated` item still flagged
`unlabelled`.

**Vocabularies start empty and are never seeded.** The planning estimates (~11
entity classes, ~26 subject families) are estimates. Encoding them would turn an
estimate into an assumption, and a later discovered count that disagreed would
read as a bug rather than a finding. `empty_entity_class_vocabulary()` returns an
empty vocabulary; both a unit test and a runtime check in the foundation smoke
test enforce that it stays that way.

**`FIELD_SPECS` is machine-readable and enforced.** Each schema declares its
fields' owners in code. A test asserts the spec table and the dataclass fields
stay in lockstep, so a branch cannot add a field without declaring who owns it —
which is the specific failure mode that produces silent divergence across three
parallel branches.

### 3.3 Full field tables

#### `DocumentRecord` — 14 fields

One harvested source document and its provenance.

| Field | Type | Required | Nullable | Populated by | Description |
|---|---|---|---|---|---|
| `document_id` | str | yes | no | phase1/akash-scraper | Stable identifier for this document, unique across the corpus. The join key every other artifact references. |
| `source_url` | str | None | no | yes | phase1/akash-scraper | Canonical URL the document was retrieved from. Retained so downstream artifacts can cite a source without redistributing text. |
| `title` | str | None | no | yes | phase1/akash-scraper | Document title exactly as published by the source. |
| `entity_class_raw` | str | None | no | yes | phase1/akash-scraper | Regulated-entity class exactly as it appeared on the source listing, before any normalisation. |
| `subject_family_raw` | str | None | no | yes | phase1/akash-scraper | Subject/topic exactly as it appeared on the source listing, before any normalisation. |
| `entity_class` | str | None | no | yes | phase1/karan-matrix | Normalised entity class, resolved against the discovered entity-class vocabulary. |
| `subject_family` | str | None | no | yes | phase1/karan-matrix | Normalised subject family, resolved against the discovered subject-family vocabulary. |
| `update_date` | str | None | no | yes | phase1/akash-scraper | Last-updated date stamp as published, kept verbatim as a string because source formats are inconsistent. Parsing is a downstream concern. |
| `extraction_source` | str | None | no | yes | phase1/akash-scraper | Which source family this came from. Known values: rbi_master_directions, rbi_faq, rbi_circulars, rbi_circulars_withdrawn, rbi_enforcement, rbi_amendments. |
| `document_role` | str | None | no | yes | phase1/akash-scraper | Role in the study. Known values: primary_corpus, supplementary, validation. Distinguishes corpus from context. |
| `format` | str | None | no | yes | phase1/akash-scraper | Retrieved file format, e.g. PDF or HTML. |
| `local_path` | str | None | no | yes | phase1/akash-scraper | Path the payload was cached at, relative to the active working root. Never an absolute Kaggle path. |
| `content_hash` | str | None | no | yes | phase1/akash-scraper | SHA-256 of the retrieved bytes. Detects silent source changes and duplicate documents published under two IDs. |
| `retrieved_at` | str | None | no | yes | phase1/akash-scraper | ISO-8601 timestamp of retrieval. Establishes the corpus snapshot date for amendment-awareness claims. |

#### `ParagraphRecord` — 22 fields

One paragraph of one document, with full provenance back to its source.

| Field | Type | Required | Nullable | Populated by | Description |
|---|---|---|---|---|---|
| `paragraph_id` | str | yes | no | phase1/akash-scraper | Stable, deterministic identifier for this paragraph. Must be reproducible from (document_id, position) so re-running extraction does not invalidate existing annotations. |
| `document_id` | str | yes | no | phase1/akash-scraper | Identifier of the DocumentRecord this paragraph came from. |
| `document_title` | str | None | no | yes | phase1/akash-scraper | Denormalised document title, carried for annotator context without a second lookup. |
| `source_url` | str | None | no | yes | phase1/akash-scraper | Denormalised source URL, so a benchmark item is citable on its own. |
| `entity_class` | str | None | no | yes | phase1/karan-matrix | Normalised entity class inherited from the parent document. NOT an applicability judgement — see T1Label.applies_to. |
| `subject_family` | str | None | no | yes | phase1/karan-matrix | Normalised subject family inherited from the parent document. |
| `update_date` | str | None | no | yes | phase1/akash-scraper | Update date inherited from the parent document, kept verbatim as a string. |
| `extraction_source` | str | None | no | yes | phase1/akash-scraper | Source family inherited from the parent document. |
| `section_id` | str | None | no | yes | phase1/akash-scraper | Section number as printed, e.g. '4' or 'Chapter III'. Required for citation-grade provenance; a bare paragraph index is not a legal reference. |
| `section_title` | str | None | no | yes | phase1/akash-scraper | Section heading text as printed. |
| `clause_id` | str | None | no | yes | phase1/akash-scraper | Innermost clause label as printed, e.g. '(a)' or '(iii)'. |
| `clause_path` | str | None | no | yes | phase1/akash-scraper | Full hierarchical path to the clause, e.g. '4.2(a)(iii)'. This is what a compliance answer must cite. |
| `position` | int | None | no | yes | phase1/akash-scraper | Zero-based ordinal of this paragraph within its document. Combined with document_id, determines paragraph_id. |
| `text` | str | None | no | yes | phase1/akash-scraper | Paragraph text. Held for processing; excluded from any redistributable artifact pending the licensing decision. |
| `char_start` | int | None | no | yes | phase1/akash-scraper | Start offset of this paragraph in the document's extracted text. |
| `char_end` | int | None | no | yes | phase1/akash-scraper | End offset (exclusive) of this paragraph in the document's extracted text. |
| `content_hash` | str | None | no | yes | phase1/akash-scraper | SHA-256 of the paragraph text. Detects whether an amendment changed this paragraph between corpus snapshots. |
| `cross_reference_ids` | list | no | no | phase1/akash-scraper | Paragraph IDs this paragraph refers to. Empty list means none found, which is a measurement; null would mean not yet checked, so this field is non-nullable. |
| `retrieval_chunk_id` | str | None | no | yes | phase2+ | Identifier of the retrieval chunk containing this paragraph. Reserved for the retrieval phase. |
| `retrieval_chunk_index` | int | None | no | yes | phase2+ | Ordinal of this paragraph within its retrieval chunk, when chunks span paragraphs. |
| `retrieval_embedding_model` | str | None | no | yes | phase2+ | Identifier of the embedding model used to index this paragraph. Recorded per record because ablations compare indexes built with different models. |
| `retrieval_index_id` | str | None | no | yes | phase2+ | Identifier of the index build this record belongs to, so evaluation results are attributable to a specific index. |

#### `MatrixCell` — 10 fields

One (entity class, subject family) cell of the coverage matrix.

| Field | Type | Required | Nullable | Populated by | Description |
|---|---|---|---|---|---|
| `entity_class` | str | yes | no | phase1/karan-matrix | Normalised entity class naming this cell's row. Non-nullable: a cell without both axes is not addressable. |
| `subject_family` | str | yes | no | phase1/karan-matrix | Normalised subject family naming this cell's column. |
| `populated` | bool | no | no | phase1/karan-matrix | Whether at least one Master Direction was found governing this pair. False is a measurement, not a missing value, so this is non-nullable. |
| `source_directions` | list | no | no | phase1/karan-matrix | document_id values of the Directions governing this cell. Empty list when unpopulated. |
| `ambiguous` | bool | no | no | phase1/karan-matrix | Whether the mapping into this cell is uncertain. Independent of `populated`: a populated cell can still be ambiguous. |
| `ambiguity_reason` | str | None | no | yes | phase1/karan-matrix | Why the cell is ambiguous. Null when `ambiguous` is False. Known values: unresolved_entity_class, unresolved_subject_family, multiple_candidate_directions, cross_class_direction, superseded_unclear. |
| `n_documents` | int | None | no | yes | phase1/karan-matrix | Count of source Directions. Redundant with len(source_directions) but retained for matrices exported without the ID list. |
| `entity_class_term_id` | str | None | no | yes | phase1/karan-matrix | term_id of the entity class in the discovered vocabulary. Survives renaming of the display form. |
| `subject_family_term_id` | str | None | no | yes | phase1/karan-matrix | term_id of the subject family in the discovered vocabulary. |
| `notes` | str | None | no | yes | phase1/karan-matrix | Free-text observation about this cell, typically the evidence behind an ambiguity call. |

#### `ObligationSpan` — 6 fields

A character span within a paragraph that states an obligation.

| Field | Type | Required | Nullable | Populated by | Description |
|---|---|---|---|---|---|
| `paragraph_id` | str | yes | no | phase1/meer-annotation | Paragraph this span lies within. Joins to ParagraphRecord.paragraph_id. |
| `document_id` | str | yes | no | phase1/meer-annotation | Document the paragraph belongs to. Denormalised so a span is resolvable on its own. |
| `char_start` | int | yes | no | phase1/meer-annotation | Start offset within the paragraph text, zero-based. |
| `char_end` | int | yes | no | phase1/meer-annotation | End offset within the paragraph text, exclusive. |
| `text` | str | None | no | yes | phase1/meer-annotation | The span text. Convenience for annotation tooling only; offsets are authoritative and are what gets published. |
| `matched_cue` | str | None | no | yes | phase1/meer-annotation | Deontic cue that surfaced this span, e.g. 'shall'. Recorded so candidate-generation bias is measurable rather than invisible. |

#### `T1Label` — 16 fields

One T1 benchmark item.

| Field | Type | Required | Nullable | Populated by | Description |
|---|---|---|---|---|---|
| `label_id` | str | yes | no | phase0-base | Stable identifier for this benchmark item. Must survive regeneration of the candidate pool, or existing annotations detach. |
| `obligation_span` | ObligationSpan | None | no | yes | phase1/meer-annotation | The span of text stating the obligation. Null only for an item whose span has not yet been fixed. |
| `entity_class` | str | None | no | yes | phase1/karan-matrix | Entity class of the SOURCE DOCUMENT. Context only. Must not be read as an applicability judgement, and must never be copied into applies_to. |
| `subject_family` | str | None | no | yes | phase1/karan-matrix | Subject family of the source document. |
| `applies_to` | list | no | no | phase1/meer-annotation | ANNOTATION TARGET. Entity classes this obligation actually binds, as judged by annotators. Empty list means not yet annotated. Deriving this from entity_class makes the label a tautology and invalidates RQ1. |
| `applies_to_rationale` | str | None | no | yes | phase1/meer-annotation | Annotator's stated reason for the applicability judgement. Required for adjudicating disagreements. |
| `differential_flag` | str | no | no | phase1/meer-annotation | ANNOTATION TARGET. One of DifferentialFlag. Defaults to 'unlabelled'; never default to 'absent', which would assert an unexamined finding. |
| `differential_counterpart_ids` | list | no | no | phase1/meer-annotation | label_id values of counterpart obligations in other entity classes. Empty when none identified. |
| `in_force_from` | str | None | no | yes | phase1/akash-scraper | Date this obligation took effect, verbatim as published. Carries the amendment-awareness claim. |
| `in_force_to` | str | None | no | yes | phase1/akash-scraper | Date this obligation ceased to be in force, or null if still current. Distinguishing 'still in force' from 'never populated' requires checking label_status. |
| `label_status` | str | no | no | phase1/meer-annotation | One of LabelStatus. Starts at 'candidate'. Promotion to 'validated' requires the configured number of independent annotators and is never implicit. |
| `annotator_ids` | list | no | no | phase1/meer-annotation | Identifiers of annotators who labelled this item. Length drives the validation threshold. |
| `annotation_count` | int | None | no | yes | phase1/meer-annotation | Number of independent annotations received. |
| `agreement_score` | float | int | None | no | yes | phase1/meer-annotation | Inter-annotator agreement for this item, where computed. Corpus-level Fleiss' kappa is reported separately. |
| `provenance` | str | None | no | yes | phase1/meer-annotation | Which pipeline stage proposed this candidate, so candidate-generation bias stays attributable. |
| `notes` | str | None | no | yes | phase1/meer-annotation | Free-text annotator note. |

#### `VocabularyTerm` — 9 fields

One canonical term plus every surface form that maps to it.

| Field | Type | Required | Nullable | Populated by | Description |
|---|---|---|---|---|---|
| `term_id` | str | yes | no | phase1/karan-matrix | Stable slug for this term. Referenced by matrix cells and benchmark labels, so it must not change once assigned. |
| `canonical_name` | str | yes | no | phase1/karan-matrix | Preferred display form, kept exactly as published rather than normalised. |
| `kind` | str | yes | no | phase1/karan-matrix | Which axis this term belongs to. One of: entity_class, subject_family. |
| `aliases` | list | no | no | phase1/karan-matrix | Other surface forms observed in the corpus that resolve to this term. Empty list means none observed yet. |
| `source` | str | None | no | yes | phase1/karan-matrix | Where the term was discovered, e.g. a listing page URL. Makes the vocabulary auditable rather than asserted. |
| `definition` | str | None | no | yes | phase1/karan-matrix | Definition as given by the regulator, where one exists. |
| `first_seen_document_id` | str | None | no | yes | phase1/karan-matrix | First document the term was observed in. |
| `occurrence_count` | int | None | no | yes | phase1/karan-matrix | How many documents map to this term. A discovered count, never an estimate. |
| `notes` | str | None | no | yes | phase1/karan-matrix | Free-text note, typically recording why an ambiguous surface form was resolved this way. |

---

## 4. Shared utilities (Task 5) and configuration (Task 6)

| Module | Provides | Notable behaviour |
|---|---|---|
| `config.py` | Loading + validation | Reports **every** problem at once, not the first. Rejects absolute path keys, null required scalars, invalid modes. Never defaults silently. |
| `paths.py` | Dual-mode resolution | Read/write split (§2.3). Unknown key errors list the declared keys; unresolved reads list every location searched. |
| `io_helpers.py` | JSON / JSONL / text | All writes atomic via temp-file + `os.replace`, so a Kaggle session hitting its time limit mid-write cannot leave a truncated file that looks valid. Parse errors name the file and line. |
| `retry.py` | Exponential backoff + jitter | Sleep and jitter injectable, so backoff arithmetic is tested without spending the seconds. Retries a narrow default exception set — retrying a `ValueError` hides a bug. `give_up_on` short-circuits known-permanent failures. |
| `cache.py` | Content-addressed cache | Reads through Kaggle Datasets then working dir; writes only to working. Namespaced so three branches sharing one Dataset cannot collide. Sharded by key prefix. |
| `logging_setup.py` | Standard logging | Idempotent handler installation; file handler failure degrades to stderr rather than killing a run. |
| `verify.py` | Foundation self-check | Reports failures rather than raising them. |

**One I/O decision is worth flagging.** `write_json`/`write_jsonl` initially used
`default=str`, which silently coerces any unserialisable object to its `repr`.
A test caught this. A blanket `str()` fallback would let a bug — a dataclass
where a dict was expected, say — land in a corpus file as a plausible-looking
string and survive every downstream check. The helpers now serialise a
deliberate set of types (dates, `Path`, `Enum`, sets, dataclasses) and **raise**
on anything else.

### Configuration

`config/config.yaml` covers Kaggle-relative and local paths, logging, retry and
timeout parameters, cache policy, and vocabulary file locations. Values not yet
known are left unset with an explicit `TODO(phase1/<branch>)` naming the owner:
scraper source URLs, the Kaggle Dataset slug, the embedding model, and the
annotator roster. The embedding model in particular is left `null` rather than
given a plausible placeholder, because a placeholder invites accidental adoption
of a Week 7 decision that carries evaluation consequences.

---

## 5. Dependencies (Task 7)

Phase 0 requires **no pip install on Kaggle**. It uses the standard library plus
PyYAML, and is tested with pytest; both ship in Kaggle's base image.

`requirements.txt` distinguishes two categories rather than listing everything:

* **Already in the Kaggle image** — commented out with a minimum version for the
  record. Re-pinning these would make pip downgrade or upgrade packages Kaggle
  chose and tested together, dragging their dependencies with them.
* **Genuinely missing** — real requirements. Currently only `pdfplumber`
  (commented until `phase1/akash-scraper` needs it).

Because the base image changes, `scripts/verify_foundation.py --versions` and
notebook cell 2 report the versions actually found rather than trusting the file.

---

## 6. Tests (Sections T, U)

```
232 passed in 1.06s
```

| Suite | Tests | Covers |
|---|---|---|
| `test_config.py` | 18 | Valid load, missing file, malformed YAML, empty file, non-mapping, missing sections/keys, absolute path keys, null scalars, invalid mode, all-errors-at-once |
| `test_paths.py` | 22 | Mode detection (env, filesystem, explicit), local roots, Kaggle roots, **writes never target `/kaggle/input`**, **reads prefer attached Datasets**, fallback to working, search order, error messages |
| `test_io_helpers.py` | 20 | Round trips, atomicity, no temp files left, failed write leaves previous file intact, line-numbered parse errors, undecodable bytes, supported/unsupported serialisation |
| `test_retry.py` | 22 | Policy validation, exponential growth, capping, jitter one-sided, success after transient failure, exhaustion with cause, non-retryable propagation, `give_up_on`, decorator reusability |
| `test_cache.py` | 21 | Key determinism and collision resistance, round trips, namespace isolation, sharding, expiry, **Kaggle Dataset read-through**, Dataset-wins-over-working, corruption |
| `test_schemas.py` | 47 | Per-schema spec/field lockstep, owner validity, unknown-field rejection, and every integrity rule in §3.2 |
| `test_vocabulary.py` | 26 | **Vocabularies start empty**, normalisation, alias resolution, collision rejection, round trips |
| `test_smoke.py` | 35 | Integration (Section U) |
| Total | **232** | |

**Kaggle-path tests use a fake filesystem.** `conftest.py` builds
`tmp_path/kaggle/{working,input/rbi-corpus}` and points the config at it, so the
read-only-input / writable-working split is genuinely exercised locally without
touching a real `/kaggle`.

### Integration smoke test

Run locally — it does not require a real Kaggle environment, because
`PathResolver` resolves correctly in either mode:

```
[PASS] foundation modules import: 16 modules imported
[PASS] branch interface stubs import: 12 modules imported
[PASS] no circular imports: 28 modules import standalone
[PASS] packages have __init__.py: all src packages have __init__.py
[PASS] schemas are complete and owned: 6 schemas, 77 documented fields
[PASS] vocabularies start empty: entity and subject vocabularies are empty, as required
[PASS] T1 label defaults are honest: T1 defaults: unlabelled / empty applies_to / candidate
[PASS] config loads and paths resolve: mode=local, 10 path keys resolved
[PASS] cache round trip: cache write/read round trip succeeded
9/9 checks passed — OVERALL: PASS
```

The circular-import check runs each module as the first import in a fresh
subprocess, because a circular import commonly hides behind import order and
in-process `sys.modules` surgery would leave two copies of every class alive.

**Result on Kaggle: `NOT YET MEASURED`** — pending the manual notebook run.

---

## 7. Evaluation checkpoint (Section V)

| # | Criterion | Result |
|---|---|---|
| 1 | Foundation complete and sufficient for three independent forks | Yes |
| 3 | Audit completeness | Complete |
| 3 | Schema completeness vs required provenance + T1 fields | **77/77, none missing** |
| 3 | Unit test pass rate | **232 / 232 (100%)** |
| 3 | Integration smoke test | **PASS locally**, `NOT YET MEASURED` on Kaggle |
| 6 | PASS definition met | Yes, except the Kaggle run and push, which are manual |
| 9 | Progression permitted | **PASS** → Phase 1 branch prompts may be generated |

### Section Z metrics

```
Repository state at start:      empty working tree; prior implementation in history, not reused (by direction)
Files/modules created:          54
Python modules created:         39   (3,242 LOC src + 1,694 LOC tests)
Files identified as reusable:   0    (greenfield, by direction)
Files requiring modification:   0
Unit tests written:             232
Unit tests passing:             232
Integration smoke test:         PASS (local) / NOT YET MEASURED (Kaggle)
Shared schema fields defined:   77 across 6 schemas
Missing required fields:        none
Branch plan produced:           YES
Kaggle notebook name:           phase0-base-foundation
```

---

## 8. Open items for the mentor

1. **Licensing.** RBI redistribution rights remain an open IPR question. This
   branch takes the conservative position — corpus out of git, benchmark items
   as offsets rather than text — but the question needs answering before any
   public release. `ObligationSpan` is designed so a benchmark can be published
   without the corpus.
2. **Corpus history in `origin/main`.** The 381 committed PDFs remain reachable
   in the public repository's history despite the deletion commit. Purging them
   requires a history rewrite and force-push — a separate decision, not taken here.
3. **Annotation capacity is the critical path.** Nothing else in the project can
   substitute for human labels on `applies_to` and `differential_flag`. This
   should drive Phase 1 sequencing; see the branch plan.

---

## 9. Execution commands (Section X)

**Local, already run:**

```bash
pytest -q                                       # 232 passed
python scripts/verify_foundation.py --versions  # 9/9 PASS
git checkout -b base
git add . && git commit
```

**Kaggle, for the user to run manually:**

1. `git push -u origin base`
2. kaggle.com → **New Notebook → File → Upload Notebook** →
   `notebooks/phase0-base-foundation.ipynb`
3. Name it `phase0-base-foundation`; enable **Internet** in settings
4. **Run All**
5. No Kaggle Dataset is needed for Phase 0 — nothing is produced worth persisting

Report cell 7's output back to close out this phase.
