"""Safe, deterministic boundary import parsing for property boundaries."""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import Any
from xml.etree import ElementTree

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
    if not filename.lower().endswith((".geojson", ".json", ".kml", ".kmz")):
        raise ValueError("only GeoJSON, KML, and KMZ files are supported")
    return filename


def boundary_import_format(filename: str) -> str:
    """Infer an accepted format solely from the validated filename suffix."""
    suffix = PurePath(validate_import_filename(filename)).suffix.lower()
    return {".geojson": "GEOJSON", ".json": "GEOJSON", ".kml": "KML", ".kmz": "KMZ"}[
        suffix
    ]


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


def _failed_kml(
    payload: bytes, declared_crs: str | None, code: str
) -> ParsedBoundaryImport:
    return ParsedBoundaryImport(
        None,
        hashlib.sha256(payload).hexdigest(),
        None,
        declared_crs,
        "EPSG:4326",
        None,
        [code],
        "FAILED",
        code,
    )


def _local_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _coordinates(value: str) -> list[list[float]]:
    result: list[list[float]] = []
    for tuple_text in value.split():
        parts = tuple_text.split(",")
        if len(parts) not in (2, 3):
            raise ValueError("INVALID_KML_COORDINATES")
        try:
            longitude, latitude = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise ValueError("INVALID_KML_COORDINATES") from exc
        if not all(math.isfinite(item) for item in (longitude, latitude)):
            raise ValueError("INVALID_KML_COORDINATES")
        result.append([longitude, latitude])
    if not result:
        raise ValueError("INVALID_KML_COORDINATES")
    return result


def _polygon_from_kml(root: ElementTree.Element) -> dict[str, Any]:
    polygons = [element for element in root.iter() if _local_name(element) == "Polygon"]
    if len(polygons) != 1:
        raise ValueError(
            "AMBIGUOUS_KML_POLYGONS" if polygons else "MISSING_KML_POLYGON"
        )
    rings: list[list[list[float]]] = []
    for boundary in polygons[0]:
        if _local_name(boundary) not in ("outerBoundaryIs", "innerBoundaryIs"):
            continue
        coordinates = [
            element
            for element in boundary.iter()
            if _local_name(element) == "coordinates"
        ]
        if len(coordinates) != 1 or not coordinates[0].text:
            raise ValueError("INVALID_KML_POLYGON")
        rings.append(_coordinates(coordinates[0].text))
    if not rings:
        raise ValueError("INVALID_KML_POLYGON")
    return {"type": "Polygon", "coordinates": rings}


def parse_kml_import(payload: bytes, declared_crs: str | None) -> ParsedBoundaryImport:
    """Parse one KML Polygon, preserving KML's WGS84 coordinate semantics."""
    if b"<!doctype" in payload.lower() or b"<!entity" in payload.lower():
        return _failed_kml(payload, declared_crs, "UNSAFE_KML_XML")
    if declared_crs and declared_crs.upper() not in {"EPSG:4326", "CRS:84"}:
        return _failed_kml(payload, declared_crs, "KML_CRS_CONFLICT")
    try:
        root = ElementTree.fromstring(payload)
        geometry = _polygon_from_kml(root)
        validated, _, geometry_checksum = validate_boundary(geometry, "EPSG:4326")
    except (ElementTree.ParseError, ValueError) as exc:
        code = str(exc)
        if not code.startswith(("INVALID_KML", "AMBIGUOUS_KML", "MISSING_KML")):
            code = "KML_BOUNDARY_VALIDATION_FAILED"
        return _failed_kml(payload, declared_crs, code)
    return ParsedBoundaryImport(
        validated,
        hashlib.sha256(payload).hexdigest(),
        geometry_checksum,
        "EPSG:4326",
        "EPSG:4326",
        "EPSG:4326",
        [],
        "NEEDS_REVIEW",
    )


def parse_kmz_import(payload: bytes, declared_crs: str | None) -> ParsedBoundaryImport:
    """Read exactly one bounded KML document from a KMZ without extraction."""
    try:
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()
            kml_entries = [
                item for item in entries if item.filename.lower().endswith(".kml")
            ]
            if len(kml_entries) != 1:
                return _failed_kml(
                    payload,
                    declared_crs,
                    "AMBIGUOUS_KMZ_KML" if kml_entries else "MISSING_KMZ_KML",
                )
            if any(item.flag_bits & 0x1 for item in entries):
                return _failed_kml(payload, declared_crs, "ENCRYPTED_KMZ_UNSUPPORTED")
            kml = kml_entries[0]
            if (
                kml.file_size > MAX_BOUNDARY_IMPORT_BYTES
                or sum(item.file_size for item in entries) > MAX_BOUNDARY_IMPORT_BYTES
            ):
                return _failed_kml(payload, declared_crs, "KMZ_UNCOMPRESSED_SIZE_LIMIT")
            kml_payload = archive.read(kml)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return _failed_kml(payload, declared_crs, "INVALID_KMZ")
    parsed = parse_kml_import(kml_payload, declared_crs)
    return ParsedBoundaryImport(
        parsed.geometry,
        hashlib.sha256(payload).hexdigest(),
        parsed.geometry_checksum,
        parsed.original_crs,
        parsed.detected_crs,
        parsed.target_crs,
        parsed.warnings,
        parsed.status,
        parsed.failure_code,
    )


def parse_boundary_import(
    payload: bytes, declared_crs: str | None, original_format: str
) -> ParsedBoundaryImport:
    if original_format == "GEOJSON":
        return parse_geojson_import(payload, declared_crs)
    if original_format == "KML":
        return parse_kml_import(payload, declared_crs)
    if original_format == "KMZ":
        return parse_kmz_import(payload, declared_crs)
    raise ValueError("unsupported boundary import format")
