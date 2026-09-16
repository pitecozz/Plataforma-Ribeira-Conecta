from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import jwt


ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "PLATFORM_ADMIN": frozenset({"platform:admin"}),
    "TENANT_ADMIN": frozenset(
        {
            "tenant:read",
            "tenant:manage",
            "property:read",
            "property:write",
            "source:read",
            "source:write",
            "rule:read",
            "rule:create",
            "rule:approve",
            "decision:read",
            "action:write",
            "audit:read",
            "commercial:read",
            "commercial:write",
            "pricing:simulate",
            "pricing:write",
            "pricing:approve",
            "contract:read",
            "contract:write",
            "contract:approve",
            "capacity:approve",
            "commercial:approve",
            "asset:read",
            "asset:manage",
        }
    ),
    "MANAGER": frozenset(
        {
            "tenant:read",
            "property:read",
            "property:write",
            "source:read",
            "source:write",
            "rule:read",
            "rule:create",
            "decision:read",
            "action:write",
            "audit:read",
            "commercial:read",
            "commercial:write",
            "pricing:simulate",
            "pricing:write",
            "contract:read",
            "contract:write",
            "contract:approve",
            "capacity:approve",
            "commercial:approve",
            "asset:read",
            "asset:manage",
        }
    ),
    "ANALYST": frozenset(
        {
            "tenant:read",
            "property:read",
            "source:read",
            "rule:read",
            "decision:read",
            "audit:read",
            "commercial:read",
            "pricing:simulate",
            "contract:read",
            "asset:read",
        }
    ),
    "COMMERCIAL": frozenset(
        {
            "tenant:read",
            "property:read",
            "source:read",
            "decision:read",
            "commercial:read",
            "commercial:write",
            "pricing:simulate",
            "pricing:write",
            "contract:read",
            "contract:write",
            "asset:read",
        }
    ),
    "AGRONOMIST": frozenset(
        {
            "tenant:read",
            "property:read",
            "source:read",
            "rule:read",
            "rule:create",
            "rule:approve",
            "decision:read",
            "action:write",
            "commercial:read",
            "pricing:simulate",
            "asset:read",
        }
    ),
    "TECHNICIAN": frozenset(
        {
            "tenant:read",
            "property:read",
            "source:read",
            "source:write",
            "decision:read",
            "action:write",
            "asset:read",
            "asset:manage",
            "commercial:read",
        }
    ),
    "OPERATOR": frozenset(
        {
            "tenant:read",
            "property:read",
            "source:read",
            "decision:read",
            "action:write",
            "asset:read",
        }
    ),
    "VIEWER": frozenset(
        {
            "tenant:read",
            "property:read",
            "source:read",
            "decision:read",
            "commercial:read",
            "contract:read",
            "asset:read",
        }
    ),
}


class AuthenticationError(PermissionError):
    pass


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class AuthContext:
    subject: str
    tenant_id: str | None
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    is_platform_admin: bool = False
    token_id: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)

    def effective_permissions(self) -> frozenset[str]:
        values = set(self.permissions)
        for role in self.roles:
            values.update(ROLE_PERMISSIONS.get(role, ()))
        if "PLATFORM_ADMIN" in self.roles:
            values.add("platform:admin")
        return frozenset(values)


class IdentityProvider(Protocol):
    def authenticate(self, token: str) -> AuthContext: ...


class JwtIdentityProvider:
    """JWT/OIDC validator; production requires issuer, audience and key material."""

    def __init__(
        self,
        *,
        public_key: str | None = None,
        jwks_url: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
        algorithms: tuple[str, ...] = ("RS256",),
    ) -> None:
        self.public_key = public_key
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience
        self.algorithms = algorithms
        if not public_key and not jwks_url:
            raise ValueError("JWT public key or JWKS URL is required")
        if not issuer or not audience:
            raise ValueError("JWT issuer and audience are required")

    def authenticate(self, token: str) -> AuthContext:
        try:
            key = self.public_key
            if not key and self.jwks_url:
                key = jwt.PyJWKClient(self.jwks_url).get_signing_key_from_jwt(token).key
            if key is None:
                raise AuthenticationError("JWT signing key unavailable")
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "sub"]},
            )
        except (jwt.InvalidTokenError, ValueError) as exc:
            raise AuthenticationError("invalid bearer token") from exc
        return context_from_claims(claims)


class DevelopmentIdentityProvider:
    """Explicit local-only identity provider; never enabled by production defaults."""

    def __init__(self, token: str, context: AuthContext) -> None:
        if not token:
            raise ValueError("development auth token cannot be empty")
        self.token = token
        self.context = context

    def authenticate(self, token: str) -> AuthContext:
        if token != self.token:
            raise AuthenticationError("invalid development token")
        return self.context


def context_from_claims(claims: dict[str, Any]) -> AuthContext:
    roles_claim = claims.get("roles", claims.get("role", []))
    if isinstance(roles_claim, str):
        roles_claim = [roles_claim]
    roles = frozenset(str(value) for value in roles_claim or [])
    permissions_claim = claims.get("permissions", [])
    if isinstance(permissions_claim, str):
        permissions_claim = [permissions_claim]
    tenant_id = claims.get("tenant_id", claims.get("tid"))
    return AuthContext(
        subject=str(claims["sub"]),
        tenant_id=str(tenant_id) if tenant_id is not None else None,
        roles=roles,
        permissions=frozenset(str(value) for value in permissions_claim or []),
        is_platform_admin="PLATFORM_ADMIN" in roles
        or "platform:admin" in permissions_claim,
        token_id=str(claims["jti"]) if claims.get("jti") else None,
        claims=dict(claims),
    )


class AuthorizationPolicy:
    """Central default-deny policy for subject + tenant + permission + resource."""

    def require(
        self,
        context: AuthContext,
        permission: str,
        tenant_id: str | None = None,
        resource_tenant_id: str | None = None,
    ) -> None:
        if context is None:
            raise AuthorizationError("authentication required")
        if (
            tenant_id
            and not context.is_platform_admin
            and context.tenant_id != tenant_id
        ):
            raise AuthorizationError("tenant context does not match identity")
        if (
            resource_tenant_id
            and not context.is_platform_admin
            and context.tenant_id != resource_tenant_id
        ):
            raise AuthorizationError("resource is outside identity tenant")
        if context.is_platform_admin:
            return
        if permission not in context.effective_permissions():
            raise AuthorizationError("permission denied")
