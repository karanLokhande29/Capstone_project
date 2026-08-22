"""Shared fixtures.

The Kaggle fixtures build a *fake* Kaggle filesystem under ``tmp_path`` rather
than touching ``/kaggle``. That keeps the tests runnable on a laptop while still
exercising the real read-only-input / writable-working split, which is the part
of the dual-mode design most likely to break in production.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.common.paths import PathResolver

PATH_KEYS = {
    "raw": "data/raw",
    "extracted": "data/extracted",
    "processed": "data/processed",
    "metadata": "data/metadata",
    "matrix": "data/matrix",
    "benchmark": "data/benchmark",
    "evaluation": "data/evaluation",
    "cache": "data/cache",
    "reports": "reports",
    "logs": "logs",
}


def make_config(**overrides: Any) -> dict[str, Any]:
    """A minimal config that passes validation, with optional overrides."""
    cfg: dict[str, Any] = {
        "environment": {
            "mode": "local",
            "local": {"working_root": ".", "input_roots": []},
            "kaggle": {
                "working_root": "/kaggle/working",
                "input_root": "/kaggle/input",
                "input_datasets": [],
            },
        },
        "paths": dict(PATH_KEYS),
        "logging": {"level": "INFO", "format": "%(message)s", "to_file": False},
        "network": {
            "retry": {
                "attempts": 3,
                "initial_delay_sec": 0.01,
                "backoff_factor": 2.0,
                "max_delay_sec": 1.0,
                "jitter": 0.0,
            },
            "request_timeout_sec": 30,
            "rate_limit_sec": 0.0,
        },
        "cache": {"enabled": True, "namespace": "test", "max_age_days": None},
    }
    cfg.update(overrides)
    return cfg


@pytest.fixture
def base_config() -> dict[str, Any]:
    """A valid in-memory config."""
    return make_config()


@pytest.fixture
def config_file(tmp_path: Path, base_config: dict[str, Any]) -> Path:
    """``base_config`` written to a real YAML file."""
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(base_config), encoding="utf-8")
    return path


@pytest.fixture
def local_resolver(tmp_path: Path, base_config: dict[str, Any]) -> PathResolver:
    """A resolver rooted at ``tmp_path`` in local mode."""
    return PathResolver.from_config(base_config, repo_root=tmp_path)


@pytest.fixture
def kaggle_dirs(tmp_path: Path) -> dict[str, Path]:
    """A fake Kaggle filesystem: read-only input mount plus writable working dir."""
    working = tmp_path / "kaggle" / "working"
    input_root = tmp_path / "kaggle" / "input"
    dataset = input_root / "rbi-corpus"
    for directory in (working, dataset):
        directory.mkdir(parents=True, exist_ok=True)
    return {"working": working, "input_root": input_root, "dataset": dataset, "root": tmp_path}


@pytest.fixture
def kaggle_config(kaggle_dirs: dict[str, Path]) -> dict[str, Any]:
    """A config pointing at the fake Kaggle filesystem."""
    return make_config(
        environment={
            "mode": "kaggle",
            "local": {"working_root": ".", "input_roots": []},
            "kaggle": {
                "working_root": str(kaggle_dirs["working"]),
                "input_root": str(kaggle_dirs["input_root"]),
                "input_datasets": ["rbi-corpus"],
            },
        }
    )


@pytest.fixture
def kaggle_resolver(kaggle_config: dict[str, Any], kaggle_dirs: dict[str, Path]) -> PathResolver:
    """A resolver in Kaggle mode over the fake Kaggle filesystem."""
    return PathResolver.from_config(kaggle_config, repo_root=kaggle_dirs["root"])
