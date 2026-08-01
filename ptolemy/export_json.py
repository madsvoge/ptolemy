"""Step 5: a Defaux-style declarative JSON export --
book -> chapters (map) -> sections -> points -- that a consumer can walk
and render without recomputing any classification or line-building logic.
"""
from __future__ import annotations

import json

from .lines import Line
from .parser import Section
from .points import Point

SOURCE = (
    "topostext.org work/209 -- Ptolemaeus, Geography (II-VI), translated/"
    "transliterated by Brady Kiesling from the Greek texts of Karl Nobbe "
    "(1843) and Karl Muller (1883)"
)


def _line_memberships(lines: list[Line]) -> dict[str, list[dict]]:
    memberships: dict[str, list[dict]] = {}
    for line in lines:
        for seq, point_id in enumerate(line.point_ids):
            memberships.setdefault(point_id, []).append({
                "line_id": line.id,
                "kind": line.kind,
                "feature_name": line.feature_name,
                "seq": seq,
                "closed": line.closed,
            })
    return memberships


def _point_json(point: Point, occurrence_name_phrase: str, memberships: dict[str, list[dict]]) -> dict:
    return {
        "id": point.id,
        "name": point.name,
        "name_phrase": occurrence_name_phrase,
        "name_variants": point.name_variants,
        "lon_ferro": round(point.lon_ferro, 4),
        "lat_ferro": round(point.lat_ferro, 4),
        "lon_modern": round(point.lon_modern, 4),
        "lat_modern": round(point.lat_modern, 4),
        "south": point.south,
        "tags": sorted(point.tags),
        "lines": memberships.get(point.id, []),
    }


def build_export(sections: list[Section], points: list[Point], resolved: dict[str, str],
                  occurrence_index: dict[tuple[str, int], Point], lines: list[Line]) -> dict:
    memberships = _line_memberships(lines)

    books: dict[int, dict] = {}
    for section in sections:
        book = books.setdefault(section.book, {"book": section.book, "chapters": {}})
        chapter = book["chapters"].setdefault(section.map, {"map": section.map, "sections": []})

        section_points = []
        for citation in section.citations:
            point = occurrence_index[(section.key, citation.char_offset)]
            section_points.append(_point_json(point, citation.name_phrase, memberships))

        chapter["sections"].append({
            "book": section.book,
            "map": section.map,
            "section": section.section,
            "key": section.key,
            "title": section.title_line,
            "lead_text": section.lead_text,
            "type": resolved[section.key],
            "points": section_points,
        })

    return {
        "source": SOURCE,
        "books": [
            {"book": b["book"], "chapters": list(b["chapters"].values())}
            for b in sorted(books.values(), key=lambda x: x["book"])
        ],
    }


def write_export(path: str, sections: list[Section], points: list[Point], resolved: dict[str, str],
                  occurrence_index: dict[tuple[str, int], Point], lines: list[Line]) -> None:
    data = build_export(sections, points, resolved, occurrence_index, lines)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
