"""P1-004 §A3: three independent human raters, and the AI-label firewall.

The pilot turned out to have three human raters after all (Karan, Akash,
Meer), so genuine inter-rater agreement is computable for the first time. Two
things have to hold at once and they pull in opposite directions:

* three real raters must produce real pairwise and Fleiss' kappa;
* a file produced with AI assistance must never become the third rater, never
  enter either statistic, and never promote an item — because an AI label is
  not an independent observer of the same construct, and counting it would
  fabricate exactly the agreement the benchmark's validity rests on.

Fixtures only, no network.
"""

from __future__ import annotations

import csv
import json

import pytest

from src.benchmark.annotation import (
    AI_RATER_PREFIX,
    LABEL_SOURCE_AI,
    LABEL_SOURCE_MANUAL,
    ROUTE_CONSENSUS,
    ROUTE_NEEDS_ADJUDICATION,
    ROUTE_NOT_OBLIGATION,
    TASK_FILE_COLUMNS,
    append_annotation_log,
    consensus_raters,
    human_raters,
    label_route,
    load_ai_diagnostic_votes,
    load_votes,
    measure_agreement,
    merge_votes,
    promote_validated,
    rater_label_sources,
    route_counts,
)
from src.common.paths import PathResolver
from src.schemas.benchmark import LabelStatus

from tests.test_benchmark_solo_protocol import (
    CFG as SOLO_CFG,
    _candidates,
    _fleiss_keys,
    _vote,
    _write_pass,
    seed_entity_classes,
)

RATERS = ("karan", "akash", "meer")

CFG = {
    **SOLO_CFG,
    "benchmark": {
        **SOLO_CFG["benchmark"],
        "second_raters": ["akash", "meer"],
        "ai_diagnostic_files": [],
    },
}


def _cfg(**overrides):
    return {**CFG, "benchmark": {**CFG["benchmark"], **overrides}}


@pytest.fixture
def env(tmp_path):
    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)
    seed_entity_classes(resolver)
    return resolver


def _declare(resolver, rater, source=LABEL_SOURCE_MANUAL):
    append_annotation_log(resolver, {
        "event": "ingest", "rater_id": rater, "pass_no": 1,
        "timestamp": "2026-09-25T06:00:00+00:00", "rows_voted": 6,
        "rows_blank": 0, "rows_not_obligation": 0,
        "minutes": 45, "minutes_basis": "recalled_estimate", "label_source": source,
    })


def _run(resolver, labels, cfg=CFG, *, retest_ids=None, ai_votes=None):
    votes = load_votes(cfg, candidates=labels, resolver=resolver)
    humans = human_raters(cfg, resolver)
    merged = merge_votes(
        labels, votes, cfg,
        retest_ids=retest_ids if retest_ids is not None else set(),
        human_rater_ids=humans,
    )
    promoted = promote_validated(merged, cfg)
    agreement = measure_agreement(
        votes, cfg, resolver=resolver, ai_votes=ai_votes or [], raters=humans,
    )
    return votes, promoted, agreement


# -- 1. three raters never agree ---------------------------------------------


def test_three_raters_who_never_agree_score_near_chance_and_promote_nothing(env):
    labels = _candidates(6, resolver=env)
    for rater in RATERS:
        _declare(env, rater)

    # Every rater uses a different flag on every item, so no two ever coincide.
    cycles = {
        "karan": ["shared", "class-specific", "absent"],
        "akash": ["class-specific", "absent", "shared"],
        "meer": ["absent", "shared", "class-specific"],
    }
    for rater, flags in cycles.items():
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(flag=flags[i % 3]) for i, lbl in enumerate(labels)
        })

    _, promoted, agreement = _run(env, labels)

    for key, block in agreement["pairwise"].items():
        kappa = block["cohen_kappa_flag"]
        assert isinstance(kappa, float), f"{key}: kappa must be a number, got {kappa!r}"
        assert kappa < 0.2, f"{key}: raters who never agree must not score {kappa}"

    fleiss = agreement["fleiss_three_raters"]["kappa"]
    assert isinstance(fleiss, float) and fleiss < 0.2, f"Fleiss must be low, got {fleiss!r}"

    assert sum(1 for lbl in promoted if lbl.is_validated) == 0
    assert all(label_route(lbl) == ROUTE_NEEDS_ADJUDICATION for lbl in promoted)


