"""Collapse the raw, ordered citation stream from parser.py into canonical
Points: one per real place, even where topostext cites the same coordinate
more than once (a boundary/orientation restatement, or the lead sentence of
a new paragraph restating the previous paragraph's last point).

This has to run before any line-building: an unresolved duplicate point is
exactly what turns a clean coastal walk into a false loop or junction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parser import Section

DEDUP_TOLERANCE_DEG = 0.05

# Trimmed from the *front* and *back* of a citation's raw name_phrase to
# recover the actual place name out of a restatement/lead-in sentence
# ("from the Boreum promontory which is in" -> "Boreum promontory").
# Deliberately small and generic -- this is a stopword trim, not a per-name
# exception list. Words that carry real classification meaning (mouth,
# source, promontory, island, mountain, ...) are never in this set, so a
# real descriptive name like "mouth of the Vidua river" passes through
# untouched (its first token "mouth" isn't a stopword).
_LEADING_STOPWORDS = {
    "from", "the", "which", "is", "in", "at", "near", "next", "to", "this",
    "toward", "towards", "likewise", "again", "then", "above", "below",
    "whom", "are", "these", "and", "after",
}
_TRAILING_STOPWORDS = {
    "which", "is", "in", "at", "of", "likewise", "toward", "towards",
    "the", "near", "and",
}

# Ptolemy routinely folds a tribe's or nome's capital into a much longer
# sentence naming the tribe/region itself first ("Further east than the
# Remi are, more northerly, the Treveri and their city Augusta Treverum",
# "The Atribati occupy the sea coast...their city being Nemetacum") --
# recognized here by the same marker tag.py's own point-tagging uses to
# spot this idiom (see tag.py's _TRIBAL_CITY_RE/_TRIBAL_CITY_BARE_RE,
# which import these two regexes from here rather than duplicating them).
# Defined in points.py, not tag.py, because trim_name needs them too:
# neither the leading- nor trailing-stopword trim below reaches into the
# *middle* of a sentence, so without this a point like that ended up
# named after its entire tribal description instead of just "Augusta
# Treverum" (confirmed §2.9.7).
TRIBAL_CITY_RE = re.compile(
    r"\b(?:city|town)\s+is\b|\b(?:cities|towns)\s+is\b"
    r"|\bwhose\s+(?:city|town)\b|\btheir\s+(?:city|town)\b"
    r"|\b(?:city|town)\s+being\b",
    re.I,
)
TRIBAL_CITY_BARE_RE = re.compile(r"\bthe\s+towns?\s+[A-Z]")
# The place's own real name is always the trailing run of capitalized
# words -- whatever tribal/nome description precedes it in the sentence
# is never itself capitalized-word-for-word all the way to the very end
# (confirmed against every "their city"/"whose city"/"the town" citation
# in this text, including asides sitting between the marker and the name
# itself, e.g. "whose city on the eastern bank of the Sequana River is
# Ratomagus" -- "Sequana River" is capitalized too, but isn't at the tail,
# so this still isolates just "Ratomagus").
_TRAILING_PROPER_NOUN_RE = re.compile(r"[A-Z][\w-]*(?:\s+[A-Z][\w-]*)*$")


def trim_name(phrase: str) -> str:
    phrase = phrase.strip()
    # Ptolemy's own list-intro sentences ("The following are the inland
    # towns:", "Named mountains in Baetica are:") consistently end with a
    # colon right before the real enumeration starts -- so the text after
    # the last colon is the name, whatever the intro reads like.
    if ":" in phrase:
        phrase = phrase.rsplit(":", 1)[1]
    if TRIBAL_CITY_RE.search(phrase) or TRIBAL_CITY_BARE_RE.search(phrase):
        m = _TRAILING_PROPER_NOUN_RE.search(phrase.strip(" ,:;."))
        if m:
            return m.group(0)
    words = phrase.strip().strip(":,;.").split()
    while words and words[0].strip(",:;").lower() in _LEADING_STOPWORDS:
        words.pop(0)
    while words and words[-1].strip(",:;").lower() in _TRAILING_STOPWORDS:
        words.pop()
    trimmed = " ".join(words).strip(" ,:;")
    return trimmed or phrase.strip()


@dataclass
class Occurrence:
    section_key: str
    book_map: str
    name_phrase: str
    char_offset: int
    south: bool


@dataclass
class Point:
    id: str
    lon_ferro: float
    lat_ferro: float
    book_map: str  # the book.map this point belongs to (its dedup/graph scope)
    occurrences: list[Occurrence] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    lon_modern: float | None = None
    lat_modern: float | None = None
    # A point manually added via data/manual_added_points.csv (see
    # ptolemy/overrides.py) has no citation of its own -- it exists only to
    # close a shape for display, not because Ptolemy's text says anything
    # at that coordinate. is_synthetic keeps that fact visible all the way
    # through to the GeoPackage, and manual_name stands in for the `name`
    # property below, which otherwise has nothing to derive a name from.
    is_synthetic: bool = False
    manual_name: str | None = None

    @property
    def name(self) -> str:
        if not self.occurrences:
            return self.manual_name or self.id
        candidates = [trim_name(o.name_phrase) for o in self.occurrences]
        return min(candidates, key=len)

    @property
    def name_variants(self) -> list[str]:
        if not self.occurrences:
            return [self.manual_name] if self.manual_name else []
        seen, out = set(), []
        for o in self.occurrences:
            if o.name_phrase not in seen:
                seen.add(o.name_phrase)
                out.append(o.name_phrase)
        return out

    @property
    def first_char_offset(self) -> int:
        return self.occurrences[0].char_offset if self.occurrences else -1

    @property
    def south(self) -> bool:
        return any(o.south for o in self.occurrences)


def _close(a: Point, lon: float, lat: float, tol: float) -> bool:
    return abs(a.lon_ferro - lon) <= tol and abs(a.lat_ferro - lat) <= tol


# Sentence-initial capitals (a phrase almost always starts a sentence or
# clause) that must not count as a "shared name" between two phrases --
# without this filter, two totally unrelated citations that both merely
# *start* with "The"/"And"/... would look like a name match.
_PROPER_NOUN_STOPWORDS = {
    "the", "a", "an", "and", "of", "in", "on", "at", "to", "from", "which",
    "is", "below", "above", "after", "between", "near", "next", "this",
    "toward", "towards", "then", "again", "first", "second", "third",
}


def _proper_nouns(phrase: str) -> set[str]:
    return {
        w.lower() for w in re.findall(r"[A-Z][a-zA-Z]*", phrase)
        if w.lower() not in _PROPER_NOUN_STOPWORDS
    }


def _same_place(point: Point, phrase: str) -> bool:
    # Two citations at the same coordinate are only the same real place if
    # they also share a proper noun -- coordinates alone aren't enough.
    # Confirmed on this text: "Lekton promontory" (Troas, mainland) and
    # "Methymna" (a city on Lesbos, a separate island) cite the *exact*
    # same coordinate (55d25' . 40d25') by coincidence, and coordinate-only
    # matching silently welded Lesbos's own coastline onto the Anatolian
    # mainland's. A phrase with no proper noun of its own (a bare "and", a
    # generic "the source of the river") never matches anything this way --
    # safer to leave it as its own point than to guess.
    new_names = _proper_nouns(phrase)
    if not new_names:
        return False
    return any(new_names & _proper_nouns(o.name_phrase) for o in point.occurrences)


def dedup_points(sections: list[Section], tol: float = DEDUP_TOLERANCE_DEG) -> list[Point]:
    """Cluster every citation, across all sections, into canonical Points.

    Clustering is scoped to a single book.map: Ptolemy's own catalogue never
    reuses a coordinate across two different regional maps, and scoping this
    way keeps the O(n^2) proximity scan cheap and keeps two genuinely
    different regions from ever merging just because they're geographically
    close (the same guard the line-building step needs later).
    """
    by_book_map: dict[str, list[Point]] = {}
    next_id = 0
    for section in sections:
        for citation in section.citations:
            bucket = by_book_map.setdefault(section.book_map, [])
            match = next(
                (p for p in bucket
                 if _close(p, citation.lon_ferro, citation.lat_ferro, tol)
                 and _same_place(p, citation.name_phrase)),
                None,
            )
            occ = Occurrence(
                section_key=section.key,
                book_map=section.book_map,
                name_phrase=citation.name_phrase,
                char_offset=citation.char_offset,
                south=citation.south,
            )
            if match is None:
                next_id += 1
                match = Point(
                    id=f"P{next_id}",
                    lon_ferro=citation.lon_ferro,
                    lat_ferro=citation.lat_ferro,
                    book_map=section.book_map,
                )
                bucket.append(match)
            match.occurrences.append(occ)

    points = [p for bucket in by_book_map.values() for p in bucket]
    points.sort(key=lambda p: p.first_char_offset)
    return points


def build_occurrence_index(points: list[Point]) -> dict[tuple[str, int], Point]:
    """(section_key, citation.char_offset) -> the canonical Point it dedups to."""
    index: dict[tuple[str, int], Point] = {}
    for p in points:
        for o in p.occurrences:
            index[(o.section_key, o.char_offset)] = p
    return index
