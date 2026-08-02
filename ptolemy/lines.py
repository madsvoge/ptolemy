"""Step 6: the line-drawing engine -- coastlines, rivers, mountain ranges,
islands. Reconstructs each as a MultiLineString-worthy set of trails built
purely from catalogue order and coordinates; no ground truth is consulted.
"""
from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass

from shapely.geometry import LineString as ShapelyLineString

from .classify import COASTAL, ISLAND, is_named_island_walk, is_new_region_declaration, river_bank_city_lead_name, river_delta_lead_name, starts_new_coastal_arc, starts_new_named_island
from .parser import Section
from .points import Point
from .tag import RESTATED_LANDMARK_RE

# Starting point suggested by prior art on this same kind of reconstruction,
# re-derived empirically against this text: consecutive-citation gaps for
# resolved coastal-walk points have their 95th percentile at ~6.8 degrees
# and their median under 0.7 degrees, so 5 degrees excludes only the real
# long tail (genuine jumps between disjoint stretches) without touching the
# bulk of true adjacent-point edges.
COASTLINE_CAP_DEG = 5.0
# A wider cap was tried here (15 degrees) specifically to connect the
# Nile's own far-apart citations (junction-with-Astapos to the lakes
# outlet, >10 degrees). Reverted: common river names repeat for
# genuinely unrelated rivers (confirmed on Britain's own text -- two
# *different* rivers both named "Alaunus", one on the north coast, one on
# the south, 6.9 degrees apart), and distance alone can't tell that case
# apart from "one very large river's own citations are just spread out" --
# they look identical geometrically. Left unconnected is the safe default
# per the brief's own guidance ("don't draw a confident line between two
# things that just happen to share a name"); a big single-region river
# like the Nile simply won't auto-connect end to end.
RIVER_CAP_DEG = 5.0
MOUNTAIN_CAP_DEG = 5.0
# A trail's two ends close into a loop only if they're both near in
# absolute terms AND close relative to the trail's own total length --
# otherwise two points that just happen to sit near each other on an open
# stretch would wrongly get treated as a wraparound.
LOOP_CLOSE_RELATIVE_FRACTION = 0.2


@dataclass
class Line:
    id: str
    kind: str  # "coastline" | "river" | "mountain" | "island"
    book_map: str
    feature_name: str | None  # river/mountain/island group name; None for coastlines
    point_ids: list[str]
    closed: bool = False


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a.lon_modern - b.lon_modern, a.lat_modern - b.lat_modern)


def _trail_length(trail: list[Point]) -> float:
    return sum(_dist(a, b) for a, b in zip(trail, trail[1:]))


def build_citation_streams(sections: list[Section], occurrence_index: dict[tuple[str, int], Point]) -> dict[str, list[list[tuple[str, Point, str]]]]:
    """Every citation, in document order, grouped by book.map, and within
    that further split into segments at each is_new_region_declaration
    section (confirmed §3.14.25, "Position of the Peloponnesos", mid
    book.map 3.14) or starts_new_coastal_arc citation (confirmed §3.11.3,
    "the description is the following: After Mesembria...") -- almost
    always just one segment per book.map, but two genuinely separate
    coastal arcs catalogued under the same book.map must never have their
    coastlines bridged by build_coastlines' own greedy distance-based
    stitching just because book.map scoping alone doesn't separate them.
    Each segment entry is (section_key, Point, this citation's own raw
    name_phrase)."""
    streams: dict[str, list[list[tuple[str, Point, str]]]] = {}
    for section in sections:
        segments = streams.setdefault(section.book_map, [[]])
        if is_new_region_declaration(section) and segments[-1]:
            segments.append([])
        for citation in section.citations:
            point = occurrence_index[(section.key, citation.char_offset)]
            if starts_new_coastal_arc(citation.name_phrase) and segments[-1]:
                segments.append([])
            segments[-1].append((section.key, point, citation.name_phrase))
    return streams


def _split_into_runs(ordered_points: list[Point], cap: float, keep_singletons: bool = False) -> list[list[Point]]:
    """Split a same-book.map, filtered point sequence into runs (trails)
    wherever consecutive points repeat (a dedup echo) or exceed the cap.
    A leftover single point is dropped by default (a Line needs 2+ points)
    -- unless keep_singletons is set, for a name about to be handed to
    _stitch_runs across book_map boundaries, where a lone point in one
    book_map (e.g. the Ganges' own separately-cited mouth, alone in 7.4)
    still needs to survive this step as a 1-point run so the stitch phase
    can pair it up; _build_named_feature_lines drops anything still a
    singleton once stitching is done."""
    runs: list[list[Point]] = []
    current: list[Point] = []
    for p in ordered_points:
        if not current:
            current = [p]
            continue
        prev = current[-1]
        if p.id == prev.id:
            continue
        if _dist(prev, p) <= cap:
            current.append(p)
        else:
            if len(current) >= 2 or keep_singletons:
                runs.append(current)
            current = [p]
    if len(current) >= 2 or keep_singletons:
        runs.append(current)
    return runs


