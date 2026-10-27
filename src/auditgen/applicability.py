"""Applicability register: the deontic candidates (P2-001 v4, kept) that bind the profile's class as of a date.

Rules v1:
- a paragraph of a Direction issued for the profile's class applies (confidence ``class_direction``);
- a paragraph of a cross-cutting function-heading Direction applies only through a selected activity
  (``function_heading``), and is marked for review;
- a class Direction with no subject family (often written for a sub-type, e.g. Housing Finance Companies) applies with
  the lower ``subtype_direction`` confidence and is marked for review;
- activity flags narrow the list through subject families: narrowed rows are kept, marked "filtered by activity" and
  hidden by default, never deleted; paragraphs deleted or not yet in force on the as-of date are kept and hidden too.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.auditgen import calendar_extract as CAL
from src.auditgen import temporal as TMP
from src.auditgen.corpus import CorpusStore, excerpt
from src.auditgen.profile import Profile


def family_activities(cfg: Mapping[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for act, fams in cfg["activities"].items():
        for f in fams:
            out.setdefault(f, set()).add(act)
    return out


def _direction_scope(store: CorpusStore, cfg: Mapping[str, Any], md: str, profile: Profile) -> dict[str, Any] | None:
    d = store.docs.get(md) or {}
    cls = d.get("entity_class")
    conf = cfg["confidence"]
    if cls == profile.entity_class:
        if d.get("subject_family"):
            return {"applies_to": cls, "basis": "Direction issued for the class", "confidence": conf["class_direction"], "note": ""}
        return {"applies_to": cls, "basis": "Direction issued for the class (no subject family: may be written for a sub-type)",
                "confidence": conf["subtype_direction"], "note": "Check that this Direction covers your entity type."}
    if cls in store.function_headings:
        act = cfg["function_heading_activities"].get(cls, "none")
        if act == "core" or act in profile.activities:
            return {"applies_to": f"cross-cutting ({cls})", "basis": f"function-heading Direction via activity '{act}'",
                    "confidence": conf["function_heading"], "note": "Cross-cutting Direction: confirm it covers your entity type."}
    return None


def build_register(store: CorpusStore, cfg: Mapping[str, Any], profile: Profile) -> list[dict[str, Any]]:
    fam_acts = family_activities(cfg)
    review_t = float(cfg["confidence"]["review_threshold"])
    max_words = int(cfg["excerpt_max_words"])
    rows = []
    scopes: dict[str, dict | None] = {}
    for c in store.candidates():
        md = c["document_id"]
        if md not in scopes:
            scopes[md] = _direction_scope(store, cfg, md, profile)
        scope = scopes[md]
        if scope is None:
            continue
        para = store.paragraphs[c["paragraph_id"]]
        doc = store.docs.get(md) or {}
        fam = doc.get("subject_family")
        st = TMP.paragraph_status(store, c["paragraph_id"], profile.as_of)
        sentence = store.obligation_sentence(c)
        cal = CAL.extract(sentence)
        acts = fam_acts.get(fam or "", set())
        filtered = bool(acts) and not (acts & set(profile.activities))
        hidden = []
        if filtered:
            hidden.append("filtered by activity (" + ", ".join(sorted(acts)) + ")")
        if st["state"] in ("deleted", "not_yet"):
            hidden.append(st["label"] + " on the as-of date")
        conf = scope["confidence"] - (cfg["confidence"]["status_uncertain_penalty"] if st["state"] == "uncertain" else 0.0)
        conf = round(max(0.0, conf), 2)
        rows.append({
            "row_id": f"APP-{c['candidate_id']}", "obligation_id": c["candidate_id"],
            "md_id": md, "paragraph_id": c["paragraph_id"], "direction_title": doc.get("title") or "",
            "section": " ".join(x for x in [para.get("section_id") or "", para.get("section_title") or ""] if x).strip(),
            "clause": para.get("clause_path") or "",
            "excerpt": excerpt(sentence, max_words),
            "applies_to": scope["applies_to"], "applicability_basis": scope["basis"], "scope_note": scope["note"],
            "status": st["label"], "status_state": st["state"], "as_of": profile.as_of,
            "effective_from": st["effective_from"], "effective_from_basis": st["effective_from_basis"],
            "governing_instrument": st["governing_instrument"], "governing_url": st["governing_url"],
            "amended_by": [{"id": e["amendment_id"], "effective": e["effective"], "url": e["url"], "action": e["action"]}
                           for e in st["amended_by"]],
            "scheduled_changes": [{"id": e["amendment_id"], "effective": e["effective"], "url": e["url"], "action": e["action"]}
                                  for e in st["scheduled"]],
            "deadline_frequency": CAL.summary(cal), "subject_family": fam or "",
            "source_url": doc.get("source_url") or "", "confidence": conf,
            "needs_review": conf < review_t or st["state"] == "uncertain",
            "filtered_by_activity": filtered, "hidden": bool(hidden), "hidden_reason": "; ".join(hidden),
            "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": "",
            "_calendar": cal,
        })
    rows.sort(key=lambda r: (r["md_id"], store.paragraphs[r["paragraph_id"]].get("position") or 0))
    return rows
