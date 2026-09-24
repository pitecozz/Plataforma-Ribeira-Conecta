from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datetime import datetime, timedelta, timezone

from ribeira_platform.epistemology import (
    DataClassification,
    DecisionStatus,
    RuleAuthority,
)
from ribeira_platform.models import RuleDefinition, new_id
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.providers import ProviderMetadata, ProviderRegistry
from ribeira_platform.security import NetworkPolicy
from ribeira_platform.sources import HttpJsonSourceAdapter, SyntheticFixtureAdapter
from ribeira_platform.models import Property, Source
from ribeira_platform.storage import SQLiteStore


class IntegrityTests(unittest.TestCase):
    def test_existing_sqlite_schema_adds_field_rule_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE rules (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, version INTEGER NOT NULL,
                  name TEXT NOT NULL, authority TEXT NOT NULL, metric TEXT NOT NULL,
                  operator TEXT NOT NULL, threshold REAL NOT NULL, unit TEXT NOT NULL,
                  severity TEXT NOT NULL, status TEXT NOT NULL, approved_by TEXT,
                  valid_from TEXT NOT NULL, valid_until TEXT, scope_type TEXT NOT NULL,
                  scope_property_id TEXT, scope_asset_id TEXT, scope_customer_id TEXT
                );
                CREATE TABLE decisions (
                  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL,
                  rule_id TEXT, selected_rule_scope_type TEXT, subject_customer_id TEXT,
                  subject_asset_id TEXT, status TEXT NOT NULL, severity TEXT,
                  rationale TEXT NOT NULL, missing_data TEXT NOT NULL,
                  evidence_ids TEXT NOT NULL, classification TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                """
            )
            connection.close()

            store = SQLiteStore(path)
            rule_columns = {
                row["name"]
                for row in store.connection.execute("PRAGMA table_info(rules)")
            }
            decision_columns = {
                row["name"]
                for row in store.connection.execute("PRAGMA table_info(decisions)")
            }
            store.close()

            self.assertIn("scope_field_id", rule_columns)
            self.assertIn("subject_field_id", decision_columns)

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
            app.create_rule(
                RuleDefinition(
                    id=new_id(),
                    tenant_id=tenant.id,
                    version=1,
                    name="unapproved",
                    authority=RuleAuthority.REGRA_RIBEIRA,
                    metric="soil_moisture",
                    operator="<",
                    threshold=30,
                    unit="%",
                    severity="HIGH",
                    status="ACTIVE",
                    approved_by=None,
                    valid_from="2026-09-16T00:00:00+00:00",
                )
            )
        store.close()

    def test_expired_rule_is_not_active(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant = app.create_tenant("Tenant")
        expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        until = datetime.now(timezone.utc).isoformat()
        app.create_rule(
            RuleDefinition(
                id=new_id(),
                tenant_id=tenant.id,
                version=1,
                name="expired",
                authority=RuleAuthority.REGRA_RIBEIRA,
                metric="soil_moisture",
                operator="<",
                threshold=30,
                unit="%",
                severity="HIGH",
                status="ACTIVE",
                approved_by="approver",
                valid_from=expired,
                valid_until=until,
            )
        )
        self.assertIsNone(store.active_rule(tenant.id, "soil_moisture"))
        store.close()

    def test_http_adapter_rejects_non_http_endpoint(self) -> None:
        property = Property(new_id(), "tenant", "property")
        source = Source(
            new_id(), "tenant", "source", "provider", "provider", "file:///etc/passwd"
        )
        result = HttpJsonSourceAdapter().fetch_property_observations(
            "tenant", property, source
        )
        self.assertEqual(result.status.value, "SOURCE_UNAVAILABLE")
        self.assertEqual(result.observations, [])

    def test_timestamps_require_timezone_and_preserve_original_offset(self) -> None:
        property = Property(new_id(), "tenant", "property")
        source = Source(new_id(), "tenant", "source", "test", "fixture")
        adapter = SyntheticFixtureAdapter(
            [
                {
                    "metric": "soil_moisture",
                    "value": 27.4,
                    "unit": "%",
                    "observation_timestamp": "2026-09-16T13:42:11-03:00",
                }
            ]
        )
        result = adapter.fetch_property_observations("tenant", property, source)
        observation = result.observations[0]
        self.assertEqual(observation.observation_timestamp, "2026-09-16T16:42:11+00:00")
        self.assertEqual(
            observation.original_observation_timestamp, "2026-09-16T13:42:11-03:00"
        )
        with self.assertRaises(ValueError):
            SyntheticFixtureAdapter(
                [
                    {
                        "metric": "soil_moisture",
                        "value": 27.4,
                        "unit": "%",
                        "observation_timestamp": "2026-09-16T13:42:11",
                    }
                ]
            ).fetch_property_observations("tenant", property, source)

    def test_rule_timestamps_require_timezone(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant = app.create_tenant("Tenant")
        with self.assertRaises(ValueError):
            app.create_rule(
                RuleDefinition(
                    new_id(),
                    tenant.id,
                    1,
                    "naive rule",
                    RuleAuthority.REGRA_RIBEIRA,
                    "soil_moisture",
                    "<",
                    30,
                    "%",
                    "HIGH",
                    "DRAFT",
                    None,
                    "2026-09-16T00:00:00",
                )
            )
        store.close()

    def test_http_adapter_marks_invalid_provider_payload(self) -> None:
        property = Property(new_id(), "tenant", "property")
        source = Source(
            new_id(),
            "tenant",
            "source",
            "provider",
            "provider-1",
            "https://provider.example/observations",
        )

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"unexpected": true}'

        class Opener:
            def open(self, *_args, **_kwargs):
                return Response()

        registry = ProviderRegistry(
            [
                ProviderMetadata(
                    "provider-1",
                    "Provider",
                    "test",
                    "MANUAL_CONFIRMED",
                    "https://provider.example/observations",
                    None,
                    "none",
                    None,
                    None,
                    "1",
                    "ACTIVE",
                )
            ]
        )
        adapter = HttpJsonSourceAdapter(
            provider_registry=registry,
            network_policy=NetworkPolicy(allowed_hosts=frozenset({"provider.example"})),
        )
        with (
            patch(
                "ribeira_platform.sources.urllib.request.build_opener",
                return_value=Opener(),
            ),
            patch(
                "ribeira_platform.security.socket.getaddrinfo",
                return_value=[(None, None, None, None, ("93.184.216.34", 443))],
            ),
        ):
            result = adapter.fetch_property_observations("tenant", property, source)
        self.assertEqual(result.status.value, "INVALID_PAYLOAD")
        self.assertEqual(result.observations, [])


if __name__ == "__main__":
    unittest.main()