def _trail_self_intersects(trail: list[Point]) -> bool:
    """True if any two non-adjacent segments of this trail cross at a point
    that isn't one of the trail's own vertices -- a trail merely touching
    itself at a shared/repeated vertex (legitimate, e.g. a peninsula loop)
    is not a crossing."""
    coords = [(p.lon_modern, p.lat_modern) for p in trail]
    segs = list(zip(coords, coords[1:]))
    endpoints = set(coords)
    for i in range(len(segs)):
        for j in range(i + 2, len(segs)):
            a, b = segs[i]
            c, d = segs[j]
            s1, s2 = ShapelyLineString([a, b]), ShapelyLineString([c, d])
            if not s1.intersects(s2):
                continue
            inter = s1.intersection(s2)
            if inter.geom_type == "Point":
                if (inter.x, inter.y) not in endpoints:
                    return True
            elif inter.geom_type != "MultiPoint" or any((pt.x, pt.y) not in endpoints for pt in inter.geoms):
                return True
    return False


def _stitch_runs(runs: list[list[Point]], cap: float, avoid_crossings: bool = False) -> list[list[Point]]:
    """Greedily join two trails' loose ends when they land close together --
    the gap an interrupting non-coastal section leaves behind. All four
    end/start orientations are tried, not just forward (end_i -> start_j):
    confirmed necessary on this very text (2.2, Ireland, the brief's own
    worked example) -- its north-coast run (Boreum ... Rhobogdium) and its
    west/south/east run in fact join end-to-end (Rhobogdium next to the
    east coast's last point), not end-to-start, because Ptolemy's prose
    revisits the Boreum corner explicitly ("from the Boreum promontory
    which is in...") to *open* the second run rather than close the first.

    avoid_crossings (river cross-book_map stitching only) rejects the
    nearest-endpoint candidate if it would self-cross the merged trail, and
    falls back to the next-nearest instead. Nearest-endpoint distance alone
    isn't always the geometrically correct join: two runs can share a real
    duplicate point sitting in the *middle* of one of them, not at either
    of its ends (confirmed on the Danube: "the bend at Dinogeteia city",
    book_map 3.8, and "5th Legion Macedonica Dinogeteia", book_map 3.10,
    are 0.17 degrees apart -- the same real place cited twice, too far
    apart to dedup, but sitting mid-trail in 3.10's own run) -- stitching
    onto the nearer-but-wrong end still passes the cap and produces a real
    self-crossing. Left disabled for every other caller (coastlines) to
    avoid changing already-verified behaviour there."""
    runs = [list(r) for r in runs]
    merged = True
    while merged and len(runs) > 1:
        merged = False
        candidates = []  # (dist, i, j, orientation)
        for i, ti in enumerate(runs):
            for j, tj in enumerate(runs):
                if i == j:
                    continue
                for d, orientation in (
                    (_dist(ti[-1], tj[0]), "end_start"),
                    (_dist(ti[-1], tj[-1]), "end_end"),
                    (_dist(ti[0], tj[-1]), "start_end"),
                    (_dist(ti[0], tj[0]), "start_start"),
                ):
                    if d <= cap:
                        candidates.append((d, i, j, orientation))
        candidates.sort(key=lambda c: c[0])
        for _d, i, j, orientation in candidates:
            ti, tj = runs[i], runs[j]
            if orientation == "end_start":
                head, tail = ti, tj
            elif orientation == "end_end":
                head, tail = ti, list(reversed(tj))
            elif orientation == "start_end":  # tj's end meets ti's start -> tj then ti
                head, tail = tj, ti
            else:  # start_start: reverse ti so its start becomes its end, then tj
                head, tail = list(reversed(ti)), tj
            # The joining endpoints are often the *same* dedup'd point (a
            # shared junction, distance 0) -- don't duplicate it in the
            # merged trail.
            if head[-1].id == tail[0].id:
                tail = tail[1:]
            new_run = head + tail
            if avoid_crossings and _trail_self_intersects(new_run):
                continue
            runs = [r for idx, r in enumerate(runs) if idx not in (i, j)] + [new_run]
            merged = True
            break
    return runs


