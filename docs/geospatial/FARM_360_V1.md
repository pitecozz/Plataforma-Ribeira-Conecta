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

An operator with `property:write` can create a property entirely in Ribeira
Maps: map clicks form a local WGS84 polygon draft, whose individual vertices can
be reviewed, corrected or removed before confirmation. The browser refuses a
drawn draft with fewer than three vertices or coordinates outside WGS84, but it
does not repair topology, calculate a legal area or replace server validation.
No click or coordinate edit is persisted until the explicit create request;
afterwards the API remains responsible for strict polygon validation, checksum,
audit and automatic monitored-context registration. KML/KMZ/GeoJSON import
remains optional and is never a prerequisite for this workflow.

Optional boundary import accepts GeoJSON, KML and KMZ, but no import changes the
canonical property boundary until a separately authorized human review records a
reason and current-boundary checksum. A correction also fails atomically when it
would exclude any current field/talhão boundary; the field must first be corrected
through its own immutable, source-backed boundary history. The original bytes,
SHA-256, filename,
format, declared/detected CRS, parsed-geometry checksum, warnings and audit event
are retained. KML/KMZ are bounded to one unencrypted KML Polygon and KML's WGS84
coordinates; a conflicting caller CRS, unsafe XML declaration, ambiguous polygon,
invalid geometry or oversized compressed expansion is retained as failed evidence,
never repaired or re-labelled. KML altitude is discarded because the boundary is
2D only. These uploaded/drawn geometries are operational AOIs, not legal title or
survey evidence.

An authorized boundary editor starts from the persisted polygon and works with a
local draft. The map renders that draft and a click explicitly appends a vertex;
coordinate fields remain available for correction and the draft can be undone or
cancelled. A map click is not a boundary mutation, observation or confirmation.
Only an explicit save creates a new version through the checksum-protected API,
after the browser verifies each coordinate is finite and within WGS84 longitude
and latitude bounds. Server-side geometry validation, audit and versioning remain
the authority.

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

A user holding the tenant-scoped `asset:manage` permission can register a
manually confirmed asset directly in Farm360. The form requires name, technical
type, reported operational status, confirmation source and observation time; an
optional point is accepted only when both WGS84 longitude and latitude are
valid. The authenticated registration API enforces that non-blank source reference and
observation time too, so a caller cannot bypass the form and create an
unprovenanced new asset record. Missing location remains missing rather than
being derived from the property, map centre or another asset. The browser sends the property ID only
through the authenticated tenant endpoint; the service independently verifies
that property, applies RLS and records the existing `ASSET_REGISTERED` audit
event. The registration creates immutable, tenant-local `ASSET_REGISTRATION` evidence with the submitted source reference, observation time, classification and explicit limitations. Farm360 exposes its opaque identifier in the technical provenance details so an operator may explicitly attach it to a later action outcome. Where the persisted property boundary is available, the same authenticated map lets the operator choose an optional coordinate: the provisional marker only copies the selected WGS84 point into the form and is not saved until the required source and confirmation are submitted. It never derives a location from the property, map centre or basemap. It does not make the asset a measurement or independent verification, and does not assert ownership, calibration, connectivity, service availability or condition beyond the submitted factual fields.

An authorized user can evaluate a rule for one persisted property-linked asset through `POST /v1/tenants/{tenant_id}/assets/{asset_id}/evaluate`. Farm360 shows the dedicated control only when the user holds both `asset:read` and `decision:evaluate`, and only permits it when the selected asset retains its `ASSET_REGISTRATION` evidence identifier. It is an explicit operator action: it never runs because an asset appears on the map or during a property-only evaluation. The server resolves the asset and its property inside the tenant/RLS context. Only an `ASSET`-scoped rule naming that asset can take precedence in that explicit request. The resulting immutable decision records `subject_asset_id`, the factual `ASSET_REGISTRATION` evidence ID and the property observations separately, then Farm360 refreshes the property decision history. An asset registration is not a measurement, condition assessment, diagnostic or automatic action. If its evidence is absent, the API response is explicitly inconclusive and Farm360 leaves the control disabled.

When a persisted property decision creates an `OPEN` human action, a user with
`action:write` can record its result in Farm360. The user supplies the result
text, an explicit classification, the recorded-at time and any tenant-local
evidence identifiers that support that result. The screen never prepopulates
outcome evidence from decision evidence: a recommendation and its subsequent
result are different claims. The original decision remains immutable; the API
records the authenticated actor and audit event, and a failed submission leaves
the action open. Read-only users can inspect the history without seeing the
completion control.

At the current zoom, very close real asset locations may be represented by one
temporary overlap marker. Selecting it opens the names of every corresponding
persisted asset; selecting an asset from the list recentres and highlights its
real location. This is a screen-space interaction aid, not a coordinate edit,
derived position or asset relationship. Zooming can separate the original
positions where their actual geometries permit it.

