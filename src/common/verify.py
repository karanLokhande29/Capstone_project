"""Foundation self-check.

One entry point, :func:`run_foundation_check`, exercised from three places:
the integration test, the ``scripts/verify_foundation.py`` CLI, and the Kaggle
notebook. Keeping the logic here rather than in the notebook is deliberate — the
notebook stays a thin wrapper whose JSON is small enough to regenerate safely.

The check answers one question: can three branches fork from this base and
expect it to work? That means every module imports, the config loads and
validates, paths resolve in whichever environment we are actually in, the cache
round-trips, and every schema constructs.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

#: Every module that must import cleanly. Listed explicitly rather than
#: discovered by walking the tree, so a module that silently fails to be created
#: shows up as a failure instead of simply not being checked.
FOUNDATION_MODULES = (
    "src",
    "src.common",
    "src.common.cache",
    "src.common.config",
    "src.common.errors",
    "src.common.io_helpers",
    "src.common.logging_setup",
    "src.common.paths",
    "src.common.retry",
    "src.common.verify",
    "src.schemas",
    "src.schemas.base",
    "src.schemas.benchmark",
    "src.schemas.matrix",
    "src.schemas.provenance",
    "src.schemas.vocabulary",
)

#: Branch packages and their interface stubs. These must import even though
#: every function in them raises, because a broken import here would block all
#: three Phase 1 branches at once.
BRANCH_MODULES = (
    "src.scraper",
    "src.scraper.interfaces",
    "src.extraction",
    "src.extraction.interfaces",
    "src.preprocessing",
    "src.preprocessing.interfaces",
    "src.metadata",
    "src.metadata.interfaces",
    "src.matrix",
    "src.matrix.interfaces",
    "src.benchmark",
    "src.benchmark.interfaces",
)

NOT_MEASURED = "NOT YET MEASURED"


def _check(name: str, fn: Callable[[], Any]) -> dict[str, Any]:
    """Run one check, capturing its outcome rather than letting it abort the run."""
    try:
        detail = fn()
        return {"check": name, "status": "PASS", "detail": detail}
    except Exception as exc:  # noqa: BLE001 - a self-check reports failures, it does not raise them
        return {"check": name, "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}


def _import_all(modules: tuple[str, ...]) -> str:
    """Import every named module, reporting the first failure clearly."""
    for name in modules:
        importlib.import_module(name)
    return f"{len(modules)} modules imported"


def _check_no_circular_imports(repo_root: Path) -> str:
    """Import each module first, in a fresh interpreter.

    A circular import often hides behind import order: the package works when
    the parent is imported first and fails when a leaf is. Each module is
    therefore imported as the *very first* thing a cold interpreter does.

    A subprocess rather than ``sys.modules`` surgery: clearing and re-importing
    in-process would leave two copies of every class alive, and the identity
    mismatch would produce confusing failures in whatever ran next.
    """
    import subprocess

    for name in FOUNDATION_MODULES + BRANCH_MODULES:
        result = subprocess.run(
            [sys.executable, "-c", f"import {name}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            tail = (result.stderr or "").strip().splitlines()
            raise AssertionError(
                f"importing {name} first fails: {tail[-1] if tail else 'unknown error'}"
            )
    return f"{len(FOUNDATION_MODULES + BRANCH_MODULES)} modules import standalone"


def _check_package_markers(repo_root: Path) -> str:
    """Every source package needs an ``__init__.py`` or Kaggle imports get strange."""
    missing = [
        str(directory.relative_to(repo_root))
        for directory in sorted((repo_root / "src").rglob("*"))
        if directory.is_dir()
        and directory.name != "__pycache__"
        and not (directory / "__init__.py").exists()
    ]
    if missing:
        raise AssertionError(f"packages missing __init__.py: {missing}")
    return "all src packages have __init__.py"


def _check_schemas() -> str:
    """Every declared schema must construct and describe itself."""
    from src.schemas import ALL_SCHEMAS
    from src.schemas.base import KNOWN_OWNERS

    total_fields = 0
    for schema in ALL_SCHEMAS:
        declared = set(schema.field_names())
        specified = set(schema.spec_map())
        if declared != specified:
            raise AssertionError(f"{schema.__name__}: field/spec mismatch {declared ^ specified}")
        for spec in schema.FIELD_SPECS:
            if spec.populated_by not in KNOWN_OWNERS:
                raise AssertionError(f"{schema.__name__}.{spec.name}: unknown owner {spec.populated_by!r}")
        total_fields += len(declared)
    return f"{len(ALL_SCHEMAS)} schemas, {total_fields} documented fields"


def _check_vocabularies_empty() -> str:
    """Guards the no-hard-coded-vocabulary rule at runtime, not just in tests."""
    from src.schemas.vocabulary import (
        empty_entity_class_vocabulary,
        empty_subject_family_vocabulary,
    )

    entity = empty_entity_class_vocabulary()
    subject = empty_subject_family_vocabulary()
    if len(entity) or len(subject):
        raise AssertionError(
            "vocabularies must start empty; terms are discovered from the corpus, "
            f"got entity={len(entity)} subject={len(subject)}"
        )
    return "entity and subject vocabularies are empty, as required"


def _check_benchmark_defaults() -> str:
    """Guards the two label-integrity rules that carry the research claims."""
    from src.schemas.benchmark import DifferentialFlag, LabelStatus, T1Label

    label = T1Label(label_id="smoke_check")
    if label.differential_flag != DifferentialFlag.UNLABELLED.value:
        raise AssertionError(
            f"differential_flag must default to 'unlabelled', got {label.differential_flag!r}"
        )
    if label.applies_to:
        raise AssertionError("applies_to must default to empty; it is an annotation target")
    if label.label_status != LabelStatus.CANDIDATE.value:
        raise AssertionError("label_status must default to 'candidate'")
    return "T1 defaults: unlabelled / empty applies_to / candidate"


def run_foundation_check(
    config_path: Path | str | None = None,
    *,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run every foundation check and return a structured report.

    Args:
        config_path: Config to load. Defaults to the repository's config.
        repo_root: Repository root, used for the package-marker check.

    Returns:
        A mapping with ``overall`` (``"PASS"``/``"FAIL"``), the ``checks`` list,
        a ``summary`` of counts, and the resolved ``environment``. Never raises:
        a self-check that crashes tells you less than one that reports.
    """
    from src.common.config import REPO_ROOT, load_config
    from src.common.paths import PathResolver

    root = Path(repo_root) if repo_root is not None else REPO_ROOT

    checks: list[dict[str, Any]] = [
        _check("foundation modules import", lambda: _import_all(FOUNDATION_MODULES)),
        _check("branch interface stubs import", lambda: _import_all(BRANCH_MODULES)),
        _check("no circular imports", lambda: _check_no_circular_imports(root)),
        _check("packages have __init__.py", lambda: _check_package_markers(root)),
        _check("schemas are complete and owned", _check_schemas),
        _check("vocabularies start empty", _check_vocabularies_empty),
        _check("T1 label defaults are honest", _check_benchmark_defaults),
    ]

    environment: dict[str, Any] = {}

    def _config_and_paths() -> str:
        nonlocal environment
        cfg = load_config(config_path)
        resolver = PathResolver.from_config(cfg)
        environment = resolver.describe()
        # Resolving every declared key catches a key present in config but
        # unusable, which is otherwise found only by the branch that needs it.
        for key in cfg["paths"]:
            resolver.write_dir(key)
        return f"mode={resolver.mode.value}, {len(cfg['paths'])} path keys resolved"

    checks.append(_check("config loads and paths resolve", _config_and_paths))

    def _cache_round_trip() -> str:
        from src.common.cache import ArtifactCache
        from src.common.config import load_config as _load
        from src.common.paths import PathResolver as _Resolver

        cfg = _load(config_path)
        cache = ArtifactCache.from_config(cfg, _Resolver.from_config(cfg), namespace="smoke")
        key = cache.key_for("foundation-smoke-check")
        cache.put(key, b"round trip")
        if cache.get(key) != b"round trip":
            raise AssertionError("cache round trip returned unexpected content")
        target = cache.write_target(key)
        target.unlink(missing_ok=True)
        return "cache write/read round trip succeeded"

    checks.append(_check("cache round trip", _cache_round_trip))

    failures = [c for c in checks if c["status"] == "FAIL"]
    return {
        "overall": "FAIL" if failures else "PASS",
        "checks": checks,
        "summary": {
            "checks_run": len(checks),
            "checks_passed": len(checks) - len(failures),
            "checks_failed": len(failures),
        },
        "environment": environment or NOT_MEASURED,
    }


