"""A3 direction-level linking: each cited string -> a Master Direction, or none.

Methods, tried in this order for every cited string; the first that links wins:

1. ``exact_ref``: a hyperlink to ``BS_ViewMasDirections.aspx?id=N`` whose
   ``md_N`` is in the manifest; an RBI reference number that a Direction
   carries in its opening paragraphs; or the exact consolidated title
   (normalised; with or without its year).
2. ``repeal_map``: a reference number, title or subject that a local repeal
   entry (annex list or "stand repealed" statement) maps to its repealing
   Direction. Exact after normalisation.

Methods 1-3 respect the item's entity class (see :meth:`LinkIndex.scope`): a
match that exists only in another class's Direction is not a link, and the
next method is tried. An explicit Master Direction hyperlink is exempt.
3. ``title_fuzzy``: token Dice between the cited subject and each Direction's
   subject, >= ``linking.fuzzy_threshold`` (config, fixed before labelling).
   When the item's entity class is resolved, only that class's Directions and
   the function-heading Directions are candidates.
4. ``none``.

Ties at the best score are broken by ``linking.tie_break_class_order``, then
``md_id``; the second best and the margin are recorded either way. No
paragraph-level link is produced here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from src.benchmark.candidates import normalise_sentence
from src.supplementary.common import UNRESOLVED, clean_text
from src.supplementary.withdrawn import CIRCULAR_REF, normalise_ref

METHOD_EXACT = "exact_ref"
METHOD_REPEAL = "repeal_map"
METHOD_FUZZY = "title_fuzzy"
METHOD_NONE = "none"
METHODS = (METHOD_EXACT, METHOD_REPEAL, METHOD_FUZZY, METHOD_NONE)

LINK_FIELDS = ("item_id", "cited_string", "md_id", "method", "score", "second_best_md_id", "margin",
               "cited_scope", "basis", "tied_best")

_MD_LINK = re.compile(r"BS_ViewMasDirections\.aspx\?id=(\d+)", re.IGNORECASE)
_UPDATED = re.compile(r"\(\s*updated\s+as\s+on[^)]*\)", re.IGNORECASE)
_YEAR = re.compile(r",?\s*\b(?:19|20)\d{2}\b")
_DASHES = re.compile(r"\s*[-–—]\s*")

#: Words that say "this is a Direction" rather than what it is about.
TITLE_STOPWORDS = frozenset(
    "a an and as at by for from in into of on or the to under with its their be is are "
    "reserve bank india rbi master direction directions circular circulars guidelines guideline instructions "
    "instruction norms amendment amendments updated revised issued certain provisions provision "
    "regulated entities entity res".split())

#: Entity-class names dropped from a subject as whole phrases ("Housing Finance for UCBs" -> "housing finance").
#: Single words are never dropped: "finance", "credit", "payment" also name subjects.
_CLASS_PHRASES = re.compile(
    r"\b(?:primary\s*\(?\s*urban\s*\)?\s*cooperative\s+banks?|(?:urban|rural|state|district\s+central)\s+"
    r"cooperative\s+banks?|cooperative\s+banks?|small\s+finance\s+banks?|payments\s+banks?|local\s+area\s+banks?|"
    r"regional\s+rural\s+banks?|commercial\s+banks?|non-?\s?banking\s+financial\s+compan(?:y|ies)|"
    r"all\s+india\s+financial\s+institutions?|asset\s+reconstruction\s+compan(?:y|ies)|"
    r"credit\s+information\s+compan(?:y|ies))\b")
#: Entity-class abbreviations, dropped as tokens.
CLASS_ABBREVIATIONS = frozenset(
    "ucb ucbs rrb rrbs sfb sfbs nbfc nbfcs aifi aifis arc arcs cic cics stcb stcbs dccb dccbs banks".split())


def _singular(tok: str) -> str:
    return tok[:-1] if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss") else tok


def normalise_title(raw: str, *, drop_year: bool = False) -> str:
    """Full-title comparison key: the candidates normaliser, no "(Updated as on ...)", one dash form, no quotes."""
    text = _UPDATED.sub(" ", raw)
    text = re.sub(r"[‘’“”\"']", "", text)
    text = _DASHES.sub(" - ", text)
    if drop_year:
        text = _YEAR.sub(" ", text)
    text = normalise_sentence(text)
    return " ".join(text.replace("( ", "(").replace(" )", ")").split())


def subject_of(title: str, entity_class: str | None = None) -> str:
    """What a Direction or citation is about, without the RBI wrapper, the class and the year.

    ``Reserve Bank of India (Commercial Banks – Know Your Customer) Directions, 2025 (Updated ...)``
    -> ``Know Your Customer``; ``Master Direction – Liberalised Remittance Scheme (LRS)`` ->
    ``Liberalised Remittance Scheme (LRS)``.
    """
    text = _UPDATED.sub(" ", title)
    m = re.search(r"Reserve\s+Bank\s+of\s+India\s*\((?P<inner>(?:[^()]|\([^()]*\))+)\)", text, re.IGNORECASE)
    if m:
        text = m.group("inner")
    text = re.sub(r"^\s*Master\s+Directions?\s*[-–—:]?\s*", "", text, flags=re.IGNORECASE)
    if entity_class:
        text = re.sub(rf"^\s*{re.escape(entity_class)}\s*[-–—:]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bDirections?\s*,?\s*(?:19|20)\d{2}\b", " ", text, flags=re.IGNORECASE)
    return clean_text(_YEAR.sub(" ", text)).strip(" -–—,")


def subject_tokens(text: str) -> frozenset[str]:
    lowered = _CLASS_PHRASES.sub(" ", re.sub(r"co-\s?operative", "cooperative", text.lower()))
    words = re.findall(r"[a-z0-9]+", lowered)
    return frozenset(_singular(w) for w in words
                     if w not in TITLE_STOPWORDS and w not in CLASS_ABBREVIATIONS and not w.isdigit() and len(w) > 1)


def dice(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def refs_in(text: str) -> list[str]:
    return [normalise_ref(m.group(0)) for m in CIRCULAR_REF.finditer(text)]


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


@dataclass
class DirectionEntry:
    md_id: str
    title: str
    entity_class: str | None
    subject: str
    tokens: frozenset[str]
    title_key: str
    title_key_no_year: str


@dataclass
class LinkIndex:
    directions: dict[str, DirectionEntry]
    by_ref: dict[str, set[str]]
    by_title: dict[str, set[str]]
    by_title_no_year: dict[str, set[str]]
    repeal_by_ref: dict[str, set[str]]
    repeal_by_title: dict[str, set[str]]
    repeal_by_subject: dict[str, set[tuple[str, str]]]
    core_classes: frozenset[str]
    tie_order: dict[str, int]
    threshold: float
    empty_title: list[str] = field(default_factory=list)

    @classmethod
    def build(cls, manifest: Sequence[Mapping[str, Any]], paragraphs_by_doc: Mapping[str, Sequence[Mapping[str, Any]]],
              repeal: Mapping[str, Any], *, linking: Mapping[str, Any], core_classes: Iterable[str]) -> "LinkIndex":
        directions, by_ref, by_title, by_title_ny, empty = {}, {}, {}, {}, []
        scan = int(linking.get("ref_scan_paragraphs", 6))
        for row in manifest:
            md, title = row["document_id"], row.get("title") or ""
            if not title.strip():
                empty.append(md)
            subj = subject_of(title, row.get("entity_class_raw"))
            entry = DirectionEntry(md, title, row.get("entity_class_raw"), subj, subject_tokens(subj),
                                   normalise_title(title), normalise_title(title, drop_year=True))
            directions[md] = entry
            if entry.title_key:
                by_title.setdefault(entry.title_key, set()).add(md)
                by_title_ny.setdefault(entry.title_key_no_year, set()).add(md)
            # The Direction's own reference numbers: the first paragraph (within `scan`) that carries any.
            # Later paragraphs cite other circulars (annex lists, "please refer to ...").
            own = next((refs for para in list(paragraphs_by_doc.get(md, []))[:scan]
                        if (refs := refs_in(para["text"]))), [])
            for ref in own:
                by_ref.setdefault(ref, set()).add(md)
        rep_ref, rep_title, rep_subject = {}, {}, {}
        for e in repeal.get("annex_entries", []):
            for r in e["refs"]:
                rep_ref.setdefault(normalise_ref(r), set()).add(e["md_id"])
            if e.get("title"):
                rep_title.setdefault(normalise_title(e["title"]), set()).add(e["md_id"])
        for e in repeal.get("repeal_statements", []):
            key = " ".join(sorted(subject_tokens(e["subject"])))
            if key:
                rep_subject.setdefault(key, set()).add((e["md_id"], e["applicable_to"]))
        order = {c: i for i, c in enumerate(linking.get("tie_break_class_order", []))}
        return cls(directions, by_ref, by_title, by_title_ny, rep_ref, rep_title, rep_subject, frozenset(core_classes),
                   order, float(linking["fuzzy_threshold"]), sorted(empty))

    # -- helpers ---------------------------------------------------------------
    def _rank(self, md_ids: Iterable[str]) -> list[str]:
        big = len(self.tie_order)
        return sorted(md_ids, key=lambda m: (self.tie_order.get(self.directions[m].entity_class or "", big), m))

    def scope(self, entity_class: str | None) -> list[str]:
        """Fuzzy candidates: the item's core class plus function-heading Directions, or everything."""
        if not entity_class or entity_class == UNRESOLVED:
            return sorted(self.directions)
        if entity_class in self.core_classes:
            return sorted(m for m, d in self.directions.items()
                          if d.entity_class == entity_class or d.entity_class not in self.core_classes)
        return sorted(m for m, d in self.directions.items() if d.entity_class == entity_class) or sorted(self.directions)

    def _pick(self, md_ids: set[str], entity_class: str | None, score: float, method: str,
              basis: str) -> dict | None:
        """The best of ``md_ids`` within the item's scope; ``None`` when none is in scope.

        A resolved entity class never falls back to another class's Direction:
        a UCB release is not linked to the Commercial Banks Direction.
        """
        allowed = set(self.scope(entity_class))
        pool = [m for m in md_ids if m in allowed]
        if not pool:
            return None
        ranked = self._rank(pool)
        return {"md_id": ranked[0], "method": method, "score": score,
                "second_best_md_id": ranked[1] if len(ranked) > 1 else None,
                "margin": 0.0 if len(ranked) > 1 else None, "basis": basis, "tied_best": len(ranked)}

    # -- methods ---------------------------------------------------------------
    def exact(self, cited: str, href: str | None, entity_class: str | None) -> dict | None:
        if href:
            m = _MD_LINK.search(href)
            if m and f"md_{m.group(1)}" in self.directions:  # an explicit pointer: no class scope applies
                return self._pick({f"md_{m.group(1)}"}, None, 1.0, METHOD_EXACT, "md_hyperlink")
        hits: set[str] = set()
        for ref in refs_in(cited):
            hits |= self.by_ref.get(ref, set())
        if hits and (picked := self._pick(hits, entity_class, 1.0, METHOD_EXACT, "reference_number")):
            return picked
        for key, table, basis in ((normalise_title(cited), self.by_title, "title"),
                                  (normalise_title(cited, drop_year=True), self.by_title_no_year, "title_no_year")):
            if key and key in table and (picked := self._pick(table[key], entity_class, 1.0, METHOD_EXACT, basis)):
                return picked
        return None

    def repeal(self, cited: str, entity_class: str | None) -> dict | None:
        hits: set[str] = set()
        for ref in refs_in(cited):
            hits |= self.repeal_by_ref.get(ref, set())
        if hits and (picked := self._pick(hits, entity_class, 1.0, METHOD_REPEAL, "annex_reference")):
            return picked
        key = normalise_title(cited)
        if key in self.repeal_by_title and (picked := self._pick(self.repeal_by_title[key], entity_class, 1.0,
                                                                  METHOD_REPEAL, "annex_title")):
            return picked
        skey = " ".join(sorted(subject_tokens(subject_of(cited))))
        if skey and skey in self.repeal_by_subject:
            return self._pick({m for m, _ in self.repeal_by_subject[skey]}, entity_class, 1.0, METHOD_REPEAL,
                              "repeal_statement")
        return None

    def fuzzy(self, cited: str, entity_class: str | None) -> dict:
        toks = subject_tokens(subject_of(cited))
        scored = sorted(((dice(toks, self.directions[m].tokens), m) for m in self.scope(entity_class)),
                        key=lambda x: -x[0])
        if not scored or scored[0][0] <= 0:
            return {"md_id": None, "method": METHOD_NONE, "score": None, "second_best_md_id": None, "margin": None,
                    "basis": "no_token_overlap", "tied_best": 0}
        best = scored[0][0]
        tied = self._rank([m for s, m in scored if s == best])
        rest = [(s, m) for s, m in scored if m != tied[0]]
        second = rest[0] if rest else (None, None)
        link = {"md_id": tied[0], "score": round(best, 6), "second_best_md_id": second[1],
                "margin": round(best - second[0], 6) if second[0] is not None else None,
                "tied_best": len(tied)}
        if best >= self.threshold:
            return {**link, "method": METHOD_FUZZY, "basis": "subject_dice"}
        # Below threshold: no link, but the best candidate and margin stay visible for the report.
        return {**link, "md_id": None, "method": METHOD_NONE, "basis": f"best_below_threshold:{tied[0]}"}

    def link_one(self, item_id: str, cited: str | None, *, href: str | None = None, entity_class: str | None = None,
                 scope: str = "item") -> dict[str, Any]:
        if not cited and not href:
            result = {"md_id": None, "method": METHOD_NONE, "score": None, "second_best_md_id": None,
                      "margin": None, "basis": "nothing_cited", "tied_best": 0}
        else:
            text = cited or ""
            result = (self.exact(text, href, entity_class) or self.repeal(text, entity_class)
                      or self.fuzzy(text, entity_class))
        return {"item_id": item_id, "cited_string": cited, "md_id": result["md_id"], "method": result["method"],
                "score": result["score"], "second_best_md_id": result["second_best_md_id"],
                "margin": result["margin"], "cited_scope": scope, "basis": result["basis"],
                "tied_best": result["tied_best"]}


