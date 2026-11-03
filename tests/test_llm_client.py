"""P3-001 LLM client, with fake providers only (no network)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.llm import client as L

SECRET = "sk-test-SECRET-value-1234567890"


class FakeProvider:
    def __init__(self, name: str, *, fail_with: list[Exception] | None = None, text: str = "OK") -> None:
        self.name = name
        self.fail_with = list(fail_with or [])
        self.text = text
        self.calls = 0

    def list_models(self):
        return []

    def generate(self, model, messages, params):
        self.calls += 1
        if self.fail_with:
            raise self.fail_with.pop(0)
        return L.Completion(text=self.text, provider=self.name, model=model, model_version=f"{model}-v",
                            input_tokens=7, output_tokens=2)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, secs: float) -> None:
        self.slept.append(secs)
        self.t += secs


def make_client(tmp_path: Path, providers, *, max_calls: int = 10, rpm: int = 100, tpm: int = 10**6,
                attempts: int = 3, **kw) -> tuple[L.LLMClient, FakeClock]:
    clock = FakeClock()
    slots = [L.ProviderSlot(p, {"default": f"{p.name}-model"}, rpm=rpm, tpm=tpm) for p in providers]
    client = L.LLMClient(slots, cache_dir=tmp_path / "cache", max_calls=max_calls, backoff_attempts=attempts,
                         backoff_initial_sec=1.0, call_log_path=tmp_path / "calls.jsonl", clock=clock,
                         sleep=clock.sleep, **kw)
    return client, clock


MSG = [{"role": "user", "content": "hello"}]


def test_cache_hit_skips_the_provider(tmp_path):
    prov = FakeProvider("gemini")
    client, _ = make_client(tmp_path, [prov])
    first = client.complete(MSG)
    second = client.complete(MSG)
    assert prov.calls == 1
    assert not first.cached and second.cached
    assert second.text == first.text and second.model_version == first.model_version
    assert client.run.cache_hits == 1 and client.run.http_attempts == 1
    # A fresh client (a later run) is served from disk too.
    again, _ = make_client(tmp_path, [prov])
    assert again.complete(MSG).cached and prov.calls == 1


def test_cache_key_covers_provider_model_messages_params():
    base = L.LLMClient.cache_key("gemini", "m", MSG, {"temperature": 0})
    assert base != L.LLMClient.cache_key("groq", "m", MSG, {"temperature": 0})
    assert base != L.LLMClient.cache_key("gemini", "m2", MSG, {"temperature": 0})
    assert base != L.LLMClient.cache_key("gemini", "m", [{"role": "user", "content": "x"}], {"temperature": 0})
    assert base != L.LLMClient.cache_key("gemini", "m", MSG, {"temperature": 0, "max_output_tokens": 5})
    assert base == L.LLMClient.cache_key("gemini", "m", [dict(MSG[0])], {"temperature": 0})


def test_temperature_is_zero(tmp_path):
    seen = {}

    class Spy(FakeProvider):
        def generate(self, model, messages, params):
            seen.update(params)
            return super().generate(model, messages, params)

    client, _ = make_client(tmp_path, [Spy("gemini")])
    client.complete(MSG)
    assert seen["temperature"] == 0


def test_call_cap_is_hard(tmp_path):
    prov = FakeProvider("gemini")
    client, _ = make_client(tmp_path, [prov], max_calls=2)
    client.complete([{"role": "user", "content": "a"}])
    client.complete([{"role": "user", "content": "b"}])
    with pytest.raises(L.CallCapReached):
        client.complete([{"role": "user", "content": "c"}])
    assert prov.calls == 2
    # Cache hits do not count against the cap.
    assert client.complete([{"role": "user", "content": "a"}]).cached


def test_retries_count_against_the_cap(tmp_path):
    prov = FakeProvider("gemini", fail_with=[L.RateLimitError("429")] * 5)
    client, _ = make_client(tmp_path, [prov], max_calls=2, attempts=5)
    with pytest.raises(L.CallCapReached):
        client.complete(MSG)
    assert prov.calls == 2


def test_backoff_on_429_is_exponential(tmp_path, monkeypatch):
    monkeypatch.setattr(L.random, "random", lambda: 0.0)
    prov = FakeProvider("gemini", fail_with=[L.RateLimitError("429"), L.RateLimitError("429")])
    client, clock = make_client(tmp_path, [prov], attempts=3)
    assert client.complete(MSG).text == "OK"
    assert clock.slept == [1.0, 2.0]


def test_5xx_is_retried_but_never_falls_back(tmp_path):
    primary = FakeProvider("gemini", fail_with=[L.TransientError("503")] * 3)
    fallback = FakeProvider("groq")
    client, _ = make_client(tmp_path, [primary, fallback], attempts=3)
    with pytest.raises(L.TransientError):
        client.complete(MSG)
    assert fallback.calls == 0 and client.run.fallback_events == []


def test_fallback_before_first_answer_moves_the_whole_run(tmp_path):
    primary = FakeProvider("gemini", fail_with=[L.RateLimitError("quota")] * 3)
    fallback = FakeProvider("groq")
    client, _ = make_client(tmp_path, [primary, fallback], attempts=3)
    out = client.complete(MSG)
    assert out.provider == "groq"
    assert client.run.provider == "groq"
    assert client.run.status == "fallback_groq_from_start"
    assert client.run.fallback_events[0]["mid_run"] is False
    # Every later call stays on the fallback, even once the primary would answer again.
    client.complete([{"role": "user", "content": "next"}])
    assert primary.calls == 3 and {c["provider"] for c in client.run.calls} == {"groq"}


def test_providers_never_mix_within_a_run(tmp_path):
    primary = FakeProvider("gemini")
    fallback = FakeProvider("groq")
    client, _ = make_client(tmp_path, [primary, fallback], attempts=2)
    client.complete(MSG)
    primary.fail_with = [L.RateLimitError("quota")] * 2
    with pytest.raises(L.ProviderSwitchMidRun):
        client.complete([{"role": "user", "content": "second"}])
    assert fallback.calls == 0
    assert client.run.status == "fallback_needed_mid_run"
    assert client.run.fallback_events[-1]["mid_run"] is True
    assert {c["provider"] for c in client.run.calls} == {"gemini"}


def test_a_cache_hit_also_locks_the_run(tmp_path):
    primary = FakeProvider("gemini")
    client, _ = make_client(tmp_path, [primary, FakeProvider("groq")], attempts=1)
    client.complete(MSG)
    later, _ = make_client(tmp_path, [primary, FakeProvider("groq")], attempts=1)
    assert later.complete(MSG).cached and later.run.provider == "gemini"
    primary.fail_with = [L.RateLimitError("quota")]
    with pytest.raises(L.ProviderSwitchMidRun):
        later.complete([{"role": "user", "content": "new"}])


def test_forced_fallback_run(tmp_path):
    client, _ = make_client(tmp_path, [FakeProvider("gemini"), FakeProvider("groq")], force_provider="groq")
    assert client.complete(MSG).provider == "groq"
    assert client.run.status == "forced_groq"


def test_throttle_waits_for_the_minute_window(tmp_path):
    client, clock = make_client(tmp_path, [FakeProvider("gemini")], rpm=2)
    for i in range(3):
        client.complete([{"role": "user", "content": str(i)}])
    assert clock.slept and clock.t >= 60.0


def test_call_log_records_provider_model_tokens(tmp_path):
    client, _ = make_client(tmp_path, [FakeProvider("gemini")])
    client.complete(MSG)
    entry = json.loads((tmp_path / "calls.jsonl").read_text().splitlines()[0])
    assert entry["provider"] == "gemini" and entry["model"] == "gemini-model"
    assert entry["input_tokens"] == 7 and entry["output_tokens"] == 2
    assert client.run.summary()["api_calls"] == 1


# -- keys -----------------------------------------------------------------------


def test_env_file_loading_and_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=from-file\nGROQ_API_KEY=groq-from-file\n")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "already-set")
    assert L.load_env(env) is True
    assert L.require_key("GEMINI_API_KEY") == "from-file"
    assert L.require_key("GROQ_API_KEY") == "already-set"  # the environment wins
    assert L.load_env(tmp_path / "missing.env") is False


def test_missing_key_message_names_the_variable_only(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "   ")
    with pytest.raises(L.MissingKeyError) as exc:
        L.require_key("GEMINI_API_KEY")
    assert str(exc.value) == "GEMINI_API_KEY missing/empty"


class _Resp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class _Session:
    def __init__(self, resp: _Resp) -> None:
        self.resp = resp
        self.seen: list[dict] = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        self.seen.append({"url": url, "headers": headers})
        return self.resp


def test_provider_errors_are_redacted_and_keys_stay_out_of_urls():
    body = {"error": {"status": "INVALID", "message": f"bad key {SECRET}"}}
    for cls in (L.GeminiProvider, L.GroqProvider):
        session = _Session(_Resp(400, body))
        prov = cls(SECRET, session=session)
        with pytest.raises(L.ProviderError) as exc:
            prov.generate("m", MSG, {"temperature": 0})
        assert SECRET not in str(exc.value) and "***" in str(exc.value)
        assert all(SECRET not in s["url"] for s in session.seen)


def test_no_key_is_ever_written_or_printed(tmp_path, monkeypatch, capsys, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    ok = {"candidates": [{"content": {"parts": [{"text": "OK"}]}}], "modelVersion": "v",
          "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1}}
    session = _Session(_Resp(200, ok))
    prov = L.GeminiProvider(L.require_key("GEMINI_API_KEY"), session=session)
    caplog.set_level(logging.DEBUG)
    client, _ = make_client(tmp_path, [prov])
    client.logger.setLevel(logging.DEBUG)
    client.complete(MSG)
    client.complete(MSG)
    assert session.seen[0]["headers"]["x-goog-api-key"] == SECRET  # only ever in a header
    out = capsys.readouterr()
    blobs = [out.out, out.err, caplog.text, json.dumps(client.run.summary()), json.dumps(client.run.calls)]
    blobs += [p.read_text() for p in tmp_path.rglob("*") if p.is_file()]
    assert all(SECRET not in b for b in blobs)


# -- model selection --------------------------------------------------------------


def _m(i, ctx=1_000_000, methods=("generateContent",), provider="gemini"):
    return L.ModelInfo(provider=provider, id=i, version="v", input_token_limit=ctx, methods=methods)


def test_gemini_selection_rule():
    models = [_m("gemini-2.5-flash"), _m("gemini-3.1-flash"), _m("gemini-3.1-flash-lite"),
              _m("gemini-3.2-flash-preview"), _m("gemini-3.1-pro", ctx=2_000_000),
              _m("gemini-embedding-2", methods=("embedContent",)), _m("gemini-3.1-flash-tts")]
    pick = L.select_gemini_models(models)
    assert pick["model"].id == "gemini-3.1-flash"  # newest stable flash, not lite / preview
    assert pick["long_context_model"].id == "gemini-3.1-pro"  # largest input limit


def test_gemini_long_context_tie_goes_to_the_text_model():
    pick = L.select_gemini_models([_m("gemini-3.1-flash"), _m("gemini-3.1-pro")])
    assert pick["long_context_model"].id == "gemini-3.1-flash"


def test_groq_selection_rule():
    models = [_m("whisper-large-v3", ctx=448, provider="groq"), _m("meta/llama-8b", ctx=131072, provider="groq"),
              _m("vendor/model-70b", ctx=131072, provider="groq"), _m("x/guard-2", ctx=10**6, provider="groq")]
    assert L.select_groq_model(models).id == "vendor/model-70b"


def test_network_errors_are_transient_and_capped_at_three_attempts(tmp_path):
    """Audit note 2: a connection drop or read timeout is retried inside the attempt budget, never beyond it."""
    import requests

    class Boom:
        def request(self, *a, **k):
            raise requests.ConnectionError("No route to host")

    prov = L.GeminiProvider(SECRET, session=Boom())
    with pytest.raises(L.TransientError):
        prov.generate("m", MSG, {"temperature": 0})

    flaky = FakeProvider("gemini", fail_with=[L.TransientError("503")] * 5)
    led = L.QuotaLedger(tmp_path / "q.json", soft_cap=100)
    client, _ = make_client(tmp_path, [flaky], attempts=3, ledger=led)
    with pytest.raises(L.TransientError):
        client.complete(MSG)
    assert flaky.calls == 3 and led.used("gemini-model") == 3  # every attempt, 503s included, is in the ledger
