"""A small, git-committed, hand-edited layer of curator judgment that sits
on top of the pipeline's own text-driven output. Nothing in this module
infers or guesses anything from the source text -- every value here exists
because a human put it in one of the three CSVs under data/, and it's
loaded fresh and applied as an explicit, late pipeline step on every run.
The pipeline only ever *reads* these files; nothing it does writes to them.

Three files, three different jobs:
  - manual_section_overrides.csv: force a whole section's resolved type
    (classify.py's own text rules gave no usable signal, or the wrong one).
  - manual_point_overrides.csv: force a single point's tag, correct a
    single field (a transcription typo), or stitch it to another point.
  - manual_added_points.csv: a point with no citation of its own at all --
    exists only to close a shape for display (see Point.is_synthetic).

A point override is keyed by (section_key, char_offset): the exact
position of its coordinate in the raw source text, which is what
occurrence_index already uses internally. That position never moves
just because a future parser/dedup/classification change reshuffles
point IDs (P1234 is reassigned sequentially on every run and is *not*
a stable key) -- as long as the source text itself isn't edited, this
key is permanent. A synthetic added point instead uses its own `key`
column directly, prefixed "synthetic:", since it has no citation to
anchor to.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

from .lines import Line
from .points import Point

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SECTION_OVERRIDES_PATH = os.path.join(_DATA_DIR, "manual_section_overrides.csv")
POINT_OVERRIDES_PATH = os.path.join(_DATA_DIR, "manual_point_overrides.csv")
ADDED_POINTS_PATH = os.path.join(_DATA_DIR, "manual_added_points.csv")


def _read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if any(v.strip() for v in row.values() if v)]


def override_key_for_point(point: Point) -> str | None:
    """The stable key a CSV row references this point by. None only for a
    point that is neither a real citation nor a synthetic addition, which
    shouldn't happen in practice."""
    if point.id.startswith("synthetic:"):
        return point.id
    if not point.occurrences:
        return None
    o = point.occurrences[0]
    return f"{o.section_key}@{o.char_offset}"


# ---------------------------------------------------------------------
# Section overrides

def load_section_overrides(path: str = SECTION_OVERRIDES_PATH) -> dict[str, tuple[str, str]]:
    """{section_key: (classify, note)}."""
    overrides: dict[str, tuple[str, str]] = {}
    for row in _read_csv(path):
        key = (row.get("section_key") or "").strip()
        classify = (row.get("classify") or "").strip()
        if key and classify:
            overrides[key] = (classify, (row.get("note") or "").strip())
    return overrides


def apply_section_overrides(resolved: dict[str, str], path: str = SECTION_OVERRIDES_PATH) -> dict[str, str]:
    """Force specific sections' resolved type, in place. Applied *after*
    classify_sections' own inheritance chain has already run, and doesn't
    feed back into it: a section right after an overridden one, with no
    signal of its own, should still inherit whatever type the text itself
    actually carries (confirmed needed for §7.1.96, which must continue
    §7.1.95's real coastal walk rather than inheriting its island
    override) -- an override corrects that one section's own type, not
    the whole downstream chain."""
    for key, (classify, _note) in load_section_overrides(path).items():
        if key in resolved:
            resolved[key] = classify
    return resolved


# ---------------------------------------------------------------------
# Point overrides

@dataclass
class PointOverride:
    key: str
    classify: str | None
    stitch_to: str | None
    correction_field: str | None
    correction_value: str | None
    note: str


_CORRECTABLE_FIELDS = {"lon_ferro", "lat_ferro"}


def load_point_overrides(path: str = POINT_OVERRIDES_PATH) -> list[PointOverride]:
    out = []
    for row in _read_csv(path):
        section_key = (row.get("section_key") or "").strip()
        char_offset = (row.get("char_offset") or "").strip()
        if not section_key or not char_offset:
            continue
        out.append(PointOverride(
            key=f"{section_key}@{char_offset}",
            classify=(row.get("classify") or "").strip() or None,
            stitch_to=(row.get("stitch_to") or "").strip() or None,
            correction_field=(row.get("correction_field") or "").strip() or None,
            correction_value=(row.get("correction_value") or "").strip() or None,
            note=(row.get("note") or "").strip(),
        ))
    return out


