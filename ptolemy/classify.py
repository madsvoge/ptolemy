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
_ISLAND_LIST_RE = re.compile(
    r"\bislands?\b\s*(?:lying\s+|located\s+|lies?\s+)?(?:off|near|around|alongside|above|beyond|in|along|adjoining|on|adjacent(?:\s+to)?)\b"
    r"|\b(?:off|above|near|around|alongside|beyond|along|adjoining|adjacent(?:\s+to)?)\b[^.\n]{0,60}\bislands?\b"
    r"|\bthese\s+are\s+the\s+islands?\b"
    r"|\bthere\s+are\b[^.\n]{0,25}\bislands?\b"
    # "the cities of the [so-called] Cycladic islands" -- an island-group
    # appendix headed by its settlements rather than the bare word
    # "islands" acting as its own subject.
    r"|\bcities?\s+of\s+the\b[^.\n]{0,30}\bislands?\b"
    # Same colon-terminated list-intro convention already exploited for
    # inland/mountain lists ("High seas islands of Africa are the
    # following:") -- catches phrasings where "islands" isn't paired with
    # one of the specific prepositions above. Plural "islands" only: a
    # *list* of several islands is always plural, whereas singular "this
    # island"/"the island" is how Ptolemy refers to the single landmass a
    # coastal-walk or mountain-list section is itself describing (e.g.
    # "the seacoast of this island...:", "the mountains in the island
    # are:") -- those must not flip category just because a colon shows up
    # somewhere later in an unrelated clause.
    r"|\bislands\b[^.\n]{0,80}:",
    re.I,
)

# A single named island's own coastal walk, embedded as an appendix inside
# a shared/mainland book.map (Lesbos in 5.2, Euboia in 3.14, Karpathos in
# 5.2) -- kept as its own pattern, separate from the island *list* intros
# above, because lines.py needs to tell the two apart: a list of several
# distinct islands (Ebuda, the Cyclades, "islands in the Ikarian sea"...)
# must NOT have its points blanket-connected by catalogue-order adjacency
# the way one island's own walk should be (confirmed: doing so for every
# ISLAND-classified section drew nonsense self-intersecting lines across
# unrelated islands cited back to back in the same list).
_NAMED_ISLAND_WALK_RE = re.compile(
    # "island" co-occurring with Ptolemy's own "described/description as
    # follows" list-intro convention in the same lead sentence. That
    # convention alone is not island-specific (plain coastal/boundary
    # sections use it constantly, e.g. "the description of the coast is
    # the following"), so it's only trusted paired with the word
    # "island(s)" already present in the very same lead -- and NOT the
    # similar-looking "with the following description" word order also
    # used to open a single island within a larger list (§3.13.9, Korkyra),
    # which must stay excluded since it's still list-scoped, not its own
    # section.
    r"(?=[^\n]*\bislands?\b)[^\n]*\b(?:described|description)\s+as\s+follows\b"
    # "Description of <Name>[ island]:" as a section's own bare lead, e.g.
    # "Description of Karpathos:" / "Description of Rhodes island:" --
    # distinct from the generic "Description of the west/south/... side:"
    # and "the description of {this side|this boundary|which} is..." coastal
    # conventions (confirmed: every other "description of" in this text
    # is followed by "the"/"this"/"which", never a bare proper noun).
    r"|\bdescription\s+of\s+(?!the\b|this\b|which\b)[A-Za-z][\w\s]{0,30}?:",
    re.I,
)

_ISLAND_RE = re.compile(_ISLAND_LIST_RE.pattern + "|" + _NAMED_ISLAND_WALK_RE.pattern, re.I)

# Same reasoning as islands: a bare "mountain" mention (a boundary marker
# named after a mountain range, e.g. "bounded ... by Adulas mountain") is
# common and must not outrank the boundary/coastal cues it's embedded in.
# The list-introducing form always pairs "mountain(s)" with an adjective
# like named/celebrated/notable, or ends the clause with a colon before
# the enumeration starts.
_MOUNTAIN_RE = re.compile(
    r"\b(?:named|celebrated|notable|noteworthy)\s+mountains?\b"
    r"|\bmountains?\b.{0,15}\b(?:are|called):"
    r"|\bmountains?\s+in\s+this\s+(?:section|region)\b"
    # A bare title like "Mountains in the Peloponnese" -- same
    # list-heading convention as "Mountains in this section:", just
    # naming the region instead of saying "this section".
    r"|^mountains?\s+(?:in|of)\b",
    re.I,
)

