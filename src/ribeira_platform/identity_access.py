"""Persistent application authorization for a verified OIDC identity."""

from __future__ import annotations

from dataclasses import replace

from .iam import AuthContext, AuthorizationError
from .postgres import PostgresStore


class IdentityAccess:
    """Maps verified issuer+subject to active local membership, never claims."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def for_tenant(self, context: AuthContext, tenant_id: str) -> AuthContext:
        if not context.issuer:
            raise AuthorizationError("OIDC issuer is required for tenant access")
        # The application role temporarily reads IAM tables as platform context
        # only to establish membership; no JWT claim can set this flag.
        with self.store.tenant_transaction(None, platform_admin=True):
            user = self.store.connection.execute(
                """SELECT id, platform_admin FROM identity_user
                   WHERE external_issuer=%s AND external_subject=%s AND status='ACTIVE'""",
                (context.issuer, context.subject),
            ).fetchone()
            if user is None:
                raise AuthorizationError("identity has no local access")
            if user["platform_admin"]:
                return replace(
                    context,
                    tenant_id=tenant_id,
                    roles=frozenset({"PLATFORM_ADMIN"}),
                    is_platform_admin=True,
                )
            rows = self.store.connection.execute(
                """SELECT r.code FROM tenant_membership m
                   JOIN iam_role r ON r.id=m.role_id
                   WHERE m.user_id=%s AND m.tenant_id=%s AND m.status='ACTIVE'""",
                (user["id"], tenant_id),
            ).fetchall()
        if not rows:
            raise AuthorizationError("identity has no active tenant membership")
        return replace(
            context,
            tenant_id=tenant_id,
            roles=frozenset(str(row["code"]) for row in rows),
            is_platform_admin=False,
        )