# ---------------------------------------------------------------------------
# Items -> link records
# ---------------------------------------------------------------------------

METHOD_RANK = {m: i for i, m in enumerate(METHODS)}


def _faq_citations(item: Mapping[str, Any]) -> list[tuple[str | None, str | None, str]]:
    """(cited string, href, scope) for an FAQ item: its own links first, else the topic's."""
    f = item["fields"]
    out = [(c, None, "item") for c in item["cited_directions"]]
    out += [(None, f"BS_ViewMasDirections.aspx?id={m.split('_')[1]}", "item") for m in f.get("linked_md_ids", [])]
    if not out:
        out += [(c, None, "topic") for c in f.get("topic_cited_directions", [])]
        out += [(None, f"BS_ViewMasDirections.aspx?id={m.split('_')[1]}", "topic")
                for m in f.get("topic_linked_md_ids", [])]
    return out


def citations(item: Mapping[str, Any]) -> list[tuple[str | None, str | None, str]]:
    source = item["source"]
    if source == "faq":
        return _faq_citations(item)
    out = [(c, None, "item") for c in item["cited_directions"]]
    if source == "amendment":
        out += [(None, f"BS_ViewMasDirections.aspx?id={m.split('_')[1]}", "item")
                for m in item["fields"].get("linked_md_ids", [])]
    return out


