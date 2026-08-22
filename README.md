# RBI Compliance Corpus & RBI-ObliBench (Weeks 1–5)

Engineering artifact supporting an **Agentic RAG compliance system** for RBI Master Directions.
The research contribution is **RBI-ObliBench** — an applicability- and amendment-aware
benchmark — and the applicability / differential-obligation evaluation. Agentic RAG,
hybrid retrieval, and LangGraph are engineering choices, not claimed research novelties.

## Scope (this repository state)

Implemented: **Weeks 1–5 only**

- Week 1: environment, scraper, metadata schema, Matrix v0
- Week 2: extraction pilot, temporal metadata, alignment/FAQ/licensing checks
- Week 3: full harvest, paragraph segmentation, cross-references, Matrix v1
- Week 4: supplementary sources, deontic candidates, cross-class matching, T1 candidates
- Week 5: stratified validation sample, annotation template, validated set (honest empty if unannotated)

Not implemented yet: Weeks 6–15 (RePASs audit, retrieval baselines, class-aware/temporal
retrieval, Agentic RAG, ablations, paper, release).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configuration: `config/config.yaml` (paths, rate limits, pilot sizes).

## Run pipeline

```bash
# Full Weeks 1–5 orchestration (resumable; caches downloads)
python scripts/run_weeks_1_to_5.py

# Or week-by-week:
python scripts/run_week1.py
python scripts/run_week2.py
python scripts/run_week3.py
python scripts/run_week4.py
python scripts/run_week5.py
```

## Tests

```bash
pytest -q
```

Tests use mocked HTTP responses only — no live network calls.

## Key outputs

| Artifact | Path |
|----------|------|
| Scrape manifest | `data/metadata/scrape_manifest.json` |
| Matrix v0 / v1 | `data/matrix/matrix_v0.csv`, `data/matrix/matrix_v1.csv` |
| T1 candidates | `data/benchmark/candidate/t1_candidates.csv` |
| T1 validated | `data/benchmark/validated/t1_validated.csv` |
| Week metrics | `reports/week{1..5}_metrics.json` |
| Consolidated summary | `reports/weeks_1_to_5_summary.md` |

## Integrity rules

- Document / entity-class / subject-family counts are **discovered**, never hard-coded.
- Metrics that were not measured are recorded as `NOT YET MEASURED`.
- Failures are recorded as `FAILED — [reason]`.
- Candidate items are never silently labeled as validated.
- Synthetic data appears only in unit tests.

## Licensing

Redistribution of RBI content is an open IPR question — see `reports/week2_licensing_note.md`.
# Capstone_project
