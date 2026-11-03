"""P2-001 section H: cue regex, boilerplate exclusion, candidate schema, and
the guarantee that Phase 1's pilot artifacts are never touched."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from src.benchmark.candidates import (
    CANDIDATES_FILENAME,
    CANDIDATES_SUBDIR,
    EXCLUDED_BOILERPLATE,
    EXCLUSION_DEFINITIONAL,
    EXCLUSION_HEADER,
    EXCLUSION_PROCEDURAL,
    EXCLUSION_QUOTED_STATUTE,
    ObligationCandidate,
    ProtectedFileChanged,
    SampleOverwriteError,
    SchemaDriftError,
    allocate_sample,
    assert_unchanged,
    build_candidate,
    classify_paragraph_cues,
    document_cell_map,
    draw_precision_sample,
    extract_corpus_candidates,
    extraction_metrics,
    find_cues,
    persist_candidates,
    protected_file_hashes,
    read_sample,
    score_precision_sample,
    write_precision_sample,
)
from src.common.io_helpers import read_jsonl, write_jsonl
from src.common.paths import PathResolver
from tests.conftest import make_config

# -- cue matching ------------------------------------------------------------


def cues(text: str) -> list[str]:
    return [c.cue for c in find_cues(text)]


def test_basic_cues_match_case_insensitively():
    assert cues("The bank SHALL maintain records.") == ["shall"]
    assert cues("Banks Must report within 7 days.") == ["must"]
    assert cues("NBFCs are required to file returns.") == ["are required to"]
    assert cues("The company is required to disclose it.") == ["is required to"]


def test_word_boundary_rejects_embedded_shall():
    assert cues("The Marshall Islands and a shallow reading.") == []
    assert cues("marshalling of assets") == []
    assert cues("mustard seed") == []


def test_longest_cue_wins_at_same_offset():
    assert cues("It shall not lend.") == ["shall not"]
    assert cues("It must not lend.") == ["must not"]


def test_cue_spanning_a_line_break_is_normalised():
    found = find_cues("The bank shall\nnot accept deposits.")
    assert [c.cue for c in found] == ["shall not"]
    assert found[0].start == len("The bank ")


def test_all_cue_positions_are_recorded():
    text = "The bank shall maintain a register and must report it; it shall not delay."
    found = find_cues(text)
    assert [c.cue for c in found] == ["shall", "must", "shall not"]
    for c in found:
        assert text[c.start:c.end].lower().split()[0] in ("shall", "must")


def test_negated_requirement_is_not_a_cue():
    assert cues("Banks are not required to file this return.") == []


def test_equivalent_cues():
    assert cues("Banks are prohibited from charging fees.") == ["are prohibited from"]
    assert cues("It is mandatory for banks to comply.") == ["is mandatory"]
    assert cues("Lenders are obliged to inform borrowers.") == ["are obliged to"]


# -- boilerplate exclusion (C.3) ----------------------------------------------


def exclusions(text: str, previous: str | None = None) -> list[str | None]:
    return [c.exclusion for c in classify_paragraph_cues(text, previous)]


def test_shall_mean_is_excluded_shall_maintain_is_not():
    assert exclusions('"Bank" shall mean a banking company as defined in the Act.') == [EXCLUSION_DEFINITIONAL]
    assert exclusions("Every bank shall maintain a register of complaints.") == [None]


@pytest.mark.parametrize(
    "text",
    [
        '"Deposit" shall have the same meaning as assigned in the Act.',
        "Words not defined here shall have the meanings assigned in the RBI Act.",
        "Any reference to the Act shall be construed as a reference to the amended Act.",
        "Such a company shall be deemed to be a non-banking financial company.",
        '"Credit facility" shall include loans and advances.',
        '"Tier I capital" (T1) shall include paid-up equity.',
        "(ii) ‘Electronic Trading Platform’ (ETP) shall mean any electronic system.",
    ],
)
def test_definitional_uses_are_excluded(text):
    assert exclusions(text) == [EXCLUSION_DEFINITIONAL]


def test_shall_include_without_defined_term_is_an_obligation():
    assert exclusions("The Board-approved policy shall include the following elements.") == [None]


@pytest.mark.parametrize(
    "text",
    [
        "These Directions shall come into force with immediate effect.",
        "These Directions shall come into effect from April 1, 2026.",
        "These Directions shall be called the Reserve Bank of India (KYC) Directions, 2016.",
        "These Directions shall apply to every Scheduled Commercial Bank.",
        "The provisions of this Master Direction shall be applicable to all NBFCs.",
        "The earlier circulars shall stand repealed.",
        "57. The provisions of these Directions shall be in addition to, and not in derogation of any other law.",
    ],
)
def test_procedural_uses_are_excluded(text):
    assert exclusions(text) == [EXCLUSION_PROCEDURAL]


def test_apply_with_an_entity_subject_is_kept():
    assert exclusions("Every bank shall apply the revised risk weights.") == [None]


def test_heading_is_excluded_as_procedural_header():
    assert exclusions("What The Bank Shall Disclose") == [EXCLUSION_HEADER]


def test_heading_glued_to_the_end_of_a_paragraph_is_excluded():
    text = "Chapter III – Outsourcing of Financial Services\nA. Activities that shall not be outsourced"
    assert exclusions(text) == [EXCLUSION_HEADER]


def test_sentence_before_a_glued_heading_is_kept():
    # Real corpus shape: segmentation attaches the next sub-heading to the
    # end of the preceding paragraph. The obligation above it is operative.
    assert exclusions("interest shall be paid.\nH. Penalty on Premature Withdrawal of Deposits") == [None]


def test_sentence_cut_at_a_paragraph_break_is_not_a_heading():
    text = "C. Advances in India Advances shall be broadly classified into"
    assert [c.exclusion for c in classify_paragraph_cues(text, rules="v1")] == [None]
    # Later rule sets exclude it, but as a classification clause, never as a heading.
    assert [c.exclusion for c in classify_paragraph_cues(text, rules="v2")] == ["classification_deeming"]
    assert exclusions(text) == ["non_action_effect:definitional"]


def test_wrapped_mid_paragraph_line_is_not_a_heading():
    text = "A. Banks shall maintain adequate\nrecords of every transaction for eight years."
    assert exclusions(text) == [None]


def test_clause_fragment_is_not_a_heading():
    assert exclusions("(i) shall ensure that the customer is informed, and") == [None]
    assert exclusions("the bank shall maintain adequate records") == [None]


def test_quoted_statute_is_excluded():
    text = (
        'Section 45-IA provides: "No non-banking financial company shall commence or carry on the '
        'business of a non-banking financial institution without a certificate of registration."'
    )
    assert exclusions(text) == [EXCLUSION_QUOTED_STATUTE]


def test_curly_quoted_statute_is_excluded():
    text = (
        "The Act states “every banking company shall maintain in India assets the value of which "
        "shall not be less than seventy-five per cent of its demand and time liabilities”."
    )
    assert exclusions(text) == [EXCLUSION_QUOTED_STATUTE, EXCLUSION_QUOTED_STATUTE]


def test_superseded_text_in_an_amendment_footnote_is_excluded():
    text = (
        "An Indian company shall report such issue in Form FC-GPR.\n"
        "46 Inserted with effect from 07.11.17. Prior to insertion it read as “An Indian company "
        "receiving investment from outside India shall report the details of the consideration”."
    )
    assert exclusions(text) == [None, EXCLUSION_QUOTED_STATUTE]


def test_short_quoted_term_is_not_statute():
    assert exclusions('The "bank" shall maintain records of every transaction.') == [None]


def test_reads_as_under_excludes_following_cues_in_same_paragraph():
    text = "Section 26A of the Act reads as under: every bank shall transfer unclaimed deposits."
    assert exclusions(text) == [EXCLUSION_QUOTED_STATUTE]


def test_cue_before_the_intro_phrase_is_kept():
    text = "Banks shall comply with Section 26A, which reads as under: every bank shall transfer deposits."
    assert exclusions(text) == [None, EXCLUSION_QUOTED_STATUTE]


def test_paragraph_after_a_quote_intro_is_excluded():
    previous = "Section 45-IC of the RBI Act, 1934 reads as follows:"
    assert exclusions("Every NBFC shall create a reserve fund.", previous) == [EXCLUSION_QUOTED_STATUTE]
    assert exclusions("Every NBFC shall create a reserve fund.", "The bank should note this.") == [None]


# -- candidate records ------------------------------------------------------


def para(pid: str = "md_1::p00001", text: str = "The bank shall maintain records.") -> dict:
    return {"paragraph_id": pid, "document_id": pid.split("::")[0], "position": 1, "text": text}


def test_mixed_paragraph_is_a_kept_candidate():
    c = build_candidate(
        para(text='"Bank" shall mean a banking company. Every bank shall maintain a register.'),
        entity_class="Commercial Banks", matrix_cell=None,
    )
    assert c.cue_exclusions == [EXCLUSION_DEFINITIONAL, None]
    assert c.exclusion_reason is None
    assert c.validate() == []


def test_all_boilerplate_paragraph_is_flagged_not_dropped():
    c = build_candidate(para(text='"Bank" shall mean a banking company.'), entity_class="X", matrix_cell=None)
    assert c is not None
    assert c.exclusion_reason == EXCLUDED_BOILERPLATE
    assert c.validate() == []


def test_paragraph_without_cue_yields_nothing():
    assert build_candidate(para(text="Banks may, at their discretion, lend."), entity_class="X", matrix_cell=None) is None


# -- schema -----------------------------------------------------------------

SECTION_D_FIELDS = {
    "candidate_id", "document_id", "paragraph_id", "entity_class", "cue_matched",
    "cue_position", "span_text", "matrix_cell", "exclusion_reason",
}


def test_schema_field_specs_match_dataclass():
    assert set(ObligationCandidate.field_names()) == set(ObligationCandidate.spec_map())


def test_schema_covers_section_d_plus_one_documented_extra():
    assert set(ObligationCandidate.field_names()) - SECTION_D_FIELDS == {"cue_exclusions"}
    assert SECTION_D_FIELDS <= set(ObligationCandidate.field_names())


def test_schema_rejects_inconsistent_records():
    good = build_candidate(para(), entity_class="X", matrix_cell="ec_x|sf_y")
    assert good.validate() == []

    bad = ObligationCandidate.from_dict({**good.to_dict(), "cue_position": [[0, 3]]})
    assert any("cue_position" in e for e in bad.validate())

    bad = ObligationCandidate.from_dict({**good.to_dict(), "exclusion_reason": EXCLUDED_BOILERPLATE})
    assert any("exclusion_reason" in e for e in bad.validate())

    bad = ObligationCandidate.from_dict({**good.to_dict(), "candidate_id": "something_else"})
    assert any("candidate_id" in e for e in bad.validate())

    with pytest.raises(Exception):
        ObligationCandidate.from_dict({**good.to_dict(), "undeclared": 1})


# -- corpus fixture ---------------------------------------------------------

MANIFEST = [
    {"document_id": "md_1", "entity_class_raw": "Commercial Banks", "entity_class": "Commercial Banks",
     "subject_family": "KYC"},
    {"document_id": "md_2", "entity_class_raw": "Small Finance Banks", "entity_class": "Small Finance Banks",
     "subject_family": None},
    {"document_id": "md_3", "entity_class_raw": "Payments Banks", "entity_class": "Payments Banks",
     "subject_family": "KYC"},
]
CELLS = [
    {"entity_class": "Commercial Banks", "subject_family": "KYC", "source_directions": ["md_1"],
     "entity_class_term_id": "ec_commercial_banks", "subject_family_term_id": "sf_kyc"},
    {"entity_class": "Payments Banks", "subject_family": "KYC", "source_directions": ["md_3"],
     "entity_class_term_id": "ec_payments_banks", "subject_family_term_id": "sf_kyc"},
]
PARAGRAPHS = {
    "md_1": [
        "These Directions shall come into force with immediate effect.",
        '"Customer" shall mean a person who is engaged in a financial transaction.',
        "Every bank shall carry out customer due diligence and must not open anonymous accounts.",
        "Banks may use digital KYC.",
    ],
    "md_2": ["A small finance bank shall maintain a CRR.", "Banks should review this annually."],
    "md_3": ["Payments banks are required to report every quarter.", "What Payments Banks Shall Disclose"],
}


@pytest.fixture
def corpus(tmp_path: Path) -> PathResolver:
    resolver = PathResolver.from_config(make_config(), repo_root=tmp_path)
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), MANIFEST)
    write_jsonl(resolver.write_path("matrix", "matrix_v1.jsonl"), CELLS)
    for doc_id, texts in PARAGRAPHS.items():
        write_jsonl(
            resolver.write_path("processed", f"{doc_id}.jsonl"),
            [{"paragraph_id": f"{doc_id}::p{i:05d}", "document_id": doc_id, "position": i, "text": t}
             for i, t in enumerate(texts)],
        )
    return resolver


def test_corpus_extraction_end_to_end(corpus):
    candidates, scan = extract_corpus_candidates(corpus, make_config())
    by_id = {c.paragraph_id: c for c in candidates}

    assert scan["paragraphs_scanned"] == 8
    assert len(candidates) == 6
    assert by_id["md_1::p00000"].exclusion_reason == EXCLUDED_BOILERPLATE
    assert by_id["md_1::p00001"].exclusion_reason == EXCLUDED_BOILERPLATE
    assert by_id["md_1::p00002"].cue_matched == ["shall", "must not"]
    assert by_id["md_1::p00002"].matrix_cell == "ec_commercial_banks|sf_kyc"
    assert by_id["md_2::p00000"].matrix_cell is None
    assert by_id["md_3::p00001"].cue_exclusions == [EXCLUSION_HEADER]
    raw = {m["document_id"]: m["entity_class_raw"] for m in MANIFEST}
    assert all(c.entity_class == raw[c.document_id] for c in candidates)

    metrics = extraction_metrics(candidates, scan)
    assert metrics["cue_matches_total"] == 7
    assert metrics["cue_matches_excluded"] == 3
    assert metrics["rejection_rate_cue_level"] == 3 / 7
    assert metrics["candidates_kept"] == 3
    assert metrics["rejection_rate_zero_flag"] is False
    assert metrics["paragraphs_should_without_cue"] == 1


def test_missing_corpus_refuses_to_write_an_empty_file(tmp_path):
    resolver = PathResolver.from_config(make_config(), repo_root=tmp_path)
    write_jsonl(resolver.write_path("metadata", "document_manifest.jsonl"), MANIFEST)
    write_jsonl(resolver.write_path("matrix", "matrix_v1.jsonl"), CELLS)
    with pytest.raises(FileNotFoundError):
        extract_corpus_candidates(resolver, make_config())


def test_candidate_file_round_trips_through_schema(corpus):
    candidates, _ = extract_corpus_candidates(corpus, make_config())
    path = persist_candidates(candidates, corpus)
    assert path.parent.name == CANDIDATES_SUBDIR and path.name == CANDIDATES_FILENAME
    rows = read_jsonl(path)
    assert len(rows) == len(candidates)
    for row in rows:
        record = ObligationCandidate.from_dict(row)
        assert record.validate() == []
        assert set(row) == set(ObligationCandidate.field_names())
    assert len({r["candidate_id"] for r in rows}) == len(rows)


def test_zero_rejection_rate_is_flagged():
    c = build_candidate(para(), entity_class="X", matrix_cell=None)
    assert extraction_metrics([c], {"paragraphs_scanned": 1})["rejection_rate_zero_flag"] is True


# -- stop condition: schema drift -------------------------------------------


def test_missing_matrix_cell_is_schema_drift():
    manifest = [{"document_id": "md_9", "entity_class": "Commercial Banks", "subject_family": "Nonexistent"}]
    with pytest.raises(SchemaDriftError):
        document_cell_map(manifest, CELLS)


def test_cell_not_listing_the_document_is_schema_drift():
    manifest = [{"document_id": "md_9", "entity_class": "Commercial Banks", "subject_family": "KYC"}]
    with pytest.raises(SchemaDriftError):
        document_cell_map(manifest, CELLS)


def test_corpus_run_stops_on_drift(corpus):
    cells = [dict(CELLS[0], source_directions=[])] + CELLS[1:]
    write_jsonl(corpus.write_path("matrix", "matrix_v1.jsonl"), cells)
    with pytest.raises(SchemaDriftError):
        extract_corpus_candidates(corpus, make_config())


# -- regression: Phase 1 artifacts untouched ---------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pilot_candidates_untouched_by_extraction(corpus):
    pilot = corpus.write_path("benchmark", "pilot_candidates.jsonl")
    pilot.write_text(json.dumps({"label_id": "t1_pilot_x", "status": "candidate"}) + "\n", encoding="utf-8")
    task = corpus.write_path("benchmark", "tasks", "annotation_karan.csv")
    task.write_text("label_id,applies_to\nt1_pilot_x,Commercial Banks\n", encoding="utf-8")
    before_bytes = {pilot: _sha(pilot), task: _sha(task)}
    before = protected_file_hashes(corpus)
    assert len(before) == 2

    candidates, _ = extract_corpus_candidates(corpus, make_config())
    persist_candidates(candidates, corpus)
    sample_path = corpus.write_path("benchmark", CANDIDATES_SUBDIR, "t1_precision_sample_v1.csv")
    write_precision_sample(draw_precision_sample(candidates), sample_path)

    assert_unchanged(before, protected_file_hashes(corpus))
    assert {p: _sha(p) for p in before_bytes} == before_bytes


def test_cli_run_leaves_pilot_candidates_byte_identical(corpus, tmp_path, monkeypatch):
    from scripts import run_candidates

    pilot = corpus.write_path("benchmark", "pilot_candidates.jsonl")
    pilot.write_text('{"label_id": "t1_pilot_x"}\n', encoding="utf-8")
    digest = _sha(pilot)

    monkeypatch.setattr(run_candidates, "load_config", lambda _path=None: make_config())
    monkeypatch.setattr(
        run_candidates.PathResolver, "from_config",
        classmethod(lambda cls, cfg, **kw: corpus),
    )
    # v4's sample stage draws from v3's output, so v3 runs first.
    assert run_candidates.main(["all", "--rules", "v3"]) == 0
    assert run_candidates.main(["all"]) == 0
    assert _sha(pilot) == digest
    assert (tmp_path / "data/benchmark/candidates" / CANDIDATES_FILENAME).is_file()


def test_protected_file_change_is_detected():
    with pytest.raises(ProtectedFileChanged):
        assert_unchanged({"a": "1"}, {"a": "2"})
    with pytest.raises(ProtectedFileChanged):
        assert_unchanged({}, {"pilot_candidates.jsonl": "1"})


# -- precision sample --------------------------------------------------------


def test_allocation_spreads_across_small_classes():
    sizes = {"big": 5000, "mid": 400, "tiny": 1, **{f"c{i}": 30 for i in range(16)}}
    allocation = allocate_sample(sizes, 40)
    assert sum(allocation.values()) == 40
    assert len(allocation) == 19
    assert allocation["tiny"] == 1
    assert allocation["big"] >= allocation["c0"]


def test_allocation_never_exceeds_availability():
    assert allocate_sample({"a": 3, "b": 1}, 40) == {"a": 3, "b": 1}


def _candidates(n_per_class: dict[str, int]) -> list[ObligationCandidate]:
    out = []
    for cls, n in n_per_class.items():
        for i in range(n):
            out.append(build_candidate(para(f"md_{cls}::p{i:05d}"), entity_class=cls, matrix_cell=None))
    return out


def test_sample_is_deterministic_and_excludes_boilerplate():
    pool = _candidates({"A": 50, "B": 50, "C": 3})
    pool.append(build_candidate(para("md_Z::p00000", '"X" shall mean Y.'), entity_class="Z", matrix_cell=None))
    first = draw_precision_sample(pool)
    second = draw_precision_sample(pool)
    assert [c.candidate_id for c in first] == [c.candidate_id for c in second]
    assert len(first) == 40
    assert {c.entity_class for c in first} == {"A", "B", "C"}
    assert all(c.exclusion_reason is None for c in first)


def test_filled_sample_is_never_silently_overwritten(tmp_path):
    path = tmp_path / "sample.csv"
    sample = draw_precision_sample(_candidates({"A": 5}), n=5)
    write_precision_sample(sample, path)
    rows = read_sample(path)
    rows[0]["is_obligation"] = "y"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(SampleOverwriteError):
        write_precision_sample(sample, path)
    write_precision_sample(sample, path, force=True)
    assert (tmp_path / "sample.csv.bak").is_file()


def test_precision_scoring_counts_and_stop_condition():
    rows = [{"candidate_id": str(i), "entity_class": "A", "is_obligation": "y" if i < 27 else "n"} for i in range(40)]
    result = score_precision_sample(rows)
    assert (result["true_obligation"], result["not_obligation"]) == (27, 13)
    assert result["precision"] == 27 / 40
    assert result["precision_stop_triggered"] is True

    rows = [{"candidate_id": str(i), "entity_class": "A", "is_obligation": "y" if i < 28 else "n"} for i in range(40)]
    assert score_precision_sample(rows)["precision_stop_triggered"] is False


def test_sample_can_exclude_earlier_rows_and_renumber(tmp_path):
    pool = _candidates({"A": 50, "B": 50})
    first = draw_precision_sample(pool, seed=1)
    second = draw_precision_sample(pool, seed=2, exclude_ids=[c.candidate_id for c in first])
    assert len(second) == 40
    assert not {c.candidate_id for c in first} & {c.candidate_id for c in second}

    path = write_precision_sample(second, tmp_path / "v2.csv", index_start=41)
    assert [int(r["sample_index"]) for r in read_sample(path)] == list(range(41, 81))


def test_partial_sample_reports_not_yet_measured():
    rows = [{"candidate_id": "1", "is_obligation": "y"}, {"candidate_id": "2", "is_obligation": ""}]
    result = score_precision_sample(rows)
    assert result["precision"] == "NOT YET MEASURED"
    assert result["precision_stop_triggered"] is None
    assert result["unjudged"] == 1
