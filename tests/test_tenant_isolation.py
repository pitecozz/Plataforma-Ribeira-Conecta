from __future__ import annotations

import unittest

from ribeira_platform.service import RibeiraApplication
from ribeira_platform.storage import SQLiteStore


class TenantIsolationTests(unittest.TestCase):
    def test_cross_tenant_property_is_invisible(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        tenant_a = app.create_tenant("A")
        tenant_b = app.create_tenant("B")
        property_a = app.create_property(tenant_a.id, "A property")
        self.assertIsNotNone(store.get_property(tenant_a.id, property_a.id))
        self.assertIsNone(store.get_property(tenant_b.id, property_a.id))
        with self.assertRaises(LookupError):
            app.evaluate(tenant_b.id, property_a.id)
        store.close()

    def test_property_cannot_be_created_for_unknown_tenant(self) -> None:
        store = SQLiteStore()
        app = RibeiraApplication(store)
        with self.assertRaises(PermissionError):
            app.create_property("missing-tenant", "should fail")
        store.close()


if __name__ == "__main__":
    unittest.main()
