"""PostgreSQL tests using explicitly synthetic tenants and boundaries only."""

from __future__ import annotations

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import psycopg

from ribeira_platform.epistemology import DataClassification
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import RibeiraApplication
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


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class PropertyPortfolioPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self.tenant_ids: list[str] = []

    def tearDown(self) -> None:
        try:
            delete_test_tenants(self.tenant_ids)
        finally:
            self.store.close()

    def tenant(self, name: str):
        item = self.application.create_tenant(name)
        self.tenant_ids.append(item.id)
        return item

    def test_portfolio_boundary_history_and_rls_are_tenant_scoped(self) -> None:
        tenant_a = self.tenant("Synthetic portfolio tenant A")
        tenant_b = self.tenant("Synthetic portfolio tenant B")
        property_a = self.application.create_property(
            tenant_a.id,
            "Synthetic boundary A",
            BOUNDARY_V1,
            "EPSG:4326",
            boundary_source="synthetic test survey",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor="synthetic-create-actor",
        )
        property_b = self.application.create_property(
            tenant_b.id,
            "Synthetic boundary B",
            BOUNDARY_V1,
            "EPSG:4326",
            boundary_source="synthetic test survey",
            classification=DataClassification.MANUAL_CONFIRMED,
        )
        self.assertIsNotNone(property_a.boundary_checksum)
        with self.store.tenant_transaction(tenant_a.id):
            self.assertEqual(
                [p.id for p in self.store.list_properties(tenant_a.id)], [property_a.id]
            )
            baseline = self.store.connection.execute(
                "SELECT version,checksum,boundary_source,data_classification,actor,effective_at FROM property_boundary_version WHERE property_id=%s",
                (property_a.id,),
            ).fetchone()
            self.assertEqual(baseline["version"], 1)
            self.assertEqual(baseline["checksum"], property_a.boundary_checksum)
            self.assertEqual(baseline["boundary_source"], "synthetic test survey")
            self.assertEqual(baseline["data_classification"], "MANUAL_CONFIRMED")
            self.assertEqual(baseline["actor"], "synthetic-create-actor")
            self.assertIsNotNone(baseline["effective_at"])

        updated = self.application.update_property_boundary(
            tenant_a.id,
            property_a.id,
            BOUNDARY_V2,
            "EPSG:4326",
            "synthetic revised survey",
            DataClassification.MANUAL_CONFIRMED,
            "synthetic correction",
            "integration-test",
            property_a.boundary_checksum,
        )
        self.assertNotEqual(updated.boundary_checksum, property_a.boundary_checksum)
        with self.store.tenant_transaction(tenant_a.id):
            history = self.store.connection.execute(
                "SELECT version,checksum,boundary_source,data_classification,reason,actor,effective_at FROM property_boundary_version WHERE property_id=%s ORDER BY version",
                (property_a.id,),
            ).fetchall()
            self.assertEqual([row["version"] for row in history], [1, 2])
            self.assertEqual(history[0]["checksum"], property_a.boundary_checksum)
            self.assertEqual(history[1]["checksum"], updated.boundary_checksum)
            self.assertEqual(history[1]["reason"], "synthetic correction")
            self.assertEqual(history[1]["actor"], "integration-test")
            self.assertEqual(history[1]["data_classification"], "MANUAL_CONFIRMED")
            self.assertIsNotNone(history[1]["effective_at"])
            current = self.store.get_property(tenant_a.id, property_a.id)
            self.assertEqual(current.boundary_checksum, updated.boundary_checksum)
            self.assertEqual(current.boundary_source, "synthetic revised survey")
            self.assertIsNone(self.store.get_property(tenant_a.id, property_b.id))
            self.assertEqual(
                self.store.connection.execute(
                    "SELECT count(*) AS count FROM property_boundary_version WHERE property_id=%s",
                    (property_b.id,),
                ).fetchone()["count"],
                0,
            )
        with self.assertRaises(ValueError):
            self.application.update_property_boundary(
                tenant_a.id,
                property_a.id,
                BOUNDARY_V1,
                "EPSG:4326",
                "synthetic stale survey",
                DataClassification.MANUAL_CONFIRMED,
                "stale update",
                "integration-test",
                property_a.boundary_checksum,
            )
        with self.assertRaises(LookupError):
            self.application.update_property_boundary(
                tenant_b.id,
                property_a.id,
                BOUNDARY_V2,
                "EPSG:4326",
                "synthetic cross-tenant survey",
                DataClassification.MANUAL_CONFIRMED,
                "cross-tenant update",
                "integration-test",
                property_a.boundary_checksum,
            )

    def test_boundary_update_cannot_exclude_current_field(self) -> None:
        tenant = self.tenant("Synthetic property field guard tenant")
        property_item = self.application.create_property(
            tenant.id,
            "Synthetic property with field",
            BOUNDARY_V2,
            "EPSG:4326",
            boundary_source="synthetic property survey",
            classification=DataClassification.MANUAL_CONFIRMED,
        )
        self.application.fields.create(
            tenant.id,
            property_id=property_item.id,
            name="Synthetic east field",
            status="ACTIVE",
            geometry_geojson={
                "type": "Polygon",
                "coordinates": [
                    [
                        [-46.989, -24.009],
                        [-46.981, -24.009],
                        [-46.981, -24.001],
                        [-46.989, -24.001],
                        [-46.989, -24.009],
                    ]
                ],
            },
            geometry_crs="EPSG:4326",
            source_reference="synthetic field walk",
            observed_at="2026-09-25T12:00:00+00:00",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor="integration-test",
        )

        with self.assertRaisesRegex(
            psycopg.Error, "property boundary must cover every current field boundary"
        ):
            self.application.update_property_boundary(
                tenant.id,
                property_item.id,
                BOUNDARY_V1,
                "EPSG:4326",
                "synthetic excluding correction",
                DataClassification.MANUAL_CONFIRMED,
                "synthetic invalid correction",
                "integration-test",
                property_item.boundary_checksum,
            )

        with self.store.tenant_transaction(tenant.id):
            current = self.store.get_property(tenant.id, property_item.id)
            versions = self.store.connection.execute(
                "SELECT count(*) AS count FROM property_boundary_version WHERE tenant_id=%s AND property_id=%s",
                (tenant.id, property_item.id),
            ).fetchone()
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.boundary_checksum, property_item.boundary_checksum)
        self.assertEqual(versions["count"], 1)

    def test_concurrent_updates_serialize_or_report_stale_checksum(self) -> None:
        tenant = self.tenant("Synthetic concurrent boundary tenant")
        item = self.application.create_property(
            tenant.id,
            "Synthetic concurrent boundary",
            BOUNDARY_V1,
            "EPSG:4326",
            boundary_source="synthetic test survey",
            actor="synthetic-create-actor",
        )
        assert item.boundary_checksum is not None
        barrier = Barrier(2)

        def update(actor: str) -> str:
            store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
            try:
                application = RibeiraApplication(store)
                barrier.wait(timeout=5)
                application.update_property_boundary(
                    tenant.id,
                    item.id,
                    BOUNDARY_V2,
                    "EPSG:4326",
                    f"synthetic concurrent survey {actor}",
                    DataClassification.MANUAL_CONFIRMED,
                    "synthetic concurrent update",
                    actor,
                    item.boundary_checksum,
                )
                return "updated"
            except ValueError:
                return "conflict"
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, ["worker-a", "worker-b"]))
        self.assertEqual(sorted(results), ["conflict", "updated"])
        with self.store.tenant_transaction(tenant.id):
            versions = self.store.connection.execute(
                "SELECT version FROM property_boundary_version WHERE property_id=%s ORDER BY version",
                (item.id,),
            ).fetchall()
        self.assertEqual([row["version"] for row in versions], [1, 2])

    def test_failed_current_property_write_rolls_back_version_and_audit(self) -> None:
        tenant = self.tenant("Synthetic atomic boundary tenant")
        item = self.application.create_property(
            tenant.id,
            "Synthetic atomic boundary",
            BOUNDARY_V1,
            "EPSG:4326",
            boundary_source="synthetic test survey",
            actor="synthetic-create-actor",
        )
        assert item.boundary_checksum is not None
        function_name = "test_reject_boundary_current_update"
        trigger_name = "test_reject_boundary_current_update_trigger"
        with psycopg.connect(MIGRATION_DATABASE_URL) as admin:  # type: ignore[arg-type]
            admin.execute(
                f"""CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger
                LANGUAGE plpgsql AS $$ BEGIN
                  IF NEW.id = '{item.id}'::uuid THEN RAISE EXCEPTION 'synthetic property update failure'; END IF;
                  RETURN NEW;
                END $$"""
            )
            admin.execute(
                f"CREATE TRIGGER {trigger_name} BEFORE UPDATE OF geometry ON property FOR EACH ROW EXECUTE FUNCTION {function_name}()"
            )
        try:
            with self.assertRaises(psycopg.Error):
                self.application.update_property_boundary(
                    tenant.id,
                    item.id,
                    BOUNDARY_V2,
                    "EPSG:4326",
                    "synthetic rejected survey",
                    DataClassification.MANUAL_CONFIRMED,
                    "synthetic rollback test",
                    "integration-test",
                    item.boundary_checksum,
                )
        finally:
            with psycopg.connect(MIGRATION_DATABASE_URL) as admin:  # type: ignore[arg-type]
                admin.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON property")
                admin.execute(f"DROP FUNCTION IF EXISTS {function_name}()")
        with self.store.tenant_transaction(tenant.id):
            versions = self.store.connection.execute(
                "SELECT version FROM property_boundary_version WHERE property_id=%s ORDER BY version",
                (item.id,),
            ).fetchall()
            current = self.store.get_property(tenant.id, item.id)
            audits = self.store.connection.execute(
                "SELECT count(*) AS count FROM audit_log WHERE entity_id=%s AND event_type='BOUNDARY_CHANGED'",
                (item.id,),
            ).fetchone()
        self.assertEqual([row["version"] for row in versions], [1])
        self.assertEqual(current.boundary_checksum, item.boundary_checksum)
        self.assertEqual(audits["count"], 0)
