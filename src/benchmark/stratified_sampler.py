"""Stratified sampler for T1 validation sample."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import load_config, resolve_path, setup_logging


class StratifiedSampler:
    def __init__(self, config: dict[str, Any] | None = None):
        self.cfg = config or load_config()
        self.logger = setup_logging("benchmark.sampler", self.cfg)
        self.cand_dir = resolve_path(self.cfg, "benchmark_candidate")
        self.val_dir = resolve_path(self.cfg, "benchmark_validated")
        self.reports = resolve_path(self.cfg, "reports")
        self.max_n = int(self.cfg.get("benchmark", {}).get("max_validation_sample", 30))

    def sample(self, seed: int = 42) -> dict[str, Any]:
        path = self.cand_dir / "t1_candidates.csv"
        if not path.exists():
            raise FileNotFoundError(f"Missing candidates: {path}")
        try:
            df = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(
                columns=[
                    "entity_class",
                    "subject_family",
                    "obligation_span_ref",
                    "paragraph_id",
                    "document_id",
                    "differential_flag",
                ]
            )
        if df.empty:
            sample = df
            reason = "candidate pool empty"
        else:
            # Stratify by differential_flag first, then entity_class
            groups = []
            for _, g in df.groupby(["differential_flag", "entity_class"], dropna=False):
                groups.append(g)
            # Round-robin take until max_n
            rng = __import__("random").Random(seed)
            order = list(range(len(groups)))
            rng.shuffle(order)
            picked_idx: list[int] = []
            # Convert each group to list of indices
            group_indices = [g.index.tolist() for g in groups]
            for gi in group_indices:
                rng.shuffle(gi)
            pointers = [0] * len(group_indices)
            while len(picked_idx) < min(self.max_n, len(df)):
                progressed = False
                for oi in order:
                    if pointers[oi] < len(group_indices[oi]) and len(picked_idx) < self.max_n:
                        picked_idx.append(group_indices[oi][pointers[oi]])
                        pointers[oi] += 1
                        progressed = True
                    if len(picked_idx) >= self.max_n:
                        break
                if not progressed:
                    break
            sample = df.loc[picked_idx].copy()
            reason = (
                f"Annotation capacity for this run capped at max_validation_sample="
                f"{self.max_n} (config). Stratified round-robin over "
                f"(differential_flag, entity_class). Not the dossier ~350–400 ceiling."
            )

        sample_path = self.cand_dir / "t1_validation_sample.csv"
        sample.to_csv(sample_path, index=False)

        # Annotation template: one file per annotator, blank labels
        annotators = self.cfg.get("benchmark", {}).get("annotators") or ["Akash", "Karan", "Meer"]
        ann_dir = self.val_dir / "annotation_templates"
        ann_dir.mkdir(parents=True, exist_ok=True)
        for name in annotators:
            tmpl = sample.copy()
            tmpl["annotator"] = name
            tmpl["applies_to_label"] = ""
            tmpl["differential_flag_label"] = ""  # shared | class-specific | absent
            tmpl["in_force_confirmed"] = ""
            tmpl["notes"] = ""
            tmpl["label_status"] = "pending_annotation"
            # Drop span text if present; keep refs only
            out = ann_dir / f"annotation_{name.lower()}.csv"
            tmpl.to_csv(out, index=False)

        instructions = self.val_dir / "annotation_instructions.md"
        instructions.write_text(
            "\n".join(
                [
                    "# T1 Annotation Instructions (Week 5)",
                    "",
                    "Annotators: Akash, Karan, Meer — label **independently**; do not share answers.",
                    "",
                    "## Fields to fill",
                    "",
                    "- `applies_to_label`: entity class(es) the obligation binds",
                    "- `differential_flag_label`: one of `shared` | `class-specific` | `absent`",
                    "- `in_force_confirmed`: yes/no/uncertain given temporal metadata",
                    "- `notes`: brief justification / ambiguity",
                    "",
                    "## Rules",
                    "",
                    "- Use the `obligation_span_ref` / `paragraph_id` to look up source text in",
                    "  `data/processed/{document_id}.jsonl` (local only).",
                    "- Do **not** invent obligations; if unclear, mark absent/uncertain in notes.",
                    "- Candidate flags in the sample are **not gold** — re-judge from source.",
                    "",
                    f"## Sample size rationale",
                    "",
                    reason,
                    "",
                ]
            ),
            encoding="utf-8",
        )

        # Empty validated file with headers if none validated yet
        validated_path = self.val_dir / "t1_validated.csv"
        if not validated_path.exists() or validated_path.stat().st_size == 0:
            cols = [
                "entity_class",
                "subject_family",
                "obligation_span_ref",
                "paragraph_id",
                "document_id",
                "applies_to",
                "differential_flag",
                "in_force_from",
                "in_force_to",
                "label_status",
                "annotators_agreeing",
                "fleiss_subset",
            ]
            pd.DataFrame(columns=cols).to_csv(validated_path, index=False)

        self.logger.info("Validation sample size=%s reason=%s", len(sample), reason)
        return {
            "candidate_pool_size": int(len(df)),
            "stratified_validation_sample_size": int(len(sample)),
            "sample_size_rationale": reason,
            "sample_path": str(sample_path),
            "annotation_templates_dir": str(ann_dir),
            "validated_path": str(validated_path),
            "validated_count": int(pd.read_csv(validated_path).shape[0])
            if validated_path.exists()
            else 0,
        }


def fleiss_kappa(ratings: list[list[int]], n_categories: int) -> float | str:
    """
    Compute Fleiss' kappa.
    ratings: list of items; each item is a list of category counts across annotators
             (length = n_categories), summing to n_annotators.
    Returns float, or message if insufficient data.
    """
    if not ratings:
        return "NOT YET MEASURED — annotation not yet completed"
    N = len(ratings)
    n = sum(ratings[0])
    if n < 2 or N < 1:
        return "NOT YET MEASURED — need ≥2 annotators"
    # P_i
    P = []
    for row in ratings:
        s = sum(v * v for v in row)
        P.append((s - n) / (n * (n - 1)))
    P_bar = sum(P) / N
    # p_j
    cols = [0] * n_categories
    for row in ratings:
        for j, v in enumerate(row):
            cols[j] += v
    p = [c / (N * n) for c in cols]
    P_e = sum(pj * pj for pj in p)
    if abs(1 - P_e) < 1e-12:
        return "NOT YET MEASURED — no category variance"
    return (P_bar - P_e) / (1 - P_e)


def try_compute_kappa_from_annotations(val_dir: Path) -> dict[str, Any]:
    """If completed annotation CSVs exist with labels, compute kappa; else NOT YET MEASURED."""
    ann_dir = val_dir / "annotation_templates"
    if not ann_dir.exists():
        return {
            "fleiss_kappa": "NOT YET MEASURED — annotation not yet completed",
            "items_annotated_by_ge_2": 0,
            "disagreement_categories": [],
        }
    files = sorted(ann_dir.glob("annotation_*.csv"))
    if len(files) < 2:
        return {
            "fleiss_kappa": "NOT YET MEASURED — annotation not yet completed",
            "items_annotated_by_ge_2": 0,
            "disagreement_categories": [],
        }
    frames = []
    for f in files:
        df = pd.read_csv(f)
        if "differential_flag_label" not in df.columns:
            continue
        # Only rows with non-empty labels count as completed
        labeled = df[df["differential_flag_label"].astype(str).str.len() > 0]
        if labeled.empty:
            continue
        frames.append(labeled[["paragraph_id", "differential_flag_label"]].assign(file=f.name))
    if len(frames) < 2:
        return {
            "fleiss_kappa": "NOT YET MEASURED — annotation not yet completed",
            "items_annotated_by_ge_2": 0,
            "disagreement_categories": [],
        }
    merged = None
    for i, fr in enumerate(frames):
        fr = fr.rename(columns={"differential_flag_label": f"lab_{i}"})
        merged = fr if merged is None else merged.merge(
            fr[["paragraph_id", f"lab_{i}"]], on="paragraph_id", how="inner"
        )
    lab_cols = [c for c in merged.columns if c.startswith("lab_")]
    cats = ["shared", "class-specific", "absent"]
    ratings = []
    disagreements = []
    for _, row in merged.iterrows():
        labels = [str(row[c]).strip().lower() for c in lab_cols]
        if any(l not in cats for l in labels):
            continue
        counts = [labels.count(c) for c in cats]
        ratings.append(counts)
        if len(set(labels)) > 1:
            disagreements.append(
                {"paragraph_id": row["paragraph_id"], "labels": labels, "field": "differential_flag"}
            )
    if not ratings:
        return {
            "fleiss_kappa": "NOT YET MEASURED — annotation not yet completed",
            "items_annotated_by_ge_2": 0,
            "disagreement_categories": [],
        }
    kappa = fleiss_kappa(ratings, n_categories=len(cats))
    return {
        "fleiss_kappa": kappa if isinstance(kappa, str) else round(float(kappa), 4),
        "items_annotated_by_ge_2": len(ratings),
        "disagreement_categories": disagreements,
    }
