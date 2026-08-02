"""Step 3: tag every canonical Point with its own category label(s).

Primary signal is the point's own name text; the section's resolved
narrative type (Step 2) both feeds two of the checks directly (island,
mountain) and supplies the coastal-walk fallback. Checked in priority
order, first match wins for the point's primary tag -- except where the
text itself genuinely gives a point more than one real role (a river
mouth sitting in a coastal walk is also a step in the coastline; a point
cited in a boundary/orientation section is whatever its own name says,
*plus* a boundary marker).
"""
from __future__ import annotations

import re

from .classify import BOUNDARY, COASTAL, ISLAND, MOUNTAIN
from .points import Point, TRIBAL_CITY_BARE_RE, TRIBAL_CITY_RE

_ISLAND_NAME_RE = re.compile(r"\bisland", re.I)
# "Mt." (with or without the period) is this text's dominant way of citing
# a single named peak/range, at least as common as spelling out "mount".
_MOUNTAIN_NAME_RE = re.compile(r"\bmounts?\b|\bmountain|\bmt\.?\s", re.I)
# "Mouth(s) of" is the dominant form, but a distributary's own name is
# often given as "the X Mouth" (a proper noun in its own right, e.g. "the
# Kambyson Mouth") with no "of" at all -- and the plural "Mouths of the
# river X" (a delta with more than one outlet) was being missed entirely
# by a singular-only "mouth of". Except "mouth of Pontos": Pontos is the
# Black Sea itself, not a river, and this idiom for the Bosporos strait
# recurs 3 times in the text -- twice as a *restated boundary/reference
# point* shared between two different regions' descriptions ("the mouth of
# Pontos...at 55°00'.44°40'", cited identically in both §3.10.3's "limit
# point toward Thrace" and §3.11.3's "until the border with lower Moesia"),
# and only once as a real coastal waypoint (Byzantion). Matching the bare
# word there wrongly gave the two boundary restatements a "river_mouth"
# primary tag, which took priority over _REFERENCE_MARKER_RE ever being
# consulted and pulled them into the coastal walk as if they were fresh,
# adjacent waypoints -- confirmed self-intersecting the drawn Thracian
# coastline. Byzantion doesn't need the river_mouth tag to be recognized as
# coastal anyway: it falls through to the plain coastal-section default.
_RIVER_MOUTH_RE = re.compile(
    r"\bmouths?\s+of\b(?!\s+Pontos\b)|\bmouths?\b(?!\s+of\s+Pontos\b)|\bestuary\b|\boutlet\b",
    re.I,
)
_RIVER_RE = re.compile(
    r"\bsources?\b|\bsprings?\b|\bbends?\b|\bconfluence\b|\bforks?\b|\bbranch\w*\b"
    r"|\bjunctions?\b|\bbifurcat\w*\b|\bunites?\b|\bunion\b"
    # "flows into", "joins (with)", "splits into" -- a tributary meeting or
    # leaving its main river, and "turn(s)"/"bend(s)" of *the river*
    # specifically (as opposed to an ambiguous bare "turn towards the
    # east", handled separately below via its neighbours in the stream).
    r"|\bflows?\s+into\b|\bjoins?\b|\bsplits?\s+into\b"
    # "From the Sagapa into the Indus", "from the Ganges into the
    # Kambyson" -- a delta distributary named by its own two endpoints,
    # without repeating "branch"/"mouth" the way its own sibling citations
    # in the same list do (confirmed §7.1.28's Indus delta and §7.1.29-30's
    # Ganges delta). Two capitalized names either side of "into" is what
    # distinguishes this from an unrelated boundary-description "from X to
    # Y" (that idiom never uses "into", only "to").
    r"|\bfrom\s+the\s+[A-Z]\w*\s+into\s+the\s+[A-Z]\w*\b"
    # "The one through Babylon connects at COORD" -- another river-joining
    # synonym (confirmed §5.20.2, a tributary of the Euphrates). Deliberately
    # "connects at" specifically, not bare "connects?": "connect" alone has
    # an unrelated administrative sense elsewhere in this text ("The sides
    # of Lugdunensis which connect to Aquitania..."), and only the
    # coordinate-anchored "at" form is this river-joining idiom.
    r"|\bconnects?\s+at\b"
    r"|\briver\b[^.\n]{0,25}\bturns?\b|\bturns?\b[^.\n]{0,25}\briver\b"
    r"|\bturn\s+of\s+the\s+river\b"
    # "Beginning of the river" / "Head of the river" -- both confirmed
    # (Peloponnese: Eurotas's and Inachos's own sources) as this text's
    # other synonyms for a river's source, cited right after that same
    # river's own mouth/outlet.
    r"|\bbeginning\s+of\s+(?:the\s+)?river\b|\bhead\s+of\s+(?:the\s+)?river\b"
    # "The Peneios river from Mt. Pindos at position..." / "the Spercheios
    # river similarly at position..." -- a river's source given by naming
    # the mountain it rises from (or anaphorically restating that same
    # template for the next river). The window allows a period so an
    # embedded "Mt." abbreviation doesn't cut it short.
    r"|\briver\b[^\n]{0,30}\bat\s+position\b"
    # Other verbs this text uses for the same "river originates at/flows
    # from a named mountain" idiom: "the Strymon river begins from the
    # mountains..." (§3.12.15), "Mt. Thammes, from which the Rubricatus
    # river flows" / "...mountain, from which flow the Salathus river, the
    # Massa river..." (confirmed throughout book 4.6's Libyan river
    # catalogue), "the Nigeir river itself links Mandron mountain and
    # Thala mountain" (§4.6, a river given by the two mountains it
    # connects rather than a single source), "the Melas river flows to
    # meet the river Euphrates" (§5.6), and the bare "The Axios river from
    # Mt. Skardos at <coord>" (§3.12.15) with no verb at all.
    r"|\bbegins?\s+(?:from|in|at)\b|\bfrom\s+which\s+(?:it\s+)?flows?\b"
    r"|\bflows?\s+(?:from|to\s+meet)\b|\briver\s+from\s+(?:mt\.?|mounta?in\w*)\b"
    # "links" alone has an unrelated administrative sense elsewhere in this
    # text ("The northern side links to Tarraconensis..."), same reasoning
    # as "connects at" above -- only trusted here when "river" itself sits
    # nearby (confirmed §4.6.14: "the Nigeir river itself links Mandron
    # mountain and Thala mountain").
    r"|\briver\b[^.\n]{0,30}\blinks?\b|\blinks?\b[^.\n]{0,30}\briver\b"
    # "Mid-point of its length" / "Mid–point of the length of the river"
    # (referring anaphorically, or by full restatement, to a river cited
    # nearby) is this text's own way of citing a point partway along a
    # river's course, alongside its mouth and source. The separator
    # between "mid" and "point" varies (hyphen, en dash, space).
    r"|\bmid.{0,2}points?\s+of\s+(?:its|the)\s+length\b"
    # "The part of the river where Lusitania begins", "Where the river
    # touches the border of Lusitania" -- a boundary line that runs along a
    # named river (Ana, Dourius) is traced waypoint by waypoint the same
    # way a coastal walk is, but these particular waypoints don't repeat
    # any of the specific river verbs above -- they just say "the river"
    # plainly, as the sentence's own subject. Confirmed §2.4.2 and §2.5.1:
    # each is one step in a mouth-to-source river-boundary chain (mouth,
    # then this, then sources), and without a keyword of its own this
    # fell through to the plain coastal-section default. Narrow enough not
    # to catch a real coastal city that merely mentions a nearby river in
    # passing (e.g. "Pitane; the river Euenos flows around it") -- those
    # name a place first, they don't open with "the river" as the subject.
    r"|\bpart\s+of\s+the\s+river\b|\bwhere\s+the\s+river\b|\briver\b[^.\n]{0,25}\btouches?\b|\btouches?\b[^.\n]{0,25}\briver\b",
    re.I,
)
# A handful of *generic, name-free* positional clauses Ptolemy uses to cite
# a point along a river's course without repeating any river keyword at
# all, relying purely on the reader following the sequence: "The turn
# towards the east", "Point at which it crosses over to X", "The next
# point below this", "second turn", "point where it turns". Deliberately
# an allowlist of confirmed phrasings, not a general "lacks a proper noun"
# heuristic -- a real city name (Genua, Ostia, Sidon, ...) must never match
# this, since it sits right next to real river mouths constantly in an
# ordinary coastal walk.
_GENERIC_RIVER_POSITION_RE = re.compile(
    r"^(?:the\s+)?(?:next\s+)?point\s+(?:at\s+which|where|below|above)\b"
    r"|^(?:the\s+)?turn(?:s|ing)?\s+(?:towards?|to)\s+the\s+(?:north|south|east|west)\b"
    r"|^(?:the\s+)?(?:first|second|third|fourth|fifth|\d+(?:st|nd|rd|th))\s+turn\b",
    re.I,
)
_HARBOR_RE = re.compile(r"\bharbou?r\b|\bport\b", re.I)
_COAST_NAME_RE = re.compile(r"\bpromontory\b|\bcape\b|\bheadland\b|\bbay\b|\bgulf\b", re.I)
# Plural: "The more western of the lakes", "in it these lakes: Tritonitis".
_LAKE_RE = re.compile(r"\blakes?\b", re.I)
# Ptolemy routinely folds a tribe's capital into an otherwise coastal
# section ("The Caletes occupy the northern coast...their city is
# Iuliobona", "...the Osismi whose city is Vorgum", "Near which on the
# Opportunum bay are the Parisi and the town Petuaria") -- this idiom
# recurs throughout the catalogue, using "town" exactly as often as "city"
# (confirmed: Britain's own tribal lists, 2.3.9-2.3.11, and Egypt's nome
# capitals, 4.5.55, both use "the town X"/"whose town is X"). Such a city
# is not itself a waypoint on the coastal walk (it can sit well inland of
# the stretch it's attached to, breaking catalogue-order adjacency badly
# enough to self-intersect the drawn coastline -- confirmed on 2.8.5/2.8.6),
# so it must be recognized and tagged 'city' regardless of whether the same
# restated sentence also happens to name a coastal landmark in passing
# ("up to the Gabaeum promontory, the Osismi whose city is Vorgum" --
# confirmed the promontory mention alone otherwise outranked this check
# entirely, since it used to only run as a last-resort fallback after
# every explicit_checks entry, including the bare _COAST_NAME_RE match, had
# already failed to fire). Imported from points.py, not redefined here,
# since points.trim_name needs the very same marker to recover the city's
# own bare name out of the same restated sentence (confirmed §2.9.7) -- see
# TRIBAL_CITY_RE/TRIBAL_CITY_BARE_RE in the import block above.
# A boundary/orientation aside can land inside an otherwise coastal
# section too (Ptolemy occasionally re-cites a "limit point" or "extreme
# point already mentioned" mid-walk to tie the coast back to a boundary
# he stated earlier) -- these are reference markers, not fresh waypoints,
# and forcing them into the coastal walk creates exactly the kind of
# backtracking jump that self-intersects the drawn line.
_REFERENCE_MARKER_RE = re.compile(
    r"\bextreme\s+points?\b|\bextremity\b|\blimit\s+points?\b|\bend\s+points?\b"
    r"|\balready\s+mentioned\b|\bterminal\s+points?\b|\bterminus\b"
    # "The limit on the side of Kolchis is at COORD" -- another restated
    # boundary-line-endpoint idiom, sibling to "limit point" above but
    # without the word "point" (confirmed §5.9.7, right after "mouth of
    # the Korax river", the boundary's own starting landmark).
    r"|\blimit\s+on\s+the\s+side\s+of\b"
    # "...along the line on this side along Epiros until the end, at
    # position..." -- a boundary line's own endpoint, phrased without any
    # of the "limit/extreme/end point" wording above. Confirmed on
    # Macedonia's southern border (3.12.3): its coordinate sits far from
    # where it's cited in document order (near the walk's actual
    # Thessalian end, cited early as an orientation marker), which is
    # exactly the shape of jump that self-intersects a drawn coastline.
    r"|\buntil\s+the\s+end\b"
    # "...to the part of this line at COORD" -- another restated
    # boundary-line-position idiom, sibling to "limit point of this line
    # at..." (already covered above by "limit points?"). Confirmed
    # §5.17.2, Arabia Petraia's own eastern boundary.
    r"|\bpart\s+of\s+this\s+line\b"
    # Named frontier landmarks Ptolemy uses to mark a boundary line
    # ("The Pillars of Alexander are at...", "The Sarmatian Gates...",
    # "The Albanian Gates...", "The Altars of Caesar...") -- proper nouns,
    # but frontier markers, not coastal capes, and they cluster right
    # alongside mountain-range extremity citations in boundary-heavy
    # sections (confirmed 5.9.15, 3.5.12: "Altars of Alexander"/"Altars of
    # Caesar" both mark the same river-turn boundary point on the Tanais).
    r"|\bgates\b|\bpillars\s+of\b|\baltars\s+of\b"
    # "Along Achaia until the Maliac gulf to the end, position..." -- the
    # same restated boundary-line-endpoint idiom as "until the end" above,
    # just with an extra clause inserted before "the end" (confirmed
    # §3.12.3's own Thessalian/Achaia border, right next to that section's
    # other "until the end" citation).
    r"|\bto\s+the\s+end\b",
    re.I,
)
# A second, *weaker* reference-marker idiom, kept as its own separate
# pattern rather than folded into _REFERENCE_MARKER_RE above: "After the
# Nestos river, which is the border of Thrace..." / "After Pegai in the
# Megarid, which is in the Corinthian gulf..." -- Ptolemy routinely opens
# a new region's coastal description by restating the previous region's
# own last-cited landmark as an orientation hand-off, not a fresh waypoint
# (confirmed §3.12.6 and §3.14.26, and again on Taprobane, §7.4.3: "After
# the North Cape which is situated in..." restates §7.4.2's own single
# citation). The capitalized name right after "after (the)?" is what
# distinguishes this from an ordinary boundary-restatement sentence that
# happens to use "after" as a plain preposition mid-clause (confirmed
# §3.10.7: "...the shore is as follows: after the mouth of the
# Borysthenes, which is at..." -- lowercase "mouth", not a proper noun,
# stays excluded; that citation really is the walk's own first point, not
# a restatement of anything cited earlier) -- but that alone isn't a
# reliable enough signal to also exclude a *first* occurrence outright
# (confirmed §4.5.74: "east of the river after the Lesser Cataract, which
# is at..." matches this same shape but is that citation's own only,
# genuine appearance in book.map 4.5, not a restatement of anything).
# Kept separate from _REFERENCE_MARKER_RE for that reason: unlike every
# pattern above, this one is only trusted by build_coastlines when the
# point it matches has *already* been placed once earlier in the same
# coastal-walk segment (see its own comment) -- and NOT promoted into
# tag_point's explicit_checks the way _REFERENCE_MARKER_RE effectively is
# via the fallback below, since a point's combined `name` joins every
# occurrence's phrase into one string, and doing so cost a point that is
# genuinely coastal at one citation its 'coast' tag entirely just because
# *another* occurrence of the same point matches this idiom (confirmed
# regression on Pegai, P2255).
RESTATED_LANDMARK_RE = re.compile(
    r"\bafter\s+(?:the\s+)?(?-i:[A-Z])[\w\s-]{0,40}?,?\s+which\s+is\b",
    re.I,
)
# "Branch of/from the Indus into the Sagapa mouth" names a distributary
# *joining another named channel upstream in a delta* -- the coordinate is
# an inland branch/fork point, not the actual coastline. Confirmed on the
# Indus (§7.1.28), matching the same delta structure already found on the
# Ganges (§7.1.29-30) and the Nile (§4.5.39-44, "The so-called Great Delta
# begins where the Agathodaimon branches off...", "...river splits into
# the Bousiritikos river...", "...the branching of the Taly river is
# at..."): threading these into the coastal walk alongside the delta's
# real, separately-cited coastal mouths (§7.1.2's "the seven mouths of the
# [river]", §4.5.10's "the seven mouths of the Nile") draws two
# near-parallel tracks along the same stretch of coast ("duplicate
# coastline"). "branch\w*" (not just "branch(es)") catches "branching" too
# -- confirmed §4.5.43, where the exact-word-boundary version missed it.
_DISTRIBUTARY_BRANCH_RE = re.compile(
    r"\bbranch\w*\b|\bsplits?\s+into\b|\bforks?\s+into\b|\bdelta\b", re.I
)