# -- 2. two of three agree ----------------------------------------------------


def test_unanimous_raters_validate_with_consensus_provenance(env):
    labels = _candidates(4, resolver=env)
    for rater in RATERS:
        _declare(env, rater)
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(flag="shared") for lbl in labels
        })

    _, promoted, _ = _run(env, labels)

    assert all(lbl.is_validated for lbl in promoted)
    assert all(label_route(lbl) == ROUTE_CONSENSUS for lbl in promoted)
    for lbl in promoted:
        assert consensus_raters(lbl) == ["akash", "karan", "meer"]
        assert lbl.provenance == "annotator:consensus:akash+karan+meer"
        assert lbl.validate() == []


def test_two_agreeing_raters_validate_when_the_third_did_not_vote(env):
    """'At least 2 agree' is satisfied by two raters when nobody contradicts."""
    labels = _candidates(3, resolver=env)
    for rater in ("karan", "akash"):
        _declare(env, rater)
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(flag="absent") for lbl in labels
        })
    _declare(env, "meer")
    _write_pass(env, labels, rater="meer", pass_no=1, rows={})  # all blank

    _, promoted, _ = _run(env, labels)
    assert all(lbl.is_validated for lbl in promoted)
    assert all(consensus_raters(lbl) == ["akash", "karan"] for lbl in promoted)


def test_a_single_dissenting_rater_blocks_the_majority(env):
    """A 2-1 split goes to adjudication; the majority never silently carries it.

    Taking the majority would throw away the dissent, which is the part of a
    disagreement that actually carries information about the guideline.
    """
    labels = _candidates(3, resolver=env)
    for rater in ("karan", "akash"):
        _declare(env, rater)
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(flag="shared") for lbl in labels
        })
    _declare(env, "meer")
    _write_pass(env, labels, rater="meer", pass_no=1, rows={
        labels[0].label_id: _vote(flag="absent"),
        labels[1].label_id: _vote(flag="shared"),
        labels[2].label_id: _vote(flag="shared"),
    })

    _, promoted, _ = _run(env, labels)
    by_id = {lbl.label_id: lbl for lbl in promoted}

    assert label_route(by_id[labels[0].label_id]) == ROUTE_NEEDS_ADJUDICATION
    assert not by_id[labels[0].label_id].is_validated
    assert by_id[labels[1].label_id].is_validated
    assert by_id[labels[2].label_id].is_validated


def test_unanimous_not_obligation_is_rejected_with_consensus_provenance(env):
    labels = _candidates(2, resolver=env)
    for rater in RATERS:
        _declare(env, rater)
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: {"applies_to": "", "differential_flag": "",
                           "applies_to_rationale": "", "notes": "definitional"}
            for lbl in labels
        })

    _, promoted, agreement = _run(env, labels)

    assert all(lbl.label_status == LabelStatus.REJECTED.value for lbl in promoted)
    # Rejection keeps the not-obligation route: it is not a promotion, and
    # giving it the consensus provenance would make route_counts read it as
    # a consensus validation. Who agreed is recoverable from the vote file
    # and from the not_obligation_agreement block below.
    assert all(label_route(lbl) == ROUTE_NOT_OBLIGATION for lbl in promoted)
    assert all(consensus_raters(lbl) == [] for lbl in promoted)
    assert agreement["not_obligation_agreement"]["unanimous_not_an_obligation"] == 2
    assert agreement["not_obligation_agreement"]["agreement_rate"] == pytest.approx(1.0)


# -- 3. an AI-assisted file is never a rater ----------------------------------


