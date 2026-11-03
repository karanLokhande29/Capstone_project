"""Rebuild rules for derived texts in the pointer-only release (P5-001 task 4).

Each rule turns corpus paragraphs (rehydrated from RBI's URLs) back into the exact text used in the benchmark; the
release stores the rule, the pointers and the sha256 of the result, never the text.

- ``span_text``: a T1 obligation span / T2 query, ``" … ".join`` of whitespace-collapsed character ranges.
- ``raw_slice``: a P2-002 query, the raw character range.
- ``spans_text``: T4 concatenated / off-topic answers, ``" ".join`` of whitespace-collapsed sentence ranges.
- ``negate(concatenated)``: the T4 negated answer (src/t4/audit.py).
"""

from __future__ import annotations

from typing import Mapping, Sequence

from src.t4.audit import collapse, kept_sentence_spans, negate  # noqa: F401  (negate re-exported)


def span_text(text: str, units: Sequence[Sequence[int]]) -> str:
    return " … ".join(" ".join(text[s:e].split()) for s, e in units)


def raw_slice(text: str, units: Sequence[Sequence[int]]) -> str:
    (s, e), = units
    return text[s:e]


def _kept(pid: str, raw: Mapping[str, str], cands: Mapping[str, Mapping]) -> list[tuple[int, int]]:
    c = cands.get(pid)
    if not c or c.get("exclusion_reason"):
        return []
    return [(a, b) for a, b in kept_sentence_spans(raw[pid], c["cue_position"], c["cue_exclusions"]) if collapse(raw[pid][a:b])]


def concat_rule_spans(pids: Sequence[str], raw: Mapping[str, str], cands: Mapping[str, Mapping]) -> list[tuple[str, int, int]]:
    """Sentence spans of src.t4.audit.concatenated_answer, in order, de-duplicated by text."""
    seen, out = set(), []
    for pid in pids:
        for a, b in _kept(pid, raw, cands):
            s = collapse(raw[pid][a:b])
            if s not in seen:
                seen.add(s)
                out.append((pid, a, b))
    return out


def offtopic_rule_spans(md_ids: Sequence[str], target_chars: int, raw: Mapping[str, str], md_of: Mapping[str, str],
                        cands: Mapping[str, Mapping]) -> list[tuple[str, int, int]]:
    """Sentence spans of src.t4.audit.offtopic_answer for the Directions it used, in the order it used them."""
    by_md: dict[str, list[str]] = {}
    for pid in raw:
        by_md.setdefault(md_of[pid], []).append(pid)
    out, length = [], -1
    for m in md_ids:
        for pid in by_md.get(m, []):
            for a, b in _kept(pid, raw, cands):
                out.append((pid, a, b))
                length += 1 + len(collapse(raw[pid][a:b]))
                if length >= target_chars:
                    return out
    return out


def spans_text(spans: Sequence[Sequence], raw: Mapping[str, str]) -> str:
    return " ".join(collapse(raw[p][a:b]) for p, a, b in spans)
