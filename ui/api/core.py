"""Comparator API service (Demo Build Spec, Phase H). Shared by the local server (server.py) and the Azure Function
(function_app.py). Standard library only; the frozen prompt and rule come from ./bundle and are sha256-verified at start-up.

Honesty rules enforced here:
- If any frozen hash does not match, /api/health reports it and /api/compare refuses (503).
- `field` events are emitted only for values that have fully parsed from the model's streamed text (jsonstream.JsonStream).
  If the stream cannot be parsed incrementally, the run continues in buffered mode with no per-field events.
- The verdict always comes from the frozen rule (bundle/obli_frozen/comparator_rule.py), traced, never re-implemented.
- Paste mode: nothing of the pasted text is stored or logged. The cache keeps only the input hash and the field statuses.
- Request bodies are never logged; errors are reported without payloads.
- The model key is read from the environment of the server process only, never from a file and never sent to a client.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsonstream import JsonStream, JsonStreamError  # noqa: E402

API_DIR = Path(__file__).resolve().parent
BUNDLE = API_DIR / "bundle"
DATA = API_DIR / ".data"
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
log = logging.getLogger("rbiob.api")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, replay_key: str | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.replay_key = status, code, message, replay_key

    def body(self) -> dict:
        return {"code": self.code, "message": self.message, "replayKey": self.replay_key}


# ---------------------------------------------------------------------------------------------------------------------
# Frozen files
# ---------------------------------------------------------------------------------------------------------------------

class Frozen:
    def __init__(self, bundle: Path = BUNDLE):
        pkg = bundle / "obli_frozen"
        self.meta = json.loads((pkg / "FROZEN.json").read_text())
        self.expected = self.meta["sha256"]
        self.actual = {name: sha256_bytes((pkg / name).read_bytes()) for name in self.expected}
        self.mismatches = [n for n in self.expected if self.actual[n] != self.expected[n]]
        self.verified = not self.mismatches
        self.model = self.meta["model"]
        sys.path.insert(0, str(bundle))
        self.rule = _load("obli_frozen.comparator_rule", pkg / "comparator_rule.py")
        self.cmp = _load("obli_frozen.comparator", pkg / "comparator.py")
        self.prompts = self.cmp.Prompts(pkg) if self.verified else None

    @property
    def prompt_sha(self) -> str:
        return self.expected["comparator_system.txt"]

    @property
    def rule_sha(self) -> str:
        return self.expected["comparator_rule.py"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------------------------------------------------
# Rule trace, signals and the M2 confidence model (mirrors ui/scripts/build_demo_data.py and cc_common; tested for equality)
# ---------------------------------------------------------------------------------------------------------------------

def trace_candidates(rule, cands: list[dict]) -> tuple[list[dict], dict]:
    steps: list[dict] = []
    for c in cands:
        official = rule.candidate_verdict(c)
        pid = c["paragraph_id"]
        if not c["addresses_same_duty"]:
            steps.append({"step": "addresses the same duty", "fields": [], "result": "fired", "verdict": "none", "pid": pid})
            mine = "none"
        else:
            steps.append({"step": "addresses the same duty", "fields": [], "result": "pass", "pid": pid})
            fc = c["field_comparison"]
            differs = [f for f in rule.FIELDS if fc[f] == "differs"]
            one_side = [f for f in rule.MATERIAL if fc[f] in ("only_source", "only_target")]
            steps.append({"step": "any field differs", "fields": differs, "result": "fired" if differs else "pass",
                          **({"verdict": "different"} if differs else {}), "pid": pid})
            if not differs:
                steps.append({"step": "a material field is stated on one side only", "fields": one_side, "result": "fired" if one_side else "pass",
                              **({"verdict": "different"} if one_side else {}), "pid": pid})
            mine = "different" if (differs or one_side) else "same"
            if mine == "same":
                steps.append({"step": "no difference found", "fields": [], "result": "fired", "verdict": "same", "pid": pid})
        if mine != official:
            raise RuntimeError("trace wrapper disagrees with the frozen rule")
    v = rule.class_verdict(cands)
    steps.append({"step": "precedence same > different > none", "fields": [], "result": "fired", "verdict": v["judgement"], "pid": v["matched_paragraph_id"]})
    return steps, v


def signals(rule, raw: dict | None, judgement: str, matched: str | None) -> dict:
    """Same as ui/scripts/cc_common.comparator_signals, on an already-parsed raw answer."""
    out = {"parse_ok": raw is not None, "n_both": 0, "n_material_diff": 0, "hinge": False, "candidates_agree": False, "decisive_pid": None}
    if raw is None:
        return out
    cands = [c for c in raw.get("candidates") or [] if isinstance(c, dict)]
    verdicts = []
    for c in cands:
        try:
            verdicts.append(rule.candidate_verdict(c))
        except (KeyError, TypeError):
            verdicts.append("unsure")
    out["candidates_agree"] = len(set(verdicts)) == 1 and len(verdicts) >= 2
    pid = matched or (cands[0].get("paragraph_id") if cands else None)
    dec = next((c for c in cands if c.get("paragraph_id") == pid), cands[0] if cands else None)
    out["decisive_pid"] = pid
    if dec is None:
        return out
    src_f = raw.get("source", {}) or {}
    tgt_f = dec.get("fields", {}) or {}
    fc = dec.get("field_comparison", {}) or {}
    out["n_both"] = sum(1 for f in rule.FIELDS if src_f.get(f) not in (None, "") and tgt_f.get(f) not in (None, ""))
    diffs = [f for f in rule.FIELDS if fc.get(f) == "differs"] + [f for f in rule.MATERIAL if fc.get(f) in ("only_source", "only_target")]
    out["n_material_diff"] = len(set(diffs))
    out["hinge"] = judgement == "different" and len(set(diffs)) == 1
    return out


class Confidence:
    def __init__(self, bundle: Path = BUNDLE):
        m = json.loads((bundle / "confidence_m2.json").read_text())
        self.version, self.cuts, self.m = m["version"], m["bandThresholds"], m["M2"]
        ctx = json.loads((bundle / "context.json").read_text())
        self.amended = set(ctx["amended"])
        self.cells = ctx["ambiguousCells"]
        self.family = ctx["familyOfDirection"]
        self.ctx = ctx

    def features(self, sig: dict, judgement: str, source_class: str, source_md: str | None) -> list[float] | None:
        if not sig["parse_ok"] or judgement not in ("same", "different", "none"):
            return None
        fam = self.family.get(source_md or "")
        target_md = (sig["decisive_pid"] or "").split("::")[0]
        return [float(judgement == "different"), float(judgement == "none"), float(sig["n_both"]), float(sig["n_material_diff"]),
                float(sig["hinge"]), float(sig["candidates_agree"]), float(target_md in self.amended), float(bool(self.cells.get(f"{source_class}|{fam}", False)))]

    def score(self, x: list[float] | None) -> dict:
        if x is None:
            return {"p": None, "band": "Abstain", "model": "M2", "version": self.version}
        z = self.m["intercept"] + sum(w * (v - mu) / sd for w, v, mu, sd in zip(self.m["weights"], x, self.m["means"], self.m["sds"]))
        p = 1 / (1 + math.exp(-z))
        band = "High" if p >= self.cuts["high"] else ("Medium" if p >= self.cuts["low"] else "Low")
        return {"p": p, "band": band, "model": "M2", "version": self.version}


# ---------------------------------------------------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------------------------------------------------

@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class Llm(Protocol):
    id: str
    mock: bool

    def stream(self, system: str, user: str, usage: Usage) -> Iterator[str]: ...


class GeminiLlm:
    """Gemini streamGenerateContent (SSE). Same request shape as the sealed run: temperature 0, JSON mode, minimal thinking."""

    mock = False

    def __init__(self, api_key: str, ctx: dict, opener: Callable[..., Any] = urllib.request.urlopen):
        self._key = api_key
        self.id = ctx["model"]
        self.cfg = {"temperature": ctx["temperature"], "maxOutputTokens": ctx["maxOutputTokens"], "thinkingConfig": ctx["thinking"],
                    **({"responseMimeType": "application/json"} if ctx["jsonMode"] else {})}
        self.opener = opener

    def stream(self, system: str, user: str, usage: Usage) -> Iterator[str]:
        payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": user}]}],
                   "generationConfig": self.cfg}
        req = urllib.request.Request(f"{GEMINI}/models/{self.id}:streamGenerateContent?alt=sse", data=json.dumps(payload).encode(),
                                     headers={"content-type": "application/json", "x-goog-api-key": self._key}, method="POST")
        try:
            resp = self.opener(req, timeout=90)
        except urllib.error.HTTPError as e:
            raise LlmError("quota" if e.code == 429 else "upstream", f"provider error {e.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LlmError("offline", f"provider unreachable ({type(e).__name__})") from None
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                obj = json.loads(line[6:])
                um = obj.get("usageMetadata") or {}
                if um:
                    usage.input_tokens = um.get("promptTokenCount", usage.input_tokens)
                    usage.output_tokens = um.get("candidatesTokenCount", usage.output_tokens)
                for cand in obj.get("candidates") or []:
                    for part in (cand.get("content") or {}).get("parts") or []:
                        if part.get("text") and not part.get("thought"):
                            yield part["text"]


class MockLlm:
    """Test double: streams scripted text in chunks. Health reports it as a mock; it is never deployed."""

    mock = True

    def __init__(self, reply: Callable[[str, str], str], chunk: int = 37, fail_after: int | None = None):
        self.id = "mock (test double)"
        self.reply, self.chunk, self.fail_after = reply, chunk, fail_after
        self.calls: list[tuple[str, str]] = []

    def stream(self, system: str, user: str, usage: Usage) -> Iterator[str]:
        self.calls.append((system, user))
        text = self.reply(system, user)
        usage.input_tokens, usage.output_tokens = len((system + user).split()), len(text.split())
        for i in range(0, len(text), self.chunk):
            if self.fail_after is not None and i >= self.fail_after:
                raise LlmError("offline", "connection lost mid-stream")
            yield text[i:i + self.chunk]


# ---------------------------------------------------------------------------------------------------------------------
# Durable store (local files, or Azure Blob when CACHE_CONNECTION is set) and rate limiting
# ---------------------------------------------------------------------------------------------------------------------

class FileStore:
    def __init__(self, root: Path):
        self.root = root
        (root / "replays").mkdir(parents=True, exist_ok=True)
        (root / "paste").mkdir(parents=True, exist_ok=True)

    def get(self, ns: str, key: str) -> dict | None:
        p = self.root / ns / f"{key}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def put(self, ns: str, key: str, obj: dict) -> None:
        (self.root / ns).mkdir(parents=True, exist_ok=True)
        (self.root / ns / f"{key}.json").write_text(json.dumps(obj, ensure_ascii=False))

    def count(self, ns: str) -> int:
        return len(list((self.root / ns).glob("*.json"))) if (self.root / ns).exists() else 0

    def append(self, name: str, obj: dict) -> None:
        with (self.root / name).open("a", encoding="utf-8") as h:
            h.write(json.dumps(obj, ensure_ascii=False) + "\n")


class BlobStore:
    """Azure Blob container (deployed mode). Appends go to an append blob, never to a file inside a Function instance."""

    def __init__(self, conn: str, container: str = "comparator-cache"):
        from azure.storage.blob import BlobServiceClient  # type: ignore[import-not-found]

        self.c = BlobServiceClient.from_connection_string(conn).get_container_client(container)
        try:
            self.c.create_container()
        except Exception:  # noqa: BLE001 - already exists
            pass

    def get(self, ns: str, key: str) -> dict | None:
        try:
            return json.loads(self.c.download_blob(f"{ns}/{key}.json").readall())
        except Exception:  # noqa: BLE001 - not found
            return None

    def put(self, ns: str, key: str, obj: dict) -> None:
        self.c.upload_blob(f"{ns}/{key}.json", json.dumps(obj, ensure_ascii=False), overwrite=True)

    def count(self, ns: str) -> int:
        return sum(1 for _ in self.c.list_blobs(name_starts_with=f"{ns}/"))

    def append(self, name: str, obj: dict) -> None:
        b = self.c.get_blob_client(name)
        if not b.exists():
            b.create_append_blob()
        b.append_block((json.dumps(obj, ensure_ascii=False) + "\n").encode())


class RateLimiter:
    def __init__(self, per_min: int):
        self.per_min, self.hits, self.lock = per_min, {}, threading.Lock()

    def allow(self, who: str) -> bool:
        now = time.monotonic()
        with self.lock:
            xs = [t for t in self.hits.get(who, []) if now - t < 60]
            if len(xs) >= self.per_min:
                self.hits[who] = xs
                return False
            xs.append(now)
            self.hits[who] = xs
            return True


# ---------------------------------------------------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------------------------------------------------

@dataclass
class Settings:
    mode: str = "public"  # public | presenter
    rate_per_min: int = 6
    streaming: str = "incremental"  # incremental | buffered (Azure without an HTTP streaming extension)
    rehydrate_allowed: bool = False


def cache_key(prompt_sha: str, rule_sha: str, model: str, mode: str, payload: dict) -> str:
    """Identical to the client's cacheKey(): sha256(prompt|rule|model|mode|JSON.stringify(payload))."""
    return sha256_bytes(f"{prompt_sha}|{rule_sha}|{model}|{mode}|{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}".encode())


