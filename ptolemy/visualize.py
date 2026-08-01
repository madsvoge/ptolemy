"""Step 8: a minimal visual smoke test -- render every point and every
drawn line to a PNG with matplotlib. Not a finished map; just fast enough
feedback to catch parsing/classification bugs that are obvious on sight
but easy to miss reading JSON.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .lines import Line
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


def render_map(points: list[Point], lines: list[Line], out_path: str,
                title: str = "Ptolemy's Geographica, reconstructed from topostext (Nobbe)",
                book_map_filter: str | None = None, width_px: int = 2400,
                stitches: list[Stitch] | None = None) -> None:
    point_by_id = {p.id: p for p in points}
    plot_points = [p for p in points if book_map_filter is None or p.book_map == book_map_filter]
    plot_lines = [l for l in lines if book_map_filter is None or l.book_map == book_map_filter]
    loose_ends = _loose_ends(plot_lines)
    plot_line_ids = {l.id for l in plot_lines}
    plot_stitches = [
        s for s in (stitches or [])
        if s.from_line_id in plot_line_ids and s.to_line_id in plot_line_ids
    ]

    dpi = 150
    fig, ax = plt.subplots(figsize=(width_px / dpi, width_px / dpi * 9 / 16))

    for tag, color in _POINT_COLORS.items():
        xs = [p.lon_modern for p in plot_points if tag in p.tags and p.id not in loose_ends]
        ys = [p.lat_modern for p in plot_points if tag in p.tags and p.id not in loose_ends]
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
