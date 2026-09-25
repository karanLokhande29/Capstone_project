"""P1-005 §T: the Single-Expert Annotation Protocol, and the defects it repairs.

Every test here exists because the superseded three-annotator tooling got the
corresponding case wrong in a way that would have reached the paper:

* an audit simulation where three annotators never agreed on anything scored
  Fleiss' κ = 1.0 and promoted all 18 items, because each annotator's row
  overwrote the last and κ then counted the single survivor once per annotator
  (tests 1, 2, 5);
* `pilot`, `all` and `report` each rewrote every task file blank, and
  `data/benchmark/**` is gitignored (tests 8, 9);
* a UTF-8 BOM from Excel's "CSV UTF-8" export broke the header check, and
  `applies_to` names were never validated (tests 10, 11);
* "entity classes spanned: 16" counted the paragraphs searched, not the 11
  classes the 18 items actually span (test 14).

Fixtures only, no network, and nothing here writes to the real
`data/benchmark/`.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.benchmark.annotation import (
    ROUTE_ADJUDICATED,
    ROUTE_NEEDS_ADJUDICATION,
    ROUTE_NOT_OBLIGATION,
    ROUTE_PASS1_ONLY,
    ROUTE_RETEST_CONSISTENT,
    ROUTE_SINGLE_PASS,
    TASK_FILE_COLUMNS,
    VOTE_BLANK,
    VOTE_NOT_OBLIGATION,
    VOTE_VOTED,
    AnnotationError,
    append_annotation_log,
    build_adjudication_tasks,
    build_annotation_tasks,
    build_pass2_tasks,
    cohen_kappa,
    draw_retest_set,
    label_route,
    load_adjudications,
    load_votes,
    make_candidate,
    measure_agreement,
    merge_votes,
    persist_candidates,
    promote_validated,
    route_counts,
    tautology_share_by_rater,
)
from src.benchmark.pilot import item_coverage_metrics
from src.common.paths import PathResolver
from src.schemas.benchmark import LabelStatus, ObligationSpan

CLASSES = ["Commercial Banks", "Small Finance Banks", "Urban Co-operative Banks"]

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
        "retest": {
            "min_gap_days": 5,
            "pilot_fraction": 1.0,
            "phase2_fraction": 0.20,
            "shuffle_seed": 20260924,
        },
        "agreement": {"bootstrap_seed": 20260924, "bootstrap_resamples": 200},
    },
}


def _cfg(**benchmark_overrides):
    return {**CFG, "benchmark": {**CFG["benchmark"], **benchmark_overrides}}


def seed_entity_classes(resolver: PathResolver, names=CLASSES) -> Path:
    """Write the discovered entity-class vocabulary the ingest validates against."""
    path = resolver.write_path("metadata", "entity_classes.json")
    path.write_text(
        json.dumps(
            {
                "kind": "entity_class",
                "term_count": len(names),
                "terms": [{"canonical_name": n, "kind": "entity_class"} for n in names],
            }
        ),
        encoding="utf-8",
    )
    return path


def _candidates(n=6, cfg=CFG, resolver=None):
    labels = []
    for i in range(n):
        span = ObligationSpan(
            paragraph_id=f"md_1::p{i:05d}", document_id="md_1",
            char_start=0, char_end=40,
            text=f"Banks shall maintain record {i}.", matched_cue="shall",
        )
        labels.append(
            make_candidate(
                f"t1_{i:04d}", span,
                entity_class=CLASSES[i % len(CLASSES)], subject_family="KYC",
                provenance="pilot:keyword_heuristic_v1",
            )
        )
    if resolver is not None:
        persist_candidates(labels, cfg, resolver=resolver)
    return labels


def _write_pass(resolver, labels, *, rater="karan", pass_no=1, rows, encoding="utf-8", newline="\n"):
    """Write a task file. ``rows`` maps label_id -> dict of annotator columns."""
    name = f"annotation_{rater}.csv" if pass_no == 1 else f"annotation_{rater}_pass{pass_no}.csv"
    path = resolver.write_path("benchmark", "tasks", name)
    out = []
    for label in labels:
        filled = rows.get(label.label_id, {})
        out.append(
            {
                "label_id": label.label_id,
                "paragraph_id": label.obligation_span.paragraph_id,
                "document_id": label.obligation_span.document_id,
                "context_entity_class": label.entity_class or "",
                "context_subject_family": label.subject_family or "",
                "span_text": label.obligation_span.text or "",
                "matched_cue": label.obligation_span.matched_cue or "",
                "applies_to": filled.get("applies_to", ""),
                "applies_to_rationale": filled.get("applies_to_rationale", ""),
                "differential_flag": filled.get("differential_flag", ""),
                "notes": filled.get("notes", ""),
            }
        )
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS), lineterminator=newline)
        writer.writeheader()
        writer.writerows(out)
    return path


def _vote(applies_to="Commercial Banks", flag="shared", rationale="because", notes=""):
    return {
        "applies_to": applies_to,
        "differential_flag": flag,
        "applies_to_rationale": rationale,
        "notes": notes,
    }


@pytest.fixture
def env(tmp_path):
    """A resolver rooted at tmp_path with the vocabulary and a retest set drawn."""
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)
    seed_entity_classes(resolver)
    return resolver


def _ingest(resolver, labels, cfg=CFG, *, retest_ids=None, adjudications=None):
    votes = load_votes(cfg, candidates=labels, resolver=resolver)
    if retest_ids is None:
        retest_ids = {lbl.label_id for lbl in labels}
    merged = merge_votes(
        labels, votes, cfg, retest_ids=retest_ids, adjudications=adjudications or {}
    )
    return votes, promote_validated(merged, cfg)


# -- 1. retest never agrees ---------------------------------------------------


def test_retest_that_never_agrees_yields_a_low_kappa_and_promotes_nothing(env):
    """The audit's simulation, as a regression test.

    Under the superseded tooling three annotators who never agreed scored
    Fleiss' κ = 1.0 and every item was promoted, because each row overwrote the
    last and κ counted the single survivor once per annotator.
    """
    labels = _candidates(6, resolver=env)
    flags_p1 = ["shared", "class-specific", "absent", "shared", "class-specific", "absent"]
    flags_p2 = ["class-specific", "absent", "shared", "absent", "shared", "class-specific"]

    _write_pass(env, labels, pass_no=1, rows={
        lbl.label_id: _vote(flag=flags_p1[i]) for i, lbl in enumerate(labels)
    })
    _write_pass(env, labels, pass_no=2, rows={
        lbl.label_id: _vote(flag=flags_p2[i]) for i, lbl in enumerate(labels)
    })

    votes, promoted = _ingest(env, labels)
    agreement = measure_agreement(votes, CFG)
    kappa = agreement["test_retest"]["cohen_kappa_flag"]

    assert isinstance(kappa, float), f"kappa must be a real number, got {kappa!r}"
    assert kappa < 0.2, f"passes that never agree must not score {kappa}"

    assert sum(1 for lbl in promoted if lbl.is_validated) == 0
    assert all(label_route(lbl) == ROUTE_NEEDS_ADJUDICATION for lbl in promoted)
    assert all(lbl.label_status == LabelStatus.IN_REVIEW.value for lbl in promoted)


def test_retest_that_never_agrees_records_zero_agreement_per_item(env):
    labels = _candidates(4, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote(flag="shared") for lbl in labels})
    _write_pass(env, labels, pass_no=2, rows={
        lbl.label_id: _vote(flag="absent") for lbl in labels
    })
    _, promoted = _ingest(env, labels)
    assert all(lbl.agreement_score == 0.0 for lbl in promoted)


# -- 2. retest agrees ---------------------------------------------------------


def test_retest_agreement_with_varied_flags_gives_kappa_one_and_validates(env):
    labels = _candidates(6, resolver=env)
    flags = ["shared", "class-specific", "absent", "shared", "class-specific", "absent"]
    rows = {lbl.label_id: _vote(flag=flags[i]) for i, lbl in enumerate(labels)}

    _write_pass(env, labels, pass_no=1, rows=rows)
    _write_pass(env, labels, pass_no=2, rows=rows)

    votes, promoted = _ingest(env, labels)
    agreement = measure_agreement(votes, CFG)

    assert agreement["test_retest"]["cohen_kappa_flag"] == pytest.approx(1.0)
    assert agreement["test_retest"]["n_items"] == 6
    assert agreement["test_retest"]["applies_to_exact_match_rate"] == pytest.approx(1.0)
    assert all(label_route(lbl) == ROUTE_RETEST_CONSISTENT for lbl in promoted)
    assert all(lbl.is_validated for lbl in promoted)
    assert all(lbl.validate() == [] for lbl in promoted)
    assert all(lbl.agreement_score == 1.0 for lbl in promoted)


def test_identical_retest_reports_a_bootstrap_interval_or_says_why_not(env):
    labels = _candidates(6, resolver=env)
    flags = ["shared", "class-specific", "absent", "shared", "class-specific", "absent"]
    rows = {lbl.label_id: _vote(flag=flags[i]) for i, lbl in enumerate(labels)}
    _write_pass(env, labels, pass_no=1, rows=rows)
    _write_pass(env, labels, pass_no=2, rows=rows)

    votes, _ = _ingest(env, labels)
    ci = measure_agreement(votes, CFG)["test_retest"]["kappa_bootstrap_ci95"]

    assert ci["resamples_used"] + ci["resamples_skipped_undefined"] == 200
    # Resamples that land on one category are undefined, not zero.
    if ci["ci95"] != "NOT YET MEASURED":
        assert ci["ci95"][0] <= ci["ci95"][1]


# -- 3. blank row in pass 2 ---------------------------------------------------


def test_blank_pass2_row_leaves_the_item_pass1_only_and_out_of_n(env):
    labels = _candidates(4, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})
    # The last item is left untouched in pass 2.
    _write_pass(env, labels, pass_no=2, rows={
        lbl.label_id: _vote() for lbl in labels[:-1]
    })

    votes, promoted = _ingest(env, labels)  # must not raise
    by_id = {lbl.label_id: lbl for lbl in promoted}

    assert label_route(by_id[labels[-1].label_id]) == ROUTE_PASS1_ONLY
    assert by_id[labels[-1].label_id].label_status == LabelStatus.IN_REVIEW.value
    assert measure_agreement(votes, CFG)["test_retest"]["n_items"] == 3

    blank = [v for v in votes if v.status == VOTE_BLANK]
    assert len(blank) == 1 and blank[0].pass_no == 2


# -- 4. not an obligation -----------------------------------------------------


def test_not_obligation_in_both_passes_is_rejected_not_validated(env):
    labels = _candidates(3, resolver=env)
    rows = {
        lbl.label_id: {"applies_to": "", "differential_flag": "", "applies_to_rationale": "",
                       "notes": "definitional, not an obligation"}
        for lbl in labels
    }
    _write_pass(env, labels, pass_no=1, rows=rows)
    _write_pass(env, labels, pass_no=2, rows=rows)

    votes, promoted = _ingest(env, labels)

    assert all(v.status == VOTE_NOT_OBLIGATION for v in votes)
    assert all(lbl.label_status == LabelStatus.REJECTED.value for lbl in promoted)
    assert all(label_route(lbl) == ROUTE_NOT_OBLIGATION for lbl in promoted)
    assert all(lbl.applies_to == [] for lbl in promoted)
    assert all(lbl.differential_flag == "unlabelled" for lbl in promoted)


def test_not_obligation_outside_the_retest_set_is_rejected_on_pass_one(env):
    labels = _candidates(2, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={
        lbl.label_id: {"applies_to": "", "differential_flag": "", "applies_to_rationale": "",
                       "notes": "commencement clause"}
        for lbl in labels
    })
    _, promoted = _ingest(env, labels, retest_ids=set())
    assert all(label_route(lbl) == ROUTE_NOT_OBLIGATION for lbl in promoted)
    assert all(lbl.label_status == LabelStatus.REJECTED.value for lbl in promoted)


# -- 5. a second rater disagrees ----------------------------------------------


def test_second_rater_disagreement_blocks_an_otherwise_consistent_retest(env):
    cfg = _cfg(second_raters=["akash"])
    labels = _candidates(3, resolver=env)
    rows = {lbl.label_id: _vote(flag="shared") for lbl in labels}

    _write_pass(env, labels, pass_no=1, rows=rows)
    _write_pass(env, labels, pass_no=2, rows=rows)
    # Same items, a different call on the middle one.
    second = dict(rows)
    second[labels[1].label_id] = _vote(applies_to="Small Finance Banks", flag="class-specific")
    _write_pass(env, labels, rater="akash", pass_no=1, rows=second)

    votes = load_votes(cfg, candidates=labels, resolver=env)
    merged = merge_votes(labels, votes, cfg, retest_ids={lbl.label_id for lbl in labels})
    promoted = promote_validated(merged, cfg)
    by_id = {lbl.label_id: lbl for lbl in promoted}

    assert label_route(by_id[labels[1].label_id]) == ROUTE_NEEDS_ADJUDICATION
    assert not by_id[labels[1].label_id].is_validated
    # The items the second rater agreed on are unaffected.
    assert by_id[labels[0].label_id].is_validated
    assert label_route(by_id[labels[0].label_id]) == ROUTE_RETEST_CONSISTENT


# -- 6. adjudication ----------------------------------------------------------


def _fill_adjudication(path, updates):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames)
        rows = list(reader)
    for row in rows:
        row.update(updates.get(row["label_id"], {}))
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _disagreeing_pilot(env, n=2):
    labels = _candidates(n, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote(flag="shared") for lbl in labels})
    _write_pass(env, labels, pass_no=2, rows={lbl.label_id: _vote(flag="absent") for lbl in labels})
    votes, promoted = _ingest(env, labels)
    return labels, votes, promoted


def test_adjudication_with_a_rationale_validates_via_the_adjudicated_route(env):
    labels, votes, promoted = _disagreeing_pilot(env)
    result = build_adjudication_tasks(promoted, votes, CFG, resolver=env)
    assert result["items"] == len(labels)

    _fill_adjudication(result["path"], {
        lbl.label_id: {
            "final_applies_to": "Commercial Banks;Small Finance Banks",
            "final_differential_flag": "shared",
            "adjudication_rationale": "Re-read the span; it names both classes explicitly.",
        }
        for lbl in labels
    })

    adjudications = load_adjudications(CFG, candidates=labels, resolver=env)
    assert len(adjudications) == len(labels)

    _, final = _ingest(env, labels, adjudications=adjudications)
    assert all(lbl.is_validated for lbl in final)
    assert all(label_route(lbl) == ROUTE_ADJUDICATED for lbl in final)
    assert all(lbl.applies_to == ["Commercial Banks", "Small Finance Banks"] for lbl in final)
    assert all(lbl.validate() == [] for lbl in final)


def test_adjudication_without_a_rationale_is_a_hard_fail(env):
    labels, votes, promoted = _disagreeing_pilot(env)
    result = build_adjudication_tasks(promoted, votes, CFG, resolver=env)

    _fill_adjudication(result["path"], {
        labels[0].label_id: {
            "final_applies_to": "Commercial Banks",
            "final_differential_flag": "shared",
            "adjudication_rationale": "",  # the decision, with no stated reason
        }
    })

    with pytest.raises(AnnotationError, match="adjudication_rationale is empty"):
        load_adjudications(CFG, candidates=labels, resolver=env)


def test_an_entirely_blank_adjudication_row_defers_the_item(env):
    labels, votes, promoted = _disagreeing_pilot(env)
    build_adjudication_tasks(promoted, votes, CFG, resolver=env)

    adjudications = load_adjudications(CFG, candidates=labels, resolver=env)
    assert adjudications == {}

    _, final = _ingest(env, labels, adjudications=adjudications)
    assert all(label_route(lbl) == ROUTE_NEEDS_ADJUDICATION for lbl in final)


def test_adjudication_file_carries_every_vote_side_by_side(env):
    labels, votes, promoted = _disagreeing_pilot(env)
    result = build_adjudication_tasks(promoted, votes, CFG, resolver=env)
    assert "karan_pass1_applies_to" in result["columns"]
    assert "karan_pass2_differential_flag" in result["columns"]
    assert "final_applies_to" in result["columns"]


# -- 7. the retest gap guard --------------------------------------------------


def _log_pass1(resolver, *, days_ago: float, rater="karan"):
    stamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
    append_annotation_log(resolver, {
        "event": "ingest", "rater_id": rater, "pass_no": 1,
        "timestamp": stamp.isoformat(), "rows_voted": 6, "rows_blank": 0,
        "rows_not_obligation": 0, "minutes": 30,
    })


def test_retest_refuses_before_pass_one_is_ingested(env):
    labels = _candidates(4, resolver=env)
    draw_retest_set(labels, 1.0, 1, resolver=env)
    with pytest.raises(AnnotationError, match="no pass-1 ingest"):
        build_pass2_tasks(CFG, candidates=labels, resolver=env)


def test_retest_refuses_at_one_day(env):
    labels = _candidates(4, resolver=env)
    draw_retest_set(labels, 1.0, 1, resolver=env)
    _log_pass1(env, days_ago=1)
    with pytest.raises(AnnotationError, match="min_gap_days"):
        build_pass2_tasks(CFG, candidates=labels, resolver=env)


def test_retest_proceeds_with_allow_short_gap_and_records_it(env, caplog):
    labels = _candidates(4, resolver=env)
    draw_retest_set(labels, 1.0, 1, resolver=env)
    _log_pass1(env, days_ago=1)

    with caplog.at_level("WARNING"):
        result = build_pass2_tasks(CFG, candidates=labels, resolver=env, allow_short_gap=True)

    assert result["allow_short_gap_used"] is True
    assert Path(result["path"]).exists()
    assert any("allow-short-gap" in r.message or "--allow-short-gap" in r.getMessage()
               for r in caplog.records)

    log = json.loads((env.write_path("benchmark", "annotation_log.json")).read_text())
    retest_entries = [e for e in log["entries"] if e["event"] == "retest"]
    assert retest_entries and retest_entries[-1]["allow_short_gap_used"] is True


def test_retest_refuses_to_overwrite_an_existing_pass2_file(env):
    labels = _candidates(4, resolver=env)
    draw_retest_set(labels, 1.0, 1, resolver=env)
    _log_pass1(env, days_ago=10)

    build_pass2_tasks(CFG, candidates=labels, resolver=env)
    with pytest.raises(AnnotationError, match="refusing to overwrite the existing pass-2 file"):
        build_pass2_tasks(CFG, candidates=labels, resolver=env)

    # Forced, it backs the old file up rather than destroying it.
    build_pass2_tasks(CFG, candidates=labels, resolver=env, force=True)
    backups = list((env.write_path("benchmark", "tasks", "x").parent / "_overwritten").glob("*.csv"))
    assert backups


def test_pass2_file_is_shuffled_blank_and_limited_to_the_retest_set(env):
    labels = _candidates(6, resolver=env)
    drawn = draw_retest_set(labels, 1.0, 20260924, resolver=env)
    _log_pass1(env, days_ago=10)
    result = build_pass2_tasks(CFG, candidates=labels, resolver=env)

    with open(result["path"], newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert {r["label_id"] for r in rows} == set(drawn["label_ids"])
    assert all(r["applies_to"] == "" and r["differential_flag"] == "" for r in rows)
    assert [r["label_id"] for r in rows] != sorted(drawn["label_ids"]), "row order must be shuffled"


def test_retest_set_is_deterministic_and_refuses_to_silently_redraw(env):
    labels = _candidates(6, resolver=env)
    first = draw_retest_set(labels, 1.0, 20260924, resolver=env)
    second = draw_retest_set(labels, 0.5, 999, resolver=env)
    assert second["label_ids"] == first["label_ids"], "an existing retest set must not be redrawn"
    assert second["seed"] == first["seed"]


# -- 8. the overwrite guard ---------------------------------------------------


def test_build_annotation_tasks_refuses_to_blank_a_filled_file(env):
    labels = _candidates(3, resolver=env)
    build_annotation_tasks(labels, CFG, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={labels[0].label_id: _vote()})  # one filled cell

    with pytest.raises(AnnotationError, match="refusing to overwrite"):
        build_annotation_tasks(labels, CFG, resolver=env)


def test_forced_regeneration_backs_the_old_file_up_first(env):
    labels = _candidates(3, resolver=env)
    build_annotation_tasks(labels, CFG, resolver=env)
    path = _write_pass(env, labels, pass_no=1, rows={labels[0].label_id: _vote()})
    before = path.read_bytes()

    build_annotation_tasks(labels, CFG, resolver=env, force=True)

    backups = list((path.parent / "_overwritten").glob("annotation_karan.csv.*.csv"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == before
    # ...and the live file really was regenerated blank.
    with open(path, newline="", encoding="utf-8") as handle:
        assert all(row["applies_to"] == "" for row in csv.DictReader(handle))


def test_persist_candidates_refuses_a_changed_label_id_set(env):
    labels = _candidates(3, resolver=env)
    with pytest.raises(AnnotationError, match="label_id set has changed"):
        persist_candidates(_candidates(4), CFG, resolver=env)
    # Unchanged is fine, and forced is allowed.
    persist_candidates(labels, CFG, resolver=env)
    persist_candidates(_candidates(4), CFG, resolver=env, force=True)


# -- 9. report writes nothing under data/benchmark ----------------------------


def _point_cli_at(monkeypatch, cli, root):
    """Aim the CLI at a throwaway tree.

    The module attribute is replaced, never ``PathResolver.from_config``
    itself: patching the classmethod in place makes the replacement call the
    replacement, which recurses forever.
    """

    class _Rooted:
        @staticmethod
        def from_config(cfg, **kwargs):
            return PathResolver.from_config(CFG, repo_root=root)

    monkeypatch.setattr(cli, "load_config", lambda _path=None: CFG)
    monkeypatch.setattr(cli, "PathResolver", _Rooted)


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_report_leaves_every_benchmark_file_byte_identical(env, tmp_path, monkeypatch):
    import scripts.run_annotation as cli

    labels = _candidates(4, resolver=env)
    build_annotation_tasks(labels, CFG, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})
    draw_retest_set(labels, 1.0, 1, resolver=env)

    benchmark_dir = env.write_dir("benchmark")
    before = _hash_tree(benchmark_dir)
    assert before, "fixture must have written something to compare"

    _point_cli_at(monkeypatch, cli, tmp_path)
    assert cli.main(["report"]) == 0

    assert _hash_tree(benchmark_dir) == before
    assert (env.write_path("reports", "phase1_meer_annotation.md")).exists()


def test_report_text_states_the_protocol_is_solo(env, tmp_path, monkeypatch):
    import scripts.run_annotation as cli

    _candidates(4, resolver=env)
    _point_cli_at(monkeypatch, cli, tmp_path)
    cli.main(["report"])

    text = (env.write_path("reports", "phase1_meer_annotation.md")).read_text(encoding="utf-8")
    assert "2026-09-24" in text
    assert "single annotator" in text
    assert "NOT YET MEASURED" in text


# -- 10. BOM + CRLF -----------------------------------------------------------


def test_bom_and_crlf_file_ingests_cleanly(env):
    """Excel's "CSV UTF-8" export prepends a BOM, which broke the header check."""
    labels = _candidates(3, resolver=env)
    path = _write_pass(
        env, labels, pass_no=1,
        rows={lbl.label_id: _vote() for lbl in labels},
        encoding="utf-8-sig", newline="\r\n",
    )
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw

    votes = load_votes(CFG, candidates=labels, resolver=env)
    assert len(votes) == 3
    assert all(v.status == VOTE_VOTED for v in votes)
    assert all(v.applies_to == ("Commercial Banks",) for v in votes)


