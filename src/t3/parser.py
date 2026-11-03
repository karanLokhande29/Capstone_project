"""Deterministic parser for P2-003 Amendment Directions (P4-001 task 1).

Precision over recall: an instruction becomes a parsed action only when it
matches one of a few explicit templates. Everything else is counted as
``unparsed`` and never used. The same parser feeds the T3 gold and the
pipeline's temporal filter, so T3 measures whether the *LLM pipeline* uses
the date information, not whether the rules are right (circularity, stated in
the report).

Templates, tried on the instruction text before ``shall be <verb>`` (quoted new
text masked out, the enclosing enumerated item as the scope):

* ``paragraph_whole``: "(The) paragraph(s) <paths> (of ...) shall be substituted /
  deleted / omitted", or "For paragraph <path> (...), the following shall be
  substituted". The whole paragraph is replaced or removed.
* ``within_paragraph``: "In paragraph <path> (...), the words / word / phrase /
  sentence / proviso / explanation ... shall be substituted / deleted /
  inserted / added". The paragraph stays and is amended.
* ``new_paragraph``: "(After paragraph <path>,) (a new) paragraph(s) <newpath>
  shall be inserted". A new paragraph; no existing paragraph changes status.

Relative references ("a) Sub-para (1) shall be ..."), chapters, sections,
annexes, forms and footnotes are ``unparsed``.

Effective date, per amendment, from its commencement sentence:
immediate / date of issue -> the published date; "on|from <date>" -> that date;
"... whichever is earlier" -> a window [published date, date] (status unknown
inside it); anything else, or several different dates -> unclear.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

from src.benchmark.t1 import _PATH, _expand_list

ACTION_OF = {"substituted": "substitute", "deleted": "delete", "omitted": "delete", "inserted": "insert",
             "added": "insert"}
VERB_RE = re.compile(r"shall\s+be\s+(substituted|deleted|omitted|inserted|added)\b", re.I)
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_RE = re.compile(rf"\b({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
_ENUM_RE = re.compile(r"(?:^|\n|\s)(?:\d+\(\d+\)(?:\([ivxlc]+\))?|\((?:\d+|[ivxlc]+|[a-z])\)|[ivxlc]+[.)]|[a-z]\))\s",
                      re.I)
_PATHS = rf"{_PATH}(?:\s*(?:,|and|to|through|-|–)\s*{_PATH})*"
_OF = r"(?:\s+of\s+[^,;:]{0,90}?)?"
WHOLE_RE = re.compile(rf"^(?:the\s+)?(?:existing\s+)?(?:sub-?)?paragraphs?\s+(?P<paths>{_PATHS}){_OF},?\s*$", re.I)
FOR_RE = re.compile(rf"^for\s+(?:sub-?)?paragraphs?\s+(?P<paths>{_PATHS}){_OF},?\s*the\s+following\s*$", re.I)
WITHIN_RE = re.compile(
    rf"^in\s+(?:sub-?)?paragraphs?\s+(?P<paths>{_PATH}){_OF},\s*(?:the|a|an)\s+"
    r"(?:words?|phrase|sentence|expression|proviso|explanation|figures?|footnote)\b", re.I)
NEW_RE = re.compile(
    rf"^(?:after\s+(?:sub-?)?paragraph\s+(?P<after>{_PATH}){_OF},\s*)?(?:a\s+)?(?:new\s+)?(?:sub-?)?paragraphs?\s+"
    rf"(?P<paths>{_PATHS})(?:\s+(?:and\s+)?{_PATH})*\s*$", re.I)
COMMENCE_RE = re.compile(r"(?:come|came)\s+into\s+(?:force|effect)[^.]{0,500}", re.I)
#: v2: a date that names another instrument ("... Directions dated March 30, 2026") is not a commencement date.
DATED_RE = re.compile(rf"\bdated\s+(?:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}}", re.I)
EXCEPT_RE = re.compile(r"\bexcept\s+(?:sub-?)?paragraphs?\s+(\d+)((?:\s*\(\s*[0-9a-z]+\s*\))*)", re.I)
TOP_RE = re.compile(r"(?m)^\s*(\d+)\.\s")
ROMAN_RE = re.compile(r"(?m)^\s*\(([ivxlc]+)\)\s", re.I)
RULES_VERSION = "v2"
IMMEDIATE_RE = re.compile(r"immediate(?:ly)?|date\s+of\s+(?:issue|issuance|this)", re.I)


@dataclass
class Action:
    action_id: str
    item_id: str
    md_id: str | None
    action: str  # substitute | delete | insert
    scope: str  # paragraph_whole | within_paragraph | new_paragraph
    targets: list[str]
    instruction: str
    new_text: str | None = None
    old_words: list[str] = field(default_factory=list)
    new_words: list[str] = field(default_factory=list)
    #: v2: offset of the instruction's enumerated item in the amendment text (for per-item commencement dates)
    start: int | None = None
    #: v2: every change a within-paragraph instruction makes, in order: {"verb", "old", "new"}
    changes: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def norm_path(raw: str) -> str:
    return re.sub(r"\s+", "", raw).lower()


def quoted_regions(text: str) -> list[tuple[int, int]]:
    """Top-level “…” regions (curly double quotes, which the notifications use for new text)."""
    regs, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "“":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "”" and depth:
            depth -= 1
            if depth == 0:
                regs.append((start, i + 1))
    return regs


def _mask(text: str, regions: Sequence[tuple[int, int]]) -> str:
    chars = list(text)
    for a, b in regions:
        for i in range(a, b):
            if chars[i] != "\n":
                chars[i] = "\x00"
    return "".join(chars)


def _instruction_start(masked: str, pos: int) -> int:
    """Start of the enumerated item holding ``pos``: the last enumerator, else the last sentence break."""
    window = masked[:pos]
    starts = [m.end() for m in _ENUM_RE.finditer(window)]
    sent = max(window.rfind(". "), window.rfind(".\n"), window.rfind(":\n"))
    cand = [s for s in starts] + ([sent + 2] if sent >= 0 else [])
    return max(cand) if cand else 0


def _quote_after(text: str, regions: Sequence[tuple[int, int]], pos: int, within: int = 200) -> str | None:
    for a, b in regions:
        if pos <= a <= pos + within:
            return text[a + 1:b - 1].strip()
    return None


_SQ = r"[‘'\"“]([^’'\"”]{1,300})[’'\"”]"


def norm_title(t: str) -> str:
    t = re.sub(r"\(\s*updated\s+as\s+on[^)]*\)", "", (t or "").lower())
    t = t.replace("–", "-").replace("—", "-")
    t = re.sub(r",?\s*\d{4}\s*$", "", t.strip())
    return " ".join(t.split())


def target_direction(item: Mapping[str, Any], titles: Mapping[str, str] | None = None) -> str | None:
    """The one Direction an amendment modifies: its only linked md_id, or, when several are linked, the one
    whose normalised title equals the amendment's title-derived target (exact match only)."""
    f = item.get("fields") or {}
    linked = list(f.get("linked_md_ids") or [])
    if len(linked) == 1:
        return linked[0]
    target = norm_title(f.get("title_derived_target") or "")
    if not target or not titles:
        return None
    hits = [m for m in linked if m in titles and norm_title(titles[m]) == target]
    return hits[0] if len(hits) == 1 else None


