"""Step 9 (advisory, not wired into the pipeline's own line data): suggest
candidate connections between loose coastal/island trail ends that the
line-builder left unconnected. This is explicitly a proximity *hint* for a
human reviewer, not a new source of ground truth -- a Stitch never edits
an existing Line's point_ids, it's a separate, clearly-labelled overlay so
a bad suggestion is obvious and easy to ignore or discard.
"""
from __future__ import annotations

from dataclasses import dataclass

from .lines import Line, _dist
from .points import Point

# Wider than COASTLINE_CAP_DEG (5.0) on purpose: within-book.map gaps under
# that cap are already closed by _stitch_runs, so anything left open and
# still worth suggesting is, by definition, further apart than that -- most
# often a cross-book.map jump (Ptolemy resumes a coast in the next section
# after an inland/boundary/mountain aside). This cap only bounds what's
# worth a human's time to look at, not a claim that the connection is real.
STITCH_SUGGEST_CAP_DEG = 10.0


@dataclass
class Stitch:
    from_point_id: str
    to_point_id: str
    from_line_id: str
    to_line_id: str
    distance: float


def _open_ends(lines: list[Line], kinds: tuple[str, ...] = ("coastline", "island")) -> list[tuple[str, str]]:
    """(line_id, point_id) for every loose end of an unclosed line."""
    ends: list[tuple[str, str]] = []
    for line in lines:
        if line.kind not in kinds or line.closed or len(line.point_ids) < 2:
            continue
        ends.append((line.id, line.point_ids[0]))
        ends.append((line.id, line.point_ids[-1]))
    return ends


def suggest_stitches(lines: list[Line], points: list[Point], cap: float = STITCH_SUGGEST_CAP_DEG) -> list[Stitch]:
    """Greedily pair up the nearest not-yet-used loose ends from *different*
    lines, closest pairs first -- the same greedy nearest-pair matching
    _stitch_runs already uses within a single book.map's own runs, just
    applied across every open trail in the whole reconstruction. Each
    endpoint is used in at most one suggestion; a trail's two ends are
    independent, so the same trail can pick up two different suggested
    neighbours, one on each end.
    """
    point_by_id = {p.id: p for p in points}
    ends = _open_ends(lines)

    candidates: list[tuple[float, tuple[str, str], tuple[str, str]]] = []
    for i in range(len(ends)):
        line_i, point_i = ends[i]
        for j in range(i + 1, len(ends)):
            line_j, point_j = ends[j]
            if line_i == line_j:
                continue
            d = _dist(point_by_id[point_i], point_by_id[point_j])
            if d <= cap:
                candidates.append((d, ends[i], ends[j]))
    candidates.sort(key=lambda c: c[0])

    used_points: set[str] = set()
    stitches: list[Stitch] = []
    for d, (line_i, point_i), (line_j, point_j) in candidates:
        if point_i in used_points or point_j in used_points:
            continue
        stitches.append(Stitch(point_i, point_j, line_i, line_j, d))
        used_points.add(point_i)
        used_points.add(point_j)
    return stitches
