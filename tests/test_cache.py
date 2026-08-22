"""Artifact cache, including the Kaggle Dataset read-through path.

The Kaggle behaviour is exercised against the fake ``/kaggle`` filesystem from
``conftest``: entries written in a previous session (simulated by an attached
Dataset) must be cache hits, and new writes must land in the writable working
root rather than the read-only mount.
"""

from __future__ import annotations

import pytest

from src.common.cache import ArtifactCache
from src.common.errors import CacheError


# -- keys ---------------------------------------------------------------------


def test_key_is_deterministic():
    a = ArtifactCache.key_for("https://rbi.org.in/md_1.pdf")
    b = ArtifactCache.key_for("https://rbi.org.in/md_1.pdf")
    assert a == b and len(a) == 64


def test_different_inputs_give_different_keys():
    assert ArtifactCache.key_for("a") != ArtifactCache.key_for("b")


def test_key_parts_are_unambiguous():
    """Joining on a separator that cannot occur in the parts avoids collisions."""
    assert ArtifactCache.key_for("ab", "c") != ArtifactCache.key_for("a", "bc")


def test_key_requires_parts():
    with pytest.raises(CacheError):
        ArtifactCache.key_for()


def test_empty_namespace_rejected(local_resolver):
    with pytest.raises(CacheError, match="namespace"):
        ArtifactCache(local_resolver, namespace="")


# -- local round trip ---------------------------------------------------------


def test_bytes_round_trip(local_resolver):
    cache = ArtifactCache(local_resolver, namespace="scraper")
    key = cache.key_for("https://example.org/a.pdf")
    assert cache.get(key) is None

    cache.put(key, b"%PDF-1.4 payload")
    assert cache.get(key) == b"%PDF-1.4 payload"
    assert cache.has(key)


def test_json_round_trip(local_resolver):
    cache = ArtifactCache(local_resolver, namespace="meta")
    key = cache.key_for("manifest", "v1")
    assert cache.get_json(key) is None

    cache.put_json(key, {"documents": 381})
    assert cache.get_json(key) == {"documents": 381}


def test_namespaces_are_isolated(local_resolver):
    """Three branches sharing one Kaggle Dataset must not collide."""
    key = ArtifactCache.key_for("same-input")
    ArtifactCache(local_resolver, namespace="akash").put(key, b"one")
    ArtifactCache(local_resolver, namespace="meer").put(key, b"two")

    assert ArtifactCache(local_resolver, namespace="akash").get(key) == b"one"
    assert ArtifactCache(local_resolver, namespace="meer").get(key) == b"two"


def test_entries_are_sharded(local_resolver):
    cache = ArtifactCache(local_resolver, namespace="scraper")
    key = cache.key_for("x")
    path = cache.put(key, b"data")
    assert path.parent.name == key[:2]


def test_put_rejects_non_bytes(local_resolver):
    cache = ArtifactCache(local_resolver, namespace="scraper")
    with pytest.raises(CacheError, match="expects bytes"):
        cache.put(cache.key_for("x"), "a string")  # type: ignore[arg-type]


def test_disabled_cache_never_hits(local_resolver):
    cache = ArtifactCache(local_resolver, namespace="scraper", enabled=False)
    key = cache.key_for("x")
    cache.put(key, b"data")
    assert cache.get(key) is None
    assert not cache.has(key)


def test_from_config(base_config, local_resolver):
    cache = ArtifactCache.from_config(base_config, local_resolver)
    assert cache.namespace == "test"
    assert cache.enabled is True


def test_from_config_requires_cache_section(local_resolver):
    with pytest.raises(CacheError, match="cache"):
        ArtifactCache.from_config({}, local_resolver)


# -- expiry -------------------------------------------------------------------


def test_expired_entry_is_a_miss(local_resolver):
    import os
    import time

    cache = ArtifactCache(local_resolver, namespace="scraper", max_age_days=1)
    key = cache.key_for("x")
    path = cache.put(key, b"stale")
    old = time.time() - (3 * 86400)
    os.utime(path, (old, old))
    assert cache.get(key) is None


def test_no_expiry_by_default(local_resolver):
    """Regulatory source documents are immutable; expiring them wastes a harvest."""
    import os
    import time

    cache = ArtifactCache(local_resolver, namespace="scraper")
    key = cache.key_for("x")
    path = cache.put(key, b"old but valid")
    old = time.time() - (365 * 86400)
    os.utime(path, (old, old))
    assert cache.get(key) == b"old but valid"


# -- Kaggle read-through ------------------------------------------------------


def test_kaggle_write_targets_working_not_input(kaggle_resolver, kaggle_dirs):
    cache = ArtifactCache(kaggle_resolver, namespace="scraper")
    path = cache.put(cache.key_for("x"), b"data")
    assert kaggle_dirs["working"] in path.parents
    assert kaggle_dirs["input_root"] not in path.parents


def test_kaggle_reads_hit_the_attached_dataset(kaggle_resolver, kaggle_dirs):
    """A corpus harvested last session and saved as a Dataset is a hit this session."""
    cache = ArtifactCache(kaggle_resolver, namespace="scraper")
    key = cache.key_for("https://rbi.org.in/md_1.pdf")

    # Simulate a previous session's output, saved as a Kaggle Dataset.
    seeded = kaggle_dirs["dataset"] / "data" / "cache" / "scraper" / key[:2] / f"{key}.bin"
    seeded.parent.mkdir(parents=True, exist_ok=True)
    seeded.write_bytes(b"%PDF from previous session")

    entry = cache.locate(key)
    assert entry is not None
    assert entry.from_input is True
    assert cache.get(key) == b"%PDF from previous session"


def test_kaggle_dataset_wins_over_working_copy(kaggle_resolver, kaggle_dirs):
    cache = ArtifactCache(kaggle_resolver, namespace="scraper")
    key = cache.key_for("x")

    seeded = kaggle_dirs["dataset"] / "data" / "cache" / "scraper" / key[:2] / f"{key}.bin"
    seeded.parent.mkdir(parents=True, exist_ok=True)
    seeded.write_bytes(b"from dataset")
    cache.put(key, b"from working")

    assert cache.get(key) == b"from dataset"


def test_kaggle_working_entry_is_still_readable(kaggle_resolver):
    """Nothing written this session is in a Dataset yet; it must still be a hit."""
    cache = ArtifactCache(kaggle_resolver, namespace="scraper")
    key = cache.key_for("new")
    cache.put(key, b"fresh")
    entry = cache.locate(key)
    assert entry is not None and entry.from_input is False


# -- corruption ---------------------------------------------------------------


def test_corrupt_json_entry_raises_rather_than_returning_garbage(local_resolver):
    cache = ArtifactCache(local_resolver, namespace="meta")
    key = cache.key_for("x")
    cache.write_target(key, suffix=".json").write_text("{not json", encoding="utf-8")
    with pytest.raises(CacheError, match="not valid JSON"):
        cache.get_json(key)
