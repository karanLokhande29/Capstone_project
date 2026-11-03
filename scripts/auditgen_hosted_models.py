#!/usr/bin/env python3
"""Models and retrieval vectors for the hosted audit generator (ui/api_audit/).

    python3 scripts/auditgen_hosted_models.py export   OUT   # bge + NLI -> ONNX int8, tokenizer.json, meta.json
    python3 scripts/auditgen_hosted_models.py parity   OUT   # ONNX vs the local torch models on corpus pairs
    python3 scripts/auditgen_hosted_models.py vectors  OUT   # bge vectors of every register paragraph, 11 classes

Needs torch, transformers, onnx, onnxruntime and onnxscript (export) or onnxruntime + tokenizers (parity, vectors).
OUT is git-ignored (ui/api_audit/.build/models by default in ui/api_audit/package.py).
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auditgen.corpus import CorpusStore, load_config  # noqa: E402
from src.auditgen.gap_analysis import LocalModels, _snapshot  # noqa: E402


def export(out: Path) -> None:
    import onnx
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic
    from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

    g = load_config()["gap_analysis"]

    class Cls(torch.nn.Module):  # bge-base: CLS pooling, L2-normalised (its sentence-transformers config)
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask):
            return torch.nn.functional.normalize(self.m(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state[:, 0], dim=-1)

    class Logits(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, input_ids, attention_mask):
            return self.m(input_ids=input_ids, attention_mask=attention_mask).logits

    for name, key, wrap, auto in (("bge", "embedding", Cls, AutoModel), ("nli", "nli", Logits, AutoModelForSequenceClassification)):
        path = _snapshot(g[f"{key}_model"], g[f"{key}_revision"])
        tok = AutoTokenizer.from_pretrained(str(path))
        base = auto.from_pretrained(str(path), attn_implementation="eager").eval()
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        tok.save_pretrained(str(d))
        x = tok(["a sample sentence about deposits", "two"], ["second", "x"] if name == "nli" else None, return_tensors="pt", padding=True)
        b, t = torch.export.Dim("b", max=256), torch.export.Dim("t", max=512)
        fp32 = d / "model_fp32.onnx"
        torch.onnx.export(wrap(base), (x["input_ids"], x["attention_mask"]), str(fp32), input_names=["input_ids", "attention_mask"],
                          output_names=["out"], dynamic_shapes={"input_ids": {0: b, 1: t}, "attention_mask": {0: b, 1: t}},
                          opset_version=18, dynamo=True, external_data=False)
        m = onnx.load(str(fp32))
        del m.graph.value_info[:]  # stale shapes from the exporter break the quantiser's shape inference
        onnx.save(m, str(fp32))
        quantize_dynamic(str(fp32), str(d / "model.onnx"), weight_type=QuantType.QInt8, per_channel=True)
        fp32.unlink()
        meta = {"id": f"{g[f'{key}_model']}@{g[f'{key}_revision']}+onnx-int8", "pad_id": tok.pad_token_id, "pad_token": tok.pad_token}
        if name == "nli":
            labels = {int(k): v.lower() for k, v in base.config.id2label.items()}
            meta["entailment"] = next(k for k, v in labels.items() if v.startswith("entail"))
        (d / "meta.json").write_text(json.dumps(meta, indent=1))
        for f in d.iterdir():
            if f.name not in ("model.onnx", "tokenizer.json", "meta.json"):
                f.unlink()
        print(f"{name}: {(d / 'model.onnx').stat().st_size // 1_000_000} MB")


def parity(out: Path, n: int = 400) -> None:
    """Agreement of the hosted models with the local ones: NLI argmax-entailment decisions and bge cosine."""
    from src.auditgen.hosted import OnnxModels

    cfg = load_config()
    store = CorpusStore(cfg)
    rnd = random.Random(20261030)
    paras = [p for p in store.paragraphs.values() if 20 <= len((p.get("text") or "").split()) <= 200]
    picks = rnd.sample(paras, n)
    pairs = []
    for i, p in enumerate(picks):
        words = p["text"].split()
        same = " ".join(words[: max(8, len(words) // 3)])
        other = " ".join(picks[(i + 1) % n]["text"].split()[:20])
        pairs += [(p["text"], same), (p["text"], other)]
    local, hosted = LocalModels.get(cfg), OnnxModels(out)
    pl, al = local.nli_scores(pairs)
    ph, ah = hosted.nli_scores(pairs)
    texts = [p["text"] for p in picks[:200]]
    cos = (local.embed(texts) * hosted.embed(texts)).sum(-1)
    q = local.embed(texts[:50]) @ local.embed(texts).T
    qh = hosted.embed(texts[:50]) @ hosted.embed(texts).T
    top = float(np.mean([len(set(np.argsort(-a)[1:6]) & set(np.argsort(-b)[1:6])) / 5 for a, b in zip(q, qh)]))
    res = {"nli_pairs": len(pairs), "nli_decision_agreement": round(float(np.mean(al == ah)), 4),
           "nli_entailed_local": int(al.sum()), "nli_entailed_hosted": int(ah.sum()),
           "nli_p_mean_abs_diff": round(float(np.mean(np.abs(pl - ph))), 4),
           "bge_cosine_min": round(float(cos.min()), 4), "bge_cosine_mean": round(float(cos.mean()), 4), "bge_top5_overlap": round(top, 4)}
    (out / "parity.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


def vectors(out: Path) -> None:
    """bge vectors of every register paragraph for all 11 classes (every activity, hidden rows included), in the
    Retriever's own cache format, so the hosted service never embeds RBI text at request time."""
    from src.auditgen import ai_features as AI
    from src.auditgen import genai as G
    from src.auditgen import pack as PK
    from src.auditgen.hosted import OnnxModels
    from src.auditgen.profile import ACTIVITIES, Profile

    cfg = load_config()
    gcfg = G.load_genai_config()
    store = CorpusStore(cfg)
    models = OnnxModels(out)
    a = gcfg["ask"]
    docs: dict[str, str] = {}
    for cls in store.core_classes:
        prof = Profile(name="vectors", entity_class=cls, as_of=time.strftime("%Y-%m-%d"), last_review="2025-01-01",
                       activities=list(ACTIVITIES), group_classes=[])
        for r in PK.generate(store, cfg, prof)["register"]:
            pid = r.get("paragraph_id")
            if pid and pid not in docs:
                t = G.words(AI.para_text(store, pid) or r.get("excerpt") or "", int(a["passage_max_words"]))
                docs[pid] = f"{r['direction_title']}. {t}"
    ids = sorted(docs)
    t0 = time.time()
    vecs = models.embed([docs[i] for i in ids], batch=32)
    path = out / "vectors" / f"emb_{store.snapshot.sha256[:12]}_{G.sha(models.ids['embedding'])[:8]}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, ids=np.array(ids), vecs=vecs.astype(np.float32))
    print(f"{len(ids)} paragraphs embedded in {time.time() - t0:.0f} s -> {path.relative_to(out)}")


if __name__ == "__main__":
    cmd, out = sys.argv[1], Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "ui/api_audit/.build/models").resolve()
    {"export": export, "parity": parity, "vectors": vectors}[cmd](out)
