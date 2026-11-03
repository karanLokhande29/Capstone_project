"""Circulars Withdrawn / repeal information, from two sources reported separately.

1. **Local, no network.** The consolidated Master Directions already in
   ``data/processed`` carry two kinds of repeal information:

   * ``annex_list``: an appendix listing the circulars / notifications a
     Direction consolidated or repealed (mostly the FEMA and older Master
     Directions). One entry per list line that carries a circular reference.
   * ``repeal_statement``: the 2025 Directions' repeal paragraph, "the existing
     Directions, instructions, and guidelines relating to <subject> as
     applicable to <class> stand repealed, as communicated vide circular <ref>".
     The subject and class are kept verbatim.

   Each entry maps (old circular reference / title / subject) -> the repealing
   ``md_id``. This is the ``repeal_map`` link method.

2. **Online.** ``NotificationUserWithdrawnCircular.aspx`` (found 2026-09-26 via
   the "Consolidation of Regulations – Withdrawal of circulars" notification,
   DOR.RRC.REC.302/33-01-010/2025-26): one page listing every withdrawn
   circular (number, title, date). It does not say which Direction replaced
   each circular, so it cannot map to an ``md_id`` by itself.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from bs4 import BeautifulSoup

from src.supplementary.common import (
    HarvestContext,
    SupplementaryError,
    clean_text,
    make_item,
    parse_listing_date,
)

SOURCE = "withdrawn"
ORIGIN_LOCAL_ANNEX = "local_annex"
ORIGIN_LOCAL_STATEMENT = "local_repeal_statement"
ORIGIN_ONLINE = "online_list"
LIST_KEY = "withdrawn_list"

_ANNEX_HEADER = re.compile(
    r"(?:list\s+of|consolidated\s+list\s+of)\s+(?:the\s+)?(?:notifications?|circulars?|directions?|master\s+circulars?|"
    r"a\.?\s*p\.?\s*\(dir)[^\n]{0,120}?(?:consolidated|repealed|withdrawn|superseded|covered)|"
    r"consolidated\s+list\s+of\s+circulars|circulars?\s+(?:repealed|withdrawn)\b", re.IGNORECASE)
_NEW_ANNEX = re.compile(r"^\s*(?:Annex(?:ure)?|Appendix|Schedule)\b", re.IGNORECASE)
#: Circular / notification references as they appear in annex lists and elsewhere.
CIRCULAR_REF = re.compile(
    r"A\.?\s?P\.?\s*\(\s*DIR\s+Series\s*\)\s*Circular\s+No\.?\s*[\w/()\[\].\- ]{1,30}?(?=\s+(?:dated|[A-Z][a-z]+\s+\d)|$|\n|,)"
    r"|(?:FEMA\s+)?Notification\s+No\.?\s*[\w()/.\- ]{2,30}?-RB"
    r"|FEMA\s+\d+(?:\s*\(R\))?(?:\s*\(\d+\))?/\d{4}-RB"
    r"|\bRBI/\d{4}-\d{2}/\d+"
    r"|\b[A-Z]{2,6}(?:\.[A-Za-z&]{1,12}){1,5}\.?\s?(?:No\.)?\s?\d{1,4}/[\d.\-]+/\d{4}-\d{2}"
    r"|\bMaster\s+Circular\s+No\.?\s*[\w/.\-]+", re.IGNORECASE)
_REPEAL_STATEMENT = re.compile(
    r"relating\s+to\s+(?P<subj>.+?)\s+as\s+applicable\s+to\s+(?P<cls>.+?)\s+stand\s+repealed"
    r"(?:,?\s+as\s+communicated\s+vide\s+circular\s+(?:No\.?\s*)?(?P<ref>[A-Z][A-Za-z0-9.&/\-]*(?:\s?[0-9./\-]+)*)"
    r"(?:\s+dated\s+(?P<date>[A-Z][a-z]+\s+\d{1,2},\s*\d{4}))?)?",
    re.IGNORECASE | re.DOTALL)
_SERIAL = re.compile(r"^\s*(?:\d{1,4}[.)]?|[ivxlc]+[.)])\s+", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Local repeal information
# ---------------------------------------------------------------------------


def normalise_ref(ref: str) -> str:
    """Reference numbers compare without spaces, "No." or case."""
    return re.sub(r"(?<![a-z])no\.?(?=[\d(])", "", re.sub(r"\s+", "", ref.lower())).strip(".")


def _entry_title(line: str, refs: Sequence[str]) -> str:
    rest = line
    for r in refs:
        rest = rest.replace(r, " ")
    rest = re.sub(r"(?:dated\s+)?[A-Z][a-z]+\s+\d{1,2},?\s*\d{4}", " ", rest)
    rest = _SERIAL.sub("", rest)
    rest = clean_text(re.sub(r"[\[\]]|\(\s*\)", " ", rest)).strip(" -–,;:")
    return rest if len(rest.split()) >= 3 else ""


def extract_annex_entries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Annex-list entries in one Direction's paragraphs (in order). Pure; no I/O."""
    out: list[dict[str, Any]] = []
    i, n = 0, len(rows)
    while i < n:
        if not _ANNEX_HEADER.search(rows[i]["text"]):
            i += 1
            continue
        block = [rows[i]]
        j = i + 1
        while j < n and j - i <= 40 and not _NEW_ANNEX.match(rows[j]["text"]) \
                and not _ANNEX_HEADER.search(rows[j]["text"]) and CIRCULAR_REF.search(rows[j]["text"]):
            block.append(rows[j])
            j += 1
        for para in block:
            for line in para["text"].split("\n"):
                refs = [clean_text(m.group(0)) for m in CIRCULAR_REF.finditer(line)]
                if not refs:
                    continue
                out.append({"md_id": para["document_id"], "paragraph_id": para["paragraph_id"],
                            "kind": ORIGIN_LOCAL_ANNEX, "line": clean_text(line), "refs": refs,
                            "title": _entry_title(line, refs), "date": parse_listing_date(line)})
        i = j
    return out


