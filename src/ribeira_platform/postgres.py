from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row

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


class PostgresStore:
    """Production persistence adapter.

    The connection is intentionally opened with the non-owner application role.
    A request must use ``tenant_transaction`` so PostgreSQL RLS receives a
    transaction-local tenant context.
    """

    def __init__(self, dsn: str) -> None:
        self.connection = psycopg.connect(dsn, row_factory=dict_row)
        self._transaction_depth = 0

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self):
        outer = self._transaction_depth > 0
        self._transaction_depth += 1
        try:
            if outer:
                yield self
            else:
                with self.connection.transaction():
                    yield self
        finally:
            self._transaction_depth -= 1

    @contextmanager
    def tenant_transaction(self, tenant_id: str | None, platform_admin: bool = False):
        with self.transaction():
            self.connection.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (tenant_id or "",)
            )
            self.connection.execute(
                "SELECT set_config('app.platform_admin', %s, true)",
                ("true" if platform_admin else "false",),
            )
            yield self

    def ready(self) -> bool:
        row = self.connection.execute("SELECT 1 AS ready").fetchone()
        return row is not None and row["ready"] == 1

    def _one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        return self.connection.execute(sql, tuple(params)).fetchone()

    @staticmethod
    def _id(value: Any) -> str:
        return str(value)

    def tenant_exists(self, tenant_id: str) -> bool:
        return self._one("SELECT 1 FROM tenant WHERE id = %s", (tenant_id,)) is not None

    def create_tenant(self, tenant: Tenant) -> Tenant:
        self.connection.execute(
            "INSERT INTO tenant(id,name,created_at) VALUES (%s,%s,%s)",
            (tenant.id, tenant.name, tenant.created_at),
        )
        return tenant

    def create_property(self, item: Property) -> Property:
        if not self.tenant_exists(item.tenant_id):
            raise PermissionError("tenant does not exist or is outside context")
        if item.geometry_crs and item.geometry_crs.upper() not in {
            "EPSG:4326",
            "CRS:84",
        }:
            raise ValueError(
                "PostGIS adapter currently accepts only EPSG:4326 geometry"
            )
        geometry = (
            json.dumps(item.geometry_geojson)
            if item.geometry_geojson is not None
            else None
        )
        self.connection.execute(
            """INSERT INTO property(id,tenant_id,name,geometry,geometry_crs,data_classification,created_at)
               VALUES (%s,%s,%s,CASE WHEN %s::text IS NULL THEN NULL ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::text),4326) END,%s,%s,%s)""",
            (
                item.id,
                item.tenant_id,
                item.name,
                geometry,
                geometry,
                item.geometry_crs,
                item.classification.value,
                item.created_at,
            ),
        )
        return item

    def get_property(self, tenant_id: str, property_id: str) -> Property | None:
        row = self._one(
            "SELECT id,tenant_id,name,ST_AsGeoJSON(geometry) AS geometry_geojson,geometry_crs,data_classification,created_at FROM property WHERE tenant_id=%s AND id=%s",
            (tenant_id, property_id),
        )
        if row is None:
            return None
        return Property(
            self._id(row["id"]),
            self._id(row["tenant_id"]),
            row["name"],
            json.loads(row["geometry_geojson"]) if row["geometry_geojson"] else None,
            row["geometry_crs"],
            DataClassification(row["data_classification"]),
            row["created_at"].isoformat(),
        )

    def list_properties(self, tenant_id: str) -> list[Property]:
        rows = self.connection.execute(
            "SELECT id FROM property WHERE tenant_id=%s ORDER BY created_at DESC, id",
            (tenant_id,),
        ).fetchall()
        return [
            item
            for row in rows
            if (item := self.get_property(tenant_id, self._id(row["id"]))) is not None
        ]

    def create_source(self, item: Source) -> Source:
        if not self.tenant_exists(item.tenant_id):
            raise PermissionError("tenant does not exist or is outside context")
        self.connection.execute(
            "INSERT INTO source(id,tenant_id,name,source_type,provider,endpoint,source_version,status,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
        row = self._one(
            "SELECT * FROM source WHERE tenant_id=%s AND id=%s", (tenant_id, source_id)
        )
        if row is None:
            return None
        return Source(
            self._id(row["id"]),
            self._id(row["tenant_id"]),
            row["name"],
            row["source_type"],
            row["provider"],
            row["endpoint"],
            row["source_version"],
            row["status"],
            row["created_at"].isoformat(),
        )

    def create_observation(self, item: Observation) -> Observation:
        if (
            self.get_property(item.tenant_id, item.property_id) is None
            or self.get_source(item.tenant_id, item.source_id) is None
        ):
            raise PermissionError("observation reference is outside tenant context")
        self.connection.execute(
            """INSERT INTO observation(id,tenant_id,property_id,source_id,metric,value,unit,observation_timestamp,
               ingestion_timestamp,processing_timestamp,original_observation_timestamp,idempotency_key,data_classification,
               quality_flag,raw_data_reference,dataset_version,spatial_resolution,temporal_resolution,crs,checksum)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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

    def _observation(self, row: dict[str, Any]) -> Observation:
        def iso(value: Any) -> str:
            return value.isoformat() if hasattr(value, "isoformat") else str(value)

        return Observation(
            self._id(row["id"]),
            self._id(row["tenant_id"]),
            self._id(row["property_id"]),
            self._id(row["source_id"]),
            row["metric"],
            row["value"],
            row["unit"],
            iso(row["observation_timestamp"]),
            iso(row["ingestion_timestamp"]),
            iso(row["processing_timestamp"]),
            row["original_observation_timestamp"],
            row["idempotency_key"],
            DataClassification(row["data_classification"]),
            QualityFlag(row["quality_flag"]),
            row["raw_data_reference"],
            row["dataset_version"],
            row["spatial_resolution"],
            row["temporal_resolution"],
            row["crs"],
            row["checksum"],
        )

    def observations_for_property(
        self, tenant_id: str, property_id: str
    ) -> list[Observation]:
        rows = self.connection.execute(
            "SELECT * FROM observation WHERE tenant_id=%s AND property_id=%s ORDER BY observation_timestamp",
            (tenant_id, property_id),
        ).fetchall()
        return [self._observation(row) for row in rows]

    def observation_by_idempotency(
        self, tenant_id: str, idempotency_key: str
    ) -> Observation | None:
        row = self._one(
            "SELECT * FROM observation WHERE tenant_id=%s AND idempotency_key=%s",
            (tenant_id, idempotency_key),
        )
        return self._observation(row) if row else None

    def create_evidence(self, item: Evidence) -> Evidence:
        self.connection.execute(
            "INSERT INTO evidence(id,tenant_id,evidence_type,reference_id,data_classification,source_id,observed_at,transformation,limitations,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
        row = self._one(
            "SELECT * FROM evidence WHERE tenant_id=%s AND reference_id=%s",
            (tenant_id, reference_id),
        )
        if row is None:
            return None
        return Evidence(
            self._id(row["id"]),
            self._id(row["tenant_id"]),
            row["evidence_type"],
            self._id(row["reference_id"]),
            DataClassification(row["data_classification"]),
            self._id(row["source_id"]) if row["source_id"] else None,
            row["observed_at"].isoformat() if row["observed_at"] else None,
            row["transformation"],
            row["limitations"]
            if isinstance(row["limitations"], list)
            else json.loads(row["limitations"]),
            row["created_at"].isoformat(),
        )

    def active_rule(self, tenant_id: str, metric: str) -> RuleDefinition | None:
        row = self._one(
            "SELECT * FROM rule_definition WHERE tenant_id=%s AND metric=%s AND status='ACTIVE' AND valid_from <= now() AND (valid_until IS NULL OR now() < valid_until) ORDER BY version DESC LIMIT 1",
            (tenant_id, metric),
        )
        if row is None:
            return None
        return RuleDefinition(
            self._id(row["id"]),
            self._id(row["tenant_id"]),
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
            row["valid_from"].isoformat(),
            row["valid_until"].isoformat() if row["valid_until"] else None,
            row["created_at"].isoformat(),
        )

    def create_rule(self, item: RuleDefinition) -> RuleDefinition:
        self.connection.execute(
            "INSERT INTO rule_definition(id,tenant_id,version,name,authority,metric,operator,threshold,unit,severity,status,approved_by,valid_from,valid_until,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
        self.connection.execute(
            """INSERT INTO decision(id,tenant_id,property_id,conclusion,data_classification,status,evidence_ids,rule_id,rule_version,model_id,model_version,confidence,limitations,missing_data,conflicts,recommended_action,created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
        self.connection.execute(
            "INSERT INTO alert(id,tenant_id,property_id,alert_type,severity,status,title,decision_id,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
        self.connection.execute(
            "INSERT INTO action(id,tenant_id,action_type,status,responsible_user_id,deadline,decision_id,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
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
        self.connection.execute(
            "INSERT INTO data_quality_event(id,tenant_id,property_id,source_id,event_type,details,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
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
        self.connection.execute(
            "INSERT INTO audit_log(id,tenant_id,actor,event_type,entity_type,entity_id,payload,request_id,correlation_id,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
            "observation": "SELECT COUNT(*) AS count FROM observation WHERE tenant_id=%s",
            "evidence": "SELECT COUNT(*) AS count FROM evidence WHERE tenant_id=%s",
            "decision": "SELECT COUNT(*) AS count FROM decision WHERE tenant_id=%s",
            "alert": "SELECT COUNT(*) AS count FROM alert WHERE tenant_id=%s",
            "action": "SELECT COUNT(*) AS count FROM action WHERE tenant_id=%s",
            "audit_log": "SELECT COUNT(*) AS count FROM audit_log WHERE tenant_id=%s",
            "data_quality_event": "SELECT COUNT(*) AS count FROM data_quality_event WHERE tenant_id=%s",
        }
        if table not in queries:
            raise ValueError("table is not allowed")
        row = self.connection.execute(queries[table], (tenant_id,)).fetchone()
        if row is None:
            raise RuntimeError("count query returned no row")
        return int(row["count"])
