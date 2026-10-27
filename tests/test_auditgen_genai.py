"""Audit generator, generative-AI features: the loopback-only LLM gate, the sentence verifier, every feature on a scripted
local model, the activity log (hashes, never text), no remote calls, and the /api/auditgen/ai endpoints."""

from __future__ import annotations

import io
import json
import re

import pytest

from src.auditgen import ai_features as AI
from src.auditgen import gap_analysis as GAP
from src.auditgen import genai as G
from src.auditgen import pack as PK
from src.auditgen.corpus import get_store, load_config
from src.auditgen.profile import Profile
from tests.test_auditgen_gap_api import SECRET, FakeModels, _block_remote


class FakeLLM:
    """A scripted stand-in for the local Ollama model. ``reply`` maps a feature to a function(prompt) -> dict."""

    def __init__(self, **reply):
        self.reply = reply
        self.calls: list[str] = []

    FEATURES = (("QUESTION:", "ask"), ("Explain this paragraph", "explain"), ("BEFORE THE AMENDMENT", "change"),
                ("FACTS FROM THE AUDIT PACK", "memo"), ("ITEMS FROM THE AUDIT PACK", "plan"), ("Draft one clause", "draft"),
                ("set a deadline or a frequency", "calendar"), ("state the same duty", "diff"), ("Should a reviewer confirm", "suggest"))

    def chat(self, messages, *, model=None, json_mode=True):
        prompt = messages[-1]["content"]
        feature = next(f for k, f in self.FEATURES if k in prompt)
        self.calls.append(feature)
        out = self.reply[feature](prompt)
        return {"text": json.dumps(out), "json": out, "model": "fake-local", "seconds": 0.01, "eval_tokens": 1}


def evidence(prompt: str, label: str) -> str:
    m = re.search(rf"\[{label}\][^\n]*\n(.*?)(?:\n\n\[E\d+\]|\n\nEvery sentence)", prompt, re.S)
    return m.group(1).strip() if m else ""


def para(prompt: str, marker: str) -> str:
    return prompt.split(marker, 1)[1].split("\n\n", 1)[0].strip()


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def store(cfg):
    return get_store(cfg)


@pytest.fixture()
def gcfg(tmp_path):
    g = G.load_genai_config()
    g["storage"] = {"ai_cache": str(tmp_path / "genai"), "activity_log": str(tmp_path / "genai/activity.jsonl")}
    return g


@pytest.fixture()
def lcfg(cfg, tmp_path):
    return {**cfg, "paths": {**cfg["paths"], "runs": str(tmp_path / "runs"), "samples": str(tmp_path / "samples")}}


@pytest.fixture(scope="module")
def pack(store, cfg):
    return PK.generate(store, cfg, Profile("GenAI test", "Small Finance Banks", "2026-10-15", "2025-12-01", ["kyc_aml"], ["Payments Banks"]))


def _row(pack, pred=lambda r: True):
    return next(r for r in pack["register"] if not r["hidden"] and r["paragraph_id"] and pred(r))


# -- gate and verifier --------------------------------------------------------------------------------------------------

def test_local_llm_refuses_non_loopback_hosts(gcfg):
    for bad in ("https://api.example.com", "http://10.0.0.5:11434", "http://0.0.0.0:11434"):
        with pytest.raises(G.GenAIError):
            G.LocalLLM({**gcfg, "llm": {**gcfg["llm"], "host": bad}})

    class Tags:
        def __init__(self, names):
            self.names = names

        def get(self, url, timeout):
            assert url.startswith("http://127.0.0.1:")
            return type("R", (), {"json": lambda s: {"models": [{"name": n} for n in self.names]}})()

    assert G.LocalLLM(gcfg, http=Tags(["qwen2.5:1.5b-instruct", "qwen2.5:7b-instruct"])).status()["model"] == "qwen2.5:7b-instruct"
    assert G.LocalLLM(gcfg, http=Tags(["qwen2.5:1.5b-instruct"])).status()["model"] == "qwen2.5:1.5b-instruct"
    st = G.LocalLLM(gcfg, http=Tags(["llama3:8b"])).status()
    assert st["available"] is False and "ollama pull" in st["reason"]
    with pytest.raises(G.GenAIError):
        G.LocalLLM(gcfg, http=Tags([])).pick()


