from ptolemy.parser import parse_sections

IRELAND_EXCERPT = """§ 2.2.1  Setting of Hivernia British island
A description of the north coast, beyond which is located the Hyperborean ocean:
Boreum promontory 11°00' . 61°00'
Vennicnium promontory 12°50' . 61°20'
mouth of the Vidua river 13°00' . 61°00'


§ 2.2.2  The Vennicni inhabit the west coast; next to them and toward the east are the Rhobogdi


§ 2.2.3  A description of the west side, which borders on the Western ocean
from the Boreum promontory which is in 11°00' . 61°00'
mouth of the Ravius river 11°20' . 60°40'
"""


def test_splits_into_sections_with_book_map_section():
    sections = parse_sections(IRELAND_EXCERPT)
    assert [s.key for s in sections] == ["2.2.1", "2.2.2", "2.2.3"]
    assert sections[0].book == 2
    assert sections[0].map == "2"
    assert sections[0].section == 1


def test_zero_point_section_is_kept():
    sections = parse_sections(IRELAND_EXCERPT)
    assert sections[1].citations == []
    assert "Vennicni" in sections[1].lead_text


def test_citations_extracted_in_document_order():
    sections = parse_sections(IRELAND_EXCERPT)
    assert len(sections[0].citations) == 3
    names = [c.name_phrase for c in sections[0].citations]
    assert names[0] == "Boreum promontory"
    assert names[2] == "mouth of the Vidua river"


def test_bare_degree_without_minutes_is_parsed():
    text = "§ 3.9.1  Title\nSome point 34° . 16°\n"
    sections = parse_sections(text)
    c = sections[0].citations[0]
    assert c.lon_ferro == 34.0
    assert c.lat_ferro == 16.0


def test_trailing_period_after_section_number_does_not_break_marker():
    text = "§ 2.12.1.  Title one\nPoint A 10°00' . 20°00'\n\n\n§ 2.12.2  Title two\nPoint B 11°00' . 21°00'\n"
    sections = parse_sections(text)
    assert [s.key for s in sections] == ["2.12.1", "2.12.2"]
    assert len(sections[0].citations) == 1
    assert len(sections[1].citations) == 1


def test_south_marker_flips_latitude_sign():
    text = "§ 4.7.1  Title\nSome point 51°15' . 3°10' S\n"
    sections = parse_sections(text)
    c = sections[0].citations[0]
    assert c.south is True
    assert c.lat_ferro == -3 - 10 / 60


def test_south_marker_does_not_eat_next_point_name():
    # The dominant false-positive mode: a bare "S" separator swallowing the
    # first letter of the next citation's own name ("Southern promontory").
    text = "§ 2.2.3  Title\nmouth of the Iernus river 8°00' . 58°00'\nSouthern promontory 7°40' . 57°45'\n"
    sections = parse_sections(text)
    citations = sections[0].citations
    assert citations[0].south is False
    assert citations[0].lat_ferro == 58.0
    assert citations[1].name_phrase == "Southern promontory"


def test_footnote_letter_separator_is_tolerated():
    text = "§ 2.3.4  Title\nVarar estuary 28°00 e 59°40'\n"
    sections = parse_sections(text)
    c = sections[0].citations[0]
    assert c.lon_ferro == 28.0
    assert c.lat_ferro == 59 + 40 / 60


def test_restatement_citation_is_still_captured_as_its_own_point():
    sections = parse_sections(IRELAND_EXCERPT)
    third = sections[2]
    assert third.citations[0].lon_ferro == 11.0
    assert third.citations[0].lat_ferro == 61.0
    assert "Boreum promontory" in third.citations[0].name_phrase


def test_bracketed_manuscript_variant_map_number_is_parsed():
    text = "§ 4.8[9].1  Title\nSome point 10°00' . 5°00'\n"
    sections = parse_sections(text)
    assert sections[0].map == "8[9]"
    assert sections[0].book_map == "4.8[9]"


def test_orphan_subheading_between_citations_attaches_to_next_citation():
    # A section can pack more than one island/region walk, each opened by
    # its own bare titled line with no coordinate of its own -- that line
    # must not be silently dropped (§5.2.33, confirmed in the source text).
    text = (
        "§ 5.2.33  Description of Karpathos:\n"
        "Thoantion promontory . 57°00' . 35°20'\n"
        "Description of Rhodes island:\n"
        "Panos promontory . 58°00' . 35°55'\n"
    )
    sections = parse_sections(text)
    names = [c.name_phrase for c in sections[0].citations]
    assert names[0] == "Thoantion promontory"
    assert names[1] == "Description of Rhodes island:\nPanos promontory"


def test_long_intro_sentence_ending_in_colon_does_not_leak_into_next_citation():
    # Ptolemy also ends ordinary multi-clause sentences that merely
    # introduce a sub-list with a colon ("...is the following:") -- unlike
    # a real orphan title, that must NOT get pulled into the next
    # citation's own name_phrase just because it also lacks a coordinate
    # (confirmed regression: §3.8.1, boundary-description prose bleeding
    # into an unrelated city name and flipping its section's classification).
    text = (
        "§ 3.8.1  Dacia\n"
        "Dacia is bounded on the north by Sarmatia already mentioned, at . 53°00' . 48°30'\n"
        "On the south by part of the Danube river from the fork of the Tibiskos river "
        "as far as Axioupolis, from which point as far as Pontos and the river mouth "
        "the Danube is called Istros. The position of this part is the following:\n"
        "After the fork of the Tibiskos river the first bend to the south, 47°20' . 44°45'\n"
    )
    sections = parse_sections(text)
    names = [c.name_phrase for c in sections[0].citations]
    assert "mouth" not in names[1]
    assert names[1] == "After the fork of the Tibiskos river the first bend to the south"
