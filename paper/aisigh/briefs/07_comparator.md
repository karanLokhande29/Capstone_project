# Brief: Targeted experiment: structured comparator

Word budget: **220 words** (6-page) / 350 (8-page, paid). Prose is written by the authors.

**Claims:**
- Motivation: **56** (`EA:a_different_missed.missed_by_every_llm_system`) of **78** (`EA:a_different_missed.gold_different_units`) gold `different` units are missed by every LLM system (all five answered; 58/78 counting answered systems only). In the dry run, 27 of 58 were reasoning failures for every system that erred (the gold paragraph was in context).
- Method:
  - the LLM extracts 13 fields per side and compares them field by field;
  - a fixed rule decides (same > different > none);
  - frozen before any T1 run (amendment 3; sha256 system `51f7ea78…`, rule `83664f8d…`).
- Development set: the separate 30-item set (disclosed), with one revision for a field-extraction bug.
  - dev macro-F1 0.635, `different` F1 0.348 (development evidence only).
- Result on the 106-item gold: {{cmp-diffF1}}, {{cmp vs class-aware paired}}.

**Disclosures:** dev on the separate set; one revision and its reason; sealed predictions (manifest sha256).

