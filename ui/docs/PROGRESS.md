# Command Center build progress (resume from here)

| Step | Status | Notes |
|---|---|---|
| Step 0 frozen-file integrity | DONE | All 8 hashes OK (2026-10-03 16:28 IST). |
| Part A verify A1–A9 | DONE | All present in MD v2 and main.tex. |
| Part A A11–A16 | DONE | A11 scoring asymmetry; A12 scan/dossier → v2; A13 deliverables rebuilt; A14 prompt copied; A15 `reports/final/venue_check_v1.md`; A16 placeholders listed. Checks green (pytest 1211, release PASS, tables up to date, scan 0 unsourced, check_paper --allow-placeholders PASS). |
| Part B | DONE | `ui/docs/ANALYSIS.md`. |
| Phase 2 ingest + domain + CI | DONE | `scripts/ingest.py` → `src/data/snapshot.json` (2.5 MB). It cross-checks every unit-level rebuild against results_v2 (confusions, missed A/B, retrieval-vs-reasoning) and stops on mismatch. `src/lib/ci.ts` matches ci_format.py on all vectors. |
| Phase 6 calibration | DONE | `scripts/calibrate.py`: M2 fitted on dev and frozen, then gold evaluation; M1 grouped 5-fold. Report `docs/CALIBRATION.md`. |
| Phases 3–5, 7–8 screens | DONE (first pass) | All §7 screens, drawer, palette, R1–R14, assistant + live proxy (mocked tests), Showcase, tour, diff, workbench, review queue, exports. |
| Checks after first pass | GREEN | tsc, eslint, vitest 36, vite build, check_dist PASS (after capping titles at 20 words), python UI tests 7, repo pytest 1211, release_check PASS, build_tables --check. |
| Tests added | DONE | §6 chains, 10 palette queries, 23 screen renders + fixture, server (mocked LLM) + live e2e; vitest 79, python 7. |
| Visual QA | DONE | Every screen at 1440 and 360 px, light and dark; 0 console errors on all routes; no horizontal scroll at 360. Fixes: CI label wrap, rule-card/grid min-width, badge wrap, forest-plot width, A2 display labels, title cap at 20 words (check_dist), annotator-name redaction (D-18), fixture-mode crash, proxy states as 200. |
| §14 quality bar | DONE | Caveats attached to every T2 +0.451 and T1 F1 / coverage view; F7 → RQ / 78 units / 13-field diff / caveat in ≤ 4 clicks; Showcase footnotes on every number; M2-only product badges. |
| Final checks | GREEN | tsc, eslint, vitest 79, vite build, check_dist PASS, test:py 7, repo pytest 1211, release_check PASS, build_tables --check, scan_documents 0 unsourced, check_paper --allow-placeholders PASS, Step 0 re-check OK. |
| Pitch site (D-23) | DONE | Public builds are pitch-only: 5 pages, persona chooser, plain-language findings with fine print, slim snapshot. Visual QA at 1440 and 360 px, light and dark; 0 console errors; no horizontal scroll. Deployed to Azure (5 routes 200; old workspace routes "Page not found") and republished the claude.ai copy (version 2, old assets removed). Checks: tsc, eslint, vitest 86, build, check_dist PASS (dist, dist-azure, dist-artifact), test:py 7, repo pytest 1211, release_check PASS, build_tables --check. |
