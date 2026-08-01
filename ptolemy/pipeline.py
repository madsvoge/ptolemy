"""End-to-end pipeline: topostext raw text -> parsed sections -> canonical
points -> classified/tagged/converted -> drawn lines -> JSON + GeoPackage
+ a smoke-test PNG. Run as `python -m ptolemy.pipeline`.

A late step applies data/manual_*_overrides.csv -- committed, hand-edited
curator judgment (see ptolemy/overrides.py) -- on top of the text-driven
output. Every run re-reads these files fresh; nothing here ever writes to
them.
"""
from __future__ import annotations

import argparse
import os

from .classify import classify_sections
from .coords import convert_points
from .export_gpkg import write_geopackage
from .export_json import write_export
from .lines import build_all_lines
from .overrides import (
    apply_point_overrides,
    apply_section_overrides,
    apply_manual_stitches,
    build_added_points,
    load_added_points,
    load_point_overrides,
    load_section_overrides,
)
from .parser import load_sections
from .points import build_occurrence_index, dedup_points
from .stitch import suggest_stitches
from .tag import propagate_bare_connector_tags, propagate_river_context, tag_points
from .visualize import render_map


def run(source_path: str, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)

    sections = load_sections(source_path)
    resolved = classify_sections(sections)
    apply_section_overrides(resolved)

    points = dedup_points(sections)
    tag_points(points, resolved)
    propagate_river_context(sections, points)
    propagate_bare_connector_tags(sections, points)

    warnings = apply_point_overrides(points)
    points += build_added_points()

    convert_points(points)
    occurrence_index = build_occurrence_index(points)
    lines = build_all_lines(sections, points, resolved, occurrence_index)

    point_overrides = load_point_overrides()
    added_point_rows = load_added_points()
    stitch_lines, stitch_warnings = apply_manual_stitches(points, point_overrides, added_point_rows)
    lines += stitch_lines
    warnings += stitch_warnings
    for w in warnings:
        print(f"WARNING: {w}")

    # Advisory only: candidate connections between loose trail ends, close
    # enough to be worth a human looking at. Never fed back into `lines`
    # or the GeoPackage export -- just an overlay on the smoke-test map so
    # a reviewer can judge each one before it's ever treated as real (a
    # confirmed one graduates into manual_point_overrides.csv's own
    # stitch_to column, which produces a real "stitch"-kind Line above).
    stitches = suggest_stitches(lines, points)

    section_notes = {key: note for key, (_classify, note) in load_section_overrides().items()}

    write_export(
        os.path.join(out_dir, "ptolemy.json"),
        sections, points, resolved, occurrence_index, lines,
    )
    write_geopackage(
        os.path.join(out_dir, "ptolemy.gpkg"),
        lines, points, resolved, sections, section_notes,
    )
    render_map(points, lines, os.path.join(out_dir, "ptolemy_map.png"), stitches=stitches)
    for label, book_map in (("ireland", "2.2"), ("britain", "2.3"), ("italy", "3.1")):
        render_map(points, lines, os.path.join(out_dir, f"ptolemy_{label}.png"),
                   title=f"Spot check: {label} ({book_map})", book_map_filter=book_map, stitches=stitches)

    return {
        "sections": sections,
        "resolved": resolved,
        "points": points,
        "lines": lines,
        "stitches": stitches,
        "warnings": warnings,
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
