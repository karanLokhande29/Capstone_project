"""Hosted audit generator (public site): the pieces that differ from the local install.

The local install runs a 7B model in Ollama and the bge / NLI models in torch on the user's machine. The hosted service
(ui/api_audit/function_app.py, an Azure Function) keeps the same features and the same checks, with three swaps:

1. ``GeminiLLM``: the writer is Gemini (REST), with the same ``chat()`` contract as ``genai.LocalLLM``. Inputs are RBI
   text and pack rows only; uploads (policy gap analysis) stay in the installed version.
2. ``OnnxModels``: bge-base (retrieval) and the NLI cross-encoder (sentence verifier), exported to ONNX and int8
   quantised (scripts/auditgen_hosted_models.py), with the same ``embed()`` / ``nli_scores()`` contract as
   ``gap_analysis.LocalModels``. A sentence is still kept only if the NLI argmax is entailment.
3. ``cap()``: every string the service returns that copies a run of more than 12 words of RBI text is cut to 12 words,
   the public site's quote limit (the same rule as ui/scripts/build_public_extras.py). Links to the RBI PDFs are kept.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.auditgen import genai as G

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
QUOTE_WORDS = 12
HOSTED_RULE = ("Write plain English for a compliance officer. Do not copy more than ten consecutive words from the "
               "evidence; restate it in your own words while keeping its meaning, numbers and conditions exact.")


class GeminiLLM:
    """Gemini over REST with the ``LocalLLM.chat()`` contract. The key comes from the server environment only."""

    def __init__(self, gcfg: Mapping[str, Any], *, key: str | None = None, opener=urllib.request.urlopen):
        self.cfg = gcfg["llm"]
        self.key = key if key is not None else os.environ.get("AUDIT_GEMINI_API_KEY", "")
        self.model = str(self.cfg.get("hosted_model") or "gemini-3.5-flash-lite")
        self.open = opener

    def status(self) -> dict[str, Any]:
        ok = bool(self.key)
        return {"available": ok, "model": self.model if ok else None, "pulled": [self.model] if ok else [],
                "preferred": [self.model], "reason": "" if ok else "no model key is configured on the server"}

    def chat(self, messages: Sequence[Mapping[str, str]], *, model: str | None = None, json_mode: bool = True) -> dict[str, Any]:
        if not self.key:
            raise G.GenAIError("no model key is configured on the server")
        system = "\n\n".join([m["content"] for m in messages if m["role"] == "system"] + [HOSTED_RULE])
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages if m["role"] != "system"]
        # Thinking tokens count against maxOutputTokens on Gemini 3.5: keep thinking minimal (as in the research runs)
        # and leave room for a full memo, or a long JSON reply is cut off and cannot be parsed.
        gen: dict[str, Any] = {"temperature": self.cfg["temperature"], "maxOutputTokens": max(4096, int(self.cfg["max_tokens"]) * 2),
                               "thinkingConfig": {"thinkingLevel": "minimal"}}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": gen}
        out = self._call(body, json_mode)
        if json_mode and out["json"] is None:
            # One retry with an explicit reminder; a reply that still is not JSON is returned as is (callers abstain).
            body["contents"] = contents + [{"role": "model", "parts": [{"text": out["text"][:2000]}]},
                                           {"role": "user", "parts": [{"text": "That reply was not one complete JSON object. "
                                                                                "Reply again with the JSON object only, shorter if needed."}]}]
            out = self._call(body, json_mode)
        return out

    def _call(self, body: dict, json_mode: bool) -> dict[str, Any]:
        req = urllib.request.Request(f"{GEMINI}/models/{self.model}:generateContent", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": self.key}, method="POST")
        t0 = time.monotonic()
        last: Exception | None = None
        for attempt in range(3):
            try:
                with self.open(req, timeout=float(self.cfg.get("hosted_timeout_sec", 60))) as r:
                    data = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 500, 502, 503, 504):
                    raise G.GenAIError(f"model call failed ({e.code})") from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
            time.sleep(1.5 * (attempt + 1))
        else:
            if isinstance(last, urllib.error.HTTPError) and last.code == 429:
                raise G.GenAIError("The free model quota is used up for now; please try again later.")
            raise G.GenAIError(f"model call failed ({type(last).__name__})")
        cand = (data.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in ((cand.get("content") or {}).get("parts") or []) if not p.get("thought"))
        return {"text": text, "json": G.parse_json(text) if json_mode else None, "model": self.model,
                "seconds": round(time.monotonic() - t0, 2), "eval_tokens": (data.get("usageMetadata") or {}).get("candidatesTokenCount")}


class OnnxModels:
    """bge-base and the NLI cross-encoder in ONNX Runtime (int8). ``directory`` holds bge/ and nli/, each with
    model.onnx, tokenizer.json and meta.json (written by scripts/auditgen_hosted_models.py)."""

    _inst: "OnnxModels | None" = None

    def __init__(self, directory: Path, threads: int = 2):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.meta = {k: json.loads((directory / k / "meta.json").read_text()) for k in ("bge", "nli")}
        self.sess = {k: ort.InferenceSession(str(directory / k / "model.onnx"), opts, providers=["CPUExecutionProvider"])
                     for k in ("bge", "nli")}
        self.tok = {}
        for k in ("bge", "nli"):
            t = Tokenizer.from_file(str(directory / k / "tokenizer.json"))
            t.enable_truncation(512, strategy="only_first" if k == "nli" else "longest_first")
            t.enable_padding(pad_id=int(self.meta[k]["pad_id"]), pad_token=self.meta[k]["pad_token"])
            self.tok[k] = t
        self.entail = int(self.meta["nli"]["entailment"])
        self.ids = {"embedding": self.meta["bge"]["id"], "nli": self.meta["nli"]["id"]}

    @classmethod
    def get(cls, directory: Path) -> "OnnxModels":
        if cls._inst is None:
            cls._inst = cls(directory)
        return cls._inst

    def _run(self, k: str, encs) -> np.ndarray:
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        return self.sess[k].run(None, {"input_ids": ids, "attention_mask": mask})[0]

    def embed(self, texts: Sequence[str], batch: int = 16) -> np.ndarray:
        out = [self._run("bge", self.tok["bge"].encode_batch([" ".join(t.split()) for t in texts[i:i + batch]]))
               for i in range(0, len(texts), batch)]
        return np.concatenate(out).astype(np.float32) if out else np.zeros((0, 768), dtype=np.float32)

    def nli_scores(self, pairs: Sequence[tuple[str, str]], batch: int = 16) -> tuple[np.ndarray, np.ndarray]:
        ps, args = [], []
        for i in range(0, len(pairs), batch):
            logits = self._run("nli", self.tok["nli"].encode_batch([(p, h) for p, h in pairs[i:i + batch]]))
            e = np.exp(logits - logits.max(-1, keepdims=True))
            ps.append((e / e.sum(-1, keepdims=True))[:, self.entail])
            args.append(logits.argmax(-1) == self.entail)
        if not ps:
            return np.zeros(0), np.zeros(0, dtype=bool)
        return np.concatenate(ps), np.concatenate(args)


def cap(value: Any, index, stats: dict | None = None) -> Any:
    """Cut every string that copies more than QUOTE_WORDS words of RBI text (``index``: release.rbi_text.CorpusIndex)."""
    from src.release.rbi_text import copied_runs

    if isinstance(value, dict):
        return {k: cap(v, index, stats) for k, v in value.items()}
    if isinstance(value, list):
        return [cap(v, index, stats) for v in value]
    if isinstance(value, str) and any(copied_runs(value, index, min_words=QUOTE_WORDS + 1)):
        # Shorten further while the checker's tokeniser (which splits "2.1.3.i" into four words) still finds a long run.
        words = value.split()
        n = min(QUOTE_WORDS, len(words))
        while n > 1 and any(copied_runs(" ".join(words[:n]), index, min_words=QUOTE_WORDS + 1)):
            n -= 1
        if stats is not None:
            stats["capped"] = stats.get("capped", 0) + 1
        return " ".join(words[:n]) + " …"
    return value
