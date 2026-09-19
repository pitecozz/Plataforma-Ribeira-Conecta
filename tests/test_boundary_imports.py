"""GeoJSON-only boundary import parsing uses explicit synthetic_test_data."""

from __future__ import annotations

import hashlib
import json
import unittest

from ribeira_platform.boundary_imports import (
    MAX_BOUNDARY_IMPORT_BYTES,
    parse_geojson_import,
    validate_import_filename,
)


POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-47.0, -24.0],
            [-46.99, -24.0],
            [-46.99, -24.01],
            [-47.0, -24.01],
            [-47.0, -24.0],
        ]
    ],
}
MULTIPOLYGON = {"type": "MultiPolygon", "coordinates": [POLYGON["coordinates"]]}


class BoundaryImportParsingTests(unittest.TestCase):
    def payload(self, value: object) -> bytes:
        return json.dumps(value, separators=(",", ":")).encode("utf-8")

    def test_polygon_and_feature_are_accepted_with_distinct_hashes(self) -> None:
        payload = self.payload(
            {
                "type": "Feature",
                "properties": {"synthetic_test_data": True},
                "geometry": POLYGON,
            }
        )
        parsed = parse_geojson_import(payload, "EPSG:4326")
        self.assertEqual(parsed.status, "NEEDS_REVIEW")
        self.assertEqual(parsed.geometry, POLYGON)
        self.assertEqual(parsed.file_sha256, hashlib.sha256(payload).hexdigest())
        self.assertIsNotNone(parsed.geometry_checksum)
        self.assertNotEqual(parsed.file_sha256, parsed.geometry_checksum)
        self.assertEqual(parsed.target_crs, "EPSG:4326")

    def test_multipolygon_and_single_feature_collection_are_deterministic(self) -> None:
        parsed = parse_geojson_import(self.payload(MULTIPOLYGON), "CRS:84")
        self.assertEqual(parsed.status, "NEEDS_REVIEW")
        self.assertEqual(parsed.geometry, MULTIPOLYGON)
        collection = {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": POLYGON, "properties": {}}],
        }
        self.assertEqual(
            parse_geojson_import(self.payload(collection), "EPSG:4326").status,
            "NEEDS_REVIEW",
        )

    def test_invalid_and_ambiguous_payloads_are_failed(self) -> None:
        self.assertEqual(
            parse_geojson_import(b"not-json", "EPSG:4326").failure_code,
            "INVALID_GEOJSON",
        )
        collection = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": POLYGON},
                {"type": "Feature", "geometry": POLYGON},
            ],
        }
        self.assertEqual(
            parse_geojson_import(self.payload(collection), "EPSG:4326").failure_code,
            "AMBIGUOUS_FEATURE_COLLECTION",
        )
        self.assertEqual(
            parse_geojson_import(
                self.payload({"type": "Point", "coordinates": [0, 0]}), "EPSG:4326"
            ).failure_code,
            "BOUNDARY_VALIDATION_FAILED",
        )

    def test_strict_geometry_and_crs_are_not_repaired_or_assumed(self) -> None:
        open_ring = {
            **POLYGON,
            "coordinates": [
                [[-47.0, -24.0], [-46.99, -24.0], [-46.99, -24.01], [-47.0, -24.01]]
            ],
        }
        bow_tie = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-47.0, -24.0],
                    [-46.99, -24.01],
                    [-46.99, -24.0],
                    [-47.0, -24.01],
                    [-47.0, -24.0],
                ]
            ],
        }
        self.assertEqual(
            parse_geojson_import(self.payload(open_ring), "EPSG:4326").status, "FAILED"
        )
        self.assertEqual(
            parse_geojson_import(self.payload(bow_tie), "EPSG:4326").status, "FAILED"
        )
        unknown = parse_geojson_import(self.payload(POLYGON), None)
        self.assertEqual(unknown.status, "NEEDS_REVIEW")
        self.assertIsNone(unknown.geometry)
        self.assertEqual(unknown.warnings, ["CRS_UNKNOWN"])
        self.assertEqual(
            parse_geojson_import(self.payload(POLYGON), "EPSG:3857").status, "FAILED"
        )

    def test_filename_policy_and_explicit_limit(self) -> None:
        self.assertEqual(
            validate_import_filename("boundary.geojson"), "boundary.geojson"
        )
        for invalid in ("../boundary.geojson", "boundary.kml", ""):
            with self.assertRaises(ValueError):
                validate_import_filename(invalid)
        self.assertEqual(MAX_BOUNDARY_IMPORT_BYTES, 1_000_000)
