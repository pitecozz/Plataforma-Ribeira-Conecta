from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Any

from .engine import DecisionEngine, EvidenceEngine
from .business_service import BusinessApplication
from .boundaries import validate_boundary
from .epistemology import IngestionStatus
from .epistemology import DataClassification
from .geospatial_provider import CopernicusStacAdapter, default_copernicus_registry
from .geospatial_service import GeospatialApplication
from .property_refresh import PropertyRefreshService
from .models import (
    BoundaryImport,
    DecisionResult,
    FetchResult,
    Property,
    PilotFeedback,
    RuleDefinition,
    Source,
    Tenant,
    new_id,
    now_utc,
)
from .boundary_imports import (
    MAX_BOUNDARY_IMPORT_BYTES,
    boundary_import_format,
    parse_boundary_import,
    validate_import_filename,
)
from .field_context import FieldContextApplication
from .sources import HttpJsonSourceAdapter, SourceAdapter
from .object_storage import LocalObjectStorage
from .iam import AuthorizationError
from .storage import SQLiteStore
from .postgres import PostgresStore
from .time_utils import parse_aware


@dataclass
class IngestionOutcome:
    fetch: FetchResult
    observation_ids: list[str]
    evidence_ids: list[str]


class BoundaryImportConflict(ValueError):
    """A reviewed boundary can no longer be applied without a fresh review."""


