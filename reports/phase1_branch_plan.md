# Phase 1 — Branch Map & Dependency Graph

**Produced by:** Phase 0 (P0-001) · **Fork point:** `base` · **Date:** 2026-08-22

> **Do not create these branches yet.** They fork from `base` only after the
> Phase 0 output passes audit. This document is the plan, not the execution.

---

## 1. Branch map

```
main ──▶ base ──┬──▶ phase1/akash-scraper     (acquisition → paragraphs)
                ├──▶ phase1/karan-matrix      (vocabulary → matrix)
                └──▶ phase1/meer-annotation   (candidates → validated labels)
```

Each branch forks from `base` and **never from another Phase 1 branch**. Merges
go back to `base`, not sideways.

### 1.1 File scope — designed for zero overlap

The scope split below is the point of Phase 0. No file appears in two branches,
so three people working simultaneously produce no merge conflicts in code.

| Branch | Owner | Exclusive write scope |
|---|---|---|
| `phase1/akash-scraper` | Akash | `src/scraper/**`, `src/extraction/**`, `src/preprocessing/**`, `tests/test_scraper*.py`, `tests/test_extraction*.py`, `tests/test_preprocessing*.py`, `scripts/run_harvest.py`, `notebooks/phase1-akash-*.ipynb` |
| `phase1/karan-matrix` | Karan | `src/metadata/**`, `src/matrix/**`, `tests/test_metadata*.py`, `tests/test_matrix*.py`, `scripts/run_matrix.py`, `notebooks/phase1-karan-*.ipynb` |
| `phase1/meer-annotation` | Meer | `src/benchmark/**`, `tests/test_benchmark*.py`, `scripts/run_annotation.py`, `notebooks/phase1-meer-*.ipynb`, `data/benchmark/**` (gitignored payloads; templates excepted) |

### 1.2 Shared, read-only to all three

| Path | Rule |
|---|---|
| `src/common/**` | **Base-branch change only.** Needs agreement from all three owners. |
| `src/schemas/**` | **Base-branch change only.** A schema change lands under everyone at once. |
| `config/config.yaml` | Base-branch change, *except* each branch may fill in its own `TODO(phase1/<branch>)` value. Those TODOs are placed in distinct blocks so even that does not conflict. |
| `requirements.txt` | Base-branch change. Adding a dependency affects every branch's Kaggle runtime. |
| `reports/phase0_*.md` | Frozen. Phase 1 writes `reports/phase1_<owner>_*.md`. |

**If a branch needs a schema field that does not exist, it stops and requests a
base change.** Adding the field locally is the one action that reliably breaks
the other two branches, and `FIELD_SPECS` enforcement makes it fail the test
suite rather than fail silently.

---

## 2. Branch scopes in detail

### 2.1 `phase1/akash-scraper` — corpus acquisition

**Implements:** `src/scraper/interfaces.py`, `src/extraction/interfaces.py`,
`src/preprocessing/interfaces.py`

**Produces:** `DocumentRecord` set (corpus manifest), extracted text,
`ParagraphRecord` set with section/clause provenance and cross-references.

**Consumes from base:** `PathResolver`, `ArtifactCache`, `retry_call`,
`get_logger`, I/O helpers, `DocumentRecord`, `ParagraphRecord`,
`stable_paragraph_id`.

Load-bearing requirements:

* **Validate payloads before caching.** A bot-challenge HTML page saved under a
  `.pdf` name becomes a permanent cache hit and is far more expensive to detect
  downstream than at download time.
* **Populate `section_id` / `clause_path`.** These cannot be recovered once
  extraction has flattened a document to an undifferentiated string, and a bare
  paragraph index is not a legal citation. This is the field most likely to be
  skipped and most expensive to add later.
* **Use `stable_paragraph_id` and nothing else.** Annotations key on it; a
  different derivation silently detaches completed annotation work.
* **Discovery is separate from download**, so a download failure never silently
  shrinks the recorded corpus size.

**Blocks:** both other branches.

### 2.2 `phase1/karan-matrix` — vocabulary and coverage matrix

**Implements:** `src/metadata/interfaces.py`, `src/matrix/interfaces.py`

**Produces:** discovered entity-class and subject-family vocabularies,
normalised `DocumentRecord` / `ParagraphRecord` fields, temporal metadata, the
full `MatrixCell` set, and routing.

**Consumes:** Akash's `DocumentRecord` set; base utilities; `Vocabulary`,
`VocabularyTerm`, `MatrixCell`.

Load-bearing requirements:

* **Discover the vocabulary; never seed it.** Start from
  `empty_entity_class_vocabulary()`. A discovered count that disagrees with the
  ~11 / ~26 planning estimate is a finding to report, not an error to correct.
* **Write normalised values to `entity_class`; leave `*_raw` untouched.**
* **Emit a cell for every axis pair, including unpopulated ones.** The
  unpopulated cells are the interesting output; dropping them turns a measured
  gap into a silent absence.
* **Record every unresolved surface form** — that set is the honest measure of
  normalisation coverage.
* `populated` and `ambiguous` are independent; a cell can be both.

**Partially blocks:** Meer needs normalised classes for stratification, but not
for candidate extraction.

### 2.3 `phase1/meer-annotation` — benchmark construction and annotation

**Implements:** `src/benchmark/interfaces.py`

**Produces:** T1 candidate pool, per-annotator task files, ingested annotations,
measured agreement, the validated T1 set.

**Consumes:** Akash's `ParagraphRecord` set; Karan's normalised classes (for
stratification only); `T1Label`, `ObligationSpan`, `DifferentialFlag`,
`LabelStatus`.

