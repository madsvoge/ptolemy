"""Step 8: a minimal visual smoke test -- render every point and every
drawn line to a PNG with matplotlib. Not a finished map; just fast enough
feedback to catch parsing/classification bugs that are obvious on sight
but easy to miss reading JSON.
"""
from __future__ import annotations

import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .lines import Line, _dist
from .points import Point
from .stitch import Stitch

_COLORS = {
    "coastline": "#1f6f8b",
    "river": "#12b83a",
    "mountain": "#8d5524",
    "island": "#d4a017",
    # A confirmed manual stitch (data/manual_point_overrides.csv's own
    # stitch_to, or manual_added_points.csv's) -- solid, darker than the
    # dashed *suggested* stitch color below, so a reviewer can tell at a
    # glance which connections are still just candidates and which have
    # already been accepted.
    "stitch": "#7c1fa2",
}
_POINT_COLORS = {
    "coast": "#1f6f8b",
    "city": "#888888",
    "river": "#12b83a",
    "river_mouth": "#12b83a",
    "harbor": "#1f6f8b",
    "island": "#d4a017",
    "mountain": "#8d5524",
    "lake": "#3a86ff",
    "boundary": "#cccccc",
}
_LOOSE_END_COLOR = "#e63232"
_LOOSE_END_LABEL = "open trail end"
_STITCH_COLOR = "#c026d3"
_STITCH_LABEL = "suggested stitch"
# Deliberately not another shade of orange/gold: at small marker sizes on
# a dense map this was getting mistaken for "island" points (#d4a017,
# visually close to the old #f59e0b) despite being a completely different
# concept -- an "X" marker in near-black is unmistakable at any size and
# doesn't compete with any existing color in the legend.
_GAP_COLOR = "#111111"
_GAP_MARKER = "X"
_GAP_LABEL = "large internal gap"
# A *relative* threshold, not a single corpus-wide absolute number: a
# region Ptolemy knew well (the Mediterranean coasts) is cited far more
# densely than one he barely knew (Scandinavia, India beyond the Ganges,
# Serica) -- those trails' own *normal* spacing is already several degrees,
# so a fixed absolute cutoff flagged nearly every edge in them as "wrong"
# even though nothing there is anomalous, just sparse (reported: "why does
# Scandinavia/East Asia get this marker, there were no holes before").
# Flagging relative to each trail's *own* median edge length fixes that --
# a genuine oddity like Ireland's closed loop (median 0.79 degrees, one
# edge at 3.6) still stands out, while a uniformly sparse trail (3.5:
# Sarmatia's own median is already 3.26) no longer does. The absolute
# floor still applies on top, so a hyper-dense trail's minor variance
# (e.g. median 0.1, one edge at 0.3) doesn't get flagged just for being
# relatively bigger than its own tiny neighbours.
LARGE_GAP_RELATIVE_MULTIPLE = 4.0
LARGE_GAP_ABSOLUTE_FLOOR_DEG = 1.5


def _loose_ends(lines: list[Line]) -> set[str]:
    """First/last point of every *unclosed* coastline/island trail -- a
    dangling end that the line-builder never managed to connect or close
    into a loop. Rendered in a distinct color as a debugging aid: a real
    coastline is a closed ring or ends at a genuine map-edge/section
    boundary, so a cluster of these red points is usually exactly where
    to go looking for the next classification/stitching bug.

    Covers "island" as well as "coastline" -- an island's own walk
    (build_island_walks) can be just as unclosed as a mainland coastline,
    and was previously invisible here since this only checked "coastline"."""
    ends: set[str] = set()
    for line in lines:
        if line.kind not in ("coastline", "island") or line.closed or len(line.point_ids) < 2:
            continue
        ends.add(line.point_ids[0])
        ends.add(line.point_ids[-1])
    return ends


