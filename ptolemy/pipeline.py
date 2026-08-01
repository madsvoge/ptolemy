"""End-to-end pipeline: topostext raw text -> parsed sections -> canonical
points -> classified/tagged/converted -> drawn lines -> JSON + GeoPackage
+ a smoke-test PNG. Run as `python -m ptolemy.pipeline`.
"""
from __future__ import annotations

import argparse
import os

from .classify import classify_sections
from .coords import convert_points
from .export_gpkg import write_geopackage
from .export_json import write_export
from .lines import build_all_lines
from .parser import load_sections
from .points import build_occurrence_index, dedup_points
from .tag import tag_points
from .visualize import render_map


def run(source_path: str, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)

    sections = load_sections(source_path)
    resolved = classify_sections(sections)
    points = dedup_points(sections)
    tag_points(points, resolved)
    convert_points(points)
    occurrence_index = build_occurrence_index(points)
    lines = build_all_lines(sections, points, resolved, occurrence_index)

    write_export(
        os.path.join(out_dir, "ptolemy.json"),
        sections, points, resolved, occurrence_index, lines,
    )
    write_geopackage(
        os.path.join(out_dir, "ptolemy.gpkg"),
        lines, points, resolved,
    )
    render_map(points, lines, os.path.join(out_dir, "ptolemy_map.png"))
    for label, book_map in (("ireland", "2.2"), ("britain", "2.3"), ("italy", "3.1")):
        render_map(points, lines, os.path.join(out_dir, f"ptolemy_{label}.png"),
                   title=f"Spot check: {label} ({book_map})", book_map_filter=book_map)

    return {
        "sections": sections,
        "resolved": resolved,
        "points": points,
        "lines": lines,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/raw/ptolemy_nobbe.txt")
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    result = run(args.source, args.out)
    print(f"sections: {len(result['sections'])}")
    print(f"points: {len(result['points'])}")
    print(f"lines: {len(result['lines'])}")


if __name__ == "__main__":
    main()
