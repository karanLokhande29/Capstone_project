# RBI-ObliBench — dataset card

Version 1.0. Annotations and derived metadata for evaluating retrieval and QA systems on Reserve Bank of India (RBI) Master Directions. **This release contains no RBI text.** Every item points into the corpus (Direction id, paragraph id, character offsets, source URL, harvest date, sha256 of the paragraph text); `scripts/rehydrate.py` (or `release/rehydrate.py`) rebuilds the text from RBI's own URLs and checks it against the hashes.

## Corpus

- 381 Master Directions from RBI's listing, 76,188 paragraphs, harvested 2026-08-22 to 2026-09-25 (`data/documents.jsonl`, `data/paragraphs.jsonl`).
- 19 entity-class headings: 11 regulated-entity classes and 8 RBI function headings. 57 subject families, derived from titles; 305 Directions have one.
- **Drift warning:** RBI updates consolidated Directions in place ("Updated as on …"). A rehydrated paragraph can differ from the harvested one; `rehydrate.py` reports it as `drifted` rather than silently using it.

## Tasks and files

| Task | File(s) | Rows | What an item is |
|---|---|---|---|
| T1 candidates | `data/t1/candidates_part1.jsonl`, `candidates_part2.jsonl` | 25,582 | an automatically extracted obligation span with P2-002 cross-class candidate labels (`label_status: candidate`) |
| T1 validated | `data/t1/validated.jsonl` | 106 | a human-validated obligation: per-class judgement (`same` / `different` / `none`), matched counterpart, `applies_to`, differential flag |
| T2 `t2_xclass_t1` | `data/t2/t2_xclass_t1.jsonl` | 412 | a query (pointer) with a target class and graded relevant paragraphs |
| T2 `t2_xclass_p2002` | `data/t2/t2_xclass_p2002.jsonl` | 53 | a query (pointer) with a target class and graded relevant paragraphs |
| T2 `t2_supp_p2003` | `data/t2/t2_supp_p2003.jsonl` | 25 | a query (pointer) with a target class and graded relevant paragraphs |
| T3 | `data/t3/items.jsonl`, `data/t3/dropped.jsonl` | 52 + 8 dropped | a (paragraph, as-of date) with gold status and governing instrument; dropped items carry the reason |
| T4 | `data/t4/questions.jsonl`, `answers_*.jsonl`, `scores.jsonl` | 30 questions, 120 scored answers | a question with four answer types, RePASs scores and (30 answers) human ratings |
| Matrix | `data/matrix/matrix_v1.jsonl`, `matrix_v1_summary.json` | 1,083 | one entity class × subject family cell |

**Splits.** Evaluation-only; there is no training split. T4 has 28 primary questions (the rater flagged 2 as bad) and 30 in the sensitivity analysis. T3 has 52 scored items; 8 were dropped after the second parse spot-check.

### Pointer fields (every task)

`md_id`, `paragraph_id`, `source_url`, `harvest_date`, `paragraph_sha256`; for spans `units` (character offsets `[start, end)` into the paragraph text), `rule` and `text_sha256`. Rebuild rules (`src/release/rebuild.py`):

- `span_text`: `" … ".join` of the whitespace-collapsed character ranges (T1 spans, T2 `t2_xclass_t1` queries);
- `raw_slice`: the raw character range (T2 `t2_xclass_p2002` queries);
- `spans_text`: `" ".join` of whitespace-collapsed sentence ranges (T4 concatenated and off-topic answers);
- `negate(concatenated)`: flip shall/must/required polarity and double every number (T4 negated answers, `src/t4/audit.py`).

The 25 `t2_supp_p2003` query texts come from RBI FAQ pages and press releases, not from the corpus; they carry the source URL and sha256 but are **not** rebuilt automatically (the parser is in `src/supplementary/`). T4 genuine answers are LLM outputs and are included as text; one answer (T4Q25) quoted 32 consecutive corpus words and is cut to 25 words plus "[…]" (recorded in `redactions`; `text_sha256` is of the answer as scored).

### Subject × Entity-Class Matrix (`data/matrix/matrix_v1.jsonl`)

Derived metadata only. One row per (entity class, subject family) cell:

| Field | Type | Meaning |
|---|---|---|
| `entity_class`, `entity_class_term_id` | string | entity-class heading from RBI's listing and its vocabulary id (`data/metadata/entity_classes.json`) |
| `subject_family`, `subject_family_term_id` | string | subject family derived from Direction titles and its id (`data/metadata/subject_families.json`) |
| `populated` | bool | at least one Direction exists for the cell |
| `source_directions` | list of `md_id` | the Directions in the cell |
| `n_documents` | int | number of Directions in the cell |
| `ambiguous`, `ambiguity_reason` | bool, string | the title-to-family mapping was ambiguous, and why |
| `notes` | string | provenance of each axis (raw vs derived) |

Summary (`matrix_v1_summary.json`): 1083 cells, 296 populated, 9 ambiguous, 9 with duplicate mappings.

## Label sources and provenance

- T1: 106 validated of 123 sampled (17 rejected as not an obligation). Every label is manual. Routes: `adjudicated` 38, `retest-consistent` 6, `single-pass` 62 (field `provenance`).
- T2: relevance comes from the T1 labels (`t2_xclass_t1`), the P2-002 validation pairs (`t2_xclass_p2002`) and the P2-003 hand alignment (`t2_supp_p2003`); all manual.
- T3: gold is computed by a deterministic amendment parser; humans spot-checked the parses (15/20 = 0.750 (Wilson 95% [0.531, 0.888]) for rules v1; 8/10 = 0.800 (Wilson 95% [0.490, 0.943]) independent post-fix).
- T4: questions and genuine answers are LLM outputs (Groq `openai/gpt-oss-120b`); the other answer types are rule-built. The human ratings are manual, blind, by one rater.
- Raters are pseudonymised as `rater_1` (primary annotator), `rater_2` and `rater_3` (second raters). The release has no names and no per-person minutes. No AI tool was used for any label.

## Reliability

Single-expert annotations with second-rater κ = 0.774 (class-row judgement, Fleiss, n = 20 items) and blind test-retest κ = 0.426 (flag, n = 20).

- Inter-rater, 3 raters, 30-item subset, before adjudication: class-row 0.774 [0.645, 0.886] (n = 20 items, 80 units); flag 0.571 [0.289, 0.807] (n = 20 items, 20 units); not-obligation 0.392 [-0.015, 0.689] (n = 30 items, 30 units).
- Test-retest (blind, no washout period): flag 0.426 [0.091, 0.730] (n = 20 items, 20 units); class-row 0.550 [0.333, 0.752] (n = 20 items, 78 units).
- Timed re-label of 20 single-pass items: flag 0.409 [0.042, 0.759] (n = 19 items, 19 units); class-row 0.684 [0.506, 0.872] (n = 19 items, 72 units).
- The pilot Fleiss flag κ (0.603, n = 17) is conditional: `applies_to` was pre-filled for all raters.

## Known biases

- T2 `t2_xclass_t1`: Raters were shown the bge-base-en-v1.5 top-1/top-2 P2-002 candidates for each compared class (they could look up any paragraph), so the labelled counterparts favour the dense retriever.
- T2 `t2_xclass_p2002`: Pairs were drawn by bge-base-en-v1.5 semantic-score bands (the same model and revision as the dense system), so the relevant paragraphs favour the dense retriever.
- T2 `t2_supp_p2003`: Candidates shown to the rater were ranked by TF-IDF, which favours BM25 (the rater could enter any paragraph id of the Direction).
- T2 relevance covers only the target-class counterpart, so class-blind retrievers are partly disadvantaged by construction.
- T1: most items are single-pass; compared classes are capped at 4 per item; `absent` covers only the paragraphs shown or looked up; source classes have 7–15 items each.
- T3 gold and a temporal filter built from the same parser are circular; the corpus holds only amended text.
- T4: 30 questions drafted by one LLM; one rater.

## Intended use

Evaluating retrieval and QA systems on entity-class applicability, differential obligations and amendment dates in RBI Directions, and auditing answer-faithfulness metrics. Compare systems on the same items with paired CIs.

## Out-of-scope use

- Legal or compliance advice; the labels are research annotations, not RBI interpretations.
- Training a model and reporting results on the same items (there is no held-out split).
- Redistributing rehydrated RBI text as part of a derived dataset without checking RBI's terms.

## Guidelines

Annotation guidelines v3 (with the later v3.x sections): `release/guidelines/ANNOTATION_INSTRUCTIONS.md`. Names are replaced by rater ids; there is no RBI text beyond short quotations.

## Licence

The annotations and derived metadata are licensed CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). **This covers the annotations only.** RBI documents are not included and are not licensed by this project. The code is MIT (repository `LICENSE`).

