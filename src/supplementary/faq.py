"""RBI FAQs: index -> topic pages -> Q&A items.

``FAQDisplay.aspx`` lists every topic in one table per category (checked
2026-09-26: 81 topics under 13 categories; the per-category ``?dId=`` pages
list the same topics). Each topic is a page ``FAQDisplay.aspx?Id=<n>``.

Topic markup is not uniform. Seen on the live pages: ``<p class="head">``
questions; "Query N: ... Clarification: ..." table rows; a bare row number in
one cell and the question in the next; a table of contents that lists every
question before repeating it with its answer; one answer shared by a run of
questions ("A.(1 to 4)"); a disclaimer before the first question. The splitter
below linearises the page into lines, marks lines inside heading-like elements,
and applies these rules in order. Topics whose content is only a linked PDF
yield no items and are counted as ``no_html_items``.
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

SOURCE = "faq"

_BLOCK_TAGS = ["p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ol", "ul",
               "blockquote"]
_HEAD_SELECTOR = ".head, b, strong, h1, h2, h3, h4, h5, h6, u"
_HEAD_ON, _HEAD_OFF = "\x01", "\x02"

#: "Q 1.", "Q.11.", "Query 2:", "Question 3", "Q1." — an explicit question label with a number.
_Q_LABELLED = re.compile(r"^Q(?:ue(?:ry|stion)?|uestion)?\s*\.?\s*(?:No\.?\s*)?\d+[a-z]?\b", re.IGNORECASE)
#: "Que -", "Query:" — an explicit label without a number.
_Q_LABEL_ONLY = re.compile(r"^Q(?:ue(?:ry|stion)?)?\s*[-–:]\s*\S", re.IGNORECASE)
#: "12.", "12)", "(12)" before the question text.
_Q_NUMBERED = re.compile(r"^(?:\d{1,3}[a-z]?\s*[.)]|\(\d{1,3}\))\s*\S")
_BARE_NUMBER = re.compile(r"^\d{1,3}\.?$")
_SKIP_LINE = re.compile(
    r"^(?:\d{1,3}\.?|[A-Z]\.?|Sr\.?\s*No\.?|S\.?\s*No\.?|Sl\.?\s*No\.?|FAQs?|Question|Contents|Top|Back to top|\*+)$",
    re.IGNORECASE)
#: A real disclaimer sentence, not a one-word table-of-contents entry.
_DISCLAIMER = re.compile(r"^disclaimer\b.{40,}", re.IGNORECASE)
#: "Ans.", "Answer:", "A:", "A.(1 to 4)", "A –". A bare "A." also opens section headings ("A. Classification").
_ANSWER_LABEL = re.compile(r"^(?:Ans(?:wer)?\b|A\s*[:(\-–]|A\.\s*\()", re.IGNORECASE)
_TOPIC_ID = re.compile(r"[?&]Id=(\d+)", re.IGNORECASE)
_MD_LINK = re.compile(r"BS_ViewMasDirections\.aspx\?id=(\d+)", re.IGNORECASE)
_NOTIFICATION_LINK = re.compile(r"(NotificationUser|BS_CircularIndexDisplay|BS_ViewMasCirculardetails|"
                                r"BS_ViewMasterCirculars|BS_PressReleaseDisplay)\.aspx", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def parse_index(html: bytes | str, topic_url: str) -> list[dict[str, Any]]:
    """Every topic on the index, in page order: id, category, title, listing date, PDF link."""
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("div#example-min")
    if root is None:
        raise SupplementaryError("FAQ index has no #example-min container; the layout may have changed")
    topics: list[dict[str, Any]] = []
    seen: set[str] = set()
    category = None
    for tr in root.find_all("tr"):
        header = tr.find("td", class_="tableheader")
        if header is not None and not tr.find("a", class_="link2"):
            category = clean_text(header.get_text(" "))
            continue
        link = tr.find("a", class_="link2")
        if link is None:
            continue
        m = _TOPIC_ID.search(link.get("href", ""))
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        bold = link.find("b")
        listed = clean_text(bold.get_text(" ")) if bold else ""
        full = clean_text(link.get_text(" "))
        title = full[len(listed):].strip() if listed and full.startswith(listed) else full
        pdf = next((a["href"] for a in tr.find_all("a", href=True) if a["href"].lower().endswith(".pdf")), None)
        topics.append({"item_key": f"faq_topic_{int(m.group(1)):04d}", "url": topic_url.format(id=m.group(1)),
                       "faq_topic_id": int(m.group(1)), "category": category, "topic_title": title,
                       "listed_date": parse_listing_date(listed), "pdf_url": pdf})
    return topics


def discover(ctx: HarvestContext) -> dict[str, Any]:
    conf = ctx.sc.faq
    store = ctx.store(SOURCE)
    res = ctx.get(conf["index_url"], marker=conf["content_marker"])
    if not res.ok:
        return {"source": SOURCE, "discovered": 0, "targets": [], "listing_failure": res.failure_record()}
    page = store.save_discovery_page("faq_index.html", res)
    targets = parse_index(res.data, conf["topic_url"])
    categories: dict[str, int] = {}
    for t in targets:
        categories[t["category"]] = categories.get(t["category"], 0) + 1
    return {"source": SOURCE, "discovered": len(targets), "targets": targets, "listing_pages": [page],
            "by_category": dict(sorted(categories.items()))}


def fetch(ctx: HarvestContext, targets: Sequence[Mapping[str, Any]], limit: int | None = None) -> dict[str, Any]:
    return fetch_items(ctx, SOURCE, targets, marker=ctx.sc.faq["content_marker"], limit=limit)


# ---------------------------------------------------------------------------
# Topic page -> Q&A
# ---------------------------------------------------------------------------


def topic_lines(html: bytes | str) -> tuple[list[tuple[str, bool]], dict[str, Any]]:
    """Linearise a topic page: ``(line, in_heading_element)`` plus header facts and links."""
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("div#example-min")
    if root is None:
        raise SupplementaryError("FAQ topic page has no #example-min container")
    headers = [clean_text(td.get_text(" ")) for td in root.select("td.tableheader")]
    date_line = next((h for h in headers if h.lower().startswith("date")), None)
    title = next((h for h in reversed(headers) if h and not h.lower().startswith("date")
                  and not re.fullmatch(r"[\d.]+\s*kb", h, re.IGNORECASE)), "")
    body = root.find("table", class_="td") or root
    for br in body.find_all("br"):
        br.replace_with("\n")
    for tag in body.select(_HEAD_SELECTOR):  # inside the tag, so the block newlines below stay outside
        tag.insert(0, _HEAD_ON)
        tag.append(_HEAD_OFF)
    for tag in body.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = []
    for raw in body.get_text().split("\n"):
        text = clean_text(raw.replace(_HEAD_ON, " ").replace(_HEAD_OFF, " "))
        if text:
            lines.append((text, _HEAD_ON in raw or _HEAD_OFF in raw))
    meta = {"topic_title_page": title, "page_date": parse_listing_date(date_line)}
    return lines, meta


def topic_links(html: bytes | str) -> list[dict[str, str]]:
    """Hyperlinks in the topic body that point at a Master Direction or a circular/notification."""
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("div#example-min")
    out = []
    for a in (root.find_all("a", href=True) if root else []):
        href = a["href"]
        if _MD_LINK.search(href) or _NOTIFICATION_LINK.search(href):
            out.append({"href": href, "text": clean_text(a.get_text(" "))})
    return out


def _is_question(lines: Sequence[tuple[str, bool]], i: int) -> bool:
    text, head = lines[i]
    if _Q_LABELLED.match(text) or _Q_LABEL_ONLY.match(text):
        return True
    if "?" in text and _Q_NUMBERED.match(text):
        return True
    if head and text.endswith("?"):
        return True
    prev = lines[i - 1][0] if i else ""
    return "?" in text and bool(_BARE_NUMBER.match(prev)) and len(text) < 400


def split_topic(lines: Sequence[tuple[str, bool]]) -> tuple[list[str], list[dict[str, Any]]]:
    """Lines -> (preamble, items). Each item: question, answer, section.

    1. A question starts an item; answer lines follow until the next question.
    2. A disclaimer ends the Q&A, unless it comes before the first question.
    3. A short heading line directly before a question, after an answered
       question, is a section heading (never an "Ans." line or a sentence).
    4. A table of contents is dropped: an answerless question whose text is
       asked again later, and a whole leading run of answerless questions
       when at least half of them are asked again later.
    5. A run of answerless questions followed by an answered one shares that
       answer ("A.(1 to 4)"), so the run becomes one item.
    """
    preamble: list[str] = []
    raw: list[dict[str, Any]] = []
    section = None
    n = len(lines)
    for i, (text, head) in enumerate(lines):
        if _DISCLAIMER.match(text):
            if raw:
                break
            continue
        if _is_question(lines, i):
            raw.append({"question": [text], "answer": [], "section": section})
            continue
        if _SKIP_LINE.match(text):
            continue
        nxt = next((j for j in range(i + 1, n) if not _SKIP_LINE.match(lines[j][0])), None)
        if (head and len(text) < 120 and not text.endswith(("?", ".")) and not _ANSWER_LABEL.match(text)
                and (not raw or raw[-1]["answer"]) and nxt is not None and _is_question(lines, nxt)):
            section = text
            continue
        (raw[-1]["answer"] if raw else preamble).append(text)

    def key(q: Sequence[str]) -> str:
        return re.sub(r"\W+", " ", re.sub(r"^\W*(?:q(?:ue(?:ry|stion)?)?)?\W*\d*\W*", "", " ".join(q).lower())).strip()

    later: dict[str, int] = {}
    for idx, it in enumerate(raw):
        later[key(it["question"])] = idx
    lead = next((i for i, it in enumerate(raw) if it["answer"]), len(raw))
    if lead >= 3 and sum(later[key(it["question"])] > i for i, it in enumerate(raw[:lead])) >= lead / 2:
        raw = raw[lead:]  # a table of contents, including entries whose wording differs from the body
        later = {key(it["question"]): idx for idx, it in enumerate(raw)}
    deduped = [it for idx, it in enumerate(raw) if it["answer"] or later[key(it["question"])] == idx]

    items: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for it in deduped:
        if not it["answer"]:
            pending.append(it)
            continue
        questions = [q for p in pending for q in p["question"]] + it["question"]
        items.append({"question": "\n".join(questions), "answer": "\n".join(it["answer"]),
                      "section": (pending[0]["section"] if pending else it["section"]),
                      "questions_grouped": len(pending) + 1})
        pending = []
    for p in pending:  # trailing answerless questions: kept, visibly empty
        items.append({"question": "\n".join(p["question"]), "answer": "", "section": p["section"],
                      "questions_grouped": 1})
    return preamble, items


def _by_frequency(values) -> list[str]:
    """Distinct values, most frequent first, then alphabetical: the Direction a topic links most comes first."""
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return sorted(counts, key=lambda v: (-counts[v], v))


def parse_topic(html: bytes | str, meta: Mapping[str, Any], manifest_entry: Mapping[str, Any], cutoff) -> dict:
    """One stored topic page -> Q&A items (§P schema) and a topic record."""
    lines, page = topic_lines(html)
    preamble, qa = split_topic(lines)
    links = topic_links(html)
    topic_id = int(meta["faq_topic_id"])
    published = meta.get("listed_date") or page["page_date"]
    title = meta.get("topic_title") or page["topic_title_page"]
    topic_cited = [link["text"] for link in links if link["text"]]
    items = []
    for idx, q in enumerate(qa, start=1):
        body = f"{q['question']}\n{q['answer']}".strip()
        cited = [link["text"] for link in links if link["text"] and link["text"] in body]
        md_ids = sorted({f"md_{m.group(1)}" for link in links if link["text"] and link["text"] in body
                         for m in [_MD_LINK.search(link["href"])] if m})
        items.append(make_item(
            item_id=f"faq_{topic_id:04d}_{idx:03d}", source=SOURCE, source_url=manifest_entry["url"],
            retrieved_at=manifest_entry["retrieved_at"], content_hash=manifest_entry["content_hash"],
            published_date=published, title=title, text=body,
            fields={"faq_topic_id": topic_id, "faq_item_index": idx, "category": meta.get("category"),
                    "topic_title": title, "section": q["section"], "question": q["question"], "answer": q["answer"],
                    "questions_grouped": q["questions_grouped"], "linked_md_ids": md_ids,
                    "topic_linked_md_ids": _by_frequency(f"md_{m.group(1)}" for link in links
                                                         for m in [_MD_LINK.search(link["href"])] if m),
                    "topic_cited_directions": list(dict.fromkeys([title] + topic_cited))},
            cited_directions=cited, entity_class=None, cutoff=cutoff))
    topic = {"faq_topic_id": topic_id, "category": meta.get("category"), "topic_title": title,
             "published_date": published, "items": len(items), "preamble_lines": len(preamble),
             "status": "ok" if items else "no_html_items", "pdf_url": meta.get("pdf_url"),
             "links": len(links)}
    return {"items": items, "topic": topic}


def parse_all(ctx: HarvestContext) -> dict[str, Any]:
    """Re-parse every stored topic page (deterministic; no network)."""
    store = ctx.store(SOURCE)
    items, topics = [], []
    for key in sorted(store.manifest()):
        entry = store.manifest()[key]
        out = parse_topic(store.read_raw(key), entry, entry, ctx.sc.era_cutoff)
        items += out["items"]
        topics.append(out["topic"])
    store.write_items(items)
    return {"source": SOURCE, "topics": len(topics), "items": len(items),
            "topics_without_html_items": [t["faq_topic_id"] for t in topics if t["status"] != "ok"],
            "topic_records": topics}
