"""RBI enforcement: monetary-penalty press releases.

Discovery: ``BS_PressReleaseDisplay.aspx`` shows only the latest releases; a
POST with ``hdnYear=<year>, hdnMonth=0`` returns the whole year (checked
2026-09-26: 166 penalty releases in 2026 to date). Rows sit under a date
heading. Titles matching ``include_title_regex`` are penalty releases; titles
matching a near-miss pattern (cancelled registrations, section 35A directions)
are excluded and counted by pattern.

Parsing keeps the direction titles a release quotes (``‘Know Your Customer
(KYC)’``) and the deficiency sentences verbatim. A release that cites a subject
without quotes ("directions issued by RBI on Know Your Customer (KYC)") keeps
that subject too, marked unquoted. Statute contraventions ("Section 20 read
with Section 56 of the Banking Regulation Act") are kept apart: they are not
Master Directions.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from bs4 import BeautifulSoup

from src.supplementary.common import (
    UNRESOLVED,
    HarvestContext,
    SupplementaryError,
    aspnet_form,
    clean_text,
    fetch_items,
    make_item,
    parse_listing_date,
)

SOURCE = "enforcement"

_PRID = re.compile(r"[?&]prid=(\d+)", re.IGNORECASE)
_NOTIF_ID = re.compile(r"[?&]Id=(\d+)", re.IGNORECASE)
_ENTITY_FROM_TITLE = re.compile(r"monetary\s+penalty\s+on\s+(?P<name>.+?)\s*$", re.IGNORECASE)
_ORDER_DATE = re.compile(r"by\s+an\s+order\s+dated\s+(?P<d>[A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})")
_AMOUNT = re.compile(r"monetary\s+penalty\s+of\s+(?P<amt>₹\s?[\d,.]+(?:\s*(?:lakh|crore))?(?:/-)?)", re.IGNORECASE)
_POWERS = re.compile(r"in\s+exercise\s+of\s+(?:the\s+)?powers\s+conferred\s+on\s+RBI\s+under\s+(?P<s>[^.]+?\b(?:Act|Rules),?\s*\d{4})",
                     re.IGNORECASE)
#: Paired quotes: ‘…’, “…”, "…", and '…' when the ' is not an apostrophe.
_QUOTED = re.compile(r"(?<![\w’'])(?:‘(?P<a>[^‘’]{3,300}?)’|“(?P<b>[^“”]{3,300}?)”|\"(?P<c>[^\"]{3,300}?)\"|"
                     r"'(?P<d>[^']{3,300}?)')(?![A-Za-z])")
_UNQUOTED_SUBJECT = re.compile(
    r"(?:directions?|instructions?|guidelines?)\s+issued\s+by\s+(?:RBI|the\s+Reserve\s+Bank(?:\s+of\s+India)?)\s+"
    r"(?:on|under|regarding|relating\s+to)\s+(?P<s>[^‘“\"'].*?)"
    r"(?=\s+and\s+(?:certain|specific|operational|contravention|non-compliance|provisions)|,\s|;|\.\s|\.$|$)",
    re.IGNORECASE)
_STATUTE = re.compile(r"(?:contravention|non-compliance|violation)\s+(?:of|with)\s+(?:the\s+)?(?:certain\s+)?"
                      r"(?:provisions?\s+of\s+)?(?P<s>Sections?\s+[^.;]+?(?:Act|Rules),?\s*\d{4}(?:\s*\([A-Z .]+\))?)",
                      re.IGNORECASE)
_FINDING_START = re.compile(r"sustained|found,?\s+inter\s+alia,?\s+that", re.IGNORECASE)
#: The boilerplate close, the signature "(Brij Raj) Chief General Manager", or the release number.
_FINDING_END = re.compile(r"^(?:This\s+action\s+is\s+based|The\s+action\s+is\s+based|Further,\s+imposition|"
                          r"\([A-Z][a-z]+(?:\s+[A-Z][a-z.]*)+\)|Press\s+Release\s*:)")
_PRESS_RELEASE_NO = re.compile(r"Press\s+Release\s*:\s*(?P<n>\d{4}-\d{4}/\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Entity class (deterministic rules only)
# ---------------------------------------------------------------------------

_CO_OP = re.compile(r"co-?\s?operative|sahakari|souharda|co-op\b", re.IGNORECASE)
_RURAL_CO_OP = re.compile(r"district\s+central|state\s+co-?\s?operative\s+bank|\bDCCB\b|\bStCB\b|\bapex\b",
                          re.IGNORECASE)
_NABARD_INSPECTION = re.compile(r"inspection\s+of\s+the\s+bank\s+was\s+conducted\s+by\s+(?:the\s+)?National\s+Bank\s+"
                                r"for\s+Agriculture|conducted\s+by\s+NABARD", re.IGNORECASE)
_AIFI_NAME = re.compile(r"\bNABARD\b|National\s+Bank\s+for\s+Agriculture|\bSIDBI\b|Small\s+Industries\s+Development|"
                        r"Export-Import\s+Bank|\bEXIM\b|National\s+Housing\s+Bank|\bNaBFID\b", re.IGNORECASE)

#: (rule id, raw class, predicate over (name, body)). First match wins.
ENTITY_RULES: tuple[tuple[str, str, Any], ...] = (
    ("name:payments_bank", "Payments Banks", lambda n, b: re.search(r"payments\s+bank", n, re.I)),
    ("name:small_finance_bank", "Small Finance Banks", lambda n, b: re.search(r"small\s+finance\s+bank", n, re.I)),
    ("name:local_area_bank", "Local Area Banks", lambda n, b: re.search(r"local\s+area\s+bank", n, re.I)),
    ("name:aifi", "All India Financial Institutions", lambda n, b: _AIFI_NAME.search(n)),
    ("name:rrb", "Regional Rural Banks",
     lambda n, b: re.search(r"gramin|grameen|regional\s+rural", n, re.I) and not _CO_OP.search(n)),
    ("name:rural_co_operative", "Rural Co-operative Banks",
     lambda n, b: _CO_OP.search(n) and re.search(r"bank", n, re.I) and _RURAL_CO_OP.search(n)),
    ("name:co_operative+nabard_inspection", "Rural Co-operative Banks",
     lambda n, b: _CO_OP.search(n) and re.search(r"bank", n, re.I) and _NABARD_INSPECTION.search(b)),
    ("name:urban_co_operative", "Urban Co-operative Banks",
     lambda n, b: _CO_OP.search(n) and re.search(r"bank", n, re.I)),
    ("name:asset_reconstruction", "Asset Reconstruction Companies",
     lambda n, b: re.search(r"asset\s+reconstruction", n, re.I)),
    ("name:credit_information", "Credit Information Companies",
     lambda n, b: re.search(r"credit\s+information|\bCIBIL\b|\bCRIF\b|experian|equifax", n, re.I)),
    ("statute:rbi_act_chapter_iiib", "Non-Banking Financial Companies",
     lambda n, b: re.search(r"Section\s+58\s*[-(]?\s*[GB]\b", b, re.I)),
    ("statute:nhb_act", "Non-Banking Financial Companies",
     lambda n, b: re.search(r"National\s+Housing\s+Bank\s+Act", b, re.I)),
    ("statute:pss_act", "Payment and Settlement System",
     lambda n, b: re.search(r"Payment\s+and\s+Settlement\s+Systems\s+Act", b, re.I)),
    ("statute:fema", "Foreign Exchange Management",
     lambda n, b: re.search(r"Foreign\s+Exchange\s+Management\s+Act", b, re.I)),
    ("name:bank+br_act", "Commercial Banks",
     lambda n, b: re.search(r"\bbank\b|\bbanking\s+corporation\b|citibank", n, re.I)
     and re.search(r"Banking\s+Regulation\s+Act", b, re.I)),
)


def resolve_entity_class(name: str, body: str) -> tuple[str, str | None]:
    for rule, cls, pred in ENTITY_RULES:
        if pred(name, body):
            return cls, rule
    return UNRESOLVED, None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def parse_dated_listing(html: bytes | str, id_re: re.Pattern) -> list[dict[str, Any]]:
    """Rows of a year listing (press releases or notifications): id, title, date, PDF."""
    soup = BeautifulSoup(html, "lxml")
    rows, current = [], None
    for tr in soup.find_all("tr"):
        header = tr.find("td", class_="tableheader")
        if header is not None and not tr.find("a", class_="link2"):
            current = parse_listing_date(header.get_text(" ")) or current
            continue
        link = tr.find("a", class_="link2", href=id_re)
        if link is None:
            continue
        pdf = next((a["href"] for a in tr.find_all("a", href=True) if a["href"].lower().endswith(".pdf")), None)
        rows.append({"id": int(id_re.search(link["href"]).group(1)), "title": clean_text(link.get_text(" ")),
                     "listed_date": current, "pdf_url": pdf})
    return rows


def classify_titles(rows: Sequence[Mapping[str, Any]], include: str, near_miss: Mapping[str, str]) -> dict:
    inc = re.compile(include, re.IGNORECASE)
    misses = {k: re.compile(v, re.IGNORECASE) for k, v in near_miss.items()}
    kept, near, near_by = [], [], {k: 0 for k in misses}
    for r in rows:
        if inc.search(r["title"]):
            kept.append(r)
            continue
        hit = next((k for k, rx in misses.items() if rx.search(r["title"])), None)
        if hit:
            near_by[hit] += 1
            near.append({**r, "near_miss": hit})
    return {"kept": kept, "near_misses": near, "near_miss_by_pattern": near_by}


def year_listings(ctx: HarvestContext, source: str, listing_url: str, years: Sequence[int], marker: str,
                  prefix: str) -> tuple[list[bytes], list[dict[str, Any]], list[dict[str, Any]]]:
    """GET the listing once (for the ASP.NET form), then POST each year. Returns pages, page records, failures."""
    store = ctx.store(source)
    first = ctx.get(listing_url, marker=marker)
    if not first.ok:
        return [], [], [first.failure_record()]
    pages, records, failures = [], [store.save_discovery_page(f"{prefix}_listing.html", first)], []
    form = aspnet_form(first.data)
    for year in years:
        res = ctx.get(listing_url, marker=marker, method="POST",
                      data={**form, "hdnYear": str(year), "hdnMonth": "0"})
        if res.ok:
            pages.append(res.data)
            records.append(store.save_discovery_page(f"{prefix}_{year}.html", res))
        else:
            failures.append({**res.failure_record(), "year": year})
    return pages, records, failures


def discover(ctx: HarvestContext) -> dict[str, Any]:
    conf = ctx.sc.enforcement
    pages, records, failures = year_listings(ctx, SOURCE, conf["listing_url"], conf["years"],
                                             conf["content_marker"], "press_releases")
    rows: dict[int, dict[str, Any]] = {}
    for page in pages:
        for r in parse_dated_listing(page, _PRID):
            rows.setdefault(r["id"], r)
    classified = classify_titles(list(rows.values()), conf["include_title_regex"], conf["near_miss_title_regexes"])
    targets = [{"item_key": f"enf_{r['id']}", "url": conf["release_url"].format(id=r["id"]), "prid": r["id"],
                "listing_title": r["title"], "listed_date": r["listed_date"], "pdf_url": r["pdf_url"]}
               for r in sorted(classified["kept"], key=lambda r: r["id"])]
    return {"source": SOURCE, "discovered": len(targets), "targets": targets, "listing_pages": records,
            "listing_failures": failures, "press_releases_listed": len(rows),
            "near_misses_excluded": len(classified["near_misses"]),
            "near_miss_by_pattern": classified["near_miss_by_pattern"],
            "near_miss_examples": [{"id": r["id"], "title": r["title"], "pattern": r["near_miss"]}
                                   for r in classified["near_misses"][:20]]}


def fetch(ctx: HarvestContext, targets: Sequence[Mapping[str, Any]], limit: int | None = None) -> dict[str, Any]:
    return fetch_items(ctx, SOURCE, targets, marker=ctx.sc.enforcement["content_marker"], limit=limit)


# ---------------------------------------------------------------------------
# Release page
# ---------------------------------------------------------------------------


def release_blocks(html: bytes | str) -> tuple[str, str | None, list[str]]:
    """(title, date, body blocks) from a press-release page."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="tablebg")
    if table is None:
        raise SupplementaryError("press release page has no table.tablebg")
    headers = [clean_text(td.get_text(" ")) for td in table.find_all("td", class_="tableheader")]
    date_line = next((h for h in headers if h.lower().startswith("date")), None)
    title = next((h for h in reversed(headers) if h and not h.lower().startswith("date")
                  and not re.search(r"\bkb\b", h, re.IGNORECASE)), "")
    body = table.find("table", class_="td") or table
    blocks = []
    for el in body.find_all(["p", "li"]):
        if el.find(["p", "li"]):
            continue  # a container; its children are visited
        text = clean_text(el.get_text(" "))
        if text:
            blocks.append(text)
    return title, parse_listing_date(date_line), blocks


