"""Shared utilities every branch depends on.

Import from this package rather than reimplementing. Anything added here becomes
a shared dependency for all three Phase 1 branches, so additions belong on the
base branch and need agreement, not a drive-by commit from one branch.
"""

from src.common.cache import ArtifactCache, CacheEntry
from src.common.config import (
    DEFAULT_CONFIG_PATH,
    REPO_ROOT,
    get_required,
    load_config,
    validate_config,
)
from src.common.errors import (
    CacheError,
    ConfigError,
    FoundationError,
    IOFormatError,
    PathResolutionError,
    RetryExhaustedError,
    SchemaValidationError,
)
from src.common.io_helpers import (
    atomic_write_bytes,
    atomic_write_text,
    count_jsonl,
    iter_jsonl,
    read_json,
    read_jsonl,
    read_text,
    write_json,
    write_jsonl,
    write_text,
)
from src.common.logging_setup import get_logger, reset_logger
from src.common.paths import Mode, PathResolver, detect_mode
from src.common.retry import RetryPolicy, retry_call, with_retry

__all__ = [
    "ArtifactCache",
    "CacheEntry",
    "CacheError",
    "ConfigError",
    "DEFAULT_CONFIG_PATH",
    "FoundationError",
    "IOFormatError",
    "Mode",
    "PathResolutionError",
    "PathResolver",
    "REPO_ROOT",
    "RetryExhaustedError",
    "RetryPolicy",
    "SchemaValidationError",
    "atomic_write_bytes",
    "atomic_write_text",
    "count_jsonl",
    "detect_mode",
    "get_logger",
    "get_required",
    "iter_jsonl",
    "load_config",
    "read_json",
    "read_jsonl",
    "read_text",
    "reset_logger",
    "retry_call",
    "validate_config",
    "with_retry",
    "write_json",
    "write_jsonl",
    "write_text",
]
