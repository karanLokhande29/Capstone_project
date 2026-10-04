# RBI-ObliBench Command Center

An explainable, read-only product layer over the RBI-ObliBench research record. It has three faces:

- the **Research Command Center**: traceability, results, audit and submission readiness;
- the **Obligation Explorer** and the **Ask RBI-ObliBench** assistant;
- a **Product Showcase**.

**Two sites from one codebase (D-23, D-24).** Public builds (Azure and the claude.ai copy) contain only the **demo**:
- Home · Cases (Explore, Failure Map, Play, Atlas, `/case/:unitId` Microscope) · Lab · Triage · Results · Method & Trust;
- the hidden `/present`.

It reads small per-route JSON shards from `public/data/` (`npm run data` → `scripts/build_demo_data.py`, with the §C3 assertions) and never the research snapshot. The author workspace (research views, audit, readiness) runs locally only, at `/workspace`. Start with `AUDIT.md`, `DEMO_RUNBOOK.md` and `CHANGELOG.md`.

The benchmark is the research contribution, and the pipeline and comparator are the engineering artefacts. The Command Center itself makes **no LLM calls**.

## Quick start

```bash
cd ui
npm install
npm run ingest      # repo -> src/data/snapshot.json (numbers by results key, pointers, unit predictions, ≤25-word excerpts)
npm run calibrate   # §8.2 confidence: spec -> M2 fitted on dev + frozen -> gold evaluation -> confidence_model_v1.json, docs/CALIBRATION.md
npm run dev         # http://localhost:5181
```

For the production build:

```bash
npm run build && npm run preview
```

The preview is served at http://127.0.0.1:5183.

## Public site (Azure)

**https://rbioblibench5qbvp2.z29.web.core.windows.net/** is an Azure Storage static website in resource group `rg-rbi-oblibench` (Azure for Students).

To update it, sign in with `az login`, then run:

```bash
npm run deploy:azure   # data build + both builds + check_dist (must pass) + gzip upload; every route incl. the 412 case pages returns 200
```

## Comparator API (Phase H)

```bash
npm run api:bundle   # frozen prompt/rule bundle (hash-checked) + server-side inputs in api/.data (gitignored)
npm run api          # local API on :5190 (vite dev proxies /api/health|compare|replay|rehydrate|freshness)
npm run present:local   # presenter mode (full text, freshness) + the app at /present
```

- **Key:** read only from the server process's environment: `ASSISTANT_GEMINI_API_KEY` locally, `GEMINI_API_KEY` as an Azure Function app setting. It must be a key dedicated to the demo. Without it, `/api/health` reports the model unavailable and the UI is replay-only.
- **Azure:** `api/function_app.py` is the Azure Functions wrapper (buffered streaming). It is not deployed yet.
- **Tests:** `npm run test:py` (mocked model).

## Hosted copy

```bash
npm run build:hosted   # -> dist-artifact/page.html + assets/
```

The output is published as a claude.ai Artifact: https://claude.ai/artifact/NqaqjFz3gUz7zrnaFo6V4R. It is private until it is shared from the page's Share menu.
- **Routing:** hash routes (`#/results/t1`). Drawer state is kept in the hash.
- **Content:** the same pitch-only site as Azure. When republishing, set any asset paths that no longer exist to `null`.

## Checks

| Command | What it checks |
|---|---|
| `npm run typecheck` / `npm run lint` | TypeScript strict and ESLint (0 warnings). |
| `npm test` | Vitest:<br>• CI formatter vs `src/eval/ci_format.py`;<br>• R1–R14;<br>• confidence equals the frozen model;<br>• the four §6 chains;<br>• the 10 palette queries;<br>• every screen renders;<br>• the proxy with a mocked LLM;<br>• the live pipeline end to end with a mocked LLM. |
| `npm run test:py` | Python:<br>• the snapshot word budget and the privacy invariants;<br>• calibration freeze order;<br>• the live bridge: a new query string → local bge encode (pinned revision) → class-aware RRF → comparator (mocked) → frozen rule. |
| `npm run build && npm run check:dist` | `ui/dist` and `ui/src/data` contain no RBI run over 25 words (corpus shingles) and no key-like string. |
| Repo root | `python3 -m pytest -q -o addopts= -p no:cacheprovider`, `python3 scripts/release_check.py`, `python3 scripts/build_tables.py --check`. |

