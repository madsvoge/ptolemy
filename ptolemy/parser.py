"""Step 1: parse topostext's raw Ptolemy Geographica text into ordered
§ book.map.section paragraphs, each carrying its lead text and every
(name_phrase, lon, lat) coordinate citation in document order.

Source: topostext.org work/209, Kiesling's translation from Nobbe's 1843
Greek text. This module treats that text as the sole source of truth --
no external gazetteer, no other manuscript tradition.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

# "§ 2.2.1  Title..." -- book/map/section are plain digits, map can also be
# a bracketed manuscript variant like "8[9]" (topostext's own way of
# flagging a disputed map number, e.g. "§ 4.8[9].1"). A trailing period
# after the section digits ("§ 2.12.1.") is optional and must not break
# the marker match.
_SECTION_MARKER = re.compile(
    r"^§[ \t]*(\d+)\.([0-9A-Za-z\[\]]+)\.(\d+)\.?[ \t]*", re.MULTILINE
)
# Non-catalogue front matter markers like "§ i" (no book.map.section triple).
_FRONT_MATTER_MARKER = re.compile(r"^§[ \t]*([A-Za-z]+)[ \t]*", re.MULTILINE)

_DEGREES = r"\d{1,3}°(?:\s?\d{1,2}\'?)?"
# lon SEP lat [S], where SEP is normally '.' but is sometimes a stray
# single letter -- an OCR/transcription footnote marker leaking into the
# separator position (confirmed in this text, e.g. "14°00 d 51°45'").
#
# The south marker itself ("S", "S.", or the "S.L." variant seen around
# lon 160-164) must NOT be followed by a letter, or it silently eats the
# initial "S" of the next point's own name (e.g. "58°00'\nSouthern
# promontory" would otherwise misparse as a false south marker plus a
# name_phrase of "outhern promontory") -- confirmed as the dominant
# failure mode: of ~480 candidate "S" sightings in this text, only 56 are
# real hemisphere markers, the rest are the next citation's name starting
# with a capital S.
_COORD_PAIR = re.compile(
    rf"(?P<lon>{_DEGREES})\s*(?:[.,]|[A-Za-z](?!\w))\s*(?P<lat>{_DEGREES})"
    rf"(?:(?P<south>\s*S(?:\.L)?\.?)(?![A-Za-z]))?"
)


@dataclass
class Citation:
    name_phrase: str
    lon_ferro: float
    lat_ferro: float
    south: bool
    char_offset: int  # position within the full source text, for ordering/debugging


@dataclass
class Section:
    book: int
    map: str  # kept as topostext's own token (usually numeric, occasionally "8[9]")
    section: int
    title_line: str
    lead_text: str
    citations: list[Citation] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.book}.{self.map}.{self.section}"

    @property
    def book_map(self) -> str:
        return f"{self.book}.{self.map}"


def _parse_degrees(token: str) -> float:
    m = re.match(r"(\d{1,3})°\s?(\d{1,2})?", token)
    deg = int(m.group(1))
    minutes = int(m.group(2)) if m.group(2) else 0
    return deg + minutes / 60.0


def extract_citations(text: str, base_offset: int = 0) -> list[Citation]:
    """Extract every (name_phrase, lon, lat) triple from `text`, in order.

    A citation's name_phrase is the text since the later of (a) the end of
    the previous citation, or (b) the start of the current line -- this
    keeps phrases like "from the Boreum promontory which is in" intact when
    a citation opens a line, without also dragging in unrelated lead-in
    prose from earlier lines (e.g. a section's own title, or an unrelated
    sentence of boundary-description prose several lines back).

    The one exception: if the line immediately above is itself a short,
    bare, coordinate-free title ending in ":" (e.g. "Description of Rhodes
    island:", sitting between two citations because a section can pack more
    than one island/region walk), that heading line is pulled in too --
    otherwise it's silently dropped, belonging to neither the section's
    lead_text nor any citation's own phrase, even though it's the only
    thing naming what follows. The word-count cap is what keeps this
    narrow: Ptolemy also uses a trailing colon to end ordinary multi-clause
    sentences that merely *introduce* a sub-list ("...the river mouth the
    Danube is called Istros. The position of this part is the
    following:"), and those must NOT leak into the next citation's phrase
    just because they also happen to lack a coordinate of their own
    (confirmed regressed §3.8.1-4 without this cap, where a long sentence
    of boundary-description prose several lines back was pulled into an
    unrelated city's name_phrase) -- a real naming title, by contrast, is
    always a short noun phrase.
    """
    citations: list[Citation] = []
    prev_end = 0
    for m in _COORD_PAIR.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        phrase_start = max(prev_end, line_start)
        if prev_end != 0 and phrase_start == line_start and line_start > 0:
            prev_line_end = line_start - 1
            prev_line_start = text.rfind("\n", 0, prev_line_end) + 1
            prev_line = text[prev_line_start:prev_line_end]
            stripped = prev_line.strip()
            if (
                prev_line_start >= prev_end
                and stripped.endswith(":")
                and len(stripped.split()) <= 6
                and not _COORD_PAIR.search(prev_line)
            ):
                phrase_start = prev_line_start
        name_phrase = text[phrase_start:m.start()].strip(" \t\n.,;:")
        citations.append(
            Citation(
                name_phrase=name_phrase,
                lon_ferro=_parse_degrees(m.group("lon")),
                lat_ferro=-_parse_degrees(m.group("lat")) if m.group("south") else _parse_degrees(m.group("lat")),
                south=bool(m.group("south")),
                char_offset=base_offset + m.start(),
            )
        )
        prev_end = m.end()
    return citations


def parse_sections(text: str) -> list[Section]:
    """Split the full source text into ordered Section records.

    Non-catalogue front matter (the "§ i" preface, and Books I/VIII which
    are theoretical prose with no coordinate catalogue) still becomes
    Section objects -- they simply carry zero citations, which Step 2's
    classifier treats as real data (their lead_text can still signal what
    kind of section follows).
    """
    matches = list(_SECTION_MARKER.finditer(text))
    sections: list[Section] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end]
        title_end = body.find("\n")
        title_line = body if title_end == -1 else body[:title_end]
        title_line = title_line.strip()

        citations = extract_citations(body, base_offset=m.end())
        lead_text = body[:citations[0].char_offset - m.end()].strip() if citations else body.strip()

        sections.append(
            Section(
                book=int(m.group(1)),
                map=m.group(2),
                section=int(m.group(3)),
                title_line=title_line,
                lead_text=lead_text,
                citations=citations,
            )
        )
    return sections


def load_sections(path: str) -> list[Section]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return parse_sections(text)
