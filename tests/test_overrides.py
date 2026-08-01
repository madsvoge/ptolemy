import csv

from ptolemy.classify import classify_sections, COASTAL, INLAND, ISLAND
from ptolemy.coords import convert_points
from ptolemy.lines import build_all_lines
from ptolemy.overrides import (
    ADDED_POINTS_PATH,
    POINT_OVERRIDES_PATH,
    SECTION_OVERRIDES_PATH,
    apply_manual_stitches,
    apply_point_overrides,
    apply_section_overrides,
    build_added_points,
    load_added_points,
    load_point_overrides,
    load_section_overrides,
    override_key_for_point,
)
from ptolemy.parser import parse_sections
from ptolemy.points import build_occurrence_index, dedup_points
from ptolemy.tag import tag_points


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_section_override_applies_and_does_not_leak_downstream(tmp_path):
    path = tmp_path / "sections.csv"
    _write_csv(path, ["section_key", "classify", "note"], [
        {"section_key": "7.1.95", "classify": "island", "note": "seven islands"},
    ])
    text = (
        "§ 7.1.95  And along the line of coast as far as the Kolchic Gulf:—\n"
        "Heptanesia . 113°00' . 13°00'\n\n\n"
        "§ 7.1.96  And in the Argaric Gulf:—\nKory . 126°30' . 13°00'\n"
    )
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    apply_section_overrides(resolved, path=str(path))
    assert resolved["7.1.95"] == ISLAND
    # The section after it, with no signal of its own, still inherits the
    # real coastal type carried by the text -- the override corrects only
    # 7.1.95's own type, not the downstream inheritance chain.
    assert resolved["7.1.96"] == COASTAL


def test_section_override_note_available(tmp_path):
    path = tmp_path / "sections.csv"
    _write_csv(path, ["section_key", "classify", "note"], [
        {"section_key": "4.6.24", "classify": "inland", "note": "desert corridor"},
    ])
    overrides = load_section_overrides(str(path))
    assert overrides["4.6.24"] == ("inland", "desert corridor")


def test_real_committed_section_overrides_cover_known_cases():
    # Regression guard for the migration off classify.py's old hardcoded
    # SECTION_OVERRIDES dict: both cases found this session must still be
    # present in the committed CSV.
    overrides = load_section_overrides(SECTION_OVERRIDES_PATH)
    assert overrides["7.1.95"][0] == "island"
    assert overrides["4.6.24"][0] == "inland"


def _build_points(text):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    return sections, resolved, points


def test_point_override_forces_classify(tmp_path):
    text = "§ 2.2.1  A description of the coast\nBoreum promontory 11°00' . 61°00'\n"
    sections, resolved, points = _build_points(text)
    offset = points[0].occurrences[0].char_offset
    path = tmp_path / "points.csv"
    _write_csv(path, ["section_key", "char_offset", "point_name_ref", "classify", "stitch_to",
                       "correction_field", "correction_value", "note"], [
        {"section_key": "2.2.1", "char_offset": str(offset), "point_name_ref": "Boreum promontory",
         "classify": "island", "stitch_to": "", "correction_field": "", "correction_value": "", "note": "actually an island"},
    ])
    warnings = apply_point_overrides(points, path=str(path))
    assert warnings == []
    assert points[0].tags == {"island"}


def test_point_override_corrects_a_coordinate_typo(tmp_path):
    text = "§ 3.14.31  A description of the coast\nPherai . 49°30' . 30°15'\n"
    sections, resolved, points = _build_points(text)
    offset = points[0].occurrences[0].char_offset
    path = tmp_path / "points.csv"
    _write_csv(path, ["section_key", "char_offset", "point_name_ref", "classify", "stitch_to",
                       "correction_field", "correction_value", "note"], [
        {"section_key": "3.14.31", "char_offset": str(offset), "point_name_ref": "Pherai",
         "classify": "", "stitch_to": "", "correction_field": "lat_ferro", "correction_value": "35.25",
         "note": "transcription typo, neighbours are all ~35 degrees"},
    ])
    warnings = apply_point_overrides(points, path=str(path))
    assert warnings == []
    assert points[0].lat_ferro == 35.25


