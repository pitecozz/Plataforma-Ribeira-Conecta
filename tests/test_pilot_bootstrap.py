"""Private pilot package parsing is strict before any database operation."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from ribeira_platform.pilot_bootstrap import BootstrapError, load_plan


BOUNDARY = {
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
}


def feature(name: str, kind: str, geometry: dict[str, object], **extra: object):
    return {
        "type": "Feature",
        "properties": {
            "name": name,
            "entity_kind": kind,
            "crs": "EPSG:4326",
            "source": "USER_PROVIDED_GOOGLE_EARTH_KML",
            "classification": "MANUAL_CONFIRMED",
            **extra,
        },
        "geometry": geometry,
    }


class PilotBootstrapPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manifest_path = self.root / "manifest.json"
        self.geojson_path = self.root / "pilot.geojson"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, manifest: dict[str, object], geojson: dict[str, object]) -> None:
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.geojson_path.write_text(json.dumps(geojson), encoding="utf-8")
        os.chmod(self.manifest_path, 0o600)
        os.chmod(self.geojson_path, 0o600)

    def package(self) -> tuple[dict[str, object], dict[str, object]]:
        manifest: dict[str, object] = {
            "pilot_customer_label": "SYNTHETIC TEST CUSTOMER",
            "property_name": "SYNTHETIC TEST PROPERTY",
            "source": "USER_PROVIDED_GOOGLE_EARTH_KML",
            "crs": "EPSG:4326",
            "boundary": {
                "placemark_name": "SYNTHETIC BOUNDARY",
                "confirmed_by_operator": True,
                "legal_boundary_verified": False,
                "intended_use": "operational_analysis_boundary",
            },
            "included_assets": ["SYNTHETIC HOUSE", "SYNTHETIC CAMERA"],
            "excluded_features": {
                "unresolved marker": "synthetic test exclusion",
            },
        }
        geojson: dict[str, object] = {
            "type": "FeatureCollection",
            "features": [
                feature(
                    "SYNTHETIC BOUNDARY",
                    "property_boundary",
                    BOUNDARY,
                    usage="operational_analysis_boundary",
                    legal_boundary_verified=False,
                ),
                feature(
                    "SYNTHETIC HOUSE",
                    "asset",
                    {"type": "Point", "coordinates": [-46.999, -24.001]},
                    asset_type="house_building",
                ),
                feature(
                    "SYNTHETIC CAMERA",
                    "asset",
                    {"type": "Point", "coordinates": [-46.998, -24.002]},
                    asset_type="camera",
                ),
            ],
        }
        return manifest, geojson

    def test_plan_is_deterministic_and_preserves_boundary_limitations(self) -> None:
        manifest, geojson = self.package()
        self.write(manifest, geojson)
        first = load_plan(self.manifest_path, self.geojson_path)
        second = load_plan(self.manifest_path, self.geojson_path)
        self.assertEqual(first.tenant_id, second.tenant_id)
        self.assertEqual(first.property_id, second.property_id)
        self.assertFalse(first.legal_boundary_verified)
        self.assertEqual(first.boundary_usage, "operational_analysis_boundary")
        self.assertEqual(
            [asset.name for asset in first.assets], manifest["included_assets"]
        )
        self.assertEqual(first.excluded_feature_names, ("unresolved marker",))

    def test_unapproved_geojson_feature_is_rejected_before_any_write(self) -> None:
        manifest, geojson = self.package()
        features = geojson["features"]  # type: ignore[index]
        assert isinstance(features, list)
        features.append(
            feature(
                "SYNTHETIC UNAPPROVED",
                "asset",
                {"type": "Point", "coordinates": [-46.997, -24.003]},
                asset_type="unknown",
            )
        )
        self.write(manifest, geojson)
        with self.assertRaisesRegex(BootstrapError, "exactly match manifest"):
            load_plan(self.manifest_path, self.geojson_path)

    def test_non_private_input_file_is_rejected(self) -> None:
        manifest, geojson = self.package()
        self.write(manifest, geojson)
        os.chmod(self.geojson_path, 0o644)
        with self.assertRaisesRegex(BootstrapError, "not private"):
            load_plan(self.manifest_path, self.geojson_path)
