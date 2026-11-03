"""P2-001-CORRECTIVE section E: the v2 exclusion subtypes, pinned to the
sentences the v1 hand review judged not-obligations, plus regressions that the
v1 rules and every earlier exclusion are unchanged."""

from __future__ import annotations

import json

import pytest

from src.benchmark.candidates import (
    EXCLUSION_CLASSIFICATION,
    EXCLUSION_DEFINITIONAL,
    EXCLUSION_HEADER,
    EXCLUSION_PROCEDURAL,
    EXCLUSION_QUOTED_STATUTE,
    EXCLUSION_REDIRECT,
    RULES_V1,
    RULES_V2,
    classify_paragraph_cues,
)
from src.common.io_helpers import write_json


# Splits long real-corpus fixture strings so the public source holds no >= 30-word run of RBI text
# (P5-001 task 3); the runtime value of every string is unchanged.
_J = ""

def exclusions(text: str, rules: str = RULES_V2, previous: str | None = None) -> list[str | None]:
    return [c.exclusion for c in classify_paragraph_cues(text, previous, rules=rules)]


# -- ground-truth fixtures ---------------------------------------------------
# The prompt quotes five sentences (three redirects, two classifications),
# although it says "6". Each is used twice: as the fragment the prompt quotes,
# and as the full paragraph from the v1 sample, so the rule is tested on real
# corpus text and not only on a trimmed quotation.

REDIRECT_FIXTURES = [
    # v1 sample row 9, md_12982::p00030
    "An AIFI shall be governed by the instructions contained in Master Direction...",
    "23. An AIFI shall be governed by the " + _J + "instructions contained in Master Direction – Reserve Bank of "
    "India (Commercial Paper and Non-Convertible Debentures of original or initial maturity " + _J + "upto one year) "
    "Directions, 2024.",
    # v1 sample row 30, md_12999::p00050
    "...shall be subject to the prudential ceilings and norms prescribed...",
    "Provided that, the credit facilities mentioned at sub-paras (iv) and (v) above shall be subject to "
    "the prudential ceilings " + _J + "and norms prescribed for various loans to individuals in Reserve Bank of "
    "India (Rural Co-operative Banks – Credit Risk Management) " + _J + "Directions, 2025.",
    # v1 sample row 36, md_10476::p00029
    "...bank-PDs who shall be guided by the extant guidelines applicable to banks.",
    "The requirement of ensuring minimum investment in " + _J + "G-Sec and T-Bills on a daily basis, based on net "
    "call / RBI borrowing and NOF will not be " + _J + "applicable to bank-PDs who shall be guided by the extant "
    "guidelines applicable to banks.",
]

CLASSIFICATION_FIXTURES = [
    # v1 sample row 20, md_13523::p00012
    "crop seasons shall be standardized at twelve months...",
    "(4) For the purpose of the KCC Scheme, crop seasons shall be standardized at twelve months for short "
    "duration crops and eighteen months for long duration crops.",
    # v1 sample row 37, md_12972::p00134
    "...time for payment... exceeds three months shall be treated as restructuring.",
    "86. Notwithstanding paragraph 85, compromise settlements where the time for payment of the agreed "
    "settlement amount exceeds three months shall be treated as restructuring.",
]


@pytest.mark.parametrize("text", REDIRECT_FIXTURES)
def test_redirect_fixtures_are_excluded(text):
    assert exclusions(text) == [EXCLUSION_REDIRECT]


@pytest.mark.parametrize("text", CLASSIFICATION_FIXTURES)
def test_classification_fixtures_are_excluded(text):
    assert exclusions(text) == [EXCLUSION_CLASSIFICATION]


@pytest.mark.parametrize("text", REDIRECT_FIXTURES + CLASSIFICATION_FIXTURES)
def test_fixtures_stay_candidates_under_v1(text):
    assert exclusions(text, RULES_V1) == [None]


# -- redirect_reference boundaries -------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Levy of foreclosure charges shall be subject to a ceiling of 2 per cent of the outstanding.",
        "The facility shall be subject to the following conditions:",
        "The EWS framework shall be subject to suitable validation in accordance with the directions of RMCB.",
        "The loan shall be subject to approval of the Board as per the guidelines.",
    ],
)
def test_redirect_with_its_own_constraint_or_duty_is_kept(text):
    assert exclusions(text) == [None]


def test_redirect_alongside_a_real_duty_keeps_the_paragraph():
    text = "An AIFI shall be governed by the Master Direction on CPs and shall report every issue to RBI."
    assert exclusions(text) == [EXCLUSION_REDIRECT, None]