def _maybe_close_loop(trail: list[Point], cap: float) -> bool:
    if len(trail) < 3:
        return False
    d = _dist(trail[0], trail[-1])
    if trail[0].id == trail[-1].id:
        return True
    length = _trail_length(trail)
    return d <= cap and length > 0 and d <= LOOP_CLOSE_RELATIVE_FRACTION * length


def build_coastlines(streams: dict[str, list[list[tuple[str, Point, str]]]], resolved: dict[str, str],
                      cap: float = COASTLINE_CAP_DEG) -> list[Line]:
    lines: list[Line] = []
    for book_map, segments in streams.items():
        i = 0
        for seq in segments:
            # "coast" in point.tags is a *point*-level property (true if
            # any of its occurrences earned it), but a point can also be
            # cited once more elsewhere in the same book.map as an
            # incidental boundary/inland aside (confirmed §2.5.1/§2.5.3,
            # Lusitania: the Dourius river mouth restated as the
            # province's own opening boundary landmark, then cited again,
            # correctly, as the coastal walk's own last point) --
            # including that non-coastal occurrence's position in the walk
            # stitched in a spurious early detour to the same coordinate.
            # Only an occurrence whose *own* section actually resolved
            # COASTAL belongs in the walk.
            #
            # A *second* real signal for the same "restated, not a fresh
            # waypoint" problem: Ptolemy routinely opens a new region's own
            # coastal description by restating the previous region's last
            # landmark for orientation ("After Pegai in the Megarid, which
            # is in the Corinthian gulf...", confirmed §3.14.6/§3.14.26) --
            # and that restated citation's own section resolves COASTAL
            # just like the walk it's opening, so the check above doesn't
            # catch it. Once a point has already been placed in this
            # segment's walk, a later occurrence matching tag.py's own
            # RESTATED_LANDMARK_RE idiom is that restatement, not a second
            # real waypoint to revisit -- skipped, or it stitched a
            # spurious detour back to the earlier coordinate (confirmed:
            # connected clean across the Boiotia/Attike coast to the
            # unrelated Megarid point, self-intersecting the drawn
            # coastline). A point's own genuine *first* occurrence is
            # never skipped this way even if its phrase happens to match
            # the same idiom (confirmed §4.5.74's Lesser Cataract and
            # §3.10.7's mouth of the Borysthenes: both are a section's own
            # real opening waypoint, not a restatement of anything cited
            # earlier).
            coastal_points: list[Point] = []
            seen: set[str] = set()
            for key, p, phrase in seq:
                if "coast" not in p.tags or resolved[key] != COASTAL:
                    continue
                if p.id in seen and RESTATED_LANDMARK_RE.search(phrase):
                    continue
                coastal_points.append(p)
                seen.add(p.id)
            runs = _split_into_runs(coastal_points, cap)
            runs = _stitch_runs(runs, cap)
            for trail in runs:
                i += 1
                closed = _maybe_close_loop(trail, cap)
                lines.append(Line(
                    id=f"coastline-{book_map}-{i}",
                    kind="coastline",
                    book_map=book_map,
                    feature_name=None,
                    point_ids=[p.id for p in trail],
                    closed=closed,
                ))
    return lines


