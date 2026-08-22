"""Configuration loading and validation.

Design rule for this module: **fail loudly**. A missing or malformed required
field raises :class:`~src.common.errors.ConfigError` at load time, listing every
problem found rather than the first. Silent defaulting is what lets three
parallel branches drift apart without noticing, so it is not offered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from src.common.errors import ConfigError

# Repository root: src/common/config.py -> src/common -> src -> <root>
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"

#: Top-level sections every config must define.
REQUIRED_SECTIONS = ("environment", "paths", "logging", "network", "cache")

#: Logical path keys every branch may rely on being present.
REQUIRED_PATH_KEYS = (
    "raw",
    "extracted",
    "processed",
    "metadata",
    "matrix",
    "benchmark",
    "evaluation",
    "cache",
    "reports",
    "logs",
)

#: Scalar fields that must be present AND non-null. Dotted paths.
REQUIRED_SCALARS = (
    "environment.mode",
    "logging.level",
    "logging.format",
    "network.retry.attempts",
    "network.retry.initial_delay_sec",
    "network.retry.backoff_factor",
    "network.retry.max_delay_sec",
    "network.request_timeout_sec",
    "cache.enabled",
    "cache.namespace",
)

VALID_MODES = ("auto", "local", "kaggle")


def _get_dotted(cfg: Mapping[str, Any], dotted: str) -> tuple[bool, Any]:
    """Return ``(found, value)`` for a dotted config key."""
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, Mapping) or part not in node:
            return False, None
        node = node[part]
    return True, node


def get_required(cfg: Mapping[str, Any], dotted: str) -> Any:
    """Fetch a required config value, raising :class:`ConfigError` if absent/null.

    Use this in branch code instead of ``cfg.get(...)`` chains, so a missing
    value surfaces as a clear error naming the key rather than a ``TypeError``
    several frames away.
    """
    found, value = _get_dotted(cfg, dotted)
    if not found:
        raise ConfigError(f"Required config key is missing: {dotted!r}")
    if value is None:
        raise ConfigError(f"Required config key is null: {dotted!r}")
    return value


def validate_config(cfg: Any) -> list[str]:
    """Return every validation problem found. Empty list means the config is valid."""
    errors: list[str] = []

    if not isinstance(cfg, Mapping):
        return [f"config must be a mapping, got {type(cfg).__name__}"]

    for section in REQUIRED_SECTIONS:
        if section not in cfg:
            errors.append(f"missing section: {section!r}")
        elif not isinstance(cfg[section], Mapping):
            errors.append(f"section {section!r} must be a mapping")

    paths = cfg.get("paths")
    if isinstance(paths, Mapping):
        for key in REQUIRED_PATH_KEYS:
            if key not in paths:
                errors.append(f"missing path key: paths.{key}")
            elif not paths[key] or not isinstance(paths[key], str):
                errors.append(f"path key must be a non-empty string: paths.{key}")
            elif Path(paths[key]).is_absolute():
                errors.append(
                    f"path key must be relative, not absolute: paths.{key}={paths[key]!r} "
                    "(absolute roots come from environment.<mode>, not paths)"
                )

    for dotted in REQUIRED_SCALARS:
        found, value = _get_dotted(cfg, dotted)
        if not found:
            errors.append(f"missing required key: {dotted}")
        elif value is None:
            errors.append(f"required key is null: {dotted}")

    found, mode = _get_dotted(cfg, "environment.mode")
    if found and mode not in VALID_MODES:
        errors.append(f"environment.mode must be one of {VALID_MODES}, got {mode!r}")

    env = cfg.get("environment")
    if isinstance(env, Mapping):
        for sub in ("local", "kaggle"):
            block = env.get(sub)
            if not isinstance(block, Mapping):
                errors.append(f"missing or non-mapping section: environment.{sub}")
            elif not block.get("working_root"):
                errors.append(f"missing required key: environment.{sub}.working_root")

    found, attempts = _get_dotted(cfg, "network.retry.attempts")
    if found and isinstance(attempts, int) and attempts < 1:
        errors.append(f"network.retry.attempts must be >= 1, got {attempts}")

    return errors


def load_config(config_path: Path | str | None = None, *, validate: bool = True) -> dict[str, Any]:
    """Load and validate the shared configuration.

    Args:
        config_path: Path to a YAML config. Defaults to ``config/config.yaml``
            at the repository root.
        validate: Run :func:`validate_config` and raise on any problem. Only
            disable this in tests that deliberately construct partial configs.

    Raises:
        ConfigError: The file is missing, is not valid YAML, is not a mapping,
            or fails validation.
    """
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read config file {path}: {exc}") from exc

    try:
        cfg = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file {path} is not valid YAML: {exc}") from exc

    if cfg is None:
        raise ConfigError(f"Config file {path} is empty")
    if not isinstance(cfg, dict):
        raise ConfigError(f"Config file {path} must contain a mapping, got {type(cfg).__name__}")

    if validate:
        errors = validate_config(cfg)
        if errors:
            listed = "\n".join(f"  - {e}" for e in errors)
            raise ConfigError(f"Invalid config at {path}:\n{listed}")

    return cfg
