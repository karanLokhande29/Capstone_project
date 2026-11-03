"""P3-001 retrieval systems: RRF, class filtering, source exclusion, BM25 tokens, corpus loading."""

from __future__ import annotations

import json

import numpy as np
import pytest

from src.retrieval import index as IX
from src.retrieval import systems as S

CLASSES = np.array(["A", "A", "B", "B", "A"], dtype=object)


def test_ranks_within_and_zero_scores():
    scores = np.array([0.0, 3.0, 1.0, 3.0, 0.0])
    mask = np.ones(5, dtype=bool)
    assert list(S.ranks_within(scores, mask)) == [4, 1, 3, 2, 5]  # tie 1 vs 3 -> lower row first
    r = S.ranks_within(scores, mask, zero_is_unranked=True)
    assert list(r[[1, 3, 2]]) == [1, 2, 3] and np.isinf(r[0]) and np.isinf(r[4])


def test_rrf_hand_computed():
    bm25 = np.array([3.0, 2.0, 1.0, 0.0])
    dense = np.array([0.1, 0.9, 0.5, 0.7])
    mask = np.ones(4, dtype=bool)
    fused = S.rrf_scores([S.ranks_within(bm25, mask, zero_is_unranked=True), S.ranks_within(dense, mask)], 60)
    # bm25 ranks 1,2,3,- ; dense ranks 4,1,3,2
    expected = [1 / 61 + 1 / 64, 1 / 62 + 1 / 61, 1 / 63 + 1 / 63, 1 / 62]
    assert fused == pytest.approx(expected)
    ranked = S.rrf(bm25, dense, mask, k=60, depth=4)
    assert list(ranked.indices) == [1, 0, 2, 3]


def test_source_paragraph_is_always_excluded():
    bm25 = np.array([5.0, 1.0, 1.0, 1.0, 1.0])
    dense = np.array([1.0, 0.2, 0.3, 0.1, 0.4])
    out = S.run_query(bm25, dense, entity_class=CLASSES, source_index=0, target_class="A", rrf_k=60, depth=5)
    for r in out.values():
        assert 0 not in r.indices


def test_class_filter_restricts_and_flags():
    bm25 = np.array([1.0, 2.0, 9.0, 8.0, 0.5])
    dense = np.array([0.5, 0.4, 0.9, 0.8, 0.1])
    out = S.run_query(bm25, dense, entity_class=CLASSES, source_index=None, target_class="A", rrf_k=60, depth=5)
    assert set(out["class_aware"].indices) == {0, 1, 4}
    assert out["class_aware"].class_filter_applied
    assert set(out["hybrid_rrf"].indices) == {0, 1, 2, 3, 4}
    none = S.run_query(bm25, dense, entity_class=CLASSES, source_index=None, target_class=None, rrf_k=60, depth=5)
    assert list(none["class_aware"].indices) == list(none["hybrid_rrf"].indices)
    assert not none["class_aware"].class_filter_applied


def test_depth_caps_the_list():
    s = np.arange(10, dtype=float)
    out = S.run_query(s, s, entity_class=np.array(["A"] * 10, dtype=object), source_index=None,
                      target_class=None, rrf_k=60, depth=3)
    assert all(len(r.indices) == 3 for r in out.values())
    assert list(out["bm25"].indices) == [9, 8, 7]


def test_bm25_tokens_and_scores():
    assert IX.tokenize("The NBFC's KYC-2024 Norms!") == ["the", "nbfc", "s", "kyc", "2024", "norms"]
    idx = IX.BM25Index(["alpha beta", "beta gamma gamma", "delta"], method="lucene", k1=1.5, b=0.75,
                       token_regex="[a-z0-9]+")
    s = idx.scores("GAMMA")
    assert s[1] > 0 and s[0] == 0 and s[2] == 0
    assert (idx.scores("!!!") == 0).all() and len(idx.scores("!!!")) == 3


def test_corpus_loading_order_and_fingerprint(tmp_path):
    for md, rows in {"md_2": [("md_2::p00000", "B", "two")], "md_1": [("md_1::p00000", "A", "one"),
                                                                        ("md_1::p00001", "A", "one b")]}.items():
        (tmp_path / f"{md}.jsonl").write_text("".join(
            json.dumps({"paragraph_id": p, "entity_class": c, "text": t, "document_id": md}) + "\n"
            for p, c, t in rows))
    corpus = IX.load_corpus(tmp_path)
    assert corpus.ids == ["md_1::p00000", "md_1::p00001", "md_2::p00000"]
    assert corpus.index_of["md_2::p00000"] == 2 and list(corpus.entity_class) == ["A", "A", "B"]
    assert corpus.fingerprint() == IX.load_corpus(tmp_path).fingerprint()


def test_embeddings_checkpoint_and_resume(tmp_path):
    corpus = IX.Corpus(["p0", "p1", "p2"], ["a  b", "c", "d"], np.array(["A"] * 3, dtype=object), ["m"] * 3)
    calls = []

    def enc(texts):
        calls.append(list(texts))
        return np.ones((len(texts), 4), dtype=np.float32)

    mat, info = IX.build_embeddings(corpus, enc, tmp_path, meta={"model_id": "fake"}, chunk_size=2)
    assert mat.shape == (3, 4) and mat.dtype == np.float16 and info["paragraphs"] == 3
    assert calls[0] == ["a b", "c"]  # whitespace collapsed
    calls.clear()
    IX.build_embeddings(corpus, enc, tmp_path, meta={"model_id": "fake"}, chunk_size=2)
    assert calls == []  # every chunk resumed from disk
    loaded, _ = IX.load_embeddings(tmp_path, corpus)
    assert loaded.shape == (3, 4)
    other = IX.Corpus(["p0", "p1", "pX"], ["a", "c", "d"], np.array(["A"] * 3, dtype=object), ["m"] * 3)
    with pytest.raises(IX.RetrievalError):
        IX.load_embeddings(tmp_path, other)
