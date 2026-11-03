"""Azure Functions (Python v2) wrapper around service.Service: the hosted audit generator for the public site.

App settings: AUDIT_GEMINI_API_KEY (the model key, read from the environment only), AUDIT_STORE_CONNECTION (storage for
generated packs and AI outputs), ALLOWED_ORIGINS. CORS is also set on the Function App. Deploy: ui/api_audit/deploy.sh.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import threading

import azure.functions as func  # type: ignore[import-not-found]

from service import BlobStore, GzJson, HttpError, Service

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
ALLOWED = {o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "https://rbioblibench5qbvp2.z29.web.core.windows.net").split(",") if o.strip()}
MAX_BODY = 256_000
_svc: Service | None = None
_init = threading.Lock()


def svc() -> Service:
    global _svc
    with _init:
        if _svc is None:
            _svc = Service(BlobStore(os.environ["AUDIT_STORE_CONNECTION"]))
    return _svc


def _warm() -> None:
    try:
        s = svc()
        s.models()
    except Exception:  # noqa: BLE001 - the next real request reports the error
        logging.exception("warm-up failed")


def _headers(req: func.HttpRequest, ctype: str) -> dict:
    h = {"Content-Type": ctype, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    origin = req.headers.get("Origin")
    if origin in ALLOWED:
        h.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
    return h


def _json(req: func.HttpRequest, status: int, obj) -> func.HttpResponse:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    h = _headers(req, "application/json")
    if len(body) > 2048 and "gzip" in (req.headers.get("Accept-Encoding") or ""):
        body = gzip.compress(body, 6)
        h["Content-Encoding"] = "gzip"
    return func.HttpResponse(body, status_code=status, headers=h)


@app.route(route="auditgen/{*rest}", methods=["GET", "POST"])
def auditgen(req: func.HttpRequest) -> func.HttpResponse:
    rest = req.route_params.get("rest", "")
    if req.method == "GET" and rest.strip("/") == "health":
        # Answers at once on a cold instance and loads the corpus and models in the background (about 20 s).
        if _svc is None:
            threading.Thread(target=_warm, daemon=True).start()
        return _json(req, 200, {"ok": True, "mode": "hosted", "remote_api_calls": True, "ready": _svc is not None,
                                "quote_words": 12, "keeps_packs_days": 7,
                                "worker": f"{os.environ.get('WEBSITE_INSTANCE_ID', '')[:6]}-{os.getpid()}"})
    body = None
    if req.method == "POST":
        raw = req.get_body() or b""
        if len(raw) > MAX_BODY:
            return _json(req, 413, {"detail": "request too large"})
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            return _json(req, 400, {"detail": "body is not JSON"})
    client = (req.headers.get("X-Forwarded-For") or "anon").split(",")[0].strip().rsplit(":", 1)[0]
    try:
        out = svc().handle_http(req.method, rest, body, client)
    except HttpError as e:
        return _json(req, e.status, {"detail": e.detail})
    except Exception:  # noqa: BLE001
        logging.exception("auditgen failed")
        return _json(req, 500, {"detail": "internal error"})
    if isinstance(out, GzJson):
        h = _headers(req, "application/json")
        h["Content-Encoding"] = "gzip"
        return func.HttpResponse(bytes(out), status_code=200, headers=h)
    if isinstance(out, tuple):
        data, ctype, name = out
        h = _headers(req, ctype)
        h["Content-Disposition"] = f'attachment; filename="{name}"'
        return func.HttpResponse(data, status_code=200, headers=h)
    return _json(req, 200, out)
