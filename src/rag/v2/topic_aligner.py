"""Agent 1 of V2: does a candidate paragraph describe the same underlying regulatory duty as the source?

**One call per unit (item, compared class), as for the V1 comparator.** The prompt carries:
- the source obligation;
- the target class's shown candidate paragraphs (up to two, the same ones V1 and the raters saw).

**What the model returns:** per candidate, five alignment dimensions (actor, action, object, regulated activity,
purpose), ``same_underlying_duty`` (``yes`` / ``no`` / ``uncertain``), one exact quotation from each side and a reason.
The prompt says that differing deadlines, thresholds, amounts or scope do not by themselves make two duties unrelated:
V1 decided the duty and the fields in one call, and 32 of its 40 missed gold ``different`` units came back ``none``.

**What the code checks before anything downstream sees it:**
- the answer is JSON with an ``alignments`` list; otherwise every candidate is ``uncertain``;
- each candidate appears exactly once, with a known id, a label from the vocabulary and all five dimensions;
- for ``yes`` / ``no``, both quotations occur in the texts they claim to quote (``evidence.quote_in``).
A candidate that fails any check is downgraded to ``uncertain``, with the reason in ``problems``. The model's own label
is kept as ``model_label``.

**Rules for use:**
- Calls go through the existing LLM client: cache, quota ledger, P4 model and settings.
- Develop only on fixtures or the separate 30-item IRR set. Never tune on T1 gold, the rejected items or the packet items.
- The prompts, this module and ``evidence.py`` are frozen by sha256 before any T1 call.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.rag.v2 import evidence as EV
from src.rag.v2 import schemas as S

PROMPT_FILES = ("topic_alignment_system.txt", "topic_alignment_user.txt")
CODE_FILES = (Path(__file__), Path(EV.__file__))
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PLACEHOLDERS = ("source_id", "source_class", "source_text", "target_class", "candidates")
_PID_RE = re.compile(r"md_\d+::p\d+")
_SLOT_RE = re.compile(r"\{(" + "|".join(PLACEHOLDERS) + r")\}")


class AlignerError(ValueError):
    pass


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def frozen_hashes(prompts_dir: Path = PROMPTS_DIR) -> dict[str, str]:
    out = {f: sha256_file(Path(prompts_dir) / f) for f in PROMPT_FILES}
    out.update({p.name: sha256_file(p) for p in CODE_FILES})
    return out


def source_id_of(unit: Mapping[str, Any]) -> str | None:
    """The unit's source paragraph id: ``source_id`` if given, else read from ``item_id`` (``t1_<paragraph id>``)."""
    if unit.get("source_id"):
        return str(unit["source_id"])
    m = _PID_RE.search(str(unit.get("item_id") or ""))
    return m.group(0) if m else None


