"""Bounded, fail-closed clients for official Vale public-data sources.

The clients deliberately keep transport and parsing separate from persistence.
They use only published HTTPS endpoints, retain source semantics, and do not
turn unavailable or malformed values into estimates.
"""

from __future__ import annotations

import gzip
import json
import math
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WIS2_COLLECTION = "urn:wmo:md:br-inmet:synop"
WIS2_HOST = "wis2bra.inmet.gov.br"
WIS2_ITEMS_URL = f"https://{WIS2_HOST}/oapi/collections/{WIS2_COLLECTION}/items"
WIS2_PRECIPITATION_NAME = "total_precipitation_or_total_water_equivalent"
WIS2_RAW_RAIN_UNIT = "kg m-2"
SIDRA_METADATA_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/1613/metadados"
SIDRA_PERIODS_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/1613/periodos"
SIDRA_VALUES_BASE_URL = "https://apisidra.ibge.gov.br/values"


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("provider timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def parse_phenomenon_time(value: object) -> tuple[datetime, datetime]:
    """Return an explicit interval; an instant becomes a zero-length interval."""
    if not isinstance(value, str) or not value:
        raise ValueError("phenomenonTime is required")
    pieces = value.split("/")
    if len(pieces) == 1:
        moment = _utc(pieces[0])
        return moment, moment
    if len(pieces) != 2 or not all(pieces):
        raise ValueError("phenomenonTime must be an instant or start/end interval")
    start, end = _utc(pieces[0]), _utc(pieces[1])
    if end < start:
        raise ValueError("phenomenonTime ends before it starts")
    return start, end


@dataclass(frozen=True)
class Wis2RainRecord:
    provider_record_id: str
    wigos_station_identifier: str
    station_name: str
    longitude: float
    latitude: float
    period_start: datetime
    period_end: datetime
    report_time: datetime
    raw_value: float | None
    raw_unit: str
    source_url: str

    @property
    def normalized_mm(self) -> float | None:
        # WIS2 metadata identifies this field as total water equivalent. For
        # liquid-water depth kg m-2 is numerically equal to mm.
        return self.raw_value


class InmetWis2HttpProvider:
    """Official INMET WIS2 HTTP OGC API client with strict bounded paging."""

    parser_version = "inmet_wis2_http_v1"

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 2_000_000,
        max_retries: int = 2,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_retries = max_retries

    def _get_json(self, url: str) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != WIS2_HOST:
            raise ValueError("WIS2 URL is outside the approved official host")
        request = Request(
            url,
            headers={
                "Accept": "application/geo+json,application/json",
                "User-Agent": "RibeiraConecta/1.0 official-public-data",
            },
        )
        raw: bytes | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 -- fixed official host above
                    raw = response.read(self.max_response_bytes + 1)
                break
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = min(float(retry_after), 30.0) if retry_after and retry_after.isdigit() else min(2**attempt, 8)
                time.sleep(delay)
            except URLError:
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(2**attempt, 8))
        if raw is None:
            raise RuntimeError("WIS2 request did not return a response")
        if len(raw) > self.max_response_bytes:
            raise ValueError("WIS2 response exceeds bounded size")
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("WIS2 response is not an object")
        return payload

    def collection(self) -> dict[str, Any]:
        return self._get_json(
            f"https://{WIS2_HOST}/oapi/collections/{WIS2_COLLECTION}"
        )

    def queryables(self) -> dict[str, Any]:
        return self._get_json(
            f"https://{WIS2_HOST}/oapi/collections/{WIS2_COLLECTION}/queryables"
        )

    @staticmethod
    def parse_feature(feature: object, *, source_url: str) -> Wis2RainRecord | None:
        if not isinstance(feature, dict):
            raise ValueError("WIS2 feature is not an object")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, dict) or not isinstance(geometry, dict):
            raise ValueError("WIS2 feature lacks properties or geometry")
        name = properties.get("name")
        if name != WIS2_PRECIPITATION_NAME:
            return None
        unit = properties.get("units")
        if unit != WIS2_RAW_RAIN_UNIT:
            raise ValueError("unexpected WIS2 precipitation unit")
        record_id = properties.get("id") or feature.get("id")
        wigos = properties.get("wigos_station_identifier")
        if not isinstance(record_id, str) or not record_id or not isinstance(wigos, str) or not wigos:
            raise ValueError("WIS2 precipitation feature lacks official identity")
        if geometry.get("type") != "Point" or not isinstance(geometry.get("coordinates"), list):
            raise ValueError("WIS2 station geometry must be a Point")
        coordinates = geometry["coordinates"]
        if len(coordinates) < 2:
            raise ValueError("WIS2 point geometry is incomplete")
        longitude, latitude = float(coordinates[0]), float(coordinates[1])
        if not (math.isfinite(longitude) and math.isfinite(latitude) and -180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError("WIS2 station coordinates are invalid")
        value = properties.get("value")
        if value is not None:
            if isinstance(value, bool):
                raise ValueError("WIS2 precipitation value is not numeric")
            value = float(value)
            if not math.isfinite(value) or value < 0:
                raise ValueError("WIS2 precipitation value is invalid")
        start, end = parse_phenomenon_time(properties.get("phenomenonTime"))
        return Wis2RainRecord(
            provider_record_id=record_id,
            wigos_station_identifier=wigos,
            station_name=str(properties.get("description") or wigos),
            longitude=longitude,
            latitude=latitude,
            period_start=start,
            period_end=end,
            report_time=_utc(str(properties.get("reportTime"))),
            raw_value=value,
            raw_unit=str(unit),
            source_url=source_url,
        )

    def discover_rain(
        self,
        *,
        bbox: tuple[float, float, float, float] | None,
        datetime_range: str | None = None,
        station_identifier: str | None = None,
        max_pages: int = 10,
        max_records: int = 2000,
        page_size: int = 100,
    ) -> tuple[list[Wis2RainRecord], int, bool]:
        """Return valid precipitation records, examined count, and bbox support.

        All pagination follows only the provider's rel=next link and never
        manufactures offsets. A rejected bbox is reported through the boolean
        so callers may choose a separately bounded fallback.
        """
        if max_pages < 1 or max_records < 1:
            raise ValueError("bounded pagination limits must be positive")
        params = {
            "f": "json",
            "limit": str(min(page_size, max_records)),
            "name": WIS2_PRECIPITATION_NAME,
        }
        if bbox is not None:
            params["bbox"] = ",".join(f"{value:.6f}" for value in bbox)
        if datetime_range is not None:
            params["datetime"] = datetime_range
        if station_identifier is not None:
            params["wigos_station_identifier"] = station_identifier
        query = urlencode(params)
        url = f"{WIS2_ITEMS_URL}?{query}"
        records: list[Wis2RainRecord] = []
        examined = 0
        bbox_supported = True
        for _ in range(max_pages):
            try:
                page = self._get_json(url)
            except Exception:
                if examined == 0 and bbox is not None:
                    return [], 0, False
                raise
            features = page.get("features")
            if not isinstance(features, list):
                raise ValueError("WIS2 page has no feature collection")
            for feature in features:
                examined += 1
                parsed = self.parse_feature(feature, source_url=url)
                if parsed is not None:
                    records.append(parsed)
                if examined >= max_records:
                    return records, examined, bbox_supported
            next_url = next(
                (
                    link.get("href")
                    for link in page.get("links", [])
                    if isinstance(link, dict) and link.get("rel") == "next"
                ),
                None,
            )
            if not isinstance(next_url, str):
                break
            url = next_url
        return records, examined, bbox_supported


def _comparison_text(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
        .split()
    )


@dataclass(frozen=True)
class SidraVariable:
    identifier: str
    label: str
    unit: str


@dataclass(frozen=True)
class SidraBananaMetadata:
    classification_id: str
    classification_label: str
    category_id: str
    category_label: str
    variables: dict[str, SidraVariable]
    period: str


def parse_sidra_metadata(payload: object, periods: object) -> SidraBananaMetadata:
    if not isinstance(payload, dict):
        raise ValueError("SIDRA metadata must be an object")
    classifications = payload.get("classificacoes")
    variables = payload.get("variaveis")
    if not isinstance(classifications, list) or len(classifications) != 1:
        raise ValueError("SIDRA table 1613 must have exactly one product classification")
    classification = classifications[0]
    if not isinstance(classification, dict):
        raise ValueError("SIDRA classification is malformed")
    categories = classification.get("categorias")
    if not isinstance(categories, list):
        raise ValueError("SIDRA product classification has no categories")
    banana = [
        category
        for category in categories
        if isinstance(category, dict)
        and _comparison_text(str(category.get("nome", "")))
        in {"banana", "banana (cacho)"}
    ]
    if len(banana) != 1:
        raise ValueError("SIDRA banana category is absent or ambiguous")
    if not isinstance(variables, list):
        raise ValueError("SIDRA variables are malformed")
    targets = {
        "area_destined": "area destinada a colheita",
        "area_harvested": "area colhida",
        "production": "quantidade produzida",
        "yield": "rendimento medio da producao",
        "production_value": "valor da producao",
    }
    resolved: dict[str, SidraVariable] = {}
    for key, target in targets.items():
        matches = [
            variable
            for variable in variables
            if isinstance(variable, dict)
            and _comparison_text(str(variable.get("nome", ""))) == target
        ]
        if len(matches) != 1:
            raise ValueError(f"SIDRA required variable {key} is absent or ambiguous")
        item = matches[0]
        resolved[key] = SidraVariable(
            str(item.get("id")), str(item.get("nome")), str(item.get("unidade"))
        )
    if not isinstance(periods, list) or not periods:
        raise ValueError("SIDRA periods are unavailable")
    period = max(str(item.get("id")) for item in periods if isinstance(item, dict))
    return SidraBananaMetadata(
        classification_id=str(classification.get("id")),
        classification_label=str(classification.get("nome")),
        category_id=str(banana[0].get("id")),
        category_label=str(banana[0].get("nome")),
        variables=resolved,
        period=period,
    )


@dataclass(frozen=True)
class SidraValue:
    value: float | None
    state: str
    raw_value: str


def parse_sidra_value(raw_value: object) -> SidraValue:
    raw = "" if raw_value is None else str(raw_value).strip()
    if raw == "":
        return SidraValue(None, "MISSING", raw)
    if raw == "-":
        return SidraValue(None, "NOT_APPLICABLE", raw)
    if raw == "..":
        return SidraValue(None, "NOT_AVAILABLE", raw)
    if raw == "...":
        return SidraValue(None, "MISSING", raw)
    if raw.casefold() == "x":
        return SidraValue(None, "SUPPRESSED", raw)
    try:
        value = float(raw.replace(".", "").replace(",", ".")) if "," in raw else float(raw)
    except ValueError as exc:
        raise ValueError("unknown SIDRA value marker") from exc
    if not math.isfinite(value):
        raise ValueError("SIDRA numeric value must be finite")
    return SidraValue(value, "ZERO" if value == 0 else "NUMERIC", raw)


class SidraPamProvider:
    """Public IBGE SIDRA PAM 1613 metadata and bounded municipality client."""

    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    def _get_json(self, url: str) -> object:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "servicodados.ibge.gov.br",
            "apisidra.ibge.gov.br",
        }:
            raise ValueError("SIDRA URL is outside approved official hosts")
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "RibeiraConecta/1.0 official-public-data"})
        with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 -- approved HTTPS host above
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("SIDRA response exceeds bounded size")
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))

    def metadata(self) -> SidraBananaMetadata:
        return parse_sidra_metadata(
            self._get_json(SIDRA_METADATA_URL), self._get_json(SIDRA_PERIODS_URL)
        )

    def values(self, municipality_codes: Iterable[str], metadata: SidraBananaMetadata) -> list[dict[str, Any]]:
        municipalities = ",".join(str(code) for code in municipality_codes)
        if not municipalities:
            return []
        variable_ids = ",".join(item.identifier for item in metadata.variables.values())
        url = (
            f"{SIDRA_VALUES_BASE_URL}/t/1613/n6/{municipalities}/v/{variable_ids}"
            f"/p/{metadata.period}/c{metadata.classification_id}/{metadata.category_id}"
        )
        payload = self._get_json(url)
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise ValueError("SIDRA values response is malformed")
        return list(payload)


