"""P4-001 Part A: filters, T3 parser, verifier, derivation, metrics, budgets, quota ledger, freeze, fallback, demo.

The LLM and the NLI model are mocked everywhere; no RBI text.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from src.llm import client as L
from src.rag import evaluation as E
from src.rag import pipeline as PL
from src.retrieval.index import Corpus
from src.t3 import build as B
from src.t3 import parser as P

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# -- fixtures ---------------------------------------------------------------------------

PARAS = [  # pid, md, class, text
    ("md_1::p00001", "md_1", "A", "A bank shall report fraud within seven days."),
    ("md_1::p00002", "md_1", "A", "A bank shall keep records for ten years."),
    ("md_2::p00001", "md_2", "B", "A company shall report fraud within fourteen days."),
    ("md_2::p00002", "md_2", "B", "A company shall keep records for five years."),
    ("md_3::p00001", "md_3", "Payment and Settlement System", "An operator shall report fraud promptly."),
    ("md_4::p00001", "md_4", "C", "A bank shall appoint a compliance officer."),
]
DOC = {"md_1": {"title": "A Fraud Directions", "entity_class": "A", "subject_family": "Fraud"},
       "md_2": {"title": "B Fraud Directions", "entity_class": "B", "subject_family": "Fraud"},
       "md_3": {"title": "PSS Fraud Directions", "entity_class": "Payment and Settlement System", "subject_family": "Fraud"},
       "md_4": {"title": "C Compliance Directions", "entity_class": "C", "subject_family": "Compliance"}}


class FakeBM25:
    def __init__(self, texts):
        self.texts = [t.lower() for t in texts]

    def scores(self, q):
        words = set(q.lower().split())
        return np.array([float(len(words & set(t.split()))) for t in self.texts], dtype=np.float32)


def make_res(temporal: PL.TemporalIndex | None = None) -> PL.Resources:
    corpus = Corpus([p[0] for p in PARAS], [p[3] for p in PARAS], np.array([p[2] for p in PARAS], dtype=object),
                    [p[1] for p in PARAS])
    rng = np.random.default_rng(0)
    emb = rng.normal(size=(len(PARAS), 8)).astype(np.float32)
    return PL.Resources(corpus=corpus, bm25=FakeBM25(corpus.texts), emb=emb, encoder=lambda q: np.ones(8, np.float32),
                        doc=DOC, function_headings=frozenset({"Payment and Settlement System"}),
                        temporal=temporal or PL.TemporalIndex({}), paragraph_max_chars=500)


class FakeLLM:
    """Returns queued texts; counts calls; caches identical messages like the real client."""

    def __init__(self, replies, *, cache=True):
        self.replies = list(replies)
        self.seen = []
        self.cache = {}
        self.use_cache = cache

    def complete(self, messages, *, role="default", max_output_tokens=None):
        key = json.dumps(messages, sort_keys=True)
        if self.use_cache and key in self.cache:
            return L.Completion(text=self.cache[key], provider="gemini", model="m", model_version="v",
                                input_tokens=1, output_tokens=1, cached=True)
        self.seen.append(messages)
        text = self.replies.pop(0)
        self.cache[key] = text
        return L.Completion(text=text, provider="gemini", model="m", model_version="v", input_tokens=1, output_tokens=1)


class FakeNLI:
    """Supported iff the hypothesis's words all appear in the premise (a stand-in for entailment)."""

    def supported(self, pairs):
        return [set(h.lower().strip(".").split()) <= set(p.lower().replace(".", "").split()) for p, h in pairs]


@pytest.fixture
def prompts(tmp_path):
    for f in PL.PROMPT_FILES:
        (tmp_path / f).write_text((ROOT / "configs" / "p4_prompts_v1" / f).read_text(encoding="utf-8"), encoding="utf-8")
    return PL.Prompts(tmp_path, PL.prompt_hashes(tmp_path))


# -- class filter ------------------------------------------------------------------------------


