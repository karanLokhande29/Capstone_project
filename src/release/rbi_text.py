"""RBI-text policy (P5-001 task 3): no run of >= 30 consecutive words copied from data/processed may appear in
anything public. Shorter quotations (with their paragraph_id) are allowed.

Detection: the corpus is tokenised into lower-case alphanumeric words and every 12-word window is hashed into a set
(hashed 12-word shingles). A text's words are marked where a 12-word window starting there is in the set; a copied run
is a maximal stretch of words covered by consecutive matching windows. A run of >= ``min_words`` words is a violation.
A copied run of length L produces L - 11 consecutive matching windows, so runs shorter than 12 words are never seen,
which is fine for a 30-word rule.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

SHINGLE = 12
MIN_RUN = 30
_WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _h(ws: Sequence[str]) -> int:
    return int.from_bytes(hashlib.blake2b(" ".join(ws).encode("utf-8"), digest_size=8).digest(), "big")


def shingles(ws: Sequence[str], k: int = SHINGLE) -> Iterable[int]:
    for i in range(len(ws) - k + 1):
        yield _h(ws[i:i + k])


class CorpusIndex:
    """Hashed k-word shingles of every paragraph in a processed corpus directory."""

    def __init__(self, hashes: set[int], k: int = SHINGLE):
        self.hashes = hashes
        self.k = k

    @classmethod
    def from_texts(cls, texts: Iterable[str], k: int = SHINGLE) -> "CorpusIndex":
        hs: set[int] = set()
        for t in texts:
            hs.update(shingles(words(t), k))
        return cls(hs, k)

    @classmethod
    def from_processed(cls, processed_dir: Path | str, k: int = SHINGLE) -> "CorpusIndex":
        def texts():
            for p in sorted(Path(processed_dir).glob("md_*.jsonl")):
                with p.open(encoding="utf-8", errors="replace") as h:
                    for line in h:
                        if line.strip():
                            yield json.loads(line)["text"]

        return cls.from_texts(texts(), k)


@dataclass
class Run:
    start_word: int
    length: int
    excerpt: str


def copied_runs(text: str, index: CorpusIndex, min_words: int = MIN_RUN) -> list[Run]:
    ws = words(text)
    k = index.k
    hit = [False] * len(ws)
    for i, h in enumerate(shingles(ws, k)):
        if h in index.hashes:
            for j in range(i, i + k):
                hit[j] = True
    runs, i = [], 0
    while i < len(ws):
        if hit[i]:
            j = i
            while j < len(ws) and hit[j]:
                j += 1
            if j - i >= min_words:
                runs.append(Run(i, j - i, " ".join(ws[i:min(j, i + 25)])))
            i = j
        else:
            i += 1
    return runs


def shorten(text: str, max_words: int = 25) -> str:
    """The first ``max_words`` words of a quotation, with an ellipsis if cut."""
    parts = text.split()
    return " ".join(parts[:max_words]) + (" …" if len(parts) > max_words else "")


def shorten_words(text: str, max_words: int = 25) -> str:
    """Like :func:`shorten`, but counts words the way the copied-text check does (alphanumeric runs: "9." and
    "Board-approved" count as one and two). The result never exceeds ``max_words`` such words."""
    out, n = [], 0
    toks = text.split()
    for tok in toks:
        k = len(words(tok))
        if n + k > max_words:
            break
        out.append(tok)
        n += k
    return " ".join(out) + (" …" if len(out) < len(toks) else "")


def shorten_copied_runs(text: str, index: CorpusIndex, *, keep_words: int = 25,
                        min_words: int = MIN_RUN) -> tuple[str, list[dict]]:
    """Cut every copied run of >= ``min_words`` words in ``text`` to its first ``keep_words`` words plus " […]".

    Returns the new text and one record per cut run (words kept and removed, and the 12-word excerpt that locates it).
    """
    lowered = (text or "").lower()
    spans = [(m.start(), m.end()) for m in _WORD.finditer(lowered)]
    runs = copied_runs(text, index, min_words)
    out, last, cuts = [], 0, []
    for r in runs:
        cut_from = spans[r.start_word + keep_words - 1][1]
        cut_to = spans[r.start_word + r.length - 1][1]
        out.append(text[last:cut_from] + " […]")
        last = cut_to
        cuts.append({"run_words": r.length, "kept_words": keep_words, "removed_words": r.length - keep_words,
                     "locator": " ".join(words(text)[r.start_word:r.start_word + SHINGLE])})
    out.append(text[last:])
    return "".join(out), cuts
