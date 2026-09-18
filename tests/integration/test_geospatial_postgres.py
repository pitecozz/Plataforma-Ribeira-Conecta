from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import psycopg
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import Polygon, mapping

from ribeira_platform.cdse_s3 import AssetCredentials, CdseS3AssetAdapter, CdseS3Config
from ribeira_platform.geospatial import (
    ProviderSearchResult,
    ProcessingJob,
    ProcessingJobStatus,
    SatelliteCollection,
    SatelliteScene,
    SatelliteSearchRequest,
)
from ribeira_platform.geospatial_provider import default_copernicus_registry
from ribeira_platform.geospatial_service import GeospatialApplication
from ribeira_platform.models import new_id
from ribeira_platform.object_storage import LocalObjectStorage
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.raster_processing import validate_cog
from ribeira_platform.service import RibeiraApplication
from tests.integration.tenant_cleanup import delete_test_tenants


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")


class _SyntheticBody:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def close(self) -> None:
        return None


class _SyntheticS3:
    """Explicit synthetic test data; it never contacts CDSE."""

    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def head_object(self, *, Key: str, **_: object) -> dict[str, object]:
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, *, Key: str, **_: object) -> dict[str, _SyntheticBody]:
        return {"Body": _SyntheticBody(self.objects[Key])}


class _SyntheticCredentials:
    def get_credentials(self) -> AssetCredentials:
        return AssetCredentials("synthetic-test-access", "synthetic-test-key-material")


class _SyntheticStacProvider:
    def __init__(self, item: dict[str, object]) -> None:
        self.registry = default_copernicus_registry()
        self.item = item

    def get_collection(self, collection_id: str) -> SatelliteCollection:
        return SatelliteCollection(
            id="",
            provider_id="COPERNICUS_CDSE",
            external_collection_id=collection_id,
            title="Synthetic Sentinel-2 test collection",
            mission="Sentinel-2",
            processing_level="L2A",
            spatial_resolution="[10]",
            temporal_characteristics={},
            bands={},
            license="test-data-only",
            stac_version="1.1.0",
            metadata={"synthetic_test_data": True},
        )

    def search(
        self, _request: SatelliteSearchRequest, _aoi: dict[str, object]
    ) -> ProviderSearchResult:
        return ProviderSearchResult([self.item], [{"synthetic_test_data": True}])


