from __future__ import annotations

import os
from decimal import Decimal
from dataclasses import replace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .audit_context import current_context
from .epistemology import DataClassification
from .geospatial import (
    BandResolver,
    DerivedProduct,
    DerivedProductDependency,
    GeospatialError,
    GeospatialQuality,
    GeospatialStatus,
    NdviResult,
    ProcessingJob,
    ProcessingJobStatus,
    ProviderSearchResult,
    SatelliteAsset,
    SatelliteScene,
    SatelliteSearch,
    SatelliteSearchCandidate,
    SatelliteSearchRequest,
    SearchResult,
    parse_scene,
    processing_idempotency_key,
)
from .geospatial_provider import StacProviderError
from .geospatial_repository import GeospatialRepository
from .field_context import FieldContextRepository
from .models import Evidence, Source, new_id, now_utc
from .object_storage import LocalObjectStorage, ObjectStorageError
from .cdse_s3 import (
    AssetAccessStatus,
    CdseS3AssetAdapter,
    CdseS3Config,
)
from .raster_processing import (
    NdviProcessor,
    RasterProcessingError,
    TemporalDeltaProcessor,
    algorithm_parameters,
)
from .sentinel2_quality import Sentinel2QualityPolicy
from .time_utils import parse_aware


class AssetAccessFailure(RuntimeError):
    def __init__(self, status: AssetAccessStatus, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class GeospatialApplication:
    """Application service for the auditable CDSE discovery and NDVI slice."""

    provider_id = "COPERNICUS_CDSE"

    @staticmethod
    def _max_job_attempts() -> int:
        value = int(os.getenv("RIBEIRA_GEOSPATIAL_JOB_MAX_ATTEMPTS", "3"))
        return min(max(value, 1), 10)

    def __init__(
        self,
        store: Any,
        provider: Any,
        object_storage: LocalObjectStorage,
        asset_adapter: CdseS3AssetAdapter | None = None,
    ) -> None:
        self.store = store
        self.provider = provider
        self.object_storage = object_storage
        self.repository = GeospatialRepository(store)
        self.fields = FieldContextRepository(store)
        self.processor = NdviProcessor(object_storage)
        asset_config = CdseS3Config.from_environment()
        registry = getattr(provider, "registry", None)
        provider_metadata = (
            registry.get(self.provider_id) if registry is not None else None
        )
        if provider_metadata is not None:
            if provider_metadata.asset_endpoint and not os.getenv("CDSE_S3_ENDPOINT"):
                asset_config = replace(
                    asset_config, endpoint=provider_metadata.asset_endpoint
                )
            if provider_metadata.asset_bucket and not os.getenv("CDSE_S3_BUCKET"):
                asset_config = replace(
                    asset_config, bucket=provider_metadata.asset_bucket
                )
        self.asset_adapter = asset_adapter or CdseS3AssetAdapter(
            object_storage=object_storage,
            config=asset_config,
        )

    def _prepare_processing_assets(
        self,
        tenant_id: str,
        job_id: str,
        assets: list[SatelliteAsset],
        actor: str,
        platform_admin: bool,
        required_asset_keys: set[str] | None = None,
    ) -> tuple[list[SatelliteAsset], list[dict[str, Any]]]:
        """Acquire only the semantic RED/NIR inputs required by NDVI."""
        try:
            roles = BandResolver.resolve(
                {
                    item.asset_key: {"title": item.title, "roles": item.roles}
                    for item in assets
                }
            )
        except ValueError as exc:
            raise RuntimeError("required RED/NIR assets could not be resolved") from exc

        required = required_asset_keys or {roles["red"], roles["nir"]}
        if len(required) > self.asset_adapter.config.max_assets_per_job:
            raise AssetAccessFailure(
                AssetAccessStatus.ASSET_TOO_LARGE, "ASSET_COUNT_LIMIT"
            )
        prepared: list[SatelliteAsset] = []
        access_records: list[dict[str, Any]] = []
        job_bytes = 0
        for asset in assets:
            if asset.asset_key not in required:
                prepared.append(asset)
                continue
            if asset.local_reference:
                try:
                    self.object_storage.read_local_path(asset.local_reference)
                    prepared.append(replace(asset, href=asset.local_reference))
                    access_records.append(
                        {
                            "asset_id": asset.id,
                            "asset_key": asset.asset_key,
                            "status": AssetAccessStatus.CACHED.value,
                            "local_reference": asset.local_reference,
                            "checksum_local": asset.checksum_local,
                        }
                    )
                    continue
                except ObjectStorageError:  # stale cache is re-acquired below
                    pass
            if asset.href.startswith("local://"):
                self.object_storage.read_local_path(asset.href)
                prepared.append(asset)
                access_records.append(
                    {
                        "asset_id": asset.id,
                        "asset_key": asset.asset_key,
                        "status": AssetAccessStatus.CACHED.value,
                        "local_reference": asset.href,
                        "checksum_local": asset.checksum_local,
                    }
                )
                continue
            with self.store.tenant_transaction(tenant_id, platform_admin):
                self.store.audit(
                    tenant_id,
                    actor,
                    "ASSET_ACCESS_STARTED",
                    "satellite_asset",
                    asset.id,
                    {"asset_key": asset.asset_key, "policy": "PROCESS_REQUIRED"},
                    new_id(),
                    now_utc(),
                )
            result = self.asset_adapter.download(
                asset.href,
                f"tenants/{tenant_id}/assets/{asset.id}/{asset.asset_key.replace('/', '_')}",
                max_job_bytes=self.asset_adapter.config.max_job_bytes - job_bytes,
            )
            access_record = {
                "asset_id": asset.id,
                "asset_key": asset.asset_key,
                "status": result.status.value,
                "bucket": result.bucket,
                "object_key": result.object_key,
                "size_bytes": result.size_bytes,
                "bytes_downloaded": result.bytes_downloaded,
                "checksum_algorithm": result.checksum_algorithm,
                "checksum_local": result.checksum_local,
                "checksum_provider": result.checksum_provider,
                "local_reference": result.local_reference,
                "failure_code": result.failure_code,
            }
            access_records.append(access_record)
            with self.store.tenant_transaction(tenant_id, platform_admin):
                self.repository.update_asset_access(
                    tenant_id,
                    asset.id,
                    status=result.status.value,
                    checksum_provider=result.checksum_provider,
                    checksum_local=result.checksum_local,
                    checksum_algorithm=result.checksum_algorithm,
                    size_bytes=result.size_bytes,
                    bytes_downloaded=result.bytes_downloaded,
                    local_reference=result.local_reference,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                )
                self.store.audit(
                    tenant_id,
                    actor,
                    "ASSET_ACCESS_COMPLETED"
                    if result.local_reference
                    else "ASSET_ACCESS_FAILED",
                    "satellite_asset",
                    asset.id,
                    {
                        "asset_key": asset.asset_key,
                        "status": result.status.value,
                        "failure_code": result.failure_code,
                        "bytes_downloaded": result.bytes_downloaded,
                    },
                    new_id(),
                    now_utc(),
                )
            if (
                result.status
                not in {
                    AssetAccessStatus.SUCCEEDED,
                    AssetAccessStatus.CACHED,
                }
                or not result.local_reference
            ):
                raise AssetAccessFailure(
                    result.status, result.failure_code or "ASSET_UNAVAILABLE"
                )
            job_bytes += result.bytes_downloaded
            prepared.append(replace(asset, href=result.local_reference))
        return prepared, access_records

    def _source(self, tenant_id: str) -> Source:
        source_id = str(uuid5(NAMESPACE_URL, f"ribeira:{tenant_id}:{self.provider_id}"))
        source = self.store.get_source(tenant_id, source_id)
        if source is not None:
            return source
        registry = getattr(self.provider, "registry", None)
        metadata = registry.get(self.provider_id) if registry is not None else None
        endpoint = metadata.catalog_endpoint if metadata else None
        version = metadata.stac_version if metadata else None
        return self.store.create_source(
            Source(
                id=source_id,
                tenant_id=tenant_id,
                name="Copernicus Data Space Ecosystem STAC",
                source_type="STAC",
                provider=self.provider_id,
                endpoint=endpoint,
                source_version=version,
            )
        )

    def _raw_reference(
        self, tenant_id: str, search_id: str, payload: Any, name: str
    ) -> str:
        reference, _ = self.object_storage.put_json(
            f"tenants/{tenant_id}/satellite-searches/{search_id}/{name}.json",
            payload,
        )
        return reference

    def search_satellite(
        self,
        tenant_id: str,
        request: SatelliteSearchRequest,
        actor: str = "system",
        platform_admin: bool = False,
    ) -> SearchResult:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            property_item = self.store.get_property(tenant_id, request.property_id)
            if property_item is None:
                raise LookupError("property not found in tenant")
            source = self._source(tenant_id)
        aoi, source_crs, transformation = self._geometry(request, property_item)
        try:
            collection = self.provider.get_collection(request.collection_id)
        except StacProviderError as exc:
            raise GeospatialError(
                GeospatialStatus.SOURCE_UNAVAILABLE,
                f"{exc.code}: {exc}",
            ) from exc
        search = SatelliteSearch(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=request.property_id,
            provider_id=self.provider_id,
            collection_id=request.collection_id,
            datetime_start=request.datetime_start,
            datetime_end=request.datetime_end,
            aoi_geojson=aoi,
            source_crs=source_crs,
            target_crs="EPSG:4326",
            transformation=transformation,
            policy_id=request.selection_policy.policy_id,
            policy_version=request.selection_policy.version,
            cloud_cover_limit=request.selection_policy.cloud_cover_limit,
            status=GeospatialStatus.INCONCLUSIVE,
            candidate_count=0,
            selected_scene_id=None,
            raw_metadata_reference=None,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.upsert_collection(collection)
            self.repository.create_search(search)
            self.store.audit(
                tenant_id,
                actor,
                "SATELLITE_SEARCH_REQUESTED",
                "satellite_search",
                search.id,
                {
                    "provider": self.provider_id,
                    "collection": request.collection_id,
                    "policy_id": request.selection_policy.policy_id,
                    "policy_version": request.selection_policy.version,
                },
                new_id(),
                now_utc(),
            )
        try:
            result = self.provider.search(request, aoi)
            if isinstance(result, list):  # compatibility for simple test doubles
                result = ProviderSearchResult(result, [])
        except StacProviderError as exc:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                self.repository.update_search(
                    tenant_id,
                    search.id,
                    GeospatialStatus.SOURCE_UNAVAILABLE,
                    0,
                    None,
                    None,
                    [GeospatialQuality.SOURCE_UNAVAILABLE],
                    f"{exc.code}: {exc}",
                )
                self.store.create_quality_event(
                    tenant_id,
                    request.property_id,
                    source.id,
                    "SOURCE_UNAVAILABLE",
                    {"provider": self.provider_id, "code": exc.code},
                    new_id(),
                    now_utc(),
                )
            with self.store.tenant_transaction(tenant_id, platform_admin):
                updated = self.repository.get_search(tenant_id, search.id)
            if updated is None:
                raise RuntimeError(
                    "satellite search disappeared after provider failure"
                )
            return SearchResult(updated, [], [], [])

        raw_reference = self._raw_reference(
            tenant_id, search.id, result.raw_pages, "stac-response"
        )
        scenes: list[SatelliteScene] = []
        evidence_ids: list[str] = []
        with self.store.tenant_transaction(tenant_id, platform_admin):
            for item in result.items[: request.selection_policy.max_candidates]:
                try:
                    scene = parse_scene(
                        item,
                        tenant_id=tenant_id,
                        property_id=request.property_id,
                        provider_id=self.provider_id,
                        collection_id=request.collection_id,
                        raw_metadata_reference=raw_reference,
                    )
                    scene = self.repository.upsert_scene(scene)
                    scenes.append(scene)
                    for key, raw_asset in (item.get("assets") or {}).items():
                        if not isinstance(raw_asset, dict) or not isinstance(
                            raw_asset.get("href"), str
                        ):
                            continue
                        href = raw_asset["href"]
                        asset_policy = getattr(
                            self.provider, "asset_href_allowed", None
                        )
                        if callable(asset_policy) and not asset_policy(href):
                            self.store.create_quality_event(
                                tenant_id,
                                request.property_id,
                                source.id,
                                "ASSET_UNAVAILABLE",
                                {
                                    "scene_id": scene.id,
                                    "asset_key": str(key),
                                    "reason": "asset host or scheme is not allowlisted",
                                },
                                new_id(),
                                now_utc(),
                            )
                            continue
                        self.repository.upsert_asset(
                            SatelliteAsset(
                                id=new_id(),
                                tenant_id=tenant_id,
                                scene_id=scene.id,
                                asset_key=str(key),
                                href=href,
                                media_type=raw_asset.get("type"),
                                roles=[
                                    str(role)
                                    for role in raw_asset.get("roles", [])
                                    if isinstance(role, str)
                                ],
                                title=raw_asset.get("title"),
                                band_metadata=raw_asset,
                            )
                        )
                    existing_evidence = self.store.evidence_for_reference(
                        tenant_id, scene.id
                    )
                    if existing_evidence is None:
                        evidence = Evidence(
                            id=new_id(),
                            tenant_id=tenant_id,
                            evidence_type="SATELLITE_SCENE",
                            reference_id=scene.id,
                            classification=DataClassification.OFFICIAL_SOURCE,
                            source_id=source.id,
                            observed_at=scene.acquisition_datetime,
                            transformation="CDSE STAC Item catalogued without raster transformation",
                            limitations=[
                                "Scene metadata is not a pixel-level cloud mask"
                            ],
                        )
                        self.repository.create_evidence(evidence)
                        evidence_ids.append(evidence.id)
                    else:
                        evidence_ids.append(existing_evidence.id)
                except (ValueError, TypeError, KeyError) as exc:
                    self.store.create_quality_event(
                        tenant_id,
                        request.property_id,
                        source.id,
                        "SCENE_INCOMPLETE",
                        {"error": str(exc)},
                        new_id(),
                        now_utc(),
                    )

            ordered = sorted(
                scenes,
                key=lambda item: (
                    parse_aware(item.acquisition_datetime),
                    item.cloud_cover is None,
                    item.cloud_cover
                    if item.cloud_cover is not None
                    else Decimal("101"),
                ),
                reverse=True,
            )
            candidates: list[SatelliteSearchCandidate] = []
            selected: SatelliteScene | None = None
            for rank, scene in enumerate(ordered, 1):
                rejection = None
                if (
                    request.selection_policy.cloud_cover_limit is not None
                    and scene.cloud_cover is not None
                    and scene.cloud_cover > request.selection_policy.cloud_cover_limit
                ):
                    rejection = "CLOUD_COVER_ABOVE_POLICY_LIMIT"
                elif (
                    request.selection_policy.cloud_cover_limit is not None
                    and scene.cloud_cover is None
                ):
                    rejection = "CLOUD_METADATA_UNKNOWN"
                elif selected is None:
                    selected = scene
                candidates.append(
                    SatelliteSearchCandidate(
                        id=new_id(),
                        tenant_id=tenant_id,
                        search_id=search.id,
                        scene_id=scene.id,
                        rank=rank,
                        selected=selected is scene,
                        rejection_reason=rejection,
                        criteria={
                            "acquisition_datetime": scene.acquisition_datetime,
                            "cloud_cover": str(scene.cloud_cover)
                            if scene.cloud_cover is not None
                            else None,
                            "cloud_cover_limit": str(
                                request.selection_policy.cloud_cover_limit
                            )
                            if request.selection_policy.cloud_cover_limit is not None
                            else None,
                        },
                    )
                )
                self.repository.create_candidate(candidates[-1])
            status = (
                GeospatialStatus.COMPLETED
                if selected
                else GeospatialStatus.NO_SCENE_FOUND
            )
            quality = [] if selected else [GeospatialQuality.CLOUD_LIMITATION]
            self.repository.update_search(
                tenant_id,
                search.id,
                status,
                len(scenes),
                selected.id if selected else None,
                raw_reference,
                quality,
                None if selected else "No scene met the configured selection policy",
            )
            self.store.audit(
                tenant_id,
                actor,
                "SATELLITE_SEARCH_COMPLETED",
                "satellite_search",
                search.id,
                {
                    "candidate_count": len(scenes),
                    "selected_scene_id": selected.id if selected else None,
                    "raw_metadata_reference": raw_reference,
                },
                new_id(),
                now_utc(),
            )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            persisted = self.repository.get_search(tenant_id, search.id)
        if persisted is None:
            raise RuntimeError("satellite search disappeared after completion")
        return SearchResult(persisted, scenes, candidates, evidence_ids)

    @staticmethod
    def _geometry(
        request: SatelliteSearchRequest, property_item: Any
    ) -> tuple[dict[str, Any], str, str]:
        from .geospatial import GeometryService

        return GeometryService.to_wgs84(property_item)

    def create_ndvi_job(
        self,
        tenant_id: str,
        property_id: str,
        search_id: str,
        actor: str = "system",
        platform_admin: bool = False,
    ) -> ProcessingJob:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            search = self.repository.get_search(tenant_id, search_id)
        if search is None or search.property_id != property_id:
            raise LookupError("satellite search not found in tenant")
        if search.selected_scene_id is None:
            raise GeospatialError(
                GeospatialStatus.INCONCLUSIVE, "search has no selected scene"
            )
        parameters = algorithm_parameters(search.aoi_geojson)
        key = processing_idempotency_key(
            search.selected_scene_id,
            property_id,
            NdviProcessor.algorithm_id,
            NdviProcessor.algorithm_version,
            parameters,
        )
        request_id, correlation_id = current_context()
        job = ProcessingJob(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=property_id,
            scene_id=search.selected_scene_id,
            job_type="NDVI",
            algorithm_id=NdviProcessor.algorithm_id,
            algorithm_version=NdviProcessor.algorithm_version,
            parameters=parameters,
            status=ProcessingJobStatus.QUEUED,
            idempotency_key=key,
            max_attempts=self._max_job_attempts(),
            requested_by=actor,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            persisted = self.repository.create_job(job, actor)
            self.store.audit(
                tenant_id,
                actor,
                "NDVI_JOB_CREATED",
                "processing_job",
                persisted.id,
                {
                    "scene_id": persisted.scene_id,
                    "algorithm_version": persisted.algorithm_version,
                    "idempotency_key": persisted.idempotency_key,
                },
                new_id(),
                now_utc(),
            )
        return persisted

    def run_ndvi_job(
        self,
        tenant_id: str,
        job_id: str,
        actor: str = "system",
        platform_admin: bool = False,
        worker_id: str | None = None,
    ) -> NdviResult:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            job = self.repository.get_job(tenant_id, job_id)
        if job is None:
            raise LookupError("processing job not found in tenant")
        if job.status == ProcessingJobStatus.SUCCEEDED and job.output_product_id:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                product = self.repository.get_derived_product(
                    tenant_id, job.output_product_id
                )
            return NdviResult(job, product, [])
        with self.store.tenant_transaction(tenant_id, platform_admin):
            property_item = self.store.get_property(tenant_id, job.property_id)
            scene = self.repository.get_scene(tenant_id, job.scene_id)
            assets = self.repository.list_assets(tenant_id, job.scene_id)
        if property_item is None or scene is None:
            raise LookupError("processing references are outside tenant")
        from .geospatial import GeometryService

        aoi, _, _ = GeometryService.to_wgs84(property_item)
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.mark_job(
                tenant_id,
                job.id,
                ProcessingJobStatus.RUNNING,
                actor=actor,
                worker_id=worker_id,
            )
        try:
            processing_assets, access_records = self._prepare_processing_assets(
                tenant_id, job.id, assets, actor, platform_admin
            )
            output = self.processor.process(
                processing_assets,
                aoi,
                f"tenants/{tenant_id}/derived/{job.id}/ndvi.tif",
            )
        except AssetAccessFailure as exc:
            quality = {
                AssetAccessStatus.BLOCKED_BY_CREDENTIAL: GeospatialQuality.ASSET_UNAVAILABLE,
                AssetAccessStatus.PROVIDER_AUTHENTICATION_FAILED: GeospatialQuality.PROVIDER_AUTHENTICATION_FAILED,
                AssetAccessStatus.ASSET_TOO_LARGE: GeospatialQuality.ASSET_TOO_LARGE,
                AssetAccessStatus.INVALID_ASSET_REFERENCE: GeospatialQuality.INVALID_ASSET_REFERENCE,
                AssetAccessStatus.SOURCE_UNAVAILABLE: GeospatialQuality.SOURCE_UNAVAILABLE,
            }.get(exc.status, GeospatialQuality.ASSET_UNAVAILABLE)
            with self.store.tenant_transaction(tenant_id, platform_admin):
                failed = self.repository.mark_job(
                    tenant_id,
                    job.id,
                    ProcessingJobStatus.BLOCKED
                    if exc.status == AssetAccessStatus.BLOCKED_BY_CREDENTIAL
                    else ProcessingJobStatus.FAILED,
                    failure_reason=exc.status.value,
                    failure_code=exc.code,
                    actor=actor,
                    worker_id=worker_id,
                )
                self.store.create_quality_event(
                    tenant_id,
                    job.property_id,
                    None,
                    quality.value,
                    {
                        "job_id": job.id,
                        "access_status": exc.status.value,
                        "failure_code": exc.code,
                    },
                    new_id(),
                    now_utc(),
                )
                self.store.audit(
                    tenant_id,
                    actor,
                    "ASSET_ACCESS_FAILED",
                    "processing_job",
                    job.id,
                    {"status": exc.status.value, "failure_code": exc.code},
                    new_id(),
                    now_utc(),
                )
            return NdviResult(failed, None, [])
        except RasterProcessingError as exc:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                failed = self.repository.mark_job(
                    tenant_id,
                    job.id,
                    ProcessingJobStatus.FAILED,
                    failure_reason=type(exc).__name__,
                    failure_code=type(exc).__name__,
                    actor=actor,
                    worker_id=worker_id,
                )
                self.store.create_quality_event(
                    tenant_id,
                    job.property_id,
                    None,
                    exc.quality.value,
                    {"job_id": job.id, "error_type": type(exc).__name__},
                    new_id(),
                    now_utc(),
                )
                self.store.audit(
                    tenant_id,
                    actor,
                    "NDVI_JOB_FAILED",
                    "processing_job",
                    job.id,
                    {"quality": exc.quality.value, "error_type": type(exc).__name__},
                    new_id(),
                    now_utc(),
                )
            return NdviResult(failed, None, [])
        except RuntimeError as exc:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                failed = self.repository.mark_job(
                    tenant_id,
                    job.id,
                    ProcessingJobStatus.FAILED,
                    failure_reason=type(exc).__name__,
                    failure_code=type(exc).__name__,
                    actor=actor,
                    worker_id=worker_id,
                )
                self.store.create_quality_event(
                    tenant_id,
                    job.property_id,
                    None,
                    GeospatialQuality.ASSET_UNAVAILABLE.value,
                    {"job_id": job.id, "error_type": type(exc).__name__},
                    new_id(),
                    now_utc(),
                )
            return NdviResult(failed, None, [])
        product = DerivedProduct(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=job.property_id,
            scene_id=scene.id,
            processing_job_id=job.id,
            product_type="NDVI",
            classification=DataClassification.DERIVED,
            statistics=output.statistics,
            output_reference=output.output_reference,
            output_checksum=output.output_checksum,
            algorithm_id=NdviProcessor.algorithm_id,
            algorithm_version=NdviProcessor.algorithm_version,
            formula=NdviProcessor.formula,
            input_asset_keys=output.input_asset_keys,
            parameters={
                **job.parameters,
                "scene_id": scene.id,
                "external_item_id": scene.external_item_id,
                "acquisition_datetime": scene.acquisition_datetime,
                "input_asset_ids": [
                    asset.id
                    for asset in processing_assets
                    if asset.asset_key in output.input_asset_keys
                ],
                "asset_access": access_records,
            },
            limitations=output.limitations
            + ["NDVI is not a disease diagnosis or causal explanation"],
            quality=output.quality,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.create_derived_product(product)
            completed = self.repository.mark_job(
                tenant_id,
                job.id,
                ProcessingJobStatus.SUCCEEDED,
                output_product_id=product.id,
                actor=actor,
                worker_id=worker_id,
            )
            source = self._source(tenant_id)
            evidence = Evidence(
                id=new_id(),
                tenant_id=tenant_id,
                evidence_type="DERIVED_PRODUCT",
                reference_id=product.id,
                classification=DataClassification.DERIVED,
                source_id=source.id,
                observed_at=scene.acquisition_datetime,
                transformation=f"{NdviProcessor.algorithm_id} {NdviProcessor.algorithm_version}: {NdviProcessor.formula}",
                limitations=product.limitations,
            )
            self.repository.create_evidence(evidence)
            self.store.audit(
                tenant_id,
                actor,
                "NDVI_JOB_COMPLETED",
                "derived_product",
                product.id,
                {
                    "processing_job_id": job.id,
                    "output_checksum": product.output_checksum,
                    "classification": product.classification.value,
                },
                new_id(),
                now_utc(),
            )
        return NdviResult(completed, product, [evidence.id])

    def create_quality_masked_ndvi_job(
        self,
        tenant_id: str,
        property_id: str,
        source_product_id: str,
        actor: str = "system",
        platform_admin: bool = False,
    ) -> ProcessingJob:
        """Create a persisted reprocessing job that adds the official SCL mask."""
        policy = Sentinel2QualityPolicy()
        with self.store.tenant_transaction(tenant_id, platform_admin):
            source_product = self.repository.get_derived_product(
                tenant_id, source_product_id
            )
        if source_product is None:
            raise LookupError("source NDVI product not found in tenant")
        if (
            source_product.property_id != property_id
            or source_product.product_type not in {"NDVI", "NDVI_QUALITY_MASKED"}
        ):
            raise ValueError(
                "quality-masked NDVI requires an NDVI product of the requested property"
            )
        params = {
            "source_product_id": source_product.id,
            "quality_mask_policy": policy.record(),
            **algorithm_parameters(
                {"type": "quality-masked-ndvi", "source_product_id": source_product.id}
            ),
        }
        request_id, correlation_id = current_context()
        job = ProcessingJob(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=property_id,
            scene_id=source_product.scene_id,
            job_type="QUALITY_MASKED_NDVI",
            algorithm_id="NDVI_QUALITY_MASKED",
            algorithm_version="1.0.3",
            parameters=params,
            status=ProcessingJobStatus.QUEUED,
            idempotency_key=processing_idempotency_key(
                source_product.scene_id,
                property_id,
                "NDVI_QUALITY_MASKED",
                "1.0.3",
                params,
            ),
            max_attempts=self._max_job_attempts(),
            requested_by=actor,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            persisted = self.repository.create_job(job, actor)
            self.store.audit(
                tenant_id,
                actor,
                "QUALITY_MASKED_NDVI_JOB_CREATED",
                "processing_job",
                persisted.id,
                {"source_product_id": source_product.id, "policy": policy.policy_id},
                new_id(),
                now_utc(),
            )
        return persisted

    def run_quality_masked_ndvi_job(
        self,
        tenant_id: str,
        job_id: str,
        actor: str = "system",
        platform_admin: bool = False,
        worker_id: str | None = None,
    ) -> NdviResult:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            job = self.repository.get_job(tenant_id, job_id)
        if job is None or job.job_type != "QUALITY_MASKED_NDVI":
            raise LookupError("quality-masked NDVI processing job not found in tenant")
        if job.status == ProcessingJobStatus.SUCCEEDED and job.output_product_id:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                product = self.repository.get_derived_product(
                    tenant_id, job.output_product_id
                )
            return NdviResult(job, product, [])
        with self.store.tenant_transaction(tenant_id, platform_admin):
            property_item = self.store.get_property(tenant_id, job.property_id)
            scene = self.repository.get_scene(tenant_id, job.scene_id)
            assets = self.repository.list_assets(tenant_id, job.scene_id)
        if property_item is None or scene is None:
            raise LookupError("processing references are outside tenant")
        policy = Sentinel2QualityPolicy()
        if policy.scl_asset_key not in {asset.asset_key for asset in assets}:
            raise ValueError(
                "scene does not expose the required official SCL_20m asset"
            )
        from .geospatial import GeometryService

        aoi, _, _ = GeometryService.to_wgs84(property_item)
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.mark_job(
                tenant_id,
                job.id,
                ProcessingJobStatus.RUNNING,
                actor=actor,
                worker_id=worker_id,
            )
        try:
            prepared, access_records = self._prepare_processing_assets(
                tenant_id,
                job.id,
                assets,
                actor,
                platform_admin,
                required_asset_keys={"B04_10m", "B08_10m", policy.scl_asset_key},
            )
            output = self.processor.process(
                prepared,
                aoi,
                f"tenants/{tenant_id}/derived/{job.id}/quality-masked-ndvi.tif",
                quality_policy=policy,
            )
        except (
            AssetAccessFailure,
            RasterProcessingError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as exc:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                failure = getattr(exc, "code", type(exc).__name__)
                failed = self.repository.mark_job(
                    tenant_id,
                    job.id,
                    ProcessingJobStatus.BLOCKED
                    if isinstance(exc, AssetAccessFailure)
                    and exc.status == AssetAccessStatus.BLOCKED_BY_CREDENTIAL
                    else ProcessingJobStatus.FAILED,
                    failure_reason=type(exc).__name__,
                    failure_code=failure,
                    actor=actor,
                    worker_id=worker_id,
                )
                self.store.audit(
                    tenant_id,
                    actor,
                    "QUALITY_MASKED_NDVI_JOB_FAILED",
                    "processing_job",
                    job.id,
                    {"failure": failure},
                    new_id(),
                    now_utc(),
                )
            return NdviResult(failed, None, [])
        quality_mask = dict(output.quality_mask or {})
        scl_access = next(
            (
                record
                for record in access_records
                if record["asset_key"] == policy.scl_asset_key
            ),
            None,
        )
        if scl_access is not None:
            quality_mask["scl_asset_id"] = scl_access["asset_id"]
            quality_mask["scl_checksum"] = scl_access.get("checksum_local")
        product = DerivedProduct(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=job.property_id,
            scene_id=scene.id,
            processing_job_id=job.id,
            product_type="NDVI_QUALITY_MASKED",
            classification=DataClassification.DERIVED,
            statistics=output.statistics,
            output_reference=output.output_reference,
            output_checksum=output.output_checksum,
            algorithm_id="NDVI_QUALITY_MASKED",
            algorithm_version="1.0.3",
            formula=NdviProcessor.formula,
            input_asset_keys=output.input_asset_keys,
            parameters={
                **job.parameters,
                "scene_id": scene.id,
                "acquisition_datetime": scene.acquisition_datetime,
                "input_asset_ids": [
                    asset.id
                    for asset in prepared
                    if asset.asset_key in output.input_asset_keys
                ],
                "asset_access": access_records,
                "quality_mask": quality_mask,
            },
            limitations=output.limitations
            + ["SCL is a scene-classification quality policy, not a causal diagnosis"],
            quality=output.quality,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.create_derived_product(product)
            completed = self.repository.mark_job(
                tenant_id,
                job.id,
                ProcessingJobStatus.SUCCEEDED,
                output_product_id=product.id,
                actor=actor,
                worker_id=worker_id,
            )
            source = self._source(tenant_id)
            evidence = Evidence(
                id=new_id(),
                tenant_id=tenant_id,
                evidence_type="DERIVED_PRODUCT",
                reference_id=product.id,
                classification=DataClassification.DERIVED,
                source_id=source.id,
                observed_at=scene.acquisition_datetime,
                transformation=f"NDVI_QUALITY_MASKED 1.0.3: {NdviProcessor.formula}; {policy.policy_id}",
                limitations=product.limitations,
            )
            self.repository.create_evidence(evidence)
            self.store.audit(
                tenant_id,
                actor,
                "QUALITY_MASKED_NDVI_JOB_COMPLETED",
                "derived_product",
                product.id,
                {
                    "processing_job_id": job.id,
                    "output_checksum": product.output_checksum,
                    "policy": policy.record(),
                },
                new_id(),
                now_utc(),
            )
        return NdviResult(completed, product, [evidence.id])

    @staticmethod
    def _has_valid_quality_mask(product: DerivedProduct) -> bool:
        quality_mask = product.parameters.get("quality_mask")
        policy = Sentinel2QualityPolicy()
        if product.product_type != "NDVI_QUALITY_MASKED" or not isinstance(
            quality_mask, dict
        ):
            return False
        expected = policy.record()
        return (
            all(quality_mask.get(key) == value for key, value in expected.items())
            and isinstance(quality_mask.get("scl_asset_id"), str)
            and bool(quality_mask["scl_asset_id"].strip())
            and isinstance(quality_mask.get("scl_checksum"), str)
            and bool(quality_mask["scl_checksum"].strip())
            and isinstance(quality_mask.get("valid_before_scl"), int)
            and isinstance(quality_mask.get("discarded_by_scl"), int)
            and isinstance(quality_mask.get("valid_after_scl"), int)
            and quality_mask["valid_before_scl"]
            == quality_mask["discarded_by_scl"] + quality_mask["valid_after_scl"]
            and quality_mask["valid_after_scl"] == product.statistics.valid_count
        )

    @classmethod
    def _has_valid_temporal_delta_provenance(
        cls,
        delta: DerivedProduct,
        baseline: DerivedProduct,
        target: DerivedProduct,
    ) -> bool:
        alignment = delta.parameters.get("alignment")
        policies = delta.parameters.get("quality_mask_policies")
        valid_alignment = isinstance(alignment, dict) and (
            all(
                alignment.get(key) == value
                for key, value in {
                    "status": "IDENTICAL_GRID",
                    "target_grid": "baseline",
                    "resampling": None,
                }.items()
            )
            or all(
                alignment.get(key) == value
                for key, value in {
                    "status": "REPROJECTED_TO_BASELINE",
                    "target_grid": "baseline",
                    "resampling": "bilinear",
                }.items()
            )
        )
        return (
            delta.product_type == "NDVI_DELTA"
            and delta.algorithm_id == TemporalDeltaProcessor.algorithm_id
            and delta.algorithm_version == TemporalDeltaProcessor.algorithm_version
            and delta.formula == TemporalDeltaProcessor.formula
            and bool(delta.output_reference)
            and bool(delta.output_checksum)
            and valid_alignment
            and isinstance(policies, list)
            and policies
            == [
                baseline.parameters.get("quality_mask"),
                target.parameters.get("quality_mask"),
            ]
            and cls._has_valid_quality_mask(baseline)
            and cls._has_valid_quality_mask(target)
        )

    @staticmethod
    def _has_valid_field_delta_provenance(
        delta: DerivedProduct, field: Any | None
    ) -> bool:
        snapshot = delta.parameters.get("field_snapshot")
        return (
            field is not None
            and delta.field_id == field.id
            and delta.property_id == field.property_id
            and delta.field_boundary_version == field.boundary_version
            and delta.field_boundary_checksum == field.boundary_checksum
            and snapshot
            == {
                "field_id": field.id,
                "boundary_version": field.boundary_version,
                "boundary_checksum": field.boundary_checksum,
            }
        )

    def create_temporal_delta_job(
        self,
        tenant_id: str,
        property_id: str,
        baseline_product_id: str,
        target_product_id: str,
        actor: str = "system",
        field_id: str | None = None,
        platform_admin: bool = False,
    ) -> ProcessingJob:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            baseline = self.repository.get_derived_product(
                tenant_id, baseline_product_id
            )
            target = self.repository.get_derived_product(tenant_id, target_product_id)
            field = self.fields.get(tenant_id, field_id) if field_id else None
        if baseline is None or target is None:
            raise LookupError("quality-masked NDVI product not found in tenant")
        if baseline.property_id != property_id or target.property_id != property_id:
            raise ValueError(
                "baseline and target must belong to the requested property"
            )
        if field_id and field is None:
            raise LookupError("field not found in tenant")
        if field is not None and field.property_id != property_id:
            raise ValueError("field does not belong to the requested property")
        if (
            baseline.id == target.id
            or not self._has_valid_quality_mask(baseline)
            or not self._has_valid_quality_mask(target)
        ):
            raise ValueError(
                "temporal delta requires two different provenance-valid quality-masked NDVI products"
            )
        params: dict[str, Any] = {
            "baseline_product_id": baseline.id,
            "target_product_id": target.id,
            "target_grid": "baseline",
            "alignment_resampling": "bilinear",
        }
        if field is not None:
            params["field_snapshot"] = {
                "field_id": field.id,
                "boundary_version": field.boundary_version,
                "boundary_checksum": field.boundary_checksum,
            }
        request_id, correlation_id = current_context()
        job = ProcessingJob(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=property_id,
            scene_id=baseline.scene_id,
            job_type="TEMPORAL_DELTA",
            algorithm_id=TemporalDeltaProcessor.algorithm_id,
            algorithm_version=TemporalDeltaProcessor.algorithm_version,
            parameters=params,
            status=ProcessingJobStatus.QUEUED,
            idempotency_key=processing_idempotency_key(
                baseline.scene_id,
                property_id,
                TemporalDeltaProcessor.algorithm_id,
                TemporalDeltaProcessor.algorithm_version,
                params,
            ),
            max_attempts=self._max_job_attempts(),
            requested_by=actor,
            request_id=request_id,
            correlation_id=correlation_id,
            field_id=field.id if field is not None else None,
            field_boundary_version=field.boundary_version
            if field is not None
            else None,
            field_boundary_checksum=field.boundary_checksum
            if field is not None
            else None,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            persisted = self.repository.create_job(job, actor)
            self.store.audit(
                tenant_id,
                actor,
                "TEMPORAL_DELTA_JOB_CREATED",
                "processing_job",
                persisted.id,
                params,
                new_id(),
                now_utc(),
            )
        return persisted

    def run_temporal_delta_job(
        self,
        tenant_id: str,
        job_id: str,
        actor: str = "system",
        platform_admin: bool = False,
        worker_id: str | None = None,
    ) -> NdviResult:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            job = self.repository.get_job(tenant_id, job_id)
        if job is None or job.job_type != "TEMPORAL_DELTA":
            raise LookupError("temporal delta processing job not found in tenant")
        if job.status == ProcessingJobStatus.SUCCEEDED and job.output_product_id:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                product = self.repository.get_derived_product(
                    tenant_id, job.output_product_id
                )
            return NdviResult(job, product, [])
        baseline_id = str(job.parameters.get("baseline_product_id") or "")
        target_id = str(job.parameters.get("target_product_id") or "")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            baseline = self.repository.get_derived_product(tenant_id, baseline_id)
            target = self.repository.get_derived_product(tenant_id, target_id)
            field = (
                self.fields.get_snapshot(
                    tenant_id,
                    job.property_id,
                    job.field_id,
                    job.field_boundary_version,
                    job.field_boundary_checksum,
                )
                if job.field_id is not None
                and job.field_boundary_version is not None
                and job.field_boundary_checksum is not None
                else None
            )
        if job.field_id is not None and field is None:
            raise ValueError("field boundary snapshot provenance is invalid")
        if (
            baseline is None
            or target is None
            or not baseline.output_reference
            or not target.output_reference
        ):
            raise LookupError("temporal delta inputs are unavailable in tenant")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.mark_job(
                tenant_id,
                job.id,
                ProcessingJobStatus.RUNNING,
                actor=actor,
                worker_id=worker_id,
            )
        try:
            output = TemporalDeltaProcessor(self.object_storage).process(
                baseline.output_reference,
                target.output_reference,
                f"tenants/{tenant_id}/derived/{job.id}/ndvi-delta.tif",
                field.geometry_geojson if field is not None else None,
                field.geometry_crs if field is not None else "EPSG:4326",
            )
        except (RasterProcessingError, ObjectStorageError, OSError, ValueError) as exc:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                failed = self.repository.mark_job(
                    tenant_id,
                    job.id,
                    ProcessingJobStatus.FAILED,
                    failure_reason=type(exc).__name__,
                    failure_code=type(exc).__name__,
                    actor=actor,
                    worker_id=worker_id,
                )
            return NdviResult(failed, None, [])
        product = DerivedProduct(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=job.property_id,
            scene_id=baseline.scene_id,
            processing_job_id=job.id,
            product_type="NDVI_DELTA",
            classification=DataClassification.DERIVED,
            statistics=output.statistics,
            output_reference=output.output_reference,
            output_checksum=output.output_checksum,
            algorithm_id=TemporalDeltaProcessor.algorithm_id,
            algorithm_version=TemporalDeltaProcessor.algorithm_version,
            formula=TemporalDeltaProcessor.formula,
            input_asset_keys=[],
            parameters={
                **job.parameters,
                "alignment": output.alignment,
                "quality_mask_policies": [
                    baseline.parameters.get("quality_mask"),
                    target.parameters.get("quality_mask"),
                ],
            },
            limitations=[
                "Delta is only the target NDVI minus baseline NDVI for pixels valid in both quality-masked products",
                "Delta does not identify a cause, diagnosis, gain, loss, or field condition",
            ],
            quality=[],
            field_id=job.field_id,
            field_boundary_version=job.field_boundary_version,
            field_boundary_checksum=job.field_boundary_checksum,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.repository.create_derived_product(product)
            self.repository.create_product_dependency(
                DerivedProductDependency(
                    tenant_id, product.id, baseline.id, "BASELINE_NDVI"
                )
            )
            self.repository.create_product_dependency(
                DerivedProductDependency(
                    tenant_id, product.id, target.id, "TARGET_NDVI"
                )
            )
            completed = self.repository.mark_job(
                tenant_id,
                job.id,
                ProcessingJobStatus.SUCCEEDED,
                output_product_id=product.id,
                actor=actor,
                worker_id=worker_id,
            )
            source = self._source(tenant_id)
            evidence = Evidence(
                id=new_id(),
                tenant_id=tenant_id,
                evidence_type="DERIVED_PRODUCT",
                reference_id=product.id,
                classification=DataClassification.DERIVED,
                source_id=source.id,
                observed_at=None,
                transformation=f"{TemporalDeltaProcessor.algorithm_id} {TemporalDeltaProcessor.algorithm_version}: {TemporalDeltaProcessor.formula}",
                limitations=product.limitations,
            )
            self.repository.create_evidence(evidence)
            self.store.audit(
                tenant_id,
                actor,
                "TEMPORAL_DELTA_JOB_COMPLETED",
                "derived_product",
                product.id,
                {
                    "baseline_product_id": baseline.id,
                    "target_product_id": target.id,
                    "output_checksum": product.output_checksum,
                },
                new_id(),
                now_utc(),
            )
        return NdviResult(completed, product, [evidence.id])

    def get_search(self, tenant_id: str, search_id: str) -> SatelliteSearch | None:
        with self.store.tenant_transaction(tenant_id):
            return self.repository.get_search(tenant_id, search_id)

    def list_scenes(self, tenant_id: str, property_id: str) -> list[SatelliteScene]:
        with self.store.tenant_transaction(tenant_id):
            return self.repository.list_scenes(tenant_id, property_id)

    def list_assets(self, tenant_id: str, scene_id: str) -> list[SatelliteAsset]:
        with self.store.tenant_transaction(tenant_id):
            return self.repository.list_assets(tenant_id, scene_id)

    def get_job(self, tenant_id: str, job_id: str) -> ProcessingJob | None:
        with self.store.tenant_transaction(tenant_id):
            return self.repository.get_job(tenant_id, job_id)

    def get_product(self, tenant_id: str, product_id: str) -> DerivedProduct | None:
        with self.store.tenant_transaction(tenant_id):
            return self.repository.get_derived_product(tenant_id, product_id)

    def list_products(self, tenant_id: str, property_id: str) -> list[DerivedProduct]:
        with self.store.tenant_transaction(tenant_id):
            return self.repository.list_derived_products(tenant_id, property_id)

    def timeline(self, tenant_id: str, property_id: str) -> list[dict[str, Any]]:
        with self.store.tenant_transaction(tenant_id):
            return self.repository.list_timeline(tenant_id, property_id)

    def compare_products(
        self,
        tenant_id: str,
        property_id: str,
        baseline_product_id: str,
        target_product_id: str,
        field_id: str | None = None,
    ) -> dict[str, Any]:
        """Compare persisted NDVI products without causal inference.

        A persisted delta product is returned only when its quality-mask and
        alignment provenance prove a pixel-aligned comparison.  Otherwise the
        legacy aggregate comparison remains explicitly non-pixel-comparable.
        """
        with self.store.tenant_transaction(tenant_id):
            baseline = self.repository.get_derived_product(
                tenant_id, baseline_product_id
            )
            target = self.repository.get_derived_product(tenant_id, target_product_id)
            if baseline is None or target is None:
                raise LookupError("derived product not found in tenant")
            if baseline.property_id != property_id or target.property_id != property_id:
                raise ValueError("both products must belong to the requested property")
            if baseline.product_type not in {
                "NDVI",
                "NDVI_QUALITY_MASKED",
            } or target.product_type not in {"NDVI", "NDVI_QUALITY_MASKED"}:
                raise ValueError("temporal comparison supports NDVI products only")
            baseline_job = self.repository.get_job(
                tenant_id, baseline.processing_job_id
            )
            target_job = self.repository.get_job(tenant_id, target.processing_job_id)
            field = self.fields.get(tenant_id, field_id) if field_id else None
        if field_id is not None and field is None:
            raise LookupError("field context not found in tenant")
        if field is not None and field.property_id != property_id:
            raise ValueError("field context must belong to the requested property")

        delta = None
        with self.store.tenant_transaction(tenant_id):
            delta = self.repository.find_temporal_delta(
                tenant_id, baseline.id, target.id, field_id
            )
        valid_field_scope = delta is not None and (
            field is None
            and delta.field_id is None
            or field is not None
            and self._has_valid_field_delta_provenance(delta, field)
        )
        if (
            delta is not None
            and valid_field_scope
            and self._has_valid_temporal_delta_provenance(delta, baseline, target)
        ):
            return {
                "status": "READY",
                "baseline": baseline,
                "target": target,
                "delta": delta,
                "delta_mean": delta.statistics.mean,
                "comparable_valid_pixels": delta.statistics.valid_count,
                "comparable_coverage_percentage": delta.statistics.coverage_percentage,
                "limitations": delta.limitations,
            }
        limitations = [
            "Aggregate mean difference is not a pixel-aligned delta raster",
            "Temporal change does not identify a cause, diagnosis, or field condition",
        ]
        if baseline_product_id == target_product_id:
            return {
                "status": "DADO_INSUFICIENTE",
                "baseline": baseline,
                "target": target,
                "delta_mean": None,
                "comparable_valid_pixels": None,
                "comparable_coverage_percentage": None,
                "limitations": limitations
                + ["Baseline and target must be different derived products"],
            }
        baseline_mean = baseline.statistics.mean
        target_mean = target.statistics.mean
        usable = (
            baseline.output_reference
            and target.output_reference
            and baseline_job is not None
            and target_job is not None
            and baseline_job.status == ProcessingJobStatus.SUCCEEDED
            and target_job.status == ProcessingJobStatus.SUCCEEDED
            and baseline_mean is not None
            and target_mean is not None
            and baseline.statistics.valid_count > 0
            and target.statistics.valid_count > 0
        )
        if not usable or baseline_mean is None or target_mean is None:
            return {
                "status": "DADO_INSUFICIENTE",
                "baseline": baseline,
                "target": target,
                "delta_mean": None,
                "comparable_valid_pixels": None,
                "comparable_coverage_percentage": None,
                "limitations": limitations
                + [
                    "Both persisted NDVI products require successful processing and valid means"
                ],
            }
        return {
            "status": "READY",
            "baseline": baseline,
            "target": target,
            "delta_mean": target_mean - baseline_mean,
            "comparable_valid_pixels": None,
            "comparable_coverage_percentage": None,
            "limitations": limitations,
        }

    def provenance(self, tenant_id: str, product_id: str) -> dict[str, Any] | None:
        """Return the persisted chain; HTTP presentation removes storage references."""
        with self.store.tenant_transaction(tenant_id):
            product = self.repository.get_derived_product(tenant_id, product_id)
            if product is None:
                return None
            job = self.repository.get_job(tenant_id, product.processing_job_id)
            scene = self.repository.get_scene(tenant_id, product.scene_id)
            assets = (
                self.repository.list_assets(tenant_id, scene.id)
                if scene is not None
                else []
            )
            evidence = self.store.evidence_for_reference(tenant_id, product.id)
            scene_evidence = self.store.evidence_for_reference(
                tenant_id, product.scene_id
            )
            dependencies = self.repository.list_product_dependencies(
                tenant_id, product.id
            )
            upstreams = []
            for dependency in dependencies:
                upstream = self.repository.get_derived_product(
                    tenant_id, dependency.upstream_product_id
                )
                if upstream is None:
                    continue
                upstream_scene = self.repository.get_scene(tenant_id, upstream.scene_id)
                upstream_assets = self.repository.list_assets(
                    tenant_id, upstream.scene_id
                )
                upstreams.append(
                    {
                        "relationship": dependency.relationship,
                        "product": upstream,
                        "scene": upstream_scene,
                        "assets": [
                            asset
                            for asset in upstream_assets
                            if asset.asset_key in upstream.input_asset_keys
                        ],
                        "evidence": self.store.evidence_for_reference(
                            tenant_id, upstream.id
                        ),
                    }
                )
        return {
            "product": product,
            "processing_job": job,
            "scene": scene,
            "assets": [
                asset for asset in assets if asset.asset_key in product.input_asset_keys
            ],
            "evidence": [
                item for item in (evidence, scene_evidence) if item is not None
            ],
            "upstreams": upstreams,
        }
