"""Step 4: Ferro -> modern longitude conversion.

Ptolemy's latitude is already equator-relative (unchanged in the modern
convention); his longitude is measured east of the Ferro (El Hierro)
meridian rather than Greenwich. This is a raw, uncorrected modernization
of the coordinate frame only -- it does not attempt to correct for
Ptolemy's own (too-small) circumference figure, which skews his own
points worse the further they are from the Mediterranean. A plotted
position is "what Ptolemy's text claims", not ground truth.
"""
from __future__ import annotations

from .points import Point

FERRO_OFFSET_WEST_OF_GREENWICH = 17.6667


def to_modern(point: Point) -> None:
    point.lon_modern = point.lon_ferro - FERRO_OFFSET_WEST_OF_GREENWICH
    point.lat_modern = point.lat_ferro


def convert_points(points: list[Point]) -> None:
    for point in points:
        to_modern(point)