def _write_ai_file(resolver, labels, rows):
    path = resolver.write_path("benchmark", "diagnostics", "annotation_karan_ai_assisted.csv")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TASK_FILE_COLUMNS))
        writer.writeheader()
        for label in labels:
            filled = rows.get(label.label_id, {})
            writer.writerow({
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
            })
    return path


def test_an_ai_file_never_enters_pairwise_or_fleiss_and_never_promotes(env):
    cfg = _cfg(
        second_raters=["akash"],
        ai_diagnostic_files=["diagnostics/annotation_karan_ai_assisted.csv"],
    )
    labels = _candidates(4, resolver=env)
    for rater in ("karan", "akash"):
        _declare(env, rater)

    # The two humans disagree on every item, so nothing may promote. The AI
    # file agrees with Karan throughout — if it were counted as a rater it
    # would form a 2-1 "majority" and push every item to validated.
    _write_pass(env, labels, rater="karan", pass_no=1, rows={
        lbl.label_id: _vote(flag="shared") for lbl in labels
    })
    _write_pass(env, labels, rater="akash", pass_no=1, rows={
        lbl.label_id: _vote(flag="absent") for lbl in labels
    })
    _write_ai_file(env, labels, {lbl.label_id: _vote(flag="shared") for lbl in labels})

    ai_votes = load_ai_diagnostic_votes(cfg, candidates=labels, resolver=env)
    assert ai_votes, "the diagnostic file must be read"
    assert all(v.rater_id.startswith(AI_RATER_PREFIX) for v in ai_votes)

    votes, promoted, agreement = _run(env, labels, cfg, ai_votes=ai_votes)

    # It is not in the rater roster, the vote set, or either statistic.
    assert all(not v.rater_id.startswith(AI_RATER_PREFIX) for v in votes)
    assert agreement["human_raters_with_votes"] == ["akash", "karan"]
    assert _fleiss_keys(agreement) == [], "2 humans + an AI file is not 3 raters"
    for key in agreement["pairwise"]:
        assert AI_RATER_PREFIX not in key

    # And it promoted nothing.
    assert sum(1 for lbl in promoted if lbl.is_validated) == 0
    assert all(label_route(lbl) == ROUTE_NEEDS_ADJUDICATION for lbl in promoted)
    assert all(AI_RATER_PREFIX not in (lbl.provenance or "") for lbl in promoted)


def test_the_ai_comparison_is_reported_but_labelled_as_not_reliability(env):
    cfg = _cfg(
        second_raters=["akash"],
        ai_diagnostic_files=["diagnostics/annotation_karan_ai_assisted.csv"],
    )
    labels = _candidates(4, resolver=env)
    for rater in ("karan", "akash"):
        _declare(env, rater)
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(flag="shared") for lbl in labels
        })
    _write_ai_file(env, labels, {lbl.label_id: _vote(flag="shared") for lbl in labels})

    ai_votes = load_ai_diagnostic_votes(cfg, candidates=labels, resolver=env)
    _, _, agreement = _run(env, labels, cfg, ai_votes=ai_votes)

    diag = agreement["human_ai_diagnostic"]
    assert diag["is_a_reliability_statistic"] is False
    assert "NOT a reliability statistic" in diag["warning"]
    assert set(diag["comparisons"]) == {
        "akash__vs__ai:annotation_karan_ai_assisted",
        "karan__vs__ai:annotation_karan_ai_assisted",
    }
    # It is a real comparison, just not a reliability one.
    assert diag["comparisons"]["karan__vs__ai:annotation_karan_ai_assisted"]["n_items"] == 4


# -- 4. a rater missing rows --------------------------------------------------


