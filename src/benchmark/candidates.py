"""Full-corpus deontic obligation-span candidate extraction (P2-001).

The successor to :mod:`src.benchmark.pilot` at corpus scale. Scans every
paragraph for deontic cues and proposes it as a T1 obligation candidate. It
**proposes only**: nothing here validates, labels, or asserts applicability.
Week 5 validates what this module emits.

Three design choices are load-bearing:

**One candidate per paragraph, every cue recorded.** The unit is the paragraph
(the unit obligations are anchored to, see
:class:`~src.schemas.provenance.ParagraphRecord`), not a sentence split. A
paragraph with three cues yields one candidate carrying all three cue
positions, so cue density stays measurable and no near-duplicate overlapping
spans are created.

**Boilerplate is flagged, never dropped.** Definitional ("shall mean"),
procedural ("shall come into force", headings) and reproduced-statute uses of
"shall" are classified per cue match. A paragraph whose every cue is
boilerplate is still written out, with ``exclusion_reason =
"excluded_boilerplate"``. Dropping it would make the rejection rate
unmeasurable and the exclusion rules unauditable.

**The matrix cell is looked up, never invented.** A candidate's ``matrix_cell``
comes from the document's (entity_class, subject_family) pair resolved against
``matrix_v1.jsonl``. A pair with no cell in the matrix is schema drift and is
raised, not silently nulled. A document with no derived subject family has no
cell, and ``matrix_cell`` is null.

Known recall gap, recorded rather than hidden: "should" is not a cue. RBI
text uses it both as a binding obligation and as advisory language, and at
paragraph granularity it would flood the pool. :func:`extraction_metrics`
counts paragraphs that contain "should" and no cue, so the size of the gap is a
number rather than an assumption.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping, Sequence

from src.common.io_helpers import iter_jsonl, read_jsonl, write_json, write_jsonl
from src.common.logging_setup import get_logger
from src.common.paths import PathResolver
from src.schemas.base import LATER, FieldSpec, SchemaRecord

BRANCH = "wip/P2-001"

#: Exclusion rule sets. ``v1`` is P2-001 as run and hand-reviewed (27/40 =
#: 67.5%, below the 70% floor). ``v2`` is P2-001-CORRECTIVE: v1 plus the
#: ``redirect_reference`` and ``classification_deeming`` subtypes and two more
#: definitional phrasings. v1 stays selectable so its published figures remain
#: exactly reproducible rather than being silently replaced.
#: ``v3`` is P2-001-CORRECTIVE-v2. v2 also came back at 27/40, and v3
#: replaces v2's two narrow subtypes with one general ``non_action_effect``
#: exclusion (see :func:`non_action_effect_subtype`).
#: ``v4`` is P2-001-V4: v3 re-aligned with the labelling line, which governs
#: (Karan, 2026-09-26). It drops ``disclosure_scope``, narrows ``access_scope``
#: to permissions and options (so "shall have access to ... only" is a
#: restriction and a candidate again), and re-admits risk-weight, provisioning
#: and capital-charge measurement clauses. Nothing else differs from v3.
RULES_V1 = "v1"
RULES_V2 = "v2"
RULES_V3 = "v3"
RULES_V4 = "v4"
RULE_VERSIONS = (RULES_V1, RULES_V2, RULES_V3, RULES_V4)
CURRENT_RULES = RULES_V4
#: Rule sets that apply the non_action_effect exclusion.
NON_ACTION_EFFECT_RULES = (RULES_V3, RULES_V4)

CANDIDATES_SUBDIR = "candidates"


def candidates_filename(rules: str = CURRENT_RULES) -> str:
    return f"t1_candidates_{rules}.jsonl"


def precision_sample_filename(rules: str = CURRENT_RULES) -> str:
    return f"t1_precision_sample_{rules}.csv"


CANDIDATES_FILENAME = candidates_filename()
PRECISION_SAMPLE_FILENAME = precision_sample_filename()

#: Phase 1 artifacts this stage must never write. Checked by hash before and
#: after every run (see :func:`protected_file_hashes`).
PILOT_CANDIDATES_FILENAME = "pilot_candidates.jsonl"
ANNOTATION_FILE_GLOB = "annotation_*.csv"

EXCLUDED_BOILERPLATE = "excluded_boilerplate"

#: Per-cue exclusion subtypes, recorded in ``cue_exclusions``.
EXCLUSION_DEFINITIONAL = "definitional"
EXCLUSION_PROCEDURAL = "procedural"
EXCLUSION_HEADER = "procedural_header"
EXCLUSION_QUOTED_STATUTE = "quoted_statute"
#: v2 (P2-001-CORRECTIVE). Superseded in v3 by non_action_effect, but still
#: emitted by ``--rules v2`` so the v2 artifacts stay reproducible.
EXCLUSION_REDIRECT = "redirect_reference"
EXCLUSION_CLASSIFICATION = "classification_deeming"
#: Subtypes of the paragraph-level ``excluded_boilerplate`` reason.
BOILERPLATE_SUBTYPES = (
    EXCLUSION_DEFINITIONAL,
    EXCLUSION_PROCEDURAL,
    EXCLUSION_HEADER,
    EXCLUSION_QUOTED_STATUTE,
    EXCLUSION_REDIRECT,
    EXCLUSION_CLASSIFICATION,
)

#: v3 (P2-001-CORRECTIVE-v2): one general exclusion for a cue whose only
#: content is a fact about the entity's legal position, another rule, a
#: definition, or a permission/scope boundary, not an action the entity must
#: take. Recorded as ``non_action_effect:<subtype>`` so the breakdown survives.
NON_ACTION_EFFECT = "non_action_effect"
NAE_LEGAL_EFFECT = f"{NON_ACTION_EFFECT}:legal_effect"
NAE_CROSS_REFERENCE = f"{NON_ACTION_EFFECT}:cross_reference"
NAE_DEFINITIONAL = f"{NON_ACTION_EFFECT}:definitional"
NAE_ACCESS_SCOPE = f"{NON_ACTION_EFFECT}:access_scope"
NAE_DISCLOSURE_SCOPE = f"{NON_ACTION_EFFECT}:disclosure_scope"
NON_ACTION_EFFECT_SUBTYPES = (
    NAE_LEGAL_EFFECT,
    NAE_CROSS_REFERENCE,
    NAE_DEFINITIONAL,
    NAE_ACCESS_SCOPE,
    NAE_DISCLOSURE_SCOPE,
)

EXCLUSION_SUBTYPES = BOILERPLATE_SUBTYPES + NON_ACTION_EFFECT_SUBTYPES

#: Size of the hand spot-check sample (Phase 2 gate item 1).
PRECISION_SAMPLE_SIZE = 40
#: One seed per rule version, so the v2 sample is a fresh draw rather than the
#: v1 draw re-filtered.
PRECISION_SAMPLE_SEEDS = {RULES_V1: 20260925, RULES_V2: 20260926, RULES_V3: 20260927, RULES_V4: 20260928}
PRECISION_SAMPLE_SEED = PRECISION_SAMPLE_SEEDS[RULES_V1]
#: First ``sample_index`` per version (1-40, 41-80, 81-120, 121-150), so a row
#: can never be confused with an earlier round's row judged under the same number.
SAMPLE_INDEX_START = {
    RULES_V1: 1,
    RULES_V2: PRECISION_SAMPLE_SIZE + 1,
    RULES_V3: 2 * PRECISION_SAMPLE_SIZE + 1,
    RULES_V4: 3 * PRECISION_SAMPLE_SIZE + 1,
}

#: P2-001-V4 §B.3: the v4 check samples only the re-admitted candidates,
#: 10 per re-admitted group, and scores each group on its own.
READMIT_GROUP_ACCESS = "access_restriction"
READMIT_GROUP_DISCLOSURE = "disclosure_scope"
READMIT_GROUP_MEASUREMENT = "risk_weight_provisioning"
READMIT_GROUPS = (READMIT_GROUP_ACCESS, READMIT_GROUP_DISCLOSURE, READMIT_GROUP_MEASUREMENT)
READMIT_PER_GROUP = 10
#: Below this spot-check precision the extractor needs rework (stop condition).
PRECISION_STOP_THRESHOLD = 0.70

# ---------------------------------------------------------------------------
# Cue matching
# ---------------------------------------------------------------------------

_WS = r"\s+"

#: Deontic cues. Multi-word cues come first so that at a given offset "shall
#: not" wins over "shall" and the negative obligation is the one recorded.
#: Whitespace between words is ``\s+`` because PDF extraction breaks lines
#: mid-phrase ("shall\nnot"). The lookarounds are the word boundary: "shall"
#: inside "marshall" or "shallow" never matches.
_CUE_ALTERNATIVES: tuple[str, ...] = (
    rf"shall{_WS}not",
    rf"must{_WS}not",
    rf"(?:is|are){_WS}required{_WS}to",
    rf"(?:is|are){_WS}(?:obliged|obligated){_WS}to",
    rf"(?:is|are){_WS}prohibited{_WS}from",
    rf"(?:is|are){_WS}not{_WS}permitted{_WS}to",
    rf"(?:is|are){_WS}mandatory",
    r"shall",
    r"must",
)
CUE_RE = re.compile(
    r"(?<![\w-])(?:" + "|".join(_CUE_ALTERNATIVES) + r")(?![\w-])",
    re.IGNORECASE,
)

SHOULD_RE = re.compile(r"(?<![\w-])should(?![\w-])", re.IGNORECASE)


def normalise_cue(surface: str) -> str:
    """Lower-case a matched cue and collapse its internal whitespace."""
    return " ".join(surface.lower().split())


@dataclass(frozen=True)
class CueMatch:
    """One deontic cue occurrence inside a paragraph."""

    cue: str
    start: int
    end: int
    exclusion: str | None = None


def find_cues(text: str) -> list[CueMatch]:
    """Every deontic cue in ``text``, non-overlapping, in document order."""
    return [
        CueMatch(cue=normalise_cue(m.group(0)), start=m.start(), end=m.end())
        for m in CUE_RE.finditer(text or "")
    ]


# ---------------------------------------------------------------------------
# Boilerplate exclusion (P2-001 step C.3)
# ---------------------------------------------------------------------------

#: Anchored at the cue. "shall include" is deliberately absent here: "the
#: policy shall include ..." is an obligation. It is only definitional right
#: after a quoted defined term, handled by _DEFINED_TERM_BEFORE_RE.
_DEFINITIONAL_AFTER_RE = re.compile(
    r"(?:shall|must)(?:\s+not)?\s+(?:"
    r"mean|means|"
    r"have\s+the\s+(?:same\s+)?meanings?|"
    r"be\s+construed|"
    r"be\s+deemed|"
    r"be\s+interpreted"
    r")\b",
    re.IGNORECASE,
)
#: v2 definitional phrasings, found in the v1 output ("the terms herein shall
#: bear the meanings assigned to them as below"; "'Securitisation note' shall
#: be as defined in ..."). Kept separate so v1 stays reproducible.
_DEFINITIONAL_V2_AFTER_RE = re.compile(
    r"(?:shall|must)(?:\s+not)?\s+(?:"
    r"bear\s+the\s+(?:same\s+)?meanings?|"
    r"be\s+as\s+defined\s+(?:in|under|by)"
    r")\b",
    re.IGNORECASE,
)
_INCLUDE_AFTER_RE = re.compile(r"(?:shall|must)(?:\s+not)?\s+(?:include|includes)\b", re.IGNORECASE)

#: redirect_reference (v2): the clause only points at another instrument's
#: requirements ("An AIFI shall be governed by the instructions contained in
#: Master Direction ..."). It states no duty of its own.
_REDIRECT_AFTER_RE = re.compile(
    r"(?:shall|must)(?:\s+continue\s+to)?\s+be\s+(?:"
    r"governed\s+by|"
    r"subject\s+to|"
    r"guided\s+by|"
    r"regulated\s+by|"
    r"in\s+accordance\s+with|"
    r"as\s+per"
    r")\b",
    re.IGNORECASE,
)
#: The redirect's object must name another document or body of rules.
#: "shall be subject to a ceiling of 10 per cent" or "subject to the
#: following conditions:" states the constraint itself, so it stays a
#: candidate.
_REFERENCE_OBJECT_RE = re.compile(
    r"\b(?:master\s+directions?|directions?|act|rules|regulations?|guidelines|instructions|norms|"
    r"circulars?|notifications?|scheme|provisions|framework|paragraphs?|para|sections?|chapter|"
    r"annex(?:ure)?|appendix|laws?|code)\b",
    re.IGNORECASE,
)
#: A duty named before the reference means the clause does state something to
#: do ("shall be subject to suitable validation in accordance with the
#: directions of RMCB"), so it is not a pure redirect. Ceilings, limits and
#: norms are deliberately absent: "subject to the prudential ceilings and norms
#: prescribed in ..." was hand-judged a redirect in the v1 review.
_DUTY_BEFORE_REFERENCE_RE = re.compile(
    r"\b(?:validation|approval|audit|review|verification|scrutiny|examination|monitoring|inspection|oversight)\b",
    re.IGNORECASE,
)
#: The object is read up to the end of its sentence or clause.
_CLAUSE_END_RE = re.compile(r"[.;:](?:\s|$)")
REDIRECT_OBJECT_MAX_CHARS = 250

#: classification_deeming (v2): the clause decides what something counts as or
#: how it is measured ("... shall be treated as restructuring"; "crop seasons
#: shall be standardized at twelve months"). It is not an action anyone takes.
_CLASSIFICATION_AFTER_RE = re.compile(
    r"(?:shall|must)(?:\s+not)?\s+(?:also\s+)?be\s+(?:broadly\s+)?(?:"
    r"treated|classified|categori[sz]ed|reckoned|regarded|considered|counted|standardi[sz]ed"
    r")\s+(?:as|at|into|under|towards)\b"
    # "shall be treated as confidential" imposes a duty of confidentiality.
    r"(?!\s+(?:strictly\s+)?(?:confidential|secret|a\s+priority|priority)\b)",
    re.IGNORECASE,
)

# -- v3: non_action_effect ------------------------------------------------------
# The test (P2-001-CORRECTIVE-v2 §B.2): does the clause say what the entity
# itself must DO, or state a FACT about its legal position, another rule, a
# definition, or a permission/scope boundary? Every pattern below is anchored
# at the cue, so it only claims that cue. A paragraph keeps its candidacy
# while any other cue in it states a real duty.

#: legal_effect: "outsourcing ... shall not diminish its obligations", "shall
#: be final and binding", "shall continue to apply", "shall attract penal
#: provisions".
_LEGAL_EFFECT_AFTER_RE = re.compile(
    r"(?:shall|must)\s+(?:"
    r"not\s+(?:be\s+)?(?:diminish(?:ed)?|undermin(?:e|ed)|affect(?:ed)?|prejudice(?:d)?|absolve(?:d)?|"
    r"dilute(?:d)?|relieve(?:d)?|impair(?:ed)?|override|overridden|derogate)|"
    r"continue\s+to\s+(?:apply|remain|hold\s+good|have\s+effect|operate|"
    r"be\s+(?:valid|applicable|in\s+force|effective|eligible))|"
    r"remain\s+(?:valid|unaffected|in\s+effect|applicable|binding)|"
    r"(?:also\s+)?be\s+(?:final\s+and\s+binding|final|binding|valid|invalid|void|null\s+and\s+void|"
    r"enforceable|unenforceable)|"
    r"attract\s+(?:the\s+)?(?:penal|penalt(?:y|ies)|action)"
    r")\b",
    re.IGNORECASE,
)

#: cross_reference, signpost form: "Instruction at (4) above shall also apply
#: to ...". The duty lives in the referenced rule. This needs either a rule as
#: the subject or an extension word (also / equally / mutatis mutandis), and it
#: never matches "shall apply for" or "shall apply the/a ..." (an action).
_APPLY_SIGNPOST_AFTER_RE = re.compile(
    r"(?:shall|must)\s+(?P<mods>(?:also\s+|equally\s+|not\s+|mutatis\s+mutandis\s+)*)"
    r"(?:apply|be\s+(?:made\s+)?applicable)\b"
    r"(?P<post>\s+mutatis\s+mutandis)?"
    r"(?!\s+(?:for|a|an|the|its|their|such|this|these|appropriate|suitable)\b)",
    re.IGNORECASE,
)
_RULE_SUBJECT_RE = re.compile(
    r"\b(?:instructions?|paragraphs?|paras?|provisions?|clauses?|sub-paragraphs?|guidelines|norms|"
    r"requirements?|limits?|conditions|restrictions|stipulations|directions?|circulars?|rules|regulations|"
    r"framework|ceilings?|exemptions?|relaxations?|procedures?|above|same)\b",
    re.IGNORECASE,
)

#: definitional (measurement form): "claims on the Central Government shall
#: attract zero risk weight". It says how something is measured, not what
#: anyone does. The clause must reach the measure before its sentence ends.
_MEASUREMENT_AFTER_RE = re.compile(
    r"(?:shall|must)\s+(?:also\s+)?(?:"
    r"(?:attract|carry|be\s+assigned)\b[^.;:]{0,60}?\b(?:risk\s+weights?|provisioning|capital\s+charge)|"
    r"be\s+risk[\s-]weighted\s+at"
    r")\b",
    re.IGNORECASE,
)

#: access_scope: "Such a CI shall have access to Credit Information Reports
#: pertaining to only those borrowers ...", "shall have the option to", "it
#: shall also be in order for the bank to". These grant or bound a permission;
#: they impose no duty. Negated forms ("shall not be permitted to") are
#: prohibitions and are deliberately not matched.
_ACCESS_SCOPE_AFTER_RE = re.compile(
    r"(?:shall|must)\s+(?:also\s+)?(?:"
    r"have\s+(?:access|the\s+(?:option|right|discretion|freedom|flexibility|liberty|choice)|an\s+option)|"
    # Permission to the subject, followed by a verb ("a bank shall be allowed
    # to invest"). "shall be allowed to the survivors" names a recipient the
    # entity must grant something to, which is a duty, so it is not matched.
    r"be\s+(?:permitted|allowed|entitled|free|at\s+liberty)\s+to"
    r"(?!\s+(?:the|a|an|such|all|any|its|their|his|her|each|every|them|him)\b)|"
    r"be\s+eligible\s+(?:to|for)|"
    r"be\s+in\s+order\s+(?:for|to)"
    r")\b",
    re.IGNORECASE,
)

#: disclosure_scope: "Note: This disclosure shall exclude Level 3 assets where
#: ...". The subject is a disclosure or reporting item, and the verb bounds its
#: content. "The policy shall include ..." stays a candidate because a policy
#: is not a reporting item.
_SCOPE_VERB_AFTER_RE = re.compile(
    r"(?:shall|must)\s+(?:also\s+)?(?:not\s+)?"
    r"(?:exclude|include|cover|comprise|consist\s+of|contain|capture|reflect)\b",
    re.IGNORECASE,
)
_DISCLOSURE_SUBJECT_RE = re.compile(
    r"\b(?:disclosures?|reports?|returns?|statements?|templates?|formats?|tables?|data|figures?)\b",
    re.IGNORECASE,
)
#: The subject is looked for between the last clause break and the cue.
_SUBJECT_BREAK_RE = re.compile(r"[.;:]\s|\n\s*(?:\(?[a-z0-9ivx]{1,5}[).]|\d+(?:\.\d+)*\.)\s", re.IGNORECASE)
#: A closing quote (straight or curly), optionally followed by a short
#: parenthetical such as an abbreviation, immediately before the cue.
_DEFINED_TERM_BEFORE_RE = re.compile(r"[\"”’']\s*(?:\([^)]{0,60}\)\s*)?$")

_PROCEDURAL_AFTER_RE = re.compile(
    r"shall\s+(?:"
    r"come\s+into\s+(?:force|effect|operation)|"
    r"take\s+effect|"
    r"be\s+effective|"
    r"remain\s+in\s+force|"
    r"stand\s+(?:repealed|withdrawn|superseded|rescinded|modified)|"
    r"be\s+called|be\s+cited|be\s+known\s+as|"
    # Savings clause closing nearly every Direction: "The provisions of these
    # Directions shall be in addition to, and not in derogation of ...".
    r"be\s+in\s+addition\s+to|be\s+without\s+prejudice\s+to"
    r")\b",
    re.IGNORECASE,
)
#: "These Directions shall apply to ..." is a scope clause, not an obligation
#: on anyone. Only matched when the subject is the instrument itself.
_APPLY_AFTER_RE = re.compile(r"shall\s+(?:apply|be\s+applicable)\b", re.IGNORECASE)
_INSTRUMENT_SUBJECT_BEFORE_RE = re.compile(
    r"\b(?:these|this|the|such)\s+(?:master\s+)?"
    r"(?:directions?|provisions?|circulars?|guidelines|instructions|notifications?|regulations|rules|scheme)"
    r"[^.;:]{0,40}$",
    re.IGNORECASE,
)

#: Phrases introducing reproduced statute or regulation text.
QUOTE_INTRO_RE = re.compile(
    r"\b(?:reads?\s+as\s+(?:under|follows)|"
    r"(?:is|are)\s+reproduced\s+(?:below|hereunder|as\s+under)|"
    r"(?:is|are)\s+(?:extracted|quoted)\s+(?:below|hereunder)|"
    r"provides?\s+as\s+(?:under|follows)|"
    r"states?\s+as\s+(?:under|follows))\b",
    re.IGNORECASE,
)
#: A quoted region must be at least this long before a cue inside it counts as
#: reproduced text. Short quotes are defined terms ("the bank"), not statute.
MIN_QUOTED_REGION_CHARS = 60

#: Heading heuristic bounds. A heading is short, unpunctuated at the end and
#: mostly title-cased. A clause fragment such as "(i) shall ensure that ..., and"
#: ends in a connector or starts with a clause label and is never a heading.
HEADER_MAX_CHARS = 100
_CLAUSE_LABEL_START_RE = re.compile(r"^\(?[a-z0-9ivx]{1,5}[).]\s", re.IGNORECASE)
_TITLE_STOPWORDS = frozenset(
    {"and", "or", "of", "the", "to", "for", "in", "on", "by", "with", "a", "an", "shall", "must", "not", "be"}
)


def _quoted_regions(text: str) -> list[tuple[int, int]]:
    """Character ranges inside double quotes, curly or straight.

    Curly quotes pair unambiguously. Straight quotes pair in sequence. An
    opening curly quote with no closing one quotes to the end of the paragraph,
    which is how a reproduced section that continues into the next paragraph
    reads after PDF extraction.
    """
    regions: list[tuple[int, int]] = []
    for match in re.finditer(r"“([^”]*)(”|$)", text):
        regions.append((match.start(), match.end()))
    straight = [i for i, ch in enumerate(text) if ch == '"']
    for open_at, close_at in zip(straight[0::2], straight[1::2]):
        regions.append((open_at, close_at + 1))
    return [(s, e) for s, e in regions if e - s >= MIN_QUOTED_REGION_CHARS]


#: A lettered/roman sub-heading label as RBI prints it ("A. ", "IV. "). Numeric
#: labels are left out: "4. Banks shall ..." is an operative paragraph.
_HEADING_LABEL_RE = re.compile(r"^(?:[A-Z]|[IVX]{1,5})\.\s+[A-Z]")


def is_procedural_header(text: str) -> bool:
    """Whether a single-line paragraph is a heading rather than operative text."""
    stripped = (text or "").strip()
    if not stripped or "\n" in stripped or len(stripped) > HEADER_MAX_CHARS:
        return False
    if stripped[-1] in ".;:,":
        return False
    if _CLAUSE_LABEL_START_RE.match(stripped) and not _HEADING_LABEL_RE.match(stripped):
        return False
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]*", stripped) if w.lower() not in _TITLE_STOPWORDS]
    if not words:
        return False
    capitalised = sum(1 for w in words if w[0].isupper())
    return capitalised / len(words) >= 0.6


def is_trailing_heading_line(text: str, cue_start: int) -> bool:
    """Whether the cue sits on a sub-heading PDF extraction glued to a paragraph.

    Segmentation often attaches the next sub-heading ("H. Penalty on ...") to
    the end of the preceding paragraph, or stacks a chapter title over one
    ("Chapter III – ...\\nA. Activities that shall not be outsourced"). Only the
    paragraph's **last** line qualifies, and only with a lettered/roman label
    and no closing punctuation. Every wrapped mid-paragraph line also lacks
    closing punctuation, so the position and label requirements are what keep
    ordinary operative text out.
    """
    line_start = text.rfind("\n", 0, cue_start) + 1
    if "\n" in text[cue_start:].rstrip():
        return False
    line = text[line_start:].strip()
    return (
        bool(line)
        and len(line) <= HEADER_MAX_CHARS
        and line[-1] not in ".;:,"
        and bool(_HEADING_LABEL_RE.match(line))
        # "C. Advances shall be broadly classified into" is a sentence cut
        # at a paragraph break, not a heading.
        and line.rsplit(None, 1)[-1].lower() not in _DANGLING_WORDS
    )


_DANGLING_WORDS = frozenset(
    {"the", "a", "an", "of", "on", "into", "to", "and", "or", "for", "in", "with", "by", "as", "that", "which"}
)


def previous_paragraph_introduces_quote(previous_text: str | None) -> bool:
    """Whether the preceding paragraph ends by introducing reproduced text."""
    if not previous_text:
        return False
    tail = previous_text.strip()[-120:]
    return bool(QUOTE_INTRO_RE.search(tail)) and tail.rstrip().endswith((":", ":-", ":—", "-"))


def is_redirect_reference(text: str, cue_start: int) -> bool:
    """Whether the cue opens a redirect to another instrument's requirements."""
    match = _REDIRECT_AFTER_RE.match(text, cue_start)
    if match is None:
        return False
    window = text[match.end():match.end() + REDIRECT_OBJECT_MAX_CHARS]
    end = _CLAUSE_END_RE.search(window)
    obj = window[:end.start()] if end else window
    reference = _REFERENCE_OBJECT_RE.search(obj)
    if reference is None:
        return False
    return not _DUTY_BEFORE_REFERENCE_RE.search(obj, 0, reference.start())


