from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from ribeira_platform.hydrology import (
    AnaHidroWebAdapter,
    HydroFetchStatus,
    HydroObservationInput,
    HydroStationInput,
    HydroVariable,
    SaispPublicAdapter,
    observation_deduplication_key,
    observation_quality_issues,
    parse_copel_capivari_notice,
    parse_noaa_cpc_enso,
    rainfall_accumulations,
    rate_of_rise,
    river_stage_deltas,
    station_quality_issues,
)


UTC = timezone.utc


class HydrologyCoreTests(unittest.TestCase):
    def observation(
        self, variable: HydroVariable, observed_at: datetime, value: float, unit: str
    ) -> HydroObservationInput:
        return HydroObservationInput(
            "station-1", "TEST", variable, observed_at, value, unit
        )

    def test_station_identity_and_coordinate_quality(self) -> None:
        valid = HydroStationInput("ANA", "123", "Station", "TELEMETRIC", -24.0, -48.0)
        invalid = HydroStationInput("ANA", "123", "Station", "TELEMETRIC", 99.0, -48.0)
        self.assertEqual(station_quality_issues(valid), frozenset())
        self.assertIn("INVALID_COORDINATE", station_quality_issues(invalid))

    def test_observation_deduplication_and_quality_markers(self) -> None:
        now = datetime(2026, 9, 21, tzinfo=UTC)
        item = self.observation(HydroVariable.RAINFALL, now, -1.0, "mm")
        self.assertEqual(observation_deduplication_key(item)[0], "station-1")
        issues = observation_quality_issues(
            item, now=now, stale_after=timedelta(hours=1), conflicting_provider=True
        )
        self.assertEqual(issues, frozenset({"NEGATIVE_RAINFALL", "PROVIDER_CONFLICT"}))
        unsupported = self.observation(HydroVariable.DISCHARGE, now, 2.0, "mm")
        self.assertIn(
            "UNSUPPORTED_UNIT", observation_quality_issues(unsupported, now=now)
        )
        future = self.observation(
            HydroVariable.RIVER_STAGE, now + timedelta(minutes=1), 2.0, "m"
        )
        self.assertIn("FUTURE_TIMESTAMP", observation_quality_issues(future, now=now))

    def test_rain_accumulation_preserves_missing_as_none(self) -> None:
        end = datetime(2026, 9, 21, 12, tzinfo=UTC)
        samples = [
            self.observation(
                HydroVariable.RAINFALL, end - timedelta(minutes=30), 4.0, "mm"
            ),
            self.observation(
                HydroVariable.RAINFALL, end - timedelta(hours=2), 6.0, "mm"
            ),
        ]
        totals = rainfall_accumulations(samples, end_at=end)
        self.assertEqual(totals[1], 4.0)
        self.assertEqual(totals[3], 10.0)
        self.assertIsNone(rainfall_accumulations([], end_at=end)[24])

    def test_stage_delta_requires_exact_evidence_and_rate_is_not_imputed(self) -> None:
        end = datetime(2026, 9, 21, 12, tzinfo=UTC)
        samples = [
            self.observation(HydroVariable.RIVER_STAGE, end, 2.4, "m"),
            self.observation(
                HydroVariable.RIVER_STAGE, end - timedelta(hours=1), 2.0, "m"
            ),
        ]
        delta = river_stage_deltas(samples, end_at=end)
        self.assertAlmostEqual(delta["1h"] or 0, 0.4)
        self.assertIsNone(delta["3h"])
        self.assertAlmostEqual(
            rate_of_rise(delta["1h"], timedelta(hours=1)) or 0, 0.4 / 3600
        )
        self.assertIsNone(rate_of_rise(None, timedelta(hours=1)))

    def test_auth_and_unavailable_adapters_do_not_fabricate_data(self) -> None:
        self.assertEqual(
            AnaHidroWebAdapter().list_stations().status, HydroFetchStatus.AUTH_REQUIRED
        )
        self.assertEqual(
            SaispPublicAdapter().fetch_observations().status,
            HydroFetchStatus.SOURCE_UNAVAILABLE,
        )

    def test_copel_parser_only_keeps_explicit_gate_fact(self) -> None:
        notice = """{"datePublished":"2026-09-11T10:00:00-03:00"}
        A usina de Capivari aumentou a abertura das comportas."""
        event = parse_copel_capivari_notice(
            notice, "https://www.copel.com/site/noticias/example/"
        )
        self.assertEqual(event.event_type, "GATE_OPENING")
        self.assertIsNone(event.numeric_value)
        self.assertEqual(event.classification, "OFFICIAL_SOURCE")

    def test_noaa_parser_keeps_climate_as_context(self) -> None:
        text = "Issued on 10 September 2026. El Niño has a 90% chance during ASO 2026 and may be very strong."
        context = parse_noaa_cpc_enso(
            text, "https://www.cpc.ncep.noaa.gov/products/example"
        )
        self.assertEqual(context.enso_state, "EL_NINO")
        self.assertEqual(context.probability, 90.0)
        self.assertEqual(context.valid_window, "ASO 2026")


if __name__ == "__main__":
    unittest.main()
