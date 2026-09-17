from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

from shapely.geometry import mapping, shape
from shapely.validation import explain_validity
from pyproj import CRS, Transformer

from .epistemology import DataClassification
from .models import Property, new_id, now_utc
from .time_utils import parse_aware


class DownloadPolicy(StrEnum):
    METADATA_ONLY = "METADATA_ONLY"
    ON_DEMAND = "ON_DEMAND"
    PROCESS_REQUIRED = "PROCESS_REQUIRED"
    CACHE = "CACHE"


class ProcessingJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GeospatialStatus(StrEnum):
    COMPLETED = "COMPLETED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"
    NO_SCENE_FOUND = "NO_SCENE_FOUND"


class GeospatialQuality(StrEnum):
    VALID = "VALID"
    SCENE_INCOMPLETE = "SCENE_INCOMPLETE"
    CLOUD_LIMITATION = "CLOUD_LIMITATION"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    ASSET_UNAVAILABLE = "ASSET_UNAVAILABLE"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    PROVIDER_AUTHENTICATION_FAILED = "PROVIDER_AUTHENTICATION_FAILED"
    ASSET_TOO_LARGE = "ASSET_TOO_LARGE"
    INVALID_ASSET_REFERENCE = "INVALID_ASSET_REFERENCE"
    PROCESSING_QUALITY_EVENT = "PROCESSING_QUALITY_EVENT"
    NDVI_OUT_OF_RANGE = "NDVI_OUT_OF_RANGE"


