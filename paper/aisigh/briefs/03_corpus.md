# Brief: Corpus and benchmark construction

Word budget: **250 words** (6-page) / 400 (8-page, paid). Prose is written by the authors.

**Claims:**
- Harvest of RBI Master Directions; paragraph segmentation; the entity-class vocabulary mixes **11** (`R:01_corpus.core_entity_classes`) regulated classes and **8** (`R:01_corpus.function_headings`) RBI function headings (D8).
- Candidate obligations by deontic cues: **28,694** (`R:02_candidates.candidates_kept`) kept.
- Cross-class matching (P2-002, bge-base + lexical, thresholded).
- T1 sample of **123** (`R:05_t1_benchmark.sample`) items, seeded and stratified; at most 4 compared classes per item.

**Floats:** Table `tab:benchmark`; Fig. `fig:construction` (single column).

**Disclosures:**
- D1 (81 Directions recovered in P1-004; all P2 work on the full set);
- D2 (3 empty-title Directions);
- subject families are derived from titles.

