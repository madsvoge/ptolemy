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

from .classify import override_note
from .lines import Line
from .parser import Section
from .points import Point

_KIND_TO_LAYER = {
    "coastline": "coastlines",
    "river": "rivers",
    "mountain": "mountains",
    "island": "islands",
}

# One boolean column per tag, in addition to the comma-joined "tags"
# column -- much easier to filter/symbolize on in QGIS (categorized
# rendering, attribute-table checkboxes) than parsing a string column.
_ALL_TAGS = ["coast", "city", "river", "river_mouth", "harbor", "island", "mountain", "lake", "boundary"]


def _feature_id(line: Line) -> str:
    if line.kind == "coastline":
        return line.book_map
    return f"{line.book_map}-{line.feature_name}"


def _line_geometry(trail: list[Point]) -> LineString:
    return LineString([(p.lon_modern, p.lat_modern) for p in trail])


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
            "closed": False,
        })
        bucket["trails"].append([point_by_id[pid] for pid in line.point_ids])
        bucket["closed"] = bucket["closed"] or line.closed

    layers: dict[str, gpd.GeoDataFrame] = {}
    for layer_name, features in grouped.items():
        rows = []
        for feature_id, data in features.items():
            geom = MultiLineString([_line_geometry(trail) for trail in data["trails"]])
            rows.append({
                "feature_id": feature_id,
                "kind": data["kind"],
                "book_map": data["book_map"],
                "feature_name": data["feature_name"],
                "closed": data["closed"],
                "num_trails": len(data["trails"]),
                "num_points": sum(len(t) for t in data["trails"]),
                "point_names": " | ".join(p.name for trail in data["trails"] for p in trail),
                "geometry": geom,
            })
        layers[layer_name] = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    return layers


def build_points_layer(points: list[Point], resolved: dict[str, str]) -> gpd.GeoDataFrame:
    rows = []
    for p in points:
        row = {
            "id": p.id,
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
        }
        for tag in _ALL_TAGS:
            row[f"is_{tag}"] = tag in p.tags
        row["geometry"] = ShapelyPoint(p.lon_modern, p.lat_modern)
        rows.append(row)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def build_sections_table(sections: list[Section], resolved: dict[str, str]) -> pd.DataFrame:
    rows = []
    for s in sections:
        note = override_note(s.key)
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
                      sections: list[Section] | None = None) -> None:
    point_by_id = {p.id: p for p in points}
    layers = build_line_layers(lines, point_by_id)
    layers["points"] = build_points_layer(points, resolved)
    for layer_name, gdf in layers.items():
        if gdf.empty:
            continue
        gdf.to_file(path, layer=layer_name, driver="GPKG")

    if sections is not None:
        # A non-spatial attribute table (no geometry column) -- GeoPackage
        # supports these natively (an "attributes" table type), and QGIS
        # lists them alongside the spatial layers with a normal attribute
        # table view.
        build_sections_table(sections, resolved).to_csv(
            path.rsplit(".", 1)[0] + "_sections.csv", index=False
        )
        import sqlite3
        con = sqlite3.connect(path)
        try:
            df = build_sections_table(sections, resolved)
            df.to_sql("sections", con, if_exists="replace", index=False)
            con.execute(
                "INSERT OR REPLACE INTO gpkg_contents "
                "(table_name, data_type, identifier, description) VALUES (?, 'attributes', ?, ?)",
                ("sections", "sections", "Step 2 section classification, one row per §book.map.section"),
            )
            con.commit()
        finally:
            con.close()
