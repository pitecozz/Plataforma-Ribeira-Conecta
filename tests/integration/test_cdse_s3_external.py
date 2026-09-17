from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from ribeira_platform.cdse_s3 import CdseS3AssetAdapter, CdseS3Config
from ribeira_platform.geospatial import (
    BandResolver,
    SatelliteAsset,
    SatelliteSearchRequest,
    SceneSelectionPolicy,
)
from ribeira_platform.geospatial_provider import (
    CopernicusStacAdapter,
    default_copernicus_registry,
)
from ribeira_platform.object_storage import LocalObjectStorage
from ribeira_platform.raster_processing import NdviProcessor, validate_cog


@unittest.skipUnless(
    os.getenv("RIBEIRA_CDSE_S3_EXTERNAL_TEST") == "1",
    "set RIBEIRA_CDSE_S3_EXTERNAL_TEST=1 to run authenticated CDSE S3 test",
)
class CdseS3ExternalTests(unittest.TestCase):
    def test_real_sentinel2_assets_produce_real_ndvi_for_test_aoi(self) -> None:
        if not os.getenv("CDSE_S3_ACCESS_KEY") or not os.getenv("CDSE_S3_SECRET_KEY"):
            self.skipTest("CDSE S3 credentials are not configured")
        catalog = CopernicusStacAdapter(default_copernicus_registry())
        request = SatelliteSearchRequest(
            property_id="TEST_AOI_ONLY",
            collection_id="sentinel-2-l2a",
            datetime_start="2025-01-01T00:00:00Z",
            datetime_end="2025-12-31T23:59:59Z",
            selection_policy=SceneSelectionPolicy(max_candidates=10),
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
        search = catalog.search(request, aoi)

        def resolve_item(candidate: dict) -> dict[str, str] | None:
            try:
                return BandResolver.resolve(
                    {
                        str(key): {
                            "title": value.get("title"),
                            "roles": value.get("roles", []),
                        }
                        for key, value in (candidate.get("assets") or {}).items()
                        if isinstance(value, dict)
                    }
                )
            except ValueError:
                return None

        item = next(
            (candidate for candidate in search.items if resolve_item(candidate)), None
        )
        self.assertIsNotNone(item, "no live item exposed validated RED/NIR assets")
        assert item is not None
        roles = resolve_item(item)
        assert roles is not None
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        storage = LocalObjectStorage(Path(tmp.name), max_object_bytes=500_000_000)
        adapter = CdseS3AssetAdapter(storage, config=CdseS3Config.from_environment())
        assets: list[SatelliteAsset] = []
        bytes_total = 0
        started = time.perf_counter()
        for semantic_key in ("red", "nir"):
            key = roles[semantic_key]
            raw = item["assets"][key]
            href = raw.get("href")
            self.assertIsInstance(href, str)
            result = adapter.download(
                href,
                f"external-test/{item['id']}/{key}.jp2",
                max_job_bytes=1_000_000_000 - bytes_total,
            )
            self.assertEqual(result.status.value, "SUCCEEDED", result.failure_code)
            self.assertIsNotNone(result.local_reference)
            bytes_total += result.bytes_downloaded
            assets.append(
                SatelliteAsset(
                    id=f"TEST_{key}",
                    tenant_id="TEST_TENANT_ONLY",
                    scene_id="TEST_SCENE_ONLY",
                    asset_key=key,
                    href=result.local_reference or "",
                    media_type=raw.get("type"),
                    roles=list(raw.get("roles", [])),
                    title=raw.get("title"),
                    band_metadata=raw,
                    size_bytes=result.size_bytes,
                    checksum_local=result.checksum_local,
                    checksum_algorithm=result.checksum_algorithm,
                )
            )
        output = NdviProcessor(storage).process(assets, aoi, "external-test/ndvi.tif")
        self.assertGreater(output.statistics.valid_count, 0)
        self.assertIsNotNone(output.output_checksum)
        validate_cog(storage.read_local_path(output.output_reference))
        self.assertGreaterEqual(output.statistics.minimum or -2, -1)
        self.assertLessEqual(output.statistics.maximum or 2, 1)
        print(
            "Observed CDSE S3/NDVI metrics: "
            f"bytes={bytes_total}; elapsed={time.perf_counter() - started:.3f}s; "
            f"valid_pixels={output.statistics.valid_count}"
        )
