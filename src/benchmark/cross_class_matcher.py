"""Cross-class CANDIDATE semantic matching of obligation spans (bounded)."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.utils import load_config, resolve_path, setup_logging


def _normalize_for_match(text: str) -> str:
    t = text.lower()
    for ent in [
        "commercial banks",
        "small finance banks",
        "payments banks",
        "local area banks",
        "regional rural banks",
        "urban co-operative banks",
        "rural co-operative banks",
        "non-banking financial companies",
        "asset reconstruction companies",
        "credit information companies",
        "all india financial institutions",
    ]:
        t = t.replace(ent, " ENTITY ")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def token_jaccard(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


@dataclass
class CrossClassMatch:
    subject_family: str
    entity_class_a: str
    entity_class_b: str
    paragraph_id_a: str
    paragraph_id_b: str
    similarity: float
    differential_flag: str  # shared | class-specific | absent — CANDIDATE
    match_level: str  # paragraph | section
    label_status: str = "candidate"


class CrossClassMatcher:
    def __init__(self, config: dict[str, Any] | None = None, match_level: str = "paragraph"):
        self.cfg = config or load_config()
        self.logger = setup_logging("benchmark.cross_class", self.cfg)
        self.out_dir = resolve_path(self.cfg, "benchmark_candidate")
        self.match_level = match_level
        self.sim_threshold_shared = 0.55
        self.sim_threshold_related = 0.35
        # Hard caps so matching stays tractable on laptop (not research novelty — engineering bound)
        self.max_per_entity = 40
        self.max_compare_pairs_per_entity_pair = 800

    def _section_key(self, text: str) -> str:
        norm = _normalize_for_match(text)
        return " ".join(norm.split()[:8])

    def _prep(self, item: dict[str, Any]) -> dict[str, Any]:
        text = item.get("span_text") or ""
        if self.match_level == "section":
            key = self._section_key(text)
        else:
            key = _normalize_for_match(text)
        return {**item, "_norm": key}

    def run(
        self,
        candidates_path: Path | None = None,
        alignment_rate: float | None = None,
    ) -> dict[str, Any]:
        if alignment_rate is not None and alignment_rate < 0.60:
            self.match_level = "section"
            self.logger.warning(
                "Alignment rate %.3f < 0.60 — using section-level matching", alignment_rate
            )

        path = candidates_path or (self.out_dir / "obligation_candidates.jsonl")
        cands: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("rejected"):
                    continue
                cands.append(row)

        by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for c in cands:
            by_subject[c.get("subject_family") or ""].append(c)

        matches: list[CrossClassMatch] = []
        for subject, items in by_subject.items():
            if not subject:
                continue
            by_ent: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for it in items:
                by_ent[it.get("entity_class") or "UNKNOWN"].append(it)

            # Cap + prefer higher-confidence spans
            for ent, lst in list(by_ent.items()):
                lst_sorted = sorted(
                    lst, key=lambda x: float(x.get("extraction_confidence") or 0), reverse=True
                )
                by_ent[ent] = [self._prep(x) for x in lst_sorted[: self.max_per_entity]]

            entities = sorted(by_ent.keys())
            for i, ea in enumerate(entities):
                for eb in entities[i + 1 :]:
                    best = (0.0, None, None)
                    compares = 0
                    # Block by first 3 tokens to avoid full Cartesian when possible
                    buckets_a: dict[str, list[dict[str, Any]]] = defaultdict(list)
                    for a in by_ent[ea]:
                        prefix = " ".join((a.get("_norm") or "").split()[:3]) or "_"
                        buckets_a[prefix].append(a)
                    for b in by_ent[eb]:
                        prefix = " ".join((b.get("_norm") or "").split()[:3]) or "_"
                        pool = buckets_a.get(prefix) or by_ent[ea]
                        for a in pool:
                            compares += 1
                            if compares > self.max_compare_pairs_per_entity_pair:
                                break
                            sim = token_jaccard(a.get("_norm") or "", b.get("_norm") or "")
                            if sim > best[0]:
                                best = (sim, a, b)
                        if compares > self.max_compare_pairs_per_entity_pair:
                            break
                    sim, a, b = best
                    if a is None or b is None:
                        continue
                    if sim >= self.sim_threshold_shared:
                        flag = "shared"
                    elif sim >= self.sim_threshold_related:
                        flag = "class-specific"
                    else:
                        flag = "absent"
                    matches.append(
                        CrossClassMatch(
                            subject_family=subject,
                            entity_class_a=ea,
                            entity_class_b=eb,
                            paragraph_id_a=a["paragraph_id"],
                            paragraph_id_b=b["paragraph_id"],
                            similarity=round(sim, 4),
                            differential_flag=flag,
                            match_level=self.match_level,
                        )
                    )

        out = self.out_dir / "cross_class_matches.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for m in matches:
                f.write(json.dumps(asdict(m), ensure_ascii=False) + "\n")

        by_flag: dict[str, int] = defaultdict(int)
        for m in matches:
            by_flag[m.differential_flag] += 1

        self.logger.info(
            "Cross-class candidate matches=%s level=%s by_flag=%s",
            len(matches),
            self.match_level,
            dict(by_flag),
        )
        return {
            "cross_class_candidate_matches": len(matches),
            "matches_by_differential_flag": dict(by_flag),
            "match_level_used": self.match_level,
            "output_path": str(out),
            "matcher_caps": {
                "max_per_entity": self.max_per_entity,
                "max_compare_pairs_per_entity_pair": self.max_compare_pairs_per_entity_pair,
            },
        }
