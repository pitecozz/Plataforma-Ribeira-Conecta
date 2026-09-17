from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    name: str
    category: str
    authority: str
    endpoint: str | None
    license: str | None
    authentication_type: str
    spatial_resolution: str | None
    temporal_resolution: str | None
    version: str | None
    status: str
    last_success: str | None = None
    last_failure: str | None = None
    organization: str | None = None
    provider_type: str | None = None
    documentation_url: str | None = None
    catalog_endpoint: str | None = None
    api_standard: str | None = None
    stac_version: str | None = None
    asset_hosts: frozenset[str] = frozenset()
    asset_endpoint: str | None = None
    asset_bucket: str | None = None


class ProviderRegistry:
    def __init__(self, providers: list[ProviderMetadata] | None = None) -> None:
        self._providers = {item.provider_id: item for item in providers or []}

    def register(self, metadata: ProviderMetadata) -> None:
        self._providers[metadata.provider_id] = metadata

    def get(self, provider_id: str) -> ProviderMetadata | None:
        return self._providers.get(provider_id)

    def endpoint_allowed(self, provider_id: str, endpoint: str) -> bool:
        metadata = self.get(provider_id)
        if metadata is None or metadata.status != "ACTIVE":
            return False
        bases = tuple(
            value for value in (metadata.endpoint, metadata.catalog_endpoint) if value
        )
        return any(
            endpoint == base or endpoint.startswith(base.rstrip("/") + "/")
            for base in bases
        )

    def asset_host_allowed(self, provider_id: str, hostname: str) -> bool:
        metadata = self.get(provider_id)
        return bool(metadata and hostname.lower() in metadata.asset_hosts)

    def asset_endpoint(self, provider_id: str) -> str | None:
        metadata = self.get(provider_id)
        return metadata.asset_endpoint if metadata else None

    def asset_bucket(self, provider_id: str) -> str | None:
        metadata = self.get(provider_id)
        return metadata.asset_bucket if metadata else None
