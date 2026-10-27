"""Generative-AI layer for the audit generator: a local LLM client, the sentence verifier and the AI store.

Rules (config/auditgen_genai_v1.yaml):
- **Local only.** Every call goes to an Ollama server on a loopback address (127.0.0.1 / ::1 / localhost). Any other
  host is refused before a request is made. No remote API (Gemini, Groq, …) is used by any feature.
- **Cite or drop.** Every generated sentence carries the evidence it rests on. The local NLI cross-encoder checks it
  against that evidence (argmax = entailment, the P4 verifier rule); an unsupported sentence is not shown as an answer.
- **Numbers check.** A sentence that states a number absent from its evidence is unsupported.
- **Never settled.** AI output is labelled "AI draft, needs review" and never changes a review status by itself.
- **No text in logs.** The activity log records the feature, model, timings, row ids and sha256 hashes, never the
  question, the prompt or the answer.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import yaml

from src.auditgen.corpus import ROOT

CONFIG_PATH = ROOT / "config/auditgen_genai_v1.yaml"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
LABEL = "AI draft (local model), verified sentence by sentence against the cited RBI text; needs human review."
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'‘“0-9])")
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)(?![\w])")
_WORD = re.compile(r"\S+")


class GenAIError(RuntimeError):
    pass


def load_genai_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    g = yaml.safe_load(path.read_text(encoding="utf-8"))
    g["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return g


def sha(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def host_ok(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOOPBACK


def words(text: str, n: int) -> str:
    w = _WORD.findall(text or "")
    return " ".join(w[:n]) + (" …" if len(w) > n else "")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(" ".join((text or "").split())) if s.strip()]


def numbers(text: str) -> set[str]:
    """Numbers stated in ``text``, normalised (thousands separators and leading zeros removed: "01" == "1")."""
    out = set()
    for m in _NUM.finditer(text or ""):
        n = m.group(1).replace(",", "")
        out.add(n.lstrip("0") or "0" if "." not in n else n)
    return out


def parse_json(text: str) -> dict | None:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        v = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return v if isinstance(v, dict) else None


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def quote_in(quote: str, text: str) -> bool:
    """True when the (normalised) quote occurs in the text: the model's claimed evidence really is there."""
    q = norm(quote)
    return bool(q) and len(q.split()) >= 3 and q in norm(text)


# -- local LLM ----------------------------------------------------------------------------------------------------------

class LocalLLM:
    """An Ollama server on loopback. ``http`` is injectable (tests); the default is httpx."""

    def __init__(self, gcfg: Mapping[str, Any], *, http=None):
        self.cfg = gcfg["llm"]
        if not host_ok(self.cfg["host"]):
            raise GenAIError(f"the local LLM host must be loopback, not {self.cfg['host']!r}")
        if http is None:
            import httpx

            http = httpx
        self.http = http
        self.base = self.cfg["host"].rstrip("/")

    def models(self) -> list[str]:
        r = self.http.get(self.base + "/api/tags", timeout=3.0)
        return [m.get("name") for m in (r.json() or {}).get("models", []) if m.get("name")]

    def status(self) -> dict[str, Any]:
        try:
            pulled = self.models()
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            return {"available": False, "model": None, "pulled": [], "preferred": list(self.cfg["models"]),
                    "reason": f"no local runtime at {self.cfg['host']} ({type(exc).__name__}); start it with "
                              f"`OLLAMA_HOST=127.0.0.1:11434 ollama serve`"}
        chosen = next((m for m in self.cfg["models"] if m in pulled), None)
        return {"available": chosen is not None, "model": chosen, "pulled": pulled, "preferred": list(self.cfg["models"]),
                "reason": "" if chosen else f"none of {self.cfg['models']} is pulled; run `ollama pull {self.cfg['models'][0]}`"}

    def pick(self, model: str | None = None) -> str:
        st = self.status()
        if model:
            if model not in st["pulled"]:
                raise GenAIError(f"model {model} is not pulled in the local runtime")
            return model
        if not st["available"]:
            raise GenAIError(st["reason"])
        return st["model"]

    def chat(self, messages: Sequence[Mapping[str, str]], *, model: str | None = None, json_mode: bool = True) -> dict[str, Any]:
        m = self.pick(model)
        t0 = time.monotonic()
        body = {"model": m, "messages": list(messages), "stream": False,
                "options": {"temperature": self.cfg["temperature"], "seed": self.cfg["seed"], "num_ctx": self.cfg["num_ctx"],
                            "num_predict": self.cfg["max_tokens"]}}
        if json_mode:
            body["format"] = "json"
        r = self.http.post(self.base + "/api/chat", json=body, timeout=float(self.cfg["timeout_sec"]))
        data = r.json() or {}
        text = str(((data.get("message") or {}).get("content")) or "")
        return {"text": text, "json": parse_json(text) if json_mode else None, "model": m,
                "seconds": round(time.monotonic() - t0, 2), "eval_tokens": data.get("eval_count")}


# -- verifier -----------------------------------------------------------------------------------------------------------

