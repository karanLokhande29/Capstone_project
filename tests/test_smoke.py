"""Integration smoke test (Phase 0, Section U).

Confirms the repository is importable end to end with no circular dependencies
or missing package markers, that the shipped config loads, and that the shared
utilities work together. This is the check that says three branches can safely
fork from this base.
"""

from __future__ import annotations

import pytest

from src.common.config import REPO_ROOT
from src.common.verify import BRANCH_MODULES, FOUNDATION_MODULES, format_report, run_foundation_check


@pytest.fixture(scope="module")
def report():
    return run_foundation_check()


def test_foundation_check_passes(report):
    failed = [c for c in report["checks"] if c["status"] != "PASS"]
    assert report["overall"] == "PASS", f"failing checks: {failed}"


@pytest.mark.parametrize("name", FOUNDATION_MODULES)
def test_foundation_module_imports(name):
    __import__(name)


@pytest.mark.parametrize("name", BRANCH_MODULES)
def test_branch_module_imports(name):
    """Stubs must import cleanly; a broken import here blocks all three branches."""
    __import__(name)


def test_report_is_renderable(report):
    text = format_report(report)
    assert "OVERALL: PASS" in text


def test_report_records_the_environment(report):
    assert report["environment"]["mode"] in {"local", "kaggle"}


def test_end_to_end_utilities_compose(tmp_path):
    """Config -> resolver -> logger -> I/O -> schema, the way a branch will use them."""
    from src.common.config import load_config
    from src.common.io_helpers import read_jsonl, write_jsonl
    from src.common.logging_setup import get_logger, reset_logger
    from src.common.paths import PathResolver
    from src.schemas.provenance import ParagraphRecord, stable_paragraph_id

    cfg = load_config()
    resolver = PathResolver.from_config(cfg, repo_root=tmp_path)
    logger = get_logger("smoke.compose", cfg, resolver=resolver)
    logger.info("composing foundation utilities")

    records = [
        ParagraphRecord(
            paragraph_id=stable_paragraph_id("md_smoke", i),
            document_id="md_smoke",
            position=i,
            text=f"paragraph {i}",
        )
        for i in range(3)
    ]
    for record in records:
        assert record.is_valid()

    target = resolver.write_path("processed", "smoke.jsonl")
    write_jsonl(target, [r.to_dict() for r in records])

    restored = [ParagraphRecord.from_dict(r) for r in read_jsonl(resolver.read_path("processed", "smoke.jsonl"))]
    assert restored == records
    reset_logger("smoke.compose")


def test_every_interface_stub_raises_not_implemented():
    """A stub that silently returns None would be worse than one that raises."""
    import importlib
    import inspect

    checked = 0
    for name in BRANCH_MODULES:
        if not name.endswith(".interfaces"):
            continue
        module = importlib.import_module(name)
        for _, fn in inspect.getmembers(module, inspect.isfunction):
            if fn.__module__ != module.__name__:
                continue
            signature = inspect.signature(fn)
            args = [None] * len(
                [
                    p
                    for p in signature.parameters.values()
                    if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty
                ]
            )
            with pytest.raises(NotImplementedError, match="phase1/"):
                fn(*args)
            checked += 1
    assert checked >= 15, f"expected the full interface surface, checked only {checked}"


def test_config_shipped_with_the_repo_is_the_one_checked(report):
    detail = next(c["detail"] for c in report["checks"] if c["check"] == "config loads and paths resolve")
    assert "path keys resolved" in detail


def test_repo_root_points_at_this_repository():
    assert (REPO_ROOT / "src" / "common" / "config.py").exists()
    assert (REPO_ROOT / "config" / "config.yaml").exists()
