"""V2 milestone 1: the Topic Alignment Agent with a mocked LLM (no API), plus V1 freeze regression checks.

The example paragraphs are fabricated (tests/fixtures/v2/alignment_examples.json); they are not RBI text.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.rag import comparator as CMP
from src.rag.v2 import evidence as EV
from src.rag.v2 import schemas as S
from src.rag.v2 import topic_aligner as TA

REPO = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((REPO / "tests/fixtures/v2/alignment_examples.json").read_text(encoding="utf-8"))["cases"]


@dataclass
class FakeCompletion:
    text: str
    cached: bool = False
    model: str = "gemini-3.5-flash-lite"
    model_version: str = "fake"


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, messages, *, max_output_tokens=None, role="default"):
        self.calls.append(messages)
        return FakeCompletion(self.replies.pop(0))


def unit_of(case):
    u = copy.deepcopy(FIXTURES[case]["unit"])
    u["candidates"] = [tuple(c) for c in u["candidates"]]
    return u


def run(case, reply=None):
    u = unit_of(case)
    reply = FIXTURES[case]["reply"] if reply is None else reply
    llm = FakeLLM([reply if isinstance(reply, str) else json.dumps(reply)])
    return TA.align_unit(llm, TA.Prompts(), u, max_output_tokens=800), llm


def labels(rec):
    return {a["candidate_id"]: a["same_underlying_duty"] for a in rec["alignments"]}


# -- the three fixture cases ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(FIXTURES))
def test_fixture_cases_give_expected_labels(case):
    rec, llm = run(case)
    assert labels(rec) == FIXTURES[case]["expected"]
    assert rec["parse_problems"] == [] and rec["warnings"] == []
    assert len(llm.calls) == 1  # one call per unit, all candidates together


def test_same_duty_with_different_deadline_is_yes_and_evidence_checked():
    rec, _ = run("same_duty_different_deadline")
    yes = rec["alignments"][0]
    assert yes["same_underlying_duty"] == "yes" and yes["model_label"] == "yes"
    assert yes["evidence_ok"] is True and yes["problems"] == []
    assert set(yes["dimensions"]) == set(S.DIMENSIONS)
    assert rec["source_id"] == "md_90001::p00010"


def test_ambiguous_case_needs_no_quotes():
    rec, _ = run("ambiguous_duty")
    a = rec["alignments"][0]
    assert a["same_underlying_duty"] == "uncertain" and a["problems"] == [] and a["evidence_ok"] is False


# -- validation: nothing unverified reaches the next stage --------------------------------------------------------------


def test_fabricated_quote_downgrades_to_uncertain():
    reply = copy.deepcopy(FIXTURES["same_duty_different_deadline"]["reply"])
    reply["alignments"][0]["candidate_evidence"] = "shall report each fraud to the Reserve Bank within seven days"
    rec, _ = run("same_duty_different_deadline", reply)
    a = rec["alignments"][0]
    assert a["model_label"] == "yes" and a["same_underlying_duty"] == "uncertain"
    assert any("candidate_evidence not found" in p for p in a["problems"])
    assert labels(rec)["md_90002::p00021"] == "no"  # the other candidate is unaffected


def test_quote_from_the_wrong_paragraph_is_rejected():
    reply = copy.deepcopy(FIXTURES["same_duty_different_deadline"]["reply"])
    # A real quote, but from candidate 2, offered as evidence for candidate 1.
    reply["alignments"][0]["candidate_evidence"] = "display the name and contact details of its grievance redressal officer"
    rec, _ = run("same_duty_different_deadline", reply)
    assert labels(rec)["md_90002::p00020"] == "uncertain"


def test_too_short_quote_is_rejected():
    reply = copy.deepcopy(FIXTURES["different_duty_shared_topic"]["reply"])
    reply["alignments"][0]["source_evidence"] = "the bank shall"
    rec, _ = run("different_duty_shared_topic", reply)
    assert labels(rec)["md_90004::p00007"] == "uncertain"


def test_invalid_label_or_dimension_downgrades():
    reply = copy.deepcopy(FIXTURES["different_duty_shared_topic"]["reply"])
    reply["alignments"][0]["same_underlying_duty"] = "maybe"
    rec, _ = run("different_duty_shared_topic", reply)
    assert labels(rec) == {"md_90004::p00007": "uncertain"} and rec["alignments"][0]["model_label"] is None
    reply = copy.deepcopy(FIXTURES["different_duty_shared_topic"]["reply"])
    del reply["alignments"][0]["dimensions"]["purpose"]
    rec, _ = run("different_duty_shared_topic", reply)
    a = rec["alignments"][0]
    assert a["same_underlying_duty"] == "uncertain" and "purpose" in a["problems"][0]


def test_missing_duplicate_and_unknown_candidates():
    reply = copy.deepcopy(FIXTURES["same_duty_different_deadline"]["reply"])
    extra = copy.deepcopy(reply["alignments"][0])
    reply["alignments"] = [reply["alignments"][0], reply["alignments"][0], {**extra, "candidate_id": "md_99999::p00001"}]
    rec, _ = run("same_duty_different_deadline", reply)
    assert labels(rec) == {"md_90002::p00020": "uncertain", "md_90002::p00021": "uncertain"}
    probs = {a["candidate_id"]: a["problems"][0] for a in rec["alignments"]}
    assert "2 times" in probs["md_90002::p00020"] and "missing" in probs["md_90002::p00021"]
    assert any("md_99999::p00001" in w for w in rec["warnings"])


def test_unusable_answers_make_every_candidate_uncertain():
    for bad in ("not json at all", json.dumps({"candidates": []}), json.dumps(["a list"])):
        rec, _ = run("same_duty_different_deadline", bad)
        assert set(labels(rec).values()) == {"uncertain"} and rec["parse_problems"]


def test_code_fenced_json_is_accepted_and_source_id_mismatch_is_a_warning():
    reply = copy.deepcopy(FIXTURES["different_duty_shared_topic"]["reply"])
    reply["source_id"] = "md_00000::p00000"
    rec, _ = run("different_duty_shared_topic", "```json\n" + json.dumps(reply) + "\n```")
    assert labels(rec) == {"md_90004::p00007": "no"} and rec["parse_problems"] == []
    assert rec["warnings"] and "does not match" in rec["warnings"][0]


def test_summarise_counts_downgrades():
    good, _ = run("same_duty_different_deadline")
    reply = copy.deepcopy(FIXTURES["same_duty_different_deadline"]["reply"])
    reply["alignments"][0]["source_evidence"] = "invented words not in the source text"
    bad, _ = run("same_duty_different_deadline", reply)
    s = TA.summarise([good, bad])
    assert s["units"] == 2 and s["candidates"] == 4 and s["downgraded_by_validation"] == 1
    assert s["final"] == {"yes": 1, "no": 2, "uncertain": 1} and s["model"] == {"yes": 2, "no": 2}


# -- prompts ----------------------------------------------------------------------------------------------------------


def test_prompt_rendering():
    _, llm = run("same_duty_different_deadline")
    system, user = llm.calls[0][0]["content"], llm.calls[0][1]["content"]
    assert "do NOT by themselves mean the duties are unrelated" in system
    assert "SOURCE id: md_90001::p00010" in user and "TARGET class: Non-Banking Financial Companies" in user
    assert "[md_90002::p00020] An NBFC shall report" in user and "[md_90002::p00021]" in user
    assert not TA._SLOT_RE.search(user)


def test_placeholder_text_inside_a_paragraph_is_not_substituted():
    u = unit_of("different_duty_shared_topic")
    u["source_text"] = "Text that literally contains {candidates} and {target_class}."
    msgs = TA.Prompts().messages(source_id="md_1::p00001", source_class="A", source_text=u["source_text"],
                                 target_class="B", candidates=u["candidates"])
    assert "literally contains {candidates} and {target_class}." in msgs[1]["content"]


def test_source_id_and_empty_unit():
    assert TA.source_id_of({"item_id": "t1_md_12927::p00093"}) == "md_12927::p00093"
    assert TA.source_id_of({"item_id": "x", "source_id": "md_1::p00002"}) == "md_1::p00002"
    assert TA.source_id_of({"item_id": "irr_7"}) is None
    with pytest.raises(TA.AlignerError, match="no candidates"):
        TA.align_unit(FakeLLM([]), TA.Prompts(), {**unit_of("ambiguous_duty"), "candidates": []}, max_output_tokens=10)


def test_freeze_check_refuses_changed_prompts(tmp_path):
    for f in TA.PROMPT_FILES:
        (tmp_path / f).write_text((TA.PROMPTS_DIR / f).read_text())
    h = TA.frozen_hashes(tmp_path)
    assert {"topic_aligner.py", "evidence.py"} <= set(h)
    TA.Prompts(tmp_path, expected=h)
    (tmp_path / "topic_alignment_system.txt").write_text("changed")
    with pytest.raises(TA.AlignerError, match="changed"):
        TA.Prompts(tmp_path, expected=h)


# -- evidence helpers -------------------------------------------------------------------------------------------------


def test_evidence_helpers():
    text = "The bank shall, within fifteen (15) days, report frauds of ₹1,00,000 or more."
    assert EV.quote_in("THE BANK SHALL within fifteen", text)
    assert not EV.quote_in("bank shall", text)  # under four words
    assert not EV.quote_in("shall report within thirty days", text)
    assert not EV.quote_in("ank shall within fifteen", text)  # matches on word boundaries only
    assert EV.numbers(text) == {"15", "100000"}
    assert EV.numbers("at least 03 members, 2.5 per cent") == {"3", "2.5"}


# -- regression: V2 must not touch V1 ---------------------------------------------------------------------------------


def test_v1_frozen_artefacts_unchanged():
    frozen = json.loads((REPO / "configs/comparator_v1/FROZEN.json").read_text())["sha256"]
    assert CMP.frozen_hashes(REPO / "configs/comparator_v1") == frozen


def test_p4_frozen_prompts_unchanged():
    from src.common.config import load_config
    from src.rag import pipeline as PL

    assert PL.prompt_hashes(REPO / "configs/p4_prompts_v1") == load_config(None)["p4"]["prompt_sha256"]
