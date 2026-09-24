# Ribeira Maps / Farm 360 v1

Farm 360 is an authenticated operational workspace over the Phase 1C pipeline.
It can create a property AOI, request a CDSE STAC search and explicitly start
an NDVI job for the scene selected by the persisted selection policy. It never
downloads CDSE assets or runs NDVI as an implicit browser side effect.

```text
Property (PostGIS AOI)
  -> SatelliteScene + SatelliteAsset catalogue
  -> ProcessingJob
  -> quantitative NDVI COG in tenant object storage
  -> authenticated tenant-scoped PNG tile (window/reprojection)
  -> MapLibre map + metadata + Evidence Chain
```

## Evidence First

The UI only renders values carried by the persisted records. `NULL`, `UNKNOWN`,
`DADO_INSUFICIENTE` and `SOURCE_UNAVAILABLE` stay explicit; it never substitutes
a scene, value, timestamp, coverage or statistic. NDVI is `DERIVED`, keeps its
formula, input asset keys, checksum, limits and evidence. The display palette is
generated only for the PNG tile and never alters the float NDVI COG.

No demo customer or property is seeded by this feature. Unit tests use only
explicitly labelled `synthetic_test_data` and `TEST_AOI_ONLY`; neither is a
customer observation or a commercial record. The controlled real E2E run uses
the separate `CDSE Real Evidence Validation` tenant; it is a validation tenant,
not a customer tenant.

Property creation requires a GeoJSON geometry in an explicit CRS and a boundary
origin. The AOI area is calculated geodesically by the API; it is never guessed.
The persisted `boundary_source` and `MANUAL_CONFIRMED` classification are shown
alongside the property. Legacy properties legitimately retain `UNKNOWN` for a
missing boundary origin.

## Operations workspace

The workspace lists tenant-scoped properties, keeps the map as the main view,
and exposes the existing real flow:

```text
Property AOI -> persisted CDSE STAC search -> policy-selected candidate
             -> persisted NDVI job -> explicit run -> real COG/product
             -> timeline/comparison -> provenance/evidence
```

The scene list presents provider metadata exactly as returned (including an
explicit `UNKNOWN` cloud value when absent). It does not fabricate a fallback
scene or raster. A job reports its persisted status (`QUEUED`, `RUNNING`,
`SUCCEEDED`, `FAILED`; access blocks are identified by their real failure code).
Selection is policy-driven in this phase; a manual override workflow requires
its own auditable approval policy and is deliberately not implied by the UI.

The customer-facing satellite section can show a persisted catalogue scene
before any derived product exists. It labels this as catalogue metadata and
retains acquisition time, reported cloud coverage and provider provenance. A
scene does not enable NDVI controls or imply vegetation, agronomic or flood
conclusions; those require a separately persisted, traceable derived product.

When persisted property assets are available, Farm360 renders them as a
separate Digital Twin map layer and lists them for inspection. Selection shows
only stored type, status, geometry, CRS, source reference, observed timestamp,
classification and context. An empty inventory remains
`DADO_INSUFICIENTE`; visualizing an asset never asserts unrecorded equipment,
calibration, connectivity or condition.

At the current zoom, very close real asset locations may be represented by one
temporary overlap marker. Selecting it opens the names of every corresponding
persisted asset; selecting an asset from the list recentres and highlights its
real location. This is a screen-space interaction aid, not a coordinate edit,
derived position or asset relationship. Zooming can separate the original
positions where their actual geometries permit it.

The map also accepts an explicit coordinate pair for local navigation while drawing or inspecting a property. It uses no geocoder or external provider: a temporary marker and viewport change are purely a screen interaction. The lookup is not persisted, does not change a boundary or asset coordinate, and is not evidence of an address, ownership, coverage or condition.

## Terrain foundation

`terrain.py` provides the bounded, provider-neutral calculation core for an
explicitly supplied DEM: clipped elevation, slope, downslope aspect, hillshade and an
optional line-profile sample at DEM-resolution intervals. Its input AOI is transformed from WGS84 to a
projected metre-based DEM CRS; geographic or rotated grids are rejected rather
than producing misleading slope values. Border cells and cells with missing
neighbours remain unavailable, and profile samples over nodata remain `NULL`; intermediate profile samples are derived from the DEM grid, not a surveyed trace. A requested profile must be wholly inside the supplied AOI: Ribeira rejects an outside segment rather than silently clipping it or attributing neighbouring terrain to the property.

This is not yet a configured customer-facing terrain layer. A future ingest
increment must use an approved, allowlisted DEM provider and persist its
dataset/version, source reference, acquisition/publication time, checksum,
resolution, CRS, processing version and limitations before a result is exposed
or stored. Derived terrain is neither a field survey nor legal boundary,
drainage, soil, coverage or agronomic conclusion.

## Read endpoints

- `GET /v1/tenants/{tenant_id}/properties`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/geospatial`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/assets`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/scenes`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/derived-products`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/timeline`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/temporal-comparison?baseline_product_id={id}&target_product_id={id}`
- `GET /v1/tenants/{tenant_id}/derived-products/{product_id}/provenance`
- `GET /v1/tenants/{tenant_id}/derived-products/{product_id}/tiles/{z}/{x}/{y}`

Write operations use the same tenant authorization and RLS context:

- `POST /v1/tenants/{tenant_id}/properties`
- `POST /v1/tenants/{tenant_id}/properties/{property_id}/satellite-searches`
- `POST /v1/tenants/{tenant_id}/properties/{property_id}/ndvi-jobs`
- `POST /v1/tenants/{tenant_id}/processing-jobs/{job_id}/run`

