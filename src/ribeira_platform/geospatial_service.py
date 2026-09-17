from __future__ import annotations

import os
from decimal import Decimal
from dataclasses import replace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .epistemology import DataClassification
from .geospatial import (
    BandResolver,
    DerivedProduct,
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
    algorithm_parameters,
)
from .time_utils import parse_aware


class AssetAccessFailure(RuntimeError):
    def __init__(self, status: AssetAccessStatus, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class GeospatialApplication:
    """Application service for the auditable CDSE discovery and NDVI slice."""

    provider_id = "COPERNICUS_CDSE"

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

        required = {roles["red"], roles["nir"]}
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
        job = ProcessingJob(
            id=new_id(),
            tenant_id=tenant_id,
            property_id=property_id,
            scene_id=search.selected_scene_id,
            job_type="NDVI",
            algorithm_id=NdviProcessor.algorithm_id,
            algorithm_version=NdviProcessor.algorithm_version,
            parameters=parameters,
            status=ProcessingJobStatus.PENDING,
            idempotency_key=key,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            persisted = self.repository.create_job(job)
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
            self.repository.mark_job(tenant_id, job.id, ProcessingJobStatus.RUNNING)
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
                    ProcessingJobStatus.FAILED,
                    exc.status.value,
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
                    tenant_id, job.id, ProcessingJobStatus.FAILED, str(exc)
                )
                self.store.create_quality_event(
                    tenant_id,
                    job.property_id,
                    None,
                    exc.quality.value,
                    {"job_id": job.id, "message": str(exc)},
                    new_id(),
                    now_utc(),
                )
                self.store.audit(
                    tenant_id,
                    actor,
                    "NDVI_JOB_FAILED",
                    "processing_job",
                    job.id,
                    {"quality": exc.quality.value, "message": str(exc)},
                    new_id(),
                    now_utc(),
                )
            return NdviResult(failed, None, [])
        except RuntimeError as exc:
            with self.store.tenant_transaction(tenant_id, platform_admin):
                failed = self.repository.mark_job(
                    tenant_id, job.id, ProcessingJobStatus.FAILED, str(exc)
                )
                self.store.create_quality_event(
                    tenant_id,
                    job.property_id,
                    None,
                    GeospatialQuality.ASSET_UNAVAILABLE.value,
                    {"job_id": job.id, "message": str(exc)},
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
        }