def test_class_filter_keeps_class_and_same_family_function_headings():
    res = make_res()
    got = PL.retrieve(res, "report fraud", exclude_pid=None, entity_class="A", subject_family="Fraud",
                      class_filter=True, depth=20)
    assert set(got) == {"md_1::p00001", "md_1::p00002", "md_3::p00001"}
    no_family = PL.retrieve(res, "report fraud", exclude_pid=None, entity_class="A", subject_family=None,
                            class_filter=True, depth=20)
    assert set(no_family) == {"md_1::p00001", "md_1::p00002"}
    other_family = PL.retrieve(res, "report fraud", exclude_pid=None, entity_class="A", subject_family="Compliance",
                               class_filter=True, depth=20)
    assert "md_3::p00001" not in other_family
    blind = PL.retrieve(res, "report fraud", exclude_pid="md_2::p00001", entity_class="A", subject_family="Fraud",
                        class_filter=False, depth=20)
    assert len(blind) == 5 and "md_2::p00001" not in blind  # source paragraph always excluded


# -- temporal filter ------------------------------------------------------------------------------


def _temporal():
    return PL.TemporalIndex({
        "md_1::p00001": [PL.Event("amd_9", "delete", "paragraph_whole", "2026-04-01", None, "Amd 9", None)],
        "md_1::p00002": [PL.Event("amd_8", "substitute", "within_paragraph", "2026-02-01", None, "Amd 8", "twelve years")],
        "md_2::p00002": [PL.Event("amd_7", "substitute", "paragraph_whole", None, ["2026-01-01", "2026-03-01"], "Amd 7", None)],
    })


def test_temporal_filter_drops_deleted_and_marks_amended_and_later():
    res = make_res(_temporal())
    kept, status = PL.apply_temporal(res, ["md_1::p00001", "md_1::p00002", "md_2::p00002"], "2026-05-01")
    assert "md_1::p00001" not in kept
    assert status["md_1::p00002"]["state"] == "amended" and "twelve years" in status["md_1::p00002"]["notes"][0]
    assert status["md_2::p00002"]["state"] == "amended"
    kept, status = PL.apply_temporal(res, ["md_1::p00001", "md_1::p00002"], "2026-01-15")
    assert kept == ["md_1::p00001", "md_1::p00002"]
    assert status["md_1::p00001"]["state"] == "original_amended_later"
    assert "original in force; amended from 2026-04-01" in status["md_1::p00001"]["notes"][0]
    assert res.temporal.status("md_2::p00002", "2026-02-01")["state"] == "uncertain"  # inside the window
    kept, _ = PL.apply_temporal(res, ["md_1::p00001"], "2026-05-01", keep=["md_1::p00001"])
    assert kept == ["md_1::p00001"]  # a pinned T3 target stays, marked
    assert PL.apply_temporal(res, ["md_1::p00001"], None) == (["md_1::p00001"], {})


# -- T3 parser -------------------------------------------------------------------------------------

AMD = {
    "item_id": "amd_1", "published_date": "2026-01-10", "title": "X Amendment Directions, 2026",
    "fields": {"linked_md_ids": ["md_1"]},
    "text": ("1. These Directions shall come into force on April 1, 2026.\n"
             "2. The Directions shall be amended as under:\n"
             "(1) Paragraph 12 shall be substituted by the following, namely: “12. A bank shall report weekly.”\n"
             "(2) Paragraphs 14 to 16 shall be deleted.\n"
             "(3) In paragraph 20, the words ‘seven days’ shall be substituted with ‘five days’.\n"
             "(4) Paragraph 21(3A) shall be inserted as under: “(3A) New text.”\n"
             "(6) After paragraph 22, a new paragraph 22A shall be inserted: “22A. More text.”\n"
             "(5) In Annex II, the form shall be substituted with the enclosed form.\n"),
}


def test_parser_substitute_delete_insert_and_unclear():
    actions, counts = P.parse_amendment(AMD)
    by = {(a.action, a.scope): a for a in actions}
    sub = by[("substitute", "paragraph_whole")]
    assert sub.targets == ["12"] and sub.new_text == "12. A bank shall report weekly."
    assert by[("delete", "paragraph_whole")].targets == ["14", "15", "16"]
    w = by[("substitute", "within_paragraph")]
    assert w.targets == ["20"] and w.old_words == ["seven days"] and w.new_words == ["five days"]
    assert by[("insert", "new_paragraph")].targets == ["21(3a)"]
    # the annex instruction, and "22A": a letter suffix without parentheses is not a parsed path (known limit)
    assert counts["unparsed"] == 2
    assert P.effective_date(AMD) == {"date": "2026-04-01", "window": None, "basis": "stated_date",
                                     "sentence": "come into force on April 1, 2026"}


