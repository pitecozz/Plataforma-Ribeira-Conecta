"""API tests for the source-backed non-legal field/talhão workflow."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from shapely.geometry import Polygon, mapping

from ribeira_platform.api import Settings, create_app
from ribeira_platform.iam import AuthContext, DevelopmentIdentityProvider
from ribeira_platform.service import RibeiraApplication
from ribeira_platform.storage import SQLiteStore


class FieldContextApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteStore()
        self.application = RibeiraApplication(self.store)
        self.tenant = self.application.create_tenant("Synthetic API tenant")
        self.other_tenant = self.application.create_tenant("Other API tenant")
        self.property = self.application.create_property(
            self.tenant.id,
            "TEST_PROPERTY_ONLY",
            mapping(Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])),
            "EPSG:4326",
        )
        settings = Settings("test", "sqlite", None, (), "development", 1_000_000)
        self.client = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "admin",
                    AuthContext(
                        "admin",
                        None,
                        roles=frozenset({"PLATFORM_ADMIN"}),
                        is_platform_admin=True,
                    ),
                ),
                settings=settings,
            )
        )
        self.denied_client = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "viewer",
                    AuthContext(
                        "viewer", self.other_tenant.id, roles=frozenset({"VIEWER"})
                    ),
                ),
                settings=settings,
            )
        )
        self.viewer_client = TestClient(
            create_app(
                self.application,
                DevelopmentIdentityProvider(
                    "viewer",
                    AuthContext("viewer", self.tenant.id, roles=frozenset({"VIEWER"})),
                ),
                settings=settings,
            )
        )

    def tearDown(self) -> None:
        self.store.close()

    def payload(self) -> dict:
        return {
            "name": "TEST_FIELD_ONLY",
            "status": "ACTIVE",
            "geometry_geojson": mapping(
                Polygon([(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8), (0.2, 0.2)])
            ),
            "geometry_crs": "EPSG:4326",
            "source_reference": "synthetic_test_data field walk",
            "observed_at": "2026-09-24T12:00:00+00:00",
            "classification": "MANUAL_CONFIRMED",
        }

    def test_registers_lists_and_scopes_field_context(self) -> None:
        path = f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/fields"
        response = self.client.post(
            path, headers={"Authorization": "Bearer admin"}, json=self.payload()
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["boundary_version"], 1)
        self.assertIsNotNone(response.json()["evidence_id"])

        listed = self.client.get(path, headers={"Authorization": "Bearer admin"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listed.json()["items"]], [response.json()["id"]]
        )

        denied = self.denied_client.get(
            path, headers={"Authorization": "Bearer viewer"}
        )
        self.assertEqual(denied.status_code, 403)

    def test_corrects_boundary_and_requires_property_write(self) -> None:
        path = f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/fields"
        created = self.client.post(
            path, headers={"Authorization": "Bearer admin"}, json=self.payload()
        )
        correction_path = f"{path}/{created.json()['id']}/boundary-corrections"
        correction = {
            "geometry_geojson": mapping(
                Polygon([(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75), (0.25, 0.25)])
            ),
            "geometry_crs": "EPSG:4326",
            "source_reference": "synthetic corrected field walk",
            "observed_at": "2026-09-25T12:00:00+00:00",
            "classification": "MANUAL_CONFIRMED",
            "reason": "synthetic operator correction",
        }
        denied = self.viewer_client.post(
            correction_path,
            headers={"Authorization": "Bearer viewer"},
            json=correction,
        )
        self.assertEqual(denied.status_code, 403)

        response = self.client.post(
            correction_path,
            headers={"Authorization": "Bearer admin"},
            json=correction,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["boundary_version"], 2)
        self.assertIsNotNone(response.json()["evidence_id"])
        listed = self.client.get(path, headers={"Authorization": "Bearer admin"})
        self.assertEqual(listed.json()["items"][0]["boundary_version"], 2)

    def test_rejects_blank_source_at_request_validation(self) -> None:
        path = f"/v1/tenants/{self.tenant.id}/properties/{self.property.id}/fields"
        response = self.client.post(
            path,
            headers={"Authorization": "Bearer admin"},
            json={**self.payload(), "source_reference": "  "},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