The map also accepts an explicit coordinate pair for local navigation while drawing or inspecting a property. It uses no geocoder or external provider: a temporary marker and viewport change are purely a screen interaction. The lookup is not persisted, does not change a boundary or asset coordinate, and is not evidence of an address, ownership, coverage or condition.

## Portfolio search

The Maps portfolio can filter the properties already returned by the authenticated,
tenant-scoped portfolio request using their registered names. Matching is local to
that response, case- and accent-insensitive, and narrows the list and portfolio
map only; it performs no address lookup, geocoding, provider request, boundary
mutation or claim about a property beyond its persisted record. A selected Farm360
workspace remains available until the property itself is absent from a refreshed
authorized portfolio.

## Terrain foundation

`terrain.py` provides the bounded, provider-neutral calculation core for an
explicitly supplied DEM: clipped elevation, slope, downslope aspect, hillshade and an
optional line-profile sample at DEM-resolution intervals. The caller must explicitly declare that
the DEM sample values are metres before the core labels any elevation result in metres; its
horizontal CRS alone cannot establish that vertical/value unit. Its input AOI is transformed from WGS84 to a
projected metre-based DEM CRS; geographic or rotated grids are rejected rather
than producing misleading slope values. Border cells and cells with missing
neighbours remain unavailable, and profile samples over nodata or non-finite values remain `NULL`; intermediate profile samples are derived from the DEM grid, not a surveyed trace. Invalid, empty, non-finite or out-of-range WGS84 AOIs/profile geometries and a DEM with no valid clipped elevation cells are rejected rather than becoming an empty terrain conclusion.
The current processor identifier/version is `TERRAIN_DERIVATIVES` `1.1.0`; it changed from
`1.0.0` when explicit elevation-unit attestation became mandatory.
A requested profile must be wholly inside the supplied AOI: Ribeira rejects an outside segment rather than silently clipping it or attributing neighbouring terrain to the property.

This is not yet a configured customer-facing terrain layer. A future ingest
increment must use an approved, allowlisted DEM provider and persist its
dataset/version, source reference, acquisition/publication time, checksum,
resolution, horizontal CRS, elevation value/vertical unit, processing version and limitations before a result is exposed
or stored. Derived terrain is neither a field survey nor legal boundary,
drainage, soil, coverage or agronomic conclusion.

## Field/talhão context foundation

A user with `property:write` may register a field/talhão only against a persisted
tenant property boundary. The request requires a WGS84 Polygon or MultiPolygon,
a factual source reference and its observation time. The submitted geometry must
be fully contained by the current property boundary; Ribeira rejects an outside
or boundary-less field instead of clipping or inferring one.

The initial geometry is stored as immutable version 1 with its checksum,
classification, source/time, tenant-local `FIELD_REGISTRATION` evidence and
`FIELD_REGISTERED` audit event. PostgreSQL migrations 039/040 add forced RLS,
composite tenant/property foreign keys, a PostGIS containment trigger and immutable versions. This
is operational context only: it is not legal title, survey, crop declaration,
soil observation, management zone, agronomic recommendation or rule result.
A later field-boundary update and field/zone/crop rule applicability need their
own explicit versioned workflow; registering a field does not activate a rule.

Farm360 now loads this tenant-scoped inventory as an independent blue map layer and lists each persisted geometry with its source, observation time, classification, boundary-version checksum and opaque evidence identifier. Its availability panel reports only the persisted field count and whether the sourced inventory is absent. A `property:write` user may submit a technical WGS84 Polygon or MultiPolygon from the same workspace; the browser does not clip, repair or infer geometry, and the server remains responsible for containment, provenance, RLS and audit. A missing or unavailable inventory is shown as `DADO_INSUFICIENTE` or a bounded load failure, never as an empty agronomic conclusion. There is no field-boundary editor, crop claim or field-scoped rule activation control in Farm360 in this increment; field-scoped rules are activated and evaluated only through the explicit audited API workflow documented in the rule catalogue.

## Read endpoints

- `GET /v1/tenants/{tenant_id}/properties`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/geospatial`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/assets`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/fields`
- `POST /v1/tenants/{tenant_id}/assets/{asset_id}/evaluate` (requires `asset:read` and `decision:evaluate`; writes an immutable decision)
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/scenes`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/derived-products`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/timeline`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/temporal-comparison?baseline_product_id={id}&target_product_id={id}`
- `GET /v1/tenants/{tenant_id}/derived-products/{product_id}/provenance`
- `GET /v1/tenants/{tenant_id}/derived-products/{product_id}/tiles/{z}/{x}/{y}`

Write operations use the same tenant authorization and RLS context:

- `POST /v1/tenants/{tenant_id}/properties`
- `POST /v1/tenants/{tenant_id}/properties/{property_id}/boundary-imports`
- `POST /v1/tenants/{tenant_id}/properties/{property_id}/satellite-searches`
- `POST /v1/tenants/{tenant_id}/properties/{property_id}/ndvi-jobs`
- `POST /v1/tenants/{tenant_id}/properties/{property_id}/fields`
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
