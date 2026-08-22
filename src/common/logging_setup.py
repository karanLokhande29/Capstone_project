"""Standard logging configuration shared by every branch.

Import :func:`get_logger` rather than calling :mod:`logging` directly, so all
three branches produce identically-formatted, identically-located logs. On
Kaggle the file handler lands under ``/kaggle/working/logs/``, which survives
the session only if the working directory is saved as a Dataset version.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Mapping

from src.common.paths import PathResolver

DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_LEVEL = "INFO"

#: Marker attribute set on handlers this module installs, so repeated calls are
#: idempotent without clobbering handlers installed by pytest or by Kaggle.
_MANAGED = "_rbi_obligench_managed"


def _resolve_level(name: Any) -> int:
    level = getattr(logging, str(name).upper(), None)
    return level if isinstance(level, int) else logging.INFO


def get_logger(
    name: str,
    cfg: Mapping[str, Any] | None = None,
    *,
    resolver: PathResolver | None = None,
) -> logging.Logger:
    """Return a configured logger.

    Args:
        name: Dotted logger name, e.g. ``"scraper.rbi"``. Also determines the
            log filename (dots become underscores).
        cfg: Loaded config. When omitted, sane defaults are used so that
            utilities remain usable before config exists.
        resolver: Path resolver used to locate the log directory. When omitted,
            no file handler is attached and logging goes to stderr only.

    Repeated calls with the same name reconfigure the level but do not stack
    duplicate handlers.
    """
    log_cfg: Mapping[str, Any] = {}
    if cfg is not None:
        candidate = cfg.get("logging")
        if isinstance(candidate, Mapping):
            log_cfg = candidate

    level = _resolve_level(log_cfg.get("level", DEFAULT_LEVEL))
    fmt = str(log_cfg.get("format") or DEFAULT_FORMAT)
    to_file = bool(log_cfg.get("to_file", True))

    logger = logging.getLogger(name)
    logger.setLevel(level)

    existing = {getattr(h, _MANAGED, None) for h in logger.handlers}
    formatter = logging.Formatter(fmt)

    if "stream" not in existing:
        stream = logging.StreamHandler(stream=sys.stderr)
        stream.setFormatter(formatter)
        setattr(stream, _MANAGED, "stream")
        logger.addHandler(stream)

    if to_file and resolver is not None and "file" not in existing:
        try:
            log_dir = resolver.write_dir("logs")
            handler = logging.FileHandler(log_dir / f"{name.replace('.', '_')}.log", encoding="utf-8")
            handler.setFormatter(formatter)
            setattr(handler, _MANAGED, "file")
            logger.addHandler(handler)
        except OSError as exc:
            # A read-only or missing log directory must never take down a run.
            logger.warning("File logging disabled (%s): %s", type(exc).__name__, exc)

    # Records are emitted by our handlers; do not also bubble to the root logger,
    # which Kaggle configures with its own handler and would duplicate output.
    logger.propagate = False
    return logger


def reset_logger(name: str) -> None:
    """Remove handlers this module installed. Used by tests for isolation."""
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        if getattr(handler, _MANAGED, None) is not None:
            handler.close()
            logger.removeHandler(handler)
