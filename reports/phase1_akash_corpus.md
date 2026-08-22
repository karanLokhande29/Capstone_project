# Phase 1 — Akash: Corpus Acquisition, Extraction, Segmentation

Run scope: **small validation slice, limit=12** (pipeline stage: `all`)

This is the Task 7 small validation slice — real network calls against the live RBI site, a strict subset of the eventual full corpus, produced so `phase1/meer-annotation` (P1-003) has real `ParagraphRecord`s to build its Week-2 checks against rather than waiting on the full harvest.

The full-corpus harvest (Task 8, Week 3) is a Kaggle-execution deliverable, not a local one — see `notebooks/phase1-akash-corpus.ipynb` §5 and Section U of the governing prompt ("The full-network, full-corpus run is not a local test — it is reported from the Kaggle execution"). Its metrics are **NOT YET MEASURED** here; they will be reported after that notebook runs.

## Discovery

- Documents discovered: **380**
- Downloads attempted: **12**
- Downloads successful: **12**
- Downloads failed: **0**
- Download success rate: **1.0**
- PDF count: **12**
- HTML count: **0**
- Distinct entity classes (raw, this run's downloaded slice): **4**
  - ['Banker and Debt Manager to Government', 'Banker to Governments and Banks', 'Commercial Banks', 'Consumer Education and Protection']

### Subject-family axis: not present on the source listing

`subject_family_raw` is `null` for every discovered document. The RBI Master Directions listing (`BS_ViewMasDirections.aspx`) groups documents only by an entity-class heading and, within that, a date sub-heading — there is no subject/topic column or heading level anywhere on the page (confirmed: no dropdown, no anchor, no distinguishing id on any heading row). This is a discovery finding, not a parsing gap: recording it faithfully as absent, rather than deriving a value from the title, avoids repeating the bug in this project's pre-Phase-0 history where title-based subject splitting truncated names like "Urban Co-operative Banks" to "Urban Co". Subject-family construction is left to `phase1/karan-matrix`, which can work from paragraph text.

### Duplicate entity-class heading blocks

A number of entity-class headings on the listing page (e.g. "Commercial Banks") appear more than once, as non-adjacent blocks with no distinguishing marker anywhere in the HTML — see the WARNING-level log line from `discover_documents` for the exact count and names on this run. `entity_class_raw` is recorded faithfully as the heading text either way, so this does not affect correctness of what's captured — but it means two documents sharing `entity_class_raw` may come from different, unlabelled listing passes. See `src/scraper/rbi_scraper.py` module docstring for the full investigation.

## Extraction

- Documents considered: **12**
- Extraction successful: **12**
- Extraction failures: **0**
- Extracted empty (parsed, no usable text): **0**
- Skipped (not downloaded): **0**
- Extraction success rate: **1.0**

## Segmentation

- Documents segmented: **12**
- Total paragraphs: **1456**
- section_id coverage: **0.9903846153846154**
- clause_path coverage: **0.9903846153846154**
- Documents with no recognised structure: **0**

## Cross-references

- Phrases detected: **33**
- Resolved (intra-document only): **8**
- Resolution rate: **0.24242424242424243**

Cross-document references (to other Directions, circulars, or the Banking Regulation Act) are detected as phrases but never resolved to a `paragraph_id` outside this scope — a low resolution rate is therefore expected and is not itself a defect; most legal cross-references in RBI text point outside the referencing document.

## Temporal signal (`update_date`)

- Documents carrying an "(Updated as on ...)" stamp in this run's manifest: **2 / 12** (0.167)
- Extracted verbatim from the title via `src.extraction.temporal_signals`; not parsed into a structured date, and not cross-checked against the listing's own per-block date sub-heading (see that module's docstring for why the two are not interchangeable).

## FAQ / enforcement supplementary sample

**NOT YET MEASURED.** `FAQView.aspx` (the FAQ index) was reachable, but is a category index requiring a second-level crawl into per-category pages to reach actual FAQ text — not "trivially reachable" in the sense Task 7 intends, and building that crawl would be the systematic harvester this prompt explicitly says not to build here. Left for Phase 2, Week 4 as scoped.
