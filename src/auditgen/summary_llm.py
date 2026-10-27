"""Optional plain-language explanations from a LOCAL LLM only (an Ollama server on this machine's loopback address).

- Never a remote API: the host must resolve to 127.0.0.1 / ::1 / localhost, or the feature refuses to run.
- If no local runtime answers, the feature is reported unavailable and hidden; gap analysis works without it.
- Every explanation sentence passes the NLI verifier (premise = the matched policy clause + the obligation sentence);
  an unsupported sentence is dropped.
- Explanations are generated on request, never logged, and stored only in the user's local pack.
"""

from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_SENT = re.compile(r"(?<=[.!?])\s+")


class LocalLLMError(RuntimeError):
    pass


def _host_ok(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOOPBACK


def available(cfg: Mapping[str, Any], *, http=None) -> dict[str, Any]:
    c = cfg["local_llm"]
    if not _host_ok(c["host"]):
        return {"available": False, "reason": "configured host is not loopback; refused"}
    import httpx

    client = http or httpx
    try:
        r = client.get(c["host"].rstrip("/") + "/api/tags", timeout=2.0)
        models = [m.get("name") for m in r.json().get("models", [])]
    except Exception as exc:  # noqa: BLE001 - any failure means "not available"
        return {"available": False, "reason": f"no local runtime at {c['host']} ({type(exc).__name__})"}
    ok = any(m == c["model"] or (m or "").split(":")[0] == c["model"].split(":")[0] for m in models)
    return {"available": ok, "models": models, "model": c["model"],
            "reason": "" if ok else f"model {c['model']} is not pulled in the local runtime"}


def explain(cfg: Mapping[str, Any], obligation: str, clause: str, *, http=None) -> str:
    c = cfg["local_llm"]
    if not _host_ok(c["host"]):
        raise LocalLLMError("local LLM host must be loopback")
    import httpx

    client = http or httpx
    prompt = ("In one or two short sentences, say whether and how the POLICY CLAUSE addresses the OBLIGATION. "
              "Use only what the two texts say.\n\nOBLIGATION: " + obligation + "\n\nPOLICY CLAUSE: " + clause)
    r = client.post(c["host"].rstrip("/") + "/api/generate", timeout=float(c["timeout_sec"]),
                    json={"model": c["model"], "prompt": prompt, "stream": False, "options": {"temperature": 0}})
    return str((r.json() or {}).get("response") or "").strip()


def verified(models, obligation: str, clause: str, text: str) -> dict[str, Any]:
    """Keep only sentences the NLI model judges entailed by clause + obligation."""
    sents = [s.strip() for s in _SENT.split(text or "") if s.strip()]
    if not sents:
        return {"kept": [], "dropped": 0}
    premise = clause + " " + obligation
    p, ok = models.nli_scores([(premise, s) for s in sents])
    kept = [s for s, k in zip(sents, ok) if bool(k)]
    return {"kept": kept, "dropped": len(sents) - len(kept)}


def explain_rows(cfg: Mapping[str, Any], models, rows: Sequence[dict[str, Any]], sentences: Mapping[str, str], *,
                 limit: int = 25, http=None) -> int:
    """Add verified explanations to up to ``limit`` covered / partial rows. Returns the number explained."""
    n = 0
    for r in rows:
        if n >= limit or r["coverage"] == "missing" or not r["matched_clauses"]:
            continue
        clause_full = sentences.get(r["matched_clauses"][0]["clause_id"]) or r["matched_clauses"][0]["excerpt"]
        obl = sentences.get(r["obligation_id"]) or r["excerpt"]
        v = verified(models, obl, clause_full, explain(cfg, obl, clause_full, http=http))
        r["explanation"] = " ".join(v["kept"]) or None
        r["explanation_dropped_sentences"] = v["dropped"]
        n += 1
    return n
