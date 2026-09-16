# Sentinel-2 Level-2A

The first collection is the live CDSE collection `sentinel-2-l2a`. Collection
metadata is fetched from the provider and persisted with its retrieval time and
raw metadata reference. The adapter does not assert band mappings from numeric
position. NDVI processing resolves the provider item assets by validated
semantic metadata: the reflectance asset titled `Red (band 4) - 10m` and the
reflectance asset titled `NIR 1 (band 8) - 10m`. The resolved asset keys are
stored in the derived product provenance.

Only one derived index is in scope: `NDVI = (NIR - RED) / (NIR + RED)`. A zero
denominator and source nodata become `NO_DATA`, never zero. The result is
classified `DERIVED` and is not a disease diagnosis, cause attribution or
agronomic recommendation.

Cloud cover is copied from `eo:cloud_cover` when present. It is scene metadata,
not a pixel-level cloud mask. Partial coverage and missing quality layers are
reported as limitations.
