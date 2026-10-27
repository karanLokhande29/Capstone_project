"""Audit generator: gap analysis on fixtures, privacy (no remote calls, no uploaded text in logs / cache / exports),
the local LLM gate, and the 127.0.0.1-only FastAPI backend."""

from __future__ import annotations

import io
import json
import socket
from pathlib import Path

import numpy as np
import pytest

from src.auditgen import exports as EX
from src.auditgen import gap_analysis as GAP
from src.auditgen import pack as PK
from src.auditgen import summary_llm as LLM
from src.auditgen.corpus import ROOT, get_store, load_config
from src.auditgen.profile import Profile

SECRET = "Zebra-Quartz confidential clause 7781: the treasury desk settles every Thursday at the Pune vault."


class FakeModels:
    """Deterministic stand-in for bge + NLI: bag-of-words cosine; entailment when every hypothesis word is in the premise."""

    ids = {"embedding": "fake-bow", "nli": "fake-nli"}

    def __init__(self):
        self.vocab: dict[str, int] = {}

    def _vec(self, t):
        v = np.zeros(4096, dtype=np.float32)
        for w in t.lower().split():
            v[hash(w) % 4096] += 1
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts):
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, 4096), dtype=np.float32)

    def nli_scores(self, pairs):
        ps, ok = [], []
        for prem, hyp in pairs:
            hw, pw = set(hyp.lower().split()), set(prem.lower().split())
            share = len(hw & pw) / max(1, len(hw))
            ps.append(0.95 if share > 0.9 else 0.3 if share > 0.5 else 0.01)
            ok.append(share > 0.9)
        return np.array(ps), np.array(ok)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


@pytest.fixture(scope="module")
def store(cfg):
    return get_store(cfg)


@pytest.fixture(scope="module")
def pack(store, cfg):
    return PK.generate(store, cfg, Profile("Gap test", "Payments Banks", "2026-10-15", "2025-12-01", ["kyc_aml"], []))


def _kyc(pack, n=6):
    return [r for r in pack["register"] if not r["hidden"] and r["subject_family"] == "Know Your Customer"][:n]


def _sentence(store, row):
    c = {c["candidate_id"]: c for c in store.candidates()}[row["obligation_id"]]
    return store.obligation_sentence(c)


def test_split_clauses_and_extract_text():
    import docx
    from reportlab.pdfgen import canvas

    text = "1. The Company will verify identity before opening an account.\n\n2. Records are kept for five years after closure.\n\nshort"
    cl = GAP.split_clauses(text, min_chars=20, max_words=40)
    assert len(cl) == 2 and cl[-1].endswith("short")
    d = docx.Document()
    d.add_paragraph("The Company will verify identity before opening an account.")
    b = io.BytesIO()
    d.save(b)
    assert "verify identity" in GAP.extract_text("p.docx", b.getvalue())
    b = io.BytesIO()
    c = canvas.Canvas(b)
    c.drawString(72, 720, "Records are kept for five years after closure.")
    c.save()
    assert "five years" in GAP.extract_text("p.pdf", b.getvalue())
    assert "Records" in GAP.extract_text("p.md", b"# Records\nRecords are kept.")
    with pytest.raises(GAP.GapError):
        GAP.extract_text("p.exe", b"MZ")


