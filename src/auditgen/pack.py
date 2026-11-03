"""Assemble an audit pack: every section, the About box and the citation / excerpt checks."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from src.auditgen import applicability as APP
from src.auditgen import calendar_extract as CAL
from src.auditgen import changes as CHG
from src.auditgen import differential as DIF
from src.auditgen import enforcement as ENF
from src.auditgen import freshness as FR
from src.auditgen import validation as VAL
from src.auditgen.corpus import ROOT, CorpusStore, word_count
from src.auditgen.profile import Profile

SECTIONS = ("register", "changes", "calendar", "differential", "enforcement", "gaps")
PARAGRAPH_CITATION = ("md_id", "paragraph_id", "direction_title", "source_url")
DIRECTION_CITATION = ("md_id", "direction_title", "source_url")
RELEASE_CITATION = ("direction_title", "source_url")  # an RBI press release that names no current Direction
EXCERPT_FIELDS = ("excerpt", "counterpart_excerpt", "phrase")


class CitationError(ValueError):
    pass


def require_citation(section: str, row: Mapping[str, Any]) -> None:
    """No citation, no row: paragraph-level rows need md_id, paragraph_id, title and URL; Direction-level rows
    (enforcement, withdrawn circulars) need md_id, title and URL and say so in ``citation_level``; release-level rows
    (enforcement releases that cite no current Direction) need a title and the press release's rbi.org.in URL."""
    level = row.get("citation_level")
    need = DIRECTION_CITATION if level == "direction" else RELEASE_CITATION if level == "release" else PARAGRAPH_CITATION
    missing = [k for k in need if not row.get(k)]
    if section in ("register", "calendar") and not row.get("status"):
        missing.append("status")
    if missing:
        raise CitationError(f"{section} row {row.get('row_id')} lacks {missing}")
    if not str(row["source_url"]).startswith("https://"):
        raise CitationError(f"{section} row {row.get('row_id')} has no rbi.org.in link")


def enforce_rules(pack: dict[str, Any], max_words: int) -> dict[str, Any]:
    """Drop any row without a citation (counted) and assert every RBI excerpt is within the word limit."""
    dropped = {}
    for sec in SECTIONS:
        rows = pack.get(sec)
        if isinstance(rows, dict):  # gaps
            rows = rows.get("rows")
        if not rows:
            continue
        keep = []
        for r in rows:
            try:
                require_citation(sec, r)
            except CitationError:
                d = dropped.setdefault(sec, {"count": 0, "md_ids": []})
                d["count"] += 1
                if r.get("md_id") and r["md_id"] not in d["md_ids"]:
                    d["md_ids"].append(r["md_id"])
                continue
            for f in EXCERPT_FIELDS:
                if r.get(f) and sec != "gaps" and word_count(r[f]) > max_words:
                    raise CitationError(f"{sec} row {r.get('row_id')}: {f} exceeds {max_words} words")
            keep.append(r)
        rows[:] = keep
    return dropped


def about(store: CorpusStore, cfg: Mapping[str, Any], profile: Profile) -> dict[str, Any]:
    return {"tool": "RBI-ObliBench audit generator", "tool_version": cfg["tool_version"], "rules_version": cfg["version"],
            "rules_sha256": cfg["_sha256"], "corpus": store.snapshot.as_dict(), "as_of": profile.as_of,
            "last_review": profile.last_review, "entity_profile": profile.as_dict(), "validation": VAL.box(store),
            "disclaimer": cfg["disclaimer"], "freshness": FR.status(store, cfg),
            "privacy": "Generated locally. No API calls. Uploaded policies never leave this machine.",
            "excerpt_rule": f"RBI excerpts are at most {cfg['excerpt_max_words']} words; follow the link for the official text."}


def calendar_section(cfg: Mapping[str, Any], profile: Profile, register) -> list[dict[str, Any]]:
    out = []
    t = float(cfg["calendar"]["review_threshold"])
    start = date.fromisoformat(profile.as_of)
    end = start + timedelta(days=365)
    for r in register:
        if r["hidden"]:
            continue
        for k, e in enumerate(r.get("_calendar") or []):
            entry = {"row_id": f"CAL-{r['obligation_id']}-{k}", "entry_id": f"CAL-{r['obligation_id']}-{k}",
                     "obligation_id": r["obligation_id"], "md_id": r["md_id"], "paragraph_id": r["paragraph_id"],
                     "direction_title": r["direction_title"], "source_url": r["source_url"], "status": r["status"],
                     "subject_family": r["subject_family"], "excerpt": r["excerpt"], **e,
                     "summary": f"{CAL.summary([e])}: {r['direction_title'][:60]}",
                     "verify": e["confidence"] < t, "needs_review": e["confidence"] < t,
                     "review_status": "unreviewed", "reviewer": "", "note": "", "timestamp": ""}
            entry["next_due"] = [d.isoformat() for d in CAL.occurrences(entry, start, end, cfg["calendar"]["financial_year_end"])]
            out.append(entry)
    out.sort(key=lambda e: (e["next_due"][0] if e["next_due"] else "9999", e["md_id"]))
    return out


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "profile"


