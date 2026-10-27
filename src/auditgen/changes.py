"""Change-impact log: what changed between the last review and the as-of date, grouped by Direction."""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from src.auditgen.corpus import CorpusStore, excerpt, read_jsonl
from src.auditgen.profile import Profile


def _in_window(d: str | None, lo: str, hi: str) -> bool:
    return bool(d) and lo < d <= hi


def build_changes(store: CorpusStore, cfg: Mapping[str, Any], profile: Profile,
                  register: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    lo, hi = profile.last_review, profile.as_of
    out: list[dict[str, Any]] = []
    seen_new: set[str] = set()
    for r in register:
        pid = r["paragraph_id"]
        base = {k: r[k] for k in ("md_id", "paragraph_id", "direction_title", "source_url", "subject_family", "excerpt",
                                  "applies_to", "effective_from")}
        for e in store.temporal().events.get(pid, []):
            when = e.date or (e.window[-1] if e.window else None)
            window_hit = bool(e.window) and not e.date and e.window[0] <= hi and e.window[-1] > lo
            if _in_window(when, lo, hi) or window_hit:
                kind = ("deleted" if e.action == "delete" and e.scope == "paragraph_whole" else "amended")
                out.append({**base, "row_id": f"CHG-{e.item_id}-{pid}", "change": kind if not window_hit else "uncertain (effective window)",
                            "governing_instrument": e.item_id, "governing_title": e.title,
                            "governing_url": store.amendment_url(e.item_id), "instrument_date": store.amendment_date(e.item_id),
                            "effective": when, "status": r["status"], "confidence": 0.9 if e.date else 0.5,
                            "needs_review": not e.date, "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""})
        if _in_window(r["effective_from"], lo, hi):
            if r["effective_from_basis"] == "issue_date_letterhead":
                # A Direction first issued inside the window: each of its obligations is newly in force.
                out.append({**base, "row_id": f"CHG-new-{pid}", "change": "newly in force", "governing_instrument": r["md_id"],
                            "governing_title": r["direction_title"], "governing_url": r["source_url"],
                            "instrument_date": r["effective_from"], "effective": r["effective_from"], "status": r["status"],
                            "confidence": 0.8, "needs_review": False,
                            "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""})
            elif r["md_id"] not in seen_new:
                # Only the consolidated text's "Updated as on" stamp moved: one Direction-level row, no paragraph claim.
                out.append({**{k: base[k] for k in ("md_id", "direction_title", "source_url", "subject_family", "applies_to")},
                            "paragraph_id": None, "citation_level": "direction", "excerpt": "",
                            "effective_from": r["effective_from"], "row_id": f"CHG-upd-{r['md_id']}",
                            "change": "Direction text updated (consolidated 'Updated as on' date); changed paragraphs not identified",
                            "governing_instrument": r["md_id"], "governing_title": r["direction_title"], "governing_url": r["source_url"],
                            "instrument_date": r["effective_from"], "effective": r["effective_from"], "status": "updated",
                            "confidence": 0.6, "needs_review": True,
                            "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""})
            seen_new.add(r["md_id"])
    out.extend(_withdrawn(store, cfg, profile, lo, hi))
    out.sort(key=lambda x: (x["md_id"] or "", x.get("effective") or "", x["paragraph_id"] or ""))
    return out


def _withdrawn(store: CorpusStore, cfg: Mapping[str, Any], profile: Profile, lo: str, hi: str) -> list[dict[str, Any]]:
    """Withdrawn circulars in the window that the P2-003 links tie to one of the profile's Directions (Direction level)."""
    root = store.root
    wpath = root / "data/supplementary/withdrawn/items_v1.jsonl"
    if not wpath.exists():
        return []
    links = {l["item_id"]: l for l in read_jsonl(root / cfg["paths"]["supp_links"]) if l["item_id"].startswith("wdr_") and l.get("md_id")}
    rows = []
    for it in read_jsonl(wpath):
        lk = links.get(it["item_id"])
        if not lk or not _in_window(it.get("published_date"), lo, hi):
            continue
        md = lk["md_id"]
        if (store.docs.get(md) or {}).get("entity_class") != profile.entity_class:
            continue
        rows.append({"row_id": f"CHG-{it['item_id']}", "md_id": md, "paragraph_id": None, "citation_level": "direction",
                     "direction_title": store.title(md), "source_url": store.url(md),
                     "subject_family": (store.docs.get(md) or {}).get("subject_family") or "",
                     "excerpt": excerpt(it.get("title") or "", 25), "applies_to": profile.entity_class, "effective_from": None,
                     "change": "circular withdrawn", "governing_instrument": it["item_id"], "governing_title": it.get("title") or "",
                     "governing_url": it.get("source_url") or "", "instrument_date": it.get("published_date"),
                     "effective": it.get("published_date"), "status": "withdrawn (Direction-level link)",
                     "confidence": round(float(lk.get("score") or 0.5), 2), "needs_review": True,
                     "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""})
    return rows
