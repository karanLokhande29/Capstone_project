"""Hosted audit generator service (public site): generate, review, sign off, export and the AI assistant.

Plain Python, no Azure imports: function_app.py maps HTTP routes onto ``Service.handle()``, and tests call it directly.
The routes mirror the local backend (src/auditgen/api.py) so the UI uses one client; the hosted service leaves out
policy uploads (gap analysis), corpus refresh, the full-text view and the activity log, which stay in the installed
version. Differences from the local backend are in src/auditgen/hosted.py (Gemini writer, ONNX models, 12-word cap).

Storage: generated packs and their AI outputs as gzip JSON in ``store`` (Azure Blob in production, a folder in tests),
deleted by a 7-day lifecycle rule. The sample packs (one per entity class) ship read-only with the package.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

from src.auditgen import ai_features as AI
from src.auditgen import genai as G
from src.auditgen import pack as PK
from src.auditgen import review as RV
from src.auditgen.corpus import CorpusStore, load_config
from src.auditgen.exports import write_all
from src.auditgen.hosted import GeminiLLM, OnnxModels, cap
from src.auditgen.profile import ACTIVITIES, Profile, ProfileError

HERE = Path(__file__).resolve().parent
PACK_ID = re.compile(r"^[a-z0-9_\-]{3,120}$")
LABEL = ("AI draft (Gemini), every sentence checked against the cited RBI text by the NLI verifier; unsupported "
         "sentences are held back. Needs human review.")
ACTIVITY_LABELS = {"deposits": "Deposits", "lending": "Lending", "digital_lending": "Digital lending", "forex": "Forex",
                   "payments": "Payments", "priority_sector": "Priority-sector lending", "co_lending": "Co-lending",
                   "outsourcing": "Outsourcing", "kyc_aml": "KYC / AML", "it_cyber": "IT / cyber"}
EXPORTS = {"xlsx": ("audit_pack.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
           "docx": ("audit_report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
           "pdf": ("audit_report.pdf", "application/pdf"), "ics": ("compliance_calendar.ics", "text/calendar"),
           "json": ("audit_trail.json", "application/json")}
LIMITS = {"generate": (20, 3600), "ai": (60, 3600), "write": (300, 3600)}  # (requests, window seconds) per client
# Site-wide caps per day, so usage stays inside the free Azure allowance and the free Gemini quota (Karan: nothing may be
# charged). The service runs on one instance (deploy.sh), so these in-memory counters cover every visitor.
DAILY = {"generate": int(os.environ.get("AUDIT_GENERATE_DAILY_CAP", "40")), "ai": int(os.environ.get("AUDIT_AI_DAILY_CAP", "30"))}


# Slow routes run as background jobs (POST jobs/start, then GET jobs/<id> until done): Azure's front end sometimes routes
# a request to a dead backend and answers 503 after 60 s, so the client keeps every request short and retries it.
JOB_PATH = re.compile(r"^(generate|packs/[a-z0-9_\-]{3,120}/(review|signoff|export/(xlsx|docx|pdf|ics|json))"
                      r"|ai/ask|ai/packs/[a-z0-9_\-]{3,120}/[a-z]+)$")


class GzJson(bytes):
    """A JSON body already gzip-compressed (sent with Content-Encoding: gzip)."""


def gz_json(obj: Any) -> GzJson:
    return GzJson(gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode(), 6))


class HttpError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


class DirStore:
    """Gzip JSON blobs in a folder (tests and local runs)."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def get(self, name: str) -> dict | None:
        raw = self.get_raw(name)
        return json.loads(gzip.decompress(raw)) if raw is not None else None

    def get_raw(self, name: str) -> bytes | None:
        p = self.root / name
        return p.read_bytes() if p.exists() else None

    def put(self, name: str, obj: Mapping[str, Any]) -> None:
        self.put_raw(name, gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode(), 6))

    def put_raw(self, name: str, data: bytes) -> None:
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_bytes(data)


