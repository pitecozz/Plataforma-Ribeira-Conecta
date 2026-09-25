from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Iterable

from .audit_context import current_context
from .epistemology import DataClassification
from .geospatial import (
    DerivedProduct,
    DerivedProductDependency,
    DownloadPolicy,
    GeospatialQuality,
    GeospatialStatus,
    NdviStatistics,
    ProcessingJob,
    ProcessingJobStatus,
    ProcessingJobTransition,
    SatelliteAsset,
    SatelliteCollection,
    SatelliteScene,
    SatelliteSearch,
    SatelliteSearchCandidate,
)
from .models import Evidence, new_id, now_utc


SQLITE_GEOSPATIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS geospatial_collection (
  provider_id TEXT NOT NULL, external_collection_id TEXT NOT NULL, title TEXT,
  mission TEXT, processing_level TEXT, spatial_resolution TEXT,
  temporal_characteristics TEXT NOT NULL, bands TEXT NOT NULL, license TEXT,
  stac_version TEXT, metadata TEXT NOT NULL, retrieved_at TEXT NOT NULL,
  PRIMARY KEY(provider_id, external_collection_id)
);
CREATE TABLE IF NOT EXISTS satellite_search (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL,
  provider_id TEXT NOT NULL, collection_id TEXT NOT NULL, datetime_start TEXT NOT NULL,
  datetime_end TEXT NOT NULL, aoi TEXT NOT NULL, source_crs TEXT NOT NULL,
  target_crs TEXT NOT NULL, transformation TEXT NOT NULL, policy_id TEXT NOT NULL,
  policy_version INTEGER NOT NULL, cloud_cover_limit TEXT, status TEXT NOT NULL,
  candidate_count INTEGER NOT NULL, selected_scene_id TEXT, raw_metadata_reference TEXT,
  quality TEXT NOT NULL, failure_reason TEXT, created_at TEXT NOT NULL, completed_at TEXT
);
CREATE TABLE IF NOT EXISTS satellite_scene (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL,
  provider_id TEXT NOT NULL, collection_id TEXT NOT NULL, external_item_id TEXT NOT NULL,
  acquisition_datetime TEXT NOT NULL, provider_published_datetime TEXT, geometry TEXT NOT NULL,
  bbox TEXT NOT NULL, cloud_cover TEXT, platform TEXT, constellation TEXT,
  processing_level TEXT, stac_version TEXT NOT NULL, raw_metadata_reference TEXT NOT NULL,
  checksum TEXT NOT NULL, ingested_at TEXT NOT NULL,
  UNIQUE(tenant_id, property_id, provider_id, collection_id, external_item_id)
);
CREATE TABLE IF NOT EXISTS satellite_asset (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, scene_id TEXT NOT NULL, asset_key TEXT NOT NULL,
  href TEXT NOT NULL, media_type TEXT, roles TEXT NOT NULL, title TEXT,
  band_metadata TEXT NOT NULL, download_policy TEXT NOT NULL, checksum TEXT, size_bytes INTEGER,
  checksum_provider TEXT, checksum_local TEXT, checksum_algorithm TEXT,
  download_status TEXT, download_started_at TEXT, download_finished_at TEXT,
  local_reference TEXT, bytes_downloaded INTEGER,
  created_at TEXT NOT NULL, UNIQUE(tenant_id, scene_id, asset_key)
);
CREATE TABLE IF NOT EXISTS satellite_search_candidate (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, search_id TEXT NOT NULL, scene_id TEXT NOT NULL,
  rank INTEGER NOT NULL, selected INTEGER NOT NULL, rejection_reason TEXT, criteria TEXT NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(tenant_id, search_id, scene_id)
);
CREATE TABLE IF NOT EXISTS processing_job (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL, scene_id TEXT NOT NULL,
  job_type TEXT NOT NULL, algorithm_id TEXT NOT NULL, algorithm_version TEXT NOT NULL,
  parameters TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL,
  output_product_id TEXT, failure_code TEXT, failure_reason TEXT, created_at TEXT NOT NULL, started_at TEXT,
  finished_at TEXT, attempt INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
  next_attempt_at TEXT, heartbeat_at TEXT, claimed_by TEXT, claimed_at TEXT, requested_by TEXT,
  request_id TEXT, correlation_id TEXT, field_id TEXT, field_boundary_version INTEGER,
  field_boundary_checksum TEXT, UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS processing_job_transition (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, job_id TEXT NOT NULL, from_status TEXT,
  to_status TEXT NOT NULL, attempt INTEGER NOT NULL, actor TEXT NOT NULL, worker_id TEXT,
  failure_code TEXT, failure_reason TEXT, request_id TEXT, correlation_id TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS derived_product (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL, scene_id TEXT NOT NULL,
  processing_job_id TEXT NOT NULL, product_type TEXT NOT NULL, data_classification TEXT NOT NULL,
  valid_count INTEGER NOT NULL, nodata_count INTEGER NOT NULL, minimum TEXT, maximum TEXT,
  mean TEXT, median TEXT, coverage_percentage TEXT, output_reference TEXT, output_checksum TEXT,
  algorithm_id TEXT NOT NULL, algorithm_version TEXT NOT NULL, formula TEXT NOT NULL,
  input_asset_keys TEXT NOT NULL, parameters TEXT NOT NULL, limitations TEXT NOT NULL,
  quality TEXT NOT NULL, created_at TEXT NOT NULL, field_id TEXT,
  field_boundary_version INTEGER, field_boundary_checksum TEXT,
  UNIQUE(tenant_id, processing_job_id)
);
CREATE TABLE IF NOT EXISTS derived_product_dependency (
  tenant_id TEXT NOT NULL, derived_product_id TEXT NOT NULL,
  upstream_product_id TEXT NOT NULL, relationship TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, derived_product_id, relationship),
  UNIQUE(tenant_id, derived_product_id, upstream_product_id)
);
CREATE TABLE IF NOT EXISTS property_refresh_policy (
  tenant_id TEXT NOT NULL, property_id TEXT NOT NULL, provider_id TEXT NOT NULL,
  collection_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  frequency_seconds INTEGER NOT NULL, search_window_days INTEGER NOT NULL,
  cloud_cover_limit TEXT, auto_process INTEGER NOT NULL DEFAULT 1,
  last_search_at TEXT, next_search_at TEXT, last_success_at TEXT,
  last_failure_at TEXT, latest_available_scene_id TEXT,
  latest_usable_scene_id TEXT, latest_processed_scene_id TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
  failure_code TEXT, failure_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, property_id, provider_id, collection_id)
);
CREATE TABLE IF NOT EXISTS property_refresh_run (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL,
  provider_id TEXT NOT NULL, collection_id TEXT NOT NULL, trigger_type TEXT NOT NULL,
  status TEXT NOT NULL, idempotency_key TEXT NOT NULL, scheduled_at TEXT NOT NULL,
  started_at TEXT, finished_at TEXT, next_attempt_at TEXT, attempt INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3, search_id TEXT, processing_job_id TEXT,
  failure_code TEXT, failure_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(tenant_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS property_refresh_due_idx
  ON property_refresh_run(status, next_attempt_at, scheduled_at);
"""


class GeospatialRepository:
    def __init__(self, store: Any) -> None:
        self.store = store
        self.connection = store.connection
        self.postgres = store.__class__.__name__ == "PostgresStore"
        if not self.postgres:
            self.connection.executescript(SQLITE_GEOSPATIAL_SCHEMA)

    @property
    def p(self) -> str:
        return "%s" if self.postgres else "?"

    def _execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        return self.connection.execute(sql, tuple(params))

    def _one(self, sql: str, params: Iterable[Any] = ()) -> Any:
        return self._execute(sql, params).fetchone()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @staticmethod
    def _decode(value: Any, default: Any) -> Any:
        if value is None:
            return default
        return value if isinstance(value, (dict, list)) else json.loads(value)

    @staticmethod
    def _timestamp(value: Any) -> str | None:
        return (
            None
            if value is None
            else value.isoformat()
            if hasattr(value, "isoformat")
            else str(value)
        )

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        return None if value is None else Decimal(str(value))

    def _insert(self, table: str, columns: list[str], values: list[Any]) -> None:
        marks = ",".join([self.p] * len(columns))
        bind = [str(item) if isinstance(item, Decimal) else item for item in values]
        self._execute(
            f"INSERT INTO {table}({','.join(columns)}) VALUES ({marks})",  # nosec B608 - internal table and column names only
            bind,
        )

    def upsert_collection(self, item: SatelliteCollection) -> SatelliteCollection:
        values = [
            item.provider_id,
            item.external_collection_id,
            item.title,
            item.mission,
            item.processing_level,
            item.spatial_resolution,
            self._json(item.temporal_characteristics),
            self._json(item.bands),
            item.license,
            item.stac_version,
            self._json(item.metadata),
            item.retrieved_at,
        ]
        sql = f"""INSERT INTO geospatial_collection
          (provider_id,external_collection_id,title,mission,processing_level,spatial_resolution,
           temporal_characteristics,bands,license,stac_version,metadata,retrieved_at)
          VALUES ({",".join([self.p] * len(values))})
          ON CONFLICT (provider_id,external_collection_id) DO UPDATE SET
           title=excluded.title, mission=excluded.mission, processing_level=excluded.processing_level,
           spatial_resolution=excluded.spatial_resolution, temporal_characteristics=excluded.temporal_characteristics,
           bands=excluded.bands, license=excluded.license, stac_version=excluded.stac_version,
           metadata=excluded.metadata, retrieved_at=excluded.retrieved_at"""  # nosec B608
        self._execute(sql, values)
        return item

    def create_search(self, item: SatelliteSearch) -> SatelliteSearch:
        values = [
            item.id,
            item.tenant_id,
            item.property_id,
            item.provider_id,
            item.collection_id,
            item.datetime_start,
            item.datetime_end,
            self._json(item.aoi_geojson),
            item.source_crs,
            item.target_crs,
            item.transformation,
            item.policy_id,
            item.policy_version,
            item.cloud_cover_limit,
            item.status.value,
            item.candidate_count,
            item.selected_scene_id,
            item.raw_metadata_reference,
            self._json([value.value for value in item.quality]),
            item.failure_reason,
            item.created_at,
            item.completed_at,
        ]
        if self.postgres:
            sql = f"""INSERT INTO satellite_search
              (id,tenant_id,property_id,provider_id,collection_id,datetime_start,datetime_end,aoi,
               source_crs,target_crs,transformation,policy_id,policy_version,cloud_cover_limit,status,
               candidate_count,selected_scene_id,raw_metadata_reference,quality,failure_reason,created_at,completed_at)
              VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},
                ST_SetSRID(ST_GeomFromGeoJSON({self.p}::text),4326),
                {",".join([self.p] * 14)})"""  # nosec B608
            self._execute(sql, [*values[:7], values[7], *values[8:]])
        else:
            self._insert(
                "satellite_search",
                [
                    "id",
                    "tenant_id",
                    "property_id",
                    "provider_id",
                    "collection_id",
                    "datetime_start",
                    "datetime_end",
                    "aoi",
                    "source_crs",
                    "target_crs",
                    "transformation",
                    "policy_id",
                    "policy_version",
                    "cloud_cover_limit",
                    "status",
                    "candidate_count",
                    "selected_scene_id",
                    "raw_metadata_reference",
                    "quality",
                    "failure_reason",
                    "created_at",
                    "completed_at",
                ],
                values,
            )
        return item

    def upsert_scene(self, item: SatelliteScene) -> SatelliteScene:
        values = [
            item.id,
            item.tenant_id,
            item.property_id,
            item.provider_id,
            item.collection_id,
            item.external_item_id,
            item.acquisition_datetime,
            item.provider_published_datetime,
            self._json(item.geometry_geojson),
            self._json(item.bbox),
            item.cloud_cover,
            item.platform,
            item.constellation,
            item.processing_level,
            item.stac_version,
            item.raw_metadata_reference,
            item.checksum,
            item.ingested_at,
        ]
        if self.postgres:
            sql = f"""INSERT INTO satellite_scene
              (id,tenant_id,property_id,provider_id,collection_id,external_item_id,acquisition_datetime,
               provider_published_datetime,geometry,bbox,cloud_cover,platform,constellation,processing_level,
               stac_version,raw_metadata_reference,checksum,ingested_at)
              VALUES ({self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},
               ST_SetSRID(ST_GeomFromGeoJSON({self.p}::text),4326),{self.p},{self.p},{self.p},{self.p},{self.p},{self.p},
               {self.p},{self.p},{self.p})
              ON CONFLICT (tenant_id,property_id,provider_id,collection_id,external_item_id)
              DO UPDATE SET raw_metadata_reference=excluded.raw_metadata_reference,
                checksum=excluded.checksum, cloud_cover=excluded.cloud_cover,
                ingested_at=excluded.ingested_at
              RETURNING id"""  # nosec B608 - SQL structure is fixed and all values are placeholders
            params = [*values[:8], values[8], *values[9:]]
            row = self._one(sql, params)
            return SatelliteScene(**{**item.__dict__, "id": str(row["id"])})
        self._execute(
            f"""INSERT INTO satellite_scene
              (id,tenant_id,property_id,provider_id,collection_id,external_item_id,acquisition_datetime,
               provider_published_datetime,geometry,bbox,cloud_cover,platform,constellation,processing_level,
               stac_version,raw_metadata_reference,checksum,ingested_at)
              VALUES ({",".join([self.p] * len(values))})
              ON CONFLICT (tenant_id,property_id,provider_id,collection_id,external_item_id)
              DO UPDATE SET raw_metadata_reference=excluded.raw_metadata_reference,
                checksum=excluded.checksum, cloud_cover=excluded.cloud_cover,
                ingested_at=excluded.ingested_at""",  # nosec B608
            [str(value) if isinstance(value, Decimal) else value for value in values],
        )
        row = self._one(
            "SELECT id FROM satellite_scene WHERE tenant_id=? AND property_id=? AND provider_id=? AND collection_id=? AND external_item_id=?",
            values[1:6],
        )
        return SatelliteScene(**{**item.__dict__, "id": str(row["id"])})

    def upsert_asset(self, item: SatelliteAsset) -> SatelliteAsset:
        values = [
            item.id,
            item.tenant_id,
            item.scene_id,
            item.asset_key,
            item.href,
            item.media_type,
            self._json(item.roles),
            item.title,
            self._json(item.band_metadata),
            item.download_policy.value,
            item.checksum,
            item.size_bytes,
            item.checksum_provider,
            item.checksum_local,
            item.checksum_algorithm,
            item.download_status,
            item.download_started_at,
            item.download_finished_at,
            item.local_reference,
            item.bytes_downloaded,
            now_utc(),
        ]
        sql = f"""INSERT INTO satellite_asset
          (id,tenant_id,scene_id,asset_key,href,media_type,roles,title,band_metadata,download_policy,checksum,size_bytes,
           checksum_provider,checksum_local,checksum_algorithm,download_status,download_started_at,download_finished_at,
           local_reference,bytes_downloaded,created_at)
          VALUES ({",".join([self.p] * len(values))})
          ON CONFLICT (tenant_id,scene_id,asset_key) DO UPDATE SET href=excluded.href,
            media_type=excluded.media_type, roles=excluded.roles, title=excluded.title,
            band_metadata=excluded.band_metadata, download_policy=excluded.download_policy,
            checksum=COALESCE(excluded.checksum, satellite_asset.checksum),
            size_bytes=COALESCE(excluded.size_bytes, satellite_asset.size_bytes)"""  # nosec B608
        self._execute(
            sql,
            [str(value) if isinstance(value, Decimal) else value for value in values],
        )
        row = self._one(
            f"SELECT id FROM satellite_asset WHERE tenant_id={self.p} AND scene_id={self.p} AND asset_key={self.p}",  # nosec B608
            values[1:4],
        )
        return SatelliteAsset(**{**item.__dict__, "id": str(row["id"])})

    def create_candidate(
        self, item: SatelliteSearchCandidate
    ) -> SatelliteSearchCandidate:
        values = [
            item.id,
            item.tenant_id,
            item.search_id,
            item.scene_id,
            item.rank,
            item.selected,
            item.rejection_reason,
            self._json(item.criteria),
            now_utc(),
        ]
        sql = f"""INSERT INTO satellite_search_candidate
          (id,tenant_id,search_id,scene_id,rank,selected,rejection_reason,criteria,created_at)
          VALUES ({",".join([self.p] * len(values))})
          ON CONFLICT (tenant_id,search_id,scene_id) DO UPDATE SET rank=excluded.rank,
            selected=excluded.selected, rejection_reason=excluded.rejection_reason,
            criteria=excluded.criteria"""  # nosec B608
        self._execute(sql, values)
        return item

    def update_search(
        self,
        tenant_id: str,
        search_id: str,
        status: GeospatialStatus,
        candidate_count: int,
        selected_scene_id: str | None,
        raw_reference: str | None,
        quality: list[GeospatialQuality],
        failure_reason: str | None = None,
    ) -> None:
        p = self.p
        self._execute(
            f"""UPDATE satellite_search SET status={p}, candidate_count={p}, selected_scene_id={p},
              raw_metadata_reference={p}, quality={p}, failure_reason={p}, completed_at={p}
              WHERE tenant_id={p} AND id={p}""",  # nosec B608
            [
                status.value,
                candidate_count,
                selected_scene_id,
                raw_reference,
                self._json([item.value for item in quality]),
                failure_reason,
                now_utc(),
                tenant_id,
                search_id,
            ],
        )

    def get_search(self, tenant_id: str, search_id: str) -> SatelliteSearch | None:
        p = self.p
        geometry = "ST_AsGeoJSON(aoi) AS aoi" if self.postgres else "aoi"
        row = self._one(
            f"SELECT id,tenant_id,property_id,provider_id,collection_id,datetime_start,datetime_end,{geometry},source_crs,target_crs,transformation,policy_id,policy_version,cloud_cover_limit,status,candidate_count,selected_scene_id,raw_metadata_reference,quality,failure_reason,created_at,completed_at FROM satellite_search WHERE tenant_id={p} AND id={p}",  # nosec B608
            [tenant_id, search_id],
        )
        if row is None:
            return None
        return SatelliteSearch(
            str(row["id"]),
            str(row["tenant_id"]),
            str(row["property_id"]),
            row["provider_id"],
            row["collection_id"],
            self._timestamp(row["datetime_start"]) or "",
            self._timestamp(row["datetime_end"]) or "",
            self._decode(row["aoi"], {}),
            row["source_crs"],
            row["target_crs"],
            row["transformation"],
            row["policy_id"],
            int(row["policy_version"]),
            self._decimal(row["cloud_cover_limit"]),
            GeospatialStatus(row["status"]),
            int(row["candidate_count"]),
            str(row["selected_scene_id"]) if row["selected_scene_id"] else None,
            row["raw_metadata_reference"],
            [GeospatialQuality(item) for item in self._decode(row["quality"], [])],
            row["failure_reason"],
            self._timestamp(row["created_at"]) or "",
            self._timestamp(row["completed_at"]),
        )

    def get_scene(self, tenant_id: str, scene_id: str) -> SatelliteScene | None:
        p = self.p
        geometry = "ST_AsGeoJSON(geometry) AS geometry" if self.postgres else "geometry"
        row = self._one(
            f"SELECT id,tenant_id,property_id,provider_id,collection_id,external_item_id,acquisition_datetime,provider_published_datetime,{geometry},bbox,cloud_cover,platform,constellation,processing_level,stac_version,raw_metadata_reference,checksum,ingested_at FROM satellite_scene WHERE tenant_id={p} AND id={p}",  # nosec B608
            [tenant_id, scene_id],
        )
        if row is None:
            return None
        return SatelliteScene(
            str(row["id"]),
            str(row["tenant_id"]),
            str(row["property_id"]),
            row["provider_id"],
            row["collection_id"],
            row["external_item_id"],
            self._timestamp(row["acquisition_datetime"]) or "",
            self._timestamp(row["provider_published_datetime"]),
            self._decode(row["geometry"], {}),
            [float(item) for item in self._decode(row["bbox"], [])],
            self._decimal(row["cloud_cover"]),
            row["platform"],
            row["constellation"],
            row["processing_level"],
            row["stac_version"],
            row["raw_metadata_reference"],
            row["checksum"],
            self._timestamp(row["ingested_at"]) or "",
        )

    def list_scenes(self, tenant_id: str, property_id: str) -> list[SatelliteScene]:
        p = self.p
        rows = self._execute(
            f"SELECT id FROM satellite_scene WHERE tenant_id={p} AND property_id={p} ORDER BY acquisition_datetime DESC",  # nosec B608
            [tenant_id, property_id],
        ).fetchall()
        scenes: list[SatelliteScene] = []
        for row in rows:
            scene = self.get_scene(tenant_id, str(row["id"]))
            if scene is not None:
                scenes.append(scene)
        return scenes

    def list_assets(self, tenant_id: str, scene_id: str) -> list[SatelliteAsset]:
        p = self.p
        rows = self._execute(
            f"SELECT * FROM satellite_asset WHERE tenant_id={p} AND scene_id={p} ORDER BY asset_key",  # nosec B608
            [tenant_id, scene_id],
        ).fetchall()
        return [
            SatelliteAsset(
                str(row["id"]),
                str(row["tenant_id"]),
                str(row["scene_id"]),
                row["asset_key"],
                row["href"],
                row["media_type"],
                self._decode(row["roles"], []),
                row["title"],
                self._decode(row["band_metadata"], {}),
                DownloadPolicy(row["download_policy"]),
                row["checksum"],
                row["size_bytes"],
                row["checksum_provider"],
                row["checksum_local"],
                row["checksum_algorithm"],
                row["download_status"],
                self._timestamp(row["download_started_at"]),
                self._timestamp(row["download_finished_at"]),
                row["local_reference"],
                row["bytes_downloaded"],
            )
            for row in rows
        ]

    def update_asset_access(
        self,
        tenant_id: str,
        asset_id: str,
        *,
        status: str,
        checksum_provider: str | None = None,
        checksum_local: str | None = None,
        checksum_algorithm: str | None = None,
        size_bytes: int | None = None,
        bytes_downloaded: int | None = None,
        local_reference: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> SatelliteAsset:
        p = self.p
        self._execute(
            f"""UPDATE satellite_asset SET download_status={p}, checksum_provider={p},
              checksum_local={p}, checksum_algorithm={p}, size_bytes=COALESCE({p}, size_bytes),
              bytes_downloaded={p}, local_reference={p}, download_started_at={p},
              download_finished_at={p}
              WHERE tenant_id={p} AND id={p}""",  # nosec B608
            [
                status,
                checksum_provider,
                checksum_local,
                checksum_algorithm,
                size_bytes,
                bytes_downloaded,
                local_reference,
                started_at,
                finished_at,
                tenant_id,
                asset_id,
            ],
        )
        row = self._one(
            f"SELECT * FROM satellite_asset WHERE tenant_id={p} AND id={p}",  # nosec B608
            [tenant_id, asset_id],
        )
        if row is None:
            raise LookupError("satellite asset not found")
        return SatelliteAsset(
            str(row["id"]),
            str(row["tenant_id"]),
            str(row["scene_id"]),
            row["asset_key"],
            row["href"],
            row["media_type"],
            self._decode(row["roles"], []),
            row["title"],
            self._decode(row["band_metadata"], {}),
            DownloadPolicy(row["download_policy"]),
            row["checksum"],
            row["size_bytes"],
            row["checksum_provider"],
            row["checksum_local"],
            row["checksum_algorithm"],
            row["download_status"],
            self._timestamp(row["download_started_at"]),
            self._timestamp(row["download_finished_at"]),
            row["local_reference"],
            row["bytes_downloaded"],
        )

    def create_evidence(self, evidence: Evidence) -> Evidence:
        return self.store.create_evidence(evidence)

    @staticmethod
    def _validate_field_snapshot(item: ProcessingJob | DerivedProduct) -> None:
        values = (
            item.field_id,
            item.field_boundary_version,
            item.field_boundary_checksum,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("field snapshot must include id, version, and checksum")
        if item.field_boundary_version is not None and item.field_boundary_version < 1:
            raise ValueError("field boundary version must be positive")
        if (
            item.field_boundary_checksum is not None
            and len(item.field_boundary_checksum) != 64
        ):
            raise ValueError("field boundary checksum must be SHA-256")

    def create_job(self, item: ProcessingJob, actor: str = "system") -> ProcessingJob:
        self._validate_field_snapshot(item)
        p = self.p
        existing = self._one(
            f"SELECT * FROM processing_job WHERE tenant_id={p} AND idempotency_key={p}",  # nosec B608
            [item.tenant_id, item.idempotency_key],
        )
        if existing is not None:
            return self._job(existing)
        self._insert(
            "processing_job",
            [
                "id",
                "tenant_id",
                "property_id",
                "scene_id",
                "job_type",
                "algorithm_id",
                "algorithm_version",
                "parameters",
                "status",
                "idempotency_key",
                "output_product_id",
                "failure_code",
                "failure_reason",
                "created_at",
                "started_at",
                "finished_at",
                "attempt",
                "max_attempts",
                "next_attempt_at",
                "heartbeat_at",
                "claimed_by",
                "claimed_at",
                "requested_by",
                "request_id",
                "correlation_id",
                "field_id",
                "field_boundary_version",
                "field_boundary_checksum",
            ],
            [
                item.id,
                item.tenant_id,
                item.property_id,
                item.scene_id,
                item.job_type,
                item.algorithm_id,
                item.algorithm_version,
                self._json(item.parameters),
                item.status.value,
                item.idempotency_key,
                item.output_product_id,
                item.failure_code,
                item.failure_reason,
                item.created_at,
                item.started_at,
                item.finished_at,
                item.attempt,
                item.max_attempts,
                item.next_attempt_at,
                item.heartbeat_at,
                item.claimed_by,
                item.claimed_at,
                item.requested_by,
                item.request_id,
                item.correlation_id,
                item.field_id,
                item.field_boundary_version,
                item.field_boundary_checksum,
            ],
        )
        self._record_transition(item, None, item.status, actor, None)
        return item

    def _job(self, row: Any) -> ProcessingJob:
        return ProcessingJob(
            str(row["id"]),
            str(row["tenant_id"]),
            str(row["property_id"]),
            str(row["scene_id"]),
            row["job_type"],
            row["algorithm_id"],
            row["algorithm_version"],
            self._decode(row["parameters"], {}),
            ProcessingJobStatus(row["status"]),
            row["idempotency_key"],
            str(row["output_product_id"]) if row["output_product_id"] else None,
            row["failure_reason"],
            self._timestamp(row["created_at"]) or "",
            self._timestamp(row["started_at"]),
            self._timestamp(row["finished_at"]),
            row["failure_code"] if "failure_code" in row.keys() else None,
            int(row["attempt"]) if "attempt" in row.keys() else 0,
            int(row["max_attempts"]) if "max_attempts" in row.keys() else 3,
            self._timestamp(row["next_attempt_at"])
            if "next_attempt_at" in row.keys()
            else None,
            self._timestamp(row["heartbeat_at"])
            if "heartbeat_at" in row.keys()
            else None,
            row["claimed_by"] if "claimed_by" in row.keys() else None,
            self._timestamp(row["claimed_at"]) if "claimed_at" in row.keys() else None,
            row["requested_by"] if "requested_by" in row.keys() else None,
            row["request_id"] if "request_id" in row.keys() else None,
            row["correlation_id"] if "correlation_id" in row.keys() else None,
            str(row["field_id"])
            if "field_id" in row.keys() and row["field_id"]
            else None,
            int(row["field_boundary_version"])
            if "field_boundary_version" in row.keys()
            and row["field_boundary_version"] is not None
            else None,
            row["field_boundary_checksum"]
            if "field_boundary_checksum" in row.keys()
            else None,
        )

    def get_job(self, tenant_id: str, job_id: str) -> ProcessingJob | None:
        p = self.p
        row = self._one(
            f"SELECT * FROM processing_job WHERE tenant_id={p} AND id={p}",  # nosec B608
            [tenant_id, job_id],
        )
        return self._job(row) if row else None

    def _record_transition(
        self,
        job: ProcessingJob,
        from_status: ProcessingJobStatus | None,
        to_status: ProcessingJobStatus,
        actor: str,
        worker_id: str | None,
    ) -> None:
        request_id, correlation_id = current_context()
        item = ProcessingJobTransition(
            new_id(),
            job.tenant_id,
            job.id,
            from_status,
            to_status,
            job.attempt,
            actor,
            worker_id,
            job.failure_code,
            job.failure_reason,
            request_id or job.request_id,
            correlation_id or job.correlation_id,
        )
        self._insert(
            "processing_job_transition",
            [
                "id",
                "tenant_id",
                "job_id",
                "from_status",
                "to_status",
                "attempt",
                "actor",
                "worker_id",
                "failure_code",
                "failure_reason",
                "request_id",
                "correlation_id",
                "created_at",
            ],
            [
                item.id,
                item.tenant_id,
                item.job_id,
                item.from_status.value if item.from_status else None,
                item.to_status.value,
                item.attempt,
                item.actor,
                item.worker_id,
                item.failure_code,
                item.failure_reason,
                item.request_id,
                item.correlation_id,
                item.created_at,
            ],
        )

    def list_job_transitions(
        self, tenant_id: str, job_id: str
    ) -> list[ProcessingJobTransition]:
        p = self.p
        rows = self._execute(
            f"SELECT * FROM processing_job_transition WHERE tenant_id={p} AND job_id={p} ORDER BY created_at, id",  # nosec B608
            [tenant_id, job_id],
        ).fetchall()
        return [
            ProcessingJobTransition(
                str(row["id"]),
                str(row["tenant_id"]),
                str(row["job_id"]),
                ProcessingJobStatus(row["from_status"]) if row["from_status"] else None,
                ProcessingJobStatus(row["to_status"]),
                int(row["attempt"]),
                row["actor"],
                row["worker_id"],
                row["failure_code"],
                row["failure_reason"],
                row["request_id"],
                row["correlation_id"],
                self._timestamp(row["created_at"]) or "",
            )
            for row in rows
        ]

    def claim_next_job(self, worker_id: str) -> ProcessingJob | None:
        """Atomically move one eligible job to RUNNING; callers hold no long DB transaction."""
        p = self.p
        now = now_utc()
        if self.postgres:
            row = self._one(
                f"""WITH candidate AS (
                    SELECT id FROM processing_job
                    WHERE status={p} AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                    ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1
                )
                UPDATE processing_job AS job
                SET status={p}, attempt=attempt+1, started_at=COALESCE(started_at,{p}),
                    heartbeat_at={p}, claimed_by={p}, claimed_at={p},
                    failure_code=NULL, failure_reason=NULL, next_attempt_at=NULL
                FROM candidate WHERE job.id=candidate.id
                RETURNING job.*""",  # nosec B608
                [
                    ProcessingJobStatus.QUEUED.value,
                    ProcessingJobStatus.RUNNING.value,
                    now,
                    now,
                    worker_id,
                    now,
                ],
            )
        else:
            candidate = self._one(
                f"SELECT * FROM processing_job WHERE status={p} AND (next_attempt_at IS NULL OR next_attempt_at <= {p}) ORDER BY created_at, id LIMIT 1",  # nosec B608
                [ProcessingJobStatus.QUEUED.value, now],
            )
            if candidate is None:
                return None
            result = self._execute(
                f"""UPDATE processing_job SET status={p},attempt=attempt+1,
                    started_at=COALESCE(started_at,{p}),heartbeat_at={p},claimed_by={p},claimed_at={p},
                    failure_code=NULL,failure_reason=NULL,next_attempt_at=NULL
                    WHERE id={p} AND status={p}""",  # nosec B608
                [
                    ProcessingJobStatus.RUNNING.value,
                    now,
                    now,
                    worker_id,
                    now,
                    candidate["id"],
                    ProcessingJobStatus.QUEUED.value,
                ],
            )
            if result.rowcount != 1:
                return None
            row = self._one(
                f"SELECT * FROM processing_job WHERE id={p}", [candidate["id"]]
            )
        if row is None:
            return None
        claimed = self._job(row)
        self._record_transition(
            claimed,
            ProcessingJobStatus.QUEUED,
            ProcessingJobStatus.RUNNING,
            actor=f"worker:{worker_id}",
            worker_id=worker_id,
        )
        return claimed

    def heartbeat(self, tenant_id: str, job_id: str, worker_id: str) -> bool:
        p = self.p
        result = self._execute(
            f"UPDATE processing_job SET heartbeat_at={p} WHERE tenant_id={p} AND id={p} AND status={p} AND claimed_by={p}",  # nosec B608
            [
                now_utc(),
                tenant_id,
                job_id,
                ProcessingJobStatus.RUNNING.value,
                worker_id,
            ],
        )
        return result.rowcount == 1

    def recover_stale_jobs(self, stale_before: str, actor: str) -> int:
        """Return abandoned RUNNING jobs to QUEUED or terminally fail exhausted jobs."""
        p = self.p
        rows = self._execute(
            f"SELECT * FROM processing_job WHERE status={p} AND (heartbeat_at IS NULL OR heartbeat_at < {p})",  # nosec B608
            [ProcessingJobStatus.RUNNING.value, stale_before],
        ).fetchall()
        recovered = 0
        for row in rows:
            old = self._job(row)
            target = (
                ProcessingJobStatus.FAILED
                if old.attempt >= old.max_attempts
                else ProcessingJobStatus.QUEUED
            )
            code = "WORKER_HEARTBEAT_EXPIRED"
            reason = (
                "worker heartbeat expired; job was recovered without producing a result"
            )
            schedule_update = (
                f"next_attempt_at={p},finished_at=NULL"
                if target == ProcessingJobStatus.QUEUED
                else f"next_attempt_at=NULL,finished_at={p}"
            )
            result = self._execute(
                f"""UPDATE processing_job SET status={p},failure_code={p},failure_reason={p},
                    {schedule_update},
                    claimed_by=NULL,claimed_at=NULL,heartbeat_at=NULL
                    WHERE id={p} AND status={p} AND (heartbeat_at IS NULL OR heartbeat_at < {p})""",  # nosec B608
                [
                    target.value,
                    code,
                    reason,
                    now_utc(),
                    old.id,
                    ProcessingJobStatus.RUNNING.value,
                    stale_before,
                ],
            )
            if result.rowcount == 1:
                current = self.get_job(old.tenant_id, old.id)
                if current is not None:
                    self._record_transition(
                        current, old.status, target, actor, old.claimed_by
                    )
                    recovered += 1
        return recovered

    def retry_job(self, tenant_id: str, job_id: str, actor: str) -> ProcessingJob:
        """Explicit, auditable retry; never creates a second idempotency key."""
        previous = self.get_job(tenant_id, job_id)
        if previous is None:
            raise LookupError("processing job not found")
        if previous.status not in {
            ProcessingJobStatus.FAILED,
            ProcessingJobStatus.BLOCKED,
        }:
            raise ValueError("only terminal unsuccessful jobs may be retried")
        if previous.attempt >= previous.max_attempts:
            raise ValueError("processing job retry budget is exhausted")
        p = self.p
        result = self._execute(
            f"UPDATE processing_job SET status={p},failure_code=NULL,failure_reason=NULL,next_attempt_at={p},finished_at=NULL,claimed_by=NULL,claimed_at=NULL,heartbeat_at=NULL WHERE tenant_id={p} AND id={p} AND status={p}",  # nosec B608
            [
                ProcessingJobStatus.QUEUED.value,
                now_utc(),
                tenant_id,
                job_id,
                previous.status.value,
            ],
        )
        if result.rowcount != 1:
            raise RuntimeError("processing job retry transition was not acquired")
        current = self.get_job(tenant_id, job_id)
        if current is None:
            raise LookupError("processing job not found")
        self._record_transition(current, previous.status, current.status, actor, None)
        return current

    def job_counts(self) -> dict[str, int]:
        rows = self._execute(
            "SELECT status, count(*) AS count FROM processing_job GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def mark_job(
        self,
        tenant_id: str,
        job_id: str,
        status: ProcessingJobStatus,
        failure_reason: str | None = None,
        output_product_id: str | None = None,
        failure_code: str | None = None,
        actor: str = "system",
        worker_id: str | None = None,
    ) -> ProcessingJob:
        p = self.p
        now = now_utc()
        previous = self.get_job(tenant_id, job_id)
        if previous is None:
            raise LookupError("processing job not found")
        terminal = {
            ProcessingJobStatus.SUCCEEDED,
            ProcessingJobStatus.FAILED,
            ProcessingJobStatus.BLOCKED,
            ProcessingJobStatus.CANCELLED,
        }
        if status == ProcessingJobStatus.RUNNING and previous.status == status:
            self._execute(
                f"UPDATE processing_job SET heartbeat_at={p} WHERE tenant_id={p} AND id={p}",  # nosec B608
                [now, tenant_id, job_id],
            )
        elif status == ProcessingJobStatus.RUNNING:
            result = self._execute(
                f"UPDATE processing_job SET status={p},started_at=COALESCE(started_at,{p}),heartbeat_at={p},claimed_by=COALESCE(claimed_by,{p}),claimed_at=COALESCE(claimed_at,{p}) WHERE tenant_id={p} AND id={p} AND status={p}",  # nosec B608
                [
                    status.value,
                    now,
                    now,
                    worker_id,
                    now,
                    tenant_id,
                    job_id,
                    ProcessingJobStatus.QUEUED.value,
                ],
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    "processing job transition to RUNNING was not acquired"
                )
        else:
            if status not in terminal or (
                worker_id is not None and previous.status != ProcessingJobStatus.RUNNING
            ):
                raise ValueError("invalid processing job state transition")
            lease_clause = f" AND status={p} AND claimed_by={p}" if worker_id else ""
            values: list[Any] = [
                status.value,
                failure_code,
                failure_reason,
                output_product_id,
                now,
                tenant_id,
                job_id,
            ]
            if worker_id:
                values.extend([ProcessingJobStatus.RUNNING.value, worker_id])
            result = self._execute(
                f"UPDATE processing_job SET status={p},failure_code={p},failure_reason={p},output_product_id={p},finished_at={p},heartbeat_at={p} WHERE tenant_id={p} AND id={p}{lease_clause}",  # nosec B608
                [
                    *values[:4],
                    now,
                    now,
                    *values[5:],
                ],
            )
            if result.rowcount != 1:
                raise RuntimeError("processing job completion lease was lost")
        result = self.get_job(tenant_id, job_id)
        if result is None:
            raise LookupError("processing job not found")
        if previous.status != result.status:
            self._record_transition(
                result, previous.status, result.status, actor, worker_id
            )
        return result

    def create_derived_product(self, item: DerivedProduct) -> DerivedProduct:
        self._validate_field_snapshot(item)
        stats = item.statistics
        self._insert(
            "derived_product",
            [
                "id",
                "tenant_id",
                "property_id",
                "scene_id",
                "processing_job_id",
                "product_type",
                "data_classification",
                "valid_count",
                "nodata_count",
                "minimum",
                "maximum",
                "mean",
                "median",
                "coverage_percentage",
                "output_reference",
                "output_checksum",
                "algorithm_id",
                "algorithm_version",
                "formula",
                "input_asset_keys",
                "parameters",
                "limitations",
                "quality",
                "created_at",
                "field_id",
                "field_boundary_version",
                "field_boundary_checksum",
            ],
            [
                item.id,
                item.tenant_id,
                item.property_id,
                item.scene_id,
                item.processing_job_id,
                item.product_type,
                item.classification.value,
                stats.valid_count,
                stats.nodata_count,
                stats.minimum,
                stats.maximum,
                stats.mean,
                stats.median,
                stats.coverage_percentage,
                item.output_reference,
                item.output_checksum,
                item.algorithm_id,
                item.algorithm_version,
                item.formula,
                self._json(item.input_asset_keys),
                self._json(item.parameters),
                self._json(item.limitations),
                self._json([value.value for value in item.quality]),
                item.created_at,
                item.field_id,
                item.field_boundary_version,
                item.field_boundary_checksum,
            ],
        )
        return item

    def create_product_dependency(
        self, item: DerivedProductDependency
    ) -> DerivedProductDependency:
        self._insert(
            "derived_product_dependency",
            [
                "tenant_id",
                "derived_product_id",
                "upstream_product_id",
                "relationship",
                "created_at",
            ],
            [
                item.tenant_id,
                item.derived_product_id,
                item.upstream_product_id,
                item.relationship,
                item.created_at,
            ],
        )
        return item

    def list_product_dependencies(
        self, tenant_id: str, derived_product_id: str
    ) -> list[DerivedProductDependency]:
        p = self.p
        rows = self._execute(
            f"SELECT * FROM derived_product_dependency WHERE tenant_id={p} AND derived_product_id={p} ORDER BY relationship",  # nosec B608
            [tenant_id, derived_product_id],
        ).fetchall()
        return [
            DerivedProductDependency(
                str(row["tenant_id"]),
                str(row["derived_product_id"]),
                str(row["upstream_product_id"]),
                row["relationship"],
                self._timestamp(row["created_at"]) or "",
            )
            for row in rows
        ]

    def find_temporal_delta(
        self, tenant_id: str, baseline_product_id: str, target_product_id: str
    ) -> DerivedProduct | None:
        p = self.p
        row = self._one(
            f"""SELECT d.* FROM derived_product d
              JOIN derived_product_dependency baseline ON baseline.tenant_id=d.tenant_id
                AND baseline.derived_product_id=d.id AND baseline.relationship='BASELINE_NDVI'
              JOIN derived_product_dependency target ON target.tenant_id=d.tenant_id
                AND target.derived_product_id=d.id AND target.relationship='TARGET_NDVI'
              WHERE d.tenant_id={p} AND d.product_type='NDVI_DELTA'
                AND baseline.upstream_product_id={p} AND target.upstream_product_id={p}
              ORDER BY d.created_at DESC, d.id DESC LIMIT 1""",  # nosec B608
            [tenant_id, baseline_product_id, target_product_id],
        )
        return self._derived_product(row) if row is not None else None

    def get_derived_product(
        self, tenant_id: str, product_id: str
    ) -> DerivedProduct | None:
        p = self.p
        row = self._one(
            f"SELECT * FROM derived_product WHERE tenant_id={p} AND id={p}",  # nosec B608
            [tenant_id, product_id],
        )
        if row is None:
            return None
        return self._derived_product(row)

    def _derived_product(self, row: Any) -> DerivedProduct:
        stats = NdviStatistics(
            int(row["valid_count"]),
            int(row["nodata_count"]),
            self._decimal(row["minimum"]),
            self._decimal(row["maximum"]),
            self._decimal(row["mean"]),
            self._decimal(row["median"]),
            self._decimal(row["coverage_percentage"]),
        )
        return DerivedProduct(
            str(row["id"]),
            str(row["tenant_id"]),
            str(row["property_id"]),
            str(row["scene_id"]),
            str(row["processing_job_id"]),
            row["product_type"],
            DataClassification(row["data_classification"]),
            stats,
            row["output_reference"],
            row["output_checksum"],
            row["algorithm_id"],
            row["algorithm_version"],
            row["formula"],
            self._decode(row["input_asset_keys"], []),
            self._decode(row["parameters"], {}),
            self._decode(row["limitations"], []),
            [GeospatialQuality(item) for item in self._decode(row["quality"], [])],
            self._timestamp(row["created_at"]) or "",
            str(row["field_id"])
            if "field_id" in row.keys() and row["field_id"]
            else None,
            int(row["field_boundary_version"])
            if "field_boundary_version" in row.keys()
            and row["field_boundary_version"] is not None
            else None,
            row["field_boundary_checksum"]
            if "field_boundary_checksum" in row.keys()
            else None,
        )

    def list_derived_products(
        self, tenant_id: str, property_id: str
    ) -> list[DerivedProduct]:
        p = self.p
        rows = self._execute(
            f"SELECT id FROM derived_product WHERE tenant_id={p} AND property_id={p} ORDER BY created_at DESC, id",  # nosec B608
            [tenant_id, property_id],
        ).fetchall()
        return [
            item
            for row in rows
            if (item := self.get_derived_product(tenant_id, str(row["id"]))) is not None
        ]

    def list_timeline(self, tenant_id: str, property_id: str) -> list[dict[str, Any]]:
        """Read the temporal catalogue in one joined query, ordered ascending."""
        p = self.p
        rows = self._execute(
            f"""SELECT p.*, s.id AS timeline_scene_id, s.external_item_id AS timeline_external_item_id,
                s.provider_id AS timeline_provider_id, s.collection_id AS timeline_collection_id,
                s.acquisition_datetime AS timeline_acquisition_datetime,
                s.cloud_cover AS timeline_cloud_cover, j.status AS timeline_job_status
                FROM derived_product p
                JOIN satellite_scene s ON s.tenant_id=p.tenant_id AND s.id=p.scene_id
                JOIN processing_job j ON j.tenant_id=p.tenant_id AND j.id=p.processing_job_id
                WHERE p.tenant_id={p} AND p.property_id={p}
                  AND p.product_type IN ('NDVI', 'NDVI_QUALITY_MASKED')
                  AND (p.product_type='NDVI_QUALITY_MASKED' OR NOT EXISTS (
                    SELECT 1 FROM derived_product masked
                    WHERE masked.tenant_id=p.tenant_id AND masked.scene_id=p.scene_id
                      AND masked.product_type='NDVI_QUALITY_MASKED'
                  ))
                ORDER BY s.acquisition_datetime ASC, p.created_at ASC, p.id ASC""",  # nosec B608
            [tenant_id, property_id],
        ).fetchall()
        return [
            {
                "product": self._derived_product(row),
                "scene_id": str(row["timeline_scene_id"]),
                "external_scene_id": row["timeline_external_item_id"],
                "provider_id": row["timeline_provider_id"],
                "collection_id": row["timeline_collection_id"],
                "acquisition_datetime": self._timestamp(
                    row["timeline_acquisition_datetime"]
                ),
                "cloud_cover": self._decimal(row["timeline_cloud_cover"]),
                "processing_status": row["timeline_job_status"],
            }
            for row in rows
        ]
