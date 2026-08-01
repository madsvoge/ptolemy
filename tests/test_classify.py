from ptolemy.parser import parse_sections
from ptolemy.classify import classify_sections, COASTAL, INLAND, ISLAND, MOUNTAIN, BOUNDARY


def _resolve(text):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    return sections, resolved


def test_island_list_intro_is_classified_island():
    text = "§ 2.3.14  The islands which are near Albion island and the Orcades promontory are: Scetis island 10°00' . 60°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == ISLAND


def test_islands_own_name_does_not_misclassify_its_coastal_walk():
    # "Setting of Hivernia British island" must not itself trigger the
    # island-list category; it's the opening of a coastal walk.
    text = "§ 2.2.1  Setting of Hivernia British island\nA description of the north coast:\nBoreum promontory 11°00' . 61°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == COASTAL


def test_named_mountain_list_intro_is_classified_mountain():
    text = "§ 2.4.12  The named mountains in Baetica are Marianus, midpoint at 6°20' . 37°45'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == MOUNTAIN


def test_bare_mountain_mention_in_boundary_does_not_misclassify():
    text = "§ 2.12.1  Raetia is bounded on the west side by Adulas mountain 10°00' . 47°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == BOUNDARY


def test_inland_towns_colon_intro_is_classified_inland():
    text = "§ 2.2.9  The following are the inland towns: Regia 13°00' . 60°20'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == INLAND


def test_interior_cities_word_order_variant_is_classified_inland():
    text = "§ 3.1.28  The interior cities of Istria\nPacinum 14°00' . 45°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == INLAND


def test_bounded_by_without_direction_word_is_classified_boundary():
    text = "§ 2.14.1  UPPER PANNONIA\nOn the west, Upper Pannonia is bounded by Cetium mountain 15°00' . 46°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == BOUNDARY


def test_no_signal_inherits_previous_type_within_same_book_map():
    text = (
        "§ 2.2.1  A description of the coast\nPoint A 10°00' . 60°00'\n\n\n"
        "§ 2.2.2  Then next to these\nPoint B 10°30' . 60°30'\n"
    )
    sections, resolved = _resolve(text)
    assert resolved["2.2.1"] == COASTAL
    assert resolved["2.2.2"] == COASTAL


def test_no_signal_never_inherits_into_island_or_mountain():
    text = (
        "§ 2.2.1  A description of the coast\nPoint A 10°00' . 60°00'\n\n\n"
        "§ 2.2.2  The named mountains here are Foo\nMt. Foo 10°10' . 60°10'\n\n\n"
        "§ 2.2.3  Then next to these\nPoint C 10°30' . 60°30'\n"
    )
    sections, resolved = _resolve(text)
    assert resolved["2.2.2"] == MOUNTAIN
    assert resolved["2.2.3"] == COASTAL  # inherits from 2.2.1, skipping the mountain aside


def test_no_signal_scoped_to_same_book_map():
    text = (
        "§ 2.2.1  The named mountains here are Foo\nMt. Foo 10°00' . 60°00'\n\n\n"
        "§ 2.3.1  Then next to these\nPoint B 10°30' . 60°30'\n"
    )
    sections, resolved = _resolve(text)
    # 2.3.1 has no signal of its own and no prior *carryable* (non-island/
    # mountain) state in its own book_map, so it must fall back to the
    # first-section default rather than inheriting 2.2's mountain type
    # across a map boundary.
    assert resolved["2.2.1"] == MOUNTAIN
    assert resolved["2.3.1"] == COASTAL
