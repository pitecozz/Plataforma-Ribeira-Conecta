"""PostgreSQL tests using explicitly synthetic tenants and boundaries only."""

from __future__ import annotations

import os
import unittest

from ribeira_platform.epistemology import DataClassification
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import RibeiraApplication
from tests.integration.tenant_cleanup import delete_test_tenants


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")
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
                "SELECT version,checksum,boundary_source,data_classification FROM property_boundary_version WHERE property_id=%s",
                (property_a.id,),
            ).fetchone()
            self.assertEqual(baseline["version"], 1)
            self.assertEqual(baseline["checksum"], property_a.boundary_checksum)
            self.assertEqual(baseline["boundary_source"], "synthetic test survey")
            self.assertEqual(baseline["data_classification"], "MANUAL_CONFIRMED")

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
                "SELECT version,checksum,boundary_source,reason FROM property_boundary_version WHERE property_id=%s ORDER BY version",
                (property_a.id,),
            ).fetchall()
            self.assertEqual([row["version"] for row in history], [1, 2])
            self.assertEqual(history[0]["checksum"], property_a.boundary_checksum)
            self.assertEqual(history[1]["checksum"], updated.boundary_checksum)
            self.assertEqual(history[1]["reason"], "synthetic correction")
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
