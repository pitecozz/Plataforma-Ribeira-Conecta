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
path traversal and oversized objects. A production object-store adapter and a
controlled CDSE asset downloader remain gaps. CDSE assets are not downloaded
automatically during metadata discovery.