def verify(models, items: Sequence[Mapping[str, Any]], *, premise_max_words: int = 380) -> list[dict[str, Any]]:
    """Check each ``{"text", "premise"}`` item with the NLI model; adds ``verified``, ``entailment`` and ``reason``.

    A sentence is verified iff the NLI argmax is entailment with the premise and every number it states appears in the
    premise. An item may carry ``premises`` (one per cited paragraph) instead: it is verified against each and against
    their concatenation, and the best-scoring premise counts, so a long first citation never truncates the second.
    An item without a premise (no valid citation) is unverified.
    """
    out = [dict(it) for it in items]
    for it in out:
        ps = [p for p in (it.pop("premises", None) or []) if p]
        if ps:
            it["_cands"] = ps + ([" ".join(ps)] if len(ps) > 1 else [])
        elif it.get("premise"):
            it["_cands"] = [it["premise"]]
    pairs, owner = [], []
    for i, it in enumerate(out):
        if it.get("text"):
            for c in it.get("_cands") or []:
                pairs.append((words(c, premise_max_words), it["text"]))
                owner.append((i, c))
    best: dict[int, tuple[float, bool, str]] = {}
    if pairs:
        p, ok = models.nli_scores(pairs)
        for k, (i, c) in enumerate(owner):
            cur = (float(p[k]), bool(ok[k]), c)
            if i not in best or (cur[1], cur[0]) > (best[i][1], best[i][0]):
                best[i] = cur
    for i, it in enumerate(out):
        cands = it.pop("_cands", None) or []
        if i in best:
            pe, ok_, prem = best[i]
            it.update({"entailment": round(pe, 4), "verified": ok_, "reason": "" if ok_ else "not entailed by the cited text"})
        else:
            it.update({"verified": False, "entailment": None, "reason": "no valid citation"})
            prem = ""
        source_nums = numbers(" ".join(cands)) if cands else numbers(prem)
        stray = numbers(it.get("text", "")) - source_nums
        if it["verified"] and stray:
            it["verified"], it["reason"] = False, f"states a number not in the cited text ({', '.join(sorted(stray))})"
        it.pop("premise", None)
    return out


# -- AI store and activity log ------------------------------------------------------------------------------------------

def ai_path(cfg: Mapping[str, Any], pack_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_\-]+", pack_id or ""):
        raise GenAIError("bad pack id")
    return ROOT / cfg["paths"]["runs"] / pack_id / "ai.json"


def load_ai(cfg: Mapping[str, Any], pack_id: str) -> dict[str, Any]:
    p = ai_path(cfg, pack_id)
    if p.exists():
        return json.loads(p.read_text())
    sample = ROOT / cfg["paths"]["samples"] / pack_id / "ai.json"
    if sample.exists():
        return json.loads(sample.read_text())
    return {"pack_id": pack_id, "kind": "ai_outputs", "label": LABEL}


def save_ai(cfg: Mapping[str, Any], pack_id: str, ai: Mapping[str, Any]) -> Path:
    p = ai_path(cfg, pack_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ai, ensure_ascii=False))
    return p


def record(cfg: Mapping[str, Any], gcfg: Mapping[str, Any], pack_id: str, feature: str, key: str | None,
           result: Mapping[str, Any]) -> dict[str, Any]:
    """Store ``result`` in the pack's AI store (``ai[feature]`` or ``ai[feature][key]``) and log it (hashes only)."""
    ai = load_ai(cfg, pack_id)
    if key is None:
        if feature == "ask":
            ai.setdefault("ask", []).insert(0, dict(result))
            del ai["ask"][50:]
        else:
            ai[feature] = dict(result)
    else:
        ai.setdefault(feature, {})[key] = dict(result)
    ai["genai_version"] = gcfg["version"]
    ai["genai_sha256"] = gcfg["_sha256"]
    save_ai(cfg, pack_id, ai)
    log(gcfg, pack_id, feature, key, result)
    return dict(result)


def log(gcfg: Mapping[str, Any], pack_id: str, feature: str, key: str | None, result: Mapping[str, Any]) -> None:
    items = result.get("sentences") or []
    entry = {"utc": now(), "pack_id": pack_id, "feature": feature, "key": key, "model": result.get("model"),
             "seconds": result.get("seconds"), "verified": sum(1 for s in items if s.get("verified")),
             "unverified": sum(1 for s in items if not s.get("verified")), "abstained": bool(result.get("abstained")),
             "input_sha256": result.get("input_sha256"), "output_sha256": sha(json.dumps(result, sort_keys=True, default=str))}
    p = ROOT / gcfg["storage"]["activity_log"]
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as h:
        h.write(json.dumps(entry) + "\n")


def activity(gcfg: Mapping[str, Any], limit: int = 200) -> list[dict[str, Any]]:
    p = ROOT / gcfg["storage"]["activity_log"]
    if not p.exists():
        return []
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    return rows[-limit:][::-1]


def envelope(gcfg: Mapping[str, Any], cfg: Mapping[str, Any], model: str | None, seconds: float, input_text: str,
             **fields: Any) -> dict[str, Any]:
    return {"created_utc": now(), "model": model, "seconds": round(seconds, 2), "genai_version": gcfg["version"],
            "verifier": cfg["gap_analysis"]["nli_model"] + "@" + cfg["gap_analysis"]["nli_revision"][:12],
            "label": LABEL, "disclaimer": cfg["disclaimer"], "input_sha256": sha(input_text), **fields}

