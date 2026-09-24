"""Tenant-safe persistence for non-legal field/talhão context."""

from __future__ import annotations

import json
from typing import Any, Iterable

from shapely.geometry import shape

from .boundaries import validate_boundary
from .epistemology import DataClassification
from .models import Evidence, FieldContext, new_id, now_utc
from .time_utils import parse_aware


SQLITE_FIELD_CONTEXT_SCHEMA = """
CREATE TABLE IF NOT EXISTS field_context (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL,
 name TEXT NOT NULL, status TEXT NOT NULL, source_reference TEXT NOT NULL,
 observed_at TEXT NOT NULL, data_classification TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(tenant_id,id)
);
CREATE INDEX IF NOT EXISTS field_context_property_idx
 ON field_context(tenant_id,property_id,created_at DESC);
CREATE TABLE IF NOT EXISTS field_context_boundary_version (
 id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
 field_context_id TEXT NOT NULL REFERENCES field_context(id), property_id TEXT NOT NULL,
 version INTEGER NOT NULL, geometry_geojson TEXT NOT NULL, geometry_crs TEXT NOT NULL,
 geometry_checksum TEXT NOT NULL, source_reference TEXT NOT NULL, observed_at TEXT NOT NULL,
 data_classification TEXT NOT NULL, reason TEXT NOT NULL, created_by TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(field_context_id,version)
);
"""


class FieldContextRepository:
    """Translate the narrow field aggregate for SQLite tests and PostgreSQL."""

    def __init__(self, store: Any) -> None:
        self.store, self.connection = store, store.connection
        self.postgres = store.__class__.__name__ == "PostgresStore"
        if not self.postgres:
            self.connection.executescript(SQLITE_FIELD_CONTEXT_SCHEMA)

    @property
    def placeholder(self) -> str:
        return "%s" if self.postgres else "?"

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        return self.connection.execute(sql, tuple(params))

    @staticmethod
    def _timestamp(value: Any) -> str:
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def create(self, item: FieldContext, *, actor: str) -> FieldContext:
        p = self.placeholder
        self._execute(
            f"""INSERT INTO field_context(
                 id,tenant_id,property_id,name,status,source_reference,observed_at,data_classification,created_at
               ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p})""",  # nosec B608 - fixed internal SQL and placeholder
            [
                item.id,
                item.tenant_id,
                item.property_id,
                item.name,
                item.status,
                item.source_reference,
                item.observed_at,
                item.classification.value,
                item.created_at,
            ],
        )
        geometry_column = "geometry" if self.postgres else "geometry_geojson"
        geometry_value = (
            f"ST_SetSRID(ST_GeomFromGeoJSON({p}::text),4326)" if self.postgres else p
        )
        self._execute(
            f"""INSERT INTO field_context_boundary_version(
                 id,tenant_id,field_context_id,property_id,version,{geometry_column},geometry_crs,
                 geometry_checksum,source_reference,observed_at,data_classification,reason,created_by,created_at
               ) VALUES ({p},{p},{p},{p},{p},{geometry_value},{p},{p},{p},{p},{p},{p},{p},{p})""",  # nosec B608 - fixed internal SQL and geometry expression
            [
                new_id(),
                item.tenant_id,
                item.id,
                item.property_id,
                item.boundary_version,
                json.dumps(item.geometry_geojson, separators=(",", ":")),
                item.geometry_crs,
                item.boundary_checksum,
                item.source_reference,
                item.observed_at,
                item.classification.value,
                "initial non-legal field registration",
                actor,
                item.created_at,
            ],
        )
        return item

    def list_for_property(self, tenant_id: str, property_id: str) -> list[FieldContext]:
        p = self.placeholder
        geometry = (
            "ST_AsGeoJSON(version.geometry)"
            if self.postgres
            else "version.geometry_geojson"
        )
        rows = self._execute(
            f"""SELECT field.id,field.tenant_id,field.property_id,field.name,field.status,
                       {geometry} AS geometry_geojson,version.geometry_crs,version.version,
                       version.geometry_checksum,field.source_reference,field.observed_at,
                       field.data_classification,field.created_at
                  FROM field_context field
                  JOIN field_context_boundary_version version
                    ON version.tenant_id=field.tenant_id AND version.field_context_id=field.id
                   AND version.version=1
                 WHERE field.tenant_id={p} AND field.property_id={p}
                 ORDER BY field.name ASC,field.id ASC""",  # nosec B608 - fixed internal SQL and placeholder
            [tenant_id, property_id],
        ).fetchall()
        return [
            FieldContext(
                str(row["id"]),
                str(row["tenant_id"]),
                str(row["property_id"]),
                str(row["name"]),
                str(row["status"]),
                json.loads(row["geometry_geojson"])
                if isinstance(row["geometry_geojson"], str)
                else row["geometry_geojson"],
                str(row["geometry_crs"]),
                int(row["version"]),
                str(row["geometry_checksum"]),
                str(row["source_reference"]),
                self._timestamp(row["observed_at"]),
                DataClassification(str(row["data_classification"])),
                self._timestamp(row["created_at"]),
            )
            for row in rows
        ]

    def get(self, tenant_id: str, field_id: str) -> FieldContext | None:
        p = self.placeholder
        geometry = (
            "ST_AsGeoJSON(version.geometry)"
            if self.postgres
            else "version.geometry_geojson"
        )
        row = self._execute(
            f"""SELECT field.id,field.tenant_id,field.property_id,field.name,field.status,
                       {geometry} AS geometry_geojson,version.geometry_crs,version.version,
                       version.geometry_checksum,field.source_reference,field.observed_at,
                       field.data_classification,field.created_at
                  FROM field_context field
                  JOIN field_context_boundary_version version
                    ON version.tenant_id=field.tenant_id AND version.field_context_id=field.id
                   AND version.version=1
                 WHERE field.tenant_id={p} AND field.id={p}""",  # nosec B608 - fixed internal SQL and placeholder
            [tenant_id, field_id],
        ).fetchone()
        if row is None:
            return None
        return FieldContext(
            str(row["id"]),
            str(row["tenant_id"]),
            str(row["property_id"]),
            str(row["name"]),
            str(row["status"]),
            json.loads(row["geometry_geojson"])
            if isinstance(row["geometry_geojson"], str)
            else row["geometry_geojson"],
            str(row["geometry_crs"]),
            int(row["version"]),
            str(row["geometry_checksum"]),
            str(row["source_reference"]),
            self._timestamp(row["observed_at"]),
            DataClassification(str(row["data_classification"])),
            self._timestamp(row["created_at"]),
        )


