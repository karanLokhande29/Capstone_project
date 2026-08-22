"""Serialisation helpers shared by every branch.

Two properties matter more than convenience here:

1. **Atomic writes.** A Kaggle session that hits its time limit mid-write leaves
   a truncated file that looks valid to the next run. Every write goes to a
   temporary file in the same directory and is then atomically renamed.
2. **Errors that name the file and the line.** A ``JSONDecodeError`` from a
   68k-line JSONL file is useless without the line number, so parse failures are
   re-raised as :class:`~src.common.errors.IOFormatError` with that context.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.common.errors import IOFormatError

DEFAULT_ENCODING = "utf-8"


def _json_default(value: Any) -> Any:
    """Serialise the handful of types we deliberately support.

    Notably *not* a blanket ``default=str``. Coercing an arbitrary object to its
    repr would let a bug — a dataclass instance where a dict was expected, say —
    land in a corpus file as a plausible-looking string and survive every
    downstream check. Anything not handled here raises, which is the point.
    """
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serialisable")


# -- primitives ---------------------------------------------------------------


def atomic_write_bytes(path: Path | str, data: bytes) -> Path:
    """Write ``data`` to ``path`` atomically, creating parent directories."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def atomic_write_text(path: Path | str, text: str, *, encoding: str = DEFAULT_ENCODING) -> Path:
    """Write ``text`` to ``path`` atomically."""
    return atomic_write_bytes(path, text.encode(encoding))


def read_bytes(path: Path | str) -> bytes:
    """Read raw bytes, raising :class:`IOFormatError` with path context on failure."""
    path = Path(path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise IOFormatError(f"Could not read {path}: {exc}") from exc


def read_text(path: Path | str, *, encoding: str = DEFAULT_ENCODING) -> str:
    """Read text, replacing undecodable bytes rather than failing a whole run.

    Regulatory PDFs extract to text containing occasional invalid sequences;
    losing one character is preferable to losing the document.
    """
    path = Path(path)
    try:
        return path.read_text(encoding=encoding, errors="replace")
    except OSError as exc:
        raise IOFormatError(f"Could not read {path}: {exc}") from exc


def write_text(path: Path | str, text: str, *, encoding: str = DEFAULT_ENCODING) -> Path:
    """Alias for :func:`atomic_write_text`, named for symmetry with :func:`read_text`."""
    return atomic_write_text(path, text, encoding=encoding)


# -- JSON ---------------------------------------------------------------------


def read_json(path: Path | str) -> Any:
    """Parse a JSON document."""
    path = Path(path)
    raw = read_text(path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IOFormatError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc


def write_json(path: Path | str, data: Any, *, indent: int | None = 2, sort_keys: bool = False) -> Path:
    """Serialise ``data`` as JSON, atomically.

    ``ensure_ascii`` is off throughout this module: RBI titles contain en-dashes
    and other non-ASCII characters that are far easier to diff unescaped.
    """
    try:
        text = json.dumps(
            data, indent=indent, ensure_ascii=False, sort_keys=sort_keys, default=_json_default
        )
    except (TypeError, ValueError) as exc:
        raise IOFormatError(f"Could not serialise data for {path} as JSON: {exc}") from exc
    return atomic_write_text(path, text + "\n")


# -- JSONL --------------------------------------------------------------------


def iter_jsonl(path: Path | str, *, skip_blank: bool = True) -> Iterator[dict[str, Any]]:
    """Stream a JSONL file one record at a time.

    Preferred over :func:`read_jsonl` for corpus-scale files, which are large
    enough that materialising them costs real memory on a Kaggle kernel.
    """
    path = Path(path)
    try:
        handle = path.open("r", encoding=DEFAULT_ENCODING, errors="replace")
    except OSError as exc:
        raise IOFormatError(f"Could not read {path}: {exc}") from exc
    with handle:
        for lineno, line in enumerate(handle, start=1):
            if skip_blank and not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise IOFormatError(f"{path} line {lineno} is not valid JSON: {exc.msg}") from exc


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    """Read an entire JSONL file into a list."""
    return list(iter_jsonl(path))


def write_jsonl(path: Path | str, records: Iterable[Any]) -> Path:
    """Write ``records`` as JSONL, atomically.

    Records are serialised into memory before the rename, so a serialisation
    failure partway through leaves the previous file untouched.
    """
    lines: list[str] = []
    for index, record in enumerate(records):
        try:
            lines.append(json.dumps(record, ensure_ascii=False, default=_json_default))
        except (TypeError, ValueError) as exc:
            raise IOFormatError(f"Could not serialise record {index} for {path}: {exc}") from exc
    payload = "".join(line + "\n" for line in lines)
    return atomic_write_text(path, payload)


def count_jsonl(path: Path | str) -> int:
    """Count non-blank lines without parsing them."""
    path = Path(path)
    try:
        with path.open("r", encoding=DEFAULT_ENCODING, errors="replace") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError as exc:
        raise IOFormatError(f"Could not read {path}: {exc}") from exc
