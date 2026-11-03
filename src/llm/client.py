"""Provider-agnostic LLM client (P3-001). Free tiers only.

* **Primary:** Gemini (``GEMINI_API_KEY``). **Fallback:** Groq (``GROQ_API_KEY``),
  used only when the primary keeps answering with a rate-limit / quota error.
* Keys come from a gitignored ``.env`` loaded with python-dotenv; environment
  variables that are already set win. Key values are never printed, logged,
  cached or written. Errors name the variable only ("GEMINI_API_KEY
  missing/empty"), and every provider error message is redacted before it is
  raised, in case an API ever echoes a key back.
* Keys travel in request headers, never in URLs, so a ``requests`` exception
  (which quotes the URL) cannot leak one.
* Every call runs at temperature 0, goes through a disk cache keyed on
  sha256(provider, model, messages, params), is throttled client-side
  (requests and tokens per minute), backs off exponentially on HTTP 429 (and on
  5xx, which never triggers the fallback), and
  counts against a hard per-run cap (``llm.max_calls``). Each HTTP attempt
  counts, retries included, because the cap protects the free-tier quota.
* **Providers are never mixed within one system run.** The run locks to the
  provider that serves its first answer (cache hits included). If the primary
  is rate-limited before that, the whole run moves to the fallback and the
  switch is recorded. If it is rate-limited after that, the run is marked
  ``fallback_needed_mid_run`` and :class:`ProviderSwitchMidRun` is raised: the
  caller reruns the whole system on the fallback (``force_provider``) rather
  than mixing answers from two models.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import random
import re
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from src.common.config import REPO_ROOT, get_required
from src.common.errors import FoundationError
from src.common.io_helpers import atomic_write_text

DEFAULT_ENV_FILE = REPO_ROOT / ".env"
KEY_ENV = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROQ_BASE = "https://api.groq.com/openai/v1"

Message = Mapping[str, str]  # {"role": "system" | "user" | "assistant", "content": str}


# -- errors -------------------------------------------------------------------


class LLMError(FoundationError):
    """Base class for LLM client failures."""


class MissingKeyError(LLMError):
    """An API key variable is unset or empty. The message names the variable only."""


class RateLimitError(LLMError):
    """HTTP 429 / quota exhausted."""


class ProviderError(LLMError):
    """Any other provider failure (bad request, auth, blocked output)."""


class TransientError(ProviderError):
    """HTTP 5xx (e.g. Gemini 503 "high demand"): backed off and retried, never a reason to fall back."""


class CallCapReached(LLMError):
    """``llm.max_calls`` HTTP attempts have been made in this run."""


class ProviderSwitchMidRun(LLMError):
    """The primary hit its quota after it had already answered in this run."""


class CacheMiss(LLMError):
    """Cache-only mode: the exact prompt is not cached, and no API call is allowed."""


class QuotaPaused(LLMError):
    """P4: the daily quota (or the ledger's soft cap) is reached. Checkpoint, stop, resume after the reset."""

    def __init__(self, message: str, *, resume_after_ist: str | None = None):
        super().__init__(message)
        self.resume_after_ist = resume_after_ist


# -- keys ---------------------------------------------------------------------


def load_env(path: Path | str | None = None) -> bool:
    """Load ``.env`` into ``os.environ`` without overriding variables already set.

    Returns whether the file existed. Nothing about its contents is returned or logged.
    """
    from dotenv import load_dotenv

    env_path = Path(path) if path is not None else DEFAULT_ENV_FILE
    if not env_path.exists():
        return False
    load_dotenv(env_path, override=False)
    return True


def require_key(name: str, env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    value = (env.get(name) or "").strip()
    if not value:
        raise MissingKeyError(f"{name} missing/empty")
    return value


def _redact(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


# -- provider layer -----------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    """One model as the provider's list endpoint describes it."""

    provider: str
    id: str
    version: str | None = None
    display_name: str | None = None
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    methods: tuple[str, ...] = ()
    active: bool = True


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str
    #: What the API says actually served the call (Gemini ``modelVersion``,
    #: Groq ``model`` + ``system_fingerprint``).
    model_version: str | None
    input_tokens: int
    output_tokens: int
    cached: bool = False


class Provider(Protocol):
    name: str

    def list_models(self) -> list[ModelInfo]: ...

    def generate(self, model: str, messages: Sequence[Message], params: Mapping[str, Any]) -> Completion: ...


class _HttpProvider:
    name = "base"

    def __init__(self, api_key: str, *, timeout_sec: float = 120.0, session: Any = None) -> None:
        import requests

        self._key = api_key
        self._timeout = timeout_sec
        self._session = session or requests.Session()

    def _headers(self) -> dict[str, str]:  # pragma: no cover - overridden
        raise NotImplementedError

    def _request(self, method: str, url: str, payload: Any = None) -> Any:
        import requests

        try:
            resp = self._session.request(
                method, url, headers=self._headers(), json=payload, timeout=self._timeout
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            # P4 (audit note 2): network drops and read timeouts are transient, retried inside the attempt budget.
            raise TransientError(f"{self.name}: {type(exc).__name__}: {_redact(str(exc), [self._key])}") from None
        except requests.RequestException as exc:
            raise ProviderError(f"{self.name}: {type(exc).__name__}: {_redact(str(exc), [self._key])}") from None
        if resp.status_code == 429:
            raise RateLimitError(f"{self.name}: HTTP 429 {_redact(_error_message(resp), [self._key])}")
        if resp.status_code >= 500:
            raise TransientError(
                f"{self.name}: HTTP {resp.status_code} {_redact(_error_message(resp), [self._key])}"
            )
        if resp.status_code >= 400:
            raise ProviderError(
                f"{self.name}: HTTP {resp.status_code} {_redact(_error_message(resp), [self._key])}"
            )
        return resp.json()


def _error_message(resp: Any) -> str:
    try:
        body = resp.json()
    except ValueError:
        return (resp.text or "")[:300]
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        quota_ids = [v.get("quotaId") for d in err.get("details") or [] if isinstance(d, dict)
                     for v in d.get("violations") or [] if isinstance(v, dict) and v.get("quotaId")]
        tail = f" [quotaId: {', '.join(quota_ids)}]" if quota_ids else ""
        return str(err.get("status") or err.get("type") or "") + ": " + str(err.get("message") or "")[:300] + tail
    return str(body)[:300]


class GeminiProvider(_HttpProvider):
    name = "gemini"

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._key, "Content-Type": "application/json"}

    def list_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        token = None
        while True:
            url = f"{GEMINI_BASE}/models?pageSize=1000" + (f"&pageToken={token}" if token else "")
            body = self._request("GET", url)
            for m in body.get("models", []):
                models.append(
                    ModelInfo(
                        provider=self.name,
                        id=str(m["name"]).removeprefix("models/"),
                        version=m.get("version"),
                        display_name=m.get("displayName"),
                        input_token_limit=m.get("inputTokenLimit"),
                        output_token_limit=m.get("outputTokenLimit"),
                        methods=tuple(m.get("supportedGenerationMethods") or ()),
                    )
                )
            token = body.get("nextPageToken")
            if not token:
                return models

    def generate(self, model: str, messages: Sequence[Message], params: Mapping[str, Any]) -> Completion:
        system = [m["content"] for m in messages if m["role"] == "system"]
        contents = [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        gen_cfg: dict[str, Any] = {"temperature": params.get("temperature", 0)}
        if params.get("max_output_tokens"):
            gen_cfg["maxOutputTokens"] = int(params["max_output_tokens"])
        if params.get("json"):
            gen_cfg["responseMimeType"] = "application/json"
        if params.get("thinking"):
            gen_cfg["thinkingConfig"] = dict(params["thinking"])
        payload: dict[str, Any] = {"contents": contents, "generationConfig": gen_cfg}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system)}]}
        body = self._request("POST", f"{GEMINI_BASE}/models/{model}:generateContent", payload)
        candidates = body.get("candidates") or []
        if not candidates:
            reason = (body.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(f"gemini: empty response ({reason})")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        usage = body.get("usageMetadata") or {}
        return Completion(
            text=text,
            provider=self.name,
            model=model,
            model_version=body.get("modelVersion"),
            input_tokens=int(usage.get("promptTokenCount") or 0),
            # Thinking tokens are billed as output, so they count against TPM.
            output_tokens=int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
        )


class GroqProvider(_HttpProvider):
    name = "groq"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    def list_models(self) -> list[ModelInfo]:
        body = self._request("GET", f"{GROQ_BASE}/models")
        return [
            ModelInfo(
                provider=self.name,
                id=str(m["id"]),
                version=None,
                display_name=m.get("owned_by"),
                input_token_limit=m.get("context_window"),
                output_token_limit=m.get("max_completion_tokens"),
                active=bool(m.get("active", True)),
            )
            for m in body.get("data", [])
        ]

    def generate(self, model: str, messages: Sequence[Message], params: Mapping[str, Any]) -> Completion:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": params.get("temperature", 0),
        }
        if params.get("max_output_tokens"):
            payload["max_tokens"] = int(params["max_output_tokens"])
        # Opt-in (extension #4, Amendment 5): reasoning effort for reasoning models, and JSON mode for parity with P4.
        if params.get("reasoning_effort"):
            payload["reasoning_effort"] = str(params["reasoning_effort"])
        if params.get("json"):
            payload["response_format"] = {"type": "json_object"}
        body = self._request("POST", f"{GROQ_BASE}/chat/completions", payload)
        choice = (body.get("choices") or [{}])[0]
        usage = body.get("usage") or {}
        served = body.get("model")
        fp = body.get("system_fingerprint")
        return Completion(
            text=str((choice.get("message") or {}).get("content") or ""),
            provider=self.name,
            model=model,
            model_version=f"{served} ({fp})" if fp else served,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )


PROVIDER_CLASSES: dict[str, type[_HttpProvider]] = {"gemini": GeminiProvider, "groq": GroqProvider}


# -- model selection (from the live model lists, never hard-coded ids) ---------

_VERSION_RE = re.compile(r"(\d+(?:\.\d+)?)")
_NON_TEXT = ("embedding", "image", "tts", "audio", "live", "native", "aqa", "imagen", "veo", "robotics",
             "computer-use", "learnlm", "gemma", "whisper", "guard", "orpheus", "playai", "compound",
             "allam", "safeguard", "transcribe", "omni")
_UNSTABLE = ("preview", "exp", "latest")


def _family_version(model_id: str) -> float:
    match = _VERSION_RE.search(model_id)
    return float(match.group(1)) if match else 0.0


def _is_gemini_text(m: ModelInfo) -> bool:
    return (
        m.id.startswith("gemini-")
        and "generateContent" in m.methods
        and not any(tag in m.id for tag in _NON_TEXT)
    )


def select_gemini_models(models: Sequence[ModelInfo]) -> dict[str, Any]:
    """Pick ``llm.model`` and ``llm.long_context_model`` from Gemini's model list.

    Rule, stated so the report can quote it:
    * text-generation Gemini models only (``generateContent``, no embedding /
      image / audio / live / TTS variants), stable ids preferred over
      ``preview`` / ``exp`` / ``latest`` aliases when any stable one exists;
    * ``model`` = the newest family version's ``flash`` tier (not ``lite``):
      the free tier's usable default. If no flash tier exists, the newest model;
    * ``long_context_model`` = the largest ``inputTokenLimit``; ties go to
      ``model`` itself, then to the newest version.
    """
    text = [m for m in models if _is_gemini_text(m)]
    if not text:
        raise LLMError("gemini: no text-generation models listed")
    stable = [m for m in text if not any(tag in m.id for tag in _UNSTABLE)]
    pool = stable or text
    flash = [m for m in pool if "flash" in m.id and "lite" not in m.id]
    ranked = sorted(flash or pool, key=lambda m: (_family_version(m.id), m.id), reverse=True)
    model = ranked[0]
    max_ctx = max(m.input_token_limit or 0 for m in pool)
    longest = [m for m in pool if (m.input_token_limit or 0) == max_ctx]
    long_model = model if model in longest else sorted(
        longest, key=lambda m: (_family_version(m.id), m.id), reverse=True
    )[0]
    return {
        "model": model,
        "long_context_model": long_model,
        "candidates_considered": len(pool),
        "stable_only": bool(stable),
    }