def apply_point_overrides(points: list[Point], path: str = POINT_OVERRIDES_PATH) -> list[str]:
    """Apply classify/correction overrides in place. Returns a list of
    warning strings for any row whose key didn't match a live point (a
    stale key, or a typo) -- loud instead of silently doing nothing."""
    by_key = {}
    for p in points:
        key = override_key_for_point(p)
        if key:
            by_key.setdefault(key, p)

    warnings = []
    for ov in load_point_overrides(path):
        point = by_key.get(ov.key)
        if point is None:
            warnings.append(f"manual_point_overrides: no point found for {ov.key} ({ov.note})")
            continue
        if ov.classify:
            point.tags = {ov.classify}
        if ov.correction_field:
            if ov.correction_field not in _CORRECTABLE_FIELDS:
                warnings.append(
                    f"manual_point_overrides: unsupported correction_field "
                    f"{ov.correction_field!r} for {ov.key} (allowed: {sorted(_CORRECTABLE_FIELDS)})"
                )
            elif ov.correction_value is None:
                warnings.append(f"manual_point_overrides: correction_field set with no correction_value for {ov.key}")
            else:
                setattr(point, ov.correction_field, float(ov.correction_value))
    return warnings


# ---------------------------------------------------------------------
# Added (synthetic) points

@dataclass
class AddedPointRow:
    key: str
    book_map: str
    name: str
    lon_ferro: float
    lat_ferro: float
    tags: set[str]
    stitch_to: str | None
    note: str


def load_added_points(path: str = ADDED_POINTS_PATH) -> list[AddedPointRow]:
    out = []
    for row in _read_csv(path):
        key = (row.get("key") or "").strip()
        if not key:
            continue
        tags = {t.strip() for t in (row.get("tags") or "").split("|") if t.strip()}
        out.append(AddedPointRow(
            key=key,
            book_map=(row.get("book_map") or "").strip(),
            name=(row.get("name") or "").strip(),
            lon_ferro=float(row["lon_ferro"]),
            lat_ferro=float(row["lat_ferro"]),
            tags=tags or {"coast"},
            stitch_to=(row.get("stitch_to") or "").strip() or None,
            note=(row.get("note") or "").strip(),
        ))
    return out


def build_added_points(path: str = ADDED_POINTS_PATH) -> list[Point]:
    """Point objects for every row in manual_added_points.csv, flagged
    is_synthetic so nothing downstream can mistake one for something
    Ptolemy's text actually says."""
    points = []
    for row in load_added_points(path):
        points.append(Point(
            id=f"synthetic:{row.key}",
            lon_ferro=row.lon_ferro,
            lat_ferro=row.lat_ferro,
            book_map=row.book_map,
            tags=set(row.tags),
            is_synthetic=True,
            manual_name=row.name,
        ))
    return points


# ---------------------------------------------------------------------
# Manual stitches -- one confirmed connector Line per stitch_to reference,
# drawn from *either* file (a real point can stitch to another real point,
# or to a synthetic one added just to close a shape).

def apply_manual_stitches(points: list[Point],
                           point_overrides: list[PointOverride],
                           added_points: list[AddedPointRow]) -> tuple[list[Line], list[str]]:
    by_key = {}
    for p in points:
        key = override_key_for_point(p)
        if key:
            by_key.setdefault(key, p)

    pairs: list[tuple[str, str, str]] = []  # (from_key, to_key, note)
    for ov in point_overrides:
        if ov.stitch_to:
            pairs.append((ov.key, ov.stitch_to, ov.note))
    for row in added_points:
        if row.stitch_to:
            pairs.append((f"synthetic:{row.key}", row.stitch_to, row.note))

    lines: list[Line] = []
    warnings: list[str] = []
    for i, (from_key, to_key, note) in enumerate(pairs, start=1):
        a, b = by_key.get(from_key), by_key.get(to_key)
        if a is None or b is None:
            missing = from_key if a is None else to_key
            warnings.append(f"manual stitch: no point found for {missing} ({note})")
            continue
        lines.append(Line(
            id=f"manual-stitch-{i}",
            kind="stitch",
            book_map=a.book_map,
            feature_name=None,
            point_ids=[a.id, b.id],
            closed=False,
        ))
    return lines, warnings
