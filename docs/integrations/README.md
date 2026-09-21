# Integration catalogue

External providers sit behind bounded, provider-specific adapters and common
domain interfaces. An integration record documents purpose, data type,
authentication, known rate/terms limits, quality, cache/retry policy,
provenance, health check, failure behavior, fallback policy and classification.
It never contains a secret.

| Integration | State | Contract / restriction |
|---|---|---|
| CDSE STAC/S3 | Current | Official collection metadata and controlled authenticated asset access; [details](../geospatial/COPERNICUS_PROVIDER.md). |
| Sentinel-1/2 | Current catalogue capability | Mission identity is separate from provider; selection uses exact catalogue metadata. |
| Google Earth Engine | `LATER` | Optional provider/data-access adapter only; no Google Earth visualization imagery as evidence. |
| USGS/NASA Landsat 8/9 | `LATER` | Official contract/licence/comparability test required before use. |
| JRC | `LATER` | Dataset-specific provenance and methodology required. |
| WIS2/INMET | `PREPARED/VERIFY` | Use only verified provider contract and station provenance. |
| ANA | `BLOCKED` | `AUTH_REQUIRED_PENDING_PROVIDER`. |
| SAISP | `BLOCKED` | Automation is not approved; fail closed. |
| IoT provider/device | `PLANNED` | Tenant-bound authenticated MQTT/HTTPS and health/provenance contract. |

Provider redundancy is explicit policy, not invisible fallback. It must retain
dataset/item compatibility and provenance; a failure becomes an explicit data
quality state. See [source catalogue](../data/SOURCE_CATALOG.md).