@dataclass
class Service:
    frozen: Frozen
    conf: Confidence
    llm: Llm | None
    store: Any
    settings: Settings = field(default_factory=Settings)
    inputs: dict = field(default_factory=dict)
    paragraphs: dict = field(default_factory=dict)
    freshness_fn: Callable[[str], dict] | None = None
    limiter: RateLimiter | None = None
    unavailable_reason: str | None = None

    def __post_init__(self):
        self.limiter = self.limiter or RateLimiter(self.settings.rate_per_min)

    # -- health ----------------------------------------------------------------------------------------------------------
    def health(self) -> dict:
        try:
            replays, reachable = self.store.count("replays"), True
        except Exception:  # noqa: BLE001
            replays, reachable = 0, False
        model_ok = self.llm is not None and self.frozen.verified
        return {
            "ok": self.frozen.verified and reachable,
            "model": {"id": self.llm.id if self.llm else self.frozen.model, "available": model_ok, "mock": bool(self.llm and self.llm.mock),
                      **({} if model_ok else {"reason": self.unavailable_reason or ("frozen hashes do not match" if not self.frozen.verified else "no model key configured on the server")})},
            "hashes": {"verified": self.frozen.verified, "prompt": self.frozen.prompt_sha, "rule": self.frozen.rule_sha, "mismatches": self.frozen.mismatches},
            "cache": {"reachable": reachable, "replays": replays},
            "mode": self.settings.mode, "streaming": self.settings.streaming,
            "rehydrate": self.settings.mode == "presenter" and self.settings.rehydrate_allowed and bool(self.paragraphs),
        }

    # -- compare ---------------------------------------------------------------------------------------------------------
    def prepare(self, body: dict) -> tuple[str, dict, str | None, dict]:
        """-> (mode, unit inputs, cache key or None, meta). Raises ServiceError for bad requests."""
        mode = body.get("mode")
        if mode in ("benchmark", "edit"):
            uid = body.get("unitId")
            if uid not in self.inputs:
                raise ServiceError(404, "unknown_unit", "Unknown benchmark pair (or the server has no benchmark inputs).")
            u = dict(self.inputs[uid])
            u["candidates"] = [list(c) for c in u["candidates"]]
            payload: dict = {"unitId": uid}
            if mode == "edit":
                edits = body.get("edits") or []
                if not isinstance(edits, list) or not edits or len(edits) > 3:
                    raise ServiceError(400, "bad_edits", "Send one to three structured edits.")
                target = u.get("sealed_matched") or u["candidates"][0][0]
                idx = next((i for i, c in enumerate(u["candidates"]) if c[0] == target), 0)
                text = u["candidates"][idx][1]
                clean = []
                for e in edits:
                    frm, to, kind = str(e.get("from", "")), str(e.get("to", "")), str(e.get("kind", ""))
                    if not frm or frm not in text:
                        raise ServiceError(400, "edit_not_applicable", "The edit's original text is not in the target paragraph.")
                    text = text.replace(frm, to, 1)
                    clean.append({"kind": kind, "from": frm, "to": to})
                u["candidates"][idx][1] = text
                payload = {"unitId": uid, "edits": clean}
                u["edited_pid"] = target
            key = cache_key(self.frozen.prompt_sha, self.frozen.rule_sha, self.llm.id if self.llm else self.frozen.model, mode, payload)
            return mode, u, key, payload
        if mode == "paste":
            a, b, ca, cb = (str(body.get(k) or "") for k in ("textA", "textB", "classA", "classB"))
            if not a.strip() or not b.strip() or not ca or not cb:
                raise ServiceError(400, "bad_paste", "Paste two texts and choose both institution types.")
            if len(a) > 4000 or len(b) > 4000:
                raise ServiceError(400, "too_long", "Each text may have at most 4,000 characters.")
            u = {"item_id": None, "source_class": ca, "source_text": a, "target_class": cb, "candidates": [["pasted::B", b]], "source_md": None}
            ih = sha256_bytes(json.dumps([a, b, ca, cb], ensure_ascii=False).encode())
            return mode, u, None, {"inputHash": ih}
        raise ServiceError(400, "bad_mode", "mode must be benchmark, edit or paste.")

    def compare(self, body: dict, client: str = "anon") -> Iterator[dict]:
        """Yields events {"type", "data"}. Raises ServiceError before the first event for refusals."""
        if not self.frozen.verified:
            raise ServiceError(503, "hash_mismatch", f"Frozen files changed: {', '.join(self.frozen.mismatches)}. Live runs are disabled.")
        mode, u, key, payload = self.prepare(body)
        if self.llm is None:
            raise ServiceError(503, "model_unavailable", self.unavailable_reason or "No model key is configured on the server.", key)
        if not self.limiter.allow(client):
            raise ServiceError(429, "rate_limited", "Too many live runs from this address; try again in a minute or watch the cached replay.", key)
        return self._run(mode, u, key, payload, body)

    def _run(self, mode: str, u: dict, key: str | None, payload: dict, body: dict) -> Iterator[dict]:
        rule, cmp_ = self.frozen.rule, self.frozen.cmp
        cands = [(c[0], c[1]) for c in u["candidates"]]
        ids = [c[0] for c in cands]
        msgs = self.frozen.prompts.messages(source_class=u["source_class"], source_text=u["source_text"], target_class=u["target_class"], candidates=cands)
        system = next(m["content"] for m in msgs if m["role"] == "system")
        user = next(m["content"] for m in msgs if m["role"] == "user")
        t0, started = time.monotonic(), utcnow()
        events: list[dict] = []

        def ev(t: str, d: dict) -> dict:
            e = {"type": t, "data": d}
            if mode != "paste":
                events.append({**e, "t": round(time.monotonic() - t0, 3)})
            return e

        streaming = self.settings.streaming
        yield ev("status", {"message": "Receiving structured output…", "streaming": streaming})
        parser = JsonStream() if streaming == "incremental" else None
        cand_pid: dict[int, str] = {}
        usage = Usage()
        text: list[str] = []
        try:
            for chunk in self.llm.stream(system, user, usage):
                text.append(chunk)
                if parser is None:
                    continue
                try:
                    leaves = parser.feed(chunk)
                except JsonStreamError:
                    parser = None
                    streaming = "buffered"
                    yield ev("status", {"message": "Receiving structured output…", "streaming": "buffered"})
                    continue
                for path, value in leaves:
                    f = _field_event(path, value, cand_pid, rule)
                    if f:
                        yield ev("field", f)
        except LlmError as e:
            yield {"type": "error", "data": {"code": e.kind, "message": str(e), "replayKey": key}}
            return
        full = "".join(text)
        parsed, problems = cmp_.parse_response(full, ids)
        if parsed:
            trace, v = trace_candidates(rule, parsed)
            judgement, matched = v["judgement"], v["matched_paragraph_id"]
        else:
            trace = [{"step": "model output could not be read", "fields": [], "result": "fired", "verdict": "abstain"}]
            judgement, matched = "unsure", None
        try:
            raw = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", full.strip()))
        except json.JSONDecodeError:
            raw = None
        raw = raw if parsed else None
        dec_pid = matched or (ids[0] if ids else None)
        dec = next((c for c in (parsed or []) if c["paragraph_id"] == dec_pid), None)
        rows = [{"field": f, "status": dec["field_comparison"][f]} for f in rule.FIELDS] if dec else []
        yield ev("verdict", {"judgement": judgement, "matchedPid": matched, "trace": trace, "rows": rows,
                             "perCandidate": [{"pid": c["paragraph_id"], "verdict": rule.candidate_verdict(c)} for c in parsed] if parsed else [],
                             "parseProblems": problems[:3]})
        sig = signals(rule, raw, judgement, matched)
        conf = self.conf.score(self.conf.features(sig, judgement, u["source_class"], u.get("source_md")))
        yield ev("confidence", conf)
        done = {"cacheKey": key, "latencyMs": int((time.monotonic() - t0) * 1000), "inputTokens": usage.input_tokens,
                "outputTokens": usage.output_tokens, "recordedUtc": started, "replay": False, "model": self.llm.id, "streaming": streaming}
        yield ev("done", done)
        try:
            if mode == "paste":
                # Privacy: only the input hash and the field statuses; never the pasted text or extracted values.
                self.store.put("paste", payload["inputHash"], {"inputHash": payload["inputHash"], "judgement": judgement, "statuses": rows, "utc": started})
            else:
                # Test-double runs never become "cached replays" of a live model.
                self.store.put("replays-mock" if self.llm.mock else "replays", key, {"key": key, "mode": mode, "payload": payload, "recordedUtc": started, "model": self.llm.id,
                                                "promptSha": self.frozen.prompt_sha, "ruleSha": self.frozen.rule_sha, "events": events})
                if mode == "edit":
                    self.store.append("lab_runs.jsonl", {"utc": started, "unitId": payload["unitId"], "edits": payload["edits"],
                                                          "control": body.get("control"), "judgement": judgement, "statuses": rows, "key": key})
        except Exception:  # noqa: BLE001 - the run itself succeeded; a cache failure is logged without payloads
            log.warning("cache write failed for a %s run", mode)

    # -- replay / rehydrate / freshness -------------------------------------------------------------------------------
    def replay(self, key: str) -> dict:
        if not re.fullmatch(r"[0-9a-f]{64}", key or ""):
            raise ServiceError(400, "bad_key", "Malformed replay key.")
        rec = self.store.get("replays-mock" if (self.llm and self.llm.mock) else "replays", key)
        if not rec:
            return {"found": False, "events": [], "recordedUtc": None, "model": None}  # 200: absence is a normal answer
        evs = [{"type": e["type"], "data": ({**e["data"], "replay": True} if e["type"] == "done" else e["data"])} for e in rec["events"]]
        return {"found": True, "events": evs, "recordedUtc": rec["recordedUtc"], "model": rec.get("model")}

    def rehydrate(self, pid: str) -> dict:
        if not (self.settings.mode == "presenter" and self.settings.rehydrate_allowed):
            raise ServiceError(403, "public_mode", "Full text is available only in presenter mode.")
        if pid not in self.paragraphs:
            raise ServiceError(404, "unknown_paragraph", "Unknown paragraph id.")
        return {"pid": pid, "text": self.paragraphs[pid]}

    def freshness(self, pid: str) -> dict:
        now = utcnow()
        cached = self.store.get("freshness", hashlib.sha256(pid.encode()).hexdigest())
        if cached and (datetime.fromisoformat(now) - datetime.fromisoformat(cached["checkedUtc"])).total_seconds() < 86400:
            return cached
        if self.freshness_fn is None:
            out = {"outcome": "unverified", "harvestDate": None, "detail": "the re-segmentation pipeline is not installed on this server", "checkedUtc": now}
        else:
            try:
                out = {**self.freshness_fn(pid), "checkedUtc": now}
            except Exception as e:  # noqa: BLE001
                out = {"outcome": "unverified", "harvestDate": None, "detail": f"{type(e).__name__}", "checkedUtc": now}
        try:
            self.store.put("freshness", hashlib.sha256(pid.encode()).hexdigest(), out)
        except Exception:  # noqa: BLE001
            pass
        return out


