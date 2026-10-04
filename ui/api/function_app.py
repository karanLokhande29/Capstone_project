"""Azure Functions (Python v2 programming model) wrapper around core.Service — Demo Build Spec H1.

App settings: GEMINI_API_KEY (a key dedicated to this demo, never the experiments' key), MODE=public|presenter,
CACHE_CONNECTION (storage connection string for replays / lab-run log), RATE_LIMIT_PER_MIN=6, ALLOWED_ORIGINS.
CORS is restricted to the site origin in the Function App's CORS settings (and checked here).

Responses are buffered (STREAMING=buffered): the whole event stream is returned once the model has finished. The UI
then shows only "Receiving structured output…" until the result arrives; it never claims fields appeared one by one.
Not deployed yet: deployment waits for a model key and approval (AUDIT.md, hard stop 3).
"""

from __future__ import annotations

import json
import logging
import os

import azure.functions as func  # type: ignore[import-not-found]

from core import ServiceError, build_service

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
_svc = None
ALLOWED = {o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "https://rbioblibench5qbvp2.z29.web.core.windows.net,http://localhost:5173").split(",") if o.strip()}


def svc():
    global _svc
    if _svc is None:
        _svc = build_service(streaming="buffered", key_env=("GEMINI_API_KEY",))
    return _svc


def _headers(req: func.HttpRequest, ctype: str = "application/json") -> dict:
    h = {"Content-Type": ctype, "Cache-Control": "no-store"}
    origin = req.headers.get("Origin")
    if origin in ALLOWED:
        h.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
    return h


def _json(req, status, obj):
    return func.HttpResponse(json.dumps(obj, ensure_ascii=False), status_code=status, headers=_headers(req))


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json(req, 200, svc().health())


@app.route(route="compare", methods=["POST"])
def compare(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json(req, 400, {"code": "bad_json", "message": "Body is not JSON."})
    try:
        events = list(svc().compare(body, client=(req.headers.get("X-Forwarded-For") or "anon").split(",")[0]))
    except ServiceError as e:
        return _json(req, e.status, e.body())
    except Exception as e:  # noqa: BLE001 - never log or echo the payload
        logging.error("compare failed: %s", type(e).__name__)
        return _json(req, 500, {"code": "internal", "message": "The run failed on the server."})
    text = "".join(f"event: {e['type']}\ndata: {json.dumps(e['data'], ensure_ascii=False)}\n\n" for e in events)
    return func.HttpResponse(text, status_code=200, headers=_headers(req, "text/event-stream"))


@app.route(route="replay/{key}", methods=["GET"])
def replay(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _json(req, 200, svc().replay(req.route_params.get("key", "")))
    except ServiceError as e:
        return _json(req, e.status, e.body())


@app.route(route="rehydrate/{pid}", methods=["GET"])
def rehydrate(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _json(req, 200, svc().rehydrate(req.route_params.get("pid", "")))
    except ServiceError as e:
        return _json(req, e.status, e.body())


@app.route(route="freshness/{pid}", methods=["GET"])
def freshness(req: func.HttpRequest) -> func.HttpResponse:
    return _json(req, 200, svc().freshness(req.route_params.get("pid", "")))