# ---------------------------------------------------------------------
# Rivers and mountain ranges: grouped by a base name extracted from the
# point's own name text, not by catalogue adjacency (Ptolemy revisits a
# river/range at unrelated points in the text: a mouth here, a source
# hundreds of citations later). A point whose phrase doesn't cleanly match
# one of these templates is left ungrouped rather than guessed at -- most
# of the noise here comes from boundary-marker sentences that merely
# mention a river/mountain in passing, and this is a deliberate filter to
# keep those out rather than a gap to patch with more patterns.
# Every keyword below (mouth/sources/river/bend/estuary/confluence/
# junction/and/with/the/of) is matched case-insensitively -- a citation
# that opens its own section is routinely sentence-initial and
# capitalized ("Mouth of the River Lykos", confirmed throughout book 7,
# India) where every other citation of the same idiom uses lowercase
# ("mouth of the river Rhymmos"). Confirmed as a real, wide gap: case-
# sensitive matching alone left the *entire* Ganges/Indus tributary
# catalogue's own "Mouth of River X"/"Sources of the River X" citations
# unnamed, and therefore silently dropped from every river line. The
# name capture itself stays case-sensitive via (?-i:...), or the
# optional "the"/"river" skip would fail on a capitalized "The"/"River"
# and the capture group would swallow that word instead of the real name
# right after it.
_RIVER_TEMPLATES = [
    re.compile(r"\bmouths?\s+of\s+(?:the\s+)?((?-i:[A-Z])[\w-]*)\b", re.I),
    re.compile(r"\bsources?\s+of\s+(?:the\s+)?(?:river\s+)?((?-i:[A-Z])[\w-]*)\b", re.I),
    re.compile(r"\b((?-i:[A-Z])[\w-]*)\s+river\b", re.I),
    # "river Nile", "the river Astapos" -- reversed word order used
    # throughout the Nile catalogue (§4.7.20-26), where "X river" is used
    # everywhere else. Checked after "X river" so a plain "Nile river"
    # citation still resolves the same way regardless of which template
    # would have matched.
    re.compile(r"\briver\s+((?-i:[A-Z])[\w-]*)\b", re.I),
    re.compile(r"\bbend\s+of\s+(?:the\s+)?((?-i:[A-Z])[\w-]*)\b", re.I),
    # "Clota estuary", "Belisama estuary" -- Britain's own river-mouth
    # naming convention (confirmed book.map 2.3), "X estuary" rather than
    # "mouth of X"/"X river" used everywhere else. Without this template
    # these already-'river_mouth'-tagged points had no name at all, so
    # they were silently dropped from every named river line.
    re.compile(r"\b((?-i:[A-Z])[\w-]*)\s+estuary\b", re.I),
]
# "Confluence of the Koa and Indus", "Junction of the Kiabros with the
# Danube" -- a tributary joining a named river, both names given in the
# same breath (confirmed 26 occurrences corpus-wide, Nile/Indus/Ganges/
# Danube/Rhodanus/Oxos/Iaxartes/Tigris systems, zero false positives
# checked by hand). Unlike every other river template above, which name
# a point belongs to for grouping, a confluence point belongs to *both*
# rivers' groups at once -- it's the tributary's own endpoint and a real
# waypoint on the main river's course simultaneously. See
# river_base_names (plural), the only caller that uses this.
_RIVER_CONFLUENCE_TEMPLATES = [
    re.compile(r"\b(?:confluence|junction)\s+of\s+(?:the\s+)?(?:river\s+)?((?-i:[A-Z])[\w-]*)\s+and\s+(?:the\s+)?(?:river\s+)?((?-i:[A-Z])[\w-]*)\b", re.I),
    re.compile(r"\b(?:confluence|junction)\s+of\s+(?:the\s+)?(?:river\s+)?((?-i:[A-Z])[\w-]*)\s+with\s+(?:the\s+)?(?:river\s+)?((?-i:[A-Z])[\w-]*)\b", re.I),
]
_MOUNTAIN_TEMPLATES = [
    re.compile(r"\bmt\.?\s+((?-i:[A-Z])[\w-]*)\b", re.I),
    re.compile(r"\b((?-i:[A-Z])[\w-]*)\s+mountains?\b", re.I),
    re.compile(r"\bmountains?\s+of\s+(?:the\s+)?((?-i:[A-Z])[\w-]*)\b", re.I),
]

_GENERIC_RIVER_WORDS = {"river", "the", "sea", "sources", "source"}

# "After the mouth of the Liger river, Brivates 1°20' . 48°20'" -- a coastal
# city/promontory citation that merely uses an earlier river's mouth as its
# own positional landmark, the way a coastal walk restates its last point
# before naming the next one. The coordinate belongs to the NEW name after
# the comma (Brivates), not the river mentioned before it -- but every river
# template above still matches "Liger" in the first half of the phrase, so
# without this guard the city was wrongly folded into the Liger's own line
# (confirmed §3.10.3: "after the Sacred mouth of the Istros river, Pteron
# promontory" put a Thracian coastal promontory more than 30 degrees from
# the Danube's own course into the Danube's line). Distinguished from a
# genuine restatement of the *same* river ("after the mouth of the
# Borysthenes, which is at...", confirmed book.map 3.10) by what follows the
# comma: a bare capitalized name means a new subject, "which" means the
# same feature restated.
_RIVER_LANDMARK_HANDOFF_RE = re.compile(
    r"\bafter\s+(?:the\s+)?.{0,60}?\b(?:mouths?|sources?|bends?|confluence|junction)\b"
    r".{0,40}?,\s*(?-i:[A-Z])",
    re.I,
)


