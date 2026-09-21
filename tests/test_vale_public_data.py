from __future__ import annotations

from datetime import datetime, timezone
import unittest

from ribeira_platform.vale_public_data import (
    InmetWis2HttpProvider,
    WIS2_PRECIPITATION_NAME,
    parse_phenomenon_time,
    parse_sidra_baselines,
    parse_sidra_metadata,
    parse_sidra_value,
)


UTC = timezone.utc


def sidra_metadata() -> dict[str, object]:
    return {
        "variaveis": [
            {"id": 1, "nome": "Área destinada à colheita", "unidade": "Hectares"},
            {"id": 2, "nome": "Área colhida", "unidade": "Hectares"},
            {"id": 3, "nome": "Quantidade produzida", "unidade": "Toneladas"},
            {"id": 4, "nome": "Rendimento médio da produção", "unidade": "Quilogramas por Hectare"},
            {"id": 5, "nome": "Valor da produção", "unidade": "Mil Reais"},
        ],
        "classificacoes": [
            {
                "id": 82,
                "nome": "Produto das lavouras permanentes",
                "categorias": [{"id": 2720, "nome": "Banana (cacho)"}],
            }
        ],
    }


def wis2_feature(*, value: object = 0.0, name: str = WIS2_PRECIPITATION_NAME) -> dict[str, object]:
    return {
        "id": "record-1",
        "geometry": {"type": "Point", "coordinates": [-47.0, -24.0]},
        "properties": {
            "id": "record-1",
            "name": name,
            "description": "official station",
            "wigos_station_identifier": "0-76-0-test",
            "phenomenonTime": "2026-09-21T10:00:00Z/2026-09-21T11:00:00Z",
            "reportTime": "2026-09-21T11:05:00Z",
            "units": "kg m-2",
            "value": value,
        },
    }


class Wis2AndSidraTests(unittest.TestCase):
    def test_interval_and_instant_phenomenon_time_preserve_semantics(self) -> None:
        start, end = parse_phenomenon_time("2026-09-21T10:00:00Z/2026-09-21T11:00:00Z")
        self.assertEqual(end - start, __import__("datetime").timedelta(hours=1))
        instant_start, instant_end = parse_phenomenon_time("2026-09-21T11:00:00Z")
        self.assertEqual(instant_start, instant_end)

    def test_exact_precipitation_preserves_raw_and_calculates_mm(self) -> None:
        record = InmetWis2HttpProvider.parse_feature(
            wis2_feature(value=0.0), source_url="https://wis2bra.inmet.gov.br/example"
        )
        assert record is not None
        self.assertEqual(record.raw_unit, "kg m-2")
        self.assertEqual(record.raw_value, 0.0)
        self.assertEqual(record.normalized_mm, 0.0)
        self.assertEqual(record.period_end, datetime(2026, 9, 21, 11, tzinfo=UTC))

    def test_unknown_variable_is_rejected_and_missing_is_not_zero(self) -> None:
        self.assertIsNone(
            InmetWis2HttpProvider.parse_feature(
                wis2_feature(name="unrelated_water_variable"),
                source_url="https://wis2bra.inmet.gov.br/example",
            )
        )
        record = InmetWis2HttpProvider.parse_feature(
            wis2_feature(value=None), source_url="https://wis2bra.inmet.gov.br/example"
        )
        assert record is not None
        self.assertIsNone(record.raw_value)
        with self.assertRaises(ValueError):
            InmetWis2HttpProvider.parse_feature(
                wis2_feature(value=-1), source_url="https://wis2bra.inmet.gov.br/example"
            )

    def test_pagination_follows_only_provider_next_link_and_stays_bounded(self) -> None:
        class FixtureProvider(InmetWis2HttpProvider):
            def __init__(self) -> None:
                super().__init__()
                self.urls: list[str] = []

            def _get_json(self, url: str):  # type: ignore[override]
                self.urls.append(url)
                if len(self.urls) == 1:
                    return {
                        "features": [wis2_feature(value=1.0)],
                        "links": [{"rel": "next", "href": "https://wis2bra.inmet.gov.br/next"}],
                    }
                return {"features": [wis2_feature(value=2.0)], "links": []}

        provider = FixtureProvider()
        records, examined, supported = provider.discover_rain(
            bbox=(-48.0, -25.0, -47.0, -24.0), max_pages=2, max_records=2
        )
        self.assertTrue(supported)
        self.assertEqual(examined, 2)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(provider.urls), 2)

    def test_sidra_metadata_and_values_are_fail_closed(self) -> None:
        metadata = parse_sidra_metadata(sidra_metadata(), [{"id": "2025"}])
        self.assertEqual(metadata.category_label, "Banana (cacho)")
        self.assertEqual(metadata.variables["production"].unit, "Toneladas")
        rows = [
            {"NC": "Nível Territorial (Código)"},
            *[
                {
                    "NC": "6", "D1C": "123", "D2C": variable.identifier,
                    "D2N": variable.label, "D3C": "2025", "D4C": metadata.category_id,
                    "D4N": metadata.category_label, "MN": variable.unit, "V": "0",
                }
                for variable in metadata.variables.values()
            ],
        ]
        parsed = parse_sidra_baselines(rows, metadata)
        self.assertEqual(parsed["123"]["states"]["production"], "ZERO")
        self.assertEqual(parse_sidra_value("X").state, "SUPPRESSED")
        self.assertEqual(parse_sidra_value("-").state, "NOT_APPLICABLE")
        self.assertEqual(parse_sidra_value("..").state, "NOT_AVAILABLE")
        self.assertEqual(parse_sidra_value("...").state, "MISSING")
        with self.assertRaises(ValueError):
            parse_sidra_value("unexpected-marker")

    def test_ambiguous_banana_category_fails_closed(self) -> None:
        payload = sidra_metadata()
        classifications = payload["classificacoes"]
        assert isinstance(classifications, list)
        category = classifications[0]["categorias"][0]  # type: ignore[index]
        classifications[0]["categorias"].append(dict(category))  # type: ignore[index]
        with self.assertRaises(ValueError):
            parse_sidra_metadata(payload, [{"id": "2025"}])


if __name__ == "__main__":
    unittest.main()
