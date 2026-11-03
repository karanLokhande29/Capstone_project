"""P2-001-CORRECTIVE-v2 section E: the general ``non_action_effect`` exclusion.

All 10 false positives the two hand-review rounds found are fixtures here (the
six from round 1, the four from round 2). Each is tested both as the fragment
the corrective prompts quote and as the full sentence from the corpus paragraph
the reviewer saw. The regressions confirm P2-001's own definitional, heading,
procedural and quoted-statute exclusions are unchanged under v3.
"""

from __future__ import annotations

import pytest

from src.benchmark.candidates import (
    EXCLUDED_BOILERPLATE,
    EXCLUSION_DEFINITIONAL,
    EXCLUSION_HEADER,
    EXCLUSION_PROCEDURAL,
    EXCLUSION_QUOTED_STATUTE,
    NAE_ACCESS_SCOPE,
    NAE_CROSS_REFERENCE,
    NAE_DEFINITIONAL,
    NAE_DISCLOSURE_SCOPE,
    NAE_LEGAL_EFFECT,
    NON_ACTION_EFFECT,
    RULES_V1,
    RULES_V2,
    RULES_V3,
    ObligationCandidate,
    build_candidate,
    classify_paragraph_cues,
    paragraph_exclusion_reason,
)


# Splits long real-corpus fixture strings so the public source holds no >= 30-word run of RBI text
# (P5-001 task 3); the runtime value of every string is unchanged.
_J = ""

def exclusions(text: str, rules: str = RULES_V3, previous: str | None = None) -> list[str | None]:
    return [c.exclusion for c in classify_paragraph_cues(text, previous, rules=rules)]


# -- the 10 known false positives ---------------------------------------------

ROUND_1 = [
    # (v1 sample row, text, expected subtype)
    ("r1#9", "23. An AIFI shall be governed by the instructions contained in Master Direction – Reserve Bank "
             "of India (Commercial Paper and Non-Convertible Debentures) Directions, 2024.", NAE_CROSS_REFERENCE),
    ("r1#30", "Provided that, the credit facilities mentioned at sub-paras (iv) and (v) above shall be subject "
              "to the prudential ceilings " + _J + "and norms prescribed for various loans to individuals in Reserve Bank "
              "of India Directions, 2025.", NAE_CROSS_REFERENCE),
    ("r1#36", "The requirement of ensuring minimum investment in G-Sec and T-Bills on a daily basis will not "
              "be applicable " + _J + "to bank-PDs who shall be guided by the extant guidelines applicable to banks.",
     NAE_CROSS_REFERENCE),
    ("r1#40", "3.2.3 The admission of an entity to a clearing house shall be subject to the entity\nfulfilling "
              "the requirements as laid down in the Uniform Regulations and Rules for\nBankers' Clearing House "
              "(URRBCH), procedural guidelines and instructions issued in\nthis regard, from time to time.",
     NAE_CROSS_REFERENCE),
    ("r1#20", "(4) For the purpose of the KCC Scheme, crop seasons shall be standardized at twelve months for "
              "short duration crops and eighteen months for long duration crops.", NAE_DEFINITIONAL),
    ("r1#37", "86. Notwithstanding paragraph 85, compromise settlements where the time for payment of the "
              "agreed settlement amount exceeds three months shall be treated as restructuring.", NAE_DEFINITIONAL),
]

ROUND_2 = [
    # (v2 sample row, text, expected subtype)
    ("r2#42", "Note: This disclosure shall exclude Level 3 assets where the valuation of the asset is the "
              "price declared by FBIL / FIMMDA for that asset.", NAE_DISCLOSURE_SCOPE),
    ("r2#60", "17. As stated in paragraph 9, the outsourcing of any activity by a bank shall not diminish its "
              "obligations including " + _J + "to its customers and RBI, and those of its Board and Senior Management.",
     NAE_LEGAL_EFFECT),
    ("r2#61", "(5) Instruction at (4) above shall also apply to sale of the bank’s own products, payment of "
              "dues of credit cards / sale and reloading of prepaid / travel cards.", NAE_CROSS_REFERENCE),
    ("r2#73", "(iii) Such a CI shall have access to Credit Information Reports pertaining to only those "
              "borrowers which were onboarded and reported to CICs before the cancellation of their license.",
     NAE_ACCESS_SCOPE),
]

#: The fragments exactly as the two corrective prompts quote them.
QUOTED_FRAGMENTS = [
    ("An AIFI shall be governed by the instructions contained in Master Direction...", NAE_CROSS_REFERENCE),
    ("...shall be subject to the prudential ceilings and norms prescribed...", NAE_CROSS_REFERENCE),
    ("...bank-PDs who shall be guided by the extant guidelines applicable to banks.", NAE_CROSS_REFERENCE),
    ("crop seasons shall be standardized at twelve months...", NAE_DEFINITIONAL),
    ("...time for payment... exceeds three months shall be treated as restructuring.", NAE_DEFINITIONAL),
    ("this disclosure shall exclude Level 3 assets where...", NAE_DISCLOSURE_SCOPE),
    ("outsourcing... shall not diminish its obligations...", NAE_LEGAL_EFFECT),
    ("Instruction (4) shall also apply to...", NAE_CROSS_REFERENCE),
    ("shall have access to... only those borrowers which...", NAE_ACCESS_SCOPE),
]