# Split into two tiers. The strong tier is unambiguous -- Ptolemy is never
# describing a coastal walk when he uses the word "inland"/"interior", or
# "komai" (Greek villages), or "the interior villages of X". The weak tier
# ("the following cities are:", "Its towns are:") is Ptolemy's own generic
# list-introducing convention, and he reuses that exact phrasing for
# coastal river-mouth lists too (confirmed: Hyrkania's own Caspian-coast
# section opens "In this section are the following cities:" and then
# cites nothing but river mouths) -- so the weak tier is only trusted when
# the section's own points don't already show a stronger coastal signal.
_INLAND_STRONG_RE = re.compile(
    # "inlands cities" (the -s misplaced onto "inland" instead of the noun)
    # is a real transcription slip in this text (confirmed §2.10.6) --
    # tolerate it the same way "villages"/"komai" tolerate Ptolemy's own
    # wording variance.
    r"\binlands?\s+(?:cities|towns|villages)\b"
    r"|\binterior\s+(?:cities|towns|villages)\b"
    r"|\b(?:cities|towns|villages)\s+of\s+the\s+interior\b"
    # "in the interior" and "in the Cretan interior" (a regional adjective
    # inserted between "the" and "interior") -- confirmed §3.15.10,
    # "Cities in the Cretan interior:".
    r"|\bin\s+the\s+(?:[\w-]+\s+)?interior\b"
    r"|\binterior\s+of\b"
    # "komai" (Greek villages) is specific/technical enough a term that it
    # doesn't need a "following/these" wrapper to be a reliable signal on
    # its own -- e.g. "on the west bank of the river are the komai".
    r"|\bkomai\b"
    # "By [part of] the Euphrates river:" -- a river named purely as an
    # orientation landmark for the interior settlement list that follows
    # (confirmed §5.20.6, Babylonia: every city in the list is inland,
    # river mouths/coast are never mentioned). A coastal section never
    # uses a bare "by the X river:" as its own list header -- it always
    # reaches for sea/coast/promontory/mouth-of vocabulary instead -- so
    # this is safe as a strong-tier signal, not just a weak fallback.
    r"|\bby\s+(?:part\s+of\s+)?the\s+[A-Za-z]+\s+river\s*:",
    re.I,
)
_INLAND_WEAK_RE = re.compile(
    r"\b(?:the\s+)?(?:following|these)\s+(?:towns|cities|villages|komai)\b"
    r"|\b(?:towns|cities|villages|komai):"
    r"|\bits\s+towns\s+are\b|\bits\s+cities\s+are\b"
    # "And the cities are these:" / "whose towns are these:" -- the same
    # list-intro convention with subject and predicate swapped (confirmed
    # §7.1.43 and §7.1.65). Without this, a section using this word order
    # had no signal of its own at all and silently inherited whatever
    # coastal/inland type happened to be carried in from far earlier in
    # the book.map.
    r"|\b(?:towns|cities|villages|komai)\s+are\s+(?:these|the\s+following)\b"
    # The same swapped order again, but with the "these"/"the following"
    # qualifier dropped entirely -- "The cities are:", "whose towns are:",
    # "their towns are:" -- confirmed §5.9.16 ("...the Iaxamatai people.
    # The cities are:") and several tribal-town idioms elsewhere ("whose
    # towns are:", "whose cities are:") that don't use "its" the way the
    # two dedicated patterns above already cover.
    r"|\b(?:towns|cities|villages|komai)\s+are:",
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
    # Bare "mouth(s)" catches both word orders ("mouth of the Vidua river"
    # and "Maxeras river mouth", confirmed both used in this text -- see
    # the same word-order tolerance already needed in tag.py's own
    # river-mouth matching).
    r"\bpromontory\b|\bcape\b|\bheadland\b|\bbay\b|\bgulf\b|\bharbou?r\b|\bmouths?\b|\bestuary\b",
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
    phrases = " ".join(c.name_phrase for c in section.citations)
    if _ISLAND_RE.search(lead):
        return ISLAND
    if _MOUNTAIN_RE.search(lead):
        return MOUNTAIN
    if _INLAND_STRONG_RE.search(lead):
        return INLAND
    if _COASTAL_LEAD_RE.search(lead):
        return COASTAL
    weak_inland = bool(_INLAND_WEAK_RE.search(lead))
    if section.citations:
        coastal_hits = sum(1 for c in section.citations if _COASTAL_POINT_RE.search(c.name_phrase))
    else:
        coastal_hits = 0
    if weak_inland:
        # The weak inland tier ("the following towns are:") and coastal
        # point-level cues can both fire on the same section -- e.g. a
        # genuine inland tribal-town list (Britain's Brigantes, 2.3.10)
        # that tacks on one trailing orientation aside mentioning a bay.
        # One incidental coastal word among many plain city names must
        # not flip the whole section; only trust point-level cues over
        # the section's own explicit list header when they're not just
        # incidental -- i.e. at least half the citations carry one
        # (confirmed coastal on this basis: Hyrkania's own river-mouth
        # list, §6.9.2, where nearly every citation is a "river mouth").
        if coastal_hits and coastal_hits >= len(section.citations) / 2:
            return COASTAL
        return INLAND
    if coastal_hits:
        return COASTAL
    if _BOUNDARY_RE.search(lead):
        return BOUNDARY
    return None


# Section keys where Ptolemy's own prose gives the classifier no textual
# signal to read -- or actively points the wrong way -- confirmed only by
# checking the citations against outside knowledge of the region, not
# something a text-only rule can ever detect on its own. Applied as the
# very last step of classify_sections(), after every automatic
# signal/inheritance rule has already run, specifically so a later
# automatic pass can never silently reclassify one of these out from under
# a documented, deliberate correction. Each entry keeps its own note
# explaining the evidence, since "why was this overridden" isn't
# recoverable from the text the way every other classification decision
# in this module is.
SECTION_OVERRIDES: dict[str, tuple[str, str]] = {
    "7.1.95": (
        ISLAND,
        "Ptolemy's own lead calls this \"the line of coast\", but several of "
        "its citations (Heptanesia -- literally \"Seven Islands\" in Greek "
        "-- Trikadiba, Peperine, Trinesia, Nanigeris) are historically "
        "identified as an island group off India's coast, not a coastal "
        "walk. Nothing in the section's own prose distinguishes it from an "
        "ordinary coastal section, so this can't be reached by a general "
        "text rule; confirmed by manual review only.",
    ),
    "4.6.24": (
        INLAND,
        "Own lead reads \"...in the coastal section, as follows:\", which "
        "reads as Ptolemy's own administrative label for a named district, "
        "not a declared coastal walk -- \"coastal\" here doesn't even match "
        "the classifier's own coast-word check (it needs the standalone "
        "word \"coast\", not \"coastal\"), so this section had no signal of "
        "its own at all and was silently inheriting a stale 'coastal' type "
        "carried from an unrelated, zero-citation tribal-ethnography aside "
        "eight sections earlier (§4.6.17, 'the smaller ethnic groups... "
        "occupy the coast') that has nothing to do with these particular "
        "cities. Its own coordinates (23°50'N down to 12°15'N, a "
        "north-south desert corridor) match the 'Interior of Libya' framing "
        "given for the whole book.map at §4.6.1, not any real coastline; "
        "confirmed by manual review only.",
    ),
}


def override_note(key: str) -> str | None:
    """The documented reason a section's type was manually overridden, or
    None if it wasn't."""
    entry = SECTION_OVERRIDES.get(key)
    return entry[1] if entry else None


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

    # Manual overrides are applied last and don't feed back into the
    # inheritance chain above: a section right after an overridden one
    # that has no signal of its own should still inherit whatever type was
    # actually carried by the text (e.g. §7.1.96 correctly continues
    # §7.1.95's original coastal walk rather than inheriting the island
    # override) -- the override corrects that one section's own type, not
    # the whole downstream chain.
    for key, (rtype, _note) in SECTION_OVERRIDES.items():
        if key in resolved:
            resolved[key] = rtype

    return resolved


def is_named_island_walk(section: Section) -> bool:
    """True for a section that is one named island's own coastal walk
    (Lesbos, Euboia, Karpathos...), as opposed to a section that lists
    several distinct islands together (Ebuda, the Cyclades...). Only
    meaningful for a section already resolved to ISLAND; lines.py uses
    this to decide which island sections it's safe to connect by
    catalogue-order adjacency (see build_island_walks).
    """
    return bool(_NAMED_ISLAND_WALK_RE.search(section.lead_text))