def test_verifier_needs_entailment_citation_and_source_numbers():
    premise = "The bank shall report the fraud to RBI within 7 days of detection."
    # The fake NLI entails when > 90% of the hypothesis words are in the premise, so the "9" sentence is entailed and only
    # the numbers check rejects it.
    out = G.verify(FakeModels(), [{"text": "The bank shall report the fraud to RBI within 7 days of detection.", "premise": premise},
                                  {"text": "The bank shall report the fraud to RBI within 9 days of detection.", "premise": premise},
                                  {"text": "Board approval is needed for every loan.", "premise": premise},
                                  {"text": "Uncited claim.", "premise": ""}])
    assert [o["verified"] for o in out] == [True, False, False, False]
    assert out[3]["reason"] == "no valid citation" and "premise" not in out[0]
    # Several citations: each is checked on its own, so a long first paragraph cannot crowd out the second.
    filler = " ".join(["unrelated words"] * 400)
    multi = G.verify(FakeModels(), [{"text": "The bank shall report the fraud to RBI within 7 days of detection.", "premises": [filler, premise]}])
    assert multi[0]["verified"] and "premises" not in multi[0] and "_cands" not in multi[0]
    assert G.numbers("on 01-12-2025 and 1,000 or 2.5") == {"1", "12", "2025", "1000", "2.5"}
    assert G.quote_in("report the fraud to RBI", premise) and not G.quote_in("report it", premise)


# -- features -----------------------------------------------------------------------------------------------------------

def test_ask_cites_verifies_retries_and_abstains(store, cfg, gcfg, pack):
    def answer(prompt):
        e1 = evidence(prompt, "E1")
        return {"can_answer": True, "sentences": [{"text": " ".join(e1.split()[:14]), "citations": ["E1"]},
                                                  {"text": "Every loan needs board approval within 3 days.", "citations": ["E1"]},
                                                  {"text": " ".join(e1.split()[:10]), "citations": ["E99"]}]}

    llm = FakeLLM(ask=answer)
    r = AI.ask(store, cfg, gcfg, pack, "How must customer identity be verified under KYC?", llm=llm, models=FakeModels())
    assert r["attempts"] == 2 and llm.calls == ["ask", "ask"]  # unsupported sentences -> one retry
    kept = [s for s in r["sentences"] if s["verified"]]
    assert len(kept) == 1 and not r["abstained"]
    src = kept[0]["sources"][0]
    assert src["paragraph_id"] == r["evidence"][0]["paragraph_id"] and src["source_url"].startswith("https://")
    assert {s["reason"] for s in r["sentences"] if not s["verified"]} >= {"no valid citation"}
    assert all("text" not in e for e in r["evidence"]) and len(r["evidence"]) == gcfg["ask"]["evidence"]
    assert r["label"] == G.LABEL and r["disclaimer"] == cfg["disclaimer"]

    r2 = AI.ask(store, cfg, gcfg, pack, "What is the capital of France?", llm=FakeLLM(ask=lambda p: {"can_answer": False, "sentences": []}),
                models=FakeModels())
    assert r2["abstained"] and r2["attempts"] == 1 and "cannot answer" in r2["answer"]
    with pytest.raises(AI.FeatureError):
        AI.ask(store, cfg, gcfg, pack, "x" * 700, llm=llm, models=FakeModels())