class GeospatialError(ValueError):
    def __init__(self, status: GeospatialStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class SceneSelectionPolicy:
    policy_id: str = "SENTINEL2_L2A_LATEST_V1"
    version: int = 1
    cloud_cover_limit: Decimal | None = None
    max_candidates: int = 100

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("scene selection policy version must be positive")
        if (
            self.cloud_cover_limit is not None
            and not 0 <= self.cloud_cover_limit <= 100
        ):
            raise ValueError("cloud cover limit must be between 0 and 100")
        if not 1 <= self.max_candidates <= 1000:
            raise ValueError("max candidates must be between 1 and 1000")


@dataclass(frozen=True)
class SatelliteSearchRequest:
    property_id: str
    collection_id: str
    datetime_start: str
    datetime_end: str
    selection_policy: SceneSelectionPolicy = field(default_factory=SceneSelectionPolicy)

    def __post_init__(self) -> None:
        start = parse_aware(self.datetime_start)
        end = parse_aware(self.datetime_end)
        if end <= start:
            raise ValueError("satellite search end must be after start")


@dataclass(frozen=True)
class SatelliteCollection:
    id: str
    provider_id: str
    external_collection_id: str
    title: str | None
    mission: str | None
    processing_level: str | None
    spatial_resolution: str | None
    temporal_characteristics: dict[str, Any]
    bands: dict[str, Any]
    license: str | None
    stac_version: str | None
    metadata: dict[str, Any]
    retrieved_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class SatelliteScene:
    id: str
    tenant_id: str
    property_id: str
    provider_id: str
    collection_id: str
    external_item_id: str
    acquisition_datetime: str
    provider_published_datetime: str | None
    geometry_geojson: dict[str, Any]
    bbox: list[float]
    cloud_cover: Decimal | None
    platform: str | None
    constellation: str | None
    processing_level: str | None
    stac_version: str
    raw_metadata_reference: str
    checksum: str
    ingested_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class SatelliteAsset:
    id: str
    tenant_id: str
    scene_id: str
    asset_key: str
    href: str
    media_type: str | None
    roles: list[str]
    title: str | None
    band_metadata: dict[str, Any]
    download_policy: DownloadPolicy = DownloadPolicy.METADATA_ONLY
    checksum: str | None = None
    size_bytes: int | None = None
    checksum_provider: str | None = None
    checksum_local: str | None = None
    checksum_algorithm: str | None = None
    download_status: str | None = None
    download_started_at: str | None = None
    download_finished_at: str | None = None
    local_reference: str | None = None
    bytes_downloaded: int | None = None


@dataclass(frozen=True)
class SatelliteSearchCandidate:
    id: str
    tenant_id: str
    search_id: str
    scene_id: str
    rank: int
    selected: bool
    rejection_reason: str | None
    criteria: dict[str, Any]


@dataclass(frozen=True)
class SatelliteSearch:
    id: str
    tenant_id: str
    property_id: str
    provider_id: str
    collection_id: str
    datetime_start: str
    datetime_end: str
    aoi_geojson: dict[str, Any]
    source_crs: str
    target_crs: str
    transformation: str
    policy_id: str
    policy_version: int
    cloud_cover_limit: Decimal | None
    status: GeospatialStatus
    candidate_count: int
    selected_scene_id: str | None
    raw_metadata_reference: str | None
    quality: list[GeospatialQuality] = field(default_factory=list)
    failure_reason: str | None = None
    created_at: str = field(default_factory=now_utc)
    completed_at: str | None = None


@dataclass(frozen=True)
class ProcessingJob:
    id: str
    tenant_id: str
    property_id: str
    scene_id: str
    job_type: str
    algorithm_id: str
    algorithm_version: str
    parameters: dict[str, Any]
    status: ProcessingJobStatus
    idempotency_key: str
    output_product_id: str | None = None
    failure_reason: str | None = None
    created_at: str = field(default_factory=now_utc)
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(frozen=True)
class NdviStatistics:
    valid_count: int
    nodata_count: int
    minimum: Decimal | None
    maximum: Decimal | None
    mean: Decimal | None
    median: Decimal | None
    coverage_percentage: Decimal | None


@dataclass(frozen=True)
class DerivedProduct:
    id: str
    tenant_id: str
    property_id: str
    scene_id: str
    processing_job_id: str
    product_type: str
    classification: DataClassification
    statistics: NdviStatistics
    output_reference: str | None
    output_checksum: str | None
    algorithm_id: str
    algorithm_version: str
    formula: str
    input_asset_keys: list[str]
    parameters: dict[str, Any]
    limitations: list[str]
    quality: list[GeospatialQuality]
    created_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class SearchResult:
    search: SatelliteSearch
    scenes: list[SatelliteScene]
    candidates: list[SatelliteSearchCandidate]
    evidence_ids: list[str]


@dataclass(frozen=True)
class NdviResult:
    job: ProcessingJob
    product: DerivedProduct | None
    evidence_ids: list[str]


@dataclass(frozen=True)
class ProviderSearchResult:
    items: list[dict[str, Any]]
    raw_pages: list[dict[str, Any]]


class GeospatialProviderPort(Protocol):
    def get_collection(self, collection_id: str) -> SatelliteCollection: ...

    def search(
        self, request: SatelliteSearchRequest, aoi_geojson: dict[str, Any]
    ) -> ProviderSearchResult: ...


class ObjectStoragePort(Protocol):
    def put_bytes(
        self, key: str, payload: bytes, media_type: str
    ) -> tuple[str, str]: ...

    def put_json(self, key: str, payload: Any) -> tuple[str, str]: ...

    def read_local_path(self, reference: str) -> str: ...


class GeometryService:
    WGS84 = "EPSG:4326"

    @classmethod
    def to_wgs84(cls, property: Property) -> tuple[dict[str, Any], str, str]:
        if property.geometry_geojson is None:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                "property geometry is required for satellite search",
            )
        if not property.geometry_crs:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                "property geometry CRS is required",
            )
        source_crs = property.geometry_crs.upper()
        try:
            geometry = shape(property.geometry_geojson)
            source = CRS.from_user_input(source_crs)
        except Exception as exc:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                "property geometry or CRS could not be parsed",
            ) from exc
        if geometry.is_empty or geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                "AOI must be a non-empty Polygon or MultiPolygon",
            )
        if not geometry.is_valid:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                f"AOI is invalid: {explain_validity(geometry)}",
            )
        try:
            transformer = Transformer.from_crs(
                source, CRS.from_epsg(4326), always_xy=True
            )
            if source.to_epsg() == 4326:
                transformed = geometry
                transformation = "identity: " + source_crs
            else:
                from shapely.ops import transform

                transformed = transform(transformer.transform, geometry)
                transformation = f"pyproj:{source_crs}->EPSG:4326"
        except Exception as exc:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                "AOI CRS transformation failed",
            ) from exc
        if transformed.is_empty or not transformed.is_valid:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                "transformed AOI is invalid",
            )
        minx, miny, maxx, maxy = transformed.bounds
        if minx < -180 or maxx > 180 or miny < -90 or maxy > 90:
            raise GeospatialError(
                GeospatialStatus.INVALID_GEOMETRY,
                "transformed AOI is outside WGS84 bounds",
            )
        return mapping(transformed), source_crs, transformation