def is_classification_deeming(text: str, cue_start: int) -> bool:
    """Whether the cue opens a clause classifying or standardising something."""
    return _CLASSIFICATION_AFTER_RE.match(text, cue_start) is not None


def _clause_subject(text: str, cue_start: int, window: int = 160) -> str:
    """The text between the cue and the last clause break before it."""
    head = text[max(0, cue_start - window):cue_start]
    breaks = list(_SUBJECT_BREAK_RE.finditer(head))
    return head[breaks[-1].end():] if breaks else head


#: v4: the one access_scope form that is a restriction, not a permission.
_HAVE_ACCESS_AFTER_RE = re.compile(r"(?:shall|must)\s+(?:also\s+)?have\s+access\b", re.IGNORECASE)


def readmitted_group(text: str, cue_start: int) -> str | None:
    """Which v4 change re-admits a cue that v3 excluded, or ``None``.

    Only meaningful for cues v3 excluded as non_action_effect. A cue that also
    matches a classification or v2 definition phrasing stays excluded in v4,
    so it has no group.
    """
    tail = text[cue_start:cue_start + 120]
    if _DEFINITIONAL_V2_AFTER_RE.match(tail) or is_classification_deeming(text, cue_start):
        return None
    if _MEASUREMENT_AFTER_RE.match(tail):
        return READMIT_GROUP_MEASUREMENT
    if _HAVE_ACCESS_AFTER_RE.match(tail):
        return READMIT_GROUP_ACCESS
    if _SCOPE_VERB_AFTER_RE.match(tail) and _is_disclosure_subject(_clause_subject(text, cue_start)):
        return READMIT_GROUP_DISCLOSURE
    return None


