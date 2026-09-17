# Raster processing

Raster processing is asynchronous at the domain boundary through
`ProcessingJob` states: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED` and
`CANCELLED`. The current local worker executes the bounded job explicitly; the
API does not perform long raster work during scene discovery.

The processor uses Rasterio and NumPy, transforms the WGS84 AOI to each source
raster CRS, masks both inputs to the AOI, aligns the NIR grid to the RED grid,
and writes a derived Cloud Optimized GeoTIFF. The persisted output is reopened
through GDAL/Rasterio and must be recognized as `IMAGE_STRUCTURE:LAYOUT=COG`.
Validation also checks GTiff driver, tiled blocks, DEFLATE compression, one band,
CRS, transform, dimensions, NaN nodata and a readable NDVI window within
`[-1, 1]`. It does not accept an extension or metadata string as proof of COG.
The job records algorithm ID/version,
formula, input asset keys, AOI checksum, scene ID, acquisition time, output
checksum and limitations.

The development object store uses `local://` references and refuses remote URLs,
path traversal and oversized objects. `CdseS3AssetAdapter` is a separate
provider-specific acquisition adapter: it validates the exact bucket, validates
the configured HTTPS endpoint, checks object size with `HeadObject`, streams the
object with bounded reads, computes a local SHA-256, and stores it atomically.
Only the RED and NIR assets resolved by the validated collection mapping are
requested for NDVI; metadata discovery never downloads assets.

The initial strategy is controlled local download rather than remote GDAL/range
reads. This makes the bytes, checksum, cleanup and retry boundary explicit and
reproducible. Per-object, per-job, asset-count, timeout and retry limits are
configuration, not infinite defaults. A future remote-window implementation
must preserve the same provenance and SSRF controls.

COG output is reopened and validated for driver/layout, nodata, CRS and
transform. NDVI values outside `[-1, 1]` fail the job; they are not silently
clamped.

## Verification boundaries

`tests/test_geospatial.py` uses explicitly synthetic rasters to verify COG
acceptance and rejection of a regular GeoTIFF. The PostgreSQL/PostGIS integration
test uses explicitly synthetic STAC and S3 fixture bytes to verify persistence,
checksums, evidence linkage and RLS; it is not a claim about a live Sentinel-2
scene. `tests/integration/test_cdse_s3_external.py` is opt-in and validates the
persisted COG from live CDSE RED/NIR bytes when runtime credentials are present.

On 2026-09-17, the opt-in test completed against CDSE with 144488401 downloaded
bytes and 11273 valid NDVI pixels. It passed local RED/NIR and output SHA-256
checks, the `[-1, 1]` range check and structural COG validation. This observation
does not persist a customer evidence chain; PostgreSQL/PostGIS persistence is
verified separately with explicitly synthetic test data.