def _last_template_match(phrase: str, templates: list[re.Pattern], exclude_words: set[str] = frozenset()) -> str | None:
    # The name mentioned *last* in the phrase -- i.e. closest to the
    # coordinate that follows it -- is what a citation is actually about.
    # A long restating sentence often names an earlier river/range first
    # ("from the mouth of the Istros until the mouth of the Borysthenes
    # river...after the mouth of the Borysthenes, which is at <coord>")
    # before settling on the one the coordinate is really for; taking the
    # first match in document order wrongly grouped a Borysthenes citation
    # under "Istros" this way (confirmed, book.map 3.10).
    best: tuple[int, str] | None = None
    for template in templates:
        for m in template.finditer(phrase):
            if m.group(1).lower() in exclude_words:
                continue
            if best is None or m.start() > best[0]:
                best = (m.start(), m.group(1))
    return best[1] if best else None


def river_base_name(point: Point) -> str | None:
    for phrase in point.name_variants:
        if _RIVER_LANDMARK_HANDOFF_RE.search(phrase):
            continue
        name = _last_template_match(phrase, _RIVER_TEMPLATES, _GENERIC_RIVER_WORDS)
        if name:
            return name
    return None


def river_base_names(point: Point) -> list[str]:
    """Every river a point belongs to -- almost always the same single
    name river_base_name (singular) returns, except a confluence citation
    ("Confluence of the Koa and Indus"), which names *two* rivers at once
    and genuinely belongs to both: it's the tributary's own endpoint and,
    simultaneously, a real waypoint sitting on the main river's course.
    Threading it into both groups is what makes the tributary's own line
    actually meet the river it joins, rather than stopping just short of
    it (confirmed §7.1.26-30's Indus/Ganges tributary catalogue: without
    this, e.g. the Koa's own line ended at a point never shared with the
    Indus's line, an unconnected loose end sitting right next to it)."""
    for phrase in point.name_variants:
        if _RIVER_LANDMARK_HANDOFF_RE.search(phrase):
            continue
        for template in _RIVER_CONFLUENCE_TEMPLATES:
            m = template.search(phrase)
            if m:
                a, b = m.group(1), m.group(2)
                if a.lower() not in _GENERIC_RIVER_WORDS and b.lower() not in _GENERIC_RIVER_WORDS:
                    return [a, b]
    single = river_base_name(point)
    return [single] if single else []


def mountain_base_name(point: Point) -> str | None:
    for phrase in point.name_variants:
        name = _last_template_match(phrase, _MOUNTAIN_TEMPLATES)
        if name:
            return name
    return None