def test_effective_date_variants():
    base = {"published_date": "2026-01-10"}
    assert P.effective_date({**base, "text": "shall come into force with immediate effect."})["date"] == "2026-01-10"
    w = P.effective_date({**base, "text": "shall come into effect on April 1, 2026 or on adoption, whichever is earlier."})
    assert w["date"] is None and w["window"] == ["2026-01-10", "2026-04-01"]
    e = P.effective_date({**base, "text": "come into effect from March 15, 2026, except paragraph 7, which shall be effective from March 12, 2026"})
    assert e["window"] == ["2026-03-12", "2026-03-15"]
    assert P.effective_date({**base, "text": "shall come into force from the date a bank decides."})["basis"] == "unclear"
    assert P.effective_date({**base, "text": "no commencement here"})["basis"] == "no_commencement_sentence"


def test_multi_linked_amendment_resolved_only_by_exact_title():
    item = {"fields": {"linked_md_ids": ["md_1", "md_2"], "title_derived_target": "Reserve Bank of India (A - Fraud) Directions"}}
    titles = {"md_1": "Reserve Bank of India (A – Fraud) Directions, 2025 (Updated as on May 1, 2026)", "md_2": "Other"}
    assert P.target_direction(item, titles) == "md_1"
    assert P.target_direction(item, {"md_1": "Reserve Bank of India (A – Fraudulent) Directions", "md_2": "x"}) is None


def test_corpus_version_check():
    actions, _ = P.parse_amendment(AMD)
    sub = next(a for a in actions if a.scope == "paragraph_whole" and a.action == "substitute")
    assert P.corpus_version(sub, "12. A bank shall report weekly.") == "amended"
    assert P.corpus_version(sub, "12. The entity shall file an annual statement with its board of directors.") == "original"
    w = next(a for a in actions if a.scope == "within_paragraph")
    assert P.corpus_version(w, "20. Report within five days.") == "amended"
    assert P.corpus_version(w, "20. Report within seven days.") == "original"


def test_t3_items_are_paired_and_gold_follows_dates():
    rows = [{"action_id": "a", "item_id": "amd_1", "md_id": "md_1", "target": "12", "paragraph_id": "md_1::p00012",
             "paragraphs_with_path": 1, "action": "delete", "scope": "paragraph_whole",
             "effective": {"date": "2026-04-01", "window": None}, "corpus_version": "original",
             "direction_issue_date": "2025-11-28"}]
    items, log = B.build_items(rows, n=10, seed=1, max_per_direction=5, today="2026-09-27")
    assert [i["side"] for i in items] == ["before", "after"]
    before, after = items
    assert before["as_of"] < "2026-04-01" <= after["as_of"] <= "2026-09-27"
    assert (before["gold_status"], before["gold_governing_instrument"]) == ("in_force_original", "md_1")
    assert (after["gold_status"], after["gold_governing_instrument"]) == ("deleted", "amd_1")
    assert B.wilson(18, 20)[0] == pytest.approx(0.699, abs=0.01)


# -- verifier and retry ---------------------------------------------------------------------------------


def _answer_json(sentence, cite):
    return json.dumps({"can_answer": True, "sentences": [{"text": sentence, "citations": [cite]}]})


def test_verifier_supported_first_time(prompts):
    res = make_res()
    llm = FakeLLM([_answer_json("A bank shall report fraud within seven days.", "md_1::p00001")])
    log = PL.answer(res, prompts, llm, FakeNLI(), "report fraud", entity_class="A")
    assert log["result"]["can_answer"] and not log["result"]["abstained_by_verifier"]
    assert log["result"]["supported"] == [True] and len(log["steps"]) == 1 and log["calls"] == 1