# -- 11. unknown entity-class name --------------------------------------------


def test_unknown_applies_to_name_is_a_hard_fail_naming_the_row(env):
    labels = _candidates(3, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={
        labels[1].label_id: _vote(applies_to="Commercial Banks;Merchant Banks")
    })

    with pytest.raises(AnnotationError) as excinfo:
        load_votes(CFG, candidates=labels, resolver=env)

    message = str(excinfo.value)
    assert "Merchant Banks" in message
    assert labels[1].label_id in message
    assert "row 3" in message
    assert "Commercial Banks" in message  # the valid names are listed


def test_duplicate_label_id_in_one_file_is_a_hard_fail(env):
    labels = _candidates(2, resolver=env)
    path = _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows.append(dict(rows[0]))
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(AnnotationError, match="already appears at row"):
        load_votes(CFG, candidates=labels, resolver=env)


def test_missing_vocabulary_file_fails_loudly_rather_than_skipping_validation(tmp_path):
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)
    labels = _candidates(2, resolver=resolver)
    _write_pass(resolver, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})
    with pytest.raises(AnnotationError, match="entity-class vocabulary"):
        load_votes(CFG, candidates=labels, resolver=resolver)


def test_legacy_roster_files_are_ignored_and_never_deleted(env, caplog):
    labels = _candidates(2, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})
    legacy = _write_pass(env, labels, rater="meer", pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})

    with caplog.at_level("WARNING"):
        votes = load_votes(CFG, candidates=labels, resolver=env)

    assert {v.rater_id for v in votes} == {"karan"}
    assert legacy.exists(), "a legacy roster file must never be deleted"
    assert any("annotation_meer.csv" in r.getMessage() for r in caplog.records)


