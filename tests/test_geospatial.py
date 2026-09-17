from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import mapping, Polygon

from ribeira_platform.geospatial import (
    GeospatialError,
    GeospatialQuality,
    GeospatialStatus,
    ProviderSearchResult,
    SatelliteCollection,
    SatelliteSearchRequest,
)
from ribeira_platform.geospatial_provider import default_copernicus_registry
from ribeira_platform.cdse_s3 import CdseS3AssetAdapter, CdseS3Config
from ribeira_platform.geospatial_service import GeospatialApplication
from ribeira_platform.models import Property, Tenant, new_id
from ribeira_platform.object_storage import LocalObjectStorage
from ribeira_platform.raster_processing import validate_cog
from ribeira_platform.storage import SQLiteStore


class FakeProvider:
    def __init__(
        self, result: ProviderSearchResult | None = None, unavailable: bool = False
    ):
        self.registry = default_copernicus_registry()
        self.result = result
        self.unavailable = unavailable
        self.search_calls = 0

    def get_collection(self, collection_id: str) -> SatelliteCollection:
        return SatelliteCollection(
            id="",
            provider_id="COPERNICUS_CDSE",
            external_collection_id=collection_id,
            title="Sentinel-2 Level-2A",
            mission="Sentinel-2",
            processing_level="L2A",
            spatial_resolution="[10, 20, 60]",
            temporal_characteristics={},
            bands={},
            license="other",
            stac_version="1.1.0",
            metadata={"fixture": True},
        )

    def search(
        self, request: SatelliteSearchRequest, aoi_geojson: dict
    ) -> ProviderSearchResult:
        self.search_calls += 1
        if self.unavailable:
            from ribeira_platform.geospatial_provider import StacProviderError

            raise StacProviderError("SOURCE_UNAVAILABLE", "controlled provider failure")
        assert self.result is not None
        return self.result


def _item() -> dict:
    geometry = mapping(Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]))
    return {
        "type": "Feature",
        "stac_version": "1.1.0",
        "id": "TEST_S2_ITEM_001",
        "geometry": geometry,
        "bbox": [0, 0, 1, 1],
        "properties": {
            "datetime": "2025-01-15T10:00:00Z",
            "created": "2025-01-15T12:00:00Z",
            "eo:cloud_cover": 4.2,
            "platform": "sentinel-2a",
            "constellation": "sentinel-2",
            "processing:level": "L2A",
        },
        "assets": {
            "B04_10m": {
                "href": "local://assets/red.tif",
                "type": "image/tiff",
                "roles": ["data", "reflectance"],
                "title": "Red (band 4) - 10m",
            },
            "B08_10m": {
                "href": "local://assets/nir.tif",
                "type": "image/tiff",
                "roles": ["data", "reflectance"],
                "title": "NIR 1 (band 8) - 10m",
            },
        },
    }


class GeospatialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore()
        self.tenant = Tenant(new_id(), "Geospatial tenant")
        self.other_tenant = Tenant(new_id(), "Other tenant")
        self.store.create_tenant(self.tenant)
        self.store.create_tenant(self.other_tenant)
        self.property = Property(
            new_id(),
            self.tenant.id,
            "Test AOI",
            mapping(
                Polygon(
                    [
                        (0.05, 0.05),
                        (0.95, 0.05),
                        (0.95, 0.95),
                        (0.05, 0.95),
                        (0.05, 0.05),
                    ]
                )
            ),
            "EPSG:4326",
        )
        self.store.create_property(self.property)
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = LocalObjectStorage(Path(self.tmp.name))
        self._write_rasters()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _write_rasters(self) -> None:
        transform = from_origin(0, 1, 0.25, 0.25)
        profile = {
            "driver": "GTiff",
            "height": 4,
            "width": 4,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:4326",
            "transform": transform,
            "nodata": -9999.0,
        }
        red = np.ones((4, 4), dtype="float32")
        nir = np.full((4, 4), 3, dtype="float32")
        red[0, 0] = -9999
        nir[0, 0] = -9999
        for key, values in (("assets/red.tif", red), ("assets/nir.tif", nir)):
            path = Path(self.tmp.name) / key
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(path, "w", **profile) as dataset:
                dataset.write(values, 1)

    def _application(
        self, provider: FakeProvider | None = None
    ) -> GeospatialApplication:
        return GeospatialApplication(
            self.store,
            provider
            or FakeProvider(
                ProviderSearchResult(
                    [_item()], [{"type": "FeatureCollection", "features": [_item()]}]
                )
            ),
            self.storage,
        )

    def test_search_catalogues_scene_and_ndvi_is_derived(self) -> None:
        app = self._application()
        result = app.search_satellite(
            self.tenant.id,
            SatelliteSearchRequest(
                self.property.id,
                "sentinel-2-l2a",
                "2025-01-01T00:00:00Z",
                "2025-02-01T00:00:00Z",
            ),
        )
        self.assertEqual(result.search.status, GeospatialStatus.COMPLETED)
        self.assertEqual(len(result.scenes), 1)
        self.assertEqual(len(result.evidence_ids), 1)
        job = app.create_ndvi_job(self.tenant.id, self.property.id, result.search.id)
        output = app.run_ndvi_job(self.tenant.id, job.id)
        self.assertIsNotNone(output.product)
        assert output.product is not None
        self.assertEqual(output.product.classification.value, "DERIVED")
        self.assertAlmostEqual(
            float(output.product.statistics.mean or 0), 0.5, places=5
        )
        self.assertEqual(output.product.statistics.nodata_count, 1)
        self.assertIn(GeospatialQuality.PARTIAL_COVERAGE, output.product.quality)
        self.assertEqual(output.product.statistics.coverage_percentage, 93.75)
        assert output.product.output_reference is not None
        validate_cog(self.storage.read_local_path(output.product.output_reference))

    def test_cog_validator_rejects_a_regular_geotiff(self) -> None:
        path = Path(self.tmp.name) / "not-a-cog.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=4,
            width=4,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0, 1, 0.25, 0.25),
            nodata=np.nan,
        ) as dataset:
            dataset.write(np.ones((1, 4, 4), dtype="float32"))
        with self.assertRaisesRegex(ValueError, "not recognized by GDAL as a COG"):
            validate_cog(path)

    def test_s3_asset_without_credentials_blocks_real_ndvi(self) -> None:
        item = deepcopy(_item())
        item["assets"]["B04_10m"]["href"] = "s3://eodata/real/red.jp2"
        item["assets"]["B08_10m"]["href"] = "s3://eodata/real/nir.jp2"
        app = GeospatialApplication(
            self.store,
            FakeProvider(ProviderSearchResult([item], [{"features": [item]}])),
            self.storage,
            asset_adapter=CdseS3AssetAdapter(
                self.storage,
                credential_provider=type(
                    "Missing", (), {"get_credentials": lambda _: None}
                )(),
                config=CdseS3Config(),
            ),
        )
        result = app.search_satellite(
            self.tenant.id,
            SatelliteSearchRequest(
                self.property.id,
                "sentinel-2-l2a",
                "2025-01-01T00:00:00Z",
                "2025-02-01T00:00:00Z",
            ),
        )
        job = app.create_ndvi_job(self.tenant.id, self.property.id, result.search.id)
        output = app.run_ndvi_job(self.tenant.id, job.id)
        self.assertIsNone(output.product)
        self.assertEqual(output.job.failure_reason, "BLOCKED_BY_CREDENTIAL")

    def test_duplicate_scene_is_idempotent_and_tenant_scoped(self) -> None:
        app = self._application()
        request = SatelliteSearchRequest(
            self.property.id,
            "sentinel-2-l2a",
            "2025-01-01T00:00:00Z",
            "2025-02-01T00:00:00Z",
        )
        first = app.search_satellite(self.tenant.id, request)
        second = app.search_satellite(self.tenant.id, request)
        self.assertEqual(first.scenes[0].id, second.scenes[0].id)
        self.assertEqual(len(app.list_scenes(self.tenant.id, self.property.id)), 1)
        self.assertEqual(app.list_scenes(self.other_tenant.id, self.property.id), [])
        self.assertIsNone(app.get_search(self.other_tenant.id, first.search.id))

    def test_provider_unavailable_is_explicit(self) -> None:
        app = self._application(FakeProvider(unavailable=True))
        result = app.search_satellite(
            self.tenant.id,
            SatelliteSearchRequest(
                self.property.id,
                "sentinel-2-l2a",
                "2025-01-01T00:00:00Z",
                "2025-02-01T00:00:00Z",
            ),
        )
        self.assertEqual(result.search.status, GeospatialStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(result.scenes, [])
        self.assertEqual(result.search.selected_scene_id, None)

    def test_invalid_geometry_and_naive_time_are_rejected(self) -> None:
        invalid = Property(
            new_id(),
            self.tenant.id,
            "Invalid",
            {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
            },
            "EPSG:4326",
        )
        self.store.create_property(invalid)
        with self.assertRaises(GeospatialError):
            self._application().search_satellite(
                self.tenant.id,
                SatelliteSearchRequest(
                    invalid.id,
                    "sentinel-2-l2a",
                    "2025-01-01T00:00:00Z",
                    "2025-02-01T00:00:00Z",
                ),
            )
        with self.assertRaises(ValueError):
            SatelliteSearchRequest(
                self.property.id, "sentinel-2-l2a", "2025-01-01", "2025-02-01T00:00:00Z"
            )


if __name__ == "__main__":
    unittest.main()
