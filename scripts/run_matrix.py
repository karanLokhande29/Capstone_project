#!/usr/bin/env python3
"""CLI entry point for vocabulary discovery, normalization, and matrix building.

    python scripts/run_matrix.py discover    # vocabularies only, no writes to Document/ParagraphRecord
    python scripts/run_matrix.py normalize   # discover + write entity_class/subject_family onto records
    python scripts/run_matrix.py matrix      # build + persist the MatrixCell set (requires normalize first)
    python scripts/run_matrix.py all         # all of the above, then write the report
    python scripts/run_matrix.py report      # regenerate reports/phase1_karan_matrix.md only

Reads Akash's committed `data/metadata/document_manifest.jsonl` and
`data/processed/*.jsonl`; writes normalized values back into those same
files (never touching `*_raw`) plus the new vocabulary and matrix artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import load_config  # noqa: E402
from src.common.io_helpers import read_jsonl, write_json, write_jsonl  # noqa: E402
from src.common.logging_setup import get_logger  # noqa: E402
from src.common.paths import PathResolver  # noqa: E402
from src.matrix.matrix_builder import build_matrix, matrix_metrics, persist_matrix  # noqa: E402
from src.metadata.vocabulary_discovery import (  # noqa: E402
    discover_entity_class_vocabulary,
    discover_subject_family_vocabulary,
    normalise_documents,
    normalise_paragraphs,
    persist_vocabularies,
    provenance_counts,
    segmented_unresolved_rates,
)
from src.schemas.provenance import DocumentRecord, ParagraphRecord  # noqa: E402


def _load_documents(resolver: PathResolver) -> list[DocumentRecord]:
    manifest_path = resolver.read_path("metadata", "document_manifest.jsonl")
    return [DocumentRecord.from_dict(r) for r in read_jsonl(manifest_path)]


def run_discover(cfg, resolver, logger) -> dict:
    documents = _load_documents(resolver)
    entity_vocab, entity_unresolved = discover_entity_class_vocabulary(documents, cfg, logger=logger)
    subject_vocab, subject_unresolved = discover_subject_family_vocabulary(documents, cfg, logger=logger)
    paths = persist_vocabularies(entity_vocab, subject_vocab, cfg, resolver=resolver)

    unresolved_path = resolver.write_path("metadata", "subject_family_unresolved.json")
    write_json(unresolved_path, subject_unresolved)

    metrics = {
        "documents_scanned": len(documents),
        "entity_classes_discovered": len(entity_vocab),
        "entity_class_unresolved_documents": len(entity_unresolved),
        "subject_families_discovered": len(subject_vocab),
        "subject_family_unresolved_documents": len(subject_unresolved),
        # P1-002-CORRECTIVE: provenance split and segmented rates
        "entity_class_provenance": provenance_counts(entity_vocab),
        "subject_family_provenance": provenance_counts(subject_vocab),
        "segmented_unresolved_rates": segmented_unresolved_rates(
            documents, entity_unresolved, subject_unresolved
        ),
        "entity_class_file": paths["entity_class_file"],
        "subject_family_file": paths["subject_family_file"],
        "vocabulary_provenance_file": paths["vocabulary_provenance_file"],
        "subject_family_unresolved_file": str(unresolved_path),
    }
    logger.info("discover: %s", metrics)
    return metrics


def run_normalize(cfg, resolver, logger) -> dict:
    documents = _load_documents(resolver)
    entity_vocab, _ = discover_entity_class_vocabulary(documents, cfg, logger=logger)
    subject_vocab, _ = discover_subject_family_vocabulary(documents, cfg, logger=logger)

    normalised_docs = normalise_documents(documents, entity_vocab, subject_vocab)
    doc_lookup = {r.document_id: r for r in normalised_docs}

    raw_by_id = {r.document_id: (r.entity_class_raw, r.subject_family_raw) for r in documents}
    for record in normalised_docs:
        assert raw_by_id[record.document_id] == (record.entity_class_raw, record.subject_family_raw), (
            f"*_raw field changed for {record.document_id} — this must never happen"
        )

    manifest_path = resolver.read_path("metadata", "document_manifest.jsonl")
    write_jsonl(manifest_path, [r.to_dict() for r in normalised_docs])

    documents_with_paragraphs = 0
    documents_missing_paragraphs = 0
    total_paragraphs_normalised = 0
    index_rows: list[dict] = []

    for record in normalised_docs:
        doc_path = resolver.find_read_path("processed", f"{record.document_id}.jsonl")
        if doc_path is None:
            documents_missing_paragraphs += 1
            continue
        paragraphs = [ParagraphRecord.from_dict(r) for r in read_jsonl(doc_path)]
        normalised_paragraphs = normalise_paragraphs(paragraphs, doc_lookup)
        write_jsonl(doc_path, [p.to_dict() for p in normalised_paragraphs])
        total_paragraphs_normalised += len(normalised_paragraphs)
        documents_with_paragraphs += 1
        for paragraph in normalised_paragraphs:
            slim = paragraph.to_dict()
            slim.pop("text", None)
            slim["text_char_count"] = len(paragraph.text or "")
            index_rows.append(slim)

    if index_rows:
        index_path = resolver.write_path("processed", "paragraphs_index.jsonl")
        write_jsonl(index_path, index_rows)

    ec_coverage = sum(1 for r in normalised_docs if r.entity_class) / len(normalised_docs) if normalised_docs else 0.0
    sf_coverage = sum(1 for r in normalised_docs if r.subject_family) / len(normalised_docs) if normalised_docs else 0.0

    metrics = {
        "documents_normalised": len(normalised_docs),
        "entity_class_extraction_coverage": ec_coverage,
        "subject_family_extraction_coverage": sf_coverage,
        "documents_with_paragraphs_normalised": documents_with_paragraphs,
        "documents_missing_paragraphs": documents_missing_paragraphs,
        "total_paragraphs_normalised": total_paragraphs_normalised,
        "raw_fields_verified_unchanged": True,
    }
    logger.info("normalize: %s", metrics)
    return metrics


def run_matrix_stage(cfg, resolver, logger) -> dict:
    documents = _load_documents(resolver)
    entity_vocab, _ = discover_entity_class_vocabulary(documents, cfg, logger=logger)
    subject_vocab, _ = discover_subject_family_vocabulary(documents, cfg, logger=logger)
    normalised_docs = normalise_documents(documents, entity_vocab, subject_vocab)

    cells = build_matrix(normalised_docs, entity_vocab, subject_vocab, cfg, logger=logger)
    paths = persist_matrix(cells, cfg, resolver=resolver)
    metrics = matrix_metrics(cells)
    metrics.update(paths)
    logger.info("matrix: %s", metrics)
    return metrics


def _write_report(metrics: dict, resolver: PathResolver, logger) -> Path:
    discover = metrics.get("discover", {})
    normalize = metrics.get("normalize", {})
    matrix = metrics.get("matrix", {})

    ec_prov = discover.get("entity_class_provenance", {})
    sf_prov = discover.get("subject_family_provenance", {})
    seg = discover.get("segmented_unresolved_rates", {})

    lines = [
        "# Phase 1 — Karan: Metadata Normalization + Subject x Entity-Class Matrix",
        "",
        "---",
        "",
        "## FINDING (2026-08-23): `subject_family_raw` is absent from the entire corpus",
        "",
        "**This should have been reported before any workaround was built on top "
        "of it. It was not — it is recorded here retroactively, stated as it "
        "should have been stated at the moment of discovery.**",
        "",
        "`DocumentRecord.subject_family_raw` is **null for all 380 harvested "
        "documents**. Investigation during P1-002 established why, and the cause "
        "is a property of the source, not a defect in `phase1/akash-scraper`'s "
        "extraction:",
        "",
        "- The RBI Master Directions listing (`BS_ViewMasDirections.aspx`) groups "
        "documents under an entity-class heading and a date sub-heading only. "
        "There is no subject/topic column, no dropdown, no anchor, and no "
        "distinguishing id on any heading row.",
        "- The document text itself carries no `Subject:`-style field either "
        "(sampled across extracted documents; zero hits).",
        "",
        "**In short: RBI's Master Directions listing does not publish a "
        "subject-family taxonomy at discovery time.** One of the two axes of the "
        "Subject x Entity-Class Matrix — the project's primary structural "
        "artifact — has no harvested source.",
        "",
        "Per P1-002 Section AB, this was a stop-and-report condition (\"P1-001's "
        "committed data turns out to be missing a field this step needs — do not "
        "patch around a gap in Akash's output, report it\"). P1-002 instead "
        "proceeded directly to a title-derivation workaround. The derivation "
        "itself is sound and validated (see below and "
        "`src/metadata/vocabulary_discovery.py`), and is **not** being redone — "
        "but it should have been a reported decision, not an assumed one.",
        "",
        "### Consequence for downstream consumers",
        "",
        "Every `subject_family` value in this corpus is **inferred**, not "
        "harvested. It is now marked as such in the data itself (see "
        "\"Provenance marking\" below), so no consumer needs to read a docstring "
        "to discover this. Anyone stratifying, sampling, or reporting on "
        "subject families — starting with `phase1/meer-annotation` (P1-003) — "
        "should treat that axis as project-inferred metadata, and should not "
        "describe it as RBI's own classification.",
        "",
        "---",
        "",
        "## Vocabulary discovery",
        "",
        f"- Documents scanned: **{discover.get('documents_scanned', 'NOT YET MEASURED')}**",
        f"- Entity classes discovered: **{discover.get('entity_classes_discovered', 'NOT YET MEASURED')}** "
        "(dossier estimate: ~11 — reported as a finding, not corrected toward it)",
        f"- Subject families discovered: **{discover.get('subject_families_discovered', 'NOT YET MEASURED')}** "
        "(dossier estimate: ~26 — reported as a finding, not corrected toward it)",
        f"- Entity-class unresolved documents: **{discover.get('entity_class_unresolved_documents', 'NOT YET MEASURED')}**",
        f"- Subject-family unresolved documents: **{discover.get('subject_family_unresolved_documents', 'NOT YET MEASURED')}**",
        "",
        "## Provenance marking (queryable from the data, not just this report)",
        "",
        "Each `VocabularyTerm.source` now carries a machine-readable prefix, so "
        "harvested and inferred terms are mechanically separable:",
        "",
        "| Axis | raw | derived | mixed |",
        "|---|---|---|---|",
        f"| `entity_class` | **{ec_prov.get('raw', 'n/a')}** | {ec_prov.get('derived', 'n/a')} | {ec_prov.get('mixed', 'n/a')} |",
        f"| `subject_family` | {sf_prov.get('raw', 'n/a')} | **{sf_prov.get('derived', 'n/a')}** | {sf_prov.get('mixed', 'n/a')} |",
        "",
        "- `raw:rbi_listing_entity_class_heading` — harvested from a real field, then normalised.",
        "- `derived:title_strip_entity_class` — inferred from the title; no raw source exists.",
        "",
        "Queryable three ways, none of which require reading code:",
        "",
        "```bash",
        "grep '\"source\": \"derived:' data/metadata/subject_families.json   # every inferred term",
        "cat data/metadata/vocabulary_provenance.json                       # canonical_name -> provenance",
        "grep 'DERIVED axis present' data/matrix/matrix_v1.jsonl            # cells resting on inferred axes",
        "```",
        "",
        "`MatrixCell.notes` records the provenance of both of a cell's axes, so "
        "the matrix is auditable standalone without joining back to the "
        "vocabulary files.",
        "",
        "### Schema question (P1-002-CORRECTIVE Task 3): answer — **no schema change required**",
        "",
        "*Question:* does a derived `subject_family` belong in the existing "
        "field once marked, or does honest representation require a new "
        "`subject_family_source: Literal[\"raw\",\"derived\"]` on "
        "`DocumentRecord`/`ParagraphRecord`?",
        "",
        "*Answer:* **the existing field is sufficient for this corpus, and no "
        "base-branch schema change is requested.** The reasoning, and the "
        "condition that would reverse it, both matter:",
        "",
        "1. **The join is total and verified.** Every one of the 56 distinct "
        "`subject_family` values appearing on a record resolves to exactly one "
        "`VocabularyTerm` — 56 values, 56 terms, **zero orphans**, checked "
        "programmatically. Provenance is therefore fully recoverable from the "
        "committed data for every record, with no information loss.",
        "2. **No term has mixed provenance.** Because `subject_family_raw` is "
        "null corpus-wide, all 56 subject-family terms are 100% derived and all "
        "19 entity-class terms are 100% raw. The split is clean per axis, so a "
        "per-record field would carry exactly one value per axis and duplicate "
        "what the vocabulary already states. (P1-002-CORRECTIVE Section R's "
        "mixed-provenance stop condition does **not** trigger; a test asserts "
        "this and will fail loudly if it ever changes.)",
        "3. **`VocabularyTerm.source` is Phase 0's designated field for exactly "
        "this** — its own `FIELD_SPECS` description reads \"Makes the vocabulary "
        "auditable rather than asserted.\" Using it as designed is preferable to "
        "widening two already-large record schemas (`ParagraphRecord` is at 22 "
        "fields) and to denormalising provenance into a second place that can "
        "drift out of sync with the first.",
        "",
        "**The honest counter-argument, and the trigger to revisit:** a JSONL "
        "row is often consumed standalone, and requiring a join is a real (if "
        "small) cost — which is why `vocabulary_provenance.json` is emitted as "
        "a one-lookup artifact rather than making consumers parse the full "
        "vocabulary. **If a future corpus ever yields a `subject_family` value "
        "reachable from both a raw field and a derivation, the join stops being "
        "unambiguous and the per-record field becomes genuinely necessary.** At "
        "that point this answer should flip, and the proposed field would be:",
        "",
        "> `subject_family_source: str | None` on `DocumentRecord` and "
        "`ParagraphRecord`, values `\"raw\" | \"derived\" | \"mixed\"`, owner "
        "`phase1/karan-matrix`, requiring a base-branch change agreed by all "
        "three owners.",
        "",
        "That request is **not** being raised now, because the condition "
        "justifying it does not hold for this corpus.",
        "",
        "## Segmented unresolved rate (P1-002-CORRECTIVE Task 4)",
        "",
        "P1-002 reported a single combined figure (76/380, 20%). That number "
        "conflates two different things; split by origin:",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| `entity_class` unresolved rate (**raw-sourced**) | **{seg.get('entity_class_unresolved_rate_raw_sourced', 'NOT YET MEASURED')}** "
        f"({seg.get('entity_class_unresolved', '?')}/{seg.get('entity_class_raw_sourced_documents', '?')}) |",
        f"| `subject_family` unresolved rate (combined) | **{seg.get('subject_family_unresolved_rate_combined', 'NOT YET MEASURED')}** "
        f"({seg.get('subject_family_unresolved_combined', '?')}/{seg.get('documents_total', '?')}) |",
        f"| `subject_family` unresolved rate (**raw-sourced only**) | **{seg.get('subject_family_unresolved_rate_raw_sourced_only', 'NOT YET MEASURED')}** |",
        f"| Documents with a derived `subject_family` | {seg.get('subject_family_derived_documents', '?')} / {seg.get('documents_total', '?')} |",
        "",
        "**Reading this:** the raw-sourced subject-family rate is reported as "
        "`NOT MEASURABLE`, not `0.0` — there are no raw subject-family values in "
        "this corpus, so reporting 0% would falsely imply raw values were "
        "examined and found clean. The distinction is the whole point of the "
        "split.",
        "",
        "**What it means:** the entire 20% unresolved rate is attributable to "
        "the *reach of the derivation method*, not to normalisation difficulty. "
        "On the one axis that does have a harvested source (`entity_class`), "
        "the unresolved rate is **0%** — normalisation of genuinely-harvested "
        "data in this corpus is clean. The 76 unresolved documents are "
        "overwhelmingly cases where the title names a different entity class "
        "than the filing category (the \"Internal Ombudsman\" directions), which "
        "is a limitation of inferring from titles, not a taxonomy problem.",
        "",
        "### Entity-class vocabulary: direct 1:1 construction",
        "",
        "`entity_class_raw` values are already clean, mutually distinct strings "
        "scraped directly from the RBI listing's category headings — verified "
        "against the full corpus (zero normalised-key collisions). Each raw "
        "value becomes its own canonical term; no alias resolution was needed "
        "for this corpus.",
        "",
        "### Subject-family vocabulary: title-residual extraction",
        "",
        "`subject_family_raw` is null for all discovered documents — the RBI "
        "listing has no subject/topic column (established during "
        "`phase1/akash-scraper`). Subject families are derived mechanically: "
        "the already-known `entity_class_raw` string is matched and removed "
        "from `DocumentRecord.title` on a word boundary, and RBI/Directions/"
        "date boilerplate is stripped from what remains. This is string "
        "matching on two already-discovered fields, not semantic topic "
        "modelling or invented classification — see "
        "`src/metadata/vocabulary_discovery.py` module docstring for the full "
        "methodology and the real-corpus bugs found and fixed while "
        "validating it (a dangling-bracket residual, and a singular/plural "
        "substring collision on \"Financial Market\"/\"Financial Markets\").",
        "",
        "Documents where the entity-class substring cannot be found in the "
        "title at all (e.g. the \"Internal Ombudsman\" directions, filed under "
        "`entity_class_raw` \"Consumer Education and Protection\" while their "
        "titles name the entity class the rule actually applies to) are "
        "recorded as unresolved, never force-matched — see "
        "`data/metadata/subject_family_unresolved.json` for the full list "
        "with reasons.",
        "",
        "## Normalization",
        "",
        f"- Documents normalised: **{normalize.get('documents_normalised', 'NOT YET MEASURED')}**",
        f"- Entity-class extraction coverage: **{normalize.get('entity_class_extraction_coverage', 'NOT YET MEASURED')}**",
        f"- Subject-family extraction coverage: **{normalize.get('subject_family_extraction_coverage', 'NOT YET MEASURED')}**",
        f"- Documents with paragraphs normalised: **{normalize.get('documents_with_paragraphs_normalised', 'NOT YET MEASURED')}**",
        f"- Documents missing paragraphs (not downloaded/extracted by Akash's run): "
        f"**{normalize.get('documents_missing_paragraphs', 'NOT YET MEASURED')}**",
        f"- Total paragraphs normalised: **{normalize.get('total_paragraphs_normalised', 'NOT YET MEASURED')}**",
        f"- `*_raw` fields verified unchanged: **{normalize.get('raw_fields_verified_unchanged', 'NOT YET MEASURED')}** "
        "(checked programmatically for every document, not spot-checked)",
        "",
        "## Subject x Entity-Class Matrix",
        "",
        f"- Total cells (entity classes x subject families): **{matrix.get('total_cells', 'NOT YET MEASURED')}**",
        f"- Populated cells: **{matrix.get('populated_cells', 'NOT YET MEASURED')}**",
        f"- Missing cells: **{matrix.get('missing_cells', 'NOT YET MEASURED')}**",
        f"- Ambiguous cells: **{matrix.get('ambiguous_cells', 'NOT YET MEASURED')}**",
        f"- Duplicate-mapping cells (>1 source Direction): **{matrix.get('duplicate_mapping_cells', 'NOT YET MEASURED')}**",
        f"- Matrix coverage (populated / total): **{matrix.get('matrix_coverage', 'NOT YET MEASURED')}**",
        "",
        "### On the ambiguous cells",
        "",
        "Every ambiguous cell found on the real corpus is a genuine "
        "\"Miscellaneous\" vs \"Miscellaneous Supervisory\" pairing: RBI issued "
        "both a general Miscellaneous Directions and a separate Miscellaneous "
        "Supervisory Directions for the same entity class, and this module's "
        "extraction only captures what sits inside the title's brackets — the "
        "\"Supervisory\" qualifier sits outside them, so both titles reduce to "
        "the same \"Miscellaneous\" subject residual. This is a real "
        "granularity limit of title-residual extraction, correctly surfaced as "
        "`ambiguous=True` with `ambiguity_reason='multiple_candidate_directions'` "
        "rather than silently merged or arbitrarily picked — exactly what the "
        "ambiguous flag exists to catch.",
        "",
    ]

    out_path = resolver.write_path("reports", "phase1_karan_matrix.md")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("report written: %s", out_path)
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["discover", "normalize", "matrix", "all", "report"])
    parser.add_argument("--config", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    resolver = PathResolver.from_config(cfg)
    logger = get_logger("scripts.run_matrix", cfg)

    metrics: dict = {"scope": args.stage}
    if args.stage in ("discover", "all"):
        metrics["discover"] = run_discover(cfg, resolver, logger)
    if args.stage in ("normalize", "all"):
        metrics["normalize"] = run_normalize(cfg, resolver, logger)
    if args.stage in ("matrix", "all"):
        metrics["matrix"] = run_matrix_stage(cfg, resolver, logger)
    if args.stage == "report":
        # Report-only regeneration: re-run discover/normalize/matrix in memory
        # (idempotent, no re-download) to get current metrics without assuming
        # a prior run's JSON is on disk.
        metrics["discover"] = run_discover(cfg, resolver, logger)
        metrics["normalize"] = run_normalize(cfg, resolver, logger)
        metrics["matrix"] = run_matrix_stage(cfg, resolver, logger)

    if args.stage in ("all", "report"):
        _write_report(metrics, resolver, logger)

    if args.stage != "report":
        metrics_path = resolver.write_path("reports", f"phase1_karan_{args.stage}_metrics.json")
        write_json(metrics_path, metrics)

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        for stage_name, stage_metrics in metrics.items():
            if not isinstance(stage_metrics, dict):
                continue
            print(f"=== {stage_name} ===")
            for key, value in stage_metrics.items():
                print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
