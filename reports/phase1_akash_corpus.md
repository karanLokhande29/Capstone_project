# Phase 1 — Akash: Corpus Acquisition, Extraction, Segmentation

Run scope: **full corpus** (pipeline stage: `all`)

## Discovery

- Documents discovered: **380**
- Downloads attempted: **380**
- Downloads successful: **299**
- Downloads failed: **81**
- Download success rate: **0.7868421052631579**
- PDF count: **299**
- HTML count: **0**
- Distinct entity classes (raw, this run's downloaded slice): **19**
  - ['All India Financial Institutions', 'Asset Reconstruction Companies', 'Banker and Debt Manager to Government', 'Banker to Governments and Banks', 'Commercial Banks', 'Consumer Education and Protection', 'Credit Information Companies', 'Financial Inclusion and Development', 'Financial Market', 'Foreign Exchange Management', 'Issuer of Currency', 'Local Area Banks', 'Non-Banking Financial Companies', 'Payment and Settlement System', 'Payments Banks', 'Regional Rural Banks', 'Rural Co-operative Banks', 'Small Finance Banks', 'Urban Co-operative Banks']

### Subject-family axis: not present on the source listing

`subject_family_raw` is `null` for every discovered document. The RBI Master Directions listing (`BS_ViewMasDirections.aspx`) groups documents only by an entity-class heading and, within that, a date sub-heading — there is no subject/topic column or heading level anywhere on the page (confirmed: no dropdown, no anchor, no distinguishing id on any heading row). This is a discovery finding, not a parsing gap: recording it faithfully as absent, rather than deriving a value from the title, avoids repeating the bug in this project's pre-Phase-0 history where title-based subject splitting truncated names like "Urban Co-operative Banks" to "Urban Co". Subject-family construction is left to `phase1/karan-matrix`, which can work from paragraph text.

### Duplicate entity-class heading blocks

A number of entity-class headings on the listing page (e.g. "Commercial Banks") appear more than once, as non-adjacent blocks with no distinguishing marker anywhere in the HTML — see the WARNING-level log line from `discover_documents` for the exact count and names on this run. `entity_class_raw` is recorded faithfully as the heading text either way, so this does not affect correctness of what's captured — but it means two documents sharing `entity_class_raw` may come from different, unlabelled listing passes. See `src/scraper/rbi_scraper.py` module docstring for the full investigation.

## Extraction

- Documents considered: **299**
- Extraction successful: **299**
- Extraction failures: **0**
- Extracted empty (parsed, no usable text): **0**
- Skipped (not downloaded): **81**
- Extraction success rate: **1.0**

## Segmentation

- Documents segmented: **299**
- Total paragraphs: **51853**
- section_id coverage: **0.9934430023335198**
- clause_path coverage: **0.9934430023335198**
- Documents with no recognised structure: **0**

## Cross-references

- Phrases detected: **2254**
- Resolved (intra-document only): **438**
- Resolution rate: **0.19432120674356698**

Cross-document references (to other Directions, circulars, or the Banking Regulation Act) are detected as phrases but never resolved to a `paragraph_id` outside this scope — a low resolution rate is therefore expected and is not itself a defect; most legal cross-references in RBI text point outside the referencing document.

## Temporal signal (`update_date`)

- Documents carrying an "(Updated as on ...)" stamp in this run's manifest: **162 / 380** (0.426)
- Extracted verbatim from the title via `src.extraction.temporal_signals`; not parsed into a structured date, and not cross-checked against the listing's own per-block date sub-heading (see that module's docstring for why the two are not interchangeable).

## FAQ / enforcement supplementary sample

**NOT YET MEASURED.** `FAQView.aspx` (the FAQ index) was reachable, but is a category index requiring a second-level crawl into per-category pages to reach actual FAQ text — not "trivially reachable" in the sense Task 7 intends, and building that crawl would be the systematic harvester this prompt explicitly says not to build here. Left for Phase 2, Week 4 as scoped.
