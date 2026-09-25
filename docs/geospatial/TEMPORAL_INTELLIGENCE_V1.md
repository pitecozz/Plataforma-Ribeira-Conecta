# Temporal Intelligence V1

Phase 1E extends Farm 360's persisted Sentinel-2/NDVI catalogue. It is a
read-only temporal view; opening the page never searches CDSE, downloads an
asset, regenerates NDVI, recalculates a checksum, or creates a product.

```text
Property / AOI
  -> dated SatelliteScene
  -> ProcessingJob
  -> persisted NDVI COG / DerivedProduct
  -> chronological timeline
  -> selected authorized PNG tile + metadata + Evidence Chain
```

The existing schema already has the required cardinality: every
`satellite_scene` has its own `acquisition_datetime`, and every
`derived_product` references its scene and processing job. Phase 1E adds no
redundant timestamp table or migration.

## Temporal contracts

- `GET /v1/tenants/{tenant_id}/properties/{property_id}/timeline` returns
  catalogued products in deterministic `acquisition_datetime_asc` order, then
  product creation time and ID for ties. It returns only persisted scene
  metadata, product statistics, status, checksum and provenance availability.
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/temporal-comparison?baseline_product_id={id}&target_product_id={id}` requires two different,
  tenant-scoped NDVI products of the requested property.

The Farm 360 default is deliberately deterministic: the most recent successful
product in that ascending catalogue. A user selection always takes precedence.
The selected product is the only product whose tile, scene metadata and
provenance are shown.

## Comparison semantics and limits

V1 exposes `target.mean - baseline.mean` only when both persisted products have
successful jobs, output COG references, valid pixels and a stored mean. It is
labelled `DERIVED_AGGREGATE`; it is not a pixel-aligned raster delta. This
fallback is property-scoped only. A field/talhão request requires a valid
field-clipped delta with its exact boundary snapshot; otherwise the result is
`DADO_INSUFICIENTE` and no property aggregate is presented as field evidence.

`comparable_valid_pixels` and `comparable_coverage_percentage` are therefore
`NULL` rather than invented.

No delta COG is created in this phase. A future delta product must first make
CRS, resolution, transform, AOI, nodata/mask policy and any reprojection
explicitly reproducible in a processing job and evidence chain. Neither an
aggregate difference nor a raster delta identifies disease, water stress,
nutrient condition, yield, loss, gain, or any other cause. The response carries
these limitations and reports `DADO_INSUFICIENTE` when the evidence is not
sufficient.

## Evidence and security

For either selected product, the existing provenance endpoint provides:

```text
DerivedProduct -> ProcessingJob -> RED/NIR assets -> Sentinel scene
               -> acquisition datetime -> provider / STAC source -> evidence
```

Timeline and comparison first authorize `geospatial:read`, validate the route
property under the tenant transaction, and query through the existing RLS/force
RLS scope. Products from another tenant are invisible/denied; a product from a
different property is rejected. The selected COG remains available only through
the existing authorized tenant-scoped tile endpoint. The browser never receives
object-store paths, CDSE S3 URLs or CDSE credentials.

Farm360 uses a provider-neutral visual-basemap configuration. The default is a
minimal CARTO raster style via `VITE_RIBEIRA_BASEMAP_STYLE_URL`; it is
geographic context only, never a remote-sensing evidence fallback or analytical
input. Its requests never receive the Ribeira bearer token.
`VITE_*` values are browser-visible build/runtime configuration, not secret
storage; a `VITE_RIBEIRA_ACCESS_TOKEN` may only be a short-lived local
development token and never a CDSE credential.

## Controlled real-data validation

`TEST_AOI_ONLY` and `RUNTIME_VALIDATION_TEST_DEMO` are explicitly test/demo
identities, never customer records. Where credentials are available, the
controlled worker may catalogue two real CDSE Sentinel-2 scenes and persist the
corresponding independently derived NDVI COGs. Credentials stay in the worker
environment and must not be printed, committed, passed to Vite, or returned by
the API.