def _field_event(path: tuple, value: Any, cand_pid: dict, rule) -> dict | None:
    if len(path) == 2 and path[0] == "source" and path[1] in rule.FIELDS:
        return {"path": "source." + path[1], "candidate": None, "field": path[1], "kind": "source", "value": value}
    if len(path) >= 3 and path[0] == "candidates" and isinstance(path[1], int):
        i = path[1]
        if path[2] == "paragraph_id" and len(path) == 3:
            cand_pid[i] = value
            return None
        pid = cand_pid.get(i, f"candidate {i + 1}")
        if path[2] == "addresses_same_duty" and len(path) == 3:
            return {"path": f"candidates.{i}.addresses_same_duty", "candidate": pid, "field": "addresses_same_duty", "kind": "same_duty", "value": value}
        if len(path) == 4 and path[3] in rule.FIELDS and path[2] in ("fields", "field_comparison"):
            return {"path": f"candidates.{i}.{path[2]}.{path[3]}", "candidate": pid, "field": path[3],
                    "kind": "target" if path[2] == "fields" else "comparison", "value": value}
    return None


# ---------------------------------------------------------------------------------------------------------------------

def build_service(mode: str | None = None, llm: Llm | None = None, store: Any = None, streaming: str | None = None,
                  key_env: Iterable[str] = ("ASSISTANT_GEMINI_API_KEY",), with_inputs: bool = True) -> Service:
    """Construct the service from environment settings. The key is read only from the named environment variables."""
    frozen = Frozen()
    conf = Confidence()
    mode = mode or os.environ.get("MODE", "public")
    reason = None
    if llm is None:
        key = next((os.environ[k] for k in key_env if os.environ.get(k)), None)
        if key:
            llm = GeminiLlm(key, conf.ctx)
        else:
            reason = "No model key is configured on the server (" + " / ".join(key_env) + "). Showing cached replays."
    if store is None:
        conn = os.environ.get("CACHE_CONNECTION")
        store = BlobStore(conn) if conn else FileStore(API_DIR / ".state")
    inputs = json.loads((DATA / "inputs.json").read_text()) if with_inputs and (DATA / "inputs.json").exists() else {}
    paragraphs = json.loads((DATA / "paragraphs.json").read_text()) if mode == "presenter" and (DATA / "paragraphs.json").exists() else {}
    settings = Settings(mode=mode, rate_per_min=int(os.environ.get("RATE_LIMIT_PER_MIN", "6")),
                        streaming=streaming or os.environ.get("STREAMING", "incremental"), rehydrate_allowed=mode == "presenter")
    return Service(frozen=frozen, conf=conf, llm=llm, store=store, settings=settings, inputs=inputs, paragraphs=paragraphs,
                   freshness_fn=_local_freshness() if mode == "presenter" else None, unavailable_reason=reason)


