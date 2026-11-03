"""P5-001 housekeeping: `run_t1.py ingest-timed --corrects` (an authorised, versioned correction of a rater's file)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def rt1():
    spec = importlib.util.spec_from_file_location("run_t1_under_test", ROOT / "scripts" / "run_t1.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resolver:
    def __init__(self, root: Path):
        self.root = root

    def write_dir(self, name: str) -> Path:
        d = self.root / "data" / name
        d.mkdir(parents=True, exist_ok=True)
        return d


def _setup(rt1, tmp_path, monkeypatch):
    T = rt1.T
    res = _Resolver(tmp_path)
    d = rt1.tdir(res)
    blank = d / T.TIMED_SHEET
    blank.write_text("item_id,compared_class,judgement\n", encoding="utf-8")
    (d / T.TIMED_SENDLOG_FILE).write_text(json.dumps({
        "sheet_sha256": hashlib.sha256(blank.read_bytes()).hexdigest(), "blocks": [], "purpose": "timed re-label"}))
    completed = tmp_path / "timed_completed_v2.csv"
    completed.write_text("item_id,compared_class,judgement\nx,A,same\n", encoding="utf-8")
    original = tmp_path / "timed_completed.csv"
    original.write_text("item_id,compared_class,judgement\nx,A,sam\n", encoding="utf-8")
    minutes = tmp_path / "minutes.csv"
    minutes.write_text("block,minutes\n1,10\n", encoding="utf-8")
    monkeypatch.setattr(T, "validate_annotation_file", lambda *a, **k: {"problems": [], "has_bom": False, "rows": 1, "items": 1})
    monkeypatch.setattr(T, "timed_block_minutes", lambda *a, **k: ([{"block": 1, "minutes": 10}], []))
    monkeypatch.setattr(rt1, "paragraph_classes", lambda resolver: {})
    return res, d, completed, original, minutes


def test_corrects_is_receipted_with_both_files(rt1, tmp_path, monkeypatch):
    res, d, completed, original, minutes = _setup(rt1, tmp_path, monkeypatch)
    rec = rt1.run_ingest_timed(None, res, None, str(completed), str(minutes), "manual",
                               corrects=str(original), correction_note="fixed one typo ('sam' -> 'same') in row 1")
    corr = rec["correction"]
    assert corr["corrects_sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert corr["note"].startswith("fixed one typo")
    assert rec["sha256"] == hashlib.sha256(completed.read_bytes()).hexdigest()
    store = d / rt1.T.TIMED_RECEIVED_DIR
    for f in (completed, original, minutes):
        kept = store / f.name
        assert kept.read_bytes() == f.read_bytes()
        assert not kept.stat().st_mode & stat.S_IWUSR  # stored read-only
    assert json.loads((d / rt1.T.TIMED_RECEIPTS_FILE).read_text())["correction"] == corr


@pytest.mark.parametrize("missing", ["note", "original"])
def test_corrects_without_note_or_original_is_refused_before_any_write(rt1, tmp_path, monkeypatch, missing):
    res, d, completed, original, minutes = _setup(rt1, tmp_path, monkeypatch)
    corrects = str(tmp_path / "no_such_file.csv") if missing == "original" else str(original)
    note = None if missing == "note" else "a note"
    with pytest.raises(rt1.T.T1Error, match="--corrects needs"):
        rt1.run_ingest_timed(None, res, None, str(completed), str(minutes), "manual", corrects=corrects, correction_note=note)
    assert not (d / rt1.T.TIMED_RECEIPTS_FILE).exists()
    assert not (d / rt1.T.TIMED_RECEIVED_DIR).exists()


def test_a_second_submission_is_refused(rt1, tmp_path, monkeypatch):
    res, d, completed, original, minutes = _setup(rt1, tmp_path, monkeypatch)
    rt1.run_ingest_timed(None, res, None, str(completed), str(minutes), "manual", corrects=str(original), correction_note="n")
    with pytest.raises(rt1.T.T1Error, match="already received"):
        rt1.run_ingest_timed(None, res, None, str(completed), str(minutes), "manual", corrects=str(original), correction_note="n")
