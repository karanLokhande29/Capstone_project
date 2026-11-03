"""P2-001-V4 §B.7: the three v4 changes, what v4 must NOT change, the re-admit
sample and its per-group gate, and a byte-for-byte regression that v1-v3
still reproduce their candidate files.

The re-admission fixtures are spans from the step-1 examples (the v3 output
on the real corpus) plus round-2 rows #42 and #73, which Karan labelled as
obligations.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.benchmark.candidates import (
    EXCLUDED_BOILERPLATE,
    EXCLUSION_DEFINITIONAL,
    NAE_ACCESS_SCOPE,
    NAE_CROSS_REFERENCE,
    NAE_DEFINITIONAL,
    NAE_DISCLOSURE_SCOPE,
    NAE_LEGAL_EFFECT,
    READMIT_GROUP_ACCESS,
    READMIT_GROUP_DISCLOSURE,
    READMIT_GROUP_MEASUREMENT,
    READMIT_GROUPS,
    RULES_V1,
    RULES_V2,
    RULES_V3,
    RULES_V4,
    build_candidate,
    candidates_filename,
    classify_paragraph_cues,
    draw_readmit_sample,
    extract_corpus_candidates,
    matrix_cell_counts,
    readmitted_candidates,
    readmitted_group,
    score_by_group,
)

# Splits long real-corpus fixture strings so the public source holds no >= 30-word run of RBI text
# (P5-001 task 3); the runtime value of every string is unchanged.
_J = ""

REPO = Path(__file__).resolve().parents[1]


def exclusions(text: str, rules: str) -> list[str | None]:
    return [c.exclusion for c in classify_paragraph_cues(text, rules=rules)]


# -- the three v4 changes (fixtures from step 1) ------------------------------

ACCESS_RESTRICTIONS = [
    # round-2 #73, labelled an obligation (binding restriction)
    "(iii) Such a CI shall have access to Credit Information Reports pertaining to only those borrowers "
    "which were onboarded and reported to CICs before the cancellation of their license.",
    # md_13044::p00081
    "the System must have access to the required data from the CBS and / or other relevant applications "
    "of the bank and the borrowers.",
    # md_13597::p00177 (the cue on "RBI shall have access")
    "RBI shall have access to all information resources (online / in person) that are consumed by it.",
]
DISCLOSURE_SCOPE = [
    # round-2 #42, labelled an obligation
    "Note: This disclosure shall exclude Level 3 assets where the valuation of the asset is the price "
    "declared by FBIL / FIMMDA for that asset.",
    # md_13143::p00372
    "The disclosure shall also include:",
    # md_12990::p00086
    "(a) In respect of loans not in default that are transferred or acquired, the disclosures shall cover, "
    "inter alia, aspects such as weighted average maturity.",
    # md_13163::p00021
    "Further, the report shall also include the details of cost-benefit analysis.",
]
MEASUREMENT = [
    # md_13127::p00723
    "(i) Credit enhancements which are first loss positions shall be risk weighted at 1250 per cent.",
    # md_12983::p00234
    "(ii) An AIFI's investments in Tier 2 instruments issued by a bank / another AIFI shall attract risk "
    "weight as per paragraphs 37 to 40 of these directions.",
    # md_13114::p00185
    "Credit exposures on account of derivative transactions shall attract provisioning requirement as "
    "applicable to the loan assets in the 'standard' category.",
    # md_13159::p01048
    "The exposure shall be assigned the same risk weight as is applicable to the low-quality assessment.",
    "Claims on the Central Government shall attract zero risk weight.",
    "The open position shall attract a capital charge of 9 per cent.",
]


@pytest.mark.parametrize("text", ACCESS_RESTRICTIONS)
def test_access_restrictions_are_candidates_again(text):
    assert exclusions(text, RULES_V3) == [NAE_ACCESS_SCOPE]
    assert exclusions(text, RULES_V4) == [None]


@pytest.mark.parametrize("text", DISCLOSURE_SCOPE)
def test_disclosure_scope_rules_are_candidates_again(text):
    assert exclusions(text, RULES_V3) == [NAE_DISCLOSURE_SCOPE]
    assert exclusions(text, RULES_V4) == [None]


@pytest.mark.parametrize("text", MEASUREMENT)
def test_measurement_clauses_are_candidates_again(text):
    assert exclusions(text, RULES_V3) == [NAE_DEFINITIONAL]
    assert exclusions(text, RULES_V4) == [None]


@pytest.mark.parametrize(
    "text,group",
    [(t, READMIT_GROUP_ACCESS) for t in ACCESS_RESTRICTIONS]
    + [(t, READMIT_GROUP_DISCLOSURE) for t in DISCLOSURE_SCOPE]
    + [(t, READMIT_GROUP_MEASUREMENT) for t in MEASUREMENT],
)
def test_readmitted_group_attribution(text, group):
    cue = classify_paragraph_cues(text, rules=RULES_V3)[0]
    assert readmitted_group(text, cue.start) == group


def test_restricted_to_was_never_excluded():
    assert exclusions("Such lending shall be restricted to members of the society.", RULES_V3) == [None]
    assert exclusions("Such lending shall be restricted to members of the society.", RULES_V4) == [None]


# -- what v4 must NOT change -------------------------------------------------

STILL_EXCLUDED_IN_V4 = [
    # genuine permissions and options stay access_scope
    ("A bank shall have the option to offer loans with reset dates.", NAE_ACCESS_SCOPE),
    ("A bank shall be allowed to invest 20 per cent in a subsidiary.", NAE_ACCESS_SCOPE),
    ("The lender shall have the discretion to waive the charge.", NAE_ACCESS_SCOPE),
    ("301. It shall also be in order for the bank to remit the amount to the overseas bank.", NAE_ACCESS_SCOPE),
    # eligibility status is a non-obligation under the labelling line
    ("Marginal farmers shall also be eligible for a flexible credit limit.", NAE_ACCESS_SCOPE),
    # classification / deeming stays, including capital classification
    ("86. Notwithstanding paragraph 85, compromise settlements where the time for payment of the agreed "
     "settlement amount exceeds three months shall be treated as restructuring.", NAE_DEFINITIONAL),
    ("The amount raised through PDIs shall also be reckoned as Tier 1 Capital.", NAE_DEFINITIONAL),
    ("(4) For the purpose of the KCC Scheme, crop seasons shall be standardized at twelve months.", NAE_DEFINITIONAL),
    ("The terms herein shall bear the meanings assigned to them below:", NAE_DEFINITIONAL),
    # the other non_action_effect subtypes are untouched
    ("23. An AIFI shall be governed by the instructions contained in Master Direction – Reserve Bank of "
     "India Directions, 2024.", NAE_CROSS_REFERENCE),
    ("(5) Instruction at (4) above shall also apply to sale of the bank's own products.", NAE_CROSS_REFERENCE),
    ("17. The outsourcing of any activity by a bank shall not diminish its obligations.", NAE_LEGAL_EFFECT),
    ("The interpretation of any provision given by the Reserve Bank shall be final and binding.", NAE_LEGAL_EFFECT),
    # real definitions stay excluded as P2-001 boilerplate
    ('"Bank" shall mean a banking company as defined in the Act.', EXCLUSION_DEFINITIONAL),
    ('"Deposit" shall have the same meaning as assigned in the Act.', EXCLUSION_DEFINITIONAL),
]


@pytest.mark.parametrize("text,expected", STILL_EXCLUDED_IN_V4)
def test_v4_leaves_everything_else_as_v3(text, expected):
    assert exclusions(text, RULES_V3) == [expected]
    assert exclusions(text, RULES_V4) == [expected]


KNOWN_MISSES_LEFT_FOR_NEXT_VERSION = [
    "Further, the repeal of these directions shall not in any way prejudicially affect:",  # #98 (third cue)
    "provided that contracts involving currencies of Nepal and Bhutan shall not qualify under this definition.",
    "the surviving nominee or nominees shall be entitled to the Relief/Savings Bond and payment thereon.",
    "Borrowers who have committed frauds shall remain ineligible for restructuring.",
    "Reserve Bank shall issue directions to Authorised Persons through A.P. (DIR Series) Circulars.",
]


@pytest.mark.parametrize("text", KNOWN_MISSES_LEFT_FOR_NEXT_VERSION)
def test_known_misses_are_not_fixed_in_v4(text):
    assert exclusions(text, RULES_V3) == [None]
    assert exclusions(text, RULES_V4) == [None]


# -- re-admit pools, sample and per-group gate -------------------------------


def _para(pid: str, text: str) -> dict:
    return {"paragraph_id": pid, "document_id": pid.split("::")[0], "text": text}


def _pair(pid, text, cls="X"):
    v3 = build_candidate(_para(pid, text), entity_class=cls, matrix_cell=None, rules=RULES_V3)
    v4 = build_candidate(_para(pid, text), entity_class=cls, matrix_cell=None, rules=RULES_V4)
    return v3, v4


def test_readmitted_pools_attribute_each_paragraph_to_one_change():
    texts = {
        "md_a::p00001": ACCESS_RESTRICTIONS[0],
        "md_b::p00001": DISCLOSURE_SCOPE[0],
        "md_c::p00001": MEASUREMENT[0],
        "md_d::p00001": MEASUREMENT[0] + " " + DISCLOSURE_SCOPE[0],  # two changes
        "md_e::p00001": STILL_EXCLUDED_IN_V4[0][0],  # still excluded
        "md_f::p00001": "Every bank shall maintain a register.",  # kept by both
    }
    pairs = [_pair(pid, t) for pid, t in texts.items()]
    pools, multiple = readmitted_candidates([a for a, _ in pairs], [b for _, b in pairs])
    assert [c.paragraph_id for c in pools[READMIT_GROUP_ACCESS]] == ["md_a::p00001"]
    assert [c.paragraph_id for c in pools[READMIT_GROUP_DISCLOSURE]] == ["md_b::p00001"]
    assert [c.paragraph_id for c in pools[READMIT_GROUP_MEASUREMENT]] == ["md_c::p00001"]
    assert [c.paragraph_id for c in multiple] == ["md_d::p00001"]


def test_readmit_sample_is_10_per_group_shuffled_and_skips_earlier_rows():
    pools = {
        g: [build_candidate(_para(f"md_{g}{i}::p00001", "Banks shall comply."), entity_class=f"C{i % 4}",
                            matrix_cell=None) for i in range(25)]
        for g in READMIT_GROUPS
    }
    earlier = [pools[READMIT_GROUP_ACCESS][0].candidate_id]
    sample = draw_readmit_sample(pools, seed=20260928, exclude_ids=earlier)
    assert len(sample) == 30
    assert {g: sum(1 for _, x in sample if x == g) for g in READMIT_GROUPS} == {g: 10 for g in READMIT_GROUPS}
    assert earlier[0] not in {c.candidate_id for c, _ in sample}
    assert [g for _, g in sample] != sorted(g for _, g in sample)  # interleaved, not blocks
    again = draw_readmit_sample(pools, seed=20260928, exclude_ids=earlier)
    assert [c.candidate_id for c, _ in again] == [c.candidate_id for c, _ in sample]


def test_score_by_group_and_the_70_percent_gate():
    rows, group_of = [], {}
    for g, yes in ((READMIT_GROUP_ACCESS, 9), (READMIT_GROUP_DISCLOSURE, 7), (READMIT_GROUP_MEASUREMENT, 6)):
        for i in range(10):
            cid = f"{g}{i}"
            group_of[cid] = g
            rows.append({"candidate_id": cid, "is_obligation": "y" if i < yes else "n"})
    result = score_by_group(rows, group_of)
    assert result["groups"][READMIT_GROUP_ACCESS]["precision"] == 0.9
    assert result["groups"][READMIT_GROUP_DISCLOSURE]["restore_v3_exclusion"] is False  # exactly 70% passes
    assert result["groups"][READMIT_GROUP_MEASUREMENT]["restore_v3_exclusion"] is True
    assert result["groups_failing_gate"] == [READMIT_GROUP_MEASUREMENT]
    assert (result["overall"]["true_obligation"], result["overall"]["sample_size"]) == (22, 30)


def test_matrix_cell_counts_cover_kept_candidates_only():
    kept = build_candidate(_para("md_a::p00001", "Banks shall comply."), entity_class="X", matrix_cell="ec|sf")
    excluded = build_candidate(_para("md_b::p00001", '"Bank" shall mean a bank.'), entity_class="X",
                               matrix_cell="ec|sf2")
    counts = matrix_cell_counts([kept, excluded])
    assert counts["candidates_with_matrix_cell"] == 1
    assert counts["distinct_matrix_cells"] == 1


# -- distinct-text scoring (P2-001-V4-FINISH §B.4) ------------------------------


def test_near_duplicates_cluster_one_word_variants_and_page_break_truncations():
    from src.benchmark.candidates import near_duplicate_clusters

    sentences = [
        "such a ci shall have access to credit information reports pertaining to only those borrowers which "
        "were onboarded and reported " + _J + "to cics before the cancellation of their license",
        "such a ci shall have access to credit information reports pertaining to " + _J + "only those borrowers which "
        "were onboarded and reported to cics before the cancellation of their cor",
        "the annual report of " + _J + "the bank shall also include the progress in respect of extending banking services",
        "the annual report of the bank shall " + _J + "also include the progress in respect",  # cut at a page break
        "claims on the central government shall attract zero risk weight",
    ]
    assert near_duplicate_clusters(sentences) == [[0, 1], [2, 3], [4]]


def test_score_distinct_counts_a_text_once_and_flags_conflicts():
    from src.benchmark.candidates import score_distinct

    rows = [{"sample_index": str(i), "is_obligation": v} for i, v in enumerate(["y", "y", "y", "n", "y", "n"])]
    sentences = ["a shall do x", "a shall do x", "b shall do y", "b shall do y", "c shall do z", "d shall mean q"]
    result = score_distinct(rows, sentences)
    assert (result["rows"], result["distinct_texts"], result["true_obligation"]) == (6, 4, 2)
    assert result["repeated_texts"] == [["0", "1"], ["2", "3"]]
    assert result["clusters_with_conflicting_labels"] == [["2", "3"]]


def test_cue_sentence_strips_enumerators_and_page_numbers():
    from src.benchmark.candidates import cue_sentence

    text = "(iii) Such a CI shall have access to reports. 26"
    start = text.index("shall")
    assert cue_sentence(text, start, start + 5) == "such a ci shall have access to reports"


@pytest.mark.parametrize("source,counts", [("manual", True), ("ai_assisted", False), (None, False)])
def test_label_source_decides_whether_a_score_counts_toward_the_gate(tmp_path, source, counts):
    from scripts import run_candidates
    from src.common.paths import PathResolver
    from tests.conftest import make_config

    resolver = PathResolver.from_config(make_config(), repo_root=tmp_path)
    sample = resolver.write_path("benchmark", "candidates", "t1_precision_sample_v3.csv")
    sample.write_text("sample_index,candidate_id,is_obligation\n81,t1c_a,y\n", encoding="utf-8")
    result = run_candidates.run_score({}, resolver, None, "v3", None, source)
    assert result["label_source"] == (source or "undeclared")
    assert result["counts_toward_gate"] is counts


# -- regression: v1, v2, v3 reproduce their files byte for byte ---------------


@pytest.mark.parametrize("rules", [RULES_V1, RULES_V2, RULES_V3])
def test_earlier_rule_versions_reproduce_their_candidate_files(rules):
    """Runs against the real corpus; skipped where the gitignored data is absent."""
    from src.common.config import load_config
    from src.common.paths import PathResolver

    target = REPO / "data" / "benchmark" / "candidates" / candidates_filename(rules)
    if not target.is_file() or not (REPO / "data" / "processed").is_dir():
        pytest.skip("real corpus / candidate file not present")
    cfg = load_config()
    cfg["logging"]["to_file"] = False
    resolver = PathResolver.from_config(cfg)
    candidates, _ = extract_corpus_candidates(resolver, cfg, rules=rules)
    payload = "".join(json.dumps(c.to_dict(), ensure_ascii=False) + "\n" for c in candidates).encode("utf-8")
    assert payload == target.read_bytes()
