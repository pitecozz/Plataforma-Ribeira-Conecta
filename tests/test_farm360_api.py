"""Farm 360 read API tests use explicitly synthetic_test_data raster bytes only."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin
from shapely.geometry import Polygon, mapping

from ribeira_platform.api import Settings, create_app
from ribeira_platform.business import Asset, CommercialClassification
from ribeira_platform.epistemology import DataClassification, RuleAuthority
from ribeira_platform.geospatial import (
    DerivedProductDependency,
    ProviderSearchResult,
    SatelliteCollection,
    SatelliteSearchRequest,
)
from ribeira_platform.geospatial_service import GeospatialApplication
from ribeira_platform.iam import AuthContext, DevelopmentIdentityProvider
from ribeira_platform.object_storage import LocalObjectStorage
from ribeira_platform.models import Evidence, RuleDefinition, new_id
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.storage import SQLiteStore


class SyntheticProvider:
    def get_collection(self, collection_id: str) -> SatelliteCollection:
        return SatelliteCollection(
            "",
            "COPERNICUS_CDSE",
            collection_id,
            "synthetic_test_data",
            None,
            "L2A",
            "10m",
            {},
            {},
            "other",
            "1.1.0",
            {"synthetic_test_data": True},
        )

    def search(
        self, request: SatelliteSearchRequest, aoi_geojson: dict
    ) -> ProviderSearchResult:
        item = {
            "type": "Feature",
            "stac_version": "1.1.0",
            "id": "SYNTHETIC_TEST_SCENE",
            "geometry": aoi_geojson,
            "bbox": [0, 0, 1, 1],
            "properties": {"datetime": "2025-01-15T10:00:00Z", "eo:cloud_cover": 12.0},
            "assets": {
                "B04_10m": {
                    "href": "local://assets/red.tif",
                    "roles": ["reflectance"],
                    "title": "Red (band 4) - 10m",
                },
                "B08_10m": {
                    "href": "local://assets/nir.tif",
                    "roles": ["reflectance"],
                    "title": "NIR 1 (band 8) - 10m",
                },
            },
        }
        return ProviderSearchResult([item], [{"features": [item]}])


class Farm360ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = SQLiteStore()
        self.storage = LocalObjectStorage(Path(self.temporary.name) / "objects")
        self._write_synthetic_test_rasters()
        provider = SyntheticProvider()
        self.application = RibeiraApplication(
            self.store, geospatial_provider=provider, object_storage=self.storage
        )
        self.application.geospatial = GeospatialApplication(
            self.store, provider, self.storage
        )
        self.tenant = self.application.create_tenant("Synthetic test tenant")
        self.other_tenant = self.application.create_tenant("Other test tenant")
        polygon = mapping(
            Polygon(
                [(0.05, 0.05), (0.95, 0.05), (0.95, 0.95), (0.05, 0.95), (0.05, 0.05)]
            )
        )
        self.property = self.application.create_property(
            self.tenant.id, "TEST_AOI_ONLY", polygon, "EPSG:4326"
        )
        search = self.application.geospatial.search_satellite(
            self.tenant.id,
            SatelliteSearchRequest(
                self.property.id,
                "sentinel-2-l2a",
                "2025-01-01T00:00:00Z",
                "2025-02-01T00:00:00Z",
            ),
        )
        job = self.application.geospatial.create_ndvi_job(
            self.tenant.id, self.property.id, search.search.id
        )
        result = self.application.geospatial.run_ndvi_job(self.tenant.id, job.id)
        assert result.product is not None
        self.product = result.product
        settings = Settings("test", "sqlite", None, (), "development", 1_000_000)
        self.client = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "admin",
                    AuthContext(
                        "admin",
                        None,
                        roles=frozenset({"PLATFORM_ADMIN"}),
                        is_platform_admin=True,
                    ),
                ),
                settings=settings,
            )
        )
        self.tenant_client = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "tenant-b",
                    AuthContext(
                        "tenant-b", self.other_tenant.id, roles=frozenset({"VIEWER"})
                    ),
                ),
                settings=settings,
            )
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _write_synthetic_test_rasters(self) -> None:
        profile = {
            "driver": "GTiff",
            "height": 4,
            "width": 4,
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:4326",
            "transform": from_origin(0, 1, 0.25, 0.25),
            "nodata": -9999.0,
        }
        for key, value in (("red.tif", 1.0), ("nir.tif", 3.0)):
            path = Path(self.temporary.name) / "objects" / "assets" / key
            path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(path, "w", **profile) as dataset:
                dataset.write(np.full((1, 4, 4), value, dtype="float32"))

    def test_property_scene_product_and_provenance_are_safe_and_tenant_scoped(
        self,
    ) -> None:
        headers = {"Authorization": "Bearer admin"}
        property_response = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}",
            headers=headers,
        )
        scenes = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/scenes",
            headers=headers,
        )
        products = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/derived-products",
            headers=headers,
        )
        provenance = self.client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/{self.product.id}/provenance",
            headers=headers,
        )
        self.assertEqual(property_response.json()["data_status"], "READY")
        self.assertEqual(scenes.json()["items"][0]["scene_id"], "SYNTHETIC_TEST_SCENE")
        self.assertEqual(
            products.json()["items"][0]["checksum"], self.product.output_checksum
        )
        self.assertIn(
            "B04_10m", [asset["asset_key"] for asset in provenance.json()["assets"]]
        )
        self.assertNotIn("local://", provenance.text)
        denied = self.tenant_client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/{self.product.id}/provenance",
            headers={"Authorization": "Bearer tenant-b"},
        )
        self.assertEqual(denied.status_code, 403)

    def test_asset_registration_requires_factual_source_and_observation_time(
        self,
    ) -> None:
        payload = {
            "asset_type": "RAIN_GAUGE",
            "name": "Gauge registered through API",
            "status": "ACTIVE",
            "property_id": self.property.id,
            "geometry": {"type": "Point", "coordinates": [0.5, 0.5]},
            "geometry_crs": "EPSG:4326",
            "source_reference": "synthetic_test_data installation record",
            "observed_at": "2026-09-24T12:00:00+00:00",
            "classification": "MANUAL_CONFIRMED",
        }
        created = self.client.post(
            f"/v1/tenants/{self.tenant.id}/assets",
            headers={"Authorization": "Bearer admin"},
            json=payload,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(
            created.json()["source_reference"], payload["source_reference"]
        )
        self.assertEqual(created.json()["observed_at"], payload["observed_at"])
        self.assertIsNotNone(created.json()["evidence_id"])

        blank_source = {**payload, "source_reference": "   "}
        blank_rejected = self.client.post(
            f"/v1/tenants/{self.tenant.id}/assets",
            headers={"Authorization": "Bearer admin"},
            json=blank_source,
        )
        self.assertEqual(blank_rejected.status_code, 422)
        self.assertEqual(blank_rejected.json()["error"]["code"], "VALIDATION_ERROR")

        for missing_field in ("source_reference", "observed_at"):
            incomplete = {
                key: value for key, value in payload.items() if key != missing_field
            }
            rejected = self.client.post(
                f"/v1/tenants/{self.tenant.id}/assets",
                headers={"Authorization": "Bearer admin"},
                json=incomplete,
            )
            self.assertEqual(rejected.status_code, 422)
            self.assertEqual(rejected.json()["error"]["code"], "VALIDATION_ERROR")
            self.assertIn(missing_field, str(rejected.json()["error"]["fields"]))

    def test_property_asset_inventory_is_tenant_scoped_and_preserves_context(
        self,
    ) -> None:
        asset = Asset(
            new_id(),
            self.tenant.id,
            "RAIN_GAUGE",
            "Gauge A",
            None,
            "ACTIVE",
            self.property.id,
            None,
            CommercialClassification.MANUAL_CONFIRMED,
            {"type": "Point", "coordinates": [0.5, 0.5]},
            "EPSG:4326",
            "manual installation record",
            "2026-09-21T12:00:00+00:00",
            {"calibration_state": "UNKNOWN"},
        )
        self.application.business.register_asset(asset, actor="operator")
        response = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/assets",
            headers={"Authorization": "Bearer admin"},
        )
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["id"], asset.id)
        self.assertEqual(item["classification"], "MANUAL_CONFIRMED")
        self.assertIsNotNone(item["evidence_id"])
        evidence = self.store.evidence_for_reference(self.tenant.id, asset.id)
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(item["evidence_id"], evidence.id)
        self.assertEqual(item["context"]["calibration_state"], "UNKNOWN")
        denied = self.tenant_client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/assets",
            headers={"Authorization": "Bearer tenant-b"},
        )
        self.assertEqual(denied.status_code, 403)

    def test_ndvi_enqueue_is_202_and_never_runs_in_the_http_request(self) -> None:
        polygon = mapping(
            Polygon([(0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.1, 0.2), (0.1, 0.1)])
        )
        queued_property = self.application.create_property(
            self.tenant.id, "TEST_AOI_ONLY_ASYNC", polygon, "EPSG:4326"
        )
        search = self.application.geospatial.search_satellite(
            self.tenant.id,
            SatelliteSearchRequest(
                queued_property.id,
                "sentinel-2-l2a",
                "2025-01-01T00:00:00Z",
                "2025-02-01T00:00:00Z",
            ),
        )
        headers = {"Authorization": "Bearer admin"}
        response = self.client.post(
            f"/v1/tenants/{self.tenant.id}/properties/{queued_property.id}/ndvi-jobs",
            headers=headers,
            json={"search_id": search.search.id},
        )
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "QUEUED")
        self.assertEqual(body["attempt"], 0)
        self.assertIsNone(body["output_product_id"])
        fetched = self.client.get(
            f"/v1/tenants/{self.tenant.id}/processing-jobs/{body['id']}",
            headers=headers,
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["status"], "QUEUED")
        compatibility = self.client.post(
            f"/v1/tenants/{self.tenant.id}/processing-jobs/{body['id']}/run",
            headers=headers,
        )
        self.assertEqual(compatibility.status_code, 202)
        self.assertEqual(compatibility.json()["status"], "QUEUED")

    def test_tile_is_png_and_invalid_or_unknown_resources_are_not_served(self) -> None:
        headers = {"Authorization": "Bearer admin"}
        tile = self.client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/{self.product.id}/tiles/0/0/0",
            headers=headers,
        )
        self.assertEqual(tile.status_code, 200)
        self.assertEqual(tile.headers["content-type"], "image/png")
        self.assertEqual(tile.headers["cache-control"], "private, max-age=300")
        self.assertTrue(tile.content.startswith(b"\x89PNG"))
        invalid = self.client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/{self.product.id}/tiles/99/0/0",
            headers=headers,
        )
        self.assertEqual(invalid.status_code, 422)
        missing = self.client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/not-a-product/tiles/0/0/0",
            headers=headers,
        )
        self.assertEqual(missing.status_code, 404)
        traversal = self.client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/..%2F..%2Fetc%2Fpasswd/tiles/0/0/0",
            headers=headers,
        )
        self.assertEqual(traversal.status_code, 404)
        no_raster = replace(
            self.product,
            id=new_id(),
            processing_job_id=new_id(),
            output_reference=None,
            output_checksum=None,
        )
        self.application.geospatial.repository.create_derived_product(no_raster)
        unavailable = self.client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/{no_raster.id}/tiles/0/0/0",
            headers=headers,
        )
        self.assertEqual(unavailable.status_code, 409)

    def test_timeline_is_ascending_and_comparison_is_non_causal_aggregate(self) -> None:
        original_scene = self.application.geospatial.repository.get_scene(
            self.tenant.id, self.product.scene_id
        )
        original_job = self.application.geospatial.get_job(
            self.tenant.id, self.product.processing_job_id
        )
        assert original_scene is not None
        assert original_job is not None
        later_scene = replace(
            original_scene,
            id=new_id(),
            external_item_id="SYNTHETIC_TEST_SCENE_LATER",
            acquisition_datetime="2025-02-15T10:00:00Z",
        )
        later_job = replace(
            original_job,
            id=new_id(),
            scene_id=later_scene.id,
            idempotency_key=new_id(),
            output_product_id=None,
        )
        later_product = replace(
            self.product,
            id=new_id(),
            scene_id=later_scene.id,
            processing_job_id=later_job.id,
            output_checksum="synthetic_test_checksum_later",
            statistics=replace(self.product.statistics, mean=Decimal("0.7")),
        )
        repository = self.application.geospatial.repository
        repository.upsert_scene(later_scene)
        repository.create_job(later_job)
        repository.create_derived_product(later_product)
        repository.mark_job(
            self.tenant.id,
            later_job.id,
            original_job.status,
            output_product_id=later_product.id,
        )
        headers = {"Authorization": "Bearer admin"}
        timeline = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/timeline",
            headers=headers,
        )
        self.assertEqual(timeline.status_code, 200)
        entries = timeline.json()["items"]
        self.assertEqual(timeline.json()["order"], "acquisition_datetime_asc")
        self.assertEqual(
            [entry["scene_id"] for entry in entries],
            [
                "SYNTHETIC_TEST_SCENE",
                "SYNTHETIC_TEST_SCENE_LATER",
            ],
        )
        comparison = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/temporal-comparison",
            params={
                "baseline_product_id": self.product.id,
                "target_product_id": later_product.id,
            },
            headers=headers,
        )
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(comparison.json()["status"], "READY")
        self.assertEqual(comparison.json()["comparison"]["delta_mean"], "0.2")
        self.assertEqual(
            comparison.json()["comparison"]["comparable_valid_pixels"], None
        )
        same = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/temporal-comparison",
            params={
                "baseline_product_id": self.product.id,
                "target_product_id": self.product.id,
            },
            headers=headers,
        )
        self.assertEqual(same.json()["status"], "DADO_INSUFICIENTE")
        empty_property = self.application.create_property(
            self.tenant.id, "TEST_AOI_EMPTY", None, None
        )
        empty = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{empty_property.id}/timeline",
            headers=headers,
        )
        self.assertEqual(empty.json()["items"], [])

    def test_temporal_endpoints_do_not_cross_tenant_or_property_boundaries(
        self,
    ) -> None:
        headers = {"Authorization": "Bearer admin"}
        original_job = self.application.geospatial.get_job(
            self.tenant.id, self.product.processing_job_id
        )
        assert original_job is not None
        wrong_type_job = replace(
            original_job,
            id=new_id(),
            idempotency_key=new_id(),
            output_product_id=None,
        )
        wrong_type = replace(
            self.product,
            id=new_id(),
            processing_job_id=wrong_type_job.id,
            product_type="EVI",
            output_checksum="synthetic_test_wrong_type",
        )
        self.application.geospatial.repository.create_job(wrong_type_job)
        self.application.geospatial.repository.create_derived_product(wrong_type)
        wrong_type_response = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/temporal-comparison",
            params={
                "baseline_product_id": self.product.id,
                "target_product_id": wrong_type.id,
            },
            headers=headers,
        )
        self.assertEqual(wrong_type_response.status_code, 422)
        nonexistent = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/temporal-comparison",
            params={
                "baseline_product_id": self.product.id,
                "target_product_id": "not-a-product",
            },
            headers=headers,
        )
        self.assertEqual(nonexistent.status_code, 404)
        other_property = self.application.create_property(
            self.tenant.id, "TEST_AOI_OTHER", None, None
        )
        cross_property = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{other_property.id}/temporal-comparison",
            params={
                "baseline_product_id": self.product.id,
                "target_product_id": self.product.id,
            },
            headers=headers,
        )
        self.assertEqual(cross_property.status_code, 422)
        cross_tenant_timeline = self.tenant_client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/timeline",
            headers={"Authorization": "Bearer tenant-b"},
        )
        self.assertEqual(cross_tenant_timeline.status_code, 403)
        cross_tenant_comparison = self.tenant_client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/temporal-comparison",
            params={
                "baseline_product_id": self.product.id,
                "target_product_id": self.product.id,
            },
            headers={"Authorization": "Bearer tenant-b"},
        )
        self.assertEqual(cross_tenant_comparison.status_code, 403)

    def test_persisted_delta_is_exposed_as_pixel_aligned_and_tenant_scoped(
        self,
    ) -> None:
        """Synthetic test data exercises the API contract, never live CDSE data."""
        repository = self.application.geospatial.repository
        original_job = self.application.geospatial.get_job(
            self.tenant.id, self.product.processing_job_id
        )
        original_scene = repository.get_scene(self.tenant.id, self.product.scene_id)
        assert original_job is not None
        assert original_scene is not None
        quality_mask = {
            "policy_id": "SENTINEL2_SCL_CONSERVATIVE_V1",
            "version": 1,
            "scl_asset_key": "SCL_20m",
            "accepted_classes": [4, 5, 6],
            "excluded_classes": [0, 1, 2, 3, 7, 8, 9, 10, 11],
            "optional_policy_dependent_classes": [7],
            "scl_asset_id": "synthetic_test_scl",
            "scl_checksum": "synthetic_test_scl_checksum",
            "valid_before_scl": self.product.statistics.valid_count,
            "discarded_by_scl": 0,
            "valid_after_scl": self.product.statistics.valid_count,
        }
        baseline_job = replace(
            original_job,
            id=new_id(),
            job_type="QUALITY_MASKED_NDVI",
            idempotency_key=new_id(),
            output_product_id=None,
        )
        baseline = replace(
            self.product,
            id=new_id(),
            processing_job_id=baseline_job.id,
            product_type="NDVI_QUALITY_MASKED",
            output_checksum="synthetic_test_baseline",
            parameters={"quality_mask": quality_mask},
        )
        target_scene = replace(
            original_scene,
            id=new_id(),
            external_item_id="SYNTHETIC_TEST_SCENE_DELTA_TARGET",
            acquisition_datetime="2025-02-15T10:00:00Z",
        )
        target_job = replace(
            original_job,
            id=new_id(),
            scene_id=target_scene.id,
            idempotency_key=new_id(),
            output_product_id=None,
        )
        target = replace(
            baseline,
            id=new_id(),
            scene_id=target_scene.id,
            processing_job_id=target_job.id,
            output_checksum="synthetic_test_target",
            statistics=replace(baseline.statistics, mean=Decimal("0.7")),
        )
        delta_job = replace(
            original_job,
            id=new_id(),
            job_type="TEMPORAL_DELTA",
            idempotency_key=new_id(),
            output_product_id=None,
        )
        delta = replace(
            baseline,
            id=new_id(),
            processing_job_id=delta_job.id,
            product_type="NDVI_DELTA",
            algorithm_id="NDVI_TEMPORAL_DELTA",
            algorithm_version="1.0.0",
            formula="NDVI_target - NDVI_baseline",
            output_checksum="synthetic_test_delta",
            statistics=replace(
                baseline.statistics,
                minimum=Decimal("-0.1"),
                maximum=Decimal("0.2"),
                mean=Decimal("0.05"),
                median=Decimal("0.04"),
                valid_count=12,
                coverage_percentage=Decimal("75.0"),
            ),
            parameters={
                "baseline_product_id": baseline.id,
                "target_product_id": target.id,
                "baseline_checksum": baseline.output_checksum,
                "target_checksum": target.output_checksum,
                "alignment": {
                    "status": "IDENTICAL_GRID",
                    "target_grid": "baseline",
                    "resampling": None,
                },
                "quality_mask_policies": [quality_mask, quality_mask],
            },
        )
        repository.create_job(baseline_job)
        repository.create_derived_product(baseline)
        repository.mark_job(
            self.tenant.id,
            baseline_job.id,
            original_job.status,
            output_product_id=baseline.id,
        )
        repository.upsert_scene(target_scene)
        repository.create_job(target_job)
        repository.create_derived_product(target)
        repository.mark_job(
            self.tenant.id,
            target_job.id,
            original_job.status,
            output_product_id=target.id,
        )
        repository.create_job(delta_job)
        repository.create_derived_product(delta)
        repository.create_product_dependency(
            DerivedProductDependency(
                self.tenant.id, delta.id, baseline.id, "BASELINE_NDVI"
            )
        )
        repository.create_product_dependency(
            DerivedProductDependency(self.tenant.id, delta.id, target.id, "TARGET_NDVI")
        )
        repository.mark_job(
            self.tenant.id,
            delta_job.id,
            original_job.status,
            output_product_id=delta.id,
        )
        evidence = Evidence(
            new_id(),
            self.tenant.id,
            "DERIVED_PRODUCT",
            delta.id,
            DataClassification.DERIVED,
            None,
            None,
            "NDVI_TEMPORAL_DELTA 1.0.0: NDVI_target - NDVI_baseline",
            delta.limitations,
        )
        repository.create_evidence(evidence)

        comparison = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/temporal-comparison",
            params={
                "baseline_product_id": baseline.id,
                "target_product_id": target.id,
            },
            headers={"Authorization": "Bearer admin"},
        )
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(
            comparison.json()["comparison"]["classification"], "PIXEL_ALIGNED_DELTA"
        )
        self.assertEqual(comparison.json()["comparison"]["delta_product_id"], delta.id)
        self.assertEqual(comparison.json()["comparison"]["comparable_valid_pixels"], 12)

        self.application.create_rule(
            RuleDefinition(
                new_id(),
                self.tenant.id,
                3,
                "Synthetic NDVI delta inspection threshold",
                RuleAuthority.REGRA_AGRONOMICA,
                "ndvi_temporal_delta_mean",
                ">=",
                0.04,
                "index_delta",
                "MEDIUM",
                "ACTIVE",
                "synthetic-reviewer",
                "2026-01-01T00:00:00+00:00",
                scope_type="PROPERTY",
                scope_property_id=self.property.id,
            )
        )
        evaluation_path = (
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}"
            f"/temporal-deltas/{delta.id}/evaluate"
        )
        evaluation = self.client.post(
            evaluation_path, headers={"Authorization": "Bearer admin"}
        )
        self.assertEqual(evaluation.status_code, 200)
        evaluated = evaluation.json()
        self.assertEqual(evaluated["decision"]["status"], "ACTIONABLE")
        self.assertEqual(evaluated["decision"]["evidence_ids"], [evidence.id])
        self.assertEqual(evaluated["decision"]["rule_version"], 3)
        self.assertEqual(evaluated["decision"]["selected_rule_scope_type"], "PROPERTY")
        self.assertFalse(evaluated["decision"]["recommended_action"]["automated"])
        self.assertEqual(
            evaluated["action"]["action_type"],
            "targeted field inspection recommendation",
        )
        self.assertIsNotNone(evaluated["alert"])
        audit = self.store.connection.execute(
            "SELECT * FROM audit_log WHERE tenant_id=? AND entity_id=?",
            (self.tenant.id, evaluated["decision"]["id"]),
        ).fetchone()
        self.assertIsNotNone(audit)

        other_property = self.application.create_property(
            self.tenant.id, "OTHER_SYNTHETIC_AOI", None, None
        )
        wrong_property = self.client.post(
            f"/v1/tenants/{self.tenant.id}/properties/{other_property.id}"
            f"/temporal-deltas/{delta.id}/evaluate",
            headers={"Authorization": "Bearer admin"},
        )
        self.assertEqual(wrong_property.status_code, 422)
        cross_tenant = self.tenant_client.post(
            evaluation_path, headers={"Authorization": "Bearer tenant-b"}
        )
        self.assertEqual(cross_tenant.status_code, 403)
        wrong_type = self.client.post(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}"
            f"/temporal-deltas/{baseline.id}/evaluate",
            headers={"Authorization": "Bearer admin"},
        )
        self.assertEqual(wrong_type.status_code, 422)

        tile = self.client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/{delta.id}/tiles/0/0/0",
            headers={"Authorization": "Bearer admin"},
        )
        self.assertEqual(tile.status_code, 200)
        self.assertEqual(tile.headers["content-type"], "image/png")

        no_trigger_rule = self.store.connection.execute(
            "SELECT id FROM rules WHERE tenant_id=? AND metric=?",
            (self.tenant.id, "ndvi_temporal_delta_mean"),
        ).fetchone()
        assert no_trigger_rule is not None
        self.store.connection.execute(
            "UPDATE rules SET threshold=? WHERE tenant_id=? AND id=?",
            (0.06, self.tenant.id, no_trigger_rule["id"]),
        )
        self.store.connection.commit()
        no_trigger = self.client.post(
            evaluation_path, headers={"Authorization": "Bearer admin"}
        )
        self.assertEqual(no_trigger.status_code, 200)
        self.assertEqual(no_trigger.json()["decision"]["status"], "NO_TRIGGER")
        self.assertIsNone(no_trigger.json()["alert"])
        self.assertIsNone(no_trigger.json()["action"])

        malformed_parameters = dict(delta.parameters)
        malformed_parameters["alignment"] = {"status": "IDENTICAL_GRID"}
        self.application.store.connection.execute(
            "UPDATE derived_product SET parameters=? WHERE tenant_id=? AND id=?",
            (
                json.dumps(malformed_parameters),
                self.tenant.id,
                delta.id,
            ),
        )
        self.application.store.connection.commit()
        invalid_provenance = self.client.post(
            evaluation_path, headers={"Authorization": "Bearer admin"}
        )
        self.assertEqual(invalid_provenance.status_code, 200)
        self.assertEqual(
            invalid_provenance.json()["decision"]["status"], "INCONCLUSIVE"
        )
        self.assertIsNone(invalid_provenance.json()["alert"])
        self.assertIsNone(invalid_provenance.json()["action"])
        malformed = self.client.get(
            f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/temporal-comparison",
            params={
                "baseline_product_id": baseline.id,
                "target_product_id": target.id,
            },
            headers={"Authorization": "Bearer admin"},
        )
        self.assertEqual(malformed.status_code, 200)
        self.assertEqual(malformed.json()["status"], "READY")
        self.assertEqual(
            malformed.json()["comparison"]["classification"], "DERIVED_AGGREGATE"
        )
        self.assertIsNone(malformed.json()["comparison"]["delta_product_id"])
        self.assertIsNone(malformed.json()["comparison"]["comparable_valid_pixels"])
        self.assertIsNone(
            malformed.json()["comparison"]["comparable_coverage_percentage"]
        )
        self.assertEqual(
            Decimal(malformed.json()["comparison"]["delta_mean"]),
            target.statistics.mean - baseline.statistics.mean,
        )
        denied = self.tenant_client.get(
            f"/v1/tenants/{self.tenant.id}/derived-products/{delta.id}/tiles/0/0/0",
            headers={"Authorization": "Bearer tenant-b"},
        )
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
