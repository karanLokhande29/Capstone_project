"""Dual-mode path resolution for local and Kaggle execution.

All compute for this project runs on Kaggle Notebooks, but code is authored and
unit-tested locally. The two filesystems differ in a way that breaks naive path
handling:

===============  ==========================  ====================================
                 Local                       Kaggle
===============  ==========================  ====================================
Read + write     repository root             ``/kaggle/working`` (writable)
Read-only input  --                          ``/kaggle/input/<slug>`` (read-only)
===============  ==========================  ====================================

On Kaggle, attached Datasets mount **read-only**. Any code that resolves one
path and then both reads and writes it will work locally and fail on Kaggle. So
this module deliberately splits the two operations:

* :meth:`PathResolver.read_path` searches input roots first, then the working
  root, and reports where it looked when nothing is found.
* :meth:`PathResolver.write_path` *always* targets the working root and creates
  parent directories.

Branch code must never construct ``/kaggle/...`` or ``data/...`` paths by hand.
Resolve a logical key from ``config.yaml`` instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.common.config import REPO_ROOT
from src.common.errors import ConfigError, PathResolutionError


class Mode(str, Enum):
    """Execution environment."""

    LOCAL = "local"
    KAGGLE = "kaggle"


#: Environment variables Kaggle sets inside a notebook kernel.
KAGGLE_ENV_MARKERS = ("KAGGLE_KERNEL_RUN_TYPE", "KAGGLE_URL_BASE")

#: Filesystem marker probed when no environment variable is present.
KAGGLE_FS_MARKER = Path("kaggle") / "working"


def detect_mode(
    env: Mapping[str, str] | None = None,
    *,
    probe_root: Path | str | None = None,
) -> Mode:
    """Detect whether we are running on Kaggle.

    Args:
        env: Environment mapping. Defaults to :data:`os.environ`.
        probe_root: Filesystem root to probe for ``kaggle/working``. Defaults to
            ``/``. Tests pass a temp directory here instead of mocking
            :mod:`os.path`, which keeps the check honest.
    """
    env = os.environ if env is None else env
    if any(env.get(marker) for marker in KAGGLE_ENV_MARKERS):
        return Mode.KAGGLE
    root = Path("/") if probe_root is None else Path(probe_root)
    if (root / KAGGLE_FS_MARKER).is_dir():
        return Mode.KAGGLE
    return Mode.LOCAL


@dataclass(frozen=True)
class PathResolver:
    """Resolves logical path keys against the active execution environment.

    Attributes:
        mode: Resolved execution mode (never ``auto``).
        working_root: The single writable root. All output goes here.
        input_roots: Read-only roots searched before ``working_root`` on reads.
        relative_paths: Logical key -> relative subpath, from ``config.paths``.
    """

    mode: Mode
    working_root: Path
    input_roots: tuple[Path, ...]
    relative_paths: Mapping[str, str]

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        cfg: Mapping[str, Any],
        *,
        env: Mapping[str, str] | None = None,
        probe_root: Path | str | None = None,
        repo_root: Path | str | None = None,
    ) -> "PathResolver":
        """Build a resolver from a loaded config.

        Args:
            cfg: Config mapping, as returned by :func:`src.common.config.load_config`.
            env: Environment mapping used for mode detection.
            probe_root: Filesystem root used for mode detection.
            repo_root: Overrides the repository root that relative local roots
                resolve against. Tests point this at a temp directory.
        """
        environment = cfg.get("environment")
        if not isinstance(environment, Mapping):
            raise ConfigError("config is missing the 'environment' section")

        declared = str(environment.get("mode", "auto"))
        if declared == "auto":
            mode = detect_mode(env, probe_root=probe_root)
        elif declared in (Mode.LOCAL.value, Mode.KAGGLE.value):
            mode = Mode(declared)
        else:
            raise ConfigError(
                f"environment.mode must be 'auto', 'local' or 'kaggle', got {declared!r}"
            )

        block = environment.get(mode.value)
        if not isinstance(block, Mapping):
            raise ConfigError(f"config is missing the 'environment.{mode.value}' section")

        base = Path(repo_root) if repo_root is not None else REPO_ROOT

        working_raw = block.get("working_root")
        if not working_raw:
            raise ConfigError(f"environment.{mode.value}.working_root is required")
        working_root = cls._absolutise(working_raw, base)

        input_roots = cls._collect_input_roots(mode, block, base)

        paths = cfg.get("paths")
        if not isinstance(paths, Mapping):
            raise ConfigError("config is missing the 'paths' section")

        return cls(
            mode=mode,
            working_root=working_root,
            input_roots=tuple(input_roots),
            relative_paths=dict(paths),
        )

    @staticmethod
    def _absolutise(raw: str, base: Path) -> Path:
        path = Path(raw)
        return path if path.is_absolute() else (base / path).resolve()

    @classmethod
    def _collect_input_roots(
        cls, mode: Mode, block: Mapping[str, Any], base: Path
    ) -> list[Path]:
        if mode is Mode.KAGGLE:
            input_root = Path(str(block.get("input_root") or "/kaggle/input"))
            datasets: Sequence[str] = block.get("input_datasets") or []
            if isinstance(datasets, str):  # tolerate a single slug written unquoted
                datasets = [datasets]
            return [input_root / str(slug) for slug in datasets]

        extra: Sequence[str] = block.get("input_roots") or []
        if isinstance(extra, str):
            extra = [extra]
        return [cls._absolutise(str(item), base) for item in extra]

    # -- key resolution -------------------------------------------------------

    def _relative(self, key: str) -> Path:
        if key not in self.relative_paths:
            known = ", ".join(sorted(self.relative_paths)) or "<none>"
            raise PathResolutionError(
                f"Unknown path key {key!r}. Declared keys: {known}. "
                "Add it to `paths:` in config/config.yaml rather than hard-coding a path."
            )
        return Path(str(self.relative_paths[key]))

    def search_roots(self) -> tuple[Path, ...]:
        """Roots searched on reads, in order: read-only inputs, then working."""
        return (*self.input_roots, self.working_root)

    # -- writes (always to the writable root) ---------------------------------

    def write_dir(self, key: str, *, create: bool = True) -> Path:
        """Return the writable directory for ``key``, creating it by default."""
        path = self.working_root / self._relative(key)
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def write_path(self, key: str, *parts: str, create_parents: bool = True) -> Path:
        """Return a writable file path under ``key``.

        The file itself is not created; only its parent directory is.
        """
        if not parts:
            raise PathResolutionError("write_path requires at least one filename component")
        path = self.working_root.joinpath(self._relative(key), *parts)
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    # -- reads (input roots first, then working) ------------------------------

    def candidate_read_paths(self, key: str, *parts: str) -> list[Path]:
        """Every location that would be searched for ``key``/``parts``, in order."""
        relative = self._relative(key)
        if parts:
            return [root.joinpath(relative, *parts) for root in self.search_roots()]
        return [root / relative for root in self.search_roots()]

    def read_path(self, key: str, *parts: str) -> Path:
        """Return the first existing path for ``key``/``parts``.

        Raises:
            PathResolutionError: Nothing exists at any candidate location. The
                message lists every location searched, which is the single most
                useful thing to know when a Kaggle Dataset is not attached.
        """
        candidates = self.candidate_read_paths(key, *parts)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        searched = "\n".join(f"  - {c}" for c in candidates)
        target = "/".join((key, *parts)) if parts else key
        raise PathResolutionError(
            f"Could not resolve {target!r} in {self.mode.value} mode. Searched:\n{searched}"
        )

    def find_read_path(self, key: str, *parts: str) -> Path | None:
        """Like :meth:`read_path` but returns ``None`` instead of raising."""
        for candidate in self.candidate_read_paths(key, *parts):
            if candidate.exists():
                return candidate
        return None

    def exists(self, key: str, *parts: str) -> bool:
        """Whether ``key``/``parts`` resolves anywhere."""
        return self.find_read_path(key, *parts) is not None

    # -- diagnostics ----------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """A JSON-serialisable summary, for smoke tests and notebook output."""
        return {
            "mode": self.mode.value,
            "working_root": str(self.working_root),
            "input_roots": [str(p) for p in self.input_roots],
            "path_keys": sorted(self.relative_paths),
        }
