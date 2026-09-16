from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, cast

from prometheus_client import Counter, Histogram

from .geospatial import (
    GeospatialProviderPort,
    ProviderSearchResult,
    SatelliteCollection,
    SatelliteSearchRequest,
)
from .providers import ProviderRegistry
from .security import NetworkPolicy, SSRFBlocked


STAC_SEARCHES = Counter(
    "ribeira_stac_search_total", "STAC searches", ["provider", "status"]
)
STAC_ERRORS = Counter(
    "ribeira_stac_search_errors_total", "STAC search errors", ["provider", "error"]
)
STAC_LATENCY = Histogram(
    "ribeira_stac_search_latency_seconds", "STAC search latency", ["provider"]
)
SCENES_DISCOVERED = Counter(
    "ribeira_stac_scenes_discovered_total", "STAC scenes discovered", ["provider"]
)


class StacProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CopernicusStacConfig:
    provider_id: str = "COPERNICUS_CDSE"
    catalog_endpoint: str = "https://stac.dataspace.copernicus.eu/v1/"
    documentation_url: str = (
        "https://documentation.dataspace.copernicus.eu/APIs/STAC.html"
    )
    collection_id: str = "sentinel-2-l2a"
    timeout_seconds: float = 30.0
    max_pages: int = 10


def default_copernicus_registry(
    config: CopernicusStacConfig | None = None,
) -> ProviderRegistry:
    config = config or CopernicusStacConfig()
    host = urllib.parse.urlparse(config.catalog_endpoint).hostname
    if host is None:
        raise ValueError("CDSE catalog endpoint must contain a hostname")
    from .providers import ProviderMetadata

    return ProviderRegistry(
        [
            ProviderMetadata(
                provider_id=config.provider_id,
                name="Copernicus Data Space Ecosystem",
                category="EARTH_OBSERVATION",
                authority="COPERNICUS",
                endpoint=config.catalog_endpoint,
                license="other",
                authentication_type="NOT_DETERMINED",
                spatial_resolution=None,
                temporal_resolution=None,
                version="STAC 1.1.0",
                status="ACTIVE",
                organization="Copernicus Data Space Ecosystem",
                provider_type="EARTH_OBSERVATION",
                documentation_url=config.documentation_url,
                catalog_endpoint=config.catalog_endpoint,
                api_standard="STAC",
                stac_version="1.1.0",
                # The live CDSE response uses s3://eodata/... asset references;
                # this is an explicit provider reference, not a wildcard host.
                asset_hosts=frozenset({host, "eodata"}),
            )
        ]
    )