# -- 12. no Fleiss' kappa below three raters ----------------------------------


def test_primary_plus_one_second_rater_produces_no_numeric_fleiss_key(env):
    cfg = _cfg(second_raters=["akash"])
    labels = _candidates(4, resolver=env)
    rows = {lbl.label_id: _vote(flag="shared") for lbl in labels}
    _write_pass(env, labels, pass_no=1, rows=rows)
    _write_pass(env, labels, rater="akash", pass_no=1, rows=rows)

    votes = load_votes(cfg, candidates=labels, resolver=env)
    agreement = measure_agreement(votes, cfg)

    flat = json.dumps(agreement)
    assert "fleiss" not in flat.lower(), f"no fleiss key may exist with 2 raters: {flat}"
    assert agreement["second_rater"]["raters"]["akash"]["n_items"] == 4


def test_solo_annotator_produces_no_fleiss_key_and_says_why(env):
    labels = _candidates(4, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})

    votes = load_votes(CFG, candidates=labels, resolver=env)
    agreement = measure_agreement(votes, CFG)

    assert "fleiss" not in json.dumps(agreement).lower()
    assert agreement["second_rater"]["status"] == "NOT YET MEASURED — no second rater configured"
    assert "NOT YET MEASURED" in agreement["test_retest"]["status"]


