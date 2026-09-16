from __future__ import annotations

import unittest

from datetime import datetime, timedelta, timezone

from ribeira_platform.epistemology import DataClassification, DecisionStatus, RuleAuthority
from ribeira_platform.models import RuleDefinition, new_id
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.sources import HttpJsonSourceAdapter
from ribeira_platform.models import Property, Source
from ribeira_platform.storage import SQLiteStore


class IntegrityTests(unittest.TestCase):
    def test_no_active_rule_is_explicitly_inconclusive(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant = app.create_tenant("Tenant")
        property = app.create_property(tenant.id, "Property")
        source = app.create_source(tenant.id, "source", "manual", "none")
        result = app.evaluate(tenant.id, property.id)
        self.assertEqual(result.decision.status, DecisionStatus.INCONCLUSIVE)
        self.assertIn("active_rule:soil_moisture", result.decision.missing_data)
        self.assertEqual(result.decision.classification, DataClassification.UNKNOWN)
        self.assertIsNone(result.decision.rule_id)
        self.assertIsNotNone(source)
        store.close()

    def test_active_rule_requires_approval(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant = app.create_tenant("Tenant")
        with self.assertRaises(ValueError):
            app.create_rule(RuleDefinition(
                id=new_id(), tenant_id=tenant.id, version=1, name="unapproved", authority=RuleAuthority.REGRA_RIBEIRA,
                metric="soil_moisture", operator="<", threshold=30, unit="%", severity="HIGH", status="ACTIVE",
                approved_by=None, valid_from="2026-09-16T00:00:00+00:00",
            ))
        store.close()

    def test_expired_rule_is_not_active(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant = app.create_tenant("Tenant")
        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        until = datetime.now(timezone.utc).isoformat()
        app.create_rule(RuleDefinition(
            id=new_id(), tenant_id=tenant.id, version=1, name="expired", authority=RuleAuthority.REGRA_RIBEIRA,
            metric="soil_moisture", operator="<", threshold=30, unit="%", severity="HIGH", status="ACTIVE",
            approved_by="approver", valid_from=expired, valid_until=until,
        ))
        self.assertIsNone(store.active_rule(tenant.id, "soil_moisture"))
        store.close()

    def test_http_adapter_rejects_non_http_endpoint(self) -> None:
        property = Property(new_id(), "tenant", "property")
        source = Source(new_id(), "tenant", "source", "provider", "provider", "file:///etc/passwd")
        result = HttpJsonSourceAdapter().fetch_property_observations("tenant", property, source)
        self.assertEqual(result.status.value, "SOURCE_UNAVAILABLE")
        self.assertEqual(result.observations, [])


if __name__ == "__main__":
    unittest.main()
