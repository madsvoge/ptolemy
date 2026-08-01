"""Step 6: the line-drawing engine -- coastlines, rivers, mountain ranges,
islands. Reconstructs each as a MultiLineString-worthy set of trails built
purely from catalogue order and coordinates; no ground truth is consulted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re

from .classify import COASTAL, ISLAND, MOUNTAIN
from .parser import Section
from .points import Point

# Starting point suggested by prior art on this same kind of reconstruction,
# re-derived empirically against this text: consecutive-citation gaps for
# resolved coastal-walk points have their 95th percentile at ~6.8 degrees
# and their median under 0.7 degrees, so 5 degrees excludes only the real
# long tail (genuine jumps between disjoint stretches) without touching the
# bulk of true adjacent-point edges.
COASTLINE_CAP_DEG = 5.0
RIVER_MOUNTAIN_CAP_DEG = 5.0
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


def build_citation_streams(sections: list[Section], occurrence_index: dict[tuple[str, int], Point]) -> dict[str, list[tuple[str, Point]]]:
    """Every citation, in document order, grouped by book.map: (section_key, Point)."""
    streams: dict[str, list[tuple[str, Point]]] = {}
    for section in sections:
        for citation in section.citations:
            point = occurrence_index[(section.key, citation.char_offset)]
            streams.setdefault(section.book_map, []).append((section.key, point))
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


def build_coastlines(streams: dict[str, list[tuple[str, Point]]], cap: float = COASTLINE_CAP_DEG) -> list[Line]:
    lines: list[Line] = []
    for book_map, seq in streams.items():
        coastal_points = [p for _key, p in seq if "coast" in p.tags]
        runs = _split_into_runs(coastal_points, cap)
        runs = _stitch_runs(runs, cap)
        for i, trail in enumerate(runs, start=1):
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
_RIVER_TEMPLATES = [
    re.compile(r"\bmouths?\s+of\s+(?:the\s+)?([A-Z][\w-]*)\b"),
    re.compile(r"\bsources?\s+of\s+(?:the\s+)?(?:river\s+)?([A-Z][\w-]*)\b"),
    re.compile(r"\b([A-Z][\w-]*)\s+river\b"),
    re.compile(r"\bbend\s+of\s+(?:the\s+)?([A-Z][\w-]*)\b"),
]
_MOUNTAIN_TEMPLATES = [
    re.compile(r"\bmt\.?\s+([A-Z][\w-]*)\b", re.I),
    re.compile(r"\b([A-Z][\w-]*)\s+mountains?\b"),
    re.compile(r"\bmountains?\s+of\s+(?:the\s+)?([A-Z][\w-]*)\b"),
]

_GENERIC_RIVER_WORDS = {"river", "the", "sea", "sources", "source"}


def river_base_name(point: Point) -> str | None:
    for phrase in point.name_variants:
        for template in _RIVER_TEMPLATES:
            m = template.search(phrase)
            if m and m.group(1).lower() not in _GENERIC_RIVER_WORDS:
                return m.group(1)
    return None


def mountain_base_name(point: Point) -> str | None:
    for phrase in point.name_variants:
        for template in _MOUNTAIN_TEMPLATES:
            m = template.search(phrase)
            if m:
                return m.group(1)
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


def build_rivers(points: list[Point], cap: float = RIVER_MOUNTAIN_CAP_DEG) -> list[Line]:
    river_points = [p for p in points if "river" in p.tags or "river_mouth" in p.tags]
    return _build_named_feature_lines(river_points, "river", river_base_name, cap)


def build_mountains(points: list[Point], cap: float = RIVER_MOUNTAIN_CAP_DEG) -> list[Line]:
    mountain_points = [p for p in points if "mountain" in p.tags]
    return _build_named_feature_lines(mountain_points, "mountain", mountain_base_name, cap)


# ---------------------------------------------------------------------
# Islands: only connect points that are unambiguously several capes of the
# *same* named island cited consecutively -- otherwise leave the points
# standalone. Reuses the exact same name-grouping/run-splitting machinery
# as rivers/mountains (not a bespoke mechanism), scoped to island-tagged
# points inside island-classified sections.
_ISLAND_TEMPLATE = re.compile(r"\b([A-Z][\w-]*)\s+island\b|\bisland\s+of\s+([A-Z][\w-]*)\b")


def island_base_name(point: Point) -> str | None:
    for phrase in point.name_variants:
        m = _ISLAND_TEMPLATE.search(phrase)
        if m:
            return m.group(1) or m.group(2)
    return None


def build_islands(points: list[Point], resolved: dict[str, str], cap: float = RIVER_MOUNTAIN_CAP_DEG) -> list[Line]:
    island_points = [
        p for p in points
        if "island" in p.tags and any(resolved[o.section_key] == ISLAND for o in p.occurrences)
    ]
    return _build_named_feature_lines(island_points, "island", island_base_name, cap)


def build_all_lines(sections: list[Section], points: list[Point], resolved: dict[str, str],
                     occurrence_index: dict[tuple[str, int], Point]) -> list[Line]:
    streams = build_citation_streams(sections, occurrence_index)
    lines = []
    lines += build_coastlines(streams)
    lines += build_rivers(points)
    lines += build_mountains(points)
    lines += build_islands(points, resolved)
    return lines
