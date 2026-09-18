from __future__ import annotations

import os
import unittest

from ribeira_platform.iam import AuthContext, AuthorizationError
from ribeira_platform.identity_access import IdentityAccess
from ribeira_platform.models import new_id
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import RibeiraApplication
from tests.integration.tenant_cleanup import delete_test_tenants


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class OidcMembershipIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self.tenant_a = self.application.create_tenant("OIDC membership tenant A")
        self.tenant_b = self.application.create_tenant("OIDC membership tenant B")
        self.user_id = new_id()
        self.role_id = new_id()
        with self.store.tenant_transaction(None, platform_admin=True):
            self.store.connection.execute(
                "INSERT INTO identity_user(id,external_issuer,external_subject,status) VALUES (%s,%s,%s,'ACTIVE')",
                (self.user_id, "https://issuer.integration", "subject-integration"),
            )
            self.store.connection.execute(
                "INSERT INTO iam_role(id,code,description) VALUES (%s,%s,%s)",
                (
                    self.role_id,
                    f"VIEWER_TEST_{self.role_id[:8]}",
                    "OIDC integration test role",
                ),
            )
            self.store.connection.execute(
                "INSERT INTO tenant_membership(tenant_id,user_id,role_id,status) VALUES (%s,%s,%s,'ACTIVE')",
                (self.tenant_a.id, self.user_id, self.role_id),
            )

    def tearDown(self) -> None:
        try:
            with self.store.tenant_transaction(None, platform_admin=True):
                self.store.connection.execute(
                    "DELETE FROM tenant_membership WHERE user_id=%s", (self.user_id,)
                )
                self.store.connection.execute(
                    "DELETE FROM identity_user WHERE id=%s", (self.user_id,)
                )
                self.store.connection.execute(
                    "DELETE FROM iam_role WHERE id=%s", (self.role_id,)
                )
            delete_test_tenants([self.tenant_a.id, self.tenant_b.id])
        finally:
            self.store.close()

    def test_local_membership_resolves_identity_and_cross_tenant_is_denied(
        self,
    ) -> None:
        access = IdentityAccess(self.store)
        identity = AuthContext(
            "subject-integration", None, issuer="https://issuer.integration"
        )
        resolved = access.for_tenant(identity, self.tenant_a.id)
        self.assertEqual(resolved.tenant_id, self.tenant_a.id)
        self.assertEqual(len(resolved.roles), 1)
        with self.assertRaises(AuthorizationError):
            access.for_tenant(identity, self.tenant_b.id)
        with self.store.tenant_transaction(self.tenant_b.id):
            self.assertIsNone(
                self.store.connection.execute(
                    "SELECT user_id FROM tenant_membership WHERE tenant_id=%s AND user_id=%s",
                    (self.tenant_a.id, self.user_id),
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
