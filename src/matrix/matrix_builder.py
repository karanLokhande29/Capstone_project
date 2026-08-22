"""Subject × Entity-Class Matrix builder (v1)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import load_config, resolve_path, setup_logging

ENTITY_PREFIXES = [
    "Commercial Banks",
    "Small Finance Banks",
    "Payments Banks",
    "Local Area Banks",
    "Regional Rural Banks",
    "Urban Co-operative Banks",
    "Rural Co-operative Banks",
    "All India Financial Institutions",
    "Non-Banking Financial Companies",
    "Asset Reconstruction Companies",
    "Credit Information Companies",
    "Non-Bank Prepaid Payment Instruments Issuers",
    "Universal Banks",
    "Primary Dealers",
]


def normalize_subject(raw: str, entity: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"\s+", " ", s)
    # Strip leading entity name if redundantly present
    for ent in sorted(ENTITY_PREFIXES, key=len, reverse=True):
        if s.lower().startswith(ent.lower()):
            s = s[len(ent) :].strip(" –-:|")
    if entity and s.lower().startswith(entity.lower()):
        s = s[len(entity) :].strip(" –-:|")
    s = re.sub(r"\s*\(Updated as on.*?\)\s*", "", s, flags=re.I)
    return s.strip() or raw


class MatrixBuilder:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("matrix.builder", self.cfg)
        self.meta = resolve_path(self.cfg, "metadata")
        self.matrix_dir = resolve_path(self.cfg, "matrix")
        self.reports = resolve_path(self.cfg, "reports")

    def build_v1(self) -> dict[str, Any]:
        catalog = json.loads((self.meta / "discovered_documents.json").read_text(encoding="utf-8"))
        rows = []
        # cell -> list of document_ids
        cell_docs: dict[tuple[str, str], list[str]] = defaultdict(list)
        ambiguous: list[dict[str, Any]] = []

        for doc in catalog:
            entity = (doc.get("entity_class_raw") or "").strip() or "UNKNOWN"
            subject_raw = doc.get("subject_family_raw") or ""
            subject = normalize_subject(subject_raw, entity)
            if entity == "UNKNOWN" or not subject:
                ambiguous.append(
                    {
                        "document_id": doc["document_id"],
                        "reason": "ambiguous_entity_or_subject",
                        "title": doc.get("title"),
                        "entity_class_raw": entity,
                        "subject_family_raw": subject_raw,
                    }
                )
            cell_docs[(entity, subject)].append(doc["document_id"])
            rows.append(
                {
                    "entity_class": entity,
                    "subject_family": subject,
                    "subject_family_raw": subject_raw,
                    "document_id": doc["document_id"],
                    "source_url": doc.get("source_url"),
                    "title": doc.get("title"),
                    "category_heading": doc.get("category_heading"),
                }
            )

        df = pd.DataFrame(rows)
        out_csv = self.matrix_dir / "matrix_v1.csv"
        df.to_csv(out_csv, index=False)

        entities = sorted({e for e, _ in cell_docs.keys()})
        subjects = sorted({s for _, s in cell_docs.keys()})
        populated = len(cell_docs)
        # Theoretical grid from discovered axes
        theoretical = len(entities) * len(subjects) if entities and subjects else 0
        missing = max(theoretical - populated, 0)

        # Duplicates: same entity+subject mapped to >1 document
        duplicates = [
            {
                "entity_class": e,
                "subject_family": s,
                "document_ids": ids,
                "count": len(ids),
            }
            for (e, s), ids in cell_docs.items()
            if len(ids) > 1
        ]

        # Persist cell summary
        cells = []
        for (e, s), ids in sorted(cell_docs.items()):
            cells.append(
                {
                    "entity_class": e,
                    "subject_family": s,
                    "document_ids": ids,
                    "n_documents": len(ids),
                    "status": "populated",
                }
            )
        (self.matrix_dir / "matrix_v1_cells.json").write_text(
            json.dumps(cells, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (self.matrix_dir / "matrix_v1_ambiguous.json").write_text(
            json.dumps(ambiguous, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (self.matrix_dir / "matrix_v1_duplicates.json").write_text(
            json.dumps(duplicates, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        coverage = (populated / theoretical) if theoretical else 0.0
        summary_md = self.reports / "week3_matrix_summary.md"
        summary_md.write_text(
            "\n".join(
                [
                    "# Week 3 — Matrix v1 Summary",
                    "",
                    "Counts below are **discovered** from the harvested corpus (not dossier estimates).",
                    "",
                    f"- Entity classes discovered: **{len(entities)}**",
                    f"- Subject families discovered (normalized): **{len(subjects)}**",
                    f"- Populated cells: **{populated}**",
                    f"- Theoretical grid size (E×S): **{theoretical}**",
                    f"- Missing cells (theoretical − populated): **{missing}**",
                    f"- Duplicate mappings (cells with >1 Direction): **{len(duplicates)}**",
                    f"- Ambiguous mappings flagged: **{len(ambiguous)}**",
                    f"- Matrix coverage (populated/theoretical): **{coverage:.4f}**",
                    "",
                    "## Entity classes",
                    "",
                    *[f"- {e}" for e in entities],
                    "",
                    f"Artifacts: `{out_csv}`, `data/matrix/matrix_v1_cells.json`.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        self.logger.info(
            "Matrix v1: entities=%s subjects=%s populated=%s missing=%s",
            len(entities),
            len(subjects),
            populated,
            missing,
        )
        return {
            "entity_classes_discovered": len(entities),
            "subject_families_discovered": len(subjects),
            "matrix_cells_populated": populated,
            "matrix_cells_missing": missing,
            "duplicate_mappings_count": len(duplicates),
            "ambiguous_mappings_count": len(ambiguous),
            "matrix_coverage": coverage,
            "entity_classes": entities,
            "subject_families": subjects,
            "matrix_v1_path": str(out_csv),
            "summary_path": str(summary_md),
        }
