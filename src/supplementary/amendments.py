"""Amendment Directions: post-consolidation notifications that amend a Master Direction.

Discovery: ``NotificationUser.aspx`` year listings (POST ``hdnYear``, month 0),
the same layout as the press releases. A notification is kept when its title
matches ``include_title_regex`` ("... Amendment Directions, 2026") and it is
dated on or after the era cut-off. Other titles with "amendment" (FEMA
regulations, UAPA list updates) are counted as near misses.

Parsing records, verbatim and for T3 later: the amended Direction as the body
cites it, the target implied by the title, links to a Master Direction page,
and every paragraph reference. Amendments are never applied to corpus text.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from bs4 import BeautifulSoup

from src.supplementary.common import (
    HarvestContext,
    SupplementaryError,
    clean_text,
    fetch_items,
    make_item,
    parse_listing_date,
)
from src.supplementary.enforcement import classify_titles, parse_dated_listing, year_listings

SOURCE = "amendment"

_NOTIF_ID = re.compile(r"[?&]Id=(\d+)", re.IGNORECASE)
_MD_LINK = re.compile(r"BS_ViewMasDirections\.aspx\?id=(\d+)", re.IGNORECASE)
#: "Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025", one level of nested brackets.
_RBI_DIRECTIONS = re.compile(r"Reserve\s+Bank\s+of\s+India\s+\((?:[^()]|\([^()]*\))+\)\s+(?:[A-Za-z]+\s+)?"
                             r"(?:Amendment\s+)?Directions?,?\s*\d{4}")
_MASTER_DIRECTION = re.compile(r"Master\s+Directions?\s*[-–—]\s*[^,.;()]+(?:\([^()]*\)[^,.;()]*)?")
_AMENDMENT_SUFFIX = re.compile(r"\s+(?:(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\s+)?"
                               r"(?:\(\s*)?Amendment(?:\s*\))?\s+Directions?,?\s*\d{4}\s*$", re.IGNORECASE)
_PARA_REF = re.compile(
    r"\b(?:sub-)?(?:[Pp]aragraphs?|[Pp]aras?|[Cc]lauses?)\s+(?:[Nn]o\.?\s*)?"
    r"\d+[A-Z]?(?:\.\d+)*(?:\s*\([0-9a-zA-Z]{1,6}\))*"
    r"(?:\s*(?:,|and|to|&|or)\s*\d+[A-Z]?(?:\.\d+)*(?:\s*\([0-9a-zA-Z]{1,6}\))*)*")
_ANNEX_REF = re.compile(r"\bAnnex(?:ure)?\s*[-–]?\s*[IVXLC0-9]+[A-Z]?\b")
_RBI_REF = re.compile(r"\bRBI/\d{4}-\d{2}/\d+\b")
_DEPT_REF = re.compile(r"\b[A-Z]{2,6}(?:\.[A-Za-z&]{1,12}){1,5}\.?\s?(?:No\.)?\s?\d{1,4}/[\d.\-]+/\d{4}-\d{2}\b")


def discover(ctx: HarvestContext) -> dict[str, Any]:
    conf = ctx.sc.amendments
    pages, records, failures = year_listings(ctx, SOURCE, conf["listing_url"], conf["years"],
                                             conf["content_marker"], "notifications")
    rows: dict[int, dict[str, Any]] = {}
    for page in pages:
        for r in parse_dated_listing(page, _NOTIF_ID):
            rows.setdefault(r["id"], r)
    classified = classify_titles(list(rows.values()), conf["include_title_regex"],
                                 {"amendment_not_directions": conf["near_miss_title_regex"]})
    cutoff = ctx.sc.era_cutoff.isoformat()
    kept = [r for r in classified["kept"] if r["listed_date"] and r["listed_date"] >= cutoff]
    before = len(classified["kept"]) - len(kept)
    targets = [{"item_key": f"amd_{r['id']}", "url": conf["notification_url"].format(id=r["id"]),
                "notification_id": r["id"], "listing_title": r["title"], "listed_date": r["listed_date"],
                "pdf_url": r["pdf_url"]} for r in sorted(kept, key=lambda r: r["id"])]
    return {"source": SOURCE, "discovered": len(targets), "targets": targets, "listing_pages": records,
            "listing_failures": failures, "notifications_listed": len(rows),
            "amendment_directions_before_cutoff_excluded": before,
            "near_misses_excluded": len(classified["near_misses"]),
            "near_miss_by_pattern": classified["near_miss_by_pattern"]}


def fetch(ctx: HarvestContext, targets: Sequence[Mapping[str, Any]], limit: int | None = None) -> dict[str, Any]:
    return fetch_items(ctx, SOURCE, targets, marker=ctx.sc.amendments["content_marker"], limit=limit)


def notification_text(html: bytes | str) -> tuple[str, str | None, str, list[dict[str, str]]]:
    """(title, date, body text, links) from a notification page."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="tablebg")
    if table is None:
        raise SupplementaryError("notification page has no table.tablebg")
    headers = [clean_text(td.get_text(" ")) for td in table.find_all("td", class_="tableheader")]
    date_line = next((h for h in headers if h.lower().startswith("date")), None)
    title = next((h for h in reversed(headers) if h and not h.lower().startswith("date")
                  and not re.search(r"\bkb\b", h, re.IGNORECASE)), "")
    body = table.find("table", class_="td") or table
    links = [{"href": a["href"], "text": clean_text(a.get_text(" "))} for a in body.find_all("a", href=True)]
    for br in body.find_all("br"):
        br.replace_with("\n")
    for tag in body.find_all(["p", "div", "li", "tr", "td"]):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = [clean_text(line) for line in body.get_text().split("\n")]
    return title, parse_listing_date(date_line), "\n".join(line for line in lines if line), links


