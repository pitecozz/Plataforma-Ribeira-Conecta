from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Iterable

from .epistemology import DataClassification
from .geospatial import (
    DerivedProduct,
    DownloadPolicy,
    GeospatialQuality,
    GeospatialStatus,
    NdviStatistics,
    ProcessingJob,
    ProcessingJobStatus,
    SatelliteAsset,
    SatelliteCollection,
    SatelliteScene,
    SatelliteSearch,
    SatelliteSearchCandidate,
)
from .models import Evidence, now_utc


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
  output_product_id TEXT, failure_reason TEXT, created_at TEXT NOT NULL, started_at TEXT,
  finished_at TEXT, UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS derived_product (
  id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, property_id TEXT NOT NULL, scene_id TEXT NOT NULL,
  processing_job_id TEXT NOT NULL, product_type TEXT NOT NULL, data_classification TEXT NOT NULL,
  valid_count INTEGER NOT NULL, nodata_count INTEGER NOT NULL, minimum TEXT, maximum TEXT,
  mean TEXT, median TEXT, coverage_percentage TEXT, output_reference TEXT, output_checksum TEXT,
  algorithm_id TEXT NOT NULL, algorithm_version TEXT NOT NULL, formula TEXT NOT NULL,
  input_asset_keys TEXT NOT NULL, parameters TEXT NOT NULL, limitations TEXT NOT NULL,
  quality TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(tenant_id, processing_job_id)
);
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

    def create_job(self, item: ProcessingJob) -> ProcessingJob:
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
                "failure_reason",
                "created_at",
                "started_at",
                "finished_at",
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
                item.failure_reason,
                item.created_at,
                item.started_at,
                item.finished_at,
            ],
        )
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
        )

    def get_job(self, tenant_id: str, job_id: str) -> ProcessingJob | None:
        p = self.p
        row = self._one(
            f"SELECT * FROM processing_job WHERE tenant_id={p} AND id={p}",  # nosec B608
            [tenant_id, job_id],
        )
        return self._job(row) if row else None

    def mark_job(
        self,
        tenant_id: str,
        job_id: str,
        status: ProcessingJobStatus,
        failure_reason: str | None = None,
        output_product_id: str | None = None,
    ) -> ProcessingJob:
        p = self.p
        now = now_utc()
        if status == ProcessingJobStatus.RUNNING:
            self._execute(
                f"UPDATE processing_job SET status={p},started_at={p} WHERE tenant_id={p} AND id={p}",  # nosec B608
                [status.value, now, tenant_id, job_id],
            )
        else:
            self._execute(
                f"UPDATE processing_job SET status={p},failure_reason={p},output_product_id={p},finished_at={p} WHERE tenant_id={p} AND id={p}",  # nosec B608
                [
                    status.value,
                    failure_reason,
                    output_product_id,
                    now,
                    tenant_id,
                    job_id,
                ],
            )
        result = self.get_job(tenant_id, job_id)
        if result is None:
            raise LookupError("processing job not found")
        return result

    def create_derived_product(self, item: DerivedProduct) -> DerivedProduct:
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
            ],
        )
        return item

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