class FieldContextApplication:
    """Register a field only when its source, time and containing property exist."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.repository = FieldContextRepository(store)

    def create(
        self,
        tenant_id: str,
        *,
        property_id: str,
        name: str,
        status: str,
        geometry_geojson: dict[str, Any],
        geometry_crs: str,
        source_reference: str,
        observed_at: str,
        classification: DataClassification,
        actor: str,
        platform_admin: bool = False,
    ) -> FieldContext:
        name = name.strip()
        status = status.strip()
        if not name:
            raise ValueError("field name must not be blank")
        if not status:
            raise ValueError("field status must not be blank")
        source_reference = source_reference.strip()
        if not source_reference:
            raise ValueError("field source_reference must not be blank")
        parse_aware(observed_at)
        geometry, _, checksum = validate_boundary(geometry_geojson, geometry_crs)
        geometry = json.loads(json.dumps(geometry))
        with self.store.tenant_transaction(tenant_id, platform_admin):
            property_item = self.store.get_property(tenant_id, property_id)
            if property_item is None:
                raise LookupError("property not found in tenant")
            if property_item.geometry_geojson is None:
                raise ValueError(
                    "field registration requires a persisted property boundary"
                )
            if not shape(property_item.geometry_geojson).covers(shape(geometry)):
                raise ValueError(
                    "field geometry must be fully contained by the property boundary"
                )
            item = FieldContext(
                new_id(),
                tenant_id,
                property_id,
                name,
                status,
                geometry,
                geometry_crs.upper(),
                1,
                checksum,
                source_reference,
                observed_at,
                classification,
            )
            self.repository.create(item, actor=actor)
            evidence = self.store.create_evidence(
                Evidence(
                    id=new_id(),
                    tenant_id=tenant_id,
                    evidence_type="FIELD_REGISTRATION",
                    reference_id=item.id,
                    classification=classification,
                    source_id=None,
                    observed_at=observed_at,
                    transformation=(
                        "field registration retained as submitted; no crop, soil, management, "
                        "legal-boundary, or agronomic conclusion was inferred"
                    ),
                    limitations=[
                        "the field/talhão is non-legal operational context bounded by the submitted geometry",
                        "it is not a survey, crop declaration, laboratory observation, or management recommendation",
                    ],
                )
            )
            self.store.audit(
                tenant_id,
                actor,
                "FIELD_REGISTERED",
                "field_context",
                item.id,
                {
                    "property_id": property_id,
                    "boundary_version": 1,
                    "classification": classification.value,
                    "evidence_id": evidence.id,
                    "source_reference_recorded": True,
                    "observed_at": observed_at,
                },
                new_id(),
                now_utc(),
            )
        return item

    def list_for_property(
        self, tenant_id: str, property_id: str, *, platform_admin: bool = False
    ) -> list[FieldContext]:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            if self.store.get_property(tenant_id, property_id) is None:
                raise LookupError("property not found in tenant")
            return self.repository.list_for_property(tenant_id, property_id)

    def get(
        self, tenant_id: str, field_id: str, *, platform_admin: bool = False
    ) -> FieldContext:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            item = self.repository.get(tenant_id, field_id)
            if item is None:
                raise LookupError("field context not found in tenant")
            return item
