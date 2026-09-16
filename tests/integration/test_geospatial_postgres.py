from __future__ import annotations

import json
import os
import unittest

import psycopg

from ribeira_platform.geospatial import SatelliteCollection, SatelliteScene
from ribeira_platform.models import new_id
from ribeira_platform.postgres import PostgresStore
from ribeira_platform.service import RibeiraApplication


DATABASE_URL = os.getenv("RIBEIRA_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "RIBEIRA_TEST_DATABASE_URL is required")
class GeospatialPostgresTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = PostgresStore(DATABASE_URL)  # type: ignore[arg-type]
        self.application = RibeiraApplication(self.store)
        self.repo = self.application.geospatial.repository

    def tearDown(self) -> None:
        self.store.close()

    def test_postgis_scene_and_rls_block_cross_tenant_access(self) -> None:
        tenant_a = self.application.create_tenant("Geo A")
        tenant_b = self.application.create_tenant("Geo B")
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-47.1, -24.1],
                    [-47.0, -24.1],
                    [-47.0, -24.0],
                    [-47.1, -24.0],
                    [-47.1, -24.1],
                ]
            ],
        }
        property_a = self.application.create_property(
            tenant_a.id, "AOI A", polygon, "EPSG:4326"
        )
        collection = SatelliteCollection(
            id="",
            provider_id="COPERNICUS_CDSE",
            external_collection_id="sentinel-2-l2a",
            title="Sentinel-2 Level-2A",
            mission="Sentinel-2",
            processing_level="L2A",
            spatial_resolution="[10,20,60]",
            temporal_characteristics={},
            bands={},
            license="other",
            stac_version="1.1.0",
            metadata={"test": True},
        )
        scene = SatelliteScene(
            id=new_id(),
            tenant_id=tenant_a.id,
            property_id=property_a.id,
            provider_id="COPERNICUS_CDSE",
            collection_id="sentinel-2-l2a",
            external_item_id="RLS_TEST_ITEM",
            acquisition_datetime="2025-01-01T00:00:00+00:00",
            provider_published_datetime=None,
            geometry_geojson=polygon,
            bbox=[-47.1, -24.1, -47.0, -24.0],
            cloud_cover=None,
            platform="sentinel-2a",
            constellation="sentinel-2",
            processing_level="L2A",
            stac_version="1.1.0",
            raw_metadata_reference="local://test/raw.json",
            checksum="test-checksum",
        )
        with self.store.tenant_transaction(tenant_a.id):
            self.repo.upsert_collection(collection)
            stored = self.repo.upsert_scene(scene)
            self.assertEqual(stored.id, scene.id)
            row = self.store.connection.execute(
                "SELECT ST_SRID(geometry) AS srid FROM satellite_scene WHERE id=%s",
                (scene.id,),
            ).fetchone()
            self.assertEqual(row["srid"], 4326)

        with self.store.tenant_transaction(tenant_b.id):
            self.assertIsNone(
                self.store.connection.execute(
                    "SELECT id FROM satellite_scene WHERE id=%s", (scene.id,)
                ).fetchone()
            )
            self.assertEqual(
                self.store.connection.execute(
                    "UPDATE satellite_scene SET platform='tampered' WHERE id=%s",
                    (scene.id,),
                ).rowcount,
                0,
            )
            self.assertEqual(
                self.store.connection.execute(
                    "DELETE FROM satellite_scene WHERE id=%s", (scene.id,)
                ).rowcount,
                0,
            )

        with self.assertRaises(psycopg.Error):
            with self.store.tenant_transaction(tenant_b.id):
                self.store.connection.execute(
                    "INSERT INTO satellite_asset(id,tenant_id,scene_id,asset_key,href) VALUES (%s,%s,%s,%s,%s)",
                    (new_id(), tenant_b.id, scene.id, "B04_10m", "s3://not-used"),
                )

        with self.assertRaises(psycopg.Error):
            with self.store.tenant_transaction(tenant_b.id):
                self.store.connection.execute(
                    "INSERT INTO evidence(id,tenant_id,evidence_type,reference_id,data_classification,limitations) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        new_id(),
                        tenant_b.id,
                        "SATELLITE_SCENE",
                        scene.id,
                        "OFFICIAL_SOURCE",
                        json.dumps([]),
                    ),
                )


if __name__ == "__main__":
    unittest.main()
