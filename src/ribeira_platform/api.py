from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pyproj import Geod
from shapely.geometry import shape

from .audit_context import request_context as audit_request_context
from .business import (
    Asset,
    AssetOwnership,
    CapitalBreakdown,
    CommercialClassification,
    ContractVersion,
    CustomerContract,
    InstallationProject,
    OpportunityClassification,
    OperationalCapacityPolicy,
    OwnershipKind,
    PricingPolicy,
    PricingPolicyVersion,
    Product,
    ProductStatus,
    RevenueTreatment,
    RevenueType,
    ServiceOffering,
    ServicePlan,
)
from .epistemology import DataClassification, RuleAuthority
from .geospatial import GeometryService, SceneSelectionPolicy, SatelliteSearchRequest
from .iam import (
    AuthContext,
    AuthenticationError,
    AuthorizationError,
    DevelopmentIdentityProvider,
    IdentityProvider,
    JwtIdentityProvider,
    AuthorizationPolicy,
)
from .identity_access import IdentityAccess
from .hydrology import ValeDoRibeiraSituationService
from .logging_config import configure_structured_logging
from .models import (
    BoundaryImport,
    Property,
    RuleDefinition,
    new_id,
    now_utc,
    to_jsonable,
)
from .object_storage import ObjectStorageError
from .postgres import PostgresStore
from .raster_tiles import InvalidTile, RasterUnavailable, render_ndvi_tile
from .service import BoundaryImportConflict, RibeiraApplication
from .storage import SQLiteStore


logger = logging.getLogger("ribeira.api")
REQUESTS = Counter(
    "ribeira_http_requests_total", "HTTP requests", ["method", "path", "status"]
)
LATENCY = Histogram(
    "ribeira_http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)
TILE_LATENCY = Histogram("ribeira_raster_tile_duration_seconds", "Raster tile latency")
TILE_FAILURES = Counter("ribeira_raster_tile_failures_total", "Raster tile failures")


@dataclass(frozen=True)
class Settings:
    env: str
    storage: str
    database_url: str | None
    cors_origins: tuple[str, ...]
    auth_mode: str
    max_body_bytes: int

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            item.strip()
            for item in os.getenv("RIBEIRA_CORS_ORIGINS", "").split(",")
            if item.strip()
        )
        settings = cls(
            os.getenv("RIBEIRA_ENV", "development"),
            os.getenv("RIBEIRA_STORAGE", "postgres"),
            os.getenv("RIBEIRA_DATABASE_URL"),
            origins,
            os.getenv("RIBEIRA_AUTH_MODE", "jwt"),
            int(os.getenv("RIBEIRA_MAX_BODY_BYTES", "1048576")),
        )
        if settings.env == "production" and settings.auth_mode != "oidc":
            raise ValueError("production requires RIBEIRA_AUTH_MODE=oidc")
        if settings.env == "production" and os.getenv("RIBEIRA_DEV_AUTH_TOKEN"):
            raise ValueError("production rejects RIBEIRA_DEV_AUTH_TOKEN")
        return settings


class TenantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class PropertyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    geometry_geojson: dict[str, Any] | None = None
    geometry_crs: str | None = Field(default=None, max_length=32)
    boundary_source: str | None = Field(default=None, min_length=1, max_length=500)
    classification: DataClassification = DataClassification.MANUAL_CONFIRMED


class BoundaryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    geometry_geojson: dict[str, Any]
    geometry_crs: str = Field(min_length=1, max_length=32)
    boundary_source: str = Field(min_length=1, max_length=500)
    classification: DataClassification
    reason: str = Field(min_length=1, max_length=500)
    expected_checksum: str = Field(min_length=64, max_length=64)


class BoundaryImportReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_reason: str = Field(min_length=1, max_length=500)
    expected_property_checksum: str | None = Field(
        default=None, min_length=64, max_length=64
    )


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    source_type: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=160)
    endpoint: str | None = Field(default=None, max_length=2048)
    source_version: str | None = Field(default=None, max_length=160)


class SatelliteSearchRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection_id: str = Field(default="sentinel-2-l2a", min_length=1, max_length=160)
    datetime_start: str
    datetime_end: str
    cloud_cover_limit: Decimal | None = Field(default=None, ge=0, le=100)
    max_candidates: int = Field(default=100, ge=1, le=100)
    policy_id: str = Field(
        default="SENTINEL2_L2A_LATEST_V1", min_length=1, max_length=120
    )
    policy_version: int = Field(default=1, ge=1)


class NdviJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_id: str


class ProductJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str


class TemporalDeltaJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_product_id: str
    target_product_id: str


class RuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    authority: RuleAuthority
    metric: str = Field(min_length=1, max_length=120)
    operator: str = Field(pattern=r"^(<|<=|>|>=|==)$")
    threshold: float
    unit: str = Field(min_length=1, max_length=32)
    severity: str = Field(min_length=1, max_length=32)
    status: str = Field(pattern=r"^(DRAFT|ACTIVE|RETIRED)$")
    approved_by: str | None = None
    valid_from: str = Field(default_factory=now_utc)
    valid_until: str | None = None
    scope_type: str = Field(default="TENANT", pattern=r"^(TENANT|PROPERTY)$")
    scope_property_id: str | None = Field(default=None, min_length=1, max_length=200)


class ActorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str | None = Field(default=None, max_length=200)


class ActionOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_detail: str = Field(min_length=1, max_length=4000)
    outcome_classification: DataClassification
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    completed_at: str | None = None


class PilotFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_type: str = Field(
        pattern=r"^(BUG|CONFUSING|INCORRECT_DATA|MISSING_FEATURE|SUGGESTION|USEFUL)$"
    )
    page: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_./:-]+$")
    feature_id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    message: str = Field(min_length=1, max_length=4000)
    property_id: str | None = Field(default=None, min_length=1, max_length=200)


class FloodExposureAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_key: str = Field(min_length=1, max_length=200)
    subject_type: str = Field(pattern=r"^(PROPERTY|ASSET)$")
    subject_id: str = Field(min_length=1, max_length=200)
    exposure_zone_id: str | None = Field(default=None, min_length=1, max_length=200)


class CustomerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=240)
    customer_type: str = Field(default="LEGAL_ENTITY", min_length=1, max_length=60)
    legal_name: str | None = Field(default=None, max_length=240)
    status: str = Field(default="ACTIVE", min_length=1, max_length=40)
    external_reference: str | None = Field(default=None, max_length=200)


class ContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str
    property_id: str | None = None
    contract_type: str = Field(min_length=1, max_length=60)
    counterparty_name: str | None = Field(default=None, max_length=240)
    external_provider_name: str | None = Field(default=None, max_length=240)
    revenue_treatment: RevenueTreatment
    status: str = Field(default="DRAFT", min_length=1, max_length=40)
    start_at: str
    end_at: str | None = None
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class ContractVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_id: str
    version: int = Field(ge=1)
    status: str = Field(default="DRAFT", pattern=r"^(DRAFT|ACTIVE|RETIRED)$")
    valid_from: str
    valid_until: str | None = None
    total_price: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    recurring: bool = False
    configuration: dict[str, Any] = Field(default_factory=dict)


class ProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    status: ProductStatus = ProductStatus.DRAFT
    sku: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class ServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    status: ProductStatus = ProductStatus.DRAFT
    recurring: bool = False
    revenue_type: RevenueType = RevenueType.ONE_TIME_SERVICE
    product_id: str | None = None
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class ServicePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: str
    name: str = Field(min_length=1, max_length=200)
    billing_period: str = Field(default="MONTH", min_length=1, max_length=30)
    monthly_price: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    status: str = Field(default="DRAFT", min_length=1, max_length=40)
    revenue_treatment: RevenueTreatment
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class AssetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    serial_number: str | None = Field(default=None, max_length=200)
    status: str = Field(default="ACTIVE", min_length=1, max_length=40)
    property_id: str | None = None
    site_id: str | None = None
    geometry: dict[str, Any] | None = None
    geometry_crs: str | None = Field(default=None, max_length=32)
    source_reference: str | None = Field(default=None, max_length=2000)
    observed_at: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class AssetOwnershipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ownership_kind: OwnershipKind
    customer_id: str | None = None
    purchased_by: str | None = None
    maintained_by: str | None = None
    replacement_responsibility: str | None = None
    risk_bearer: str | None = None
    valid_from: str
    valid_until: str | None = None
    acquisition_document: str | None = None
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class InstallationProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: str
    property_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    status: str = Field(default="DRAFT", min_length=1, max_length=40)
    technical_provider_type: str = Field(default="RIBEIRA", min_length=1, max_length=60)
    customer_total_project_cost: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    revenue_treatment: RevenueTreatment
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class PricingPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    scope: str = Field(default="TENANT", min_length=1, max_length=60)
    status: str = Field(default="DRAFT", min_length=1, max_length=40)


class PricingPolicyVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    status: str = Field(default="DRAFT", pattern=r"^(DRAFT|ACTIVE|RETIRED)$")
    lower_threshold: Decimal = Field(ge=0)
    lower_rate: Decimal = Field(ge=0)
    lower_minimum: Decimal = Field(ge=0)
    upper_rate: Decimal = Field(ge=0)
    upper_minimum: Decimal = Field(ge=0)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    valid_from: str
    valid_until: str | None = None
    classification: CommercialClassification = CommercialClassification.CONFIRMED
    source: str = Field(min_length=1, max_length=500)


class PricingSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int | None = Field(default=None, ge=1)
    capex_ribeira: Decimal | None = Field(default=None, ge=0)
    net_installation_margin: Decimal | None = None
    other_net_inflows: Decimal | None = None
    capex_classification: CommercialClassification = CommercialClassification.CONFIRMED
    margin_classification: CommercialClassification = CommercialClassification.CONFIRMED
    other_inflows_classification: CommercialClassification = (
        CommercialClassification.CONFIRMED
    )


class CapacityPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(default="TENANT", min_length=1, max_length=60)
    capacity_type: str = Field(min_length=1, max_length=100)
    value: Decimal = Field(ge=0)
    unit: str = Field(min_length=1, max_length=60)
    effective_from: str
    effective_until: str | None = None
    status: str = Field(default="DRAFT", min_length=1, max_length=40)
    source: str = Field(min_length=1, max_length=500)
    classification: CommercialClassification = CommercialClassification.CONFIRMED


class CapacityEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requested_capacity: Decimal = Field(ge=0)
    capacity_type: str = Field(min_length=1, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list)


class CommercialRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    condition: dict[str, Any]
    action: dict[str, Any]
    version: int = Field(default=1, ge=1)
    status: str = Field(default="DRAFT", pattern=r"^(DRAFT|ACTIVE|RETIRED)$")


class OpportunityQualificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: str | None = None
    rule_id: str
    version: int | None = Field(default=None, ge=1)
    facts: dict[str, Any]
    classification: OpportunityClassification = (
        OpportunityClassification.POTENTIAL_OPPORTUNITY
    )


def _build_store(settings: Settings):
    if settings.storage == "sqlite":
        return SQLiteStore(os.getenv("RIBEIRA_SQLITE_PATH", ":memory:"))
    if not settings.database_url:
        raise RuntimeError(
            "RIBEIRA_DATABASE_URL is required when RIBEIRA_STORAGE=postgres"
        )
    return PostgresStore(settings.database_url)


def _build_identity_provider(settings: Settings) -> IdentityProvider:
    if settings.auth_mode == "development":
        token = os.getenv("RIBEIRA_DEV_AUTH_TOKEN")
        tenant_id = os.getenv("RIBEIRA_DEV_AUTH_TENANT_ID") or None
        roles = frozenset(
            item.strip()
            for item in os.getenv("RIBEIRA_DEV_AUTH_ROLES", "VIEWER").split(",")
            if item.strip()
        )
        if not token:
            raise RuntimeError("development auth requires RIBEIRA_DEV_AUTH_TOKEN")
        return DevelopmentIdentityProvider(
            token,
            AuthContext(
                os.getenv("RIBEIRA_DEV_AUTH_SUBJECT", "local-developer"),
                tenant_id,
                roles=roles,
                is_platform_admin="PLATFORM_ADMIN" in roles,
            ),
        )
    if settings.auth_mode != "oidc":
        raise ValueError("authentication mode must be development or oidc")
    public_key = os.getenv("RIBEIRA_JWT_PUBLIC_KEY") or None
    jwks_url = os.getenv("RIBEIRA_JWT_JWKS_URL") or None
    issuer = os.getenv("RIBEIRA_JWT_ISSUER") or None
    audience = os.getenv("RIBEIRA_JWT_AUDIENCE") or None
    algorithms = tuple(
        item.strip()
        for item in os.getenv("RIBEIRA_JWT_ALGORITHMS", "RS256").split(",")
        if item.strip()
    )
    return JwtIdentityProvider(
        public_key=public_key,
        jwks_url=jwks_url,
        issuer=issuer,
        audience=audience,
        algorithms=algorithms,
        jwks_cache_ttl_seconds=int(os.getenv("RIBEIRA_JWKS_CACHE_TTL_SECONDS", "300")),
        jwks_refresh_seconds=int(os.getenv("RIBEIRA_JWKS_REFRESH_SECONDS", "30")),
        jwks_timeout_seconds=int(os.getenv("RIBEIRA_JWKS_TIMEOUT_SECONDS", "3")),
    )


def _auth_context(request: Request, provider: IdentityProvider) -> AuthContext:
    value = request.headers.get("Authorization", "")
    if not value.startswith("Bearer ") or not value[7:].strip():
        raise AuthenticationError("authentication required")
    try:
        return provider.authenticate(value[7:].strip())
    except AuthenticationError:
        raise


def create_app(
    application: RibeiraApplication | None = None,
    identity_provider: IdentityProvider | None = None,
    policy: AuthorizationPolicy | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    application = application or RibeiraApplication(_build_store(settings))
    identity_provider = identity_provider or _build_identity_provider(settings)
    policy = policy or AuthorizationPolicy()
    app = FastAPI(
        title="Ribeira Intelligence Platform API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.ribeira = application
    app.state.identity_provider = identity_provider
    app.state.authorization = policy
    app.state.settings = settings
    identity_store = application.store
    identity_access = (
        IdentityAccess(cast(PostgresStore, identity_store))
        if settings.auth_mode == "oidc" and isinstance(identity_store, PostgresStore)
        else None
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-Correlation-ID",
                "X-Boundary-Filename",
                "X-Boundary-CRS",
                "X-Boundary-Source",
                "X-Boundary-Classification",
            ],
        )

    @app.middleware("http")
    async def request_middleware(request: Request, call_next: Callable):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        correlation_id = request.headers.get("X-Correlation-ID") or request_id
        if len(request_id) > 128 or len(correlation_id) > 128:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_REQUEST_ID",
                        "message": "request identifiers are too long",
                    }
                },
            )
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        length = request.headers.get("content-length")
        if length:
            try:
                body_length = int(length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_CONTENT_LENGTH",
                            "message": "content-length must be an integer",
                        }
                    },
                )
            if body_length < 0 or body_length > settings.max_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "BODY_TOO_LARGE",
                            "message": "request body exceeds configured limit",
                        }
                    },
                )
        start = time.perf_counter()
        try:
            with audit_request_context(request_id, correlation_id):
                response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled request error",
                extra={"request_id": request_id, "correlation_id": correlation_id},
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "internal server error",
                    }
                },
            )
        elapsed = time.perf_counter() - start
        path = request.url.path
        REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        LATENCY.labels(request.method, path).observe(elapsed)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = (
            response.headers.get("Cache-Control", "private, max-age=300")
            if "/tiles/" in path
            else "no-store"
            if path.startswith("/v1")
            else response.headers.get("Cache-Control", "no-cache")
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "request validation failed",
                    "fields": exc.errors(),
                }
            },
        )

    @app.exception_handler(AuthorizationError)
    async def authorization_error(_: Request, exc: AuthorizationError):
        logger.warning(
            "authorization denied",
            extra={"status": "DENIED", "failure_code": "AUTHORIZATION_DENIED"},
        )
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "FORBIDDEN", "message": str(exc)}},
        )

    @app.exception_handler(PermissionError)
    async def permission_error(_: Request, exc: PermissionError):
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "FORBIDDEN", "message": str(exc)}},
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_error(_: Request, exc: AuthenticationError):
        logger.warning(
            "authentication failed",
            extra={
                "status": "DENIED",
                "failure_code": getattr(exc, "failure_code", "AUTHENTICATION_FAILED"),
            },
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": {"code": "INVALID_TOKEN", "message": "invalid bearer token"}
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(LookupError)
    async def lookup_error(_: Request, exc: LookupError):
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "NOT_FOUND", "message": str(exc)}},
        )

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_VALUE", "message": str(exc)}},
        )

    @app.exception_handler(BoundaryImportConflict)
    async def boundary_import_conflict(_: Request, exc: BoundaryImportConflict):
        return JSONResponse(
            status_code=409,
            content={
                "error": {"code": "BOUNDARY_IMPORT_CONFLICT", "message": str(exc)}
            },
        )

    @app.get("/health/live", tags=["health"])
    async def live():
        return {"status": "ok", "service": "ribeira-platform"}

    @app.get("/health/ready", tags=["health"])
    async def ready():
        try:
            if not application.store.ready():
                raise RuntimeError("storage not ready")
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "dependency": "database"},
            )
        return {"status": "ready", "dependency": "database"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    def context(request: Request) -> AuthContext:
        verified = _auth_context(request, identity_provider)
        parts = request.url.path.split("/")
        tenant_id = (
            parts[3] if len(parts) > 3 and parts[1:3] == ["v1", "tenants"] else None
        )
        if identity_access and tenant_id:
            try:
                resolved = identity_access.for_tenant(verified, tenant_id)
            except AuthorizationError:
                logger.warning(
                    "membership denied",
                    extra={
                        "tenant_id": tenant_id,
                        "status": "DENIED",
                        "failure_code": "MEMBERSHIP_DENIED",
                    },
                )
                raise
            logger.info(
                "authentication succeeded",
                extra={"tenant_id": tenant_id, "status": "SUCCEEDED"},
            )
            return resolved
        return verified

    def authorize(ctx: AuthContext, permission: str, tenant_id: str) -> None:
        policy.require(ctx, permission, tenant_id=tenant_id)

    def property_area_hectares(item: Property) -> str | None:
        """Calculate only from an explicit, valid geometry; never estimate area."""
        if item.geometry_geojson is None or item.geometry_crs is None:
            return None
        try:
            geometry, _, _ = GeometryService.to_wgs84(item)
            square_metres, _ = Geod(ellps="WGS84").geometry_area_perimeter(
                shape(geometry)
            )
            return format(abs(Decimal(str(square_metres))) / Decimal("10000"), "f")
        except Exception:
            return None

    def safe_property(item: Property, status: str | None = None) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "tenant_id": item.tenant_id,
            "geometry_geojson": item.geometry_geojson,
            "geometry_crs": item.geometry_crs,
            "boundary_source": item.boundary_source,
            "boundary_checksum": item.boundary_checksum,
            "area_hectares": property_area_hectares(item),
            "classification": item.classification.value,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "data_status": status or "UNKNOWN",
        }

    def safe_boundary_import(
        item: BoundaryImport, *, include_geometry: bool = False
    ) -> dict[str, Any]:
        """Return import metadata without leaking a physical storage reference."""
        result: dict[str, Any] = {
            "id": item.id,
            "tenant_id": item.tenant_id,
            "property_id": item.property_id,
            "original_filename": item.original_filename,
            "original_format": item.original_format,
            "file_size_bytes": item.file_size_bytes,
            "file_sha256": item.file_sha256,
            "original_crs": item.original_crs,
            "detected_crs": item.detected_crs,
            "target_crs": item.target_crs,
            "geometry_checksum": item.geometry_checksum,
            "boundary_source": item.boundary_source,
            "classification": item.classification.value,
            "warnings": item.warnings,
            "status": item.status,
            "created_by": item.created_by,
            "expected_property_checksum": item.expected_property_checksum,
            "created_at": item.created_at,
            "reviewed_by": item.reviewed_by,
            "review_reason": item.review_reason,
            "approved_boundary_version": item.approved_boundary_version,
            "reviewed_at": item.reviewed_at,
        }
        if include_geometry:
            result["geometry_geojson"] = item.geometry_geojson
        return result

    async def read_boundary_import_body(request: Request) -> bytes:
        """Bound raw upload buffering to the configured boundary import size."""
        maximum = min(settings.max_body_bytes, 1_000_000)
        chunks: list[bytes] = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > maximum:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "BOUNDARY_IMPORT_TOO_LARGE",
                        "message": "boundary import exceeds configured limit",
                    },
                )
            chunks.append(chunk)
        if not chunks:
            raise ValueError("boundary import body is required")
        return b"".join(chunks)

    def safe_scene(item: Any, assets: list[Any] | None = None) -> dict[str, Any]:
        return {
            "id": item.id,
            "property_id": item.property_id,
            "provider": item.provider_id,
            "collection": item.collection_id,
            "scene_id": item.external_item_id,
            "acquisition_datetime": item.acquisition_datetime,
            "provider_published_datetime": item.provider_published_datetime,
            "cloud_cover": item.cloud_cover,
            "platform": item.platform,
            "constellation": item.constellation,
            "processing_level": item.processing_level,
            "checksum": item.checksum,
            "source_status": "METADATA_CATALOGUED",
            "assets": [
                {
                    "id": asset.id,
                    "asset_key": asset.asset_key,
                    "title": asset.title,
                    "roles": asset.roles,
                    "checksum": asset.checksum_local
                    or asset.checksum_provider
                    or asset.checksum,
                    "download_status": asset.download_status or "METADATA_ONLY",
                    "bytes_downloaded": asset.bytes_downloaded,
                }
                for asset in (assets or [])
            ],
        }

    def safe_product(item: Any) -> dict[str, Any]:
        stats = item.statistics
        return {
            "id": item.id,
            "property_id": item.property_id,
            "scene_id": item.scene_id,
            "processing_job_id": item.processing_job_id,
            "product_type": item.product_type,
            "classification": item.classification.value,
            "statistics": {
                "minimum": stats.minimum,
                "maximum": stats.maximum,
                "mean": stats.mean,
                "median": stats.median,
                "valid_count": stats.valid_count,
                "nodata_count": stats.nodata_count,
                "coverage_percentage": stats.coverage_percentage,
            },
            "checksum": item.output_checksum,
            "generated_at": item.created_at,
            "processing_status": "SUCCEEDED"
            if item.output_reference
            else "DADO_INSUFICIENTE",
            "algorithm_id": item.algorithm_id,
            "algorithm_version": item.algorithm_version,
            "formula": item.formula,
            "input_asset_keys": item.input_asset_keys,
            "limitations": item.limitations,
            "quality": [quality.value for quality in item.quality],
        }

    def safe_timeline_item(item: dict[str, Any]) -> dict[str, Any]:
        product = safe_product(item["product"])
        product["processing_status"] = item["processing_status"]
        return {
            "scene_internal_id": item["scene_id"],
            "scene_id": item["external_scene_id"],
            "provider": item["provider_id"],
            "collection": item["collection_id"],
            "acquisition_datetime": item["acquisition_datetime"],
            "cloud_cover": item["cloud_cover"],
            "derived_product": product,
            "provenance_available": True,
        }

    def data_status(products: list[Any], scenes: list[Any]) -> str:
        if any(product.output_reference for product in products):
            return "READY"
        if products:
            return "DADO_INSUFICIENTE"
        if scenes:
            return "DADO_INSUFICIENTE"
        return "UNKNOWN"

    @app.post("/v1/tenants", status_code=201, tags=["tenants"])
    async def create_tenant(
        payload: TenantRequest, ctx: AuthContext = Depends(context)
    ):
        policy.require(ctx, "platform:admin")
        return to_jsonable(application.create_tenant(payload.name))

    @app.post(
        "/v1/tenants/{tenant_id}/properties", status_code=201, tags=["properties"]
    )
    async def create_property(
        tenant_id: str, payload: PropertyRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "property:write", tenant_id)
        item = application.create_property(
            tenant_id,
            payload.name,
            payload.geometry_geojson,
            payload.geometry_crs,
            platform_admin=ctx.is_platform_admin,
            boundary_source=payload.boundary_source,
            classification=payload.classification,
            actor=ctx.subject,
        )
        return safe_property(item)

    @app.get("/v1/tenants/{tenant_id}/properties", tags=["farm-360"])
    async def list_properties(tenant_id: str, ctx: AuthContext = Depends(context)):
        authorize(ctx, "property:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            properties = application.store.list_properties(tenant_id)
        return {"items": [safe_property(item) for item in properties]}

    @app.get("/v1/tenants/{tenant_id}/portfolio", tags=["portfolio"])
    async def tenant_portfolio(tenant_id: str, ctx: AuthContext = Depends(context)):
        """Tenant-scoped operational summary; absent source values remain null."""
        authorize(ctx, "property:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            properties = application.store.list_properties(tenant_id)
            jobs = application.store.connection.execute(
                "SELECT property_id,status,COUNT(*) AS count FROM processing_job WHERE tenant_id=%s GROUP BY property_id,status",
                (tenant_id,),
            ).fetchall()
            scenes = application.store.connection.execute(
                """SELECT DISTINCT ON (property_id) property_id, acquisition_datetime
                   FROM satellite_scene WHERE tenant_id=%s
                   ORDER BY property_id, acquisition_datetime DESC""",
                (tenant_id,),
            ).fetchall()
            products = application.store.connection.execute(
                """SELECT DISTINCT ON (property_id) property_id,id,created_at,output_reference
                   FROM derived_product
                   WHERE tenant_id=%s
                     AND product_type IN ('NDVI', 'NDVI_QUALITY_MASKED')
                   ORDER BY property_id, created_at DESC""",
                (tenant_id,),
            ).fetchall()
        job_status: dict[str, dict[str, int]] = {}
        for job in jobs:
            job_status.setdefault(str(job["property_id"]), {})[str(job["status"])] = (
                int(job["count"])
            )
        latest_scene = {str(row["property_id"]): row for row in scenes}
        latest_product = {str(row["property_id"]): row for row in products}
        items: list[dict[str, Any]] = []
        for item in properties:
            scene = latest_scene.get(item.id)
            product = latest_product.get(item.id)
            status = (
                "READY"
                if product and product["output_reference"]
                else ("DADO_INSUFICIENTE" if scene else "UNKNOWN")
            )
            record = safe_property(item, status)
            record.update(
                {
                    "latest_scene_at": scene["acquisition_datetime"].isoformat()
                    if scene
                    else None,
                    "latest_ndvi_at": product["created_at"].isoformat()
                    if product
                    else None,
                    "latest_ndvi_id": str(product["id"]) if product else None,
                    "provenance_available": bool(
                        product and product["output_reference"]
                    ),
                    "jobs": job_status.get(item.id, {}),
                }
            )
            items.append(record)
        return {"items": items}

    @app.get(
        "/v1/tenants/{tenant_id}/vale-do-ribeira/situation",
        tags=["vale-do-ribeira"],
    )
    async def vale_do_ribeira_situation(
        tenant_id: str, ctx: AuthContext = Depends(context)
    ):
        """Tenant-authorized read of shared, non-tenant hydro reference facts."""
        authorize(ctx, "geospatial:read", tenant_id)
        return ValeDoRibeiraSituationService(application.store).build()

    @app.get("/v1/tenants/{tenant_id}/properties/{property_id}", tags=["farm-360"])
    async def get_property(
        tenant_id: str, property_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "property:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            item = application.store.get_property(tenant_id, property_id)
        if item is None:
            raise LookupError("property not found in tenant")
        products = application.geospatial.list_products(tenant_id, property_id)
        scenes = application.geospatial.list_scenes(tenant_id, property_id)
        return safe_property(item, data_status(products, scenes))

    @app.put(
        "/v1/tenants/{tenant_id}/properties/{property_id}/boundary", tags=["properties"]
    )
    async def update_property_boundary(
        tenant_id: str,
        property_id: str,
        payload: BoundaryUpdateRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "property:write", tenant_id)
        item = application.update_property_boundary(
            tenant_id,
            property_id,
            payload.geometry_geojson,
            payload.geometry_crs,
            payload.boundary_source,
            payload.classification,
            payload.reason,
            ctx.subject,
            payload.expected_checksum,
            ctx.is_platform_admin,
        )
        return safe_property(item)

    @app.post(
        "/v1/tenants/{tenant_id}/properties/{property_id}/boundary-imports",
        status_code=201,
        tags=["boundary-imports"],
    )
    async def create_boundary_import(
        tenant_id: str,
        property_id: str,
        request: Request,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "property:write", tenant_id)
        filename = request.headers.get("X-Boundary-Filename", "")
        declared_crs = request.headers.get("X-Boundary-CRS")
        source = request.headers.get("X-Boundary-Source", "")
        classification_value = request.headers.get("X-Boundary-Classification", "")
        try:
            classification = DataClassification(classification_value)
        except ValueError as exc:
            raise ValueError(
                "X-Boundary-Classification must be an explicit classification"
            ) from exc
        item = application.create_boundary_import(
            tenant_id,
            property_id,
            original_filename=filename,
            payload=await read_boundary_import_body(request),
            declared_crs=declared_crs,
            boundary_source=source,
            classification=classification,
            actor=ctx.subject,
            platform_admin=ctx.is_platform_admin,
        )
        return safe_boundary_import(item, include_geometry=True)

    @app.get(
        "/v1/tenants/{tenant_id}/properties/{property_id}/boundary-imports",
        tags=["boundary-imports"],
    )
    async def list_boundary_imports(
        tenant_id: str, property_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "property:read", tenant_id)
        return {
            "items": [
                safe_boundary_import(item)
                for item in application.list_boundary_imports(
                    tenant_id, property_id, platform_admin=ctx.is_platform_admin
                )
            ]
        }

    @app.get(
        "/v1/tenants/{tenant_id}/boundary-imports/{import_id}",
        tags=["boundary-imports"],
    )
    async def get_boundary_import(
        tenant_id: str, import_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "property:read", tenant_id)
        return safe_boundary_import(
            application.get_boundary_import(
                tenant_id, import_id, platform_admin=ctx.is_platform_admin
            ),
            include_geometry=True,
        )

    @app.get(
        "/v1/tenants/{tenant_id}/boundary-imports/{import_id}/preview",
        tags=["boundary-imports"],
    )
    async def preview_boundary_import(
        tenant_id: str, import_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "property:read", tenant_id)
        preview = application.preview_boundary_import(
            tenant_id, import_id, platform_admin=ctx.is_platform_admin
        )
        return {
            "import": safe_boundary_import(preview["import"], include_geometry=True),
            "current_boundary_checksum": preview["current_boundary_checksum"],
            "current_area_hectares": preview["current_area_hectares"],
            "imported_area_hectares": preview["imported_area_hectares"],
            "absolute_area_delta_hectares": preview["absolute_area_delta_hectares"],
            "percentage_area_delta": preview["percentage_area_delta"],
            "current_geometry": preview["current_geometry"],
            "imported_geometry": preview["imported_geometry"],
        }

    @app.post(
        "/v1/tenants/{tenant_id}/boundary-imports/{import_id}/approve",
        tags=["boundary-imports"],
    )
    async def approve_boundary_import(
        tenant_id: str,
        import_id: str,
        payload: BoundaryImportReviewRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "tenant:manage", tenant_id)
        if payload.expected_property_checksum is None:
            raise ValueError("expected_property_checksum is required for approval")
        item = application.approve_boundary_import(
            tenant_id,
            import_id,
            reviewer=ctx.subject,
            reason=payload.review_reason,
            expected_property_checksum=payload.expected_property_checksum,
            platform_admin=ctx.is_platform_admin,
        )
        return safe_boundary_import(item, include_geometry=True)

    @app.post(
        "/v1/tenants/{tenant_id}/boundary-imports/{import_id}/reject",
        tags=["boundary-imports"],
    )
    async def reject_boundary_import(
        tenant_id: str,
        import_id: str,
        payload: BoundaryImportReviewRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "tenant:manage", tenant_id)
        item = application.reject_boundary_import(
            tenant_id,
            import_id,
            reviewer=ctx.subject,
            reason=payload.review_reason,
            platform_admin=ctx.is_platform_admin,
        )
        return safe_boundary_import(item, include_geometry=True)

    @app.get(
        "/v1/tenants/{tenant_id}/properties/{property_id}/geospatial",
        tags=["farm-360"],
    )
    async def get_property_geospatial(
        tenant_id: str, property_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            item = application.store.get_property(tenant_id, property_id)
        if item is None:
            raise LookupError("property not found in tenant")
        products = application.geospatial.list_products(tenant_id, property_id)
        scenes = application.geospatial.list_scenes(tenant_id, property_id)
        return {
            "property_id": item.id,
            "aoi": item.geometry_geojson,
            "geometry_crs": item.geometry_crs,
            "data_status": data_status(products, scenes),
        }

    @app.get(
        "/v1/tenants/{tenant_id}/properties/{property_id}/assets",
        tags=["farm-360", "assets"],
    )
    async def list_property_assets(
        tenant_id: str, property_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "asset:read", tenant_id)
        items = application.business.list_assets_for_property(
            tenant_id, property_id, platform_admin=ctx.is_platform_admin
        )
        return {"property_id": property_id, "items": to_jsonable(items)}

    @app.post("/v1/tenants/{tenant_id}/sources", status_code=201, tags=["sources"])
    async def create_source(
        tenant_id: str, payload: SourceRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "source:write", tenant_id)
        return to_jsonable(
            application.create_source(
                tenant_id,
                payload.name,
                payload.source_type,
                payload.provider,
                payload.endpoint,
                payload.source_version,
                ctx.is_platform_admin,
            )
        )

    @app.post("/v1/tenants/{tenant_id}/rules", status_code=201, tags=["rules"])
    async def create_rule(
        tenant_id: str, payload: RuleRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "rule:create", tenant_id)
        if payload.status == "ACTIVE":
            authorize(ctx, "rule:approve", tenant_id)
            if not payload.approved_by or payload.approved_by == ctx.subject:
                raise AuthorizationError("critical rule requires a distinct approver")
        rule = RuleDefinition(
            id=payload.id or new_id(),
            tenant_id=tenant_id,
            version=payload.version,
            name=payload.name,
            authority=payload.authority,
            metric=payload.metric,
            operator=payload.operator,
            threshold=payload.threshold,
            unit=payload.unit,
            severity=payload.severity,
            status=payload.status,
            approved_by=payload.approved_by,
            valid_from=payload.valid_from,
            valid_until=payload.valid_until,
            scope_type=payload.scope_type,
            scope_property_id=payload.scope_property_id,
        )
        return to_jsonable(application.create_rule(rule))

    @app.post(
        "/v1/tenants/{tenant_id}/properties/{property_id}/ingestions/{source_id}",
        tags=["ingestion"],
    )
    async def ingest(
        tenant_id: str,
        property_id: str,
        source_id: str,
        payload: ActorRequest | None = None,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "source:write", tenant_id)
        result = application.ingest(
            tenant_id,
            property_id,
            source_id,
            (payload.actor if payload and payload.actor else ctx.subject),
            ctx.is_platform_admin,
        )
        return to_jsonable(result)

    @app.post(
        "/v1/tenants/{tenant_id}/properties/{property_id}/evaluate", tags=["decisions"]
    )
    async def evaluate(
        tenant_id: str,
        property_id: str,
        payload: ActorRequest | None = None,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "decision:read", tenant_id)
        result = application.evaluate(
            tenant_id,
            property_id,
            (payload.actor if payload and payload.actor else ctx.subject),
            ctx.is_platform_admin,
        )
        return to_jsonable(result)

    @app.post(
        "/v1/tenants/{tenant_id}/actions/{action_id}/outcome",
        tags=["actions"],
    )
    async def complete_action(
        tenant_id: str,
        action_id: str,
        payload: ActionOutcomeRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "action:write", tenant_id)
        application.complete_action(
            tenant_id,
            action_id,
            outcome_detail=payload.outcome_detail,
            outcome_classification=payload.outcome_classification,
            evidence_ids=payload.evidence_ids,
            actor=ctx.subject,
            completed_at=payload.completed_at,
            platform_admin=ctx.is_platform_admin,
        )
        return {"id": action_id, "status": "COMPLETED"}

    @app.post(
        "/v1/tenants/{tenant_id}/pilot-feedback", status_code=201, tags=["feedback"]
    )
    async def create_pilot_feedback(
        tenant_id: str,
        payload: PilotFeedbackRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "feedback:write", tenant_id)
        item = application.create_pilot_feedback(
            tenant_id,
            feedback_type=payload.feedback_type,
            page=payload.page,
            feature_id=payload.feature_id,
            message=payload.message,
            property_id=payload.property_id,
            submitted_by=ctx.subject,
            platform_admin=ctx.is_platform_admin,
        )
        return to_jsonable(item)

    @app.post(
        "/v1/tenants/{tenant_id}/flood-exposure-assessments",
        status_code=201,
        tags=["flood-events"],
    )
    async def assess_flood_exposure(
        tenant_id: str,
        payload: FloodExposureAssessmentRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "action:write", tenant_id)
        return to_jsonable(
            application.assess_flood_exposure(
                tenant_id,
                event_key=payload.event_key,
                subject_type=payload.subject_type,
                subject_id=payload.subject_id,
                exposure_zone_id=payload.exposure_zone_id,
                actor=ctx.subject,
                platform_admin=ctx.is_platform_admin,
            )
        )

    @app.post("/v1/tenants/{tenant_id}/customers", status_code=201, tags=["commercial"])
    async def create_customer(
        tenant_id: str, payload: CustomerRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "commercial:write", tenant_id)
        return to_jsonable(
            application.business.create_customer(
                tenant_id,
                payload.display_name,
                customer_type=payload.customer_type,
                legal_name=payload.legal_name,
                status=payload.status,
                external_reference=payload.external_reference,
                actor=ctx.subject,
                platform_admin=ctx.is_platform_admin,
            )
        )

    @app.post("/v1/tenants/{tenant_id}/contracts", status_code=201, tags=["contracts"])
    async def create_contract(
        tenant_id: str, payload: ContractRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "contract:write", tenant_id)
        item = CustomerContract(
            new_id(),
            tenant_id,
            payload.customer_id,
            payload.property_id,
            payload.contract_type,
            payload.counterparty_name,
            payload.external_provider_name,
            payload.revenue_treatment,
            payload.status,
            payload.start_at,
            payload.end_at,
            payload.classification,
        )
        return to_jsonable(
            application.business.create_contract(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/contract-versions",
        status_code=201,
        tags=["contracts"],
    )
    async def create_contract_version(
        tenant_id: str,
        payload: ContractVersionRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "contract:write", tenant_id)
        if payload.status == "ACTIVE":
            raise AuthorizationError(
                "create the contract version as DRAFT and approve it in a separate operation"
            )
        item = ContractVersion(
            new_id(),
            tenant_id,
            payload.contract_id,
            payload.version,
            payload.status,
            payload.valid_from,
            payload.valid_until,
            payload.total_price,
            payload.currency,
            payload.recurring,
            payload.configuration,
            ctx.subject,
            None,
            CommercialClassification.CONFIRMED,
        )
        return to_jsonable(
            application.business.create_contract_version(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/contract-versions/{version_id}/approve",
        tags=["contracts"],
    )
    async def approve_contract_version(
        tenant_id: str, version_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "contract:approve", tenant_id)
        application.business.approve_contract_version(
            tenant_id,
            version_id,
            approver=ctx.subject,
            platform_admin=ctx.is_platform_admin,
        )
        return {
            "status": "ACTIVE",
            "approved_by": ctx.subject,
            "version_id": version_id,
        }

    @app.post("/v1/tenants/{tenant_id}/products", status_code=201, tags=["catalog"])
    async def create_product(
        tenant_id: str, payload: ProductRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "commercial:write", tenant_id)
        item = Product(
            new_id(),
            tenant_id,
            payload.name,
            payload.category,
            payload.status,
            payload.sku,
            payload.description,
            payload.classification,
        )
        return to_jsonable(
            application.business.create_product(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post("/v1/tenants/{tenant_id}/services", status_code=201, tags=["catalog"])
    async def create_service(
        tenant_id: str, payload: ServiceRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "commercial:write", tenant_id)
        item = ServiceOffering(
            new_id(),
            tenant_id,
            payload.name,
            payload.category,
            payload.status,
            payload.recurring,
            payload.revenue_type,
            payload.product_id,
            payload.classification,
        )
        return to_jsonable(
            application.business.create_service(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/service-plans", status_code=201, tags=["catalog"]
    )
    async def create_service_plan(
        tenant_id: str,
        payload: ServicePlanRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "commercial:write", tenant_id)
        item = ServicePlan(
            new_id(),
            tenant_id,
            payload.service_id,
            payload.name,
            payload.billing_period,
            payload.monthly_price,
            payload.currency,
            payload.status,
            payload.revenue_treatment,
            payload.classification,
        )
        return to_jsonable(
            application.business.create_service_plan(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.get(
        "/v1/tenants/{tenant_id}/customers/{customer_id}/mrr",
        tags=["commercial"],
    )
    async def customer_mrr(
        tenant_id: str, customer_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "commercial:read", tenant_id)
        return to_jsonable(
            application.business.calculate_mrr(
                tenant_id, customer_id, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post("/v1/tenants/{tenant_id}/assets", status_code=201, tags=["assets"])
    async def register_asset(
        tenant_id: str, payload: AssetRequest, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "asset:manage", tenant_id)
        item = Asset(
            new_id(),
            tenant_id,
            payload.asset_type,
            payload.name,
            payload.serial_number,
            payload.status,
            payload.property_id,
            payload.site_id,
            payload.classification,
            payload.geometry,
            payload.geometry_crs,
            payload.source_reference,
            payload.observed_at,
            payload.context,
        )
        return to_jsonable(
            application.business.register_asset(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/assets/{asset_id}/ownership",
        status_code=201,
        tags=["assets"],
    )
    async def assign_asset_ownership(
        tenant_id: str,
        asset_id: str,
        payload: AssetOwnershipRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "asset:manage", tenant_id)
        item = AssetOwnership(
            new_id(),
            tenant_id,
            asset_id,
            payload.ownership_kind,
            payload.customer_id,
            payload.purchased_by,
            payload.maintained_by,
            payload.replacement_responsibility,
            payload.risk_bearer,
            payload.valid_from,
            payload.valid_until,
            payload.acquisition_document,
            payload.classification,
        )
        return to_jsonable(
            application.business.assign_asset_ownership(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/installation-projects",
        status_code=201,
        tags=["projects"],
    )
    async def create_installation_project(
        tenant_id: str,
        payload: InstallationProjectRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "commercial:write", tenant_id)
        item = InstallationProject(
            new_id(),
            tenant_id,
            payload.customer_id,
            payload.property_id,
            payload.name,
            payload.status,
            payload.technical_provider_type,
            payload.customer_total_project_cost,
            payload.currency,
            payload.revenue_treatment,
            payload.classification,
        )
        return to_jsonable(
            application.business.create_installation_project(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/pricing-policies",
        status_code=201,
        tags=["pricing"],
    )
    async def create_pricing_policy(
        tenant_id: str,
        payload: PricingPolicyRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "pricing:write", tenant_id)
        item = PricingPolicy(
            new_id(),
            tenant_id,
            payload.name,
            payload.scope,
            payload.status,
            ctx.subject,
        )
        return to_jsonable(
            application.business.create_pricing_policy(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/pricing-policies/{policy_id}/versions",
        status_code=201,
        tags=["pricing"],
    )
    async def create_pricing_policy_version(
        tenant_id: str,
        policy_id: str,
        payload: PricingPolicyVersionRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "pricing:write", tenant_id)
        if payload.status == "ACTIVE":
            raise AuthorizationError(
                "create the pricing policy version as DRAFT and approve it in a separate operation"
            )
        item = PricingPolicyVersion(
            new_id(),
            tenant_id,
            policy_id,
            payload.version,
            payload.status,
            payload.lower_threshold,
            payload.lower_rate,
            payload.lower_minimum,
            payload.upper_rate,
            payload.upper_minimum,
            payload.currency,
            payload.valid_from,
            payload.valid_until,
            ctx.subject,
            None,
            payload.classification,
            payload.source,
        )
        return to_jsonable(
            application.business.create_pricing_policy_version(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/pricing-policies/{policy_id}/versions/{version_id}/approve",
        tags=["pricing"],
    )
    async def approve_pricing_policy_version(
        tenant_id: str,
        policy_id: str,
        version_id: str,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "pricing:approve", tenant_id)
        application.business.approve_pricing_policy_version(
            tenant_id,
            policy_id,
            version_id,
            approver=ctx.subject,
            platform_admin=ctx.is_platform_admin,
        )
        return {
            "status": "ACTIVE",
            "approved_by": ctx.subject,
            "policy_id": policy_id,
            "version_id": version_id,
        }

    @app.post(
        "/v1/tenants/{tenant_id}/pricing-policies/{policy_id}/simulate",
        tags=["pricing"],
    )
    async def simulate_price(
        tenant_id: str,
        policy_id: str,
        payload: PricingSimulationRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "pricing:simulate", tenant_id)
        capital = CapitalBreakdown(
            payload.capex_ribeira,
            payload.net_installation_margin,
            payload.other_net_inflows,
            payload.capex_classification,
            payload.margin_classification,
            payload.other_inflows_classification,
        )
        return to_jsonable(
            application.business.simulate_price(
                tenant_id,
                policy_id,
                capital,
                version=payload.version,
                platform_admin=ctx.is_platform_admin,
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/capacity-policies",
        status_code=201,
        tags=["capacity"],
    )
    async def create_capacity_policy(
        tenant_id: str,
        payload: CapacityPolicyRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "pricing:write", tenant_id)
        if payload.status == "ACTIVE":
            raise AuthorizationError(
                "create the capacity policy as DRAFT and approve it in a separate operation"
            )
        item = OperationalCapacityPolicy(
            new_id(),
            tenant_id,
            payload.scope,
            payload.capacity_type,
            payload.value,
            payload.unit,
            payload.effective_from,
            payload.effective_until,
            payload.status,
            ctx.subject,
            None,
            payload.source,
            payload.classification,
        )
        return to_jsonable(
            application.business.create_capacity_policy(
                item, actor=ctx.subject, platform_admin=ctx.is_platform_admin
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/capacity-policies/{policy_id}/approve",
        tags=["capacity"],
    )
    async def approve_capacity_policy(
        tenant_id: str, policy_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "capacity:approve", tenant_id)
        application.business.approve_capacity_policy(
            tenant_id,
            policy_id,
            approver=ctx.subject,
            platform_admin=ctx.is_platform_admin,
        )
        return {"status": "ACTIVE", "approved_by": ctx.subject, "policy_id": policy_id}

    @app.post(
        "/v1/tenants/{tenant_id}/capacity/evaluate",
        tags=["capacity"],
    )
    async def evaluate_capacity(
        tenant_id: str,
        payload: CapacityEvaluationRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "commercial:read", tenant_id)
        return to_jsonable(
            application.business.evaluate_capacity(
                tenant_id,
                payload.requested_capacity,
                payload.capacity_type,
                evidence_ids=payload.evidence_ids,
                platform_admin=ctx.is_platform_admin,
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/commercial-rules",
        status_code=201,
        tags=["commercial"],
    )
    async def create_commercial_rule(
        tenant_id: str,
        payload: CommercialRuleRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "commercial:write", tenant_id)
        if payload.status == "ACTIVE":
            raise AuthorizationError(
                "create the commercial rule as DRAFT and approve it in a separate operation"
            )
        rule_id, version_id = application.business.create_commercial_rule_version(
            tenant_id,
            payload.name,
            payload.condition,
            payload.action,
            created_by=ctx.subject,
            approved_by=None,
            version=payload.version,
            status=payload.status,
            platform_admin=ctx.is_platform_admin,
        )
        return {
            "rule_id": rule_id,
            "version_id": version_id,
            "version": payload.version,
        }

    @app.post(
        "/v1/tenants/{tenant_id}/commercial-rules/{version_id}/approve",
        tags=["commercial"],
    )
    async def approve_commercial_rule(
        tenant_id: str, version_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "commercial:approve", tenant_id)
        application.business.approve_commercial_rule_version(
            tenant_id,
            version_id,
            approver=ctx.subject,
            platform_admin=ctx.is_platform_admin,
        )
        return {
            "status": "ACTIVE",
            "approved_by": ctx.subject,
            "version_id": version_id,
        }

    @app.post(
        "/v1/tenants/{tenant_id}/customers/{customer_id}/opportunities/qualify",
        tags=["commercial"],
    )
    async def qualify_opportunity(
        tenant_id: str,
        customer_id: str,
        payload: OpportunityQualificationRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "commercial:write", tenant_id)
        result = application.business.qualify_opportunity(
            tenant_id,
            customer_id,
            payload.property_id,
            payload.rule_id,
            payload.facts,
            version=payload.version,
            actor=ctx.subject,
            classification=payload.classification,
            platform_admin=ctx.is_platform_admin,
        )
        return to_jsonable(result)

    @app.post(
        "/v1/tenants/{tenant_id}/properties/{property_id}/satellite-searches",
        status_code=201,
        tags=["geospatial"],
    )
    async def search_satellite(
        tenant_id: str,
        property_id: str,
        payload: SatelliteSearchRequestModel,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "geospatial:search", tenant_id)
        result = application.geospatial.search_satellite(
            tenant_id,
            SatelliteSearchRequest(
                property_id=property_id,
                collection_id=payload.collection_id,
                datetime_start=payload.datetime_start,
                datetime_end=payload.datetime_end,
                selection_policy=SceneSelectionPolicy(
                    policy_id=payload.policy_id,
                    version=payload.policy_version,
                    cloud_cover_limit=payload.cloud_cover_limit,
                    max_candidates=payload.max_candidates,
                ),
            ),
            actor=ctx.subject,
            platform_admin=ctx.is_platform_admin,
        )
        return to_jsonable(result)

    @app.get(
        "/v1/tenants/{tenant_id}/satellite-searches/{search_id}",
        tags=["geospatial"],
    )
    async def get_satellite_search(
        tenant_id: str, search_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        result = application.geospatial.get_search(tenant_id, search_id)
        if result is None:
            raise LookupError("satellite search not found in tenant")
        return to_jsonable(result)

    @app.get(
        "/v1/tenants/{tenant_id}/properties/{property_id}/scenes",
        tags=["geospatial"],
    )
    async def list_satellite_scenes(
        tenant_id: str, property_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            property_item = application.store.get_property(tenant_id, property_id)
        if property_item is None:
            raise LookupError("property not found in tenant")
        scenes = application.geospatial.list_scenes(tenant_id, property_id)
        return {
            "items": [
                safe_scene(
                    scene,
                    application.geospatial.list_assets(tenant_id, scene.id),
                )
                for scene in scenes
            ]
        }

    @app.get(
        "/v1/tenants/{tenant_id}/properties/{property_id}/derived-products",
        tags=["farm-360"],
    )
    async def list_derived_products(
        tenant_id: str, property_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            property_item = application.store.get_property(tenant_id, property_id)
        if property_item is None:
            raise LookupError("property not found in tenant")
        return {
            "items": [
                safe_product(item)
                for item in application.geospatial.list_products(tenant_id, property_id)
            ]
        }

    @app.get(
        "/v1/tenants/{tenant_id}/properties/{property_id}/timeline",
        tags=["temporal"],
    )
    async def get_property_timeline(
        tenant_id: str, property_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            property_item = application.store.get_property(tenant_id, property_id)
        if property_item is None:
            raise LookupError("property not found in tenant")
        return {
            "property_id": property_id,
            "order": "acquisition_datetime_asc",
            "items": [
                safe_timeline_item(item)
                for item in application.geospatial.timeline(tenant_id, property_id)
            ],
        }

    @app.get(
        "/v1/tenants/{tenant_id}/properties/{property_id}/temporal-comparison",
        tags=["temporal"],
    )
    async def get_temporal_comparison(
        tenant_id: str,
        property_id: str,
        baseline_product_id: str,
        target_product_id: str,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            property_item = application.store.get_property(tenant_id, property_id)
        if property_item is None:
            raise LookupError("property not found in tenant")
        comparison = application.geospatial.compare_products(
            tenant_id, property_id, baseline_product_id, target_product_id
        )
        return to_jsonable(
            {
                "property_id": property_id,
                "status": comparison["status"],
                "baseline": safe_product(comparison["baseline"]),
                "target": safe_product(comparison["target"]),
                "comparison": {
                    "delta_mean": comparison["delta_mean"],
                    "comparable_valid_pixels": comparison["comparable_valid_pixels"],
                    "comparable_coverage_percentage": comparison[
                        "comparable_coverage_percentage"
                    ],
                    "classification": "PIXEL_ALIGNED_DELTA"
                    if comparison.get("delta")
                    else "DERIVED_AGGREGATE"
                    if comparison["status"] == "READY"
                    else "INCONCLUSIVE",
                    "delta_product_id": comparison["delta"].id
                    if comparison.get("delta")
                    else None,
                    "delta_minimum": comparison["delta"].statistics.minimum
                    if comparison.get("delta")
                    else None,
                    "delta_maximum": comparison["delta"].statistics.maximum
                    if comparison.get("delta")
                    else None,
                    "delta_median": comparison["delta"].statistics.median
                    if comparison.get("delta")
                    else None,
                    "quality_mask_policy": comparison["delta"].parameters.get(
                        "quality_mask_policies"
                    )
                    if comparison.get("delta")
                    else None,
                    "alignment_summary": comparison["delta"].parameters.get("alignment")
                    if comparison.get("delta")
                    else None,
                    "limitations": comparison["limitations"],
                },
            }
        )

    @app.post(
        "/v1/tenants/{tenant_id}/properties/{property_id}/ndvi-jobs",
        status_code=202,
        tags=["geospatial"],
    )
    async def create_ndvi_job(
        tenant_id: str,
        property_id: str,
        payload: NdviJobRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "geospatial:process", tenant_id)
        return to_jsonable(
            application.geospatial.create_ndvi_job(
                tenant_id,
                property_id,
                payload.search_id,
                ctx.subject,
                ctx.is_platform_admin,
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/properties/{property_id}/quality-masked-ndvi-jobs",
        status_code=202,
        tags=["geospatial"],
    )
    async def create_quality_masked_ndvi_job(
        tenant_id: str,
        property_id: str,
        payload: ProductJobRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "geospatial:process", tenant_id)
        return to_jsonable(
            application.geospatial.create_quality_masked_ndvi_job(
                tenant_id,
                property_id,
                payload.product_id,
                ctx.subject,
                ctx.is_platform_admin,
            )
        )

    @app.post(
        "/v1/tenants/{tenant_id}/properties/{property_id}/temporal-delta-jobs",
        status_code=202,
        tags=["temporal"],
    )
    async def create_temporal_delta_job(
        tenant_id: str,
        property_id: str,
        payload: TemporalDeltaJobRequest,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "geospatial:process", tenant_id)
        return to_jsonable(
            application.geospatial.create_temporal_delta_job(
                tenant_id,
                property_id,
                payload.baseline_product_id,
                payload.target_product_id,
                ctx.subject,
                ctx.is_platform_admin,
            )
        )

    @app.get(
        "/v1/tenants/{tenant_id}/processing-jobs/{job_id}",
        tags=["geospatial"],
    )
    async def get_processing_job(
        tenant_id: str, job_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        result = application.geospatial.get_job(tenant_id, job_id)
        if result is None:
            raise LookupError("processing job not found in tenant")
        return to_jsonable(result)

    @app.get(
        "/v1/tenants/{tenant_id}/processing-jobs/{job_id}/transitions",
        tags=["geospatial"],
    )
    async def get_processing_job_transitions(
        tenant_id: str, job_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            job = application.geospatial.get_job(tenant_id, job_id)
            if job is None:
                raise LookupError("processing job not found in tenant")
            transitions = application.geospatial.repository.list_job_transitions(
                tenant_id, job_id
            )
        return {"items": to_jsonable(transitions)}

    @app.post(
        "/v1/tenants/{tenant_id}/processing-jobs/{job_id}/run",
        status_code=202,
        tags=["geospatial"],
    )
    async def run_processing_job(
        tenant_id: str, job_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:process", tenant_id)
        # Kept as a compatibility acknowledgement. A private worker claims and
        # executes persisted jobs; HTTP requests never invoke Rasterio/GDAL.
        job = application.geospatial.get_job(tenant_id, job_id)
        if job is None:
            raise LookupError("processing job not found in tenant")
        return to_jsonable(job)

    @app.post(
        "/v1/tenants/{tenant_id}/processing-jobs/{job_id}/retry",
        status_code=202,
        tags=["geospatial"],
    )
    async def retry_processing_job(
        tenant_id: str, job_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:process", tenant_id)
        with application.store.tenant_transaction(tenant_id, ctx.is_platform_admin):
            job = application.geospatial.repository.retry_job(
                tenant_id, job_id, ctx.subject
            )
            application.store.audit(
                tenant_id,
                ctx.subject,
                "PROCESSING_JOB_REQUEUED",
                "processing_job",
                job.id,
                {"attempt": job.attempt},
                new_id(),
                now_utc(),
            )
        return to_jsonable(job)

    @app.get(
        "/v1/tenants/{tenant_id}/derived-products/{product_id}/provenance",
        tags=["geospatial"],
    )
    async def get_derived_product_provenance(
        tenant_id: str, product_id: str, ctx: AuthContext = Depends(context)
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        result = application.geospatial.provenance(tenant_id, product_id)
        if result is None:
            raise LookupError("derived product not found in tenant")
        product = result["product"]
        scene = result["scene"]
        job = result["processing_job"]
        return to_jsonable(
            {
                "product": safe_product(product),
                "processing_job": {
                    "id": job.id if job else None,
                    "status": job.status if job else "UNKNOWN",
                    "algorithm_id": job.algorithm_id if job else None,
                    "algorithm_version": job.algorithm_version if job else None,
                    "created_at": job.created_at if job else None,
                    "started_at": job.started_at if job else None,
                    "finished_at": job.finished_at if job else None,
                },
                "assets": [
                    {
                        "id": asset.id,
                        "asset_key": asset.asset_key,
                        "title": asset.title,
                        "checksum": asset.checksum_local
                        or asset.checksum_provider
                        or asset.checksum,
                        "download_status": asset.download_status or "METADATA_ONLY",
                    }
                    for asset in result["assets"]
                ],
                "scene": safe_scene(scene) if scene else None,
                "provider": {
                    "id": scene.provider_id if scene else "UNKNOWN",
                    "collection": scene.collection_id if scene else "UNKNOWN",
                    "catalog_source": "COPERNICUS_CDSE_STAC" if scene else "UNKNOWN",
                },
                "evidence": result["evidence"],
                "upstreams": [
                    {
                        "relationship": upstream["relationship"],
                        "product": safe_product(upstream["product"]),
                        "scene": safe_scene(upstream["scene"])
                        if upstream["scene"]
                        else None,
                        "assets": [
                            {
                                "id": asset.id,
                                "asset_key": asset.asset_key,
                                "checksum": asset.checksum_local
                                or asset.checksum_provider
                                or asset.checksum,
                            }
                            for asset in upstream["assets"]
                        ],
                        "evidence": upstream["evidence"],
                    }
                    for upstream in result.get("upstreams", [])
                ],
            }
        )

    @app.get(
        "/v1/tenants/{tenant_id}/derived-products/{product_id}/tiles/{z}/{x}/{y}",
        tags=["farm-360"],
    )
    async def get_derived_product_tile(
        tenant_id: str,
        product_id: str,
        z: int,
        x: int,
        y: int,
        ctx: AuthContext = Depends(context),
    ):
        authorize(ctx, "geospatial:read", tenant_id)
        product = application.geospatial.get_product(tenant_id, product_id)
        if product is None:
            raise LookupError("derived product not found in tenant")
        if not product.output_reference:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "RASTER_UNAVAILABLE",
                    "message": "derived product has no raster",
                },
            )
        started = time.perf_counter()
        try:
            path = application.geospatial.object_storage.read_local_path(
                product.output_reference
            )
            tile = render_ndvi_tile(
                path, z, x, y, delta=product.product_type == "NDVI_DELTA"
            )
        except InvalidTile:
            TILE_FAILURES.inc()
            raise
        except (ObjectStorageError, RasterUnavailable, OSError, ValueError) as exc:
            TILE_FAILURES.inc()
            logger.warning("raster tile unavailable", extra={"product_id": product.id})
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "RASTER_UNAVAILABLE",
                    "message": "derived raster is unavailable",
                },
            ) from exc
        finally:
            TILE_LATENCY.observe(time.perf_counter() - started)
        return Response(
            content=tile.payload,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=300", "Vary": "Authorization"},
        )

    return app


def main() -> None:
    import uvicorn

    configure_structured_logging()
    uvicorn.run(
        create_app(),
        host=os.getenv("RIBEIRA_API_HOST", "127.0.0.1"),
        port=int(os.getenv("RIBEIRA_API_PORT", "8080")),
        log_config=None,
    )


if __name__ == "__main__":
    main()
