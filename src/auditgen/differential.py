"""Cross-class differential from the P2-002 matches (bge semantic match within the subject family, validated threshold).

P2-002 can say "a counterpart exists" or "no counterpart above threshold"; it cannot say that two matched paragraphs
differ in substance. Rules v1 therefore label a near-verbatim match (lexical >= ``shared_lexical_min``) as shared and
every other match as "possibly different". Every possibly-different or no-counterpart row needs human review: the
RBI-ObliBench evaluation found that LLM systems miss most differential cases, so nothing here is settled.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from src.auditgen.corpus import CorpusStore, excerpt
from src.auditgen.profile import Profile

CAUTION = ("The RBI-ObliBench benchmark found that LLM systems miss most differential cases (56 of 78 gold 'different' "
           "units missed by every LLM system); every 'possibly different' or 'no counterpart' row needs human review.")


def _iter_matches(path, sources: set[str], targets: set[str]):
    with open(path, encoding="utf-8") as h:
        for line in h:
            if '"source_entity_class"' not in line:
                continue
            d = json.loads(line)
            if d["source_entity_class"] in sources and d["target_entity_class"] in targets:
                yield d


def build_differential(store: CorpusStore, cfg: Mapping[str, Any], profile: Profile,
                       register: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not profile.group_classes:
        return []
    classes = {profile.entity_class, *profile.group_classes}
    in_scope = {r["obligation_id"] for r in register if not r["hidden"] and r["applies_to"] == profile.entity_class}
    lex_min = float(cfg["differential"]["shared_lexical_min"])
    cand_by_id = {c["candidate_id"]: c for c in store.candidates()}
    rows = []
    for d in _iter_matches(store.root / cfg["paths"]["matches"], classes, classes):
        src_id = d["source_candidate_id"]
        if d["source_entity_class"] == profile.entity_class and src_id not in in_scope:
            continue
        src = cand_by_id.get(src_id)
        if src is None:
            continue
        targets = json.loads(d["top_targets"]) if isinstance(d.get("top_targets"), str) else (d.get("top_targets") or [])
        top = targets[0] if targets else None
        status = d["status"]
        if status == "matched" and top:
            same = float(top.get("lexical_score") or 0) >= lex_min
            label = "shared" if same else "possibly different"
            conf = round(float(top.get("semantic_score") or 0), 3)
        elif status == "below_threshold":
            label, conf = "no counterpart found (possibly class-specific)", round(float(top.get("semantic_score") or 0), 3) if top else 0.0
        else:
            label, conf = "target class has no Direction in this subject family", 1.0
        tgt = cand_by_id.get(top["candidate_id"]) if (top and status == "matched") else None
        src_md = src["document_id"]
        rows.append({
            "row_id": f"DIF-{src_id}-{d['target_entity_class']}", "obligation_id": src_id,
            "md_id": src_md, "paragraph_id": src["paragraph_id"], "direction_title": store.title(src_md),
            "source_url": store.url(src_md), "source_class": d["source_entity_class"], "target_class": d["target_entity_class"],
            "subject_family": d.get("subject_family") or "", "excerpt": excerpt(store.obligation_sentence(src), 25),
            "differential": label, "confidence": conf,
            "semantic_score": float(top.get("semantic_score")) if top else None,
            "lexical_score": float(top.get("lexical_score")) if top else None,
            "counterpart_md_id": tgt["document_id"] if tgt else None,
            "counterpart_paragraph_id": tgt["paragraph_id"] if tgt else None,
            "counterpart_title": store.title(tgt["document_id"]) if tgt else None,
            "counterpart_url": store.url(tgt["document_id"]) if tgt else None,
            "counterpart_excerpt": excerpt(store.obligation_sentence(tgt), 25) if tgt else None,
            "needs_review": label != "shared" and not label.startswith("target class has no"),
            "caution": CAUTION if label in ("possibly different", "no counterpart found (possibly class-specific)") else "",
            "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""})
    rows.sort(key=lambda r: (r["source_class"], r["target_class"], r["md_id"], r["paragraph_id"]))
    return rows