def parse_amendment(item: Mapping[str, Any], titles: Mapping[str, str] | None = None) -> tuple[list[Action], dict[str, int]]:
    """Every parsed action of one amendment, plus counts of what was not parsed."""
    text = item.get("text") or ""
    regions = quoted_regions(text)
    masked = _mask(text, regions)
    md = target_direction(item, titles)
    actions: list[Action] = []
    counts = {"verbs": 0, "parsed": 0, "unparsed": 0, "merged_into_previous": 0}
    prev_start, prev_end = -1, 0
    for n, m in enumerate(VERB_RE.finditer(masked)):
        counts["verbs"] += 1
        start = _instruction_start(masked, m.start())
        # v2: a verb whose clause carries no paragraph of its own ("..., the word 'seven' shall be substituted
        # with 'five'") continues the within-paragraph change of the same enumerated item.
        if prev_start == start and actions and actions[-1].scope == "within_paragraph" and actions[-1].start == start:
            head_here = " ".join(masked[prev_end:m.start()].replace("\x00", " ").split())
            if not re.search(r"paragraph|annex|form|chapter|section|appendix|footnote", head_here, re.I):
                last = actions[-1]
                act = ACTION_OF[m.group(1).lower()]
                before = " ".join(text[prev_end:m.start()].split())
                seg = text[m.end():m.end() + 300]
                nxt = VERB_RE.search(masked, m.end())
                if nxt and nxt.start() < m.end() + 300:
                    seg = text[m.end():nxt.start()]
                olds = re.findall(_SQ, before) if act != "insert" else []
                news = re.findall(_SQ, " ".join(seg.split()))[:1] if act == "substitute" else (
                    (re.findall(_SQ, before) + re.findall(_SQ, " ".join(seg.split())))[:1] if act == "insert" else [])
                last.changes.append({"verb": act, "old": olds, "new": news})
                last.old_words += olds
                last.new_words += news
                if "substitute" in {c["verb"] for c in last.changes}:
                    last.action = "substitute"
                last.instruction = " ".join(text[start:m.end()].split())
                counts["merged_into_previous"] += 1
                prev_end = m.end()
                continue
        head = " ".join(masked[start:m.start()].replace("\x00", " ").split()).strip(" ,;-–")
        verb = m.group(1).lower()
        action = ACTION_OF[verb]
        instr = " ".join(text[start:m.end()].split())
        parsed: Action | None = None
        whole = WHOLE_RE.match(head) or (FOR_RE.match(head) if action == "substitute" else None)
        if whole and action in ("substitute", "delete"):
            new = _quote_after(text, regions, m.end()) if action == "substitute" else None
            parsed = Action(f"{item['item_id']}#a{n:02d}", item["item_id"], md, action, "paragraph_whole",
                            [norm_path(p) for p in _expand_list(whole["paths"])], instr, new_text=new, start=start)
        elif (w := WITHIN_RE.match(head)):
            # v2: the quoted words of THIS change only (between the previous verb of the same item and this one)
            seg_from = prev_end if prev_start == start else start
            before = " ".join(text[seg_from:m.start()].split())
            after = text[m.end():m.end() + 300]
            nxt = VERB_RE.search(masked, m.end())
            if nxt and nxt.start() < m.end() + 300:
                after = text[m.end():nxt.start()]
            olds = re.findall(_SQ, before) if action != "insert" else []
            news = re.findall(_SQ, " ".join(after.split()))[:1] if action == "substitute" else []
            if action == "insert":
                news = (re.findall(_SQ, before) + re.findall(_SQ, " ".join(after.split())))[:1]
            parsed = Action(f"{item['item_id']}#a{n:02d}", item["item_id"], md, action, "within_paragraph",
                            [norm_path(w["paths"])], instr, old_words=olds, new_words=news, start=start,
                            changes=[{"verb": action, "old": olds, "new": news}])
        elif action == "insert" and (nw := NEW_RE.match(head)):
            parsed = Action(f"{item['item_id']}#a{n:02d}", item["item_id"], md, action, "new_paragraph",
                            [norm_path(p) for p in _expand_list(nw["paths"])], instr,
                            new_text=_quote_after(text, regions, m.end()), start=start)
        if parsed is not None and parsed.targets:
            actions.append(parsed)
            counts["parsed"] += 1
        else:
            counts["unparsed"] += 1
        prev_start, prev_end = start, m.end()
    return actions, counts


