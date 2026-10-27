"""Enforcement-risk view: RBI monetary-penalty press releases (P2-003) against the profile's class, per Direction.

Links are Direction-level weak labels (P2-003: 53.3% clean alignment on a 30-item check), and a press release names a
subject, not a paragraph. This view is prioritisation context only, not a prediction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from src.auditgen.corpus import CorpusStore, read_jsonl
from src.auditgen.profile import Profile

LABEL = "Prioritisation context only: past penalties on similar entities, not a prediction."
LINK_NOTE = "Direction-level weak link (P2-003 alignment: 16/30 clean, 53.3%)."


def build_enforcement(store: CorpusStore, cfg: Mapping[str, Any], profile: Profile,
                      register: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    root = store.root
    links: dict[str, list[dict]] = defaultdict(list)
    for l in read_jsonl(root / cfg["paths"]["supp_links"]):
        if l["item_id"].startswith("enf_") and l.get("md_id"):
            links[l["item_id"]].append(l)
    fam_of = {md: (d.get("subject_family") or "") for md, d in store.docs.items()}
    # A release linked to another class's Direction counts for the profile's Direction of the same subject family.
    own_by_family: dict[str, list[str]] = defaultdict(list)
    for md, d in store.docs.items():
        if d.get("entity_class") == profile.entity_class and d.get("subject_family"):
            own_by_family[d["subject_family"]].append(md)
    agg: dict[str, dict[str, Any]] = {}
    for it in read_jsonl(root / cfg["paths"]["enforcement"]):
        if it.get("entity_class") != profile.entity_class:
            continue
        for l in links.get(it["item_id"], []):
            md = l["md_id"]
            targets = [md] if (store.docs.get(md) or {}).get("entity_class") == profile.entity_class else own_by_family.get(fam_of.get(md, ""), [])
            for t in targets:
                a = agg.setdefault(t, {"releases": {}, "cited": set(), "via": set()})
                fields = it.get("fields") or {}
                a["releases"][it["item_id"]] = {"date": it.get("published_date"), "url": it.get("source_url"),
                                                "amount": fields.get("penalty_amount"), "entity": fields.get("entity_name")}
                a["cited"].add(l.get("cited_string") or "")
                a["via"].add("direct" if t == md else f"same subject family via {md}")
    obligations = defaultdict(int)
    for r in register:
        if not r["hidden"]:
            obligations[r["md_id"]] += 1
    rows = []
    for md, a in agg.items():
        rel = sorted(a["releases"].items(), key=lambda kv: kv[1]["date"] or "", reverse=True)
        rows.append({"row_id": f"ENF-{md}", "md_id": md, "paragraph_id": None, "citation_level": "direction",
                     "direction_title": store.title(md), "source_url": store.url(md), "subject_family": fam_of.get(md, ""),
                     "entity_class": profile.entity_class, "penalty_count": len(rel),
                     "first_date": rel[-1][1]["date"] if rel else None, "last_date": rel[0][1]["date"] if rel else None,
                     "press_releases": [{"id": k, **v} for k, v in rel],
                     "cited_subjects": sorted(s for s in a["cited"] if s)[:8], "link_basis": sorted(a["via"]),
                     "obligations_in_register": obligations.get(md, 0), "label": LABEL, "link_note": LINK_NOTE,
                     "needs_review": True, "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""})
    rows.sort(key=lambda r: (-r["penalty_count"], r["md_id"]))
    return rows


def risk_by_family(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[r["subject_family"]] += r["penalty_count"]
    return dict(out)
