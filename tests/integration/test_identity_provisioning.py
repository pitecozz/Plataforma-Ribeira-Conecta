"""PostgreSQL tests use only explicitly synthetic OIDC identities and tenants."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from ribeira_platform.api import Settings, create_app
from ribeira_platform.business import Asset, CommercialClassification
from ribeira_platform.iam import AuthContext, AuthorizationError, AuthorizationPolicy
from ribeira_platform.iam import DevelopmentIdentityProvider
from ribeira_platform.identity_access import IdentityAccess
from ribeira_platform.identity_admin import provision, revoke
from ribeira_platform.identity_provisioning import (
    ExternalIdentityProvisioningRequest,
    ExternalMembershipRevocationRequest,
    IdentityProvisioningService,
    ProvisioningConflict,
    ProvisioningNotFound,
)
from ribeira_platform.models import new_id
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import RibeiraApplication
from tests.integration.tenant_cleanup import delete_test_tenants


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class IdentityProvisioningPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self.tenant_ids: list[str] = []
        self.user_ids: list[str] = []
        self.test_role_ids: list[str] = []

    def tearDown(self) -> None:
        try:
            with self.store.tenant_transaction(None, platform_admin=True):
                if self.user_ids:
                    self.store.connection.execute(
                        "DELETE FROM tenant_membership WHERE user_id = ANY(%s)",
                        (self.user_ids,),
                    )
                    self.store.connection.execute(
                        "DELETE FROM identity_user WHERE id = ANY(%s)",
                        (self.user_ids,),
                    )
                if self.test_role_ids:
                    self.store.connection.execute(
                        "DELETE FROM iam_role WHERE id = ANY(%s)",
                        (self.test_role_ids,),
                    )
            delete_test_tenants(self.tenant_ids)
        finally:
            self.store.close()

    def tenant(self, name: str):
        tenant = self.application.create_tenant(name)
        self.tenant_ids.append(tenant.id)
        return tenant

    def request(self, tenant_id: str, subject: str = "provider|synthetic-viewer"):
        return ExternalIdentityProvisioningRequest(
            external_issuer="https://issuer.synthetic.test/",
            external_subject=subject,
            tenant_id=tenant_id,
            role="VIEWER",
            operator_actor="SYSTEM_OPERATOR_TEST",
        )

    def provision(
        self, request: ExternalIdentityProvisioningRequest, *, dry_run: bool = False
    ):
        return IdentityProvisioningService(
            self.store
        ).provision_external_identity_membership(request, dry_run=dry_run)

    def revocation(
        self, request: ExternalMembershipRevocationRequest, *, dry_run: bool = False
    ):
        return IdentityProvisioningService(
            self.store
        ).revoke_external_identity_membership(request, dry_run=dry_run)

    def revoke_request(
        self, tenant_id: str, subject: str = "provider|synthetic-viewer"
    ) -> ExternalMembershipRevocationRequest:
        return ExternalMembershipRevocationRequest(
            external_issuer="https://issuer.synthetic.test/",
            external_subject=subject,
            tenant_id=tenant_id,
            expected_role="VIEWER",
            operator_actor="SYSTEM_OPERATOR_TEST",
        )

    def user_id(self, request: ExternalIdentityProvisioningRequest) -> str:
        with self.store.tenant_transaction(None, platform_admin=True):
            row = self.store.connection.execute(
                "SELECT id FROM identity_user WHERE external_issuer=%s AND external_subject=%s",
                (request.external_issuer, request.external_subject),
            ).fetchone()
        self.assertIsNotNone(row)
        user_id = str(row["id"])
        if user_id not in self.user_ids:
            self.user_ids.append(user_id)
        return user_id

    def test_viewer_role_is_persisted_with_exact_read_permissions(self) -> None:
        with self.store.tenant_transaction(None, platform_admin=True):
            rows = self.store.connection.execute(
                """SELECT permission.code FROM iam_role role
                   JOIN role_permission mapping ON mapping.role_id=role.id
                   JOIN iam_permission permission ON permission.id=mapping.permission_id
                   WHERE role.code='VIEWER' ORDER BY permission.code"""
            ).fetchall()
        self.assertEqual(
            [row["code"] for row in rows],
            ["asset:read", "geospatial:read", "property:read"],
        )

    def test_new_identity_membership_is_audited_and_idempotent(self) -> None:
        tenant = self.tenant("Synthetic identity provisioning tenant")
        request = self.request(tenant.id)
        created = self.provision(request)
        self.assertEqual(
            (created.identity, created.membership, created.audit),
            ("NEW", "CREATED", "WRITTEN"),
        )
        user_id = self.user_id(request)
        repeated = self.provision(request)
        self.assertEqual(
            (repeated.identity, repeated.membership, repeated.audit),
            ("EXISTING", "EXISTS", "NOT_WRITTEN"),
        )
        with self.store.tenant_transaction(tenant.id):
            membership_count = self.store.connection.execute(
                "SELECT count(*) AS count FROM tenant_membership WHERE user_id=%s",
                (user_id,),
            ).fetchone()
            audit = self.store.connection.execute(
                "SELECT payload FROM audit_log WHERE event_type='IDENTITY_MEMBERSHIP_PROVISIONED' AND entity_id=%s",
                (user_id,),
            ).fetchone()
        self.assertEqual(membership_count["count"], 1)
        self.assertIsNotNone(audit)
        self.assertNotIn(request.external_subject, str(audit["payload"]))
        self.assertNotIn(request.external_issuer, str(audit["payload"]))

    def test_dry_run_does_not_create_identity_or_membership(self) -> None:
        tenant = self.tenant("Synthetic identity dry run tenant")
        request = self.request(tenant.id, "provider|synthetic-dry-run")
        result = self.provision(request, dry_run=True)
        self.assertEqual(
            (result.identity, result.membership, result.audit),
            ("NEW", "WOULD_CREATE", "WOULD_WRITE"),
        )
        with self.store.tenant_transaction(None, platform_admin=True):
            row = self.store.connection.execute(
                "SELECT id FROM identity_user WHERE external_issuer=%s AND external_subject=%s",
                (request.external_issuer, request.external_subject),
            ).fetchone()
        self.assertIsNone(row)

    def test_cli_dry_run_uses_private_file_and_sanitized_output(self) -> None:
        tenant = self.tenant("Synthetic identity CLI tenant")
        request = self.request(tenant.id, "provider|synthetic-cli-dry-run")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "request.json"
            path.write_text(
                json.dumps(
                    {
                        "external_issuer": request.external_issuer,
                        "external_subject": request.external_subject,
                        "tenant_id": request.tenant_id,
                        "role": request.role,
                        "operator_actor": request.operator_actor,
                    }
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"RIBEIRA_DATABASE_URL": DATABASE_URL or ""}),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(provision(path, dry_run=True), 0)
        self.assertIn("REQUEST_FILE=SECURE", output.getvalue())
        self.assertIn("IDENTITY=NEW", output.getvalue())
        self.assertIn("MEMBERSHIP=WOULD_CREATE", output.getvalue())
        self.assertIn("AUDIT=WOULD_WRITE", output.getvalue())
        self.assertIn("DRY_RUN=PASS", output.getvalue())
        self.assertNotIn(request.external_issuer, output.getvalue())
        self.assertNotIn(request.external_subject, output.getvalue())
        self.assertNotIn(request.tenant_id, output.getvalue())

    def test_revocation_is_audited_idempotent_and_removes_endpoint_access(self) -> None:
        tenant = self.tenant("Synthetic identity revoke tenant")
        other_tenant = self.tenant("Synthetic identity revoke other tenant")
        provision_request = self.request(tenant.id, "provider|synthetic-revoke")
        self.provision(provision_request)
        self.provision(
            self.request(other_tenant.id, provision_request.external_subject)
        )
        user_id = self.user_id(provision_request)
        client = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "synthetic-revoked-token",
                    AuthContext(
                        provision_request.external_subject,
                        None,
                        issuer=provision_request.external_issuer,
                    ),
                ),
                settings=Settings("test", "postgres", None, (), "oidc", 1_000_000),
            )
        )
        headers = {"Authorization": "Bearer synthetic-revoked-token"}
        self.assertEqual(
            client.get(
                f"/v1/tenants/{tenant.id}/portfolio", headers=headers
            ).status_code,
            200,
        )

        revoked = self.revocation(
            self.revoke_request(tenant.id, provision_request.external_subject)
        )
        self.assertEqual(
            (revoked.current_status, revoked.action, revoked.audit),
            ("ACTIVE", "REVOKED", "WRITTEN"),
        )
        repeated = self.revocation(
            self.revoke_request(tenant.id, provision_request.external_subject)
        )
        self.assertEqual(
            (repeated.current_status, repeated.action, repeated.audit),
            ("REVOKED", "NO_CHANGE", "NOT_WRITTEN"),
        )
        self.assertEqual(
            client.get(
                f"/v1/tenants/{tenant.id}/portfolio", headers=headers
            ).status_code,
            403,
        )
        with self.store.tenant_transaction(tenant.id):
            membership = self.store.connection.execute(
                "SELECT status FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                (tenant.id, user_id),
            ).fetchone()
            identity = self.store.connection.execute(
                "SELECT id FROM identity_user WHERE id=%s", (user_id,)
            ).fetchone()
            events = self.store.connection.execute(
                "SELECT event_type, payload FROM audit_log WHERE entity_id=%s ORDER BY created_at",
                (user_id,),
            ).fetchall()
        self.assertEqual(membership["status"], "REVOKED")
        self.assertIsNotNone(identity)
        self.assertEqual(
            [row["event_type"] for row in events],
            ["IDENTITY_MEMBERSHIP_PROVISIONED", "IDENTITY_MEMBERSHIP_REVOKED"],
        )
        self.assertNotIn(provision_request.external_issuer, str(events[-1]["payload"]))
        self.assertNotIn(provision_request.external_subject, str(events[-1]["payload"]))
        with self.store.tenant_transaction(other_tenant.id):
            other_membership = self.store.connection.execute(
                "SELECT status FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                (other_tenant.id, user_id),
            ).fetchone()
        self.assertEqual(other_membership["status"], "ACTIVE")

    def test_revocation_dry_run_cli_and_guardrails_do_not_write(self) -> None:
        tenant_a = self.tenant("Synthetic revocation CLI tenant A")
        tenant_b = self.tenant("Synthetic revocation CLI tenant B")
        provision_request = self.request(tenant_a.id, "provider|synthetic-revoke-cli")
        self.provision(provision_request)
        self.provision(self.request(tenant_b.id, provision_request.external_subject))
        user_id = self.user_id(provision_request)
        revocation_request = self.revoke_request(
            tenant_a.id, provision_request.external_subject
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "revoke.json"
            path.write_text(
                json.dumps(
                    {
                        "external_issuer": revocation_request.external_issuer,
                        "external_subject": revocation_request.external_subject,
                        "tenant_id": revocation_request.tenant_id,
                        "expected_role": revocation_request.expected_role,
                        "operator_actor": revocation_request.operator_actor,
                    }
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"RIBEIRA_DATABASE_URL": DATABASE_URL or ""}),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(revoke(path, dry_run=True), 0)
        self.assertIn("CURRENT_STATUS=ACTIVE", output.getvalue())
        self.assertIn("ACTION=WOULD_REVOKE", output.getvalue())
        self.assertIn("AUDIT=WOULD_WRITE", output.getvalue())
        self.assertNotIn(revocation_request.external_subject, output.getvalue())
        with self.store.tenant_transaction(None, platform_admin=True):
            statuses = self.store.connection.execute(
                "SELECT tenant_id, status FROM tenant_membership WHERE user_id=%s ORDER BY tenant_id",
                (user_id,),
            ).fetchall()
        self.assertEqual(len(statuses), 2)
        self.assertTrue(all(row["status"] == "ACTIVE" for row in statuses))
        with self.assertRaises(ProvisioningNotFound):
            self.revocation(self.revoke_request(tenant_b.id, "provider|missing"))

    def test_revocation_role_mismatch_and_audit_failure_roll_back(self) -> None:
        tenant = self.tenant("Synthetic revocation guardrail tenant")
        provision_request = self.request(tenant.id, "provider|synthetic-revoke-guard")
        self.provision(provision_request)
        user_id = self.user_id(provision_request)
        alternate_role = new_id()
        self.test_role_ids.append(alternate_role)
        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.connection.execute(
                "INSERT INTO iam_role(id,code,description) VALUES (%s,%s,%s)",
                (alternate_role, f"SYNTHETIC_ROLE_{alternate_role[:8]}", "synthetic"),
            )
            self.store.connection.execute(
                "DELETE FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                (tenant.id, user_id),
            )
            self.store.connection.execute(
                "INSERT INTO tenant_membership(tenant_id,user_id,role_id,status) VALUES (%s,%s,%s,'ACTIVE')",
                (tenant.id, user_id, alternate_role),
            )
        with self.assertRaises(ProvisioningConflict):
            self.revocation(
                self.revoke_request(tenant.id, provision_request.external_subject)
            )

        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.connection.execute(
                "DELETE FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                (tenant.id, user_id),
            )
            viewer_role = self.store.connection.execute(
                "SELECT id FROM iam_role WHERE code='VIEWER'"
            ).fetchone()
            self.store.connection.execute(
                "INSERT INTO tenant_membership(tenant_id,user_id,role_id,status) VALUES (%s,%s,%s,'ACTIVE')",
                (tenant.id, user_id, viewer_role["id"]),
            )

        class FailingAuditStore(PostgresStore):
            def audit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("synthetic audit failure")

        failing_store = FailingAuditStore(DATABASE_URL)  # type: ignore[arg-type]
        try:
            with self.assertRaises(RuntimeError):
                IdentityProvisioningService(
                    failing_store
                ).revoke_external_identity_membership(
                    self.revoke_request(tenant.id, provision_request.external_subject)
                )
        finally:
            failing_store.close()
        with self.store.tenant_transaction(tenant.id):
            status = self.store.connection.execute(
                "SELECT status FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                (tenant.id, user_id),
            ).fetchone()
        self.assertEqual(status["status"], "ACTIVE")

    def test_revocation_does_not_cross_tenant_when_membership_is_absent(self) -> None:
        tenant_a = self.tenant("Synthetic revocation tenant A")
        tenant_b = self.tenant("Synthetic revocation tenant B")
        provision_request = self.request(tenant_a.id, "provider|synthetic-tenant-guard")
        self.provision(provision_request)
        user_id = self.user_id(provision_request)
        with self.assertRaises(ProvisioningNotFound):
            self.revocation(
                self.revoke_request(tenant_b.id, provision_request.external_subject)
            )
        with self.store.tenant_transaction(tenant_a.id):
            membership = self.store.connection.execute(
                "SELECT status FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                (tenant_a.id, user_id),
            ).fetchone()
        self.assertEqual(membership["status"], "ACTIVE")

    def test_conflicting_or_disabled_membership_is_not_replaced(self) -> None:
        tenant = self.tenant("Synthetic identity conflict tenant")
        request = self.request(tenant.id, "provider|synthetic-conflict")
        self.provision(request)
        user_id = self.user_id(request)
        alternate_role = new_id()
        self.test_role_ids.append(alternate_role)
        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.connection.execute(
                "INSERT INTO iam_role(id,code,description) VALUES (%s,%s,%s)",
                (
                    alternate_role,
                    f"SYNTHETIC_ROLE_{alternate_role[:8]}",
                    "synthetic test role",
                ),
            )
            self.store.connection.execute(
                "DELETE FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                (tenant.id, user_id),
            )
            self.store.connection.execute(
                "INSERT INTO tenant_membership(tenant_id,user_id,role_id,status) VALUES (%s,%s,%s,'DISABLED')",
                (tenant.id, user_id, alternate_role),
            )
        with self.assertRaises(ProvisioningConflict):
            self.provision(request)

    def test_failed_audit_rolls_back_identity_and_membership(self) -> None:
        tenant = self.tenant("Synthetic identity rollback tenant")
        request = self.request(tenant.id, "provider|synthetic-rollback")

        class FailingAuditStore(PostgresStore):
            def audit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise RuntimeError("synthetic audit failure")

        failing_store = FailingAuditStore(DATABASE_URL)  # type: ignore[arg-type]
        try:
            with self.assertRaises(RuntimeError):
                IdentityProvisioningService(
                    failing_store
                ).provision_external_identity_membership(request)
        finally:
            failing_store.close()
        with self.store.tenant_transaction(None, platform_admin=True):
            row = self.store.connection.execute(
                "SELECT id FROM identity_user WHERE external_issuer=%s AND external_subject=%s",
                (request.external_issuer, request.external_subject),
            ).fetchone()
        self.assertIsNone(row)

    def test_viewer_is_read_only_and_cross_tenant_is_denied(self) -> None:
        tenant_a = self.tenant("Synthetic identity tenant A")
        tenant_b = self.tenant("Synthetic identity tenant B")
        request = self.request(tenant_a.id, "provider|synthetic-cross-tenant")
        self.provision(request)
        self.user_id(request)
        identity = AuthContext(
            request.external_subject, None, issuer=request.external_issuer
        )
        resolved = IdentityAccess(self.store).for_tenant(identity, tenant_a.id)
        policy = AuthorizationPolicy()
        policy.require(resolved, "property:read", tenant_id=tenant_a.id)
        policy.require(resolved, "geospatial:read", tenant_id=tenant_a.id)
        policy.require(resolved, "asset:read", tenant_id=tenant_a.id)
        for permission in (
            "property:write",
            "tenant:manage",
            "asset:manage",
            "platform:admin",
        ):
            with self.assertRaises(AuthorizationError):
                policy.require(resolved, permission, tenant_id=tenant_a.id)
        with self.assertRaises(AuthorizationError):
            IdentityAccess(self.store).for_tenant(identity, tenant_b.id)

    def test_viewer_can_read_portfolio_but_cannot_write_or_approve(self) -> None:
        tenant = self.tenant("Synthetic viewer HTTP tenant")
        property_item = self.application.create_property(
            tenant.id, "SYNTHETIC_TEST_PROPERTY"
        )
        asset = Asset(
            new_id(),
            tenant.id,
            "BUILDING",
            "SYNTHETIC_VIEWER_ASSET",
            None,
            "ACTIVE",
            property_item.id,
            None,
            CommercialClassification.MANUAL_CONFIRMED,
            {"type": "Point", "coordinates": [-46.95, -24.05]},
            "EPSG:4326",
            "synthetic_test_data",
            "2026-09-22T00:00:00+00:00",
            {},
        )
        self.application.business.register_asset(asset, actor="SYSTEM_OPERATOR_TEST")
        request = self.request(tenant.id, "provider|synthetic-viewer-http")
        self.provision(request)
        self.user_id(request)
        client = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "synthetic-viewer-token",
                    AuthContext(
                        request.external_subject,
                        tenant.id,
                        roles=frozenset({"VIEWER"}),
                    ),
                ),
                settings=Settings(
                    "test", "postgres", None, (), "development", 1_000_000
                ),
            )
        )
        headers = {"Authorization": "Bearer synthetic-viewer-token"}

        portfolio = client.get(f"/v1/tenants/{tenant.id}/portfolio", headers=headers)
        self.assertEqual(portfolio.status_code, 200)
        self.assertEqual(len(portfolio.json()["items"]), 1)

        access = client.get(f"/v1/tenants/{tenant.id}/access", headers=headers)
        self.assertEqual(access.status_code, 200)
        self.assertEqual(
            access.json()["permissions"],
            [
                "asset:read",
                "decision:read",
                "feedback:write",
                "geospatial:read",
                "property:read",
            ],
        )

        assets = client.get(
            f"/v1/tenants/{tenant.id}/properties/{property_item.id}/assets",
            headers=headers,
        )
        self.assertEqual(assets.status_code, 200)
        self.assertEqual(assets.json()["items"][0]["id"], asset.id)

        evaluation = client.post(
            f"/v1/tenants/{tenant.id}/assets/{asset.id}/evaluate",
            headers=headers,
        )
        self.assertEqual(evaluation.status_code, 403)

        create = client.post(
            f"/v1/tenants/{tenant.id}/properties",
            headers=headers,
            json={"name": "SYNTHETIC_TEST_FORBIDDEN"},
        )
        self.assertEqual(create.status_code, 403)

        boundary = client.put(
            f"/v1/tenants/{tenant.id}/properties/{property_item.id}/boundary",
            headers=headers,
            json={
                "geometry_geojson": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-47.0, -24.0],
                            [-46.99, -24.0],
                            [-46.99, -24.01],
                            [-47.0, -24.01],
                            [-47.0, -24.0],
                        ]
                    ],
                },
                "geometry_crs": "EPSG:4326",
                "boundary_source": "synthetic_test_data",
                "classification": "MANUAL_CONFIRMED",
                "reason": "synthetic authorization test",
                "expected_checksum": "0" * 64,
            },
        )
        self.assertEqual(boundary.status_code, 403)

        approval = client.post(
            f"/v1/tenants/{tenant.id}/boundary-imports/"
            "00000000-0000-0000-0000-000000000000/approve",
            headers=headers,
            json={
                "review_reason": "synthetic authorization test",
                "expected_property_checksum": "0" * 64,
            },
        )
        self.assertEqual(approval.status_code, 403)


if __name__ == "__main__":
    unittest.main()
