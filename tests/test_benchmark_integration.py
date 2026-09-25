"""Integration test (P1-005, Section U): the solo protocol end-to-end.

keyword-heuristic candidate generation -> pass-1 task file -> ingest -> retest
-> blind pass 2 -> ingest -> adjudicate -> ingest -> report, run against a
small real slice of P1-001's committed paragraphs.

**The completed annotations here are fixtures, and exist only inside this
test.** They exercise the ingestion, retest, adjudication and promotion
machinery; they are never written into `data/benchmark/` and are not the
pilot's real annotations, which require Karan to sit down and label. The
report reflects that distinction — the real test-retest kappa stays NOT YET
MEASURED until the real passes are filled in.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.benchmark.annotation import (
    NOT_YET_MEASURED,
    ROUTE_NEEDS_ADJUDICATION,
    ROUTE_RETEST_CONSISTENT,
    TASK_FILE_COLUMNS,
    build_annotation_tasks,
    draw_retest_set,
    ingest_annotations,
    load_votes,
    measure_agreement,
    promote_validated,
    persist_candidates,
    route_counts,
)
from src.benchmark.pilot import extract_obligation_candidates
from src.common.io_helpers import read_jsonl
from src.common.paths import PathResolver
from src.schemas.benchmark import LabelStatus
from src.schemas.provenance import ParagraphRecord

from tests.test_benchmark_solo_protocol import seed_entity_classes

CFG = {
    "environment": {
        "mode": "local",
        "local": {"working_root": ".", "input_roots": []},
        "kaggle": {"working_root": "/kaggle/working", "input_root": "/kaggle/input", "input_datasets": []},
    },
    "paths": {
        k: k
        for k in ("raw", "extracted", "processed", "metadata", "matrix", "benchmark",
                  "evaluation", "cache", "reports", "logs")
    },
    "logging": {"level": "INFO", "format": "%(message)s", "to_file": False},
    "benchmark": {
        "primary_annotator": "karan",
        "second_raters": [],
        "promotion_policy": "single_expert_retest",
        "retest": {"min_gap_days": 5, "pilot_fraction": 1.0, "phase2_fraction": 0.20,
                   "shuffle_seed": 20260924},
        "agreement": {"bootstrap_seed": 20260924, "bootstrap_resamples": 100},
    },
}

FIXTURE_CLASSES = [
    "Commercial Banks",
    "Small Finance Banks",
    "Urban Co-operative Banks",
    "Non-Banking Financial Companies",
]


def _real_paragraphs(limit: int = 12) -> list[ParagraphRecord]:
    """A small slice of genuinely committed ParagraphRecords."""
    files = sorted(Path("data/processed").glob("md_*.jsonl"))
    if not files:
        pytest.skip("no committed processed paragraphs in this checkout")

    records: list[ParagraphRecord] = []
    for path in files:
        for row in read_jsonl(path):
            if (row.get("text") or "") and len(row["text"]) > 200:
                records.append(ParagraphRecord.from_dict(row))
            if len(records) >= limit:
                return records
    if not records:
        pytest.skip("no usable paragraphs found")
    return records


@pytest.fixture(scope="module")
def real_paragraphs():
    return _real_paragraphs()


def _resolver(tmp_path):
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)
    seed_entity_classes(resolver, FIXTURE_CLASSES)
    return resolver


def _complete_task_file(path: str, *, applies_to: str, flag: str, only=None) -> None:
    """Fill a task file in place. ``only`` limits which label_ids get filled."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if only is not None and row["label_id"] not in only:
            continue
        row["applies_to"] = applies_to
        row["differential_flag"] = flag
        row["applies_to_rationale"] = "fixture annotation for integration test"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def test_pilot_extracts_candidates_from_real_paragraphs(real_paragraphs):
    labels = extract_obligation_candidates(real_paragraphs, CFG)
    assert labels, "keyword heuristic found no obligations in real RBI text"
    for label in labels:
        assert label.obligation_span is not None
        assert label.obligation_span.text
        assert label.obligation_span.matched_cue
        assert label.validate() == []


def test_pilot_candidates_assert_nothing_about_applicability(real_paragraphs):
    for label in extract_obligation_candidates(real_paragraphs, CFG):
        assert label.applies_to == []
        assert label.differential_flag == "unlabelled"
        assert label.label_status == LabelStatus.CANDIDATE.value
        assert label.agreement_score is None


def test_pilot_spans_index_into_their_paragraph(real_paragraphs):
    """Offsets must resolve against the real paragraph text they came from."""
    by_id = {p.paragraph_id: p for p in real_paragraphs}
    for label in extract_obligation_candidates(real_paragraphs, CFG):
        span = label.obligation_span
        source = by_id[span.paragraph_id].text
        assert source[span.char_start : span.char_end].strip() == span.text