def _last_match_start(pattern: re.Pattern, text: str) -> int:
    matches = list(pattern.finditer(text))
    return matches[-1].start() if matches else -1


def tag_point(point: Point, resolved: dict[str, str]) -> set[str]:
    name = " ".join(point.name_variants)
    section_types = {resolved[o.section_key] for o in point.occurrences}

    # A long boundary-restatement sentence routinely names a river mouth
    # as the orientation landmark a boundary line *starts from*, before
    # going on to give the coordinate of the line's actual endpoint (a
    # "limit point"/"extreme point"/etc.) -- confirmed §4.1.8: "...south
    # from the Malva river mouth to the limit point at COORD". A bare
    # river-mouth keyword match alone can't tell that apart from a
    # citation that's genuinely a river mouth restated *after* an earlier,
    # unrelated reference marker in the same sentence (confirmed just as
    # common, e.g. §5.12.1: "...from the limit point at Iberia to the
    # Hyrkanian sea at the mouth of the Kyros river at COORD", where the
    # coordinate *is* the river mouth). Whichever keyword sits closest to
    # the coordinate that follows -- i.e. is mentioned *last* -- is what
    # the citation is actually about; same "last match wins" principle
    # already used by river_base_name/mountain_base_name for the same
    # reason.
    river_mouth_hit = bool(_RIVER_MOUTH_RE.search(name))
    if river_mouth_hit and _REFERENCE_MARKER_RE.search(name):
        river_mouth_hit = _last_match_start(_RIVER_MOUTH_RE, name) > _last_match_start(_REFERENCE_MARKER_RE, name)

    explicit_checks = [
        ("island", bool(_ISLAND_NAME_RE.search(name)) or ISLAND in section_types),
        ("mountain", bool(_MOUNTAIN_NAME_RE.search(name)) or MOUNTAIN in section_types),
        ("river_mouth", river_mouth_hit),
        ("river", bool(_RIVER_RE.search(name))),
        # Checked ahead of harbor/coast: a tribal-capital restatement
        # ("...up to the Gabaeum promontory, the Osismi whose city is
        # Vorgum") routinely names a coastal landmark in passing on its way
        # to the city it's actually about, and that landmark must not
        # outrank the city idiom just because it happens to be an
        # *explicit_checks* entry checked earlier in list order (confirmed
        # bug on 2.3.10/2.8.5: "bay"/"promontory" elsewhere in the same
        # restated sentence silently won every time, tagging the tribal
        # capital 'coast' instead of 'city'). _REFERENCE_MARKER_RE (the
        # reliable tier -- "limit point", "until the end", "gates",
        # "pillars of"...) is the same class of bug for the same reason
        # (confirmed §3.12.3, P2044: "Along Achaia until the Maliac gulf
        # to the end, position" has "gulf" sitting right there too).
        # RESTATED_LANDMARK_RE (the weaker "after X, which is" tier) is
        # deliberately NOT included here: a point's combined `name` joins
        # *every* occurrence's phrase into one string (see top of this
        # function), and a point can genuinely be a real coastal waypoint
        # at one citation while also being restated via that weaker idiom
        # at another (confirmed regression on Pegai, P2255: promoting it
        # here made its genuine §3.14.6 coastal citation lose the 'coast'
        # tag entirely just because its *other* occurrence, §3.14.26,
        # matches it). build_coastlines' own per-citation phrase check
        # already excludes that specific restated occurrence from the walk
        # without needing the point's aggregate tag to lose 'coast'.
        ("city", bool(TRIBAL_CITY_RE.search(name)) or bool(TRIBAL_CITY_BARE_RE.search(name))
         or bool(_REFERENCE_MARKER_RE.search(name))),
        ("harbor", bool(_HARBOR_RE.search(name))),
        ("coast", bool(_COAST_NAME_RE.search(name))),
        ("lake", bool(_LAKE_RE.search(name))),
    ]
    primary = next((tag for tag, matched in explicit_checks if matched), None)
    if primary is None:
        if RESTATED_LANDMARK_RE.search(name):
            primary = "city"
        elif COASTAL in section_types:
            primary = "coast"
        else:
            primary = "city"
    tags = {primary}

    # A river mouth cited while walking a coast is a real waypoint on that
    # coastline, not just a river feature -- keep both roles. Except a
    # delta *branch* point ("Branch from the Indus into the Sagapa
    # mouth"): its own name says it's an inland distributary junction,
    # not the coastline itself.
    if primary == "river_mouth" and COASTAL in section_types and not _DISTRIBUTARY_BRANCH_RE.search(name):
        tags.add("coast")
    # Same reasoning for a harbor: it's cited as an ordinary waypoint
    # between capes and river mouths in a coastal walk (confirmed
    # §3.4.7-8, Sicily: "Brouka promontory ... Kaukana harbor ... Motykanos
    # river mouth ... Odysseia promontory", all in the same walk) -- a
    # harbor sitting on a coast is definitionally a coastal point, not just
    # a harbor feature, and dropping it from the "coast" tag broke the
    # drawn coastline into two separate trails around it.
    if primary == "harbor" and COASTAL in section_types:
        tags.add("coast")
    # A river's own source is routinely given by naming the mountain it
    # rises from -- "Mt. X, from which the Y river flows" (confirmed
    # throughout book 4.6's Libyan river catalogue: Mandron, Sagapola,
    # Russadion, Kapha, Girgiri...), "Sources of the River X in the Y
    # Mountains" (confirmed book 7.1's Indian river catalogue: Tyna,
    # Maisolos, Manda...), "the Strymon river begins from the mountains
    # forming the border of Thrace and Macedonia" (confirmed §3.12.2).
    # 'mountain' wins primary since explicit_checks puts it ahead of
    # river/river_mouth, but the same citation is just as much a river
    # citation -- without this, the entire "river originates at a named
    # mountain" idiom (exactly the "which mountains do rivers rise from"
    # case the original brief asked to identify) was invisible to every
    # river line: a point tagged only 'mountain' never enters
    # build_rivers' own river_points filter.
    if primary == "mountain":
        if river_mouth_hit:
            tags.add("river_mouth")
        elif _RIVER_RE.search(name):
            tags.add("river")
    # A point cited in a boundary/orientation section is a boundary marker
    # *in addition to* whatever its own name says (it's frequently also a
    # duplicate of a point cited properly elsewhere -- see points.py dedup).
    if BOUNDARY in section_types:
        tags.add("boundary")

    return tags


