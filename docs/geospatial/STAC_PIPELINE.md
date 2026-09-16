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
