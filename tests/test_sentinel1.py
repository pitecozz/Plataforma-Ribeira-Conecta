from __future__ import annotations

from datetime import datetime, timezone
import unittest

from ribeira_platform.sentinel1 import select_comparable_pair


def item(identifier: str, acquired: str, orbit: int = 53) -> dict[str, object]:
    return {
        "id": identifier,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        },
        "properties": {
            "datetime": acquired,
            "sar:instrument_mode": "IW",
            "sat:orbit_state": "descending",
            "sat:relative_orbit": orbit,
            "sar:polarizations": ["VH", "VV"],
        },
    }


class Sentinel1SelectionTests(unittest.TestCase):
    def test_selects_matching_orbit_mode_and_polarization(self) -> None:
        selected = select_comparable_pair(
            [
                item("pre", "2026-09-07T08:00:00Z"),
                item("event", "2026-09-13T08:00:00Z"),
                item("different", "2026-09-13T09:00:00Z", 126),
            ],
            event_start=datetime(2026, 9, 11, tzinfo=timezone.utc),
            event_end=datetime(2026, 9, 20, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            (selected[0].provider_record_id, selected[1].provider_record_id),
            ("pre", "event"),
        )

    def test_fails_closed_without_comparable_pair(self) -> None:
        self.assertIsNone(
            select_comparable_pair(
                [
                    item("pre", "2026-09-07T08:00:00Z"),
                    item("event", "2026-09-13T08:00:00Z", 126),
                ],
                event_start=datetime(2026, 9, 11, tzinfo=timezone.utc),
                event_end=datetime(2026, 9, 20, tzinfo=timezone.utc),
            )
        )
