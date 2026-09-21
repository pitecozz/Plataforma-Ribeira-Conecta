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
    BoundaryImport,
    Observation,
    Property,
    RuleDefinition,
    Source,
    Tenant,
    new_id,
)


class PostgresStore:
    """Production persistence adapter.

    The connection is intentionally opened with the non-owner application role.
    A request must use ``tenant_transaction`` so PostgreSQL RLS receives a
    transaction-local tenant context.
    """

    def __init__(self, dsn: str) -> None:
        # Kept only by the private process so it can open a separate
        # short-lived connection for worker heartbeats. It is never exposed
        # through an API response or log record.
        self.dsn = dsn
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
        # psycopg starts a transaction for SELECT when autocommit is disabled.
        # Health probes must close it, otherwise a long-lived API connection can
        # retain relation locks as ``idle in transaction``.
        with self.transaction():
            row = self.connection.execute("SELECT 1 AS ready").fetchone()
        return row is not None and row["ready"] == 1

    def upsert_source_health(
        self,
        provider: str,
        status: str,
        *,
        last_attempt: str | None = None,
        last_success: str | None = None,
        last_observation: str | None = None,
        latency_seconds: float | None = None,
        failure_code: str | None = None,
        failure_detail_sanitized: str | None = None,
    ) -> None:
        """Persist global provider health without credentials or response bodies."""
        self.connection.execute(
            """INSERT INTO source_health(
                   provider,status,last_attempt,last_success,last_observation,
                   latency_seconds,failure_code,failure_detail_sanitized
                 ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                 ON CONFLICT (provider) DO UPDATE SET
                   status=EXCLUDED.status,last_attempt=EXCLUDED.last_attempt,
                   last_success=COALESCE(EXCLUDED.last_success,source_health.last_success),
                   last_observation=COALESCE(EXCLUDED.last_observation,source_health.last_observation),
                   latency_seconds=EXCLUDED.latency_seconds,failure_code=EXCLUDED.failure_code,
                   failure_detail_sanitized=EXCLUDED.failure_detail_sanitized,updated_at=now()""",
            (
                provider,
                status,
                last_attempt,
                last_success,
                last_observation,
                latency_seconds,
                failure_code,
                failure_detail_sanitized,
            ),
        )

    def upsert_reservoir(
        self,
        *,
        provider: str,
        provider_reservoir_id: str,
        name: str,
        river_name: str | None,
    ) -> str:
        row = self.connection.execute(
            """INSERT INTO reservoir(id,provider,provider_reservoir_id,name,river_name)
                 VALUES (%s,%s,%s,%s,%s)
                 ON CONFLICT (provider,provider_reservoir_id) DO UPDATE
                   SET name=EXCLUDED.name,river_name=EXCLUDED.river_name
                 RETURNING id""",
            (new_id(), provider, provider_reservoir_id, name, river_name),
        ).fetchone()
        if row is None:
            raise RuntimeError("reservoir upsert did not return an identifier")
        return self._id(row["id"])

    def record_reservoir_operation_event(self, event: Any) -> bool:
        reservoir_id = self.upsert_reservoir(
            provider="COPEL",
            provider_reservoir_id=event.reservoir_provider_id,
            name=event.reservoir_name,
            river_name=event.river_name,
        )
        row = self.connection.execute(
            """INSERT INTO reservoir_operation_event(
                   id,reservoir_id,provider,event_type,published_at,effective_at,
                   numeric_value,unit,description_sanitized,source_reference,
                   classification,provenance
                 ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                 ON CONFLICT (provider,source_reference,event_type) DO NOTHING
                 RETURNING id""",
            (
                new_id(),
                reservoir_id,
                "COPEL",
                event.event_type,
                event.published_at,
                event.effective_at,
                event.numeric_value,
                event.unit,
                event.description_sanitized,
                event.source_reference,
                event.classification,
                json.dumps(
                    {
                        "parser": "copel_capivari_notice_v1",
                        "classification": event.classification,
                    }
                ),
            ),
        ).fetchone()
        return row is not None

    def record_climate_context(self, context: Any, *, fetched_at: str) -> bool:
        row = self.connection.execute(
            """INSERT INTO climate_context(
                   id,provider,issued_on,valid_window,enso_state,probability,
                   strength_category,source_reference,classification,source_fetched_at,provenance
                 ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                 ON CONFLICT (provider,issued_on,enso_state,source_reference) DO NOTHING
                 RETURNING id""",
            (
                new_id(),
                context.provider,
                context.issued_on,
                context.valid_window,
                context.enso_state,
                context.probability,
                context.strength_category,
                context.source_reference,
                context.classification,
                fetched_at,
                json.dumps(
                    {
                        "parser": "noaa_cpc_enso_v1",
                        "classification": context.classification,
                    }
                ),
            ),
        ).fetchone()
        return row is not None

    def vale_do_ribeira_situation(self) -> dict[str, Any]:
        """Return global facts only; lack of a source remains explicit."""
        health = self.connection.execute(
            "SELECT provider,status,last_success,last_observation,failure_code,updated_at FROM source_health ORDER BY provider"
        ).fetchall()
        events = self.connection.execute(
            """SELECT event_type,published_at,effective_at,numeric_value,unit,
                      description_sanitized,source_reference,classification
                 FROM reservoir_operation_event
                 ORDER BY published_at DESC LIMIT 20"""
        ).fetchall()
        climate = self.connection.execute(
            """SELECT provider,issued_on,valid_window,enso_state,probability,
                      strength_category,source_reference,classification
                 FROM climate_context ORDER BY issued_on DESC LIMIT 5"""
        ).fetchall()
        scope = self.connection.execute(
            "SELECT geometry_status,source_reference FROM geographic_scope WHERE scope_key='VALE_DO_RIBEIRA'"
        ).fetchone()
        return {
            "source_health": [dict(row) for row in health],
            "rainfall_summary": {
                "status": "UNKNOWN",
                "reason": "NO_REAL_HYDRO_OBSERVATIONS",
            },
            "river_summary": {
                "status": "UNKNOWN",
                "reason": "ANA_AUTH_REQUIRED_OR_SAISP_AUTOMATION_UNAVAILABLE",
            },
            "reservoir_events": [dict(row) for row in events],
            "climate_context": [dict(row) for row in climate],
            "active_alerts": [],
            "unknowns": [
                "No verified automated SAISP observation contract",
                "ANA hydrological inventory and telemetry require official OAuth credentials",
                "Vale do Ribeira geometry is not yet verified",
            ],
            "evidence": {
                "scope_geometry_status": scope["geometry_status"]
                if scope
                else "UNKNOWN",
                "scope_reference": scope["source_reference"] if scope else None,
            },
        }

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

    def create_property(self, item: Property, *, actor: str = "user") -> Property:
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
            """INSERT INTO property(id,tenant_id,name,geometry,geometry_crs,boundary_source,boundary_checksum,data_classification,created_at)
               VALUES (%s,%s,%s,CASE WHEN %s::text IS NULL THEN NULL ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::text),4326) END,%s,%s,%s,%s,%s)""",
            (
                item.id,
                item.tenant_id,
                item.name,
                geometry,
                geometry,
                item.geometry_crs,
                item.boundary_source,
                item.boundary_checksum,
                item.classification.value,
                item.created_at,
            ),
        )
        if (
            item.geometry_geojson is not None
            and item.boundary_source
            and item.boundary_checksum
        ):
            self.connection.execute(
                """INSERT INTO property_boundary_version(id,tenant_id,property_id,version,geometry,geometry_crs,boundary_source,data_classification,checksum,actor,effective_at)
                   VALUES (%s,%s,%s,1,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s,%s,%s,%s,%s,%s)""",
                (
                    new_id(),
                    item.tenant_id,
                    item.id,
                    geometry,
                    item.geometry_crs,
                    item.boundary_source,
                    item.classification.value,
                    item.boundary_checksum,
                    actor,
                    item.created_at,
                ),
            )
        return item

    def get_property(self, tenant_id: str, property_id: str) -> Property | None:
        row = self._one(
            "SELECT id,tenant_id,name,ST_AsGeoJSON(geometry) AS geometry_geojson,geometry_crs,data_classification,created_at,boundary_source,boundary_checksum,updated_at FROM property WHERE tenant_id=%s AND id=%s",
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
            row["boundary_source"],
            row["boundary_checksum"],
            row["updated_at"].isoformat() if row["updated_at"] else None,
        )

    def list_properties(self, tenant_id: str) -> list[Property]:
        rows = self.connection.execute(
            """SELECT id,tenant_id,name,ST_AsGeoJSON(geometry) AS geometry_geojson,
                      geometry_crs,data_classification,created_at,boundary_source,
                      boundary_checksum,updated_at
               FROM property WHERE tenant_id=%s ORDER BY created_at DESC, id""",
            (tenant_id,),
        ).fetchall()
        return [self._property_from_row(row) for row in rows]

    def _property_from_row(self, row: dict[str, Any]) -> Property:
        """Translate a property row without issuing a per-property query."""
        return Property(
            self._id(row["id"]),
            self._id(row["tenant_id"]),
            row["name"],
            json.loads(row["geometry_geojson"]) if row["geometry_geojson"] else None,
            row["geometry_crs"],
            DataClassification(row["data_classification"]),
            row["created_at"].isoformat(),
            row["boundary_source"],
            row["boundary_checksum"],
            row["updated_at"].isoformat() if row["updated_at"] else None,
        )

    def update_property_boundary(
        self,
        item: Property,
        *,
        actor: str,
        reason: str,
        effective_at: str,
        expected_checksum: str | None,
    ) -> int:
        # Lock the current property before allocating a version. This makes
        # max(version)+1 serial for one property while retaining independent
        # concurrency across different tenant/property pairs.
        locked = self.connection.execute(
            "SELECT id FROM property WHERE tenant_id=%s AND id=%s FOR UPDATE",
            (item.tenant_id, item.id),
        ).fetchone()
        if locked is None:
            raise LookupError("property not found in tenant")
        current = self.get_property(item.tenant_id, item.id)
        if current is None:
            raise LookupError("property not found in tenant")
        if current.boundary_checksum != expected_checksum:
            raise ValueError("boundary checksum no longer matches the current version")
        version_row = self.connection.execute(
            "SELECT coalesce(max(version), 0) + 1 AS version FROM property_boundary_version WHERE tenant_id=%s AND property_id=%s",
            (item.tenant_id, item.id),
        ).fetchone()
        if version_row is None:
            raise RuntimeError("boundary version could not be allocated")
        version = int(version_row["version"])
        geometry = json.dumps(item.geometry_geojson)
        self.connection.execute(
            """INSERT INTO property_boundary_version(id,tenant_id,property_id,version,geometry,geometry_crs,boundary_source,data_classification,checksum,reason,actor,effective_at)
               VALUES (%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),%s,%s,%s,%s,%s,%s,%s)""",
            (
                new_id(),
                item.tenant_id,
                item.id,
                version,
                geometry,
                item.geometry_crs,
                item.boundary_source,
                item.classification.value,
                item.boundary_checksum,
                reason,
                actor,
                effective_at,
            ),
        )
        self.connection.execute(
            """UPDATE property SET geometry=ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),geometry_crs=%s,boundary_source=%s,boundary_checksum=%s,data_classification=%s,updated_at=%s WHERE tenant_id=%s AND id=%s""",
            (
                geometry,
                item.geometry_crs,
                item.boundary_source,
                item.boundary_checksum,
                item.classification.value,
                effective_at,
                item.tenant_id,
                item.id,
            ),
        )
        return version

    def create_boundary_import(self, item: BoundaryImport) -> BoundaryImport:
        geometry = json.dumps(item.geometry_geojson) if item.geometry_geojson else None
        self.connection.execute(
            """INSERT INTO boundary_import(
                 id,tenant_id,property_id,original_filename,original_format,file_size_bytes,
                 file_sha256,object_reference,original_crs,detected_crs,target_crs,geometry,
                 geometry_checksum,boundary_source,data_classification,warnings,status,created_by,
                 expected_property_checksum,created_at
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                 CASE WHEN %s::text IS NULL THEN NULL ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::text),4326) END,
                 %s,%s,%s,%s::jsonb,%s,%s,%s,%s)""",
            (
                item.id,
                item.tenant_id,
                item.property_id,
                item.original_filename,
                item.original_format,
                item.file_size_bytes,
                item.file_sha256,
                item.object_reference,
                item.original_crs,
                item.detected_crs,
                item.target_crs,
                geometry,
                geometry,
                item.geometry_checksum,
                item.boundary_source,
                item.classification.value,
                json.dumps(item.warnings),
                item.status,
                item.created_by,
                item.expected_property_checksum,
                item.created_at,
            ),
        )
        return item

    def get_boundary_import(
        self, tenant_id: str, import_id: str, *, lock: bool = False
    ) -> BoundaryImport | None:
        suffix = " FOR UPDATE" if lock else ""
        row = self._one(
            """SELECT id,tenant_id,property_id,original_filename,original_format,file_size_bytes,
                      file_sha256,object_reference,original_crs,detected_crs,target_crs,
                      ST_AsGeoJSON(geometry) AS geometry_geojson,geometry_checksum,boundary_source,
                      data_classification,warnings,status,created_by,expected_property_checksum,
                      created_at,reviewed_by,review_reason,approved_boundary_version,reviewed_at
               FROM boundary_import WHERE tenant_id=%s AND id=%s"""
            + suffix,
            (tenant_id, import_id),
        )
        return self._boundary_import_from_row(row) if row else None

    def list_boundary_imports(
        self, tenant_id: str, property_id: str
    ) -> list[BoundaryImport]:
        rows = self.connection.execute(
            """SELECT id,tenant_id,property_id,original_filename,original_format,file_size_bytes,
                      file_sha256,object_reference,original_crs,detected_crs,target_crs,
                      ST_AsGeoJSON(geometry) AS geometry_geojson,geometry_checksum,boundary_source,
                      data_classification,warnings,status,created_by,expected_property_checksum,
                      created_at,reviewed_by,review_reason,approved_boundary_version,reviewed_at
               FROM boundary_import WHERE tenant_id=%s AND property_id=%s
               ORDER BY created_at DESC, id""",
            (tenant_id, property_id),
        ).fetchall()
        return [self._boundary_import_from_row(row) for row in rows]

    def review_boundary_import(
        self,
        item: BoundaryImport,
        *,
        status: str,
        reviewer: str,
        reason: str,
        approved_version: int | None = None,
    ) -> None:
        self.connection.execute(
            """UPDATE boundary_import SET status=%s,reviewed_by=%s,review_reason=%s,
                      reviewed_at=now(),approved_boundary_version=%s
               WHERE tenant_id=%s AND id=%s""",
            (status, reviewer, reason, approved_version, item.tenant_id, item.id),
        )

    def _boundary_import_from_row(self, row: dict[str, Any]) -> BoundaryImport:
        return BoundaryImport(
            self._id(row["id"]),
            self._id(row["tenant_id"]),
            self._id(row["property_id"]),
            row["original_filename"],
            row["original_format"],
            int(row["file_size_bytes"]),
            row["file_sha256"],
            row["object_reference"],
            row["original_crs"],
            row["detected_crs"],
            row["target_crs"],
            json.loads(row["geometry_geojson"]) if row["geometry_geojson"] else None,
            row["geometry_checksum"],
            row["boundary_source"],
            DataClassification(row["data_classification"]),
            list(row["warnings"]),
            row["status"],
            row["created_by"],
            row["expected_property_checksum"],
            row["created_at"].isoformat(),
            row["reviewed_by"],
            row["review_reason"],
            row["approved_boundary_version"],
            row["reviewed_at"].isoformat() if row["reviewed_at"] else None,
        )

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