class CopernicusStacAdapter(GeospatialProviderPort):
    """Small defensive CDSE STAC client using the documented JSON API."""

    def __init__(
        self,
        registry: ProviderRegistry,
        config: CopernicusStacConfig | None = None,
        network_policy: NetworkPolicy | None = None,
    ) -> None:
        self.config = config or CopernicusStacConfig()
        self.registry = registry
        self.network_policy = network_policy or NetworkPolicy(
            allowed_hosts=frozenset(
                {urllib.parse.urlparse(self.config.catalog_endpoint).hostname or ""}
            )
        )

    def _url(self, suffix: str) -> str:
        metadata = self.registry.get(self.config.provider_id)
        if metadata is None or not metadata.catalog_endpoint:
            raise StacProviderError(
                "PROVIDER_NOT_CONFIGURED", "CDSE provider is not configured"
            )
        endpoint = metadata.catalog_endpoint.rstrip("/") + "/"
        url = endpoint + suffix.lstrip("/")
        if not self.registry.endpoint_allowed(self.config.provider_id, url):
            raise StacProviderError(
                "PROVIDER_ENDPOINT_NOT_ALLOWED", "CDSE endpoint is not allowlisted"
            )
        try:
            self.network_policy.validate(url)
        except SSRFBlocked as exc:
            raise StacProviderError("SSRF_BLOCKED", str(exc)) from exc
        return url

    def _request_json(
        self, method: str, url: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.build_opener(_NoRedirectHandler()).open(
                request, timeout=self.config.timeout_seconds
            ) as response:
                raw = response.read(10 * 1024 * 1024 + 1)
                if len(raw) > 10 * 1024 * 1024:
                    raise StacProviderError(
                        "RESPONSE_TOO_LARGE",
                        "CDSE response exceeds the configured limit",
                    )
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                code = "RATE_LIMITED"
            elif 500 <= exc.code <= 599:
                code = "PROVIDER_5XX"
            else:
                code = f"PROVIDER_HTTP_{exc.code}"
            raise StacProviderError(code, f"CDSE returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise StacProviderError(
                "SOURCE_UNAVAILABLE", "CDSE request failed"
            ) from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StacProviderError(
                "INVALID_PAYLOAD", "CDSE response is not valid JSON"
            ) from exc
        if not isinstance(value, dict):
            raise StacProviderError(
                "INVALID_PAYLOAD", "CDSE response must be a JSON object"
            )
        return value

    def get_collection(self, collection_id: str) -> SatelliteCollection:
        payload = self._request_json(
            "GET", self._url(f"collections/{urllib.parse.quote(collection_id)}")
        )
        if payload.get("type") != "Collection" or payload.get("id") != collection_id:
            raise StacProviderError(
                "INVALID_PAYLOAD", "CDSE collection response is invalid"
            )
        summaries_raw = payload.get("summaries")
        summaries: dict[str, Any] = (
            cast(dict[str, Any], summaries_raw)
            if isinstance(summaries_raw, dict)
            else {}
        )
        return SatelliteCollection(
            id="",
            provider_id=self.config.provider_id,
            external_collection_id=collection_id,
            title=payload.get("title"),
            mission="Sentinel-2" if "sentinel-2" in collection_id else None,
            processing_level=(summaries.get("processing:level") or [None])[0]
            if isinstance(summaries.get("processing:level"), list)
            else summaries.get("processing:level"),
            spatial_resolution=json.dumps(summaries.get("gsd"), separators=(",", ":"))
            if summaries.get("gsd") is not None
            else None,
            temporal_characteristics={
                "extent": payload.get("extent", {}).get("temporal")
                if isinstance(payload.get("extent"), dict)
                else None
            },
            bands={},
            license=payload.get("license"),
            stac_version=payload.get("stac_version"),
            metadata=payload,
        )

    def asset_href_allowed(self, href: str) -> bool:
        parsed = urllib.parse.urlparse(href)
        if parsed.scheme not in {"http", "https", "s3"} or not parsed.hostname:
            return False
        return self.registry.asset_host_allowed(
            self.config.provider_id, parsed.hostname
        )

    def search(
        self, request: SatelliteSearchRequest, aoi_geojson: dict[str, Any]
    ) -> ProviderSearchResult:
        started = time.perf_counter()
        provider = self.config.provider_id
        body: dict[str, Any] = {
            "collections": [request.collection_id],
            "datetime": f"{request.datetime_start}/{request.datetime_end}",
            "intersects": aoi_geojson,
            "limit": min(request.selection_policy.max_candidates, 100),
            "sortby": [{"field": "datetime", "direction": "desc"}],
        }
        if request.selection_policy.cloud_cover_limit is not None:
            body["query"] = {
                "eo:cloud_cover": {
                    "lte": float(request.selection_policy.cloud_cover_limit)
                }
            }
        items: list[dict[str, Any]] = []
        raw_pages: list[dict[str, Any]] = []
        next_url: str | None = self._url("search")
        next_method = "POST"
        next_payload: dict[str, Any] | None = body
        try:
            for _ in range(self.config.max_pages):
                if (
                    next_url is None
                    or len(items) >= request.selection_policy.max_candidates
                ):
                    break
                payload = self._request_json(next_method, next_url, next_payload)
                raw_pages.append(payload)
                features = payload.get("features")
                if not isinstance(features, list):
                    raise StacProviderError(
                        "INVALID_PAYLOAD", "STAC search response lacks features"
                    )
                for feature in features:
                    if isinstance(feature, dict):
                        items.append(feature)
                        if len(items) >= request.selection_policy.max_candidates:
                            break
                link = next(
                    (
                        item
                        for item in payload.get("links", [])
                        if isinstance(item, dict) and item.get("rel") == "next"
                    ),
                    None,
                )
                next_url = link.get("href") if isinstance(link, dict) else None
                if next_url:
                    if not isinstance(next_url, str):
                        raise StacProviderError(
                            "INVALID_PAYLOAD", "STAC next link is invalid"
                        )
                    if not self.registry.endpoint_allowed(provider, next_url):
                        raise StacProviderError(
                            "PROVIDER_ENDPOINT_NOT_ALLOWED",
                            "STAC next link is not allowlisted",
                        )
                    try:
                        self.network_policy.validate(next_url)
                    except SSRFBlocked as exc:
                        raise StacProviderError("SSRF_BLOCKED", str(exc)) from exc
                    next_method, next_payload = "GET", None
        except StacProviderError as exc:
            STAC_ERRORS.labels(provider, exc.code).inc()
            STAC_SEARCHES.labels(provider, "ERROR").inc()
            raise
        finally:
            STAC_LATENCY.labels(provider).observe(time.perf_counter() - started)
        STAC_SEARCHES.labels(provider, "SUCCESS").inc()
        SCENES_DISCOVERED.labels(provider).inc(len(items))
        return ProviderSearchResult(items=items, raw_pages=raw_pages)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise StacProviderError("REDIRECT_BLOCKED", "provider redirects are disabled")
