# Ribeira Maps / Farm 360 v1

Farm 360 is a read-only operational view of data already persisted by the Phase
1C pipeline. It does not discover Sentinel scenes, download CDSE assets or run
NDVI as a side effect of a browser request.

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

No demo customer or property is seeded by this feature. The tests use only
explicitly labelled `synthetic_test_data` and `TEST_AOI_ONLY`; neither is a
customer observation or a commercial record.

## Read endpoints

- `GET /v1/tenants/{tenant_id}/properties`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/geospatial`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/scenes`
- `GET /v1/tenants/{tenant_id}/properties/{property_id}/derived-products`
- `GET /v1/tenants/{tenant_id}/derived-products/{product_id}/provenance`
- `GET /v1/tenants/{tenant_id}/derived-products/{product_id}/tiles/{z}/{x}/{y}`

All need the established bearer authentication and tenant authorization. The
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

```bash
cd frontend
npm install
npm run typecheck && npm run lint && npm test && npm run build
```

The current MapLibre bundle is approximately 224 kB minified in the production
build. Code splitting or a prebuilt basemap/style is the next performance step
if field use proves it necessary. The normal Node 18 local environment is
supported by Vite 6.

## MapLibre worker with Vite

MapLibre 6 derives its worker URL relative to `import.meta.url`. Vite's default
dependency optimization rewrites that URL into `node_modules/.vite/deps` but
does not emit MapLibre's sibling `maplibre-gl-worker.mjs`, causing a worker 404.
Clearing the Vite cache alone does not fix this. `vite.config.ts` therefore
excludes only `maplibre-gl` from `optimizeDeps`, so Vite serves the package's
actual `dist/maplibre-gl.mjs` and its sibling worker. No worker is copied into
`public/`.