def test_three_real_raters_do_get_a_fleiss_figure(env):
    """The guard is about rater count, not about refusing to ever compute it."""
    cfg = _cfg(second_raters=["akash", "meer"])
    labels = _candidates(4, resolver=env)
    flags = ["shared", "class-specific", "absent", "shared"]
    _write_pass(env, labels, pass_no=1, rows={
        lbl.label_id: _vote(flag=flags[i]) for i, lbl in enumerate(labels)
    })
    for rater in ("akash", "meer"):
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(flag=flags[i]) for i, lbl in enumerate(labels)
        })

    agreement = measure_agreement(load_votes(cfg, candidates=labels, resolver=env), cfg)
    fleiss = agreement["second_rater"]["fleiss_kappa_flag"]
    assert fleiss["n_items"] == 4
    assert fleiss["kappa"] == pytest.approx(1.0)


# -- 13. tautology share ------------------------------------------------------


def test_tautology_share_is_one_when_a_rater_copies_the_context_class(env):
    labels = _candidates(6, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={
        lbl.label_id: _vote(applies_to=lbl.entity_class) for lbl in labels
    })

    votes = load_votes(CFG, candidates=labels, resolver=env)
    shares = tautology_share_by_rater(votes, labels)

    assert shares["karan:pass1"]["share"] == pytest.approx(1.0)
    assert shares["karan:pass1"]["voted_rows"] == 6


