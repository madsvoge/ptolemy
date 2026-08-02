from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points, build_occurrence_index
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points
from ptolemy.coords import convert_points
from ptolemy.lines import build_all_lines

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




def test_coastal_walk_ignores_a_points_own_restated_boundary_occurrence():
    # Confirmed §2.5.1/§2.5.3 (Lusitania): the Dourius river mouth is
    # restated once as the province's own opening boundary landmark
    # ("...is the common boundary with...the mouth of the river...is at
    # COORD"), then cited again, correctly, as the real coastal walk's own
    # last point. Both citations dedup to one Point, and since the point's
    # own 'coast' tag is an aggregate across all its occurrences, the walk
    # used to include it *twice* -- once at its boundary-declaration
    # position (stitching a spurious early detour there), once at its real
    # place. Only the occurrence whose own section actually resolved
    # COASTAL belongs in the drawn coastline.
    text = (
        "§ 2.5.1  LUSITANIA\n"
        "The southern side of Lusitania is the common boundary with the "
        "northern side of Baetica, along the western part of the Dourius "
        "river. The mouth of the river, which flows into the Outer Sea, "
        "is at 5°20' . 41°50'\n\n\n"
        "§ 2.5.2  A description of the coast:\n"
        "Balsa 3°40' . 37°45'\n"
        "Ossonoba 3°00' . 37°50'\n\n\n"
        "§ 2.5.3  Of the Lusitani:\n"
        "Oliosipum 5°10' . 40°15'\n"
        "Dourius river mouth 5°20' . 41°50'\n"
    )
    points, lines = _build(text)
    coastlines = [l for l in lines if l.kind == "coastline"]
    assert len(coastlines) == 1
    trail = coastlines[0]
    dourius = next(p for p in points if p.name == "Dourius river mouth")
    assert trail.point_ids.count(dourius.id) == 1
    assert trail.point_ids[-1] == dourius.id


def test_new_coastal_side_lead_splits_the_coastal_walk():
    # Confirmed §5.1.5, Bithynia: the region's coast runs two separate
    # directions from the same Bosporos-mouth starting point (west along
    # the Propontis/gulf side, then -- restated via "which is thus
    # described: after..." -- north along the Black Sea side). Without
    # splitting there, the Propontis arc's own inland end (up a river to
    # its sources) connected straight to the Black Sea arc's own start, a
    # nonsensical jump across the whole peninsula (confirmed P3523/P3525).
    text = (
        "§ 5.1.2  The promontory of Bithynia at the mouth of the Pontos, on which are:\n"
        "Hieron of Artemis 56°25' . 43°20'\n"
        "Chalkedon 56°05' . 43°05'\n\n\n"
        "§ 5.1.4  Posideion promontory 56°10' . 42°25'\n"
        "mouth of the Ryndakos river 56°20' . 41°45'\n\n\n"
        "§ 5.1.5  On the north it is bounded by a part of the Euxine "
        "Pontos, which is thus described: after the mouth of the Pontos "
        "and the sanctuary of Artemis\n"
        "Bithynian promontory 56°45' . 43°20'\n"
        "Artake kome 57°00' . 43°05'\n"
    )
    points, lines = _build(text)
    coastlines = [l for l in lines if l.kind == "coastline"]
    assert len(coastlines) == 2
    point_by_id = {p.id: p for p in points}
    names_by_trail = [{point_by_id[pid].name for pid in l.point_ids} for l in coastlines]
    propontis = next(n for n in names_by_trail if "Chalkedon" in n)
    black_sea = next(n for n in names_by_trail if n is not propontis)
    assert "mouth of the Ryndakos river" in propontis
    assert "Artake kome" not in propontis
    assert "Bithynian promontory" in black_sea


