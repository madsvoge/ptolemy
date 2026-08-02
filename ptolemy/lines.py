"""Step 6: the line-drawing engine -- coastlines, rivers, mountain ranges,
islands. Reconstructs each as a MultiLineString-worthy set of trails built
purely from catalogue order and coordinates; no ground truth is consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re

from .classify import BOUNDARY, COASTAL, ISLAND, RIVER, is_named_island_walk, is_new_region_declaration, starts_new_coastal_arc, starts_new_named_island
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
# Rivers: "sources to mouth", per the user's own methodology -- the exact
# opposite of the reverted, whole-book_map name-matching approach this
# module used earlier. A river's course is walked from its own citations
# -- but "its own citations" turns out not to mean only the ones inside a
# RIVER-classified section (see classify.py). Confirmed real and common
# (32 cases corpus-wide, e.g. §2.11.1: "Mouths of the river Amisius" /
# "Sources of the river"; §7.3.2: "the mouth of the river Aspithra" /
# "Sources of the river..."; §3.1.5's Tiber: "mouth of the Tiber river" /
# "where the river turns toward the west"): an ordinary COASTAL walk
# routinely gives a river's mouth and then, a citation or two later,
# *also* gives that same river's own source/turn/confluence -- Ptolemy's
# text doesn't reserve that content for a dedicated river section at all.
# So a book.map's own COASTAL sections are walked by the exact same
# mechanism as its RIVER sections, just with a narrower rule for what may
# *open* a fresh river (see the is_river distinction in
# _walk_river_sections): only a citation that says "mouth of/at NAME
# river" may start tracking a not-yet-seen name outside a RIVER section --
# a bare "NAME river" mention must not, or every province whose boundary
# happens to be phrased "...by the Euphrates river at COORD" would spawn
# its own throwaway group. Inside a RIVER section (whose own classify.py
# signal already establishes "this is about a river's course"), any of
# the forms below may open one, same as always.
#
# Within that scope, a citation is one of:
#   - a *dual* declaration -- a confluence/junction ("Confluence of the
#     Koa and Indus") or a bifurcation ("Where it bifurcates into the
#     Goaris and Binda") -- naming two rivers at once. This citation is a
#     shared graph node between both of them (confirmed throughout book
#     7.1's Indus/Ganges tributary network, §7.1.27/§7.1.29/§7.1.32).
#   - a *single* declaration of the river's own name ("Sources of the
#     River Solen...", "the Araxes river, which flows...", "the Lykos,
#     the springs of which..."), which becomes (or continues) the
#     "current" river for this section's walk. If the same phrase *also*
#     says this river joins/branches into another one by name ("where it
#     joins with the Dorias river"), the point is a shared node between
#     the outgoing and incoming rivers, same as a dual declaration.
#   - a *join* onto a river named only implicitly ("it joins the
#     Euphrates at", "the junction with the Tigris at", "this one flows
#     into the Oxos at") -- shared between whatever was "current" and the
#     named target, which becomes "current" from here on.
#   - an anaphoric continuation with no name of its own ("The point where
#     it turns", "first turn of the river") -- continues "current".
# "current" resets to nothing at the start of every section walked (never
# carried over from the previous section, even an adjacent one in the
# same catalogue run -- confirmed needed by §7.1.34, which names Baris
# then Solen back to back before one shared "the point where it turns"
# that belongs only to whichever was named last, Solen). A river's own
# *group* of points, however, persists across the whole book.map: once
# any section opens (or re-mentions) a name, a later section's citation
# for that same name -- in either document-order direction, mouth-first
# or source-first -- joins the same group (confirmed both orders happen:
# §7.1's Indian rivers give the source in a RIVER section *before* their
# coastal mouth citation; §2.11.1 gives the mouth *before* its section's
# own "Sources of the river").
#
# A citation that names no river and isn't a recognizable continuation
# idiom is dropped from the walk rather than guessed at -- confirmed real
# and necessary: §6.10.4 opens on an unnamed tributary of the Margos and
# then, with no further river vocabulary at all, lists that region's
# ordinary bank cities (Rea, Antiocheia Margiane...); blanket-continuing
# "current" through those would draw a nonsense river line through city
# coordinates. The heuristic used: a citation that starts with a capital
# letter (reads as its own fresh, standalone proper-noun citation, the
# same shape an ordinary city citation has) is only trusted as a
# continuation if it *also* carries real river vocabulary somewhere in it
# (confirmed needed both ways: rejects "Draga"/"Sarouon" after "Source of
# Styx water" §6.7.40, but keeps "another in Ottorokorrha" after
# "Bautisos...has one of its sources..." §6.16.3, which starts lowercase).
#
# No group ever needing a separate "find the matching mouth" search is
# the whole reason for walking COASTAL sections in the same pass as RIVER
# ones: the mouth citation is just another member of the same
# document-order group, wherever in the book.map it happens to sit. A
# river with no mouth citation anywhere in its own book.map (or none this
# module recognizes) simply ends its trail at its last real citation --
# not an error: plenty of these are tributaries whose text already ends
# them at a confluence with a bigger named river instead (confirmed
# throughout book 7.1's Indus network -- Koa/Souastos/Bidaspes/Sandabal/
# Adris/Bidasis never get their own "Mouth of X" citation, only ever a
# confluence with Indus).
_RIVER_NAME_STOPWORDS = {
    "the", "a", "an", "and", "of", "in", "on", "at", "to", "from", "which",
    "is", "below", "above", "after", "between", "near", "next", "this",
    "that", "its", "toward", "towards", "then", "again", "first", "second",
    "third", "another", "one", "part", "other", "same", "such", "these",
    "those", "each", "it",
}

# Its own name, checked ahead of the general last-match-wins priority
# below (see _river_primary_name) -- a multi-outlet delta citation
# routinely names both the *river* and that specific outlet's own name
# in one phrase ("The most western mouth of the River Indus called
# Sagapa", confirmed §7.1.2), and last-match-wins would otherwise prefer
# "Sagapa" (mentioned last, closest to the coordinate) over "Indus",
# losing the river's own mouth entirely -- confirmed regression: every
# tributary that confluences into the Indus or Ganges (Koa, Souastos,
# Bidaspes, Sandabal, Adris, Bidasis, Zaradros; Diamouna, Sarabos) then
# had nowhere left to reach, since Indus/Ganges's own trail never
# extended to any of their delta's real mouth citations.
_RIVER_MOUTH_NAME_RE = re.compile(r"(?i:mouths?)\s+of\s+(?i:the\s+)?(?i:river\s+)?([A-Z][\w-]*)")
_RIVER_NAME_TEMPLATES = [
    # "headwaters" is this text's other synonym for "sources" (confirmed
    # §2.10.4: "the headwaters of the Druentia at").
    re.compile(r"(?i:sources?|springs?|headwaters?)\s+of\s+(?i:the\s+)?(?i:river\s+)?([A-Z][\w-]*)"),
    _RIVER_MOUTH_NAME_RE,
    # "The fork of the Rhabon river..." -- a boundary line that traces a
    # river's own fork/bend points (confirmed §3.8.1, Dacia's boundary
    # following the Tibiskos/Rhabon/Kiabros/Aloutas in turn) is textually
    # a BOUNDARY-classified section, not a RIVER or COASTAL one, but each
    # of these citations is still unambiguously a river-topology point.
    # Without its own template here, "fork" isn't in the name-extraction
    # list at all (only in the continuation vocabulary below), so a fresh
    # river name introduced this way was invisible and silently swept
    # into whichever *other* name happened to be "current" instead.
    re.compile(r"(?i:forks?)\s+of\s+(?i:the\s+)?(?i:river\s+)?([A-Z][\w-]*)"),
    re.compile(r"([A-Z][\w-]*)\s+(?i:river)\b"),
    re.compile(r"(?i:river)\s+([A-Z][\w-]*)\b"),
    re.compile(r"(?i:so-called)\s+(?:the\s+)?([A-Z][\w-]*)"),
    re.compile(r"(?i:called)\s+(?:the\s+)?([A-Z][\w-]*)"),
    re.compile(r"([A-Z][\w-]*)(?:\s+river)?,\s*(?i:the\s+)?(?i:springs|sources)\s+of\s+which"),
    re.compile(r"([A-Z][\w-]*),\s*(?i:whose\s+springs\s+are)"),
    # "two rivers, the Oichardes..." -- an appositive naming right after
    # the generic word "river(s)" itself (confirmed §6.16.3), distinct
    # from the "NAME river"/"river NAME" templates above (no "river" word
    # sits directly next to the name here).
    re.compile(r"(?i:rivers?),\s+(?:the\s+)?([A-Z][\w-]*)"),
]
_RIVER_DUAL_TEMPLATES = [
    re.compile(r"(?i:confluence|junction)\s+of\s+(?:the\s+)?([A-Z][\w-]*)\s+and\s+(?:the\s+)?([A-Z][\w-]*)"),
    # "the confluence of the Isar with the Rhodanus" -- the same idiom,
    # connected with "with" instead of "and" (confirmed §2.10.4).
    re.compile(r"(?i:confluence|junction)\s+of\s+(?:the\s+)?([A-Z][\w-]*)\s+with\s+(?:the\s+)?([A-Z][\w-]*)"),
    # "the Hermos and the Paktolos rivers unite" -- the reverse word order
    # of the "confluence of A and B" template above (confirmed §5.2.6).
    re.compile(r"([A-Z][\w-]*)\s+and\s+(?:the\s+)?([A-Z][\w-]*)\s+(?i:rivers?)?\s*(?i:unite\w*)"),
]
# "Where it bifurcates into the Goaris and Binda" -- unlike the dual
# templates above, where *both* parties are named in the citation itself,
# a bifurcation/split names only its two children; the party doing the
# bifurcating ("it") is only ever "current", implicit. Kept as its own
# template list so that party gets registered too (see the walk loop) --
# confluence/junction/unite citations must NOT also touch "current" the
# same way (confirmed regression: §7.1.27's "Confluence of the Koa and
# Indus" would otherwise wrongly also extend whatever unrelated river,
# e.g. Zaradros, happened to be "current" at that point in the walk).
_RIVER_BRANCH_TEMPLATES = [
    re.compile(r"(?i:bifurcat\w*|splits?)\s+into\s+(?:the\s+)?([A-Z][\w-]*)\s+and\s+(?:the\s+)?([A-Z][\w-]*)"),
]
_RIVER_JOIN_TEMPLATES = [
    re.compile(r"(?i:confluence|junction)\s+with\s+(?:the\s+)?(?i:river\s+)?([A-Z][\w-]*)"),
    re.compile(r"(?i:joins?|unites?)\s+(?:with\s+)?(?:the\s+)?([A-Z][\w-]*)"),
    re.compile(r"(?i:flows?\s+into)\s+(?:the\s+)?(?i:river\s+)?([A-Z][\w-]*)"),
    re.compile(r"(?i:branch(?:es)?\s+off\s+from)\s+(?:the\s+)?(?i:river\s+)?([A-Z][\w-]*)"),
]
# Whether a single-name citation ("...the Euphrates river at") is *also* a
# join event onto whatever was "current" before it -- distinct from a bare
# declaration ("Sources of the River Koa") which starts fresh instead.
_RIVER_JOIN_TRIGGER_RE = re.compile(
    r"\bjoins?\b|\bunites?\b|\bconfluence\b|\bjunction\b|\bflows?\s+into\b|\bbranch(?:es)?\s+off\s+from\b", re.I,
)
# Same bare-word philosophy as tag.py's own _RIVER_MOUTH_RE (a "mouth of"
# citation is just as often worded the other way round, "NAME river
# mouth", or without "of" at all -- word order isn't the reliable part,
# the word "mouth(s)" itself is), including its one exception: "mouth of
# Pontos" is Ptolemy's idiom for the Bosporos strait, not a river mouth.
# Used both to open a brand-new river name outside a RIVER section (see
# is_river_section below) and to know which end of a finished trail is
# the river's own downstream terminus (see _reorder_river_trail).
_RIVER_MOUTH_WORD_RE = re.compile(
    r"\bmouths?\s+of\b(?!\s+Pontos\b)|\bmouths?\b(?!\s+of\s+Pontos\b)|\bestuary\b|\boutlet\b", re.I,
)
# A river's *fork* (confirmed §3.8.1, Dacia's boundary tracing the
# Tibiskos/Rhabon/Kiabros/Aloutas in turn) is just as unambiguous an
# opening idiom outside a RIVER section as its mouth -- but unlike a
# mouth, a fork is a mid-course bifurcation, not the river's own
# downstream end, so it's kept separate from _RIVER_MOUTH_WORD_RE rather
# than folded into it.
_RIVER_FORK_WORD_RE = re.compile(r"\bforks?\s+of\b", re.I)
# A river's own *source* is just as unambiguous an opening idiom outside a
# RIVER section as its mouth or fork -- confirmed missed on §2.10.4 (the
# Isar/Druentia, two Alpine tributaries of the Rhodanus given entirely
# within an ordinary COASTAL section): "sources of the Isar" was correctly
# extracting the name "Isar" already, but the opening gate only ever
# recognized mouth/fork, so this whole section -- both tributaries'
# sources, headwaters, and their confluences with the Rhodanus -- was
# silently dropped rather than connected.
_RIVER_SOURCE_WORD_RE = re.compile(r"\bsources?\b|\bsprings?\b|\bheadwaters?\b", re.I)
_RIVER_OPENING_WORD_RE = re.compile(
    _RIVER_MOUTH_WORD_RE.pattern + r"|" + _RIVER_FORK_WORD_RE.pattern + r"|" + _RIVER_SOURCE_WORD_RE.pattern, re.I,
)
# A citation with no name of its own is only trusted as a continuation if
# it carries this vocabulary *or* doesn't read as its own fresh
# proper-noun citation to begin with (see the capitalisation check in
# _looks_like_river_continuation).
_RIVER_CONTINUATION_VOCAB_RE = re.compile(
    r"\bturns?\b|\bbends?\b|\bsources?\b|\bsprings?\b|\bconfluence\b|\bjoins?\b|\bunites?\b"
    r"|\bforks?\b|\bbifurcat\w*\b|\bsplits?\s+into\b|\blakes?\b|\bdivert\w*\b|\briver\b"
    # "head of" is only river vocabulary when it actually says "river"
    # (optionally with a name in between, "head of the Dorias river") --
    # a bare "head of" alone also means the innermost point of a gulf/bay
    # (confirmed §7.3.2's "head of Wild Beast Gulf", a real coastal
    # point), and without this qualifier that got swept into the
    # preceding river's own trail purely because "head of" matched.
    r"|\bhead\s+of\s+(?:the\s+)?(?:[\w-]+\s+)?river\b",
    re.I,
)
# Hand-confirmed spelling variants between a river's own citation in one
# part of a book.map and its own citation elsewhere in the same book.map
# (typically a RIVER section's source/confluence wording vs. a coastal
# section's separately catalogued "Mouth of X") -- not a generic fuzzy
# matcher, which was tried and rejected: at any cutoff loose enough to
# catch these, it also merges genuinely different rivers that happen to
# be short and similar (confirmed false positive: Baris/Adris, Bidasis/
# Bidaspes, both real, distinct rivers in book 7.1's own tributary
# network).
_RIVER_NAME_ALIASES = {
    "mophis": "moghis",
    "manada": "manda",
    "benda": "binda",
    "bibasis": "bidasis",
}


def _river_last_match(phrase: str, templates: list[re.Pattern]) -> str | None:
    best: tuple[int, str] | None = None
    for template in templates:
        for m in template.finditer(phrase):
            name = m.group(1)
            if name.lower() in _RIVER_NAME_STOPWORDS:
                continue
            if best is None or m.start() > best[0]:
                best = (m.start(), name)
    return best[1] if best else None


def _river_primary_name(phrase: str) -> str | None:
    """Like _river_last_match(phrase, _RIVER_NAME_TEMPLATES), but a "mouth
    of NAME" match wins outright over a later, more-specific name in the
    same phrase (see _RIVER_MOUTH_NAME_RE) -- *only* when the phrase names
    just that one single mouth. A restated boundary/orientation sentence
    routinely mentions two different rivers' mouths in the same breath
    ("between which and the mouth of the Kyrus is the mouth of the Araxes
    river", confirmed §5.13.3; "mouth of the Padus river...likewise
    Atrianos river mouth", confirmed §3.1.25), and there last-match-wins
    is still correct -- the *last* one is the citation's real subject,
    the same "restates an earlier river before settling on the one the
    coordinate is really for" pattern mountain_base_name's own docstring
    describes."""
    if len(_RIVER_MOUTH_WORD_RE.findall(phrase)) == 1:
        m = _RIVER_MOUTH_NAME_RE.search(phrase)
        if m and m.group(1).lower() not in _RIVER_NAME_STOPWORDS:
            return m.group(1)
    return _river_last_match(phrase, _RIVER_NAME_TEMPLATES)


def _river_dual_names(phrase: str) -> tuple[str, str] | None:
    for template in _RIVER_DUAL_TEMPLATES:
        m = template.search(phrase)
        if m and m.group(1).lower() not in _RIVER_NAME_STOPWORDS and m.group(2).lower() not in _RIVER_NAME_STOPWORDS:
            return m.group(1), m.group(2)
    return None


def _river_branch_names(phrase: str) -> tuple[str, str] | None:
    for template in _RIVER_BRANCH_TEMPLATES:
        m = template.search(phrase)
        if m and m.group(1).lower() not in _RIVER_NAME_STOPWORDS and m.group(2).lower() not in _RIVER_NAME_STOPWORDS:
            return m.group(1), m.group(2)
    return None


def _looks_like_river_continuation(phrase: str) -> bool:
    stripped = phrase.strip()
    if not stripped:
        return False
    if stripped[0].isupper() and not _RIVER_CONTINUATION_VOCAB_RE.search(stripped):
        return False
    return True


def _normalize_river_name(name: str) -> str:
    return _RIVER_NAME_ALIASES.get(name.lower(), name.lower())


def _reorder_river_trail(entries: list[tuple[Point, str, bool]]) -> list[Point]:
    """A mouth citation is walked wherever document order puts it, which
    is routinely *before* the rest of its river's own course -- confirmed
    the ordinary case, since a book.map's coastal walk (where a mouth is
    cited) almost always comes before its later RIVER section (where the
    source/bends are). Left as document order, that produces a trail that
    visits the mouth first and then jumps back upstream, self-intersecting
    the drawn line (confirmed §7.1's Namados).
    A *whole run* of consecutive mouth citations (a multi-outlet delta,
    e.g. §2.9.1's Rhine: western/middle/eastern mouth cited back to back)
    is treated as one unit -- it stays exactly where it was walked only if
    the entry right after the run continues from the *same section* as
    the run's own last citation, i.e. it's genuinely telling the river's
    course in mouth-to-head direction (confirmed §3.1.24's Padus,
    §5.1.6's Sangarios: the mouth opens their own RIVER section and the
    rest of that section's citations follow it directly). Every other
    mouth run is moved to the trail's end instead (in its own internal
    order), since "the mouth" is definitionally the river's downstream
    terminus."""
    ordered: list[Point] = []
    trailing_mouths: list[Point] = []
    i, n = 0, len(entries)
    while i < n:
        point, section_key, is_mouth = entries[i]
        if not is_mouth:
            ordered.append(point)
            i += 1
            continue
        run_end = i
        while run_end < n and entries[run_end][2]:
            run_end += 1
        run = entries[i:run_end]
        continues_in_place = run_end < n and entries[run_end][1] == run[-1][1]
        target = ordered if continues_in_place else trailing_mouths
        target.extend(p for p, _, _ in run)
        i = run_end
    return ordered + trailing_mouths


def _walk_river_sections(sections_with_flags: list[tuple[Section, bool]],
                          occurrence_index: dict[tuple[str, int], Point]) -> tuple[dict[str, list[Point]], dict[str, str]]:
    """Group every citation across this book.map's sections by the named
    river it belongs to (see the big comment above). ``sections_with_flags``
    pairs each section with whether it is itself RIVER-classified --
    outside a RIVER section, only a "mouth of..."/"fork of..." citation
    may open a name this walk hasn't seen yet. Returns each group already
    reordered (see _reorder_river_trail) so its mouth sits at whichever
    end the text actually places it.

    "current" persists across a section boundary when both sides are
    RIVER-classified, not just within one section -- a river's own
    narrative routinely continues into the very next RIVER section
    without repeating its name (confirmed §7.1.31 -> §7.1.32: Namados/
    Baris bend, then confluence with Moghis, and only *then*, in the
    next section, the bifurcation into Goaris and Binda -- two sections
    telling one continuous course). It's still only ever read forward,
    and a section that opens with its own explicit declaration (a
    "Sources of..."/"mouth of..." citation) immediately overrides
    whatever was "current" before it, same as always."""
    raw_groups: dict[str, list[tuple[Point, str, bool]]] = {}
    seen_ids: dict[str, set[str]] = {}
    display_names: dict[str, str] = {}
    current: str | None = None

    def key_for(name: str) -> str:
        key = _normalize_river_name(name)
        if key not in raw_groups:
            raw_groups[key] = []
            seen_ids[key] = set()
            display_names[key] = name
        return key

    def register(key: str, point: Point, phrase: str, section_key: str) -> None:
        # A river's mouth or turn is occasionally restated verbatim as the
        # orientation landmark opening an unrelated later citation (the
        # same idiom build_coastlines already guards against) -- without
        # this, the point re-enters its own group a second time instead
        # of being recognized as the same, already-visited citation.
        if point.id in seen_ids[key]:
            return
        is_mouth = bool(_RIVER_MOUTH_WORD_RE.search(phrase))
        raw_groups[key].append((point, section_key, is_mouth))
        seen_ids[key].add(point.id)

    previous_was_river_section = False
    for section, is_river_section in sections_with_flags:
        # "current" only carries into a new section when *both* sides of
        # the boundary are themselves RIVER-classified (confirmed needed
        # §7.1.31 -> §7.1.32, both RIVER: Moghis's confluence carries
        # straight into the next section's bifurcation). Anywhere else,
        # carrying it through the anaphoric-continuation path picked up
        # unrelated boundary/mountain content that merely opens with a
        # bare lowercase "and" (confirmed regression: §4.2's Ampsagas
        # absorbing "Cinnaba mountains"/"Beryn mountains" this way once
        # persistence was unconditional). A RIVER section's own explicit
        # citations stay just as reliable a source of *new* current as
        # ever -- this only narrows how far a name-free continuation is
        # trusted to reach.
        if not (previous_was_river_section and is_river_section):
            current = None
        previous_was_river_section = is_river_section
        for citation in section.citations:
            point = occurrence_index[(section.key, citation.char_offset)]
            phrase = citation.name_phrase

            dual = _river_dual_names(phrase)
            if dual:
                key_a, key_b = key_for(dual[0]), key_for(dual[1])
                register(key_a, point, phrase, section.key)
                if key_b != key_a:
                    register(key_b, point, phrase, section.key)
                current = key_b
                continue

            # A bifurcation/split names only its two children -- the
            # party doing the bifurcating is "current", implicit in the
            # citation's own "it" (confirmed §7.1.32: "Where it
            # bifurcates into the Goaris and Binda" continues straight on
            # from §7.1.31's Moghis confluence). Registering onto current
            # too is what makes that trunk's own trail end exactly at the
            # branch point, instead of stopping short one citation early.
            branch = _river_branch_names(phrase)
            if branch:
                if current is not None:
                    register(current, point, phrase, section.key)
                key_a, key_b = key_for(branch[0]), key_for(branch[1])
                register(key_a, point, phrase, section.key)
                if key_b != key_a:
                    register(key_b, point, phrase, section.key)
                current = key_b
                continue

            name = _river_primary_name(phrase)
            if name:
                is_new = _normalize_river_name(name) not in raw_groups
                if is_new and not is_river_section and current is None and not _RIVER_OPENING_WORD_RE.search(phrase):
                    # Outside a RIVER section, a bare "NAME river" mention
                    # is too common and ambiguous to trust as an opening
                    # (confirmed: it's this text's routine way of citing a
                    # boundary line, "bounded... by the Euphrates river at
                    # COORD") -- only a citation that says this is the
                    # river's *mouth* or *fork* may start tracking a
                    # brand-new name here.
                    continue
                key = key_for(name)
                if current is not None and current != key and _RIVER_JOIN_TRIGGER_RE.search(phrase):
                    register(current, point, phrase, section.key)
                register(key, point, phrase, section.key)
                current = key
                continue

            target = _river_last_match(phrase, _RIVER_JOIN_TEMPLATES)
            if target:
                is_new = _normalize_river_name(target) not in raw_groups
                if is_new and not is_river_section and current is None:
                    continue
                key = key_for(target)
                if current is not None and current != key:
                    register(current, point, phrase, section.key)
                register(key, point, phrase, section.key)
                current = key
                continue

            if current is not None and _looks_like_river_continuation(phrase):
                register(current, point, phrase, section.key)

    groups = {key: _reorder_river_trail(entries) for key, entries in raw_groups.items()}
    return groups, display_names


def build_rivers(sections: list[Section], resolved: dict[str, str],
                  occurrence_index: dict[tuple[str, int], Point]) -> list[Line]:
    # Walked for RIVER, COASTAL, and BOUNDARY sections -- confirmed real
    # river-course pairs show up not just in COASTAL sections (§2.11.1,
    # §7.3.2, §3.1.5) but in a BOUNDARY one too (§3.8.1, Dacia's boundary
    # tracing several rivers' own fork points). The is_river_section flag
    # passed into _walk_river_sections is what keeps this safe: outside a
    # RIVER section, a name can only be *opened* by its own mouth/fork
    # idiom, never a bare mention. INLAND and ISLAND sections are
    # deliberately excluded even with that guard: their own bank-city or
    # island-extremity lists routinely carry a lowercase-leading, name-free
    # continuation phrase right after an unrelated river mouth mention (a
    # region's boundary/inland list opens by restating the coastal walk's
    # last river, then moves on to ordinary cities) and the continuation
    # heuristic below can't always tell that apart from the same river's
    # own next course point (confirmed regression: Iuliobona/Ratomagus/...
    # swept into the Sequana's own trail via §2.8's inland city list;
    # Vistula's island-extremities swept in via §2.11.16).
    sections_by_book_map: dict[str, list[tuple[Section, bool]]] = {}
    for section in sections:
        section_type = resolved[section.key]
        if section_type not in (RIVER, COASTAL, BOUNDARY):
            continue
        sections_by_book_map.setdefault(section.book_map, []).append((section, section_type == RIVER))

    lines: list[Line] = []
    for book_map, secs in sections_by_book_map.items():
        groups, display_names = _walk_river_sections(secs, occurrence_index)
        for key, trail in groups.items():
            if len(trail) < 2:
                continue
            lines.append(Line(
                id=f"river-{book_map}-{display_names[key]}",
                kind="river",
                book_map=book_map,
                feature_name=display_names[key],
                point_ids=[p.id for p in trail],
            ))
    return lines


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
    lines += build_rivers(sections, resolved, occurrence_index)
    lines += build_mountains(points)
    lines += build_islands(points, resolved)
    lines += build_island_walks(sections, resolved, occurrence_index)
    return lines
