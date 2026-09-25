"""PostgreSQL/RLS coverage for non-legal field/talhão context."""

from __future__ import annotations

import os
import psycopg
import unittest

from shapely.geometry import Polygon, mapping

from ribeira_platform.epistemology import DataClassification
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import RibeiraApplication


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class FieldContextPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self.store.connection.execute("BEGIN")

    def tearDown(self) -> None:
        self.store.connection.rollback()
        self.store.close()

    def tenant(self, name: str):
        item = self.application.create_tenant(name)
        return item

    @staticmethod
    def polygon(west: float, south: float, east: float, north: float) -> dict:
        return mapping(
            Polygon(
                [
                    (west, south),
                    (east, south),
                    (east, north),
                    (west, north),
                    (west, south),
                ]
            )
        )

    def test_field_is_contained_versioned_evidenced_and_rls_scoped(self) -> None:
        tenant = self.tenant("Synthetic field PostgreSQL tenant")
        other_tenant = self.tenant("Other synthetic field PostgreSQL tenant")
        property_item = self.application.create_property(
            tenant.id,
            "Synthetic field property",
            self.polygon(-47.0, -24.01, -46.99, -24.0),
            "EPSG:4326",
            boundary_source="synthetic integration boundary",
            classification=DataClassification.MANUAL_CONFIRMED,
        )
        field = self.application.fields.create(
            tenant.id,
            property_id=property_item.id,
            name="Synthetic field",
            status="ACTIVE",
            geometry_geojson=self.polygon(-46.998, -24.008, -46.992, -24.002),
            geometry_crs="EPSG:4326",
            source_reference="synthetic integration field walk",
            observed_at="2026-09-24T12:00:00+00:00",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor="integration-operator",
        )
        with self.store.tenant_transaction(tenant.id):
            row = self.store.connection.execute(
                """SELECT version,geometry_crs,
                          ST_Covers((SELECT geometry FROM property WHERE id=%s),geometry) AS contained
                     FROM field_context_boundary_version
                    WHERE tenant_id=%s AND field_context_id=%s""",
                (property_item.id, tenant.id, field.id),
            ).fetchone()
            evidence = self.store.evidence_for_reference(tenant.id, field.id)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["version"], 1)
        self.assertEqual(row["geometry_crs"], "EPSG:4326")
        self.assertTrue(row["contained"])
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence.evidence_type, "FIELD_REGISTRATION")

        with self.store.tenant_transaction(tenant.id):
            with self.assertRaises(psycopg.Error):
                with self.store.connection.transaction():
                    self.store.connection.execute(
                        "UPDATE field_context_boundary_version SET reason=%s WHERE field_context_id=%s",
                        ("synthetic attempted rewrite", field.id),
                    )

        corrected = self.application.fields.correct_boundary(
            tenant.id,
            property_id=property_item.id,
            field_id=field.id,
            expected_boundary_version=field.boundary_version,
            expected_boundary_checksum=field.boundary_checksum,
            geometry_geojson=self.polygon(-46.997, -24.007, -46.993, -24.003),
            geometry_crs="EPSG:4326",
            source_reference="synthetic corrected integration field walk",
            observed_at="2026-09-25T12:00:00+00:00",
            classification=DataClassification.MANUAL_CONFIRMED,
            reason="synthetic integration correction",
            actor="integration-corrector",
        )
        self.assertEqual(corrected.boundary_version, 2)
        self.assertEqual(
            self.application.fields.get(tenant.id, field.id).boundary_version, 2
        )
        with self.store.tenant_transaction(tenant.id):
            versions = self.store.connection.execute(
                """SELECT version,source_reference FROM field_context_boundary_version
                    WHERE tenant_id=%s AND field_context_id=%s ORDER BY version""",
                (tenant.id, field.id),
            ).fetchall()
            registration_evidence = self.store.evidence_for_reference(
                tenant.id, field.id
            )
            correction_evidence = self.store.evidence_for_reference(
                tenant.id, corrected.boundary_version_id
            )
        self.assertEqual([item["version"] for item in versions], [1, 2])
        assert registration_evidence is not None
        assert correction_evidence is not None
        self.assertEqual(registration_evidence.evidence_type, "FIELD_REGISTRATION")
        self.assertEqual(correction_evidence.evidence_type, "FIELD_BOUNDARY_CORRECTION")
        with self.assertRaisesRegex(ValueError, "unchanged"):
            self.application.fields.correct_boundary(
                tenant.id,
                property_id=property_item.id,
                field_id=field.id,
                expected_boundary_version=corrected.boundary_version,
                expected_boundary_checksum=corrected.boundary_checksum,
                geometry_geojson=self.polygon(-46.997, -24.007, -46.993, -24.003),
                geometry_crs="EPSG:4326",
                source_reference="synthetic duplicate correction",
                observed_at="2026-09-25T13:00:00+00:00",
                classification=DataClassification.MANUAL_CONFIRMED,
                reason="synthetic duplicate",
                actor="integration-corrector",
            )
        with self.assertRaisesRegex(ValueError, "fully contained"):
            self.application.fields.correct_boundary(
                tenant.id,
                property_id=property_item.id,
                field_id=field.id,
                expected_boundary_version=corrected.boundary_version,
                expected_boundary_checksum=corrected.boundary_checksum,
                geometry_geojson=self.polygon(-47.01, -24.02, -46.98, -23.99),
                geometry_crs="EPSG:4326",
                source_reference="synthetic outside correction",
                observed_at="2026-09-25T14:00:00+00:00",
                classification=DataClassification.MANUAL_CONFIRMED,
                reason="synthetic outside",
                actor="integration-corrector",
            )

        with self.store.tenant_transaction(other_tenant.id):
            rows = self.store.connection.execute(
                "SELECT id FROM field_context WHERE tenant_id=%s", (tenant.id,)
            ).fetchall()
        self.assertEqual(rows, [])

    def test_field_delta_snapshot_constraints_reject_mismatched_context(self) -> None:
        tenant = self.tenant("Synthetic delta snapshot tenant")
        other_tenant = self.tenant("Other synthetic delta snapshot tenant")
        property_item = self.application.create_property(
            tenant.id,
            "Synthetic delta property",
            self.polygon(-47.0, -24.01, -46.99, -24.0),
            "EPSG:4326",
            boundary_source="synthetic integration boundary",
            classification=DataClassification.MANUAL_CONFIRMED,
        )
        other_property = self.application.create_property(
            tenant.id,
            "Other synthetic delta property",
            self.polygon(-48.0, -25.01, -47.99, -25.0),
            "EPSG:4326",
            boundary_source="synthetic integration boundary",
            classification=DataClassification.MANUAL_CONFIRMED,
        )
        field = self.application.fields.create(
            tenant.id,
            property_id=property_item.id,
            name="Synthetic delta field",
            status="ACTIVE",
            geometry_geojson=self.polygon(-46.998, -24.008, -46.992, -24.002),
            geometry_crs="EPSG:4326",
            source_reference="synthetic integration field walk",
            observed_at="2026-09-24T12:00:00+00:00",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor="integration-operator",
        )
        with self.store.tenant_transaction(tenant.id):
            snapshot = self.application.fields.repository.get_snapshot(
                tenant.id,
                property_item.id,
                field.id,
                field.boundary_version,
                field.boundary_checksum,
            )
            mismatch = self.application.fields.repository.get_snapshot(
                tenant.id,
                other_property.id,
                field.id,
                field.boundary_version,
                field.boundary_checksum,
            )
        self.assertIsNotNone(snapshot)
        self.assertIsNone(mismatch)
        with self.store.tenant_transaction(other_tenant.id):
            self.assertIsNone(
                self.application.fields.repository.get_snapshot(
                    other_tenant.id,
                    property_item.id,
                    field.id,
                    field.boundary_version,
                    field.boundary_checksum,
                )
            )
        with self.store.tenant_transaction(tenant.id):
            constraints = self.store.connection.execute(
                """SELECT conname FROM pg_constraint
                     WHERE conname IN (
                       'processing_job_field_snapshot_fk',
                       'derived_product_field_snapshot_fk',
                       'derived_product_job_field_snapshot_fk'
                     )"""
            ).fetchall()
        self.assertEqual(
            {row["conname"] for row in constraints},
            {
                "processing_job_field_snapshot_fk",
                "derived_product_field_snapshot_fk",
                "derived_product_job_field_snapshot_fk",
            },
        )
        with self.store.tenant_transaction(tenant.id):
            triggers = self.store.connection.execute(
                """SELECT tgname FROM pg_trigger
                     WHERE tgname IN (
                       'processing_job_field_delta_snapshot_immutable',
                       'derived_product_field_delta_snapshot_immutable'
                     ) AND NOT tgisinternal"""
            ).fetchall()
        self.assertEqual(
            {row["tgname"] for row in triggers},
            {
                "processing_job_field_delta_snapshot_immutable",
                "derived_product_field_delta_snapshot_immutable",
            },
        )
