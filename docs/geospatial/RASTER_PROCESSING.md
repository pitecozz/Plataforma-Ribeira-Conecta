# Raster processing

Raster processing is asynchronous at the domain boundary through
`ProcessingJob` states: `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED` and
`CANCELLED`. The current local worker executes the bounded job explicitly; the
API does not perform long raster work during scene discovery.

The processor uses Rasterio and NumPy, transforms the WGS84 AOI to each source
raster CRS, masks both inputs to the AOI, aligns the NIR grid to the RED grid,
and writes a derived Cloud Optimized GeoTIFF. The output is reopened and checked
for COG layout before it is stored. The job records algorithm ID/version,
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
