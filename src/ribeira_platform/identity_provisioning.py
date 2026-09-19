"""Controlled local provisioning of audited OIDC tenant memberships."""

from __future__ import annotations

from dataclasses import dataclass

from .models import new_id, now_utc
from .postgres import PostgresStore


VIEWER_ROLE = "VIEWER"
PROVISION_EVENT = "IDENTITY_MEMBERSHIP_PROVISIONED"
REVOCATION_EVENT = "IDENTITY_MEMBERSHIP_REVOKED"


class ProvisioningConflict(RuntimeError):
    """A pre-existing identity or membership cannot be changed implicitly."""


class ProvisioningRequestError(ValueError):
    """A local operator request is incomplete or unsafe."""


class ProvisioningNotFound(LookupError):
    """The controlled identity, tenant, or membership was not found."""


@dataclass(frozen=True)
class ExternalIdentityProvisioningRequest:
    external_issuer: str
    external_subject: str
    tenant_id: str
    role: str
    operator_actor: str

    def validate(self) -> None:
        fields = {
            "external_issuer": self.external_issuer,
            "external_subject": self.external_subject,
            "tenant_id": self.tenant_id,
            "role": self.role,
            "operator_actor": self.operator_actor,
        }
        if any(
            not isinstance(value, str) or not value.strip() for value in fields.values()
        ):
            raise ProvisioningRequestError("provisioning request fields are required")
        if self.role != VIEWER_ROLE:
            raise ProvisioningRequestError("only the VIEWER role can be provisioned")
        if self.operator_actor.strip().lower() in {"user", "admin"}:
            raise ProvisioningRequestError("operator actor must be specific")


@dataclass(frozen=True)
class ProvisioningResult:
    identity: str
    membership: str
    audit: str
    dry_run: bool


@dataclass(frozen=True)
class ExternalMembershipRevocationRequest:
    external_issuer: str
    external_subject: str
    tenant_id: str
    expected_role: str
    operator_actor: str

    def validate(self) -> None:
        fields = {
            "external_issuer": self.external_issuer,
            "external_subject": self.external_subject,
            "tenant_id": self.tenant_id,
            "expected_role": self.expected_role,
            "operator_actor": self.operator_actor,
        }
        if any(
            not isinstance(value, str) or not value.strip() for value in fields.values()
        ):
            raise ProvisioningRequestError("revocation request fields are required")
        if self.expected_role != VIEWER_ROLE:
            raise ProvisioningRequestError("only the VIEWER role can be revoked")
        if self.operator_actor.strip().lower() in {"user", "admin"}:
            raise ProvisioningRequestError("operator actor must be specific")


@dataclass(frozen=True)
class RevocationResult:
    identity: str
    membership: str
    role: str
    current_status: str
    action: str
    audit: str
    dry_run: bool


