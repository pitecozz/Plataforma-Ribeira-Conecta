from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
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

    @staticmethod
    def _scope_name(value: str) -> str:
        import unicodedata

        return " ".join(
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
            .casefold()
            .split()
        )

    def derive_verified_semil_scope(self) -> int:
        """Persist the official municipality membership and IBGE-derived shape.

        This deliberately touches only the verified administrative SEMIL
        definition.  The separate hydrological-basin scope remains UNKNOWN.
        """
        definition = self.connection.execute(
            """SELECT id,geographic_scope_id,municipality_criteria
                 FROM spatial_scope_definition
                WHERE id=%s AND definition_status='VERIFIED'""",
            ("00000000-0000-5000-8000-000000000211",),
        ).fetchone()
        if definition is None:
            raise RuntimeError("verified SEMIL scope definition is missing")
        expected = definition["municipality_criteria"]
        if not isinstance(expected, list) or not expected:
            raise RuntimeError("verified SEMIL municipality definition is missing")
        municipalities = self.connection.execute(
            """SELECT id,name FROM municipality_reference
                 WHERE uf='SP' AND source_year=2025"""
        ).fetchall()
        by_name = {self._scope_name(str(row["name"])): row["id"] for row in municipalities}
        missing = [name for name in expected if self._scope_name(str(name)) not in by_name]
        if missing:
            raise RuntimeError("official SEMIL municipality definition cannot be joined to IBGE 2025")
        scope_id = definition["geographic_scope_id"]
        ids = [by_name[self._scope_name(str(name))] for name in expected]
        for municipality_id in ids:
            self.connection.execute(
                """INSERT INTO spatial_scope_municipality(
                       geographic_scope_id,municipality_id,definition_id,classification
                     ) VALUES (%s,%s,%s,'OFFICIAL_SOURCE')
                     ON CONFLICT DO NOTHING""",
                (scope_id, municipality_id, definition["id"]),
            )
        self.connection.execute(
            """UPDATE geographic_scope AS scope
                   SET geometry=derived.geometry,
                       geometry_status='VERIFIED',
                       metadata=scope.metadata || jsonb_build_object(
                         'geometry_source','IBGE_MUNICIPAL_2025',
                         'geometry_method','union_of_verified_SEMIL_municipalities'
                       ),
                       updated_at=now()
                  FROM (
                    SELECT ST_Multi(ST_UnaryUnion(ST_Collect(ST_Transform(m.geometry,4326)))) AS geometry
                      FROM spatial_scope_municipality sm
                      JOIN municipality_reference m ON m.id=sm.municipality_id
                     WHERE sm.geographic_scope_id=%s
                  ) AS derived
                 WHERE scope.id=%s AND derived.geometry IS NOT NULL""",
            (scope_id, scope_id),
        )
        return len(ids)

    def vale_scope_envelope(self, *, buffer_degrees: float = 0.25) -> tuple[float, float, float, float]:
        if buffer_degrees < 0 or buffer_degrees > 1:
            raise ValueError("scope buffer must be between zero and one degree")
        row = self.connection.execute(
            """SELECT ST_XMin(envelope) AS xmin,ST_YMin(envelope) AS ymin,
                      ST_XMax(envelope) AS xmax,ST_YMax(envelope) AS ymax
                 FROM (
                   SELECT ST_Envelope(geometry) AS envelope FROM geographic_scope
                    WHERE scope_key='VALE_DO_RIBEIRA_SP_SEMIL'
                      AND geometry_status='VERIFIED' AND geometry IS NOT NULL
                 ) AS bounded"""
        ).fetchone()
        if row is None or any(row[key] is None for key in ("xmin", "ymin", "xmax", "ymax")):
            raise RuntimeError("verified Vale administrative geometry is unavailable")
        return (
            float(row["xmin"]) - buffer_degrees,
            float(row["ymin"]) - buffer_degrees,
            float(row["xmax"]) + buffer_degrees,
            float(row["ymax"]) + buffer_degrees,
        )

    def station_scope_relation(self, *, longitude: float, latitude: float, buffer_meters: float = 25_000) -> str:
        row = self.connection.execute(
            """SELECT CASE
                     WHEN ST_Intersects(
                       scope.geometry,ST_SetSRID(ST_MakePoint(%s,%s),4326)
                     ) THEN 'INSIDE_VERIFIED_SCOPE'
                     WHEN ST_DWithin(
                       scope.geometry::geography,
                       ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s
                     ) THEN 'NEAR_SCOPE_BUFFER'
                     ELSE 'OUTSIDE_SCOPE'
                   END AS relation
                 FROM geographic_scope scope
                WHERE scope.scope_key='VALE_DO_RIBEIRA_SP_SEMIL'
                  AND scope.geometry_status='VERIFIED'""",
            (longitude, latitude, longitude, latitude, buffer_meters),
        ).fetchone()
        return str(row["relation"]) if row else "OUTSIDE_SCOPE"

    def upsert_wis2_station(self, item: Any, *, relation: str) -> str:
        row = self.connection.execute(
            """INSERT INTO hydrological_station(
                   id,provider,provider_station_id,name,station_type,latitude,longitude,
                   active_status,metadata
                 ) VALUES (%s,'INMET_WIS2',%s,%s,'SYNOP',%s,%s,'ACTIVE',%s::jsonb)
                 ON CONFLICT (provider,provider_station_id) DO UPDATE
                   SET name=EXCLUDED.name,latitude=EXCLUDED.latitude,
                       longitude=EXCLUDED.longitude,
                       metadata=hydrological_station.metadata || EXCLUDED.metadata,
                       updated_at=now()
                 RETURNING id""",
            (
                new_id(),
                item.wigos_station_identifier,
                item.station_name[:500],
                item.latitude,
                item.longitude,
                json.dumps(
                    {
                        "geometry_source": "INMET_WIS2_FEATURE",
                        "scope_relation": relation,
                    }
                ),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("WIS2 station upsert did not return an identifier")
        return self._id(row["id"])

    def record_wis2_rain(self, item: Any, *, station_id: str, fetched_at: datetime) -> bool:
        row = self.connection.execute(
            """INSERT INTO hydrological_observation(
                   id,station_id,provider,variable,observed_at,received_at,value,unit,
                   quality_flag,classification,raw_reference,source_fetched_at,parser_version,
                   period_start,period_end,provider_record_id,delivery_channel,raw_unit,
                   normalized_value,normalized_unit,provenance
                 ) VALUES (
                   %s,%s,'INMET_WIS2','RAINFALL',%s,%s,%s,%s,'VALID','OFFICIAL_SOURCE',
                   %s,%s,'inmet_wis2_http_v1',%s,%s,%s,'HTTP_OGC_API',%s,%s,'mm',%s::jsonb
                 ) ON CONFLICT (station_id,variable,observed_at,provider) DO UPDATE
                   SET received_at=EXCLUDED.received_at,raw_reference=EXCLUDED.raw_reference,
                       source_fetched_at=EXCLUDED.source_fetched_at,
                       provider_record_id=EXCLUDED.provider_record_id,
                       period_start=EXCLUDED.period_start,period_end=EXCLUDED.period_end,
                       raw_unit=EXCLUDED.raw_unit,normalized_value=EXCLUDED.normalized_value,
                       normalized_unit=EXCLUDED.normalized_unit,provenance=EXCLUDED.provenance
                 RETURNING (xmax = 0) AS inserted""",
            (
                new_id(),
                station_id,
                item.period_end,
                item.report_time,
                item.raw_value,
                item.raw_unit,
                item.source_url,
                fetched_at,
                item.period_start,
                item.period_end,
                item.provider_record_id,
                item.raw_unit,
                item.normalized_mm,
                json.dumps(
                    {
                        "provider_record_id": item.provider_record_id,
                        "wigos_station_identifier": item.wigos_station_identifier,
                        "delivery_channel": "HTTP_OGC_API",
                        "raw_classification": "OFFICIAL_SOURCE",
                        "normalization": {
                            "classification": "CALCULATED",
                            "method": "1 kg m-2 equals 1 mm liquid-water equivalent",
                        },
                    }
                ),
            ),
        ).fetchone()
        return bool(row and row["inserted"])

    def semil_municipality_codes(self) -> list[str]:
        rows = self.connection.execute(
            """SELECT m.ibge_code
                 FROM spatial_scope_municipality sm
                 JOIN municipality_reference m ON m.id=sm.municipality_id
                 JOIN geographic_scope s ON s.id=sm.geographic_scope_id
                WHERE s.scope_key='VALE_DO_RIBEIRA_SP_SEMIL'
                ORDER BY m.ibge_code"""
        ).fetchall()
        return [str(row["ibge_code"]) for row in rows]

    def wis2_ingestion_counts(self) -> tuple[int, int]:
        stations = self.connection.execute(
            "SELECT count(*) AS count FROM hydrological_station WHERE provider='INMET_WIS2'"
        ).fetchone()
        observations = self.connection.execute(
            "SELECT count(*) AS count FROM hydrological_observation WHERE provider='INMET_WIS2' AND variable='RAINFALL'"
        ).fetchone()
        if stations is None or observations is None:
            raise RuntimeError("WIS2 count query returned no row")
        return int(stations["count"]), int(observations["count"])

    def banana_baseline_count(self) -> int:
        row = self.connection.execute(
            "SELECT count(*) AS count FROM banana_municipal_baseline WHERE crop='BANANA'"
        ).fetchone()
        if row is None:
            raise RuntimeError("banana baseline count query returned no row")
        return int(row["count"])

    def wis2_station_rainfall_aggregates(self) -> dict[str, dict[str, Any]]:
        """Coverage-aware aggregates for the freshest local station series.

        A regional total is intentionally not produced: summing rainfall from
        different stations would be a misleading spatial estimate.  Values
        are exposed only when the exact hourly interval coverage is complete.
        """
        selected = self.connection.execute(
            """SELECT station_id,max(period_end) AS latest
                 FROM hydrological_observation
                WHERE provider='INMET_WIS2' AND variable='RAINFALL'
                GROUP BY station_id
                ORDER BY max(period_end) DESC, count(*) DESC LIMIT 1"""
        ).fetchone()
        if selected is None:
            return {
                f"{hours}h": {
                    "status": "INCOMPLETE_COVERAGE", "value": None,
                    "expected_intervals": hours, "observed_intervals": 0,
                    "coverage_ratio": 0.0,
                }
                for hours in (1, 3, 6, 12, 24)
            }
        aggregates: dict[str, dict[str, Any]] = {}
        for hours in (1, 3, 6, 12, 24):
            row = self.connection.execute(
                """SELECT count(DISTINCT period_end) AS observed,
                          sum(normalized_value) AS value
                     FROM hydrological_observation
                    WHERE station_id=%s AND provider='INMET_WIS2'
                      AND variable='RAINFALL' AND period_end > %s - (%s * interval '1 hour')
                      AND period_end <= %s
                      AND period_start = period_end - interval '1 hour'""",
                (selected["station_id"], selected["latest"], hours, selected["latest"]),
            ).fetchone()
            observed = int(row["observed"]) if row else 0
            complete = observed == hours
            aggregates[f"{hours}h"] = {
                "status": "AVAILABLE" if complete else "INCOMPLETE_COVERAGE",
                "value": float(row["value"]) if complete and row and row["value"] is not None else None,
                "expected_intervals": hours,
                "observed_intervals": observed,
                "coverage_ratio": observed / hours,
                "classification": "CALCULATED" if complete else "UNKNOWN",
            }
        return aggregates

    def upsert_banana_baseline(self, *, municipality_code: str, values: dict[str, Any], metadata: Any, source_reference: str) -> bool:
        municipality = self.connection.execute(
            """SELECT id FROM municipality_reference
                WHERE ibge_code=%s AND source_year=2025""",
            (municipality_code,),
        ).fetchone()
        if municipality is None:
            raise ValueError("SIDRA municipality is outside the verified 2025 reference")
        numbers = values["numbers"]
        row = self.connection.execute(
            """INSERT INTO banana_municipal_baseline(
                   id,municipality_id,reference_year,crop,area_planted_or_destined,
                   area_harvested,production_quantity,average_yield,production_value,
                   units,source_reference,classification,classification_id,
                   classification_label,category_id,category_label,raw_values,data_status
                 ) VALUES (%s,%s,%s,'BANANA',%s,%s,%s,%s,%s,%s::jsonb,%s,
                   'OFFICIAL_SOURCE',%s,%s,%s,%s,%s::jsonb,%s)
                 ON CONFLICT (municipality_id,reference_year,crop) DO UPDATE SET
                   area_planted_or_destined=EXCLUDED.area_planted_or_destined,
                   area_harvested=EXCLUDED.area_harvested,
                   production_quantity=EXCLUDED.production_quantity,
                   average_yield=EXCLUDED.average_yield,production_value=EXCLUDED.production_value,
                   units=EXCLUDED.units,source_reference=EXCLUDED.source_reference,
                   classification_id=EXCLUDED.classification_id,
                   classification_label=EXCLUDED.classification_label,
                   category_id=EXCLUDED.category_id,category_label=EXCLUDED.category_label,
                   raw_values=EXCLUDED.raw_values,data_status=EXCLUDED.data_status
                 RETURNING (xmax = 0) AS inserted""",
            (
                new_id(), municipality["id"], int(metadata.period),
                numbers.get("area_destined"), numbers.get("area_harvested"),
                numbers.get("production"), numbers.get("yield"), numbers.get("production_value"),
                json.dumps(values["units"]),
                source_reference, metadata.classification_id, metadata.classification_label,
                metadata.category_id, metadata.category_label, json.dumps(values["raw"]),
                values["status"],
            ),
        ).fetchone()
        return bool(row and row["inserted"])

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
        scopes = self.connection.execute(
            """SELECT scope_key,name,scope_type,geometry_status,source,source_version,classification
               FROM geographic_scope
               WHERE scope_key IN ('VALE_DO_RIBEIRA_SP_SEMIL','VALE_DO_RIBEIRA_INTERSTATE_IPARDES','RIBEIRA_DE_IGUAPE_BASIN')
               ORDER BY scope_key"""
        ).fetchall()
        banana = self.connection.execute(
            """SELECT max(reference_year) AS reference_year, count(*) AS municipalities_with_data
               FROM banana_municipal_baseline WHERE crop='BANANA'"""
        ).fetchone()
        inmet = self.connection.execute(
            """SELECT count(DISTINCT station_id) AS stations,max(period_end) AS latest_observation,
                      count(*) AS observations
                 FROM hydrological_observation
                WHERE provider='INMET_WIS2' AND variable='RAINFALL'"""
        ).fetchone()
        if banana is None or inmet is None:
            raise RuntimeError("global baseline aggregate query returned no row")
        rainfall_aggregates = self.wis2_station_rainfall_aggregates()
        return {
            "source_health": [dict(row) for row in health],
            "rainfall_summary": {
                "status": "AVAILABLE" if inmet["observations"] else "INSUFFICIENT_LOCAL_DATA",
                "provider": "INMET_WIS2" if inmet["observations"] else None,
                "delivery_channel": "HTTP_OGC_API" if inmet["observations"] else None,
                "latest_observation": inmet["latest_observation"],
                "observations": int(inmet["observations"]),
            },
            "rainfall_status": "AVAILABLE" if inmet["observations"] else "INSUFFICIENT_LOCAL_DATA",
            "inmet_stations": int(inmet["stations"]),
            "rainfall_1h": rainfall_aggregates["1h"],
            "rainfall_3h": rainfall_aggregates["3h"],
            "rainfall_6h": rainfall_aggregates["6h"],
            "rainfall_12h": rainfall_aggregates["12h"],
            "rainfall_24h": rainfall_aggregates["24h"],
            "rainfall_72h": {"status": "INCOMPLETE_COVERAGE", "value": None},
            "river_summary": {
                "status": "UNKNOWN",
                "reason": "ANA_AUTH_REQUIRED_OR_SAISP_AUTOMATION_UNAVAILABLE",
            },
            "reservoir_events": [dict(row) for row in events],
            "climate_context": [dict(row) for row in climate],
            "banana_baseline_summary": {
                "status": "UNKNOWN" if not banana["reference_year"] else "AVAILABLE",
                "reference_year": banana["reference_year"],
                "municipalities_with_data": int(banana["municipalities_with_data"]),
                "limitation": "Municipal productive structure; not property or pixel crop area",
            },
            "scope_definition": [dict(row) for row in scopes],
            "active_alerts": [],
            "unknowns": [
                "No verified automated SAISP observation contract",
                "ANA hydrological inventory and telemetry require official OAuth credentials",
                "Ribeira de Iguape hydrological-basin geometry remains unknown",
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
