"""Detect explicit cross-references between paragraphs / Directions."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.utils import load_config, resolve_path, setup_logging

PATTERNS = [
    re.compile(
        r"as\s+(?:specified|provided|laid\s+down|stated)\s+in\s+(?:paragraph|para\.?|clause)\s+"
        r"([0-9A-Za-z.()/\-]+)(?:\s+of\s+([^,]{5,80}))?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:in\s+terms\s+of|under)\s+(?:paragraph|para\.?|clause)\s+([0-9A-Za-z.()/\-]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"Master\s+Direction[s]?\s+(?:on|–|-)?\s*([^,\n]{5,100})",
        re.IGNORECASE,
    ),
]


@dataclass
class CrossReference:
    source_paragraph_id: str
    source_document_id: str
    raw_snippet: str
    target_paragraph_hint: str | None
    target_document_hint: str | None
    pattern_name: str


class CrossReferenceDetector:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("preprocessing.xref", self.cfg)
        self.processed = resolve_path(self.cfg, "processed")
        self.meta = resolve_path(self.cfg, "metadata")

    def detect_in_text(
        self, paragraph_id: str, document_id: str, text: str
    ) -> list[CrossReference]:
        found: list[CrossReference] = []
        for i, pat in enumerate(PATTERNS):
            for m in pat.finditer(text):
                groups = m.groups()
                para_hint = groups[0] if groups else None
                doc_hint = groups[1] if len(groups) > 1 else None
                found.append(
                    CrossReference(
                        source_paragraph_id=paragraph_id,
                        source_document_id=document_id,
                        raw_snippet=m.group(0)[:240],
                        target_paragraph_hint=para_hint,
                        target_document_hint=doc_hint,
                        pattern_name=f"pattern_{i}",
                    )
                )
        return found

    def run(self) -> dict[str, Any]:
        refs: list[CrossReference] = []
        for path in sorted(self.processed.glob("md_*.jsonl")):
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    refs.extend(
                        self.detect_in_text(
                            row["paragraph_id"], row["document_id"], row.get("text", "")
                        )
                    )
        # Also catch pdf_/doc_ ids
        for path in sorted(self.processed.glob("*.jsonl")):
            if path.name == "paragraphs_index.jsonl":
                continue
            if path.name.startswith("md_"):
                continue
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    refs.extend(
                        self.detect_in_text(
                            row["paragraph_id"], row["document_id"], row.get("text", "")
                        )
                    )

        out = self.meta / "cross_references.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for r in refs:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
        self.logger.info("Recorded %s cross-reference mentions", len(refs))
        return {"cross_reference_count": len(refs), "output_path": str(out)}
