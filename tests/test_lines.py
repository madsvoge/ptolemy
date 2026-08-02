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