def _build_named_feature_lines(
    points: list[Point],
    kind: str,
    names_fn,
    cap: float,
    cross_book_map_caps: dict[str, float] | None = None,
) -> list[Line]:
    """names_fn returns every group a point belongs to (almost always
    zero or one; a river confluence point belongs to two at once -- see
    river_base_names). A point in two groups appears once in each
    resulting Line, which is exactly what makes a tributary's own line
    actually meet the river it joins at a shared vertex.

    Every name's own per-book_map runs are always built first, the same
    safe, document-order way as before (unchanged for every caller that
    doesn't pass cross_book_map_caps).

    cross_book_map_caps (river-only) is a curated, human-verified allowlist
    of {lowercase canonical name: cap_deg} -- see data/river_long_course.csv.
    Only a name listed there ever bridges book_map boundaries at all, and
    only by handing its own separate per-book_map runs to _stitch_runs,
    which joins the geometrically *nearest* pair of loose ends first --
    never by raw document order across the boundary. Document order across
    a book_map boundary isn't safe to trust the way it is within one: two
    neighbouring regions' own city lists routinely each restart near their
    shared stretch of the river rather than continuing monotonically
    downstream (confirmed on the Danube: 2.11's own bank-city list runs
    east to its own region's edge, then 2.12's own list restarts further
    west, near the source again) -- concatenating them in document order
    draws a false backtrack across the whole width of the river bend,
    self-crossing the real course five times. Nearest-endpoint stitching
    (already used for coastlines, e.g. Ireland's own north/west runs)
    doesn't have that failure mode.

    This is deliberately not a blanket wider cap on top of everything: a
    plain distance cap can't tell "one large river's citations are just
    spread out" apart from "two different, unrelated rivers happen to
    share a name" (confirmed on Britain's own text, two different rivers
    both named Alaunus, 6.9 degrees apart) -- and at whole-corpus scale,
    common river names like Lykos or Phasis repeat for genuinely different
    rivers far more often than a single real river's own citations are
    legitimately spread that far apart. Widening the cap (or bridging
    book_map boundaries) is only safe once a human has actually read the
    text and confirmed it's the same river, the same way
    manual_section_overrides.csv exists for exactly this kind of judgment
    call."""
    cross_book_map_caps = cross_book_map_caps or {}
    groups: dict[tuple[str, str], list[Point]] = {}
    display_names: dict[str, str] = {}
    for p in points:
        for base in names_fn(p):
            key = (p.book_map, base.lower())
            groups.setdefault(key, []).append(p)
            display_names.setdefault(base.lower(), base)

    runs_by_name: dict[str, list[list[Point]]] = {}
    for (_book_map, name_key), group_points in groups.items():
        group_points = sorted(group_points, key=lambda p: p.first_char_offset)
        # Always split at the shared *default* cap first, even for a name
        # with its own wider override -- document order is only trustworthy
        # up to that default distance. A name's own runs beyond that
        # (whether the gap sits inside one book_map, like the Indus's own
        # sources-to-delta spread, or crosses a book_map boundary, like the
        # Danube's) are only ever bridged by the nearest-endpoint,
        # crossing-checked stitch below -- never by widening this initial,
        # document-order split itself. Confirmed necessary: forward-filling
        # the Danube's own tributary-junction citations ("point at the bend
        # of the river flowing...") into 2.11's group put them right before
        # that book_map's *separate* "towns along the Danube" list in
        # document order but nowhere near it geographically (14+ degrees
        # apart) -- splitting *that* jump at the wider override cap too
        # produced a real self-crossing that nearest-endpoint stitching
        # doesn't have, because it isn't limited to trying only the two
        # runs' raw document-order ends.
        runs_by_name.setdefault(name_key, []).extend(
            _split_into_runs(group_points, cap, keep_singletons=name_key in cross_book_map_caps)
        )

    lines: list[Line] = []
    for name_key, runs in runs_by_name.items():
        base = display_names[name_key]
        override_cap = cross_book_map_caps.get(name_key)
        if override_cap is not None and len(runs) > 1:
            runs = _stitch_runs(runs, override_cap, avoid_crossings=True)
        runs = [r for r in runs if len(r) >= 2]
        for i, trail in enumerate(runs, start=1):
            # A cross-book_map-stitched trail's own Line.book_map is just
            # its first (earliest-cited) point's book_map -- representative
            # metadata, since the trail itself may now span several.
            book_map = trail[0].book_map
            lines.append(Line(
                id=f"{kind}-{book_map}-{base}-{i}",
                kind=kind,
                book_map=book_map,
                feature_name=base,
                point_ids=[p.id for p in trail],
            ))
    return lines


_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RIVER_ALIASES_PATH = os.path.join(_DATA_DIR, "river_aliases.csv")
RIVER_LONG_COURSE_PATH = os.path.join(_DATA_DIR, "river_long_course.csv")


def _load_river_aliases(path: str = RIVER_ALIASES_PATH) -> dict[str, str]:
    """lowercase alias -> canonical display name, e.g. 'istros' -> 'Danube'
    (confirmed §3.8.2: "the Danube is also called Istros as far as the
    mouth"). Curated by hand in data/river_aliases.csv, same reasoning as
    the cross-book_map cap list below: a name-equivalence like this can
    only be established by actually reading the text, never inferred from
    spelling or distance alone."""
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["alias"].lower(): row["canonical"] for row in csv.DictReader(f)}


def _load_river_long_course_caps(path: str = RIVER_LONG_COURSE_PATH) -> dict[str, float]:
    """lowercase canonical name -> cap_deg, from data/river_long_course.csv.
    See _build_named_feature_lines' own docstring for why this has to be an
    explicit, curated allowlist rather than a blanket wider cap."""
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {row["canonical"].lower(): float(row["cap_deg"]) for row in csv.DictReader(f)}