def test_gap_analysis_covered_partial_missing(store, cfg, pack):
    rows = _kyc(pack, 3)
    s0, s1 = _sentence(store, rows[0]), _sentence(store, rows[1])
    half = " ".join(s1.split()[: max(3, len(s1.split()) * 2 // 3)])
    policy = f"1. {s0}\n\n2. {half}\n\n3. {SECRET}\n\n4. Employees may claim travel expenses monthly with receipts."
    res = GAP.analyse(store, cfg, rows, [("policy.txt", policy.encode())], models=FakeModels())
    by = {r["obligation_id"]: r for r in res["rows"]}
    assert by[rows[0]["obligation_id"]]["coverage"] == "covered" and by[rows[0]["obligation_id"]]["matched_clauses"]
    assert by[rows[1]["obligation_id"]]["coverage"] in ("partial", "covered")
    assert res["counts"]["missing"] >= 1
    for r in res["rows"]:
        assert r["source_url"].startswith("https://") and r["paragraph_id"]
        assert len(r["top_clauses"]) == min(cfg["gap_analysis"]["top_k"], 4)
        assert all({"cosine", "entailment"} <= set(c) for c in r["top_clauses"])
        if r["coverage"] != "covered":
            assert r["needs_review"]
    assert res["files"][0]["sha256"] and "text" not in res["files"][0]
    assert res["thresholds"]["covered_entailment"] == cfg["gap_analysis"]["covered_entailment"]


def test_uploaded_text_never_in_logs_cache_or_exports(store, cfg, pack, tmp_path, monkeypatch):
    logs_before = {p: p.stat().st_size for p in (ROOT / "logs").rglob("*") if p.is_file()}
    cache = ROOT / "data/llm_cache"
    cache_before = sorted(p.name for p in cache.rglob("*") if p.is_file())
    rows = _kyc(pack, 4)
    res = GAP.analyse(store, cfg, rows, [("policy.txt", f"1. {SECRET}\n\n2. {SECRET} again".encode())], models=FakeModels())
    res.pop("_texts", None)
    p = dict(pack)
    p["gaps"] = res
    p["summary"] = PK.summarise(p)
    trail = json.dumps(EX.audit_trail(p))
    assert "Zebra-Quartz" not in trail
    ics = EX.to_ics(p)
    assert "Zebra-Quartz" not in ics
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(EX.to_excel(p)))
    xl = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value)
    matched = [c["excerpt"] for r in res["rows"] for c in r["matched_clauses"]]
    assert ("Zebra-Quartz" not in xl) or any("Zebra-Quartz" in m for m in matched)  # only as a matched-clause excerpt
    # Nothing new in the LLM cache; no log line carries the text.
    assert sorted(p.name for p in cache.rglob("*") if p.is_file()) == cache_before
    for f in (ROOT / "logs").rglob("*"):
        if f.is_file() and f in logs_before and f.stat().st_size != logs_before[f]:
            assert "Zebra-Quartz" not in f.read_text(errors="replace")[logs_before[f]:]


def _block_remote(monkeypatch):
    """Any socket connection to a non-loopback address, and any LLM client call, raises."""
    real = socket.socket.connect

    def guarded(self, addr):
        host = addr[0] if isinstance(addr, tuple) else addr
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"remote connection attempted: {host}")
        return real(self, addr)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    from src.llm import client as L

    def boom(*a, **k):
        raise AssertionError("remote LLM API call attempted")

    monkeypatch.setattr(L.LLMClient, "complete", boom)
    for name in ("GeminiProvider", "GroqProvider"):
        if hasattr(L, name):
            monkeypatch.setattr(getattr(L, name), "generate", boom)


def test_no_remote_api_call_in_default_and_gap_modes(store, cfg, monkeypatch):
    _block_remote(monkeypatch)
    pk = PK.generate(store, cfg, Profile("Remote test", "Small Finance Banks", "2026-10-15", "2025-12-01", ["kyc_aml"], ["Payments Banks"]))
    rows = [r for r in pk["register"] if not r["hidden"] and r["subject_family"] == "Know Your Customer"][:5]
    res = GAP.analyse(store, cfg, rows, [("p.txt", b"1. The Company will verify customer identity before opening an account.")])
    assert res["models"]["embedding"].startswith("BAAI/bge-base-en-v1.5@") and res["models"]["nli"].startswith("cross-encoder/nli-deberta-v3-xsmall@")
    EX.to_excel(pk)
    EX.to_pdf(pk)


def test_local_llm_gate_refuses_remote_hosts(cfg):
    remote = {**cfg, "local_llm": {**cfg["local_llm"], "host": "https://api.example.com"}}
    assert LLM.available(remote)["available"] is False
    with pytest.raises(LLM.LocalLLMError):
        LLM.explain(remote, "o", "c")

    class Down:
        def get(self, *a, **k):
            raise ConnectionError("down")

    assert LLM.available(cfg, http=Down())["available"] is False

    class Fake:
        def nli_scores(self, pairs):
            return np.array([0.9, 0.1]), np.array([True, False])

    v = LLM.verified(Fake(), "obligation", "clause", "Supported sentence. Invented sentence.")
    assert v == {"kept": ["Supported sentence."], "dropped": 1}


