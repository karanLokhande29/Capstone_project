"""Pairwise structured comparator (the targeted experiment): field extraction by the LLM, verdict by a fixed rule.

**One call per (item, compared class).** The prompt carries:
- the source obligation;
- the target class's two shown candidate paragraphs, the same text the raters saw.

**How the verdict is reached:** the model extracts actor / action / object / scope / condition / threshold / amount /
percentage / frequency / deadline / exception / documentation / reporting for each side and marks each field equal,
differs, only_source, only_target or absent. `src/rag/comparator_rule.py` then decides same / different / none.

**Rules for use:**
- Calls go through the existing LLM client: cache, quota ledger, P4 model and settings.
- Develop only on fixtures or the separate 30-item IRR set. Never tune on T1 gold, the rejected items or the packet items.
- The prompt and rule are frozen by sha256 before any T1 evaluation.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from obli_frozen import comparator_rule as RULE  # bundle copy; identical to src/rag/comparator.py otherwise

PROMPT_FILES = ("comparator_system.txt", "comparator_user.txt")
_CAND_RE = re.compile(r"\[(md_\d+::p\d{5})\]\s*(.*?)(?=\n\n\[md_\d+::p\d{5}\]|\Z)", re.S)


class ComparatorError(ValueError):
    pass


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def frozen_hashes(prompts_dir: Path) -> dict[str, str]:
    out = {f: sha256_file(Path(prompts_dir) / f) for f in PROMPT_FILES}
    out["comparator_rule.py"] = sha256_file(Path(RULE.__file__))
    return out


def parse_candidates(cell: str) -> list[tuple[str, str]]:
    """'[md_..::p..] text\\n\\n[md_..::p..] text' (the sheet's target_candidates) -> [(id, text)]."""
    return [(m.group(1), m.group(2).strip()) for m in _CAND_RE.finditer(cell or "")]


class Prompts:
    def __init__(self, directory: Path, expected: Mapping[str, str] | None = None):
        self.dir = Path(directory)
        self.text = {f: (self.dir / f).read_text(encoding="utf-8") for f in PROMPT_FILES}
        if expected:
            now = frozen_hashes(self.dir)
            bad = [k for k, v in expected.items() if now.get(k) != v]
            if bad:
                raise ComparatorError(f"comparator prompt/rule changed since it was frozen: {bad}")

    def messages(self, *, source_class: str, source_text: str, target_class: str,
                 candidates: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
        cand = "\n\n".join(f"[{pid}] {txt}" for pid, txt in candidates)
        user = (self.text["comparator_user.txt"].replace("{source_class}", source_class)
                .replace("{source_text}", source_text).replace("{target_class}", target_class)
                .replace("{candidates}", cand))
        return [{"role": "system", "content": self.text["comparator_system.txt"].strip()},
                {"role": "user", "content": user.strip()}]


def parse_response(text: str, candidate_ids: Sequence[str]) -> tuple[list[dict[str, Any]] | None, list[str]]:
    """Validated candidate answers, or (None, problems)."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as exc:
        return None, [f"not JSON: {exc}"]
    cands = obj.get("candidates") if isinstance(obj, dict) else None
    if not isinstance(cands, list):
        return None, ["no candidates list"]
    by_id = {c.get("paragraph_id"): c for c in cands if isinstance(c, dict)}
    problems, out = [], []
    for pid in candidate_ids:
        c = by_id.get(pid)
        if c is None:
            problems.append(f"candidate {pid} missing")
            continue
        if not isinstance(c.get("addresses_same_duty"), bool):
            problems.append(f"{pid}: addresses_same_duty not a boolean")
            continue
        fc = c.get("field_comparison") or {}
        bad = [f for f in RULE.FIELDS if fc.get(f) not in RULE.COMPARISONS]
        if bad:
            problems.append(f"{pid}: field_comparison invalid for {bad}")
            continue
        out.append({"paragraph_id": pid, "addresses_same_duty": c["addresses_same_duty"],
                    "field_comparison": {f: fc[f] for f in RULE.FIELDS}, "fields": c.get("fields") or {}})
    return (out if not problems else None), problems


def compare_unit(llm: Any, prompts: Prompts, unit: Mapping[str, Any], *, max_output_tokens: int) -> dict[str, Any]:
    """unit: item_id, source_class, source_text, target_class, candidates [(id, text)]."""
    ids = [pid for pid, _ in unit["candidates"]]
    msgs = prompts.messages(source_class=unit["source_class"], source_text=unit["source_text"],
                            target_class=unit["target_class"], candidates=unit["candidates"])
    c = llm.complete(msgs, max_output_tokens=max_output_tokens)
    parsed, problems = parse_response(c.text, ids)
    verdict = RULE.class_verdict(parsed) if parsed else {"judgement": "unsure", "matched_paragraph_id": None,
                                                          "per_candidate": [], "rule": RULE.RULE_VERSION}
    return {"item_id": unit["item_id"], "target_class": unit["target_class"], **verdict, "parse_problems": problems,
            "raw": c.text, "cached": getattr(c, "cached", None), "model": getattr(c, "model", None),
            "model_version": getattr(c, "model_version", None)}


def evaluate(results: Sequence[Mapping[str, Any]], gold: Mapping[tuple[str, str], str]) -> dict[str, Any]:
    from src.eval.metrics import f1_scores

    keys = [(r["item_id"], r["target_class"]) for r in results if (r["item_id"], r["target_class"]) in gold]
    by = {(r["item_id"], r["target_class"]): r for r in results}
    g = [gold[k] for k in keys]
    p = [by[k]["judgement"] for k in keys]
    f = f1_scores(g, p, ("same", "different", "none"))
    cats = ("same", "different", "none", "unsure")
    return {"n_units": len(keys), "judgement_macro_f1": f["macro_f1"],
            "per_label": {k: v for k, v in f["per_label"].items()},
            "different_recall": (sum(1 for a, b in zip(g, p) if a == b == "different") / g.count("different")) if "different" in g else None,
            "confusion": {a: {b: sum(1 for x, y in zip(g, p) if x == a and y == b) for b in cats} for a in cats[:3]},
            "unsure": p.count("unsure"), "parse_failures": sum(1 for k in keys if by[k]["parse_problems"])}