All need the established bearer authentication and tenant authorization. The
property-assets inventory requires `asset:read`, resolves the property inside
the tenant transaction/RLS context, and returns only persisted asset type,
status, geometry, source reference, timestamp, classification and context. It
does not infer a missing physical asset, location, condition or calibration.
An asset registration that names a property rejects a property outside the
tenant.

All other read endpoints need the established bearer authentication and tenant authorization. The
tile endpoint applies `geospatial:read`, resolves the product under the tenant
transaction/RLS context, validates XYZ coordinates (zoom 0–22), and only then
resolves its already-persisted opaque object reference. It never accepts a
filename or object key from the browser and does not return a filesystem path,
S3 URL, CDSE credential or raw metadata reference. Tiles are `image/png` with
`private, max-age=300` and `Vary: Authorization`; all other `/v1` responses are
`no-store`.

The minimal renderer uses Rasterio to reproject a 256×256 destination window
from the COG to EPSG:3857. This gives windowed reading, avoids whole-file or
base64 transfer, and leaves room to move it into a separate service if measured
tile load requires it. A full TiTiler deployment is intentionally out of scope.

## Frontend

`frontend/` is a strict TypeScript React/Vite application using MapLibre GL JS.
It gets the API base URL, tenant, property and an already-issued session token
at runtime through `VITE_RIBEIRA_*` configuration. Do not put CDSE secrets in
Vite variables. For local use, bind only to loopback (the `dev` script uses
`127.0.0.1`) and forward it over SSH if needed.

`VITE_*` values are compiled into browser-delivered code and are not secret
storage. `VITE_RIBEIRA_ACCESS_TOKEN` is permitted only for a short-lived,
discardable local validation token; it must never contain a production CDSE
credential or be committed. Production session handling remains outside this
slice. The MapLibre request transform attaches that token only to the exact
same-origin Ribeira derived-product XYZ endpoint, never to basemap styles,
glyphs, sprites, or other third-party origins.

### Visual basemap

Farm360 defaults to a minimal CARTO raster style through
`VITE_RIBEIRA_BASEMAP_STYLE_URL`, with `VITE_MAP_STYLE_URL` retained only as a
legacy override. The default has one CORS-enabled tile origin and no sprite,
glyph or vector-style dependency, while an operator can substitute an approved
style without an application rewrite.
The basemap is geographic orientation only: it is not an analytical layer,
evidence source, or fallback for missing property, satellite, environmental or
agronomic data. Map requests never forward Ribeira bearer tokens to that
provider. Property boundaries and asset geometries always come from the
tenant-scoped Ribeira API and retain their own provenance.

The Farm360 layer manager reads this same runtime configuration. It labels the
selected provider only when its style/key is configured, calls it visual
reference only, and reports the local neutral background as unavailable rather
than claiming OpenFreeMap is active.

Current CARTO raster access requires a key. Set
`VITE_RIBEIRA_CARTO_BASEMAP_API_KEY` only in protected build/runtime
configuration when CARTO is the selected provider. Since a browser retrieves
tiles directly, this is a **public restricted credential**, not a secret: it
must be domain/referer restricted, quota-limited, rotated through the provider,
never committed or logged. Without an approved configured provider, Farm360
uses a neutral background and explicitly says that a basemap is unavailable;
it never presents CARTO's watermark as a usable customer map.

For the pilot, protected frontend build configuration selects
`VITE_RIBEIRA_BASEMAP_PROVIDER=openfreemap` and
`VITE_RIBEIRA_BASEMAP_STYLE_URL=https://tiles.openfreemap.org/styles/liberty`.
OpenFreeMap needs no key. Its style, sprites, glyphs and tiles use the exact
`https://tiles.openfreemap.org` origin; attribution remains enabled. Future
providers include `OPENFREEMAP`, `CARTO`, `PROTOMAPS`, `SELF_HOSTED` and another
approved configured provider. OpenFreeMap public hosting has no SLA: a future
production option is self-hosted OpenFreeMap or Protomaps/PMTiles, while the
current fallback keeps property overlays and states that only the basemap is
unavailable.

The property map has a visible boundary fill/outline, automatic fit to the
persisted boundary, clickable asset markers, a recenter control, zoom controls
and metric scale. A basemap failure must not be interpreted as the absence of
the persisted property geometry; the map still attempts to render the local
tenant-scoped boundary and assets.

```bash
cd frontend
npm install
npm run typecheck && npm run lint && npm test && npm run build
```

The current MapLibre bundle is approximately 224 kB minified in the production
build. Code splitting or a prebuilt basemap/style is the next performance step
if field use proves it necessary. The normal Node 18 local environment is
supported by Vite 6.

For Phase 1E temporal selection and comparison semantics, including why V1
does not create an unproven pixel delta raster, see
`docs/geospatial/TEMPORAL_INTELLIGENCE_V1.md`.

## MapLibre worker with Vite

MapLibre 6 derives its worker URL relative to `import.meta.url`. Vite's default
dependency optimization rewrites that URL into `node_modules/.vite/deps` but
does not emit MapLibre's sibling `maplibre-gl-worker.mjs`, causing a worker 404.
Clearing the Vite cache alone does not fix this. `MapCanvas` therefore imports
`maplibre-gl-worker.mjs?worker&url` and calls `setWorkerUrl()` once before any
map instance. Vite emits a hashed, bundled worker asset under `dist/assets/`;
deployment validation must request that exact emitted URL and require HTTP 200
with a JavaScript MIME type. The browser must never request the non-emitted
`/assets/maplibre-gl-worker.mjs` fallback path.
