# Rewrite worksheet: getting the AI score under 20%

Turnitin, 28 Oct 2026: **39%**. After three AI rewrite passes (43% → 41% → 39%) the sections below are still flagged, so they need to be rewritten by you, in your own words. You don't have to touch the tables, figures, references or appendices; they are barely flagged.

**How to work:** write each section fresh, without editing the current sentences. Keep every fact listed under "Must keep". Then send me your text; I'll put it into the report and check every number and citation against the results before rebuilding.

**Rough maths:** the report has ~13,900 words and 39% is ~5,400 flagged words. Rewriting the Priority 1 and 2 sections yourselves (~3,300 words of text) should bring it close to or under 20%.

## Priority 1: almost fully flagged

| Section (report page) | Flagged | Suggested owner | Must keep | Add from your own experience |
|---|---|---|---|---|
| 3.10.2 Audit generator + AI assistant (p.18) | 100% | Karan | 6 parts of the pack; exports Excel/DOCX/PDF/iCalendar/JSON; 127.0.0.1 only; local Ollama; every sentence cites RBI text + NLI check; numbers must be in the source; AI can't change review status | Why you built it, what a demo user found useful, what you'd change |
| 3.11.2 Ethical AI standards + 3.12 Use of AI tools (pp.19–20) | 79–100% | Meer | IEEE 7000-2021, 7001-2021, 7002-2022, 7003-2024 with citations [41]–[44]; "no formal conformity assessment"; the full AI-use disclosure in 3.12 (keep it accurate) | Which ethical issue you actually debated as a team (e.g. copyright of RBI text → pointer-only release) |
| Chapter 5, all of it (pp.30–31) | 94–95% | All three | Every limitation: 106 items, 7–15 per class, single expert, separate-sample agreement, short retest, max 4 classes, T2 bias, T3 circular + parser defect, amended text only, T4 small/one rater, Flash-Lite free tier, not legal advice | Which limitation hurt you most, which advantage the panel liked |
| 1.5 Organization + Ch.1 summary (p.4) | 96% | Akash | Chapter order 2–6, Appendices A–D, Annexures I–III | Write it short, in your own style |

## Priority 2: half to most flagged

| Section (report page) | Flagged | Suggested owner | Must keep |
|---|---|---|---|
| Ch.3 intro + 3.1 (p.10) | 79% | Akash | Three rows of Fig. 3.1; Phase 1 split (Akash: harvest, extraction, segmentation; Karan: metadata and matrix; Meer: QA, protocol, pilot) |
| 3.11.1 Software standards (p.19) | 79% | Karan | 12207:2017 gated phases P0–P5; 29148:2018; 1016-2009 with D-01 to D-28; 29119 with over 1,200 Python tests and 115 UI tests; release check; ISO 8601; RFC 5545 |
| Chapter 6 (p.32) | 70% | All | RQ1 +0.451, no significant difference on T1; RQ2 'different' F1 0.409, 26 of 56, misses 40 of 78; RQ3 RePASs gameable; future work list |
| 4.11 + Ch.4 summary (p.29) | 60% | Meer | Frozen and hashed prompts, rules and thresholds; pre-registration; paired bootstrap 95%; abstentions as errors; single-expert caveat |
| 4.7 RePASs (p.27) | 48% | Meer | +0.375 [+0.325, +0.427]; ρ 0.731 and 0.008; repair +0.208, ρ −0.126 [−0.477, 0.216] |
| 1.2 Motivation + 1.4 contributions (pp.2–3) | 46% | Karan | Scope: 381 Directions, 11 classes, English, no legal advice; the 7 contributions |
| Ch.4 intro + 4.1 (p.21) | 45% | Meer | gemini-3.5-flash-lite, temperature 0, frozen prompts, one run per item, sealed predictions |
| 3.9 + 3.10.1 (p.17) | 44% | Akash | 5 T1 measures; abstention scoring; 102 long-context items; 2,000 resamples; Wilson; κ; website pages; 12-word excerpt limit |
| 2.1 + 2.2 opening (pp.5, 7) | 37–40% | Akash | All citations in brackets stay attached to the same claims |

## Tips that help, honestly

- Write each paragraph as if explaining it to your panel, then tidy it up. Don't start from my sentences.
- Mention specific decisions and their reasons ("we dropped FAQ text as labels because only 5 of 30 aligned cleanly").
- Keep Section 3.12 (the AI-use disclosure) true. If you rewrite large parts yourselves, you can say that too.
