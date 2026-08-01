from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points, build_occurrence_index
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points
from ptolemy.coords import convert_points
from ptolemy.lines import build_all_lines, river_base_name, mountain_base_name

IRELAND_NORTH_WEST = """§ 2.2.1  Setting of Hivernia
North coast:
Boreum promontory 11°00' . 61°00'
Vennicnium promontory 12°50' . 61°20'
mouth of the Vidua river 13°00' . 61°00'
mouth of the Argita river 14°30' . 61°30'
Rhobogdium promontory 16°20' . 61°30'


§ 2.2.3  A description of the west side
from the Boreum promontory which is in 11°00' . 61°00'
mouth of the Ravius river 11°20' . 60°40'
Southern promontory 7°40' . 57°45'
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


def test_coastal_walk_becomes_one_trail_via_shared_junction():
    points, lines = _build(IRELAND_NORTH_WEST)
    coastlines = [l for l in lines if l.kind == "coastline"]
    assert len(coastlines) == 1
    trail = coastlines[0]
    # north run (5 points) and west run (3 points) share the Boreum node,
    # so the trail should visit every distinct point exactly once even
    # though Boreum was cited twice.
    assert len(trail.point_ids) == 7




def test_river_grouping_connects_mouth_and_source_by_shared_name():
    text = (
        "§ 2.9.1  A description of the coast\n"
        "mouth of the Rhenus river 25°00' . 53°00'\n\n\n"
        "§ 2.9.5  Below these\n"
        "source of the river Rhenus 27°00' . 50°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert len(rivers) == 1
    assert rivers[0].feature_name == "Rhenus"
    assert len(rivers[0].point_ids) == 2


def test_boundary_prose_mentioning_a_different_river_does_not_merge_groups():
    # A boundary sentence naming a *different* river in passing ("the
    # source of the river Danube") must land in its own Danube group, not
    # get folded into an unrelated Rhenus group just because both are
    # river-tagged points in the same book.map. Each group here has only
    # one citation, so a *correct* grouping draws no line at all (a single
    # point has no edge to draw) -- any line here would mean a mismerge.
    text = (
        "§ 2.9.1  A description of the coast\n"
        "mouth of the Rhenus river 25°00' . 53°00'\n\n\n"
        "§ 2.11.5  Of the mountains that girdle Germania, the most notable "
        "lie above the source of the river Danube 40°00' . 48°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert rivers == []


def test_mountain_grouping_handles_mt_abbreviation():
    text = (
        "§ 3.14.35  Mountains in the Peloponnese\n"
        "Mt. Taygeton 30°00' . 35°15'\n"
        "and Mt. Taygeton southern spur 30°10' . 35°05'\n"
    )
    points, lines = _build(text)
    mountains = [l for l in lines if l.kind == "mountain"]
    assert len(mountains) == 1
    assert mountains[0].feature_name == "Taygeton"


def test_no_line_self_intersects_on_this_small_fixture():
    from shapely.geometry import LineString
    points, lines = _build(IRELAND_NORTH_WEST)
    point_by_id = {p.id: p for p in points}
    for line in lines:
        coords = [(point_by_id[pid].lon_modern, point_by_id[pid].lat_modern) for pid in line.point_ids]
        if len(coords) < 2:
            continue
        assert LineString(coords).is_simple, f"{line.id} self-intersects"
