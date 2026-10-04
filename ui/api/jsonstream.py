"""Incremental JSON reader for the comparator's streamed output (Demo Build Spec H2).

`feed(chunk)` returns the scalar leaves that have *fully* parsed so far, as (path, value) pairs, e.g.
(("source", "actor"), "A bank") or (("candidates", 0, "field_comparison", "deadline"), "differs"). A value is emitted only
after its closing quote / delimiter has been read, so nothing is ever reported before the model has actually written it.
Leading text before the first "{" (for example a ``` fence) is skipped. Anything malformed raises JsonStreamError; the
caller then falls back to the buffered path (parse the complete text once), never to synthetic events.
"""

from __future__ import annotations

from typing import Any

_WS = " \t\r\n"
_LIT = {"true": True, "false": False, "null": None}


class JsonStreamError(ValueError):
    pass


class JsonStream:
    def __init__(self) -> None:
        self.started = False
        self.done = False
        self.stack: list[dict[str, Any]] = []  # frames: {"type": "obj"|"arr", "key": str|None, "index": int, "expect": ...}
        self.mode = "value"  # value | string | key | scalar | after
        self.buf: list[str] = []
        self.escape = False
        self.unicode: str | None = None
        self.string_is_key = False

    def _path(self) -> tuple:
        out: list[Any] = []
        for f in self.stack:
            if f["type"] == "obj":
                if f["key"] is not None:
                    out.append(f["key"])
            else:
                out.append(f["index"])
        return tuple(out)

    def _emit_value(self, value: Any, out: list) -> None:
        if self.stack:
            out.append((self._path(), value))
        self.mode = "after"

    def feed(self, chunk: str) -> list[tuple[tuple, Any]]:
        out: list[tuple[tuple, Any]] = []
        for ch in chunk:
            if self.done:
                if ch not in _WS and ch != "`":
                    raise JsonStreamError("text after the end of the JSON value")
                continue
            if not self.started:
                if ch == "{":
                    self.started = True
                    self.stack.append({"type": "obj", "key": None, "index": 0, "expect": "key"})
                    self.mode = "key_or_end"
                continue
            self._step(ch, out)
        return out

    def _step(self, ch: str, out: list) -> None:  # noqa: C901 - a small state machine
        m = self.mode
        if m == "string":
            if self.unicode is not None:
                self.unicode += ch
                if len(self.unicode) == 4:
                    self.buf.append(chr(int(self.unicode, 16)))
                    self.unicode = None
                return
            if self.escape:
                self.escape = False
                if ch == "u":
                    self.unicode = ""
                else:
                    self.buf.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}.get(ch, ch))
                return
            if ch == "\\":
                self.escape = True
                return
            if ch == '"':
                s = "".join(self.buf)
                self.buf = []
                if self.string_is_key:
                    self.stack[-1]["key"] = s
                    self.mode = "colon"
                else:
                    self._emit_value(s, out)
                return
            self.buf.append(ch)
            return
        if m == "scalar":
            if ch in _WS or ch in ",]}":
                tok = "".join(self.buf)
                self.buf = []
                if tok in _LIT:
                    v = _LIT[tok]
                else:
                    try:
                        v = float(tok) if any(c in tok for c in ".eE") else int(tok)
                    except ValueError as exc:
                        raise JsonStreamError(f"bad literal {tok!r}") from exc
                self._emit_value(v, out)
                self._step(ch, out)
                return
            self.buf.append(ch)
            return
        if ch in _WS:
            return
        if m in ("key_or_end", "key"):
            if ch == "}" and m == "key_or_end":
                self._close(out)
                return
            if ch != '"':
                raise JsonStreamError(f"expected a key, got {ch!r}")
            self.string_is_key = True
            self.mode = "string"
            return
        if m == "colon":
            if ch != ":":
                raise JsonStreamError("expected ':'")
            self.mode = "value"
            return
        if m in ("value", "value_or_end"):
            if ch == "]" and m == "value_or_end":
                self._close(out)
                return
            if ch == "{":
                self.stack.append({"type": "obj", "key": None, "index": 0})
                self.mode = "key_or_end"
            elif ch == "[":
                self.stack.append({"type": "arr", "key": None, "index": 0})
                self.mode = "value_or_end"
            elif ch == '"':
                self.string_is_key = False
                self.mode = "string"
            elif ch in "-0123456789tfn":
                self.mode = "scalar"
                self.buf = [ch]
            else:
                raise JsonStreamError(f"unexpected {ch!r}")
            return
        if m == "after":
            top = self.stack[-1]
            if ch == ",":
                if top["type"] == "obj":
                    top["key"] = None
                    self.mode = "key"
                else:
                    top["index"] += 1
                    self.mode = "value"
                return
            if (ch == "}" and top["type"] == "obj") or (ch == "]" and top["type"] == "arr"):
                self._close(out)
                return
            raise JsonStreamError(f"unexpected {ch!r} after a value")
        raise JsonStreamError(f"bad state {m}")

    def _close(self, out: list) -> None:
        self.stack.pop()
        if not self.stack:
            self.done = True
            self.mode = "done"
        else:
            self.mode = "after"
