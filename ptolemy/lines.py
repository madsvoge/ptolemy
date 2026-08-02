"""Step 6: the line-drawing engine -- coastlines, rivers, mountain ranges,
islands. Reconstructs each as a MultiLineString-worthy set of trails built
purely from catalogue order and coordinates; no ground truth is consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re

from .classify import COASTAL, ISLAND, is_named_island_walk, is_new_region_declaration, starts_new_coastal_arc, starts_new_named_island
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


def _split_into_runs(ordered_points: list[Point], cap: float) -> list[list[Point]]:
    """Split a same-book.map, filtered point sequence into runs (trails)
    wherever consecutive points repeat (a dedup echo) or exceed the cap."""
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
            if len(current) >= 2:
                runs.append(current)
            current = [p]
    if len(current) >= 2:
        runs.append(current)
    return runs


def _stitch_runs(runs: list[list[Point]], cap: float) -> list[list[Point]]:
    """Greedily join two trails' loose ends when they land close together --
    the gap an interrupting non-coastal section leaves behind. All four
    end/start orientations are tried, not just forward (end_i -> start_j):
    confirmed necessary on this very text (2.2, Ireland, the brief's own
    worked example) -- its north-coast run (Boreum ... Rhobogdium) and its
    west/south/east run in fact join end-to-end (Rhobogdium next to the
    east coast's last point), not end-to-start, because Ptolemy's prose
    revisits the Boreum corner explicitly ("from the Boreum promontory
    which is in...") to *open* the second run rather than close the first."""
    runs = [list(r) for r in runs]
    merged = True
    while merged and len(runs) > 1:
        merged = False
        best = None  # (dist, i, j, orientation)
        for i, ti in enumerate(runs):
            for j, tj in enumerate(runs):
                if i == j:
                    continue
                candidates = [
                    (_dist(ti[-1], tj[0]), "end_start"),
                    (_dist(ti[-1], tj[-1]), "end_end"),
                    (_dist(ti[0], tj[-1]), "start_end"),
                    (_dist(ti[0], tj[0]), "start_start"),
                ]
                for d, orientation in candidates:
                    if d <= cap and (best is None or d < best[0]):
                        best = (d, i, j, orientation)
        if best:
            _, i, j, orientation = best
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
            runs = [r for idx, r in enumerate(runs) if idx not in (i, j)] + [new_run]
            merged = True
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
# Mountain ranges: grouped by a base name extracted from the point's own
# name text, not by catalogue adjacency (Ptolemy revisits a range at
# unrelated points in the text). A point whose phrase doesn't cleanly
# match one of these templates is left ungrouped rather than guessed at.
_MOUNTAIN_TEMPLATES = [
    re.compile(r"\bmt\.?\s+([A-Z][\w-]*)\b", re.I),
    re.compile(r"\b([A-Z][\w-]*)\s+mountains?\b"),
    re.compile(r"\bmountains?\s+of\s+(?:the\s+)?([A-Z][\w-]*)\b"),
]


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


def mountain_base_name(point: Point) -> str | None:
    for phrase in point.name_variants:
        name = _last_template_match(phrase, _MOUNTAIN_TEMPLATES)
        if name:
            return name
    return None


def _build_named_feature_lines(points: list[Point], kind: str, base_name_fn, cap: float) -> list[Line]:
    groups: dict[tuple[str, str], list[Point]] = {}
    display_names: dict[tuple[str, str], str] = {}
    for p in points:
        base = base_name_fn(p)
        if base is None:
            continue
        key = (p.book_map, base.lower())
        groups.setdefault(key, []).append(p)
        display_names.setdefault(key, base)

    lines: list[Line] = []
    for key, group_points in groups.items():
        book_map, _ = key
        base = display_names[key]
        group_points = sorted(group_points, key=lambda p: p.first_char_offset)
        runs = _split_into_runs(group_points, cap)
        for i, trail in enumerate(runs, start=1):
            lines.append(Line(
                id=f"{kind}-{book_map}-{base}-{i}",
                kind=kind,
                book_map=book_map,
                feature_name=base,
                point_ids=[p.id for p in trail],
            ))
    return lines


def build_mountains(points: list[Point], cap: float = MOUNTAIN_CAP_DEG) -> list[Line]:
    mountain_points = [p for p in points if "mountain" in p.tags]
    return _build_named_feature_lines(mountain_points, "mountain", mountain_base_name, cap)


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
    return _build_named_feature_lines(island_points, "island", island_base_name, cap)


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
    # Rivers deliberately not built yet -- the previous name-matching
    # approach (grouping any two same-named river citations across a
    # whole book.map, then a whole session's worth of forward-fill/bank-
    # city/delta-branch patches on top of it) didn't follow how Ptolemy's
    # own text actually organizes a river's course, and is being replaced
    # with a per-river, section-scoped "sources to mouth" reconstruction
    # instead: start from the section(s) that specifically describe one
    # named river's own course (its sources, bends, confluences), walk
    # only the points cited *within* those sections, then separately
    # locate that river's mouth -- which typically isn't in the river's
    # own section at all, but in an unrelated coastal section elsewhere in
    # the same book.map. One lesson worth keeping from the old approach:
    # a plain distance cap can't tell "one real river's citations are
    # just spread out" apart from "two different rivers coincidentally
    # share a name" (confirmed on Britain's own text -- two different
    # rivers both named "Alaunus", 6.9 degrees apart) -- whatever
    # heuristic walks a river's course needs its own way of guarding
    # against that, not just a cap.
    lines += build_mountains(points)
    lines += build_islands(points, resolved)
    lines += build_island_walks(sections, resolved, occurrence_index)
    return lines
