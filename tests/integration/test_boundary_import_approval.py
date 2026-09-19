"""PostgreSQL boundary-import workflow uses synthetic_test_data only."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import psycopg
from fastapi.testclient import TestClient

from ribeira_platform.api import Settings, create_app
from ribeira_platform.epistemology import DataClassification
from ribeira_platform.iam import AuthContext, DevelopmentIdentityProvider
from ribeira_platform.object_storage import LocalObjectStorage
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import BoundaryImportConflict, RibeiraApplication
from tests.integration.tenant_cleanup import delete_test_tenants


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")
MIGRATION_DATABASE_URL = os.getenv("RIBEIRA_TEST_MIGRATION_DATABASE_URL")
BOUNDARY_V1 = {
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
BOUNDARY_V2 = {
    "type": "Polygon",
    "coordinates": [
        [
            [-47.0, -24.0],
            [-46.98, -24.0],
            [-46.98, -24.01],
            [-47.0, -24.01],
            [-47.0, -24.0],
        ]
    ],
}


@unittest.skipUnless(
    DATABASE_URL and MIGRATION_DATABASE_URL, "PostgreSQL integration URLs are required"
)
class BoundaryImportApprovalPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(
            self.store,
            object_storage=LocalObjectStorage(Path(self.temporary.name) / "objects"),
        )
        self.tenant_ids: list[str] = []

    def tearDown(self) -> None:
        try:
            delete_test_tenants(self.tenant_ids)
        finally:
            self.store.close()
            self.temporary.cleanup()

    def tenant(self, name: str):
        value = self.application.create_tenant(name)
        self.tenant_ids.append(value.id)
        return value

    @staticmethod
    def payload(boundary: dict[str, object] = BOUNDARY_V2) -> bytes:
        return json.dumps(
            {
                "type": "Feature",
                "properties": {"synthetic_test_data": True},
                "geometry": boundary,
            },
            separators=(",", ":"),
        ).encode()

    def property(self, tenant_id: str):
        return self.application.create_property(
            tenant_id,
            "SYNTHETIC_TEST_PROPERTY",
            BOUNDARY_V1,
            "EPSG:4326",
            boundary_source="synthetic test source",
            actor="creator-a",
        )

    def create_import(
        self, tenant_id: str, property_id: str, actor: str = "importer-a"
    ):
        return self.application.create_boundary_import(
            tenant_id,
            property_id,
            original_filename="synthetic_test_data.geojson",
            payload=self.payload(),
            declared_crs="EPSG:4326",
            boundary_source="synthetic imported survey",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor=actor,
        )

    def test_import_preview_approval_rejection_and_rls(self) -> None:
        tenant_a = self.tenant("Synthetic import tenant A")
        tenant_b = self.tenant("Synthetic import tenant B")
        property_a = self.property(tenant_a.id)
        property_b = self.property(tenant_b.id)
        created = self.create_import(tenant_a.id, property_a.id)
        self.assertEqual(created.status, "NEEDS_REVIEW")
        self.assertTrue(
            created.object_reference.startswith("local://boundary-imports/")
        )
        self.assertNotEqual(created.file_sha256, created.geometry_checksum)
        self.assertEqual(
            self.application.get_boundary_import(tenant_a.id, created.id).status,
            "NEEDS_REVIEW",
        )
        self.assertEqual(
            self.application.list_boundary_imports(tenant_a.id, property_a.id)[0].id,
            created.id,
        )
        with self.store.tenant_transaction(tenant_a.id):
            current = self.store.get_property(tenant_a.id, property_a.id)
            self.assertEqual(current.boundary_checksum, property_a.boundary_checksum)
            self.assertIsNone(
                self.store.get_boundary_import(
                    tenant_a.id, "00000000-0000-0000-0000-000000000000"
                )
            )
        preview = self.application.preview_boundary_import(tenant_a.id, created.id)
        self.assertEqual(
            preview["current_boundary_checksum"], property_a.boundary_checksum
        )
        self.assertIsNotNone(preview["absolute_area_delta_hectares"])
        approved = self.application.approve_boundary_import(
            tenant_a.id,
            created.id,
            reviewer="reviewer-b",
            reason="synthetic review",
            expected_property_checksum=property_a.boundary_checksum or "",
        )
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(approved.approved_boundary_version, 2)
        with self.store.tenant_transaction(tenant_a.id):
            changed = self.store.get_property(tenant_a.id, property_a.id)
            versions = self.store.connection.execute(
                "SELECT version FROM property_boundary_version WHERE property_id=%s ORDER BY version",
                (property_a.id,),
            ).fetchall()
        self.assertNotEqual(changed.boundary_checksum, property_a.boundary_checksum)
        self.assertEqual([row["version"] for row in versions], [1, 2])
        rejected = self.create_import(tenant_a.id, property_a.id, actor="importer-c")
        same_checksum = changed.boundary_checksum
        rejected = self.application.reject_boundary_import(
            tenant_a.id,
            rejected.id,
            reviewer="reviewer-d",
            reason="synthetic rejection",
        )
        self.assertEqual(rejected.status, "REJECTED")
        with self.store.tenant_transaction(tenant_a.id):
            self.assertEqual(
                self.store.get_property(tenant_a.id, property_a.id).boundary_checksum,
                same_checksum,
            )
            self.assertEqual(
                self.store.connection.execute(
                    "SELECT count(*) AS count FROM property_boundary_version WHERE property_id=%s",
                    (property_a.id,),
                ).fetchone()["count"],
                2,
            )
            self.assertEqual(
                self.store.connection.execute(
                    "SELECT count(*) AS count FROM boundary_import WHERE property_id=%s",
                    (property_b.id,),
                ).fetchone()["count"],
                0,
            )
        with self.store.tenant_transaction(tenant_b.id):
            self.assertIsNone(self.store.get_boundary_import(tenant_b.id, created.id))
        with self.assertRaises(LookupError):
            self.application.preview_boundary_import(tenant_b.id, created.id)

    def test_stale_and_double_approval_do_not_overwrite(self) -> None:
        tenant = self.tenant("Synthetic import concurrency tenant")
        property_item = self.property(tenant.id)
        imported = self.create_import(tenant.id, property_item.id)
        self.application.update_property_boundary(
            tenant.id,
            property_item.id,
            BOUNDARY_V2,
            "EPSG:4326",
            "synthetic external revision",
            DataClassification.MANUAL_CONFIRMED,
            "synthetic changed while reviewing",
            "other-reviewer",
            property_item.boundary_checksum,
        )
        with self.assertRaises(BoundaryImportConflict):
            self.application.approve_boundary_import(
                tenant.id,
                imported.id,
                reviewer="reviewer-b",
                reason="stale synthetic review",
                expected_property_checksum=property_item.boundary_checksum or "",
            )

        property_item = self.property(tenant.id)
        imported = self.create_import(tenant.id, property_item.id)
        barrier = Barrier(2)

        def approve(actor: str) -> str:
            store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
            try:
                application = RibeiraApplication(
                    store,
                    object_storage=LocalObjectStorage(
                        Path(self.temporary.name) / "objects"
                    ),
                )
                barrier.wait(timeout=5)
                application.approve_boundary_import(
                    tenant.id,
                    imported.id,
                    reviewer=actor,
                    reason="synthetic concurrent review",
                    expected_property_checksum=property_item.boundary_checksum or "",
                )
                return "approved"
            except BoundaryImportConflict:
                return "conflict"
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(approve, ["reviewer-a", "reviewer-b"]))
        self.assertEqual(sorted(outcomes), ["approved", "conflict"])
        with self.store.tenant_transaction(tenant.id):
            rows = self.store.connection.execute(
                "SELECT status,approved_boundary_version FROM boundary_import WHERE id=%s",
                (imported.id,),
            ).fetchall()
            versions = self.store.connection.execute(
                "SELECT version FROM property_boundary_version WHERE property_id=%s ORDER BY version",
                (property_item.id,),
            ).fetchall()
        self.assertEqual(rows[0]["status"], "APPROVED")
        self.assertEqual([row["version"] for row in versions], [1, 2])

    def test_failed_parse_and_unknown_crs_preserve_file_without_changing_property(
        self,
    ) -> None:
        tenant = self.tenant("Synthetic failed import tenant")
        property_item = self.property(tenant.id)
        failed = self.application.create_boundary_import(
            tenant.id,
            property_item.id,
            original_filename="synthetic_test_data.json",
            payload=b"<kml>not GeoJSON</kml>",
            declared_crs="EPSG:4326",
            boundary_source="synthetic mismatch",
            classification=DataClassification.UNKNOWN,
            actor="importer-a",
        )
        self.assertEqual(failed.status, "FAILED")
        self.assertIn("INVALID_GEOJSON", failed.warnings)
        self.assertTrue(
            Path(
                self.application.object_storage.read_local_path(failed.object_reference)
            ).is_file()
        )
        unknown = self.application.create_boundary_import(
            tenant.id,
            property_item.id,
            original_filename="synthetic_test_data.geojson",
            payload=self.payload(),
            declared_crs=None,
            boundary_source="synthetic unknown CRS",
            classification=DataClassification.UNKNOWN,
            actor="importer-b",
        )
        self.assertEqual(unknown.status, "NEEDS_REVIEW")
        self.assertIsNone(unknown.geometry_geojson)
        with self.assertRaises(BoundaryImportConflict):
            self.application.approve_boundary_import(
                tenant.id,
                unknown.id,
                reviewer="reviewer-c",
                reason="cannot approve CRS unknown",
                expected_property_checksum=property_item.boundary_checksum or "",
            )
        with self.store.tenant_transaction(tenant.id):
            self.assertEqual(
                self.store.get_property(tenant.id, property_item.id).boundary_checksum,
                property_item.boundary_checksum,
            )
        with self.assertRaises(ValueError):
            self.application.create_boundary_import(
                tenant.id,
                property_item.id,
                original_filename="synthetic_test_data.kml",
                payload=self.payload(),
                declared_crs="EPSG:4326",
                boundary_source="synthetic unsupported format",
                classification=DataClassification.UNKNOWN,
                actor="importer-d",
            )

    def test_tenant_scoped_api_never_returns_object_storage_paths(self) -> None:
        tenant = self.tenant("Synthetic import API tenant")
        property_item = self.property(tenant.id)
        settings = Settings(
            "test", "postgres", DATABASE_URL, (), "development", 1_000_000
        )
        importer = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "synthetic-importer",
                    AuthContext(
                        "synthetic-importer",
                        None,
                        roles=frozenset({"PLATFORM_ADMIN"}),
                        is_platform_admin=True,
                    ),
                ),
                settings=settings,
            )
        )
        response = importer.post(
            f"/v1/tenants/{tenant.id}/properties/{property_item.id}/boundary-imports",
            content=self.payload(),
            headers={
                "Authorization": "Bearer synthetic-importer",
                "X-Boundary-Filename": "synthetic_test_data.geojson",
                "X-Boundary-CRS": "EPSG:4326",
                "X-Boundary-Source": "synthetic API source",
                "X-Boundary-Classification": "MANUAL_CONFIRMED",
            },
        )
        self.assertEqual(response.status_code, 201)
        created = response.json()
        self.assertEqual(created["status"], "NEEDS_REVIEW")
        self.assertNotIn("object_reference", created)
        preview = importer.get(
            f"/v1/tenants/{tenant.id}/boundary-imports/{created['id']}/preview",
            headers={"Authorization": "Bearer synthetic-importer"},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertNotIn("object_reference", preview.text)
        reviewer = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "synthetic-reviewer",
                    AuthContext(
                        "synthetic-reviewer",
                        None,
                        roles=frozenset({"PLATFORM_ADMIN"}),
                        is_platform_admin=True,
                    ),
                ),
                settings=settings,
            )
        )
        approved = reviewer.post(
            f"/v1/tenants/{tenant.id}/boundary-imports/{created['id']}/approve",
            headers={"Authorization": "Bearer synthetic-reviewer"},
            json={
                "review_reason": "synthetic API review",
                "expected_property_checksum": property_item.boundary_checksum,
            },
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "APPROVED")

    def test_failed_approval_rolls_back_import_version_property_and_audit(self) -> None:
        tenant = self.tenant("Synthetic import atomicity tenant")
        property_item = self.property(tenant.id)
        imported = self.create_import(tenant.id, property_item.id)
        function = "test_reject_import_property_update"
        trigger = "test_reject_import_property_update_trigger"
        with psycopg.connect(MIGRATION_DATABASE_URL) as admin:  # type: ignore[arg-type]
            admin.execute(
                f"CREATE OR REPLACE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id = '{property_item.id}'::uuid THEN RAISE EXCEPTION 'synthetic approval failure'; END IF; RETURN NEW; END $$"
            )
            admin.execute(
                f"CREATE TRIGGER {trigger} BEFORE UPDATE OF geometry ON property FOR EACH ROW EXECUTE FUNCTION {function}()"
            )
        try:
            with self.assertRaises(psycopg.Error):
                self.application.approve_boundary_import(
                    tenant.id,
                    imported.id,
                    reviewer="reviewer-z",
                    reason="synthetic atomicity",
                    expected_property_checksum=property_item.boundary_checksum or "",
                )
        finally:
            with psycopg.connect(MIGRATION_DATABASE_URL) as admin:  # type: ignore[arg-type]
                admin.execute(f"DROP TRIGGER IF EXISTS {trigger} ON property")
                admin.execute(f"DROP FUNCTION IF EXISTS {function}()")
        with self.store.tenant_transaction(tenant.id):
            item = self.store.get_boundary_import(tenant.id, imported.id)
            current = self.store.get_property(tenant.id, property_item.id)
            versions = self.store.connection.execute(
                "SELECT version FROM property_boundary_version WHERE property_id=%s ORDER BY version",
                (property_item.id,),
            ).fetchall()
        self.assertEqual(item.status, "NEEDS_REVIEW")
        self.assertEqual(current.boundary_checksum, property_item.boundary_checksum)
        self.assertEqual([row["version"] for row in versions], [1])
