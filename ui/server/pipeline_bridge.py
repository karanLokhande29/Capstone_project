#!/usr/bin/env python3
"""Live-mode bridge (opt-in): the real class-aware retrieval + the frozen comparator prompt and rule.

Protocol: one JSON object per line on stdin -> one JSON object per line on stdout.
- {"cmd": "ping"}
- {"cmd": "prepare", "target_class": str, "source_pid": str | null, "text": str | null, "source_class": str | null}
    -> candidates (top-2 of the class-aware hybrid RRF within the target class), the comparator messages, pointers.
- {"cmd": "decide", "raw": str, "candidate_ids": [str], "source_pid": str | null, "source_class": str | null}
    -> the frozen rule's verdict, field statuses, M2 features.

What it does and never does:
- No LLM call is made here: the Node proxy calls the model with ASSISTANT_GEMINI_API_KEY and passes the raw reply back.
- Retrieval is src/retrieval/systems.run_query (class filter = target class).
  - Dense query: the stored bge-base-en-v1.5 embedding for an existing corpus paragraph.
  - Free text: encoded locally with the pinned revision a5beb1e3… (HF offline; the snapshot commit is asserted).
- The prompt comes from src/rag/comparator.Prompts with FROZEN.json hashes checked; the verdict from comparator_rule.class_verdict.
- Text returned to the UI: pointers + ≤ 25 words per paragraph. The model sees the full paragraphs (local) as in the benchmark.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UI / "scripts"))

import numpy as np  # noqa: E402

import cc_common as C  # noqa: E402
from src.rag import comparator as CMP  # noqa: E402
from src.rag import comparator_rule as RULE  # noqa: E402

MODEL_ID = "BAAI/bge-base-en-v1.5"
MODEL_REV = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
DEPTH = 2  # the comparator compares two candidates, as in the benchmark


class Bridge:
    def __init__(self, encoder=None):
        from src.common.config import load_config
        from src.retrieval import index as IX

        self.IX = IX
        cfg = load_config(None)
        self.rc = cfg["retrieval"]
        self.corpus = IX.load_corpus(ROOT / "data/processed")
        self.pos = {pid: i for i, pid in enumerate(self.corpus.ids)}
        self.bm25 = IX.BM25Index.from_config(self.corpus.texts, self.rc["bm25"])
        emb, _ = IX.load_embeddings(ROOT / "data/indexes", self.corpus)
        self.emb = np.asarray(emb, dtype=np.float32)
        frozen = json.loads((ROOT / "configs/comparator_v1/FROZEN.json").read_text())
        self.prompts = CMP.Prompts(ROOT / "configs/comparator_v1", expected=frozen["sha256"])
        self._encoder = encoder
        docs = C.read_jsonl(ROOT / "release/data/documents.jsonl")
        self.docs = {d["md_id"]: d for d in docs}
        self.amended = {k for k, d in self.docs.items() if "Updated as on" in (d.get("title") or "")}
        self.cells = {(m["entity_class"], m["subject_family"]): m["ambiguous"] for m in C.read_jsonl(ROOT / "release/data/matrix/matrix_v1.jsonl")}
        self.classes = sorted(set(self.corpus.entity_class.tolist()))

    # -- encoding ------------------------------------------------------------------------------------------------
    def encoder(self):
        if self._encoder is None:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            from huggingface_hub import snapshot_download
            from sentence_transformers import SentenceTransformer

            path = snapshot_download(MODEL_ID, revision=MODEL_REV, local_files_only=os.environ.get("LIVE_ALLOW_MODEL_DOWNLOAD") != "1")
            if Path(path).name != MODEL_REV:
                raise RuntimeError(f"STOP: {MODEL_ID} resolved to {Path(path).name}, pinned {MODEL_REV}")
            m = SentenceTransformer(path, device="cpu")
            m.max_seq_length = int(self.rc["max_seq_length"])
            self._encoder = lambda texts: self.IX.encode(m, texts, 8)
        return self._encoder

    def query_vector(self, source_pid: str | None, text: str) -> tuple[np.ndarray, str]:
        if source_pid and source_pid in self.pos:
            return self.emb[self.pos[source_pid]], "stored paragraph embedding (bge-base-en-v1.5 @ a5beb1e3)"
        vec = self.encoder()([self.IX.embedding_text(text)])[0]
        return np.asarray(vec, dtype=np.float32), "encoded locally (bge-base-en-v1.5 @ a5beb1e3, offline)"

    # -- commands ------------------------------------------------------------------------------------------------
    def prepare(self, target_class: str, source_pid: str | None = None, text: str | None = None, source_class: str | None = None) -> dict:
        from src.retrieval import systems as SY

        if target_class not in self.classes:
            return {"ok": False, "error": f"unknown target class {target_class!r}"}
        src_idx = self.pos.get(source_pid) if source_pid else None
        if source_pid and src_idx is None:
            return {"ok": False, "error": f"unknown paragraph id {source_pid!r}"}
        src_text = self.corpus.texts[src_idx] if src_idx is not None else (text or "").strip()
        if len(src_text.split()) < 3:
            return {"ok": False, "error": "query text too short"}
        if src_idx is not None:
            source_class = source_class or str(self.corpus.entity_class[src_idx])
        qvec, dense_basis = self.query_vector(source_pid, src_text)
        bm = self.bm25.scores(src_text)
        dense = self.emb @ qvec
        ranked = SY.run_query(bm, dense, entity_class=self.corpus.entity_class, source_index=src_idx, target_class=target_class,
                              rrf_k=int(self.rc["rrf_k"]), depth=DEPTH, source_class=source_class)["class_aware"]
        cands = [(self.corpus.ids[i], self.corpus.texts[i]) for i in ranked.indices.tolist()]
        msgs = self.prompts.messages(source_class=source_class or "unspecified", source_text=src_text, target_class=target_class, candidates=cands)
        budget = C.WordBudget()
        pointers = [self.pointer(pid, txt, budget) for pid, txt in cands]
        out = {"ok": True, "candidate_ids": [pid for pid, _ in cands], "messages": msgs, "pointers": pointers,
               "retrieval": {"system": "class_aware hybrid RRF (src/retrieval/systems.run_query)", "dense_query": dense_basis,
                             "class_filter_applied": bool(ranked.class_filter_applied), "rrf_k": int(self.rc["rrf_k"])},
               "source_class": source_class}
        if src_idx is not None:
            out["source_pointer"] = self.pointer(source_pid, src_text, budget)
        return out

    def pointer(self, pid: str, text: str, budget) -> dict:
        md = pid.split("::")[0]
        d = self.docs.get(md, {})
        return {"id": pid, "mdId": md, "url": d.get("source_url"), "harvestDate": d.get("harvest_date"),
                "excerpt": budget.take(pid, text, cap=C.EXCERPT_WORDS),
                "title": " ".join((d.get("title") or "").split()[:20])}

    def decide(self, raw: str, candidate_ids: list[str], source_pid: str | None = None, source_class: str | None = None) -> dict:
        parsed, problems = CMP.parse_response(raw, candidate_ids)
        verdict = RULE.class_verdict(parsed) if parsed else {"judgement": "unsure", "matched_paragraph_id": None, "per_candidate": [],
                                                             "rule": RULE.RULE_VERSION}
        rec = {"item_id": f"t1_{source_pid or 'live::free'}", "target_class": "", "raw": raw, "parse_problems": problems, **verdict}
        sig = C.comparator_signals(rec)
        fields = C.decisive_fields(rec)
        rows = [{"field": r["field"], "status": r["status"], "material": r["material"]} for r in (fields or {}).get("rows", [])]
        features = None
        if sig["parse_ok"] and sig["judgement"] in ("same", "different", "none"):
            fam = self.docs.get((source_pid or "").split("::")[0], {}).get("subject_family")
            features = [float(sig["judgement"] == "different"), float(sig["judgement"] == "none"), float(sig["n_both"]), float(sig["n_material_diff"]),
                        float(sig["hinge"]), float(sig["candidates_agree"]), float((sig["decisive_pid"] or "").split("::")[0] in self.amended),
                        float(bool(self.cells.get((source_class, fam), False)))]
        return {"ok": True, "judgement": verdict["judgement"], "matched_paragraph_id": verdict.get("matched_paragraph_id"),
                "per_candidate": verdict.get("per_candidate", []), "rule": verdict.get("rule"), "parse_problems": problems,
                "fields": rows, "features_m2": features}


def main() -> int:
    bridge = None
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if req.get("cmd") == "ping":
                out = {"ok": True, "pong": True}
            else:
                bridge = bridge or Bridge()
                if req["cmd"] == "prepare":
                    out = bridge.prepare(req["target_class"], req.get("source_pid"), req.get("text"), req.get("source_class"))
                elif req["cmd"] == "decide":
                    out = bridge.decide(req["raw"], req["candidate_ids"], req.get("source_pid"), req.get("source_class"))
                elif req["cmd"] == "classes":
                    out = {"ok": True, "classes": bridge.classes}
                else:
                    out = {"ok": False, "error": "unknown command"}
        except Exception as e:  # report, never crash the proxy
            out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        out["id"] = (req or {}).get("id") if isinstance(locals().get("req"), dict) else None
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
