"""Explicit synthetic_test_data coverage for SCL masking and temporal delta math."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from ribeira_platform.geospatial import SatelliteAsset
from ribeira_platform.object_storage import LocalObjectStorage
from ribeira_platform.raster_processing import (
    NdviProcessor,
    TemporalDeltaProcessor,
    validate_cog,
)
from ribeira_platform.sentinel2_quality import Sentinel2QualityPolicy


class QualityMaskedDeltaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = LocalObjectStorage(Path(self.temporary.name))
        self.aoi = {
            "type": "Polygon",
            "coordinates": [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _assets(
        self, prefix: str, nir_value: float, scl: np.ndarray, transform=None
    ) -> list[SatelliteAsset]:
        transform = transform or from_origin(0, 1, 0.25, 0.25)
        profile = {
            "driver": "GTiff",
            "height": 4,
            "width": 4,
            "count": 1,
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": -9999.0,
        }
        paths = {
            "B04_10m": np.ones((4, 4), dtype="float32"),
            "B08_10m": np.full((4, 4), nir_value, dtype="float32"),
            "SCL_20m": scl.astype("uint8"),
        }
        assets = []
        for key, values in paths.items():
            path = Path(self.temporary.name) / prefix / f"{key}.tif"
            path.parent.mkdir(parents=True, exist_ok=True)
            nodata = 255 if values.dtype == np.uint8 else -9999.0
            with rasterio.open(
                path,
                "w",
                dtype=str(values.dtype),
                nodata=nodata,
                **{key: value for key, value in profile.items() if key != "nodata"},
            ) as dataset:
                dataset.write(values, 1)
            assets.append(
                SatelliteAsset(
                    key,
                    "synthetic_test_data",
                    "scene",
                    key,
                    f"local://{prefix}/{key}.tif",
                    "image/tiff",
                    ["reflectance"] if key != "SCL_20m" else ["data"],
                    "Red (band 4) - 10m"
                    if key == "B04_10m"
                    else "NIR 1 (band 8) - 10m"
                    if key == "B08_10m"
                    else "Scene classification map (SCL) - 20m",
                    {},
                )
            )
        return assets

    def test_policy_excludes_cloud_nodata_and_keeps_non_vegetated_valid_classes(
        self,
    ) -> None:
        scl = np.array(
            [[4, 5, 6, 8], [0, 1, 3, 10], [4, 5, 6, 11], [7, 2, 9, 4]], dtype="uint8"
        )
        output = NdviProcessor(self.storage).process(
            self._assets("a", 3.0, scl),
            self.aoi,
            "derived/a.tif",
            quality_policy=Sentinel2QualityPolicy(),
        )
        self.assertEqual(output.statistics.valid_count, 7)
        self.assertEqual(output.quality_mask["discarded_by_scl"], 9)
        self.assertEqual(output.input_asset_keys, ["B04_10m", "B08_10m", "SCL_20m"])
        validate_cog(self.storage.read_local_path(output.output_reference))

    def test_field_delta_uses_only_valid_pixels_inside_exact_geometry(self) -> None:
        baseline = NdviProcessor(self.storage).process(
            self._assets("field-base", 3.0, np.full((4, 4), 4)),
            self.aoi,
            "derived/field-base.tif",
            quality_policy=Sentinel2QualityPolicy(),
        )
        target_scl = np.full((4, 4), 4, dtype="uint8")
        target_scl[0, 0] = 8
        target = NdviProcessor(self.storage).process(
            self._assets("field-target", 5.0, target_scl),
            self.aoi,
            "derived/field-target.tif",
            quality_policy=Sentinel2QualityPolicy(),
        )
        field_geometry = {
            "type": "Polygon",
            "coordinates": [[(0, 0), (0.5, 0), (0.5, 1), (0, 1), (0, 0)]],
        }
        delta = TemporalDeltaProcessor(self.storage).process(
            baseline.output_reference,
            target.output_reference,
            "derived/field-delta.tif",
            field_geometry,
        )
        self.assertEqual(delta.statistics.valid_count, 7)
        self.assertEqual(delta.statistics.nodata_count, 9)
        self.assertEqual(delta.statistics.coverage_percentage, Decimal("43.75"))
        with rasterio.open(self.storage.read_local_path(delta.output_reference)) as src:
            values = src.read(1)
            self.assertTrue(np.isnan(values[:, 2:]).all())
            self.assertTrue(np.isnan(values[0, 0]))

    def test_delta_uses_only_valid_intersection_and_writes_float_cog(self) -> None:
        baseline = NdviProcessor(self.storage).process(
            self._assets("base", 3.0, np.full((4, 4), 4)),
            self.aoi,
            "derived/base.tif",
            quality_policy=Sentinel2QualityPolicy(),
        )
        target_scl = np.full((4, 4), 4, dtype="uint8")
        target_scl[0, 0] = 8
        target = NdviProcessor(self.storage).process(
            self._assets("target", 5.0, target_scl),
            self.aoi,
            "derived/target.tif",
            quality_policy=Sentinel2QualityPolicy(),
        )
        delta = TemporalDeltaProcessor(self.storage).process(
            baseline.output_reference, target.output_reference, "derived/delta.tif"
        )
        self.assertEqual(delta.statistics.valid_count, 15)
        self.assertAlmostEqual(
            float(delta.statistics.minimum or 0), 0.1666667, places=5
        )
        self.assertEqual(delta.alignment["status"], "IDENTICAL_GRID")
        validate_cog(
            self.storage.read_local_path(delta.output_reference),
            expected_value_range=(-2, 2),
        )


if __name__ == "__main__":
    unittest.main()
