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
# "Description of <Name>[ island]:" as a section's own bare lead, e.g.
# "Description of Karpathos:" / "Description of Rhodes island:" --
# distinct from the generic "Description of the west/south/... side:" and
# "the description of {this side|this boundary|which} is..." coastal
# conventions (confirmed: every other "description of" in this text is
# followed by "the"/"this"/"which", never a bare proper noun). Also used,
# via starts_new_named_island below, to catch a *second* such heading
# appearing mid-section rather than in the lead -- Ptolemy sometimes packs
# more than one named island's own walk into a single §-numbered section
# (confirmed §5.2.33: "Description of Karpathos:" immediately followed,
# after Karpathos's own points, by "Description of Rhodes island:" and
# Rhodes's).
_ISLAND_SUBHEADING_RE = re.compile(
    r"\bdescription\s+of\s+(?!the\b|this\b|which\b)[A-Za-z][\w\s]{0,30}?:",
    re.I,
)

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
    r"|" + _ISLAND_SUBHEADING_RE.pattern,
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
    r"|^mountains?\s+(?:in|of)\b"
    # "The extremes of the Hippika mountains are at COORD and COORD" --
    # confirmed §5.9.15, a whole list of ranges each cited by name plus
    # its own two extremity coordinates. Narrow window (15 chars) so this
    # doesn't fire on an unrelated "mountains...are at" many words later
    # in a long boundary sentence (confirmed distinct from §4.5.19's "the
    # Libyan mountains..., the end points of which are at", which stays
    # boundary/coastal as intended).
    r"|\bmountains?\b.{0,15}\bare\s+at\b"
    # "The mountains in this division are thus named:—" (confirmed
    # §7.2.8) -- the same list-intro convention as "...are called:", just
    # with "named" and enough words in between that the 15-char window
    # above doesn't reach it. "thus named" is rare and specific enough in
    # this text (2 uses total, the other about cities not mountains) that
    # requiring only "mountains" anywhere earlier in the same line is safe.
    r"|\bmountains?\b[^.\n]*\bthus\s+named\b",
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
    # "These are the cities and villages of inland Karmania:" (confirmed
    # §6.8.13) / "Of inland Corinthia" (§3.14.38) -- the adjective
    # "inland" modifying the *region's own name* rather than sitting
    # directly before "cities/towns/villages" the way the first
    # alternative above requires.
    r"|\b(?:cities|towns|villages)\s+of\s+inland\b|^of\s+inland\b"
    # "komai" (Greek villages) is specific/technical enough a term that it
    # doesn't need a "following/these" wrapper to be a reliable signal on
    # its own -- e.g. "on the west bank of the river are the komai".
    r"|\bkomai\b"
    # "Cities in the hinterland of Epiros:" (confirmed §3.13.5) -- the
    # same "cities/towns/villages of the interior" idiom, just with
    # "hinterland" instead of "interior". Without this, the section had no
    # signal of its own (neither tier matched "hinterland", and it doesn't
    # open with "the following"/"these" the way the weak tier requires) and
    # silently inherited COASTAL from the preceding coastal-walk section,
    # pulling a whole list of interior Epirote towns into that book.map's
    # coastline trail as if they were shore citations (confirmed: this
    # alone produced 11 of coastline-3.13-1's self-crossings).
    r"|\b(?:cities|towns|villages)\s+(?:in|of)\s+the\s+hinterland\b"
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
    # two dedicated patterns above already cover. A short qualifier phrase
    # can sit between the noun and "are:" too -- "Cities on the Euphrates
    # are:" (confirmed §5.7.2, which had no signal of its own at all and
    # fell through to a stale inherited COASTAL type without this) --
    # bounded so it doesn't reach across an unrelated sentence boundary.
    r"|\b(?:towns|cities|villages|komai)\b[^.\n:]{0,50}\bare:",
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