def link_items(index: LinkIndex, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One record per (item, citation); an item with nothing cited gets one ``none`` record.

    Local repeal entries already know their repealing Direction; they are
    recorded as ``repeal_map`` by construction.
    """
    records = []
    for item in items:
        f = item["fields"]
        if item["source"] == "withdrawn" and f.get("repealing_md_id"):
            records.append({"item_id": item["item_id"], "cited_string": item["title"], "md_id": f["repealing_md_id"],
                            "method": METHOD_REPEAL, "score": 1.0, "second_best_md_id": None, "margin": None,
                            "cited_scope": "item", "basis": f"local:{f['origin']}", "tied_best": 1})
            continue
        cites = [c for c in citations(item) if (c[0] and len(c[0].strip()) >= 3) or c[1]]
        seen = set()
        for cited, href, scope in cites:
            if (cited, href) in seen:
                continue
            seen.add((cited, href))
            records.append(index.link_one(item["item_id"], cited, href=href, entity_class=item["entity_class"],
                                          scope=scope))
        if not cites:
            records.append(index.link_one(item["item_id"], None, entity_class=item["entity_class"]))
    return records


def best_link(records: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """An item's best link: item scope before topic scope, then method order, then score, then citation order.

    Citation order is deterministic: an FAQ topic's links come most frequent first.
    """
    linked = [(i, r) for i, r in enumerate(records) if r["md_id"]]
    if not linked:
        return None
    return min(linked, key=lambda x: (x[1]["cited_scope"] != "item", METHOD_RANK[x[1]["method"]],
                                      -(x[1]["score"] or 0), x[0]))[1]


def coverage(items: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per source: items linked by their best method, and the fuzzy margin distribution."""
    by_item: dict[str, list[Mapping[str, Any]]] = {}
    for r in records:
        by_item.setdefault(r["item_id"], []).append(r)
    out: dict[str, Any] = {}
    for item in items:
        src = item["source"] if item["source"] != "withdrawn" else f"withdrawn:{item['fields'].get('origin')}"
        row = out.setdefault(src, {"items": 0, **{m: 0 for m in METHODS}, "fuzzy_margins": []})
        row["items"] += 1
        best = best_link(by_item.get(item["item_id"], []))
        row[best["method"] if best else METHOD_NONE] += 1
        if best and best["method"] == METHOD_FUZZY and best["margin"] is not None:
            row["fuzzy_margins"].append(best["margin"])
    for row in out.values():
        margins = sorted(row.pop("fuzzy_margins"))
        n = len(margins)
        row["fuzzy_margin"] = {"n": n, "min": margins[0] if n else None, "median": margins[n // 2] if n else None,
                               "max": margins[-1] if n else None, "zero_margin": sum(m == 0 for m in margins)}
        row["linked"] = row["items"] - row[METHOD_NONE]
        row["link_rate"] = round(row["linked"] / row["items"], 4) if row["items"] else None
    return dict(sorted(out.items()))