def select_groq_model(models: Sequence[ModelInfo]) -> ModelInfo:
    """Fallback model: an active chat model with the largest context window.

    Ties go to the larger parameter count stated in the id (e.g. ``70b``), then the id.
    """
    chat = [m for m in models if m.active and not any(tag in m.id.lower() for tag in _NON_TEXT)]
    if not chat:
        raise LLMError("groq: no chat models listed")

    def size(m: ModelInfo) -> float:
        found = re.findall(r"(\d+)b\b", m.id.lower())
        return max((float(x) for x in found), default=0.0)

    return sorted(chat, key=lambda m: (m.input_token_limit or 0, size(m), m.id), reverse=True)[0]


# -- client -------------------------------------------------------------------


@dataclass
class ProviderSlot:
    provider: Provider
    #: role -> model id, e.g. {"default": ..., "long_context": ...}
    models: Mapping[str, str]
    rpm: int
    tpm: int


@dataclass
class RunRecord:
    run_id: str
    provider: str | None = None
    status: str = "ok"
    fallback_events: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    http_attempts: int = 0
    cache_hits: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "provider": self.provider,
            "status": self.status,
            "fallback_events": self.fallback_events,
            "http_attempts": self.http_attempts,
            "cache_hits": self.cache_hits,
            "api_calls": sum(1 for c in self.calls if not c["cached"]),
            "input_tokens": sum(c["input_tokens"] for c in self.calls if not c["cached"]),
            "output_tokens": sum(c["output_tokens"] for c in self.calls if not c["cached"]),
            "models": sorted({c["model"] for c in self.calls}),
        }


