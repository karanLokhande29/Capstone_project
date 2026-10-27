"""Rule-based extraction of deadlines and frequencies, and the compliance calendar (.ics).

Patterns (rules v1): "within N (working) days/weeks/months [of/from the end of each month/quarter/half-year/year]",
frequencies (monthly, quarterly, half-yearly, annually, fortnightly, weekly, daily), "by / on or before / not later
than <date>", "by the end of <month>". A submission verb or a return/report noun raises the confidence; an
event-triggered deadline ("within 30 days of the change") cannot be placed on a calendar and is listed only.
"""

from __future__ import annotations

import calendar as _cal
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from src.auditgen.corpus import excerpt

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
             "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "twenty one": 21, "thirty": 30, "forty five": 45,
             "sixty": 60, "ninety": 90}
MONTHS = {m.lower(): i for i, m in enumerate(_cal.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(_cal.month_abbr) if m})
FREQ_WORDS = [("half-yearly", r"half[- ]?yearly|semi[- ]?annual(?:ly)?|six[- ]monthly|every six months"),
              ("quarterly", r"quarterly|every quarter|each quarter"),
              ("monthly", r"monthly|every month|each month"),
              ("annually", r"annual(?:ly)?|yearly|every year|each year|once a year"),
              ("fortnightly", r"fortnightly|every fortnight"),
              ("weekly", r"weekly|every week"),
              ("daily", r"\bdaily\b|every day")]
PERIOD_END = {"month": "monthly", "quarter": "quarterly", "half year": "half-yearly", "year": "annually",
              "financial year": "annually"}
_NUM = r"(?P<n>\d{1,3}|" + "|".join(sorted(NUM_WORDS, key=len, reverse=True)) + r")"
WITHIN = re.compile(_NUM + r"\s*(?:\(\d+\)\s*)?(?P<unit>working days|business days|days|weeks|months)", re.I)
WITHIN_LEAD = re.compile(r"(?:within|not later than|no later than|before the expiry of)\s+(?:a period of\s+)?$", re.I)
END_OF = re.compile(r"(?:of|from|after)\s+the\s+(?:close|end)\s+of\s+(?:the|each|every)?\s*(?:relevant\s+)?"
                    r"(?P<p>financial year|half[- ]year|quarter|month|year)", re.I)
BY_DATE = re.compile(r"(?:by|on or before|not later than|no later than|before)\s+(?:the\s+)?(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+"
                     r"(?:of\s+)?(?P<m>[A-Za-z]{3,9})(?:,?\s+(?P<y>\d{4}))?"
                     r"|(?:by|on or before|not later than|no later than|before)\s+(?P<m2>[A-Za-z]{3,9})\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?"
                     r"(?:,?\s+(?P<y2>\d{4}))?", re.I)
END_OF_MONTH = re.compile(r"by\s+the\s+end\s+of\s+(?P<m>[A-Za-z]{3,9})\b", re.I)
SUBMIT = re.compile(r"\b(submit|submitted|furnish|furnished|report|reported|file|filed|return|returns|statement|"
                    r"certificate|send|sent|forward|publish|disclose|place before the board|review)\b", re.I)
FREQ_RE = [(name, re.compile(rf"\b(?:{pat})\b", re.I)) for name, pat in FREQ_WORDS]


def _num(s: str) -> int | None:
    s = s.lower().strip()
    return int(s) if s.isdigit() else NUM_WORDS.get(s)


def extract(text: str) -> list[dict[str, Any]]:
    """Deadline/frequency mentions in one obligation text, each with a confidence and the matched phrase."""
    t = " ".join((text or "").split())
    out: list[dict[str, Any]] = []
    has_submit = bool(SUBMIT.search(t))
    for m in WITHIN.finditer(t):
        lead = t[max(0, m.start() - 40):m.start()]
        if not WITHIN_LEAD.search(lead):
            continue
        n, unit = _num(m["n"]), m["unit"].lower()
        if not n or n > 400:
            continue
        days = n * (7 if unit == "weeks" else 30 if unit == "months" else 1)
        tail = t[m.end():m.end() + 80]
        pe = END_OF.match(tail.lstrip()) or END_OF.search(tail[:60])
        phrase = t[max(0, m.start() - 12):min(len(t), m.end() + (pe.end() if pe else 30))]
        if pe:
            freq = PERIOD_END[" ".join(pe["p"].lower().replace("-", " ").split())]
            out.append({"kind": "recurring", "frequency": freq, "offset_days": days, "working_days": "working" in unit or "business" in unit,
                        "phrase": excerpt(phrase, 25), "confidence": 0.85 if has_submit else 0.7})
        else:
            out.append({"kind": "event", "frequency": None, "offset_days": days, "working_days": "working" in unit or "business" in unit,
                        "phrase": excerpt(phrase, 25), "confidence": 0.6 if has_submit else 0.45})
    for m in BY_DATE.finditer(t):
        d, mon, y = (m["d"], m["m"], m["y"]) if m["d"] else (m["d2"], m["m2"], m["y2"])
        mi = MONTHS.get((mon or "").lower())
        if not mi or not d or not (1 <= int(d) <= 31):
            continue
        out.append({"kind": "fixed", "frequency": None if y else "annually", "month": mi, "day": int(d), "year": int(y) if y else None,
                    "phrase": excerpt(t[max(0, m.start() - 12):m.end() + 20], 25), "confidence": 0.8 if has_submit else 0.6})
    for m in END_OF_MONTH.finditer(t):
        mi = MONTHS.get(m["m"].lower())
        if mi:
            out.append({"kind": "fixed", "frequency": "annually", "month": mi, "day": _cal.monthrange(2026, mi)[1], "year": None,
                        "phrase": excerpt(t[max(0, m.start() - 12):m.end() + 20], 25), "confidence": 0.7 if has_submit else 0.55})
    if not any(e["kind"] in ("recurring", "fixed") for e in out):
        for name, rx in FREQ_RE:
            m = rx.search(t)
            if m:
                out.append({"kind": "recurring", "frequency": name, "offset_days": 0, "working_days": False,
                            "phrase": excerpt(t[max(0, m.start() - 60):m.end() + 40], 25),
                            "confidence": 0.65 if has_submit else 0.4})
                break
    return out


