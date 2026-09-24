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
  -> durable processing job (when a product is authorized and inputs exist)
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

## Scheduling foundation

The existing `satellite_search` history and PostgreSQL `processing_job` queue
are the durable foundations. The next increment adds a tenant-isolated refresh
policy/schedule record and private scheduler that creates bounded searches only
when due; it must persist last attempt, retry state and the three freshness
references above. Provider schedules are policy-driven, bounded and fail
closed. It must not poll continuously or enqueue duplicate
property/scene/product/version work.

Initial backfill after approved property creation uses recent scenes plus a
bounded historical window where policy permits. Terrain and environmental
providers follow their own configured refresh policies. No KML re-import is
required for any of these data refreshes.

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
