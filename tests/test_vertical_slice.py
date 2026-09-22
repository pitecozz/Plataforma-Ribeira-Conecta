from __future__ import annotations

import json
import unittest

from ribeira_platform.epistemology import (
    DataClassification,
    DecisionStatus,
    IngestionStatus,
    RuleAuthority,
)
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
        self.assertEqual(self.store.count("audit_log", self.tenant.id), 5)

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
        self.assertEqual(self.store.count("audit_log", self.tenant.id), 6)

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


if __name__ == "__main__":
    unittest.main()