def _large_gap_ends(lines: list[Line], point_by_id: dict[str, Point],
                     relative_multiple: float = LARGE_GAP_RELATIVE_MULTIPLE,
                     absolute_floor: float = LARGE_GAP_ABSOLUTE_FLOOR_DEG) -> set[str]:
    """Both endpoints of any edge -- including a closed loop's own closing
    edge -- that's unusually large *for that trail*: bigger than both a
    flat absolute floor and some multiple of the trail's own median edge
    length. A trail can be "closed" (no red loose end) and still contain
    one citation-to-citation jump far bigger than its own typical spacing,
    which is exactly what a loose-end check alone can't see -- but judged
    against that trail's own scale, not one fixed number for every region
    regardless of how densely Ptolemy cited it."""
    ends: set[str] = set()
    for line in lines:
        if line.kind not in ("coastline", "island") or len(line.point_ids) < 2:
            continue
        ids = line.point_ids
        pairs = list(zip(ids, ids[1:]))
        if line.closed and len(ids) > 2:
            pairs.append((ids[-1], ids[0]))
        dists = [_dist(point_by_id[a], point_by_id[b]) for a, b in pairs]
        if not dists:
            continue
        median = statistics.median(dists)
        threshold = max(absolute_floor, relative_multiple * median)
        for (a_id, b_id), d in zip(pairs, dists):
            if d > threshold:
                ends.add(a_id)
                ends.add(b_id)
    return ends


def render_map(points: list[Point], lines: list[Line], out_path: str,
                title: str = "Ptolemy's Geographica, reconstructed from topostext (Nobbe)",
                book_map_filter: str | None = None, width_px: int = 2400,
                stitches: list[Stitch] | None = None) -> None:
    point_by_id = {p.id: p for p in points}
    plot_points = [p for p in points if book_map_filter is None or p.book_map == book_map_filter]
    plot_lines = [l for l in lines if book_map_filter is None or l.book_map == book_map_filter]
    loose_ends = _loose_ends(plot_lines)
    gap_ends = _large_gap_ends(plot_lines, point_by_id) - loose_ends
    plot_line_ids = {l.id for l in plot_lines}
    plot_stitches = [
        s for s in (stitches or [])
        if s.from_line_id in plot_line_ids and s.to_line_id in plot_line_ids
    ]

    dpi = 150
    fig, ax = plt.subplots(figsize=(width_px / dpi, width_px / dpi * 9 / 16))

    excluded = loose_ends | gap_ends
    for tag, color in _POINT_COLORS.items():
        xs = [p.lon_modern for p in plot_points if tag in p.tags and p.id not in excluded]
        ys = [p.lat_modern for p in plot_points if tag in p.tags and p.id not in excluded]
        if xs:
            ax.scatter(xs, ys, s=3, color=color, alpha=0.6, label=tag, zorder=2)

    for line in plot_lines:
        coords = [(point_by_id[pid].lon_modern, point_by_id[pid].lat_modern) for pid in line.point_ids]
        xs, ys = zip(*coords)
        ax.plot(xs, ys, color=_COLORS[line.kind], linewidth=0.8, zorder=1)

    loose_xs = [point_by_id[pid].lon_modern for pid in loose_ends]
    loose_ys = [point_by_id[pid].lat_modern for pid in loose_ends]
    if loose_xs:
        ax.scatter(loose_xs, loose_ys, s=10, color=_LOOSE_END_COLOR, alpha=0.9,
                   label=_LOOSE_END_LABEL, zorder=3)

    gap_xs = [point_by_id[pid].lon_modern for pid in gap_ends]
    gap_ys = [point_by_id[pid].lat_modern for pid in gap_ends]
    if gap_xs:
        ax.scatter(gap_xs, gap_ys, s=14, color=_GAP_COLOR, marker=_GAP_MARKER, alpha=0.9,
                   label=_GAP_LABEL, zorder=3)

    for i, s in enumerate(plot_stitches):
        a, b = point_by_id[s.from_point_id], point_by_id[s.to_point_id]
        ax.plot([a.lon_modern, b.lon_modern], [a.lat_modern, b.lat_modern],
                color=_STITCH_COLOR, linewidth=1.2, linestyle="--", alpha=0.85,
                zorder=4, label=_STITCH_LABEL if i == 0 else None)

    ax.set_title(title)
    ax.set_xlabel("longitude (modern, approximate)")
    ax.set_ylabel("latitude")
    ax.set_aspect("equal")
    ax.legend(markerscale=4, loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