def test_tautology_share_is_measured_per_rater_not_from_the_merged_label(env):
    """The superseded report read the merged label and saw only the last annotator."""
    cfg = _cfg(second_raters=["akash"])
    labels = _candidates(4, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={
        lbl.label_id: _vote(applies_to=lbl.entity_class) for lbl in labels
    })
    _write_pass(env, labels, rater="akash", pass_no=1, rows={
        lbl.label_id: _vote(applies_to="Small Finance Banks") for lbl in labels
    })

    shares = tautology_share_by_rater(load_votes(cfg, candidates=labels, resolver=env), labels)
    assert shares["karan:pass1"]["share"] == pytest.approx(1.0)
    assert shares["akash:pass1"]["share"] < 1.0


# -- 14. pilot metrics computed from items, not paragraphs --------------------


def test_entity_classes_in_items_counts_items_not_paragraphs():
    """Three classes appear across the candidates; a fourth was only searched."""
    labels = _candidates(5)  # cycles through 3 classes
    metrics = item_coverage_metrics(labels)

    assert metrics["entity_classes_in_items_count"] == 3
    assert set(metrics["entity_classes_in_items"]) == set(CLASSES)
    assert metrics["items_missing_subject_family"] == 0


def test_items_missing_subject_family_is_counted():
    labels = _candidates(4)
    labels[0].subject_family = None
    labels[2].subject_family = ""
    assert item_coverage_metrics(labels)["items_missing_subject_family"] == 2


