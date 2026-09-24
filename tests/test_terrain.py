"""Terrain tests use only labelled synthetic DEMs; no customer terrain is invented."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from ribeira_platform.terrain import TerrainProcessingError, TerrainProcessor


class TerrainProcessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "synthetic-dem.tif"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_dem(
        self, data: np.ndarray, *, crs: str = "EPSG:3857", nodata: float = -9999.0
    ) -> None:
        with rasterio.open(
            self.path,
            "w",
            driver="GTiff",
            height=data.shape[0],
            width=data.shape[1],
            count=1,
            dtype="float32",
            crs=crs,
            transform=from_origin(0, 500, 100, 100),
            nodata=nodata,
        ) as dataset:
            dataset.write(data.astype("float32"), 1)

    @staticmethod
    def aoi() -> dict:
        # This is deliberately WGS84 and transformed to the synthetic DEM CRS.
        return {
            "type": "Polygon",
            "coordinates": [
                [[0.0, 0.0], [0.0045, 0.0], [0.0045, 0.0045], [0.0, 0.0045], [0.0, 0.0]]
            ],
        }

    def test_planar_dem_calculates_elevation_slope_aspect_and_hillshade(self) -> None:
        # Elevation rises 10 m per 100 m towards the east.
        self.write_dem(np.tile(np.arange(5) * 10, (5, 1)))
        result = TerrainProcessor().analyze(self.path, self.aoi(), elevation_unit="m")
        self.assertEqual(result.statistics.valid_cell_count, 25)
        self.assertEqual(result.statistics.elevation_minimum_metres, 0.0)
        self.assertEqual(result.statistics.elevation_maximum_metres, 40.0)
        self.assertAlmostEqual(
            result.statistics.slope_mean_degrees or 0, 5.7106, places=3
        )
        self.assertAlmostEqual(
            float(result.aspect_degrees_from_north[2, 2]), 270.0, places=4
        )
        self.assertGreater(float(result.hillshade[2, 2]), 0.0)
        self.assertTrue(result.slope_degrees.mask[0, 0])
        self.assertIn("not a field survey", result.limitations[0])

    def test_nodata_and_profile_samples_remain_explicit(self) -> None:
        data = np.tile(np.arange(5) * 10, (5, 1)).astype(float)
        data[2, 2] = -9999.0
        self.write_dem(data)
        profile = {
            "type": "LineString",
            "coordinates": [[0.0005, 0.0025], [0.0023, 0.0025], [0.0040, 0.0025]],
        }
        result = TerrainProcessor().analyze(
            self.path, self.aoi(), elevation_unit="m", profile_geojson=profile
        )
        self.assertGreater(result.statistics.nodata_cell_count, 0)
        self.assertTrue(result.slope_degrees.mask[2, 2])
        self.assertEqual(len(result.profile), 5)
        self.assertEqual(result.profile[0].distance_metres, 0.0)
        self.assertGreater(result.profile[-1].distance_metres, 0)
        self.assertIsNone(result.profile[2].elevation_metres)

    def test_rejects_geographic_dem_before_calculating_slope(self) -> None:
        self.write_dem(np.ones((5, 5)), crs="EPSG:4326")
        with self.assertRaisesRegex(TerrainProcessingError, "projected"):
            TerrainProcessor().analyze(self.path, self.aoi(), elevation_unit="m")

    def test_rejects_profile_segments_outside_the_property_aoi(self) -> None:
        self.write_dem(np.tile(np.arange(5) * 10, (5, 1)))
        profile = {
            "type": "LineString",
            "coordinates": [[-0.0009, 0.0025], [0.0025, 0.0025]],
        }

        with self.assertRaisesRegex(TerrainProcessingError, "fully contained"):
            TerrainProcessor().analyze(
                self.path, self.aoi(), elevation_unit="m", profile_geojson=profile
            )

    def test_rejects_invalid_aoi_and_zero_length_profile(self) -> None:
        self.write_dem(np.tile(np.arange(5) * 10, (5, 1)))
        invalid_aoi = {
            "type": "Polygon",
            "coordinates": [
                [[0.0, 0.0], [0.0045, 0.0045], [0.0045, 0.0], [0.0, 0.0045], [0.0, 0.0]]
            ],
        }
        with self.assertRaisesRegex(TerrainProcessingError, "valid and non-empty"):
            TerrainProcessor().analyze(self.path, invalid_aoi, elevation_unit="m")
        zero_profile = {
            "type": "LineString",
            "coordinates": [[0.002, 0.002], [0.002, 0.002]],
        }
        with self.assertRaisesRegex(TerrainProcessingError, "valid and non-empty"):
            TerrainProcessor().analyze(
                self.path, self.aoi(), elevation_unit="m", profile_geojson=zero_profile
            )

    def test_rejects_dem_without_valid_cells_inside_aoi(self) -> None:
        self.write_dem(np.full((5, 5), -9999.0))
        with self.assertRaisesRegex(TerrainProcessingError, "no valid elevation cells"):
            TerrainProcessor().analyze(self.path, self.aoi(), elevation_unit="m")

    def test_requires_metric_elevation_unit_before_labelling_results(self) -> None:
        self.write_dem(np.ones((5, 5)))
        with self.assertRaisesRegex(TerrainProcessingError, "explicitly declared"):
            TerrainProcessor().analyze(self.path, self.aoi())
        with self.assertRaisesRegex(TerrainProcessingError, "in metres"):
            TerrainProcessor().analyze(self.path, self.aoi(), elevation_unit="feet")

    def test_rejects_out_of_range_wgs84_and_preserves_nan_profile_sample(self) -> None:
        data = np.tile(np.arange(5) * 10, (5, 1)).astype(float)
        data[2, 2] = np.nan
        self.write_dem(data, nodata=-9999.0)
        profile = {
            "type": "LineString",
            "coordinates": [[0.0005, 0.0025], [0.0040, 0.0025]],
        }
        result = TerrainProcessor().analyze(
            self.path, self.aoi(), elevation_unit="m", profile_geojson=profile
        )
        self.assertIsNone(result.profile[2].elevation_metres)
        invalid_wgs84_aoi = {
            "type": "Polygon",
            "coordinates": [
                [[0.0, 0.0], [181.0, 0.0], [181.0, 0.0045], [0.0, 0.0045], [0.0, 0.0]]
            ],
        }
        with self.assertRaisesRegex(TerrainProcessingError, "WGS84"):
            TerrainProcessor().analyze(self.path, invalid_wgs84_aoi, elevation_unit="m")
