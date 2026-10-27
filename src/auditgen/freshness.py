"""Corpus freshness, and a safe incremental refresh that never touches the research corpus.

- ``status``: snapshot date, age, a warning past ``freshness_warn_days``.
- ``dry_run``: what an incremental re-harvest would fetch. Four requests at most (Master Direction listing; the
  notifications listing and its current-year page; the withdrawn-circulars list), 1.5 s apart, nothing written.
- ``apply``: downloads new or updated Directions and new Amendment Directions into ``data/auditgen_corpus/`` only,
  with the same rate limit and a request budget, extracts and segments them with the research pipeline's own code,
  and activates the new snapshot. ``data/processed`` and every research file stay unchanged; research results stay
  tied to the original corpus.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from src.auditgen.corpus import ROOT, CorpusStore, read_jsonl, research_config

RATE_LIMIT_SEC = 1.5


class RefreshError(RuntimeError):
    pass


def status(store: CorpusStore, cfg: Mapping[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    snap = store.snapshot.as_dict()
    try:
        age = (today - date.fromisoformat(snap["snapshot_date"])).days
    except ValueError:
        age = None
    warn = age is None or age > int(cfg["freshness_warn_days"])
    return {**snap, "age_days": age, "warn": warn,
            "message": (f"Corpus snapshot is {age} days old (older than {cfg['freshness_warn_days']}): run a refresh dry run."
                        if warn else f"Corpus snapshot is {age} days old."),
            "directions": len(store.docs), "paragraphs": len(store.paragraphs)}


class Fetcher:
    """Polite fetcher: >= 1.5 s between requests and a hard request budget."""

    def __init__(self, budget: int, *, session=None, rcfg: Mapping[str, Any] | None = None,
                 sleep: Callable[[float], None] = time.sleep, fetch_fn: Callable | None = None):
        from src.scraper.rbi_scraper import build_session

        self.rcfg = rcfg or research_config()
        self.session = session or build_session(self.rcfg)
        self.budget, self.used, self.sleep, self._last = budget, 0, sleep, None
        if fetch_fn is None:
            from src.supplementary.common import fetch_url

            fetch_fn = fetch_url
        self.fetch_fn = fetch_fn

    def get(self, url: str, *, marker: str | None, expect: str = "html", method: str = "GET", data=None):
        if self.used >= self.budget:
            raise RefreshError(f"request budget of {self.budget} reached")
        if self._last is not None:
            wait = RATE_LIMIT_SEC - (time.monotonic() - self._last)
            if wait > 0:
                self.sleep(wait)
        self.used += 1
        res = self.fetch_fn(url, self.session, self.rcfg, marker=marker, expect=expect, method=method, data=data)
        self._last = time.monotonic()
        return res


def _listing(fetcher: Fetcher) -> list[dict[str, Any]]:
    from src.scraper.rbi_scraper import _parse_listing
    from src.extraction.temporal_signals import extract_update_date_stamp

    rc = fetcher.rcfg
    url = rc["network"]["sources"]["rbi_master_directions"]["listing_url"]
    res = fetcher.get(url, marker=None)
    if not res.ok:
        raise RefreshError(f"Master Direction listing failed: {res.reason}")
    import logging

    rows = _parse_listing(res.data.decode("utf-8", "replace"), logger=logging.getLogger("auditgen.refresh"))
    return [{**r, "update_date": extract_update_date_stamp(r["title"])} for r in rows]


def dry_run(store: CorpusStore, cfg: Mapping[str, Any], *, fetcher: Fetcher | None = None) -> dict[str, Any]:
    from src.supplementary.common import aspnet_form
    from src.supplementary.enforcement import classify_titles, parse_dated_listing
    from src.supplementary.amendments import _NOTIF_ID
    from src.supplementary.withdrawn import parse_withdrawn_list

    fetcher = fetcher or Fetcher(budget=4)
    rc = fetcher.rcfg
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    listed = _listing(fetcher)
    known = store.docs
    new, updated, same = [], [], 0
    for r in listed:
        k = known.get(r["document_id"])
        rec = {"document_id": r["document_id"], "title": r["title"], "entity_class": r.get("entity_class_raw"),
               "update_date": r.get("update_date"), "url": r.get("pdf_url")}
        if k is None:
            new.append(rec)
        elif (k.get("update_date") or None) != (r.get("update_date") or None) or (k.get("source_url") or "") != (r.get("pdf_url") or ""):
            updated.append({**rec, "corpus_update_date": k.get("update_date")})
        else:
            same += 1
    removed = sorted(set(known) - {r["document_id"] for r in listed})
    amd = {"checked": False}
    sc = rc["supplementary"]["amendments"]
    first = fetcher.get(sc["listing_url"], marker=sc["content_marker"])
    if first.ok:
        year = date.today().year
        page = fetcher.get(sc["listing_url"], marker=sc["content_marker"], method="POST",
                           data={**aspnet_form(first.data), "hdnYear": str(year), "hdnMonth": "0"})
        if page.ok:
            rows = parse_dated_listing(page.data, _NOTIF_ID)
            kept = classify_titles(rows, sc["include_title_regex"], {"amendment_not_directions": sc["near_miss_title_regex"]})["kept"]
            have = {it["item_id"] for it in read_jsonl(ROOT / cfg["paths"]["amendments"])}
            fresh = [{"item_id": f"amd_{r['id']}", "title": r["title"], "listed_date": r["listed_date"],
                      "url": sc["notification_url"].format(id=r["id"])} for r in kept if f"amd_{r['id']}" not in have]
            amd = {"checked": True, "year": year, "listed": len(kept), "new": fresh}
    wd = {"checked": False}
    wc = rc["supplementary"]["withdrawn"]
    if fetcher.used < fetcher.budget:
        res = fetcher.get(wc["listing_url"], marker=wc["content_marker"])
        if res.ok:
            parsed = parse_withdrawn_list(res.data)
            have = {(it.get("fields") or {}).get("circular_number") for it in read_jsonl(ROOT / "data/supplementary/withdrawn/items_v1.jsonl")}
            fresh = [r for r in parsed["rows"] if r.get("circular_number") not in have]
            wd = {"checked": True, "listed": len(parsed["rows"]),
                  "new": [{"circular_number": r.get("circular_number"), "title": r.get("title") or r.get("subject"),
                           "date": r.get("date")} for r in fresh][:200]}
    return {"kind": "refresh_dry_run", "started_utc": started, "requests": fetcher.used, "rate_limit_sec": RATE_LIMIT_SEC,
            "snapshot": store.snapshot.as_dict(), "listing_count": len(listed), "unchanged": same,
            "new_directions": new, "updated_directions": updated, "removed_from_listing": removed,
            "amendment_directions": amd, "withdrawn_circulars": wd,
            "would_fetch": len(new) + len(updated) + len(amd.get("new", []) if amd.get("checked") else []),
            "writes": "none (dry run)"}


def assert_outside_research(target: Path) -> None:
    """Refuse a refresh target that is, contains or sits inside any research root (data/processed, benchmark, ...)."""
    from src.auditgen.guard import RESEARCH_ROOTS

    t = target.resolve()
    for r in RESEARCH_ROOTS:
        rr = (ROOT / r).resolve()
        if t == rr or rr in t.parents or t in rr.parents:
            raise RefreshError(f"refusing to write the refreshed corpus at {target}: it overlaps the research path {r}")


def apply(store: CorpusStore, cfg: Mapping[str, Any], *, budget: int = 80, fetcher: Fetcher | None = None,
          plan: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fetch what the dry run found into ``data/auditgen_corpus/`` and activate that snapshot."""
    from src.extraction.text_extractor import _extract_pdf_text
    from src.preprocessing.segmenter import segment_document
    from src.schemas.provenance import DocumentRecord
    from src.supplementary.amendments import parse_notification

    out_root = ROOT / cfg["paths"]["auditgen_corpus"]
    assert_outside_research(out_root)  # checked before anything is created
    fetcher = fetcher or Fetcher(budget=budget)
    plan = plan or dry_run(store, cfg, fetcher=fetcher)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap_dir = out_root / f"snapshot_{stamp}"
    proc = snap_dir / "processed"
    proc.mkdir(parents=True, exist_ok=False)
    manifest = {d["document_id"]: dict(d) for d in store.manifest}
    done, failed = [], []
    rc = fetcher.rcfg
    for rec in plan["new_directions"] + plan["updated_directions"]:
        res = fetcher.get(rec["url"], marker=None, expect="pdf")
        if not res.ok:
            failed.append({"document_id": rec["document_id"], "reason": res.reason})
            continue
        md = rec["document_id"]
        (snap_dir / "payloads").mkdir(exist_ok=True)
        (snap_dir / "payloads" / f"{md}.pdf").write_bytes(res.data)
        base = manifest.get(md, {})
        dr = DocumentRecord(document_id=md, source_url=rec["url"], title=rec["title"],
                            entity_class_raw=rec.get("entity_class") or base.get("entity_class_raw"), subject_family_raw=None,
                            update_date=rec.get("update_date"), extraction_source="rbi_master_directions",
                            document_role="primary_corpus", format="PDF")
        text = _extract_pdf_text(res.data, document_id=md)
        paras = segment_document(dr, text, rc)
        with (proc / f"{md}.jsonl").open("w", encoding="utf-8") as h:
            for p in paras:
                row = asdict(p)
                row.update({"entity_class": dr.entity_class_raw, "subject_family": base.get("subject_family"),
                            "document_title": rec["title"], "source_url": rec["url"], "update_date": rec.get("update_date")})
                h.write(json.dumps(row, ensure_ascii=False) + "\n")
        manifest[md] = {**base, "document_id": md, "source_url": rec["url"], "title": rec["title"],
                        "entity_class_raw": dr.entity_class_raw, "entity_class": base.get("entity_class") or dr.entity_class_raw,
                        "subject_family": base.get("subject_family"), "update_date": rec.get("update_date"),
                        "retrieved_at": res.retrieved_at, "content_hash": res.content_hash, "local_path": None,
                        "document_role": "primary_corpus", "format": "PDF", "extraction_source": "rbi_master_directions"}
        done.append(md)
    amd_items = list(read_jsonl(ROOT / cfg["paths"]["amendments"]))
    new_amd = []
    for a in (plan.get("amendment_directions") or {}).get("new", []):
        if fetcher.used >= fetcher.budget:
            break
        res = fetcher.get(a["url"], marker=rc["supplementary"]["amendments"]["content_marker"])
        if not res.ok:
            failed.append({"item_id": a["item_id"], "reason": res.reason})
            continue
        meta = {"notification_id": int(a["item_id"].split("_")[1]), "listing_title": a["title"], "listed_date": a["listed_date"]}
        entry = {"url": a["url"], "retrieved_at": res.retrieved_at, "content_hash": res.content_hash}
        from src.supplementary.common import parse_iso_date

        new_amd.append(parse_notification(res.data, meta, entry, parse_iso_date(rc["supplementary"]["era_cutoff"])))
    with (snap_dir / "manifest.jsonl").open("w", encoding="utf-8") as h:
        for d in sorted(manifest.values(), key=lambda d: d["document_id"]):
            h.write(json.dumps(d, ensure_ascii=False) + "\n")
    with (snap_dir / "amendments.jsonl").open("w", encoding="utf-8") as h:
        for it in amd_items + new_amd:
            h.write(json.dumps(it, ensure_ascii=False) + "\n")
    active = {"snapshot": snap_dir.name, "created_utc": stamp, "manifest": (snap_dir / "manifest.jsonl").relative_to(ROOT).as_posix(),
              "processed_dir": proc.relative_to(ROOT).as_posix(), "amendments": (snap_dir / "amendments.jsonl").relative_to(ROOT).as_posix(),
              "replaced_or_added_docs": done, "new_amendments": [x["item_id"] for x in new_amd], "failed": failed,
              "requests": fetcher.used, "removed_docs": []}
    (out_root / "active.json").write_text(json.dumps(active, indent=1))
    return {"kind": "refresh_apply", **active}