def _date(m: re.Match) -> str:
    return _dt.datetime.strptime(f"{m.group(1).title()} {int(m.group(2))} {m.group(3)}", "%B %d %Y").date().isoformat()


def item_path(text: str, pos: int) -> tuple[str | None, str | None]:
    """(top-level paragraph number, roman item) of the amendment's own enumeration at ``pos`` (quoted text masked)."""
    masked = _mask(text, quoted_regions(text))
    tops = [m for m in TOP_RE.finditer(masked[:pos + 1])]
    top = tops[-1] if tops else None
    romans = [m for m in ROMAN_RE.finditer(masked[:pos + 8]) if not top or m.start() >= top.start()]
    return (top.group(1) if top else None), (romans[-1].group(1).lower() if romans else None)


def effective_date(item: Mapping[str, Any], pos: int | None = None) -> dict[str, Any]:
    """``{"date", "window": [from, to] | None, "basis"}``; ``date`` None when unclear or windowed.

    v2: the full commencement sentence; "dated <date>" (another instrument's date) is ignored; an
    "except paragraph N (item) ..." date applies only to the instruction at ``pos`` when it sits under that
    item of the amendment's own enumeration (a deeper exception inside that item stays a window).
    """
    pub = item.get("published_date")
    text = item.get("text") or ""
    found = [DATED_RE.sub(" ", c.group(0)) for c in COMMENCE_RE.finditer(text)]
    if not found:
        return {"date": None, "window": None, "basis": "no_commencement_sentence", "sentence": None}
    dates = sorted({_date(d) for s in found for d in DATE_RE.finditer(s)})
    sentence = found[0][:300]
    exc = next((EXCEPT_RE.search(s) for s in found if EXCEPT_RE.search(s)), None)
    if exc and len(dates) == 2 and pos is not None:
        main_date = _date(DATE_RE.search(found[0][:exc.start()])) if DATE_RE.search(found[0][:exc.start()]) else None
        exc_date = _date(DATE_RE.search(found[0][exc.end():])) if DATE_RE.search(found[0][exc.end():]) else None
        parts = [p.strip().lower() for p in re.findall(r"\(\s*([0-9a-z]+)\s*\)", exc.group(2))]
        top, roman = item_path(text, pos)
        if main_date and exc_date and top:
            if top != exc.group(1) or (parts and roman and roman != parts[0]):
                return {"date": main_date, "window": None, "basis": "stated_date_outside_exception", "sentence": sentence}
            if not parts or (roman == parts[0] and len(parts) == 1):
                return {"date": exc_date, "window": None, "basis": "exception_date", "sentence": sentence}
    if any(re.search(r"whichever\s+is\s+earlier", s, re.I) for s in found):
        if len(dates) == 1 and pub:
            return {"date": None, "window": [pub, dates[0]], "basis": "earlier_of_date_or_adoption",
                    "sentence": sentence}
        return {"date": None, "window": None, "basis": "unclear", "sentence": sentence}
    if len(dates) >= 2 and any(re.search(r"\bexcept\b", s, re.I) for s in found):
        # "from D1, except <item>, which shall be effective from D2": the exception names the amendment's own
        # instruction numbering, which is not mapped to parsed actions, so status is unknown between the dates.
        return {"date": None, "window": [dates[0], dates[-1]], "basis": "except_clause_window", "sentence": sentence}
    immediate = any(IMMEDIATE_RE.search(s) for s in found)
    if immediate and not dates and pub:
        return {"date": pub, "window": None, "basis": "immediate_or_date_of_issue", "sentence": sentence}
    if len(dates) == 1 and not immediate:
        return {"date": dates[0], "window": None, "basis": "stated_date", "sentence": sentence}
    return {"date": None, "window": None, "basis": "unclear", "sentence": sentence}


