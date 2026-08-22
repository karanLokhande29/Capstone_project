"""Temporal metadata extraction from document titles and extracted text."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.utils import load_config, resolve_path, setup_logging

UPDATED_RE = re.compile(
    r"(?:Updated|updated)\s+as\s+on\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    re.IGNORECASE,
)
AMENDMENT_RE = re.compile(
    r"(Amendment\s+Directions?|amended\s+by|as\s+amended\s+by)([^\n.]{0,120})",
    re.IGNORECASE,
)
SUPERSESSION_RE = re.compile(
    r"(supersede[sd]?|in\s+supersession\s+of|hereby\s+repealed|stand[s]?\s+repealed)([^\n.]{0,160})",
    re.IGNORECASE,
)
IN_FORCE_RE = re.compile(
    r"(?:shall\s+come\s+into\s+force|come\s+into\s+effect|effective\s+from)\s+(?:on\s+|from\s+)?([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|April\s+1,\s+\d{4})",
    re.IGNORECASE,
)


@dataclass
class TemporalRecord:
    document_id: str
    update_date_stamp: str | None
    amendment_refs: list[str]
    supersession_language: list[str]
    in_force_from: str | None
    usable_date: bool


class TemporalExtractor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("metadata.temporal", self.cfg)
        self.meta = resolve_path(self.cfg, "metadata")
        self.extracted = resolve_path(self.cfg, "extracted")

    def extract_from_text(self, document_id: str, text: str, title: str = "") -> TemporalRecord:
        blob = f"{title}\n{text[:20000]}"
        updates = UPDATED_RE.findall(blob)
        amendments = [m.group(0).strip() for m in AMENDMENT_RE.finditer(blob)]
        supers = [m.group(0).strip() for m in SUPERSESSION_RE.finditer(blob)]
        forces = IN_FORCE_RE.findall(blob)
        stamp = updates[0] if updates else None
        in_force = forces[0] if forces else None
        usable = bool(stamp or in_force)
        return TemporalRecord(
            document_id=document_id,
            update_date_stamp=stamp,
            amendment_refs=amendments[:20],
            supersession_language=supers[:20],
            in_force_from=in_force,
            usable_date=usable,
        )

    def run(self, document_ids: list[str] | None = None, limit: int | None = None) -> dict[str, Any]:
        catalog = json.loads((self.meta / "discovered_documents.json").read_text(encoding="utf-8"))
        by_id = {r["document_id"]: r for r in catalog}
        ids = document_ids or list(by_id.keys())
        if limit is not None:
            ids = ids[: int(limit)]

        records: list[TemporalRecord] = []
        for did in ids:
            text_path = self.extracted / f"{did}.txt"
            title = by_id.get(did, {}).get("title", "")
            if not text_path.exists():
                # Still try title-only
                rec = self.extract_from_text(did, "", title=title)
                records.append(rec)
                continue
            text = text_path.read_text(encoding="utf-8", errors="replace")
            records.append(self.extract_from_text(did, text, title=title))

        out = self.meta / "temporal_metadata.json"
        out.write_text(
            json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        usable = sum(1 for r in records if r.usable_date)
        self.logger.info("Temporal coverage: %s/%s usable dates", usable, len(records))
        return {
            "documents_processed": len(records),
            "usable_date_count": usable,
            "temporal_coverage_rate": (usable / len(records)) if records else 0.0,
            "output_path": str(out),
        }
