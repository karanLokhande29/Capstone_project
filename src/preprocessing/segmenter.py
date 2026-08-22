"""Paragraph segmentation with stable deterministic IDs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.utils import load_config, resolve_path, setup_logging

XREF_INLINE = re.compile(
    r"(?:as\s+(?:specified|provided|laid\s+down|stated)\s+in|in\s+terms\s+of|refer(?:red)?\s+to)"
    r"[^\n.]{0,160}",
    re.IGNORECASE,
)


@dataclass
class ParagraphUnit:
    paragraph_id: str
    document_id: str
    document_title: str
    source_url: str
    position: int
    text: str
    entity_class: str
    subject_family: str
    update_date: str | None
    extraction_source: str
    cross_reference_snippets: list[str] = field(default_factory=list)


def stable_paragraph_id(document_id: str, position: int) -> str:
    return f"{document_id}::p{position:05d}"


def split_paragraphs(text: str, min_chars: int = 40) -> list[str]:
    # Split on blank lines first; fall back to numbered clauses
    parts = re.split(r"\n\s*\n+", text)
    cleaned: list[str] = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) >= min_chars:
            cleaned.append(p)
    if len(cleaned) < 2:
        # Try clause-style splits: "1. ", "2. ", "(i)", etc.
        alt = re.split(r"(?=\n\s*(?:\d+\.|\([a-zivx]+\))\s+)", text)
        cleaned = []
        for p in alt:
            p = re.sub(r"\s+", " ", p).strip()
            if len(p) >= min_chars:
                cleaned.append(p)
    return cleaned


class Segmenter:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("preprocessing.segmenter", self.cfg)
        self.out_dir = resolve_path(self.cfg, "processed")
        self.extracted = resolve_path(self.cfg, "extracted")
        self.meta = resolve_path(self.cfg, "metadata")
        self.min_chars = int(self.cfg.get("segmentation", {}).get("min_paragraph_chars", 40))

    def segment_document(
        self,
        document_id: str,
        text: str,
        *,
        title: str,
        source_url: str,
        entity_class: str,
        subject_family: str,
        update_date: str | None,
        extraction_source: str = "rbi_master_directions",
    ) -> list[ParagraphUnit]:
        paras = split_paragraphs(text, min_chars=self.min_chars)
        units: list[ParagraphUnit] = []
        for i, p in enumerate(paras):
            xrefs = [m.group(0).strip() for m in XREF_INLINE.finditer(p)]
            units.append(
                ParagraphUnit(
                    paragraph_id=stable_paragraph_id(document_id, i),
                    document_id=document_id,
                    document_title=title,
                    source_url=source_url,
                    position=i,
                    text=p,
                    entity_class=entity_class,
                    subject_family=subject_family,
                    update_date=update_date,
                    extraction_source=extraction_source,
                    cross_reference_snippets=xrefs,
                )
            )
        return units

    def run(self) -> dict[str, Any]:
        catalog = json.loads((self.meta / "discovered_documents.json").read_text(encoding="utf-8"))
        temporal_path = self.meta / "temporal_metadata.json"
        temporal = {}
        if temporal_path.exists():
            temporal = {r["document_id"]: r for r in json.loads(temporal_path.read_text(encoding="utf-8"))}

        all_units: list[dict[str, Any]] = []
        malformed = 0
        extraction_failures = 0
        for row in catalog:
            did = row["document_id"]
            text_path = self.extracted / f"{did}.txt"
            if not text_path.exists():
                extraction_failures += 1
                continue
            text = text_path.read_text(encoding="utf-8", errors="replace")
            if len(text.strip()) < self.min_chars:
                malformed += 1
                continue
            update = None
            if did in temporal:
                update = temporal[did].get("update_date_stamp") or row.get("update_date_stamp")
            else:
                update = row.get("update_date_stamp")
            units = self.segment_document(
                did,
                text,
                title=row.get("title", ""),
                source_url=row.get("source_url", ""),
                entity_class=row.get("entity_class_raw", ""),
                subject_family=row.get("subject_family_raw", ""),
                update_date=update,
            )
            # Write per-document JSONL (text included for local processing; not redistributed)
            out = self.out_dir / f"{did}.jsonl"
            with out.open("w", encoding="utf-8") as f:
                for u in units:
                    f.write(json.dumps(asdict(u), ensure_ascii=False) + "\n")
            all_units.extend(asdict(u) for u in units)

        index_path = self.out_dir / "paragraphs_index.jsonl"
        with index_path.open("w", encoding="utf-8") as f:
            for u in all_units:
                # Index without full text to keep smaller; text lives in per-doc files
                slim = {k: v for k, v in u.items() if k != "text"}
                slim["text_char_count"] = len(u.get("text") or "")
                f.write(json.dumps(slim, ensure_ascii=False) + "\n")

        self.logger.info("Segmented %s paragraphs across corpus", len(all_units))
        return {
            "total_paragraphs": len(all_units),
            "extraction_failures_missing_text": extraction_failures,
            "malformed_documents": malformed,
            "index_path": str(index_path),
        }
