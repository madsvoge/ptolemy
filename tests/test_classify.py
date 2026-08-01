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


def test_named_island_walk_described_as_follows_is_classified_island():
    # A single named island's own coastal walk, embedded as an appendix
    # inside a shared/mainland book.map (confirmed §5.2.29, Lesbos) --
    # signalled by "island" co-occurring with Ptolemy's own "described as
    # follows" list-intro in the same lead sentence.
    text = (
        "§ 5.2.29  In the Aegean sea Lesbos, an Aiolian island, described as follows:\n"
        "Sigrion promontory . 55°00' . 40°00'\n"
    )
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == ISLAND


def test_generic_described_as_follows_without_island_word_stays_coastal():
    # The bare "described as follows"/"description...as follows" list-intro
    # convention is not island-specific on its own -- plain coastal/
    # boundary sections use it constantly -- so it must only fire paired
    # with "island(s)" already present in the same lead.
    text = "§ 6.3.2  this coast is described as follows:\nSome point . 79°30' . 30°15'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == COASTAL


def test_bare_description_of_name_title_is_classified_island():
    # "Description of Karpathos:" as a section's own bare lead (confirmed
    # §5.2.33) -- distinct from the generic "Description of the west/south/
    # ... side:" and "the description of {this side|which} is..." coastal
    # conventions used everywhere else in this text.
    text = "§ 5.2.33  Description of Karpathos:\nThoantion promontory . 57°00' . 35°20'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == ISLAND


def test_description_of_the_side_stays_coastal():
    text = "§ 3.2.3  Description of the west coast:\nSome point . 57°00' . 35°20'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == COASTAL


def test_islands_on_its_coast_is_classified_island():
    # "on" as the connecting preposition (confirmed §5.14.7, Cleides) --
    # not part of the original preposition set, which missed this phrasing.
    text = "§ 5.14.7  The islands on its coast are those called Cleides, their midpoint . 67°20' . 35°45'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == ISLAND


def test_islands_adjacent_to_is_classified_island():
    # Confirmed §3.14.22 (Euboia) and §3.15.11/§6.21.6 (both previously
    # misclassified inland, since "adjacent" wasn't among the recognized
    # island-list prepositions).
    text = "§ 3.15.11  Islands adjacent to Crete\nSome island 57°00' . 35°20'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == ISLAND


def test_cities_are_these_word_order_variant_is_classified_inland():
    # "And the cities are these:" (confirmed §7.1.43) -- the same list-intro
    # convention as "the following cities:", just with subject and
    # predicate swapped. Without recognizing this order, the section had no
    # signal of its own and silently inherited a stale coastal type carried
    # in from far earlier in the book.map.
    text = "§ 7.1.43  And the cities are these:—\nKaisana . 120°00' . 34°20'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == INLAND


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


def test_section_with_no_textual_signal_stays_unoverridden():
    # §7.1.95 has no manual-override mechanism at this layer any more --
    # classify_sections is a pure function of the text, so its own "line of
    # coast" wording resolves it coastal on text alone. The curator
    # correction that makes this section island (its citations are
    # historically an island group Ptolemy's own prose doesn't name as
    # such) now lives in data/manual_section_overrides.csv, applied by
    # ptolemy.overrides as an explicit, separate step -- see
    # tests/test_overrides.py.
    text = "§ 7.1.95  And along the line of coast as far as the Kolchic Gulf:—\nHeptanesia . 113°00' . 13°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == COASTAL


def test_bare_cities_are_colon_word_order_is_classified_inland():
    # "The cities are:" / "whose towns are:" -- the same swapped-order
    # list-intro convention as "the cities are these:", just without the
    # "these"/"the following" qualifier at all (confirmed §5.9.16, ending
    # a long tribal-ethnography aside about Sarmatia's unknown country).
    text = "§ 5.9.16  Latitudes of Sarmatia toward the unknown country\nThe cities are:\nHexapolis . 72°00' . 55°40'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == INLAND


def test_mountains_are_at_is_classified_mountain():
    # "The extremes of the Hippika mountains are at COORD and COORD"
    # (confirmed §5.9.15) -- narrow window so this doesn't fire on an
    # unrelated "mountains...are at" many words later in a boundary
    # sentence (§4.5.19 stays boundary/coastal, not mountain).
    text = "§ 5.9.15  The extremes of the Hippika mountains are at 74°00' . 54°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == MOUNTAIN


def test_mountains_are_at_far_from_boundary_stays_unmatched():
    text = (
        "§ 4.5.19  A description of the coast\n"
        "and the Libyan mountains to the west of the Nile river, the end points of which "
        "are at 61°00' . 29°00'\n"
    )
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] != MOUNTAIN


def test_mountains_thus_named_is_classified_mountain():
    # "The mountains in this division are thus named:—" (confirmed
    # §7.2.8) -- same list-intro convention as "...are called:", just with
    # "named" and more words in between than the narrow "are at" window
    # above allows.
    text = "§ 7.2.8  The mountains in this division are thus named:—\nBepyrrhos . 148°00' . 34°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] == MOUNTAIN


def test_cities_thus_named_stays_unaffected():
    text = "§ 6.16.6  The cities in Serike are thus named :—\nSera . 100°00' . 30°00'\n"
    sections, resolved = _resolve(text)
    assert resolved[sections[0].key] != MOUNTAIN