def environment_versions() -> dict[str, str]:
    """Report the package versions actually present.

    ``requirements.txt`` records what we expect Kaggle's base image to provide;
    this records what it actually provided. The two disagreeing is exactly the
    kind of thing that is cheap to see now and expensive to debug later.
    """
    import platform

    versions = {"python": platform.python_version(), "platform": platform.platform()}
    for name in ("yaml", "pytest", "requests", "bs4", "lxml", "pandas", "numpy", "pdfplumber"):
        try:
            module = importlib.import_module(name)
            versions[name] = getattr(module, "__version__", "present (version unknown)")
        except ImportError:
            versions[name] = "NOT INSTALLED"
    return versions


def format_report(report: dict[str, Any]) -> str:
    """Render a report for a terminal or a notebook cell."""
    lines = ["Phase 0 foundation check", "=" * 40]
    for check in report["checks"]:
        marker = "PASS" if check["status"] == "PASS" else "FAIL"
        lines.append(f"[{marker}] {check['check']}: {check['detail']}")
    summary = report["summary"]
    lines.append("-" * 40)
    lines.append(f"{summary['checks_passed']}/{summary['checks_run']} checks passed")
    lines.append(f"Environment: {report['environment']}")
    lines.append(f"OVERALL: {report['overall']}")
    return "\n".join(lines)
