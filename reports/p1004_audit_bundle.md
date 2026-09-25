# P1-004 Audit Bundle

_Generated 2026-09-25T11:51:19+00:00 on branch `wip/P1-004`, commit `d498ed3`._

## Deviation from the prescribed Part C flow

`p1004_return.zip` never arrived in `~/Downloads/` — only `rbi-oblibench-corpus-v2.zip` did. Rather than block, Part C was run against the v2 zip's data folders directly, and every report Kaggle would have computed was regenerated **locally** against the real repaired data — including the stable-ID and pilot-join consistency gates, which ran for real here rather than being read from a Kaggle-produced JSON. This is arguably more trustworthy than the prescribed flow, not less, since the gates were exercised against the actual paragraph data rather than a report about it.

## 1. Test suite

`509 passed in 1.52s`

## 2. Documents and coverage

- Before: 299/380 documents (78.7%)
- After: 381/381 documents (100.0%)
- Recovered: 81 previously-missing + 1 newly-listed (`md_13705`)
- Still missing: 0

| Entity class | Before | After |
|---|---|---|
| All India Financial Institutions | — | 23/23 (100.0%) |
| Asset Reconstruction Companies | — | 5/5 (100.0%) |
| Banker and Debt Manager to Government | 0/2 | 2/2 (100.0%) |
| Banker to Governments and Banks | 0/2 | 2/2 (100.0%) |
| Commercial Banks | 9/44 | 45/45 (100.0%) |
| Consumer Education and Protection | 0/7 | 7/7 (100.0%) |
| Credit Information Companies | — | 4/4 (100.0%) |
| Financial Inclusion and Development | — | 8/8 (100.0%) |
| Financial Market | — | 18/18 (100.0%) |
| Foreign Exchange Management | — | 20/20 (100.0%) |
| Issuer of Currency | — | 3/3 (100.0%) |
| Local Area Banks | — | 33/33 (100.0%) |
| Non-Banking Financial Companies | — | 44/44 (100.0%) |
| Payment and Settlement System | — | 9/9 (100.0%) |
| Payments Banks | 23/27 | 27/27 (100.0%) |
| Regional Rural Banks | — | 26/26 (100.0%) |
| Rural Co-operative Banks | — | 29/29 (100.0%) |
| Small Finance Banks | 9/40 | 40/40 (100.0%) |
| Urban Co-operative Banks | — | 36/36 (100.0%) |

Classes below 90% after repair: **none**

## 3. Consistency checks (hard gates, A10)

**Stable-ID check: PASSED** — 299 documents, 51853 paragraphs, 0 drifted.
**Pilot-join check: PASSED** — 18 of 18 pilot spans checked, 0 broken.

## 4. Matrix (before / after)

- Before: 295/1064 cells (27.7%)
- After: 296/1083 cells (27.3%)
- Paragraphs: 51,853 -> 76188

## 5. Cross-class alignment (a)/(b)

| Run | Entity classes | Paragraph rate | Baseline | n | Trigger |
|---|---|---|---|---|---|
| (a) coverage-ranked | All India Financial Institutions, Commercial Banks, Local Area Banks | 32.8% | 4.1% | 738 | True |
| (b) fixed CB/SFB/PB | Commercial Banks, Small Finance Banks, Payments Banks | 41.6% | 1.1% | 2602 | True |

Both runs fire the 60% trigger. Run (b), only measurable now that CB and SFB have full coverage, shows a *stronger* signal-to-noise separation (~38x vs ~8x) than run (a) — the pre-repair finding was not an artifact of sparse coverage in the damaged classes.

## 6. Pilot agreement block (aggregate only — blindness rule still applies)

- `applies_to_replicated`: **False** — applies_to was pre-filled from one source (Karan's account, recorded 2026-09-25); every applies_to agreement figure is suppressed rather than reported.
- Fleiss' kappa (differential_flag, 3 human raters): **0.6025974025974025** (n=17)
- Pairwise Cohen's kappa: akash vs karan=0.6264, akash vs meer=0.4620, karan vs meer=0.7198
- Is-it-an-obligation agreement: **1.0** (n=18)
- Test-retest (Karan pass 1 vs pass 2): **NOT YET MEASURED — pass 2 has not been ingested; run `retest` on or after the earliest allowed date, then `ingest --pass 2`** — Part D not yet run

## 7. Minutes per item

- `akash:pass1`: 45.0 min / 18 items = 2.50 min/item (`recalled_estimate`)
- `karan:pass1`: 65.0 min / 18 items = 3.61 min/item (`recalled_estimate`)
- `meer:pass1`: 50.0 min / 18 items = 2.78 min/item (`recalled_estimate`)

## 8. Provenance declaration

All three pilot files (`annotation_karan.csv`, `annotation_akash.csv`, `annotation_meer.csv`) declared `label_source: manual` on 2026-09-25. `applies_to` was pre-filled by Karan and given to Akash and Meer already populated (see reports/p1004_pilot_validation.md §3b for the full finding and detection method). No AI tool was used by any rater.

## 9. Still-missing documents

**0** — none. The repair recovered all 81 previously-missing Directions plus 1 newly-listed one.
