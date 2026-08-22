""""(Updated as on ...)" stamp extraction.

RBI Master Directions carry their last-updated date, when one exists, as a
literal stamp in the title or body text — e.g. "Master Direction – Operational
Guidelines for Primary Dealers (Updated as on November 22, 2018)". This module
extracts exactly that stamp, verbatim as a string, per Task 6 of the governing
prompt: nothing here parses it into a date object, resolves supersession, or
reaches for any source beyond the primary Master Direction's own text.
Supersession logic is out of scope until Phase 4.

Deliberately narrow: the listing page also groups documents under a per-block
date sub-heading (e.g. "Jul 01, 2016"), which is not used here. Comparing that
heading against in-text "Updated as on" stamps in sample data shows the heading
is consistently the same as or older than the stamp, i.e. it is an issuance
date, not an update date — using it as a fallback for `update_date` would
misrepresent one for the other, so it is left alone.
"""

from __future__ import annotations

import re

#: Matches "(Updated as on <Month DD, YYYY>)" allowing for the minor spacing and
#: comma variations actually observed on the site (e.g. missing comma before
#: the year, or an ordinal form is deliberately NOT matched — RBI text is
#: consistent enough that guessing at ordinal variants would risk a false
#: match instead of catching a real one).
UPDATED_AS_ON_RE = re.compile(
    r"\(\s*Updated\s+as\s+on\s+"
    r"([A-Za-z]+\s+\d{1,2},?\s*\d{4})"
    r"\s*\)",
    re.IGNORECASE,
)


def extract_update_date_stamp(text: str | None) -> str | None:
    """Return the verbatim "Updated as on ..." date from `text`, if present.

    Searches the whole string and returns the *last* match — a document whose
    title and body both carry a stamp almost always has the more current one
    in the body, appended or corrected after the title was first set, and
    scanning to the end costs nothing on text this short.

    Returns the date exactly as printed (e.g. ``"November 22, 2018"``), not
    parsed into a structured date. Returns ``None`` when no stamp is present,
    which is the common case — most Directions have never been amended.
    """
    if not text:
        return None
    matches = UPDATED_AS_ON_RE.findall(text)
    if not matches:
        return None
    return matches[-1].strip()