def _river_forward_fill(points: list[Point], sections: list[Section], aliases: dict[str, str]) -> dict[str, str]:
    """point.id -> an inherited river name, for a citation that carries its
    own river vocabulary (tag.py's 'river'/'river_mouth') but names no
    river of its own -- inherited from the most recently *explicitly*
    named river earlier in the same book_map's document order.

    Confirmed §5.1.6: "mouth of the Sangarios river" names the river, then
    "first turn of the river", "second turn", "third turn", "river
    sources" carry the river tag but never repeat "Sangarios" -- anaphoric
    continuation of the same citation, not a fresh, differently-named one.
    Also how a delta's own mouths ever connect at all: river_delta_lead_name
    seeds the name from the section's own heading ("The seven mouths of
    the Nile:", confirmed §4.5.10), since none of the individual mouth
    citations below it ("the Bolbitine mouth") name the river either.
    And how the Danube's own multi-section delta connects (confirmed
    §3.10.1's "...the Danube, here called Istros, until the mouth..."
    followed by §3.10.2's "The order of the mouths is as follows:", a
    heading with no river name of its own at all, relying entirely on the
    prior section already having named it) -- deliberately *not* reset at
    every section boundary, only at a book_map boundary, since Ptolemy's
    own delta descriptions routinely run on across several short sections.

    Every one of these still only fires onto a point that independently
    carries the river tag -- a plain coastal city with no river vocabulary
    of its own (confirmed §7.1.18's "Poloura, a town", sitting between two
    named Ganges mouths) never inherits a name this way, so the resulting
    line stays a simple, finger-like set of real mouths/turns/sources
    rather than sweeping in every incidental nearby place."""
    delta_seed: dict[str, str] = {}
    for section in sections:
        name = river_delta_lead_name(section)
        if name:
            delta_seed[section.key] = name

    ordered = sorted(points, key=lambda p: p.first_char_offset)
    fills: dict[str, str] = {}
    current_book_map: str | None = None
    current_section: str | None = None
    current_name: str | None = None
    for p in ordered:
        if not p.occurrences:
            continue
        section_key = p.occurrences[0].section_key
        if p.book_map != current_book_map:
            current_book_map = p.book_map
            current_name = None
        if section_key != current_section:
            current_section = section_key
            if section_key in delta_seed:
                current_name = delta_seed[section_key]
        own_names = river_base_names(p)
        if own_names:
            current_name = aliases.get(own_names[-1].lower(), own_names[-1])
        elif current_name is not None and ("river" in p.tags or "river_mouth" in p.tags):
            fills[p.id] = current_name
    return fills


def build_rivers(
    points: list[Point],
    sections: list[Section],
    cap: float = RIVER_CAP_DEG,
    aliases: dict[str, str] | None = None,
    long_course_caps: dict[str, float] | None = None,
) -> list[Line]:
    # A city cited in a "the following cities are along the Danube
    # river:" section (confirmed §3.10.5, §2.12.4, §3.10.8) carries no
    # river vocabulary in its own name -- "Bragodurum" mentions no river
    # at all -- so river_base_names alone can never place it. The
    # section's own lead is the only place that link exists; bank_city_rivers
    # maps every such section to the river its cities sit along.
    bank_city_rivers: dict[str, str] = {}
    for section in sections:
        name = river_bank_city_lead_name(section)
        if name:
            bank_city_rivers[section.key] = name

    if aliases is None:
        aliases = _load_river_aliases()

    forward_fill = _river_forward_fill(points, sections, aliases)

    def names_fn(p: Point) -> list[str]:
        names = river_base_names(p)
        for o in p.occurrences:
            hint = bank_city_rivers.get(o.section_key)
            if hint and hint not in names:
                names = names + [hint]
        if not names and p.id in forward_fill:
            names = [forward_fill[p.id]]
        return [aliases.get(n.lower(), n) for n in names]

    river_points = [
        p for p in points
        if "river" in p.tags or "river_mouth" in p.tags
        or any(o.section_key in bank_city_rivers for o in p.occurrences)
    ]
    if long_course_caps is None:
        long_course_caps = _load_river_long_course_caps()
    return _build_named_feature_lines(river_points, "river", names_fn, cap, long_course_caps)


def build_mountains(points: list[Point], cap: float = MOUNTAIN_CAP_DEG) -> list[Line]:
    mountain_points = [p for p in points if "mountain" in p.tags]
    names_fn = lambda p: [name] if (name := mountain_base_name(p)) else []
    return _build_named_feature_lines(mountain_points, "mountain", names_fn, cap)


# ---------------------------------------------------------------------
# Islands: only connect points that are unambiguously several capes of the
# *same* named island cited consecutively -- otherwise leave the points
# standalone. Reuses the exact same name-grouping/run-splitting machinery
# as rivers/mountains (not a bespoke mechanism), scoped to island-tagged
# points inside island-classified sections.
_ISLAND_TEMPLATE = re.compile(
    r"\b((?-i:[A-Z])[\w-]*)\s+island\b|\bisland\s+of\s+(?:the\s+)?((?-i:[A-Z])[\w-]*)\b",
    re.I,
)