def tag_points(points: list[Point], resolved: dict[str, str]) -> None:
    for point in points:
        point.tags = tag_point(point, resolved)


def _citation_stream(sections, points: list[Point]) -> list[tuple[Point, str]]:
    """Every citation, in document order, as (canonical Point, the raw
    name_phrase actually cited *here* -- not the point's overall trimmed
    name, since a shared/deduped point can be cited with different wording
    at different spots)."""
    occurrence_index: dict[tuple[str, int], Point] = {}
    for p in points:
        for o in p.occurrences:
            occurrence_index[(o.section_key, o.char_offset)] = p

    stream: list[tuple[Point, str]] = []
    for section in sections:
        for citation in section.citations:
            point = occurrence_index[(section.key, citation.char_offset)]
            stream.append((point, citation.name_phrase))
    return stream


# A mountain-range or region's two extremity coordinates are routinely
# cited as "COORD1 and COORD2" ("The extremes of the Hippika mountains are
# at .74deg.00' . 54deg.00' and . 81deg.00' . 52deg.00'") -- since a
# citation's name_phrase is only the text back to the previous coordinate,
# the second extremity's own "name" ends up being just the bare connector
# "and", carrying no keyword of its own at all. Confirmed widespread (60
# points corpus-wide, not confined to one region) rather than a one-off.
_BARE_CONNECTOR_RE = re.compile(r"^and$", re.I)
# A whole *list* of ranges' extremities reuses that same "COORD1 and
# COORD2" shape per range, but each subsequent range in the list is
# introduced tersely as "[and] of [the] NAME" rather than repeating
# "mountains" -- e.g. "The extremes of the Hippika mountains are at X and
# Y; of the Keraunian Z and W; of Korax ...; and of the Kaukasos ...".
# Confirmed §5.9.15: three ranges named this way (Keraunian, Korax,
# Kaukasos) had none of their own citations carry the word "mountain" at
# all, so every one of them -- and every bare "and" chained after them --
# fell through to the section's coastal default.
_BARE_NAMED_CONTINUATION_RE = re.compile(r"^(?:and\s+)?of\s+(?:the\s+)?[A-Za-z][\w-]*$", re.I)


