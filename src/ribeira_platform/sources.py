from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .epistemology import DataClassification, IngestionStatus, QualityFlag
from .models import FetchResult, Observation, Property, Source, new_id
from .providers import ProviderRegistry
from .security import NetworkPolicy, SSRFBlocked
from .time_utils import canonical_utc


class SourceAdapter(Protocol):
    def fetch_property_observations(
        self, tenant_id: str, property: Property, source: Source
    ) -> FetchResult: ...


def _parse_observations(
    payload: dict[str, Any], tenant_id: str, property: Property, source: Source
) -> list[Observation]:
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list):
        raise ValueError("payload must contain observations list")
    result: list[Observation] = []
    for item in raw_observations:
        if not isinstance(item, dict):
            raise ValueError("observation must be an object")
        required = {"metric", "value", "unit", "observation_timestamp"}
        if not required.issubset(item):
            raise ValueError(
                f"observation missing fields: {sorted(required - set(item))}"
            )
        value = item["value"]
        if value is not None and not isinstance(value, (int, float)):
            raise ValueError("observation value must be numeric or null")
        quality_flag = QualityFlag(item.get("quality_flag", QualityFlag.UNKNOWN))
        if value is None and quality_flag == QualityFlag.VALID:
            quality_flag = QualityFlag.UNKNOWN
        original_timestamp = str(item["observation_timestamp"])
        result.append(
            Observation(
                id=new_id(),
                tenant_id=tenant_id,
                property_id=property.id,
                source_id=source.id,
                metric=str(item["metric"]),
                value=float(value) if value is not None else None,
                unit=str(item["unit"]) if item["unit"] is not None else None,
                observation_timestamp=canonical_utc(original_timestamp),
                original_observation_timestamp=original_timestamp,
                classification=DataClassification.OBSERVED,
                quality_flag=quality_flag,
                raw_data_reference=item.get("raw_data_reference"),
                dataset_version=item.get("dataset_version"),
                spatial_resolution=item.get("spatial_resolution"),
                temporal_resolution=item.get("temporal_resolution"),
                crs=item.get("crs"),
                checksum=item.get("checksum"),
            )
        )
    return result


class HttpJsonSourceAdapter:
    """Adapter for a configured provider endpoint.

    No endpoint means SOURCE_UNAVAILABLE. No fallback values are generated.
    The provider response is expected to be JSON with an `observations` array.
    """

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        network_policy: NetworkPolicy | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.network_policy = network_policy or NetworkPolicy()
        self.provider_registry = provider_registry or ProviderRegistry()

    def fetch_property_observations(
        self, tenant_id: str, property: Property, source: Source
    ) -> FetchResult:
        if not source.endpoint:
            return FetchResult(
                IngestionStatus.SOURCE_UNAVAILABLE,
                [],
                "source endpoint is not configured",
            )
        parsed_endpoint = urllib.parse.urlparse(source.endpoint)
        if (
            parsed_endpoint.scheme not in {"http", "https"}
            or not parsed_endpoint.netloc
        ):
            return FetchResult(
                IngestionStatus.SOURCE_UNAVAILABLE,
                [],
                "source endpoint scheme is not allowed",
            )
        try:
            self.network_policy.validate(source.endpoint)
        except SSRFBlocked as exc:
            return FetchResult(
                IngestionStatus.SOURCE_UNAVAILABLE,
                [],
                f"provider blocked by network policy: {exc}",
            )
        if not self.provider_registry.endpoint_allowed(
            source.provider, source.endpoint
        ):
            return FetchResult(
                IngestionStatus.SOURCE_UNAVAILABLE,
                [],
                "provider endpoint is not allowlisted",
            )
        query = urllib.parse.urlencode({"property_id": property.id})
        url = f"{source.endpoint}{'&' if '?' in source.endpoint else '?'}{query}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            opener = urllib.request.build_opener(_NoRedirectHandler())
            with opener.open(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            observations = _parse_observations(payload, tenant_id, property, source)
            return FetchResult(
                IngestionStatus.INGESTED, observations, "provider response ingested"
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            return FetchResult(
                IngestionStatus.SOURCE_UNAVAILABLE,
                [],
                f"provider unavailable or invalid: {type(exc).__name__}",
            )
        except (json.JSONDecodeError, ValueError) as exc:
            return FetchResult(
                IngestionStatus.INVALID_PAYLOAD,
                [],
                f"provider payload invalid: {type(exc).__name__}",
            )


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise SSRFBlocked("provider redirects are disabled")


@dataclass(frozen=True)
class SyntheticFixtureAdapter:
    """Test-only adapter; never registered by the production application."""

    observations: list[dict[str, Any]]
    synthetic_data: bool = True

    def fetch_property_observations(
        self, tenant_id: str, property: Property, source: Source
    ) -> FetchResult:
        payload = {"observations": self.observations}
        parsed = _parse_observations(payload, tenant_id, property, source)
        parsed = [
            Observation(
                **{
                    **observation.__dict__,
                    "classification": DataClassification.SIMULATED,
                }
            )
            for observation in parsed
        ]
        return FetchResult(
            IngestionStatus.INGESTED,
            parsed,
            "synthetic fixture; tests only",
            DataClassification.SIMULATED,
        )
