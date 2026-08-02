from ptolemy.parser import parse_sections
from ptolemy.points import dedup_points, trim_name

RESTATEMENT_TEXT = """§ 2.2.1  Setting of Hivernia
North coast:
Boreum promontory 11°00' . 61°00'
Rhobogdium promontory 16°20' . 61°30'


§ 2.2.3  West side
from the Boreum promontory which is in 11°00' . 61°00'
mouth of the Ravius river 11°20' . 60°40'
"""


def test_near_identical_coordinates_dedup_into_one_point():
    sections = parse_sections(RESTATEMENT_TEXT)
    points = dedup_points(sections)
    boreum = [p for p in points if "Boreum" in p.name]
    assert len(boreum) == 1
    assert len(boreum[0].occurrences) == 2


def test_dedup_scoped_to_book_map():
    text = (
        "§ 2.2.1  Title\nPoint A 11°00' . 61°00'\n\n\n"
        "§ 2.3.1  Title\nPoint A again 11°00' . 61°00'\n"
    )
    sections = parse_sections(text)
    points = dedup_points(sections)
    assert len(points) == 2
    assert {p.book_map for p in points} == {"2.2", "2.3"}


def test_trim_name_recovers_bare_name_from_restatement():
    assert trim_name("from the Boreum promontory which is in") == "Boreum promontory"


def test_trim_name_uses_text_after_last_colon():
    assert trim_name("The following are the inland towns: Regia") == "Regia"


def test_trim_name_leaves_descriptive_names_untouched():
    assert trim_name("mouth of the Vidua river") == "mouth of the Vidua river"


def test_trim_name_recovers_bare_city_name_from_tribal_restatement():
    # Confirmed §2.9.7: "Further east than the Remi are, more northerly,
    # the Treveri and their city Augusta Treverum" was becoming the
    # point's whole *name* -- neither the leading nor trailing stopword
    # trim reaches into the middle of a sentence to cut this down to just
    # "Augusta Treverum", the city's own real name.
    text = (
        "Further east than the Remi are, more northerly, the Treveri and "
        "their city Augusta Treverum"
    )
    assert trim_name(text) == "Augusta Treverum"


def test_trim_name_recovers_bare_city_name_with_aside_before_the_verb():
    # Confirmed §2.9.6: an aside sits between "whose city" and the verb
    # that finally introduces the real name -- "Ratomagus" must still be
    # isolated, not "Sequana River" (also capitalized, but not the name).
    text = (
        "And below these are the Subanecti whose city on the eastern "
        "bank of the Sequana River is Ratomagus"
    )
    assert trim_name(text) == "Ratomagus"


def test_trim_name_recovers_bare_town_name_with_no_verb_at_all():
    # Confirmed §2.3.10: "the town Petuaria" with no "is"/"being" verb.
    text = "Near which on the Opportunum bay are the Parisi and the town Petuaria"
    assert trim_name(text) == "Petuaria"


def test_canonical_name_prefers_shortest_cleaned_variant():
    sections = parse_sections(RESTATEMENT_TEXT)
    points = dedup_points(sections)
    boreum = next(p for p in points if "Boreum" in p.name)
    assert boreum.name == "Boreum promontory"
