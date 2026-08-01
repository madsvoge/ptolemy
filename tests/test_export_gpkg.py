import sqlite3

from ptolemy.classify import classify_sections
from ptolemy.coords import convert_points
from ptolemy.export_gpkg import _line_geometry, write_geopackage
from ptolemy.lines import build_all_lines
from ptolemy.parser import parse_sections
from ptolemy.points import Point, build_occurrence_index, dedup_points
from ptolemy.tag import propagate_bare_connector_tags, propagate_river_context, tag_points

TEXT = """§ 2.2.1  Setting of Hivernia
North coast:
Boreum promontory 11°00' . 61°00'
Vennicnium promontory 12°50' . 61°20'


§ 2.2.2  The Vennicni inhabit the west coast
"""


def _build(tmp_path):
    sections = parse_sections(TEXT)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    propagate_river_context(sections, points)
    propagate_bare_connector_tags(sections, points)
    convert_points(points)
    occ_index = build_occurrence_index(points)
    lines = build_all_lines(sections, points, resolved, occ_index)
    path = str(tmp_path / "test.gpkg")
    write_geopackage(path, lines, points, resolved, sections)
    return path


def test_sections_table_registered_as_attributes(tmp_path):
    path = _build(tmp_path)
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT table_name, data_type FROM gpkg_contents WHERE table_name = 'sections'"
        ).fetchall()
        assert rows == [("sections", "attributes")]

        count = con.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
        assert count == 2

        row = con.execute(
            "SELECT key, type, num_points FROM sections WHERE key = '2.2.1'"
        ).fetchone()
        assert row == ("2.2.1", "coastal", 2)
    finally:
        con.close()


def test_sections_table_carries_manual_override_note(tmp_path):
    text = (
        "§ 2.2.1  A description of the coast\nBoreum promontory 11°00' . 61°00'\n\n\n"
        "§ 7.1.95  And along the line of coast as far as the Kolchic Gulf:—\n"
        "Heptanesia . 113°00' . 13°00'\n"
    )
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    resolved["7.1.95"] = "island"  # simulates ptolemy.overrides.apply_section_overrides
    points = dedup_points(sections)
    tag_points(points, resolved)
    propagate_river_context(sections, points)
    propagate_bare_connector_tags(sections, points)
    convert_points(points)
    occ_index = build_occurrence_index(points)
    lines = build_all_lines(sections, points, resolved, occ_index)
    path = str(tmp_path / "override.gpkg")
    write_geopackage(path, lines, points, resolved, sections, section_notes={"7.1.95": "seven islands"})

    con = sqlite3.connect(path)
    try:
        row = con.execute(
            "SELECT type, manual_override, override_note FROM sections WHERE key = '7.1.95'"
        ).fetchone()
        assert row[0] == "island"
        assert row[1] == 1
        assert row[2]  # non-empty note

        row = con.execute(
            "SELECT manual_override, override_note FROM sections WHERE key = '2.2.1'"
        ).fetchone()
        assert row == (0, "")
    finally:
        con.close()


def test_points_layer_has_boolean_tag_columns(tmp_path):
    path = _build(tmp_path)
    con = sqlite3.connect(path)
    try:
        cols = {row[1] for row in con.execute("PRAGMA table_info(points)")}
        assert "is_coast" in cols
        assert "is_river" in cols
        row = con.execute(
            "SELECT is_coast FROM points WHERE name = 'Boreum promontory'"
        ).fetchone()
        assert row == (1,)
    finally:
        con.close()


def test_line_geometry_closes_the_ring_when_closed():
    # A "closed" trail's own exported geometry must actually repeat the
    # first point at the end, or QGIS renders the same broken-looking seam
    # this was confirmed to produce (NE Ireland: the real closing edge was
    # never part of the drawn geometry, despite the "closed" column saying
    # it was).
    pts = [
        Point(id="P1", lon_ferro=0, lat_ferro=0, book_map="2.2", lon_modern=0.0, lat_modern=0.0),
        Point(id="P2", lon_ferro=1, lat_ferro=0, book_map="2.2", lon_modern=1.0, lat_modern=0.0),
        Point(id="P3", lon_ferro=1, lat_ferro=1, book_map="2.2", lon_modern=1.0, lat_modern=1.0),
    ]
    closed_geom = _line_geometry(pts, closed=True)
    assert list(closed_geom.coords)[0] == list(closed_geom.coords)[-1]
    open_geom = _line_geometry(pts, closed=False)
    assert list(open_geom.coords)[0] != list(open_geom.coords)[-1]


def test_a_separate_layer_exists_per_tag(tmp_path):
    # A point's own "tags" column on the combined points layer is
    # comma-joined (a point can carry more than one tag at once), which
    # most GIS programs can't style or filter on directly -- a dedicated
    # single-tag layer per tag sidesteps that entirely.
    path = _build(tmp_path)
    con = sqlite3.connect(path)
    try:
        layer_names = {
            row[0] for row in con.execute(
                "SELECT table_name FROM gpkg_contents WHERE table_name LIKE 'points_%'"
            )
        }
        assert "points_coast" in layer_names
        assert "points_river" not in layer_names  # no river points in this fixture

        names = {row[0] for row in con.execute("SELECT name FROM points_coast")}
        assert names == {"Boreum promontory", "Vennicnium promontory"}
    finally:
        con.close()