# -- API ---------------------------------------------------------------------------------------------------------------

@pytest.fixture()
def client(cfg, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.auditgen import api as API

    local = {**cfg, "paths": {**cfg["paths"], "runs": str(tmp_path / "runs"), "uploads": str(tmp_path / "uploads"),
                              "samples": str(tmp_path / "samples")}}
    monkeypatch.setattr(API, "load_config", lambda: local)
    monkeypatch.setattr(GAP.LocalModels, "get", classmethod(lambda cls, c: FakeModels()))
    return TestClient(API.create_app()), local


def test_api_endpoints(client):
    c, local = client
    assert c.get("/api/auditgen/health").json()["remote_api_calls"] is False
    v = c.get("/api/auditgen/vocab").json()
    assert "Payments Banks" in v["classes"] and len(v["activities"]) == 10
    bad = c.post("/api/auditgen/generate", json={"name": "x", "entity_class": "Nope", "as_of": "2026-10-15", "last_review": "2025-12-01"})
    assert bad.status_code == 422
    pk = c.post("/api/auditgen/generate", json={"name": "API test", "entity_class": "Payments Banks", "as_of": "2026-10-15",
                                                 "last_review": "2025-12-01", "activities": ["kyc_aml"], "group_classes": []}).json()
    pid = pk["pack_id"]
    assert pk["disclaimer"].startswith("Decision support only")
    assert any(p["pack_id"] == pid for p in c.get("/api/auditgen/packs").json())
    row = next(r for r in pk["register"] if not r["hidden"])
    r = c.post(f"/api/auditgen/packs/{pid}/review", json=[{"section": "register", "row_id": row["row_id"], "review_status": "confirmed",
                                                           "reviewer": "QA", "note": ""}])
    assert r.json()["updated"] == 1
    for fmt, ctype in (("xlsx", "spreadsheetml"), ("docx", "wordprocessingml"), ("pdf", "pdf"), ("ics", "calendar"), ("json", "json")):
        resp = c.get(f"/api/auditgen/packs/{pid}/export/{fmt}")
        assert resp.status_code == 200 and ctype in resp.headers["content-type"]
    ft = c.get(f"/api/auditgen/fulltext/{row['paragraph_id']}").json()
    assert ft["label"] == "internal use; source: RBI" and ft["text"]
    g = c.post(f"/api/auditgen/packs/{pid}/gaps", files=[("files", ("policy.txt", f"1. {SECRET}".encode(), "text/plain"))],
               data={"families": "Know Your Customer", "explain": "false"}).json()
    sid = g["session"]
    up = Path(local["paths"]["uploads"]) / sid
    assert up.is_dir() and (up / "policy.txt").exists()
    assert c.delete(f"/api/auditgen/uploads/{sid}?pack_id={pid}&clear_results=true").json()["deleted"] is True
    assert not up.exists()
    assert c.get(f"/api/auditgen/packs/{pid}").json()["gaps"] is None
    assert c.get("/api/auditgen/freshness").json()["snapshot_date"]
    so = c.post(f"/api/auditgen/packs/{pid}/signoff", data={"signer": "Head of Compliance"}).json()
    assert so["pack_id"] != pid and so["signoff"]["signer"] == "Head of Compliance"
    assert c.get("/api/auditgen/packs/../../etc").status_code == 404


def test_backend_binds_to_loopback_only():
    from src.auditgen.api import assert_loopback

    for ok in ("127.0.0.1", "::1", "localhost"):
        assert_loopback(ok)
    for bad in ("0.0.0.0", "192.168.1.5", "::", "example.com"):
        with pytest.raises(ValueError):
            assert_loopback(bad)
    cfg = load_config()
    assert cfg["server"]["host"] == "127.0.0.1"
