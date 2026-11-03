"""Hosted audit generator service: routes, storage, review, exports, the 12-word cap and the assistant (a stand-in LLM;
the real ONNX models). Skipped when the models or vectors are not built (scripts/auditgen_hosted_models.py).

    python3 -m pytest ui/api_audit/test_service.py -q
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT)]
MODELS = HERE / ".build/models"
pytestmark = pytest.mark.skipif(not list((MODELS / "vectors").glob("*.npz")) if (MODELS / "vectors").exists() else True,
                                reason="hosted models/vectors not built")


class EchoLLM:
    """Answers with the first sentence of the first evidence paragraph, cited to it (what a faithful model would say)."""

    calls = 0

    def status(self):
        return {"available": True, "model": "echo", "pulled": ["echo"], "preferred": ["echo"], "reason": ""}

    def chat(self, messages, *, model=None, json_mode=True):
        EchoLLM.calls += 1
        user = messages[-1]["content"]
        m = re.search(r"\[E1\][^\n]*\n(.+)", user)
        first = re.split(r"(?<=[.;:])\s", m.group(1).strip())[0] if m else ""
        out = {"can_answer": bool(first), "sentences": [{"text": first, "citations": ["E1"]}] if first else []}
        return {"text": json.dumps(out), "json": out, "model": "echo", "seconds": 0.0, "eval_tokens": 0}


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    from service import DirStore, Service

    tmp = tmp_path_factory.mktemp("hosted")
    return Service(DirStore(tmp / "store"), models_dir=MODELS, samples_dir=ROOT / "ui/.public-auditgen", llm=EchoLLM(), work_dir=tmp / "work")


PROFILE = {"name": "Test Bank <script>", "entity_class": "Small Finance Banks", "as_of": "2026-10-30", "last_review": "2025-12-01",
           "activities": ["deposits", "kyc_aml"], "group_classes": ["Commercial Banks"]}


def longest_run(obj, svc) -> int:
    from src.release.rbi_text import copied_runs

    best = 0

    def walk(v):
        nonlocal best
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            for r in copied_runs(v, svc.index, min_words=13):
                best = max(best, r.length)

    walk(obj)
    return best


def test_health_vocab_samples(svc):
    assert svc.handle("GET", "health", None, "c")["mode"] == "hosted"
    assert len(svc.handle("GET", "vocab", None, "c")["classes"]) == 11
    packs = svc.handle("GET", "packs", None, "c")
    assert len(packs) == 11 and all(p["kind"] == "sample" for p in packs)


def test_generate_review_signoff_export(svc):
    from service import HttpError

    p = svc.handle("POST", "generate", PROFILE, "c")
    assert p["hosted"] and p["register"] and p["profile"]["entity_class"] == "Small Finance Banks"
    assert longest_run(p, svc) == 0, "a generated pack quotes more than 12 words of RBI text"
    again = svc.handle("GET", f"packs/{p['pack_id']}", None, "c")
    assert again["pack_id"] == p["pack_id"]
    row = next(r for r in p["register"] if not r["hidden"])
    with pytest.raises(HttpError) as e:
        svc.handle("POST", f"packs/{p['pack_id']}/review", [{"section": "register", "row_id": row["row_id"], "review_status": "confirmed", "reviewer": ""}], "c")
    assert e.value.status == 422
    r = svc.handle("POST", f"packs/{p['pack_id']}/review", [{"section": "register", "row_id": row["row_id"], "review_status": "confirmed", "reviewer": "rater_1"}], "c")
    assert r["updated"] == 1
    svc.cache.clear()  # read back from storage, not memory
    stored = svc.handle("GET", f"packs/{p['pack_id']}", None, "c")
    assert next(x for x in stored["register"] if x["row_id"] == row["row_id"])["review_status"] == "confirmed"
    s = svc.handle("POST", f"packs/{p['pack_id']}/signoff", {"signer": "rater_1"}, "c")
    assert s["signoff"]["signer"] == "rater_1" and s["pack_id"] != p["pack_id"]
    with pytest.raises(HttpError) as e:
        svc.handle("POST", f"packs/{s['pack_id']}/review", [], "c")
    assert e.value.status == 409
    for fmt in ("xlsx", "docx", "pdf", "ics", "json"):
        data, ctype, name = svc.handle("GET", f"packs/{p['pack_id']}/export/{fmt}", None, "c")
        assert len(data) > 500 and name.endswith(fmt if fmt != "xlsx" else "xlsx")


def test_samples_are_read_only(svc):
    from service import HttpError

    sid = svc.samples[0]["pack_id"]
    with pytest.raises(HttpError) as e:
        svc.handle("POST", f"packs/{sid}/review", [], "c")
    assert e.value.status == 403
    assert svc.handle("GET", f"ai/packs/{sid}", None, "c")["pack_id"] == sid


def test_bad_input(svc):
    from service import HttpError

    for method, path, body, status in (("POST", "generate", {**PROFILE, "entity_class": "Banks"}, 422),
                                       ("GET", "packs/../../etc", None, 404), ("GET", "packs/NOPE", None, 404),
                                       ("GET", "fulltext/x", None, 404), ("POST", "ai/ask", {"question": "x" * 700}, 422)):
        with pytest.raises(HttpError) as e:
            svc.handle(method, path, body, "bad")
        assert e.value.status == status, path


def test_ask_pack_and_general(svc):
    p = svc.handle("POST", "generate", PROFILE, "c2")
    r = svc.handle("POST", f"ai/packs/{p['pack_id']}/ask", {"question": "What must we do to verify a customer's identity?"}, "c2")
    assert r["evidence"] and r["verifier"].endswith("+onnx-int8") and "Gemini" in r["label"]
    assert svc.handle("GET", f"ai/packs/{p['pack_id']}", None, "c2")["ask"][0]["question"] == r["question"]
    g = svc.handle("POST", "ai/ask", {"question": "When must fraud be reported to the RBI?", "entity_class": None}, "c2")
    assert g["scope"] == "all 11 entity types" and g["evidence"]
    assert any(s["verified"] for s in g["sentences"]) or g["abstained"]
    assert longest_run(g, svc) == 0
    one = svc.handle("POST", "ai/ask", {"question": "What are the rules on outsourcing?", "entity_class": "Non-Banking Financial Companies"}, "c2")
    assert one["scope"] == "Non-Banking Financial Companies"


def test_rate_limit(svc):
    from service import LIMITS, HttpError

    n, _ = LIMITS["generate"]
    import time

    svc.hits[("rl", "generate")].extend([time.monotonic()] * n)
    with pytest.raises(HttpError) as e:
        svc.handle("POST", "generate", PROFILE, "rl")
    assert e.value.status == 429


def test_daily_cap_is_site_wide(svc):
    import time

    from service import DAILY, HttpError

    from datetime import date

    name = f"counters/{date.today().isoformat()}.json.gz"
    saved = svc.blobs.get(name) or {}
    svc.blobs.put(name, {**saved, "ai": DAILY["ai"]})
    with pytest.raises(HttpError) as e:
        svc.handle("POST", "ai/ask", {"question": "What is KYC?"}, "someone-new")
    assert e.value.status == 429 and "today's limit" in e.value.detail
    svc.blobs.put(name, {**saved, "ai": 0})


def test_jobs_and_stored_gzip(svc):
    import gzip
    import time

    from service import GzJson, HttpError

    def wait(jid):
        for _ in range(600):
            st = svc.handle("GET", f"jobs/{jid}", None, "j")
            if st["status"] != "running":
                return st
            time.sleep(0.2)
        raise AssertionError("job did not finish")

    jid = svc.handle("POST", "jobs/start", {"method": "POST", "path": "generate", "body": PROFILE}, "j")["job"]
    assert wait(jid)["status"] == "done"
    res = svc.handle_http("GET", f"jobs/{jid}/result", None, "j")
    p = json.loads(gzip.decompress(res))
    assert isinstance(res, GzJson) and p["register"]
    raw = svc.handle_http("GET", f"packs/{p['pack_id']}", None, "j")
    assert json.loads(gzip.decompress(raw))["pack_id"] == p["pack_id"]
    sample = svc.handle_http("GET", f"packs/{svc.samples[0]['pack_id']}", None, "j")
    assert json.loads(gzip.decompress(sample))["pack_id"] == svc.samples[0]["pack_id"]
    jid = svc.handle("POST", "jobs/start", {"method": "GET", "path": f"packs/{p['pack_id']}/export/ics"}, "j")["job"]
    st = wait(jid)
    assert st["status"] == "done" and st["file"]
    svc.jobs.clear()  # a second worker knows nothing in memory: everything comes from shared storage
    data, ctype, name = svc.handle("GET", f"jobs/{jid}/file", None, "j")
    assert ctype == "text/calendar" and data.startswith(b"BEGIN:VCALENDAR")
    jid = svc.handle("POST", "jobs/start", {"path": "generate", "body": {**PROFILE, "entity_class": "Banks"}}, "j")["job"]
    st = wait(jid)
    assert st["status"] == "error" and st["error"]["status"] == 422
    for bad in ("health", "fulltext/x", "jobs/start", "../generate"):
        with pytest.raises(HttpError):
            svc.handle("POST", "jobs/start", {"path": bad}, "j")
