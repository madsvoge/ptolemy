from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points, build_occurrence_index
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points
from ptolemy.coords import convert_points
from ptolemy.lines import build_all_lines
from ptolemy.stitch import suggest_stitches

# Two separate book.maps, each an open (non-closing) coastal walk. The last
# point of the first and the first point of the second sit close together
# but in different book.maps, so build_coastlines' own per-book.map
# _stitch_runs never merges them -- exactly the cross-section gap a human
# stitch suggestion should catch.
TWO_TRAILS = """§ 2.2.1  A description of the coast
Point A 10°00' . 60°00'
Point B 11°00' . 60°00'
Point C 12°00' . 60°00'


§ 3.1.1  A description of the coast
Point D 12°10' . 60°10'
Point E 13°00' . 60°00'
Point F 14°00' . 60°00'
"""


def _build(text):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    convert_points(points)
    occ_index = build_occurrence_index(points)
    lines = build_all_lines(sections, points, resolved, occ_index)
    return points, lines


def test_suggests_stitch_between_nearby_loose_ends_in_different_book_maps():
    points, lines = _build(TWO_TRAILS)
    stitches = suggest_stitches(lines, points, cap=1.0)
    assert len(stitches) == 1
    point_by_id = {p.id: p for p in points}
    names = {point_by_id[stitches[0].from_point_id].name, point_by_id[stitches[0].to_point_id].name}
    assert names == {"Point C", "Point D"}


def test_no_stitch_suggested_beyond_the_cap():
    text = (
        "§ 2.2.1  A description of the coast\n"
        "Point A 10°00' . 60°00'\nPoint B 11°00' . 60°00'\nPoint C 12°00' . 60°00'\n\n\n"
        "§ 3.1.1  A description of the coast\n"
        "Point D 40°00' . 60°00'\nPoint E 41°00' . 60°00'\nPoint F 42°00' . 60°00'\n"
    )
    points, lines = _build(text)
    stitches = suggest_stitches(lines, points, cap=10.0)
    assert stitches == []


def test_does_not_pair_a_trails_own_two_ends():
    # A single short open trail has two loose ends of its own; they must
    # never be suggested as a stitch to each other (that's the separate
    # "should this close into a loop" question, not a cross-trail stitch).
    text = "§ 2.2.1  A description of the coast\nPoint A 10°00' . 60°00'\nPoint B 10°10' . 60°10'\n"
    points, lines = _build(text)
    stitches = suggest_stitches(lines, points)
    assert stitches == []


def test_each_endpoint_used_at_most_once():
    text = (
        "§ 2.2.1  A description of the coast\n"
        "Point A 10°00' . 60°00'\nPoint B 11°00' . 60°00'\nPoint C 12°00' . 60°00'\n\n\n"
        "§ 3.1.1  A description of the coast\n"
        "Point D 12°05' . 60°05'\nPoint E 13°00' . 60°00'\nPoint F 14°00' . 60°00'\n\n\n"
        "§ 4.1.1  A description of the coast\n"
        "Point G 12°08' . 60°08'\nPoint H 30°00' . 60°00'\nPoint I 31°00' . 60°00'\n"
    )
    points, lines = _build(text)
    stitches = suggest_stitches(lines, points)
    used = [s.from_point_id for s in stitches] + [s.to_point_id for s in stitches]
    assert len(used) == len(set(used))
