from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .audit_context import request_context as audit_request_context
from .epistemology import RuleAuthority
from .iam import (
    AuthContext,
    AuthenticationError,
    AuthorizationError,
    DevelopmentIdentityProvider,
    IdentityProvider,
    JwtIdentityProvider,
    AuthorizationPolicy,
)
from .models import RuleDefinition, new_id, now_utc, to_jsonable
from .postgres import PostgresStore
from .service import RibeiraApplication
from .storage import SQLiteStore


logger = logging.getLogger("ribeira.api")
REQUESTS = Counter(
    "ribeira_http_requests_total", "HTTP requests", ["method", "path", "status"]
)
LATENCY = Histogram(
    "ribeira_http_request_duration_seconds", "HTTP request latency", ["method", "path"]
)


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
        return cls(
            os.getenv("RIBEIRA_ENV", "development"),
            os.getenv("RIBEIRA_STORAGE", "postgres"),
            os.getenv("RIBEIRA_DATABASE_URL"),
            origins,
            os.getenv("RIBEIRA_AUTH_MODE", "jwt"),
            int(os.getenv("RIBEIRA_MAX_BODY_BYTES", "1048576")),
        )


class TenantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class PropertyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    geometry_geojson: dict[str, Any] | None = None
    geometry_crs: str | None = Field(default=None, max_length=32)


class SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    source_type: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=160)
    endpoint: str | None = Field(default=None, max_length=2048)
    source_version: str | None = Field(default=None, max_length=160)


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


class ActorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str | None = Field(default=None, max_length=200)


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
    public_key = os.getenv("RIBEIRA_JWT_PUBLIC_KEY") or None
    jwks_url = os.getenv("RIBEIRA_JWT_JWKS_URL") or None
    issuer = os.getenv("RIBEIRA_JWT_ISSUER") or None
    audience = os.getenv("RIBEIRA_JWT_AUDIENCE") or None
    return JwtIdentityProvider(
        public_key=public_key, jwks_url=jwks_url, issuer=issuer, audience=audience
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

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-Correlation-ID",
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
            "no-store"
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
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}},
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
        return _auth_context(request, identity_provider)

    def authorize(ctx: AuthContext, permission: str, tenant_id: str) -> None:
        policy.require(ctx, permission, tenant_id=tenant_id)

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
        return to_jsonable(
            application.create_property(
                tenant_id,
                payload.name,
                payload.geometry_geojson,
                payload.geometry_crs,
                ctx.is_platform_admin,
            )
        )

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

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.getenv("RIBEIRA_API_HOST", "127.0.0.1"),
        port=int(os.getenv("RIBEIRA_API_PORT", "8080")),
    )


if __name__ == "__main__":
    main()
