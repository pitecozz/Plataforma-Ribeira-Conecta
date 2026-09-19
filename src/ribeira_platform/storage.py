from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from .epistemology import DataClassification, QualityFlag, RuleAuthority
from .audit_context import current_context
from .models import (
    Action,
    Alert,
    Decision,
    Evidence,
    Observation,
    Property,
    RuleDefinition,
    Source,
    Tenant,
)


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tenants (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS properties (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL, geometry_geojson TEXT, geometry_crs TEXT, boundary_source TEXT,
  classification TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_properties_tenant ON properties(tenant_id);
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL, source_type TEXT NOT NULL, provider TEXT NOT NULL,
  endpoint TEXT, source_version TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_tenant ON sources(tenant_id);
CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
  property_id TEXT NOT NULL REFERENCES properties(id), source_id TEXT NOT NULL REFERENCES sources(id),
  metric TEXT NOT NULL, value REAL, unit TEXT, observation_timestamp TEXT NOT NULL,
  ingestion_timestamp TEXT NOT NULL, processing_timestamp TEXT NOT NULL, original_observation_timestamp TEXT,
  idempotency_key TEXT, classification TEXT NOT NULL, quality_flag TEXT NOT NULL,
  raw_data_reference TEXT, dataset_version TEXT, spatial_resolution TEXT,
  temporal_resolution TEXT, crs TEXT, checksum TEXT
);
CREATE INDEX IF NOT EXISTS idx_observations_property_metric
  ON observations(tenant_id, property_id, metric, observation_timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS observations_idempotency_uq
  ON observations(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
  evidence_type TEXT NOT NULL, reference_id TEXT NOT NULL, classification TEXT NOT NULL,
  source_id TEXT REFERENCES sources(id), observed_at TEXT, transformation TEXT,
  limitations_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS evidence_reference_uq ON evidence(tenant_id, reference_id);
CREATE INDEX IF NOT EXISTS idx_evidence_tenant ON evidence(tenant_id);
CREATE TABLE IF NOT EXISTS rules (
  id TEXT NOT NULL, tenant_id TEXT NOT NULL REFERENCES tenants(id), version INTEGER NOT NULL,
  name TEXT NOT NULL, authority TEXT NOT NULL, metric TEXT NOT NULL, operator TEXT NOT NULL,
  threshold REAL NOT NULL, unit TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL,
  approved_by TEXT, valid_from TEXT NOT NULL, valid_until TEXT, created_at TEXT NOT NULL,
  PRIMARY KEY (id, version)
);
CREATE INDEX IF NOT EXISTS idx_rules_active ON rules(tenant_id, metric, status, version);
CREATE TABLE IF NOT EXISTS decisions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
  property_id TEXT NOT NULL REFERENCES properties(id), conclusion TEXT NOT NULL,
  classification TEXT NOT NULL, status TEXT NOT NULL, evidence_ids_json TEXT NOT NULL,
  rule_id TEXT, rule_version INTEGER, model_id TEXT, model_version TEXT,
  confidence REAL, limitations_json TEXT NOT NULL, missing_data_json TEXT NOT NULL,
  conflicts_json TEXT NOT NULL, recommended_action_json TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_property ON decisions(tenant_id, property_id, created_at);
CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
  property_id TEXT NOT NULL REFERENCES properties(id), alert_type TEXT NOT NULL,
  severity TEXT NOT NULL, status TEXT NOT NULL, title TEXT NOT NULL,
  decision_id TEXT NOT NULL REFERENCES decisions(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id),
  action_type TEXT NOT NULL, status TEXT NOT NULL, responsible_user_id TEXT,
  deadline TEXT, decision_id TEXT NOT NULL REFERENCES decisions(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS data_quality_events (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), property_id TEXT,
  source_id TEXT, event_type TEXT NOT NULL, details_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(id), actor TEXT NOT NULL,
  event_type TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
  payload_json TEXT NOT NULL, request_id TEXT, correlation_id TEXT, created_at TEXT NOT NULL
);
"""


class TenantBoundaryError(PermissionError):
    """Raised when a tenant-scoped lookup would cross the tenant boundary."""


class SQLiteStore:
    """Small local store with tenant-scoped queries.

    This is intentionally dependency-free for bootstrap and tests. Production
    deployment uses the equivalent PostGIS schema in db/migrations.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._transaction_depth = 0
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def _insert(self, sql: str, values: Iterable[Any]) -> None:
        self.connection.execute(sql, tuple(values))
        if self._transaction_depth == 0:
            self.connection.commit()

    @contextmanager
    def transaction(self):
        outer = self._transaction_depth > 0
        self._transaction_depth += 1
        try:
            yield self
            if not outer:
                self.connection.commit()
        except Exception:
            if not outer:
                self.connection.rollback()
            raise
        finally:
            self._transaction_depth -= 1

    @contextmanager
    def tenant_transaction(self, tenant_id: str | None, platform_admin: bool = False):
        with self.transaction():
            yield self

    def ready(self) -> bool:
        return self.connection.execute("SELECT 1").fetchone()[0] == 1

    def create_tenant(self, tenant: Tenant) -> Tenant:
        self._insert(
            "INSERT INTO tenants(id,name,created_at) VALUES (?,?,?)",
            (tenant.id, tenant.name, tenant.created_at),
        )
        return tenant

    def tenant_exists(self, tenant_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)
            ).fetchone()
            is not None
        )

    def create_property(self, item: Property, *, actor: str = "user") -> Property:
        del actor  # SQLite has no boundary-history table; retain API parity in tests.
        if not self.tenant_exists(item.tenant_id):
            raise TenantBoundaryError("tenant does not exist")
        self._insert(
            "INSERT INTO properties(id,tenant_id,name,geometry_geojson,geometry_crs,boundary_source,classification,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.tenant_id,
                item.name,
                json.dumps(item.geometry_geojson)
                if item.geometry_geojson is not None
                else None,
                item.geometry_crs,
                item.boundary_source,
                item.classification.value,
                item.created_at,
            ),
        )
        return item

    def get_property(self, tenant_id: str, property_id: str) -> Property | None:
        row = self.connection.execute(
            "SELECT * FROM properties WHERE tenant_id = ? AND id = ?",
            (tenant_id, property_id),
        ).fetchone()
        if row is None:
            return None
        return Property(
            row["id"],
            row["tenant_id"],
            row["name"],
            json.loads(row["geometry_geojson"]) if row["geometry_geojson"] else None,
            row["geometry_crs"],
            DataClassification(row["classification"]),
            row["created_at"],
            row["boundary_source"],
        )

    def list_properties(self, tenant_id: str) -> list[Property]:
        rows = self.connection.execute(
            "SELECT id FROM properties WHERE tenant_id = ? ORDER BY created_at DESC, id",
            (tenant_id,),
        ).fetchall()
        return [
            item
            for row in rows
            if (item := self.get_property(tenant_id, str(row["id"]))) is not None
        ]

    def create_source(self, item: Source) -> Source:
        if not self.tenant_exists(item.tenant_id):
            raise TenantBoundaryError("tenant does not exist")
        self._insert(
            "INSERT INTO sources(id,tenant_id,name,source_type,provider,endpoint,source_version,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.tenant_id,
                item.name,
                item.source_type,
                item.provider,
                item.endpoint,
                item.source_version,
                item.status,
                item.created_at,
            ),
        )
        return item

    def get_source(self, tenant_id: str, source_id: str) -> Source | None:
        row = self.connection.execute(
            "SELECT * FROM sources WHERE tenant_id = ? AND id = ?",
            (tenant_id, source_id),
        ).fetchone()
        if row is None:
            return None
        return Source(
            row["id"],
            row["tenant_id"],
            row["name"],
            row["source_type"],
            row["provider"],
            row["endpoint"],
            row["source_version"],
            row["status"],
            row["created_at"],
        )

    def create_observation(self, item: Observation) -> Observation:
        if self.get_property(item.tenant_id, item.property_id) is None:
            raise TenantBoundaryError(
                "property is outside tenant boundary or does not exist"
            )
        if self.get_source(item.tenant_id, item.source_id) is None:
            raise TenantBoundaryError(
                "source is outside tenant boundary or does not exist"
            )
        self._insert(
            """INSERT INTO observations(id,tenant_id,property_id,source_id,metric,value,unit,observation_timestamp,
               ingestion_timestamp,processing_timestamp,original_observation_timestamp,idempotency_key,classification,
               quality_flag,raw_data_reference,dataset_version,spatial_resolution,temporal_resolution,crs,checksum)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item.id,
                item.tenant_id,
                item.property_id,
                item.source_id,
                item.metric,
                item.value,
                item.unit,
                item.observation_timestamp,
                item.ingestion_timestamp,
                item.processing_timestamp,
                item.original_observation_timestamp,
                item.idempotency_key,
                item.classification.value,
                item.quality_flag.value,
                item.raw_data_reference,
                item.dataset_version,
                item.spatial_resolution,
                item.temporal_resolution,
                item.crs,
                item.checksum,
            ),
        )
        return item

    def observations_for_property(
        self, tenant_id: str, property_id: str
    ) -> list[Observation]:
        rows = self.connection.execute(
            "SELECT * FROM observations WHERE tenant_id = ? AND property_id = ? ORDER BY observation_timestamp",
            (tenant_id, property_id),
        ).fetchall()
        return self._observation_rows(rows)

    def observation_by_idempotency(
        self, tenant_id: str, idempotency_key: str
    ) -> Observation | None:
        rows = self.connection.execute(
            "SELECT * FROM observations WHERE tenant_id = ? AND idempotency_key = ? LIMIT 1",
            (tenant_id, idempotency_key),
        ).fetchall()
        return self._observation_rows(rows)[0] if rows else None

    @staticmethod
    def _observation_rows(rows: list[sqlite3.Row]) -> list[Observation]:
        return [
            Observation(
                row["id"],
                row["tenant_id"],
                row["property_id"],
                row["source_id"],
                row["metric"],
                row["value"],
                row["unit"],
                row["observation_timestamp"],
                row["ingestion_timestamp"],
                row["processing_timestamp"],
                row["original_observation_timestamp"],
                row["idempotency_key"],
                DataClassification(row["classification"]),
                QualityFlag(row["quality_flag"]),
                row["raw_data_reference"],
                row["dataset_version"],
                row["spatial_resolution"],
                row["temporal_resolution"],
                row["crs"],
                row["checksum"],
            )
            for row in rows
        ]

    def create_evidence(self, item: Evidence) -> Evidence:
        self._insert(
            "INSERT INTO evidence(id,tenant_id,evidence_type,reference_id,classification,source_id,observed_at,transformation,limitations_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.tenant_id,
                item.evidence_type,
                item.reference_id,
                item.classification.value,
                item.source_id,
                item.observed_at,
                item.transformation,
                json.dumps(item.limitations),
                item.created_at,
            ),
        )
        return item

    def evidence_for_reference(
        self, tenant_id: str, reference_id: str
    ) -> Evidence | None:
        row = self.connection.execute(
            "SELECT * FROM evidence WHERE tenant_id = ? AND reference_id = ? ORDER BY created_at LIMIT 1",
            (tenant_id, reference_id),
        ).fetchone()
        if row is None:
            return None
        return Evidence(
            row["id"],
            row["tenant_id"],
            row["evidence_type"],
            row["reference_id"],
            DataClassification(row["classification"]),
            row["source_id"],
            row["observed_at"],
            row["transformation"],
            json.loads(row["limitations_json"]),
            row["created_at"],
        )

    def active_rule(self, tenant_id: str, metric: str) -> RuleDefinition | None:
        rows = self.connection.execute(
            "SELECT * FROM rules WHERE tenant_id = ? AND metric = ? AND status = 'ACTIVE' ORDER BY version DESC",
            (tenant_id, metric),
        ).fetchall()
        now = datetime.now(timezone.utc)
        row = None
        for candidate in rows:
            try:
                valid_from = datetime.fromisoformat(candidate["valid_from"])
                valid_until = (
                    datetime.fromisoformat(candidate["valid_until"])
                    if candidate["valid_until"]
                    else None
                )
            except ValueError:
                continue
            if (
                valid_from.tzinfo is not None
                and (valid_until is None or valid_until.tzinfo is not None)
                and valid_from <= now
                and (valid_until is None or now < valid_until)
            ):
                row = candidate
                break
        if row is None:
            return None
        return RuleDefinition(
            row["id"],
            row["tenant_id"],
            row["version"],
            row["name"],
            RuleAuthority(row["authority"]),
            row["metric"],
            row["operator"],
            row["threshold"],
            row["unit"],
            row["severity"],
            row["status"],
            row["approved_by"],
            row["valid_from"],
            row["valid_until"],
            row["created_at"],
        )

    def create_rule(self, item: RuleDefinition) -> RuleDefinition:
        self._insert(
            "INSERT INTO rules(id,tenant_id,version,name,authority,metric,operator,threshold,unit,severity,status,approved_by,valid_from,valid_until,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.tenant_id,
                item.version,
                item.name,
                item.authority.value,
                item.metric,
                item.operator,
                item.threshold,
                item.unit,
                item.severity,
                item.status,
                item.approved_by,
                item.valid_from,
                item.valid_until,
                item.created_at,
            ),
        )
        return item

    def create_decision(self, item: Decision) -> Decision:
        self._insert(
            """INSERT INTO decisions(id,tenant_id,property_id,conclusion,classification,status,evidence_ids_json,rule_id,rule_version,
               model_id,model_version,confidence,limitations_json,missing_data_json,conflicts_json,recommended_action_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item.id,
                item.tenant_id,
                item.property_id,
                item.conclusion,
                item.classification.value,
                item.status.value,
                json.dumps(item.evidence_ids),
                item.rule_id,
                item.rule_version,
                item.model_id,
                item.model_version,
                item.confidence,
                json.dumps(item.limitations),
                json.dumps(item.missing_data),
                json.dumps(item.conflicts),
                json.dumps(item.recommended_action)
                if item.recommended_action is not None
                else None,
                item.created_at,
            ),
        )
        return item

    def create_alert(self, item: Alert) -> Alert:
        self._insert(
            "INSERT INTO alerts(id,tenant_id,property_id,alert_type,severity,status,title,decision_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.tenant_id,
                item.property_id,
                item.alert_type,
                item.severity,
                item.status,
                item.title,
                item.decision_id,
                item.created_at,
            ),
        )
        return item

    def create_action(self, item: Action) -> Action:
        self._insert(
            "INSERT INTO actions(id,tenant_id,action_type,status,responsible_user_id,deadline,decision_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.tenant_id,
                item.action_type,
                item.status,
                item.responsible_user_id,
                item.deadline,
                item.decision_id,
                item.created_at,
            ),
        )
        return item

    def create_quality_event(
        self,
        tenant_id: str,
        property_id: str | None,
        source_id: str | None,
        event_type: str,
        details: dict[str, Any],
        event_id: str,
        created_at: str,
    ) -> None:
        self._insert(
            "INSERT INTO data_quality_events(id,tenant_id,property_id,source_id,event_type,details_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (
                event_id,
                tenant_id,
                property_id,
                source_id,
                event_type,
                json.dumps(details),
                created_at,
            ),
        )

    def audit(
        self,
        tenant_id: str,
        actor: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        event_id: str,
        created_at: str,
    ) -> None:
        request_id, correlation_id = current_context()
        self._insert(
            "INSERT INTO audit_log(id,tenant_id,actor,event_type,entity_type,entity_id,payload_json,request_id,correlation_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                tenant_id,
                actor,
                event_type,
                entity_type,
                entity_id,
                json.dumps(payload),
                request_id,
                correlation_id,
                created_at,
            ),
        )

    def count(self, table: str, tenant_id: str) -> int:
        queries = {
            "observations": "SELECT COUNT(*) FROM observations WHERE tenant_id = ?",
            "evidence": "SELECT COUNT(*) FROM evidence WHERE tenant_id = ?",
            "decisions": "SELECT COUNT(*) FROM decisions WHERE tenant_id = ?",
            "alerts": "SELECT COUNT(*) FROM alerts WHERE tenant_id = ?",
            "actions": "SELECT COUNT(*) FROM actions WHERE tenant_id = ?",
            "audit_log": "SELECT COUNT(*) FROM audit_log WHERE tenant_id = ?",
            "data_quality_events": "SELECT COUNT(*) FROM data_quality_events WHERE tenant_id = ?",
        }
        if table not in queries:
            raise ValueError("table is not allowed")
        row = self.connection.execute(queries[table], (tenant_id,)).fetchone()
        if row is None:
            raise RuntimeError("count query returned no row")
        return int(row[0])

    def close_without_commit(self) -> None:
        self.connection.rollback()
