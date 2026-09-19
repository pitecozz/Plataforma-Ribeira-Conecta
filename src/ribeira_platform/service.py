from __future__ import annotations

from dataclasses import dataclass
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
from .models import (
    FetchResult,
    Property,
    RuleDefinition,
    Source,
    Tenant,
    new_id,
    now_utc,
)
from .sources import HttpJsonSourceAdapter, SourceAdapter
from .object_storage import LocalObjectStorage
from .storage import SQLiteStore
from .time_utils import parse_aware


@dataclass
class IngestionOutcome:
    fetch: FetchResult
    observation_ids: list[str]
    evidence_ids: list[str]


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
        self.business = BusinessApplication(self.store)
        registry = default_copernicus_registry()
        self.geospatial_provider = geospatial_provider or CopernicusStacAdapter(
            registry
        )
        self.geospatial = GeospatialApplication(
            self.store, self.geospatial_provider, object_storage or LocalObjectStorage()
        )

    def create_tenant(self, name: str) -> Tenant:
        tenant = Tenant(new_id(), name)
        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.create_tenant(tenant)
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
    ) -> Property:
        checksum = None
        if geometry_geojson is not None:
            _, _, checksum = validate_boundary(geometry_geojson, geometry_crs or "")
        property = Property(
            new_id(),
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
        return item

    def create_rule(self, rule: RuleDefinition) -> RuleDefinition:
        parse_aware(rule.valid_from)
        if rule.valid_until is not None:
            parse_aware(rule.valid_until)
        if rule.status == "ACTIVE" and not rule.approved_by:
            raise ValueError("active rule requires approved_by")
        with self.store.tenant_transaction(rule.tenant_id, platform_admin=False):
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
