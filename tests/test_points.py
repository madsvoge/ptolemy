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


def test_canonical_name_prefers_shortest_cleaned_variant():
    sections = parse_sections(RESTATEMENT_TEXT)
    points = dedup_points(sections)
    boreum = next(p for p in points if "Boreum" in p.name)
    assert boreum.name == "Boreum promontory"