`ui/.gitignore` keeps `node_modules/`, `dist/`, `.env` and the proxy's state and cache out of the release check. No release-check exclusion was needed.

## Opt-in assistant and live mode

Both are **off by default** and need two switches:

1. Create `ui/.env` (gitignored) from `.env.example`. Set `ASSISTANT_GEMINI_API_KEY=` to a key from a **separate Google Cloud project**. Never use the experiments' `GEMINI_API_KEY`.
2. Run `npm run server`. This starts the proxy on 127.0.0.1:5182; the dev and preview servers proxy `/api` to it. Then turn the routes on in **Settings** in the app.

Safeguards:
- **Key handling.** The key is read server-side only. It is never sent to the browser and never logged.
- **Daily cap.** `ASSISTANT_DAILY_CAP`, default 50, with a visible counter. "Quota reached", "off" and "offline" states are handled.
- **Cache.** Responses are cached by the sha256 of the prompt (`server/.cache/`); cached answers do not consume quota.
- **Grounded route.** BM25 over local project chunks (snapshot + Master Document v2). The model must cite every claim (`[key]` / `[MD §x]`) or reply "Not in the project record".
  - Every number in an answer is post-checked against the snapshot; a mismatch blocks the answer (R6).
  - Grounding badge: Exact / Partial / Unsupported.
- **Live pipeline.** `server/pipeline_bridge.py` reuses the repo's real class-aware RRF (`src/retrieval/systems.run_query`) and the frozen comparator prompt and rule. The prompt hashes are checked against `FROZEN.json`.
  - Free text is embedded locally with `BAAI/bge-base-en-v1.5 @ a5beb1e3e68b9ab74eb54cfd186867f64f240e1a` (HF offline; the snapshot commit is asserted). Existing benchmark paragraphs use their stored embeddings.
  - The result carries an M2 confidence band labelled "calibrated on benchmark; new queries may differ".

## What is shown, and what is not

- **Numbers.** Every number comes from `reports/results_v2.json` by key (hover any number). CIs are printed exactly as `src/eval/ci_format.py` prints them.
- **RBI text.** At most 25 words per paragraph across everything bundled: a 12-word excerpt plus comparator field values, always with the pointer (id, URL, harvest date, sha256). Direction titles are capped at 20 words. Full text only via `python3 release/rehydrate.py`.
- **Privacy.**
  - Nothing from `reports/private/`, rater-identity mappings or excluded rounds is ingested.
  - Raters appear only as `rater_1`–`rater_3`. Annotator names that occur in the frozen results file are redacted in the snapshot copy (DECISIONS D-18, gap G-28).
- **Confidence (§8.2).** Calibrated for **comparator verdicts only**.
  - M2 (comparator-intrinsic): fitted on the 30-item dev set and frozen before the gold evaluation. It powers the Showcase and every product badge.
  - M1 (full signals, *cross-validated on gold*): research views only.
  - Every badge shows its band's empirical accuracy, Wilson CI and n, and names its model. See [docs/CALIBRATION.md](docs/CALIBRATION.md).
  - Honest limit: the High band is almost entirely `same` verdicts; `different` verdicts are routed to review.
- **Caveats.** T3's filter-on 1.000 is circular and is never shown as a win (R3). T2 gains always carry the by-construction caveat (R2). The A11 scoring asymmetry is shown wherever T1 F1 or coverage appears.

## Layout

```
scripts/   ingest.py, calibrate.py, check_dist.py, cc_common.py, tests/
server/    Hono proxy (app.ts, llm.ts, grounding.ts, store.ts, bridge.ts, index.ts) + pipeline_bridge.py
src/       domain/ (types), data/ (repository, derive, store, snapshot, confidence), intelligence/ (R1–R14),
           lib/ (ci, keys, export), components/ (drawer, CI cell, forest plot, badges), features/<screen>/
docs/      ANALYSIS.md (Part B), DECISIONS.md, CALIBRATION.md, PROGRESS.md
```
