from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points
from ptolemy.classify import classify_sections
from ptolemy.tag import propagate_bare_connector_tags, propagate_river_context, tag_points


def _tagged_points(text, with_context_pass=False):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    if with_context_pass:
        propagate_river_context(sections, points)
    return {p.name: p for p in points}


def _tagged_point_list(text, with_bare_connector_pass=True):
    sections = parse_sections(text)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    propagate_river_context(sections, points)
    if with_bare_connector_pass:
        propagate_bare_connector_tags(sections, points)
    points.sort(key=lambda p: p.first_char_offset)
    return points


def test_river_mouth_in_coastal_section_gets_both_tags():
    text = "§ 2.2.1  A description of the coast\nmouth of the Vidua river 13°00' . 61°00'\n"
    points = _tagged_points(text)
    p = points["mouth of the Vidua river"]
    assert p.tags == {"river_mouth", "coast"}


def test_promontory_tagged_coast():
    text = "§ 2.2.1  A description of the coast\nBoreum promontory 11°00' . 61°00'\n"
    points = _tagged_points(text)
    assert points["Boreum promontory"].tags == {"coast"}


def test_harbor_in_coastal_section_gets_both_tags():
    # A harbor cited as an ordinary waypoint in a coastal walk is a real
    # point on that coastline, not just a harbor feature -- confirmed
    # §3.4.7 (Sicily), "Kaukana harbor" sitting between a promontory and a
    # river mouth in the same walk (previously excluded from the drawn
    # coastline, breaking it into two trails).
    text = "§ 3.4.7  A description of the coast\nKaukana harbor . 39°30' . 36°15'\n"
    points = _tagged_points(text)
    p = points["Kaukana harbor"]
    assert p.tags == {"harbor", "coast"}


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


def test_bare_and_connector_inherits_previous_mountain_tag():
    # "The extremes of the X mountains are at COORD1 and COORD2" -- the
    # second extremity's whole name_phrase is just "and", since a
    # citation's name is only the text back to the previous coordinate.
    text = (
        "§ 5.9.15  Boundary markers\n"
        "The extremes of the Hippika mountains are at 74°00' . 54°00' and 81°00' . 52°00'\n"
    )
    points = _tagged_point_list(text)
    assert len(points) == 2
    assert points[0].tags == {"mountain"}
    assert points[1].name.strip().lower() == "and"
    assert points[1].tags == {"mountain"}


def test_bare_and_connector_inherits_previous_river_tag():
    text = (
        "§ 2.9.1  A description of the coast\n"
        "mouth of the Rhenus river 25°00' . 53°00' and 26°00' . 52°30'\n"
    )
    points = _tagged_point_list(text)
    assert points[1].tags == {"river_mouth", "coast"}


def test_bare_and_connector_does_not_apply_when_not_bare():
    # "and" as part of a longer phrase (not the *entire* name_phrase) must
    # not trigger inheritance -- only an exact, standalone "and".
    text = (
        "§ 5.9.15  Boundary markers\n"
        "Mt. Kaukasos 74°00' . 54°00'\n"
        "and then Vennicnium river source 12°00' . 62°00'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"mountain"}
    assert points[1].tags == {"river"}  # matched its own "source" keyword, not inherited


def test_gates_and_pillars_are_not_coastal():
    text = (
        "§ 5.9.15  Boundary markers\n"
        "A description of the coast\n"
        "The Sarmatian Gates 81°00' . 48°30'\n"
        "The Pillars of Alexander are at 80°00' . 51°30'\n"
    )
    points = _tagged_point_list(text)
    for p in points:
        assert p.tags == {"city"}, (p.name, p.tags)


def test_until_the_border_is_a_reference_marker_not_coastal():
    # "...until the border with lower Moesia, at..." (confirmed §3.11.3) is
    # a boundary line's own restated endpoint, not a fresh coastal
    # waypoint -- the same idiom as "until the end" already handled, just
    # naming the neighbouring region instead.
    text = (
        "§ 3.11.3  A description of the coast\n"
        "On the east by the Propontis until the border with lower Moesia, at 55°00' . 44°40'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"city"}


def test_mouth_of_pontos_is_not_a_river_mouth():
    # "Pontos" is the Black Sea itself, not a river -- "mouth of Pontos" is
    # Ptolemy's idiom for the Bosporos strait, confirmed used identically
    # as a restated boundary/reference point from two different regions'
    # descriptions (§3.10.3 and §3.11.3) sharing the same coordinate.
    # Matching it as a literal river mouth gave those restatements a
    # "river_mouth" primary tag before _REFERENCE_MARKER_RE ever got
    # consulted, pulling them into the coastal walk as fresh waypoints and
    # self-intersecting the drawn line.
    text = (
        "§ 3.11.3  A description of the coast\n"
        "the mouth of Pontos, at the limit point 55°00' . 44°40'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"city"}


def test_real_river_mouth_still_tagged():
    text = "§ 2.2.1  A description of the coast\nmouth of the Vistula river 10°00' . 56°00'\n"
    points = _tagged_point_list(text)
    assert points[0].tags == {"river_mouth", "coast"}
