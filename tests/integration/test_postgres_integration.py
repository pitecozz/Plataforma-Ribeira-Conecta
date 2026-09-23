from __future__ import annotations

import json
import os
import threading
import time
import unittest
from datetime import datetime, timezone

import psycopg
from psycopg import pq

from ribeira_platform.audit_context import request_context
from ribeira_platform.business import (
    Asset,
    CommercialClassification,
    ProductStatus,
    RevenueType,
    ServiceOffering,
)
from ribeira_platform.epistemology import (
    DataClassification,
    DecisionStatus,
    IngestionStatus,
    RuleAuthority,
)
from ribeira_platform.models import RuleDefinition, new_id
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.sources import SyntheticFixtureAdapter
from tests.integration.tenant_cleanup import delete_test_tenants


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")
MIGRATION_DATABASE_URL = os.getenv("RIBEIRA_TEST_MIGRATION_DATABASE_URL")


@unittest.skipUnless(
    DATABASE_URL,
    "RIBEIRA_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgresIntegrationTests(unittest.TestCase):
    def test_flood_exposure_requires_a_verified_zone_and_preserves_hypotheses(
        self,
    ) -> None:
        # Historical reconciliation is the supported, idempotent registration
        # path for this global factual event.  Do not rely on data that may
        # happen to predate migration 030 in a shared integration database.
        with self.store.transaction():
            self.store.rebuild_september_event_timeline(
                end_at=datetime(2026, 9, 30, tzinfo=timezone.utc)
            )
        tenant = self.create_test_tenant("Flood exposure PG tenant")
        property = self.application.create_property(
            tenant.id,
            "Flood exposure property",
            {
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
            },
            "EPSG:4326",
        )
        unknown = self.application.assess_flood_exposure(
            tenant.id,
            event_key="VALE_RIBEIRA_FLOOD_2026_09",
            subject_type="PROPERTY",
            subject_id=property.id,
            exposure_zone_id=None,
            actor="operator",
        )
        self.assertEqual(unknown["status"], "UNKNOWN")
        self.assertEqual(unknown["classification"], "UNKNOWN")
        self.assertIn("VERIFIED_FLOOD_EXPOSURE_ZONE_REQUIRED", unknown["limitations"])

        other_tenant = self.create_test_tenant("Other flood exposure tenant")
        with self.store.tenant_transaction(None, platform_admin=True):
            event = self.store.connection.execute(
                "SELECT id FROM operational_event WHERE event_key=%s",
                ("VALE_RIBEIRA_FLOOD_2026_09",),
            ).fetchone()
        self.assertIsNotNone(event)
        assert event is not None
        with self.store.tenant_transaction(other_tenant.id):
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    """INSERT INTO tenant_flood_exposure_assessment(
                           id,tenant_id,event_id,subject_type,property_id,status,
                           classification,method,limitations,provenance,assessed_at
                         ) VALUES (%s,%s,%s,'PROPERTY',%s,'UNKNOWN','UNKNOWN',
                           'cross_tenant_test','[]'::jsonb,'{}'::jsonb,now())""",
                    (new_id(), other_tenant.id, event["id"], property.id),
                )

        zone_id = new_id()
        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.connection.execute(
                """INSERT INTO flood_event_exposure_zone(
                       id,event_id,zone_type,geometry,geometry_status,classification,
                       method,source_reference,limitations,provenance
                     ) VALUES (%s,%s,'FLOOD_EXTENT',ST_GeomFromText(%s,4326),
                       'VERIFIED','OFFICIAL_SOURCE','synthetic_postgis_test',%s,'[]'::jsonb,
                       '{"fixture":true}'::jsonb)""",
                (
                    zone_id,
                    event["id"],
                    "POLYGON((-47.005 -24.005,-46.995 -24.005,-46.995 -23.995,-47.005 -23.995,-47.005 -24.005))",
                    "https://example.invalid/flood-zone-fixture",
                ),
            )
            hypotheses = self.store.connection.execute(
                "SELECT hypothesis_key,status FROM flood_event_hypothesis "
                "WHERE event_id=%s ORDER BY hypothesis_key",
                (event["id"],),
            ).fetchall()
        self.assertEqual(
            [(item["hypothesis_key"], item["status"]) for item in hypotheses],
            [
                ("H1_LOCAL_RAINFALL", "INCONCLUSIVE"),
                ("H2_UPSTREAM_RAINFALL", "UNKNOWN"),
                ("H3_RESERVOIR_OPERATION", "INCONCLUSIVE"),
                ("H4_ENSO_CONTEXT", "INCONCLUSIVE"),
            ],
        )
        situation = self.store.vale_do_ribeira_situation()
        self.assertEqual(
            situation["event"]["flood_profile"]["classification"],
            "FACTUAL_EVIDENCE_ONLY",
        )
        self.assertEqual(len(situation["event"]["hypotheses"]), 4)
        exposed = self.application.assess_flood_exposure(
            tenant.id,
            event_key="VALE_RIBEIRA_FLOOD_2026_09",
            subject_type="PROPERTY",
            subject_id=property.id,
            exposure_zone_id=zone_id,
            actor="operator",
        )
        self.assertEqual(exposed["status"], "EXPOSED")
        self.assertEqual(exposed["classification"], "CALCULATED")
        self.assertGreater(float(exposed["intersection_km2"]), 0)
        with self.store.tenant_transaction(tenant.id):
            self.store.connection.execute(
                "DELETE FROM tenant_flood_exposure_assessment WHERE id=%s",
                (exposed["id"],),
            )
        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.connection.execute(
                "DELETE FROM flood_event_exposure_zone WHERE id=%s", (zone_id,)
            )

    def test_spatial_asset_context_is_postgis_persisted_and_tenant_scoped(self) -> None:
        tenant = self.create_test_tenant("Spatial asset PG tenant")
        property = self.application.create_property(tenant.id, "Asset context property")
        asset = Asset(
            new_id(),
            tenant.id,
            "CCTV_CAMERA",
            "Loading area camera",
            None,
            "ACTIVE",
            property.id,
            None,
            CommercialClassification.MANUAL_CONFIRMED,
            {"type": "Point", "coordinates": [-47.0, -24.0]},
            "EPSG:4326",
            "operator survey",
            "2026-09-21T12:00:00+00:00",
            {"operational_role": "security", "condition": "UNKNOWN"},
        )
        self.application.business.register_asset(asset, actor="operator")
        with self.store.tenant_transaction(tenant.id):
            row = self.store.connection.execute(
                "SELECT ST_AsGeoJSON(geometry) AS geometry,geometry_crs,context FROM asset WHERE id=%s",
                (asset.id,),
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["geometry_crs"], "EPSG:4326")
        self.assertEqual(row["context"]["operational_role"], "security")
        self.assertEqual(json.loads(row["geometry"])["type"], "Point")
        listed = self.application.business.list_assets_for_property(
            tenant.id, property.id
        )
        self.assertEqual([item.id for item in listed], [asset.id])
        self.assertEqual(listed[0].geometry_geojson, asset.geometry_geojson)

    def test_pilot_feedback_is_rls_scoped_and_rejects_cross_tenant_property(
        self,
    ) -> None:
        tenant_a = self.create_test_tenant("Pilot feedback tenant A")
        tenant_b = self.create_test_tenant("Pilot feedback tenant B")
        property_a = self.application.create_property(
            tenant_a.id, "Feedback property A"
        )
        property_b = self.application.create_property(
            tenant_b.id, "Feedback property B"
        )
        item = self.application.create_pilot_feedback(
            tenant_a.id,
            feedback_type="USEFUL",
            page="farm360",
            feature_id="F-ASSET-001",
            message="Asset context is useful for the pilot workspace.",
            property_id=property_a.id,
            submitted_by="pilot-user-a",
        )
        with self.store.tenant_transaction(tenant_a.id):
            row = self.store.connection.execute(
                "SELECT submitted_by,feedback_type,property_id FROM pilot_feedback WHERE id=%s",
                (item.id,),
            ).fetchone()
            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row["submitted_by"], "pilot-user-a")
            self.assertEqual(str(row["property_id"]), property_a.id)
        with self.store.tenant_transaction(tenant_b.id):
            self.assertIsNone(
                self.store.connection.execute(
                    "SELECT id FROM pilot_feedback WHERE id=%s", (item.id,)
                ).fetchone()
            )
        with self.assertRaises(LookupError):
            self.application.create_pilot_feedback(
                tenant_a.id,
                feedback_type="BUG",
                page="farm360",
                feature_id="F-ASSET-001",
                message="Cross-tenant property link must be rejected.",
                property_id=property_b.id,
                submitted_by="pilot-user-a",
            )

    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self._test_tenant_ids: list[str] = []

    def create_test_tenant(self, name: str):
        tenant = self.application.create_tenant(name)
        self._test_tenant_ids.append(tenant.id)
        return tenant

    def tearDown(self) -> None:
        try:
            delete_test_tenants(self._test_tenant_ids)
        finally:
            self.store.close()

    def test_postgis_round_trip_and_evidence_first_slice(self) -> None:
        tenant = self.create_test_tenant("PG integration tenant")
        with request_context("req-pg", "corr-pg"):
            property = self.application.create_property(
                tenant.id,
                "PG property",
                {
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
                },
                "EPSG:4326",
                boundary_source="MANUAL_CONFIRMED integration boundary",
            )
        source = self.application.create_source(
            tenant.id, "PG fixture source", "TEST", "fixture"
        )
        self.application.create_rule(
            RuleDefinition(
                new_id(),
                tenant.id,
                1,
                "moisture rule",
                RuleAuthority.REGRA_AGRONOMICA,
                "soil_moisture",
                "<",
                30,
                "%",
                "HIGH",
                "ACTIVE",
                "distinct-approver",
                "2026-09-16T00:00:00+00:00",
            )
        )
        self.application.adapters[source.id] = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": 27.4,
                    "unit": "%",
                    "observation_timestamp": "2026-09-16T13:42:11-03:00",
                    "quality_flag": "VALID",
                }
            ]
        )
        ingestion = self.application.ingest(tenant.id, property.id, source.id)
        result = self.application.evaluate(tenant.id, property.id)
        self.assertEqual(ingestion.fetch.status, IngestionStatus.INGESTED)
        self.assertEqual(result.decision.status, DecisionStatus.ACTIONABLE)
        self.assertEqual(result.decision.classification, DataClassification.INFERRED)
        assert result.action is not None
        self.application.complete_action(
            tenant.id,
            result.action.id,
            outcome_detail="Field operator confirmed the corrective irrigation.",
            outcome_classification=DataClassification.MANUAL_CONFIRMED,
            evidence_ids=result.decision.evidence_ids,
            actor="pg-field-operator",
            completed_at="2026-09-16T18:00:00+00:00",
        )
        history = self.application.decision_history_for_property(tenant.id, property.id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "ACTIONABLE")
        self.assertEqual(history[0]["action"]["status"], "COMPLETED")
        with self.store.tenant_transaction(tenant.id):
            self.assertEqual(self.store.count("observation", tenant.id), 1)
            self.assertEqual(self.store.count("evidence", tenant.id), 1)
            row = self.store.connection.execute(
                "SELECT ST_SRID(geometry) AS srid, ST_AsText(geometry) AS wkt FROM property WHERE id=%s",
                (property.id,),
            ).fetchone()
            self.assertEqual(row["srid"], 4326)
            self.assertEqual(
                row["wkt"],
                "POLYGON((-47 -24,-46.99 -24,-46.99 -24.01,-47 -24.01,-47 -24))",
            )
            self.assertEqual(
                self.store.get_property(tenant.id, property.id).boundary_source,
                "MANUAL_CONFIRMED integration boundary",
            )
            action = self.store.connection.execute(
                "SELECT status,completed_by,outcome_classification,"
                "outcome_evidence_ids FROM action WHERE id=%s",
                (result.action.id,),
            ).fetchone()
            self.assertIsNotNone(action)
            assert action is not None
            self.assertEqual(action["status"], "COMPLETED")
            self.assertEqual(action["completed_by"], "pg-field-operator")
            self.assertEqual(action["outcome_classification"], "MANUAL_CONFIRMED")
            self.assertEqual(
                action["outcome_evidence_ids"], result.decision.evidence_ids
            )
            audit = self.store.connection.execute(
                "SELECT request_id, correlation_id FROM audit_log WHERE entity_id=%s",
                (property.id,),
            ).fetchone()
            self.assertEqual(audit["request_id"], "req-pg")
            self.assertEqual(audit["correlation_id"], "corr-pg")

    def test_ready_closes_its_read_transaction(self) -> None:
        for _ in range(5):
            self.assertTrue(self.store.ready())
        self.assertEqual(
            self.store.connection.info.transaction_status, pq.TransactionStatus.IDLE
        )
        with psycopg.connect(MIGRATION_DATABASE_URL) as admin:  # type: ignore[arg-type]
            row = admin.execute(
                "SELECT state FROM pg_stat_activity WHERE pid=%s",
                (self.store.connection.info.backend_pid,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertNotEqual(row[0], "idle in transaction")

    def test_shared_store_serializes_tenant_transactions(self) -> None:
        """Concurrent request dependencies cannot leak an RLS setting."""
        tenant_a = self.create_test_tenant("Serialized transaction tenant A")
        tenant_b = self.create_test_tenant("Serialized transaction tenant B")
        start = threading.Barrier(2)
        observed: list[str] = []
        errors: list[BaseException] = []

        def read_tenant(tenant_id: str) -> None:
            try:
                start.wait(timeout=2)
                with self.store.tenant_transaction(tenant_id):
                    row = self.store.connection.execute(
                        "SELECT current_setting('app.tenant_id', true) AS tenant_id"
                    ).fetchone()
                    assert row is not None
                    observed.append(str(row["tenant_id"]))
                    time.sleep(0.03)
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [
            threading.Thread(target=read_tenant, args=(tenant_a.id,)),
            threading.Thread(target=read_tenant, args=(tenant_b.id,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertCountEqual(observed, [tenant_a.id, tenant_b.id])
        self.assertEqual(
            self.store.connection.info.transaction_status, pq.TransactionStatus.IDLE
        )

    def test_rls_denies_cross_tenant_read_write_and_references(self) -> None:
        tenant_a = self.create_test_tenant("Tenant A PG")
        tenant_b = self.create_test_tenant("Tenant B PG")
        property_a = self.application.create_property(tenant_a.id, "Property A")
        source_a = self.application.create_source(
            tenant_a.id, "Source A", "TEST", "fixture"
        )
        with self.store.tenant_transaction(tenant_b.id):
            self.assertIsNone(
                self.store.connection.execute(
                    "SELECT id FROM property WHERE id=%s", (property_a.id,)
                ).fetchone()
            )
            self.assertEqual(
                self.store.connection.execute(
                    "UPDATE property SET name='tampered' WHERE id=%s", (property_a.id,)
                ).rowcount,
                0,
            )
            self.assertEqual(
                self.store.connection.execute(
                    "DELETE FROM property WHERE id=%s", (property_a.id,)
                ).rowcount,
                0,
            )
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    "INSERT INTO observation(id,tenant_id,property_id,source_id,metric,observation_timestamp,ingestion_timestamp,processing_timestamp,data_classification,quality_flag) VALUES (%s,%s,%s,%s,%s,now(),now(),now(),%s,%s)",
                    (
                        new_id(),
                        tenant_b.id,
                        property_a.id,
                        source_a.id,
                        "soil_moisture",
                        "OBSERVED",
                        "VALID",
                    ),
                )
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    "INSERT INTO evidence(id,tenant_id,evidence_type,reference_id,data_classification,limitations) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        new_id(),
                        tenant_b.id,
                        "PROPERTY",
                        property_a.id,
                        "OBSERVED",
                        json.dumps([]),
                    ),
                )
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    "INSERT INTO decision(id,tenant_id,property_id,conclusion,data_classification,status,evidence_ids,limitations,missing_data,conflicts) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        new_id(),
                        tenant_b.id,
                        property_a.id,
                        "cross tenant",
                        "UNKNOWN",
                        "INCONCLUSIVE",
                        json.dumps([]),
                        json.dumps([]),
                        json.dumps([]),
                        json.dumps([]),
                    ),
                )
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    "INSERT INTO alert(id,tenant_id,property_id,alert_type,severity,status,title,decision_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        new_id(),
                        tenant_b.id,
                        property_a.id,
                        "TEST",
                        "HIGH",
                        "OPEN",
                        "cross tenant",
                        new_id(),
                    ),
                )
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    "INSERT INTO action(id,tenant_id,action_type,status,decision_id) VALUES (%s,%s,%s,%s,%s)",
                    (new_id(), tenant_b.id, "cross tenant", "OPEN", new_id()),
                )
        with self.assertRaises(LookupError):
            self.application.evaluate(tenant_b.id, property_a.id)

    def test_business_domain_is_persisted_and_rls_blocks_cross_tenant_references(
        self,
    ) -> None:
        tenant_a = self.create_test_tenant("Business Tenant A")
        tenant_b = self.create_test_tenant("Business Tenant B")
        property_a = self.application.create_property(
            tenant_a.id, "Business Property A"
        )
        property_b = self.application.create_property(
            tenant_b.id, "Business Property B"
        )
        customer_a = self.application.business.create_customer(
            tenant_a.id,
            "Customer A",
            actor="commercial-a",
        )
        customer_b = self.application.business.create_customer(
            tenant_b.id,
            "Customer B",
            actor="commercial-b",
        )
        self.application.business.create_service(
            ServiceOffering(
                new_id(),
                tenant_a.id,
                "Managed network",
                "CONNECTIVITY",
                ProductStatus.ACTIVE,
                True,
                RevenueType.RECURRING_REVENUE,
                None,
                CommercialClassification.CONFIRMED,
            ),
            actor="commercial-a",
        )
        self.application.business.link_customer_property(
            tenant_a.id,
            customer_a.id,
            property_a.id,
            "OWNER",
            "2026-09-16T00:00:00+00:00",
            None,
            actor="commercial-a",
        )

        with self.store.tenant_transaction(tenant_b.id):
            self.assertIsNone(
                self.store.connection.execute(
                    "SELECT id FROM customer WHERE id=%s", (customer_a.id,)
                ).fetchone()
            )
            self.assertEqual(
                self.store.connection.execute(
                    "UPDATE customer SET display_name='tampered' WHERE id=%s",
                    (customer_a.id,),
                ).rowcount,
                0,
            )
            self.assertEqual(
                self.store.connection.execute(
                    "DELETE FROM customer WHERE id=%s", (customer_a.id,)
                ).rowcount,
                0,
            )
        with self.store.tenant_transaction(tenant_b.id):
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    """INSERT INTO customer_property
                       (id,tenant_id,customer_id,property_id,relationship_type,valid_from,data_classification)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        new_id(),
                        tenant_b.id,
                        customer_a.id,
                        property_a.id,
                        "OWNER",
                        "2026-09-16T00:00:00+00:00",
                        "CONFIRMED",
                    ),
                )
        with self.store.tenant_transaction(tenant_b.id):
            with self.assertRaises(psycopg.Error):
                self.store.connection.execute(
                    """INSERT INTO commercial_opportunity
                       (id,tenant_id,customer_id,property_id,opportunity_type,status,classification,
                        evidence_ids,estimated_value_classification)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        new_id(),
                        tenant_b.id,
                        customer_a.id,
                        property_a.id,
                        "CROSS_TENANT",
                        "OPEN",
                        "POTENTIAL_OPPORTUNITY",
                        "[]",
                        "UNKNOWN",
                    ),
                )
        with self.store.tenant_transaction(tenant_b.id):
            rls = self.store.connection.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname='customer'"
            ).fetchone()
            self.assertTrue(rls["relrowsecurity"])
            self.assertTrue(rls["relforcerowsecurity"])
        self.assertEqual(customer_b.tenant_id, tenant_b.id)
        self.assertEqual(property_b.tenant_id, tenant_b.id)


if __name__ == "__main__":
    unittest.main()
