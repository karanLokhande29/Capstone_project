# Table 11. LLM usage

| Phase | Model id | Calls | Note |
|---|---|---|---|
| P3-001 smoke test (2026-09-27) | gemini-3.8-flash | 1 | gemini, status OK |
| P3-001 smoke test (2026-09-27) | openai/gpt-oss-120b | 1 | groq, status OK |
| P3-002 question drafting, discarded | gemini-3.8-flash | 7 | Gemini free-tier daily quota ran out; these questions were discarded, never mixed |
| P3-002 question drafting | openai/gpt-oss-120b | 30 | Groq, whole step rerun on the fallback |
| P3-002 genuine answers | openai/gpt-oss-120b | 30 | Groq, whole step on the fallback |
| P4 (all systems), quota day 2026-09-27 (Pacific) | gemini-3.5-flash-lite | 317 | Gemini; soft cap 480 |
| P4 (all systems), quota day 2026-09-28 (Pacific) | gemini-3.5-flash-lite | 480 | Gemini; soft cap 480 |

P1–P2 made no LLM calls. RePASs and the P4 verifier use local NLI models (NOTICE.md), not hosted LLMs.

P4 model: `gemini-3.5-flash-lite` (version `3.5-flash-lite-07-2026`), thinking {'thinkingLevel': 'minimal'}, temperature 0, no provider fallback. Outage: HTTP 503 on every call from 2026-09-28 20:09:51 IST until 2026-09-28 22:19:25 IST; intermittent 503s until 2026-09-29 01:59:44 IST.

- **D10.** The note-2 fallback was triggered EARLY: the long-context baseline is rerun on all 106 items at one uniform 100K cap (same proportional per-class truncation) without first finishing the 150K remainder run and retry pass. The decision was based ONLY on the failure-size evidence: never-answered prompts had a median of about 150K tokens (14 items, range 60K–150K) against about 71K for the 47 scored items (range 6K–132K). Disclosure: long-context scores on those 47 scored items had already been computed and displayed in Claude's session (3-way flag F1 0.515 [0.374, 0.626] against final agentic 0.518 on the same items) before Claude recommended the rerun; Claude's recommendation cited only the size evidence, and Karan decided on that evidence. The 150K run's items are kept only as a record, never reported as the baseline. Items under 100K reuse the cache (identical prompt). Pre-committed next step: if more than 20% of items still fail at 100K after one retry pass, one step down to a uniform 64K cap for all items; if failures remain after that, long-context is reported only on the scored items with the size distribution and every system compared on exactly those items; no further cap changes. A health probe and a 3-consecutive-failure circuit breaker stop provider outages from spending quota.
- **D11.** Claude stopped the 150K remainder step on the 3-hour compute rule using wall-clock time (4 h). Measured as actual run time (Mac awake, from the power log), that step ran about 62 minutes (6 + 55 min), so the rule was not reached. Run times in this report are active time (macOS monotonic clock, which stops while the Mac sleeps); wall time is shown alongside.
- **D12.** Before the outage cutoff, the 37 long-context items whose 100K prompt is byte-identical to a cached 150K prompt were scored from the cache (cache-only mode: no API call, no ledger entry); their outputs are identical to the 150K run. Gemini then recovered overnight and the chain completed the 100K pass and one retry pass: 102 of 106 items answered, 4 still failing (4%, below the 20% step-down threshold, so no 64K rerun). The demo transcripts ran on Gemini; the Groq demo fallback was never used.