def test_retry_with_unchanged_evidence_is_a_cache_hit(prompts):
    """At temperature 0 an identical retry prompt (same top 5) gives the same answer, from the cache, at no quota."""
    res = make_res()
    llm = FakeLLM([_answer_json("A bank shall report fraud within three days.", "md_1::p00001")])
    log = PL.answer(res, prompts, llm, FakeNLI(), "report fraud", entity_class="A")
    assert len(log["steps"]) == 2 and log["steps"][1]["cached"] and log["calls"] == 1
    assert log["result"]["abstained_by_verifier"]


def test_verifier_retry_then_supported(prompts):
    res = make_res()
    llm = FakeLLM(cache=False, replies=[_answer_json("A bank shall report fraud within three days.", "md_1::p00001"),
                   _answer_json("A bank shall report fraud within seven days.", "md_1::p00001")])
    log = PL.answer(res, prompts, llm, FakeNLI(), "report fraud", entity_class="A")
    assert len(log["steps"]) == 2 and log["result"]["supported"] == [True]
    assert "three days" in log["steps"][1]["query_used"]  # deterministic reformulation, no LLM call
    assert not log["result"]["abstained_by_verifier"] and log["calls"] == 2


def test_verifier_abstains_after_one_retry(prompts):
    res = make_res()
    llm = FakeLLM(cache=False, replies=[_answer_json("A bank shall report fraud within three days.", "md_1::p00001"),
                   _answer_json("A bank shall report fraud within two days.", "md_1::p00001")])
    log = PL.answer(res, prompts, llm, FakeNLI(), "report fraud", entity_class="A")
    assert log["result"]["abstained_by_verifier"] and log["result"]["answer"] == PL.ABSTAIN
    assert log["result"]["evidence"] and len(llm.seen) == 2  # exactly one retry


def test_uncited_sentence_is_unsupported():
    res = make_res()
    sents = [{"text": "A bank shall report fraud within seven days.", "citations": []},
             {"text": "A bank shall report fraud within seven days.", "citations": ["md_9::p00001"]}]
    assert PL.verify_sentences(res, sents, ["md_1::p00001"], FakeNLI()) == [False, False]


# -- T1: derivation, budgets, verifier on judgements --------------------------------------------------------


def test_label_derivation_including_unsure_to_ambiguous():
    d = lambda js: PL.derive({c: {"judgement": j} for c, j in js.items()}, "S")
    assert d({"A": "same", "B": "different"})["flag"] == "class-specific"
    assert d({"A": "same", "B": "none"})["flag"] == "shared"
    assert d({"A": "none", "B": "none"})["flag"] == "absent"
    assert d({"A": "none", "B": "unsure"}) == {"flag": "ambiguous", "ambiguous": True, "applies_to": ["S"]}
    assert d({"A": "same", "B": "unsure"})["applies_to"] == ["A", "S"]


def test_flag_macro_f1_counts_ambiguous_as_wrong():
    gold = ["shared", "absent", "class-specific"]
    assert E.flag_macro_f1(gold, gold) == 1.0
    amb = ["shared", "absent", "ambiguous"]
    # class-specific: tp 0 -> F1 0; the other two perfect -> (1 + 1 + 0) / 3
    assert E.flag_macro_f1(gold, amb) == pytest.approx(2 / 3)
    assert E.coverage(amb) == pytest.approx(2 / 3)
    assert E.collapsed_macro_f1(["absent", "shared"], ["absent", "class-specific"]) == 1.0


ITEM = {"item_id": "t1_md_1::p00001", "md_id": "md_1", "paragraph_id": "md_1::p00001", "entity_class": "A",
        "subject_family": "Fraud", "obligation_span": {"text": "A bank shall report fraud within seven days."},
        "compared_classes": ["B", "C"]}


def test_equal_evidence_budget_class_aware_vs_blind():
    res = make_res()
    aware_txt, aware = PL.t1_evidence(res, ITEM, "report fraud", PL.T1Config(class_filter=True, verifier=False, per_class=1))
    blind_txt, blind = PL.t1_evidence(res, ITEM, "report fraud", PL.T1Config(class_filter=False, verifier=False, per_class=1))
    assert sum(len(v) for v in aware.values()) == len(blind["*"]) == 2  # 1 x K each, K = 2
    assert all(p != ITEM["paragraph_id"] for v in (*aware.values(), blind["*"]) for p in v)
    assert set(aware) == {"B", "C"} and "Compared class: B" in aware_txt


