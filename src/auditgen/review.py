"""Reviewer workflow: row-level review (unreviewed / confirmed / disputed / not applicable), re-import of a reviewed
Excel workbook, and sign-off. A re-import never edits the original pack: it writes a new, signed-off pack beside it."""

from __future__ import annotations

import copy
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROW_ID = re.compile(r"^(APP|CHG|CAL|DIF|ENF|GAP)-")
REVIEW_STATUSES = ("unreviewed", "confirmed", "disputed", "not applicable")
REVIEW_SECTIONS = {"Applicability": "register", "Changes": "changes", "Calendar": "calendar", "Differential": "differential",
                   "Enforcement": "enforcement", "Gap analysis": "gaps"}


class ReviewError(ValueError):
    pass


def _rows(pack: Mapping[str, Any], section: str) -> list[dict[str, Any]]:
    v = pack.get(section)
    if isinstance(v, dict):
        return v.get("rows") or []
    return v or []


def apply_updates(pack: dict[str, Any], updates: Sequence[Mapping[str, Any]], *, now: str | None = None) -> int:
    """``updates``: {section, row_id, review_status, reviewer, note}. Returns the number of rows changed."""
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    index = {(sec, r["row_id"]): r for sec in REVIEW_SECTIONS.values() for r in _rows(pack, sec)}
    n = 0
    for u in updates:
        st = (u.get("review_status") or "").strip().lower()
        if st not in REVIEW_STATUSES:
            raise ReviewError(f"review_status {u.get('review_status')!r} must be one of {REVIEW_STATUSES}")
        row = index.get((u.get("section"), u.get("row_id")))
        if row is None:
            raise ReviewError(f"unknown row {u.get('section')}/{u.get('row_id')}")
        if st != "unreviewed" and not str(u.get("reviewer") or "").strip():
            raise ReviewError(f"row {u['row_id']}: a reviewer name is required")
        changed = (row.get("review_status"), row.get("reviewer"), row.get("note")) != (st, u.get("reviewer") or "", u.get("note") or "")
        row.update({"review_status": st, "reviewer": u.get("reviewer") or "", "note": u.get("note") or "",
                    "timestamp": u.get("timestamp") or now if changed else row.get("timestamp", "")})
        n += changed
    return n


def progress(pack: Mapping[str, Any]) -> dict[str, Any]:
    out = {}
    for label, sec in REVIEW_SECTIONS.items():
        rows = _rows(pack, sec)
        if sec == "register":
            rows = [r for r in rows if not r.get("hidden")]
        c = {s: sum(1 for r in rows if (r.get("review_status") or "unreviewed") == s) for s in REVIEW_STATUSES}
        out[sec] = {"label": label, "total": len(rows), **c,
                    "needs_review_unreviewed": sum(1 for r in rows if r.get("needs_review") and (r.get("review_status") or "unreviewed") == "unreviewed")}
    tot = sum(v["total"] for v in out.values())
    done = sum(v["total"] - v["unreviewed"] for v in out.values())
    return {"sections": out, "reviewed": done, "total": tot, "share": round(done / tot, 3) if tot else 0.0}


def read_review_workbook(path: Path) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    updates = []
    for sheet, sec in REVIEW_SECTIONS.items():
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        rows = ws.iter_rows(values_only=True)
        header = [str(h or "").strip() for h in next(rows, [])]
        need = ("row_id", "review_status", "reviewer", "note")
        if not all(h in header for h in need):
            continue
        ix = {h: header.index(h) for h in need}
        for vals in rows:
            rid = vals[ix["row_id"]]
            if not rid or not ROW_ID.match(str(rid)):
                continue  # blank lines and the disclaimer footer
            st = str(vals[ix["review_status"]] or "unreviewed").strip().lower()
            updates.append({"section": sec, "row_id": str(rid), "review_status": st,
                            "reviewer": str(vals[ix["reviewer"]] or "").strip(), "note": str(vals[ix["note"]] or "").strip()})
    return updates


def signed_off(pack: Mapping[str, Any], updates: Sequence[Mapping[str, Any]], *, signer: str, source_name: str,
               source_sha256: str) -> dict[str, Any]:
    """A new pack with the reviews applied and a sign-off record; the original pack is not modified."""
    if not signer.strip():
        raise ReviewError("a sign-off needs the signer's name")
    new = copy.deepcopy(pack)
    changed = apply_updates(new, updates)
    prog = progress(new)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new["derived_from"] = pack["pack_id"]
    new["pack_id"] = f"{pack['pack_id']}_signed_" + hashlib.sha256((now + source_sha256).encode()).hexdigest()[:6]
    new["created_utc"] = now
    disputed = [{"section": sec, "row_id": r["row_id"], "note": r.get("note", ""), "reviewer": r.get("reviewer", "")}
                for sec in REVIEW_SECTIONS.values() for r in _rows(new, sec) if r.get("review_status") == "disputed"]
    new["signoff"] = {"signer": signer.strip(), "signed_utc": now, "source_workbook": source_name,
                      "source_workbook_sha256": source_sha256, "rows_updated": changed, "progress": prog,
                      "complete": prog["reviewed"] == prog["total"], "disputed": disputed,
                      "statement": ("Reviewed rows reflect the reviewers' decisions recorded here. Unreviewed rows remain "
                                    "decision support only and are not settled.")}
    return new
