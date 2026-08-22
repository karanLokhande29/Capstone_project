"""I/O helpers: atomicity, and errors that say which file and which line."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.common.errors import IOFormatError
from src.common.io_helpers import (
    atomic_write_bytes,
    atomic_write_text,
    count_jsonl,
    iter_jsonl,
    read_bytes,
    read_json,
    read_jsonl,
    read_text,
    write_json,
    write_jsonl,
)


# -- round trips --------------------------------------------------------------


def test_text_round_trip(tmp_path: Path):
    path = tmp_path / "a.txt"
    atomic_write_text(path, "hello")
    assert read_text(path) == "hello"


def test_bytes_round_trip(tmp_path: Path):
    path = tmp_path / "a.bin"
    atomic_write_bytes(path, b"\x00\x01\x02")
    assert read_bytes(path) == b"\x00\x01\x02"


def test_json_round_trip(tmp_path: Path):
    path = tmp_path / "a.json"
    data = {"document_id": "md_1", "count": 3, "nested": {"ok": True}}
    write_json(path, data)
    assert read_json(path) == data


def test_jsonl_round_trip(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    records = [{"i": i} for i in range(5)]
    write_jsonl(path, records)
    assert read_jsonl(path) == records
    assert count_jsonl(path) == 5


def test_non_ascii_is_not_escaped(tmp_path: Path):
    """RBI titles use en-dashes; escaped output is unreadable in a diff."""
    path = tmp_path / "a.json"
    write_json(path, {"title": "Commercial Banks – KYC"})
    assert "–" in path.read_text(encoding="utf-8")


def test_parents_are_created(tmp_path: Path):
    path = tmp_path / "deep" / "deeper" / "a.txt"
    atomic_write_text(path, "x")
    assert path.exists()


# -- atomicity ----------------------------------------------------------------


def test_failed_write_leaves_previous_file_intact(tmp_path: Path):
    """A serialisation failure must not truncate the file that was already there."""
    path = tmp_path / "a.json"
    write_json(path, {"good": 1})

    class Unserialisable:
        __slots__ = ()

    with pytest.raises(IOFormatError):
        write_jsonl(path, [{"bad": Unserialisable()}, object()])

    assert read_json(path) == {"good": 1}


def test_no_temp_files_left_behind(tmp_path: Path):
    path = tmp_path / "a.txt"
    atomic_write_text(path, "x")
    assert [p.name for p in tmp_path.iterdir()] == ["a.txt"]


def test_overwrite_replaces_content(tmp_path: Path):
    path = tmp_path / "a.txt"
    atomic_write_text(path, "first")
    atomic_write_text(path, "second")
    assert read_text(path) == "second"


# -- error reporting ----------------------------------------------------------


def test_missing_file_raises_io_format_error(tmp_path: Path):
    with pytest.raises(IOFormatError, match="Could not read"):
        read_text(tmp_path / "nope.txt")


def test_invalid_json_reports_line_and_column(tmp_path: Path):
    path = tmp_path / "a.json"
    path.write_text('{"a": 1,\n "b": }\n', encoding="utf-8")
    with pytest.raises(IOFormatError, match="line 2"):
        read_json(path)


def test_invalid_jsonl_reports_the_offending_line(tmp_path: Path):
    """The line number is the whole point when the file has 68k lines."""
    path = tmp_path / "a.jsonl"
    path.write_text('{"a": 1}\n{"b": 2}\nNOT JSON\n{"c": 3}\n', encoding="utf-8")
    with pytest.raises(IOFormatError, match="line 3"):
        read_jsonl(path)


def test_unserialisable_record_names_its_index(tmp_path: Path):
    with pytest.raises(IOFormatError, match="record 1"):
        write_jsonl(tmp_path / "a.jsonl", [{"ok": 1}, {"bad": object()}])


# -- streaming and edge cases -------------------------------------------------


def test_iter_jsonl_streams_lazily(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    write_jsonl(path, [{"i": i} for i in range(3)])
    stream = iter_jsonl(path)
    assert next(stream) == {"i": 0}
    stream.close()


def test_blank_lines_are_skipped(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    path.write_text('{"a": 1}\n\n\n{"b": 2}\n', encoding="utf-8")
    assert read_jsonl(path) == [{"a": 1}, {"b": 2}]
    assert count_jsonl(path) == 2


def test_empty_jsonl_is_empty_not_an_error(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    write_jsonl(path, [])
    assert read_jsonl(path) == []


def test_undecodable_bytes_are_replaced_not_fatal(tmp_path: Path):
    """One bad byte from a PDF extraction must not cost the whole document."""
    path = tmp_path / "a.txt"
    path.write_bytes(b"valid \xff\xfe text")
    assert "valid" in read_text(path)


def test_supported_types_are_serialised(tmp_path: Path):
    """Dates, paths, enums and sets are handled deliberately, not by str() fallback."""
    import enum
    from datetime import date

    class Flag(enum.Enum):
        SHARED = "shared"

    path = tmp_path / "a.json"
    write_json(path, {"d": date(2026, 1, 1), "p": Path("data/raw"), "e": Flag.SHARED, "s": {1}})
    assert read_json(path) == {"d": "2026-01-01", "p": "data/raw", "e": "shared", "s": [1]}


def test_unsupported_type_raises_rather_than_becoming_its_repr(tmp_path: Path):
    """A blanket default=str would write '<object at 0x...>' into a corpus file."""

    class Custom:
        pass

    with pytest.raises(IOFormatError, match="not JSON serialisable"):
        write_json(tmp_path / "a.json", {"x": Custom()})