class BlobStore:
    def __init__(self, connection: str, container: str = "auditgen-packs"):
        from azure.storage.blob import BlobServiceClient

        self.c = BlobServiceClient.from_connection_string(connection).get_container_client(container)
        try:
            self.c.create_container()
        except Exception:  # noqa: BLE001 - already exists
            pass

    def get(self, name: str) -> dict | None:
        raw = self.get_raw(name)
        return json.loads(gzip.decompress(raw)) if raw is not None else None

    def get_raw(self, name: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.c.download_blob(name).readall()
        except ResourceNotFoundError:
            return None

    def put(self, name: str, obj: Mapping[str, Any]) -> None:
        self.put_raw(name, gzip.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode(), 6))

    def put_raw(self, name: str, data: bytes) -> None:
        self.c.upload_blob(name, data, overwrite=True)


class Service:
    def __init__(self, store, *, models_dir: Path = HERE / "models", samples_dir: Path = HERE / "samples",
                 llm: Any = None, models: Any = None, work_dir: Path = Path("/tmp/auditgen_hosted")):
        self.cfg = load_config()
        self.gcfg = G.load_genai_config()
        self.corpus = CorpusStore(self.cfg)
        self.blobs = store
        self.samples_dir = samples_dir
        self.models_dir = models_dir
        self._llm, self._models = llm, models
        # The Retriever writes its vector cache next to the RBI-only vectors shipped with the package; the package
        # folder is read-only on Azure, so the cache lives in a writable copy.
        work_dir.mkdir(parents=True, exist_ok=True)
        for f in (models_dir / "vectors").glob("*.npz") if (models_dir / "vectors").exists() else []:
            if not (work_dir / f.name).exists():
                shutil.copy(f, work_dir / f.name)
        self.gcfg["storage"] = {**self.gcfg["storage"], "ai_cache": str(work_dir)}
        from src.release.rbi_text import CorpusIndex

        self.index = CorpusIndex.from_processed(self.corpus.root / self.cfg["paths"]["research_corpus"])
        self.samples = [{**it, "kind": "sample"} for it in json.loads((samples_dir / "index.json").read_text())["packs"]] if (samples_dir / "index.json").exists() else []
        self.cache: OrderedDict[str, tuple[dict, bool]] = OrderedDict()
        self.general: dict[str, dict] = {}
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self.jobs: dict[str, float] = {}  # running jobs started here, by client (concurrency limit)
        self.lock = threading.Lock()

    # -- helpers ---------------------------------------------------------------------------------------------------------

    def llm(self):
        if self._llm is None:
            self._llm = GeminiLLM(self.gcfg)
        return self._llm

    def models(self):
        if self._models is None:
            self._models = OnnxModels.get(self.models_dir)
        return self._models

    def limit(self, client: str, kind: str) -> None:
        n, window = LIMITS[kind]
        now = time.monotonic()
        q, day = self.hits[(client, kind)], self.hits[("*", kind)]
        for d, w in ((q, window), (day, 86400)):
            while d and now - d[0] > w:
                d.popleft()
        if len(q) >= n:
            raise HttpError(429, f"Rate limit: at most {n} {kind} requests per hour from one address. Try again later.")
        if kind in DAILY:
            # Site-wide and shared by every worker of the app (Azure may run more than one), so the cap really holds.
            name = f"counters/{date.today().isoformat()}.json.gz"
            with self.lock:
                c = self.blobs.get(name) or {}
                if c.get(kind, 0) >= DAILY[kind]:
                    raise HttpError(429, f"This free demo has reached today's limit of {DAILY[kind]} {'AI answers' if kind == 'ai' else 'generated packs'}. "
                                         "Please try again tomorrow; the sample packs and their recorded AI outputs remain available.")
                c[kind] = c.get(kind, 0) + 1
                self.blobs.put(name, c)
        q.append(now)

    def cap(self, obj):
        return cap(obj, self.index)

    def sample(self, pack_id: str) -> dict | None:
        it = next((s for s in self.samples if s["pack_id"] == pack_id), None)
        if not it:
            return None
        return json.loads(gzip.decompress((self.samples_dir / it["file"]).read_bytes()))

    def load(self, pack_id: str) -> tuple[dict, bool]:
        """(pack, is_sample)."""
        if not PACK_ID.match(pack_id or ""):
            raise HttpError(404, "no such pack")
        with self.lock:
            if pack_id in self.cache:
                self.cache.move_to_end(pack_id)
                return self.cache[pack_id]
        s = self.sample(pack_id)
        if s is not None:
            self.remember(s, True)
            return s, True
        p = self.blobs.get(f"packs/{pack_id}.json.gz")
        if p is None:
            raise HttpError(404, "no such pack (generated packs are kept for 7 days)")
        self.remember(p)
        return p, False

    def remember(self, p: dict, is_sample: bool = False) -> None:
        with self.lock:
            self.cache[p["pack_id"]] = (p, is_sample)
            self.cache.move_to_end(p["pack_id"])
            while len(self.cache) > 4:
                self.cache.popitem(last=False)

    def save(self, p: dict) -> None:
        p["summary"] = PK.summarise(p)
        self.blobs.put(f"packs/{p['pack_id']}.json.gz", p)
        self.remember(p)

    def ai_store(self, pack_id: str, is_sample: bool) -> dict:
        if is_sample:
            f = self.samples_dir / f"ai_{pack_id}.json"
            return json.loads(f.read_text()) if f.exists() else {"pack_id": pack_id, "kind": "ai_outputs", "label": LABEL}
        return self.blobs.get(f"ai/{pack_id}.json.gz") or {"pack_id": pack_id, "kind": "ai_outputs", "label": LABEL}

    # -- routes ----------------------------------------------------------------------------------------------------------

    def handle(self, method: str, path: str, body: Any, client: str) -> Any:
        """Returns a JSON-able object, or (bytes, content_type, filename) for a file."""
        parts = [p for p in path.strip("/").split("/") if p]
        if parts[:2] == ["api", "auditgen"]:
            parts = parts[2:]
        route = "/".join(parts)
        if method == "GET" and route == "health":
            return {"ok": True, "tool_version": self.cfg["tool_version"], "rules_version": self.cfg["version"],
                    "disclaimer": self.cfg["disclaimer"], "mode": "hosted", "remote_api_calls": True,
                    "quote_words": 12, "keeps_packs_days": 7}
        if method == "GET" and route == "vocab":
            return {"classes": self.corpus.core_classes, "activities": [{"id": a, "label": ACTIVITY_LABELS[a]} for a in ACTIVITIES],
                    "subject_families": sorted({d.get("subject_family") for d in self.corpus.docs.values() if d.get("subject_family")})}
        if method == "GET" and route == "packs":
            return self.samples
        if method == "POST" and route == "generate":
            self.limit(client, "generate")
            return self.generate(body)
        if parts[:1] == ["packs"] and len(parts) >= 2:
            pid = parts[1]
            if method == "GET" and len(parts) == 2:
                return self.load(pid)[0]
            if method == "POST" and parts[2:] == ["review"]:
                self.limit(client, "write")
                return self.review(pid, body)
            if method == "POST" and parts[2:] == ["signoff"]:
                self.limit(client, "write")
                return self.signoff(pid, body)
            if method == "GET" and len(parts) == 4 and parts[2] == "export":
                return self.export(pid, parts[3])
        if parts[:1] == ["ai"]:
            return self.ai(method, parts[1:], body, client)
        if parts[:1] == ["jobs"]:
            return self.job_route(method, parts[1:], body, client)
        raise HttpError(404, "not found")

    def handle_http(self, method: str, path: str, body: Any, client: str) -> Any:
        """``handle()`` for the HTTP wrapper: packs and job results go out as stored gzip bytes (no re-serialising)."""
        parts = [p for p in path.strip("/").split("/") if p]
        if method == "GET" and len(parts) == 2 and parts[0] == "packs" and PACK_ID.match(parts[1]):
            it = next((s for s in self.samples if s["pack_id"] == parts[1]), None)
            raw = (self.samples_dir / it["file"]).read_bytes() if it else self.blobs.get_raw(f"packs/{parts[1]}.json.gz")
            if raw is None:
                raise HttpError(404, "no such pack (generated packs are kept for 7 days)")
            return GzJson(raw)
        if method == "GET" and len(parts) == 3 and parts[0] == "jobs" and parts[2] == "result":
            if self.job(parts[1])["status"] != "done":
                raise HttpError(409, "job not finished")
            raw = self.blobs.get_raw(f"jobs/{parts[1]}.result.gz")
            if raw is None:
                raise HttpError(404, "job result not found")
            return GzJson(raw)
        return self.handle(method, path, body, client)

    # -- background jobs -------------------------------------------------------------------------------------------------

    def job(self, jid: str) -> dict:
        """A job's record, from shared storage: Azure may serve the start and the polls from different workers."""
        rec = self.blobs.get(f"jobs/{jid}.json.gz") if re.fullmatch(r"[0-9a-f]{32}", jid or "") else None
        if rec is None:
            raise HttpError(404, "no such job (jobs are kept for 7 days)")
        if rec["status"] == "running" and time.time() - rec["started"] > 600:
            rec = {**rec, "status": "error", "error": {"status": 503, "detail": "The service restarted during this request. Please try again."}}
        return rec

    def job_route(self, method: str, parts: list[str], body: Any, client: str) -> Any:
        if method == "POST" and parts == ["start"]:
            b = body if isinstance(body, dict) else {}
            m, path = str(b.get("method") or "POST").upper(), str(b.get("path") or "").strip("/")
            if m not in ("GET", "POST") or not JOB_PATH.match(path):
                raise HttpError(404, "this route cannot run as a job")
            now = time.time()
            with self.lock:
                for k in [k for k, t in self.jobs.items() if now - t > 600]:
                    del self.jobs[k]
                if sum(1 for k in self.jobs if k.startswith(client + "|")) >= 3:
                    raise HttpError(429, "Too many requests running at once from one address. Wait for one to finish.")
                jid = uuid.uuid4().hex
                self.jobs[f"{client}|{jid}"] = now
            self.blobs.put(f"jobs/{jid}.json.gz", {"status": "running", "started": now})
            threading.Thread(target=self.run_job, args=(jid, m, path, b.get("body"), client), daemon=True).start()
            return {"job": jid}
        if method == "GET" and len(parts) == 1:
            j = self.job(parts[0])
            return {"status": j["status"], "error": j.get("error"), "file": bool(j.get("file")),
                    "seconds": round((j.get("ended") or time.time()) - j["started"], 1)}
        if method == "GET" and len(parts) == 2 and parts[1] == "file":
            j = self.job(parts[0])
            data = self.blobs.get_raw(f"jobs/{parts[0]}.file") if j.get("file") else None
            if data is None:
                raise HttpError(404, "this job has no file")
            return data, j["file"]["ctype"], j["file"]["name"]
        raise HttpError(404, "not found")

    def run_job(self, jid: str, method: str, path: str, body: Any, client: str) -> None:
        rec = self.blobs.get(f"jobs/{jid}.json.gz") or {"started": time.time()}
        try:
            out = self.handle(method, path, body, client)
            if isinstance(out, tuple):
                self.blobs.put_raw(f"jobs/{jid}.file", out[0])
                rec["file"] = {"ctype": out[1], "name": out[2]}
                out = {"file": out[2]}
            self.blobs.put_raw(f"jobs/{jid}.result.gz", gz_json(out))
            rec["status"] = "done"
        except HttpError as e:
            rec.update(status="error", error={"status": e.status, "detail": e.detail})
        except Exception as e:  # noqa: BLE001 - reported to the caller, logged by the wrapper
            import logging

            logging.exception("job %s failed", path)
            rec.update(status="error", error={"status": 500, "detail": f"internal error ({type(e).__name__})"})
        rec["ended"] = time.time()
        self.blobs.put(f"jobs/{jid}.json.gz", rec)
        with self.lock:
            self.jobs.pop(f"{client}|{jid}", None)

    def generate(self, body: Any) -> dict:
        if not isinstance(body, dict):
            raise HttpError(422, "profile must be a JSON object")
        body = {**body, "name": " ".join(str(body.get("name") or "").split())[:80]}
        try:
            prof = Profile.from_dict(body).validate(self.corpus.core_classes)
        except (ProfileError, TypeError) as exc:
            raise HttpError(422, str(exc))
        p = self.cap(PK.generate(self.corpus, self.cfg, prof))
        p["hosted"] = True
        self.save(p)
        return p

    def review(self, pid: str, updates: Any) -> dict:
        p, is_sample = self.load(pid)
        if is_sample:
            raise HttpError(403, "Sample packs are read-only. Generate a pack for your entity to review it.")
        if p.get("signoff"):
            raise HttpError(409, "this pack is signed off; review a new pack")
        if not isinstance(updates, list) or len(updates) > 500:
            raise HttpError(422, "updates must be a list of at most 500 rows")
        p = copy.deepcopy(p)
        try:
            n = RV.apply_updates(p, [{**u, "reviewer": str(u.get("reviewer") or "")[:80], "note": str(u.get("note") or "")[:1000]}
                                     for u in updates if isinstance(u, dict)])
        except RV.ReviewError as exc:
            raise HttpError(422, str(exc))
        self.save(p)
        return {"updated": n, "progress": RV.progress(p)}

    def signoff(self, pid: str, body: Any) -> dict:
        p, is_sample = self.load(pid)
        if is_sample:
            raise HttpError(403, "Sample packs are read-only. Generate a pack for your entity to sign it off.")
        signer = str((body or {}).get("signer") or "")[:80]
        try:
            new = RV.signed_off(p, [], signer=signer, source_name="in-app review",
                                source_sha256=hashlib.sha256(p["pack_id"].encode()).hexdigest())
        except RV.ReviewError as exc:
            raise HttpError(422, str(exc))
        new["hosted"] = True
        self.save(new)
        return {"pack_id": new["pack_id"], "signoff": new["signoff"]}

    def export(self, pid: str, fmt: str):
        if fmt not in EXPORTS:
            raise HttpError(404, "unknown export format")
        p, _ = self.load(pid)
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            files = write_all(p, Path(td))
            data = Path(files[fmt]).read_bytes()
        name, ctype = EXPORTS[fmt]
        return data, ctype, f"{pid}_{name}"

    # -- AI --------------------------------------------------------------------------------------------------------------

    def ai(self, method: str, parts: list[str], body: Any, client: str) -> Any:
        body = body if isinstance(body, dict) else {}
        if method == "GET" and parts == ["status"]:
            st = self.llm().status()
            return {**st, "genai_version": self.gcfg["version"] + "+hosted", "host": "Gemini (Google) via the hosted service",
                    "remote_api_calls": True, "verifier": self.models_meta("nli"), "embedding": self.models_meta("bge"),
                    "label": LABEL, "privacy": "Hosted demo: your question and RBI text go to Gemini (Google). Do not type "
                    "confidential information. Policy uploads are only in the installed version, which runs inside your network."}
        if method == "POST" and parts == ["ask"]:
            self.limit(client, "ai")
            return self.ask_general(body)
        if parts[:1] != ["packs"] or len(parts) < 2:
            raise HttpError(404, "not found")
        pid, rest = parts[1], parts[2:]
        if method == "GET" and not rest:
            return self.ai_store(pid, self.load(pid)[1])
        if method == "GET" and rest == ["memo.docx"]:
            p, is_sample = self.load(pid)
            res = self.ai_store(pid, is_sample).get("memo")
            if not res:
                raise HttpError(404, "no memo drafted for this pack yet")
            return AI.memo_docx(res), EXPORTS["docx"][1], f"{pid}_ai_memo.docx"
        if method != "POST" or len(rest) != 1:
            raise HttpError(404, "not found")
        feature = rest[0]
        rid, sec = str(body.get("row_id") or ""), str(body.get("section") or "register")
        c, cfg, g = self.corpus, self.cfg, self.gcfg
        runs: dict[str, tuple[str | None, Callable]] = {
            "ask": (None, lambda p, llm, m: AI.ask(c, cfg, g, p, str(body.get("question") or ""), llm=llm, models=m,
                                                   history=(body.get("history") or [])[-3:])),
            "explain": (rid, lambda p, llm, m: AI.explain_obligation(c, cfg, g, p, rid, llm=llm, models=m)),
            "change": (rid, lambda p, llm, m: AI.explain_change(c, cfg, g, p, rid, llm=llm, models=m)),
            "memo": (None, lambda p, llm, m: AI.memo(c, cfg, g, p, llm=llm, models=m)),
            "plan": (None, lambda p, llm, m: AI.action_plan(c, cfg, g, p, llm=llm, models=m)),
            "draft": (rid, lambda p, llm, m: AI.draft_clause(c, cfg, g, p, rid, llm=llm, models=m, section=sec if sec in ("register", "gaps") else "register",
                                                             company=str(body.get("company") or "the Company")[:80])),
            "calendar": (None, lambda p, llm, m: AI.calendar_check(c, cfg, g, p, [str(x) for x in (body.get("entry_ids") or [])][:25] or None, llm=llm)),
            "diff": (rid, lambda p, llm, m: AI.diff_second_opinion(c, cfg, g, p, rid, llm=llm)),
            "suggest": (f"{sec}:{rid}", lambda p, llm, m: AI.review_suggestion(c, cfg, g, p, sec, rid, llm=llm, models=m)),
        }
        if feature not in runs:
            raise HttpError(404, "not found")
        self.limit(client, "ai")
        p, is_sample = self.load(pid)
        key, fn = runs[feature]
        res = self.run(lambda: fn(p, self.llm(), self.models()))
        if not is_sample:  # the sample packs keep their recorded outputs; a new run is returned but not stored
            ai = self.ai_store(pid, False)
            if key is None:
                if feature == "ask":
                    ai.setdefault("ask", []).insert(0, res)
                    del ai["ask"][50:]
                else:
                    ai[feature] = res
            else:
                ai.setdefault(feature, {})[key] = res
            ai["genai_version"] = self.gcfg["version"] + "+hosted"
            self.blobs.put(f"ai/{pid}.json.gz", ai)
        return res

    def run(self, fn: Callable[[], dict]) -> dict:
        try:
            res = fn()
        except AI.FeatureError as exc:
            raise HttpError(422, str(exc))
        except G.GenAIError as exc:
            raise HttpError(503, str(exc))
        res = self.cap(res)
        res["label"] = LABEL
        res["verifier"] = self.models_meta("nli")
        return res

    def models_meta(self, k: str) -> str:
        f = self.models_dir / k / "meta.json"
        return json.loads(f.read_text())["id"] if f.exists() else k

    def general_pack(self, entity_class: str | None) -> dict:
        """The register the general assistant searches: one entity class, or every RBI obligation in the corpus (all
        11 classes, each paragraph once, with the classes it applies to)."""
        key = entity_class or "all"
        with self.lock:
            if key in self.general:
                return self.general[key]
        classes = [entity_class] if entity_class else list(self.corpus.core_classes)
        today = date.today()
        rows: dict[str, dict] = {}
        for cls in classes:
            prof = Profile(name="RBI assistant", entity_class=cls, as_of=today.isoformat(),
                           last_review=(today - timedelta(days=365)).isoformat(), activities=list(ACTIVITIES), group_classes=[])
            for r in PK.generate(self.corpus, self.cfg, prof)["register"]:
                if r["hidden"] or not r.get("paragraph_id"):
                    continue
                # The same paragraph recurs word for word in each class's own Direction: keep it once (the first
                # Direction's citation), so the evidence slots go to different rules.
                key = " ".join(AI.para_text(self.corpus, r["paragraph_id"]).lower().split()) or r["paragraph_id"]
                cur = rows.get(key)
                if cur is None:
                    rows[key] = cur = {k: r.get(k) for k in ("row_id", "md_id", "paragraph_id", "direction_title", "source_url",
                                                             "excerpt", "deadline_frequency", "subject_family", "hidden")}
                    cur["_classes"] = []
                if cls not in cur["_classes"]:
                    cur["_classes"].append(cls)
        for r in rows.values():
            cs = r.pop("_classes")
            r["status"] = "applies to " + ("all 11 entity types" if len(cs) == len(self.corpus.core_classes) else ", ".join(cs))
        pack = {"pack_id": f"assistant_{key.lower().replace(' ', '_')}_{today.isoformat()}", "created_utc": today.isoformat(),
                "register": list(rows.values())}
        with self.lock:
            self.general[key] = pack
        return pack

    def ask_general(self, body: Mapping[str, Any]) -> dict:
        cls = body.get("entity_class") or None
        if cls is not None and cls not in self.corpus.core_classes:
            raise HttpError(422, "entity_class must be one of the 11 core classes, or empty for all")
        pack = self.general_pack(cls)
        res = self.run(lambda: AI.ask(self.corpus, self.cfg, self.gcfg, pack, str(body.get("question") or ""), llm=self.llm(),
                                      models=self.models(), history=(body.get("history") or [])[-3:]))
        if res.get("abstained"):
            res["answer"] = ("I cannot answer this reliably from the RBI Master Directions in the corpus. The closest "
                             "evidence is listed below.")
        res["scope"] = cls or "all 11 entity types"
        return res
