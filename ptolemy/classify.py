"""Step 2: classify each section's own narrative type from its own prose,
per the priority order given in the mission brief. Ptolemy tells you
directly what a section is -- these regexes exist to read that statement,
not to substitute a keyword guess for it.
"""
from __future__ import annotations

import re

from .parser import Section

ISLAND = "island"
MOUNTAIN = "mountain"
INLAND = "inland"
COASTAL = "coastal"
BOUNDARY = "boundary"

# NB: bare "island" is deliberately NOT a signal on its own -- Ptolemy
# opens the coastal walk of every insular region (Ireland, Britain,
# Corsica, Sardinia, Sicily...) with a line like "Setting of Hivernia
# British island" or "Kyrnos island...is surrounded on the west", and a
# bare-keyword match would misfire on every single one of those, wrongly
# outranking the coastal-walk cue that immediately follows. The real
# signal in this text is the word "island(s)" acting as the *subject of a
# list-introducing clause* alongside a locative preposition ("lying off",
# "near", "around", ...), confirmed empirically against ~80 lead_texts
# containing "island" in books 2-7 (see repo notes / commit history).
_ISLAND_RE = re.compile(
    r"\bislands?\b\s*(?:lying\s+|located\s+|lies?\s+)?(?:off|near|around|alongside|above|beyond)\b"
    r"|\b(?:off|above|near|around|alongside|beyond)\b[^.\n]{0,60}\bislands?\b"
    r"|\bthese\s+are\s+the\s+islands?\b"
    r"|\bthere\s+are\b[^.\n]{0,25}\bislands?\b"
    # "the cities of the [so-called] Cycladic islands" -- an island-group
    # appendix headed by its settlements rather than the bare word
    # "islands" acting as its own subject.
    r"|\bcities?\s+of\s+the\b[^.\n]{0,30}\bislands?\b",
    re.I,
)

# Same reasoning as islands: a bare "mountain" mention (a boundary marker
# named after a mountain range, e.g. "bounded ... by Adulas mountain") is
# common and must not outrank the boundary/coastal cues it's embedded in.
# The list-introducing form always pairs "mountain(s)" with an adjective
# like named/celebrated/notable, or ends the clause with a colon before
# the enumeration starts.
_MOUNTAIN_RE = re.compile(
    r"\b(?:named|celebrated|notable)\s+mountains?\b"
    r"|\bmountains?\b.{0,15}\b(?:are|called):"
    r"|\bmountains?\s+in\s+this\s+(?:section|region)\b"
    # A bare title like "Mountains in the Peloponnese" -- same
    # list-heading convention as "Mountains in this section:", just
    # naming the region instead of saying "this section".
    r"|^mountains?\s+(?:in|of)\b",
    re.I,
)

_INLAND_RE = re.compile(
    r"\binland\s+(?:cities|towns)\b"
    r"|\binterior\s+(?:cities|towns)\b"
    r"|\bcities?\s+of\s+the\s+interior\b"
    r"|\bin\s+the\s+interior\b"
    r"|\binterior\s+of\b"
    # Ptolemy names a tribe's own settlements with a colon-terminated
    # "(the following|these) (towns|cities):" intro just as often as he
    # uses the literal word "inland" -- this is the same list-introducing
    # convention as the named-mountain-list cue above, just for
    # settlements, and it recurs constantly interleaved *within* an
    # otherwise coastal walk (confirmed empirically: ~30 of these carry no
    # other signal and would otherwise wrongly inherit whatever type came
    # before them).
    r"|\b(?:the\s+)?(?:following|these)\s+(?:towns|cities)\b"
    r"|\b(?:towns|cities):",
    re.I,
)

_COASTAL_LEAD_RE = re.compile(
    r"\bsea\s*coast\b"
    r"|\bdescription\s+of\s+the\s+coast\b"
    r"|\bshores?\s+of\b"
    r"|\bon\s+the\b[^.\n]{0,20}\bsea\b"
    r"|\bcoast\b",
    re.I,
)
_COASTAL_POINT_RE = re.compile(
    r"\bpromontory\b|\bcape\b|\bheadland\b|\bbay\b|\bgulf\b|\bharbou?r\b|\bmouth\s+of\b|\bestuary\b",
    re.I,
)

_BOUNDARY_RE = re.compile(
    r"\bbounded\b|\bbordered\b"
    r"|\bextends?\s+to\b"
    r"|\bthe\s+limit\s+of\b",
    re.I,
)


def _own_signal(section: Section) -> str | None:
    """The type this section's own prose declares, if any (no inheritance).

    Island and named-mountain-list intros are always structural, lead-in
    prose ("The named mountains in X are...", "Islands lying off Y are...")
    -- so they're checked against lead_text only. Checking them against
    every point's own name phrase too would let one stray citation (e.g. a
    single island tacked onto the end of an otherwise pure mountain list)
    outrank the section's own, explicit, structurally-clear lead sentence.
    Coastal is the one category whose own definition (per the brief)
    includes point-level cues -- promontory/cape/mouth-of/... -- since
    those words only make sense describing a shore, so it consults point
    phrases as first-class signal, not a fallback.
    """
    lead = section.lead_text
    if _ISLAND_RE.search(lead):
        return ISLAND
    if _MOUNTAIN_RE.search(lead):
        return MOUNTAIN
    if _INLAND_RE.search(lead):
        return INLAND
    phrases = " ".join(c.name_phrase for c in section.citations)
    if _COASTAL_LEAD_RE.search(lead) or _COASTAL_POINT_RE.search(phrases):
        return COASTAL
    if _BOUNDARY_RE.search(lead):
        return BOUNDARY
    return None


def classify_sections(sections: list[Section]) -> dict[str, str]:
    """Return {section.key: resolved_type}, in document order.

    A section with no signal of its own inherits the previous section's
    resolved type, scoped to the same book.map -- but never inherits INTO
    island/mountain: those are always their own explicitly-marked
    appendix, so a no-signal continuation skips past them to the last
    resolved coastal/inland/boundary type instead.
    """
    resolved: dict[str, str] = {}
    last_type: dict[str, str] = {}          # book.map -> most recent resolved type
    last_carryable: dict[str, str] = {}     # book.map -> most recent non-island/mountain type

    for section in sections:
        bm = section.book_map
        own = _own_signal(section)
        if own is not None:
            rtype = own
        else:
            rtype = last_carryable.get(bm)
            if rtype is None:
                rtype = COASTAL  # first section in a book.map with no signal: default to coastal walk

        resolved[section.key] = rtype
        last_type[bm] = rtype
        if rtype not in (ISLAND, MOUNTAIN):
            last_carryable[bm] = rtype

    return resolved
