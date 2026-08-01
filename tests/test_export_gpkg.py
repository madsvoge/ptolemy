import sqlite3

from ptolemy.classify import classify_sections
from ptolemy.coords import convert_points
from ptolemy.export_gpkg import write_geopackage
from ptolemy.lines import build_all_lines
from ptolemy.parser import parse_sections
from ptolemy.points import build_occurrence_index, dedup_points
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
