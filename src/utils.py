"""Shared config / path helpers for Weeks 1–5."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


def load_config(config_path: Path | str | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config at {path} must be a mapping")
    return cfg


def resolve_path(cfg: dict[str, Any], key: str) -> Path:
    rel = cfg["paths"][key]
    p = Path(rel)
    if not p.is_absolute():
        p = REPO_ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_logging(name: str, cfg: dict[str, Any] | None = None) -> logging.Logger:
    level_name = "INFO"
    if cfg:
        level_name = cfg.get("logging", {}).get("level", "INFO")
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        log_dir = REPO_ROOT / "reports" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / f"{name.replace('.', '_')}.log")
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(fh)
    logger.setLevel(level)
    return logger
