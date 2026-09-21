from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from .epistemology import (
    DataClassification,
    DecisionStatus,
    IngestionStatus,
    QualityFlag,
    RuleAuthority,
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str
    created_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class Property:
    id: str
    tenant_id: str
    name: str
    geometry_geojson: dict[str, Any] | None = None
    geometry_crs: str | None = None
    classification: DataClassification = DataClassification.MANUAL_CONFIRMED
    created_at: str = field(default_factory=now_utc)
    boundary_source: str | None = None
    boundary_checksum: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class BoundaryImport:
    id: str
    tenant_id: str
    property_id: str
    original_filename: str
    original_format: str
    file_size_bytes: int
    file_sha256: str
    object_reference: str
    original_crs: str | None
    detected_crs: str | None
    target_crs: str | None
    geometry_geojson: dict[str, Any] | None
    geometry_checksum: str | None
    boundary_source: str
    classification: DataClassification
    warnings: list[str]
    status: str
    created_by: str
    expected_property_checksum: str | None
    created_at: str
    reviewed_by: str | None = None
    review_reason: str | None = None
    approved_boundary_version: int | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True)
class Source:
    id: str
    tenant_id: str
    name: str
    source_type: str
    provider: str
    endpoint: str | None = None
    source_version: str | None = None
    status: str = "CONFIGURED"
    created_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class Observation:
    id: str
    tenant_id: str
    property_id: str
    source_id: str
    metric: str
    value: float | None
    unit: str | None
    observation_timestamp: str
    ingestion_timestamp: str = field(default_factory=now_utc)
    processing_timestamp: str = field(default_factory=now_utc)
    original_observation_timestamp: str | None = None
    idempotency_key: str | None = None
    classification: DataClassification = DataClassification.OBSERVED
    quality_flag: QualityFlag = QualityFlag.VALID
    raw_data_reference: str | None = None
    dataset_version: str | None = None
    spatial_resolution: str | None = None
    temporal_resolution: str | None = None
    crs: str | None = None
    checksum: str | None = None


@dataclass(frozen=True)
class Evidence:
    id: str
    tenant_id: str
    evidence_type: str
    reference_id: str
    classification: DataClassification
    source_id: str | None
    observed_at: str | None
    transformation: str | None = None
    limitations: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    tenant_id: str
    version: int
    name: str
    authority: RuleAuthority
    metric: str
    operator: str
    threshold: float
    unit: str
    severity: str
    status: str
    approved_by: str | None
    valid_from: str
    valid_until: str | None = None
    created_at: str = field(default_factory=now_utc)
    scope_type: str = "TENANT"
    scope_property_id: str | None = None


@dataclass(frozen=True)
class Action:
    id: str
    tenant_id: str
    action_type: str
    status: str
    responsible_user_id: str | None
    deadline: str | None
    decision_id: str
    created_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class Alert:
    id: str
    tenant_id: str
    property_id: str
    alert_type: str
    severity: str
    status: str
    title: str
    decision_id: str
    created_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class Decision:
    id: str
    tenant_id: str
    property_id: str
    conclusion: str
    classification: DataClassification
    status: DecisionStatus
    evidence_ids: list[str]
    rule_id: str | None
    rule_version: int | None
    model_id: str | None
    model_version: str | None
    confidence: float | None
    limitations: list[str]
    missing_data: list[str]
    conflicts: list[dict[str, Any]]
    recommended_action: dict[str, Any] | None
    created_at: str = field(default_factory=now_utc)


@dataclass(frozen=True)
class FetchResult:
    status: IngestionStatus
    observations: list[Observation]
    message: str
    source_classification: DataClassification = DataClassification.UNKNOWN


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    alert: Alert | None
    action: Action | None


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value
