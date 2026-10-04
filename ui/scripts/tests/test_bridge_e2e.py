"""Live mode end to end with a mocked LLM: a new, unseen query string -> local encode (pinned bge revision) ->
class-aware RRF -> frozen comparator prompt -> mocked reply -> frozen rule. No network, no API key."""

import json

import pytest

import pipeline_bridge as PB
from cc_common import FIELDS, rbi_words

UNSEEN = ("A lender that wants to hand over its core banking software operations to an outside vendor "
          "must first adopt a written policy approved by its board describing the risks and controls (test query 7f3a).")


def mock_llm(messages, candidate_ids):
    """Deterministic stand-in for the model: the first candidate addresses the same duty with one differing field."""
    assert messages[0]["role"] == "system" and messages[1]["role"] == "user"
    assert all(f"[{pid}]" in messages[1]["content"] for pid in candidate_ids)
    cands = []
    for i, pid in enumerate(candidate_ids):
        fc = {f: "equal" for f in FIELDS}
        if i == 0:
            fc["scope"] = "differs"
        cands.append({"paragraph_id": pid, "addresses_same_duty": i == 0, "fields": {"actor": "a lender"}, "field_comparison": fc})
    return json.dumps({"source": {"actor": "a lender"}, "candidates": cands})


@pytest.fixture(scope="module")
def bridge():
    calls = {"n": 0}
    b = PB.Bridge()
    real = b.encoder()

    def counting(texts):
        calls["n"] += 1
        return real(texts)

    b._encoder = counting
    b.calls = calls
    return b


def test_unseen_query_goes_through_encode_rrf_comparator(bridge):
    assert UNSEEN not in bridge.corpus.texts
    target = "Non-Banking Financial Companies"
    prep = bridge.prepare(target, source_pid=None, text=UNSEEN, source_class="Commercial Banks")
    assert prep["ok"], prep
    assert bridge.calls["n"] == 1, "free text must be embedded locally"
    assert "encoded locally" in prep["retrieval"]["dense_query"] and "a5beb1e3" in prep["retrieval"]["dense_query"]
    assert prep["retrieval"]["class_filter_applied"] is True
    assert len(prep["candidate_ids"]) == 2
    for pid in prep["candidate_ids"]:
        assert bridge.corpus.entity_class[bridge.pos[pid]] == target
    for p in prep["pointers"]:
        assert p["excerpt"] is None or len(rbi_words(p["excerpt"])) <= 25
    raw = mock_llm(prep["messages"], prep["candidate_ids"])
    out = bridge.decide(raw, prep["candidate_ids"], source_pid=None, source_class="Commercial Banks")
    assert out["ok"] and out["rule"] == "comparator-rule-v1"
    assert out["judgement"] == "different" and out["matched_paragraph_id"] == prep["candidate_ids"][0]
    assert len(out["features_m2"]) == 8 and out["features_m2"][0] == 1.0


def test_existing_paragraph_uses_stored_embedding(bridge):
    before = bridge.calls["n"]
    prep = bridge.prepare("Commercial Banks", source_pid="md_12925::p00044")
    assert prep["ok"]
    assert bridge.calls["n"] == before
    assert "stored paragraph embedding" in prep["retrieval"]["dense_query"]
    assert "md_12925::p00044" not in prep["candidate_ids"]


def test_unparseable_reply_is_unsure(bridge):
    prep = bridge.prepare("Payments Banks", source_pid="md_12925::p00044")
    out = bridge.decide("not json", prep["candidate_ids"])
    assert out["judgement"] == "unsure" and out["features_m2"] is None


def test_frozen_prompt_hash_is_enforced():
    import shutil
    import stat

    from src.rag import comparator as CMP
    d = PB.UI / "server/.cache/test_frozen_cmp"  # gitignored scratch inside the repo
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(PB.ROOT / "configs/comparator_v1", d)
    f = d / "comparator_system.txt"
    f.chmod(stat.S_IWUSR | stat.S_IRUSR)
    f.write_text("changed", encoding="utf-8")
    frozen = json.loads((PB.ROOT / "configs/comparator_v1/FROZEN.json").read_text())
    with pytest.raises(CMP.ComparatorError):
        CMP.Prompts(d, expected=frozen["sha256"])
    shutil.rmtree(d, ignore_errors=True)