def test_explain_obligation_checks_sentences_and_quote(store, cfg, gcfg, pack):
    row = _row(pack)
    text = AI.para_text(store, row["paragraph_id"])

    def reply(prompt):
        return {"plain_summary": [" ".join(text.split()[:12])], "actions": ["Hire a chief risk officer by 2031."],
                "who_must_act": " ".join(text.split()[:4]), "deadline_or_frequency": None, "evidence_quote": " ".join(text.split()[2:9])}

    r = AI.explain_obligation(store, cfg, gcfg, pack, row["row_id"], llm=FakeLLM(explain=reply), models=FakeModels())
    by = {s["part"]: s for s in r["sentences"]}
    assert by["summary"]["verified"] and not by["action"]["verified"] and by["who"]["verified"]
    assert r["evidence_quote_found"] and r["row"]["paragraph_id"] == row["paragraph_id"]
    with pytest.raises(AI.FeatureError):
        AI.explain_obligation(store, cfg, gcfg, pack, "APP-nope", llm=FakeLLM(explain=reply), models=FakeModels())


def test_explain_change_direction_level_rows_are_not_guessed(store, cfg, gcfg, pack):
    d = next((c for c in pack["changes"] if not c.get("paragraph_id")), None)
    if d:
        r = AI.explain_change(store, cfg, gcfg, pack, d["row_id"], llm=FakeLLM(), models=FakeModels())
        assert r["abstained"] and "not identified" in r["note"]
    p = next((c for c in pack["changes"] if c.get("paragraph_id")), None)
    if p:
        def reply(prompt):
            before = para(prompt, "BEFORE THE AMENDMENT:\n")
            return {"what_changed": [" ".join(before.split()[:10])], "impact": ["Customers get a free car."]}

        r = AI.explain_change(store, cfg, gcfg, pack, p["row_id"], llm=FakeLLM(change=reply), models=FakeModels())
        assert [s["verified"] for s in r["sentences"]] == [True, False] and r["amendment"]["id"] == p["governing_instrument"]


def test_memo_numbers_must_come_from_the_facts(store, cfg, gcfg, pack):
    s = pack["summary"]

    def reply(prompt):
        return {"subject": "Audit pack", "sections": [{"heading": "Overview", "sentences": [
            {"text": f"The register shows {s['register_visible']} applicable obligations.", "facts": ["F2"]},
            {"text": "The register shows 123456 applicable obligations.", "facts": ["F2"]},
            f"{s['needs_review']} obligations need human review.",
            "We should hire more staff."]}]}

    r = AI.memo(store, cfg, gcfg, pack, llm=FakeLLM(memo=reply), models=FakeModels())
    sent = r["sections"][0]["sentences"]
    assert [x["verified"] for x in sent] == [True, False, True, False]
    assert "123456" in sent[1]["reason"] and sent[2]["facts"] and sent[3]["reason"] == "cites no fact"
    assert any(f["text"].startswith("The applicability register has") for f in r["facts"])
    doc = AI.memo_docx(r)
    import docx

    body = " ".join(p.text for p in docx.Document(io.BytesIO(doc)).paragraphs)
    assert "123456" not in body and cfg["disclaimer"] in body


def test_action_plan_items_must_point_at_pack_rows(store, cfg, gcfg, pack):
    fs = [f for f in AI.facts(pack, gcfg) if f.get("ref")]
    assert fs, "the test pack needs changes or deadlines"

    def reply(prompt):
        return {"actions": [{"item": fs[0]["id"], "priority": "high", "action": "Read the amended paragraph and update the procedure.", "why": "It changed."},
                            {"item": "F999", "priority": "low", "action": "Do something.", "why": ""},
                            {"item": fs[0]["id"], "priority": "medium", "action": "Again.", "why": ""}]}

    r = AI.action_plan(store, cfg, gcfg, pack, llm=FakeLLM(plan=reply), models=FakeModels())
    assert [i["verified"] for i in r["items"]] == [True, False, False]
    assert r["items"][0]["ref"] == fs[0]["ref"] and {i["reason"] for i in r["items"][1:]} == {"unknown item id", "repeated item"}


