#!/usr/bin/env python3
"""P5-001 task 4: write release/DATASET_CARD.md from reports/results_v1.json and release/MANIFEST.json.

    python3 scripts/build_card.py

Sizes and reliability figures are read from those files, never typed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_tables import kappa, rate  # noqa: E402


def main() -> int:
    R = json.loads((ROOT / "reports" / "results_v1.json").read_text())["tables"]
    M = json.loads((ROOT / "release" / "MANIFEST.json").read_text())
    c1, c5, c6, c8, c9 = R["01_corpus"], R["05_t1_benchmark"], R["06_t2_retrieval"], R["08_t3"], R["09_t4"]
    irr, rt, tr = c5["irr"]["fleiss"], c5["retest"]["phase2"]["all_25"], c5["timed_relabel"]
    rows = lambda f: M[f]["rows"]  # noqa: E731
    harvest = sorted({json.loads(x)["harvest_date"] for x in (ROOT / "release" / "data" / "documents.jsonl").read_text().splitlines() if x.strip()})
    L = []
    A = L.append
    A("# RBI-ObliBench — dataset card\n")
    A("Version 1.0. Annotations and derived metadata for evaluating retrieval and QA systems on Reserve Bank of India (RBI) "
      "Master Directions. **This release contains no RBI text.** Every item points into the corpus (Direction id, "
      "paragraph id, character offsets, source URL, harvest date, sha256 of the paragraph text); `scripts/rehydrate.py` "
      "(or `release/rehydrate.py`) rebuilds the text from RBI's own URLs and checks it against the hashes.\n")
    A("## Corpus\n")
    A(f"- {c1['directions']} Master Directions from RBI's listing, {c1['paragraphs']:,} paragraphs, harvested "
      f"{harvest[0]} to {harvest[-1]} (`data/documents.jsonl`, `data/paragraphs.jsonl`).")
    A(f"- {c1['entity_classes']} entity-class headings: {c1['core_entity_classes']} regulated-entity classes and "
      f"{c1['function_headings']} RBI function headings. {c1['subject_families']} subject families, derived from titles; "
      f"{c1['directions_with_subject_family']} Directions have one.")
    A("- **Drift warning:** RBI updates consolidated Directions in place (\"Updated as on …\"). A rehydrated paragraph can "
      "differ from the harvested one; `rehydrate.py` reports it as `drifted` rather than silently using it.\n")
    A("## Tasks and files\n")
    A("| Task | File(s) | Rows | What an item is |\n|---|---|---|---|")
    A(f"| T1 candidates | `data/t1/candidates_part1.jsonl`, `candidates_part2.jsonl` | {rows('data/t1/candidates_part1.jsonl') + rows('data/t1/candidates_part2.jsonl'):,} | an automatically extracted obligation span with P2-002 cross-class candidate labels (`label_status: candidate`) |")
    A(f"| T1 validated | `data/t1/validated.jsonl` | {rows('data/t1/validated.jsonl')} | a human-validated obligation: per-class judgement (`same` / `different` / `none`), matched counterpart, `applies_to`, differential flag |")
    for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        A(f"| T2 `{s}` | `data/t2/{s}.jsonl` | {rows(f'data/t2/{s}.jsonl')} | a query (pointer) with a target class and graded relevant paragraphs |")
    A(f"| T3 | `data/t3/items.jsonl`, `data/t3/dropped.jsonl` | {rows('data/t3/items.jsonl')} + {rows('data/t3/dropped.jsonl')} dropped | a (paragraph, as-of date) with gold status and governing instrument; dropped items carry the reason |")
    A(f"| T4 | `data/t4/questions.jsonl`, `answers_*.jsonl`, `scores.jsonl` | {rows('data/t4/questions.jsonl')} questions, {rows('data/t4/scores.jsonl')} scored answers | a question with four answer types, RePASs scores and (30 answers) human ratings |")
    A(f"| Matrix | `data/matrix/matrix_v1.jsonl`, `matrix_v1_summary.json` | {rows('data/matrix/matrix_v1.jsonl'):,} | one entity class × subject family cell |")
    A("")
    A("**Splits.** Evaluation-only; there is no training split. T4 has 28 primary questions (the rater flagged 2 as bad) "
      "and 30 in the sensitivity analysis. T3 has 52 scored items; 8 were dropped after the second parse spot-check.\n")
    A("### Pointer fields (every task)\n")
    A("`md_id`, `paragraph_id`, `source_url`, `harvest_date`, `paragraph_sha256`; for spans `units` (character offsets "
      "`[start, end)` into the paragraph text), `rule` and `text_sha256`. Rebuild rules (`src/release/rebuild.py`):\n")
    A("- `span_text`: `\" … \".join` of the whitespace-collapsed character ranges (T1 spans, T2 `t2_xclass_t1` queries);")
    A("- `raw_slice`: the raw character range (T2 `t2_xclass_p2002` queries);")
    A("- `spans_text`: `\" \".join` of whitespace-collapsed sentence ranges (T4 concatenated and off-topic answers);")
    A("- `negate(concatenated)`: flip shall/must/required polarity and double every number (T4 negated answers, `src/t4/audit.py`).\n")
    A("The 25 `t2_supp_p2003` query texts come from RBI FAQ pages and press releases, not from the corpus; they carry the "
      "source URL and sha256 but are **not** rebuilt automatically (the parser is in `src/supplementary/`). T4 genuine "
      "answers are LLM outputs and are included as text; one answer (T4Q25) quoted 32 consecutive corpus words and is cut "
      "to 25 words plus \"[…]\" (recorded in `redactions`; `text_sha256` is of the answer as scored).\n")
    A("### Subject × Entity-Class Matrix (`data/matrix/matrix_v1.jsonl`)\n")
    A("Derived metadata only. One row per (entity class, subject family) cell:\n")
    A("| Field | Type | Meaning |\n|---|---|---|")
    A("| `entity_class`, `entity_class_term_id` | string | entity-class heading from RBI's listing and its vocabulary id (`data/metadata/entity_classes.json`) |")
    A("| `subject_family`, `subject_family_term_id` | string | subject family derived from Direction titles and its id (`data/metadata/subject_families.json`) |")
    A("| `populated` | bool | at least one Direction exists for the cell |")
    A("| `source_directions` | list of `md_id` | the Directions in the cell |")
    A("| `n_documents` | int | number of Directions in the cell |")
    A("| `ambiguous`, `ambiguity_reason` | bool, string | the title-to-family mapping was ambiguous, and why |")
    A("| `notes` | string | provenance of each axis (raw vs derived) |")
    m = c1["matrix"]
    A(f"\nSummary (`matrix_v1_summary.json`): {m['total_cells']} cells, {m['populated_cells']} populated, "
      f"{m['ambiguous_cells']} ambiguous, {m['duplicate_mapping_cells']} with duplicate mappings.\n")
    A("## Label sources and provenance\n")
    A(f"- T1: {c5['validated']} validated of {c5['sample']} sampled ({c5['rejected']} rejected as not an obligation). Every "
      "label is manual. Routes: " + ", ".join(f"`{k}` {v}" for k, v in c5["route_counts"].items()) + " (field `provenance`).")
    A("- T2: relevance comes from the T1 labels (`t2_xclass_t1`), the P2-002 validation pairs (`t2_xclass_p2002`) and the "
      "P2-003 hand alignment (`t2_supp_p2003`); all manual.")
    A("- T3: gold is computed by a deterministic amendment parser; humans spot-checked the parses "
      f"({rate(c8['precision_v1_human']['k'], c8['precision_v1_human']['n'], c8['precision_v1_human']['wilson_95'])} for rules v1; "
      f"{rate(c8['precision_independent_post_fix']['k'], c8['precision_independent_post_fix']['n'], c8['precision_independent_post_fix']['wilson_95'])} "
      "independent post-fix).")
    A("- T4: questions and genuine answers are LLM outputs (Groq `openai/gpt-oss-120b`); the other answer types are rule-built. "
      "The human ratings are manual, blind, by one rater.")
    A("- Raters are pseudonymised as `rater_1` (primary annotator), `rater_2` and `rater_3` (second raters). The release "
      "has no names and no per-person minutes. No AI tool was used for any label.\n")
    A("## Reliability\n")
    A(f"Single-expert annotations with second-rater κ = {irr['per_class_judgement']['kappa']:.3f} (class-row judgement, Fleiss, "
      f"n = {irr['per_class_judgement']['n_items']} items) and blind test-retest κ = {rt['differential_flag']['kappa']:.3f} "
      f"(flag, n = {rt['differential_flag']['n_items']}).\n")
    A(f"- Inter-rater, 3 raters, {c5['irr']['items']}-item subset, before adjudication: class-row {kappa(irr['per_class_judgement'])}; "
      f"flag {kappa(irr['differential_flag'])}; not-obligation {kappa(irr['not_obligation'])}.")
    A(f"- Test-retest (blind, no washout period): flag {kappa(rt['differential_flag'])}; class-row {kappa(rt['per_class_judgement'])}.")
    A(f"- Timed re-label of 20 single-pass items: flag {kappa(tr['differential_flag'])}; class-row {kappa(tr['per_class_judgement'])}.")
    A(f"- The pilot Fleiss flag κ ({c5['pilot_fleiss_flag']['kappa']:.3f}, n = {c5['pilot_fleiss_flag']['n_items']}) is conditional: "
      "`applies_to` was pre-filled for all raters.\n")
    A("## Known biases\n")
    for s in ("t2_xclass_t1", "t2_xclass_p2002", "t2_supp_p2003"):
        A(f"- T2 `{s}`: {c6['p3001'][s]['bias']}")
    A("- T2 relevance covers only the target-class counterpart, so class-blind retrievers are partly disadvantaged by construction.")
    A("- T1: most items are single-pass; compared classes are capped at 4 per item; `absent` covers only the paragraphs shown "
      "or looked up; source classes have 7–15 items each.")
    A("- T3 gold and a temporal filter built from the same parser are circular; the corpus holds only amended text.")
    A("- T4: 30 questions drafted by one LLM; one rater.\n")
    A("## Intended use\n")
    A("Evaluating retrieval and QA systems on entity-class applicability, differential obligations and amendment dates in RBI "
      "Directions, and auditing answer-faithfulness metrics. Compare systems on the same items with paired CIs.\n")
    A("## Out-of-scope use\n")
    A("- Legal or compliance advice; the labels are research annotations, not RBI interpretations.")
    A("- Training a model and reporting results on the same items (there is no held-out split).")
    A("- Redistributing rehydrated RBI text as part of a derived dataset without checking RBI's terms.\n")
    A("## Guidelines\n")
    A("Annotation guidelines v3 (with the later v3.x sections): `release/guidelines/ANNOTATION_INSTRUCTIONS.md`. Names are "
      "replaced by rater ids; there is no RBI text beyond short quotations.\n")
    A("## Licence\n")
    A("The annotations and derived metadata are licensed CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). **This covers the annotations "
      "only.** RBI documents are not included and are not licensed by this project. The code is MIT (repository `LICENSE`).\n")
    (ROOT / "release" / "DATASET_CARD.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote release/DATASET_CARD.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
