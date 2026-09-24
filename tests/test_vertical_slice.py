from __future__ import annotations

import json
import unittest

from ribeira_platform.epistemology import (
    DataClassification,
    DecisionStatus,
    IngestionStatus,
    RuleAuthority,
)
from ribeira_platform.business import Asset, CommercialClassification
from ribeira_platform.models import RuleDefinition, new_id
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.sources import SyntheticFixtureAdapter
from ribeira_platform.storage import SQLiteStore


class VerticalSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore()
        self.app = RibeiraApplication(self.store)
        self.tenant = self.app.create_tenant("Tenant A")
        self.property = self.app.create_property(
            self.tenant.id,
            "Sítio Ribeira",
            {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-47.0, -24.0],
                        [-47.0, -24.1],
                        [-47.1, -24.1],
                        [-47.1, -24.0],
                        [-47.0, -24.0],
                    ]
                ],
            },
            "EPSG:4326",
        )
        self.source = self.app.create_source(
            self.tenant.id, "sensor de umidade", "IOT", "fixture"
        )

    def tearDown(self) -> None:
        self.store.close()

    def activate_rule(
        self, metric: str = "soil_moisture", threshold: float = 30.0
    ) -> None:
        self.app.create_rule(
            RuleDefinition(
                id=new_id(),
                tenant_id=self.tenant.id,
                version=1,
                name="limiar explícito de umidade",
                authority=RuleAuthority.REGRA_AGRONOMICA,
                metric=metric,
                operator="<",
                threshold=threshold,
                unit="%",
                severity="HIGH",
                status="ACTIVE",
                approved_by="agronomist-test",
                valid_from="2026-09-16T00:00:00+00:00",
            )
        )

    def test_source_unavailable_is_not_fabricated(self) -> None:
        self.activate_rule()
        result = self.app.ingest(self.tenant.id, self.property.id, self.source.id)
        self.assertEqual(result.fetch.status, IngestionStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(result.observation_ids, [])
        self.assertEqual(self.store.count("data_quality_events", self.tenant.id), 1)

        decision = self.app.evaluate(self.tenant.id, self.property.id).decision
        self.assertEqual(decision.status, DecisionStatus.INCONCLUSIVE)
        self.assertEqual(decision.classification, DataClassification.UNKNOWN)
        self.assertEqual(decision.confidence, None)
        self.assertIn("soil_moisture observation", decision.missing_data)

    def test_rule_trigger_has_evidence_alert_action_and_audit(self) -> None:
        self.activate_rule()
        self.app.adapters[self.source.id] = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": 27.4,
                    "unit": "%",
                    "observation_timestamp": "2026-09-16T13:42:11-03:00",
                    "quality_flag": "VALID",
                    "dataset_version": "fixture-v1",
                    "crs": "EPSG:4326",
                }
            ]
        )
        ingestion = self.app.ingest(self.tenant.id, self.property.id, self.source.id)
        self.assertEqual(ingestion.fetch.status, IngestionStatus.INGESTED)
        self.assertEqual(len(ingestion.observation_ids), 1)
        self.assertEqual(len(ingestion.evidence_ids), 1)

        result = self.app.evaluate(self.tenant.id, self.property.id)
        self.assertEqual(result.decision.status, DecisionStatus.ACTIONABLE)
        self.assertEqual(result.decision.classification, DataClassification.INFERRED)
        self.assertIsNone(result.decision.confidence)
        self.assertEqual(len(result.decision.evidence_ids), 1)
        self.assertEqual(self.store.count("evidence", self.tenant.id), 1)
        self.assertIsNotNone(result.alert)
        self.assertIsNotNone(result.action)
        self.assertIsNone(result.action.responsible_user_id)
        self.assertIsNone(result.action.deadline)
        # Property creation also records registration of its automatic refresh policy.
        self.assertEqual(self.store.count("audit_log", self.tenant.id), 6)

        self.app.complete_action(
            self.tenant.id,
            result.action.id,
            outcome_detail="Técnico confirmou a irrigação corretiva no talhão.",
            outcome_classification=DataClassification.MANUAL_CONFIRMED,
            evidence_ids=result.decision.evidence_ids,
            actor="field-technician",
            completed_at="2026-09-16T18:00:00+00:00",
        )
        action = self.store.connection.execute(
            "SELECT status, completed_at, completed_by, outcome_detail, "
            "outcome_classification, outcome_evidence_ids_json "
            "FROM actions WHERE id=?",
            (result.action.id,),
        ).fetchone()
        self.assertEqual(action["status"], "COMPLETED")
        self.assertEqual(action["completed_at"], "2026-09-16T18:00:00+00:00")
        self.assertEqual(action["completed_by"], "field-technician")
        self.assertEqual(
            action["outcome_detail"],
            "Técnico confirmou a irrigação corretiva no talhão.",
        )
        self.assertEqual(action["outcome_classification"], "MANUAL_CONFIRMED")
        self.assertEqual(
            json.loads(action["outcome_evidence_ids_json"]),
            result.decision.evidence_ids,
        )
        self.assertEqual(self.store.count("audit_log", self.tenant.id), 7)

        with self.assertRaises(LookupError):
            self.app.complete_action(
                self.tenant.id,
                result.action.id,
                outcome_detail="The same action cannot be completed twice.",
                outcome_classification=DataClassification.MANUAL_CONFIRMED,
                evidence_ids=result.decision.evidence_ids,
                actor="field-technician",
            )

    def test_null_does_not_become_zero_or_false(self) -> None:
        self.activate_rule()
        self.app.adapters[self.source.id] = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": None,
                    "unit": "%",
                    "observation_timestamp": "2026-09-16T13:42:11-03:00",
                    "quality_flag": "UNKNOWN",
                }
            ]
        )
        self.app.ingest(self.tenant.id, self.property.id, self.source.id)
        observations = self.store.observations_for_property(
            self.tenant.id, self.property.id
        )
        self.assertEqual(len(observations), 1)
        self.assertIsNone(observations[0].value)
        decision = self.app.evaluate(self.tenant.id, self.property.id).decision
        self.assertEqual(decision.status, DecisionStatus.INCONCLUSIVE)
        self.assertEqual(decision.classification, DataClassification.UNKNOWN)

    def test_conflicting_sources_are_not_resolved_silently(self) -> None:
        self.activate_rule()
        second = self.app.create_source(
            self.tenant.id, "sensor concorrente", "IOT", "fixture"
        )
        timestamp = "2026-09-16T13:42:11-03:00"
        for source, value in ((self.source, 27.0), (second, 45.0)):
            self.app.adapters[source.id] = SyntheticFixtureAdapter(
                [
                    {
                        "metric": "soil_moisture",
                        "value": value,
                        "unit": "%",
                        "observation_timestamp": timestamp,
                        "quality_flag": "VALID",
                    }
                ]
            )
            self.app.ingest(self.tenant.id, self.property.id, source.id)
        result = self.app.evaluate(self.tenant.id, self.property.id)
        self.assertEqual(result.decision.status, DecisionStatus.CONFLICTING)
        self.assertEqual(result.decision.classification, DataClassification.CONFLICTING)
        self.assertEqual(result.decision.confidence, None)
        self.assertEqual(result.alert.alert_type, "DATA_CONFLICT")
        self.assertEqual(result.action.action_type, "resolver conflito de dados")

    def test_repeated_ingestion_is_idempotent(self) -> None:
        self.activate_rule()
        self.app.adapters[self.source.id] = SyntheticFixtureAdapter(
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
        first = self.app.ingest(self.tenant.id, self.property.id, self.source.id)
        second = self.app.ingest(self.tenant.id, self.property.id, self.source.id)
        self.assertEqual(first.observation_ids, second.observation_ids)
        self.assertEqual(first.evidence_ids, second.evidence_ids)
        self.assertEqual(self.store.count("observations", self.tenant.id), 1)
        self.assertEqual(self.store.count("evidence", self.tenant.id), 1)

    def test_customer_scoped_rule_requires_active_link_and_snapshots_context(
        self,
    ) -> None:
        customer = self.app.business.create_customer(
            self.tenant.id, "Customer context", actor="commercial"
        )
        self.app.business.link_customer_property(
            self.tenant.id,
            customer.id,
            self.property.id,
            "OWNER",
            "2026-09-16T00:00:00+00:00",
            None,
            actor="commercial",
        )
        self.app.create_rule(
            RuleDefinition(
                id=new_id(),
                tenant_id=self.tenant.id,
                version=1,
                name="Customer moisture threshold",
                authority=RuleAuthority.REGRA_AGRONOMICA,
                metric="soil_moisture",
                operator="<",
                threshold=30,
                unit="%",
                severity="HIGH",
                status="ACTIVE",
                approved_by="agronomist-test",
                valid_from="2026-09-16T00:00:00+00:00",
                scope_type="CUSTOMER",
                scope_customer_id=customer.id,
            )
        )
        self.app.adapters[self.source.id] = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": 27.0,
                    "unit": "%",
                    "observation_timestamp": "2026-09-24T13:42:11+00:00",
                    "quality_flag": "VALID",
                }
            ]
        )
        self.app.ingest(self.tenant.id, self.property.id, self.source.id)
        result = self.app.evaluate(self.tenant.id, self.property.id)
        self.assertEqual(result.decision.status, DecisionStatus.ACTIONABLE)
        self.assertEqual(result.decision.selected_rule_scope_type, "CUSTOMER")
        self.assertEqual(result.decision.subject_customer_id, customer.id)
        history = self.app.decision_history_for_property(
            self.tenant.id, self.property.id
        )
        self.assertEqual(history[0]["selected_rule_scope_type"], "CUSTOMER")
        self.assertEqual(history[0]["subject_customer_id"], customer.id)
        audit = self.store.connection.execute(
            "SELECT payload_json FROM audit_log WHERE tenant_id=? AND entity_id=?",
            (self.tenant.id, result.decision.id),
        ).fetchone()
        self.assertEqual(
            json.loads(audit["payload_json"])["subject_customer_id"], customer.id
        )

    def test_expired_customer_property_link_does_not_apply_rule(self) -> None:
        customer = self.app.business.create_customer(
            self.tenant.id, "Former customer", actor="commercial"
        )
        self.app.business.link_customer_property(
            self.tenant.id,
            customer.id,
            self.property.id,
            "FORMER_OPERATOR",
            "2020-01-01T00:00:00+00:00",
            "2021-01-01T00:00:00+00:00",
            actor="commercial",
        )
        self.app.create_rule(
            RuleDefinition(
                id=new_id(),
                tenant_id=self.tenant.id,
                version=1,
                name="Former customer moisture threshold",
                authority=RuleAuthority.REGRA_AGRONOMICA,
                metric="soil_moisture",
                operator="<",
                threshold=30,
                unit="%",
                severity="HIGH",
                status="ACTIVE",
                approved_by="agronomist-test",
                valid_from="2026-09-16T00:00:00+00:00",
                scope_type="CUSTOMER",
                scope_customer_id=customer.id,
            )
        )
        decision = self.app.evaluate(self.tenant.id, self.property.id).decision
        self.assertEqual(decision.status, DecisionStatus.INCONCLUSIVE)
        self.assertIsNone(decision.rule_id)
        self.assertIn("active_rule:soil_moisture", decision.missing_data)

    def test_equally_specific_customer_rules_are_conflicting_not_version_selected(
        self,
    ) -> None:
        customer = self.app.business.create_customer(
            self.tenant.id, "Customer context", actor="commercial"
        )
        self.app.business.link_customer_property(
            self.tenant.id,
            customer.id,
            self.property.id,
            "OWNER",
            "2026-09-16T00:00:00+00:00",
            None,
            actor="commercial",
        )
        for name, version in (("Customer threshold A", 1), ("Customer threshold B", 2)):
            self.app.create_rule(
                RuleDefinition(
                    id=new_id(),
                    tenant_id=self.tenant.id,
                    version=version,
                    name=name,
                    authority=RuleAuthority.REGRA_AGRONOMICA,
                    metric="soil_moisture",
                    operator="<",
                    threshold=30,
                    unit="%",
                    severity="HIGH",
                    status="ACTIVE",
                    approved_by="agronomist-test",
                    valid_from="2026-09-16T00:00:00+00:00",
                    scope_type="CUSTOMER",
                    scope_customer_id=customer.id,
                )
            )
        result = self.app.evaluate(self.tenant.id, self.property.id)
        self.assertEqual(result.decision.status, DecisionStatus.CONFLICTING)
        self.assertIsNone(result.decision.rule_id)
        self.assertEqual(result.decision.selected_rule_scope_type, "CUSTOMER")
        self.assertEqual(result.decision.subject_customer_id, customer.id)
        self.assertEqual(
            result.decision.conflicts[0]["type"], "equally_specific_active_rules"
        )

    def test_property_scoped_rule_is_not_applied_to_another_property(self) -> None:
        other_property = self.app.create_property(self.tenant.id, "Other property")
        self.app.create_rule(
            RuleDefinition(
                id=new_id(),
                tenant_id=self.tenant.id,
                version=1,
                name="Property-only moisture threshold",
                authority=RuleAuthority.REGRA_AGRONOMICA,
                metric="soil_moisture",
                operator="<",
                threshold=30,
                unit="%",
                severity="HIGH",
                status="ACTIVE",
                approved_by="agronomist-test",
                valid_from="2026-09-16T00:00:00+00:00",
                scope_type="PROPERTY",
                scope_property_id=self.property.id,
            )
        )
        decision = self.app.evaluate(self.tenant.id, other_property.id).decision
        self.assertEqual(decision.status, DecisionStatus.INCONCLUSIVE)
        self.assertIsNone(decision.rule_id)
        self.assertIn("active_rule:soil_moisture", decision.missing_data)

    def test_asset_scoped_rule_requires_factual_context_and_never_leaks_to_property(
        self,
    ) -> None:
        asset = Asset(
            new_id(),
            self.tenant.id,
            "IRRIGATION_PUMP",
            "Pump A",
            None,
            "ACTIVE",
            self.property.id,
            None,
            CommercialClassification.MANUAL_CONFIRMED,
            None,
            None,
            "operator inventory 2026-09-24",
            "2026-09-24T12:00:00+00:00",
            {"condition": "UNKNOWN"},
        )
        self.app.business.register_asset(asset, actor="operator")
        asset_evidence = self.store.evidence_for_reference(self.tenant.id, asset.id)
        assert asset_evidence is not None
        self.app.create_rule(
            RuleDefinition(
                id=new_id(),
                tenant_id=self.tenant.id,
                version=1,
                name="Pump-specific moisture threshold",
                authority=RuleAuthority.REGRA_AGRONOMICA,
                metric="soil_moisture",
                operator="<",
                threshold=30,
                unit="%",
                severity="HIGH",
                status="ACTIVE",
                approved_by="agronomist-test",
                valid_from="2026-09-16T00:00:00+00:00",
                scope_type="ASSET",
                scope_asset_id=asset.id,
            )
        )
        self.app.adapters[self.source.id] = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": 27.0,
                    "unit": "%",
                    "observation_timestamp": "2026-09-24T13:42:11+00:00",
                    "quality_flag": "VALID",
                }
            ]
        )
        self.app.ingest(self.tenant.id, self.property.id, self.source.id)

        property_decision = self.app.evaluate(self.tenant.id, self.property.id).decision
        self.assertIsNone(property_decision.rule_id)
        self.assertIsNone(property_decision.subject_asset_id)

        result = self.app.evaluate_asset(self.tenant.id, asset.id, actor="operator")
        self.assertEqual(result.decision.status, DecisionStatus.ACTIONABLE)
        self.assertEqual(result.decision.rule_id is not None, True)
        self.assertEqual(result.decision.subject_asset_id, asset.id)
        self.assertIn(asset_evidence.id, result.decision.evidence_ids)
        self.assertIn("não é uma medição", result.decision.limitations[-1])
        history = self.app.decision_history_for_property(
            self.tenant.id, self.property.id
        )
        self.assertEqual(history[0]["subject_asset_id"], asset.id)

        unlinked_asset = Asset(
            new_id(),
            self.tenant.id,
            "PORTABLE_SENSOR",
            "Unlinked asset",
            None,
            "ACTIVE",
            None,
            None,
            CommercialClassification.MANUAL_CONFIRMED,
        )
        self.app.business.register_asset(unlinked_asset, actor="operator")
        with self.assertRaises(ValueError):
            self.app.create_rule(
                RuleDefinition(
                    id=new_id(),
                    tenant_id=self.tenant.id,
                    version=1,
                    name="Unlinked asset rule",
                    authority=RuleAuthority.REGRA_AGRONOMICA,
                    metric="soil_moisture",
                    operator="<",
                    threshold=30,
                    unit="%",
                    severity="HIGH",
                    status="ACTIVE",
                    approved_by="agronomist-test",
                    valid_from="2026-09-16T00:00:00+00:00",
                    scope_type="ASSET",
                    scope_asset_id=unlinked_asset.id,
                )
            )

    def test_field_scoped_rule_requires_explicit_field_evaluation(self) -> None:
        field = self.app.fields.create(
            self.tenant.id,
            property_id=self.property.id,
            name="Talhao operacional A",
            status="ACTIVE",
            geometry_geojson={
                "type": "Polygon",
                "coordinates": [
                    [
                        [-47.01, -24.01],
                        [-47.01, -24.05],
                        [-47.05, -24.05],
                        [-47.05, -24.01],
                        [-47.01, -24.01],
                    ]
                ],
            },
            geometry_crs="EPSG:4326",
            source_reference="synthetic_test_data field walk",
            observed_at="2026-09-24T12:00:00+00:00",
            classification=DataClassification.MANUAL_CONFIRMED,
            actor="operator",
        )
        field_evidence = self.store.evidence_for_reference(self.tenant.id, field.id)
        assert field_evidence is not None
        self.app.create_rule(
            RuleDefinition(
                id=new_id(),
                tenant_id=self.tenant.id,
                version=1,
                name="Field-specific moisture threshold",
                authority=RuleAuthority.REGRA_AGRONOMICA,
                metric="soil_moisture",
                operator="<",
                threshold=30,
                unit="%",
                severity="HIGH",
                status="ACTIVE",
                approved_by="agronomist-test",
                valid_from="2026-09-16T00:00:00+00:00",
                scope_type="FIELD",
                scope_field_id=field.id,
            )
        )
        self.app.adapters[self.source.id] = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": 27.0,
                    "unit": "%",
                    "observation_timestamp": "2026-09-24T13:42:11+00:00",
                    "quality_flag": "VALID",
                }
            ]
        )
        self.app.ingest(self.tenant.id, self.property.id, self.source.id)

        property_decision = self.app.evaluate(self.tenant.id, self.property.id).decision
        self.assertIsNone(property_decision.rule_id)
        self.assertIsNone(property_decision.subject_field_id)

        result = self.app.evaluate_field(self.tenant.id, field.id, actor="operator")
        self.assertEqual(result.decision.status, DecisionStatus.ACTIONABLE)
        self.assertEqual(result.decision.selected_rule_scope_type, "FIELD")
        self.assertEqual(result.decision.subject_field_id, field.id)
        self.assertIn(field_evidence.id, result.decision.evidence_ids)
        self.assertIn("não é evidência de cultura", result.decision.limitations[-1])
        history = self.app.decision_history_for_property(
            self.tenant.id, self.property.id
        )
        self.assertEqual(history[0]["subject_field_id"], field.id)


if __name__ == "__main__":
    unittest.main()
