from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points, propagate_river_context


def _tagged_points(text, with_context_pass=False):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    if with_context_pass:
        propagate_river_context(sections, points)
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


def test_plural_mouths_of_is_recognized():
    text = "§ 2.11.1  A description of the coast\nMouths of the river Amisius 29°00' . 55°00'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river_mouth" in p.tags


def test_bare_mouth_as_proper_noun_is_recognized():
    # "the Kambyson Mouth" -- a distributary's own name, no "of" at all.
    text = "§ 7.1.30  Branch from the coast\nBranch from the Ganges into the Kambyson Mouth 146°00' . 22°00'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river_mouth" in p.tags or "river" in p.tags


def test_junction_and_bifurcation_language_tagged_river():
    text = (
        "§ 7.1.29  Of the streams which join the Ganges the order is this:\n"
        "Junction of the Diamouna and Ganges 136°00' . 34°00'\n"
        "Where it bifurcates into the Goaris and Binda 114°00' . 16°00'\n"
        "Its confluence with the River Moghis 115°00' . 18°30'\n"
    )
    points = _tagged_points(text)
    for p in points.values():
        assert "river" in p.tags, p.name


def test_flows_into_and_joins_language_tagged_river():
    text = (
        "§ 3.1.4  A description of the coast\n"
        "where the Boacias flows into it 31°30' . 43°00'\n\n\n"
        "§ 2.4.4  Of the Turduli\n"
        "Where the Asta joins it 6°00' . 36°45'\n"
    )
    points = _tagged_points(text)
    for p in points.values():
        assert "river" in p.tags, p.name


def test_river_turn_explicit_is_tagged_river_not_coast():
    text = "§ 2.10.14  A description of the coast\nThe turn of the river toward the Alps, below Lugdunum 23°00' . 45°15'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"river"}


def test_mid_point_of_length_with_en_dash_and_named_variant():
    text = "§ 2.6.16  A description of the coast\nMid–point of the length of the river 14°00' . 42°00'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"river"}


def test_generic_turn_phrase_needs_context_pass_and_river_neighbour():
    text = (
        "§ 2.10.14  A description of the coast\n"
        "mouth of the Rhodanus river 22°50' . 42°40'\n"
        "The turn towards the east 23°00' . 45°00'\n"
    )
    without = _tagged_points(text, with_context_pass=False)
    assert without["turn towards the east"].tags == {"coast"}

    with_ctx = _tagged_points(text, with_context_pass=True)
    assert with_ctx["turn towards the east"].tags == {"river"}


def test_generic_turn_phrase_without_river_neighbour_stays_coastal():
    text = (
        "§ 2.10.14  A description of the coast\n"
        "Boreum promontory 11°00' . 61°00'\n"
        "The turn towards the east 23°00' . 45°00'\n"
        "Another promontory 24°00' . 46°00'\n"
    )
    points = _tagged_points(text, with_context_pass=True)
    assert points["turn towards the east"].tags == {"coast"}


def test_river_context_pass_does_not_cascade_through_ordinary_coastal_cities():
    # Regression test for a real bug: a naive context pass that checks
    # *live* (already-mutated) neighbour tags cascades a single river
    # mouth into reclassifying an entire coastal walk as 'river'. Plain
    # coastal city names sitting a few steps away from a genuine river
    # mouth must never flip, even though *some* neighbour down the chain
    # is river-tagged.
    text = (
        "§ 3.1.3  A description of the coast\n"
        "mouth of the Macralla 31°50' . 42°45'\n"
        "where the Boacias flows into it 31°30' . 43°00'\n"
        "Luna 30°00' . 44°00'\n"
        "Genua 28°00' . 44°30'\n"
        "Tigullia 27°00' . 44°45'\n"
    )
    points = _tagged_points(text, with_context_pass=True)
    assert points["Luna"].tags == {"coast"}
    assert points["Genua"].tags == {"coast"}
    assert points["Tigullia"].tags == {"coast"}