def _synthetic_tiff(value: float) -> bytes:
    profile = {
        "driver": "GTiff",
        "height": 8,
        "width": 8,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": from_origin(-47.1, -24.0, 0.0125, 0.0125),
        "nodata": -9999.0,
    }
    with MemoryFile() as memory:
        with memory.open(**profile) as dataset:
            dataset.write(np.full((1, 8, 8), value, dtype="float32"))
        return memory.read()


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class GeospatialPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self.repo = self.application.geospatial.repository
        self._test_tenant_ids: list[str] = []

    def create_test_tenant(self, name: str, application: RibeiraApplication | None = None):
        tenant = (application or self.application).create_tenant(name)
        self._test_tenant_ids.append(tenant.id)
        return tenant

    def tearDown(self) -> None:
        try:
            delete_test_tenants(self._test_tenant_ids)
        finally:
            self.store.close()

    def test_postgis_scene_and_rls_block_cross_tenant_access(self) -> None:
        tenant_a = self.create_test_tenant("Geo A")
        tenant_b = self.create_test_tenant("Geo B")
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-47.1, -24.1],
                    [-47.0, -24.1],
                    [-47.0, -24.0],
                    [-47.1, -24.0],
                    [-47.1, -24.1],
                ]
            ],
        }
        property_a = self.application.create_property(
            tenant_a.id, "AOI A", polygon, "EPSG:4326"
        )
        collection = SatelliteCollection(
            id="",
            provider_id="COPERNICUS_CDSE",
            external_collection_id="sentinel-2-l2a",
            title="Sentinel-2 Level-2A",
            mission="Sentinel-2",
            processing_level="L2A",
            spatial_resolution="[10,20,60]",
            temporal_characteristics={},
            bands={},
            license="other",
            stac_version="1.1.0",
            metadata={"test": True},
        )
        scene = SatelliteScene(
            id=new_id(),
            tenant_id=tenant_a.id,
            property_id=property_a.id,
            provider_id="COPERNICUS_CDSE",
            collection_id="sentinel-2-l2a",
            external_item_id="RLS_TEST_ITEM",
            acquisition_datetime="2025-01-01T00:00:00+00:00",
            provider_published_datetime=None,
            geometry_geojson=polygon,
            bbox=[-47.1, -24.1, -47.0, -24.0],
            cloud_cover=None,
            platform="sentinel-2a",
            constellation="sentinel-2",
            processing_level="L2A",
            stac_version="1.1.0",
            raw_metadata_reference="local://test/raw.json",
            checksum="test-checksum",
        )
        with self.store.tenant_transaction(tenant_a.id):
            self.repo.upsert_collection(collection)
            stored = self.repo.upsert_scene(scene)
            self.assertEqual(stored.id, scene.id)
            row = self.store.connection.execute(
                "SELECT ST_SRID(geometry) AS srid FROM satellite_scene WHERE id=%s",
                (scene.id,),
            ).fetchone()
            self.assertEqual(row["srid"], 4326)

        with self.store.tenant_transaction(tenant_b.id):
            self.assertIsNone(
                self.store.connection.execute(
                    "SELECT id FROM satellite_scene WHERE id=%s", (scene.id,)
                ).fetchone()
            )
            self.assertEqual(
                self.store.connection.execute(
                    "UPDATE satellite_scene SET platform='tampered' WHERE id=%s",
                    (scene.id,),
                ).rowcount,
                0,
            )
            self.assertEqual(
                self.store.connection.execute(
                    "DELETE FROM satellite_scene WHERE id=%s", (scene.id,)
                ).rowcount,
                0,
            )

        with self.assertRaises(psycopg.Error):
            with self.store.tenant_transaction(tenant_b.id):
                self.store.connection.execute(
                    "INSERT INTO satellite_asset(id,tenant_id,scene_id,asset_key,href) VALUES (%s,%s,%s,%s,%s)",
                    (new_id(), tenant_b.id, scene.id, "B04_10m", "s3://not-used"),
                )

    def test_postgresql_queue_claim_is_atomic_and_job_history_is_rls_scoped(
        self,
    ) -> None:
        """Uses PostgreSQL/RLS; fixture identifiers do not represent client data."""
        tenant_a = self.create_test_tenant("Async queue A")
        tenant_b = self.create_test_tenant("Async queue B")
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-47.1, -24.1],
                    [-47.0, -24.1],
                    [-47.0, -24.0],
                    [-47.1, -24.0],
                    [-47.1, -24.1],
                ]
            ],
        }
        property_a = self.application.create_property(
            tenant_a.id, "Async queue AOI", polygon, "EPSG:4326"
        )
        collection = SatelliteCollection(
            id="",
            provider_id="COPERNICUS_CDSE",
            external_collection_id="sentinel-2-l2a",
            title="Test collection",
            mission="Sentinel-2",
            processing_level="L2A",
            spatial_resolution="[10]",
            temporal_characteristics={},
            bands={},
            license="test-data-only",
            stac_version="1.1.0",
            metadata={"synthetic_test_data": True},
        )
        scene = SatelliteScene(
            id=new_id(),
            tenant_id=tenant_a.id,
            property_id=property_a.id,
            provider_id="COPERNICUS_CDSE",
            collection_id="sentinel-2-l2a",
            external_item_id=f"ASYNC_QUEUE_{new_id()}",
            acquisition_datetime="2025-01-01T00:00:00+00:00",
            provider_published_datetime=None,
            geometry_geojson=polygon,
            bbox=[-47.1, -24.1, -47.0, -24.0],
            cloud_cover=None,
            platform="sentinel-2a",
            constellation="sentinel-2",
            processing_level="L2A",
            stac_version="1.1.0",
            raw_metadata_reference="test://async-queue",
            checksum="test-checksum",
        )
        with self.store.tenant_transaction(tenant_a.id):
            self.repo.upsert_collection(collection)
            self.repo.upsert_scene(scene)
            job = self.repo.create_job(
                ProcessingJob(
                    new_id(),
                    tenant_a.id,
                    property_a.id,
                    scene.id,
                    "NDVI",
                    "NDVI",
                    "test",
                    {},
                    ProcessingJobStatus.QUEUED,
                    f"async-queue-{new_id()}",
                ),
                "test-requester",
            )
            claimed = self.repo.claim_next_job("postgres-worker-a")
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.status, ProcessingJobStatus.RUNNING)

        second_store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        try:
            second_app = RibeiraApplication(second_store)
            second_repo = second_app.geospatial.repository
            with second_store.tenant_transaction(tenant_a.id):
                self.assertIsNone(second_repo.claim_next_job("postgres-worker-b"))
            with second_store.tenant_transaction(tenant_b.id):
                self.assertIsNone(second_repo.get_job(tenant_b.id, job.id))
                self.assertEqual(
                    second_repo.list_job_transitions(tenant_b.id, job.id), []
                )
        finally:
            second_store.close()

        with self.store.tenant_transaction(tenant_a.id):
            completed = self.repo.mark_job(
                tenant_a.id,
                job.id,
                ProcessingJobStatus.FAILED,
                failure_code="TEST_WORKER_FAILURE",
                failure_reason="test worker failure",
                actor="worker:postgres-worker-a",
                worker_id="postgres-worker-a",
            )
            transitions = self.repo.list_job_transitions(tenant_a.id, job.id)
        self.assertEqual(completed.status, ProcessingJobStatus.FAILED)
        self.assertEqual(
            [transition.to_status for transition in transitions],
            [
                ProcessingJobStatus.QUEUED,
                ProcessingJobStatus.RUNNING,
                ProcessingJobStatus.FAILED,
            ],
        )

        with self.assertRaises(psycopg.Error):
            with self.store.tenant_transaction(tenant_b.id):
                self.store.connection.execute(
                    "INSERT INTO evidence(id,tenant_id,evidence_type,reference_id,data_classification,limitations) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        new_id(),
                        tenant_b.id,
                        "SATELLITE_SCENE",
                        scene.id,
                        "OFFICIAL_SOURCE",
                        json.dumps([]),
                    ),
                )

    def test_synthetic_ndvi_evidence_chain_is_persisted_with_postgis_and_rls(
        self,
    ) -> None:
        """This proves persistence with synthetic fixture bytes, never live CDSE data."""
        polygon = mapping(
            Polygon(
                [
                    (-47.1, -24.1),
                    (-47.0, -24.1),
                    (-47.0, -24.0),
                    (-47.1, -24.0),
                    (-47.1, -24.1),
                ]
            )
        )
        item = {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "SYNTHETIC_TEST_SENTINEL2_ITEM",
            "geometry": polygon,
            "bbox": [-47.1, -24.1, -47.0, -24.0],
            "properties": {
                "datetime": "2025-01-15T10:00:00Z",
                "created": "2025-01-15T12:00:00Z",
                "eo:cloud_cover": 0,
                "platform": "synthetic-sentinel-2a",
                "constellation": "sentinel-2",
                "processing:level": "L2A",
            },
            "assets": {
                "B04_10m": {
                    "href": "s3://eodata/synthetic-test/B04_10m.tif",
                    "type": "image/tiff",
                    "roles": ["data", "reflectance"],
                    "title": "Red (band 4) - 10m",
                },
                "B08_10m": {
                    "href": "s3://eodata/synthetic-test/B08_10m.tif",
                    "type": "image/tiff",
                    "roles": ["data", "reflectance"],
                    "title": "NIR 1 (band 8) - 10m",
                },
            },
        }
        fixture_objects = {
            "synthetic-test/B04_10m.tif": _synthetic_tiff(1.0),
            "synthetic-test/B08_10m.tif": _synthetic_tiff(3.0),
        }
        with tempfile.TemporaryDirectory() as temporary:
            storage = LocalObjectStorage(Path(temporary) / "objects")
            adapter = CdseS3AssetAdapter(
                storage,
                credential_provider=_SyntheticCredentials(),
                config=CdseS3Config(
                    max_object_bytes=1_000_000,
                    max_job_bytes=2_000_000,
                    chunk_bytes=1024,
                ),
                client_factory=lambda *_: _SyntheticS3(fixture_objects),
            )
            provider = _SyntheticStacProvider(item)
            application = RibeiraApplication(
                self.store,
                geospatial_provider=provider,
                object_storage=storage,
            )
            application.geospatial = GeospatialApplication(
                self.store, provider, storage, asset_adapter=adapter
            )
            tenant_a = self.create_test_tenant("Synthetic geospatial tenant", application)
            tenant_b = self.create_test_tenant("Other geospatial tenant", application)
            property_a = application.create_property(
                tenant_a.id, "Synthetic AOI", polygon, "EPSG:4326"
            )
            search = application.geospatial.search_satellite(
                tenant_a.id,
                SatelliteSearchRequest(
                    property_a.id,
                    "sentinel-2-l2a",
                    "2025-01-01T00:00:00Z",
                    "2025-02-01T00:00:00Z",
                ),
            )
            job = application.geospatial.create_ndvi_job(
                tenant_a.id, property_a.id, search.search.id
            )
            result = application.geospatial.run_ndvi_job(tenant_a.id, job.id)
            self.assertIsNotNone(result.product)
            assert result.product is not None
            self.assertEqual(result.product.statistics.valid_count, 64)
            self.assertIsNotNone(result.product.output_checksum)
            self.assertEqual(len(result.evidence_ids), 1)
            assert result.product.output_reference is not None
            validate_cog(storage.read_local_path(result.product.output_reference))

            with self.store.tenant_transaction(tenant_a.id):
                scene_row = self.store.connection.execute(
                    "SELECT external_item_id, checksum, raw_metadata_reference "
                    "FROM satellite_scene WHERE id=%s",
                    (search.search.selected_scene_id,),
                ).fetchone()
                asset_rows = self.store.connection.execute(
                    "SELECT asset_key, checksum_local, checksum_algorithm, "
                    "download_status, local_reference FROM satellite_asset "
                    "WHERE scene_id=%s ORDER BY asset_key",
                    (search.search.selected_scene_id,),
                ).fetchall()
                job_row = self.store.connection.execute(
                    "SELECT status, algorithm_id, algorithm_version, output_product_id "
                    "FROM processing_job WHERE id=%s",
                    (job.id,),
                ).fetchone()
                product_row = self.store.connection.execute(
                    "SELECT processing_job_id, output_checksum, input_asset_keys "
                    "FROM derived_product WHERE id=%s",
                    (result.product.id,),
                ).fetchone()
                evidence_rows = self.store.connection.execute(
                    "SELECT evidence_type, reference_id FROM evidence "
                    "WHERE reference_id IN (%s,%s) ORDER BY evidence_type",
                    (search.search.selected_scene_id, result.product.id),
                ).fetchall()

            assert scene_row is not None
            self.assertEqual(
                scene_row["external_item_id"], "SYNTHETIC_TEST_SENTINEL2_ITEM"
            )
            self.assertTrue(scene_row["checksum"])
            self.assertTrue(scene_row["raw_metadata_reference"])
            self.assertEqual(len(asset_rows), 2)
            for asset in asset_rows:
                self.assertTrue(asset["checksum_local"])
                self.assertEqual(asset["checksum_algorithm"], "SHA-256")
                self.assertEqual(asset["download_status"], "SUCCEEDED")
                self.assertTrue(asset["local_reference"])
            assert job_row is not None
            self.assertEqual(job_row["status"], "SUCCEEDED")
            self.assertEqual(job_row["algorithm_id"], "NDVI")
            self.assertEqual(job_row["algorithm_version"], "1.0.0")
            self.assertEqual(str(job_row["output_product_id"]), result.product.id)
            assert product_row is not None
            self.assertEqual(str(product_row["processing_job_id"]), job.id)
            self.assertEqual(
                product_row["output_checksum"], result.product.output_checksum
            )
            self.assertEqual(product_row["input_asset_keys"], ["B04_10m", "B08_10m"])
            self.assertEqual(
                {
                    (row["evidence_type"], str(row["reference_id"]))
                    for row in evidence_rows
                },
                {
                    ("SATELLITE_SCENE", search.search.selected_scene_id),
                    ("DERIVED_PRODUCT", result.product.id),
                },
            )

            with self.store.tenant_transaction(tenant_b.id):
                self.assertIsNone(
                    self.store.connection.execute(
                        "SELECT id FROM derived_product WHERE id=%s",
                        (result.product.id,),
                    ).fetchone()
                )
                self.assertIsNone(
                    self.store.connection.execute(
                        "SELECT id FROM satellite_scene WHERE id=%s",
                        (search.search.selected_scene_id,),
                    ).fetchone()
                )


if __name__ == "__main__":
    unittest.main()