class IdentityProvisioningService:
    """Applies issuer+subject provisioning in one controlled RLS transaction."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def provision_external_identity_membership(
        self, request: ExternalIdentityProvisioningRequest, *, dry_run: bool = False
    ) -> ProvisioningResult:
        request.validate()
        with self.store.tenant_transaction(None, platform_admin=True):
            tenant = self.store.connection.execute(
                "SELECT id FROM tenant WHERE id=%s FOR KEY SHARE", (request.tenant_id,)
            ).fetchone()
            if tenant is None:
                raise ProvisioningRequestError("tenant was not found")
            role = self.store.connection.execute(
                "SELECT id FROM iam_role WHERE code=%s", (request.role,)
            ).fetchone()
            if role is None:
                raise ProvisioningRequestError("requested role was not found")

            identity = self.store.connection.execute(
                """SELECT id, status, platform_admin FROM identity_user
                   WHERE external_issuer=%s AND external_subject=%s FOR UPDATE""",
                (request.external_issuer, request.external_subject),
            ).fetchone()
            if identity is None:
                if dry_run:
                    return ProvisioningResult(
                        "NEW", "WOULD_CREATE", "WOULD_WRITE", True
                    )
                inserted = self.store.connection.execute(
                    """INSERT INTO identity_user(id,external_issuer,external_subject,status,platform_admin)
                       VALUES (%s,%s,%s,'ACTIVE',false)
                       ON CONFLICT (external_issuer,external_subject) WHERE external_issuer IS NOT NULL
                       DO NOTHING RETURNING id""",
                    (new_id(), request.external_issuer, request.external_subject),
                ).fetchone()
                identity = self.store.connection.execute(
                    """SELECT id, status, platform_admin FROM identity_user
                       WHERE external_issuer=%s AND external_subject=%s FOR UPDATE""",
                    (request.external_issuer, request.external_subject),
                ).fetchone()
            else:
                inserted = None
            if identity is None:
                raise RuntimeError("identity provisioning did not resolve identity")
            if identity["status"] != "ACTIVE" or identity["platform_admin"]:
                raise ProvisioningConflict(
                    "identity is not eligible for viewer provisioning"
                )

            memberships = self.store.connection.execute(
                """SELECT role_id, status FROM tenant_membership
                   WHERE tenant_id=%s AND user_id=%s FOR UPDATE""",
                (request.tenant_id, identity["id"]),
            ).fetchall()
            if memberships:
                if (
                    len(memberships) == 1
                    and str(memberships[0]["role_id"]) == str(role["id"])
                    and memberships[0]["status"] == "ACTIVE"
                ):
                    return ProvisioningResult(
                        "NEW" if inserted is not None else "EXISTING",
                        "EXISTS",
                        "NOT_WRITTEN",
                        dry_run,
                    )
                raise ProvisioningConflict(
                    "existing membership cannot be replaced or reactivated"
                )

            if dry_run:
                return ProvisioningResult(
                    "NEW" if inserted is not None else "EXISTING",
                    "WOULD_CREATE",
                    "WOULD_WRITE",
                    True,
                )

            self.store.connection.execute(
                """INSERT INTO tenant_membership(tenant_id,user_id,role_id,status)
                   VALUES (%s,%s,%s,'ACTIVE')""",
                (request.tenant_id, identity["id"], role["id"]),
            )
            self.store.audit(
                request.tenant_id,
                request.operator_actor,
                PROVISION_EVENT,
                "tenant_membership",
                str(identity["id"]),
                {
                    "target_user_id": str(identity["id"]),
                    "role": request.role,
                    "membership_status": "ACTIVE",
                    "provisioning": "INTERNAL_OPERATOR",
                },
                new_id(),
                now_utc(),
            )
            return ProvisioningResult(
                "NEW" if inserted is not None else "EXISTING",
                "CREATED",
                "WRITTEN",
                False,
            )

    def revoke_external_identity_membership(
        self,
        request: ExternalMembershipRevocationRequest,
        *,
        dry_run: bool = False,
    ) -> RevocationResult:
        """Revoke only one expected role without deleting identity history."""
        request.validate()
        with self.store.tenant_transaction(None, platform_admin=True):
            tenant = self.store.connection.execute(
                "SELECT id FROM tenant WHERE id=%s FOR KEY SHARE", (request.tenant_id,)
            ).fetchone()
            if tenant is None:
                raise ProvisioningNotFound("tenant was not found")
            role = self.store.connection.execute(
                "SELECT id FROM iam_role WHERE code=%s", (request.expected_role,)
            ).fetchone()
            if role is None:
                raise ProvisioningRequestError("expected role was not found")
            identity = self.store.connection.execute(
                """SELECT id FROM identity_user
                   WHERE external_issuer=%s AND external_subject=%s FOR UPDATE""",
                (request.external_issuer, request.external_subject),
            ).fetchone()
            if identity is None:
                raise ProvisioningNotFound("identity was not found")

            memberships = self.store.connection.execute(
                """SELECT role_id, status FROM tenant_membership
                   WHERE tenant_id=%s AND user_id=%s FOR UPDATE""",
                (request.tenant_id, identity["id"]),
            ).fetchall()
            if not memberships:
                raise ProvisioningNotFound("membership was not found")
            membership = next(
                (row for row in memberships if str(row["role_id"]) == str(role["id"])),
                None,
            )
            if membership is None:
                raise ProvisioningConflict("membership role does not match request")
            current_status = str(membership["status"])
            if current_status == "REVOKED":
                return RevocationResult(
                    "FOUND",
                    "FOUND",
                    request.expected_role,
                    current_status,
                    "NO_CHANGE",
                    "NOT_WRITTEN",
                    dry_run,
                )
            if current_status != "ACTIVE":
                raise ProvisioningConflict("membership is not active")
            if dry_run:
                return RevocationResult(
                    "FOUND",
                    "FOUND",
                    request.expected_role,
                    current_status,
                    "WOULD_REVOKE",
                    "WOULD_WRITE",
                    True,
                )

            updated = self.store.connection.execute(
                """UPDATE tenant_membership SET status='REVOKED'
                   WHERE tenant_id=%s AND user_id=%s AND role_id=%s AND status='ACTIVE'""",
                (request.tenant_id, identity["id"], role["id"]),
            )
            if updated.rowcount != 1:
                raise ProvisioningConflict("membership state changed before revocation")
            self.store.audit(
                request.tenant_id,
                request.operator_actor,
                REVOCATION_EVENT,
                "tenant_membership",
                str(identity["id"]),
                {
                    "target_user_id": str(identity["id"]),
                    "role": request.expected_role,
                    "previous_status": "ACTIVE",
                    "membership_status": "REVOKED",
                    "revocation": "INTERNAL_OPERATOR",
                },
                new_id(),
                now_utc(),
            )
            return RevocationResult(
                "FOUND",
                "FOUND",
                request.expected_role,
                current_status,
                "REVOKED",
                "WRITTEN",
                False,
            )
