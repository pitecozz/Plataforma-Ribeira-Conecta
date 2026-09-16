from __future__ import annotations

import json
import os
import unittest

import psycopg

from ribeira_platform.audit_context import request_context
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


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")


@unittest.skipUnless(
    DATABASE_URL,
    "RIBEIRA_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)

    def tearDown(self) -> None:
        self.store.close()

    def test_postgis_round_trip_and_evidence_first_slice(self) -> None:
        tenant = self.application.create_tenant("PG integration tenant")
        with request_context("req-pg", "corr-pg"):
            property = self.application.create_property(
                tenant.id,
                "PG property",
                {"type": "Point", "coordinates": [-47.0, -24.0]},
                "EPSG:4326",
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
        with self.store.tenant_transaction(tenant.id):
            self.assertEqual(self.store.count("observation", tenant.id), 1)
            self.assertEqual(self.store.count("evidence", tenant.id), 1)
            row = self.store.connection.execute(
                "SELECT ST_SRID(geometry) AS srid, ST_AsText(geometry) AS wkt FROM property WHERE id=%s",
                (property.id,),
            ).fetchone()
            self.assertEqual(row["srid"], 4326)
            self.assertEqual(row["wkt"], "POINT(-47 -24)")
            audit = self.store.connection.execute(
                "SELECT request_id, correlation_id FROM audit_log WHERE entity_id=%s",
                (property.id,),
            ).fetchone()
            self.assertEqual(audit["request_id"], "req-pg")
            self.assertEqual(audit["correlation_id"], "corr-pg")

    def test_rls_denies_cross_tenant_read_write_and_references(self) -> None:
        tenant_a = self.application.create_tenant("Tenant A PG")
        tenant_b = self.application.create_tenant("Tenant B PG")
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


if __name__ == "__main__":
    unittest.main()
