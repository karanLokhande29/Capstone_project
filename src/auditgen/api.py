"""Local FastAPI backend for the audit generator (127.0.0.1 only; no telemetry; no remote API calls).

    python3 scripts/auditgen.py serve            # http://127.0.0.1:8765

Uploaded policies are handled in memory and in ``data/auditgen_uploads/<session>/`` only; their text is never logged
(access logging is off) and never written to the call logs or the LLM cache.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from src.auditgen import ai_features as AI
from src.auditgen import exports as EX
from src.auditgen import genai as G
from src.auditgen import freshness as FR
from src.auditgen import gap_analysis as GAP
from src.auditgen import pack as PK
from src.auditgen import review as RV
from src.auditgen import summary_llm as LLM
from src.auditgen import validation as VAL
from src.auditgen.corpus import get_store, load_config
from src.auditgen.enforcement import risk_by_family
from src.auditgen.genai import load_genai_config
from src.auditgen.profile import ACTIVITIES, ACTIVITY_LABELS, Profile, ProfileError

LOOPBACK_ONLY = ("127.0.0.1", "::1", "localhost")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def assert_loopback(host: str) -> None:
    if host == "localhost":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError(f"the audit generator binds to 127.0.0.1 only, not {host!r}")


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="RBI audit generator (local)", version=cfg["tool_version"], docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5181", "http://localhost:5181", "http://127.0.0.1:5183",
                                                      "http://localhost:5183"], allow_methods=["*"], allow_headers=["*"])

    def store():
        return get_store(cfg)

    def load_pack(pack_id: str) -> dict[str, Any]:
        try:
            return PK.load(cfg, pack_id)
        except FileNotFoundError:
            raise HTTPException(404, "no such pack")

    def save_pack(p: dict[str, Any]) -> None:
        p["summary"] = PK.summarise(p)
        PK.save(p, PK.runs_dir(cfg) / p["pack_id"])

    @app.get("/api/auditgen/health")
    def health():
        return {"ok": True, "tool_version": cfg["tool_version"], "rules_version": cfg["version"], "disclaimer": cfg["disclaimer"],
                "mode": "local", "remote_api_calls": False}

    @app.get("/api/auditgen/vocab")
    def vocab():
        s = store()
        return {"classes": s.core_classes, "activities": [{"id": a, "label": ACTIVITY_LABELS[a]} for a in ACTIVITIES],
                "subject_families": sorted({d.get("subject_family") for d in s.docs.values() if d.get("subject_family")})}

    @app.post("/api/auditgen/generate")
    def generate(profile: dict = Body(...)):
        s = store()
        try:
            p = Profile.from_dict(profile).validate(s.core_classes)
        except ProfileError as exc:
            raise HTTPException(422, str(exc))
        pk = PK.generate(s, cfg, p)
        PK.save(pk, PK.runs_dir(cfg) / pk["pack_id"])
        return pk

    @app.get("/api/auditgen/packs")
    def packs():
        return PK.list_packs(cfg)

    @app.get("/api/auditgen/packs/{pack_id}")
    def get_pack(pack_id: str):
        return load_pack(pack_id)

    @app.post("/api/auditgen/packs/{pack_id}/review")
    def review(pack_id: str, updates: list[dict] = Body(...)):
        p = load_pack(pack_id)
        if p.get("signoff"):
            raise HTTPException(409, "this pack is signed off; review a new pack or re-import a workbook")
        try:
            n = RV.apply_updates(p, updates)
        except RV.ReviewError as exc:
            raise HTTPException(422, str(exc))
        save_pack(p)
        return {"updated": n, "progress": RV.progress(p)}

    @app.get("/api/auditgen/packs/{pack_id}/progress")
    def progress(pack_id: str):
        return RV.progress(load_pack(pack_id))

    @app.post("/api/auditgen/packs/{pack_id}/signoff")
    def signoff(pack_id: str, signer: str = Form(...), workbook: UploadFile | None = File(None)):
        p = load_pack(pack_id)
        if workbook is not None:
            data = workbook.file.read()
            import io
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as td:
                f = Path(td) / "review.xlsx"
                f.write_bytes(data)
                updates = RV.read_review_workbook(f)
            src_name, src_sha = workbook.filename or "review.xlsx", hashlib.sha256(data).hexdigest()
        else:
            updates, src_name, src_sha = [], "in-app review", hashlib.sha256(json.dumps(p["pack_id"]).encode()).hexdigest()
        try:
            new = RV.signed_off(p, updates, signer=signer, source_name=src_name, source_sha256=src_sha)
        except RV.ReviewError as exc:
            raise HTTPException(422, str(exc))
        save_pack(new)
        return {"pack_id": new["pack_id"], "signoff": new["signoff"]}

    @app.get("/api/auditgen/packs/{pack_id}/export/{fmt}")
    def export(pack_id: str, fmt: str):
        p = load_pack(pack_id)
        if fmt == "xlsx":
            return Response(EX.to_excel(p), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f'attachment; filename="{pack_id}.xlsx"'})
        if fmt == "docx":
            return Response(EX.to_docx(p), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            headers={"Content-Disposition": f'attachment; filename="{pack_id}.docx"'})
        if fmt == "pdf":
            return Response(EX.to_pdf(p), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{pack_id}.pdf"'})
        if fmt == "ics":
            return Response(EX.to_ics(p), media_type="text/calendar", headers={"Content-Disposition": f'attachment; filename="{pack_id}.ics"'})
        if fmt == "json":
            return JSONResponse(EX.audit_trail(p), headers={"Content-Disposition": f'attachment; filename="{pack_id}_audit_trail.json"'})
        raise HTTPException(404, "format must be xlsx, docx, pdf, ics or json")

    @app.post("/api/auditgen/packs/{pack_id}/gaps")
    def gaps(pack_id: str, files: list[UploadFile] = File(...), families: str = Form(""), explain: bool = Form(False)):
        p = load_pack(pack_id)
        if p.get("signoff"):
            raise HTTPException(409, "this pack is signed off")
        sid = GAP.new_session(cfg)
        docs = []
        for f in files:
            data = f.file.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                GAP.delete_session(cfg, sid)
                raise HTTPException(413, "file larger than 25 MB")
            try:
                meta = GAP.save_upload(cfg, sid, f.filename or "upload.txt", data)
            except GAP.GapError as exc:
                GAP.delete_session(cfg, sid)
                raise HTTPException(422, str(exc))
            docs.append((meta["name"], data))
        fams = [x for x in families.split("|") if x] or None
        s = store()
        try:
            res = GAP.analyse(s, cfg, p["register"], docs, families=fams, risk=risk_by_family(p["enforcement"]),
                              md_risk={r["md_id"]: r["penalty_count"] for r in p["enforcement"]})
        except GAP.GapError as exc:
            raise HTTPException(422, str(exc))
        res["session"] = sid
        texts = res.pop("_texts", {})
        if explain:
            st = LLM.available(cfg)
            if st["available"]:
                LLM.explain_rows(cfg, GAP.LocalModels.get(cfg), res["rows"], texts)
                res["explained_with"] = st["model"]
        del texts
        p["gaps"] = res
        save_pack(p)
        return {"pack_id": p["pack_id"], "session": sid, "counts": res["counts"], "files": res["files"]}

    @app.delete("/api/auditgen/uploads/{session}")
    def delete_upload(session: str, pack_id: str | None = None, clear_results: bool = False):
        try:
            gone = GAP.delete_session(cfg, session)
        except GAP.GapError as exc:
            raise HTTPException(422, str(exc))
        if pack_id and clear_results:
            p = load_pack(pack_id)
            if (p.get("gaps") or {}).get("session") == session:
                p["gaps"] = None
                save_pack(p)
        return {"deleted": gone}

    @app.get("/api/auditgen/fulltext/{pid}")
    def fulltext(pid: str):
        s = store()
        row = s.paragraphs.get(pid)
        if row is None:
            raise HTTPException(404, "no such paragraph")
        return {"paragraph_id": pid, "text": row.get("text") or "", "source_url": s.url(pid.split("::")[0]),
                "label": "internal use; source: RBI", "disclaimer": cfg["disclaimer"]}

    @app.get("/api/auditgen/freshness")
    def freshness():
        return FR.status(store(), cfg)

    @app.post("/api/auditgen/refresh/dry-run")
    def refresh_dry_run():
        try:
            return FR.dry_run(store(), cfg)
        except FR.RefreshError as exc:
            raise HTTPException(502, str(exc))

    @app.get("/api/auditgen/validation")
    def validation():
        return VAL.box(store())

    @app.get("/api/auditgen/llm")
    def llm():
        return LLM.available(cfg)

    # -- generative AI (local LLM only; src/auditgen/genai.py) ---------------------------------------------------------

    gcfg = load_genai_config()

    def ai_run(pack_id: str, feature: str, key: str | None, fn):
        p = load_pack(pack_id)
        try:
            res = fn(p, make_llm(gcfg), GAP.LocalModels.get(cfg))
        except AI.FeatureError as exc:
            raise HTTPException(422, str(exc))
        except (G.GenAIError, GAP.GapError) as exc:
            raise HTTPException(503, str(exc))
        return G.record(cfg, gcfg, p["pack_id"], feature, key, res)

    @app.get("/api/auditgen/ai/status")
    def ai_status():
        try:
            st = make_llm(gcfg).status()
        except G.GenAIError as exc:
            st = {"available": False, "model": None, "pulled": [], "reason": str(exc)}
        return {**st, "genai_version": gcfg["version"], "host": gcfg["llm"]["host"], "remote_api_calls": False,
                "verifier": f"{cfg['gap_analysis']['nli_model']}@{cfg['gap_analysis']['nli_revision'][:12]}",
                "embedding": f"{cfg['gap_analysis']['embedding_model']}@{cfg['gap_analysis']['embedding_revision'][:12]}",
                "label": G.LABEL, "privacy": "Local model on 127.0.0.1 only. Inputs are RBI text and this pack's rows; "
                "no uploaded company document is sent to the model by these features. The activity log keeps hashes, never text."}

    @app.get("/api/auditgen/ai/packs/{pack_id}")
    def ai_outputs(pack_id: str):
        load_pack(pack_id)
        return G.load_ai(cfg, pack_id)

    @app.get("/api/auditgen/ai/activity")
    def ai_activity():
        return G.activity(gcfg)

    @app.post("/api/auditgen/ai/packs/{pack_id}/ask")
    def ai_ask(pack_id: str, body: dict = Body(...)):
        return ai_run(pack_id, "ask", None, lambda p, llm, m: AI.ask(store(), cfg, gcfg, p, str(body.get("question") or ""), llm=llm,
                                                                     models=m, history=body.get("history") or [], model=body.get("model")))

    @app.post("/api/auditgen/ai/packs/{pack_id}/explain")
    def ai_explain(pack_id: str, body: dict = Body(...)):
        rid = str(body.get("row_id") or "")
        return ai_run(pack_id, "explain", rid, lambda p, llm, m: AI.explain_obligation(store(), cfg, gcfg, p, rid, llm=llm, models=m,
                                                                                       model=body.get("model")))

    @app.post("/api/auditgen/ai/packs/{pack_id}/change")
    def ai_change(pack_id: str, body: dict = Body(...)):
        rid = str(body.get("row_id") or "")
        return ai_run(pack_id, "change", rid, lambda p, llm, m: AI.explain_change(store(), cfg, gcfg, p, rid, llm=llm, models=m,
                                                                                  model=body.get("model")))

    @app.post("/api/auditgen/ai/packs/{pack_id}/memo")
    def ai_memo(pack_id: str, body: dict = Body(default={})):
        return ai_run(pack_id, "memo", None, lambda p, llm, m: AI.memo(store(), cfg, gcfg, p, llm=llm, models=m, model=body.get("model")))

    @app.get("/api/auditgen/ai/packs/{pack_id}/memo.docx")
    def ai_memo_docx(pack_id: str):
        load_pack(pack_id)
        res = G.load_ai(cfg, pack_id).get("memo")
        if not res:
            raise HTTPException(404, "no memo drafted for this pack yet")
        return Response(AI.memo_docx(res), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="{pack_id}_ai_memo.docx"'})

    @app.post("/api/auditgen/ai/packs/{pack_id}/plan")
    def ai_plan(pack_id: str, body: dict = Body(default={})):
        return ai_run(pack_id, "plan", None, lambda p, llm, m: AI.action_plan(store(), cfg, gcfg, p, llm=llm, models=m, model=body.get("model")))

    @app.post("/api/auditgen/ai/packs/{pack_id}/draft")
    def ai_draft(pack_id: str, body: dict = Body(...)):
        rid, sec = str(body.get("row_id") or ""), str(body.get("section") or "register")
        if sec not in ("register", "gaps"):
            raise HTTPException(422, "section must be register or gaps")
        return ai_run(pack_id, "draft", rid, lambda p, llm, m: AI.draft_clause(store(), cfg, gcfg, p, rid, llm=llm, models=m, section=sec,
                                                                               company=str(body.get("company") or "the Company"),
                                                                               model=body.get("model")))

    @app.post("/api/auditgen/ai/packs/{pack_id}/calendar")
    def ai_calendar(pack_id: str, body: dict = Body(default={})):
        ids = [str(x) for x in (body.get("entry_ids") or [])] or None
        return ai_run(pack_id, "calendar", None, lambda p, llm, m: AI.calendar_check(store(), cfg, gcfg, p, ids, llm=llm, model=body.get("model")))

    @app.post("/api/auditgen/ai/packs/{pack_id}/diff")
    def ai_diff(pack_id: str, body: dict = Body(...)):
        rid = str(body.get("row_id") or "")
        return ai_run(pack_id, "diff", rid, lambda p, llm, m: AI.diff_second_opinion(store(), cfg, gcfg, p, rid, llm=llm, model=body.get("model")))

    @app.post("/api/auditgen/ai/packs/{pack_id}/suggest")
    def ai_suggest(pack_id: str, body: dict = Body(...)):
        rid, sec = str(body.get("row_id") or ""), str(body.get("section") or "register")
        if sec not in PK.SECTIONS:
            raise HTTPException(422, f"section must be one of {PK.SECTIONS}")
        return ai_run(pack_id, "suggest", f"{sec}:{rid}", lambda p, llm, m: AI.review_suggestion(store(), cfg, gcfg, p, sec, rid, llm=llm,
                                                                                                models=m, model=body.get("model")))

    return app


def make_llm(gcfg) -> G.LocalLLM:
    """The local LLM client (a seam for tests)."""
    return G.LocalLLM(gcfg)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    assert_loopback(host)
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, access_log=False, log_level="warning")
