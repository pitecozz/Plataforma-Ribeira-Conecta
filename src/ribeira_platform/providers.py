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


class ProviderRegistry:
    def __init__(self, providers: list[ProviderMetadata] | None = None) -> None:
        self._providers = {item.provider_id: item for item in providers or []}

    def register(self, metadata: ProviderMetadata) -> None:
        self._providers[metadata.provider_id] = metadata

    def get(self, provider_id: str) -> ProviderMetadata | None:
        return self._providers.get(provider_id)

    def endpoint_allowed(self, provider_id: str, endpoint: str) -> bool:
        metadata = self.get(provider_id)
        if metadata is None or metadata.status != "ACTIVE" or not metadata.endpoint:
            return False
        return endpoint == metadata.endpoint or endpoint.startswith(
            metadata.endpoint.rstrip("/") + "/"
        )
