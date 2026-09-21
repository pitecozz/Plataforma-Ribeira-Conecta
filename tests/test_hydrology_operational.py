from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from ribeira_platform.hydrology_operational import reconciliation_window


class OperationalHydrologyTests(unittest.TestCase):
    def test_operational_window_has_required_three_hour_overlap(self) -> None:
        now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
        start, end = reconciliation_window(now=now, historical=False, lookback_hours=3)
        self.assertEqual(end, now)
        self.assertEqual(end - start, timedelta(hours=3))

    def test_historical_window_is_fixed_to_september_event_start(self) -> None:
        now = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
        start, end = reconciliation_window(now=now, historical=True, lookback_hours=3)
        self.assertEqual(start, datetime(2026, 9, 1, tzinfo=timezone.utc))
        self.assertEqual(end, now)

    def test_invalid_window_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            reconciliation_window(
                now=datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
                historical=False,
                lookback_hours=2,
            )


if __name__ == "__main__":
    unittest.main()
