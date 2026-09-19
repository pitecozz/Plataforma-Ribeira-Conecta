from __future__ import annotations

import unittest

from ribeira_platform.boundaries import validate_boundary


VALID_POLYGON = {
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


class BoundaryValidationTests(unittest.TestCase):
    """Explicitly synthetic geometry fixtures; never customer boundaries."""

    def test_polygon_is_calculated_and_checksums_are_stable(self) -> None:
        geometry, area, checksum = validate_boundary(VALID_POLYGON, "EPSG:4326")
        self.assertEqual(geometry, VALID_POLYGON)
        self.assertGreater(float(area), 0)
        self.assertEqual(len(checksum), 64)
        self.assertEqual(checksum, validate_boundary(VALID_POLYGON, "CRS:84")[2])

    def test_multipolygon_is_valid(self) -> None:
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [
                VALID_POLYGON["coordinates"],
                [
                    [
                        [-46.98, -24.0],
                        [-46.97, -24.0],
                        [-46.97, -24.01],
                        [-46.98, -24.01],
                        [-46.98, -24.0],
                    ]
                ],
            ],
        }
        self.assertGreater(float(validate_boundary(geometry, "EPSG:4326")[1]), 0)

    def assert_invalid(self, geometry: dict, message: str = "") -> None:
        with self.assertRaisesRegex(ValueError, message or ".*"):
            validate_boundary(geometry, "EPSG:4326")

    def test_open_ring_is_rejected_without_repair(self) -> None:
        geometry = {
            **VALID_POLYGON,
            "coordinates": [
                [[-47.0, -24.0], [-46.99, -24.0], [-46.99, -24.01], [-47.0, -24.01]]
            ],
        }
        self.assert_invalid(geometry, "explicitly closed")

    def test_self_intersection_is_rejected(self) -> None:
        self.assert_invalid(
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-47, -24],
                        [-46.99, -24.01],
                        [-46.99, -24],
                        [-47, -24.01],
                        [-47, -24],
                    ]
                ],
            },
            "invalid",
        )

    def test_empty_or_wrong_type_is_rejected(self) -> None:
        self.assert_invalid({"type": "Polygon", "coordinates": []}, "closed")
        self.assert_invalid({"type": "Point", "coordinates": [-47, -24]}, "Polygon")

    def test_out_of_bounds_and_zero_area_are_rejected(self) -> None:
        self.assert_invalid(
            {
                "type": "Polygon",
                "coordinates": [[[181, 0], [181, 1], [179, 1], [181, 0]]],
            },
            "bounds",
        )
        self.assert_invalid(
            {
                "type": "Polygon",
                "coordinates": [[[-47, -24], [-47, -24], [-47, -24], [-47, -24]]],
            },
            "invalid",
        )

    def test_unsupported_crs_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "CRS"):
            validate_boundary(VALID_POLYGON, "EPSG:3857")
