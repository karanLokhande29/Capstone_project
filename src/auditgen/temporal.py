"""As-of status of a paragraph: the research amendment index (``TemporalIndex``) plus the Direction's own date."""

from __future__ import annotations

from typing import Any

from src.auditgen.corpus import CorpusStore

STATUS_LABEL = {"in_force": "in force", "original_amended_later": "in force (amendment scheduled)",
                "amended": "in force, amended", "deleted": "deleted", "uncertain": "uncertain (effective window)",
                "not_yet": "not yet in force"}
# T3 gold vocabulary, for validation only.
T3_MAP = {"in_force": "in_force_original", "original_amended_later": "in_force_original", "amended": "amended",
          "deleted": "deleted"}


def paragraph_status(store: CorpusStore, pid: str, as_of: str) -> dict[str, Any]:
    md = pid.split("::")[0]
    eff, basis = store.in_force_from(md)
    st = store.temporal().status(pid, as_of)
    events = []
    for e in store.temporal().events.get(pid, []):
        when = e.date or (e.window[-1] if e.window else None)
        events.append({"amendment_id": e.item_id, "action": e.action, "scope": e.scope, "effective": when,
                       "window": e.window, "title": e.title, "url": store.amendment_url(e.item_id),
                       "issued": store.amendment_date(e.item_id)})
    state = st["state"]
    if eff and eff > as_of and state == "in_force":
        state = "not_yet"
    governing = st.get("governing") or md
    return {"state": state, "label": STATUS_LABEL[state], "effective_from": eff, "effective_from_basis": basis,
            "governing_instrument": governing,
            "governing_url": store.amendment_url(governing) if governing != md else store.url(md),
            "amended_by": [e for e in events if e["effective"] and e["effective"] <= as_of],
            "scheduled": [e for e in events if not e["effective"] or e["effective"] > as_of],
            "events": events}


def t3_prediction(store: CorpusStore, item: dict) -> str:
    """The generator's T3 status for one T3 item, in the T3 gold vocabulary."""
    st = store.temporal().status(item["paragraph_id"], item["as_of"])["state"]
    return T3_MAP.get(st, st)
