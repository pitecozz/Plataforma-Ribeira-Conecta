# Automatic property data refresh

A boundary imported from KML, KMZ or GeoJSON is the property spatial reference
after the existing validation and approval workflow. The original import,
geometry, CRS, calculated area, placemarks/assets, source, checksum and audit
history remain evidence. Provider activity never rewrites that boundary.

## Canonical flow

```text
approved property AOI
  -> provider-specific bounded search
  -> exact AOI coverage and quality policy
  -> persisted scene catalogue/history
  -> durable refresh run and processing job (when a product is authorized and inputs exist)
  -> derived product/context/report
```

The same pipeline serves an initial backfill, a scheduled refresh and an
authorized **Buscar dados mais recentes** action. Manual refresh is not a
different or less-audited path.

## Freshness semantics

For every provider/dataset/property tuple, retain independently:

- `LATEST_AVAILABLE_SCENE`: newest returned catalogue item with valid metadata;
- `LATEST_USABLE_SCENE`: newest item selected after exact coverage and the
  configured quality policy;
- `LATEST_PROCESSED_SCENE`: newest scene with a successful persisted product.

These are not interchangeable. A later scene may fail coverage, cloud, asset
availability or processing checks. Each search persists its time window,
provider response reference, candidates, selection/rejection criteria, status,
quality and failure. Products are a time series and are never overwritten.

## Implemented scheduling foundation

Migration 034 persists a tenant/property/provider/collection refresh policy and
durable runs. The supported Sentinel-2 policy is enabled after a property is
created with an approved geometry and immediately queues
`INITIAL_PROPERTY_CONTEXT_REFRESH`. The private
`ribeira-property-refresh-worker` claims due work atomically, runs a bounded
CDSE search, catalogs item metadata/assets through the canonical pipeline, and
queues NDVI only when the required protected asset credentials exist.

Policy records retain `enabled`, frequency, window, cloud policy, last/next
search, success/failure time, retry count, status and the three freshness
references. Run records retain trigger, state (`QUEUED`, `RUNNING`,
`SUCCEEDED`, `RETRYABLE`, `BLOCKED`, `FAILED`), bounded exponential retry,
search/job references and a stable idempotency key. Scene and product
idempotency remain enforced by the existing tenant/property/provider/item and
processing-version uniqueness constraints.

The worker is private and must be installed with the existing user-service
installer after migration 034; it is not a public endpoint. `POST .../refreshes`
is an authorized, debounced manual fallback into the same durable path, not the
normal customer workflow. `GET .../refresh-status` supplies Farm360 freshness
status without exposing provider credentials.

Properties created before migration 034 are enrolled by the private, idempotent
`python -m ribeira_platform.property_refresh_bootstrap --apply` command. Its
default is dry run. It only creates policies/runs for existing non-null AOIs;
it never reads, exports or changes boundary geometry.

Initial backfill uses a bounded 90-day window with the configured cloud policy.
The first provider is Sentinel-2/CDSE; Sentinel-1, Landsat, terrain and weather
need their own approved adapter/policy before they are enabled. No KML re-import
is required for data refresh. A future linked KML/KMZ/GeoJSON source may create
a *candidate* boundary version and require human approval; no provider may
silently replace the canonical boundary.

## Boundary safety and interpretation

Remote sensing can create an observation or boundary-review candidate, never a
silent change to the canonical property boundary. Imported values and
platform-derived values keep their own source, time, transformation and
classification. Basemap visualization is not an analytical source.

## Current Sentinel-2 Hamilton evidence

On 2026-09-24, a bounded official CDSE STAC search for the persisted Hamilton
AOI used `sentinel-2-l2a`, `2026-06-16T00:00:00Z` through
`2026-09-24T00:00:00Z`, `eo:cloud_cover <= 50`, and a maximum of 25 candidates.
It completed with 13 candidates. The latest persisted available scene is
`S2C_MSIL2A_20260915T132231_N0512_R038_T22JGT_20260915T162524`, acquired
2026-09-15T13:22:31.025Z with 49.380% provider-reported cloud cover. There is
no processed product yet. This is catalogue evidence only, not NDVI or an
agronomic conclusion.

Downloading Sentinel-2 bands and producing NDVI remains blocked until the
protected CDSE S3 asset credentials are configured. The absence is explicit;
the system does not fabricate a product.