# -- Cohen's kappa itself -----------------------------------------------------


def test_cohen_kappa_is_one_on_perfect_varied_agreement():
    pairs = [("shared", "shared"), ("absent", "absent"), ("class-specific", "class-specific")]
    assert cohen_kappa(pairs) == pytest.approx(1.0)


def test_cohen_kappa_is_not_measurable_when_expected_agreement_is_one():
    """Both sides unanimous on one category: undefined, never 0.0."""
    result = cohen_kappa([("shared", "shared"), ("shared", "shared")])
    assert result == "NOT YET MEASURED"
    assert result is not None and result != 0.0


def test_cohen_kappa_is_not_measurable_with_no_pairs():
    assert cohen_kappa([]) == "NOT YET MEASURED"


def test_cohen_kappa_is_negative_on_systematic_disagreement():
    pairs = [("shared", "absent"), ("absent", "shared")] * 3
    kappa = cohen_kappa(pairs)
    assert isinstance(kappa, float) and kappa < 0


# -- route accounting ---------------------------------------------------------


def test_route_counts_cover_every_item_exactly_once(env):
    labels = _candidates(6, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={
        labels[0].label_id: _vote(flag="shared"),
        labels[1].label_id: _vote(flag="shared"),
        labels[2].label_id: {"applies_to": "", "differential_flag": "",
                             "applies_to_rationale": "", "notes": "not an obligation"},
        labels[3].label_id: _vote(flag="absent"),
    })
    _write_pass(env, labels, pass_no=2, rows={
        labels[0].label_id: _vote(flag="shared"),
        labels[1].label_id: _vote(flag="absent"),
        labels[2].label_id: {"applies_to": "", "differential_flag": "",
                             "applies_to_rationale": "", "notes": "not an obligation"},
    })

    _, promoted = _ingest(env, labels)
    counts = route_counts(promoted)

    assert sum(counts.values()) == 6
    assert counts[ROUTE_RETEST_CONSISTENT] == 1
    assert counts[ROUTE_NEEDS_ADJUDICATION] == 1
    assert counts[ROUTE_NOT_OBLIGATION] == 1
    assert counts[ROUTE_PASS1_ONLY] == 1
    assert counts["unvoted-candidate"] == 2


def test_single_pass_route_validates_outside_the_retest_set(env):
    labels = _candidates(3, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})
    _, promoted = _ingest(env, labels, retest_ids=set())

    assert all(label_route(lbl) == ROUTE_SINGLE_PASS for lbl in promoted)
    assert all(lbl.is_validated for lbl in promoted)
    assert all(lbl.annotator_ids == ["karan"] and lbl.annotation_count == 1 for lbl in promoted)
    assert all(lbl.agreement_score is None for lbl in promoted)


def test_promotion_never_counts_annotators(env):
    """One annotator, one pass, outside the retest set: promoted on the route."""
    labels = _candidates(2, resolver=env)
    _write_pass(env, labels, pass_no=1, rows={lbl.label_id: _vote() for lbl in labels})
    _, promoted = _ingest(env, labels, retest_ids=set())
    assert all(len(lbl.annotator_ids) == 1 for lbl in promoted)
    assert all(lbl.is_validated for lbl in promoted)