def non_action_effect_subtype(text: str, cue_start: int, rules: str = RULES_V3) -> str | None:
    """The ``non_action_effect:<subtype>`` a cue opens, or ``None``.

    Order decides only which subtype is recorded when several apply: "shall
    continue to be governed by the Act" is both a continuity and a
    cross-reference clause, and is recorded as the cross-reference.

    ``rules="v4"`` applies P2-001-V4's three changes and nothing else:
    measurement clauses (risk weight, provisioning, capital charge) are no
    longer ``definitional``; "shall have access" is a restriction, not an
    ``access_scope`` permission; and ``disclosure_scope`` is gone.
    """
    v4 = rules == RULES_V4
    tail = text[cue_start:cue_start + 120]

    if is_redirect_reference(text, cue_start):
        return NAE_CROSS_REFERENCE
    signpost = _APPLY_SIGNPOST_AFTER_RE.match(text, cue_start)
    if signpost is not None:
        mods = (signpost.group("mods") or "").lower()
        extends = any(w in mods for w in ("also", "equally", "mutatis")) or signpost.group("post")
        if extends or _RULE_SUBJECT_RE.search(_clause_subject(text, cue_start)):
            return NAE_CROSS_REFERENCE

    if (
        _DEFINITIONAL_V2_AFTER_RE.match(tail)
        or is_classification_deeming(text, cue_start)
        or (not v4 and _MEASUREMENT_AFTER_RE.match(tail))
    ):
        return NAE_DEFINITIONAL

    if _LEGAL_EFFECT_AFTER_RE.match(tail):
        return NAE_LEGAL_EFFECT

    if _ACCESS_SCOPE_AFTER_RE.match(tail) and not (v4 and _HAVE_ACCESS_AFTER_RE.match(tail)):
        return NAE_ACCESS_SCOPE

    if (
        not v4
        and _SCOPE_VERB_AFTER_RE.match(tail)
        and _is_disclosure_subject(_clause_subject(text, cue_start))
    ):
        return NAE_DISCLOSURE_SCOPE

    return None


