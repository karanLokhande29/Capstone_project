# Demo runbook

The site: **https://rbioblibench5qbvp2.z29.web.core.windows.net/** (Azure Storage static website).
Presenter mode: `/present`. It is not in the navigation.

The demo has one job, and every page says it:

> This is not a chatbot over RBI documents. It is a benchmark and inspection environment for finding, explaining and stress-testing differences between regulatory obligations.

## 1. Before you present (5 minutes)

| What | How |
|---|---|
| Public site only (no live model) | Open `/present` on the public URL. The preflight shows sealed data ✓ and the API as not configured. Live steps are hidden, and nothing is labelled Live. |
| Local presenter (full RBI text, freshness check) | `cd ui && npm run present:local`. This starts the comparator API in presenter mode (port 5190) and opens `/present`. |
| Local presenter with a live model | `export ASSISTANT_GEMINI_API_KEY=…` (a key **dedicated to the demo**, never the experiments' `GEMINI_API_KEY`), then `npm run present:local`. The preflight runs the live step once; that run becomes the cached replay for the hero case. |
| Rebuild everything | `cd ui && npm run api:bundle && npm run build` (runs the data build and all §C3 assertions). |

**Preflight checklist (green before you press Start):**
- **Sealed data loads.** Without it nothing works; rebuild with `npm run build`.
- **Prompt and rule hashes verified.** If red, **stop**: a frozen file changed. See `ui/AUDIT.md`, hard stop 1.
- **Live model reachable.** Optional; skipped without a key.
- **Replay recorded for the live step.** Optional. Without it (and without a live model) the live step is hidden.

`MOCK_LLM=sealed npm run api` starts a *test double* for checking the UI. Its runs are labelled "Test double (mock model, not live)" and are never stored as replays. Never present with it.

## 2. Keys in presenter mode

| Key | Action |
|---|---|
| → / ← | next / previous step |
| R | restart at step 1 |
| L | toggle live / cached replay for the live step |
| B | big text on/off |
| F | fullscreen |

## 3. If the live step fails

- Press **L** to switch to the cached replay. On screen it shows the **Cached replay** badge with its recording time; say so out loud.
- If neither a model nor a replay is available, the step is not in the script at all. Skip to Triage.
- A network drop mid-stream shows "The live run did not complete" with a button for the cached replay. Nothing partial is shown as a result.
- "Too many live runs" (429) means the rate limit (6 per minute per address). Use the replay.

## 4. The 3-minute script

| # | Step | Say (≈) | Show |
|---|---|---|---|
| 1 | **Guess** (0:00–0:30) | "Two RBI rules on asset-liability returns: one for NBFCs, one for rural co-operative banks. Same requirement or not?" Take a show of hands. | Hero round; the audience picks. |
| 2 | **Reveal** (0:30–0:50) | "The expert says different: monthly versus quarterly, and different deadlines. All five AI systems missed it. The structured comparator caught it." | Expert, five systems, comparator, decisive fields. |
| 3 | **Microscope** (0:50–1:20) | "The model only extracts 13 fields. A fixed rule, frozen by hash before any test, decides. Here is the trace: frequency differs, deadline differs, so DIFFERENT." | 13 rows and the decision trace. |
| 4 | **Live re-run** (1:20–1:50, if shown) | "Same frozen prompt, run now, next to the sealed output." If they differ: "Live ≠ sealed. Both are shown; the benchmark result is the sealed one." | Sealed vs live (or replay, with its badge). |
| 5 | **Edit** (if shown) | "Change one value and run again, but only after a control run reproduces the sealed output." | The edit lab (presenter only). |
| 6 | **Triage** (1:50–2:20) | "At the frozen High threshold the system handles 39% of comparisons and is right 96% of the time. 'Different' answers never clear it: a flag is a reason to look." Observed trade-off, not a recommendation. | The slider at High. |
| 7 | **Failure Map** (2:20–2:40) | "It wasn't one case: 56 real differences no LLM system caught; the comparator recovered 26. In 75% of LLM errors the right paragraph was already in context." | The map. |
| 8 | **Close** (2:40–3:00) | "And the popular metric would have rewarded copying: 0.746 for pasted evidence vs 0.371 for a genuine answer." | Close. |

## 5. Honesty reminders on stage

- The comparator also raises **70 false alarms**; when it flags a difference the expert agreed 38 of 108 times.
- The comparator was evaluated on the **two candidates the expert saw**, not on retrieved evidence.
- Confidence, triage and the actor sensitivity analysis are **post-paper**.
- One expert labelled the gold; three-rater agreement (κ 0.774) was measured on a separate 30-item set.
