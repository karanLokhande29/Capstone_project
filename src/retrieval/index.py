"""The paragraph corpus, its BM25 index and its dense embeddings (P3-001).

* Paragraphs are read from ``data/processed`` in sorted file order, so row ``i``
  of every index is the same paragraph on every run. The id list is
  fingerprinted and checked against the embedding file before use.
* BM25: ``bm25s`` over lower-case alphanumeric tokens (``[a-z0-9]+``), no
  stemming, no stopwords; parameters from ``retrieval.bm25``.
* Dense: ``BAAI/bge-base-en-v1.5`` at the pinned revision (asserted against the
  Hub), whitespace-collapsed text as in P2-002, no query instruction (queries
  are obligation passages, matched passage-to-passage as in P2-002), unit-norm
  vectors stored as float16. Embedding is checkpointed in chunks, so an
  interrupted run resumes.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from src.common.io_helpers import write_json

EMBEDDINGS_FILE = "p3001_bge_paragraphs_v1.npy"
EMBEDDINGS_META = "p3001_bge_paragraphs_v1_meta.json"
CHUNK_DIR = "p3001_bge_chunks_v1"
CHUNK_SIZE = 8192


class RetrievalError(RuntimeError):
    pass


@dataclass
class Corpus:
    ids: list[str]
    texts: list[str]
    entity_class: np.ndarray  # object array, one raw class per paragraph
    md_id: list[str]

    def __post_init__(self) -> None:
        self.index_of = {pid: i for i, pid in enumerate(self.ids)}

    def __len__(self) -> int:
        return len(self.ids)

    def fingerprint(self) -> str:
        return hashlib.sha256("\n".join(self.ids).encode("utf-8")).hexdigest()


def load_corpus(processed_dir: Path | str) -> Corpus:
    ids, texts, classes, mds = [], [], [], []
    for path in sorted(Path(processed_dir).glob("md_*.jsonl")):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                r = json.loads(line)
                ids.append(r["paragraph_id"])
                texts.append(r["text"])
                classes.append(r["entity_class"])
                mds.append(r["document_id"])
    if len(set(ids)) != len(ids):
        raise RetrievalError("duplicate paragraph ids in data/processed")
    return Corpus(ids, texts, np.array(classes, dtype=object), mds)


def embedding_text(text: str) -> str:
    """Whitespace collapsed, case kept: what P2-002 embedded."""
    return " ".join(text.split())


# -- BM25 ---------------------------------------------------------------------


def tokenize(text: str, pattern: str = "[a-z0-9]+") -> list[str]:
    return re.findall(pattern, text.lower())


class BM25Index:
    def __init__(self, texts: Sequence[str], *, method: str, k1: float, b: float, token_regex: str) -> None:
        import bm25s

        self.token_regex = token_regex
        self.params = {"method": method, "k1": k1, "b": b, "token_regex": token_regex}
        self.n_docs = len(texts)
        self._bm25 = bm25s.BM25(method=method, k1=k1, b=b)
        self._bm25.index([tokenize(t, token_regex) for t in texts], show_progress=False)

    @classmethod
    def from_config(cls, texts: Sequence[str], conf: Mapping[str, Any]) -> "BM25Index":
        return cls(texts, method=str(conf["method"]), k1=float(conf["k1"]), b=float(conf["b"]),
                   token_regex=str(conf["token_regex"]))

    def scores(self, query: str) -> np.ndarray:
        tokens = tokenize(query, self.token_regex)
        if not tokens:
            return np.zeros(self.n_docs, dtype=np.float32)
        return np.asarray(self._bm25.get_scores(tokens), dtype=np.float32)


# -- dense --------------------------------------------------------------------


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(model_id: str, revision: str, *, device: str, max_seq_length: int) -> Any:
    """Load the pinned model; stop if the Hub resolves the revision to anything else."""
    from huggingface_hub import model_info
    from sentence_transformers import SentenceTransformer

    resolved = model_info(model_id, revision=revision).sha
    if resolved != revision:
        raise RetrievalError(f"STOP: {model_id} revision resolved to {resolved}, pinned {revision}")
    model = SentenceTransformer(model_id, revision=revision, device=device)
    model.max_seq_length = max_seq_length
    return model


def count_truncated(model: Any, texts: Sequence[str], max_seq_length: int, batch: int = 4096) -> int:
    """Texts whose tokenisation (special tokens included) exceeds ``max_seq_length``."""
    over = 0
    for i in range(0, len(texts), batch):
        enc = model.tokenizer(list(texts[i:i + batch]), add_special_tokens=True, truncation=False)["input_ids"]
        over += sum(1 for ids in enc if len(ids) > max_seq_length)
    return over


def encode(model: Any, texts: Sequence[str], batch_size: int) -> np.ndarray:
    return model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True,
                        convert_to_numpy=True, show_progress_bar=False).astype(np.float32)


def build_embeddings(
    corpus: Corpus,
    encoder: Callable[[Sequence[str]], np.ndarray],
    out_dir: Path,
    *,
    meta: Mapping[str, Any],
    chunk_size: int = CHUNK_SIZE,
    progress: Callable[[int, int, float], None] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Embed every paragraph in checkpointed chunks, then write one float16 matrix + its meta."""
    chunk_dir = out_dir / CHUNK_DIR
    chunk_dir.mkdir(parents=True, exist_ok=True)
    fp = corpus.fingerprint()
    stamp = chunk_dir / "fingerprint.txt"
    if stamp.exists() and stamp.read_text().strip() != fp:
        raise RetrievalError(f"{chunk_dir} holds chunks for a different corpus; delete it and rerun")
    stamp.write_text(fp)
    texts = [embedding_text(t) for t in corpus.texts]
    started = time.time()
    parts = []
    for start in range(0, len(texts), chunk_size):
        path = chunk_dir / f"chunk_{start:06d}.npy"
        if path.exists():
            parts.append(np.load(path))
            continue
        vec = encoder(texts[start:start + chunk_size]).astype(np.float16)
        np.save(path, vec)
        parts.append(vec)
        if progress is not None:
            progress(start + len(vec), len(texts), time.time() - started)
    matrix = np.concatenate(parts, axis=0)
    if matrix.shape[0] != len(corpus):
        raise RetrievalError(f"embedded {matrix.shape[0]} rows for {len(corpus)} paragraphs")
    info = {
        **meta,
        "paragraphs": len(corpus),
        "ids_sha256": fp,
        "dim": int(matrix.shape[1]),
        "dtype": "float16",
        "embed_seconds_this_run": round(time.time() - started, 1),
        "machine": platform.machine(),
    }
    np.save(out_dir / EMBEDDINGS_FILE, matrix)
    write_json(out_dir / EMBEDDINGS_META, info)
    return matrix, info


def load_embeddings(out_dir: Path, corpus: Corpus) -> tuple[np.ndarray, dict[str, Any]]:
    meta = json.loads((out_dir / EMBEDDINGS_META).read_text(encoding="utf-8"))
    if meta["ids_sha256"] != corpus.fingerprint():
        raise RetrievalError("embedding file was built for a different paragraph list")
    return np.load(out_dir / EMBEDDINGS_FILE), meta


def iter_batches(seq: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