#: A pronoun directly before the cue ("..., it shall include such missed out
#: data") means an entity is the subject, and it is acting.
_PRONOUN_SUBJECT_RE = re.compile(r"\b(?:it|they|he|she|we|who)\s*$", re.IGNORECASE)
DISCLOSURE_SUBJECT_MAX_WORDS = 6


def _is_disclosure_subject(subject: str) -> bool:
    """Whether the clause's subject, right before the cue, is a reporting item."""
    if _PRONOUN_SUBJECT_RE.search(subject):
        return False
    near = " ".join(subject.split()[-DISCLOSURE_SUBJECT_MAX_WORDS:])
    return bool(_DISCLOSURE_SUBJECT_RE.search(near))


def classify_cue(
    text: str,
    cue: CueMatch,
    *,
    quoted_regions: Sequence[tuple[int, int]] = (),
    header: bool = False,
    after_quote_intro: bool = False,
    rules: str = CURRENT_RULES,
) -> str | None:
    """Exclusion subtype for one cue match, or ``None`` if it is a candidate.

    Checked in order: heading, definitional, procedural, reproduced statute,
    then the v2 redirect and classification subtypes. The order only decides
    which subtype is recorded when several apply; any of them excludes the
    match. The v2 subtypes come last so that every cue v1 excluded keeps its
    v1 subtype, and the v1 -> v2 difference stays readable per subtype.
    """
    if rules not in RULE_VERSIONS:
        raise ValueError(f"unknown rule version {rules!r}; expected one of {RULE_VERSIONS}")
    v2 = rules == RULES_V2

    if header or is_trailing_heading_line(text, cue.start):
        return EXCLUSION_HEADER

    tail = text[cue.start:cue.start + 80]
    head = text[max(0, cue.start - 120):cue.start]

    if _DEFINITIONAL_AFTER_RE.match(tail):
        return EXCLUSION_DEFINITIONAL
    if _INCLUDE_AFTER_RE.match(tail) and _DEFINED_TERM_BEFORE_RE.search(head):
        return EXCLUSION_DEFINITIONAL

    if _PROCEDURAL_AFTER_RE.match(tail):
        return EXCLUSION_PROCEDURAL
    if _APPLY_AFTER_RE.match(tail) and _INSTRUMENT_SUBJECT_BEFORE_RE.search(head):
        return EXCLUSION_PROCEDURAL

    if after_quote_intro:
        return EXCLUSION_QUOTED_STATUTE
    if any(start < cue.start and cue.end <= end for start, end in quoted_regions):
        return EXCLUSION_QUOTED_STATUTE
    intro = QUOTE_INTRO_RE.search(text, 0, cue.start)
    if intro is not None:
        return EXCLUSION_QUOTED_STATUTE

    if v2:
        if _DEFINITIONAL_V2_AFTER_RE.match(tail):
            return EXCLUSION_DEFINITIONAL
        if is_redirect_reference(text, cue.start):
            return EXCLUSION_REDIRECT
        if is_classification_deeming(text, cue.start):
            return EXCLUSION_CLASSIFICATION

    if rules in NON_ACTION_EFFECT_RULES:
        return non_action_effect_subtype(text, cue.start, rules)

    return None