def title_target(title: str) -> str | None:
    """The Direction a title says it amends: the title without "(Nth) Amendment", no year."""
    if not _AMENDMENT_SUFFIX.search(title):
        return None
    return _AMENDMENT_SUFFIX.sub(" Directions", title).strip()


def parse_notification(html: bytes | str, meta: Mapping[str, Any], entry: Mapping[str, Any], cutoff) -> dict:
    title, page_date, text, links = notification_text(html)
    title = title or meta.get("listing_title", "")
    flat = clean_text(text)
    own_title = clean_text(title).lower()
    cited_rbi = [clean_text(m.group(0)) for m in _RBI_DIRECTIONS.finditer(flat)]
    amended = [c for c in dict.fromkeys(cited_rbi) if "amendment" not in c.lower() and c.lower() != own_title]
    earlier_amendments = [c for c in dict.fromkeys(cited_rbi) if "amendment" in c.lower() and c.lower() != own_title]
    master = [clean_text(m.group(0)) for m in _MASTER_DIRECTION.finditer(flat)]
    md_links = sorted({f"md_{m.group(1)}" for link in links for m in [_MD_LINK.search(link["href"])] if m})
    para_refs = list(dict.fromkeys(clean_text(m.group(0)) for m in _PARA_REF.finditer(flat)))
    annex_refs = list(dict.fromkeys(clean_text(m.group(0)) for m in _ANNEX_REF.finditer(flat)))
    derived = title_target(title)
    published = meta.get("listed_date") or page_date
    cited = amended + list(dict.fromkeys(master)) + ([derived] if derived else [])
    return make_item(
        item_id=f"amd_{int(meta['notification_id'])}", source=SOURCE, source_url=entry["url"],
        retrieved_at=entry["retrieved_at"], content_hash=entry["content_hash"], published_date=published,
        title=title, text=text,
        fields={"notification_id": int(meta["notification_id"]),
                "rbi_ref": next(iter(_RBI_REF.findall(flat)), None),
                "dept_ref": next(iter(_DEPT_REF.findall(flat)), None),
                "amended_directions_cited": amended, "title_derived_target": derived,
                "earlier_amendments_cited": earlier_amendments, "master_directions_cited": list(dict.fromkeys(master)),
                "linked_md_ids": md_links, "paragraph_refs": para_refs, "annex_refs": annex_refs,
                "pdf_url": meta.get("pdf_url")},
        cited_directions=cited, entity_class=None, cutoff=cutoff)


def parse_all(ctx: HarvestContext) -> dict[str, Any]:
    store = ctx.store(SOURCE)
    items = []
    for key in sorted(store.manifest()):
        entry = store.manifest()[key]
        items.append(parse_notification(store.read_raw(key), entry, entry, ctx.sc.era_cutoff))
    store.write_items(items)
    return {"source": SOURCE, "items": len(items)}