def quoted_titles(text: str) -> list[str]:
    out = []
    for m in _QUOTED.finditer(text):
        q = next(g for g in m.groups() if g is not None).strip()
        if q:
            out.append(q)
    return out


def _citation_clause(blocks: Sequence[str]) -> str:
    """The sentence(s) naming what was breached: the first block with the penalty, up to "This penalty"."""
    first = next((b for b in blocks if re.search(r"monetary\s+penalty", b, re.IGNORECASE)), blocks[0] if blocks else "")
    return re.split(r"\.\s+This\s+penalty\s+has\s+been\s+imposed", first, maxsplit=1)[0]


def deficiencies(blocks: Sequence[str]) -> list[str]:
    """The sustained charges, verbatim: blocks after the "sustained" sentence, before the boilerplate close."""
    start = next((i for i, b in enumerate(blocks) if _FINDING_START.search(b)), None)
    if start is None:
        return []
    out = []
    head = blocks[start]
    m = re.search(r"(?:sustained|that)[^:]*:\s*(?P<rest>.+)$", head)
    if m and len(m.group("rest")) > 20:
        out.append(m.group("rest"))
    for b in blocks[start + 1:]:
        if _FINDING_END.match(b):
            break
        out.append(b)
    return out


def parse_release(html: bytes | str, meta: Mapping[str, Any], entry: Mapping[str, Any], cutoff) -> dict[str, Any]:
    title, page_date, blocks = release_blocks(html)
    title = title or meta.get("listing_title", "")
    body = "\n".join(blocks)
    clause = _citation_clause(blocks)
    quoted = quoted_titles(clause)
    unquoted = [s for s in (clean_text(m.group("s")).rstrip(" .,") for m in _UNQUOTED_SUBJECT.finditer(clause))
                if len(s) >= 4]
    statutes = [clean_text(m.group("s")) for m in _STATUTE.finditer(_QUOTED.sub(" ", clause))]
    m = _ENTITY_FROM_TITLE.search(title) or _ENTITY_FROM_TITLE.search(meta.get("listing_title", ""))
    name = m.group("name") if m else ""
    entity_class, rule = resolve_entity_class(name, body)
    order = _ORDER_DATE.search(body)
    amount = _AMOUNT.search(body)
    powers = _POWERS.search(body)
    pr_no = _PRESS_RELEASE_NO.search(body)
    defs = deficiencies(blocks)
    published = meta.get("listed_date") or page_date
    item = make_item(
        item_id=f"enf_{int(meta['prid'])}", source=SOURCE, source_url=entry["url"],
        retrieved_at=entry["retrieved_at"], content_hash=entry["content_hash"], published_date=published,
        title=title, text=body,
        fields={"prid": int(meta["prid"]), "entity_name": name, "entity_class_rule": rule,
                "order_date": parse_listing_date(order.group("d")) if order else None,
                "penalty_amount": amount.group("amt") if amount else None,
                "powers_under": clean_text(powers.group("s")) if powers else None,
                "press_release_no": pr_no.group("n") if pr_no else None,
                "quoted_titles": quoted, "unquoted_subjects": unquoted, "statutes_cited": statutes,
                "deficiencies": defs, "pdf_url": meta.get("pdf_url")},
        cited_directions=quoted + unquoted, entity_class=entity_class, cutoff=cutoff)
    return item


def parse_all(ctx: HarvestContext) -> dict[str, Any]:
    store = ctx.store(SOURCE)
    items = []
    for key in sorted(store.manifest()):
        entry = store.manifest()[key]
        items.append(parse_release(store.read_raw(key), entry, entry, ctx.sc.era_cutoff))
    store.write_items(items)
    return {"source": SOURCE, "items": len(items)}