def classify_paragraph_cues(
    text: str, previous_text: str | None = None, *, rules: str = CURRENT_RULES
) -> list[CueMatch]:
    """Find every cue in a paragraph and classify each one."""
    cues = find_cues(text)
    if not cues:
        return []
    regions = _quoted_regions(text)
    header = is_procedural_header(text)
    after_intro = previous_paragraph_introduces_quote(previous_text)
    return [
        CueMatch(
            cue=c.cue,
            start=c.start,
            end=c.end,
            exclusion=classify_cue(
                text, c, quoted_regions=regions, header=header, after_quote_intro=after_intro,
                rules=rules,
            ),
        )
        for c in cues
    ]


# ---------------------------------------------------------------------------
# Candidate record
# ---------------------------------------------------------------------------


@dataclass
class ObligationCandidate(SchemaRecord):
    """One machine-proposed obligation candidate (P2-001 schema, section D).

    Lives here rather than in :mod:`src.schemas` because changing that package
    is a base-branch change needing all three owners. ``cue_exclusions`` is the
    one field beyond the prompt's schema. It holds the per-cue exclusion
    subtype, without which the rejection rate over cue matches (gate item 2)
    could not be recomputed from the file.
    """

    candidate_id: str
    document_id: str
    paragraph_id: str
    entity_class: str | None = None
    cue_matched: list[str] = field(default_factory=list)
    cue_position: list[list[int]] = field(default_factory=list)
    span_text: str = ""
    matrix_cell: str | None = None
    exclusion_reason: str | None = None
    cue_exclusions: list[str | None] = field(default_factory=list)

    FIELD_SPECS: ClassVar[tuple[FieldSpec, ...]] = (
        FieldSpec(
            "candidate_id", (str,), True, False,
            "Deterministic id, 't1c_' + paragraph_id. Stable across re-runs so the precision sample stays joinable.",
            LATER,
        ),
        FieldSpec("document_id", (str,), True, False, "Source DocumentRecord id.", LATER),
        FieldSpec("paragraph_id", (str,), True, False, "Source ParagraphRecord id.", LATER),
        FieldSpec(
            "entity_class", (str,), False, True,
            "entity_class_raw of the source document, from the manifest. The class of the file the text came from, NOT an applicability judgement.",
            LATER,
        ),
        FieldSpec(
            "cue_matched", (list,), True, False,
            "Every deontic cue in the paragraph, normalised (lower-case, single spaces), in document order.",
            LATER,
        ),
        FieldSpec(
            "cue_position", (list,), True, False,
            "[char_start, char_end] of each cue within span_text, aligned index-for-index with cue_matched.",
            LATER,
        ),
        FieldSpec(
            "span_text", (str,), True, False,
            "The full paragraph text. Paragraph granularity, not sentence-split.",
            LATER,
        ),
        FieldSpec(
            "matrix_cell", (str,), False, True,
            "'<entity_class_term_id>|<subject_family_term_id>' of the matrix_v1 cell this document populates. Null when the document has no subject family.",
            LATER,
        ),
        FieldSpec(
            "exclusion_reason", (str,), False, True,
            "Set only when EVERY cue in the paragraph is excluded; null otherwise. 'excluded_boilerplate' "
            "(P2-001 subtypes), 'non_action_effect:<subtype>[+<subtype>]' (v3), or both joined by '+'. "
            "See paragraph_exclusion_reason().",
            LATER,
        ),
        FieldSpec(
            "cue_exclusions", (list,), False, False,
            f"Per-cue exclusion subtype aligned with cue_matched: one of {', '.join(EXCLUSION_SUBTYPES)}, or null for a kept cue.",
            LATER,
        ),
    )

    def validate(self) -> list[str]:
        errors = super().validate()
        n = len(self.cue_matched)
        if n == 0:
            errors.append("cue_matched: a candidate needs at least one cue")
        if len(self.cue_position) != n:
            errors.append(f"cue_position: {len(self.cue_position)} entries for {n} cues")
        if len(self.cue_exclusions) != n:
            errors.append(f"cue_exclusions: {len(self.cue_exclusions)} entries for {n} cues")
        for index, pos in enumerate(self.cue_position):
            if not (isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, int) for v in pos)):
                errors.append(f"cue_position[{index}]: expected [start, end], got {pos!r}")
                continue
            start, end = pos
            if not (0 <= start < end <= len(self.span_text)):
                errors.append(f"cue_position[{index}]: {pos} out of range for span_text")
            elif index < n and normalise_cue(self.span_text[start:end]) != self.cue_matched[index]:
                errors.append(f"cue_position[{index}]: text at {pos} is not {self.cue_matched[index]!r}")
        for index, reason in enumerate(self.cue_exclusions):
            if reason is not None and reason not in EXCLUSION_SUBTYPES:
                errors.append(f"cue_exclusions[{index}]: unknown subtype {reason!r}")
        if len(self.cue_exclusions) == n:
            expected = paragraph_exclusion_reason(self.cue_exclusions)
            if self.exclusion_reason != expected:
                errors.append(
                    f"exclusion_reason: {self.exclusion_reason!r} but the cue exclusions give {expected!r} "
                    "(set exactly when every cue is excluded)"
                )
        if self.candidate_id != candidate_id_for(self.paragraph_id):
            errors.append("candidate_id: must be derived from paragraph_id")
        return errors


def candidate_id_for(paragraph_id: str) -> str:
    return f"t1c_{paragraph_id}"


def paragraph_exclusion_reason(cue_exclusions: Sequence[str | None]) -> str | None:
    """The paragraph-level reason, set only when every cue is excluded.

    * every excluded cue is a P2-001 boilerplate subtype -> ``excluded_boilerplate``
      (unchanged, so v1/v2 files still validate);
    * every excluded cue is non_action_effect -> ``non_action_effect:<subtypes>``,
      with multiple subtypes joined by ``+`` in sorted order;
    * both families present -> ``excluded_boilerplate+non_action_effect:<subtypes>``.
    """
    if not cue_exclusions or any(e is None for e in cue_exclusions):
        return None
    prefix = NON_ACTION_EFFECT + ":"
    nae = sorted({e[len(prefix):] for e in cue_exclusions if e.startswith(prefix)})
    boilerplate = any(not e.startswith(prefix) for e in cue_exclusions)
    parts = []
    if boilerplate:
        parts.append(EXCLUDED_BOILERPLATE)
    if nae:
        parts.append(prefix + "+".join(nae))
    return "+".join(parts)


def build_candidate(
    paragraph: Mapping[str, Any],
    *,
    entity_class: str | None,
    matrix_cell: str | None,
    previous_text: str | None = None,
    rules: str = CURRENT_RULES,
) -> ObligationCandidate | None:
    """A candidate for one paragraph row, or ``None`` if it has no cue."""
    text = paragraph.get("text") or ""
    cues = classify_paragraph_cues(text, previous_text, rules=rules)
    if not cues:
        return None
    exclusions = [c.exclusion for c in cues]
    return ObligationCandidate(
        candidate_id=candidate_id_for(paragraph["paragraph_id"]),
        document_id=paragraph["document_id"],
        paragraph_id=paragraph["paragraph_id"],
        entity_class=entity_class,
        cue_matched=[c.cue for c in cues],
        cue_position=[[c.start, c.end] for c in cues],
        span_text=text,
        matrix_cell=matrix_cell,
        exclusion_reason=paragraph_exclusion_reason(exclusions),
        cue_exclusions=exclusions,
    )


# ---------------------------------------------------------------------------
# Matrix cell resolution (stop condition: schema drift)
# ---------------------------------------------------------------------------


class SchemaDriftError(RuntimeError):
    """A matrix cell reference that does not exist in ``matrix_v1.jsonl``."""