def _t1_reply(matched_b, rationale_b):
    return json.dumps({"per_class": {
        "B": {"judgement": "different", "matched_paragraph_id": matched_b, "rationale": rationale_b},
        "C": {"judgement": "none", "matched_paragraph_id": None, "rationale": "No counterpart."}}})


def test_t1_verifier_supported_retry_and_unsure(prompts):
    res = make_res()
    cfg = PL.T1Config(class_filter=True, verifier=True, per_class=2)
    ok = PL.run_t1_item(res, prompts, FakeLLM([_t1_reply("md_2::p00001", "A company shall report fraud within fourteen days.")]),
                        FakeNLI(), ITEM, cfg)
    assert ok["final"]["flag"] == "class-specific" and not ok["retried"]
    # unsupported rationale, then supported on the retry
    llm = FakeLLM(cache=False, replies=[_t1_reply("md_2::p00001", "A company shall report fraud daily."),
                   _t1_reply("md_2::p00001", "A company shall report fraud within fourteen days.")])
    r = PL.run_t1_item(res, prompts, llm, FakeNLI(), ITEM, cfg)
    assert r["retried"] and r["final"]["per_class"]["B"]["judgement"] == "different"
    # still unsupported -> unsure -> flag derived from the rest
    llm = FakeLLM(cache=False, replies=[_t1_reply("md_2::p00001", "wrong."), _t1_reply("md_2::p00001", "still wrong.")])
    r = PL.run_t1_item(res, prompts, llm, FakeNLI(), ITEM, cfg)
    assert r["final"]["per_class"]["B"]["judgement"] == "unsure" and r["final"]["flag"] == "ambiguous"
    # a matched id from the wrong class is never supported
    llm = FakeLLM(cache=False, replies=[_t1_reply("md_1::p00002", "A bank shall keep records for ten years."),
                                        _t1_reply("md_1::p00002", "x")])
    r = PL.run_t1_item(res, prompts, llm, FakeNLI(), ITEM, cfg)
    assert r["final"]["per_class"]["B"]["judgement"] == "unsure"


def test_paired_systems_share_the_first_prompt(prompts):
    """final agentic sends class-aware's first prompt; ablation A sends class-blind's (cache hits, no new call)."""
    res = make_res()
    reply = _t1_reply("md_2::p00001", "A company shall report fraud within fourteen days.")
    llm = FakeLLM([reply, reply])
    a = PL.run_t1_item(res, prompts, llm, None, ITEM, PL.T1Config(class_filter=True, verifier=False, per_class=2))
    f = PL.run_t1_item(res, prompts, llm, FakeNLI(), ITEM, PL.T1Config(class_filter=True, verifier=True, per_class=2))
    assert a["steps"][0]["cached"] is False and f["steps"][0]["cached"] is True and len(llm.seen) == 1


def test_ablation_flags():
    run_p4 = _load("run_p4", ROOT / "scripts" / "run_p4.py")
    s = run_p4.SYSTEMS
    assert (s["class_aware"].class_filter, s["class_aware"].verifier) == (True, False)
    assert (s["final_agentic"].class_filter, s["final_agentic"].verifier) == (True, True)
    assert (s["class_blind"].class_filter, s["class_blind"].verifier) == (False, False)
    assert (s["ablation_a"].class_filter, s["ablation_a"].verifier) == (False, True)
    assert run_p4.PART_A_ORDER == ("class_aware", "final_agentic", "class_blind", "ablation_a")


def test_t1_parse_marks_malformed_output_unsure():
    per, problems = PL.parse_t1("not json", ["B"])
    assert per["B"]["judgement"] == "unsure" and "unparseable JSON" in problems
    per, problems = PL.parse_t1(json.dumps({"per_class": {"B": {"judgement": "maybe"}}}), ["B", "C"])
    assert per["B"]["judgement"] == "unsure" and per["C"]["judgement"] == "unsure" and len(problems) == 2


