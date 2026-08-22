"""Dual-mode path resolution.

The behaviour these tests pin down is the one that separates a run that works on
Kaggle from one that raises ``OSError: Read-only file system`` twenty minutes in:
reads search attached Datasets first, writes always land in the working root.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.common.errors import ConfigError, PathResolutionError
from src.common.paths import Mode, PathResolver, detect_mode


# -- mode detection -----------------------------------------------------------


def test_detects_local_by_default(tmp_path: Path):
    assert detect_mode({}, probe_root=tmp_path) is Mode.LOCAL


def test_detects_kaggle_from_env(tmp_path: Path):
    assert detect_mode({"KAGGLE_KERNEL_RUN_TYPE": "Interactive"}, probe_root=tmp_path) is Mode.KAGGLE


def test_detects_kaggle_from_filesystem(kaggle_dirs):
    """No env var set, but /kaggle/working exists — still Kaggle."""
    assert detect_mode({}, probe_root=kaggle_dirs["root"]) is Mode.KAGGLE


def test_explicit_mode_overrides_detection(base_config, tmp_path: Path):
    cfg = copy.deepcopy(base_config)
    cfg["environment"]["mode"] = "local"
    resolver = PathResolver.from_config(
        cfg, env={"KAGGLE_KERNEL_RUN_TYPE": "Batch"}, repo_root=tmp_path
    )
    assert resolver.mode is Mode.LOCAL


def test_invalid_mode_raises(base_config, tmp_path: Path):
    cfg = copy.deepcopy(base_config)
    cfg["environment"]["mode"] = "colab"
    with pytest.raises(ConfigError, match="environment.mode"):
        PathResolver.from_config(cfg, repo_root=tmp_path)


def test_missing_environment_section_raises(tmp_path: Path):
    with pytest.raises(ConfigError, match="environment"):
        PathResolver.from_config({"paths": {}}, repo_root=tmp_path)


# -- local mode ---------------------------------------------------------------


def test_local_roots(local_resolver: PathResolver, tmp_path: Path):
    assert local_resolver.mode is Mode.LOCAL
    assert local_resolver.working_root == tmp_path.resolve()
    assert local_resolver.input_roots == ()


def test_write_dir_is_created(local_resolver: PathResolver):
    path = local_resolver.write_dir("raw")
    assert path.is_dir()
    assert path.name == "raw"


def test_write_path_creates_parent_but_not_file(local_resolver: PathResolver):
    path = local_resolver.write_path("metadata", "manifest.json")
    assert path.parent.is_dir()
    assert not path.exists()


def test_write_path_requires_a_filename(local_resolver: PathResolver):
    with pytest.raises(PathResolutionError, match="at least one filename"):
        local_resolver.write_path("metadata")


def test_unknown_key_lists_declared_keys(local_resolver: PathResolver):
    with pytest.raises(PathResolutionError, match="Unknown path key"):
        local_resolver.write_dir("nonexistent")


def test_read_path_finds_written_file(local_resolver: PathResolver):
    target = local_resolver.write_path("processed", "a.jsonl")
    target.write_text("{}\n", encoding="utf-8")
    assert local_resolver.read_path("processed", "a.jsonl") == target


def test_read_path_error_lists_every_location_searched(local_resolver: PathResolver):
    with pytest.raises(PathResolutionError) as exc:
        local_resolver.read_path("processed", "missing.jsonl")
    assert "Searched:" in str(exc.value)
    assert "missing.jsonl" in str(exc.value)


def test_find_read_path_returns_none_on_miss(local_resolver: PathResolver):
    assert local_resolver.find_read_path("processed", "missing.jsonl") is None
    assert local_resolver.exists("processed", "missing.jsonl") is False


# -- Kaggle mode --------------------------------------------------------------


def test_kaggle_roots(kaggle_resolver: PathResolver, kaggle_dirs):
    assert kaggle_resolver.mode is Mode.KAGGLE
    assert kaggle_resolver.working_root == kaggle_dirs["working"]
    assert kaggle_resolver.input_roots == (kaggle_dirs["dataset"],)


def test_kaggle_writes_go_to_working_never_input(kaggle_resolver: PathResolver, kaggle_dirs):
    """The whole point: /kaggle/input is read-only, so writes must not target it."""
    path = kaggle_resolver.write_path("raw", "md_1.pdf")
    assert kaggle_dirs["working"] in path.parents
    assert kaggle_dirs["input_root"] not in path.parents


def test_kaggle_reads_prefer_attached_dataset(kaggle_resolver: PathResolver, kaggle_dirs):
    """A document present in both places resolves to the Dataset copy."""
    dataset_copy = kaggle_dirs["dataset"] / "data" / "raw" / "md_1.pdf"
    dataset_copy.parent.mkdir(parents=True, exist_ok=True)
    dataset_copy.write_bytes(b"%PDF-1.4 from dataset")

    working_copy = kaggle_resolver.write_path("raw", "md_1.pdf")
    working_copy.write_bytes(b"%PDF-1.4 from working")

    assert kaggle_resolver.read_path("raw", "md_1.pdf") == dataset_copy


def test_kaggle_reads_fall_back_to_working(kaggle_resolver: PathResolver):
    """Output produced this session is readable even though it is not in a Dataset."""
    produced = kaggle_resolver.write_path("processed", "new.jsonl")
    produced.write_text("{}\n", encoding="utf-8")
    assert kaggle_resolver.read_path("processed", "new.jsonl") == produced


def test_search_order_is_inputs_then_working(kaggle_resolver: PathResolver, kaggle_dirs):
    candidates = kaggle_resolver.candidate_read_paths("raw", "x.pdf")
    assert candidates[0].is_relative_to(kaggle_dirs["dataset"])
    assert candidates[-1].is_relative_to(kaggle_dirs["working"])


def test_multiple_datasets_searched_in_declared_order(kaggle_config, kaggle_dirs):
    kaggle_config["environment"]["kaggle"]["input_datasets"] = ["first", "second"]
    resolver = PathResolver.from_config(kaggle_config, repo_root=kaggle_dirs["root"])
    assert [p.name for p in resolver.input_roots] == ["first", "second"]


def test_describe_is_json_serialisable(kaggle_resolver: PathResolver):
    import json

    described = kaggle_resolver.describe()
    assert described["mode"] == "kaggle"
    json.dumps(described)
