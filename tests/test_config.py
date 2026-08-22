"""Config loader: it must fail loudly, never default silently."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from src.common.config import (
    DEFAULT_CONFIG_PATH,
    REQUIRED_PATH_KEYS,
    get_required,
    load_config,
    validate_config,
)
from src.common.errors import ConfigError

from tests.conftest import make_config


def test_loads_valid_config(config_file: Path):
    cfg = load_config(config_file)
    assert cfg["environment"]["mode"] == "local"
    assert set(REQUIRED_PATH_KEYS) <= set(cfg["paths"])


def test_shipped_config_is_valid():
    """The config actually committed to the repo must pass its own validator."""
    cfg = load_config(DEFAULT_CONFIG_PATH)
    assert validate_config(cfg) == []


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_malformed_yaml_raises(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("paths: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(path)


def test_empty_file_raises(tmp_path: Path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="empty"):
        load_config(path)


def test_non_mapping_raises(tmp_path: Path):
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must contain a mapping"):
        load_config(path)


def test_missing_section_is_reported(tmp_path: Path, base_config):
    cfg = copy.deepcopy(base_config)
    del cfg["network"]
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    with pytest.raises(ConfigError, match="missing section: 'network'"):
        load_config(path)


def test_missing_path_key_is_reported(base_config):
    cfg = copy.deepcopy(base_config)
    del cfg["paths"]["matrix"]
    errors = validate_config(cfg)
    assert any("paths.matrix" in e for e in errors)


def test_absolute_path_key_is_rejected(base_config):
    """Absolute roots come from environment.<mode>; a path key must stay relative."""
    cfg = copy.deepcopy(base_config)
    cfg["paths"]["raw"] = "/kaggle/input/raw"
    errors = validate_config(cfg)
    assert any("must be relative" in e for e in errors)


def test_null_required_scalar_is_reported(base_config):
    cfg = copy.deepcopy(base_config)
    cfg["cache"]["namespace"] = None
    errors = validate_config(cfg)
    assert any("cache.namespace" in e for e in errors)


def test_invalid_mode_is_reported(base_config):
    cfg = copy.deepcopy(base_config)
    cfg["environment"]["mode"] = "colab"
    errors = validate_config(cfg)
    assert any("environment.mode" in e for e in errors)


def test_zero_retry_attempts_is_reported(base_config):
    cfg = copy.deepcopy(base_config)
    cfg["network"]["retry"]["attempts"] = 0
    errors = validate_config(cfg)
    assert any("attempts must be >= 1" in e for e in errors)


def test_all_errors_reported_at_once(base_config):
    """One fix per run is a slow loop; the validator reports everything it finds."""
    cfg = copy.deepcopy(base_config)
    del cfg["cache"]
    del cfg["paths"]["raw"]
    cfg["environment"]["mode"] = "bogus"
    errors = validate_config(cfg)
    assert len(errors) >= 3


def test_validate_rejects_non_mapping():
    assert validate_config(["not", "a", "mapping"])


def test_get_required_returns_nested_value(base_config):
    assert get_required(base_config, "network.retry.attempts") == 3


def test_get_required_raises_on_missing(base_config):
    with pytest.raises(ConfigError, match="missing"):
        get_required(base_config, "retrieval.embedding_model")


def test_get_required_raises_on_null(base_config):
    cfg = copy.deepcopy(base_config)
    cfg["cache"]["namespace"] = None
    with pytest.raises(ConfigError, match="null"):
        get_required(cfg, "cache.namespace")


def test_validate_false_skips_validation(tmp_path: Path):
    path = tmp_path / "partial.yaml"
    path.write_text(yaml.safe_dump({"paths": {}}), encoding="utf-8")
    cfg = load_config(path, validate=False)
    assert cfg == {"paths": {}}


def test_make_config_helper_is_valid():
    assert validate_config(make_config()) == []