# -- quota ledger ---------------------------------------------------------------------------------


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_quota_day_rolls_over_at_midnight_pacific(tmp_path):
    utc = dt.timezone.utc
    clock = Clock(dt.datetime(2026, 9, 28, 6, 59, tzinfo=utc))  # 23:59 PDT on 27 Sep
    led = L.QuotaLedger(tmp_path / "q.json", soft_cap=3, now=clock)
    assert led.quota_day() == "2026-09-27"
    assert led.next_reset_ist() == "2026-09-28 12:30"
    led.record("m")
    clock.t = dt.datetime(2026, 9, 28, 7, 1, tzinfo=utc)  # 00:01 PDT on 28 Sep
    assert led.quota_day() == "2026-09-28" and led.used("m") == 0 and led.used("m", "2026-09-27") == 1


def test_soft_cap_pauses_before_calling(tmp_path):
    class Prov:
        name = "gemini"
        calls = 0

        def list_models(self):
            return []

        def generate(self, model, messages, params):
            Prov.calls += 1
            return L.Completion(text="{}", provider="gemini", model=model, model_version="v", input_tokens=1, output_tokens=1)

    led = L.QuotaLedger(tmp_path / "q.json", soft_cap=2)
    client = L.LLMClient([L.ProviderSlot(Prov(), {"default": "m"}, rpm=100, tpm=10**6)], cache_dir=tmp_path / "c",
                         max_calls=10, ledger=led, sleep=lambda s: None)
    client.complete([{"role": "user", "content": "1"}])
    client.complete([{"role": "user", "content": "2"}])
    with pytest.raises(L.QuotaPaused) as exc:
        client.complete([{"role": "user", "content": "3"}])
    assert Prov.calls == 2 and exc.value.resume_after_ist
    assert client.complete([{"role": "user", "content": "1"}]).cached  # cache hits never touch the ledger
    assert led.used("m") == 2


def test_daily_quota_error_pauses_without_retry_or_fallback(tmp_path):
    class Prov:
        name = "gemini"
        calls = 0

        def list_models(self):
            return []

        def generate(self, model, messages, params):
            Prov.calls += 1
            raise L.RateLimitError("gemini: HTTP 429 RESOURCE_EXHAUSTED [quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier]")

    led = L.QuotaLedger(tmp_path / "q.json", soft_cap=100)
    client = L.LLMClient([L.ProviderSlot(Prov(), {"default": "m"}, rpm=100, tpm=10**6)], cache_dir=tmp_path / "c",
                         max_calls=10, ledger=led, backoff_attempts=5, sleep=lambda s: None)
    with pytest.raises(L.QuotaPaused):
        client.complete([{"role": "user", "content": "x"}])
    assert Prov.calls == 1


def test_checkpoint_and_resume_never_recall(tmp_path, monkeypatch):
    run_p4 = _load("run_p4", ROOT / "scripts" / "run_p4.py")
    calls = {"n": 0}

    class Client:
        slots = [type("S", (), {"models": {"default": "m"}})()]
        run = type("R", (), {"summary": lambda self: {"api_calls": calls["n"], "cache_hits": 0}})()

    class Ledger:
        def quota_day(self):
            return "d"

        def used(self, m):
            return calls["n"]

    def fake_item(res, prompts, client, verifier, it, cfg):
        if calls["n"] == 2:
            raise L.QuotaPaused("cap", resume_after_ist="2026-09-28 12:30")
        calls["n"] += 1
        return {"item_id": it["item_id"], "final": {}}

    monkeypatch.setattr(run_p4, "make_llm", lambda *a, **k: (Client(), Ledger()))
    monkeypatch.setattr(run_p4.PL, "run_t1_item", fake_item)
    items = [{"item_id": f"i{k}"} for k in range(4)]
    cfg = {"p4": {"retrieval": {"t1_per_class": 5, "depth": 20}, "max_output_tokens": 10, "long_context": {"max_input_tokens": 1}}}
    fake_prompts = type("P", (), {"hashes": {"t1_system.txt": "h"}})()
    s = run_p4.run_t1(cfg, None, "class_aware", items, prompts=fake_prompts, res=None, extra={}, verifier=None, out_dir=tmp_path)
    assert s["paused"] and s["done"] == 2 and s["left"] == 2
    calls["n"] = 0
    s = run_p4.run_t1(cfg, None, "class_aware", items, prompts=fake_prompts, res=None, extra={}, verifier=None, out_dir=tmp_path)
    assert s["skipped"] == 2 and s["done"] == 2 and calls["n"] == 2  # only the two unwritten items were called
    assert len(list(tmp_path.glob("*.json"))) == 4