class BandResolver:
    """Resolve semantic red/NIR assets from provider metadata, not positions."""

    @staticmethod
    def resolve(assets: dict[str, dict[str, Any]]) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for key, asset in assets.items():
            title = str(asset.get("title") or "").lower()
            roles = {str(item).lower() for item in asset.get("roles", [])}
            if "reflectance" not in roles:
                continue
            if "red (band 4)" in title and "10m" in title:
                resolved.setdefault("red", key)
            if "nir 1 (band 8)" in title and "10m" in title:
                resolved.setdefault("nir", key)
        if set(resolved) != {"red", "nir"}:
            raise ValueError(
                "provider item does not expose validated red and NIR assets"
            )
        return resolved


def item_checksum(item: dict[str, Any]) -> str:
    encoded = json.dumps(
        item, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_scene(
    item: dict[str, Any],
    *,
    tenant_id: str,
    property_id: str,
    provider_id: str,
    collection_id: str,
    raw_metadata_reference: str,
) -> SatelliteScene:
    item_id = item.get("id")
    properties = item.get("properties")
    geometry = item.get("geometry")
    if (
        not isinstance(item_id, str)
        or not isinstance(properties, dict)
        or not isinstance(geometry, dict)
    ):
        raise ValueError("STAC item is missing id, properties or geometry")
    acquisition = properties.get("datetime")
    if not isinstance(acquisition, str):
        raise ValueError("STAC item is missing properties.datetime")
    parse_aware(acquisition)
    bbox = item.get("bbox")
    if not isinstance(bbox, list) or len(bbox) not in {4, 6}:
        raise ValueError("STAC item has invalid bbox")
    cloud = properties.get("eo:cloud_cover")
    cloud_value = None if cloud is None else Decimal(str(cloud))
    if cloud_value is not None and not 0 <= cloud_value <= 100:
        raise ValueError("STAC cloud cover is outside 0..100")
    return SatelliteScene(
        id=new_id(),
        tenant_id=tenant_id,
        property_id=property_id,
        provider_id=provider_id,
        collection_id=collection_id,
        external_item_id=item_id,
        acquisition_datetime=acquisition,
        provider_published_datetime=properties.get("created")
        or properties.get("updated"),
        geometry_geojson=geometry,
        bbox=[float(value) for value in bbox],
        cloud_cover=cloud_value,
        platform=properties.get("platform"),
        constellation=properties.get("constellation"),
        processing_level=properties.get("processing:level"),
        stac_version=str(item.get("stac_version") or "UNKNOWN"),
        raw_metadata_reference=raw_metadata_reference,
        checksum=item_checksum(item),
    )


def processing_idempotency_key(
    scene_id: str,
    property_id: str,
    algorithm_id: str,
    algorithm_version: str,
    parameters: dict[str, Any],
) -> str:
    payload = json.dumps(
        [scene_id, property_id, algorithm_id, algorithm_version, parameters],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