def test_draft_clause_is_scored_by_the_gap_rule(store, cfg, gcfg, pack):
    row = _row(pack)
    cand = {c["candidate_id"]: c for c in store.candidates()}[row["obligation_id"]]
    obl = store.obligation_sentence(cand)
    good = AI.draft_clause(store, cfg, gcfg, pack, row["row_id"], llm=FakeLLM(draft=lambda p: {"title": "T", "clause": obl, "owner": "Compliance"}),
                           models=FakeModels(), company="Acme SFB")
    assert good["check"]["coverage"] == "covered" and good["company"] == "Acme SFB"
    bad = AI.draft_clause(store, cfg, gcfg, pack, row["row_id"], llm=FakeLLM(draft=lambda p: {"clause": "Staff may wear blue on Fridays."}),
                          models=FakeModels())
    assert bad["check"]["coverage"] == "missing" and not bad["sentences"][0]["verified"]


def test_calendar_check_needs_a_real_quote(store, cfg, gcfg, pack):
    entries = [e for e in pack["calendar"] if e.get("paragraph_id")][:2]
    assert entries

    def reply(prompt):
        text = para(prompt, "PARAGRAPH:\n")
        return {"kind": "recurring", "frequency": entries[0].get("frequency"), "quote": " ".join(text.split()[:6]), "what": "file"}

    r = AI.calendar_check(store, cfg, gcfg, pack, [e["entry_id"] for e in entries], llm=FakeLLM(calendar=reply))
    assert len(r["results"]) == len(entries) and all(x["ai"]["quote_found"] for x in r["results"])
    assert r["agreement"]["n"] == len(entries) and "not accuracy" in r["note"]
    r2 = AI.calendar_check(store, cfg, gcfg, pack, [entries[0]["entry_id"]], llm=FakeLLM(calendar=lambda p: {"kind": "weekly?", "quote": "made up words here"}))
    assert r2["results"][0]["ai"]["kind"] == "none" and not r2["results"][0]["verified"]


def test_diff_second_opinion_uses_the_frozen_comparator_rule(store, cfg, gcfg, pack):
    from src.rag import comparator_rule as CR

    row = next(r for r in pack["differential"] if r.get("counterpart_paragraph_id"))
    equal = {f: "equal" for f in CR.FIELDS}
    same = AI.diff_second_opinion(store, cfg, gcfg, pack, row["row_id"],
                                  llm=FakeLLM(diff=lambda p: {"addresses_same_duty": True, "field_comparison": equal}))
    assert same["judgement"] == "same" and same["rule"] == CR.RULE_VERSION and "Second opinion" in same["caution"]
    diff = AI.diff_second_opinion(store, cfg, gcfg, pack, row["row_id"],
                                  llm=FakeLLM(diff=lambda p: {"addresses_same_duty": True, "field_comparison": {**equal, "deadline": "differs"},
                                                              "differences": [{"field": "deadline", "source": "nonexistent words here", "target": ""}]}))
    assert diff["judgement"] == "different" and diff["differences"][0]["source_found"] is False
    bad = AI.diff_second_opinion(store, cfg, gcfg, pack, row["row_id"], llm=FakeLLM(diff=lambda p: {"field_comparison": {}}))
    assert bad["judgement"] == "unsure"


def test_review_suggestion_never_changes_the_row(store, cfg, gcfg, pack):
    row = _row(pack)
    text = AI.para_text(store, row["paragraph_id"])
    before = json.dumps(row, sort_keys=True)
    ok = AI.review_suggestion(store, cfg, gcfg, pack, "register", row["row_id"],
                              llm=FakeLLM(suggest=lambda p: {"suggestion": "confirm", "reason": " ".join(text.split()[:12]) + "."}), models=FakeModels())
    assert ok["suggestion"] == "confirm" and ok["current_review_status"] == "unreviewed"
    weak = AI.review_suggestion(store, cfg, gcfg, pack, "register", row["row_id"],
                                llm=FakeLLM(suggest=lambda p: {"suggestion": "dispute", "reason": "The moon is made of cheese."}), models=FakeModels())
    assert weak["suggestion"] == "unsure" and weak["raw_suggestion"] == "dispute"
    assert json.dumps(row, sort_keys=True) == before


