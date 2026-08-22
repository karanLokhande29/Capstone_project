"""Retry/backoff. Sleep and jitter are injected, so the arithmetic is tested
without spending the seconds."""

from __future__ import annotations

import pytest

from src.common.errors import ConfigError, RetryExhaustedError
from src.common.retry import RetryPolicy, retry_call, with_retry


class Recorder:
    """Stands in for ``time.sleep`` and records what it was asked to wait."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


# -- policy -------------------------------------------------------------------


def test_policy_from_config(base_config):
    policy = RetryPolicy.from_config(base_config)
    assert policy.attempts == 3
    assert policy.backoff_factor == 2.0


def test_policy_from_config_uses_defaults_when_absent():
    policy = RetryPolicy.from_config({})
    assert policy.attempts == RetryPolicy.attempts


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempts": 0},
        {"backoff_factor": 0.5},
        {"jitter": 1.5},
        {"jitter": -0.1},
        {"initial_delay_sec": -1},
        {"max_delay_sec": -1},
    ],
)
def test_invalid_policy_rejected(kwargs):
    with pytest.raises(ConfigError):
        RetryPolicy(**kwargs)


def test_first_attempt_is_immediate():
    assert RetryPolicy().delay_for(1) == 0.0


def test_delays_grow_exponentially():
    policy = RetryPolicy(initial_delay_sec=1.0, backoff_factor=2.0, jitter=0.0)
    assert [policy.delay_for(n) for n in (2, 3, 4)] == [1.0, 2.0, 4.0]


def test_delay_is_capped():
    policy = RetryPolicy(initial_delay_sec=1.0, backoff_factor=10.0, max_delay_sec=5.0, jitter=0.0)
    assert policy.delay_for(5) == 5.0


def test_jitter_only_ever_adds():
    policy = RetryPolicy(initial_delay_sec=1.0, backoff_factor=2.0, jitter=0.5)
    assert policy.delay_for(2, rng=lambda: 0.0) == 1.0
    assert policy.delay_for(2, rng=lambda: 1.0) == 1.5


# -- retry_call ---------------------------------------------------------------


def test_returns_immediately_on_success():
    sleeper = Recorder()
    assert retry_call(lambda: "ok", sleep_fn=sleeper) == "ok"
    assert sleeper.delays == [0.0] or sleeper.delays == []


def test_succeeds_after_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    result = retry_call(
        flaky,
        policy=RetryPolicy(attempts=5, initial_delay_sec=0.0, jitter=0.0),
        sleep_fn=Recorder(),
    )
    assert result == "ok"
    assert calls["n"] == 3


def test_exhaustion_raises_with_attempt_count_and_cause():
    def always_fails():
        raise ConnectionError("down")

    with pytest.raises(RetryExhaustedError) as exc:
        retry_call(
            always_fails,
            policy=RetryPolicy(attempts=3, initial_delay_sec=0.0, jitter=0.0),
            description="fetch listing",
            sleep_fn=Recorder(),
        )
    assert exc.value.attempts == 3
    assert isinstance(exc.value.last_exception, ConnectionError)
    assert isinstance(exc.value.__cause__, ConnectionError)
    assert "fetch listing" in str(exc.value)


def test_non_retryable_exception_propagates_unchanged():
    """Retrying a programming error hides the bug; it must surface as itself."""
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise ValueError("this is a bug, not a blip")

    with pytest.raises(ValueError, match="bug"):
        retry_call(bad, policy=RetryPolicy(attempts=5), sleep_fn=Recorder())
    assert calls["n"] == 1


def test_give_up_on_wins_over_retry_on():
    """A known-permanent failure such as a 404 should not be retried four times."""
    calls = {"n": 0}

    class NotFound(OSError):
        pass

    def missing():
        calls["n"] += 1
        raise NotFound("404")

    with pytest.raises(NotFound):
        retry_call(
            missing,
            policy=RetryPolicy(attempts=4, initial_delay_sec=0.0, jitter=0.0),
            give_up_on=[NotFound],
            sleep_fn=Recorder(),
        )
    assert calls["n"] == 1


def test_custom_retry_on():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise KeyError("missing key")
        return "ok"

    assert (
        retry_call(
            flaky,
            policy=RetryPolicy(attempts=3, initial_delay_sec=0.0, jitter=0.0),
            retry_on=[KeyError],
            sleep_fn=Recorder(),
        )
        == "ok"
    )


def test_sleeps_between_attempts_not_before_the_first():
    sleeper = Recorder()

    def always_fails():
        raise TimeoutError("slow")

    with pytest.raises(RetryExhaustedError):
        retry_call(
            always_fails,
            policy=RetryPolicy(attempts=3, initial_delay_sec=1.0, backoff_factor=2.0, jitter=0.0),
            sleep_fn=sleeper,
        )
    assert [d for d in sleeper.delays if d > 0] == [1.0, 2.0]


def test_logger_receives_one_warning_per_failed_attempt():
    class FakeLogger:
        def __init__(self):
            self.warnings = []

        def warning(self, *args):
            self.warnings.append(args)

    logger = FakeLogger()

    def always_fails():
        raise ConnectionError("down")

    with pytest.raises(RetryExhaustedError):
        retry_call(
            always_fails,
            policy=RetryPolicy(attempts=3, initial_delay_sec=0.0, jitter=0.0),
            sleep_fn=Recorder(),
            logger=logger,
        )
    assert len(logger.warnings) == 3


# -- decorator ----------------------------------------------------------------


def test_decorator_retries_and_preserves_metadata():
    calls = {"n": 0}

    @with_retry(RetryPolicy(attempts=3, initial_delay_sec=0.0, jitter=0.0), sleep_fn=Recorder())
    def fetch(url: str) -> str:
        """Fetch a URL."""
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("blip")
        return url

    assert fetch("https://example.org") == "https://example.org"
    assert fetch.__name__ == "fetch"
    assert fetch.__doc__ == "Fetch a URL."


def test_decorator_is_reusable_across_calls():
    """Options must not be consumed by the first invocation."""

    @with_retry(RetryPolicy(attempts=2, initial_delay_sec=0.0, jitter=0.0), sleep_fn=Recorder())
    def ok() -> int:
        return 1

    assert ok() == 1
    assert ok() == 1
