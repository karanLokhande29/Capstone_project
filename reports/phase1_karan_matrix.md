# Phase 1 — Karan: Metadata Normalization + Subject x Entity-Class Matrix

---

## FINDING (2026-08-23): `subject_family_raw` is absent from the entire corpus

**This should have been reported before any workaround was built on top of it. It was not — it is recorded here retroactively, stated as it should have been stated at the moment of discovery.**

`DocumentRecord.subject_family_raw` is **null for all 380 harvested documents**. Investigation during P1-002 established why, and the cause is a property of the source, not a defect in `phase1/akash-scraper`'s extraction:

- The RBI Master Directions listing (`BS_ViewMasDirections.aspx`) groups documents under an entity-class heading and a date sub-heading only. There is no subject/topic column, no dropdown, no anchor, and no distinguishing id on any heading row.
- The document text itself carries no `Subject:`-style field either (sampled across extracted documents; zero hits).

**In short: RBI's Master Directions listing does not publish a subject-family taxonomy at discovery time.** One of the two axes of the Subject x Entity-Class Matrix — the project's primary structural artifact — has no harvested source.

Per P1-002 Section AB, this was a stop-and-report condition ("P1-001's committed data turns out to be missing a field this step needs — do not patch around a gap in Akash's output, report it"). P1-002 instead proceeded directly to a title-derivation workaround. The derivation itself is sound and validated (see below and `src/metadata/vocabulary_discovery.py`), and is **not** being redone — but it should have been a reported decision, not an assumed one.

### Consequence for downstream consumers

Every `subject_family` value in this corpus is **inferred**, not harvested. It is now marked as such in the data itself (see "Provenance marking" below), so no consumer needs to read a docstring to discover this. Anyone stratifying, sampling, or reporting on subject families — starting with `phase1/meer-annotation` (P1-003) — should treat that axis as project-inferred metadata, and should not describe it as RBI's own classification.

---

## Vocabulary discovery

- Documents scanned: **380**
- Entity classes discovered: **19** (dossier estimate: ~11 — reported as a finding, not corrected toward it)
- Subject families discovered: **56** (dossier estimate: ~26 — reported as a finding, not corrected toward it)
- Entity-class unresolved documents: **0**
- Subject-family unresolved documents: **76**

## Provenance marking (queryable from the data, not just this report)

Each `VocabularyTerm.source` now carries a machine-readable prefix, so harvested and inferred terms are mechanically separable:

| Axis | raw | derived | mixed |
|---|---|---|---|
| `entity_class` | **19** | 0 | 0 |
| `subject_family` | 0 | **56** | 0 |

- `raw:rbi_listing_entity_class_heading` — harvested from a real field, then normalised.
- `derived:title_strip_entity_class` — inferred from the title; no raw source exists.

Queryable three ways, none of which require reading code:

```bash
grep '"source": "derived:' data/metadata/subject_families.json   # every inferred term
cat data/metadata/vocabulary_provenance.json                       # canonical_name -> provenance
grep 'DERIVED axis present' data/matrix/matrix_v1.jsonl            # cells resting on inferred axes
```

`MatrixCell.notes` records the provenance of both of a cell's axes, so the matrix is auditable standalone without joining back to the vocabulary files.

### Schema question (P1-002-CORRECTIVE Task 3): answer — **no schema change required**

*Question:* does a derived `subject_family` belong in the existing field once marked, or does honest representation require a new `subject_family_source: Literal["raw","derived"]` on `DocumentRecord`/`ParagraphRecord`?

*Answer:* **the existing field is sufficient for this corpus, and no base-branch schema change is requested.** The reasoning, and the condition that would reverse it, both matter:

1. **The join is total and verified.** Every one of the 56 distinct `subject_family` values appearing on a record resolves to exactly one `VocabularyTerm` — 56 values, 56 terms, **zero orphans**, checked programmatically. Provenance is therefore fully recoverable from the committed data for every record, with no information loss.
2. **No term has mixed provenance.** Because `subject_family_raw` is null corpus-wide, all 56 subject-family terms are 100% derived and all 19 entity-class terms are 100% raw. The split is clean per axis, so a per-record field would carry exactly one value per axis and duplicate what the vocabulary already states. (P1-002-CORRECTIVE Section R's mixed-provenance stop condition does **not** trigger; a test asserts this and will fail loudly if it ever changes.)
3. **`VocabularyTerm.source` is Phase 0's designated field for exactly this** — its own `FIELD_SPECS` description reads "Makes the vocabulary auditable rather than asserted." Using it as designed is preferable to widening two already-large record schemas (`ParagraphRecord` is at 22 fields) and to denormalising provenance into a second place that can drift out of sync with the first.

**The honest counter-argument, and the trigger to revisit:** a JSONL row is often consumed standalone, and requiring a join is a real (if small) cost — which is why `vocabulary_provenance.json` is emitted as a one-lookup artifact rather than making consumers parse the full vocabulary. **If a future corpus ever yields a `subject_family` value reachable from both a raw field and a derivation, the join stops being unambiguous and the per-record field becomes genuinely necessary.** At that point this answer should flip, and the proposed field would be:

> `subject_family_source: str | None` on `DocumentRecord` and `ParagraphRecord`, values `"raw" | "derived" | "mixed"`, owner `phase1/karan-matrix`, requiring a base-branch change agreed by all three owners.

That request is **not** being raised now, because the condition justifying it does not hold for this corpus.

## Segmented unresolved rate (P1-002-CORRECTIVE Task 4)

P1-002 reported a single combined figure (76/380, 20%). That number conflates two different things; split by origin:

| Measure | Value |
|---|---|
| `entity_class` unresolved rate (**raw-sourced**) | **0.0** (0/380) |
| `subject_family` unresolved rate (combined) | **0.2** (76/380) |
| `subject_family` unresolved rate (**raw-sourced only**) | **NOT MEASURABLE — no raw-sourced subject_family values exist in this corpus** |
| Documents with a derived `subject_family` | 380 / 380 |

**Reading this:** the raw-sourced subject-family rate is reported as `NOT MEASURABLE`, not `0.0` — there are no raw subject-family values in this corpus, so reporting 0% would falsely imply raw values were examined and found clean. The distinction is the whole point of the split.

**What it means:** the entire 20% unresolved rate is attributable to the *reach of the derivation method*, not to normalisation difficulty. On the one axis that does have a harvested source (`entity_class`), the unresolved rate is **0%** — normalisation of genuinely-harvested data in this corpus is clean. The 76 unresolved documents are overwhelmingly cases where the title names a different entity class than the filing category (the "Internal Ombudsman" directions), which is a limitation of inferring from titles, not a taxonomy problem.

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
