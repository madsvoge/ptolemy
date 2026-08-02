"""Step 7: GeoPackage export -- one combined layer per feature kind
(coastline / river / mountain range / island), each row a MultiLineString
keyed by a shared feature id (all trails belonging to the same coastline
system, or the same named river/range/island, combined into one feature).
Every point -- connected or not -- also gets its own row in a full points
layer, so nothing plotted is invisible just because it never made it onto
a drawn line. A non-spatial `sections` table carries Step 2's own
classification per §book.map.section, for a section-by-section review
independent of any geometry.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point as ShapelyPoint

from .lines import Line
from .overrides import override_key_for_point
from .parser import Section
from .points import Point

_KIND_TO_LAYER = {
    "coastline": "coastlines",
    "river": "rivers",
    "mountain": "mountains",
    "island": "islands",
    "stitch": "manual_stitches",
}

# One boolean column per tag, in addition to the comma-joined "tags"
# column -- much easier to filter/symbolize on in QGIS (categorized
# rendering, attribute-table checkboxes) than parsing a string column.
_ALL_TAGS = ["coast", "city", "river", "river_mouth", "harbor", "island", "mountain", "lake", "boundary"]


def _feature_id(line: Line) -> str:
    if line.kind == "coastline":
        return line.book_map
    if line.kind == "stitch":
        return line.id
    return f"{line.book_map}-{line.feature_name}"


def _line_geometry(trail: list[Point], closed: bool) -> LineString:
    coords = [(p.lon_modern, p.lat_modern) for p in trail]
    # `closed` is metadata from the line-builder (the trail's own two ends
    # are close enough to treat as a loop) -- the geometry itself has to
    # actually repeat the first point at the end for that to be true,
    # or QGIS renders exactly the same broken-looking seam this was
    # confirmed to produce (NE Ireland: the real closing edge was never
    # part of the drawn geometry at all, despite "closed" saying it was).
    if closed and len(coords) > 2:
        coords = coords + [coords[0]]
    return LineString(coords)


def build_line_layers(lines: list[Line], point_by_id: dict[str, Point]) -> dict[str, gpd.GeoDataFrame]:
    grouped: dict[str, dict[str, list]] = {}
    for line in lines:
        layer_name = _KIND_TO_LAYER[line.kind]
        feature_id = _feature_id(line)
        bucket = grouped.setdefault(layer_name, {}).setdefault(feature_id, {
            "kind": line.kind,
            "book_map": line.book_map,
            "feature_name": line.feature_name,
            "trails": [],
        })
        bucket["trails"].append(([point_by_id[pid] for pid in line.point_ids], line.closed))

    layers: dict[str, gpd.GeoDataFrame] = {}
    for layer_name, features in grouped.items():
        rows = []
        for feature_id, data in features.items():
            geom = MultiLineString([_line_geometry(trail, trail_closed) for trail, trail_closed in data["trails"]])
            rows.append({
                "feature_id": feature_id,
                "kind": data["kind"],
                "book_map": data["book_map"],
                "feature_name": data["feature_name"],
                # True only if *every* trail bundled into this feature is
                # its own closed ring -- a book.map can have more than one
                # disjoint coastline run (confirmed §3.10, §3.12, §4.5: one
                # closed loop plus one genuinely separate short open
                # fragment that never found a stitch partner), and an OR
                # here would call the whole feature "closed" even though
                # part of it visibly isn't.
                "closed": all(trail_closed for _t, trail_closed in data["trails"]),
                "num_trails": len(data["trails"]),
                "num_points": sum(len(t) for t, _closed in data["trails"]),
                "point_names": " | ".join(p.name for t, _closed in data["trails"] for p in t),
                "geometry": geom,
            })
        layers[layer_name] = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    return layers


def _point_row(p: Point, resolved: dict[str, str]) -> dict:
    row = {
        "id": p.id,
        # p.id is a plain "P<n>" sequence number assigned in document order
        # by dedup_points -- it shifts if any citation earlier in the text
        # is added, removed, or merges differently on a future run, so it
        # can't be used to track "the same point" across regenerations
        # (e.g. to cross-reference a QA note written against an older
        # export). stable_id doesn't have that problem: it's the point's
        # first citation's own (section_key, char_offset) -- or, for a
        # manually added point with no citation of its own, its
        # committed CSV key (see overrides.override_key_for_point) --
        # neither of which moves just because an unrelated point elsewhere
        # in the document was added or removed.
        "stable_id": override_key_for_point(p),
        "name": p.name,
        "name_variants": " | ".join(p.name_variants),
        "book": int(p.book_map.split(".")[0]),
        "map": p.book_map.split(".", 1)[1],
        "book_map": p.book_map,
        "tags": ",".join(sorted(p.tags)),
        "num_occurrences": len(p.occurrences),
        "section_keys": ",".join(sorted({o.section_key for o in p.occurrences})),
        "section_types": ",".join(sorted({resolved[o.section_key] for o in p.occurrences})),
        "lon_ferro": round(p.lon_ferro, 4),
        "lat_ferro": round(p.lat_ferro, 4),
        "south": p.south,
        "is_synthetic": p.is_synthetic,
    }
    for tag in _ALL_TAGS:
        row[f"is_{tag}"] = tag in p.tags
    row["geometry"] = ShapelyPoint(p.lon_modern, p.lat_modern)
    return row


def build_points_layer(points: list[Point], resolved: dict[str, str]) -> gpd.GeoDataFrame:
    rows = [_point_row(p, resolved) for p in points]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def build_points_layers_by_tag(points: list[Point], resolved: dict[str, str]) -> dict[str, gpd.GeoDataFrame]:
    """One layer per tag (points_coast, points_city, ...), each holding
    only the points that carry that tag. A single-value-per-layer
    membership test (is this point in the layer or not) works with plain
    GIS layer visibility/symbology, where the combined "points" layer's
    own multi-value "tags" column (comma-joined, since a point can be
    both e.g. "river_mouth" and "coast") does not -- most GIS programs
    can't style or filter on a column holding several values at once.
    Points with no tags at all (shouldn't happen, but not enforced
    upstream) simply appear in no per-tag layer; they're still in the
    combined "points" layer."""
    layers: dict[str, gpd.GeoDataFrame] = {}
    for tag in _ALL_TAGS:
        rows = [_point_row(p, resolved) for p in points if tag in p.tags]
        if not rows:
            continue
        layers[f"points_{tag}"] = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    return layers


def build_sections_table(sections: list[Section], resolved: dict[str, str],
                          section_notes: dict[str, str] | None = None) -> pd.DataFrame:
    section_notes = section_notes or {}
    rows = []
    for s in sections:
        note = section_notes.get(s.key)
        rows.append({
            "key": s.key,
            "book": s.book,
            "map": s.map,
            "section": s.section,
            "book_map": s.book_map,
            "type": resolved[s.key],
            "title": s.title_line,
            "lead_text": s.lead_text,
            "num_points": len(s.citations),
            "point_names": " | ".join(c.name_phrase for c in s.citations),
            "manual_override": note is not None,
            "override_note": note or "",
        })
    return pd.DataFrame(rows)


def write_geopackage(path: str, lines: list[Line], points: list[Point], resolved: dict[str, str],
                      sections: list[Section] | None = None,
                      section_notes: dict[str, str] | None = None) -> None:
    point_by_id = {p.id: p for p in points}
    layers = build_line_layers(lines, point_by_id)
    layers["points"] = build_points_layer(points, resolved)
    layers.update(build_points_layers_by_tag(points, resolved))
    for layer_name, gdf in layers.items():
        if gdf.empty:
            continue
        gdf.to_file(path, layer=layer_name, driver="GPKG")

    if sections is not None:
        # A non-spatial attribute table (no geometry column) -- GeoPackage
        # supports these natively (an "attributes" table type), and QGIS
        # lists them alongside the spatial layers with a normal attribute
        # table view.
        build_sections_table(sections, resolved, section_notes).to_csv(
            path.rsplit(".", 1)[0] + "_sections.csv", index=False
        )
        import sqlite3
        con = sqlite3.connect(path)
        try:
            df = build_sections_table(sections, resolved, section_notes)
            df.to_sql("sections", con, if_exists="replace", index=False)
            con.execute(
                "INSERT OR REPLACE INTO gpkg_contents "
                "(table_name, data_type, identifier, description) VALUES (?, 'attributes', ?, ?)",
                ("sections", "sections", "Step 2 section classification, one row per §book.map.section"),
            )
            con.commit()
        finally:
            con.close()