class RibeiraApplication:
    def __init__(
        self,
        store: SQLiteStore | None = None,
        adapters: dict[str, SourceAdapter] | None = None,
        geospatial_provider: Any | None = None,
        object_storage: LocalObjectStorage | None = None,
    ) -> None:
        self.store = store or SQLiteStore()
        self.adapters = adapters or {}
        self.default_adapter = HttpJsonSourceAdapter()
        self.decisions = DecisionEngine(self.store)
        self.evidence = EvidenceEngine(self.store)
        self.fields = FieldContextApplication(self.store)
        self.business = BusinessApplication(self.store)
        registry = default_copernicus_registry()
        self.geospatial_provider = geospatial_provider or CopernicusStacAdapter(
            registry
        )
        self.object_storage = object_storage or LocalObjectStorage()
        self.geospatial = GeospatialApplication(
            self.store, self.geospatial_provider, self.object_storage
        )
        self.property_refresh = PropertyRefreshService(self)

    def evaluate_temporal_delta(
        self,
        tenant_id: str,
        property_id: str,
        product_id: str,
        actor: str = "system",
        platform_admin: bool = False,
    ) -> DecisionResult:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            property_item = self.store.get_property(tenant_id, property_id)
            if property_item is None:
                raise LookupError("property not found in tenant")
            product = self.geospatial.repository.get_derived_product(
                tenant_id, product_id
            )
            if product is None:
                raise LookupError("derived product not found in tenant")
            if product.property_id != property_id:
                raise ValueError("derived product does not belong to property")
            if product.product_type != "NDVI_DELTA":
                raise ValueError("derived product must be NDVI_DELTA")
            dependencies = self.geospatial.repository.list_product_dependencies(
                tenant_id, product.id
            )
            dependency_ids = {
                dependency.relationship: dependency.upstream_product_id
                for dependency in dependencies
            }
            baseline = self.geospatial.repository.get_derived_product(
                tenant_id, dependency_ids.get("BASELINE_NDVI", "")
            )
            target = self.geospatial.repository.get_derived_product(
                tenant_id, dependency_ids.get("TARGET_NDVI", "")
            )
            provenance_valid = (
                baseline is not None
                and target is not None
                and baseline.property_id == property_id
                and target.property_id == property_id
                and self.geospatial._has_valid_temporal_delta_provenance(
                    product, baseline, target
                )
            )
            evidence = self.store.evidence_for_reference(tenant_id, product.id)
            provenance_valid = (
                provenance_valid
                and evidence is not None
                and evidence.evidence_type == "DERIVED_PRODUCT"
                and evidence.classification == DataClassification.DERIVED
            )
            return self.decisions.evaluate_temporal_delta(
                tenant_id,
                property_item,
                product.id,
                float(product.statistics.mean)
                if product.statistics.mean is not None
                else None,
                evidence.id if evidence is not None else None,
                provenance_valid,
                actor,
            )

    def create_tenant(
        self, name: str, *, tenant_id: str | None = None, actor: str = "system"
    ) -> Tenant:
        tenant = Tenant(tenant_id or new_id(), name)
        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.create_tenant(tenant)
            self.store.audit(
                tenant.id,
                actor,
                "TENANT_CREATED",
                "tenant",
                tenant.id,
                {},
                new_id(),
                now_utc(),
            )
        return tenant

    def create_property(
        self,
        tenant_id: str,
        name: str,
        geometry_geojson: dict[str, Any] | None = None,
        geometry_crs: str | None = None,
        platform_admin: bool = False,
        boundary_source: str | None = None,
        classification: DataClassification = DataClassification.MANUAL_CONFIRMED,
        actor: str = "user",
        property_id: str | None = None,
    ) -> Property:
        checksum = None
        if geometry_geojson is not None:
            _, _, checksum = validate_boundary(geometry_geojson, geometry_crs or "")
        property = Property(
            property_id or new_id(),
            tenant_id,
            name,
            geometry_geojson,
            geometry_crs,
            classification,
            boundary_source=boundary_source,
            boundary_checksum=checksum,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.store.create_property(property, actor=actor)
            self.store.audit(
                tenant_id,
                actor,
                "PROPERTY_CREATED",
                "property",
                property.id,
                {"classification": property.classification.value},
                new_id(),
                now_utc(),
            )
        # A persisted approved AOI begins unattended context discovery.  This
        # deliberately enqueues work; it never performs provider I/O in the
        # property creation request or mutates the imported boundary.
        if property.geometry_geojson is not None:
            self.property_refresh.register_property(
                tenant_id, property.id, actor=actor, platform_admin=platform_admin
            )
        return property

    def create_source(
        self,
        tenant_id: str,
        name: str,
        source_type: str,
        provider: str,
        endpoint: str | None = None,
        source_version: str | None = None,
        platform_admin: bool = False,
    ) -> Source:
        source = Source(
            new_id(), tenant_id, name, source_type, provider, endpoint, source_version
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.store.create_source(source)
        return source

    def update_property_boundary(
        self,
        tenant_id: str,
        property_id: str,
        geometry: dict[str, Any],
        crs: str,
        source: str,
        classification: DataClassification,
        reason: str,
        actor: str,
        expected_checksum: str | None,
        platform_admin: bool = False,
    ) -> Property:
        _, _, checksum = validate_boundary(geometry, crs)
        with self.store.tenant_transaction(tenant_id, platform_admin):
            current = self.store.get_property(tenant_id, property_id)
            if current is None:
                raise LookupError("property not found in tenant")
            item = Property(
                property_id,
                tenant_id,
                current.name,
                geometry,
                crs,
                classification,
                current.created_at,
                source,
                checksum,
                now_utc(),
            )
            if not hasattr(self.store, "update_property_boundary"):
                raise RuntimeError("boundary versioning requires PostgreSQL")
            self.store.update_property_boundary(
                item,
                actor=actor,
                reason=reason,
                effective_at=item.updated_at or now_utc(),
                expected_checksum=expected_checksum,
            )
            self.store.audit(
                tenant_id,
                actor,
                "BOUNDARY_CHANGED",
                "property",
                property_id,
                {
                    "previous_checksum": current.boundary_checksum,
                    "checksum": checksum,
                    "reason": reason,
                    "classification": classification.value,
                },
                new_id(),
                now_utc(),
            )
        # A boundary change is a new approved AOI version, not a provider
        # mutation. Ensure its automatic context policy exists; the stable
        # initial run remains idempotent across approval retries.
        self.property_refresh.register_property(
            tenant_id, property_id, actor=actor, platform_admin=platform_admin
        )
        return item

    def create_boundary_import(
        self,
        tenant_id: str,
        property_id: str,
        *,
        original_filename: str,
        payload: bytes,
        declared_crs: str | None,
        boundary_source: str,
        classification: DataClassification,
        actor: str,
        platform_admin: bool = False,
    ) -> BoundaryImport:
        """Persist original boundary evidence without changing the property.

        The API has already streamed the body through its size limiter.  The
        second guard makes this service safe for non-HTTP callers as well.
        """
        if len(payload) > MAX_BOUNDARY_IMPORT_BYTES:
            raise ValueError("boundary import exceeds the configured size limit")
        filename = validate_import_filename(original_filename)
        original_format = boundary_import_format(filename)
        if not boundary_source.strip():
            raise ValueError("boundary_source is required")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            property_item = self.store.get_property(tenant_id, property_id)
            if property_item is None:
                raise LookupError("property not found in tenant")

        parsed = parse_boundary_import(payload, declared_crs, original_format)
        import_id = new_id()
        # The client filename never becomes a filesystem path.  The opaque key
        # is deliberately segregated from COGs, products and backup archives.
        object_reference, stored_checksum = self.object_storage.put_bytes(
            f"boundary-imports/{tenant_id}/{import_id}/original.{original_format.lower()}",
            payload,
            {
                "GEOJSON": "application/geo+json",
                "KML": "application/vnd.google-earth.kml+xml",
                "KMZ": "application/vnd.google-earth.kmz",
            }[original_format],
        )
        if stored_checksum != parsed.file_sha256:
            raise RuntimeError("stored boundary import checksum does not match input")
        warnings = list(parsed.warnings)
        if parsed.failure_code and parsed.failure_code not in warnings:
            warnings.append(parsed.failure_code)
        item = BoundaryImport(
            import_id,
            tenant_id,
            property_id,
            filename,
            original_format,
            len(payload),
            parsed.file_sha256,
            object_reference,
            parsed.original_crs,
            parsed.detected_crs,
            parsed.target_crs,
            parsed.geometry,
            parsed.geometry_checksum,
            boundary_source,
            classification,
            warnings,
            parsed.status,
            actor,
            property_item.boundary_checksum,
            now_utc(),
        )
        if not isinstance(self.store, PostgresStore):
            raise RuntimeError("boundary imports require PostgreSQL")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            # Re-read so an import cannot accidentally receive a stale
            # expected checksum while its file was being written.
            current = self.store.get_property(tenant_id, property_id)
            if current is None:
                raise LookupError("property not found in tenant")
            item = BoundaryImport(
                **{
                    **item.__dict__,
                    "expected_property_checksum": current.boundary_checksum,
                }
            )
            self.store.create_boundary_import(item)
            self.store.audit(
                tenant_id,
                actor,
                "BOUNDARY_IMPORT_CREATED",
                "boundary_import",
                item.id,
                {
                    "property_id": property_id,
                    "status": item.status,
                    "file_sha256": item.file_sha256,
                    "geometry_checksum": item.geometry_checksum,
                    "original_format": item.original_format,
                    "classification": classification.value,
                },
                new_id(),
                now_utc(),
            )
        return item

    def list_boundary_imports(
        self, tenant_id: str, property_id: str, *, platform_admin: bool = False
    ) -> list[BoundaryImport]:
        if not isinstance(self.store, PostgresStore):
            raise RuntimeError("boundary imports require PostgreSQL")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            if self.store.get_property(tenant_id, property_id) is None:
                raise LookupError("property not found in tenant")
            return self.store.list_boundary_imports(tenant_id, property_id)

    def get_boundary_import(
        self, tenant_id: str, import_id: str, *, platform_admin: bool = False
    ) -> BoundaryImport:
        if not isinstance(self.store, PostgresStore):
            raise RuntimeError("boundary imports require PostgreSQL")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            item = self.store.get_boundary_import(tenant_id, import_id)
            if item is None:
                raise LookupError("boundary import not found in tenant")
            return item

    def preview_boundary_import(
        self, tenant_id: str, import_id: str, *, platform_admin: bool = False
    ) -> dict[str, Any]:
        if not isinstance(self.store, PostgresStore):
            raise RuntimeError("boundary imports require PostgreSQL")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            item = self.store.get_boundary_import(tenant_id, import_id)
            if item is None:
                raise LookupError("boundary import not found in tenant")
            property_item = self.store.get_property(tenant_id, item.property_id)
            if property_item is None:
                raise LookupError("property not found in tenant")
            current_area = (
                Decimal(
                    validate_boundary(
                        property_item.geometry_geojson, property_item.geometry_crs or ""
                    )[1]
                )
                if property_item.geometry_geojson is not None
                else None
            )
            imported_area = (
                Decimal(
                    validate_boundary(item.geometry_geojson, item.target_crs or "")[1]
                )
                if item.geometry_geojson is not None and item.target_crs
                else None
            )
            absolute_delta = (
                abs(imported_area - current_area)
                if current_area is not None and imported_area is not None
                else None
            )
            percentage_delta = (
                (absolute_delta / current_area * 100)
                if absolute_delta is not None and current_area and current_area > 0
                else None
            )
            return {
                "import": item,
                "current_boundary_checksum": property_item.boundary_checksum,
                "current_area_hectares": str(current_area)
                if current_area is not None
                else None,
                "imported_area_hectares": str(imported_area)
                if imported_area is not None
                else None,
                "absolute_area_delta_hectares": str(absolute_delta)
                if absolute_delta is not None
                else None,
                "percentage_area_delta": str(percentage_delta)
                if percentage_delta is not None
                else None,
                "current_geometry": property_item.geometry_geojson,
                "imported_geometry": item.geometry_geojson,
            }

    def approve_boundary_import(
        self,
        tenant_id: str,
        import_id: str,
        *,
        reviewer: str,
        reason: str,
        expected_property_checksum: str,
        platform_admin: bool = False,
    ) -> BoundaryImport:
        if not reason.strip():
            raise ValueError("review_reason is required")
        if not isinstance(self.store, PostgresStore):
            raise RuntimeError("boundary imports require PostgreSQL")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            item = self.store.get_boundary_import(tenant_id, import_id, lock=True)
            if item is None:
                raise LookupError("boundary import not found in tenant")
            if item.status != "NEEDS_REVIEW":
                raise BoundaryImportConflict("boundary import is not awaiting review")
            if item.created_by == reviewer:
                raise AuthorizationError(
                    "boundary import requires a different reviewer"
                )
            if (
                item.geometry_geojson is None
                or item.geometry_checksum is None
                or item.target_crs != "EPSG:4326"
            ):
                raise BoundaryImportConflict(
                    "boundary import has unresolved CRS or geometry"
                )
            if item.expected_property_checksum != expected_property_checksum:
                raise BoundaryImportConflict(
                    "review request checksum does not match import"
                )
            current = self.store.get_property(tenant_id, item.property_id)
            if current is None:
                raise LookupError("property not found in tenant")
            if current.boundary_checksum != item.expected_property_checksum:
                raise BoundaryImportConflict(
                    "property boundary changed while import was under review"
                )
            # Existing boundary version locking/audit executes inside this same
            # tenant transaction; nested store transactions do not commit.
            updated = self.update_property_boundary(
                tenant_id,
                item.property_id,
                item.geometry_geojson,
                item.target_crs,
                item.boundary_source,
                item.classification,
                reason,
                reviewer,
                item.expected_property_checksum,
                platform_admin,
            )
            version = self.store.connection.execute(
                "SELECT max(version) AS version FROM property_boundary_version "
                "WHERE tenant_id=%s AND property_id=%s",
                (tenant_id, item.property_id),
            ).fetchone()
            if version is None or version["version"] is None:
                raise RuntimeError("approved boundary version was not persisted")
            self.store.review_boundary_import(
                item,
                status="APPROVED",
                reviewer=reviewer,
                reason=reason,
                approved_version=int(version["version"]),
            )
            self.store.audit(
                tenant_id,
                reviewer,
                "BOUNDARY_IMPORT_APPROVED",
                "boundary_import",
                item.id,
                {
                    "property_id": item.property_id,
                    "boundary_version": int(version["version"]),
                    "checksum": updated.boundary_checksum,
                },
                new_id(),
                now_utc(),
            )
            approved = self.store.get_boundary_import(tenant_id, item.id)
            if approved is None:
                raise RuntimeError("approved boundary import was not persisted")
            return approved

    def reject_boundary_import(
        self,
        tenant_id: str,
        import_id: str,
        *,
        reviewer: str,
        reason: str,
        platform_admin: bool = False,
    ) -> BoundaryImport:
        if not reason.strip():
            raise ValueError("review_reason is required")
        if not isinstance(self.store, PostgresStore):
            raise RuntimeError("boundary imports require PostgreSQL")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            item = self.store.get_boundary_import(tenant_id, import_id, lock=True)
            if item is None:
                raise LookupError("boundary import not found in tenant")
            if item.status != "NEEDS_REVIEW":
                raise BoundaryImportConflict("boundary import is not awaiting review")
            if item.created_by == reviewer:
                raise AuthorizationError(
                    "boundary import requires a different reviewer"
                )
            self.store.review_boundary_import(
                item, status="REJECTED", reviewer=reviewer, reason=reason
            )
            self.store.audit(
                tenant_id,
                reviewer,
                "BOUNDARY_IMPORT_REJECTED",
                "boundary_import",
                item.id,
                {"property_id": item.property_id},
                new_id(),
                now_utc(),
            )
            rejected = self.store.get_boundary_import(tenant_id, item.id)
            if rejected is None:
                raise RuntimeError("rejected boundary import was not persisted")
            return rejected

    def create_rule(self, rule: RuleDefinition) -> RuleDefinition:
        parse_aware(rule.valid_from)
        if rule.valid_until is not None:
            parse_aware(rule.valid_until)
        if rule.status == "ACTIVE" and not rule.approved_by:
            raise ValueError("active rule requires approved_by")
        if rule.scope_type not in {"TENANT", "PROPERTY", "ASSET", "FIELD", "CUSTOMER"}:
            raise ValueError(
                "rule scope_type must be TENANT, PROPERTY, ASSET, FIELD or CUSTOMER"
            )
        scope_is_valid = (
            (
                rule.scope_type == "TENANT"
                and rule.scope_property_id is None
                and rule.scope_asset_id is None
                and rule.scope_field_id is None
                and rule.scope_customer_id is None
            )
            or (
                rule.scope_type == "PROPERTY"
                and rule.scope_property_id is not None
                and rule.scope_asset_id is None
                and rule.scope_field_id is None
                and rule.scope_customer_id is None
            )
            or (
                rule.scope_type == "ASSET"
                and rule.scope_property_id is None
                and rule.scope_asset_id is not None
                and rule.scope_field_id is None
                and rule.scope_customer_id is None
            )
            or (
                rule.scope_type == "FIELD"
                and rule.scope_property_id is None
                and rule.scope_asset_id is None
                and rule.scope_field_id is not None
                and rule.scope_customer_id is None
            )
            or (
                rule.scope_type == "CUSTOMER"
                and rule.scope_property_id is None
                and rule.scope_asset_id is None
                and rule.scope_field_id is None
                and rule.scope_customer_id is not None
            )
        )
        if not scope_is_valid:
            raise ValueError("rule scope identifiers must match scope_type")
        with self.store.tenant_transaction(rule.tenant_id, platform_admin=False):
            if (
                rule.scope_property_id is not None
                and self.store.get_property(rule.tenant_id, rule.scope_property_id)
                is None
            ):
                raise LookupError("rule scope property is unavailable in tenant")
            if rule.scope_asset_id is not None:
                self.business.asset_for_rule_evaluation(
                    rule.tenant_id, rule.scope_asset_id
                )
            if rule.scope_field_id is not None:
                if (
                    self.fields.repository.get(rule.tenant_id, rule.scope_field_id)
                    is None
                ):
                    raise LookupError("rule scope field is unavailable in tenant")
            if (
                rule.scope_customer_id is not None
                and self.business.repository.get_customer(
                    rule.tenant_id, rule.scope_customer_id
                )
                is None
            ):
                raise LookupError("rule scope customer is unavailable in tenant")
            self.store.create_rule(rule)
            self.store.audit(
                rule.tenant_id,
                rule.approved_by or "user",
                "RULE_VERSION_CREATED",
                "rule",
                rule.id,
                {
                    "version": rule.version,
                    "status": rule.status,
                    "authority": rule.authority.value,
                    "scope_type": rule.scope_type,
                    "scope_property_id": rule.scope_property_id,
                    "scope_asset_id": rule.scope_asset_id,
                    "scope_field_id": rule.scope_field_id,
                    "scope_customer_id": rule.scope_customer_id,
                },
                new_id(),
                now_utc(),
            )
        return rule

    @staticmethod
    def _observation_idempotency_key(observation) -> str:
        payload = {
            "source_id": observation.source_id,
            "property_id": observation.property_id,
            "metric": observation.metric,
            "observation_timestamp": observation.observation_timestamp,
            "unit": observation.unit,
            "value": observation.value,
            "checksum": observation.checksum,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def ingest(
        self,
        tenant_id: str,
        property_id: str,
        source_id: str,
        actor: str = "system",
        platform_admin: bool = False,
    ) -> IngestionOutcome:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            return self._ingest_in_context(tenant_id, property_id, source_id, actor)

    def _ingest_in_context(
        self, tenant_id: str, property_id: str, source_id: str, actor: str
    ) -> IngestionOutcome:
        property = self.store.get_property(tenant_id, property_id)
        source = self.store.get_source(tenant_id, source_id)
        if property is None or source is None:
            raise LookupError("property or source not found in tenant")
        adapter = self.adapters.get(source_id, self.default_adapter)
        fetch = adapter.fetch_property_observations(tenant_id, property, source)
        observation_ids: list[str] = []
        evidence_ids: list[str] = []
        with self.store.transaction():
            for observation in fetch.observations:
                key = self._observation_idempotency_key(observation)
                existing = self.store.observation_by_idempotency(tenant_id, key)
                persisted = existing or self.store.create_observation(
                    observation.__class__(
                        **{**observation.__dict__, "idempotency_key": key}
                    )
                )
                observation_ids.append(persisted.id)
                evidence_ids.append(
                    self.evidence.evidence_for_observation(persisted).id
                )
            if fetch.status != IngestionStatus.INGESTED:
                self.store.create_quality_event(
                    tenant_id,
                    property_id,
                    source_id,
                    fetch.status.value,
                    {"message": fetch.message},
                    new_id(),
                    now_utc(),
                )
            self.store.audit(
                tenant_id,
                actor,
                "INGESTION_COMPLETED",
                "source",
                source_id,
                {
                    "property_id": property_id,
                    "status": fetch.status.value,
                    "observation_ids": observation_ids,
                    "evidence_ids": evidence_ids,
                    "source_classification": fetch.source_classification.value,
                },
                new_id(),
                now_utc(),
            )
        return IngestionOutcome(fetch, observation_ids, evidence_ids)

    def evaluate(
        self,
        tenant_id: str,
        property_id: str,
        actor: str = "system",
        platform_admin: bool = False,
    ):
        with self.store.tenant_transaction(tenant_id, platform_admin):
            return self._evaluate_in_context(tenant_id, property_id, actor)

    def _evaluate_in_context(
        self, tenant_id: str, property_id: str, actor: str = "system"
    ):
        property = self.store.get_property(tenant_id, property_id)
        if property is None:
            raise LookupError("property not found in tenant")
        with self.store.transaction():
            return self.decisions.evaluate(tenant_id, property, actor)

    def evaluate_asset(
        self,
        tenant_id: str,
        asset_id: str,
        actor: str = "system",
        platform_admin: bool = False,
    ):
        """Evaluate a rule selected for one property-linked Digital Twin asset.

        The current observations stay property-scoped.  The asset registration
        evidence makes the asset's applicability explicit and is never treated
        as an observed metric.
        """
        with self.store.tenant_transaction(tenant_id, platform_admin):
            asset = self.business.asset_for_rule_evaluation(tenant_id, asset_id)
            evidence = self.store.evidence_for_reference(tenant_id, asset.id)
            evidence_id = (
                evidence.id
                if evidence is not None
                and evidence.evidence_type == "ASSET_REGISTRATION"
                else None
            )
            # asset_for_rule_evaluation enforces this relation; retain the guard
            # here so the type contract remains explicit at the decision boundary.
            if asset.property_id is None:
                raise ValueError(
                    "asset rule evaluation requires an associated property"
                )
            property_item = self.store.get_property(tenant_id, asset.property_id)
            if property_item is None:
                raise LookupError("asset property is unavailable in tenant")
            with self.store.transaction():
                return self.decisions.evaluate(
                    tenant_id,
                    property_item,
                    actor,
                    asset_id=asset.id,
                    asset_evidence_id=evidence_id,
                )

    def decision_history_for_property(
        self,
        tenant_id: str,
        property_id: str,
        *,
        platform_admin: bool = False,
    ) -> list[dict[str, Any]]:
        with self.store.tenant_transaction(tenant_id, platform_admin):
            if self.store.get_property(tenant_id, property_id) is None:
                raise LookupError("property not found in tenant")
            return self.store.decision_history_for_property(tenant_id, property_id)

    def evaluate_field(
        self,
        tenant_id: str,
        field_id: str,
        actor: str = "system",
        platform_admin: bool = False,
    ):
        """Evaluate a rule selected for one source-backed non-legal field/talhao.

        The current observations remain property-scoped. Field registration is
        only applicability context and does not become crop, soil or agronomic
        evidence.
        """
        with self.store.tenant_transaction(tenant_id, platform_admin):
            field = self.fields.repository.get(tenant_id, field_id)
            if field is None:
                raise LookupError("field context not found in tenant")
            evidence = self.store.evidence_for_reference(tenant_id, field.id)
            evidence_id = (
                evidence.id
                if evidence is not None
                and evidence.evidence_type == "FIELD_REGISTRATION"
                else None
            )
            property_item = self.store.get_property(tenant_id, field.property_id)
            if property_item is None:
                raise LookupError("field property is unavailable in tenant")
            with self.store.transaction():
                return self.decisions.evaluate(
                    tenant_id,
                    property_item,
                    actor,
                    field_id=field.id,
                    field_evidence_id=evidence_id,
                )

    def complete_action(
        self,
        tenant_id: str,
        action_id: str,
        *,
        outcome_detail: str,
        outcome_classification: DataClassification,
        evidence_ids: list[str],
        actor: str,
        completed_at: str | None = None,
        platform_admin: bool = False,
    ) -> None:
        """Record a human-confirmed result for an actionable, property-scoped rule.

        Actions are created by decisions, and decisions are always scoped to a
        property.  Completing an action must therefore preserve the original
        decision and attach explicit outcome provenance instead of replacing a
        recommendation with an unsupported conclusion.
        """
        if not outcome_detail.strip():
            raise ValueError("action outcome detail is required")
        effective_completed_at = completed_at or now_utc()
        parse_aware(effective_completed_at)
        with self.store.tenant_transaction(tenant_id, platform_admin):
            self.store.complete_action(
                tenant_id,
                action_id,
                actor=actor,
                detail=outcome_detail,
                classification=outcome_classification.value,
                evidence_ids=evidence_ids,
                completed_at=effective_completed_at,
            )
            self.store.audit(
                tenant_id,
                actor,
                "ACTION_OUTCOME_RECORDED",
                "action",
                action_id,
                {
                    "classification": outcome_classification.value,
                    "evidence_ids": evidence_ids,
                    "completed_at": effective_completed_at,
                },
                new_id(),
                now_utc(),
            )

    def create_pilot_feedback(
        self,
        tenant_id: str,
        *,
        feedback_type: str,
        page: str,
        feature_id: str,
        message: str,
        submitted_by: str,
        property_id: str | None = None,
        platform_admin: bool = False,
    ) -> PilotFeedback:
        """Persist product feedback without fabricating an operational conclusion."""
        item = PilotFeedback(
            new_id(),
            tenant_id,
            submitted_by,
            feedback_type,
            page,
            feature_id,
            message,
            property_id,
        )
        with self.store.tenant_transaction(tenant_id, platform_admin):
            if property_id and self.store.get_property(tenant_id, property_id) is None:
                raise LookupError("feedback property is unavailable in tenant")
            self.store.create_pilot_feedback(item)
            self.store.audit(
                tenant_id,
                submitted_by,
                "PILOT_FEEDBACK_SUBMITTED",
                "pilot_feedback",
                item.id,
                {
                    "feedback_type": feedback_type,
                    "page": page,
                    "feature_id": feature_id,
                    "property_id": property_id,
                },
                new_id(),
                now_utc(),
            )
        return item

    def assess_flood_exposure(
        self,
        tenant_id: str,
        *,
        event_key: str,
        subject_type: str,
        subject_id: str,
        exposure_zone_id: str | None,
        actor: str,
        platform_admin: bool = False,
    ) -> dict[str, Any]:
        if not isinstance(self.store, PostgresStore):
            raise RuntimeError("flood exposure assessments require PostgreSQL/PostGIS")
        with self.store.tenant_transaction(tenant_id, platform_admin):
            assessment = self.store.assess_flood_exposure(
                tenant_id,
                event_key=event_key,
                subject_type=subject_type,
                subject_id=subject_id,
                exposure_zone_id=exposure_zone_id,
                actor=actor,
            )
            self.store.audit(
                tenant_id,
                actor,
                "FLOOD_EXPOSURE_ASSESSED",
                "flood_exposure_assessment",
                str(assessment["id"]),
                {
                    "event_key": event_key,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "status": assessment["status"],
                    "classification": assessment["classification"],
                },
                new_id(),
                now_utc(),
            )
            return assessment