# -- privacy ------------------------------------------------------------------------------------------------------------

def test_no_remote_calls_and_no_text_in_the_activity_log(store, lcfg, gcfg, pack, monkeypatch):
    _block_remote(monkeypatch)
    q = f"Does {SECRET} matter?"
    llm = FakeLLM(ask=lambda p: {"can_answer": True, "sentences": [{"text": " ".join(evidence(p, "E1").split()[:12]), "citations": ["E1"]}]})
    r = AI.ask(store, lcfg, gcfg, pack, q, llm=llm, models=FakeModels())
    G.record(lcfg, gcfg, pack["pack_id"], "ask", None, r)
    log = (G.ROOT / gcfg["storage"]["activity_log"]).read_text()
    assert "Zebra-Quartz" not in log and G.sha(" ".join(q.split())) in log
    row = json.loads(log.splitlines()[-1])
    assert row["feature"] == "ask" and row["verified"] == 1 and set(row) >= {"input_sha256", "output_sha256", "model"}
    stored = G.load_ai(lcfg, pack["pack_id"])
    assert stored["ask"][0]["question"] == " ".join(q.split()) and stored["genai_version"] == gcfg["version"]
    # The embedding cache holds RBI paragraph vectors only.
    import numpy as np

    z = np.load(next((G.ROOT / gcfg["storage"]["ai_cache"]).glob("emb_*.npz")))
    assert all(str(i).startswith("md_") for i in z["ids"])


# -- API ----------------------------------------------------------------------------------------------------------------

@pytest.fixture()
def client(lcfg, gcfg, monkeypatch):
    from fastapi.testclient import TestClient

    from src.auditgen import api as API

    def evidence_answer(p):
        return {"can_answer": True, "sentences": [{"text": " ".join(evidence(p, "E1").split()[:12]), "citations": ["E1"]}]}

    from src.rag import comparator_rule as CR

    fake = FakeLLM(ask=evidence_answer,
             explain=lambda p: {"plain_summary": [" ".join(para(p, "):\n").split()[:10])], "actions": [], "evidence_quote": ""},
             change=lambda p: {"what_changed": [], "impact": []},
             memo=lambda p: {"subject": "S", "sections": [{"heading": "Overview", "sentences": [{"text": "See the register.", "facts": ["F2"]}]}]},
             plan=lambda p: {"actions": [{"item": "F1", "action": "x"}]},
             draft=lambda p: {"clause": "Staff shall do things."},
             calendar=lambda p: {"kind": "none"},
             diff=lambda p: {"addresses_same_duty": True, "field_comparison": {f: "equal" for f in CR.FIELDS}},
             suggest=lambda p: {"suggestion": "confirm", "reason": "Because."})

    class Status:
        def status(self):
            return {"available": True, "model": "fake-local", "pulled": ["fake-local"], "reason": ""}

        def __getattr__(self, k):
            return getattr(fake, k)

    monkeypatch.setattr(API, "load_config", lambda: lcfg)
    monkeypatch.setattr(API, "load_genai_config", lambda: gcfg)
    monkeypatch.setattr(API, "make_llm", lambda g: Status())
    monkeypatch.setattr(GAP.LocalModels, "get", classmethod(lambda cls, c: FakeModels()))
    return TestClient(API.create_app()), fake


