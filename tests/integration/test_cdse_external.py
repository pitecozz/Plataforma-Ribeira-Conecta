from __future__ import annotations

import os
import time
import unittest

from ribeira_platform.geospatial import SceneSelectionPolicy, SatelliteSearchRequest
from ribeira_platform.geospatial_provider import (
    CopernicusStacAdapter,
    default_copernicus_registry,
)


@unittest.skipUnless(
    os.getenv("RIBEIRA_CDSE_EXTERNAL_TEST") == "1",
    "set RIBEIRA_CDSE_EXTERNAL_TEST=1 to run the controlled CDSE test",
)
class CdseExternalTests(unittest.TestCase):
    def test_official_stac_collection_and_real_scene_discovery(self) -> None:
        adapter = CopernicusStacAdapter(default_copernicus_registry())
        collection = adapter.get_collection("sentinel-2-l2a")
        self.assertEqual(collection.external_collection_id, "sentinel-2-l2a")
        self.assertEqual(collection.stac_version, "1.1.0")
        request = SatelliteSearchRequest(
            property_id="TEST_AOI_ONLY",
            collection_id="sentinel-2-l2a",
            datetime_start="2025-01-01T00:00:00Z",
            datetime_end="2025-12-31T23:59:59Z",
            selection_policy=SceneSelectionPolicy(max_candidates=5),
        )
        aoi = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-47.0, -24.0],
                    [-46.99, -24.0],
                    [-46.99, -23.99],
                    [-47.0, -23.99],
                    [-47.0, -24.0],
                ]
            ],
        }
        started = time.perf_counter()
        result = adapter.search(request, aoi)
        elapsed = time.perf_counter() - started
        self.assertGreater(len(result.items), 0)
        self.assertGreater(len(result.raw_pages), 0)
        self.assertTrue(all(isinstance(item.get("id"), str) for item in result.items))
        # This is an observed test measurement, not a product SLA.
        print(
            f"CDSE STAC search observed latency: {elapsed:.3f}s; items={len(result.items)}"
        )


if __name__ == "__main__":
    unittest.main()
