from __future__ import annotations

from datetime import datetime, timezone
import unittest

from ribeira_platform.sentinel1_discovery import (
    EventWindow,
    assess_scene,
    build_pairs,
    derive_event_window,
)


UTC = timezone.utc
REGISTRO = {
    "type": "Polygon",
    "coordinates": [
        [[-47.1, -24.1], [-46.9, -24.1], [-46.9, -23.9], [-47.1, -23.9], [-47.1, -24.1]]
    ],
}


def item(
    identifier: str, when: str, geometry: dict[str, object] = REGISTRO, orbit: int = 126
):
    return {
        "id": identifier,
        "geometry": geometry,
        "properties": {
            "datetime": when,
            "platform": "sentinel-1c",
            "sar:instrument_mode": "IW",
            "sat:orbit_state": "descending",
            "sat:relative_orbit": orbit,
            "sat:absolute_orbit": 1,
            "sar:polarizations": ["VV", "VH"],
            "product:type": "IW_GRDH_1S",
        },
    }


class Sentinel1DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = EventWindow(
            datetime(2026, 9, 11, tzinfo=UTC),
            datetime(2026, 9, 14, tzinfo=UTC),
            (),
        )

    def test_event_window_uses_factual_entries_and_ignores_climate(self) -> None:
        window = derive_event_window(
            [
                {
                    "event_type": "CLIMATE_CONTEXT",
                    "occurred_at": datetime(2026, 9, 1, tzinfo=UTC),
                },
                {
                    "event_type": "RESERVOIR_OPERATION",
                    "occurred_at": datetime(2026, 9, 11, tzinfo=UTC),
                },
                {
                    "event_type": "RAINFALL_ACCUMULATION_PEAK",
                    "occurred_at": datetime(2026, 9, 12, tzinfo=UTC),
                },
                {
                    "event_type": "EVENT_PRIORITY",
                    "occurred_at": datetime(2026, 9, 14, tzinfo=UTC),
                },
                {
                    "event_type": "RAINFALL_ACCUMULATION_PEAK",
                    "occurred_at": datetime(2026, 9, 14, 20, tzinfo=UTC),
                },
            ]
        )
        self.assertEqual(window.start, datetime(2026, 9, 11, tzinfo=UTC))
        self.assertEqual(window.end, datetime(2026, 9, 14, 20, tzinfo=UTC))

    def test_exact_intersection_rejects_bbox_false_positive(self) -> None:
        concave_registro = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-47.1, -24.1],
                    [-46.9, -24.1],
                    [-46.9, -23.9],
                    [-46.95, -23.9],
                    [-46.95, -24.05],
                    [-47.05, -24.05],
                    [-47.05, -23.9],
                    [-47.1, -23.9],
                    [-47.1, -24.1],
                ]
            ],
        }
        scene_in_concavity = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-47.04, -24.04],
                    [-46.96, -24.04],
                    [-46.96, -23.91],
                    [-47.04, -23.91],
                    [-47.04, -24.04],
                ]
            ],
        }
        assessment = assess_scene(
            item("outside", "2026-09-06T00:00:00Z", scene_in_concavity),
            concave_registro,
            self.window,
        )
        self.assertEqual(assessment.coverage_km2, 0.0)
        self.assertEqual(assessment.pre_classification, "REJECTED")

    def test_scene_classification_and_common_coverage_pair_ranking(self) -> None:
        scenes = [
            assess_scene(item("pre", "2026-09-06T00:00:00Z"), REGISTRO, self.window),
            assess_scene(item("event", "2026-09-12T00:00:00Z"), REGISTRO, self.window),
            assess_scene(item("late", "2026-09-18T00:00:00Z"), REGISTRO, self.window),
        ]
        pairs = build_pairs(scenes, REGISTRO, self.window)
        self.assertEqual(scenes[0].pre_classification, "GOOD_PRE")
        self.assertEqual(scenes[1].event_classification, "GOOD_EVENT")
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0].pre.scene.provider_record_id, "pre")
        self.assertEqual(pairs[0].event.scene.provider_record_id, "event")
        self.assertGreater(pairs[0].common_coverage_km2, 0)
        self.assertEqual(pairs[0].rank_order, 1)

    def test_orbit_and_polarization_incompatibility_do_not_pair(self) -> None:
        pre = assess_scene(item("pre", "2026-09-06T00:00:00Z"), REGISTRO, self.window)
        incompatible = item("event", "2026-09-12T00:00:00Z", orbit=53)
        assessments = [pre, assess_scene(incompatible, REGISTRO, self.window)]
        self.assertEqual(build_pairs(assessments, REGISTRO, self.window), [])
