"""Step 7: GeoPackage export -- one combined layer per feature kind
(coastline / river / mountain range / island), each row a MultiLineString
keyed by a shared feature id (all trails belonging to the same coastline
system, or the same named river/range/island, combined into one feature).
Every point -- connected or not -- also gets its own row in a full points
layer, so nothing plotted is invisible just because it never made it onto
a drawn line.
"""
from __future__ import annotations

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point as ShapelyPoint

from .lines import Line
from .points import Point

_KIND_TO_LAYER = {
    "coastline": "coastlines",
    "river": "rivers",
    "mountain": "mountains",
    "island": "islands",
}


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
                "book_map": data["book_map"],
                "feature_name": data["feature_name"],
                "closed": data["closed"],
                "num_trails": len(data["trails"]),
                "num_points": sum(len(t) for t in data["trails"]),
                "geometry": geom,
            })
        layers[layer_name] = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    return layers


def build_points_layer(points: list[Point], resolved: dict[str, str]) -> gpd.GeoDataFrame:
    rows = []
    for p in points:
        rows.append({
            "id": p.id,
            "name": p.name,
            "book_map": p.book_map,
            "tags": ",".join(sorted(p.tags)),
            "section_keys": ",".join(sorted({o.section_key for o in p.occurrences})),
            "section_types": ",".join(sorted({resolved[o.section_key] for o in p.occurrences})),
            "lon_ferro": p.lon_ferro,
            "lat_ferro": p.lat_ferro,
            "south": p.south,
            "geometry": ShapelyPoint(p.lon_modern, p.lat_modern),
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def write_geopackage(path: str, lines: list[Line], points: list[Point], resolved: dict[str, str]) -> None:
    point_by_id = {p.id: p for p in points}
    layers = build_line_layers(lines, point_by_id)
    layers["points"] = build_points_layer(points, resolved)
    for layer_name, gdf in layers.items():
        if gdf.empty:
            continue
        gdf.to_file(path, layer=layer_name, driver="GPKG")
