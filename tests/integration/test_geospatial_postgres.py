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
from ribeira_platform.epistemology import (
    DataClassification,
    DecisionStatus,
    RuleAuthority,
)
from ribeira_platform.geospatial_provider import default_copernicus_registry
from ribeira_platform.geospatial_service import GeospatialApplication
from ribeira_platform.models import RuleDefinition, new_id
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
    return _synthetic_raster(np.full((8, 8), value, dtype="float32"))


def _synthetic_raster(values: np.ndarray) -> bytes:
    profile = {
        "driver": "GTiff",
        "height": 8,
        "width": 8,
        "count": 1,
        "dtype": str(values.dtype),
        "crs": "EPSG:4326",
        "transform": from_origin(-47.1, -24.0, 0.0125, 0.0125),
        "nodata": 0 if values.dtype == np.dtype("uint8") else -9999.0,
    }
    with MemoryFile() as memory:
        with memory.open(**profile) as dataset:
            dataset.write(values, 1)
        return memory.read()


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class GeospatialPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self.repo = self.application.geospatial.repository
        self._test_tenant_ids: list[str] = []

    def create_test_tenant(
        self, name: str, application: RibeiraApplication | None = None
    ):
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
            tenant_a = self.create_test_tenant(
                "Synthetic geospatial tenant", application
            )
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

    def test_field_quality_masked_temporal_delta_end_to_end(self) -> None:
        property_boundary = mapping(
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
        field_boundary = mapping(
            Polygon(
                [
                    (-47.1, -24.1),
                    (-47.05, -24.1),
                    (-47.05, -24.0),
                    (-47.1, -24.0),
                    (-47.1, -24.1),
                ]
            )
        )
        baseline_scl = np.full((8, 8), 4, dtype="uint8")
        baseline_scl[0, 0] = 9
        target_scl = np.full((8, 8), 4, dtype="uint8")
        target_scl[0, 1] = 9
        target_nir = np.full((8, 8), 5.0, dtype="float32")
        target_nir[:, :4] = 2.0
        fixture_objects = {
            "synthetic-delta-baseline/B04_10m.tif": _synthetic_tiff(1.0),
            "synthetic-delta-baseline/B08_10m.tif": _synthetic_tiff(3.0),
            "synthetic-delta-baseline/SCL_20m.tif": _synthetic_raster(baseline_scl),
            "synthetic-delta-target/B04_10m.tif": _synthetic_tiff(1.0),
            "synthetic-delta-target/B08_10m.tif": _synthetic_raster(target_nir),
            "synthetic-delta-target/SCL_20m.tif": _synthetic_raster(target_scl),
        }

        def scene_item(name: str, acquired_at: str) -> dict[str, object]:
            prefix = f"synthetic-delta-{name}"
            return {
                "type": "Feature",
                "stac_version": "1.1.0",
                "id": f"SYNTHETIC_DELTA_{name.upper()}",
                "geometry": property_boundary,
                "bbox": [-47.1, -24.1, -47.0, -24.0],
                "properties": {
                    "datetime": acquired_at,
                    "created": acquired_at,
                    "eo:cloud_cover": 0,
                    "platform": "synthetic-sentinel-2a",
                    "constellation": "sentinel-2",
                    "processing:level": "L2A",
                },
                "assets": {
                    key: {
                        "href": f"s3://eodata/{prefix}/{key}.tif",
                        "type": "image/tiff",
                        "roles": ["data", "reflectance"]
                        if key != "SCL_20m"
                        else ["data", "classification"],
                        "title": {
                            "B04_10m": "Red (band 4) - 10m",
                            "B08_10m": "NIR 1 (band 8) - 10m",
                            "SCL_20m": "Scene classification - 20m",
                        }[key],
                    }
                    for key in ("B04_10m", "B08_10m", "SCL_20m")
                },
            }

        with tempfile.TemporaryDirectory() as temporary:
            storage = LocalObjectStorage(Path(temporary))
            adapter = CdseS3AssetAdapter(
                storage,
                credential_provider=_SyntheticCredentials(),
                config=CdseS3Config(
                    max_object_bytes=1_000_000,
                    max_job_bytes=3_000_000,
                    chunk_bytes=1024,
                ),
                client_factory=lambda *_: _SyntheticS3(fixture_objects),
            )
            provider = _SyntheticStacProvider(
                scene_item("baseline", "2025-01-15T10:00:00Z")
            )
            application = RibeiraApplication(
                self.store,
                geospatial_provider=provider,
                object_storage=storage,
            )
            application.geospatial = GeospatialApplication(
                self.store, provider, storage, asset_adapter=adapter
            )
            tenant = self.create_test_tenant(
                "Synthetic field delta tenant", application
            )
            property_item = application.create_property(
                tenant.id,
                "Synthetic field delta property",
                property_boundary,
                "EPSG:4326",
                boundary_source="synthetic integration boundary",
                classification=DataClassification.MANUAL_CONFIRMED,
            )
            field = application.fields.create(
                tenant.id,
                property_id=property_item.id,
                name="Synthetic western field",
                status="ACTIVE",
                geometry_geojson=field_boundary,
                geometry_crs="EPSG:4326",
                source_reference="synthetic integration field boundary",
                observed_at="2025-01-10T10:00:00+00:00",
                classification=DataClassification.MANUAL_CONFIRMED,
                actor="integration-operator",
            )

            products = []
            for name, acquired_at, search_end in (
                (
                    "baseline",
                    "2025-01-15T10:00:00Z",
                    "2025-01-15T10:01:00Z",
                ),
                (
                    "target",
                    "2025-02-15T10:00:00Z",
                    "2025-02-15T10:01:00Z",
                ),
            ):
                provider.item = scene_item(name, acquired_at)
                search = application.geospatial.search_satellite(
                    tenant.id,
                    SatelliteSearchRequest(
                        property_item.id,
                        "sentinel-2-l2a",
                        acquired_at,
                        search_end,
                    ),
                )
                ndvi_job = application.geospatial.create_ndvi_job(
                    tenant.id, property_item.id, search.search.id
                )
                ndvi = application.geospatial.run_ndvi_job(tenant.id, ndvi_job.id)
                self.assertIsNotNone(
                    ndvi.product,
                    f"{name} NDVI job failed: {ndvi.job.failure_code} {ndvi.job.failure_reason}",
                )
                assert ndvi.product is not None
                masked_job = application.geospatial.create_quality_masked_ndvi_job(
                    tenant.id, property_item.id, ndvi.product.id
                )
                masked = application.geospatial.run_quality_masked_ndvi_job(
                    tenant.id, masked_job.id
                )
                assert masked.product is not None
                products.append(masked.product)

            baseline, target = products
            self.assertEqual(baseline.product_type, "NDVI_QUALITY_MASKED")
            self.assertEqual(target.product_type, "NDVI_QUALITY_MASKED")
            self.assertEqual(baseline.parameters["quality_mask"]["valid_after_scl"], 63)
            self.assertEqual(target.parameters["quality_mask"]["valid_after_scl"], 63)
            delta_job = application.geospatial.create_temporal_delta_job(
                tenant.id,
                property_item.id,
                baseline.id,
                target.id,
                field_id=field.id,
            )
            self.assertEqual(delta_job.field_id, field.id)
            self.assertEqual(delta_job.field_boundary_version, field.boundary_version)
            self.assertEqual(delta_job.field_boundary_checksum, field.boundary_checksum)
            self.assertEqual(
                delta_job.parameters["field_snapshot"],
                {
                    "field_id": field.id,
                    "boundary_version": field.boundary_version,
                    "boundary_checksum": field.boundary_checksum,
                },
            )
            delta_result = application.geospatial.run_temporal_delta_job(
                tenant.id, delta_job.id
            )
            assert delta_result.product is not None
            delta = delta_result.product
            self.assertEqual(delta.statistics.valid_count, 30)
            self.assertAlmostEqual(float(delta.statistics.mean), -1 / 6, places=5)
            self.assertEqual(delta.field_id, field.id)
            self.assertEqual(delta.field_boundary_version, field.boundary_version)
            self.assertEqual(delta.field_boundary_checksum, field.boundary_checksum)
            assert delta.output_reference is not None
            validate_cog(
                storage.read_local_path(delta.output_reference),
                expected_value_range=(-2.0, 2.0),
            )

            with self.store.tenant_transaction(tenant.id):
                dependencies = (
                    application.geospatial.repository.list_product_dependencies(
                        tenant.id, delta.id
                    )
                )
                evidence = self.store.evidence_for_reference(tenant.id, delta.id)
                persisted_jobs = self.store.connection.execute(
                    "SELECT id,status,output_product_id FROM processing_job "
                    "WHERE tenant_id=%s AND id IN (%s,%s,%s) ORDER BY id",
                    (
                        tenant.id,
                        baseline.processing_job_id,
                        target.processing_job_id,
                        delta_job.id,
                    ),
                ).fetchall()
                snapshot_row = self.store.connection.execute(
                    "SELECT version,geometry_checksum FROM field_context_boundary_version "
                    "WHERE tenant_id=%s AND field_context_id=%s AND version=%s",
                    (tenant.id, field.id, field.boundary_version),
                ).fetchone()
                with self.assertRaises(psycopg.Error):
                    with self.store.connection.transaction():
                        self.store.connection.execute(
                            "UPDATE field_context_boundary_version SET reason=%s "
                            "WHERE tenant_id=%s AND field_context_id=%s AND version=%s",
                            (
                                "synthetic attempted rewrite",
                                tenant.id,
                                field.id,
                                field.boundary_version,
                            ),
                        )
            self.assertEqual(
                {
                    (item.relationship, item.upstream_product_id)
                    for item in dependencies
                },
                {("BASELINE_NDVI", baseline.id), ("TARGET_NDVI", target.id)},
            )
            self.assertEqual(len(persisted_jobs), 3)
            self.assertTrue(
                all(
                    row["status"] == ProcessingJobStatus.SUCCEEDED.value
                    and row["output_product_id"] is not None
                    for row in persisted_jobs
                )
            )
            self.assertIsNotNone(evidence)
            assert evidence is not None
            self.assertEqual(evidence.evidence_type, "DERIVED_PRODUCT")
            self.assertEqual(evidence.classification, DataClassification.DERIVED)
            self.assertIsNotNone(snapshot_row)
            assert snapshot_row is not None
            self.assertEqual(snapshot_row["version"], field.boundary_version)
            self.assertEqual(snapshot_row["geometry_checksum"], field.boundary_checksum)

            with self.store.tenant_transaction(tenant.id):
                persisted_delta = (
                    application.geospatial.repository.find_temporal_delta(
                        tenant.id, baseline.id, target.id, field.id
                    )
                )
            self.assertIsNotNone(persisted_delta)
            assert persisted_delta is not None
            self.assertTrue(
                application.geospatial._has_valid_field_delta_provenance(
                    persisted_delta, field
                ),
                persisted_delta.parameters,
            )
            self.assertTrue(
                application.geospatial._has_valid_temporal_delta_provenance(
                    persisted_delta, baseline, target
                ),
                persisted_delta.parameters,
            )
            comparison = application.geospatial.compare_products(
                tenant.id,
                property_item.id,
                baseline.id,
                target.id,
                field.id,
            )
            unscoped_comparison = application.geospatial.compare_products(
                tenant.id, property_item.id, baseline.id, target.id
            )
            self.assertEqual(comparison["status"], "READY", comparison)
            self.assertEqual(comparison["delta"].id, delta.id)
            self.assertEqual(comparison["comparable_valid_pixels"], 30)
            self.assertNotEqual(unscoped_comparison.get("delta"), delta)

            rule = application.create_rule(
                RuleDefinition(
                    new_id(),
                    tenant.id,
                    1,
                    "synthetic field NDVI decline rule",
                    RuleAuthority.REGRA_AGRONOMICA,
                    "ndvi_temporal_delta_mean",
                    "<",
                    -0.1,
                    "NDVI",
                    "HIGH",
                    "ACTIVE",
                    "integration-approver",
                    "2025-01-01T00:00:00+00:00",
                    scope_type="FIELD",
                    scope_field_id=field.id,
                )
            )
            decision = application.evaluate_temporal_delta(
                tenant.id, property_item.id, delta.id, actor="integration-operator"
            )
            self.assertEqual(decision.decision.status, DecisionStatus.ACTIONABLE)
            self.assertEqual(decision.decision.rule_id, rule.id)
            self.assertEqual(decision.decision.selected_rule_scope_type, "FIELD")
            self.assertEqual(decision.decision.subject_field_id, field.id)
            self.assertEqual(
                decision.decision.subject_field_boundary_version,
                field.boundary_version,
            )
            self.assertEqual(
                decision.decision.subject_field_boundary_checksum,
                field.boundary_checksum,
            )
            self.assertEqual(decision.decision.evidence_ids, [evidence.id])
            self.assertIsNotNone(decision.alert)
            self.assertIsNotNone(decision.action)


if __name__ == "__main__":
    unittest.main()