def island_base_name(point: Point) -> str | None:
    for phrase in point.name_variants:
        m = _ISLAND_TEMPLATE.search(phrase)
        if m:
            return m.group(1) or m.group(2)
    return None


def build_islands(points: list[Point], resolved: dict[str, str], cap: float = MOUNTAIN_CAP_DEG) -> list[Line]:
    island_points = [
        p for p in points
        if "island" in p.tags and any(resolved[o.section_key] == ISLAND for o in p.occurrences)
    ]
    names_fn = lambda p: [name] if (name := island_base_name(p)) else []
    return _build_named_feature_lines(island_points, "island", names_fn, cap)


# ---------------------------------------------------------------------
# Island walks: a single named island's own coastal walk, cited as a
# self-contained appendix inside a shared/mainland book.map (Lesbos in
# 5.2, Euboia in 3.14, Karpathos+Rhodes in 5.2) rather than as its own
# book.map the way Ireland/Britain/Corsica/Sardinia/Sicily each get. Its
# points don't carry the word "island" in their own name (they're plain
# capes/cities -- "Kenaion promontory", "Chalkis on the Euripos"), so
# build_islands' name-matching leaves them all standalone; connecting them
# needs the same catalogue-order-adjacency approach build_coastlines uses,
# just scoped per *section* rather than per book.map. That narrower scope
# is the point: unlike a coastal walk, which is meant to chain every
# coastal section of a book.map into one continuous line, each
# island-classified section is already Ptolemy's own complete, bounded
# description of one island (or small island group) -- stitching across
# section boundaries here would bridge one island into whatever unrelated
# section happens to sit next to it in the text (confirmed the bug this
# fixes: §3.14.22 Euboia was bridging into its neighbouring sections
# instead of closing into its own loop).
#
# Scoped further to is_named_island_walk() sections specifically, not
# every ISLAND-classified section: an ISLAND section can equally be a
# *list* of several distinct islands (Ebuda, the Cyclades, "islands in the
# Ikarian sea"...), each cited with its own name and often just one or two
# points -- blanket-connecting a whole such section by catalogue-order
# adjacency draws a nonsense line hopping between unrelated islands
# (confirmed: doing so surfaced 9 new self-intersecting lines across the
# corpus). A named island's own walk is recognisable because it names
# itself once in the section's lead ("Lesbos...described as follows",
# "Description of Karpathos:") and then never repeats that name per point;
# a list keeps re-naming each island as it goes, which is exactly what
# is_named_island_walk's narrower pattern excludes.
def build_island_walks(sections: list[Section], resolved: dict[str, str],
                        occurrence_index: dict[tuple[str, int], Point],
                        cap: float = COASTLINE_CAP_DEG) -> list[Line]:
    lines: list[Line] = []
    for section in sections:
        if resolved[section.key] != ISLAND or not section.citations:
            continue
        if not is_named_island_walk(section):
            continue
        # A section can pack more than one named island's own walk back to
        # back (confirmed §5.2.33: "Description of Karpathos:" then,
        # mid-section, "Description of Rhodes island:") -- split there
        # first, or the two islands' points get connected to each other by
        # catalogue-order adjacency as if they were one landmass (confirmed
        # bug: drew a self-crossing loop jumping between Karpathos and
        # Rhodes). The first citation never triggers a split on its own --
        # its heading is already what made is_named_island_walk true via
        # section.lead_text.
        groups: list[list[Point]] = [[]]
        for citation in section.citations:
            point = occurrence_index[(section.key, citation.char_offset)]
            if groups[-1] and starts_new_named_island(citation.name_phrase):
                groups.append([])
            groups[-1].append(point)

        seq_num = 0
        for group in groups:
            runs = _split_into_runs(group, cap)
            runs = _stitch_runs(runs, cap)
            for trail in runs:
                seq_num += 1
                closed = _maybe_close_loop(trail, cap)
                lines.append(Line(
                    id=f"island-walk-{section.key}-{seq_num}",
                    kind="island",
                    book_map=section.book_map,
                    feature_name=None,
                    point_ids=[p.id for p in trail],
                    closed=closed,
                ))
    return lines


def build_all_lines(sections: list[Section], points: list[Point], resolved: dict[str, str],
                     occurrence_index: dict[tuple[str, int], Point]) -> list[Line]:
    streams = build_citation_streams(sections, occurrence_index)
    lines = []
    lines += build_coastlines(streams, resolved)
    lines += build_rivers(points, sections)
    lines += build_mountains(points)
    lines += build_islands(points, resolved)
    lines += build_island_walks(sections, resolved, occurrence_index)
    return lines
