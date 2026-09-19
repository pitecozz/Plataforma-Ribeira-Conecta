"""Safe, deterministic GeoJSON import parsing for property boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from .boundaries import validate_boundary


MAX_BOUNDARY_IMPORT_BYTES = 1_000_000


@dataclass(frozen=True)
class ParsedBoundaryImport:
    geometry: dict[str, Any] | None
    file_sha256: str
    geometry_checksum: str | None
    original_crs: str | None
    detected_crs: str | None
    target_crs: str | None
    warnings: list[str]
    status: str
    failure_code: str | None = None


def validate_import_filename(filename: str) -> str:
    if not filename or len(filename) > 255 or PurePath(filename).name != filename:
        raise ValueError("invalid boundary import filename")
    if not filename.lower().endswith((".geojson", ".json")):
        raise ValueError("only GeoJSON files are supported")
    return filename


def parse_geojson_import(
    payload: bytes, declared_crs: str | None
) -> ParsedBoundaryImport:
    """Parse exactly one polygonal GeoJSON boundary; never repair or merge."""
    file_sha256 = hashlib.sha256(payload).hexdigest()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ParsedBoundaryImport(
            None,
            file_sha256,
            None,
            declared_crs,
            None,
            None,
            [],
            "FAILED",
            "INVALID_GEOJSON",
        )
    if not isinstance(document, dict):
        return ParsedBoundaryImport(
            None,
            file_sha256,
            None,
            declared_crs,
            None,
            None,
            [],
            "FAILED",
            "INVALID_GEOJSON",
        )
    geometry: Any
    kind = document.get("type")
    if kind == "Feature":
        geometry = document.get("geometry")
    elif kind == "FeatureCollection":
        features = document.get("features")
        if (
            not isinstance(features, list)
            or len(features) != 1
            or not isinstance(features[0], dict)
        ):
            return ParsedBoundaryImport(
                None,
                file_sha256,
                None,
                declared_crs,
                None,
                None,
                ["FEATURE_COLLECTION_AMBIGUOUS"],
                "FAILED",
                "AMBIGUOUS_FEATURE_COLLECTION",
            )
        geometry = features[0].get("geometry")
    else:
        geometry = document
    if not isinstance(geometry, dict):
        return ParsedBoundaryImport(
            None,
            file_sha256,
            None,
            declared_crs,
            None,
            None,
            [],
            "FAILED",
            "MISSING_GEOMETRY",
        )
    if not declared_crs:
        # A geometry column with SRID 4326 would itself be an unproven CRS
        # assertion. Preserve the original file, but do not persist geometry
        # coordinates as platform geometry until a reviewer supplies evidence.
        return ParsedBoundaryImport(
            None,
            file_sha256,
            None,
            None,
            None,
            None,
            ["CRS_UNKNOWN"],
            "NEEDS_REVIEW",
            "CRS_UNKNOWN",
        )
    try:
        validated, _, geometry_checksum = validate_boundary(geometry, declared_crs)
    except ValueError as exc:
        return ParsedBoundaryImport(
            # Failed validation and unsupported CRS are evidence about the
            # uploaded file, not a licensed platform geometry.  Do not tag
            # their coordinates with SRID 4326 merely to retain a preview.
            None,
            file_sha256,
            None,
            declared_crs,
            declared_crs,
            None,
            [str(exc)],
            "FAILED",
            "BOUNDARY_VALIDATION_FAILED",
        )
    return ParsedBoundaryImport(
        validated,
        file_sha256,
        geometry_checksum,
        declared_crs,
        declared_crs,
        "EPSG:4326",
        [],
        "NEEDS_REVIEW",
    )
