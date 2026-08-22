"""Content-addressed cache backed by the dual-mode filesystem.

The point of this cache is that a Kaggle notebook re-run must not re-download
381 PDFs. It reads through the same root ordering as
:class:`~src.common.paths.PathResolver`, which gives the behaviour Kaggle needs:

* **Reads** hit attached Kaggle Datasets (read-only) first, then the working
  directory. A corpus harvested in a previous session and saved as a Dataset is
  therefore a cache hit in the next session.
* **Writes** always go to ``/kaggle/working/…``. The user then saves that
  directory as a new Dataset version through the Kaggle UI, and the next run
  reads it back as read-only input.

Nothing here writes to local disk when running on Kaggle, and nothing assumes a
writable input mount.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.common.errors import CacheError, IOFormatError
from src.common.io_helpers import atomic_write_bytes, read_bytes, read_json, write_json
from src.common.paths import PathResolver

#: Cache keys are sharded into subdirectories by this prefix length. A single
#: directory holding tens of thousands of files is slow to list on Kaggle.
SHARD_WIDTH = 2


@dataclass(frozen=True)
class CacheEntry:
    """Where a cache lookup landed."""

    key: str
    path: Path
    #: True when the hit came from a read-only input root (a Kaggle Dataset).
    from_input: bool


class ArtifactCache:
    """Namespaced, content-addressed cache over :class:`PathResolver`.

    Args:
        resolver: Active path resolver.
        namespace: Prefix isolating one consumer's entries from another's, so
            three branches sharing one Kaggle Dataset never collide.
        enabled: When false, every lookup misses and every store is a no-op.
            Wired to ``cache.enabled`` in config.
        max_age_days: Entries older than this are treated as misses. ``None``
            means never expire, which is correct for immutable source documents.
        path_key: Logical path key the cache lives under.
        logger: Optional logger for hit/miss lines.
    """

    def __init__(
        self,
        resolver: PathResolver,
        *,
        namespace: str = "default",
        enabled: bool = True,
        max_age_days: float | None = None,
        path_key: str = "cache",
        logger: Any = None,
    ) -> None:
        if not namespace:
            raise CacheError("ArtifactCache requires a non-empty namespace")
        self.resolver = resolver
        self.namespace = namespace
        self.enabled = enabled
        self.max_age_days = max_age_days
        self.path_key = path_key
        self.logger = logger

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        cfg: Mapping[str, Any],
        resolver: PathResolver,
        *,
        namespace: str | None = None,
        logger: Any = None,
    ) -> "ArtifactCache":
        """Build a cache from the ``cache`` section of a loaded config."""
        block = cfg.get("cache")
        if not isinstance(block, Mapping):
            raise CacheError("config is missing the 'cache' section")
        return cls(
            resolver,
            namespace=namespace or str(block.get("namespace") or "default"),
            enabled=bool(block.get("enabled", True)),
            max_age_days=block.get("max_age_days"),
            logger=logger,
        )

    # -- keys -----------------------------------------------------------------

    @staticmethod
    def key_for(*parts: str) -> str:
        """Derive a stable cache key from its identifying parts.

        Uses SHA-256 over NUL-joined parts, so the key is filesystem-safe
        regardless of what a source URL contains, and identical inputs always
        produce an identical key across machines and sessions.
        """
        if not parts:
            raise CacheError("key_for requires at least one part")
        digest = hashlib.sha256("\x00".join(str(p) for p in parts).encode("utf-8"))
        return digest.hexdigest()

    def _relative(self, key: str, suffix: str) -> tuple[str, ...]:
        if not key:
            raise CacheError("cache key must be non-empty")
        suffix = suffix if suffix.startswith(".") or not suffix else f".{suffix}"
        return (self.namespace, key[:SHARD_WIDTH], f"{key}{suffix}")

    # -- lookup ---------------------------------------------------------------

    def _is_fresh(self, path: Path) -> bool:
        if self.max_age_days is None:
            return True
        try:
            age_days = (time.time() - path.stat().st_mtime) / 86400.0
        except OSError:
            return False
        return age_days <= float(self.max_age_days)

    def locate(self, key: str, *, suffix: str = ".bin") -> CacheEntry | None:
        """Find an existing, unexpired entry. Returns ``None`` on a miss."""
        if not self.enabled:
            return None
        parts = self._relative(key, suffix)
        candidates = self.resolver.candidate_read_paths(self.path_key, *parts)
        input_count = len(self.resolver.input_roots)
        for index, candidate in enumerate(candidates):
            if candidate.exists() and self._is_fresh(candidate):
                return CacheEntry(key=key, path=candidate, from_input=index < input_count)
        return None

    def has(self, key: str, *, suffix: str = ".bin") -> bool:
        """Whether a usable entry exists."""
        return self.locate(key, suffix=suffix) is not None

    def write_target(self, key: str, *, suffix: str = ".bin") -> Path:
        """The writable path an entry would be stored at."""
        return self.resolver.write_path(self.path_key, *self._relative(key, suffix))

    # -- bytes ----------------------------------------------------------------

    def get(self, key: str, *, suffix: str = ".bin") -> bytes | None:
        """Return cached bytes, or ``None`` on a miss."""
        entry = self.locate(key, suffix=suffix)
        if entry is None:
            if self.logger is not None:
                self.logger.debug("cache miss: %s/%s", self.namespace, key)
            return None
        try:
            data = read_bytes(entry.path)
        except IOFormatError as exc:
            raise CacheError(f"Cache entry {key} is unreadable at {entry.path}: {exc}") from exc
        if self.logger is not None:
            self.logger.debug(
                "cache hit (%s): %s/%s", "input" if entry.from_input else "working", self.namespace, key
            )
        return data

    def put(self, key: str, data: bytes, *, suffix: str = ".bin") -> Path:
        """Store bytes and return the path written to.

        When the cache is disabled the path is still returned but nothing is
        written, so callers need no special-casing.
        """
        target = self.write_target(key, suffix=suffix)
        if not self.enabled:
            return target
        if not isinstance(data, (bytes, bytearray)):
            raise CacheError(f"ArtifactCache.put expects bytes, got {type(data).__name__}")
        try:
            return atomic_write_bytes(target, bytes(data))
        except OSError as exc:
            raise CacheError(f"Could not write cache entry {key} to {target}: {exc}") from exc

    # -- JSON convenience -----------------------------------------------------

    def get_json(self, key: str) -> Any | None:
        """Return a cached JSON value, or ``None`` on a miss."""
        entry = self.locate(key, suffix=".json")
        if entry is None:
            return None
        try:
            return read_json(entry.path)
        except IOFormatError as exc:
            raise CacheError(f"Cache entry {key} is not valid JSON at {entry.path}: {exc}") from exc

    def put_json(self, key: str, value: Any) -> Path:
        """Store a JSON-serialisable value."""
        target = self.write_target(key, suffix=".json")
        if not self.enabled:
            return target
        try:
            return write_json(target, value)
        except IOFormatError as exc:
            raise CacheError(f"Could not write cache entry {key}: {exc}") from exc
