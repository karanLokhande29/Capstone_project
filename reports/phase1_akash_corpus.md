# Phase 1 — Akash: Corpus Acquisition, Extraction, Segmentation

Run scope: **full corpus** (pipeline stage: `report-only`)

## Discovery

- Documents discovered: **381**
- Downloads attempted: **NOT YET MEASURED**
- Downloads successful: **NOT YET MEASURED**
- Downloads failed: **NOT YET MEASURED**
- Download success rate: **NOT YET MEASURED**
- PDF count: **NOT YET MEASURED**
- HTML count: **NOT YET MEASURED**
- Distinct entity classes (raw, this run's downloaded slice): **19**
  - ['All India Financial Institutions', 'Asset Reconstruction Companies', 'Banker and Debt Manager to Government', 'Banker to Governments and Banks', 'Commercial Banks', 'Consumer Education and Protection', 'Credit Information Companies', 'Financial Inclusion and Development', 'Financial Market', 'Foreign Exchange Management', 'Issuer of Currency', 'Local Area Banks', 'Non-Banking Financial Companies', 'Payment and Settlement System', 'Payments Banks', 'Regional Rural Banks', 'Rural Co-operative Banks', 'Small Finance Banks', 'Urban Co-operative Banks']

### Subject-family axis: not present on the source listing

`subject_family_raw` is `null` for every discovered document. The RBI Master Directions listing (`BS_ViewMasDirections.aspx`) groups documents only by an entity-class heading and, within that, a date sub-heading — there is no subject/topic column or heading level anywhere on the page (confirmed: no dropdown, no anchor, no distinguishing id on any heading row). This is a discovery finding, not a parsing gap: recording it faithfully as absent, rather than deriving a value from the title, avoids repeating the bug in this project's pre-Phase-0 history where title-based subject splitting truncated names like "Urban Co-operative Banks" to "Urban Co". Subject-family construction is left to `phase1/karan-matrix`, which can work from paragraph text.

### Duplicate entity-class heading blocks

A number of entity-class headings on the listing page (e.g. "Commercial Banks") appear more than once, as non-adjacent blocks with no distinguishing marker anywhere in the HTML — see the WARNING-level log line from `discover_documents` for the exact count and names on this run. `entity_class_raw` is recorded faithfully as the heading text either way, so this does not affect correctness of what's captured — but it means two documents sharing `entity_class_raw` may come from different, unlabelled listing passes. See `src/scraper/rbi_scraper.py` module docstring for the full investigation.

## Extraction

- Documents considered: **NOT YET MEASURED**
- Extraction successful: **NOT YET MEASURED**
- Extraction failures: **NOT YET MEASURED**
- Extracted empty (parsed, no usable text): **NOT YET MEASURED**
- Skipped (not downloaded): **NOT YET MEASURED**
- Extraction success rate: **NOT YET MEASURED**

## Segmentation

- Documents segmented: **NOT YET MEASURED**
- Total paragraphs: **NOT YET MEASURED**
- section_id coverage: **NOT YET MEASURED**
- clause_path coverage: **NOT YET MEASURED**
- Documents with no recognised structure: **NOT YET MEASURED**

## Cross-references

- Phrases detected: **NOT YET MEASURED**
- Resolved (intra-document only): **NOT YET MEASURED**
- Resolution rate: **NOT YET MEASURED**

Cross-document references (to other Directions, circulars, or the Banking Regulation Act) are detected as phrases but never resolved to a `paragraph_id` outside this scope — a low resolution rate is therefore expected and is not itself a defect; most legal cross-references in RBI text point outside the referencing document.

## Temporal signal (`update_date`)

- Documents carrying an "(Updated as on ...)" stamp in this run's manifest: **162 / 381** (0.425)
- Extracted verbatim from the title via `src.extraction.temporal_signals`; not parsed into a structured date, and not cross-checked against the listing's own per-block date sub-heading (see that module's docstring for why the two are not interchangeable).

## FAQ / enforcement supplementary sample

**NOT YET MEASURED.** `FAQView.aspx` (the FAQ index) was reachable, but is a category index requiring a second-level crawl into per-category pages to reach actual FAQ text — not "trivially reachable" in the sense Task 7 intends, and building that crawl would be the systematic harvester this prompt explicitly says not to build here. Left for Phase 2, Week 4 as scoped.


---

## Coverage by entity class

_Repaired by P1-004 (Karan, solo)._ A corpus-level download rate is not enough for RQ1: the first harvest's 81 failures were not spread evenly, they fell almost entirely on Commercial Banks and Small Finance Banks, which is exactly where a cross-class comparison needs coverage most.

| Entity class | Before | After | Rate |
|---|---|---|---|
| All India Financial Institutions | — | 23/23 | 100.0% |
| Asset Reconstruction Companies | — | 5/5 | 100.0% |
| Banker and Debt Manager to Government | — | 2/2 | 100.0% |
| Banker to Governments and Banks | — | 2/2 | 100.0% |
| Commercial Banks | — | 45/45 | 100.0% |
| Consumer Education and Protection | — | 7/7 | 100.0% |
| Credit Information Companies | — | 4/4 | 100.0% |
| Financial Inclusion and Development | — | 8/8 | 100.0% |
| Financial Market | — | 18/18 | 100.0% |
| Foreign Exchange Management | — | 20/20 | 100.0% |
| Issuer of Currency | — | 3/3 | 100.0% |
| Local Area Banks | — | 33/33 | 100.0% |
| Non-Banking Financial Companies | — | 44/44 | 100.0% |
| Payment and Settlement System | — | 9/9 | 100.0% |
| Payments Banks | — | 27/27 | 100.0% |
| Regional Rural Banks | — | 26/26 | 100.0% |
| Rural Co-operative Banks | — | 29/29 | 100.0% |
| Small Finance Banks | — | 40/40 | 100.0% |
| Urban Co-operative Banks | — | 36/36 | 100.0% |
| **Overall** | — | **381/381** | **100.0%** |