def test_fleiss_uses_only_items_every_rater_voted_on_and_reports_n(env):
    labels = _candidates(6, resolver=env)
    for rater in RATERS:
        _declare(env, rater)

    flags = ["shared", "class-specific", "absent", "shared", "class-specific", "absent"]
    full = {lbl.label_id: _vote(flag=flags[i]) for i, lbl in enumerate(labels)}
    _write_pass(env, labels, rater="karan", pass_no=1, rows=full)
    _write_pass(env, labels, rater="akash", pass_no=1, rows=full)
    # Meer left the last two rows untouched.
    partial = {lbl.label_id: full[lbl.label_id] for lbl in labels[:4]}
    _write_pass(env, labels, rater="meer", pass_no=1, rows=partial)

    _, promoted, agreement = _run(env, labels)

    fleiss = agreement["fleiss_three_raters"]
    assert fleiss["n_items"] == 4, "only items all three voted on may enter Fleiss"
    assert sorted(fleiss["raters"]) == ["akash", "karan", "meer"]

    # The two rows Meer skipped still validate on the other two raters.
    by_id = {lbl.label_id: lbl for lbl in promoted}
    assert consensus_raters(by_id[labels[5].label_id]) == ["akash", "karan"]
    # Pairwise karan-vs-meer is computed over the 4 items they share.
    assert agreement["pairwise"]["karan__vs__meer"]["n_items"] == 4
    assert agreement["pairwise"]["akash__vs__karan"]["n_items"] == 6


# -- 5. label_source = ai_assisted excludes a rater ---------------------------


def test_an_ai_assisted_rater_is_dropped_from_every_human_statistic(env):
    labels = _candidates(4, resolver=env)
    _declare(env, "karan", LABEL_SOURCE_AI)   # Karan's own file is AI-assisted
    _declare(env, "akash")
    _declare(env, "meer")
    for rater in RATERS:
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(flag="shared") for lbl in labels
        })

    assert rater_label_sources(env)["karan"] == LABEL_SOURCE_AI
    assert human_raters(CFG, env) == ["akash", "meer"]

    _, promoted, agreement = _run(env, labels)

    assert agreement["human_raters"] == ["akash", "meer"]
    assert agreement["human_raters_with_votes"] == ["akash", "meer"]
    assert "karan" not in json.dumps(agreement["pairwise"])
    assert _fleiss_keys(agreement) == [], "2 humans is not 3 raters, whoever else voted"

    # Items still validate, but on Akash and Meer alone.
    assert all(lbl.is_validated for lbl in promoted)
    assert all(consensus_raters(lbl) == ["akash", "meer"] for lbl in promoted)
    assert all("karan" not in (lbl.provenance or "") for lbl in promoted)


def test_an_ai_assisted_rater_cannot_carry_an_item_alone(env):
    """With the only other rater blank, an ai_assisted rater promotes nothing."""
    labels = _candidates(3, resolver=env)
    _declare(env, "karan", LABEL_SOURCE_AI)
    _declare(env, "akash")
    _write_pass(env, labels, rater="karan", pass_no=1, rows={
        lbl.label_id: _vote(flag="shared") for lbl in labels
    })
    _write_pass(env, labels, rater="akash", pass_no=1, rows={})

    cfg = _cfg(second_raters=["akash"])
    votes = load_votes(cfg, candidates=labels, resolver=env)
    humans = human_raters(cfg, env)
    assert humans == ["akash"]

    merged = merge_votes(labels, votes, cfg, retest_ids=set(), human_rater_ids=humans)
    promoted = promote_validated(merged, cfg)
    assert sum(1 for lbl in promoted if lbl.is_validated) == 0


def test_the_latest_declaration_wins(env):
    _declare(env, "karan", LABEL_SOURCE_AI)
    assert human_raters(CFG, env) == ["akash", "meer"]
    _declare(env, "karan", LABEL_SOURCE_MANUAL)
    assert human_raters(CFG, env) == ["karan", "akash", "meer"]


# -- route accounting ---------------------------------------------------------