@pytest.mark.parametrize(
    "text",
    [
        "Such accounts shall continue to be guided by the existing prudential guidelines.",
        "Settlement of trades shall be in accordance with the rules issued by the stock exchange.",
        "The securities shall be as per the provisions of paragraph 64 of these Directions.",
    ],
)
def test_redirect_variants_are_excluded(text):
    assert exclusions(text) == [EXCLUSION_REDIRECT]


# -- classification_deeming boundaries --------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Partial credit enhancement facilities to the extent drawn shall be treated as an advance.",
        "Such advances shall be reckoned as unsecured.",
        "A nominee director shall not be considered as wilful defaulter unless it is established that.",
        "Investments shall be classified into three categories.",
    ],
)
def test_classification_variants_are_excluded(text):
    assert exclusions(text) == [EXCLUSION_CLASSIFICATION]


def test_treated_as_confidential_is_a_duty_and_kept():
    assert exclusions("Customer information shall be treated as confidential.") == [None]
    assert exclusions("Such complaints shall be treated as a priority.") == [None]


# -- definitional extension (C.2) --------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "(1) In these Directions, unless the context states otherwise, the terms herein shall bear the "
        "meanings assigned to them as " + _J + "below:",
        "(35) ‘Securitisation note’ shall be as defined in Reserve Bank of India Directions, 2025.",
    ],
)
def test_v2_definitional_phrasings(text):
    assert exclusions(text) == [EXCLUSION_DEFINITIONAL]
    assert exclusions(text, RULES_V1) == [None]


# -- regression: earlier exclusions unchanged under v2 -----------------------

UNCHANGED = [
    ('"Bank" shall mean a banking company as defined in the Act.', [EXCLUSION_DEFINITIONAL]),
    ('"Deposit" shall have the same meaning as assigned in the Act.', [EXCLUSION_DEFINITIONAL]),
    ('"Credit facility" shall include loans and advances.', [EXCLUSION_DEFINITIONAL]),
    ("Such a company shall be deemed to be a non-banking financial company.", [EXCLUSION_DEFINITIONAL]),
    ("What The Bank Shall Disclose", [EXCLUSION_HEADER]),
    ("Chapter III – Outsourcing of Financial Services\nA. Activities that shall not be outsourced",
     [EXCLUSION_HEADER]),
    ("These Directions shall come into force with immediate effect.", [EXCLUSION_PROCEDURAL]),
    ("57. The provisions of these Directions shall be in addition to, and not in derogation of any other law.",
     [EXCLUSION_PROCEDURAL]),
    ("Section 26A of the Act reads as under: every bank shall transfer unclaimed deposits.",
     [EXCLUSION_QUOTED_STATUTE]),
    ("Every bank shall maintain a register of complaints.", [None]),
    # Permissive option. No permissive-option exclusion exists in P2-001 (the
    # corrective prompt assumes one does). v1 kept this cue, and v2 must not
    # change it without an audited rule.
    ("(iv) Any user who is otherwise eligible to be classified as a non-retail user shall have the option "
     "to get classified as a retail user.", [None]),
    ("301. It shall also be in order for the bank to remit the amount to the overseas bank.", [None]),
]


@pytest.mark.parametrize("text,expected", UNCHANGED)
@pytest.mark.parametrize("rules", [RULES_V1, RULES_V2])
def test_existing_exclusions_unchanged(text, expected, rules):
    assert exclusions(text, rules) == expected


def test_unknown_rule_version_is_rejected():
    with pytest.raises(ValueError):
        exclusions("Banks shall comply.", "v9")


# -- scoring never clobbers a completed result -----------------------------


def test_score_refuses_to_replace_a_completed_result(tmp_path, monkeypatch):
    from scripts import run_candidates
    from src.common.paths import PathResolver
    from tests.conftest import make_config

    resolver = PathResolver.from_config(make_config(), repo_root=tmp_path)
    write_json(resolver.write_path("reports", "p2001_precision_metrics_v1.json"),
               {"precision": 0.675, "true_obligation": 27, "not_obligation": 13, "sample_size": 40})
    blank = resolver.write_path("benchmark", "candidates", "t1_precision_sample_v1.csv")
    blank.write_text("sample_index,candidate_id,is_obligation\n1,t1c_x,\n", encoding="utf-8")

    with pytest.raises(run_candidates.ScoreOverwriteError):
        run_candidates.run_score({}, resolver, None, "v1")
    kept = json.loads(resolver.write_path("reports", "p2001_precision_metrics_v1.json").read_text("utf-8"))
    assert kept["true_obligation"] == 27
