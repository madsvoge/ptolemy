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
_RIVER_MOUTH_RE = re.compile(r"\bmouth\s+of\b|\bestuary\b|\boutlet\b", re.I)
_RIVER_RE = re.compile(
    r"\bsource\b|\bspring\b|\bbend\b|\bconfluence\b|\bfork\b|\bbranch\b"
    # "Mid-point of its length" (referring anaphorically to the previous
    # citation's river) is this text's own way of citing a point partway
    # along a river's course, alongside its mouth and source.
    r"|\bmid-?points?\s+of\s+its\s+length\b",
    re.I,
)
_HARBOR_RE = re.compile(r"\bharbou?r\b|\bport\b", re.I)
_COAST_NAME_RE = re.compile(r"\bpromontory\b|\bcape\b|\bheadland\b|\bbay\b|\bgulf\b", re.I)
_LAKE_RE = re.compile(r"\blake\b", re.I)
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
    r"|\balready\s+mentioned\b|\bterminal\s+points?\b|\bterminus\b",
    re.I,
)


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
    # coastline, not just a river feature -- keep both roles.
    if primary == "river_mouth" and COASTAL in section_types:
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