def cell_id(cell: Mapping[str, Any]) -> str:
    return f"{cell['entity_class_term_id']}|{cell['subject_family_term_id']}"


def document_cell_map(
    manifest: Iterable[Mapping[str, Any]], cells: Iterable[Mapping[str, Any]]
) -> dict[str, str | None]:
    """document_id -> matrix cell id (or ``None``), cross-checked both ways.

    Raises :class:`SchemaDriftError` when a document's (entity_class,
    subject_family) has no cell, or when the cell that exists does not list the
    document in ``source_directions``: either means the manifest and the matrix
    were built from different corpus states.
    """
    cells = list(cells)
    by_key = {(c["entity_class"], c["subject_family"]): c for c in cells}
    problems: list[str] = []
    mapping: dict[str, str | None] = {}

    for record in manifest:
        doc_id = record["document_id"]
        ec, sf = record.get("entity_class"), record.get("subject_family")
        if not (ec and sf):
            mapping[doc_id] = None
            continue
        cell = by_key.get((ec, sf))
        if cell is None:
            problems.append(f"{doc_id}: no matrix cell for ({ec!r}, {sf!r})")
            continue
        if doc_id not in (cell.get("source_directions") or []):
            problems.append(f"{doc_id}: cell {cell_id(cell)} does not list it in source_directions")
            continue
        mapping[doc_id] = cell_id(cell)

    if problems:
        raise SchemaDriftError(
            f"{len(problems)} matrix cell reference(s) do not resolve against matrix_v1.jsonl; "
            f"first: {problems[0]}"
        )
    return mapping


def check_candidate_cells(
    candidates: Iterable[ObligationCandidate], cells: Iterable[Mapping[str, Any]]
) -> list[str]:
    """Every candidate whose ``matrix_cell`` is not a cell in the matrix."""
    known = {cell_id(c) for c in cells}
    return [
        f"{c.candidate_id}: matrix_cell {c.matrix_cell!r} not in matrix_v1.jsonl"
        for c in candidates
        if c.matrix_cell is not None and c.matrix_cell not in known
    ]


# ---------------------------------------------------------------------------
# Phase 1 artifact protection
# ---------------------------------------------------------------------------


def protected_paths(resolver: PathResolver) -> list[Path]:
    """Every existing Phase 1 file this stage must leave byte-identical."""
    found: set[Path] = set()
    for root in resolver.search_roots():
        benchmark = root / resolver.relative_paths["benchmark"]
        if not benchmark.is_dir():
            continue
        pilot = benchmark / PILOT_CANDIDATES_FILENAME
        if pilot.is_file():
            found.add(pilot)
        found.update(p for p in benchmark.rglob(ANNOTATION_FILE_GLOB) if p.is_file())
    return sorted(found)


def protected_file_hashes(resolver: PathResolver) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected_paths(resolver)
    }


class ProtectedFileChanged(RuntimeError):
    """A Phase 1 artifact changed during a P2-001 run."""


def assert_unchanged(before: Mapping[str, str], after: Mapping[str, str]) -> None:
    changed = sorted(k for k in before if after.get(k) != before[k])
    added = sorted(k for k in after if k not in before)
    if changed or added:
        raise ProtectedFileChanged(
            f"Phase 1 artifacts touched by this run — changed: {changed}, created: {added}"
        )


def candidates_path(resolver: PathResolver, rules: str = CURRENT_RULES) -> Path:
    path = resolver.write_path("benchmark", CANDIDATES_SUBDIR, candidates_filename(rules))
    if path.name == PILOT_CANDIDATES_FILENAME:  # guards a future rename
        raise ProtectedFileChanged("candidate output would overwrite pilot_candidates.jsonl")
    return path


# ---------------------------------------------------------------------------
# Corpus run
# ---------------------------------------------------------------------------


def extract_corpus_candidates(
    resolver: PathResolver,
    cfg: Mapping[str, Any] | None = None,
    *,
    logger: logging.Logger | None = None,
    rules: str = CURRENT_RULES,
) -> tuple[list[ObligationCandidate], dict[str, Any]]:
    """Scan every manifest document's paragraphs and build candidates.

    Returns the candidates plus scan counters that :func:`extraction_metrics`
    folds into the report. Reads through the resolver, so it runs unchanged
    against a read-only Kaggle input mount.
    """
    logger = logger or get_logger("benchmark.candidates", cfg or {})

    manifest = read_jsonl(resolver.read_path("metadata", "document_manifest.jsonl"))
    cells = read_jsonl(resolver.read_path("matrix", "matrix_v1.jsonl"))
    doc_cells = document_cell_map(manifest, cells)

    candidates: list[ObligationCandidate] = []
    scan: dict[str, Any] = {
        "documents_in_manifest": len(manifest),
        "documents_scanned": 0,
        "documents_missing_paragraphs": [],
        "paragraphs_scanned": 0,
        "paragraphs_by_entity_class": Counter(),
        "paragraphs_should_without_cue": 0,
    }

    for record in manifest:
        doc_id = record["document_id"]
        path = resolver.find_read_path("processed", f"{doc_id}.jsonl")
        if path is None:
            scan["documents_missing_paragraphs"].append(doc_id)
            continue
        scan["documents_scanned"] += 1
        entity_class = record.get("entity_class_raw")
        previous_text: str | None = None
        rows = sorted(iter_jsonl(path), key=lambda r: (r.get("position") is None, r.get("position") or 0))
        for row in rows:
            scan["paragraphs_scanned"] += 1
            scan["paragraphs_by_entity_class"][entity_class] += 1
            candidate = build_candidate(
                row, entity_class=entity_class, matrix_cell=doc_cells.get(doc_id),
                previous_text=previous_text, rules=rules,
            )
            if candidate is not None:
                candidates.append(candidate)
            elif SHOULD_RE.search(row.get("text") or ""):
                scan["paragraphs_should_without_cue"] += 1
            previous_text = row.get("text")

    if scan["documents_scanned"] == 0:
        searched = ", ".join(str(p) for p in resolver.candidate_read_paths("processed"))
        raise FileNotFoundError(
            f"no paragraph files (processed/<document_id>.jsonl) found for any of the "
            f"{len(manifest)} manifest documents; searched {searched}. Refusing to write an "
            "empty candidate file."
        )

    drift = check_candidate_cells(candidates, cells)
    if drift:
        raise SchemaDriftError(f"{len(drift)} candidate(s) reference a non-existent cell; first: {drift[0]}")

    invalid = [(c.candidate_id, c.validate()) for c in candidates]
    invalid = [(cid, errs) for cid, errs in invalid if errs]
    if invalid:
        raise ValueError(f"{len(invalid)} invalid candidate record(s); first: {invalid[0]}")

    scan["rules"] = rules
    logger.info(
        "candidates (%s rules): %d paragraphs scanned, %d candidates (%d excluded_boilerplate)",
        rules, scan["paragraphs_scanned"], len(candidates),
        sum(1 for c in candidates if c.exclusion_reason),
    )
    return candidates, scan


def persist_candidates(
    candidates: Sequence[ObligationCandidate], resolver: PathResolver, rules: str = CURRENT_RULES
) -> Path:
    return write_jsonl(candidates_path(resolver, rules), [c.to_dict() for c in candidates])


def load_candidates(path: Path | str) -> list[ObligationCandidate]:
    return [ObligationCandidate.from_dict(r) for r in iter_jsonl(path)]


def matrix_cell_counts(candidates: Sequence[ObligationCandidate]) -> dict[str, Any]:
    """Matrix-cell coverage of the KEPT candidates (excluded paragraphs are not candidates)."""
    kept = [c for c in candidates if not c.exclusion_reason]
    return {
        "candidates_with_matrix_cell": sum(1 for c in kept if c.matrix_cell),
        "candidates_without_matrix_cell": sum(1 for c in kept if not c.matrix_cell),
        "distinct_matrix_cells": len({c.matrix_cell for c in kept if c.matrix_cell}),
        "matrix_cell_counts_basis": "kept candidates only",
    }


