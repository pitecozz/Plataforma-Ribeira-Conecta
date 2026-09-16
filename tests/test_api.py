from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from ribeira_platform.api import Settings, create_app
from ribeira_platform.iam import AuthContext, DevelopmentIdentityProvider
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.storage import SQLiteStore


class ApiSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore()
        self.application = RibeiraApplication(self.store)
        self.provider = DevelopmentIdentityProvider(
            "platform-secret-dev-only",
            AuthContext(
                "platform",
                None,
                roles=frozenset({"PLATFORM_ADMIN"}),
                is_platform_admin=True,
            ),
        )
        self.app = create_app(
            self.application,
            self.provider,
            settings=Settings("test", "sqlite", None, (), "development", 1024),
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.store.close()

    def test_live_and_ready_are_separate(self) -> None:
        live = self.client.get("/health/live")
        ready = self.client.get("/health/ready")
        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.assertNotEqual(live.json(), ready.json())

    def test_v1_requires_authentication_and_request_ids(self) -> None:
        missing = self.client.post("/v1/tenants", json={"name": "no auth"})
        self.assertEqual(missing.status_code, 401)
        invalid = self.client.post(
            "/v1/tenants",
            headers={"Authorization": "Bearer wrong"},
            json={"name": "invalid"},
        )
        self.assertEqual(invalid.status_code, 401)
        response = self.client.post(
            "/v1/tenants",
            headers={
                "Authorization": "Bearer platform-secret-dev-only",
                "X-Request-ID": "req-1",
            },
            json={"name": "Tenant"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.headers["X-Request-ID"], "req-1")
        self.assertIn("X-Correlation-ID", response.headers)

    def test_payload_limit_and_validation(self) -> None:
        large = self.client.post(
            "/v1/tenants",
            headers={
                "Authorization": "Bearer platform-secret-dev-only",
                "Content-Length": "4096",
            },
            content=b"{}",
        )
        self.assertEqual(large.status_code, 413)
        invalid = self.client.post(
            "/v1/tenants",
            headers={"Authorization": "Bearer platform-secret-dev-only"},
            json={"unexpected": "field"},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_audit_receives_request_and_correlation_ids(self) -> None:
        tenant = self.application.create_tenant("Tenant for audit")
        response = self.client.post(
            f"/v1/tenants/{tenant.id}/properties",
            headers={
                "Authorization": "Bearer platform-secret-dev-only",
                "X-Request-ID": "req-audit",
                "X-Correlation-ID": "corr-audit",
            },
            json={"name": "Audited property"},
        )
        self.assertEqual(response.status_code, 201)
        row = self.store.connection.execute(
            "SELECT request_id, correlation_id FROM audit_log WHERE entity_type='property'"
        ).fetchone()
        self.assertEqual(row["request_id"], "req-audit")
        self.assertEqual(row["correlation_id"], "corr-audit")


if __name__ == "__main__":
    unittest.main()
