"""Field/talhão context tests use only explicit synthetic geometry."""

from __future__ import annotations

import unittest

from shapely.geometry import Polygon, mapping

from ribeira_platform.epistemology import DataClassification
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.storage import SQLiteStore


class FieldContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore()
        self.application = RibeiraApplication(self.store)
        self.tenant = self.application.create_tenant("Synthetic field tenant")
        self.other_tenant = self.application.create_tenant("Other synthetic tenant")
        self.property = self.application.create_property(
            self.tenant.id,
            "TEST_PROPERTY_ONLY",
            mapping(Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])),
            "EPSG:4326",
        )

    def tearDown(self) -> None:
        self.store.close()

    @staticmethod
    def field_geometry() -> dict:
        return mapping(
            Polygon([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8), (0.2, 0.2)])
        )

    def test_registers_source_backed_non_legal_field_with_evidence_and_audit(
        self,
    ) -> None:
        field = self.application.fields.create(
            self.tenant.id,
            property_id=self.property.id,
            name="TEST_FIELD_ONLY",
            status="ACTIVE",
            geometry_geojson=self.field_geometry(),
            geometry_crs="EPSG:4326",
            source_reference="synthetic_test_data field walk",
            observed_at="2026-09-24T12:00:00+00:00",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor="test-operator",
        )

        self.assertEqual(field.boundary_version, 1)
        self.assertEqual(field.property_id, self.property.id)
        self.assertEqual(
            self.application.fields.list_for_property(self.tenant.id, self.property.id),
            [field],
        )
        evidence = self.store.evidence_for_reference(self.tenant.id, field.id)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.evidence_type, "FIELD_REGISTRATION")
        audit = self.store.connection.execute(
            "SELECT event_type FROM audit_log WHERE tenant_id=? AND entity_id=?",
            (self.tenant.id, field.id),
        ).fetchone()
        self.assertEqual(audit["event_type"], "FIELD_REGISTERED")

    def test_rejects_geometry_outside_property_and_cross_tenant_read(self) -> None:
        outside = mapping(
            Polygon([(0.8, 0.8), (1.2, 0.8), (1.2, 1.2), (0.8, 1.2), (0.8, 0.8)])
        )
        with self.assertRaisesRegex(ValueError, "fully contained"):
            self.application.fields.create(
                self.tenant.id,
                property_id=self.property.id,
                name="OUTSIDE_TEST_FIELD",
                status="ACTIVE",
                geometry_geojson=outside,
                geometry_crs="EPSG:4326",
                source_reference="synthetic_test_data",
                observed_at="2026-09-24T12:00:00+00:00",
                classification=DataClassification.MANUAL_CONFIRMED,
                actor="test-operator",
            )
        with self.assertRaisesRegex(LookupError, "property not found"):
            self.application.fields.list_for_property(
                self.other_tenant.id, self.property.id
            )

    def test_snapshot_lookup_fails_closed_for_tenant_property_version_and_checksum(
        self,
    ) -> None:
        field = self.application.fields.create(
            self.tenant.id,
            property_id=self.property.id,
            name="TEST_FIELD_SNAPSHOT",
            status="ACTIVE",
            geometry_geojson=self.field_geometry(),
            geometry_crs="EPSG:4326",
            source_reference="synthetic_test_data",
            observed_at="2026-09-24T12:00:00+00:00",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor="test-operator",
        )
        other_property = self.application.create_property(
            self.tenant.id,
            "OTHER_TEST_PROPERTY",
            mapping(Polygon([(2, 2), (3, 2), (3, 3), (2, 3), (2, 2)])),
            "EPSG:4326",
        )
        self.assertIsNotNone(
            self.application.fields.repository.get_snapshot(
                self.tenant.id,
                self.property.id,
                field.id,
                field.boundary_version,
                field.boundary_checksum,
            )
        )
        invalid_contexts = [
            (
                self.other_tenant.id,
                self.property.id,
                field.boundary_version,
                field.boundary_checksum,
            ),
            (
                self.tenant.id,
                other_property.id,
                field.boundary_version,
                field.boundary_checksum,
            ),
            (
                self.tenant.id,
                self.property.id,
                field.boundary_version + 1,
                field.boundary_checksum,
            ),
            (self.tenant.id, self.property.id, field.boundary_version, "0" * 64),
        ]
        for tenant_id, property_id, version, checksum in invalid_contexts:
            self.assertIsNone(
                self.application.fields.repository.get_snapshot(
                    tenant_id, property_id, field.id, version, checksum
                )
            )