# A region's own opening position/boundary statement (confirmed §2.5.1,
# "LUSITANIA\nThe southern side of Lusitania is the common boundary with
# the northern side of Baetica...") using the bare noun "boundary" instead
# of one of the passive verb forms _BOUNDARY_RE above already covers.
# Checked ahead of the coastal point-cue fallback in _own_signal (unlike
# _BOUNDARY_RE itself, which is only a last-resort check there) because
# this idiom's own citations routinely restate a river's mouth as the
# boundary line's own starting landmark, which is exactly the kind of
# point-level "mouth" cue that fallback exists to catch -- and here it's
# the wrong signal: the same coordinate is cited again, correctly, as the
# region's real coastal walk's own endpoint later in the book.map
# (confirmed: Dourius river mouth, restated in 2.5.1's boundary
# declaration and again as Lusitania's actual coastal walk's last point in
# 2.5.3 -- one dedup'd Point that would otherwise carry a stray early
# occurrence in the drawn coastline).
_BOUNDARY_LEAD_RE = re.compile(
    r"\bcommon\s+boundary\b|\bis\s+the\s+boundary\b",
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
    if _INLAND_STRONG_RE.search(lead):
        return INLAND
    if _COASTAL_LEAD_RE.search(lead):
        return COASTAL
    if _BOUNDARY_LEAD_RE.search(lead):
        return BOUNDARY
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
    # A region's own opening boundary declaration is routinely its
    # section's *only* citation, restating the boundary line's own
    # endpoint (a river mouth, a gulf, a sea) as the coordinate --
    # confirmed §5.20.1, Babylonia: "...on the east by Susiana along the
    # remaining parts of the Tigris river as far as its outflows into the
    # Persian Gulf at COORD" is one citation, matching _BOUNDARY_RE
    # ("bounded... by...") and _COASTAL_POINT_RE ("gulf") both at once --
    # and the coastal_hits check below, being checked first, otherwise
    # always wins. Scoped tightly to a *single*-citation section: once a
    # section goes on to cite several more, real coastal points (confirmed
    # distinct from this, e.g. §2.7.1, §3.5.1: a boundary-declaration lead
    # followed by a genuine multi-point coastal walk), this section-wide
    # override would wrongly swallow them too.
    if len(section.citations) == 1 and _BOUNDARY_RE.search(lead):
        return BOUNDARY
    if coastal_hits:
        return COASTAL
    if _BOUNDARY_RE.search(lead):
        return BOUNDARY
    # A section can open with a boundary-line citation whose own lead
    # doesn't reach "bounded"/"bordered" yet (confirmed §5.2.12: "On the
    # east by Lykia, from the point after Kaunos to COORD" -- the word
    # "bounded" only shows up in the *next* citation, "...it is bounded by
    # Milyas..."). With zero coastal_hits already established above (no
    # citation in this section names a promontory/cape/mouth/... either),
    # a boundary word anywhere in the section's own citations is as
    # trustworthy a last-resort signal as the lead-only check just above,
    # and without it this fell through to a stale inherited COASTAL type
    # from the unrelated coastal section before it.
    if section.citations and any(_BOUNDARY_RE.search(c.name_phrase) for c in section.citations):
        return BOUNDARY
    return None


def classify_sections(sections: list[Section]) -> dict[str, str]:
    """Return {section.key: resolved_type}, in document order, from the
    text alone -- no manual judgment applied here. A section with no
    signal of its own inherits the previous section's resolved type,
    scoped to the same book.map -- but never inherits INTO island/
    mountain: those are always their own explicitly-marked appendix, so a
    no-signal continuation skips past them to the last resolved coastal/
    inland/boundary type instead.

    Cases where the text genuinely gives no usable signal (or points the
    wrong way) are not handled here: see ptolemy.overrides.
    apply_section_overrides, a small git-committed CSV of curator
    judgment applied as an explicit, separate pipeline step -- kept out of
    this function so classify_sections stays a pure function of the
    source text, and a manual correction never requires touching this
    module or its tests.
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


def is_named_island_walk(section: Section) -> bool:
    """True for a section that is one named island's own coastal walk
    (Lesbos, Euboia, Karpathos...), as opposed to a section that lists
    several distinct islands together (Ebuda, the Cyclades...). Only
    meaningful for a section already resolved to ISLAND; lines.py uses
    this to decide which island sections it's safe to connect by
    catalogue-order adjacency (see build_island_walks).
    """
    return bool(_NAMED_ISLAND_WALK_RE.search(section.lead_text))


def starts_new_named_island(name_phrase: str) -> bool:
    """True if a citation's own name_phrase opens with a fresh 'Description
    of <Name>:' sub-heading. parser.extract_citations pulls a short bare
    heading line into the *next* citation's own phrase rather than
    dropping it (see its docstring) -- this is how a second named island's
    walk, packed into the same §-numbered section as the first, becomes
    detectable at all. build_island_walks uses this to start a fresh trail
    instead of connecting the new island's points onto the previous one's.
    """
    return bool(_ISLAND_SUBHEADING_RE.search(name_phrase))


# Ptolemy's own convention for opening a named region's boundary
# declaration ("Position of Epiros...", "Position of the Peloponnesos...")
# -- almost always a book.map's own first section, where it needs no
# special handling (dedup/line-building are already scoped per book.map).
# The one confirmed exception is §3.14.25, "Position of the Peloponnesos",
# appearing *mid* book.map 3.14: Ptolemy's own Achaia map covers both
# mainland Greece and the separate Peloponnese peninsula as one catalogue
# unit, so nothing about book.map scoping keeps their two, only-narrowly-
# connected coastlines apart. lines.py uses this to force a hard break
# in the coastal-walk stream there, rather than let greedy distance-based
# stitching treat both as one continuous (and, worse, spuriously
# self-closing -- confirmed connecting Achaia's own mainland starting
# point back to the Peloponnese's own last point) trail.
_NEW_REGION_LEAD_RE = re.compile(r"^position\s+of\b", re.I)

# The same "hard break, don't stitch across this" signal, but for a new
# *coastal side* of the same region rather than a whole new region --
# "On the north it is bounded by a part of the Euxine Pontos, which is
# thus described: after the mouth of the Pontos and the sanctuary of
# Artemis..." (confirmed §5.1.5, Bithynia). Bithynia's own coast runs two
# separate directions from the same Bosporos-mouth starting point (west
# along the Propontis/gulf side, §5.1.2-5.1.4; north along the Black Sea
# side, §5.1.5-5.1.7) -- the second arc's own lead restates that shared
# starting landmark ("the sanctuary of Artemis", already cited as "Hieron
# of Artemis" in §5.1.2) purely for orientation, the same hand-off idiom
# as "Position of X", just without a fresh citation of its own attached
# to it. Without the split, the Propontis arc's own end (inland, up the
# Ryndakos river to its sources) connected directly to the Black Sea arc's
# start (confirmed P3523/P3525), a nonsensical jump across the whole
# Bithynian peninsula.
_NEW_COASTAL_SIDE_LEAD_RE = re.compile(r"\bwhich\s+is\s+thus\s+described\s*:\s*after\b", re.I)


def is_new_region_declaration(section: Section) -> bool:
    return bool(_NEW_REGION_LEAD_RE.search(section.lead_text)) or bool(_NEW_COASTAL_SIDE_LEAD_RE.search(section.lead_text))


# A third variant of the same hand-off idiom, except this one sits inside
# a *citation's own name_phrase* rather than a section's lead_text --
# "...by the onward shores of Pontos until the border with lower Moesia,
# at [COORD]" (confirmed §3.11.3, Thrace; also §3.10.3's own symmetric
# "...as far as the limit point toward Thrace, at COORD", the same shared
# boundary landmark cited from Lower Moesia's own side). Thrace's coast,
# like Bithynia's, runs two separate directions from its Bosporos-mouth
# boundary -- but unlike Bithynia's restated hand-off, this citation's own
# coordinate genuinely *is* the boundary landmark itself, immediately
# followed by the new arc's real points (confirmed §3.11.3: this citation
# is only ~0.3 degrees from Mesembria, the very next citation -- nowhere
# near the "far away, self-intersecting jump" its coordinate would suggest
# if left connected *backward* to whatever preceded it instead). So this
# citation stays a real point in the walk (unlike Bithynia's or the
# Peloponnese's own pure-orientation restatements, which carry no fresh
# waypoint of their own) -- it just needs to open a fresh segment rather
# than close out the old one, or the point right before it in document
# order (confirmed P1972) stitched straight across the whole peninsula to
# reach it.
_NEW_COASTAL_ARC_PHRASE_RE = re.compile(r"\buntil\s+the\s+border\s+with\b|\bthe\s+limit\s+point\s+toward\b", re.I)


def starts_new_coastal_arc(name_phrase: str) -> bool:
    return bool(_NEW_COASTAL_ARC_PHRASE_RE.search(name_phrase))


# A section can introduce a plain list of cities/towns that carries no
# river vocabulary of its own in any individual citation, but whose own
# lead explicitly says they sit along a named river -- "The following
# cities are along the Danube river:" (confirmed §3.10.5), "The towns in
# Vindelicia along the Danube are:" (§2.12.4), "the inland cities on that
# side are, along the Hierasos river," (§3.10.8). Point-level river
# detection (lines.river_base_names) can never catch these: a bare city
# name like "Bragodurum" mentions no river at all. lines.py uses this to
# fold such a section's points into that river's own line as real
# waypoints anyway -- the same reasoning tag.py's harbor/river_mouth
# already use for a coastal walk (a point sitting *on* a linear feature
# is part of that feature, whatever its own citation happens to say).
# Deliberately keeps "along" itself scoped to this exact list-intro
# shape, not stripped as generic noise -- "bounded... along the river
# Liger until it turns southwards" (a boundary line's own endpoint, not a
# city list) uses the same word for a different, unrelated purpose.
_RIVER_BANK_CITY_ALONG_RE = re.compile(r"\balong\s+(?:the\s+)?(?:river\s+)?((?-i:[A-Z])\w*)", re.I)
_RIVER_BANK_CITY_NOUN_RE = re.compile(r"\b(?:cities|towns)\b", re.I)
_ARE_RE = re.compile(r"\bare\b", re.I)
# "The inland towns and villages of this division, in addition to those
# mentioned along the Ganges are called:—" (confirmed §7.2.22) -- reads
# like a match (towns...along the Ganges...are), but "in addition to"
# says the opposite: *these* towns are explicitly the ones *not* already
# covered by the along-the-river list mentioned earlier; "along the
# Ganges" describes that earlier, different group, not this one.
_RIVER_BANK_CITY_EXCLUDE_RE = re.compile(r"\bin\s+addition\s+to\b", re.I)


def river_bank_city_lead_name(section: Section) -> str | None:
    lead = section.lead_text
    if _RIVER_BANK_CITY_EXCLUDE_RE.search(lead):
        return None
    along_match = _RIVER_BANK_CITY_ALONG_RE.search(lead)
    if not along_match:
        return None
    # "cities"/"towns" must be the sentence's own subject governing "are"
    # -- i.e. appear *before* it -- not just present somewhere nearby.
    # Confirmed §2.9.10: "are the Helveti along the River Rhine, with
    # cities Ganodurum" has both words, but in the wrong order/role ("are"
    # governs the tribe; "cities" is a later, unrelated aside naming that
    # tribe's own towns, which this text does not claim sit in any
    # particular order along the river). Connecting that section's points
    # as if they were a real river-walk produced a genuine self-crossing
    # (confirmed) -- every real "cities ... are ... along the river" list
    # header, by contrast, always has the noun before the copula.
    noun_match = _RIVER_BANK_CITY_NOUN_RE.search(lead)
    are_match = _ARE_RE.search(lead)
    if not noun_match or not are_match or noun_match.start() > are_match.start():
        return None
    return along_match.group(1)
