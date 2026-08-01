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
from .points import Point

_ISLAND_NAME_RE = re.compile(r"\bisland", re.I)
# "Mt." (with or without the period) is this text's dominant way of citing
# a single named peak/range, at least as common as spelling out "mount".
_MOUNTAIN_NAME_RE = re.compile(r"\bmounts?\b|\bmountain|\bmt\.?\s", re.I)
# "Mouth(s) of" is the dominant form, but a distributary's own name is
# often given as "the X Mouth" (a proper noun in its own right, e.g. "the
# Kambyson Mouth") with no "of" at all -- and the plural "Mouths of the
# river X" (a delta with more than one outlet) was being missed entirely
# by a singular-only "mouth of".
_RIVER_MOUTH_RE = re.compile(r"\bmouths?\s+of\b|\bmouths?\b|\bestuary\b|\boutlet\b", re.I)
_RIVER_RE = re.compile(
    r"\bsources?\b|\bspring\b|\bbends?\b|\bconfluence\b|\bforks?\b|\bbranch(?:es)?\b"
    r"|\bjunctions?\b|\bbifurcat\w*\b|\bunites?\b|\bunion\b"
    # "flows into", "joins (with)", "splits into" -- a tributary meeting or
    # leaving its main river, and "turn(s)"/"bend(s)" of *the river*
    # specifically (as opposed to an ambiguous bare "turn towards the
    # east", handled separately below via its neighbours in the stream).
    r"|\bflows?\s+into\b|\bjoins?\b|\bsplits?\s+into\b"
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
    # "Mid-point of its length" / "Mid–point of the length of the river"
    # (referring anaphorically, or by full restatement, to a river cited
    # nearby) is this text's own way of citing a point partway along a
    # river's course, alongside its mouth and source. The separator
    # between "mid" and "point" varies (hyphen, en dash, space).
    r"|\bmid.{0,2}points?\s+of\s+(?:its|the)\s+length\b",
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
# Iuliobona", "...the Osismi whose city is Vorgum") -- this idiom recurs
# throughout the catalogue. Such a city is not itself a waypoint on the
# coastal walk (it can sit well inland of the stretch it's attached to,
# breaking catalogue-order adjacency badly enough to self-intersect the
# drawn coastline -- confirmed on 2.8.5/2.8.6), so it must be recognized
# and tagged 'city' *before* falling back to the coastal-section default.
_TRIBAL_CITY_RE = re.compile(r"\bcity\s+is\b|\bcities?\s+is\b|\bwhose\s+city\b|\btheir\s+city\b|\bcity\s+being\b", re.I)
# A boundary/orientation aside can land inside an otherwise coastal
# section too (Ptolemy occasionally re-cites a "limit point" or "extreme
# point already mentioned" mid-walk to tie the coast back to a boundary
# he stated earlier) -- these are reference markers, not fresh waypoints,
# and forcing them into the coastal walk creates exactly the kind of
# backtracking jump that self-intersects the drawn line.
_REFERENCE_MARKER_RE = re.compile(
    r"\bextreme\s+points?\b|\bextremity\b|\blimit\s+points?\b|\bend\s+points?\b"
    r"|\balready\s+mentioned\b|\bterminal\s+points?\b|\bterminus\b"
    # "...along the line on this side along Epiros until the end, at
    # position..." -- a boundary line's own endpoint, phrased without any
    # of the "limit/extreme/end point" wording above. Confirmed on
    # Macedonia's southern border (3.12.3): its coordinate sits far from
    # where it's cited in document order (near the walk's actual
    # Thessalian end, cited early as an orientation marker), which is
    # exactly the shape of jump that self-intersects a drawn coastline.
    r"|\buntil\s+the\s+end\b"
    # Named frontier landmarks Ptolemy uses to mark a boundary line
    # ("The Pillars of Alexander are at...", "The Sarmatian Gates...",
    # "The Albanian Gates...") -- proper nouns, but frontier markers, not
    # coastal capes, and they cluster right alongside mountain-range
    # extremity citations in boundary-heavy sections (confirmed 5.9.15).
    r"|\bgates\b|\bpillars\s+of\b",
    re.I,
)
# "Branch of/from the Indus into the Sagapa mouth" names a distributary
# *joining another named channel upstream in a delta* -- the coordinate is
# an inland branch point, not the actual coastline. Confirmed on the
# Indus (§7.1.28), matching the same delta structure already found on the
# Ganges (§7.1.29-30) and Nile: threading these into the coastal walk
# alongside the delta's real, separately-cited coastal mouths (§7.1.2's
# "the seven mouths of the [river]") draws two near-parallel tracks along
# the same stretch of coast ("duplicate coastline").
_DISTRIBUTARY_BRANCH_RE = re.compile(r"\bbranch(?:es)?\b", re.I)


def tag_point(point: Point, resolved: dict[str, str]) -> set[str]:
    name = " ".join(point.name_variants)
    section_types = {resolved[o.section_key] for o in point.occurrences}

    explicit_checks = [
        ("island", bool(_ISLAND_NAME_RE.search(name)) or ISLAND in section_types),
        ("mountain", bool(_MOUNTAIN_NAME_RE.search(name)) or MOUNTAIN in section_types),
        ("river_mouth", bool(_RIVER_MOUTH_RE.search(name))),
        ("river", bool(_RIVER_RE.search(name))),
        ("harbor", bool(_HARBOR_RE.search(name))),
        ("coast", bool(_COAST_NAME_RE.search(name))),
        ("lake", bool(_LAKE_RE.search(name))),
    ]
    primary = next((tag for tag, matched in explicit_checks if matched), None)
    if primary is None:
        if _TRIBAL_CITY_RE.search(name) or _REFERENCE_MARKER_RE.search(name):
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


def propagate_bare_connector_tags(sections, points: list[Point]) -> None:
    """A citation whose entire name_phrase is the bare word "and" is
    always the second half of the *same* feature as the citation
    immediately before it in document order (a range/region's other
    extremity) -- so it inherits that point's full tag set outright,
    rather than falling back to the enclosing section's coastal default.

    Uses a frozen snapshot of pre-pass tags for the same reason
    propagate_river_context does: two consecutive bare-'and' citations
    must not chain off of each other's *new* tags.
    """
    stream = _citation_stream(sections, points)
    original_tags = {id(point): set(point.tags) for point, _ in stream}

    for i, (point, phrase) in enumerate(stream):
        if not _BARE_CONNECTOR_RE.match(phrase.strip().strip(",;.")):
            continue
        if i == 0:
            continue
        prev_point = stream[i - 1][0]
        if id(prev_point) == id(point):
            continue
        point.tags = set(original_tags[id(prev_point)])


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
