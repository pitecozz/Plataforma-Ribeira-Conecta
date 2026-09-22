"""The private pilot bootstrap uses actual PostgreSQL RLS and audit persistence."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from ribeira_platform.pilot_bootstrap import execute_plan, load_plan
from ribeira_platform.postgres import PostgresStore
from tests.integration.tenant_cleanup import delete_test_tenants


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class PilotBootstrapPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest_path = self.root / "manifest.json"
        self.geojson_path = self.root / "pilot.geojson"
        self.plan = self._write_package()

    def tearDown(self) -> None:
        try:
            delete_test_tenants([self.plan.tenant_id])
        finally:
            self.store.close()
            self.temporary.cleanup()

    def _write_package(self):
        boundary = {
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

        def feature(name, kind, geometry, **extra):
            return {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "entity_kind": kind,
                    "crs": "EPSG:4326",
                    "source": "SYNTHETIC_TEST_SOURCE",
                    "classification": "MANUAL_CONFIRMED",
                    **extra,
                },
                "geometry": geometry,
            }

        manifest = {
            "pilot_customer_label": "SYNTHETIC BOOTSTRAP CUSTOMER",
            "property_name": "SYNTHETIC BOOTSTRAP PROPERTY",
            "source": "SYNTHETIC_TEST_SOURCE",
            "crs": "EPSG:4326",
            "boundary": {
                "placemark_name": "SYNTHETIC BOOTSTRAP BOUNDARY",
                "confirmed_by_operator": True,
                "legal_boundary_verified": False,
                "intended_use": "operational_analysis_boundary",
            },
            "included_assets": ["SYNTHETIC BOOTSTRAP HOUSE"],
            "excluded_features": {"unresolved": "synthetic exclusion"},
        }
        geojson = {
            "type": "FeatureCollection",
            "features": [
                feature(
                    "SYNTHETIC BOOTSTRAP BOUNDARY",
                    "property_boundary",
                    boundary,
                    usage="operational_analysis_boundary",
                    legal_boundary_verified=False,
                ),
                feature(
                    "SYNTHETIC BOOTSTRAP HOUSE",
                    "asset",
                    {"type": "Point", "coordinates": [-46.999, -24.001]},
                    asset_type="house_building",
                ),
            ],
        }
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.geojson_path.write_text(json.dumps(geojson), encoding="utf-8")
        os.chmod(self.manifest_path, 0o600)
        os.chmod(self.geojson_path, 0o600)
        return load_plan(self.manifest_path, self.geojson_path)

    def test_dry_run_create_and_idempotent_retry_are_audited(self) -> None:
        self.assertEqual(
            execute_plan(
                self.store, self.plan, actor="SYNTHETIC_OPERATOR", dry_run=True
            ),
            "WOULD_CREATE",
        )
        self.assertEqual(
            execute_plan(
                self.store, self.plan, actor="SYNTHETIC_OPERATOR", dry_run=False
            ),
            "CREATED",
        )
        self.assertEqual(
            execute_plan(
                self.store, self.plan, actor="SYNTHETIC_OPERATOR", dry_run=False
            ),
            "EXISTS",
        )
        with self.store.tenant_transaction(self.plan.tenant_id):
            property_item = self.store.get_property(
                self.plan.tenant_id, self.plan.property_id
            )
            asset_count = self.store.connection.execute(
                "SELECT count(*) AS count FROM asset WHERE property_id=%s",
                (self.plan.property_id,),
            ).fetchone()
            audit = self.store.connection.execute(
                """SELECT payload FROM audit_log
                   WHERE tenant_id=%s AND event_type='PILOT_BOOTSTRAP_COMPLETED'""",
                (self.plan.tenant_id,),
            ).fetchone()
        self.assertIsNotNone(property_item)
        assert property_item is not None
        self.assertEqual(property_item.boundary_source, "SYNTHETIC_TEST_SOURCE")
        self.assertEqual(asset_count["count"], 1)
        self.assertFalse(audit["payload"]["legal_boundary_verified"])
