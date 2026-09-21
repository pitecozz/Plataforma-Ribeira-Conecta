# Source catalogue

Every source is registered with provider, dataset/product, authority,
authentication state, terms/licence, rate/bounds, data class, freshness,
cache/retry and failure behavior, provenance reference, health-check and
fallback policy. Secrets, access tokens and private endpoints are never
documented here.

| Provider/source | Purpose and current state | Failure/fallback policy |
|---|---|---|
| Copernicus CDSE | Official Sentinel catalogue; controlled asset-access capability. | Bounded official adapter; explicit unavailable/credential/coverage result; no silent provider replacement. |
| IBGE official boundaries | Municipal/property-context reference where verified. | Preserve source/version/geometry validation; missing coverage remains unknown. |
| JRC | Future water/environment context. | Dataset-specific adapter and methodology required. |
| WIS2/INMET and verified weather | Future/verified weather observation. | Station representativeness/gaps recorded; no interpolation as observation. |
| ANA | River/hydrology provider candidate. | `AUTH_REQUIRED_PENDING_PROVIDER`; no bypass. |
| SAISP | Potential public information context. | `NOT_APPROVED_FOR_AUTOMATION`; fail closed. |
| Google Earth Engine / USGS/NASA | Optional provider-neutral data/processing paths. | Future opt-in contracts; Google Earth visualization is not evidence. |

See [integration catalogue](../integrations/README.md) and
[provider abstraction](../geospatial/PROVIDER_ABSTRACTION.md).