def generate(store: CorpusStore, cfg: Mapping[str, Any], profile: Profile) -> dict[str, Any]:
    profile.validate(store.core_classes)
    register = APP.build_register(store, cfg, profile)
    cal = calendar_section(cfg, profile, register)
    changes = CHG.build_changes(store, cfg, profile, register)
    diff = DIF.build_differential(store, cfg, profile, register)
    enf = ENF.build_enforcement(store, cfg, profile, register)
    for r in register:
        r.pop("_calendar", None)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pid = f"{slug(profile.name)}_{profile.as_of}_" + hashlib.sha256((json.dumps(profile.as_dict(), sort_keys=True) + created).encode()).hexdigest()[:8]
    pack = {"pack_id": pid, "kind": "audit_pack", "created_utc": created, "profile": profile.as_dict(),
            "about": about(store, cfg, profile), "disclaimer": cfg["disclaimer"],
            "register": register, "changes": changes, "calendar": cal, "differential": diff, "enforcement": enf,
            "differential_caution": DIF.CAUTION if diff else "", "enforcement_label": ENF.LABEL, "gaps": None,
            "signoff": None, "derived_from": None}
    pack["dropped_without_citation"] = enforce_rules(pack, int(cfg["excerpt_max_words"]))
    pack["summary"] = summarise(pack)
    return pack


def summarise(pack: Mapping[str, Any]) -> dict[str, Any]:
    reg = pack["register"]
    vis = [r for r in reg if not r["hidden"]]
    by_status: dict[str, int] = {}
    by_dir: dict[str, dict[str, Any]] = {}
    for r in vis:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        d = by_dir.setdefault(r["md_id"], {"md_id": r["md_id"], "direction_title": r["direction_title"], "source_url": r["source_url"], "obligations": 0})
        d["obligations"] += 1
    start = pack["profile"]["as_of"]
    end = (date.fromisoformat(start) + timedelta(days=90)).isoformat()
    next90 = sorted(((d, e) for e in pack["calendar"] for d in e["next_due"] if start <= d <= end), key=lambda x: x[0])
    gaps = pack.get("gaps") or {}
    review_rows = [r for sec in ("register", "changes", "calendar", "differential", "enforcement") for r in pack.get(sec) or []]
    if gaps:
        review_rows += gaps.get("rows", [])
    reviewed = sum(1 for r in review_rows if r.get("review_status") not in (None, "", "unreviewed"))
    return {"register_rows": len(reg), "register_visible": len(vis), "register_hidden": len(reg) - len(vis),
            "needs_review": sum(1 for r in vis if r["needs_review"]), "by_status": by_status,
            "by_direction": sorted(by_dir.values(), key=lambda d: -d["obligations"]),
            "changes": len(pack["changes"]), "top_changes": pack["changes"][:10],
            "calendar_entries": len(pack["calendar"]), "calendar_verify": sum(1 for e in pack["calendar"] if e["verify"]),
            "next_90_days": [{"date": d, "entry_id": e["entry_id"], "summary": e["summary"], "verify": e["verify"],
                              "source_url": e["source_url"], "paragraph_id": e["paragraph_id"]} for d, e in next90[:60]],
            "differential_rows": len(pack["differential"]),
            "differential_needs_review": sum(1 for r in pack["differential"] if r["needs_review"]),
            "enforcement_directions": sum(1 for r in pack["enforcement"] if r.get("md_id")),
            "enforcement_releases": len({p["id"] for r in pack["enforcement"] for p in r["press_releases"]}),
            "gaps": gaps.get("counts") if gaps else None,
            "highest_risk_gaps": [r for r in (gaps.get("rows") or []) if r["coverage"] == "missing"][:15] if gaps else [],
            "review_progress": {"reviewed": reviewed, "total": len(review_rows)}}


def runs_dir(cfg: Mapping[str, Any]) -> Path:
    return ROOT / cfg["paths"]["runs"]


def save(pack: Mapping[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / "pack.json"
    p.write_text(json.dumps(pack, ensure_ascii=False))
    return p


def load(cfg: Mapping[str, Any], pack_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9_\-]+", pack_id or ""):
        raise FileNotFoundError(pack_id)
    for base in (runs_dir(cfg), ROOT / cfg["paths"]["samples"]):
        for p in (base / pack_id / "pack.json",):
            if p.exists():
                return json.loads(p.read_text())
    raise FileNotFoundError(pack_id)


def list_packs(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for kind, base in (("run", runs_dir(cfg)), ("sample", ROOT / cfg["paths"]["samples"])):
        if not base.exists():
            continue
        for p in sorted(base.glob("*/pack.json")):
            try:
                d = json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
            out.append({"pack_id": d["pack_id"], "kind": kind, "created_utc": d["created_utc"], "profile": d["profile"],
                        "signed_off": bool(d.get("signoff")), "summary": {k: d["summary"].get(k) for k in ("register_visible", "needs_review", "changes", "calendar_entries")}})
    return sorted(out, key=lambda x: x["created_utc"], reverse=True)
