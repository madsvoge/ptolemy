from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points, build_occurrence_index
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points
from ptolemy.coords import convert_points
from ptolemy.lines import Line, build_all_lines
from ptolemy.points import Point
from ptolemy.visualize import _loose_ends, _large_gap_ends


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


def _pt(pid, lon, lat):
    p = Point(id=pid, lon_ferro=lon, lat_ferro=lat, book_map="2.2")
    p.lon_modern, p.lat_modern = lon, lat
    return p


def test_large_internal_gap_flagged_on_a_closed_loop():
    # A trail can close into a loop (no red loose-end dot) while still
    # containing one citation-to-citation jump much bigger than its own
    # typical spacing -- invisible to a loose-end check, which only looks
    # at trail termini, not every edge along the way (confirmed on
    # Ireland's own real coastline: closed=True, no red dot, yet one
    # internal edge is 3.6 degrees against a ~0.9 degree median). Three
    # sides of this rectangle are walked in short 1-degree steps; only the
    # last side (the closing edge back to the start) is a single 3-degree
    # jump, standing in for a stretch of coast Ptolemy just didn't cite
    # any intermediate points for.
    coords = [
        (10, 60), (10, 61), (10, 62), (10, 63),
        (11, 63), (12, 63), (13, 63),
        (13, 62), (13, 61), (13, 60),
    ]
    points = [_pt(f"P{i}", lon, lat) for i, (lon, lat) in enumerate(coords, start=1)]
    point_by_id = {p.id: p for p in points}
    line = Line(id="l1", kind="coastline", book_map="2.2", feature_name=None,
                point_ids=[p.id for p in points], closed=True)
    gaps = _large_gap_ends([line], point_by_id, threshold=2.5)
    assert gaps == {"P1", "P10"}


def test_no_gap_flagged_when_all_edges_are_short():
    points = [_pt("P1", 10.0, 60.0), _pt("P2", 10.1, 60.1), _pt("P3", 10.2, 60.2)]
    point_by_id = {p.id: p for p in points}
    line = Line(id="l1", kind="coastline", book_map="2.2", feature_name=None,
                point_ids=["P1", "P2", "P3"], closed=False)
    assert _large_gap_ends([line], point_by_id, threshold=2.5) == set()
