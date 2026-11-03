# RBI-ObliBench

A benchmark and a class- and date-aware RAG system for **Reserve Bank of India (RBI) Master Directions**:

- does a system know which entity class an obligation binds, and what differs between parallel Directions (T1, T2)?
- does it respect amendment dates (T3)?
- does the RePASs faithfulness metric survive gaming on Indian regulatory text (T4)?

The corpus has 381 Directions and 76,188 paragraphs. The benchmark has four tasks, and every result carries a bootstrap
95% CI.

- **Report (draft):** [reports/final/rbi_oblibench_report.md](reports/final/rbi_oblibench_report.md)
- **Tables:** [reports/tables/](reports/tables/), with all numbers in [reports/results_v1.json](reports/results_v1.json)
- **Dataset card:** [release/DATASET_CARD.md](release/DATASET_CARD.md)
- **Release data (pointers only, no RBI text):** [release/data/](release/data/)

## Setup

Tested on macOS arm64 with Python 3.14.3.

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements-lock.txt     # exact versions of the environment used
cp .env.example .env                                # only for LLM runs: fill GEMINI_API_KEY / GROQ_API_KEY
python3 -m pytest -q                                # the test suite (no network, no LLM calls)
```

- `requirements.txt` keeps the original, looser Kaggle notes; `requirements-lock.txt` is the lock.
- RePASs (T4) runs in its own environment ([requirements-repass-lock.txt](requirements-repass-lock.txt)), from a checkout
  of https://github.com/RegNLP/RePASs at the commit in [NOTICE.md](NOTICE.md), under `external/`.
- API keys are read from `.env`, which is never committed, and are never printed.

## Get the text (rehydrate)

The release holds no RBI text. It holds pointers: Direction id, paragraph id, character offsets, source URL, harvest
date and the sha256 of the paragraph text. To rebuild the text from RBI's own URLs:

```bash
python3 scripts/rehydrate.py --sample 5 --out rehydrated/    # quick check: the Directions behind 5 T1 items
python3 scripts/rehydrate.py --out rehydrated/               # every Direction (downloads ~381 PDFs)
```

It reports `matched` / `drifted` / `missing` paragraphs. RBI updates consolidated Directions in place
("Updated as on …"), so some drift is expected over time.

## Pipeline: one command per stage

| Stage | Command |
|---|---|
| Scraper, text extraction and paragraph segmentation → `data/processed/` | `python3 scripts/run_harvest.py all` |
| Entity-class and subject-family vocabularies, and the Subject × Entity-Class Matrix → `data/matrix/` | `python3 scripts/run_matrix.py all` |
| Obligation candidates (P2-001) | `python3 scripts/run_candidates.py extract` |
| Cross-class matching (P2-002; embeddings run on Kaggle) | `python3 scripts/run_matching.py units`, then the notebook it writes |
| T1 candidate benchmark (P2-004) | `python3 scripts/run_t1.py candidates` |
| T2 retrieval baselines (P3-001) | `python3 scripts/run_p3001.py index && python3 scripts/run_p3001.py qrels && python3 scripts/run_p3001.py retrieve && python3 scripts/run_p3001.py score` |
| T3 temporal set | `python3 scripts/run_t3.py build` |
| T4 RePASs audit (P3-002) | `python3 scripts/run_t4.py questions` … `python3 scripts/run_t4.py analyze` (see its `--help`) |
| RAG systems and ablations (P4; LLM calls) | `python3 scripts/run_p4.py t1 --system <system>`, `t2`, `t3`, `t4`, then `python3 scripts/run_p4.py report` |
| Evaluation harness: all tables and `results_v1.json` | `python3 scripts/build_tables.py` |
| Release data (pointer-only, pseudonymised) | `python3 scripts/build_release.py` |
| Release safety check | `python3 scripts/release_check.py` |

Human labels (T1, T3 spot-checks, T4 ratings) are in `release/data/`. The labelling stages above only regenerate the
blank sheets.

## Reproduce each table

Each command prints one table from the committed metrics files; a public clone uses `release/provenance/` for the few
inputs that live outside the public tree.

| Table | Command |
|---|---|
| 1. Corpus and matrix | `python3 scripts/build_tables.py --only 01` |
| 2. Candidate extraction precision | `python3 scripts/build_tables.py --only 02` |
| 3. Cross-class matching validation | `python3 scripts/build_tables.py --only 03` |
| 4. Supplementary-source decisions | `python3 scripts/build_tables.py --only 04` |
| 5. T1 labels, routes, reliability | `python3 scripts/build_tables.py --only 05` |
| 6. T2 baselines and the P4 retrieval stage | `python3 scripts/build_tables.py --only 06` |
| 7. T1 systems and long-context | `python3 scripts/build_tables.py --only 07` |
| 8. T3 and ablation B | `python3 scripts/build_tables.py --only 08` |
| 9. T4 RePASs audit | `python3 scripts/build_tables.py --only 09` |
| 10. Ablations A–C | `python3 scripts/build_tables.py --only 10` |
| 11. LLM usage | `python3 scripts/build_tables.py --only 11` |
| 12–13. Per-class T1 results and error analysis | `python3 scripts/build_error_analysis.py` (needs the P4 run outputs in `data/rag_runs/`, which `run_p4.py` writes) |

## Demo

```bash
python3 scripts/demo.py "What minimum share of the loan portfolio must consist of loans of up to Rs 25 lakh?" --class "Small Finance Banks"
python3 scripts/demo.py "<question>" --class "<entity class>" --as-of 2026-03-01 [--no-class-filter] [--no-temporal-filter] [--no-verifier]
```

The demo needs a Gemini API key in `.env`. It prints:

- the answer, or an abstention;
- the cited paragraphs, with Direction titles and ids;
- the filters applied;
- the verifier verdicts;
- the LLM calls used.

**Limits:**

- It uses the free-tier `gemini-3.5-flash-lite`. Answers can change as the hosted model changes, and the daily quota can
  run out.
- The corpus holds only the current (amended) text of each Direction. For a date before an amendment, the demo can say
  the paragraph was amended later, but it cannot show the older wording.
- The verifier abstains often. It is not legal or compliance advice.

## Licences

- **Code:** MIT ([LICENSE](LICENSE)).
- **Annotations and derived metadata:** CC BY 4.0 ([release/LICENSE-DATA](release/LICENSE-DATA)). This covers the
  annotations only.
- **RBI documents** are not included and not licensed by this project.
- **Third-party components:** [NOTICE.md](NOTICE.md).
- **Citation:** [CITATION.cff](CITATION.cff).

## Notes for running on Kaggle

The original corpus harvest and the P2-002 embeddings ran on Kaggle Notebooks. `PathResolver` (`src/common/paths.py`)
reads from `/kaggle/input/<slug>` first and writes only under `/kaggle/working`. Never build `data/...` paths by hand;
add a key under `paths:` in `config/config.yaml` instead. Annotation sheets never travel to Kaggle.
