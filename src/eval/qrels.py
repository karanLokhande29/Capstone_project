"""T2 relevance sets, built only from human labels (P3-001).

Three sets, built separately and never pooled; each carries a known bias, stated
next to its results:

* ``t2_xclass_t1`` (main): P2-004 validated T1 items. One query per (item,
  compared class): the source obligation text, with that class as the target.
  Relevant = the final ``matched_paragraph_id`` (grade 2 ``same``, 1
  ``different``); ``none`` gives no relevant paragraph.
* ``t2_xclass_p2002``: the 60 P2-002 validation pairs. Query = the source unit
  text, target = class_b. Relevant = the target paragraph (2 ``same``, 1
  ``related``); ``unrelated`` pairs are dropped.
* ``t2_supp_p2003``: P2-003 alignment rows labelled ``paragraph`` /
  ``multi_paragraph``. Query = the FAQ Q&A, or the enforcement release's
  sustained charges (the penalty deficiencies). Relevant = the chosen paragraph
  ids (grade 2). Target class = the item's resolved entity class, if any.

Every query records its source paragraph (excluded from its own results) and a
cluster id (queries sharing a source text), for a clustered-bootstrap check.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

VERSION = "v1"

BIAS = {
    "t2_xclass_t1": (
        "Raters were shown the bge-base-en-v1.5 top-1/top-2 P2-002 candidates for each compared class "
        "(they could look up any paragraph), so the labelled counterparts favour the dense retriever."
    ),
    "t2_xclass_p2002": (
        "Pairs were drawn by bge-base-en-v1.5 semantic-score bands (the same model and revision as the "
        "dense system), so the relevant paragraphs favour the dense retriever."
    ),
    "t2_supp_p2003": (
        "Candidates shown to the rater were ranked by TF-IDF, which favours BM25 (the rater could enter any "
        "paragraph id of the Direction)."
    ),
}

GRADE_T1 = {"same": 2, "different": 1}
GRADE_P2002 = {"same": 2, "related": 1}
P2003_LABELS = ("paragraph", "multi_paragraph")
UNRESOLVED = "unresolved"


class QrelsError(ValueError):
    pass


def _query(qid: str, set_name: str, text: str, target_class: str | None, source_pid: str | None,
           relevant: Mapping[str, int], cluster: str, **meta: Any) -> dict[str, Any]:
    if not text.strip():
        raise QrelsError(f"{qid}: empty query text")
    return {
        "query_id": qid,
        "set": set_name,
        "text": text,
        "target_class": target_class,
        "source_paragraph_id": source_pid,
        "relevant": dict(sorted(relevant.items())),
        "cluster": cluster,
        **meta,
    }


def build_t1(items: Sequence[Mapping[str, Any]], paragraph_ids: set[str] | None = None) -> list[dict[str, Any]]:
    out = []
    for it in items:
        if it.get("label_status") != "validated":
            raise QrelsError(f"{it['item_id']}: label_status {it.get('label_status')!r}, expected validated")
        judgements = it["per_class_judgement"]
        for cls in sorted(it["compared_classes"]):
            j = judgements[cls]
            relevant: dict[str, int] = {}
            if j in GRADE_T1:
                pid = (it.get("matched_paragraph_id") or {}).get(cls)
                if not pid:
                    raise QrelsError(f"{it['item_id']} / {cls}: {j} without matched_paragraph_id")
                if paragraph_ids is not None and pid not in paragraph_ids:
                    raise QrelsError(f"{it['item_id']} / {cls}: unknown paragraph {pid}")
                relevant[pid] = GRADE_T1[j]
            elif j != "none":
                raise QrelsError(f"{it['item_id']} / {cls}: judgement {j!r}")
            out.append(_query(f"{it['item_id']}::{cls}", "t2_xclass_t1", it["obligation_span"]["text"], cls,
                              it["paragraph_id"], relevant, it["item_id"], judgement=j,
                              source_class=it["entity_class"]))
    return out


def candidate_to_paragraph(candidate_id: str) -> str:
    if not candidate_id.startswith("t1c_"):
        raise QrelsError(f"not a T1 candidate id: {candidate_id}")
    return candidate_id[len("t1c_"):]


def build_p2002(key_pairs: Mapping[str, Mapping[str, Any]], labelled: Sequence[Mapping[str, str]],
                paragraph_text: Mapping[str, str]) -> list[dict[str, Any]]:
    labels = {r["pair_id"]: (r.get("label") or "").strip() for r in labelled}
    if set(labels) != set(key_pairs):
        raise QrelsError("P2-002 sheet and key hold different pair ids")
    out = []
    for pair_id in sorted(key_pairs):
        lab = labels[pair_id]
        if lab == "unrelated":
            continue
        if lab not in GRADE_P2002:
            raise QrelsError(f"{pair_id}: label {lab!r}")
        p = key_pairs[pair_id]
        src = candidate_to_paragraph(p["source_candidate_id"])
        tgt = candidate_to_paragraph(p["target_candidate_id"])
        a, b = p["source_unit_offsets"]
        text = paragraph_text[src][a:b]
        out.append(_query(pair_id, "t2_xclass_p2002", text, p["class_b"], src, {tgt: GRADE_P2002[lab]}, src,
                          judgement=lab, source_class=p["class_a"], stratum=p.get("stratum")))
    return out


_CHARGES = re.compile(r"Charges sustained:\s*\n(?P<body>.*)\Z", re.S)


def p2003_query_text(source: str, item_text: str) -> tuple[str, str]:
    """FAQ: the Q&A as shown. Enforcement: the sustained-charges lines only; ``(text, basis)``."""
    if source == "faq":
        return item_text, "faq_qa"
    match = _CHARGES.search(item_text)
    body = match.group("body").strip() if match else ""
    if not body or body == "(none parsed)":
        return item_text, "enforcement_full_item_text"
    return body, "enforcement_charges"


def build_p2003(labelled: Sequence[Mapping[str, str]], key_items: Mapping[str, Mapping[str, Any]],
                paragraph_ids: set[str] | None = None) -> list[dict[str, Any]]:
    out = []
    for row in sorted(labelled, key=lambda r: r["item_id"]):
        if (row.get("label") or "").strip() not in P2003_LABELS:
            continue
        ids = [p.strip() for p in re.split(r"[;,\s]+", row.get("paragraph_ids") or "") if p.strip()]
        if not ids:
            raise QrelsError(f"{row['item_id']}: {row['label']} without paragraph ids")
        if paragraph_ids is not None and set(ids) - paragraph_ids:
            raise QrelsError(f"{row['item_id']}: unknown paragraph ids {sorted(set(ids) - paragraph_ids)}")
        key = key_items[row["item_id"]]
        cls = key.get("entity_class")
        target = None if cls in (None, "", UNRESOLVED) else cls
        text, basis = p2003_query_text(row["source"], row["item_text"])
        out.append(_query(row["item_id"], "t2_supp_p2003", text, target, None, {p: 2 for p in ids},
                          row["item_id"], judgement=row["label"], source=row["source"], text_basis=basis))
    return out


def summarise(queries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [q for q in queries if q["relevant"]]
    by_class: dict[str, int] = {}
    for q in scored:
        key = q["target_class"] or "(none)"
        by_class[key] = by_class.get(key, 0) + 1
    return {
        "queries": len(queries),
        "queries_with_relevant": len(scored),
        "queries_without_relevant": len(queries) - len(scored),
        "relevant_pairs": sum(len(q["relevant"]) for q in queries),
        "grade_counts": {str(g): sum(1 for q in queries for v in q["relevant"].values() if v == g) for g in (1, 2)},
        "clusters": len({q["cluster"] for q in scored}),
        "queries_with_target_class": sum(1 for q in scored if q["target_class"]),
        "by_target_class": dict(sorted(by_class.items())),
    }
