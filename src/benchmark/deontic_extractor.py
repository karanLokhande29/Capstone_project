"""Deontic cue-based CANDIDATE obligation span extraction."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.utils import load_config, resolve_path, setup_logging


@dataclass
class ObligationCandidate:
    paragraph_id: str
    document_id: str
    entity_class: str
    subject_family: str
    span_start: int
    span_end: int
    matched_cue: str
    extraction_confidence: float
    label_status: str = "candidate"
    rejected: bool = False
    rejection_reason: str | None = None
    # span_text stored only for local processing; prefer offsets for redistribution
    span_text: str = ""


class DeonticExtractor:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("benchmark.deontic", self.cfg)
        deontic = self.cfg.get("deontic", {})
        cues = deontic.get("cues") or ["shall", "must"]
        # Longer cues first
        self.cues = sorted(cues, key=len, reverse=True)
        self.reject_patterns = [
            re.compile(p) for p in (deontic.get("reject_patterns") or [])
        ]
        self.processed = resolve_path(self.cfg, "processed")
        self.out_dir = resolve_path(self.cfg, "benchmark_candidate")

    def _window(self, text: str, start: int, end: int, pad: int = 120) -> tuple[int, int, str]:
        s = max(0, start - pad)
        e = min(len(text), end + pad)
        # Expand to nearest sentence-ish boundaries
        while s > 0 and text[s] not in ".!?;\n":
            s -= 1
        while e < len(text) and text[e - 1] not in ".!?;\n":
            e += 1
        return s, e, text[s:e].strip()

    def extract_from_paragraph(self, row: dict[str, Any]) -> list[ObligationCandidate]:
        text = row.get("text") or ""
        found: list[ObligationCandidate] = []
        lower = text.lower()
        for cue in self.cues:
            start = 0
            cue_l = cue.lower()
            while True:
                idx = lower.find(cue_l, start)
                if idx < 0:
                    break
                # word-boundary-ish check
                before_ok = idx == 0 or not lower[idx - 1].isalnum()
                after_ok = idx + len(cue_l) >= len(lower) or not lower[idx + len(cue_l)].isalnum()
                if before_ok and after_ok:
                    # Sentence-bounded span (deterministic offsets into paragraph text)
                    left = text.rfind(".", 0, idx)
                    right = text.find(".", idx)
                    s = left + 1 if left >= 0 else 0
                    e = right + 1 if right >= 0 else len(text)
                    while s < e and text[s].isspace():
                        s += 1
                    span = text[s:e].strip()
                    rejected = False
                    reason = None
                    for pat in self.reject_patterns:
                        if pat.search(span):
                            rejected = True
                            reason = f"reject_pattern:{pat.pattern}"
                            break
                    conf = 0.55 if rejected else min(0.95, 0.6 + 0.05 * len(cue.split()))
                    found.append(
                        ObligationCandidate(
                            paragraph_id=row["paragraph_id"],
                            document_id=row["document_id"],
                            entity_class=row.get("entity_class", ""),
                            subject_family=row.get("subject_family", ""),
                            span_start=s,
                            span_end=e,
                            matched_cue=cue,
                            extraction_confidence=conf,
                            rejected=rejected,
                            rejection_reason=reason,
                            span_text=span,
                        )
                    )
                start = idx + len(cue_l)
        # Deduplicate identical cue@offset hits
        deduped: list[ObligationCandidate] = []
        seen: set[tuple[str, int, int]] = set()
        for c in found:
            key = (c.matched_cue, c.span_start, c.span_end)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(c)
        return deduped

    def _window(self, text: str, start: int, end: int, pad: int = 120) -> tuple[int, int, str]:
        # retained for compatibility; sentence spans preferred in extract_from_paragraph
        s = max(0, start - pad)
        e = min(len(text), end + pad)
        return s, e, text[s:e].strip()

    def run(self) -> dict[str, Any]:
        candidates: list[ObligationCandidate] = []
        for path in sorted(self.processed.glob("*.jsonl")):
            if path.name == "paragraphs_index.jsonl":
                continue
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    candidates.extend(self.extract_from_paragraph(row))

        out = self.out_dir / "obligation_candidates.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for c in candidates:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

        kept = [c for c in candidates if not c.rejected]
        rejected = [c for c in candidates if c.rejected]
        rate = (len(rejected) / len(candidates)) if candidates else 0.0
        self.logger.info(
            "Deontic candidates=%s kept=%s rejected=%s",
            len(candidates),
            len(kept),
            len(rejected),
        )
        return {
            "candidate_obligation_spans": len(kept),
            "candidate_spans_total_including_rejected": len(candidates),
            "candidate_rejection_rate": rate,
            "output_path": str(out),
        }