def test_solo_protocol_end_to_end_through_the_cli(tmp_path, real_paragraphs, monkeypatch):
    """§U: candidates -> pass 1 -> retest -> pass 2 -> adjudicate -> report.

    Driven through `scripts/run_annotation.py` rather than the library, because
    the stages' guards, the annotation log and the metrics files are part of
    what is being tested.
    """
    import json

    import scripts.run_annotation as cli

    resolver = _resolver(tmp_path)

    class _Rooted:
        @staticmethod
        def from_config(cfg, **kwargs):
            return PathResolver.from_config(CFG, repo_root=tmp_path)

    monkeypatch.setattr(cli, "load_config", lambda _path=None: CFG)
    monkeypatch.setattr(cli, "PathResolver", _Rooted)

    # 1. candidates
    candidates = extract_obligation_candidates(real_paragraphs, CFG)
    assert len(candidates) >= 4, "need a few items to split across routes"
    persist_candidates(candidates, CFG, resolver=resolver)
    task_files = build_annotation_tasks(candidates, CFG, resolver=resolver)
    assert set(task_files) == {"karan"}
    drawn = draw_retest_set(candidates, 1.0, 20260924, resolver=resolver)
    assert len(drawn["label_ids"]) == len(candidates)

    # 2. pass-1 CSV
    ids = [lbl.label_id for lbl in candidates]
    agree_ids, differ_ids = set(ids[: len(ids) // 2]), set(ids[len(ids) // 2 :])
    _complete_task_file(task_files["karan"], applies_to="Commercial Banks", flag="shared")

    # 3. ingest --pass 1 --minutes karan=30
    assert cli.main(["ingest", "--pass", "1", "--minutes", "karan=30"]) == 0

    # 4. retest --allow-short-gap (pass 1 was ingested seconds ago)
    assert cli.main(["retest", "--allow-short-gap"]) == 0
    pass2_path = resolver.write_path("benchmark", "tasks", "annotation_karan_pass2.csv")
    assert pass2_path.exists()

    # 5. fill the pass-2 fixture: half consistent, half a changed judgment
    _complete_task_file(pass2_path, applies_to="Commercial Banks", flag="shared", only=agree_ids)
    _complete_task_file(
        pass2_path, applies_to="Small Finance Banks", flag="class-specific", only=differ_ids
    )

    # 6. ingest --pass 2
    assert cli.main(["ingest", "--pass", "2", "--minutes", "karan=25"]) == 0

    # 7. adjudicate
    assert cli.main(["adjudicate"]) == 0
    adjudication_path = resolver.write_path("benchmark", "tasks", "adjudication_karan.csv")
    assert adjudication_path.exists()

    with open(adjudication_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames)
        adj_rows = list(reader)
    assert {r["label_id"] for r in adj_rows} == differ_ids
    for row in adj_rows:
        row["final_applies_to"] = "Commercial Banks"
        row["final_differential_flag"] = "shared"
        row["adjudication_rationale"] = "Re-read the span; pass 1 was right."
    with open(adjudication_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(adj_rows)

    # 8. ingest --adjudication
    assert cli.main(["ingest", "--adjudication"]) == 0

    # 9. report
    task_bytes = {
        path.name: path.read_bytes()
        for path in sorted(resolver.write_dir("benchmark", create=False).glob("tasks/*.csv"))
    }
    assert cli.main(["report"]) == 0

    # -- assertions ----------------------------------------------------------
    metrics = json.loads(
        resolver.write_path("reports", "phase1_annotation_ingest_metrics.json").read_text()
    )

    for key in (
        "protocol", "primary_annotator", "items_total", "items_validated",
        "retest_set_size", "route_counts", "passes", "agreement",
        "tautology_smell", "tautology_share_by_rater", "disagreements_path",
    ):
        assert key in metrics, f"missing metric key: {key}"

    for key in (
        "test_retest", "second_rater", "unlabelled_votes", "primary_annotator",
    ):
        assert key in metrics["agreement"], f"missing agreement key: {key}"

    retest_block = metrics["agreement"]["test_retest"]
    for key in (
        "n_items", "cohen_kappa_flag", "cohen_kappa_flag_excl_unlabelled",
        "raw_flag_agreement", "applies_to_exact_match_rate", "applies_to_mean_jaccard",
        "kappa_bootstrap_ci95", "not_obligation_consistency", "disagreement_categories",
    ):
        assert key in retest_block, f"missing test_retest key: {key}"

    # Route counts account for every item exactly once.
    assert sum(metrics["route_counts"].values()) == len(candidates)
    assert metrics["route_counts"].get(ROUTE_RETEST_CONSISTENT) == len(agree_ids)
    assert metrics["route_counts"].get("adjudicated") == len(differ_ids)
    assert metrics["items_total"] == len(candidates)

    # Both passes were recorded, not just the last one.
    assert set(metrics["passes"]) == {"karan:pass1", "karan:pass2"}

    # The disagreements CSV carries no RBI text.
    with open(metrics["disagreements_path"], newline="", encoding="utf-8") as handle:
        disagreement_columns = list(csv.DictReader(handle).fieldnames)
    assert "span_text" not in disagreement_columns
    assert "label_id" in disagreement_columns and "category" in disagreement_columns

    # No numeric Fleiss' kappa can exist with one rater.
    assert "fleiss" not in json.dumps(metrics["agreement"]).lower()

    # `report` touched nothing under data/benchmark/.
    after = {
        path.name: path.read_bytes()
        for path in sorted(resolver.write_dir("benchmark", create=False).glob("tasks/*.csv"))
    }
    assert after == task_bytes, "report must not rewrite task files"


def test_no_label_reaches_validated_without_a_validating_route(tmp_path, real_paragraphs):
    """§U's core assertion, on real-derived candidates.

    Every item is in the retest set and pass 2 has not happened, so every item
    is `pass1-only` and nothing may promote — however confident pass 1 was.
    """
    resolver = _resolver(tmp_path)
    candidates = extract_obligation_candidates(real_paragraphs, CFG)
    persist_candidates(candidates, CFG, resolver=resolver)
    task_files = build_annotation_tasks(candidates, CFG, resolver=resolver)
    _complete_task_file(task_files["karan"], applies_to="Commercial Banks", flag="shared")

    retest_ids = {lbl.label_id for lbl in candidates}
    promoted = ingest_annotations(
        CFG, candidates=candidates, resolver=resolver, retest_ids=retest_ids
    )

    assert all(not label.is_validated for label in promoted)
    assert all(label.label_status != LabelStatus.VALIDATED.value for label in promoted)


def test_unannotated_pilot_reports_agreement_as_the_sentinel(tmp_path, real_paragraphs):
    """The state the real pilot is actually in: task file generated, nobody has
    annotated yet. Agreement must be the exact sentinel string."""
    resolver = _resolver(tmp_path)
    candidates = extract_obligation_candidates(real_paragraphs, CFG)
    persist_candidates(candidates, CFG, resolver=resolver)
    build_annotation_tasks(candidates, CFG, resolver=resolver)

    votes = load_votes(CFG, candidates=candidates, resolver=resolver)
    agreement = measure_agreement(votes, CFG)

    assert agreement["test_retest"]["status"].startswith(NOT_YET_MEASURED)
    assert agreement["test_retest"]["n_items"] == 0
    assert agreement["second_rater"]["status"] == f"{NOT_YET_MEASURED} — no second rater configured"

    promoted = ingest_annotations(CFG, candidates=candidates, resolver=resolver)
    assert all(not label.is_validated for label in promoted)


def test_a_consistent_retest_validates_the_whole_set(tmp_path, real_paragraphs):
    resolver = _resolver(tmp_path)
    candidates = extract_obligation_candidates(real_paragraphs, CFG)[:3]
    persist_candidates(candidates, CFG, resolver=resolver)
    task_files = build_annotation_tasks(candidates, CFG, resolver=resolver)

    _complete_task_file(task_files["karan"], applies_to="Commercial Banks", flag="shared")
    pass2 = resolver.write_path("benchmark", "tasks", "annotation_karan_pass2.csv")
    pass2.write_bytes(Path(task_files["karan"]).read_bytes())

    promoted = ingest_annotations(
        CFG, candidates=candidates, resolver=resolver,
        retest_ids={lbl.label_id for lbl in candidates},
    )

    assert all(label.is_validated for label in promoted)
    assert route_counts(promoted) == {ROUTE_RETEST_CONSISTENT: len(candidates)}
    for label in promoted:
        assert label.validate() == []
        assert label.applies_to  # non-empty, annotator-sourced
        assert label.differential_flag != "unlabelled"
        assert label.agreement_score == 1.0


def test_a_contradicted_retest_validates_nothing(tmp_path, real_paragraphs):
    """The audit's never-agree simulation, end to end on real-derived items."""
    resolver = _resolver(tmp_path)
    candidates = extract_obligation_candidates(real_paragraphs, CFG)[:3]
    persist_candidates(candidates, CFG, resolver=resolver)
    task_files = build_annotation_tasks(candidates, CFG, resolver=resolver)

    _complete_task_file(task_files["karan"], applies_to="Commercial Banks", flag="shared")
    pass2 = resolver.write_path("benchmark", "tasks", "annotation_karan_pass2.csv")
    pass2.write_bytes(Path(task_files["karan"]).read_bytes())
    _complete_task_file(pass2, applies_to="Small Finance Banks", flag="absent")

    promoted = ingest_annotations(
        CFG, candidates=candidates, resolver=resolver,
        retest_ids={lbl.label_id for lbl in candidates},
    )

    assert all(not label.is_validated for label in promoted)
    assert route_counts(promoted) == {ROUTE_NEEDS_ADJUDICATION: len(candidates)}