def summary(entries: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for e in entries:
        if e["kind"] == "recurring":
            parts.append(e["frequency"] + (f" (+{e['offset_days']} days)" if e.get("offset_days") else ""))
        elif e["kind"] == "fixed":
            parts.append(f"by {e['day']} {_cal.month_abbr[e['month']]}" + (f" {e['year']}" if e.get("year") else " (yearly)"))
        else:
            parts.append(f"within {e['offset_days']} days of an event")
    return "; ".join(dict.fromkeys(parts))


# -- occurrences ---------------------------------------------------------------------------------------

def _period_ends(freq: str, start: date, end: date, fy_end: tuple[int, int]) -> Iterable[date]:
    months = {"monthly": list(range(1, 13)), "quarterly": [3, 6, 9, 12], "half-yearly": [3, 9],
              "annually": [fy_end[0]]}.get(freq)
    if months:
        y = start.year - 1
        while y <= end.year:
            for mo in months:
                d = date(y, mo, _cal.monthrange(y, mo)[1])
                yield d
            y += 1
    elif freq in ("weekly", "fortnightly", "daily"):
        step = {"weekly": 7, "fortnightly": 14, "daily": 1}[freq]
        d = start
        while d <= end:
            yield d
            d += timedelta(days=step)


def occurrences(entry: Mapping[str, Any], start: date, end: date, fy_end: str = "03-31") -> list[date]:
    """Due dates of one entry inside [start, end] (event-triggered entries have none)."""
    fm, fd = (int(x) for x in fy_end.split("-"))
    out: list[date] = []
    if entry["kind"] == "recurring":
        if entry["frequency"] == "daily":
            return []  # a daily duty is listed, not drawn 365 times
        for pe in _period_ends(entry["frequency"], start, end, (fm, fd)):
            due = pe + timedelta(days=int(entry.get("offset_days") or 0))
            if start <= due <= end:
                out.append(due)
    elif entry["kind"] == "fixed":
        years = [entry["year"]] if entry.get("year") else range(start.year, end.year + 1)
        for y in years:
            try:
                due = date(int(y), entry["month"], min(entry["day"], _cal.monthrange(int(y), entry["month"])[1]))
            except ValueError:
                continue
            if start <= due <= end:
                out.append(due)
    return sorted(set(out))


def _ics_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(entries: Sequence[Mapping[str, Any]], *, prodid: str, start: date, end: date, fy_end: str) -> str:
    """RFC 5545 calendar: one all-day VEVENT per due date in [start, end]."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{prodid}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for e in entries:
        for due in occurrences(e, start, end, fy_end):
            uid = f"{e['entry_id']}-{due.isoformat()}@auditgen.local"
            desc = (f"{e['phrase']}\nSource: {e['direction_title']} ({e['paragraph_id']})\n{e['source_url']}\n"
                    f"Confidence {e['confidence']:.2f}{' (verify)' if e.get('verify') else ''}. "
                    "Decision support only; verify against the official RBI text; not legal advice.")
            lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}",
                      f"DTEND;VALUE=DATE:{(due + timedelta(days=1)).strftime('%Y%m%d')}",
                      f"SUMMARY:{_ics_escape(('[verify] ' if e.get('verify') else '') + e['summary'][:120])}",
                      f"DESCRIPTION:{_ics_escape(desc)}", f"URL:{e['source_url']}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    folded = []
    for ln in lines:
        while len(ln.encode()) > 74:
            cut = 74
            while len(ln[:cut].encode()) > 74:
                cut -= 1
            folded.append(ln[:cut])
            ln = " " + ln[cut:]
        folded.append(ln)
    return "\r\n".join(folded) + "\r\n"