def test_point_override_warns_on_unmatched_key(tmp_path):
    text = "§ 2.2.1  A description of the coast\nBoreum promontory 11°00' . 61°00'\n"
    sections, resolved, points = _build_points(text)
    path = tmp_path / "points.csv"
    _write_csv(path, ["section_key", "char_offset", "point_name_ref", "classify", "stitch_to",
                       "correction_field", "correction_value", "note"], [
        {"section_key": "2.2.1", "char_offset": "999999", "point_name_ref": "nonexistent",
         "classify": "island", "stitch_to": "", "correction_field": "", "correction_value": "", "note": "typo'd offset"},
    ])
    warnings = apply_point_overrides(points, path=str(path))
    assert len(warnings) == 1
    assert "2.2.1@999999" in warnings[0]


def test_added_point_is_flagged_synthetic_and_gets_a_stable_name(tmp_path):
    path = tmp_path / "added.csv"
    _write_csv(path, ["key", "book_map", "name", "lon_ferro", "lat_ferro", "tags", "stitch_to", "note"], [
        {"key": "ne-corner", "book_map": "8.1", "name": "Northeast closure point",
         "lon_ferro": "180", "lat_ferro": "63", "tags": "coast", "stitch_to": "", "note": "closes the NE edge"},
    ])
    points = build_added_points(path=str(path))
    assert len(points) == 1
    p = points[0]
    assert p.is_synthetic is True
    assert p.id == "synthetic:ne-corner"
    assert p.name == "Northeast closure point"
    assert p.tags == {"coast"}


def test_manual_stitch_connects_two_real_points(tmp_path):
    text = (
        "§ 2.2.1  A description of the coast\nPoint A 10°00' . 60°00'\n\n\n"
        "§ 3.1.1  A description of the coast\nPoint B 40°00' . 60°00'\n"
    )
    sections, resolved, points = _build_points(text)
    convert_points(points)
    a_key = override_key_for_point(points[0])
    b_key = override_key_for_point(points[1])

    from ptolemy.overrides import PointOverride
    point_overrides = [PointOverride(key=a_key, classify=None, stitch_to=b_key,
                                      correction_field=None, correction_value=None, note="manual link")]
    lines, warnings = apply_manual_stitches(points, point_overrides, [])
    assert warnings == []
    assert len(lines) == 1
    assert lines[0].kind == "stitch"
    assert set(lines[0].point_ids) == {points[0].id, points[1].id}


def test_manual_stitch_connects_a_real_point_to_a_synthetic_one(tmp_path):
    text = "§ 2.2.1  A description of the coast\nPoint A 10°00' . 60°00'\n"
    sections, resolved, points = _build_points(text)
    convert_points(points)
    a_key = override_key_for_point(points[0])

    added_path = tmp_path / "added.csv"
    _write_csv(added_path, ["key", "book_map", "name", "lon_ferro", "lat_ferro", "tags", "stitch_to", "note"], [
        {"key": "closure", "book_map": "2.2", "name": "Closure point", "lon_ferro": "12", "lat_ferro": "60",
         "tags": "coast", "stitch_to": a_key, "note": "closes the loop"},
    ])
    added_rows = load_added_points(path=str(added_path))
    synthetic_points = build_added_points(path=str(added_path))
    convert_points(synthetic_points)
    all_points = points + synthetic_points

    lines, warnings = apply_manual_stitches(all_points, [], added_rows)
    assert warnings == []
    assert len(lines) == 1
    assert set(lines[0].point_ids) == {points[0].id, "synthetic:closure"}


def test_manual_stitch_warns_on_unmatched_target():
    from ptolemy.overrides import PointOverride
    point_overrides = [PointOverride(key="1.1.1@1", classify=None, stitch_to="9.9.9@99999",
                                      correction_field=None, correction_value=None, note="bad ref")]
    lines, warnings = apply_manual_stitches([], point_overrides, [])
    assert lines == []
    assert len(warnings) == 1
