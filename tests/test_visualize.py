from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points, build_occurrence_index
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points
from ptolemy.coords import convert_points
from ptolemy.lines import build_all_lines
from ptolemy.visualize import _loose_ends, _ring_coords


def _build(text):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    convert_points(points)
    occ_index = build_occurrence_index(points)
    lines = build_all_lines(sections, points, resolved, occ_index)
    return points, lines


def test_island_walk_loose_ends_are_flagged():
    # An island's own walk (build_island_walks) can be just as unclosed as
    # a mainland coastline -- confirmed regression: _loose_ends only
    # checked kind == "coastline" and silently skipped every open island
    # trail (e.g. Karpathos/Rhodes, §5.2.33).
    text = (
        "§ 5.2.33  Description of Karpathos:\n"
        "Thoantion promontory . 57°00' . 35°20'\n"
        "Poseidion city . 57°20' . 35°25'\n"
    )
    points, lines = _build(text)
    ends = _loose_ends(lines)
    assert len(ends) == 2


def test_ring_coords_closes_the_loop():
    # A "closed" trail's own drawn geometry must actually repeat the first
    # point at the end -- confirmed regression: `closed` was stored as
    # metadata only and never used when plotting, so the real closing edge
    # (e.g. Ireland's mouth of the Logia river back to Rhobogdium
    # promontory) was never drawn at all, reading as a broken seam on the
    # map despite the trail data being genuinely continuous.
    coords = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    assert _ring_coords(coords, closed=True) == coords + [coords[0]]
    assert _ring_coords(coords, closed=False) == coords


def test_ring_coords_leaves_short_trails_alone():
    coords = [(0.0, 0.0), (1.0, 0.0)]
    assert _ring_coords(coords, closed=True) == coords