# -- corpus-version check ----------------------------------------------------------------


def _collapse(s: str) -> str:
    return " ".join((s or "").lower().split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _collapse(a), _collapse(b), autojunk=False).ratio()


def segment_for(new_text: str, target: str, targets: Sequence[str]) -> str:
    """The part of a multi-paragraph substitution that belongs to ``target`` ("18. ..." up to "19. ...")."""
    if len(targets) == 1:
        return new_text
    m = re.search(rf"(?:^|\s){re.escape(target)}\.\s", new_text, re.I)
    if not m:
        return ""
    later = [re.search(rf"\s{re.escape(t)}\.\s", new_text[m.end():], re.I) for t in targets[targets.index(target) + 1:]]
    ends = [x.start() + m.end() for x in later if x]
    return new_text[m.start():min(ends) if ends else len(new_text)]


def corpus_version(action: Action, paragraph_text: str, target: str | None = None) -> str:
    """original | amended | unclear: does the corpus paragraph carry the old or the new text?"""
    t = _collapse(paragraph_text)
    target = target or action.targets[0]
    if action.scope == "paragraph_whole" and action.action == "substitute":
        seg = segment_for(action.new_text or "", target, action.targets)
        if not seg:
            return "unclear"
        new = _collapse(seg)
        body = re.sub(rf"^{re.escape(target)}\.?\s*", "", new)
        s = max(similarity(t, new), similarity(t, body))
        return "amended" if s >= 0.8 else "original" if s <= 0.5 else "unclear"
    if action.scope == "paragraph_whole" and action.action == "delete":
        return "amended" if re.fullmatch(r"[\d.()a-z\s]*(?:\[?\s*(?:deleted|omitted)\s*\]?)\.?", t) else "original"
    if action.scope == "within_paragraph":
        olds = [_collapse(x) for x in action.old_words]
        news = [_collapse(x) for x in action.new_words]
        has_old = bool(olds) and all(o in t for o in olds)
        has_new = bool(news) and all(x in t for x in news)
        if action.action == "substitute":
            return "amended" if has_new and not has_old else "original" if has_old and not has_new else "unclear"
        if action.action == "delete":
            return "original" if has_old else "unclear"
        if action.action == "insert":
            return "amended" if has_new else "original" if news else "unclear"
    return "unclear"