def test_ai_api_endpoints(client):
    c, fake = client
    st = c.get("/api/auditgen/ai/status").json()
    assert st["available"] and st["remote_api_calls"] is False and st["host"].startswith("http://127.0.0.1")
    pk = c.post("/api/auditgen/generate", json={"name": "AI API", "entity_class": "Small Finance Banks", "as_of": "2026-10-15",
                                                 "last_review": "2025-12-01", "activities": ["kyc_aml"], "group_classes": ["Payments Banks"]}).json()
    pid = pk["pack_id"]
    row = next(r for r in pk["register"] if not r["hidden"])
    a = c.post(f"/api/auditgen/ai/packs/{pid}/ask", json={"question": "How is identity verified?"}).json()
    assert a["sentences"] and a["sentences"][0]["sources"]
    assert c.post(f"/api/auditgen/ai/packs/{pid}/ask", json={"question": ""}).status_code == 422
    assert c.post(f"/api/auditgen/ai/packs/{pid}/explain", json={"row_id": row["row_id"]}).status_code == 200
    assert c.post(f"/api/auditgen/ai/packs/{pid}/explain", json={"row_id": "nope"}).status_code == 422
    chg = next((x for x in pk["changes"]), None)
    if chg:
        assert c.post(f"/api/auditgen/ai/packs/{pid}/change", json={"row_id": chg["row_id"]}).status_code == 200
    assert c.get(f"/api/auditgen/ai/packs/{pid}/memo.docx").status_code == 404
    assert c.post(f"/api/auditgen/ai/packs/{pid}/memo", json={}).json()["sections"]
    d = c.get(f"/api/auditgen/ai/packs/{pid}/memo.docx")
    assert d.status_code == 200 and "wordprocessingml" in d.headers["content-type"]
    assert c.post(f"/api/auditgen/ai/packs/{pid}/plan", json={}).status_code == 200
    assert c.post(f"/api/auditgen/ai/packs/{pid}/draft", json={"row_id": row["row_id"], "company": "Acme"}).json()["company"] == "Acme"
    assert c.post(f"/api/auditgen/ai/packs/{pid}/draft", json={"row_id": row["row_id"], "section": "changes"}).status_code == 422
    assert c.post(f"/api/auditgen/ai/packs/{pid}/calendar", json={}).status_code == 200
    dif = next(r for r in pk["differential"] if r.get("counterpart_paragraph_id"))
    assert c.post(f"/api/auditgen/ai/packs/{pid}/diff", json={"row_id": dif["row_id"]}).json()["judgement"] == "same"
    sg = c.post(f"/api/auditgen/ai/packs/{pid}/suggest", json={"section": "register", "row_id": row["row_id"]}).json()
    assert sg["suggestion"] == "unsure"  # "Because." is not supported by the paragraph
    assert c.get(f"/api/auditgen/packs/{pid}").json()["register"][0]["review_status"] == "unreviewed"
    store = c.get(f"/api/auditgen/ai/packs/{pid}").json()
    assert {"ask", "explain", "memo", "plan", "draft", "calendar", "diff", "suggest"} <= set(store)
    assert f"register:{row['row_id']}" in store["suggest"]
    acts = c.get("/api/auditgen/ai/activity").json()
    assert len(acts) >= 8 and all("question" not in json.dumps(x) for x in acts)
    assert c.get("/api/auditgen/ai/packs/..%2F..%2Fetc").status_code == 404
    assert c.post("/api/auditgen/ai/packs/no_such_pack/memo", json={}).status_code == 404


def test_ai_api_reports_a_missing_local_model(client, monkeypatch):
    from src.auditgen import api as API

    c, _ = client

    class Down:
        def status(self):
            return {"available": False, "model": None, "pulled": [], "reason": "no local runtime"}

        def chat(self, *a, **k):
            raise G.GenAIError("no local runtime")

    monkeypatch.setattr(API, "make_llm", lambda g: Down())
    assert c.get("/api/auditgen/ai/status").json()["available"] is False
    pk = c.post("/api/auditgen/generate", json={"name": "AI down", "entity_class": "Payments Banks", "as_of": "2026-10-15",
                                                 "last_review": "2025-12-01", "activities": ["kyc_aml"], "group_classes": []}).json()
    assert c.post(f"/api/auditgen/ai/packs/{pk['pack_id']}/memo", json={}).status_code == 503
