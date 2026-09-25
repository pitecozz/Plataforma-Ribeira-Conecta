"""Tenant-safe persistence for non-legal field/talhão context."""

from __future__ import annotations

import json
from typing import Any, Iterable

from shapely.geometry import shape

from .boundaries import validate_boundary
from .epistemology import DataClassification
from .models import Evidence, FieldContext, new_id, now_utc
from .time_utils import parse_aware


class FieldBoundaryConflict(ValueError):
    pass


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
        version_id = new_id()
        self._execute(
            f"""INSERT INTO field_context_boundary_version(
                 id,tenant_id,field_context_id,property_id,version,{geometry_column},geometry_crs,
                 geometry_checksum,source_reference,observed_at,data_classification,reason,created_by,created_at
               ) VALUES ({p},{p},{p},{p},{p},{geometry_value},{p},{p},{p},{p},{p},{p},{p},{p})""",  # nosec B608 - fixed internal SQL and geometry expression
            [
                version_id,
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
        return FieldContext(
            item.id,
            item.tenant_id,
            item.property_id,
            item.name,
            item.status,
            item.geometry_geojson,
            item.geometry_crs,
            item.boundary_version,
            item.boundary_checksum,
            item.source_reference,
            item.observed_at,
            item.classification,
            item.created_at,
            version_id,
        )

    def append_boundary_version(
        self,
        current: FieldContext,
        *,
        expected_boundary_version: int,
        expected_boundary_checksum: str,
        geometry_geojson: dict[str, Any],
        geometry_crs: str,
        geometry_checksum: str,
        source_reference: str,
        observed_at: str,
        classification: DataClassification,
        reason: str,
        actor: str,
    ) -> FieldContext:
        p = self.placeholder
        if self.postgres:
            locked = self._execute(
                f"""SELECT id FROM field_context
                     WHERE tenant_id={p} AND property_id={p} AND id={p}
                     FOR UPDATE""",  # nosec B608 - fixed internal SQL and placeholder
                [current.tenant_id, current.property_id, current.id],
            ).fetchone()
            if locked is None:
                raise LookupError("field context not found in tenant property")
        row = self._execute(
            f"""SELECT field.id,field.name,field.status,field.created_at,
                       version.version,version.geometry_checksum
                  FROM field_context field
                  JOIN field_context_boundary_version version
                    ON version.tenant_id=field.tenant_id
                   AND version.field_context_id=field.id
                 WHERE field.tenant_id={p} AND field.property_id={p} AND field.id={p}
                 ORDER BY version.version DESC LIMIT 1""",  # nosec B608 - fixed internal SQL and placeholder
            [current.tenant_id, current.property_id, current.id],
        ).fetchone()
        if row is None:
            raise LookupError("field context not found in tenant property")
        current_version = int(row["version"])
        current_checksum = str(row["geometry_checksum"])
        if (
            current_version != expected_boundary_version
            or current_checksum != expected_boundary_checksum
        ):
            raise FieldBoundaryConflict(
                "field boundary changed after it was loaded; refresh before correcting"
            )
        if current_checksum == geometry_checksum:
            raise ValueError("field boundary correction geometry is unchanged")
        next_version = current_version + 1
        version_id = new_id()
        geometry_column = "geometry" if self.postgres else "geometry_geojson"
        geometry_value = (
            f"ST_SetSRID(ST_GeomFromGeoJSON({p}::text),4326)" if self.postgres else p
        )
        created_at = now_utc()
        self._execute(
            f"""INSERT INTO field_context_boundary_version(
                 id,tenant_id,field_context_id,property_id,version,{geometry_column},geometry_crs,
                 geometry_checksum,source_reference,observed_at,data_classification,reason,created_by,created_at
               ) VALUES ({p},{p},{p},{p},{p},{geometry_value},{p},{p},{p},{p},{p},{p},{p},{p})""",  # nosec B608 - fixed internal SQL and geometry expression
            [
                version_id,
                current.tenant_id,
                current.id,
                current.property_id,
                next_version,
                json.dumps(geometry_geojson, separators=(",", ":")),
                geometry_crs,
                geometry_checksum,
                source_reference,
                observed_at,
                classification.value,
                reason,
                actor,
                created_at,
            ],
        )
        return FieldContext(
            current.id,
            current.tenant_id,
            current.property_id,
            str(row["name"]),
            str(row["status"]),
            geometry_geojson,
            geometry_crs,
            next_version,
            geometry_checksum,
            source_reference,
            observed_at,
            classification,
            self._timestamp(row["created_at"]),
            version_id,
        )

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
                       version.geometry_checksum,version.source_reference,version.observed_at,
                       version.data_classification,field.created_at,version.id AS boundary_version_id
                  FROM field_context field
                  JOIN field_context_boundary_version version
                    ON version.tenant_id=field.tenant_id AND version.field_context_id=field.id
                   AND version.version=(SELECT MAX(latest.version)
                                          FROM field_context_boundary_version latest
                                         WHERE latest.tenant_id=field.tenant_id
                                           AND latest.field_context_id=field.id)
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
                str(row["boundary_version_id"]),
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
                       version.geometry_checksum,version.source_reference,version.observed_at,
                       version.data_classification,field.created_at,version.id AS boundary_version_id
                  FROM field_context field
                  JOIN field_context_boundary_version version
                    ON version.tenant_id=field.tenant_id AND version.field_context_id=field.id
                   AND version.version=(SELECT MAX(latest.version)
                                          FROM field_context_boundary_version latest
                                         WHERE latest.tenant_id=field.tenant_id
                                           AND latest.field_context_id=field.id)
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
            str(row["boundary_version_id"]),
        )

    def get_snapshot(
        self,
        tenant_id: str,
        property_id: str,
        field_id: str,
        version: int,
        checksum: str,
    ) -> FieldContext | None:
        p = self.placeholder
        geometry = (
            "ST_AsGeoJSON(version.geometry)"
            if self.postgres
            else "version.geometry_geojson"
        )
        row = self._execute(
            f"""SELECT field.id,field.tenant_id,field.property_id,field.name,field.status,
                       {geometry} AS geometry_geojson,version.geometry_crs,version.version,
                       version.geometry_checksum,version.source_reference,version.observed_at,
                       version.data_classification,field.created_at
                  FROM field_context field
                  JOIN field_context_boundary_version version
                    ON version.tenant_id=field.tenant_id AND version.field_context_id=field.id
                 WHERE field.tenant_id={p} AND field.property_id={p} AND field.id={p}
                   AND version.property_id={p} AND version.version={p}
                   AND version.geometry_checksum={p}""",  # nosec B608 - fixed internal SQL and placeholder
            [tenant_id, property_id, field_id, property_id, version, checksum],
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
            item = self.repository.create(item, actor=actor)
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

    def correct_boundary(
        self,
        tenant_id: str,
        *,
        property_id: str,
        field_id: str,
        expected_boundary_version: int,
        expected_boundary_checksum: str,
        geometry_geojson: dict[str, Any],
        geometry_crs: str,
        source_reference: str,
        observed_at: str,
        classification: DataClassification,
        reason: str,
        actor: str,
        platform_admin: bool = False,
    ) -> FieldContext:
        source_reference = source_reference.strip()
        reason = reason.strip()
        if not source_reference:
            raise ValueError("field source_reference must not be blank")
        if not reason:
            raise ValueError("field boundary correction reason must not be blank")
        parse_aware(observed_at)
        geometry, _, checksum = validate_boundary(geometry_geojson, geometry_crs)
        geometry = json.loads(json.dumps(geometry))
        with self.store.tenant_transaction(tenant_id, platform_admin):
            property_item = self.store.get_property(tenant_id, property_id)
            if property_item is None:
                raise LookupError("property not found in tenant")
            current = self.repository.get(tenant_id, field_id)
            if current is None or current.property_id != property_id:
                raise LookupError("field context not found in tenant property")
            if property_item.geometry_geojson is None:
                raise ValueError(
                    "field correction requires a persisted property boundary"
                )
            if not shape(property_item.geometry_geojson).covers(shape(geometry)):
                raise ValueError(
                    "field geometry must be fully contained by the property boundary"
                )
            item = self.repository.append_boundary_version(
                current,
                expected_boundary_version=expected_boundary_version,
                expected_boundary_checksum=expected_boundary_checksum,
                geometry_geojson=geometry,
                geometry_crs=geometry_crs.upper(),
                geometry_checksum=checksum,
                source_reference=source_reference,
                observed_at=observed_at,
                classification=classification,
                reason=reason,
                actor=actor,
            )
            assert item.boundary_version_id is not None
            evidence = self.store.create_evidence(
                Evidence(
                    id=new_id(),
                    tenant_id=tenant_id,
                    evidence_type="FIELD_BOUNDARY_CORRECTION",
                    reference_id=item.boundary_version_id,
                    classification=classification,
                    source_id=None,
                    observed_at=observed_at,
                    transformation=(
                        "field boundary correction retained as an immutable successor; "
                        "the original registration evidence remains unchanged"
                    ),
                    limitations=[
                        "the corrected field/talhão remains non-legal operational context",
                        "the correction does not infer crop, soil, management, or agronomic facts",
                    ],
                )
            )
            self.store.audit(
                tenant_id,
                actor,
                "FIELD_BOUNDARY_CORRECTED",
                "field_context_boundary_version",
                item.boundary_version_id,
                {
                    "field_id": field_id,
                    "property_id": property_id,
                    "boundary_version": item.boundary_version,
                    "previous_boundary_version": item.boundary_version - 1,
                    "classification": classification.value,
                    "evidence_id": evidence.id,
                    "reason": reason,
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