def extraction_metrics(candidates: Sequence[ObligationCandidate], scan: Mapping[str, Any]) -> dict[str, Any]:
    """Counts for the report and gate item 2 (rejection rate).

    The rejection rate is reported over cue matches, as the prompt asks, and
    also over paragraphs. A rate of exactly zero is flagged: on RBI text,
    where every Direction opens with definitions and a commencement clause, it
    means the exclusion rules never fired.
    """
    cue_total = sum(len(c.cue_matched) for c in candidates)
    cue_excluded = sum(1 for c in candidates for e in c.cue_exclusions if e is not None)
    subtype_counts = Counter(e for c in candidates for e in c.cue_exclusions if e is not None)
    excluded_paragraphs = sum(1 for c in candidates if c.exclusion_reason)
    kept = [c for c in candidates if not c.exclusion_reason]

    by_class_kept = Counter(c.entity_class for c in kept)
    by_class_excluded = Counter(c.entity_class for c in candidates if c.exclusion_reason)
    cue_counts = Counter(cue for c in candidates for cue in c.cue_matched)
    kept_cue_counts = Counter(
        cue for c in candidates for cue, e in zip(c.cue_matched, c.cue_exclusions) if e is None
    )

    rejection_rate = (cue_excluded / cue_total) if cue_total else None
    paragraphs_scanned = scan.get("paragraphs_scanned", 0)
    return {
        "rules": scan.get("rules"),
        "documents_in_manifest": scan.get("documents_in_manifest"),
        "documents_scanned": scan.get("documents_scanned"),
        "documents_missing_paragraphs": list(scan.get("documents_missing_paragraphs", [])),
        "paragraphs_scanned": paragraphs_scanned,
        "paragraphs_with_cue": len(candidates),
        "paragraphs_with_cue_rate": (len(candidates) / paragraphs_scanned) if paragraphs_scanned else None,
        "candidates_total": len(candidates),
        "candidates_kept": len(kept),
        "candidates_excluded": excluded_paragraphs,
        # Literal count of exclusion_reason == "excluded_boilerplate". For v1/v2
        # this equals candidates_excluded; v3 adds non_action_effect reasons.
        "candidates_excluded_boilerplate": sum(1 for c in candidates if c.exclusion_reason == EXCLUDED_BOILERPLATE),
        "exclusion_reason_counts": dict(Counter(c.exclusion_reason for c in candidates if c.exclusion_reason).most_common()),
        # Kept candidates only (P2-001-V4 §B.5). Earlier metrics counted every
        # cue paragraph, excluded ones included, which overstated the matrix
        # coverage of the candidate pool.
        **matrix_cell_counts(candidates),
        "cue_matches_total": cue_total,
        "cue_matches_excluded": cue_excluded,
        "rejection_rate_cue_level": rejection_rate,
        "rejection_rate_paragraph_level": (excluded_paragraphs / len(candidates)) if candidates else None,
        "rejection_rate_zero_flag": rejection_rate == 0,
        "exclusions_by_subtype": dict(subtype_counts.most_common()),
        "cue_distribution_all": dict(cue_counts.most_common()),
        "cue_distribution_kept": dict(kept_cue_counts.most_common()),
        "mixed_paragraphs": sum(
            1 for c in candidates
            if any(e is None for e in c.cue_exclusions) and any(e is not None for e in c.cue_exclusions)
        ),
        "paragraphs_should_without_cue": scan.get("paragraphs_should_without_cue", 0),
        "paragraphs_by_entity_class": dict(sorted(Counter(scan.get("paragraphs_by_entity_class", {})).items())),
        "kept_by_entity_class": dict(sorted(by_class_kept.items(), key=lambda kv: str(kv[0]))),
        "excluded_by_entity_class": dict(sorted(by_class_excluded.items(), key=lambda kv: str(kv[0]))),
    }


# ---------------------------------------------------------------------------
# Precision spot-check sample (gate item 1)
# ---------------------------------------------------------------------------

SAMPLE_COLUMNS = (
    "sample_index",
    "candidate_id",
    "entity_class",
    "document_id",
    "paragraph_id",
    "cue_matched",
    "span_text",
    "is_obligation",
    "reviewer_note",
)
#: Accepted answers in the ``is_obligation`` column.
SAMPLE_YES = frozenset({"y", "yes", "1", "true"})
SAMPLE_NO = frozenset({"n", "no", "0", "false"})


def allocate_sample(class_sizes: Mapping[str, int], n: int) -> dict[str, int]:
    """Spread ``n`` draws across classes, small ones included.

    Every class first gets an equal share (capped at its size), so small
    classes are not crowded out by the largest ones. The remainder is dealt one
    at a time to classes in descending size order, skipping any class already
    exhausted, until ``n`` is reached.
    """
    classes = sorted(k for k, v in class_sizes.items() if v > 0)
    n = min(n, sum(class_sizes[k] for k in classes))
    if not classes or n <= 0:
        return {}

    base = n // len(classes)
    allocation = {k: min(base, class_sizes[k]) for k in classes}
    remaining = n - sum(allocation.values())

    by_size = sorted(classes, key=lambda k: (-class_sizes[k], k))
    while remaining > 0:
        for k in by_size:
            if remaining == 0:
                break
            if allocation[k] < class_sizes[k]:
                allocation[k] += 1
                remaining -= 1
    return {k: v for k, v in allocation.items() if v > 0}


def draw_precision_sample(
    candidates: Sequence[ObligationCandidate],
    *,
    n: int = PRECISION_SAMPLE_SIZE,
    seed: int = PRECISION_SAMPLE_SEED,
    exclude_ids: Iterable[str] = (),
) -> list[ObligationCandidate]:
    """Stratified random sample of kept (non-excluded) candidates.

    ``exclude_ids`` removes candidates an earlier sample already put in front
    of the reviewer. The v2 sample excludes all 40 v1 rows, because judging
    the corrected rules on rows that exposed the rule gap would be circular.
    """
    skip = set(exclude_ids)
    by_class: dict[str, list[ObligationCandidate]] = defaultdict(list)
    for candidate in candidates:
        if not candidate.exclusion_reason and candidate.candidate_id not in skip:
            by_class[candidate.entity_class or "<none>"].append(candidate)
    for pool in by_class.values():
        pool.sort(key=lambda c: c.candidate_id)

    allocation = allocate_sample({k: len(v) for k, v in by_class.items()}, n)
    rng = random.Random(seed)
    sample: list[ObligationCandidate] = []
    for cls in sorted(allocation):
        sample.extend(rng.sample(by_class[cls], allocation[cls]))
    rng.shuffle(sample)
    return sample


def readmitted_candidates(
    v3: Sequence[ObligationCandidate], v4: Sequence[ObligationCandidate]
) -> tuple[dict[str, list[ObligationCandidate]], list[ObligationCandidate]]:
    """Candidates kept by v4 but excluded by v3, pooled by the v4 change responsible.

    A paragraph is attributed to a group only when every cue v4 re-admitted
    belongs to that one group. Paragraphs re-admitted by more than one change
    are returned separately and left out of the per-group sample, so each
    group's precision measures one rule change.
    """
    old = {c.candidate_id: c for c in v3}
    pools: dict[str, list[ObligationCandidate]] = {g: [] for g in READMIT_GROUPS}
    multiple: list[ObligationCandidate] = []
    for cand in v4:
        before = old[cand.candidate_id]
        if cand.exclusion_reason or not before.exclusion_reason:
            continue
        groups = {
            readmitted_group(cand.span_text, start)
            for (start, _end), was, now in zip(cand.cue_position, before.cue_exclusions, cand.cue_exclusions)
            if was is not None and now is None
        }
        if None in groups:
            raise ValueError(f"{cand.candidate_id}: re-admitted by something other than a v4 change")
        if len(groups) == 1:
            pools[groups.pop()].append(cand)
        else:
            multiple.append(cand)
    return pools, multiple


def draw_readmit_sample(
    pools: Mapping[str, Sequence[ObligationCandidate]],
    *,
    per_group: int = READMIT_PER_GROUP,
    seed: int,
    exclude_ids: Iterable[str] = (),
) -> list[tuple[ObligationCandidate, str]]:
    """``per_group`` candidates from each pool, stratified by entity class, then shuffled.

    Shuffling across groups means the reviewer never sees a block of one kind
    of clause. The group of each row is kept out of the sample file (see
    :func:`write_group_map`).
    """
    drawn: list[tuple[ObligationCandidate, str]] = []
    for offset, group in enumerate(READMIT_GROUPS):
        picks = draw_precision_sample(pools.get(group, []), n=per_group, seed=seed + offset,
                                      exclude_ids=exclude_ids)
        drawn.extend((c, group) for c in picks)
    random.Random(seed).shuffle(drawn)
    return drawn