class QuotaLedger:
    """P4: HTTP attempts per model per **quota day** (Gemini resets daily quotas at midnight Pacific).

    Stored as JSON (``{"<model>": {"<YYYY-MM-DD Pacific>": n}}``). Cache hits never reach it. ``check``
    raises :class:`QuotaPaused` once the soft cap is reached, before any further request is sent.
    """

    TZ = "America/Los_Angeles"

    def __init__(self, path: Path | str, *, soft_cap: int, now: Callable[[], _dt.datetime] | None = None) -> None:
        self.path = Path(path)
        self.soft_cap = int(soft_cap)
        self._now = now or (lambda: _dt.datetime.now(_dt.timezone.utc))

    def _zone(self):
        from zoneinfo import ZoneInfo

        return ZoneInfo(self.TZ)

    def quota_day(self, when: _dt.datetime | None = None) -> str:
        return (when or self._now()).astimezone(self._zone()).date().isoformat()

    def next_reset(self, when: _dt.datetime | None = None) -> _dt.datetime:
        local = (when or self._now()).astimezone(self._zone())
        nxt = _dt.datetime.combine(local.date() + _dt.timedelta(days=1), _dt.time(0, 0), tzinfo=self._zone())
        return nxt

    def next_reset_ist(self, when: _dt.datetime | None = None) -> str:
        from zoneinfo import ZoneInfo

        return self.next_reset(when).astimezone(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M")

    def _load(self) -> dict[str, dict[str, int]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def used(self, model: str, day: str | None = None) -> int:
        return int(self._load().get(model, {}).get(day or self.quota_day(), 0))

    def remaining(self, model: str) -> int:
        return max(0, self.soft_cap - self.used(model))

    def check(self, model: str) -> None:
        if self.used(model) >= self.soft_cap:
            raise QuotaPaused(f"soft cap {self.soft_cap} calls reached for {model} on quota day {self.quota_day()}",
                              resume_after_ist=self.next_reset_ist())

    def record(self, model: str) -> None:
        data = self._load()
        day = self.quota_day()
        data.setdefault(model, {})[day] = int(data.get(model, {}).get(day, 0)) + 1
        atomic_write_text(self.path, json.dumps(data, indent=1, sort_keys=True))


def is_daily_quota(exc: BaseException) -> bool:
    return "PerDay" in str(exc) or "per day" in str(exc).lower()


class _Throttle:
    """Sliding 60 s window over requests and tokens."""

    def __init__(self, rpm: int, tpm: int, clock: Callable[[], float], sleep: Callable[[float], None]):
        self.rpm, self.tpm = rpm, tpm
        self.clock, self.sleep = clock, sleep
        self.events: deque[tuple[float, int]] = deque()

    def _trim(self, now: float) -> None:
        while self.events and now - self.events[0][0] >= 60.0:
            self.events.popleft()

    def wait(self, tokens: int) -> None:
        while True:
            now = self.clock()
            self._trim(now)
            used = sum(t for _, t in self.events)
            if len(self.events) < self.rpm and (not self.events or used + tokens <= self.tpm):
                return
            self.sleep(max(0.05, 60.0 - (now - self.events[0][0])))

    def record(self, tokens: int) -> None:
        self.events.append((self.clock(), tokens))

    def correct_last(self, tokens: int) -> None:
        if self.events:
            ts, _ = self.events[-1]
            self.events[-1] = (ts, tokens)


class LLMClient:
    """One client per system run. See the module docstring for the guarantees."""

    def __init__(
        self,
        slots: Sequence[ProviderSlot],
        *,
        cache_dir: Path | str,
        max_calls: int,
        run_id: str = "adhoc",
        temperature: float = 0.0,
        backoff_attempts: int = 5,
        backoff_initial_sec: float = 2.0,
        backoff_factor: float = 2.0,
        backoff_max_sec: float = 60.0,
        force_provider: str | None = None,
        call_log_path: Path | str | None = None,
        extra_params: Mapping[str, Any] | None = None,
        ledger: QuotaLedger | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        if not slots:
            raise LLMError("LLMClient needs at least one provider")
        self.slots = list(slots)
        if force_provider is not None:
            self.slots = [s for s in self.slots if s.provider.name == force_provider]
            if not self.slots:
                raise LLMError(f"force_provider {force_provider!r} is not configured")
        self.cache_dir = Path(cache_dir)
        self.max_calls = int(max_calls)
        self.temperature = float(temperature)
        self.backoff = (int(backoff_attempts), float(backoff_initial_sec), float(backoff_factor), float(backoff_max_sec))
        self.call_log_path = Path(call_log_path) if call_log_path else None
        #: Sent with every call and part of the cache key (P4: JSON mode, the thinking setting).
        self.extra_params = dict(extra_params or {})
        self.ledger = ledger
        self.clock, self.sleep = clock, sleep
        self.logger = logger or logging.getLogger("llm.client")
        self._throttles = {s.provider.name: _Throttle(s.rpm, s.tpm, clock, sleep) for s in self.slots}
        self._active = 0
        self.run = RunRecord(run_id=run_id, provider=self.slots[0].provider.name if force_provider else None)
        if force_provider is not None:
            self.run.status = f"forced_{force_provider}"

    # -- cache ---------------------------------------------------------------

    @staticmethod
    def cache_key(provider: str, model: str, messages: Sequence[Message], params: Mapping[str, Any]) -> str:
        blob = json.dumps(
            {"provider": provider, "model": model, "messages": [dict(m) for m in messages], "params": dict(params)},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _cache_get(self, key: str) -> Completion | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Completion(**{**data["completion"], "cached": True})

    def _cache_put(self, key: str, completion: Completion) -> None:
        record = {
            "created_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "completion": {**asdict(completion), "cached": False},
        }
        atomic_write_text(self._cache_path(key), json.dumps(record, ensure_ascii=False, indent=1))

    # -- logging -------------------------------------------------------------

    def _log_call(self, completion: Completion, key: str) -> None:
        entry = {
            "run_id": self.run.run_id,
            "provider": completion.provider,
            "model": completion.model,
            "model_version": completion.model_version,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "cached": completion.cached,
            "cache_key": key,
            "utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        }
        self.run.calls.append(entry)
        self.logger.info(
            "llm %s provider=%s model=%s in=%d out=%d",
            "cache-hit" if completion.cached else "call",
            completion.provider, completion.model, completion.input_tokens, completion.output_tokens,
        )
        if self.call_log_path is not None:
            self.call_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.call_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")

    # -- calls ---------------------------------------------------------------

    @property
    def active_provider(self) -> str:
        return self.slots[self._active].provider.name

    def complete(
        self,
        messages: Sequence[Message],
        *,
        role: str = "default",
        max_output_tokens: int | None = None,
    ) -> Completion:
        while True:
            slot = self.slots[self._active]
            try:
                return self._complete_on(slot, messages, role, max_output_tokens)
            except RateLimitError as exc:
                self._on_quota(slot, exc)

    def _on_quota(self, slot: ProviderSlot, exc: RateLimitError) -> None:
        has_next = self._active + 1 < len(self.slots)
        if not has_next:
            raise exc
        nxt = self.slots[self._active + 1].provider.name
        event = {"from": slot.provider.name, "to": nxt, "reason": str(exc)[:200],
                 "after_answers": len(self.run.calls)}
        if self.run.provider is None:
            event["mid_run"] = False
            self.run.fallback_events.append(event)
            self.run.status = f"fallback_{nxt}_from_start"
            self.logger.warning("llm: %s rate-limited before its first answer; whole run moves to %s",
                                slot.provider.name, nxt)
            self._active += 1
            return
        event["mid_run"] = True
        self.run.fallback_events.append(event)
        self.run.status = "fallback_needed_mid_run"
        raise ProviderSwitchMidRun(
            f"{slot.provider.name} rate-limited after {len(self.run.calls)} answers in run "
            f"{self.run.run_id!r}; providers are never mixed, so rerun the whole run with "
            f"force_provider={nxt!r}"
        ) from exc

    def _complete_on(
        self, slot: ProviderSlot, messages: Sequence[Message], role: str, max_output_tokens: int | None
    ) -> Completion:
        name = slot.provider.name
        if role not in slot.models:
            raise LLMError(f"{name}: no model configured for role {role!r}")
        model = slot.models[role]
        params: dict[str, Any] = {"temperature": self.temperature, **self.extra_params}
        if max_output_tokens:
            params["max_output_tokens"] = int(max_output_tokens)
        key = self.cache_key(name, model, messages, params)

        cached = self._cache_get(key)
        if cached is not None:
            self.run.cache_hits += 1
            self.run.provider = self.run.provider or name
            self._log_call(cached, key)
            return cached

        if getattr(self, "cache_only", False):
            raise CacheMiss(f"{name}: prompt not cached (cache-only mode)")
        attempts, delay, factor, max_delay = self.backoff
        # Conservative (chars / 3): RBI text tokenises denser than chars / 4, and with ~150K-token long-context
        # prompts an undercount lets two requests land in one of the provider's per-minute input-token buckets.
        estimate = sum(len(m["content"]) for m in messages) // 3 + int(max_output_tokens or 0)
        throttle = self._throttles[name]
        for attempt in range(1, attempts + 1):
            if self.run.http_attempts >= self.max_calls:
                raise CallCapReached(f"llm.max_calls={self.max_calls} reached in run {self.run.run_id!r}")
            if self.ledger is not None:
                self.ledger.check(model)
            throttle.wait(estimate)
            throttle.record(estimate)
            self.run.http_attempts += 1
            if self.ledger is not None:
                self.ledger.record(model)
            try:
                completion = slot.provider.generate(model, messages, params)
            except (RateLimitError, TransientError) as exc:
                if self.ledger is not None and isinstance(exc, RateLimitError) and is_daily_quota(exc):
                    raise QuotaPaused(f"{name} daily quota reached: {str(exc)[:200]}",
                                      resume_after_ist=self.ledger.next_reset_ist()) from exc
                if attempt == attempts:
                    raise
                wait = min(max_delay, delay * factor ** (attempt - 1)) * (1 + 0.25 * random.random())
                self.logger.warning("llm: %s %s, backing off %.1fs (attempt %d/%d)",
                                    name, type(exc).__name__, wait, attempt, attempts)
                self.sleep(wait)
                continue
            throttle.correct_last(completion.input_tokens + completion.output_tokens)
            self.run.provider = self.run.provider or name
            self._cache_put(key, completion)
            self._log_call(completion, key)
            return completion
        raise AssertionError("unreachable")  # pragma: no cover


# -- factory ------------------------------------------------------------------


def build_client(
    cfg: Mapping[str, Any],
    resolver: Any,
    *,
    run_id: str,
    env_file: Path | str | None = None,
    force_provider: str | None = None,
    verify_models: bool = True,
    model: str | None = None,
    long_context_model: str | None = None,
    rpm: int | None = None,
    tpm: int | None = None,
    extra_params: Mapping[str, Any] | None = None,
    ledger: QuotaLedger | None = None,
    timeout_sec: float | None = None,
    backoff_attempts: int | None = None,
    logger: logging.Logger | None = None,
) -> LLMClient:
    """Build the configured client. The primary key is required; the fallback is optional."""
    load_env(env_file)
    block = get_required(cfg, "llm")
    primary = str(get_required(cfg, "llm.primary"))
    fallback = block.get("fallback")
    if fallback in (None, "", "none"):
        fallback = None  # P4: no provider fallback; a quota error pauses the run instead
    timeout = float(timeout_sec or block.get("request_timeout_sec", 120))

    slots: list[ProviderSlot] = []
    for name in [primary] + ([str(fallback)] if fallback else []):
        pblock = get_required(cfg, f"llm.providers.{name}")
        try:
            key = require_key(str(pblock.get("key_env", KEY_ENV[name])))
        except MissingKeyError:
            if name == primary and force_provider != fallback:
                raise
            (logger or logging.getLogger("llm.client")).warning("llm: %s key missing/empty; no fallback", name)
            continue
        # Primary ids: llm.model / llm.long_context_model; fallback: llm.fallback_*.
        prefix = "" if name == primary else "fallback_"
        models = {"default": str(model or get_required(cfg, f"llm.{prefix}model"))}
        if long_context_model or block.get(f"{prefix}long_context_model"):
            models["long_context"] = str(long_context_model or block[f"{prefix}long_context_model"])
        provider = PROVIDER_CLASSES[name](key, timeout_sec=timeout)
        if verify_models:
            # Startup check against the live list: a configured id the API no longer serves fails here.
            listed = {m.id for m in provider.list_models()}
            missing = sorted(set(models.values()) - listed)
            if missing:
                raise LLMError(f"{name}: configured model(s) not listed by the API: {missing}; "
                               "rerun scripts/run_llm_setup.py")
        slots.append(
            ProviderSlot(
                provider=provider,
                models=models,
                rpm=int(rpm or get_required(cfg, f"llm.providers.{name}.rpm")),
                tpm=int(tpm or get_required(cfg, f"llm.providers.{name}.tpm")),
            )
        )
    backoff = block.get("backoff") or {}
    return LLMClient(
        slots,
        cache_dir=resolver.write_dir("llm_cache"),
        max_calls=int(get_required(cfg, "llm.max_calls")),
        run_id=run_id,
        temperature=float(block.get("temperature", 0)),
        backoff_attempts=int(backoff_attempts or backoff.get("attempts", 5)),
        backoff_initial_sec=float(backoff.get("initial_delay_sec", 2.0)),
        backoff_factor=float(backoff.get("factor", 2.0)),
        backoff_max_sec=float(backoff.get("max_delay_sec", 60.0)),
        force_provider=force_provider,
        call_log_path=resolver.write_path("logs", "llm_calls.jsonl"),
        extra_params=extra_params,
        ledger=ledger,
        logger=logger,
    )
