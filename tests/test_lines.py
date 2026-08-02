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


def test_river_source_to_mouth_matches_users_india_worked_example():
    # The exact case the "sources to mouth" methodology was designed for
    # (confirmed §7.1.10/§7.1.34, the Solen -- one of the user's own two
    # worked examples): a RIVER section gives the source and a bend, and
    # the river's mouth is a same-named citation elsewhere in the same
    # book.map's coastal walk, cited earlier in the text. The trail is
    # built source-first even though the mouth is walked first in
    # document order (see _reorder_river_trail).
    text = (
        "§ 7.1.10  A description of the coast\n"
        "Mouth of the river Solen 100°00' . 15°00'\n\n\n"
        "§ 7.1.34  Sources of the River Solen in the Bettigo range 130°00' . 15°20'\n"
        "The point where it turns 131°00' . 16°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert len(rivers) == 1
    assert rivers[0].feature_name == "Solen"
    names = [next(p.name for p in points if p.id == pid) for pid in rivers[0].point_ids]
    assert names == [
        "Sources of the River Solen in the Bettigo range",
        "point where it turns",
        "Mouth of the river Solen",
    ]


def test_river_branching_network_matches_users_india_worked_example():
    # The user's own second worked example: Namados/Baris bending and
    # confluencing with Moghis, which then bifurcates into Goaris and
    # Binda, each ending at its own separately catalogued mouth --
    # including the hand-confirmed spelling variants between a RIVER
    # section's own wording and its coastal mouth citation (Moghis/
    # Mophis, Goaris/Binda's "Benda").
    text = (
        "§ 7.1.4  A description of the coast\n"
        "Mouth of the River Mophis 97°00' . 18°00'\n"
        "Mouth of the River Namados 96°00' . 17°30'\n"
        "Mouth of the river Goaris 95°00' . 17°00'\n"
        "Mouth of the River Benda 94°30' . 16°30'\n\n\n"
        "§ 7.1.31  And of the other rivers the positions are thus:\n"
        "The sources of the River Namados in the Ouindion range 109°00' . 26°00'\n"
        "The bend of the river at Seripala 100°00' . 22°00'\n"
        "Its confluence with the River Moghis 98°00' . 19°00'\n\n\n"
        "§ 7.1.32  Sources of the River Nanagouna from the Ouindion range 108°00' . 25°00'\n"
        "Where it bifurcates into the Goaris and Binda 99°00' . 20°00'\n"
    )
    points, lines = _build(text)
    rivers = {l.feature_name: l for l in lines if l.kind == "river"}
    assert set(rivers) == {"Namados", "Mophis", "Goaris", "Benda"}

    def names_of(feature_name):
        return [next(p.name for p in points if p.id == pid) for pid in rivers[feature_name].point_ids]

    assert names_of("Namados") == [
        "sources of the River Namados in the Ouindion range",
        "bend of the river at Seripala",
        "Its confluence with the River Moghis",
        "Mouth of the River Namados",
    ]
    # The bifurcation point is a shared graph node between both branches.
    bifurcation = "Where it bifurcates into the Goaris and Binda"
    assert names_of("Goaris") == [bifurcation, "Mouth of the river Goaris"]
    assert names_of("Benda") == [bifurcation, "Mouth of the River Benda"]
    # Moghis/Mophis: a spelling variant between the RIVER section's own
    # wording and the coastal mouth's, resolved via the alias table.
    assert names_of("Mophis") == ["Its confluence with the River Moghis", "Mouth of the River Mophis"]


def test_coastal_mouth_immediately_followed_by_its_own_source_is_connected():
    # Confirmed real and common (32 cases corpus-wide, found by the user):
    # an ordinary coastal walk gives a river's mouth and then, a citation
    # or two later, that same river's own bare "sources of the river" --
    # with no RIVER section involved at all (§7.3.2, §2.11.1). The
    # in-between town must not be swept into either river's trail.
    text = (
        "§ 7.3.2  A description of the coast\n"
        "After the boundary of the Gulf on the side of India the mouth of the river Aspithra 150°00' . 10°00'\n"
        "Sources of the river on the eastern side of the Semanthinos range 151°00' . 11°00'\n"
        "Bramma, a town 152°00' . 12°00'\n"
        "The mouth of the river Ambastes 153°00' . 13°00'\n"
        "The sources of the river 154°00' . 14°00'\n"
        "Rhabana, a town 155°00' . 15°00'\n"
    )
    points, lines = _build(text)
    rivers = {l.feature_name: l for l in lines if l.kind == "river"}
    assert set(rivers) == {"Aspithra", "Ambastes"}
    for feature_name in ("Aspithra", "Ambastes"):
        assert len(rivers[feature_name].point_ids) == 2
    town_ids = {p.id for p in points if p.name in ("Bramma, a town", "Rhabana, a town")}
    for line in rivers.values():
        assert not town_ids & set(line.point_ids)


def test_multiple_rivers_mouth_source_pairs_in_one_coastal_list():
    # Confirmed §2.11.1: several rivers, each cited "Mouths of the river
    # X" immediately followed by its own bare "Sources of the river" --
    # each pair must resolve to its own river, never bleed into its
    # neighbour's.
    text = (
        "§ 2.11.1  A description of the coast\n"
        "Mouths of the river Amisius 29°00' . 55°00'\n"
        "Sources of the river 30°00' . 56°00'\n"
        "Mouths of the river Visurgius 31°00' . 55°30'\n"
        "Sources of the river 32°00' . 56°30'\n"
    )
    points, lines = _build(text)
    rivers = {l.feature_name: l for l in lines if l.kind == "river"}
    assert set(rivers) == {"Amisius", "Visurgius"}
    for feature_name in ("Amisius", "Visurgius"):
        assert len(rivers[feature_name].point_ids) == 2


def test_river_turn_with_no_source_citation_still_connects_to_its_mouth():
    # Confirmed §3.1.5, the Tiber: a coastal walk's river mouth is
    # followed only by a generic "where the river turns..." with no
    # "sources of" citation at all before reverting to ordinary coastal
    # cities -- the pair still connects, and Ostia must not be swept in.
    text = (
        "§ 3.1.5  A description of the coast\n"
        "mouth of the Tiber river 36°30' . 41°40'\n"
        "where the river turns toward the west 36°00' . 42°00'\n"
        "Ostia 36°30' . 41°35'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert len(rivers) == 1
    assert rivers[0].feature_name == "Tiber"
    assert len(rivers[0].point_ids) == 2
    ostia_id = next(p.id for p in points if p.name == "Ostia")
    assert ostia_id not in rivers[0].point_ids


def test_boundary_section_tracing_a_rivers_fork_points_is_connected():
    # Confirmed §3.8.1: Dacia's own boundary declaration is classified
    # BOUNDARY (not RIVER or COASTAL), but the citations after its lead
    # trace a river by its own fork/bend points -- "fork of X river" is
    # as unambiguous an opening idiom as "mouth of X river", so this
    # still connects even though the section itself isn't about a river.
    text = (
        "§ 3.8.1  Dacia\n"
        "Dacia is bounded on the north by the part of Sarmatia in Europe from Mt. "
        "Karpatos to the limit of the return of the Tyras river already mentioned, "
        "which, as mentioned, is at 46°00' . 48°30'\n"
        "The fork of the Rhabon river, which flows to Dacia 45°00' . 47°15'\n"
        "The bend at Oiskos 44°30' . 47°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert len(rivers) == 1
    assert rivers[0].feature_name == "Rhabon"
    assert len(rivers[0].point_ids) == 2


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