def score_by_group(rows: Sequence[Mapping[str, str]], group_of: Mapping[str, str]) -> dict[str, Any]:
    """Per-group and overall precision for the v4 re-admitted sample.

    Gate (P2-001-V4 §B.3): a group below 70% gets its v3 exclusion back. This
    function only reports that, and never changes a rule itself.
    """
    missing = [r.get("candidate_id") for r in rows if r.get("candidate_id") not in group_of]
    if missing:
        raise ValueError(f"no group recorded for {len(missing)} row(s), e.g. {missing[0]}")
    result: dict[str, Any] = {"groups": {}}
    for group in READMIT_GROUPS:
        scored = score_precision_sample([r for r in rows if group_of[r["candidate_id"]] == group])
        scored["restore_v3_exclusion"] = scored["precision_stop_triggered"]
        result["groups"][group] = scored
    result["overall"] = score_precision_sample(rows)
    result["groups_failing_gate"] = [g for g, s in result["groups"].items() if s["restore_v3_exclusion"]]
    return result


#: Two cue sentences are one text when either is a prefix of the other (a copy
#: cut at a page break) or when they are at least this similar (a one-word
#: variant, e.g. "their license" vs "their CoR").
NEAR_DUPLICATE_RATIO = 0.9


def cue_sentence(text: str, start: int, end: int) -> str:
    """The normalised sentence around a cue: lower-case, whitespace collapsed,
    leading enumerators and a trailing page number stripped."""
    left, right = cue_sentence_bounds(text, start, end)
    return normalise_sentence(text[left:right])


def cue_sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Raw ``[left, right)`` offsets of the sentence around a cue. Boundaries are
    ". ", "; ", ": " or a new "(" clause line before the cue, and the next ". "
    or "; " after it."""
    left = max(text.rfind(". ", 0, start), text.rfind("; ", 0, start), text.rfind(": ", 0, start),
               text.rfind("\n(", 0, start))
    left = 0 if left < 0 else left + 1
    stop = re.search(r"[.;](?:\s|$)", text[end:])
    right = end + stop.end() if stop else len(text)
    return left, right


def normalise_sentence(raw: str) -> str:
    """The normalisation behind :func:`cue_sentence` and :func:`near_duplicate_clusters`."""
    sentence = " ".join(raw.lower().split())
    sentence = re.sub(r"^(?:\(?[a-z0-9ivx]{1,5}[).]\s*)+", "", sentence)
    return re.sub(r"\s+\d{1,3}$", "", sentence).strip(" .;")


def is_near_duplicate(a: str, b: str) -> bool:
    """The pairwise test behind :func:`near_duplicate_clusters`: prefix, or ratio >= NEAR_DUPLICATE_RATIO."""
    return _near_duplicate(a, b)


def _near_duplicate(a: str, b: str) -> bool:
    import difflib

    if a.startswith(b) or b.startswith(a):
        return True
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= NEAR_DUPLICATE_RATIO


def near_duplicate_clusters(sentences: Sequence[str]) -> list[list[int]]:
    """Group indices whose sentences are near-identical (single-link, in input order).

    The consolidated Directions repeat the same sentence across entity classes,
    so a per-row sample can hold far fewer distinct texts than rows. Repeated
    text across classes is also direct evidence of a SHARED obligation, which
    is P2-002's concern, so clusters are reported rather than discarded.
    """
    clusters: list[list[int]] = []
    for i, s in enumerate(sentences):
        home = next((c for c in clusters if any(_near_duplicate(s, sentences[j]) for j in c)), None)
        if home is None:
            clusters.append([i])
        else:
            home.append(i)
    return clusters


def score_distinct(rows: Sequence[Mapping[str, str]], sentences: Sequence[str]) -> dict[str, Any]:
    """Precision per distinct text: a cluster counts as an obligation only if every row in it is ``y``.

    Rows in one cluster that were labelled differently are listed rather than
    silently resolved.
    """
    clusters = near_duplicate_clusters(sentences)
    yes = sum(1 for c in clusters if all((rows[i].get("is_obligation") or "").strip().lower() in SAMPLE_YES for i in c))
    conflicting = [[rows[i].get("sample_index") for i in c] for c in clusters
                   if len({(rows[i].get("is_obligation") or "").strip().lower() for i in c}) > 1]
    n = len(clusters)
    return {
        "rows": len(rows),
        "distinct_texts": n,
        "true_obligation": yes,
        "precision": yes / n if n else None,
        "wilson_95": list(wilson_interval(yes, n)) if n else None,
        "repeated_texts": [[rows[i].get("sample_index") for i in c] for c in clusters if len(c) > 1],
        "clusters_with_conflicting_labels": conflicting,
    }


def read_sample(path: Path | str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sample_has_judgments(path: Path | str) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    return any((row.get("is_obligation") or "").strip() or (row.get("reviewer_note") or "").strip()
               for row in read_sample(path))


class SampleOverwriteError(RuntimeError):
    """Refused to overwrite a precision sample that already holds judgments."""


def write_group_map(sample: Sequence[tuple[ObligationCandidate, str]], path: Path | str) -> Path:
    """candidate_id -> re-admit group, kept OUT of the reviewer's CSV.

    It holds provenance only (which v4 change re-admitted the row), never a
    prediction. It lives in its own file so the sample CSV the reviewer opens
    carries no hint beyond the span itself.
    """
    return write_json(path, {c.candidate_id: group for c, group in sample})


def write_precision_sample(
    sample: Sequence[ObligationCandidate], path: Path | str, *, force: bool = False, index_start: int = 1
) -> Path:
    """Write the spot-check CSV. Never silently overwrites filled-in judgments.

    ``data/benchmark/**`` is gitignored, so a hand-filled sample that gets
    overwritten is gone. With ``force`` the old file is copied aside first.
    """
    path = Path(path)
    if sample_has_judgments(path):
        if not force:
            raise SampleOverwriteError(
                f"{path} already holds hand judgments; refusing to overwrite. "
                "Pass --force-resample to redraw (the old file is kept as a .bak copy)."
            )
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAMPLE_COLUMNS)
        writer.writeheader()
        for index, candidate in enumerate(sample, start=index_start):
            writer.writerow({
                "sample_index": index,
                "candidate_id": candidate.candidate_id,
                "entity_class": candidate.entity_class or "",
                "document_id": candidate.document_id,
                "paragraph_id": candidate.paragraph_id,
                "cue_matched": "; ".join(candidate.cue_matched),
                "span_text": candidate.span_text,
                "is_obligation": "",
                "reviewer_note": "",
            })
    tmp.replace(path)
    return path


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default).

    Used instead of the normal approximation because n=40 with p near 0.8 puts
    the normal interval's upper end uncomfortably close to 1.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def score_precision_sample(rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Precision from the hand-filled sample, with the raw counts shown.

    Precision is only reported once every row is judged. A partly-filled
    sample reports its counts and NOT YET MEASURED, never an extrapolation.
    """
    yes = no = blank = 0
    unreadable: list[str] = []
    for row in rows:
        value = (row.get("is_obligation") or "").strip().lower()
        if not value:
            blank += 1
        elif value in SAMPLE_YES:
            yes += 1
        elif value in SAMPLE_NO:
            no += 1
        else:
            unreadable.append(f"{row.get('candidate_id')}: {value!r}")
    judged = yes + no
    complete = blank == 0 and not unreadable and judged > 0
    precision = (yes / judged) if complete else None
    return {
        "sample_size": len(rows),
        "true_obligation": yes,
        "not_obligation": no,
        "unjudged": blank,
        "unreadable": unreadable,
        "precision": precision if complete else "NOT YET MEASURED",
        "wilson_95": list(wilson_interval(yes, judged)) if complete else None,
        "precision_stop_triggered": (precision < PRECISION_STOP_THRESHOLD) if complete else None,
        "entity_classes_in_sample": len({row.get("entity_class") for row in rows}),
    }
