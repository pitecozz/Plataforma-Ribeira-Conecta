"""Strict, non-repairing property-boundary validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from pyproj import Geod
from shapely.geometry import shape
from shapely.validation import explain_validity


def validate_boundary(
    geometry: dict[str, Any], crs: str
) -> tuple[dict[str, Any], str, str]:
    if crs.upper() not in {"EPSG:4326", "CRS:84"}:
        raise ValueError("unsupported property CRS; only EPSG:4326 is accepted")
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("property geometry must be Polygon or MultiPolygon")
    polygons = geometry.get("coordinates")
    rings = (
        polygons
        if geometry.get("type") == "Polygon"
        else [ring for polygon in polygons or [] for ring in polygon]
    )
    if (
        not isinstance(rings, Sequence)
        or not rings
        or any(
            not isinstance(ring, Sequence) or len(ring) < 4 or ring[0] != ring[-1]
            for ring in rings
        )
    ):
        raise ValueError("property polygon rings must be explicitly closed")
    try:
        parsed = shape(geometry)
    except Exception as exc:
        raise ValueError("property geometry could not be parsed") from exc
    if parsed.is_empty or not parsed.is_valid:
        raise ValueError(f"property geometry is invalid: {explain_validity(parsed)}")
    min_x, min_y, max_x, max_y = parsed.bounds
    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
        raise ValueError("property geometry bounds are outside EPSG:4326")
    square_metres, _ = Geod(ellps="WGS84").geometry_area_perimeter(parsed)
    if Decimal(str(abs(square_metres))) <= 0:
        raise ValueError("property geometry area must be greater than zero")
    canonical = json.dumps(geometry, sort_keys=True, separators=(",", ":"))
    return (
        geometry,
        format(abs(Decimal(str(square_metres))) / Decimal("10000"), "f"),
        hashlib.sha256(canonical.encode()).hexdigest(),
    )
