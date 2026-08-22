"""Assemble T1 candidate benchmark items from deontic + cross-class outputs."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import load_config, resolve_path, setup_logging


class T1CandidateBuilder:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("benchmark.t1", self.cfg)
        self.cand_dir = resolve_path(self.cfg, "benchmark_candidate")
        self.meta = resolve_path(self.cfg, "metadata")

    def run(self) -> dict[str, Any]:
        obligations_path = self.cand_dir / "obligation_candidates.jsonl"
        matches_path = self.cand_dir / "cross_class_matches.jsonl"
        temporal_path = self.meta / "temporal_metadata.json"

        temporal = {}
        if temporal_path.exists():
            temporal = {
                r["document_id"]: r for r in json.loads(temporal_path.read_text(encoding="utf-8"))
            }

        # Map paragraph -> best differential flag from matches
        para_flags: dict[str, str] = {}
        if matches_path.exists():
            with matches_path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    m = json.loads(line)
                    for pid in (m.get("paragraph_id_a"), m.get("paragraph_id_b")):
                        if not pid:
                            continue
                        # Prefer class-specific over shared over absent when multiple
                        prev = para_flags.get(pid)
                        flag = m.get("differential_flag", "absent")
                        rank = {"class-specific": 2, "shared": 1, "absent": 0}
                        if prev is None or rank.get(flag, 0) > rank.get(prev, 0):
                            para_flags[pid] = flag

        rows: list[dict[str, Any]] = []
        with obligations_path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                c = json.loads(line)
                if c.get("rejected"):
                    continue
                did = c["document_id"]
                t = temporal.get(did, {})
                rows.append(
                    {
                        "entity_class": c.get("entity_class"),
                        "subject_family": c.get("subject_family"),
                        "obligation_span_ref": f"{c['paragraph_id']}@{c['span_start']}:{c['span_end']}",
                        "paragraph_id": c["paragraph_id"],
                        "document_id": did,
                        "span_start": c["span_start"],
                        "span_end": c["span_end"],
                        "matched_cue": c.get("matched_cue"),
                        "applies_to": c.get("entity_class"),
                        "differential_flag": para_flags.get(c["paragraph_id"], "absent"),
                        "in_force_from": t.get("in_force_from"),
                        "in_force_to": None,
                        "update_date_stamp": t.get("update_date_stamp"),
                        "extraction_confidence": c.get("extraction_confidence"),
                        "label_status": "candidate",
                        "provenance": "deontic_extractor+cross_class_matcher",
                    }
                )

        out_csv = self.cand_dir / "t1_candidates.csv"
        out_jsonl = self.cand_dir / "t1_candidates.jsonl"
        df = pd.DataFrame(rows)
        df.to_csv(out_csv, index=False)
        with out_jsonl.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        by_flag = df["differential_flag"].value_counts().to_dict() if len(df) else {}
        by_class = df["entity_class"].value_counts().to_dict() if len(df) else {}
        self.logger.info("T1 candidates written: %s", len(rows))
        return {
            "t1_candidate_count": len(rows),
            "differential_flag_distribution": by_flag,
            "entity_class_distribution": by_class,
            "output_csv": str(out_csv),
            "output_jsonl": str(out_jsonl),
        }