def _local_freshness() -> Callable[[str], dict] | None:
    """H4 with the repository's own pipeline (local / presenter only): fetch, re-segment, hash, compare."""
    root = API_DIR.parents[1]
    if not (root / "scripts/rehydrate.py").exists():
        return None

    def check(pid: str) -> dict:
        sys.path.insert(0, str(root))
        rh = _load("rbiob_rehydrate", root / "scripts/rehydrate.py")
        md = pid.split("::")[0]
        docs = {d["md_id"]: d for d in rh.jl(root / "release/data/documents.jsonl")}
        want = next((r for r in rh.jl(root / "release/data/paragraphs.jsonl") if r["paragraph_id"] == pid), None)
        if md not in docs or want is None:
            return {"outcome": "unverified", "harvestDate": None, "detail": "paragraph not in the release"}
        got, notes = rh.online_paragraphs(docs, [md])
        harvest = docs[md].get("harvest_date")
        text = (got.get(md) or {}).get(pid)
        if text is None:
            return {"outcome": "unverified", "harvestDate": harvest, "detail": notes.get(md) or "paragraph not located after re-segmentation"}
        return {"outcome": "match" if rh.sha(text) == want["text_sha256"] else "differs", "harvestDate": harvest, "detail": notes.get(md)}

    return check
