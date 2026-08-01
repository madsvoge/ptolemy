from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points


def _tagged_points(text):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    return {p.name: p for p in points}


def test_river_mouth_in_coastal_section_gets_both_tags():
    text = "§ 2.2.1  A description of the coast\nmouth of the Vidua river 13°00' . 61°00'\n"
    points = _tagged_points(text)
    p = points["mouth of the Vidua river"]
    assert p.tags == {"river_mouth", "coast"}


def test_promontory_tagged_coast():
    text = "§ 2.2.1  A description of the coast\nBoreum promontory 11°00' . 61°00'\n"
    points = _tagged_points(text)
    assert points["Boreum promontory"].tags == {"coast"}


def test_inland_city_default_tag():
    text = "§ 2.2.9  The following are the inland towns: Regia 13°00' . 60°20'\n"
    points = _tagged_points(text)
    assert points["Regia"].tags == {"city"}


def test_boundary_point_gets_boundary_plus_own_tag():
    text = "§ 2.12.1  Raetia is bounded on the west by Adulas mountain 10°00' . 47°00'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "mountain" in p.tags
    assert "boundary" in p.tags


def test_mt_abbreviation_is_tagged_mountain():
    text = "§ 3.14.35  Mountains in the Peloponnese\nMt. Kallidromon 31°20' . 38°15'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "mountain" in p.tags
    assert "coast" not in p.tags


def test_tribal_city_idiom_overrides_coastal_default():
    text = (
        "§ 2.8.5  The Caletes occupy the northern coast from the Sequana River; "
        "their city is Iuliobona 20°15' . 51°10'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"city"}


def test_reference_marker_idiom_overrides_coastal_default():
    text = (
        "§ 6.21.2  A description of the coast\n"
        "After which the extreme point at the sea already mentioned 109°00' . 20°00'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"city"}


def test_island_list_point_tagged_island():
    text = "§ 2.2.10  Above Hibernia are the Ebuda islands: Ebuda 15°00' . 62°00'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "island" in p.tags
