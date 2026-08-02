from ptolemy.parser import parse_sections
from ptolemy.points import Point, dedup_points, build_occurrence_index
from ptolemy.classify import classify_sections
from ptolemy.tag import tag_points
from ptolemy.coords import convert_points
from ptolemy.lines import build_all_lines, _split_into_runs

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


def test_branch_of_named_river_resolves_to_the_source_river():
    # Confirmed §7.1.28: "Branch of the Indus towards Arachosia", "Branch
    # from the Indus running towards Mt. Ouindion" -- a delta fork point
    # named for its own source river only, no destination given. Without
    # this template these citations had no name of their own at all, and
    # silently inherited whatever unrelated river forward-fill happened
    # to have active at that point in the document instead (confirmed:
    # this exact idiom wrongly polluted the *Sandabal* river's own line
    # with five Indus-only delta citations that immediately preceded it).
    text = (
        "§ 7.1.28  Branch of the Indus towards Arachosia 121°30' . 27°30'\n"
        "Branch from the Indus running towards Mt. Ouindion 123°00' . 29°30'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Indus"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 2


def test_branch_from_x_into_y_links_a_multi_level_delta_tree():
    # Confirmed §7.1.29-30: a delta's own fork tree runs several links
    # deep -- "Branch from the Ganges into the Kambyson Mouth", then
    # further down its own delta, "Branch from the Kambyson River into
    # the Mega Mouth", "Branch from the Mega Mouth into the Kamberichon
    # Mouth". Each link names both the channel it forks *from* and the
    # new one it forks *into*; threading each fork point into both
    # groups is what makes Ganges -> Kambyson -> Mega -> Kamberichon
    # connect end to end into one tree, the same "fingers branching from
    # a knudepunkt" shape historical Ptolemy maps draw for this delta,
    # instead of three separate, disconnected fragments.
    text = (
        "§ 7.1.29  Sources of the Ganges itself 136°00' . 37°00'\n\n\n"
        "§ 7.1.30  Branch from the Ganges into the Kambyson Mouth 146°00' . 22°00'\n"
        "Branch from the Kambyson River into the Mega Mouth 145°00' . 20°00'\n"
        "Branch from the Mega Mouth into the Kamberichon Mouth 145°30' . 19°30'\n"
    )
    points, lines = _build(text)
    rivers = {l.feature_name: l for l in lines if l.kind == "river"}
    assert set(rivers) == {"Ganges", "Kambyson", "Mega"}
    ganges_kambyson = next(p for p in points if p.name.startswith("Branch from the Ganges"))
    kambyson_mega = next(p for p in points if p.name.startswith("Branch from the Kambyson"))
    mega_kamberichon = next(p for p in points if p.name.startswith("Branch from the Mega"))
    assert ganges_kambyson.id in rivers["Ganges"].point_ids
    assert ganges_kambyson.id in rivers["Kambyson"].point_ids
    assert kambyson_mega.id in rivers["Kambyson"].point_ids
    assert kambyson_mega.id in rivers["Mega"].point_ids
    assert mega_kamberichon.id in rivers["Mega"].point_ids


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


def test_anaphoric_lead_uses_the_curated_override_not_the_stale_book_map_name():
    # data/river_anaphoric_leads.csv curates §7.1.73 ("And on the river
    # itself these towns:—") as Ganges -- confirmed by context (follows
    # §7.1.72's own "towards the Ganges", and its first city, Palimbothra,
    # is the historically attested capital on the Ganges), NOT by blindly
    # trusting "whatever river was most recently named earlier in this
    # book_map", which is wrong here: this fixture's own most recent
    # explicit river name is "Adamas", not "Ganges" -- exactly the failure
    # mode confirmed on the real corpus (Ganges established at §7.1.29,
    # but book_map 7.1's own citation stream last *explicitly* names a
    # river at "Mouth of the River Adamas" dozens of sections later, with
    # every intervening tribal/city catalogue only mentioning a river
    # anaphorically in passing prose).
    text = (
        "§ 7.1.17  Mouth of the River Adamas 142°40' . 18°00'\n\n\n"
        "§ 7.1.29  Sources of the Ganges itself 136°00' . 37°00'\n\n\n"
        "§ 7.1.72  Farther east than the Adeisathroi towards the Ganges "
        "are the Mandalai with this city:\n"
        "Asthagoura 142°00' . 25°00'\n\n\n"
        "§ 7.1.73  And on the river itself these towns:\n"
        "Sambalaka 141°00' . 29°30'\n"
        "Palimbothra, the Royal residence 143°00' . 27°00'\n"
    )
    points, lines = _build(text)
    ganges = [l for l in lines if l.kind == "river" and l.feature_name == "Ganges"]
    adamas = [l for l in lines if l.kind == "river" and l.feature_name == "Adamas"]
    assert adamas == []
    sambalaka = next(p for p in points if p.name.startswith("Sambalaka"))
    palimbothra = next(p for p in points if p.name.startswith("Palimbothra"))
    assert len(ganges) == 1
    assert sambalaka.id in ganges[0].point_ids
    assert palimbothra.id in ganges[0].point_ids


def test_alongside_variant_also_folds_bare_city_names_into_the_river():
    # Confirmed §2.9.8: "The territory alongside the Rhine from the sea
    # until the Abrinca River is called Lower Germania; in which the
    # cities are on the west bank..." -- "alongside", not "along", was
    # missing entirely from the bank-city detector.
    text = (
        "§ 2.9.8  The territory alongside the Rhine from the sea until "
        "the Abrinca River is called Lower Germania; in which the cities "
        "are on the west bank, of the Batavians in the interior:\n"
        "Batavodurum 27°15' . 52°30'\n"
        "Lugdunum 27°30' . 52°40'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Rhine"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 2


def test_island_between_two_rivers_folds_its_cities_into_the_named_river():
    # Confirmed §4.7.20: "Here Meroe region is made an island by the Nile
    # River on the west and the Astaboras river on the east, in which are
    # the following cities:" -- the same bare-city-list idiom as "cities
    # are along the river", phrased as an island between two rivers
    # instead.
    text = (
        "§ 4.7.20  Here Meroe region is made an island by the Nile River "
        "on the west and the Astaboras river on the east, in which are "
        "the following cities:\n"
        "Meroe 61°30' . 16°25'\n"
        "Sakolche 61°40' . 15°15'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Nile"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 2


def test_on_the_river_colon_lead_folds_bare_city_names_into_the_river():
    # Confirmed §5.9.29: "on the Bourkas river:\nKoukounda" -- a bare
    # city-list lead phrased as "on the X river", not "along X" or "made
    # an island by X".
    text = (
        "§ 5.9.29  on the Bourkas river:\n"
        "Koukounda 70°00' . 47°45'\n"
        "Sourouba 70°30' . 47°45'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Bourkas"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 2


def test_on_the_river_no_colon_lead_also_folds_bare_city_names():
    # Confirmed §5.9.28: "on the Ouardanos river Skopelos" (no colon at
    # all -- the first city name sits directly after "river") followed by
    # bare city names with no river vocabulary of their own.
    text = (
        "§ 5.9.28  on the Ouardanos river Skopelos 68°00' . 48°00'\n"
        "Sourouba 68°30' . 48°10'\n"
        "Korousia 69°00' . 48°20'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Ouardanos"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 3


def test_on_the_river_at_coord_is_not_treated_as_a_city_list_lead():
    # Confirmed §5.19.1: "bounded... on the Euphrates river at <coord>" is
    # a boundary-limit-point idiom, not a city-list lead -- must not fold
    # a following, unrelated citation into "Euphrates".
    text = (
        "§ 5.19.1  Eremos Arabia is bounded on the north by part of "
        "Mesopotamia on the Euphrates river at 76°15' . 33°20'\n"
        "On the west by the defined parts of Syria 79°00' . 30°10'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river"]
    assert rivers == []


def test_district_city_list_with_one_river_mention_does_not_fold_the_whole_list():
    # Confirmed §5.15.16: "The cities in Kasiotis:\nAntiocheia on the
    # Orontes river ." is a plain regional catalogue (its own colon-
    # delimited heading, "The cities in Kasiotis:", comes *before* the
    # river mention) where only the first entry happens to sit on a
    # river -- Daphne and the rest have no river connection at all and
    # must not be swept into "Orontes".
    text = (
        "§ 5.15.16  The cities in Kasiotis:\n"
        "Antiocheia on the Orontes river 69°00' . 35°30'\n"
        "Daphne 69°00' . 35°25'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Orontes"]
    assert rivers == []
    daphne = next(p for p in points if p.name.startswith("Daphne"))
    for river_line in (l for l in lines if l.kind == "river"):
        assert daphne.id not in river_line.point_ids


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


def test_delta_mouths_heading_seeds_the_river_name_for_unnamed_mouth_citations():
    # Confirmed §4.5.10 ("The seven mouths of the Nile:") and §7.1.18
    # ("Mouths of the Ganges."): every individual mouth citation below the
    # heading names only its own branch ("the Bolbitine mouth"), never the
    # river itself -- point-level river_base_names can never resolve them
    # on their own. The section's own heading is the only place the link
    # exists.
    text = (
        "§ 4.5.10  The seven mouths of the Pyramos:\n"
        "the first mouth 40°00' . 30°00'\n"
        "the second mouth 40°10' . 30°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Pyramos"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 2


def test_delta_mouths_heading_does_not_fold_in_an_interspersed_plain_city():
    # Confirmed §7.1.18: "Poloura, a town" sits between two named Ganges
    # mouths but carries no river vocabulary of its own -- unlike a real
    # "cities are along the river" list (river_bank_city_lead_name), a
    # bare delta heading only ever seeds a name for citations that
    # independently carry the river tag, keeping the resulting line a
    # simple, finger-like set of real mouths rather than sweeping in every
    # incidental nearby place.
    text = (
        "§ 7.1.18  Mouths of the Pyramos.\n"
        "the first mouth 40°00' . 30°00'\n"
        "Somecity, a town 40°05' . 30°00'\n"
        "the second mouth 40°10' . 30°00'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Pyramos"]
    assert len(rivers) == 1
    somecity = next(p for p in points if p.name.startswith("Somecity"))
    assert somecity.id not in rivers[0].point_ids


def test_anaphoric_turn_and_sources_inherit_the_sections_own_named_mouth():
    # Confirmed §5.1.6: "mouth of the Sangarios river" names the river
    # once, then "first turn of the river", "second turn", "third turn",
    # "river sources" carry the river tag (tag.py's own turn/source
    # detection) but never repeat "Sangarios" -- anaphoric continuation of
    # the same citation, not a fresh, differently-named one.
    text = (
        "§ 5.1.6  mouth of the Sangarios river 58°00' . 42°45'\n"
        "first turn of the river 58°10' . 42°40'\n"
        "river sources 58°20' . 42°30'\n"
    )
    points, lines = _build(text)
    rivers = [l for l in lines if l.kind == "river" and l.feature_name == "Sangarios"]
    assert len(rivers) == 1
    assert len(rivers[0].point_ids) == 3


def test_forward_fill_does_not_leak_across_a_book_map_boundary():
    # A river name inherited within one book_map must never bleed into an
    # unrelated later book_map just because it's the most recently seen
    # name in document order -- each book_map's own river citations are
    # independent unless a curated data/river_long_course.csv entry says
    # otherwise (see the cross-book_map bridging tests above).
    text = (
        "§ 5.1.6  mouth of the Sangarios river 58°00' . 42°45'\n"
        "first turn of the river 58°10' . 42°40'\n\n\n"
        "§ 6.1.1  Some other book entirely\n"
        "second turn of the river 40°00' . 30°00'\n"
        "third turn of the river 40°05' . 30°00'\n"
    )
    points, lines = _build(text)
    leaked = [l for l in lines if l.kind == "river" and l.book_map == "6.1"]
    assert leaked == []


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


def _river_point(pid, lon, lat, book_map="2.10"):
    # _split_into_runs only ever looks at .id, .lon_modern, .lat_modern --
    # already-ordered points are handed to it directly, so no real
    # Occurrence/char_offset is needed here.
    p = Point(id=pid, lon_ferro=0.0, lat_ferro=0.0, book_map=book_map)
    p.lon_modern = lon
    p.lat_modern = lat
    p.tags = {"river"}
    return p


def test_wide_cap_step_that_would_self_cross_is_rejected():
    # Confirmed on the real Rhodanus (book.map 2.10): forward-filling its
    # own source ("the source of the river", 5.4 degrees from "the turn
    # of the river toward the Alps") is a correct extension on its own,
    # and the tributary confluence cited right after it in document order
    # (D -> E, well within the *plain* default cap) doesn't cross anything
    # yet either -- but a *second* confluence right after that (E -> F,
    # also an ordinary-looking default-cap step) sits back near the
    # river's mouth rather than its source, and completes a real
    # self-crossing against the earlier B->C and C->D legs. Reproduced
    # here with the same relative shape (translated to round numbers):
    # B->C normal, C->D only clears the *wide* cap, D->E and E->F are
    # both individually ordinary default-cap steps.
    b = _river_point("B", 0.0, 0.0)
    c = _river_point("C", 0.0, 2.42)
    d = _river_point("D", 5.34, 1.5)
    e = _river_point("E", 1.0, 2.67)
    f = _river_point("F", -0.33, 1.67)
    runs = _split_into_runs([b, c, d, e, f], cap=5.0, wide_cap_points={"D": 8.0})
    assert len(runs) == 1
    assert [p.id for p in runs[0]] == ["B", "C", "D", "E"]


def test_wide_cap_step_with_no_crossing_risk_still_connects():
    # The same wide-cap mechanism must still connect a genuine case with
    # no crossing risk at all (confirmed on the real Ana, §2.4.2: "Before
    # the river turns...", "Where the river touches...", "The sources of
    # the river" -- a plain, non-crossing chain 5.1 degrees apart at its
    # widest gap).
    a = _river_point("A", 0.0, 0.0)
    b = _river_point("B", 0.5, 1.0)
    c = _river_point("C", 5.5, 1.5)
    runs = _split_into_runs([a, b, c], cap=5.0, wide_cap_points={"C": 8.0})
    assert len(runs) == 1
    assert [p.id for p in runs[0]] == ["A", "B", "C"]


def test_no_line_self_intersects_on_this_small_fixture():
    from shapely.geometry import LineString
    points, lines = _build(IRELAND_NORTH_WEST)
    point_by_id = {p.id: p for p in points}
    for line in lines:
        coords = [(point_by_id[pid].lon_modern, point_by_id[pid].lat_modern) for pid in line.point_ids]
        if len(coords) < 2:
            continue
        assert LineString(coords).is_simple, f"{line.id} self-intersects"