def test_new_coastal_arc_citation_phrase_splits_the_coastal_walk():
    # Confirmed §3.11.3, Thrace: the region's coast, like Bithynia's, runs
    # two separate directions from its own Bosporos-mouth boundary. Unlike
    # Bithynia's own purely-orientation restatement, this citation's own
    # coordinate ("...until the border with lower Moesia, at COORD") is a
    # real point, only ~0.3 degrees from Mesembria which immediately
    # follows it -- it belongs in the walk, as the Black Sea arc's own
    # first point, not excluded outright. Without a hard break *before*
    # it, the point right before it in document order stitched straight
    # across to it instead (confirmed P1972/P1974, skipping the whole
    # Bosporos peninsula between the Aegean and Black Sea coasts).
    text = (
        "§ 3.11.2  Nestos river mouth 51°45' . 41°45'\n"
        "border of Chersonesos on Propontis 53°17' . 41°50'\n\n\n"
        "§ 3.11.3  On the east by the Propontis and the mouth of Pontos, "
        "called the Thracian Bosporos, and by the onward shores of Pontos "
        "until the border with lower Moesia, at 55°00' . 44°40'\n"
        "Mesembria of Moesia, Anchialos 54°45' . 44°30'\n"
        "Apollonia 54°50' . 44°20'\n"
    )
    points, lines = _build(text)
    coastlines = [l for l in lines if l.kind == "coastline"]
    assert len(coastlines) == 2
    point_by_id = {p.id: p for p in points}
    names_by_trail = [{point_by_id[pid].name for pid in l.point_ids} for l in coastlines]
    aegean = next(n for n in names_by_trail if "border of Chersonesos on Propontis" in n)
    black_sea = next(n for n in names_by_trail if n is not aegean)
    assert "Mesembria of Moesia, Anchialos" not in aegean
    assert "Mesembria of Moesia, Anchialos" in black_sea
    # The boundary citation itself opens the Black Sea trail as a real,
    # included point -- not dropped from the map entirely.
    assert any("lower Moesia" in name for name in black_sea)


def test_mid_book_map_region_declaration_splits_the_coastal_walk():
    # Confirmed §3.14.25, "Position of the Peloponnesos": Ptolemy's own
    # Achaia map (book.map 3.14) covers both mainland Greece and the
    # separate Peloponnese peninsula as one catalogue unit, and the
    # Peloponnese's own coastal description opens by restating the
    # mainland's last-cited point (Pegai) purely for orientation. Without
    # splitting there, the whole book.map's citations formed one long
    # trail whose first point (mainland) and last point (Peloponnese)
    # happened to sit close enough to spuriously "close the loop",
    # self-intersecting near the isthmus (confirmed P2437/P2243).
    text = (
        "§ 3.14.2  After the Acheloos river, which is the border of Epiros, "
        "as follows: Aitolia\n"
        "Chersonesos promontory 48°30' . 37°25'\n"
        "Euenos river outlet 49°00' . 37°30'\n\n\n"
        "§ 3.14.6  Megarid\n"
        "Pegai 51°25' . 37°25'\n"
        "Nisaia 52°00' . 37°20'\n\n\n"
        "§ 3.14.25  Position of the Peloponnesos: bounded to the north by "
        "the Corinthian Gulf.\n"
        "And the shore of this has the following description:\n\n\n"
        "§ 3.14.26  After Pegai in the Megarid, which is in the Corinthian "
        "gulf off Achaia, at degrees 51°25' . 37°25'\n\n\n"
        "§ 3.14.27  Of the Korinthia:\n"
        "Lechaion port 51°20' . 37°00'\n"
        "Schoinous harbor 50°45' . 36°50'\n"
    )
    points, lines = _build(text)
    coastlines = [l for l in lines if l.kind == "coastline"]
    assert len(coastlines) == 2
    point_by_id = {p.id: p for p in points}
    mainland = next(l for l in coastlines if any(
        point_by_id[pid].name == "Chersonesos promontory" for pid in l.point_ids))
    peloponnese = next(l for l in coastlines if l is not mainland)
    # The mainland trail must not reach all the way to Schoinous harbor
    # (the Peloponnese's own point), and vice versa -- they're two
    # separate trails now, not one spuriously self-closing loop.
    mainland_names = {point_by_id[pid].name for pid in mainland.point_ids}
    peloponnese_names = {point_by_id[pid].name for pid in peloponnese.point_ids}
    assert "Schoinous harbor" not in mainland_names
    assert "Chersonesos promontory" not in peloponnese_names
    # Pegai itself is the deliberate hand-off point: its real §3.14.6
    # citation belongs to the mainland trail, and its restated §3.14.26
    # occurrence correctly opens the Peloponnese's own trail -- appearing
    # once in each, by design, not a spurious revisit within either one.
    assert mainland.point_ids.count(
        next(p.id for p in points if p.name == "Pegai")) == 1
    assert peloponnese.point_ids.count(
        next(p.id for p in points if p.name == "Pegai")) == 1


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