# -- prompt freeze, fallback ---------------------------------------------------------------------------


def test_prompt_freeze_hash_mismatch_stops(tmp_path):
    for f in PL.PROMPT_FILES:
        (tmp_path / f).write_text("x", encoding="utf-8")
    frozen = PL.prompt_hashes(tmp_path)
    PL.Prompts(tmp_path, frozen)
    (tmp_path / "t1_system.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(PL.PromptFreezeError, match="t1_system.txt"):
        PL.Prompts(tmp_path, frozen)
    with pytest.raises(PL.PromptFreezeError):
        PL.Prompts(tmp_path, {})


def test_fallback_none_is_enforced(monkeypatch, tmp_path):
    from tests.conftest import make_config

    cfg = make_config(llm={"primary": "gemini", "fallback": "none", "max_calls": 5, "model": "m",
                           "providers": {"gemini": {"key_env": "GEMINI_API_KEY", "rpm": 1, "tpm": 1},
                                         "groq": {"key_env": "GROQ_API_KEY", "rpm": 1, "tpm": 1}}})
    cfg["paths"]["llm_cache"] = "c"
    monkeypatch.setenv("GEMINI_API_KEY", "k1")
    monkeypatch.setenv("GROQ_API_KEY", "k2")
    from src.common.paths import PathResolver

    res = PathResolver.from_config(cfg, repo_root=tmp_path)
    client = L.build_client(cfg, res, run_id="t", env_file=tmp_path / "none.env", verify_models=False)
    assert [s.provider.name for s in client.slots] == ["gemini"]
    run_p4 = _load("run_p4", ROOT / "scripts" / "run_p4.py")
    with pytest.raises(SystemExit, match="fallback: none"):
        run_p4.make_llm({"llm": {"fallback": "groq"}, "p4": {}}, res, "x")


# -- demo -------------------------------------------------------------------------------------------------


def test_demo_renders_answer_filters_and_calls(prompts):
    demo = _load("demo", ROOT / "scripts" / "demo.py")
    res = make_res(_temporal())
    llm = FakeLLM([_answer_json("A bank shall report fraud within seven days.", "md_1::p00001")])
    log = PL.answer(res, prompts, llm, FakeNLI(), "report fraud", entity_class="A", as_of="2026-01-15")
    out = demo.render(log, res, calls=1, cache_hits=0, model="gemini-x")
    assert "class filter ON" in out and "temporal filter ON" in out and "verifier ON" in out
    assert "[md_1::p00001]" in out and "A Fraud Directions" in out and "[verifier: supported]" in out
    assert "original in force; amended from 2026-04-01" in out
    assert "LLM calls: 1 new" in out and "k1" not in out


def test_cache_only_mode_never_calls(tmp_path):
    class Prov:
        name = "gemini"
        calls = 0

        def list_models(self):
            return []

        def generate(self, model, messages, params):
            Prov.calls += 1
            return L.Completion(text="{}", provider="gemini", model=model, model_version="v", input_tokens=1, output_tokens=1)

    led = L.QuotaLedger(tmp_path / "q.json", soft_cap=10)
    client = L.LLMClient([L.ProviderSlot(Prov(), {"default": "m"}, rpm=100, tpm=10**6)], cache_dir=tmp_path / "c",
                         max_calls=10, ledger=led, sleep=lambda s: None)
    client.complete([{"role": "user", "content": "cached"}])
    client.cache_only = True
    assert client.complete([{"role": "user", "content": "cached"}]).cached
    with pytest.raises(L.CacheMiss):
        client.complete([{"role": "user", "content": "new"}])
    assert Prov.calls == 1 and led.used("m") == 1
