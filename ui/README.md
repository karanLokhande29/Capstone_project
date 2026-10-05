# RBI-ObliBench demo and Command Center

> This is not a chatbot over RBI documents. It is a benchmark and inspection environment for finding, explaining and stress-testing differences between regulatory obligations.

**Live site:** https://rbioblibench5qbvp2.z29.web.core.windows.net
**Comparator API:** https://rbiob-api-5qbvp2.azurewebsites.net/api/health

Key documents:
- `AUDIT.md`: what was checked, branch decisions, QA;
- `DEMO_RUNBOOK.md`: how to present;
- `CHANGELOG.md`: every user-visible change, and the source of every number;
- `docs/DECISIONS.md`: D-01 to D-28.

## What it is

RBI issues a separate Master Direction for each kind of regulated institution (banks, NBFCs, co-operative banks and others), so the same topic recurs with small but important differences.

The demo is built on **412 comparisons labelled by an expert**: one institution type's obligation against the closest rule for another type, labelled *same*, *different* or *no matching rule*. The same 412 comparisons were answered by:
- five LLM systems;
- a **structured comparator**. Its model extracts 13 fields from both rules, and a fixed rule, frozen by sha256 before any test run, decides the verdict.

Every answer is sealed. The site shows them all and lets you inspect, replay and re-run them.

## Pages

| Route | What you can do |
|---|---|
| `/` **Home** | Play a spot-the-difference round on a verified case that all five LLMs missed and the comparator caught. Then the positioning, four stats, and next-step cards ordered by persona ("I'm here as…"). |
| `/cases` **Explore** | Three entry cards, eight filters plus a paragraph-id search over the 412 cases. |
| `/case/:unitId` **Microscope** | See one case in full:<br>• both paragraph excerpts with RBI links;<br>• every system's answer, marked when the gold paragraph was in context;<br>• the X-Ray of what each LLM was given;<br>• the 13-field table (click to highlight by string match);<br>• the frozen-rule decision trace;<br>• confidence: "Flagged for review" on *different*;<br>• the provenance drawer. |
| `/cases/failures` **Failure Map** | The 78 real differences × systems: caught, reasoning failure, retrieval failure (hatched), abstained, never answered. Includes the "Why the comparator misses" drill-down. |
| `/cases/play` **Play** | Curated hard cases (the 56 every LLM missed) or a random draw. Scored against the best LLM and the comparator over the same rounds. |
| `/cases/atlas` **Atlas** | 11 institution types × 57 topics: which have Directions, where the test questions come from, and ambiguous cells. |
| `/lab` **Lab** | Re-run a benchmark pair live, sealed vs live, with a "Live ≠ sealed" diff. Also cached replays, paste mode (unvalidated; only a hash is stored), the edit lab (read-only in public) and a token cost meter. |
| `/triage` **Triage** *(post-paper)* | A threshold slider over the M2 confidence: coverage, accuracy, what goes to review (bootstrap 95% ranges), a reliability diagram and the feature weights. An observed trade-off, not a recommendation. |
| `/results` **Results** | Six findings with plain-language meanings and fine print, plus the T2 filter animation, the T3 date timeline and the RePASs playground. |
| `/method` **Method & Trust** | How it was built, two separately evaluated lanes, safeguards, the actor-masked sensitivity analysis (post-paper), limits, cost, frozen-file hashes and licences. |
| `/present` | Hidden presenter mode: preflight, then an 8-step 3-minute script. Keys: ← → R L B F. |

**Status badges** on every page: Benchmark · sealed / Live re-run / Cached replay / Unvalidated input / Post-paper / Live ≠ sealed.

**RBI text:** at most 12 words per excerpt and 25 per paragraph across the whole site, always linked to RBI's PDF. Full text appears only in local presenter mode.

## Run it locally

```bash
cd ui
npm install
npm run data     # repo -> public/data/*.json (per-route shards); runs every §C3 assertion and stops on any mismatch
npm run dev      # http://localhost:5181  (author workspace at /workspace)
```

The author workspace also needs `npm run ingest` (research snapshot) and `npm run calibrate` (confidence model). Both make no LLM calls.

### Live comparator on your laptop

```bash
npm run api:bundle      # frozen prompt + rule (sha256-checked) and server-side inputs in api/.data (gitignored)
npm run present:local   # comparator API on :5190 in presenter mode + the app at /present
```

