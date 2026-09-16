from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .engine import DecisionEngine, EvidenceEngine
from .epistemology import DataClassification, IngestionStatus
from .models import FetchResult, Property, RuleDefinition, Source, Tenant, new_id, now_utc
from .sources import HttpJsonSourceAdapter, SourceAdapter
from .storage import SQLiteStore


@dataclass
class IngestionOutcome:
    fetch: FetchResult
    observation_ids: list[str]
    evidence_ids: list[str]


class RibeiraApplication:
    def __init__(self, store: SQLiteStore | None = None, adapters: dict[str, SourceAdapter] | None = None) -> None:
        self.store = store or SQLiteStore()
        self.adapters = adapters or {}
        self.default_adapter = HttpJsonSourceAdapter()
        self.decisions = DecisionEngine(self.store)
        self.evidence = EvidenceEngine(self.store)

    def create_tenant(self, name: str) -> Tenant:
        tenant = Tenant(new_id(), name)
        self.store.create_tenant(tenant)
        return tenant

    def create_property(self, tenant_id: str, name: str, geometry_geojson: dict[str, Any] | None = None, geometry_crs: str | None = None) -> Property:
        property = Property(new_id(), tenant_id, name, geometry_geojson, geometry_crs)
        self.store.create_property(property)
        self.store.audit(tenant_id, "user", "PROPERTY_CREATED", "property", property.id, {"classification": property.classification.value}, new_id(), now_utc())
        return property

    def create_source(self, tenant_id: str, name: str, source_type: str, provider: str, endpoint: str | None = None, source_version: str | None = None) -> Source:
        source = Source(new_id(), tenant_id, name, source_type, provider, endpoint, source_version)
        self.store.create_source(source)
        return source

    def create_rule(self, rule: RuleDefinition) -> RuleDefinition:
        if rule.status == "ACTIVE" and not rule.approved_by:
            raise ValueError("active rule requires approved_by")
        self.store.create_rule(rule)
        self.store.audit(rule.tenant_id, rule.approved_by or "user", "RULE_VERSION_CREATED", "rule", rule.id, {
            "version": rule.version, "status": rule.status, "authority": rule.authority.value,
        }, new_id(), now_utc())
        return rule

    def ingest(self, tenant_id: str, property_id: str, source_id: str, actor: str = "system") -> IngestionOutcome:
        property = self.store.get_property(tenant_id, property_id)
        source = self.store.get_source(tenant_id, source_id)
        if property is None or source is None:
            raise LookupError("property or source not found in tenant")
        adapter = self.adapters.get(source_id, self.default_adapter)
        fetch = adapter.fetch_property_observations(tenant_id, property, source)
        observation_ids: list[str] = []
        evidence_ids: list[str] = []
        for observation in fetch.observations:
            persisted = self.store.create_observation(observation)
            observation_ids.append(persisted.id)
            evidence_ids.append(self.evidence.evidence_for_observation(persisted).id)
        if fetch.status != IngestionStatus.INGESTED:
            event_type = "SOURCE_UNAVAILABLE" if fetch.status == IngestionStatus.SOURCE_UNAVAILABLE else "INVALID_SOURCE_PAYLOAD"
            self.store.create_quality_event(tenant_id, property_id, source_id, event_type, {"message": fetch.message}, new_id(), now_utc())
        self.store.audit(tenant_id, actor, "INGESTION_COMPLETED", "source", source_id, {
            "property_id": property_id, "status": fetch.status.value, "observation_ids": observation_ids,
            "evidence_ids": evidence_ids, "source_classification": fetch.source_classification.value,
        }, new_id(), now_utc())
        return IngestionOutcome(fetch, observation_ids, evidence_ids)

    def evaluate(self, tenant_id: str, property_id: str, actor: str = "system"):
        property = self.store.get_property(tenant_id, property_id)
        if property is None:
            raise LookupError("property not found in tenant")
        return self.decisions.evaluate(tenant_id, property, actor)