def test_route_counts_cover_every_item_once_with_three_raters(env):
    labels = _candidates(6, resolver=env)
    for rater in RATERS:
        _declare(env, rater)

    agree = {lbl.label_id: _vote(flag="shared") for lbl in labels[:3]}
    _write_pass(env, labels, rater="karan", pass_no=1, rows={
        **agree,
        labels[3].label_id: _vote(flag="absent"),
        labels[4].label_id: {"applies_to": "", "differential_flag": "",
                             "applies_to_rationale": "", "notes": "not an obligation"},
    })
    _write_pass(env, labels, rater="akash", pass_no=1, rows={
        **agree,
        labels[3].label_id: _vote(flag="class-specific"),
        labels[4].label_id: {"applies_to": "", "differential_flag": "",
                             "applies_to_rationale": "", "notes": "not an obligation"},
    })
    _write_pass(env, labels, rater="meer", pass_no=1, rows=agree)

    _, promoted, _ = _run(env, labels)
    counts = route_counts(promoted)

    assert sum(counts.values()) == 6
    assert counts[ROUTE_CONSENSUS] == 3
    assert counts[ROUTE_NEEDS_ADJUDICATION] == 1   # the flag disagreement
    assert counts[ROUTE_NOT_OBLIGATION] == 1       # both called it not an obligation
    assert counts["unvoted-candidate"] == 1


# -- ingest metrics merging ---------------------------------------------------


def test_re_ingesting_one_rater_keeps_the_others_recorded_minutes(tmp_path, monkeypatch):
    """`ingest --rater X` knows only X's minutes; it must not null the rest.

    A plain dict.update() wiped every other rater's figure on each run, so the
    file ended up holding whichever rater was ingested last — and minutes per
    item is the number the whole Phase 2 size projection is built on.
    """
    import scripts.run_annotation as cli

    resolver = PathResolver.from_config(CFG, repo_root=tmp_path)

    first = {"passes": {
        "karan:pass1": {"rows_voted": 17, "minutes": 65.0, "minutes_basis": "recalled_estimate"},
        "akash:pass1": {"rows_voted": 17, "minutes": None, "minutes_basis": None},
    }}
    cli._merge_ingest_metrics(resolver, first)

    second = {"passes": {
        "karan:pass1": {"rows_voted": 17, "minutes": None, "minutes_basis": None},
        "akash:pass1": {"rows_voted": 17, "minutes": 45.0, "minutes_basis": "recalled_estimate"},
    }}
    merged = cli._merge_ingest_metrics(resolver, second)

    assert merged["passes"]["karan:pass1"]["minutes"] == 65.0
    assert merged["passes"]["akash:pass1"]["minutes"] == 45.0
    assert merged["passes"]["karan:pass1"]["minutes_basis"] == "recalled_estimate"


def test_applies_to_agreement_is_suppressed_when_the_column_has_one_source(env):
    """A pre-filled applies_to column must never read as RQ1 agreement."""
    from src.benchmark.annotation import APPLIES_TO_NOT_REPLICATED

    labels = _candidates(6, resolver=env)
    for rater in RATERS:
        _declare(env, rater)
    # Identical multi-class applies_to everywhere; flags differ.
    shared = "Commercial Banks;Small Finance Banks;Urban Co-operative Banks"
    flags = {"karan": "shared", "akash": "absent", "meer": "class-specific"}
    for rater in RATERS:
        _write_pass(env, labels, rater=rater, pass_no=1, rows={
            lbl.label_id: _vote(applies_to=shared, flag=flags[rater]) for lbl in labels
        })

    _, _, agreement = _run(env, labels)

    assert agreement["applies_to_replicated"] is False
    assert agreement["column_independence"]["multi_class_items_identical_across_all_raters"] == 6
    for block in agreement["pairwise"].values():
        assert block["applies_to_exact_match_rate"] == APPLIES_TO_NOT_REPLICATED
        assert block["applies_to_mean_jaccard"] == APPLIES_TO_NOT_REPLICATED
        # The flag kappa is still a real number.
        assert isinstance(block["cohen_kappa_flag"], float)
