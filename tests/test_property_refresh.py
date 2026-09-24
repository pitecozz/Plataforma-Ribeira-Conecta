from __future__ import annotations

import unittest

from ribeira_platform.service import RibeiraApplication
from ribeira_platform.storage import SQLiteStore


BOUNDARY = {
    "type": "Polygon",
    "coordinates": [
        [[-48.25, -24.59], [-48.24, -24.59], [-48.24, -24.58], [-48.25, -24.59]]
    ],
}


class PropertyRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore()
        self.app = RibeiraApplication(self.store)
        self.tenant = self.app.create_tenant("Refresh tenant")

    def tearDown(self) -> None:
        self.store.close()

    def test_property_aoi_registers_one_durable_initial_backfill(self) -> None:
        property_item = self.app.create_property(
            self.tenant.id, "AOI", BOUNDARY, "EPSG:4326", actor="operator"
        )
        with self.store.tenant_transaction(self.tenant.id):
            status = self.app.property_refresh.status(self.tenant.id, property_item.id)
            assert status is not None
            runs = self.store.connection.execute(
                "SELECT * FROM property_refresh_run WHERE tenant_id=? AND property_id=?",
                [self.tenant.id, property_item.id],
            ).fetchall()
        self.assertEqual(status["status"], "QUEUED")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["trigger_type"], "INITIAL_PROPERTY_CONTEXT_REFRESH")
        # A deployment retry cannot duplicate a first backfill.
        self.app.property_refresh.register_property(
            self.tenant.id, property_item.id, actor="operator"
        )
        with self.store.tenant_transaction(self.tenant.id):
            count = self.store.connection.execute(
                "SELECT COUNT(*) AS count FROM property_refresh_run WHERE tenant_id=? AND property_id=?",
                [self.tenant.id, property_item.id],
            ).fetchone()["count"]
        self.assertEqual(count, 1)

    def test_manual_refresh_is_authorized_fallback_and_debounced(self) -> None:
        property_item = self.app.create_property(
            self.tenant.id, "AOI", BOUNDARY, "EPSG:4326", actor="operator"
        )
        first = self.app.property_refresh.enqueue_manual(
            self.tenant.id, property_item.id, actor="operator"
        )
        second = self.app.property_refresh.enqueue_manual(
            self.tenant.id, property_item.id, actor="operator"
        )
        self.assertEqual(first["id"], second["id"])

    def test_refresh_status_is_tenant_isolated(self) -> None:
        property_item = self.app.create_property(
            self.tenant.id, "AOI", BOUNDARY, "EPSG:4326", actor="operator"
        )
        other = self.app.create_tenant("Other")
        self.assertIsNone(self.app.property_refresh.status(other.id, property_item.id))

    def test_transient_provider_failure_is_durable_and_retryable(self) -> None:
        property_item = self.app.create_property(
            self.tenant.id, "AOI", BOUNDARY, "EPSG:4326", actor="operator"
        )

        def unavailable(*_args, **_kwargs):
            raise RuntimeError("provider unavailable")

        self.app.geospatial.search_satellite = unavailable  # type: ignore[method-assign]
        run = self.app.property_refresh.run_one(worker_id="test-worker")
        assert run is not None
        self.assertEqual(run["status"], "RETRYABLE")
        self.assertEqual(run["failure_code"], "RuntimeError")
        with self.store.tenant_transaction(self.tenant.id):
            status = self.app.property_refresh.status(self.tenant.id, property_item.id)
        assert status is not None
        self.assertEqual(status["status"], "RETRYABLE")
        self.assertEqual(status["retry_count"], 1)