def propagate_bare_connector_tags(sections, points: list[Point]) -> None:
    """A citation whose entire name_phrase is the bare word "and", or a
    bare "[and] of [the] NAME" continuation, is always the same feature as
    the citation immediately before it in document order (a range/region's
    other extremity, or the next range in the same extremities list) -- so
    it inherits that point's *current* tag set outright, rather than
    falling back to the enclosing section's coastal default.

    Deliberately live, not frozen: a chain of several of these in a row
    (as in §5.9.15's four-range list) must resolve link by link, each one
    picking up the tag its immediate predecessor was *just* given. No
    consecutive-connector run in this corpus is a case where that chaining
    would be wrong (confirmed: no two bare "and" citations are ever
    directly adjacent), so nothing is lost by not freezing here the way
    propagate_river_context must.
    """
    stream = _citation_stream(sections, points)

    for i, (point, phrase) in enumerate(stream):
        cleaned = phrase.strip().strip(",;.")
        if not (_BARE_CONNECTOR_RE.match(cleaned) or _BARE_NAMED_CONTINUATION_RE.match(cleaned)):
            continue
        if i == 0:
            continue
        prev_point = stream[i - 1][0]
        if id(prev_point) == id(point):
            continue
        point.tags = set(prev_point.tags)


def propagate_river_context(sections, points: list[Point]) -> None:
    """Re-tag the generic, name-free positional citations matched by
    _GENERIC_RIVER_POSITION_RE ("The turn towards the east", "Point at
    which it crosses over to X") as 'river' when a river/river_mouth
    citation sits immediately next to them in document order -- their own
    text carries no keyword at all, so the citations on either side are the
    only real signal that they're still mid-river, not a fresh coastal
    point.

    Neighbour lookups use a *frozen* snapshot of each point's tags taken
    before this pass runs. Without that, re-tagging point i to 'river'
    would make it look river-tagged when point i+1 is checked next,
    letting the change cascade down an entire coastal walk -- confirmed by
    running this once without the snapshot: it silently reclassified 651
    points, including plain coastal cities (Genua, Neapolis, Sidon...)
    nowhere near a river.
    """
    stream = _citation_stream(sections, points)

    original_riverish = {
        id(point) for point, _ in stream
        if "river" in point.tags or "river_mouth" in point.tags
    }

    def was_riverish(p: Point) -> bool:
        return id(p) in original_riverish

    for i, (point, phrase) in enumerate(stream):
        if was_riverish(point) or not _GENERIC_RIVER_POSITION_RE.search(phrase):
            continue
        prev_point = stream[i - 1][0] if i > 0 else None
        next_point = stream[i + 1][0] if i + 1 < len(stream) else None
        if (prev_point and was_riverish(prev_point)) or (next_point and was_riverish(next_point)):
            point.tags.discard("coast")
            point.tags.add("river")
