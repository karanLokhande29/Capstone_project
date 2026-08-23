# Phase 1 — Karan: Metadata Normalization + Subject x Entity-Class Matrix

## Vocabulary discovery

- Documents scanned: **380**
- Entity classes discovered: **19** (dossier estimate: ~11 — reported as a finding, not corrected toward it)
- Subject families discovered: **56** (dossier estimate: ~26 — reported as a finding, not corrected toward it)
- Entity-class unresolved documents: **0**
- Subject-family unresolved documents: **76**

### Entity-class vocabulary: direct 1:1 construction

`entity_class_raw` values are already clean, mutually distinct strings scraped directly from the RBI listing's category headings — verified against the full corpus (zero normalised-key collisions). Each raw value becomes its own canonical term; no alias resolution was needed for this corpus.

### Subject-family vocabulary: title-residual extraction

`subject_family_raw` is null for all discovered documents — the RBI listing has no subject/topic column (established during `phase1/akash-scraper`). Subject families are derived mechanically: the already-known `entity_class_raw` string is matched and removed from `DocumentRecord.title` on a word boundary, and RBI/Directions/date boilerplate is stripped from what remains. This is string matching on two already-discovered fields, not semantic topic modelling or invented classification — see `src/metadata/vocabulary_discovery.py` module docstring for the full methodology and the real-corpus bugs found and fixed while validating it (a dangling-bracket residual, and a singular/plural substring collision on "Financial Market"/"Financial Markets").

Documents where the entity-class substring cannot be found in the title at all (e.g. the "Internal Ombudsman" directions, filed under `entity_class_raw` "Consumer Education and Protection" while their titles name the entity class the rule actually applies to) are recorded as unresolved, never force-matched — see `data/metadata/subject_family_unresolved.json` for the full list with reasons.

## Normalization

- Documents normalised: **380**
- Entity-class extraction coverage: **1.0**
- Subject-family extraction coverage: **0.8**
- Documents with paragraphs normalised: **299**
- Documents missing paragraphs (not downloaded/extracted by Akash's run): **81**
- Total paragraphs normalised: **51853**
- `*_raw` fields verified unchanged: **True** (checked programmatically for every document, not spot-checked)

## Subject x Entity-Class Matrix

- Total cells (entity classes x subject families): **1064**
- Populated cells: **295**
- Missing cells: **769**
- Ambiguous cells: **9**
- Duplicate-mapping cells (>1 source Direction): **9**
- Matrix coverage (populated / total): **0.27725563909774437**

### On the ambiguous cells

Every ambiguous cell found on the real corpus is a genuine "Miscellaneous" vs "Miscellaneous Supervisory" pairing: RBI issued both a general Miscellaneous Directions and a separate Miscellaneous Supervisory Directions for the same entity class, and this module's extraction only captures what sits inside the title's brackets — the "Supervisory" qualifier sits outside them, so both titles reduce to the same "Miscellaneous" subject residual. This is a real granularity limit of title-residual extraction, correctly surfaced as `ambiguous=True` with `ambiguity_reason='multiple_candidate_directions'` rather than silently merged or arbitrarily picked — exactly what the ambiguous flag exists to catch.
