"""Retry with exponential backoff and jitter.

Used by anything that touches the network. The scraper is the obvious consumer,
but Kaggle Dataset reads and any future API calls need the same behaviour, so it
lives in the shared foundation rather than in one branch.

Both ``sleep`` and the jitter source are injectable, so tests exercise the real
backoff arithmetic without spending real seconds.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, TypeVar

from src.common.errors import ConfigError, RetryExhaustedError

T = TypeVar("T")

#: Exceptions retried when a caller does not specify. Deliberately narrow:
#: retrying a ``ValueError`` or a ``KeyError`` just hides a bug.
DEFAULT_RETRY_ON: tuple[type[BaseException], ...] = (OSError, TimeoutError, ConnectionError)


@dataclass(frozen=True)
class RetryPolicy:
    """Backoff parameters.

    Attributes:
        attempts: Total attempts including the first. Must be >= 1.
        initial_delay_sec: Delay before the second attempt.
        backoff_factor: Multiplier applied to the delay after each failure.
        max_delay_sec: Ceiling applied to each delay before jitter.
        jitter: Fraction of the delay added at random, in ``[0, 1]``. Prevents
            several workers retrying in lockstep.
    """

    attempts: int = 4
    initial_delay_sec: float = 1.0
    backoff_factor: float = 2.0
    max_delay_sec: float = 30.0
    jitter: float = 0.25

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ConfigError(f"RetryPolicy.attempts must be >= 1, got {self.attempts}")
        if self.initial_delay_sec < 0:
            raise ConfigError("RetryPolicy.initial_delay_sec must be >= 0")
        if self.backoff_factor < 1:
            raise ConfigError(f"RetryPolicy.backoff_factor must be >= 1, got {self.backoff_factor}")
        if self.max_delay_sec < 0:
            raise ConfigError("RetryPolicy.max_delay_sec must be >= 0")
        if not 0 <= self.jitter <= 1:
            raise ConfigError(f"RetryPolicy.jitter must be in [0, 1], got {self.jitter}")

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> "RetryPolicy":
        """Build a policy from ``network.retry`` in a loaded config."""
        network = cfg.get("network")
        block: Mapping[str, Any] = {}
        if isinstance(network, Mapping) and isinstance(network.get("retry"), Mapping):
            block = network["retry"]
        return cls(
            attempts=int(block.get("attempts", cls.attempts)),
            initial_delay_sec=float(block.get("initial_delay_sec", cls.initial_delay_sec)),
            backoff_factor=float(block.get("backoff_factor", cls.backoff_factor)),
            max_delay_sec=float(block.get("max_delay_sec", cls.max_delay_sec)),
            jitter=float(block.get("jitter", cls.jitter)),
        )

    def delay_for(self, attempt: int, *, rng: Callable[[], float] | None = None) -> float:
        """Delay in seconds before the attempt numbered ``attempt`` (1-based).

        ``delay_for(1)`` is 0 — the first attempt is immediate.
        """
        if attempt <= 1:
            return 0.0
        base = self.initial_delay_sec * (self.backoff_factor ** (attempt - 2))
        base = min(base, self.max_delay_sec)
        if self.jitter:
            draw = rng() if rng is not None else random.random()
            base += base * self.jitter * draw
        return base


def retry_call(
    fn: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    retry_on: Iterable[type[BaseException]] | None = None,
    give_up_on: Iterable[type[BaseException]] | None = None,
    description: str = "operation",
    sleep_fn: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] | None = None,
    logger: Any = None,
) -> T:
    """Call ``fn`` with retries, returning its result.

    Args:
        fn: Zero-argument callable. Wrap arguments with :func:`functools.partial`.
        policy: Backoff parameters. Defaults to :class:`RetryPolicy` defaults.
        retry_on: Exception types that trigger a retry. Defaults to
            :data:`DEFAULT_RETRY_ON`.
        give_up_on: Exception types that abort immediately even if they also
            match ``retry_on``. Checked first. Use for known-permanent failures
            such as a 404.
        description: Human-readable label used in log lines and the final error.
        sleep_fn: Sleep implementation. Tests pass a recorder.
        rng: Zero-argument source of floats in ``[0, 1)`` for jitter.
        logger: Optional logger receiving one warning per failed attempt.

    Raises:
        RetryExhaustedError: Every attempt failed. Chained from the last error.
        BaseException: Anything not matching ``retry_on``, re-raised unchanged.
    """
    policy = policy or RetryPolicy()
    retryable = tuple(retry_on) if retry_on is not None else DEFAULT_RETRY_ON
    permanent = tuple(give_up_on) if give_up_on is not None else ()

    last_exc: BaseException | None = None

    for attempt in range(1, policy.attempts + 1):
        delay = policy.delay_for(attempt, rng=rng)
        if delay > 0:
            sleep_fn(delay)
        try:
            return fn()
        except permanent:
            raise
        except retryable as exc:
            last_exc = exc
            if logger is not None:
                logger.warning(
                    "%s failed (attempt %d/%d): %s: %s",
                    description,
                    attempt,
                    policy.attempts,
                    type(exc).__name__,
                    exc,
                )

    raise RetryExhaustedError(
        f"{description} failed after {policy.attempts} attempt(s): "
        f"{type(last_exc).__name__}: {last_exc}",
        attempts=policy.attempts,
        last_exception=last_exc,
    ) from last_exc


def with_retry(
    policy: RetryPolicy | None = None, **kwargs: Any
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator form of :func:`retry_call`."""
    import functools

    options = dict(kwargs)
    override = options.pop("description", None)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        description = override or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **fn_kwargs: Any) -> T:
            return retry_call(
                functools.partial(fn, *args, **fn_kwargs),
                policy=policy,
                description=description,
                **options,
            )

        return wrapper

    return decorator