def test_sentence_initial_capitalized_mouth_and_sources_are_still_named():
    # Confirmed throughout book 7 (India): a citation that opens its own
    # section is routinely sentence-initial and capitalized ("Mouth of
    # the River Lykos", "Sources of the River Zaradros") where the same
    # idiom elsewhere in the corpus uses lowercase ("mouth of the river
    # Rhymmos"). The river/mountain templates used to be case-sensitive
    # for the keywords themselves (not just the captured name), so every
    # sentence-initial citation like this was silently left unnamed and
    # dropped from every river line -- confirmed a real, wide gap
    # (433 -> 518 of 699 river-tagged points corpus-wide gained a name).
    text = (
        "§ 7.1.27  Sources of the River Zaradros 120°00' . 35°00'\n\n\n"
        "§ 7.1.31  Mouth of the River Zaradros 122°00' . 32°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert len(rivers) == 1
    assert rivers[0].feature_name == "Zaradros"
    assert len(rivers[0].point_ids) == 2


def test_confluence_citation_links_tributary_into_the_main_river():
    # Confirmed §7.1.26-30 (Indus/Ganges tributary catalogue): "Confluence
    # of the Koa and Indus" is simultaneously the Koa's own endpoint and a
    # real waypoint on the Indus's course. Without linking it into *both*
    # groups, the tributary's own line stopped just short of the river it
    # joins -- an unconnected loose end sitting right next to it, instead
    # of visibly meeting it.
    text = (
        "§ 7.1.26  The rivers which flow from Mount Imaos into the Indus:\n"
        "Sources of the River Koa 120°00' . 35°00'\n"
        "Confluence of the Koa and Indus 123°00' . 32°00'\n"
        "Mouth of the Indus 125°00' . 29°00'\n"
    )
    points, lines = _build(text)
    rivers = {l.feature_name: l for l in lines if l.kind == "river"}
    assert set(rivers) == {"Koa", "Indus"}
    confluence = next(p for p in points if p.name.startswith("Confluence"))
    assert confluence.id in rivers["Koa"].point_ids
    assert confluence.id in rivers["Indus"].point_ids


def test_cities_along_the_river_lead_folds_bare_city_names_into_the_river():
    # Confirmed §3.10.5: "The following cities are along the Danube
    # river:" followed by bare city names carrying no river vocabulary of
    # their own ("Rhegianon", not "Rhegianon on the Danube") -- point-level
    # river detection can never catch these; only the section's own lead
    # names the river they belong to.
    text = (
        "§ 3.10.5  The following cities are along the Danube river:\n"
        "Rhegianon 50°00' . 45°00'\n"
        "Dorticum 51°00' . 45°10'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Danube"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 2


def test_tribal_aside_naming_a_river_in_passing_does_not_fold_its_cities_in():
    # Confirmed §2.9.10: "...are the Helveti along the River Rhine, with
    # cities Ganodurum..." has "cities" and "along the river" both
    # present, but "cities" is a later, unrelated aside naming the
    # tribe's own towns, not a "cities are along the river" list header --
    # "are" governs "the Helveti", not "cities". Connecting these
    # non-geographically-ordered tribal-list points as if they were a
    # real river-walk produced a genuine self-crossing (confirmed).
    text = (
        "§ 2.9.10  And after the mountain, are the Helveti along the "
        "River Rhine, with cities Ganodurum 28°30' . 46°30'\n"
        "Forum Tiberii 28°00' . 46°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Rhine"]
    assert rivers == []


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


def test_curated_long_course_river_bridges_across_book_maps():
    # Danube is in data/river_long_course.csv (curated, human-verified),
    # with its own cap wide enough to bridge a real cross-book_map gap that
    # the shared default RIVER_CAP_DEG (5 degrees) would leave split.
    # Confirmed on the real corpus: the Danube's own citations span
    # book_maps 2.11 through 3.10, and blindly widening the shared default
    # cap for every river reintroduces a known false-merge (two different
    # rivers both named Alaunus in Britain, 6.9 degrees apart) -- so this
    # only works for a name the allowlist actually covers.
    text = (
        "§ 2.11.1  Germania Magna\n"
        "The source of the river Danube 30°00' . 48°00'\n\n\n"
        "§ 3.10.1  Lower Moesia\n"
        "Mouth of the river Danube 45°00' . 46°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Danube"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 2


def test_river_alias_normalizes_istros_to_danube():
    # Confirmed §3.8.2: "the Danube is also called Istros as far as the
    # mouth" -- data/river_aliases.csv folds "Istros" citations into the
    # same "Danube" group rather than leaving them as two separate,
    # unconnected single-citation rivers.
    text = (
        "§ 2.11.1  Germania Magna\n"
        "The source of the river Danube 30°00' . 48°00'\n\n\n"
        "§ 3.8.1  Lower Moesia\n"
        "mouth of the Istros river 32°00' . 47°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert len(rivers) == 1
    assert rivers[0].feature_name == "Danube"
    assert len(rivers[0].point_ids) == 2


def test_landmark_handoff_after_mouth_does_not_fold_the_next_named_point_into_the_river():
    # Confirmed §3.10.3: "after the Sacred mouth of the Istros river,
    # Pteron promontory <coord>" is a *coastal* citation that merely uses
    # the Danube's mouth as its own positional landmark -- the coordinate
    # belongs to Pteron, not the Danube. Without this guard the river
    # template still matched "Danube" in the first half of the phrase and
    # folded a coastal point more than 30 degrees from the Danube's real
    # course into its line (a self-crossing).
    text = (
        "§ 3.8.1  Lower Moesia\n"
        "The source of the river Danube 30°00' . 48°00'\n\n\n"
        "§ 3.10.1  The coastal side\n"
        "after the mouth of the Danube river, Pteron promontory 31°00' . 6°00'\n"
    )
    points, lines = _build(text)
    rivers = {l.feature_name: l for l in lines if l.kind == "river"}
    assert "Danube" not in rivers
    pteron = next(p for p in points if p.name.startswith("Pteron") or "Pteron" in p.name)
    for river_line in (l for l in lines if l.kind == "river"):
        assert pteron.id not in river_line.point_ids


def test_uncurated_river_name_does_not_bridge_across_book_maps():
    # Lykos is *not* in data/river_long_course.csv -- a shared name across
    # two far-apart book_maps must stay unconnected (the safe default),
    # not silently bridged the way an explicitly curated name is.
    text = (
        "§ 2.9.1  A description of the coast\n"
        "mouth of the Lykos river 25°00' . 53°00'\n\n\n"
        "§ 5.2.1  Some other region entirely\n"
        "source of the river Lykos 40°00' . 48°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Lykos"]
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


def test_island_section_closes_into_its_own_loop():
    # A single named island's own coastal walk, embedded inside a shared/
    # mainland book.map (confirmed §3.14.22, Euboia) -- its points don't
    # carry "island" in their own name, so build_islands' name-matching
    # leaves them all standalone; build_island_walks must connect them by
    # catalogue order instead, scoped to this section only, and close the
    # loop since the last point (Dion) lands right back near the first
    # (Kenaion).
    text = (
        "§ 3.14.22  islands adjacent to Achaia in the Aegean sea, Euboia being large, "
        "with a description as follows:\n"
        "Kenaion promontory . 52°20' . 38°35'\n"
        "Chalkis on the Euripos . 53°10' . 38°00'\n"
        "Karystos . 54°30' . 37°40'\n"
        "Dion promontory . 53°00' . 38°35'\n"
    )
    points, lines = _build(text)
    walks = [l for l in lines if l.kind == "island" and l.id.startswith("island-walk-")]
    assert len(walks) == 1
    assert walks[0].closed is True
    assert len(walks[0].point_ids) == 4


def test_island_walk_does_not_bridge_into_the_next_section():
    # Two separate named-island-walk sections sitting back to back (Lesbos,
    # then Karpathos) must stay two separate trails, not one merged line --
    # each section is Ptolemy's own bounded description of a single island,
    # unlike coastal sections which are meant to chain across a whole
    # book.map.
    text = (
        "§ 5.2.29  In the Aegean sea Lesbos, an Aiolian island, described as follows:\n"
        "Sigrion promontory . 55°00' . 40°00'\n"
        "Mytilene . 55°40' . 39°40'\n\n\n"
        "§ 5.2.33  Description of Karpathos:\n"
        "Thoantion promontory . 57°00' . 35°20'\n"
        "Poseidion city . 57°20' . 35°25'\n"
    )
    points, lines = _build(text)
    walks = [l for l in lines if l.kind == "island" and l.id.startswith("island-walk-")]
    assert len(walks) == 2
    ids_by_walk = [set(w.point_ids) for w in walks]
    assert ids_by_walk[0].isdisjoint(ids_by_walk[1])


def test_two_named_islands_packed_in_one_section_stay_separate_walks():
    # Confirmed bug, §5.2.33: "Description of Karpathos:" and, mid-section,
    # a second bare heading "Description of Rhodes island:" -- both
    # citation lists land in the same §-numbered Section (the parser only
    # splits on § markers), so without detecting the second heading,
    # build_island_walks connected Karpathos's last point straight to
    # Rhodes's first, drawing one self-crossing loop hopping between two
    # unrelated islands instead of two separate trails.
    text = (
        "§ 5.2.33  Description of Karpathos:\n"
        "Thoantion promontory . 57°00' . 35°20'\n"
        "Poseidion city . 57°20' . 35°25'\n"
        "Description of Rhodes island:\n"
        "Panos promontory . 58°00' . 35°55'\n"
        "Kameiros . 58°20' . 35°15'\n"
        "Lindos . 58°40' . 36°00'\n"
    )
    points, lines = _build(text)
    walks = [l for l in lines if l.kind == "island" and l.id.startswith("island-walk-")]
    assert len(walks) == 2
    ids_by_walk = [set(w.point_ids) for w in walks]
    assert ids_by_walk[0].isdisjoint(ids_by_walk[1])
    karpathos = next(w for w in walks if len(w.point_ids) == 2)
    names = {p.name for p in points if p.id in karpathos.point_ids}
    assert names == {"Thoantion promontory", "Poseidion city"}


def test_island_list_section_is_not_blanket_connected():
    # A section that lists several distinct islands (each named as it
    # goes) must NOT have its points blanket-connected by catalogue-order
    # adjacency the way a single named island's own walk is -- confirmed
    # bug: doing so for every ISLAND-classified section drew nonsense
    # self-intersecting lines hopping between unrelated islands cited back
    # to back in the same list (§5.2.30, Islands in the Ikarian sea).
    text = (
        "§ 5.2.30  Islands in the Ikarian sea:\n"
        "Ikaros island . 56°45' . 37°20'\n"
        "Myndos . 57°40' . 36°25'\n"
    )
    points, lines = _build(text)
    walks = [l for l in lines if l.kind == "island" and l.id.startswith("island-walk-")]
    assert walks == []


def test_no_line_self_intersects_on_this_small_fixture():
    from shapely.geometry import LineString
    points, lines = _build(IRELAND_NORTH_WEST)
    point_by_id = {p.id: p for p in points}
    for line in lines:
        coords = [(point_by_id[pid].lon_modern, point_by_id[pid].lat_modern) for pid in line.point_ids]
        if len(coords) < 2:
            continue
        assert LineString(coords).is_simple, f"{line.id} self-intersects"
