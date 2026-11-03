# Brief: AI-use statement and acknowledgements (for the authors to word)

Word budget: **80 words** (6-page) / 120 (8-page, paid). Prose is written by the authors.

**Where AI tools were used (factual list; the authors word it):**
- **Code generation:** Claude Code (Anthropic) wrote the repository code (scraper, preprocessing, candidate extraction, matching, benchmark tooling, ingest/freeze tools, evaluation and statistics scripts) under the authors' direction.
- **Analysis scripts:** Claude Code wrote and ran the analysis and bootstrap scripts; the authors reviewed the outputs.
- **Internal reports:** Claude Code drafted the internal phase reports, the methods/limitations briefs and the report_corrections file.
- **LLM systems under study (system outputs, not labels):**
  - gemini-3.5-flash-lite (P4 systems, long-context, structured comparator);
  - Groq openai/gpt-oss-120b (T4 question drafting and genuine answers, P3).
- **Provider terms (disclosure):** Gemini API (free tier) terms: outputs may be published, and they were not used to train any model; free-tier inputs may be used by Google, including human review. The prompts contained only public RBI text and no personal data. Groq (gpt-oss-120b) terms: https://groq.com/terms-of-use.
- **Not AI:** every human label (T1, T3 spot-checks, T4 faithfulness) is manual. One early team-review file set was revised after AI-reviewer file-level feedback; it was recorded as not independent and never used for agreement.
- **The paper text:** written by the authors (the venue requires AI-generated content < 20% at camera-ready).
- **Authors:** Karan Lokhande, Akash Goyal, Meer Magia (order confirmed 2 Oct). The second raters are co-authors, so there is no acknowledgement line for them. The paper must **not** map authors to rater ids (release rule).

