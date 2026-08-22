# RBI-ObliBench — Agentic RAG Compliance System for RBI Master Directions

A 15-week B.Tech AI capstone. The research contribution is **RBI-ObliBench**: a
retrieval-grade, applicability- and amendment-aware benchmark built from RBI
Master Directions, together with its applicability and differential-obligation
evaluation (RQ1, RQ2) and a metric-integrity audit (RQ3). The Agentic RAG system
is the engineering artifact, not the claimed novelty.

**Current state: Phase 0 — shared foundation only.** No scraping, no
normalisation, no matrix population, no annotation, no retrieval. Every
workstream module contains interface stubs that raise `NotImplementedError`
naming the branch that will implement them.

---

## Repository layout

```
config/config.yaml          Single shared config. Every branch loads it.
src/common/                 Shared utilities — the foundation.
  config.py                 Loading + loud validation
  paths.py                  Dual-mode (local / Kaggle) path resolution
  io_helpers.py             Atomic JSON / JSONL / text I/O
  retry.py                  Exponential backoff with jitter
  cache.py                  Content-addressed cache over Kaggle Datasets
  logging_setup.py          Standard logging
  verify.py                 Foundation self-check
  errors.py                 Exception hierarchy
src/schemas/                Shared record contracts. Owner-neutral by design.
  provenance.py             DocumentRecord, ParagraphRecord
  vocabulary.py             Vocabulary, VocabularyTerm (start empty)
  matrix.py                 MatrixCell
  benchmark.py              T1Label, ObligationSpan
src/scraper/                }
src/extraction/             } phase1/akash-scraper   — interface stubs
src/preprocessing/          }
src/metadata/               } phase1/karan-matrix    — interface stubs
src/matrix/                 }
src/benchmark/              phase1/meer-annotation   — interface stubs
tests/                      232 tests, no network, Kaggle paths mocked
scripts/verify_foundation.py
notebooks/phase0-base-foundation.ipynb
reports/                    Audit and branch plan
data/                       Directory contract only — contents are gitignored
```

`src/schemas/` deliberately sits outside every workstream package: all three
branches read and write these records, so placing them under one branch's
package would misrepresent ownership and put the contract inside that branch's
edit scope.

Modules for later phases (`retrieval/`, `temporal/`, `evaluation/`, `agent/`)
are **not** created. They have no near-term purpose, and empty packages invite
premature commitment to a structure the research has not yet justified.

---

## Two things every branch must honour

**1. Vocabularies are discovered, never declared.** No entity class or subject
family is hard-coded anywhere. The planning estimates (~11 classes, ~26
families) are estimates; a discovered count that disagrees with them is a
finding to report, not a bug to fix. `empty_entity_class_vocabulary()` returns
an empty vocabulary and a test enforces that it stays empty.

**2. Unmeasured is not zero.** Report `"NOT YET MEASURED"` for a statistic that
has not been computed and `"FAILED — <reason>"` for one that could not be. In
particular, `T1Label.differential_flag` defaults to `"unlabelled"`, never
`"absent"` — defaulting to `absent` would turn every unexamined item into a
positive finding. And `applies_to` is an annotation target: deriving it from the
source document's `entity_class` produces a label that restates its own input
and cannot support any applicability claim.

---

## Running on Kaggle

All compute happens on Kaggle Notebooks. The local machine is used only for
authoring code, running unit tests, and pushing to GitHub.

1. **Push the branch to GitHub.**
2. On [kaggle.com](https://www.kaggle.com): **New Notebook → File → Upload
   Notebook**, select `notebooks/phase0-base-foundation.ipynb`. Name it
   `phase0-base-foundation`.
3. In the notebook settings, enable **Internet** (needed to clone the repo).
4. **Run All.** The first cell clones the repository; the rest import `src/`,
   run the test suite, and run the foundation check.
5. If a run produces data worth keeping, save it with **New Dataset** (or **New
   Version** on an existing one) from the Kaggle UI, then add that dataset's
   slug to `environment.kaggle.input_datasets` in `config/config.yaml`.

There is no Kaggle CLI step and no `kernel-metadata.json`. Deployment is by hand
through the website.

### Why paths are resolved, never written literally

On Kaggle, attached Datasets mount **read-only** at `/kaggle/input/<slug>` while
only `/kaggle/working` is writable. Code that resolves one path and then both
reads and writes it works locally and fails on Kaggle. So `PathResolver` splits
the two:

| | Reads | Writes |
|---|---|---|
| Local | repo root | repo root |
| Kaggle | `/kaggle/input/<slug>` first, then `/kaggle/working` | `/kaggle/working` only |

```python
from src.common.config import load_config
from src.common.paths import PathResolver

cfg = load_config()
paths = PathResolver.from_config(cfg)      # detects the environment

paths.read_path("raw", "md_1.pdf")          # searches Datasets, then working
paths.write_path("processed", "md_1.jsonl") # always writable, parents created
```

Never build `data/...` or `/kaggle/...` by hand. Add a key to `paths:` in
`config/config.yaml` instead.

The same ordering makes the cache work across sessions: a corpus harvested
last session and saved as a Dataset is a cache **hit** this session, so a re-run
costs nothing instead of re-downloading the corpus.

---

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # Phase 0 needs nothing beyond stdlib + PyYAML

pytest -q                                # 232 tests
python scripts/verify_foundation.py --versions
```

Tests make no network calls. Kaggle paths are exercised against a fake
`/kaggle` filesystem built under `tmp_path`, so the read-only-input / writable-
working split is genuinely tested without a Kaggle session.

---

## Git workflow

```
main ──▶ base ──┬──▶ phase1/akash-scraper
                ├──▶ phase1/karan-matrix
                └──▶ phase1/meer-annotation
```

`base` is the fork point. All three Phase 1 branches fork from it and never from
each other. See [reports/phase1_branch_plan.md](reports/phase1_branch_plan.md)
for the file-scope split, which is designed so no two branches edit the same
file.

**Changing anything in `src/common/` or `src/schemas/` is a base-branch change**
and needs agreement from all three owners, because it lands under everyone at
once. Adding a field to a schema without declaring its owner in `FIELD_SPECS`
fails the test suite by design.

---

## Data and licensing

Whether RBI Master Directions may be redistributed as part of a public research
benchmark is an **open IPR question** and is not assumed to be settled by their
public availability on rbi.org.in.

Accordingly: `data/raw/**` and `data/extracted/**` are gitignored, source
documents live in a private Kaggle Dataset, and benchmark artifacts reference
source text by document ID, paragraph ID and character offset rather than
embedding it. `ObligationSpan` stores offsets for exactly this reason — it is
fully reproducible for anyone holding the corpus without republishing the text.

Raise the redistribution question with the mentor / institutional IPR cell
before any public release.