def extract_repeal_statements(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        for m in _REPEAL_STATEMENT.finditer(clean_text(r["text"])):  # a reference can wrap across lines
            out.append({"md_id": r["document_id"], "paragraph_id": r["paragraph_id"], "kind": ORIGIN_LOCAL_STATEMENT,
                        "subject": clean_text(m.group("subj")), "applicable_to": clean_text(m.group("cls")),
                        "via_ref": re.sub(r"\s+", "", m.group("ref") or "").rstrip(".,") or None,
                        "date": parse_listing_date(m.group("date")), "line": clean_text(m.group(0))})
    return out


def local_repeal_map(paragraphs_by_doc: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Both local kinds over the whole corpus, plus counts for the report."""
    annex, statements = [], []
    for doc_id in sorted(paragraphs_by_doc):
        rows = paragraphs_by_doc[doc_id]
        annex += extract_annex_entries(rows)
        statements += extract_repeal_statements(rows)
    return {"annex_entries": annex, "repeal_statements": statements,
            "directions_with_annex": len({e["md_id"] for e in annex}),
            "directions_with_repeal_statement": len({e["md_id"] for e in statements})}


def local_items(repeal: Mapping[str, Any], cutoff) -> list[dict[str, Any]]:
    """Local repeal entries as §P items (source ``withdrawn``). The repealing md_id is known by construction."""
    items = []
    for idx, e in enumerate(repeal["annex_entries"], start=1):
        items.append(make_item(
            item_id=f"wdr_local_{idx:05d}", source=SOURCE, source_url=f"local:{e['paragraph_id']}",
            retrieved_at=None, content_hash=None, published_date=e["date"], title=e["title"] or e["line"],
            text=e["line"],
            fields={"origin": ORIGIN_LOCAL_ANNEX, "repealing_md_id": e["md_id"], "paragraph_id": e["paragraph_id"],
                    "refs": e["refs"]},
            cited_directions=e["refs"] + ([e["title"]] if e["title"] else []), entity_class=None, cutoff=cutoff))
    for idx, e in enumerate(repeal["repeal_statements"], start=1):
        items.append(make_item(
            item_id=f"wdr_stmt_{idx:05d}", source=SOURCE, source_url=f"local:{e['paragraph_id']}",
            retrieved_at=None, content_hash=None, published_date=e["date"], title=e["subject"], text=e["line"],
            fields={"origin": ORIGIN_LOCAL_STATEMENT, "repealing_md_id": e["md_id"], "paragraph_id": e["paragraph_id"],
                    "applicable_to": e["applicable_to"], "via_ref": e["via_ref"]},
            cited_directions=[e["subject"]], entity_class=None, cutoff=cutoff))
    return items


# ---------------------------------------------------------------------------
# Online withdrawn list
# ---------------------------------------------------------------------------


def parse_withdrawn_list(html: bytes | str) -> dict[str, Any]:
    """Every row of the online list: serial, circular number, title, date, notification link, '@' flag."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        raise SupplementaryError("withdrawn-circulars page has no table")
    table = max(tables, key=lambda t: len(t.find_all("tr")))
    rows, notes = [], []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) != 4:
            text = clean_text(tr.get_text(" "))
            if text:
                notes.append(text)
            continue
        serial, number, title, when = (clean_text(c.get_text(" ")) for c in cells)
        if not re.match(r"^\d+\.?$", serial):
            continue  # the header row
        link = cells[2].find("a", href=True) or cells[1].find("a", href=True)
        rows.append({"serial": int(serial.rstrip(".")), "circular_number": number,
                     "title": title.rstrip("@").strip(), "repeal_deferred": title.endswith("@"),
                     "date": parse_listing_date(when), "href": link["href"] if link else None})
    return {"rows": rows, "notes": notes}


def discover(ctx: HarvestContext) -> dict[str, Any]:
    """One request: the online list page is both the discovery page and the fetched content."""
    conf = ctx.sc.withdrawn
    store = ctx.store(SOURCE)
    if store.has_good(LIST_KEY):
        data = store.read_raw(LIST_KEY)
    else:
        res = ctx.get(conf["listing_url"], marker=conf["content_marker"])
        if not res.ok:
            store.record_failures([{**res.failure_record(), "item_key": LIST_KEY}])
            return {"source": SOURCE, "discovered": 0, "targets": [], "online_list_found": False,
                    "listing_failure": res.failure_record()}
        store.save(LIST_KEY, res)
        data = res.data
    parsed = parse_withdrawn_list(data)
    return {"source": SOURCE, "discovered": len(parsed["rows"]), "online_list_found": True,
            "targets": [{"item_key": f"wdr_{r['serial']:05d}", **r} for r in parsed["rows"]],
            "notes": parsed["notes"], "repeal_deferred_rows": sum(r["repeal_deferred"] for r in parsed["rows"])}


def fetch(ctx: HarvestContext, targets: Sequence[Mapping[str, Any]], limit: int | None = None) -> dict[str, Any]:
    """Nothing to fetch per row: every row came from the one page stored at discovery."""
    stored = ctx.store(SOURCE).has_good(LIST_KEY)
    n = len(targets) if limit is None else min(limit, len(targets))
    return {"source": SOURCE, "targets": len(targets), "already_stored": n if stored else 0, "attempted": 0,
            "fetched": 0, "failed": 0 if stored else n, "failure_reasons": {} if stored else {"not_stored": n},
            "failure_rate": 0.0 if stored else 1.0, "stopped": None, "note": "rows come from the single list page"}


def parse_all(ctx: HarvestContext, repeal: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Online rows (when the list was stored) plus local repeal entries (when ``repeal`` is given)."""
    store = ctx.store(SOURCE)
    items: list[dict[str, Any]] = []
    online = 0
    if store.has_good(LIST_KEY):
        entry = store.manifest()[LIST_KEY]
        for r in parse_withdrawn_list(store.read_raw(LIST_KEY))["rows"]:
            items.append(make_item(
                item_id=f"wdr_{r['serial']:05d}", source=SOURCE, source_url=entry["url"],
                retrieved_at=entry["retrieved_at"], content_hash=entry["content_hash"], published_date=r["date"],
                title=r["title"], text=r["title"],
                fields={"origin": ORIGIN_ONLINE, "serial": r["serial"], "circular_number": r["circular_number"],
                        "repeal_deferred": r["repeal_deferred"], "href": r["href"]},
                cited_directions=[r["circular_number"], r["title"]], entity_class=None, cutoff=ctx.sc.era_cutoff))
        online = len(items)
    local = local_items(repeal, ctx.sc.era_cutoff) if repeal else []
    store.write_items(items + local)
    return {"source": SOURCE, "items": len(items) + len(local), "online_items": online, "local_items": len(local)}


def iter_paragraphs_by_doc(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["document_id"], []).append(r)
    return out
