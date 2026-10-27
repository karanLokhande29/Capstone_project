"""Policy gap analysis on local models only.

Privacy: uploaded documents are read and scored on this machine. Nothing here imports an LLM client, and the models
are loaded from the local Hugging Face snapshot named by their pinned commit with the hub set offline, so no document
text can leave the machine. Uploaded text is never logged; it is stored only under ``data/auditgen_uploads/<session>/``
(gitignored, excluded from release_check) and can be deleted from the UI. Reports carry the matched clause excerpts
only; the JSON audit trail carries file hashes, never text.

Method (rules v1, thresholds fixed in config/auditgen_v1.yaml before any evaluation):
1. extract text (pdfplumber / python-docx / plain text) and split it into clauses;
2. for each applicable obligation, retrieve the top-k clauses by bge cosine similarity;
3. score each (clause, obligation sentence) pair with the NLI cross-encoder:
   - covered: NLI argmax is entailment with p >= covered_entailment;
   - partial: else p(entailment) >= partial_entailment, or cosine >= partial_cosine;
   - missing: nothing above threshold.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.auditgen.corpus import ROOT, CorpusStore, excerpt

HF_HUB = Path.home() / ".cache/huggingface/hub"
ALLOWED_SUFFIXES = (".pdf", ".docx", ".txt", ".md")
_SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
_SPLIT = re.compile(r"\n\s*\n|\n(?=\s*(?:\d+(?:\.\d+)*[.)]|\([a-z0-9ivx]+\)|[a-z][.)]|[•\-–*])\s)")
_SENT = re.compile(r"(?<=[.;])\s+(?=[A-Z(\"'0-9])")


class GapError(ValueError):
    pass


def _snapshot(repo: str, rev: str) -> Path:
    p = HF_HUB / f"models--{repo.replace('/', '--')}" / "snapshots" / rev
    if not p.is_dir():
        raise GapError(f"local model {repo}@{rev[:8]} is not in the local cache; gap analysis runs on local models only")
    return p


class LocalModels:
    """bge-base (embeddings) and the NLI cross-encoder, both loaded offline from pinned local snapshots."""

    _inst: "LocalModels | None" = None

    def __init__(self, cfg: Mapping[str, Any]):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from sentence_transformers import SentenceTransformer
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        g = cfg["gap_analysis"]
        self.embedder = SentenceTransformer(str(_snapshot(g["embedding_model"], g["embedding_revision"])), device="cpu")
        nli_path = _snapshot(g["nli_model"], g["nli_revision"])
        self.tok = AutoTokenizer.from_pretrained(str(nli_path))
        self.nli = AutoModelForSequenceClassification.from_pretrained(str(nli_path)).eval()
        labels = {int(k): v.lower() for k, v in self.nli.config.id2label.items()}
        ent = [k for k, v in labels.items() if v.startswith("entail")]
        if len(ent) != 1:
            raise GapError(f"cannot find the entailment label in {labels}")
        self.entail, self.torch = ent[0], torch
        self.ids = {"embedding": f"{g['embedding_model']}@{g['embedding_revision']}", "nli": f"{g['nli_model']}@{g['nli_revision']}"}

    @classmethod
    def get(cls, cfg: Mapping[str, Any]) -> "LocalModels":
        if cls._inst is None:
            cls._inst = cls(cfg)
        return cls._inst

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        return self.embedder.encode([" ".join(t.split()) for t in texts], batch_size=32, normalize_embeddings=True,
                                    convert_to_numpy=True, show_progress_bar=False).astype(np.float32)

    def nli_scores(self, pairs: Sequence[tuple[str, str]], batch: int = 32) -> tuple[np.ndarray, np.ndarray]:
        """(p(entailment), argmax is entailment) per (premise, hypothesis) pair."""
        ps, args = [], []
        for i in range(0, len(pairs), batch):
            chunk = pairs[i:i + batch]
            f = self.tok([p for p, _ in chunk], [h for _, h in chunk], padding=True, truncation="only_first",
                         max_length=512, return_tensors="pt")
            with self.torch.no_grad():
                logits = self.nli(**f).logits
            pr = logits.softmax(-1).numpy()
            ps.append(pr[:, self.entail])
            args.append(logits.argmax(-1).numpy() == self.entail)
        if not ps:
            return np.zeros(0), np.zeros(0, dtype=bool)
        return np.concatenate(ps), np.concatenate(args)


# -- documents --------------------------------------------------------------------------------------

def extract_text(name: str, data: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise GapError(f"unsupported file type {suffix!r}; use PDF, DOCX, TXT or MD")
    if suffix == ".pdf":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n\n".join(page.extract_text() or "" for page in pdf.pages)
    if suffix == ".docx":
        import docx

        d = docx.Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in d.paragraphs if p.text.strip())
    return data.decode("utf-8", errors="replace")


def split_clauses(text: str, *, min_chars: int = 40, max_words: int = 120) -> list[str]:
    blocks = [" ".join(b.split()) for b in _SPLIT.split(text or "") if b and b.strip()]
    out: list[str] = []
    buf = ""
    for b in blocks:
        b = (buf + " " + b).strip() if buf else b
        buf = ""
        if len(b) < min_chars:
            buf = b
            continue
        words = b.split()
        if len(words) <= max_words:
            out.append(b)
            continue
        cur: list[str] = []
        for s in _SENT.split(b):
            if cur and len(" ".join(cur + [s]).split()) > max_words:
                out.append(" ".join(cur))
                cur = []
            cur.append(s)
        if cur:
            out.append(" ".join(cur))
    if buf:
        if out:
            out[-1] = out[-1] + " " + buf
        elif len(buf) >= 10:
            out.append(buf)
    return out


# -- sessions (local storage, deletable) ------------------------------------------------------------

def uploads_root(cfg: Mapping[str, Any]) -> Path:
    return ROOT / cfg["paths"]["uploads"]


def new_session(cfg: Mapping[str, Any]) -> str:
    sid = uuid.uuid4().hex
    (uploads_root(cfg) / sid).mkdir(parents=True, exist_ok=False)
    return sid


def session_dir(cfg: Mapping[str, Any], sid: str) -> Path:
    if not _SESSION_RE.match(sid or ""):
        raise GapError("bad session id")
    return uploads_root(cfg) / sid


def save_upload(cfg: Mapping[str, Any], sid: str, name: str, data: bytes) -> dict[str, Any]:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:120] or "upload"
    if Path(safe).suffix.lower() not in ALLOWED_SUFFIXES:
        raise GapError("unsupported file type; use PDF, DOCX, TXT or MD")
    d = session_dir(cfg, sid)
    d.mkdir(parents=True, exist_ok=True)
    (d / safe).write_bytes(data)
    return {"name": safe, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def delete_session(cfg: Mapping[str, Any], sid: str) -> bool:
    d = session_dir(cfg, sid)
    if d.exists():
        shutil.rmtree(d)
        return True
    return False


# -- analysis ----------------------------------------------------------------------------------------

def analyse(store: CorpusStore, cfg: Mapping[str, Any], register: Sequence[Mapping[str, Any]],
            documents: Sequence[tuple[str, bytes]], *, models: LocalModels | None = None,
            families: Sequence[str] | None = None, risk: Mapping[str, int] | None = None,
            md_risk: Mapping[str, int] | None = None) -> dict[str, Any]:
    g = cfg["gap_analysis"]
    clauses: list[dict[str, Any]] = []
    files = []
    for name, data in documents:
        text = extract_text(name, data)
        cl = split_clauses(text, min_chars=int(g["min_clause_chars"]), max_words=int(g["max_clause_words"]))
        files.append({"name": Path(name).name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "clauses": len(cl)})
        clauses += [{"doc": Path(name).name, "index": i, "text": c} for i, c in enumerate(cl)]
    if not clauses:
        raise GapError("no text could be extracted from the uploaded documents")
    rows_in = [r for r in register if not r["hidden"] and (not families or r["subject_family"] in set(families))]
    m = models or LocalModels.get(cfg)
    by_id = _cands(store)
    hyps = [" ".join((store.obligation_sentence(by_id[r["obligation_id"]]) if r["obligation_id"] in by_id
                      else r["excerpt"]).split()[:80]) for r in rows_in]
    E_o, E_c = m.embed(hyps), m.embed([c["text"] for c in clauses])
    sims = E_o @ E_c.T
    k = min(int(g["top_k"]), len(clauses))
    top = np.argsort(-sims, axis=1)[:, :k]
    pairs = [(clauses[j]["text"], hyps[i]) for i in range(len(rows_in)) for j in top[i]]
    p_ent, is_ent = m.nli_scores(pairs)
    out_rows = []
    risk = risk or {}
    md_risk = md_risk or {}
    for i, r in enumerate(rows_in):
        cand = []
        for jj, j in enumerate(top[i]):
            q = i * k + jj
            cand.append({"clause_id": f"{clauses[j]['doc']}#c{clauses[j]['index']:04d}", "excerpt": excerpt(clauses[j]["text"], 40),
                         "cosine": round(float(sims[i, j]), 4), "entailment": round(float(p_ent[q]), 4), "nli_entails": bool(is_ent[q])})
        best_ent = max(cand, key=lambda c: c["entailment"])
        best_cos = max(cand, key=lambda c: c["cosine"])
        if best_ent["nli_entails"] and best_ent["entailment"] >= float(g["covered_entailment"]):
            cov, conf, matched = "covered", best_ent["entailment"], [best_ent]
        elif best_ent["entailment"] >= float(g["partial_entailment"]) or best_cos["cosine"] >= float(g["partial_cosine"]):
            cov = "partial"
            conf = max(best_ent["entailment"], best_cos["cosine"])
            matched = [best_ent] if best_ent is best_cos else [best_ent, best_cos]
        else:
            cov, conf, matched = "missing", 1.0 - best_ent["entailment"], []
        out_rows.append({
            "row_id": f"GAP-{r['obligation_id']}", "obligation_id": r["obligation_id"], "md_id": r["md_id"],
            "paragraph_id": r["paragraph_id"], "direction_title": r["direction_title"], "source_url": r["source_url"],
            "subject_family": r["subject_family"], "excerpt": r["excerpt"], "status": r["status"],
            "coverage": cov, "confidence": round(float(conf), 3), "matched_clauses": matched, "top_clauses": cand,
            "needs_review": cov != "covered" or conf < float(g["review_threshold"]),
            "enforcement_risk": int(md_risk.get(r["md_id"], 0)) or int(risk.get(r["subject_family"], 0)),
            "explanation": None, "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""})
    order = {"missing": 0, "partial": 1, "covered": 2}
    out_rows.sort(key=lambda x: (order[x["coverage"]], -x["enforcement_risk"], x["md_id"], x["paragraph_id"]))
    per_dir: dict[str, dict[str, Any]] = {}
    for x in out_rows:
        d = per_dir.setdefault(x["md_id"], {"md_id": x["md_id"], "direction_title": x["direction_title"], "source_url": x["source_url"],
                                           "covered": 0, "partial": 0, "missing": 0})
        d[x["coverage"]] += 1
    return {"files": files, "clauses": len(clauses), "obligations": len(out_rows), "models": m.ids,
            "thresholds": {k2: g[k2] for k2 in ("top_k", "covered_entailment", "partial_entailment", "partial_cosine", "review_threshold")},
            "rules_version": cfg["version"], "families": list(families or []),
            "counts": {c: sum(1 for x in out_rows if x["coverage"] == c) for c in ("covered", "partial", "missing")},
            "per_direction": sorted(per_dir.values(), key=lambda d: (-d["missing"], d["md_id"])), "rows": out_rows,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            # In-memory only: full clause and obligation text for the optional local explanation step. Callers pop it
            # before anything is saved, so the stored pack keeps excerpts only.
            "_texts": {**{f"{c['doc']}#c{c['index']:04d}": c["text"] for c in clauses},
                       **{r["obligation_id"]: h for r, h in zip(rows_in, hyps)}}}


_CAND_CACHE: dict[int, dict[str, dict]] = {}


def _cands(store: CorpusStore) -> dict[str, dict]:
    key = id(store)
    if key not in _CAND_CACHE:
        _CAND_CACHE.clear()
        _CAND_CACHE[key] = {c["candidate_id"]: c for c in store.candidates()}
    return _CAND_CACHE[key]