Load-bearing requirements — these are correctness rules, enforced by
`T1Label.validate()`:

* **Never derive `applies_to` from `entity_class`.** That produces a label
  restating its own input, which cannot support RQ1.
* **Never default `differential_flag` to `absent`.** Leave it `unlabelled` until
  examined, or unexamined items become a positive finding.
* **Never promote to `validated` implicitly.** Promotion requires
  `config.benchmark.min_annotators_per_item` independent annotations.
* **Report agreement as `"NOT YET MEASURED"` until computed**, never as `0.0`.
* Do not stratify on `differential_flag` while it is mostly `unlabelled` —
  that samples the extractor's blind spots rather than the corpus.

**Blocks:** nothing downstream in Phase 1, but is the **critical path for the
research contribution**. Without validated labels and a measured agreement
statistic, RBI-ObliBench is a candidate pool, not a benchmark. Nothing else in
the project can substitute for human labels here, and annotation capacity is the
one resource that cannot be recovered by working faster later.

---

## 3. Dependency graph

### 3.1 Phase 0 → Phase 1

```
                        ┌─────────────────────────┐
                        │   base (Phase 0)        │
                        │                         │
                        │  src/common/            │
                        │    config, paths,       │
                        │    io, retry, cache,    │
                        │    logging, verify      │
                        │  src/schemas/           │
                        │    Document, Paragraph, │
                        │    Vocabulary, Matrix,  │
                        │    ObligationSpan, T1   │
                        │  config/config.yaml     │
                        └───────────┬─────────────┘
                                    │ all three consume
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
   ┌────────────────────┐ ┌───────────────────┐ ┌────────────────────┐
   │ phase1/            │ │ phase1/           │ │ phase1/            │
   │ akash-scraper      │ │ karan-matrix      │ │ meer-annotation    │
   │                    │ │                   │ │                    │
   │ DocumentRecord[]   │ │ Vocabulary x2     │ │ T1Label[] cand.    │
   │ extracted text     │ │ normalised fields │ │ annotation tasks   │
   │ ParagraphRecord[]  │ │ temporal metadata │ │ agreement stat     │
   │ cross-references   │ │ MatrixCell[]      │ │ T1Label[] valid.   │
   └─────────┬──────────┘ └─────────┬─────────┘ └─────────┬──────────┘
             │                      │                     │
             │ DocumentRecord[]     │                     │
             ├─────────────────────▶│                     │
             │                      │                     │
             │ ParagraphRecord[]    │                     │
             ├────────────────────────────────────────────▶
             │                      │ normalised classes  │
             │                      ├────────────────────▶│
             │                      │  (stratification)   │
```

**Reading the arrows:** Akash blocks both. Karan partially blocks Meer —
candidate extraction can begin without normalisation, only stratification needs
it. Meer blocks nobody in Phase 1 and everything in Phase 2+.

### 3.2 Sequencing implication

The graph makes Akash the schedule bottleneck and Meer the *research*
bottleneck, which pull in opposite directions. Two consequences:

1. Akash should ship a **small validated slice** of `ParagraphRecord`s early —
   enough for Meer to build and pilot the annotation protocol — before
   completing the full harvest. A protocol piloted in week 1 and a corpus
   completed in week 3 beats both finishing in week 3.
2. Karan can build vocabulary discovery against that same slice, then re-run at
   full corpus scale. Vocabulary code does not care how many documents it sees.

### 3.3 What later phases need from this base

| Phase | Depends on |
|---|---|
| Retrieval (Wk 7+) | `ParagraphRecord.retrieval_*` fields (reserved, unpopulated); `config.retrieval.embedding_model` (deliberately `null`) |
| Temporal / amendment (Wk 8+) | `in_force_from` / `in_force_to`; `content_hash` for cross-snapshot change detection |
| Evaluation (Wk 9+) | Validated `T1Label` set; `applies_to`; `differential_flag`; `agreement_score` |
| Agentic RAG (Wk 11+) | Matrix routing; `clause_path` for citation-grade answers |
| Release (Wk 15) | `ObligationSpan` offsets, which allow publishing the benchmark without redistributing RBI text |

The base is designed so none of these requires a schema change: the fields are
already declared, documented, owned, and nullable.

---

## 4. Per-branch prompt checklist

Each Phase 1 prompt can be written from this document without further
architecture decisions. Every branch prompt must specify:

- [ ] Branch name and fork point (`base`)
- [ ] Owner and exclusive file scope from §1.1
- [ ] Which `interfaces.py` functions it implements
- [ ] Which base utilities and schemas it consumes
- [ ] The load-bearing requirements from §2 for that branch
- [ ] Model (Opus for design-bearing work — normalisation policy, annotation
      protocol, matrix semantics; Sonnet for mechanical implementation against a
      fixed interface)
- [ ] Kaggle notebook name (`phase1-<owner>-<task>`)
- [ ] Metrics to collect, with `NOT YET MEASURED` / `FAILED — <reason>` for
      anything unmeasured
- [ ] Explicit prohibition on editing `src/common/**` or `src/schemas/**`

---

## 5. Merge protocol

1. Branch completes; its own tests plus the full base suite pass on Kaggle.
2. Owner opens a PR into `base` (not `main`).
3. Reviewer confirms the diff touches **only** that branch's scope from §1.1.
4. Merge into `base`. Other owners rebase onto the updated `base`.
5. `base` merges into `main` only at phase boundaries.

A diff touching `src/common/` or `src/schemas/` is rejected on sight and
re-raised as a base-branch change with all three owners.
