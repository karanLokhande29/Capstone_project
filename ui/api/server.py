#!/usr/bin/env python3
"""Local comparator API (Demo Build Spec, Phase H): the same service as the Azure Function, on the standard library.

    python3 ui/api/server.py                    # public mode, port 5190 (vite dev proxies /api/health etc. here)
    MODE=presenter python3 ui/api/server.py     # presenter mode: full paragraph text, freshness check
    (cd ui && npm run present:local)            # presenter mode + the app

The model key is read only from ASSISTANT_GEMINI_API_KEY in this process's environment (never from a file, never the
experiments' GEMINI_API_KEY). Without it, /api/health reports the live model as unavailable and the UI uses replays.
Request bodies are never logged.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import ServiceError, build_service  # noqa: E402

ALLOWED = {o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5181,http://127.0.0.1:5181,http://localhost:5183").split(",") if o.strip()}
MAX_BODY = 20_000


def make_handler(svc):
    class H(BaseHTTPRequestHandler):
        server_version = "rbiob-api"

        def log_message(self, fmt, *args):  # method + path + status only; never bodies or query strings
            logging.getLogger("rbiob.api.http").info("%s %s", self.command, urlparse(self.path).path.split("/api/")[-1].split("/")[0])

        def _cors(self):
            origin = self.headers.get("Origin")
            if origin in ALLOWED:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

        def _json(self, status: int, obj: dict):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "content-type, accept")
            self.end_headers()

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == "/api/health":
                    return self._json(200, svc.health())
                if path.startswith("/api/replay/"):
                    return self._json(200, svc.replay(unquote(path.split("/api/replay/", 1)[1])))
                if path.startswith("/api/rehydrate/"):
                    return self._json(200, svc.rehydrate(unquote(path.split("/api/rehydrate/", 1)[1])))
                if path.startswith("/api/freshness/"):
                    return self._json(200, svc.freshness(unquote(path.split("/api/freshness/", 1)[1])))
                return self._json(404, {"code": "not_found", "message": "Unknown endpoint."})
            except ServiceError as e:
                return self._json(e.status, e.body())

        def do_POST(self):
            if urlparse(self.path).path != "/api/compare":
                return self._json(404, {"code": "not_found", "message": "Unknown endpoint."})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._json(413, {"code": "too_large", "message": "Request too large."})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"code": "bad_json", "message": "Body is not JSON."})
            try:
                events = svc.compare(body, client=self.client_address[0])
            except ServiceError as e:
                return self._json(e.status, e.body())
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self._cors()
            self.end_headers()
            try:
                for e in events:
                    self.wfile.write(f"event: {e['type']}\ndata: {json.dumps(e['data'], ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                logging.getLogger("rbiob.api").info("client went away mid-stream")
            except Exception as exc:  # noqa: BLE001 - report without payloads
                logging.getLogger("rbiob.api").error("compare failed: %s", type(exc).__name__)
                try:
                    self.wfile.write(b'event: error\ndata: {"code":"internal","message":"The run failed on the server."}\n\n')
                except OSError:
                    pass

    return H


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    llm = None
    if os.environ.get("MOCK_LLM") == "sealed":
        # Dev-only test double for UI checks: replays the sealed output of each unit as if it were a model, slowly.
        # /api/health reports it as a mock, and the UI labels its runs "Test double", never "Live re-run".
        import time
        from core import MockLlm, build_service as _bs

        base = _bs(llm=MockLlm(lambda a, b: "", chunk=1))
        sealed = {}
        for p in (Path(__file__).resolve().parents[2] / "data/rag_runs/sealed_phase4/comparator_t1_gold_v1").glob("t1_*.json"):
            r = json.loads(p.read_text())
            sealed[f"{r['item_id']}|{r['target_class']}"] = r["raw"]

        def reply(system: str, user: str) -> str:
            for uid, u in base.inputs.items():
                if u["candidates"][0][0] in user and u["source_text"][:200] in user:
                    return sealed.get(uid, "{}")
            return "{}"

        class Slow(MockLlm):
            def stream(self, system, user, usage):
                for c in super().stream(system, user, usage):
                    time.sleep(0.04)
                    yield c

        llm = Slow(reply, chunk=24)
    svc = build_service(llm=llm)
    port = int(os.environ.get("PORT", "5190"))
    h = svc.health()
    print(f"comparator API on http://127.0.0.1:{port} · mode {h['mode']} · hashes {'verified' if h['hashes']['verified'] else 'MISMATCH'} · "
          f"model {'available' if h['model']['available'] else 'unavailable (replay only)'} · replays {h['cache']['replays']}")
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(svc)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