def test_there_are_ten_known_fixtures():
    assert len(ROUND_1) == 6 and len(ROUND_2) == 4


@pytest.mark.parametrize("row,text,expected", ROUND_1 + ROUND_2)
def test_known_false_positives_are_non_action_effect(row, text, expected):
    assert exclusions(text) == [expected], row


@pytest.mark.parametrize("row,text,expected", ROUND_1 + ROUND_2)
def test_known_false_positives_are_excluded_paragraphs(row, text, expected):
    candidate = build_candidate(
        {"paragraph_id": "md_x::p00001", "document_id": "md_x", "text": text},
        entity_class="X", matrix_cell=None, rules=RULES_V3,
    )
    assert candidate.exclusion_reason == expected
    assert candidate.exclusion_reason.startswith(NON_ACTION_EFFECT + ":")
    assert candidate.validate() == []


@pytest.mark.parametrize("text,expected", QUOTED_FRAGMENTS)
def test_quoted_fragments_are_non_action_effect(text, expected):
    assert exclusions(text) == [expected]


@pytest.mark.parametrize("row,text,expected", ROUND_2)
def test_round_2_fixtures_were_kept_by_v2(row, text, expected):
    # Confirms these are genuinely new catches, not relabelled v2 exclusions.
    assert exclusions(text, RULES_V2) == [None], row


# -- the rest of each subtype ---------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The interpretation of any provision of these Directions given by the Reserve Bank shall be final "
         "and binding.", NAE_LEGAL_EFFECT),
        ("The liability of the borrowers in respect of the underlying loan shall remain unaffected.",
         NAE_LEGAL_EFFECT),
        ("Outsourcing arrangements shall not affect the rights of its customers against the bank.",
         NAE_LEGAL_EFFECT),
        ("The bank's right to recovery shall not be undermined in any manner.", NAE_LEGAL_EFFECT),
        ("Such cases shall attract penal provisions in terms of the Master Direction.", NAE_LEGAL_EFFECT),
        ("The provisions of paragraph 12 shall not apply to such accounts.", NAE_CROSS_REFERENCE),
        ("These norms shall apply mutatis mutandis to UCBs.", NAE_CROSS_REFERENCE),
        ("Claims on the Central Government shall attract zero risk weight.", NAE_DEFINITIONAL),
        ("A bank's investment in security receipts shall be risk weighted at 150 per cent.", NAE_DEFINITIONAL),
        ("The terms herein shall bear the meanings assigned to them below:", NAE_DEFINITIONAL),
        ("A bank shall have the option to offer loans with reset dates.", NAE_ACCESS_SCOPE),
        ("A bank shall be allowed to invest 20 per cent in a subsidiary.", NAE_ACCESS_SCOPE),
        ("Marginal farmers shall also be eligible for a flexible credit limit.", NAE_ACCESS_SCOPE),
        ("301. It shall also be in order for the bank to remit the amount to the overseas bank.",
         NAE_ACCESS_SCOPE),
        ("The report shall include reasons for such usage and corrective steps initiated.", NAE_DISCLOSURE_SCOPE),
    ],
)
def test_subtype_coverage(text, expected):
    assert exclusions(text) == [expected]


# -- genuine duties stay candidates (the §B.2 test) --------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Every bank shall maintain a register of complaints.",
        "Banks shall continue to report such accounts to CRILC every month.",
        "The NBFC shall apply to the Reserve Bank for a certificate of registration.",
        "The bank shall apply a haircut of 10 per cent to the collateral value.",
        "An NBFC shall not be permitted to accept demand deposits.",
        "The premature withdrawal option shall be allowed to the survivors without seeking consent.",
        "In such a case, it shall include such missed out data in the loss data set in the subsequent year.",
        "The Board-approved policy shall include the following elements.",
        "The EWS framework shall be subject to suitable validation in accordance with the directions of RMCB.",
        "Customer information shall be treated as confidential.",
        "Levy of foreclosure charges shall be subject to a ceiling of 2 per cent.",
    ],
)
def test_duties_are_not_non_action_effect(text):
    assert exclusions(text) == [None]


def test_mixed_span_keeps_the_candidate():
    text = ("Outsourcing shall not diminish the bank's obligations. The bank shall review the service "
            "provider annually.")
    assert exclusions(text) == [NAE_LEGAL_EFFECT, None]
    candidate = build_candidate({"paragraph_id": "md_x::p00001", "document_id": "md_x", "text": text},
                                entity_class="X", matrix_cell=None)
    assert candidate.exclusion_reason is None
    assert candidate.validate() == []


# -- regression: P2-001 exclusions unchanged under v3 ------------------------------

