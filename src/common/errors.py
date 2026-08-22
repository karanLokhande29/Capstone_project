"""Exception hierarchy for the shared foundation.

Every error raised by :mod:`src.common` derives from :class:`FoundationError`, so
Phase 1 branches can catch foundation failures as a single category without
catching unrelated exceptions from their own code.
"""

from __future__ import annotations


class FoundationError(Exception):
    """Base class for every error raised by the shared foundation."""


class ConfigError(FoundationError):
    """Configuration is missing, malformed, or fails validation.

    Raised eagerly and loudly. The foundation never silently substitutes a
    default for a required configuration value.
    """


class PathResolutionError(FoundationError):
    """A logical path key could not be resolved to a real filesystem location."""


class IOFormatError(FoundationError):
    """A file exists but its contents could not be parsed in the expected format."""


class RetryExhaustedError(FoundationError):
    """A retried operation failed on every attempt.

    The final underlying exception is available as :attr:`last_exception` and is
    also chained via ``raise ... from``.
    """

    def __init__(self, message: str, *, attempts: int, last_exception: BaseException | None = None):
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception


class CacheError(FoundationError):
    """A cache read or write could not be completed."""


class SchemaValidationError(FoundationError):
    """A record does not satisfy its declared schema.

    The individual failures are available as :attr:`errors`.
    """

    def __init__(self, message: str, *, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []
