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


def test_plural_springs_is_tagged_river():
    # Confirmed P5360/P5393: "springs of the river"/"Springs of the
    # Maxeras" -- _RIVER_RE only had the singular "spring", missing the
    # plural Ptolemy actually uses here.
    text = "§ 6.9.2  A description of the coast\nsprings of the Maxeras river . 60°00' . 44°00'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river" in p.tags
    assert "coast" not in p.tags


def test_delta_distributary_named_by_two_endpoints_is_tagged_river():
    # Confirmed P5761, §7.1.28: "From the Sagapa into the Indus" -- a
    # delta channel named by its own two endpoints, without repeating
    # "branch"/"mouth" the way its sibling citations in the same list do.
    text = "§ 7.1.28  A description of the coast\nFrom the Sagapa into the Indus . 60°00' . 44°00'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"river"}


def test_branching_verb_form_is_tagged_river():
    # Confirmed P3193, §4.5.43 (Nile delta): "the branching of the Taly
    # river is at" -- _RIVER_RE's old "branch(es)?" exact-word-boundary
    # form missed the "-ing" verb form.
    text = "§ 4.5.43  A description of the coast\nthe branching of the Taly river is at . 61°00' . 30°50'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river" in p.tags


def test_delta_fork_river_mouth_does_not_also_get_coast_tag():
    # Confirmed P3190, §4.5.40 (Nile delta): "the Boubastiakos river
    # splits into the Bousiritikos river, which flows out through the
    # Pathmitic mouth" -- an inland delta fork, not a real coastline
    # point, even though it carries a 'mouth' word like a genuine coastal
    # river mouth would. The old _DISTRIBUTARY_BRANCH_RE only recognized
    # the literal word "branch", missing "splits into"/"delta".
    text = (
        "§ 4.5.40  A description of the coast\n"
        "The so-called Little Delta is where the Boubastiakos river "
        "splits into the Bousiritikos river, which flows out through the "
        "Pathmitic mouth, position of which is . 62°40' . 30°20'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"river_mouth"}


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


def test_river_source_named_by_its_mountain_gets_both_mountain_and_river_tags():
    # Confirmed throughout book 4.6's Libyan river catalogue: "Mandron
    # mountain, from which flow the Salathus river, the Massa river..." --
    # explicit_checks picks 'mountain' as primary since it's checked ahead
    # of 'river', but the exact same citation is just as much a river
    # source. Without adding 'river' as a second tag here, the entire
    # "river originates at a named mountain" idiom was invisible to
    # build_rivers, which only ever looks at 'river'/'river_mouth' tags.
    text = (
        "§ 4.6.5  Mandron mountain, from which flow the Salathus river, "
        "the Massa river 12°00' . 28°00'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"mountain", "river"}


def test_river_begins_from_mountain_is_tagged_river_too():
    # Confirmed §3.12.15: "The Strymon river begins from the mountains
    # forming the border of Thrace and Macedonia, at this location".
    text = (
        "§ 3.12.15  The Strymon river begins from the mountains forming "
        "the border of Thrace and Macedonia, at this location 48°40' . 42°00'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river" in p.tags
    assert "mountain" in p.tags


def test_river_links_two_mountains_is_tagged_river():
    # Confirmed §4.6.14: "the Nigeir river itself links Mandron mountain
    # and Thala mountain" -- "links" alone has an unrelated administrative
    # sense elsewhere in this text ("the northern side links to
    # Tarraconensis"), so this only fires with "river" nearby.
    text = (
        "§ 4.6.14  the Nigeir river itself links Mandron mountain and "
        "Thala mountain 10°00' . 20°00'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river" in p.tags


def test_administrative_links_without_a_nearby_river_is_not_tagged_river():
    text = (
        "§ 2.4.1  The northern side links to Tarraconensis along the "
        "western part 10°00' . 20°00'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river" not in p.tags


def test_city_on_a_named_river_is_tagged_river():
    # Confirmed line 5814: "Apollonia on the Ryndakos river" and §5.15.16:
    # "Antiocheia on the Orontes river" -- a city cited on a named river
    # carries no other river vocabulary of its own, but lines.py's own
    # river_base_name template already recognizes "NAME river"/"river
    # NAME" for grouping; without this tag it never entered
    # build_rivers' own river_points filter to begin with.
    text = "§ 5.15.16  Antiocheia on the Orontes river 69°00' . 35°30'\n"
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river" in p.tags


def test_on_the_river_at_coord_boundary_idiom_is_not_tagged_river():
    # Confirmed §5.19.1: "Eremos Arabia is bounded... on the Euphrates
    # river at <coord>" is this text's own boundary-limit-point idiom --
    # the coordinate belongs to the boundary point, not a city cited on
    # the river.
    text = (
        "§ 5.19.1  Eremos Arabia is bounded on the north by part of "
        "Mesopotamia on the Euphrates river at 76°15' . 33°20'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert "river" not in p.tags


def test_tribal_city_idiom_overrides_coastal_default():
    text = (
        "§ 2.8.5  The Caletes occupy the northern coast from the Sequana River; "
        "their city is Iuliobona 20°15' . 51°10'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"city"}


def test_tribal_city_idiom_wins_over_a_coastal_landmark_word_in_the_same_phrase():
    # Confirmed P731, §2.8.5: "...up to the Gabaeum promontory, the Osismi
    # whose city is Vorgum" -- "promontory" is an explicit_checks entry
    # checked before the old fallback-only tribal-city check ever ran, so
    # it silently won and tagged the tribal capital 'coast' instead of
    # 'city', even though the sentence's real subject (closest to the
    # coordinate) is the city.
    text = (
        "§ 2.8.5  After these the Lexubii, then the Venelli and afterwards "
        "the Viducasii and finally, up to the Gabaeum promontory, the "
        "Osismi whose city is Vorgum 17°30' . 49°10'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"city"}


def test_reference_marker_wins_over_a_coastal_landmark_word_in_the_same_phrase():
    # Confirmed P2044, §3.12.3: "Along Achaia until the Maliac gulf to the
    # end, position" -- "gulf" is a _COAST_NAME_RE explicit_checks entry
    # checked before the reference-marker idiom, so it silently won and
    # tagged this restated boundary-line endpoint 'coast' instead of
    # 'city', same class of bug as the tribal-city idiom above.
    text = (
        "§ 3.12.3  Elimiotes\n"
        "Along Achaia until the Maliac gulf to the end, position 51°00' . 38°25'\n"
    )
    points = _tagged_points(text)
    p = next(iter(points.values()))
    assert p.tags == {"city"}


def test_restated_landmark_idiom_does_not_strip_coast_from_a_genuinely_coastal_point():
    # Confirmed regression risk on Pegai, P2255: promoting the weaker
    # "after X, which is" reference-marker idiom into explicit_checks (the
    # way the reliable tier above is) cost the point its 'coast' tag
    # entirely, since tag_point's `name` joins *every* occurrence's phrase
    # into one string -- Pegai's own genuine §3.14.6 citation has no
    # marker language of its own, but its *other* occurrence (§3.14.26,
    # restating it to open the Peloponnese's own coastal walk) does, and
    # that alone must not flip the whole point away from 'coast'.
    text = (
        "§ 3.14.6  Megarid\nPegai 51°25' . 37°25'\n\n\n"
        "§ 3.14.25  Position of the Peloponnesos: bounded to the north by "
        "the Corinthian Gulf.\n\n\n"
        "§ 3.14.26  After Pegai in the Megarid, which is in the Corinthian "
        "gulf off Achaia, at degrees 51°25' . 37°25'\n"
    )
    points = _tagged_points(text)
    assert points["Pegai"].tags == {"coast"}


def test_bare_the_town_name_idiom_is_tagged_city():
    # Confirmed P136, §2.3.10: "Near which on the Opportunum bay are the
    # Parisi and the town Petuaria" -- the same tribal-capital idiom as
    # "whose city is X", but with "the town X" and no verb at all, and
    # "bay" sitting right there in the same sentence.
    text = (
        "§ 2.3.10  Below the Selgovae and Otalini are the Brigantes, "
        "among whom are the following towns:\n"
        "Near which on the Opportunum bay are the Parisi and the town "
        "Petuaria 20°40' . 56°40'\n"
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


def test_until_the_border_with_stays_coastal_not_a_reference_marker():
    # "...until the border with lower Moesia, at..." (confirmed §3.11.3) is
    # NOT the same as "until the end": unlike that idiom's own confirmed
    # cases, this citation's coordinate genuinely is the next real coastal
    # waypoint (~0.3 degrees from the very next citation, Mesembria), not
    # a restated endpoint far from where the walk actually continues --
    # excluding it from 'coast' entirely dropped a real point from the
    # map. classify.starts_new_coastal_arc handles the actual problem this
    # idiom does cause (see test_lines.py): the point right before it in
    # document order must not stitch straight across to it, since it opens
    # a *different* coastal arc of the same region (confirmed §3.11.3:
    # Thrace's own Black Sea side, not a continuation of its Aegean side).
    text = (
        "§ 3.11.3  A description of the coast\n"
        "On the east by the Propontis until the border with lower Moesia, at 55°00' . 44°40'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"coast"}


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


def test_river_boundary_line_generic_river_references_stay_river():
    # A boundary line following a named river's own course (§2.4.2, §2.5.1)
    # cites several waypoints that just say "the river" plainly, with none
    # of the specific verb keywords (source/turn/bend/...) -- confirmed
    # regression: these fell through to the coastal-section default.
    text = (
        "§ 2.4.2  A description of the coast\n"
        "The eastern mouth of the river Ana 4°20' . 37°30'\n"
        "Where the river touches the border of Lusitania 9°00' . 39°00'\n"
        "The sources of the river 14°00' . 40°00'\n"
    )
    points = _tagged_point_list(text)
    names = {p.name: p.tags for p in points}
    assert "river" in names["Where the river touches the border of Lusitania"]
    assert "coast" not in names["Where the river touches the border of Lusitania"]


def test_part_of_the_river_is_tagged_river():
    text = (
        "§ 2.5.1  A description of the coast\n"
        "The mouth of the river, which flows into the Outer Sea, is at 5°20' . 41°50'\n"
        "The part of the river where Lusitania begins is at 9°10' . 41°20'\n"
    )
    points = _tagged_point_list(text)
    p = next(p for p in points if "part of the river" in p.name)
    assert p.tags == {"river"}


def test_altars_of_x_is_a_reference_marker_not_coastal():
    # "Altars of X" is Ptolemy's own frontier-marker naming convention,
    # the same idiom as "Gates"/"Pillars of" -- confirmed §3.5.12, where
    # "Altars of Caesar" restates the same river-turn boundary point as
    # "Altars of Alexander" right before it.
    text = (
        "§ 3.5.12  A description of the coast\n"
        "Below the turn of the Tanais river the Altars of Alexander were set up, at 63°00' . 57°00' "
        "and the Altars of Caesar, at 68°00' . 56°30'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"river"}
    assert points[1].tags == {"city"}


def test_bare_named_continuation_chains_through_a_whole_extremities_list():
    # "The extremes of the Hippika mountains are at X and Y; of the
    # Keraunian Z and W; of Korax ...; and of the Kaukasos ..." -- each
    # subsequent range's own first extremity is a bare "[and] of [the]
    # NAME" continuation with no "mountain" keyword of its own, and must
    # chain correctly through the whole list, not just the first pair
    # (confirmed §5.9.15).
    text = (
        "§ 5.9.15  A description of the coast\n"
        "The extremes of the Hippika mountains are at 74°00' . 54°00' and 81°00' . 52°00';\n"
        "of the Keraunian 82°00' . 49°30' and 84°00' . 52°00'\n"
        "of Korax 69°00' . 48°00' and 75°00' . 48°00';\n"
        "and of the Kaukasos 75°00' . 47°30'\n"
        "and 85°00' . 48°00'\n"
    )
    points = _tagged_point_list(text)
    for p in points:
        assert p.tags == {"mountain"}, (p.name, p.tags)


def test_river_mouth_before_reference_marker_loses_to_the_marker():
    # "...south from the Malva river mouth to the limit point at COORD"
    # (confirmed §4.1.8) -- the river mouth is only the boundary line's
    # own starting landmark; the coordinate actually cited is the limit
    # point mentioned *after* it. Whichever keyword sits closest to the
    # coordinate is what the citation is really about.
    text = (
        "§ 4.1.8  A description of the coast\n"
        "The eastern side is bordered by Mauritania Caesarensis south from the Malva river mouth "
        "to the limit point at 11°40' . 26°00'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"city"}


def test_river_mouth_after_reference_marker_still_wins():
    # "...from the limit point at Iberia to the Hyrkanian sea at the mouth
    # of the Kyros river at COORD" (confirmed §5.12.1) -- here the
    # coordinate genuinely *is* the river mouth; "limit point" is only an
    # earlier, unrelated waypoint in the same long boundary sentence.
    text = (
        "§ 5.12.1  A description of the coast\n"
        "Albania is bounded on the north by Sarmatia; on the south by Armenia from the limit point "
        "at Iberia to the Hyrkanian sea at the mouth of the Kyros river at 79°40' . 44°30'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"river_mouth", "coast"}


def test_part_of_this_line_is_a_reference_marker():
    # "...to the part of this line at COORD" (confirmed §5.17.2) -- a
    # restated boundary-line-position idiom, sibling to "limit point of
    # this line at..." (already covered separately by "limit points?").
    text = (
        "§ 5.17.2  A description of the coast\n"
        "to the east its boundary is the line leading to the eastern limit of Syria, "
        "to the part of this line at 70°00' . 30°30'\n"
    )
    points = _tagged_point_list(text)
    assert points[0].tags == {"city"}


def test_connects_at_is_a_river_joining_synonym():
    # "The one through Babylon connects at COORD" (confirmed §5.20.2) --
    # another river tributary meeting its main river. Deliberately narrow
    # ("connects at" specifically): bare "connect" has an unrelated
    # administrative sense elsewhere in this text.
    text = "§ 5.20.2  A description of the coast\nThe one through Babylon connects at 79°00' . 34°55'\n"
    points = _tagged_point_list(text)
    assert points[0].tags == {"river"}


def test_bare_connect_to_a_region_is_not_a_river():
    text = (
        "§ 2.8.1  A description of the coast\n"
        "The sides of Lugdunensis which connect to Aquitania have been described; "
        "Brivates Harbour 17°40' . 48°45'\n"
    )
    points = _tagged_point_list(text)
    assert "river" not in points[0].tags


def test_limit_on_the_side_of_is_a_reference_marker():
    # "The limit on the side of Kolchis is at COORD" (confirmed §5.9.7) --
    # sibling to "limit point" but without the word "point".
    text = "§ 5.9.7  A description of the coast\nThe limit on the side of Kolchis is at 75°00' . 47°30'\n"
    points = _tagged_point_list(text)
    assert points[0].tags == {"city"}
