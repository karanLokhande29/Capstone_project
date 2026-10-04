"""Comparator API tests (Demo Build Spec H, acceptance): mocked LLM only, no network, no key.

    python3 -m pytest -q -o addopts= -p no:cacheprovider ui/api/tests
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1]
UI = API.parent
ROOT = UI.parent
sys.path.insert(0, str(API))
sys.path.insert(0, str(UI / "scripts"))
sys.path.insert(0, str(ROOT))

import core  # noqa: E402
from jsonstream import JsonStream, JsonStreamError  # noqa: E402

pytestmark = pytest.mark.skipif(not (API / ".data/inputs.json").exists(), reason="run ui/api/build_bundle.py first (needs the local corpus)")

SEALED_DIR = ROOT / "data/rag_runs/sealed_phase4/comparator_t1_gold_v1"


def sealed() -> dict:
    out = {}
    for p in SEALED_DIR.glob("t1_*.json"):
        r = json.loads(p.read_text())
        out[f"{r['item_id']}|{r['target_class']}"] = r
    return out


SEALED = sealed() if SEALED_DIR.exists() else {}
INPUTS = json.loads((API / ".data/inputs.json").read_text()) if (API / ".data/inputs.json").exists() else {}


def sealed_reply_for(user: str) -> str:
    """Mock model: answers with the sealed raw output of the unit whose prompt this is."""
    for uid, u in INPUTS.items():
        if u["candidates"][0][0] in user and u["source_text"][:200] in user and f"{u['target_class']}" in user:
            return SEALED[uid]["raw"]
    return '{"source": {}, "candidates": []}'


def service(tmp_path, llm=None, **kw):
    s = core.build_service(mode=kw.pop("mode", "public"), llm=llm, store=core.FileStore(tmp_path / "store"), **kw)
    return s


def mock(**kw):
    return core.MockLlm(lambda system, user: sealed_reply_for(user), **kw)


def run(svc, body, client="t"):
    return list(svc.compare(body, client=client))


# ---- jsonstream ----------------------------------------------------------------------------------------------------

def flatten(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flatten(v, path + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flatten(v, path + (i,))
    else:
        yield path, o


@pytest.mark.parametrize("seed", range(5))
def test_jsonstream_emits_every_leaf_once_and_only_when_complete(seed):
    raw = next(iter(SEALED.values()))["raw"]
    want = list(flatten(json.loads(raw)))
    rng = random.Random(seed)
    js, got, i = JsonStream(), [], 0
    while i < len(raw):
        n = rng.randint(1, 40)
        got += js.feed(raw[i:i + n])
        i += n
    assert got == want
    js2 = JsonStream()
    assert js2.feed('{"source": {"actor": "A ba') == []  # an unfinished string is never emitted
    assert js2.feed('nk", ') == [(("source", "actor"), "A bank")]


def test_jsonstream_rejects_garbage():
    with pytest.raises(JsonStreamError):
        JsonStream().feed('{"a": nope}')


# ---- frozen files and health ---------------------------------------------------------------------------------------

def test_health_without_key_reports_model_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("ASSISTANT_GEMINI_API_KEY", raising=False)
    s = service(tmp_path)
    h = s.health()
    assert h["hashes"]["verified"] and not h["model"]["available"] and "key" in h["model"]["reason"]
    with pytest.raises(core.ServiceError) as e:
        run(s, {"mode": "benchmark", "unitId": next(iter(INPUTS))})
    assert e.value.status == 503 and e.value.replay_key


def test_hash_mismatch_disables_compare(tmp_path):
    b = tmp_path / "bundle"
    shutil.copytree(API / "bundle", b)
    (b / "obli_frozen/comparator_system.txt").write_text("tampered")
    fz = core.Frozen(b)
    assert not fz.verified and fz.mismatches == ["comparator_system.txt"]
    s = core.Service(frozen=fz, conf=core.Confidence(), llm=mock(), store=core.FileStore(tmp_path / "s"), inputs=INPUTS)
    assert s.health()["hashes"]["verified"] is False and s.health()["model"]["available"] is False
    with pytest.raises(core.ServiceError) as e:
        run(s, {"mode": "benchmark", "unitId": next(iter(INPUTS))})
    assert e.value.status == 503


def test_bundle_copy_of_comparator_differs_only_in_the_import_line():
    a = (ROOT / "src/rag/comparator.py").read_text().splitlines()
    b = (API / "bundle/obli_frozen/comparator.py").read_text().splitlines()
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and len(diff) == 1 and "comparator_rule as RULE" in diff[0][1]


# ---- benchmark runs (acceptance: 5 units end to end) ------------------------------------------------------------------

def test_five_benchmark_units_end_to_end_reproduce_the_sealed_output(tmp_path):
    import cc_common as C

    model = json.loads((UI / "src/data/confidence_model_v1.json").read_text())
    s = service(tmp_path, llm=mock())
    for uid in sorted(INPUTS)[:5]:
        evs = run(s, {"mode": "benchmark", "unitId": uid})
        types = [e["type"] for e in evs]
        assert types[0] == "status" and types[-3:] == ["verdict", "confidence", "done"] and "field" in types
        v = next(e["data"] for e in evs if e["type"] == "verdict")
        rec = SEALED[uid]
        assert v["judgement"] == rec["judgement"] and v["matchedPid"] == rec.get("matched_paragraph_id")
        df = C.decisive_fields(rec)
        if df:
            assert [r["status"] for r in v["rows"]] == [r["status"] for r in df["rows"]]
        c = next(e["data"] for e in evs if e["type"] == "confidence")
        assert c["band"] == model["units"][uid]["M2"]["band"]
        if c["p"] is not None:
            assert abs(c["p"] - model["units"][uid]["M2"]["p"]) < 1e-9
        n_fields = sum(1 for e in evs if e["type"] == "field")
        assert n_fields == sum(1 for p, _ in flatten(json.loads(rec["raw"])) if core._field_event(p, None, {}, s.frozen.rule) or p[-1] == "paragraph_id") - len(json.loads(rec["raw"])["candidates"])
        done = evs[-1]["data"]
        assert done["cacheKey"] == core.cache_key(s.frozen.prompt_sha, s.frozen.rule_sha, s.llm.id, "benchmark", {"unitId": uid})
        rep = s.replay(done["cacheKey"])
        assert [e["type"] for e in rep["events"]] == types and rep["events"][-1]["data"]["replay"] is True
        assert s.store.count("replays") == 0  # a test double's runs are never stored as live replays
        real = core.Service(frozen=s.frozen, conf=s.conf, llm=None, store=s.store, inputs=INPUTS)
        assert real.replay(done["cacheKey"])["found"] is False


def test_signals_and_m2_mirror_the_ingest_on_every_sealed_unit():
    import cc_common as C

    fz, conf = core.Frozen(), core.Confidence()
    model = json.loads((UI / "src/data/confidence_model_v1.json").read_text())
    for uid, rec in SEALED.items():
        raw = C.parse_raw(rec) if not rec.get("parse_problems") else None
        sig = core.signals(fz.rule, raw, rec["judgement"], rec.get("matched_paragraph_id"))
        ref = C.comparator_signals(rec)
        for k in ("n_both", "n_material_diff", "hinge", "candidates_agree"):
            assert sig[k] == ref[k], (uid, k)
        score = conf.score(conf.features(sig, rec["judgement"], INPUTS[uid]["source_class"], INPUTS[uid]["source_md"]))
        assert score["band"] == model["units"][uid]["M2"]["band"], uid


def test_network_loss_mid_stream_gives_a_clean_error_and_a_replay_offer(tmp_path):
    s = service(tmp_path, llm=mock(fail_after=200))
    evs = run(s, {"mode": "benchmark", "unitId": sorted(INPUTS)[0]})
    assert evs[-1]["type"] == "error" and evs[-1]["data"]["replayKey"]
    assert not any(e["type"] == "verdict" for e in evs)


def test_buffered_mode_never_emits_field_events(tmp_path):
    s = service(tmp_path, llm=mock(), streaming="buffered")
    evs = run(s, {"mode": "benchmark", "unitId": sorted(INPUTS)[1]})
    assert not any(e["type"] == "field" for e in evs) and evs[0]["data"]["streaming"] == "buffered"
    assert any(e["type"] == "verdict" for e in evs)


def test_unparseable_stream_falls_back_to_buffered_without_synthetic_fields(tmp_path):
    s = service(tmp_path, llm=core.MockLlm(lambda a, b: '{"source": {"actor": oops}}'))
    evs = run(s, {"mode": "benchmark", "unitId": sorted(INPUTS)[2]})
    assert [e["data"].get("streaming") for e in evs if e["type"] == "status"] == ["incremental", "buffered"]
    assert next(e["data"] for e in evs if e["type"] == "verdict")["judgement"] == "unsure"


def test_rate_limit_returns_429_with_a_replay_key(tmp_path):
    s = service(tmp_path, llm=mock())
    uid = sorted(INPUTS)[0]
    for _ in range(6):
        run(s, {"mode": "benchmark", "unitId": uid}, client="1.2.3.4")
    with pytest.raises(core.ServiceError) as e:
        run(s, {"mode": "benchmark", "unitId": uid}, client="1.2.3.4")
    assert e.value.status == 429 and e.value.replay_key
    run(s, {"mode": "benchmark", "unitId": uid}, client="5.6.7.8")  # other clients unaffected


# ---- paste privacy ------------------------------------------------------------------------------------------------

def test_paste_mode_never_persists_or_logs_the_text(tmp_path, caplog):
    marker = "ZQX-MARKER-7f3a91"
    reply = json.dumps({"source": {"actor": f"{marker} bank", "action": "report"}, "candidates": [
        {"paragraph_id": "pasted::B", "addresses_same_duty": True, "fields": {"actor": f"{marker} nbfc"},
         "field_comparison": {f: ("differs" if f == "actor" else "absent") for f in core.Frozen().rule.FIELDS}}]})
    s = service(tmp_path, llm=core.MockLlm(lambda a, b: reply))
    with caplog.at_level(logging.DEBUG):
        evs = run(s, {"mode": "paste", "textA": f"A {marker} bank shall report.", "textB": f"An {marker} NBFC shall report.",
                      "classA": "Commercial Banks", "classB": "Non-Banking Financial Companies"})
    assert next(e["data"] for e in evs if e["type"] == "verdict")["judgement"] == "different"
    stored = "".join(p.read_text() for p in (tmp_path / "store").rglob("*") if p.is_file())
    assert stored and marker not in stored
    assert marker not in caplog.text
    assert evs[-1]["data"]["cacheKey"] is None and s.store.count("replays") == 0


# ---- edit mode -----------------------------------------------------------------------------------------------------

def test_edit_mode_applies_the_edit_to_the_target_paragraph_and_logs_the_run(tmp_path):
    seen = []
    s = service(tmp_path, llm=core.MockLlm(lambda a, b: (seen.append(b), SEALED[uid]["raw"])[1]))
    uid = next(u for u, x in INPUTS.items() if x.get("sealed_matched") and "shall" in dict(map(tuple, x["candidates"]))[x["sealed_matched"]])
    tgt = dict(map(tuple, INPUTS[uid]["candidates"]))[INPUTS[uid]["sealed_matched"]]
    i = tgt.index("shall")
    evs = run(s, {"mode": "edit", "unitId": uid, "edits": [{"kind": "exception", "from": "shall", "to": "shall, except where exempted,"}], "control": "reproduced"})
    assert "shall, except where exempted," in seen[0] and tgt[:i] in seen[0]
    assert evs[-1]["type"] == "done"
    logged = [json.loads(x) for x in (tmp_path / "store/lab_runs.jsonl").read_text().splitlines()]
    assert logged[-1]["unitId"] == uid and logged[-1]["control"] == "reproduced"
    with pytest.raises(core.ServiceError) as e:
        run(s, {"mode": "edit", "unitId": uid, "edits": [{"kind": "deadline", "from": "not in the text at all", "to": "x"}]})
    assert e.value.status == 400


# ---- presenter-only full text ---------------------------------------------------------------------------------------

def test_full_text_only_in_presenter_mode(tmp_path):
    pub = service(tmp_path)
    with pytest.raises(core.ServiceError) as e:
        pub.rehydrate("md_12949::p00040")
    assert e.value.status == 403 and pub.health()["rehydrate"] is False
    pres = service(tmp_path, mode="presenter")
    assert "Structural Liquidity" in pres.rehydrate("md_12949::p00040")["text"] and pres.health()["rehydrate"] is True


# ---- the local HTTP server -------------------------------------------------------------------------------------------

def test_http_server_streams_sse_and_reports_health(tmp_path):
    import server

    s = service(tmp_path, llm=mock())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(s))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        h = json.loads(urllib.request.urlopen(f"{base}/api/health").read())
        assert h["model"]["available"] and h["model"]["mock"]
        req = urllib.request.Request(f"{base}/api/compare", data=json.dumps({"mode": "benchmark", "unitId": sorted(INPUTS)[0]}).encode(),
                                     headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as r:
            assert r.headers["Content-Type"] == "text/event-stream"
            text = r.read().decode()
        assert "event: verdict" in text and text.strip().endswith("}")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/api/rehydrate/md_12949::p00040")
        assert e.value.code == 403
    finally:
        httpd.shutdown()
