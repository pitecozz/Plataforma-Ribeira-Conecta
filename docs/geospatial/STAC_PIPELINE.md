# STAC pipeline

```text
Property geometry + explicit CRS
  -> WGS84 AOI transformation
  -> CDSE STAC POST /v1/search
  -> paginated and bounded response
  -> raw response object reference
  -> tenant-scoped scene and asset catalogue
  -> explicit scene-selection policy
  -> evidence and audit
  -> authenticated CDSE S3 RED/NIR acquisition when processing is requested
  -> bounded AOI NDVI processing and validated COG
```

The request requires a timezone-aware start and end. No default time window is
silently inserted. Search pagination is bounded by both policy and adapter page
limits. `429`, 5xx, malformed payloads, redirects, non-allowlisted links and
SSRF destinations become explicit provider errors.

Provider and collection metadata are global configuration. Scene, asset, search,
candidate, processing job and derived product records are tenant-scoped copies;
this keeps audit and RLS boundaries simple and avoids sharing a customer AOI or
raw reference accidentally.

The internal API exposes domain operations (search, list scenes, create/run
NDVI job, provenance), not generic STAC CRUD.

CDSE is the current adapter, not a domain dependency. Other independent
providers can implement the same provider-neutral catalogue/asset/processing
ports only after their source, licensing, processing semantics and provenance
are recorded. A provider failure never causes an implicit switch or a fallback
to Google Earth visualization imagery.

An STAC `s3://` href is only a catalog reference until the provider-specific
adapter validates its exact bucket and obtains authenticated access. Missing or
rejected credentials are explicit processing outcomes; they do not trigger a
different provider or synthetic raster.