- **Key:** set `ASSISTANT_GEMINI_API_KEY` in that terminal first. Use a key dedicated to the demo, never the experiments' `GEMINI_API_KEY`.
- **Without a key** the API reports the model as unavailable and the UI is replay-only.
- **Test double:** `MOCK_LLM=sealed npm run api` is a test double for UI checks. It is labelled "Test double", never "Live", and its runs are never saved as replays.

## Deploy

| What | Command | Notes |
|---|---|---|
| Public site (Azure Storage static website, `rg-rbi-oblibench`) | `VITE_API_BASE=https://rbiob-api-5qbvp2.azurewebsites.net npm run deploy:azure` | Runs the data build, both builds and `check_dist`; refuses to deploy if any check fails. Gzips JS/CSS/JSON. All 412 case URLs return 200. |
| Comparator API (Azure Function, Flex Consumption, Central India) | `bash api/deploy_function.sh` | Re-runnable. Asks for the Gemini key in your terminal; the key is never written to a file. Uploads recorded runs as cached replays, then redeploys the site. |
| claude.ai copy (private until shared) | `npm run build:hosted` | Republish `dist-artifact/page.html` with every file in `dist-artifact/files.json`, setting removed asset paths to `null`. |

**To rotate the key:** update only the Function's app setting `GEMINI_API_KEY`. Enter the new key through a hidden dialog, not the app's terminal panel, which echoes pasted text.

## Checks

| Command | What it checks |
|---|---|
| `npm run typecheck` / `npm run lint` | TypeScript strict; ESLint with 0 warnings. |
| `npm test` | Vitest (101 tests):<br>• every demo route renders from the real shards;<br>• honesty invariants: B2 names, "Flagged for review", triage 162/156 with no "recommended / optimal / safe", sensitivity label next to its numbers;<br>• Failure Map error counts equal the published table;<br>• no label leaks before a guess;<br>• SSE parsing and "Live ≠ sealed";<br>• the workspace screens. |
| `npm run test:py` | Python (26 tests): UI ingest and privacy tests, and 19 comparator API tests with a mocked model. The API tests cover:<br>• 5 units reproducing the sealed output;<br>• hash mismatch → 503;<br>• buffered fallback;<br>• rate limit;<br>• a paste-mode marker never stored or logged. |
| `npm run check:dist` | All builds and `public/data`: no RBI run over 25 words, no key-like strings, the §14 honesty grep, and no full-text endpoint in public builds. |
| Repo root | `python3 -m pytest -q -o addopts=` (1211 tests), `python3 scripts/release_check.py` and `python3 scripts/build_tables.py --check`. |

**Accessibility:** axe-core 4.10 reports 0 violations on every route, in light and dark.

## Honesty rules the code enforces

- **Frozen files** are read and never edited: gold, `results_v2.json`, the comparator prompt and rule, the confidence model. Their hashes are shown, and the API refuses to run if they change.
- **Per-unit data** comes only from run files; nothing is derived from aggregate tables.
- **Verdicts** always come from the frozen rule, traced, and never from free text. Model rationales are never shown.
- **Live fields** appear only once parsed from the model's output; there are no staged animations. Replays are labelled with their recording time.
- **Pasted text** is never stored.
- **Confidence, triage and the sensitivity analysis** are tagged *Post-paper*. A *different* verdict is "Flagged for review" (the expert agreed 38 of 108 times), never a confidence band.

## Layout

```
scripts/   build_demo_data.py (public/data shards + §C3 assertions), ingest.py, calibrate.py, check_dist.py,
           deploy_azure.sh, artifact_page.py, cc_common.py, tests/
api/       core.py (service), jsonstream.py, server.py (local), function_app.py (Azure), build_bundle.py,
           deploy_function.sh, bundle/ (frozen files + M2), tests/
public/    data/ (home, cases/index + 106 case shards, results, triage_grid, method, t2/t3/t4, matrix, cost, edit_bases)
src/       features/demo/ (public site: Home, cases/, case/, play/, lab/, present/, Triage, Results, Method),
           features/* (author workspace), components/, data/, domain/, intelligence/, lib/
server/    Hono proxy for the workspace assistant (local only) + pipeline_bridge.py
docs/      ANALYSIS.md, DECISIONS.md, CALIBRATION.md, PROGRESS.md
```