def parse_sidra_baselines(
    rows: Iterable[dict[str, Any]], metadata: SidraBananaMetadata
) -> dict[str, dict[str, Any]]:
    """Parse the compact SIDRA values representation without losing markers."""
    expected_ids = {item.identifier: key for key, item in metadata.variables.items()}
    results: dict[str, dict[str, Any]] = {}
    for row in rows:
        # The API's first row labels the columns and is not a data record.
        if row.get("NC") == "Nível Territorial (Código)":
            continue
        if str(row.get("NC")) != "6" or str(row.get("D3C")) != metadata.period:
            raise ValueError("SIDRA response has an unexpected territorial level or period")
        if str(row.get("D4C")) != metadata.category_id or str(row.get("D4N")) != metadata.category_label:
            raise ValueError("SIDRA response does not match the resolved banana category")
        municipality = str(row.get("D1C", ""))
        variable_key = expected_ids.get(str(row.get("D2C")))
        if not municipality or variable_key is None:
            raise ValueError("SIDRA response has an unknown municipality or variable")
        expected = metadata.variables[variable_key]
        # The aggregate metadata describes historical unit ranges for some
        # variables (notably production value); the values endpoint supplies
        # the authoritative unit for the selected period. Labels must still
        # match exactly and the period unit must be explicit.
        if str(row.get("D2N")) != expected.label or not str(row.get("MN", "")).strip():
            raise ValueError("SIDRA response unit or label differs from metadata")
        parsed = parse_sidra_value(row.get("V"))
        record = results.setdefault(
            municipality,
            {"numbers": {}, "raw": {}, "states": {}, "status": "WITH_DATA"},
        )
        if variable_key in record["raw"]:
            raise ValueError("SIDRA response duplicates a municipality variable")
        record["numbers"][variable_key] = parsed.value
        record["raw"][variable_key] = parsed.raw_value
        record["states"][variable_key] = parsed.state
        record.setdefault("units", {})[variable_key] = str(row["MN"])
    for record in results.values():
        missing = set(metadata.variables) - set(record["raw"])
        if missing:
            record["status"] = "PARTIAL"
        elif any(state not in {"NUMERIC", "ZERO"} for state in record["states"].values()):
            record["status"] = "MISSING"
    return results