class Prompts:
    def __init__(self, directory: Path = PROMPTS_DIR, expected: Mapping[str, str] | None = None):
        self.dir = Path(directory)
        self.text = {f: (self.dir / f).read_text(encoding="utf-8") for f in PROMPT_FILES}
        if expected:
            now = frozen_hashes(self.dir)
            bad = [k for k, v in expected.items() if now.get(k) != v]
            if bad:
                raise AlignerError(f"topic-alignment prompt/code changed since it was frozen: {bad}")

    def messages(self, *, source_id: str | None, source_class: str, source_text: str, target_class: str,
                 candidates: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
        values = {"source_id": source_id or "(not given)", "source_class": source_class, "source_text": source_text,
                  "target_class": target_class,
                  "candidates": "\n\n".join(f"[{pid}] {txt}" for pid, txt in candidates)}
        # One pass, so a placeholder-like string inside RBI text is never substituted again.
        user = _SLOT_RE.sub(lambda m: values[m.group(1)], self.text["topic_alignment_user.txt"])
        return [{"role": "system", "content": self.text["topic_alignment_system.txt"].strip()},
                {"role": "user", "content": user.strip()}]


def _loads(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    return json.loads(t)


def _check_candidate(c: Mapping[str, Any], pid: str, cand_text: str, source_text: str) -> S.CandidateAlignment:
    label = c.get("same_underlying_duty")
    if label not in S.DUTY_LABELS:
        return S.uncertain(pid, f"same_underlying_duty {label!r} not in {S.DUTY_LABELS}")
    dims = c.get("dimensions") if isinstance(c.get("dimensions"), dict) else {}
    bad_dims = [d for d in S.DIMENSIONS if dims.get(d) not in S.DIMENSION_LABELS]
    src_q, cand_q = c.get("source_evidence"), c.get("candidate_evidence")
    src_ok, cand_ok = EV.quote_in(src_q, source_text), EV.quote_in(cand_q, cand_text)
    out = S.CandidateAlignment(candidate_id=pid, same_underlying_duty=label, model_label=label,
                               dimensions={d: dims.get(d) for d in S.DIMENSIONS},
                               source_evidence=src_q, candidate_evidence=cand_q, evidence_ok=src_ok and cand_ok,
                               reason=str(c.get("reason") or "").strip())
    if bad_dims:
        out.problems.append(f"dimensions invalid for {bad_dims}")
    if label != "uncertain" or src_q or cand_q:
        if not src_ok:
            out.problems.append("source_evidence not found in the source (or under "
                                f"{EV.MIN_QUOTE_WORDS} words)")
        if not cand_ok:
            out.problems.append("candidate_evidence not found in this candidate (or under "
                                f"{EV.MIN_QUOTE_WORDS} words)")
    if out.problems and label != "uncertain":
        out.same_underlying_duty = "uncertain"
    return out


def parse_alignment(text: str, *, source_id: str | None, source_text: str,
                    candidates: Sequence[tuple[str, str]]) -> tuple[list[S.CandidateAlignment], list[str], list[str]]:
    """(one alignment per candidate, in candidate order; unit-level problems; warnings).

    Unit-level problems mean the answer could not be used at all: every candidate is then ``uncertain``. Warnings are
    recorded but do not change any label.
    """
    ids = [pid for pid, _ in candidates]
    try:
        obj = _loads(text)
    except json.JSONDecodeError as exc:
        return [S.uncertain(pid, "unit answer unusable") for pid in ids], [f"not JSON: {exc}"], []
    rows = obj.get("alignments") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        return [S.uncertain(pid, "unit answer unusable") for pid in ids], ["no alignments list"], []
    warnings = []
    if source_id and obj.get("source_id") != source_id:
        warnings.append(f"source_id {obj.get('source_id')!r} does not match {source_id!r}")
    by_id: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        if isinstance(r, dict):
            by_id.setdefault(r.get("candidate_id"), []).append(r)
    unknown = sorted(str(k) for k in by_id if k not in ids)
    if unknown:
        warnings.append(f"unknown candidate ids ignored: {unknown}")
    texts = dict(candidates)
    out = []
    for pid in ids:
        got = by_id.get(pid, [])
        if not got:
            out.append(S.uncertain(pid, "candidate missing from the answer"))
        elif len(got) > 1:
            out.append(S.uncertain(pid, f"candidate answered {len(got)} times"))
        else:
            out.append(_check_candidate(got[0], pid, texts[pid], source_text))
    return out, [], warnings


def align_unit(llm: Any, prompts: Prompts, unit: Mapping[str, Any], *, max_output_tokens: int) -> dict[str, Any]:
    """unit: item_id, source_class, source_text, target_class, candidates [(id, text)]; source_id optional."""
    if not unit.get("candidates"):
        raise AlignerError(f"{unit.get('item_id')}: no candidates")
    sid = source_id_of(unit)
    msgs = prompts.messages(source_id=sid, source_class=unit["source_class"], source_text=unit["source_text"],
                            target_class=unit["target_class"], candidates=unit["candidates"])
    c = llm.complete(msgs, max_output_tokens=max_output_tokens)
    aligned, problems, warnings = parse_alignment(c.text, source_id=sid, source_text=unit["source_text"],
                                                  candidates=unit["candidates"])
    return {"item_id": unit["item_id"], "source_id": sid, "target_class": unit["target_class"],
            "alignments": [a.to_dict() for a in aligned], "parse_problems": problems, "warnings": warnings,
            "raw": c.text, "cached": getattr(c, "cached", None), "model": getattr(c, "model", None),
            "model_version": getattr(c, "model_version", None)}


def summarise(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Label counts over records, before and after validation (no gold: for plan/dev reporting only)."""
    from collections import Counter

    final, model, downgraded = Counter(), Counter(), 0
    for r in records:
        for a in r["alignments"]:
            final[a["same_underlying_duty"]] += 1
            model[a["model_label"]] += 1
            downgraded += a["model_label"] not in (None, "uncertain") and a["same_underlying_duty"] == "uncertain"
    return {"units": len(records), "candidates": sum(final.values()), "final": dict(final), "model": dict(model),
            "downgraded_by_validation": downgraded,
            "unit_parse_failures": sum(1 for r in records if r["parse_problems"])}