UNCHANGED = [
    ('"Bank" shall mean a banking company as defined in the Act.', [EXCLUSION_DEFINITIONAL]),
    ('"Deposit" shall have the same meaning as assigned in the Act.', [EXCLUSION_DEFINITIONAL]),
    ('"Credit facility" shall include loans and advances.', [EXCLUSION_DEFINITIONAL]),
    ("Such a company shall be deemed to be a non-banking financial company.", [EXCLUSION_DEFINITIONAL]),
    ("What The Bank Shall Disclose", [EXCLUSION_HEADER]),
    ("Chapter III – Outsourcing of Financial Services\nA. Activities that shall not be outsourced",
     [EXCLUSION_HEADER]),
    ("These Directions shall come into force with immediate effect.", [EXCLUSION_PROCEDURAL]),
    ("These Directions shall apply to every Scheduled Commercial Bank.", [EXCLUSION_PROCEDURAL]),
    ("57. The provisions of these Directions shall be in addition to, and not in derogation of any other law.",
     [EXCLUSION_PROCEDURAL]),
    ("Section 26A of the Act reads as under: every bank shall transfer unclaimed deposits.",
     [EXCLUSION_QUOTED_STATUTE]),
]


@pytest.mark.parametrize("text,expected", UNCHANGED)
@pytest.mark.parametrize("rules", [RULES_V1, RULES_V2, RULES_V3])
def test_p2001_exclusions_unchanged(text, expected, rules):
    assert exclusions(text, rules) == expected


def test_permissive_option_changes_only_in_v3():
    # P2-001 never had a permissive-option exclusion: v1 and v2 kept this cue.
    # v3 excludes it because §B.1 lists "shall have the option to" under
    # non_action_effect. v1/v2 behaviour is pinned so the history stays true.
    text = ("(iv) Any user who is otherwise eligible to be classified as a non-retail user shall have the "
            "option to get classified as a retail user.")
    assert exclusions(text, RULES_V1) == [None]
    assert exclusions(text, RULES_V2) == [None]
    assert exclusions(text, RULES_V3) == [NAE_ACCESS_SCOPE]


# -- paragraph-level exclusion_reason --------------------------------------------


@pytest.mark.parametrize(
    "cues,expected",
    [
        ([None], None),
        ([NAE_LEGAL_EFFECT, None], None),
        ([EXCLUSION_DEFINITIONAL, EXCLUSION_PROCEDURAL], EXCLUDED_BOILERPLATE),
        ([NAE_LEGAL_EFFECT], "non_action_effect:legal_effect"),
        ([NAE_LEGAL_EFFECT, NAE_CROSS_REFERENCE, NAE_LEGAL_EFFECT], "non_action_effect:cross_reference+legal_effect"),
        ([EXCLUSION_DEFINITIONAL, NAE_ACCESS_SCOPE], "excluded_boilerplate+non_action_effect:access_scope"),
        (["redirect_reference", "classification_deeming"], EXCLUDED_BOILERPLATE),
    ],
)
def test_paragraph_exclusion_reason(cues, expected):
    assert paragraph_exclusion_reason(cues) == expected


@pytest.mark.parametrize(
    "k,lo,hi",
    [(34, 0.709, 0.929), (27, 0.520, 0.799), (31, 0.625, 0.877), (32, 0.652, 0.895)],
)
def test_wilson_interval_matches_the_reported_figures(k, lo, hi):
    from src.benchmark.candidates import wilson_interval

    got_lo, got_hi = wilson_interval(k, 40)
    assert round(got_lo, 3) == lo and round(got_hi, 3) == hi


def test_score_rejects_a_labelled_file_from_another_round(tmp_path):
    from scripts import run_candidates
    from src.common.paths import PathResolver
    from tests.conftest import make_config

    resolver = PathResolver.from_config(make_config(), repo_root=tmp_path)
    folder = resolver.write_path("benchmark", "candidates", "t1_precision_sample_v3.csv").parent
    (folder / "t1_precision_sample_v3.csv").write_text(
        "sample_index,candidate_id,is_obligation\n81,t1c_a,\n", encoding="utf-8")
    (folder / "other_round.csv").write_text(
        "sample_index,candidate_id,is_obligation\n41,t1c_b,y\n", encoding="utf-8")
    (folder / "right_round.csv").write_text(
        "sample_index,candidate_id,is_obligation\n81,t1c_a,y\n", encoding="utf-8")

    with pytest.raises(run_candidates.SampleMismatchError):
        run_candidates.run_score({}, resolver, None, "v3", "other_round.csv")
    result = run_candidates.run_score({}, resolver, None, "v3", "right_round.csv")
    assert (result["true_obligation"], result["precision"]) == (1, 1.0)
    # read-only on the labelled file
    assert (folder / "right_round.csv").read_text(encoding="utf-8").endswith("81,t1c_a,y\n")


def test_validate_rejects_a_wrong_paragraph_reason():
    good = build_candidate(
        {"paragraph_id": "md_x::p00001", "document_id": "md_x",
         "text": "The interpretation given by the Reserve Bank shall be final and binding."},
        entity_class="X", matrix_cell=None,
    )
    assert good.exclusion_reason == NAE_LEGAL_EFFECT and good.validate() == []
    bad = ObligationCandidate.from_dict({**good.to_dict(), "exclusion_reason": EXCLUDED_BOILERPLATE})
    assert any("exclusion_reason" in e for e in bad.validate())
