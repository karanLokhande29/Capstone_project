"""Tests for segmenter, deontic extractor, fleiss helper."""

from src.preprocessing.segmenter import split_paragraphs, stable_paragraph_id
from src.benchmark.deontic_extractor import DeonticExtractor
from src.benchmark.stratified_sampler import fleiss_kappa


def test_stable_paragraph_id_deterministic():
    assert stable_paragraph_id("md_1", 3) == "md_1::p00003"
    assert stable_paragraph_id("md_1", 3) == stable_paragraph_id("md_1", 3)


def test_split_paragraphs():
    text = "First paragraph has enough characters to pass.\n\nSecond paragraph also has enough characters here."
    parts = split_paragraphs(text, min_chars=20)
    assert len(parts) == 2


def test_deontic_extract_and_reject():
    ext = DeonticExtractor(
        config={
            "paths": {
                "raw": "data/raw",
                "extracted": "data/extracted",
                "processed": "data/processed",
                "metadata": "data/metadata",
                "matrix": "data/matrix",
                "benchmark_candidate": "data/benchmark/candidate",
                "benchmark_validated": "data/benchmark/validated",
                "reports": "reports",
                "logs": "reports/logs",
            },
            "deontic": {
                "cues": ["shall not", "shall", "must"],
                "reject_patterns": [r"(?i)\bshall\s+mean\b"],
            },
            "logging": {"level": "INFO"},
        }
    )
    row = {
        "paragraph_id": "md_1::p00000",
        "document_id": "md_1",
        "entity_class": "Commercial Banks",
        "subject_family": "KYC",
        "text": "Banks shall maintain records. For this Direction, KYC shall mean the process. Banks must not open anonymous accounts.",
    }
    cands = ext.extract_from_paragraph(row)
    assert any(c.matched_cue == "shall" and not c.rejected for c in cands)
    assert any(c.rejected for c in cands) or any("shall mean" in c.span_text.lower() for c in cands)
    assert any(c.matched_cue in {"must", "shall not"} or "must not" in c.matched_cue for c in cands)


def test_fleiss_kappa_perfect_agreement():
    # 2 items, 3 annotators, 3 categories; all agree on cat0 then cat1
    ratings = [
        [3, 0, 0],
        [0, 3, 0],
    ]
    k = fleiss_kappa(ratings, 3)
    assert isinstance(k, float)
    assert k == 1.0


def test_fleiss_not_measured_empty():
    assert "NOT YET MEASURED" in str(fleiss_kappa([], 3))
